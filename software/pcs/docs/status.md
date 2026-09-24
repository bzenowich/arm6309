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
| `pcsui.inc` — the editor's screen (`pcs 22`) | 250 | ⭐ **the kit panel (tool icons redrawn at card resolution, white on black) and the 12 × 10 colour picker, every card pixel**, against `pcskit.py` (`k0`). ⚠ No interaction yet |
| `pcsfile.inc` — a table is a file on the card | 192 | ⭐ all four `DEMO*.PB` load off `/SD0/DATA` with **byte-identical span databases** |
| `pcstext.inc` — the original's proportional font | 216 | screenshotted: the glyphs, the spacing, right-aligned numbers, boxes and frames |
| `pcsin.inc` — mouse, keyboard, cursor | 230 | the cursor is the **card's hardware sprite**; a scripted mouse drives a real game |
| `pcssnd.inc` — the seven effects on the audio card | 200 | ⚠ **unheard**. The note sequences are the original's tables; nothing gates a sound |
| `pcsgame.inc` — players, balls, tally, panel | 380 | ⭐ **it plays**: a scripted mouse launches the ball, gravity pulls it down, it bounces, the panel draws |

**The two decisions the whole port rests on**, both holding:

- ⭐⭐ **The world stayed in the Atari's own units and only the renderer is doubled.**
  Every number in the database and the simulator is exact integer arithmetic, which is
  what lets a Python transliteration of the 6502 be the gate rather than a screenshot.
- ⭐⭐ **The span database is a display list**, because this card cannot XOR. It is the
  picture, the hit test and the collision model at once.

---

## 2. What is left

⛔ **The editor's UI is the gap.** `pcsedit.inc`'s 950 lines of database operations —
add, delete, drag, drag-point, cut, paste, paint, with rollback — exist and **nothing
calls them**, because there is no tool bar, no parts bin and no drag. That is the one
piece where a large amount of working code is waiting on a small amount of missing code.

| | of the 6502 | note |
|---|---|---|
| The editor shell: tool bar, **parts bin**, drag-and-drop | part of `EDIT.s` | the data is already generated — `PCBox` (43 hit rects), `PCTLen`, `PCTmpl`, the screen rects. What is missing is the loop and the dispatch |
| The wiring kit's UI | `WIRE.s`, 1,143 | ⭐ the **evaluator** is already built and gated (`PBWire`, `TURNOFF`); only the screen and the three tools are missing |
| The World panel — four sliders | part of `EDIT.s` | `wset` already loads and drives the physics; it is not editable |
| The magnifier — fat-bits paint | part of `EDIT.s` | and the free-hand layer, which the original RLE-compresses on save |
| Save, and a catalogue | part of `DISK.s` | ⭐ `PFSave` is written; nothing calls it and there is no file picker |
| `desk` integration | — | no icon, no `IcTab` entry, no Applications item |
| Four-player attract loop | `RUN2.s` | ⚠ **deliberately not ported**: it read the Atari's console START/OPTION/SELECT keys, which this machine does not have |

### Known open items on work already written

- ⚠ **Nothing re-keys the parts after an edit.** `vlo`/`rcn` point into the object area
  and `PERbld` rewrites it, so the editor UI must re-run `PBPlay`'s keying half before it
  draws parts or plays.
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
