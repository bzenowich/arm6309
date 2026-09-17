#!/usr/bin/env python3
"""v3show.py OUT - the video3 demo's byte streams, into OUT/.

Each file is a stream of CoWin/CoArm escapes that a NitrOS-9 `copy` sends to
a window device, so the demo is driven by ordinary NitrOS-9 commands and file
I/O rather than by a bare-metal ROM.  video3/docs/demo-report.md 4 says why.

⭐ THE DESKTOP IS DRAWN BY THE ROM TOOLBOX.  ESC $6A calls tbox.asm, which
CoArm runs in place from ROM page 64 - Haiku's window tabs and bevels,
anti-aliased Noto Sans, the icons, the palette and the paint document are
all in the boot ROM, the way QuickDraw was in a Macintosh's (mktbox.py).

⭐ AND EVERY STREAM SHOWS ITS WINDOW FIRST.  DWSet, then Select, then the
drawing - so the display blanks, comes back, and the chrome is drawn in
front of the viewer rather than off-screen.

Files:
  v3desk      the 640 x 480 Haiku desktop: icons, the Deskbar, a Tracker
              window (whose list v3trk fills from the real directory)
  v3cmds      the second Tracker window, on top of the first
  v3about     the window v3drag moves with the copy engine
  v3paint     the Paint window, on the same screen; its document goes into
              VRAM's scroll margin, where v3scrl scrolls it from
  v3doodle    what is painted on the canvas once it has scrolled
  v3bbs       80 x 25 CP437 ANSI art - gruvbox, and 256-colour pairs
  video3.txt  a long text for `list` on the 80 x 60 console
"""
import sys, os, pathlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mktbox as T                                      # the palette, the icons

PAL, RAMP = T.PAL, T.RAMP
ICON = T.icon_names()


def esc(code, *b):
    return bytes([0x1B, code]) + bytes(b)


def W(*v):
    return b"".join(int(x).to_bytes(2, "big", signed=True) for x in v)


# ------------------------------------------------------- the ROM toolbox
def tb(fn, payload):
    assert len(payload) <= 64, len(payload)
    return esc(0x6A, fn, len(payload)) + payload


def col(c):
    return PAL[c] if isinstance(c, str) else c


def text(x, y, s, ramp="panel", bold=False):
    return tb(0, W(x, y) + bytes([RAMP[ramp], int(bold)]) + s.encode("latin-1"))


def textc(x, w, y, s, ramp="panel", bold=False):
    return tb(1, W(x, w, y) + bytes([RAMP[ramp], int(bold)]) + s.encode("latin-1"))


def icon(name, x, y, sel=0):
    return tb(2, bytes([ICON[name]]) + W(x, y) + bytes([sel]))


def bevel(x, y, w, h, fill="panel", raised=1):
    return tb(3, W(x, y, w, h) + bytes([col(fill), raised]))


def window(x, y, w, h, title, active=1):
    return tb(4, W(x, y, w, h) + bytes([active]) + title.encode("latin-1"))


def rect(x, y, w, h, c):
    return tb(5, W(x, y, w, h) + bytes([col(c)]))


def grad(x, y, w, h, first, n):
    return tb(6, W(x, y, w, h) + bytes([first, n]))


def palette():
    return tb(7, b"")


def image(n, x, y, raw=0):
    return tb(8, bytes([n]) + W(x, y) + bytes([raw]))


def scroll(x, y, length, vert, pos, thumb):
    return tb(9, W(x, y, length) + bytes([vert]) + W(pos, thumb))


def dwset(sty, x, y, w, h, fg, bg, bg3=None):
    """⚠ A NEW screen takes an eighth byte, PRN3; a window on the shown
    screen (STY $FF) does not.  Leaving it off a new screen's DWSet does not
    fail - the next escape's ESC is taken for it, and that escape is lost."""
    assert (bg3 is None) == (sty == 0xFF), "PRN3 is for a new screen only"
    return esc(0x20, sty, x, y, w, h, fg, bg) + (bytes([bg3]) if bg3 is not None else b"")


SELECT = esc(0x21)
CURSOR_OFF = b"\x05\x20"
POINTER_ON = esc(0x39, 0xCA, 0x01)          # GCSet: the arrow, on the card's sprite
# ⚠ where the pointer waits while the desktop is drawn: v3drag.asm's glide
# starts here, and ends on the About window's tab at GRAB, where
# session3.py's mouse tour starts.  Change one, change both.
PARK = (470, 430)
GRAB = (96 + 60, 392 - 19 + 9)


