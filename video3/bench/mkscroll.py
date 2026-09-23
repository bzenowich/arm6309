#!/usr/bin/env python3
"""mkscroll.py [CMDSDIR] - a 32 x 32 TILE BANK, a world map, and the equates.

    python3 video3/bench/mkscroll.py ../nitros9/level2/arm6309/cmds

⭐⭐ WHAT THIS IS FOR.  `zelda` draws a ROOM: the creatures freeze, the next
room is composed into the far half of the ring and slid in.  That bounds the
actor count, which is what it was for, but the world can only ever be a grid of
screens.  This is the other design - a camera that roams a world of any size
with the hero in the middle of it - and it is the one this card was shaped for.

⛔ THE WHOLE THING TURNS ON ONE FACT: the ring is 1024 x 512 and the view is
640 x 480, so there is ALWAYS a 384 x 512 rectangle of VRAM the raster is not
looking at - and it moves with the camera.  Put the tile bank in it and the
bank is hidden for free; scroll horizontally and the bank walks into view,
unless the bank walks out of the way at the same rate.  ⭐ That is the engine:
the bank is nine 32-column strips that ROTATE round the ring as the camera
moves, and the strip they vacate is where the next column of world is drawn.

    ring columns, relative to the camera at HSCROLL = h

      0                             640    704              992   1024
      |------------ view ------------|-marg-|---- bank 9 ----|-marg-|
      \\_____________________________________/                \\______/
            terrain: world columns wx-32 .. wx+704             ... and the
                                                               other margin

A margin slot at each end is what makes it work in BOTH directions: the slot
the camera is about to need is already terrain, and the work to refill it has a
whole 32 pixels of travel to happen in.  Without it the newly-freed strip is
visible the instant HSCROLL moves one pixel.

⚠ VERTICALLY THERE IS NO SLOT TO SPARE - the view is 480 rows of 512, so the
16 row-slots of a 32-pixel tile are all of them.  The vertical axis streams in
HALF-tile bands of 16 rows instead, which is what the 32 spare rows will hold.

The files:

    scroll.bnk    288 x 512 bytes - 9 columns x 16 rows of 32 x 32 tiles
    scroll.art    the keyed actor bank, one 32-row strip
    scrolldat.asm every equate the program and this file share, and the map
"""
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]

# ⛔ THE GEOMETRY.  Every number here is in scrolldat.asm too; the program
# reads none of them from a file.
ZRINGW, ZRINGH = 1024, 512    # the framebuffer torus
ZVW, ZVH = 640, 480           # the view - VMODE 11, and square pixels at last
ZTILE = 32                    # a tile, and the horizontal streaming quantum
ZSLOTS = ZRINGW // ZTILE      # 32 column slots in the ring
ZVSLOT = ZVW // ZTILE + 1     # 21 - the slots a 640-wide view can touch
ZTSLOT = ZVSLOT + 2           # 23 - ... and one margin slot at each end
ZBCOL = ZSLOTS - ZTSLOT       # 9 - what is left is the bank
ZBROW = ZRINGH // ZTILE       # 16 tiles up a bank column
ZNTILE = ZBCOL * ZBROW        # 144 tiles, and the budget is ~70

# ⚠ THE VERTICAL BAND IS HALF A TILE.  16 rows x 23 slots is 23 copies of
# 32 x 16 - 4.3 ms per 16 rows of travel, where whole 32-row bands would need
# all 32 spare rows and leave no margin at all.
ZVBAND = 16
ZVMARG = ZVBAND               # terrain is valid for world rows wy-16 .. wy+496

# the world, in tiles - a torus, so the camera never reaches an edge
ZWLDW, ZWLDH = 128, 64

# the keyed actor bank: one 32-row strip beside the tile bank is not possible
# (the bank rotates), so it goes in the 32 rows the vertical stream keeps
# ⚠ ... which it cannot either.  The art rides in the BANK, as tiles: the
# last bank column is art rather than terrain, and it rotates with the rest.
ZART0 = ZNTILE - 16           # the last column of the bank is the actors
ZNART = 16

KEY = 0x00                    # the copy engine's colour key is index 0


