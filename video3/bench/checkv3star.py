#!/usr/bin/env python3
"""checkv3star.py OUT [OUT2 ...] - the stardew scene's gates, budget and sheets.

Each OUT is one emulator run of `stardew` (video3/bench/run-v3star.sh) holding
marks.txt, and usually frames.bin and vram.bin.  This makes four different
kinds of claim, and ⭐ two of them are new to this scene:

  ⛔ THE VRAM GATE.  The farm is decided by DATA: every byte of ring rows
     0..479 is stardew.pic, with exactly the crop stages the scene's own
     retirement count says it grew - so the world is rebuilt here and
     compared byte for byte, the keyed art bank with it.  A dropped restore,
     a save taken from the wrong row, a keyed copy that wrote its holes or a
     crop at the wrong stage each fail it.

  ⭐ THE PALETTE GATE, WHICH NO OTHER SCENE HERE NEEDED.  ⛔ A DAY CYCLE
     TOUCHES NO VRAM AT ALL, so the gate above is structurally blind to the
     entire headline feature.  The LUT is read off the RECORDING instead, and
     it is read INDEX BY INDEX rather than by hunting for a colour: the world
     is known, the camera is in the marks, so for a recorded frame every
     pixel's palette index is known - and the MODAL colour of an index's
     pixels IS what the card's LUT held for it.  That is then compared with
     the tint the driver should have reached, which the marks also say,
     because the commit cursor is reported every frame.
     ⛔ With a negative control: a run with the cycle disabled (mode b0) must
     read the AUTHORED palette at every checkpoint and no other.

  ⛔ THE COMPOUNDING GATE.  stardew.md §2: the tint must be applied to the
     AUTHORED colour, never to the current one, or it compounds and the world
     converges on black over a thousand frames - a drift that looks like a
     slow bug and is nearly invisible in a contact sheet.  The scene ends by
     pinning the day at noon and putting every entry back through the same
     arithmetic at unity gain, and after that the LUT must be the authored
     palette BIT FOR BIT.  `stardew`'s mode b5 is the mutation that breaks it.

  ⭐ THE BUDGET and ⛔ THE TEARING GATE, as monster and pinball keep them: the
     $FF2E marks timestamped in picoseconds, and "the scroll pair AND the
     frame's LUT writes reached the card inside the blank" read off the
     recording rather than argued.

⛔ Its exit code is the answer.

  --gate-must-fail   the run is a MUTATION and THE GATE ITS MODE BELONGS TO
                     is required to catch it - the VRAM gate for a dropped
                     restore or a skipped Wipe (b6, b3), the compounding gate
                     for a tint that compounds (b5).  ⚠ The OTHER gate must
                     still pass: a palette mutation that also broke VRAM
                     would mean the two are not measuring different things.
                     This is what makes the gates worth anything (CLAUDE.md:
                     a green check proves nothing on its own).
"""
import base64
import bisect
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "software", "demo", "tools"))
import frames as fr  # noqa: E402

# stardew.asm's marks
M_FRAME, M_SCROLL, M_LUT, M_SPRITE = 0x10, 0x11, 0x12, 0x13
M_LOGIC, M_PREP, M_ACTORS, M_CROPS, M_SCALL = 0x14, 0x1F, 0x15, 0x16, 0x17
M_BEGIN, M_LAST, M_WIPED, M_SETTLED, M_LOADED = 0x18, 0x19, 0x1A, 0x1B, 0x1C
M_NOBLANK, M_NOLUT = 0x1E, 0x1D
M_POLL0, M_ACT0 = 0x40, 0x60
M_CXH, M_CXL, M_CYH, M_CYL, M_NIB = 0x80, 0xA0, 0xC0, 0xE0, 0xF0

BUDGET_MS = 14.27                   # VMODE 00
SYNCMS = 2.0
NCHECK = int(os.environ.get("NCHECK", "12"))     # palette checkpoints in the run
NSETCHK = int(os.environ.get("NSETCHK", "4"))    # ... and after the settle
MINPIX = 24                         # an index needs this many visible pixels
MODEFRAC = 0.60                     # ... and this much of them must agree
SHEET_EVERY = float(os.environ.get("SHEET_EVERY", "0.9"))
COLS, ROWS = 4, 5

# ⚠ `restore` is the restore phase AND the crop retirement, because the crop
# has to land between the restores and the saves (stardew.asm Actors) - and
# `actors` is then the saves and the draws.
PHASES = [("scroll", M_FRAME, M_SCROLL), ("lut", M_SCROLL, M_LUT),
          ("sprite", M_LUT, M_SPRITE), ("logic", M_SPRITE, M_LOGIC),
          ("tint", M_LOGIC, M_PREP), ("restore", M_PREP, M_CROPS),
          ("actors", M_CROPS, M_ACTORS), ("oscall", M_ACTORS, M_SCALL)]

