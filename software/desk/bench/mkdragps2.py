#!/usr/bin/env python3
"""mkdragps2.py - the figure-8 window drag, as a PS/2 script.

    python3 software/desk/bench/mkdragps2.py > software/desk/bench/scripts/drag.ps2
    SESSION=1 python3 software/desk/bench/mkdragps2.py     the whole demo session

⭐ THE GEOMETRY IS PARSED OUT OF desk.asm, exactly as checkdesk.py and
checkfiles.py parse it: the travel box the drag is clamped to (FM.MNX,
FM.MXX, FM.MNY, FM.MXY) and the window's own FM.X / FM.Y / FM.TABH are read
from the module that enforces them, so a change there moves this script with
it rather than leaving it pointing at empty desktop.

⛔ THE SAMPLE INTERVAL IS THE WINDOW'S STEP TIME, NOT A FRAME RATE.  One drag
step is one SS.Copy of the window's bounding box - 420 x 279 = 117,180 bytes
at the engine's 725 us fixed + 0.247 us a byte, which is 29.7 ms when the
step moves up or left and ~71 ms when it moves down or right and vidcpy3.asm
has to stage it through the off-screen rows - plus the loop's own F$Sleep 1.
So a pass is 50-90 ms.  ⚠ Sampling FASTER than that does not make the drag
smoother: `desk` chases the pointer's ABSOLUTE position, so the window simply
falls behind and the pointer visibly detaches from the tab it is holding.
STEP_MS is set to the slow end of a pass on purpose - the two stay together,
and the honest result is a ~11 fps drag, which is what this machine does.
"""
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DESKASM = os.environ.get(
    "DESKASM",
    os.path.join(HERE, "..", "..", "..", "..", "nitros9", "level2", "arm6309", "cmds", "desk.asm"))

STEP_MS = int(os.environ.get("STEP_MS", 90))
N = int(os.environ.get("N", 132))            # samples round the figure-8
EASE = int(os.environ.get("EASE", 16))       # in from home, and back out


def equates(path):
    """Every `X equ <expression>` desk.asm declares, resolved in order -
    the same discipline checkfiles.py uses, and for the same reason."""
    S = {}
    txt = open(path, encoding="utf-8", errors="replace").read()
    for m in re.finditer(r"^([A-Za-z][\w.]*)\s+equ\s+(\S+)", txt, re.M):
        name, expr = m.group(1), m.group(2)
        try:
            S[name] = int(eval(re.sub(r"[A-Za-z][\w.]*",
                                      lambda k: str(S[k.group(0)]), expr)))
        except Exception:
            pass                              # not an arithmetic equate
    return S


S = equates(DESKASM)
for k in ("FM.X", "FM.Y", "FM.W", "FM.H", "FM.TABH",
          "FM.MNX", "FM.MXX", "FM.MNY", "FM.MXY", "GEO.ORGX", "GEO.ORGY"):
    if k not in S:
        sys.exit("FAIL  mkdragps2: desk.asm has no %s equate" % k)

HOMEX, HOMEY = S["FM.X"], S["FM.Y"] - S["FM.TABH"]        # the box, at home
MNX, MXX, MNY, MXY = S["FM.MNX"], S["FM.MXX"], S["FM.MNY"], S["FM.MXY"]

# ⚠ WHERE THE POINTER HOLDS THE TAB, and it has to be ON the drawn tab and
# not merely in desk's grab band.  tbox.asm's TWin makes the tab as wide as
# its bold title plus 52, and the shortest title this session ever shows is
# "/SD0" - so 60 in from the corner is inside the tab for every path the
# manager can be on, and 9 down is its middle row.  desk.asm's ⚠ on the band
# says why the band itself is wider than this.
GRABX, GRABY = 60, 9

CX, CY = (MNX + MXX) // 2, (MNY + MXY) // 2
A, B = (MXX - MNX) // 2, (MXY - MNY) // 2


