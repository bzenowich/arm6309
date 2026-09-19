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
  v3paint     Paint, on a SCREEN OF ITS OWN, and its page into VRAM's
              scroll margin, where v3scrl scrolls it from
  v3draw      the page painted in front of the viewer: shapes, a pattern
              fill, a polygon, type and a band of colour
  v3menu      the File menu pulled down
  v3open      the Choose File dialog, parrot.img picked
  v3load      the dialog gone, the window renamed, the picture into the
              margin for v3grab to drag round a circle
  v3shut      the close box pressed - then DWEnd, and the desktop is back
  v3bbs       80 x 25 CP437 ANSI art - gruvbox, and 256-colour pairs
  v3art       a real .ans re-emitted, when video3/we-tortuga.ans is there
  v3pal       the DOS palette for it, which cannot travel with it (have_art)
  v3fonts     the 27 wildbits 8 x 8 faces, one GP buffer each - 55 KB, and
              nothing to look at, so the session loads it under another scene
  v3write     the word processor, with the Font menu open in its own faces
  v3spec      the same window as a specimen: Noto Sans names, 8 x 8 samples
  video3.txt  a long text for `list` on the 80 x 60 console
"""
import sys, os, re, pathlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mktbox as T                                      # the palette, the icons

import mkfonts as F                             # the wildbits 8 x 8 faces

PAL, RAMP = T.PAL, T.RAMP
FACES = F.FONTS                                 # [(name, 2048 bytes)]
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


# ⭐ FONT bit 2 is F.Opaq: draw the ramp's paper as well as the ink, so the
# row is one run instead of ~10 and the CPU skips the KEY fill and the run
# scan.  ⚠ Only where the background really is that ramp's flat paper - the
# window tab is a gradient, and tbox.asm refuses it there (RPaper $FF).
F_OPAQ = 4


def text(x, y, s, ramp="panel", bold=False, opaque=False):
    fnt = int(bold) | (F_OPAQ if opaque else 0)
    return tb(0, W(x, y) + bytes([RAMP[ramp], fnt]) + s.encode("latin-1"))


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


# ---------------------------------------------------------------- Paint
# ⭐ PAINT HAS ITS OWN SCREEN.  Everything else in this demo is a window on
# the desktop's screen; Paint is a NitrOS-9 SCREEN of its own ($13), because
# that is what makes the close box work: DWEnd hands the display back to the
# desktop's screen, whose pixels have been waiting in its DRAM store
# (ca_scr.asm), and the desktop is simply there again.  A full-screen window
# over the desktop could only be closed by redrawing the desktop.
PSCR = (640, 480)
PWIN = (0, 19, 640, 461)            # ⚠ window() puts the TAB above y: 0..18
PIN = (PWIN[0] + 5, PWIN[1] + 5, PWIN[2] - 10, PWIN[3] - 10)
CANVAS = T.CANVAS                   # ⚠ mktbox.py, v3scrl.asm VW/VH, v3grab.asm
CANX, CANY = 14, 82                 # ⚠ v3scrl.asm VX/VY, v3grab.asm CX/CY
PARROT = T.PARROT                   # ⚠ v3grab.asm PW/PH
PHOME = ((CANVAS[0] - PARROT[0]) // 2, (CANVAS[1] - PARROT[1]) // 2)
GRABR = 25                          # the circle v3grab drags it round, in pixels
assert PHOME[0] >= GRABR and PHOME[1] >= GRABR, "the circle runs off the page"
RPX = 362                           # the notes panel, right of the canvas
PMENU = "File   Edit   Goodies   Font   FontSize   Style"
PATY = 420                          # the pattern and colour strip
STATY = 452

# the eight patterns of the strip, 8 x 8 rows of bits - MacPaint's, near
# enough: solid, the three grey screens, two hatches, a brick and a weave
PATS = [0xFF] * 8, \
       [0xAA, 0x55, 0xAA, 0x55, 0xAA, 0x55, 0xAA, 0x55], \
       [0x88, 0x22, 0x88, 0x22, 0x88, 0x22, 0x88, 0x22], \
       [0x80, 0x08, 0x80, 0x08, 0x80, 0x08, 0x80, 0x08], \
       [0x11, 0x22, 0x44, 0x88, 0x11, 0x22, 0x44, 0x88], \
       [0x88, 0x44, 0x22, 0x11, 0x88, 0x44, 0x22, 0x11], \
       [0xFF, 0x80, 0x80, 0x80, 0xFF, 0x08, 0x08, 0x08], \
       [0x33, 0xCC, 0x33, 0xCC, 0x33, 0xCC, 0x33, 0xCC]


def fcol(c):
    return esc(0x32, col(c))


def bcol(c):
    return esc(0x33, col(c))


def bar(x, y, w, h):
    return esc(0x40, *W(x, y)) + esc(0x4A, *W(x + w - 1, y + h - 1))


def box(x, y, w, h):
    return esc(0x40, *W(x, y)) + esc(0x48, *W(x + w - 1, y + h - 1))


def patdef(n, rows):
    return esc(0x62, n, *rows)


def patbar(x, y, w, h):
    return esc(0x63, *W(x, y, x + w - 1, y + h - 1))


def poly(left, right, pat=False):
    """⚠ BOTH CHAINS RUN DOWN, and they must start and finish on the same
    row: CoArm walks y from the LEFT chain's first to its last and wants an x
    from each chain on every row of it (ca_ext.asm, vgmodel.poly_spans)."""
    pts = list(left) + list(right)
    assert 2 <= len(left) and 2 <= len(right) and len(pts) <= 16, len(pts)
    assert left[0][1] == right[0][1] and left[-1][1] == right[-1][1], "chains must meet"
    return esc(0x66 if pat else 0x65, len(left), len(right)) + b"".join(W(x, y) for x, y in pts)


def lines(pts, close=True):
    p = list(pts) + ([pts[0]] if close else [])
    return esc(0x40, *W(*p[0])) + b"".join(esc(0x46, *W(x, y)) for x, y in p[1:])


def star(cx, cy, r, ri):
    """A five-pointed star as THREE chain pairs, and the ring for its outline.

    ⛔ A POLY IS ONE SPAN A ROW.  CoArm walks a left chain and a right chain
    and paints between them (ca_ext.asm), so a shape whose row is two separate
    runs cannot be one call - and below the star's bottom inner vertex every
    row IS two runs, one down each leg.  Handed the ten vertices as a single
    pair of chains it paints the notch between the legs solid, and the star
    comes out with a filled-in foot.

    So it is cut across that vertex: the body above it, and a leg each below.
    The pattern is tiled from the working area's origin rather than from the
    shape, so the three pieces have no seam.
    """
    import math

    def at(k, rad, off):
        a = math.radians(off + 72 * k)
        return (cx + rad * math.cos(a), cy + rad * math.sin(a))

    def rd(p):
        return (int(round(p[0])), int(round(p[1])))

    def cut(a, b, y):
        """where segment a-b crosses row y"""
        return (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)

    o = [at(k, r, -90) for k in range(5)]        # 0 top, 1 right, 2 foot, 3 foot, 4 left
    i = [at(k, ri, -54) for k in range(5)]       # 2 is the bottom inner vertex
    yb = round(i[2][1])
    L, R = cut(i[3], o[3], yb), cut(i[1], o[2], yb)
    foot = max(round(o[2][1]), round(o[3][1]))   # the two feet share a row
    o2, o3 = (o[2][0], foot), (o[3][0], foot)
    parts = [([o[0], i[4], o[4], i[3], L], [o[0], i[0], o[1], i[1], R]),
             ([L, o3], [i[2], o3]),              # the left leg
             ([i[2], o2], [R, o2])]              # and the right
    parts = [([rd(p) for p in a], [rd(p) for p in b]) for a, b in parts]
    ring = [rd(p) for p in (o[0], i[0], o[1], i[1], o[2],
                            i[2], o[3], i[3], o[4], i[4])]
    return parts, ring


def tool_row(chosen):
    """The tools, ONE ROW along the top the way the model in
    software/demo/build/video's show has them - which is what leaves the
    canvas its width."""
    s = bytearray()
    for i, t in enumerate(T.TOOLS):
        bx, by = 9 + i * 28, 48
        on = t == chosen
        s += bevel(bx, by, 26, 26, "black" if on else "panel", 0 if on else 1)
        s += icon("tool_" + t, bx + 5, by + 5, 1 if on else 0)
    return bytes(s)


def paint_title(name):
    return window(*PWIN, "Paint - " + name, 1)


NOTES_UNTITLED = ("untitled",
                  ["%d x %d pixels, 8 bits" % (T.DOC_W, T.DOC_H),
                   "shown %d x %d" % CANVAS, "",
                   "held in VRAM's margin,", "columns 640-1023, where",
                   "the display cannot see it"],
                  ["two copies a step, by", "the card: the view,",
                   "then the strip coming in", "- and the page is 64",
                   "columns and 160 rows", "wider than the window"],
                  "brush 3 px     100%     0 CPU pixels a scroll step", "brush")
NOTES_PARROT = ("parrot.img",
                ["%d x %d pixels, 8 bits" % PARROT, "shown 1:1", "",
                 "in the margin as well,", "so the copy engine can",
                 "drag it round a circle"],
                ["one SS.Copy a step, and", "a white bar for each",
                 "axis that moved - the", "page is a colour, so",
                 "there is no backing", "store to keep"],
                "grab     100%%     %d x %d pixels a step, none of them" % PARROT, "grab")


def paint_chrome(title, notes):
    """⛔ THE WHOLE WINDOW, because window() CLEARS IT.  tbox.asm's TWin
    fills the frame with C.Panel before it draws the border (Fill 1,1,-2,-2),
    so a title changed after the fact wipes the canvas, the notes and the
    palette strip with it.  Everything a repaint needs is therefore here, and
    the callers differ only in the title and the words."""
    cx, cy, cw, ch = PIN
    vx, vy, vw, vh = CANX, CANY, *CANVAS
    head, note, scr, status, tool = notes
    s = bytearray()
    s += window(*PWIN, "Paint - " + title, 1)
    s += grad(cx, cy, cw, 20, T.GREYG, 8)
    s += text(cx + 6, cy + 1, PMENU, "menu")
    s += rect(cx, cy + 20, cw, 1, "frame")
    s += tool_row(tool)
    # the canvas, sunken, and its scroll bars
    s += bevel(vx - 2, vy - 2, vw + 18, vh + 18, "frame", 0)
    s += rect(vx, vy, vw, vh, "white")
    s += scroll(vx + vw, vy, vh, 1, 0, (vh - 26) * vh // T.DOC_H)
    s += scroll(vx, vy + vh, vw, 0, 0, (vw - 26) * vw // T.DOC_W)
    s += rect(vx + vw, vy + vh, 14, 14, "panel")
    # the notes, right of the canvas
    s += bevel(RPX, vy, cx + cw - 6 - RPX, 150)
    s += text(RPX + 8, vy + 4, head, "panel", bold=True)
    for i, line in enumerate(note):
        s += text(RPX + 8, vy + 24 + 18 * i, line, "panel")
    s += bevel(RPX, vy + 158, cx + cw - 6 - RPX, 120)
    s += text(RPX + 8, vy + 162, "Scrolling" if tool == "brush" else "Dragging",
              "panel", bold=True)
    for i, line in enumerate(scr):
        s += text(RPX + 8, vy + 182 + 18 * i, line, "panel")
    # ⭐ the patterns and the colours, in a strip along the bottom
    s += bevel(cx, PATY, cw, 28)
    for i, rows in enumerate(PATS):
        s += bevel(cx + 4 + i * 24, PATY + 3, 22, 22, "panel", 0)
        s += patdef(i, rows) + fcol("black") + bcol("white")
        s += patbar(cx + 5 + i * 24, PATY + 4, 20, 20)
    s += rect(cx + 206, PATY + 3, 1, 22, "frame")
    for i in range(30):
        c = ("black", "white", "red", "orange", "green", "desk", "tab", "pale")[i % 8] \
            if i < 8 else T.CUBE0 + ((i - 8) * 9 + (i - 8) // 5 * 37) % 200
        s += rect(cx + 212 + i * 14, PATY + 3, 13, 22, c)
    s += bevel(cx, STATY, cw, 20)
    s += text(cx + 8, STATY + 1, status, "panel")
    return bytes(s)


def stream_paint():
    """Paint, on a screen of its own, drawn as you watch; then the page into
    VRAM's margin, where the display cannot see it."""
    s = bytearray()
    s += dwset(0x13, 0, 0, 80, 60, PAL["black"], 2, 2)
    s += SELECT + CURSOR_OFF
    # ⛔ A NEW SCREEN COMES UP IN CoWin's OWN PALETTE, and every colour
    # below is an index into the toolbox's.  v3desk loads it for the desktop's
    # screen; Paint has a screen of its own, so it has to load it too - and
    # without this line the whole window is drawn in somebody else's sixteen.
    s += palette()
    s += paint_chrome("untitled", NOTES_UNTITLED)
    # ⚠ LAST, and the only slow thing here: the page into the margin, as raw
    # VRAM pixels the display does not fetch.  v3scrl copies the canvas over
    # its corner before it scrolls, so what the viewer draws IS page one.
    s += image(T.IMAGE["page"], 640, 0, raw=1)
    return bytes(s)


