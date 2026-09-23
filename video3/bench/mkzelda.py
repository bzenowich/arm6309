#!/usr/bin/env python3
"""mkzelda.py [CMDSDIR] - the overworld, as a video3 BITMAP playfield.

    python3 video3/bench/mkzelda.py ../nitros9/level2/arm6309/cmds

⚠ THE BINARIES GO BESIDE THIS SCRIPT and only `zeldadat.asm` goes to the port,
which is `mkstardew.py`'s arrangement and for its reason: the equates are
SOURCE the assembler needs and the pictures are data the card carries.

⭐ WHAT THIS REPLACES.  `overworld` draws the same game in the archived
`video/` card's TILE MODE: a 64-row map of cell codes, a 16 KB tile bank on
the card, and a hero composed FIFTEEN TILES AT A TIME in DRAM and written back
into the bank (overworld.asm's `compose1`).  video3 has a copy engine, a
colour key and a hardware sprite, so none of that is necessary: the world is
just a picture in VRAM, the view is scrolled over it by two registers, and the
hero is the sprite.

⛔ AND THE WORLD IS 1024 x 480 BECAUSE THAT IS WHAT FITS.  The overworld is
240 x 76 cells - **1920 x 608 pixels** - and video3's ring is 1024 x 512 with
the picture in rows 0..479 (plan.md §4).  A world that large needs `monster`'s
column streaming in BOTH axes, which is a different program; this takes the
128 x 60 cells the camera can reach and clamps to them, exactly as
`stardew.asm` does with its farm.  ⚠ The original's recorded camera path
(`frames.bin`) does not fit either - it visits 1280 x 392 - so the hero here is
driven by the PROGRAM rather than replaying a recording, which is more of a
game and not less.

What it writes into OUT:

    zelda.pic     1024 x 480 bytes, one RGB332 palette index a pixel, the
                  playfield.  Read straight into ring rows 0..479
    zelda.art     the keyed art bank: the enemies, 16 x 16 each, laid out as
                  one VRAM strip to be copied into ring row ZRART
    zeldadat.asm  every equate the program and this file share

⭐ THE TERRAIN IS THE ORIGINAL GAME'S - `software/demo/tools/mkgame.py`'s
`model.npz` carries the tile bank and the map, and the playfield comes straight
out of it, so this is the same overworld drawn a different way.

⭐⭐ AND THE HERO IS A KEYED BLIT, NOT THE HARDWARE SPRITE.  The first cut put
him on the sprite the way `stardew` and `mvania` put theirs - ⛔ and the sprite
is **two bits a pixel**, so a hero on it has three colours and a transparency.
The card has a colour KEY and a copy engine: an actor drawn with `WM.Sprite`
is full eight-bit colour for one blit, and the only thing it costs over the
sprite is the save-behind the other actors already pay. So he is drawn here at
sixteen art pixels square in as many colours as he wants, and the sprite is
left for the driver's pointer.
⚠ RGB332 throughout, which is what the demo authored and what `vggame` loads.
"""
import os
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
MODEL = ROOT / "software" / "demo" / "build" / "model.npz"

# ⛔ THE GEOMETRY, AND EVERY NUMBER HERE IS IN zeldadat.asm TOO.  The program
# reads none of them from a file: they are assembled in, which is why they are
# emitted rather than documented.
ZWW, ZWH = 1024, 480          # the playfield, and the whole of the ring's picture
ZVW, ZVH = 640, 200           # the view - VMODE 00, as the original's
ZHSMX = ZWW - ZVW             # 384: the camera's right clamp
ZVSMX = ZWH - ZVH             # 280: ... and its bottom
CELLW = CELLH = 8             # the overworld's cell, in VRAM bytes
ZMAPW, ZMAPH = ZWW // CELLW, ZWH // CELLH     # 128 x 60 cells

