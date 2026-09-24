#!/usr/bin/env python3
"""pcskit.py - the editor's kit panel: the tool bar and the parts bin.

⛔ READ OUT OF EDIT.s, NOT REDRAWN.  `DRAWKIT` (EDIT.s:220) clears `KITB` and
then XOR-draws the 52 entries of `ICONS` - thirteen tools and the frame-0
picture of every part in the bin - and scan-converts the four plain polygons
in `POLYS`.  This does the same, in the same order, at the Atari's own
resolution: one bit per world unit, which is one hi-res pixel, 160 x 192.

⭐ THE KIT IS MONOCHROME, and that is not a simplification: every icon is 1bpp
and all four bin polygons fill with `$FF`.  The colour is the PICKER, which is
this port's and not the original's: EDIT.s offered three paint pots (`$FF`,
`$55`, `$AA` - artefact colours on the Atari), and here a 12 x 10 grid of
palette entries 32..151 replaces them (pcspal.PICK), centred in the panel under
the tool column, 8 x 8 card pixels a cell.  ⛔ So the pots are NOT drawn: the
three rectangles CMDMENU still lists for them are empty panel.

⚠ AND THE MACHINE DOES NOT SCAN-CONVERT THE KIT'S POLYGONS: their x runs to
243 in a panel that starts at 160, and the port's converter is one byte of x
over a 160-wide table.  They are rendered here, into the bitmap, once.

The outputs:
    bits()      160 x 192, 0/1 - what DRAWKIT leaves in KITB, without the pots
    card(cur)   320 x 480 palette indices - the panel column as the card shows
                it, the picker and its frame on cell `cur` included; what the
                bench compares
    tools()     [(name, x, y, w, h)] - CMDMENU's hit rectangles, in order
    picker()    (x, y, cell) in card pixels, from the panel's left edge
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pcsasm as A                                             # noqa: E402
import pcsparts as T                                           # noqa: E402
import pcspak as K                                             # noqa: E402

KX, KW, KH = 160, 160, 192      # KITB: x 160..319, y 0..191 (EDIT.s:1378)

# ⭐ CMDMENU (EDIT.s:1166) pairs each tool's hit rectangle with its handler, in
# this order - and the order IS the menu's, so the index is the tool.
TOOLS = ('HAND', 'POINTER', 'SCISSOR', 'HAMMER', 'BRUSH',
         'WHITE', 'GREEN', 'VIOLET', 'PLAY', 'MAGN', 'WORLD', 'WIRE', 'DISK')

# The pots, which the picker replaces and which are therefore not drawn.
POTS = ('WHITEPAINT', 'GREENPAINT', 'VIOLETPAINT')

# ⭐ The picker, in CARD pixels from the panel's left edge: 12 x 10 cells of
# 8 x 8, centred across the panel and starting just under the tool column,
# whose last rectangle (DISK) ends at world row 174 - card row 349.
CELL = 8
PICKX = (2 * KW - 12 * CELL) // 2          # 112: panel x 112..207
PICKY = 360                                 # rows 360..439
# ⭐ ... and a white box round it, a pixel thick with two pixels of panel
# between it and the cells (asked for on 2026-09-24).
BOXGAP = 2


def rect(label):
    """A GETRECT record (CDRAW.s:276): top, left byte, left bit, height, width
    bytes, width bits.  -> (x, y, w, h), INCLUSIVE of the far edges exactly as
    INRECT tests them, so w and h are one more than the record's."""
    b = A.block('EDIT.s', label)
    top, ld8, lm8, h, wd8, wm8 = b[:6]
    return (ld8 * 8 + lm8, top, wd8 * 8 + wm8 + 1, h + 1)


def _icon(label):
    """A self-contained icon: `DA *+7` then VERT, HDIV8, HMOD8, HEIGHT, WIDTH
    and the bitmap.  -> (x, y, h, wbytes, bits)."""
    parts = A._block_parts('EDIT.s', label)
    raw = b''.join(c for k, c in parts if k == 'HEX')
    vert, d8, m8, h, w = raw[:5]
    return d8 * 8 + m8, vert, h, w, raw[5:5 + h * w]


def _xor(canvas, x0, y0, h, w, bits):
    for r in range(h):
        for c in range(w):
            byte = bits[r * w + c]
            for b in range(8):
                if byte & (0x80 >> b):
                    x, y = x0 + c * 8 + b - KX, y0 + r
                    if 0 <= x < KW and 0 <= y < KH:
                        canvas[y][x] ^= 1