def put_gc(x, y):
    return esc(0x4E) + W(x, y)


# --------------------------------------------------------------- layout
# One place for every rectangle a command also needs (session3.py passes
# them to v3trk; v3drag.asm and v3scrl.asm hold their own copies, and say so).
class Tracker:
    def __init__(self, x, y, w, h, title, cols):
        self.x, self.y, self.w, self.h, self.title, self.cols = x, y, w, h, title, cols
        cx, cy, cw, ch = x + 5, y + 5, w - 10, h - 10
        self.menu = (cx, cy, cw, 20)
        self.head = (cx, cy + 21, cw - 14, 17)
        self.list = (cx, cy + 38, cw - 14, ch - 38 - 14)
        self.status = (cx, cy + ch - 14, 80, 14)
        self.hbar = (cx + 80, cy + ch - 14, cw - 80 - 14)
        self.corner = (cx + cw - 14, cy + ch - 14, 14, 14)

    def args(self, path):
        """v3trk's arguments: the list rectangle, its columns, the status text"""
        lx, ly, lw, lh = self.list
        sx, sy = self.status[0] + 5, self.status[1] - 3
        return "%s %d %d %d %d %d %d %d" % (path, lx, ly, lw, lh, self.cols, sx, sy)


TRK_DD = Tracker(96, 30, 230, 170, "/DD", 1)
TRK_CMDS = Tracker(236, 120, 390, 250, "/DD/CMDS", 2)
ABOUT = (96, 392, 250, 80)          # v3drag.asm: StartX 96, StartY 373, 250 x 99
assert GRAB == (ABOUT[0] + 60, ABOUT[1] - 19 + 9), "v3drag.asm's GrabX, GrabY"
DESKBAR_X = 500

# the Paint window: /W4 is cells (1, 1, 78, 58) of the screen, so its origin
# is (8, 8) and everything below is in its coordinates
PAINT_ORG = (8, 8)
PAINT = (0, 19, 624, 444)
VIEW = (72, 52, 256, 320)           # v3scrl.asm: the canvas, in /W4's pixels
DOC = (T.DOC_W, T.DOC_H)            # held at VRAM x 640, y 0: the margin


def tracker_chrome(t, active):
    s = bytearray()
    s += window(t.x, t.y, t.w, t.h, t.title, active)
    mx, my, mw, mh = t.menu
    s += grad(mx, my, mw, mh, T.GREYG, 8)
    s += text(mx + 6, my + 1, "File   Window   Attributes", "menu")
    s += rect(mx, my + mh, mw, 1, "frame")
    hx, hy, hw, hh = t.head
    s += bevel(hx, hy, hw, hh)
    cw = hw // t.cols
    for c in range(t.cols):
        s += text(hx + c * cw + 24, hy, "Name", "panel")
        if c:
            s += rect(hx + c * cw, hy + 2, 1, hh - 4, "frame")
    s += rect(*t.list, "white")
    s += scroll(hx + hw, hy, hh + t.list[3], 1, 0, hh + t.list[3] - 26)
    sx, sy, sw, sh = t.status
    s += bevel(sx, sy, sw, sh)
    hbx, hby, hbl = t.hbar
    s += scroll(hbx, hby, hbl, 0, 0, hbl - 26)
    s += rect(*t.corner, "panel")
    return bytes(s)


def desk_icon(name, x, y, label):
    return icon(name, x + 16, y) + textc(x, 64, y + 34, label, "desk")


