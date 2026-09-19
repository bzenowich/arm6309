#!/usr/bin/env python3
"""mklegs.py - a path turned into an fcb table of steps.

    python3 video3/bench/mklegs.py 186 194 175 195 emit   v3drag's figure-8
    python3 video3/bench/mklegs.py circle 25 56 emit      v3grab's circle

⭐ EIGHT-WAY, NOT FOUR.  The copy engine moves a rectangle from anywhere to
anywhere - CP.DX and CP.DY are independent - so a diagonal step is one copy
exactly like an axis-aligned one, and there was never a reason for the path
to climb in stairs.  Each run is `count, dx, dy` with dx and dy signed and in
{-STEP, 0, +STEP}.

⚠ What a diagonal step costs is in Vacate, not in the move: the region the
window no longer covers is an L rather than a strip, so it is two rectangles
instead of one (plus the tab's own edge, which is the same story again).
"""
import math
import os
import sys

N = int(os.environ.get("N", 300))               # samples, as the pointer uses
WINW, WINH = 250, 99
HOME = (96, 373)


def path(A, CX, B, CY, n=None):
    """⭐ THE POINTER'S OWN FIGURE-8, scaled to where the window may go.
    session3.py's mouse tour is x = 320 + 280 sin a, y = 240 - 180 sin 2a over
    N samples; this is the same curve and the same sampling, with the centre
    and the amplitudes moved so the window's TOP-LEFT stays on screen and
    inside the backing region's reach.  A run in from the window's home and
    back out again, eased, so it does not start with a jerk."""
    n = n or N
    out = [HOME]
    ease = 24
    first = (CX, CY - 0.0)
    for i in range(1, ease + 1):                 # home -> the curve's start
        f = (1 - math.cos(math.pi * i / ease)) / 2
        out.append((HOME[0] + (first[0] - HOME[0]) * f,
                    HOME[1] + (first[1] - HOME[1]) * f))
    for i in range(1, n + 1):
        a = 2 * math.pi * i / n
        out.append((CX + A * math.sin(a), CY - B * math.sin(2 * a)))
    for i in range(1, ease + 1):                 # and back home
        f = (1 - math.cos(math.pi * i / ease)) / 2
        out.append((first[0] + (HOME[0] - first[0]) * f,
                    first[1] + (HOME[1] - first[1]) * f))
    return out


def runs(pts):
    """The DELTA between consecutive samples, one step each.

    ⭐ NOT QUANTISED TO A GRID.  An earlier version rounded every point to a
    STEP-pixel lattice and walked to it, which is what made the drag climb in
    stairs: on a shallow slope the lattice turns a gentle curve into runs of
    horizontal steps with an occasional diagonal.  The pointer's figure-8 in
    session3.py looks smooth because it samples the curve 300 times and moves
    by whatever the difference is - 1 to 5 pixels, in both axes at once - and
    this now does the same.

    ⚠ Nothing in the driver had to change for it: Vacate already takes dxs
    and dys as VALUES, not as a fixed Step, so an arbitrary delta restores the
    right strips.  ⚠ A delta must fit a signed byte."""
    cur = (round(pts[0][0]), round(pts[0][1]))
    out, xs, ys = [], [cur[0]], [cur[1]]
    for x, y in pts[1:]:
        gx, gy = round(x), round(y)
        dx, dy = gx - cur[0], gy - cur[1]
        if not dx and not dy:
            continue
        assert -128 <= dx <= 127 and -128 <= dy <= 127, (dx, dy)
        cur = (gx, gy)
        if out and out[-1][0] == (dx, dy) and out[-1][1] < 255:
            out[-1][1] += 1
        else:
            out.append([(dx, dy), 1])
        xs.append(cur[0])
        ys.append(cur[1])
    return out, xs, ys


def circle(R, n):
    """⭐ A CIRCLE OF DIAMETER 2R, STARTING AND ENDING WHERE IT BEGAN.
    The picture's rest place is the circle's CENTRE, so the path eases out to
    the rim, goes round once, and eases back - which is what "drag it in a
    circle and put it back" looks like when a hand does it, and what makes
    the last step land exactly on the first."""
    ease = 10
    out = [(0.0, 0.0)]
    for i in range(1, ease + 1):
        f = (1 - math.cos(math.pi * i / ease)) / 2
        out.append((R * f, 0.0))
    for i in range(1, n + 1):
        a = 2 * math.pi * i / n
        out.append((R * math.cos(a), R * math.sin(a)))
    for i in range(1, ease + 1):
        f = (1 - math.cos(math.pi * i / ease)) / 2
        out.append((R * (1 - f), 0.0))
    return out


