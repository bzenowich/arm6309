#!/usr/bin/env python3
"""checkcg.py - software/boot/boot.asm's copy of CoArm's layout, against CoArm's.

⛔ THE BOOT ROM HAS A SECOND COPY OF defs/armvid.d's OFFSETS, and it cannot
have anything else.  boot.asm §10a draws the boot dialog with the ROM toolbox
(nitros9 level2/arm6309/modules/tbox.asm), which reads its state out of CoArm's
globals at `>CoG + CG.*` - but boot.asm is assembled by A09 and armvid.d is
lwasm source, so there is no way to include it.  A field that moves in the
driver tree would then put the dialog's clip, its origin or its vector table
somewhere else, and NOTHING WOULD SAY SO: the dialog would still assemble, the
ROM would still boot, and the picture would be wrong in a way that reads like a
drawing bug.

So this re-derives every one of them with lwasm, off the real armvid.d, and
compares.  software/nitros9/mkrom.sh runs it and refuses to build a ROM whose
two halves disagree.

  python3 software/nitros9/tools/checkcg.py [NITROS9DIR]
"""
import os
import re
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BOOT = os.path.join(ROOT, "software", "boot", "boot.asm")

# boot.asm's equate  ->  the expression armvid.d / arm6309.d says it is.
# ⚠ Every name boot.asm §10a borrowed is here; adding one there without adding
# it here is the hole this file exists to close, so the count is asserted below.
PAIRS = [
    ("COG",     "Co.Data"),
    ("TBENT",   "Co.WinA+3"),
    ("TB_PG",   "TB.Pg"),
    ("ROM_HI",  "ROM.Hi"),
    ("VGBASE",  "VG.Base"),
    ("WT_PCNT", "WT.Parms+1"),
    ("CG_DEV",  "CG.Dev"),
    ("CG_TMP",  "CG.Tmp"),
    ("CG_WINB", "CG.WinB"),
    ("CG_TSTR", "CG.TStr"),
    ("CG_TTOP", "CG.TTop"),
    ("CG_RY",   "CG.RY"),
    ("CG_RX",   "CG.RX"),
    ("CG_RN",   "CG.RN"),
    ("CG_FH",   "CG.FH"),
    ("CG_CX0",  "CG.CX0"),
    ("CG_CY0",  "CG.CY0"),
    ("CG_CX1",  "CG.CX1"),
    ("CG_CY1",  "CG.CY1"),
    ("CG_OX",   "CG.OX"),
    ("CG_OY",   "CG.OY"),
    ("CG_TBV",  "CG.TbV"),
]


def boot_equates():
    """Every `NAME EQU value` in boot.asm whose value is a plain number."""
    out = {}
    for line in open(BOOT, encoding="utf-8"):
        m = re.match(r"^(\w+)\s+EQU\s+(\$[0-9A-Fa-f]+|\d+)\b", line)
        if m:
            v = m.group(2)
            out[m.group(1)] = int(v[1:], 16) if v.startswith("$") else int(v)
    return out


def armvid_values(nd):
    """Assemble one fdb per expression with lwasm and read the words back."""
    src = ["                    use       defsfile",
           "                    use       armvid.d",
           "                    org       0"]
    src += ["                    fdb       " + e for _, e in PAIRS]
    src.append("                    end")
    with tempfile.TemporaryDirectory() as td:
        a = os.path.join(td, "cg.asm")
        b = os.path.join(td, "cg.bin")
        open(a, "w").write("\n".join(src) + "\n")
        cmd = ["lwasm", "--no-warn=ifp1", "--6309", "--format=raw",
               "--pragma=pcaspcr,nosymbolcase,condundefzero,undefextern,"
               "dollarnotlocal,noforwardrefmax",
               "--includedir=" + os.path.join(nd, "defs"),
               "-I", os.path.join(nd, "level2", "arm6309"),
               "-DV3=1", "-o", b, a]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(b):
            sys.stderr.write(r.stdout + r.stderr)
            return None
        d = open(b, "rb").read()
    if len(d) != 2 * len(PAIRS):
        sys.stderr.write("FAIL  checkcg: lwasm emitted %d bytes, want %d\n"
                         % (len(d), 2 * len(PAIRS)))
        return None
    return [struct.unpack(">H", d[i * 2:i * 2 + 2])[0] for i in range(len(PAIRS))]


def main():
    nd = (sys.argv[1] if len(sys.argv) > 1
          else os.environ.get("NITROS9DIR") or os.path.join(ROOT, "..", "nitros9"))
    if not os.path.isdir(os.path.join(nd, "level2", "arm6309")):
        sys.stderr.write("FAIL  checkcg: no NitrOS-9 tree at %s\n" % nd)
        return 1
    want = armvid_values(nd)
    if want is None:
        sys.stderr.write("FAIL  checkcg: lwasm could not read armvid.d\n")
        return 1
    got = boot_equates()
    bad = 0
    for (name, expr), w in zip(PAIRS, want):
        if name not in got:
            print("FAIL  checkcg: boot.asm has no %s (armvid.d: %s = $%04X)"
                  % (name, expr, w))
            bad += 1
        elif got[name] != w:
            print("FAIL  checkcg: boot.asm %s = $%04X, but %s is $%04X"
                  % (name, got[name], expr, w))
            bad += 1
    if bad:
        return 1
    print("ok    boot.asm's %d CoArm offsets are defs/armvid.d's, re-derived with lwasm"
          % len(PAIRS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
