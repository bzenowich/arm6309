#!/usr/bin/env python3
"""checkfiles.py DESK.ASM OUTDIR NAMES - what the file manager LISTED, read
off the card's own pixels.

One run of software/desk/bench/run-v3files.sh.  Three files go in:

    OUTDIR/frames.bin   the card's output, RGB565, timestamped in picoseconds
    OUTDIR/ps2.txt      every PS/2 event, the same clock (emu/ps2script.h)
    NAMES               every name that is anywhere on the SD image, one a
                        line, as the HOST's `os9 dir` reads it

⭐ THE LIST IS READ, NOT ASSUMED.  Every row of the window is matched against
the rendered glyphs of each candidate name, and the candidates come from the
image rather than from this file - so what is printed below is what the
machine DREW, and run-v3files.sh is what compares it with what `os9 dir`
says is there.  A row that matches nothing prints `?`, which fails a claim
rather than passing an empty one.

⭐ THE GLYPHS ARE THE ROM'S OWN.  mktbox.py's font_blob() is what wrote the
two fonts into ROM pages 65 on; this parses that blob (4-byte head, 95 x
(width, offset), then rows two bits a pixel) and rebuilds each glyph's level
array.  There is no second rasteriser, and a font change moves the bench
with the ROM.  A text pixel of level L is RAMP + L - 1 (mktbox.py RAMPS) and
tbox.asm's text is transparent, so level 0 is the paper and is not compared.

⭐ AND THE GEOMETRY IS PARSED OUT OF desk.asm - `GEO.*` and `FM.*` both, so
a window that moves moves the claims with it.

⛔ THE POINTER IS IN THE PICTURE.  video3 composites the arrow as a 16 x 16
hardware sprite whose hot spot is its top left, so a frame has 16 x 16 pixels
of it wherever the mouse is.  Two defences, and the negative control needs
both: every SAMPLE is taken at an instant the script has parked the pointer
off the window, and `listcrcs` - how many different pictures the list ever
held - counts only frames in which the sprite is clear of the list and the
pointer has been still for SETTLE seconds.

Output, one fact a line, for the shell to make claims from:

    geom ...                     the window, from desk.asm
    frames=<n> chrome=<n> listcrcs=<n> paint=<n> mg=<ok|bad>
    clicks=<n> rests=<n>
    C<i> t=<s> x=<> y=<>         every click the script sent
    S<i> t=<s> win=<yes|no> title=<s> items=<s> sel=<i|-> rows=<a,b,...>
                                 the window 3 s after click <i>
    SE  t=<s> ...                and at the end of the run
    paint0=<s> paint1=<s> deskback=<s>

⛔ Its exit code is 0 unless a file cannot be read; the facts are the answer.
"""
import os
import re
import sys
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "software", "tools"))
sys.path.insert(0, os.path.join(ROOT, "software", "toolbox", "tools"))
import frames as fr                                             # noqa: E402
import mktbox as T                                              # noqa: E402

RGB = T.palette_rgb()
C = {n: T.rgb565(RGB[i]) for n, i in T.PAL.items()}
SAMPLE = float(os.environ.get("SAMPLE_AT", "3.0"))   # after a click
# ⛔ 1.5 s, AND IT IS A LAG AND NOT A HABIT.  `desk` moves the hardware sprite
# once a loop pass, so the POINTER ARRIVES AFTER THE SCRIPT SAYS IT DID - and
# the `clear` test below believes the SCRIPT's coordinates, because nothing
# tells this checker where the card actually put the sprite.  On 2026-09-22 a
# recording showed the arrow still sitting in the list rectangle **1.2 s**
# after the script had parked it at (580, 300): ONE frame out of 532, counted
# as a second "picture" of a list that had not been touched.
# ⚠ A longer settle is only safe because it is not vacuous - `listn` below is
# printed and the bench claims a floor on it.  At 1.5 s that run kept 106
# frames; at 0.35 it kept 532 and two of them disagreed.
SETTLE = 1.5                                         # after a mouse packet
# ⚠ WHERE A ROW'S TEXT SITS INSIDE ITS 18-PIXEL ROW, and desk and v3trk do
# not agree: desk.asm's DrawRow puts the icon AND the name at row + 1, and
# v3trk.asm's Entry puts the icon at row + 1 and the name at row + 0 (it
# pushes ly + r * RowH for the text and adds one only for the icon).  One
# pixel, invisible to anyone reading the screen and fatal to a matcher that
# compares glyph rasters - so the run that drives v3trk passes ROW_DY=0.
ROW_DY = int(os.environ.get("ROW_DY", "1"))


