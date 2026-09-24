#!/usr/bin/env python3
"""mkzelda.py [CMDSDIR] - the overworld, as a video3 BITMAP playfield.

    python3 software/archive/zelda/bench/mkzelda.py ../nitros9/level2/arm6309/cmds

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

⭐ THE TERRAIN IS THE ORIGINAL GAME'S - `software/archive/zelda/bench/mkgame.py`'s
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

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODEL = ROOT / "software" / "zelda" / "build" / "model.npz"

# ⛔ THE GEOMETRY, AND EVERY NUMBER HERE IS IN zeldadat.asm TOO.  The program
# reads none of them from a file: they are assembled in, which is why they are
# emitted rather than documented.
#
# ⭐⭐ ROOMS, NOT A SCROLLING WORLD - 2026-09-22, and the reason is draw time.
# An actor is three copy-engine rectangles a frame (restore, save, draw) at
# ~186 us each, so a free-roaming scene's actor pass overhangs the top of the
# picture and the beam catches it mid-blit.  A ROOM is the answer the NES gave:
# the creatures freeze, the next room slides in, and then THAT room's creatures
# are placed - so the count on screen is DATA and the budget can be proved
# rather than measured.  `optimizations.md` §11 has the arithmetic.
#
# ⛔ AND THE ROOM IS 512 WIDE BECAUSE THE RING IS 1024 AND THE VIEW IS 640.
# Every VMODE is 640 dots across; the ring is a 1024-column torus.  Two
# horizontally adjacent 640-wide rooms therefore CANNOT both be resident, so a
# room that exactly fills the screen cannot slide to its neighbour.  Rooms of
# 512 tile the torus exactly, two at a time, and the view shows 64 columns of
# each neighbour - which is why every room's outer eight cells are the same
# wall.  You are looking at your neighbour's wall and it is identical to your
# own, so the seam does not exist.
ZRINGW, ZRINGH = 1024, 512    # the framebuffer torus, both axes
ZVW, ZVH = 640, 240           # the view - VMODE 01, shown as 640 x 480
ZSLTW, ZSLTH = 512, 240       # one room slot in the ring
CELLW = CELLH = 8             # the overworld's cell, in VRAM bytes
ZRMCW, ZRMCH = ZSLTW // CELLW, ZSLTH // CELLH        # 64 x 30 cells
ZWCX, ZWCY = 8, 3             # the wall, in cells: 64 columns, 24 rows
ZWLDW, ZWLDH = 4, 2           # the world, in ROOMS
ZNROOM = ZWLDW * ZWLDH

# ⚠ THE INTERIOR IS SQUARE ON THE CONNECTOR.  48 x 24 cells is 384 x 192 VRAM
# bytes, and a byte is one dot wide and two lines tall in this mode - 384 x 384
# displayed.  The wall is 64 columns a side and 24 rows top and bottom.
ZINTX, ZINTY = ZWCX * CELLW, ZWCY * CELLH            # 64, 24
ZINTW = ZSLTW - 2 * ZINTX                            # 384
ZINTH = ZSLTH - 2 * ZINTY                            # 192

# ⭐ THE VERTICAL WORLD IS EXACTLY TWO ROOMS, AND THAT IS WHAT BUYS THE BANK.
# The view is 240 rows of a 512-row torus, so two parked rows cover 0..479 and
# rows 480..511 are never displayed - 32 rows of VRAM the raster cannot reach.
# A third room row would need the camera to wrap through them.  That is where
# the tile bank, the actor art and the save-behind scratch live.
ZRTILE = 480                  # the tile bank: rows 480..487, 128 tiles a band
ZTPB = ZRINGW // CELLW        # 128 - tiles in one 8-row band

# ⭐ THE KEYED ART BANK: one 16-row strip at ring row ZRART, columns 0 on.
# ⚠ It shares rows 488..503 with the save-behind scratch, which starts at
# column ZCSCR - different columns of the same band.  Neither is ever
# displayed: see ZRTILE above for why those 32 rows are free.
#
# ⛔ A SHAPE IS 32 BYTES WIDE AND 16 ROWS, WHICH IS SQUARE.  The view is
# 640 x 200 shown as 640 x 400, so a VRAM byte is one dot wide and TWO LINES
# tall: art is drawn at 16 x 16 and each art pixel becomes two bytes.  A bank
# of 16-byte shapes would be half as wide as it is tall on the connector.
ZRART = 488                   # rows 488..503, columns 0..511
ZNART = 16                    # 8 hero frames, then 8 of the cast
ZARTW = 32                    # bytes - 16 art pixels
ZARTH = 16
ZCART = 0
ZNHERO = 8                    # slots 0..7: down, up, left, right x 2

# save-behind scratch: one slot an actor, on ring row ZRSCR
ZRSCR = 488                   # ... and the scratch beside it
ZCSCR = 512
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
        sys.exit("FAIL  mkzelda: no %s - run `python3 software/archive/zelda/bench/mkgame.py software/archive/zelda/build` first" % MODEL)
    m = np.load(MODEL)
    return m["tiles"], m["world"], m["sprites"], int(m["key"])


def c332(r, g, b):
    """RGB332, the byte the card's LUT is loaded with for this game.

    ⛔ NEVER 0, because 0 is the copy engine's transparent key: a drawn colour
    that quantises to it would be a HOLE in the shape.  1 is the next index
    up - (0, 0, 85), which is as near black as this palette gets."""
    v = ((r >> 5) << 5) | ((g >> 5) << 2) | (b >> 6)
    return v if v else 1


def tile_bank(tiles, used):
    """The tile bank as a VRAM strip: 8 rows, bank entry n at columns n*8.

    ⛔ ONLY THE TILES THE ROOMS ACTUALLY NAME, renumbered.  mkgame's bank is
    256 entries and the overworld draws 53 of them; a band is 1024/8 = 128
    columns wide, so the full bank would not fit in the eight rows that are
    off the raster and the compacted one fits twice over.

    ⚠ A tile's pixel (r, c) is `tiles[n, r*8 + c]` - graphics.md §6.4.1's
    concatenation, which is why mkgame's tiles.bin IS a VRAM image.  Here they
    are laid side by side so the copy engine can take one as a rectangle.
    ⭐ AND THE WORLD'S OWN ZEROS MOVE UP ONE, so that LUT entry 0 can be BRIGHT
    MAGENTA and mean something: nothing in the scene is index 0 afterwards, so
    magenta on the connector is a leak and only a leak - a keyed copy that
    wrote a hole, or a rectangle nobody painted.
    """
    if len(used) > ZTPB:
        sys.exit("FAIL  mkzelda: %d tiles is more than one %d-tile band"
                 % (len(used), ZTPB))
    t = tiles.astype(np.uint8).copy()
    t[t == 0] = 1
    strip = np.zeros((CELLH, ZRINGW), np.uint8)
    cells = t.reshape(-1, CELLH, CELLW)
    for i, n in enumerate(used):
        strip[:, i * CELLW:(i + 1) * CELLW] = cells[n]
    return strip


def wall_tile(tiles, world):
    """The FOREST - the greenest tile the world actually draws.

    ⛔ EVERY ROOM'S OUTER EIGHT CELLS ARE THIS ONE and nothing else, because
    the view shows 64 columns of the NEIGHBOUR slot at each edge: the seam is
    invisible only while the two walls are the same pixels.
    ⚠ The first cut took the commonest tile on the original map's own border,
    which is SAND - so the rooms were walled in the colour of their floor and
    the border did not exist.  It has to be a tile that reads as a wall,
    because the 24 rows at the top of it are also what keeps every actor out of
    the rows the beam reaches before the actor pass can finish."""
    a = tiles[np.unique(world)].astype(np.int32)
    g = ((a >> 2) & 7).mean(axis=1) / 7.0
    r = (a >> 5).mean(axis=1) / 7.0
    b = (a & 3).mean(axis=1) / 3.0
    return int(np.unique(world)[np.argmax(g - r - b)])


def rooms(tiles, world):
    """`ZNROOM` maps of ZRMCW x ZRMCH cells, walls forced.

    Room (rc, rr) is the world's cells [rr*30 .. ) x [rc*64 .. ), which is why
    the world has to be at least ZWLDW*ZRMCW by ZWLDH*ZRMCH."""
    need = (ZWLDH * ZRMCH, ZWLDW * ZRMCW)
    if world.shape[0] < need[0] or world.shape[1] < need[1]:
        sys.exit("FAIL  mkzelda: the world is %s, too small for %s" % (world.shape, need))
    w = wall_tile(tiles, world)
    out = []
    for rr in range(ZWLDH):
        for rc in range(ZWLDW):
            m = world[rr * ZRMCH:(rr + 1) * ZRMCH,
                      rc * ZRMCW:(rc + 1) * ZRMCW].astype(np.uint8).copy()
            m[:ZWCY] = w
            m[-ZWCY:] = w
            m[:, :ZWCX] = w
            m[:, -ZWCX:] = w
            out.append(m)
    return out, w


# ⛔ FOUR CREATURES A ROOM, AND THE NUMBER IS DERIVED AND NOT CHOSEN.
# `Actors` draws in ascending screen row and the pass starts at the blank, so
# the actor at sorted rank k is written at ~186*(3k+5) us and the beam reaches
# picture row Y at 1430 + 63.56*Y us (VMODE 01: 45 blanked lines of 525, a
# 31.78 us line, and two lines to a VRAM row).  Rank 3 is therefore safe above
# row 18.5 and the hero - drawn last, at 186*(3N+3) - above row 21.4.  ⭐ THE
# TOP WALL IS 24 ROWS, so every actor in every room clears both by
# construction.  A fifth creature needs row 27.3 and the wall would have to
# grow with it.
ZMAXCR = 4

# ⚠ AND THE WANDER BOX IS WHAT MAKES FOUR OF THEM DISJOINT.  `Actors`
# interleaves restore/save/draw per creature, which is correct only while no
# creature's rectangle can reach another's: a save that sees a neighbour paints
# it back as a ghost when its owner moves off.  `CastMv` allows ZWANDER either
# side in x and HALF that in y - a VRAM row is two connector lines, so the same
# number of rows is twice the distance - so a box is
# [HX-48, HX+80] x [HY-24, HY+40], 128 x 64.  The four homes are 224 columns
# and 128 rows apart and the boxes clear the interior's own edges:
#     x [64,192] [288,416]   within the interior's 64..447
#     y [24, 88] [152,216]   within its 24..216
ZWANDER = 48
HOMES = [(ZINTX + 48, ZINTY + 24), (ZINTX + 272, ZINTY + 24),
         (ZINTX + 48, ZINTY + 152), (ZINTX + 272, ZINTY + 152)]
PROPS = [(ZINTX + 144, ZINTY + 80), (ZINTX + 184, ZINTY + 80)]


def actors():
    """Per room: `ZMAXCR` creatures on the fixed grid above, then two props.

    ⭐ The KINDS vary with the room and the counts do not - which is the whole
    point of the room model.  A room is data, and the data cannot ask for more
    draw time than the budget above allows."""
    creat = [0, 2]                      # ZNHERO+0 octorok, +2 moblin
    prop = [4, 5, 6, 7]                 # rupee, heart, bush, rock
    out = []
    for r in range(ZNROOM):
        a = []
        for i, (x, y) in enumerate(HOMES):
            a.append((ZNHERO + creat[(r + i) % len(creat)], 2, x, y))
        for i, (x, y) in enumerate(PROPS):
            a.append((ZNHERO + prop[(r * 2 + i) % len(prop)], 1, x, y))
        out.append(a)
    return out


# ⭐ THE TOUR: eight rooms, every one of them, and back where it started.  The
# hero walks the direction the tour asks for until the interior's edge, and the
# edge is what asks for the next room.  ⚠ hdir is 0 down, 1 up, 2 left, 3 right
# - the art bank's order.
TOUR = [3, 3, 3, 0, 2, 2, 2, 1]


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


# ⭐ THE SLIDE.  512 columns at 8 a frame is 64 frames; 240 rows at 5 is 48.
# At VMODE 01's 59.94 Hz that is 1.07 s and 0.80 s - the NES's own pace.
ZHSTEP, ZNSLH = 8, ZSLTW // 8
ZVSTEP, ZNSLV = 5, ZSLTH // 5

DAT = """\
********************************************************************
* zeldadat.asm - GENERATED by arm6309 software/archive/zelda/bench/mkzelda.py.  Do not edit.
*
* ⛔ INCLUDED BEFORE THE CODE, so every equate is a BACKWARD reference and an
* 8-bit immediate is chosen as one - the same rule monsterdat.asm's header
* records, and for the same reason.
********************************************************************

