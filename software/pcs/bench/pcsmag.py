#!/usr/bin/env python3
"""pcsmag.py - the MAGNIFIER and the free-hand layer, modelled (pcs.md §8).

EDIT.s's MAGNIFY blows a 16 x 14 patch of the screen up seven times in the kit
and lets a pixel be toggled in it; what it toggles is the hi-res screen itself,
so the drawing is whatever the screen holds, and DISK.s RLE-compresses the
screen to save it.  This machine keeps no picture of the table - the span
database IS the picture (pcs.md §2) - so the free-hand drawing is a LAYER of
its own: world pixels, each a palette index, composed over the spans and under
the parts' art on every repaint.

⭐ THE LAYER IS A WHOLE BITMAP, IN RAM OF ITS OWN.  160 x 240 bytes do not
belong in a 64 KB logical map that the core, its data and two windows already
fill - so the layer is eight blocks from F$AllRAM, 32 world rows of 256 bytes
each, paged through the LIBRARY window - pcs has no free slot of its own to
give it - by core code that puts the caller's library back before it returns
(pcsdraw.inc's LyOpen / LyClose).  Every pixel of the table can be drawn on;
there is no capacity to refuse.

⚠ THE ARTIFACT COLOUR IS NOT COPIED.  The Apple II's fat bits show NTSC
artifact colours in their colour mode; here a pixel is a palette index and the
fat bit shows that index.

This module is the model: `checkpcs.py` applies each gesture through it and
compares the records, the layer, the table picture and the fat bits.
"""

TW, TH = 160, 240
MAX = TW * TH               # a trailer's largest count

# The viewer: MW x MH world pixels, each a CELL-pixel square in the kit, the
# fat bit FAT x FAT at (+1, +1) inside it and the grid between in PCC.Dark.
MW, MH = 24, 40
CELL, FAT = 8, 6
VX, VY = 332, 16            # card pixels: the viewer's corner
VW, VH = MW * CELL + 1, MH * CELL + 2
QX, QY, QW, QH = 336, 368, 64, 24     # QUIT
TOOLX = 268                 # world x of the tool column: a press there ends it

# The box on the table: a 2-pixel frame just OUTSIDE the viewed rectangle,
# so the pixels the viewer reads are never the frame's.
BX0, BY0 = 68, 100          # where it starts
BXMAX, BYMAX = TW - MW - 1, TH - MH - 1     # 135, 199: the frame stays
                                            # inside the table's 320 x 480

PCC_PANEL, PCC_DARK, PCC_INK, PCC_HILITE = 16, 18, 19, 20