def stream_draw():
    """⭐ THE PAGE, PAINTED IN FRONT OF THE VIEWER - shapes, a pattern fill,
    a polygon, type and a band of colour, each with its own tool lit in the
    palette, all of it CoArm's own drawing primitives on the canvas.

    ⚠ Nothing clips to the canvas: the window's working area is the whole
    screen, so every coordinate here is checked into the canvas by hand."""
    X, Y = CANX, CANY

    def c(x, y):
        assert 0 <= x < CANVAS[0] and 0 <= y < CANVAS[1], (x, y)
        return X + x, Y + y

    s = bytearray()
    # 1 - a filled rectangle, and its frame
    s += tool_row("frect") + fcol("red") + bar(*c(12, 12), 128, 74)
    s += fcol("black") + box(*c(12, 12), 128, 74)
    # 2 - an outlined one, then the bucket, in a pattern
    s += tool_row("rect") + box(*c(160, 12), 148, 74)
    s += tool_row("bucket") + patdef(6, PATS[6]) + fcol("orange") + bcol("pale")
    s += patbar(*c(161, 13), 146, 72)
    # 3 - a polygon: the triangle
    s += tool_row("fpoly") + fcol("sel")
    s += poly([c(24, 104), c(10, 196)], [c(24, 104), c(104, 196)])
    s += fcol("black") + lines([c(24, 104), c(104, 196), c(10, 196)])
    # 4 - and a star, filled with a pattern instead of a colour
    # ⚠ the INK is the sparse one: pattern 4 sets one bit in eight, so
    # black ink on a gold paper is a gold star ruled with fine diagonals -
    # the other way round would be a black star with gold threads
    parts, ring = star(190, 152, 50, 20)
    s += patdef(4, PATS[4]) + fcol("black") + bcol("tab")
    for left, right in parts:
        s += poly([c(*p) for p in left], [c(*p) for p in right], pat=True)
    s += fcol("black") + lines([c(*p) for p in ring])
    # 5 - type, from the ROM toolbox
    s += tool_row("text")
    s += text(*c(12, 210), "Hello from a 6309 - the toolbox drew this", "white")
    # 6 - ⭐ and the band of colour, a bar at a time, left to right
    s += tool_row("line")
    for i, name in enumerate(("red", "orange", "tab", "green", "desk", "sel")):
        s += fcol(name) + bar(*c(12, 232 + i * 13), 292, 10)
    s += tool_row("grab")
    return bytes(s)


