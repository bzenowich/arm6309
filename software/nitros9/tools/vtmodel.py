#!/usr/bin/env python3
"""The arm6309 video console's fast-text screen, modelled in Python.

    python3 vtmodel.py --emit DIR      write the scripted clients' streams into DIR
    python3 vtmodel.py --png NAME OUT  render a stream's expected screen as OUT

software/nitros9/docs/nitros9-av-plan.md phase P1 is closed by "a scripted client's output:
emulator frames vs a Python model of the expected text screen". This is the
model. It interprets CoWin's byte protocol as CoArm is meant to - the control
codes $01-$0D, $1F's pairs and the escapes P1 acts on - WITHOUT sharing any code
with it, and renders the picture the card should show: 80 x 25 cells of 8 x 8
glyphs, line-doubled to 640 x 400, through the screen's palette, in RGB565.

What it shares with the 6809 is data, and only data: the font, read from
CoArm's own coarmfont.asm (NitrOS-9's stdfonts set 1), and CoWin's default
colours.

run-vid.sh compares the emulator's last frame against render() pixel for
pixel, and reads text back off a frame with decode().
"""
import os, re, sys
import numpy as np

NITROS9 = os.environ.get("NITROS9DIR") or os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "nitros9")
FONT_ASM = os.path.join(NITROS9, "level2", "arm6309", "modules", "coarmfont.asm")


def font():
    """128 glyphs x 8 row bytes, MSB leftmost, from CoArm's font source."""
    rows = []
    for line in open(FONT_ASM):
        m = re.match(r"\s+fcb\s+(\$[0-9A-F]{2}(?:,\$[0-9A-F]{2}){7})", line)
        if m:
            rows.append([int(t[1:], 16) for t in m.group(1).split(",")])
    assert len(rows) == 128, f"{FONT_ASM}: {len(rows)} glyphs, not 128"
    return np.array(rows, dtype=np.uint8)


