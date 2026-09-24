#!/usr/bin/env python3
"""Check what reached the connector against what the demo was supposed to draw.

    python3 software/archive/demo/tools/checkdemo.py OUT [BUILD]

OUT is demo_tb's output directory, BUILD software/demo/build. Every claim is
printed "ok" or "FAIL", and the exit code is the answer.

OUT may equally be emu/run-emu.sh's directory: the emulator writes the same
frames.bin.

⭐ THE SHOW IS COMPARED PIXEL FOR PIXEL, AT EVERY CHECKPOINT. show.Model ran
the script and kept a picture at each CHECK; the bench read the checkpoint word
at each frame's first and last active dots. A frame whose two readings agree
was scanned while nothing was drawn, and it must be that picture through its
palette - with the raster phase its display list held, if it has one, and only
if a list was running at line 1. Every checkpoint must have reached the
connector at least once.

⭐ AND SO IS THE GAME, against a model that does not share code with the 6809.
mkgame.py's render() draws world + hero for a (camera record, hero record) pair
in Python; the bench read those two record numbers out of the SIMM at each
frame's last active dot. So a frame is right when the machine drew what its
own state says it was showing - scroll, strips, tiles, hero composite, flip -
and the checker also asks whether that state moved like a game: the camera
record advancing one frame per frame, and how often it did not.
"""
import os, pickle, sys
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import frames as fr
import mkgame
import show

out = sys.argv[1]
build = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", "build")
fails = 0


def ok(good, msg):
    global fails
    print(("ok    " if good else "FAIL  ") + msg)
    if not good:
        fails += 1


pal = fr.palette565()
inv = np.full(65536, -1, dtype=np.int32)
inv[pal] = np.arange(256)
model = np.load(os.path.join(build, "model.npz"))

# the show's pictures: show.Model's, one per CHECK in the script
shows = np.load(os.path.join(build, "show.npz"))
rasts = pickle.load(open(os.path.join(build, "show_rast.pkl"), "rb"))
names = dict(l.rstrip("\n").split(" ", 1) for l in open(os.path.join(build, "checks.txt")))
pictures = {int(k): dict(idx=shows[f"idx{k}"], pal=shows[f"pal{k}"], list=bool(shows[f"lst{k}"]),
                         **rasts.get(int(k), dict(rast=None, wave=None, ring=None))) for k in shows["ids"]}
seen, exact, bad_show = {}, {}, []
n_rast = n_rast_skip = n_nolist = 0
n_game = game_exact = game_stale = 0
game_bad_frames = []
first_bad = None
cam_steps = {}
prev_camk = None
last_missed = 0
dbl_bad = 0
n_total = 0
lruns = []
for meta, px in fr.read(os.path.join(out, "frames.bin")):
    n_total += 1
    lruns.append(meta["lrun"])
    ck0, ck1 = meta["ck"]
    if ck0 and ck0 == ck1 and ck0 in pictures and meta["prog"] != 0x85:
        pic = pictures[ck0]
        ph = None
        if pic["list"] and not meta["lrun"]:
            # the picture needs a display list and none was running at line 1
            n_nolist += 1
            continue
        if pic["rast"] is not None or pic["wave"] is not None:
            if not (meta["ph"][0] and meta["ph"][0] == meta["ph"][1] and meta["lrun"]):
                n_rast_skip += 1
                continue
            ph = meta["ph"][0] - 1
            n_rast += 1
        want = show.picture_rgb(pic, ph)
        seen[ck0] = seen.get(ck0, 0) + 1
        if px.shape == want.shape and np.array_equal(px, want):
            exact[ck0] = exact.get(ck0, 0) + 1
        else:
            bad_show.append((meta["n"], ck0, ph, int(np.count_nonzero(px != want)) if px.shape == want.shape else -1))
            if first_bad is None:
                first_bad = ("show", meta, px, want)
    if meta["prog"] == 0x85 and meta["vmode"] == 0 and px.shape == (400, 640) and meta["ck"] == (0, 0):
        n_game += 1
        if not np.array_equal(px[0::2], px[1::2]):
            dbl_bad += 1
        idx = inv[px[0::2]]
        k, hk = meta["camk"], meta["herok"]
        if k >= len(model["frames"]) or (hk != 0xFFFF and hk >= len(model["frames"])):
            game_bad_frames.append((meta["n"], k, hk, -1))
            continue
        want = mkgame.render(model, k, None if hk == 0xFFFF else hk) if hk != 0xFFFF else \
            mkgame.render({**{f: model[f] for f in model.files}, "sprites": np.full_like(model["sprites"], int(model["key"]))}, k)
        bad = int(np.count_nonzero(idx != want))
        if bad == 0:
            game_exact += 1
        elif int(model["frames"][k][0]) % 8 == 4 and np.array_equal(
                idx, mkgame.render_cells(model, k, None if hk == 0xFFFF else hk, stale_half=True)):
            # ⚠ the card's cell-mode defect, reproduced exactly: see mkgame.render_cells
            game_stale += 1
        else:
            game_bad_frames.append((meta["n"], k, hk, bad))
            if first_bad is None or first_bad[0] != "game":
                if first_bad is None:
                    first_bad = ("game", meta, px, want)
        if prev_camk is not None:
            step = (k - prev_camk) % len(model["frames"])
            cam_steps[step] = cam_steps.get(step, 0) + 1
        prev_camk = k
        last_missed = meta["missed"]

