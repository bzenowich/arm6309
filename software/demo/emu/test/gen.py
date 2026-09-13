#!/usr/bin/env python3
"""Generate an exerciser program and an interrupt schedule for the differential test.

    gen.py SEED OUTDIR [--maxcyc N] [--undoc]  -> OUTDIR/prog_SEED.{bin,hex,sched}

The program is a run of self-contained chunks, each: load every register the
instruction under test depends on (S, CC, the operand memory, X Y U DP, A B),
then the instruction. Chunks that transfer control arrange their own target -
the next chunk, a subroutine that returns to it, a stack frame that pulls it -
so a divergence cannot run the program off into data, and the diff's first
differing line is the instruction that caused it. The flags need no compare
instructions: the trace carries CC at every boundary.

The chunks loop until the harness's cycle bound, so each pass meets the
interrupt schedule at different instructions. Operands live in $0000-$1FFF,
U stacks in $2000-$2EFF, S stacks in $3000-$3EFF, code from $5000, handlers at
$F000. S is only ever loaded with a stack: an interrupt can arrive anywhere.
"""
import random, sys, os

R = None

EDGE8 = [0x00, 0x01, 0x7F, 0x80, 0x81, 0xFE, 0xFF, 0x0F, 0x10, 0xF0, 0x09, 0x0A, 0x99, 0x90, 0x9A, 0x60, 0x06]
EDGE16 = [0x0000, 0x0001, 0x7FFF, 0x8000, 0x8001, 0xFFFF, 0xFFFE, 0x00FF, 0x0100, 0x7F00, 0x80FF, 0xFF00]

def v8():  return R.choice(EDGE8) if R.random() < 0.45 else R.randrange(256)
def v16(): return R.choice(EDGE16) if R.random() < 0.35 else R.randrange(65536)
def ram_ea(n=1): return R.randrange(0x0100, 0x2000 - n)
def s_sane(): return R.randrange(0x3100, 0x3E00)
def u_sane(): return R.randrange(0x2100, 0x2E00)
def sx8(v): return v - 256 if v & 0x80 else v

RR = {'X': 0, 'Y': 1, 'U': 2, 'S': 3}

# ---- assembler ----------------------------------------------------------------
class Asm:
    def __init__(self):
        self.mem = bytearray(0x10000)
        self.pc = 0
        self.fix = []          # (at, label, kind, end)
        self.labels = {}
        self.n = 0
    def db(self, *bs):
        for b in bs:
            self.mem[self.pc] = b & 0xFF
            self.pc += 1
    def dw(self, w):
        if isinstance(w, str): self.fix.append((self.pc, w, 'abs', 0)); self.db(0, 0)
        else: self.db(w >> 8, w)
    def label(self, name=None):
        if name is None: name = self.new()
        self.labels[name] = self.pc
        return name
    def new(self):
        self.n += 1
        return 'L%d' % self.n
    def rel8(self, name):
        self.fix.append((self.pc, name, 'rel8', self.pc + 1)); self.db(0)
    def rel16(self, name):
        self.fix.append((self.pc, name, 'rel16', self.pc + 2)); self.db(0, 0)
    def resolve(self):
        for at, name, kind, end in self.fix:
            t = self.labels[name]
            if kind == 'abs':
                self.mem[at] = t >> 8; self.mem[at + 1] = t & 0xFF
            elif kind == 'rel16':
                o = (t - end) & 0xFFFF; self.mem[at] = o >> 8; self.mem[at + 1] = o & 0xFF
            else:
                o = t - end
                if not -128 <= o <= 127: sys.exit("FAIL  gen.py: branch out of reach (%d)" % o)
                self.mem[at] = o & 0xFF

A = Asm()

def jmp(name): A.db(0x7E); A.dw(name)

class Setup:
    """What a chunk needs in place before its instruction. Values may be labels."""
    def __init__(self):
        self.mem = []          # (addr, value, width)
        self.reg = {}          # 'X' 'Y' 'U' 'S' 'A' 'B' 'D' 'DP'
        self.cc = v8()
    def put8(self, a, v): self.mem.append((a, v, 1))
    def put16(self, a, v): self.mem.append((a, v, 2))

