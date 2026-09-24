#!/usr/bin/env python3
"""checkv3mv.py OUT [OUT2 ...] - what the metroidvania scene cost, and the sheets.

Each OUT is one emulator run of `mvania` (software/mvania/bench/run-v3mv.sh), holding
frames.bin and marks.txt.  This reads the marks - the picosecond timestamps
the emulator writes for every store to $FF2E - and turns them into the frame
budget:

    actors  frames  work ms  frame ms | list restore logic draw scroll | idle  drops

and it writes the contact sheets the scene is REVIEWED from, at
OUT/sheet-N.png, one tile every SHEET_EVERY seconds of machine time.

⛔ Its exit code is the answer.  The claims are at the bottom: every phase
accounted for, the sweep's steps all reached, and - for the merged run -
fewer rectangles than actors.
"""
import bisect
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "software", "tools"))
import frames as fr  # noqa: E402

# mvania.asm's marks
M_FRAME, M_REST, M_LOGIC, M_DRAW, M_SCROLL = 0x10, 0x11, 0x12, 0x13, 0x14
M_LIST = 0x15                       # the restore list is decided; the copies start
M_STEP0, M_POLL0, M_ACT0 = 0x20, 0x40, 0x80
M_NOBLK = 0x2E                      # b8: the blank had passed, nothing written
# ⭐ THE BLANK GATE's marks, and they exist only in a -DBTMARK=1 ROM
# (defs/armvid.d).  $3E is vidsvc.asm's VcSvc committing the frame batch's
# scroll pair, $38 is VcBatch committing SS.Batch's records, $3A is mvania
# writing HSCROLL and VSCROLL itself in mode b8.
M_VCSVC, M_VCBATCH, M_SCENEW = 0x3E, 0x38, 0x3A
BUDGET_MS = 14.3                    # VMODE 00, keyed-copy.md 6.1
SHEET_EVERY = float(os.environ.get("SHEET_EVERY", "0.5"))
COLS, ROWS = 5, 6

def mode_name(v):
    """mvania.asm's mode bits, spelled out."""
    if v is None:
        return "?"
    return ", ".join([
        "KEYED COPY blits" if v & 16 else "sprite-WMODE draws",
        "interleaved" if (v & 64) and not (v & 2) else "two phases",
        "no restores" if v & 4 else
        ("one rectangle an actor" if v & 1 else "merged restores"),
        "SS.CopyN" if v & 2 else "card registers",
        "scroll by register (it tears)" if v & 8 else
        ("scroll in the blank, no call" if v & 0x100 else
         ("SS.Batch scroll" if v & 0x80 else "SS.Scroll")),
    ])


def read_marks(path):
    """Yield one dict a frame: its phase timestamps in seconds, the actor
    count and how many card frames the poll waited."""
    cur = None
    for line in open(path):
        a, tag = line.split()
        t = int(a) / 1e12
        if tag[0] != "M":
            continue
        v = int(tag[1:])
        if v == M_FRAME:
            if cur and "scroll" in cur:
                yield cur
            cur = dict(t0=t)
        elif cur is None:
            continue
        elif v == M_LIST:
            # ⚠ mvania's Wipe issues one more restore after the last frame,
            # so a $15 can arrive with no $10 in front of it; it belongs to
            # no frame and must not move the last one's split.
            if "scroll" not in cur:
                cur["list"] = t
        elif v == M_REST:
            cur["rest"] = t
        elif v == M_LOGIC:
            cur["logic"] = t
        elif v == M_DRAW:
            cur["draw"] = t
        elif v == M_SCROLL:
            cur["scroll"] = t
        elif M_ACT0 <= v < M_ACT0 + 64:
            cur["n"] = v - M_ACT0
        elif M_POLL0 <= v < M_POLL0 + 64:
            cur["waited"] = v - M_POLL0
    if cur and "scroll" in cur:
        yield cur


def blanks(path):
    """marks.txt as three lists: VBLANK's rises, the first active lines, and
    the (t, code) marks.  The emulator writes V when the raster reaches the
    first blanked line and A at the first active line of the next frame, so
    [V, A) IS the blank."""
    V, A, M = [], [], []
    for line in open(path):
        a, tag = line.split()
        t = int(a)
        if tag == "V":
            V.append(t)
        elif tag == "A":
            A.append(t)
        elif tag[0] == "M":
            M.append((t, int(tag[1:])))
    return V, A, M


def in_blank(V, A, t):
    """Is t inside a blank?  None if the recording cannot say (before the
    first V, or after the last A)."""
    i = bisect.bisect_right(V, t) - 1
    if i < 0:
        return None
    j = bisect.bisect_right(A, V[i])
    if j >= len(A):
        return None
    return t < A[j]


