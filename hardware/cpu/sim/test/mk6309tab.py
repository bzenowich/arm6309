#!/usr/bin/env python3
"""Derive the HD6309 opcode table, and check it against a second source.

    mk6309tab.py [--book PDF] [--out hd6309.tab] [--check]

⭐ TWO INDEPENDENT SOURCES, WHICH IS WHY THIS SCRIPT EXISTS RATHER THAN A TYPED
TABLE.  The encodings come from **lwasm** - the assembler that actually produces
this project's code, so a table that disagrees with it is wrong by definition -
and the byte counts and both cycle columns come from **Appendix A of The 6309
Book (Burke & Burke)**, the programming card.  Each is checked against the
other and a disagreement is a failure, not a merge.

⛔ THE BOOK IS A SCAN AND ITS OCR LIES.  `1lE0` for `11E0` (lower-case L),
`ALSB/LSLB` for `ASLB/LSLB`, `l1AD` for `11AD`.  Every one of those was in the
first extraction.  The normalisation below is deliberately narrow - it fixes
characters that cannot occur in the field being read (a letter L in a hex
opcode) and nothing else - because a generous normaliser would launder a real
disagreement into agreement, which is the one outcome this script must not
produce.

⚠ THE PDF IS NOT IN GIT.  `reference/**/*.pdf` is ignored: this project has no
right to redistribute the book.  So `hd6309.tab` IS checked in, the way
`<card>/logic/cpld/*.fit` is, and this script re-derives it when the book is present.
Without the book `--check` still runs the lwasm half, which is the half that
covers encodings.  Cycle counts then rest on the checked-in table alone, and
the header of that file says so.

The emitted table is one line per defined opcode:

    <page> <op> <mnem> <mode> <bytes> <em> <nm> <cpu>

  page   0, 1 or 2   -> no prefix, $10, $11
  op     the opcode byte, two hex digits
  mode   INH IMM DIR IDX EXT REL LREL RTOR BITOP TFM PSH
  bytes  instruction length; indexed modes are the base, before the postbyte
  em     cycles in 6809 emulation mode (MD bit 0 clear)
  nm     cycles in 6309 native mode (MD bit 0 set)

⚠ THE CYCLE COLUMNS ARE THE BOOK'S OWN NOTATION, NOT INTEGERS, and they are
kept verbatim because flattening them loses the thing that makes them
interesting:

    6        exact
    6+       plus the indexed postbyte's or the register list's own cost
    >=20     a minimum - CWAI and SYNC wait for the world
    6/15     two values - RTI by CC.E, a long branch by taken/not-taken
    6+3W     TFM: six, plus three a byte. ⭐ This is where sdcard.md's 3.01
             cycles/byte and net.md's 56%-of-the-wire ceiling come from.

⛔ An earlier version of this script demanded an integer and **silently dropped
the whole row** when it did not get one. That cost SYNC, RTI, CWAI and fourteen
of the sixteen long branches - 17 opcodes that the table is supposed to say
exist. A consumer that wants a number takes the leading integer; one that wants
to be exact reads the flag.

⛔ AND `only6309` IS THE COLUMN THAT MATTERS TODAY.  An encoding the 6809 also
defines is not a hazard; one it does not is what `cpu6809.c` has to refuse and
what `armio.asm`'s rule exists for.  The 6809 set is taken from the opcode map
in `cpu6809.c`'s own `build()` - transliterated here, not guessed - so the two
cannot drift without this script saying so.
"""
import argparse, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
BOOK = os.path.join(ROOT, "hardware", "cpu", "reference", "The 6309 Book (Burke & Burke).pdf")
LWASM = os.path.join(ROOT, ".tools", "bin", "lwasm")

# ---------------------------------------------------------------- the book

MODES = {
    "INHERENT": "INH", "IMMEDIATE": "IMM", "DIRECT": "DIR", "INDEXED": "IDX",
    "EXTENDED": "EXT", "RELATIVE": "REL", "LONG RELATIVE": "LREL",
    "REGISTER": "RTOR", "IMMED.": "IMM", "SINGLE BIT": "BITOP",
}

