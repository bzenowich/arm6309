#!/usr/bin/env python3
"""mkmvania.py [CMDSDIR] - mvania's data tables, as lwasm source.

    python3 video3/bench/mkmvania.py ../nitros9/level2/arm6309/cmds

Writes, beside mvania.asm:

    mvaniapal.asm   the 32-entry RGB565 palette, which is `include`d INSIDE
                    the PalRange escape stream, so it must be that and
                    nothing else
    mvaniadat.asm   the sine table, the four actor masks, the hero's
                    two-plane sprite shape and the room's rectangle list

The room's geometry and the palette exist here and nowhere else; the two
.asm files are generated and are checked in beside the source that
includes them.  Re-run this after changing anything below.
"""
import math
import os
import sys


def rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)

PAL = [
    (0x00,0x00,0x00),  # 0  void
    (0x14,0x10,0x26),  # 1  backfar
    (0x1d,0x18,0x36),  # 2  backmid
    (0x2a,0x24,0x48),  # 3  backnear
    (0x3a,0x31,0x57),  # 4  wallA
    (0x4a,0x3f,0x6b),  # 5  wallB
    (0x2b,0x2b,0x3a),  # 6  stoneDark
    (0x55,0x55,0x6e),  # 7  stoneMid
    (0x8a,0x8a,0xa6),  # 8  stoneLite
    (0x3b,0x2f,0x2a),  # 9  floorDark
    (0x6b,0x55,0x44),  # 10 floorMid
    (0x9c,0x7f,0x5f),  # 11 floorLite
    (0x2f,0x5a,0x3a),  # 12 mossA
    (0x47,0x80,0x4f),  # 13 mossB
    (0x7a,0x20,0x10),  # 14 lavaA
    (0xd2,0x52,0x1a),  # 15 lavaB
    (0xff,0xa0,0x3a),  # 16 lavaC
    (0x8a,0x6a,0x2a),  # 17 doorFrame
    (0xff,0xe0,0x8a),  # 18 doorGlow
    (0x1b,0x6f,0x8c),  # 19 crystalA
    (0x3f,0xc9,0xe8),  # 20 crystalB
    (0xd8,0xc0,0xa0),  # 21 dust
    (0xb0,0x40,0x7f),  # 22 bat
    (0x7f,0xd2,0x3f),  # 23 crawler
    (0xf0,0xd0,0x40),  # 24 orb
    (0x56,0xa8,0xff),  # 25 drone
    (0xff,0x6a,0x4a),  # 26 spike
    (0x6a,0x6a,0x80),  # 27 pipe
    (0xff,0xff,0xff),  # 28 highlight
    (0x0a,0x08,0x12),  # 29 shadow
    (0xb0,0x9a,0x6a),  # 30 platTop
    (0x6e,0x5c,0x3c),  # 31 platBody
]

def emit_bytes(label, data, per=8, comment=""):
    out = []
    if comment:
        out.append("* " + comment)
    first = True
    for i in range(0, len(data), per):
        chunk = ",".join("$%02X" % b for b in data[i:i+per])
        lbl = label if first else ""
        out.append("%-19s fcb       %s" % (lbl, chunk))
        first = False
    return "\n".join(out)

# ---------------------------------------------------------------- palette
pal = []
for r, g, b in PAL:
    v = rgb565(r, g, b)
    pal += [v >> 8, v & 255]
PAL_TXT = emit_bytes("PalArt", pal, 8, "32 RGB565 entries: PalRange 0, 32")
DAT = []

# ---------------------------------------------------------------- sine
sin = [int(round(127 * math.sin(2 * math.pi * i / 256))) & 255 for i in range(256)]
DAT.append(emit_bytes("SinTab", sin, 8, "256 entries, signed -127..127"))

# ---------------------------------------------------------------- shapes
SHAPES = {
"bat": """
................
................
..X..........X..
.XXX........XXX.
.XXXX......XXXX.
.XXXXX....XXXXX.
.XXXXXXXXXXXXXX.
..XXXXXXXXXXXX..
...XXXXXXXXXX...
....XX.XX.XX....
.....X.XX.X.....
......XXXX......
.......XX.......
................
................
................
""",
"crawler": """
................
................
................
....XXXXXXXX....
...XXXXXXXXXX...
..XXX.XXXX.XXX..
..XXXXXXXXXXXX..
..XXXXXXXXXXXX..
...XXXXXXXXXX...
..X.X.X..X.X.X..
.X..X.X..X.X..X.
X...X.X..X.X...X
................
................
................
................
""",
"orb": """
................
.....XXXXXX.....
...XXXXXXXXXX...
..XXXXXXXXXXXX..
..XXXXXXXXXXXX..
.XXXXXXXXXXXXXX.
.XXXXXXXXXXXXXX.
.XXXXXXXXXXXXXX.
.XXXXXXXXXXXXXX.
.XXXXXXXXXXXXXX.
.XXXXXXXXXXXXXX.
..XXXXXXXXXXXX..
..XXXXXXXXXXXX..
...XXXXXXXXXX...
.....XXXXXX.....
................
""",
"drone": """
................
......XXXX......
.....XXXXXX.....
....XXXXXXXX....
XXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXX
.XX.XXXXXXXX.XX.
.....XXXXXX.....
......XXXX......
.....X.XX.X.....
....XX.XX.XX....
................
................
................
................
................
""",
}
blob = []
for nm in ("bat", "crawler", "orb", "drone"):
    rows = [r for r in SHAPES[nm].strip("\n").split("\n")]
    assert len(rows) == 16, (nm, len(rows))
    # STRIP-MAJOR: the left eight columns' sixteen rows, then the right eight.
    # A strip is what one WADV 01 run writes, so it must be contiguous.
    for off in (0, 8):
        for r in rows:
            assert len(r) == 16, (nm, r)
            blob.append(sum((1 << (7 - i)) for i in range(8) if r[off + i] == "X"))
