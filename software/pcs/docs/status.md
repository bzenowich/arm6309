# `pcs` — Pinball Construction Set: where the port stands

**2026-09-24.** Bill Budge's *Pinball Construction Set* (Atari 800, 1983), ported from
his own MIT-licensed 6502 in [`software/pcs/reference/pcs-source/`](../reference/pcs-source/) to a 6809 running
NitrOS-9 Level 2 against a video3 card at 640 × 480 chunky 8 bpp.
[`software/pcs/docs/pcs.md`](pcs.md) is the spec; this is a progress note and
not a design document.

**Scale.** The original is **11,538 lines of 6502** across sixteen files. The port is
**~7,000 lines of 6809** plus ~2,500 of Python (the generator, the models and the
checkers).

---

## 1. What is built, and how it is known

| | lines | how it is verified |
|---|---|---|
| `pcspak.inc` — the scan converter and span database | 1,252 | ⭐⭐ **byte-identical to `PPAK.s`** on all 26 shipped tables |
| `pcsobj.inc` + `pcsrun.inc` — the simulator | 2,299 | ⭐⭐ **bit-exact over 600 frames** against a Python transliteration of `RUN.s`: the ball's `(x, y, BDX, BDY)` every frame, 95 hits on 11 objects, every part's state byte, and the score |
| `pcsdraw.inc` — the painter, the 1bpp art blit | 589 | every pixel of the table, against the model |
| `pcsedit.inc` — the editor's **database** operations | 950 | ⭐⭐ **agrees with `pcsedit.py`** over a twelve-edit session: step results, object area and span database (`m6`, in the default bench since 2026-09-24) |
| `pcsui.inc` — the editor's screen (`pcs 22`) and its event loop (`pcs 23`) | 1,743 | ⭐ **the kit panel and the 12 × 10 colour picker, every card pixel**, against `pcskit.py` (`k0`). ⭐⭐ **And the editor with a mouse** (`e0`): 22 scripted gestures — the hand, the bin, the pointer, the hammer, the scissors and the brush — each one's record against what the checker works out from the script alone, then the object area, the span database and the whole table picture |
| `pcsfile.inc` — a table is a file on the card | 192 | ⭐ all four `DEMO*.PB` load off `/SD0/DATA` with **byte-identical span databases** |
| `pcstext.inc` — the original's proportional font | 216 | screenshotted: the glyphs, the spacing, right-aligned numbers, boxes and frames |
| `pcsin.inc` — mouse, keyboard, cursor | 230 | the cursor is the **card's hardware sprite**; a scripted mouse drives a real game |
| `pcssnd.inc` — the seven effects on the audio card | 200 | ⚠ **unheard**. The note sequences are the original's tables; nothing gates a sound |
| `pcsgame.inc` — players, balls, tally, panel | 380 | ⭐ **it plays**: a scripted mouse launches the ball, gravity pulls it down, it bounces, the panel draws |

⭐ **Since 2026-09-24 `pcs` is a 24.3 KB core and four libraries** (`pcsed`, `pcsui`,
`pcsfl`, `pcsmg`) paged through one 8 KB window (`pcs.md` §5, `pcscore.inc`), so the editor can
grow without the one-module 32 KB ceiling. The whole gate runs on the paged build.

**The two decisions the whole port rests on**, both holding:

- ⭐⭐ **The world stayed in the Atari's own units and only the renderer is doubled.**
  Every number in the database and the simulator is exact integer arithmetic, which is
  what lets a Python transliteration of the 6502 be the gate rather than a screenshot.
- ⭐⭐ **The span database is a display list**, because this card cannot XOR. It is the
  picture, the hit test and the collision model at once.

---

## 2. What is left

⭐ **The editor has a mouse** (2026-09-24): `pcs 23` runs `EDIT.s`'s `MAIN` as
`EdLoop`, and all seven of `pcsedit.inc`'s operations are reached through the tool bar,
the parts bin and drag-and-drop (`pcs.md` §8). What is left is the rest of the editor
around it:

