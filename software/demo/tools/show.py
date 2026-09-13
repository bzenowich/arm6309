"""The show: the bytecode demo.asm's interpreter runs, its assets, and the model.

    import show

`mkshow.py` writes the script - a desktop, a paint program, a BBS, a raster
demo - as bytecode through `Script`. The 6809 interprets that bytecode
(`gui.asm`); `Model` interprets THE SAME BYTES in Python, drawing into a
1024 x 512 ring the way features.md says the card does, and keeps a picture of
the screen at every CHECK. The checker compares the machine's frames against
those pictures, so the model and the 6809 share the script and nothing else:
not a line of drawing code.

WHAT THE BYTECODE IS. One opcode byte, big-endian operands, coordinates in
ring pixels. Every drawing operation is one of the primitives features.md 7
says the card offloads - a solid span, a pattern row, a glyph, a 1bpp mask -
or an 8bpp copy (IMAGE), which it says the CPU does. OPS below is the whole
format; gui.asm's dispatch table is in the same order.
"""
import gzip, os, struct
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------------ opcodes
OPS = [
    "END",      # 00                          stop: the interpreter idles for ever
    "SYNC",     # 01 n                        wait n vertical blanks (GO the frame's list at each)
    "CHECK",    # 02 id16                     the screen is now model picture `id`
    "CTRL",     # 03 v                        CTRL := v (WMODE bits are the primitives')
    "PAL",      # 04 first count(0=256) (hi lo)*count
    "FILL",     # 05 x y w h c                span-solid
    "PAT",      # 06 x y w h fg bg p          span-mask, x and w multiples of 8
    "TEXT",     # 07 x y fg bg n chars        8x16 glyphs; bg $FF = sprite mode
    "ICON",     # 08 x y n v                  a layered 1bpp icon, sprite mode
    "POLY",     # 09 c nl nr (x y)*nl (x y)*nr    left and right chains, top to bottom
    "POLYP",    # 0A fg bg p nl nr (x y)*nl (x y)*nr
    "IMAGE",    # 0B x y w h                  8bpp from the image asset, VDATA
    "CURS",     # 0C x y                      move the pointer
    "HIDE",     # 0D
    "SHOW",     # 0E
    "CALL",     # 0F off24
    "RET",      # 10
    "ORG",      # 11 dx dy                    added to every drawing x, y
    "LISTHS",   # 12 y0 y1 v                  HSCROLL = v on lines y0..y1-1, by display list
    "LISTOFF",  # 13
    "RASTER",   # 14 ph                       rewrite the raster list for phase ph
    "RASTDEF",  # 15 y0 n idx base16 grad(3*8*2) sin(256)
    "PATDEF",   # 16 p b*8
    "TERM",     # 17 n16 bytes                to the terminal, RATE bytes a frame
    "RATE",     # 18 n
    "TINIT",    # 19 rows                     terminal of 80 x rows: clear, home, 7 on 0
    "GAME",     # 1A                          the overworld, for ever
    "MUSIC",    # 1B                          load the module and start it
    "TEXT8",    # 1C x y fg bg n chars        8x8 glyphs
    "STOP",     # 1D                          stop the module
    "WAVEDF",   # 1E y0 n tab(256)            a per-line HSCROLL warp of 2n lines from y0
    "WAVE",     # 1F ph amp                   rewrite the warp's list for phase ph, amplitude amp
]
OP = {n: i for i, n in enumerate(OPS)}

# the pointer's colours: GUI palette entries (black, white)
CUR_BLACK, CUR_WHITE = 0, 1
CURW, CURH = 16, 16

W16 = lambda v: struct.pack(">H", v & 0xFFFF)
S16 = lambda v: struct.pack(">h", v)


# ------------------------------------------------------------------- colour
def rgb565(r, g, b):
    return (round(r * 31 / 255) << 11) | (round(g * 63 / 255) << 5) | round(b * 31 / 255)


def rgb888(c):
    r5, g6, b5 = c >> 11, (c >> 5) & 63, c & 31
    return ((r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2))


