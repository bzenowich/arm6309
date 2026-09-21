#!/usr/bin/env python3
"""mkstardew.py [CMDSDIR] - the `stardew` farm's art, palette and day cycle.

    python3 video3/bench/mkstardew.py ../nitros9/level2/arm6309/cmds

Writes, beside stardew.asm:

    stardewdat.asm   the authored palette (8-bit RGB, which is the SOURCE OF
                     TRUTH the tint multiplies), the per-entry rounding bias,
                     the 256-phase tint table, the lit set, the HUD set, the
                     keyed art (chickens, the dog, four crop stages, the HUD
                     strip), the farmer's sprite shapes, the crop plots, the
                     actor cast and a sine table

and, in video3/bench/:

    stardew.pic      491,520 raw bytes - one palette index a pixel, row-major,
                     1024 to a row, 480 rows.  ⭐ 960 SD blocks of 512, so the
                     loader is a block count and not a partial tail.  It goes
                     on the SD card and is read straight into VRAM rows 0..479
    stardew.json     the DATA checkv3star.py rebuilds the world from - the
                     palette, the tint table, the geometry, the crop plots and
                     the keyed art.  ⭐ The ROM and the model share the data
                     and no code (bench/README.md's rule)
    stardew-art.png  a 1:1 preview with the palette applied at noon, and the
                     same strip at dawn, dusk and night, for reviewing the
                     art - and the DAY CYCLE - without a machine

⭐ THE HEADLINE IS THE DAY CYCLE, AND IT IS PALETTE WRITES AND NOTHING ELSE
(video3/docs/stardew.md §0).  So the palette's split IS the specification:

    0          ⛔ the copy engine's colour key.  Never a visible colour
    1..200     the world's art - ⭐ and the ONLY entries the tint touches
    201..230   the LIT SET: window glow, the lantern, the stove, fireflies,
               the moon's reflection.  The tint never touches these, so they
               keep their own brightness and BECOME the light as the world
               darkens.  This is how pixel art does night, and here it is free
    231..255   the HUD: the day bar, its marker, the energy bar, the banner.
               Constant, because a UI that dims with the sun cannot be read

⛔ INDEX 0 IS THE KEY (keyed-copy.md) and may never be a visible colour.  The
dither only ever returns 1..200, so a 0 in the .pic is impossible by
construction; `assert_key_free` checks it anyway, because "impossible by
construction" is what every defect in docs/history.md was.

═══ ⭐ THE TINT, WHICH IS A CONTRACT AND IS IMPLEMENTED TWICE ═══════════════

stardew.asm's `Tint` and this file's `pipeline()` must agree BIT FOR BIT, and
they share the DATA (the authored RGB, the bias byte, the 256-phase table)
and no code.  The contract, per channel, with gain g (128 = unity), offset o,
rounding bias d and shift s (3 for R and B, 2 for G):

    v = (c * g) >> 7        ⚠ 128 is unity EXACTLY, which is what lets a full
    if v > 255: v = 255        cycle come home to the authored value
    v = v + o ; if v > 255: v = 255
    v = v + d ; if v > 255: v = 255
    q = v >> s

⛔ AND THE TINT IS APPLIED TO THE AUTHORED COLOUR, NEVER TO THE CURRENT ONE.
Re-tinting a tinted entry compounds and the world converges on black over a
thousand frames - a drift that looks like a slow bug and is nearly invisible
in a contact sheet (stardew.md §2).  The authored 8-bit RGB lives in the
module and is read every commit; `checkv3star.py`'s compounding gate asserts
that one full cycle returns every art entry to its authored value, and
stardew.asm's mode b5 is the mutation that breaks it on purpose.

⭐ THE AUTHORED LUT IS *DEFINED* AS THE PIPELINE'S OWN OUTPUT AT NOON, and
the dither targets that.  Doing it the other way round - authoring an RGB565
and hoping the pipeline reproduces it - is how the rounding bias d would have
made "day" differ from the art's own palette by one LSB a channel.

═══ ⚠ THE ROUNDING BIAS, AND THE RISK stardew.md §6 ITEM 2 NAMES ═══════════

Floyd-Steinberg picks NEIGHBOURING palette entries and lets the eye average
them.  A per-channel affine tint commutes with averaging, so the tint itself
cannot break a dither - but the REQUANTISATION to 5/6/5 afterwards can: at
night's ~0.3 gain, 32 red levels become ~10, adjacent ramp entries collapse
onto the same output word, and a gradient that was smooth at noon bands.

`--tint-test` measures exactly that, on one region, before the whole farm is
committed (stardew.md §6 item 2's instruction).  The mitigation, if it is
needed, is the per-entry rounding bias `d`: a FIXED per-index offset applied
before the truncation, so that two entries a dither pair is made of do not
round the same way and the ramp keeps its spacing.  `d` is DATA, one byte an
entry, so setting it to zero costs nothing and changes no code.

    python3 video3/bench/mkstardew.py --tint-test     # ~40 s; prints the table
"""
import base64
import hashlib
import json
import math
import os
import sys

import numpy as np

# ─────────────────────────────────────────────────────────── geometry
W, H = 1024, 480                 # the world: 491,520 bytes of the 524,288 ring
VIEWW, VIEWH = 640, 200          # what VMODE 00 shows
HSMAX, VSMAX = W - VIEWW, H - VIEWH      # 384, 280 - the camera never wraps

BLK = 16
R_ART = 480                      # the keyed art bank: ring rows 480..495
R_SCR = 496                      # save-behind scratch: rows 496..511
C_SPR, NSPR = 0, 16              # 16 slots of 16 x 16 at columns 0..255
C_DOG, DOGW, DOGH, NDOG = 256, 24, 16, 2
C_HUD, HUDW, HUDH = 320, 160, 16
C_SCR, SCRPITCH = 0, 32          # an actor's scratch slot, 32 px apart
MAXACT = 20
C_HSCR = 640                     # the HUD's own scratch, 160 wide
# ⚠ ring row 511, columns 960..1023 is the hardware sprite's shape at MAPBASE
# 7 (plan §7, armvid.d PS.Shape) - so the scratch above stops at column 960.
assert C_HSCR + HUDW <= 960

# ── the palette's three tenants
NART = 200
LIT0, NLIT = 201, 30
HUD0, NHUD = 231, 25
assert LIT0 + NLIT == HUD0 and HUD0 + NHUD == 256

# the lit set, by name: each is a RAMP of consecutive reserved indices
LIT_RAMPS = [
    ("window", 6),     # 201..206  the house's windows
    ("lantern", 5),    # 207..211  the lantern heads on the path
    ("stove", 4),      # 212..215  the kitchen's stove, through its window
    ("firefly", 6),    # 216..221  fireflies at the forest edge
    ("moon", 6),       # 222..227  the moon's reflection on the pond
    ("pool", 3),       # 228..230  the light a lantern spills on the ground
]
assert sum(n for _, n in LIT_RAMPS) == NLIT

LIT_COLOURS = {   # (dim end, bright end) - the ramp is interpolated between
    "window":  ((120, 82, 30), (255, 236, 168)),
    "lantern": ((150, 96, 24), (255, 226, 130)),
    "stove":   ((160, 52, 16), (255, 168, 72)),
    "firefly": ((96, 120, 24), (216, 255, 128)),
    "moon":    ((70, 86, 124), (196, 214, 246)),
    "pool":    ((92, 76, 44), (148, 126, 80)),
}
HUD_COLOURS = [   # 25, and none of them may collide with an art colour
    (16, 20, 26), (36, 44, 54), (60, 72, 86), (96, 112, 128), (150, 166, 182),
    (216, 228, 240), (250, 252, 255), (28, 60, 100), (44, 96, 156), (72, 148, 220),
    (124, 196, 248), (196, 96, 40), (240, 148, 52), (252, 204, 88), (168, 220, 96),
    (92, 180, 80), (48, 132, 64), (200, 72, 84), (140, 40, 56), (84, 28, 44),
    (232, 232, 200), (180, 176, 148), (128, 124, 100), (72, 70, 58), (255, 128, 200),
]
assert len(HUD_COLOURS) == NHUD

