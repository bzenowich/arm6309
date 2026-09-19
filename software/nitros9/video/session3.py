#!/usr/bin/env python3
"""session3.py OUT - the VIDEO3 demo session, as the emulator's inputs.

The brief (video3/docs/demo-report.md): boot in 80 x 60 character mode, an
ANSI BBS in 80 x 25, a 640 x 480 Haiku desktop whose Tracker windows list the
real ROM disk, a window dragged by the card's copy engine, the pointer on the
card's sprite, Paint with a canvas scrolled by the copy engine, and the game.

⭐ EVERY SCENE IS ORDINARY NITROS-9. The chrome arrives as escape streams that
`copy` sends to a window device - most of them calls into the ROM toolbox -
the Tracker lists are v3trk reading the directories, and the drag and the
scroll are commands that call SS.Copy. Nothing here is a bare-metal ROM
writing registers.
"""
import math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import vtmodel  # noqa: E402

P = "\x01"          # a second


def pause(s):
    return P * s


import v3show                                          # the layout, in one place

T = v3show.T
DCMD = "%d %d" % (T.ICON["folder16"], T.ICON["doc16"])
DAPP = "%d %d" % (T.ICON["folder16"], T.ICON["app16"])

# ⭐ EVERY WINDOW IS SHOWN BEFORE IT IS DRAWN ON.  The streams begin with
# DWSet and Select, so the display blanks, comes back on the new screen,
# and the viewer watches the chrome being drawn - by the ROM toolbox, for
# the desktop and Paint (v3show.py says how).
LINES = [
    # ---- 80 x 60 character mode, which video/ cannot do at all
    ("dir", 2),
    ("iniz w1", 0), ("display 1b 21 >/w1", 1),
    ("shell i=/w1&", 0),
    # the PS/2 keyboard types KBD_LINES on /W1 while this waits: the
    # listing is long enough to scroll the 80 x 60 screen by copyrect
    # ⚠ THE WAIT WAS 46 AND THE KEYBOARD FINISHED AT 37, so the demo sat on a
    # dead screen from 37 s to 64 s.  The changefont commands moved to the
    # PS/2 keyboard (KBD_LINES) - where a user would actually type them, and
    # where they fill what used to be the pause.
    ("echo now typing on the PS/2 keyboard", 20),
    ("echo and changing the console font", 26),
    # ---- the BBS: CP437, gruvbox and 256-colour pairs, 80 x 25
    ("iniz w2", 0), ("copy /dd/sys/v3bbs /w2", 10),
    # ⭐ and then a REAL .ans scrolls through that window: Blocktronics'
    # "we-tortuga", drawn by ca_ext.asm's ANSI terminal itself.  ⚠ The BBS
    # stream turns ANSI off at its end, so it goes back on first.
    # ⚠ and it is SKIPPED when video3/we-tortuga.ans is not there: it is not
    # this project's work, so it is not in the repository (v3show.have_art).
    *([("display 0c >/w2", 0),                      # clear first: a palette load
       ("copy /dd/sys/v3pal /w2", 0),               # recolours what is still up
       ("display 1b 69 01 >/w2", 0), ("copy /dd/sys/v3art /w2", 2)]
      if v3show.have_art() else []),
    # ---- the Haiku desktop, drawn by the ROM toolbox as you watch
    ("iniz w3", 0), ("copy /dd/sys/v3desk /w3", 1),
    ("v3trk " + v3show.TRK_DD.args("/dd") + " " + DCMD + " >/w3", 1),
    ("copy /dd/sys/v3cmds /w3", 0),
    ("v3trk " + v3show.TRK_CMDS.args("/dd/cmds") + " " + DAPP + " >/w3", 2),
    # ---- a window, and the copyrect drag
    ("copy /dd/sys/v3about /w3", 2),
    ("v3drag >/w3", 1),
    # ---- the pointer, on the card's sprite
    ("echo now moving the PS/2 mouse", 17),
    # ---- Paint, on a SCREEN OF ITS OWN: the page painted in front of you,
    # scrolled by copyrect, then a picture opened and dragged round a circle
    ("iniz w4", 0), ("copy /dd/sys/v3paint /w4", 1),
    ("copy /dd/sys/v3draw /w4", 2),
    ("v3scrl >/w4", 2),
    ("copy /dd/sys/v3menu /w4", 2),
    ("copy /dd/sys/v3open /w4", 3),
    ("copy /dd/sys/v3load /w4", 1),
    ("v3grab >/w4", 3),
    # ⭐ and the close box.  ⛔ DWEnd FREES A SCREEN, IT DOES NOT SHOW
    # ANOTHER - ca_scr.asm's ScrFree clears CG.Disp and stops there, so the
    # card keeps whatever pixels were last on it until something draws.  It
    # takes a Select on /W3 to bring the desktop back, and the desktop's
    # pixels have been waiting in its DRAM store all along.
    ("copy /dd/sys/v3shut /w4", 1),
    ("display 1b 24 >/w4", 0), ("display 1b 21 >/w3", 4),
    # ⛔ THE WORD PROCESSOR SCENE IS OUT (2026-09-18).  The wildbits faces
    # are fixed-width, and a word processor is where that shows worst - they
    # look right at the console, which is where changefont now puts them.
    # v3show.py still generates v3fonts, v3write and v3spec, so the scene can
    # come back when there is a way to show PROPORTIONAL text that earns its
    # place.  ⭐ Dropping it also drops the 25 s v3fonts load: GPLoad's data
    # path is a per-byte escape callback at ~2.2 KB/s, and nothing else needs
    # the GP buffers - changefont reads /DD/SYS/FONT.* straight into the
    # glyph bank.
    # ---- the game
    # ⚠ DWEnd ($24), not Select ($21): overworld makes its own window, and
    # /W3 still has the desktop's.  A second DWSet on it is E$WADef.
    ("display 1b 24 >/w3", 0), ("overworld >/w3", 1),
    ("display 1b 21 >/w1", 0), ("procs", 3),
    ("echo DONE-arm6309", 0),
]