# The desktop's sixteen, Haiku's colours where it has them.
GUI16 = [
    (0, 0, 0),          # 0  black
    (255, 255, 255),    # 1  white
    (216, 216, 216),    # 2  panel
    (152, 152, 152),    # 3  frame
    (112, 112, 112),    # 4  shadow
    (240, 240, 240),    # 5  bevel light
    (51, 102, 152),     # 6  desktop
    (255, 203, 0),      # 7  active tab
    (232, 232, 232),    # 8  inactive tab
    (40, 92, 170),      # 9  selection
    (190, 208, 230),    # 10 light selection
    (204, 51, 51),      # 11 red
    (51, 170, 68),      # 12 green
    (255, 153, 0),      # 13 orange
    (255, 230, 128),    # 14 pale yellow
    (51, 102, 152),     # 15 the raster demo's copper - the desktop until a list repaints it
]
C = dict(black=0, white=1, panel=2, frame=3, shadow=4, light=5, desk=6, tab=7, itab=8,
         sel=9, lsel=10, red=11, green=12, orange=13, pale=14, copper=15)
R_LEV = [0, 51, 102, 153, 204, 255]
G_LEV = [0, 36, 73, 109, 146, 182, 219, 255]
B_LEV = [0, 64, 128, 191, 255]


def gui_palette():
    """16 desktop colours, then a 6 x 8 x 5 cube for pictures and icons."""
    pal = [rgb565(*c) for c in GUI16]
    for r in range(6):
        for g in range(8):
            for b in range(5):
                pal.append(rgb565(R_LEV[r], G_LEV[g], B_LEV[b]))
    return np.array(pal, dtype=np.uint16)


def gui_rgb():
    return np.array([rgb888(int(c)) for c in gui_palette()], dtype=np.int32)


ANSI16 = [(0, 0, 0), (170, 0, 0), (0, 170, 0), (170, 85, 0), (0, 0, 170), (170, 0, 170), (0, 170, 170),
          (170, 170, 170), (85, 85, 85), (255, 85, 85), (85, 255, 85), (255, 255, 85), (85, 85, 255),
          (255, 85, 255), (85, 255, 255), (255, 255, 255)]


def ansi_palette():
    """SGR order: 30-37 are 0-7, bold adds 8. The rest is the desktop's cube."""
    pal = gui_palette().copy()
    for i, c in enumerate(ANSI16):
        pal[i] = rgb565(*c)
    return pal


def rgb332_palette():
    """demo.asm's game palette, entry i = RGB332(i) - frames.palette565()."""
    r5 = [0, 4, 9, 13, 18, 22, 27, 31]
    g6 = [0, 9, 18, 27, 36, 45, 54, 63]
    b5 = [0, 10, 21, 31]
    return np.array([(r5[i >> 5] << 11) | (g6[(i >> 2) & 7] << 5) | b5[i & 3] for i in range(256)], dtype=np.uint16)


def nearest(rgb, pal_rgb, lo=0):
    d = ((pal_rgb[lo:] - np.array(rgb)) ** 2).sum(1)
    return int(np.argmin(d)) + lo


# --------------------------------------------------------------------- fonts
def _psf(name):
    path = f"/usr/share/consolefonts/{name}.psf.gz"
    if not os.path.exists(path):
        raise SystemExit(f"FAIL  {path} is missing - the show's fonts come from console-setup's VGA fonts")
    d = gzip.open(path).read()
    assert d[:2] == b"\x36\x04", name
    mode, h = d[2], d[3]
    n = 512 if mode & 1 else 256
    glyphs = np.frombuffer(d[4:4 + n * h], dtype=np.uint8).reshape(n, h)
    tab = d[4 + n * h:]
    umap, i, g = {}, 0, 0
    while g < n and i + 1 < len(tab):
        v = struct.unpack_from("<H", tab, i)[0]
        i += 2
        if v == 0xFFFF:
            g += 1
        elif v != 0xFFFE:
            umap.setdefault(v, g)
    return glyphs, umap, h


# CP437 0x01-0x1F as the IBM PC draws them
CP437_LOW = "☺☻♥♦♣♠•◘○◙♂♀♪♫☼" \
            "►◄↕‼¶§▬↨↑↓→←∟↔▲▼"