# ⭐ THE KEYED ART BANK: one 16-row strip at ring row ZRART, columns 0 on.
# ⚠ rows 480..510 are vidcpy3's scratch and row 511 is the pointer's shape
# (plan.md §4); a 16-row strip at 480 is inside the scratch and safe here for
# the reason stardew.asm gives - every copy has source and destination in
# disjoint regions, so nothing ever stages.
#
# ⛔ A SHAPE IS 32 BYTES WIDE AND 16 ROWS, WHICH IS SQUARE.  The view is
# 640 x 200 shown as 640 x 400, so a VRAM byte is one dot wide and TWO LINES
# tall: art is drawn at 16 x 16 and each art pixel becomes two bytes.  A bank
# of 16-byte shapes would be half as wide as it is tall on the connector.
ZRART = 480
ZNART = 16                    # 8 hero frames, then 8 of the cast
ZARTW = 32                    # bytes - 16 art pixels
ZARTH = 16
ZCART = 0
ZNHERO = 8                    # slots 0..7: down, up, left, right x 2

# save-behind scratch: one slot an actor, on ring row ZRSCR
ZRSCR = 496
ZMXAC = 12
ZSCRP = 32                    # a slot's pitch in columns

# ⛔⛔ THE KEY IS INDEX 0, AND IT IS THE CARD'S AND NOT mkgame's.  `mkgame.py`
# picks $E3 because that is a colour its own compositor never draws; video3
# does the test IN HARDWARE, and what `WM.Sprite` refuses to write is **index
# zero** (keyed-copy.md).  A bank keyed on $E3 would have drawn its holes as
# magenta and dropped nothing.
#
# ⚠ AND FOUR OF THE CAST'S DARKS LANDED ON IT.  RGB332 keeps three bits of red,
# three of green and TWO of blue, so every colour darker than (32, 32, 64) is
# index 0 - the hero's outline (20, 16, 16), his eyes, the moblin's shadow and
# the octorok's pupils were all exactly that. `c332()` lifts a zero to 1 and
# says so, because a hole where an outline should be is not a colour bug that
# announces itself: it looks like a sprite with a hole in it.
KEY = 0x00


def load():
    if not MODEL.exists():
        sys.exit("FAIL  mkzelda: no %s - run software/demo/tools/mkgame.py first" % MODEL)
    m = np.load(MODEL)
    return m["tiles"], m["world"], m["sprites"], int(m["key"])


def playfield(tiles, world):
    """The 128 x 60 cells the camera can reach, as 1024 x 480 bytes.

    ⚠ A tile's pixel (r, c) is `tiles[n, r*8 + c]` - graphics.md §6.4.1's
    concatenation, which is why mkgame's tiles.bin IS a VRAM image.  Here the
    tiles are unpacked into a flat picture instead, because a bitmap playfield
    has no tile bank to point at."""
    sub = world[:ZMAPH, :ZMAPW]
    if sub.shape != (ZMAPH, ZMAPW):
        sys.exit("FAIL  mkzelda: the world is %s, too small for %d x %d cells"
                 % (sub.shape, ZMAPW, ZMAPH))
    pic = tiles[sub].reshape(ZMAPH, ZMAPW, CELLH, CELLW)
    out = pic.transpose(0, 2, 1, 3).reshape(ZWH, ZWW).astype(np.uint8)
    # ⭐ AND THE WORLD'S OWN ZEROS MOVE UP ONE, so that LUT entry 0 can be
    # BRIGHT MAGENTA and mean something.  Nothing in the scene is index 0
    # afterwards, so magenta on the connector is a leak and only a leak - a
    # keyed copy that wrote a hole, or a rectangle nobody painted.  It is 1.8%
    # of the map and index 1 is (0, 0, 85), which is as near black as this
    # palette gets.  stardew.asm's PalUp keeps the same discipline.
    out[out == 0] = 1
    return out


def c332(r, g, b):
    """RGB332, the byte the card's LUT is loaded with for this game.

    ⛔ NEVER 0, because 0 is the copy engine's transparent key: a drawn colour
    that quantises to it would be a HOLE in the shape.  1 is the next index
    up - (0, 0, 85), which is as near black as this palette gets."""
    v = ((r >> 5) << 5) | ((g >> 5) << 2) | (b >> 6)
    return v if v else 1


