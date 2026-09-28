"""walkcast.py - `tilescroll`'s actors for the SPRITE WALKER: seven kinds, six
sizes, and every one of them animated its own way.

⭐ WHY A NEW CAST.  The walker (hardware/video3/docs/plan.md §6.4) takes each
slot's rectangle from a DIM table the card holds, so an actor is no longer a
32 x 32 bank tile - it is whatever size its art is, and a small one costs
proportionally less of the blank.  This file is the art and the one table the
program and the bench share about it:

    kind       size     shapes   animation
    hero       16 x 16    8      a two-step walk in the direction of travel
    slime      16 x 16    3      squash and stretch, bottom-anchored
    bird       24 x 16    3      wings up, level, down, level
    butterfly  12 x 12    3      wings open, half, edge-on, half
    firefly     8 x  8    3      a glow that swells and fades
    gem         8 x 12    3      a crystal turning on its axis
    bat        16 x  8    3      a fast flap

⭐ A CREATURE'S CYCLE IS FOUR FRAMES AND THREE SHAPES: the fourth frame is the
second again (level, half, ...), so it is drawn from the same shape and
tilescroll's CastMv plays 0, 1, 2, 1.  That is 26 shapes of the walker's 32,
in two bank columns of 32 x 32 cells; 26-30 are empty and ⭐ SHAPE 31 IS THE
WALKER'S "NO SHAPE" (plan.md §6.4) - a record carrying it is skipped, which is
how a parked actor costs nothing.  Each shape sits in the TOP-LEFT of its
cell; the rest of the cell is the key.

⛔ INDEX 0 IS THE KEY AND NOTHING DRAWN MAY BE 0 - `c332` lifts a colour that
quantises to it, exactly as cast.py's does.
"""
import numpy as np

import cast as Z

KEY = 0x00
c332 = Z.c332

# kind: 0 the hero (the camera's), 1 walks the ground, 2 flies to the TOP of
# the view - which is what puts actors in the rows the beam reaches first, and
# so what the tearing measurement is about.
#          name        w   h  speed step kind
KINDS = [("hero",     16, 16,   0, 0x00, 0),
         ("slime",    16, 16,   6, 0x60, 1),
         ("bird",     24, 16,  16, 0xFF, 2),
         ("butterfly", 12, 12, 12, 0x90, 2),
         ("firefly",   8,  8,   5, 0x50, 1),
         ("gem",       8, 12,   9, 0x40, 1),
         ("bat",      16,  8,  21, 0xFF, 2)]
NSHAPE = 32          # the walker's SHAPE field; the cells are all of it
NULL = 31            # ... and this one is "no shape": never drawn
NFRAME = 3           # unique shapes a creature, played 0, 1, 2, 1


def _new(w, h):
    return np.full((h, w), KEY, np.uint8)


def _ellipse(a, cx, cy, rx, ry, col):
    h, w = a.shape
    yy, xx = np.mgrid[0:h, 0:w]
    m = ((xx + 0.5 - cx) / rx) ** 2 + ((yy + 0.5 - cy) / ry) ** 2 <= 1.0
    a[m] = col
    return m


def _poly(a, pts, col):
    """Fill a convex-or-not polygon by the even-odd rule at pixel centres."""
    h, w = a.shape
    for y in range(h):
        for x in range(w):
            px, py, inside = x + 0.5, y + 0.5, False
            for i in range(len(pts)):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % len(pts)]
                if (y1 > py) != (y2 > py):
                    if px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
                        inside = not inside
            if inside:
                a[y, x] = col


def slime():
    out = []
    dark, body, lit, eye = (c332(20, 90, 30), c332(60, 190, 70),
                            c332(180, 255, 170), c332(20, 20, 40))
    for rx, ry in ((7.5, 5.0), (7.0, 6.0), (6.0, 7.5), (7.0, 6.0)):
        a = _new(16, 16)
        cy = 16 - ry
        _ellipse(a, 8, cy, rx, ry, dark)
        _ellipse(a, 8, cy + 0.4, rx - 1, ry - 1, body)
        _ellipse(a, 8 - rx * 0.4, cy - ry * 0.45, 1.6, 1.2, lit)
        ey = int(cy - ry * 0.1)
        a[ey, int(8 - rx * 0.35)] = eye
        a[ey, int(8 + rx * 0.35)] = eye
        out.append(a)
    return out


def bird():
    out = []
    body, dark, wing, beak, eye = (c332(70, 110, 230), c332(30, 40, 120),
                                   c332(150, 190, 255), c332(250, 170, 40),
                                   c332(255, 255, 255))
    # the wing tip's height above the body line: up, level, down, level
    for tip in (-7, 0, 6, 0):
        a = _new(24, 16)
        _poly(a, [(7, 8), (17, 8), (12 - 3, 8 + tip - 1), (4, 8 + tip)], wing)
        _poly(a, [(7, 8), (17, 8), (20, 8 + tip), (15, 8 + tip - 1)], wing)
        _ellipse(a, 12, 9, 6.5, 3.2, dark)
        _ellipse(a, 12, 8.6, 5.5, 2.4, body)
        _poly(a, [(18, 7.5), (23, 8.8), (18, 10)], beak)
        a[8, 16] = eye
        out.append(a)
    return out


