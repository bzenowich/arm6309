#!/usr/bin/env python3
"""The video console's claims, from run-vid.sh's emulator runs.

    python3 checkvid.py OUT

OUT holds run-vid.sh's runs, each an emulator output directory:

  OUT/select  /W1 given vtp1 and displayed; /W2 (80 x 30) given vtw2 while not
              displayed; Select /W2; Select /W1
  OUT/kbd     a shell on /W1, typed at on the PS/2 keyboard
  OUT/p2      /W3 (bitmap) given vgp2a and displayed; /W4 given vgp2b while not
              displayed; Select /W4; Select /W3
  OUT/mouse   vgp2a on /W3, then PS/2 mouse packets moving the pointer
  OUT/p3      vgp3 on /W3: the extension escapes, and an ANSI terminal
  OUT/rast    rastbar on /W3: raster bars, a display list rewritten every frame
  OUT/wave    wave on /W3: an HSCROLL warp, the same way
  OUT/game    overworld on /W3: the demo's game on an exclusive tile screen

Every claim prints "ok" or "FAIL", and the exit code is the answer.

⭐ THE PICTURE IS COMPARED PIXEL FOR PIXEL, against vtmodel.py (text screens)
and vgmodel.py (bitmap windows and the pointer) - models that share only the
font, CoWin's default colours and the arrow with the 6809. A frame is the
screen's when every one of its 256,000 (or 307,200) pixels is the model's
RGB565 value.
"""
import os, re, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "demo", "tools"))
import frames as fr
import vtmodel as vm

out = sys.argv[1]
fails = n = 0


def ok(msg, good):
    global fails, n
    n += 1
    print(("ok    " if good else "FAIL  ") + msg)
    if not good:
        fails += 1


def frames_of(run):
    return list(fr.read(os.path.join(out, run, "frames.bin")))


def masks(run):
    """emu's MASK lines: (us, where it began, where the longest ended)."""
    rows = []
    for line in open(os.path.join(out, run, "emu.log")):
        m = re.match(r"MASK\s+([\d.]+) us\s+(\S+) to (\S+)", line)
        if m:
            rows.append((float(m.group(1)), m.group(2), m.group(3)))
    return rows


def console(run):
    return open(os.path.join(out, run, "console.txt"), errors="replace").read()


def emulog(run):
    return open(os.path.join(out, run, "emu.log"), errors="replace").read()


# --------------------------------------------------------------------- select
glyphs = vm.font()
p1 = vm.expected("vtp1").render(glyphs)
w2 = vm.expected("vtw2").render(glyphs)
fs = frames_of("select")
con = console("select")

ok("iniz w1, iniz w2 and both copies ran without an error" + "", "Error" not in con and "error" not in con)
first480 = next((i for i, (meta, px) in enumerate(fs) if meta["h"] == 480), None)
ok(f"Select /W2 put the card in VMODE 01: a 640 x 480 frame appeared (frame {first480})", first480 is not None)
before = [px for meta, px in fs[:first480 or len(fs)] if meta["h"] == 400]
ok("before it, /W1 showed vtp1 exactly - /W2 was drawn in DRAM and never touched the card",
   len(before) > 0 and np.array_equal(before[-1], p1))
w2hits = [meta["n"] for meta, px in fs if meta["h"] == 480 and np.array_equal(px, w2)]
ok(f"/W2 showed vtw2 exactly, repainted from its shadow on Select ({len(w2hits)} frames)", len(w2hits) > 0)
if fs:
    meta, last = fs[-1]
    exact = last.shape == p1.shape and np.array_equal(last, p1)
    nbad = int((last != p1).sum()) if last.shape == p1.shape else -1
    ok(f"Select /W1 again: the last frame is vtp1 exactly, 640 x 400 in VMODE 00 ({nbad} pixels differ)", exact)
    if not exact and last.shape == p1.shape:
        for i, ((g, _), (w, _)) in enumerate(zip(vm.decode(last, 25, glyphs), vm.decode(p1, 25, glyphs))):
            if g != w:
                print(f"      row {i:2d} got  {g.rstrip()}\n             want {w.rstrip()}")
