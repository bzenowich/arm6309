#!/usr/bin/env python3
"""checkcyc.py - our 6309 cycle tables against SILICON'S, as hoglet67 measured.

    python3 hardware/cpu/sim/oracle/checkcyc.py [--show]

⭐ WHY.  test/hd6309.tab's cycle columns come from Appendix A of The 6309 Book,
read out of a SCAN - and mk6309tab.py's own header records the OCR inventing
opcodes.  A cycle count the OCR got wrong is invisible: the instruction does
the right thing and the machine is simply the wrong speed.  hoglet67's (David
Banks) 6809Decoder carries a per-opcode table of emulation- and native-mode
cycles that its author validated against logic-analyser captures of real
HD6309s, and per-postbyte indexed tables transcribed from Burke & Burke's own
"Addendum to The 6309 Book: Indexed Addressing Mode Post Bytes".  This fetches
that file at one pinned commit and compares:

  1. every opcode both tables define: the book's base cycles against silicon's
  2. hd6309.c's postbyte tables (IX_EM, IX_NM) against the addendum's

⛔ The decoder's repository carries NO LICENCE, so its file is fetched into
build/ and read, never copied here; the cycle counts are facts and the
comparison is ours.  EXIT CODE IS THE ANSWER: every difference must be one
this file lists as KNOWN, with the reason it is not a fault.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
SHA = "4f7e1846375024888ad7987bd390f434897953cf"
URL = "https://raw.githubusercontent.com/hoglet67/6809Decoder/%s/src/em_6809.c" % SHA
OUT = os.path.join(ROOT, "hardware", "cpu", "build", "oracle", "em_6809.c")
TAB = os.path.join(HERE, "..", "test", "hd6309.tab")
CORE = os.path.join(HERE, "..", "hd6309.c")

# ⭐ Differences that are understood.  (page, op): reason.
KNOWN = {}


def fetch():
    if not os.path.exists(OUT):
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        r = subprocess.run(["curl", "-sfL", "-o", OUT, URL])
        if r.returncode != 0:
            print("FAIL  checkcyc: cannot fetch hoglet67's em_6809.c at %s" % SHA)
            sys.exit(1)
    return open(OUT, encoding="latin-1").read()


def silicon_ops(src):
    """{(page, op): (mnem, em, nm)} from instr_table_6309."""
    a = src.index("static opcode_t instr_table_6309[] = {")
    body = src[a:src.index("};", a)]
    out = {}
    for m in re.finditer(r"/\*\s*([0-9A-F]{2,4})\s*\*/\s*\{\s*&op_(\w+)\s*,\s*(\w+)\s*,"
                         r"\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\}", body):
        code = int(m.group(1), 16)
        page = {0x10: 1, 0x11: 2}.get(code >> 8, 0) if code > 0xFF else 0
        op = code & 0xFF
        # ⚠ Skip on the NAME, not the mode: the decoder lists $115D TSTF with
        # mode ILLEGAL and the right cycles - a typo in its table.
        if m.group(2) in ("TRAP", "XX"):
            continue
        out[(page, op)] = (m.group(2), int(m.group(5)), int(m.group(6)))
    return out


def silicon_postbytes(src, name):
    a = src.index("static int %s[0x100] = {" % name)
    body = src[a:src.index("};", a)]
    body = re.sub(r"//[^\n]*", "", body.split("{", 1)[1])
    vals = [int(v) for v in re.findall(r"-?\d+", body)]
    assert len(vals) == 256, (name, len(vals))
    return vals


SIL = os.path.join(HERE, "..", "test", "hd6309.silicon")


def book_ops():
    """The table the core runs on: the book's, with hd6309.silicon applied."""
    out = {}
    corr = {}
    for line in open(SIL):
        if line.startswith("#") or not line.strip():
            continue
        f = line.split()
        corr[(int(f[0]), int(f[1], 16))] = (int(f[2]), int(f[3]))
    for line in open(TAB):
        if line.startswith("#") or not line.strip():
            continue
        f = line.split()
        lead = lambda x: int(re.match(r">?=?(\d+)", x).group(1))
        key = (int(f[0]), int(f[1], 16))
        em, nm = corr.get(key, (lead(f[5]), lead(f[6])))
        out[key] = (f[2], f[3], em, nm, f[5], f[6])
    return out


def core_postbytes():
    src = open(CORE).read()
    res = []
    for name in ("IX_EM", "IX_NM"):
        a = src.index("static const int8_t %s[256] = {" % name)
        body = src[a:src.index("};", a)]
        body = re.sub(r"/\*.*?\*/", "", body.split("{", 1)[1], flags=re.S)
        vals = [int(v) for v in re.findall(r"-?\d+", body)]
        assert len(vals) == 256, (name, len(vals))
        res.append(vals)
    return res


def main():
    show = "--show" in sys.argv
    src = fetch()
    sil, book = silicon_ops(src), book_ops()
    bad, known = [], 0
    for key in sorted(set(sil) | set(book)):
        if key in ((0, 0x10), (0, 0x11)):
            continue                          # the prefixes themselves
        if key not in sil or key not in book:
            bad.append("%s: defined in %s only" % (fmt(key), "the book" if key in book else "silicon"))
            continue
        mn, em, nm = sil[key]
        bmn, mode, bem, bnm, rem, rnm = book[key]
        if (em, nm) != (bem, bnm):
            line = "%s %-6s %-4s book %s/%s  silicon %d/%d" % (fmt(key), bmn, mode, rem, rnm, em, nm)
            if key in KNOWN:
                known += 1
                if show:
                    print("      known: " + line + " - " + KNOWN[key])
            else:
                bad.append(line)
    pb_bad = []
    try:
        ours = core_postbytes()
        for k, name in enumerate(("postbyte_cycles_6309_emu", "postbyte_cycles_6309_nat")):
            sv = silicon_postbytes(src, name)
            for pb in range(256):
                if ours[k][pb] != sv[pb]:
                    pb_bad.append("%s $%02X: ours %d, addendum %d" % (("emulation", "native")[k], pb, ours[k][pb], sv[pb]))
    except ValueError:
        pb_bad.append("hd6309.c carries no IX_EM/IX_NM tables yet")
    for b in bad:
        print("FAIL  " + b)
    for b in pb_bad:
        print("FAIL  " + b)
    if bad or pb_bad:
        print("FAIL  checkcyc: %d opcode(s) and %d postbyte(s) differ from silicon" % (len(bad), len(pb_bad)))
        return 1
    print("ok    checkcyc: %d opcodes' cycles agree with silicon in both modes (%d known differences),"
          % (len(book) - known, known))
    print("      and both postbyte tables are the addendum's, all 512 entries")
    return 0


def fmt(key):
    page, op = key
    return ("" if page == 0 else "$10" if page == 1 else "$11") + "$%02X" % op


if __name__ == "__main__":
    sys.exit(main())
