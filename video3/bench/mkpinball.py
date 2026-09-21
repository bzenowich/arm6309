#!/usr/bin/env python3
"""mkpinball.py [CMDSDIR] - the `pinball` scene's ACTORS and its collision data.

    python3 video3/bench/mkpinball.py ../nitros9/level2/arm6309/cmds

⭐ THE TABLE IS NO LONGER BUILT HERE.  `mkpcb.py` draws it as a picture -
pcbtable.pic, 327,680 bytes, 640 x 512, exactly 640 SD blocks - and the scene
READS THAT FILE OFF THE CARD straight into VRAM rows 0..511, columns 0..639.
Nothing is interned, nothing is composed out of blocks, and this file no
longer emits a single byte of playfield.

What it does emit is everything the picture is NOT:

    pinballdat.asm   (beside pinball.asm)
                     ⭐ THE COLLISION GRID, lifted verbatim out of
                     pcbtable.json - the 40 x 32 `colmap` and the `idmap`
                     that says WHICH bumper, target, rollover, kicker or
                     return lane a cell belongs to - plus every concrete
                     position the physics needs (the plunger seat, the kick
                     vectors, the flipper pivots and zones, which lamp
                     belongs to which object), the keyed ball and flipper
                     art, the hardware sprite's shapes, and the loading
                     screen's banner.

    pinball.json     ⭐ THE SAME DATA, for video3/bench/checkv3pin.py, which
                     rebuilds every byte the card should hold and compares it
                     against a VRAM dump.  The ROM and the model share the
                     DATA and no code - bench/README.md's rule.

    pinball-art.png  the table with its actors beside it, for reviewing the
                     art without running the machine.

═══ ART AND COLLISION ARE SEPARATE, AND THAT IS THE DESIGN ═════════════════

`mkpinball.py` used to derive both from one grid, because it drew both.  It
does not draw the table any more, so the rule is the other way round: ⛔ THE
COLLISION MAP IS NEVER RE-DERIVED FROM PIXELS.  mkpcb.py authors the object
rectangles and derives `colmap`/`idmap` from them; `checkpcb.py` is what
asserts the picture and the grid agree (299 claims, 11 mutations).  This file
copies the grid across and adds nothing to it.

⛔ INDEX 0 IS THE COPY ENGINE'S COLOUR KEY (keyed-copy.md).  pcbtable.pic
contains no 0 by construction and checkpcb.py says so; the ball and flipper
art drawn HERE are keyed, so their holes are 0 and their ink is quantised
against the picture's OWN palette, entries 1..205.  A reserved entry
(206..255, the lamps and the six digits) is never returned by the dither -
the search cannot reach it - because checkv3pin.py's lamp gate reads the
lamps off the recording by looking for their exact RGB565 in the picture.

⚠ THE PALETTE IS NOT EMITTED EITHER.  pcbtable.pal is the LUT as the card
stores it and the scene loads it off the card beside the picture; what is
emitted here is only the lamps' LIT colours and the segment pair, which are
the values the scene WRITES.
"""
import base64
import hashlib
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mkpcb import FONT                                          # noqa: E402

# ───────────────────────────────────────────────────── the spare region
# The 384 columns of the 1024-wide ring the 640-wide view never shows.  ⭐ The
# block bank is gone with the blocks, so all 512 rows of it are free and the
# flipper frames get a two-band layout instead of one 384-column strip.
C_BANK = 640
R_FLIP = 0                       # 8 COMPOSED flipper frames: 2 bands of 4
R_FART = 128                     # the KEYED flipper art they are composed from
R_BALL = 256                     # the keyed ball art, 4 frames
R_SAVE = 272                     # the save-behind scratch, one slot a blit ball
R_SPR, C_SPR = 511, 960          # MAPBASE 7's top 64 bytes (armvid.d)

