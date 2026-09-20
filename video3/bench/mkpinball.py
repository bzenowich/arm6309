#!/usr/bin/env python3
"""mkpinball.py [CMDSDIR] - the `pinball` scene's table, as lwasm source and JSON.

    python3 video3/bench/mkpinball.py ../nitros9/level2/arm6309/cmds

Writes, beside pinball.asm:

    pinballdat.asm   the palette, the 16 x 16 block bank, the table's block
                     map and its COLLISION map, the keyed ball and flipper
                     art, the hardware sprite's shapes and a sine table

and, in video3/bench/:

    pinball.json     ⭐ THE SAME DATA, for video3/bench/checkv3pin.py, which
                     rebuilds every byte the card should hold and compares it
                     against a VRAM dump.  The ROM and the model share the
                     DATA and no code - bench/README.md's rule.
    pinball-art.png  the whole 640 x 512 table, for reviewing the art without
                     running the machine

⭐ THE TABLE IS 640 x 512 - 327 KB of the card's 512 KB ring, two and a half
screens tall - and `VSCROLL` follows the ball for ONE register write a frame
(optimizations.md §10).  There is no refill and no second page: 512 rows are
all the ring has.

═══ WHY THE TABLE IS BUILT OUT OF BLOCKS, AND WHY THE ART IS FLAT ═══════════

327,680 bytes of picture cannot live in a NitrOS-9 module (64 K of address
space, and the ROM disk had 6,656 bytes free (⚠ HISTORICAL: the demos and their data moved to the SD
card on 2026-09-20 and the ROM disk now has 358,400 free) before this scene took some
back).  So the table is 40 x 32 cells of 16 x 16 interned BY CONTENT, exactly
as `monster` does it - the difference being that a pinball table is built
ONCE at start-up and never refilled, so the blocks are copied straight into
place and no strip composition is needed.

⛔ AND THE ART IS DELIBERATELY FLAT-GROUND, which is a block-budget decision
before it is an art one.  `monster` gave its background a 208-row gradient and
paid for it with one block a row; anything laid OVER such a background
multiplies by the row it sits on.  Here the playfield is three flat zones with
dither grain, so a bumper, a rail or a slope composites over ONE background
and costs ONE block wherever it is placed - which is what buys a 1,280-cell
table out of under 128 blocks.  A real playfield is flat paint with art on
top, so the constraint and the subject agree.

⛔ INDEX 0 IS THE COPY ENGINE'S COLOUR KEY (keyed-copy.md) and may not be a
visible colour: the ball and the flipper art are keyed, their holes are 0, and
`assert_key_free` checks every opaque byte.  LUT entry 0 is BRIGHT MAGENTA so
a leak is unmistakable on a contact sheet.

⭐ THE SCOREBOARD AND THE LAMPS ARE PALETTE ENTRIES, NOT PIXELS.  50 of the
256 LUT entries are reserved: 8 lamps and 6 seven-segment digits.  Nothing
dithers into them - the quantiser only ever returns 1..205 - and the cells
that use them are painted with the index AFTER the dither.  A lamp flashing or
a digit changing is then a LUT write and costs the copy engine nothing at all,
which is the one thing this card gives away free.
"""
import base64
import hashlib
import json
import math
import os
import sys

import numpy as np

# ─────────────────────────────────────────────────────────── geometry
BLK = 16
CW, CH = 40, 32                  # the table in cells
TW, TH = CW * BLK, CH * BLK      # 640 x 512
VIEWH = 200
VSMAX = TH - VIEWH               # 312: the highest VSCROLL with no ring wrap
PLAYR = 26                       # cell rows 0..25 are the playfield ...
SCORER = PLAYR                   # ... and 26..31 the scoreboard, which scrolls
MAXBLK = 96                      # the module's budget, and the bank's

# the spare 384 columns of the 1024-wide ring, and what is in them
C_BANK = 640
BANKW = 1024 - C_BANK            # 384
# ⭐ SIXTEEN BLOCKS A BAND AND NOT TWENTY-FOUR, which the 384 spare columns
# would allow.  The ROM turns a block id into (band, slot) on every one of
# 1,280 copies, and 24 is not a power of two: `andb #23` is not `mod 24`, it
# is a mask, and the first draft built two thirds of the table out of the
# wrong blocks with it.  16 makes the split a shift and a mask and cannot be
# got wrong.
BPB = 16                         # blocks a band, and a power of two
R_BANK = 0                       # the block bank: up to 6 bands of 16, rows 0..95
R_FLIP, FLIPW, FLIPH = 96, 48, 32     # 8 composed flipper frames, 8*48 = 384
R_BALL, BALLW, BALLH = 128, 20, 16    # the keyed ball art
NBALLF = 4                            # ... four frames of it
R_SAVE = 144                          # the save-behind scratch, one slot a ball
R_FART = 160                          # the KEYED flipper art, which the frames are composed from
MAXBLIT = 14                          # blit balls (ball 0 is the hardware sprite)
NGAIT = 4                             # the hardware sprite's shapes
R_SPR, C_SPR = 511, 960               # MAPBASE 7's top 64 bytes (armvid.d)

# ── the palette's three tenants
NLAMP = 8
NDIG = 6
NSEG = NDIG * 7
NART = 255 - NLAMP - NSEG        # 205 dithered colours
LAMP0 = 1 + NART                 # 206
SEG0 = LAMP0 + NLAMP             # 214
assert SEG0 + NSEG == 256

# ── the cell kinds, which are the COLLISION map as well as the art.
# ⚠ A DEFLECTOR IS NAMED BY WHERE IT SENDS A FALLING BALL, not by which corner
# the wedge fills: K_DEFR's hypotenuse runs from the cell's top-left to its
# bottom-right, so reflecting about it SWAPS the velocity ((vx, vy) -> (vy,
# vx)) and a ball falling onto it leaves to the RIGHT.  K_DEFL is the mirror
# ((vx, vy) -> (-vy, -vx)).  Getting this pair the wrong way round makes a
# funnel that feeds the drain, which is how it was found.
K_EMPTY, K_SOLID, K_DEFR, K_DEFL = 0, 1, 2, 3
K_BUMP0, K_BUMP1, K_BUMP2 = 4, 5, 6
K_SLINGL, K_SLINGR = 7, 8
K_TARGET, K_LANE, K_DRAIN = 9, 10, 11
K_FLIPL, K_FLIPR = 12, 13
K_PLUNGE = 14                    # the seat at the bottom of the lane: it FIRES
# ⭐ AND THE LANE'S MOUTH IS A KICKER, NOT A DEFLECTOR.  A 45 degree mirror
# reflects the ball's own speed, and at the top of a lane the ball is at its
# SLOWEST - so it left the mouth at 7 px a frame, fell into the divider one
# cell below and came straight back.  A kicker gives it the full VMAX
# leftwards and it is out of the lane in one frame.
K_KICKL = 15

