# `pcs` — history

Superseded claims from [`pcs.md`](pcs.md), with the date each moved and what replaced
it. `CLAUDE.md`'s rule: **specs describe only the present design**. Entries before
2026-09-24 were written in `hardware/video3/docs/history.md`, when `pcs.md` lived under
`video3/docs/`, and moved here with it.

## `pcs.md` §5 — "the `pcs` module must stay under 32 KB" (2026-09-24)

Superseded the same day it was written, by the core-and-libraries layout (§5,
`pcscore.inc`). The paragraph said:

> ⚠ **The `pcs` module must stay under 32 KB.** With 21 KB of data, one byte over is five
> 8 KB blocks plus three, `F$Fork` answers `Error #207`, and nothing runs. The kit bitmap is
> stored at world resolution and cropped to the bin for exactly this reason; it is 31.1 KB
> today.

The limit it describes was real: the redrawn tool icons had put the one module 268 bytes
over four blocks, and `F$Fork` answered `Error #207`. The user's direction was not to be
bound by a 32 KB chunk at all, so the editor, its screen and the file layer became
libraries paged through one window slot, and the core is 22.8 KB.

⚠ **One gate number moved with it, for a reason that had nothing to do with `pcs`.**
`f0` had reported *"416 of 153600 card pixels differ, all of them part animation"* on
every run. All 416 were the screen's top-left 64 × 8, in colour 27: the leg stopped on the
shell's echo, after `pcs` had exited, and the window driver's repaint of that corner was
in the dump. `checkpbt.py`'s part-art tolerance let it through because it happened to be
colour 27. `LibFini` made the exit slower, the dump landed before the repaint, and the
count went to 0. `f0` now stops on `PCS-RAN`, as `run` always has.

## `pcs.md` §8 — "the 6809 side does not yet agree" (2026-09-24)

The bullet said:

> - ⚠⚠ **The editor's database operations are modelled and gated but the 6809 side does not
>   yet agree.** `pcsedit.py` and its self-tests are the specification and are green; the
>   bench's `m6` leg runs the same twelve-edit session on the machine and compares what each
>   step came to, every byte of the object area and the whole span database — and it is
>   **asked for by name** (`RUNS=m6`) until it passes, so the default bench stays honest.
>   What is established by measurement: the record each operation builds is byte-identical to
>   the model's, and the object area comes back with the original object count, so something
>   between the rebuild and the commit is undoing the session.

**What was really wrong.** The measurement it quotes had not been made: the session
**hung in its first edit**, the progress port stuck at `$20` until the 90 s budget ran
out, and the "machine took" column was VRAM nothing had written. Six defects lay behind
it, each hiding the next:

1. **`PEAdd` stored the template index after `lda #$FF`**, so every add asked for
   template 255, `PETPtr` walked off the end of `PCTmpl`, and the converter was handed a
   record with no vertices. It spun in `PKVtx`'s horizontal-edge walk (a trace's PC
   histogram named it in one run).
2. **`PKAlign` reset its rotation counter every time round** (`clrb` before looping, and
   B used as scratch by the copy), so a polygon whose every Y was equal rotated for ever.
   The refusal the routine exists to make could never be made.
3. **The editor started from a played table.** `PBPlay` runs for every mode and borrows
   `L[8]`; the port had no `CLOSEOBJS`. Mode 6 now restores a snapshot, and `PBClose`
   exists for the play-to-edit path.
4. **`template_record` kept Budge's `(HDIV8, HMOD8)` in `L[3]`/`L[4]`**, where every
   loaded table's record holds one pixel column (`pcsfile.rekey`). `PEAdd` translated a
   byte column by a pixel displacement; a rollover placed at x = 96 put its art at 198.
5. **`PEClmp` compared a room of 0..253 as a signed byte**, reading 238 − 13 = 225 as
   −31, so a bumper dragged up 5 went up 31. It clamps in 16 bits now.
6. **`PEDel` never set `perep`**, so it inherited the previous edit's. After a cut of
   object 1, the next delete "replaced" object 1 with the bytes at address 0.

`PCS_EDIT_UPTO=n` (`mkpcs.py`) truncates the session for bisecting; items 3–6 were found
with it, one run each.