def ramp565(name):
    """the three palette words a ramp's levels 1, 2 and 3 are drawn in"""
    b = T.RAMP[name]
    return [T.rgb565(RGB[b + k]) for k in range(3)]


# ----------------------------------------------------------------- desk.asm
def source(path):
    """every `X equ <number-or-expression-of-numbers>` desk.asm declares,
    resolved in order - FM.LY is FM.CY+FM.HH and both are wanted."""
    txt = open(path, encoding="utf-8").read()
    sym = {}
    for m in re.finditer(r"^([A-Za-z][\w.]*)\s+equ\s+(\S+)", txt, re.M):
        e = m.group(2)
        if not re.fullmatch(r"[$0-9A-Za-z_.+\-*/]+", e):
            continue
        py = re.sub(r"\$([0-9A-Fa-f]+)", lambda k: str(int(k.group(1), 16)), e)
        py = re.sub(r"[A-Za-z][\w.]*", lambda k: "sym['%s']" % k.group(0), py)
        try:
            sym[m.group(1)] = int(eval(py, {"sym": sym}))       # noqa: S307
        except Exception:
            pass
    return sym


# -------------------------------------------------------------------- fonts
def font(bold):
    """mktbox.py's own blob, decoded: chr -> a (h, w) array of 0..3"""
    blob, _ = T.font_blob(os.path.join(T.FONT_DIR,
                                       "NotoSans-Bold.ttf" if bold else "NotoSans-Regular.ttf"))
    h, _asc, first, count = blob[0], blob[1], blob[2], blob[3]
    g = {}
    # ⚠ FIVE bytes an entry since 2026-09-21: width, the rows' offset, and the
    # 2-byte strike position mktbox.py bakes in (strike_layout).
    for i in range(count):
        w = blob[4 + 5 * i]
        off = int.from_bytes(blob[5 + 5 * i:7 + 5 * i], "big")
        bpr = (w + 3) // 4
        lv = np.zeros((h, w), np.uint8)
        for y in range(h):
            row = blob[off + y * bpr: off + y * bpr + bpr]
            vals = []
            for by in row:
                vals += [(by >> 6) & 3, (by >> 4) & 3, (by >> 2) & 3, by & 3]
            lv[y] = vals[:w]
        g[chr(first + i)] = lv
    return g, h


def render(s, g, h):
    """tbox.asm's TextAt: each glyph at the pen, the pen advanced by its
    clipped width (which is what TextW sums, and what mktbox.py stored)"""
    cols = [g[c] for c in s if c in g]
    if not cols:
        return np.zeros((h, 0), np.uint8)
    return np.concatenate(cols, axis=1)


def levels(band, ramp):
    """a picture -> the text levels in it, 0 where it is not this ramp's ink"""
    out = np.zeros(band.shape, np.uint8)
    for k, v in enumerate(ramp):
        out[band == v] = k + 1
    return out


def tbox_equ(name):
    """An equate out of tbox.asm - the same discipline checkdesk.py uses on
    desk.asm's GEO.*: the number lives in the source that draws it."""
    nd = os.environ.get("NITROS9DIR") or os.path.join(ROOT, "..", "nitros9")
    src = open(os.path.join(nd, "level2", "arm6309", "modules", "tbox.asm")).read()
    m = re.search(r"^%s\s+equ\s+(\d+)" % re.escape(name), src, re.M)
    if not m:
        sys.exit("FAIL  checkfiles: tbox.asm has no %s equate" % name)
    return int(m.group(1))


