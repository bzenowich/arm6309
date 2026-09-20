# A colour-keyed copyrect — what it would buy, and what it would cost

⚠ **A DESIGN STUDY, NOT A DESIGN.** Nothing here is built and nothing here is
proposed for `plan.md` yet. It exists so the question stops being re-argued from
memory. `demo-report.md` §10.5 did the tile-game arithmetic on 2026-09-17 and is
not repeated — it is cited. The numbers for text are from
`video3/bench/run-v3text.sh` (§16 of the same file), measured 2026-09-18.

**The feature in one sentence:** on a copyrect, skip the write access when the
source byte equals a key register, so the destination keeps what was already
there.

---

## 0. ⭐⭐ BUILT, 2026-09-19 — and not where this document expected

**The key is in the card.** A copy whose source byte is **zero** does not write that
byte, so the destination keeps its background: a full-colour transparent blit at the
engine's rate (~349 µs for a 16 × 16 sprite) where software costs **a pass a colour**
(plan §5's sprite `WMODE`, ~244 µs each).

| | as built |
|---|---|
| the compare | **one 74HC4078**, an 8-input NOR on the card's internal data bus. The byte about to be written is on IDB for the whole write access — the posted-write `'574` drives it — so the compare has the access to settle in and needs **no pipeline register** |
| the skip | **`v3lane`'s byte enables**: a keyed write enables no byte, so the SRAM writes nothing |
| what arms it | ⭐ **`WMODE` 11.** Sprite mode already means "transparent" to the span writer, so it means the same to the copy engine; any other `WMODE` copies index 0 like any other byte |
| the key's value | ⛔ **fixed at index 0**, not a register |
| the cost | **+1 DIP-14** (45 ICs, still places on 24 cm), one input pin on `v3lane`, and four of its byte-enable terms. ⭐ **`v3ptr` is untouched** |

⛔ **THREE OF THIS DOCUMENT'S CONCLUSIONS WERE WRONG, and the fitter and the packer
said so:**

1. §7.2 priced a **`74HC688`** at "+1 package" and called it the right shape. It is a
   DIP-20, and `check:place` refuses it — it pushes a sprite `'165` off the board. A
   DIP-14 fits, which is what makes the key **fixed** rather than programmable. ⚠ The
   package count was never asked of the packer.
2. §7.2 and §7.3 put the compare's result on **`v3ptr`**, "one pin into `v3ptr` and one
   literal on that term". `v3ptr` refused it **twice** — with a `CCTRL` enable bit
   (one cell, one pin) and then with `WMODE` arming it (no new cell at all, one pin and
   two terms): *"Design does not fit"* at 124/128 with every LAB at 39 of 40 inputs.
   The byte enables were the way in, and they are `v3lane`'s.
3. §7.2's timing rule — compare during the *read* access and gate the write an access
   later — is real but does not apply: comparing what the `'574` is **already driving**
   through the write access has ~20 ns of slack and no register.

⭐ **What this document got right** is the order. The key was worth nothing while a
copy cost 788 µs, and it went in the week the copy came down to 344 (§7.1).

## 1. What it costs in silicon

From `demo-report.md` §10.5, which stands:

- **`CCTRL` b1 and b2 are free** — reserved since the direction bits were dropped
  (`plan.md` §6.2).
- **No adder, no latch, no direction logic.** The source byte is already latched
  in the posted-write `'574` on the read access (`PWCK`) and leaves from it on the
  write (`PWOE`), crossing the internal bus both times, so a compare simply **gates
  the write access** — `VWE`, which is `v3ptr`'s.
- ⛔ **No part has room for the 8-pin form.** `v3ptr` has **6 macrocells and 7
  pins spare**, `v3host` **none** (§7's table), so the compare is one pin and a
  `'688` comparator, plus a `CCTRL` bit and a term.
- ⛔ **It needs a fit, and the part has form here.** `v3ptr_rows` and
  `v3ptr_both` went from 3 cascades to 19–21 and filled the part. `CLAUDE.md`:
  *a change in cascades is a timing change even when the cell count is flat.*

⚠ **And the skipped access is not free time.** The engine's cost is two accesses
a byte (`plan.md` §6.1); keying removes the *write*, so a fully-transparent row
runs at up to twice the rate and an opaque one at the same rate as today. It
never makes a copy slower. It also never makes one **faster than 4.05 MB/s** on
the bytes it does write, which matters for every estimate below.

---

## 2. Where it does **not** help

### 2.1 Tile-based games — correct, this is not the win

⛔ **A tile is not a rectangle to the engine.** The engine steps a row by the
1024-byte stride; a tile's eight rows are one 64-byte run at
`TILEBASE + code × 64`. So a keyed hero is ~15 plain copies plus ~80 keyed row
copies of 8 bytes, each seven or eight register writes from the CPU. **The
engine's own time is nothing; the register writes are the whole cost**, and
keying does not reduce their number.

⭐ **And the save-and-restore the scheme exists for is already free in tile
mode**: the hero's background is the world's tile code, so giving a cell back is
writing that code into the map — which is what `flip` does, in the same batch as
the scroll, in one blank. (§10.5.)

### 2.2 Sprites over a **scrolling** bitmap playfield — refused by the scroll

The figure itself is attractive: 32 × 16 is a rectangle on the stride, so a
keyed hero is **one copy**, and one more to restore what it covered. ⛔ But in
bitmap mode the incoming columns have to be *drawn*: at 16 px a frame that is
two tile columns — 50 tiles, 400 row copies a frame. And switching modes does
not rescue it, because **in tile mode the picture exists only as map codes and
tiles, composed at scan time** — there are no playfield pixels in VRAM for a
bitmap pass to overlay. Blitting a bitmap playfield out of the tile bank first is
~2,000 tiles, ~16,000 row copies a screen. (§10.5.)

---

## 3. Where it **does** help

### 3.1 ⭐ Sprites over a **static or slowly-changing** bitmap playfield

This is §2.2 with its one obstacle removed, and the obstacle is the scroll, not
the sprites. A screen that does not scroll every frame — a room-at-a-time
adventure, a board game, a pinball table, a paint program's brush cursor, a
desktop — pays none of the 400-row-copies cost, and then the keyed copy is doing
exactly what it is good at:

| | without a key | with a key |
|---|---|---|
| draw a 32 × 16 figure | save the 512-byte rectangle, compose the figure over it **on the CPU**, write it back | **one copy** from the sprite store |
| undo it | write the saved rectangle back | one copy, unkeyed |
| CPU touches pixels | yes, every one | **none** |

⛔ **CORRECTED 2026-09-18, BY THE SAME MEASUREMENT AS §3.2.** What stood here
compared the engine's 126 µs against ~2 ms of CPU compositing and claimed ~16×.
That was wrong, because **a copy does not cost its engine time — it costs 5.81
ms of call overhead** (`v3cpyb`), and the figure needs two of them. 11.6 ms
against 2 ms of CPU work is a **loss**, not a win.

⭐ **The win is real but it lives in the batch, not in the copy.** `SS.Batch`
exists precisely so a frame's operations are committed together in one VBL
(`libvid`, `armvid.d` BT.*), and the game path already uses it; the 5.81 ms is
the *public per-call* path that a batch is designed to avoid. So the honest
statement is:

| a 32 × 16 figure | |
|---|---|
| engine time for the two copies | **0.25 ms** |
| ⛔ as two separate `SS.Copy` calls | **11.6 ms — worse than compositing it** |
| batched, one commit | **1.90 ms**, measured 2026-09-19 |

⛔ **AND THE 1.90 ms IS NOT THE BATCH — IT IS THE CALL.** `mvania`'s scroll
batch is four `BT.Reg` records and a `BT.Tags`, twenty bits of scroll and two
tag words, and the marks split it (`bench/README.md`, `run-v3mv.sh`'s
`--blank` ROM):

| where `SS.Batch`'s 1.94 ms went (instrumented; 1.90 without the marks) | µs | |
|---|---|---|
| IOMan, SCF and the SetStat dispatch, inbound | 654 | ⛔ not ours |
| the same path, outbound | 392 | ⛔ not ours |
| `FromCallerX` — one `F$Move` of 17 bytes out of the caller's map | 486 | |
| walking the records to validate them | 160 | |
| building them in the caller | 106 | |
| `XBusy`, the `VG.BtOn` handshake, `XFree` | 73 | |
| the `F$Sleep` on a batch still pending | **0** | never taken: the scene's own frame poll has already let the last one commit |

⭐ **So the answer was `SS.Scroll` ($D5), which was specified in
`defs/arm6309.d` and implemented nowhere** — the OS tree's own version of
`check:reach`'s *open*. It carries the same twenty bits in `X`, `Y` and `U`,
so there is nothing to move and nothing to walk, and it commits through the
same door: `VG.BFlag`'s `BF.HScr`/`BF.VScr` pair, which `vidsvc.asm` writes in
the blank. **1.90 ms → 1.13 ms**, and the rest of it is IOMan.

⚠ **Which makes the per-frame OS call the floor, not the batch.** An exclusive
owner that writes the two registers itself — inside the blank its own frame
poll has already waited for, with `VSTAT` b6 read back to prove it is still
there — pays **0.04 ms** (`mvania` mode b8, measured, 0 misses in 495 frames
that fit the budget). On this machine a driver call costs about a
fourteenth of a frame whatever it carries.

### 3.2 ⭐⭐ Text compositing in a GUI — the strongest case, and it is measured

**Today a 40-character line costs 473 ms** (`demo-report.md` §16). The split,
measured the same day:

| a 40-character line, 473.26 ms | ms | share |
|---|---|---|
| the call's floor, before any glyph | 11.14 | 2% |
| parsing its 40 payload bytes (~1 ms a byte) | ~40 | 8% |
| composition — `GRow`, the `KEY` fill, the run scan | ~228 | **48%** |
| the card's half — `RowPut` setup and `VDATA` | 194.47 | **41%** |
| of which `VDATA` pixels | 6.8 | **1.4%** |

Per character: **~1.0 ms parse + ~5.7 ms compose + ~4.9 ms card = 11.55 ms**,
against a measured slope of 11.52. So ~188 ms of a line is **per-run `RowPut`
setup** — ~395 runs at **2.1 bytes a call** — and the runs exist *because the
text is transparent*: `BlitRow` splits each row into the stretches that are not
`KEY`.

⭐ **Transparency is not a feature the CPU is paying a little for. It is 41% of
the bill, plus the `KEY` fill inside the other 48%.**

⭐ **A keyed copy makes transparency the card's problem.** Render each glyph
**once** into the off-screen margin (columns 640–1023, 184 KB spare — where Paint
already keeps its document), key on the background index, and then:

| drawing a 40-character line | cost |
|---|---|
| today | **473 ms** |
| opaque text, one run a row (§4 idea 1, no hardware) | ~270 ms |
| + table-driven `GRow` (idea 2) | ~170 ms |
| ⭐ **keyed copy from a glyph cache** | **~6–10 ms** (see the caveat) |

A 12 × 17 glyph is 204 bytes ≈ **50 µs** of engine. Forty of them is 2 ms of
engine plus the per-copy register writes.

⛔ **MEASURED, AND THE CAVEAT WAS RIGHT** (`v3cpyb`, 2026-09-18):

| | |
|---|---|
| one `SS.Copy`, 12 × 17 (204 bytes) | **5.807 ms** |
| one `SS.Copy`, 204 × 1 (204 bytes) | **5.805 ms** |
| the engine's own share of it | **0.050 ms — 0.9%** |

⛔ **So a glyph-per-copy cache is dead**: 40 glyphs × 5.81 ms = **232 ms, worse
than the 218.64 ms the software path already costs.** The estimate of "≈6–10 ms"
above was wrong by a factor of thirty, and it was wrong in the direction that
would have wasted the silicon.

⭐ **And the same measurement gives the design that does work.** 17 rows and 1
row cost the *same to a microsecond*, so the cost is **entirely per call** —
IOMan, ArmIO and CoArm's dispatch, not the engine and not the register writes.
**One big copy is as cheap as one small one.** So the unit is not a glyph, it is
a **string**:

| drawing a 40-character label | cost |
|---|---|
| today, opaque (§4 ideas 1–2, built) | **218.64 ms** |
| ⭐ composed once, then **one copy** a redraw | **5.81 ms + 1.03 ms of engine ≈ 6.8 ms** |

⭐ **32×, for text that is drawn more than once** — window titles, menu bars,
labels repainted on every move or refresh, which is most of a GUI's text. The
first draw costs what it costs today; every later one is a copy.

⚠ **And it needs no new code at all.** `SS.Copy` is already public: an
application can compose a label into the margin and copy it back itself. What a
toolbox call would add is convenience, and what a **key** would add is the same
trick over a background that is not flat — which is still the thing software
cannot do.

⭐ **And this is where the key earns its keep over the cheaper alternatives.**
Ideas 1–3 in §4 get a *flat-paper* glyph cache with no hardware at all, because a
pre-composed ink-on-paper glyph needs no transparency. What a key buys on top is
**text over anything that is not flat** — the gradient window tab (where the
ramp is exactly right for one of eight steps today), an icon, a photograph, the
desktop. That is the difference between "fast text on panels" and "fast text".

### 3.3 Icons, the pointer, and window chrome

31 icons are drawn with a transparent key already (`TB.Buf`'s `KEY`, `$0F`), by
the same per-run path. They are small, so the win is proportionally the same and
absolutely small. ⚠ **The pointer is not a customer**: it is the card's hardware
sprite, five registers and nothing saved.

---

## 4. The software wins — 1 and 2 BUILT, 3 not

⭐ **Items 1 and 2 are done** (2026-09-18, `tbox.asm`), and the measured result
is in `demo-report.md` §16. A 40-character line:

| | ms | |
|---|---|---|
| before | **479.03** | |
| 1. opaque text | 333.27 | 1.44× |
| 2. a table for `GRow` | 256.16 | |
|   + the row fill two bytes at a time | **218.64** | **2.19×** |

⛔ **And every step proved it draws the SAME PIXELS**: `run-v3text.sh` draws
the line both ways into two bands and compares VRAM — 0 of 5,712 bytes differ.

1. ⭐ **Opaque text — BUILT.** `FONT` bit 2 (`F.Opaq`) fills the row with the
   ramp's own paper instead of `KEY`, so `BlitRow` emits one run. ⚠ `RPaper`
   holds each ramp's paper as a palette index, or `$FF` where the ramp has no
   flat paper — **`tab` is a step of the window tab's gradient, so opaque text
   is REFUSED there** and falls back to the transparent path. That is the
   most-drawn text in the GUI, and it is exactly what a key would rescue.

2. ⭐ **A table for `GRow` — BUILT, but NOT the one described here.** This
   section proposed 256 entries in ROM, one table a ramp, 8 KB in the unused
   pages. ⛔ **That cannot work**: `GRow` already has the font's ROM page
   mapped at `Co.WinB`, and there is no second block window for a table. What
   went in is a **32-byte nibble table in RAM** — sixteen entries of two bytes,
   a nibble being two pixels — rebuilt per call by `MkTab`. ~60 cycles a pixel
   became ~15, for 32 bytes and no ROM at all.

3. ⛔ **A flat-paper glyph cache — NOT built**, and §7.1 is why it is no longer
   obviously worth building: a copy costs a fixed ~725 µs, so a glyph-sized
   blit is **788 µs against the ~250 µs a character now costs to compose**. The
   cache only pays for a **whole string** (§3.2), and only when that string is
   drawn more than once.

⚠ **And this section's closing claim was wrong.** It said 1–3 "answer §3.2's
open question (the in-driver copy cost) as a side effect". They did not —
`v3cpyb` did, by measuring it, and the answer retired §3.2's own arithmetic
along with two more estimates in §7.

---

## 4.1 What is actually outstanding

| | state |
|---|---|
| opaque text (§4.1) | ⭐ **built**, gated by `run-v3text.sh` |
| `GRow`'s table (§4.2) | ⭐ **built**, same gate |
| `SS.CopyN`, the software copy list | ⭐ **built**, 2.75×, and gated by `run-v3copyn.sh` — the same rectangles as one table and as N calls, 0 of 307,200 bytes differ |
| a tighter `CpRun` — one `VcWait` a copy | ⭐ **built**: 779 → 695 µs |
| ⭐ **the per-copy work itself** (§7.1) | ⭐ **built 2026-09-19**: the register poll the pin already does, the block copy into `VG.CpBlk`, the `VG.CpA` round trip and the walk's arithmetic — **698 → 344 µs a copy, size-independent**, and the engine's own time now overlaps the next rectangle's set-up |
| a **string** cache in the margin (§3.2) | ⛔ not built, and the first thing that would pay |
| the **hardware descriptor walker** (§7.1.1) | ⛔ not built — and the CPU spends more building a VRAM descriptor (91.6 µs) than writing the registers it replaces (~33 µs), so it only pays for **persistent** lists or for the concurrency. ⚠ At 344 µs a copy the case for it is weaker again: ten sprites fit in half a frame without it |
| the **colour key** itself | ⭐ **built 2026-09-19** — §0. A `74HC4078`, `v3lane`'s byte enables, armed by `WMODE` 11, keyed on index 0 |
| more hardware sprites (§6.4) | ⛔ not built — the answer to genre C, which the key does not serve |

⚠ **Two gaps in the gates, not in the code**: the V3 IRQ-masked stretch that
one-`VcWait`-a-copy created (~250 µs) has nothing measuring it, and
`run-v3copyn.sh` copies from unwritten margin, so it is strong on the walk and
the destinations and weak on source-address errors.

---

## 5. What would have to be true

⭐ **The one thing that had to be true first is.** A key is a term on the copy
engine's write strobe, so it could not be priced until the engine existed: on
2026-09-18 `check:reach` showed the four parts had **neither sequencer built**,
and both went in on 2026-09-19 — the span writer on `v3ptr`, the copy's phase
machine on `v3host` (`plan.md` §14 item 14; `history.md` has the steps).

- [x] ⭐ **The two sequencers are built and fitted**, and the gate is passed:
      `plan.md` §14 item 14 has the table. ⛔ **Which re-prices the key, and not
      in its favour.** The compare wants the source byte, which means eight
      pins into whichever part gates the write strobe, and **there is no part
      on this card with eight spare pins**: `v3dot` has one pin and 7 cells,
      `v3scan` one pin, `v3ptr` — which makes `VWE`, the write strobe — 7 pins and
      6 cells, and `v3host` **none**. ⭐ So §7.2's **`74HC688` — one pin** — is not
      the cheaper-by-a-package option.
      It is the only version of this feature that fits anywhere.
      ⭐ **The good half of the news stands**: the key is a term on a write
      strobe, which is the cheapest form it can take. It is the PART that is
      not settled, not the compare.
- [ ] `v3ptr` fits with the compare, **and its cascade count is read out of the
      new `.fit`** and compared with the old (`CLAUDE.md`'s trap).
- [ ] The in-driver copy cost is measured, not assumed (§3.2's caveat).
- [ ] A decision on the key value: a reserved palette index (like `TB.Buf`'s
      `$0F`) costs a colour; a `CCTRL`-selected register costs a register.
- [x] ⭐ **`check:reach` covers video3** (done 2026-09-18) — a `CCTRL` bit that
      nothing reads is exactly the `ACTRL` b3 defect the check exists for, and
      until that day the check was not watching this card at all. `check:pins`
      covers it too, and found three wrong pin senses the day it did.

---

## 6. ⭐ Many sprites on a playfield — and whether the three genres are reachable

The question this study was reopened with: does a keyed copy let this machine
run a **metroidvania**, a **Turrican-style side-scroller**, or **Mario-like
mayhem**? The short answer is that **a key is necessary for two of the three and
useless for the third** — and that for all of them the *binding* constraint is
something else entirely.

### 6.1 The frame budget, which decides everything

| | |
|---|---|
| a frame, `VMODE 00` | **14.3 ms** — 29,933 E cycles |
| a CPU byte into VRAM | **7.63 µs** (16 E cycles, `vidcore`'s spacing) |
| an engine byte | **0.247 µs** — **31× the CPU** |
| ⛔ **one `SS.Copy`, public path** | **5.81 ms**, whatever its size (measured, §3.2) |

| | bytes | by CPU | by engine |
|---|---|---|---|
| a 16 × 16 sprite | 256 | 1.95 ms | 0.063 ms |
| a 32 × 32 sprite | 1,024 | 7.81 ms | 0.253 ms |
| a 16 px column of a 480-line screen | 7,680 | 58.6 ms | 1.90 ms |
| a 16 px column of a 200-line screen | 3,200 | 24.4 ms | 0.79 ms |

⛔ **Read the CPU column first: ONE 32 × 32 sprite is half a frame.** Compositing
sprites on this CPU is not slow, it is impossible — which is why the existing
game composes *tiles* and lets the map do the work.

### 6.2 ⛔ The binding constraint is not the key. It is the per-copy overhead.

Ten sprites need ~20 copies a frame (draw and undo). At the engine's rate that is
**1.3 ms**. Through one `SS.Copy` a rectangle it is **43 ms — three frames**; through
the software list `SS.CopyN` that is now built, **15.8 ms — still more than a
frame** (§7.1, measured).

⭐ **So the feature that unlocks all three genres is a COPY LIST** — and §7.1
measures that it has to be a **hardware** one. `SS.CopyN` is built and is 2.75×;
what it leaves is ~725 µs a copy of driver register sequencing, which is 15.8 ms
for ten sprites against a 14.3 ms frame. A card that walks descriptors takes that
to ~78 µs a sprite and 1.6 ms for ten.

### 6.3 The three genres

| | tile mode | bitmap + key + copy list | the blocker |
|---|---|---|---|
| **Metroidvania** | sprites cost tiles | ⭐⭐ **the natural fit** | none, if a room fits VRAM |
| **Turrican-style** | scroll is free, sprites are not | ⭐ plausible at 200 lines | the page flip, and the refill |
| **Mario-like** | ⭐ animated tiles are one write | ⛔ animated tiles cost every instance | wants *sprites*, not copies |

**A. Metroidvania — the natural fit, and the cheapest to reach.** Rooms are
static or slowly scrolling, so the playfield is drawn **once a room** and the
per-frame cost is only the sprites. Better, a room larger than the view can live
in VRAM and scroll with `HSCROLL`/`VSCROLL` for one register write and **no
refill at all**: a 640 × 400 room is 256 KB, half of VRAM, leaving the rest for
the sprite store. 15 sprites is ~30 copies ≈ 3 ms of a 14.3 ms frame.
⭐ **This one works with a key and a copy list, and nothing else.**

**B. Turrican-style side-scroller — plausible, at a cost stated up front.**
Continuous scroll means refilling the columns entering the view: at 16 px a frame
that is **1.90 ms of engine on a 480-line screen, 0.79 ms at 200** — affordable —
but as ~30 tile copies a column it is 30 × the per-copy cost, which is the copy
list again.
⛔ **And the page flip forces the height.** VRAM is 512 rows on a fixed
1024-byte stride, so two pages of 480 do not fit and two of 240 do (§10.5's
table). **A scrolling shooter here is a 320 × 200 or 640 × 200 game**, not a
640 × 480 one.
⛔ **PARALLAX IS NOT FREE, AND AN EARLIER DRAFT OF THIS SECTION SAID IT WAS.**
It claimed `SS.Raster`'s display list would give `HSCROLL` per band. **video3
deleted the display-list engine** — `plan.md` §0: *"⛔ Deleted | the display-list
engine — and with it per-scanline `HSCROLL`, per-scanline palette, raster bars
and `SS.Raster`"* — and the demo's own first caption says "four CPLDs, **no
display list**". There is one `HSCROLL` for the whole screen.

So parallax here means the CPU changing `HSCROLL` mid-frame, timed against
`VSTAT`'s `HBLANK` bit: a poll loop per band, with no hardware to hold the
schedule. Two or three bands might be affordable; it is **CPU-chased raster, not
a free feature**, and it belongs in the cost column rather than the credit one.

**C. Mario-like mayhem — ⛔ the key does not help, and the card already can.**
This is the genre that most wants **tile mode**: the scroll is one register
write, and an **animated tile is a single write to the tile bank that changes
every instance of it at once** — coin spin, question blocks, flowing water. In
bitmap mode each instance is its own copy, so animation scales with what is on
screen instead of with the tileset.
⭐ **What a Mario-like needs is not a keyed copy but MORE HARDWARE SPRITES.** The
card has one 16 × 16 sprite (five registers, nothing saved) and it is spent on
the pointer. Eight of them would carry the player, the shell and a few enemies
over a tile playfield with **zero** VRAM traffic.

### 6.4 So, the feature list

| | wanted by | already there? |
|---|---|---|
| ⭐ **a copy list** — N rectangles, one call | A, B, and every bitmap path | ⛔ no, and it is the biggest lever |
| ⭐ **colour-keyed copy** | A, B | ⛔ no (this document) |
| **more hardware sprites** | C above all, helps A and B | ⛔ one, and the pointer has it |
| page flip at ≤ 240 lines | B | ⭐ yes — `VSCROLL` in the blank (§10.5) |
| per-band `HSCROLL` for parallax | B | ⛔ **no** — the display-list engine was deleted (`plan.md` §0). CPU-chased, or bring it back |
| a sprite store in the off-screen margin | A, B | ⭐ yes — 184 KB, where Paint's document lives |
| batched commits in one VBL | all | ⭐ yes — `SS.Batch` |

⭐ **The honest ranking**: the copy list is worth more than the key, because the
key without it is 5.81 ms a sprite. The key is worth more than more sprites for
A and B; more sprites is worth more than either for C.

---

## 7. ⭐ Pricing the two, on a card whose constraint is PINS

⛔ **AN EARLIER DRAFT SAID "none of the four video3 CPLDs has ever been fitted".
THAT WAS WRONG.** All four were fitted and committed on 2026-09-16 — `v3dot`
(`8b58bab`), `v3host` (`3d66089`), `v3ptr` (`4e28142`), `v3scan` (`363c86e`) —
in **`hardware/gal/cpld/`**. The draft looked in `hardware/gal/video3/cpld/`,
found nothing, and concluded from the absence instead of from `git ls-files`.
⚠ **Absence in the directory you guessed is not absence.**

So these are real numbers out of the real `.fit` files, not `partition.md`'s
estimates:

| part | logic cells | I/O pins | cascades | foldback |
|---|---|---|---|---|
| `v3dot` | **121/128** — 7 spare | 63/64 — one spare | ⚠ 5 | 39/128 |
| `v3host` | 58/128 — 70 spare | ⛔ **64/64** — **no** pin spare | 0 | 0 |
| `v3ptr` | ⛔ **124/128** — 4 spare | 58/64 — 6 spare | **3** | 52/128 |
| `v3scan` | 112/128 — 16 spare | 63/64 — one spare | 3 | 39/128 |

⚠ **`v3ptr`'s 3 cascades are the baseline a refit is compared against**, not
zero, and its Nodes+FB is at 133 % with seven of eight LABs at 39 of 40 inputs — a
part that refuses additions on grouping before it runs out of cells.

⛔ **The room is cells on `v3host`, and it has no pins.** Pins are the binding
constraint (`partition.md` §7.1), and the only part with more than one spare is
`v3ptr` — which does gate the write strobe (`VWE`), and has seven.

### 7.1 ⛔ MEASURED, AND IT REVERSES THIS SECTION'S RECOMMENDATION

`SS.CopyN` is **built** (`vidcpy3.asm`'s `DoCopyN`, `SS.CopyN` = `$E1`, a table
of up to 32 rectangles walked by ArmIO). It is worth **2.75×**, not 50×, and
that is not enough.

⛔ **First, the number this document was built on was wrong.** §3.2's "one
`SS.Copy` costs 5.81 ms" came from wall-clock over 200 copies of a *forked
command*, and **~740 ms of that was the fork** — measured directly by running
32 and 192 copies and taking the slope. Corrected:

| | per copy, 204 bytes |
|---|---|
| one `SS.Copy` a rectangle | **2,143 µs** |
| ⭐ `SS.CopyN`, 32 a call | **779 µs** — **2.75×** |
| `CpRun` alone (`CALLTIME`) | 543 µs |
| `CpWait` — the engine itself | **54 µs** |

⭐ **AND THE RESIDUAL WENT, 2026-09-19 — 698 → 344 µs A COPY.** The figures above
are the state this section reasoned from; what was left after one-`VcWait`-a-copy
turned out to be arithmetic and copying rather than waiting:

| | before | after |
|---|---|---|
| `SS.CopyN`, 204 B | 698 µs | **344 µs** |
| `SS.CopyN`, 256 B (a 16 × 16 sprite) | 708 µs | **349 µs** |
| `SS.CopyN`, 20,000 B | 5,708 µs | 5,125 µs |
| `CpRun` alone | 465 µs | **220 µs** |
| the IRQ-masked stretch a copy | 276 µs | **130 µs** |
| ⭐ ten sprites, 20 copies of 256 B | 14.17 ms | ⭐ **6.98 ms** of a 14.3 ms frame |

**What went**: the `SPANBUSY` poll before each register group — `v3host`'s `WAITN`
holds a register *write* under a span or a copy in its own bus cycle and the strobes
are qualified by `!BUSY`, so the poll did in software what the pin does in silicon
(a register *read* is not held, which is why the one remaining poll still works);
the 12-byte block copy into `VG.CpBlk`; the `VG.CpA` round trip, because the
column's low byte **is** the address's low byte, so it is an OR and not an add; and
`CpOver` when the destination precedes the source. The engine's 0.247 µs a byte is
unchanged hardware, but ~180 µs of it now overlaps the next rectangle's set-up, so
**a copy under ~728 bytes retires for free**. ⚠ The IRQ mask stays: what the
sequence guards against is the VBL service moving `WPTR` between the pointer write
and `GO`, which is not something `/WAIT` can hold.

⚠ **`SS.Copy` is $DF, not $E0**, and `v3cpyb`'s modes 0 and 1 are the same run —
`cmpd #3 / lbne List` sends everything but 2 and 3 to the table path.

⛔ **And the observation I reasoned from was an artefact of my own bench.**
§3.2 said "17 rows and 1 row cost the same to a microsecond, so the cost is
entirely per call". **12 × 17 and 204 × 1 are both 204 bytes** — I varied the
shape and held the size constant, then concluded size did not matter. Varying
the size says otherwise:

| rectangle | bytes | per copy | engine | engine's share |
|---|---|---|---|---|
| 12 × 17 | 204 | 779 µs | 50 µs | **6%** |
| 200 × 100 | 20,000 | 5,658 µs | 4,938 µs | **87%** |

⭐ **So a copy is a fixed ~725 µs plus 0.247 µs a byte**, and the two rows agree
on the constant to within 5 µs. The fixed part is the driver's per-copy register
sequencing — `CpSrc`, `CpDst`, `CpGo`, each with its own `VcWait` — and **software
cannot remove it, because it IS the software.**

### 7.1.1 ⛔ Which makes a HARDWARE copy list necessary, not an optimisation

| | per 16 × 16 sprite | 10 sprites (20 copies) | 30-tile column refill |
|---|---|---|---|
| `SS.CopyN`, software, as this section was written | **788 µs** | ⛔ **15.8 ms** | ⛔ **23.7 ms** |
| ⭐ `SS.CopyN` **as measured 2026-09-19** | **349 µs** | ⭐ **6.98 ms** | ⭐ **10.5 ms** |
| a card that walks descriptors | ~78 µs | ⭐ **1.6 ms** | ⭐ **2.4 ms** |
| **a frame** | | **14.3 ms** | **14.3 ms** |

⛔ **SO THIS SECTION'S CONCLUSION IS WITHDRAWN.** "Ten sprites do not fit in a frame
with a software list" was true of a 788 µs copy. They fit in half a frame at 349,
and a 30-tile column refill fits too. The hardware walker is worth the concurrency
and the persistent list, not the arithmetic — §4.1 has the current state.

⛔ **Ten sprites do not fit in a frame with a software list.** Not "cost 16% of
a frame" — *do not fit*. The hardware list is ~10× on a sprite and it is the
difference between §6's three genres being reachable and not.

⭐ **An earlier draft of §7.1 said the copy list "is FREE, it is not a hardware
feature at all" and put software first. That was wrong**, and it was wrong
because it rested on the 5.81 ms figure: if the cost had been the call, a
software list would have taken it. The cost is the per-copy register work, and
only silicon takes that.

⚠ **What is still true**: `SS.CopyN` is the right API either way, it is built,
and it is 2.75× for free — a hardware walker replaces the *walk* behind the same
call. And the 725 µs is software that has never been tuned; a tighter `CpRun`
with one `VcWait` instead of three might halve it. That would make the hardware
list ~5× rather than ~10×, and **ten sprites would still not fit**.

### 7.2 The key, three ways

The compare needs the **source byte**, which already exists on the board: the
posted-write `'574` latches it on the read access and drives it back out on the
write (§1). What differs is where the comparing happens.

| | CPLD pins | macrocells | packages |
|---|---|---|---|
| key = a **constant** index in `v3ptr` | **8** (the source byte in) | ~2 — an 8-input AND of literals is one product term, and the toolbox already reserves `$0F` as `KEY` | 0 |
| key = a **register** in `v3ptr` | **8** | ~17 — 8 for the register, ~9 for the comparator | 0 |
| ⭐ key compared by a **`74HC688`** on the board, its result gating the write | **1** | ~2 | **+1** |

⭐ **The third is the right shape for this card, and `partition.md` §7.1 is why**:
*"a card whose binding constraint is pins... a `'574` or a `'165` has zero pin
overhead, because its pins ARE its data."* Spending 8 pins on a byte
that is already on the board, to save one discrete package, is the trade this
project has already refused once — and no part on the card has 8 to spend.

⛔ **And there is a timing rule the cheap versions must obey.**
`timing.check.ts`: a slot is 158.9 ns, an access is 72 ns, and **two accesses fit
with 14.9 ns to spare**. A `'688` is ~20–35 ns. **It cannot sit in series inside
the write access.** The compare has to run during the *read* access and gate the
*write* one an access later — 72 ns apart, which is comfortable, but it makes
this a **pipelined** change rather than a combinational one, and that is exactly
the kind of change that moves cascades.

### 7.3 What to buy, in order

1. ⭐ **`SS.CopyN`** — done, 2.75×, no silicon. It was worth building for the API
   alone, and it is what measured the residual.
2. ⭐ **DONE, and it was the whole answer.** One `VcWait` a copy, then the
   arithmetic and the copying around it: **344 µs a copy**, ten sprites in 6.98 ms
   of a 14.3 ms frame (§7.1).
3. **Only then the hardware descriptor walker**, and only for the concurrency —
   the CPU spends more building a VRAM descriptor than writing the registers it
   replaces, and ten sprites now fit without it.
4. **Then the key**, which is worth a package once a copy is cheap — and a copy
   is cheap now, so this is the next thing on the list rather than the fourth.
5. **More hardware sprites** last — the answer to genre C, which the key does
   not serve at all.

⭐ **The key is one more term on one strobe.** The copy's write is `v3ptr`'s
`VWE` — `CSTEP`, beside the span writer's retire terms — so a `'688`'s result is
one input pin into `v3ptr` and one literal on that term.

⚠ **What is still missing before any of this is a design**: a **re**fit of
`v3ptr` with the compare, read out of the new `.fit` and compared **against its
existing 3 cascades and 122 cells**, not against zero — on a part at 133 %
Nodes+FB, where the fitter refuses on grouping first; and the spare-access
budget, which `plan.md` §14 item 8 still owes.