log = emulog("select")
ok("no register write under a span or a display list (graphics.md 7.4, 10.3.3)",
   re.search(r"0 register writes under a list, 0 under a span", log) is not None)
ok("the CPU never ran through empty RAM (WILD)", "WILD" not in log)

# --------------------------------------------------------------------- masked time
ms = masks("select")
coarm = [r for r in ms if r[1].startswith("CoArm+")]
worst = max((r[0] for r in coarm), default=0.0)
ok(f"VidCore's longest IRQ-masked stretch is {worst:.0f} us (a stream chunk; plan 3.4: measured, <= 500 us)",
   0 < worst <= 500)
irq = [r for r in ms if r[1].endswith("+$FEF7")]
worst_irq = max((r[0] for r in irq), default=0.0)
ok(f"every IRQ, the VBL service's batch included, returns within {worst_irq:.0f} us (<= 5 ms): "
   "none is left unclaimed with interrupts masked", 0 < worst_irq <= 5000)
m = re.search(r"CALLTIME ArmIO\+\$[0-9A-F]+: (\d+) calls, longest ([\d.]+) us, mean ([\d.]+) us", log)
calls, svc_max, svc_mean = (int(m.group(1)), float(m.group(2)), float(m.group(3))) if m else (0, 0.0, 0.0)
ok(f"the VBL service itself: {calls} VBLs, the longest {svc_max:.0f} us and the mean {svc_mean:.0f} us "
   "(plan 3.4's budget is 0.5 ms; the palette is not the service's since the card posts a commit to HLOAD)",
   calls > 500 and svc_max <= 500)
kbd = [r for r in ms if r[1].startswith("KbdArm+")]
ok(f"KbdArm's transmit masks /IRQ for {max((r[0] for r in kbd), default=0):.0f} us, at Init only (ps2.md 7.1, <= 3 ms)",
   max((r[0] for r in kbd), default=0) <= 3000)

# --------------------------------------------------------------------- keyboard
kcon = console("kbd")
klog = emulog("kbd")
ok("a shell on /W1 ran the line typed on the PS/2 keyboard: KBD-OK reached /Term",
   re.search(r"/DD:KBD-OK$", kcon, re.M) is not None)
kfs = frames_of("kbd")
typed = False
for meta, px in kfs[::-1]:
    if meta["h"] == 400 and any("echo KBD-OK >/term" in line for line, _ in vm.decode(px, 25, glyphs)):
        typed = True
        break
ok("and /W1's screen shows the line as typed: shift, and a backspace SCF edited out", typed)
ok("no register write under a span or a display list, with the keyboard", "0 register writes under a list, 0 under a span" in klog)

# --------------------------------------------------------------------- P2: bitmap windows
import vgmodel as gm

model = gm.Console()
model.feed(3, gm.stream_p2a())
g3 = model.picture()
model.feed(4, gm.stream_p2b())
model._select(4, model.dev(4))
g4 = model.picture()
model._select(3, model.dev(3))
g3b = model.picture()

pfs = frames_of("p2")
pcon = console("p2")
plog = emulog("p2")
ok("iniz w3, iniz w4 and both copies ran without an error", "rror" not in pcon and "DONE-arm6309" in pcon)
p480 = next((i for i, (meta, px) in enumerate(pfs) if meta["h"] == 480), None)
ok(f"Select /W4 put the card in VMODE 01: a 640 x 480 frame appeared (frame {p480})", p480 is not None)
# the last frames before the switch have the pointer off: Select takes it off first
h3 = [meta["n"] for meta, px in pfs[:p480 or len(pfs)] if meta["h"] == 400 and np.array_equal(px, g3)]
ok(f"before it, /W3 showed vgp2a exactly: text, attributes, shapes, XOR, a pattern, Get/PutBlk, a GP font, "
   f"a working area, overlays, the cursor and the pointer ({len(h3)} frames)", len(h3) > 0)
h4 = [meta["n"] for meta, px in pfs if meta["h"] == 480 and np.array_equal(px, g4)]
ok(f"/W4 showed vgp2b exactly, drawn in DRAM while /W3 was displayed and copied to the card on Select "
   f"({len(h4)} frames)", len(h4) > 0)
