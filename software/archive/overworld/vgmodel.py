#!/usr/bin/env python3
"""The arm6309 video console's bitmap screens and windows, modelled in Python.

software/nitros9/docs/nitros9-av-plan.md phase P2 is CoArm's bitmap screens, windows, text,
graphics, GP buffers and the pointer. This is the model run-vid.sh judges them
against: it interprets CoWin's protocol for bitmap windows as
software/nitros9/docs/video-console.md says CoArm does, and renders the
displayed picture. It shares no code with the 6809 - the shapes are
vgshapes.py's definitions and the font is read from coarmfont.asm as data.

A Console holds every screen and every device window; feed(device, bytes)
runs a device's stream; picture() is what the card should show, the pointer
and the text cursor included.
"""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vgshapes as vs
import vtmodel as vt

HEIGHTS = {0x10: 200, 0x11: 240, 0x12: 400, 0x13: 480}

PTR_ART = ["X...............", "XX..............", "XWX.............", "XWWX............",
           "XWWWX...........", "XWWWWX..........", "XWWWWWX.........", "XWWWWWWX........",
           "XWWWWWWWX.......", "XWWWWWWWWX......", "XWWWWWXXXXX.....", "XWWXWWX.........",
           "XWX.XWWX........", "XX..XWWX........", "X....XWWX.......", ".....XXX........"]

PT = dict(Valid=0x00, CBSA=0x08, CBSB=0x09, Stat=0x16, AcX=0x18, AcY=0x1A, WRX=0x1C, WRY=0x1E)


class ModelError(Exception):
    pass


class Screen:
    def __init__(self, sty, bg):
        self.sty = sty
        self.w, self.h = 640, HEIGHTS[sty]
        self.vmode = sty - 0x10
        self.pix = np.full((self.h, self.w), bg, dtype=np.uint8)
        self.pal = vt.default_palette()
        self.wins = 0


class Window:
    def __init__(self, scr, x, y, w, h, fg, bg, parent=None):
        self.scr, self.parent = scr, parent
        self.x, self.y, self.w, self.h = x, y, w, h
        self.ax, self.ay, self.aw, self.ah = x, y, w, h
        self.fg, self.bg = fg, bg
        self.cx = self.cy = 0
        self.px = self.py = 0
        self.rev = self.undl = self.trans = self.bold = False
        self.cursor = True
        self.pat = None
        self.p8 = None           # PatDef's pattern
        self.logic = 0
        self.font = None
        self.save = None


class Device:
    def __init__(self):
        self.win = None          # the device window
        self.cur = None          # the current window: itself or its top overlay
        self.pending = []
        self.ansi = False        # AnsiSw
        self.an_st, self.an_n, self.an_p = 0, 0, [0, 0, 0, 0]
        self.an_fg, self.an_bg, self.an_bold = 7, 0, 0


# CoWin's parameter counts ($20-$54), as vtmodel has them, and the extensions'
# (ca_ext.asm, ca_tile.asm): $61, $65 and $66 are followed by data
ESC_COUNTS = {**vt.ESC_COUNTS, 0x60: 3, 0x61: 2, 0x62: 9, 0x63: 8, 0x64: 6, 0x65: 2, 0x66: 2, 0x67: 6,
              0x68: 7, 0x69: 1}


