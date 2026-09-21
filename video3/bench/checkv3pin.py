#!/usr/bin/env python3
"""checkv3pin.py OUT [OUT2 ...] - the pinball scene's gates, its budget, its sheets.

Each OUT is one emulator run of `pinball` (video3/bench/run-v3pin.sh) holding
marks.txt, and usually frames.bin and vram.bin.  This reads them and makes
four different kinds of claim:

  ⛔ THE VRAM GATE.  The table is decided by DATA, not by what the run
     happened to do - and since 2026-09-21 the data is ⭐ THE FILE THE
     MACHINE READ.  Ring rows 0..511, columns 0..639 must be pcbtable.pic,
     byte for byte, 327,680 of them; the spare columns must hold the keyed
     art and the eight flipper frames composed out of that same picture.  A
     load to the wrong VRAM address, a truncated load, a dropped restore, a
     save-behind taken from the wrong row, a keyed copy that wrote its holes
     or a composition that took the wrong background each fail it.
     ⭐ The expected VRAM now IS the file, which is both a stronger gate than
     the block composition it replaced and a much shorter one to write.
  ⭐ THE LOAD, which is the new path and therefore the new thing that can be
     wrong: $1B, $1C and $1D bracket the palette and the picture, so the
     bench reports the seconds and the KiB/s the machine really managed.
  ⭐ THE COLLISION GRID REACHED THE PHYSICS.  Art and collision are separate
     files now, so "the table looks right" says nothing about whether the
     ball can hit any of it.  Every Hit marks its KIND ($01..$0C) and the
     union over the runs must cover every kind pcbtable.json's colmap
     carries - the one claim that fails if the grid never arrived.
  ⭐ THE LAMP GATE, which is the one this scene needs and the other two did
     not.  Its lamps and its six-digit score are PALETTE entries, so nothing
     they do reaches a VRAM dump at all - the whole feature is invisible to
     the gate above.  It is read off the RECORDING instead: the reserved LUT
     entries' colours are not in the art palette (mkpinball.py asserts it), so
     a pixel of exactly that colour in a recorded frame can only be that
     entry, and "the lamp is lit in some frames and out in others" is a claim
     about the picture the card really produced.
  ⭐ THE BUDGET.  The $FF2E marks, timestamped in picoseconds, split into the
     scroll, the lamps, the sprite shape, the physics, the flippers and the
     balls.
  ⛔ THE TEARING GATE.  VSCROLL has to reach the card INSIDE the blank, which
     is the whole reason a driver call ever did it.

⛔ Its exit code is the answer.

  --gate-must-fail   invert the VRAM gate: the run is a MUTATION and the gate
                     is required to catch it.  This is what makes the gate
                     worth anything (CLAUDE.md: a green check proves nothing
                     on its own).
"""
import base64
import bisect
import hashlib
import json
import os
import shutil
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "software", "demo", "tools"))
import frames as fr  # noqa: E402

# pinball.asm's marks
M_FRAME, M_SCROLL, M_LAMPS, M_SPRITE = 0x10, 0x11, 0x12, 0x13
M_PHYS, M_FLIPS, M_ACTORS, M_SCALL = 0x14, 0x15, 0x16, 0x17
M_BEGIN, M_LAST, M_WIPED, M_NOBLK = 0x18, 0x19, 0x1A, 0x1E
M_PALLD, M_PICO, M_PICD = 0x1B, 0x1C, 0x1D
M_POLL0, M_ACT0, M_CAMH, M_CAML, M_SLOT0, M_NIB = 0x40, 0x60, 0x80, 0xA0, 0xC0, 0xE0
# ⭐ $01..$0C: a ball met a cell of that collision kind.  ⚠ They are below
# M_FRAME and outside every other range, so frames_of() ignores them.
M_KIND0, M_KINDN = 0x01, 0x0C
BUDGET_MS = 14.3                    # VMODE 00, keyed-copy.md §6.1
# ⚠ THREE MILLISECONDS, WHERE monster USES TWO.  A frame declines the blank
# because THE FRAME BEFORE IT overran, so the in-sync set is "frames whose
# predecessor left this much margin".  This scene's per-frame work is
# DATA-DEPENDENT in a way monster's is not - a ball in a bumper nest costs
# several collisions where a ball in free air costs none - so the same
# nominal step varies by about a millisecond and two is inside the noise.
# At three, nothing in a fitting step declines; the whole-run numbers are
# printed beside the claim either way.
SYNCMS = 3.0                        # the margin a frame leaves the next one
SHEET_EVERY = float(os.environ.get("SHEET_EVERY", "0.75"))
COLS, ROWS = 3, 4

