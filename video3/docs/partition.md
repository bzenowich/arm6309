# video3 — the partition

**DRAFT, 2026-09-16.** Which programmable part holds what, derived from
[`signals.md`](signals.md)'s census. This is plan §15 step 4's first half: a partition
comes before term lists, and how many parts video3 takes is an *output* of it.

> ⛔ **NOTHING HERE IS FITTED.** Macrocell counts are bits of state plus an estimate of
> the combinational logic around them; pin counts are read off the census. An
> `ATF1508AS` in PLCC-84 is **128 macrocells and 64 I/O** — that is a datasheet
> property, and it is the only number in this document that is not an estimate.
> ⚠ **No figure from `video/`'s fit applies here** (plan §14 item 4).

---

## 0. The answer, and the thing it runs into

**Four parts**, and `plan.md` §13.5 already measured that **four is the most that places
on a 240 mm board**.

⛔ **So video3 is exactly at its ceiling.** There is no fifth part, which means there is
no room for a feature that needs one — and the partition below has no slack to give a
later change. That is the single most important consequence of this document, and it
should be read before anything is added to plan §0.

| | Cells, est. | I/O, est. | What it is |
|---|---|---|---|
| **`v3dot`** | ~102 / 128 | ~60 / 64 | the raster, the dot path, the sprite, the arbiter |
| **`v3scan`** | ~108 / 128 | ~50 / 64 | the scan and cell addresses, the map word |
| **`v3ptr`** | ~99 / 128 | ~55 / 64 | `WPTR`, `CPTR`, the span writer, the copy engine |
| **`v3host`** | ~24 / 128 | ~45 / 64 | the backplane, the registers, the palette write path |

⚠ **`v3host` is pin-bound, not cell-bound** — a fifth full of macrocells and two thirds
full of pins, because it is the part the backplane lands on. **It is not cells that stop
it merging** — §7 has the arithmetic, and it is pins every time.

> ⚠ **Corrected 2026-09-16**: an earlier draft put `v3host` at ~40 cells by counting
> `PIDX`'s sixteen bits. `PIDX` is **discrete** in `hardware/place/parts.ts` — two
> `'163` and a `'574` — so those bits are not macrocells at all. The conclusion does not
> move, because the constraint was never cells.

---

## 1. What forced the shape

`graphics.md` §10.1.2 is the precedent and the warning: a ten-GAL build spent **52 % of
its pins on the packaging talking to itself**, and the one place merging costs silicon
rather than saving it is the framebuffer address mux — *"on GALs the scan and `WPTR`
pairs tri-state onto a shared bus for free; inside one die two macrocells cannot drive
one pin."*

**`VA[16:0]` has five sources** (plan §14 item 3) and they fall into two clusters:

| | Sources | Lives with |
|---|---|---|
| **scan-side** | the bitmap scan address, the cell/tile concatenation, the map fetch | the scan counters, the cell counters, `TILEBASE`/`MAPBASE` |
| **pointer-side** | `WPTR`, `CPTR` | the span writer and the copy engine |

Putting both clusters in one part costs ~125 macrocells before any control logic — the
scan side alone carries **32 bits of `MAP`/`MAPQ`**, because video3's map is a *word*.

⭐ **So `VA` is a tri-stated bus between `v3scan` and `v3ptr`**, exactly as the GAL build
had it and for the same reason. An `ATF1508AS` macrocell has a product-term output
enable, so this costs no extra silicon — **17 pins on each part, one net each.**

⛔ **And it costs a discipline**: the two parts must never drive `VA` together. The
grant that decides it is one signal from one place (§3), not an agreement between two.

---

## 2. The four parts

### 2.1 `v3dot` — the raster, the dot path, the sprite, the arbiter

| Holds | bits |
|---|---|
| dot counter, line counter | ~20 |
| `M0`, the frame-end family latch | 1 |
| ⭐ **`CTRL`** — `VMODE`, `MODE`, `WMODE`, enables | 8 |
| the sprite: `SPRX`, `SPRY`, `SPRH`, `SPRIDX`, two shift registers, the window counter | ~46 |
| the spare-access arbiter | ~6 |
| **plus** the dot-path control, sync, blanking, the cadence | ~30 combinational |

**Why `CTRL` is here and not on the host part.** Everything reads it and one thing
writes it. Put it where `MODE` and `VMODE` are consumed at dot rate, and export two
bits of `MODE` rather than importing six.