def emit_setup(st):
    """S first (the CC trick needs a stack), CC pushed, memory, X Y U, DP, A B
    (or D), CC pulled: nothing after the pull touches a flag."""
    A.db(0x10, 0xCE); A.dw(st.reg.get('S', s_sane()))           # LDS
    A.db(0x86, st.cc, 0x34, 0x02)                                # LDA #cc; PSHS A
    for a, v, w in st.mem:
        if w == 2: A.db(0xCC); A.dw(v); A.db(0xFD); A.dw(a)      # LDD; STD
        else: A.db(0x86, v); A.db(0xB7); A.dw(a)                 # LDA; STA
    if 'X' in st.reg: A.db(0x8E); A.dw(st.reg['X'])
    if 'Y' in st.reg: A.db(0x10, 0x8E); A.dw(st.reg['Y'])
    if 'U' in st.reg: A.db(0xCE); A.dw(st.reg['U'])
    if 'DP' in st.reg: A.db(0x86, st.reg['DP'], 0x1F, 0x8B)      # LDA; TFR A,DP
    if 'D' in st.reg:
        A.db(0xCC); A.dw(st.reg['D'])
    else:
        A.db(0x86, st.reg.get('A', v8()), 0xC6, st.reg.get('B', v8()))
    A.db(0x35, 0x01)                                             # PULS CC

# ---- indexed operands ------------------------------------------------------------
IDX_MODES = ['R', '5', '8', '16', 'A', 'B', 'D', 'R+', 'R++', '-R', '--R', 'PCR8', 'PCR16', 'EXT']
IND_OK = {'R', '8', '16', 'A', 'B', 'D', 'R++', '--R', 'PCR8', 'PCR16', 'EXT'}

