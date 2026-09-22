#!/usr/bin/env python3
"""mktbox.py OUT.bin - the ROM toolbox's data: ROM pages 65 on.

The toolbox (nitros9 level2/arm6309/modules/tbox.asm) is code on ROM page 64
that CoArm runs in place, the way a Macintosh ran QuickDraw out of ROM.  This
writes what it draws WITH, as the pages after it:

  page 65 +$000   the directory: "TD", fonts, icons, images (tbox.asm says how)
          +$100   the Haiku palette, 256 RGB565 words
  then            Noto Sans 12 px, regular and bold, two bits a pixel
                  the icons, show.Icon blobs - software/demo's, re-quantised
                  the pictures, W H and then W x H palette indices

It is also the one place the palette's layout is written down: v3show.py
imports PAL / RAMP / ICON / IMAGE from here, and check_asm() holds tbox.asm's
own equates to the same numbers, so neither can drift from the other.
"""
import os, re, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DEMO = os.path.join(ROOT, "software", "demo", "tools")
PAGE = 8192
FONT_DIR = "/usr/share/fonts/truetype/noto"

# ------------------------------------------------------------------ palette
# 0-15: Haiku's desktop colours (software/demo/tools/show.py GUI16) and KEY.
UI = [
    ("black", (0, 0, 0)), ("white", (255, 255, 255)), ("panel", (216, 216, 216)),
    ("frame", (152, 152, 152)), ("shadow", (112, 112, 112)), ("light", (240, 240, 240)),
    ("desk", (51, 102, 152)), ("tab", (255, 203, 0)), ("itab", (232, 232, 232)),
    ("sel", (40, 92, 170)), ("lsel", (190, 208, 230)), ("red", (204, 51, 51)),
    ("green", (51, 170, 68)), ("orange", (255, 153, 0)), ("pale", (255, 230, 128)),
    ("key", (255, 0, 255)),              # 15: never drawn - a transparent pixel
]
PAL = {n: i for i, (n, _) in enumerate(UI)}
TABG, GREYG = 16, 24                     # 8-step gradients: the tab, and bars
# ⭐ THE ACTIVE TAB IS FLAT BEHIND ITS TITLE, and this is which step it is.
# The tab is 18 rows and an opaque text box is the font's 17, so there is
# exactly ONE spare row - the pale highlight at the top. The other 17 are one
# colour, so `tab` has a flat paper, so RPaper stops being 255 and F.Opaq works
# on the most-drawn text in the GUI. docs/proportional-font.md §4.4.
TAB_FLAT = TABG + 4                      # the step the flat band uses
# 32-55: text ramps, three entries each - the two anti-aliased levels and the
# ink - for one ink on one paper.  A glyph pixel of level L is RAMP + L - 1.
RAMPS = [
    ("panel", (0, 0, 0), (216, 216, 216)),
    ("white", (0, 0, 0), (255, 255, 255)),
    # ⚠ THE PAPER IS THE EXACT RGB OF PALETTE ENTRY TAB_FLAT, not an eyeballed
    # midpoint. It used to be (255, 214, 60) - close to the gradient's middle
    # and equal to no palette entry at all, which is why ramp_papers() answered
    # 255 and opaque text was refused here.
    ("tab", (0, 0, 0), None),            # filled in below, once TABG exists
    ("desk", (255, 255, 255), (51, 102, 152)),
    ("sel", (255, 255, 255), (40, 92, 170)),
    ("menu", (0, 0, 0), (232, 232, 232)),
    ("dim", (96, 96, 96), (216, 216, 216)),
    ("lsel", (0, 0, 0), (190, 208, 230)),
]
RAMP = {n: 32 + 3 * i for i, (n, _, _) in enumerate(RAMPS)}
CUBE0 = 56                               # 56-255: 5 x 8 x 5, for icons and pictures
R_LEV = [0, 64, 128, 191, 255]
G_LEV = [0, 36, 73, 109, 146, 182, 219, 255]
B_LEV = [0, 64, 128, 191, 255]
FONT = {"regular": 0, "bold": 1}


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _tabg(i):
    """Palette entry TABG + i, the tab gradient's own colours."""
    return lerp((255, 238, 150), (255, 190, 0), i / 7)


# ⭐ Resolve the `tab` ramp's paper to the colour that is actually DRAWN behind
# the title, so the ramp is baked against the band rather than near it.
RAMPS = [(n, ink, (_tabg(TAB_FLAT - TABG) if paper is None else paper))
         for n, ink, paper in RAMPS]
