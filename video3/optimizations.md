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

## 5. ⭐ CLOSED 2026-09-19 — the colour key

Built: an 8-input NOR (`74HC4078`, +1 IC — 45, and it still places on 24 cm) on the
card's internal bus, `v3lane`'s byte enables dropping for a keyed write, armed by
`WMODE` 11, keyed on index 0. A full-colour transparent blit at ~349 µs a 16 × 16
sprite, where software costs a pass a colour.

⛔ **Not where this queue said it would land.** `v3ptr` refused it twice — with a
`CCTRL` enable bit, and then with `WMODE` arming it and no new cell at all — and the
packer refused the `74HC688` that a *programmable* key needs, which is why the key is
fixed. [`keyed-copy.md`](docs/keyed-copy.md) §0 has the three corrections.

## 6. More hardware sprites

The card has one 16 × 16 sprite and the pointer is usually it. §6.3's genre C (a
Mario-like) wants sprites rather than copies; each further sprite is its own position
registers, window counters and shape fetch on `v3dot` — **121/128 cells and one spare
pin**, so it is a partition change and not an addition.

## 7. ⭐ "Mayhem in Monsterland" — and §7.1, which is the way in

**Asked 2026-09-19: are the features there to recreate it?** Partly, as written here —
and then ⭐ **§7.1 removed the blocker**: a bitmap playfield built out of blitted
blocks is as long as DRAM allows, so read that section with this one. The genre study
(`keyed-copy.md` §6.3, written before the copy came down to 344 µs and before the key
existed) called this genre C and said the key does not serve it. That is still true,
but for a different reason than it gave.

**What the card has now**, measured rather than argued:

| | |
|---|---|
| 256 simultaneous colours, a byte a pixel | plan §3 — the thing the other card cannot do at all |
| a playfield that scrolls for one register write, both axes, with ring wrap | plan §8.1, pixel-exact in `v3card_tb` at every fine phase |
| ⭐ **19 full-colour actors a frame** in bitmap mode | `run-v3mv.sh`, keyed blits interleaved with their restores, 0.467 ms an actor of a 14.3 ms frame. It was 18 until `SS.Scroll` took 0.77 ms of the frame back (entry 9); **21** if the game commits its own scroll in the blank |
| tile mode for long levels: a map cell is a byte, and an **animated tile is one write that changes every instance** | plan §2.4 |
| a copy at 4.05 MB/s, 183 µs a rectangle through the card's registers | `optimizations.md` 4 |

⛔ **THE TWO THINGS MISSING, and they are the same thing twice.**

1. **The playfield and the actors want different modes.** Monsterland's levels are
   long, which is tile mode's case: the map is small, tiles repeat, and the scroll is
   free. Its *look* is big smooth multi-colour sprites, which is bitmap mode's case:
   the keyed blit and the one hardware sprite are **bitmap only**. In tile mode there
   is no per-pixel actor path at all — an actor would have to be composed into the map
   on an 8-pixel grid, or into the tile bank, where it changes every instance of that
   tile.
   ⚠ **And a bitmap level cannot be long.** The art has to live in VRAM (512 KB, and
   the ring is 1024 × 512): about four 640 × 200 screens. Refilling a 16-pixel column
   from VRAM is one copy, ~1 ms a frame — affordable — but refilling it from DRAM is
   7.63 µs a byte, **24 ms a column**. So bitmap means rooms, which is why the
   Metroidvania fits and this does not.
2. **One sprite, and it is bitmap's.** §6.3's own conclusion — *"what a Mario-like
   needs is not a keyed copy but MORE HARDWARE SPRITES"* — stands.

⭐ **The cheapest route, in order:**

| | what it costs |
|---|---|
| **the sprite in TILE mode** | three gates, not a redesign: `v3dot`'s `SPRACT` and `SPRLD` each carry `!MODE1 & !MODE0`, and `v3scan`'s address mux picks the shape source on the same pair. ⚠ The real work is that in tile mode a map access and a sprite access are both `GMAP`, so `v3scan` needs to tell them apart — a discriminator pin on two parts that are 63/64 and 63/64. `SPRAOE` already allows tile mode |
| **more sprites** | each is its own position registers, window counters and shape fetch on `v3dot` — **121/128 cells, one spare pin**. A partition change |
| tile-mode actors on the 8-pixel grid | free, and it is what `overworld` already does — but it is not Monsterland's look |
| parallax | ⛔ there is no display list (plan §0), so per-band `HSCROLL` is CPU chased against `VSTAT` |