def match(band, cands, g, h, ramp):
    """the candidate whose glyphs ARE these pixels, or '' for blank, or '?'.
    ⚠ The three columns after the match have to be blank too, or `desk`
    matches the first four glyphs of `deskbar`."""
    lv = levels(band, ramp)
    if not lv.any():
        return ""
    for name in cands:
        r = render(name, g, h)
        w = r.shape[1]
        if w + 3 > lv.shape[1]:
            continue
        if (lv[:, :w] == r).all() and not lv[:, w:w + 3].any():
            return name
    return "?"


# ------------------------------------------------------------------ ps2.txt
def ps2(path):
    ev = []
    if os.path.exists(path):
        for line in open(path, encoding="latin-1"):
            f = line.split()
            if len(f) >= 5 and f[1] == "M":
                ev.append((int(f[0]) / 1e12, int(f[2]), int(f[3]), int(f[4])))
    clicks, rests = [], []
    for i, (t, x, y, btn) in enumerate(ev):
        pbtn = ev[i - 1][3] if i else 0
        pxy = (ev[i - 1][1], ev[i - 1][2]) if i else None
        if (btn & 1) and not (pbtn & 1):
            clicks.append((t, x, y))
        nxt = ev[i + 1][0] if i + 1 < len(ev) else t + 99
        if nxt - t >= 0.30 and not (btn & 1) and pxy != (x, y):
            rests.append((t, x, y))
    return ev, clicks, rests


def mg_agree(path):
    ms, gs = [], []
    if os.path.exists(path):
        for line in open(path, encoding="latin-1"):
            f = line.split()
            if len(f) >= 5 and f[1] == "M":
                ms.append((int(f[2]), int(f[3])))
            elif len(f) >= 5 and f[1] == "G":
                gs.append((int(f[2]), int(f[3])))
    if not ms or not gs:
        return None
    n = min(len(ms), len(gs))
    skew = sum(1 for i in range(1, n)
               if (ms[i][0] - ms[i - 1][0], ms[i][1] - ms[i - 1][1])
               != (gs[i][0] - gs[i - 1][0], gs[i][1] - gs[i - 1][1]))
    return skew == 0 and gs[n - 1] == ms[n - 1]