RAMP = {n: 32 + 3 * i for i, (n, _, _) in enumerate(RAMPS)}

def palette_rgb():
    pal = [c for _, c in UI]
    pal += [_tabg(i) for i in range(8)]                                        # the tab
    pal += [lerp((250, 250, 250), (200, 200, 200), i / 7) for i in range(8)]   # bars
    for _, ink, paper in RAMPS:
        pal += [lerp(paper, ink, 1 / 3), lerp(paper, ink, 2 / 3), ink]
    for r in R_LEV:
        for g in G_LEV:
            for b in B_LEV:
                pal.append((r, g, b))
    assert len(pal) == 256, len(pal)
    return pal


def rgb565(c):
    r, g, b = c
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


RGB = np.array(palette_rgb(), dtype=np.int32)


def nearest(rgb, lo=0):
    """The closest entry, never KEY (15) and never a ramp or gradient."""
    cand = [i for i in range(256) if i != PAL["key"] and not (16 <= i < CUBE0)]
    d = ((RGB[cand] - np.array(rgb)) ** 2).sum(1)
    return cand[int(np.argmin(d))]


_NEAR = {}


def cidx(rgb):
    if rgb not in _NEAR:
        _NEAR[rgb] = nearest(rgb)
    return _NEAR[rgb]


def ramp_papers():
    """⭐ For each ramp, the palette index its PAPER is, or 255 where the
    paper is not a palette entry at all.  tbox.asm's opaque text fills a row
    with this instead of KEY, so a row becomes one run; a ramp with no flat
    paper must keep the transparent path, and 255 is how it says so."""
    # ⭐ THE SEARCH IS THE FLAT REGION, 0-31: the UI colours AND the two 8-step
    # gradients. It used to be UI alone, which is why `tab` answered 255 - its
    # paper is a gradient step, and a gradient step is a perfectly good flat
    # paper once the band behind the text really is flat, which since
    # 2026-09-21 it is (TAB_FLAT).
    # ⚠ NOT the whole palette: 56-255 is a 5x8x5 cube and a paper could collide
    # with a cube entry by accident, answering an index nobody meant.
    flat = palette_rgb()[:32]
    byrgb = {}
    for i, rgb in enumerate(flat):
        byrgb.setdefault(tuple(rgb), i)
    return [byrgb.get(tuple(paper), 255) for _, _, paper in RAMPS]


def check_asm():
    """tbox.asm's equates must say what this file says."""
    nd = os.environ.get("NITROS9DIR") or os.path.join(ROOT, "..", "nitros9")
    src = open(os.path.join(nd, "level2", "arm6309", "modules", "tbox.asm")).read()
    want = {"C.Black": PAL["black"], "C.White": PAL["white"], "C.Panel": PAL["panel"],
            "C.Frame": PAL["frame"], "C.Shadow": PAL["shadow"], "C.Light": PAL["light"],
            "C.Tab": PAL["tab"], "C.ITab": PAL["itab"], "C.Pale": PAL["pale"],
            "C.TabF": TAB_FLAT,
            "KEY": PAL["key"], "C.TabG": TABG, "R.Tab": RAMP["tab"], "R.Menu": RAMP["menu"],
            "F.Bold": FONT["bold"]}
    for name, v in want.items():
        m = re.search(r"^%s\s+equ\s+(\d+)" % re.escape(name), src, re.M)
        if not m or int(m.group(1)) != v:
            sys.exit("FAIL  tbox.asm %s is %s, mktbox.py says %d" % (name, m and m.group(1), v))
    # ⚠ and the paper table, which is data rather than an equate
    m = re.search(r"^RPaper\s+fcb\s+([0-9,]+)", src, re.M)
    got = [int(x) for x in m.group(1).split(",")] if m else None
    if got != ramp_papers():
        sys.exit("FAIL  tbox.asm RPaper is %s, mktbox.py says %s"
                 % (got, ramp_papers()))


# -------------------------------------------------------------------- fonts
# ⭐ THE STRIKE'S BAND WIDTH, and it is 256 because that is a power of two.
# A glyph's place in the strike is stored as ONE 16-bit word whose HIGH byte is
# the band and whose LOW byte is the column in it, so the ROM unpacks it with
# `lda`/`ldb` and no arithmetic at all. 384 - the margin's real width - would
# have needed a divide per glyph. The 128 columns a band gives up are free:
# the margin is 512 rows deep and a face needs three bands.
STRIKE_BAND = 256
# ⛔ SK.Max IN tbox.asm, AND THE TWO MUST AGREE.  The strike holds three
# (font, ramp) slots stacked down the margin at 51 rows each, so a face that
# needed a fourth band would lay its glyphs into the next slot's rows.  The
# ROM refuses such a face at run time and composes instead; this refuses it at
# build time, which is the half that can name the font.  checkfiles.py greps
# the equate so the two numbers cannot drift apart silently.
STRIKE_MAXBAND = 3