# ─────────────────────────────────── ⭐ the day cycle, as DATA and a contract
NPHASE = 256                    # one whole day
KEYP = [0, 64, 128, 192]        # dawn, day, dusk, night; it wraps to dawn
KEYNM = ["dawn", "day", "dusk", "night"]
# gain (128 = unity) and offset, per channel.  ⚠ day IS exactly unity and no
# offset: that is what makes one full cycle come home bit for bit.
KEYTINT = [
    (112, 114, 134,  22, 22, 36),   # dawn:  cool blue-violet, lifted blacks
    (128, 128, 128,   0,  0,  0),   # day:   the authored colours, untouched
    (142, 108,  84,  26,  8,  2),   # dusk:  warm, orange-shifted
    ( 36,  40,  74,   4,  6, 26),   # night: deep blue, desaturated, ~35 % value
]
# ⭐ LUT ENTRIES A FRAME, and the number is the COMMIT's and not the tint's.
# The tint is nine multiplies and six clamps an entry and measured 250 us on
# the 6809 - so the whole of §2's "four entries in 0.24 ms inside a 353 us
# blank" is impossible if the arithmetic is done there.  stardew.asm splits
# it: the words are COMPUTED in the frame's own 5 ms of slack and only
# WRITTEN in the blank, at ~12 us an entry, so six fit where four of the
# original shape did not fit at all.
MAXPW = 6


def tint_table():
    """⭐ 256 phases x six coefficients, interpolated between the four key
    times - emitted as DATA so the 6809 and this file cannot disagree about
    an interpolation.  §2 forbids precomputing 200 x 4 PALETTES (3.2 KB that
    scales with the palette); six bytes a phase does not scale with it at
    all, and it deletes a second implementation of the same arithmetic."""
    out = []
    for p in range(NPHASE):
        seg = p // 64
        t = (p % 64) * 4                     # 0..252, in 256ths
        a, b = KEYTINT[seg], KEYTINT[(seg + 1) % 4]
        row = []
        for k in range(6):
            lo, hi = a[k], b[k]
            if hi >= lo:
                row.append(lo + ((hi - lo) * t >> 8))
            else:
                row.append(lo - ((lo - hi) * t >> 8))
        out.append(tuple(row))
    for i, p in enumerate(KEYP):             # the key times are exact
        assert out[p] == KEYTINT[i], (p, out[p], KEYTINT[i])
    return out


TINT = tint_table()
DAYP = KEYP[1]


def chan(c, g, o, d, s):
    """One channel of the contract above.  stardew.asm's Tint is this."""
    v = (c * g) >> 7
    if v > 255:
        v = 255
    v += o
    if v > 255:
        v = 255
    v += d
    if v > 255:
        v = 255
    return v >> s


def pipeline(c8, coef, bias):
    """The RGB565 word the card holds for an art entry at one phase."""
    gr, gg, gb, orr, og, ob = coef
    dr, dg, db = bias & 7, (bias >> 3) & 3, (bias >> 5) & 7
    return ((chan(c8[0], gr, orr, dr, 3) << 11) |
            (chan(c8[1], gg, og, dg, 2) << 5) |
            chan(c8[2], gb, ob, db, 3))


def rgb565(c):
    r, g, b = int(c[0]), int(c[1]), int(c[2])
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def unpack565(v):
    r5, g6, b5 = v >> 11, (v >> 5) & 63, v & 31
    return ((r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2))


def snap565(c):
    return unpack565(rgb565(c))


# ──────────────────────────────────────────────────── the nearest-colour search
class Quant:
    """NART colours in indices 1..NART, and Floyd-Steinberg against them.

    ⚠ The search never considers 0 (the key) and never reaches LIT0, so
    neither can come out of a dither.  That is structural; assert_key_free
    and assert_reserved_free check it anyway.

    ⚠ The cache is keyed on the INTEGER-ROUNDED working colour (mkpcb.py's
    trick): half a million pixels times a 200-way search is the whole runtime
    of this generator, and rounding the QUERY - never the error, which stays
    in floating point and is what the dither is made of - costs at most half
    a unit in a space whose entries are ~20 apart.
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

    def dither(self, img, skip=None, alpha=None):
        """Floyd-Steinberg.  `skip` marks pixels whose colour is decided
        elsewhere (a lit window, a HUD cell): they take no index here and
        diffuse no error, because their colour is not a rendering of
        anything.  `alpha` marks the pixels a KEYED shape actually covers;
        the rest come back 0, which is the copy engine's key."""
        h, w, _ = img.shape
        work = np.clip(np.asarray(img, dtype=np.float64), 0, 255)
        out = np.zeros((h, w), dtype=np.uint8)
        rgb = self.rgb
        for y in range(h):
            row = work[y]
            nxt = work[y + 1] if y + 1 < h else None
            for x in range(w):
                if skip is not None and skip[y, x]:
                    continue
                if alpha is not None and not alpha[y, x]:
                    continue
                old = row[x]
                i = self.nearest(old)
                out[y, x] = i
                err = old - rgb[i - 1]
                if x + 1 < w and (alpha is None or alpha[y, x + 1]):
                    row[x + 1] += err * 0.4375
                if nxt is not None:
                    if x and (alpha is None or alpha[y + 1, x - 1]):
                        nxt[x - 1] += err * 0.1875
                    if alpha is None or alpha[y + 1, x]:
                        nxt[x] += err * 0.3125
                    if x + 1 < w and (alpha is None or alpha[y + 1, x + 1]):
                        nxt[x + 1] += err * 0.0625
        return out


