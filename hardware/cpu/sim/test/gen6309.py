#!/usr/bin/env python3
"""gen6309.py - a generated exerciser for the 6309 differential test.

    gen6309.py SEED OUT.asm [--chunks N]

⭐ ONE CHUNK PER INSTRUCTION UNDER TEST, and every chunk loads everything its
instruction depends on first: every register (A B E F X Y U V DP CC, W and Q
through them), the mode (LDMD, emulation or native, and the FIRQ-mode bit),
and the memory its operand names.  So the first line where hd6309.c and the
oracle disagree names the instruction that caused it - the design of gen.py,
which this follows for a different CPU.

⛔ WHAT IT MUST NOT DO is let a random operand run the program off into data.
So memory operands point into DATA ($4000-$7FFF), indexed offsets are bounded
to stay there, and control flow is built rather than drawn: every branch,
jump, call and return has a target the chunk arranges, and the traps and
software interrupts vector to a handler that clears MD and returns.

Every encoding the 6309 defines is drawn with equal weight, which is what
makes the coverage report mean something.
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CODE = 0x8000
DATA_LO, DATA_HI = 0x4000, 0x7FFF
STACK = 0x3F00          # S, and U's stack below it
USTK = 0x3E00
DP = 0x40               # the direct page lies in DATA


def load_tab():
    ops = []
    for line in open(os.path.join(HERE, "hd6309.tab")):
        if line.startswith("#") or not line.strip():
            continue
        f = line.split()
        ops.append((int(f[0]), int(f[1], 16), f[2], f[3]))
    return ops


# Encodings drawn from the table but built by hand below, or not drawn at all.
NEVER = {
    (2, 0x3D),                          # LDMD: every chunk sets the mode itself
}

# ⭐ THE INTERRUPT PORT (run6309.c and oracle/xroar_run.c): a write raises or
# lowers a line, so the program decides where an interrupt arrives.
IRQ_ON, IRQ_OFF, FIRQ_ON, FIRQ_OFF, NMI_ON, NMI_OFF = range(0xFFD0, 0xFFD6)

# ⭐ The postbytes, by kind, that keep an indexed address inside DATA when the
# base register holds DATA_MID.  Those that add an accumulator are only drawn
# with that accumulator made small first.
PB_PLAIN = [0x84, 0x88, 0x89, 0x80, 0x81, 0x82, 0x83, 0x94, 0x98, 0x99, 0x91, 0x93, 0x9F,
            0x8F, 0xAF, 0xCF, 0xEF, 0x90, 0xB0, 0xD0, 0xF0]
PB_ACC = [(0x86, "a"), (0x85, "b"), (0x87, "e"), (0x8A, "f"), (0x8B, "d"), (0x8E, "w"),
          (0x96, "a"), (0x95, "b"), (0x97, "e"), (0x9A, "f"), (0x9B, "d"), (0x9E, "w")]
DATA_MID = 0x5800

# ⭐ Every postbyte above $7F the 6309 decodes, less the RR variants of the
# PC-relative forms and of [n16], which ignore those bits and which lwasm
# emits one way only - cov6309.py leaves the same ones out of its count.
PB_ALL = [pb for pb in range(0x80, 0x100)
          if pb not in (0x92, 0xB2, 0xD2, 0xF2, 0xBF, 0xDF, 0xFF)
          and not ((pb & 0x0E) == 0x0C and pb & 0x60)]


class Gen(object):
    def __init__(self, seed):
        self.r = random.Random(seed)
        self.out = []
        self.lab = 0
        self.ptrs = []          # pointer cells for indirect modes, filled in DATA

    def w(self, s):
        self.out.append("        " + s)

    def label(self):
        self.lab += 1
        return "L%d" % self.lab

    def b(self):
        return self.r.randrange(256)

    def wd(self):
        return self.r.randrange(65536)

    def data_addr(self, width=1):
        return self.r.randrange(DATA_LO + 0x100, DATA_HI - 0x100)

    # -- a chunk's preamble: the mode and every register -------------------
    def setup(self, keep=()):
        r = self.r
        self.w("ldmd #$%02X" % r.choice((0, 1, 2, 3)))
        self.w("lds #$%04X" % STACK)
        self.w("ldu #$%04X" % USTK)
        self.w("ldq #$%08X" % r.randrange(1 << 32))
        self.w("ldx #$%04X" % DATA_MID)
        self.w("ldy #$%04X" % self.ybase)
        self.w("pshs d")
        self.w("ldd #$%04X" % r.randrange(65536))
        self.w("tfr d,v")
        self.w("lda #$%02X" % DP)
        self.w("tfr a,dp")
        self.w("puls d")
        # CC: I and F stay set - no interrupts in this pass - and E random
        self.w("andcc #$%02X" % (0x50 | r.randrange(256)))
        self.w("orcc #$%02X" % (0x50 | r.randrange(256) & 0xAF))

    def indexed(self):
        """An indexed operand, drawn UNIFORMLY over the defined postbytes, with
        every base register's value known.  Returns (operand, loads, pointer):
        `loads` follow the preamble; `pointer` - (cell, target) - is planted
        before it, so an indirect form reads a pointer this generator chose.
        ⭐ PC-relative forms address a slot the chunk puts in its own code
        stream (`bra` over it), so an 8-bit offset reaches it and a write lands
        in the slot and nowhere else."""
        r = self.r
        tgt = self.data_addr()
        pb = r.choice(PB_ALL) if r.random() > 0.1 else r.randrange(0x80) & 0x7F
        if pb < 0x80:                                     # n5,R
            reg = "xyus"[(pb >> 5) & 3]
            o = pb & 0x1F
            return "%d,%s" % (o - 32 if o & 0x10 else o, reg), [], None
        reg = "xyus"[(pb >> 5) & 3]
        base = {"x": DATA_MID, "y": self.ybase, "u": USTK, "s": STACK}[reg]
        low, ind = pb & 0x0F, (pb >> 4) & 1
        loads, cell = [], None
        wv = DATA_MID + r.randrange(-0x300, 0x300)
        n8, n16 = r.randrange(-100, 100), r.randrange(-2000, 2000)
        acc = {0x5: "b", 0x6: "a", 0x7: "e", 0xA: "f", 0xB: "d", 0xE: "w"}.get(low)
        if acc:
            v = r.randrange(-100, 100) if acc in "abef" else r.randrange(-2000, 2000)
            if acc == "w":
                wv = v & 0xFFFF
            loads.append(("ld%s #$%04X" % (acc, v & 0xFFFF)) if acc in "dw" else ("ld%s #$%02X" % (acc, v & 0xFF)))
            txt, ea = "%s,%s" % (acc, reg), base + v
        elif low == 0xF or (low == 0x0 and ind):          # the W modes, and [n16]
            if pb == 0x9F:
                cell = self.data_addr()
                return "[>$%04X]" % cell, [], (cell, tgt)
            loads.append("ldw #$%04X" % wv)
            k = (pb >> 5) & 3
            txt, ea = [(",w", wv), (">%d,w" % n16, wv + n16), (",w++", wv), (",--w", wv - 2)][k]
        elif low in (0xC, 0xD):                           # PC-relative: a slot in the code
            slot = self.label(); over = self.label()
            self.w("bra %s" % over)
            self.out.append(slot)
            self.w("fdb $%04X,$%04X" % (tgt, self.data_addr()))
            self.out.append(over)
            txt = ("<%s,pcr" if low == 0xC else ">%s,pcr") % slot
            return ("[%s]" % txt) if ind else txt, loads, None
        else:
            txt, ea = {0x0: (",%s+" % reg, base), 0x1: (",%s++" % reg, base),
                       0x2: (",-%s" % reg, base - 1), 0x3: (",--%s" % reg, base - 2),
                       0x4: (",%s" % reg, base), 0x8: ("<%d,%s" % (n8, reg), base + n8),
                       0x9: (">%d,%s" % (n16, reg), base + n16)}[low]
        if ind:
            return "[%s]" % txt, loads, (ea & 0xFFFF, tgt)
        return txt, loads, None

    def illegal(self):
        """An encoding the 6309 does NOT define - an opcode on any page, or an
        undefined indexed postbyte - which takes the trap at $FFF0.  NOPs
        follow, because where the stacked PC points is part of what is
        compared and execution resumes there."""
        r = self.r
        # ⚠ NOT the seven undefined POSTBYTES: the Burke & Burke addendum and
        # hoglet67 say they trap (hd6309.c does), XRoar decodes them as a
        # neighbour, and silicon has not been asked - hoglet67's own entry is
        # "TODO: validate actual".  An opinion cannot be a gate.
        if True:
            page = r.choice((0, 1, 2))
            # ⚠ never a prefix after a prefix: hd6309.c traps $10 $10 after two
            # bytes (hoglet67 lists $1010 as a two-byte illegal), XRoar chains
            # the prefixes and traps a byte later, and silicon is not recorded
            undef = [o for o in range(256) if (page, o) not in DEFINED and o not in (0x10, 0x11)]
            op = r.choice(undef)
            self.w("fcb %s$%02X" % ({0: "", 1: "$10,", 2: "$11,"}[page], op))
        for _ in range(4):
            self.w("nop")

    def interrupt(self, kind):
        """An interrupt the program places: the line goes up with the mask set,
        and then ANDCC, CWAI or SYNC decides - so both cores meet it at the same
        instruction boundary.  Each handler lowers its own line and returns."""
        r = self.r
        self.w("orcc #$50")
        if kind == "nmi":
            self.w("sta >$%04X" % NMI_ON)
            self.w("nop")
            return
        firq = kind == "firq" or (kind in ("cwai", "sync") and r.random() < 0.5)
        self.w("sta >$%04X" % (FIRQ_ON if firq else IRQ_ON))
        if kind == "sync":
            # masked: SYNC ends on the line and the interrupt is NOT taken
            self.w("sync")
            self.w("sta >$%04X" % (FIRQ_OFF if firq else IRQ_OFF))
            return
        if kind == "cwai":
            self.w("cwai #$%02X" % (0xBF if firq else 0xEF))
            return
        self.w("nop")
        self.w("andcc #$%02X" % (0xBF if firq else 0xEF))
        self.w("nop")

    # -- one instruction ----------------------------------------------------
    def chunk(self, page, op, mnem, mode):
        """Build the body first, then emit: the pointer plants, the preamble,
        the body - because an indirect operand's pointer is only known once the
        operand is, and must be stored before the preamble loads D."""
        self.ybase = DATA_MID + self.r.randrange(-0x400, 0x400)
        self.pre = []
        outer, self.out = self.out, []
        self.body(page, op, mnem, mode)
        body, self.out = self.out, outer
        self.w("* %s %s" % (mnem, mode))
        for l in self.pre:
            self.w(l)
        self.setup()
        self.out.extend(body)

    def body(self, page, op, mnem, mode):
        r = self.r
        m = mnem.split("/")[0].lower()
        # ⚠ THE STATES WHERE THE ORACLE IS KNOWN TO BE WRONG ARE NOT MADE: DAA's
        # 6309-only correction (C set, A in $80..$99) and LDQ with V set - the
        # silicon behaviour of each is tested in silicon6309.c instead, because
        # a differential cannot carry on past a state the two disagree about.
        if m == "daa":
            self.w("andcc #$FE")
        if m == "ldq":
            self.w("andcc #$FD")
        if m in ("sync", "cwai"):
            self.interrupt(m)
            return
        if r.random() < 0.04:
            self.illegal()
        if r.random() < 0.1:
            self.interrupt(r.choice(("irq", "firq", "nmi", "cwai", "sync")))
        if mode == "INH":
            if m in ("rts",):
                t = self.label(); self.w("ldd #%s" % t); self.w("pshs d"); self.w("rts"); self.out.append(t)
                return
            if m == "rti":
                # a fast frame: CC with E clear, then PC
                t = self.label(); self.w("ldd #%s" % t); self.w("pshs d"); self.w("tfr cc,a")
                self.w("anda #$7F"); self.w("pshs a"); self.w("rti"); self.out.append(t)
                return
            if m in ("swi", "swi2", "swi3"):
                self.w(m)
                return
            self.w(m)
            return
        if mode == "REL":
            t = self.label()
            if m in ("bsr", "lbsr"):
                s_ = self.label(); self.w("%s %s" % (m, s_)); self.w("bra %s" % t)
                self.out.append(s_); self.w("rts"); self.out.append(t)
                return
            self.w("%s %s" % (m, t)); self.w("nop"); self.out.append(t)
            return
        if mode == "RTOR":
            if m.startswith("tfm"):
                self.w("ldw #%d" % r.randrange(0, 12))
                regs = "xyu"
                a, b_ = r.choice(regs), r.choice(regs)
                while b_ == a:
                    b_ = r.choice(regs)
                self.w("ld%s #$%04X" % (a, DATA_MID)); self.w("ld%s #$%04X" % (b_, DATA_MID + 0x100))
                form = {0x38: "%s+,%s+", 0x39: "%s-,%s-", 0x3A: "%s+,%s", 0x3B: "%s,%s+"}[op]
                self.w("tfm " + form % (a, b_))
                return
            # never PC or S as a destination (control flow and the stack)
            ok = "d x y u w v a b cc dp e f 0".split()
            # ⚠ never CC as a destination: TFR/EXG would clear I and F, and for
            # ADDR..CMPR the book says "r2=CC should not be used" - undefined
            dst = r.choice([x for x in ok if x != "cc"])
            src = r.choice(ok + ["s", "pc"] if m == "tfr" else ok)
            if m == "exg" and dst == "0":
                dst = "x"
            self.w("%s %s,%s" % (m, src, dst))
            return
        if mode == "BITOP":
            reg = r.choice(("a", "b", "cc"))
            self.w("%s %s,%d,%d,<$%02X" % (m, reg, r.randrange(8), r.randrange(8), r.randrange(256)))
            return
        if mode == "IMM":
            if m in ("pshs", "pshu", "puls", "pulu"):
                mask = r.randrange(256) & 0x3F      # never PC, never the other stack
                if m.startswith("pul"):
                    # something to pull
                    self.w("%s #$FF" % ("pshs" if m == "puls" else "pshu") + "")
                    self.out[-1] = "        %s a,b,dp,x,y,cc" % ("pshs" if m == "puls" else "pshu")
                regs = [n for bit, n in ((1, "cc"), (2, "a"), (4, "b"), (8, "dp"), (16, "x"), (32, "y")) if mask & bit]
                if not regs:
                    regs = ["a"]
                self.w("%s %s" % (m, ",".join(regs)))
                return
            if m in ("andcc", "orcc"):
                self.w("%s #$%02X" % (m, (r.randrange(256) | 0x50) if m == "andcc" else (r.randrange(256) & 0xAF)))
                return
            if m in ("divd", "divq"):
                v = 0 if r.random() < 0.08 else r.randrange(1, 256 if m == "divd" else 65536)
                self.w("%s #$%X" % (m, v))
                return
            wide = mnem.endswith(("D", "X", "Y", "U", "S", "W")) or m in ("ldq", "muld", "divq")
            if m == "ldq":
                self.w("ldq #$%08X" % r.randrange(1 << 32))
            elif m in ("bitmd",):
                self.w("bitmd #$%02X" % r.randrange(256))
            elif m in ("lds",):
                self.w("lds #$%04X" % (STACK - r.randrange(0x40)))
            elif wide:
                self.w("%s #$%04X" % (m, r.randrange(65536)))
            else:
                self.w("%s #$%02X" % (m, r.randrange(256)))
            return
        # memory modes
        if m in ("jmp", "jsr"):
            t = self.label()
            if mode == "IDX":
                self.w("leax %s,pcr" % t)
                self.w("%s ,x" % m)
            elif mode == "DIR":
                # ⚠ the direct page has to be the code's for a direct jump
                self.w("lda #%s/256" % t)
                self.w("tfr a,dp")
                self.w("fcb $%02X,%s&255" % (0x0E if m == "jmp" else 0x9D, t))
            else:
                self.w("%s %s" % (m, t))
            self.out.append(t)
            if m == "jsr":
                self.w("leas 2,s")
            return
        if m == "leas":
            self.w("leas %d,s" % r.randrange(-40, 40))
            return
        imm = ""
        if m in ("oim", "aim", "eim", "tim"):
            imm = "#$%02X," % r.randrange(256)
        loads = []
        if mode == "DIR":
            opnd = "<$%02X" % r.randrange(256)
        elif mode == "EXT":
            opnd = ">$%04X" % self.data_addr()
        else:
            opnd, loads, ptr = self.indexed()
            if ptr:
                # the pointer, planted before the preamble loads every register
                self.pre.append("ldd #$%04X" % ptr[1])
                self.pre.append("std >$%04X" % ptr[0])
        for l in loads:
            self.w(l)
        self.w("%s %s%s" % (m, imm, opnd))
        if m == "muld":
            # ⚠ XRoar sets N, not Z, when MULD's D is 0 (a slip in its source;
            # silicon and the book agree on N and Z of Q).  TSTA rewrites N, Z
            # and V at once, so the one differing boundary cannot propagate;
            # cmp6309.py allows exactly that boundary and nothing after it.
            self.w("tsta")


DEFINED = set((p, o) for p, o, _, _ in load_tab())


def main():
    seed = int(sys.argv[1])
    out = sys.argv[2]
    n = 600
    if "--chunks" in sys.argv:
        n = int(sys.argv[sys.argv.index("--chunks") + 1])
    g = Gen(seed)
    ops = [o for o in load_tab() if (o[0], o[1]) not in NEVER]
    g.out.append("        org $%04X" % CODE)
    g.out.append("start")
    for k in range(n):
        page, op, mnem, mode = g.r.choice(ops)
        g.chunk(page, op, mnem, mode)
    g.out.append("        sta $FFE0")
    g.out.append("        bra *")
    # the handler every trap and software interrupt uses: clear MD's flags and return
    g.out.append("handler")
    g.w("bitmd #$C0")
    g.w("rti")
    for name, off in (("irqh", IRQ_OFF), ("firqh", FIRQ_OFF), ("nmih", NMI_OFF)):
        g.out.append(name)
        g.w("sta >$%04X" % off)
        g.w("rti")
    # DATA: random, and the direct page within it
    g.out.append("        org $%04X" % DATA_LO)
    for k in range(0, DATA_HI + 1 - DATA_LO, 16):
        g.w("fcb " + ",".join("$%02X" % g.r.randrange(256) for _ in range(16)))
    g.out.append("        org $FFF0")
    # $FFF0 trap, SWI3, SWI2, FIRQ, IRQ, SWI, NMI, reset
    g.w("fdb handler,handler,handler,firqh,irqh,handler,nmih,start")
    open(out, "w").write("\n".join(g.out) + "\n")


if __name__ == "__main__":
    main()