def butterfly():
    out = []
    o1, o2, blk, bod = (c332(255, 140, 20), c332(255, 220, 90),
                        c332(25, 20, 20), c332(90, 60, 40))
    for sx in (1.0, 0.6, 0.15, 0.6):
        a = _new(12, 12)
        for side in (-1, 1):
            wx = 6 + side * 3.2 * sx
            _ellipse(a, wx, 4.2, max(0.6, 2.8 * sx), 3.4, blk)
            _ellipse(a, wx, 4.2, max(0.5, 2.0 * sx), 2.5, o1)
            _ellipse(a, 6 + side * 2.4 * sx, 8.6, max(0.5, 2.0 * sx), 2.2, o2)
        a[2:11, 5:7] = bod
        out.append(a)
    return out


def firefly():
    out = []
    glow = [c332(90, 110, 20), c332(200, 220, 60), c332(255, 255, 160)]
    core = c332(40, 60, 20)
    for r in (1.6, 2.6, 3.8, 2.6):
        a = _new(8, 8)
        _ellipse(a, 4, 4, r, r, glow[0])
        _ellipse(a, 4, 4, r * 0.72, r * 0.72, glow[1])
        _ellipse(a, 4, 4, r * 0.42, r * 0.42, glow[2])
        a[3:5, 3:5] = np.where(a[3:5, 3:5] == KEY, core, a[3:5, 3:5])
        out.append(a)
    return out


def gem():
    out = []
    edge, faceA, faceB, shine = (c332(40, 20, 120), c332(210, 60, 230),
                                 c332(110, 40, 200), c332(255, 230, 255))
    for half, shade in ((4.0, 0), (2.8, 1), (0.9, 0), (2.8, 1)):
        a = _new(8, 12)
        _poly(a, [(4, 0), (4 + half, 4), (4, 12), (4 - half, 4)], edge)
        inner = max(0.5, half - 1)
        _poly(a, [(4, 1.2), (4 + inner, 4), (4, 10.8), (4 - inner, 4)],
              faceA if shade == 0 else faceB)
        if half > 2:
            _poly(a, [(4, 1.2), (4 + inner, 4), (4, 5)], faceB if shade == 0 else faceA)
        a[3, 3 if half > 1 else 4] = shine
        out.append(a)
    return out


def bat():
    out = []
    body, wing, eye = c332(90, 40, 110), c332(50, 20, 70), c332(255, 60, 60)
    for tip in (-4, 0, 3, 0):
        a = _new(16, 8)
        _poly(a, [(6, 4), (1, 4 + tip), (0, 5 + tip), (3, 5 + tip), (6, 6)], wing)
        _poly(a, [(10, 4), (15, 4 + tip), (16, 5 + tip), (13, 5 + tip), (10, 6)], wing)
        _ellipse(a, 8, 4.6, 2.6, 2.4, body)
        a[3, 6] = body
        a[3, 9] = body
        a[4, 7] = eye
        a[4, 8] = eye
        out.append(a)
    return out


def shapes():
    """The shapes in SHAPE order, and the kinds' first shape each.  Each
    creature's fourth frame must BE its second - that is what lets it be
    dropped - and this asserts it rather than trusting the drawing code."""
    out = list(Z.hero_art())
    first = [0]
    for f in (slime, bird, butterfly, firefly, gem, bat):
        first.append(len(out))
        fr = f()
        assert len(fr) == 4 and (fr[3] == fr[1]).all(), f.__name__
        out += fr[:NFRAME]
    assert len(out) <= NULL, len(out)
    for (name, w, h, *_), s0 in zip(KINDS, first):
        for k in range(NFRAME if name != "hero" else 8):
            a = out[s0 + k]
            assert a.shape == (h, w), (name, k, a.shape)
            assert (a == KEY).any() and (a != KEY).any(), (name, k)
    return out, first


def cells():
    """Each shape in the top-left of a 32 x 32 cell, the rest keyed; the
    cells past the last shape - and so NULL's - are all key."""
    sh, _ = shapes()
    out = []
    for a in sh:
        c = np.full((32, 32), KEY, np.uint8)
        c[:a.shape[0], :a.shape[1]] = a
        out.append(c)
    while len(out) < NSHAPE:
        out.append(np.full((32, 32), KEY, np.uint8))
    return out


def walk_cost(w, h):
    """⭐ The walker's time for one actor, in dots: three copies (restore,
    save, draw), each 25 dots of loads and waits plus the engine's 6.216 dots a
    byte and 17 a row end - v3card_tb's measurement, and the emulator's."""
    return 3 * (25 + h * (w * 246913 / 39722 + 17))
