#!/usr/bin/env python3
"""Measure mc6809e's E cycles per instruction from a cpu_tb trace, against the datasheet.

    cycles.py prog.bin v.trace [more.bin more.trace ...]

Replays the trace's writes over the image so every opcode and postbyte is read
as the core saw it, takes the cycles between consecutive boundaries, and
groups them by instruction form (opcode, indexed postbyte form, branch taken,
bytes pushed or pulled, RTI's E). Prints every form whose Verilog count differs
from the MC6809E datasheet table below, and how many forms agree. Undocumented
opcodes, CWAI and SYNC (whose length is the wait) are not tabled.

Exit 1 if a form differs that is not in KNOWN - the differences cpu6809.c's
header lists and matches - or an interrupt entry differs from the datasheet.
"""
import sys
from collections import defaultdict

# datasheet extra cycles for an indexed postbyte form (pb & $9F, or 'n5')
IDX = {0x84: 0, 'n5': 1, 0x88: 1, 0x89: 4, 0x86: 1, 0x85: 1, 0x8B: 4, 0x80: 2, 0x81: 3, 0x82: 2, 0x83: 3,
       0x8C: 1, 0x8D: 5, 0x94: 3, 0x98: 4, 0x99: 7, 0x96: 4, 0x95: 4, 0x9B: 7, 0x91: 6, 0x93: 6, 0x9C: 4,
       0x9D: 8, 0x9F: 5}

INVALID1 = {0x01, 0x02, 0x05, 0x0B, 0x14, 0x15, 0x18, 0x1B, 0x38, 0x3E, 0x41, 0x42, 0x45, 0x4B, 0x4E, 0x51,
            0x52, 0x55, 0x5B, 0x5E, 0x61, 0x62, 0x65, 0x6B, 0x71, 0x72, 0x75, 0x7B, 0x87, 0x8F, 0xC7, 0xCD, 0xCF}
P2 = {0x3F, 0x83, 0x8C, 0x8E, 0x93, 0x9C, 0x9E, 0x9F, 0xA3, 0xAC, 0xAE, 0xAF, 0xB3, 0xBC, 0xBE, 0xBF, 0xCE, 0xDE,
      0xDF, 0xEE, 0xEF, 0xFE, 0xFF} | set(range(0x21, 0x30))
P3 = {0x3F, 0x83, 0x8C, 0x93, 0x9C, 0xA3, 0xAC, 0xB3, 0xBC}

# mc6809i.v's own lengths where the datasheet says otherwise (cpu6809.c's header)
KNOWN = {'3F': 20, '103F': 21, '113F': 21, '34 #0 bytes': 6, '36 #0 bytes': 6}

def pushed(m): return sum(2 if (m >> b) & 1 and b >= 4 else ((m >> b) & 1) for b in range(8))

def datasheet(pg, op, mem, pc, s, taken):
    """(form, cycles) for a documented instruction, or None."""
    hi, lo = op >> 4, op & 15
    if pg == 0 and (op in INVALID1 or op in (0x10, 0x11)): return None
    if pg == 1 and op not in P2: return None
    if pg == 2 and op not in P3: return None
    p = 0 if pg == 0 else 1
    name = ('%02X' % op) if pg == 0 else ('%s%02X' % ('10' if pg == 1 else '11', op))
    at = pc + 1 + p                       # first operand byte
    if op in (0x3C, 0x13): return None    # CWAI, SYNC
    if hi == 2 and pg == 0: return (name + (' taken' if taken else ' not'), 3)
    if hi == 2: return (name + (' taken' if taken else ' not'), 6 if taken else 5)
    fixed = {0x12: 2, 0x19: 2, 0x1D: 2, 0x3A: 3, 0x39: 5, 0x3D: 11, 0x1A: 3, 0x1C: 3, 0x1E: 8, 0x1F: 6,
             0x16: 5, 0x17: 9, 0x8D: 7}
    if op == 0x3F: return (name, 19 if pg == 0 else 20)
    if op in fixed and pg == 0: return (name, fixed[op])
    if hi in (4, 5): return (name, 2)
    if op == 0x3B:
        e = mem[s] & 0x80
        return (name + (' E' if e else ' !E'), 15 if e else 6)
    if op in (0x34, 0x35, 0x36, 0x37):
        m = mem[at]
        return ('%s #%d bytes' % (name, pushed(m)), 5 + pushed(m))
    # addressing mode
    if hi in (0x8, 0xC) and op != 0x8D: mode = 'imm'
    elif hi in (0x0, 0x9, 0xD): mode = 'dir'
    elif hi in (0x7, 0xB, 0xF): mode = 'ext'
    else: mode = 'idx'
    # operation class
    if hi in (0, 6, 7):
        cls = 'jmp' if lo == 0xE else 'mod'
    elif op in (0x30, 0x31, 0x32, 0x33):
        cls = 'lea'
    elif lo == 0xD and hi in (9, 0xA, 0xB):
        cls = 'jsr'
    elif lo in (0x3, 0xC) and not (hi >= 0xC and lo == 0xC):
        cls = 'a16'                       # SUBD ADDD CMPX CMPD CMPY CMPU CMPS
    elif lo == 0xC or lo == 0xE:
        cls = 'ld16'                      # LDD LDX LDU LDY LDS
    elif lo == 0xF or (lo == 0xD and hi >= 0xD):
        cls = 'st16'
    elif lo == 0x7:
        cls = 'st8'
    else:
        cls = 'rd8'
    if mode == 'imm':
        n = {'rd8': 2, 'a16': 4, 'ld16': 3}[cls]
        return (name + ' imm', n + p)
    base = {'mod': 6, 'jmp': 3, 'rd8': 4, 'st8': 4, 'a16': 6, 'ld16': 5, 'st16': 5, 'jsr': 7, 'lea': 4}[cls]
    if mode == 'dir': return (name + ' dir', base + p)
    if mode == 'ext': return (name + ' ext', base + 1 + p)
    pb = mem[at]
    form = 'n5' if not pb & 0x80 else pb & 0x9F
    if form not in IDX: return None
    return ('%s idx %s' % (name, form if form == 'n5' else '%02X' % form), base + IDX[form] + p)