# ⚠ SCREEN RECTANGLES THE PALETTE GATE DOES NOT READ, and each has a reason.
# The HUD is blitted at (8, 8) of the view every frame and this card has ONE
# buffer, so the rows the raster has already passed still hold the PREVIOUS
# frame's HUD at the previous camera - a smear that is correct behaviour and
# is not a rendering of the world.  The farmer is the hardware sprite, which
# is composited over the picture and is not a palette index at all; his
# screen position is bounded by the camera's own clamp (stardew.asm SprReg).
MASKS = [(0, 0, 200, 48), (296, 84, 44, 36)]     # x, y, w, h


def unpack565(v):
    v = int(v)
    r5, g6, b5 = v >> 11, (v >> 5) & 63, v & 31
    return ((r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2))


# ─────────────────────── ⭐ the tint contract, the other implementation
def chan(c, g, o, d, s):
    v = (c * g) >> 7
    if v > 255:
        v = 255
    v += o
    if v > 255:
        v = 255
    v += d
    if v > 255:
        v = 255
    return v >> s


def pipeline(c8, coef, bias):
    gr, gg, gb, orr, og, ob = coef
    dr, dg, db = bias & 7, (bias >> 3) & 3, (bias >> 5) & 7
    return ((chan(c8[0], gr, orr, dr, 3) << 11) |
            (chan(c8[1], gg, og, dg, 2) << 5) |
            chan(c8[2], gb, ob, db, 3))


def lut_at(j, phase):
    """⭐ The 200 art words the driver should hold if every entry were at this
    phase.  The scene's own schedule means they are not all at one phase, so
    the gate uses `expected_lut` below - this is for the settle, where they
    are."""
    coef = j["tint"][phase]
    return [pipeline(j["auth"][i], coef, j["bias"][i]) for i in range(j["nart"])]


# ───────────────────────────────────────────────────────────── marks.txt
def read_marks(path):
    V, A, M = [], [], []
    for line in open(path):
        # ⚠ THE LAST LINE CAN BE HALF A LINE: the emulator stops on
        # SERIAL_STOP and does not always flush marks.txt's tail.
        f = line.split()
        if len(f) != 2:
            continue
        a, tag = f
        try:
            t = int(a)
        except ValueError:
            continue
        if tag == "V":
            V.append(t)
        elif tag == "A":
            A.append(t)
        elif tag[0] == "M":
            M.append((t, int(tag[1:])))
    return V, A, M


def frames_of(M):
    """One dict a frame: the phase timestamps, the actor count, the camera,
    ⭐ the day's phase and the commit cursor, and how many card frames the
    poll waited."""
    out, cur = [], None
    cam = [0, 0, 0, 0]
    for t, v in M:
        if v == M_FRAME:
            if cur is not None and M_SCALL in cur:
                out.append(cur)
            cur = {M_FRAME: t, "nib": []}
        elif cur is None:
            continue
        elif v in (M_SCROLL, M_LUT, M_SPRITE, M_LOGIC, M_PREP, M_ACTORS,
                   M_CROPS, M_SCALL):
            cur[v] = t
        elif v == M_NOBLANK:
            cur["declined"] = True
        elif v == M_NOLUT:
            cur["lutshort"] = True
        elif M_ACT0 <= v < M_ACT0 + 32:
            cur["n"] = v - M_ACT0
        elif M_POLL0 <= v < M_POLL0 + 32:
            cur["waited"] = v - M_POLL0
        elif M_CXH <= v < M_CXH + 32:
            cam[0] = v - M_CXH
        elif M_CXL <= v < M_CXL + 32:
            cam[1] = v - M_CXL
        elif M_CYH <= v < M_CYH + 32:
            cam[2] = v - M_CYH
        elif M_CYL <= v < M_CYL + 16:
            cam[3] = v - M_CYL
            cur["camx"] = (cam[0] << 5) | cam[1]
            cur["camy"] = (cam[2] << 4) | cam[3]
        elif M_NIB <= v < M_NIB + 16:
            cur["nib"].append(v - M_NIB)
            if len(cur["nib"]) == 4:
                a, b, c, d = cur["nib"]
                cur["phase"] = (a << 4) | b
                cur["cursor"] = (c << 4) | d
    if cur is not None and M_SCALL in cur:
        out.append(cur)
    return out


def cropcount(M):
    """The four nibble marks in $00..$0F the scene emits after its Wipe."""
    nib = [v for _, v in M if v < 16]
    if len(nib) < 4:
        return None
    nib = nib[-4:]
    return (nib[0] << 12) | (nib[1] << 8) | (nib[2] << 4) | nib[3]


def mode_name(v):
    if v is None:
        return "?"
    bits = ["⛔ THE CONTROL: no day cycle at all" if v & 1
            else "⭐ the day cycle, four LUT entries a frame",
            "SS.Scroll" if v & 2 else "the scroll written in the blank, no call",
            "no restores" if v & 4 else "save-behind restores"]
    if v & 8:
        bits.append("no Wipe")
    if v & 0x10:
        bits.append("SWEEP")
    if v & 0x20:
        bits.append("⛔ MUTATION: the tint compounds")
    if v & 0x40:
        bits.append("⛔ MUTATION: actor 0 is never restored")
    if v & 0x80:
        bits.append("no settle")
    return ", ".join(bits)