# ── the flippers, in table pixels.  A frame is FLIPW x FLIPH at (x, y), which
# is exactly cell row 23, columns 16..18 and 21..23 - so the collision grid and
# the composed picture are the same three cells.
FLIP_LX, FLIP_RX, FLIP_Y = 16 * BLK, 21 * BLK, 22 * BLK
NFLIPF = 4                       # rest, two intermediates, up


# ─────────────────────────────────────────────────────── the palette
def rgb565(c):
    r, g, b = int(c[0]), int(c[1]), int(c[2])
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def snap565(c):
    v = rgb565(c)
    r5, g6, b5 = v >> 11, (v >> 5) & 63, v & 31
    return ((r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2))


class Quant:
    """NART colours in indices 1..NART, and Floyd-Steinberg against them.

    ⚠ The search never considers 0 (the key) and never reaches LAMP0 (the
    reserved entries), so neither can come out of a dither.  That is
    structural; assert_key_free and assert_no_reserved check it anyway.
    """

    def __init__(self, cols):
        assert len(cols) == NART
        self.rgb = np.array(cols, dtype=np.float64)

    def nearest(self, px):
        d = self.rgb - px
        return int(np.argmin((d * d).sum(1))) + 1

    def dither(self, img, alpha=None):
        h, w, _ = img.shape
        work = img.astype(np.float64).copy()
        out = np.zeros((h, w), dtype=np.uint8)
        for y in range(h):
            for x in range(w):
                if alpha is not None and not alpha[y, x]:
                    continue        # a hole: index 0, and its error is nobody's
                old = work[y, x]
                i = self.nearest(np.clip(old, 0, 255))
                out[y, x] = i
                err = old - self.rgb[i - 1]
                if x + 1 < w and (alpha is None or alpha[y, x + 1]):
                    work[y, x + 1] += err * (7 / 16)
                if y + 1 < h:
                    if x and (alpha is None or alpha[y + 1, x - 1]):
                        work[y + 1, x - 1] += err * (3 / 16)
                    if alpha is None or alpha[y + 1, x]:
                        work[y + 1, x] += err * (5 / 16)
                    if x + 1 < w and (alpha is None or alpha[y + 1, x + 1]):
                        work[y + 1, x + 1] += err * (1 / 16)
        return out


def build_palette(samples):
    """NART colours by median cut over the art's own pixels, snapped to 5/6/5.

    ⚠ SNAPPED BEFORE THE DITHER: the LUT stores RGB565, so a palette entry
    chosen in 8-bit space is not the colour the card shows, and a dither aimed
    at a colour the card cannot make is a dither that makes things worse.
    """
    from PIL import Image
    px = np.concatenate([s.reshape(-1, 3) for s in samples]).astype(np.uint8)
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


# ─────────────────────────────────────────────────── continuous tone
def lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def hashnoise(x, y, s=0):
    """Deterministic value noise in [0, 1) - the art is the same byte for byte
    on any machine, which a numpy RNG would not guarantee across versions."""
    h = (x * 374761393 + y * 668265263 + s * 2654435761) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65536.0


def grain(base, y, x, amp, seed):
    n = (hashnoise(x, y, seed) - 0.5) * amp
    return [base[0] + n, base[1] + n, base[2] + n]


# the three flat zones.  ⭐ FLAT, so an overlay costs one block wherever it is
ZONE = {
    "play":  (30, 46, 62),       # the playfield's blue-grey paint
    "arch":  (52, 28, 74),       # the upper arch, a deeper violet
    "apron": (26, 26, 32),       # the apron below the flippers
    "lane":  (18, 30, 44),       # the plunger lane
    "fade":  (41, 37, 68),       # one row that carries the arch into the play
    "panel": (16, 16, 22),       # the scoreboard's inset
    "trim":  (52, 40, 30),       # its wooden trim
}
ZGRAIN = {"play": 13, "arch": 15, "apron": 9, "lane": 9, "panel": 6,
          "trim": 18, "fade": 14}


def zone_img(z, var=0):
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    for y in range(BLK):
        for x in range(BLK):
            img[y, x] = grain(ZONE[z], y, x, ZGRAIN[z], 100 + var)
    return np.clip(img, 0, 255)


STEEL = ((214, 222, 236), (120, 132, 154), (58, 64, 82))


def cell_rail(edges):
    """A chrome rail filling the cell, bevelled on the named edges."""
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    for y in range(BLK):
        for x in range(BLK):
            t = 0.0
            if "l" in edges:
                t = max(t, 1.0 - x / 5.0)
            if "r" in edges:
                t = max(t, 1.0 - (BLK - 1 - x) / 5.0)
            if "t" in edges:
                t = max(t, 1.0 - y / 5.0)
            if "b" in edges:
                t = max(t, 1.0 - (BLK - 1 - y) / 5.0)
            c = lerp(STEEL[1], STEEL[0], max(0.0, t) ** 1.4)
            if "b" in edges and y > BLK - 4:
                c = lerp(c, STEEL[2], 0.6)
            img[y, x] = grain(c, y, x, 12, 41)
    return np.clip(img, 0, 255), np.ones((BLK, BLK), bool)


def over(base, img, al):
    out = base.copy()
    out[al] = img[al]
    return out


def wedge(kind):
    """A SOLID 45 degree deflector, filling half the cell - the moulded guide
    the bottom of a table is made of.  `r` sends a falling ball right."""
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.zeros((BLK, BLK), bool)
    for y in range(BLK):
        for x in range(BLK):
            d = (y - x) / 16.0 if kind == "r" else (y - (BLK - 1 - x)) / 16.0
            if d < 0:
                continue
            c = lerp((196, 204, 220), (74, 82, 104), min(1.0, d * 2.0))
            img[y, x] = grain(c, y, x, 11, 43)
            al[y, x] = True
    return img, al