def emit_indexed(st, opbytes, ea, write=False, control=False, modes=None, regs=None):
    """Emit setup and an indexed instruction whose effective address is `ea`
    (a number, or a label for control transfers). PCR8 reaches only the code,
    so a read through it takes whatever byte is there and a write or a jump
    through it is not generated."""
    mode = R.choice(modes or IDX_MODES)
    ind = mode == 'EXT' or (mode in IND_OK and R.random() < 0.35)
    if mode == 'PCR8' and not ind and (write or control): mode = 'PCR16'
    if regs is None: regs = ['X', 'Y', 'U'] if control else ['X', 'Y', 'U', 'S']
    reg = R.choice(regs)
    rr = RR[reg] << 5
    ib = 0x10 if ind else 0

    # `need` is the address the indexing itself computes: the EA, or a pointer to it
    planted = None
    if ind and mode == 'PCR8':
        planted = ea                          # pointer bytes in the code, just before the opcode
        need = None
    elif ind:
        need = ram_ea(2)
        st.put16(need, ea)
    else:
        need = ea

    post = []                                 # the operand bytes, known now or at emit time
    if mode in ('PCR8', 'PCR16', 'EXT'):
        pass
    elif reg == 'S':
        # S is a stack, so it is chosen first and the mode decides the address
        s = s_sane()
        st.reg['S'] = s
        if mode in ('16', 'D'):
            if isinstance(need, str): return False
            off = (need - s) & 0xFFFF
            if mode == '16': post = [off >> 8, off & 0xFF]
            else: st.reg['D'] = off
        else:
            if mode == '5': o = R.randrange(-16, 16); post = [o]
            elif mode == '8': o = R.randrange(-128, 128); post = [o & 0xFF]
            elif mode == 'A': st.reg['A'] = v8(); o = sx8(st.reg['A'])
            elif mode == 'B': st.reg['B'] = v8(); o = sx8(st.reg['B'])
            elif mode == '-R': o = -1
            elif mode == '--R': o = -2
            else: o = 0
            at = (s + o) & 0xFFFF
            if ind:
                st.mem = [m for m in st.mem if m[0] != need]
                st.put16(at, ea)
                if at < s: st.cc |= 0x50      # an interrupt would stack over the pointer
            elif isinstance(need, str):
                return False
    else:
        if isinstance(need, str):
            # a label EA: the register is loaded with label arithmetic we cannot
            # express, so indexed control transfers go through a pointer or ,R
            if mode not in ('R', 'R+', 'R++'):
                mode = 'R'
            st.reg[reg] = need
            post = []
        else:
            if mode == 'R' or mode == 'R+' or mode == 'R++': st.reg[reg] = need
            elif mode == '-R': st.reg[reg] = (need + 1) & 0xFFFF
            elif mode == '--R': st.reg[reg] = (need + 2) & 0xFFFF
            elif mode == '5':
                o = R.randrange(-16, 16); post = [o]; st.reg[reg] = (need - o) & 0xFFFF
            elif mode == '8':
                o = R.randrange(256); post = [o]; st.reg[reg] = (need - sx8(o)) & 0xFFFF
            elif mode == '16':
                o = v16(); post = [o >> 8, o & 0xFF]; st.reg[reg] = (need - o) & 0xFFFF
            elif mode in ('A', 'B'):
                o = v8(); st.reg[mode] = o; st.reg[reg] = (need - sx8(o)) & 0xFFFF
            elif mode == 'D':
                o = v16(); st.reg['D'] = o; st.reg[reg] = (need - o) & 0xFFFF
    if mode in ('-R', 'R+', '5'): ind = False; ib = 0
    if isinstance(need, str) and ind: return False
    if mode == 'EXT' and isinstance(need, str): return False

    emit_setup(st)
    if planted is not None:
        A.db(0x20, 0x02); A.dw(planted)       # BRA +2; FDB ea
    ptr_at = A.pc - 2
    A.db(*opbytes)
    end_op = A.pc
    if mode == 'R':     A.db(0x84 | rr | ib)
    elif mode == '5':   A.db(rr | (post[0] & 0x1F))
    elif mode == '8':   A.db(0x88 | rr | ib, post[0])
    elif mode == '16':  A.db(0x89 | rr | ib, *post)
    elif mode == 'A':   A.db(0x86 | rr | ib)
    elif mode == 'B':   A.db(0x85 | rr | ib)
    elif mode == 'D':   A.db(0x8B | rr | ib)
    elif mode == 'R+':  A.db(0x80 | rr)
    elif mode == 'R++': A.db(0x81 | rr | ib)
    elif mode == '-R':  A.db(0x82 | rr)
    elif mode == '--R': A.db(0x83 | rr | ib)
    elif mode == 'PCR8':
        if planted is not None: A.db(0x9C, (ptr_at - (end_op + 2)) & 0xFF)
        else: A.db(0x8C, R.randrange(256))
    elif mode == 'PCR16':
        A.db(0x8D | ib)
        if isinstance(need, str): A.rel16(need)
        else: o = (need - (end_op + 3)) & 0xFFFF; A.db(o >> 8, o & 0xFF)
    elif mode == 'EXT':
        A.db(0x9F); A.dw(need)
    return True

# ---- chunks ---------------------------------------------------------------------
SET1 = [0x80, 0x81, 0x82, 0x84, 0x85, 0x86, 0x88, 0x89, 0x8A, 0x8B]
SET0 = [0x00, 0x03, 0x04, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0C, 0x0D, 0x0F]
A16 = [(0x83,), (0xC3,), (0x8C,), (0xCC,), (0x8E,), (0xCE,), (0x10, 0x83), (0x10, 0x8C), (0x10, 0x8E),
       (0x10, 0xCE), (0x11, 0x83), (0x11, 0x8C)]
ST16 = [(0x9F,), (0xDD,), (0xDF,), (0x10, 0x9F), (0x10, 0xDF)]

def mode_op(opb, delta): return list(opb[:-1]) + [opb[-1] + delta]

def dir_ea(st):
    dp = R.choice([0, 0, R.randrange(1, 0x20)])
    st.reg['DP'] = dp
    n = R.randrange(255)
    return dp, n, (dp << 8) | n

