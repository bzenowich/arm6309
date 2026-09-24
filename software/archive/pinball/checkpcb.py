#!/usr/bin/env python3
"""checkpcb.py - the gates on `mkpcb.py`'s table.  ⛔ Its exit code is the answer.

    python3 software/archive/pinball/checkpcb.py              # the table as generated
    python3 software/archive/pinball/checkpcb.py --negative   # ⭐ and the control

It reads `pcbtable.pic`, `pcbtable.pal` and `pcbtable.json` and asks three
different kinds of question:

  ⛔ THE INDEX GATE.  Index 0 is the copy engine's colour key and may never be
     a visible pixel; the 8 lamps and the 42 segments must each be somewhere
     the camera goes; and no art colour may equal a reserved one, because the
     scene lights a lamp by writing the LUT and a checker reads it back by
     LOOKING for that colour in the picture.  If a wall could be the same
     RGB565 as a lit lamp, a lit lamp and a wall would be the same evidence.
  ⭐ THE COLLISION GATE, which is the one a full-graphic table needs and the
     block-built one did not.  `mkpinball.py`'s physics read the block grid,
     so art and collision were the same object and could not disagree.  Here
     the picture is a picture and the grid is 1,280 bytes beside it, so the
     agreement is a CLAIM: every cell marked bumper has IC pixels under it,
     every cell the ball flies through has none, every wall is visibly a wall
     (ground pour, copper or a part - never open solder mask), the drain is a
     milled slot at the bottom and the flipper zones flank it.
     ⚠ It reads the PICTURE, through the palette, and classifies pixels by
     colour - not the generator's own notion of what it drew.  That is the
     only version of this check worth running.
  ⭐ THE REACHABILITY GATE.  From the plunger seat, a ball must be able to get
     to every drain through cells that do not block it.  A pocket the ball
     can fall into and never leave is a table that gates green and plays dead.

⛔ AND THE NEGATIVE CONTROL.  `--negative` mutates the inputs eleven ways -
shifts the collision grid a cell, recolours a bumper to bare board, moves the
drain to the top, kills a lamp, plants the colour key, swaps the flippers,
collides an art colour with a lamp's, moves an actuator, fills a slot with
copper, strips a wall's pour - and REQUIRES each mutation to be caught.  A
green check proves nothing on its own (CLAUDE.md); `--negative` is what says
these ones can go red.

`--mutate NAME` applies one of them and prints the claims it broke.
"""
import base64
import hashlib
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# ── the thresholds.  Every one is a measured separation, and the run prints
# the margin it had, so a change in the art that erodes one is visible before
# it is fatal.  (measured 2026-09-20, over the 1,280 cells of the table)
T_IC_DARK = 0.32        # bumper cells: 0.42..0.52; anything open: <= 0.29
T_IC_PINS = 0.10        # bumper cells: 0.18..0.30
T_SW_RED = 0.08         # target cells: 0.11..0.33; anything open: <= 0.04
T_ACT_LUM = 150.0       # a switch actuator is white plastic: 191..200
T_PAD_GOLD = 0.45       # rollover cells: 0.57..0.60
T_SLOT = 0.60           # drain cells: 0.84..0.96; anything open: <= 0.29
T_SLOT_OPEN = 0.50
T_POUR = 0.10           # a wall is poured: >= 0.10; open cells: <= 0.027
T_POUR_OPEN = 0.08
T_COVER = 0.30          # ... or a part, a relief or a slot sits on it
T_GOLD_WALL = 0.45      # ... or it is buried under copper
T_SEG_FILL = 0.50       # a segment must fill its declared box

BLOCKING = ("solid", "slope_r", "slope_l", "bumper", "target")
OPEN_KINDS = ("empty", "rollover", "return", "flip_l", "flip_r", "plunger")


def unpack565(v):
    v = np.asarray(v)
    r5, g6, b5 = v >> 11, (v >> 5) & 63, v & 31
    return np.stack([(r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4),
                     (b5 << 3) | (b5 >> 2)], -1).astype(np.int32)