def bar(kind):
    """A THIN chrome guide rail across the cell at 45 degrees - the wire
    guides a real playfield is strung with, where a filled wedge would wall
    off half the table."""
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.zeros((BLK, BLK), bool)
    for y in range(BLK):
        for x in range(BLK):
            d = (y - x) if kind == "r" else (y - (BLK - 1 - x))
            if -1 <= d <= 4:
                c = lerp(STEEL[0], STEEL[2], (d + 1) / 6.0)
                img[y, x] = grain(c, y, x, 10, 52)
                al[y, x] = True
    return img, al


def bumper_cell(dy, dx, cap):
    """One of a 3 x 3 pop bumper.  dy, dx in -1..1; cap = the centre.

    The ring's lit pixels take lamp 3 (all three bumpers share it) and the
    cap's take lamp 0..2 - so the ring pulses as one and the caps flash
    individually, which is three blocks of art instead of twenty-seven.
    """
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.zeros((BLK, BLK), bool)
    lamp = np.zeros((BLK, BLK), np.uint8)
    for y in range(BLK):
        for x in range(BLK):
            px, py = dx * BLK + x - 7.5, dy * BLK + y - 7.5
            r = math.hypot(px, py)
            if r > 23.0:
                continue
            al[y, x] = True
            if r > 18.0:                       # the skirt
                img[y, x] = grain(lerp((96, 78, 52), (54, 42, 28),
                                       (r - 18.0) / 5.0), y, x, 12, 44)
            elif r > 13.0:                     # the lamp ring
                img[y, x] = (180, 150, 60)
                lamp[y, x] = LAMP0 + 3
            elif r > 10.0:
                img[y, x] = grain((72, 60, 44), y, x, 10, 45)
            else:                              # the cap
                sh = max(0.0, 1.0 - math.hypot(px + 3, py + 3) / 13.0)
                img[y, x] = lerp((150, 70, 40), (250, 200, 130), sh)
                if r < 7.0:
                    lamp[y, x] = LAMP0 + cap
    return img, al, lamp


def sling_cell(side, dy, dx):
    """One quarter of a 32 x 32 slingshot: a right triangle whose hypotenuse
    faces the middle of the table, with a lit rubber along that face."""
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.zeros((BLK, BLK), bool)
    lamp = np.zeros((BLK, BLK), np.uint8)
    for y in range(BLK):
        for x in range(BLK):
            px, py = dx * BLK + x, dy * BLK + y      # 0..31 inside the 2 x 2
            face = (31 - px) - py if side == "l" else px - py
            if face < 0:
                continue
            al[y, x] = True
            if face < 4:
                img[y, x] = (210, 96, 64)
                lamp[y, x] = LAMP0 + (4 if side == "l" else 5)
            else:
                img[y, x] = grain(lerp((104, 78, 56), (46, 34, 26),
                                       min(1.0, face / 26.0)), y, x, 12, 46)
    return img, al, lamp


def target_cell():
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.zeros((BLK, BLK), bool)
    lamp = np.zeros((BLK, BLK), np.uint8)
    for y in range(BLK):
        for x in range(BLK):
            if 3 <= y <= 12:
                al[y, x] = True
                if 5 <= y <= 10 and 2 <= x <= 13:
                    img[y, x] = (210, 200, 110)
                    lamp[y, x] = LAMP0 + 6
                else:
                    img[y, x] = grain((78, 70, 60), y, x, 10, 47)
    return img, al, lamp


def lane_cell():
    """A painted lane arrow - no collision, a lamp and a score."""
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.zeros((BLK, BLK), bool)
    lamp = np.zeros((BLK, BLK), np.uint8)
    for y in range(BLK):
        for x in range(BLK):
            d = abs(x - 7.5)
            if (y >= 4 and d <= (y - 3) * 0.9 and y <= 9) or (10 <= y <= 13 and d <= 2.5):
                al[y, x] = True
                img[y, x] = (230, 220, 150)
                lamp[y, x] = LAMP0 + 6
    return img, al, lamp


def drain_cell():
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.ones((BLK, BLK), bool)
    for y in range(BLK):
        for x in range(BLK):
            img[y, x] = grain(lerp((28, 22, 26), (8, 6, 10), y / 15.0), y, x, 6, 48)
    return img, al, np.zeros((BLK, BLK), np.uint8)


def insert_cell(lamp_i):
    """A round lamp insert set into the playfield."""
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.zeros((BLK, BLK), bool)
    lamp = np.zeros((BLK, BLK), np.uint8)
    for y in range(BLK):
        for x in range(BLK):
            r = math.hypot(x - 7.5, y - 7.5)
            if r > 6.8:
                continue
            al[y, x] = True
            if r > 5.4:
                img[y, x] = grain((58, 52, 46), y, x, 8, 49)
            else:
                img[y, x] = (200, 180, 90)
                lamp[y, x] = LAMP0 + lamp_i
    return img, al, lamp


# ── the seven-segment digits: 16 x 32 in two cells
SEGBOX = [  # (x0, y0, x1, y1) inclusive, in the 16 x 32 digit box
    (3, 1, 12, 3),      # a  top
    (12, 3, 14, 15),    # b  upper right
    (12, 17, 14, 29),   # c  lower right
    (3, 29, 12, 31),    # d  bottom
    (1, 17, 3, 29),     # e  lower left
    (1, 3, 3, 15),      # f  upper left
    (3, 15, 12, 17),    # g  middle
]


def digit_cells(d):
    """The two 16 x 16 halves of digit d, painted with its segment indices."""
    img = np.zeros((32, BLK, 3), dtype=np.float64)
    al = np.ones((32, BLK), bool)
    lamp = np.zeros((32, BLK), np.uint8)
    for y in range(32):
        for x in range(BLK):
            img[y, x] = grain((14, 14, 20), y, x, 5, 50)
    for s, (x0, y0, x1, y1) in enumerate(SEGBOX):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                img[y, x] = (120, 40, 40)
                lamp[y, x] = SEG0 + d * 7 + s
    return (img[:BLK], al[:BLK], lamp[:BLK]), (img[BLK:], al[BLK:], lamp[BLK:])