PHASES = [("scroll", M_FRAME, M_SCROLL), ("lamps", M_SCROLL, M_LAMPS),
          ("sprite", M_LAMPS, M_SPRITE), ("physics", M_SPRITE, M_PHYS),
          ("flips", M_PHYS, M_FLIPS), ("balls", M_FLIPS, M_ACTORS),
          ("oscall", M_ACTORS, M_SCALL)]


def mode_name(v):
    if v is None:
        return "?"
    bits = [
        "SS.Scroll" if v & 1 else "⭐ VSCROLL written in the blank, no call",
        "⛔ NO PALETTE WRITES" if v & 2 else "lamps and score in the LUT",
        "no restores" if v & 4 else "save-behind restores",
        "flippers blitted EVERY frame" if v & 0x80 else "flippers blitted on change",
    ]
    if v & 8:
        bits.append("no Wipe")
    if v & 0x10:
        bits.append("SWEEP")
    if v & 0x20:
        bits.append("⛔ MUTATION: the save-behind is one row low")
    if v & 0x40:
        bits.append("⛔ MUTATION: ball 1 is never restored")
    if v & 0x100:
        bits.append("⛔ MUTATION: the picture is loaded ONE VRAM ROW LOW")
    if v & 0x200:
        bits.append("⛔ MUTATION: the load is TRUNCATED")
    return ", ".join(bits)


def read_marks(path):
    """marks.txt: VBLANK's rises, the first active lines, and (t_ns, code)."""
    V, A, M = [], [], []
    for line in open(path):
        # ⚠ THE LAST LINE CAN BE HALF A LINE: the emulator stops on
        # SERIAL_STOP and does not always flush marks.txt's tail.
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
    i = bisect.bisect_right(V, t) - 1
    if i < 0:
        return None
    j = bisect.bisect_right(A, V[i])
    if j >= len(A):
        return None
    return t < A[j]


def frames_of(M):
    """One dict a frame: its phase timestamps in ns, the ball counts, VSCROLL
    and how many card frames the poll waited."""
    out, cur, cam = [], None, [0, 0]
    for t, v in M:
        if v == M_FRAME:
            if cur and M_SCALL in cur:
                out.append(cur)
            cur = {M_FRAME: t, "cam": cam[0] << 4 | cam[1]}
        elif cur is None:
            continue
        elif v in (M_SCROLL, M_LAMPS, M_SPRITE, M_PHYS, M_FLIPS, M_ACTORS, M_SCALL):
            cur[v] = t
        elif M_ACT0 <= v < M_ACT0 + 32:
            cur["n"] = v - M_ACT0
        elif M_SLOT0 <= v < M_SLOT0 + 32:
            cur["slots"] = v - M_SLOT0
        elif v == M_NOBLK:
            cur["declined"] = True
        elif M_POLL0 <= v < M_POLL0 + 32:
            cur["waited"] = v - M_POLL0
        elif M_CAMH <= v < M_CAMH + 32:
            cam[0] = v - M_CAMH
            cur["cam"] = cam[0] << 4 | cam[1]
        elif M_CAML <= v < M_CAML + 32:
            cam[1] = v - M_CAML
            cur["cam"] = cam[0] << 4 | cam[1]
    if cur and M_SCALL in cur:
        out.append(cur)
    return out


def score_of(M, ndig):
    """The ndig nibble marks the scene emits after its Wipe."""
    nib = [v - M_NIB for _, v in M if M_NIB <= v < M_NIB + 16]
    if len(nib) < ndig:
        return None
    return "".join(str(d) for d in nib[-ndig:])


# ───────────────────────────────────────── the expected VRAM, from the DATA
def d64(s, shape=None):
    a = np.frombuffer(base64.b64decode(s), dtype=np.uint8)
    return a.reshape(shape) if shape else a