def font(h):
    """256 glyphs of CP437, h = 16 or 8, as (256, h) row bytes, MSB leftmost.
    The shade and half-block cells are drawn here rather than taken from the
    console font, which lacks some of them and ANSI art is made of them."""
    glyphs, umap, fh = _psf("Uni2-VGA16" if h == 16 else "Uni2-VGA8")
    assert fh == h
    out = np.zeros((256, h), dtype=np.uint8)
    chars = " " + CP437_LOW + bytes(range(32, 256)).decode("cp437")
    for code, ch in enumerate(chars):
        g = umap.get(ord(ch))
        if g is not None:
            out[code] = glyphs[g]
    half = h // 2
    rows = np.arange(h)
    out[0xDB] = 0xFF
    out[0xDC] = np.where(rows >= half, 0xFF, 0)
    out[0xDF] = np.where(rows < half, 0xFF, 0)
    out[0xDD] = 0xF0
    out[0xDE] = 0x0F
    out[0xB0] = np.where(rows % 2 == 0, 0x88, 0x22)
    out[0xB1] = np.where(rows % 2 == 0, 0xAA, 0x55)
    out[0xB2] = np.where(rows % 2 == 0, 0x77, 0xDD)
    return out


# --------------------------------------------------------------------- icons
class Icon:
    """A picture as 1bpp layers, one per colour, drawn in sprite mode.

    `art` is an (h, w) array of palette indices, -1 transparent, w and h
    multiples of 8. `sel` maps a normal colour to the one the selected variant
    draws - Haiku darkens a selected icon."""

    def __init__(self, name, art, sel=None):
        self.name, self.art = name, np.asarray(art, dtype=np.int32)
        self.h, self.w = self.art.shape
        assert self.w % 8 == 0 and self.h <= 255
        self.sel = sel or {}

    def layers(self):
        cols = [c for c in sorted(set(self.art.flatten().tolist())) if c >= 0]
        return [(c, self.sel.get(c, c), self.art == c) for c in cols]

    def blob(self):
        ncol = self.w // 8
        ls = self.layers()
        out = bytearray([ncol, self.h, len(ls)])
        for c0, c1, mask in ls:
            present = 0
            data = bytearray()
            for k in range(ncol):
                col = mask[:, k * 8:k * 8 + 8]
                if col.any():
                    present |= 1 << k
                    for r in range(self.h):
                        b = 0
                        for i in range(8):
                            if col[r, i]:
                                b |= 0x80 >> i
                        data.append(b)
            out += bytes([c0, c1, present]) + data
        return bytes(out)


def cursor_masks():
    """The arrow: an outline and a fill, 16 x 16, hotspot at the top left."""
    art = [
        "X...............",
        "XX..............",
        "XWX.............",
        "XWWX............",
        "XWWWX...........",
        "XWWWWX..........",
        "XWWWWWX.........",
        "XWWWWWWX........",
        "XWWWWWWWX.......",
        "XWWWWWWWWX......",
        "XWWWWWXXXXX.....",
        "XWWXWWX.........",
        "XWX.XWWX........",
        "XX..XWWX........",
        "X....XWWX.......",
        ".....XXX........",
    ]
    ol = np.array([[ch == "X" for ch in row] for row in art])
    fl = np.array([[ch == "W" for ch in row] for row in art])
    return ol, fl


def mask_rows(m):
    """(16, 16) bool -> two columns of 16 bytes."""
    out = []
    for k in range(2):
        col = []
        for r in range(m.shape[0]):
            b = 0
            for i in range(8):
                if m[r, k * 8 + i]:
                    b |= 0x80 >> i
            col.append(b)
        out.append(col)
    return out