if pfs:
    meta, last = pfs[-1]
    nl = int((last != g3b).sum()) if last.shape == g3b.shape else -1
    ok(f"Select /W3 again: the last frame is /W3 exactly, from its store ({nl} pixels differ)", nl == 0)
ok("no register write under a span or a display list, with bitmap windows",
   "0 register writes under a list, 0 under a span" in plog)
ok("the CPU never ran through empty RAM (WILD), with bitmap windows", "WILD" not in plog)
pms = masks("p2")
worst = max((r[0] for r in pms if r[1].startswith("CoArm+")), default=0.0)
ok(f"CoArm's longest IRQ-masked stretch is {worst:.0f} us (<= 500 us)", 0 < worst <= 500)

# --------------------------------------------------------------------- P2: the mouse
mfs = frames_of("mouse")
mlog = emulog("mouse")
model = gm.Console()
model.feed(3, gm.stream_p2a())
want = [model.picture()]
for mv in gm.MOVES:
    model.mouse(*mv)
    want.append(model.picture())
at, seen = 0, []
for meta, px in mfs:
    if at < len(want) and px.shape == want[at].shape and np.array_equal(px, want[at]):
        seen.append(meta["n"])
        at += 1
ok(f"the pointer followed {len(gm.MOVES)} PS/2 mouse packets: every position's screen appeared exactly and in "
   f"order, the last clamped to x 639 and the last row (frames {seen})", at == len(want))
if mfs:
    ok("and the last frame is the last position's", np.array_equal(mfs[-1][1], want[-1]))
m = re.search(r"CALLTIME ArmIO\+\$[0-9A-F]+: (\d+) calls, longest ([\d.]+) us, mean ([\d.]+) us; "
              r"outside interrupts longest ([\d.]+) us", mlog)
calls, mv_max, mv_net = (int(m.group(1)), float(m.group(2)), float(m.group(4))) if m else (0, 0.0, 0.0)
ok(f"the longest pointer move is {mv_max / 1000:.1f} ms, {mv_net / 1000:.1f} ms of it outside interrupts: the "
   "arrow's 106 pixels of runs saved, restored and composed, a row a masked stretch - too long for an IRQ service, "
   "so it runs from the kernel's idle loop with IRQs enabled", calls > 0)
mms = masks("mouse")
worst_armio = max((r[0] for r in mms if r[1].startswith("ArmIO+")), default=0.0)
ok(f"ArmIO's longest IRQ-masked stretch while it moves the pointer is {worst_armio:.0f} us (<= 500 us)",
   0 < worst_armio <= 500)
irq = max((r[0] for r in mms if r[1].endswith("+$FEF7")), default=0.0)
ok(f"after boot, every IRQ returns within {irq:.0f} us: under the 16C550 FIFO's 1.4 ms at 115.2 kbaud "
   "(an IRQ the clock's poll serviced is no longer reported unclaimed)", 0 < irq <= 1400)

# --------------------------------------------------------------------- P3: the extensions
model = gm.Console()
model.feed(3, gm.stream_p3())
g3 = model.picture()
xfs = frames_of("p3")
xcon = console("p3")
ok("p3: the extensions' stream was copied to /W3 without an error", "rror" not in xcon and "DONE-arm6309" in xcon)
nx = sum(1 for meta, px in xfs if px.shape == g3.shape and np.array_equal(px, g3))
nl = int((xfs[-1][1] != g3).sum()) if xfs and xfs[-1][1].shape == g3.shape else -1
ok(f"⭐ p3: PatDef and PatBar, Poly and PolyPat by show.py's rule, PutMask, Image, Icon, Pal565, PalRange, and an "
   f"ANSI terminal (AnsiSw) in an overlay that scrolls - the model's picture exactly ({nx} frames; the last "
   f"differs by {nl} pixels)", nx > 0 and nl == 0)