# ──────────────────────────────────────────── ⛔ the VRAM gate, from the DATA
def expected_world(j, pic, ncrop):
    """⭐ WHAT THE CARD MUST HOLD, built from stardew.pic and the plot table.

    Retirement k puts plot (k mod NPLOT) into stage (k / NPLOT) + 1, so after
    `ncrop` retirements plot p's stage is decided - and the stages composite
    in order, keyed, exactly as the scene blits them.
    """
    w = pic.copy()
    art = np.frombuffer(base64.b64decode(j["art"]), dtype=np.uint8).reshape(16, 1024)
    npl, nst, blk = j["nplot"], j["nstage"], j["blk"]
    for p, (px, py) in enumerate(j["plots"]):
        st = min(nst, ncrop // npl + (1 if ncrop % npl > p else 0))
        kind = j["plotkind"][p]
        for k in range(st):
            slot = j["slot_crop"] + kind * nst + k
            s = art[:, j["c_spr"] + slot * blk:j["c_spr"] + (slot + 1) * blk]
            tgt = w[py:py + blk, px:px + blk]
            m = s != 0                                  # ⛔ index 0 is the key
            tgt[m] = s[m]
    return w, art


def vram_gate(out, j, pic, claim, must_fail):
    name = os.path.basename(out.rstrip("/"))
    vp = os.path.join(out, "vram.bin")
    if not os.path.exists(vp):
        return None
    V, A, M = read_marks(os.path.join(out, "marks.txt"))
    nc = cropcount(M)
    if nc is None:
        claim("%s: the scene reported how many plants it retired" % name, False)
        return None
    got = np.fromfile(vp, dtype=np.uint8).reshape(512, 1024)
    exp, art = expected_world(j, pic, nc)
    d = got[:j["h"]] != exp
    bad = int(d.sum())
    where = ""
    if bad:
        rows = np.where(d.any(1))[0]
        cols = np.where(d.any(0))[0]
        where = " - first at world row %d, column %d; %d rows, %d columns" % (
            rows[0], cols[0], len(rows), len(cols))
    what = ("%s: ⛔ THE MUTATION IS CAUGHT - the world is NOT what the data "
            "says (%d bytes differ%s)" if must_fail else
            "%s: every byte of the 1024 x 480 world is stardew.pic with the "
            "%d crop stages the scene grew (%d differ%s)")
    claim(what % ((name, bad, where) if must_fail else (name, nc, bad, where)),
          (bad > 0) if must_fail else (bad == 0))
    if must_fail:
        return nc
    ab = got[j["r_art"]:j["r_art"] + 16]
    claim("%s: ... and the keyed art bank at ring rows %d..%d is the %d bytes "
          "the generator emitted (%d differ)"
          % (name, j["r_art"], j["r_art"] + 15, art.size, int((ab != art).sum())),
          bool((ab == art).all()))
    # ⭐ AND THE LOAD ITSELF, as a separate claim: outside the crop plots
    # nothing may have moved, which says the 491,520 bytes came off the card
    # and reached VRAM unaltered.
    mask = np.ones((j["h"], j["w"]), dtype=bool)
    for (px, py) in j["plots"]:
        mask[py:py + j["blk"], px:px + j["blk"]] = False
    nb = int((got[:j["h"]][mask] != pic[mask]).sum())
    claim("%s: ⭐ and outside the crop plots the world is stardew.pic exactly - "
          "491,520 bytes off /SD0 into VRAM, %d wrong" % (name, nb), nb == 0)
    return nc


# ───────────────────── ⭐ the palette gate: the LUT, read off the RECORDING
def index_image(j, world, camx, camy):
    """The palette index of every pixel of the 640 x 200 view, from the world
    and the camera the scene reported.  ⚠ The camera is CLAMPED by the scene
    so neither axis can wrap (stardew.asm Logic), which is why this is a
    slice and not a modulo."""
    return world[camy:camy + j["viewh"], camx:camx + j["vieww"]]


def read_lut(j, idx, px):
    """⭐ THE LUT THE CARD REALLY HELD, index by index.

    Every pixel of the view whose index is i shows LUT[i], so the MODAL
    colour of index i's pixels IS that entry - and the actors, which are the
    only pixels the index image does not know about, are a couple of per cent
    and cannot carry the mode.  Returns {index: (word, count, agree)}.
    """
    keep = np.ones(idx.shape, dtype=bool)
    for (x, y, w, h) in MASKS:
        keep[y:y + h, x:x + w] = False
    i = idx[keep].astype(np.int64)
    c = px[keep].astype(np.int64)
    key = i * 65536 + c
    u, n = np.unique(key, return_counts=True)
    tot = np.bincount(i, minlength=256)
    best = {}
    for k, cnt in zip(u.tolist(), n.tolist()):
        ii, cc = k >> 16, k & 0xFFFF
        if ii not in best or cnt > best[ii][1]:
            best[ii] = (cc, cnt)
    return dict((ii, (w, c, c / float(tot[ii]))) for ii, (w, c) in best.items())


def expected_lut(j, fs, upto):
    """⭐ WHAT THE DRIVER SHOULD HAVE REACHED, from the cursor stream alone.

    The scene prepares SWMAXPW entries a frame at that frame's phase and
    writes them in the NEXT frame's blank, and it reports the cursor AFTER
    the preparation - so the batch prepared in frame g is
    [cursor(g-1), cursor(g)) at phase(g), and the picture of frame f shows
    every batch up to g = f - 1.  ⛔ No arithmetic of the scene's is replayed
    here: a frame that had to decline the blank moves the cursor not at all,
    and this reads that straight off the marks.
    """
    nart = j["nart"]
    last = [j["dayp"]] * nart                    # PalUp loaded them at noon
    prev = None
    for g, f in enumerate(fs):
        # ⚠ INCLUSIVE, and the off-by-one here cost a debugging session: the
        # batch a frame REPORTS is the one its own blank wrote, because Tags
        # runs after PalCom.  Excluding frame `upto` left exactly SWMAXPW
        # entries a checkpoint carrying the PREVIOUS sweep's phase - 54 of
        # 1,606 readings, all of them at a cursor boundary.
        if g > upto:
            break
        if "cursor" not in f or "phase" not in f:
            continue
        c = f["cursor"]
        if prev is not None and c != prev:
            k = prev
            while k != c:
                last[k] = f["phase"]
                k = (k + 1) % nart
        prev = c
    return [pipeline(j["auth"][i], j["tint"][last[i]], j["bias"][i])
            for i in range(nart)], last


def join(A, fts, t):
    """⭐ WHICH SCENE FRAME PRODUCED THE PICTURE RECORDED AT t, and it is a
    physical rule rather than a nearest-match.

    A field's pixels are drawn between its first active line and the end of
    the frame, and the work that decided them - the scroll pair and the LUT
    writes - ran in the BLANK BEFORE that active line.  So the frame mark to
    use is the last $10 before this field's `A`.  ⛔ The camera cannot be
    used to choose: when it is clamped at an edge two consecutive frames
    report the SAME camera, and three checkpoints of twelve were joined one
    frame early that way - which showed up as exactly one batch of six LUT
    entries carrying the previous sweep's phase.
    """
    ai = bisect.bisect_right(A, t) - 1
    if ai < 0:
        return max(0, bisect.bisect_right(fts, t) - 1)
    return max(0, bisect.bisect_right(fts, A[ai]) - 1)


def palette_gate(out, j, world, claim, mode, must_fail, fs, V, A):
    """⭐ THE CLAIM NO BYTE COMPARE CAN MAKE."""
    name = os.path.basename(out.rstrip("/"))
    fp = os.path.join(out, "frames.bin")
    if not os.path.exists(fp) or not fs:
        return
    V2, A2, M = read_marks(os.path.join(out, "marks.txt"))
    tset = [t for t, v in M if v == M_SETTLED]
    tlast = [t for t, v in M if v == M_WIPED]
    t0 = fs[0][M_FRAME]
    tend = tset[0] if tset else fs[-1][M_SCALL]
    want = [t0 + (tend - t0) * (k + 1) // (NCHECK + 1) for k in range(NCHECK)]
    settled = []
    if tset and tlast:
        settled = [tset[0] + (tlast[0] - tset[0]) * (k + 1) // (NSETCHK + 1)
                   for k in range(NSETCHK)]
    fts = [f[M_FRAME] for f in fs]

    # one pass over the recording, keeping the frame nearest each checkpoint
    picked = {}
    for m, px in fr.read(fp):
        t = int(m["t"] * 1e12)
        # ⚠ VMODE 00 SHOWS EACH PICTURE ROW TWICE, so the recording is
        # 640 x 400 and one VRAM byte is TWO recorded rows.  Taking every
        # other row is what makes a recorded pixel a palette index again.
        if m["h"] == 2 * j["viewh"] and m["w"] == j["vieww"]:
            px = px[::2]
        for w in want + settled:
            cur = picked.get(w)
            if cur is None or abs(t - w) < abs(cur[0] - w):
                picked[w] = (t, px.copy())
    if not picked:
        claim("%s: the recording has frames to read the LUT off" % name, False)
        return

    nart, lit0, nlit = j["nart"], j["lit0"], j["nlit"]
    day = lut_at(j, j["dayp"])
    lits = j["litcols"]

    def reading(w):
        """(the LUT the card held, the scene frame, the camera's score)."""
        t, px = picked[w]
        if px.shape != (j["viewh"], j["vieww"]):
            return None
        g = join(A, fts, t)
        if "camx" not in fs[g]:
            return None
        idx = index_image(j, world, fs[g]["camx"], fs[g]["camy"])
        lut = read_lut(j, idx, px)
        agree = sum(c for _, (_, c, a) in lut.items() if a >= MODEFRAC)
        return lut, g, agree / float(idx.size)

    def usable(lut, i):
        e = lut.get(i)
        return e if e and e[1] >= MINPIX and e[2] >= MODEFRAC else None

    # ⭐ THE JOIN IS ITSELF A CLAIM: the camera the marks report has to be the
    # camera the picture shows, or every reading below is of the wrong pixel.
    scores = [r[2] for r in (reading(w) for w in want) if r]
    claim("%s: ⭐ the camera the scene reported is the camera the card showed "
          "- %.0f%% of the view's pixels carry their index's own colour at the "
          "worst checkpoint" % (name, 100 * min(scores) if scores else 0),
          bool(scores) and min(scores) > 0.80)

    if mode is not None and mode & 1:
        # ⛔ THE CONTROL.  Mode b0 writes no LUT entry after the upload, so
        # every checkpoint must read the AUTHORED palette and nothing else.
        # Without it "the palette changed" is not a claim about anything.
        nauth = ndiff = 0
        for w in want:
            r = reading(w)
            if not r:
                continue
            for i in range(1, nart + 1):
                e = usable(r[0], i)
                if e is None:
                    continue
                if e[0] == day[i - 1]:
                    nauth += 1
                else:
                    ndiff += 1
        claim("%s: ⛔ THE CONTROL - with no LUT write the picture is the "
              "AUTHORED palette at every checkpoint (%d readings, %d not the "
              "authored colour)" % (name, nauth + ndiff, ndiff),
              nauth > 200 and ndiff == 0)
        return

    nok = nbad = ncov = litbad = moved = 0
    firstbad = None
    worstph = []
    for w in want:
        r = reading(w)
        if not r:
            continue
        lut, g, _ = r
        exp, lastph = expected_lut(j, fs, g)
        # ⚠ the phase is CIRCULAR, so the spread is the smallest arc that
        # holds every entry and not max - min.
        srt = sorted(set(lastph))
        gaps = [(srt[(k + 1) % len(srt)] - srt[k]) % j["nphase"]
                for k in range(len(srt))] or [0]
        worstph.append(j["nphase"] - max(gaps))
        for i in range(1, nart + 1):
            e = usable(lut, i)
            if e is None:
                continue
            ncov += 1
            if e[0] == exp[i - 1]:
                nok += 1
            else:
                nbad += 1
                if firstbad is None:
                    firstbad = (i, e[0], exp[i - 1], fs[g].get("phase"))
            if e[0] != day[i - 1]:
                moved += 1
        for k in range(nlit):
            e = usable(lut, lit0 + k)
            if e is not None and e[0] != lits[k]:
                litbad += 1

    # ⛔ A PALETTE MUTATION BREAKS BOTH OF THIS GATE'S CLAIMS, and it has to:
    # the compounding bug corrupts the AUTHORED table, so the mid-run readings
    # are wrong as well as the settled ones.  The first draft of the mutation
    # harness expected this claim to pass under b5 and was simply wrong about
    # what the bug does.
    what = ("%s: ⛔ THE MUTATION IS CAUGHT - the picture is NOT the tint the "
            "driver should have reached (%d of %d readings over %d "
            "checkpoints differ%s)" if must_fail else
            "%s: ⭐ THE PALETTE GATE - every art entry the picture shows is "
            "the tint the driver should have reached (%d of %d readings over "
            "%d checkpoints%s)")
    claim(what % (name, nbad if must_fail else nok, ncov, len(want),
                  "" if firstbad is None else
                  "; entry %d read $%04X, wanted $%04X at phase %s" % firstbad),
          (ncov > 0 and nbad > 0) if must_fail else (ncov > 0 and nbad == 0))
    claim("%s: ... and the gate is not vacuous: %d of the %d art entries were "
          "read at an average checkpoint"
          % (name, ncov // max(1, len(want)), nart),
          ncov >= len(want) * nart // 4)
    # ⭐ THE LIT SET: the tint never touches it, so it is the same colour at
    # every checkpoint and it is the AUTHORED one.  This is what makes the
    # windows and the lanterns BECOME the light as the world darkens.
    claim("%s: ⭐ the lit set is untouched by the tint - every reading of "
          "entries %d..%d is its authored colour (%d wrong)"
          % (name, lit0, lit0 + nlit - 1, litbad), litbad == 0)
    # ⭐ AND THE POSITIVE CONTROL: the day must actually have happened.
    claim("%s: ⭐ and THE DAY HAPPENED: %d readings were NOT the authored "
          "colour, so the claim above can fail" % (name, moved), moved > 200)
    if worstph:
        print("  -> the LUT lags the day by at most %d of %d phases, which is "
              "the round-robin's own depth" % (max(worstph), j["nphase"]))

    # ⛔ THE COMPOUNDING GATE
    if not settled:
        claim("%s: ⛔ the settle ran, so a whole day can be judged" % name,
              bool(mode is not None and mode & 0x80))
        return
    cok = cbad = 0
    cfirst = None
    for w in settled:
        r = reading(w)
        if not r:
            continue
        for i in range(1, nart + 1):
            e = usable(r[0], i)
            if e is None:
                continue
            if e[0] == day[i - 1]:
                cok += 1
            else:
                cbad += 1
                if cfirst is None:
                    cfirst = (i, e[0], day[i - 1])
    what = ("%s: ⛔ THE COMPOUNDING MUTATION IS CAUGHT - a whole day did NOT "
            "come home (%d of %d readings are not the authored colour%s)"
            if must_fail else
            "%s: ⛔ THE COMPOUNDING GATE - one whole day returns every art "
            "entry to its authored value (%d of %d readings wrong%s)")
    claim(what % (name, cbad, cok + cbad,
                  "" if cfirst is None else
                  "; entry %d is $%04X, authored $%04X" % cfirst),
          (cbad > 0) if must_fail else (cok > 0 and cbad == 0))


# ──────────────────────────────────────────── the budget and the tearing gate
def in_blank(V, A, t):
    i = bisect.bisect_right(V, t) - 1
    if i < 0:
        return None
    j = bisect.bisect_right(A, V[i])
    if j >= len(A):
        return None
    return t < A[j]


def budget(out, claim, j):
    name = os.path.basename(out.rstrip("/"))
    mp = os.path.join(out, "marks.txt")
    if not os.path.exists(mp):
        claim("%s: marks.txt exists" % name, False)
        return None, None, None, None
    V, A, M = read_marks(mp)
    fs = frames_of(M)
    mv = None
    ap = os.path.join(out, "args.txt")
    if os.path.exists(ap):
        mv = int(open(ap).read().split()[0])
    print("\n%s - %s" % (name, mode_name(mv)))
    print("  actors  frames  work ms  frame ms | " +
          " ".join("%7s" % p[0] for p in PHASES) + " | idle ms  drops")
    rows = {}
    prev = None
    for f in fs:
        n = f.get("n", 0)
        r = rows.setdefault(n, dict(frames=0, period=[], work=[], drops=0,
                                    **{p[0]: 0.0 for p in PHASES}))
        r["frames"] += 1
        for nm, a, b in PHASES:
            if a in f and b in f:
                r[nm] += (f[b] - f[a]) / 1e9
        r["work"].append((f[M_SCALL] - f[M_FRAME]) / 1e9)
        if prev is not None and prev.get("n") == n:
            r["period"].append((f[M_FRAME] - prev[M_FRAME]) / 1e9)
        if f.get("waited", 1) > 1:
            r["drops"] += 1
        prev = f
    hard, fit = None, []
    for n in sorted(rows):
        r = rows[n]
        c = r["frames"]
        work = sum(r["work"]) / c
        if c >= 8:
            fit.append((n, work, c))
        per = sum(r["period"]) / len(r["period"]) if r["period"] else float("nan")
        print("  %6d  %6d  %7.2f  %8.2f | " % (n, c, work, per) +
              " ".join("%7.3f" % (r[p[0]] / c) for p in PHASES) +
              " | %7.2f  %5d" % (per - work, r["drops"]))
        if hard is None and work > BUDGET_MS:
            hard = n
    if hard is None:
        print("  -> every step fitted the %.2f ms frame" % BUDGET_MS)
    else:
        print("  -> the work first passed %.2f ms at %d actors" % (BUDGET_MS, hard))
    if len(fit) >= 4:
        sw = sum(c for _, _, c in fit)
        mx = sum(n * c for n, _, c in fit) / sw
        my = sum(w * c for _, w, c in fit) / sw
        den = sum(c * (n - mx) ** 2 for n, _, c in fit)
        if den > 0:
            b = sum(c * (n - mx) * (wk - my) for n, wk, c in fit) / den
            a = my - b * mx
            print("  -> %.3f ms of frame + %.3f ms an actor  ⭐ %d actors fit "
                  "the %.2f ms frame" % (a, b, int((BUDGET_MS - a) / b), BUDGET_MS))
    claim("%s: every frame carried all eight phase marks" % name,
          len(fs) > 0 and all(all(k in f for _, k, _ in PHASES) for f in fs))
    okn = set(n for n, r in rows.items()
              if sum(r["work"]) / r["frames"] < BUDGET_MS * 0.9)
    fits = [rows[n] for n in okn]
    claim("%s: the frame poll never waited more than one card frame at an "
          "actor count that fits with 10%% to spare (%d dropped)"
          % (name, sum(r["drops"] for r in fits)),
          all(r["drops"] == 0 for r in fits))

    # ⛔ THE TEARING GATE, and its negative control
    if mv is not None and not (mv & 2):
        sync, pw = [], None
        for f in fs:
            if pw is None or pw < BUDGET_MS - SYNCMS:
                sync.append(f)
            pw = (f[M_SCALL] - f[M_FRAME]) / 1e9
        wrote = [f for f in sync if not f.get("declined")]
        tot = [f[M_SCROLL] for f in wrote]
        ins = [t for t in tot if in_blank(V, A, t)]
        claim("%s: ⛔ every scroll write is INSIDE the blank - $11 is marked "
              "the instant the four stores are done and it lands in [V, A) "
              "(%d of %d)" % (name, len(ins), len(tot)),
              bool(tot) and len(ins) == len(tot))
        # ⭐ AND THE LUT WRITES ARE IN THE SAME CLAIM, which is the whole
        # reason the tint's arithmetic was moved out of the blank.
        lt = [f[M_LUT] for f in wrote if M_LUT in f]
        lin = [t for t in lt if in_blank(V, A, t)]
        lms = sorted((f[M_LUT] - f[M_SCROLL]) / 1e6 for f in wrote if M_LUT in f)
        if lms:
            print("  -> the frame's LUT writes take %.0f us at the median and "
                  "%.0f at worst" % (lms[len(lms) // 2], lms[-1]))
        claim("%s: ⛔ ... and so is the last of the frame's LUT writes - $12 "
              "lands in the same blank (%d of %d)" % (name, len(lin), len(lt)),
              bool(lt) and len(lin) == len(lt))
        # ⚠ AT AN OPERATING POINT THAT FITS.  A frame whose predecessor
        # overran wakes with the blank nearly gone and DECLINES what does not
        # fit, which is the designed answer and is most of the sweep's
        # over-budget steps; what may never happen is a write made late, and
        # the claim above is the one that says it never was.
        short = sum(1 for f in sync if f.get("lutshort"))
        allshort = sum(1 for f in fs if f.get("lutshort"))
        claim("%s: ... and a commit that would not fit was DECLINED rather "
              "than written late (%d frames ran the blank out after a frame "
              "that kept its budget; %d over the whole run)"
              % (name, short, allshort), short == 0)
        pic = [t for t, v in M if v == M_ACTORS and in_blank(V, A, t) is False]  # noqa: E501
        alt = [t for t, v in M if v == M_ACTORS]
        claim("%s: ... and the control says the test can fail: the actor "
              "phase ends in the PICTURE (%d of %d)" % (name, len(pic), len(alt)),
              bool(alt) and len(pic) * 4 > len(alt) * 3)
        into, blen = [], []
        for f in wrote:
            t = f[M_FRAME]
            i = bisect.bisect_right(V, t) - 1
            if not in_blank(V, A, t):
                continue
            jj = bisect.bisect_right(A, V[i]) if i >= 0 else -1
            if i >= 0 and 0 <= jj < len(A):
                into.append((t - V[i]) / 1e6)
                blen.append((A[jj] - V[i]) / 1e6)
        if into:
            into.sort()
            bl = sum(blen) / len(blen)
            print("  -> the frame poll returns %.0f us into a %.0f us blank, "
                  "leaving %.0f" % (into[len(into) // 2], bl, bl - into[-1]))
            claim("%s: the scroll pair AND the LUT writes still fit the blank "
                  "the poll leaves (%.0f us left at worst, and they need ~%.0f)"
                  % (name, bl - into[-1], (lms[-1] if lms else 0) + 45),
                  bl - into[-1] > (lms[-1] if lms else 0) + 45)
    # ⭐ the scene did its own housekeeping
    codes = set(v for _, v in M)
    claim("%s: the world was loaded off the card ($1C)" % name, M_LOADED in codes)
    if mv is None or not (mv & 0x80):
        claim("%s: ⭐ and the settle finished, so the compounding gate has "
              "something to read ($1B)" % name, M_SETTLED in codes)
    return fs, V, A, mv


# ───────────────────────────────────────────────────────── contact sheets
def make_sheets(out, fs, j, world):
    from PIL import Image, ImageDraw, ImageFont
    fp = os.path.join(out, "frames.bin")
    if not os.path.exists(fp) or not fs:
        return []
    font = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", 15)
    t0 = fs[0][M_FRAME] / 1e12
    t1 = fs[-1][M_SCALL] / 1e12
    fts = [f[M_FRAME] / 1e12 for f in fs]
    TW, TH, LABEL = 640, 200, 24
    tiles, nxt, prev = [], t0, None
    for m, px in fr.read(fp):
        t = m["t"]
        if t < t0 or t > t1 + 0.05 or t < nxt:
            continue
        if prev is not None and np.array_equal(px, prev):
            continue
        prev = px.copy()
        nxt = t + SHEET_EVERY
        i = max(0, bisect.bisect_right(fts, t) - 1)
        im = Image.fromarray(fr.rgb565_to_rgb8(px))
        if im.size != (TW, TH):
            im = im.resize((TW, TH), Image.NEAREST)
        tile = Image.new("RGB", (TW, TH + LABEL), (16, 18, 22))
        tile.paste(im, (0, 0))
        d = ImageDraw.Draw(tile)
        ph = fs[i].get("phase", 0)
        seg = j["keynm"][min(3, ph // 64)]
        d.text((4, TH + 3), "%.2f s   camera %d, %d   day %d/%d (%s)   %d actors"
               % (t - t0, fs[i].get("camx", 0), fs[i].get("camy", 0), ph,
                  j["nphase"], seg, fs[i].get("n", 0)),
               font=font, fill=(255, 190, 80))
        tiles.append(tile)
    paths = []
    for p in range(0, len(tiles), COLS * ROWS):
        grp = tiles[p:p + COLS * ROWS]
        r = (len(grp) + COLS - 1) // COLS
        sh = Image.new("RGB", (COLS * TW, r * (TH + LABEL)), (0, 0, 0))
        for i, tl in enumerate(grp):
            sh.paste(tl, ((i % COLS) * TW, (i // COLS) * (TH + LABEL)))
        path = os.path.join(out, "sheet-%d.png" % (p // (COLS * ROWS) + 1))
        sh.save(path)
        paths.append(path)
        print("ok    %s: %d tiles" % (path, len(grp)))
    return paths


def main():
    outs = list(sys.argv[1:])
    must_fail = "--gate-must-fail" in outs
    if must_fail:
        outs.remove("--gate-must-fail")
    nosheet = bool(os.environ.get("NOSHEET")) or must_fail
    if not outs:
        print("usage: checkv3star.py [--gate-must-fail] OUT [OUT2 ...]")
        return 2
    j = json.load(open(os.path.join(HERE, "stardew.json")))
    pp = os.path.join(HERE, j["pic"])
    if not os.path.exists(pp):
        print("FAIL  no %s - run mkstardew.py" % pp)
        return 1
    pic = np.fromfile(pp, dtype=np.uint8).reshape(j["h"], j["w"])
    fail, n = 0, 0

    def claim(what, ok):
        nonlocal fail, n
        n += 1
        print("%s  %s" % ("ok   " if ok else "FAIL ", what))
        if not ok:
            fail += 1

    summary = {}
    for i, out in enumerate(outs):
        fs, V, A, mv = budget(out, claim, j)
        # ⛔ A MUTATION IS CAUGHT BY THE GATE ITS MODE BELONGS TO, and the
        # other one must still pass.  b6 drops a restore and b3 skips the
        # Wipe, which are VRAM; b5 compounds the tint, which touches no VRAM
        # at all - and that asymmetry IS the reason this scene needed a
        # second gate, so the mutation test has to respect it.
        vfail = bool(must_fail and mv is not None and (mv & 0x48))
        pfail = bool(must_fail and mv is not None and (mv & 0x20))
        nc = vram_gate(out, j, pic, claim, vfail)
        if fs and nc is not None:
            world, _ = expected_world(j, pic, nc)
            palette_gate(out, j, world, claim, mv, pfail, fs, V, A)
            if not nosheet and i == 0:
                paths = make_sheets(out, fs, j, world)
                claim("%s: contact sheets written (%d)"
                      % (os.path.basename(out.rstrip("/")), len(paths)), len(paths) > 0)
        if fs:
            rows = {}
            for f in fs:
                rows.setdefault(f.get("n", 0), []).append(
                    (f[M_SCALL] - f[M_FRAME]) / 1e9)
            summary[os.path.basename(out.rstrip("/"))] = rows

    # ⭐ THE HEADLINE, STATED AS ONE CLAIM: a day costs no pixels.  The run
    # with the cycle and the run without it did the same drawing, so if the
    # tint touched VRAM anywhere their dumps would differ - and the palette
    # gate has already said the two runs' LUTs did NOT agree.  Two dumps that
    # are byte-identical and two palettes that are not is the whole feature.
    vs = {}
    for out in outs:
        ap = os.path.join(out, "args.txt")
        vp = os.path.join(out, "vram.bin")
        if os.path.exists(ap) and os.path.exists(vp):
            vs[int(open(ap).read().split()[0])] = vp
    if 0 in vs and 1 in vs:
        a0 = np.fromfile(vs[0], dtype=np.uint8).reshape(512, 1024)[:j["h"]]
        a1 = np.fromfile(vs[1], dtype=np.uint8).reshape(512, 1024)[:j["h"]]
        d = int((a0 != a1).sum())
        claim("⭐ THE DAY COSTS NO PIXELS: the run WITH the cycle and the run "
              "WITHOUT it leave the 1024 x 480 world byte for byte the same "
              "(%d differ)" % d, d == 0)

    if len(summary) >= 2:
        keys = sorted(summary)
        print("\nthe whole frame's work, ms, the same scene several ways")
        print("  actors " + "".join("%16s" % k for k in keys))
        base = summary[keys[0]]
        for a in sorted(base):
            line = "  %6d" % a
            for k in keys:
                r = summary[k].get(a)
                line += "%16s" % ("%.3f" % (sum(r) / len(r)) if r else "-")
            print(line)

    print("\n%d claims, %d failed" % (n, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