class Console:
    def __init__(self):
        self.glyphs = vt.font()
        self.devs = {}
        self.disp = None          # the displayed Screen
        self.focus = None         # the Device with the keyboard
        self.gp = {}              # (grp, buf) -> dict(sty, xs, ys, data bytearray)
        self.ptr_on = False
        self.msx = self.msy = 0
        self.pats = [bytes(8)] * 32

    def dev(self, n):
        return self.devs.setdefault(n, Device())

    # ------------------------------------------------------------- the stream
    def feed(self, n, data):
        d = self.dev(n)
        for b in data:
            if d.ansi and not d.pending:
                self._ansi(d, b)
                continue
            d.pending.append(b)
            if self._complete(d.pending):
                seq, d.pending = d.pending, []
                try:
                    self._do(n, d, seq)
                except ModelError:
                    pass                    # an error: the sequence does nothing more

    @staticmethod
    def _complete(p):
        c = p[0]
        if c == 0x1B:
            if len(p) < 2:
                return False
            k = ESC_COUNTS.get(p[1])
            if k is None:
                return True
            if p[1] == 0x20 and len(p) >= 3 and p[2] != 0xFF:
                k = 8
            if len(p) < 2 + k:
                return False
            if p[1] == 0x2B:
                return len(p) >= 2 + k + ((p[9] << 8) | p[10])
            if p[1] == 0x61:
                return len(p) >= 2 + k + 2 * (p[3] or 256)
            if p[1] in (0x65, 0x66):
                return len(p) >= 2 + k + 4 * (p[2] + p[3])
            return True
        if c == 0x02:
            return len(p) == 3
        if c in (0x05, 0x1F):
            return len(p) == 2
        return True

    def _do(self, n, d, s):
        c = s[0]
        if c == 0x1B:
            return self._esc(n, d, s[1], bytes(s[2:]))
        w = d.cur
        if w is None:
            raise ModelError("window undefined")
        if c >= 0x20:
            return self._put(w, c)
        cols, rows = w.aw // 8, w.ah // 8
        if c == 0x01:
            w.cx = w.cy = 0
        elif c == 0x02:
            x, y = s[1] - 32, s[2] - 32
            if 0 <= x < cols:
                w.cx = x
            if 0 <= y < rows:
                w.cy = y
        elif c == 0x03:
            self._clr_row(w, w.cy, 0)
        elif c == 0x04:
            self._clr_row(w, w.cy, w.cx)
        elif c == 0x05:
            if s[1] == 0x20:
                w.cursor = False
            elif s[1] == 0x21:
                w.cursor = True
        elif c == 0x06:
            if w.cx + 1 < cols:
                w.cx += 1
            elif w.cy + 1 < rows:
                w.cx, w.cy = 0, w.cy + 1
        elif c == 0x08:
            if w.cx:
                w.cx -= 1
            elif w.cy:
                w.cy, w.cx = w.cy - 1, cols - 1
        elif c == 0x09:
            if w.cy:
                w.cy -= 1
        elif c == 0x0A:
            self._lf(w)
        elif c == 0x0B:
            self._clr_row(w, w.cy, w.cx)
            for r in range(w.cy + 1, rows):
                self._clr_row(w, r, 0)
        elif c == 0x0C:
            w.cx = w.cy = 0
            for r in range(rows):
                self._clr_row(w, r, 0)
        elif c == 0x0D:
            w.cx = 0
        elif c == 0x1F:
            a = s[1]
            if a == 0x20:
                w.rev = True
            elif a == 0x21:
                w.rev = False
            elif a == 0x22:
                w.undl = True
            elif a == 0x23:
                w.undl = False
            elif a == 0x30:
                for r in range(rows - 1, w.cy, -1):
                    self._row_move(w, r, r - 1)
                self._clr_row(w, w.cy, 0)
            elif a == 0x31:
                for r in range(w.cy, rows - 1):
                    self._row_move(w, r, r + 1)
                self._clr_row(w, rows - 1, 0)

    # ------------------------------------------------------------- text
    def _glyph(self, w, code):
        if w.font is None:
            g = list(self.glyphs[code & 0x7F])
        else:
            buf = self.gp.get(w.font)
            data = buf["data"] if buf else b""
            if (code + 1) * 8 <= len(data):
                g = list(data[code * 8:code * 8 + 8])
            elif ((code & 0x7F) + 1) * 8 <= len(data):
                g = list(data[(code & 0x7F) * 8:(code & 0x7F) * 8 + 8])
            else:
                g = [0] * 8
        if w.bold:
            g = [(b | (b >> 1)) & 0xFF for b in g]
        if w.undl:
            g[7] = 0xFF
        return g

    def _put(self, w, code):
        fg, bg = (w.bg, w.fg) if w.rev else (w.fg, w.bg)
        g = self._glyph(w, code)
        x0, y0 = w.ax + w.cx * 8, w.ay + w.cy * 8
        pix = w.scr.pix
        for r in range(8):
            for i in range(8):
                if g[r] & (0x80 >> i):
                    pix[y0 + r, x0 + i] = fg
                elif not w.trans:
                    pix[y0 + r, x0 + i] = bg
        w.cx += 1
        if (w.cx + 1) * 8 > w.aw:
            w.cx = 0
            self._lf(w)

    def _lf(self, w):
        if (w.cy + 2) * 8 > w.ah:
            p = w.scr.pix
            p[w.ay:w.ay + w.ah - 8, w.ax:w.ax + w.aw] = p[w.ay + 8:w.ay + w.ah, w.ax:w.ax + w.aw].copy()
            self._clr_row(w, w.ah // 8 - 1, 0)
        else:
            w.cy += 1

    def _clr_row(self, w, row, col):
        x0, y0 = w.ax + col * 8, w.ay + row * 8
        w.scr.pix[y0:y0 + 8, x0:w.ax + w.aw] = w.bg

    def _row_move(self, w, dst, src):
        p = w.scr.pix
        ys, yd = w.ay + src * 8, w.ay + dst * 8
        p[yd:yd + 8, w.ax:w.ax + w.aw] = p[ys:ys + 8, w.ax:w.ax + w.aw].copy()

    # ------------------------------------------------------------- drawing
    def _span(self, w, y, xa, xb):
        if not (w.ay <= y <= w.ay + w.ah - 1):
            return
        xa, xb = max(xa, w.ax), min(xb, w.ax + w.aw - 1)
        if xa > xb:
            return
        row = w.scr.pix[y]
        for x in range(xa, xb + 1):
            v = w.fg
            if w.pat is not None:
                buf = self.gp[w.pat]
                pw = min(buf["xs"], 128)
                ry = (y - w.ay) % buf["ys"]
                v = buf["data"][ry * buf["xs"] + (x - w.ax) % pw]
            if w.logic == 1:
                v &= int(row[x])
            elif w.logic == 2:
                v |= int(row[x])
            elif w.logic == 3:
                v ^= int(row[x])
            row[x] = v

    def _patspan(self, w, y, xa, xb):
        if not (w.ay <= y <= w.ay + w.ah - 1):
            return
        xa, xb = max(xa, w.ax), min(xb, w.ax + w.aw - 1)
        row = self.pats[w.p8][y & 7] if w.p8 is not None else 0
        for x in range(xa, xb + 1):
            w.scr.pix[y, x] = w.fg if row & (0x80 >> (x & 7)) else w.bg

    # ------------------------------------------------------------- ANSI (AnsiSw)
    def _ansi(self, d, b):
        if d.an_st == 1:                        # after ESC
            d.an_st = 0
            if b == ord("["):
                d.an_st, d.an_n, d.an_p = 2, 0, [0, 0, 0, 0]
            elif b == 0x69:
                d.pending = [0x1B, 0x69]
            return
        if d.an_st == 2:                        # in a CSI
            if b == ord(";"):
                d.an_n = min(d.an_n + 1, 3)
            elif ord("0") <= b <= ord("9"):
                d.an_p[d.an_n] = min(d.an_p[d.an_n] * 10 + b - ord("0"), 255)
            elif b >= ord("@"):
                d.an_st = 0
                w = d.cur
                if w is None or w.scr.sty not in HEIGHTS:
                    return
                self._csi(d, w, chr(b), d.an_p[:d.an_n + 1])
            return
        if b == 0x1B:
            d.an_st = 1
            return
        w = d.cur
        if w is None or w.scr.sty not in HEIGHTS:
            return
        if b == 0x0D:
            w.cx = 0
        elif b == 0x0A:
            self._an_lf(d, w)
        elif b == 0x08:
            w.cx = max(0, w.cx - 1)
        elif b in (0, 7):
            pass
        else:
            if w.cx >= w.aw // 8:
                w.cx = 0
                self._an_lf(d, w)
            self._an_col(d, w)
            g = self._glyph(w, b)
            x0, y0 = w.ax + w.cx * 8, w.ay + w.cy * 8
            for r in range(8):
                for i in range(8):
                    w.scr.pix[y0 + r, x0 + i] = w.fg if g[r] & (0x80 >> i) else w.bg
            w.cx += 1

    # ca_ext.asm AnsiPal: ANSI 0-15 onto xterm-256's cube, which PalDef puts at
    # 16-231 with its greys at 232-255.  16-255 are already a palette index.
    ANSI_PAL = [16, 160, 40, 184, 21, 165, 45, 254, 244, 196, 46, 226, 63, 201, 51, 231]

    @classmethod
    def _an_map(cls, v):
        return cls.ANSI_PAL[v] if v < 16 else v

    @classmethod
    def _an_col(cls, d, w):
        f = d.an_fg
        if f < 8 and d.an_bold:          # AnCol: 8-255 are already bright or direct
            f += 8
        w.fg, w.bg = cls._an_map(f), cls._an_map(d.an_bg)

    def _an_lf(self, d, w):
        w.bg = 0
        self._lf(w)
        self._an_col(d, w)

    def _csi(self, d, w, final, ps):
        cols, rows = w.aw // 8, w.ah // 8
        n1 = ps[0] or 1
        if final == "m":
            ps = list(ps)
            # An256: 38;5;n and 48;5;n are taken before the loop and blanked to
            # 255, which no other branch claims
            for i in range(max(0, len(ps) - 2)):
                if ps[i] in (38, 48) and ps[i + 1] == 5:
                    if ps[i] == 38:
                        d.an_fg = ps[i + 2]
                    else:
                        d.an_bg = ps[i + 2]
                    ps[i] = ps[i + 1] = ps[i + 2] = 255
            for v in ps:
                if v == 0:
                    d.an_fg, d.an_bg, d.an_bold = 7, 0, 0
                elif v == 1:
                    d.an_bold = 1
                elif v == 22:
                    d.an_bold = 0
                elif v == 39:
                    d.an_fg = 7
                elif v == 49:
                    d.an_bg = 0
                elif 30 <= v <= 37:
                    d.an_fg = v - 30
                elif 40 <= v <= 47:
                    d.an_bg = v - 40
                elif 90 <= v <= 97:            # aixterm's bright foregrounds
                    d.an_fg = v - 90 + 8
                elif 100 <= v <= 107:          # ... and its bright backgrounds
                    d.an_bg = v - 100 + 8
            self._an_col(d, w)
        elif final == "J":
            if ps[0] == 2:
                w.scr.pix[w.ay:w.ay + w.ah, w.ax:w.ax + w.aw] = 0
                w.cx = w.cy = 0
                self._an_col(d, w)
        elif final in "Hf":
            r = (ps[0] - 1) if ps[0] else 0
            c = (ps[1] - 1) if len(ps) > 1 and ps[1] else 0
            w.cy, w.cx = min(r, rows - 1), min(c, cols - 1)
        elif final == "K":
            if w.cx < cols:
                self._clr_row(w, w.cy, w.cx)
        elif final == "C":
            w.cx = min(cols - 1, w.cx + n1)
        elif final == "D":
            w.cx = max(0, w.cx - n1)
        elif final == "A":
            w.cy = max(0, w.cy - n1)
        elif final == "B":
            w.cy = min(rows - 1, w.cy + n1)

    def _points(self, w, pts):
        for x, y in pts:
            self._span(w, y, x, x)

    def _esc(self, n, d, code, p):
        W = lambda i: int.from_bytes(p[i:i + 2], "big")
        S = lambda i: int.from_bytes(p[i:i + 2], "big", signed=True)
        w = d.cur
        if code == 0x20:
            return self._dwset(n, d, p)
        if code == 0x29:                                       # DefGPB
            if p[0] in (0, 0xFF) or p[1] == 0 or W(2) == 0 or (p[0], p[1]) in self.gp:
                raise ModelError("DefGPB")
            self.gp[(p[0], p[1])] = dict(sty=0, xs=0, ys=0, data=bytearray(W(2)))
            return
        if code == 0x2A:                                       # KillBuf
            if p[1] == 0:
                for k in [k for k in self.gp if k[0] == p[0]]:
                    del self.gp[k]
            else:
                self.gp.pop((p[0], p[1]), None)
            return
        if code == 0x2B:                                       # GPLoad
            nbytes = W(7)
            data = bytes(p[9:9 + nbytes])
            key = (p[0], p[1])
            if key in self.gp:
                if len(self.gp[key]["data"]) < nbytes:
                    raise ModelError("BufSiz")
            else:
                self.gp[key] = dict(sty=0, xs=0, ys=0, data=bytearray(nbytes))
            b = self.gp[key]
            b.update(sty=p[2], xs=W(3), ys=W(5))
            b["data"][:nbytes] = data
            return
        if code == 0x62:                                       # PatDef
            self.pats[p[0] & 31] = bytes(p[1:9])
            if w is not None:
                w.p8 = p[0] & 31
            return
        if code == 0x39:                                       # GCSet
            self.ptr_on = p[0] != 0
            return
        if code == 0x4E:                                       # PutGC
            self.msx, self.msy = W(0), W(2)
            self._clamp()
            return
        if w is None:
            raise ModelError("window undefined")
        scr = w.scr
        if code == 0x21:
            self._select(n, d)
        elif code == 0x22:
            self._owset(d, p)
        elif code == 0x23:
            if w.parent is None:
                raise ModelError("not an overlay")
            x, y, save = w.x, w.y, w.save
            if save is not None:
                scr.pix[y:y + save.shape[0], x:x + save.shape[1]] = save
            scr.wins -= 1
            d.cur = w.parent
        elif code == 0x24:
            self._dwend(d)
        elif code == 0x25:                                     # CWArea
            cpx, cpy, szx, szy = p[0] * 8, p[1] * 8, p[2] * 8, p[3] * 8
            if szx == 0 or szy == 0 or cpx + szx > w.w or cpy + szy > w.h:
                raise ModelError("CWArea")
            w.ax, w.ay, w.aw, w.ah = w.x + cpx, w.y + cpy, szx, szy
            w.cx = w.cy = 0
        elif code == 0x2C:                                     # GetBlk
            x, y, xs, ys = S(2), S(4), W(6), W(8)
            if x < 0 or y < 0 or xs == 0 or ys == 0 or x + xs > w.aw or y + ys > w.ah or xs * ys > 65535:
                raise ModelError("ICoord")
            if (p[0], p[1]) in self.gp:
                raise ModelError("exists")
            blk = scr.pix[w.ay + y:w.ay + y + ys, w.ax + x:w.ax + x + xs]
            self.gp[(p[0], p[1])] = dict(sty=scr.sty, xs=xs, ys=ys, data=bytearray(blk.tobytes()))
        elif code == 0x2D:                                     # PutBlk
            b = self.gp.get((p[0], p[1]))
            if b is None:
                raise ModelError("BadBuf")
            x0, y0 = w.ax + S(2), w.ay + S(4)
            for r in range(b["ys"]):
                y = y0 + r
                if y < w.ay:
                    continue
                if y > w.ay + w.ah - 1:
                    break
                if b["sty"] == 5:
                    nb = (b["xs"] + 7) // 8
                    rowb = b["data"][r * nb:r * nb + min(nb, 80)]
                    row = []
                    for byte in rowb:
                        for i in range(8):
                            row.append(w.fg if byte & (0x80 >> i) else w.bg)
                else:
                    row = list(b["data"][r * b["xs"]:r * b["xs"] + min(b["xs"], 640)])
                for i, v in enumerate(row[:b["xs"]]):
                    x = x0 + i
                    if w.ax <= x <= w.ax + w.aw - 1:
                        scr.pix[y, x] = v
        elif code == 0x2E:                                     # PSet
            if p[0] == 0:
                w.pat = None
            else:
                if (p[0], p[1]) not in self.gp:
                    raise ModelError("BadBuf")
                w.pat = (p[0], p[1])
        elif code == 0x2F:
            if p[0] > 3:
                raise ModelError("IllArg")
            w.logic = p[0]
        elif code == 0x30:
            scr.pal = vt.default_palette()
        elif code == 0x31:
            scr.pal[p[0]] = vt.coco(p[1])
        elif code == 0x32:
            w.fg = p[0]
        elif code == 0x33:
            w.bg = p[0]
        elif code == 0x3A:                                     # Font
            if p[0] == 0:
                w.font = None
            elif (p[0], p[1]) in self.gp:
                w.font = (p[0], p[1])
            else:
                raise ModelError("NFont")
        elif code == 0x3C:
            w.trans = p[0] != 0
        elif code == 0x3D:
            w.bold = p[0] != 0
        elif code == 0x40:
            w.px, w.py = S(0), S(2)
        elif code == 0x41:
            w.px, w.py = w.px + S(0), w.py + S(2)
        elif code in (0x42, 0x43):
            x, y = (S(0), S(2)) if code == 0x42 else (w.px + S(0), w.py + S(2))
            self._span(w, w.ay + y, w.ax + x, w.ax + x)
        elif 0x44 <= code <= 0x47:
            rel, move = code in (0x45, 0x47), code in (0x46, 0x47)
            x1, y1 = (w.px + S(0), w.py + S(2)) if rel else (S(0), S(2))
            pts = vs.line(w.px, w.py, x1, y1)
            self._points(w, [(w.ax + x, w.ay + y) for x, y in pts])
            if move:
                w.px, w.py = x1, y1
        elif 0x48 <= code <= 0x4B:
            rel = code in (0x49, 0x4B)
            x1, y1 = (w.px + S(0), w.py + S(2)) if rel else (S(0), S(2))
            if code in (0x48, 0x49):
                self._points(w, [(w.ax + x, w.ay + y) for x, y in vs.box(w.px, w.py, x1, y1)])
            else:
                for y, xa, xb in vs.bar_spans(w.px, w.py, x1, y1):
                    self._span(w, w.ay + y, w.ax + xa, w.ax + xb)
        elif code == 0x4F:                                     # FFill: solid
            fx, fy = w.ax + w.px, w.ay + w.py
            clip = (w.ax, w.ay, w.ax + w.aw - 1, w.ay + w.ah - 1)
            if clip[0] <= fx <= clip[2] and clip[1] <= fy <= clip[3]:
                vs.ffill(scr.pix, fx, fy, w.fg, clip)
        elif code in (0x50, 0x51, 0x53, 0x54, 0x52):
            cx, cy = w.ax + w.px, w.ay + w.py
            if code in (0x50, 0x53):
                rx = ry = W(0)
            else:
                rx, ry = W(0), W(2)
            if code == 0x52:
                pts = vs.arc_points(cx, cy, rx, ry, S(4), S(6), S(8), S(10))
                self._points(w, pts)
            else:
                for y, xa, xb in vs.ellipse_spans(cx, cy, rx, ry, code in (0x53, 0x54)):
                    self._span(w, y, xa, xb)
        elif code == 0x60:                                     # Pal565
            scr.pal[p[0]] = W(1)
        elif code == 0x61:                                     # PalRange
            for i in range(p[1] or 256):
                scr.pal[(p[0] + i) & 255] = int.from_bytes(p[2 + 2 * i:4 + 2 * i], "big")
        elif code == 0x63:                                     # PatBar
            xa, xb = sorted((w.ax + S(0), w.ax + S(4)))
            ya, yb = sorted((w.ay + S(2), w.ay + S(6)))
            for y in range(ya, yb + 1):
                self._patspan(w, y, xa, xb)
        elif code == 0x64:                                     # PutMask
            b = self.gp.get((p[0], p[1]))
            if b is None or b["sty"] != 5:
                raise ModelError("BadBuf")
            x0, y0 = w.ax + S(2), w.ay + S(4)
            nb = (b["xs"] + 7) // 8
            for r in range(b["ys"]):
                y = y0 + r
                if y < w.ay:
                    continue
                if y > w.ay + w.ah - 1:
                    break
                rowb = b["data"][r * nb:r * nb + min(nb, 80)]
                for i in range(b["xs"]):
                    x = x0 + i
                    if w.ax <= x <= w.ax + w.aw - 1 and rowb[i >> 3] & (0x80 >> (i & 7)):
                        scr.pix[y, x] = w.fg
        elif code in (0x65, 0x66):                             # Poly, PolyPat
            nl, nr = p[0], p[1]
            if nl < 2 or nr < 2 or nl + nr > 16:
                raise ModelError("IllArg")
            pts = [(w.ax + S(2 + 4 * i), w.ay + S(4 + 4 * i)) for i in range(nl + nr)]
            for y, xl, xr in poly_spans(pts[:nl], pts[nl:]):
                if code == 0x65:
                    self._span(w, y, xl, xr - 1)
                else:
                    self._patspan(w, y, xl, xr - 1)
        elif code == 0x67:                                     # Image: PutBlk
            return self._esc(n, d, 0x2D, p)
        elif code == 0x68:                                     # Icon
            b = self.gp.get((p[0], p[1]))
            if b is None:
                raise ModelError("BadBuf")
            blob = bytes(b["data"][:1024])
            ncol, h, nl = blob[0], blob[1], blob[2]
            x0, y0, sel = w.ax + S(2), w.ay + S(4), p[6]
            for r in range(h):
                y = y0 + r
                if y < w.ay:
                    continue
                if y > w.ay + w.ah - 1:
                    break
                k = 3
                for _ in range(nl):
                    c = blob[k + 1] if sel else blob[k]
                    present = blob[k + 2]
                    k += 3
                    for col in range(ncol):
                        if present & (1 << col):
                            byte = blob[k + r]
                            for i in range(8):
                                x = x0 + 8 * col + i
                                if byte & (0x80 >> i) and w.ax <= x <= w.ax + w.aw - 1:
                                    scr.pix[y, x] = c
                            k += h
        elif code == 0x69:                                     # AnsiSw
            d.ansi = p[0] != 0
            d.an_st = 0
            if d.ansi:
                d.an_fg, d.an_bg, d.an_bold = 7, 0, 0
                w.cursor = False
            else:
                w.cursor = True
        # $34 Border, $35 ScaleSw, $36 DWProtSw, $3F PropSw: accepted

    def _dwset(self, n, d, p):
        if d.win is not None:
            raise ModelError("WADef")
        sty = p[0]
        if sty == 0xFF:
            scr = self.disp
            if scr is None:
                raise ModelError("WUndef")
        elif sty in HEIGHTS:
            scr = Screen(sty, p[6])
        else:
            raise ModelError("IWTyp")
        x, y, w, h = p[1] * 8, p[2] * 8, p[3] * 8, p[4] * 8
        if w == 0 or h == 0 or x + w > scr.w or y + h > scr.h:
            raise ModelError("IWDef")
        win = Window(scr, x, y, w, h, p[5], p[6])
        scr.pix[y:y + h, x:x + w] = win.bg
        scr.wins += 1
        d.win = d.cur = win
        if self.disp is None:
            self.disp, self.focus = scr, d
            self._clamp()

    def _owset(self, d, p):
        root = d.win
        cpx, cpy, szx, szy = p[1] * 8, p[2] * 8, p[3] * 8, p[4] * 8
        if szx == 0 or szy == 0 or cpx + szx > root.w or cpy + szy > root.h:
            raise ModelError("IWDef")
        scr = root.scr
        ov = Window(scr, root.ax + cpx, root.ay + cpy, szx, szy, p[5], p[6], parent=d.cur)
        if p[0]:
            ov.save = scr.pix[ov.y:ov.y + szy, ov.x:ov.x + szx].copy()
        scr.pix[ov.y:ov.y + szy, ov.x:ov.x + szx] = ov.bg
        scr.wins += 1
        d.cur = ov

    def _dwend(self, d):
        while d.cur is not d.win:
            w = d.cur
            if w.save is not None:
                w.scr.pix[w.y:w.y + w.save.shape[0], w.x:w.x + w.save.shape[1]] = w.save
            w.scr.wins -= 1
            d.cur = w.parent
        scr = d.win.scr
        scr.wins -= 1
        if scr.wins == 0 and scr is self.disp:
            self.disp = None
        d.win = d.cur = None

    def _select(self, n, d):
        self.focus = d
        if self.disp is not d.cur.scr:
            self.disp = d.cur.scr
            self._clamp()

    def _clamp(self):
        if self.disp is not None:
            self.msx = min(max(self.msx, 0), 639)
            self.msy = min(max(self.msy, 0), self.disp.h - 1)

    def mouse(self, dx, dy):
        """A packet's deltas, as KbdArm applies them: y is up."""
        self.msx = min(max(self.msx + dx, 0), 639)
        h = self.disp.h if self.disp is not None else 480
        self.msy = min(max(self.msy - dy, 0), h - 1)

    # ------------------------------------------------------------- the picture
    def picture(self, indices=False):
        scr = self.disp
        idx = scr.pix.copy()
        d = self.focus
        if d is not None and d.cur is not None and d.cur.scr is scr and d.cur.cursor:
            w = d.cur
            x0, y0 = w.ax + w.cx * 8, w.ay + w.cy * 8
            idx[y0:y0 + 8, x0:x0 + 8] ^= 0xFF
        if self.ptr_on:
            for r, row in enumerate(PTR_ART):
                y = self.msy + r
                if y >= scr.h:
                    break
                for c, ch in enumerate(row):
                    x = self.msx + c
                    if x < 640 and ch != ".":
                        idx[y, x] = 0 if ch == "X" else 1
        if scr.vmode in (0, 1):
            idx = np.repeat(idx, 2, axis=0)
        if indices:
            return idx, np.array(scr.pal, dtype=np.uint16)
        return np.array(scr.pal, dtype=np.uint16)[idx]


# ----------------------------------------------------------------- the scripted clients
def poly_spans(left, right):
    """software/tools/show.py's polygon rule (Model.spans): (y, xl, xr),
    line y covering [xl, xr)."""
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
        if y in L and y in R and R[y] > L[y]:
            yield y, L[y], R[y]


def esc(code, *parts):
    b = bytearray([0x1B, code])
    for p in parts:
        if isinstance(p, (bytes, bytearray)):
            b += p
        elif isinstance(p, tuple):              # a 16-bit word
            b += int(p[0]).to_bytes(2, "big", signed=p[0] < 0)
        else:
            b.append(p)
    return bytes(b)


def w16(v):
    return (v,)


def xy(x, y):
    return bytes([0x02, x + 32, y + 32])


PATTERN = bytes([(3 if (x + y) % 4 < 2 else 5) for y in range(8) for x in range(8)])   # green and yellow stripes


def stream_p2a():
    """vgp2a, for /W3: a 640 x 200 bitmap screen - text, graphics, GP buffers."""
    s = bytearray()
    s += esc(0x20, 0x10, 0, 0, 80, 25, 0, 1, 2)                # white on blue
    s += b"P2: a bitmap window on the arm6309 video card\r\n"
    s += b"\x1f\x20reverse\x1f\x21 \x1f\x22underlined\x1f\x23 " + esc(0x3D, 1) + b"bold" + esc(0x3D, 0) + b"\r\n"
    # shapes on the left half
    s += esc(0x32, 5) + esc(0x40, w16(8), w16(32)) + esc(0x4A, w16(100), w16(60))       # a yellow bar
    s += esc(0x32, 4) + esc(0x40, w16(110), w16(32)) + esc(0x48, w16(200), w16(60))     # a red box
    s += esc(0x32, 7) + esc(0x40, w16(8), w16(70)) + esc(0x46, w16(200), w16(100)) + esc(0x47, w16(-50), w16(-30))
    s += esc(0x32, 0) + esc(0x40, w16(260), w16(50)) + esc(0x50, w16(20))              # a circle
    s += esc(0x32, 6) + esc(0x40, w16(330), w16(50)) + esc(0x54, w16(30), w16(14))     # a filled ellipse
    s += esc(0x32, 3) + esc(0x40, w16(420), w16(50)) + esc(0x52, w16(30), w16(20), w16(-30), w16(0), w16(30), w16(5))
    # a closed box, filled
    s += esc(0x32, 0) + esc(0x40, w16(470), w16(30)) + esc(0x48, w16(530), w16(70))
    s += esc(0x32, 4) + esc(0x40, w16(480), w16(40)) + esc(0x4F)
    # XOR over the yellow bar and the box
    s += esc(0x2F, 3) + esc(0x32, 0x0F) + esc(0x40, w16(60), w16(40)) + esc(0x4A, w16(160), w16(50)) + esc(0x2F, 0)
    # a pattern
    s += esc(0x2B, 1, 1, 0x10, w16(8), w16(8), w16(64), PATTERN)
    s += esc(0x2E, 1, 1) + esc(0x40, w16(560), w16(30)) + esc(0x4A, w16(630), w16(80)) + esc(0x2E, 0, 0)
    # GetBlk and PutBlk
    s += esc(0x2C, 2, 1, w16(8), w16(32), w16(120), w16(40)) + esc(0x2D, 2, 1, w16(500), w16(110))
    # a font of our own: every glyph a hollow square, in group $C8 buffer 2
    square = bytes([0xFF, 0x81, 0x81, 0x81, 0x81, 0x81, 0x81, 0xFF]) * 128
    s += esc(0x2B, 0xC8, 2, 5, w16(8), w16(8), w16(len(square)), square)
    s += xy(0, 13) + esc(0x3A, 0xC8, 2) + b"squares" + esc(0x3A, 0, 0) + b" and back"
    # transparent text over a bar
    s += esc(0x32, 3) + esc(0x40, w16(0), w16(112)) + esc(0x4A, w16(160), w16(119)) + esc(0x32, 0)
    s += xy(0, 14) + esc(0x3C, 1) + b"transparent" + esc(0x3C, 0)
    # a working area of its own, scrolled by copying
    s += esc(0x25, 2, 16, 30, 4)
    for i in range(1, 8):
        s += b"working area line %d\r\n" % i
    s += esc(0x25, 0, 0, 80, 25)
    # an overlay that saves what it covers, drawn in, ended
    s += xy(40, 16) + b"under the overlay"
    s += esc(0x22, 1, 38, 15, 30, 4, 7, 4) + b"an overlay: cyan on red" + esc(0x23)
    # an overlay kept
    s += esc(0x22, 0, 50, 20, 26, 4, 2, 5) + b"a kept overlay" + b"\r\n" + b"black on yellow"
    s += esc(0x39, 0xCA, 1) + esc(0x4E, w16(300), w16(150))
    return bytes(s)


def stream_p2b():
    """vgp2b, for /W4: a 640 x 240 screen made and drawn while /W3 is displayed."""
    s = bytearray()
    s += esc(0x20, 0x11, 0, 0, 80, 30, 2, 5, 2)                # black on yellow
    s += b"P2: /W4, 640 x 240, drawn in DRAM while /W3 was displayed\r\n"
    s += esc(0x32, 4) + esc(0x40, w16(320), w16(120)) + esc(0x53, w16(60))
    s += esc(0x32, 1) + esc(0x40, w16(20), w16(40)) + esc(0x48, w16(620), w16(220))
    s += xy(2, 25) + b"Select repaints it from its store"
    return bytes(s)


# ----------------------------------------------------------------- P3: raster bars
# rastbar's band: scanlines y0 .. y0 + 2n - 1 of a 640 x 200 screen (pixel rows
# 40-119), palette entry idx, and three bars moved `step` phases a frame
RAST = dict(y0=80, n=80, idx=15, frames=64, step=3)


def _grads():
    def rgb565(r, g, b):
        return (round(r * 31 / 255) << 11) | (round(g * 63 / 255) << 5) | round(b * 31 / 255)
    tops = [(255, 64, 64), (64, 255, 64), (96, 128, 255)]
    return [[rgb565(*(int(c * (8 - d) / 8) for c in top)) for d in range(8)] for top in tops]


def _sint(n):
    import math
    return [n // 2 + int(round((n // 2 - 2) * math.sin(2 * math.pi * i / 256))) for i in range(256)]


def stream_rast():
    """vgrast: the screen rastbar puts its bars on, then Select."""
    s = bytearray()
    s += esc(0x20, 0x10, 0, 0, 80, 25, 0, 2, 2)                # black on green
    s += b"P3: raster bars, a display list rewritten every frame by SS.Raster"
    s += esc(0x32, RAST["idx"]) + esc(0x40, w16(40), w16(RAST["y0"] // 2))
    s += esc(0x4A, w16(599), w16(RAST["y0"] // 2 + RAST["n"] - 1))
    s += esc(0x32, 0) + esc(0x21)
    return bytes(s)


def rast_def():
    """show.py's raster definition for rastbar: base is the entry as the screen has it."""
    con = Console()
    con.feed(3, stream_rast())
    base = int(con.disp.pal[RAST["idx"]])
    return dict(y0=RAST["y0"], n=RAST["n"], idx=RAST["idx"], base=base, grads=_grads(), sint=_sint(RAST["n"]))


def rastdat():
    r = rast_def()
    b = bytearray(r["y0"].to_bytes(2, "big") + bytes([r["n"], r["idx"]]) + r["base"].to_bytes(2, "big"))
    for g in r["grads"]:
        for c in g:
            b += c.to_bytes(2, "big")
    b += bytes(r["sint"]) + bytes([RAST["frames"], RAST["step"]])
    assert len(b) == 312
    return bytes(b)


def raster_colours(r, ph):
    """software/tools/show.py's raster_colours, the same arithmetic."""
    cols = [r["base"]] * r["n"]
    for bar in range(3):
        c = r["sint"][(ph + 85 * bar) & 255]
        for i in range(r["n"]):
            d = abs(i - c)
            if d < 8:
                cols[i] = r["grads"][bar][d]
    return cols


def rast_picture(idx, pal, r, ph):
    """The screen as the card shows it while a list of phase ph runs: the
    band's scanlines of entry idx in that line's colour."""
    out = pal[idx]
    if ph is None:
        return out
    for i, c in enumerate(raster_colours(r, ph)):
        for y in (r["y0"] + 2 * i, r["y0"] + 2 * i + 1):
            out[y][idx[y] == r["idx"]] = c
    return out


# ----------------------------------------------------------------- P3: the warp
# wave's band: scanlines y0 .. y0 + 2n - 1 (pixel rows 20-169), each band line
# scrolled (tab[(ph + 2i) & 255] * amp) >> 8 pixels - gui.asm's opwave
WAVE = dict(y0=40, n=150, amp=48, frames=64, step=5)


def stream_wave():
    """vgwave: stripes and text to warp, then Select."""
    s = bytearray()
    s += esc(0x20, 0x10, 0, 0, 80, 25, 0, 2, 2)
    s += b"P3: a warp, an HSCROLL display list rewritten every frame by SS.Raster"
    for k, x in enumerate(range(0, 640, 32)):
        s += esc(0x32, 3 + k % 5) + esc(0x40, w16(x), w16(24)) + esc(0x4A, w16(x + 15), w16(165))
    s += esc(0x32, 0) + xy(10, 10) + b"   the lines between rows 20 and 169 move   "
    s += esc(0x21)
    return bytes(s)


def _wtab():
    import math
    return [128 + int(round(127 * math.sin(2 * math.pi * i / 256))) for i in range(256)]


def wavedat():
    b = WAVE["y0"].to_bytes(2, "big") + bytes([WAVE["n"], WAVE["amp"]]) + bytes(_wtab()) + \
        bytes([WAVE["frames"], WAVE["step"]])
    assert len(b) == 262
    return b


def wave_picture(idx, pal, ph):
    """The screen while a warp list of phase ph runs. idx is picture(True)'s,
    line-doubled; the ring's columns past 640 are colour 0 (CoArm's Select)."""
    out = pal[idx].copy()
    if ph is None:
        return out
    tab, w = _wtab(), WAVE
    ring = np.zeros((idx.shape[0], 1024), dtype=np.uint8)
    ring[:, :640] = idx
    for i in range(w["n"]):
        v = (tab[(ph + 2 * i) & 255] * w["amp"]) >> 8
        for y in (w["y0"] + 2 * i, w["y0"] + 2 * i + 1):
            out[y] = pal[ring[y, (v + np.arange(640)) % 1024]]
    return out


# ----------------------------------------------------------------- P3: the overworld
def stream_game():
    """vggame: overworld's tile screen, the game's RGB332 palette in RGB565, Select."""
    sys.path.insert(0, os.path.join(HERE, "..", "..", "demo", "tools"))
    import frames as fr
    pal = fr.palette565()
    s = bytearray()
    s += esc(0x20, 0x1C, 0, 0, 80, 25, 0, 0, 0)
    s += esc(0x61, 0, 0) + b"".join(int(v).to_bytes(2, "big") for v in pal)
    s += esc(0x21)
    return bytes(s)


# ----------------------------------------------------------------- P3: the extensions
def _icon_blob():
    sys.path.insert(0, os.path.join(HERE, "..", "..", "demo", "tools"))
    import show
    art = np.full((16, 16), -1, dtype=np.int32)
    art[2:14, 2:14] = 3                                         # a green square,
    art[5:11, 5:11] = 5                                         # a yellow one in it,
    art[0, :] = 0                                               # a white top edge
    return show.Icon("p3", art, sel={3: 4, 5: 6, 0: 2}).blob()


def stream_p3():
    """vgp3, for /W3: every extension escape, then an ANSI terminal in an overlay."""
    s = bytearray()
    s += esc(0x20, 0x10, 0, 0, 80, 25, 0, 1, 1)                # white on blue
    s += b"P3: PatDef PatBar Poly PolyPat PutMask Image Icon Pal565 PalRange AnsiSw"
    s += esc(0x32, 4) + esc(0x33, 7)
    s += esc(0x62, 1, bytes([0xAA, 0x55] * 4)) + esc(0x63, w16(8), w16(16), w16(151), w16(63))
    s += esc(0x62, 2, bytes([0x80 >> i for i in range(8)]))
    s += esc(0x32, 3) + esc(0x33, 0)
    s += esc(0x66, 2, 2, w16(200), w16(16), w16(160), w16(80), w16(200), w16(16), w16(262), w16(80))
    s += esc(0x32, 5)
    s += esc(0x65, 3, 3, w16(330), w16(16), w16(300), w16(50), w16(321), w16(90),
             w16(330), w16(16), w16(371), w16(40), w16(351), w16(90))
    mask = bytes([0xF0, 0x0F, 0xC3] * 16)
    s += esc(0x2B, 0xC9, 1, 5, w16(24), w16(16), w16(len(mask)), mask)
    s += esc(0x32, 6) + esc(0x64, 0xC9, 1, w16(400), w16(20))
    img = bytes([(16 + x * 3 + y * 5) & 0xFF for y in range(16) for x in range(32)])
    s += esc(0x2B, 0xC9, 2, 0, w16(32), w16(16), w16(len(img)), img)
    s += esc(0x67, 0xC9, 2, w16(440), w16(20))
    blob = _icon_blob()
    s += esc(0x2B, 0xC9, 3, 0, w16(len(blob)), w16(1), w16(len(blob)), blob)
    s += esc(0x68, 0xC9, 3, w16(500), w16(20), 0) + esc(0x68, 0xC9, 3, w16(540), w16(20), 1)
    s += esc(0x60, 9, w16(0xF81F)) + esc(0x32, 9) + esc(0x40, w16(8), w16(70)) + esc(0x4A, w16(60), w16(80))
    s += esc(0x61, 10, 3, w16(0x07E0), w16(0xFFE0), w16(0x001F))
    for k in range(3):
        s += esc(0x32, 10 + k) + esc(0x40, w16(70 + 20 * k), w16(70)) + esc(0x4A, w16(85 + 20 * k), w16(80))
    # an overlay, an ANSI terminal in it, and back
    s += esc(0x22, 1, 2, 12, 60, 10, 7, 0)
    s += esc(0x69, 1)
    s += b"\x1b[2J\x1b[1;33mBold yellow\x1b[0m normal\r\n\x1b[44;37m white on blue \x1b[0m\r\n"
    for i in range(12):
        s += b"\x1b[3%dmline %d scrolls the terminal\r\n" % (i % 8, i)
    s += b"\x1b[2;10Hat 2,10\x1b[K" + b"\x1b[31m\x1b[3A^\x1b[2B\x1b[4C>\x1b[2D<" + b"\x1b[9;59HWXYZ!"
    # the 2026-09-16 additions: aixterm's bright ranges and xterm's 256-colour
    # indexed form.  One of 38;5;n / 48;5;n fits a CSI - WT.AnP is four deep -
    # so a pair that sets both is two of them (docs/video-compat.md 6.7)
    s += b"\x1b[2J\x1b[91mbright red\x1b[0m \x1b[102m bright green bg \x1b[0m\r\n"
    s += b"\x1b[38;5;208m208 orange\x1b[0m \x1b[48;5;19m\x1b[38;5;226m226 on 19\x1b[0m\r\n"
    s += b"\x1b[38;5;244mgrey 244\x1b[0m \x1b[38;5;9m9 is bright red\x1b[0m"
    s += b"\x1b" + bytes([0x69, 0]) + esc(0x32, 7) + xy(0, 9) + b"CoWin again"
    return bytes(s)


STREAMS = {"vgp3": stream_p3, "vgp2a": stream_p2a, "vgp2b": stream_p2b, "vgrast": stream_rast, "rastdat": rastdat,
           "vgwave": stream_wave, "wavedat": wavedat, "vggame": stream_game}

# the mouse run's moves, played on PS2_MOUSE after vgp2a: right and up, left and
# down, then far enough right and down that the pointer is clamped at x 639 and
# at the screen's last row, where only its first column and row are on the card
MOVES = [(100, 30), (-20, -100), (127, -127), (127, -127), (127, 0)]


def mouse_bytes(moves):
    """ps2.md 11.3's 3-byte packets, as PS2_MOUSE's hex list."""
    out = []
    for dx, dy in moves:
        b0 = 0x08 | (0x10 if dx < 0 else 0) | (0x20 if dy < 0 else 0)
        out += [b0, dx & 0xFF, dy & 0xFF]
    return " ".join("%02X" % v for v in out)

if __name__ == "__main__":
    if sys.argv[1] == "--emit":
        os.makedirs(sys.argv[2], exist_ok=True)
        for name, fn in STREAMS.items():
            open(os.path.join(sys.argv[2], name), "wb").write(fn())
    elif sys.argv[1] == "--mouse":
        print(mouse_bytes(MOVES))
    elif sys.argv[1] == "--png":
        from PIL import Image
        sys.path.insert(0, os.path.join(HERE, "..", "..", "demo", "tools"))
        import frames as fr
        con = Console()
        con.feed(3, stream_p2a())
        con.feed(4, stream_p2b())
        if sys.argv[2] == "w4":
            con._select(4, con.dev(4))
        Image.fromarray(fr.rgb565_to_rgb8(con.picture())).save(sys.argv[3])
