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

## 1. What it costs in silicon

From `demo-report.md` §10.5, which stands:

- **`CCTRL` b1 and b2 are free** — reserved since the direction bits were dropped
  (`plan.md` §6.2).
- **No adder, no latch, no direction logic.** The source byte is already latched
  in `vread` on the read access and leaves through the posted-write `'574` on the
  write, so a compare simply **gates the write access**.
- `v3ptr` has **18 macrocells and 20 pins spare** (`partition.md` §2.3): about
  8 pins to bring `vread` into the part, or one pin and a `'688` comparator,
  plus a `CCTRL` bit and a term.
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
| batched, one commit | the batch's cost, **which has not been measured either** |

⚠ **So §3.1 is not proven.** It is plausible and it is the right shape, and it
now rests on a second unmeasured number rather than the one §3.2 retired. The
bench that would settle it is `v3cpyb` again, issuing its copies through
`SS.Batch` instead.

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

## 4. What to do first, and why the key is not first

Measured shares say the software wins are large, cheap and independent of any
fit:

1. **Opaque text** — the `RAMP` already names ink *and* paper, so a row can be
   written whole: the `KEY` fill goes, the run scan goes, and **395 `RowPut`
   calls become 17**. Costs +25 ms of `VDATA`, saves ~185. No hardware.
2. **Table-driven `GRow`** — 256 entries mapping a source byte (4 pixels at
   2 bpp) to 4 output bytes, one table a ramp, 8 KB in the **38 unused ROM
   pages**. ~60 cycles a pixel becomes ~10.
3. **A flat-paper glyph cache in the margin**, blitted by the *existing* engine.
   No hardware, and it is the same code a keyed cache would use.

⭐ **Do 1–3 first regardless.** They are the same work a keyed copy needs
underneath it, they need no fit, and they answer §3.2's open question (the
in-driver copy cost) as a side effect. If a key is then added, the cache stops
caring what is behind the text — which is the part software cannot do.

---

## 5. What would have to be true