ZRINGW              equ       {ZRINGW}     the framebuffer torus
ZRINGH              equ       {ZRINGH}
ZVW                 equ       {ZVW}      the view - VMODE 01, shown 640 x 480
ZVH                 equ       {ZVH}
ZSLTW               equ       {ZSLTW}      one room slot in the ring
ZSLTH               equ       {ZSLTH}
ZCELL               equ       {CELLW}
ZRMCW               equ       {ZRMCW}       a room, in cells
ZRMCH               equ       {ZRMCH}
ZRMSZ               equ       ZRMCW*ZRMCH
ZWCX                equ       {ZWCX}        the wall, in cells
ZWCY                equ       {ZWCY}
ZWLDW               equ       {ZWLDW}        the world, in ROOMS
ZWLDH               equ       {ZWLDH}
ZNROOM              equ       {ZNROOM}

ZINTX               equ       {ZINTX}       the interior, slot-relative
ZINTY               equ       {ZINTY}
ZINTW               equ       {ZINTW}
ZINTH               equ       {ZINTH}

* ⛔ THE CAMERA PARKS 64 COLUMNS LEFT OF THE SLOT, so the view straddles it:
* 64 columns of the left neighbour's wall, the room, 64 of the right's.
ZPARK0              equ       {ZPARK0}      HSCROLL for slot column 0
ZPARK1              equ       {ZPARK1}      ... and for slot column 1
ZHSTEP              equ       {ZHSTEP}        the slide
ZNSLH               equ       {ZNSLH}
ZVSTEP              equ       {ZVSTEP}
ZNSLV               equ       {ZNSLV}

