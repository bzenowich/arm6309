#!/usr/bin/env python3
"""mkpcbt.py - the pinball table as a 640 x 1280 TILED playfield, still a PCB.

    python3 video3/bench/mkpcbt.py [CMDSDIR]

⭐⭐ WHY THIS REPLACES mkpcb.py's PICTURE.  `pinball` used to read a
640 x 512 picture off the card - 327,680 bytes - and the whole table fitted
inside the ring, so nothing streamed.  A 640 x 1280 table does not fit, and
the scene now links against `tscroll.inc`, which wants a TILE BANK and a MAP.

⛔ AND THAT IS WHY THE ART IS AUTHORED AND NOT DITHERED.  mkpcb.py draws the
board and then Floyd-Steinbergs it into 205 colours; every 32 x 32 block of
the result is unique, so a bank cut from it would need eight hundred tiles
where the ring has room for a hundred and twenty-eight.  This file authors a
VOCABULARY of 32 x 32 motifs - substrate, trace, pad, wall, chip, target,
slingshot, lane, drain - and lays the table out as a grid of them, which is
the same thing a real board's silkscreen does.

The files, beside this one:

    pcbt.bnk    256 x 512 bytes - 8 columns x 16 rows of 32 x 32 tiles
    pcbt.pal    512 bytes - 256 big-endian RGB565 words, lamps and segments
                loaded UNLIT, exactly as mkpcb.py's
    pcbt.png    a 1:1 preview of the whole table with every lamp lit
    pcbtdat.asm the geometry, the map and the collision map, as equates

⚠ THE PALETTE'S THREE TENANTS ARE mkpcb.py's, unchanged: art 1..205, eight
lamps at 206..213, six seven-segment digits at 214..255.  The scene's lamp and
scoreboard code is palette writes and nothing else, so it carries over intact.
"""
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]

# ── the ring, and what of it this scene uses ────────────────────────────────
ZTILE = 32
ZRINGW, ZRINGH = 1024, 512
ZVW, ZVH = 640, 480               # VMODE 11
# ⛔ THE TABLE DOES NOT SCROLL SIDEWAYS, so the terrain window does not need a
# margin at each end and the bank can have what is left.  24 slots of terrain
# (768 columns, of which the table is the first 640) and 8 of bank.
ZTSLOT, ZBCOL = 24, 8
ZSLOTS = ZRINGW // ZTILE          # 32
ZBROW = ZRINGH // ZTILE           # 16
ZNTILE = ZBCOL * ZBROW            # 128
ZBK0 = ZTSLOT - 1                 # the bank's first ring slot: 23
ZVBAND = 16

# ── the table, in tiles and in cells ───────────────────────────────────────
TW, TH = 20, 40                   # 640 x 1280
ZWLDW, ZWLDH = 32, 64             # ⚠ the MAP is a power of two in both axes
CELL = 16                         # the collision grid, as mkpcb.py's
CW, CH = TW * ZTILE // CELL, TH * ZTILE // CELL       # 40 x 80

ZART0 = 64                        # bank column 4: the ball and the flippers
ZNART = 16
ZSCR0 = 96                        # column 6: the actors' save-behind
ZMXAC = 8

# ── the palette's three tenants (mkpcb.py's split, unchanged) ──────────────
NLAMP, NDIG = 8, 6
NSEG = NDIG * 7
NART = 255 - NLAMP - NSEG         # 205
LAMP0 = 1 + NART                  # 206
SEG0 = LAMP0 + NLAMP              # 214
assert SEG0 + NSEG == 256

# ── the collision kinds, mkpcb.py's, and for its reasons ───────────────────
KINDS = {"empty": 0, "solid": 1, "slope_r": 2, "slope_l": 3, "bumper": 4,
         "target": 5, "rollover": 6, "kicker": 7, "drain": 8, "flip_l": 9,
         "flip_r": 10, "return": 11, "plunger": 12}