# the records' op[1] kinds (EDL.* in pcsui.inc), after 0..3
EDL_MBOX, EDL_PLOT, EDL_MQUIT = 4, 5, 6


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def box_at(rwx, rwy):
    """A press on the table moves the box, CENTRED on where it is let go."""
    return clamp(rwx - MW // 2, 1, BXMAX), clamp(rwy - MH // 2, 1, BYMAX)


def in_viewer(px, py):
    return VX <= px < VX + MW * CELL and VY <= py < VY + MH * CELL


def in_quit(px, py):
    return QX <= px < QX + QW and QY <= py < QY + QH


def fat(px, py):
    """The fat bit a card point is in, clamped into the viewer - a release
    outside it still ends the line at its edge."""
    return (clamp((px - VX) // CELL, 0, MW - 1),
            clamp((py - VY) // CELL, 0, MH - 1))


def line(x0, y0, x1, y1):
    """Bresenham, both ends included - exactly MgLine's walk."""
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x1 >= x0 else -1
    sy = 1 if y1 >= y0 else -1
    err = dx - dy
    out = []
    x, y = x0, y0
    while True:
        out.append((x, y))
        if (x, y) == (x1, y1):
            return out
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


class Layer:
    def __init__(self, triples=()):
        self.px = dict(((x, y), c) for (y, x, c) in triples)

    def triples(self):
        return sorted((y, x, c) for (x, y), c in self.px.items())

    def plot(self, pts, c):
        """One gesture: the whole line in the brush's colour - or, if the
        press was on a pixel already that colour, the whole line erased."""
        c0 = self.px.get(pts[0], 0)
        cc = 0 if c0 == c else c                # the brush's toggle
        for p in pts:
            if cc:
                self.px[p] = cc
            else:
                self.px.pop(p, None)
        return cc

    def blob(self):
        """What mode 23 streams to EditL: the count, big-endian, then the
        triples."""
        t = self.triples()
        out = bytearray([len(t) >> 8, len(t) & 0xFF])
        for y, x, c in t:
            out += bytes([y, x, c])
        return bytes(out)

    def compose(self, fb, w, scale=2):
        """Over the spans, under the art: each pixel a scale x scale square."""
        for (x, y), c in self.px.items():
            for k in range(scale):
                o = (y * scale + k) * w + x * scale
                fb[o:o + scale] = bytes([c]) * scale


def trailer(triples):
    """The file's optional layer section, after the payload: "PL", the count
    big-endian, the triples.  A table with no layer has none, and a reader
    that stops at PF.Len never sees it."""
    if not triples:
        return b''
    out = bytearray(b'PL' + bytes([len(triples) >> 8, len(triples) & 0xFF]))
    for y, x, c in sorted(triples):
        out += bytes([y, x, c])
    return bytes(out)


def frame(fb, w, bx, by):
    """The box on the table: PTFrame round the viewed rectangle, 2 thick."""
    x0, y0 = 2 * bx - 2, 2 * by - 2
    fw, fh = 2 * MW + 4, 2 * MH + 4
    for yy in range(y0, y0 + fh):
        for xx in range(x0, x0 + fw):
            if yy < y0 + 2 or yy >= y0 + fh - 2 or xx < x0 + 2 or xx >= x0 + fw - 2:
                fb[yy * w + xx] = PCC_HILITE


def viewer(table, w, bx, by):
    """The fat bits, as {(card x, card y): index} over the viewer's rectangle:
    the grid in PCC.Dark and each cell the table's pixel at (2x, 2y)."""
    out = {}
    for yy in range(VY, VY + VH):
        for xx in range(VX, VX + VW):
            out[(xx, yy)] = PCC_DARK
    for j in range(MH):
        for i in range(MW):
            c = table[(2 * (by + j)) * w + 2 * (bx + i)]
            for yy in range(VY + CELL * j + 1, VY + CELL * j + 1 + FAT):
                for xx in range(VX + CELL * i + 1, VX + CELL * i + 1 + FAT):
                    out[(xx, yy)] = c
    return out


def demo_layer():
    """The drawing `demo2l.pbt` carries (mkpcs.write_tables, run-pcs.sh's
    `f1`): a disc, a ring round it and a diagonal the height of the table, in
    three colours - 2,000-odd pixels, so the loader's 64-triple chunks turn
    over many times and every row band of the layer's eight blocks is used."""
    px = {}
    for y in range(TH):
        for x in range(TW):
            d2 = (x - 80) ** 2 + (y - 60) ** 2
            if d2 < 14 ** 2:
                px[(x, y)] = 40
            elif 18 ** 2 <= d2 < 21 ** 2:
                px[(x, y)] = 45
    for x, y in line(4, 4, 150, 236):
        px[(x, y)] = 60
    return sorted((y, x, c) for (x, y), c in px.items())


def _selftest():
    assert line(0, 0, 3, 0) == [(0, 0), (1, 0), (2, 0), (3, 0)]
    assert line(2, 2, 2, 2) == [(2, 2)]
    assert line(0, 0, 2, 4)[-1] == (2, 4) and len(line(0, 0, 2, 4)) == 5
    assert len(line(0, 0, 23, 39)) == 40
    L = Layer()
    assert L.plot(line(0, 0, 3, 0), 40) == 40 and len(L.px) == 4
    assert L.plot([(0, 0)], 40) == 0 and len(L.px) == 3         # toggled off
    assert L.plot(line(1, 0, 1, 5), 41) == 41
    assert L.triples()[0] == (0, 1, 41)
    L2 = Layer([(k % TH, k // TH, 5) for k in range(MAX)])      # every pixel
    assert len(L2.px) == MAX and len(L2.blob()) == 2 + 3 * MAX
    assert box_at(0, 0) == (1, 1) and box_at(159, 239) == (135, 199)
    assert fat(0, 0) == (0, 0) and fat(639, 479) == (MW - 1, MH - 1)
    assert all(c and y < TH and x < TW for y, x, c in demo_layer())
    assert trailer([]) == b'' and trailer([(1, 2, 3)]) == b'PL\x00\x01\x01\x02\x03'
    print('ok    pcsmag: Bresenham, the toggle, a full layer, the box')


if __name__ == '__main__':
    _selftest()