def build_authored(px, bias_of):
    """⭐ NART authored 8-bit colours, and the RGB565 the LUT holds at noon.

    Median cut over the art's own pixels gives the 8-bit triples; the noon
    LUT word is then the TINT PIPELINE'S OWN OUTPUT for each - which is what
    makes "a full cycle comes home" a bit-exact claim whatever the bias is.
    Duplicate noon words are dropped and the palette is topped up with a
    neutral ramp, so the count is always exactly NART.
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
    auth, day, seen = [], [], set()
    cand = [tuple(raw[i * 3:i * 3 + 3]) for i in range(NART)]
    i = 0
    while len(auth) < NART:
        if cand:
            c = cand.pop(0)
        else:                                # top up: a neutral ramp
            c = (i * 7 % 256, i * 11 % 256, i * 5 % 256)
            i += 1
        d = pipeline(c, KEYTINT[1], bias_of(len(auth)))
        if d in seen:
            continue
        seen.add(d)
        auth.append(tuple(int(v) for v in c))
        day.append(d)
    return auth, day


def hash_bias(i):
    """A FIXED per-index rounding offset - dr in 0..7, dg in 0..3, db in
    0..7 - packed into one byte.  Deterministic, so an entry's rounding
    phase never moves and the tint cannot crawl on its own account."""
    h = (i * 2654435761) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return ((h & 7) | (((h >> 4) & 3) << 3) | (((h >> 8) & 7) << 5)) & 0xFF


BIAS_MODE = os.environ.get("STARDEW_BIAS", "hash")


def bias_of(i):
    return 0 if BIAS_MODE == "none" else hash_bias(i)


# ─────────────────────────────────────────────────── the world, continuous tone
def lerp(a, b, t):
    return tuple(a[k] + (b[k] - a[k]) * t for k in range(3))


def hashnoise(x, y, s=0):
    """A deterministic value noise in [0, 1) - no numpy RNG, so the art is the
    same byte for byte on any machine."""
    h = (x * 374761393 + y * 668265263 + s * 2654435761) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65536.0


def vnoise(shape, cell, seed):
    """Smooth value noise on a grid, bilinearly interpolated - the mottle that
    makes grass and water look like something rather than a flat fill."""
    h, w = shape
    gh, gw = h // cell + 2, w // cell + 2
    g = np.array([[hashnoise(i, j, seed) for j in range(gw)] for i in range(gh)])
    yy = np.arange(h) / cell
    xx = np.arange(w) / cell
    y0, x0 = yy.astype(int), xx.astype(int)
    fy, fx = (yy - y0)[:, None], (xx - x0)[None, :]
    fy = fy * fy * (3 - 2 * fy)
    fx = fx * fx * (3 - 2 * fx)
    a = g[np.ix_(y0, x0)]
    b = g[np.ix_(y0, x0 + 1)]
    c = g[np.ix_(y0 + 1, x0)]
    d = g[np.ix_(y0 + 1, x0 + 1)]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def fine(shape, seed, amp):
    h, w = shape
    n = np.array([[hashnoise(x, y, seed) for x in range(w)] for y in range(h)])
    return (n - 0.5) * amp


# ── the farm's layout.  ⭐ AUTHORED HERE and nowhere else; everything
# downstream - the crop plots, the lit set's positions, the actor pen, the
# JSON - is derived from these numbers.
HOUSE = (96, 88, 288, 216)       # x0, y0, x1, y1
BARN = (688, 80, 900, 212)
FIELD = (176, 252, 640, 424)     # the tilled field
POND = (824, 352, 132, 78)       # cx, cy, rx, ry
DOCK = (668, 340, 736, 364)
FOREST_T, FOREST_B, FOREST_L, FOREST_R = 56, 432, 40, 984
PLOTC, PLOTR = 8, 6              # the crop plots, 8 across and 6 down
NSTAGE = 4
CROPIV = 4                       # frames between one plant's retirement


def crop_plots():
    """⭐ DERIVED from FIELD: PLOTC x PLOTR mounds on a regular lattice.  The
    scene, the .pic and checkv3star.py all take them from here."""
    x0, y0, x1, y1 = FIELD
    px = (x1 - x0 - 32) // (PLOTC - 1)
    py = (y1 - y0 - 32) // (PLOTR - 1)
    return [(x0 + 16 + c * px, y0 + 16 + r * py)
            for r in range(PLOTR) for c in range(PLOTC)]


NPLOT = PLOTC * PLOTR


def render_world():
    """The farm, in continuous tone, plus the reserved-index overlay.

    Returns (img [H, W, 3] float, res [H, W] int16 of -1 or a reserved index).
    """
    img = np.zeros((H, W, 3), dtype=np.float64)
    res = np.full((H, W), -1, dtype=np.int16)
    yy, xx = np.mgrid[0:H, 0:W]

    # ── the grass, which is most of the picture and is the reason the dither
    # is here at all: two mottles at different scales plus per-pixel grain
    m1 = vnoise((H, W), 96, 101)
    m2 = vnoise((H, W), 23, 102)
    g = 0.62 * m1 + 0.38 * m2
    base = np.stack([
        62 + 74 * g + 10 * m2,
        128 + 96 * g - 14 * m1,
        54 + 52 * g,
    ], -1)
    img[:] = base + fine((H, W), 103, 13)[..., None]
    # a few mown lighter patches
    for k in range(9):
        cx = int(hashnoise(k, 1, 111) * W)
        cy = int(hashnoise(k, 2, 112) * H)
        rx = 40 + int(hashnoise(k, 3, 113) * 90)
        ry = 26 + int(hashnoise(k, 4, 114) * 50)
        d = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
        t = np.clip(1.0 - d, 0, 1)[..., None] * 0.35
        img = img * (1 - t) + np.array([148, 196, 96]) * t

    def rect(x0, y0, x1, y1):
        return (xx >= x0) & (xx < x1) & (yy >= y0) & (yy < y1)

    def paint(mask, colour):
        img[mask] = np.asarray(colour, dtype=np.float64)

    def shade(mask, colour, t):
        img[mask] = img[mask] * (1 - t) + np.asarray(colour, dtype=np.float64) * t

    # ── the forest edge: a ragged conifer canopy round all four sides
    edge = np.zeros((H, W), dtype=bool)
    jag = (8 * np.sin(xx * 0.11) + 6 * np.sin(xx * 0.037 + 1.3)).astype(int)
    edge |= yy < (FOREST_T + jag)
    edge |= yy > (FOREST_B - jag)
    jagy = (7 * np.sin(yy * 0.13) + 5 * np.sin(yy * 0.041 + 0.7)).astype(int)
    edge |= xx < (FOREST_L + jagy)
    edge |= xx > (FOREST_R - jagy)
    cn = vnoise((H, W), 9, 121)
    canopy = np.stack([18 + 44 * cn, 52 + 96 * cn, 30 + 48 * cn], -1)
    img[edge] = (canopy + fine((H, W), 122, 20)[..., None])[edge]
    # the shadow the canopy throws onto the grass
    for k in range(1, 7):
        sh = np.zeros((H, W), dtype=bool)
        sh |= (yy >= FOREST_T + jag) & (yy < FOREST_T + jag + k)
        sh |= (yy <= FOREST_B - jag) & (yy > FOREST_B - jag - k)
        sh |= (xx >= FOREST_L + jagy) & (xx < FOREST_L + jagy + k)
        sh |= (xx <= FOREST_R - jagy) & (xx > FOREST_R - jagy - k)
        shade(sh & ~edge, (24, 44, 30), 0.30)

    # ── the path: a soft dirt track from the porch, past the field, to the barn
    pathpts = [(200, 220), (232, 268), (300, 300), (420, 296), (560, 268),
               (660, 232), (760, 214), (800, 180)]
    pathm = np.zeros((H, W), dtype=bool)
    for i in range(len(pathpts) - 1):
        (ax, ay), (bx, by) = pathpts[i], pathpts[i + 1]
        n = max(abs(bx - ax), abs(by - ay))
        for s in range(n + 1):
            px = ax + (bx - ax) * s // n
            py = ay + (by - ay) * s // n
            wdt = 13 + int(2.5 * math.sin(s * 0.14 + i))
            pathm |= ((xx - px) ** 2 + (yy - py) ** 2) < wdt * wdt
    pd = vnoise((H, W), 11, 131)
    dirt = np.stack([146 + 46 * pd, 116 + 38 * pd, 82 + 30 * pd], -1)
    img[pathm] = (dirt + fine((H, W), 132, 22)[..., None])[pathm]

    # ── the tilled field: furrows, and a mound where each crop plot is
    fx0, fy0, fx1, fy1 = FIELD
    fm = rect(fx0, fy0, fx1, fy1)
    fr = 0.5 + 0.5 * np.sin((yy - fy0) * math.pi / 14.0)
    soil = np.stack([104 + 46 * fr + 18 * pd, 70 + 34 * fr + 12 * pd,
                     44 + 24 * fr + 8 * pd], -1)
    img[fm] = (soil + fine((H, W), 141, 16)[..., None])[fm]
    shade(rect(fx0, fy0, fx1, fy0 + 3) | rect(fx0, fy1 - 3, fx1, fy1) |
          rect(fx0, fy0, fx0 + 3, fy1) | rect(fx1 - 3, fy0, fx1, fy1),
          (72, 48, 30), 0.6)
    for (px, py) in crop_plots():
        d = ((xx - (px + 8)) / 7.0) ** 2 + ((yy - (py + 9)) / 5.0) ** 2
        t = np.clip(1.0 - d, 0, 1)[..., None] * 0.7
        img = img * (1 - t) + np.array([132, 96, 62]) * t

    # ── the pond, its shore and the dock
    cx, cy, rx, ry = POND
    pdst = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
    shore = (pdst < 1.28) & (pdst >= 1.0)
    water = pdst < 1.0
    sand = np.stack([196 + 34 * pd, 172 + 28 * pd, 122 + 22 * pd], -1)
    img[shore] = (sand + fine((H, W), 151, 14)[..., None])[shore]
    depth = np.clip(1.0 - pdst, 0, 1)
    rip = 0.5 + 0.5 * np.sin(xx * 0.09 + 3.0 * np.sin(yy * 0.05))
    wat = np.stack([26 + 70 * (1 - depth) + 26 * rip,
                    96 + 104 * (1 - depth) + 30 * rip,
                    142 + 88 * (1 - depth) + 22 * rip], -1)
    img[water] = (wat + fine((H, W), 152, 10)[..., None])[water]
    dx0, dy0, dx1, dy1 = DOCK
    for k in range(dy0, dy1):
        pl = ((k - dy0) // 4) % 2
        col = (156, 118, 74) if pl else (134, 98, 60)
        paint(rect(dx0, k, dx1, k + 1), col)
    shade(rect(dx0, dy1, dx1, dy1 + 3), (44, 34, 24), 0.55)

    # ── the house: walls, a shingled roof, a porch, a door and its windows
    hx0, hy0, hx1, hy1 = HOUSE
    roofh = 52
    shade(rect(hx0 + 8, hy1, hx1 + 8, hy1 + 10), (30, 40, 28), 0.5)   # its shadow
    wallg = (yy - (hy0 + roofh)) / float(hy1 - hy0 - roofh)
    wall = np.stack([214 - 54 * wallg, 198 - 52 * wallg, 168 - 46 * wallg], -1)
    body = rect(hx0, hy0 + roofh, hx1, hy1)
    img[body] = (wall + fine((H, W), 161, 12)[..., None])[body]
    for k in range(hy0 + roofh, hy1, 7):                              # clapboard
        shade(rect(hx0, k, hx1, k + 1), (120, 108, 88), 0.45)
    rt = np.clip((yy - hy0) / float(roofh), 0, 1)
    roofc = np.stack([172 - 78 * rt, 74 - 34 * rt, 62 - 28 * rt], -1)
    rm = rect(hx0 - 10, hy0, hx1 + 10, hy0 + roofh)
    img[rm] = (roofc + fine((H, W), 162, 14)[..., None])[rm]
    for k in range(hx0 - 10, hx1 + 10, 11):                           # shingles
        shade(rect(k, hy0, k + 1, hy0 + roofh), (86, 34, 30), 0.5)
    paint(rect(hx0 + 74, hy1 - 46, hx0 + 110, hy1), (96, 62, 40))     # the door
    paint(rect(hx0 + 74, hy1 - 46, hx0 + 110, hy1 - 43), (62, 40, 26))
    porch = rect(hx0 + 46, hy1, hx1 - 46, hy1 + 18)
    img[porch] = np.array([160, 126, 86])
    for k in range(hy1, hy1 + 18, 4):
        shade(rect(hx0 + 46, k, hx1 - 46, k + 1), (108, 82, 54), 0.45)
    # ⭐ the windows are the LIT SET, painted after the dither
    lit_specs = []
    for (wx, wy) in ((hx0 + 20, hy0 + roofh + 18), (hx0 + 132, hy0 + roofh + 18)):
        lit_specs.append(("window", wx, wy, 30, 24))
        paint(rect(wx - 3, wy - 3, wx + 33, wy + 27), (74, 56, 38))
    lit_specs.append(("stove", hx0 + 20, hy1 - 40, 18, 16))
    paint(rect(hx0 + 17, hy1 - 43, hx0 + 41, hy1 - 21), (74, 56, 38))

    # ── the barn
    bx0, by0, bx1, by1 = BARN
    broof = 44
    shade(rect(bx0 + 8, by1, bx1 + 8, by1 + 10), (30, 40, 28), 0.5)
    bg = (yy - (by0 + broof)) / float(by1 - by0 - broof)
    bwall = np.stack([196 - 64 * bg, 58 - 22 * bg, 48 - 18 * bg], -1)
    bb = rect(bx0, by0 + broof, bx1, by1)
    img[bb] = (bwall + fine((H, W), 171, 12)[..., None])[bb]
    for k in range(bx0, bx1, 9):
        shade(rect(k, by0 + broof, k + 1, by1), (120, 32, 30), 0.4)
    brt = np.clip((yy - by0) / float(broof), 0, 1)
    broofc = np.stack([96 - 36 * brt, 92 - 34 * brt, 104 - 38 * brt], -1)
    brm = rect(bx0 - 12, by0, bx1 + 12, by0 + broof)
    img[brm] = (broofc + fine((H, W), 172, 12)[..., None])[brm]
    paint(rect(bx0 + 70, by1 - 58, bx0 + 142, by1), (120, 84, 52))    # the doors
    paint(rect(bx0 + 104, by1 - 58, bx0 + 108, by1), (68, 46, 30))
    for k in range(by1 - 58, by1, 9):
        shade(rect(bx0 + 70, k, bx0 + 142, k + 1), (84, 58, 36), 0.4)
    lit_specs.append(("window", bx0 + 94, by0 + 12, 24, 20))          # the hayloft
    paint(rect(bx0 + 91, by0 + 9, bx0 + 121, by0 + 35), (70, 44, 34))

    # ── a fence round the field
    for k in range(fx0 - 8, fx1 + 8, 24):
        paint(rect(k, fy0 - 14, k + 3, fy0 - 2), (176, 150, 104))
        paint(rect(k, fy1 + 2, k + 3, fy1 + 14), (176, 150, 104))
    paint(rect(fx0 - 8, fy0 - 11, fx1 + 8, fy0 - 9), (168, 142, 98))
    paint(rect(fx0 - 8, fy1 + 5, fx1 + 8, fy1 + 7), (168, 142, 98))

    # ── the lanterns on the path: a post, a head (lit) and a pool of light
    lamps = [(268, 282), (486, 276), (708, 218)]
    for (lx, ly) in lamps:
        paint(rect(lx, ly, lx + 4, ly + 26), (88, 70, 46))
        paint(rect(lx - 5, ly - 12, lx + 9, ly - 10), (70, 58, 40))
        lit_specs.append(("lantern", lx - 4, ly - 10, 12, 10))
        lit_specs.append(("pool", lx - 22, ly + 22, 48, 16))

    # ── fireflies at the forest edge, and the moon on the pond
    for k in range(14):
        fxp = 60 + int(hashnoise(k, 5, 181) * (W - 160))
        fyp = FOREST_T + 6 + int(hashnoise(k, 6, 182) * 26)
        if hashnoise(k, 7, 183) > 0.5:
            fyp = FOREST_B - 30 + int(hashnoise(k, 8, 184) * 22)
        lit_specs.append(("firefly", fxp, fyp, 4, 4))
    lit_specs.append(("moon", cx - 20, cy - 40, 40, 26))

    # ── ⭐ the lit set, painted AFTER everything and BEFORE the dither's skip
    # mask is taken: each spec is a soft ellipse mapped onto its ramp, so a
    # window is a glow and not a flat block.
    ramp0 = {}
    o = LIT0
    for nm, n in LIT_RAMPS:
        ramp0[nm] = (o, n)
        o += n
    for (nm, lx, ly, lw, lh) in lit_specs:
        i0, n = ramp0[nm]
        sx = np.clip((xx - lx) / max(lw - 1, 1), 0, 1)
        sy = np.clip((yy - ly) / max(lh - 1, 1), 0, 1)
        inside = (xx >= lx) & (xx < lx + lw) & (yy >= ly) & (yy < ly + lh)
        d = np.sqrt((sx - 0.5) ** 2 + (sy - 0.5) ** 2) * 2.0
        lvl = np.clip((1.0 - d) * 1.35, 0, 1)
        idx = i0 + np.clip((lvl * n).astype(int), 0, n - 1)
        res[inside] = idx[inside]
    return np.clip(img, 0, 255), res, ramp0, lamps, lit_specs


# ────────────────────────────────────────────────── the keyed art and the hero
def chicken(frame, body, comb, leg):
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.zeros((BLK, BLK), dtype=bool)

    def put(y, x, c):
        if 0 <= y < BLK and 0 <= x < BLK:
            img[y, x] = c
            al[y, x] = True
    bob = 1 if frame else 0
    for y in range(BLK):
        for x in range(BLK):
            if math.hypot((x - 7.0) * 1.05, (y - 8.5 - bob) * 1.3) < 4.6:
                put(y, x, lerp(body, (255, 255, 255), max(0.0, 0.5 - (y - 6) / 12.0)))
    for y in range(BLK):                                   # the head
        for x in range(BLK):
            if math.hypot(x - 10.5, y - 4.5 - bob) < 2.8:
                put(y, x, lerp(body, (255, 255, 255), 0.25))
    for k in range(3):                                     # the comb
        put(2 - bob, 9 + k, comb)
    put(4 - bob, 13, comb)                                 # the beak
    put(5 - bob, 13, comb)
    put(4 - bob, 11, (24, 20, 28))                         # the eye
    for x in (5, 9):                                       # the legs
        put(13 + (frame and x == 5), x, leg)
        put(14, x + (1 if frame else 0), leg)
    for y in range(7, 11):                                 # a wing
        for x in range(4, 9):
            if abs(x - 6) + abs(y - 9) < 4:
                put(y + bob, x, lerp(body, (40, 34, 42), 0.35))
    return img, al


def dog(frame):
    img = np.zeros((DOGH, DOGW, 3), dtype=np.float64)
    al = np.zeros((DOGH, DOGW), dtype=bool)
    body, dark, tan = (198, 150, 88), (116, 78, 40), (238, 214, 168)

    def put(y, x, c):
        if 0 <= y < DOGH and 0 <= x < DOGW:
            img[y, x] = c
            al[y, x] = True
    for y in range(DOGH):
        for x in range(DOGW):
            if math.hypot((x - 10.0) / 6.0, (y - 8.5) / 3.4) < 1.0:
                put(y, x, lerp(body, tan, max(0.0, 0.6 - (y - 5) / 10.0)))
            if math.hypot(x - 18.5, y - 6.0) < 3.6:                  # the head
                put(y, x, lerp(body, tan, 0.3))
    for k in range(4):                                               # the ear
        put(3 + k, 16 - (k // 2), dark)
    put(6, 21, (26, 22, 28))                                         # the eye
    put(7, 22, dark)                                                 # the muzzle
    for x in (5, 8, 13, 16):                                         # the legs
        h = 12 + ((x + frame) % 2)
        for y in range(11, h + 1):
            put(y, x, dark)
    for k in range(5):                                               # the tail
        put(5 - (k if frame else k // 2), 3 - k // 2, tan)
    return img, al


def crop(kind, stage):
    """A crop at one of NSTAGE stages, KEYED: what is not the plant is 0."""
    img = np.zeros((BLK, BLK, 3), dtype=np.float64)
    al = np.zeros((BLK, BLK), dtype=bool)
    stem, leafd, leafl = (52, 128, 54), (36, 104, 44), (128, 216, 104)
    fruit = [(226, 72, 58), (236, 178, 46)][kind]
    h = (4, 7, 10, 13)[stage]

    def put(y, x, c):
        if 0 <= y < BLK and 0 <= x < BLK:
            img[y, x] = c
            al[y, x] = True
    for y in range(BLK - h, BLK - 1):
        put(y, 7, stem)
        put(y, 8, lerp(stem, (20, 62, 28), 0.4))
    for k in range(stage + 1):                                # the leaves
        ly = BLK - 2 - k * max(2, h // (stage + 2))
        sp = 2 + k
        for dx in range(1, sp + 1):
            put(ly, 7 - dx, lerp(leafl, leafd, dx / float(sp + 1)))
            put(ly, 8 + dx, lerp(leafd, leafl, dx / float(sp + 1)))
        put(ly - 1, 7 - sp, leafd)
        put(ly - 1, 8 + sp, leafd)
    if stage >= 2:                                            # the fruit
        for (fy, fx) in ((BLK - h + 1, 6), (BLK - h + 3, 10)):
            for dy in range(2):
                for dx in range(2):
                    put(fy + dy, fx + dx, fruit if (dy or dx) else
                        lerp(fruit, (255, 255, 255), 0.4))
    if stage == NSTAGE - 1:
        put(BLK - h - 1, 7, lerp(fruit, (255, 240, 180), 0.5))
        put(BLK - h - 1, 8, fruit)
    return img, al


# the farmer, 2-bit, for the hardware sprite.  '.' hole, 'o' outline,
# 'b' body, 'a' accent - plan §7's two planes, four bytes a row.
NGAIT = 6
FARMER = [
    """
    .....oooo.......
    ....oaaaao......
    ...oabbbbao.....
    ...oabbbbao.....
    ....obbbbo......
    ....obbbbo......
    ...ooobboooo....
    ..obbbbbbbbbo...
    ..obbbbbbbbbo...
    ..obbbbbbbbo....
    ...obbbbbbo.....
    ....ob..bo......
    ....ob..bo......
    ...oaao.oaao....
    ...oaao.oaao....
    ....oo...oo.....
    """,
    """
    .....oooo.......
    ....oaaaao......
    ...oabbbbao.....
    ...oabbbbao.....
    ....obbbbo......
    ....obbbbo......
    ..ooobbbooooo...
    .obbbbbbbbbbo...
    .obbbbbbbbbbo...
    ..obbbbbbbbo....
    ...obbbbbbo.....
    ...ob....bo.....
    ..ob......bo....
    ..oaao...oaao...
    ...oo.....oo....
    ................
    """,
    """
    .....oooo.......
    ....oaaaao......
    ...oabbbbao.....
    ...oabbbbao.....
    ....obbbbo......
    ....obbbbo......
    ...ooobboooo....
    ..obbbbbbbbbo...
    ..obbbbbbbbbo...
    ..obbbbbbbbo....
    ...obbbbbbo.....
    ....ob..bo......
    ....ob..bo......
    ...oaao.oaao....
    ...oaao.oaao....
    ....oo...oo.....
    """,
    """
    .....oooo.......
    ....oaaaao......
    ...oabbbbao.....
    ...oabbbbao.....
    ....obbbbo......
    ....obbbbo......
    ....ooobbooooo..
    ...obbbbbbbbbo..
    ...obbbbbbbbbo..
    ....obbbbbbbo...
    ...obbbbbbo.....
    ...ob....bo.....
    ..ob......bo....
    ..oaao...oaao...
    ...oo.....oo....
    ................
    """,
    # carrying a watering can
    """
    .....oooo.......
    ....oaaaao......
    ...oabbbbao.....
    ...oabbbbao.....
    ....obbbbo......
    ....obbbbo......
    ...ooobboooo....
    ..obbbbbbbbbo...
    ..obbbbbbbbboaa.
    ..obbbbbbbbooaa.
    ...obbbbbbo.....
    ....ob..bo......
    ....ob..bo......
    ...oaao.oaao....
    ...oaao.oaao....
    ....oo...oo.....
    """,
    # idle
    """
    .....oooo.......
    ....oaaaao......
    ...oabbbbao.....
    ...oabbbbao.....
    ....obbbbo......
    ....obbbbo......
    ...ooobboooo....
    ..obbbbbbbbbo...
    ..obbbbbbbbbo...
    ..obbbbbbbbbo...
    ...obbbbbbo.....
    ....ob..bo......
    ....ob..bo......
    ....oaaoaao.....
    ....oaaoaao.....
    .....oo.oo......
    """,
]
# ⚠ the sprite's three LUT banks are NOT the art palette and are NOT tinted:
# a sprite pixel's LUT address is (code << 8) | the pixel under it, so all
# 256 entries of a bank carry one colour (plan §7).
FARMER_LUT = [(0x20, 0x18, 0x28), (0x48, 0x8C, 0xD8), (0xF0, 0xC8, 0x70)]


def hero_shape(txt):
    rows = [r.strip() for r in txt.strip("\n").split("\n")]
    rows = [r for r in rows if r]
    assert len(rows) == 16, len(rows)
    code = np.zeros((16, 16), dtype=np.uint8)
    for y, r in enumerate(rows):
        assert len(r) == 16, (y, r, len(r))
        for x, ch in enumerate(r):
            code[y, x] = {".": 0, "o": 1, "b": 2, "a": 3}[ch]
    out = []
    for y in range(16):
        for pl in (0, 1):
            bits = [(code[y, x] >> pl) & 1 for x in range(16)]
            out.append(sum(1 << (7 - i) for i in range(8) if bits[i]))
            out.append(sum(1 << (7 - i) for i in range(8) if bits[8 + i]))
    return out


# ───────────────────────────────────────────────────────────── the HUD strip
def hud_strip():
    """160 x 16 of HUD, in reserved indices only.  ⭐ Its 16-cell day bar is
    what the marker walks along, so the clock is visible in a contact sheet
    and in the recording without reading a single digit."""
    a = np.zeros((HUDH, HUDW), dtype=np.uint8)
    F, B, R = HUD0 + 0, HUD0 + 5, HUD0 + 2       # frame, bright, rule
    a[:, :] = HUD0 + 1
    a[0, :] = a[-1, :] = F
    a[:, 0] = a[:, -1] = F
    a[1, 1:-1] = HUD0 + 3
    # the day bar: sixteen cells, dawn -> night in the HUD's own ramp
    for c in range(16):
        x0 = 6 + c * 8
        shade = (HUD0 + 10, HUD0 + 13, HUD0 + 12, HUD0 + 8)[c // 4]
        a[4:11, x0:x0 + 7] = shade
        a[3, x0:x0 + 7] = R
        a[11, x0:x0 + 7] = R
    # the energy bar, under it
    for c in range(16):
        x0 = 6 + c * 8
        a[12:15, x0:x0 + 7] = HUD0 + 15 if c < 11 else HUD0 + 23
    a[2, 2:HUDW - 2] = B
    return a


def hud_marker():
    """The day bar's marker, a 16 x 16 KEYED slot: only the arrow is drawn."""
    a = np.zeros((BLK, BLK), dtype=np.uint8)
    for y in range(6):
        for x in range(-y, y + 1):
            a[y + 1, 7 + x] = HUD0 + 6 if y < 4 else HUD0 + 4
    a[7, 5:11] = HUD0 + 24
    return a


