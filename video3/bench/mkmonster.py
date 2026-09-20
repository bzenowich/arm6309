#!/usr/bin/env python3
"""mkmonster.py [CMDSDIR] - the `monster` scene's art, as lwasm source and JSON.

    python3 video3/bench/mkmonster.py ../nitros9/level2/arm6309/cmds

Writes, beside monster.asm:

    monsterdat.asm   the palette, the 16 x 16 block bank, the strip
                     composition tables, the level map, the ground profile,
                     the keyed actor art, the hero's sprite shapes and a
                     sine table

and, in video3/bench/:

    monster.json     ⭐ THE SAME DATA, for video3/bench/checkv3mon.py, which
                     rebuilds the playfield the scene should have drawn and
                     compares it against a VRAM dump.  The ROM and the model
                     share the DATA and no code - bench/README.md's rule.
    monster-art.png  a preview of the level, for reviewing the art without
                     running the machine

⭐ THE ART IS THE POINT (optimizations.md priority 3).  256 simultaneous
colours out of 65,536, a byte a pixel, and FLOYD-STEINBERG dithering against
the card's RGB565 palette - which is done here, in the generator, because the
6309 is not going to do it at 70 Hz.  The palette is median-cut out of the
art itself, snapped to the 5/6/5 grid the LUT actually stores, and the dither
then targets the colours the card will really show.

⛔ INDEX 0 IS THE COPY ENGINE'S COLOUR KEY (keyed-copy.md) and may not be a
visible colour anywhere - not in the playfield, not in an actor.  Every
quantised pixel comes back in 1..255 by construction (the nearest-colour
search never considers 0) and `assert_key_free` checks it again at the end.
LUT entry 0 is loaded with BRIGHT MAGENTA so that a leak is unmistakable on a
contact sheet rather than merely wrong.

═══ THE GEOMETRY, which video3/bench/README.md's monster section explains ═══

The playfield is 208 rows (13 block rows of 16) of the card's 1024-column
ring; the view is 640 x 200 at VSCROLL 8.  A level column is 16 px wide and
is described by TWO bytes - the archetype of its TOP strip (16 x 128) and of
its BOT strip (16 x 80).  §7.1 of optimizations.md is explicit that a copy is
183 us of fixed cost against 63 us of data for a 16 x 16 block, so the engine
wants a vertical RUN of blocks and not the blocks: 13 blocks a column is
3.20 ms, two strips is ~1.2.  The 16 x 16 block is still the unit the ART is
drawn in - the bank is composed out of blocks in VRAM at start-up - which is
exactly the mixed shape §7.1 recommends.
"""
import base64
import hashlib
import json
import math
import os
import sys

import numpy as np

# ─────────────────────────────────────────────────────────── geometry
BLK = 16                 # a block is 16 x 16
PLAYROWS = 13            # block rows in the playfield
PLAYH = PLAYROWS * BLK   # 208
TOPROWS = 7              # block rows in the TOP strip
BOTROWS = PLAYROWS - TOPROWS  # 5
TOPH = TOPROWS * BLK     # 128
BOTH = BOTROWS * BLK     # 80
LEVCOLS = 640            # 10,240 px of level
VSCROLL = 8              # the view is rows 8..207 of the playfield

MAXBLK = 128             # the staging area is ring rows 416..447, two bands of 64
MAXTOP = 60              # TOP strips: ring rows 208..319, columns 0..959 -
#                        # 960.. is the hardware sprite's shape at MAPBASE 3
MAXBOT = 48              # BOT strips: ring rows 320..415, columns 0..767
NSPR = 16                # keyed actor art: 16 slots of 16 x 16
NGAIT = 6                # the hero's sprite shapes

# ring rows, all of which checkv3mon.py rebuilds
R_LIVE, R_TOPBANK, R_BOTBANK, R_CLEAN = 0, 208, 320, 416
R_ART, C_ART = 400, 768          # the keyed art, inside BOT's unused columns
HILLR = 5                # the skyline: its crest row, and HILLR+1 its body
TREER = 6                # ⚠ the treeline, and it must stay in the TOP band:
#                        # in BOT it would multiply the strips past 48
R_BLK = 416                      # the block staging area, before the first refill


# ─────────────────────────────────────────────────────── the palette
def rgb565(c):
    r, g, b = int(c[0]), int(c[1]), int(c[2])
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def snap565(c):
    """The colour the LUT will really show for this 8-bit triple."""
    v = rgb565(c)
    r5, g6, b5 = v >> 11, (v >> 5) & 63, v & 31
    return ((r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2))


class Quant:
    """255 colours in indices 1..255, and Floyd-Steinberg against them.

    ⚠ The search never considers index 0, so no opaque pixel can come back as
    the key.  That is the invariant, and it is structural rather than checked
    after the fact - though assert_key_free checks it anyway.
    """

    def __init__(self, cols):
        assert len(cols) == 255
        self.rgb = np.array(cols, dtype=np.float64)        # [255, 3], indices 1..255

    def nearest(self, px):
        d = self.rgb - px
        return int(np.argmin((d * d).sum(1))) + 1

    def dither(self, img):
        """img: [h, w, 3] float.  Returns [h, w] uint8 of palette indices."""
        h, w, _ = img.shape
        work = img.astype(np.float64).copy()
        out = np.zeros((h, w), dtype=np.uint8)
        for y in range(h):
            for x in range(w):
                old = work[y, x]
                i = self.nearest(np.clip(old, 0, 255))
                out[y, x] = i
                err = old - self.rgb[i - 1]
                if x + 1 < w:
                    work[y, x + 1] += err * (7 / 16)
                if y + 1 < h:
                    if x:
                        work[y + 1, x - 1] += err * (3 / 16)
                    work[y + 1, x] += err * (5 / 16)
                    if x + 1 < w:
                        work[y + 1, x + 1] += err * (1 / 16)
        return out

    def dither_keyed(self, img, alpha):
        """The same, with transparent pixels forced to 0 (the key).  The error
        from a hole is not diffused: it is not a colour anybody asked for."""
        h, w, _ = img.shape
        work = img.astype(np.float64).copy()
        out = np.zeros((h, w), dtype=np.uint8)
        for y in range(h):
            for x in range(w):
                if not alpha[y, x]:
                    continue
                old = work[y, x]
                i = self.nearest(np.clip(old, 0, 255))
                out[y, x] = i
                err = old - self.rgb[i - 1]
                if x + 1 < w and alpha[y, x + 1]:
                    work[y, x + 1] += err * (7 / 16)
                if y + 1 < h:
                    if x and alpha[y + 1, x - 1]:
                        work[y + 1, x - 1] += err * (3 / 16)
                    if alpha[y + 1, x]:
                        work[y + 1, x] += err * (5 / 16)
                    if x + 1 < w and alpha[y + 1, x + 1]:
                        work[y + 1, x + 1] += err * (1 / 16)
        return out


