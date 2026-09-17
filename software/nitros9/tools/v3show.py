#!/usr/bin/env python3
"""v3show.py OUT - the video3 demo's byte streams, into OUT/.

Each file is a stream of CoWin/CoArm escapes that a NitrOS-9 `copy` sends to
a window device, so the demo is driven by ordinary NitrOS-9 commands and file
I/O rather than by a bare-metal ROM: the shell opens the window, copies the
chrome in, and then redirects REAL command output (dir, mfree, procs) into the
panes.  video3/docs/demo-report.md 4 says why that shape was chosen.

Files:
  v3desk    640 x 480 desktop: menu bar, two file-manager panes, a window
  v3about   the draggable window's contents
  v3paint   the paint canvas
  v3bbs     CP437 ANSI art for an 80 x 25 character screen
"""
import sys, os, pathlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vgmodel import esc, w16, xy                      # the same builders the model uses

# ---------------------------------------------------------------- colours
# CoWin's eight, twice, at 0-15 (ca_scr.asm PalDef), then xterm's 6x6x6 cube
# at 16-231 and greys at 232-255.  The cube is what makes a desktop look like
# anything: CoWin's eight are saturated primaries.
WHITE, BLUE, BLACK, GREEN, RED, YELLOW, MAGENTA, CYAN = range(8)
def cube(r, g, b):      return 16 + 36 * r + 6 * g + b
def grey(n):            return 232 + n                 # 0-23, black to white
DESK    = cube(1, 1, 3)      # a deep slate blue
BAR     = grey(18)           # the menu bar
BARSH   = grey(10)           # its shadow
PANE    = grey(22)           # a pane's paper
PANEHD  = cube(2, 3, 4)      # a pane's title bar
INK     = BLACK
ACCENT  = cube(5, 3, 0)      # amber

W, H = 80, 60                # cells of a 640 x 480 screen


def _win(sty, x, y, w, h, fg, bg):
    return esc(0x20, sty, x, y, w, h, fg, bg, bg)

def _bar(col, x0, y0, x1, y1):
    """a filled rectangle in PIXELS"""
    return esc(0x32, col) + esc(0x40, w16(x0), w16(y0)) + esc(0x4A, w16(x1), w16(y1))

def _box(col, x0, y0, x1, y1):
    return esc(0x32, col) + esc(0x40, w16(x0), w16(y0)) + esc(0x48, w16(x1), w16(y1))

def _at(x, y):
    return xy(x, y)


def _frame(x, y, w, h, title, hd=PANEHD):
    """a pane: shadow, paper, title bar, border.  x/y/w/h in CELLS."""
    px, py, pw, ph = x * 8, y * 8, w * 8, h * 8
    s = bytearray()
    s += _bar(grey(4), px + 4, py + 4, px + pw + 3, py + ph + 3)      # drop shadow
    s += _bar(PANE, px, py, px + pw - 1, py + ph - 1)                 # paper
    s += _bar(hd, px, py, px + pw - 1, py + 11)                       # title bar
    s += _box(grey(8), px, py, px + pw - 1, py + ph - 1)              # border
    s += esc(0x32, WHITE) + _at(x + 1, y) + esc(0x3C, 1) + title.encode("latin-1") + esc(0x3C, 0)
    return bytes(s)