def c332(r, g, b):
    """RGB332, and never 0 - index 0 is the copy engine's transparent key, so a
    drawn colour that quantised to it would be a HOLE in the shape."""
    v = ((r >> 5) << 5) | ((g >> 5) << 2) | (b >> 6)
    return v if v else 1


class Rnd:
    """⚠ ITS OWN GENERATOR, because the bench compares VRAM byte for byte and
    numpy's default seeding is not a promise across versions."""

    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFF

    def u32(self):
        self.s = (1664525 * self.s + 1013904223) & 0xFFFFFFFF
        return self.s

    def f(self):
        return self.u32() / 4294967296.0

    def i(self, n):
        # ⛔ THE TOP BITS, NOT THE BOTTOM ONES.  A power-of-two LCG's low k bits
        # have period 2^k, so `u32() % 16` cycles through sixteen values in
        # lockstep with whatever else consumes the generator.  Scattering the
        # decorations that way put ONE tree on a screen where seventeen were
        # asked for, and seventeen flowers beside it.  `zelda`'s creatures stopped
        # moving for the same reason (optimizations.md §11) - twice in one week.
        return (self.u32() >> 13) % n


# --------------------------------------------------------------------------
# ⭐ THE TILESET.  Four terrains, and three of them are OVERLAYS painted on to
# grass with their edges eroded wherever the neighbour in that direction is
# something else.  A tile is therefore (terrain, 4-bit mask of which cardinal
# neighbours match), which is 16 tiles a terrain and gives a rounded blob edge
# without the 256 cases a corner-indexed set would need.
# ⛔ FOREST AND NOT ROCK, and the reason is the palette.  RGB332 keeps three
# bits of red, three of green and TWO of blue, so there is no grey in it: every
# stone colour tried quantised to mauve or khaki.  A dark forest is three
# bits of green against grass's four and reads at a glance.
GRASS, SAND, WATER, FOREST = 0, 1, 2, 3
NTERR = 4
OVER = (SAND, WATER, FOREST)
# ⚠ AND THE INTERIOR GETS VARIANTS.  A region is almost all mask-15 tiles, so
# one of them repeating on a 32-pixel lattice is what the eye finds first.
NVAR = 3

# masks: bit 0 north, 1 east, 2 south, 3 west
NORTH, EAST, SOUTH, WEST = 1, 2, 4, 8


def base_tile(kind, rnd):
    """A full 32 x 32 of one terrain, with its own grain."""
    a = np.empty((ZTILE, ZTILE), np.uint8)
    if kind == GRASS:
        lo, hi = (44, 110, 44), (78, 165, 62)
    elif kind == SAND:
        lo, hi = (206, 180, 126), (240, 216, 166)
    elif kind == WATER:
        lo, hi = (30, 70, 170), (60, 120, 224)
    else:
        lo, hi = (18, 62, 26), (34, 96, 34)
    c0, c1 = c332(*lo), c332(*hi)
    for y in range(ZTILE):
        for x in range(ZTILE):
            a[y, x] = c1 if rnd.i(7) == 0 else c0
    if kind == WATER:
        # ⚠ horizontal wave lines, so water reads as water at a glance
        for y in range(2, ZTILE, 7):
            for x in range(rnd.i(6), ZTILE, 2):
                a[y, x] = c332(120, 180, 255)
    if kind == FOREST:
        # ⚠ canopies, not streaks: a blob with a lit top left and a dark
        # underside, so a wood reads as depth rather than as texture
        for _ in range(5):
            cx, cy, r = 4 + rnd.i(24), 4 + rnd.i(24), 5 + rnd.i(3)
            for y in range(-r, r + 1):
                for x in range(-r, r + 1):
                    if x * x + y * y > r * r:
                        continue
                    py, px = (cy + y) % ZTILE, (cx + x) % ZTILE
                    a[py, px] = (c332(60, 140, 54) if (x + y) < -r // 2
                                 else c332(10, 44, 18) if (x + y) > r // 2
                                 else c332(34, 92, 36))
    return a


def erode(mask, side, rnd):
    """Pull `mask` back from one edge with an irregular boundary.

    ⭐ The depth wanders between 4 and 9 pixels, which is what stops a blob
    looking like a rounded rectangle."""
    d = 6
    for i in range(ZTILE):
        d = max(4, min(9, d + rnd.i(3) - 1))
        if side == NORTH:
            mask[:d, i] = False
        elif side == SOUTH:
            mask[ZTILE - d:, i] = False
        elif side == WEST:
            mask[i, :d] = False
        else:
            mask[i, ZTILE - d:] = False


