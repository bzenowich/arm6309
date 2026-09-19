# video3 — optimisations not taken, and what each is worth

**A backlog, costed. 2026-09-19.** Everything here is *not built*. Each entry says
what it buys (measured where a number exists), what it costs, what could refuse it,
and what would have to be true first. The specs — [`plan.md`](docs/plan.md),
[`partition.md`](docs/partition.md), [`keyed-copy.md`](docs/keyed-copy.md) — describe
the card as it is; this file is the queue beside them.

⚠ **A number here is either measured or marked as arithmetic.** The study this file
grew out of had three figures corrected by measurement, each of which had reversed a
recommendation (`keyed-copy.md` §7.1), so an estimate that reads like a measurement is
the specific mistake to avoid.

## The state the queue starts from

| part | cells | I/O | cascades |
|---|---|---|---|
| `v3dot` | 121/128 | 63/64 | 5 |
| `v3scan` | 112/128 | 63/64 | 3 |
| `v3ptr` | 124/128 | 58/64 | 3 |
| `v3host` | 58/128 | 64/64 | 0 |
| `v3lane` (GAL22V10) | 10/10 macrocells | 10 inputs | — |

⛔ **`v3ptr` is where most of this queue lands, and it is the part that refuses.**
Seven of its eight logic blocks sit at 39 of the fitter's 40 inputs and Nodes+FB is
132 %: it answers `INTERNAL ERROR` on grouping long before it runs out of cells. Three
additions were refused there in one session; each was landed only by taking something
else out. **Every entry below that touches it needs a fit before it is a plan**, and
CLAUDE.md's ninth trap applies — a refusal is not a result until a second file name
refuses it too.

⛔ **And the board is full**: 44 ICs, placing on 24 cm, which `plan.md` §13.5 says is
the longest board there is. A new package has to displace one.

---

## 1. ⭐ The copy-side step — halve a character-mode scroll

**What it buys.** A console scroll copies map rows, and a four-byte cell makes a row
320 bytes where a two-byte cell made it 160. Stepping BOTH copy pointers by two would
move only lanes 0 and 2 — the code and the attribute — and skip the unused lanes:

| | bytes a row | engine time, 59 rows | measured per scrolled line |
|---|---|---|---|
| now | 320 | 4.66 ms | **10.70 ms** |
| stepped by two | 160 | 2.33 ms | ~8.9 ms *(arithmetic)* |

That is the whole of the four-byte cell's scroll regression (`plan.md` §12), and it
would speed up any full-map copy the same way.