def main():
    # ⭐ the geometry, for the shell: it drives v3trk into the SAME rectangle
    # desk.asm's manager uses, and neither may transcribe the numbers
    if len(sys.argv) == 3 and sys.argv[1] == "--geom":
        for k, v in sorted(source(sys.argv[2]).items()):
            if k.startswith(("FM.", "GEO.")):
                print("%s=%d" % (k.replace(".", "_"), v))
        # ⚠ and the two tab colours, from mktbox.py - the shell asks whether
        # the window the manager drew is the ACTIVE one, and C.Tab against
        # C.ITab is what tbox.asm's TWin decides that with
        print("PAL_TAB=%d\nPAL_ITAB=%d" % (T.PAL["tab"], T.PAL["itab"]))
        return 0
    if len(sys.argv) != 4:
        print("usage: checkfiles.py DESK.ASM OUTDIR NAMES", file=sys.stderr)
        return 2
    asm, out, namefile = sys.argv[1], sys.argv[2], sys.argv[3]
    S = source(asm)
    cands = [l.strip() for l in open(namefile) if l.strip()]
    cands.sort(key=len, reverse=True)           # the longest match wins

    WX, WY, WW, WH = S["FM.X"], S["FM.Y"], S["FM.W"], S["FM.H"]
    TOP = WY - 19                               # the tab is above the frame
    print("geom x=%d y=%d w=%d h=%d lx=%d ly=%d lw=%d lh=%d rows=%d rowh=%d"
          % (WX, WY, WW, WH, S["FM.LX"], S["FM.LY"], S["FM.LW"], S["FM.LH"],
             S["FM.ROWS"], S["FM.ROWH"]))

    TITY = tbox_equ("TitY")
    print("title row: TitY=%d" % TITY)
    reg = font(False)
    bld = font(True)
    rWhite, rSel, rPanel, rTab = (ramp565("white"), ramp565("sel"),
                                  ramp565("panel"), ramp565("tab"))

    # the list rectangle, in screen pixels: what the control says never moves
    LRECT = (S["FM.LY"], S["FM.LY"] + S["FM.LH"], S["FM.LX"], S["FM.LX"] + S["FM.LW"])

    def sub(px):                                # the window, tab and all
        return px[TOP:WY + WH, WX:WX + WW].copy()

    idx_of = {}
    for i in range(256):
        idx_of.setdefault(T.rgb565(RGB[i]), i)

    def _idx(v):
        return idx_of.get(int(v), -1)

    def readwin(w):
        """title, "N items", the selected row and every row, off the pixels"""
        if w is None:
            return dict(win="no", title="-", items="-", sel="-", rows="-", tab="-")
        # ⚠ COLUMNS RELATIVE TO FM.W, NOT LITERALS.  This sampled column 300,
        # which is inside a 420-wide window and OFF THE END of the 284-wide
        # one FM.W became on 2026-09-22 - numpy indexed past the crop and
        # every claim that needed the window reported "0 frames", which reads
        # like a machine that drew nothing rather than a bench that moved.
        ok = (w[19, 0] == C["shadow"] and w[19 + 4, WW // 4] == C["frame"]
              and w[19 + 10, WW // 2] == C["panel"])
        # ⚠ the title is BOLD and in the tab's ramp (tbox.asm TWin), and its
        # row comes from tbox.asm's own TitY rather than being repeated here -
        # it moved from 18 to 17 when the tab went flat and the title dropped
        # below C.Pale's highlight row, and a hard-coded 18 failed 8 claims.
        ty, tx = 19 - TITY, 26
        title = match(w[ty:ty + bld[1], tx:tx + WW - tx - 2], cands + PATHS, *bld, rTab)
        sy = S["FM.SY"] - TOP + 1
        sx = S["FM.CX"] - WX + 6
        items = match(w[sy:sy + reg[1], sx:sx + 90], COUNTS, *reg, rPanel)
        rows, sel = [], "-"
        for i in range(S["FM.ROWS"]):
            y = S["FM.LY"] - TOP + i * S["FM.ROWH"] + ROW_DY
            x = S["FM.LX"] - WX + S["FM.TX"]
            band = w[y:y + reg[1], x:x + S["FM.LW"] - S["FM.TX"] - 2]
            n = match(band, cands, *reg, rWhite)
            if n == "" or n == "?":
                m = match(band, cands, *reg, rSel)
                if m not in ("", "?"):
                    n, sel = m, str(i)
            if n:
                rows.append(n)
        return dict(win="yes" if ok else "no", title=title or "-",
                    items=(items or "-").replace(" ", "_"), sel=sel,
                    rows=",".join(rows) or "-", tab=str(_idx(w[6, 8])))

    fpath = os.path.join(out, "frames.bin")
    ppath = os.path.join(out, "ps2.txt")
    if not os.path.exists(fpath):
        print("FAIL  no %s" % fpath, file=sys.stderr)
        return 1
    ev, clicks, rests = ps2(ppath)

    # the paths a title can be, and the counts a status line can be: both are
    # derived from the candidate names, never typed
    PATHS = sorted({"/SD0"} | {"/SD0/" + n for n in cands}, key=len, reverse=True)
    COUNTS = ["%d+ items" % n for n in range(100)] + ["%d items" % n for n in range(100)]
    COUNTS.sort(key=len, reverse=True)

    # ⚠ TWO INSTANTS A CLICK, and the EARLIER one is what says the window
    # came back after a child owned the screen: the run ends with `desk`
    # exited and its window gone, so the LAST frame is not that evidence.
    targets = [("A%d" % i, t - 1.0) for i, (t, x, y) in enumerate(clicks)]
    targets += [("S%d" % i, t + SAMPLE) for i, (t, x, y) in enumerate(clicks)]
    targets.append(("SE", 1e8))
    targets.sort(key=lambda kv: kv[1])
    got, ki, prev = {}, 0, None

    n = nchrome = npaint = nrestin = 0
    paint_t, desk_t = [], []
    listcrcs = set()
    listn = 0
    for t, x, y in rests:
        if LRECT[2] <= x < LRECT[3] and LRECT[0] <= y < LRECT[1]:
            nrestin += 1
    for meta, px in fr.read(fpath):
        n += 1
        t = meta["t"]
        if px is None or px.shape != (S["GEO.SCRH"], S["GEO.SCRW"]):
            continue
        w = sub(px)
        chrome = (w[19, 0] == C["shadow"] and w[19 + 4, 100] == C["frame"]
                  and w[19 + 10, 300] == C["panel"])
        if chrome:
            nchrome += 1
        # the menu bar, as run-v3desk.sh reads it: the desktop is itself again
        bar = ((px[S["GEO.BARH"] // 2, 250:600] == C["itab"]).all()
               and (px[S["GEO.RULEY"], 250:600] == C["frame"]).all())
        if bar:
            desk_t.append(t)
        # ⛔ Paint's page: a fifth of the screen pure white and NEITHER THE
        # DESKTOP NOR THE MANAGER under it.  run-v3desk.sh's detector was the
        # white alone, and this bench's own file manager - a 396 x 216 white
        # list, 28% of the screen - satisfied it on every frame the window
        # was up.  A child takes the screen with DWSet, so "the bar is gone"
        # separates Paint's picture from the desktop's; and the boot dialog,
        # which is also white and also has no bar, is excluded by requiring
        # the desktop to have existed first.
        # ⛔ AND THE CHROME TEST IS NOT REDUNDANT: A FULL-SCREEN REPAINT IS
        # NOT ATOMIC.  DrawAll fills 640 x 480 with the desktop colour from
        # the top down, so a frame caught in the middle of the repaint after
        # Go > Close has the menu bar already gone and the old list still
        # white - 28% of the screen, no bar, and it read as Paint at 114 s of
        # a run whose Paint was at 174.  The window's frame is still intact
        # in that same frame, which is what tells the two apart.
        if (desk_t and not bar and not chrome and np.unique(px).size >= 40
                and float((px == 0xFFFF).mean()) >= 0.20):
            npaint += 1
            paint_t.append(t)
        # ⛔ the list's pictures, counted only where the sprite cannot be on
        # it and the pointer has been still
        p = [e for e in ev if e[0] <= t]
        if p and t - p[-1][0] >= SETTLE:
            _, mxp, myp, _ = p[-1]
            clear = (mxp + 16 <= LRECT[2] or mxp >= LRECT[3]
                     or myp + 16 <= LRECT[0] or myp >= LRECT[1])
            if clear:
                listcrcs.add(zlib.crc32(px[LRECT[0]:LRECT[1], LRECT[2]:LRECT[3]].tobytes()))
                listn += 1
        while ki < len(targets) and t > targets[ki][1]:
            got[targets[ki][0]] = prev
            ki += 1
        prev = w
    while ki < len(targets):
        got[targets[ki][0]] = prev
        ki += 1

    print("frames=%d chrome=%d listcrcs=%d listn=%d paint=%d mg=%s"
          % (n, nchrome, len(listcrcs), listn, npaint,
             {None: "na", True: "ok", False: "bad"}[mg_agree(ppath)]))
    print("clicks=%d rests=%d restsin=%d" % (len(clicks), len(rests), nrestin))
    for i, (t, x, y) in enumerate(clicks):
        print("C%d t=%.3f x=%d y=%d" % (i, t, x, y))
    for k in [k for k, _ in targets]:
        r = readwin(got.get(k))
        tt = dict(targets).get(k, -1)
        print("%s t=%.3f win=%s tab=%s title=%s items=%s sel=%s rows=%s"
              % (k, -1 if tt > 1e7 else tt, r["win"], r["tab"], r["title"],
                 r["items"], r["sel"], r["rows"]))
    # ⚠ THE LONGEST RUN, not the first frame.  A child owns the screen for
    # tens of seconds; anything shorter is the card caught between two
    # pictures, and "when did Paint start" has to be the run and not a blip.
    runs, cur = [], []
    for t in paint_t:
        if cur and t - cur[-1] > 1.0:
            runs.append(cur)
            cur = []
        cur.append(t)
    if cur:
        runs.append(cur)
    best = max(runs, key=len) if runs else []
    p0 = best[0] if best else -1
    p1 = best[-1] if best else -1
    back = next((t for t in desk_t if t > p1), -1) if best else -1
    print("paint0=%.3f paint1=%.3f deskback=%.3f paintruns=%d"
          % (p0, p1, back, len(runs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