def ch_set1():
    st = Setup()
    op = R.choice(SET1) + R.choice([0, 0x40])
    m = R.choice(['imm', 'dir', 'idx', 'ext'])
    if m == 'imm':
        emit_setup(st); A.db(op, v8())
    elif m == 'dir':
        dp, n, ea = dir_ea(st); st.put8(ea, v8()); emit_setup(st); A.db(op + 0x10, n)
    elif m == 'ext':
        ea = ram_ea(); st.put8(ea, v8()); emit_setup(st); A.db(op + 0x30); A.dw(ea)
    else:
        ea = ram_ea(); st.put8(ea, v8()); emit_indexed(st, [op + 0x20], ea)

def ch_store8():
    st = Setup()
    op = R.choice([0x97, 0xD7])
    m = R.choice(['dir', 'idx', 'ext'])
    if m == 'dir': dp, n, ea = dir_ea(st); emit_setup(st); A.db(op, n)
    elif m == 'ext': emit_setup(st); A.db(op + 0x20); A.dw(ram_ea())
    else: emit_indexed(st, [op + 0x10], ram_ea(), write=True)

def ch_set0():
    st = Setup()
    op = R.choice(SET0)
    m = R.choice(['inhA', 'inhB', 'dir', 'idx', 'ext'])
    if m == 'inhA': emit_setup(st); A.db(0x40 + op)
    elif m == 'inhB': emit_setup(st); A.db(0x50 + op)
    elif m == 'dir': dp, n, ea = dir_ea(st); st.put8(ea, v8()); emit_setup(st); A.db(op, n)
    elif m == 'ext': ea = ram_ea(); st.put8(ea, v8()); emit_setup(st); A.db(op + 0x70); A.dw(ea)
    else: ea = ram_ea(); st.put8(ea, v8()); emit_indexed(st, [op + 0x60], ea, write=True)

def ch_a16():
    st = Setup()
    opb = R.choice(A16)
    lds = opb == (0x10, 0xCE)
    for r in 'XYU': st.reg[r] = v16()
    if opb == (0x11, 0x8C): st.reg['S'] = s_sane()
    val = s_sane() if lds else v16()
    m = R.choice(['imm', 'dir', 'idx', 'ext'])
    if m == 'imm':
        emit_setup(st); A.db(*opb); A.dw(val)
    elif m == 'dir':
        dp, n, ea = dir_ea(st); st.put16(ea, val); emit_setup(st); A.db(*mode_op(opb, 0x10), n)
    elif m == 'ext':
        ea = ram_ea(2); st.put16(ea, val); emit_setup(st); A.db(*mode_op(opb, 0x30)); A.dw(ea)
    else:
        ea = ram_ea(2); st.put16(ea, val)
        for r in 'XYU': st.reg.pop(r, None)
        if lds:
            emit_indexed(st, mode_op(opb, 0x20), ea, regs=['X', 'Y', 'U'],
                         modes=[x for x in IDX_MODES if x != 'PCR8'])
        else:
            emit_indexed(st, mode_op(opb, 0x20), ea)

def ch_st16():
    st = Setup()
    opb = R.choice(ST16)
    for r in 'XYU': st.reg[r] = v16()
    m = R.choice(['dir', 'idx', 'ext'])
    if m == 'dir': dp, n, ea = dir_ea(st); emit_setup(st); A.db(*opb, n)
    elif m == 'ext': emit_setup(st); A.db(*mode_op(opb, 0x20)); A.dw(ram_ea(2))
    else:
        for r in 'XYU': st.reg.pop(r, None)
        emit_indexed(st, mode_op(opb, 0x10), ram_ea(2), write=True)

def ch_lea():
    st = Setup()
    op = R.choice([0x30, 0x31, 0x32, 0x33])
    if op == 0x32:
        emit_indexed(st, [op], s_sane(), regs=['X', 'Y', 'U'], modes=[x for x in IDX_MODES if x != 'PCR8'])
    else:
        emit_indexed(st, [op], v16() if R.random() < 0.5 else ram_ea())

def filler(n):
    for _ in range(n): A.db(R.randrange(256))