**What it costs.** `CCOL` (the copy's source column) needs `stepTerms`, as `WCOL` has
it — one more product term on each of ten bits — and `WCOL`'s step has to take the
copy's step as well as `WADV` b2. `CWIDTH` changes meaning to *bytes moved*, so the
driver halves it for a map copy. A mode bit: `CCTRL` b6 is free.

**What could refuse it.** `v3ptr`, on grouping. This is the largest of the three
`v3ptr` entries here and the most likely to be refused.

**First.** A fit. Then `v3card_tb` needs a copy claim in the mode, and the emulator and
`vidcpy3`/`ca_v3txt` follow.

## 2. ⭐ Retire-only qualification for `WADV` b2 — the last 5 µs, and a hazard gone

**What it buys.** Measured, same method through `run-v3text.sh`:

| | µs a character |
|---|---|
| before the four-byte cell | 99.45 |
| four writes a cell | 108.15 |
| `WADV` b2, as built | **104.38** |
| with this | ~99.5 *(arithmetic: 11 E cycles a chunk)* |

The residual is the driver setting and clearing b2 around each stream chunk, because
the step applies to *every* advance of `WPTR` — a copy's write and a `VDATA` read's
post-increment included — so it cannot be left set. Qualify the step with "this
advance is a retire" and the driver sets b2 once when it selects the text screen.
⭐ **It also removes the hazard**: with it, a copy started while b2 is set behaves.

**What it costs.** One literal in the step's terms (`WADV2 & !WSTEP`), which doubles
the two terms per bit that carry `!STEP2` — about one more term on each of ten bits.

**What could refuse it.** `v3ptr`, again on grouping.

**⚠ The software alternative is closed.** Folding b2 into the driver's cached `WADV`
would cost nothing in silicon, and CoArm is at **exactly** its 16,384-byte limit with
no room for the three bytes it needs.

## 3. ⭐ CLOSED 2026-09-19 — the sprite-mode claim

`WMODE 11` (sprite) retires a transparent pixel without writing: it is how software
draws a 1-bit-transparent actor at 8 pixels a write, and it is what a keyed copy would
be measured against. The term was in `v3ptr`'s `VWE` and in the model with **no bench
claim on it** — `v3card_tb` ran direct, mask and solid. It has three now, over a
background that is neither `WFG` nor `WBG`: the ink lands, the transparent pixels
leave the background standing, and the pointer still advances over them.

## 4. ⭐ CLOSED 2026-09-19 — the copy's per-copy overhead, and it was the whole answer

Measured (host emulator, `v3cpyb` through `SS.CopyN`, per-copy from the slope of two
call counts so the typing and the fork cancel):

| | before | after |
|---|---|---|
| a copy, 204 B | 698 µs | **344 µs** |
| a copy, 256 B — a 16 × 16 sprite | 708 µs | **349 µs** |
| a copy, 20,000 B | 5,708 µs | 5,125 µs |
| ⭐ ten sprites, 20 copies | 14.17 ms | ⭐ **6.98 ms** of a 14.3 ms frame |

The driver's cost is **size-independent** now, and ~180 µs of the engine's own time
overlaps the next rectangle's set-up, so **a copy under ~728 bytes retires for free**.
What went: the `SPANBUSY` poll before each register group (`/WAIT` holds a register
write under a span or a copy by itself), the block copy into `VG.CpBlk`, the `VG.CpA`
round trip — the column's low byte **is** the address's low byte, an OR and not an add
— and `CpOver` where the destination precedes the source. `armio.dr` shrank 92 bytes.

**What is left, and it is outside the driver**: `F$Move` for the caller's table
(65 µs a rectangle) and the IOMan/`SetStt` floor (~42 µs).

⚠ **A gate this left open**: the staged path (`CpOne`, overlapping copies) has no
pixel-comparing check — `run-v3copyn.sh` never overlaps — and waits moved inside it.

**A hardware descriptor walker** is what remains of this entry: cells on `v3host` (70
spare) and **no pins there** (64/64). ⚠ Its case is weaker now — the win is
concurrency and a persistent list, not the register writes, and ten sprites already
fit in half a frame.

## 5. The colour key — fourth, and cheap when it arrives

[`keyed-copy.md`](docs/keyed-copy.md) §7.2 prices it three ways; the `74HC688` version
is **one pin into `v3ptr` and one literal on `VWE`**, plus a package the board has to
find. ⚠ §7.2's timing rule: the compare cannot sit in series inside the 72 ns write
access — it runs during the read access and gates the write one access later, which
makes it a pipelined change. ⛔ It was worth nothing while a copy cost 788 µs; at **344 µs** (entry 4) that
objection is gone, and this is now the front of the hardware queue — ⚠ behind a fit
of `v3ptr`, which is where it lands.

## 6. More hardware sprites

The card has one 16 × 16 sprite and the pointer is usually it. §6.3's genre C (a
Mario-like) wants sprites rather than copies; each further sprite is its own position
registers, window counters and shape fetch on `v3dot` — **121/128 cells and one spare
pin**, so it is a partition change and not an addition.

## 7. Smaller things

| | |
|---|---|
| `TFM` for cell runs | The 6309's block move would stream a run to `VDATA` at 3 cycles a byte. ⛔ `software/demo/emu/cpu6809.c` has no 6309 opcodes, so it cannot even be tried on the emulator yet |
| `SS.Batch`'s tile puts | `BT.Put`'s raw byte runs go out with `WADV` forced to 00, so `overworld`'s tile writes still cost four bytes a cell where `SS.MapWr` costs two. The record has nowhere to ask for the step |
| `v3scan_mq` | The variant with the map latches discrete is fitted against a design two changes old. Either refit it or retire it |
| `v3machine_tb` | video3 has no whole-machine bench. `plan.md` §15's ladder puts it last, and it is what `SCENARIOS=nitros9` is for the other card |
| the span writer's "25.1 MB/s broadcast" | `plan.md` §5 inherits the figure from `video/`, where a write reached four lanes at once. On this card `v3lane` enables one lane a write. The figure needs re-deriving |