# -------------------------------------------------------------------- script
class Script:
    """Bytecode, with CALL targets resolved at the end."""

    def __init__(self):
        self.b = bytearray()
        self.labels = {}
        self.fix = []
        self.next_check = 1
        self.checks = []            # (id, comment)

    def op(self, name, *parts):
        self.b.append(OP[name])
        for p in parts:
            self.b += p
        return self

    def here(self):
        return len(self.b)

    def label(self, name):
        self.labels[name] = len(self.b)

    def call(self, name):
        self.b.append(OP["CALL"])
        self.fix.append((len(self.b), name))
        self.b += b"\0\0\0"

    def link(self):
        for at, name in self.fix:
            off = self.labels[name]
            self.b[at:at + 3] = bytes([(off >> 16) & 0xFF, (off >> 8) & 0xFF, off & 0xFF])
        return bytes(self.b)

    # -- the operations, with Python argument checking
    def sync(self, n=1):
        while n > 0:
            k = min(n, 255)
            self.op("SYNC", bytes([k]))
            n -= k

    def check(self, what, hold=3):
        """The screen is now a model picture, and stays it for `hold` frames at
        least - demo_tb judges a frame only when the checkpoint is the same at
        its first and last active dots, so one that is drawn over at once is
        never judged."""
        cid = self.next_check
        self.next_check += 1
        self.checks.append((cid, what))
        self.op("CHECK", W16(cid))
        self.sync(hold)
        return cid

    def ctrl(self, v):
        self.op("CTRL", bytes([v]))

    def pal(self, values, first=0):
        """Entries first, first + 1, ... := values."""
        data = b"".join(W16(int(v)) for v in values)
        self.op("PAL", bytes([first, len(values) & 0xFF]), data)

    def fill(self, x, y, w, h, c):
        if w <= 0 or h <= 0:
            return
        assert 0 <= x and x + w <= 1024 and 0 <= y and y + h <= 512, (x, y, w, h)
        self.op("FILL", W16(x), W16(y), W16(w), W16(h), bytes([c]))

    def pat(self, x, y, w, h, fg, bg, p):
        assert x % 8 == 0 and w % 8 == 0 and w > 0 and h > 0
        self.op("PAT", W16(x), W16(y), W16(w), W16(h), bytes([fg, bg, p]))

    def text(self, x, y, fg, bg, s, big=True):
        data = s.encode("cp437") if isinstance(s, str) else bytes(s)
        for i in range(0, len(data), 255):
            chunk = data[i:i + 255]
            self.op("TEXT" if big else "TEXT8", W16(x + 8 * i), W16(y), bytes([fg, bg, len(chunk)]), chunk)

    def icon(self, x, y, n, v=0):
        self.op("ICON", W16(x), W16(y), bytes([n, v]))

    def poly(self, c, left, right, pattern=None):
        assert left[0] == right[0] and left[-1][1] == right[-1][1]
        for ch in (left, right):
            assert all(b[1] >= a[1] for a, b in zip(ch, ch[1:])), f"a chain must run downwards: {ch}"
        body = bytes([len(left), len(right)]) + b"".join(W16(x) + W16(y) for x, y in left + right)
        if pattern is None:
            self.op("POLY", bytes([c]), body)
        else:
            fg, bg, p = pattern
            self.op("POLYP", bytes([fg, bg, p]), body)

    def image(self, x, y, w, h):
        self.op("IMAGE", W16(x), W16(y), W16(w), W16(h))

    def curs(self, x, y):
        self.op("CURS", W16(x), W16(y))

    def hide(self):
        self.op("HIDE")

    def show(self):
        self.op("SHOW")

    def ret(self):
        self.op("RET")

    def org(self, dx, dy):
        self.op("ORG", S16(dx), S16(dy))

    def lisths(self, y0, y1, v):
        self.op("LISTHS", W16(y0), W16(y1), W16(v))

    def listoff(self):
        self.op("LISTOFF")

    def raster(self, ph):
        self.op("RASTER", bytes([ph & 0xFF]))

    def rastdef(self, y0, n, idx, base, grads, sint):
        assert len(grads) == 3 and all(len(g) == 8 for g in grads) and len(sint) == 256
        self.op("RASTDEF", W16(y0), bytes([n, idx]), W16(base),
                b"".join(W16(int(c)) for g in grads for c in g), bytes(sint))

    def patdef(self, p, rows):
        self.op("PATDEF", bytes([p]), bytes(rows))

    def term(self, data):
        data = data.encode("latin-1") if isinstance(data, str) else bytes(data)   # \xNN is the CP437 byte
        for i in range(0, len(data), 60000):
            chunk = data[i:i + 60000]
            self.op("TERM", W16(len(chunk)), chunk)

    def wavedf(self, y0, n, tab):
        assert len(tab) == 256 and y0 > 0 and y0 + 4 * n + 3 <= 1024 and n <= 150
        self.op("WAVEDF", W16(y0), W16(n), bytes(tab))

    def wave(self, ph, amp):
        assert 0 <= amp <= 255
        self.op("WAVE", bytes([ph & 255, amp]))

    def rate(self, n):
        self.op("RATE", bytes([n]))


