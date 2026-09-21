#!/usr/bin/env python3
"""checkdesk.py DESK.ASM OUTDIR - what the desktop shell DREW, joined to what
was clicked at it.

One run of video3/bench/run-v3desk.sh.  Two files go in and are read as one:

    OUTDIR/frames.bin   the card's output, RGB565, timestamped in picoseconds
    OUTDIR/ps2.txt      every PS/2 event, the same clock (emu/ps2script.h)

⭐ THE GEOMETRY IS PARSED OUT OF desk.asm, not repeated here.  `GEO.*` and
the whole of `MTab` are read from the source the machine is running, so a
menu that moves moves the claims with it - and an item renamed, re-ordered
or un-greyed changes what the bench asks for rather than quietly passing.
⭐ AND THE COLOURS COME FROM mktbox.py, which is what wrote the palette into
the ROM.  There is no third transcription of either.

⚠ `hi` IS SAMPLED IN ONE MENU'S COLUMN, THE LAST ONE'S.  The swatch is a few
pixels inside the Applications pull-down's item rectangles - and the Desk
menu's pull-down overlaps that column, so a rest inside *its* second item
reports `hi=1` as well.  That is why every highlight CLAIM names the pointer
position it is asking about: the rest at 168,52 is the Applications item and
the one at 60,52 is Quit, and the bench asks about the first.

⛔ THE POINTER IS IN THE PICTURE.  video3 composites the arrow as a hardware
sprite, so a recorded frame has 16 x 16 pixels of it wherever the mouse is.
Every claim below is therefore made about pixels the sprite is not on, and
the two frames the restore test compares are both taken with the pointer
parked well away from the pull-down (the bench's script says where).

Output, one fact a line, for the shell to make claims from:

    geom <menu> x=<> w=<> y=<> h=<> items=<>
    item <menu> <i> <action> <label>
    frames=<n> barok=<n> barink=<n> open=<n> paint=<n> hiany=<n>
    clicks=<n> rests=<n>
    C<i> t=<s> x=<> y=<> pre=<open|shut> post=<open|shut> chg=<0..100> hi=<set>
    H<i> t=<s> x=<> y=<> hi=<set>
    restore=<ok|bad|na> basecrc=<> postcrc=<>
    paintafter=<i> paintruns=<n> paint0=<s> paint1=<s> deskback=<s>
                            which click Paint followed, how many separate
                            times it was on the card, and when the desktop
                            had repainted itself afterwards
    mg=<ok|bad> mgoff=<dx,dy>   the script's pointer and the machine's,
                            compared packet by packet and at the end

`frames=` also carries `dropcrcs=`: how many DIFFERENT pictures the
pull-down's rectangle ever held once the script started.  ⛔ One is what the
negative control has to show.

⛔ Its exit code is 0 unless a file cannot be read; the facts are the answer
and run-v3desk.sh makes the claims.
"""
import os
import re
import sys
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "software", "demo", "tools"))
sys.path.insert(0, os.path.join(ROOT, "software", "nitros9", "tools"))
import frames as fr                                             # noqa: E402
import mktbox as T                                              # noqa: E402

RGB = T.palette_rgb()
C = {n: T.rgb565(RGB[i]) for n, i in T.PAL.items()}


