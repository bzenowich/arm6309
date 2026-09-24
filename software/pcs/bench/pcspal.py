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

# ⭐ THE PICKER: 12 x 10, entries 32..151, row by row.  Sampled from the
# reference picker the user supplied on 2026-09-24 (the median of each cell's
# centre): a row of greys from white to black, then nine rows of twelve hues
# from dark to light.  ⚠ Append-only like the strip above - a table stores
# the entry number, so these indices are file format the day a table is saved.
PICK0 = 32
PICKW, PICKH = 12, 10
PICK = [
    0xFFFFFF, 0xEBEBEB, 0xD7D7D7, 0xC2C2C2, 0xADADAD, 0x999999, 0x848587, 0x707271, 0x5C5E5D, 0x474747, 0x333333, 0x020202,
    0x04374A, 0x1C2455, 0x150E3A, 0x2F0B3B, 0x37111E, 0x5A0F0A, 0x58210D, 0x563514, 0x553F16, 0x67622A, 0x505628, 0x2A3D1D,
    0x054D66, 0x243875, 0x1C1751, 0x451D59, 0x56122B, 0x811717, 0x7C2B16, 0x784C1D, 0x785A26, 0x8C8733, 0x707733, 0x385829,
    0x066E91, 0x15499F, 0x322871, 0x5F2A7C, 0x79193E, 0xB52026, 0xAD4124, 0xA76A29, 0xA67D2D, 0xC3BE2F, 0x9AA638, 0x4E7B38,
    0x0C8BB4, 0x355FAB, 0x3D2F8E, 0x772F92, 0x9B2350, 0xE12A26, 0xD95427, 0xD2852B, 0xD09E2B, 0xF4EA0E, 0xC2D130, 0x659D42,
    0x11A0D8, 0x3F66B1, 0x523F99, 0x8A449C, 0xBC2C5F, 0xEF4524, 0xF36B21, 0xFBAB18, 0xFBC80B, 0xF9ED49, 0xD6DF44, 0x76BC42,
    0x2AC5F5, 0x527DC1, 0x5954A4, 0x9356A3, 0xE63C7A, 0xF16254, 0xF5864E, 0xFCB340, 0xFFCC3F, 0xFAF170, 0xE1E56A, 0x98CC60,
    0x60CCF2, 0x7DA1D5, 0x705EA8, 0xA467AC, 0xEE709F, 0xF68B83, 0xF8A47F, 0xFFC878, 0xFDD978, 0xFAF496, 0xE7EC90, 0xB2D68C,
    0x99DAF5, 0xAEC2E5, 0x9F8CC3, 0xC597C5, 0xF5A5C0, 0xF8B2B0, 0xFBC5AD, 0xFED8A7, 0xFCE4A8, 0xFAF8BB, 0xF2F1B8, 0xCDE5B5,
    0xCCEBFD, 0xD4E1F2, 0xD6C8E2, 0xE4CAE3, 0xFAD4E1, 0xFCDAD8, 0xFDE3D6, 0xFEECD4, 0xFEF3D7, 0xFBFCDD, 0xF5F8DE, 0xDEEED4,
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
    for i, v in enumerate(PICK):
        pal[PICK0 + i] = ((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)
    # 152..255 are unassigned and black.  ⚠ Deliberately not filled with a ramp:
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

# ⭐ AND THE APPLE II's, which is what the shipped tables are saved in.  Its
# hi-res has eight colour codes and PCS stores them doubled; `$10` is the
# library parts' "no fill", which is this port's index 0 - unfilled AND SOLID.
FROM_APPLE = {0x00: KEY, 0x02: PAINT0 + 1, 0x04: PAINT0 + 2, 0x06: PAINT0 + 0,
              0x08: KEY, 0x0A: PAINT0 + 4, 0x0C: PAINT0 + 8, 0x0E: PAINT0 + 0,
              0x10: KEY}


if __name__ == '__main__':
    pal = palette()
    for i in range(0, 32):
        r, g, b = pal[i]
        tag = next((k for k, v in NAMES.items() if v == i), '')
        if PAINT0 <= i < PAINT0 + NPAINT:
            tag = 'paint %d' % (i - PAINT0 + 1)
        print('%3d  #%02X%02X%02X  %04X  %s' % (i, r, g, b, rgb565(r, g, b), tag))
    print('\n%d bytes' % len(blob()))