⭐ **Why the arbiter is here.** It has the cadence, and the cadence is the timing
reference. §3 is the whole of it.

⭐ **Why the LUT's three output enables are here.** `PIXOE`, `ATOE` and `PIDXOE` are the
three masters of §1 of `signals.md` §3.1, and `graphics.md` §13.1's discipline is *one
pin doing both halves of the turnaround so the pair can never be half-turned*. With
three masters that becomes **one part deciding all three**, never three parts agreeing.

### 2.2 `v3scan` — the scan and cell addresses

| Holds | bits |
|---|---|
| `HSCROLL`, `VSCROLL` | 19 |
| the scan row and column counters | 19 |
| the cell row (six bits) and cell column counters | 13 |
| ⚠ **`MAP` / `MAPQ`** — the map is a word, so the two-stage pipeline is **32 bits** | 32 |
| `TILEBASE`, `MAPBASE` | 8 |
| the `VA` mux, scan side | 17 |

⚠ **`MAP`/`MAPQ` is a third of this part**, and plan §13.4 already records the
alternative: two `'574` instead, at two packages. **If the fit is short, this is the
first thing to move** — and §13.5 says the board has room for the packages where it has
none for a fifth PLCC.

### 2.3 `v3ptr` — the pointers, the span writer, the copy engine

| Holds | bits |
|---|---|
| `WPTR` | 19 |
| `CPTR` | 19 |
| `CWIDTH`, `CHEIGHT`, `CCTRL` | 22 |
| `SPANLEN`, the mask serialiser, the three-bit mask counter, `WADV` | 21 |
| `SPANBUSY`, `CBUSY`, the span and copy sequencers | ~10 |
| the `VA` mux, pointer side | 17 |

⭐ **The mask serialiser and the register-file address must share a part**, because
`graphics.md` §7.4's trick is that *the serialiser's serial output is the register
file's address bit 0* — which is what makes per-pixel colour selection free. So `RFA`,
`RFWE` and `RFOE` are here.

