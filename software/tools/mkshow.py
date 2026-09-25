#!/usr/bin/env python3
"""Write the show: the script, its assets, and the model's pictures.

    python3 software/tools/mkshow.py BUILD

  BUILD/script.bin   the bytecode gui.asm interprets
  BUILD/gfx.bin      the 8x16 and 8x8 CP437 fonts
  BUILD/icons.bin    the icons, a (page, offset) table first
  BUILD/image.bin    parrot.img: the photograph, 640 x 345, in the desktop palette
  BUILD/show.inc     the pointer's masks and the checkpoint count, for the assembler
  BUILD/show.npz     every CHECK's picture, from show.Model running script.bin
  BUILD/checks.txt   what each CHECK is

THE STORY, in machine seconds at the card's own frame rates:
  a Haiku-flavoured desktop is drawn; the module loads; the pointer appears,
  opens a dual-pane file browser, selects a folder and a file, and drags the
  window by its tab; the Deskbar menu starts Paint, a MacPaint mock-up, which
  draws a rubber-banded rectangle, a pattern fill, patterned and solid
  polygons, typed text and horizontal brush strokes, then scrolls its canvas
  with a display list to show art that was drawn off the screen. File > Open...
  lists parrot.img; it loads into the canvas and stays five seconds; the window
  closes. "Connect to BBS" dials an ANSI board and plays a few turns of
  TradeWars 2002 at 19200 baud; the terminal hangs up and the desktop comes
  back. "Raster Bars Demo" opens a window whose colour is rewritten every
  scanline by a display list; it closes; "Zelda" starts the overworld.
"""
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
import show
from show import C, W16

B = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "archive", "demo", "build")
QUICK = os.environ.get("QUICK")

PAL = show.gui_palette()
PRGB = show.gui_rgb()
SW, SH = 640, 480


def cidx(rgb):
    return show.nearest(rgb, PRGB)


# ------------------------------------------------------------------- icons
def art_from_rgba(img, outline=True):
    """An RGBA picture to palette indices; alpha under 128 is transparent. With
    outline, every transparent pixel touching the shape becomes a dark edge -
    Haiku's icons have one."""
    a = np.array(img.convert("RGBA"))
    h, w = a.shape[:2]
    out = np.full((h, w), -1, dtype=np.int32)
    for y in range(h):
        for x in range(w):
            if a[y, x, 3] >= 128:
                out[y, x] = cidx(tuple(int(v) for v in a[y, x, :3]))
    if outline:
        op = out >= 0
        edge = np.zeros_like(op)
        edge[1:] |= op[:-1]
        edge[:-1] |= op[1:]
        edge[:, 1:] |= op[:, :-1]
        edge[:, :-1] |= op[:, 1:]
        out[edge & ~op] = cidx((40, 40, 48))
    return out


def sel_map(art):
    m = {}
    for c in set(art.flatten().tolist()):
        if c >= 0:
            r, g, b = PRGB[c]
            m[c] = cidx((int(r * 0.55), int(g * 0.55), min(255, int(b * 0.55) + 50)))
    return m


def canvas(n=32):
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def icon_folder(n=32):
    im, d = canvas(n)
    s = n / 32
    d.polygon([(2 * s, 8 * s), (12 * s, 8 * s), (15 * s, 5 * s), (27 * s, 5 * s), (28 * s, 8 * s), (28 * s, 12 * s), (2 * s, 12 * s)], fill=(230, 170, 40))
    d.polygon([(1 * s, 11 * s), (30 * s, 11 * s), (28 * s, 27 * s), (3 * s, 27 * s)], fill=(255, 210, 80))
    d.line([(3 * s, 13 * s), (28 * s, 13 * s)], fill=(255, 240, 170))
    return im


def icon_home():
    im = icon_folder()
    d = ImageDraw.Draw(im)
    d.polygon([(10, 19), (16, 14), (22, 19)], fill=(200, 60, 50))
    d.rectangle([12, 19, 20, 24], fill=(250, 250, 240))
    d.rectangle([15, 21, 17, 24], fill=(120, 80, 40))
    return im


def icon_disk():
    im, d = canvas()
    d.polygon([(4, 12), (10, 6), (30, 6), (26, 12)], fill=(200, 200, 205))
    d.rectangle([4, 12, 26, 24], fill=(170, 170, 180))
    d.polygon([(26, 12), (30, 6), (30, 18), (26, 24)], fill=(120, 120, 130))
    d.rectangle([7, 17, 18, 19], fill=(80, 80, 90))
    d.rectangle([21, 17, 23, 19], fill=(60, 230, 80))
    return im


def icon_trash():
    im, d = canvas()
    d.polygon([(7, 9), (25, 9), (23, 29), (9, 29)], fill=(190, 195, 200))
    d.rectangle([5, 6, 27, 9], fill=(150, 155, 160))
    d.rectangle([13, 3, 19, 6], fill=(150, 155, 160))
    for x in (12, 16, 20):
        d.line([(x, 12), (x, 26)], fill=(120, 125, 130))
    return im


def icon_files():
    im, d = canvas()
    d.rectangle([2, 5, 29, 27], fill=(235, 235, 235))
    d.rectangle([2, 5, 29, 9], fill=(255, 203, 0))
    d.rectangle([4, 11, 15, 25], fill=(255, 255, 255))
    d.rectangle([17, 11, 27, 25], fill=(255, 255, 255))
    for y in (13, 17, 21):
        d.rectangle([5, y, 8, y + 2], fill=(255, 200, 60))
        d.line([(10, y + 1), (14, y + 1)], fill=(80, 80, 80))
        d.rectangle([18, y, 21, y + 2], fill=(90, 150, 220))
        d.line([(23, y + 1), (26, y + 1)], fill=(80, 80, 80))
    return im


def icon_paint():
    im, d = canvas()
    d.ellipse([3, 7, 29, 27], fill=(225, 190, 130))
    d.ellipse([17, 19, 23, 25], fill=(0, 0, 0, 0))
    for (x, y), c in zip([(8, 12), (13, 10), (19, 10), (24, 13), (8, 19)],
                         [(220, 40, 40), (250, 200, 30), (40, 170, 60), (40, 90, 220), (150, 50, 180)]):
        d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=c)
    d.line([(14, 29), (29, 3)], fill=(120, 70, 30), width=2)
    d.line([(27, 6), (29, 3)], fill=(30, 30, 30), width=2)
    return im


def icon_bbs():
    im, d = canvas()
    d.rectangle([3, 4, 28, 22], fill=(200, 200, 205))
    d.rectangle([6, 7, 25, 19], fill=(10, 20, 60))
    d.line([(8, 10), (14, 10)], fill=(80, 255, 80))
    d.line([(8, 13), (20, 13)], fill=(255, 255, 90))
    d.line([(8, 16), (11, 16)], fill=(255, 90, 255))
    d.rectangle([11, 23, 20, 26], fill=(160, 160, 170))
    d.rectangle([6, 26, 25, 28], fill=(190, 190, 195))
    return im


def icon_raster():
    im, d = canvas()
    cols = [(255, 40, 40), (255, 150, 0), (255, 240, 0), (60, 220, 60), (40, 140, 255), (150, 60, 240)]
    d.rectangle([3, 3, 28, 28], fill=(10, 10, 40))
    for i, c in enumerate(cols):
        d.rectangle([4, 5 + 4 * i, 27, 6 + 4 * i], fill=c)
    return im


def icon_game():
    im, d = canvas()
    d.polygon([(16, 3), (22, 14), (10, 14)], fill=(250, 200, 30))
    d.polygon([(10, 14), (16, 25), (4, 25)], fill=(250, 200, 30))
    d.polygon([(22, 14), (28, 25), (16, 25)], fill=(250, 200, 30))
    d.line([(16, 26), (16, 30)], fill=(90, 60, 30), width=2)
    return im


def icon_image(n=32):
    im, d = canvas(n)
    s = n / 32
    d.polygon([(6 * s, 2 * s), (21 * s, 2 * s), (27 * s, 8 * s), (27 * s, 30 * s), (6 * s, 30 * s)], fill=(250, 250, 250))
    d.rectangle([8 * s, 10 * s, 25 * s, 24 * s], fill=(60, 140, 90))
    d.ellipse([10 * s, 12 * s, 17 * s, 19 * s], fill=(220, 40, 40))
    d.polygon([(15 * s, 13 * s), (22 * s, 15 * s), (16 * s, 18 * s)], fill=(250, 200, 30))
    return im


def icon_doc(n=32):
    im, d = canvas(n)
    s = n / 32
    d.polygon([(6 * s, 2 * s), (21 * s, 2 * s), (27 * s, 8 * s), (27 * s, 30 * s), (6 * s, 30 * s)], fill=(250, 250, 250))
    for y in range(9, 28, 4):
        d.line([(9 * s, y * s), (24 * s, y * s)], fill=(120, 120, 130))
    return im


# ⭐ THREE MORE FOR THE DESKTOP'S APPLICATIONS (2026-09-22).  arm6309
# software/desk/docs/boot-and-desktop.md §3 asks for Pinball, Monsterland, BBS, ANSI-Art and
# Stardew as clickable ICONS; `bbs` and `image` above already serve two of
# them, and these are the other three.  ⚠ They are APPENDED to
# mktbox.py's ICON_NAMES, not inserted: desk.asm's IcTab carries icon NUMBERS
# as literals, so an insertion would silently repaint every icon on the
# desktop with its neighbour's art.
def icon_pinball():
    im, d = canvas()
    d.rounded_rectangle([4, 1, 28, 30], radius=5, fill=(20, 25, 70), outline=(150, 160, 190))
    d.ellipse([8, 6, 15, 13], fill=(230, 60, 60), outline=(255, 180, 180))
    d.ellipse([18, 9, 25, 16], fill=(60, 140, 240), outline=(190, 220, 255))
    d.line([(7, 22), (14, 26)], fill=(230, 200, 90), width=3)     # the flippers
    d.line([(25, 22), (18, 26)], fill=(230, 200, 90), width=3)
    d.ellipse([14, 17, 19, 22], fill=(235, 235, 245), outline=(120, 120, 140))
    return im


def icon_monster():
    im, d = canvas()
    d.rectangle([2, 25, 30, 30], fill=(70, 50, 35))               # the ground
    d.rectangle([2, 25, 30, 26], fill=(110, 180, 70))
    d.ellipse([7, 8, 25, 26], fill=(80, 190, 90), outline=(40, 120, 50))
    d.polygon([(9, 11), (12, 3), (15, 11)], fill=(80, 190, 90))   # two horns
    d.polygon([(17, 11), (20, 3), (23, 11)], fill=(80, 190, 90))
    for cx in (12, 20):
        d.ellipse([cx - 3, 13, cx + 3, 19], fill=(255, 255, 255))
        d.ellipse([cx - 1, 15, cx + 1, 17], fill=(20, 20, 30))
    d.arc([12, 19, 20, 24], 20, 160, fill=(30, 90, 40), width=2)
    return im