# ⭐⭐ THE HERO, SIXTEEN ART PIXELS SQUARE AND AS COLOURFUL AS HE LIKES.
#
# ⛔ THIS IS WHY HE IS NOT ON THE HARDWARE SPRITE.  The sprite is 2 bits a
# pixel - three inks and a transparency - so a hero on it is a silhouette in
# three colours.  Drawn as a KEYED BLIT he is ordinary eight-bit VRAM: the copy
# engine drops every byte equal to ZKEY and writes the rest, which is one
# rectangle and full colour.  The price over the sprite is the save-behind, and
# every other actor already pays it.
#
# ⚠ Four directions, two walk frames each, in the order the program indexes
# them: DOWN, UP, LEFT, RIGHT - and RIGHT is LEFT mirrored, so it is generated
# rather than drawn twice and cannot disagree with itself.
HPAL = {
    "K": (20, 16, 16),        # outline
    "H": (26, 92, 40),        # cap, shadow side
    "h": (58, 158, 66),       # cap
    "G": (30, 110, 44),       # tunic, shadow
    "g": (72, 176, 78),       # tunic
    "S": (246, 206, 160),     # skin
    "s": (206, 158, 116),     # skin, shadow
    "E": (28, 24, 40),        # eye
    "B": (130, 76, 38),       # boot
    "b": (170, 108, 56),      # boot, lit
    "W": (226, 230, 240),     # shield rim
    "w": (72, 104, 210),      # shield face
    "Y": (240, 214, 96),      # belt / hair
}

HERO = {
 "down1": [
   "....KKKKKKKK....",
   "...KhhhhhhhhK...",
   "..KhhhHHHHhhhK..",
   "..KhSSSSSSSShK..",
   "..KSSSSSSSSSSK..",
   "..KSEESSSSEESK..",
   "..KSSSSSSSSSSK..",
   "...KSSsssSSK....",
   "..KKGGGGGGGGKK..",
   ".KWwGggggggGGK..",
   ".KWWwGgYYYgGKSK.",
   ".KWWwGGYYYGGKSK.",
   "..KWwGGGGGGGK.K.",
   "...KGGGGGGGGK...",
   "...KBbKKKKbBK...",
   "...KKK....KKK...",
 ],
 "down2": [
   "....KKKKKKKK....",
   "...KhhhhhhhhK...",
   "..KhhhHHHHhhhK..",
   "..KhSSSSSSSShK..",
   "..KSSSSSSSSSSK..",
   "..KSEESSSSEESK..",
   "..KSSSSSSSSSSK..",
   "...KSSsssSSK....",
   ".KKGGGGGGGGKK...",
   "KWwGggggggGGK...",
   "KWWwGgYYYgGKSK..",
   "KWWwGGYYYGGKSK..",
   ".KWwGGGGGGGK.K..",
   "..KGGGGGGGGK....",
   "..KbBKKKKBbK....",
   "..KKK....KKK....",
 ],
 "up1": [
   "....KKKKKKKK....",
   "...KhhhhhhhhK...",
   "..KhhhhhhhhhhK..",
   "..KhhhhhhhhhhK..",
   "..KhhhhhhhhhhK..",
   "..KhHHhhhhHHhK..",
   "..KhhhhhhhhhhK..",
   "...KhhhhhhhK....",
   "..KKGGGGGGGGKK..",
   "..KSGggggggGWK..",
   ".KSKGgYYYgGWWWK.",
   ".KSKGGYYYGGWWWK.",
   "..K.KGGGGGGGWK..",
   "...KGGGGGGGGK...",
   "...KBbKKKKbBK...",
   "...KKK....KKK...",
 ],
 "up2": [
   "....KKKKKKKK....",
   "...KhhhhhhhhK...",
   "..KhhhhhhhhhhK..",
   "..KhhhhhhhhhhK..",
   "..KhhhhhhhhhhK..",
   "..KhHHhhhhHHhK..",
   "..KhhhhhhhhhhK..",
   "...KhhhhhhhK....",
   "...KKGGGGGGGGKK.",
   "...KSGggggggGWK.",
   "..KSKGgYYYgGWWWK",
   "..KSKGGYYYGGWWWK",
   "...K.KGGGGGGGWK.",
   "....KGGGGGGGGK..",
   "....KbBKKKKBbK..",
   "....KKK....KKK..",
 ],
 "left1": [
   "....KKKKKKK.....",
   "...KhhhhhhhK....",
   "..KhhHHhhhhhK...",
   "..KhSSSSSShhK...",
   ".KSSSSSSSSShK...",
   ".KSSESSSSSShK...",
   ".KSSSSSSSSShK...",
   "..KSSsssSSK.....",
   "..KKGGGGGGKK....",
   ".KWwGgggggGGK...",
   "KWWwGgYYYggGKS..",
   "KWWwGGYYYGGGKS..",
   ".KWwGGGGGGGGK...",
   "..KGGGGGGGGK....",
   "..KBbKKKKbBK....",
   "..KKK....KKK....",
 ],
 "left2": [
   "....KKKKKKK.....",
   "...KhhhhhhhK....",
   "..KhhHHhhhhhK...",
   "..KhSSSSSShhK...",
   ".KSSSSSSSSShK...",
   ".KSSESSSSSShK...",
   ".KSSSSSSSSShK...",
   "..KSSsssSSK.....",
   "..KKGGGGGGKK....",
   ".KWwGgggggGGK...",
   "KWWwGgYYYggGKS..",
   "KWWwGGYYYGGGKS..",
   ".KWwGGGGGGGGK...",
   "...KGGGGGGGK....",
   "...KbBKKKKBK....",
   "...KKK...KKK....",
 ],
}
HERO_ORDER = ["down1", "down2", "up1", "up2", "left1", "left2"]   # then two mirrors