# ----------------------------------------------------------------- desk.asm
def source(path):
    """GEO.*, the action codes, and MTab - decoded the way desk.asm's MSkip
    walks it, out of the assembler source itself."""
    txt = open(path, encoding="utf-8").read()
    sym = {}
    for m in re.finditer(r"^(\w[\w.]*)\s+equ\s+(\$[0-9A-Fa-f]+|\d+)(?:\s|$)", txt, re.M):
        v = m.group(2)
        sym[m.group(1)] = int(v[1:], 16) if v.startswith("$") else int(v)
    body = txt.split("\nMTab", 1)[1].split("\nNMENU", 1)[0]
    b = bytearray()
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("*"):
            continue
        f = s.split(None, 1)
        if len(f) < 2:
            continue
        op, arg = f[0].lower(), f[1]
        if op not in ("fdb", "fcb", "fcc"):
            continue
        if op == "fcc":
            b += arg[1:arg.index('"', 1)].encode("latin-1")
            continue
        for tok in arg.split(","):
            tok = tok.split()[0].strip()
            v = sym[tok] if tok in sym else (int(tok[1:], 16) if tok.startswith("$") else int(tok))
            b += v.to_bytes(2, "big") if op == "fdb" else bytes([v & 0xFF])
    menus, p = [], 0
    while p < len(b):
        tx, tw, mx, mw = (int.from_bytes(b[p + 2 * k:p + 2 * k + 2], "big") for k in range(4))
        n = b[p + 8]
        p += 9
        ln = b[p]
        title = b[p + 1:p + 1 + ln].decode("latin-1")
        p += 1 + ln
        items = []
        for _ in range(n):
            act = b[p]
            ln = b[p + 1]
            label = b[p + 2:p + 2 + ln].decode("latin-1")
            p += 2 + ln
            ln = b[p]
            mod = b[p + 1:p + 1 + ln].decode("latin-1")
            p += 1 + ln
            items.append((act, label, mod))
        menus.append(dict(tx=tx, tw=tw, mx=mx, mw=mw, title=title, items=items))
    return sym, menus


# ------------------------------------------------------------------ ps2.txt
def ps2(path):
    """⭐ THE `M` LINES, which are where the SCRIPT said the pointer is after
    each packet it sent - so every coordinate below is one the bench author
    wrote, and the claims read literally.  The `G` line (what the machine
    rebuilt out of the bytes it read) is not assumed to agree; mg_agree()
    compares the two, and the highlight claims are what prove the machine's
    own pointer is where the script put it.

    A CLICK is a packet that takes the left button from up to down.
    A REST is a packet with the button up, at a position the packet before it
    was not at, and followed by at least REST seconds of nothing - so it is
    where a move ENDED.  ⚠ The button-up packet of a click sits at the same
    place and is deliberately not one: by then the menu it was clicked on has
    gone, and counting it would make "the highlight is on item 0" ask about a
    menu that is shut."""
    REST = 0.30
    ev = []
    for line in open(path, encoding="latin-1"):
        f = line.split()
        if len(f) < 5 or f[1] != "M":
            continue
        ev.append((int(f[0]) / 1e12, int(f[2]), int(f[3]), int(f[4])))
    clicks, rests = [], []
    for i, (t, x, y, btn) in enumerate(ev):
        pbtn = ev[i - 1][3] if i else 0
        pxy = (ev[i - 1][1], ev[i - 1][2]) if i else None
        if (btn & 1) and not (pbtn & 1):
            clicks.append((t, x, y))
        nxt = ev[i + 1][0] if i + 1 < len(ev) else t + 99
        if nxt - t >= REST and not (btn & 1) and pxy != (x, y):
            rests.append((t, x, y))
    return ev, clicks, rests


def mg_agree(path):
    """⭐ the two pointers, COMPARED.  `skew` counts the packets after which
    the machine's reconstruction moved by a different amount from the script;
    `off` is what is left over at the end.  Either being non-zero means the
    machine did not read what was sent (ps2script.h's own warning)."""
    ms, gs = [], []
    for line in open(path, encoding="latin-1"):
        f = line.split()
        if len(f) >= 5 and f[1] == "M":
            ms.append((int(f[2]), int(f[3])))
        elif len(f) >= 5 and f[1] == "G":
            gs.append((int(f[2]), int(f[3])))
    if not ms or not gs:
        return None, (0, 0)
    n = min(len(ms), len(gs))
    skew = sum(1 for i in range(1, n)
               if (ms[i][0] - ms[i - 1][0], ms[i][1] - ms[i - 1][1])
               != (gs[i][0] - gs[i - 1][0], gs[i][1] - gs[i - 1][1]))
    off = (gs[n - 1][0] - ms[n - 1][0], gs[n - 1][1] - ms[n - 1][1])
    return skew == 0 and off == (0, 0), off


