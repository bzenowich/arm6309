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

⛔ **And the board is full**: 45 ICs, placing on 24 cm, which `plan.md` §13.5 says is
the longest board there is. A new package has to displace one.

---

## ⭐ The priority list, 2026-09-19

Ordered by measured value against measured cost, not by how interesting it is.

| | | what it is worth |
|---|---|---|
| 1 | ⭐ **A game that owns the screen should not call the OS per frame** (§8) — **BUILT 2026-09-20** | `monster` does it as its normal path, not as a mode: **0.042 ms against `SS.Scroll`'s 1.14**, 19 → 21 actors, measured again on a second scene. ⚠ What is left is a supported pattern in `libvid`, and §8's *recording tag* objection is answered — see there |
| 2 | ⭐ **The block-streaming playfield** (§7.1) — **BUILT 2026-09-20** | `monster` streams a **10,240-pixel** level through the ring for **0.35 ms a frame** at a 4 px scroll, in bitmap mode with the sprite and the keyed blits, and **18 actors** still fit. §7.1's numbers held; two of them moved, and one of them by 2× |
| 3 | ⭐ **The demo's art: 256 colours, Floyd–Steinberg, a cast of different sprites** — **BUILT 2026-09-20** | `video3/bench/mkmonster.py`: a palette median-cut out of the art, **snapped to the LUT's 5/6/5 grid before the dither**, Floyd–Steinberg against it, and eight different creatures as full-colour keyed blits. The contact sheets are what it is reviewed from |
| 4 | ⭐ **Epic Pinball, and the LUT as a feature** (§10) — **BUILT 2026-09-20, and the table became a FILE 2026-09-21** | `pinball`: a 640 × 512 table, `VSCROLL` following the ball for **0.032 ms** a frame, the ball on the hardware sprite, and ⭐ **the lamps and a six-digit scoreboard as PALETTE writes** — 0.30 ms a frame of register traffic and no copy-engine time at all. §10's plan held; what it got wrong is in §10.1, and ⭐ **§10.2 is the playfield read off the SD card**: 327,680 bytes in 11.1 s, with art and collision as separate data |
| 5 | **The copy-side step** (§1) | halves a character-mode scroll, 10.70 → ~8.9 ms a line. ⚠ `v3ptr` may refuse |
| 6 | **Retire-only `WADV` b2** (§2) | ~5 µs a character and the mode stops being a hazard. ⚠ `v3ptr` may refuse |
| 7 | ⭐ **`v3machine_tb`** — **BUILT 2026-09-19** | `machine3.v` puts a real 6809E, the motherboard and the card together and runs a ROM. **It found a card defect on its first run** (the palette commit firing twice outside vertical blanking), which is the same return the other card's machine bench gave. 48 claims, ~40 s, now in `check:video` |
| 8 | **A pixel gate for the staged copy path** (§4) | `CpOne` (overlapping copies) has no check that compares pixels, and waits moved inside it |
| 9 | ⭐ **Run the blits first and the game afterwards** (§11) — **BUILT 2026-09-22** | `zelda`'s actor tear, **25 % of actor-frames → 2.5 %**, for a reordering of `Body` and a sort. ⛔ The ordering alone bought a third of it; the other two thirds was that the pass did not START at the blank |
| 9a | ⭐⭐ **A ROOM, so the actor count is data** (§11.1) — **BUILT 2026-09-22** | the last 2.5 % and the 17-second loading screen with it. A scene that lets the player roam cannot bound what it has to draw; one that freezes, slides and re-places can, and the budget becomes a derivation against the top wall's thickness |
| 10 | more hardware sprites (§6), a programmable key (§5) | ⛔ both blocked by pins and board space, and §7.1 removed the reason to want the first |

---

## 0. ⛔ Tile mode costs ONE macrocell — measured, so it is not where the room is

**Asked 2026-09-19: would dropping tile mode free resources?** It would free **one
cell**. Both parts were rebuilt with tile mode's terms removed and refitted:

| part | as built | rebuilt without tile mode | what the mode costs |
|---|---|---|---|
| `v3dot` | 121/128 cells, 63/64 I/O, 5 cascades | one cell fewer, same pins, same cascades | ⭐ **one macrocell** — `HSCROLL[2]`, the cell phase |
| `v3scan` | 112/128 cells, 63/64 I/O, 3 cascades | **identical in all three** | ⭐ **nothing** |

⚠ Both counterfactuals fitted ("Design fits successfully"), under their own names, so
the comparison is the fitter's and not an estimate. The experiment was reverted.

⭐ **It is a thin layer on character mode, and the layer is the cheap part.** The
expensive machinery — the map fetch and its request cadence, the two-stage code
pipeline, the map column counter, `MAPBASE`/`TILEBASE`, the address concatenation — is
**shared with character mode**, which stays either way. What tile mode adds on top is
`HSCROLL[2]`'s phase (character mode has no scroll) and a few product terms in the
address mux that the fitter absorbs. Retiring the mode would also free the `MODE1` pin
on two parts, and break `overworld` and `ca_tile`.

⛔ **And it frees the wrong part.** The queue's two hardware entries (§1, §2) are on
**`v3ptr`, which has no tile logic at all**, and a second hardware sprite is ~46 cells
and four pins on `v3dot`, which has seven and one. One macrocell buys none of that.

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

**What the refill costs a frame** *(arithmetic, 2026-09-19: 183 µs a copy through
the card's registers plus 0.247 µs a byte. ⚠ The per-copy figure came down to ~87 µs
when it was measured on this path — see "BUILT", below)*:

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

### 7.1.1 ⭐ BUILT 2026-09-20 — `monster`, and the three numbers above that moved

`video3/bench/run-v3mon.sh` runs it; `bench/README.md` has the whole account. A
10,240-pixel level, a 640 × 200 view, a hero on the hardware sprite and eight
different creatures as keyed blits, for fifteen seconds at 70 Hz. **Everything §7.1
predicted worked.** Three of its numbers are now measured rather than argued, and two
of them moved:

| | §7.1 said | measured |
|---|---|---|
| the refill, 2 px a frame | 0.13 ms *(one 16 × 208 strip)* | **0.18 ms** *(three rectangles, 4,608 B: two bands live and one clean)* |
| … 4 px | 0.25 | **0.35** |
| … 8 px | 0.50 | **0.65** |
| ⭐ a copy's fixed cost, from the card's own registers | **183 µs** | ⭐ **~87 µs** — a column is three rectangles and 4,608 bytes and costs **~1.4 ms**, where 3 × 183 + 4,608 × 0.247 is 1.69 |
| ⭐ actors with no clean page | "save-behind: three copies each, ~0.74 ms" | ⛔ **do not do that.** Refilling the BOT band **twice** — once live, once into a clean copy — costs *one more rectangle a column*, which at 4 px is a copy every four frames, and buys every actor back its second copy. **0.53 ms an actor**, and 18 of them fit |

⚠ **And the clean copy is what makes the correctness gate possible at all**, which is
worth more than the 0.2 ms: every byte of the playfield is then decided by the level
map, and `checkv3mon.py` rebuilds all 512 ring rows from the same JSON the ROM's
tables were generated from.

⛔ **THE GEOMETRY IS THE BINDING CONSTRAINT, not the frame budget.** All 512 ring rows
are spoken for — 208 live playfield, 208 strip bank, 96 clean copy — and the clean
copy has to cover every row an actor can occupy. So the cast flies in the bottom 80
pixels and the top 104 hold scenery only. A second hardware sprite would buy exactly
what that costs; §6's entry is not as dead as §7.1 left it.