# ── the art's own colours.  ⚠ AUTHORED, so there are forty of them and not
# two hundred, and each is placed rather than searched for.
C = {}


def add(name, rgb):
    C[name] = (len(C) + 1, rgb)
    assert len(C) <= NART, "more art colours than the palette's 205"


for _n, _c in (
        ("mask0", (14, 56, 30)), ("mask1", (20, 74, 40)), ("mask2", (10, 42, 24)),
        ("weave", (24, 86, 48)),
        ("cu0", (176, 124, 44)), ("cu1", (214, 164, 66)), ("cu2", (128, 86, 28)),
        ("tin0", (176, 180, 190)), ("tin1", (222, 226, 236)), ("tin2", (120, 124, 136)),
        ("silk", (226, 230, 224)), ("silk2", (150, 158, 150)),
        ("hole", (8, 10, 12)),
        ("ic0", (36, 36, 42)), ("ic1", (62, 62, 72)), ("ic2", (18, 18, 22)),
        ("icpin", (198, 200, 210)),
        ("res0", (62, 40, 26)), ("res1", (122, 86, 48)),
        ("red", (206, 54, 40)), ("blue", (54, 96, 206)),
        ("ball0", (236, 240, 250)), ("ball1", (166, 172, 190)), ("ball2", (92, 98, 116)),
        ("flip0", (226, 64, 48)), ("flip1", (150, 32, 24)), ("flip2", (255, 150, 130)),
):
    add(_n, _c)


def canvas(fill="mask0"):
    return np.full((ZTILE, ZTILE), C[fill][0], np.uint8)


class Rnd:
    """⚠ ITS OWN GENERATOR, because the bench compares VRAM byte for byte.
    ⛔ And the TOP bits: a power-of-two LCG's low k bits have period 2^k, which
    put one tree on a screen where seventeen were wanted in mkscroll.py."""

    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFF

    def i(self, n):
        self.s = (1664525 * self.s + 1013904223) & 0xFFFFFFFF
        return (self.s >> 13) % n


def substrate(a, rnd):
    """The solder mask, with the glass weave showing through it."""
    for y in range(ZTILE):
        for x in range(ZTILE):
            if (x + y) % 8 == 0 or (x - y) % 8 == 0:
                a[y, x] = C["weave"][0]
            elif rnd.i(9) == 0:
                a[y, x] = C["mask1"][0]
            elif rnd.i(11) == 0:
                a[y, x] = C["mask2"][0]
    return a


def trace(a, w=6, h=False, v=False, colour="cu0"):
    """A copper run across the tile, with a lighter edge for the etch."""
    m = (ZTILE - w) // 2
    if h:
        a[m:m + w, :] = C[colour][0]
        a[m, :] = C["cu1"][0]
        a[m + w - 1, :] = C["cu2"][0]
    if v:
        a[:, m:m + w] = C[colour][0]
        a[:, m] = C["cu1"][0]
        a[:, m + w - 1] = C["cu2"][0]
    return a


def disc(a, cx, cy, r, colour, edge=None):
    for y in range(max(0, cy - r), min(ZTILE, cy + r + 1)):
        for x in range(max(0, cx - r), min(ZTILE, cx + r + 1)):
            d = (x - cx) ** 2 + (y - cy) ** 2
            if d <= r * r:
                a[y, x] = C[colour][0]
            elif edge and d <= (r + 1) ** 2:
                a[y, x] = C[edge][0]
    return a


# ═══════════════════ THE MOTIFS ════════════════════════════════════════════
# Each is (name, kind for its four 16 x 16 quadrants, a drawing function).
# ⚠ THE KIND IS PER QUADRANT, which is mkpcb.py's 16-pixel collision grid: a
# 32-pixel cell is too coarse for a ball eight pixels across.
MOTIFS = []


def motif(name, kinds, fn):
    MOTIFS.append((name, kinds, fn))
    return len(MOTIFS) - 1


