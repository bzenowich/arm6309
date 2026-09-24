#!/usr/bin/env python3
"""cov6309.py - what a set of 6309 differential runs actually executed.

    cov6309.py prog1.bin trace1 [prog2.bin trace2 ...]

Every encoding hd6309.tab defines, in EACH mode, and every indexed postbyte in
each mode.  ⛔ A differential that never ran an instruction has not checked
it, and "18 seeds agree" says nothing about an opcode none of them drew.
EXIT CODE IS THE ANSWER: 1 if a defined encoding never ran in either mode.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def defined():
    out = {}
    for line in open(os.path.join(HERE, "hd6309.tab")):
        if line.startswith("#") or not line.strip():
            continue
        f = line.split()
        out[(int(f[0]), int(f[1], 16))] = (f[2], f[3])
    return out


def main():
    args = sys.argv[1:]
    defs = defined()
    seen = {0: set(), 1: set()}
    pbs = {0: set(), 1: set()}
    for k in range(0, len(args), 2):
        img = open(args[k], "rb").read()
        for line in open(args[k + 1]):
            f = line.split()
            if len(f) != 14:
                continue
            pc, md = int(f[1], 16), int(f[13], 16) & 1
            op, page, at = img[pc], 0, pc + 1
            if op in (0x10, 0x11):
                page, op, at = (1 if op == 0x10 else 2), img[(pc + 1) & 0xFFFF], pc + 2
            seen[md].add((page, op))
            mode = defs.get((page, op), ("", ""))[1]
            if mode == "IDX":
                if (page, op) in ((0, 0x01), (0, 0x02), (0, 0x05), (0, 0x0B)) or (page == 0 and op >> 4 == 6 and op & 15 in (1, 2, 5, 0xB)):
                    at += 1                      # AIM/OIM/EIM/TIM: the immediate first
                pbs[md].add(img[at & 0xFFFF])
    never = [k for k in defs if k not in seen[0] and k not in seen[1]]
    one = [k for k in defs if (k in seen[0]) != (k in seen[1])]
    for k in sorted(never):
        print("FAIL  never ran: %s%02X %s %s" % ({0: "", 1: "$10 ", 2: "$11 "}[k[0]], k[1], *defs[k]))
    # ⚠ less the RR variants of the PC-relative forms, which ignore those bits
    # and which lwasm emits one way only (gen6309.PB_ALL)
    idx = {pb for pb in range(0x80, 0x100)
           if pb not in (0x92, 0xB2, 0xD2, 0xF2, 0xBF, 0xDF, 0xFF)
           and not ((pb & 0x0E) == 0x0C and pb & 0x60)}
    print("      %d of %d encodings ran in both modes; %d in one only; %d never"
          % (len(defs) - len(never) - len(one), len(defs), len(one), len(never)))
    for md in (0, 1):
        print("      %s: %d of %d indexed postbytes above $7F"
              % (("emulation", "native")[md], len(idx & pbs[md]), len(idx)))
    return 1 if never else 0


if __name__ == "__main__":
    sys.exit(main())