ZRTILE              equ       {ZRTILE}      the tile bank: rows 480..487
ZTPB                equ       {ZTPB}       tiles in one band
ZNTILE              equ       {ZNTILE}

ZRART               equ       {ZRART}      the keyed art bank
ZCART               equ       {ZCART}
ZNART               equ       {ZNART}
ZARTW               equ       {ZARTW}
ZARTH               equ       {ZARTH}

ZRSCR               equ       {ZRSCR}      save-behind: one slot an actor
ZCSCR               equ       {ZCSCR}
ZMXAC               equ       {ZMXAC}
ZSCRP               equ       {ZSCRP}

ZKEY                equ       ${KEY:02X}      mkgame.py's transparent byte
ZNHERO              equ       {ZNHERO}        the hero's frames, slots 0..7
ZMAXCR              equ       {ZMAXCR}        creatures a room - the draw budget
ZNRACT              equ       {ZNRACT}        ... and the props after them
ZWANDER             equ       {ZWANDER}       how far a creature leaves home

* ⭐ THE TOUR - every room once, and home.  0 down, 1 up, 2 left, 3 right.
TourTab             fcb       {TOURB}
TourN               equ       *-TourTab

* RoomAct - ZNRACT entries a room: art slot, frames (2 walks, 1 scenery),
* and the home, SLOT-RELATIVE.
RoomAct
{ACT}
ZRAENT              equ       6