# ─────────────────────────────────────────────────── the keyed art
def ball_art(f):
    """A 20 x 16 chrome ball, keyed: its holes are index 0.

    ⚠ 20 WIDE AND 16 TALL because a VMODE 00 picture is 640 x 200 doubled to
    400 lines on a 4:3 screen, so a pixel is about 0.83 as wide as it is tall
    and a round ball is 1.2 times wider than it is high.
    """
    img = np.zeros((BALLH, BALLW, 3), dtype=np.float64)
    al = np.zeros((BALLH, BALLW), bool)
    hx = 6.2 + 3.0 * math.cos(f * math.pi / 2)
    hy = 5.0 + 1.6 * math.sin(f * math.pi / 2)
    for y in range(BALLH):
        for x in range(BALLW):
            dx, dy = (x - 9.5) / 9.6, (y - 7.5) / 7.6
            r = math.hypot(dx, dy)
            if r > 1.0:
                continue
            al[y, x] = True
            sh = max(0.0, 1.0 - math.hypot(x - hx, (y - hy) * 1.2) / 6.0)
            c = lerp((44, 52, 70), (196, 208, 228), max(0.0, 1.0 - r) ** 0.6)
            c = lerp(c, (255, 255, 255), sh ** 2)
            if r > 0.88:
                c = lerp(c, (20, 22, 32), (r - 0.88) / 0.12)
            img[y, x] = c
    return img, al


def flipper_art(side, f):
    """A 48 x 32 keyed flipper at animation frame f: rest (pointing down and
    inward) through to fully raised.  The pivot is at the OUTER end."""
    img = np.zeros((FLIPH, FLIPW, 3), dtype=np.float64)
    al = np.zeros((FLIPH, FLIPW), bool)
    ang = 0.46 - 0.92 * (f / float(NFLIPF - 1))   # +down at rest, -up at f=3
    if side == "r":
        px, py = FLIPW - 6.0, 16.0
        ang = math.pi - ang
    else:
        px, py = 6.0, 16.0
    L = 36.0
    for y in range(FLIPH):
        for x in range(FLIPW):
            vx, vy = x - px, y - py
            t = vx * math.cos(ang) + vy * math.sin(ang)
            n = abs(-vx * math.sin(ang) + vy * math.cos(ang))
            wdt = 5.6 - 2.6 * max(0.0, t) / L
            if -4.0 <= t <= L and n <= wdt:
                al[y, x] = True
                sh = 1.0 - n / max(0.8, wdt)
                base = (230, 60, 60) if side == "l" else (70, 170, 240)
                img[y, x] = lerp(lerp((60, 18, 18) if side == "l" else (16, 46, 80),
                                      base, 0.55 + 0.45 * sh),
                                 (255, 255, 255), 0.35 * sh ** 3)
            if math.hypot(vx, vy) < 4.6:            # the pivot boss
                al[y, x] = True
                img[y, x] = lerp(STEEL[1], STEEL[0],
                                 max(0.0, 1.0 - math.hypot(vx + 1, vy + 1) / 4.4))
    return img, al


# the hardware sprite: 16 x 16 of 2-bit codes.  1 outline, 2 body, 3 highlight
def spr_ball(f):
    code = np.zeros((16, 16), np.uint8)
    hx = 5.2 + 2.6 * math.cos(f * math.pi / 2)
    hy = 5.0 + 1.6 * math.sin(f * math.pi / 2)
    for y in range(16):
        for x in range(16):
            r = math.hypot(x - 7.5, y - 7.5) / 7.6
            if r > 1.0:
                continue
            code[y, x] = 1 if r > 0.84 else 2
            if math.hypot(x - hx, y - hy) < 2.4:
                code[y, x] = 3
    out = []
    for y in range(16):
        for pl in (0, 1):
            bits = [(code[y, x] >> pl) & 1 for x in range(16)]
            out.append(sum(1 << (7 - i) for i in range(8) if bits[i]))
            out.append(sum(1 << (7 - i) for i in range(8) if bits[8 + i]))
    return out


SPR_LUT = [(0x18, 0x1A, 0x28), (0xC8, 0xD4, 0xE8), (0xFF, 0xFF, 0xFF)]