def stream_menu():
    """The File menu, pulled down."""
    cx, cy = PIN[0], PIN[1]
    s = bytearray()
    s += rect(cx + 4, cy + 1, 34, 18, "sel")
    s += text(cx + 6, cy + 1, "File", "sel")
    s += bevel(cx + 2, cy + 20, 118, 118)
    for i, (name, dim) in enumerate([("New", 0), ("Open...", 0), ("Close", 0),
                                     ("Save", 1), ("Save As...", 1), ("Quit", 0)]):
        if i == 3:
            s += rect(cx + 8, cy + 26 + 18 * i, 106, 1, "frame")
        s += text(cx + 12, cy + 24 + 18 * i + (i >= 3), name, "dim" if dim else "panel")
    return bytes(s)


DLG = (180, 150, 300, 214)
FILES = [("image16", "parrot.img"), ("image16", "sunset.img"), ("image16", "tiles.img"),
         ("doc16", "palette.txt"), ("doc16", "notes.txt")]


def stream_open():
    """The Choose File dialog, with parrot.img picked."""
    x, y, w, h = DLG
    cx, cy = x + 5, y + 5
    s = bytearray()
    s += window(x, y, w, h, "Open", 1)
    s += rect(cx, cy, w - 10, h - 10, "panel")
    s += text(cx + 6, cy + 4, "Look in:  /DD/SYS", "panel")
    s += bevel(cx + 6, cy + 26, w - 22, 116, "frame", 0)
    s += rect(cx + 8, cy + 28, w - 26, 112, "white")
    for i, (ic, name) in enumerate(FILES):
        ty = cy + 30 + 21 * i
        on = i == 0
        if on:
            s += rect(cx + 9, ty, w - 28, 20, "sel")
        s += icon(ic, cx + 12, ty + 2, 0)
        s += text(cx + 34, ty + 2, name, "sel" if on else "white")
    for i, (name, bx) in enumerate([("Cancel", 128), ("Open", 210)]):
        s += bevel(cx + bx, cy + 152, 72, 26)
        s += textc(cx + bx, 72, cy + 156, name, "panel", bold=i == 1)
    return bytes(s)


