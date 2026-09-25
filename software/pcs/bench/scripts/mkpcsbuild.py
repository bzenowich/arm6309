#!/usr/bin/env python3
"""mkpcsbuild.py - write pcsbuild.ps2: a table built from nothing, the way the
Apple II session in software/pcs/reference/pcs-apple2-editor.mp4 builds one.

`pcs 24` opens the editor on a NEW table - the backdrop and nothing else - and
this script, at the pace a person would work, pulls the parts out of the bin
one by one (every one of them a live drag, so the part is seen following the
pointer), stretches a polygon into the launcher chute's divider with the
pointer, paints, PLAYs the table with the flippers, comes back to the editor,
moves a bumper, and plays again.

⭐ EVERY DROP IS WORKED OUT FROM THE BIN'S OWN GEOMETRY, as checkpcs.py's
ui_model works it out: the part keeps the offset it was grabbed at, so its
corner lands at (release - press) / 2 + the template's own corner.  A script
written by eye puts parts somewhere; this one puts them where the default
table has them.

⭐ IT IS BOTH THE DEMO'S SCRIPT (software/pcs/video/run-build.sh) AND `e1`'s.
The games are played with a scripted hand and are not reproducible to the
frame, and they do not have to be: the checker skips what the mouse does
while a game is up, and PLAY gives the editor its table back exactly as it
was left (pcs.md §8), so every gesture's record, the object area, the span
database and the picture are still the model's to decide.

    python3 software/pcs/bench/scripts/mkpcsbuild.py > .../pcsbuild.ps2
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import mkpcs            # noqa: E402
import pcsparts         # noqa: E402

PARTS = pcsparts.parts()
BOXES = mkpcs.bin_boxes()
NAMES = [p.name for p in PARTS]

# the tool column (card pixels, the icon's middle) and the picker
TOOL = {'hand': (560, 14), 'pointer': (560, 40), 'brush': (560, 116),
        'play': (560, 162)}
PICK = (432, 360)

out = []
t = 1.0


def line(s):
    """⛔ `at` IS ABSOLUTE AND `+` IS NOT, so the clock follows the `+` lines
    too - or the next `at` lands inside the gesture before it (a tool click
    fired in the middle of a 2.2 s vertex drag, which the machine rightly
    took for the drag's release)."""
    global t
    if s.startswith('+'):
        t += float(s.split()[0][1:])
    out.append(s)


def at(dt, s):
    global t
    t += dt
    line('at %-8.3f %s' % (t, s))


def glide(x0, y0, x1, y1, secs=1.0, steps=14):
    """The pointer moved as a hand moves it: a dozen packets, not one."""
    for i in range(1, steps + 1):
        x = x0 + (x1 - x0) * i // steps
        y = y0 + (y1 - y0) * i // steps
        line('+%-8.3f move to %d %d' % (secs / steps, x, y))


def press_drag(x0, y0, x1, y1, pause=3.0, secs=1.2):
    at(pause, 'move to %d %d' % (x0, y0))
    line('+0.300    down left')
    glide(x0, y0, x1, y1, secs)
    line('+0.300    up left')


def click(x, y, pause=2.0):
    at(pause, 'move to %d %d' % (x, y))
    line('+0.300    click left')


def tool(name):
    line('# the %s' % name)
    click(*TOOL[name])


def from_bin(name, tx, ty):
    """Template `name` out of the bin, its corner onto world (tx, ty)."""
    i = NAMES.index(name)
    bx, by, bw, bh = BOXES[i]
    cx, cy = 2 * (bx + bw // 2), 2 * (by + bh // 2)
    wx, wy = cx // 2, cy // 2
    p = PARTS[i]
    rx, ry = 2 * (tx - min(p.x) + wx), 2 * (ty - min(p.y) + wy)
    line('# %s out of the bin, to (%d, %d)' % (name, tx, ty))
    press_drag(cx, cy, rx, ry)


def vertex(x0, y0, x1, y1):
    """The pointer on the vertex at world (x0, y0), dragged to (x1, y1)."""
    line('# the vertex at (%d, %d) to (%d, %d)' % (x0, y0, x1, y1))
    press_drag(2 * x0, 2 * y0, 2 * x1, 2 * y1, secs=1.6)


def pick(col, row):
    click(PICK[0] + 8 * col + 4, PICK[1] + 8 * row + 4)


def play(secs, launch=True):
    """PLAY: the pointer's Y is the plunger's pull and the left button lets go
    of it (pcs.md, status.md §4); both buttons are the flippers.  ⚠ The hand
    is taken first: were the game to end on its own, a flipper click that
    reached the editor would be a hand's empty click and not a brush's paint."""
    tool('hand')
    tool('play')
    if launch:
        at(0.5, 'move to 300 150')           # the plunger at rest ...
        glide(300, 150, 300, 420, 0.8)       # ... pulled down ...
        # ⛔ HELD, AND THROUGH THE BOUNCES: LAUNCHHIT fires only on a frame
        # where the button is down AND the ball is touching the plunger
        # (pcsobj.py), and a ball dropped onto it bounces for a second or two
        # before it settles - a half-second press missed every contact, and
        # the ball walked off the plunger's edge.  Held, the plunger stays at
        # rest and the first touch is the shot, at PDL0 >> 2.
        line('+0.200    down left')
        line('+3.500    up left')
    n = int(secs / 1.2)
    for k in range(n):
        b = ('left', 'right')[k % 2]
        at(0.9, 'down %s' % b)
        line('+0.300    up %s' % b)
    at(1.0, 'type "q"')


line('# pcsbuild.ps2 - a table built from nothing at the editor (`pcs 24`), the')
line('# way the Apple II session in reference/pcs-apple2-editor.mp4 builds one.')
line('# GENERATED by mkpcsbuild.py - edit that, not this.')
line('# ⚠ `origin 0 0`: that is where the pointer is when pcs starts.')
line('origin 0 0')
line('gap 120')
line('')

# the flippers first, as the Apple II session does, then the slingshots
from_bin('LEFTFLIPPER', 26, 206)
from_bin('RIGHTFLIPPER', 82, 206)
from_bin('LKICK', 12, 160)
from_bin('RKICK', 100, 160)
# the launcher's chute: a bin polygon stretched into a divider with the pointer
from_bin('POLY1', 128, 40)
tool('pointer')
vertex(128, 57, 128, 232)
vertex(129, 57, 134, 232)
vertex(128, 40, 128, 30)
vertex(129, 40, 134, 30)
tool('hand')
from_bin('LAUNCHER', 140, 210)
from_bin('BALL', 140, 190)
# the playfield
for name, x, y in (('BMP1', 36, 66), ('BMP2', 78, 58), ('BMP5', 56, 90),
                   ('ROLL1', 32, 28), ('ROLL2', 60, 24), ('ROLL3', 88, 28),
                   ('TARG4', 88, 94), ('TARG5', 94, 94), ('TARG6', 100, 94)):
    from_bin(name, x, y)
# paint: the walls and the divider
tool('brush')
pick(3, 2)
click(2 * 4, 2 * 120)                        # the wall - a SELECTPOLY miss
pick(9, 5)
click(2 * 131, 2 * 150)                      # the divider
play(14)
# back in the editor: a bumper moved, live
line('# BMP5 dragged across the table')
press_drag(2 * 62, 2 * 96, 2 * 92, 2 * 130, secs=2.0)
play(10)
at(3.0, 'type "q"')
print('\n'.join(out))
