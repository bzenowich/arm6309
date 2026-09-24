#!/usr/bin/env python3
"""mkpcb.py - the pinball table as a 640 x 512 PICTURE, themed as a 1984 PCB.

    python3 software/archive/pinball/mkpcb.py          # ~20 s, writes into hardware/video3/bench/

Writes, beside this file:

    pcbtable.pic   327,680 raw bytes - one palette index a pixel, row-major,
                   640 to a row.  ⭐ EXACTLY 640 SD blocks of 512 bytes, so
                   the loader is a block count and not a partial tail.
    pcbtable.pal   512 bytes - 256 big-endian RGB565 words, the LUT as the
                   card stores it, lamps and segments loaded UNLIT.
    pcbtable.png   a 1:1 preview with the palette applied and every lamp and
                   segment LIT, for reviewing the art without a machine.
    pcbtable.json  the palette, the reserved-index assignment, ⭐ THE
                   COLLISION MAP, and every concrete position the scene
                   needs.

⛔ AND NOTHING HERE IS BELIEVED UNTIL `checkpcb.py` HAS RUN.  It reads the
three files back and asks whether the picture and the collision map agree -
by classifying the PICTURE's pixels through the palette, not by asking this
file what it thought it drew - and `checkpcb.py --negative` mutates the inputs
eleven ways and requires each mutation to be caught.  A green check proves
nothing on its own.

    python3 software/archive/pinball/checkpcb.py --negative     # ~20 s; the exit code is
                                                    # the answer

═══ WHY THIS IS A FILE AND NOT 61 BLOCKS ════════════════════════════════════

`mkpinball.py` builds its table out of 61 interned 16 x 16 blocks because
327,680 bytes of picture cannot live in a NitrOS-9 module.  The machine now
has a working SD card (`hardware/storage/docs/sdcard.md`, driver `rbsd`), so the
constraint is gone: the table is a file, read off the card straight into VRAM
rows 0..511, columns 0..639.  Nothing is interned, nothing is composed, and
the art is free to be continuous - which is the whole reason to redraw it.

⛔ INDEX 0 IS THE COPY ENGINE'S COLOUR KEY (keyed-copy.md) and may never be a
visible colour.  The dither only ever returns 1..205, so a 0 in the .pic is
impossible by construction; `assert_key_free` and `checkpcb.py` check it
anyway, because "impossible by construction" is what every defect in
`docs/history.md` was.

⭐ THE LAMPS AND THE SCORE ARE PALETTE ENTRIES, NOT PIXELS.  50 of the 256 LUT
entries are reserved - 8 lamps at 206..213 and 6 x 7 segments at 214..255 -
and the art gets 1..205.  Nothing dithers into a reserved entry (the search
cannot reach them) and the pixels that use one are painted with that index
AFTER the dither.  Lighting a lamp or changing a digit is then ONE LUT write
and touches no VRAM at all, which on this card is the only thing that is free.

═══ WHO OWNS WHICH NUMBER ═══════════════════════════════════════════════════

⚠ The scene and `checkpcb.py` must not disagree about who owns a number, so
the JSON carries the same two lists this header does:

AUTHORED HERE - change it here and everything downstream follows:
    the board regions; every component's pixel rectangle, part number and
    designator; the rollover groups; the drop-switch banks; the kicker
    rectangles and their kick directions; the flipper pivots, length, rest and
    active angles; the plunger lane and its seat; the drain mouth; the
    edge-connector finger pitch; which lamp belongs to which feature; the
    LUT's reserved split (205 / 8 / 42).

DERIVED - never write one of these down anywhere else:
    the 40 x 32 collision grid and its id grid (from the objects' collision
    rectangles, by cell centre, in the priority order `PRIORITY`); the bumper
    centres and radii (from the DIP bodies); the six digit boxes and their 42
    segment boxes (from the DS1 module's geometry); the 205 art colours
    (median cut over the rendered art, snapped to 5/6/5); every byte of the
    .pic, .pal and .png; the reserved-index probes.

⚠ A COLLISION KIND IS A DECISION ABOUT HEIGHT, not about what the part is.
Anything that stands proud of the board - a DIP, an electrolytic, the crystal
can, a switch bank - is an obstacle.  Anything flat - a trace, a pad, a via,
silkscreen, an LED lens, a resistor lying down - is not.  That rule is why the
resistors are lane MARKERS and the capacitors are POSTS.
"""
import base64
import hashlib
import json
import math
import os
import sys

import numpy as np

# ───────────────────────────────────────────────────────────── geometry
W, H = 640, 512                  # the table, in pixels: 327,680 bytes
BLK = 16
CW, CH = W // BLK, H // BLK      # 40 x 32 collision cells
PLAY_H = 416                     # rows 0..25 are the playfield ...
PLAY_R = PLAY_H // BLK           # ... and 26..31 the backplane
VIEWH = 200                      # what VMODE 00 shows
VSMAX = H - VIEWH                # 312: the highest VSCROLL with no ring wrap

# ── the palette's three tenants (the same split mkpinball.py uses)
NLAMP = 8
NDIG = 6
NSEG = NDIG * 7
NART = 255 - NLAMP - NSEG        # 205 dithered colours
LAMP0 = 1 + NART                 # 206
SEG0 = LAMP0 + NLAMP             # 214
assert SEG0 + NSEG == 256

# ── the collision kinds.  ⚠ A SLOPE IS NAMED BY WHERE IT SENDS A FALLING
# BALL, not by which corner the copper fills: K_SLOPE_R's face runs from the
# cell's top-left to its bottom-right, reflecting (vx, vy) -> (vy, vx), so a
# ball dropped on it leaves to the RIGHT.  mkpinball.py records getting this
# pair the wrong way round as a funnel that feeds the drain.
KINDS = {
    "empty": 0,        # open board - the ball flies over it
    "solid": 1,        # a wall, or a part that stands proud of the board
    "slope_r": 2,      # a 45 degree face; a falling ball leaves RIGHT
    "slope_l": 3,      # ... and LEFT
    "bumper": 4,       # a DIP IC: it scores and it kicks back
    "target": 5,       # one switch of a DIP-switch bank: a drop target
    "rollover": 6,     # a test-pad lane: it scores, it does not deflect
    "kicker": 7,       # the lane mouth and the two slingshots
    "drain": 8,        # a milled slot through the board: the ball is gone
    "flip_l": 9,       # the left flipper's airspace
    "flip_r": 10,      # ... and the right's
    "return": 11,      # an edge-connector return lane, back onto a flipper
    "plunger": 12,     # the seat at the bottom of the lane: it FIRES
}
# later wins, so the drain cuts the fingers and the flippers do not eat it
PRIORITY = ["solid", "slope_r", "slope_l", "rollover", "bumper", "target",
            "kicker", "return", "flip_l", "flip_r", "drain", "plunger"]

# ── the plunger lane, on the right, in cells
LANE_X0, LANE_X1 = 37, 38        # the channel
LANE_DIV = 36                    # the divider ...
LANE_DIV_Y0 = 6                  # ... which starts low enough to let the ball out
MOUTH_Y0, MOUTH_Y1 = 1, 4        # the kicker at the top of the lane

# ── the flippers, in pixels.  Authored; the zone cells are derived from them.
FLIP_LEN = 48.0
FLIP_REST = 32.0                 # degrees, y down: +down at rest
FLIP_ACTIVE = -32.0
FLIP_PIV = {"l": (248.0, 356.0), "r": (360.0, 356.0)}
DRAIN_X0, DRAIN_X1 = 288, 319    # the milled slot between the flippers
OUT_L = (96, 127)                # the two outlanes, milled the same way
OUT_R = (480, 511)
EDGE_Y0 = 24 * BLK               # the edge connector: rows 24..25
FINGER_PITCH, FINGER_W = 16, 11

# ── the DS1 display, authored; the 6 digit boxes and 42 segment boxes derive
DIG_W, DIG_H, DIG_GAP = 26, 46, 8
DIG_X0, DIG_Y0 = 222, 436

# ═══════════════════════════════════════════════════════ colour, palette


def rgb565(c):
    r, g, b = int(round(c[0])), int(round(c[1])), int(round(c[2]))
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def snap565(c):
    v = rgb565(c)
    r5, g6, b5 = v >> 11, (v >> 5) & 63, v & 31
    return ((r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2))


class Quant:
    """NART colours in indices 1..NART, and Floyd-Steinberg against them.

    ⚠ The search never considers 0 (the key) and never reaches LAMP0, so
    neither can come out of a dither.  That is structural; it is asserted
    anyway.

    ⚠ The nearest-colour cache is keyed on the INTEGER-ROUNDED working colour.
    327,680 pixels times a 205-way search is the whole runtime of this
    generator; rounding the query (never the error, which stays in floating
    point and is what the dither is made of) makes the cache hit and costs at
    most half a unit of 8-bit distance in a space whose entries are ~25 apart.
    """

    def __init__(self, cols):
        assert len(cols) == NART
        self.rgb = np.array(cols, dtype=np.float64)
        self.psq = (self.rgb * self.rgb).sum(1)
        self.cache = {}

    def nearest(self, px):
        key = (int(px[0] + 0.5), int(px[1] + 0.5), int(px[2] + 0.5))
        i = self.cache.get(key)
        if i is None:
            q = np.array(key, dtype=np.float64)
            i = int(np.argmin(self.psq - 2.0 * self.rgb.dot(q))) + 1
            self.cache[key] = i
        return i

    def dither(self, img, skip=None):
        """Floyd-Steinberg over the whole picture.  `skip` marks pixels whose
        colour is decided elsewhere (a lamp lens, a segment) - they take no
        index here and diffuse no error, because their colour is not a
        rendering of anything."""
        h, w, _ = img.shape
        work = np.clip(img.astype(np.float64), 0, 255)
        out = np.zeros((h, w), dtype=np.uint8)
        rgb = self.rgb
        for y in range(h):
            row, nxt = work[y], work[y + 1] if y + 1 < h else None
            for x in range(w):
                if skip is not None and skip[y, x]:
                    continue
                old = row[x]
                i = self.nearest(old)
                out[y, x] = i
                err = old - rgb[i - 1]
                if x + 1 < w:
                    row[x + 1] += err * 0.4375
                if nxt is not None:
                    if x:
                        nxt[x - 1] += err * 0.1875
                    nxt[x] += err * 0.3125
                    if x + 1 < w:
                        nxt[x + 1] += err * 0.0625
        return out


def build_palette(px):
    """NART colours by median cut over the art's own pixels, snapped to 5/6/5.

    ⚠ SNAPPED BEFORE THE DITHER: the LUT stores RGB565, so a palette entry
    chosen in 8-bit space is not the colour the card shows, and a dither aimed
    at a colour the card cannot make is a dither that makes things worse.
    """
    from PIL import Image
    px = np.asarray(px, dtype=np.uint8).reshape(-1, 3)
    n = int(math.ceil(math.sqrt(len(px))))
    pad = np.zeros((n * n, 3), dtype=np.uint8)
    pad[:len(px)] = px
    pad[len(px):] = px[-1]
    im = Image.fromarray(pad.reshape(n, n, 3), "RGB")
    q = im.quantize(colors=NART, method=Image.Quantize.MEDIANCUT,
                    dither=Image.Dither.NONE)
    raw = q.getpalette()[:NART * 3]
    cols, seen = [], set()
    for i in range(NART):
        c = snap565(raw[i * 3:i * 3 + 3])
        if c not in seen:
            seen.add(c)
            cols.append(c)
    i = 0
    while len(cols) < NART:      # 5/6/5 collisions leave holes; fill them
        c = snap565((i * 9 % 256, i * 5 % 256, i * 13 % 256))
        if c not in seen:
            seen.add(c)
            cols.append(c)
        i += 1
    return cols