def strike_layout(widths):
    """Where each glyph sits in the strike: band<<8 | column, packed greedily.

    ⚠ A glyph never straddles a band, so the last few columns of one go unused
    - at most max(width) - 1 of 256. The ROM does not need to know that; it
    reads the word and believes it, which is the point of baking it here."""
    pos, band, x = [], 0, 0
    for w in widths:
        if x + w > STRIKE_BAND:
            band, x = band + 1, 0
        assert x <= 255, x
        pos.append((band << 8) | x)
        x += w
    return pos, band + 1


def font_blob(path, size=12):
    """95 glyphs, 32-126, anti-aliased to four levels, clipped to the advance.

    ⭐ FIVE BYTES A GLYPH SINCE 2026-09-21: width, the 2-byte offset of its
    rows, and the 2-byte STRIKE POSITION - where the glyph sits in the
    pre-rendered strike the copy engine blits from
    (docs/proportional-font.md §4). It is baked here rather than derived in the
    ROM because it is a pure function of the widths, and the toolbox's RAM is
    CoArm's 1 KB display-list scratch with 238 bytes free - a 95-entry table
    would have taken 190 of them, for one face.
    """
    f = ImageFont.truetype(path, size)
    asc, desc = f.getmetrics()
    h = asc + desc
    widths, rows = [], []
    for code in range(32, 127):
        ch = chr(code)
        w = max(1, int(round(f.getlength(ch))))
        im = Image.new("L", (w, h), 0)
        ImageDraw.Draw(im).text((0, 0), ch, font=f, fill=255)
        lv = np.clip(np.round(np.array(im) / 85.0), 0, 3).astype(np.uint8)
        bpr = (w + 3) // 4
        data = bytearray()
        for y in range(h):
            row = np.zeros(bpr * 4, np.uint8)
            row[:w] = lv[y]
            for k in range(bpr):
                q = row[4 * k:4 * k + 4]
                data.append((q[0] << 6) | (q[1] << 4) | (q[2] << 2) | q[3])
        widths.append(w)
        rows.append(bytes(data))
    pos, nband = strike_layout(widths)
    assert nband <= STRIKE_MAXBAND, (
        "%s needs %d strike bands and a slot holds %d (tbox.asm SK.Max): "
        "either narrow the face or add a slot - there are %d margin rows "
        "below 480 and a slot costs 51" % (path, nband, STRIKE_MAXBAND, 160))
    head = bytearray([h, asc, 32, 95])
    off = 4 + 5 * 95
    table = bytearray()
    body = bytearray()
    for w, d, pw in zip(widths, rows, pos):
        assert w < 256
        table += (bytes([w]) + (off + len(body)).to_bytes(2, "big")
                  + pw.to_bytes(2, "big"))
        body += d
    blob = bytes(head + table + body)
    assert len(blob) <= PAGE, len(blob)
    f.strike_bands = nband
    return blob, f


# -------------------------------------------------------------------- icons
def art_from_rgba(img, outline=True):
    """software/demo/tools/mkshow.py's, against this palette."""
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
            r, g, b = RGB[c]
            m[c] = cidx((int(r * 0.55), int(g * 0.55), min(255, int(b * 0.55) + 50)))
    return m


def icon_app16():
    """a small application: a window with a title bar and a prompt"""
    im = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([1, 2, 14, 13], fill=(236, 236, 236))
    d.rectangle([1, 2, 14, 4], fill=(255, 203, 0))
    d.rectangle([3, 6, 12, 11], fill=(20, 24, 40))
    d.line([(4, 8), (5, 8)], fill=(80, 255, 80))
    return im


def icon_term():
    im = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([2, 5, 29, 26], fill=(210, 210, 214))
    d.rectangle([4, 7, 27, 24], fill=(16, 18, 30))
    d.line([(7, 11), (10, 14), (7, 17)], fill=(120, 255, 120), width=1)
    d.line([(12, 18), (18, 18)], fill=(220, 220, 220))
    return im