_cache = {}


def _render():
    if 'bits' in _cache:
        return _cache['bits']
    canvas = [[0] * KW for _ in range(KH)]
    tmpl = dict((t.name, t) for t in T.parts())
    for sym in A.block_syms('EDIT.s', 'ICONS'):
        name = sym.split('+')[0].strip()
        if name in tmpl:
            # ⭐ `DA BMP1+$13` points at the template's own L[0]: its picture
            # is the part's frame 0, where the template's header says.
            t = tmpl[name]
            h, w, bits, dy = t.frames()[0]
            _xor(canvas, t.px, t.vert + dy, h, w, bits)
            continue
        # ⭐ Every other entry is a TOOL icon (or the bin's polygon icon), and
        # those are redrawn at the card's resolution by pcsicons.py - so they
        # are not in this bitmap at all.  The pots are gone to the picker.
        continue
    # ⭐ POLYS (EDIT.s:1547) - DRAWOBJ with SCANMODE $80, so drawn and never
    # merged into the database.  ⚠ Scanned in a 320-wide world, because their
    # x is in the kit.
    for sym in A.block_syms('EDIT.s', 'POLYS'):
        t = tmpl[sym.strip()]
        o = K.Obj(t.objid, t.fillcolor, list(t.x), list(t.y), None)
        o.align()
        pak = K.Pak(height=KH, width=2 * KW)
        pak.objs = [o]
        pak.display()
        for y, recs in enumerate(pak.rows):
            for rec in recs:
                for x in range(rec[0], rec[2] + 1):
                    if KX <= x < KX + KW:
                        canvas[y][x - KX] ^= 1
    _cache['bits'] = canvas
    return canvas


def bits():
    return _render()


def picker():
    return PICKX, PICKY, CELL