def stream_load():
    """The dialog gone, the window renamed, and the picture into the margin
    where v3grab can drag it about with the copy engine.

    ⚠ The whole window is repainted, not patched: window() clears what it
    frames (paint_chrome says so), and the dialog was over the canvas and the
    notes anyway."""
    s = bytearray()
    s += paint_chrome("parrot.img", NOTES_PARROT)
    s += image(T.IMAGE["parrot"], 640, 0, raw=1)
    return bytes(s)


def stream_shut():
    """The close box, pushed in.

    ⚠ NOT window() AGAIN: that would clear the frame and take the picture
    with it.  The box is the 12 x 12 bevel tbox.asm's TWin puts at (7, -15)
    of the frame, so pressing it is one sunken bevel in the same place."""
    x, y, _, _ = PWIN
    return bevel(x + 7, y - 15, 12, 12, "frame", 0)


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
# ⭐ INDEX 0 IS GRUVBOX'S OWN #282828, and the screen is simply left in it.
# What was wrong with the earlier screen was never the grey: it was a backdrop
# of 2,000 CP437 light-shade cells in blue, faking the mid-tone the way ANSI
# art has to when it only has sixteen colours.  This card has a palette, so
# the background colour IS a palette entry - PalRange loads it with the other
# fifteen and every cell behind the tables stays blank.
GRUVBOX = ["282828", "cc241d", "98971a", "d79921", "458588", "b16286", "689d6a", "a89984",
           "928374", "fb4934", "b8bb26", "fabd2f", "83a598", "d3869b", "8ec07c", "ebdbb2"]