def hero_art():
    """The eight frames, as 16 x 16 arrays of RGB332 - RIGHT mirrored from LEFT."""
    lut = {k: c332(*v) for k, v in HPAL.items()}
    out = []
    for name in HERO_ORDER:
        rows = HERO[name]
        assert len(rows) == 16, (name, len(rows))
        a = np.full((16, 16), KEY, np.uint8)
        for r, row in enumerate(rows):
            assert len(row) == 16, (name, r, len(row))
            for c, ch in enumerate(row):
                if ch in lut:
                    a[r, c] = lut[ch]
        out.append(a)
    # ⭐ RIGHT IS LEFT MIRRORED, generated and not drawn: two hand-drawn
    # mirrors are two places for a pixel to be wrong in only one of them.
    out.append(out[4][:, ::-1].copy())
    out.append(out[5][:, ::-1].copy())
    assert len(out) == ZNHERO, len(out)
    return out


# ⭐ THE CAST, DRAWN RATHER THAN CUT OUT.  The first attempt took 2 x 2 blocks
# of the overworld's own cells and knocked their corners off, on the theory
# that a creature made of the terrain belongs to it - ⛔ and they came out as
# eight featureless dark blobs, because most of the map is flat ground.  A
# rendering of the bank is what said so, which is the rule: LOOK at the data
# when the symptom is a wrong answer of the right shape.
#
# ⚠ '.' is the key and every other character is an index into the shape's own
# palette below it.  Sixteen rows of sixteen, asserted on the way in.
CAST = [
 ("octorok", {"1": (200, 40, 40), "2": (250, 120, 60), "3": (30, 20, 20), "4": (250, 250, 250)},
  ["................",
   ".....111111.....",
   "....11111111....",
   "...1122221111...",
   "..112222222111..",
   "..122444442211..",
   "..122433342211..",
   "..122433342211..",
   "..122444442211..",
   "..112222222111..",
   "...1122221111...",
   "...111111111....",
   "..1..1...1..1...",
   ".33..33.33..33..",
   "................",
   "................"]),
 ("octorok2", {"1": (200, 40, 40), "2": (250, 120, 60), "3": (30, 20, 20), "4": (250, 250, 250)},
  ["................",
   ".....111111.....",
   "....11111111....",
   "...1122221111...",
   "..112222222111..",
   "..122444442211..",
   "..122343433211..",
   "..122343433211..",
   "..122444442211..",
   "..112222222111..",
   "...1122221111...",
   "...111111111....",
   "...1.11.11.1....",
   "..33.33.33.33...",
   "................",
   "................"]),
 ("moblin", {"1": (60, 130, 50), "2": (120, 190, 80), "3": (25, 20, 15), "4": (240, 230, 160)},
  ["................",
   "...11......11...",
   "...111....111...",
   "....11111111....",
   "...122222221....",
   "..12233223321...",
   "..12233223321...",
   "..1222222221....",
   "..1224444221....",
   "...12222221.....",
   "...111111111....",
   "..1111111111....",
   "..1.111111.1....",
   "..3..1111..3....",
   ".....3..3.......",
   "................"]),
 ("moblin2", {"1": (60, 130, 50), "2": (120, 190, 80), "3": (25, 20, 15), "4": (240, 230, 160)},
  ["................",
   "...11......11...",
   "...111....111...",
   "....11111111....",
   "...122222221....",
   "..12332233221...",
   "..12332233221...",
   "..1222222221....",
   "..1224444221....",
   "...12222221.....",
   "...111111111....",
   "...1111111111...",
   "...1.111111.1...",
   "....3.1111.3....",
   "......3..3......",
   "................"]),
 ("rupee", {"1": (40, 200, 120), "2": (170, 255, 210), "3": (10, 80, 60)},
  ["................",
   "................",
   ".......11.......",
   "......1221......",
   ".....122221.....",
   "....12222331....",
   "...1222233331...",
   "...1222333331...",
   "...1223333331...",
   "...1233333331...",
   "....133333 1....",
   ".....1333 1.....",
   "......131 ......",
   ".......1 .......",
   "................",
   "................"]),
 ("heart", {"1": (220, 40, 70), "2": (255, 150, 170), "3": (120, 10, 30)},
  ["................",
   "................",
   "...11.....11....",
   "..1221...1221...",
   ".122221.122221..",
   ".122222112222 1.",
   ".1222222222233 .",
   ".1222222222333 .",
   "..12222222333 ..",
   "...122222333 ...",
   "....1222333 ....",
   ".....12333 .....",
   "......13 3......",
   ".......1 .......",
   "................",
   "................"]),
 ("bush", {"1": (30, 110, 40), "2": (70, 180, 70), "3": (110, 70, 35)},
  ["................",
   "................",
   "....11...11.....",
   "...1221.1221....",
   "..122221222 1...",
   "..12222222221...",
   ".1222222222221..",
   ".1222122212221..",
   ".1222222222221..",
   "..12222222221...",
   "...111111111....",
   "......333.......",
   "......333.......",
   "......333.......",
   "................",
   "................"]),
 ("rock", {"1": (120, 120, 120), "2": (180, 180, 180), "3": (60, 60, 60)},
  ["................",
   "................",
   "....111111......",
   "...12222211.....",
   "..1222222211....",
   ".122222222211...",
   ".122222222221...",
   ".122333222221...",
   ".122333222221...",
   ".122222222221...",
   "..1222222221....",
   "...13333331.....",
   "....333333......",
   "................",
   "................",
   "................"]),
]