| | of the 6502 | note |
|---|---|---|
| The tool bar's WIRE | part of `EDIT.s` | recorded when clicked, and does nothing yet. ⭐ **The three paint pots are gone** from the column (2026-09-24): the picker chooses the colour. ⭐ **PLAY is built**: the table plays from the editor with the score strip where the kit was, and comes back as it was left (`e1`). ⭐ **MAGN is built** (`e2`), **DISK** (`d0`) and **WORLD** (`w0`) |
| The wiring kit's UI | `WIRE.s`, 1,143 | ⭐ the **evaluator** is already built and gated (`PBWire`, `TURNOFF`); only the screen and the three tools are missing |
| The World panel — four sliders | part of `EDIT.s` | ⭐ **built** (`w0`): gravity, speed, kick and elasticity dragged live, DOSLIDE's level rule, every knob read off the card |
| Save, and a catalogue | part of `DISK.s` | ⭐ **built** (`d0`): the DISK panel, a catalogue of `/SD0/DATA`'s tables, LOAD, SAVE and a refusal, and every saved file read back off the card byte for byte |
| `desk` integration | — | ⭐ **built** (2026-09-24): a Pinball icon and Applications item fork `pcs`, which with no arguments is the editor on `demo2.pbt` until `q` |
| Four-player attract loop | `RUN2.s` | ⚠ **deliberately not ported**: it read the Atari's console START/OPTION/SELECT keys, which this machine does not have |

### Known open items on work already written

- ⭐ **The drag is live** (the copy engine, keyed on index 0) and **an edit repaints
  only its rows**, composed in the margin with no black flash (`pcs.md` §8).
- ⭐ **A gesture made during a repaint is kept** (§8 below): `c0` and `c2` run
  `e0`'s and `e2`'s scripts at 0.3 of their spacing, and `cX` is required to fail
  with the queue off.
- ⭐ **The core must fit three 8 KB slots, and the build says so.** Past 24,573 bytes
  there is no room to map a library; `pcs.asm` now refuses to assemble. The picker and
  mode 3's text screen are in `pcsmg`.
- ⭐ **A game repaints four bands of rows, composed in the margin**, with a column-wise
  `PCBlit`: 35-40 frames a second on Astro Blast, and no wiped band on the screen.
- ⚠ **`TIMETBL` re-derivation for 59.94 Hz is still unmeasured.** Gravity, flipper sweep
  and the drain delay are all counted in frames and the original busy-waited.
- ⚠ **Sound is unverified by anything.** A bench cannot hear. The note *sequences* are
  the original's; the per-note *duration* is a proportional approximation and says so.

---

## 3. Three defects found this session, all of which predate it

### ⛔ `arm6309.mak` listed 4 of `pcs`'s 11 includes

`make` cannot see a `use`, so edits to `pcsobj.inc`, `pcsrun.inc` or `pcsedit.inc`
**rebuilt nothing** and the card carried the previous program. The build prints `ok`;
the only symptom is that what you just wrote does not happen. It cost about an hour, and
every hypothesis in that hour was about the 6809. Found by looking at the module's
timestamp. All eleven are listed now.

### ⛔ The ball was drawn from its bitmap header

So it sat where the editor left it for the whole game while the simulation carried it
round the table. `MOVEBALL` writes `L[17]/L[18]` and never touches `L[2]/L[3]`; the
original has a `DRAWBALL` of its own that reads exactly those two bytes and its own
`IBALL` shape rather than going through `XOFFDRAW`. Every other part moves by having its
header rewritten; the ball moves sixty times a second and does not. **The model had the
same fault** and was corrected with it — the 6502 decides.

### ⛔ A mutation leg that "passed" because the checker crashed

`if python3 checkpcs.py … then FAIL else ok` cannot tell a caught mutation from an
`AttributeError`: both exit non-zero. For one run all three mutation legs reported `ok`
while checking nothing at all. This is CLAUDE.md's own trap — *"a negated claim that can
only be satisfied by the thing under test EXISTING must prove the tool ran"*. The legs
now require a `FAIL` line and refuse a traceback.