def m_sub(a, r):
    return substrate(a, r)


def m_traceh(a, r):
    return trace(substrate(a, r), h=True)


def m_tracev(a, r):
    return trace(substrate(a, r), v=True)


def m_cross(a, r):
    return trace(trace(substrate(a, r), h=True), v=True)


def m_pad(a, r):
    a = trace(substrate(a, r), v=True)
    disc(a, 16, 16, 9, "cu1", "cu2")
    disc(a, 16, 16, 4, "hole")
    return a


def m_wallv(a, r):
    a = substrate(a, r)
    a[:, 8:24] = C["tin0"][0]
    a[:, 8] = C["tin1"][0]
    a[:, 23] = C["tin2"][0]
    for y in range(2, ZTILE, 8):
        a[y:y + 2, 12:20] = C["tin2"][0]
    return a


def m_wallh(a, r):
    a = substrate(a, r)
    a[8:24, :] = C["tin0"][0]
    a[8, :] = C["tin1"][0]
    a[23, :] = C["tin2"][0]
    for x in range(2, ZTILE, 8):
        a[12:20, x:x + 2] = C["tin2"][0]
    return a


def m_chip(a, r):
    """A DIP package: the bumper.  It scores and it kicks back."""
    a = substrate(a, r)
    a[4:28, 2:30] = C["ic0"][0]
    a[4:6, 2:30] = C["ic1"][0]
    a[26:28, 2:30] = C["ic2"][0]
    for y in range(6, 27, 5):                       # the pins, both sides
        a[y:y + 3, 0:3] = C["icpin"][0]
        a[y:y + 3, 29:32] = C["icpin"][0]
    disc(a, 9, 10, 3, "ic2")                        # the pin-1 dimple
    a[14:16, 10:22] = C["silk2"][0]                 # a silkscreen part number
    return a


def m_targ(a, r):
    """One switch of a DIP-switch bank: a drop target."""
    a = substrate(a, r)
    a[6:26, 4:28] = C["silk"][0]
    a[8:24, 6:26] = C["ic0"][0]
    a[10:22, 9:15] = C["red"][0]
    a[10:22, 17:23] = C["ic1"][0]
    return a


def m_sling(a, r, right):
    """A 45-degree copper face.  ⚠ NAMED BY WHERE IT SENDS A FALLING BALL, not
    by which corner the copper fills - mkpcb.py records getting that pair the
    wrong way round as a funnel that feeds the drain."""
    a = substrate(a, r)
    for y in range(ZTILE):
        for x in range(ZTILE):
            if (x >= y) if right else (x <= ZTILE - 1 - y):
                a[y, x] = C["cu0"][0]
    for i in range(ZTILE):
        x = i if right else ZTILE - 1 - i
        a[i, x] = C["cu1"][0]
    return a


def m_lane(a, r):
    """A row of test pads: it scores, it does not deflect."""
    a = trace(substrate(a, r), h=True)
    for x in (8, 16, 24):
        disc(a, x, 16, 5, "tin0", "tin2")
    return a


def m_drain(a, r):
    """A milled slot through the board."""
    a = substrate(a, r)
    a[:, 6:26] = C["hole"][0]
    a[:, 6] = C["mask2"][0]
    a[:, 25] = C["mask2"][0]
    return a


def m_lamp(a, r, n):
    """A pad drawn in a RESERVED index, so the scene lights it with one
    palette write and no pixels at all."""
    a = trace(substrate(a, r), v=True)
    disc(a, 16, 16, 10, "cu2")
    for y in range(6, 27):
        for x in range(6, 27):
            if (x - 16) ** 2 + (y - 16) ** 2 <= 64:
                a[y, x] = LAMP0 + n
    return a