# --------------------------------------------------------------------- model
class Model:
    """Runs a script the way features.md says the card and gui.asm do it.

    `pictures[id]` is what the screen shows at CHECK id: the displayed indices
    (h x 640, after scroll), the palette, and - while a raster list is running
    - its definition, so the checker can render any phase."""

    # where a display-list effect lands, measured by bench/calib.asm: an effect
    # after n WAITs from a GO issued inside line 0 shows on line n + LIST_DY
    LIST_DY = 0

    def __init__(self, script, gfx, icons, image, list_dy=None):
        self.s, self.gfx, self.icons, self.image = script, gfx, icons, image
        if list_dy is not None:
            self.LIST_DY = list_dy
        self.vram = np.zeros((512, 1024), dtype=np.uint8)
        self.pal = np.zeros(256, dtype=np.uint16)
        self.ctrl = 0
        self.vs = 0
        self.hs = 0
        self.list = None
        self.rast = None
        self.wave = None
        self.cvis, self.cx, self.cy = False, 0, 0
        self.saved = None
        self.ox = self.oy = 0
        self.pats = np.zeros((32, 8), dtype=np.uint8)
        self.pictures = {}
        self.ol, self.fl = cursor_masks()
        self.f16 = np.frombuffer(gfx[0:4096], dtype=np.uint8).reshape(256, 16)
        self.f8 = np.frombuffer(gfx[4096:6144], dtype=np.uint8).reshape(256, 8)
        self.term = None
        self.stack = []
        self.game = False

    # ---- pixels
    def put(self, y, x, v):
        self.vram[y % 512, x % 1024] = v

    def rect(self, x, y, w, h, c):
        ys = np.arange(y, y + h) % 512
        xs = np.arange(x, x + w) % 1024
        self.vram[np.ix_(ys, xs)] = c

    def bits(self, x, y, rows, fg, bg=None):
        """rows: bytes, one 8-pixel row each, at column x from row y down."""
        for r, byte in enumerate(rows):
            for i in range(8):
                if byte & (0x80 >> i):
                    self.put(y + r, x + i, fg)
                elif bg is not None:
                    self.put(y + r, x + i, bg)

    # ---- the pointer
    def c_hide(self):
        if self.cvis:
            ys = np.arange(self.cy, self.cy + CURH) % 512
            xs = np.arange(self.cx, self.cx + CURW) % 1024
            self.vram[np.ix_(ys, xs)] = self.saved
            self.cvis = False

    def c_show(self):
        if not self.cvis:
            ys = np.arange(self.cy, self.cy + CURH) % 512
            xs = np.arange(self.cx, self.cx + CURW) % 1024
            self.saved = self.vram[np.ix_(ys, xs)].copy()
            for r in range(CURH):
                for c in range(CURW):
                    if self.ol[r, c]:
                        self.put(self.cy + r, self.cx + c, CUR_BLACK)
                    if self.fl[r, c]:
                        self.put(self.cy + r, self.cx + c, CUR_WHITE)
            self.cvis = True

    # ---- polygons: the rule gui.asm's polyfill implements
    @staticmethod
    def spans(left, right):
        """Yield (y, xl, xr) for a polygon given as left and right vertex chains
        from its top vertex to its bottom one. Each edge steps x in 16.8 fixed
        point from (x0 << 8) + 128 by sign(dx) * ((|dx| << 8) // dy) per line;
        a line covers [xl >> 8, xr >> 8)."""
        def chain(pts):
            out = {}
            for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
                if yb <= ya:
                    continue
                dx, dy = xb - xa, yb - ya
                step = ((abs(dx) << 8) // dy) * (1 if dx >= 0 else -1)
                x8 = (xa << 8) + 128
                for y in range(ya, yb):
                    out[y] = x8 >> 8
                    x8 += step
            return out
        L, R = chain(left), chain(right)
        for y in range(left[0][1], left[-1][1]):
            xl, xr = L[y], R[y]
            if xr > xl:
                yield y, xl, xr

    # ---- the terminal
    def t_init(self, rows):
        self.term = dict(row=0, col=0, fg=7, bg=0, bold=0, top=0, rows=rows)
        self.vs = 0
        self.rect(0, 0, 640, rows * 8, 0)

    def t_glyph(self, ch):
        t = self.term
        if t["col"] >= 80:
            t["col"] = 0
            self.t_lf()
        fg = t["fg"] + (8 if t["bold"] else 0)
        y = t["top"] + t["row"] * 8
        self.bits(t["col"] * 8, y, self.f8[ch], fg, t["bg"])
        t["col"] += 1

    def t_lf(self):
        t = self.term
        if t["row"] == t["rows"] - 1:
            t["top"] = (t["top"] + 8) % 512
            self.vs = t["top"]
            self.rect(0, t["top"] + (t["rows"] - 1) * 8, 640, 8, 0)
        else:
            t["row"] += 1

    def t_bytes(self, data):
        t = self.term
        i = 0
        while i < len(data):
            ch = data[i]
            i += 1
            if ch == 27 and i < len(data) and data[i] == ord("["):
                j = i + 1
                while not (64 <= data[j] <= 126):
                    j += 1
                params = data[i + 1:j].decode("ascii")
                final = chr(data[j])
                i = j + 1
                ps = [int(p) if p else 0 for p in params.split(";")] if params else []
                if final == "m":
                    for p in (ps or [0]):
                        if p == 0:
                            t.update(fg=7, bg=0, bold=0)
                        elif p == 1:
                            t["bold"] = 1
                        elif p == 22:
                            t["bold"] = 0
                        elif 30 <= p <= 37:
                            t["fg"] = p - 30
                        elif p == 39:
                            t["fg"] = 7
                        elif 40 <= p <= 47:
                            t["bg"] = p - 40
                        elif p == 49:
                            t["bg"] = 0
                elif final == "J":
                    if (ps[0] if ps else 0) == 2:
                        self.rect(0, t["top"], 640, t["rows"] * 8, 0)
                        t["row"] = t["col"] = 0
                elif final in "Hf":
                    r = (ps[0] if len(ps) > 0 and ps[0] else 1) - 1
                    c = (ps[1] if len(ps) > 1 and ps[1] else 1) - 1
                    t["row"], t["col"] = min(r, t["rows"] - 1), min(c, 79)
                elif final == "K":
                    if t["col"] < 80:
                        self.rect(t["col"] * 8, t["top"] + t["row"] * 8, (80 - t["col"]) * 8, 8, t["bg"])
                elif final == "C":
                    t["col"] = min(79, t["col"] + max(1, ps[0] if ps else 1))
                elif final == "D":
                    t["col"] = max(0, t["col"] - max(1, ps[0] if ps else 1))
                elif final == "A":
                    t["row"] = max(0, t["row"] - max(1, ps[0] if ps else 1))
                elif final == "B":
                    t["row"] = min(t["rows"] - 1, t["row"] + max(1, ps[0] if ps else 1))
                continue
            if ch == 13:
                t["col"] = 0
            elif ch == 10:
                t["lf_pending"] = 0
                self.t_lf()
            elif ch == 8:
                if t["col"] > 0:
                    t["col"] -= 1
            elif ch in (7, 0):
                pass
            else:
                self.t_glyph(ch)

    # ---- the display
    def render(self):
        """(indices h x 640, palette, raster or None, hs-list or None)."""
        vmode = self.ctrl & 3
        h = 480 if vmode == 3 else 400 if vmode == 2 else 240 if vmode == 1 else 200
        idx = np.zeros((h, 640), dtype=np.uint8)
        for y in range(h):
            s = self.hs
            if self.list is not None and self.list[0] <= y - self.LIST_DY < self.list[1]:
                s = self.list[2]
            idx[y] = self.vram[(self.vs + y) % 512, (s + np.arange(640)) % 1024]
        if vmode in (0, 1):
            idx = np.repeat(idx, 2, axis=0)
        return idx

    def picture(self, cid):
        ring = None
        if self.wave is not None:
            ring = self.vram[(self.vs + np.arange(512)) % 512].copy()[:480]
        self.pictures[cid] = dict(idx=self.render(), pal=self.pal.copy(), vmode=self.ctrl & 3, ring=ring,
                                  list=self.list is not None or self.rast is not None or self.wave is not None,
                                  wave=None if self.wave is None else dict(self.wave),
                                  rast=None if self.rast is None else dict(self.rast))

    # ---- the interpreter
    def run(self, stop_at_game=True):
        b = self.s
        pc = 0
        rd8 = lambda: b[pc]
        while True:
            op = OPS[b[pc]]
            pc += 1

            def u8():
                nonlocal pc
                v = b[pc]
                pc += 1
                return v

            def u16():
                nonlocal pc
                v = (b[pc] << 8) | b[pc + 1]
                pc += 2
                return v

            def s16():
                v = u16()
                return v - 65536 if v >= 32768 else v

            if op == "END":
                return
            elif op == "SYNC":
                u8()
            elif op == "CHECK":
                self.picture(u16())
            elif op == "CTRL":
                self.ctrl = u8()
                self.vs = self.hs = 0
            elif op == "PAL":
                first, count = u8(), u8() or 256
                for i in range(count):
                    self.pal[(first + i) & 255] = u16()
            elif op == "FILL":
                x, y, w, h, c = u16(), u16(), u16(), u16(), u8()
                self.rect(x + self.ox, y + self.oy, w, h, c)
            elif op == "PAT":
                x, y, w, h, fg, bg, p = u16(), u16(), u16(), u16(), u8(), u8(), u8()
                x, y = x + self.ox, y + self.oy
                for r in range(h):
                    row = self.pats[p][(y + r) & 7]
                    for k in range(w // 8):
                        self.bits(x + 8 * k, y + r, [row], fg, bg)
            elif op in ("TEXT", "TEXT8"):
                x, y, fg, bg, n = u16(), u16(), u8(), u8(), u8()
                chars = b[pc:pc + n]
                pc += n
                f = self.f16 if op == "TEXT" else self.f8
                for i, ch in enumerate(chars):
                    self.bits(x + self.ox + 8 * i, y + self.oy, f[ch], fg, None if bg == 0xFF else bg)
            elif op == "ICON":
                x, y, n, v = u16(), u16(), u8(), u8()
                x, y = x + self.ox, y + self.oy
                page, off = self.icons_at(n)
                blob = self.icons[off:]
                ncol, h, nl = blob[0], blob[1], blob[2]
                k = 3
                for _ in range(nl):
                    c0, c1, present = blob[k], blob[k + 1], blob[k + 2]
                    k += 3
                    for col in range(ncol):
                        if present & (1 << col):
                            self.bits(x + 8 * col, y, blob[k:k + h], c1 if v else c0)
                            k += h
            elif op in ("POLY", "POLYP"):
                if op == "POLY":
                    c = u8()
                else:
                    fg, bg, p = u8(), u8(), u8()
                nl, nr = u8(), u8()
                left = [(u16() + self.ox, u16() + self.oy) for _ in range(nl)]
                right = [(u16() + self.ox, u16() + self.oy) for _ in range(nr)]
                for y, xl, xr in self.spans(left, right):
                    if op == "POLY":
                        self.rect(xl, y, xr - xl, 1, c)
                    else:
                        row = self.pats[p][y & 7]
                        for x in range(xl, xr):
                            self.put(y, x, fg if row & (0x80 >> (x & 7)) else bg)
            elif op == "IMAGE":
                x, y, w, h = u16(), u16(), u16(), u16()
                img = np.frombuffer(self.image[:w * h], dtype=np.uint8).reshape(h, w)
                ys = np.arange(y + self.oy, y + self.oy + h) % 512
                xs = np.arange(x + self.ox, x + self.ox + w) % 1024
                self.vram[np.ix_(ys, xs)] = img
            elif op == "CURS":
                x, y = u16(), u16()
                if self.cvis:
                    self.c_hide()
                    self.cx, self.cy = x, y
                    self.c_show()
                else:
                    self.cx, self.cy = x, y
            elif op == "HIDE":
                self.c_hide()
            elif op == "SHOW":
                self.c_show()
            elif op == "CALL":
                off = (u8() << 16) | u16()
                self.stack.append(pc)
                pc = off
            elif op == "RET":
                pc = self.stack.pop()
            elif op == "ORG":
                self.ox, self.oy = s16(), s16()
            elif op == "LISTHS":
                y0, y1, v = u16(), u16(), u16()
                self.list = (y0, y1, v & 1023)
                self.hs = 0
            elif op == "LISTOFF":
                self.list = None
                self.rast = None
                self.wave = None
                self.hs = 0
            elif op == "RASTER":
                self.rast["ph"] = u8()
            elif op == "RASTDEF":
                y0, n, idx, base = u16(), u8(), u8(), u16()
                grads = [[u16() for _ in range(8)] for _ in range(3)]
                sint = list(b[pc:pc + 256])
                pc += 256
                self.rast = dict(y0=y0, n=n, idx=idx, base=base, grads=grads, sint=sint, ph=0)
            elif op == "PATDEF":
                p = u8()
                self.pats[p] = np.frombuffer(bytes(b[pc:pc + 8]), dtype=np.uint8)
                pc += 8
            elif op == "TERM":
                n = u16()
                self.t_bytes(bytes(b[pc:pc + n]))
                pc += n
            elif op == "RATE":
                u8()
            elif op == "TINIT":
                self.t_init(u8())
            elif op == "GAME":
                self.game = True                  # the game's pictures are mkgame's; the desktop redraws after
            elif op == "STOP":
                pass
            elif op == "WAVEDF":
                y0, n = u16(), u16()
                tab = list(b[pc:pc + 256])
                pc += 256
                self.wave = dict(y0=y0, n=n, tab=tab)
            elif op == "WAVE":
                u8(), u8()
            elif op == "MUSIC":
                pass
            else:
                raise ValueError(f"model: opcode {op} at {pc - 1}")

    def icons_at(self, n):
        page, hi, lo = self.icons[3 * n], self.icons[3 * n + 1], self.icons[3 * n + 2]
        return page, page * 8192 + ((hi << 8) | lo)


def raster_colours(r, ph):
    """The colour the raster list gives each band line at phase ph - the
    arithmetic gui.asm's rastgen does: three bars, later over earlier, each at
    band line sint[(ph + 85 b) & 255], coloured by distance from its centre."""
    n = r["n"]
    cols = [r["base"]] * n
    for bar in range(3):
        c = r["sint"][(ph + 85 * bar) & 255]
        for i in range(n):
            d = abs(i - c)
            if d < 8:
                cols[i] = r["grads"][bar][d]
    return cols


def wave_offsets(w, code):
    """The HSCROLL each warp entry gives its two lines, for a WAVE whose phase word
    is code: amp in the high byte, ph in the low - gui.asm's opwave."""
    amp, ph = code >> 8, code & 255
    return [(w["tab"][(ph + 2 * i) & 255] * amp) >> 8 for i in range(w["n"])]


def picture_rgb(pic, ph=None, list_dy=0, vram=None):
    """A model picture as RGB565, with the raster phase applied if it has one.
    A warped picture needs the ring (`vram`, `vs`) to fetch the shifted lines."""
    idx, pal = pic["idx"], pic["pal"]
    if pic.get("wave") is not None and ph is not None:
        idx = idx.copy()
        w = pic["wave"]
        for i, v in enumerate(wave_offsets(w, ph)):
            for y in (w["y0"] + 2 * i, w["y0"] + 2 * i + 1):
                idx[y] = pic["ring"][y, (v + np.arange(640)) % 1024]
    out = pal[idx]
    r = pic["rast"]
    if r is not None and ph is not None:
        cols = raster_colours(r, ph)
        h = idx.shape[0]
        for i in range(r["n"]):
            for dy in range(2):
                y = r["y0"] + 2 * i + dy + list_dy
                if 0 <= y < h:
                    row = out[y]
                    row[idx[y] == r["idx"]] = cols[i]
    return out