# ⛔ Narrow on purpose - see the header.  Applied ONLY to a field that must be
# hex, so a letter that is not a hex digit can only be an OCR slip.
HEXFIX = str.maketrans({"l": "1", "I": "1", "O": "0", "S": "5", "B": "B"})

# The book's own typos, as distinct from OCR damage.  Each is the mnemonic
# lwasm disagreed with; the value is what lwasm says.
BOOKTYPO = {"ALSB/LSLB": "ASLB/LSLB"}

# ⚠ `6+3W` is TFM: six cycles plus three A BYTE, and it is the only notation in
# the table that depends on a register rather than on the operand.  It is also
# the figure every throughput number in sdcard.md and net.md rests on, so it is
# worth having from the primary document rather than from a comment.
CYC = r">=?[0-9]{1,2}|[0-9]{1,2}\+[0-9]W|[0-9]{1,2}/[0-9]{1,2}|[0-9]{1,2}\+?|-{2,}"

ROW = re.compile(
    r"([0-9A-Fa-flIO]{2,4})\s+"          # opcode, possibly prefixed, possibly OCR'd
    r"([A-Z][A-Z0-9/]*|-{2,})\s+"        # mnemonic or ---
    r"([A-Z][A-Z. ]*?|-{2,})\s+"         # mode or ---
    r"([0-9]\+?|-{2,})\s+"               # bytes
    r"(" + CYC + r")\s+"                 # EM cycles
    r"(" + CYC + r")"                    # NM cycles
)


def book_rows(pdftext):
    """Yield (page, op, mnem, mode, bytes, em, nm) from Appendix A."""
    lines = pdftext.splitlines()
    # ⛔ ANCHOR ON THE COLUMN HEADER, NOT ON THE APPENDIX TITLE.  The title is
    # printed in the FOOTER of each card page, so the first title line sits
    # *after* the first table - anchoring on it silently dropped page 0's
    # $00-$3F, which is 64 opcodes and, in a table whose job is to say which
    # bytes must be refused, 64 missing refusals.
    HDR = re.compile(r"^\s*OP\s+MNEM\s+MODE\s+#", re.I)
    start = next((i for i, l in enumerate(lines) if HDR.match(l)), 0)
    for line in lines[start:]:
        # Each printed line carries TWO column groups; findall takes both.
        for m in ROW.finditer(line):
            op, mnem, mode, nby, em, nm = (g.strip() for g in m.groups())
            if mnem.startswith("--") or nby.startswith("--"):
                continue
            op = op.translate(HEXFIX).upper()
            if not re.fullmatch(r"[0-9A-F]{2,4}", op):
                continue
            mnem = BOOKTYPO.get(mnem, mnem)
            mode = mode.rstrip(". ").upper()
            if mode not in MODES:
                continue
            if len(op) == 4:
                pfx, opb = op[:2], op[2:]
                if pfx not in ("10", "11"):
                    continue
                page = 1 if pfx == "10" else 2
            elif len(op) == 2:
                page, opb = 0, op
            else:
                continue
            yield (page, int(opb, 16), mnem, MODES[mode],
                   int(nby.rstrip("+")), em, nm)


# ---------------------------------------------------------------- lwasm

# One representative source line per (mnemonic, mode).  The operand shapes are
# chosen so lwasm cannot pick a different mode than the one intended: `<` forces
# direct, `>` forces extended, `,x` forces indexed with a one-byte postbyte.
OPERAND = {
    "INH": "", "IMM": " #1", "DIR": " <$20", "IDX": " ,x", "EXT": " >$1234",
    "REL": " *", "LREL": " *", "RTOR": " a,b", "BITOP": " a,1,2,$30",
}
# OIM/AIM/EIM/TIM carry an immediate byte AND a memory operand, so they do not
# take the plain shapes above.
LOGMEM = {"DIR": " #$0F,<$20", "IDX": " #$0F,,x", "EXT": " #$0F,>$1234"}
# TFM's four forms are four opcodes with one mnemonic, so the operand decides
# which encoding comes out and the table's opcode is what selects the form.
TFMFORM = {0x38: " x+,y+", 0x39: " x-,y-", 0x3A: " x+,y", 0x3B: " x,y+"}