⭐ **And the column shadows cost nothing here**: `WPTR`'s and `CPTR`'s are register-file
locations, not macrocells (§7.2's trick, and the reason a second pointer is affordable).

### 2.4 `v3host` — the backplane, the registers, the palette

| Holds | bits |
|---|---|
| the register decode, `VSTAT` assembly | ~10 |
| `PPEND`, `PS0`–`PS3` — ⚠ **not `PIDX`, which is discrete** | 5 |
| `RDVALID` and the prefetch | ~4 |
| `/WAIT`, `/IRQ`, the `'245` and `'244` controls | ~5 |

It is **~24 cells and ~45 pins**: the backplane is 27 signals on its own
(`signals.md` §2.1) and the palette path's `'163`/`'574`/`'244`/`'573` controls are seven
more. ⭐ **And it needs no `IDB`** — every register it touches is a discrete latch or
counter that loads from the bus itself, so `v3host` only strobes them.

---

## 3. What crosses between parts

| | pins each | |
|---|---|---|
| `IDB[7:0]` — the card's internal data bus | 8 | every part. The `'245` bridges it to the backplane; the register file, the `'573`s and the posted-write latch sit on it |
| `A4`–`A0` + `REGWR` | 6 | every part decodes **its own** register offsets. ⭐ Cheaper than `v3host` emitting 24 individual strobes |
| `VA[16:0]` | 17 | `v3scan` and `v3ptr`, tri-stated |
| the cadence — `SLOTPH[1:0]`, `FETCH`, `SPARE`, `CELLTICK`, `HLOAD`, `VLOAD`, `ROWADV` | 8 | `v3dot` → `v3scan`, `v3ptr` |
| requests / grants — map, copy, span, prefetch | 4 + 4 | in and out of `v3dot` |
| `MODE[1:0]`, `M0` | 3 | `v3dot` → the others |
| `WMODE[1:0]` | 2 | `v3dot` → `v3ptr` |
| status — `SPANBUSY`, `CBUSY`, `PBUSY` | 3 | → `v3host`, for `VSTAT` and `/WAIT` |
| the palette commit — `PCREQ`, `PCGO` | 2 | `v3host` ↔ `v3dot` |
| ⚠ the sprite shape read — `SPRRD`, `SPRROW[2:0]` | 4 | `v3dot` → `v3ptr` |

### 3.1 ⚠ The sprite shape is the one cross-part read, and it is a cost plan §7 did not price

plan §7 put the shape in the register file *"so the spare-access arbiter, the map latch
and the fetch cadence are all untouched"* — which is true, and it was the right call
against a VRAM-resident shape. **But the register file is `v3ptr`'s and the sprite is
`v3dot`'s**, so once a scanline `v3dot` has to ask for two bytes: `SPRRD` plus three
bits of row, and the byte comes back on `IDB`.

**Four pins on each part, and the timing is relaxed** — the fetch is once per displayed
sprite row and can sit in horizontal blanking. Recorded because it is a real cost of a
choice made before the partition existed, and because the alternatives are worse: the
shape in macrocells is 128 bits, and the shape in VRAM puts `v3dot` on the arbiter *and*
needs `PB[7:0]` on it, which is eight more pins than this.

---

## 4. What was considered and rejected

| | Why not |
|---|---|
| **Three parts** | `v3host` is only ~40 cells, but merging it into either neighbour passes 128. Its pins are the point, not its logic |
| **`VA` owned by one part** | ~125 macrocells before any control logic, and `MAP`/`MAPQ` is 32 of them |
| **`v3host` emitting a write strobe per register** | 24 pins out of the pin-bound part, against 6 into each of three |
| **`CTRL` on `v3host`** | six bits out instead of three; and `MODE` is consumed at dot rate |
| **The sprite on `v3ptr`** | `SPRA[1:0]` drives LUT `A9..A8` and `SPRHIT` needs the dot counter — both are `v3dot`'s |
| **A fifth part for the copy engine** | ⛔ **it does not place** (plan §13.5) |

---

## 5. Risks, in the order they would bite

1. ⛔ **There is no fifth part.** §0. Any later feature needing one is a card revision.
2. ⚠ **`v3scan` at ~108 estimated cells is the tightest — but its escape is now paid
   for.** A third of it is `MAP`/`MAPQ`, and plan §13.4 offers discrete latches instead.
   §8 measured that the board would not take them *and* four CPLDs — until plan §13.3
   trade 1 returned four packages. **It now places at 40 ICs, 73 %.**
3. ⚠ **`v3dot` at ~60 estimated pins is the tightest on I/O**, and the census's cadence
   and grant lines are what fill it. Its escape is also paid for now: the sprite's two
   shift registers as `'165` take **16 cells and 2 pins** off it, and **42 ICs still
   places at 75 %**. If it overflows further, the arbiter is the movable piece — but it
   wants the cadence, so moving it costs the cadence pins instead.
4. ⚠ **The `VA` tri-state discipline.** Two parts on seventeen nets, and the rule that
   they never drive together has to be *checked*, not asserted —
   `graphics.md`'s lesson that **a model which ORs its drivers cannot see a bus fight**
   applies directly.
5. ⚠ **Estimates, not fits.** Every number above except 128 and 64.

---

## 7. ⛔ Three parts does not close, and cells are not why

The macrocell total is **~333 against three parts' 384**, so cells were never the wall.
Every three-way merge fails on something else:

| Merge | Fails on |
|---|---|
| `v3host` into `v3ptr` | **pins.** Their external clusters alone are ~39 and ~38; the merge is ~84 against 64 |
| `v3host` into `v3dot` | **pins** — ~68 |
| `v3host` into `v3scan` | **pins** — ~72 |
| `v3scan` into `v3ptr` — the two `VA` drivers, which would also delete the tri-state | ⛔ **cells: ~207 against 128**, and this is the merge §1 exists to refuse |

⭐ **So the tri-stated `VA` bus is not a workaround for a partition; it *is* the
partition.** Undoing it is the one merge that fails by 60 %.

### 7.1 Why a GAL does not rescue it

| | |
|---|---|
| **A GAL cannot be the `VA` mux** | a 17-bit five-source mux is **85 inputs**; a `GAL22V10` has 22 pins |
| **There is no "tri-state problem" for a part to solve** | the discipline is a **one-hot grant**, and §2.1 puts it in one place for exactly that reason. It is ~6 macrocells, not a package |
| ⛔ **And the repository already measured the direction** | `graphics.md` §14.1: *"+1 × `ATF1508AS`, −3 × `GAL22V10` → **−2**"* — `vsup` absorbed `rfa`, `vlen` and `pxsel`, and **a third PLCC-84 REDUCED the package count**. §10.1.2 says why: *half the pin count is the packaging talking to itself* |
| **The ratio is the argument** | a `GAL22V10` is **10 macrocells for ~22 pins**. On a card whose binding constraint is pins, that is the worst available shape — ⭐ whereas a `'574` or a `'165` has **zero pin overhead**, because its pins *are* its data |

---

## 8. ⭐ What does buy headroom — and what the board charges for it

Two moves take logic out of silicon without adding a pin:

| | Buys | Costs |
|---|---|---|
| **`MAP`/`MAPQ` → 4 × `'574`** | **−32 cells** on `v3scan`, the tightest part. ⭐ And the **attribute half never enters a CPLD at all** — `PB` → `MAPQ` → the `ATTR` latch → the LUT — so `v3scan` loses eight output pins and gains eight input pins for the code half: **pin-neutral** | 4 packages |
| **the sprite's two shift registers → 2 × `'165`** | **−16 cells and −2 pins** on `v3dot`. The serial outputs go straight to LUT `A9..A8`, so they never come back | 2 packages |

⛔ **But the board is full, and `npm run check:place`'s packer says so:**

| | ICs | 240 mm |
|---|---|---|
| 4 CPLD, as drawn | 40 | **places, 73 %** |
| 4 CPLD **+ `MAP`/`MAPQ` discrete** | 44 | ⛔ **does not place** |
| 4 CPLD + `MAP`/`MAPQ` + the sprite shifters | 46 | ⛔ **does not place** |
| 5 CPLD | 41 | ⛔ **does not place** |

⭐ **So relief in silicon has to be paid for in packages, and only plan §13.3's trades
have any to give:**

| | ICs | |
|---|---|---|
| ⛔ ~~minus the `'153` mux~~ (trade 3) | — | **withdrawn** — trade 3 is settled the other way, plan §13.3 |
| 4 CPLD + `MAP`/`MAPQ`, **minus the copy latch** (trade 1: it borrows the fetch rank) | 40 | **places, 73 %** |
| 4 CPLD + both discrete moves, minus the copy latch | 42 | **places, 75 %** |

⭐ **BOTH TRADES ARE SETTLED SINCE 2026-09-16, and the coupling is gone.**

**Trade 3** went the other way — the `'153` mux stays, because the tri-state bus must
break before make and §8.2's second rank doubled the drivers after §6.1 costed four of
them. So it yields nothing.

**Trade 1** was never a sharing question: a `'574` has one output enable and the fetch
rank's is committed to the pixel bus. ⭐ **But the latch is not needed at all** — a
byte-granular copy reuses `vread` and the posted-write `'574` — and that returns **four
packages**:

| | ICs | 240 mm |
|---|---|---|
| 4 CPLD, trade 1 taken | **36** | **places, 68 %** |
| … + `MAP`/`MAPQ` discrete — §5 risk 2's escape | **40** | **places, 73 %** |
| … + the sprite's shift registers — §5 risk 3's escape | **42** | **places, 75 %** |

⭐ **So both of §5's tight parts have an escape that fits**, the package budget no longer
gates the macrocell budget, and the partition has slack it did not have this morning.
What it cost is **4× the copy time** — 30 ms for a 192-row window scroll against 350 ms
without an engine at all.

**Trade 2 is settled too, and the other way**: `HSCROLL` keeps its one-pixel step and its
second fetch rank, because trade 1 already paid for the escapes that rank's four packages
used to be earmarked for. plan §13.3 has the reasoning; ⚠ plan §14 item 13 — **there is no
power budget** — is the only thing that could reopen it.

---

## 6. What to do with it

1. **Term lists per part**, in the shape `hardware/gal/*.jedec.ts` already uses, so
   `emit.ts` can generate Verilog from the same `Cell` lists the fitter compiles.
2. ⭐ **A pin census from the term lists, not from this document** —
   `graphics.md` §10.1.2's `npm run census` is the precedent, and it is what turns §3's
   estimate into a measurement.
3. **A fit, one part at a time** — and `CLAUDE.md`'s trap: *"Design fits successfully"
   appears only in the fitter's stdout, never in the `.fit`*, and a failed fit leaves
   the previous report in place.
4. **`reach` and `census` from the first term list, not retrofitted** (plan §15 step 5).