ICON_NAMES = ["home", "disk", "files", "trash", "paint", "bbs", "game", "image", "doc",
              "folder16", "image16", "doc16", "leaf", "app16", "term", "folder"]


def build_icons():
    sys.path.insert(0, DEMO)
    saved = sys.argv
    sys.argv = [saved[0], "/nonexistent"]
    try:
        import show
        import mkshow as M
    finally:
        sys.argv = saved
    art = {
        "home": M.icon_home(), "disk": M.icon_disk(), "files": M.icon_files(),
        "trash": M.icon_trash(), "paint": M.icon_paint(), "bbs": M.icon_bbs(),
        "game": M.icon_game(), "image": M.icon_image(), "doc": M.icon_doc(),
        "folder16": M.icon_folder(16), "image16": M.icon_image(16), "doc16": M.icon_doc(16),
        "leaf": M.icon_leaf(), "app16": icon_app16(), "term": icon_term(), "folder": M.icon_folder(),
    }
    icons = []
    for n in ICON_NAMES:
        a = art_from_rgba(art[n], outline=(n != "leaf"))
        icons.append(show.Icon(n, a, sel_map(a)))
    for t in M.TOOL_ORDER:
        a = np.array([[PAL["black"] if ch == "X" else -1 for ch in r] for r in M.TOOLS[t]], np.int32)
        icons.append(show.Icon("tool_" + t, a, {PAL["black"]: PAL["white"]}))
    names = ICON_NAMES + ["tool_" + t for t in M.TOOL_ORDER]
    assert len(icons) <= 64
    return names, [ic.blob() for ic in icons]


ICON = {}      # filled by build(): name -> number


# ----------------------------------------------------------------- pictures
# ⭐ TWO, AND THE MARGIN HOLDS ONE AT A TIME.  video3's off-screen store is
# exactly the scroll margin - columns 640-1023 of every row, 384 x 480 - so a
# picture the copy engine can reach has to fit in it (plan.md 4).
#
#   0 "page"    384 x 480, the paint document.  ⚠ Its top-left CANVAS_W x
#               CANVAS_H is never seen: v3scrl copies the canvas over it
#               before it scrolls, so the page the viewer watched being drawn
#               IS the document's first page.  What this picture is for is
#               the columns and rows beyond that - the art the scroll reveals.
#   1 "parrot"  the photograph, sized to sit inside the canvas with a border,
#               so `v3grab` can drag it in a circle without running off the
#               page.  It replaces the page in the margin when it is opened.
DOC_W, DOC_H = 384, 480      # the paint document: exactly the scroll margin
CANVAS = (320, 320)          # ⚠ v3show.py CANVAS and v3scrl.asm VW, VH
PARROT = (264, 240)          # ⚠ v3show.py PARROT and v3grab.asm PW, PH


# The photograph software/demo's desktop show was made from (git 790de82:
# build/parrots-image.jpg, kept untracked); without it, mkparrots.py's
# stand-in illustration.
PHOTO = os.path.join(ROOT, "software", "demo", "build", "parrots-image.jpg")
DOC_X0 = 255                        # the crop's left edge, in the 853-wide scaled photo


def photo():
    if os.path.exists(PHOTO):
        return Image.open(PHOTO).convert("RGB")
    print("note  no %s: the illustration stands in" % PHOTO)
    sys.path.insert(0, DEMO)
    import mkparrots
    return mkparrots.illustration()


def quantise(img):
    """Floyd-Steinberg onto the 5 x 8 x 5 cube, as a W x H index array."""
    w, h = img.size
    a = np.array(img, dtype=np.float64)
    out = np.zeros((h, w), np.uint8)
    rl, gl, bl = (np.array(v, float) for v in (R_LEV, G_LEV, B_LEV))
    for y in range(h):
        for x in range(w):
            r, g, b = np.clip(a[y, x], 0, 255)
            ri, gi, bi = int(np.argmin(abs(rl - r))), int(np.argmin(abs(gl - g))), int(np.argmin(abs(bl - b)))
            out[y, x] = CUBE0 + ri * 40 + gi * 5 + bi
            err = np.array((r - rl[ri], g - gl[gi], b - bl[bi]))
            if x + 1 < w:
                a[y, x + 1] += err * 7 / 16
            if y + 1 < h:
                if x:
                    a[y + 1, x - 1] += err * 3 / 16
                a[y + 1, x] += err * 5 / 16
                if x + 1 < w:
                    a[y + 1, x + 1] += err * 1 / 16
    assert (out != PAL["key"]).all()
    return out