def m_seg(a, r, d):
    """One digit of the six-digit display: its seven segments are seven
    reserved indices, so the whole number is 42 palette writes."""
    a = substrate(a, r)
    a[2:30, 4:28] = C["ic2"][0]
    s = SEG0 + d * 7
    a[4:7, 9:23] = s                      # a  top
    a[7:15, 20:23] = s + 1                # b  upper right
    a[15:23, 20:23] = s + 2               # c  lower right
    a[23:26, 9:23] = s + 3                # d  bottom
    a[15:23, 9:12] = s + 4                # e  lower left
    a[7:15, 9:12] = s + 5                 # f  upper left
    a[13:16, 9:23] = s + 6                # g  middle
    return a


K = KINDS
M_SUB = motif("sub", (K["empty"],) * 4, m_sub)
M_TH = motif("traceh", (K["empty"],) * 4, m_traceh)
M_TV = motif("tracev", (K["empty"],) * 4, m_tracev)
M_CR = motif("cross", (K["empty"],) * 4, m_cross)
M_PAD = motif("pad", (K["empty"],) * 4, m_pad)
M_WV = motif("wallv", (K["solid"],) * 4, m_wallv)
M_WH = motif("wallh", (K["solid"],) * 4, m_wallh)
M_CHIP = motif("chip", (K["bumper"],) * 4, m_chip)
M_TARG = motif("targ", (K["target"],) * 4, m_targ)
M_SLR = motif("slingr", (K["slope_r"],) * 4, lambda a, r: m_sling(a, r, True))
M_SLL = motif("slingl", (K["slope_l"],) * 4, lambda a, r: m_sling(a, r, False))
M_LANE = motif("lane", (K["rollover"],) * 4, m_lane)
M_DRN = motif("drain", (K["drain"],) * 4, m_drain)
M_LAMP = [motif("lamp%d" % i, (K["empty"],) * 4, (lambda n: lambda a, r: m_lamp(a, r, n))(i))
          for i in range(NLAMP)]
M_SEG = [motif("seg%d" % i, (K["empty"],) * 4, (lambda n: lambda a, r: m_seg(a, r, n))(i))
         for i in range(NDIG)]

# ═══════════════════ THE TABLE ═════════════════════════════════════════════
# ⭐ TWENTY COLUMNS BY FORTY ROWS, and it reads top to bottom the way a table
# does: the arch and the scoreboard, the bumper cluster, the targets, an open
# middle, the slingshots, and the flippers over the drain.  The plunger lane
# is the right-hand channel, as it is on every table ever built.
#
#   #  wall      .  board      -  trace across   |  trace down   +  cross
#   o  pad       C  chip       T  target         L  lane         X  drain
#   /  sling, sends right      \  sling, sends left
#   0-7 lamps    a-f the six digits
LAYOUT = [
    "####################",
    "#..abcdef.........|#",
    "#.................o#",
    "#...0.......1.....|#",
    "#..--+--.--+--....o#",
    "#....|.......|....|#",
    "#...CC.......CC...o#",
    "#...CC.......CC...|#",
    "#....|.......|....o#",
    "#..--+--.--+--....|#",
    "#.................o#",
    "#..2...........3..|#",
    "#..TTTT....TTTT...o#",
    "#.................|#",
    "#....LLLL..LLLL...o#",
    "#.................|#",
    "#...o---+---o.....|#",
    "#.......|.........o#",
    "#..4....|.......5.|#",
    "#...--++++--......o#",
    "#.....|..|........|#",
    "#.....o..o........o#",
    "#.................|#",
    "#....CC...CC......o#",
    "#....CC...CC......|#",
    "#.................o#",
    "#..6...........7..|#",
    "#...TTTT..TTTT....o#",
    "#.................|#",
    "#..--+-------+--..o#",
    "#....|.......|....|#",
    "#....o.......o....o#",
    "#.................|#",
]