print(f"      {n_total} frames captured; {sum(seen.values())} at a checkpoint, {n_game} of the game")
missing = [k for k in sorted(pictures) if k not in seen]
ok(not missing, f"⭐ every one of the script's {len(pictures)} checkpoints reached the connector"
   + ("" if not missing else f" - never seen: {', '.join(f'{k} ({names[str(k)]})' for k in missing[:6])}"))
ok(not bad_show, f"⭐ every checkpoint frame is show.Model's picture, pixel for pixel: {sum(exact.values())} of "
   f"{sum(seen.values())} frames" + ("" if not bad_show else
   f"; first wrong: frame {bad_show[0][0]}, checkpoint {bad_show[0][1]} ({names[str(bad_show[0][1])]}), "
   f"raster phase {bad_show[0][2]}, {bad_show[0][3]} pixels"))
ok(n_nolist <= max(1, sum(seen.values()) // 100),
   f"a checkpoint that needs a display list found one running in all but {n_nolist} of its frames (1% may not)")
# A list that is running is restarted every frame, so a gap of one or two frames
# between two frames with a list is a frame that lost its list and showed its
# lines unsplit. Until gui.asm's lyield, the paint scroll lost every other one.
n_listed, n_dropped, i = sum(lruns), 0, 0
while i < len(lruns):
    j = i
    while j < len(lruns) and not lruns[j]:
        j += 1
    if 0 < i < j < len(lruns) and j - i <= 2:
        n_dropped += j - i
    i = max(j, i + 1)
ok(n_dropped <= n_listed * 3 // 100,
   f"⭐ a running display list is started every frame: {n_dropped} frames dropped it between frames that had "
   f"it, of {n_listed} with it (3% may)")
if n_rast or n_rast_skip:
    ok(n_rast > 0 and n_rast_skip <= n_rast // 10,
       f"⭐ the raster bars and the paint program's wave: {n_rast} frames judged at the phase their list held, "
       f"{n_rast_skip} with no list started in time (no more than 10% may be)")
if n_game:
    ok(dbl_bad == 0, f"VMODE 00 doubles every row in all {n_game} game frames ({dbl_bad} do not)")
    ok(game_stale == 0,
       f"⛔ no game frame shows the cell-mode handover defect - cells drawn half from the previous cell's "
       f"code at HSCROLL[2:0] = 4 ({game_stale} of {n_game} frames are exactly that picture)")
    ok(game_exact + game_stale == n_game,
       f"and nothing else is wrong: every game frame is either the model or exactly the defect above "
       f"({n_game - game_exact - game_stale} are neither)")
    ok(game_exact == n_game,
       f"⭐ every game frame is the model's world + hero for the camera and hero records the SIMM held: {game_exact} of {n_game} exact"
       + ("" if not game_bad_frames else f"; first wrong: frame {game_bad_frames[0][0]} (camera {game_bad_frames[0][1]}, hero {game_bad_frames[0][2]}, {game_bad_frames[0][3]} pixels)"))
    total = sum(cam_steps.values())
    print("      camera record step per displayed frame: " +
          ", ".join(f"{s}: {c}" for s, c in sorted(cam_steps.items())))
    ok(total == 0 or cam_steps.get(1, 0) >= 0.9 * total,
       f"the camera advances one record per frame in {cam_steps.get(1, 0)} of {total} frame pairs - a game running at the card's frame rate")
    print(f"      the flip found the blank already over {last_missed} times")

# ---- the blank's budget: when each flip ran against VBLANK and the first active dot
marks_path = os.path.join(out, "marks.txt")
if os.path.exists(marks_path):
    vs, acts, flips, ticks_e = [], [], [], []
    start = None
    for line in open(marks_path):
        t, tag = line.split()[:2]
        t = int(t) / 1e9                                   # ms
        if tag == "V": vs.append(t)
        elif tag == "A": acts.append(t)
        elif tag == "M1": start = t
        elif tag == "M2" and start is not None:
            flips.append((start, t)); start = None
        elif tag == "M4":
            ticks_e.append(int(line.split()[2]))
    import bisect
    over, delays, durs = 0, [], []
    for a, b in flips:
        i = bisect.bisect_right(vs, a) - 1
        if i < 0: continue
        j = bisect.bisect_right(acts, vs[i])
        nxt = acts[j] if j < len(acts) else float("inf")
        delays.append(a - vs[i]); durs.append(b - a)
        if b > nxt: over += 1
    if flips:
        print(f"      {len(flips)} flips: start {min(delays):.2f}-{max(delays):.2f} ms after VBLANK rose, "
              f"take {min(durs):.2f}-{max(durs):.2f} ms (median {sorted(durs)[len(durs)//2]:.2f}); "
              f"the blank is {acts[1]-vs[1] if len(acts) > 1 and len(vs) > 1 else float('nan'):.2f} ms to the first active dot")
        ok(over <= len(flips) // 50,
           f"hero flips finish before the frame's first active dot ({over} of {len(flips)} ran into the picture; "
           f"no more than 2% may - a flip that waits out a replayer tick can)")
    if ticks_e:
        te = sorted(ticks_e)
        print(f"      the replayer, from /FIRQ on the 6809E: {len(te)} ticks, {te[0]}-{te[-1]} E cycles "
              f"(median {te[len(te)//2]}, mean {sum(te)/len(te):.0f}) - {100*sum(te)/len(te)/(2097917/50.0):.1f}% of the CPU at 50 Hz")

if first_bad is not None:
    from PIL import Image
    kind, meta, px = first_bad[0], first_bad[1], first_bad[2]
    Image.fromarray(fr.rgb565_to_rgb8(px)).save(os.path.join(out, f"first_bad_{kind}.png"))
    want = first_bad[3]
    if kind == "game":
        want = pal[np.repeat(want, 2, axis=0)]
    if want.shape == px.shape:
        Image.fromarray(fr.rgb565_to_rgb8(want)).save(os.path.join(out, f"first_bad_{kind}_want.png"))
        diff = (px != want)
        Image.fromarray((diff * 255).astype(np.uint8)).save(os.path.join(out, f"first_bad_{kind}_diff.png"))
    print(f"      wrote {out}/first_bad_{kind}.png (frame {meta['n']})")

sys.exit(1 if fails else 0)