def icon_farm():
    im, d = canvas()
    d.rectangle([2, 2, 30, 13], fill=(140, 200, 240))             # sky
    d.ellipse([21, 3, 29, 11], fill=(255, 220, 90))               # sun
    d.rectangle([2, 13, 30, 30], fill=(120, 85, 55))              # tilled earth
    for y in range(16, 30, 4):                                    # the furrows
        d.line([(3, y), (29, y)], fill=(95, 65, 40))
    for x in (7, 15, 23):                                         # three crops
        d.line([(x, 27), (x, 20)], fill=(60, 150, 60), width=2)
        d.ellipse([x - 4, 15, x, 20], fill=(90, 190, 80))
        d.ellipse([x, 15, x + 4, 20], fill=(70, 165, 70))
    return im


def icon_world():
    """⭐ `tilescroll`'s: the overworld seen from above, which is what the scene is.

    The terrain is the demo's own four - grass, a sand path, a pond and a dark
    wood - with the hero a speck at the middle of it, because the middle is
    exactly where that scene keeps him."""
    im, d = canvas()
    d.rectangle([2, 2, 30, 30], fill=(58, 140, 52))               # grass
    d.polygon([(2, 20), (10, 16), (18, 19), (26, 14), (30, 15),
               (30, 22), (20, 25), (10, 23), (2, 26)],
              fill=(228, 202, 146))                               # a sand path
    d.ellipse([19, 3, 30, 12], fill=(46, 96, 210))                # a pond
    d.ellipse([21, 5, 28, 10], fill=(96, 150, 240))
    for cx, cy in ((4, 5), (9, 8), (5, 11), (11, 3)):             # a dark wood
        d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=(22, 74, 30))
    d.rectangle([14, 13, 18, 20], fill=(30, 110, 44))             # the hero
    d.rectangle([14, 10, 18, 14], fill=(246, 206, 160))
    d.rectangle([14, 9, 18, 11], fill=(26, 92, 40))
    d.rectangle([13, 14, 14, 18], fill=(226, 230, 240))
    return im


def icon_pcs():
    """⭐ `pcs`'s (2026-09-24): Pinball Construction Set, so a table AND a tool.

    A small table - walls, a bumper, the ball and two flippers - with the
    editor's hammer across its right side, because what this program does that
    a pinball game does not is let you build the table."""
    im, d = canvas()
    d.rectangle([1, 2, 21, 30], fill=(120, 120, 130))             # the walls
    d.rectangle([3, 4, 19, 30], fill=(16, 22, 64))                # the playfield
    d.ellipse([5, 6, 12, 13], fill=(230, 60, 60), outline=(255, 170, 170))  # a bumper
    d.ellipse([12, 14, 16, 18], fill=(245, 245, 255))             # the ball
    d.line([(4, 23), (9, 27)], fill=(250, 214, 50), width=3)      # the flippers
    d.line([(18, 23), (13, 27)], fill=(250, 214, 50), width=3)
    d.line([(17, 12), (30, 28)], fill=(150, 95, 45), width=4)     # the hammer's handle
    d.polygon([(12, 10), (20, 3), (25, 8), (17, 15)],
              fill=(215, 220, 230), outline=(70, 75, 90))         # ... and its head
    return im


def icon_leaf():
    im, d = canvas(16)
    d.polygon([(2, 14), (5, 6), (12, 2), (14, 3), (11, 10), (4, 14)], fill=(40, 90, 200))
    d.line([(3, 13), (11, 5)], fill=(200, 220, 255))
    return im


def tool_art(rows):
    a = np.array([[C["black"] if ch == "X" else -1 for ch in r] for r in rows], dtype=np.int32)
    return a


TOOLS = {
    "marquee": ["................", ".XX.XX.XX.XX.XX.", ".X............X.", "................", ".X............X.",
                ".X............X.", "................", ".X............X.", ".X............X.", "................",
                ".X............X.", ".XX.XX.XX.XX.XX.", "................", "................", "................", "................"],
    "lasso": ["................", "....XXXXXXX.....", "..XX.......XX...", ".X...........X..", ".X...........X..",
              ".X...........X..", "..X.........X...", "...XXX...XXX....", "......X.X.......", ".....X..........",
              "....X...........", "....X...........", ".....X..........", "................", "................", "................"],
    "hand": ["......XX........", "....XX.XXX......", "...X..X..X.X....", "...X..X..XX.X...", "...X..X..X..X...",
             ".XX.X....X..X...", "X..XX.......X...", "X...X......X....", ".X.........X....", "..X........X....",
             "...X.......X....", "....X.....X.....", ".....X....X.....", ".....XXXXXX.....", "................", "................"],
    "text": ["................", "..XXXXXXXXXX....", "..XX..XX..XX....", "..X...XX...X....", "......XX........",
             "......XX........", "......XX........", "......XX........", "......XX........", "......XX........",
             "......XX........", ".....XXXX.......", "................", "................", "................", "................"],
    "bucket": ["................", ".....XX.........", "....X..X........", "....X.XXX.......", "....XX.X.X......",
               "...X.X.X..X.....", "..X..X.X...X....", ".X...XXX....X...", "X...........XX..", ".X.........X.XX.",
               "..X.......X..XX.", "...X.....X...XX.", "....X...X....XX.", ".....X.X......X.", "......X.......X.", "................"],
    "spray": ["................", ".X.X............", "X.X.X...........", ".X.X............", "X.X.XX..........",
              "......XXXX......", "......X..XX.....", ".....X....X.....", ".....X....X.....", ".....XXXXXX.....",
              ".....X....X.....", ".....X....X.....", ".....X....X.....", ".....XXXXXX.....", "................", "................"],
    "brush": ["................", "..........XX....", ".........XXX....", "........XXX.....", ".......XXX......",
              "......XXX.......", ".....XXX........", "....X.X.........", "...XXX..........", "..XXXX..........",
              "..XXX...........", ".XXX............", ".XX.............", "................", "................", "................"],
    "pencil": ["................", "...........XX...", "..........X..X..", ".........X.XX...", "........X..X....",
               ".......X..X.....", "......X..X......", ".....X..X.......", "....X..X........", "...X..X.........",
               "...XXX..........", "..XX............", "..X.............", "................", "................", "................"],
    "line": ["................", "..............X.", ".............X..", "............X...", "...........X....",
             "..........X.....", ".........X......", "........X.......", ".......X........", "......X.........",
             ".....X..........", "....X...........", "...X............", "..X.............", ".X..............", "................"],
    "eraser": ["................", "................", "......XXXXXXXX..", ".....X......XX..", "....X......X.X..",
               "...X......X..X..", "..X......X..X...", ".XXXXXXXX..X....", ".X......X.X.....", ".X......XX......",
               ".XXXXXXXX.......", "................", "................", "................", "................", "................"],
    "rect": ["................", "................", ".XXXXXXXXXXXXXX.", ".X............X.", ".X............X.",
             ".X............X.", ".X............X.", ".X............X.", ".X............X.", ".X............X.",
             ".X............X.", ".XXXXXXXXXXXXXX.", "................", "................", "................", "................"],
    "frect": ["................", "................", ".XXXXXXXXXXXXXX.", ".XXXXXXXXXXXXXX.", ".XXXXXXXXXXXXXX.",
              ".XXXXXXXXXXXXXX.", ".XXXXXXXXXXXXXX.", ".XXXXXXXXXXXXXX.", ".XXXXXXXXXXXXXX.", ".XXXXXXXXXXXXXX.",
              ".XXXXXXXXXXXXXX.", ".XXXXXXXXXXXXXX.", "................", "................", "................", "................"],
    "oval": ["................", "................", ".....XXXXXX.....", "...XX......XX...", "..X..........X..",
             ".X............X.", ".X............X.", ".X............X.", "..X..........X..", "...XX......XX...",
             ".....XXXXXX.....", "................", "................", "................", "................", "................"],
    "poly": ["................", "................", "......XXXXXXX...", ".....X......X...", "....X........X..",
             "...X.........X..", "..X...........X.", ".X............X.", "..X...........X.", "...X........XX..",
             "....XXXXXXXX....", "................", "................", "................", "................", "................"],
    "fpoly": ["................", "................", "......XXXXXXX...", ".....XXXXXXXX...", "....XXXXXXXXXX..",
              "...XXXXXXXXXXX..", "..XXXXXXXXXXXXX.", ".XXXXXXXXXXXXXX.", "..XXXXXXXXXXXXX.", "...XXXXXXXXXXX..",
              "....XXXXXXXX....", "................", "................", "................", "................", "................"],
    "grab": ["................", "....X..X..X.....", "...X.XX.XX.X....", "...X..X..X.XX...", "...X..X..X.X.X..",
             "...X.......X.X..", ".XXX..........X.", "X..X..........X.", "X.............X.", ".X...........X..",
             "..X..........X..", "...X........X...", "....X.......X...", ".....XXXXXXXX...", "................", "................"],
}
TOOL_ORDER = ["marquee", "lasso", "grab", "text", "bucket", "spray", "brush", "pencil", "line", "eraser",
              "rect", "frect", "oval", "poly", "fpoly"]