def ch_branch():
    st = Setup()
    cond = R.randrange(16)
    long = R.random() < 0.35
    T, N = A.new(), A.new()
    spread = R.randrange(0, 300) if long else R.randrange(0, 60)
    emit_setup(st)
    def br():
        if long and cond == 0 and R.random() < 0.3: A.db(0x16); A.rel16(T)
        elif long: A.db(0x10, 0x20 + cond); A.rel16(T)
        else: A.db(0x20 + cond); A.rel8(T)
    if R.random() < 0.3:                       # backward
        over = A.new()
        jmp(over)                              # JMP keeps CC
        filler(R.randrange(0, 12))
        A.label(T); A.db(0x86, 0x22); jmp(N)
        filler(spread)
        A.label(over); br()
        A.db(0x86, 0x11)
    else:
        br()
        A.db(0x86, 0x11); jmp(N)
        filler(spread)
        A.label(T); A.db(0x86, 0x22)
    A.label(N)

def emit_sub(N):
    k = R.choice(['rts', 'puls', 'leas'])
    if k == 'rts': A.db(0x39)
    elif k == 'puls':
        m = R.randrange(0x40) | (R.randrange(2) << 6)
        A.db(0x34, m, 0x35, m | 0x80)          # PSHS m; PULS m,PC
    else:
        A.db(0x32, 0x62); jmp(N)               # LEAS 2,S; JMP next

def ch_subr():
    st = Setup()
    N, SUB, GO = A.new(), A.new(), A.new()
    kind = R.choice(['bsr', 'lbsr', 'jsr_dir', 'jsr_ext', 'jsr_idx'])
    if kind in ('bsr', 'lbsr', 'jsr_ext'):
        emit_setup(st)
        if kind == 'bsr': A.db(0x8D); A.rel8(SUB)
        elif kind == 'lbsr': A.db(0x17); A.rel16(SUB)
        else: A.db(0xBD); A.dw(SUB)
        jmp(N)
        filler(R.randrange(0, 40) if kind == 'bsr' else R.randrange(0, 300))
        A.label(SUB); emit_sub(N)
    else:
        # the subroutine first, so its address is a number the setup can use
        jmp(GO)
        sub_at = A.pc
        A.label(SUB); emit_sub(N)
        A.label(GO)
        if kind == 'jsr_dir':
            st.reg['DP'] = sub_at >> 8
            emit_setup(st); A.db(0x9D, sub_at & 0xFF)
        else:
            if not emit_indexed(st, [0xAD], sub_at, control=True):
                emit_setup(st); A.db(0xBD); A.dw(SUB)
        jmp(N)
    A.label(N)

def ch_jmp():
    st = Setup()
    N, GO = A.new(), A.new()
    kind = R.choice(['dir', 'ext', 'idx', 'idx'])
    if kind == 'ext':
        emit_setup(st); A.db(0x7E); A.dw(N); filler(R.randrange(0, 8))
    else:
        jmp(GO)
        tgt = A.pc
        jmp(N)
        A.label(GO)
        if kind == 'dir':
            st.reg['DP'] = tgt >> 8; emit_setup(st); A.db(0x0E, tgt & 0xFF)
        elif not emit_indexed(st, [0x6E], tgt, control=True):
            emit_setup(st); jmp(N)
    A.label(N)

def ch_push():
    st = Setup()
    op = R.choice([0x34, 0x36])
    m = 0 if R.random() < 0.08 else R.randrange(256)
    st.reg['X'] = v16(); st.reg['Y'] = v16()
    st.reg['U'] = u_sane() if op == 0x36 else v16()
    emit_setup(st); A.db(op, m)

def ch_pull():
    st = Setup()
    N = A.new()
    op = R.choice([0x35, 0x37])
    onU = op == 0x37
    m = R.randrange(256)
    sp = u_sane() if onU else s_sane()
    st.reg['U' if onU else 'S'] = sp
    a = sp
    for bit in range(8):
        if not m & (1 << bit): continue
        if bit < 4: st.put8(a, v8()); a += 1
        elif bit < 6: st.put16(a, v16()); a += 2
        elif bit == 6: st.put16(a, s_sane() if onU else v16()); a += 2
        else: st.put16(a, N); a += 2
    emit_setup(st); A.db(op, m)
    A.label(N)