def figure8():
    """⭐ THE SAME CURVE v3drag AND session3.py DRAW, scaled to the travel
    box: x = CX + A sin a, y = CY - B sin 2a.  Eased in from the window's
    home and back out to it with a raised cosine, so the drag neither starts
    nor stops with a jerk - mklegs.py's path() does exactly this for the
    canned version, and this is the live one."""
    pts = [(HOMEX, HOMEY)]
    first = (CX, CY)
    for i in range(1, EASE + 1):
        f = (1 - math.cos(math.pi * i / EASE)) / 2
        pts.append((HOMEX + (first[0] - HOMEX) * f, HOMEY + (first[1] - HOMEY) * f))
    for i in range(1, N + 1):
        a = 2 * math.pi * i / N
        pts.append((CX + A * math.sin(a), CY - B * math.sin(2 * a)))
    for i in range(1, EASE + 1):
        f = (1 - math.cos(math.pi * i / EASE)) / 2
        pts.append((first[0] + (HOMEX - first[0]) * f, first[1] + (HOMEY - first[1]) * f))
    return pts


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def emit(out, t0, control=False):
    """The drag, as timed `move to` lines.  Returns the time it ends.

    ⛔ CONTROL=1 EMITS THE SAME PATH AND NEVER PRESSES.  It is the other half
    of the claim: a desktop that ran a canned curve on a timer would move the
    window for the driven run just as convincingly, and this is the run in
    which it must NOT move.  The pointer still crosses the tab - hovering is
    not what moves a window - so a shell that dragged on hover fails here."""
    pts = figure8()
    if control:
        out.append("# --- ⛔ THE CONTROL: the same path, and the button is never pressed ----")
        out.append("at %-9.3f move to %d %d" % (t0, HOMEX + GRABX, HOMEY + GRABY))
    else:
        out.append("# --- the grab: press ON the tab and hold -------------------------------")
        out.append("at %-9.3f move to %d %d" % (t0, HOMEX + GRABX, HOMEY + GRABY))
        out.append("+0.600      down left       # ⭐ DESK-GRAB: held, not clicked")
    out.append("")
    out.append("# --- the figure-8: %d samples %d ms apart ---------------------------" %
               (len(pts) - 1, STEP_MS))
    t = t0 + 0.600
    last = None
    for x, y in pts[1:]:
        bx = clamp(int(round(x)), MNX, MXX)
        by = clamp(int(round(y)), MNY, MXY)
        px, py = bx + GRABX, by + GRABY
        t += STEP_MS / 1000.0
        if (px, py) == last:                  # a sample the rounding repeats
            continue
        out.append("at %-9.3f move to %d %d" % (t, px, py))
        last = (px, py)
    t += 0.400
    out.append("")
    if control:
        out.append("# ⛔ and NO `up left`, because there was no `down left`.")
    else:
        out.append("# --- and the drop -----------------------------------------------------")
        out.append("at %-9.3f up left         # ⭐ DESK-DROP, at the window's home" % t)
    return t


HEAD = """# drag.ps2 - GENERATED by software/desk/bench/mkdragps2.py.  Do not edit: the
# travel box and the window's corner are parsed out of desk.asm's own
# equates, so editing this file is how the two drift apart.
#
# ⭐ SCREEN COORDINATES, Y DOWN (software/emu/ps2script.h).  Time zero
# is PS2_SCRIPT_GATE: the moment `desk` has printed DESK-READY.
#
# ⚠ `origin` MUST BE desk.asm's GEO.ORGX/GEO.ORGY - desk issues one PutGC at
# start-up and never another, so this is where the machine's mouse really is.
origin %(ORGX)d %(ORGY)d
gap 120
"""

SESSION = """
# --- 1  the `home` icon: one click selects, a second opens the manager --
# ⭐ /DD, THE ROM DISK - not the card.  /DD/CMDS is NitrOS-9's own command
# set, ~60 modules, and it is the only directory on this machine long enough
# to fill the manager's twelve rows and give its scroll bar something to do.
# ⛔ FOUR AND A HALF SECONDS BETWEEN CLICKS, and it is measured, not slack:
# desk samples the button once a pass and a pass that repaints twelve rows
# is 2.09 s, so a 120 ms click inside one is not slow - it is GONE
# (desk.asm's header; software/desk/docs/boot-and-desktop.md item 7).
at 2.000    move to 30 148
+0.700      click left      # C0: selects home, and must NOT open it
+0.500      move to 580 300
at 12.000   move to 30 148
+0.700      click left      # C1: ⭐ the manager comes up on /DD
+0.500      move to 580 300

# --- 2  into CMDS, which is row 1 of /DD --------------------------------
# ⚠ ROW 1, NOT ROW 0.  /DD's own order is OS9Boot, CMDS, MODULES, SYS,
# startup - OS9Boot is the bootfile and it is row 0.  Row i is at
# FM.LY + i*FM.ROWH + 9, so row 1 is y = 209.
at 24.000   move to 200 209
+0.700      click left      # C2: selects CMDS
+0.500      move to 580 300
at 34.000   move to 200 209
+0.700      click left      # C3: ⭐ enters it - twelve rows of real commands,
#                             and the listing the drag carries round the 8
+0.500      move to 580 300
"""

TAIL = """
# --- quit, once the window is back where it started ---------------------
at %(QUIT).3f   move to 30 8
+0.700      click left
+0.900      move to 60 52
+0.700      click left      # Quit
"""


def main():
    out = []
    out.append(HEAD % {"ORGX": S["GEO.ORGX"], "ORGY": S["GEO.ORGY"]})
    control = bool(os.environ.get("CONTROL"))
    session = os.environ.get("SESSION")
    if session:
        out.append(SESSION)
        t0 = 46.0                             # after C3's full DrawFiles
    else:
        t0 = 2.0
    t = emit(out, t0, control)
    if session:
        out.append(TAIL % {"QUIT": t + 3.0})
    sys.stdout.write("\n".join(out) + "\n")


main()