# ── the board's colours, in 8-bit before the snap
FR4 = (168, 150, 96)             # bare substrate, where the mask is not
FR4_D = (126, 110, 66)
MASK = (16, 62, 36)              # the solder mask
MASK_L = (26, 86, 48)
MASK_D = (8, 40, 24)
POUR = (40, 116, 64)             # ground pour, seen THROUGH the mask
POUR_L = (56, 140, 80)
CU_D = (112, 72, 28)             # copper, at a trace's edge ...
CU_M = (186, 134, 54)            # ... and along its crown
GOLD = (214, 174, 90)            # exposed plating: pads, vias, fingers
GOLD_H = (248, 224, 162)
GOLD_D = (128, 98, 40)
SILK = (222, 226, 214)           # white silkscreen
SILK_D = (150, 154, 146)
BODY = (26, 26, 30)              # an IC's epoxy
BODY_L = (58, 58, 64)
BODY_INK = (186, 188, 192)       # what is printed on it
PIN = (176, 182, 192)
PIN_D = (92, 98, 110)
SW_BODY = (168, 40, 34)          # the DIP switch's case
SW_ACT = (232, 230, 220)
CAP_B = (26, 42, 112)            # an electrolytic's sleeve
CAP_BL = (44, 68, 156)
CAP_TOP = (22, 24, 32)
XTAL_C = (176, 182, 192)
RES_B = (204, 182, 138)
SLOT = (11, 11, 15)              # a milled slot: straight through the board
BPLANE = (14, 15, 19)            # the backplane the card plugs into
SOCKET = (32, 32, 38)
BANDC = {"k": (18, 18, 18), "n": (96, 56, 26), "r": (176, 34, 28),
         "o": (214, 110, 30), "y": (226, 198, 58), "g": (38, 138, 58),
         "b": (36, 68, 172), "v": (118, 58, 168), "e": (140, 140, 140),
         "w": (232, 232, 232), "d": (198, 162, 72), "s": (190, 190, 196)}

# ⚠ the eight lamps and the segments, lit and out.  A reserved colour may not
# also be an art colour: `checkpcb.py` reads the lamps off the PICTURE by
# looking for their exact RGB565, so if a wall could be the same colour as a
# lit lamp, a lit lamp and a wall would be the same evidence.  `nudge()`
# below moves any that collide and says so.
LAMP_ON = [(255, 214, 72), (96, 252, 138), (255, 118, 58), (128, 206, 255),
           (255, 244, 186), (188, 140, 255), (72, 248, 232), (255, 92, 148)]
LAMP_OFF = [(66, 54, 20), (18, 62, 34), (70, 30, 16), (26, 44, 66),
            (62, 58, 44), (44, 30, 66), (16, 60, 58), (68, 22, 40)]
SEG_ON = (255, 62, 40)
SEG_OFF = (56, 14, 12)

# ═════════════════════════════════════════════════════ the raster buffers
IMG = np.zeros((H, W, 3), np.float64)    # continuous tone
LAMPI = np.zeros((H, W), np.uint8)       # which reserved index a pixel takes
KEEP = np.zeros((H, W), np.float64)      # pour keepout: copper and components


def clipbox(x0, y0, x1, y1):
    x0, y0 = max(0, int(math.floor(x0))), max(0, int(math.floor(y0)))
    x1, y1 = min(W - 1, int(math.ceil(x1))), min(H - 1, int(math.ceil(y1)))
    return None if x1 < x0 or y1 < y0 else (x0, y0, x1, y1)


def gridxy(box):
    x0, y0, x1, y1 = box
    ys = np.arange(y0, y1 + 1, dtype=np.float64)[:, None]
    xs = np.arange(x0, x1 + 1, dtype=np.float64)[None, :]
    return xs, ys


def paint(box, cov, col):
    """Composite `col` (a triple or an (h, w, 3) array) at coverage `cov`."""
    if box is None:
        return
    x0, y0, x1, y1 = box
    sub = IMG[y0:y1 + 1, x0:x1 + 1]
    c = np.asarray(col, np.float64)
    if c.ndim == 1:
        c = c[None, None, :]
    m = np.clip(cov, 0.0, 1.0)[..., None]
    sub *= (1.0 - m)
    sub += m * c


def keepout(box, cov):
    if box is None:
        return
    x0, y0, x1, y1 = box
    np.maximum(KEEP[y0:y1 + 1, x0:x1 + 1], np.clip(cov, 0, 1),
               out=KEEP[y0:y1 + 1, x0:x1 + 1])


def cov_of(sd):
    return np.clip(0.5 - sd, 0.0, 1.0)


# ── signed distance fields.  Negative inside; 0 on the edge.
def sd_seg(box, p0, p1, w):
    xs, ys = gridxy(box)
    ax, ay = float(p0[0]), float(p0[1])
    bx, by = float(p1[0]), float(p1[1])
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    if ll < 1e-9:
        t = np.zeros_like(xs + ys)
    else:
        t = np.clip(((xs - ax) * dx + (ys - ay) * dy) / ll, 0.0, 1.0)
    px, py = xs - (ax + t * dx), ys - (ay + t * dy)
    return np.hypot(px, py) - w * 0.5


def box_seg(p0, p1, w, pad=2.0):
    return clipbox(min(p0[0], p1[0]) - w * 0.5 - pad,
                   min(p0[1], p1[1]) - w * 0.5 - pad,
                   max(p0[0], p1[0]) + w * 0.5 + pad,
                   max(p0[1], p1[1]) + w * 0.5 + pad)


def sd_disc(box, cx, cy, r):
    xs, ys = gridxy(box)
    return np.hypot(xs - cx, ys - cy) - r


def box_disc(cx, cy, r, pad=2.0):
    return clipbox(cx - r - pad, cy - r - pad, cx + r + pad, cy + r + pad)


def sd_rrect(box, x0, y0, x1, y1, r=0.0):
    xs, ys = gridxy(box)
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    hx, hy = (x1 - x0) * 0.5 - r, (y1 - y0) * 0.5 - r
    qx = np.abs(xs - cx) - max(hx, 0.0)
    qy = np.abs(ys - cy) - max(hy, 0.0)
    return (np.hypot(np.maximum(qx, 0), np.maximum(qy, 0))
            + np.minimum(np.maximum(qx, qy), 0.0) - r)


def box_rect(x0, y0, x1, y1, pad=2.0):
    return clipbox(x0 - pad, y0 - pad, x1 + pad, y1 + pad)


def lerp(a, b, t):
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)
    t = np.asarray(t, np.float64)
    if t.ndim:
        t = t[..., None]
    return a + (b - a) * t


# ── deterministic value noise.  ⚠ NOT a numpy RNG: the art has to be the same
# byte for byte on any machine and any numpy, or the checker's hash is a lie.
def ihash(xi, yi, s):
    x = xi.astype(np.uint64)
    y = yi.astype(np.uint64)
    h = (x * np.uint64(374761393) + y * np.uint64(668265263)
         + np.uint64(s) * np.uint64(2654435761)) & np.uint64(0xFFFFFFFF)
    h = ((h ^ (h >> np.uint64(13))) * np.uint64(1274126177)) & np.uint64(0xFFFFFFFF)
    return (((h ^ (h >> np.uint64(16))) & np.uint64(0xFFFF)).astype(np.float64)
            / 65536.0)


def vnoise(cell, seed):
    """Bilinear value noise over the whole board, in [0, 1)."""
    gw, gh = W // cell + 3, H // cell + 3
    gx = np.arange(gw)[None, :].repeat(gh, 0)
    gy = np.arange(gh)[:, None].repeat(gw, 1)
    g = ihash(gx, gy, seed)
    xs = np.arange(W, dtype=np.float64) / cell
    ys = np.arange(H, dtype=np.float64) / cell
    ix, iy = xs.astype(int), ys.astype(int)
    fx, fy = xs - ix, ys - iy
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    a = g[np.ix_(iy, ix)]
    b = g[np.ix_(iy, ix + 1)]
    c = g[np.ix_(iy + 1, ix)]
    d = g[np.ix_(iy + 1, ix + 1)]
    return (a + (b - a) * fx[None, :]) * (1 - fy[:, None]) + \
           (c + (d - c) * fx[None, :]) * fy[:, None]


def dilate(m, r):
    """A box dilation, so the pour keeps its clearance.  scipy is not a
    dependency of this repository and this is four shifts a radius."""
    out = m.copy()
    for _ in range(r):
        o = out.copy()
        o[1:, :] = np.maximum(o[1:, :], out[:-1, :])
        o[:-1, :] = np.maximum(o[:-1, :], out[1:, :])
        out = o
        o = out.copy()
        o[:, 1:] = np.maximum(o[:, 1:], out[:, :-1])
        o[:, :-1] = np.maximum(o[:, :-1], out[:, 1:])
        out = o
    return out


# ═══════════════════════════════════════════════════════════ silkscreen font
# A 5 x 7 stroke font.  Silkscreen is the only text on a board that a person
# reads, so the part numbers have to be legible at 1:1 - which at 640 wide
# means 5 pixels a glyph and no anti-aliasing.
_F = {
    "0": ".###./#...#/#..##/#.#.#/##..#/#...#/.###.",
    "1": "..#../.##../..#../..#../..#../..#../.###.",
    "2": ".###./#...#/....#/...#./..#../.#.../#####",
    "3": "#####/...#./..#../...#./....#/#...#/.###.",
    "4": "...#./..##./.#.#./#..#./#####/...#./...#.",
    "5": "#####/#..../####./....#/....#/#...#/.###.",
    "6": "..##./.#.../#..../####./#...#/#...#/.###.",
    "7": "#####/....#/...#./..#../.#.../.#.../.#...",
    "8": ".###./#...#/#...#/.###./#...#/#...#/.###.",
    "9": ".###./#...#/#...#/.####/....#/...#./.##..",
    "A": ".###./#...#/#...#/#####/#...#/#...#/#...#",
    "B": "####./#...#/#...#/####./#...#/#...#/####.",
    "C": ".###./#...#/#..../#..../#..../#...#/.###.",
    "D": "###../#..#./#...#/#...#/#...#/#..#./###..",
    "E": "#####/#..../#..../####./#..../#..../#####",
    "F": "#####/#..../#..../####./#..../#..../#....",
    "G": ".###./#...#/#..../#.###/#...#/#...#/.####",
    "H": "#...#/#...#/#...#/#####/#...#/#...#/#...#",
    "I": ".###./..#../..#../..#../..#../..#../.###.",
    "J": "..###/...#./...#./...#./...#./#..#./.##..",
    "K": "#...#/#..#./#.#../##.../#.#../#..#./#...#",
    "L": "#..../#..../#..../#..../#..../#..../#####",
    "M": "#...#/##.##/#.#.#/#.#.#/#...#/#...#/#...#",
    "N": "#...#/##..#/#.#.#/#..##/#...#/#...#/#...#",
    "O": ".###./#...#/#...#/#...#/#...#/#...#/.###.",
    "P": "####./#...#/#...#/####./#..../#..../#....",
    "Q": ".###./#...#/#...#/#...#/#.#.#/#..#./.##.#",
    "R": "####./#...#/#...#/####./#.#../#..#./#...#",
    "S": ".####/#..../#..../.###./....#/....#/####.",
    "T": "#####/..#../..#../..#../..#../..#../..#..",
    "U": "#...#/#...#/#...#/#...#/#...#/#...#/.###.",
    "V": "#...#/#...#/#...#/#...#/#...#/.#.#./..#..",
    "W": "#...#/#...#/#...#/#.#.#/#.#.#/##.##/#...#",
    "X": "#...#/#...#/.#.#./..#../.#.#./#...#/#...#",
    "Y": "#...#/#...#/.#.#./..#../..#../..#../..#..",
    "Z": "#####/....#/...#./..#../.#.../#..../#####",
    "-": "...../...../...../#####/...../...../.....",
    ".": "...../...../...../...../...../.##../.##..",
    ",": "...../...../...../...../.##../.##../.#...",
    "+": "...../..#../..#../#####/..#../..#../.....",
    "/": "....#/....#/...#./..#../.#.../#..../#....",
    ":": "...../.##../.##../...../.##../.##../.....",
    "(": "...#./..#../.#.../.#.../.#.../..#../...#.",
    ")": ".#.../..#../...#./...#./...#./..#../.#...",
    "*": "...../#.#.#/.###./#####/.###./#.#.#/.....",
    "=": "...../...../#####/...../#####/...../.....",
    "#": ".#.#./#####/.#.#./.#.#./#####/.#.#./.....",
    " ": "...../...../...../...../...../...../.....",
}
FONT = {k: v.split("/") for k, v in _F.items()}
for _k, _g in FONT.items():
    assert len(_g) == 7 and all(len(r) == 5 for r in _g), _k