def build_palette(samples):
    """255 colours by median cut over the art's own pixels, snapped to 5/6/5.

    ⚠ SNAPPED BEFORE THE DITHER, not after.  The LUT stores RGB565, so a
    palette entry chosen in 8-bit space is not the colour the card shows, and
    a dither aimed at the wrong target is a dither that makes things worse.
    """
    from PIL import Image
    px = np.concatenate([s.reshape(-1, 3) for s in samples]).astype(np.uint8)
    n = int(math.ceil(math.sqrt(len(px))))
    pad = np.zeros((n * n, 3), dtype=np.uint8)
    pad[:len(px)] = px
    pad[len(px):] = px[-1]
    im = Image.fromarray(pad.reshape(n, n, 3), "RGB")
    q = im.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    raw = q.getpalette()[:255 * 3]
    cols, seen = [], set()
    for i in range(255):
        c = snap565(raw[i * 3:i * 3 + 3])
        if c not in seen:
            seen.add(c)
            cols.append(c)
    # ⚠ collisions on the 5/6/5 grid leave holes; fill them with a neutral ramp
    # so the palette is always exactly 255 and the indices never move.
    i = 0
    while len(cols) < 255:
        c = snap565((i * 9 % 256, i * 5 % 256, i * 13 % 256))
        if c not in seen:
            seen.add(c)
            cols.append(c)
        i += 1
    return cols


# ─────────────────────────────────────────────── the world, continuous tone
def lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def ramp(stops, t):
    """stops: [(pos, rgb)] sorted by pos."""
    if t <= stops[0][0]:
        return stops[0][1]
    for i in range(1, len(stops)):
        if t <= stops[i][0]:
            p0, c0 = stops[i - 1]
            p1, c1 = stops[i]
            return lerp(c0, c1, (t - p0) / (p1 - p0))
    return stops[-1][1]


def hashnoise(x, y, s=0):
    """A deterministic value noise in [0, 1) - no numpy RNG, so the art is the
    same byte for byte on any machine."""
    h = (x * 374761393 + y * 668265263 + s * 2654435761) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65536.0


VARY = 112               # block rows 0..6: where a background variant may differ
NVAR = 4                 # background variants: the sky's mood, nothing else
# ⛔ NO SILHOUETTE IN THE BACKGROUND COLUMN.  A level column is a 16-wide
# strip and the same strip repeats, so ANY profile a background column draws
# has a 16-pixel period - the first two passes drew mountains with a sine and
# got a row of identical spikes, which is the only thing that shape can be.
# A skyline that does not repeat has to be made of DIFFERENT columns, so the
# hills below are overlay TILES (hillL/M/P/R) the level places, exactly as it
# places platforms.
# (haze row, haze strength) a variant pulls the horizon band towards
HAZE = [(96, 0.30), (86, 0.46), (104, 0.22), (78, 0.55)]

SKY = [(0.00, (36, 24, 96)), (0.18, (52, 60, 176)), (0.36, (72, 140, 226)),
       (0.52, (126, 200, 242)), (0.62, (198, 232, 244)), (0.70, (250, 214, 168)),
       (0.78, (252, 176, 122)), (1.00, (224, 128, 104))]


def bg_column(variant):
    """A 16 x PLAYH continuous-tone background column.

    The gradient is the thing dithering is FOR, so the whole column is
    generated - and, below, dithered - as one strip: the error diffuses down
    208 rows and the banding a 5-bit blue channel would otherwise show over a
    200-row sky is broken up.
    """
    img = np.zeros((PLAYH, BLK, 3), dtype=np.float64)
    for y in range(PLAYH):
        base = ramp(SKY, y / (PLAYH - 1.0))
        for x in range(BLK):
            c = list(base)
            # ⚠ EVERY VARIANT'S DIFFERENCE IS ABOVE ROW 7 (y < 112), and that
            # is a strip-count decision as much as an art one: below it the
            # background is the same in all four, so a BOT strip does not
            # multiply by the variant and 22 of them cover the whole level.
            if y < VARY:
                hz, k = HAZE[variant]
                if y > hz:
                    d = min(1.0, (y - hz) / 26.0)
                    c = list(lerp(c, (196, 186, 214), k * d))
            # the cave band the playfield sits in
            if y > 150:
                d = min(1.0, (y - 150) / 58.0)
                c = list(lerp(c, (40, 34, 72), 0.70 * d))
            # ⚠ the grain's seed is the VARIANT only above the variant band:
            # below it every variant must be byte-identical or the BOT strips
            # multiply by four and 22 of them become 68.
            n = (hashnoise(x, y, 7 + (variant if y < VARY else 0)) - 0.5) * 7.0
            img[y, x] = [c[0] + n, c[1] + n, c[2] + n]
    return np.clip(img, 0, 255)


def tex(base, y, x, amp, seed):
    n = (hashnoise(x, y, seed) - 0.5) * amp
    return [base[0] + n, base[1] + n, base[2] + n]


