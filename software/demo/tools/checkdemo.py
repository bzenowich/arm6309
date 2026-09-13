#!/usr/bin/env python3
"""Check what reached the connector against what the demo was supposed to draw.

    python3 software/demo/tools/checkdemo.py OUT [BUILD]

OUT is demo_tb's output directory, BUILD software/demo/build. Every claim is
printed "ok" or "FAIL", and the exit code is the answer.

⭐ THE PICTURE IS COMPARED PIXEL FOR PIXEL. Once the paint has finished, every
640 x 480 frame must be parrots.raw pushed through the palette demo.asm loads -
the whole address path, the VDATA stream, the ring and the LUT, from outside.

⭐ AND SO IS THE GAME, against a model that does not share code with the 6809.
mkgame.py's render() draws world + hero for a (camera record, hero record) pair
in Python; the bench read those two record numbers out of the SIMM at each
frame's last active dot. So a frame is right when the machine drew what its
own state says it was showing - scroll, strips, tiles, hero composite, flip -
and the checker also asks whether that state moved like a game: the camera
record advancing one frame per frame, and how often it did not.
"""
import os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import frames as fr
import mkgame

out = sys.argv[1]
build = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", "build")
fails = 0


def ok(good, msg):
    global fails
    print(("ok    " if good else "FAIL  ") + msg)
    if not good:
        fails += 1


pal = fr.palette565()
pic = np.frombuffer(open(os.path.join(build, "parrots.raw"), "rb").read(), dtype=np.uint8).reshape(480, 640)
pic565 = pal[pic]
inv = np.full(65536, -1, dtype=np.int32)
inv[pal] = np.arange(256)
model = np.load(os.path.join(build, "model.npz"))

n_pic = pic_bad = 0
n_game = game_exact = game_stale = 0
game_bad_frames = []
first_bad = None
cam_steps = {}
prev_camk = None
last_missed = 0
dbl_bad = 0
n_total = 0
for meta, px in fr.read(os.path.join(out, "frames.bin")):
    n_total += 1
    if meta["prog"] == 0x84 and meta["vmode"] == 3:
        n_pic += 1
        if px.shape != (480, 640) or not np.array_equal(px, pic565):
            pic_bad += 1
            if first_bad is None:
                first_bad = ("picture", meta, px)
    if meta["prog"] == 0x85 and meta["vmode"] == 0 and px.shape == (400, 640):
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

print(f"      {n_total} frames captured; {n_pic} of the finished picture, {n_game} of the game")
if n_pic:
    ok(pic_bad == 0, f"⭐ the picture at the connector is parrots.raw through the RGB332 palette, every pixel, in all {n_pic} frames ({pic_bad} differ)")
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
    if kind == "game":
        want = first_bad[3]
        Image.fromarray(mkgame_expand := fr.rgb565_to_rgb8(pal[np.repeat(want, 2, axis=0)])).save(
            os.path.join(out, "first_bad_game_want.png"))
    print(f"      wrote {out}/first_bad_{kind}.png (frame {meta['n']})")

sys.exit(1 if fails else 0)