def emit_circle():
    R, n = int(sys.argv[2]), int(sys.argv[3])
    r, xs, ys = runs(circle(R, n))
    steps = sum(k for _, k in r)
    mx = max(max(abs(dx), abs(dy)) for (dx, dy), _ in r)
    sys.stderr.write("R=%d n=%d -> %d steps, %d runs, longest %d px, "
                     "x %d..%d y %d..%d, ends at (%d, %d)\n"
                     % (R, n, steps, len(r), mx, min(xs), max(xs), min(ys), max(ys),
                        xs[-1], ys[-1]))
    assert (xs[-1], ys[-1]) == (0, 0), "the circle must come home"
    if len(sys.argv) <= 4:
        return
    print("* ⭐ A CIRCLE OF DIAMETER %d, as runs of equal steps: count, dx, dy."
          % (2 * R))
    print("* The rest place is the CENTRE, so the path eases out to the rim, goes")
    print("* round once in %d samples and eases back - %d steps, longest %d px, and"
          % (n, steps, mx))
    print("* the last one lands exactly on the first.  Generated by")
    print("* video3/bench/mklegs.py circle %d %d emit." % (R, n))
    print("*")
    print("* ⚠ CMax is what bounds the white the drag has to put back: a step")
    print("* vacates at most CMax columns and CMax rows of the page.")
    print("CMax                equ       %d" % mx)
    print("Circle              equ       *")
    for (dx, dy), k in r:
        print("                    fcb       %d,%d,%d" % (k, dx & 255, dy & 255))
    print("                    fcb       0         the end: a count of none")


def main():
    if sys.argv[1] == "circle":
        return emit_circle()
    A, CX, B, CY = (int(v) for v in sys.argv[1:5])
    r, xs, ys = runs(path(A, CX, B, CY))
    n = sum(k for _, k in r)
    diag = sum(k for (dx, dy), k in r if dx and dy)
    mx = max(max(abs(dx), abs(dy)) for (dx, dy), _ in r)
    sys.stderr.write("A=%d CX=%d B=%d CY=%d -> %d steps (%d diagonal, %d%%), %d runs, "
                     "longest step %d px\n"
                     % (A, CX, B, CY, n, diag, 100 * diag // n, len(r), mx))
    sys.stderr.write("   x %d..%d (right edge %d)   y %d..%d (bottom %d)\n"
                     % (min(xs), max(xs), max(xs) + WINW,
                        min(ys), max(ys), max(ys) + WINH))
    if len(sys.argv) <= 5:
        return
    print("* ⭐ A FIGURE-8, as runs of equal steps: count, dx, dy - EIGHT-WAY,")
    print("* so the window moves diagonally where the curve does instead of")
    print("* climbing in stairs.  x = %d + %d sin t, y = %d + %d sin 2t on a"
          % (CX, A, CY, B))
    print("* curve sampled %d times, from the window's home at (%d, %d) and back."
          % (N, HOME[0], HOME[1]))
    print("* %d steps, %d of them diagonal.  Generated by video3/bench/mklegs.py."
          % (n, diag))
    print("*")
    print("* ⚠ x reaches %d, so the right edge reaches %d and the window stays ON"
          % (max(xs), max(xs) + WINW))
    print("* SCREEN - which is what leaves the off-screen margin free for the")
    print("* backing store (SWX, SBX).  They cannot both have it.")
    print("* ⚠ y reaches %d, so the bottom reaches %d, clear of the staging rows"
          % (max(ys), max(ys) + WINH))
    print("* vidcpy3.asm uses from 480.")
    print("*")
    print("* \u26d4 MaxStep IS GENERATED, and InB's margin depends on it.  InB re-bases")
    print("* the backing region while the window is still inside it, because NewB")
    print("* takes the hole out of the OLD store - so its margin must be at least")
    print("* the LONGEST step this path takes.  A hand-written 8 against a path")
    print("* whose longest delta is 12 let the window overshoot the region by 4,")
    print("* and the hole came back as garbage: black lines beside the tab, first")
    print("* flickering and then stuck.")
    print("MaxStep             equ       %d" % mx)
    print("Legs                equ       *")
    for (dx, dy), k in r:
        print("                    fcb       %d,%d,%d" % (k, dx & 255, dy & 255))
    print("                    fcb       0         the end: a count of none")


if __name__ == "__main__":
    main()