# ─────────────────────────────────────────────────── ⚠ the tint-vs-dither test
def tint_test():
    """⚠ stardew.md §6 item 2, measured on ONE region before the whole farm
    is committed: DOES THE DITHER SURVIVE THE TINT?

    The region is rendered in continuous tone, quantised to the art palette
    and Floyd-Steinberg dithered; then, at N phases of the day, the DISPLAYED
    picture is rebuilt from the LUT the driver would hold and compared with
    the IDEAL - the same continuous-tone region with the same affine tint
    applied in floating point.  Both are box-averaged 4 x 4 first, because
    that is what an eye does with a dither and it is the scale at which
    banding is visible; the per-pixel difference of a dithered picture is
    meaningless.

      band   the low-frequency error, RMS over the 4 x 4 means.  This is
             banding: a gradient that has collapsed onto fewer levels sits
             away from the ideal in big smooth patches
      worst  the largest single 4 x 4 block error
      lvl    distinct displayed colours in the region - the texture that is
             left
      crawl  the largest fraction of the region that changed between two
             ADJACENT phases.  A tint that moves every entry a little is
             smooth; one that moves a whole ramp at one phase pops
    """
    print("⚠ the dither against the tint - stardew.md §6 item 2\n")
    # a region with the two gradients that are hardest: the pond's depth ramp
    # and the grass mottle beside it
    img, res, _, _, _ = render_world()
    y0, x0, rh, rw = 300, 700, 128, 256
    reg = img[y0:y0 + rh, x0:x0 + rw]
    lit = res[y0:y0 + rh, x0:x0 + rw] >= 0
    print("      region %d x %d at (%d, %d); %d of its pixels are lit-set"
          % (rw, rh, x0, y0, int(lit.sum())))
    # ⚠ THE PALETTE IS THE WHOLE FARM'S, not the region's.  A palette cut from
    # the region alone would give it 200 colours to itself and answer a
    # question nobody asked; here it gets the share it will really have.
    world = img[~(res >= 0)].reshape(-1, 3).astype(np.uint8)

    # ⚠ the metrics are taken on 4 x 4 BLOCKS THAT HOLD NO LIT PIXEL: a lit
    # index is not a rendering of the continuous tone and comparing it with
    # one measures nothing.
    bh, bw = rh // 4, rw // 4

    def box(a):
        return a[:bh * 4, :bw * 4].reshape(bh, 4, bw, 4, -1).mean((1, 3))

    ok = box(lit[..., None].astype(float))[..., 0] == 0.0

    rows = []
    for mode in ("none", "hash", "ramp"):
        if mode == "none":
            bof = (lambda i: 0)
        elif mode == "hash":
            bof = hash_bias
        else:
            bof = None                      # filled in below, it needs auth
        auth, day = build_authored(world, bof if bof else hash_bias)
        if mode == "ramp":
            # ⭐ the ORDER-AWARE bias: sort the palette by luminance and give
            # consecutive entries opposite rounding phases, which is the
            # strongest possible defence of a ramp's spacing.
            order = sorted(range(NART), key=lambda i: sum(auth[i]))
            tab = [0] * NART
            for r, i in enumerate(order):
                tab[i] = (r % 8) | ((r % 4) << 3) | (((r + 4) % 8) << 5)
            bof = lambda i, t=tab: t[i]                          # noqa: E731
            auth, day = build_authored(world, bof)
        q = Quant([unpack565(d) for d in day])
        idx = q.dither(reg, skip=lit)
        used = np.unique(idx[~lit]) - 1
        band, lvls, crawl, pop = [], [], [], []
        worst = 0.0
        prev, prevbox = None, None
        for p in range(NPHASE):
            coef = TINT[p]
            words = np.array([pipeline(auth[i], coef, bof(i)) for i in range(NART)])
            if prev is not None:
                crawl.append(float((words[used] != prev[used]).mean()))
            prev = words
            lut = np.array([unpack565(int(w)) for w in words], dtype=np.float64)
            shown = lut[np.clip(idx, 1, NART) - 1]
            # ⭐ THE CRAWL METRIC THAT MATTERS.  A dither pair whose members
            # requantise TOGETHER makes a 4 x 4 mean jump a whole LSB at one
            # phase - which is a visible pop.  One whose members move apart
            # makes it step fractionally, which is what a gradient wants.
            bx = box(shown)[ok]
            if prevbox is not None:
                d = np.abs(bx - prevbox).max(-1)
                pop.append((float(d.max()), float(d.mean())))
            prevbox = bx
            if p % 8:
                continue
            gr, gg, gb, orr, og, ob = coef
            ideal = np.stack([
                np.clip(np.minimum(reg[..., 0] * gr / 128.0, 255) + orr, 0, 255),
                np.clip(np.minimum(reg[..., 1] * gg / 128.0, 255) + og, 0, 255),
                np.clip(np.minimum(reg[..., 2] * gb / 128.0, 255) + ob, 0, 255)], -1)
            e = (box(shown) - box(ideal))[ok]
            band.append((p, float(np.sqrt((e * e).sum(-1).mean())),
                         float(np.sqrt((e * e).sum(-1)).max()),
                         len(set(words[used].tolist()))))
            worst = max(worst, band[-1][2])
        rows.append((mode, band, worst, crawl, pop))

    print("\n      %-6s %-6s %8s %8s %8s %8s" %
          ("bias", "phase", "band", "worst", "levels", "of day"))
    for mode, band, worst, crawl, pop in rows:
        d = dict((p, b) for p, b, w, l in band)
        lv = dict((p, l) for p, b, w, l in band)
        for p, nm in zip(KEYP, KEYNM):
            print("      %-6s %-6s %8.2f %8.2f %8d %8d"
                  % (mode, nm, d[p], [w for q, b, w, l in band if q == p][0],
                     lv[p], lv[DAYP]))
        print("      %-6s %-6s %8.2f %8.2f" %
              (mode, "mean", sum(b for _, b, _, _ in band) / len(band), worst))
        print("      %-6s ⭐ one phase step moves %.1f%% of the region's entries "
              "at worst (%.1f%% mean);" % (mode, 100 * max(crawl),
                                           100 * sum(crawl) / len(crawl)))
        print("      %-6s    and a 4 x 4 block's own colour by at most %.1f of "
              "255 (%.2f mean) - the POP" %
              (mode, max(a for a, _ in pop), sum(b for _, b in pop) / len(pop)))
    print("\n      band/worst are 8-bit RGB distance on 4 x 4 block means, over "
          "blocks\n      with no lit pixel in them; `levels` is how many distinct "
          "LUT words the\n      region's own indices still have at that phase, "
          "against what it has at noon.")
    return 0


