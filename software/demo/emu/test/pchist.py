#!/usr/bin/env python3
"""A TIME-WEIGHTED PC histogram from a TRACE log, resolved to ROUTINE names.

    TRACE_AT=26.9 TRACE=600000 ./emu arm6309_rom.bin . 40 2>trace.log
    python3 pchist.py trace.log coarm.lst tbox.lst

⛔ TIME, NOT INSTRUCTIONS.  An instruction count answers "where does the CPU
go"; on this machine that is a different question from "where does the time
go", because /WAIT stretches one store to hundreds of dots.  machine.c's
trace line carries `D <dots>` for exactly this, and each instruction is
charged the difference to the next line.  ⚠ The first version of this script
counted instructions and reported 92 % in the kernel over a window that held
almost no drawing at all - a true statement about instructions and a useless
one about cost.

⚠ AND A PC RANGE IS NOT A MODULE.  The toolbox is a ROM page run in place at
Co.WinA ($A000) with no module header, so machine.c's module_of() cannot name
it and the obvious test - "PC in $A000-$BFFF" - also catches every user
program in task 0 that happens to be linked there.  `rbromdisk` was 15 % of
one window and was reported as toolbox time.  The test has to be the range
AND the module the emulator resolved from the live map.

Listings come from the recipe:

    mkdir -p LST/.mods
    make -C l2 ... LISTDIR=LST AFLAGS_EXTRA=-DV3=1 .mods/coarm


⚠ Two address spaces and they must not be mixed.  CoArm is an OS-9 module
and machine.c's module_of() gives an offset from its header, which is what
its listing's addresses are.  The toolbox is a ROM PAGE run in place at
Co.WinA ($A000), so it has no module header and module_of cannot name it -
its PCs are recognised by range and its listing addresses are PC - $A000.
"""
import re
import sys
import collections

# ⛔ THE SOURCE IS REPRODUCED VERBATIM after a 9-column prefix, so a LABEL
# is a symbol at index 9 and a MNEMONIC is one at index 29.  Stripping the
# whitespace first makes every `lbsr` look like a label, and the histogram
# then reports the time under instruction names - which looks like an answer.
LST = re.compile(r"^([0-9A-F]{4}) ([0-9A-F]{2}[0-9A-F ]*?)\s+\(\s*(\S+)\):\d+(.*)$")
SRCCOL = 9


def labels(path, name):
    """(addr, label, file) for every line of the listing that emitted bytes
    and whose source begins with a label in column 1."""
    out = []
    for ln in open(path, errors="replace"):
        m = LST.match(ln.rstrip("\n"))
        if not m:
            continue
        addr, _by, src, text = m.groups()
        if len(text) <= SRCCOL or text[SRCCOL] in " \t*":
            continue
        lab = re.match(r"^([A-Za-z_][A-Za-z0-9_.$@]*)", text[SRCCOL:])
        if lab:
            out.append((int(addr, 16), lab.group(1), src.split("/")[-1]))
    out.sort()
    return out


def resolve(tab, off):
    lo, hi = 0, len(tab)
    while lo < hi:
        mid = (lo + hi) // 2
        if tab[mid][0] <= off:
            lo = mid + 1
        else:
            hi = mid
    if lo == 0:
        return "?", "?"
    return tab[lo - 1][1], tab[lo - 1][2]


def main(trace, colst, tblst, lo=None, hi=None):
    co = labels(colst, "CoArm")
    tb = labels(tblst, "tbox")
    hist = collections.Counter()
    n = 0
    # \u26a0 TIME-WEIGHTED.  Each instruction is charged the DOTS between its
    # line and the next one's, because /WAIT makes a store cost hundreds of
    # them and an instruction count cannot see that at all.
    rows = []
    for ln in open(trace, errors="replace"):
        if not ln.startswith("PC "):
            continue
        f = ln.split()
        rows.append((int(f[1], 16), int(f[3]), f[-2], f[-1]))
    total = 0
    for i, (pc, dots, task, tail) in enumerate(rows):
        if i + 1 >= len(rows):
            break
        cost = rows[i + 1][1] - dots
        if cost < 0 or cost > 100000:
            continue
        n += cost
        total += 1
        # \u26a0 THE TOOLBOX LISTING IS ABSOLUTE.  tbox.asm is assembled
        # --format=raw with an org at Co.WinA, so its addresses ARE the PC;
        # subtracting $A000 resolved every one of them to "?" while still
        # attributing the time, which reads as "17.5% in a routine I cannot
        # name" rather than as a broken lookup.
        if 0xA000 <= pc < 0xC000:
            r, src = resolve(tb, pc)
            hist["tbox    %-12s %s" % (r, src)] += cost
        elif "+$" in tail and tail.startswith("CoArm"):
            off = int(tail.split("+$")[1], 16)
            r, src = resolve(co, off)
            hist["CoArm   %-12s %s" % (r, src)] += cost
        else:
            hist["other   %-12s" % tail.split("+$")[0]] += cost
    print("%d instructions, %.3f ms of dots (25.175 MHz)"
          % (total, n / 25.175e3))
    for k, v in hist.most_common(40):
        print("  %6d  %5.1f%%  %s" % (v, 100.0 * v / n, k))


if __name__ == "__main__":
    main(*sys.argv[1:])