xms = masks("p3")
worst = max((r[0] for r in xms if r[1].startswith("CoArm+")), default=0.0)
ok(f"p3: CoArm's longest IRQ-masked stretch is {worst:.0f} us (<= 500 us)", 0 < worst <= 500)
ok("p3: no register write under a span or a display list", "0 register writes under a list, 0 under a span" in emulog("p3"))

# --------------------------------------------------------------------- P3: display lists
for run, what, stream, model_of in (
        ("rast", "raster bars (a palette entry per band line)", gm.stream_rast,
         lambda idx, pal, ph: gm.rast_picture(idx, pal, gm.rast_def(), ph)),
        ("wave", "the warp (HSCROLL per band line)", gm.stream_wave, gm.wave_picture)):
    rfs = frames_of(run)
    rcon = console(run)
    rlog = emulog(run)
    model = gm.Console()
    model.feed(3, stream())
    idx, pal = model.picture(indices=True)
    still = model_of(idx, pal, None)
    total = gm.RAST["frames"] if run == "rast" else gm.WAVE["frames"]
    n_list = n_exact = n_still = 0
    phases, bad = set(), []
    for meta, px in rfs:
        if px.shape != idx.shape:
            continue
        ph0, ph1 = meta["ph"]
        if ph0 == 0 and ph1 == 0:
            n_still += int(np.array_equal(px, still))
            continue
        if ph0 != ph1 or not meta["lrun"]:
            continue
        n_list += 1
        want = model_of(idx, pal, ph0 - 1)
        if np.array_equal(px, want):
            n_exact += 1
            phases.add(ph0 - 1)
        elif not bad:
            bad.append((meta["n"], ph0 - 1, int((px != want).sum())))
    ok(f"{run}: the client ran to its end without an error", "rror" not in rcon and "DONE-arm6309" in rcon)
    ok(f"{run}: the screen without a list is the model's ({n_still} frames)", n_still > 0)
    ok(f"⭐ {run}: {what} - every frame a list ran is the model's picture at the phase the VBL service "
       f"started: {n_exact} of {n_list}" + (f"; first wrong: frame {bad[0][0]}, phase {bad[0][1]}, {bad[0][2]} pixels"
                                              if bad else ""), n_list > 0 and n_exact == n_list)
    step = gm.RAST["step"] if run == "rast" else gm.WAVE["step"]
    ok(f"{run}: {len(phases)} of the client's {total} lists reached the screen (90% must: a list rewritten "
       f"inside one frame is never started)", len(phases) >= total * 9 // 10)
    ok(f"{run}: no register write under a span or a display list", "0 register writes under a list, 0 under a span" in rlog)
    rms = masks(run)
    worst = max((r[0] for r in rms if r[1].startswith("CoArm+")), default=0.0)
    ok(f"{run}: CoArm's longest IRQ-masked stretch is {worst:.0f} us (<= 500 us): it waits a running list out "
       "with /IRQ open", 0 < worst <= 500)
    irq = max((r[0] for r in rms if r[1].endswith("+$FEF7")), default=0.0)
    ok(f"{run}: ⭐ with a list on, the longest IRQ is {irq:.0f} us - the VBL service writes GO in the blank and the "
       "card starts the list as the blank ends (graphics.md 10.3.1's armed GO), under the 16C550 FIFO's 1.4 ms",
       0 < irq <= 1400)

# --------------------------------------------------------------------- P3: the overworld
import bisect
import mkgame

gcon = console("game")
glog = emulog("game")
ok("game: overworld ran to its end without an error", "rror" not in gcon and "DONE-arm6309" in gcon)
gm_model = np.load(os.path.join(out, "gamedata", "model.npz"))
pal565 = fr.palette565()
inv = np.full(65536, -1, dtype=np.int32)
inv[pal565] = np.arange(256)
nokey = {**{f: gm_model[f] for f in gm_model.files}, "sprites": np.full_like(gm_model["sprites"], int(gm_model["key"]))}
started, n_game, n_exact, n_stale, first_bad, steps, prev = False, 0, 0, 0, None, {}, None
n_undoubled = 0
for meta, px in frames_of("game"):
    if px.shape != (400, 640) or meta["vmode"] != 0:
        continue
    k, hk = meta["camk"], meta["herok"]
    if not started:                      # the frame words mean something from the first batch on
        if hk == 0xFFFF and k == 0:
            started = True
        else:
            continue
    n_game += 1
    n_undoubled += int(not np.array_equal(px[0::2], px[1::2]))
    if k >= len(gm_model["frames"]) or (hk != 0xFFFF and hk >= len(gm_model["frames"])):
        if first_bad is None:
            first_bad = (meta["n"], k, hk, -1)
        continue
    idx = inv[px[0::2]]
    want = mkgame.render(nokey, k) if hk == 0xFFFF else mkgame.render(gm_model, k, hk)
    if np.array_equal(idx, want):
        n_exact += 1
    elif int(gm_model["frames"][k][0]) % 8 == 4 and np.array_equal(
            idx, mkgame.render_cells(gm_model, k, None if hk == 0xFFFF else hk, stale_half=True)):
        n_stale += 1
    elif first_bad is None:
        first_bad = (meta["n"], k, hk, int((idx != want).sum()))
    if prev is not None:
        steps[k - prev] = steps.get(k - prev, 0) + 1
    prev = k
ok(f"⭐ game: every frame is mkgame.render() for the camera and hero records its batch committed: {n_exact} of "
   f"{n_game}" + (f"; first wrong: frame {first_bad[0]}, camera {first_bad[1]}, hero {first_bad[2]}, {first_bad[3]} pixels"
                  if first_bad else ""), n_game > 1000 and n_exact == n_game)
ok(f"game: VMODE 00 doubles every row in all {n_game} frames ({n_undoubled} do not), and none shows the cell-mode "
   f"handover defect ({n_stale})", n_undoubled == 0 and n_stale == 0)
total = sum(steps.values())
print("      camera record step per displayed frame: " + ", ".join(f"{s}: {c}" for s, c in sorted(steps.items())))
ok(f"game: the camera advances one record per frame in {steps.get(1, 0)} of {total} frame pairs (90% must, as "
   "checkdemo.py asks of the demo)", total > 0 and steps.get(1, 0) >= 0.9 * total)
vs, acts, flips, start = [], [], [], None
for line in open(os.path.join(out, "game", "marks.txt")):
    t, tag = line.split()[:2]
    t = int(t) / 1e9
    if tag == "V":
        vs.append(t)
    elif tag == "A":
        acts.append(t)
    elif tag == "M1":
        start = t
    elif tag == "M2" and start is not None:
        flips.append((start, t))
        start = None
over, delays, durs = 0, [], []
for a, b in flips:
    i = bisect.bisect_right(vs, a) - 1
    if i < 0:
        continue
    j = bisect.bisect_right(acts, vs[i])
    nxt = acts[j] if j < len(acts) else float("inf")
    delays.append(a - vs[i])
    durs.append(b - a)
    over += b > nxt
if flips:
    print(f"      {len(flips)} hero flips from SS.Batch: start {min(delays):.2f}-{max(delays):.2f} ms after VBLANK rose, "
          f"take {min(durs):.2f}-{max(durs):.2f} ms")
ok(f"game: the hero's flips finish in the blank ({over} of {len(flips)} ran into the picture; 2% may)",
   len(flips) > 0 and over <= len(flips) // 50)
ok("game: no register write under a span or a display list", "0 register writes under a list, 0 under a span" in glog)
ok("game: the CPU never ran through empty RAM (WILD)", "WILD" not in glog)
gms = masks("game")
worst = max((r[0] for r in gms if r[1].startswith("libvid+")), default=0.0)
ok(f"game: libvid's longest IRQ-masked stretch is {worst:.0f} us (<= 500 us)", 0 < worst <= 500)
irq = max((r[0] for r in gms if r[1].endswith("+$FEF7")), default=0.0)
ok(f"game: the longest IRQ, the VBL service's SS.Batch commit included, is {irq:.0f} us (<= 1.4 ms, the 16C550's FIFO)",
   0 < irq <= 1400)

print(f"{n} claims, {fails} failed")
sys.exit(1 if fails else 0)