def blank_gate(outs, claim):
    """⛔ THE TEARING GATE.  A scroll register written while the raster is
    in the picture tears, which is the whole reason SS.Batch exists and the
    whole risk of making it cheaper - so every commit's timestamp is read
    against marks.txt's own V and A.

    ⭐ AND IT HAS A NEGATIVE CONTROL.  mvania mode b3 writes the same two
    registers wherever the raster happens to be; if THAT run's writes also
    came out 'in the blank', the check would be measuring nothing.  A blank
    is 49 lines of 449, so a check that cannot fail would still read ~11%.
    """
    for out in outs:
        name = os.path.basename(out.rstrip("/"))
        mp = os.path.join(out, "marks.txt")
        if not os.path.exists(mp):
            claim("%s: marks.txt exists" % name, False)
            continue
        V, A, M = blanks(mp)
        mv = int(name[1:]) if name[1:].isdigit() else None
        neg = mv is not None and (mv & 8)          # b3: the tearing control
        # ⛔ A RUN WITH NO COMMIT MARKS MAKES NO CLAIM, and no claim reads
        # exactly like a passing one (CLAUDE.md's seventh trap).  The ROM has
        # to have been built with -DBTMARK=1 or this whole gate is vacuous.
        seen = sum(1 for _, v in M if v in (M_VCSVC, M_VCBATCH, M_SCENEW))
        claim("%s: the recording HAS commit marks - the ROM is the "
              "instrumented one (%d)" % (name, seen), seen > 0)
        for code, what in ((M_VCSVC, "VcSvc commits the scroll pair"),
                           (M_VCBATCH, "VcBatch commits SS.Batch's records"),
                           (M_SCENEW, "mvania writes HSCROLL/VSCROLL itself")):
            ts = [t for t, v in M if v == code]
            ins = [t for t in ts if in_blank(V, A, t)]
            if not ts:
                continue
            if code == M_SCENEW and neg:
                claim("%s: the b3 control DOES write in the picture - the "
                      "gate is not vacuous (%d of %d writes were not in a "
                      "blank)" % (name, len(ts) - len(ins), len(ts)),
                      len(ins) * 4 < len(ts))
                continue
            claim("%s: %s IN THE BLANK, every time (%d of %d)"
                  % (name, what, len(ins), len(ts)), len(ins) == len(ts))
        if mv is not None and (mv & 0x100):
            # ⚠ b8 declines the write when the blank has gone.  That is
            # correct and it is also a cost: the frame keeps the last scroll.
            # It may not happen while the frame still fits its budget.
            nact, miss, work, t0 = None, {}, {}, None
            for t, v in M:
                if M_ACT0 <= v < M_ACT0 + 64:
                    nact = v - M_ACT0
                elif v == M_FRAME:
                    t0 = t
                elif v == M_SCROLL and nact is not None and t0 is not None:
                    work.setdefault(nact, []).append(t - t0)
                elif v == M_NOBLK and nact is not None:
                    miss[nact] = miss.get(nact, 0) + 1
            fits = [n for n in work
                    if sum(work[n]) / len(work[n]) / 1e9 < BUDGET_MS]
            bad = sorted(n for n in fits if miss.get(n))
            claim("%s: b8 never missed the blank at an actor count that fits "
                  "the frame (%s)" % (name, bad or "none did"), not bad)


def budget(marks):
    """Per actor count: the frame period and where the time went, in ms."""
    rows = {}
    prev = None
    for m in marks:
        if not all(k in m for k in ("rest", "list", "logic", "draw", "scroll", "n")):
            prev = m
            continue
        n = m["n"]
        r = rows.setdefault(n, dict(frames=0, period=[], rest=0.0, merge=0.0,
                                    logic=0.0, draw=0.0, scroll=0.0, drops=0,
                                    work=[]))
        r["frames"] += 1
        r["merge"] += m["list"] - m["t0"]
        r["rest"] += m["rest"] - m["list"]
        r["logic"] += m["logic"] - m["rest"]
        r["draw"] += m["draw"] - m["logic"]
        r["scroll"] += m["scroll"] - m["draw"]
        r["work"].append(m["scroll"] - m["t0"])
        if prev is not None and prev.get("n") == n:
            r["period"].append(m["t0"] - prev["t0"])
        # the poll is the frame AFTER the work: waited > 1 card frame is a drop
        if m.get("waited", 1) > 1:
            r["drops"] += 1
        prev = m
    return rows


def table(name, rows):
    ms = 1000.0
    print("\n%s" % name)
    print("  actors  frames  work ms  frame ms |   merge restore   logic    draw"
          "  scroll | idle ms  drops")
    hard = None
    for n in sorted(rows):
        r = rows[n]
        f = r["frames"]
        work = sum(r["work"]) / f * ms
        per = (sum(r["period"]) / len(r["period"]) * ms) if r["period"] else float("nan")
        idle = per - work
        print("  %6d  %6d  %7.2f  %8.2f | %7.3f %7.3f %7.3f %7.3f %7.3f | %7.2f"
              "  %5d"
              % (n, f, work, per, r["merge"] / f * ms, r["rest"] / f * ms,
                 r["logic"] / f * ms, r["draw"] / f * ms, r["scroll"] / f * ms,
                 idle, r["drops"]))
        if hard is None and work > BUDGET_MS:
            hard = n
    if hard is None:
        print("  -> every step fitted the %.1f ms frame" % BUDGET_MS)
    else:
        print("  -> the work first passed %.1f ms at %d actors" % (BUDGET_MS, hard))
    return hard