# ------------------------------------- NitrOS-9's OWN downloadable fonts
# ⭐ THE OTHER FONT SYSTEM.  The ROM toolbox has two proportional faces and
# room for four; these are GrfDrv's - 1 bpp, 8 x 8, one glyph every eight
# bytes at code * 8 - and they are not in the ROM at all.  Each one is sent
# to the card as an ESC $2B GPLoad, lands in a GP buffer (CoArm has
# GPMax = 48), and ESC $3A Font picks it for the window's ordinary text.
# ca_bmtx.asm's GlyphOf is what reads it; ca_gpb.asm's DoFont what selects it.
FONT_GRP = 0xC8                                 # stock NitrOS-9's font group


def gpfont(buf, blob):
    """ESC $2B GPLoad grp buf sty xs:w ys:w n:w, then n bytes.  Type 5 is
    1 bpp; 8 wide and one byte a row, so ys is the byte count."""
    return esc(0x2B, FONT_GRP, buf, 5) + W(8, len(blob)) + W(len(blob)) + blob


def setfont(buf):
    """⚠ Group 0 means the BUILT-IN font, and DoFont returns before it looks
    at the second parameter - but the escape's two bytes are collected
    whatever it does with them, so both are always sent."""
    return esc(0x3A, FONT_GRP, buf) if buf else esc(0x3A, 0, 0)


def curxy(cx, cy):
    """⚠ Control $02, and it is in CELLS, not pixels: on a bitmap window a
    cell is the 8 x 8 glyph box, so everything drawn as text here is on an
    8-pixel grid and the layout below is built out of multiples of 8."""
    return bytes([0x02, 32 + cx, 32 + cy])


def ink(fg, bg):
    return esc(0x32, col(fg)) + esc(0x33, col(bg))


def gptext(cx, cy, s, buf=None):
    return (setfont(buf) if buf is not None else b"") + curxy(cx, cy) + s.encode("latin-1")


def stream_wfonts():
    """Every wildbits face into a GP buffer of its own, buffers 1..n.

    ⚠ It is its own stream because it is 55 KB of glyphs and nothing to
    look at: the session copies it while the Paint window is still up, so
    the load is not a scene.  Buffers survive until KillBuf, so v3write and
    v3spec can select any face without loading it again."""
    s = bytearray()
    for i, (_, blob) in enumerate(FACES):
        s += gpfont(i + 1, blob)
    return bytes(s)


# ---------------------------------------------------------- the word processor
WR = (16, 24, 608, 440)                         # the document window
WR_IN = (24, 48, 592, 408)                      # menu bar, ruler and page
MENU = ["File", "Edit", "Search", "Format", "Font", "Style"]
MENU_X = 12                                     # where the first item starts
MENU_GAP = 26

LETTER = [
    "Dear NitrOS-9,",
    "",
    "Twenty-seven typefaces came with wildbits.  Eight pixels on a",
    "side, one glyph every eight bytes, and not one of them is in",
    "this machine's ROM.  They arrive down the same pipe as the",
    "text -- ESC $2B GPLoad -- and live in CoArm's GP buffers, of",
    "which there are forty-eight.",
    "",
    "ESC $3A Font is how a window changes its mind.  The menu to",
    "the right draws every name in its own face, which is the only",
    "honest way to show a font to somebody.",
    "",
    "Yours in 8 x 8,",
    "         a 6309 at 2.1 MHz",
]


def menu_x(i):
    """Where item i starts, measured in the ROM's own Noto Sans - the same
    host-side measurement the doodle's balloon uses, because there is no
    measure-string call on the far side of the escape."""
    x = MENU_X
    for m in MENU[:i]:
        x += T.text_width(m) + MENU_GAP
    return x


