#!/usr/bin/env python3
"""checkv3mon.py OUT [OUT2 ...] - the monster scene's gate, its budget, its sheets.

Each OUT is one emulator run of `monster` (video3/bench/run-v3mon.sh) holding
marks.txt, and usually frames.bin and vram.bin.  This reads them and makes
three different kinds of claim:

  ⛔ THE CORRECTNESS GATE.  monster's playfield is decided by DATA, not by
     what the run happened to do: every byte of ring rows 0..207 is the
     strip its level map names, for the 64 level columns the ring holds at
     the scroll the run ended on.  So the whole of VRAM is rebuilt here from
     monster.json - the block bank, the strip tables, the level map - and
     compared byte for byte.  A dropped restore, a wrong block, an
     off-by-one column, a keyed copy that wrote its holes or a composition
     that stacked a strip wrong each fail it.
  ⭐ THE BUDGET.  The $FF2E marks, timestamped in picoseconds, split into the
     blank's work, the column refill, the game logic and the actors.
  ⛔ THE TEARING GATE.  The scroll pair has to reach the card INSIDE the
     blank, which is the whole reason a driver call ever did it.  marks.txt
     carries VBLANK's rise (V) and each frame's first active line (A), and
     $10 / $11 bracket monster's own register writes - so the claim is read
     off the recording rather than argued.  ⭐ With a negative control: the
     $14 mark, at the end of the actor work, must land in the PICTURE, or
     the predicate would be passing everything.

⛔ Its exit code is the answer.

  --gate-must-fail   invert the correctness gate: the run is a MUTATION and
                     the gate is required to catch it.  This is what makes
                     the gate worth anything (CLAUDE.md: a green check
                     proves nothing on its own).
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

# monster.asm's marks
M_FRAME, M_SCROLL, M_SPRITE = 0x10, 0x11, 0x12
M_REFILL, M_LOGIC, M_ACTORS, M_SCALL = 0x13, 0x14, 0x15, 0x16
M_SEAM, M_BEGIN, M_LAST, M_WIPED, M_NOBLK = 0x17, 0x18, 0x19, 0x1A, 0x1E
M_POLL0, M_ACT0, M_CAMH, M_CAML, M_NIB = 0x40, 0x60, 0x80, 0xA0, 0xE0
BUDGET_MS = 14.3                    # VMODE 00, keyed-copy.md 6.1
SHEET_EVERY = float(os.environ.get("SHEET_EVERY", "0.6"))
COLS, ROWS = 4, 5

PHASES = [("scroll", M_FRAME, M_SCROLL), ("sprite", M_SCROLL, M_SPRITE),
          ("refill", M_SPRITE, M_REFILL), ("logic", M_REFILL, M_LOGIC),
          ("actors", M_LOGIC, M_ACTORS), ("oscall", M_ACTORS, M_SCALL)]


def mode_name(v):
    if v is None:
        return "?"
    bits = [
        "SS.Scroll" if v & 1 else "⭐ the scroll written in the blank, no call",
        "NO REFILL" if v & 2 else "block-streamed playfield",
        "no restores" if v & 4 else "restores from the clean band",
        "two phases" if v & 0x80 else "interleaved",
    ]
    if v & 8:
        bits.append("no Wipe")
    if v & 0x10:
        bits.append("SWEEP")
    if v & 0x20:
        bits.append("⛔ MUTATION: the refill is one column out")
    if v & 0x40:
        bits.append("⛔ MUTATION: actor 0 is never restored")
    return ", ".join(bits)


def read_marks(path):
    """marks.txt: VBLANK's rises, the first active lines, and (t_ns, code)."""
    V, A, M = [], [], []
    for line in open(path):
        # ⚠ THE LAST LINE CAN BE HALF A LINE.  The emulator stops on
        # SERIAL_STOP and does not always flush marks.txt's tail, so a
        # recording ends mid-record about one run in eight - and a parser
        # that throws there fails a run that was fine.
        f = line.split()
        if len(f) != 2:
            continue
        a, tag = f
        t = int(a)
        if tag == "V":
            V.append(t)
        elif tag == "A":
            A.append(t)
        elif tag[0] == "M":
            M.append((t, int(tag[1:])))
    return V, A, M