def expected_vram(j):
    """⭐ WHAT THE CARD MUST HOLD.  The table is pcbtable.pic ITSELF - the
    same 327,680 bytes the SD card carries and the machine read - and the
    bank is built out of it and pinball.json's keyed art.

    The ROM and this share the DATA and no code (bench/README.md's rule): the
    ROM reads the file off /SD0/DATA, and this reads it off the disk that
    wrote the card.  ⛔ And the sha256 in pinball.json is checked first, so a
    picture that was regenerated after the ROM was built fails LOUDLY here
    rather than as 300,000 mismatched bytes.
    """
    TW, TH = j["tw"], j["th"]
    cb = j["c_bank"]
    fw, fh, nff = j["flipw"], j["fliph"], j["nflipf"]
    bw_, bh, nbf = j["ballw"], j["ballh"], j["nballf"]
    ballart = d64(j["ballart"], (bh, nbf * bw_))
    flipart = d64(j["flipart"], (2 * fh, nff * fw))
    pic = np.fromfile(os.path.join(HERE, j["pic"]), dtype=np.uint8)
    if pic.size != TW * TH:
        raise SystemExit("FAIL  %s is %d bytes, not %d" % (j["pic"], pic.size, TW * TH))
    pic = pic.reshape(TH, TW)

    v = np.zeros((512, 1024), dtype=np.uint8)
    know = np.zeros((512, 1024), dtype=bool)

    # ── ⭐ THE TABLE, which is the file
    v[0:TH, 0:TW] = pic
    know[:, 0:TW] = True

    # ── the keyed art, which the ROM uploads verbatim out of its own module
    v[j["r_ball"]:j["r_ball"] + bh, cb:cb + nbf * bw_] = ballart
    know[j["r_ball"]:j["r_ball"] + bh, cb:cb + nbf * bw_] = True
    v[j["r_fart"]:j["r_fart"] + 2 * fh, cb:cb + nff * fw] = flipart
    know[j["r_fart"]:j["r_fart"] + 2 * fh, cb:cb + nff * fw] = True

    # ── ⭐ THE EIGHT COMPOSED FLIPPER FRAMES, exactly as Compose builds them:
    # the LOADED table's own pixels at the flipper's home rectangle, with the
    # keyed flipper art blitted over them.  ⚠ Taken BEFORE the rest frames are
    # put back on to the table, because that is the order the ROM runs in; and
    # two bands of four, left over right, which is the ROM's addressing.
    fy = j["flip_y"]
    comp = {}
    for side in (0, 1):
        fx = j["flip_lx"] if side == 0 else j["flip_rx"]
        for f in range(nff):
            tile = v[fy:fy + fh, fx:fx + fw].copy()
            art = flipart[side * fh:(side + 1) * fh, f * fw:(f + 1) * fw]
            tile[art != 0] = art[art != 0]
            comp[(side, f)] = tile
            r, c = j["r_flip"] + side * fh, cb + f * fw
            v[r:r + fh, c:c + fw] = tile
            know[r:r + fh, c:c + fw] = True

    # ── and the table's own flippers, which the Wipe leaves at rest
    for side in (0, 1):
        fx = j["flip_lx"] if side == 0 else j["flip_rx"]
        v[fy:fy + fh, fx:fx + fw] = comp[(side, 0)]

    # ⚠ the save-behind scratch is whatever was last under a ball, so it is
    # the one region nothing can predict.  It stays unknown.
    return v, know


def vram_gate(out, j, claim, must_fail):
    name = os.path.basename(out.rstrip("/"))
    vp = os.path.join(out, "vram.bin")
    if not os.path.exists(vp):
        return
    got = np.fromfile(vp, dtype=np.uint8).reshape(512, 1024)
    exp, know = expected_vram(j)
    diff = (got != exp) & know
    bad = int(diff.sum())
    where = ""
    if bad:
        rows = np.where(diff.any(1))[0]
        cols = np.where(diff.any(0))[0]
        where = " - first at ring row %d, column %d; %d rows, %d columns" % (
            rows[0], cols[0], len(rows), len(cols))
    what = ("%s: ⛔ THE MUTATION IS CAUGHT - VRAM is NOT what the table's data "
            "says (%d bytes differ%s)" if must_fail else
            "%s: ⭐ every byte of the table is pcbtable.pic itself, and the "
            "keyed art and the eight composed flipper frames are what the "
            "data says (%d differ%s)")
    claim(what % (name, bad, where), (bad > 0) if must_fail else (bad == 0))
    if must_fail:
        return
    # ⭐ AND THE HARDWARE SPRITE'S SHAPE, as a separate claim: it is one of the
    # four the generator emitted, and which one depends on where the ball's
    # highlight had turned to - so the claim is membership and not equality.
    spr = d64(j["spr"], (j["ngait"], 64))
    held = got[j["r_spr"], j["c_spr"]:j["c_spr"] + 64]
    claim("%s: the hardware sprite's 64 shape bytes at ring row %d are one of "
          "the %d the generator emitted" % (name, j["r_spr"], j["ngait"]),
          any((held == spr[i]).all() for i in range(j["ngait"])))