⚠ **The 16 × 16 block is still the right ART unit and the wrong ENGINE unit**, exactly
as §7.1 says. `monster` keeps both: 88 blocks of 16 × 16 in the module, **composed
into tall strips in VRAM by the copy engine at start-up** (483 copies, about 0.2 s,
once), and the refill then moves two strips and not thirteen blocks.

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

### 8.1 ⭐ CLOSED 2026-09-20 — the tag objection, and what the blank really leaves

**The recording tags are not a reason to keep the OS call.** `monster`
(§7.1.1) sends the camera and the actor count **as `$FF2E` marks** and
`video3/bench/checkv3mon.py` joins `marks.txt` to `frames.bin` on the
**timestamp** — both files carry picoseconds off the same clock. A tag costs
twelve E cycles instead of a system call, and the scene makes **no OS call at
all** between its first frame and its last. The in-blank write is measured
again on it at **0.042 ms** against `SS.Scroll`'s **1.14** (0.018 + 1.121), so
the 1.09 ms is this table's figure confirmed on a second scene.

⛔ **AND ONE NUMBER IN THIS SECTION WAS WRONG.** *"The frame poll returns
twelve lines into a forty-nine-line blank, so an exclusive owner has ~1.1 ms of
blank it has already paid for"* is a derivation from where the **interrupt**
arrives. `VR.FCnt` is written much later in the VBL service, and the CPU
therefore sees it later still:

| | |
|---|---|
| the blank | 1,558 µs (49 lines) |
| ⭐ where the frame poll really returns | **1,186 µs into it** (1,083–1,206 over 1,050 frames) |
| ⭐ what is left | **353 µs**, not 1,100 |

That is 70× what the four scroll stores need, so the conclusion is unchanged —
but it is **not** room for arbitrary blank-time work. `monster`'s 64-byte
sprite-shape upload is ~0.3 ms and would not reliably fit; it runs there anyway
and is deliberately *outside* the tearing gate, because the raster does not
read the shape until the sprite's own rows, about 240 scanlines in.

⚠ **The guard is check-then-write and it has a window.** `VSTAT` b6 says "still
blanked", not "there are N µs left", so a blank that ends inside the four
stores is written into the picture. In 2,100 frames of a sweep that runs the
scene past its budget on purpose it happened **once, 22.9 µs late**; at every
actor count the frame can afford it never happens, and a frame that finds the
blank already gone **declines** — 721 declines in that sweep, every one of them
after a frame that had already overrun.

## 9. Smaller things

| | |
|---|---|
| `TFM` for cell runs | The 6309's block move would stream a run to `VDATA` at 3 cycles a byte. ⛔ `software/demo/emu/cpu6809.c` has no 6309 opcodes, so it cannot even be tried on the emulator yet |
| `SS.Batch`'s tile puts | `BT.Put`'s raw byte runs go out with `WADV` forced to 00, so `overworld`'s tile writes still cost four bytes a cell where `SS.MapWr` costs two. The record has nowhere to ask for the step |
| `v3scan_mq` | The variant with the map latches discrete is fitted against a design two changes old. Either refit it or retire it |
| `v3machine_tb` **with the other cards** | ⭐ the bench exists (`machine3.v`), but with **no audio card and no UART**: plan §15.2's "two cards, one backplane" and NitrOS-9's tick on the VBL are still unasked |
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

### 10.1 ⭐ BUILT 2026-09-20 — `pinball`, and the four things §10 got wrong

`video3/bench/run-v3pin.sh` runs it and `bench/README.md` has the whole
account. A 640 × 512 table, `VSCROLL` following a scripted ball, the ball on
the hardware sprite, extra balls as keyed blits with save-behind, flippers
pre-composed over their own background, and ⭐ **eight lamps and a six-digit
seven-segment score as palette entries**. Fifteen seconds at 70 Hz, three
balls, and the table scores 65,440.

**§10's shape is right and its headline is confirmed**: the scroll is one
register pair in the blank at **0.032 ms**, the fixed score panel really is
impossible and the scoreboard really does belong in the playfield, and the
lamps really do cost the copy engine nothing. Four of its numbers moved:

