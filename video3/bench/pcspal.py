#!/usr/bin/env python3
"""pcspal.py - the 256-entry LUT for `pcs`.

The Atari ran Pinball Construction Set in two colours (GOATARI.s:20-27 sets
COLPF1 white, COLPF2 black and the border dark red, and `$D01B` is never
written in any file).  What looked like colour was the Apple II's hi-res bit
patterns surviving the port: FILLCOLOR is an 8-bit DITHER MASK ANDed into every
span (`DOBAR`, PPAK.s:910), and the brush offers exactly three --

    WHITE  $FF   solid
    GREEN  $55   01010101
    VIOLET $AA   10101010

-- which NTSC artifacting turned into two hues and white.

⭐ HERE FILLCOLOR IS A PALETTE INDEX and the brush offers a strip.  Everything
else about the field is unchanged, including the part that matters:

⛔ INDEX 0 MEANS UNFILLED, AND UNFILLED IS NOT INVISIBLE.  A polygon with
FILLCOLOR 0 draws as its vertex dots alone (PPAK.s:269-271) while remaining a
full collision solid -- it is how you build an invisible wall, and PCS players
used it.  Index 0 is therefore ALSO video3's transparent key (keyed-copy.md), so
the two meanings agree instead of fighting: a zero byte is "nothing was painted
here" in both the database and the framebuffer.
"""

# --- the fixed low entries -------------------------------------------------
# ⚠ These indices are part of the file format: a saved table stores FILLCOLOR
# as a number, so renumbering the strip repaints every table ever made.  Append
# only, exactly as `mktbox.py`'s ICON_NAMES must be appended to.
KEY = 0                 # unfilled / transparent / the table's own backdrop

PAINT0 = 1              # 1..15  the brush's strip
NPAINT = 15

UI0 = 16                # 16..31 chrome
UI_PANEL = 16           # the kit panel's face
UI_LIGHT = 17           # bevel, lit edge
UI_DARK = 18            # bevel, shadowed edge
UI_INK = 19             # text and icon ink
UI_HILITE = 20          # a menu item under the cursor
UI_DOT = 21             # a polygon's vertex dot
UI_WIRE = 22            # a wire in the wiring kit
UI_FRAME = 23           # the selection box
UI_TABLE = 24           # the table's default backdrop
UI_SCORE = 25           # the score strip's digits
UI_BALLICON = 26        # the remaining-balls icons
UI_PART = 27            # ⭐ a library part's ART.  The original's is 1bpp and
#                         its polygon's FILLCOLOR is 0 (unfilled but solid), so
#                         the picture needs a colour of its own - and `WM.Sprite`
#                         renders the 1bpp mask verbatim in it, 8 px a store.

# Named so the port and the checker agree without either quoting a number.
NAMES = {
    'key': KEY, 'panel': UI_PANEL, 'light': UI_LIGHT, 'dark': UI_DARK,
    'ink': UI_INK, 'hilite': UI_HILITE, 'dot': UI_DOT, 'wire': UI_WIRE,
    'frame': UI_FRAME, 'table': UI_TABLE, 'score': UI_SCORE,
    'ballicon': UI_BALLICON, 'part': UI_PART,
}

# --- the colours -----------------------------------------------------------
# ⭐ The three the original had come FIRST, and keep their names, so a table
# built on an Atari maps onto this strip without a translation table:
# $FF -> white (1), $55 -> green (2), $AA -> violet (3).
PAINT = [
    (0xFF, 0xFF, 0xFF),   # 1  white     <- the original's $FF
    (0x44, 0xDD, 0x55),   # 2  green     <- the original's $55
    (0xBB, 0x66, 0xEE),   # 3  violet    <- the original's $AA
    (0xEE, 0x33, 0x33),   # 4  red
    (0xFF, 0x88, 0x22),   # 5  orange
    (0xFF, 0xDD, 0x33),   # 6  yellow
    (0x22, 0xAA, 0x44),   # 7  dark green
    (0x33, 0xDD, 0xDD),   # 8  cyan
    (0x33, 0x77, 0xEE),   # 9  blue
    (0x22, 0x33, 0xAA),   # 10 navy
    (0xEE, 0x55, 0xAA),   # 11 pink
    (0x99, 0x55, 0x22),   # 12 brown
    (0xBB, 0xBB, 0xBB),   # 13 light grey
    (0x77, 0x77, 0x77),   # 14 grey
    (0x33, 0x33, 0x33),   # 15 dark grey
]

CHROME = {
    KEY:          (0x00, 0x00, 0x00),
    UI_PANEL:     (0x99, 0x99, 0x99),
    UI_LIGHT:     (0xDD, 0xDD, 0xDD),
    UI_DARK:      (0x55, 0x55, 0x55),
    UI_INK:       (0x11, 0x11, 0x11),
    UI_HILITE:    (0x33, 0x55, 0xCC),
    UI_DOT:       (0xFF, 0x22, 0x22),
    UI_WIRE:      (0x33, 0xDD, 0xFF),
    UI_FRAME:     (0xFF, 0xFF, 0x00),
    UI_TABLE:     (0x10, 0x14, 0x20),
    UI_SCORE:     (0xFF, 0xCC, 0x44),
    UI_BALLICON:  (0xDD, 0xDD, 0xEE),
    UI_PART:      (0xEE, 0xEE, 0xF4),
}


def rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def palette():
    """256 (r, g, b) triples."""
    pal = [(0, 0, 0)] * 256
    for i, c in CHROME.items():
        pal[i] = c
    for i, c in enumerate(PAINT):
        pal[PAINT0 + i] = c
    # 32..255 are unassigned and black.  ⚠ Deliberately not filled with a ramp:
    # `check:reach`'s question applied to software -- an entry nothing writes is
    # a colour the editor cannot pick, and inventing 224 of them would only make
    # the palette dump harder to read.
    return pal


def blob():
    """512 bytes, big-endian RGB565, as the card's PIDX/PDATL/PDATH want them
    and as `pinball`'s pcbt.pal already stores them."""
    out = bytearray()
    for r, g, b in palette():
        v = rgb565(r, g, b)
        out += bytes((v >> 8, v & 0xFF))
    return bytes(out)


# ⭐ The original's dither masks, mapped onto the strip.  A table imported from
# an Atari .PB carries $FF/$55/$AA/$00 in FILLCOLOR; this is the translation,
# and it is the only place it is written down.
FROM_ATARI = {0x00: KEY, 0xFF: PAINT0 + 0, 0x55: PAINT0 + 1, 0xAA: PAINT0 + 2}


if __name__ == '__main__':
    pal = palette()
    for i in range(0, 32):
        r, g, b = pal[i]
        tag = next((k for k, v in NAMES.items() if v == i), '')
        if PAINT0 <= i < PAINT0 + NPAINT:
            tag = 'paint %d' % (i - PAINT0 + 1)
        print('%3d  #%02X%02X%02X  %04X  %s' % (i, r, g, b, rgb565(r, g, b), tag))
    print('\n%d bytes' % len(blob()))