---

## 4. How to run it

```sh
sh software/pcs/bench/run-pcs.sh          # ⭐⭐ the gate: the database, the ball, 3 mutations
sh software/pcs/bench/run-pcssheet.sh     # ⭐ all 26 shipped tables on one contact sheet
pcs 20 <frames> demo1.pbt >/w5      # ⭐ PLAY IT, with a mouse
pcs 21 <frames> demo1.pbt >/w5      # ... and with the ball traced to the console
```

⭐ **The mouse is the joystick, and the mapping is the original's.** `RUN2.s` reads
`PDL0` from `STKY` — the integrated cursor Y — and both triggers as `BUTN0`/`BUTN1`:

| | |
|---|---|
| left button | left flipper, **and** the plunger release (`RUN.s:217` reads `BUTN0` for both, exactly as trigger 0 did) |
| right button | right flipper |
| pointer Y | the plunger's pull — further down is harder |

⚠ **The keyboard cannot hold a flipper.** `SS.Ready` + `I$Read` gives one byte and no
key-up, so a keyed flipper would flap once and drop. That is why the buttons carry the
flippers.

⛔ **The tables are not in this repository.** They are shipped game data, not the MIT
sources, and `software/pcs/reference/pcs-source/README.md`'s rule is that the right to redistribute is the
criterion. `mkpcs.py` reads them out of disk images supplied locally and writes
`software/pcs/bench/pcstbl/*.pbt`, which `mkrom.sh` copies onto the card; a clone without them
has no tables and every bench that names one says so rather than passing vacuously.

---

## 5. The trail, fixed 2026-09-24, and it was two faults and not one

`run-pcs.sh` is **green on every leg** again (`m0`, `m4`, `f0`, `fX`, and all three
mutations refused).

### ⛔ The ball reported no damage, because its top row is `Y1` and not `L[2]`

This was the diagnosis §3 left: `PBStep` keyed a part's repaint on `LB.State` and
`LB.Vert`, and `MOVEBALL` never touches the ball's `LB.Vert`. `PBTop` now answers "the
row this part's picture starts on" (`Y1` for the ball, `L[2]` for everything else, the
same discriminator `PBArtI` uses), and a ball that moved only sideways counts as well.

⚠ **That fix alone changed 1,180 bad bytes to 1,160.** The diagnosis was right and
incomplete.

### ⛔ Seven frames in eight threw their damage away

The rate tests after the object walk (`PBSound` every 8 frames, `PBWire` every 4 of
those) jumped to `stB@`, and **`stB@` is the routine's exit, past the repaint**. So damage
was recorded on every frame and repainted only on frames that were a multiple of 8.
Everything that moved in the seven frames between left its picture behind, which reads
exactly like a part that reported no damage. The tests now go to `stR@`, the repaint.

⭐ **How it was found**, since hypotheses cost an hour first: forcing full-table damage
every frame made `m4` green, which put the fault in the bookkeeping and not the drawing.
Then `WATCH=` on `pbdmin`/`pbdmax` and on PCWipe's own row counter (offsets from a
`lwasm -l` listing, `U` = 0 from one `TRACE` line) showed damage `$28..$3F` recorded and
reset with **no PCWipe in between**. The frame recording (`frames.bin`, read with
`software/tools/frames.py`) showed the smear growing between wipes and never shrinking
over the old ball.

### ⚠ And one found on the way, fixed and ungated

`PBWire`'s TURNOFF runs each input's **INIT** proc, which rewrites the state byte just as
a RUN proc does and recorded no damage, so a light the wiring turned off would have
stayed lit on screen. It now records damage the same way. ⚠ **No leg checks it**:
`m4` still passes with it, but nothing asserts a wired light going dark.

### Still unfinished

- `pcsgame.inc` carries progress markers `$FA`–`$FD` and a `pcs 21` console trace that
  were added for debugging. They are useful and cheap, but should be reviewed rather
  than left by accident.
