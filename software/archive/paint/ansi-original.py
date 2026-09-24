"""ansi-original.py - this project's own 80 x 25 ANSI piece, RETIRED 2026-09-24.

`v3art` drew this ("ARM6309 - A 6809 THAT DRAWS BACK") from 2026-09-22 until
2026-09-24, because Blocktronics' we-tortuga.ans cannot be redistributed and a
desktop icon that is dead on a clone seemed worse than a home-made picture.
The owner chose we-tortuga: since 2026-09-24 `v3art` IS we-tortuga
(software/paint/reference/), and a machine without the file has no `v3art`.

This is the code as it stood in software/paint/tools/v3show.py, lifted out
whole.  It needs v3show.py's VGA16 palette and encoder to run again.
"""

# ⭐⭐ AN ORIGINAL PIECE, BECAUSE THE IMPORTED ONE CANNOT SHIP (2026-09-22).
# we-tortuga.ans is Blocktronics' and is not in this repository, so `v3art`
# only existed on a machine that happened to have it - and a DESKTOP ICON that
# works here and is dead on a clone is not an application.  What follows is
# this project's own 80 x 25, composed out of CP437 and the sixteen DOS
# colours, so the stream is always there and is always the same bytes.
#
# ⚠ THE PALETTE IS STILL VGA16 and the encoder below is still the one the
# imported piece used: what changed is where the grid comes from.  ART_FROM /
# ART_ROWS and `have_art()` still select the import when it IS present, so
# nothing that used to work stopped.

# a 5 x 7 pixel face, enough for the logo.  ⚠ Rendered with the UPPER HALF
# BLOCK (CP437 223), so one cell is TWO pixel rows: the ink is the cell's
# foreground for the top pixel and its background for the bottom one, which is
# how ANSI art has always got twice the vertical resolution it is given.
LOGO5x7 = {
    "A": ".###.|#...#|#...#|#####|#...#|#...#|#...#",
    "R": "####.|#...#|#...#|####.|#..#.|#...#|#...#",
    "M": "#...#|##.##|#.#.#|#...#|#...#|#...#|#...#",
    "6": "..##.|.#...|#....|####.|#...#|#...#|.###.",
    "3": "####.|....#|....#|.###.|....#|....#|####.",
    "0": ".###.|#...#|#..##|#.#.#|##..#|#...#|.###.",
    "9": ".###.|#...#|#...#|.####|....#|...#.|.##..",
}
SHADE = [0xB0, 0xB1, 0xB2, 0xDB]        # . : light, medium, dark, full
HALF_UP = 0xDF                          # the upper half block


def _blank_grid(w, h, bg=0):
    return [[(32, 7, bg) for _ in range(w)] for _ in range(h)]


def _put(grid, x, y, text, fg, bg):
    """A run of CP437 codes (a str is encoded, a bytes is taken as codes)."""
    codes = text.encode("cp437") if isinstance(text, str) else text
    for i, c in enumerate(codes):
        if 0 <= y < len(grid) and 0 <= x + i < len(grid[0]):
            grid[y][x + i] = (c, fg, bg)


def _logo(grid, text, x0, y0, colour_of_row):
    """Lay `text` out of LOGO5x7 with the half-block trick.  `colour_of_row`
    is called with the PIXEL row and gives the ink, so the logo can carry a
    vertical gradient the way a hand-drawn one would."""
    px = []                                     # pixel rows, as strings
    for r in range(7):
        row = ""
        for ch in text:
            row += LOGO5x7[ch].split("|")[r] + "."
        px.append(row)
    px.append("." * len(px[0]))                 # 7 rows pad to 4 cell rows
    for cy in range(4):
        top, bot = px[cy * 2], px[cy * 2 + 1]
        for cx in range(len(top)):
            t, b = top[cx] == "#", bot[cx] == "#"
            if not t and not b:
                continue
            ink_t, ink_b = colour_of_row(cy * 2), colour_of_row(cy * 2 + 1)
            if t and b:
                grid[y0 + cy][x0 + cx] = (0xDB, ink_t, 0)
            elif t:
                grid[y0 + cy][x0 + cx] = (HALF_UP, ink_t, 0)
            else:
                grid[y0 + cy][x0 + cx] = (HALF_UP, 0, ink_b)