DAT.append(emit_bytes("ShpArt", blob, 8,
    "four 16x16 masks, 32 bytes each: STRIP-MAJOR - rows 0-15 of columns 0-7,"))
DAT.append("*      then rows 0-15 of columns 8-15, so a strip is sixteen contiguous bytes"
           "\n*      - a strip is what one WADV 01 run writes, so it must be contiguous")

# ---------------------------------------------------------------- the hero
HERO = """
.....oooooo.....
....obbbbbbo....
...obbbbbbbbo...
...obboooobbo...
...obboooobbo...
...obbbbbbbbo...
....obbbbbbo....
...ooobbbbooo...
..obbbobbobbbo..
..obbbobbobbbo..
..obboobbooobo..
...oobobbobo....
.....obbbbo.....
.....ob..bo.....
....obo..obo....
....oo....oo....
"""
rows = HERO.strip("\n").split("\n")
assert len(rows) == 16
h = []
for r in rows:
    assert len(r) == 16, r
    p0 = [1 if c in "ob" else 0 for c in r]        # plane 0 set for codes 1 and 3
    p1 = [1 if c == "b" else 0 for c in r]         # plane 1 set for codes 2 and 3
    # code 1 = outline (bank 1), code 2 = body (bank 2): so plane0 only for 'o',
    # plane1 only for 'b'
    p0 = [1 if c == "o" else 0 for c in r]
    p1 = [1 if c == "b" else 0 for c in r]
    def by(bits, off):
        return sum((1 << (7 - i)) for i in range(8) if bits[off + i])
    h += [by(p0, 0), by(p0, 8), by(p1, 0), by(p1, 8)]
assert len(h) == 64
DAT.append(emit_bytes("HeroArt", h, 8,
    "plan 7: 16 rows x 4 - plane0 cols 0-7 and 8-15, then plane1's two"))

# ---------------------------------------------------------------- the room
R = []
def rect(x, y, w, hh, c):
    assert 0 <= x and x + w <= 1024, (x, w)
    assert 0 <= y and y + hh <= 240, (y, hh)
    R.append((x, y, w, hh, c))

# ⚠ THE VIEW IS 200 ROWS OF A 240-ROW ROOM and the camera sits at the BOTTOM
# of the slack: VSCROLL runs 22 to 40, so the visible band is rows 22-239 and
# rows 0-21 are ceiling nobody sees.  The floor lip has to be inside that band
# or the hero stands on nothing, which is what the first pass did.
# background bands, full width
for y0, y1, c in ((0, 36, 6), (36, 40, 7), (40, 96, 1), (96, 152, 2),
                  (152, 208, 3), (208, 216, 4), (216, 220, 11), (220, 240, 10)):
    rect(0, y0, 1024, y1 - y0, c)
# floor grain
for x in range(0, 1024, 64):
    rect(x + 8, 224, 40, 3, 9)
    rect(x + 24, 232, 24, 3, 9)
# pillars
for x in (120, 360, 600, 860, 990):
    w = 20
    rect(x, 36, w, 180, 5)
    rect(x + 6, 36, 8, 180, 4)
    rect(x - 4, 36, 28, 6, 7)
    rect(x - 4, 208, 28, 8, 7)
# platforms
PLAT = ((60, 160, 90), (200, 130, 110), (420, 150, 100), (560, 105, 80),
        (700, 168, 120), (880, 128, 90), (300, 188, 70), (764, 96, 70))
for x, y, w in PLAT:
    rect(x, y, w, 10, 31)
    rect(x, y, w, 2, 30)
    rect(x, y + 10, w, 2, 29)
# crystals
for x, y in ((160, 74), (470, 80), (760, 66), (930, 84), (280, 58)):
    rect(x - 2, y - 2, 12, 16, 19)
    rect(x + 1, y + 1, 6, 10, 20)
# pipes from the ceiling
for x in (240, 520, 800):
    rect(x, 40, 8, 30, 27)
    rect(x - 3, 68, 14, 5, 7)
# the door
rect(680, 152, 44, 64, 17)
rect(684, 158, 36, 58, 18)
rect(690, 164, 24, 46, 16)
# a lava pool in the floor
rect(420, 226, 120, 14, 14)
rect(424, 228, 112, 8, 15)
rect(430, 229, 100, 3, 16)
# moss on the floor lip
for x in range(40, 1024, 128):
    rect(x, 216, 34, 4, 12)
    rect(x + 6, 216, 14, 3, 13)

body = []
for x, y, w, hh, c in R:
    body += [x >> 8, x & 255, y >> 8, y & 255, w >> 8, w & 255, hh >> 8, hh & 255, c]
body += [0, 0, 0, 0, 0, 0, 0, 0, 0]
DAT.append(emit_bytes("RoomArt", body, 9,
    "x, y, w, h (words) and a colour: %d rectangles, ending on w = 0" % len(R)))




def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    bar = "*" * 68
    top = bar + "\n* %s - generated by video3/bench/mkmvania.py; do not edit by hand\n" + bar + "\n"
    os.makedirs(out, exist_ok=True)
    for nm, body in (("mvaniapal.asm", [PAL_TXT]), ("mvaniadat.asm", DAT)):
        p = os.path.join(out, nm)
        open(p, "w").write(top % nm + "\n".join(body) + "\n")
        print("ok    %s" % p)


if __name__ == "__main__":
    main()