# ⭐ THE FUNNEL AND THE DRAIN, built rather than typed.  ⚠ A row of this
# layout is exactly TW characters and the slingshot rows are the ones with
# backslashes in them - which in a Python literal are not one character each,
# and mis-typing them is how the first cut of this table came out 19 wide.
for _i in range(6):
    _r = ["."] * TW
    _r[0] = _r[TW - 1] = "#"
    for _k in range(_i + 1):
        _r[1 + _k] = "/"
        _r[TW - 2 - _k] = "\\"
    if _i >= 4:
        for _k in range(6, 10):
            _r[_k] = "X"
    LAYOUT.append("".join(_r))
LAYOUT.append("#" * TW)

CHARMAP = {"#": M_WV, ".": M_SUB, "-": M_TH, "|": M_TV, "+": M_CR, "o": M_PAD,
           "C": M_CHIP, "T": M_TARG, "L": M_LANE, "X": M_DRN,
           "/": M_SLR, "\\": M_SLL}
for _i in range(NLAMP):
    CHARMAP[str(_i)] = M_LAMP[_i]
for _i, _c in enumerate("abcdef"):
    CHARMAP[_c] = M_SEG[_i]


def build():
    rnd = Rnd(0xB0A2D)
    tiles = []
    for name, kinds, fn in MOTIFS:
        tiles.append(fn(canvas(), rnd))
    # the top and bottom walls are the horizontal motif
    grid = np.full((TH, TW), M_SUB, np.uint8)
    for y, row in enumerate(LAYOUT):
        if len(row) != TW:
            sys.exit("FAIL  mkpcbt: LAYOUT row %d is %d wide, not %d"
                     % (y, len(row), TW))
        for x, ch in enumerate(row):
            if ch not in CHARMAP:
                sys.exit("FAIL  mkpcbt: LAYOUT row %d has no motif for %r" % (y, ch))
            grid[y, x] = CHARMAP[ch]
    grid[0, :] = M_WH
    grid[TH - 1, :] = M_WH
    return tiles, grid


def collision(grid):
    """One byte a 16 x 16 cell, from the motif each cell sits in."""
    col = np.zeros((CH, CW), np.uint8)
    for ty in range(TH):
        for tx in range(TW):
            k = MOTIFS[grid[ty, tx]][1]
            for qy in range(2):
                for qx in range(2):
                    col[ty * 2 + qy, tx * 2 + qx] = k[qy * 2 + qx]
    return col


def palette():
    """256 RGB565 words: the art as authored, the lamps and segments OUT."""
    pal = np.zeros(256, np.uint16)
    for name, (idx, (r, g, b)) in C.items():
        pal[idx] = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    pal[0] = 0xF81F                       # ⛔ index 0 is a leak, and magenta
    for i in range(NLAMP):
        r, g, b = LAMP_OFF[i]
        pal[LAMP0 + i] = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    r, g, b = SEG_OFF
    for i in range(NSEG):
        pal[SEG0 + i] = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    return pal


LAMP_ON = [(255, 214, 72), (96, 252, 138), (255, 118, 58), (128, 206, 255),
           (255, 96, 216), (176, 255, 96), (255, 240, 200), (96, 180, 255)]
LAMP_OFF = [(66, 54, 20), (18, 62, 34), (70, 30, 16), (26, 44, 66),
            (66, 24, 56), (44, 66, 24), (66, 62, 52), (24, 46, 66)]
SEG_ON = (255, 62, 40)
SEG_OFF = (56, 14, 12)


# ═══════════════════ THE ACTORS ════════════════════════════════════════════
# ⭐ The ball and the two flippers are keyed 32 x 32 blits out of the bank,
# exactly as `scroll`'s hero is - tscroll.inc does not know what they are.
def art_ball():
    a = np.zeros((ZTILE, ZTILE), np.uint8)          # 0 is the copy key
    disc(a, 16, 16, 9, "ball1", "ball2")
    disc(a, 13, 13, 5, "ball0")
    disc(a, 19, 20, 3, "ball2")
    return a