### 7.1 ⭐⭐ AND THE BLOCKER DISSOLVES: build the world out of BLOCKS, in bitmap mode

**Asked 2026-09-19: can the world be built from ~32 different 16 × 16 sprites blitted
onto a bitmap playfield? Yes — and it is the answer to (1).** Tile mode's advantage
was never the tiles, it was that a *map* is small where a *bitmap* is large. Blitting
blocks buys the same thing without leaving bitmap mode, so the hardware sprite, the
keyed blits and 256 colours all stay:

| | |
|---|---|
| the bank | 32 blocks × 256 bytes = **8 KB** of VRAM |
| the level | one byte a block: 13 rows × 512 columns = **6.5 KB in DRAM** — 8,192 pixels, thirteen screens, and nothing says stop there |
| ⭐ the refill | the ring is 1024 wide and the view is 640, so an incoming column is written **384 pixels ahead of the view**, off-screen, and `HSCROLL` streams the level through it |

**What the refill costs a frame** (183 µs a copy through the card's registers, plus
0.247 µs a byte, both measured):

| scroll | a column every | 13 blocks of 16 × 16 | one 16 × 208 strip |
|---|---|---|---|
| 2 px a frame | 8 frames | 0.40 ms | 0.13 ms |
| 4 px | 4 frames | 0.80 ms | 0.25 ms |
| 8 px | 2 frames | 1.60 ms | 0.50 ms |
| 16 px | every frame | 3.20 ms | 1.01 ms |

⚠ **Prefer TALLER blocks than 16 × 16.** A copy is 183 µs of fixed cost against 63 µs
of data for a 256-byte block — **three quarters of the work is per-rectangle** — so a
column costs 3.20 ms as thirteen blocks, 1.74 ms as four 16 × 64 strips and 1.01 ms
as one full-height strip. 16 × 16 is the unit the *art* is drawn in; the unit the
*engine* wants is a vertical run of them, composed in the bank. A mixed bank — full
columns for the common ground and sky, blocks for detail — is the cheap shape.

⚠ **No clean page** (the ring holds the streamed world), so actors are save-behind:
three copies each rather than two, ~0.74 ms for a 16 × 16.

**So the verdict changes.** With software blocks the level is as long as DRAM allows,
the player is the hardware sprite, the cast is keyed blits at 18–19 a frame, and none
of it needs tile mode — which means **neither the sprite-in-tile-mode work nor more
hardware sprites is on the path any more**. What is left is art and a frame budget:
~1 ms of refill at a 4 px scroll, ~7 ms of actors, the rest for the game.

**So the honest answer**: a Monsterland-style game is reachable in bitmap mode today.
The tile-mode route above stays costed because it is cheaper per frame if a game wants
8-pixel-grid actors and no per-pixel cast — but it is no longer the way in.

## 8. ⛔ The per-frame OS call — 1.05 ms of every frame, and it is not the card's

**CLOSED IN PART 2026-09-19, and what is left is NitrOS-9's.** `mvania`'s scroll
went through `SS.Batch` at **1.90 ms a frame** — 13% of a 14.3 ms frame for four
register writes and two tags, bigger than every actor restore put together. The
marks said where, and only 0.93 ms of it was anything a driver does:
`FromCallerX`'s `F$Move` 486 µs, validating the records 160 µs, building them
106 µs, the `VG.BtOn` handshake 73 µs, the `F$Sleep` on a pending batch **0**.
`SS.Scroll` ($D5), specified in `defs/arm6309.d` since P1 and implemented
nowhere, takes all of that out: **1.13 ms**.

**What is left is 1.05 ms of IOMan, SCF and the kernel** — 654 µs in, 392 µs out
— for a call that hands the driver twenty bits. That is 7.3% of a frame, it is
paid by *every* per-frame driver call on this machine, and no card change
touches it.