def art_grid_original(w=80, h=25):
    """⭐ THIS PROJECT'S OWN ANSI PIECE - `v3art`, as rows of (code, fg, bg).

    Everything here is a CP437 code point and one of the sixteen DOS colours,
    which is the whole of what `ca_ext.asm`'s terminal implements; there is no
    bitmap compositing anywhere in it.  ⚠ Deterministic on purpose: the bench
    compares bytes, so nothing may come from a clock or an unseeded random."""
    g = _blank_grid(w, h, 0)

    # --- the field: a dithered vertical gradient, black up into blue --------
    # ⭐ THE DITHER IS THE POINT.  Two adjacent palette entries and the four
    # shade blocks give seven tones out of two colours, which is how a
    # sixteen-colour medium has always drawn a sky.
    #
    # ⛔ AND THE DITHER IS ORDERED, NOT A MODULO.  The first cut picked the
    # heavier block when `(x * 7 + y * 13) % 5 == 0`, which is not a dither -
    # it is a comb, and it drew vertical stripes straight down the sky.  A
    # 4 x 4 Bayer threshold is the classic answer and costs nothing: it blends
    # each pair of ADJACENT tones, so the ramp reads as a ramp.
    # ⚠ Ordered, and therefore deterministic - the bench compares bytes.
    TONES = [(0, 4, 0), (0, 4, 1), (0, 4, 2), (0, 4, 3),
             (4, 12, 1), (4, 12, 2), (4, 12, 3)]
    BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
    y0, y1 = 9, 17
    for y in range(y0, y1 + 1):
        t = (y - y0) / (y1 - y0) * (len(TONES) - 1)
        k, frac = int(t), t - int(t)
        for x in range(w):
            step = min(k + (1 if BAYER[y % 4][x % 4] / 16.0 < frac else 0), len(TONES) - 1)
            lo, hi, lvl = TONES[step]
            g[y][x] = (SHADE[lvl], hi, lo)

    # --- the night above it -------------------------------------------------
    # ⚠ A FIXED LIST AND NOT A GENERATOR, for the same reason the dither is
    # ordered: the bench compares bytes.
    for i, (sx, sy) in enumerate([(6, 1), (17, 0), (31, 2), (48, 1), (61, 0), (71, 2),
                                  (12, 3), (68, 3), (25, 1), (55, 3), (3, 6), (76, 5),
                                  (9, 8), (72, 8), (40, 0), (22, 6), (64, 6), (50, 7)]):
        # ⛔⛔ NOT $07.  In CP437 $07 is a bullet and it is exactly the glyph a
        # bright star wants - and it is also BEL.  `ca_ext.asm`'s terminal
        # ACTS on a code below 32 and draws nothing, so each one EATS A CELL
        # and shifts the rest of its row left: char row 1 lost two cells, rows
        # 3, 6 and 8 one each.  ⚠ It is invisible in this file's own preview,
        # which draws from the grid and never goes near a terminal; it took
        # measuring the machine's picture against the preview, one character
        # row at a time, to see it.  $F9 is the same dot and is printable.
        g[sy][sx] = (0xFA if i % 3 else 0xF9, 15 if i % 2 else 8, 0)
    # a moon, top right: two cells of the half block against the black
    _put(g, 70, 1, bytes([0xDC, 0xDB, 0xDD]), 15, 0)
    _put(g, 70, 2, bytes([0xDF, 0xDB, 0xDE]), 7, 0)

    # --- the logo -----------------------------------------------------------
    # ⚠ VGA16 IS IN SGR ORDER, not in VGA attribute order (the note above it
    # says so): 6 is cyan, 12 is bright blue, 14 bright cyan, 15 white.  The
    # first cut read it as attributes and asked for 11, which is bright YELLOW.
    ramp = [6, 6, 14, 14, 14, 15, 15, 15]
    _logo(g, "ARM6309", (w - 7 * 6) // 2, 2, lambda r: ramp[r])

    # --- a rule, and the titles ---------------------------------------------
    for x in range(8, w - 8):
        t = min(abs(x - w // 2) * 4 // (w // 2 - 8), 3)
        g[7][x] = (SHADE[3 - t], 12, 0)
    _put(g, (w - 26) // 2, 8, "A 6809 THAT DRAWS BACK", 15, 0)

    # --- the skyline: a card standing in a backplane, in silhouette ---------
    # ⚠ Solid black on the gradient, so the shape reads as a cut-out rather
    # than as another colour - which is what a silhouette is.
    sky = [0] * w
    for x in range(w):
        # three boards of different heights, and the connector fingers under
        h1 = 3 if 8 <= x < 30 else 0
        h2 = 5 if 34 <= x < 52 else 0
        h3 = 4 if 56 <= x < 72 else 0
        sky[x] = max(h1, h2, h3)
    for x in range(w):
        for k in range(sky[x]):
            g[17 - k][x] = (0xDB, 0, 0)
    # the ICs on the boards: a row of small dark blocks
    for x in range(10, 28, 3):
        g[16][x] = (0xFE, 8, 0)
    for x in range(36, 50, 3):
        g[15][x] = (0xFE, 8, 0)
    for x in range(58, 70, 3):
        g[15][x] = (0xFE, 8, 0)
    # the backplane, and the fingers
    for x in range(4, w - 4):
        g[18][x] = (0xDB, 8, 0)
    for x in range(4, w - 4, 2):
        g[19][x] = (HALF_UP, 6, 0)

    # --- the sixteen, which is the medium ------------------------------------
    _put(g, 4, 21, "CP437 + SGR", 7, 0)
    for i in range(16):
        g[21][17 + i] = (0xDB, i, 0)
    _put(g, 35, 21, "on ca_ext.asm's terminal - no bitmap anywhere", 8, 0)

    # --- the signature ------------------------------------------------------
    box = "arm6309 . video3 . 256 colours, one sprite, a copy engine"
    x0 = (w - len(box) - 4) // 2
    _put(g, x0, 23, bytes([0xC9]) + bytes([0xCD]) * (len(box) + 2) + bytes([0xBB]), 12, 0)
    _put(g, x0, 24, bytes([0xBA]), 12, 0)
    _put(g, x0 + 2, 24, box, 14, 0)
    _put(g, x0 + len(box) + 3, 24, bytes([0xBA]), 12, 0)

    # ⛔ AND NOTHING IN THE PIECE MAY BE A CONTROL CHARACTER.  Every cell goes
    # to `ca_ext.asm`'s terminal as a literal byte, and a byte below 32 is a
    # command to it - BEL, BS, LF, CR - not a glyph.  The failure is not a
    # wrong picture, it is a row that is one or two cells to the LEFT of where
    # it should be, which is the kind of thing a preview cannot show you.
    for y, row in enumerate(g):
        for x, (code, _, _) in enumerate(row):
            assert 32 <= code <= 255, (
                "cell (%d, %d) is code %d - the terminal would act on it" % (x, y, code))
    return g