KBD_GATE = "PS/2 keyboard"
# ⭐ TYPED ON THE PS/2 KEYBOARD, at the console itself - the shell on /W1 has
# /W1 for its output, so `changefont uncial` needs no redirect.  That is the
# point: the font is changed the way a user would change it.
KBD_LINES = ["dir /dd/cmds", "mfree", "list /dd/sys/video3.txt",
             "echo 80 x 60 CP437 - scrolled by copyrect"] + (
    ["changefont " + f for f in ("uncial", "gothic", "banner", "tech", "cp437")]
    if v3show.FACES else [])

MOUSE_GATE = "PS/2 mouse"

CAPTIONS = [
    ("RKBoot", "NitrOS-9 Level 2 boots from ROM onto video3 - four CPLDs, no display list"),
    ("DD:dir", "A shell on the serial port. The console is about to move to the card"),
    ("21 >/w1", "/W1: 80 x 60 CHARACTER MODE - 640x480, 256 CP437 glyphs, colour per cell"),
    ("i=/w1&", "A shell on /W1, typed at on the PS/2 keyboard"),
    ("PS/2 keyboard", "`list` a long file: every new line moves 59 rows with the COPY ENGINE"),
    *([("changing the console font",
        "changefont, typed at the PS/2 keyboard: the glyph bank, and nothing redrawn")]
      if v3show.FACES else []),
    ("v3bbs /w2", "/W2: 80 x 25 ANSI art in gruvbox - and 256-colour pairs, 38;5 on 48;5"),
    *([("v3art /w2", "a real .ans scrolls by: Blocktronics' we-tortuga, CP437 and iCE colour")]
      if v3show.have_art() else []),
    ("v3desk /w3", "/W3: a Haiku desktop, drawn as you watch by the TOOLBOX IN ROM (page 64)"),
    ("v3trk /dd ", "v3trk: Tracker lists the real /DD - icons and Noto Sans from ROM"),
    ("v3trk /dd/cmds", "... and /DD/CMDS, two columns; the scroll bar knows how much is hidden"),
    ("v3about /w3", "A window, drawn once. Its pixels are now the only copy that exists"),
    ("v3drag >", "v3drag: a FIGURE-8 by copy engine, over a desktop a BACKING STORE keeps"),
    ("PS/2 mouse", "The pointer is video3's 16x16 HARDWARE SPRITE - five registers, nothing saved"),
    ("v3paint /w4", "Paint, on a SCREEN OF ITS OWN - and its page into VRAM's margin, x 640-1023"),
    ("v3draw /w4", "the page painted for you: bars, a pattern fill, two polygons, type, colour"),
    ("v3scrl >", "v3scrl: two copies a step - the view, and the strip - and a copy for each thumb"),
    ("v3menu /w4", "File: the menus are the ROM toolbox's too - bevels, a gradient, Noto Sans"),
    ("v3open /w4", "the Choose File dialog, with the icons and the list a Tracker window uses"),
    ("v3load /w4", "parrot.img opened: into the margin, where the copy engine can reach it"),
    ("v3grab >", "v3grab: the picture dragged round a 50-pixel circle - one copy and two bars"),
    ("v3shut /w4", "the close box - DWEnd, then Select /W3, and the desktop is back"),
    ("overworld >", "overworld: the game on an exclusive tile screen, hero and all"),
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
    """A tour of the 640 x 480 desktop.  It starts where v3drag left the
    pointer (v3show.GRAB - PutGC moves the mouse position too), glides to
    the middle, and draws a figure of eight."""
    out = ["w800"]
    px, py = v3show.GRAB
    path = []
    n = 40
    for i in range(1, n + 1):
        f = (1 - math.cos(math.pi * i / n)) / 2
        path.append((px + (320 - px) * f, py + (240 - py) * f))
    n = 300
    for i in range(1, n + 1):
        a = 2 * math.pi * i / n
        path.append((320 + 280 * math.sin(a), 240 - 180 * math.sin(2 * a)))
    steps = []
    for x, y in path:
        dx, dy = int(round(x)) - px, int(round(y)) - py
        px, py = px + dx, py + dy
        steps.append((dx, -dy))                  # PS/2's y is up
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