def wr_chrome(s, title="Untitled"):
    """The window, its menu bar and its ruler - all ROM toolbox."""
    x, y, w, h = WR
    ix, iy, iw, ih = WR_IN
    s += window(x, y, w, h, title, 1)
    s += rect(ix, iy, iw, 24, "panel")
    s += grad(ix, iy, iw, 24, T.GREYG, 8)
    for i, m in enumerate(MENU):
        s += text(ix + menu_x(i), iy + 3, m, "menu")
    s += rect(ix, iy + 23, iw, 1, "frame")
    # the ruler: a tick every half inch, a number every inch, and the two
    # margin markers - 8 px to the inch here, because the page is in cells
    s += rect(ix, iy + 24, iw, 24, "white")
    s += rect(ix, iy + 47, iw, 1, "frame")
    for n in range((iw - 32) // 32 + 1):
        tx = ix + 16 + n * 32
        s += rect(tx, iy + 38, 1, 8, "frame")
        if n % 2 == 0:
            s += rect(tx, iy + 32, 1, 14, "frame")
            s += text(tx + 3, iy + 26, str(n // 2), "white")
    for mx in (ix + 16, ix + iw - 48):           # the margin markers
        for k in range(5):
            s += rect(mx - 4 + k, iy + 42 - k, 9 - 2 * k, 1, "black")
    return s


def stream_write():
    """⭐ THE FONT MENU, EVERY NAME IN ITS OWN FACE - which is the one thing
    a word processor can show that a specimen sheet cannot.  A letter on the
    page in one face, and the menu open over it in twenty-seven."""
    ix, iy, iw, ih = WR_IN
    px, py = ix, iy + 48                        # the page, below the ruler
    ph = ih - 48
    s = bytearray()
    s += dwset(0xFF, 0, 0, 80, 60, PAL["black"], PAL["desk"])
    s += SELECT + CURSOR_OFF
    s = wr_chrome(s)
    s += rect(px, py, iw, ph, "white")
    # the letter, in one face, on the page's 8-pixel grid
    body = next(i for i, (n, _) in enumerate(FACES) if n == "c256serif") + 1
    s += ink("black", "white")
    for i, line in enumerate(LETTER):                # two cells a line: an
        s += gptext(px // 8 + 2, py // 8 + 2 + 2 * i,  # 8 x 8 face set solid
                    line, body if i == 0 else None)    # has no room under it
    # ⭐ and the Font menu, pulled down, item by item in its own face
    mx = ix + menu_x(4) - 6
    mw, mh = 8 * 13 + 12, len(FACES) * 8 + 8
    my = iy + 24
    s += rect(mx + 4, my + 4, mw, mh, "shadow")
    s += rect(mx, my, mw, mh, "white")
    s += rect(mx, my, mw, 1, "frame") + rect(mx, my + mh - 1, mw, 1, "frame")
    s += rect(mx, my, 1, mh, "frame") + rect(mx + mw - 1, my, 1, mh, "frame")
    for i, (name, _) in enumerate(FACES):
        row = (my + 4) // 8 + i
        if i + 1 == body:                       # the one the letter is set in
            s += rect(mx + 1, row * 8, mw - 2, 8, "sel")
            s += ink("white", "sel")
        else:
            s += ink("black", "white")
        s += gptext(mx // 8 + 1, row, name[:13], i + 1)
        if i + 1 == body:
            sel_y = row * 8
    s += ink("black", "white")
    s += put_gc(mx + mw - 24, sel_y)                 # the pointer, on the choice
    return bytes(s)


def stream_spec():
    """The same window with the menu closed and the page given over to a
    specimen: two columns, every face setting the same line.

    ⚠ The pitch is 24 px and not 20, because text is placed in CELLS -
    a row is 8 px and nothing lands between two of them."""
    ix, iy, iw, ih = WR_IN
    px, py = ix, iy + 48
    ph = ih - 48
    rows = (len(FACES) + 1) // 2
    s = bytearray()
    # ⚠ NO DWSet: v3write already defined this device's window and a second
    # one is E$WADef, "Window already defined" - the same rule stream_cmds
    # and stream_about follow on /W3.  It draws into the window that is there.
    s = wr_chrome(s, "Specimen")
    s += rect(px, py, iw, ph, "white")
    # ⚠ ONE header line, and the rows start at py + 32: fourteen of them at
    # a 24 px pitch is 320 px, and the page has 360.  Two header lines pushed
    # the last row's glyphs past the bottom of the window.
    s += text(px + 16, py + 6, "the name in Noto Sans, the sample in the face",
              "white", bold=True)
    s += ink("black", "white")
    for i, (name, _) in enumerate(FACES):
        cx = px + 16 + (i // rows) * (iw // 2 - 8)
        y = py + 32 + (i % rows) * 24
        s += text(cx, y - 2, name, "white")
        s += gptext(cx // 8 + 11, y // 8, "Quick brown fox 019", i + 1)
    return bytes(s)


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

    # ⛔ NO SHADED BACKDROP.  This used to fill all 25 rows with the light
    # shade block in blue, the way ANSI art fakes a mid-tone - an emulation of
    # gruvbox's #282828 out of CP437.  The palette already HAS #282828 at
    # index 0 (GRUVBOX above), so the field is the background colour itself:
    # the same grey, no dither, and 2,000 fewer cells to draw.
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
  320 bytes a row, 59 rows, about 4.7 ms of engine and six register writes.

--------------------------------------------------------------------------------
 1. Modes
--------------------------------------------------------------------------------

  CTRL b3-2 selects one of three:

    00  bitmap      640 x 200 / 240 / 400 / 480, eight bits a pixel
    01  character   80 x 25 / 30 / 50 / 60, four bytes a cell
    10  tile        8 x 8 tiles of eight-bit pixels, a code in four bytes

  The timing is inherited from video/ unchanged: one 25.175 MHz dot clock,
  800 dots a line, and two vertical families of 449 and 525 lines.

--------------------------------------------------------------------------------
 2. Character mode
--------------------------------------------------------------------------------

  A cell is four bytes - a CP437 code, an ATTR byte and two the card
  never reads: the map fetcher has sixteen data pins.

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
      the copy engine     1.9 ms of engine       six writes + the clear
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

  One 16 x 16 sprite, two bits a pixel, for the mouse pointer.  Its shape
  is 64 bytes of VRAM - the top of MAPBASE's 64 K, which bitmap mode does
  not otherwise use - and it is composed at scan time: nothing is saved
  behind it and nothing has to be put back.  Moving it is three register
  writes.

--------------------------------------------------------------------------------
 6. Memory
--------------------------------------------------------------------------------

      framebuffer    2 x AS6C8016          512K x 16, 55 ns
      palette LUT    1 x IS61C6416AL-12    64K x 16
      register file  1 x 32K x 8           20 ns

      rows 0-479                the picture, 1024-byte stride
      rows 480-511              off-screen scratch for the copy engine
      row 511, columns 960-1023 the sprite's shape, at MAPBASE 7
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


# --------------------------------------------------------- the ANSI art
# ⭐ A REAL .ans, drawn by the ANSI terminal itself: "we-tortuga" from
# Blocktronics' 2016 "Block 'n' Roll" pack (16colo.rs), 80 x 889 of CP437.
#
# ⚠ It is PARSED here and re-emitted, rather than copied: the file is 164 KB
# and the whole piece takes 100 s on the card, because dense art changes
# colour almost every cell and every cell then pays the per-character path.
# Re-emitting lets the demo show a window of it, drops CUF for the spaces it
# stands for, and keeps the stream to the sequences ca_ext.asm implements.
#
# ⭐ SAUCE's flags bit 0 is iCE COLOUR: SGR 5 is the bright background, not
# blink, which is why ca_ext.asm learned SGR 5 and 25.
ART = pathlib.Path(__file__).resolve().parents[3] / "video3" / "we-tortuga.ans"
# ⭐ The window the demo scrolls: the top of the blue sky down to the bottom
# of the pirate with the hook - rows 2270 to 6500 of we-tortuga.ans.png, which
# is 8 x 16 a cell, so rows 142 to 406 of the grid.
#
# ⚠ THE PICTURE IS THE ARBITER OF WHERE THINGS ARE, not this decoder's idea
# of which index is blue: the window was first chosen 435 rows too low because
# VGA16 below was in attribute order, so the sky read red.
ART_FROM = int(os.environ.get("V3ART_FROM", "142"))
ART_ROWS = int(os.environ.get("V3ART_ROWS", "265"))


def have_art():
    """⚠ we-tortuga.ans IS NOT THIS PROJECT'S WORK and is not in the repository,
    the same way software/demo's photograph is not: put it in video3/ (it is in
    Blocktronics' 2016 "Block 'n' Roll" pack, on 16colo.rs) and the scene comes
    back.  Without it the session simply skips those three commands."""
    return ART.exists()


def art_grid(width=80):
    """The .ans as rows of (code, fg, bg).  SGR and CUF are all it uses."""
    d = ART.read_bytes()
    i = d.rfind(b"SAUCE")
    if i >= 0 and d[i:i + 5] == b"SAUCE":
        d = d[:i]
    d = d.split(b"\x1a")[0]
    rows, row = [], []
    fg, bg, bold, ice, rev = 7, 0, 0, 0, 0
    def cell(c):
        f, b = (fg + 8) if bold and fg < 8 else fg, (bg + 8) if ice and bg < 8 else bg
        return (c, b, f) if rev else (c, f, b)
    p = 0
    while p < len(d):
        b = d[p]
        if b == 0x1B and p + 1 < len(d) and d[p + 1] == ord("["):
            m = re.match(rb"\x1b\[([0-9;]*)([A-Za-z])", d[p:])
            if not m:
                p += 1
                continue
            args = [int(x) if x else 0 for x in m.group(1).split(b";")] or [0]
            if m.group(2) == b"m":
                for a in args:
                    if a == 0: fg, bg, bold, ice, rev = 7, 0, 0, 0, 0
                    elif a == 1: bold = 1
                    elif a == 5: ice = 1
                    elif a == 7: rev = 1
                    elif a == 22: bold = 0
                    elif a == 25: ice = 0
                    elif a == 27: rev = 0
                    elif 30 <= a <= 37: fg = a - 30
                    elif 40 <= a <= 47: bg = a - 40
            elif m.group(2) == b"C":
                for _ in range(max(1, args[0])):
                    row.append(cell(32))
                    if len(row) >= width:
                        rows.append(row); row = []
            p += m.end()
            continue
        if b == 0x0A:
            rows.append(row); row = []
        elif b != 0x0D:
            row.append(cell(b))
            if len(row) >= width:
                rows.append(row); row = []
        p += 1
    if row:
        rows.append(row)
    for r in rows:
        while len(r) < width:
            r.append((32, 7, 0))
    return rows


# The DOS palette the artist drew against.  ⚠ The BBS screen before this one
# puts GRUVBOX in the same sixteen entries - that is its point - so the art
# loads its own first, and a character screen takes a palette change live
# (ca_v3txt.asm's TxPalQ reloads the pairs).
# ⛔ IN SGR ORDER, NOT VGA ATTRIBUTE ORDER.  art_grid() stores the SGR colour
# number (30+n), and that is the index the card's palette is written with, so
# 1 is red and 4 is blue - the DOS attribute table has those two the other way
# round and the sky came out red.  This is we-tortuga.ans.png's own palette.
VGA16 = ["000000", "aa0000", "00aa00", "aa5500", "0000aa", "aa00aa", "00aaaa", "aaaaaa",
         "555555", "ff5555", "55ff55", "ffff55", "5555ff", "ff55ff", "55ffff", "ffffff"]


def stream_pal():
    """The DOS palette, on its own.  ⛔ IT CANNOT TRAVEL WITH THE ART: an ANSI
    terminal passes only ESC [, ESC $69, ESC $21 and ESC $24 through
    (ca_ext.asm's AnsiByte), so a PalRange sent while ANSI is on is dropped
    with no error - the art then drew in the BBS screen's gruvbox, which is
    red where the sky is blue.  The session copies this one first, while the
    terminal is still off."""
    return esc(0x61, 0, 16) + b"".join(
        T.rgb565(tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))).to_bytes(2, "big") for h in VGA16)


def stream_art():
    """ART_ROWS rows of the piece from ART_FROM, as SGR and CP437 - one SGR
    where the colour changes, and nothing our terminal does not implement."""
    rows = art_grid()[ART_FROM:ART_FROM + ART_ROWS]
    out = bytearray()
    out += b"\x1b[0m\x1b[2J\x1b[H"                  # the piece starts on a clear screen
    fg = bg = None
    for r in rows:
        # ⚠ A ROW THAT FILLS THE WIDTH TAKES NO NEWLINE: the terminal wraps,
        # and a CR LF after it would leave a blank row between every two - the
        # same wrap-then-newline the 80-character lines of video3.txt show.
        end = len(r)
        while end and r[end - 1][0] == 32 and r[end - 1][2] == 0:
            end -= 1
        line = bytearray()
        for code, f, b in r[:end]:
            if f != fg or b != bg:
                # ⚠ bold and iCE are STATE: 1 without a later 22 leaves every
                # following colour bright, which is 481 cells of this piece
                p = []
                if (f >= 8) != (fg is not None and fg >= 8):
                    p.append(1 if f >= 8 else 22)
                if (b >= 8) != (bg is not None and bg >= 8):
                    p.append(5 if b >= 8 else 25)
                p.append(30 + (f & 7))
                p.append(40 + (b & 7))
                line += b"\x1b[" + b";".join(b"%d" % n for n in p) + b"m"
                fg, bg = f, b
            line += bytes([code])
        out += line
        if end < len(r):
            # ⚠ The trimmed blanks and the next row's leading ones inherit the
            # colour state, so a coloured background would run on across them.
            if bg not in (0, None):
                out += b"\x1b[0m"
                fg, bg = 7, 0
            out += b"\r\n"
    return bytes(out)


def stream_text():
    """A long plain-text file for `list` on the 80 x 60 console, so the
    copy-engine scroll has something to scroll.  OS-9 ends a line with CR;
    the text is CP437."""
    return TEXT.replace("\n", "\r").encode("cp437")


def main(out):
    d = pathlib.Path(out); d.mkdir(parents=True, exist_ok=True)
    streams = [("v3desk", stream_desk), ("v3cmds", stream_cmds), ("v3about", stream_about),
               ("v3paint", stream_paint), ("v3draw", stream_draw),
               ("v3menu", stream_menu), ("v3open", stream_open),
               ("v3load", stream_load), ("v3shut", stream_shut),
               ("v3bbs", stream_bbs), ("video3.txt", stream_text)]
    if FACES:
        streams[5:5] = [("v3fonts", stream_wfonts), ("v3write", stream_write),
                        ("v3spec", stream_spec)]
    else:
        print("note  no wildbits fonts: the word processor scene is left out")
    if have_art():
        streams[6:6] = [("v3pal", stream_pal), ("v3art", stream_art)]
    else:
        print("note  no %s: the ANSI art scene is left out (see art_grid)" % ART.name)
    # ⭐ every wildbits face as a file of its own, for `changefont`: 2,048
    # bytes, exactly the glyph bank's format, so the command reads it and
    # hands it straight to SS.CFont.
    for name, blob in FACES + F.BUILTIN:
        (d / ("font." + name)).write_bytes(blob)
    if FACES:
        print("ok    %s/font.*: %d faces, %d bytes" %
              (out, len(FACES), sum(len(b) for _, b in FACES)))
    for name, fn in streams:
        b = fn()
        (d / name).write_bytes(b)
        print("ok    %s/%s: %d bytes" % (out, name, len(b)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/v3sys")