def stream_desk():
    """The desktop.  ⭐ The two panes are CWArea working areas, so the shell can
    redirect `dir` straight into them - the file manager lists what is really
    on the ROM disk, through ordinary NitrOS-9 file I/O."""
    s = bytearray()
    s += _win(0x13, 0, 0, W, H, WHITE, DESK)          # 640 x 480, VMODE 11
    # menu bar
    s += _bar(BAR, 0, 0, 639, 15)
    s += _bar(BARSH, 0, 16, 639, 17)
    s += esc(0x32, INK) + _at(1, 0) + esc(0x3C, 1)
    s += b"arm6309   File   View   Window   Help"
    s += _at(60, 0) + b"video3  640x480x8"
    s += esc(0x3C, 0)
    # the two file-manager panes
    # ⚠ 32 cells tall, not 40: the drag below needs clear desktop to cross.
    # A drag has no backing store - the window's pixels ARE the only copy -
    # so the strip it vacates is repainted in the desktop colour, and
    # anything it crossed is gone.  That is what a copyrect drag costs, and
    # the demo lays the desktop out so it does not matter.
    s += _frame(1, 3, 38, 32, "/DD")
    s += _frame(41, 3, 38, 32, "/DD/CMDS")
    # a status strip
    s += _bar(BAR, 0, 464, 639, 479)
    s += esc(0x32, INK) + _at(1, 58) + esc(0x3C, 1) + b"2 panes   copyrect drag: hardware" + esc(0x3C, 0)
    return bytes(s)


def stream_about():
    """The window that gets dragged.  Drawn once; SS.Copy moves the pixels."""
    s = bytearray()
    s += _frame(10, 37, 30, 14, "About this machine", hd=ACCENT)
    s += esc(0x32, INK) + esc(0x3C, 1)
    for i, line in enumerate([
            b"HD6309E at 2.098 MHz",
            b"NitrOS-9 Level 2",
            b"",
            b"video3: 4 CPLDs, 640x480x8",
            b"  character mode 80x25/30/50/60",
            b"  copy engine, 8x8 sprite",
            b"  no display list",
            b"",
            b"This window drags by copyrect."]):
        s += _at(12, 39 + i) + line
    s += esc(0x3C, 0)
    return bytes(s)


def stream_paint():
    """The paint program's canvas: patterns, shapes, a palette strip."""
    s = bytearray()
    s += _win(0x13, 0, 0, W, H, WHITE, grey(20))
    s += _bar(BAR, 0, 0, 639, 15)
    s += esc(0x32, INK) + _at(1, 0) + esc(0x3C, 1) + b"paint - video3" + esc(0x3C, 0)
    # a tool strip down the left
    s += _bar(grey(16), 0, 16, 47, 479)
    for i in range(12):
        s += _box(grey(8), 6, 24 + i * 32, 41, 24 + i * 32 + 27)
    # the canvas
    s += _bar(WHITE, 56, 24, 631, 415)
    s += _box(grey(6), 56, 24, 631, 415)
    # something painted on it
    s += esc(0x32, cube(5, 0, 0)) + esc(0x40, w16(120), w16(90)) + esc(0x54, w16(60), w16(40))
    s += esc(0x32, cube(0, 3, 5)) + esc(0x40, w16(260), w16(60)) + esc(0x4A, w16(400), w16(150))
    s += esc(0x32, cube(5, 4, 0)) + esc(0x40, w16(430), w16(60)) + esc(0x53, w16(50))
    s += esc(0x32, cube(0, 4, 1)) + esc(0x40, w16(120), w16(200))
    s += esc(0x52, w16(80), w16(50), w16(-80), w16(0), w16(80), w16(10))
    # a pattern fill
    PAT = bytes([(1 if (x ^ y) & 2 else 0) for y in range(8) for x in range(8)])
    s += esc(0x2B, 1, 1, 0x10, w16(8), w16(8), w16(64), PAT)
    s += esc(0x2E, 1, 1) + esc(0x40, w16(300), w16(200)) + esc(0x4A, w16(600), w16(400)) + esc(0x2E, 0, 0)
    # the palette strip along the bottom
    for i in range(72):
        x = 56 + i * 8
        s += _bar(16 + i * 3, x, 424, x + 6, 455)
    return bytes(s)


# ------------------------------------------------------------------- BBS
# CP437 box drawing and shading, in ANSI SGR colours - what the card's ATTR
# plane is for.  The bytes are CP437 code points, which is exactly what the
# character map stores.
def _sgr(*n):
    return b"\x1b[" + b";".join(b"%d" % x for x in n) + b"m"