# ------------------------------------------------------------------- frames
def main():
    if len(sys.argv) != 3:
        print("usage: checkdesk.py DESK.ASM OUTDIR", file=sys.stderr)
        return 2
    asm, out = sys.argv[1], sys.argv[2]
    sym, menus = source(asm)
    G = lambda k: sym["GEO." + k]                                # noqa: E731

    # ⚠ THE APPLICATIONS MENU BY NAME, not by position.  It was "the last
    # one" until 2026-09-21, when desk.asm grew a third menu (Go) and every
    # highlight claim below silently moved to it - a bench that follows the
    # source has to follow the menu it means, not the end of the table.
    mi = next((i for i, x in enumerate(menus) if x["title"] == "Applications"),
              len(menus) - 1)
    m = menus[mi]
    dx, dw = m["mx"], m["mw"]
    dy = G("DROPY")
    dh = 2 * G("MPAD") + len(m["items"]) * G("ITEMH")
    # an item's swatch: inside its highlight rectangle and well left of both
    # its text and anything the 16-wide pointer can cover while hovering it
    sx = m["mx"] + G("MPAD") + 4
    sy = [dy + G("MPAD") + G("ITEMH") * i + G("ITEMH") // 2 for i in range(len(m["items"]))]

    print("geom %d x=%d w=%d y=%d h=%d items=%d" % (mi, dx, dw, dy, dh, len(m["items"])))
    for i, (act, label, mod) in enumerate(m["items"]):
        print("item %d %d %d %s %s" % (mi, i, act, label, mod or "-"))

    fpath = os.path.join(out, "frames.bin")
    ppath = os.path.join(out, "ps2.txt")
    if not os.path.exists(fpath):
        print("FAIL  no %s" % fpath, file=sys.stderr)
        return 1
    ev, clicks, rests = ps2(ppath) if os.path.exists(ppath) else ([], [], [])

    # ⚠ THE FIRST EVENT OF ANY KIND, not the first mouse packet: a run whose
    # script only taps a key has no `M` line at all, and `dropcrcs` measured
    # from time zero would count the desktop's own first paint as a change.
    t0 = 0.0
    if os.path.exists(ppath):
        for line in open(ppath, encoding="latin-1"):
            f = line.split()
            if len(f) >= 2 and f[0].isdigit():
                t0 = int(f[0]) / 1e12
                break

    # the instants a rectangle is wanted at, in time order.  A click is looked
    # at just before and well after; a rest, once the drawing has caught up.
    targets = []
    if t0:
        targets.append(("base", max(0.0, t0 - 0.20)))
    for i, (t, x, y) in enumerate(clicks):
        targets.append(("C%d.pre" % i, t - 0.10))
        targets.append(("C%d.post" % i, t + 0.70))
    for i, (t, x, y) in enumerate(rests):
        targets.append(("H%d" % i, t + 0.35))
    targets.sort(key=lambda kv: kv[1])
    got = {}

    n = barok = barink = nopen = npaint = nhiany = 0
    ki = 0
    prev = None
    paint_t = []
    bar_t = []
    basetime = targets[0][1] if targets else 1e9
    dropcrcs = set()
    itab, frame, desk, panel, sel = C["itab"], C["frame"], C["desk"], C["panel"], C["sel"]
    for meta, px in fr.read(fpath):
        n += 1
        t = meta["t"]
        if px is None or px.shape != (G("SCRH"), G("SCRW")):
            continue
        # ⭐ the menu bar, as pixels: its own grey across the width the titles
        # do not reach, one row of frame under it, and the desktop below that
        if ((px[G("BARH") // 2, 250:600] == itab).all()
                and (px[G("RULEY"), 250:600] == frame).all()
                and (px[G("RULEY") + 7, 250:600] == desk).all()):
            barok += 1
            bar_t.append(t)
        ink = px[2:G("BARH") - 2, 4:max(x["tx"] + x["tw"] for x in menus)]
        if int(((ink != itab) & (ink != sel)).sum()) >= 30:
            barink += 1
        rect = px[dy:dy + dh, dx:dx + dw]
        if float((rect == panel).mean()) > 0.40:
            nopen += 1
        if t >= basetime:
            # ⛔ the negative control's whole claim: how many DIFFERENT
            # pictures the pull-down's rectangle ever held once the script
            # started.  One means the desktop drew a menu for nobody.
            dropcrcs.add(zlib.crc32(rect.tobytes()))
        hi = [i for i, yy in enumerate(sy) if px[yy, sx] == sel]
        if hi:
            nhiany += 1
        # Paint's page: a third of the screen pure white, under Haiku chrome
        vals = np.unique(px)
        if vals.size >= 40 and float((px == 0xFFFF).mean()) >= 0.20:
            npaint += 1
            paint_t.append(t)
        while ki < len(targets) and t > targets[ki][1]:
            got[targets[ki][0]] = prev
            ki += 1
        prev = rect.copy()
    while ki < len(targets):
        got[targets[ki][0]] = prev
        ki += 1

    def state(r):
        if r is None:
            return "na"
        return "open" if float((r == panel).mean()) > 0.40 else "shut"

    def hiset(r):
        if r is None:
            return "-"
        s = [str(i) for i, yy in enumerate(sy) if r[yy - dy, sx - dx] == sel]
        return ",".join(s) if s else "-"

    def crc(r):
        return "na" if r is None else "%08x" % zlib.crc32(r.tobytes())

    print("frames=%d barok=%d barink=%d open=%d paint=%d hiany=%d dropcrcs=%d"
          % (n, barok, barink, nopen, npaint, nhiany, len(dropcrcs)))
    print("clicks=%d rests=%d" % (len(clicks), len(rests)))
    for i, (t, x, y) in enumerate(clicks):
        a, b = got.get("C%d.pre" % i), got.get("C%d.post" % i)
        chg = 0
        if a is not None and b is not None and a.shape == b.shape:
            chg = int(round(100 * float((a != b).mean())))
        print("C%d t=%.3f x=%d y=%d pre=%s post=%s chg=%d hi=%s"
              % (i, t, x, y, state(a), state(b), chg, hiset(b)))
    for i, (t, x, y) in enumerate(rests):
        r = got.get("H%d" % i)
        print("H%d t=%.3f x=%d y=%d hi=%s" % (i, t, x, y, hiset(r)))

    base, post = got.get("base"), got.get("C1.post")
    r = "na"
    if base is not None and post is not None:
        r = "ok" if crc(base) == crc(post) else "bad"
    print("restore=%s basecrc=%s postcrc=%s" % (r, crc(base), crc(post)))

    # ⭐ WHICH CLICK PAINT FOLLOWED, and it is the LAST click before Paint's
    # first frame rather than the first click Paint eventually followed: a
    # window wide enough to cover a 20-second child is wide enough to reach
    # back over every click before it, which is how this read "click 1" of a
    # launch that click 3 made.  `paintruns` is how many separate times
    # Paint's picture was on the card - one launch, one run.
    after, runs, last = -1, 0, -9
    for pt in paint_t:
        if pt - last > 1.0:
            runs += 1
        last = pt
    if paint_t:
        before = [i for i, (t, x, y) in enumerate(clicks) if t < paint_t[0]]
        after = before[-1] if before else -1
    # ⭐ AND WHEN, which is what a bench has to know to time its script: a
    # child owns the screen while it runs and the desktop is asleep in
    # F$Wait, so a click sent between paint0 and deskback reaches nobody.
    # deskback is the first frame AFTER the child in which the menu bar is
    # drawn correctly again - the desktop's own repaint, finished.
    p0 = paint_t[0] if paint_t else -1
    p1 = paint_t[-1] if paint_t else -1
    back = next((t for t in bar_t if t > p1), -1) if paint_t else -1
    print("paintafter=%d paintruns=%d paint0=%.3f paint1=%.3f deskback=%.3f"
          % (after, runs, p0, p1, back))
    g, off = mg_agree(ppath) if os.path.exists(ppath) else (None, (0, 0))
    print("mg=%s mgoff=%d,%d" % ("na" if g is None else ("ok" if g else "bad"), off[0], off[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