def art_bank(tiles, world):
    """The whole bank: `ZNHERO` hero frames then the CAST, one 16-row strip.

    ⭐ EVERY ART PIXEL BECOMES TWO BYTES on the way out.  The shapes above are
    drawn 16 x 16 because that is square on the connector; a VRAM byte is one
    dot wide and two lines tall in this mode, so a shape is `ZARTW` = 32 bytes.
    ⚠ `np.repeat(a, 2, axis=1)` is the same doubling `mkgame.py`'s `art()`
    does, which is why the terrain and the cast are in proportion with it.

    The key is `ZKEY` ($E3), which the card compares against in `WM.Sprite` -
    so a transparent pixel is literally that byte and the copy engine drops it.
    ⚠ `tiles`/`world` are taken and not used: the signature is kept so a shape
    cut from the map has somewhere to come from.
    """
    shapes = hero_art()
    for name, pal, rows in CAST:
        assert len(rows) == 16, (name, len(rows))
        lut = {k: c332(*v) for k, v in pal.items()}
        a = np.full((16, 16), KEY, np.uint8)
        for r, row in enumerate(rows):
            assert len(row) == 16, (name, r, len(row))
            for c, ch in enumerate(row):
                if ch in lut:
                    a[r, c] = lut[ch]
        shapes.append(a)
    assert len(shapes) == ZNART, (len(shapes), ZNART)
    # ⛔ AND NOTHING DRAWN IS THE KEY.  c332() lifts a zero, so this can only
    # fail if a shape is authored with a literal 0 - and it would fail as a
    # hole in the middle of a sprite, which is not a symptom that names itself.
    for i, a in enumerate(shapes):
        holes = (a == KEY)
        assert holes.any(), "shape %d has no transparent pixel at all" % i
        assert not (a[~holes] == KEY).any()
    strip = np.full((ZARTH, ZNART * ZARTW), KEY, np.uint8)
    for i, a in enumerate(shapes):
        strip[:, i * ZARTW:(i + 1) * ZARTW] = np.repeat(a, 2, axis=1)
    return strip.tobytes()


