#!/usr/bin/env python3
"""mkfonts.py - the wildbits 8 x 8 fonts, out of their NitrOS-9 source.

⭐ NitrOS-9's own downloadable fonts, not the ROM toolbox's.  The toolbox has
two proportional faces (Noto Sans regular and bold) and its directory reserves
exactly four slots; these are the OTHER font system - 1 bpp, 8 x 8, one glyph
every eight bytes at code * 8, which is what GrfDrv has always meant by a font
and what ca_bmtx.asm's GlyphOf reads out of a GP buffer.

They live in ../nitros9/level1/wildbits/sys/fonts/*.asm as Data modules, one
`fcb` row a scanline.  ⚠ NOTHING IS ASSEMBLED HERE: the bytes are read out of
the source, because the arm6309 ROM never loads them as modules.  v3show.py
sends each one to the card as an ESC $2B GPLoad instead, so a face costs a GP
buffer (CoArm has GPMax = 48) and no ROM disk space at all.

⚠ The parse is checked, not trusted: FONTS drops any file that does not yield
whole 8-byte glyphs, and check() asserts the printable range is not blank -
a font whose codes sit somewhere else would otherwise load as 2 KB of spaces.
"""
import re
import pathlib

FONTDIR = pathlib.Path(__file__).resolve().parents[4] / "nitros9" / \
    "level1" / "wildbits" / "sys" / "fonts"

GLYPH = 8                                       # bytes a glyph: 8 rows, 1 bpp
NEED = 128 * GLYPH                              # at least the ASCII half


def read_asm(path):
    """The fcb bytes of one font module, in order.  ⚠ A line is
    `[label] fcb $xx,$xx,...` and MAY carry a comment column with no
    delimiter, so the value list is matched rather than the line split.
    ⚠ Both radixes are here on purpose: most files are $hex, jessefont.asm
    draws its glyphs as %binary so the source looks like the letter."""
    out = bytearray()
    for line in path.read_text(errors="replace").splitlines():
        if line.lstrip().startswith("*") or line.lstrip().startswith(";"):
            continue
        m = re.search(r"\bfcb\s+((?:\$[0-9A-Fa-f]{2}|%[01]{8})"
                      r"(?:\s*,\s*(?:\$[0-9A-Fa-f]{2}|%[01]{8}))*)", line)
        if m:
            out += bytes(int(v[1:], 16 if v[0] == "$" else 2)
                         for v in (x.strip() for x in m.group(1).split(",")))
    return bytes(out)


def label(stem):
    """What the demo calls it: wildbits names every file `<face>font`."""
    return stem[:-4] if stem.endswith("font") and len(stem) > 4 else stem


def check(name, blob):
    """⚠ A font that parsed is not a font that is THERE.  Every face must
    put ink in the printable range, or its glyphs are somewhere this
    machine will never ask for."""
    ink = sum(bin(b).count("1") for b in blob[32 * GLYPH:127 * GLYPH])
    assert ink > 500, "%s: only %d pixels in codes 32-126" % (name, ink)


def fonts():
    """[(label, 2048 bytes)], by file name.  Faces whose source does not
    parse into whole glyphs are left out and named by report()."""
    out, bad = [], []
    for p in sorted(FONTDIR.glob("*.asm")):
        blob = read_asm(p)
        if len(blob) < NEED or len(blob) % GLYPH:
            bad.append((p.stem, len(blob)))
            continue
        blob = blob[:256 * GLYPH].ljust(256 * GLYPH, b"\0")
        check(p.stem, blob)
        out.append((label(p.stem), blob))
    return out, bad


FONTS, SKIPPED = (fonts() if FONTDIR.is_dir() else ([], []))


def have():
    return bool(FONTS)


if __name__ == "__main__":
    for n, b in FONTS:
        print("ok    %-14s %d bytes" % (n, len(b)))
    for n, k in SKIPPED:
        print("skip  %-14s %d bytes: not whole glyphs" % (n, k))
    print("%d faces, %d bytes" % (len(FONTS), sum(len(b) for _, b in FONTS)))