def ch_rti():
    st = Setup()
    N = A.new()
    sp = s_sane()
    st.reg['S'] = sp
    ccv = v8()
    a = sp
    st.put8(a, ccv); a += 1
    if ccv & 0x80:
        for _ in range(3): st.put8(a, v8()); a += 1
        st.put16(a, v16()); st.put16(a + 2, v16()); st.put16(a + 4, u_sane()); a += 6
    st.put16(a, N)
    emit_setup(st); A.db(0x3B)
    A.label(N)

def ch_tfr():
    st = Setup()
    N = A.new()
    exg = R.random() < 0.5
    codes = [0, 1, 2, 3, 4, 5, 8, 9, 10, 11]
    src = R.choice(codes + [6, 7, 12, 15]) if R.random() < 0.1 else R.choice(codes)
    dst = R.choice(codes + [6, 13]) if R.random() < 0.1 else R.choice(codes)
    pairs = [(dst, src)] + ([(src, dst)] if exg else [])
    sane, pcr = set(), None
    for to, frm in pairs:
        if to == frm: continue
        if to == 4:
            if frm not in (0, 1, 2, 3): return ch_tfr()
            sane.add(frm)
        if to == 5:
            if frm not in (0, 1, 2, 3): return ch_tfr()
            pcr = frm
    if pcr is not None and pcr in sane: return ch_tfr()
    names = {1: 'X', 2: 'Y', 3: 'U'}
    for k, r in names.items():
        st.reg[r] = N if pcr == k else (s_sane() if k in sane else v16())
    if pcr == 0: st.reg['D'] = N
    elif 0 in sane: st.reg['D'] = s_sane()
    emit_setup(st)
    A.db(0x1E if exg else 0x1F, (src << 4) | dst)
    if pcr is not None: filler(R.randrange(0, 6))
    A.label(N)

def ch_inh():
    st = Setup()
    op = R.choice([0x19, 0x19, 0x19, 0x3D, 0x1D, 0x3A, 0x12, 0x1A, 0x1C])
    if op == 0x19: st.reg['A'] = R.randrange(256)
    emit_setup(st)
    if op in (0x1A, 0x1C): A.db(op, v8())
    else: A.db(op)

def ch_swi():
    st = Setup(); emit_setup(st); A.db(*R.choice([(0x3F,), (0x10, 0x3F), (0x11, 0x3F)]))

def ch_cwai():
    st = Setup(); emit_setup(st); A.db(0x3C, v8() & R.choice([0xEF, 0xBF, 0xAF]))

def ch_sync():
    st = Setup(); emit_setup(st); A.db(0x13)

def ch_undoc():
    st = Setup()
    k = R.randrange(6)
    if k == 0:
        op = R.choice([0x01, 0x02, 0x05, 0x0B, 0x41, 0x42, 0x45, 0x4B, 0x51, 0x52, 0x55, 0x5B, 0x4E, 0x5E,
                       0x61, 0x62, 0x65, 0x6B, 0x71, 0x72, 0x75, 0x7B])
        hi = op >> 4
        if hi in (4, 5): emit_setup(st); A.db(op)
        elif hi == 0: dp, n, ea = dir_ea(st); st.put8(ea, v8()); emit_setup(st); A.db(op, n)
        elif hi == 7: ea = ram_ea(); st.put8(ea, v8()); emit_setup(st); A.db(op); A.dw(ea)
        else: ea = ram_ea(); st.put8(ea, v8()); emit_indexed(st, [op], ea, write=True)
    elif k == 1:                               # invalid bytes: 2 bytes, 2 cycles
        emit_setup(st); A.db(R.choice([0x14, 0x15, 0x18, 0x1B, 0x38, 0x3E, 0x87, 0x8F, 0xC7, 0xCD, 0xCF]), 0x12)
    elif k == 2:                               # index modes $x A / $x E: 3-cycle no-ops
        emit_setup(st); A.db(0xA6, R.choice([0x8A, 0x8E, 0xAA, 0xCE, 0xFA, 0xBE]), 0x12, 0x12)
    elif k == 3:                               # prefixes on page-1 instructions
        c = R.randrange(7)
        emit_setup(st)
        if c == 0: A.db(0x10, 0x86, v8())
        elif c == 1: A.db(0x11, 0x3A)
        elif c == 2: A.db(0x10, 0x10, 0x4C)
        elif c == 3: A.db(0x11, 0x10, 0x8B, v8())
        elif c == 4: A.db(0x10, 0xCC, 0x12, 0x12)
        elif c == 5: A.db(0x11, 0x21, 0x00)
        else: A.db(0x10, 0x12)
    elif k == 4:                               # [,R+] [,-R], and $87/$97: mode 7 with bit 7 set
        reg = R.choice(['X', 'Y', 'U'])
        pb = R.choice([0x90, 0x92, 0x87, 0x97])
        p = ram_ea(2) + 0x10
        st.put16(p, ram_ea())
        st.reg[reg] = {0x90: p, 0x92: p + 1, 0x87: p - 7, 0x97: p + 9}[pb]
        emit_setup(st); A.db(0xA6, pb | (RR[reg] << 5))
    else:                                      # the 16-bit decode under the wrong prefix
        c = R.randrange(3)
        emit_setup(st)
        if c == 0: A.db(0x10, 0xFD); A.dw(ram_ea(2))
        elif c == 1: A.db(0x11, 0xBF); A.dw(ram_ea(2))
        else: A.db(0x10, 0x30, 0x84)