* ⛔ RoomMap - ZNROOM maps of ZRMCW x ZRMCH cells.  The outer ZWCX columns and
* ZWCY rows of every one of them are the SAME wall tile: the view shows 64
* columns of the neighbouring slot, so the walls have to agree or the seam is
* a visible join.
RoomMap
{MAP}
"""


def main(cmds):
    d = pathlib.Path(__file__).resolve().parent
    out = str(d)
    a = pathlib.Path(cmds)
    a.mkdir(parents=True, exist_ok=True)
    tiles, world, sprites, key = load()

    maps, wtile = rooms(tiles, world)
    used = sorted(set(int(v) for m in maps for v in m.reshape(-1)))
    ix = {n: i for i, n in enumerate(used)}
    maps = [np.vectorize(ix.get)(m).astype(np.uint8) for m in maps]
    acts = actors()

    bank = tile_bank(tiles, used)
    (d / "zelda.bnk").write_bytes(bank.tobytes())

    art = art_bank(tiles, world)
    (d / "zelda.art").write_bytes(art)

    def fcb(b):
        return "\n".join("                    fcb       "
                          + ",".join(str(int(v)) for v in b[k:k + 16])
                          for k in range(0, len(b), 16))

    mtxt = "\n".join("* room %d\n%s" % (i, fcb(m.reshape(-1)))
                      for i, m in enumerate(maps))
    atxt = "\n".join(
        "* room %d\n" % i + "\n".join(
            "                    fcb       %d,%d\n"
            "                    fdb       %d,%d" % e for e in ent)
        for i, ent in enumerate(acts))

    (a / "zeldadat.asm").write_text(DAT.format(
        ZRINGW=ZRINGW, ZRINGH=ZRINGH, ZVW=ZVW, ZVH=ZVH,
        ZSLTW=ZSLTW, ZSLTH=ZSLTH, CELLW=CELLW, ZRMCW=ZRMCW, ZRMCH=ZRMCH,
        ZWCX=ZWCX, ZWCY=ZWCY, ZWLDW=ZWLDW, ZWLDH=ZWLDH, ZNROOM=ZNROOM,
        ZINTX=ZINTX, ZINTY=ZINTY, ZINTW=ZINTW, ZINTH=ZINTH,
        ZPARK0=(0 - ZINTX) % ZRINGW, ZPARK1=(ZSLTW - ZINTX) % ZRINGW,
        ZHSTEP=ZHSTEP, ZNSLH=ZNSLH, ZVSTEP=ZVSTEP, ZNSLV=ZNSLV,
        ZRTILE=ZRTILE, ZTPB=ZTPB, ZNTILE=len(used),
        ZRART=ZRART, ZCART=ZCART, ZNART=ZNART, ZARTW=ZARTW, ZARTH=ZARTH,
        ZRSCR=ZRSCR, ZCSCR=ZCSCR, ZMXAC=ZMXAC, ZSCRP=ZSCRP,
        KEY=KEY, ZNHERO=ZNHERO, ZMAXCR=ZMAXCR, ZNRACT=len(acts[0]),
        ZWANDER=ZWANDER, TOURB=",".join(str(v) for v in TOUR),
        ACT=atxt, MAP=mtxt))

    print("ok    %s/zelda.bnk: %d tiles of %d, %d x %d bytes"
          % (out, len(used), tiles.shape[0], ZRINGW, CELLH))
    print("ok    %s/zelda.art: %d keyed shapes of %d x %d, %d bytes"
          % (out, ZNART, ZARTW, ZARTH, len(art)))
    print("ok    %s/zeldadat.asm: %d rooms of %d x %d cells (wall tile %d), "
          "%d actors a room" % (a, ZNROOM, ZRMCW, ZRMCH, wtile, len(acts[0])))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else str(ROOT.parent / "nitros9" / "level2" / "arm6309" / "cmds"))