def in_blank(V, A, t):
    """Is t inside a blank?  None if the recording cannot say."""
    i = bisect.bisect_right(V, t) - 1
    if i < 0:
        return None
    j = bisect.bisect_right(A, V[i])
    if j >= len(A):
        return None
    return t < A[j]


def frames_of(M):
    """One dict a frame: its phase timestamps in ns, the actor count, the
    camera and how many card frames the poll waited."""
    out, cur, cam = [], None, [0, 0]
    for t, v in M:
        if v == M_FRAME:
            if cur and M_SCALL in cur:
                out.append(cur)
            cur = {M_FRAME: t, "cam": cam[0] << 9 | cam[1] << 4}
        elif cur is None:
            continue
        elif v in (M_SCROLL, M_SPRITE, M_REFILL, M_LOGIC, M_ACTORS, M_SCALL):
            cur[v] = t
        elif M_ACT0 <= v < M_ACT0 + 32:
            cur["n"] = v - M_ACT0
        elif v == M_NOBLK:
            cur["declined"] = True
        elif M_POLL0 <= v < M_POLL0 + 32:
            cur["waited"] = v - M_POLL0
        elif M_CAMH <= v < M_CAMH + 32:
            cam[0] = v - M_CAMH
            cur["cam"] = cam[0] << 9 | cam[1] << 4
        elif M_CAML <= v < M_CAML + 32:
            cam[1] = v - M_CAML
            cur["cam"] = cam[0] << 9 | cam[1] << 4
    if cur and M_SCALL in cur:
        out.append(cur)
    return out


def lastfil_of(M):
    """The four nibble marks the scene emits after its Wipe."""
    nib = [v - M_NIB for _, v in M if M_NIB <= v < M_NIB + 16]
    if len(nib) < 4:
        return None
    nib = nib[-4:]
    return (nib[0] << 12) | (nib[1] << 8) | (nib[2] << 4) | nib[3]


# ───────────────────────────────────────── the expected VRAM, from the DATA
def d64(s, shape=None):
    a = np.frombuffer(base64.b64decode(s), dtype=np.uint8)
    return a.reshape(shape) if shape else a


def expected_vram(j, lastfil):
    """⭐ WHAT THE CARD MUST HOLD, built from monster.json and nothing else.

    The ROM and this share the DATA and no code (bench/README.md's rule):
    the ROM reads monsterdat.asm, which mkmonster.py wrote from the same
    arrays this reads out of monster.json.
    """
    BLK, nblk = j["blk"], j["nblk"]
    ntop, nbot, nspr = j["ntop"], j["nbot"], j["nspr"]
    toprows, botrows = j["toprows"], j["botrows"]
    toph, both, playh = j["toph"], j["both"], j["playh"]
    blocks = d64(j["blocks"], (nblk, BLK, BLK))
    tops = d64(j["tops"], (ntop, toprows))
    bots = d64(j["bots"], (nbot, botrows))
    levtop, levbot = d64(j["levtop"]), d64(j["levbot"])
    art = d64(j["art"], (BLK, nspr * BLK))

    v = np.zeros((512, 1024), dtype=np.uint8)
    know = np.zeros((512, 1024), dtype=bool)

    def strip(tab, ids, r0, col):
        for k, b in enumerate(ids):
            v[r0 + k * BLK:r0 + (k + 1) * BLK, col:col + BLK] = blocks[b]
            know[r0 + k * BLK:r0 + (k + 1) * BLK, col:col + BLK] = True

    for k in range(ntop):
        strip(tops, tops[k], j["r_topbank"], k * BLK)
    for k in range(nbot):
        strip(bots, bots[k], j["r_botbank"], k * BLK)
    # the keyed art sits in the columns the BOT strips do not use
    v[j["r_art"]:j["r_art"] + BLK, j["c_art"]:j["c_art"] + nspr * BLK] = art
    know[j["r_art"]:j["r_art"] + BLK, j["c_art"]:j["c_art"] + nspr * BLK] = True

    # the live playfield and its clean BOT copy: ring group g holds the most
    # recent level column congruent to g, which is what the scene's own
    # $E0 nibbles say
    ringc = 1024 // BLK
    cols = {}
    for g in range(ringc):
        c = lastfil - ((lastfil - g) % ringc)
        assert 0 <= c < j["levcols"], (g, c)
        cols[g] = c
        t, b = levtop[c], levbot[c]
        for k in range(toprows):
            v[k * BLK:(k + 1) * BLK, g * BLK:(g + 1) * BLK] = blocks[tops[t][k]]
        for k in range(botrows):
            r = toph + k * BLK
            v[r:r + BLK, g * BLK:(g + 1) * BLK] = blocks[bots[b][k]]
            rc = j["r_clean"] + k * BLK
            v[rc:rc + BLK, g * BLK:(g + 1) * BLK] = blocks[bots[b][k]]
        know[0:playh, g * BLK:(g + 1) * BLK] = True
        know[j["r_clean"]:j["r_clean"] + both, g * BLK:(g + 1) * BLK] = True
    return v, know, cols