| | §10 said | measured |
|---|---|---|
| a frame, at the scene's own cast | scroll 0.04 + ball 0.74 + flippers ~1.1 | 0.032 + **1.97 for two blit balls** + **0.62** for both flippers |
| ⭐ **lamps and flashers** | "nothing" | ⭐ **0.16 ms a frame** of LUT writes, and **0.70** with the bookkeeping that decides what changed. Still free of the copy engine, which is the claim that mattered |
| ⭐ **the physics** | "~12 ms left … sub-stepped collision on a 6309 in native mode, with its 16 × 16 multiply and divide" | ⛔ **there is no 6309 to use**: `software/demo/emu/cpu6809.c` has no 6309 opcodes (§9), so the scene is plain 6809. It does not need them — **1.63 ms a frame** for three balls on a 16-pixel collision grid whose cell index is the coordinate's HIGH BYTE. 9.7 ms is left, not 12 |
| ⭐ **save-behind** | "a 327 KB table leaves no room for a clean page, so actors are save-behind" | right, and for a second reason §10 did not have: a *scrolling* clean band — `monster`'s actual shape — would cost **1.35 ms a frame** here, because the camera is driven by the ball and moves up to eight rows a frame. And save-behind costs the **interleave** as well as the third copy: restores, saves and draws have to be three separate phases |
| the cast | "a ball, two flippers, bumpers: eight actors against the 19 measured" | ⭐ **9 balls** — 1.674 ms of frame + **1.459 ms a blit ball**, and the sprite ball is free. Fewer than eight *actors* only because a pinball ball costs three copies and 0.5 ms of physics where a `monster` creature costs two copies and no logic |

⭐ **And one thing §10 could not have known: the table cannot be a MODULE.**
327,680 bytes is five times the address space a NitrOS-9 module may occupy.
The first build answered that by interning the table — 40 × 32 cells of
16 × 16 **by content**, `monster`'s technique without the strips — and paid
for it in the art. §10.2 is the answer that removes the constraint instead of
working inside it.

### 10.2 ⭐ BUILT 2026-09-21 — the table is a FILE, and art and collision separate

The machine has storage (`storage/docs/sdcard.md` §9.4) and the demos and
their data are on a card, so the constraint §10.1 worked inside is gone.
`video3/bench/mkpcb.py` draws the playfield as a **picture** — a 1984 circuit
board, 640 × 512, one palette index a pixel, **327,680 bytes, exactly 640 SD
blocks** — and `pinball` reads it off `/SD0/DATA` straight into VRAM rows
0–511. Nothing is interned and nothing is composed.

| | interned blocks (2026-09-20) | the file (2026-09-21) |
|---|---|---|
| the table in the module | 61 blocks = **15,616 B**, plus a 1,280-byte block map | **none** |
| what puts it in VRAM | **1,280 copy-engine rectangles**, about half a second | **512 `VDATA` runs** of 640 bytes, fed by 64 `I$Read`s |
| what it costs | nothing but the art | ⭐ **11.1 s at 28.9 KiB/s**, and a loading screen that is period-correct rather than hidden |
| what the art may be | three *flat* zones, so an overlay costs one block wherever it sits | **anything**: continuous tone, dithered into 205 entries, 223 distinct indices in the finished picture |
| the collision map | derived from the same grid that chose the blocks | ⭐ **a separate 40 × 32 grid** (`colmap` + `idmap`, 2,560 B of module data) that `mkpcb.py` derives from the object rectangles and `checkpcb.py` asserts against the *pixels* |

⭐ **The separation is the point, and it changes what can be checked.** When
one grid decided both, "the art cannot disagree with the physics" was true by
construction and therefore untestable. Now the picture is a picture and the
grid is data: `checkpcb.py` classifies the *pixels* through the palette and
asks whether every bumper cell has an IC under it, every drain cell a milled
slot, and no open cell a wall — 299 claims and eleven mutations. And the
scene marks the **collision kind** of every hit at `$FF2E`, so `checkv3pin.py`
requires every kind the grid carries to have been met by a ball. ⛔ A table
whose art is perfect and whose grid never arrived paints, scrolls, keeps its
budget and passes the VRAM gate; those two claims are what see it.

