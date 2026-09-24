# `pcs` — Pinball Construction Set on the arm6309

[`billbudge/PCS_Atari800`](https://github.com/billbudge/PCS_Atari800) is Bill Budge's 1983
*Pinball Construction Set* for the Atari 800, MIT-licensed: **11,538 lines of 6502** across
sixteen files, vendored here at [`software/pcs/reference/pcs-source/`](../reference/pcs-source/). It is four
programs sharing a screen — a direct-manipulation **editor**, a **magnifier**, a **wiring
kit**, and a **simulator** that plays the table you built — in **320 × 192 at 1 bpp** (ANTIC
mode F) and a 48 KB address space it overlaid three ways (`EDIT`, `WIRE` and `DISK` all
`ORG $A000`, swapped by `SWAP.s`).

⚠ It was cross-developed **on an Apple II** and downloaded over a parallel cable
(`MAKE1`–`MAKE3` are Applesoft `BLOAD` scripts, `DOWNLOAD.s` is the link), which is why
`ORG` is the Atari address and `OBJ` the Apple staging address, why the comments say "READ
THE PADDLES" over code that reads a joystick, and why the three paint colours are the Apple
II's hi-res bit patterns. ⭐ The Apple II sources
([`billbudge/PCS_AppleII`](https://github.com/billbudge/PCS_AppleII)) are worth reading
beside them: the physics is **byte-for-byte identical** between the two, which is how
several readings here were confirmed.

Here it is a NitrOS-9 Level 2 program on **640 × 480 chunky 8 bpp** (`VMODE` 11) with a
256-entry LUT, a copy engine, a span writer, one hardware sprite and a PS/2 mouse, forked
from `desk` like `pinball`, `monster` and `tilescroll`.

---

## 1. ⭐⭐ The WORLD is the original's, and only the RENDERER is doubled

`RUN.s` tunes the ball with four tables (`INITWORLD`, `RUN.s:2170`), eight levels each,
each patched into the code as a self-modifying immediate:

```
GRAVTBL HEX FF7F3F1F0F070301     gravity — a MASK: apply -1 to BDY when (tick & mask)==0
TIMETBL HEX 302018100C080401     speed   — the sub-steps a frame
KICKTBL HEX 04080C1018202838     kick
ELASTLO HEX 80400000C0804000     elasticity — eight ENTRY POINTS into one response
ELASTHI HEX 8383838382828282       table, which is how one table gives eight curves
```

Gravity is not an acceleration constant at all — it is *how often* you subtract one from
`BDY`, terminal velocity clamped at `$D1`. Position is pixels plus an 8-bit accumulator.
Every coordinate in the program is a **single byte** (table x 0–159, y 0–239 here).

**So the simulation, the database and the file format stay in the original's units, and the
renderer multiplies by two on the way to the screen.** `PC.Scale` applies nowhere else.

| | |
|---|---|
| ⭐⭐ **The port is provably the original** | every number is exact integer arithmetic, so a Python transliteration can be the gate and the 6809 is required to produce the **identical ball trajectory, frame for frame**. Not "it feels right" — it is the same simulation |
| ⭐ **Nothing has to be widened** | otherwise all 43 part templates, the span database and the file format need 16-bit coordinates |
| ⭐ **Nothing is chunky** | vertices sit on even pixels, but the scan converter runs at 2× with doubled slopes |

## 2. ⭐⭐ The span database is a DISPLAY LIST, because this card cannot XOR

⛔ **Every composite in PCS is an XOR** — the cursor, menu highlights, the drag preview,
polygon fill, wires, vertex dots, even the brush (which repaints by filling with
`old ^ new`, `EDIT.s:1151`). Drawing a thing twice erases it, and that is the entire undo
and animation mechanism.

⛔ **video3 has no read-modify-write.** The span writer writes `WFG`/`WBG`; the copy engine
copies. There is no raster op.

⭐ **It does not need one.** `PPAK.s`'s scan converter already maintains exactly the
structure a repaint needs. Its output is **not just a picture** — it is a per-scanline,
z-ordered list of spans with the object index and the edge slopes:

```
record (4 bytes)  x_left | object index | x_right | (slope_right << 4) | slope_left
```

in draw order, later on top. That is a retained display list, a hit-test structure and the
collision model at once. **Repainting scanline *y* is walking its records in order and
emitting one span-solid write per span**, at the object's `FILLCOLOR`. Damage is a row
range; nothing is ever XORed and nothing is saved behind.

| XOR idiom in the original | here |
|---|---|
| cursor (`XDRAWCRSR`, save-behind) | ⭐ **the hardware sprite** — two register writes |
| drag preview (`DRAWOBJ` twice a frame) | repaint the object's damaged rows from the DB |
| menu highlight (`SELECT` XOR-inverts a rect) | repaint the rect in a highlight colour |
| brush repaint (`old ^ new` fill) | ⛔ **store the new colour and redraw.** `PAINTOBJ` stores `new XOR old` and XOR-blits; the Apple II diff proved that cannot survive 256 colours |
| animation (`ADVANCE`/`RETREAT` step a bitmap pointer and XOR-draw) | ⭐ a **frame INDEX**: `L[8] & $7F` is exactly what the pointer encoded |
| `$55` over `$AA` → `$FF` | ⛔ gone, and not missed — a 1bpp dither artefact |

⚠ **This is the one place the port is an adaptation rather than a transliteration**, and it
is forced by the hardware. The semantics it preserves are: draw order is object order,
index 0 is the background `BPOLYGON`, and `FILLCOLOR = 0` means unfilled-but-solid.

⛔ **The database's LAYOUT is not the original's either.** `PPAK.s` keeps the records in a
gap buffer between `membtm` and `$7A40`, with `MAKEHOLE` sliding the hole about. The port
uses a per-scanline singly-linked list with a free list: the same content, O(1) appends,
one walk to remove an object, and `MAKEHOLE`, `GETSCAN`, `MOVEUP` and `MOVEDOWN` deleted
outright. The bench compares the database's **content**, so the layout is free.

## 3. The layout — ⭐ a 160 × 240 world, which at 2× is exactly the screen

⚠ **The table is 160 × 192 in the original, not 320 × 192.** `TABLEB` is x 0–159 and `KITB`
is x 160–319 (`EDIT.s:1376`), confirmed by `PPAK.s:774`'s `LDX #159` and `RUN.s:1864`'s
`X2 >= 153` wall clamp.

**The table gets the extra rows — a 160 × 240 world:**

```
 x 0..319      THE TABLE          160 x 240 world at 2x  = 320 x 480, the full screen height
 x 320..639    the kit panel      160 x 192 at 2x        = 320 x 384
 y 384..479    ⭐ ...which leaves 96 rows UNDER the kit panel for a permanent
               score / bonus / player strip
```

⭐ The taller table costs nothing and fixes something: the original had **no status area in
the editor** and had to blank the parts bin during play to print `BONUS X`, `BONUS` and
`PLAYER 1` into it (`RUN.s:1958`).

⚠ `y` is still one byte, so no coordinate widens. What grows is `PBDX[192] → [240]`, the
scanline tables and the drain test's `LASTY`. ⚠ A table authored for a 192-row world loads
into the top of a 240-row one — worth a version byte in the file.

⚠ **`PC.TW-7` is 153, and the original is not self-consistent about it.** `RUN.s:1864`'s
wall clamp and `CHECKVERT`'s right-hand gap both say 153 in a 160-wide world, while
`PPAK.s:774`'s right edge says 159. The Apple II version is self-consistent at 154/153, so
this is a port slip in the *original*; it is reproduced, written as one constant.

## 4. What the machine gives us, and what it takes away

| | |
|---|---|
| ⭐⭐ **The original's 1bpp art renders VERBATIM, in colour** | `WM.Mask` takes the CPU's written byte *as a bitmap* and expands it to 8 pixels choosing `WFG`/`WBG`; `WM.Sprite` writes **nothing** for a 0 bit. So `DRAWBITS`, `XOFFDRAW` and `MASKS` collapse into one span write — **8 pixels a store, with transparency, in any colour** |
| ⭐⭐ **A third of the 6502 does not port at all** | `HDIV8`/`HMOD8`, `LEFTMASK`/`RIGHTMASK`, `XOFFDRAW`'s shifter and the 6,144-byte `GPAK.OBJ` table of x÷8, x mod 8 and row addresses. **Chunky 8 bpp has no shift**: `WPTR` is a byte address *is* a pixel address, and a row is `(y << 10) + x`. The port carries ONE `px` where the Atari had `HDIV8` and `HMOD8` |
| ⭐ **The screen is not in our address space** | the Atari spent 7.5 KB of 48 on the framebuffer and had to overlay `EDIT`/`WIRE`/`DISK`. **We have the whole 64 KB, and no overlays** |
| ⭐ **The margin is 196 KB of free VRAM** | columns 640–1023 × 512 rows. The part-art bank and the magnifier's backing store live there |
| ⛔ **No XOR** | §2 |
| ⚠ **A click can be missed** | a polled loop that repaints samples the button once a pass, so the mouse is sampled **inside** the repaint loop |
| ⚠ **The margin is shared** | the ROM toolbox's glyph strike sits at column 640, rows 320–472. Our stores stay above row 320 |

## 5. The data

**The record** (`GETINFO`, `PPAK.s:209`) — kept exactly, with `FILLCOLOR` reinterpreted:

| Off | Size | Field |
|---|---|---|
| 0 | 1 | `OBJID` — `1` POLYGON, `2` BPOLYGON (the complement/backdrop, always object 0), `3` LIBOBJ |
| 1 | 1 | `FILLCOLOR` — ⭐ a palette index; `0` = unfilled but **solid** |
| 2 | 1 | `VRTXCOUNT` — 3…63 |
| 3 | n | X coords, 1 byte each |
| 3+n | n | Y coords |
| 3+2n | 16+ | the library tail, `L` |

**The library tail `L`**, and ⚠ **the offsets are the original's** because every part proc
indexes them with a literal:

| | |
|---|---|
| `L[0..1]` | was the bitmap pointer; **unused here** (§2) |
| `L[2]` | the art's top row — ⚠ a flipper MOVES it as it sweeps |
| `L[3]` | the art's left column. ⭐ One number where the Atari had `HDIV8`/`HMOD8` |
| `L[5]`, `L[6]` | height in rows, width in bytes |
| `L[7]` | was the frame's byte length; **unused — except for the BALL, where it is the idle counter** |
| `L[8]` | ⭐ **the state byte**, and the animation counter. Bit 7 is a DIRECTION flag and also "this part fired", which is what the wiring kit reads |
| `L[9]` | b7 unwireable, b6–4 sound, b3–0 score |
| `L[10]` | ⛔ **the part TYPE ID**, where the 6502 had three addresses (§5b) |
| `L[16..22]` | the ball's own record: `BSTAT, X1, Y1, BDX, BDY, BXACC, BYACC`. Other parts use `L[16]` as a second state byte |

**The database** heads with `LOGIC[24]` (six 3-input AND gates × 4 bytes) and `WSET[4]`
(gravity, speed, kick, elasticity), exactly as it heads the Atari's `$4B00` and for the same
reason: they are the first bytes of a saved table. `PBDATA[0]` is the object count **and**
the offset from `PBDATA+1` to the first record, which is why the walk needs no index.

⚠ **Keep the original's limits** — 127 objects, 63 vertices, **8 active edge records**
(`PPAK.s:568`), 32-byte span-DB headroom with rollback on overflow. They are part of what
the construction set *is*.

⛔ **And the eight is PER OBJECT, not per scanline.** The active list belongs to the polygon
being scanned, so one polygon may have four spans on a line and the next gets its own eight;
there is no cap on spans per scanline anywhere in `PPAK.s`. ⚠ This spec and the bench both
claimed otherwise until the edit gate went looking for a refusal and could not provoke one.

**The colour picker** replaces `EDIT.s`'s three paint pots (`$FF`, `$55`, `$AA`,
artefact colours on the Atari). It is a 12 × 10 grid of palette entries **32–151**
(`pcspal.PICK`): a row of greys from white to black, then nine rows of twelve hues from
dark to light, sampled from the reference picker supplied on 2026-09-24. Cells are 8 × 8
card pixels, centred in the kit panel under the tool column (x 432–527, y 360–439), and the
current colour carries a one-pixel frame, white on a dark cell and ink on a light one. A
table's `FILLCOLOR` is the entry number, so ⚠ **entries 32–151 are file format** and are
append-only. Entries 1–3 stay the translation of an imported table's dither masks, and the
editor starts on white (cell 0), the original's `COLOR = $FF`.

**The art.** `BITMAPS.OBJ` (1,792 bytes) with the offset table at `RUN.s:100`. ⭐
`mkpcs.py` reads all of it straight out of the original sources, doubles each byte's bits,
and emits the art bank — **the parts are Budge's drawings, not redrawn ones**.

### 5a. The simulator

**The ball** is a 5 × 5 disc; `BDX`/`BDY` are signed bytes in **1/32 px per frame**, clamped
to ±63; `BXACC`/`BYACC` are the sub-pixel accumulators. **`BDY` positive is up-screen.**
Motion is one pixel at a time, Y then X, and *the step is only committed when the probe says
clear* — so the ball never overlaps geometry.

**Angles** are 0–31 for a full turn and ⚠ **non-uniform**: `SUB[0..7] = 0, 5.625, 11.25,
22.5, 45, 67.5, 78.75, 84.375°` — crowded towards the axes and coarse at 45, so a ball
rolling along a nearly flat surface gets fine angular resolution where it matters. `ROTATE`
folds into the first quadrant, then does `(x cos θ − y sin θ, x sin θ + y cos θ)` with **two
lookups and no multiply**, out of ⭐ **seven 64-entry cosine tables**. The same tables are
the elasticity curve: `ELAST[vn]` is `vn · 4 · cos a` and `>> 2` makes it `vn · cos a`, so
the slider picks *which cosine*.

⛔ **The quadrant fold applied is the INVERSE of the fold owed**, and only the 180° case is
its own inverse. Using one number for both folds `(12, -12)` to `(-12, -12)`, whereupon
`ROT6`'s ceiling clamps both components to `$3F`.

**Collision** is `CHECKHORIZ` (`RUN.s:1570`) and `CHECKVERT` (`RUN.s:1668`) walking the
scanline's span records. ⛔ **Object 0 is read inside out**: the backdrop is a B-polygon
whose *records* are the open playfield, so the GAPS between them are wall. ⛔⛔ **And
`CHECKVERT` ALTERNATES between its two readings**, at every record where the object changes
— `BEQ BCHECKV2` leaves object mode and `BCHKV5`'s `JMP PCHECKV2` returns to it. Records are
in draw order, so object 0's come **first** on every scanline of a normal table and the
alternation is the only thing that ever reaches an object at all. ⚠ A walk that leaves
object mode for good passes any test whose objects are only met side-on, because
`CHECKHORIZ` has no modes.

`DOVHIT`'s `VLFIX`/`VRFIX` flatten a steep edge to a floor when the ball is falling onto it,
with thresholds 6 and 11 out of the sixteen slope codes. ⚠ That heuristic **is** the game's
feel.

**Each part is three procs and one state byte** — `RUN` (called when `frame & TIME[obj] ==
0`), `INIT` (the wiring's "turn off"), `HIT` (returns carry = "the ball was deflected").
There is no class hierarchy and no message dispatch: twenty-two HIT procs, fourteen RUN
procs, ten INIT procs, and a four-byte record.

⭐⭐ **The flipper is the one part that is not a polygon.** Its collision is resolved against
its **art**, row by row: each of sixteen frames carries a list of (right, left) pairs, one a
row, and the proc finds the row the ball is entering, reads that row's two ends, and only
then decides whether it was touched. The kick is `FLPVCTR` indexed by **where along the
flipper** the ball struck — the tip shot is a table lookup. The right-hand flippers are the
same tables read backwards from `FWIDTH`.

⭐ **The ball is an object like any other** — keyed by `PLAY`, homed by its own `INIT` proc,
and **its home polygon sits in the span database and is not solid**, which is what
`NULLBOUNCE` is for. A port that quietly dropped the ball from the display list would pass
every picture test and renumber the objects underneath every saved table.

**Scores are 9-byte decimal digit arrays.** The add lands on digit 7 while the print runs 8
down to 1, so ⭐ every score is a multiple of ten, exactly as on the machine it is imitating.

**Sound** is one POKEY channel: seven effect sequences of warbling note pairs, 108 bytes of
effects plus 96 of notes. They port as square tones on one channel of the audio card,
keeping the wiring kit's eight-way assignment.

⛔ **There is no tilt and no nudge in the Atari version** — none anywhere in the sources. So
the mouse has nothing to do during play, and the keyboard carries flippers and plunger.

### 5b. The seven known bugs, and what we do with each

A bit-exact gate means the *model* must have them too, so this is an explicit list:

| | |
|---|---|
| `ELASTLO/HI[2] == [3]` (`RUN.s:2188`) | ⭐ **reproduce** — elasticity 2 and 3 behave alike, and that is what the slider did |
| `VRFIX` + rising gives `TTA = 0` where 16 is right (`RUN.s:1811`) | ⭐ **reproduce** — a ball rising into the right of an overhang hovers. Asymmetric, and it is the feel |
| slope code 17 overflows its nibble (`PPAK.s:826`) | ⭐ **reproduce** — it is in the collision data path the gate compares |
| `BOUNCE` returns "hit" even when nothing changed | ⭐ **reproduce** — deliberate for resting balls (`MOVEB9`'s 3-frame re-probe) |
| `EOR #$FF` where a negate was meant (knockers, the spinner) | ⭐ **reproduce** — the reverse kick is one larger, and `-24` gives 11 of spin, not 12 |
| `PUTSP2` does not mask `L[9]` bit 7 (`RUN.s:1330`) | ⛔ **fix** — it reads past a 7-entry table, so the magnet's `$B3` asks for entry 11. `WIRING` masks with `$70` for the same field, which is the evidence it is a slip |
| sleeper stride 22 vs 23 bytes copied (`RUN2.s:416`/`917`) | ⛔ **fix** — adjacent extra balls corrupt each other |
| saved tables hold **absolute 6502 addresses** in `L[0..1]` and `L[10..15]` | ⛔ **re-key by part type id**; the vectors are rebuilt on load. ⛔ The type list is **append-only**: inserting one renumbers every table ever written |

⚠ **And the frame rate.** The original is a busy-wait (`WAIT`, `TIMETBL`), not VBL-locked,
and gravity, flipper sweep, animation rates and the drain delay are all counted in *frames*.
We lock to the card's 59.94 Hz VBL and `wtime` is recorded rather than spun.

## 6. Where it lives

```
nitros9/level2/arm6309/cmds/pcs.asm        main, modes, the event loop
nitros9/level2/arm6309/cmds/pcsdat.asm     GENERATED — art, palette, templates, tables
nitros9/level2/arm6309/cmds/pcsdata.inc    the data area
nitros9/level2/arm6309/cmds/pcspak.inc     PPAK.s — scan converter + span DB  (the core)
nitros9/level2/arm6309/cmds/pcsdraw.inc    CDRAW.s — blits, rects, the VRAM streams
nitros9/level2/arm6309/cmds/pcsrun.inc     RUN.s — the ball
nitros9/level2/arm6309/cmds/pcsobj.inc     RUN.s — the part procs and the PLAY loop
nitros9/level2/arm6309/cmds/pcsedit.inc    EDIT.s — tools, bin, magnifier, World   (step 4)
nitros9/level2/arm6309/cmds/pcswire.inc    WIRE.s — the wiring kit                 (step 5)
nitros9/level2/arm6309/cmds/pcsfile.inc    DISK.s — ⭐ LOAD, done; save is step 5
nitros9/level2/arm6309/cmds/pcsui.inc      EDIT.s — DRAWKIT: the kit panel; MAIN's dispatch to come

arm6309/software/pcs/bench/pcsasm.py             a reader for the 6502 sources' data directives
arm6309/software/pcs/bench/pcsparts.py           the 43 templates and their art
arm6309/software/pcs/bench/pcspal.py             the palette
arm6309/software/pcs/bench/pcspak.py             PPAK.s — the scan converter, modelled
arm6309/software/pcs/bench/pcsphys.py            RUN.s — the ball, modelled
arm6309/software/pcs/bench/pcsobj.py             RUN.s — the part procs, modelled
arm6309/software/pcs/bench/pcskit.py             EDIT.s's DRAWKIT - the kit panel, rendered
arm6309/software/pcs/bench/mkpcs.py              the generator, and the bench's table
arm6309/software/pcs/bench/checkpcs.py           the gate
arm6309/software/pcs/bench/run-pcs.sh            the bench
```

## 7. Verification — `sh software/pcs/bench/run-pcs.sh`

⛔ **The model is checked before the machine is built.** `pcspak.py`, `pcsphys.py` and
`pcsobj.py` carry their own self-tests; if the transliteration is broken there is no point
finding out on a 6809 six minutes later.

⛔ **THE MODEL IS NEVER CORRECTED TO AGREE WITH THE 6809.** When they differ the 6502
decides and the fix goes wherever it was misread. A model tuned until it passes is the check
answering its own question — CLAUDE.md's `HOSTMAP` trap. ⚠ Correcting the model against the
**6502** is the one direction that is allowed, and it has happened twice.

The legs:

| | |
|---|---|
| `m0` | the scan converter: all 153,600 bytes of the table rectangle, and the span database record for record |
| `m4` | ⭐⭐ **the whole simulator**, 600 frames — the ball's `(x, y, BDX, BDY)` every frame, every part's state byte, and the score, the sound and the run chain |
| `m6` | ⭐⭐ **the editor**: a twelve-edit session through `pcsedit.inc`, two of them required to be refused, and the step results, the object area and the span database it leaves, against `pcsedit.py` |
| `k0` | ⭐ **the editor's kit panel**: `pcs 22`'s whole 320 × 480 panel column, every card pixel, against `pcskit.py` — `DRAWKIT`'s tools and parts bin, and the 12 × 10 colour picker with its frame on the current colour |
| `m1` | ⛔ MUTATION: the midpoint x rounding is dropped, so every sloped edge moves |
| `m2` | ⛔ MUTATION: a B-polygon paints its RECORDS instead of their complement — the bug that looks plausible on screen while inverting the ball's world |
| `m5` | ⛔ MUTATION: `BOUNCE` rotates back by `TTA` instead of `32 - TTA`. ⛔ The two are the SAME for `tta` 0 and 16, so a ball in a box of flat walls behaves identically and only a slope tells them apart |

⭐ **The picture includes the parts' art**, and the ball leg compares it against each part's
**final** frame and position — not against frame 0, which happened to pass and stops being
true the day a part comes to rest mid-animation. Tightening it is what found the missing
repaint.

⛔ **`fcb 6   ,8` emits ONE byte.** lwasm ends the operand field at the first space, so
printf padding turned `PCPIdx` into a table half its length: every part found the wrong
frame and it assembled without a murmur. `mkpcs.py`'s `_checkgen` now refuses any `fcb`/`fdb`
whose operand ends at a space, on every generation. ⚠ Same defect class as `grep '^FAIL'`
matching nothing — it reads exactly like success.

⭐ **The gate requires at least five LIBRARY PARTS to have been struck.** A ball that only
ever met the backdrop proves nothing about the object system, and that is exactly the run an
earlier table gave — 600 frames and 21 bounces agreeing over a collision walk that was
reading half the world.

⚠ **The bench drives the player.** A mouse and two keys are not reproducible, so the
recording mode fills `PDL0`/`BTN0`/`BTN1` off the frame counter by one rule that `pcsobj.py`
implements identically. Without it nothing that answers to the player could be gated.

⚠ Needs `../nitros9` on its `arm6309` branch, so it is in no aggregate. ⛔ Its exit code is
the answer.

## 8. Open

- ⭐ **The animation's repaint is built.** A part whose state byte or whose art's top row
  changed damages a row range; at the end of the frame those rows are **erased**, repainted
  from the span database and every picture over them put back. ⛔ The erase is not optional
  and not obvious: a library part's polygon is unfilled, `PCFill` refuses colour 0, and the
  backdrop paints its *complement* — so a repaint never writes the open playfield at all,
  and the previous frame stays underneath.
  ⚠ **The damage is a whole row range across the table**, which is honest but coarse; a
  column range would be the obvious next economy, and nothing measures the cost yet.
- ⚠ **Whether a VRAM pointer's auto-increment carries out of a row** is an open question
  about the card or the emulator's model of it. The bench's streams reposition at every row
  boundary, so they do not depend on the answer — but `graphics.md` §19 should settle it.
- ⚠ **`TIMETBL` re-derivation is an unmeasured number** until the program runs at frame rate.
- ⭐⭐ **The editor's database operations agree with the model** (`m6`, in the default
  bench). The twelve-edit session (two parts out of the bin, a drag, a vertex moved, one
  pasted and cut again, three paints, a delete, and two edits that must be refused)
  leaves the same step results, the same object area byte for byte, and the same span
  database as `pcsedit.py`. ⚠ **The editor opens a table as loaded**: mode 6 snapshots the
  object area before `PBPlay` keys the parts and restores it before the session, because
  `PBPlay` borrows every part's `L[8]` and runs every INIT proc. `PBClose` (`CLOSEOBJS`)
  is the way back from a game, and it runs the INIT procs again, as the original does.
  ⚠ **Nothing rebuilds the run chain after an edit yet**: `vlo`/`rcn` point into the
  object area, which `PERbld` rewrites, so the editor UI has to re-key (`PBPlay`'s first
  half) before it draws parts again.
- ⚠ Not open any more, but worth keeping as a method note: the two tables that
  did not paint (2026-09-23) were **two different defects wearing one symptom**,
  and both were found by **modelling the 6809 routine in Python and diffing it
  against `pcspak.render` over all 29 shipped tables** rather than by running the
  machine. `DEMO2`'s reproduced in the model (`PCRow`'s per-record complement,
  §2); `DEMO4`'s did **not** — which is what proved it was not the algorithm and
  sent the search to the database, where object 10's span turned out to be stored
  with its ends swapped. See `history.md`.
- ⭐⭐ **A TABLE IS A FILE ON THE CARD** (2026-09-23), which is what `DISK.s`
  did and for the reason it did it: PCS never held two tables at once.
  `pcs <mode> <frames> <name>` takes a **bare name**, and `pcsfile.inc`'s
  `DOpen` tries `/SD0/DATA/` then `/DD/SYS/` — `tilescroll.asm`'s and
  `changefont.asm`'s, verbatim. `mkpcs.py` writes `software/pcs/bench/pcstbl/*.pbt`
  and `mkrom.sh` copies whatever is there onto the card; the four `DEMO*.PB` are
  there today (`PCS_FILES=n` writes more). ⛔ **The files are not in the
  repository** — same container, same shipped bytes, same rule (§5c).
  ⚠ **Still open**: `pcs` cannot **save**, and the container carries no
  free-hand magnifier layer. The format has the room, and the loader refuses a
  payload longer than the object area, so a longer one is a version it does not
  know rather than a buffer it overruns.
  ⚠ And the module **still carries** up to `PCS_BUDGET` (8 KB, 7 tables) for the
  built-in modes the bench's mutation legs use. That is the last of the old
  arrangement, and it goes when `desk` gains a table picker.
- ⚠ **Not written**: the editor's UI (tools, bin, drag, magnifier, World panel), the wiring
  kit's UI, load and save, and `desk` integration. `RUN2.s`'s four-player game loop, the
  bonus tally and multiball are step 3c.