def build_icons():
    icons = []

    def add(name, art, sel=True):
        icons.append(show.Icon(name, art, sel_map(art) if sel else {}))
        return len(icons) - 1

    ids = {}
    for name, fn in [("home", icon_home), ("disk", icon_disk), ("files", icon_files), ("trash", icon_trash),
                     ("paint", icon_paint), ("bbs", icon_bbs), ("raster", icon_raster), ("game", icon_game),
                     ("image", icon_image), ("doc", icon_doc)]:
        ids[name] = add(name, art_from_rgba(fn()))
    ids["folder16"] = add("folder16", art_from_rgba(icon_folder(16)))
    ids["image16"] = add("image16", art_from_rgba(icon_image(16)))
    ids["doc16"] = add("doc16", art_from_rgba(icon_doc(16)))
    ids["leaf"] = add("leaf", art_from_rgba(icon_leaf(), outline=False))
    for t in TOOL_ORDER:
        a = tool_art(TOOLS[t])
        # a tool's selected variant is white on black
        icons.append(show.Icon("tool_" + t, a, {C["black"]: C["white"]}))
        ids["tool_" + t] = len(icons) - 1
    # lay out: the table on page 0, each icon wholly inside one page
    blobs = [ic.blob() for ic in icons]
    table = bytearray(3 * len(blobs))
    data = bytearray(table)
    for i, bl in enumerate(blobs):
        off = len(data)
        if (off % 8192) + len(bl) > 8192:
            data += bytes(8192 - off % 8192)
            off = len(data)
        data[3 * i:3 * i + 3] = bytes([off // 8192, (off % 8192) >> 8, (off % 8192) & 0xFF])
        data += bl
    return bytes(data), ids, icons


# --------------------------------------------------------------- the image
IMG_W, IMG_H = 640, 345


def build_image():
    src = os.path.join(B, "parrots-image.jpg")
    if not os.path.exists(src):
        src = os.path.join(B, "parrots.png")
    im = Image.open(src).convert("RGB")
    w, h = im.size
    nh = round(h * IMG_W / w)
    im = im.resize((IMG_W, max(nh, IMG_H)), Image.LANCZOS)
    top = (im.size[1] - IMG_H) // 2
    im = im.crop((0, top, IMG_W, top + IMG_H))
    a = np.array(im, dtype=np.float64)
    out = np.zeros((IMG_H, IMG_W), dtype=np.uint8)
    rl, gl, bl = np.array(show.R_LEV, float), np.array(show.G_LEV, float), np.array(show.B_LEV, float)
    for y in range(IMG_H):
        for x in range(IMG_W):
            r, g, b = a[y, x]
            ri = int(np.argmin(abs(rl - r)))
            gi = int(np.argmin(abs(gl - g)))
            bi = int(np.argmin(abs(bl - b)))
            q = (rl[ri], gl[gi], bl[bi])
            out[y, x] = 16 + ri * 40 + gi * 5 + bi
            err = (r - q[0], g - q[1], b - q[2])
            for dx, dy, f in ((1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16)):
                xx, yy = x + dx, y + dy
                if 0 <= xx < IMG_W and yy < IMG_H:
                    a[yy, xx] += np.array(err) * f
    return out


# ---------------------------------------------------------------- patterns
PATTERNS = [
    [0xFF] * 8,                                                  # 0 black
    [0x00] * 8,                                                  # 1 white
    [0xAA, 0x55] * 4,                                            # 2 50% grey
    [0x88, 0x00, 0x22, 0x00] * 2,                                # 3 light
    [0xFF, 0x80, 0x80, 0x80, 0xFF, 0x08, 0x08, 0x08],            # 4 bricks
    [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80],            # 5 diagonal
    [0x11, 0x22, 0x44, 0x88, 0x11, 0x22, 0x44, 0x88],            # 6 fine diagonal
    [0xFF, 0x00, 0xFF, 0x00, 0xFF, 0x00, 0xFF, 0x00],            # 7 lines
    [0x88, 0x88, 0x88, 0xFF, 0x88, 0x88, 0x88, 0xFF],            # 8 grid
    [0x18, 0x3C, 0x7E, 0xFF, 0xFF, 0x7E, 0x3C, 0x18],            # 9 diamonds
    [0x10, 0x38, 0x7C, 0xFE, 0x7C, 0x38, 0x10, 0x00],            # 10 dots
    [0xC0, 0xC0, 0x03, 0x03, 0xC0, 0xC0, 0x03, 0x03],            # 11 checks
    [0x81, 0x42, 0x24, 0x18, 0x18, 0x24, 0x42, 0x81],            # 12 crosses
    [0xEE, 0xDD, 0xBB, 0x77, 0xEE, 0xDD, 0xBB, 0x77],            # 13 dark diagonal
    [0xF0, 0xF0, 0xF0, 0xF0, 0x0F, 0x0F, 0x0F, 0x0F],            # 14 big checks
    [0x80, 0x40, 0x20, 0x00, 0x02, 0x04, 0x08, 0x00],            # 15 weave
]


# -------------------------------------------------------------- the stage
def rect_sub(a, b):
    """The parts of rectangle a outside rectangle b, as up to four rectangles."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    if not isect(a, b):
        return [a]
    out = []
    if by > ay:
        out.append((ax, ay, aw, by - ay))
    if by + bh < ay + ah:
        out.append((ax, by + bh, aw, ay + ah - by - bh))
    y0, y1 = max(ay, by), min(ay + ah, by + bh)
    if bx > ax:
        out.append((ax, y0, bx - ax, y1 - y0))
    if bx + bw < ax + aw:
        out.append((bx + bw, y0, ax + aw - bx - bw, y1 - y0))
    return [r for r in out if r[2] > 0 and r[3] > 0]


def isect(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


class Stage:
    """The script, plus what is on the screen: the pointer, and the stack of
    desktop elements a repair redraws."""

    def __init__(self, S):
        self.S = S
        self.cx, self.cy = 320, 240
        self.cvis = False
        self.elems = []

    # -- the pointer
    def cursor_box(self):
        return (self.cx, self.cy, show.CURW, show.CURH)

    def draw(self, bbox, fn):
        """Run fn (which emits drawing) with the pointer hidden if it is in the way."""
        hide = self.cvis and (bbox is None or isect(bbox, self.cursor_box()))
        if hide:
            self.S.hide()
        fn()
        if hide:
            self.S.show()

    def show_cursor(self):
        if not self.cvis:
            self.S.curs(self.cx, self.cy)
            self.S.show()
            self.cvis = True

    def glide(self, x, y, frames=None, hover=None, per_frame=None):
        x0, y0 = self.cx, self.cy
        dist = math.hypot(x - x0, y - y0)
        if frames is None:
            frames = max(6, min(60, int(dist / 9)))
        for i in range(1, frames + 1):
            t = i / frames
            t = t * t * (3 - 2 * t)
            nx, ny = round(x0 + (x - x0) * t), round(y0 + (y - y0) * t)
            if per_frame:
                per_frame(i, nx, ny)
            if hover:
                hover(nx, ny)
            if (nx, ny) != (self.cx, self.cy):
                self.cx, self.cy = nx, ny
                self.S.curs(nx, ny)
            self.S.sync(1)

    def click(self, frames=6):
        self.S.sync(frames)

    # -- the desktop's stack
    def top(self, e):
        if e in self.elems:
            self.elems.remove(e)
        self.elems.append(e)

    def remove(self, e):
        self.elems.remove(e)

    def repair(self, rect, skip=()):
        x, y, w, h = rect
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(SW, x + w), min(SH, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        rect = (x0, y0, x1 - x0, y1 - y0)

        def go():
            self.S.fill(*rect, C["desk"])
            dmg = [rect]
            for e in self.elems:
                if e in skip:
                    continue
                if any(isect(e.bbox(), d) for d in dmg):
                    e.draw(self.S)
                    dmg.append(e.bbox())
        self.draw(rect, go)

    def redraw_all(self):
        self.repair((0, 0, SW, SH))


def bevel(S, x, y, w, h, fill=C["panel"], raised=True):
    lt, dk = (C["light"], C["frame"]) if raised else (C["frame"], C["light"])
    S.fill(x, y, w, h, fill)
    S.fill(x, y, w, 1, lt)
    S.fill(x, y, 1, h, lt)
    S.fill(x, y + h - 1, w, 1, dk)
    S.fill(x + w - 1, y, 1, h, dk)


def text_center(S, x, w, y, fg, bg, s):
    S.text(x + (w - 8 * len(s)) // 2, y, fg, bg, s)


class DeskIcon:
    def __init__(self, ic, x, y, label):
        self.ic, self.x, self.y, self.label, self.sel = ic, x, y, label, False

    def bbox(self):
        lw = max(40, 8 * len(self.label) + 4)
        return (self.x + 20 - lw // 2, self.y, lw, 54)

    def draw(self, S):
        bx, by, bw, bh = self.bbox()
        if self.sel:
            S.fill(bx, by, bw, bh, C["desk"])
        S.icon(self.x + 4, self.y, ICON[self.ic], 1 if self.sel else 0)
        lw = 8 * len(self.label)
        if self.sel:
            S.fill(self.x + 20 - lw // 2 - 2, self.y + 36, lw + 4, 18, C["sel"])
        S.text(self.x + 20 - lw // 2, self.y + 37, C["white"], 0xFF, self.label)


class Deskbar:
    X, W = 512, 128

    def __init__(self):
        self.apps = ["Tracker"]
        self.open = False

    def bbox(self):
        return (self.X, 0, self.W, 44 + 20 * len(self.apps))

    def draw(self, S):
        x, w = self.X, self.W
        S.fill(x, 0, w, self.bbox()[3], C["shadow"])
        bevel(S, x + 1, 0, w - 2, 23, C["sel"] if self.open else C["panel"])
        S.icon(x + 8, 4, ICON["leaf"], 0)
        S.text(x + 30, 4, C["white"] if self.open else C["black"], 0xFF, "arm6309")
        bevel(S, x + 1, 23, w - 2, 20)
        S.text(x + w - 48, 25, C["black"], 0xFF, "12:34")
        S.fill(x + 8, 28, 10, 10, C["green"])
        for i, a in enumerate(self.apps):
            yy = 43 + 20 * i
            bevel(S, x + 1, yy, w - 2, 20)
            S.text(x + 10, yy + 2, C["black"], 0xFF, a)


class Window:
    """A Haiku window: a yellow tab over its left edge, a five-pixel frame."""

    def __init__(self, x, y, w, h, title):
        self.x, self.y, self.w, self.h, self.title = x, y, w, h, title
        self.active = True

    def tabw(self):
        return 8 * len(self.title) + 52

    def bbox(self):
        return (self.x, self.y - 19, self.w, self.h + 19)

    def drawn(self):
        """What the window actually covers: the tab and the body."""
        return [(self.x, self.y - 19, self.tabw(), 19), (self.x, self.y, self.w, self.h)]

    def close_box(self):
        return (self.x + 8, self.y - 14)

    def chrome(self, S):
        x, y, w, h = self.x, self.y, self.w, self.h
        tw = self.tabw()
        S.fill(x, y - 19, tw, 19, C["shadow"])
        S.fill(x + 1, y - 18, tw - 2, 18, C["tab"] if self.active else C["itab"])
        S.fill(x + 1, y - 18, tw - 2, 1, C["pale"])
        bevel(S, x + 7, y - 15, 12, 12, C["tab"] if self.active else C["itab"])
        S.text(x + 26, y - 17, C["black"], 0xFF, self.title)
        bevel(S, x + tw - 20, y - 15, 12, 12, C["tab"] if self.active else C["itab"])
        S.fill(x + tw - 17, y - 12, 7, 7, C["frame"])
        S.fill(x, y, w, h, C["shadow"])
        S.fill(x + 1, y + 1, w - 2, h - 2, C["panel"])
        S.fill(x + 1, y + 1, w - 2, 1, C["light"])
        S.fill(x + 1, y + 1, 1, h - 2, C["light"])
        S.fill(x + 4, y + 4, w - 8, h - 8, C["frame"])

    def content(self):
        return (self.x + 5, self.y + 5, self.w - 10, self.h - 10)


class FilesWindow(Window):
    LEFT = [("folder16", "apps"), ("folder16", "config"), ("folder16", "Desktop"), ("folder16", "Documents"),
            ("folder16", "Pictures"), ("folder16", "Music"), ("doc16", "readme.txt")]
    RIGHT = [("image16", "parrot.img"), ("image16", "sunset.img"), ("image16", "tiles.img"),
             ("doc16", "palette.txt"), ("doc16", "notes.txt")]

    def __init__(self, x, y):
        super().__init__(x, y, 368, 232, "Files")
        self.lsel = None
        self.rshow = False
        self.rsel = None

    def row_rect(self, pane, i):
        cx, cy, cw, ch = self.content()
        pw = (cw - 6) // 2
        px = cx + 2 + (pw + 2) * pane
        return (px + 1, cy + 44 + 18 * i, pw - 2, 18)

    def draw(self, S, rows=True):
        self.chrome(S)
        cx, cy, cw, ch = self.content()
        S.fill(cx, cy, cw, ch, C["panel"])
        S.text(cx + 6, cy + 4, C["black"], C["panel"], "File  Edit  View  Go")
        S.fill(cx, cy + 22, cw, 1, C["frame"])
        pw = (cw - 6) // 2
        for pane, path in enumerate(["/boot/home", "/boot/home/Pictures" if self.rshow else "/boot/home/Pictures"]):
            px = cx + 2 + (pw + 2) * pane
            S.fill(px, cy + 26, pw, ch - 28, C["shadow"])
            S.fill(px + 1, cy + 27, pw - 2, 16, C["itab"])
            S.text(px + 4, cy + 27, C["black"], C["itab"], (path if pane == 0 else ("Pictures" if self.rshow else "-"))[:pw // 8 - 1])
            S.fill(px + 1, cy + 43, pw - 2, ch - 46, C["white"])
            if rows:
                self.draw_rows(S, pane)

    def draw_rows(self, S, pane):
        rows = self.LEFT if pane == 0 else (self.RIGHT if self.rshow else [])
        sel = self.lsel if pane == 0 else self.rsel
        for i, (ic, name) in enumerate(rows):
            self.draw_row(S, pane, i, ic, name, i == sel)

    def draw_row(self, S, pane, i, ic, name, sel):
        x, y, w, h = self.row_rect(pane, i)
        S.fill(x, y, w, h, C["sel"] if sel else C["white"])
        S.icon(x + 2, y + 1, ICON[ic], 1 if sel else 0)
        S.text(x + 22, y + 1, C["white"] if sel else C["black"], C["sel"] if sel else C["white"], name[:(w - 24) // 8])


class PlayerWindow(Window):
    """The audio player: a file, a status line, Play and Stop."""

    def __init__(self, x, y):
        super().__init__(x, y, 256, 124, "Audio Player")
        self.status = "Stopped"

    def button(self, which):
        cx, cy, cw, ch = self.content()
        return (cx + 16 + (0 if which == "play" else 112), cy + 64, 96, 36)

    def draw_button(self, S, which, pressed=False):
        x, y, w, h = self.button(which)
        bevel(S, x, y, w, h, C["frame"] if pressed else C["panel"], raised=not pressed)
        if which == "play":
            poly_convex(S, [(x + 38, y + 9), (x + 38, y + 27), (x + 56, y + 18)], colour=C["green"])
        else:
            S.fill(x + 40, y + 10, 16, 16, C["red"])

    def draw_status(self, S):
        cx, cy, cw, ch = self.content()
        S.fill(cx + 16, cy + 38, cw - 32, 16, C["black"])
        S.text(cx + 20, cy + 38, C["green"], C["black"], self.status)

    def draw(self, S):
        self.chrome(S)
        cx, cy, cw, ch = self.content()
        S.fill(cx, cy, cw, ch, C["panel"])
        S.icon(cx + 8, cy + 2, ICON["doc16"], 0)
        S.text(cx + 30, cy + 4, C["black"], C["panel"], MOD_TITLE[:26])
        S.fill(cx + 8, cy + 26, cw - 16, 1, C["frame"])
        self.draw_status(S)
        self.draw_button(S, "play")
        self.draw_button(S, "stop")


class Menu:
    def __init__(self, x, y, items, w=None):
        self.x, self.y, self.items = x, y, items
        self.w = w or max(8 * len(t) for t in items if t) + 32
        self.hover = None

    def item_rect(self, i):
        y = self.y + 3
        for k, t in enumerate(self.items):
            h = 20 if t else 7
            if k == i:
                return (self.x + 2, y, self.w - 4, h)
            y += h

    def bbox(self):
        return (self.x, self.y, self.w, sum(20 if t else 7 for t in self.items) + 6)

    def draw(self, S):
        x, y, w, h = self.bbox()
        S.fill(x, y, w, h, C["shadow"])
        S.fill(x + 1, y + 1, w - 2, h - 2, C["panel"])
        S.fill(x + 1, y + 1, w - 2, 1, C["light"])
        for i in range(len(self.items)):
            self.draw_item(S, i)

    def draw_item(self, S, i):
        x, y, w, h = self.item_rect(i)
        t = self.items[i]
        if not t:
            S.fill(x, y, w, h, C["panel"])
            S.fill(x + 4, y + 3, w - 8, 1, C["frame"])
            return
        hot = i == self.hover
        S.fill(x, y, w, h, C["frame"] if hot else C["panel"])
        S.text(x + 14, y + 2, C["black"], C["frame"] if hot else C["panel"], t)

    def at(self, px, py):
        for i, t in enumerate(self.items):
            if t:
                x, y, w, h = self.item_rect(i)
                if x <= px < x + w and y <= py < y + h:
                    return i
        return None


# ------------------------------------------------------------ the script
def main():
    global ICON, MOD_TITLE
    MOD_TITLE = open(os.path.join(B, "demo.mod"), "rb").read(20).split(b"\0")[0].decode("latin-1").strip() or "demo.mod"
    os.makedirs(B, exist_ok=True)
    f16, f8 = show.font(16), show.font(8)
    gfx = f16.tobytes() + f8.tobytes()
    icons_bin, ICON, icon_list = build_icons()
    image = build_image()

    S = show.Script()
    st = Stage(S)
    pal = PAL

    # ---- the desktop -------------------------------------------------------
    for p, rows in enumerate(PATTERNS):
        S.patdef(p, rows)
    S.ctrl(0x00)
    S.pal(pal)
    S.ctrl(0xC3)                                    # display, VBL IRQ, VMODE 11
    home = DeskIcon("home", 24, 16, "home")
    disk = DeskIcon("disk", 24, 88, "arm6309")
    files_ic = DeskIcon("files", 24, 160, "Files")
    trash = DeskIcon("trash", 24, 402, "Trash")
    bar = Deskbar()
    st.elems = [home, disk, files_ic, trash, bar]
    st.redraw_all()
    st.S.check("the desktop, drawn")
    st.cx, st.cy = 300, 260
    st.show_cursor()
    S.sync(15)
    S.check("the pointer")

    app_items = ["Paint", "Connect to BBS", "Raster Bars Demo", "Zelda", "Audio Player", "",
                 "About arm6309", "Shut down"]

    def deskbar_menu(choice):
        st.glide(bar.X + 16, 10)
        st.click(4)
        bar.open = True
        menu = Menu(bar.X - 60, 23, app_items, w=188)
        st.top(menu)

        def open_menu():
            bar.draw(S)
            menu.draw(S)
        st.draw(menu.bbox(), open_menu)
        ck = S.check("the application menu")
        i = app_items.index(choice)
        ix, iy, iw, ih = menu.item_rect(i)

        def hover(px, py):
            h = menu.at(px, py)
            if h != menu.hover:
                old = menu.hover
                menu.hover = h

                def redraw():
                    if old is not None:
                        menu.draw_item(S, old)
                    if h is not None:
                        menu.draw_item(S, h)
                st.draw(menu.bbox(), redraw)
        st.glide(ix + 40, iy + 10, frames=10 + 4 * i, hover=hover)
        S.sync(8)
        S.check(f"'{choice}' under the pointer")
        st.click(4)
        bar.open = False
        st.remove(menu)
        st.repair(menu.bbox())
        st.draw(bar.bbox(), lambda: bar.draw(S))
        return menu


    # ---- the audio player: Play ------------------------------------------------
    player = PlayerWindow(208, 150)

    def player_open():
        deskbar_menu("Audio Player")
        st.top(player)
        st.draw(player.bbox(), lambda: player.draw(S))
        S.check(f"the audio player, {player.status.lower()}")

    def player_press(which, status, action):
        bx, by, bw, bh = player.button(which)
        st.glide(bx + bw // 2, by + bh // 2)
        st.click(3)
        st.draw(player.bbox(), lambda: player.draw_button(S, which, pressed=True))
        S.sync(6)
        player.status = status

        def rel():
            player.draw_button(S, which, pressed=False)
            player.draw_status(S)
        st.draw(player.bbox(), rel)
        action()

    def player_close():
        cbx, cby = player.close_box()
        st.glide(cbx + 6, cby + 6)
        st.click(4)
        st.remove(player)
        st.repair(player.bbox())

    player_open()

    def play():
        S.op("MUSIC")
        player.status = "Playing"
        st.draw(player.bbox(), lambda: player.draw_status(S))
    player_press("play", "Loading...", play)
    S.check("the audio player, playing")
    bar.apps.append("Audio Player")
    st.draw(bar.bbox(), lambda: bar.draw(S))
    S.sync(20)
    player_close()
    S.check("the module playing, the player closed")

    # ---- Files: select, open -----------------------------------------------
    st.glide(files_ic.x + 18, files_ic.y + 14)
    st.click(4)
    files_ic.sel = True
    st.draw(files_ic.bbox(), lambda: files_ic.draw(S))
    st.click(6)
    S.check("Files selected")
    fw = FilesWindow(96, 64)
    bar.apps.append("Files")
    st.top(fw)
    st.draw(fw.bbox(), lambda: fw.draw(S))
    st.draw(bar.bbox(), lambda: bar.draw(S))
    S.check("the dual-pane browser")
    S.sync(10)

    # left pane: Pictures
    r = fw.row_rect(0, 4)
    st.glide(r[0] + 40, r[1] + 8)
    st.click(4)

    def pick_left():
        fw.lsel = 4
        fw.draw_row(S, 0, 4, "folder16", "Pictures", True)
        fw.rshow = True
        fw.draw(S)
    st.draw(fw.bbox(), pick_left)
    S.check("Pictures chosen")
    S.sync(10)
    r = fw.row_rect(1, 0)
    st.glide(r[0] + 50, r[1] + 8)
    st.click(4)

    def pick_right():
        fw.rsel = 0
        fw.draw_row(S, 1, 0, "image16", "parrot.img", True)
    st.draw(r, pick_right)
    S.check("parrot.img selected")
    S.sync(10)
    r = fw.row_rect(1, 3)
    st.glide(r[0] + 50, r[1] + 8, frames=14)
    st.click(4)

    def pick_right2():
        fw.draw_row(S, 1, 0, "image16", "parrot.img", False)
        fw.rsel = 3
        fw.draw_row(S, 1, 3, "doc16", "palette.txt", True)
    st.draw(fw.bbox(), pick_right2)
    S.check("palette.txt selected")
    S.sync(7)

    # drag the window by its tab
    tx, ty = fw.x + 60, fw.y - 10
    st.glide(tx, ty)
    st.click(3)
    DX, DY, steps = 136, 120, 16
    for i in range(1, steps + 1):
        nx = 96 + round(DX * i / steps)
        ny = 64 + round(DY * i / steps)
        old = fw.drawn()
        fw.x, fw.y = nx, ny
        new = fw.drawn()

        def step():
            # what the window uncovers, then the window where it is now
            for r in old:
                parts = [r]
                for n in new:
                    parts = [q for p in parts for q in rect_sub(p, n)]
                for q in parts:
                    st.repair(q, skip=(fw,))
            fw.draw(S, rows=(i == steps))     # the rows go in when it is dropped
        S.hide()
        step()
        st.cx, st.cy = tx + (nx - 96), ty + (ny - 64)
        S.curs(st.cx, st.cy)
        S.show()
        S.sync(1)
    S.sync(4)
    S.check("the window dragged")
    S.sync(6)

    # ---- the Deskbar menu: Paint ------------------------------------------
    deskbar_menu("Paint")

    # ---- Paint --------------------------------------------------------------
    CAN_Y0, CAN_Y1 = 85, 430
    pw = Window(0, 20, 640, 460, "Paint - untitled")
    canvas_ops = []                                 # (bbox, fn) in drawing order

    def cop(bbox, fn):
        canvas_ops.append((bbox, fn))
        st.draw(bbox, fn)

    def tool_rect(i):
        return (6 + 38 * i, 44, 36, 38)

    tool_sel = [11]

    def draw_tool(i):
        x, y, w, h = tool_rect(i)
        sel = i == tool_sel[0]
        bevel(S, x, y, w, h, C["black"] if sel else C["panel"], raised=not sel)
        S.icon(x + 10, y + 11, ICON["tool_" + TOOL_ORDER[i]], 1 if sel else 0)

    def swatch_rect(i):
        return (160 + 24 * i, 434, 24, 24)

    COLOURS = [C["black"], C["red"], C["orange"], cidx((250, 220, 30)), C["green"], cidx((40, 90, 220)),
               cidx((150, 60, 200)), C["white"]]

    def draw_paint_chrome():
        x, y = 0, 20
        # the tab and the frame, full width: the canvas rows carry no frame,
        # because a display list scrolls every pixel on a line
        tw = pw.tabw()
        S.fill(0, 0, tw, 20, C["shadow"])
        S.fill(1, 1, tw - 2, 19, C["tab"])
        bevel(S, 7, 4, 12, 12, C["tab"])
        S.text(26, 2, C["black"], 0xFF, pw.title)
        S.fill(tw, 0, SW - tw, 20, C["desk"])
        bevel(S, 0, 20, SW, 21)
        S.text(8, 23, C["black"], 0xFF, "File  Edit  Goodies  Font  FontSize  Style")
        S.fill(0, 41, SW, 44, C["panel"])
        S.fill(0, 84, SW, 1, C["shadow"])
        for i in range(len(TOOL_ORDER)):
            draw_tool(i)
        S.fill(0, CAN_Y1, SW, 32, C["panel"])
        S.fill(0, CAN_Y1, SW, 1, C["shadow"])
        bevel(S, 8, 434, 40, 24, C["white"], raised=False)
        S.pat(16, 438, 24, 16, C["black"], C["white"], 4)
        for i in range(4):
            S.pat(56 + 24 * i, 434, 24, 24, C["black"], C["white"], [2, 4, 8, 9][i])
        for i, c in enumerate(COLOURS):
            x, y, w, h = swatch_rect(i)
            S.fill(x, y, w, h, C["shadow"])
            S.fill(x + 2, y + 2, w - 4, h - 4, c)
        for i in range(6):
            S.pat(360 + 24 * i, 434, 24, 24, C["black"], C["white"], [5, 6, 10, 11, 12, 14][i])
        draw_scrollbar(0)

    SB_Y = 462

    def thumb_x(v):
        return 20 + round(v * (SW - 40 - 400) / 384)

    def draw_scrollbar(v, old=None):
        if old is None:
            S.fill(0, SB_Y, SW, 18, C["frame"])
            bevel(S, 0, SB_Y, 18, 18)
            bevel(S, SW - 18, SB_Y, 18, 18)
            S.fill(18, SB_Y + 1, SW - 36, 16, C["itab"])
            bevel(S, thumb_x(v), SB_Y + 1, 400, 16)
            return
        # Only the columns that change: a drag step is drawn between one list's
        # END and the next blank, ~3 ms a frame, and two whole 400 x 16 thumbs
        # were half of it (gui.asm's lyield). The picture is bevel()'s exactly.
        x0, x1, y = thumb_x(old), thumb_x(v), SB_Y + 1
        lt, dk = C["light"], C["frame"]
        if x1 > x0:
            d = x1 - x0
            S.fill(x0, y, d, 16, C["itab"])              # the columns left behind
            S.fill(x0 + 399, y, d, 16, C["panel"])       # the old right edge and the new interior
            S.fill(x0 + 399, y, d, 1, lt)
            S.fill(x0 + 399, y + 15, d, 1, dk)
            S.fill(x1 + 399, y, 1, 16, dk)               # the new right edge
            S.fill(x1, y + 1, 1, 14, lt)                 # the new left edge
        elif x1 < x0:
            d = x0 - x1
            S.fill(x1 + 400, y, d, 16, C["itab"])
            S.fill(x1, y, d + 1, 16, C["panel"])         # the new left edge, and the old one's column
            S.fill(x1, y, d + 1, 1, lt)
            S.fill(x1, y + 15, d + 1, 1, dk)
            S.fill(x1, y + 1, 1, 14, lt)
            S.fill(x1 + 399, y, 1, 16, dk)

    def open_paint():
        S.hide()
        draw_paint_chrome()
        S.fill(0, CAN_Y0, 640, CAN_Y1 - CAN_Y0, C["white"])
        S.fill(640, CAN_Y0, 384, CAN_Y1 - CAN_Y0, C["white"])
        # the part of the document right of the window: drawn now, seen when it scrolls
        S.fill(640, 150, 384, 180, cidx((150, 200, 250)))
        poly_convex(S, [(640, 400), (820, 230), (1000, 400)], colour=cidx((90, 110, 90)))
        poly_convex(S, [(780, 400), (900, 250), (1020, 400)], colour=cidx((120, 140, 110)))
        S.poly(cidx((255, 230, 120)), [(960, 160), (935, 185), (960, 210)], [(960, 160), (985, 185), (960, 210)])
        S.fill(640, 400, 384, 30, cidx((60, 120, 60)))
        S.text(700, 180, C["black"], 0xFF, "drawn off the screen,")
        S.text(700, 198, C["black"], 0xFF, "brought in by a display list")
        S.show()
    st.cvis = True
    open_paint()
    S.check("Paint opens")
    S.sync(7)

    def pick_tool(i):
        x, y, w, h = tool_rect(i)
        st.glide(x + 18, y + 20)
        st.click(4)
        old = tool_sel[0]
        tool_sel[0] = i

        def redraw():
            draw_tool(old)
            draw_tool(i)
        st.draw((0, 41, SW, 44), redraw)

    # a) PaintRect, rubber-banded
    pick_tool(TOOL_ORDER.index("frect"))
    st.glide(40, 110)
    S.sync(4)
    ax0, ay0 = 40, 110
    prev = None
    for i in range(1, 31):
        t = i / 30
        bx, by = round(40 + 200 * t), round(110 + 110 * t)

        def band(r, c):
            x, y, w, h = r
            S.fill(x, y, w, 1, c)
            S.fill(x, y + h - 1, w, 1, c)
            S.fill(x, y, 1, h, c)
            S.fill(x + w - 1, y, 1, h, c)
        S.hide()
        if prev:
            band(prev, C["white"])
        prev = (ax0, ay0, bx - ax0 + 1, by - ay0 + 1)
        band(prev, C["black"])
        st.cx, st.cy = bx, by
        S.curs(bx, by)
        S.show()
        S.sync(1)
    rect1 = prev

    def paint_rect1():
        x, y, w, h = rect1
        S.fill(x, y, w, h, C["black"])
        S.fill(x + 2, y + 2, w - 4, h - 4, C["red"])
    cop(rect1, paint_rect1)
    S.check("PaintRect")
    S.sync(6)

    # b) a pattern fill inside an outline
    pick_tool(TOOL_ORDER.index("rect"))
    st.glide(288, 104)
    rect2 = (288, 104, 208, 120)

    def frame2():
        x, y, w, h = rect2
        S.fill(x, y, w, 2, C["black"])
        S.fill(x, y + h - 2, w, 2, C["black"])
        S.fill(x, y, 2, h, C["black"])
        S.fill(x + w - 2, y, 2, h, C["black"])
    st.glide(496, 224, frames=20)
    cop(rect2, frame2)
    S.sync(6)
    pick_tool(TOOL_ORDER.index("bucket"))
    sx, sy, _, _ = swatch_rect(0)
    st.glide(56 + 24 + 12, 446)                    # the bricks swatch
    st.click(4)
    st.glide(400, 170)
    st.click(4)
    cop(rect2, lambda: S.pat(296, 112, 192, 104, cidx((170, 60, 30)), cidx((250, 220, 190)), 4))
    S.check("a pattern fill")
    S.sync(6)

    # c) polygons: a solid triangle, and a patterned star in convex pieces
    pick_tool(TOOL_ORDER.index("fpoly"))
    tri = [(560, 100), (620, 220), (520, 200)]
    for v in tri:
        st.glide(*v, frames=10)
        st.click(3)
    cop((520, 100, 101, 121), lambda: S.poly(cidx((40, 90, 220)), [(560, 100), (520, 200), (620, 220)],
                                             [(560, 100), (620, 220)]))
    S.check("a polygon")
    S.sync(8)
    cxs, cys, R1, R2 = 140, 330, 70, 28
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rr = R1 if k % 2 == 0 else R2
        pts.append((round(cxs + rr * math.cos(a)), round(cys + rr * math.sin(a))))
    for v in pts[::2]:
        st.glide(*v, frames=8)
        st.click(2)
    st.glide(250, 380, frames=10)

    def star():
        # five triangles out to the points, and the pentagon in the middle
        centre = (cxs, cys)
        for k in range(5):
            tip, l, r = pts[2 * k], pts[(2 * k - 1) % 10], pts[(2 * k + 1) % 10]
            poly_tri(S, [tip, l, r], (C["black"], cidx((250, 200, 40)), 10))
        inner = [pts[2 * k + 1] for k in range(5)]
        poly_convex(S, inner, (C["black"], cidx((250, 200, 40)), 10))
    cop((cxs - R1, cys - R1, 2 * R1 + 1, 2 * R1 + 1), star)
    S.check("a patterned polygon")
    S.sync(6)

    # d) glyph blits: the text tool
    pick_tool(TOOL_ORDER.index("text"))
    st.glide(260, 272)
    st.click(4)
    st.glide(250, 300, frames=6)
    msg = "Hello from a 6809 - every glyph is 16 writes"
    for i, ch in enumerate(msg):
        cop((260 + 8 * i, 262, 8, 16), lambda i=i, ch=ch: S.text(260 + 8 * i, 262, C["black"], 0xFF, ch))
        S.sync(2)
    S.check("text")
    S.sync(6)

    # e) horizontal spans: brush strokes
    pick_tool(TOOL_ORDER.index("brush"))
    stroke_cols = [cidx(c) for c in [(255, 60, 40), (255, 140, 0), (255, 220, 0), (60, 200, 60),
                                     (40, 140, 240), (120, 60, 220)]]
    for k, c in enumerate(stroke_cols):
        y = 300 + 12 * k
        st.glide(264, y + 3, frames=8)
        x = 264
        for step in range(18):
            nx = x + 20

            def seg(x=x, nx=nx, y=y, c=c):
                S.fill(x, y, nx - x, 8, c)
            cop((x, y, 20, 8), seg)
            st.cx, st.cy = nx, y + 3
            S.hide()
            S.curs(nx, y + 3)
            S.show()
            S.sync(1)
            x = nx
    S.sync(4)
    S.check("brush strokes")
    S.sync(6)

    # f) scroll: drag the thumb; a display list moves the canvas rows only, a
    #    pixel at a time where the drag is slow (graphics.md 19 item 49)
    st.glide(thumb_x(0) + 200, SB_Y + 8)
    st.click(3)
    v = 0
    for i in range(1, 49):
        t = i / 48
        nv = round(384 * t * t * (3 - 2 * t))
        tx = thumb_x(nv) + 200
        S.lisths(CAN_Y0, CAN_Y1, nv)
        st.cx = tx
        S.hide()
        draw_scrollbar(nv, old=v)
        S.curs(tx, SB_Y + 8)
        S.show()
        S.sync(1)
        v = nv
    S.sync(10)
    S.check("the canvas scrolled 384 pixels by display list")
    S.sync(30)
    for i in range(1, 49):
        t = 1 - i / 48
        nv = round(384 * t * t * (3 - 2 * t))
        tx = thumb_x(nv) + 200
        S.lisths(CAN_Y0, CAN_Y1, nv)
        st.cx = tx
        S.hide()
        draw_scrollbar(nv, old=v)
        S.curs(tx, SB_Y + 8)
        S.show()
        S.sync(1)
        v = nv
    S.listoff()
    S.sync(6)
    S.check("scrolled back")
    S.sync(10)

    def rep_canvas(rect):
        """What the File menu covered: the chrome under it, then every canvas
        operation that touched it, in order, and every later one those touch."""
        x, y, w, h = rect
        S.fill(x, y, w, h, C["white"])
        draw_paint_chrome()
        dmg = [rect]
        for bbox, fn in canvas_ops:
            if any(isect(bbox, d) for d in dmg):
                fn()
                dmg.append(bbox)
    # g) Goodies > Wave: every canvas line scrolled by its own fine HSCROLL
    st.glide(96, 30)
    st.click(4)
    gmenu = Menu(80, 40, ["Grid", "Fat Bits", "Brush Shape...", "", "Wave", "Mirrors"], w=160)
    st.draw(gmenu.bbox(), lambda: gmenu.draw(S))

    def ghover(px, py):
        h = gmenu.at(px, py)
        if h != gmenu.hover:
            old = gmenu.hover
            gmenu.hover = h

            def redraw():
                if old is not None:
                    gmenu.draw_item(S, old)
                if h is not None:
                    gmenu.draw_item(S, h)
            st.draw(gmenu.bbox(), redraw)
    ix, iy, iw, ih = gmenu.item_rect(4)
    st.glide(120, iy + 10, frames=12, hover=ghover)
    S.check("the Goodies menu")
    st.click(4)
    st.draw(gmenu.bbox(), lambda: rep_canvas(gmenu.bbox()))
    st.glide(600, 470, frames=12)
    WY0, WN = CAN_Y0, 150
    wtab = [round(127.5 + 127.5 * math.sin(2 * math.pi * k / 256)) for k in range(256)]
    S.wavedf(WY0, WN, wtab)
    ph = 0
    for f in range(150 if not QUICK else 20):
        amp = min(24, 4 * (f // 10), 4 * ((149 - f) // 10)) if not QUICK else 12
        S.wave(ph, amp)
        S.sync(1)
        ph = (ph + 5) & 255
        if f == 60:
            S.check("the canvas waving")
    S.listoff()
    S.sync(6)
    S.check("the wave over")

    # ---- File > Open... -----------------------------------------------------
    st.glide(20, 30)
    st.click(4)
    fmenu = Menu(0, 40, ["New", "Open...", "Close", "", "Save", "Save As...", "", "Quit"], w=140)

    st.draw(fmenu.bbox(), lambda: fmenu.draw(S))
    S.check("the File menu")

    def fhover(px, py):
        h = fmenu.at(px, py)
        if h != fmenu.hover:
            old = fmenu.hover
            fmenu.hover = h

            def redraw():
                if old is not None:
                    fmenu.draw_item(S, old)
                if h is not None:
                    fmenu.draw_item(S, h)
            st.draw(fmenu.bbox(), redraw)
    ix, iy, iw, ih = fmenu.item_rect(1)
    st.glide(40, iy + 10, frames=14, hover=fhover)
    S.sync(8)
    st.click(4)
    st.draw(fmenu.bbox(), lambda: rep_canvas(fmenu.bbox()))
    # the chooser
    dw = Window(150, 150, 340, 230, "Open")

    def draw_dialog():
        dw.chrome(S)
        cx, cy, cw, ch = dw.content()
        S.fill(cx, cy, cw, ch, C["panel"])
        S.text(cx + 8, cy + 6, C["black"], C["panel"], "Look in: /boot/home/Pictures")
        S.fill(cx + 8, cy + 26, cw - 16, 132, C["shadow"])
        S.fill(cx + 9, cy + 27, cw - 18, 130, C["white"])
        for i, (ic, name) in enumerate(FilesWindow.RIGHT):
            draw_dlg_row(i, ic, name, False)
        bevel(S, cx + cw - 180, cy + ch - 34, 80, 26)
        text_center(S, cx + cw - 180, 80, cy + ch - 29, C["black"], 0xFF, "Cancel")
        bevel(S, cx + cw - 90, cy + ch - 34, 80, 26)
        text_center(S, cx + cw - 90, 80, cy + ch - 29, C["black"], 0xFF, "Open")

    def dlg_row(i):
        cx, cy, cw, ch = dw.content()
        return (cx + 10, cy + 28 + 20 * i, cw - 20, 20)

    def draw_dlg_row(i, ic, name, sel):
        x, y, w, h = dlg_row(i)
        S.fill(x, y, w, h, C["sel"] if sel else C["white"])
        S.icon(x + 4, y + 2, ICON[ic], 1 if sel else 0)
        S.text(x + 26, y + 2, C["white"] if sel else C["black"], C["sel"] if sel else C["white"], name)
    st.draw(dw.bbox(), draw_dialog)
    S.check("the file chooser")
    S.sync(10)
    r = dlg_row(0)
    st.glide(r[0] + 60, r[1] + 10)
    st.click(4)
    st.draw(r, lambda: draw_dlg_row(0, "image16", "parrot.img", True))
    S.check("parrot.img chosen")
    S.sync(7)
    cx, cy, cw, ch = dw.content()
    ob = (cx + cw - 90, cy + ch - 34, 80, 26)
    st.glide(ob[0] + 40, ob[1] + 13)
    st.click(2)

    def press():
        bevel(S, *ob, raised=False)
        text_center(S, ob[0], 80, ob[1] + 6, C["black"], 0xFF, "Open")
    st.draw(ob, press)
    S.sync(6)
    # the dialog goes and the picture comes in over the canvas it covered
    pw.title = "Paint - parrot.img"
    st.glide(560, 12, frames=16)

    def load():
        tw = pw.tabw()
        S.fill(0, 0, tw, 20, C["shadow"])
        S.fill(1, 1, tw - 2, 19, C["tab"])
        bevel(S, 7, 4, 12, 12, C["tab"])
        S.text(26, 2, C["black"], 0xFF, pw.title)
        S.fill(tw, 0, SW - tw, 20, C["desk"])
        S.image(0, CAN_Y0, IMG_W, IMG_H)
    st.draw((0, 0, SW, SH), load)
    S.check("parrot.img in the canvas")
    S.sync(300)                                     # five seconds at 59.94 Hz

    # close
    st.glide(13, 10)
    st.click(4)
    st.redraw_all()
    S.check("Paint closed")
    S.sync(10)

    # ---- the BBS -----------------------------------------------------------
    deskbar_menu("Connect to BBS")
    S.sync(6)
    S.hide()
    st.cvis = False
    S.ctrl(0x00)
    S.pal(show.ansi_palette())
    S.ctrl(0xC1)                                    # VMODE 01: 640 x 240, 80 x 30
    S.op("TINIT", bytes([30]))
    bbs(S)
    # back to the desktop
    S.ctrl(0x00)
    S.pal(pal)
    S.ctrl(0xC3)
    st.redraw_all()
    st.cx, st.cy = 330, 250
    st.show_cursor()
    S.check("the desktop again")
    S.sync(15)

    # ---- raster bars --------------------------------------------------------
    deskbar_menu("Raster Bars Demo")
    rw = Window(112, 112, 416, 300, "Raster Bars")
    st.top(rw)
    RY0, RN = 150, 100
    base = show.rgb565(10, 10, 40)

    def draw_raster():
        rw.chrome(S)
        cx, cy, cw, ch = rw.content()
        S.fill(cx, cy, cw, ch, C["black"])
        S.fill(cx + 8, RY0, cw - 16, 2 * RN, C["copper"])
        S.text(cx + 12, RY0 + 2 * RN + 16, C["white"], 0xFF, "one palette entry, rewritten on")
        S.text(cx + 12, RY0 + 2 * RN + 34, C["white"], 0xFF, "every scanline by the display list")
    rw.draw = lambda S_: draw_raster()
    S.pal([base], first=C["copper"])
    st.draw(rw.bbox(), draw_raster)
    grads = []
    for hue in [(255, 60, 60), (60, 255, 90), (80, 140, 255)]:
        g = []
        for d in range(8):
            f = math.cos(d / 8 * math.pi / 2) ** 1.5
            g.append(show.rgb565(*(int(10 + (c - 10) * f) for c in hue)))
        grads.append(g)
    sint = [int(round((RN - 1) / 2 + (RN / 2 - 8) * math.sin(2 * math.pi * k / 256))) for k in range(256)]
    S.rastdef(RY0, RN, C["copper"], base, grads, sint)
    st.glide(470, 440)
    S.check("the raster window")
    ph = 0
    for f in range(240 if not QUICK else 30):
        S.raster(ph)
        S.sync(1)
        ph = (ph + 3) & 255
    cbx, cby = rw.close_box()
    for_close = []

    def pf(i, nx, ny):
        nonlocal ph
        S.raster(ph)
        ph = (ph + 3) & 255
    st.glide(cbx + 6, cby + 6, frames=40, per_frame=pf)
    S.raster(ph)
    S.sync(4)
    S.listoff()
    st.remove(rw)
    S.pal([PAL[C["copper"]]], first=C["copper"])
    st.repair(rw.bbox())
    S.check("the raster window closed")
    S.sync(10)

    # ---- the overworld -------------------------------------------------------
    deskbar_menu("Zelda")
    S.sync(6)
    S.hide()
    st.cvis = False
    S.op("GAME")

    # ---- back to the desktop, and the audio player: Stop ----------------------
    S.ctrl(0x00)
    S.pal(pal)
    S.ctrl(0xC3)
    st.redraw_all()
    st.cx, st.cy = 330, 250
    st.show_cursor()
    S.check("the desktop after the game")
    player.status = "Playing"
    player_open()
    player_press("stop", "Stopped", lambda: S.op("STOP"))
    S.check("the audio player, stopped")
    bar.apps.remove("Audio Player")
    st.draw(bar.bbox(), lambda: bar.draw(S))
    S.sync(30)
    player_close()
    S.check("the end")
    S.sync(60)
    S.op("END")

    script = S.link()
    open(os.path.join(B, "script.bin"), "wb").write(script)
    open(os.path.join(B, "gfx.bin"), "wb").write(gfx)
    open(os.path.join(B, "icons.bin"), "wb").write(icons_bin)
    open(os.path.join(B, "image.bin"), "wb").write(image.tobytes())
    ol, fl = show.cursor_masks()
    inc = ["* GENERATED by software/tools/mkshow.py - do not edit",
           f"CUR_BLACK EQU   {show.CUR_BLACK}",
           f"CUR_WHITE EQU   {show.CUR_WHITE}",
           f"CURW    EQU     {show.CURW}",
           f"CURH    EQU     {show.CURH}",
           f"NCHECKS EQU     {S.next_check - 1}"]
    for name, m in (("curol", ol), ("curfl", fl)):
        cols = show.mask_rows(m)
        inc.append(name)
        for col in cols:
            inc.append("        FCB     " + ",".join(f"${b:02X}" for b in col))
    open(os.path.join(B, "show.inc"), "w").write("\n".join(inc) + "\n")
    open(os.path.join(B, "checks.txt"), "w").write("".join(f"{i} {w}\n" for i, w in S.checks))

    model = show.Model(script, gfx, icons_bin, image.tobytes(), list_dy=int(os.environ.get("LIST_DY", "0")))
    model.run()
    np.savez_compressed(os.path.join(B, "show.npz"),
                        **{f"idx{k}": v["idx"] for k, v in model.pictures.items()},
                        **{f"lst{k}": np.array(v["list"]) for k, v in model.pictures.items()},
                        **{f"pal{k}": v["pal"] for k, v in model.pictures.items()},
                        ids=np.array(sorted(model.pictures)))
    import pickle
    extra = {k: dict(rast=v["rast"], wave=v["wave"], ring=v["ring"]) for k, v in model.pictures.items()
             if v["rast"] is not None or v["wave"] is not None}
    pickle.dump(extra, open(os.path.join(B, "show_rast.pkl"), "wb"))
    print(f"ok    script {len(script)} bytes, {S.next_check - 1} checks, {len(icon_list)} icons "
          f"({len(icons_bin)} bytes), image {IMG_W} x {IMG_H}")


def poly_convex(S, pts, pattern=None, colour=None):
    """A convex polygon's vertices, in any order around it, to left and right
    chains from the top vertex to the bottom one."""
    n = len(pts)
    top = min(range(n), key=lambda i: (pts[i][1], pts[i][0]))
    bot = max(range(n), key=lambda i: (pts[i][1], -pts[i][0]))
    a, b = [pts[top]], [pts[top]]
    i = top
    while i != bot:
        i = (i + 1) % n
        a.append(pts[i])
    i = top
    while i != bot:
        i = (i - 1) % n
        b.append(pts[i])
    # the chain whose second vertex is further left is the left one
    def x_at_mid(ch):
        y = (ch[0][1] + ch[-1][1]) / 2
        for (x0, y0), (x1, y1) in zip(ch, ch[1:]):
            if y0 <= y <= y1 and y1 > y0:
                return x0 + (x1 - x0) * (y - y0) / (y1 - y0)
        return ch[0][0]
    left, right = (a, b) if x_at_mid(a) <= x_at_mid(b) else (b, a)
    S.poly(colour, left, right, pattern=pattern)


def poly_tri(S, pts, pattern=None, colour=None):
    poly_convex(S, pts, pattern, colour)


# --------------------------------------------------------------- the BBS
def esc(*codes):
    return "\x1b[" + ";".join(str(c) for c in codes) + "m"


CLS = "\x1b[2J"
RST = esc(0)


def bbs(S):
    def out(s, rate=32):
        S.rate(rate)
        S.term(s)

    def typed(s, per=5):
        for ch in s:
            S.rate(0)
            S.term(ch)
            S.sync(per)

    out(esc(0, 37) + "ARM6309 Terminal 1.0\r\n\r\n", rate=8)
    typed("ATZ")
    out("\r\nOK\r\n", rate=8)
    S.sync(10)
    typed("ATDT 555-6309")
    out("\r\n", rate=8)
    S.sync(50)
    out("CONNECT 19200\r\n", rate=8)
    S.sync(20)

    glyphs = {
        "6": ["#####", "#....", "#####", "#...#", "#####"],
        "3": ["#####", "....#", ".####", "....#", "#####"],
        "0": ["#####", "#...#", "#...#", "#...#", "#####"],
        "9": ["#####", "#...#", "#####", "....#", "#####"],
        "B": ["####.", "#...#", "####.", "#...#", "####."],
        "S": ["#####", "#....", "#####", "....#", "#####"],
        " ": [".....", ".....", ".....", ".....", "....."],
    }
    # a pixel is one cell across and half a cell down - square at 640 x 240 -
    # so five pixel rows are three text rows of upper, lower and full blocks
    cols = [esc(1, 31), esc(1, 33), esc(1, 32)]
    scr = CLS + "\r\n"
    for tr in range(3):
        cells = []
        for g in "6309 BBS":
            for c in range(5):
                top = glyphs[g][2 * tr][c] == "#"
                bot = 2 * tr + 1 < 5 and glyphs[g][2 * tr + 1][c] == "#"
                cells.append("\xdb" if top and bot else "\xdf" if top else "\xdc" if bot else " ")
            cells.append(" ")
        scr += " " * 16 + cols[tr] + "".join(cells) + "\r\n"
    scr += "\r\n"
    scr += esc(0, 34) + "  \xc9" + "\xcd" * 72 + "\xbb\r\n"
    title = "  The 6309 BBS"
    rest = "  -  node 1 of 1  -  an HD6309 and a span writer"
    scr += ("  \xba" + esc(1, 37) + title + esc(0, 36) + rest + " " * (72 - len(title) - len(rest))
            + esc(0, 34) + "\xba\r\n")
    scr += "  \xc8" + "\xcd" * 72 + "\xbc\r\n\r\n"
    menu = [("M", "Message Bases", "F", "File Areas"), ("D", "Door Games", "W", "Who's Online"),
            ("B", "Bulletins", "G", "Goodbye")]
    for a, at, b, bt in menu:
        scr += (f"     {esc(1, 34)}[{esc(1, 37)}{a}{esc(1, 34)}]{esc(0, 36)} {at:<24}"
                f"{esc(1, 34)}[{esc(1, 37)}{b}{esc(1, 34)}]{esc(0, 36)} {bt}\r\n")
    scr += "\r\n" + esc(0, 32) + "  Time left: " + esc(1, 32) + "59" + esc(0, 32) + " min.   " \
        + esc(1, 35) + "Main Menu " + esc(1, 30) + "\xfe " + esc(0, 37) + "Command: " + esc(1, 37)
    out(scr)
    S.check("the BBS main menu")
    S.sync(45)
    typed("D", per=8)
    doors = "\r\n\r\n" + esc(1, 33) + "  Door Games\r\n" + esc(0, 33) + "  " + "\xc4" * 40 + "\r\n"
    for k, name in enumerate(["Trade Wars 2002", "Legend of the Red Dragon", "Barren Realms Elite",
                              "Usurper", "Global War"]):
        doors += f"   {esc(1, 36)}{k + 1}{esc(0, 36)}) {esc(0, 37)}{name}\r\n"
    doors += "\r\n" + esc(1, 35) + "  Doors " + esc(1, 30) + "\xfe " + esc(0, 37) + "Which door? " + esc(1, 37)
    out(doors)
    S.check("the door menu")
    S.sync(30)
    typed("1", per=8)
    out("\r\n\r\n" + esc(0, 32) + "  Opening Trade Wars 2002 in 50-line mode...\r\n", rate=16)
    S.sync(20)
    S.ctrl(0xC2)                                    # VMODE 10: 640 x 400, 80 x 50
    S.op("TINIT", bytes([50]))

    tw = CLS + "\r\n\r\n"
    tw += esc(1, 31) + "          \xdc\xdc\xdc\xdc\xdc  \xdc\xdc\xdc\xdc   \xdc\xdc\xdc  \xdc\xdc\xdc\xdc  \xdc\xdc\xdc\xdc\xdc   " + esc(1, 33) + "\xdc   \xdc  \xdc\xdc\xdc  \xdc\xdc\xdc\xdc   \xdc\xdc\xdc\xdc\r\n"
    tw += esc(0, 31) + "            \xdb    \xdb\xdc\xdc\xdf  \xdb\xdc\xdc\xdc\xdb \xdb   \xdb \xdb\xdc\xdc\xdc    " + esc(0, 33) + "\xdb \xdc \xdb \xdb\xdc\xdc\xdc\xdb \xdb\xdc\xdc\xdf  \xdf\xdc\xdc\xdc\r\n"
    tw += esc(0, 31) + "            \xdb    \xdb  \xdb  \xdb   \xdb \xdb\xdc\xdc\xdc\xdf \xdb\xdc\xdc\xdc\xdc   " + esc(0, 33) + "\xdb\xdf \xdf\xdb \xdb   \xdb \xdb  \xdb  \xdc\xdc\xdc\xdf\r\n\r\n"
    tw += esc(1, 37) + "                          2 0 0 2" + esc(0, 36) + "   -   a mock-up, for the video card\r\n\r\n"
    tw += esc(0, 32) + "  Initializing...\r\n\r\n"
    tw += esc(1, 33) + "  Show today's log? " + esc(0, 37) + "(Y/N) " + esc(1, 37)
    out(tw)
    S.check("TradeWars 2002")
    S.sync(20)
    typed("N", per=10)
    out("\r\n\r\n" + esc(0, 35) + "  Searching the trader database...\r\n\r\n", rate=16)
    S.sync(15)

    def sector(num, where, beacon, port, planets, warps, extra=""):
        s = "\r\n" + esc(1, 32) + "Sector  " + esc(1, 33) + ": " + esc(1, 36) + f"{num}" + esc(0, 32) + f" in {where}.\r\n"
        if beacon:
            s += esc(0, 35) + "Beacon  " + esc(1, 33) + ": " + esc(1, 31) + beacon + "\r\n"
        if port:
            s += esc(0, 35) + "Ports   " + esc(1, 33) + ": " + esc(1, 36) + port + "\r\n"
        if planets:
            s += esc(0, 35) + "Planets " + esc(1, 33) + ": " + esc(0, 37) + planets + "\r\n"
        s += extra
        s += esc(1, 32) + "Warps to Sector(s) " + esc(1, 33) + ": " + esc(1, 36) + (esc(0, 32) + " - " + esc(1, 36)).join(warps) + "\r\n"
        return s

    def prompt(num):
        return ("\r\n" + esc(0, 35) + "Command [" + esc(1, 33) + "TL" + esc(0, 33) + "=" + esc(1, 33) + "00:00:00"
                + esc(0, 35) + "]" + esc(1, 33) + ":" + esc(0, 35) + "[" + esc(1, 36) + f"{num}" + esc(0, 35)
                + "] (" + esc(1, 33) + "?=Help" + esc(0, 35) + ")? " + esc(1, 37))

    out(sector(1, "The Federation", "FedSpace, FedLaw Enforced", "Sol, Class 0 (Special)",
               "(M) Terra", ["2", "3", "4", "5", "6", "7"]) + prompt(1))
    S.check("sector 1")
    S.sync(30)
    typed("M", per=8)
    out("\r\n" + esc(1, 37) + "<Move>\r\n" + esc(0, 35) + "Warps to which Sector [1] ? " + esc(1, 37), rate=16)
    typed("3", per=8)
    out("\r\n\r\n" + esc(1, 33) + "<Auto Pilot Engaged>\r\n", rate=16)
    S.sync(20)
    out(sector(3, "The Federation", None, "Aldebaran, Class 1 (BBS)", None, ["1", "(4)", "(8)", "212"])
        + prompt(3))
    S.check("sector 3")
    S.sync(25)
    typed("P", per=8)
    port = ("\r\n" + esc(1, 37) + "<Port>\r\n\r\n" + esc(0, 35) + "Docking...\r\n\r\n"
            + esc(1, 32) + "Commerce report for " + esc(1, 36) + "Aldebaran" + esc(0, 32) + ": 12:04:33 PM Sat Sep 13, 2026\r\n\r\n"
            + esc(1, 33) + " Items     Status  Trading % of max OnBoard\r\n"
            + esc(0, 35) + " -----     ------  ------- -------- -------\r\n"
            + esc(0, 36) + "Fuel Ore   " + esc(0, 32) + "Buying    " + esc(1, 36) + " 2340    100%       0\r\n"
            + esc(0, 36) + "Organics   " + esc(0, 32) + "Buying    " + esc(1, 36) + " 1210     62%       0\r\n"
            + esc(0, 36) + "Equipment  " + esc(0, 32) + "Selling   " + esc(1, 36) + " 1980     88%       0\r\n\r\n"
            + esc(0, 32) + "You have " + esc(1, 36) + "3,000" + esc(0, 32) + " credits and " + esc(1, 36) + "30"
            + esc(0, 32) + " empty cargo holds.\r\n\r\n"
            + esc(0, 35) + "How many holds of " + esc(1, 36) + "Equipment" + esc(0, 35) + " do you want to buy ["
            + esc(1, 33) + "30" + esc(0, 35) + "]? " + esc(1, 37))
    out(port)
    S.check("the port")
    S.sync(20)
    typed("30", per=10)
    out("\r\n" + esc(0, 32) + "We'll sell them for " + esc(1, 33) + "1,113" + esc(0, 32) + " credits.\r\n"
        + esc(0, 35) + "Your offer [" + esc(1, 33) + "1,113" + esc(0, 35) + "] ? " + esc(1, 37), rate=16)
    typed("1050", per=8)
    out("\r\n" + esc(0, 32) + "We'll sell them for " + esc(1, 33) + "1,090" + esc(0, 32) + " credits.\r\n"
        + esc(0, 35) + "Your offer [" + esc(1, 33) + "1,090" + esc(0, 35) + "] ? " + esc(1, 37), rate=16)
    typed("1080", per=8)
    out("\r\n\r\n" + esc(1, 32) + "You have " + esc(1, 36) + "1,920" + esc(1, 32) + " credits and "
        + esc(1, 36) + "0" + esc(1, 32) + " empty cargo holds.\r\n" + prompt(3), rate=16)
    S.sync(20)
    typed("M", per=8)
    out("\r\n" + esc(1, 37) + "<Move>\r\n" + esc(0, 35) + "Warps to which Sector [3] ? " + esc(1, 37), rate=16)
    typed("8", per=8)
    out("\r\n\r\n" + esc(1, 33) + "<Auto Pilot Engaged>\r\n", rate=16)
    S.sync(15)
    out(sector(8, "uncharted space", None, "Rigel, Class 2 (BSB)", "(L) Ferrengal Prime",
               ["3", "14", "97"], extra=esc(0, 35) + "Fighters" + esc(1, 33) + ": " + esc(1, 36) + "12"
               + esc(0, 32) + " (belong to " + esc(1, 31) + "the Cabal" + esc(0, 32) + ") [Defensive]\r\n")
        + prompt(8))
    S.check("sector 8")
    S.sync(25)
    typed("P", per=8)
    out("\r\n" + esc(1, 37) + "<Port>\r\n\r\n" + esc(0, 35) + "Docking...\r\n\r\n"
        + esc(1, 33) + " Items     Status  Trading % of max OnBoard\r\n"
        + esc(0, 35) + " -----     ------  ------- -------- -------\r\n"
        + esc(0, 36) + "Fuel Ore   " + esc(0, 32) + "Selling   " + esc(1, 36) + " 3110     96%       0\r\n"
        + esc(0, 36) + "Organics   " + esc(0, 32) + "Selling   " + esc(1, 36) + "  870     44%       0\r\n"
        + esc(0, 36) + "Equipment  " + esc(0, 32) + "Buying    " + esc(1, 36) + " 2450    100%      30\r\n\r\n"
        + esc(0, 35) + "We are buying up to " + esc(1, 33) + "2450" + esc(0, 35) + ".  You have "
        + esc(1, 33) + "30" + esc(0, 35) + " in your holds.\r\n"
        + esc(0, 35) + "How many holds of " + esc(1, 36) + "Equipment" + esc(0, 35) + " do you want to sell ["
        + esc(1, 33) + "30" + esc(0, 35) + "]? " + esc(1, 37), rate=16)
    typed("30", per=10)
    out("\r\n" + esc(0, 32) + "We'll buy them for " + esc(1, 33) + "1,872" + esc(0, 32) + " credits.\r\n"
        + esc(0, 35) + "Your offer [" + esc(1, 33) + "1,872" + esc(0, 35) + "] ? " + esc(1, 37), rate=16)
    typed("2000", per=8)
    out("\r\n" + esc(1, 33) + "We'll buy them for 1,912 credits.\r\n"
        + esc(0, 35) + "Your offer [" + esc(1, 33) + "1,912" + esc(0, 35) + "] ? " + esc(1, 37), rate=16)
    typed("1912", per=8)
    out("\r\n\r\n" + esc(1, 32) + "You have " + esc(1, 36) + "3,832" + esc(1, 32) + " credits and "
        + esc(1, 36) + "30" + esc(1, 32) + " empty cargo holds.\r\n"
        + esc(0, 32) + "You receive " + esc(1, 33) + "12" + esc(0, 32) + " experience point(s).\r\n" + prompt(8), rate=16)
    S.check("a profitable trade")
    S.sync(30)
    typed("Q", per=8)
    out("\r\n" + esc(1, 31) + "Are you sure you want to quit? " + esc(0, 37) + "(Y/N) " + esc(1, 37), rate=16)
    typed("Y", per=8)
    out("\r\n\r\n" + esc(0, 36) + "  Your ship is safely parked in sector 8.  See you tomorrow, Trader.\r\n", rate=16)
    S.sync(25)
    S.ctrl(0xC1)                                    # back to the board's 80 x 30
    S.op("TINIT", bytes([30]))
    out(esc(1, 35) + "  Doors " + esc(1, 30) + "\xfe " + esc(0, 37) + "Which door? " + esc(1, 37), rate=16)
    S.sync(20)
    typed("G", per=15)
    out("\r\n\r\n" + esc(1, 33) + "  Thanks for calling The 6309 BBS!\r\n\r\n" + RST, rate=16)
    S.sync(20)
    out("NO CARRIER\r\n", rate=4)
    S.check("NO CARRIER")
    S.sync(35)


if __name__ == "__main__":
    main()