def rgb565(c):
    r, g, b = int(c[0]), int(c[1]), int(c[2])
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def load():
    j = json.load(open(os.path.join(HERE, "pcbtable.json")))
    raw = open(os.path.join(HERE, j["pic"]), "rb").read()
    palb = open(os.path.join(HERE, j["pal_file"]), "rb").read()
    return dict(j=j, raw=raw, palb=palb,
                pal=list(j["pal"]),
                col=np.frombuffer(base64.b64decode(j["colmap"]),
                                  np.uint8).reshape(j["ch"], j["cw"]).copy(),
                ident=np.frombuffer(base64.b64decode(j["idmap"]),
                                    np.uint8).reshape(j["ch"], j["cw"]).copy())


class Mat:
    """The picture's materials, read back through the palette.

    ⚠ Reserved indices are excluded from every class.  A lamp lens is not art:
    its colour is whatever the scene last wrote to the LUT, so counting an
    unlit LED as "dark" made three empty cells look like ICs on the first run
    of this check.
    """

    def __init__(self, pic, pal):
        rgb = unpack565(np.array(pal, dtype=np.int64))[pic]
        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        lum = (r * 299 + g * 587 + b * 114) // 1000
        art = pic <= 205
        self.art = art
        self.lum = lum
        self.green = (g > r + 8) & (g > b + 8) & art
        self.pour = (g > 92) & (g > r + 38) & (g > b + 38) & art
        self.gold = (r > g + 12) & (g > b + 10) & (lum > 70) & art
        self.dark = (lum < 58) & (np.abs(r - b) < 26) & (g <= r + 14) & art
        self.silver = ((lum > 120) & (np.abs(r - b) < 30)
                       & (np.abs(r - g) < 24) & art)
        # ⚠ BY DENSITY, NOT BY COLOUR ALONE.  A resistor's red colour band
        # is two pixels wide and exactly as saturated as a switch case, so a
        # plain colour test put one lane-marker cell at 0.15 against a
        # threshold of 0.15 - a gate with no margin is a gate that will go
        # off for the wrong reason.  A drop target is a BLOCK of red and a
        # colour band is a stripe, so the test is on the shape: a red pixel
        # counts when most of its 5 x 5 neighbourhood is red too.  ⚠ And the
        # neighbourhood is why a 3 x 3 EROSION was wrong - the picture is
        # Floyd-Steinberg dithered, so even the middle of the switch case has
        # holes in it, and erosion deleted all eight targets.
        red = (r > g + 70) & (r > b + 70) & (lum > 50) & art
        self.red = boxmean(red.astype(np.float32), 2) > 0.5
        self.slot = (lum < 24) & art


def boxmean(m, k):
    """The mean of each pixel's (2k+1) square, from a summed-area table."""
    P = np.pad(m, k)
    C = np.pad(np.cumsum(np.cumsum(P, 0), 1), ((1, 0), (1, 0)))
    h, w = m.shape
    n = 2 * k + 1
    return (C[n:n + h, n:n + w] - C[0:h, n:n + w]
            - C[n:n + h, 0:w] + C[0:h, 0:w]) / float(n * n)


def frac(m, x, y, blk=16):
    return float(m[y * blk:(y + 1) * blk, x * blk:(x + 1) * blk].mean())