# ──────────────────────────────────── ⭐ the lamps, read off the RECORDING
def lamp_gate(out, j, claim, must_fail, mode):
    """The reserved LUT entries do not touch VRAM at all, so the only place
    their effect exists is the picture.  ⭐ mkpinball.py asserts that no art
    colour equals a reserved one, so a pixel of exactly that RGB565 in a
    recorded frame IS that entry - and a lamp that is lit in some frames and
    out in others is proof the commits reached the card."""
    name = os.path.basename(out.rstrip("/"))
    fp = os.path.join(out, "frames.bin")
    if not os.path.exists(fp):
        return
    # ⚠ ONLY THE SCENE'S OWN FRAMES.  The recording starts at reset and the
    # boot, the shell and the screen set-up are in it; a lamp that is out for
    # all of those and lit for half the scene would read as "mostly out".
    V, A, M = read_marks(os.path.join(out, "marks.txt"))
    fs = frames_of(M)
    if not fs:
        return
    t0, t1 = fs[0][M_FRAME] / 1e12, fs[-1][M_SCALL] / 1e12
    want = {}
    for k in range(j["nlamp"]):
        want[("lamp %d lit" % k, j["lampon"][k])] = 0
        want[("lamp %d out" % k, j["lampoff"][k])] = 0
    want[("a score segment lit", j["segon"])] = 0
    want[("a score segment dark", j["segoff"])] = 0
    nfr = 0
    for m, px in fr.read(fp):
        if not (t0 <= m["t"] <= t1 + 0.05):
            continue
        nfr += 1
        seen = set(np.unique(px).tolist())
        for key in want:
            if key[1] in seen:
                want[key] += 1
    if not nfr:
        claim("%s: the recording has frames to read the lamps off" % name, False)
        return
    missing = [k[0] for k, n in want.items() if n == 0]
    lit = [k[0] for k, n in want.items() if n and "lit" in k[0]]
    if mode is not None and mode & 2:
        # ⛔ THE NEGATIVE CONTROL, and without it the gate above could not
        # fail: mode b1 makes no LUT write at all, so every lamp must stay as
        # PalUp left it and not one "lit" colour may reach the picture.
        claim("%s: ⛔ THE CONTROL - with no LUT writes not one lamp or segment "
              "ever lights (%d of %d lit states seen over %d frames%s)"
              % (name, len(lit), len(want) // 2, nfr,
                 ("; LEAKED " + ", ".join(lit)) if lit else ""), not lit)
        return
    claim("%s: ⭐ every reserved LUT entry reached the picture - %d of %d "
          "lamp/segment states were seen over %d frames%s"
          % (name, len(want) - len(missing), len(want), nfr,
             ("; MISSING " + ", ".join(missing)) if missing else ""),
          not missing)
    # ⭐ AND THE CONTROL: the flasher must TOGGLE.  A lamp that is lit in every
    # frame would satisfy the claim above without a single write after the
    # first, so the last lamp pulses on its own and has to be seen both ways.
    fl = j["flash"]
    on = want[("lamp %d lit" % fl, j["lampon"][fl])]
    off = want[("lamp %d out" % fl, j["lampoff"][fl])]
    claim("%s: ... and the flasher TOGGLES - lamp %d is lit in %d frames and "
          "out in %d, of %d" % (name, fl, on, off, nfr),
          0 < on < nfr and 0 < off < nfr)


