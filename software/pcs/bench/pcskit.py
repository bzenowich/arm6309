#!/usr/bin/env python3
"""pcskit.py - the editor's kit panel: the tool bar and the parts bin.

⛔ READ OUT OF EDIT.s, NOT REDRAWN.  `DRAWKIT` (EDIT.s:220) clears `KITB` and
then XOR-draws the 52 entries of `ICONS` - thirteen tools and the frame-0
picture of every part in the bin - and scan-converts the four plain polygons
in `POLYS`.  This does the same, in the same order, at the Atari's own
resolution: one bit per world unit, which is one hi-res pixel, 160 x 192.

⭐ THE KIT IS MONOCHROME, and that is not a simplification: every icon is 1bpp
and all four bin polygons fill with `$FF`.  The only colour in it is the three
paint pots, which on the Atari were artefact colours (`$FF`, `$55`, `$AA`).
Here they are cut out of the bitmap and filled with the palette entries those
masks translate to (pcsdat.asm's table: `$FF` -> 1, `$55` -> 2, `$AA` -> 3).

⚠ AND THE MACHINE DOES NOT SCAN-CONVERT THE KIT'S POLYGONS: their x runs to
243 in a panel that starts at 160, and the port's converter is one byte of x
over a 160-wide table.  They are rendered here, into the bitmap, once.

The outputs:
    bits()      160 x 192, 0/1 - what DRAWKIT leaves in KITB
    pots()      [(x, y, w, h, colour)] in world units - the paint pots
    card()      320 x 384 palette indices - the panel as the card shows it,
                which is what the bench compares
    tools()     [(name, x, y, w, h)] - CMDMENU's hit rectangles, in order
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

# The pots, and what their masks mean in this palette.
POTS = (('WHITEPAINT', 1), ('GREENPAINT', 2), ('VIOLETPAINT', 3))


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
        return _cache['bits'], _cache['pots']
    canvas = [[0] * KW for _ in range(KH)]
    tmpl = dict((t.name, t) for t in T.parts())
    pots = []
    potnames = dict(POTS)
    for sym in A.block_syms('EDIT.s', 'ICONS'):
        name = sym.split('+')[0].strip()
        if name in tmpl:
            # ⭐ `DA BMP1+$13` points at the template's own L[0]: its picture
            # is the part's frame 0, where the template's header says.
            t = tmpl[name]
            h, w, bits, dy = t.frames()[0]
            _xor(canvas, t.px, t.vert + dy, h, w, bits)
            continue
        x, y, h, w, bits = _icon(name)
        if name in potnames:
            # ⛔ The pot is NOT drawn: its pattern is an artefact colour, and
            # drawn as 1bpp it would come out as stripes of ink.  ⭐ A row with
            # any bit set is paint across the pot's whole width (the union of
            # its set bits - a GREEN row of $5540 is still ten pixels of
            # paint), and an all-zero row is the gap between lid and body.
            # Consecutive rows merge into one rectangle.
            ext = [c * 8 + b for c in range(w) for b in range(8)
                   if any(bits[r * w + c] & (0x80 >> b) for r in range(h))]
            x0, x1 = min(ext), max(ext)
            for r in range(h):
                if not any(bits[r * w:(r + 1) * w]):
                    continue
                if pots and pots[-1][4] == potnames[name] and \
                        pots[-1][1] + pots[-1][3] == y + r:
                    px_, py_, pw_, ph_, pc_ = pots[-1]
                    pots[-1] = (px_, py_, pw_, ph_ + 1, pc_)
                else:
                    pots.append((x + x0, y + r, x1 - x0 + 1, 1, potnames[name]))
            continue
        _xor(canvas, x, y, h, w, bits)
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
    _cache['bits'], _cache['pots'] = canvas, pots
    return canvas, pots


def bits():
    return _render()[0]


def pots():
    return _render()[1]


def tools():
    return [(n,) + rect(n + 'B') for n in TOOLS]


def bin_boxes():
    """The 43 parts-bin hit rectangles, BOXLO/BOXHI's order (EDIT.s:1194)."""
    names = A.block_syms('EDIT.s', 'BOXLO')
    return [rect(s.lstrip('<').strip()) for s in names]


def card(panel, ink):
    """320 x 384 palette indices, row-major: the panel as the card shows it."""
    cv, ps = _render()
    out = [panel] * (2 * KW * 2 * KH)
    W = 2 * KW
    for y in range(KH):
        for x in range(KW):
            if cv[y][x]:
                for dy in (0, 1):
                    for dx in (0, 1):
                        out[(2 * y + dy) * W + 2 * x + dx] = ink
    for (x, y, w, h, c) in ps:
        for yy in range(2 * (y), 2 * (y + h)):
            for xx in range(2 * (x - KX), 2 * (x - KX + w)):
                out[yy * W + xx] = c
    return out


def packed():
    """The bitmap as the machine stores it: 160 bits a row, 20 bytes, MSB first.
    ⛔ NOT DOUBLED: doubled it was 7,680 bytes, and a 35 KB module plus pcs's
    21 KB of data is 64 KB in 8 KB blocks - `Error #207` before the first
    instruction.  KitDraw doubles each nibble through a 16-byte table."""
    cv, _ = _render()
    out = bytearray()
    for y in range(KH):
        for i in range(0, KW, 8):
            v = 0
            for b in cv[y][i:i + 8]:
                v = (v << 1) | b
            out.append(v)
    return bytes(out)


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
    cv, ps = _render()
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
    # the rectangle the icon's hit test.
    for nm, x, y, w, h in tl:
        icon = {'WHITE': 'WHITEPAINT', 'GREEN': 'GREENPAINT',
                'VIOLET': 'VIOLETPAINT', 'PLAY': 'PLAYICON', 'MAGN': 'MAGNIFIER',
                'WIRE': 'ANDG'}.get(nm, nm)
        ix, iy, ih, iw, _ = _icon(icon)
        if not (x <= ix and iy >= y and iy + ih <= y + h):
            bad.append('%s\'s icon at (%d, %d) is outside its rectangle' % (nm, ix, iy))
    if len(bin_boxes()) != 43:
        bad.append('%d bin boxes, wanted 43' % len(bin_boxes()))
    if len(ps) < 3 or set(p[4] for p in ps) != {1, 2, 3}:
        bad.append('the pots came out as %s' % ps)
    for m in bad:
        print('FAIL  %s' % m)
    if not bad:
        print('ok    the kit: %d ink pixels, 13 tools each inside its own\n'
              '      rectangle in TOOLB\'s column, 43 bin boxes, and the three\n'
              '      pots as %d fill rectangles' % (n, len(ps)))
    return not bad


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'png':
        from PIL import Image
        img = Image.new('RGB', (320, 384))
        pal = {16: (40, 44, 60), 19: (230, 230, 220), 1: (255, 255, 255),
               2: (60, 200, 80), 3: (170, 80, 220)}
        img.putdata([pal[v] for v in card(16, 19)])
        img.save(sys.argv[2])
        sys.exit(0)
    sys.exit(0 if selftest() else 1)
