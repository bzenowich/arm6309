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