def load_gate(out, j, claim):
    """⭐ THE LOAD, WHICH IS THE NEW PATH.  $1B says the 512-byte palette is
    in the LUT, $1C that the picture's path is open and $1D that all 327,680
    bytes of it are in VRAM - so the difference is the whole cost of putting
    a 320 KB playfield on the card instead of in a module, measured on the
    machine rather than estimated.

    ⚠ IT IS A CLAIM AND NOT JUST A NUMBER: a scene that silently fell back to
    an empty screen would reach the loop with no $1C at all."""
    name = os.path.basename(out.rstrip("/"))
    mp = os.path.join(out, "marks.txt")
    if not os.path.exists(mp):
        return
    _, _, M = read_marks(mp)
    first = {}
    for t, v in M:
        if v in (M_PALLD, M_PICO, M_PICD) and v not in first:
            first[v] = t
    ok = all(v in first for v in (M_PALLD, M_PICO, M_PICD))
    if ok:
        dt = (first[M_PICD] - first[M_PICO]) / 1e12
        rate = j["tw"] * j["th"] / dt / 1024.0
        print("  the palette and the %d-byte picture came off /SD0/DATA: "
              "%.2f s for the picture, %.1f KiB/s" % (j["tw"] * j["th"], dt, rate))
    else:
        dt, rate = 0.0, 0.0
    claim("%s: ⭐ the table was READ OFF THE CARD - the palette is in the LUT "
          "($1B), the picture's path opened ($1C) and all %d bytes reached "
          "VRAM ($1D) in %.2f s, %.0f KiB/s"
          % (name, j["tw"] * j["th"], dt, rate), ok)


