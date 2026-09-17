#!/usr/bin/env python3
"""session3.py OUT - the VIDEO3 demo session, as the emulator's inputs.

The brief (video3/docs/demo-report.md): boot in 80 x 60 character mode, move to
a 640 x 480 bitmap desktop, a two-pane file manager whose panes are filled by
REAL NitrOS-9 commands, a window dragged by the card's copy engine, the paint
canvas, a CP437 ANSI BBS in 80 x 25, and the game.

⭐ EVERY SCENE IS ORDINARY NITROS-9. The chrome arrives as escape streams that
`copy` sends to a window device, the panes are filled by redirecting `dir` and
`mfree` into them, and the drag is a command that calls SS.Copy. Nothing here
is a bare-metal ROM writing registers.
"""
import math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import vtmodel  # noqa: E402

P = "\x01"          # a second


def pause(s):
    return P * s


# The working areas of the two panes, in cells of the 640 x 480 screen.
# ESC $25 is CWArea: the window's text goes inside that rectangle and scrolls
# there, so a redirected `dir` lands in the pane and nowhere else.
# ⛔ `display` takes HEX. Writing the cell counts as they read in decimal
# gave the left pane 54 x 48 cells instead of 36 x 29 - accepted, because it
# still fitted - and the right pane 42 + 54 > 80, which is E$IWDef. A wrong
# window that fits is worse than one that does not.
PANE_L = "display 1b 25 02 05 24 1d >/w3"     # x 2, y 5, 36 x 29 cells
PANE_R = "display 1b 25 2a 05 24 1d >/w3"     # x 42, same size
FULL   = "display 1b 25 00 00 50 3c >/w3"     # the whole 80 x 60 screen
# ⚠ ESC $32 is the foreground and ESC $33 the BACKGROUND, and text carries
# its background with it: without this the pane's listing arrived as black
# on the desktop's blue, in blocks, over the grey paper the chrome drew.
# 0x02 is CoWin's black, 0xFE the xterm grey the panes are painted in.
PANEINK = "display 1b 32 02 1b 33 fe >/w3"

LINES = [
    # ---- 80 x 60 character mode, which video/ cannot do at all
    ("dir", 2),
    ("iniz w1", 0), ("display 1b 21 >/w1", 1),
    ("shell i=/w1&", 0),
    ("echo now typing on the PS/2 keyboard", 20),
    # ---- the 640 x 480 desktop, and the file manager
    ("iniz w3", 0), ("copy /dd/sys/v3desk /w3", 0), ("display 1b 21 >/w3", 2),
    (PANEINK, 0),
    (PANE_L, 0), ("dir /dd >/w3", 2),
    (PANE_R, 0), ("dir /dd/cmds >/w3", 3),
    (FULL, 0),
    # ---- the window, and the copyrect drag
    ("copy /dd/sys/v3about /w3", 2),
    ("v3drag >/w3", 2),
    # ---- the pointer, on the card's sprite
    ("echo now moving the PS/2 mouse", 12),
    # ---- paint
    ("iniz w4", 0), ("copy /dd/sys/v3paint /w4", 0), ("display 1b 21 >/w4", 4),
    # ---- the BBS: CP437 and ANSI, in 80 x 25 character mode
    ("iniz w2", 0), ("copy /dd/sys/v3bbs /w2", 0), ("display 1b 21 >/w2", 6),
    # ---- the game
    # ⚠ DWEnd ($24), not Select ($21): overworld makes its own window, and
    # /W3 still has the desktop's. Select on a window that exists is fine;
    # a second DWSet on it is E$WADef.
    ("display 1b 24 >/w3", 0), ("overworld >/w3", 1),
    ("display 1b 21 >/w1", 0), ("procs", 3),
    ("echo DONE-arm6309", 0),
]

KBD_GATE = "PS/2 keyboard"
KBD_LINES = ["dir /dd/cmds", "mfree", "echo 80 x 60 CP437 per cell colour >/term"]

MOUSE_GATE = "PS/2 mouse"

CAPTIONS = [
    ("RKBoot", "NitrOS-9 Level 2 boots from ROM onto video3 - four CPLDs, no display list"),
    ("DD:dir", "A shell on the serial port. The console is about to move to the card"),
    ("21 >/w1", "/W1: 80 x 60 CHARACTER MODE - 640x480, 256 CP437 glyphs, colour per cell"),
    ("i=/w1&", "A shell on /W1, typed at on the PS/2 keyboard. It scrolls by COPYRECT"),
    ("v3desk /w3", "/W3: a 640 x 480 desktop. The chrome is escape codes sent by `copy`"),
    ("dir /dd >", "The left pane is a CWArea: the real `dir` command writes into it"),
    ("dir /dd/cmds >", "And the right pane the same - a file manager made of NitrOS-9 commands"),
    ("v3about /w3", "A window, drawn once. Its pixels are now the only copy that exists"),
    ("v3drag >", "v3drag: the card's COPY ENGINE moves it. Seven registers a step, no CPU pixels"),
    ("PS/2 mouse", "The pointer is video3's 8x8 HARDWARE SPRITE - five registers, nothing saved"),
    ("v3paint /w4", "paint: patterns, ellipses, arcs and a 216-colour strip from the xterm cube"),
    ("v3bbs /w2", "/W2: 80 x 25 CP437 ANSI art - the ATTR plane, 16 colours crossed with 16"),
    ("overworld >", "overworld: the game on an exclusive tile screen"),
    ("DD:procs", "procs: both shells still running"),
]


def typed():
    return "".join(cmd + "\r" + pause(s) for cmd, s in LINES).encode()


def keys():
    out = ["w1500"]
    for line in KBD_LINES:
        for ch in line + "\r":
            out.append(vtmodel.scancodes(ch))
            out.append("w90")
        out.append("w3000")
    return " ".join(out)


def mouse():
    """A tour of the 640 x 480 desktop: to the corner, then a figure of eight."""
    out = ["w800"]
    steps = [(-127, 127)] * 8
    x, y = 0.0, 0.0
    px, py = 0, 0
    n = 300
    for i in range(1, n + 1):
        a = 2 * math.pi * i / n
        x, y = 320 + 280 * math.sin(a), 240 - 180 * math.sin(2 * a)
        if i == 1:
            steps.append((int(x), -int(y)))
            px, py = int(x), int(y)
            continue
        dx, dy = int(round(x)) - px, int(round(y)) - py
        px, py = px + dx, py + dy
        steps.append((dx, -dy))
    for dx, dy in steps:
        while dx or dy:
            sx, sy = max(-127, min(127, dx)), max(-127, min(127, dy))
            b0 = 0x08 | (0x10 if sx < 0 else 0) | (0x20 if sy < 0 else 0)
            out.append("%02X %02X %02X" % (b0, sx & 0xFF, sy & 0xFF))
            dx, dy = dx - sx, dy - sy
    return " ".join(out)


if __name__ == "__main__":
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, "typed.txt"), "wb").write(typed())
    open(os.path.join(out, "kbd.txt"), "w").write(keys())
    open(os.path.join(out, "mouse.txt"), "w").write(mouse())
    print("ok    session3: %d lines, %d captions" % (len(LINES), len(CAPTIONS)))