# ───────────────────────────────────────────────── the table's layout
def build_map():
    """A 40 x 32 grid of (art-kind, collision-kind).

    ⭐ ONE LIST, TWO USES.  The picture and the physics come out of this grid,
    so a rail the ball passes through or a wall with nothing drawn on it is
    not a thing that can happen - the art IS the collision map.
    """
    art = [["play"] * CW for _ in range(CH)]
    col = [[K_EMPTY] * CW for _ in range(CH)]

    def rect(x0, y0, x1, y1, a, k):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                art[y][x], col[y][x] = a, k

    # ── the zones: flat paint, so anything laid over them costs ONE block
    rect(0, 0, CW - 1, PLAYR - 1, "play", K_EMPTY)
    rect(2, 1, 35, 12, "arch", K_EMPTY)
    rect(2, 13, 35, 13, "fade", K_EMPTY)
    rect(2, 21, 35, 25, "apron", K_EMPTY)

    # ── the cabinet: rails all round, and a plunger lane down the right
    rect(0, 0, CW - 1, 0, "railb", K_SOLID)
    rect(0, 1, 1, PLAYR - 1, "railr", K_SOLID)
    rect(CW - 1, 1, CW - 1, PLAYR - 1, "raill", K_SOLID)
    # ⚠ THE DIVIDER STARTS AT ROW 6: the kicker above is four cells tall, the
    # ball can be caught by it with its centre one cell lower still, and it
    # then has to have somewhere to go.
    rect(36, 6, 36, PLAYR - 1, "railc", K_SOLID)          # the lane divider
    rect(37, 1, 38, PLAYR - 2, "lane", K_EMPTY)
    # ⭐ THE PLUNGER, AND IT FIRES.  A seat that merely bounced cost the scene
    # its whole first day: the ball keeps 7/8 of its speed off a wall, so the
    # rise shrinks 0.77 a cycle and after two bounces it no longer reaches the
    # top of a 384-pixel lane.  The table then ran, gated green and scored
    # nothing, because the ball never left the lane at all.
    rect(37, PLAYR - 1, 38, PLAYR - 1, "railb", K_PLUNGE)
    # ⭐ THE LANE'S MOUTH: the deflector that turns a ball travelling UP into
    # one travelling LEFT, over the top of the arch.  ⚠ It is the one marked
    # "sends a FALLING ball right", because the reflection is about the line
    # and not about the direction: (vx, vy) -> (vy, vx) takes (0, -v) to
    # (-v, 0).  The mirror image of this cell fires the ball back down its own
    # lane, which is exactly what the first draft did.
    for y in (1, 2, 3, 4):
        art[y][37], col[y][37] = "wedgeR", K_KICKL
        art[y][38], col[y][38] = "wedgeR", K_KICKL

    # ── ⭐ THE ROLLOVER BANK, all the way across the top of the arch.  ⚠ Not
    # three arrows, and not seven: THIRTY.  A ball leaving the plunger lane
    # crosses this row exactly once and wherever it happens to be, so a sparse
    # bank is a table that scores only by luck - and this one scored 000000
    # for three whole runs while every other check was green.
    for x in range(4, 34):
        art[3][x], col[3][x] = "arrow", K_LANE

    # ── three pop bumpers, 3 x 3 cells each.  ⭐ The ring is one shared block
    # and only the CAP carries the bumper's own lamp, which is 11 blocks of
    # art where nine cells times three bumpers would have been 27.
    # ⭐ FIVE OF THEM, IN TWO BANDS, and that is a playability decision with a
    # measurable consequence: three bumpers covered nine of the arch's
    # thirty-four columns and the ball's diagonal from the lane went between
    # them every time.
    for b, (bx, by) in enumerate(((11, 6), (19, 6), (27, 6), (15, 10), (23, 10))):
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                cap = (dy == 0 and dx == 0)
                art[by + dy][bx + dx] = "bmp%d_%d_%d" % ((b % 3) if cap else 9,
                                                         dy + 1, dx + 1)
                col[by + dy][bx + dx] = K_BUMP0 + (b % 3)

    # ── two drop-target banks
    for x in list(range(5, 8)) + list(range(32, 35)):
        art[15][x], col[15][x] = "target", K_TARGET

    # ── thin wire guides in the middle of the table
    for i in range(4):
        art[16 + i][3 + i], col[16 + i][3 + i] = "barR", K_DEFR
        art[16 + i][35 - i], col[16 + i][35 - i] = "barL", K_DEFL

    # ── the slingshots, just above the flippers
    for dy in (0, 1):
        for dx in (0, 1):
            art[19 + dy][10 + dx] = "slgl_%d_%d" % (dy, dx)
            col[19 + dy][10 + dx] = K_SLINGL
            art[19 + dy][28 + dx] = "slgr_%d_%d" % (dy, dx)
            col[19 + dy][28 + dx] = K_SLINGR

    # ── two inlane arrows the funnel delivers the ball over
    for x in (14, 25):
        art[20][x], col[20][x] = "arrow", K_LANE

    # ── lamp inserts scattered over the playfield
    # ⚠ AND EVERY LAMP HAS TO BE SOMEWHERE THE CAMERA GOES.  The flasher lived
    # only on the scoreboard once, which the view shows for a few frames a
    # ball, so checkv3pin.py's lamp gate could not see it work.
    spots = [(7, 11), (32, 11), (15, 16), (24, 16), (19, 19), (12, 17), (27, 17)]
    for i, (x, y) in enumerate(spots):
        art[y][x], col[y][x] = "ins%d" % (i % 3), K_EMPTY
    for i, x in enumerate((8, 12, 16, 20, 24, 28, 32)):
        art[2][x], col[2][x] = "ins%d" % (3 + i % 5), K_EMPTY

    # ── ⭐ THE INLANE GUIDES, which are what makes the flippers worth having:
    # a moulded funnel down each side that gathers the ball onto them.  The
    # top edge of each is a deflector and everything below it is solid, so it
    # reads as one shape instead of as a row of teeth.
    GL = {19: 3, 20: 6, 21: 9, 22: 12, 23: 15}
    for y, gx in GL.items():
        for x in range(2, gx):
            art[y][x], col[y][x] = "railc", K_SOLID
        art[y][gx], col[y][gx] = "wedgeR", K_DEFR
        rx = 39 - gx
        rx = min(rx, 35)
        for x in range(rx + 1, 36):
            art[y][x], col[y][x] = "railc", K_SOLID
        art[y][rx], col[y][rx] = "wedgeL", K_DEFL

    # ── the flippers, and below them the drain.  ⭐ The art in the flipper
    # cells is plain apron: the flipper is COMPOSED IN VRAM over these very
    # pixels at start-up, one frame a slot, which is why it never needs a
    # colour key, a save or a restore at run time.
    rect(16, 22, 18, 23, "apron", K_FLIPL)
    rect(21, 22, 23, 23, "apron", K_FLIPR)
    rect(2, 24, 15, 25, "railc", K_SOLID)
    rect(24, 24, 35, 25, "railc", K_SOLID)
    rect(16, 25, 23, 25, "drain", K_DRAIN)

    # ── the scoreboard: trim, an inset panel, six digits and eight lamps
    rect(0, SCORER, CW - 1, CH - 1, "trim", K_SOLID)
    rect(2, SCORER + 1, CW - 3, CH - 2, "panel", K_SOLID)
    for d in range(NDIG):
        x = 14 + d * 2
        art[SCORER + 1][x], art[SCORER + 2][x] = "dig%dt" % d, "dig%db" % d
    for k in range(NLAMP):
        art[SCORER + 4][16 + k] = "pin%d" % k
    return art, col


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

    art, col = build_map()

    # ── every distinct art kind, rendered once at 16 x 16 in continuous tone
    kinds = sorted({art[y][x] for y in range(CH) for x in range(CW)})
    zone_of = {z: z for z in ZONE}
    tone, alpha, lampi = {}, {}, {}
    for k in kinds:
        if k in zone_of:
            tone[k] = zone_img(zone_of[k])
            alpha[k] = np.ones((BLK, BLK), bool)
            lampi[k] = np.zeros((BLK, BLK), np.uint8)
            continue
        base = zone_img("play")
        lp = np.zeros((BLK, BLK), np.uint8)
        if k.startswith("rail"):
            i, a = cell_rail(k[4:] if len(k) > 4 else "")
        elif k == "wedgeR":
            i, a = wedge("r")
            base = zone_img("apron")
        elif k == "wedgeL":
            i, a = wedge("l")
            base = zone_img("apron")
        elif k == "barR":
            i, a = bar("r")
        elif k == "barL":
            i, a = bar("l")
        elif k.startswith("bmp"):
            bi, dy, dx = int(k[3]), int(k.split("_")[1]), int(k.split("_")[2])
            i, a, lp = bumper_cell(dy - 1, dx - 1, bi if bi < 9 else 0)
            base = zone_img("arch")
        elif k.startswith("slg"):
            dy, dx = int(k.split("_")[1]), int(k.split("_")[2])
            i, a, lp = sling_cell(k[3], dy, dx)
            base = zone_img("apron")
        elif k == "target":
            i, a, lp = target_cell()
            base = zone_img("arch")
        elif k == "arrow":
            i, a, lp = lane_cell()
            base = zone_img("arch")
        elif k == "drain":
            i, a, lp = drain_cell()
            base = zone_img("apron")
        elif k.startswith("ins"):
            i, a, lp = insert_cell(int(k[3]))
        elif k.startswith("pin"):
            i, a, lp = insert_cell(int(k[3]))
            base = zone_img("panel")
        elif k.startswith("dig"):
            d, half = int(k[3]), k[4]
            t, b = digit_cells(d)
            i, a, lp = t if half == "t" else b
            base = zone_img("panel")
        else:
            raise KeyError(k)
        tone[k] = np.clip(over(base, i, a), 0, 255)
        alpha[k] = np.ones((BLK, BLK), bool)
        lampi[k] = lp

    # ── the keyed art, which shares the palette with the table
    balls = [ball_art(f) for f in range(NBALLF)]
    flips = [(s, f, flipper_art(s, f)) for s in ("l", "r") for f in range(NFLIPF)]

    samples = [tone[k] for k in kinds]
    for img, al in balls:
        samples.append(img[al].reshape(-1, 1, 3))
    for _, _, (img, al) in flips:
        samples.append(img[al].reshape(-1, 1, 3))
    q = Quant(build_palette(samples))

    # ── the block bank: every distinct 16 x 16 the table asks for
    blocks, index = [], {}

    def intern(arr):
        key = hashlib.sha1(arr.tobytes()).hexdigest()
        if key not in index:
            index[key] = len(blocks)
            blocks.append(arr)
        return index[key]

    kblk = {}
    for k in kinds:
        b = q.dither(tone[k])
        lp = lampi[k]
        b[lp > 0] = lp[lp > 0]           # ⭐ the reserved indices, after the dither
        kblk[k] = intern(b)
    assert len(blocks) <= MAXBLK, ("the block bank overflows the module's budget",
                                   len(blocks), MAXBLK)

    blkmap = np.zeros((CH, CW), np.uint8)
    colmap = np.zeros((CH, CW), np.uint8)
    for y in range(CH):
        for x in range(CW):
            blkmap[y, x] = kblk[art[y][x]]
            colmap[y, x] = col[y][x]

    ballart = np.zeros((BALLH, NBALLF * BALLW), np.uint8)
    for f, (img, al) in enumerate(balls):
        ballart[:, f * BALLW:(f + 1) * BALLW] = q.dither(img, al)
    flipart = np.zeros((FLIPH, len(flips) * FLIPW), np.uint8)
    for i, (_, _, (img, al)) in enumerate(flips):
        flipart[:, i * FLIPW:(i + 1) * FLIPW] = q.dither(img, al)
    spr = []
    for f in range(NGAIT):
        spr += spr_ball(f)

    # ⛔ INDEX 0 IS THE KEY and the reserved entries are not colours.
    def assert_key_free(what, arr):
        bad = int((np.asarray(arr) == 0).sum())
        assert bad == 0, "%s: %d pixels are index 0, the colour key" % (what, bad)

    for i, b in enumerate(blocks):
        assert_key_free("block %d" % i, b)
    for i in range(NBALLF):
        s = ballart[:, i * BALLW:(i + 1) * BALLW]
        assert (s != 0).any() and (s == 0).any(), "ball %d has no ink or no hole" % i
    for i in range(len(flips)):
        s = flipart[:, i * FLIPW:(i + 1) * FLIPW]
        assert (s != 0).any() and (s == 0).any(), "flipper %d has no ink or no hole" % i
    dithered = np.concatenate([b.reshape(-1) for b in blocks] +
                              [ballart.reshape(-1), flipart.reshape(-1)])
    lamps_used = set()
    for k in kinds:
        lamps_used |= set(int(v) for v in np.unique(lampi[k]) if v)
    bad = [int(v) for v in np.unique(dithered) if LAMP0 <= v < 256 and v not in lamps_used]
    assert not bad, ("the dither produced a RESERVED index", bad)
    assert len(lamps_used) == NLAMP + NSEG, (
        "every reserved entry must be painted somewhere, or nothing can show it",
        sorted(set(range(LAMP0, 256)) - lamps_used))

    # ── the block bank as the ROM uploads it: bands of BPB blocks, row-major,
    # so the upload is ONE VDATA run a VRAM row
    nb = len(blocks)
    nband = (nb + BPB - 1) // BPB
    bw = [min(BPB, nb - b * BPB) * BLK for b in range(nband)]
    bankdat = []
    for b in range(nband):
        band = np.zeros((BLK, bw[b]), np.uint8)
        for i in range(b * BPB, min(nb, (b + 1) * BPB)):
            band[:, (i % BPB) * BLK:(i % BPB) * BLK + BLK] = blocks[i]
        bankdat += band.reshape(-1).tolist()
    assert R_BANK + nband * BLK <= R_FLIP, ("the bank runs into the flipper frames",
                                            nband)

    # ── the palette: 205 art colours, then the lamps and the segments UNLIT
    pal = [rgb565(c) for c in q.rgb.astype(int)]
    LAMP_OFF = [(46, 38, 26), (46, 38, 26), (46, 38, 26), (52, 44, 20),
                (72, 30, 22), (72, 30, 22), (64, 60, 30), (58, 26, 74)]
    LAMP_ON = [(255, 220, 90), (120, 255, 160), (140, 200, 255), (255, 190, 60),
               (255, 120, 70), (255, 120, 70), (250, 240, 150), (170, 140, 255)]
    SEG_OFF, SEG_ON = (60, 18, 18), (255, 90, 60)
    palb = [0xF8, 0x1F]                           # ⭐ entry 0: the key, magenta
    for v in pal:
        palb += [v >> 8, v & 255]
    for c in LAMP_OFF:
        v = rgb565(c)
        palb += [v >> 8, v & 255]
    for _ in range(NSEG):
        v = rgb565(SEG_OFF)
        palb += [v >> 8, v & 255]
    assert len(palb) == 512

    # ⭐ A RESERVED COLOUR MAY NOT BE AN ART COLOUR, and this is not tidiness:
    # checkv3pin.py's lamp gate reads the lamps off the RECORDING, by looking
    # for their exact RGB565 among the picture's pixels.  If an art colour
    # could equal a lamp's, a lit lamp and a wall would be the same evidence.
    # ⚠ AND THE SPRITE'S THREE BANKS COUNT TOO.  LAMP_OFF[7] was (30, 26, 40)
    # and the ball's outline (24, 26, 40): different in eight bits, THE SAME
    # RGB565, and the gate spent a run reading a lamp that was really a ball.
    artv = set(pal) | {rgb565(c) for c in SPR_LUT} | {0xF81F}
    for nm, c in ([("lamp %d on" % k, LAMP_ON[k]) for k in range(NLAMP)]
                  + [("lamp %d off" % k, LAMP_OFF[k]) for k in range(NLAMP)]
                  + [("segment on", SEG_ON), ("segment off", SEG_OFF)]):
        assert rgb565(c) not in artv, (
            "%s is also an art or sprite colour - the lamp gate could not "
            "tell them apart; nudge it" % nm, c)

    sin = [int(round(127 * math.sin(2 * math.pi * i / 256))) & 255 for i in range(256)]

    def pairs(cols):
        o = []
        for c in cols:
            v = rgb565(c)
            o += [v >> 8, v & 255]
        return o

    DAT = [
        "* ⭐ THE GEOMETRY IS EMITTED, NOT RESTATED - monster.asm's lesson:",
        "*      a literal that drifted from its generator made every strip",
        "*      wrong and still looked plausible (bench/README.md).",
        "PBBLK               equ       %d        blocks in the bank" % nb,
        "PBBAND              equ       %d         bands of %d" % (nband, BPB),
        "PBBPB               equ       %d" % BPB,
        "PBBANKW             equ       %d       bytes a bank row" % (BPB * BLK),
        "PBCW                equ       %d        the table, in cells" % CW,
        "PBCH                equ       %d" % CH,
        "PBTW                equ       %d       ... and in pixels" % TW,
        "PBTH                equ       %d" % TH,
        "PBVSMAX             equ       %d       the highest VSCROLL with no wrap" % VSMAX,
        "PBCBANK             equ       %d       the spare columns" % C_BANK,
        "PBRBANK             equ       %d         the block bank" % R_BANK,
        "PBRFLIP             equ       %d        the composed flipper frames" % R_FLIP,
        "PBFLIPW             equ       %d" % FLIPW,
        "PBFLIPH             equ       %d" % FLIPH,
        "PBNFLIP             equ       %d         frames a flipper" % NFLIPF,
        "PBRBALL             equ       %d       the keyed ball art" % R_BALL,
        "PBBALLW             equ       %d" % BALLW,
        "PBBALLH             equ       %d" % BALLH,
        "PBNBALLF            equ       %d" % NBALLF,
        "PBRSAVE             equ       %d       the save-behind scratch" % R_SAVE,
        "PBRFART             equ       %d       the KEYED flipper art" % R_FART,
        "PBMAXBL             equ       %d        blit balls (0 is the sprite)" % MAXBLIT,
        "PBNGAIT             equ       %d" % NGAIT,
        "PBFLX               equ       %d       the left flipper's frame" % FLIP_LX,
        "PBFRX               equ       %d" % FLIP_RX,
        "PBFLY               equ       %d" % FLIP_Y,
        "PBLAMP0             equ       %d       the first reserved LUT entry" % LAMP0,
        "PBNLAMP             equ       %d" % NLAMP,
        "PBSEG0              equ       %d" % SEG0,
        "PBNDIG              equ       %d" % NDIG,
        "PBNRES              equ       %d        lamps + segments" % (NLAMP + NSEG),
        "* the collision kinds, which are build_map()'s and the physics'",
        "KEMPTY              equ       %d" % K_EMPTY,
        "KSOLID              equ       %d" % K_SOLID,
        "KDEFR               equ       %d        a falling ball leaves RIGHT" % K_DEFR,
        "KDEFL               equ       %d        ... and LEFT" % K_DEFL,
        "KBUMP0              equ       %d" % K_BUMP0,
        "KSLNGL              equ       %d" % K_SLINGL,
        "KSLNGR              equ       %d" % K_SLINGR,
        "KTARG               equ       %d" % K_TARGET,
        "KLANE               equ       %d" % K_LANE,
        "KDRAIN              equ       %d" % K_DRAIN,
        "KFLIPL              equ       %d" % K_FLIPL,
        "KFLIPR              equ       %d" % K_FLIPR,
        "KPLNG               equ       %d       the plunger seat: it fires" % K_PLUNGE,
        "KKICKL              equ       %d       the lane's mouth: it kicks LEFT" % K_KICKL,
        emit_bytes("PalDat", palb, 16,
                   "256 RGB565 entries, hi lo.  ⭐ 0 IS THE KEY (magenta);"),
        "*      1..%d are the art; %d..%d the lamps and %d..255 the six"
        % (NART, LAMP0, LAMP0 + NLAMP - 1, SEG0),
        "*      seven-segment digits - all of them loaded UNLIT",
        emit_bytes("LampOn", pairs(LAMP_ON), 16, "the lamps lit ..."),
        emit_bytes("LampOff", pairs(LAMP_OFF), 16, "... and out"),
        emit_bytes("SegOn", pairs([SEG_ON]), 16, "a segment lit ..."),
        emit_bytes("SegOff", pairs([SEG_OFF]), 16, "... and out"),
        "BlkBW               fdb       " + ",".join(str(w) for w in bw)
        + "        bytes in each band's row",
        emit_bytes("BlkDat", bankdat, 16,
                   "the %d blocks, ROW-MAJOR in %d band(s) of 16 rows -"
                   % (nb, nband)),
        "*      the upload is ONE VDATA run a VRAM row",
        emit_bytes("BlkMap", blkmap.reshape(-1).tolist(), 16,
                   "the table: one block id a cell, %d x %d" % (CW, CH)),
        emit_bytes("ColMap", colmap.reshape(-1).tolist(), 16,
                   "⭐ AND THE COLLISION, from the same grid: the art cannot"),
        "*      disagree with what the ball bounces off",
        emit_bytes("BallArt", ballart.reshape(-1).tolist(), 16,
                   "the keyed ball: %d frames of %d x %d, holes are index 0"
                   % (NBALLF, BALLW, BALLH)),
        emit_bytes("FlipArt", flipart.reshape(-1).tolist(), 16,
                   "the keyed flippers: %d frames of %d x %d (left then right)"
                   % (len(flips), FLIPW, FLIPH)),
        emit_bytes("SprArt", spr, 16,
                   "the hardware sprite: %d shapes of 64 bytes (plan 7's planes)"
                   % NGAIT),
        emit_bytes("SinTab", sin, 16, "256 entries, signed -127..127"),
        "* the sprite's three LUT banks: outline, body, highlight",
        "SprLut              fdb       " + ",".join("$%04X" % rgb565(c) for c in SPR_LUT),
    ]

    rule = "*" * 68
    top = rule + "\n* %s - generated by video3/bench/mkpinball.py; do not edit by hand\n" + rule + "\n"
    os.makedirs(out, exist_ok=True)
    p = os.path.join(out, "pinballdat.asm")
    open(p, "w").write(top % "pinballdat.asm" + "\n".join(DAT) + "\n")
    print("ok    %s (%d bytes of source)" % (p, os.path.getsize(p)))

    # ── the probes the checker reads the LAMPS off the recording with: a
    # pixel that carries each reserved index, in ring coordinates
    probes = {}
    for y in range(CH):
        for x in range(CW):
            lp = lampi[art[y][x]]
            for i in np.unique(lp):
                if i and int(i) not in probes:
                    ys, xs = np.where(lp == i)
                    probes[int(i)] = [int(y * BLK + ys[0]), int(x * BLK + xs[0])]

    j = dict(
        blk=BLK, cw=CW, ch=CH, tw=TW, th=TH, vsmax=VSMAX, playr=PLAYR,
        c_bank=C_BANK, bpb=BPB, r_bank=R_BANK, nband=nband,
        r_flip=R_FLIP, flipw=FLIPW, fliph=FLIPH, nflipf=NFLIPF, bw=bw,
        flip_lx=FLIP_LX, flip_rx=FLIP_RX, flip_y=FLIP_Y,
        r_ball=R_BALL, ballw=BALLW, ballh=BALLH, nballf=NBALLF,
        r_save=R_SAVE, r_fart=R_FART, maxblit=MAXBLIT, ngait=NGAIT, r_spr=R_SPR, c_spr=C_SPR,
        nblk=nb, lamp0=LAMP0, nlamp=NLAMP, seg0=SEG0, ndig=NDIG, nart=NART,
        pal=[(palb[i * 2] << 8) | palb[i * 2 + 1] for i in range(256)],
        lampon=[rgb565(c) for c in LAMP_ON], lampoff=[rgb565(c) for c in LAMP_OFF],
        segon=rgb565(SEG_ON), segoff=rgb565(SEG_OFF),
        blocks=b64(np.stack(blocks).reshape(-1).tolist()),
        blkmap=b64(blkmap.reshape(-1).tolist()),
        colmap=b64(colmap.reshape(-1).tolist()),
        ballart=b64(ballart.reshape(-1).tolist()),
        flipart=b64(flipart.reshape(-1).tolist()),
        spr=b64(spr), sprlut=[rgb565(c) for c in SPR_LUT],
        probes=probes,
    )
    jp = os.path.join(here, "pinball.json")
    open(jp, "w").write(json.dumps(j))
    print("ok    %s (%d bytes)" % (jp, os.path.getsize(jp)))

    # ── a preview of the whole table, so the art can be judged without booting
    from PIL import Image
    def unpack565(v):
        r5, g6, b5 = v >> 11, (v >> 5) & 63, v & 31
        return ((r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2))
    lut = np.array([unpack565(v) for v in j["pal"]], dtype=np.uint8)
    lut[0] = (255, 0, 255)
    for k in range(NLAMP):          # the preview shows the lamps LIT
        c = LAMP_ON[k]
        lut[LAMP0 + k] = snap565(c)
    for s in range(NSEG):
        lut[SEG0 + s] = snap565(SEG_ON)
    pic = np.zeros((TH, TW), np.uint8)
    for y in range(CH):
        for x in range(CW):
            pic[y * BLK:(y + 1) * BLK, x * BLK:(x + 1) * BLK] = blocks[blkmap[y, x]]
    # the flippers at rest, composed exactly as the ROM composes them
    for side, fx in (("l", FLIP_LX), ("r", FLIP_RX)):
        i = (0 if side == "l" else NFLIPF)
        s = flipart[:, i * FLIPW:(i + 1) * FLIPW]
        tile = pic[FLIP_Y:FLIP_Y + FLIPH, fx:fx + FLIPW].copy()
        tile[s != 0] = s[s != 0]
        pic[FLIP_Y:FLIP_Y + FLIPH, fx:fx + FLIPW] = tile
    im = Image.fromarray(lut[pic])
    sheet = Image.new("RGB", (TW, TH + 2 * BLK + 8), (10, 10, 14))
    sheet.paste(im, (0, 0))
    lut2 = lut.copy()
    lut2[0] = (24, 24, 32)
    sheet.paste(Image.fromarray(lut2[ballart]), (0, TH + 4))
    sheet.paste(Image.fromarray(lut2[flipart]), (NBALLF * BALLW + 8, TH + 4))
    pp = os.path.join(here, "pinball-art.png")
    sheet.save(pp)
    print("ok    %s" % pp)
    print("      %d blocks of %d, %d x %d cells, %d x %d px of table"
          % (nb, MAXBLK, CW, CH, TW, TH))
    print("      module data: %d B bank + %d B maps + %d B keyed art + %d B palette"
          % (len(bankdat), blkmap.size + colmap.size, ballart.size + flipart.size, 512))


if __name__ == "__main__":
    main()