def overlay_tile(kind, m, rnd):
    """Terrain `kind` over grass, eroded on every side the mask does not have.

    ⚠ The erosions are applied to ONE shared mask, so two adjacent open sides
    round the corner between them off rather than meeting at a right angle."""
    g = base_tile(GRASS, rnd)
    t = base_tile(kind, rnd)
    keep = np.ones((ZTILE, ZTILE), bool)
    for side in (NORTH, EAST, SOUTH, WEST):
        if not (m & side):
            erode(keep, side, rnd)
    out = g.copy()
    out[keep] = t[keep]
    return out


# ⭐ DECORATIONS are drawn INTO a grass tile rather than given a terrain of
# their own: a tree is not something the map has to autotile against, it is
# scenery, and scenery on its own tile is how a world starts looking like
# wallpaper.
def deco_tree(a, rnd):
    """⚠ IT HAS TO CONTRAST WITH THE GRASS IT STANDS ON.  The first cut drew a
    canopy one step greener than the field and the trees were invisible in the
    render - which is the whole reason to look at a contact sheet before
    writing any of the program that uses the art."""
    cx, cy = 16, 12
    a[cy + 7:cy + 15, cx - 2:cx + 2] = c332(92, 56, 24)
    a[cy + 14:cy + 16, cx - 5:cx + 5] = c332(20, 50, 20)      # its shadow
    for y in range(-10, 9):
        for x in range(-11, 12):
            if x * x * 0.62 + y * y * 1.1 < 84:
                a[cy + y, cx + x] = (c332(14, 52, 20) if (x + y) > 6
                                     else c332(24, 84, 30))
    for y in range(-10, 4):
        for x in range(-11, 6):
            if x * x * 0.62 + y * y * 1.1 < 46 and (x + y) < -2:
                a[cy + y, cx + x] = c332(70, 168, 62)


def deco_flowers(a, rnd):
    for _ in range(7):
        x, y = 3 + rnd.i(26), 3 + rnd.i(26)
        col = (c332(240, 230, 90), c332(240, 120, 180), c332(250, 250, 250))[rnd.i(3)]
        a[y, x] = col
        a[y, x + 1] = col
        a[y + 1, x] = col
        a[y + 1, x + 1] = col


def deco_stones(a, rnd):
    for _ in range(5):
        x, y = 3 + rnd.i(24), 3 + rnd.i(24)
        w, h = 3 + rnd.i(3), 2 + rnd.i(2)
        a[y:y + h, x:x + w] = c332(130, 124, 120)
        a[y + h - 1:y + h, x:x + w] = c332(86, 82, 80)


DECOS = (deco_tree, deco_flowers, deco_stones)


def tileset():
    """The bank, and the index every (terrain, mask) pair sits at.

    Layout, and `TileIx` in scrolldat.asm is the same table:
        0..3     grass, four grains
        4..6     grass with a tree, with flowers, with stones
        7..54    the three overlays, sixteen masks each
    """
    rnd = Rnd(0x5EED1)
    tiles, index = [], {}
    for i in range(4):
        tiles.append(base_tile(GRASS, rnd))
    for d in DECOS:
        a = base_tile(GRASS, rnd)
        d(a, rnd)
        tiles.append(a)
    for kind in OVER:
        for m in range(16):
            index[(kind, m)] = len(tiles)
            tiles.append(overlay_tile(kind, m, rnd))
        # the interior again, twice, with a different grain each time
        index[(kind, 'v')] = len(tiles)
        for _ in range(NVAR - 1):
            tiles.append(overlay_tile(kind, 15, rnd))
    return tiles, index