def frame_colour(i):
    """The current cell's frame: white on a dark cell and INK on a light one,
    because a white frame round the white cell is no frame at all."""
    import pcspal
    v = pcspal.PICK[i]
    r, g, b = (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF
    # ⚠ Ink is white on the black panel, so "dark" is the picker's own black
    # cell (row 0, column 11) and not UI_INK.
    return pcspal.PICK0 + 11 if (299 * r + 587 * g + 114 * b) > 150000 \
        else pcspal.PAINT0          # entry 1 is white


def tools():
    return [(n,) + rect(n + 'B') for n in TOOLS]


def bin_boxes():
    """The 43 parts-bin hit rectangles, BOXLO/BOXHI's order (EDIT.s:1194)."""
    names = A.block_syms('EDIT.s', 'BOXLO')
    return [rect(s.lstrip('<').strip()) for s in names]


def card(panel, ink, cur=0):
    """320 x 480 palette indices, row-major: the panel column as the card
    shows it - the kit, the strip under it, and the picker with its frame."""
    import pcspal
    cv = _render()
    W, H = 2 * KW, 480
    out = [panel] * (W * H)
    for y in range(KH):
        for x in range(KW):
            if cv[y][x]:
                for dy in (0, 1):
                    for dx in (0, 1):
                        out[(2 * y + dy) * W + 2 * x + dx] = ink
    import pcsicons
    for name, x0, y0, w, h, rows in pcsicons.icons():
        for yy in range(h):
            for xx in range(w):
                if rows[yy][xx]:
                    out[(y0 + yy) * W + x0 + xx] = ink
    for i in range(pcspal.PICKW * pcspal.PICKH):
        x0 = PICKX + (i % pcspal.PICKW) * CELL
        y0 = PICKY + (i // pcspal.PICKW) * CELL
        for yy in range(y0, y0 + CELL):
            for xx in range(x0, x0 + CELL):
                out[yy * W + xx] = pcspal.PICK0 + i
    bx0, by0 = PICKX - BOXGAP - 1, PICKY - BOXGAP - 1
    bx1 = PICKX + pcspal.PICKW * CELL + BOXGAP
    by1 = PICKY + pcspal.PICKH * CELL + BOXGAP
    for xx in range(bx0, bx1 + 1):
        out[by0 * W + xx] = out[by1 * W + xx] = ink
    for yy in range(by0, by1 + 1):
        out[yy * W + bx0] = out[yy * W + bx1] = ink
    x0 = PICKX + (cur % pcspal.PICKW) * CELL
    y0 = PICKY + (cur // pcspal.PICKW) * CELL
    f = frame_colour(cur)
    for k in range(CELL):
        for (xx, yy) in ((x0 + k, y0), (x0 + k, y0 + CELL - 1),
                         (x0, y0 + k), (x0 + CELL - 1, y0 + k)):
            out[yy * W + xx] = f
    return out


def packed():
    """The bitmap as the machine stores it, CROPPED to the bytes and rows that
    carry anything: -> (first byte column, first row, bytes a row, rows, data),
    MSB first.  ⛔ The module has to stay inside four 8 KB blocks: with pcs's
    21 KB of data, one byte over 32 K is `Error #207` before the first
    instruction - which the icons did, by 268 bytes, until the tool column
    and the empty rows came out of this bitmap.  KitDraw fills the panel first
    and doubles each nibble through PCKDbl."""
    cv = _render()
    ys = [y for y in range(KH) if any(cv[y])]
    xs = [x for y in ys for x in range(KW) if cv[y][x]]
    b0, b1 = min(xs) // 8, max(xs) // 8
    y0, y1 = min(ys), max(ys)
    out = bytearray()
    for y in range(y0, y1 + 1):
        for i in range(b0 * 8, (b1 + 1) * 8, 8):
            v = 0
            for b in cv[y][i:i + 8]:
                v = (v << 1) | b
            out.append(v)
    return b0, y0, b1 - b0 + 1, y1 - y0 + 1, bytes(out)


def doubled_nibbles():
    """A nibble's four bits, each twice: WM.Mask's byte for four world pixels."""
    out = []
    for n in range(16):
        v = 0
        for b in range(4):
            bit = (n >> (3 - b)) & 1
            v = (v << 2) | (bit * 3)
        out.append(v)
    return bytes(out)


def selftest():
    bad = []
    cv = _render()
    n = sum(map(sum, cv))
    if n == 0:
        bad.append('the kit is empty')
    tl = tools()
    if [t[0] for t in tl] != list(TOOLS):
        bad.append('the tool order is not CMDMENU\'s')
    # ⭐ Every tool's rectangle lies in TOOLB's column, and they do not overlap.
    tb = rect('TOOLB')
    for nm, x, y, w, h in tl:
        if not (tb[0] <= x and x + w <= tb[0] + tb[2]):
            bad.append('%s at x %d..%d is outside TOOLB' % (nm, x, x + w - 1))
    ys = sorted((y, y + h) for _, _, y, _, h in tl)
    for (a0, a1), (b0, b1) in zip(ys, ys[1:]):
        if b0 < a1:
            bad.append('two tool rectangles overlap at y %d' % b0)
    # ⭐ And every tool icon is INSIDE its own rectangle, which is what makes
    # the rectangle the icon's hit test (pcsicons.py checks the placement).
    import pcsicons
    if not pcsicons.selftest():
        bad.append('the redrawn icons do not sit in their rectangles')
    if len(bin_boxes()) != 43:
        bad.append('%d bin boxes, wanted 43' % len(bin_boxes()))
    # ⭐ The picker fits the panel, under the tools, and above the screen's end.
    last = max(y + h for _, _, y, _, h in tl)
    if PICKY - BOXGAP - 1 < 2 * last or PICKY + 10 * CELL > 480 or PICKX < 0 \
            or PICKX + 12 * CELL > 2 * KW:
        bad.append('the picker at (%d, %d) is not under the tools' % (PICKX, PICKY))
    for m in bad:
        print('FAIL  %s' % m)
    if not bad:
        print('ok    the kit: %d ink pixels, 13 tools each inside its own\n'
              '      rectangle in TOOLB\'s column, 43 bin boxes, and the 12 x 10\n'
              '      picker under them' % n)
    return not bad


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'png':
        from PIL import Image
        import pcspal
        pal = pcspal.palette()
        img = Image.new('RGB', (320, 480))
        img.putdata([pal[v] for v in card(pcspal.UI_PANEL, pcspal.UI_INK,
                                          int(sys.argv[3]) if len(sys.argv) > 3 else 0)])
        img.save(sys.argv[2])
        sys.exit(0)
    sys.exit(0 if selftest() else 1)
