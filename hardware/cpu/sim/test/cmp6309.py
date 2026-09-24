#!/usr/bin/env python3
"""cmp6309.py - hd6309.c's trace against the oracle's; the first difference.

    cmp6309.py ours.trace oracle.trace prog.asm [--no-cycles]

Boundaries are compared whole - the cycle, PC and every register.  Writes are
compared by address and value in order, NOT by cycle: where inside an
instruction a write falls is a bus-timing model (XRoar's dummy cycles, ours'
simple sequence), and what an instruction COSTS is what the boundary cycles
already check.  EXIT CODE IS THE ANSWER.
"""
import re
import sys


def load(path):
    bounds, writes = [], []
    for line in open(path):
        f = line.split()
        if len(f) == 4 and f[1] == "W":
            writes.append((len(bounds), f[2], f[3]))
        elif len(f) == 14:
            bounds.append(f)
    return bounds, writes


_lst = {}


def source_at(asm, pc):
    """The source line lwasm assembled at PC."""
    if not _lst:
        import os
        import subprocess
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
        out = subprocess.run([os.path.join(root, ".tools", "bin", "lwasm"), "--6309", "--format=raw",
                              "--list=-", "--output=" + os.devnull, asm],
                             capture_output=True, text=True).stdout
        for ln in out.splitlines():
            m = re.match(r"^([0-9A-F]{4}) [0-9A-F]+\s+\([^)]*\):\d+\s+(.*)$", ln)
            if m:
                _lst.setdefault(int(m.group(1), 16), m.group(2).strip())
    return _lst.get(pc, "?")


# ⭐ WHERE THE ORACLE'S TIMING IS KNOWN TO DIFFER FROM SILICON'S, by the
# instruction's mnemonic.  Only the instruction's COST may differ; its
# registers and writes are compared exactly like everything else's.
XROAR_BASE = "XRoar's base count differs from silicon's; oracle/checkcyc.py proves hd6309.c's " \
             "table IS silicon's (hoglet67's measured table)"
XROAR_NATIVE = "XRoar does not give native mode's one-cycle saving to this inherent op " \
               "(silicon: hoglet67's table, which oracle/checkcyc.py proves ours equals)"
XROAR_TST = "XRoar puts the MEMORY form's dead cycles on the register form too " \
            "(silicon: hoglet67's table)"
KNOWN_CYCLES = {
    "tim": XROAR_BASE,
    "aim": XROAR_BASE,
    "eim": XROAR_BASE,
    "nop": XROAR_NATIVE,
    "abx": XROAR_NATIVE,
    "rts": XROAR_NATIVE,
    "jsr": XROAR_BASE,
    "oim": XROAR_BASE,
    "daa": XROAR_NATIVE,
    "tsta": XROAR_TST,
    "tstb": XROAR_TST,
    "tste": XROAR_TST,
    "tstf": XROAR_TST,
    "muld": "XRoar charges a flat count; silicon (hoglet67) adds a cycle for each "
            "negative operand and one to negate a negative product",
    "muld (flags)": "with D = 0, XRoar sets N where silicon (hoglet67) and the book set Z",
}


# ⚠ A REGISTER THE ORACLE GETS WRONG CANNOT BE ALLOWED FOR HERE: once the two
# states differ, every later instruction differs too.  So gen6309.py never
# makes those states (DAA's 6309-only correction, LDQ with V set), and the
# silicon behaviour is tested on its own in test/silicon6309.c.


def main():
    a, b, asm = sys.argv[1:4]
    cycles = "--no-cycles" not in sys.argv
    ba, wa = load(a)
    bb, wb = load(b)
    n = min(len(ba), len(bb))
    names = "cyc pc a b e f x y u s v dp cc md".split()
    known, unknown = {}, {}
    for i in range(n):
        x, y = ba[i], bb[i]
        # registers exactly; the CYCLE as this instruction's own cost, so one
        # known difference does not put every later boundary out of step
        bad = x[1:] != y[1:]
        if bad and i and source_at(asm, int(ba[i - 1][1], 16)).split()[0].lower() == "muld" \
                and x[2:4] == ["00", "00"] and x[1:12] == y[1:12] and x[13] == y[13] \
                and (int(x[12], 16) ^ int(y[12], 16)) & ~0x0C == 0:
            # XRoar's MULD with D = 0: N where silicon has Z.  gen6309.py puts
            # TSTA next, so the NEXT boundary must agree in full.
            known["muld (flags)"] = known.get("muld (flags)", 0) + 1
            bad = False
        if cycles and i and not bad:
            dx = int(x[0]) - int(ba[i - 1][0])
            dy = int(y[0]) - int(bb[i - 1][0])
            if dx != dy:
                src = source_at(asm, int(ba[i - 1][1], 16))
                mn = src.split()[0].lower()
                md = "nm" if int(ba[i - 1][13], 16) & 1 else "em"
                if mn in KNOWN_CYCLES:
                    known[mn] = known.get(mn, 0) + 1
                else:
                    key = (mn, md, dx, dy)
                    unknown.setdefault(key, [0, src, i])[0] += 1
        if bad:
            diff = [names[k] for k in range(1, 14) if x[k] != y[k]] or ["cyc"]
            print("FAIL  boundary %d differs in %s, after `%s`"
                  % (i, " ".join(diff), source_at(asm, int(ba[i - 1][1], 16)) if i else "reset"))
            for k in range(max(0, i - 3), i + 1):
                print("      ours   " + " ".join(ba[k]))
                print("      oracle " + " ".join(bb[k]))
            return 1
    # the writes, in order, up to the shorter trace's last boundary
    wa2 = [w for w in wa if w[0] <= n]
    wb2 = [w for w in wb if w[0] <= n]
    for k in range(min(len(wa2), len(wb2))):
        if wa2[k] != wb2[k]:
            i = wa2[k][0]
            print("FAIL  write %d differs: ours %s, oracle %s, by `%s`"
                  % (k, wa2[k][1:], wb2[k][1:], source_at(asm, int(ba[i - 1][1], 16))))
            for j in range(max(0, i - 3), min(i + 1, n)):
                print("      ours   " + " ".join(ba[j]))
            return 1
    if len(wa2) != len(wb2):
        print("FAIL  %d writes against %d" % (len(wa2), len(wb2)))
        return 1
    if unknown:
        for (mn, md, dx, dy), (k, src, i) in sorted(unknown.items()):
            print("FAIL  %-6s %s: ours %d cycles, oracle %d  (x%d; first `%s`, boundary %d)"
                  % (mn.upper(), md, dx, dy, k, src, i))
        print("FAIL  %d instruction forms timed differently" % len(unknown))
        return 1
    if len(ba) != len(bb):
        print("FAIL  %d boundaries against %d (the rest agree)" % (len(ba), len(bb)))
        return 1
    print("ok    %d instruction boundaries and %d writes identical%s"
          % (n, len(wa2), "" if cycles else " (cycles not compared)"))
    for mn, k in sorted(known.items()):
        print("      %d %s timed differently, as known: %s" % (k, mn.upper(), KNOWN_CYCLES[mn]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