# --------------------------------------------------------------------------
# ⭐ THE WORLD.  Value noise at two scales picks the terrain, then each tile's
# index is its terrain and the 4-bit mask of which cardinal neighbours match.
# ⚠ THE MAP IS A TORUS, so the noise has to wrap: it is sampled on a lattice
# whose period is the map size, and the camera then never meets an edge.
def noise(w, h, period, rnd):
    g = np.array([[rnd.f() for _ in range(period)] for _ in range(period)])
    ys = np.arange(h) * period / h
    xs = np.arange(w) * period / w
    y0 = ys.astype(int) % period
    x0 = xs.astype(int) % period
    y1 = (y0 + 1) % period
    x1 = (x0 + 1) % period
    fy = (ys - ys.astype(int))[:, None]
    fx = (xs - xs.astype(int))[None, :]
    fy = fy * fy * (3 - 2 * fy)
    fx = fx * fx * (3 - 2 * fx)
    a = g[np.ix_(y0, x0)] * (1 - fx) + g[np.ix_(y0, x1)] * fx
    b = g[np.ix_(y1, x0)] * (1 - fx) + g[np.ix_(y1, x1)] * fx
    return a * (1 - fy) + b * fy


def world(index):
    rnd = Rnd(0xC0FFEE)
    n = (noise(ZWLDW, ZWLDH, 8, rnd) * 0.65
         + noise(ZWLDW, ZWLDH, 17, rnd) * 0.35)
    terr = np.full((ZWLDH, ZWLDW), GRASS, np.uint8)
    terr[n < 0.36] = WATER
    terr[(n >= 0.36) & (n < 0.44)] = SAND
    terr[n > 0.70] = FOREST
    out = np.empty((ZWLDH, ZWLDW), np.uint8)
    dec = Rnd(0xDEC0)
    for y in range(ZWLDH):
        for x in range(ZWLDW):
            t = terr[y, x]
            if t == GRASS:
                r = dec.i(24)
                out[y, x] = 4 + (r - 1) if 1 <= r <= 3 else dec.i(4)
                continue
            m = 0
            if terr[(y - 1) % ZWLDH, x] == t:
                m |= NORTH
            if terr[y, (x + 1) % ZWLDW] == t:
                m |= EAST
            if terr[(y + 1) % ZWLDH, x] == t:
                m |= SOUTH
            if terr[y, (x - 1) % ZWLDW] == t:
                m |= WEST
            if m == 15:
                v = dec.i(NVAR)
                out[y, x] = index[(t, 15)] if v == 0 else index[(t, 'v')] + v - 1
            else:
                out[y, x] = index[(t, m)]
    return out, terr


def bank(tiles):
    """9 columns of 16 tiles: tile n at column n // 16, row n % 16."""
    if len(tiles) > ZNTILE:
        sys.exit("FAIL  mkscroll: %d tiles is more than the bank's %d"
                 % (len(tiles), ZNTILE))
    strip = np.zeros((ZRINGH, ZBCOL * ZTILE), np.uint8)
    for n, t in enumerate(tiles):
        if t is None:
            continue
        c, r = n // ZBROW, n % ZBROW
        strip[r * ZTILE:(r + 1) * ZTILE, c * ZTILE:(c + 1) * ZTILE] = t
    return strip


# --------------------------------------------------------------------------
# ⭐ THE ACTORS RIDE IN THE BANK.  There is nowhere else for them: every row of
# the ring is either terrain or bank, and the bank ROTATES - so a strip of art
# parked at a fixed ring address would walk into view.  The art is the bank's
# last column, sixteen 32 x 32 shapes, and it is looked up exactly as a terrain
# tile is.  ⚠ mkzelda's shapes are 16 x 16 art pixels and this mode's pixels
# are SQUARE, so they double in both axes rather than one.
def art_bank():
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import mkzelda as Z
    shapes = Z.hero_art()
    for name, pal, rows in Z.CAST:
        lut = {k: Z.c332(*v) for k, v in pal.items()}
        a = np.full((16, 16), KEY, np.uint8)
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                if ch in lut:
                    a[r, c] = lut[ch]
        shapes.append(a)
    assert len(shapes) == ZNART, len(shapes)
    out = []
    for a in shapes:
        big = np.repeat(np.repeat(a, 2, axis=0), 2, axis=1)
        assert big.shape == (ZTILE, ZTILE)
        assert (big == KEY).any(), "a shape with no transparent pixel"
        out.append(big)
    return out