def gate(out, j, claim, must_fail):
    name = os.path.basename(out.rstrip("/"))
    vp = os.path.join(out, "vram.bin")
    mp = os.path.join(out, "marks.txt")
    if not os.path.exists(vp):
        return
    V, A, M = read_marks(mp)
    lf = lastfil_of(M)
    if lf is None:
        claim("%s: the scene reported the last level column it filled" % name, False)
        return
    got = np.fromfile(vp, dtype=np.uint8).reshape(512, 1024)
    exp, know, cols = expected_vram(j, lf)
    bad = int(((got != exp) & know).sum())
    where = ""
    if bad:
        rows = np.where(((got != exp) & know).any(1))[0]
        colsb = np.where(((got != exp) & know).any(0))[0]
        where = " - first at ring row %d, column %d; %d rows, %d columns" % (
            rows[0], colsb[0], len(rows), len(colsb))
    what = ("%s: ⛔ THE MUTATION IS CAUGHT - VRAM is NOT what the level map "
            "says (%d bytes differ%s)" if must_fail else
            "%s: every byte of the playfield, the bank and the clean band is "
            "what the level map says (%d differ%s)")
    claim(what % (name, bad, where), (bad > 0) if must_fail else (bad == 0))
    if must_fail:
        return
    # ⭐ AND THE SCENE'S OWN ARITHMETIC, as a SEPARATE claim.  The gate above
    # believes the nibbles; this one does not.  frames-1 because the camera
    # advances at the END of a frame, so the last refill saw speed*(frames-1).
    env = os.path.join(out, "args.txt")
    if os.path.exists(env):
        mode, frames, speed, nact = (int(x) for x in open(env).read().split())
        if not (mode & 0x12):           # no sweep quirk, and the refill is on
            want = max(1024 // j["blk"] - 1, (speed * (frames - 1) + 832) >> 4)
            claim("%s: the last column filled is where %d frames at %d px a "
                  "frame put it (%d, and the scene said %d)"
                  % (name, frames, speed, want, lf), want == lf)


def budget(out, claim, sheets_here, j):
    name = os.path.basename(out.rstrip("/"))
    mp = os.path.join(out, "marks.txt")
    if not os.path.exists(mp):
        claim("%s: marks.txt exists" % name, False)
        return None
    V, A, M = read_marks(mp)
    fs = frames_of(M)
    mv = None
    ap = os.path.join(out, "args.txt")
    if os.path.exists(ap):
        mv = int(open(ap).read().split()[0])
    print("\n%s - %s" % (name, mode_name(mv)))
    print("  actors  frames  work ms  frame ms |  scroll  sprite  refill   logic"
          "  actors  oscall | idle ms  drops")
    rows = {}
    prev = None
    for f in fs:
        n = f.get("n", 0)
        r = rows.setdefault(n, dict(frames=0, period=[], work=[], drops=0,
                                    **{p[0]: 0.0 for p in PHASES}))
        r["frames"] += 1
        for nm, a, b in PHASES:
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
        print("  %6d  %6d  %7.2f  %8.2f | %7.3f %7.3f %7.3f %7.3f %7.3f %7.3f"
              " | %7.2f  %5d"
              % (n, c, work, per, r["scroll"] / c, r["sprite"] / c, r["refill"] / c,
                 r["logic"] / c, r["actors"] / c, r["oscall"] / c, per - work,
                 r["drops"]))
        if hard is None and work > BUDGET_MS:
            hard = n
    if hard is None:
        print("  -> every step fitted the %.1f ms frame" % BUDGET_MS)
    else:
        print("  -> the work first passed %.1f ms at %d actors" % (BUDGET_MS, hard))
    # ⭐ THE MOST ACTORS THAT FIT, from the SLOPE rather than from the row
    # the sweep happened to stop on.  The cast's live count wanders (an
    # actor waiting out its respawn delay costs nothing), so the steps are
    # not evenly filled and a least-squares line over them is the honest
    # reading.  Weighted by how many frames each count was measured over.
    if len(fit) >= 4:
        sw = sum(c for _, _, c in fit)
        mx = sum(n * c for n, _, c in fit) / sw
        my = sum(w * c for _, w, c in fit) / sw
        den = sum(c * (n - mx) ** 2 for n, _, c in fit)
        if den > 0:
            b = sum(c * (n - mx) * (w - my) for n, w, c in fit) / den
            a = my - b * mx
            print("  -> %.3f ms of frame + %.3f ms an actor  ⭐ %d actors fit "
                  "the %.1f ms frame" % (a, b, int((BUDGET_MS - a) / b), BUDGET_MS))
    claim("%s: every frame carried all six phase marks" % name,
          len(fs) > 0 and all(all(k in f for _, k, _ in PHASES) for f in fs))
    # ⚠ AT AN ACTOR COUNT THAT COMFORTABLY FITS.  A step whose mean work is
    # within 10% of the frame drops one now and then on the variance alone,
    # which is a true statement about the budget and not a defect.
    fits = [r for n, r in rows.items() if sum(r["work"]) / r["frames"] < BUDGET_MS * 0.9]
    claim("%s: the frame poll never waited more than one card frame at an "
          "actor count that fits with 10%% to spare (%d frames dropped)"
          % (name, sum(r["drops"] for r in fits)),
          all(r["drops"] == 0 for r in fits))

    # ⛔ THE TEARING GATE, and its negative control
    if mv is not None and not (mv & 1):
        # ⛔ ONLY THE FRAMES THAT WROTE.  A frame that found the blank gone
        # DECLINES the write and marks $1E - which is the designed answer,
        # and counting its marks would fail the scene for doing the right
        # thing.  What may never happen is a write OUTSIDE a blank.
        wrote = [f for f in frames_of(M) if not f.get("declined")]
        tot = [f[k] for f in wrote for k in (M_FRAME, M_SCROLL)]
        ins = [t for t in tot if in_blank(V, A, t)]
        claim("%s: ⛔ every scroll write is INSIDE the blank - $10 and $11 "
              "bracket them and both land in [V, A) (%d of %d)"
              % (name, len(ins), len(tot)), len(ins) == len(tot) and tot)
        pic = [t for t, v in M if v == M_ACTORS and in_blank(V, A, t) is False]
        alt = [t for t, v in M if v == M_ACTORS]
        claim("%s: ... and the control says the test can fail: the actor "
              "phase ends in the PICTURE (%d of %d)" % (name, len(pic), len(alt)),
              alt and len(pic) * 4 > len(alt) * 3)
        miss = len(fs) - len(wrote)
        over = sum(1 for f in fs
                   if (f[M_SCALL] - f[M_FRAME]) / 1e9 > BUDGET_MS)
        claim("%s: a frame DECLINED the blank only when it had overrun it "
              "(%d declined, %d frames were over budget)" % (name, miss, over),
              miss <= over)
        # ⭐ HOW MUCH BLANK AN EXCLUSIVE OWNER REALLY HAS.  optimizations.md
        # 8 says the poll returns twelve lines into a forty-nine-line blank,
        # so the owner has ~1.1 ms of blank already paid for.  That is a
        # derivation, not a measurement; this is the measurement.
        into, blen = [], []
        for f in wrote:
            t = f[M_FRAME]
            i = bisect.bisect_right(V, t) - 1
            jj = bisect.bisect_right(A, V[i]) if i >= 0 else -1
            if i >= 0 and 0 <= jj < len(A):
                into.append((t - V[i]) / 1e6)
                blen.append((A[jj] - V[i]) / 1e6)
        if into:
            into.sort()
            bl = sum(blen) / len(blen)
            med = into[len(into) // 2]
            print("  -> the frame poll returns %.0f us into a %.0f us blank "
                  "(%.0f..%.0f), leaving %.0f us of it"
                  % (med, bl, into[0], into[-1], bl - into[-1]))
            claim("%s: the scroll pair still fits the blank the poll leaves "
                  "(%.0f us left at worst, and it needs ~5)"
                  % (name, bl - into[-1]), bl - into[-1] > 20)

    # ⚠ THE RING SEAM.  A restore rectangle that crosses ring column 1023
    # wraps INSIDE its row, which is what a 1024-column torus means - and it
    # is the one thing here mvania declined to exercise.  If no rectangle
    # ever wrapped, the gate above did not test it and says so.
    seams = sum(1 for _, v in M if v == M_SEAM)
    if mv is not None and not (mv & 0x16):
        claim("%s: at least one rectangle crossed the ring's seam, so the "
              "gate covers the wrap (%d frames)" % (name, seams), seams > 0)

    if sheets_here:
        paths = make_sheets(out, fs, M, j)
        claim("%s: contact sheets written (%d)" % (name, len(paths)), len(paths) > 0)
    return rows


def make_sheets(out, fs, M, j):
    """⭐ THE SHEETS THE SCENE IS REVIEWED FROM, and no video.

    ⚠ THE TAGS ARE NOT IN THE FRAME RECORD.  mvania's camera and actor count
    reach frames.bin through VG.MkCam and VG.MkHero, which only the driver
    can write - and this scene makes no driver call, which was the point.
    So the tags come out of marks.txt and the two files are joined on the
    TIMESTAMP: both carry picoseconds off the same emulator clock.
    """
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
        d.text((4, TH + 3), "%.2f s   level x %d of %d   %d actors"
               % (t - t0, fs[i]["cam"], j["levcols"] * j["blk"], fs[i].get("n", 0)),
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
        print("usage: checkv3mon.py [--gate-must-fail] OUT [OUT2 ...]")
        return 2
    j = json.load(open(os.path.join(HERE, "monster.json")))
    fail, n = 0, 0

    def claim(what, ok):
        nonlocal fail, n
        n += 1
        print("%s  %s" % ("ok   " if ok else "FAIL ", what))
        if not ok:
            fail += 1

    summary = {}
    for i, out in enumerate(outs):
        rows = budget(out, claim, not nosheet and i == 0, j)
        if rows:
            summary[os.path.basename(out.rstrip("/"))] = rows
        gate(out, j, claim, must_fail)

    if len(summary) >= 2:
        keys = sorted(summary)
        print("\nthe whole frame's work, ms, the same scene several ways")
        print("  actors " + "".join("%16s" % k for k in keys))
        base = summary[keys[0]]
        for a in sorted(base):
            line = "  %6d" % a
            for k in keys:
                r = summary[k].get(a)
                line += "%16s" % ("%.3f" % (sum(r["work"]) / r["frames"]) if r else "-")
            print(line)

    print("\n%d claims, %d failed" % (n, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