def build_parrot():
    """The photograph, PARROT pixels, cropped round the middle macaw."""
    pw, ph = PARROT
    img = photo()
    sc = ph / img.height
    img = img.resize((int(round(img.width * sc)), ph), Image.LANCZOS)
    l = min(int(DOC_X0 * ph / DOC_H) + 20, img.width - pw)
    return quantise(img.crop((max(l, 0), 0, max(l, 0) + pw, ph)))


# ------------------------------------------------- the page the scroll finds
# ⭐ DRAWN HERE, NOT PHOTOGRAPHED.  A painting the demo can own: a sky with
# a low sun, a range of hills, a lake with the range upside down in it, and a
# line of type along the bottom.  It is composed for the two reveals - the
# sun and the far peak sit in the columns past the canvas, and the lake is
# entirely below it - so that scrolling is what shows them.
PAGE_NOTE = "drawn off the page - the copy engine brings it in"


def _vgrad(d, box, top, bot):
    x0, y0, x1, y1 = box
    for y in range(y0, y1):
        d.line([(x0, y), (x1 - 1, y)], fill=lerp(top, bot, (y - y0) / max(1, y1 - y0 - 1)))


def oncube(c):
    """The nearest colour the 5 x 8 x 5 cube has EXACTLY.

    ⚠ A flat area painted off the cube dithers, and at this cube's coarse
    red and blue steps a dithered flat area reads as static, not as texture.
    Gradients may dither - that is what dithering is for - but every large
    flat fill in the page below is snapped here first.
    """
    return tuple(min(l, key=lambda v: abs(v - c[i]))
                 for i, l in enumerate((R_LEV, G_LEV, B_LEV)))