# ----------------------------------------------------------------- colour
LVL5 = [0, 10, 20, 31]
LVL6 = [0, 21, 42, 63]
LVL5OF7 = [i * 31 // 7 for i in range(8)]
COWIN_DEFAULTS = [0x3F, 0x09, 0x00, 0x12, 0x24, 0x36, 0x2D, 0x1B]   # white blue black green red yellow magenta cyan


def rgb565(r5, g6, b5):
    return (r5 << 11) | (g6 << 5) | b5


def coco(v):
    """A CoCo 3 colour, 00RGBRGB, as RGB565 - each gun two bits, high then low."""
    two = lambda hi, lo: ((v >> hi) & 1) * 2 + ((v >> lo) & 1)
    return rgb565(LVL5[two(5, 2)], LVL6[two(4, 1)], LVL5[two(3, 0)])


def default_palette():
    """0-15 CoWin's eight twice; 16-231 xterm-256's 6x6x6 cube; 232-255 its
    greys.  ca_scr.asm PalDef is the authority; ca_ext.asm AnsiPal maps ANSI
    0-15 onto the cube so that SGR 38;5;n is a direct index for n >= 16."""
    pal = [coco(COWIN_DEFAULTS[i & 7]) for i in range(16)]
    lvl = [0, 95, 135, 175, 215, 255]
    for r in lvl:
        for g in lvl:
            for b in lvl:
                pal.append(rgb565(r >> 3, g >> 2, b >> 3))
    pal += [rgb565(v >> 3, v >> 2, v >> 3) for v in range(8, 248, 10)]
    return pal


# ----------------------------------------------------------------- the screen
# CoWin's parameter counts for $1B $20-$54; None: CoWin has nothing there
ESC_COUNTS = {0x20: 7, 0x21: 0, 0x22: 7, 0x23: 0, 0x24: 0, 0x25: 4, 0x29: 4, 0x2A: 2, 0x2B: 9, 0x2C: 10,
              0x2D: 6, 0x2E: 2, 0x2F: 1, 0x30: 0, 0x31: 2, 0x32: 1, 0x33: 1, 0x34: 1, 0x35: 1, 0x36: 1,
              0x39: 2, 0x3A: 2, 0x3C: 1, 0x3D: 1, 0x3F: 1, **{c: 4 for c in range(0x40, 0x4C)},
              0x4E: 4, 0x4F: 0, 0x50: 2, 0x51: 4, 0x52: 12, 0x53: 2, 0x54: 4}


class Screen:
    """One fast-text window, as its bytes say it should look."""

    def __init__(self, rows=25, fg=0, bg=2):
        self.cols, self.rows = 80, rows
        self.cells = [[0x20] * self.cols for _ in range(rows)]
        self.x = self.y = 0
        self.fg, self.bg = fg, bg
        self.rev = False
        self.cursor = True
        self.pal = default_palette()
        self._pending = []          # bytes of a sequence not yet complete

    # -- the protocol
    def feed(self, data):
        for b in data:
            self._pending.append(b)
            n = self._need()
            if n is None:
                continue            # still collecting
            seq, self._pending = self._pending, []
            self._do(seq)

    def _need(self):
        """None while the pending sequence is incomplete, else its length."""
        p = self._pending
        c = p[0]
        if c == 0x1B:
            if len(p) < 2:
                return None
            n = ESC_COUNTS.get(p[1])
            if n is None:
                return len(p)
            if p[1] == 0x20 and len(p) >= 3 and p[2] != 0xFF:
                n = 8                                   # DWSet's PRN3, for a new screen
            if len(p) < 2 + n:
                return None
            if p[1] == 0x2B:                            # GPLoad: then its data
                size = (p[9] << 8) | p[10]
                if len(p) < 2 + n + size:
                    return None
            return len(p)
        if c == 0x02:
            return len(p) if len(p) == 3 else None
        if c in (0x05, 0x1F):
            return len(p) if len(p) == 2 else None
        return 1

    def _do(self, s):
        c = s[0]
        if c >= 0x20:
            return self._put(c)
        if c == 0x01:
            self.x = self.y = 0
        elif c == 0x02:
            x, y = s[1] - 32, s[2] - 32
            if 0 <= x < self.cols:
                self.x = x
            if 0 <= y < self.rows:
                self.y = y
        elif c == 0x03:
            self._clear(self.y, 0)
        elif c == 0x04:
            self._clear(self.y, self.x)
        elif c == 0x05:
            if s[1] == 0x20:
                self.cursor = False
            elif s[1] == 0x21:
                self.cursor = True
        elif c == 0x06:
            if self.x + 1 < self.cols:
                self.x += 1
            elif self.y + 1 < self.rows:
                self.x, self.y = 0, self.y + 1
        elif c == 0x08:
            if self.x:
                self.x -= 1
            elif self.y:
                self.x, self.y = self.cols - 1, self.y - 1
        elif c == 0x09:
            if self.y:
                self.y -= 1
        elif c == 0x0A:
            self._lf()
        elif c == 0x0B:
            self._clear(self.y, self.x)
            for r in range(self.y + 1, self.rows):
                self._clear(r, 0)
        elif c == 0x0C:
            self.x = self.y = 0
            for r in range(self.rows):
                self._clear(r, 0)
        elif c == 0x0D:
            self.x = 0
        elif c == 0x1F:
            a = s[1]
            if a == 0x20:
                self.rev = True
            elif a == 0x21:
                self.rev = False
            elif a == 0x30:
                self.cells.insert(self.y, [0x20] * self.cols)
                del self.cells[self.rows]
            elif a == 0x31:
                del self.cells[self.y]
                self.cells.append([0x20] * self.cols)
        elif c == 0x1B:
            e = s[1]
            if e == 0x30:
                self.pal = default_palette()
            elif e == 0x31:
                self.pal[s[2]] = coco(s[3])
            elif e == 0x32:
                self.fg = s[2]
            elif e == 0x33:
                self.bg = s[2]

    def _put(self, c):
        self.cells[self.y][self.x] = (c & 0x7F) | (0x80 if self.rev else 0)
        self.x += 1
        if self.x == self.cols:
            self.x = 0
            self._lf()

    def _lf(self):
        if self.y + 1 < self.rows:
            self.y += 1
        else:
            del self.cells[0]
            self.cells.append([0x20] * self.cols)

    def _clear(self, r, x0):
        for x in range(x0, self.cols):
            self.cells[r][x] = 0x20

    # -- the picture
    def codes(self):
        """The cell codes as the card shows them: the cursor's cell inverted."""
        out = [row[:] for row in self.cells]
        if self.cursor:
            out[self.y][self.x] ^= 0x80
        return out

    def render(self, glyphs=None):
        glyphs = font() if glyphs is None else glyphs
        bits = np.unpackbits(glyphs, axis=1).reshape(128, 8, 8).astype(bool)
        pal = np.array(self.pal, dtype=np.uint16)
        img = np.zeros((self.rows * 16, 640), dtype=np.uint16)
        for r, row in enumerate(self.codes()):
            for x, code in enumerate(row):
                g = bits[code & 0x7F] ^ bool(code & 0x80)
                cell = np.where(g, pal[self.fg], pal[self.bg])
                img[r * 16:(r + 1) * 16, x * 8:(x + 1) * 8] = np.repeat(cell, 2, axis=0)
        return img


def decode(frame, rows=25, glyphs=None):
    """Read the text back off a frame: rows of (string, reversed-cell mask).
    A cell is matched against every glyph and its inverse, by which of its two
    colours is the background - so it reads any colour pair."""
    glyphs = font() if glyphs is None else glyphs
    bits = np.unpackbits(glyphs, axis=1).reshape(128, 8, 8).astype(bool)
    lines = []
    for r in range(rows):
        text, rev = [], []
        for x in range(80):
            cell = frame[r * 16:(r + 1) * 16:2, x * 8:(x + 1) * 8]
            vals, counts = np.unique(cell, return_counts=True)
            best = "?"
            isrev = False
            for bgv in vals[np.argsort(-counts, kind="stable")]:
                on = cell != bgv
                m = np.nonzero((bits == on).all(axis=(1, 2)))[0]
                if len(m):
                    best, isrev = chr(m[0]) if m[0] >= 32 else "?", False
                    break
                m = np.nonzero((bits == ~on).all(axis=(1, 2)))[0]
                if len(m):
                    best, isrev = chr(m[0]) if m[0] >= 32 else "?", True
                    break
            text.append(best)
            rev.append(isrev)
        lines.append(("".join(text), rev))
    return lines


# ----------------------------------------------------------------- the scripted clients
def xy(x, y):
    return bytes([0x02, x + 32, y + 32])


def stream_p1():
    """vtp1: every control code a fast-text screen draws, and escapes that must take
    exactly their parameters. (Graphics escapes are E$IWTyp on a text screen, as on
    CoWin, so none is sent here: the bitmap stream has them.)"""
    s = bytearray(b"\x0c")
    s += b"P1: CoWin's control codes, drawn by CoArm on the arm6309 video card\r\n"
    for i in range(1, 41):                      # 40 lines: the 32-row map ring wraps
        s += b"line %02d of the scroll: the map ring is 32 rows and the screen 25\r\n" % i
    s += b"\x01HOME"
    s += xy(60, 5) + b"XY(60,5)"
    s += xy(10, 7) + b"erase to the end of this line: GONE GONE GONE" + xy(40, 7) + b"\x04"
    s += xy(0, 8) + b"this whole line is erased" + b"\x03" + b"kept"
    s += xy(0, 9) + b"\x1f\x20REVERSE\x1f\x21 normal \x1f\x20again\x1f\x21"
    s += xy(0, 10) + b"ABC\x08\x08x\x06\x06!"
    s += xy(5, 11) + b"\x09up\x0a\x0adown"
    s += xy(76, 13) + b"WRAPPED"            # four on this row, three on the next
    s += xy(0, 16) + b"\x1f\x30inserted at 16"
    s += xy(0, 3) + b"\x1f\x31"             # row 3 goes; 4.. move up
    s += b"\x1b\x2b\xc8\x02\x05\x00\x08\x00\x08\x00\x10" + bytes([0x1B, 0x0C] * 8)   # GPLoad: 16 bytes swallowed
    s += b"\x1b\x2a\xc8\x00"                    # KillBuf: GP buffers are CoArm's, not the window's -
    #                                             left, group $C8 is too small for vgp2a's GPLoad
    s += b"\x1b\x39\x01\x02"                    # GCSet: swallowed
    s += b"\x07\x00"                            # bell, null
    s += xy(0, 20) + b"\x0bafter erase-to-end-of-screen"
    s += b"\x1b\x31\x02\x09"                    # palette 2 (black, the background) := blue
    s += b"\x1b\x32\x05"                        # FColor 5: yellow - the font is rebuilt
    s += xy(0, 22) + b"colours: yellow on palette 2, which is now blue"
    s += b"\x05\x20" + xy(0, 23) + b"cursor off here" + b"\x05\x21" + xy(20, 24) + b"cursor on"
    return bytes(s)


def stream_w2():
    """vtw2: what /W2 (80 x 30, VMODE 01) is given while /W1 is displayed."""
    s = bytearray(b"\x0cThis is /W2, 80 x 30 in VMODE 01, drawn while it was not displayed.\r\n")
    s += b"Select repainted it from its shadow, and the card changed family.\r\n"
    for i in range(1, 34):                      # past the bottom: two spare ring rows, wrapped
        s += b"/W2 line %02d\r\n" % i
    s += xy(40, 29) + b"\x1f\x20bottom right\x1f\x21"
    return bytes(s)


STREAMS = {"vtp1": stream_p1, "vtw2": stream_w2}
ROWS = {"vtp1": 25, "vtw2": 30}


def expected(name):
    sc = Screen(rows=ROWS[name])
    sc.feed(STREAMS[name]())
    return sc


# PS/2 set 2 make codes for what the keyboard check types (ps2.md 11.1)
SET2 = {**{c: k for c, k in zip("abcdefghijklmnopqrstuvwxyz",
                                [0x1C, 0x32, 0x21, 0x23, 0x24, 0x2B, 0x34, 0x33, 0x43, 0x3B, 0x42, 0x4B, 0x3A,
                                 0x31, 0x44, 0x4D, 0x15, 0x2D, 0x1B, 0x2C, 0x3C, 0x2A, 0x1D, 0x22, 0x35, 0x1A])},
        **{c: k for c, k in zip("1234567890", [0x16, 0x1E, 0x26, 0x25, 0x2E, 0x36, 0x3D, 0x3E, 0x46, 0x45])},
        " ": 0x29, "-": 0x4E, ".": 0x49, "/": 0x4A, "\r": 0x5A, "\b": 0x66}
SHIFTED = {">": ".", "_": "-"}


def scancodes(text):
    """The make and break bytes a keyboard sends for text; capitals and SHIFTED
    are typed with the left shift held."""
    out = []
    for ch in text:
        base, shift = ch, False
        if ch.isupper():
            base, shift = ch.lower(), True
        elif ch in SHIFTED:
            base, shift = SHIFTED[ch], True
        k = SET2[base]
        if shift:
            out += [0x12]
        out += [k, 0xF0, k]
        if shift:
            out += [0xF0, 0x12]
    return " ".join("%02X" % b for b in out)

if __name__ == "__main__":
    if sys.argv[1] == "--emit":
        os.makedirs(sys.argv[2], exist_ok=True)
        for name, fn in STREAMS.items():
            open(os.path.join(sys.argv[2], name), "wb").write(fn())
    elif sys.argv[1] == "--png":
        from PIL import Image
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))
        import frames as fr
        Image.fromarray(fr.rgb565_to_rgb8(expected(sys.argv[2]).render())).save(sys.argv[3])
    elif sys.argv[1] == "--keys":
        print(scancodes(sys.argv[2].encode().decode("unicode_escape")))
