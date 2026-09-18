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
# 32-55: text ramps, three entries each - the two anti-aliased levels and the
# ink - for one ink on one paper.  A glyph pixel of level L is RAMP + L - 1.
RAMPS = [
    ("panel", (0, 0, 0), (216, 216, 216)),
    ("white", (0, 0, 0), (255, 255, 255)),
    ("tab", (0, 0, 0), (255, 214, 60)),
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


def palette_rgb():
    pal = [c for _, c in UI]
    pal += [lerp((255, 238, 150), (255, 190, 0), i / 7) for i in range(8)]     # the tab
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
    paper (`tab`, which is a step of the tab's gradient) must keep the
    transparent path, and 255 is how it says so."""
    byrgb = {rgb: i for i, (_, rgb) in enumerate(UI)}
    return [byrgb.get(paper, 255) for _, _, paper in RAMPS]


def check_asm():
    """tbox.asm's equates must say what this file says."""
    nd = os.environ.get("NITROS9DIR") or os.path.join(ROOT, "..", "nitros9")
    src = open(os.path.join(nd, "level2", "arm6309", "modules", "tbox.asm")).read()
    want = {"C.Black": PAL["black"], "C.White": PAL["white"], "C.Panel": PAL["panel"],
            "C.Frame": PAL["frame"], "C.Shadow": PAL["shadow"], "C.Light": PAL["light"],
            "C.Tab": PAL["tab"], "C.ITab": PAL["itab"], "C.Pale": PAL["pale"],
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
def font_blob(path, size=12):
    """95 glyphs, 32-126, anti-aliased to four levels, clipped to the advance."""
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
    head = bytearray([h, asc, 32, 95])
    off = 4 + 3 * 95
    table = bytearray()
    body = bytearray()
    for w, d in zip(widths, rows):
        assert w < 256
        table += bytes([w]) + (off + len(body)).to_bytes(2, "big")
        body += d
    blob = bytes(head + table + body)
    assert len(blob) <= PAGE, len(blob)
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
DOC_W, DOC_H = 384, 480      # the paint document: exactly the scroll margin


# The paint document is the photograph software/demo's desktop show was made
# from (git 790de82: build/parrots-image.jpg, kept untracked), scaled to 480
# rows and cropped round the middle macaw.  Without it, mkparrots.py's
# stand-in illustration - and the doodle's anchor is then only approximate.
PHOTO = os.path.join(ROOT, "software", "demo", "build", "parrots-image.jpg")
PHOTO_HEAD = (0.54, 0.21)           # the middle macaw's eye, as a fraction of the photo
DOC_X0 = 255                        # the crop's left edge, in the 853-wide scaled photo
DOC_HEAD = (int(PHOTO_HEAD[0] * 1920 * DOC_H / 1080) - DOC_X0, int(PHOTO_HEAD[1] * DOC_H))


def build_doc():
    """The paint program's document, 384 x 480, Floyd-Steinberg onto the
    5 x 8 x 5 cube."""
    if os.path.exists(PHOTO):
        img = Image.open(PHOTO).convert("RGB")
    else:
        print("note  no %s: the illustration stands in" % PHOTO)
        sys.path.insert(0, DEMO)
        import mkparrots
        img = mkparrots.illustration()
    sc = DOC_H / img.height
    img = img.resize((int(round(img.width * sc)), DOC_H), Image.LANCZOS)
    l = min(DOC_X0, img.width - DOC_W)
    img = img.crop((l, 0, l + DOC_W, DOC_H))
    a = np.array(img, dtype=np.float64)
    out = np.zeros((DOC_H, DOC_W), np.uint8)
    rl, gl, bl = (np.array(v, float) for v in (R_LEV, G_LEV, B_LEV))
    for y in range(DOC_H):
        for x in range(DOC_W):
            r, g, b = np.clip(a[y, x], 0, 255)
            ri, gi, bi = int(np.argmin(abs(rl - r))), int(np.argmin(abs(gl - g))), int(np.argmin(abs(bl - b)))
            out[y, x] = CUBE0 + ri * 40 + gi * 5 + bi
            err = np.array((r - rl[ri], g - gl[gi], b - bl[bi]))
            if x + 1 < DOC_W:
                a[y, x + 1] += err * 7 / 16
            if y + 1 < DOC_H:
                if x:
                    a[y + 1, x - 1] += err * 3 / 16
                a[y + 1, x] += err * 5 / 16
                if x + 1 < DOC_W:
                    a[y + 1, x + 1] += err * 1 / 16
    assert (out != PAL["key"]).all()
    return out


IMAGE = {"doc": 0}


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
    doc = build_doc()
    P.b[0xD0] = 1
    head = DOC_W.to_bytes(2, "big") + DOC_H.to_bytes(2, "big")
    pg, off = P.put(head)
    P.b += doc.tobytes()
    P.b[0xD1] = pg
    P.b[0xD2:0xD4] = off.to_bytes(2, "big")
    assert len(P.b) <= 63 * PAGE, len(P.b)
    open(out, "wb").write(bytes(P.b))
    Image.fromarray(RGB[doc].astype(np.uint8)).save(os.path.splitext(out)[0] + "-doc.png")
    print("ok    %s: %d bytes, %d pages; %d fonts, %d icons, 1 picture %dx%d"
          % (out, len(P.b), (len(P.b) + PAGE - 1) // PAGE, len(fonts), len(blobs), DOC_W, DOC_H))


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