## `pcs.md` §9 — "two of the four shipped tables do not paint correctly" (2026-09-23)

Both were fixed on 2026-09-23. The entry is kept because the two defects shared
one symptom — a table painted 20 % shut — and had nothing else in common, and
because of how they were told apart.

> - ⛔ **Two of the four shipped tables do not paint correctly**, and the span
>   databases are **byte-identical to the model's** on all four — so it is in the
>   painting, not the converter. `DEMO1` and `DEMO3` are within 0.26 % of the
>   model; `DEMO2` is 20 % out and the cause is known — its backdrop has **more
>   than one span on 73 of its rows**, and `PCRow`'s complement is written for a
>   single-span backdrop (§2). `DEMO4` is 21 % out with no multi-span rows and no
>   second B-polygon, and that one is not yet explained.

⭐⭐ **The method, which is the part worth keeping.** `PCRow` was transliterated
back into Python — twenty lines — and diffed against `pcspak.render` over all
**29** shipped tables. That is a second's work per table and it separated the two
faults immediately:

| | |
|---|---|
| `DEMO2`, `META PIN`, `LEECH`, `INSTANT EXERTION`, `BONUS BALL` | the model **reproduced** the error, to the pixel — so it is the algorithm |
| `DEMO4` | the model was **exact** — so it is *not* the algorithm, and the machine and the model must be reading different data |

⚠ **"The databases are byte-identical" was the claim that had to be wrong**, and
it was: re-read record by record, `DEMO4` differed on **34 of 200 scanlines**, in
one object and in nothing else.

### 1. `PCRow`'s complement was per-record, not per-run (`DEMO2`)

`DOSCN5` packs a concave backdrop's four or six crossings as two or three
**consecutive records of object 0**. The complement of the *run* is
`[0, xl₁] [xr₁, xl₂] [xr₂, 159]`; the complement of each record taken alone
re-paints `[0, xl₂]` over the open area the first record just opened. 73 rows of
`DEMO2`, 55 of `LEECH`, 16 of `INSTANT EXERTION`. `PCRow` now walks the run
(`rw5@`–`rw7@`), which is what `pcspak.render` had always done.

### 2. ⛔ `PKIns` compared a slope made of two different edges (`DEMO4`)

`ADDSTARTS6` breaks an x tie between two edges by their **8.8 slopes**, signed.
The 6809 read each slope as a word:

```
                    ldd       adxcoeff,y
                    cmpd      adxcoeff,x
```

with a comment asserting *"adxcoeff and adxfract are adjacent and big-endian"*.
⛔ **They are two PARALLEL ARRAYS indexed by edge** (`pcsdata.inc`), so
`adxcoeff,y` is this edge's integer part followed by **the next edge's**. It
assembles, it is a plausible 16-bit compare, and it decides the tie with a number
belonging to a third edge.

`DEMO4`'s object 10 is a triangle `(4,66) (18,89) (4,100)` — a **vertical** left
edge and a sloping one leaving the same vertex, so the tie-break is the whole
answer. It went the wrong way, the two crossings came out in the opposite order,
and the record read `(9, 10, 4)` instead of `(4, 10, 9)` for 34 scanlines.

⚠ **`blt` is right and needs no help**: on overflow the 6502 falls back to the
sign of `ADXCOEFF,X`, and X and Y have opposite signs exactly when the subtraction
overflows, so `N ⊕ V` and the `BVC` fallback agree on every input. Only the
operands were wrong. ⚠ And `pcspak.py` had the *other* half of it — `_s16(X - Y) < 0`
is the wrapped sign, not a signed compare; it is now `_s16(X) < _s16(Y)`.

### 3. ⛔ …and a reversed span then underflowed the painter

A reversed record is **legal 6502 output**: the active list is sorted when an edge
is *inserted* and never re-sorted as its x steps, so two edges that cross while
they run together emit `(xr, obj, xl)`, and `DOBAR` draws from A to X whichever
way round they are. Five of the 29 tables carry one — `FIREBALL` has 55 — and
`pcspak.render` swapped. `PCRow` did not: `2*xr + 2 - 2*xl` went negative, `PCFill`
read it as 65,528 and painted 256 columns at a time until it walked out of the
row. The new `PCSpn` swaps, and both arms of `PCRow` go through it.