def stream_bbs():
    """An 80 x 25 ANSI/CP437 BBS screen.  ⭐ Every byte here is a CP437 code
    point and an SGR colour, parsed by ca_ext.asm's ANSI terminal and drawn
    through the ATTR plane - no bitmap compositing at all."""
    s = bytearray()
    s += esc(0x20, 0x18, 0, 0, 80, 25, 7, 0, 0)        # an 80 x 25 character screen
    s += esc(0x69, 1)                                   # AnsiSw: the ANSI terminal on
    s += b"\x1b[2J\x1b[H"
    D, U = 0xC4, 0xCD          # single and double horizontals
    def dbox(x, y, w, h, colour):
        out = bytearray()
        out += b"\x1b[%d;%dH" % (y + 1, x + 1) + colour
        out += bytes([0xC9]) + bytes([U] * (w - 2)) + bytes([0xBB])
        for r in range(1, h - 1):
            out += b"\x1b[%d;%dH" % (y + r + 1, x + 1) + bytes([0xBA])
            out += b"\x1b[%d;%dH" % (y + r + 1, x + w) + bytes([0xBA])
        out += b"\x1b[%d;%dH" % (y + h, x + 1) + bytes([0xC8]) + bytes([U] * (w - 2)) + bytes([0xBC])
        return bytes(out)

    # a shaded backdrop, the way ANSI art is actually made
    s += _sgr(0, 34)
    for r in range(25):
        s += b"\x1b[%d;1H" % (r + 1) + bytes([0xB0] * 80)
    s += dbox(4, 1, 72, 8, _sgr(1, 36))
    s += b"\x1b[3;8H" + _sgr(1, 37) + b"THE ARM6309 BBS" + _sgr(0, 36) + b"  -  node 1  -  2400 baud  -  CP437"
    s += b"\x1b[5;8H" + _sgr(1, 33) + bytes([0xDB, 0xDB, 0xDC, 0xDF]) + _sgr(0, 33)
    s += b" sixteen colours, two hundred and fifty-six pairs "
    s += _sgr(1, 33) + bytes([0xDF, 0xDC, 0xDB, 0xDB])
    s += b"\x1b[7;8H" + _sgr(0, 32) + bytes([D] * 60)
    # a colour table: every foreground on every background, which IS the ATTR byte
    s += b"\x1b[10;6H" + _sgr(1, 37) + b"ATTR = (bg << 4) | fg      the LUT's high half, 256 pairs"
    for bg in range(8):
        s += b"\x1b[%d;6H" % (12 + bg)
        for fg in range(16):
            s += _sgr(0, 40 + bg, (30 + fg) if fg < 8 else (90 + fg - 8))
            s += bytes([0xB2])
        s += _sgr(0) + b"  "
        for fg in range(16):
            s += _sgr(0, 40 + bg, (30 + fg) if fg < 8 else (90 + fg - 8))
            s += b"Ab"
    s += _sgr(0)
    s += b"\x1b[21;6H" + _sgr(1, 35) + bytes([0xB0, 0xB1, 0xB2, 0xDB]) + _sgr(0, 35)
    s += b" shade cells   " + _sgr(1, 36) + bytes([0xC9, 0xCB, 0xBB, 0xCC, 0xCE, 0xB9, 0xC8, 0xCA, 0xBC])
    s += _sgr(0, 36) + b" box drawing"
    s += b"\x1b[23;6H" + _sgr(1, 37) + b"[Q]uit  [M]essages  [F]iles  [D]oors  " + _sgr(0, 37)
    return bytes(s)


def main(out):
    d = pathlib.Path(out); d.mkdir(parents=True, exist_ok=True)
    for name, fn in (("v3desk", stream_desk), ("v3about", stream_about),
                     ("v3paint", stream_paint), ("v3bbs", stream_bbs)):
        b = fn()
        (d / name).write_bytes(b)
        print("ok    %s/%s: %d bytes" % (out, name, len(b)))

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/v3sys")
