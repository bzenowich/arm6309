#!/usr/bin/env python3
"""Every 6309 instruction hd6309.c implements, timed against Appendix A.

    cyc6309.py            (part of test/run.sh)

⭐ WHAT THIS IS FOR.  hd6309.c's cycle counts are hand-written, and a wrong one
is invisible: the instruction does the right thing and the machine is simply the
wrong speed, which is exactly the failure that would make a driver benchmark
lie. software/toolbox/docs/proportional-font.md quotes those benchmarks, so they need a gate.

The table is test/hd6309.tab - Appendix A of The 6309 Book, cross-checked
against lwasm. Each instruction is assembled ALONE by lwasm, run on the core,
and its E-cycle count compared with the book's column for the mode under test.

⚠ INDEXED FORMS ARE `n+` IN THE BOOK - the postbyte's own cost is added on top -
so `,x` (the cheapest postbyte, which adds 0 on a 6809) is what is measured and
the book's base is what it is compared against.
"""
import os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
LWASM = os.path.join(ROOT, ".tools", "bin", "lwasm")

# Only what hd6309.c implements today. Anything else is still refused by name,
# so a missing entry here is not a silent gap - it cannot execute at all.
PROBES = [
    # (source, page, opcode, mode-in-the-table)
    ("sexw",            0, 0x14, "INH"),
    ("ldq #$12345678",  0, 0xCD, "IMM"),
    ("ldw #$1234",      1, 0x86, "IMM"),
    ("ldw <$20",        1, 0x96, "DIR"),
    ("ldw ,x",          1, 0xA6, "IDX"),
    ("ldw >$1234",      1, 0xB6, "EXT"),
    ("stw <$20",        1, 0x97, "DIR"),
    ("stw ,x",          1, 0xA7, "IDX"),
    ("stw >$1234",      1, 0xB7, "EXT"),
    ("addw #$1",        1, 0x8B, "IMM"),
    ("addw <$20",       1, 0x9B, "DIR"),
    ("subw #$1",        1, 0x80, "IMM"),
    ("cmpw #$1",        1, 0x81, "IMM"),
    ("ldq <$20",        1, 0xDC, "DIR"),
    ("ldq ,x",          1, 0xEC, "IDX"),
    ("ldq >$1234",      1, 0xFC, "EXT"),
    ("stq <$20",        1, 0xDD, "DIR"),
    ("stq ,x",          1, 0xED, "IDX"),
    ("stq >$1234",      1, 0xFD, "EXT"),
    ("addr a,b",        1, 0x30, "RTOR"),
    ("adcr a,b",        1, 0x31, "RTOR"),
    ("subr a,b",        1, 0x32, "RTOR"),
    ("sbcr a,b",        1, 0x33, "RTOR"),
    ("andr a,b",        1, 0x34, "RTOR"),
    ("orr a,b",         1, 0x35, "RTOR"),
    ("eorr a,b",        1, 0x36, "RTOR"),
    ("cmpr a,b",        1, 0x37, "RTOR"),
    ("pshsw",           1, 0x38, "INH"),
    ("pulsw",           1, 0x39, "INH"),
    ("pshuw",           1, 0x3A, "INH"),
    ("puluw",           1, 0x3B, "INH"),
    ("ldmd #1",         2, 0x3D, "IMM"),
]


def table():
    t = {}
    for line in open(os.path.join(HERE, "hd6309.tab")):
        if line.startswith("#") or not line.strip():
            continue
        f = line.split()
        t[(int(f[0]), int(f[1], 16))] = (f[2], f[3], int(f[4]), f[5], f[6])
    return t


def base_cycles(s):
    m = re.match(r"(\d+)", s)
    return int(m.group(1)) if m else None


def main():
    tab = table()
    bad = ok = skipped = 0
    runner = os.path.join(ROOT, "hardware", "cpu", "build", "sim", "obj_c", "one6309")
    if not os.path.exists(runner):
        print("FAIL  cyc6309: %s not built" % runner)
        return 1
    with tempfile.TemporaryDirectory() as d:
        for src, page, op, mode in PROBES:
            key = (page, op)
            if key not in tab:
                print("FAIL  cyc6309: %s is not in hd6309.tab" % src)
                bad += 1
                continue
            mnem, tmode, nby, em, nm = tab[key]
            want = base_cycles(em)
            if want is None:
                skipped += 1
                continue
            a = os.path.join(d, "p.asm")
            open(a, "w").write("\torg $1000\n\t%s\n\tswi\n" % src)
            b = os.path.join(d, "p.bin")
            r = subprocess.run([sys.executable, os.path.join(ROOT, "software", "emu", "test", "mkimg.py"), a, b],
                               capture_output=True, text=True)
            if r.returncode != 0:
                print("FAIL  cyc6309: %s did not assemble" % src)
                bad += 1
                continue
            r = subprocess.run([runner, b], capture_output=True, text=True)
            got = int(r.stdout.strip() or -1)
            if got != want:
                print("FAIL  cyc6309: %-18s %s$%02X  book %s, hd6309.c %d"
                      % (src, ("", "$10 ", "$11 ")[page], op, em, got))
                bad += 1
            else:
                ok += 1
    print("cyc6309: %d of %d implemented 6309 forms match Appendix A's "
          "emulation-mode column (%d skipped, %d differ)"
          % (ok, len(PROBES), skipped, bad))
    if bad:
        return 1
    print("ok    cyc6309: every implemented 6309 instruction costs what the book says")
    return 0


if __name__ == "__main__":
    sys.exit(main())