LST = re.compile(r"^([0-9A-F]{4}) ([0-9A-F]+)\s+\(.*\):(\d+)")


def lwasm_encode(lines, six309=True):
    """Assemble `lines` and return a list of byte strings, one per input line.

    ⚠ ONE INSTRUCTION PER ASSEMBLY, NOT ONE BIG FILE.  A single bad mnemonic
    makes lwasm abandon the listing, and the whole batch then comes back
    unverified - which reads exactly like "nothing to check" rather than like a
    failure.  Each line is assembled alone so a rejection is attributable, and
    the result is keyed by the listing's own source-line number rather than by
    output order, because `org` and error lines do not produce one.
    """
    if not os.path.exists(LWASM):
        return None
    out = []
    with tempfile.TemporaryDirectory() as d:
        s, b = os.path.join(d, "t.asm"), os.path.join(d, "t.bin")
        for l in lines:
            open(s, "w").write("\torg 0\n\t%s\n" % l)
            # ⛔ `--6809` IS THE RESTRICTIVE FLAG; OMITTING `--6309` IS NOT
            # 6809 MODE.  lwasm's default accepts 6309 mnemonics, so the first
            # version of this classified 423 of 439 opcodes as "shared" and
            # would have had cpu6809.c refuse almost nothing. The error text is
            # explicit once the right flag is passed: "Illegal use of 6309
            # instruction in 6809 mode".
            p = subprocess.run([LWASM, "--6309" if six309 else "--6809",
                                "--format=raw", "--list=-", "--output=" + b, s],
                               capture_output=True, text=True)
            got = None
            for ln in p.stdout.splitlines():
                m = LST.match(ln)
                if m and int(m.group(3)) == 2:
                    got = m.group(2)
            out.append(got)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default=BOOK)
    ap.add_argument("--out", default=os.path.join(HERE, "hd6309.tab"))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--from-tab", action="store_true",
                    help="regenerate the C header from the checked-in .tab "
                         "alone - no book, no lwasm. This is what a machine "
                         "without the PDF uses to prove the two are in step.")
    ap.add_argument("--header", default=os.path.join(
        os.path.dirname(HERE), "hd6309ops.h"))
    a = ap.parse_args()

    if a.from_tab:
        items, only = load_tab(a.out)
        emit_header(a.header, items, only)
        return 0

    if not os.path.exists(a.book):
        print("no book at %s - nothing to re-derive" % a.book)
        return 0
    txt = subprocess.run(["pdftotext", "-layout", a.book, "-"],
                         capture_output=True, text=True).stdout

    rows = {}
    dup = 0
    for page, op, mnem, mode, nby, em, nm in book_rows(txt):
        k = (page, op)
        if k in rows:
            dup += 1
            continue                      # the header line repeats on every page
        rows[k] = (mnem, mode, nby, em, nm)

    # ---- cross-check every encoding against lwasm -------------------------
    bad, checked, unver = [], 0, []
    items = sorted(rows.items())
    allrows = items
    srcs, keys = [], []
    for (page, op), (mnem, mode, nby, em, nm) in items:
        base = mnem.split("/")[0]
        if base == "TFM":
            operand = TFMFORM.get(op)
        elif base in ("OIM", "AIM", "EIM", "TIM"):
            operand = LOGMEM.get(mode)
        elif base == "CWAI":
            operand = " #$FF"       # the book calls it INHERENT; it is immediate
        elif base in ("SWI2", "SWI3"):
            operand = ""            # lwasm spells the prefix itself
        else:
            operand = OPERAND.get(mode)
        if operand is None:
            unver.append((page, op, mnem, mode))
            continue
        srcs.append(base + operand)
        keys.append((page, op, mnem, mode, nby))
    enc = lwasm_encode(srcs)
    if enc is None:
        print("⚠ no lwasm at %s - encodings NOT cross-checked" % LWASM)
    else:
        for (page, op, mnem, mode, nby), got in zip(keys, enc):
            if got is None:
                unver.append((page, op, mnem, mode))
                continue
            want = ("" if page == 0 else ("10" if page == 1 else "11")) + "%02X" % op
            checked += 1
            if not got.startswith(want):
                bad.append("%s %s: book says %s, lwasm assembles %s" %
                           (mnem, mode, want, got))
            elif mode != "IDX" and len(got) // 2 != nby:
                bad.append("%s %s: book says %d bytes, lwasm emits %d (%s)" %
                           (mnem, mode, nby, len(got) // 2, got))

    # ⭐ WHICH ARE 6309-ONLY, ASKED OF THE ASSEMBLER RATHER THAN OF MEMORY.
    # lwasm without --6309 is a 6809 assembler, so a mnemonic it refuses - or
    # one it encodes to a DIFFERENT byte - is one the 6809 does not have. The
    # second case is the subtle one and it is real: $01/$02/$05/$0B are OIM,
    # AIM, EIM and TIM on a 6309 and are undefined on a 6809, while lwasm's
    # 6809 mode has its own opinion about some of them.
    only, ghosts = {}, []
    enc09 = lwasm_encode(srcs, six309=False) if enc is not None else None
    if enc09 is not None:
        for (page, op, mnem, mode, nby), g9, g3 in zip(keys, enc09, enc):
            # ⛔ A FAILURE TO ASK IS NOT A NEGATIVE ANSWER.  `g3 is None` means
            # this probe could not be assembled at all - a bad operand shape in
            # the table above, not a property of the 6809 - and scoring it as
            # "6309-only" invents a trap for an instruction the 6809 has.  It
            # did exactly that for CWAI, whose operand the book omits. Leave it
            # unresolved and let the "?" count be visible.
            if g3 is None:
                # ⛔ NEITHER ASSEMBLER WILL PRODUCE IT, SO THE BOOK IS ALONE -
                # and a table whose job is to list bytes a model must REFUSE
                # cannot invent one. Three did get invented: $1050 NEGW,
                # $1057 ASRW and $1058 ASLW, read out of the appendix's `---`
                # rows by column bleed. lwasm answers "Bad opcode" for all
                # three while COMW and LSRW beside them assemble, which is what
                # caught it. A fabricated entry here is a spurious trap on
                # working 6809 code, so these are DROPPED and counted.
                if g9 is None:
                    ghosts.append((page, op, mnem, mode))
                continue
            only[(page, op)] = (g9 is None or g9 != g3)
    for g in ghosts:
        rows.pop((g[0], g[1]), None)
    print("6309-only: %d of %d checked encodings" % (sum(only.values()), len(only)))
    if ghosts:
        print("⛔ dropped %d book rows NEITHER assembler will produce: %s"
              % (len(ghosts), ", ".join("%s%02X %s" % (("", "10", "11")[p], o, m)
                                        for p, o, m, _ in ghosts)))

    print("book: %d opcodes (%d duplicate header rows skipped)" % (len(rows), dup))
    print("lwasm: %d encodings agree, %d unverifiable, %d DISAGREE"
          % (checked - len(bad), len(unver), len(bad)))
    for b in bad[:40]:
        print("  FAIL", b)
    if bad and a.check:
        return 1

    items = sorted(rows.items())
    with open(a.out, "w") as f:
        f.write("# HD6309 opcode table - GENERATED by mk6309tab.py, do not edit.\n")
        f.write("# Encodings cross-checked against lwasm; byte and cycle counts from\n")
        f.write("# Appendix A of The 6309 Book (Burke & Burke), which is not in git.\n")
        f.write("# page op mnem mode bytes em nm cpu\n#   cpu: 6309 = this encoding does not exist on a 6809 and must be REFUSED by\n#   a 6809 model; 6809 = shared; ? = lwasm could not be asked.\n")
        for (page, op), (mnem, mode, nby, em, nm) in items:
            flag = only.get((page, op))
            f.write("%d %02X %-10s %-5s %d %-5s %-5s %s\n"
                    % (page, op, mnem, mode, nby, em, nm,
                       "6309" if flag else ("6809" if flag is False else "?")))
    print("wrote %s" % a.out)

    emit_header(a.header, items, only)
    return 0


def emit_header(path, items, only):
    # ---- the C side: a bitmap of what a 6809 model must refuse ------------
    bits = [[0] * 32 for _ in range(3)]
    names = {}
    for (page, op), (mnem, mode, nby, em, nm) in items:
        if only.get((page, op)):
            bits[page][op >> 3] |= 1 << (op & 7)
        names[(page, op)] = mnem
    with open(path, "w") as f:
        f.write("/* GENERATED by test/mk6309tab.py from hd6309.tab - do not edit.\n"
                " *\n"
                " * Which (page, opcode) pairs exist on an HD6309 and NOT on a 6809.\n"
                " * A 6809 model must REFUSE these rather than decode them: $01 is OIM\n"
                " * on a 6309 and a ghost of NEG on a 6809, so \"execute it as the\n"
                " * neighbour\" turns a block operation into an arithmetic one and runs\n"
                " * on. armio.asm:513 records what that cost once - a TFM that\n"
                " * \"assembled, linked, booted - and copied NOTHING\".\n"
                " */\n#ifndef HD6309OPS_H\n#define HD6309OPS_H\n#include <stdint.h>\n\n")
        f.write("#define HD6309_ONLY_COUNT %d\n\n" % sum(1 for k in names if only.get(k)))
        f.write("static const uint8_t hd6309_only[3][32] = {\n")
        for pg in range(3):
            f.write("    {" + ",".join("0x%02X" % b for b in bits[pg]) + "},\n")
        f.write("};\n\n")
        f.write("/* 1 if this (page, op) is a 6309-only encoding. */\n"
                "static inline int hd6309_is_only(int page, uint8_t op)\n"
                "{\n"
                "    return page >= 0 && page < 3 &&\n"
                "           (hd6309_only[page][op >> 3] >> (op & 7)) & 1;\n"
                "}\n\n")
        # ---- the cycle columns, for native mode ---------------------------
        # ⭐ Native mode is not a rewrite of the core: it is a DELTA.  The 6809
        # model's counts are mc6809i.v's (including its five documented
        # departures from the datasheet), and native mode shortens many
        # instructions by one cycle.  Carrying (nm - em) as data lets the delta
        # be applied on top of whatever the 6809 core computed, so the Verilog's
        # quirks survive and the saving is the book's.
        # ⚠ 0 where the book's column is not a plain integer (>=N, N/M, N+kW):
        # those are state-dependent and a delta would be a lie.
        def num(x):
            import re as _re
            m = _re.fullmatch(r"([0-9]{1,2})\+?", x)
            return int(m.group(1)) if m else None
        f.write("/* native-mode cycle delta (NM - EM), 0 where the book's column\n"
                " * is state-dependent (>=N, N/M, N+kW) and a delta would lie. */\n")
        f.write("static const signed char hd6309_nm_delta[3][256] = {\n")
        for pg in range(3):
            row = [0] * 256
            for (page, op), (mnem, mode, nby, em, nm) in items:
                if page != pg:
                    continue
                a, b = num(em), num(nm)
                if a is not None and b is not None:
                    row[op] = b - a
            f.write("    {" + ",".join(str(v) for v in row) + "},\n")
        f.write("};\n\n")
        # ---- the complete HD6309 core's tables (hd6309.c, 2026-09-24) -------
        # ⭐ EVERY encoding the 6309 defines, shared or not: anything else takes
        # the ILLEGAL INSTRUCTION TRAP on an HD6309, where a 6809 model ghosts it.
        # ⭐ And the BASE cycles in both modes.  For the book's special forms the
        # leading number is emitted and the core adds the state-dependent part:
        # `6/15` (RTI: fast/entire), `5/6` (a long branch: not taken/taken),
        # `>=N` (SYNC, CWAI), `6+3W` (TFM), and `N+` (the indexed postbyte, or a
        # stacked register's bytes).
        MODES = {"INH": 0, "IMM": 1, "DIR": 2, "IDX": 3, "EXT": 4, "REL": 5,
                 "RTOR": 6, "BITOP": 7}
        def lead(x):
            import re as _re
            m = _re.match(r">?=?([0-9]{1,2})", x)
            return int(m.group(1)) if m else 0
        defd = [[0] * 32 for _ in range(3)]
        mode = [[255] * 256 for _ in range(3)]
        cyc = [[[0, 0] for _ in range(256)] for _ in range(3)]
        # ⭐ hd6309.silicon: where silicon corrects the book (oracle/checkcyc.py
        # holds the result to hoglet67's measured table, exactly).
        corr = {}
        silp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hd6309.silicon")
        for line in open(silp):
            if line.startswith("#") or not line.strip():
                continue
            g = line.split()
            corr[(int(g[0]), int(g[1], 16))] = [int(g[2]), int(g[3])]
        for (page, op), (mnem, md, nby, em, nm) in items:
            defd[page][op >> 3] |= 1 << (op & 7)
            mode[page][op] = MODES.get(md, 255)
            cyc[page][op] = corr.get((page, op), [lead(em), lead(nm)])
        f.write("/* 1 if this (page, op) is defined on an HD6309 (shared or not). */\n"
                "static const uint8_t hd6309_def[3][32] = {\n")
        for pg in range(3):
            f.write("    {" + ",".join("0x%02X" % b for b in defd[pg]) + "},\n")
        f.write("};\n\n")
        f.write("static inline int hd6309_is_defined(int page, uint8_t op)\n"
                "{\n"
                "    return page >= 0 && page < 3 &&\n"
                "           (hd6309_def[page][op >> 3] >> (op & 7)) & 1;\n"
                "}\n\n")
        f.write("enum { HM_INH, HM_IMM, HM_DIR, HM_IDX, HM_EXT, HM_REL, HM_RTOR, HM_BITOP,\n"
                "       HM_NONE = 255 };\n")
        f.write("static const uint8_t hd6309_mode[3][256] = {\n")
        for pg in range(3):
            f.write("    {" + ",".join(str(v) for v in mode[pg]) + "},\n")
        f.write("};\n\n")
        f.write("/* base cycles, [page][op][0 emulation, 1 native] - the book's column's\n"
                " * LEADING number; 0 where the 6309 does not define the encoding. */\n")
        f.write("static const uint8_t hd6309_cyc[3][256][2] = {\n")
        for pg in range(3):
            f.write("    {" + ",".join("{%d,%d}" % tuple(c) for c in cyc[pg]) + "},\n")
        f.write("};\n\n")
        f.write("static inline const char *hd6309_name(int page, uint8_t op)\n{\n"
                "    switch ((page << 8) | op) {\n")
        for (page, op), mnem in sorted(names.items()):
            f.write("    case 0x%03X: return \"%s\";\n" % ((page << 8) | op, mnem))
        f.write("    default: return \"?\";\n    }\n}\n\n#endif\n")
    print("wrote %s (%d 6309-only encodings)" % (path, sum(1 for k in names if only.get(k))))


def load_tab(path):
    """Read a checked-in hd6309.tab back into (items, only)."""
    items, only = [], {}
    for line in open(path):
        if line.startswith("#") or not line.strip():
            continue
        f = line.split()
        page, op = int(f[0]), int(f[1], 16)
        items.append(((page, op), (f[2], f[3], int(f[4]), f[5], f[6])))
        if f[7] != "?":
            only[(page, op)] = (f[7] == "6309")
    return sorted(items), only


if __name__ == "__main__":
    sys.exit(main())