- ⚠ `PCS_BUDGET` now defaults to **0**: the module carries no shipped tables at all, only
  the bench's test table and the built-in demo. That is the intended end state, but it
  means `pcs 7`..`pcs 32` no longer select a table. A table is named, not numbered.

---

## 6. The editor's mouse, 2026-09-24, and four older defects it found

`e0` agreed with the model on all 23 records the first time it ran. What it took to get
there was four faults in code that was already written, each listed in `history.md`
(§8's entry):
- `pcs` forced 120 frames whenever no table was named, because it tested `PFArg`'s
  flags instead of `frames`. It also changes `m0`'s hold from 120 frames to 30.
- `EditO` sat inside `PCDump`'s rows.
- `PEPaint` left the old colour on screen when the brush cleared it to 0.
- In the editor, the ball was drawn where the last game left it.

## 7. The magnifier and the free-hand layer, 2026-09-24

⭐ **Built and gated, first run green.** `pcsmg`, library 4 (`pcsmag.inc`, 1,606
bytes), is EDIT.s's MAGNIFY: a 24 × 40 viewer of fat bits read back off the card,
a box on the table, lines drawn and toggled off with Bresenham, QUIT (`pcs.md` §8).
What it draws on is a **160 × 240 layer in eight `F$AllRAM` blocks**, paged through
the library window by the core (`pcs.md` §5) and composed under the parts' art on
every repaint; a table file carries it in a trailer after the payload.

| leg | what it proved |
|---|---|
| `e2` | 15 gestures, every record against `pcsmag.py`; the 109-pixel layer `MgDump` streamed; all 153,600 table bytes with the layer and the box's frame; **all 62,146 viewer pixels** |
| `f1` | `demo2l.pbt`'s 1,206-pixel trailer loaded — the database identical, 0 pixels different, every layer pixel on the card |
| `e0` | unchanged, and its (empty) layer now checked too |

⭐ **The viewer's first redraw took about 3 s** — 960 cell fills, and the contact
sheet caught it half drawn. Painting runs and putting the grid back with one keyed
copy a row (`pcs.md` §8) made it quick enough that no tile catches it, and `e2`'s
62,146-pixel comparison held unchanged across the rewrite.

Sizes: core 24,154 bytes of 24,576; `pcsui` 7,962 of 8,192. ⚠ The core is
**422 bytes from a fourth slot** — which is a slot the process has not got, so the
next routine that must be resident moves something else into a library.

---

## DISK: save, load and a catalogue (2026-09-24)

The DISK tool opens a panel in the kit's place (`pcsdisk.inc`, in the `pcsfl`
library): a name field, the `*.pbt` tables on `/SD0/DATA` sorted fourteen to a
page, and LOAD, SAVE, QUIT and MORE (`pcs.md` §8).

| leg | what it proved |
|---|---|
| `d0` | 44 records (keys, a pick, two SAVEs, a LOAD taken, one refused with `PF.ENoF`, one after it that brought back the saved table) against `pcsdisk.py`; the final table's 37 objects, 790 span records, 1,220 layer pixels and `logic`/`wset`; and **every `.pbt` on the card afterwards**, byte for byte: `mytbl.pbt` as the model wrote it, the five others untouched |
| `e0`, `e1`, `e2` | unchanged, and `logic`/`wset` off `EditW` now checked in each: zeros and the built-in `wset` |

⛔ **`PFSave` had two defects, and neither had ever run**: a payload length summed
×256, and a carry left by a compare, taken as a write error on the first layer
pixel (`history.md`). The first `d0` run found both.

Sizes: core 24,195; `pcsfl` 3,925; `pcsui` 7,988 (as of that commit).

## Responsiveness: the mouse queue and a kit that is a copy (2026-09-24)

Both measured from PC traces weighted by dots (`software/emu/test/pchist.py`, which now
takes `Module=listing` pairs and names local labels `Global/local@`):

