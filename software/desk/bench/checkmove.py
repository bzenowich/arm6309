#!/usr/bin/env python3
"""checkmove.py desk.asm OUT - milestone 4 read off the PIXELS.

    OUT/frames.bin   the card's output, RGB565, timestamped in picoseconds
    OUT/console.txt  what `desk` said it did
    OUT/drag.ps2     what the mouse was asked to do

⭐ THE GEOMETRY IS PARSED OUT OF desk.asm - FM.X, FM.W, FM.TABH and the four
corners of the travel box - so a change there moves these claims with it.

⭐ AND THE RESTORE IS THE POINT SINCE 2026-09-22.  The drag keeps the
background it covers in an off-screen region (§3.7), so the claim is not "it
left no trail on flat blue" but "every pixel outside the window is the one it
was before the grab" - desktop icons the window was dragged straight over
included.

⛔ AND THE CLAIM THAT MATTERS IS NOT "IT MOVED".  A desktop that ran a canned
curve on a timer would move too; v3drag is exactly that program, and it is
already in this repository.  What is asserted here is that the window went
where the MOUSE went: every position it took is one the PS/2 script put the
pointer at, less the grab offset and clamped by desk's own travel box.  The
negative control is the other half - the same session with a pointer that
crosses the tab and never presses, in which the window must hold exactly ONE
position for the whole run.
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
import frames as fr                                               # noqa: E402
import mktbox as T                                                # noqa: E402

GRABX, GRABY = 60, 9            # ⚠ the same pair mkdragps2.py uses
# ⚠ the directory the session walks into: ~60 real NitrOS-9 commands, which
# is the only listing on this machine that fills the manager's twelve rows.
LISTDIR = os.environ.get("LISTDIR", "/DD/CMDS")
NCLAIM = [0, 0]


def ok(good, what):
    NCLAIM[0] += 1
    if not good:
        NCLAIM[1] += 1
    print("%s  %s" % ("ok   " if good else "FAIL ", what))
    return good


def equates(path):
    S = {}
    txt = open(path, encoding="utf-8", errors="replace").read()
    for m in re.finditer(r"^([A-Za-z][\w.]*)\s+equ\s+(\S+)", txt, re.M):
        name, expr = m.group(1), m.group(2)
        try:
            S[name] = int(eval(re.sub(r"[A-Za-z][\w.]*",
                                      lambda k: str(S[k.group(0)]), expr)))
        except Exception:
            pass
    return S


def to565(c):
    return ((c[0] >> 3) << 11) | ((c[1] >> 2) << 5) | (c[2] >> 3)


def boxes(path, S, desk):
    """(t, bx, by) for every frame in which the window is on screen.

    ⛔ THE WINDOW IS FOUND BY ITS EDGES, NOT BY BEING SOLID.  The obvious test
    - FM.W pixels of not-desktop in a row - is WRONG, and it answered
    confidently for a whole bench run before anyone looked: the list's folder
    and app icons contain C.Desk's own blue, so a row with an icon in it has
    desktop-coloured pixels INSIDE the window.  The count tracked the length
    of the listing (5 entries: 194 rows of 279; 12 entries: 75) and read
    exactly like a window that was not being drawn.
    So a window row is one where a run STARTS at x and another ENDS at
    x+FM.W-1 - the window's two edges against the desktop - whatever the
    pixels between them are.
    ⚠ ONLY THE FRAME'S ROWS ARE FM.W WIDE.  The tab is narrower - the window
    is an L and the desktop shows beside it - so the topmost full-width row is
    the FRAME's top, and the box's top is FM.TABH above it.
    ⚠ And the POINTER can merge with an edge, which costs those rows; the
    threshold below has slack for it.
    """
    W, TAB = S["FM.W"], S["FM.TABH"]
    out = []
    for meta, px in fr.read(path):
        if px is None or px.shape != (S["GEO.SCRH"], S["GEO.SCRW"]):
            continue
        nd = px != desk
        starts = np.zeros_like(nd)
        starts[:, 1:] = nd[:, 1:] & ~nd[:, :-1]
        starts[:, 0] = nd[:, 0]
        ends = np.zeros_like(nd)
        ends[:, :-1] = nd[:, :-1] & ~nd[:, 1:]
        ends[:, -1] = nd[:, -1]
        cand = starts[:, :S["GEO.SCRW"] - W + 1] & ends[:, W - 1:]
        ys, xs = np.nonzero(cand)
        if len(xs) == 0:
            out.append((meta["t"], None, None))
            continue
        # ⛔ THE LONGEST CONTIGUOUS RUN OF ROWS, not the topmost one.  The
        # bracket allows gaps inside (it has to - the list's icons contain
        # C.Desk's blue), so a run that STARTS at x on one object and another
        # that ENDS at x+FM.W-1 on a different one brackets a row that is not
        # the window at all.  With a narrow tab that happens on the tab's own
        # top row and put the window FM.TABH too high.  The frame is FM.H
        # unbroken rows; nothing else on this desktop is.
        best = None
        for x in np.unique(xs):
            r = np.sort(ys[xs == x])
            cut = np.flatnonzero(np.diff(r) != 1)
            for a, b in zip(np.r_[0, cut + 1], np.r_[cut + 1, len(r)]):
                if best is None or b - a > best[0]:
                    best = (b - a, int(x), int(r[a]))
        # ⛔ NEARLY THE WHOLE FRAME, because a PARTLY COPIED one is not a
        # position.  A step is two copies (the tab, then the body) and the
        # body's is 20-40 ms against a 16.7 ms frame, so the raster can catch
        # the body half moved - and the longest contiguous run is then a
        # FRAGMENT whose top is nowhere the window ever was.  At 40 rows of
        # slack that put four positions 29-32 px outside the travel box and
        # read like a drag that had escaped its clamp; at 8 it is 0 of 157.
        if best is None or best[0] < S["FM.H"] - 8:
            out.append((meta["t"], None, None))
            continue
        out.append((meta["t"], best[1], best[2] - TAB))
    return out


def tbox_equ(name):
    """An equate out of tbox.asm - the same discipline checkfiles.py uses on
    TitY: the number lives in the source that owns it."""
    src = open(os.path.join(ROOT, "..", "nitros9", "level2", "arm6309",
                            "modules", "tbox.asm"), errors="replace").read()
    m = re.search(r"^%s\s+equ\s+(\d+)" % re.escape(name), src, re.M)
    if not m:
        sys.exit("FAIL  checkmove: tbox.asm has no %s equate" % name)
    return int(m.group(1))


def icons(deskasm):
    """Every IcTab cell's corner, parsed out of desk.asm - `fcb ACTION,icon`
    then `fdb x,y`.  ⭐ They are what makes the restore claim worth making:
    the drag is meant to cross them, and an icon that does not come back is
    a backing store that did not hold."""
    txt = open(deskasm, encoding="utf-8", errors="replace").read()
    body = txt.split("IcTab", 1)[1]
    return [(int(a), int(b)) for a, b in
            re.findall(r"^\s+fdb\s+(\d+),(\d+)\s*$", body, re.M)]


def ptr_spots(ps2):
    """Every place the script parks the pointer.  ⚠ It is a 16 x 16 SPRITE in
    the picture, so a comparison of two frames has to skip wherever it sat in
    either of them."""
    return [(int(a), int(b)) for a, b in
            re.findall(r"move to (\d+) (\d+)", open(ps2).read())]


def wanted(ps2, S):
    """Every window position the SCRIPT asks for: the pointer it moves to,
    less the grab offset, clamped by desk.asm's own travel box."""
    want = []
    for m in re.finditer(r"move to (\d+) (\d+)", open(ps2).read()):
        px, py = int(m.group(1)), int(m.group(2))
        bx = min(max(px - GRABX, S["FM.MNX"]), S["FM.MXX"])
        by = min(max(py - GRABY, S["FM.MNY"]), S["FM.MXY"])
        want.append((bx, by))
    return want


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: checkmove.py desk.asm OUT")
    deskasm, out = sys.argv[1], sys.argv[2]
    S = equates(deskasm)
    desk = to565(T.palette_rgb()[6])                       # C.Desk
    home = (S["FM.X"], S["FM.Y"] - S["FM.TABH"])
    console = open(os.path.join(out, "console.txt"), errors="replace").read()
    control = bool(os.environ.get("CONTROL"))

    print("      window %d x %d at home (%d, %d); travel box x %d..%d y %d..%d"
          % (S["FM.W"], S["FM.H"] + S["FM.TABH"], home[0], home[1],
             S["FM.MNX"], S["FM.MXX"], S["FM.MNY"], S["FM.MXY"]))

    # ⭐ THE DRAG NOW CROSSES THE ICONS ON PURPOSE.  Until 2026-09-22 the
    # travel box was chosen to avoid them, because the restore was a flat
    # fill; with a real backing store (§3.7) the right claim is the opposite
    # one - that an icon the window passed OVER is still there afterwards.
    sweep = (S["FM.MNX"], S["FM.MXX"] + S["FM.W"],
             S["FM.MNY"], S["FM.MXY"] + S["FM.H"] + S["FM.TABH"])
    ich = 32 + S["GEO.ICONY"]
    over = [c for c in icons(deskasm)
            if c[0] < sweep[1] and c[0] + S["GEO.ICONW"] > sweep[0]
            and c[1] < sweep[3] and c[1] + ich > sweep[2]]
    ok(control or len(over) >= 3,
       "⭐ THE WINDOW'S TRAVEL REACHES %d DESKTOP ICONS - x %d..%d y %d..%d - so "
       "the store is being asked a real question, not a flat blue one"
       % (len(over), sweep[0], sweep[1], sweep[2], sweep[3]))

    # ⛔ THE STORE MUST CLEAR THE TOOLBOX'S GLYPH STRIKE, and both live in the
    # same off-screen margin.  tbox.asm composes text at SK.Col 640 / SK.Row
    # 320; the store is BW x BH at SBX/SBY.  A store that ran past SK.Row ATE
    # THE TEXT - every name in the listing came out as a solid bar, which
    # reads as a font bug and is a memory conflict (2026-09-22).
    sk_row, sk_col = tbox_equ("SK.Row"), tbox_equ("SK.Col")
    clear = (S["SBY"] + S["BH"] <= sk_row) or (S["SBX"] + S["BW"] <= sk_col)
    ok(clear, "⛔ THE BACKING STORE CLEARS tbox.asm's GLYPH STRIKE: the store is "
              "%d x %d at (%d, %d) and the strike starts at (%d, %d) - store ends "
              "at row %d, strike begins at row %d"
       % (S["BW"], S["BH"], S["SBX"], S["SBY"], sk_col, sk_row,
          S["SBY"] + S["BH"], sk_row))

    # ⛔ THE PASTED WIDTH TABLE MUST BE THE ROM'S.  desk.asm carries the bold
    # face's 95 advances so it can work out how wide tbox made its tab -
    # nothing hands that back - and a table that drifted from the font would
    # put the notch in the wrong place, which is a trail beside the title.
    tbl = re.search(r"TBWTab\s+equ\s+\*(.*?)\n\*", 
                    open(deskasm, encoding="utf-8", errors="replace").read(), re.S)
    pasted = [int(v) for m in re.finditer(r"fcb\s+([0-9,]+)", tbl.group(1) if tbl else "")
              for v in m.group(1).split(",")]
    real = T.glyph_widths(bold=True)
    ok(pasted == real, "⛔ desk.asm's PASTED bold widths are the font's own (%d of %d "
                       "entries, %s)" % (len(pasted), len(real),
                                         "identical" if pasted == real else "DRIFTED"))

    bs = boxes(os.path.join(out, "frames.bin"), S, desk)
    seen = [b for b in bs if b[1] is not None]
    pos = [(b[1], b[2]) for b in seen]
    uniq = sorted(set(pos))
    ok(len(seen) > 100, "the manager's window was on the card (%d frames of it)" % len(seen))
    ok(re.search(r"DESK-DIR %s" % re.escape(LISTDIR), console) is not None,
       "⭐ and it had walked into %s, which is the listing the drag carries" % LISTDIR)

    if control:
        # ⛔ THE NEGATIVE CONTROL.  The pointer crosses the tab and never
        # presses, so the window must never move - one picture, all run.
        ok("DESK-GRAB" not in console, "⛔ nothing was grabbed: no DESK-GRAB on the console")
        ok("DESK-DROP" not in console, "⛔ ...and nothing was dropped")
        ok(len(uniq) == 1, "⛔ AND THE WINDOW HELD EXACTLY ONE POSITION (%d seen: %s)"
           % (len(uniq), uniq[:4]))
        ok(uniq[:1] == [home], "⛔ ...and that position is its home, %s" % (home,))
        return report()

    ok("DESK-GRAB" in console, "⭐ the tab was grabbed (DESK-GRAB)")
    ok("DESK-DROP" in console, "⭐ ...and released (DESK-DROP)")
    ok(len(uniq) > 40, "⭐ THE WINDOW MOVED, to %d distinct positions" % len(uniq))

    inbox = [p for p in uniq
             if S["FM.MNX"] <= p[0] <= S["FM.MXX"] and S["FM.MNY"] <= p[1] <= S["FM.MXY"]]
    ok(len(inbox) == len(uniq),
       "⭐ and every one of them is inside desk.asm's own travel box")

    want = set(wanted(os.path.join(out, "drag.ps2"), S))
    hit = len(want & set(uniq))
    # ⛔ THE FRACTION IS OF THE POSITIONS THE WINDOW TOOK, NOT OF THE SAMPLES,
    # and the first form was mis-conditioned in a way that cost a green run.
    #
    # `hit / len(want)` cannot exceed `len(uniq) / len(want)`: the window takes
    # ~87 distinct positions and the script names 150 samples, so the CEILING
    # is 58% and a threshold of 55% sat 3 points under it.  A drag that tracked
    # the pointer perfectly but in slightly coarser steps then "failed" - which
    # is what happened on 2026-09-22, at 51%, on a run whose very next claim
    # says the window was never more than FIVE pixels from a sample.
    #
    # ⭐ Turned round it is well conditioned and says the same thing: of the
    # places the window went, how many are places the pointer was?  A canned
    # curve of desk's own would score near zero on it either way.
    cover = hit / float(len(uniq))
    ok(cover > 0.70, "⭐ AND IT WENT WHERE THE MOUSE WENT: %d of the %d positions it took "
                     "are the script's own samples, %.0f%% - the window followed the "
                     "POINTER, not a curve of its own (%d samples in the script)"
                     % (hit, len(uniq), 100 * cover, len(want)))

    # ⛔ AND THE REST ARE NOT STRAY, THEY ARE IN FLIGHT.  A step's copy is
    # 20-40 ms and a frame is 16.7, so the raster can read the framebuffer
    # while the engine is still moving the window - and a step is capped at
    # Marg (desk.asm's DCap), so a pass that lost time to a re-base lands
    # short of where the pointer already is.  Both put the window BETWEEN two
    # samples.  ⚠ What would not be in flight is a position far from any of
    # them, which is what a canned curve of desk's own would look like.
    marg = S["Marg"]
    far = [p for p in uniq if min(max(abs(p[0] - w[0]), abs(p[1] - w[1]))
                                  for w in want) > marg]
    worst = max(min(max(abs(p[0] - w[0]), abs(p[1] - w[1])) for w in want) for p in uniq)
    ok(not far, "⭐ ...and every other position is one IN FLIGHT between two of them - "
                "none is further than Marg=%d from a sample (worst %d, %d beyond)"
                % (marg, worst, len(far)))

    xs = [p[0] for p in uniq]
    ys = [p[1] for p in uniq]
    ok(max(xs) - min(xs) > 100 and max(ys) - min(ys) > 80,
       "⭐ ...and it is a FIGURE-8 and not a twitch: %d px across, %d px down"
       % (max(xs) - min(xs), max(ys) - min(ys)))

    ok(pos[-1] == home, "⭐ it came home: the last frame has it at %s" % (home,))

    # ⭐ THE WINDOW SURVIVED THE COPIES - its FRAME, which is everything the
    # manager draws except the tab.
    #
    # ⛔ AND THE TWO FRAMES COMPARED ARE THE ONE BEFORE IT LEFT AND THE ONE
    # WHEN IT GOT BACK, not the last frame of the run - because THE POINTER IS
    # IN THE PICTURE.  video3 composites it as a 16 x 16 sprite, the script
    # parks it on the tab to grab and leaves it there after the drop, and at
    # (FM.X+60, FM.Y-10) its bottom six rows reach into the frame.  Comparing
    # the last home frame of all against the last one before the grab compares
    # a picture with the pointer in it against one without: it FAILED on a
    # perfectly good drag, and the CRC it printed differed by exactly the six
    # rows the sprite covers (2026-09-22).  These two moments have the pointer
    # in the same place, so what is left is the window.
    depart = next((t for t, bx, by in seen if (bx, by) != home), None)
    ret = next((t for t, bx, by in reversed(seen) if (bx, by) != home), None)
    crcs = {}
    for meta, px in fr.read(os.path.join(out, "frames.bin")):
        if px is None or px.shape != (S["GEO.SCRH"], S["GEO.SCRW"]):
            continue
        b = [x for x in bs if x[0] == meta["t"]]
        if not b or b[0][1] is None or (b[0][1], b[0][2]) != home:
            continue
        body = px[home[1] + S["FM.TABH"]:home[1] + S["FM.TABH"] + S["FM.H"],
                  home[0]:home[0] + S["FM.W"]]
        if meta["t"] < depart:
            crcs["before"] = zlib.crc32(body.tobytes())
        elif meta["t"] > ret and "after" not in crcs:
            crcs["after"] = zlib.crc32(body.tobytes())
    ok(crcs.get("before") is not None and crcs.get("before") == crcs.get("after"),
       "⭐ AND IT CAME BACK BIT-EXACT: the frame's CRC when it landed is the one "
       "it had before the grab (%08x vs %08x)"
       % (crcs.get("before") or 0, crcs.get("after") or 0))

    # ⛔ THE REAL CLAIM: THE SCREEN OUTSIDE THE WINDOW IS WHAT IT WAS.  Not
    # "no trail" - that was the flat-fill design's question, and a flat fill
    # can only be wrong in one way.  With a backing store the question is
    # whether everything the window was dragged OVER came back, icons and
    # all, so the two frames are compared pixel for pixel everywhere the
    # window is not.
    # ⚠ Less the pointer: it is in the picture, and the script leaves it in a
    # different place at the two moments.
    first = last = None
    for meta, px in fr.read(os.path.join(out, "frames.bin")):
        if px is None or px.shape != (S["GEO.SCRH"], S["GEO.SCRW"]):
            continue
        b = [x for x in bs if x[0] == meta["t"]]
        if not b or b[0][1] is None or (b[0][1], b[0][2]) != home:
            continue
        if meta["t"] < depart and first is None:
            first = px.copy()
        elif meta["t"] > ret:
            last = px.copy()
    mask = np.ones((S["GEO.SCRH"], S["GEO.SCRW"]), bool)
    mask[home[1]:home[1] + S["FM.H"] + S["FM.TABH"], home[0]:home[0] + S["FM.W"]] = False
    for pt in ptr_spots(os.path.join(out, "drag.ps2")):
        y0, x0 = max(0, pt[1] - 2), max(0, pt[0] - 2)
        mask[y0:pt[1] + 20, x0:pt[0] + 20] = False
    bad = int((first[mask] != last[mask]).sum()) if first is not None and last is not None else -1
    ok(bad == 0, "⛔ AND THE SCREEN IT WAS DRAGGED OVER CAME BACK - every pixel "
                 "outside the window is the one it was before the grab (%d differ)" % bad)
    return report()


def report():
    print("\n      %d claims, %d failed" % (NCLAIM[0], NCLAIM[1]))
    sys.exit(1 if NCLAIM[1] else 0)


main()