def fg_block(kind):
    """A 16 x 16 foreground block: (rgb [16,16,3], alpha [16,16] bool)."""
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.zeros((BLK, BLK), dtype=bool)

    def put(y, x, c):
        img[y, x] = c
        al[y, x] = True

    if kind == "grass":                    # the lit turf cap
        for y in range(BLK):
            for x in range(BLK):
                if y < 4:
                    c = lerp((156, 250, 108), (92, 214, 76), y / 4.0)
                elif y < 8:
                    c = lerp((72, 186, 66), (40, 136, 54), (y - 4) / 4.0)
                else:
                    c = lerp((136, 92, 54), (104, 66, 40), (y - 8) / 8.0)
                put(y, x, tex(c, y, x, 26 if y < 8 else 36, 11))
        for x in range(0, BLK, 3):         # blades
            put(0, (x + 1) % BLK, (196, 255, 150))
            put(1, (x + 2) % BLK, (124, 236, 96))
    elif kind == "dirt":
        for y in range(BLK):
            for x in range(BLK):
                c = lerp((126, 86, 50), (88, 56, 34), y / 15.0)
                put(y, x, tex(c, y, x, 44, 12))
        for k in range(5):                 # pebbles
            px, py = int(hashnoise(k, 3, 5) * 13), int(hashnoise(k, 9, 6) * 13)
            for dy in range(2):
                for dx in range(2):
                    put(py + dy, px + dx, (144, 112, 78))
    elif kind == "rock":
        for y in range(BLK):
            for x in range(BLK):
                c = lerp((88, 72, 116), (48, 40, 72), y / 15.0)
                put(y, x, tex(c, y, x, 34, 13))
        for x in range(BLK):               # a crack
            if (x + int(2 * math.sin(x * 0.7))) % 16 in (6, 7):
                put((x * 3) % BLK, x, (30, 26, 44))
    elif kind == "plat":                   # a floating slab, full width
        for y in range(BLK):
            for x in range(BLK):
                if y < 4:
                    c = lerp((246, 206, 120), (214, 158, 78), y / 4.0)
                elif y < 11:
                    c = lerp((176, 118, 64), (132, 84, 48), (y - 4) / 7.0)
                else:
                    c = lerp((96, 58, 38), (62, 38, 28), (y - 11) / 5.0)
                put(y, x, tex(c, y, x, 22, 14))
    elif kind == "platL" or kind == "platR":
        b, al2 = fg_block("plat")
        img[:], al[:] = b, al2
        edge = 0 if kind == "platL" else BLK - 1
        for y in range(BLK):
            img[y, edge] = (250, 226, 160) if kind == "platL" else (70, 44, 30)
        for y in range(12, BLK):           # a rounded cap
            for x in range(BLK):
                if (kind == "platL" and x < y - 11) or (kind == "platR" and x > BLK - (y - 10)):
                    al[y, x] = False
    elif kind == "water":
        for y in range(BLK):
            for x in range(BLK):
                c = lerp((52, 176, 220), (22, 82, 152), y / 15.0)
                put(y, x, tex(c, y, x, 20, 15))
    elif kind == "watertop":
        for y in range(BLK):
            for x in range(BLK):
                if y < 2:
                    c = (206, 248, 255)
                elif y < 4:
                    c = (110, 218, 244)
                else:
                    c = lerp((52, 176, 220), (30, 118, 184), (y - 4) / 12.0)
                put(y, x, tex(c, y, x, 16, 16))
    elif kind == "lava":
        for y in range(BLK):
            for x in range(BLK):
                t = 0.5 + 0.5 * math.sin(2 * math.pi * x / BLK + y * 0.4)
                c = lerp((176, 40, 16), (238, 116, 30), t * (1 - y / 26.0))
                put(y, x, tex(c, y, x, 22, 17))
    elif kind == "lavatop":
        for y in range(BLK):
            for x in range(BLK):
                t = 0.5 + 0.5 * math.sin(2 * math.pi * x / BLK)
                if y < 2:
                    c = lerp((255, 236, 150), (255, 176, 60), t)
                elif y < 5:
                    c = lerp((252, 150, 40), (226, 92, 22), t)
                else:
                    c = lerp((214, 66, 18), (150, 32, 14), (y - 5) / 12.0)
                put(y, x, tex(c, y, x, 18, 18))
    elif kind == "bush":                   # over the background
        for y in range(BLK):
            for x in range(BLK):
                v = 0.0
                for bx, by, br in ((3.5, 11.5, 4.6), (8.0, 9.0, 5.6), (12.5, 11.5, 4.4)):
                    v = max(v, br - math.hypot(x - bx, (y - by) * 1.15))
                v -= 1.6 * hashnoise(x, y, 18)
                if v > 0:
                    c = lerp((40, 116, 62), (132, 232, 110), min(1.0, v / 4.2))
                    put(y, x, tex(c, y, x, 18, 19))
        for k in range(4):                 # berries
            bx, by = 2 + int(hashnoise(k, 1, 20) * 12), 7 + int(hashnoise(k, 2, 21) * 6)
            if al[by, bx]:
                put(by, bx, (252, 96, 110))
    elif kind == "flower":                 # three stems of different heights
        for i, (sx, h, head) in enumerate(((3, 7, (252, 132, 152)),
                                           (8, 10, (255, 226, 96)),
                                           (12, 6, (186, 146, 250)))):
            for y in range(BLK - h, BLK):
                put(y, sx, (58, 146, 70))
                put(y, sx + 1, (40, 112, 56))
            ty = BLK - h - 1
            for dy in range(-2, 2):
                for dx in range(-2, 3):
                    if abs(dx) + abs(dy) <= 2 and 0 <= ty + dy < BLK:
                        put(ty + dy, max(0, min(BLK - 1, sx + dx)),
                            head if (dx or dy) else (255, 250, 210))
    elif kind == "crystal":                # a cluster of three lit shards
        for cx, top, bot, tint in ((4, 6, 16, (72, 226, 214)),
                                   (8, 1, 16, (146, 118, 255)),
                                   (12, 8, 16, (250, 156, 226))):
            for y in range(top, bot):
                wdt = max(0, int((y - top) * 0.34) + 1)
                for x in range(cx - wdt, cx + wdt + 1):
                    if 0 <= x < BLK:
                        t = (y - top) / float(bot - top)
                        c = lerp((250, 252, 255), tint, min(1.0, t + 0.25))
                        if x == cx - wdt:
                            c = lerp(c, (255, 255, 255), 0.5)
                        put(y, x, c)
    elif kind.startswith("hill"):
        # a distant ridge, in four tiles the level lays end to end - a rise, a
        # flat, a peak and a fall - over a solid second row.  ⭐ THIS is how a
        # skyline that does NOT repeat is built out of 16-pixel columns.
        if kind == "hillB":
            for y in range(BLK):
                for x in range(BLK):
                    put(y, x, tex(lerp((62, 76, 144), (44, 52, 112), y / 15.0), y, x, 12, 23))
            return img, al
        prof = {"hillL": (17, 5), "hillM": (5, 4), "hillP": (4, -1), "hillR": (0, 17)}[kind]
        for x in range(BLK):
            top = prof[0] + (prof[1] - prof[0]) * x / (BLK - 1.0)
            top += 1.1 * math.sin(x * 0.9 + prof[0])
            for y in range(BLK):
                if y >= top:
                    d = min(1.0, (y - top) / 18.0)
                    base = lerp((96, 112, 184), (62, 76, 144), d)
                    if y < top + 1.8:
                        base = lerp(base, (212, 222, 252), 0.55)   # a lit crest
                    put(y, x, tex(base, y, x, 12, 23))
    elif kind.startswith("tree"):
        # a nearer treeline at block row 7, three shapes so a run of them is
        # not a pattern
        k = int(kind[4])
        h = (4, 2, 6)[k]
        for y in range(BLK):
            for x in range(BLK):
                if y >= 11 and abs(x - 8) <= 1:
                    put(y, x, (74, 52, 40))
                v = 0.0
                for cx, cy, cr in ((8, h + 4, 5.6), (4.5, h + 7, 4.0), (11.5, h + 7, 4.2)):
                    v = max(v, cr - math.hypot((x - cx) * 0.95, y - cy))
                v -= 1.4 * hashnoise(x, y, 30 + k)
                if v > 0:
                    put(y, x, tex(lerp((28, 92, 66), (96, 186, 104), min(1.0, v / 4.5)),
                                  y, x, 16, 31 + k))
    elif kind == "cloud":
        for y in range(BLK):
            for x in range(BLK):
                v = 0.0
                for cx, cy, cr in ((4, 9, 4.4), (9, 7, 5.2), (13, 10, 3.8)):
                    v = max(v, cr - math.hypot(x - cx, (y - cy) * 1.5))
                if v > 0:
                    a = min(1.0, v / 3.0)
                    put(y, x, lerp((196, 226, 250), (255, 255, 255), a))
    elif kind == "sign":                   # a striped marker post
        for y in range(BLK):
            for x in range(BLK):
                if 5 <= x <= 10 and y >= 2:
                    c = (238, 72, 92) if ((y + x) // 3) % 2 == 0 else (250, 244, 232)
                    put(y, x, c)
    else:
        raise KeyError(kind)
    return img, al


# ───────────────────────────────────────────────────────── actor art
def spr_blob(t, body, dark, lite):
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.zeros((BLK, BLK), dtype=bool)
    squash = 1.0 + 0.22 * t
    for y in range(BLK):
        for x in range(BLK):
            dx, dy = (x - 7.5) * squash, (y - 9.0) / squash
            r = math.hypot(dx, dy)
            if r < 6.6:
                sh = max(0.0, 1.0 - math.hypot(dx + 2, dy + 2) / 8.0)
                img[y, x] = lerp(lerp(dark, body, min(1.0, (6.6 - r) / 2.2)), lite, sh * 0.8)
                al[y, x] = True
    for ex in (5, 10):                       # eyes
        for dy in range(2):
            for dx in range(2):
                img[6 + dy, ex + dx] = (250, 250, 250)
                al[6 + dy, ex + dx] = True
        img[7, ex + (1 if t else 0)] = (20, 16, 40)
    return img, al


def spr_bat(t, wing, body):
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.zeros((BLK, BLK), dtype=bool)
    up = 3 if t else 0
    for y in range(BLK):
        for x in range(BLK):
            dx, dy = x - 7.5, y - 8.5
            if math.hypot(dx * 1.25, dy) < 4.0:
                img[y, x] = lerp(body, (250, 250, 250), max(0.0, 0.5 - dy / 9.0))
                al[y, x] = True
            wy = 7 - up + int(abs(dx) * 0.55)
            if 2 <= abs(dx) <= 7.5 and wy <= y <= wy + 3:
                img[y, x] = lerp(wing, body, (y - wy) / 4.0)
                al[y, x] = True
    for ex in (5, 9):
        img[7, ex] = (255, 232, 60)
        al[7, ex] = True
    return img, al


def spr_grub(t, body, dark):
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.zeros((BLK, BLK), dtype=bool)
    for i, (cx, cy, r) in enumerate(((3.5, 10, 3.0), (7.5, 9 - t, 3.4), (11.5, 10, 3.0))):
        for y in range(BLK):
            for x in range(BLK):
                d = math.hypot(x - cx, y - cy)
                if d < r:
                    img[y, x] = lerp(body, dark, d / r * 0.9)
                    al[y, x] = True
    for y in range(BLK):
        for x in range(BLK):
            if math.hypot(x - 12.8, y - 8.2) < 3.3:
                img[y, x] = lerp((250, 240, 180), body, 0.35)
                al[y, x] = True
    img[7, 13] = img[7, 14] = (24, 20, 40)
    al[7, 13] = al[7, 14] = True
    for lx in (3, 7, 11):                   # feet
        img[13 + (t & 1), lx] = dark
        al[13 + (t & 1), lx] = True
    return img, al


def spr_bird(t, body, wing, beak):
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.zeros((BLK, BLK), dtype=bool)
    for y in range(BLK):
        for x in range(BLK):
            if math.hypot((x - 8) * 1.15, y - 9) < 4.4:
                img[y, x] = lerp(body, (255, 255, 255), max(0.0, 0.45 - (y - 6) / 12.0))
                al[y, x] = True
    wy = 5 if t else 10
    for x in range(1, 15):
        h = 3 - abs(x - 8) // 3
        for d in range(h):
            y = wy + (d if t else -d)
            if 0 <= y < BLK:
                img[y, x] = lerp(wing, body, d / 3.0)
                al[y, x] = True
    for x in range(12, 15):
        img[9, x] = beak
        al[9, x] = True
    img[8, 10] = (30, 26, 40)
    al[8, 10] = True
    return img, al


def spr_gem(t, a, b):
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.zeros((BLK, BLK), dtype=bool)
    s = 6.6 - t * 0.9
    for y in range(BLK):
        for x in range(BLK):
            dx, dy = abs(x - 7.5), abs(y - 7.5)
            if dx + dy < s:
                img[y, x] = lerp(a, b, (dx + dy) / s)
                al[y, x] = True
    for y in range(3, 8):
        img[y, 6] = (255, 255, 255)
        al[y, 6] = True
    return img, al


def spr_spike(t, body, tip):
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.zeros((BLK, BLK), dtype=bool)
    ph = t * math.pi / 8
    for y in range(BLK):
        for x in range(BLK):
            dx, dy = x - 7.5, y - 7.5
            r = math.hypot(dx, dy)
            if r < 4.6:
                img[y, x] = lerp(body, (20, 18, 30), r / 6.0)
                al[y, x] = True
            elif r < 7.4:
                a = (math.atan2(dy, dx) + ph) % (math.pi / 3)
                if a < 0.34 or a > math.pi / 3 - 0.34:
                    img[y, x] = lerp(tip, body, (r - 4.6) / 3.0)
                    al[y, x] = True
    return img, al


def spr_ghost(t, body, edge):
    """A rounded hood with a wavy hem - unmistakable at 16 x 16, which the
    quadcopter it replaced was not."""
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.zeros((BLK, BLK), dtype=bool)
    for y in range(BLK):
        for x in range(BLK):
            dx, dy = x - 7.5, y - 7.0
            inside = (math.hypot(dx, dy * 1.25) < 6.6) if dy < 0 else abs(dx) < 6.6
            if dy >= 0:
                hem = 13 + 2.0 * math.sin((x + t * 3) * 0.9)
                inside = inside and y <= hem
            if inside:
                img[y, x] = lerp(body, edge, min(1.0, (abs(dx) / 7.0) ** 1.4 + y / 40.0))
                al[y, x] = True
    for ex in (4, 10):                       # two big eyes, and they blink
        for dy in range(3 - t):
            for dx in range(3):
                if al[5 + dy, ex + dx].any() if False else al[5 + dy, ex + dx]:
                    img[5 + dy, ex + dx] = (28, 22, 54)
    return img, al


def spr_jelly(t, body, edge):
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.zeros((BLK, BLK), dtype=bool)
    for y in range(BLK):
        for x in range(BLK):
            dx, dy = x - 7.5, y - 6.0
            if dy <= 0 and math.hypot(dx, dy * (1.5 - 0.3 * t)) < 6.4:
                img[y, x] = lerp(body, edge, abs(dx) / 7.0)
                al[y, x] = True
    for i, tx in enumerate((3, 6, 9, 12)):
        for y in range(6, 14 + (t if i % 2 else 0)):
            if y < BLK:
                img[y, tx + (1 if (y // 2 + t) % 2 else 0)] = lerp(edge, body, (y - 6) / 9.0)
                al[y, tx + (1 if (y // 2 + t) % 2 else 0)] = True
    return img, al


SPRITES = [
    ("grub", lambda t: spr_grub(t, (126, 226, 92), (42, 122, 56))),
    ("bat", lambda t: spr_bat(t, (168, 78, 214), (86, 40, 128))),
    ("blob", lambda t: spr_blob(t, (250, 150, 56), (150, 62, 24), (255, 226, 150))),
    ("bird", lambda t: spr_bird(t, (86, 210, 240), (36, 132, 200), (252, 196, 60))),
    ("spike", lambda t: spr_spike(t, (226, 62, 74), (250, 216, 120))),
    ("gem", lambda t: spr_gem(t, (255, 240, 130), (236, 140, 40))),
    ("jelly", lambda t: spr_jelly(t, (250, 132, 196), (152, 46, 128))),
    ("ghost", lambda t: spr_ghost(t, (236, 244, 255), (118, 140, 226))),
]
assert len(SPRITES) * 2 == NSPR


# ───────────────────────────────────────────────────── the hero, 2-bit
# code 1 outline, 2 body, 3 accent; 0 transparent.  plan §7: the shape is 64
# bytes of VRAM - plane 0 then plane 1, two bytes a row each.
HERO_FRAMES = [
    # a small runner.  '.' hole, 'o' outline, 'b' body, 'a' accent
    """
    .....oooo.......
    ....obbbbo......
    ....obaabo......
    ....obaabo......
    .....obbo.......
    ...ooobboooo....
    ..obbbbbbbbbo...
    ..obabbbbabo....
    ..obabbbbabo....
    ...obbbbbbo.....
    ....obbbbo......
    ....ob..bo......
    ....ob..bo......
    ...oaao.oaao....
    ...oaao.oaao....
    ....oo...oo.....
    """,
    """
    .....oooo.......
    ....obbbbo......
    ....obaabo......
    ....obaabo......
    .....obbo.......
    ..ooobbooooo....
    .obbbbbbbbbbo...
    .obabbbbbabo....
    ..obabbbbabo....
    ...obbbbbbo.....
    ....obbbbo......
    ...ob....bo.....
    ..ob......bo....
    ..oaao...oaao...
    ...oo.....oo....
    ................
    """,
    """
    .....oooo.......
    ....obbbbo......
    ....obaabo......
    ....obaabo......
    .....obbo.......
    ...ooobboooo....
    ..obbbbbbbbbo...
    ..obabbbbabo....
    ..obabbbbabo....
    ...obbbbbbo.....
    ....obbbbo......
    ....ob..bo......
    ....ob..bo......
    ...oaao.oaao....
    ...oaao.oaao....
    ....oo...oo.....
    """,
    """
    .....oooo.......
    ....obbbbo......
    ....obaabo......
    ....obaabo......
    .....obbo.......
    ....ooobbooooo..
    ...obbbbbbbbbbo.
    ....obabbbbbabo.
    ...obabbbbabo...
    ...obbbbbbo.....
    ...obbbbo.......
    ..ob....bo......
    .ob......bo.....
    .oaao...oaao....
    ..oo.....oo.....
    ................
    """,
    # jump
    """
    .....oooo.......
    ....obbbbo......
    ....obaabo......
    ....obaabo......
    .....obbo.......
    .oooobbbboooo...
    .obbbbbbbbbbbo..
    .obabbbbbbabo...
    ..obbbbbbbbo....
    ...obbbbbbo.....
    ...obbbbbbo.....
    ..ob..bb..bo....
    .oaao.bb.oaao...
    ..oo..bb..oo....
    .....oaao.......
    ......oo........
    """,
    # idle
    """
    .....oooo.......
    ....obbbbo......
    ....obaabo......
    ....obaabo......
    .....obbo.......
    ...ooobboooo....
    ..obbbbbbbbbo...
    ..obabbbbabo....
    ..obbbbbbbbo....
    ...obbbbbbo.....
    ....obbbbo......
    ....ob..bo......
    ....ob..bo......
    ....oaaoaao.....
    ....oaaoaao.....
    .....oo.oo......
    """,
]
HERO_LUT = [(0x18, 0x12, 0x30), (0xF8, 0xC8, 0x60), (0x40, 0xE8, 0xFF)]  # outline, body, accent


def hero_shape(txt):
    rows = [r.strip() for r in txt.strip("\n").split("\n")]
    rows = [r for r in rows if r]
    assert len(rows) == 16, len(rows)
    code = np.zeros((16, 16), dtype=np.uint8)
    for y, r in enumerate(rows):
        assert len(r) == 16, (y, r, len(r))
        for x, ch in enumerate(r):
            code[y, x] = {".": 0, "o": 1, "b": 2, "a": 3}[ch]
    # ⚠ ROW-MAJOR, FOUR BYTES A ROW: plane 0's two, then plane 1's.  That is
    # what the card fetches (machine.c reads the shape at sr * 4 + (sc >> 3),
    # and takes bit 0 from byte 0 and bit 1 from byte 2), and a plane-major
    # 64 bytes assembles and boots and draws a different animal.
    out = []
    for y in range(16):
        for pl in (0, 1):
            bits = [(code[y, x] >> pl) & 1 for x in range(16)]
            out.append(sum(1 << (7 - i) for i in range(8) if bits[i]))
            out.append(sum(1 << (7 - i) for i in range(8) if bits[8 + i]))
    return out


# ───────────────────────────────────────────────────────── the level
def build_level():
    """13 x LEVCOLS of block-KIND descriptors, plus the ground profile.

    Each cell is a tuple the bank interns by CONTENT, so 640 columns of level
    cost 640 x 2 bytes of map and the bank is whatever the art actually used.

    ⚠ THE STRIP COUNT IS A DESIGN CONSTRAINT AND IT IS TIGHT.  A TOP strip is
    8 block rows and there is room for 64 of them; a BOT strip is 5 and there
    is room for 48.  Every independent thing a column can do MULTIPLIES, so
    the level obeys three rules and the asserts below are what enforce them:
    a background variant changes only above block row 7; a column carries AT
    MOST ONE overlay; and platforms live at block row 8, inside BOT, where
    they do not multiply the sky.
    """
    grid = [[None] * LEVCOLS for _ in range(PLAYROWS)]
    gnd = [0] * LEVCOLS
    used = [False] * LEVCOLS          # this column already has an overlay

    # ── the terrain: a turf block row that walks between 9 and 11, with pits
    g, c, seg = 10, 0, []
    while c < LEVCOLS:
        w = 6 + int(hashnoise(c, 1, 21) * 10)
        k = hashnoise(c, 2, 22)
        if k < 0.17 and c > 20 and c + 5 < LEVCOLS - 20:
            seg.append(("pit", 4 + int(hashnoise(c, 4, 24) * 2)))
            c += seg[-1][1]
        else:
            if k > 0.72:
                g = max(9, min(11, g + (1 if hashnoise(c, 3, 23) < 0.5 else -1)))
            seg.append(("gnd", w, g))
            c += w

    # ── the background, in bands of 48 columns so the scenery changes as the
    # level streams past
    for x in range(LEVCOLS):
        v = int(hashnoise(x // 40, 0, 31) * NVAR)
        for r in range(PLAYROWS):
            grid[r][x] = ("bg", v, r)

    x = 0
    for s in seg:
        if s[0] == "pit":
            hot = hashnoise(x, 12, 61) < 0.4
            for i in range(min(s[1], LEVCOLS - x)):
                grid[11][x + i] = ("fg", "lavatop" if hot else "watertop")
                grid[12][x + i] = ("fg", "lava" if hot else "water")
                gnd[x + i] = 255                      # no floor: the hero jumps
            x += s[1]
        else:
            _, w, gr = s
            for i in range(min(w, LEVCOLS - x)):
                grid[gr][x + i] = ("fg", "grass")
                for r in range(gr + 1, PLAYROWS):
                    grid[r][x + i] = ("fg", "dirt" if r < gr + 3 else "rock")
                gnd[x + i] = gr * BLK
            x += w

    # ── platforms: short runs at block row 8, over the ground and inside BOT
    x = 14
    while x < LEVCOLS - 14:
        if hashnoise(x, 5, 41) < 0.36:
            w = 3 + int(hashnoise(x, 6, 42) * 4)
            if all(gnd[x + i] != 255 and gnd[x + i] // BLK > 8 and not used[x + i]
                   for i in range(w)):
                for i in range(w):
                    k = "platL" if i == 0 else ("platR" if i == w - 1 else "plat")
                    grid[8][x + i] = ("ov", k, grid[8][x + i][1], 8)
                    used[x + i] = True
                x += w + 5
        x += 3

    # ── a skyline: runs of hill tiles at block row HILLR, which is TOP's and
    # so never collides with the turf decorations below
    hill = [False] * LEVCOLS
    x = 3
    while x < LEVCOLS - 12:
        if hashnoise(x, 13, 71) < 0.5:
            w = 4 + int(hashnoise(x, 14, 72) * 6)
            for i in range(min(w, LEVCOLS - x)):
                k = ("hillL" if i == 0 else "hillR" if i == w - 1
                     else "hillP" if i == w // 2 else "hillM")
                grid[HILLR][x + i] = ("ov", k, grid[HILLR][x + i][1], HILLR)
                grid[HILLR + 1][x + i] = ("ov", "hillB", grid[HILLR + 1][x + i][1], HILLR + 1)
                hill[x + i] = True
            x += w
        x += 2 + int(hashnoise(x, 15, 73) * 6)

    # ── a treeline at block row TREER, where the skyline is not
    for x in range(LEVCOLS):
        if not hill[x] and not used[x] and hashnoise(x, 16, 81) < 0.30:
            k = "tree%d" % (int(hashnoise(x, 17, 82) * 3))
            grid[TREER][x] = ("ov", k, grid[TREER][x][1], TREER)

    # ── one decoration on the turf, or one cloud in the sky, and never both
    for x in range(LEVCOLS):
        if used[x]:
            continue
        h = hashnoise(x, 8, 51)
        r = gnd[x] // BLK - 1 if gnd[x] != 255 else 99
        if 8 <= r <= 10 and h < 0.22:
            k = ("bush", "flower", "crystal")[int(h * 100) % 3]
            grid[r][x] = ("ov", k, grid[r][x][1], r)
            used[x] = True
        elif hashnoise(x, 9, 52) < 0.06:
            r = 1 + int(hashnoise(x, 10, 53) * 3)
            grid[r][x] = ("ov", "cloud", grid[r][x][1], r)
            used[x] = True
    return grid, gnd


# ─────────────────────────────────────────────────────────── assembly
def emit_bytes(label, data, per=16, comment=""):
    out = []
    if comment:
        out.append("* " + comment)
    first = True
    for i in range(0, len(data), per):
        chunk = ",".join("$%02X" % b for b in data[i:i + per])
        out.append("%-19s fcb       %s" % (label if first else "", chunk))
        first = False
    return "\n".join(out)


def b64(a):
    return base64.b64encode(bytes(bytearray(a))).decode()


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    here = os.path.dirname(os.path.abspath(__file__))

    # ── the continuous-tone art, before any quantisation
    bgcols = [bg_column(v) for v in range(NVAR)]
    fgkinds = ["grass", "dirt", "rock", "plat", "platL", "platR", "water",
               "watertop", "lava", "lavatop", "bush", "flower", "crystal", "cloud",
               "hillL", "hillM", "hillP", "hillR", "hillB",
               "tree0", "tree1", "tree2"]
    fgs = {k: fg_block(k) for k in fgkinds}
    sprs = [(nm, t, f(t)) for nm, f in SPRITES for t in (0, 1)]

    samples = list(bgcols)
    for k in fgkinds:
        img, al = fgs[k]
        if al.any():
            samples.append(img[al].reshape(-1, 1, 3))
    for _, _, (img, al) in sprs:
        if al.any():
            samples.append(img[al].reshape(-1, 1, 3))
    pal = build_palette(samples)
    q = Quant(pal)

    # ── the background columns, dithered WHOLE so the sky's gradient is
    # continuous over all 208 rows, then sliced into blocks
    # ⛔ TWO PASSES, NOT ONE, and the reason is the block bank's size.  Floyd-
    # Steinberg carries its error downward, so a column dithered whole comes
    # out DIFFERENT below row 7 in every variant even where the art is
    # identical - 52 background blocks instead of 34, and the bank does not
    # fit.  Dithering [0, VARY) and [VARY, PLAYH) from zero error each makes
    # the shared part shared again; the seam is one row of a 208-row gradient.
    bgblocks = [[None] * PLAYROWS for _ in range(NVAR)]
    for v in range(NVAR):
        a = q.dither(bgcols[v][:VARY])
        b = q.dither(bgcols[v][VARY:])
        d = np.concatenate([a, b])
        for r in range(PLAYROWS):
            bgblocks[v][r] = d[r * BLK:(r + 1) * BLK, :]

    # ── the bank: every DISTINCT 16 x 16 the level asks for, by content
    blocks, index = [], {}

    def intern(arr):
        key = hashlib.sha1(arr.tobytes()).hexdigest()
        if key not in index:
            index[key] = len(blocks)
            blocks.append(arr)
        return index[key]

    fgq = {}
    for k in fgkinds:
        img, al = fgs[k]
        if al.all():
            fgq[k] = q.dither(img)
    ovq = {}                                 # (kind, variant, row) composited

    def block_id(cell):
        if cell[0] == "bg":
            _, v, r = cell
            return intern(bgblocks[v][r])
        if cell[0] == "fg":
            return intern(fgq[cell[1]])
        _, k, v, r = cell                    # an overlay on its background
        key = (k, v, r)
        if key not in ovq:
            img, al = fgs[k]
            base = bgcols[v][r * BLK:(r + 1) * BLK, :].copy()
            base[al] = img[al]
            ovq[key] = q.dither(base)
        return intern(ovq[key])

    grid, gnd = build_level()
    ids = np.zeros((PLAYROWS, LEVCOLS), dtype=np.int32)
    for r in range(PLAYROWS):
        for x in range(LEVCOLS):
            ids[r, x] = block_id(grid[r][x])
    assert len(blocks) <= MAXBLK, ("the block bank overflows the staging area",
                                   len(blocks), MAXBLK)

    # ── the strips: the DISTINCT vertical runs, which is what the engine copies
    tops, topi, bots, boti = [], {}, [], {}
    levtop = np.zeros(LEVCOLS, dtype=np.uint8)
    levbot = np.zeros(LEVCOLS, dtype=np.uint8)
    for x in range(LEVCOLS):
        t = tuple(int(v) for v in ids[:TOPROWS, x])
        b = tuple(int(v) for v in ids[TOPROWS:, x])
        if t not in topi:
            topi[t] = len(tops)
            tops.append(t)
        if b not in boti:
            boti[b] = len(bots)
            bots.append(b)
        levtop[x], levbot[x] = topi[t], boti[b]
    assert len(tops) <= MAXTOP, ("too many TOP strips", len(tops), MAXTOP)
    assert len(bots) <= MAXBOT, ("too many BOT strips", len(bots), MAXBOT)

    # ── the keyed actor art and the hero
    art = np.zeros((BLK, NSPR * BLK), dtype=np.uint8)
    for i, (nm, t, (img, al)) in enumerate(sprs):
        art[:, i * BLK:(i + 1) * BLK] = q.dither_keyed(img, al)
    hero = []
    for f in HERO_FRAMES:
        hero += hero_shape(f)
    assert len(hero) == NGAIT * 64

    # ⛔ INDEX 0 IS THE KEY.  Nothing visible may be it.
    def assert_key_free(what, arr):
        bad = int((np.asarray(arr) == 0).sum())
        assert bad == 0, "%s: %d pixels are index 0, which is the colour key" % (what, bad)

    for i, blk in enumerate(blocks):
        assert_key_free("block %d" % i, blk)
    holes = int((art == 0).sum())
    for i in range(NSPR):
        s = art[:, i * BLK:(i + 1) * BLK]
        assert (s != 0).any(), "sprite %d is entirely key" % i
    assert holes > 0, "no sprite has a transparent pixel - the key is untested"

    # ── the block bank as the ROM uploads it: TWO row-bands of 64 blocks,
    # row-major, so the upload is one VDATA run a VRAM row
    nb = len(blocks)
    bw = [min(nb, 64) * BLK, max(0, nb - 64) * BLK]
    bankdat = []
    for band in (0, 1):
        if not bw[band]:
            continue
        b = np.zeros((BLK, bw[band]), dtype=np.uint8)
        for i in range(band * 64, min(nb, band * 64 + 64)):
            b[:, (i % 64) * BLK:(i % 64) * BLK + BLK] = blocks[i]
        bankdat += b.reshape(-1).tolist()
    bankrows = 16 * (1 if nb <= 64 else 2)

    # ── the ground profile, one byte a column: the playfield row of the turf,
    # 255 where there is none
    gndb = [min(255, g) for g in gnd]

    # ── the palette, hi lo
    palb = []
    for c in pal:
        v = rgb565(c)
        palb += [v >> 8, v & 255]
    palb = [0xF8, 0x1F] + palb               # ⭐ entry 0: BRIGHT MAGENTA, the key
    assert len(palb) == 512

    sin = [int(round(127 * math.sin(2 * math.pi * i / 256))) & 255 for i in range(256)]

    DAT = [
        "MNBLK               equ       %d" % nb,
        "MNB0W               equ       %d" % bw[0],
        "MNB1W               equ       %d" % bw[1],
        "MNTOP               equ       %d" % len(tops),
        "MNBOT               equ       %d" % len(bots),
        "MNSPR               equ       %d" % NSPR,
        "* ⭐ THE GEOMETRY IS EMITTED, NOT RESTATED.  monster.asm had TOPROWS",
        "*      as a literal 8 once, after this file moved to 7, and every",
        "*      strip but the first came out of the wrong blocks - a whole",
        "*      bank wrong and a scene that still looked plausible.",
        "MNTR                equ       %d        block rows in a TOP strip" % TOPROWS,
        "MNBR                equ       %d        and in a BOT strip" % BOTROWS,
        "MNTOPH              equ       %d      the TOP band, in pixel rows" % TOPH,
        "MNBOTH              equ       %d       and the BOT band" % BOTH,
        "MNPLAYH             equ       %d      the playfield" % PLAYH,
        "MNRTOP              equ       %d      the ring row the TOP bank starts at" % R_TOPBANK,
        "MNRBOT              equ       %d      ... the BOT bank" % R_BOTBANK,
        "MNRCLN              equ       %d      ... the clean copy of the BOT band" % R_CLEAN,
        "MNRART              equ       %d      ... the keyed actor art" % R_ART,
        "MNCART              equ       %d      ... and its column" % C_ART,
        "MNRBLK              equ       %d      the 16 x 16 block staging area" % R_BLK,
        "MNVSCR              equ       %d        VSCROLL: the view is rows 8..207" % VSCROLL,
        "MNGAIT              equ       %d" % NGAIT,
        "MLEVC               equ       %d" % LEVCOLS,
        emit_bytes("PalDat", palb, 16,
                   "256 RGB565 entries, hi lo.  ENTRY 0 IS MAGENTA AND IS THE KEY:"),
        "*      nothing visible is index 0, so it can only appear as a leak",
        emit_bytes("BlkDat", bankdat, 16,
                   "the %d 16 x 16 blocks, ROW-MAJOR in %d band(s) of 16 rows x %d/%d"
                   % (nb, bankrows // 16, bw[0], bw[1])),
        "*      bytes - the upload is ONE VDATA run a VRAM row, into ring rows"
        "\n*      %d.., which the first clean refill then overwrites" % R_BLK,
        emit_bytes("ArtDat", art.reshape(-1).tolist(), 16,
                   "the keyed actor art: 16 rows of %d bytes, %d sprites of 16 x 16." % (NSPR * 16, NSPR)),
        "*      INDEX 0 IS THE HOLE - %d of %d pixels" % (holes, NSPR * 256),
        emit_bytes("HeroArt", hero, 16,
                   "the hardware sprite: %d shapes of 64 bytes (plan 7's two planes)" % NGAIT),
        emit_bytes("TopStr", [b for t in tops for b in t], 8,
                   "%d TOP strips, %d block ids each (16 x %d)" % (len(tops), TOPROWS, TOPH)),
        emit_bytes("BotStr", [b for t in bots for b in t], 8,
                   "%d BOT strips, %d block ids each (16 x %d)" % (len(bots), BOTROWS, BOTH)),
        emit_bytes("LevTop", levtop.tolist(), 16,
                   "the level: the TOP strip of each of %d columns" % LEVCOLS),
        emit_bytes("LevBot", levbot.tolist(), 16, "and the BOT strip"),
        emit_bytes("GndTab", gndb, 16,
                   "the turf's playfield row a column, 255 over a pit - the hero"),
        "*      walks on this and jumps when it drops away",
        emit_bytes("SinTab", sin, 16, "256 entries, signed -127..127"),
        "* the hardware sprite's three LUT banks: outline, body, accent",
        "HeroLut             fdb       " + ",".join("$%04X" % rgb565(c) for c in HERO_LUT),
    ]

    bar = "*" * 68
    top = bar + "\n* %s - generated by video3/bench/mkmonster.py; do not edit by hand\n" + bar + "\n"
    os.makedirs(out, exist_ok=True)
    p = os.path.join(out, "monsterdat.asm")
    open(p, "w").write(top % "monsterdat.asm" + "\n".join(DAT) + "\n")
    print("ok    %s (%d bytes of source)" % (p, os.path.getsize(p)))

    # ── the JSON the checker reads: the DATA, not the code
    j = dict(
        blk=BLK, playrows=PLAYROWS, playh=PLAYH, toprows=TOPROWS, botrows=BOTROWS,
        toph=TOPH, both=BOTH, levcols=LEVCOLS, vscroll=VSCROLL,
        r_live=R_LIVE, r_topbank=R_TOPBANK, r_botbank=R_BOTBANK, r_clean=R_CLEAN,
        r_art=R_ART, c_art=C_ART, r_blk=R_BLK, bankrows=bankrows, bw=bw,
        nblk=nb, ntop=len(tops), nbot=len(bots), nspr=NSPR, ngait=NGAIT,
        pal=[rgb565(c) for c in pal], pal0=0xF81F,
        blocks=b64(np.stack(blocks).reshape(-1).tolist()),
        tops=b64([b for t in tops for b in t]),
        bots=b64([b for t in bots for b in t]),
        levtop=b64(levtop.tolist()), levbot=b64(levbot.tolist()),
        art=b64(art.reshape(-1).tolist()), gnd=b64(gndb),
        herolut=[rgb565(c) for c in HERO_LUT],
    )
    jp = os.path.join(here, "monster.json")
    open(jp, "w").write(json.dumps(j))
    print("ok    %s (%d bytes)" % (jp, os.path.getsize(jp)))

    # ── a preview, so the art can be judged without booting anything
    from PIL import Image
    W = 96
    prev = np.zeros((PLAYH, W * BLK), dtype=np.uint8)
    for x in range(W):
        for r in range(PLAYROWS):
            prev[r * BLK:(r + 1) * BLK, x * BLK:(x + 1) * BLK] = blocks[ids[r, x]]
    lut = np.array([[0xF8, 0x00, 0xF8]] + [snap565(c) for c in pal], dtype=np.uint8)
    im = Image.fromarray(lut[prev])
    strip = Image.new("RGB", (W * BLK, PLAYH + BLK * NSPR // 4), (12, 12, 16))
    strip.paste(im, (0, 0))
    lut2 = lut.copy()
    lut2[0] = (24, 24, 32)                      # the key, shown as the sheet's ground
    strip.paste(Image.fromarray(lut2[art]).resize((NSPR * BLK * 4, BLK * 4), Image.NEAREST),
                (0, PLAYH))
    pp = os.path.join(here, "monster-art.png")
    strip.save(pp)
    print("ok    %s" % pp)
    print("      %d blocks, %d TOP strips, %d BOT strips, %d level columns (%d px)"
          % (nb, len(tops), len(bots), LEVCOLS, LEVCOLS * BLK))
    print("      module data: %d B blocks + %d B art + %d B strips + %d B map"
          % (len(bankdat), art.size, len(tops) * TOPROWS + len(bots) * BOTROWS,
             LEVCOLS * 3))


if __name__ == "__main__":
    main()