| the same commit, four ways | ms a frame | most actors that fit | tears? |
|---|---|---|---|
| `SS.Batch`, four `BT.Reg` + `BT.Tags` | 1.90 | 18 | no |
| ⭐ `SS.Scroll`, the registers | **1.13** | **19** | no |
| the exclusive owner writing the card in the blank it already waited for | **0.04** | **21** | no — `VSTAT` b6 is read back first |
| the exclusive owner writing the card wherever the raster is | 0.043 | — | ⛔ **yes**, 616 writes of 630 in the picture |

**What it would take to go further.** Either an IOMan/SCF fast path for a
status call that passes only registers — a kernel change, and the wrong tree —
or the third row, which is a *game engine* technique and not a driver one:
the frame poll returns twelve lines into a forty-nine-line blank, so an
exclusive owner has ~1.1 ms of blank it has already paid for. `mvania` mode b8
does it and misses the blank **0 times in 495 frames** at any actor count that
fits the budget (and declines the write, rather than tearing, when it does not).
⚠ It cannot carry the recording tags — `VG.MkCam` and `VG.MkHero` are in the
system map — so it is a measurement mode until a game needs no tags.

## 9. Smaller things

| | |
|---|---|
| `TFM` for cell runs | The 6309's block move would stream a run to `VDATA` at 3 cycles a byte. ⛔ `software/demo/emu/cpu6809.c` has no 6309 opcodes, so it cannot even be tried on the emulator yet |
| `SS.Batch`'s tile puts | `BT.Put`'s raw byte runs go out with `WADV` forced to 00, so `overworld`'s tile writes still cost four bytes a cell where `SS.MapWr` costs two. The record has nowhere to ask for the step |
| `v3scan_mq` | The variant with the map latches discrete is fitted against a design two changes old. Either refit it or retire it |
| `v3machine_tb` | video3 has no whole-machine bench. `plan.md` §15's ladder puts it last, and it is what `SCENARIOS=nitros9` is for the other card |
| the span writer's "25.1 MB/s broadcast" | `plan.md` §5 inherits the figure from `video/`, where a write reached four lanes at once. On this card `v3lane` enables one lane a write. The figure needs re-deriving |

---

## 10. ⭐ Epic Pinball — the best fit of the genres costed so far

**Asked 2026-09-19.** Better than Monsterland, because what a pinball table needs is
exactly what this card gives away free.

| | |
|---|---|
| the table | 640 × 512 is **327 KB of 512 KB** — 2.5 screens tall, which is an Epic Pinball table |
| ⭐ the scroll | `VSCROLL` is 9 bits and the ring is 512 rows, so following the ball is **one register write a frame**, no refill, and 0.04 ms in the blank the frame already waits for |
| the cast | a ball, two flippers, bumpers: **eight actors** against the 19 measured |
| ⭐ lamps and flashers | **palette writes, not blits** — one LUT entry changes every pixel of that colour at once. A flashing table costs registers, not bandwidth |
| the music | the audio card plays ProTracker modules, which is half of what anyone remembers about it |

⛔ **THE ONE THING THAT DOES NOT WORK: a fixed score panel under a scrolling
playfield.** `VSCROLL` is latched **in vertical blanking** (plan §8.1 — `v3scan` loads
the row counter from it only while `VBLANK`), so it cannot change mid-frame and there
is no vertical split. `HSCROLL` *can* change per line, and the machine has a
raster-compare timer — but it is in the CPU module, clocked from `HSYNC`
(`graphics.md` §12.2), and no interrupt can move a register the card samples once a
frame. The choices are: put the score inside the playfield and let it scroll, scroll
in discrete steps, or copy a panel strip each frame — 640 × 32 is 20 KB, **~5 ms of a
14.3 ms frame**, which is not affordable.

⚠ **Two smaller shapes.** There is no 320-wide mode, so art is authored at 640 or
drawn double-wide (a ball becomes 32 × 16 — the budget absorbs it). And a 327 KB table
leaves no room for a clean page, so actors are **save-behind**, three copies each;
flippers sit still, so they should be **pre-composed over their background** and
blitted opaquely only when the animation frame changes.

**A frame, at 70 Hz:** scroll 0.04 ms, the ball 0.74, two animating flippers ~1.1,
lamps nothing — **~12 ms left for physics and table logic**, which is where the real
question is: sub-stepped collision on a 6309 in native mode, with its 16 × 16 multiply
and divide.