def build_page():
    """The paint document, DOC_W x DOC_H.

    ⛔ COMPOSED FOR THE L, not for the rectangle.  All the viewer ever sees
    of this picture is the columns past the canvas (320-383) and the rows
    below it (320-479) - an L - because v3scrl copies the drawn page over the
    corner.  So the sun sits in the right-hand strip, and the range, the
    water and the caption are all below row 320, where the vertical scroll
    brings them in whole.
    """
    w, h = DOC_W, DOC_H
    cw, ch = CANVAS
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    sky, haze, horizon = (73, 128, 191), (255, 219, 191), 400
    _vgrad(d, (0, 0, w, horizon), sky, haze)
    # the sun and its halo, in the strip the canvas does not reach
    sx, sy = cw + 34, 84
    for r in (76, 60, 46, 34):
        d.ellipse([sx - r, sy - r, sx + r, sy + r],
                  fill=lerp(lerp(sky, haze, sy / horizon), (255, 255, 182), 0.55 - r / 260))
    d.ellipse([sx - 25, sy - 25, sx + 25, sy + 25], fill=(255, 255, 182))
    # ⭐ the range, its feet on the horizon: rows ~240-400, so 80 rows of it
    # are below the canvas and come in with the vertical scroll
    for (lx, px, rx), py, base in (((296, cw + 56, 470), 246, (128, 146, 191)),
                                   ((-70, 96, 214), 286, (64, 109, 64)),
                                   ((136, 292, 448), 236, (64, 73, 64))):
        base, lit = oncube(base), oncube(lerp(base, (255, 255, 255), 0.30))
        d.polygon([(lx, horizon), (px, py), (rx, horizon)], fill=base)
        d.polygon([(px, py), (rx, horizon), ((px + rx) // 2, horizon)], fill=lit)
        k = (horizon - py) // 5
        d.polygon([(px, py), (px + k, py + k + 6), (px + k // 3, py + k - 4),
                   (px - k // 2, py + k + 8), (px - k, py + k)], fill=(255, 255, 255))
    # ⭐ THE WATER, all of it below the canvas: the range again, upside down
    # and blued, in bands of two rows so it reads as ripple rather than as a
    # mirror somebody forgot to turn off.
    ref = img.crop((0, horizon - (h - horizon), w, horizon)).transpose(Image.FLIP_TOP_BOTTOM)
    ref = Image.blend(ref, Image.new("RGB", ref.size, oncube((64, 109, 191))), 0.62)
    img.paste(ref, (0, horizon))
    px_ = img.load()
    for y in range(horizon, h):
        k = 1.12 if (y - horizon) % 4 < 2 else 0.92
        for x in range(w):
            px_[x, y] = tuple(min(255, int(v * k)) for v in px_[x, y])
    d.line([(0, horizon), (w - 1, horizon)], fill=(255, 255, 219))
    try:
        f = ImageFont.truetype(os.path.join(FONT_DIR, "NotoSans-Bold.ttf"), 14)
    except OSError:
        f = ImageFont.load_default()
    tw = int(d.textlength(PAGE_NOTE, font=f))
    d.rectangle([10, h - 31, 16 + tw, h - 9], fill=oncube((0, 36, 64)))
    d.text((13, h - 28), PAGE_NOTE, font=f, fill=(255, 255, 255))
    a = quantise(img)
    # ⚠ the canvas-sized corner is overwritten by v3scrl before anything
    # sees it; white is what the page the viewer draws on starts as, so the
    # -page.png that comes out of this file shows the document as it will be
    a[:ch, :cw] = PAL["white"]
    return a


IMAGE = {"page": 0, "parrot": 1}


# -------------------------------------------------------------------- build
class Pages:
    """A byte image of pages 65 on; `put` keeps a blob inside one page."""

    def __init__(self):
        self.b = bytearray(0x300)            # the directory and the palette

    def put(self, blob, whole=True):
        if whole:
            assert len(blob) <= PAGE
            if len(self.b) % PAGE + len(blob) > PAGE:
                self.b += bytes(PAGE - len(self.b) % PAGE)
        off = len(self.b)
        self.b += blob
        return 1 + off // PAGE, off % PAGE     # page relative to TB.Pg


def build(out):
    check_asm()
    P = Pages()
    d = P.b
    d[0:2] = b"TD"
    for i, c in enumerate(palette_rgb()):
        d[0x100 + 2 * i:0x102 + 2 * i] = rgb565(c).to_bytes(2, "big")
    fonts = [font_blob(os.path.join(FONT_DIR, "NotoSans-Regular.ttf"))[0],
             font_blob(os.path.join(FONT_DIR, "NotoSans-Bold.ttf"))[0]]
    d[2] = len(fonts)
    for i, fb in enumerate(fonts):
        pg, off = P.put(fb)
        P.b[3 + 3 * i] = pg
        P.b[4 + 3 * i:6 + 3 * i] = off.to_bytes(2, "big")
    names, blobs = build_icons()
    P.b[0x0F] = len(blobs)
    for i, bl in enumerate(blobs):
        pg, off = P.put(bl)
        P.b[0x10 + 3 * i] = pg
        P.b[0x11 + 3 * i:0x13 + 3 * i] = off.to_bytes(2, "big")
    ICON.clear()
    assert names == list(icon_names()), "TOOL_ORDER has moved in mkshow.py"
    pics = [("page", build_page()), ("parrot", build_parrot())]
    assert [n for n, _ in pics] == sorted(IMAGE, key=IMAGE.get), "IMAGE has moved"
    P.b[0xD0] = len(pics)
    for i, (_, a) in enumerate(pics):
        h, w = a.shape
        pg, off = P.put(w.to_bytes(2, "big") + h.to_bytes(2, "big"))
        P.b += a.tobytes()
        P.b[0xD1 + 3 * i] = pg
        P.b[0xD2 + 3 * i:0xD4 + 3 * i] = off.to_bytes(2, "big")
    assert len(P.b) <= 63 * PAGE, len(P.b)
    open(out, "wb").write(bytes(P.b))
    for n, a in pics:
        Image.fromarray(RGB[a].astype(np.uint8)).save("%s-%s.png" % (os.path.splitext(out)[0], n))
    print("ok    %s: %d bytes, %d pages; %d fonts, %d icons, %s"
          % (out, len(P.b), (len(P.b) + PAGE - 1) // PAGE, len(fonts), len(blobs),
             ", ".join("%s %dx%d" % (n, a.shape[1], a.shape[0]) for n, a in pics)))


def text_width(s, bold=False):
    """What tbox.asm's TextW answers, for layout."""
    _, f = font_blob(os.path.join(FONT_DIR, "NotoSans-Bold.ttf" if bold else "NotoSans-Regular.ttf"))
    return sum(max(1, int(round(f.getlength(c)))) for c in s)


TOOLS = ("marquee", "lasso", "grab", "text", "bucket", "spray", "brush", "pencil", "line",
         "eraser", "rect", "frect", "oval", "poly", "fpoly")      # mkshow.py TOOL_ORDER


def icon_names():
    """name -> icon number, without building anything"""
    if not ICON:
        ICON.update({n: i for i, n in enumerate(ICON_NAMES + ["tool_" + t for t in TOOLS])})
    return ICON


if __name__ == "__main__":
    build(sys.argv[1])