⚠ So fix 2 removed *this* table's reversed span, and fix 3 is what stops the next
one — they are separate, and only fix 3 covers `FIREBALL`.

## `pcs.md` §2, §4 and §8 — the whole-table repaint, and a drag with no preview (2026-09-24)

Superseded by the live drag and the margin-composed row repaint (§8, `pcsui.inc`'s `Pv*`
and `RpRows`). §8 said:

> After an edit that took, `EdDone` re-keys and repaints the whole table; a paint only
> re-fills, which `PEPaint` does itself. ⚠ **A press and release that both fall inside
> a repaint are lost** — about a second — because the loop does not sample the mouse
> while it draws.

§2's XOR table gave the drag preview as *"repaint the object's damaged rows from the DB"*,
which was never built: until this entry nothing moved on the screen between the press and
the release, and the whole table was wiped to black and repainted after every edit. §4
reserved the margin for *"the part-art bank and the magnifier's backing store"*; the
art is blitted straight out of the module and the margin now holds the repaint's bands
and the dragged part.

⭐ `e0`'s final 153,600-byte picture comparison is what gates the change from a
whole-table repaint to one that covers only the damage: a row the damage range missed
would keep the old picture and fail it. It passed on the first run.

## `pcs.md` §8 — "the damage is a whole row range", and PLAY "not yet built" (2026-09-24)

Superseded by two damage bands with the art clipped to them (`pcsobj.inc`'s `PBDmR`,
`PBRep`), `EdPlay`, and mode 24. §8 said:

> ⚠ **The damage is a whole row range across the table**, which is honest but coarse; a
> column range would be the obvious next economy, and nothing measures the cost yet.

and of the tool bar, *"the other eight are recorded and not yet built"* (PLAY was one).