def art_flip(right, phase):
    """Three angles: at rest, halfway, and up.  ⚠ The pivot is the END the
    flipper turns about, and it is the same pixel in all three."""
    a = np.zeros((ZTILE, ZTILE), np.uint8)
    px, py = (4, 22) if right is False else (27, 22)
    dy = (6, 0, -8)[phase]
    for i in range(22):
        t = i / 21.0
        x = px + (i if not right else -i)
        y = int(py + dy * t)
        h = 6 - int(3 * t)
        for k in range(-h // 2, h // 2 + 1):
            if 0 <= y + k < ZTILE and 0 <= x < ZTILE:
                a[y + k, x] = C["flip1" if k > 0 else "flip0"][0]
        if 0 <= y - h // 2 < ZTILE and 0 <= x < ZTILE:
            a[y - h // 2, x] = C["flip2"][0]
    return a


def art_bank():
    out = [np.zeros((ZTILE, ZTILE), np.uint8) for _ in range(ZNART)]
    out[0] = art_ball()
    for p in range(3):
        out[1 + p] = art_flip(False, p)
        out[4 + p] = art_flip(True, p)
    return out


def bank(tiles, art):
    if len(tiles) > ZART0:
        sys.exit("FAIL  mkpcbt: %d motifs will not fit below the art at %d"
                 % (len(tiles), ZART0))
    strip = np.zeros((ZRINGH, ZBCOL * ZTILE), np.uint8)
    put = list(tiles) + [None] * (ZART0 - len(tiles)) + list(art)
    for n, t in enumerate(put):
        if t is None:
            continue
        c, r = n // ZBROW, n % ZBROW
        strip[r * ZTILE:(r + 1) * ZTILE, c * ZTILE:(c + 1) * ZTILE] = t
    return strip


DAT = """\
********************************************************************
* pcbtdat.asm - GENERATED by arm6309 video3/bench/mkpcbt.py.  Do not edit.
********************************************************************

ZRINGW              equ       {ZRINGW}
ZRINGH              equ       {ZRINGH}
ZVW                 equ       {ZVW}
ZVH                 equ       {ZVH}
ZTILE               equ       {ZTILE}
ZSLOTS              equ       {ZSLOTS}
ZSMSK               equ       ZSLOTS-1
ZVSLOT              equ       {ZVSLOT}
ZTSLOT              equ       {ZTSLOT}       ⛔ no side-scroll: no margin slot
ZBCOL               equ       {ZBCOL}
ZBROW               equ       {ZBROW}
ZNTILE              equ       {ZNTILE}
ZBK0                equ       {ZBK0}
ZVBAND              equ       {ZVBAND}
ZWLDW               equ       {ZWLDW}       the MAP, a power of two both ways
ZWLDH               equ       {ZWLDH}
ZWXMSK              equ       ZWLDW-1
ZWYMSK              equ       ZWLDH-1
ZART0               equ       {ZART0}
ZNART               equ       {ZNART}
ZSCR0               equ       {ZSCR0}
ZMXAC               equ       {ZMXAC}
ZKEY                equ       $00

* ⭐ THE TABLE, and the camera's travel over it
PT.W                equ       {TABW}      640 x 1280
PT.H                equ       {TABH}
PT.CELL             equ       {CELL}       the collision grid
PT.CW               equ       {CW}
PT.CH               equ       {CH}
PT.MXY              equ       PT.H-ZVH   the camera's bottom stop

* the collision kinds
{KINDS}

* the actors' tiles
PA.Ball             equ       ZART0+0
PA.FlipL            equ       ZART0+1    three angles, at rest first
PA.FlipR            equ       ZART0+4

* ⚠ THE MAP IS ZWLDH ROWS OF ZWLDW, because that is what tscroll.inc walks;
* only the first {TABW_T} columns and {TABH_T} rows are table and the rest is
* board that the camera's stops never reach.
WorldMap
{MAP}

* ⭐ THE COLLISION MAP - one byte a {CELL} x {CELL} cell, PT.CW x PT.CH of
* them.  It is derived from the motif each cell sits in, so a table that is
* redrawn cannot disagree with what the ball feels.
PT.Coll
{COLL}
"""


def main(cmds):
    d = pathlib.Path(__file__).resolve().parent
    a = pathlib.Path(cmds)
    a.mkdir(parents=True, exist_ok=True)
    tiles, grid = build()
    col = collision(grid)
    art = art_bank()
    b = bank(tiles, art)
    (d / "pcbt.bnk").write_bytes(b.tobytes())
    pal = palette()
    (d / "pcbt.pal").write_bytes(pal.astype(">u2").tobytes())

    wm = np.zeros((ZWLDH, ZWLDW), np.uint8)
    wm[:TH, :TW] = grid

    def fcb(v, per=16):
        return "\n".join("                    fcb       "
                         + ",".join(str(int(x)) for x in v[k:k + per])
                         for k in range(0, len(v), per))

    (a / "pcbtdat.asm").write_text(DAT.format(
        ZRINGW=ZRINGW, ZRINGH=ZRINGH, ZVW=ZVW, ZVH=ZVH, ZTILE=ZTILE,
        ZSLOTS=ZSLOTS, ZVSLOT=ZVW // ZTILE + 1, ZTSLOT=ZTSLOT, ZBCOL=ZBCOL,
        ZBROW=ZBROW, ZNTILE=ZNTILE, ZBK0=ZBK0, ZVBAND=ZVBAND,
        ZWLDW=ZWLDW, ZWLDH=ZWLDH, ZART0=ZART0, ZNART=ZNART, ZSCR0=ZSCR0,
        ZMXAC=ZMXAC, TABW=TW * ZTILE, TABH=TH * ZTILE, CELL=CELL, CW=CW, CH=CH,
        TABW_T=TW, TABH_T=TH,
        KINDS="\n".join("K.%-16s equ       %d" % (k.capitalize(), v)
                        for k, v in KINDS.items()),
        MAP="\n".join("* row %d\n%s" % (y, fcb(wm[y])) for y in range(ZWLDH)),
        COLL="\n".join("* cell row %d\n%s" % (y, fcb(col[y], 20)) for y in range(CH))))

    # ── the preview, every lamp and segment LIT ────────────────────────────
    from PIL import Image
    lit = pal.copy()
    for i in range(NLAMP):
        r, g, b2 = LAMP_ON[i]
        lit[LAMP0 + i] = ((r >> 3) << 11) | ((g >> 2) << 5) | (b2 >> 3)
    r, g, b2 = SEG_ON
    for i in range(NSEG):
        lit[SEG0 + i] = ((r >> 3) << 11) | ((g >> 2) << 5) | (b2 >> 3)
    pic = np.zeros((TH * ZTILE, TW * ZTILE), np.uint8)
    for y in range(TH):
        for x in range(TW):
            pic[y * ZTILE:(y + 1) * ZTILE, x * ZTILE:(x + 1) * ZTILE] = tiles[grid[y, x]]
    v = lit[pic].astype(np.int32)
    rgb = np.dstack([((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63,
                     (v & 31) * 255 // 31]).astype(np.uint8)
    Image.fromarray(rgb).save(d / "pcbt.png")

    print("ok    %s/pcbt.bnk: %d motifs + %d actor shapes of %d slots, %d x %d"
          % (d, len(tiles), ZNART, ZNTILE, b.shape[1], b.shape[0]))
    print("ok    %s/pcbt.pal: 256 entries, %d art / %d lamps / %d segments"
          % (d, len(C), NLAMP, NSEG))
    print("ok    %s/pcbtdat.asm: table %d x %d, map %d x %d, collision %d x %d"
          % (a, TW * ZTILE, TH * ZTILE, ZWLDW, ZWLDH, CW, CH))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else str(ROOT.parent / "nitros9" / "level2" / "arm6309" / "cmds"))