def stream_desk():
    """The Haiku desktop, drawn on the screen while it is showing."""
    s = bytearray()
    s += dwset(0x13, 0, 0, 80, 60, PAL["white"], 2, 2)    # 640 x 480; 2 is CoWin's black
    s += SELECT + CURSOR_OFF
    s += POINTER_ON + put_gc(*PARK)                      # on from the start, on the desk
    s += palette()                                       # Haiku's 256, from the ROM
    s += rect(0, 0, 640, 480, "desk")
    for i, (n, label) in enumerate([("home", "home"), ("disk", "arm6309"), ("files", "Tracker"),
                                    ("term", "Terminal"), ("paint", "Paint"), ("game", "Zelda")]):
        s += desk_icon(n, 12, 12 + 66 * i, label)
    s += desk_icon("trash", 12, 414, "Trash")
    # the Deskbar
    x, w = DESKBAR_X, 640 - DESKBAR_X
    s += rect(x, 0, w, 105, "shadow")
    s += bevel(x + 1, 0, w - 1, 24)
    s += icon("leaf", x + 8, 4)
    s += text(x + 28, 3, "arm6309", "panel", bold=True)
    s += bevel(x + 1, 24, w - 1, 20)
    s += rect(x + 8, 29, 10, 10, "green")
    s += text(x + w - 44, 25, "12:34", "panel")
    for i, a in enumerate(["Tracker", "Terminal", "Paint"]):
        y = 44 + 20 * i
        s += bevel(x + 1, y, w - 1, 20)
        s += icon("app16", x + 6, y + 2)
        s += text(x + 28, y + 1, a, "panel")
    # the first Tracker window; v3trk lists what /DD really holds, and the
    # second window comes after that, on top of it (stream_cmds)
    s += tracker_chrome(TRK_DD, 0)
    return bytes(s)


def stream_cmds():
    """The second Tracker window.  ⚠ A separate stream because there is no
    clipping by windows: whatever is drawn last is on top, so /DD's list has
    to be in before this window covers part of it."""
    return tracker_chrome(TRK_CMDS, 1)


def stream_about():
    """The window v3drag moves.  Drawn once; after that its pixels are the
    only copy there is, and the card moves them."""
    x, y, w, h = ABOUT
    s = bytearray()
    s += window(x, y, w, h, "About arm6309", 1)
    s += rect(x + 5, y + 5, w - 10, h - 10, "panel")
    s += icon("disk", x + 12, y + 12)
    s += text(x + 56, y + 6, "arm6309", "panel", bold=True)
    s += text(x + 56, y + 22, "HD6309E  -  NitrOS-9 Level 2", "panel")
    s += text(x + 56, y + 38, "video3  640x480x8, copy engine", "panel")
    s += text(x + 56, y + 54, "dragged by the card: 0 CPU pixels", "dim")
    return bytes(s)