⭐ **It was measured when PLAY first ran from a table built in the editor**: 7 frames a
second. A dots-weighted PC histogram (`TRACE_AT`/`TRACE`, CLAUDE.md's `pchist.py` method)
put `PCBlit` at 31 %, and the band told why: every fourth frame it ran from the ball's row
to row 230, because a flipper sweep is legitimate damage and one range has to span
everything between. Three changes, each needed:

- **the art is clipped to the band** — before this every picture that crossed a damaged
  row was blitted whole;
- **two bands**, so the flippers and the ball are two short ranges and not one long one;
- **the ball damages its own seven rows**, not the 23 every other part gets (`PBDmg`'s
  2 above to 20 below).

20–30 frames a second after. ⚠ `m4`'s final-picture comparison is what gates a band that
misses a row.

Two more from the same work, both of which presented as "the ball does not launch":

- ⛔ **A table built in the module played at `wset` = 0.** Only a file carried sliders, so
  `pcs 22`/`23`/`24` ran with `GRAVTBL`'s `$FF` — gravity once in 256 frames. The defaults
  are now set before `Build`.
- ⛔ **`LAUNCHHIT` needs the button held on a frame the ball touches the plunger**, and a
  ball dropped onto it bounces for a second or two. A scripted half-second click missed
  every contact. `mkpcsbuild.py` holds it for 3.5 s.

And a scripting trap: `mkpcsbuild.py`'s clock followed only its `at` lines, but `at` is
absolute and `+` relative, so the next `at` landed inside the gesture before it — a tool
click fired in the middle of a 2.2 s vertex drag, which the machine rightly took as its
release. `e1` caught it as a record whose release was at the tool bar.

⛔ **And the exit died with `PCS-NOLIB` after a game played from the editor.** `LibFini`
unlinked each library through the window with `F$UnLink`, which needs the module mapped
and leaves the caller's map to the kernel's per-process block link counts. It now empties
the window once and `F$UnLoad`s each library by name.

## `pcs.md` §8 — the editor's UI "not written", and "nothing rebuilds the run chain" (2026-09-24)

Superseded by `pcs 23`, `pcsui.inc`'s `EdLoop` (§8, gated by `e0`). §8 said:

> ⚠ **Nothing rebuilds the run chain after an edit yet**: `vlo`/`rcn` point into the
> object area, which `PERbld` rewrites, so the editor UI has to re-key (`PBPlay`'s first
> half) before it draws parts again.

and

> ⚠ **Not written**: the editor's UI (tools, bin, drag, magnifier, World panel), the wiring
> kit's UI, load and save, and `desk` integration.

`PBKey` is that first half, and `EdDone` runs it after every edit. Four defects fell out
of the first `e0` runs, each in code older than the loop:

- ⛔ **`pcs` forced 120 frames whenever no table file was named.** `pcs.asm` tested
  `bne` on **`PFArg`'s flags** to decide whether a frame count had been given, not on
  `frames`; the loop ended after the first gesture. It now tests `frames` and falls back
  to `DEFFRM` when it is 0, so `m0`'s hold went from 120 frames to the 30 it asks for.
- ⛔ **`EditO` was row 505, inside `PCDump`'s rows 500..508** for a table the size of
  `PCDemo`. It is 510. And mode 23 dumps 2,048 bytes of it, not mode 6's 512: the demo
  table is 610 bytes before a part is added, and the first full run compared 512 and
  called byte 512 a difference.
- ⛔ **`PEPaint`'s toggle to 0 left the old colour on screen.** It re-filled without
  erasing, and `PCFill` refuses colour 0, so an object cleared to "unfilled" kept its
  paint. It wipes the rows first now.
- ⛔ **In the editor the ball was drawn at its last game's `X1`/`Y1`**, so a dragged ball
  stayed behind. `PBArtI` draws it from its header when `pbedk` is set, as the model's
  `render_table` always did.
- ⚠ And a PS/2 script's `origin` has to be where the pointer really is. The first script
  said `320 240`, and every press landed 320 left and 240 up of where it was meant.

## `pcs.md` §5, §6 and §8 — three libraries, "no free-hand layer", the magnifier "not written" (2026-09-24)

The magnifier became library 4 (`pcsmg`) and the free-hand layer a paged bitmap
(§5). What the spec said before:

> ⭐ **`pcs` is a resident core and three libraries** (`pcscore.inc`, 2026-09-24).

> `LibFini` unlinks all three on every exit. … a card must carry all four modules

> ⚠ **Still open**: `pcs` cannot **save**, and the container carries no free-hand
> magnifier layer. The format has the room, and the loader refuses a payload longer
> than the object area, so a longer one is a version it does not know rather than a
> buffer it overruns.

> - ⚠ **Not written**: the magnifier, the World panel, the tool bar's other seven tools, …

> **on a tool**: the first five (hand, pointer, scissors, hammer, brush) become the
> tool; **PLAY** plays the table (below); the other seven are recorded and not yet built.

§6 listed `pcsedit.inc` as "EDIT.s — tools, bin, magnifier, World (step 4)"; the
magnifier is `pcsmag.inc` and the tools, bin and event loop are `pcsui.inc`.

⚠ **The layer's first design was capped, and wrong twice over.** It kept a fixed number
of `(y, x, colour)` triples in the data area, sized by the bytes left there, and
refused a plot past the cap. The user's direction: *"we have literally 8 MB of RAM, a
paging MMU, and relocatable code. Why are you worried about memory space?"* — so the
layer is a whole bitmap in eight `F$AllRAM` blocks. ⛔ Its first paged version then gave
the layer **a window slot of its own**, and `pcs` has none free (§5: seven slots, three
data, three core, one library window): `F$MapBlk` would have answered with an address
other than the one wanted, or failed, and the layer would silently not exist. It pages
through the **library window** instead, by core code that puts the caller's library back.

## `pcs.md` §8 — "`pcs` cannot save" (2026-09-24)

Superseded by the DISK panel (`pcsdisk.inc`, §8) and the `d0` leg. The paragraph
said:

> ⚠ **Still open**: `pcs` cannot **save** — `PFSave` is written, trailer and
> all, and nothing in the editor calls it.

⛔ **And `PFSave` had never run correctly.** Its payload length was summed with
`lda ,x+ / clrb / addd`, which adds each record's length **times 256**, so the
first SAVE the panel made asked `I$Write` for tens of kilobytes out of the data
area and was refused with `PF.EWrt` — after the file had been created and its
header written, so the card then held a `mytbl.pbt` whose header claimed a payload
longer than the object area, and loading it was refused with `PF.EBig`. The first
`d0` run caught both, one record each, on the first SAVE and on the LOAD of what it
had written. Nothing had called `PFSave` before, so nothing had seen it.

⛔ **And under it, a second one**, which the first had hidden. With the length
right, the SAVE still said `PF.EWrt`, and the card held the header, the payload
and a trailer whose count said 1,220 pixels and which carried none. After a
pixel was buffered, `psY@` pulled X and branched on carry — and when the buffer
was not yet full, the carry was the one `cmpa #LY.Buf` had just left, set
whenever `lyk` < `LY.Buf`. So the first pixel of every layer was a write error.
A table with no layer saved correctly throughout, which is the only kind anything
had tried.

## `pcs.md` §4, §5 and §8 — "a click can be missed", "the margin is shared", and a gesture "still lost" during a repaint (2026-09-24)

Superseded by the mouse queue (`pcsin.inc`'s `UISamp`/`UIPop`), the kit cache
(`KitBin`) and the `c0`/`c2`/`cX` legs. §4 said:

> | ⚠ **A click can be missed** | a polled loop that repaints samples the button once a pass, so the mouse is sampled **inside** the repaint loop |
> | ⚠ **The margin is shared** | the ROM toolbox's glyph strike sits at column 640, rows 320–472. Our stores stay above row 320 |

The first row described a remedy that had not been built: nothing sampled the mouse
inside any loop. The second was a precaution written on 2026-09-23. The strike is
per screen and is dropped whenever `CG.SGen` changes (`ca_scr.asm`), and `pcs` owns
its screen and draws no window text through the toolbox, so the rows below 320 were
free all along. The kit cache is the first thing to use them.

§5 listed `pcsui`'s exports as `KitDraw`, `IconDraw`, `PickDraw`, and the core as
22.8 KB. The picker moved to `pcsmg` when `pcsui` reached 7,988 bytes.

§8 said:

> ⚠ **A press and release that both fall inside a repaint are still lost**, because
> the loop does not sample the mouse while it draws; the repaint is now a band of rows
> rather than the table, so the window is shorter, and nothing measures it.

⛔ **The first queue sampled only in `PCWait`, and `c0` lost a click anyway.** The
lost press lasted 0.30 s, from 41.758 s to 42.061 s of machine time, while the
editor rebuilt the span database after a refused vertex drag. That is ~0.4 s of
`PKEd6`/`PKMerge`/`PKSw3`/`PKAppend` with no VRAM access, so it never reached
`PCWait`. A PC trace answered this in one run. `PKSweep` now samples once per
scanline.

⛔ **And the core crossed into a fourth slot on the same change.** At 24,594 bytes
`pcs` needed a fourth 8 KB slot, `LibInit`'s `F$Load` found no room to map a
library, and every leg printed `PCS-NOLIB` and exited `$E9`, which is also
`PKDispX`'s progress code and so pointed at the scan converter. `TxTest` moved to
`pcsmg`, and `pcs.asm` now refuses to assemble past three slots. ⚠ **The libraries'
own `ifgt *-8192` guards had never worked**: each emitted an `fcc` string, which is
bytes and not an error. They use `error` now.

## `pcs.md` §8 — "the World panel not written"; `status.md` — "`wset` … is not editable" (2026-09-24)

Superseded by the WORLD panel (`pcsworld.inc`, in `pcsmg`), gated by `w0`. §8's
open-items bullet said:

> - ⚠ **Not written**: the World panel, the tool bar's other five tools, the
>   wiring kit's UI, and `desk` integration.

and `status.md`'s table row:

> | The World panel — four sliders | part of `EDIT.s` | `wset` already loads and drives the physics; it is not editable |

`w0`'s first run was green.

## `pcs.md` §5 and §8 — "`CMDMENU`'s rectangles unchanged", and "`desk` integration not written" (2026-09-24)

Superseded when the three paint pots left the tool column and `pcs` went on the
desktop. §5 said:

> ⛔ **Each is centred in its tool's `CMDMENU` rectangle, which
> is unchanged**, so the hit test is the original's and only the picture is finer.

The pots' rectangles (WHITE, GREEN, VIOLET: world rows 64–93) had never been drawn —
the picker replaced them — but they were still hit rectangles and tools 5–7, so a
press in the gap between BRUSH and PLAY was recorded as a tool that did nothing. They
are gone; PLAY, MAGN, WORLD, WIRE and DISK moved up 30 world rows (60 card rows) and
became tools 5–9 (`ED.Play` 8 → 5, `ED.Magn` 9 → 6, `ED.Wrld` 10 → 7, `ED.Disk`
12 → 9), and every script's clicks on them moved with them.

§8's open-items bullet said:

> - ⚠ **Not written**: the tool bar's other four tools, the
>   wiring kit's UI, and `desk` integration.

and `status.md`'s rows:

> | The tool bar's other tools | part of `EDIT.s` | the wiring kit and the rest are recorded when clicked and do nothing yet. …

> | `desk` integration | — | no icon, no `IcTab` entry, no Applications item |

## `pcs.md` §4 and §8 — "a library part cannot be painted" (2026-09-24)

Superseded when the brush started colouring a library part's art, so that
Astro Blast's flippers could be painted light blue and a new bumper yellow. §8's
brush bullet ended at *"painting a colour an object already has clears it to 0"*.
`PEPaint`'s header and `pcsedit.paint`'s docstring said:

> ⛔ A LIBRARY PART CANNOT BE PAINTED - `CMP #<LIBOBJ / BEQ PAINTO4` returns
> without touching it, because its picture is its art and its polygon is the
> invisible collision shape.

That was the 6502's rule and the port kept it. The original's art was 1bpp,
so there was nothing to colour. `WM.Sprite` draws the art in any palette
entry, so the port now keeps the part's colour in `FILLCOLOR` and gives it to
the art (`artcolr`, `PBArt`) and never to the polygon (`objcolr` stays 0). Every
shipped table's library parts carry Apple `FILLCOLOR` 16, which `FROM_APPLE`
maps to 0, so every existing table still looks the way it did.

## pcs.md §8 - the damage bands, as they stood until 2026-09-24

Replaced by four bands composed in the margin, a reach taken from the part's own
template, and a column-wise `PCBlit` with an early cull (`pcs.md` §8). The repaint on
the screen showed as a flash of wiped rows in 93 of the Astro Blast demo's play frames;
after the change, 1 or 2. Frame rate went from ~9 to 35-40 frames a second over the same
traced window (flipper frames ~450 ms to 90-130 ms).

  ⭐ **The damage is two bands of rows, and the art is clipped to them.** A frame's
  damage merges into whichever band it touches (within 4 rows), or into the empty one,
  or else into the nearer; the two merge if they come to touch. The ball damages only
  its own seven rows; any other part, its rows from 2 above to 20 below its top. So a
  flipper sweeping at the bottom and a ball at the top repaint two short bands and not
  the table between them. Each band is wiped, painted, and has **only its own rows** of
  every picture blitted back (`pcclo`/`pcchi`). ⭐ That took a game on a table built in
  the editor from ~7 to 20–30 frames a second; `PCBlit` of whole pictures had been a
  third of the time.
  ⚠ **The repaint is on the screen**, so a wiped band can show for part of a frame (a
  thin dark line, now and then, on the demo's sheet). The editor's margin composition
  (`RpRows`) is the fix if it matters.

## pcs.md §8 - `Bye` did not restore the card (until 2026-09-24)

`Bye` released `SS.Excl` and sent `DWEnd` with the card's `WADV` and WMODE as the last
drawing left them. Harmless while `PCBlit` ran along rows; once it ran down columns
under `WADV` 01, quitting from PLAY handed `desk` a card that drew its repaint as
columns - found on the Astro Blast demo's contact sheet, not by any bench. The pin leg
quit from the editor, which ends on `WADV` 00, and passed with the defect in; it plays
first now, and a mutant `Bye` fails it on two claims.