⭐ **And the VRAM gate got stronger by getting shorter.** It used to rebuild
512 KB out of `pinball.json`'s bank, map and composition rules. The expected
VRAM now *is* `pcbtable.pic`, byte for byte, plus the flipper frames composed
out of it — so the gate compares the machine against **the same file the card
carries**, and the two new mutations (`m256` loads it one VRAM row low,
`m512` truncates it at ring row 448) are the ones that say it can fail.

⛔ **THE DEFECT THIS SCENE EXISTS TO HAVE FOUND IS NOT A CARD DEFECT.** The
collision switch read its cell kind out of A, and the line that set the axis
flag was `lda #1`. Every *vertical* collision in the table therefore arrived
as `KSOLID`: every bumper, every rollover, the drain, the plunger and the
lane's own kicker were plain walls. The ball bounced up and down the plunger
lane for the whole scene — and the VRAM gate passed, the frame budget was
measured, the tearing gate passed, the contact sheets looked like a pinball
table, and the score read **000000** for four runs. ⭐ What caught it was the
**lamp gate**, which is the only claim in any of the three scenes that asks
whether the scene *did* anything rather than whether the card drew what it
was told. `bench/README.md` has that and the two smaller ones beside it.

---

## 11. ⭐ CLOSED 2026-09-22 — where a frame's CPU goes, and that it must not go FIRST

**Asked and answered 2026-09-22, by `zelda`.** A scene whose actors are keyed
blits with save-behind tears — an actor drawn in pieces, because the beam
crossed its rows while the copy engine was still writing them. `zelda` with
eight actors tore **~25 % of the actor-frames** and the tear was measured, not
guessed: every component of a creature's unique body colour in 4,117 recorded
frames, its pixel count against the two walk frames, the view edge excluded.

⭐ **Three findings, in the order they were worth:**

| | |
|---|---|
| **1. The pass must be ordered by screen row** | 15 copies is ~2.8 ms and the blank is 1,559 µs, so the pass **overhangs the top of the picture by ~19 rows** whatever else is done. An actor drawn in ascending screen-row order is drawn before the beam reaches it: a creature at sorted rank *k* finishes at ~186·(2+3(*k*+1)) µs and is safe if its row exceeds (that − 1560)/63.6. Sorted, the constraint is met by every actor below the overhang. **25 % → 8 %** |
| **2. ⛔ AND THE PASS MUST *START* AT THE BLANK** | Ordering is worth nothing if the copies do not begin until the beam is already down the picture. `zelda`'s `Body` ran `Logic` — the walk, the camera, the wander rolls, the sort, several milliseconds of 6809 — **before** `Actors`. The tear was measured at picture rows 75..125, which is exactly where that put it, and no amount of ordering could reach it. ⭐ **Run the blits first and the game afterwards**: `Logic` computes the NEXT frame's positions, `Body` is `Frame → Actors → ScCall → Logic`, and `Loop` primes `Logic` once. One frame of latency, invisible. **8 % → 2.5 %** |
| **3. What is left is the machine** | The residue is confined to the top ~60 scanlines — the overhang from finding 1 — and to actors the hero is standing in front of, which is occlusion and not a tear. To remove it you must remove copies, not reorder them |

⛔ **And the correctness rule the first attempt broke.** Interleaving
restore/save/draw per actor is only safe because the creatures' wander boxes
are disjoint; the **hero** is not disjoint from anything. The first cut
restored only the hero before saving what was under him — and the creatures
were still drawn from last frame, so a hero standing on one saved it and
painted it back when he moved off. **67 bytes of ghost**, caught by the wipe
gate and by nothing else. ⚠ **Every restore comes first, then the rover's
save, then the ordered restore/save/draw of the rest.** A save sees pristine
world or it is wrong.