BALLW, BALLH, NBALLF = 20, 16, 4
MAXBLIT = 14                     # blit balls (ball 0 is the hardware sprite)
NGAIT = 4                        # the hardware sprite's shapes
NFLIPF = 4                       # rest, two intermediates, up

# ⭐ THE FLIPPER RECTANGLE IS DERIVED FROM THE PIVOT, exactly as pcbtable.json
# derives its collision zone: 56 x 64 at (240, 324) and (312, 324) covers a
# 48-pixel flipper swinging +/- 32 degrees about (248, 356) and (360, 356),
# and the two rectangles do not touch.  ⚠ ASSERTED against the JSON below.
FLIPW, FLIPH = 56, 64
FLIP_LX, FLIP_RX, FLIP_Y = 240, 312, 324

# how the picture is read: whole rows, a chunk at a time
PICCHUNK = 8                     # VRAM rows in one I$Read
# ⛔ THE TRUNCATION MUTATION stops here, which must leave the last band of the
# table holding the loading screen and fail the VRAM gate.
TRUNCR = 448

BANNER = "LOADING PLAYFIELD"
BANSCALE = 2

# the loading screen, as three palette indices picked out of the art's own
LS_BG = (10, 12, 16)
LS_FRM = (222, 226, 214)
LS_BAR = (214, 174, 90)

# the hardware sprite's three LUT banks: outline, body, highlight
SPR_LUT = [(0x18, 0x1A, 0x28), (0xC8, 0xD4, 0xE8), (0xFF, 0xFF, 0xFF)]

# ⭐ WHICH LAMP FLASHES ON ITS OWN.  checkv3pin.py's control reads this: a
# lamp that is lit in every frame would satisfy "every reserved entry reached
# the picture" without a single write after the first.
FLASH = 7

# the physics, in the 12.4 fixed point the scene uses
VMAX = 240                       # 15 px a frame, either axis
GRAV = 4
PLUNGV = -240


def rgb565(c):
    r, g, b = int(c[0]), int(c[1]), int(c[2])
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def unpack565(v):
    r5, g6, b5 = v >> 11, (v >> 5) & 63, v & 31
    return ((r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2))


def lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