def stream_paint():
    """The Paint window, over the desktop on the same screen."""
    vx, vy, vw, vh = VIEW
    s = bytearray()
    s += dwset(0xFF, 1, 1, 78, 58, PAL["black"], PAL["desk"])   # a window on the shown screen
    s += SELECT + CURSOR_OFF
    x, y, w, h = PAINT
    s += window(x, y, w, h, "parrots.img - Paint", 1)
    cx, cy, cw, ch = x + 5, y + 5, w - 10, h - 10
    s += rect(cx, cy, cw, ch, "panel")
    s += grad(cx, cy, cw, 20, T.GREYG, 8)
    s += text(cx + 6, cy + 1, "File   Edit   Image   Tools   Window   Help", "menu")
    s += rect(cx, cy + 20, cw, 1, "frame")
    # the tools, two columns, the brush chosen
    tools = ["tool_" + t for t in T.TOOLS] + [None]
    for i, t in enumerate(tools):
        bx, by = cx + 4 + (i % 2) * 27, cy + 26 + (i // 2) * 27
        chosen = t == "tool_brush"
        s += bevel(bx, by, 26, 26, "black" if chosen else "panel", 0 if chosen else 1)
        if t:
            s += icon(t, bx + 5, by + 5, 1 if chosen else 0)
    # a colour well from the cube, and the pen and paper
    for i in range(48):
        r, g = divmod(i, 6)
        c = T.CUBE0 + (r * 5 + g * 7) % 200
        s += rect(cx + 4 + g * 9, cy + 250 + r * 9, 8, 8, c)
    s += rect(cx + 14, cy + 336, 22, 22, "white")
    s += rect(cx + 6, cy + 328, 22, 22, "black")
    # the canvas, sunken, and its scroll bars
    s += bevel(vx - 2, vy - 2, vw + 18, vh + 18, "frame", 0)
    s += rect(vx, vy, vw, vh, "white")
    s += scroll(vx + vw, vy, vh, 1, 0, (vh - 26) * vh // DOC[1])
    s += scroll(vx, vy + vh, vw, 0, 0, (vw - 26) * vw // DOC[0])
    s += rect(vx + vw, vy + vh, 14, 14, "panel")
    # the information panel
    px = vx + vw + 26
    s += bevel(px, vy, cx + cw - 6 - px, 144)
    s += text(px + 8, vy + 4, "parrots.img", "panel", bold=True)
    for i, line in enumerate(["384 x 480 pixels, 8 bits", "shown 256 x 320", "",
                              "held in VRAM's margin,", "columns 640-1023, where", "the display cannot see it"]):
        s += text(px + 8, vy + 24 + 18 * i, line, "panel")
    s += bevel(px, vy + 152, cx + cw - 6 - px, 90)
    s += text(px + 8, vy + 156, "Scrolling", "panel", bold=True)
    for i, line in enumerate(["two copies a step, by", "the card: the view, then", "the strip coming in"]):
        s += text(px + 8, vy + 176 + 18 * i, line, "panel")
    # a status bar
    s += bevel(cx, cy + ch - 20, cw, 20)
    s += text(cx + 8, cy + ch - 19, "brush 3 px     100%     0 CPU pixels a scroll step", "panel")
    # the document, into the margin: raw VRAM pixels the screen does not show
    s += image(0, 640, 0, raw=1)
    return bytes(s)


def stream_doodle():
    """Painting on the canvas, where v3scrl leaves the view (the document's
    corner): a ring round the middle macaw's head (mktbox.DOC_HEAD) and a
    speech balloon pointing at it."""
    vx, vy, vw, vh = VIEW
    hx, hy = vx + T.DOC_HEAD[0], vy + T.DOC_HEAD[1]
    msg = "Polly wants a copyrect!"
    tw = T.text_width(msg, bold=True)
    rx, ry = tw // 2 + 14, 17
    bx, by = vx + 8 + rx, hy + 110
    s = bytearray()
    s += esc(0x32, PAL["red"])
    for k in range(3):
        s += esc(0x40, *W(hx + 2, hy - 2)) + esc(0x51, *W(40 + k, 38 + k))   # inside the canvas: nothing clips to it
    s += esc(0x32, PAL["white"]) + esc(0x40, *W(bx, by)) + esc(0x54, *W(rx, ry))
    s += esc(0x32, PAL["black"]) + esc(0x40, *W(bx, by)) + esc(0x51, *W(rx, ry))
    # the tail: white between two black edges, so it reads over dark feathers
    s += esc(0x32, PAL["white"])
    for dx in range(21, 34):
        s += esc(0x40, *W(bx + dx, by - ry + 2)) + esc(0x44, *W(hx - 10, hy + 40))
    s += esc(0x32, PAL["black"])
    for dx in (20, 34):
        s += esc(0x40, *W(bx + dx, by - ry + 1)) + esc(0x44, *W(hx - 10, hy + 40))
    s += textc(bx - rx, 2 * rx, by - 9, msg, "white", bold=True)
    return bytes(s)


# ------------------------------------------------------------------- BBS
# CP437 box drawing and shading, in ANSI SGR colours - what the card's ATTR
# plane is for.  The bytes are CP437 code points, which is exactly what the
# character map stores.
def _sgr(*n):
    return b"\x1b[" + b";".join(b"%d" % x for x in n) + b"m"


def _fg(n):
    return b"\x1b[38;5;%dm" % n


def _bg(n):
    return b"\x1b[48;5;%dm" % n


# gruvbox (dark): the sixteen ANSI colours, as RGB565 - the palette the
# character screen starts with is already these (ca_v3txt.asm TxAnsiP), and
# the stream loads them again with PalRange to show that it can
GRUVBOX = ["282828", "cc241d", "98971a", "d79921", "458588", "b16286", "689d6a", "a89984",
           "928374", "fb4934", "b8bb26", "fabd2f", "83a598", "d3869b", "8ec07c", "ebdbb2"]


def stream_bbs():
    """An 80 x 25 ANSI/CP437 BBS screen.  ⭐ Every byte here is a CP437 code
    point and an SGR colour, parsed by ca_ext.asm's ANSI terminal and drawn
    through the ATTR plane - no bitmap compositing at all.  The window is
    shown first, so the screen is seen being drawn."""
    s = bytearray()
    s += dwset(0x18, 0, 0, 80, 25, 7, 0, 0) + SELECT  # an 80 x 25 character screen, shown
    pal = b"".join(T.rgb565(tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))).to_bytes(2, "big")
                   for h in GRUVBOX)
    s += esc(0x61, 0, 16) + pal                         # PalRange 0, 16: gruvbox
    s += esc(0x69, 1)                                   # AnsiSw: the ANSI terminal on
    s += b"\x1b[2J\x1b[H"
    D, U = 0xC4, 0xCD

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
        s += b"\x1b[%d;1H" % (r + 1) + bytes([0xB0] * (80 if r < 24 else 79))
    s += dbox(4, 0, 72, 7, _sgr(1, 33))
    s += b"\x1b[2;8H" + _sgr(1, 37) + b"THE ARM6309 BBS" + _sgr(0, 33) + b"  -  node 1  -  2400 baud  -  CP437 + gruvbox"
    s += b"\x1b[4;8H" + _sgr(1, 31) + bytes([0xDB, 0xDB, 0xDC, 0xDF]) + _sgr(0, 32)
    s += b" ATTR is a handle: any of 256 on any of 256 "
    s += _sgr(1, 31) + bytes([0xDF, 0xDC, 0xDB, 0xDB])
    s += b"\x1b[6;8H" + _sgr(0, 36) + bytes([D] * 64)
    # the sixteen crossed with eight: the VGA byte's pairs
    s += b"\x1b[9;6H" + _sgr(1, 37) + b"SGR 30-37 on 40-47: the sixteen ANSI colours"
    for bg in range(8):
        s += b"\x1b[%d;6H" % (10 + bg)
        for fg in range(16):
            s += _sgr(0, 40 + bg, (30 + fg) if fg < 8 else (90 + fg - 8))
            s += bytes([0xB2])
        s += _sgr(0) + b"  "
        for fg in range(16):
            s += _sgr(0, 40 + bg, (30 + fg) if fg < 8 else (90 + fg - 8))
            s += b"Ab"
    # ⭐ 256 colours: 38;5;n on 48;5;n, two pixels of colour a cell with the
    # upper half block - pairs the VGA byte cannot name at all
    # ⚠ THE BUDGET IS 256 PAIRS ON THE SCREEN AT ONCE.  The table above is 128
    # and the rest of the screen about a dozen, so this block is 96: a
    # 6 x 6 x 6 cube walked in 80 half-block cells, and 16 greys.
    s += _sgr(0) + b"\x1b[9;60H" + _sgr(1, 37) + b"SGR 38;5 / 48;5"
    for row in range(5):
        s += b"\x1b[%d;60H" % (10 + row)
        for k in range(16):
            n = 16 + (row * 36 + k * 13) % 216
            s += _fg(n) + _bg(16 + (n - 16 + 108) % 216) + bytes([0xDF])
    s += b"\x1b[15;60H"
    for k in range(16):
        s += _fg(232 + (k * 23) // 15) + _bg(255 - (k * 23) // 15) + bytes([0xDF])
    s += b"\x1b[16;60H" + _sgr(0, 37) + b"96 of 65,536"
    s += _sgr(0)
    s += b"\x1b[20;6H" + _sgr(1, 35) + bytes([0xB0, 0xB1, 0xB2, 0xDB]) + _sgr(0, 35)
    s += b" shade cells   " + _sgr(1, 36) + bytes([0xC9, 0xCB, 0xBB, 0xCC, 0xCE, 0xB9, 0xC8, 0xCA, 0xBC])
    s += _sgr(0, 36) + b" box drawing   " + _sgr(1, 32) + bytes([0xDA, 0xC2, 0xBF, 0xC3, 0xC5, 0xB4, 0xC0, 0xC1, 0xD9])
    s += b"\x1b[22;6H" + _sgr(0, 33) + b"gruvbox: PalRange 0 16 on a character screen reloads its pairs"
    s += b"\x1b[24;6H" + _sgr(1, 37, 44) + b" [Q]uit  [M]essages  [F]iles  [D]oors " + _sgr(0)
    s += esc(0x69, 0)                                   # AnsiSw off: CoWin's escapes again
    return bytes(s)


TEXT = """\
================================================================================
                    video3 - a console-first video card
================================================================================

  This file is being listed by the NitrOS-9 `list` command, onto /W1: an
  80 x 60 character screen.  Every line you see arrive below the last row
  moves the other fifty-nine up with the card's COPY ENGINE - one rectangle,
  160 bytes a row, 59 rows, about 2.3 ms of engine and six register writes.

--------------------------------------------------------------------------------
 1. Modes
--------------------------------------------------------------------------------

  CTRL b3-2 selects one of three:

    00  bitmap      640 x 200 / 240 / 400 / 480, eight bits a pixel
    01  character   80 x 25 / 30 / 50 / 60, two bytes a cell
    10  tile        8 x 8 tiles of eight-bit pixels, one byte a cell

  The timing is inherited from video/ unchanged: one 25.175 MHz dot clock,
  800 dots a line, and two vertical families of 449 and 525 lines.

--------------------------------------------------------------------------------
 2. Character mode
--------------------------------------------------------------------------------

  A cell is two bytes - a CP437 code and an ATTR byte.

      map word     [15:8] attribute     [7:0] glyph code
      LUT address  [15:8] attribute     [7:0] the glyph's pixel byte

  The palette LUT is 64K x 16 and video/ uses 256 words of it.  video3
  drives the LUT's HIGH eight address lines from the attribute, so every
  ATTR value is a sub-palette of its own: 256 simultaneous (fg, bg) pairs,
  each chosen from 65,536 colours.

  The glyph bank holds all 256 CP437 characters.  Reverse video is an
  attribute, not half the font, so box drawing and shade cells are all
  there:

      +---+   ░░▒▒▓▓██   ╔═╦═╗   ┌─┬─┐
      |   |   ░░▒▒▓▓██   ╠═╬═╣   ├─┼─┤
      +---+   ░░▒▒▓▓██   ╚═╩═╝   └─┴─┘

--------------------------------------------------------------------------------
 3. Scrolling
--------------------------------------------------------------------------------

  Bitmap and tile mode scroll by register: VSCROLL is nine bits, HSCROLL
  ten, one pixel at a time, over a 1024 x 512 torus.

  Character mode scrolls by copying.  One scrolled line at 80 x 25:

      VSCROLL += 8        one register write     clear one row: 271 us
      the copy engine     948 us of engine       six writes + the clear
      the CPU alone       -                      10.0 ms

  The clear dominates, both paths pay it, and copying buys a map that
  never rotates: no ring, no runway, no recycled row.

--------------------------------------------------------------------------------
 4. The copy engine
--------------------------------------------------------------------------------

  CPTR is the source, WPTR the destination, CWIDTH and CHEIGHT the size,
  and CCTRL b0 is GO.  There is no adder anywhere: the stride is 1024, a
  power of two, so the end of a row reloads the column and steps the row.

      a window scroll, 192 rows            30.3 ms
      Select between two 200-line pages    31.6 ms
      GetBlk -> PutBlk, 64 x 64            1.0 ms

  The engine counts up only.  A copy whose destination lies above its
  source in memory is one pass; any other overlap is staged through the
  off-screen rows 480-511 in two passes.

--------------------------------------------------------------------------------
 5. The sprite
--------------------------------------------------------------------------------

  One 8 x 8 sprite, two bits a pixel, for the mouse pointer.  Its shape
  lives in the register file, not VRAM, and it is composed at scan time:
  nothing is saved behind it and nothing has to be put back.  Moving it
  is three register writes.

--------------------------------------------------------------------------------
 6. Memory
--------------------------------------------------------------------------------

      framebuffer    2 x AS6C8016          512K x 16, 55 ns
      palette LUT    1 x IS61C6416AL-12    64K x 16
      register file  1 x 32K x 8           20 ns

      rows 0-479                the picture, 1024-byte stride
      rows 480-511              off-screen scratch for the copy engine
      columns 640-1023          the scroll margin HSCROLL moves into

--------------------------------------------------------------------------------
 7. What it does not have
--------------------------------------------------------------------------------

  No display list, so nothing per-scanline: no raster bars and no sine
  warp.  No horizontal scroll in character mode.  One sprite, not eight.
  The four programmable parts are ATF1508AS CPLDs, and the board has room
  for no fifth.

================================================================================
                              end of video3.txt
================================================================================
"""


def stream_text():
    """A long plain-text file for `list` on the 80 x 60 console, so the
    copy-engine scroll has something to scroll.  OS-9 ends a line with CR;
    the text is CP437."""
    return TEXT.replace("\n", "\r").encode("cp437")


def main(out):
    d = pathlib.Path(out); d.mkdir(parents=True, exist_ok=True)
    for name, fn in (("v3desk", stream_desk), ("v3cmds", stream_cmds), ("v3about", stream_about),
                     ("v3paint", stream_paint), ("v3doodle", stream_doodle),
                     ("v3bbs", stream_bbs), ("video3.txt", stream_text)):
        b = fn()
        (d / name).write_bytes(b)
        print("ok    %s/%s: %d bytes" % (out, name, len(b)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/v3sys")
