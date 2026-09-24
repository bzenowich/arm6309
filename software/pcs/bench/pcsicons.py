#!/usr/bin/env python3
"""pcsicons.py - the editor's tool icons, redrawn at the card's own resolution.

⭐ THE ORIGINAL'S ICONS WERE DRAWN FOR A 160-UNIT PANEL, one Atari hi-res pixel
per world unit, and the port doubles every unit to 2 x 2 card pixels.  These
are drawn at the CARD's resolution instead - twice as fine each way - as white
shapes on the black panel, and nothing about the editor's interaction changes:
⛔ EACH ICON IS CENTRED IN ITS TOOL'S OWN RECTANGLE (CMDMENU's, EDIT.s:1166),
which stays exactly where the original put it.  The hit test is the rectangle;
the picture is only what is drawn inside it.

The bin's parts are NOT redrawn: their pictures are the parts' own art, which is
also what the table shows, and the two must agree.  The bin's polygon entry is,
because it is an icon and not a part's picture.

How: each shape is drawn with PIL at 8x, reduced with a box filter, and
thresholded at half - which gives clean one-bit edges on curves and diagonals.
The strokes are two card pixels, one world unit, so the icons have the weight
of the rest of the kit.

    icons()    [(name, x, y, w, h, rows)] - card pixels, x from the panel's
               left edge; rows is h lists of w 0/1
    packed()   the same as the machine stores them: (name, x, y, wbytes, h,
               bytes), rows MSB first and padded to whole bytes
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image, ImageDraw                               # noqa: E402

S = 8                   # the supersampling factor
STROKE = 2              # card pixels


# ── drawing helpers, in CARD pixels of the icon's own box ─────────────────
class Pen(object):
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.im = Image.new('L', (w * S, h * S), 0)
        self.d = ImageDraw.Draw(self.im)

    def _p(self, pts):
        return [(x * S, y * S) for (x, y) in pts]

    def poly(self, pts, fill=True, width=STROKE):
        if fill:
            self.d.polygon(self._p(pts), fill=255)
        else:
            self.d.line(self._p(pts + pts[:1]), fill=255, width=int(width * S),
                        joint='curve')

    def line(self, pts, width=STROKE):
        self.d.line(self._p(pts), fill=255, width=int(width * S), joint='curve')
        # round the ends, so a stroke is a capsule and not a sheared bar
        r = width * S / 2
        for (x, y) in (pts[0], pts[-1]):
            self.d.ellipse((x * S - r, y * S - r, x * S + r, y * S + r), fill=255)

    def disc(self, cx, cy, r, fill=True, width=STROKE):
        box = ((cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S)
        if fill:
            self.d.ellipse(box, fill=255)
        else:
            self.d.ellipse(box, outline=255, width=int(width * S))

    def ellipse(self, box, fill=False, width=STROKE):
        b = tuple(v * S for v in box)
        if fill:
            self.d.ellipse(b, fill=255)
        else:
            self.d.ellipse(b, outline=255, width=int(width * S))

    def rect(self, box, fill=True, width=STROKE, radius=0):
        b = tuple(v * S for v in box)
        if fill:
            self.d.rounded_rectangle(b, radius=radius * S, fill=255)
        else:
            self.d.rounded_rectangle(b, radius=radius * S, outline=255,
                                     width=int(width * S))

    def erase_rect(self, box):
        self.d.rectangle(tuple(v * S for v in box), fill=0)

    def erase_disc(self, cx, cy, r):
        self.d.ellipse(((cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S),
                       fill=0)

    def rows(self):
        small = self.im.resize((self.w, self.h), Image.BOX)
        px = small.load()
        return [[1 if px[x, y] >= 128 else 0 for x in range(self.w)]
                for y in range(self.h)]


# ── the icons.  Each is (w, h, draw) and draw takes a Pen. ────────────────
def _hand(p):
    # an open hand, palm down-left, four fingers up and the thumb out
    p.rect((6, 12, 21, 25), radius=5)                       # the palm
    for i, (x, top) in enumerate(((7, 4), (11, 1), (15, 2), (19, 5))):
        p.rect((x, top, x + 3, 16), radius=1.5)             # the fingers
    p.line([(7, 18), (2, 12)], width=4)                     # the thumb
    return p


def _pointer(p):
    # the arrow: tip at the top left, a tail down and to the right
    p.poly([(1, 0), (1, 14), (4.5, 10.5), (7.5, 16), (10, 14.8),
            (7, 9.5), (12, 9.5)])
    return p


def _scissors(p):
    # two blades crossing at the pivot, two finger rings below
    p.line([(4, 1), (15, 17)], width=2.5)
    p.line([(20, 1), (9, 17)], width=2.5)
    p.disc(7, 21, 4, fill=False)
    p.disc(17, 21, 4, fill=False)
    p.disc(12, 9.5, 1.3)                                    # the pivot
    p.erase_disc(12, 9.5, 0.1)
    return p


def _hammer(p):
    # a claw hammer: the striking face left, the head, a claw curling down
    # to the right, and the handle
    p.rect((1, 2, 6, 10), radius=1)                         # the face
    p.rect((5, 3.5, 15, 8.5))                               # the head
    p.poly([(14, 3.5), (19, 4.5), (23.5, 8), (25, 12), (22.5, 12.5),
            (20, 9), (16, 8.5), (14, 8.5)])                 # the claw
    p.rect((8, 8, 12, 25), radius=1.5)                      # the handle
    return p


def _brush(p):
    # a brush laid diagonally: a fat head of bristles bottom left, a band,
    # and the handle up to the right
    p.line([(15, 6.5), (26, 1)], width=3)                   # the handle
    p.poly([(10, 7), (13.5, 4), (16.5, 8), (13, 11)])       # the ferrule
    p.poly([(9, 8), (13.5, 12.5), (10, 17), (5, 19.5), (1, 19.5),
            (1.5, 15), (4.5, 10.5)])                        # the bristles
    p.line([(4, 16.5), (9.5, 11)], width=0.9)               # ... split once
    return p


def _play(p):
    # a flipper and a ball: what the Play button starts
    p.poly([(1.5, 6.5), (6.5, 0.5), (25, 16), (23.5, 18.5)])  # the bat
    p.disc(4.5, 4.5, 4.2)                                   # ... its pivot
    p.disc(25, 6, 3.4)                                      # the ball
    return p


def _magnifier(p):
    p.disc(10, 10, 7.5, fill=False, width=2.5)              # the lens
    p.line([(15.5, 15.5), (23, 23)], width=4)               # the handle
    return p


def _world(p):
    # a globe: its outline, one meridian and the equator
    p.disc(12, 12, 11, fill=False)
    p.ellipse((7, 1, 17, 23), width=1.6)
    p.line([(1.5, 12), (22.5, 12)], width=1.6)
    return p


def _wire(p):
    # an AND gate: the D, two inputs and an output, a dot at each end
    p.d.arc((5 * S, 2 * S, 25 * S, 20 * S), 270, 90, fill=255,
            width=int(STROKE * S))
    p.line([(15, 2), (9, 2), (9, 20), (15, 20)])
    p.line([(3, 6), (9, 6)])
    p.line([(3, 16), (9, 16)])
    p.line([(25, 11), (31, 11)])
    for (x, y) in ((2, 6), (2, 16), (32, 11)):
        p.disc(x, y, 2)
    return p


def _disk(p):
    # a 3.5" floppy: the case with a clipped corner, the shutter, the label
    p.poly([(1, 1), (19, 1), (23, 5), (23, 23), (1, 23)])
    p.erase_rect((6, 1, 17, 8))                             # the shutter slot
    p.rect((13, 2.5, 16, 7))                                # its window
    p.erase_rect((4.5, 13, 19.5, 23))                       # the label
    p.rect((7, 16, 17, 17))                                 # ... two lines on it
    p.rect((7, 19.5, 17, 20.5))
    return p


def _poly(p):
    # the bin's "new polygon": a quadrilateral and its vertex dots
    pts = [(4, 4), (26, 6), (24, 26), (6, 22)]
    p.poly(pts, fill=False)
    for (x, y) in pts:
        p.rect((x - 2.5, y - 2.5, x + 2.5, y + 2.5))
    return p


# (the tool's name in CMDMENU, the icon's box w x h, the drawing)
TOOL_ICONS = (
    ('HAND', 26, 26, _hand),
    ('POINTER', 13, 17, _pointer),
    ('SCISSOR', 24, 26, _scissors),
    ('HAMMER', 26, 26, _hammer),
    ('BRUSH', 28, 20, _brush),
    ('PLAY', 30, 20, _play),
    ('MAGN', 24, 24, _magnifier),
    ('WORLD', 24, 24, _world),
    ('WIRE', 35, 22, _wire),
    ('DISK', 24, 24, _disk),
)


def icons():
    """Every icon, placed: centred in its tool's rectangle, card pixels from
    the panel's left edge (world x 160)."""
    import pcskit
    rects = dict((n, (x, y, w, h)) for n, x, y, w, h in pcskit.tools())
    out = []
    for name, w, h, draw in TOOL_ICONS:
        rx, ry, rw, rh = rects[name]
        cx, cy, cw, ch = 2 * (rx - pcskit.KX), 2 * ry, 2 * rw, 2 * rh
        if w > cw - 4 or h > ch - 2:   # ⚠ a pixel clear top and bottom
            raise ValueError('%s: a %d x %d icon does not fit its %d x %d '
                             'rectangle' % (name, w, h, cw, ch))
        x, y = cx + (cw - w) // 2, cy + (ch - h) // 2
        out.append((name, x, y, w, h, draw(Pen(w, h)).rows()))
    # ⭐ The bin's polygon entry, in POLYB's box (EDIT.s:1408), card pixels.
    bx, by, bw, bh = pcskit.bin_boxes()[0]
    cx, cy, cw, ch = 2 * (bx - pcskit.KX), 2 * by, 2 * bw, 2 * bh
    out.append(('POLY', cx + (cw - 30) // 2, cy + (ch - 30) // 2, 30, 30,
                _poly(Pen(30, 30)).rows()))
    return out