### 11.1 ⭐⭐ AND THE ANSWER WAS THE STRUCTURE, NOT THE ORDERING — 2026-09-22

The ordering above took `zelda` from 25 % to 2.5 % and could not take it
further, because what is left is arithmetic: fifteen copies is 2.8 ms, the
blank is 1.43 ms, and the pass overhangs the picture whatever order it runs
in. ⛔ **The fix is not to draw faster. It is to bound what there is to draw**,
which is what the NES did and what this scene does now:

> *when the hero touches the edge of the room, all enemies freeze, the next
> room scrolls into place, then that room's enemies are placed and begin
> moving. The game is in control of how many enemies are in each room, so we
> can be sure there is always enough draw time.*

⭐ **The budget becomes a derivation.** `Actors` draws in ascending screen row
and the pass starts at the blank, so the actor at sorted rank *k* is written at
~186·(3*k*+5) µs and the beam reaches picture row *Y* at 1430 + 63.56·*Y* µs
(`VMODE` 01: 45 blanked lines of 525, a 31.78 µs line, two lines to a VRAM
row). Rank 3 is safe above row 18.5 and the hero — drawn last — above 21.4.
**The room's top wall is 24 rows**, so four creatures and a hero clear both *by
construction*. A fifth needs row 27.3 and the wall would have to grow with it.
`mkzelda.py`'s `ZMAXCR` carries that derivation as a comment and the program
clamps to it.

⛔ **AND THE ROOM IS 512 COLUMNS WIDE BECAUSE OF THE CARD.** Every `VMODE` is
640 dots across and the ring is a **1024-column torus**, so two horizontally
adjacent 640-wide rooms *cannot both be resident* — a room that exactly fills
the screen has nothing to slide to. Rooms of 512 tile the torus exactly, two at
a time, and the view shows 64 columns of each neighbour. ⭐ **Which is why
every room's outer eight cells are the same wall**: you are looking at your
neighbour's wall and it is identical to your own, so the seam does not exist.
The vertical axis has no such problem — two 240-row rooms cover 0..479 of a
512-row torus, and ⭐ **the 32 rows left over are the only VRAM on this card the
raster cannot reach**, which is where the tile bank, the actor art and the
save-behind scratch live.

| | before | after |
|---|---|---|
| torn actor-frames | 25 % → 2.5 % | ⭐ **none found**: 24 of 24 flagged cases were a sprite *occluded* by the hero or by a tree whose foliage shares its palette index |
| the playfield | 491,520 bytes off the card, **17 s of loading screen** | ⭐ **8,192** — a 50-tile bank. A room is a 1,920-byte MAP assembled into the module and composed by 1,152 copy rectangles (~90 ms) into the slot the camera is not looking at |
| the world | 1024 × 480, exactly the ring | **8 rooms** and as many more as there is module space for |
| the gate | the live page equals the file's picture | ⭐ **every one of the four slots equals some room's composition byte for byte**, and index 0 appears nowhere |

⚠ **Two ordering defects fell out of building it**, and both are the same
shape as the ones above. **The restores were still in INDEX order** while the
draws were in screen order, so an actor was erased for the whole length of the
pass rather than for the three copies between its own restore and its own draw
— 1.75 % on its own. And ⛔ **`Actors` walks the SORT and not `nact`**: a slide
that dropped `nact` to 1 and left `nord` at six went on saving and drawing six
creatures that had just been wiped, in the room they were no longer in.

⚠ **How to measure this, rather than reason about it.** Two frame-level
statistics settle it without a trace: *display frames per distinct actor
position* (1 means the pass fits in a frame; 2 means it does not), and *the
partial rate by screen-row band* (clustered at the top = the overhang;
clustered mid-screen = the pass is starting late). The second is what named
finding 2.