# ───────────────────────────────────────────── the picture's own palette
class Quant:
    """Nearest colour among the PICTURE's art entries, 1..NART, with
    Floyd-Steinberg error diffusion inside the keyed shape.

    ⛔ THE SEARCH CANNOT REACH A RESERVED ENTRY.  `rgb` holds 1..NART and
    nothing else, so a lamp or a segment index is not a possible answer -
    which is what lets the lamp gate treat a reserved colour in a recorded
    frame as proof that the LUT was written."""

    W = np.array([0.30, 0.59, 0.11])

    def __init__(self, pal, nart):
        self.rgb = np.array([unpack565(pal[i]) for i in range(1, nart + 1)],
                            dtype=np.float64)

    def nearest(self, c):
        d = ((self.rgb - c) ** 2 * self.W).sum(1)
        return int(d.argmin()) + 1

    def dither(self, img, mask=None):
        h, w = img.shape[:2]
        work = np.array(img, dtype=np.float64)
        out = np.zeros((h, w), np.uint8)
        for y in range(h):
            for x in range(w):
                if mask is not None and not mask[y, x]:
                    continue
                c = np.clip(work[y, x], 0, 255)
                i = self.nearest(c)
                out[y, x] = i
                err = c - self.rgb[i - 1]
                for dx, dy, f in ((1, 0, 7 / 16), (-1, 1, 3 / 16),
                                  (0, 1, 5 / 16), (1, 1, 1 / 16)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and (
                            mask is None or mask[ny, nx]):
                        work[ny, nx] += err * f
        return out


# ─────────────────────────────────────────────────────── the keyed art
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


STEEL = ((214, 222, 236), (120, 132, 154), (58, 64, 82))


def flipper_art(side, f, piv, length, rest, active):
    """A 56 x 64 keyed flipper at animation frame f, drawn about the pivot
    pcbtable.json AUTHORS - so the picture and the collision zone cannot
    disagree about where the flipper is."""
    ox = FLIP_LX if side == "l" else FLIP_RX
    px, py = piv[0] - ox, piv[1] - FLIP_Y
    img = np.zeros((FLIPH, FLIPW, 3), dtype=np.float64)
    al = np.zeros((FLIPH, FLIPW), bool)
    deg = rest + (active - rest) * (f / float(NFLIPF - 1))
    ang = math.radians(deg)
    if side == "r":
        ang = math.pi - ang
    ca, sa = math.cos(ang), math.sin(ang)
    base = (232, 62, 58) if side == "l" else (66, 166, 240)
    dark = (62, 16, 16) if side == "l" else (14, 44, 78)
    for y in range(FLIPH):
        for x in range(FLIPW):
            vx, vy = x - px, y - py
            t = vx * ca + vy * sa
            n = abs(-vx * sa + vy * ca)
            wdt = 6.2 - 3.0 * max(0.0, t) / length
            if -5.0 <= t <= length and n <= wdt:
                al[y, x] = True
                sh = 1.0 - n / max(0.8, wdt)
                img[y, x] = lerp(lerp(dark, base, 0.55 + 0.45 * sh),
                                 (255, 255, 255), 0.35 * sh ** 3)
            if math.hypot(vx, vy) < 5.2:                # the pivot boss
                al[y, x] = True
                img[y, x] = lerp(STEEL[1], STEEL[0],
                                 max(0.0, 1.0 - math.hypot(vx + 1, vy + 1) / 5.0))
    return img, al


def spr_ball(f):
    """The hardware sprite: 16 x 16 of 2-bit codes, two planes a row.
    1 outline, 2 body, 3 highlight."""
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


def banner(text, scale, ink, paper):
    """The loading screen's one line, as palette indices: an OPAQUE rectangle
    the loader writes straight into the view with VDATA.  ⚠ It is inside the
    rows the picture itself overwrites, so nothing it draws survives the
    load - which is what keeps it out of the VRAM gate."""
    w = len(text) * (5 + 1) * scale - scale
    h = 7 * scale
    a = np.full((h, w), paper, np.uint8)
    x = 0
    for ch in text.upper():
        g = FONT.get(ch, FONT[" "])
        for ry in range(7):
            for rx in range(5):
                if g[ry][rx] != "#":
                    continue
                a[ry * scale:(ry + 1) * scale, x + rx * scale:x + (rx + 1) * scale] = ink
        x += (5 + 1) * scale
    return a


# ──────────────────────────────────────────────────────────── emission
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


def emit_words(label, data, comment=""):
    out = []
    if comment:
        out.append("* " + comment)
    out.append("%-19s fdb       %s" % (label, ",".join(str(v) for v in data)))
    return "\n".join(out)


def b64(a):
    return base64.b64encode(bytes(bytearray(a))).decode()


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    T = json.load(open(os.path.join(HERE, "pcbtable.json")))

    BLK, CW, CH = T["blk"], T["cw"], T["ch"]
    TW, TH, VSMAX = T["w"], T["h"], T["vsmax"]
    NART, LAMP0, SEG0 = T["nart"], T["lamp0"], T["seg0"]
    NLAMP, NDIG = T["nlamp"], T["ndig"]
    NSEG = T["nseg"]
    pal = T["pal"]
    K = T["kinds"]

    picp = os.path.join(HERE, T["pic"])
    palp = os.path.join(HERE, T["pal_file"])
    pic = np.fromfile(picp, dtype=np.uint8)
    assert pic.size == TW * TH == T["bytes"], (pic.size, TW * TH)
    assert sha(picp) == T["pic_sha256"], (
        "pcbtable.pic does not match the sha256 in pcbtable.json - re-run mkpcb.py")
    assert sha(palp) == T["pal_sha256"], "pcbtable.pal does not match its sha256"
    pic = pic.reshape(TH, TW)
    assert not (pic == 0).any(), "the picture contains index 0, the colour key"
    assert TH * TW % 512 == 0 and T["sd_blocks"] == TH * TW // 512

    # ── the flipper rectangles, ASSERTED against the zones the JSON derives
    fl, fr = T["flippers"]["l"], T["flippers"]["r"]
    for side, rec, x0 in (("l", fl, FLIP_LX), ("r", fr, FLIP_RX)):
        zx0, zy0, zx1, zy1 = rec["zone_rect"]
        px, py = rec["pivot"]
        assert x0 <= px <= x0 + FLIPW - 1, (side, "the pivot is outside the frame")
        assert FLIP_Y <= py <= FLIP_Y + FLIPH - 1, (side, "pivot row")
        assert FLIP_Y <= zy0 and zy1 <= FLIP_Y + FLIPH - 1, (
            side, "the collision zone is taller than the drawn frame", zy0, zy1)
    assert FLIP_LX + FLIPW <= FLIP_RX, "the two flipper frames overlap"
    assert R_FLIP + 2 * FLIPH <= R_FART and R_FART + 2 * FLIPH <= R_BALL
    assert R_BALL + BALLH <= R_SAVE and R_SAVE + BALLH <= R_SPR
    assert C_BANK + NFLIPF * FLIPW <= 1024
    assert C_BANK + MAXBLIT * BALLW <= 1024

    # ── the actors, quantised against the PICTURE's own 205 art colours
    q = Quant(pal, NART)
    balls = [ball_art(f) for f in range(NBALLF)]
    ballart = np.zeros((BALLH, NBALLF * BALLW), np.uint8)
    for f, (img, al) in enumerate(balls):
        ballart[:, f * BALLW:(f + 1) * BALLW] = q.dither(img, al)

    # ⭐ TWO BANDS OF FOUR, left over right: the ROM turns (side, angle) into
    # (row, column) with one multiply each and no id arithmetic at all.
    flipart = np.zeros((2 * FLIPH, NFLIPF * FLIPW), np.uint8)
    for si, side in enumerate(("l", "r")):
        rec = fl if side == "l" else fr
        for f in range(NFLIPF):
            img, al = flipper_art(side, f, rec["pivot"], rec["length"],
                                  rec["rest_deg"], rec["active_deg"])
            flipart[si * FLIPH:(si + 1) * FLIPH,
                    f * FLIPW:(f + 1) * FLIPW] = q.dither(img, al)

    spr = []
    for f in range(NGAIT):
        spr += spr_ball(f)

    # ⛔ INDEX 0 IS THE KEY, and a keyed frame with no hole or no ink is a
    # frame the copy engine would draw as a solid block.
    for i in range(NBALLF):
        s = ballart[:, i * BALLW:(i + 1) * BALLW]
        assert (s != 0).any() and (s == 0).any(), "ball %d has no ink or no hole" % i
    for si in range(2):
        for f in range(NFLIPF):
            s = flipart[si * FLIPH:(si + 1) * FLIPH, f * FLIPW:(f + 1) * FLIPW]
            assert (s != 0).any() and (s == 0).any(), (
                "flipper %s%d has no ink or no hole" % ("lr"[si], f))
    bad = [int(v) for v in np.unique(np.concatenate(
        [ballart.reshape(-1), flipart.reshape(-1)])) if v >= LAMP0]
    assert not bad, ("the dither produced a RESERVED index", bad)

    # ⚠ AND THE SPRITE'S THREE BANKS COUNT TOO.  The lamp gate finds a lamp by
    # its exact RGB565 among a recorded frame's pixels; a sprite bank that
    # happened to equal one would make a ball read as a lit lamp.
    reserved = set(T["lampon"]) | set(T["lampoff"]) | {T["segon"], T["segoff"]}
    for i, c in enumerate(SPR_LUT):
        assert rgb565(c) not in reserved, (
            "sprite bank %d is also a reserved colour - nudge it" % (i + 1), c)

    # ── the loading screen's three indices, out of the art's own palette
    ls_bg, ls_frm, ls_bar = (q.nearest(np.array(c, float))
                             for c in (LS_BG, LS_FRM, LS_BAR))
    ban = banner(BANNER, BANSCALE, ls_frm, ls_bg)
    BANH, BANW = ban.shape

    # ── ⭐ THE COLLISION GRID, VERBATIM.  Neither byte is computed here.
    colmap = np.frombuffer(base64.b64decode(T["colmap"]), np.uint8)
    idmap = np.frombuffer(base64.b64decode(T["idmap"]), np.uint8)
    assert colmap.size == idmap.size == CW * CH
    used = sorted(set(int(v) for v in np.unique(colmap)))
    assert used == sorted(K.values()), ("the grid does not use every kind", used)

    # ── the objects' lamps, as BIT numbers, and the kickers' vectors
    def lampbit(idx):
        assert idx is None or LAMP0 <= idx < LAMP0 + NLAMP, idx
        return 0xFF if idx is None else idx - LAMP0

    bumplmp = [lampbit(b["lamp"]) for b in T["bumpers"]]
    targlmp = [lampbit(t["lamp"]) for t in T["targets"]]
    rolllmp = [lampbit(r["lamp"]) for r in T["rollovers"]]
    kicklmp = [lampbit(k["lamp"]) for k in T["kickers"]]

    def vel(d, p):
        return int(round(d * p * VMAX))

    kickvx = [vel(k["dir"][0], k["power"]) for k in T["kickers"]]
    kickvy = [vel(k["dir"][1], k["power"]) for k in T["kickers"]]
    # ⚠ A KICKER THAT ONLY KICKS SIDEWAYS LEAVES THE BALL WEIGHTLESS for a
    # frame and the lane's mouth is exactly that one, so it is given the
    # gravity step it would have had.
    kickvy = [v if v else GRAV * 4 for v in kickvy]

    # ⭐ THE RETURN LANES AIM AT THE FLIPPER PIVOT THE JSON GIVES THEM: the
    # sign of (to.x - the lane's own centre) is which way the ball is sent,
    # and nothing here writes a direction down.
    retvx, retvy = [], []
    for r in T["returns"]:
        x0, _, x1, _ = r["rect"]
        cx = (x0 + x1) / 2.0
        s = 1 if r["to"][0] > cx else -1
        retvx.append(s * (VMAX * 2 // 3))
        retvy.append(-(VMAX // 8))

    # ⭐ THE BALL IS SERVED INTO THE MIDDLE OF THE SEAT, at rest, and the
    # KPLNG cell is what throws it (pinball.asm's Launch).  A serve that also
    # threw the ball left the seat on the frame it appeared, so the plunger
    # kind was met by nothing and the one mechanism every ball starts with
    # was the one the bench could not see.
    seat = T["plunger"]["seat"]
    plungx = ((seat[0] + seat[2] + 1) // 2) * 16
    plungy = ((seat[1] + seat[3] + 1) // 2) * 16

    # ── the flipper zones, in table pixels, from the JSON's own rects
    fz = []
    for rec in (fl, fr):
        fz.append(rec["zone_rect"])

    kv = dict(K)
    DAT = [
        "* ⭐ THE GEOMETRY IS EMITTED, NOT RESTATED - monster.asm's lesson: a",
        "*      literal that drifted from its generator made every strip wrong",
        "*      and still looked plausible (bench/README.md).",
        "* ⭐ AND THE TABLE IS NOT HERE AT ALL.  It is pcbtable.pic, 327,680",
        "*      bytes on the SD card, read straight into VRAM rows 0..511.",
        "PBCW                equ       %d        the collision grid, in cells" % CW,
        "PBCH                equ       %d" % CH,
        "PBBLK               equ       %d        ... and a cell, in pixels" % BLK,
        "PBTW                equ       %d       the table, in pixels" % TW,
        "PBTH                equ       %d" % TH,
        "PBVSMAX             equ       %d       the highest VSCROLL with no wrap" % VSMAX,
        "PBPICSZ             equ       %d    the picture, in bytes" % (TW * TH),
        "PBCHUNK             equ       %d         VRAM rows in one I$Read" % PICCHUNK,
        "PBBUFSZ             equ       %d      ... which is this many bytes" % (PICCHUNK * TW),
        "PBNCHNK             equ       %d        chunks in the whole picture" % (TH // PICCHUNK),
        "PBTRUNR             equ       %d       ⛔ where the truncation mutation stops" % TRUNCR,
        "PBCBANK             equ       %d       the spare columns" % C_BANK,
        "PBRFLIP             equ       %d         the composed flipper frames" % R_FLIP,
        "PBRFART             equ       %d       the KEYED flipper art" % R_FART,
        "PBRBALL             equ       %d       the keyed ball art" % R_BALL,
        "PBRSAVE             equ       %d       the save-behind scratch" % R_SAVE,
        "PBFLIPW             equ       %d" % FLIPW,
        "PBFLIPH             equ       %d" % FLIPH,
        "PBNFLIP             equ       %d         frames a flipper" % NFLIPF,
        "PBFLX               equ       %d       the left flipper's frame ..." % FLIP_LX,
        "PBFRX               equ       %d       ... and the right one's" % FLIP_RX,
        "PBFLY               equ       %d" % FLIP_Y,
        "PBBALLW             equ       %d" % BALLW,
        "PBBALLH             equ       %d" % BALLH,
        "PBNBALLF            equ       %d" % NBALLF,
        "PBMAXBL             equ       %d        blit balls (0 is the sprite)" % MAXBLIT,
        "PBNGAIT             equ       %d" % NGAIT,
        "PBLAMP0             equ       %d       the first reserved LUT entry" % LAMP0,
        "PBNLAMP             equ       %d" % NLAMP,
        "PBSEG0              equ       %d" % SEG0,
        "PBNDIG              equ       %d" % NDIG,
        "PBNRES              equ       %d        lamps + segments" % (NLAMP + NSEG),
        "PBFLASH             equ       %d         the lamp that pulses on its own" % FLASH,
        "PBNBUMP             equ       %d" % len(bumplmp),
        "PBNTARG             equ       %d" % len(targlmp),
        "PBNROLL             equ       %d" % len(rolllmp),
        "PBNKICK             equ       %d" % len(kickvx),
        "PBNRET              equ       %d" % len(retvx),
        "PBPLNGX             equ       %d      the plunger's seat, 12.4 ..." % plungx,
        "PBPLNGY             equ       %d" % plungy,
        "PBPLNGV             equ       %d      ... and how hard it throws" % PLUNGV,
        "PBLSBG              equ       %d       the loading screen's three" % ls_bg,
        "PBLSFRM             equ       %d       indices, out of the art's own" % ls_frm,
        "PBLSBAR             equ       %d       palette" % ls_bar,
        "PBBANW              equ       %d       the banner" % BANW,
        "PBBANH              equ       %d" % BANH,
        "* ⭐ the collision kinds, which are pcbtable.json's `kinds` and the",
        "*      physics' - one list, and mkpcb.py owns it",
        "KEMPTY              equ       %d" % kv["empty"],
        "KSOLID              equ       %d" % kv["solid"],
        "KSLOPR              equ       %d        a falling ball leaves RIGHT" % kv["slope_r"],
        "KSLOPL              equ       %d        ... and LEFT" % kv["slope_l"],
        "KBUMP               equ       %d" % kv["bumper"],
        "KTARG               equ       %d" % kv["target"],
        "KROLL               equ       %d" % kv["rollover"],
        "KKICK               equ       %d" % kv["kicker"],
        "KDRAIN              equ       %d" % kv["drain"],
        "KFLIPL              equ       %d" % kv["flip_l"],
        "KFLIPR              equ       %d" % kv["flip_r"],
        "KRET                equ       %d       a return lane: it aims" % kv["return"],
        "KPLNG               equ       %d       the plunger seat: it fires" % kv["plunger"],
        "* the flipper zones, in table pixels: x0, y0, x1, y1, left then right",
        emit_words("FlipZ", [v for r in fz for v in r]),
        emit_bytes("ColMap", colmap.tolist(), 16,
                   "⭐ THE COLLISION GRID, %d x %d, verbatim out of" % (CW, CH)),
        "*      pcbtable.json.  mkpcb.py derives it from the object",
        "*      rectangles and checkpcb.py asserts it against the PICTURE;",
        "*      nothing here re-derives it from pixels.",
        emit_bytes("IdMap", idmap.tolist(), 16,
                   "... and WHICH object each cell belongs to"),
        emit_bytes("BumpLmp", bumplmp, 16, "each bumper's lamp, as a bit number"),
        emit_bytes("TargLmp", targlmp, 16, "each drop target's ..."),
        emit_bytes("RollLmp", rolllmp, 16, "... each rollover's ..."),
        emit_bytes("KickLmp", kicklmp, 16, "... and each kicker's ($FF: none)"),
        emit_words("KickVX", kickvx, "the kickers' velocities, 12.4 a frame"),
        emit_words("KickVY", kickvy),
        emit_words("RetVX", retvx, "and the return lanes', aimed at the pivot"),
        emit_words("RetVY", retvy),
        emit_bytes("LampOn", [b for v in T["lampon"] for b in (v >> 8, v & 255)],
                   16, "the lamps lit ..."),
        emit_bytes("LampOff", [b for v in T["lampoff"] for b in (v >> 8, v & 255)],
                   16, "... and out"),
        emit_bytes("SegOn", [T["segon"] >> 8, T["segon"] & 255], 16, "a segment lit ..."),
        emit_bytes("SegOff", [T["segoff"] >> 8, T["segoff"] & 255], 16, "... and out"),
        emit_bytes("BallArt", ballart.reshape(-1).tolist(), 16,
                   "the keyed ball: %d frames of %d x %d, holes are index 0"
                   % (NBALLF, BALLW, BALLH)),
        emit_bytes("FlipArt", flipart.reshape(-1).tolist(), 16,
                   "the keyed flippers: 2 bands of %d, %d x %d, left over right"
                   % (NFLIPF, FLIPW, FLIPH)),
        emit_bytes("SprArt", spr, 16,
                   "the hardware sprite: %d shapes of 64 bytes (plan 7's planes)"
                   % NGAIT),
        emit_bytes("BanArt", ban.reshape(-1).tolist(), 16,
                   "⭐ the loading screen's banner, %d x %d, OPAQUE - it is"
                   % (BANW, BANH)),
        "*      written into rows the picture itself overwrites",
        "* the sprite's three LUT banks: outline, body, highlight",
        "SprLut              fdb       " + ",".join("$%04X" % rgb565(c) for c in SPR_LUT),
        "* the data files, on the card beside the programs",
        'PicNam              fcc       "%s"' % T["pic"],
        "                    fcb       0",
        'PalNam              fcc       "%s"' % T["pal_file"],
        "                    fcb       0",
    ]

    rule = "*" * 68
    top = rule + "\n* %s - generated by video3/bench/mkpinball.py; do not edit by hand\n" + rule + "\n"
    os.makedirs(out, exist_ok=True)
    p = os.path.join(out, "pinballdat.asm")
    open(p, "w").write(top % "pinballdat.asm" + "\n".join(DAT) + "\n")
    print("ok    %s (%d bytes of source)" % (p, os.path.getsize(p)))

    j = dict(
        blk=BLK, cw=CW, ch=CH, tw=TW, th=TH, vsmax=VSMAX,
        c_bank=C_BANK, r_flip=R_FLIP, r_fart=R_FART, r_ball=R_BALL,
        r_save=R_SAVE, r_spr=R_SPR, c_spr=C_SPR,
        flipw=FLIPW, fliph=FLIPH, nflipf=NFLIPF,
        flip_lx=FLIP_LX, flip_rx=FLIP_RX, flip_y=FLIP_Y,
        ballw=BALLW, ballh=BALLH, nballf=NBALLF,
        maxblit=MAXBLIT, ngait=NGAIT,
        lamp0=LAMP0, nlamp=NLAMP, seg0=SEG0, ndig=NDIG, nart=NART, flash=FLASH,
        picchunk=PICCHUNK, truncr=TRUNCR,
        pic=T["pic"], pic_sha256=T["pic_sha256"],
        pal_file=T["pal_file"], pal_sha256=T["pal_sha256"],
        pal=pal, lampon=T["lampon"], lampoff=T["lampoff"],
        segon=T["segon"], segoff=T["segoff"], sprlut=[rgb565(c) for c in SPR_LUT],
        kinds=K,
        ballart=b64(ballart.reshape(-1).tolist()),
        flipart=b64(flipart.reshape(-1).tolist()),
        spr=b64(spr),
        colmap=b64(colmap.tolist()), idmap=b64(idmap.tolist()),
        ls_bg=int(ls_bg), ls_frm=int(ls_frm), ls_bar=int(ls_bar),
    )
    jp = os.path.join(HERE, "pinball.json")
    open(jp, "w").write(json.dumps(j))
    print("ok    %s (%d bytes)" % (jp, os.path.getsize(jp)))

    # ── a preview: the table as the scene will hold it, with the actors
    from PIL import Image
    lut = np.array([unpack565(v) for v in pal], dtype=np.uint8)
    lut[0] = (255, 0, 255)
    for k in range(NLAMP):
        lut[LAMP0 + k] = unpack565(T["lampon"][k])
    for s in range(NSEG):
        lut[SEG0 + s] = unpack565(T["segon"])
    shown = pic.copy()
    for si, fx in ((0, FLIP_LX), (1, FLIP_RX)):
        art = flipart[si * FLIPH:(si + 1) * FLIPH, 0:FLIPW]
        tile = shown[FLIP_Y:FLIP_Y + FLIPH, fx:fx + FLIPW].copy()
        tile[art != 0] = art[art != 0]
        shown[FLIP_Y:FLIP_Y + FLIPH, fx:fx + FLIPW] = tile
    strip = 2 * FLIPH + 8
    sheet = Image.new("RGB", (TW, TH + strip + 8), (10, 10, 14))
    sheet.paste(Image.fromarray(lut[shown]), (0, 0))
    lut2 = lut.copy()
    lut2[0] = (24, 24, 32)
    sheet.paste(Image.fromarray(lut2[flipart]), (0, TH + 4))
    sheet.paste(Image.fromarray(lut2[ballart]), (NFLIPF * FLIPW + 8, TH + 4))
    sheet.paste(Image.fromarray(lut2[ban]),
                (NFLIPF * FLIPW + 8, TH + 4 + BALLH + 6))
    pp = os.path.join(HERE, "pinball-art.png")
    sheet.save(pp)
    print("ok    %s" % pp)
    print("      the table is a FILE: %s, %d bytes, %d SD blocks"
          % (T["pic"], TW * TH, T["sd_blocks"]))
    print("      module data: %d B grid + %d B keyed art + %d B sprite + %d B banner"
          % (colmap.size + idmap.size, ballart.size + flipart.size,
             len(spr), ban.size))


if __name__ == "__main__":
    main()