DAT = """\
********************************************************************
* zeldadat.asm - GENERATED by arm6309 video3/bench/mkzelda.py.  Do not edit.
*
* ⛔ INCLUDED BEFORE THE CODE, so every equate is a BACKWARD reference and an
* 8-bit immediate is chosen as one - the same rule monsterdat.asm's header
* records, and for the same reason.
********************************************************************

ZWW                 equ       {ZWW}       the playfield, in VRAM bytes
ZWH                 equ       {ZWH}
ZVW                 equ       {ZVW}       the view - VMODE 00
ZVH                 equ       {ZVH}
ZHSMX               equ       {ZHSMX}      the camera's clamps: nothing crosses
ZVSMX               equ       {ZVSMX}      the ring's seam, so no wrap arithmetic
ZMAPW               equ       {ZMAPW}      the world, in the overworld's own cells
ZMAPH               equ       {ZMAPH}
ZCELL               equ       {CELLW}

ZRART               equ       {ZRART}      the keyed art bank's ring row
ZCART               equ       {ZCART}
ZNART               equ       {ZNART}
ZARTW               equ       {ZARTW}
ZARTH               equ       {ZARTH}

ZRSCR               equ       {ZRSCR}      save-behind: one slot an actor
ZMXAC               equ       {ZMXAC}
ZSCRP               equ       {ZSCRP}

ZKEY                equ       ${KEY:02X}      mkgame.py's transparent byte
ZNHERO              equ       {ZNHERO}       the hero's frames, slots 0..7
"""


def main(cmds):
    d = pathlib.Path(__file__).resolve().parent
    out = str(d)
    a = pathlib.Path(cmds)
    a.mkdir(parents=True, exist_ok=True)
    tiles, world, sprites, key = load()

    pic = playfield(tiles, world)
    (d / "zelda.pic").write_bytes(pic.tobytes())

    art = art_bank(tiles, world)
    (d / "zelda.art").write_bytes(art)

    (a / "zeldadat.asm").write_text(DAT.format(
        ZWW=ZWW, ZWH=ZWH, ZVW=ZVW, ZVH=ZVH, ZHSMX=ZHSMX, ZVSMX=ZVSMX,
        ZMAPW=ZMAPW, ZMAPH=ZMAPH, CELLW=CELLW,
        ZRART=ZRART, ZCART=ZCART, ZNART=ZNART, ZARTW=ZARTW, ZARTH=ZARTH,
        ZRSCR=ZRSCR, ZMXAC=ZMXAC, ZSCRP=ZSCRP, KEY=KEY, ZNHERO=ZNHERO))

    print("ok    %s/zelda.pic: %d x %d, %d bytes" % (out, ZWW, ZWH, pic.size))
    print("ok    %s/zelda.art: %d keyed shapes of %d x %d, %d bytes"
          % (out, ZNART, ZARTW, ZARTH, len(art)))
    print("ok    %s/zeldadat.asm" % a)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else str(ROOT.parent / "nitros9" / "level2" / "arm6309" / "cmds"))