def packed():
    out = []
    for name, x, y, w, h, rows in icons():
        wb = (w + 7) // 8
        data = bytearray()
        for r in rows:
            r = r + [0] * (wb * 8 - w)
            for i in range(0, len(r), 8):
                v = 0
                for b in r[i:i + 8]:
                    v = (v << 1) | b
                data.append(v)
        out.append((name, x, y, wb, h, bytes(data)))
    return out


def selftest():
    import pcskit
    bad = []
    ics = icons()
    rects = dict((n, (x, y, w, h)) for n, x, y, w, h in pcskit.tools())
    for name, x, y, w, h, rows in ics:
        if not any(any(r) for r in rows):
            bad.append('%s is empty' % name)
        if name in rects:
            rx, ry, rw, rh = rects[name]
            if not (2 * (rx - pcskit.KX) <= x and x + w <= 2 * (rx - pcskit.KX + rw)
                    and 2 * ry <= y and y + h <= 2 * (ry + rh)):
                bad.append('%s leaves its rectangle' % name)
    for m in bad:
        print('FAIL  %s' % m)
    if not bad:
        print('ok    %d icons redrawn at card resolution, each inside its own\n'
              "      tool's rectangle" % len(ics))
    return not bad


if __name__ == '__main__':
    sys.exit(0 if selftest() else 1)