def text_w(s, scale=1, sp=1):
    return len(s) * (5 + sp) * scale - sp * scale


def text(x, y, s, col=SILK, scale=1, sp=1, alpha=1.0):
    """Silkscreen text, top-left at (x, y).  Returns the advance."""
    x0 = x
    for ch in str(s).upper():
        g = FONT.get(ch, FONT[" "])
        for ry in range(7):
            row = g[ry]
            for rx in range(5):
                if row[rx] != "#":
                    continue
                px, py = int(x + rx * scale), int(y + ry * scale)
                bx = clipbox(px, py, px + scale - 1, py + scale - 1)
                if bx:
                    paint(bx, np.full((bx[3] - bx[1] + 1, bx[2] - bx[0] + 1),
                                      alpha), col)
        x += (5 + sp) * scale
    return x - x0


def text_c(cx, y, s, col=SILK, scale=1, sp=1, alpha=1.0):
    text(cx - text_w(s, scale, sp) / 2.0, y, s, col, scale, sp, alpha)


# ═══════════════════════════════════════════════════════════════ copper
class Cu:
    """Every piece of exposed copper, collected before the pour is drawn.

    ⚠ The pour needs its clearance from copper that does not exist yet, so the
    shapes are rasterised ONCE into signed distance, kept, and then used
    twice: for the keepout, and for the paint.  Rasterising twice is where a
    trace and its own clearance drift apart.
    """

    def __init__(self):
        self.items = []

    def add(self, box, sd, style, w=6.0):
        if box is not None:
            self.items.append((box, sd, style, w))

    def trace(self, pts, w=6.0, style="trace"):
        for i in range(len(pts) - 1):
            p0, p1 = pts[i], pts[i + 1]
            dx, dy = abs(p1[0] - p0[0]), abs(p1[1] - p0[1])
            # ⭐ 0, 45 or 90 degrees and nothing else: this is what a 1984
            # autorouter could draw, and asserting it is what keeps the claim
            # honest when a route gets nudged by hand.
            assert dx == 0 or dy == 0 or dx == dy, ("not an autorouter angle",
                                                    p0, p1)
            b = box_seg(p0, p1, w)
            self.add(b, sd_seg(b, p0, p1, w), style, w)

    def pad(self, cx, cy, r, drill=0.0, style="pad"):
        b = box_disc(cx, cy, r)
        self.add(b, sd_disc(b, cx, cy, r), style, r * 2)
        if drill:
            self.items.append(("drill", (cx, cy, drill), None, None))

    def cover(self):
        for it in self.items:
            if it[0] == "drill":
                continue
            box, sd, _, _ = it
            keepout(box, cov_of(sd))

    def draw(self):
        shine = vnoise(37, 91)
        for it in self.items:
            if it[0] == "drill":
                cx, cy, r = it[1]
                b = box_disc(cx, cy, r)
                paint(b, cov_of(sd_disc(b, cx, cy, r)), (16, 14, 12))
                continue
            box, sd, style, w = it
            t = np.clip(-sd / max(w * 0.5, 0.8), 0.0, 1.0)
            s = shine[box[1]:box[3] + 1, box[0]:box[2] + 1]
            if style == "trace":
                col = lerp(CU_D, CU_M, t ** 0.55)
                col += (s[..., None] - 0.5) * 14.0
            elif style == "gold":
                col = lerp(GOLD_D, GOLD, t ** 0.5)
                col += (s[..., None] - 0.5) * 12.0
            else:                                   # an exposed pad
                col = lerp(GOLD_D, GOLD, t ** 0.45)
                col = lerp(col, GOLD_H, np.clip((t - 0.55) * 1.7, 0, 1) * 0.8)
                col += (s[..., None] - 0.5) * 10.0
            paint(box, cov_of(sd), np.clip(col, 0, 255))


def via(cu, cx, cy, r=4.0, drill=1.8):
    cu.pad(cx, cy, r, drill, "pad")


def teardrop(cu, cx, cy, r, toward, w):
    """The fillet an autorouter drops where a trace meets a pad - the detail
    that makes a board look drawn rather than generated."""
    dx, dy = toward[0] - cx, toward[1] - cy
    n = math.hypot(dx, dy) or 1.0
    for k in range(5):
        t = k / 4.0
        rr = r * (1.0 - t) + w * 0.5 * t
        px, py = cx + dx / n * r * t * 1.1, cy + dy / n * r * t * 1.1
        b = box_disc(px, py, rr)
        cu.add(b, sd_disc(b, px, py, rr), "pad", rr * 2)


# ═══════════════════════════════════════════════════ the board's substrate
def substrate():
    """FR-4: a glass weave under a resin that is never quite even."""
    xs = np.arange(W, dtype=np.float64)[None, :]
    ys = np.arange(H, dtype=np.float64)[:, None]
    weave = (np.sin(xs * math.pi / 3.0) * np.sin(ys * math.pi / 3.0)) * 5.0
    n = vnoise(23, 7) * 18.0 - 9.0
    base = np.asarray(FR4, np.float64)[None, None, :] + (weave + n)[..., None]
    IMG[:] = np.clip(base, 0, 255)


def soldermask(bare):
    """The green, with the mottling of a real board, and the copper showing
    through it as a slightly warmer green wherever there is copper beneath."""
    lo = vnoise(41, 11)
    hi = vnoise(7, 13)
    t = np.clip(lo * 0.75 + hi * 0.25, 0, 1)
    col = lerp(MASK_D, MASK_L, t)
    col = lerp(col, MASK, 0.45)
    cov = np.where(bare, 0.0, 1.0)
    paint((0, 0, W - 1, H - 1), cov, np.clip(col, 0, 255))


def groundpour(region):
    """⭐ A CROSSHATCH, not a flood.  A 1984 two-layer board poured its ground
    plane as a 45 degree crosshatch - it etched faster, it did not lift, and
    it is the single detail that dates a board to the decade."""
    xs = np.arange(W)[None, :].repeat(H, 0)
    ys = np.arange(H)[:, None].repeat(W, 1)
    a = ((xs + ys) % 11) < 4
    b = ((xs - ys) % 11) < 4
    hatch = (a | b) & region & (dilate(KEEP, 2) < 0.25)
    n = vnoise(29, 17)
    col = lerp(POUR, POUR_L, 0.4 + n * 0.6)
    paint((0, 0, W - 1, H - 1), np.where(hatch, 1.0, 0.0), np.clip(col, 0, 255))


# ═══════════════════════════════════════════════════════════ components
def dip_pads(cu, x0, y0, x1, y1, npins):
    n2 = npins // 2
    pitch = (x1 - x0 + 1) / float(n2)
    for i in range(n2):
        px = x0 + pitch * (i + 0.5)
        for py in (y0 + 3.5, y1 - 3.5):
            cu.pad(px, py, 3.4, 1.4, "pad")


def dip(x0, y0, x1, y1, npins, part, desig, ink=BODY_INK):
    """A DIP package: pins, an epoxy body with its pin-1 notch, the part
    number printed on it and the designator on the silkscreen beside it."""
    n2 = npins // 2
    pitch = (x1 - x0 + 1) / float(n2)
    bx0, bx1 = x0 + 1.0, x1 - 1.0
    by0, by1 = y0 + 6.0, y1 - 6.0
    # the silkscreen outline, drawn first so the body sits on it
    b = box_rect(x0 - 1, by0 - 2, x1 + 1, by1 + 2)
    sd = sd_rrect(b, x0 - 1, by0 - 2, x1 + 1, by1 + 2, 1.0)
    paint(b, np.clip(cov_of(sd) - cov_of(sd + 1.2), 0, 1), SILK_D)
    # the legs
    for i in range(n2):
        px = x0 + pitch * (i + 0.5)
        for (ya, yb) in ((y0 + 1.5, by0 + 1.0), (by1 - 1.0, y1 - 1.5)):
            bb = box_rect(px - 1.8, ya, px + 1.8, yb, 1)
            s = sd_rrect(bb, px - 1.8, ya, px + 1.8, yb, 0.6)
            t = np.clip(-s / 1.8, 0, 1)
            paint(bb, cov_of(s), lerp(PIN_D, PIN, t ** 0.6))
    # the body
    b = box_rect(bx0, by0, bx1, by1)
    sd = sd_rrect(b, bx0, by0, bx1, by1, 1.5)
    xs, ys = gridxy(b)
    v = (ys - by0) / max(by1 - by0, 1.0)
    col = lerp(BODY_L, BODY, np.clip(v * 1.5, 0, 1) ** 0.7)
    col = lerp(col, (10, 10, 12), np.clip((v - 0.82) * 5, 0, 1))
    paint(b, cov_of(sd), np.clip(col, 0, 255))
    # pin 1: the moulded notch at the left end, and the dot beside pin 1
    ny = (by0 + by1) * 0.5
    nb = box_disc(bx0, ny, 3.6)
    paint(nb, cov_of(sd_disc(nb, bx0, ny, 3.6)), (12, 12, 15))
    paint(nb, np.clip(cov_of(sd_disc(nb, bx0 + 0.8, ny - 0.6, 3.2)) -
                      cov_of(sd_disc(nb, bx0, ny, 3.0)), 0, 1), (64, 64, 70))
    db = box_disc(bx0 + 6, by0 + 4, 1.6)
    paint(db, cov_of(sd_disc(db, bx0 + 6, by0 + 4, 1.6)), (86, 86, 92))
    # what is printed on it
    ty = int((by0 + by1) * 0.5) - 3
    text_c((bx0 + bx1) * 0.5 + 2, ty, part, ink, 1, 1, 0.92)
    text(x0 - 1, y0 - 8, desig, SILK, 1, 1)


def dipsw(x0, y0, x1, y1, n, desig, down=()):
    """⭐ A DIP-SWITCH BANK, WHICH IS WHAT A DROP TARGET IS.  A switch that is
    visibly up or visibly down is the whole mechanism: the scene drops one by
    copying the actuator rectangle this generator emits, and nothing else on
    the table changes."""
    pitch = (x1 - x0 + 1) / float(n)
    bx0, bx1, by0, by1 = x0 + 1.0, x1 - 1.0, y0 + 5.0, y1 - 5.0
    for i in range(n):
        px = x0 + pitch * (i + 0.5)
        for (ya, yb) in ((y0 + 1.0, by0 + 1.0), (by1 - 1.0, y1 - 1.0)):
            bb = box_rect(px - 1.6, ya, px + 1.6, yb, 1)
            s = sd_rrect(bb, px - 1.6, ya, px + 1.6, yb, 0.5)
            paint(bb, cov_of(s), lerp(PIN_D, PIN, np.clip(-s / 1.6, 0, 1)))
    b = box_rect(bx0, by0, bx1, by1)
    sd = sd_rrect(b, bx0, by0, bx1, by1, 1.2)
    xs, ys = gridxy(b)
    v = (ys - by0) / max(by1 - by0, 1.0)
    paint(b, cov_of(sd), np.clip(lerp((196, 62, 52), SW_BODY,
                                      np.clip(v * 1.3, 0, 1) ** 0.8), 0, 255))
    # the window the actuators slide in
    wy0, wy1 = by0 + 5.0, by1 - 3.0
    wb = box_rect(bx0 + 2, wy0, bx1 - 2, wy1)
    paint(wb, cov_of(sd_rrect(wb, bx0 + 2, wy0, bx1 - 2, wy1, 0.8)), (74, 18, 14))
    acts = []
    for i in range(n):
        px = x0 + pitch * (i + 0.5)
        ax0, ax1 = px - pitch * 0.28, px + pitch * 0.28
        up = i not in down
        ay0 = wy0 + (0.6 if up else (wy1 - wy0) * 0.5)
        ay1 = ay0 + (wy1 - wy0) * 0.45
        ab = box_rect(ax0, ay0, ax1, ay1)
        s = sd_rrect(ab, ax0, ay0, ax1, ay1, 0.8)
        t = np.clip(-s / 2.2, 0, 1)
        paint(ab, cov_of(s), lerp((150, 148, 138), SW_ACT, t ** 0.5))
        acts.append([int(round(ax0)), int(round(ay0)),
                     int(round(ax1)), int(round(ay1))])
        text_c(px, by1 - 2.5, str(i + 1), (240, 200, 190), 1, 1, 0.8)
    text(bx0 + 2, by0 + 0.5, "ON", (250, 240, 230), 1, 1, 0.9)
    text(x0 - 1, y0 - 8, desig, SILK, 1, 1)
    return acts