- [ ] `v3ptr` fits with the compare, **and its cascade count is read out of the
      new `.fit`** and compared with the old (`CLAUDE.md`'s trap).
- [ ] The in-driver copy cost is measured, not assumed (§3.2's caveat).
- [ ] A decision on the key value: a reserved palette index (like `TB.Buf`'s
      `$0F`) costs a colour; a `CCTRL`-selected register costs a register.
- [ ] `check:reach` gets an entry either way — a `CCTRL` bit that nothing reads
      is exactly the `ACTRL` b3 defect the check exists for.

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
**1.3 ms**. At the measured `SS.Copy` cost it is **116 ms — eight frames**.

⭐ **So the feature that unlocks all three genres is a COPY LIST**: many
rectangles described in one table and issued by one call, exactly as `SS.Raster`
already does for register writes. The driver would walk the table writing seven
registers a copy and waiting on `CBUSY`, so a copy should cost its registers and
its engine time and nothing else.

⚠ **~100 µs a copy is an ESTIMATE and must be measured before anyone designs to
it** — this study has already had one thirty-fold estimate retired (§3.2), and
`v3cpyb` is the bench that would settle it by issuing its copies through a list
instead of one SetStat each.

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
| `v3dot` | **122/128 (95%)** — 6 spare | 52/64 | 0 | 37/128 |
| `v3host` | ⭐ **27/128 (21%)** — 101 spare | 42/64 — 22 spare | 0 | 0 |
| `v3ptr` | **110/128 (85%)** — 18 spare | 44/64 — 20 spare | **3** | 45/128 |
| `v3scan` | 100/128 (78%) | ⛔ **63/64 (98%)** — **one** pin spare | 2 | 17/128 |

⭐ **`partition.md`'s estimate for `v3ptr` was right to the cell**: 18 spare and
20 pins, which is what §10.5 quoted. ⚠ **And `v3ptr` already carries 3
cascades** — that is the baseline a refit has to be compared against, not zero.

⭐ **`v3host` is where the room is**, by a wide margin: 101 cells and 22 pins.
⛔ **`v3dot` has six cells** and `v3scan` has **one pin**; neither can take
anything.

### 7.1 ⭐ The copy list is FREE. It is not a hardware feature at all.

A new SetStat — `SS.CopyN`, X = a table of rectangles, Y = how many — walked by
**ArmIO**, which already owns `vidcpy3.asm` and is **not** under CoArm's 16 KB
cap (it is 6,627 bytes). Per copy it costs seven register writes and a `CBUSY`
wait, which is what `CpSrc`/`CpDst`/`CpGo` already do; what it deletes is the
5.81 ms of IOMan, SetStat dispatch and `FromCallerX` **per rectangle**, paying it
once for the table instead.

| | silicon | est. per copy |
|---|---|---|
| today, one `SS.Copy` a rectangle | — | **5.81 ms** (measured) |
| ⭐ **`SS.CopyN`, software** | **none** | ~50–100 µs — **to be measured** |
| a card that walks descriptors in VRAM | ~25–40 macrocells, and a **sixth** requester on a spare-access budget `plan.md` §14 item 8 has not re-derived for the current five | engine time only |

### 7.1.1 ⚠ A hardware list IS faster. Software first is a sequencing call, not a verdict.

An earlier draft read as though a software list made the hardware one
unnecessary. It does not. Per copy of a 16 × 16 sprite (256 bytes):

| | µs | |
|---|---|---|
| today, one `SS.Copy` a rectangle | **5,810** | measured |
| software list: 7 register writes | 33 | |
|      + the `CBUSY` wait | ~20 | assumed |
|      + the engine itself | 63 | arithmetic |
|    **= software list** | **~117** | ⭐ **50×** |
| **hardware list** — engine + a descriptor fetch | **~71** | ⭐ **82×** |

⭐ **Why software gets most of it**: the 5,810 µs is almost all *operating
system* — IOMan, the SetStat dispatch, `FromCallerX` copying the caller's block
into the system map — and it is paid **per rectangle**. A list pays it **once for
N**. That is the 50×, and it is free.

⭐ **Why hardware then adds only 1.64× of throughput**: what is left after the
list is 7 register writes and a wait against the engine's own 63 µs. **The engine
is already more than half the remaining cost**, so deleting everything else
cannot do better than ~1.6×.

⛔ **But throughput is the wrong axis, and this is the real argument for
silicon.** A software list keeps the **CPU busy for the whole batch**; a hardware
list starts a descriptor chain and hands the CPU back:

| | CPU occupied, software | CPU occupied, hardware |
|---|---|---|
| 10 sprites, draw and undo (20 copies) | **2.33 ms** | 0.16 ms |
| a 30-tile column refill | **3.50 ms** | 0.24 ms |

Against a **14.3 ms** frame that is **16–24% of the frame handed back to game
logic**. For §6's three genres that matters more than the 1.6×.

⭐ **So why software first?** Three reasons, none of them "it is better":

1. It is a **prerequisite either way**. The driver needs an `SS.CopyN` API whether
   the walking is done by the CPU or handed to the card; the hardware version
   replaces the *walk*, not the call.
2. It **measures the residual**, which is what prices the silicon. The 33 µs and
   the wait above are estimates, and this document has already had one estimate
   retired by a factor of thirty.
3. ⛔ **The card has no room for it today.** `v3dot` has **6 cells**, `v3scan`
   has **one pin**; only `v3host` has space, and it is the host interface, not
   the VRAM side. And a descriptor-fetching engine is a **sixth requester** on a
   spare-access budget `plan.md` §14 item 8 has not re-derived for the current
   five.

⛔ **So build `SS.CopyN` first, before pricing any silicon.** It is the biggest
single lever in this document, it costs nothing to fabricate, and it turns the
key from "worth 5.81 ms a sprite" into "worth its engine time" — which is what
decides whether the key is worth a part.

### 7.2 The key, three ways

The compare needs the **source byte**, which already exists on the board: `vread`
latches it on the read access and it leaves through the posted-write `'574`
(§1). What differs is where the comparing happens.

| | CPLD pins | macrocells | packages |
|---|---|---|---|
| key = a **constant** index in `v3ptr` | **8** (the source byte in) | ~2 — an 8-input AND of literals is one product term, and the toolbox already reserves `$0F` as `KEY` | 0 |
| key = a **register** in `v3ptr` | **8** | ~17 — 8 for the register, ~9 for the comparator | 0 |
| ⭐ key compared by a **`74HC688`** on the board, its result gating the write | **1** | ~2 | **+1** |

⭐ **The third is the right shape for this card, and `partition.md` §7.1 is why**:
*"a card whose binding constraint is pins... a `'574` or a `'165` has zero pin
overhead, because its pins ARE its data."* `v3ptr` has ~20 pins spare; spending
8 of them on a byte that is already on the board, to save one discrete package,
is the trade this project has already refused once.

⛔ **And there is a timing rule the cheap versions must obey.**
`timing.check.ts`: a slot is 158.9 ns, an access is 72 ns, and **two accesses fit
with 14.9 ns to spare**. A `'688` is ~20–35 ns. **It cannot sit in series inside
the write access.** The compare has to run during the *read* access and gate the
*write* one an access later — 72 ns apart, which is comfortable, but it makes
this a **pipelined** change rather than a combinational one, and that is exactly
the kind of change that moves cascades.

### 7.3 What to buy, in order

1. ⭐ **`SS.CopyN`** — no silicon, biggest lever, and it makes every later number
   honest. Measure it with `v3cpyb` issuing through the list.
2. **Then price the key against that measurement.** If a copy costs ~60 µs, a
   keyed 16 × 16 sprite is ~120 µs and ten of them are 1.2 ms of a 14.3 ms
   frame — and the key is plainly worth a package.
3. **More hardware sprites** only after — they are the answer to genre C, which
   the key does not serve at all.

⭐ **AND THE KEY WOULD BE A DESIGN-IN, NOT A RETROFIT — which makes it cheaper
than any of the above suggests.** `CDONE`, `CSTEP`, `CROWADV` and `RCPY` are
declared as **inputs** on `v3ptr` (`v3ptr.cpld.ts` §228) and consumed by `v3dot`'s
arbiter (§205), and **nothing in the repository generates them**: the copy
micro-sequencer does not exist yet. Whoever builds it decides where the write
strobe comes from, and a key is one more term on a strobe that is still being
designed — rather than a change to a part that has already fitted at 85% with 3
cascades.

⚠ **What is still missing before any of this is a design**: the copy sequencer
itself; a **re**fit of whichever part gains the compare, read out of the new
`.fit` and compared **against `v3ptr`'s existing 3 cascades and 110 cells**, not
against zero; and the spare-access budget re-derived, which `plan.md` §14 item 8
has owed since before any of this was asked.