# ───────────────────────────────────────────────────────────────── assembly
def emit_bytes(label, data, per=16, comment=""):
    out = []
    if comment:
        out.append("* " + comment)
    first = True
    for i in range(0, len(data), per):
        chunk = ",".join("$%02X" % (b & 255) for b in data[i:i + per])
        out.append("%-19s fcb       %s" % (label if first else "", chunk))
        first = False
    return "\n".join(out)


def emit_words(label, data, per=8, comment=""):
    out = []
    if comment:
        out.append("* " + comment)
    first = True
    for i in range(0, len(data), per):
        chunk = ",".join("$%04X" % (w & 0xFFFF) for w in data[i:i + per])
        out.append("%-19s fdb       %s" % (label if first else "", chunk))
        first = False
    return "\n".join(out)


def b64(a):
    return base64.b64encode(bytes(bytearray(a))).decode()


# ───────────────────────────────────────────────────────── the actor cast
# ⭐ AUTHORED: each actor's home, the radius it wanders over and its rate.
# The scene walks them with the sine table, so its arithmetic is integer and
# checkv3star.py never has to replay it - the VRAM gate is about where they
# ENDED, and the Wipe is what makes that decidable.
CAST = [
    #  kind  slot  home x, y   ax, ay   sp  ph
    ("chick", 0, 700, 268, 54, 26, 3, 0),
    ("chick", 2, 760, 300, 46, 30, 4, 40),
    ("chick", 4, 640, 306, 60, 22, 2, 96),
    ("chick", 0, 720, 240, 38, 34, 5, 150),
    ("chick", 2, 660, 250, 50, 28, 3, 200),
    ("chick", 4, 780, 266, 42, 24, 4, 230),
    ("dog",   0, 380, 216, 120, 40, 2, 64),
]
NCAST = len(CAST)