| | before | now | where the rest goes |
|---|---|---|---|
| magnifier QUIT, release to idle | 0.7 s | **0.32 s** | the kit panel ~0.05 s; the table under the box repainted with its layer |
| PLAY, `q` to idle | 1.1 s | **0.90 s** | `PERoll`'s copy back, then the whole table in `RpRows`'s two bands (0.7 s) |

- ⭐ **The mouse queue** (`pcsin.inc`): while `EdLoop` runs, the left button's changes
  are queued with the pointer, eight deep, sampled at most once a frame in `PCWait` and
  once a scanline in `PKSweep`, and `UIPoll` takes from the queue first. ⛔ The first
  version sampled only in `PCWait`, and `c0` lost a 0.3 s click in the 0.4 s an edit's
  scan conversion spends with no VRAM access.
- ⭐ **The kit is drawn once** into the margin below row 320 (`KitBin`), and each redraw
  after that is two copy-engine rectangles. The picker streams a cell row and doubles it
  by copies, and `PTBox` copy-doubles its first rows.
- ⭐ **Legs**: `c0` and `c2` (`e0`'s and `e2`'s scripts at 0.3 of their spacing: 17 and 5
  samples off the queue) and ⛔ `cX` (`c0` on `pcs 25`, the queue off), which is required
  to fail on the records and does.

Sizes: core 24,344 (of 24,573); `pcsed` 3,576; `pcsui` 7,601; `pcsfl` 3,947; `pcsmg` 2,544.

## WORLD: the four sliders (2026-09-24)

The WORLD tool opens `EDIT.s`'s four sliders in the kit's place (`pcsworld.inc`, in
the `pcsmg` library): gravity, speed, kick and elasticity. Each has eight levels,
and the knob follows the pointer while the button is down (`pcs.md` §8).

| leg | what it proved |
|---|---|
| `w0` | 9 records against `pcsworld.py`: each slider moved (gravity to 7 past the bottom, speed to 0 past the top, kick down and back up, elasticity released wide of its track), a miss, QUIT, and a second gravity slide from beside the frame; `wset` off `EditW` (`[4, 0, 2, 5]`); and **all 32 knob boxes** read off the card, the knob at each track's level and nowhere else. First run green |

⛔ **The knob check was run against a model offset by one level**, to prove it can
fail, and it failed on 1,920 pixels.

Sizes: core 24,351 (of 24,573); `pcsed` 3,580; `pcsui` 7,616; `pcsfl` 3,951; `pcsmg` 3,260.

## Play speed, and the Astro Blast demo (2026-09-24)

`software/pcs/video/run-astro.sh` records the desktop's Pinball icon, Astro Blast
LOADed through DISK, both flippers painted light blue, a pop bumper out of the bin
painted yellow, KICK raised from 3 to 4 (gravity left at the table's 4), and
about twenty seconds of play. Making it found three
things:

- ⭐ **The repaint flashed** in 93 play frames: the bands were wiped on the screen. They
  are composed in the margin and copied now, four of them, with the reach taken from the
  part's own template - 1 or 2 flash frames left.
- ⭐ **Play ran at ~9 frames a second** on this table (flipper frames ~450 ms). `PCBlit`
  culls, runs down columns, and `PCIsB` reads `objkind`: 35-40 a second.
- ⛔ **Quitting from PLAY broke the desktop** (`WADV` left at 01). `Bye` restores it;
  `run-v3desk.sh`'s pin leg now plays, compares the whole desktop after with before
  (99.8 %), and fails on a mutant `Bye`.
- ⚠ The launch is a held button: the plunger fires only on the ball's landing with the
  button down, so the script holds it 14 s from the start of play - the model
  lands the ball at frame 346 at gravity 4 (249 at gravity 5).

`PCDump` moved into the `pcsfl` library to keep the core under its limit.
Sizes: core 24,540 (of 24,573); `pcsed` 3,576; `pcsui` 7,608; `pcsfl` 4,139; `pcsmg` 3,264.