DAT = """\
********************************************************************
* scrolldat.asm - GENERATED by arm6309 video3/bench/mkscroll.py.  Do not edit.
*
* ⛔ INCLUDED BEFORE THE CODE, so every equate is a BACKWARD reference and an
* 8-bit immediate is chosen as one.
********************************************************************

ZRINGW              equ       {ZRINGW}     the framebuffer torus
ZRINGH              equ       {ZRINGH}
ZHMSK               equ       ZRINGW-1   the camera wraps by masking
ZVMSK               equ       ZRINGH-1
ZVW                 equ       {ZVW}      the view - VMODE 11, and square pixels
ZVH                 equ       {ZVH}
ZTILE               equ       {ZTILE}
ZSLOTS              equ       {ZSLOTS}       32-column slots in the ring
ZSMSK               equ       ZSLOTS-1
ZVSLOT              equ       {ZVSLOT}       slots a 640-wide view can touch
ZTSLOT              equ       {ZTSLOT}       ... and one margin slot each side
ZBCOL               equ       {ZBCOL}        what is left is the bank
ZBROW               equ       {ZBROW}
ZNTILE              equ       {ZNTILE}

ZVBAND              equ       {ZVBAND}       the vertical stream's quantum
ZWLDW               equ       {ZWLDW}      the world, in TILES - a torus
ZWLDH               equ       {ZWLDH}
ZWXMSK              equ       ZWLDW-1
ZWYMSK              equ       ZWLDH-1

ZART0               equ       {ZART0}      the bank's last column is the actors
ZNART               equ       {ZNART}
ZKEY                equ       ${KEY:02X}

* ⭐ THE BANK STARTS AT SLOT ZBK0 and runs ZBCOL slots.  At wx = 0 the terrain
* window is world slots -1..21, which is ring slots 31 and 0..21, so the bank
* has ring slots 22..30 - exactly the 288 columns scroll.bnk is wide.
ZBK0                equ       {ZBK0}

* WorldMap - ZWLDH rows of ZWLDW tile indices.  ⚠ BOTH DIMENSIONS ARE POWERS
* OF TWO, so a world tile is (ty & ZWYMSK) * ZWLDW + (tx & ZWXMSK) and the
* torus costs two ANDs rather than two divisions.
WorldMap
{MAP}
"""


def main(cmds):
    d = pathlib.Path(__file__).resolve().parent
    a = pathlib.Path(cmds)
    a.mkdir(parents=True, exist_ok=True)
    tiles, index = tileset()
    m, terr = world(index)
    art = art_bank()
    all_tiles = list(tiles) + [None] * (ZART0 - len(tiles)) + art
    b = bank(all_tiles)
    (d / "scroll.bnk").write_bytes(b.tobytes())

    def fcb(v):
        return "\n".join("                    fcb       "
                          + ",".join(str(int(x)) for x in v[k:k + 16])
                          for k in range(0, len(v), 16))

    (a / "scrolldat.asm").write_text(DAT.format(
        ZRINGW=ZRINGW, ZRINGH=ZRINGH, ZVW=ZVW, ZVH=ZVH, ZTILE=ZTILE,
        ZSLOTS=ZSLOTS, ZVSLOT=ZVSLOT, ZTSLOT=ZTSLOT, ZBCOL=ZBCOL,
        ZBROW=ZBROW, ZNTILE=ZNTILE, ZVBAND=ZVBAND, ZWLDW=ZWLDW, ZWLDH=ZWLDH,
        ZART0=ZART0, ZNART=ZNART, KEY=KEY, ZBK0=ZTSLOT - 1,
        MAP="\n".join("* row %d\n%s" % (y, fcb(m[y])) for y in range(ZWLDH))))
    print("ok    %s/scroll.bnk: %d terrain + %d art of %d slots, %d x %d bytes"
          % (d, len(tiles), len(art), ZNTILE, b.shape[1], b.shape[0]))
    print("ok    %s/scrolldat.asm: map %d x %d tiles, bank at ring slot %d"
          % (a, ZWLDW, ZWLDH, ZTSLOT - 1))
    print("ok    world %d x %d tiles = %d x %d pixels; terrain mix %s"
          % (ZWLDW, ZWLDH, ZWLDW * ZTILE, ZWLDH * ZTILE,
             {k: int((terr == v).sum()) for k, v in
              (("grass", GRASS), ("sand", SAND), ("water", WATER), ("forest", FOREST))}))
    return tiles, index, m, terr


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else str(ROOT.parent / "nitros9" / "level2" / "arm6309" / "cmds"))