def elcap_pads(cu, cx, cy, r):
    cu.pad(cx - r * 0.52, cy + r * 0.72, 3.6, 1.5, "pad")
    cu.pad(cx + r * 0.52, cy + r * 0.72, 3.6, 1.5, "pad")


def elcap(cx, cy, r, desig, value):
    """A radial electrolytic, seen from above: the sleeve, the vent score and
    the stripe down the negative side.  ⚠ It STANDS PROUD, so it is a post."""
    b = box_disc(cx, cy, r + 1)
    sdo = sd_disc(b, cx, cy, r)
    xs, ys = gridxy(b)
    hl = np.clip(1.0 - np.hypot(xs - (cx - r * 0.42), ys - (cy - r * 0.42))
                 / (r * 1.5), 0, 1)
    col = lerp(CAP_B, CAP_BL, hl ** 1.4)
    paint(b, cov_of(sdo), np.clip(col, 0, 255))
    # the crimped rim
    paint(b, np.clip(cov_of(sdo) - cov_of(sdo + 2.0), 0, 1),
          np.clip(lerp((58, 84, 180), (14, 22, 66), 0.35), 0, 255))
    # the top disc and its vent score
    sdt = sd_disc(b, cx, cy, r - 3.0)
    paint(b, cov_of(sdt), np.clip(lerp(CAP_TOP, (54, 56, 70), hl ** 2), 0, 255))
    for a in (0.0, math.pi / 2):
        p0 = (cx - math.cos(a) * (r - 3.4), cy - math.sin(a) * (r - 3.4))
        p1 = (cx + math.cos(a) * (r - 3.4), cy + math.sin(a) * (r - 3.4))
        vb = box_seg(p0, p1, 1.6)
        paint(vb, cov_of(sd_seg(vb, p0, p1, 1.6)) * 0.85, (96, 100, 118))
    # the negative stripe
    stripe = (xs - cx) < -r * 0.55
    paint(b, np.where(stripe, cov_of(sdo) * 0.95, 0.0), (206, 210, 218))
    for k in range(3):
        text_c(cx - r * 0.78, cy - 11 + k * 8, "-", (40, 44, 60), 1, 1, 0.9)
    # the silkscreen: the outline, the polarity and the designator
    sb = box_disc(cx, cy, r + 3)
    sds = sd_disc(sb, cx, cy, r + 2.0)
    paint(sb, np.clip(cov_of(sds) - cov_of(sds + 1.0), 0, 1), SILK_D)
    text(cx + r + 4, cy - 11, desig, SILK, 1, 1)
    text(cx + r + 4, cy - 1, value, SILK_D, 1, 1)
    text(cx - r - 8, cy - 4, "+", SILK, 1, 1)


def xtal_pads(cu, x0, y0, x1, y1):
    cy = y1 + 5.0
    cu.pad(x0 + 8, cy, 3.6, 1.5, "pad")
    cu.pad(x1 - 8, cy, 3.6, 1.5, "pad")


def xtal(x0, y0, x1, y1, desig, freq):
    """An HC-49 can, lying down, with its leads bent into the board."""
    for px in (x0 + 8, x1 - 8):
        p0, p1 = (px, y1 - 2), (px, y1 + 5)
        lb = box_seg(p0, p1, 2.0)
        paint(lb, cov_of(sd_seg(lb, p0, p1, 2.0)), PIN_D)
    b = box_rect(x0, y0, x1, y1)
    sd = sd_rrect(b, x0, y0, x1, y1, 6.0)
    xs, ys = gridxy(b)
    v = (ys - y0) / max(y1 - y0, 1.0)
    col = lerp((228, 232, 238), XTAL_C, np.clip(v * 1.2, 0, 1) ** 0.6)
    col = lerp(col, (96, 102, 112), np.clip((v - 0.7) * 3, 0, 1))
    paint(b, cov_of(sd), np.clip(col, 0, 255))
    paint(b, np.clip(cov_of(sd) - cov_of(sd + 1.2), 0, 1), (74, 78, 88))
    text_c((x0 + x1) * 0.5, (y0 + y1) * 0.5 - 3, freq, (58, 62, 72), 1, 1, 0.9)
    text(x0, y0 - 8, desig, SILK, 1, 1)


def resistor_pads(cu, cx, cy, half):
    cu.pad(cx - half, cy, 3.4, 1.4, "pad")
    cu.pad(cx + half, cy, 3.4, 1.4, "pad")


def resistor(cx, cy, half, bands, desig, value):
    """An axial resistor lying on the board: the colour bands ARE the lane
    marker.  ⚠ It is flat, so it is not an obstacle (see the header's rule)."""
    for sx in (-1, 1):
        p0, p1 = (cx + sx * half, cy), (cx + sx * (half - 5), cy)
        lb = box_seg(p0, p1, 1.8)
        paint(lb, cov_of(sd_seg(lb, p0, p1, 1.8)), (168, 172, 180))
    bx0, bx1, by0, by1 = cx - half + 5, cx + half - 5, cy - 5.0, cy + 5.0
    b = box_rect(bx0, by0, bx1, by1)
    sd = sd_rrect(b, bx0, by0, bx1, by1, 4.0)
    xs, ys = gridxy(b)
    v = (ys - by0) / max(by1 - by0, 1.0)
    col = lerp((228, 210, 176), RES_B, np.clip(v * 1.3, 0, 1) ** 0.7)
    col = lerp(col, (132, 112, 76), np.clip((v - 0.68) * 3.2, 0, 1))
    paint(b, cov_of(sd), np.clip(col, 0, 255))
    n = len(bands)
    for i, ch in enumerate(bands):
        px = bx0 + 3.5 + i * 3.2 + (2.5 if i == n - 1 else 0)
        s2 = np.maximum(sd, sd_rrect(b, px - 1.1, by0, px + 1.1, by1, 0))
        c = np.asarray(BANDC[ch], np.float64)[None, None, :] * (0.72 + 0.4 * v[..., None])
        paint(b, cov_of(s2), np.clip(c, 0, 255))
    paint(b, np.clip(cov_of(sd) - cov_of(sd + 1.0), 0, 1) * 0.5, (110, 92, 62))
    text(cx - half, cy + 8, desig, SILK, 1, 1)
    text(cx - half + 18, cy + 8, value, SILK_D, 1, 1)


def led_pads(cu, cx, cy, r):
    cu.pad(cx - r * 0.55, cy + r + 3, 3.2, 1.3, "pad")
    cu.pad(cx + r * 0.55, cy + r + 3, 3.2, 1.3, "pad")


def led(cx, cy, r, idx, desig):
    """A through-hole LED seen from above.  ⭐ The lens is ONE palette index -
    flat, no shading - because that is what makes lighting it a LUT write.
    Everything that reads as an LED is the body around it."""
    b = box_disc(cx, cy, r + 4)
    sd = sd_disc(b, cx, cy, r + 1.6)
    paint(b, cov_of(sd), (22, 20, 24))                     # the rim seen edge-on
    sdl = sd_disc(b, cx, cy, r)
    cov = cov_of(sdl)
    x0, y0, x1, y1 = b
    m = cov > 0.5
    ys, xs = np.where(m)
    LAMPI[y0 + ys, x0 + xs] = idx
    paint(b, cov, snap565(LAMP_OFF[idx - LAMP0] if idx < SEG0 else SEG_OFF))
    # the cathode flat, on the silkscreen
    sb = box_disc(cx, cy, r + 6)
    sds = sd_disc(sb, cx, cy, r + 3.2)
    xs2, ys2 = gridxy(sb)
    flat = np.maximum(sds, -(xs2 - (cx + r * 0.72)))
    ring = np.clip(cov_of(np.maximum(sds, -(xs2 - (cx - r * 2)))) -
                   cov_of(sds + 1.1), 0, 1)
    paint(sb, ring, SILK_D)
    paint(sb, np.clip(cov_of(flat) - cov_of(flat + 1.1), 0, 1), SILK)
    text(cx - len(desig) * 3.0, cy + r + 7, desig, SILK, 1, 1)