KINDS = [(ch_set1, 12), (ch_store8, 4), (ch_set0, 10), (ch_a16, 10), (ch_st16, 4), (ch_lea, 4),
         (ch_branch, 8), (ch_subr, 5), (ch_jmp, 4), (ch_push, 4), (ch_pull, 5), (ch_rti, 2),
         (ch_tfr, 6), (ch_inh, 6), (ch_swi, 1), (ch_cwai, 1), (ch_sync, 1)]

def main():
    global R
    seed = int(sys.argv[1]); out = sys.argv[2]
    undoc = '--undoc' in sys.argv
    maxcyc = int(sys.argv[sys.argv.index('--maxcyc') + 1]) if '--maxcyc' in sys.argv else 2000000
    R = random.Random(seed)
    pool = [k for k, w in KINDS + ([(ch_undoc, 8)] if undoc else []) for _ in range(w)]

    # handlers: each counts itself in RAM and returns; FIRQ saves what it uses
    A.pc = 0xF000
    A.label('irq');  A.db(0x7C, 0x4F, 0x10, 0x3B)
    A.label('firq'); A.db(0x34, 0x02, 0xB6, 0x4F, 0x11, 0x4C, 0xB7, 0x4F, 0x11, 0x35, 0x02, 0x3B)
    A.label('nmi');  A.db(0x7C, 0x4F, 0x12, 0x3B)
    A.label('swi');  A.db(0x7C, 0x4F, 0x13, 0x3B)
    A.label('swi2'); A.db(0x7C, 0x4F, 0x14, 0x3B)
    A.label('swi3'); A.db(0x7C, 0x4F, 0x15, 0x3B)
    A.pc = 0xFFF0
    for v in ('swi3', 'swi3', 'swi2', 'firq', 'irq', 'swi', 'nmi', 'start'):
        A.dw(v)

    A.pc = 0x5000
    A.label('start')
    while A.pc < 0xEC00:
        R.choice(pool)()
    jmp('start')
    if A.pc > 0xF000: sys.exit("FAIL  gen.py: code ran into the handlers")
    A.resolve()

    base = os.path.join(out, 'prog_%d' % seed)
    open(base + '.bin', 'wb').write(A.mem)
    with open(base + '.hex', 'w') as f:
        f.write(''.join('%02x\n' % b for b in A.mem))
    # pulses on each line; a line never changes twice within 40 cycles
    ev = []
    for line, gap, width in ((0, 1400, 500), (1, 1900, 300), (2, 40000, 80)):
        t = R.randrange(300, 3000)
        while t < maxcyc + 300000:
            w = R.randrange(40, width)
            ev += [(t, line, 1), (t + w, line, 0)]
            t += w + R.randrange(40, 2 * gap)
    ev.sort()
    with open(base + '.sched', 'w') as f:
        f.write(''.join('%d %d %d\n' % e for e in ev))

if __name__ == '__main__':
    main()