# ══════════════════════════════════════════════════════════════ the checks
def run(st, claim):
    j, raw, palb = st["j"], st["raw"], st["palb"]
    W, H, BLK = j["w"], j["h"], j["blk"]
    CW, CH, PLAY_H = j["cw"], j["ch"], j["play_h"]
    PLAY_R = PLAY_H // BLK
    K = j["kinds"]
    kn = {v: k for k, v in K.items()}
    col, ident = st["col"], st["ident"]
    pal = st["pal"]

    # ───────────────────────────────────────────────── the files themselves
    claim("the .pic is exactly %d bytes (%d SD blocks of 512)"
          % (W * H, W * H // 512), len(raw) == W * H)
    claim("the .pic is %d SD blocks with no partial tail" % (W * H // 512),
          (W * H) % 512 == 0)
    if len(raw) != W * H:
        return
    pic = np.frombuffer(raw, np.uint8).reshape(H, W).copy()
    claim("the .pic hashes to what the JSON was written beside",
          hashlib.sha256(raw).hexdigest() == j["pic_sha256"])
    claim("the .pal is exactly 512 bytes (256 big-endian RGB565 words)",
          len(palb) == 512)
    claim("the .pal hashes to what the JSON was written beside",
          hashlib.sha256(palb).hexdigest() == j["pal_sha256"])

    # ────────────────────────────────────────────────────────── the palette
    claim("the palette is exactly 256 entries", len(pal) == 256)
    claim("every palette entry is a 16-bit RGB565 word",
          all(isinstance(v, int) and 0 <= v < 65536 for v in pal))
    claim("every palette entry is ON the RGB565 grid it is stored on",
          all(rgb565(unpack565(np.int64(v))) == v for v in pal))
    filepal = [(palb[i * 2] << 8) | palb[i * 2 + 1] for i in range(256)] \
        if len(palb) == 512 else []
    claim("the .pal file IS the JSON's palette, big-endian", filepal == pal)
    claim("entry 0 is the colour key and is bright magenta, not a board colour",
          pal[0] == 0xF81F)
    nart, lamp0, seg0 = j["nart"], j["lamp0"], j["seg0"]
    claim("the LUT split is 1..%d art, %d..%d lamps, %d..255 segments"
          % (nart, lamp0, lamp0 + j["nlamp"] - 1, seg0),
          lamp0 == 1 + nart and seg0 == lamp0 + j["nlamp"]
          and seg0 + j["nseg"] == 256)
    artpal = pal[1:1 + nart]
    claim("all %d art entries are distinct - a duplicate is a wasted colour"
          % nart, len(set(artpal)) == nart)
    res = ([("lamp %d on" % k, v) for k, v in enumerate(j["lampon"])]
           + [("lamp %d off" % k, v) for k, v in enumerate(j["lampoff"])]
           + [("segment on", j["segon"]), ("segment off", j["segoff"])])
    bad = [n for n, v in res if v in set(artpal) or v == pal[0]]
    claim("no reserved colour is also an art colour (%d checked): %s"
          % (len(res), bad or "none"), not bad)

    # ───────────────────────────────────────────────────────── the indices
    n0 = int((pic == 0).sum())
    claim("index 0, the copy engine's colour key, appears NOWHERE (%d found)"
          % n0, n0 == 0)
    mat = Mat(pic, pal)
    used = set(int(v) for v in np.unique(pic))
    claim("every index the picture uses is 1..%d or a reserved %d..255"
          % (nart, lamp0), all(1 <= v <= 255 for v in used))

    # where each reserved index is allowed to be.  ⚠ ONE BOX LIST AN INDEX,
    # not one array for all of them: a display's mitred segments INTERLOCK
    # (`a`'s box and `f`'s share a corner), so a single "who owns this pixel"
    # array keeps whichever was written last and calls the other a stray - it
    # reported 36 of the 42 segments as out of place, and every one of them
    # was exactly where it belonged.
    allowed = {}
    for L in j["lamps"]:
        allowed.setdefault(L["index"], []).extend([L["box"]] + L["playfield"])
    for d, dg in enumerate(j["digits"]):
        for sgi, sb in enumerate(dg["segs"]):
            allowed.setdefault(seg0 + d * 7 + sgi, []).append(sb)
    for i in range(lamp0, 256):
        m = pic == i
        n = int(m.sum())
        claim("reserved index %d appears in the picture (%d pixels)" % (i, n),
              n > 0)
        if not n:
            continue
        ok = np.zeros((H, W), bool)
        for x0, y0, x1, y1 in allowed.get(i, []):
            ok[y0:y1 + 1, x0:x1 + 1] = True
        stray = int((m & ~ok).sum())
        claim("every pixel of index %d is inside one of its own %d declared "
              "boxes (%d stray)" % (i, len(allowed.get(i, [])), stray),
              stray == 0)
    lam = {L["index"]: L for L in j["lamps"]}
    for i in range(lamp0, seg0):
        m = pic == i
        sites = [bx for bx in [lam[i]["box"]] + lam[i]["playfield"]
                 if (pic[bx[1]:bx[3] + 1, bx[0]:bx[2] + 1] == i).any()]
        claim("lamp %d is in %d places, not one - a lamp the camera never "
              "reaches cannot be seen to work" % (i, len(sites)), len(sites) >= 2)
        claim("lamp %d is somewhere on the PLAYFIELD (y < %d), not only on "
              "the backplane" % (i, PLAY_H),
              bool(m[:PLAY_H].any()))
    for d, dg in enumerate(j["digits"]):
        idxs = set()
        for sgi, sb in enumerate(dg["segs"]):
            i = seg0 + d * 7 + sgi
            idxs.add(i)
            x0, y0, x1, y1 = sb
            f = float((pic[y0:y1 + 1, x0:x1 + 1] == i).mean())
            claim("digit %d segment %s fills its box (%.2f >= %.2f)"
                  % (d, "abcdefg"[sgi], f, T_SEG_FILL), f >= T_SEG_FILL)
        claim("digit %d is seven DISTINCT indices" % d, len(idxs) == 7)
    claim("the six digits use 42 distinct segment indices",
          len({seg0 + d * 7 + s for d in range(6) for s in range(7)}) == 42)
    okp = all(pic[v[0], v[1]] == int(k) for k, v in j["probes"].items())
    claim("every probe in the JSON points at a pixel that really holds its "
          "index (%d probes)" % len(j["probes"]), okp)

    # ─────────────────────────────────────────── the collision map vs the art
    claim("the collision map is %d x %d cells" % (CW, CH), col.shape == (CH, CW))
    claim("every cell kind is a declared kind",
          bool(np.isin(col, list(K.values())).all()))

    cover = np.zeros((H, W), bool)
    for rr in ([o["rect"] for o in j["parts"]] + j["reliefs"]
               + [d["rect"] for d in j["drains"]]):
        x0, y0, x1, y1 = rr
        cover[y0:y1 + 1, x0:x1 + 1] = True

    for bm in j["bumpers"]:
        cs = [tuple(c) for c in bm["cells"]]
        dmin = min(frac(mat.dark, x, y) for x, y in cs)
        smin = min(frac(mat.silver, x, y) for x, y in cs)
        claim("bumper %s (%s): every one of its %d cells has an IC body "
              "under it (darkest %.2f >= %.2f)"
              % (bm["desig"], bm["part"], len(cs), dmin, T_IC_DARK),
              dmin >= T_IC_DARK)
        claim("bumper %s: every cell has pins or silkscreen (%.2f >= %.2f)"
              % (bm["desig"], smin, T_IC_PINS), smin >= T_IC_PINS)
        claim("bumper %s: the grid agrees it is a bumper on all %d cells"
              % (bm["desig"], len(cs)),
              all(col[y, x] == K["bumper"] and ident[y, x] == bm["id"]
                  for x, y in cs))
        x0, y0, x1, y1 = bm["rect"]
        claim("bumper %s: its centre and radius are inside its own package"
              % bm["desig"],
              x0 <= bm["cx"] <= x1 and y0 <= bm["cy"] <= y1
              and bm["r"] == min(bm["rx"], bm["ry"]))

    for t in j["targets"]:
        cs = [tuple(c) for c in t["cells"]]
        rmin = min(frac(mat.red, x, y) for x, y in cs)
        claim("target %s: its cells are switch body (%.2f >= %.2f)"
              % (t["desig"], rmin, T_SW_RED), rmin >= T_SW_RED)
        claim("target %s: the grid agrees it is target %d"
              % (t["desig"], t["id"]),
              all(col[y, x] == K["target"] and ident[y, x] == t["id"]
                  for x, y in cs))
        ax0, ay0, ax1, ay1 = t["actuator"]
        lm = float(mat.lum[ay0:ay1 + 1, ax0:ax1 + 1].mean())
        claim("target %s: the actuator is visibly there and visibly UP "
              "(luma %.0f >= %.0f)" % (t["desig"], lm, T_ACT_LUM),
              lm >= T_ACT_LUM)
        x0, y0, x1, y1 = t["rect"]
        claim("target %s: the actuator box is inside the switch" % t["desig"],
              x0 <= ax0 <= ax1 <= x1 and y0 <= ay0 <= ay1 <= y1)

    for ro in j["rollovers"]:
        cs = [tuple(c) for c in ro["cells"]]
        gmin = min(frac(mat.gold, x, y) for x, y in cs)
        claim("rollover %s: all %d cells carry test pads (%.2f >= %.2f)"
              % (ro["name"], len(cs), gmin, T_PAD_GOLD), gmin >= T_PAD_GOLD)
        claim("rollover %s: the grid agrees" % ro["name"],
              all(col[y, x] == K["rollover"] and ident[y, x] == ro["id"]
                  for x, y in cs))

    dcells = [(x, y) for y in range(CH) for x in range(CW)
              if col[y, x] == K["drain"]]
    smin = min(frac(mat.slot, x, y) for x, y in dcells) if dcells else 0.0
    claim("every drain cell is a milled slot through the board (%.2f >= %.2f)"
          % (smin, T_SLOT), dcells and smin >= T_SLOT)
    claim("the drain is at the BOTTOM: every drain cell is in row 20 or below",
          all(y >= 20 for x, y in dcells))
    claim("a drain reaches the bottom row of the playfield (row %d)"
          % (PLAY_R - 1), any(y == PLAY_R - 1 for x, y in dcells))

    # ⭐ AND THE OTHER DIRECTION, which is the one that catches a grid that
    # has slipped: nothing the ball flies through may have a part under it.
    opens = [(x, y) for y in range(PLAY_R) for x in range(CW)
             if kn[col[y, x]] in OPEN_KINDS]
    worst = max((frac(mat.dark, x, y), x, y) for x, y in opens)
    claim("no cell the ball flies through has an IC under it (worst %.2f at "
          "(%d,%d) < %.2f)" % (worst[0], worst[1], worst[2], T_IC_DARK),
          worst[0] < T_IC_DARK)
    worst = max((frac(mat.red, x, y), x, y) for x, y in opens)
    claim("no cell the ball flies through has a switch under it (worst %.2f "
          "at (%d,%d) < %.2f)" % (worst[0], worst[1], worst[2], T_SW_RED),
          worst[0] < T_SW_RED)
    worst = max((frac(mat.slot, x, y), x, y) for x, y in opens)
    claim("no cell the ball flies through is a hole in the board (worst %.2f "
          "at (%d,%d) < %.2f)" % (worst[0], worst[1], worst[2], T_SLOT_OPEN),
          worst[0] < T_SLOT_OPEN)
    worst = max((frac(mat.pour, x, y), x, y) for x, y in opens)
    claim("no cell the ball flies through is ground pour - the pour IS the "
          "wall (worst %.2f at (%d,%d) < %.2f)"
          % (worst[0], worst[1], worst[2], T_POUR_OPEN), worst[0] < T_POUR_OPEN)

    # ⭐ and every wall has to LOOK like one: poured, buried in copper, or
    # carrying a part.  Open solder mask is where the ball goes.
    walls = [(x, y) for y in range(PLAY_R) for x in range(CW)
             if col[y, x] == K["solid"]]
    weak = None
    for x, y in walls:
        ev = max(frac(mat.pour, x, y) / T_POUR, frac(cover, x, y) / T_COVER,
                 frac(mat.gold, x, y) / T_GOLD_WALL)
        if weak is None or ev < weak[0]:
            weak = (ev, x, y)
    claim("every one of the %d solid playfield cells is visibly a wall - "
          "pour, copper or a part, never open mask (weakest %.2f x at (%d,%d))"
          % (len(walls), weak[0], weak[1], weak[2]), weak[0] >= 1.0)

    # every declared part sits on cells the ball cannot enter
    for p in j["parts"]:
        if p["kind"] in ("led", "res", "kicker"):
            continue            # flat, or a kicker: see the generator's rule
        x0, y0, x1, y1 = p["rect"]
        cs = [(x, y) for y in range(CH) for x in range(CW)
              if x0 <= x * BLK + BLK // 2 <= x1 and y0 <= y * BLK + BLK // 2 <= y1]
        claim("%s (%s) stands on cells the ball cannot enter"
              % (p["desig"], p["part"]),
              all(kn[col[y, x]] not in OPEN_KINDS for x, y in cs))

    # ───────────────────────────────────────── the flippers and the drain
    mouth = j["drain_mouth"]
    zl, zr = j["flippers"]["l"], j["flippers"]["r"]
    lc = [tuple(c) for c in zl["zone_cells"]]
    rc = [tuple(c) for c in zr["zone_cells"]]
    claim("the left flipper zone is entirely LEFT of the drain mouth",
          lc and all(x * BLK + BLK // 2 < mouth[0] for x, y in lc))
    claim("the right flipper zone is entirely RIGHT of the drain mouth",
          rc and all(x * BLK + BLK // 2 > mouth[2] for x, y in rc))
    claim("the two flipper zones flank the drain on the same rows",
          sorted({y for x, y in lc}) == sorted({y for x, y in rc}))
    claim("the drain mouth is BETWEEN the two zones",
          max(x for x, y in lc) < min(x for x, y in rc)
          and any(max(x for x, y in lc) < x < min(x2 for x2, y2 in rc)
                  for x in range(mouth[0] // BLK, mouth[2] // BLK + 1)))
    for side, z in (("l", zl), ("r", zr)):
        px, py = z["pivot"]
        cx, cy = int(px) // BLK, int(py) // BLK
        claim("the %s flipper's pivot is inside its own zone"
              % side, (cx, cy) in (lc if side == "l" else rc))
        claim("the %s flipper's zone is marked flip_%s in the grid"
              % (side, side),
              all(col[y, x] == K["flip_" + side]
                  for x, y in (lc if side == "l" else rc)))
        claim("the %s flipper swings both ways about its rest" % side,
              z["rest_deg"] * z["active_deg"] < 0)

    # ───────────────────────────────────────────── the plunger and the lanes
    pl = j["plunger"]
    seat = [(x, y) for y in range(CH) for x in range(CW)
            if col[y, x] == K["plunger"]]
    claim("the plunger seat is at the bottom of the lane",
          seat and all(y >= PLAY_R - 2 for x, y in seat)
          and all(x * BLK >= pl["lane"][0] for x, y in seat))
    claim("the lane divider stops short of the top, so the ball can leave it",
          pl["divider_y0"] > pl["lane"][1])

    # ⭐ REACHABILITY: from the seat, to every drain, through cells that do
    # not block.  A kicker accelerates a ball; it does not stop one.
    block = {K[k] for k in BLOCKING}
    seen = set(seat)
    work = list(seat)
    while work:
        x, y = work.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < CW and 0 <= ny < PLAY_R) or (nx, ny) in seen:
                continue
            if col[ny, nx] in block:
                continue
            seen.add((nx, ny))
            work.append((nx, ny))
    miss = [c for c in dcells if c not in seen]
    claim("every drain is reachable from the plunger seat (%d cells reached, "
          "%d drains unreachable)" % (len(seen), len(miss)), not miss)
    pocket = [(x, y) for y in range(PLAY_R) for x in range(CW)
              if kn[col[y, x]] in OPEN_KINDS and (x, y) not in seen]
    claim("no cell the ball can occupy is cut off from the drain (%d pockets)"
          % len(pocket), not pocket)


# ═════════════════════════════════════════════════════════════ the control
MUTATIONS = {
    "shift-grid": "the collision grid, rolled one cell right",
    "shift-grid-y": "the collision grid, rolled one cell down",
    "recolour-bumper": "bumper U1 painted out to bare board",
    "move-drain": "the centre drain moved to the top of the board",
    "kill-lamp": "lamp 209's pixels replaced with an art colour",
    "plant-key": "one pixel set to index 0, the copy engine's key",
    "swap-flippers": "the two flipper zones swapped",
    "pal-collide": "an art entry set to lamp 0's lit colour",
    "move-actuator": "a drop target's actuator box moved off the switch",
    "fill-slot": "the centre drain slot filled in with copper",
    "open-wall": "one wall cell's ground pour stripped back to bare mask",
}


def mutate(name, st):
    j = st["j"]
    W, H, BLK = j["w"], j["h"], j["blk"]
    pic = np.frombuffer(st["raw"], np.uint8).reshape(H, W).copy()

    def commit():
        st["raw"] = pic.tobytes()
        j["pic_sha256"] = hashlib.sha256(st["raw"]).hexdigest()

    if name == "shift-grid":
        st["col"] = np.roll(st["col"], 1, axis=1)
        st["ident"] = np.roll(st["ident"], 1, axis=1)
    elif name == "shift-grid-y":
        st["col"] = np.roll(st["col"], 1, axis=0)
        st["ident"] = np.roll(st["ident"], 1, axis=0)
    elif name == "recolour-bumper":
        x0, y0, x1, y1 = j["bumpers"][0]["rect"]
        green = max((i for i in range(1, 206)),
                    key=lambda i: int((pic[:j["play_h"]] == i).sum()))
        pic[y0:y1 + 1, x0:x1 + 1] = green
        commit()
    elif name == "move-drain":
        j["drains"][0]["rect"] = [288, 16, 319, 47]
        st["col"][st["col"] == j["kinds"]["drain"]] = j["kinds"]["empty"]
        for y in (1, 2):
            for x in (18, 19):
                st["col"][y, x] = j["kinds"]["drain"]
    elif name == "kill-lamp":
        pic[pic == 209] = 12
        commit()
    elif name == "plant-key":
        pic[200, 300] = 0
        commit()
    elif name == "swap-flippers":
        j["flippers"]["l"], j["flippers"]["r"] = \
            j["flippers"]["r"], j["flippers"]["l"]
    elif name == "pal-collide":
        st["pal"][7] = j["lampon"][0]
        j["pal"] = st["pal"]
        st["palb"] = bytes(bytearray(
            [b for v in st["pal"] for b in (v >> 8, v & 255)]))
        j["pal_sha256"] = hashlib.sha256(st["palb"]).hexdigest()
    elif name == "move-actuator":
        a = j["targets"][0]["actuator"]
        j["targets"][0]["actuator"] = [a[0], a[1] + 14, a[2], a[3] + 14]
    elif name == "fill-slot":
        x0, y0, x1, y1 = j["drain_mouth"]
        gold = max((i for i in range(1, 206)),
                   key=lambda i: int((pic[j["edge"]["y0"]:j["play_h"]] == i).sum()))
        pic[y0 + 4:y1 - 4, x0 + 4:x1 - 4] = gold
        commit()
    elif name == "open-wall":
        # a wall cell in the left apron, scraped back to the plain solder
        # mask of a cell the ball really does fly through.  ⚠ TWO EARLIER
        # VERSIONS OF THIS CONTROL MUTATED NOTHING: the first copied from
        # another APRON cell, which is poured too, and the second scraped a
        # cell that lies under the fab-stamp relief - whose wall evidence is
        # the relief, not the pour, so the claim went on passing for a
        # perfectly good reason.  ⛔ A control that does not change the input
        # reads exactly like a gate that works.
        cx, cy = 3, 18
        patch = pic[2 * BLK:3 * BLK, 17 * BLK:18 * BLK]
        pic[cy * BLK:(cy + 1) * BLK, cx * BLK:(cx + 1) * BLK] = patch
        commit()
    else:
        raise SystemExit("unknown mutation %r" % name)


def main():
    args = sys.argv[1:]
    neg = "--negative" in args
    mut = None
    for i, a in enumerate(args):
        if a == "--mutate":
            mut = args[i + 1]
        elif a.startswith("--mutate="):
            mut = a.split("=", 1)[1]
    if "--list" in args:
        for k, v in MUTATIONS.items():
            print("  %-16s %s" % (k, v))
        return 0

    total = [0, 0]

    def sweep(label, m):
        st = load()
        if m:
            mutate(m, st)
        n = [0, 0]
        fails = []

        def claim(what, ok):
            n[0] += 1
            if not ok:
                n[1] += 1
                fails.append(what)
            if not m:
                print("%s  %s" % ("ok   " if ok else "FAIL ", what))
        run(st, claim)
        if m:
            print("%-17s %-52s %s"
                  % (m, MUTATIONS[m][:52],
                     "CAUGHT (%d of %d claims failed)" % (n[1], n[0])
                     if n[1] else "⛔ NOT CAUGHT"))
            if n[1] and neg:
                print("                  first: %s" % fails[0])
        total[0] += n[0]
        total[1] += n[1]
        return n

    if mut:
        n = sweep(mut, mut)
        return 0 if n[1] else 1

    n = sweep("base", None)
    print("\n%d claims, %d failed" % (n[0], n[1]))
    if not neg:
        return 1 if n[1] else 0

    # ⛔ THE NEGATIVE CONTROL.  A gate that has never been red is not a gate.
    print("\n⛔ the negative control: every mutation must be caught")
    caught = 0
    for m in MUTATIONS:
        r = sweep(m, m)
        caught += 1 if r[1] else 0
    print("\n%d of %d mutations caught" % (caught, len(MUTATIONS)))
    return 0 if (caught == len(MUTATIONS) and n[1] == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