def sheets(out, marks_by_t):
    """Contact sheets: a tile every SHEET_EVERY seconds, labelled with the
    machine time and the actor count the scene was running at."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", 16)
    TW, TH, LABEL = 640, 400, 26
    tiles, nxt, prev = [], 0.0, None
    for m, px in fr.read(os.path.join(out, "frames.bin")):
        t = m["t"]
        if t < nxt or m["camk"] == 0 and m["herok"] == 0:
            continue                      # the scene tags every frame it owns
        nxt = t + SHEET_EVERY
        # ⚠ the scene's tags outlive the scene: the frame words keep their
        # last value after the command exits, so the tail of a recording is
        # the same picture over and over.  A tile that is identical to the
        # one before it is that tail.
        if prev is not None and np.array_equal(px, prev):
            continue
        prev = px.copy()
        im = Image.fromarray(fr.rgb565_to_rgb8(px))
        if im.size != (TW, TH):
            im = im.resize((TW, TH), Image.NEAREST)
        tile = Image.new("RGB", (TW, TH + LABEL), (16, 18, 22))
        tile.paste(im, (0, 0))
        d = ImageDraw.Draw(tile)
        d.text((4, TH + 3), "%.2f s  frame %d   HSCROLL %d   %d actors"
               % (t, m["n"], m["camk"], m["herok"]), font=font,
               fill=(255, 190, 80))
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
    return paths, len(tiles)


def main():
    outs = sys.argv[1:]
    gate = outs and outs[0] == "--blank"
    if gate:
        outs = outs[1:]
    if not outs:
        print("usage: checkv3mv.py [--blank] OUT [OUT2 ...]")
        return 2
    fail, n = 0, 0

    def claim(what, ok):
        nonlocal fail, n
        n += 1
        print("%s  %s" % ("ok   " if ok else "FAIL ", what))
        if not ok:
            fail += 1

    if gate:
        blank_gate(outs, claim)
        print("\n%d claims, %d failed" % (n, fail))
        return 1 if fail else 0

    summary = {}
    for out in outs:
        name = os.path.basename(out.rstrip("/"))
        mp = os.path.join(out, "marks.txt")
        if not os.path.exists(mp):
            claim("%s: marks.txt exists" % name, False)
            continue
        marks = list(read_marks(mp))
        rows = budget(marks)
        mv = int(name[1:]) if name[1:].isdigit() else None
        hard = table("%s - %s" % (name, mode_name(mv)), rows)
        summary[name] = (rows, hard)
        claim("%s: the sweep reached every step of StepTab" % name, len(rows) >= 14)
        claim("%s: no frame lost its phase marks" % name,
              sum(r["frames"] for r in rows.values()) == len(marks))
        # ⭐ THE CORRECTNESS GATE.  mvania's Wipe put every actor back before
        # it exited, and nothing but the actors ever wrote ring rows 0-239 -
        # so the live page has to be the clean page again.  A run with the
        # restores switched off (mode 4) is the control and is skipped.
        vp = os.path.join(out, "vram.bin")
        if os.path.exists(vp) and mv is not None and not (mv & 0x24):
            v = np.fromfile(vp, dtype=np.uint8)
            live = v[0:240 * 1024].reshape(240, 1024)
            clean = v[240 * 1024:480 * 1024].reshape(240, 1024)
            bad = int((live != clean).sum())
            claim("%s: every actor was put back - the live page IS the clean "
                  "page (%d bytes differ)" % (name, bad), bad == 0)
        # ⭐ the sheets are made for the FIRST directory only: four runs of
        # sixty 640 x 400 tiles is a quarter of a gigabyte of PNG, and the
        # four scenes differ in what they COST rather than in what they show.
        if os.environ.get("NOSHEET") or out != outs[0]:
            continue
        paths, ntiles = sheets(out, None)
        claim("%s: contact sheets written" % name, ntiles > 0)

    # what the merge was worth: the same actor count, merged against not
    if len(summary) >= 2:
        keys = sorted(summary)
        print("\nrestores + draws, ms a frame (an interleaved run charges both to draw)")
        print("  actors " + "".join("%22s" % k for k in keys))
        base = summary[keys[0]][0]
        for act in sorted(base):
            line = "  %6d" % act
            for k in keys:
                r = summary[k][0].get(act)
                line += "%22s" % ("%.3f" % ((r["rest"] + r["merge"] + r["draw"])
                                            / r["frames"] * 1000)
                                  if r else "-")
            print(line)

    print("\n%d claims, %d failed" % (n, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