def main():
    obs = defaultdict(lambda: defaultdict(int))
    ds = {}
    ints = defaultdict(lambda: defaultdict(int))
    args = sys.argv[1:]
    total = 0
    for k in range(0, len(args), 2):
        mem = bytearray(open(args[k], 'rb').read())
        vec = {(mem[0xFFF8] << 8) | mem[0xFFF9]: 'IRQ', (mem[0xFFF6] << 8) | mem[0xFFF7]: 'FIRQ',
               (mem[0xFFFC] << 8) | mem[0xFFFD]: 'NMI'}
        prev = None
        pending = []
        for line in open(args[k + 1]):
            f = line.split()
            if f[1] == 'W':
                pending.append((int(f[2], 16), int(f[3], 16)))
                continue
            cyc, pc, s = int(f[0]), int(f[1], 16), int(f[7], 16)
            if prev is not None:
                pcyc, ppc, pmem_s, pops = prev
                dt = cyc - pcyc
                op = pops[0]; pg = 0; o = 1
                if op in (0x10, 0x11): pg = 1 if op == 0x10 else 2; op = pops[1]; o = 2
                # an entry stacks (RTI into a handler that was itself interrupted does not)
                if pc in vec and op != 0x3C and len(pending) >= 3:
                    ints[vec[pc]][dt] += 1
                else:
                    # branch taken: the next PC is not the fall-through
                    length = 2 if pg == 0 and (op >> 4) == 2 else 4 if pg == 1 else 3
                    taken = pc != (ppc + length) & 0xFFFF
                    r = datasheet(pg, op, pmem, ppc, pmem_s, taken)
                    if r:
                        obs[r[0]][dt] += 1; ds[r[0]] = r[1]; total += 1
            # memory as the instruction at this boundary will see it
            for a, v in pending: mem[a] = v
            pending = []
            pmem = mem
            prev = (cyc, pc, s, bytes(mem[pc:pc + 3]) if pc + 3 <= 0x10000 else bytes(mem[pc:]) + b'\0\0\0')
    agree = [k for k in obs if set(obs[k]) == {ds[k]}]
    differ = sorted(k for k in obs if set(obs[k]) != {ds[k]})
    print("cycles.py: %d documented instructions measured, %d forms; %d agree with the datasheet, %d differ"
          % (total, len(obs), len(agree), len(differ)))
    for k in differ:
        print("  %-24s datasheet %2d  mc6809e %s" % (k, ds[k], ', '.join('%d (x%d)' % (c, n) for c, n in sorted(obs[k].items()))))
    want = {'IRQ': 19, 'FIRQ': 10, 'NMI': 19}
    for t in ('IRQ', 'FIRQ', 'NMI'):
        print("  %-24s datasheet %2d  mc6809e %s" % (t + ' entry', want[t], ', '.join('%d (x%d)' % (c, n) for c, n in sorted(ints[t].items()))))
    bad = [k for k in differ if set(obs[k]) != {KNOWN.get(k)}]
    bad += [t for t in ints if set(ints[t]) != {want[t]}]
    if bad:
        print("FAIL  cycles.py: lengths neither the datasheet's nor the known exceptions: " + ', '.join(bad))
        sys.exit(1)
    print("ok    cycles.py: every other form measured is the datasheet's length")

if __name__ == '__main__':
    main()
