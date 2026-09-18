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

At 4.05 MB/s a 32 × 16 copy is 512 bytes ≈ **126 µs**, twice for save-and-show,
against a CPU that costs ~7.6 µs a byte to write one pixel. ⚠ The comparison
that matters is not against *today's* copy engine — it already moves the
rectangle — it is against **the CPU compositing the figure**, which is what a
key removes. A hand-composed 32 × 16 sprite with 50% coverage is ~256 pixels of
CPU work ≈ 2 ms; keyed, it is the second copy, ≈ 126 µs. **~16× a figure**, and
the CPU is left free rather than merely faster.

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

⛔ **THE CAVEAT, AND IT IS THE WHOLE RISK.** That estimate assumes a copy issued
*inside the toolbox* costs roughly its register writes. The **public** path does
not: an `SS.Copy` through IOMan, ArmIO and CoArm is **milliseconds**, and at
~10 ms a glyph a keyed cache would be *slower than today*. So this only works if
the toolbox reaches the engine directly, and **the in-driver cost has never been
measured**. It is the first thing to measure before anyone designs to this
number — `run-v3text.sh` is the shape of the bench that would do it.

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