def kinds_of(out):
    """Which collision kinds a run's balls actually met."""
    mp = os.path.join(out, "marks.txt")
    if not os.path.exists(mp):
        return set()
    _, _, M = read_marks(mp)
    return set(v for _, v in M if M_KIND0 <= v <= M_KINDN)


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
    sc = score_of(M, j["ndig"])
    if sc:
        print("  the table scored %s" % sc)
    # ⛔ AND SCORING IS A CLAIM.  Twice now this table has run perfectly,
    # kept its budget, passed its VRAM gate and scored NOTHING FOR EVER - a
    # plunger that bounced instead of firing, and a lane mouth that returned
    # the ball's own speed.  Neither is visible to a gate about pixels or one
    # about microseconds.  ⚠ The six nibble marks are emitted after the Wipe,
    # so a run that did not reach the end has no score at all and fails here.
    claim("%s: ⛔ the table SCORED - %s, and not 000000"
          % (name, sc if sc else "no score marks at all"),
          bool(sc) and sc != "0" * j["ndig"])
    print("  blits  frames  work ms  frame ms | " +
          " ".join("%7s" % p[0] for p in PHASES) + " | idle ms  drops")
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
        print("  %5d  %6d  %7.2f  %8.2f | %s | %7.2f  %5d"
              % (n, c, work, per,
                 " ".join("%7.3f" % (r[p[0]] / c) for p in PHASES),
                 per - work, r["drops"]))
        if hard is None and work > BUDGET_MS:
            hard = n
    if hard is None:
        print("  -> every step fitted the %.1f ms frame" % BUDGET_MS)
    else:
        print("  -> the work first passed %.1f ms at %d blit balls" % (BUDGET_MS, hard))
    # ⭐ THE MOST ACTORS THAT FIT, from the SLOPE rather than from the row the
    # sweep happened to stop on: a ball waiting to be served costs nothing, so
    # the steps are not evenly filled and a weighted least-squares line over
    # them is the honest reading.
    if len(fit) >= 4:
        sw = sum(c for _, _, c in fit)
        mx = sum(n * c for n, _, c in fit) / sw
        my = sum(w * c for _, w, c in fit) / sw
        den = sum(c * (n - mx) ** 2 for n, _, c in fit)
        if den > 0:
            b = sum(c * (n - mx) * (w - my) for n, w, c in fit) / den
            a = my - b * mx
            print("  -> %.3f ms of frame + %.3f ms a blit ball  ⭐ %d of them fit "
                  "the %.1f ms frame (and the sprite ball is free)"
                  % (a, b, int((BUDGET_MS - a) / b), BUDGET_MS))
    claim("%s: every frame carried all seven phase marks" % name,
          len(fs) > 0 and all(all(k in f for _, k, _ in PHASES) for f in fs))
    okn = set(n for n, r in rows.items()
              if sum(r["work"]) / r["frames"] < BUDGET_MS * 0.9)
    fits = [rows[n] for n in okn]
    claim("%s: the frame poll never waited more than one card frame at a ball "
          "count that fits with 10%% to spare (%d frames dropped)"
          % (name, sum(r["drops"] for r in fits)),
          all(r["drops"] == 0 for r in fits))

    # ⛔ THE TEARING GATE, and its negative control
    if mv is not None and not (mv & 1):
        sync, pw = [], None
        for f in fs:
            if pw is None or pw < BUDGET_MS - SYNCMS:
                sync.append(f)
            pw = (f[M_SCALL] - f[M_FRAME]) / 1e9
        wrote = [f for f in sync if not f.get("declined")]
        tot = [f[M_SCROLL] for f in wrote]
        ins = [t for t in tot if in_blank(V, A, t)]
        allw = [f for f in fs if not f.get("declined")]
        allt = [f[M_SCROLL] for f in allw]
        alli = [t for t in allt if in_blank(V, A, t)]
        # ⚠ $11 AND NOT $10: $10 is marked before ScBlank reads VSTAT, so a
        # poll that returns microseconds before the blank marks $10 in the
        # picture and then writes perfectly legally.  $11 is after the stores.
        claim("%s: ⛔ every VSCROLL write is INSIDE the blank - $11 is marked "
              "the instant the stores are done and lands in [V, A) (%d of %d "
              "after a frame that kept its budget; %d of %d over the run)"
              % (name, len(ins), len(tot), len(alli), len(allt)),
              len(ins) == len(tot) and tot)
        late = []
        for t in allt:
            if in_blank(V, A, t):
                continue
            i = bisect.bisect_right(V, t) - 1
            jj = bisect.bisect_right(A, V[i]) if i >= 0 else -1
            if i >= 0 and 0 <= jj < len(A):
                late.append((t - A[jj]) / 1e6)
        claim("%s: ... and a write that missed missed by the check-then-write "
              "window and not by a frame (%d writes, worst %.1f us past the "
              "blank, bound 40)" % (name, len(late), max(late) if late else 0.0),
              all(x < 40 for x in late))
        pic = [t for t, v in M if v == M_ACTORS and in_blank(V, A, t) is False]
        alt = [t for t, v in M if v == M_ACTORS]
        claim("%s: ... and the control says the test can fail: the ball phase "
              "ends in the PICTURE (%d of %d)" % (name, len(pic), len(alt)),
              alt and len(pic) * 4 > len(alt) * 3)
        miss = len(sync) - len(wrote)
        allmiss = len(fs) - len(allw)
        claim("%s: no frame that followed a frame inside its budget ever had "
              "to DECLINE the blank (%d of %d; %d of %d over the whole run)"
              % (name, miss, len(sync), allmiss, len(fs)), miss == 0)
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
            print("  -> the frame poll returns %.0f us into a %.0f us blank "
                  "(%.0f..%.0f), leaving %.0f us of it"
                  % (into[len(into) // 2], bl, into[0], into[-1], bl - into[-1]))
            # ⭐ AND THE LAMPS ARE IN THERE TOO, which is the claim this scene
            # adds: up to sixteen LUT entries after the scroll pair, and they
            # have to fit the same blank or a commit posts to the next HLOAD.
            lam = sorted((f[M_LAMPS] - f[M_SCROLL]) / 1e6 for f in wrote)
            print("  -> the LUT commits take %.0f us at the median and %.0f at "
                  "the worst, of the %.0f the poll leaves"
                  % (lam[len(lam) // 2], lam[-1], bl - into[-1]))
            claim("%s: the scroll pair AND the frame's LUT commits fit the "
                  "blank the poll leaves (%.0f us of work at worst against "
                  "%.0f us of blank)" % (name, lam[-1], bl - into[-1]),
                  lam[-1] < bl - into[-1])

    if sheets_here and os.path.exists(os.path.join(out, "frames.bin")):
        paths = make_sheets(out, fs, j)
        claim("%s: contact sheets written (%d)" % (name, len(paths)), len(paths) > 0)
    return rows


def make_sheets(out, fs, j):
    """⭐ THE SHEETS THE SCENE IS REVIEWED FROM, and no video.

    ⚠ THE TAGS ARE NOT IN THE FRAME RECORD.  This scene makes no driver call,
    so VG.MkCam is not available to it; VSCROLL comes out of marks.txt and the
    two files are joined on the TIMESTAMP, both being picoseconds off the same
    emulator clock (monster's mechanism, optimizations.md §8.1).
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
        d.text((4, TH + 3), "%.2f s   VSCROLL %d of %d   %d blit balls"
               % (t - t0, fs[i]["cam"], j["vsmax"], fs[i].get("n", 0)),
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
    # ⚠ SOMEWHERE DURABLE: /tmp is where the recordings are and they get
    # deleted.  The sheets are the review artefact and they are kept.
    dest = os.environ.get("SHEETDIR")
    if dest and paths:
        os.makedirs(dest, exist_ok=True)
        for p in paths:
            shutil.copy2(p, os.path.join(dest, os.path.basename(p)))
        print("ok    contact sheets copied to %s" % dest)
    return paths


def main():
    outs = list(sys.argv[1:])
    must_fail = "--gate-must-fail" in outs
    if must_fail:
        outs.remove("--gate-must-fail")
    nosheet = bool(os.environ.get("NOSHEET")) or must_fail
    if not outs:
        print("usage: checkv3pin.py [--gate-must-fail] OUT [OUT2 ...]")
        return 2
    j = json.load(open(os.path.join(HERE, "pinball.json")))
    fail, n = 0, 0

    def claim(what, ok):
        nonlocal fail, n
        n += 1
        print("%s  %s" % ("ok   " if ok else "FAIL ", what))
        if not ok:
            fail += 1

    # ⛔ THE ART IS THE ARBITER, AND IT HAS TO BE THE SAME ART.  The ROM was
    # built against pinball.json, which mkpinball.py wrote from pcbtable.pic;
    # if the picture has been regenerated since, the compare below would fail
    # by a third of a megabyte and name a row number.  This names the file.
    pic = os.path.join(HERE, j["pic"])
    got = hashlib.sha256(open(pic, "rb").read()).hexdigest() if os.path.exists(pic) else ""
    claim("%s is the picture the scene was generated against (sha256 %s)"
          % (j["pic"], got[:12]), got == j["pic_sha256"])

    summary, kinds = {}, set()
    for i, out in enumerate(outs):
        rows = budget(out, claim, not nosheet and i == 0, j)
        if rows:
            summary[os.path.basename(out.rstrip("/"))] = rows
        load_gate(out, j, claim)
        kinds |= kinds_of(out)
        vram_gate(out, j, claim, must_fail)
        if not must_fail:
            ap = os.path.join(out, "args.txt")
            mv = int(open(ap).read().split()[0]) if os.path.exists(ap) else None
            lamp_gate(out, j, claim, must_fail, mv)

    # ── ⭐ THE COLLISION GRID REACHED THE PHYSICS, and it is the union over
    # the runs because a three-ball scene is not obliged to visit a drain.
    # ⛔ Without this, a scene whose ColMap was all zeroes would paint a
    # perfect table, keep its budget, pass the VRAM gate and never bounce.
    want = set(int(v) for v in np.unique(d64(j["colmap"])) if v)
    inv = {v: k for k, v in j["kinds"].items()}
    miss = sorted(want - kinds)
    print("      kinds met: " + ", ".join(
        inv[k] for k in sorted(kinds) if k in inv))
    # ⚠ NOT ON A MUTATION RUN: those are 300 frames of one cast and are not
    # obliged to visit a drain, and this claim is about the union over the
    # scene, the sweep and the three controls.
    if not must_fail:
        claim("⭐ every collision kind pcbtable.json's grid carries was MET by "
              "a ball over the runs - %d of %d%s"
              % (len(want & kinds), len(want),
                 ("; NEVER MET " + ", ".join(inv[m] for m in miss)) if miss else ""),
              not miss)

    if len(summary) >= 2:
        keys = sorted(summary)
        print("\nthe whole frame's work, ms, the same scene several ways")
        print("  blits  " + "".join("%16s" % k for k in keys))
        base = summary[keys[0]]
        for a in sorted(base):
            line = "  %5d  " % a
            for k in keys:
                r = summary[k].get(a)
                line += "%16s" % ("%.3f" % (sum(r["work"]) / r["frames"]) if r else "-")
            print(line)

    print("\n%d claims, %d failed" % (n, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