# ── the six-digit display, and the 42 reserved indices it is made of
def seg_boxes(dx, dy):
    """The seven segment rectangles of one digit box at (dx, dy).  DERIVED
    from DIG_W/DIG_H; the JSON carries them so nothing restates them."""
    t = 5
    m = 3
    w, h = DIG_W, DIG_H
    my = (h - 1) // 2
    return [
        (dx + m + t - 2, dy + m, dx + w - m - t + 1, dy + m + t - 1),        # a
        (dx + w - m - t, dy + m + 2, dx + w - m - 1, dy + my - 1),           # b
        (dx + w - m - t, dy + my + 1, dx + w - m - 1, dy + h - m - 3),       # c
        (dx + m + t - 2, dy + h - m - t, dx + w - m - t + 1, dy + h - m - 1),  # d
        (dx + m, dy + my + 1, dx + m + t - 1, dy + h - m - 3),               # e
        (dx + m, dy + m + 2, dx + m + t - 1, dy + my - 1),                   # f
        (dx + m + t - 2, dy + my - t // 2, dx + w - m - t + 1,
         dy + my - t // 2 + t - 1),                                          # g
    ]


def seg_bar(box, idx, horiz):
    """One segment, with the 45 degree mitres a real display has."""
    x0, y0, x1, y1 = box
    # ⚠ NO PADDING.  A mitred bar's distance field reaches half a pixel past
    # the box on the un-mitred axis, so a padded raster paints the segment
    # index one pixel OUTSIDE the box the JSON declares - and checkpcb.py's
    # "every pixel of index i is inside a declared segment" found 36 of the
    # 42 doing exactly that on its first run.
    b = clipbox(x0, y0, x1, y1)
    xs, ys = gridxy(b)
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    hx, hy = (x1 - x0) * 0.5 + 0.5, (y1 - y0) * 0.5 + 0.5
    if horiz:
        d = np.maximum(np.abs(xs - cx) - hx + np.abs(ys - cy), np.abs(ys - cy) - hy)
    else:
        d = np.maximum(np.abs(ys - cy) - hy + np.abs(xs - cx), np.abs(xs - cx) - hx)
    cov = cov_of(d)
    bx0, by0 = b[0], b[1]
    ys2, xs2 = np.where(cov > 0.5)
    LAMPI[by0 + ys2, bx0 + xs2] = idx
    paint(b, cov, snap565(SEG_OFF))


# ═════════════════════════════════════════════════════════ the layout
def cells_of(rect):
    """Which of the 40 x 32 cells a pixel rectangle owns: the ones whose
    CENTRE it contains.  ⭐ This is the only place art becomes collision."""
    x0, y0, x1, y1 = rect
    out = []
    for cy in range(CH):
        py = cy * BLK + BLK // 2
        if not (y0 <= py <= y1):
            continue
        for cx in range(CW):
            px = cx * BLK + BLK // 2
            if x0 <= px <= x1:
                out.append((cx, cy))
    return out


def C(n):
    return n * BLK


def build_layout():
    """Every authored object, once.  The art is drawn from this list and the
    collision grid is derived from it, so a wall with nothing drawn on it or a
    bumper the ball passes through is not a thing that can happen."""
    objs = []

    def add(kind, rect, oid=None, **kw):
        o = dict(kind=kind, rect=[int(rect[0]), int(rect[1]),
                                  int(rect[2]), int(rect[3])], id=oid)
        o.update(kw)
        objs.append(o)
        return o

    # ── the board's own walls: the rim, the top edge, and the backplane
    add("solid", (0, 0, W - 1, C(1) - 1), name="top edge")
    add("solid", (0, 0, C(1) - 1, PLAY_H - 1), name="left rim")
    add("solid", (C(39), 0, W - 1, PLAY_H - 1), name="right rim")
    add("solid", (0, PLAY_H, W - 1, H - 1), name="backplane")

    # ── the plunger lane down the right.  ⚠ THE DIVIDER STARTS AT ROW 6: the
    # kicker above it is four cells tall and a ball caught by it has to have
    # somewhere to go (mkpinball.py paid for this one).
    add("solid", (C(LANE_DIV), C(LANE_DIV_Y0), C(LANE_DIV + 1) - 1, PLAY_H - 1),
        name="lane divider")
    add("plunger", (C(LANE_X0), C(24), C(LANE_X1 + 1) - 1, PLAY_H - 1), oid=0,
        name="plunger seat", fires=(0, -1))
    # ⭐ THE LANE'S MOUTH IS A KICKER AND NOT A MIRROR.  A 45 degree reflector
    # returns the ball's own speed, and at the top of a lane that is its
    # slowest - it falls back in.  A kicker gives it the full speed leftwards
    # and it is out in one frame.
    add("kicker", (C(LANE_X0), C(MOUTH_Y0), C(LANE_X1 + 1) - 1,
                   C(MOUTH_Y1 + 1) - 1), oid=0, name="K1 lane mouth",
        dirv=(-1.0, 0.0), power=1.0)

    # ── ⭐ THE ROLLOVER BANK, all the way across the arch.  Not three lanes:
    # SIX groups of five test pads spanning columns 4..33.  A ball leaving the
    # lane crosses this row exactly once and wherever it happens to be, so a
    # sparse bank is a table that scores by luck.
    for i in range(6):
        cx0 = 4 + i * 5
        add("rollover", (C(cx0), C(3), C(cx0 + 5) - 1, C(4) - 1), oid=i,
            name="TP%d" % (i + 1), pads=5, lamp=LAMP0 + (2 if i < 3 else 3))

    # ── the bumpers: eight DIP ICs in two staggered bands.  ⭐ TWO BANDS, and
    # that is a playability decision: one band of four covered twelve of the
    # arch's thirty columns and the ball went between them.
    PARTS = ["74LS00", "74LS04", "74LS74", "74LS86",
             "74LS08", "74LS32", "74LS132", "74LS393"]
    band = [(4, 6), (11, 6), (24, 6), (31, 6),
            (7, 10), (14, 10), (21, 10), (28, 10)]
    for i, (cx0, cy0) in enumerate(band):
        add("bumper", (C(cx0), C(cy0), C(cx0 + 3) - 1, C(cy0 + 2) - 1), oid=i,
            name="U%d" % (i + 1), part=PARTS[i], pins=14,
            lamp=LAMP0 + (0 if cy0 == 6 else 1))

    # ── the drop targets: two DIP-switch banks, four switches each
    add("switchbank", (C(2), C(13), C(6) - 1, C(15) - 1), oid=0, name="SW1",
        n=4, first=0, lamp=LAMP0 + 4)
    add("switchbank", (C(32), C(13), C(36) - 1, C(15) - 1), oid=1, name="SW2",
        n=4, first=4, lamp=LAMP0 + 5)

    # ── the posts: four electrolytics and the crystal
    for i, cx0 in enumerate((8, 12, 24, 28)):
        add("solid", (C(cx0), C(13), C(cx0 + 2) - 1, C(15) - 1), oid=i,
            name="C%d" % (i + 1), part="cap", value="470U")
    add("solid", (C(17), C(12), C(21) - 1, C(13) - 1), name="Y1", part="xtal",
        value="14.318")

    # ── the two big parts, and the centre-piece
    add("solid", (C(15), C(15), C(23) - 1, C(18) - 1), name="U9",
        part="HD63C09EP", pins=40)
    add("solid", (C(7), C(16), C(12) - 1, C(18) - 1), name="U10",
        part="2716", pins=24)
    add("solid", (C(26), C(16), C(31) - 1, C(18) - 1), name="U11",
        part="2114", pins=18)

    # ── ⭐ THE CHEVRON UNDER THE CPU: two 45 degree traces that take a ball
    # off the middle of the board and put it over a flipper.  Without it the
    # centre drains straight down the slot.
    for (cx0, cy0) in ((18, 18), (17, 19)):
        add("slope_l", (C(cx0), C(cy0), C(cx0 + 1) - 1, C(cy0 + 1) - 1),
            name="chevron L")
    for (cx0, cy0) in ((19, 18), (20, 19)):
        add("slope_r", (C(cx0), C(cy0), C(cx0 + 1) - 1, C(cy0 + 1) - 1),
            name="chevron R")

    # ── the outer funnel: a 45 degree board edge down each side
    for i in range(4):
        add("slope_r", (C(2 + i), C(16 + i), C(3 + i) - 1, C(17 + i) - 1),
            name="funnel L")
        add("slope_l", (C(35 - i), C(16 + i), C(36 - i) - 1, C(17 + i) - 1),
            name="funnel L")
        add("solid", (C(1), C(16 + i), C(2 + i) - 1, C(17 + i) - 1),
            name="apron L")
        add("solid", (C(36 - i), C(16 + i), C(36) - 1, C(17 + i) - 1),
            name="apron R")
    add("solid", (C(1), C(20), C(6) - 1, PLAY_H - 1), name="apron L")
    add("solid", (C(32), C(20), C(36) - 1, PLAY_H - 1), name="apron R")
    add("solid", (C(8), C(20), C(9) - 1, PLAY_H - 1), name="outlane divider L")
    add("solid", (C(29), C(20), C(30) - 1, PLAY_H - 1), name="outlane divider R")

    # ── the slingshots: the two kickers that keep the ball off the outlanes
    add("kicker", (C(8), C(18), C(10) - 1, C(20) - 1), oid=1, name="K2 sling L",
        dirv=(0.78, -0.63), power=0.85, lamp=LAMP0 + 6)
    add("kicker", (C(28), C(18), C(30) - 1, C(20) - 1), oid=2, name="K3 sling R",
        dirv=(-0.78, -0.63), power=0.85, lamp=LAMP0 + 7)

    # ── the edge connector, and the three slots milled through it
    add("edge", (C(1), EDGE_Y0, C(36) - 1, PLAY_H - 1), name="J1")
    add("drain", (DRAIN_X0, C(22), DRAIN_X1, PLAY_H - 1), oid=0,
        name="centre slot")
    add("drain", (OUT_L[0], C(20), OUT_L[1], PLAY_H - 1), oid=1,
        name="outlane L")
    add("drain", (OUT_R[0], C(20), OUT_R[1], PLAY_H - 1), oid=2,
        name="outlane R")

    # ── the return lanes: a chute between two fingers, onto the flipper
    add("return", (C(9), C(22), C(15) - 1, EDGE_Y0 - 1), oid=0,
        name="return L", to=(248, 356))
    add("return", (C(23), C(22), C(29) - 1, EDGE_Y0 - 1), oid=1,
        name="return R", to=(360, 356))

    # ── the lamps that are not on a part of their own
    for i, (cx0, cy0, lid) in enumerate(
            ((8, 6, 0), (29, 6, 0), (12, 10, 1), (25, 10, 1),
             (5, 4, 2), (32, 4, 2), (15, 4, 3), (22, 4, 3),
             (3, 10, 4), (34, 10, 5), (13, 20, 6), (24, 20, 7))):
        add("led", (C(cx0), C(cy0), C(cx0 + 1) - 1, C(cy0 + 1) - 1),
            oid=i, name="D%d" % (i + 9), lamp=LAMP0 + lid)

    # ── the resistors, which are the lane markers
    for i, (cx0, cy0, bands, val) in enumerate(
            ((9, 5, "nkro", "10K"), (26, 5, "nkro", "10K"),
             (9, 20, "ryod", "4K7"), (26, 20, "ryod", "4K7"),
             (1, 20, "nkrd", "1K0"), (33, 20, "nkrd", "1K0"))):
        add("res", (C(cx0), C(cy0), C(cx0 + 3) - 1, C(cy0 + 1) - 1), oid=i,
            name="R%d" % (i + 1), bands=bands, value=val)

    return objs


def derive_grid(objs):
    """The 40 x 32 collision grid and its id grid, in PRIORITY order."""
    kind = np.zeros((CH, CW), np.uint8)
    ident = np.zeros((CH, CW), np.uint8)
    order = {k: i for i, k in enumerate(PRIORITY)}

    def paint_cells(k, rect, oid):
        p = order[k]
        for (cx, cy) in cells_of(rect):
            if order.get(inv[kind[cy, cx]], -1) <= p:
                kind[cy, cx] = KINDS[k]
                ident[cy, cx] = 0 if oid is None else oid
    inv = {v: k for k, v in KINDS.items()}

    for o in objs:
        k = o["kind"]
        if k == "switchbank":
            n, x0, y0, x1, y1 = o["n"], *o["rect"]
            pitch = (x1 - x0 + 1) / float(n)
            for i in range(n):
                paint_cells("target",
                            (x0 + pitch * i, y0, x0 + pitch * (i + 1) - 1, y1),
                            o["first"] + i)
        elif k == "edge":
            paint_cells("solid", o["rect"], 0)
        elif k in ("led", "res"):
            pass                       # flat: not an obstacle (see the header)
        elif k in KINDS:
            paint_cells(k, o["rect"], o["id"])

    # the flipper zones are DERIVED from the pivots, the length and the two
    # angles - the swept rectangle, minus whatever overhangs the drain slot
    zones = {}
    for side in ("l", "r"):
        px, py = FLIP_PIV[side]
        pts = []
        for deg in (FLIP_REST, FLIP_ACTIVE, 0.0):
            a = math.radians(deg) if side == "l" else math.pi - math.radians(deg)
            pts.append((px + math.cos(a) * FLIP_LEN, py + math.sin(a) * FLIP_LEN))
        xs = [px] + [p[0] for p in pts]
        ys = [py] + [p[1] for p in pts]
        rect = (min(xs) - 6, min(ys) - 6, max(xs) + 6, max(ys) + 6)
        cs = [(cx, cy) for (cx, cy) in cells_of(rect)
              if not (DRAIN_X0 <= cx * BLK + BLK // 2 <= DRAIN_X1)]
        zones[side] = dict(rect=[int(v) for v in rect], cells=cs)
        for (cx, cy) in cs:
            k = "flip_l" if side == "l" else "flip_r"
            if order.get(inv[kind[cy, cx]], -1) <= order[k]:
                kind[cy, cx] = KINDS[k]
                ident[cy, cx] = 0 if side == "l" else 1

    # the drain and the plunger are last in PRIORITY, so re-apply them
    for o in objs:
        if o["kind"] in ("drain", "plunger"):
            paint_cells(o["kind"], o["rect"], o["id"])
    return kind, ident, zones


# ═══════════════════════════════════════════════════════════════ the art
def route_bus(cu, y, n, x0, x1, pitch=7, w=3.0):
    """n parallel traces - the bus that says a person laid this board out."""
    for i in range(n):
        yy = y + i * pitch
        jog = 18 + i * pitch
        cu.trace([(x0, yy), (x0 + jog, yy), (x0 + jog + 10, yy - 10),
                  (x1 - jog - 10, yy - 10), (x1 - jog, yy), (x1, yy)], w)


def draw_traces(cu, objs):
    """⭐ THE BALL PATHS ARE THE HEAVY TRACES.  Every route the ball takes is
    a 10-pixel power trace; everything thinner is signal.  That is the whole
    conceit of the board: the layout IS the playfield."""
    # the outer loop: out of the lane mouth, over the arch and down the left
    cu.trace([(600, 70), (600, 44), (578, 22), (60, 22), (26, 56), (26, 300)], 10)
    cu.trace([(614, 70), (614, 30), (606, 22)], 6)
    # the right-hand return, down the outside
    cu.trace([(566, 40), (566, 96), (574, 104), (574, 296)], 8)
    # the rollover bank's bus: one trace along the pads
    cu.trace([(58, 56), (540, 56)], 5)
    # the arch's ground ties
    cu.trace([(64, 40), (120, 40), (128, 32), (496, 32), (504, 40), (536, 40)], 4)
    # the bus between the two bumper bands
    route_bus(cu, 140, 5, 52, 548, 7, 3.0)
    # power rails, left and right, down to the edge connector
    cu.trace([(26, 300), (26, 330), (44, 348), (44, 384)], 10)
    cu.trace([(574, 296), (574, 330), (556, 348), (556, 384)], 10)
    # the return lanes, drawn as a pair of traces that funnel onto a flipper
    cu.trace([(148, 360), (176, 360), (200, 384)], 9)
    cu.trace([(148, 376), (192, 376), (208, 392)], 5)
    cu.trace([(492, 360), (464, 360), (440, 384)], 9)
    cu.trace([(492, 376), (448, 376), (432, 392)], 5)
    # the chevron under the CPU, which is a trace pair as well as a deflector
    cu.trace([(304, 292), (280, 316), (256, 316)], 9)
    cu.trace([(320, 292), (344, 316), (368, 316)], 9)
    # the slingshots' feeds, into the back of each wedge
    cu.trace([(112, 300), (128, 300)], 5)
    cu.trace([(528, 300), (512, 300)], 5)
    # signal traces from the CPU out to the world
    cu.trace([(240, 256), (216, 280), (160, 280)], 3)
    cu.trace([(240, 248), (208, 248), (196, 260)], 3)
    cu.trace([(368, 256), (392, 280), (448, 280)], 3)
    cu.trace([(368, 248), (400, 248), (412, 260)], 3)
    cu.trace([(272, 240), (272, 212), (288, 196)], 3)
    cu.trace([(336, 240), (336, 212), (320, 196)], 3)
    # the drop-switch banks' commons
    cu.trace([(40, 208), (40, 188), (56, 172)], 4)
    cu.trace([(560, 208), (560, 188), (544, 172)], 4)
    # a scatter of vias where the traces change layer
    for (vx, vy) in ((26, 56), (26, 300), (60, 22), (578, 22), (574, 104),
                     (256, 316), (368, 316), (160, 288), (464, 288),
                     (196, 260), (412, 260), (288, 196), (320, 196),
                     (56, 172), (544, 172), (44, 384), (556, 384)):
        via(cu, vx, vy, 5.0, 2.0)
    # free vias, spread over the pour by a deterministic hash
    for i in range(46):
        vx = 24 + int(ihash(np.array([i]), np.array([3]), 21)[0] * 580)
        vy = 24 + int(ihash(np.array([i]), np.array([9]), 22)[0] * 340)
        via(cu, vx, vy, 4.0, 1.6)


def draw_fingers(cu, objs):
    """The edge connector: gold fingers, chamfered, with a trace off each."""
    o = [x for x in objs if x["kind"] == "edge"][0]
    x0, y0, x1, y1 = o["rect"]
    slots = [(DRAIN_X0, DRAIN_X1), OUT_L, OUT_R]
    n = 0
    fingers = []
    x = x0 + 3
    while x + FINGER_W <= x1:
        mid = x + FINGER_W / 2.0
        if not any(a - 4 <= mid <= b + 4 for a, b in slots):
            fingers.append((x, x + FINGER_W - 1))
            # the trace that leaves it, up into the board
            up = 9 + (n % 4) * 5
            if n % 3 == 2:
                cu.trace([(mid, y0 - 2), (mid, y0 - up),
                          (mid + (8 if n % 2 else -8), y0 - up - 8)], 4.0)
            else:
                cu.trace([(mid, y0 - 2), (mid, y0 - up)], 4.0)
            n += 1
        x += FINGER_PITCH
    return fingers


def paint_fingers(fingers, y0, y1):
    for (fx0, fx1) in fingers:
        b = box_rect(fx0, y0, fx1, y1)
        sd = sd_rrect(b, fx0, y0, fx1, y1, 1.0)
        xs, ys = gridxy(b)
        t = np.clip((xs - fx0) / max(fx1 - fx0, 1.0), 0, 1)
        shade = 1.0 - np.abs(t - 0.40) * 1.9
        col = lerp(GOLD_D, GOLD, np.clip(shade, 0, 1) ** 0.8)
        col = lerp(col, GOLD_H, np.clip((shade - 0.82) * 5.0, 0, 1) * 0.85)
        # the chamfer at the very bottom, where the socket wipes it
        v = np.clip((ys - (y1 - 7)) / 7.0, 0, 1)
        col = lerp(col, np.asarray(GOLD_D) * 0.75, v ** 1.5)
        paint(b, cov_of(sd), np.clip(col, 0, 255))


def draw_slots(objs):
    """The three milled slots: straight through the board, and they are the
    drains.  ⭐ A ball that reaches one is off the board, which is the most
    literal drain a PCB can have."""
    for o in objs:
        if o["kind"] != "drain":
            continue
        x0, y0, x1, y1 = o["rect"]
        b = box_rect(x0, y0, x1, y1, 10)
        sd = sd_rrect(b, x0, y0, x1, y1, 8.0)
        xs, ys = gridxy(b)
        # the keepout the router left: mask pulled back to bare glass
        paint(b, np.clip(cov_of(sd - 8.0) - cov_of(sd - 3.0), 0, 1) * 0.92,
              np.asarray(FR4) * 0.78)
        # the routed wall, lit from the top left the way everything else is
        wall = np.clip(cov_of(sd - 3.0) - cov_of(sd), 0, 1)
        side = np.clip(((x0 + x1) * 0.5 - xs) / 10.0 + 0.5, 0, 1) \
            * np.clip(((y0 + y1) * 0.5 - ys) / 40.0 + 0.7, 0, 1)
        paint(b, wall, np.clip(lerp((84, 74, 44), (186, 170, 116), side),
                               0, 255))
        paint(b, cov_of(sd), SLOT)
        # and the shadow the ball falls into
        paint(b, np.clip(cov_of(sd) - cov_of(sd + 3.0), 0, 1) * 0.55,
              (2, 2, 4))


def draw_components(objs, cu, pads_only):
    """Two passes over the same list: the pads go into the copper collector
    before the pour is drawn, the bodies go on top of everything."""
    acts = {}
    for o in objs:
        k, (x0, y0, x1, y1) = o["kind"], o["rect"]
        if k == "bumper":
            if pads_only:
                dip_pads(cu, x0, y0, x1, y1, o["pins"])
            else:
                dip(x0, y0, x1, y1, o["pins"], o["part"], o["name"])
        elif k == "switchbank":
            if pads_only:
                dip_pads(cu, x0, y0, x1, y1, o["n"] * 2)
            else:
                acts[o["id"]] = dipsw(x0, y0, x1, y1, o["n"], o["name"])
        elif k == "solid" and o.get("part") == "cap":
            cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
            if pads_only:
                elcap_pads(cu, cx, cy, 13.0)
            else:
                elcap(cx, cy, 13.0, o["name"], o["value"])
        elif k == "solid" and o.get("part") == "xtal":
            if pads_only:
                xtal_pads(cu, x0, y0, x1, y1)
            else:
                xtal(x0, y0 + 2, x1, y1 - 3, o["name"], o["value"])
        elif k == "solid" and o.get("pins"):
            if pads_only:
                dip_pads(cu, x0, y0, x1, y1, o["pins"])
            else:
                dip(x0, y0, x1, y1, o["pins"], o["part"], o["name"])
        elif k == "led":
            cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
            if pads_only:
                led_pads(cu, cx, cy, 5.0)
            else:
                led(cx, cy, 5.0, o["lamp"], o["name"])
        elif k == "res":
            cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
            if pads_only:
                resistor_pads(cu, cx, cy, 21.0)
            else:
                resistor(cx, cy, 21.0, o["bands"], o["name"], o["value"])
    return acts


def draw_rollovers(cu, objs, pads_only):
    for o in objs:
        if o["kind"] != "rollover":
            continue
        x0, y0, x1, y1 = o["rect"]
        cy = (y0 + y1) * 0.5
        for i in range(o["pads"]):
            cx = x0 + BLK * (i + 0.5)
            if pads_only:
                cu.pad(cx, cy, 6.0, 2.6, "pad")
                teardrop(cu, cx, cy, 6.0, (cx - 16, cy), 5.0)
                teardrop(cu, cx, cy, 6.0, (cx + 16, cy), 5.0)
        if not pads_only:
            text_c((x0 + x1) * 0.5, y0 - 11, o["name"], SILK, 1, 1)


def draw_lane():
    """The plunger lane: two silk rails, the kicker at its mouth and the
    ball-return channel between them."""
    x0, x1 = C(LANE_X0), C(LANE_X1 + 1) - 1
    for lx in (x0 + 1, x1 - 1):
        p0, p1 = (lx, C(1)), (lx, PLAY_H - 6)
        b = box_seg(p0, p1, 1.4)
        paint(b, cov_of(sd_seg(b, p0, p1, 1.4)) * 0.55, SILK_D)
    text(x0 + 3, C(5) + 2, "K1", SILK, 1, 1)
    for k in range(7):                       # the kicker coil, as silkscreen
        yy = C(1) + 6 + k * 7
        p0, p1 = (x0 + 4, yy), (x1 - 4, yy + 4)
        b = box_seg(p0, p1, 1.4)
        paint(b, cov_of(sd_seg(b, p0, p1, 1.4)) * 0.7, SILK_D)
    text(x0 + 2, C(23), "BALL", SILK_D, 1, 1)
    text(x0 + 2, C(23) + 10, "LANE", SILK_D, 1, 1)


def draw_kickers(objs):
    """A slingshot is a wedge of pour with a bright gold face - the face is
    what the ball leaves on."""
    for o in objs:
        if o["kind"] != "kicker" or o["id"] == 0:
            continue
        x0, y0, x1, y1 = o["rect"]
        xs, ys = gridxy((x0, y0, x1, y1))
        left = o["id"] == 1
        f = ((xs - x0) + (y1 - ys)) - (x1 - x0) if left else \
            ((x1 - xs) + (y1 - ys)) - (x1 - x0)
        b = (x0, y0, x1, y1)
        # ⭐ A WEDGE OF BARE COPPER, not a tinted bit of mask.  The slingshot
        # is the one thing on the lower board that has to say "I will hit
        # you", and on a PCB the way to say that is to take the mask off.
        inside = np.clip(-f, 0, 1)
        sh = np.clip((ys - y0) / 34.0 + np.abs(f) / 44.0, 0, 1)
        paint(b, inside * 0.97,
              np.clip(lerp(CU_M, lerp(CU_M, CU_D, 0.55), sh ** 0.8), 0, 255))
        paint(b, np.clip(1.0 - np.abs(f + 1.5) / 2.0, 0, 1), GOLD_H)
        paint(b, np.clip(1.0 - np.abs(f + 4.5) / 2.0, 0, 1) * 0.85, GOLD_D)
        paint(b, np.clip(1.0 - np.abs(f - 1.5) / 1.5, 0, 1) * 0.8, MASK_D)
        # three pads down the face: the rubber, as a real board would carry it
        span = x1 - x0
        for k in range(3):
            t = 0.2 + k * 0.3
            px = x0 + t * span - 4 if left else x1 - t * span + 4
            py = y0 + t * span + 5
            pb = box_disc(px, py, 3.6)
            paint(pb, cov_of(sd_disc(pb, px, py, 3.6)), GOLD)
            paint(pb, cov_of(sd_disc(pb, px, py, 1.5)), (18, 16, 14))
        text(x1 - 13 if left else x0 + 2, y0 + 2, o["name"].split()[0],
             SILK, 1, 1)


def draw_flipper_silk(zones):
    """⭐ THE FLIPPERS ARE NOT IN THE PICTURE - they move, and the scene draws
    them.  What is in the picture is their footprint: the plated pivot and the
    silkscreen sweep, which is exactly what a board would carry."""
    for side in ("l", "r"):
        px, py = FLIP_PIV[side]
        for deg, alpha in ((FLIP_REST, 0.95), (FLIP_ACTIVE, 0.45)):
            a = math.radians(deg) if side == "l" else math.pi - math.radians(deg)
            tip = (px + math.cos(a) * FLIP_LEN, py + math.sin(a) * FLIP_LEN)
            b = box_seg((px, py), tip, 12.0)
            sd = sd_seg(b, (px, py), tip, 12.0)
            paint(b, np.clip(cov_of(sd) - cov_of(sd + 1.4), 0, 1) * alpha,
                  SILK if alpha > 0.6 else SILK_D)
            if alpha > 0.6:
                pb = box_disc(tip[0], tip[1], 5)
                paint(pb, np.clip(cov_of(sd_disc(pb, tip[0], tip[1], 4.0)) -
                                  cov_of(sd_disc(pb, tip[0], tip[1], 2.6)), 0, 1),
                      GOLD)
        pb = box_disc(px, py, 9)
        paint(pb, cov_of(sd_disc(pb, px, py, 7.5)), GOLD_D)
        paint(pb, np.clip(cov_of(sd_disc(pb, px, py, 7.0)) -
                          cov_of(sd_disc(pb, px, py, 4.6)), 0, 1), GOLD)
        paint(pb, cov_of(sd_disc(pb, px, py, 3.2)), (14, 12, 12))
        text(px - 8, py + 11, "FL" + ("1" if side == "l" else "2"), SILK, 1, 1)


def draw_returns(objs):
    for o in objs:
        if o["kind"] != "return":
            continue
        x0, y0, x1, y1 = o["rect"]
        lft = o["id"] == 0
        # a silk arrow along the chute, pointing at the flipper it feeds
        ax = x0 + 26 if lft else x1 - 26
        for k in range(4):
            px = ax + (k * 17 if lft else -k * 17)
            py = y0 + 11 + k * 3
            for (dx, dy) in (((0, 0), (-4, -4), (-4, 4)) if lft else
                             ((0, 0), (4, -4), (4, 4))):
                b = box_disc(px + dx, py + dy, 1.6)
                paint(b, cov_of(sd_disc(b, px + dx, py + dy, 1.6)) * 0.9,
                      SILK)
        text(x0 + 2 if lft else x1 - 20, y0 + 1,
             "IN" + ("L" if lft else "R"), SILK, 1, 1)


def draw_silk_border():
    """The board outline, its fiducials and the four mounting holes."""
    for (a, b) in (((6, 6), (W - 7, 6)), ((6, PLAY_H - 7), (W - 7, PLAY_H - 7)),
                   ((6, 6), (6, PLAY_H - 7)), ((W - 7, 6), (W - 7, PLAY_H - 7))):
        bb = box_seg(a, b, 1.6)
        paint(bb, cov_of(sd_seg(bb, a, b, 1.6)) * 0.8, SILK_D)
    for (hx, hy) in ((28, 28), (W - 29, 28)):
        b = box_disc(hx, hy, 13)
        paint(b, np.clip(cov_of(sd_disc(b, hx, hy, 11.0)) -
                         cov_of(sd_disc(b, hx, hy, 6.4)), 0, 1), GOLD)
        paint(b, cov_of(sd_disc(b, hx, hy, 6.0)), (10, 10, 12))
        paint(b, np.clip(cov_of(sd_disc(b, hx, hy, 12.5)) -
                         cov_of(sd_disc(b, hx, hy, 11.4)), 0, 1) * 0.7, SILK_D)


def draw_legend():
    text(52, 5, "ARM6309 PINBALL PLAYFIELD", SILK, 2, 1)
    text(W - 172, 4, "(C) 1984 VIDEO3 SYSTEMS", SILK_D, 1, 1)
    text(W - 172, 14, "ASSY 640-512-8BPP  REV C", SILK_D, 1, 1)
    text(594, 118, "+5V", SILK, 1, 1)
    text(594, 130, "GND", SILK_D, 1, 1)
    text(594, 300, "SW9", SILK_D, 1, 1)
    text(594, 312, "PLGR", SILK_D, 1, 1)
    text(20, 348, "FAB 84-1207", (84, 72, 40), 1, 1)
    text(20, 360, "UL 94V-0  2 LAYER", (84, 72, 40), 1, 1)
    text(C(1) + 2, EDGE_Y0 - 10, "J1", SILK, 1, 1)


def draw_backplane(objs):
    """The socket the card plugs into, the six-digit display and the eight
    lamps.  ⚠ It is off the playfield, and the camera only reaches it when the
    ball is low - which is exactly when a score is read."""
    y0 = PLAY_H
    n = vnoise(19, 31)
    paint((0, y0, W - 1, H - 1), np.ones((H - y0, W)),
          np.clip(lerp(BPLANE, (26, 28, 34), n[y0:]), 0, 255))
    # the socket housing, with the card's fingers entering it
    sb = box_rect(8, y0, W - 9, y0 + 26)
    sd = sd_rrect(sb, 8, y0, W - 9, y0 + 26, 3.0)
    xs, ys = gridxy(sb)
    v = np.clip((ys - y0) / 26.0, 0, 1)
    paint(sb, cov_of(sd), np.clip(lerp((56, 56, 64), SOCKET, v ** 0.6), 0, 255))
    paint(sb, np.clip(cov_of(sd) - cov_of(sd + 1.4), 0, 1), (74, 74, 84))
    slotb = box_rect(16, y0 + 3, W - 17, y0 + 9)
    paint(slotb, cov_of(sd_rrect(slotb, 16, y0 + 3, W - 17, y0 + 9, 1.5)), (8, 8, 10))
    text(14, y0 + 14, "P1", SILK_D, 1, 1)
    text(W - 40, y0 + 14, "P1", SILK_D, 1, 1)

    # DS1: the six-digit display
    dx0, dy0 = DIG_X0 - 10, DIG_Y0 - 10
    dx1 = DIG_X0 + NDIG * DIG_W + (NDIG - 1) * DIG_GAP + 9
    dy1 = DIG_Y0 + DIG_H + 9
    b = box_rect(dx0, dy0, dx1, dy1)
    sd = sd_rrect(b, dx0, dy0, dx1, dy1, 2.0)
    xs, ys = gridxy(b)
    v = np.clip((ys - dy0) / max(dy1 - dy0, 1.0), 0, 1)
    paint(b, cov_of(sd), np.clip(lerp((44, 44, 50), (16, 16, 20), v ** 0.5), 0, 255))
    ib = box_rect(dx0 + 4, dy0 + 4, dx1 - 4, dy1 - 4)
    paint(ib, cov_of(sd_rrect(ib, dx0 + 4, dy0 + 4, dx1 - 4, dy1 - 4, 1.0)),
          (10, 10, 13))
    text(dx0, dy0 - 10, "DS1", SILK, 1, 1)
    text(dx1 - 34, dy0 - 10, "SCORE", SILK_D, 1, 1)
    digits = []
    for d in range(NDIG):
        bx = DIG_X0 + d * (DIG_W + DIG_GAP)
        boxes = seg_boxes(bx, DIG_Y0)
        for s, sbx in enumerate(boxes):
            seg_bar(sbx, SEG0 + d * 7 + s, s in (0, 3, 6))
        digits.append(dict(box=[bx, DIG_Y0, bx + DIG_W - 1, DIG_Y0 + DIG_H - 1],
                           segs=[list(map(int, v2)) for v2 in boxes]))
        if d in (1, 3):
            px = bx + DIG_W + DIG_GAP // 2
            pb = box_disc(px, DIG_Y0 + DIG_H - 4, 2.0)
            paint(pb, cov_of(sd_disc(pb, px, DIG_Y0 + DIG_H - 4, 2.0)),
                  snap565(SEG_OFF))

    # the eight lamps, D1..D8, four each side of the display
    lamps = []
    for k in range(NLAMP):
        cx = 52 + k * 34 if k < 4 else W - 52 - (7 - k) * 34
        cy = DIG_Y0 + 18
        led(cx, cy, 7.0, LAMP0 + k, "D%d" % (k + 1))
        lamps.append(dict(id=k, index=LAMP0 + k, desig="D%d" % (k + 1),
                          box=[int(cx - 7), int(cy - 7), int(cx + 7), int(cy + 7)]))
    for (hx, hy) in ((24, H - 22), (W - 25, H - 22)):
        b = box_disc(hx, hy, 13)
        paint(b, np.clip(cov_of(sd_disc(b, hx, hy, 11.0)) -
                         cov_of(sd_disc(b, hx, hy, 6.4)), 0, 1), GOLD)
        paint(b, cov_of(sd_disc(b, hx, hy, 6.0)), (6, 6, 8))
    text(46, H - 14, "MADE IN TAIWAN", SILK_D, 1, 1)
    text_c(W / 2.0, H - 14, "ARM6309 / VIDEO3   640 X 512 X 8", SILK_D, 1, 1)
    text(W - 138, H - 14, "LOT 8451", SILK_D, 1, 1)
    return digits, lamps


RELIEFS = [
    [0, 0, W - 1, 4], [0, PLAY_H - 5, W - 1, PLAY_H - 1],      # the routed edge
    [0, 0, 4, PLAY_H - 1], [W - 5, 0, W - 1, PLAY_H - 1],
    [C(1), EDGE_Y0 - 6, C(36) - 1, PLAY_H - 1],                # the finger field
    [12, 342, 85, 374],                                        # the fab stamp
]


def render(objs):
    """Everything, in the order a board is actually made."""
    bare = np.zeros((H, W), bool)
    for (x0, y0, x1, y1) in RELIEFS:
        bare[y0:y1 + 1, x0:x1 + 1] = True
    substrate()
    soldermask(bare)

    cu = Cu()
    draw_traces(cu, objs)
    draw_rollovers(cu, objs, True)
    draw_components(objs, cu, True)
    fingers = draw_fingers(cu, objs)
    cu.cover()
    # components keep the pour off themselves as well
    for o in objs:
        if o["kind"] in ("bumper", "switchbank", "res", "led") or o.get("part"):
            x0, y0, x1, y1 = o["rect"]
            b = clipbox(x0 - 3, y0 - 3, x1 + 3, y1 + 3)
            if b:
                keepout(b, np.ones((b[3] - b[1] + 1, b[2] - b[0] + 1)))
    # ⭐ THE POUR IS EXACTLY THE WALLS, and that is not decoration.  A cell
    # the ball cannot enter has to LOOK different from one it flies through,
    # or "the collision grid agrees with the art" is a claim about nothing:
    # checkpcb.py reads the hatch back out of the picture.  Pouring ground
    # copper around the edge of a board and leaving the middle clear is also
    # exactly what a 1984 layout did, so the rule and the subject agree.
    kgrid, _ig, _z = derive_grid(objs)
    region = np.zeros((H, W), bool)
    for cy in range(PLAY_R):
        for cx in range(CW):
            if kgrid[cy, cx] == KINDS["solid"]:
                region[C(cy):C(cy + 1), C(cx):C(cx + 1)] = True
    region &= ~bare
    groundpour(region)
    cu.draw()

    fb = (C(1), EDGE_Y0 - 6, C(36) - 1, PLAY_H - 1)
    n = vnoise(13, 43)[EDGE_Y0 - 6:PLAY_H, C(1):C(36)]
    paint(fb, np.full((PLAY_H - EDGE_Y0 + 6, C(35)), 0.9),
          np.clip(lerp((96, 84, 52), (128, 114, 70), n), 0, 255))
    paint_fingers(fingers, EDGE_Y0 - 2, PLAY_H - 1)
    draw_silk_border()
    draw_legend()
    draw_kickers(objs)
    draw_lane()
    draw_returns(objs)
    draw_rollovers(cu, objs, False)
    acts = draw_components(objs, cu, False)
    _k, _i, zones = derive_grid(objs)
    draw_flipper_silk(zones)
    draw_slots(objs)
    digits, lamps = draw_backplane(objs)
    return acts, digits, lamps, fingers


# ═════════════════════════════════════════════════════════════════ output
def b64(a):
    return base64.b64encode(bytes(bytearray(np.asarray(a).reshape(-1).tolist()))).decode()


def nudge(c, taken, what):
    """Move a reserved colour off any art colour.  ⚠ Being able to tell a lit
    lamp from a wall is what the whole lamp gate rests on, so a collision is
    fixed here and SAID OUT LOUD, not asserted away."""
    if rgb565(c) not in taken:
        return c
    for d in range(1, 40):
        for dv in ((d, 0, 0), (0, d, 0), (0, 0, d), (-d, 0, 0), (0, -d, 0),
                   (0, 0, -d)):
            c2 = tuple(max(0, min(255, c[i] + dv[i])) for i in range(3))
            if rgb565(c2) not in taken:
                print("      nudged %s %s -> %s (it was also an art colour)"
                      % (what, c, c2))
                return c2
    raise AssertionError("no free RGB565 near %s for %s" % (c, what))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    objs = build_layout()
    acts, digits, lamps, fingers = render(objs)
    kind, ident, zones = derive_grid(objs)

    # ── the palette, over the art only: a lamp lens and a segment are not a
    # rendering of anything, so they must not spend an art entry either
    sample = IMG[LAMPI == 0].astype(np.uint8)
    q = Quant(build_palette(sample))
    pic = q.dither(IMG, skip=(LAMPI != 0))

    # ⭐ the reserved indices, painted AFTER the dither
    pic[LAMPI != 0] = LAMPI[LAMPI != 0]

    # ⛔ index 0 is the key; the dither cannot make one and nothing else may
    bad0 = int((pic == 0).sum())
    assert bad0 == 0, "%d pixels are index 0, the copy engine's colour key" % bad0
    used = set(int(v) for v in np.unique(LAMPI) if v)
    assert used == set(range(LAMP0, 256)), (
        "every reserved entry must be painted somewhere, or nothing can show it",
        sorted(set(range(LAMP0, 256)) - used))
    art = np.unique(pic[LAMPI == 0])
    assert art.max() <= NART, ("the dither produced a RESERVED index",
                               [int(v) for v in art if v > NART])

    # ── the palette file: 205 art colours, then the lamps and the segments OUT
    pal = [rgb565(c) for c in q.rgb.astype(int)]
    taken = set(pal) | {0xF81F}
    lon = [nudge(c, taken, "lamp %d on" % k) for k, c in enumerate(LAMP_ON)]
    loff = [nudge(c, taken, "lamp %d off" % k) for k, c in enumerate(LAMP_OFF)]
    son = nudge(SEG_ON, taken, "segment on")
    soff = nudge(SEG_OFF, taken, "segment off")
    for nm, c in ([("lamp %d on" % k, lon[k]) for k in range(NLAMP)]
                  + [("lamp %d off" % k, loff[k]) for k in range(NLAMP)]
                  + [("segment on", son), ("segment off", soff)]):
        assert rgb565(c) not in taken, (
            "%s is also an art colour - the lamp gate could not tell them "
            "apart" % nm, c)

    palb = [0xF8, 0x1F]                       # ⭐ entry 0: the key, magenta
    for v in pal:
        palb += [v >> 8, v & 255]
    for c in loff:
        v = rgb565(c)
        palb += [v >> 8, v & 255]
    for _ in range(NSEG):
        v = rgb565(soff)
        palb += [v >> 8, v & 255]
    assert len(palb) == 512

    # ── the probes: where each reserved index can be found in the picture
    probes = {}
    for i in range(LAMP0, 256):
        ys, xs = np.where(LAMPI == i)
        probes[i] = [int(ys[0]), int(xs[0]), int(len(ys))]

    pp = os.path.join(here, "pcbtable.pic")
    open(pp, "wb").write(pic.tobytes())
    assert os.path.getsize(pp) == W * H
    lp = os.path.join(here, "pcbtable.pal")
    open(lp, "wb").write(bytes(bytearray(palb)))

    # ── the JSON: everything the scene and the checker read
    bumpers = []
    for o in objs:
        if o["kind"] != "bumper":
            continue
        x0, y0, x1, y1 = o["rect"]
        bumpers.append(dict(
            id=o["id"], desig=o["name"], part=o["part"], rect=o["rect"],
            cx=(x0 + x1 + 1) // 2, cy=(y0 + y1 + 1) // 2,
            rx=(x1 - x0 + 1) // 2, ry=(y1 - y0 + 1) // 2,
            r=min(x1 - x0 + 1, y1 - y0 + 1) // 2, lamp=o["lamp"],
            cells=[list(c) for c in cells_of(o["rect"])]))
    targets = []
    for o in objs:
        if o["kind"] != "switchbank":
            continue
        x0, y0, x1, y1 = o["rect"]
        pitch = (x1 - x0 + 1) / float(o["n"])
        for i in range(o["n"]):
            r = [int(x0 + pitch * i), y0, int(x0 + pitch * (i + 1)) - 1, y1]
            targets.append(dict(id=o["first"] + i, bank=o["id"],
                                desig="%s.%d" % (o["name"], i + 1), rect=r,
                                actuator=acts[o["id"]][i], lamp=o["lamp"],
                                cells=[list(c) for c in cells_of(r)]))
    rolls = [dict(id=o["id"], name=o["name"], rect=o["rect"], pads=o["pads"],
                  lamp=o["lamp"], cells=[list(c) for c in cells_of(o["rect"])])
             for o in objs if o["kind"] == "rollover"]
    kickers = [dict(id=o["id"], name=o["name"], rect=o["rect"], dir=list(o["dirv"]),
                    power=o["power"], lamp=o.get("lamp"),
                    cells=[list(c) for c in cells_of(o["rect"])])
               for o in objs if o["kind"] == "kicker"]
    drains = [dict(id=o["id"], name=o["name"], rect=o["rect"])
              for o in objs if o["kind"] == "drain"]
    returns = [dict(id=o["id"], name=o["name"], rect=o["rect"], to=list(o["to"]))
               for o in objs if o["kind"] == "return"]
    plunger = [o for o in objs if o["kind"] == "plunger"][0]
    pleds = [dict(index=o["lamp"], desig=o["name"], box=o["rect"])
             for o in objs if o["kind"] == "led"]
    for L in lamps:
        L["playfield"] = [p["box"] for p in pleds if p["index"] == L["index"]]

    j = dict(
        w=W, h=H, blk=BLK, cw=CW, ch=CH, play_h=PLAY_H, viewh=VIEWH, vsmax=VSMAX,
        bytes=W * H, sd_blocks=W * H // 512,
        authored=[
            "board regions and the mask-relief areas",
            "every object's pixel rect, part number and designator",
            "the six rollover groups and their five pads each",
            "the two drop-switch banks and their four switches each",
            "the three kickers' rects, directions and power",
            "the flipper pivots, length, rest and active angles",
            "the plunger lane and its seat; the drain mouth; the outlanes",
            "the edge-connector finger pitch and width",
            "which lamp index belongs to which feature",
            "the LUT split: 1..205 art, 206..213 lamps, 214..255 segments",
        ],
        derived=[
            "colmap and idmap, from the object rects by cell centre, in the "
            "order `priority`",
            "the bumper centres and radii, from the DIP bodies",
            "the flipper zone cells, from the pivot, length and both angles, "
            "minus the drain slot",
            "the six digit boxes and their 42 segment boxes, from DS1",
            "the 205 art colours (median cut, snapped to 5/6/5) and every "
            "byte of the .pic",
            "the reserved-index probes",
        ],
        kinds=KINDS, priority=PRIORITY,
        colmap=b64(kind), idmap=b64(ident),
        lamp0=LAMP0, nlamp=NLAMP, seg0=SEG0, ndig=NDIG, nseg=NSEG, nart=NART,
        pal=[(palb[i * 2] << 8) | palb[i * 2 + 1] for i in range(256)],
        lampon=[rgb565(c) for c in lon], lampoff=[rgb565(c) for c in loff],
        segon=rgb565(son), segoff=rgb565(soff),
        probes={str(k): v for k, v in probes.items()},
        bumpers=bumpers, targets=targets, rollovers=rolls, kickers=kickers,
        drains=drains, returns=returns, lamps=lamps, digits=digits,
        plunger=dict(lane=[C(LANE_X0), C(1), C(LANE_X1 + 1) - 1, PLAY_H - 1],
                     seat=plunger["rect"], fires=list(plunger["fires"]),
                     divider_x=C(LANE_DIV), divider_y0=C(LANE_DIV_Y0)),
        drain_mouth=[DRAIN_X0, C(22), DRAIN_X1, PLAY_H - 1],
        outlanes=[[OUT_L[0], C(20), OUT_L[1], PLAY_H - 1],
                  [OUT_R[0], C(20), OUT_R[1], PLAY_H - 1]],
        flippers={s: dict(pivot=list(FLIP_PIV[s]), length=FLIP_LEN,
                          rest_deg=FLIP_REST, active_deg=FLIP_ACTIVE,
                          zone_rect=zones[s]["rect"],
                          zone_cells=[list(c) for c in zones[s]["cells"]])
                  for s in ("l", "r")},
        edge=dict(y0=EDGE_Y0, y1=PLAY_H - 1, pitch=FINGER_PITCH, w=FINGER_W,
                  fingers=[[int(a), int(b)] for a, b in fingers]),
        reliefs=RELIEFS,
        parts=[dict(desig=o["name"], part=o.get("part", o["kind"]),
                    rect=o["rect"], kind=o["kind"])
               for o in objs
               if o["kind"] in ("bumper", "switchbank", "led", "res", "kicker")
               or o.get("part")],
        pic="pcbtable.pic", pal_file="pcbtable.pal",
        pic_sha256=hashlib.sha256(pic.tobytes()).hexdigest(),
        pal_sha256=hashlib.sha256(bytes(bytearray(palb))).hexdigest(),
    )
    jp = os.path.join(here, "pcbtable.json")
    open(jp, "w").write(json.dumps(j))

    # ── the preview, with every lamp and segment LIT so a missing one shows
    from PIL import Image

    def unpack(v):
        r5, g6, b5 = v >> 11, (v >> 5) & 63, v & 31
        return ((r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2))
    lut = np.array([unpack(v) for v in j["pal"]], dtype=np.uint8)
    lut[0] = (255, 0, 255)
    for k in range(NLAMP):
        lut[LAMP0 + k] = snap565(lon[k])
    for s in range(NSEG):
        lut[SEG0 + s] = snap565(son)
    png = os.path.join(here, "pcbtable.png")
    Image.fromarray(lut[pic]).save(png)

    for p in (pp, lp, png, jp):
        print("ok    %-44s %8d bytes" % (p, os.path.getsize(p)))
    kn = {v: k for k, v in KINDS.items()}
    hist = {kn[int(v)]: int((kind == v).sum()) for v in np.unique(kind)}
    print("      %d x %d, %d SD blocks; %d art colours, %d reserved"
          % (W, H, W * H // 512, len(np.unique(pic[LAMPI == 0])), len(used)))
    print("      collision: " + ", ".join("%s=%d" % kv for kv in sorted(hist.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