def main():
    if "--tint-test" in sys.argv:
        return tint_test()
    out = None
    for a in sys.argv[1:]:
        if not a.startswith("-"):
            out = a
    here = os.path.dirname(os.path.abspath(__file__))

    print("      rendering the farm, %d x %d ..." % (W, H))
    img, res, ramp0, lamps, lit_specs = render_world()

    # ── the keyed art, in continuous tone, so the palette sees it too
    chicks = [chicken(f, c, (226, 64, 58), (232, 176, 60))
              for c in ((246, 244, 236), (198, 152, 96), (74, 70, 84))
              for f in (0, 1)]
    dogs = [dog(f) for f in range(NDOG)]
    crops = [crop(k, s) for k in range(2) for s in range(NSTAGE)]

    samples = [img[~(res >= 0)].reshape(-1, 1, 3)]
    for (a, al) in chicks + dogs + crops:
        if al.any():
            samples.append(a[al].reshape(-1, 1, 3))
    print("      median cut over %d pixels ..."
          % sum(s.shape[0] for s in samples))
    auth, day = build_authored(np.concatenate([s.reshape(-1, 3) for s in samples]),
                               bias_of)
    q = Quant([unpack565(d) for d in day])

    print("      Floyd-Steinberg over %d pixels (a minute or so) ..." % (W * H))
    pic = q.dither(img, skip=(res >= 0))
    pic[res >= 0] = res[res >= 0].astype(np.uint8)

    # ── the keyed art bank, one 16-row band of the ring
    art = np.zeros((BLK, 1024), dtype=np.uint8)
    slots = {}
    for i, (a, al) in enumerate(chicks):
        art[:, C_SPR + i * BLK:C_SPR + (i + 1) * BLK] = q.dither(a, alpha=al)
    slots["chick"] = 0
    for i, (a, al) in enumerate(crops):
        s = len(chicks) + i
        art[:, C_SPR + s * BLK:C_SPR + (s + 1) * BLK] = q.dither(a, alpha=al)
    slots["crop"] = len(chicks)
    mk = hud_marker()
    SLOT_MARK = len(chicks) + len(crops)
    assert SLOT_MARK < NSPR, SLOT_MARK
    art[:, C_SPR + SLOT_MARK * BLK:C_SPR + (SLOT_MARK + 1) * BLK] = mk
    for i, (a, al) in enumerate(dogs):
        art[:, C_DOG + i * DOGW:C_DOG + (i + 1) * DOGW] = q.dither(a, alpha=al)
    art[:, C_HUD:C_HUD + HUDW] = hud_strip()

    hero = []
    for f in FARMER:
        hero += hero_shape(f)
    assert len(hero) == NGAIT * 64

    # ── ⛔ index 0 is the key, and the reserved sets are not the dither's
    def assert_key_free(what, a):
        bad = int((np.asarray(a) == 0).sum())
        assert bad == 0, "%s: %d pixels are index 0, the colour key" % (what, bad)

    assert_key_free("the world", pic)
    nres = int(((pic >= LIT0)).sum())
    assert nres > 0, "the lit set never reaches the picture"
    lo = np.unique(pic)
    assert lo.min() >= 1 and lo.max() <= 255
    # every art pixel is 1..NART and every reserved pixel is one of the lit set
    assert int(((pic > NART) & (pic < LIT0)).sum()) == 0
    assert int((pic >= HUD0).sum()) == 0, "the HUD set is not in the world"
    for nm, (i0, n) in ramp0.items():
        assert int(((pic >= i0) & (pic < i0 + n)).sum()) > 0, \
            "the %s ramp was allocated and never painted" % nm
    for i in range(NSPR):
        s = art[:, C_SPR + i * BLK:C_SPR + (i + 1) * BLK]
        if i <= SLOT_MARK:
            assert (s != 0).any(), "art slot %d is entirely key" % i
    holes = int((art[:, :C_HUD] == 0).sum())
    assert holes > 0, "no keyed shape has a hole - the key is untested"
    assert int((art[:, C_HUD:C_HUD + HUDW] < HUD0).sum()) == 0, \
        "the HUD strip must be HUD indices alone"
    assert int(((art[:, :C_HUD] > NART) & (art[:, :C_HUD] < HUD0) &
                (art[:, :C_HUD] != 0)).sum()) == 0, \
        "a keyed shape reached the lit set"

    # ⛔ THE RESERVED SETS MUST NOT COLLIDE WITH AN ART COLOUR - AT ANY PHASE
    # OF THE DAY, which is a harder thing to ask than pinball asked.  There
    # the art never moved, so "no art colour equals a lamp" was a comparison
    # against 205 words; here the 200 art entries sweep 6,633 of the 65,536
    # words as the day turns, and a reserved colour that any of them passes
    # through is one the recording cannot tell from the art for a few frames.
    # ⭐ 90 % of RGB565 is still free, so each reserved colour is NUDGED to
    # the nearest word no art entry ever takes.  (pinball's LAMP_OFF[7]
    # lesson: two triples that differ in eight bits and are the same RGB565
    # cost a run - and a tint makes that a moving target.)
    allw = set()
    for p in range(NPHASE):
        allw |= set(pipeline(auth[i], TINT[p], bias_of(i)) for i in range(NART))

    taken = set(allw)

    def place(c):
        want = rgb565(c)
        r0, g0, b0 = want >> 11, (want >> 5) & 63, want & 31
        best, bd = None, None
        for dr in range(-3, 4):
            for dg in range(-6, 7):
                for db in range(-3, 4):
                    r, g, b = r0 + dr, g0 + dg, b0 + db
                    if not (0 <= r < 32 and 0 <= g < 64 and 0 <= b < 32):
                        continue
                    v = (r << 11) | (g << 5) | b
                    if v in taken:
                        continue
                    d = (dr * 8) ** 2 + (dg * 4) ** 2 + (db * 8) ** 2
                    if bd is None or d < bd:
                        best, bd = v, d
        assert best is not None, ("no free RGB565 near", c)
        taken.add(best)
        return best

    litcols = []
    for nm, n in LIT_RAMPS:
        a, b = LIT_COLOURS[nm]
        for k in range(n):
            litcols.append(place(lerp(a, b, k / float(n - 1))))
    hudcols = [place(c) for c in HUD_COLOURS]
    fixed = litcols + hudcols
    assert len(set(fixed)) == len(fixed), "two reserved entries are one colour"
    clash = [(k + LIT0, v) for k, v in enumerate(fixed) if v in allw]
    assert not clash, ("a reserved colour is an art colour at some phase", clash)


    # ⭐ and the FULL LUT at noon is the authored palette, by construction
    day0 = [pipeline(auth[i], TINT[DAYP], bias_of(i)) for i in range(NART)]
    assert day0 == day
    lut0 = [0xF81F] + day0 + litcols + hudcols       # entry 0: bright magenta
    assert len(lut0) == 256

    # ── the tint table and the palette, as the module carries them
    palb = []
    for c in auth:
        palb += [c[0], c[1], c[2]]
    biasb = [bias_of(i) for i in range(NART)]
    tintb = []
    for row in TINT:
        tintb += list(row)
    fixedw = []
    for v in litcols + hudcols:
        fixedw += [v >> 8, v & 255]

    # ⭐ THE CROP'S KIND RIDES IN BIT 15 OF ITS X, which is free because the
    # world is 1024 wide.  So the kind is DATA - one table, read the same way
    # by stardew.asm and by checkv3star.py - and not a rule each of them
    # carries its own copy of.
    plots = crop_plots()
    plotkind = [p & 1 for p in range(NPLOT)]
    plotb = []
    for k, (px, py) in enumerate(plots):
        v = px | (plotkind[k] << 15)
        plotb += [v >> 8, v & 255, py >> 8, py & 255]
    castb = []
    for (kind, slot, hx, hy, ax, ay, sp, ph) in CAST:
        castb += [0 if kind == "chick" else 1, slot,
                  hx >> 8, hx & 255, hy >> 8, hy & 255, ax, ay, sp, ph]
    CASTREC = 10
    assert len(castb) == NCAST * CASTREC

    sin = [int(round(127 * math.sin(2 * math.pi * i / 256))) & 255 for i in range(256)]

    DAT = [
        "* ⭐ THE PALETTE'S SPLIT IS THE SPECIFICATION (stardew.md §2).",
        "SWNART              equ       %d       art entries, 1..%d - the ONLY ones tinted" % (NART, NART),
        "SWLIT0              equ       %d       the lit set: the tint never touches it" % LIT0,
        "SWNLIT              equ       %d" % NLIT,
        "SWHUD0              equ       %d       the HUD: constant, because it has to be read" % HUD0,
        "SWNHUD              equ       %d" % NHUD,
        "SWNPH               equ       %d      phases in a whole day" % NPHASE,
        "SWDAYP              equ       %d       the phase at which the tint is unity" % DAYP,
        "SWMAXPW             equ       %d         LUT entries PREPARED and committed a frame" % MAXPW,
        "* the world, and the view over it",
        "SWW                 equ       %d" % W,
        "SWH                 equ       %d" % H,
        "SWVW                equ       %d" % VIEWW,
        "SWVH                equ       %d" % VIEWH,
        "SWHSMX              equ       %d       HSCROLL never passes this: no ring wrap" % HSMAX,
        "SWVSMX              equ       %d" % VSMAX,
        "* the ring beyond the world: the keyed art and the save-behind scratch",
        "SWRART              equ       %d       the art bank's ring row" % R_ART,
        "SWRSCR              equ       %d       the save-behind scratch" % R_SCR,
        "SWCSPR              equ       %d         %d slots of 16 x 16" % (C_SPR, NSPR),
        "SWNSPR              equ       %d" % NSPR,
        "SWCDOG              equ       %d       the dog, %d x %d, %d frames" % (C_DOG, DOGW, DOGH, NDOG),
        "SWDOGW              equ       %d" % DOGW,
        "SWDOGH              equ       %d" % DOGH,
        "SWNDOG              equ       %d" % NDOG,
        "SWCHUD              equ       %d       the HUD strip, %d x %d" % (C_HUD, HUDW, HUDH),
        "SWHUDW              equ       %d" % HUDW,
        "SWHUDH              equ       %d" % HUDH,
        "SWCHSC              equ       %d       ... and its own scratch column" % C_HSCR,
        "SWSCRP              equ       %d        an actor's scratch slot pitch" % SCRPITCH,
        "SWMXAC              equ       %d        scratch slots, so actors" % MAXACT,
        "SWSLMK              equ       %d        the day bar's marker, an art slot" % SLOT_MARK,
        "SWSLCR              equ       %d        the first crop slot: kind*%d + stage" % (slots["crop"], NSTAGE),
        "SWNSTG              equ       %d         crop stages" % NSTAGE,
        "SWNPLT              equ       %d        crop plots" % NPLOT,
        "SWCRIV              equ       %d         frames between one plant's retirement" % CROPIV,
        "SWNCST              equ       %d         the cast" % NCAST,
        "SWCREC              equ       %d        bytes a cast record" % CASTREC,
        "SWNGT               equ       %d         the farmer's sprite shapes" % NGAIT,
        "* the cast record",
        "C.Kind              equ       0",
        "C.Slot              equ       1",
        "C.HX                equ       2",
        "C.HY                equ       4",
        "C.AX                equ       6",
        "C.AY                equ       7",
        "C.SP                equ       8",
        "C.PH                equ       9",
        emit_bytes("PalDat", palb, 15,
                   "⭐ THE AUTHORED COLOUR, 8-bit RGB, %d x 3.  This is the SOURCE" % NART),
        "*      OF TRUTH: every commit multiplies THIS, never the entry the",
        "*      card is holding, or the world converges on black (§2).",
        emit_bytes("BiasDat", biasb, 16,
                   "the per-entry rounding bias: b0-2 red, b3-4 green, b5-7 blue"),
        emit_bytes("TintDat", tintb, 12,
                   "⭐ %d phases x (gr, gg, gb, or, og, ob).  128 is unity EXACTLY," % NPHASE),
        "*      which is what lets one whole day come home to the authored value.",
        emit_bytes("FixDat", fixedw, 16,
                   "the lit set and the HUD set, RGB565 hi lo - %d + %d entries," % (NLIT, NHUD)),
        "*      uploaded once and never touched again",
        emit_bytes("ArtDat", art.reshape(-1).tolist(), 16,
                   "the keyed art bank: 16 rows of 1024.  Index 0 is the hole"),
        emit_bytes("HeroArt", hero, 16,
                   "the farmer: %d shapes of 64 bytes (plan §7's two planes)" % NGAIT),
        emit_bytes("PlotTab", plotb, 16,
                   "the %d crop plots, x then y, big-endian; ⭐ bit 15 of x is the KIND" % NPLOT),
        emit_bytes("CastTab", castb, 10, "the cast: %d records of %d" % (NCAST, CASTREC)),
        emit_bytes("SinTab", sin, 16, "256 entries, signed -127..127"),
        "* the hardware sprite's three LUT banks: outline, body, accent.",
        "* ⚠ NOT tinted - a sprite bank is 256 entries of one colour (plan §7).",
        "HeroLut             fdb       " + ",".join("$%04X" % rgb565(c) for c in FARMER_LUT),
    ]

    bar = "*" * 68
    top = bar + "\n* %s - generated by video3/bench/mkstardew.py; do not edit by hand\n" + bar + "\n"
    if out:
        os.makedirs(out, exist_ok=True)
        p = os.path.join(out, "stardewdat.asm")
        open(p, "w").write(top % "stardewdat.asm" + "\n".join(DAT) + "\n")
        print("ok    %s (%d bytes of source)" % (p, os.path.getsize(p)))

    # ── the world, as the card reads it off the SD card
    pp = os.path.join(here, "stardew.pic")
    pic.tofile(pp)
    assert os.path.getsize(pp) == W * H
    assert (W * H) % 512 == 0
    print("ok    %s (%d bytes, %d SD blocks)" % (pp, W * H, W * H // 512))

    # ── the JSON: the DATA, not the code
    j = dict(
        w=W, h=H, vieww=VIEWW, viewh=VIEWH, hsmax=HSMAX, vsmax=VSMAX,
        blk=BLK, r_art=R_ART, r_scr=R_SCR, c_spr=C_SPR, nspr=NSPR,
        c_dog=C_DOG, dogw=DOGW, dogh=DOGH, ndog=NDOG,
        c_hud=C_HUD, hudw=HUDW, hudh=HUDH, c_hscr=C_HSCR,
        scrpitch=SCRPITCH, maxact=MAXACT,
        nart=NART, lit0=LIT0, nlit=NLIT, hud0=HUD0, nhud=NHUD,
        nphase=NPHASE, dayp=DAYP, keyp=KEYP, keynm=KEYNM, keytint=KEYTINT,
        maxpw=MAXPW, bias_mode=BIAS_MODE,
        auth=[list(c) for c in auth], bias=biasb, tint=[list(r) for r in TINT],
        lut0=lut0, litcols=litcols, hudcols=hudcols,
        slot_mark=SLOT_MARK, slot_crop=slots["crop"], nstage=NSTAGE,
        nplot=NPLOT, cropiv=CROPIV, plots=[list(p) for p in plots],
        plotkind=plotkind,
        cast=[list(c) for c in CAST], ncast=NCAST, castrec=CASTREC,
        ngait=NGAIT, herolut=[rgb565(c) for c in FARMER_LUT],
        art=b64(art.reshape(-1).tolist()),
        pic="stardew.pic", picsha=hashlib.sha256(pic.tobytes()).hexdigest(),
    )
    jp = os.path.join(here, "stardew.json")
    open(jp, "w").write(json.dumps(j))
    print("ok    %s (%d bytes)" % (jp, os.path.getsize(jp)))

    # ── the preview: the farm at noon, and the same strip at the other three
    from PIL import Image
    lut = np.array([unpack565(v) for v in lut0], dtype=np.uint8)
    lut[0] = (0xF8, 0x00, 0xF8)
    strips = []
    for p in KEYP:
        coef = TINT[p]
        l2 = np.array([unpack565(pipeline(auth[i], coef, bias_of(i)))
                       for i in range(NART)], dtype=np.uint8)
        full = np.concatenate([lut[:1], l2, lut[LIT0:]])
        strips.append(full)
    sheet = Image.new("RGB", (W, H + 3 * 160 + 16 * 4), (10, 12, 14))
    sheet.paste(Image.fromarray(strips[1][pic]), (0, 0))
    for k, p in enumerate((0, 2, 3)):
        band = strips[p][pic[180:340]]
        sheet.paste(Image.fromarray(band), (0, H + 16 + k * (160 + 16)))
    ap = os.path.join(here, "stardew-art.png")
    sheet.save(ap)
    print("ok    %s  (noon, then dawn / dusk / night over rows 180..339)" % ap)
    print("      %d art colours, %d lit, %d HUD; %d of %d pixels are lit-set"
          % (NART, NLIT, NHUD, int((pic >= LIT0).sum()), W * H))
    print("      module data: %d B palette + %d B tint + %d B art + %d B hero"
          % (len(palb) + len(biasb) + len(fixedw), len(tintb), art.size, len(hero)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
