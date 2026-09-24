# Copyrect, and what a blitter-first card would and would not buy

**2026-09-16.** Three questions were asked together, and they have one answer
between them: *could a blitter-first card carry character, bitmap and tile modes
and align better with NitrOS-9's graphics primitives; do we instead need
memory-mapped VRAM; and is there anything in QuickDraw worth taking?*

> This is a **design note**, not a specification. `hardware/archive/video/docs/graphics.md` owns
> the card; `docs/video-options.md` compares the three card shapes;
> `software/nitros9/docs/nitros9-hardware-improvements.md` is the ranked change list this feeds.
> ⚠ **Nothing here is fitted, placed or costed by `pack.ts`.** Package counts are
> estimates against the fitted parts' headroom, and §3 says what would refute
> them.

**The answers, in order:**

1. **A blitter cannot make character mode fast**, on this CPU, ever — the
   bottleneck is descriptor *issue*, not pixel movement, and a tilemap is a
   blitter the scanout runs for free. §1.
2. **Copyrect is nevertheless the right next hardware feature**, because it is
   the one capability class with no software substitute, and the 1024-byte stride
   makes it far cheaper here than `features.md` §5's general blitter. §2, §3.
3. **Memory-mapped VRAM is a downgrade**, and the repository has already priced
   it twice (`video2`, the VIC-II derivative). §4.
4. **QuickDraw has four lessons and three of them cost nothing.** §5.

---

## 1. Why a blitter is not a character generator

The card's documented constraint is the CPU (`graphics.md` §2.1: **~15× more
spare accesses than the CPU can consume**). A store is **6.00 E cycles**,
measured (`graphics.md` §7.3, `machine_tb`) — 2.86 µs at 2.098 MHz. A blit
descriptor is source, destination, width, height and mode: call it ten writes.

Every row below is that one measured figure times the writes a cell costs.
⚠ **The published figures in `graphics.md` §6.4.8, §7.3 and `video-options.md`
§2.3 are ~20 % lower** because they were written against the unverified 5 cycles
of `graphics.md` §19 item 1; these are the same mechanisms at the measured rate.

| 80×25 full redraw | Writes a cell | At 2.86 µs a write |
|---|---|---|
| A blitter, one blit per glyph | 10 (a descriptor) | **~57 ms** — the pixels are free; *describing* them is not |
| Span-mask bitmap text | 13 (§7.3) | ~74 ms |
| `video2`'s hardware character generator | 4 (`video-options.md` §2.3) | ~23 ms |
| **Cell mode** | **1** (§6.4.8) | **~5.7 ms** |

⭐ **A tilemap is a blitter that runs at 100 % of display bandwidth and costs
nothing**, because the composition happens in the scan path, 70 times a second,
whether or not anything changed. A blitter has to be *told*, and ten
descriptor writes is the same order as the span writer's thirteen — which is
why the two rows are within 30 % of each other and both are an order of
magnitude off cell mode.

The only way out is an engine that walks a string of codes from VRAM — at which
point it is a character generator with extra steps, paying VRAM bandwidth for
what the scanout already does free.

**So the shape stays: scanout does what repeats, the span writer does runs, and a
copyrect engine does what neither can touch.** Character mode belongs to the
first, and `graphics.md` §6.4.8 already has it.

---

## 2. What copyrect is actually for

`features.md` §5 prices a general blitter at ~14 ICs and ~10 GALs for 8.7 Mpx/s
and concludes its value is narrow. That is right, **and it measures the wrong
thing**: with §7.4's broadcast write the span writer fills at 25.1 MB/s, so a
blitter buys nothing on fills. What it buys is the row `features.md` §5 puts
third — *moving colour image data* — and on this card that reduces to one fact:

⛔ **There is no VRAM-to-VRAM path at all.** Every byte that moves within VRAM
goes out through `VDATA` into the CPU and back. That is the whole of `H1`–`H5`,
and it is the same class the NitrOS-9 compatibility report
(`software/nitros9/docs/video-compat.md` §1) identifies as what GrfDrv does by
reading memory back.

### 2.1 The rate

From `graphics.md` §2.1's own budget — 115,600 spare accesses a frame, each up to
four bytes across the two ×16 parts (§14.2.3) — a copy costs one read access and
one write access:

**≈ 16.2 MB/s sustained** across a whole frame (12.6 MB/s inside active display,
25.1 MB/s in blanking, where the display fetch is not competing).

| Operation | Today | Copyrect | |
|---|---|---|---|
| **H1** pointer save + restore, 16 × 16 | 7.9 ms, idle-loop only | **~32 µs**, + a `WMODE 11` compose ≈ **125 µs** | ⭐ fits the mouse's IRQ |
| **H5** 192-row window scroll | ~350 ms | **7.6 ms** | 46× |
| **H4** `Select`, 640 × 200 | ~2.6 s each way | **7.9 ms** | ~320× |
| `GetBlk`/`PutBlk`, 64 × 64 | ~41 ms | **0.25 ms** | 160× |
| **H15** the hero's fifteen tiles | a hero every 5 frames (2026-09-17, measured) | ~95 copies a hero **with a key**, so 1–2 frames; one copy for the figure in bitmap mode | ⚠ a tile is a 64-byte run, not a rectangle on the stride — `hardware/video3/docs/demo-report.md` §10.5 |

⭐ **It makes the hardware cursor unnecessary.** `H1` is ranked 5 at ≈ +4–5
packages for a 16 × 16 overlay that `features.md` §8 says may not fit the pixel
path's 11.7 ns of margin. Copyrect plus the sprite `WMODE` the card already has
gets a pointer move inside an interrupt service **without touching the pixel path
at all** — and delivers H4, H5 and H15 in the same silicon.

### 2.2 ⭐ And the adder that usually makes copyrect expensive does not exist here

A rectangle blit normally needs `src += stride − width` at the end of every row —
an adder, and this card's whole address path is built on not having one
(`graphics.md` §6.4.1, §7.2). **The stride is 1024, a power of two**, so
end-of-row is *reload the column, increment the row*: that is `WADV = 01`, built
since 2026-09-09, register-file shadow and all.

So a copyrect engine is a second `WADV`-shaped pointer, two down-counters and a
read-then-write micro-sequence — not `features.md` §5's general blitter with
arbitrary strides and logic modes, which was priced in the GAL era before
`§10.1.2` moved the card to CPLDs and showed **52 % of the GAL pin count was
packaging talking to itself**.

⚠ **Estimate, not a fit: a fourth `ATF1508AS` + ~4 × `'574` ≈ +5–6 packages, 33 → ~39.**

### 2.3 The cheap first increment — and what "vertical-only" actually restricts

⚠ **It does not mean full-width rectangles.** The width is a counter; any width
works. **Vertical-only means the source and the destination share a column
range** — the rectangle may move up or down, but not sideways.

An earlier draft of this section said it "needs no column handling at all" and
that `RPTR` is `WPTR` "with a constant added to bits [18:10]". Both are wrong: a
copy of any width needs a column counter and its end-of-row reload, and *adding*
a row offset would be the adder this section's whole argument says does not
exist. **The CPU loads both row registers**; there is no arithmetic on the card.

What vertical-only saves is the **second** column counter:

| | general | vertical-only |
|---|---|---|
| column | one counter + one shadow, reloaded at end-of-row (`WADV 01`, §7.2) | **shared by both pointers** |
| row | two 9-bit registers, each stepping once a row | same |
| a second column counter + shadow | needed | ⭐ **not needed** |
| the new source on `vaddr`'s address mux | spans all **17** address bits | ⭐ spans only the **9 row bits** |

**That last row is the reason to prefer it as a first increment**, and it is not
about the state. §3 says `vaddr`'s four-source mux with one spare and 40/40 block
fan-in is the binding constraint; **halving the width of the source it has to grow
is worth more than the registers saved.**

**What it covers, and what it does not:**

| | |
|---|---|
| ⭐ **H5**, a window scroll | ✓ the same columns, the rows move |
| ⭐ **H4**, `Select` between the two VRAM pages (§6.4 of the compat report) | ✓ columns 0–639, rows differ |
| ⭐ **H1**, the pointer's save-behind | ✓ **if the driver puts the save area at the pointer's own columns in an off-screen row** — the ring is 1024 wide and a screen is 640, and a 200-line screen leaves rows 200–511 free |
| ⭐ `OWSet` / `OWEnd` overlay save and restore | ✓ the same trick |
| ⛔ `GetBlk` → `PutBlk` at a different x | ✗ the general form |
| ⛔ an icon or sprite blitted to an arbitrary x | ✗ |

**So vertical-only covers every save-and-restore and every scroll, and moves
nothing sideways.**

> ⛔ **And it cannot be laundered into a horizontal move through `HSCROLL`.** The
> tempting three-step — copy a rectangle to an off-screen row, scroll it sideways
> with `HSCROLL`, copy it back — does nothing, because **`HSCROLL` moves the view,
> not the bytes**: it is a *scan-address* register that the raster loads once a
> line (§8), and no part that writes or copies ever reads it. The card has two
> address generators — the scan address, which is display-only, and `WPTR`, which
> is everything else — and **they never meet**. Step 3 would copy back exactly
> what step 1 wrote, to the columns it came from.
>
> ⭐ **The instinct is right for one case, and that case is already built.** A
> display list sets `HSCROLL` *per scanline* (§10.3), so a **full-width band of
> rows scrolls horizontally for nothing, with no copy at all** — `SS.Raster`, which
> `run-vid.sh`'s `wave` run exercises over 441 frames. ⚠ It shifts the whole line,
> so it is for full-width bands, not for a window inset in one.
>
> ⭐ **And the cheap step up from vertical-only is one more column counter, not a
> dance.** A second column counter and shadow gives the *fully general* copyrect,
> byte-granular, **with no shifter anywhere** — at 4.05 MB/s, still 40× `Strm`.
> The four-byte fast path then survives wherever the two columns are congruent mod
> 4, which every 8-pixel-aligned blit is. So the ladder is **vertical-only → a
> second column counter → (never) a barrel rotate**. `software/nitros9/docs/nitros9-hardware-improvements.md` H5 already asked for
"even one limited to vertical moves"; this is what that costs and what it buys.

---

## 3. What it would cost, and what would refute the estimate

| | |
|---|---|
| ⚠ **`vaddr` is the binding constraint, as always** | the framebuffer address mux is already four-source with one spare, and `graphics.md` §6.4.1 says a macrocell holds five before cascading. `RPTR` is the fifth — and §10.1.6.2 records that **a fifth or sixth source per bit is exactly what the list engine's fits ran out of**, which is why the engine shares `WPTR`. `vaddr` is at 113/128 cells and **40/40 fan-in in every block** |
| ⚠ **Alignment** | four bytes an access needs **`src` and `dst` columns congruent mod 4** — not absolute alignment. Vertical-only satisfies it by construction, and so does **every 8-pixel-aligned GUI blit** (a glyph cell, a tile, an icon on a cell boundary), because 8 is a multiple of 4. An arbitrary x falls to one byte an access: **4.05 MB/s, 40× `Strm` and 17× the unrolled form** (§6) — so the fast path is worth having and **a barrel rotate to rescue the non-congruent case is not** |
| ⚠ **The write-data path is eight bits wide** | `graphics.md` §7.4: there is **one** `74HC574` posted-write latch that fans out to all four byte lanes, which is what makes the broadcast write free. A copy needs four *distinct* bytes, so the read latches have to become the write drivers |
| **What would refute it** | a fit. `sh tools/gal/prjbureau/fit1508.sh` on a `vaddr` carrying a second pointer, and `pack.ts` on a parts list carrying the fourth CPLD. Until then this is arithmetic against headroom |

---

## 4. Memory-mapped VRAM — priced twice already, and it loses

`docs/video-options.md` exists for this question: **`video2` and the VIC-II
derivative are both flat-addressed**, and §2.6 is generous about what that buys —
it "deletes the 19-bit pointer, the posted-write latch, the prefetch and its
invalidation rules, the `WPTR` reload rule software must keep, and with them most
of `graphics.md`'s 2026-09-10 defect list."

Three things kill it anyway.

**1. It makes nothing fast.** Flat VRAM is still written by a 6809 at ~350,000
stores a second.

| 640 × 200 full-screen clear | |
|---|---|
| Flat-mapped, CPU stores | **366 ms** |
| Span-solid, broadcast (`graphics.md` §7.4) | **5.1 ms** |

`video-options.md` §2.4 measures the same thing from the other side: `video2`
clears in ~183 ms where `video/` does 1.2 ms of CPU. **Flat addressing would
trade a 70× drawing engine for a convenient address.**

**2. ⛔ 8bpp breaks GrfDrv's memory model whatever the addressing.** GrfDrv has
64 KB of task-1 map for the screen, the font, the patterns, the get/put buffers
and its own 7,390 lines. A CoCo 3's largest screen is 640 × 192 × 4bpp = 61,440
bytes and it *already* has to window. Ours is **128,000–307,200 bytes, 16 to 38
blocks of eight** — so a flat-mapped GrfDrv would run its inner loops through map
register writes. **The compatibility that would justify the change does not
arrive.**

**3. The packages, and the pins.** `video2` with both modes is **67, eleven over
the board**; one mode is 59, or 53 with two GALs, against `video/`'s 33 — and
neither has a drawing engine. As an *increment* to this card it is no cheaper: a
flat map needs `PA[18:0]` on the card, and `vsup` has **one** spare pin, `vctrl`
eight, `vaddr` five. A fourth CPLD and a re-partition — the same price as
copyrect, for less.

> ⭐ **A middle option exists and is worth recording.** A single 8 KB *aperture*
> windowing VRAM at a programmable base gives true random access for the cases
> `VDATA`'s post-increment handles badly — a read-modify-write pixel, the bitmap
> text caret, flood fill's probing. It needs 13 address bits and a base register
> rather than 19, so it is cheaper than a flat map. It still lands on `vaddr`'s
> mux, and copyrect is worth more per package. ⚠ **And most of it already
> exists** — see §5.5.

---

## 5. QuickDraw

The Mac 128K had no video hardware at all: a 68000 at 7.83 MHz and a
512 × 342 × 1bpp framebuffer in main RAM — **21,888 bytes**. Ours at 640 × 400 ×
8bpp is **256,000**: ~12× the data at roughly a fifth of the store bandwidth.

⭐ **So we cannot do QuickDraw's job by pushing pixels, and we do not have to.**
QuickDraw decomposes every primitive into horizontal runs and feeds them to a
slab writer; that *is* the span writer, and `features.md` §7 already found the
match "closer than it has any right to be" — a QuickDraw pattern is 8 × 8 1bpp,
and a span-mask byte is one row of it.

### 5.1 ⭐ Regions — the biggest idea we do not have

QuickDraw's `RgnHandle` is a scanline-crossing list; a window's visible area is a
region, and clipping is a region intersection. **Clipping at the span level is
already free on this card** (`features.md` §7: clip the run endpoints before
writing `SPANLEN`) — regions make that free for *any* shape rather than only
rectangles.

CoArm clips to the working rectangle and handles overlap with **save-behind**
(`OWSet`), which is a `VDATA` stream. Regions would let an obscured window be
*redrawn* through clipped spans instead of saved and restored — trading a stream
for span writes, which is the trade this card wants.

⚠ **It is a departure from CoWin's model, not a free upgrade.** CoWin is
save-behind because the CoCo 3 is; the Mac is redraw-plus-regions. Choosing is a
real design decision and it belongs to the driver, not the card.

### 5.2 ⭐ The bottleneck-routine discipline

Everything in QuickDraw funnels through a handful of inner loops. `ca_row.asm`
already is this — `RowFill`, `RowPut`, `RowGet`, `RowMask`, `Glyph`. The lesson is
to **enforce it with no side paths**, because then copyrect and logic `WMODE`s
plug in at five places instead of fifty.

### 5.3 ⭐ Compiled inner loops — measured, §6

Atkinson generated code at run time. The 6809 analogue is an unrolled store block.
`software/nitros9/docs/nitros9-hardware-improvements.md` quotes VidCore at **~10 µs a byte**, and
every H-item's cost is denominated in it. §6 measures what that is made of.

### 5.4 ⚠ Transfer modes are the one place QuickDraw needs hardware we lack

`srcOr`, `srcXor` and `srcBic` drive the caret, selection highlighting and
rubber-banding. We have no logic `WMODE` (H2, H3).

⭐ **And H3's cost model is out of date.** Its entry says a logic mode "needs the
span writer to read before it writes, which is the blitter's datapath" — **since
`graphics.md` §11 built the VRAM read path on 2026-09-11 that is no longer true.**
Read the byte at `WPTR` into the `vread` latch that already exists, ALU it with
`WFG`, write it back: one byte per two slots is **3.15 MB/s, 4.5× `TFM`**, for an
8-bit ALU and a mux — ~3 packages, not 14.

⚠ **It only works byte-wide.** The two ×16 parts need 32 distinct bits for a
4-byte logic op, and the write-data latch fans *one* byte to all four lanes
(§2.3). So logic modes give up the broadcast width, which solid fills keep.

### 5.5 Depth discipline — and the fast path that already exists

QuickDraw was fast because the GUI was 1bpp. **Ours should be too**: span-mask is
native 1bpp-source → two colours at 8 px a write, and span-solid broadcast is
25.1 MB/s. 8bpp belongs to images and games, not to window frames, menus, icons
and chrome. CoArm already draws text this way.

⭐ **And `graphics.md` §11 has a consequence nobody has used.** "The physical
address a store carries selects the VRAM window and nothing else" — so **every
address in a mapped VRAM window is `VDATA`**, and a 16-bit store carries two
bytes for one instruction. §6 measures it: it is the fastest path on the card, and
it needs no hardware change at all, only an 8 KB map slot that `+$15 VDATA` was
invented to avoid spending.

---

## 6. ⭐ The store rate, measured — `software/archive/demo/bench/vramrate.asm`

```sh
sh software/archive/demo/bench/run-vramrate.sh        # the host emulator, ~1 min
sh software/archive/demo/bench/run-vramrate-rtl.sh    # the whole machine, ~15 min
```

Eight phases, **130,560 bytes each** (85 chunks of 96, so that no form's
unrolled block over- or under-runs a partial chunk), bracketed by progress-port writes that both
the emulator and `demo_tb` timestamp in the same format; `tools/vramrate.py`
subtracts. Phases 1, 3 and 5 are `vidcore.asm`'s `Strm` **verbatim**; the rest
keep its per-chunk bookkeeping and masking discipline (`nitros9-av-plan.md` §3.4:
`/IRQ` open between chunks) and change only the inner loop. ⚠ The emulator's CPU
is cycle-checked against `mc6809e.v` (`emu/test/cycles.py`), so these are E
cycles rather than an approximation of them.

**Measured on the host emulator, 2026-09-16.** 131,072 bytes a phase,
E = 2.0979 MHz. ⭐ **The bench asserts its own correctness first**: every PUT
form writes 1,024 bytes and `vidcore.asm`'s own `Strm` GET reads them back
(`$AE`); a mismatch is `$EE`, which the emulator and `demo_tb` both treat as a
ROM failure.

| | phase | µs/byte | cyc/byte | cycle table | vs its own `Strm` |
|---|---|---|---|---|---|
| `$A1` | PUT VDATA, **`vidcore.asm` `Strm`**, chunk 24 | **9.941** | **20.86** | 21.00 | — the baseline every H-item is quoted in |
| `$A2` | PUT VDATA, unrolled DP, chunk 64 | 4.517 | 9.48 | 9.59 | **2.20×** |
| `$A3` | FILL VDATA, `Strm`, chunk 24 | 7.217 | 15.14 | 15.00 | — |
| `$A4` | FILL VDATA, unrolled DP, chunk 64 | 2.647 | 5.55 | 5.59 | **2.73×** |
| `$A5` | GET VDATA, `Strm`, chunk 24 | 10.033 | 21.05 | 21.00 | — |
| `$A6` | GET VDATA, unrolled DP, chunk 64 | 4.517 | 9.48 | 9.59 | **2.22×** |
| `$A7` | FILL **window**, `STD <dp`, chunk 64 | 2.419 | 5.07 | 4.09 | **2.98×** ⚠ |
| `$A8` | PUT **window**, `PULU` + 3 × 16-bit store | 3.922 | 8.23 | 6.09 | **2.53×** ⚠ |

⭐ **Six of the eight land within 0.11 cycles a byte of the 6809 cycle table**,
which is the check that matters: it says the card never stalled the CPU in them,
so what they measure is the cost of the *loop* and not the cost of the *card*.
`graphics.md` §2.1's no-stall guarantee, measured rather than argued.

⚠ **The two that do not are the two using 16-bit stores, and the gap is the
emulator.** `machine.c` recomputes `m->dots` from `cpu.cycles` only *between*
instructions (`machine.c:1179`), so both write cycles of an `STD` land on the
same dot and the second meets the first's `busy_until`. On silicon they are
consecutive E cycles — **476 ns apart, against a direct write's ≤318 ns of
`SPANBUSY`** (§7.4's 159 ns retire plus a grant). **So `$A7` and `$A8` are upper
bounds**, and the window is the fastest path even at them.
⭐ **THE RTL RAN IT, 2026-09-16, AND IT SETTLES BOTH.**
`run-vramrate-rtl.sh` on `demo_tb` — `mc6809e` + the whole motherboard + the
whole video card:

| | `$A1` | `$A2` | `$A3` | `$A4` | `$A5` | `$A6` | `$A7` | `$A8` |
|---|---|---|---|---|---|---|---|---|
| **RTL, cyc/byte** | **20.84** | 8.98 | 15.14 | 5.03 | 21.05 | 8.98 | **3.55** | **5.48** |
| cycle table | 21.00 | 9.06 | 15.00 | 5.06 | 21.00 | 9.06 | 3.56 | 5.56 |
| Δ | −0.16 | −0.08 | +0.14 | −0.03 | +0.05 | −0.08 | **−0.01** | −0.08 |

**All eight within 0.16 cycles a byte**, `$A7` within 0.01 — so a 16-bit store
into the window does **not** stall on silicon, the emulator's gap was entirely
its own artefact, and the window is the fastest path by measurement rather than
by argument: **4.26× on fills and 3.80× on copies** against `Strm` today.

> ⛔ **The self-check earned its keep on its first run.** The unrolled streamers
> were written with a 96-byte chunk against an 8,192-byte request, and **an
> unrolled block has no early exit** — so the last chunk of every call overran by
> 32 bytes and the check reported `$EE`. The chunk now has to divide the request
> (64 does; 96 did not), and **a real driver needs a remainder loop**, whose cost
> is once a call rather than once a chunk. Nothing in the timing would have
> revealed this: the overrun made the loop look 0.8 % *slower*, not wrong.

> ⚠ **OPEN: the self-check passes on the emulator and failed (`$EE`) on the RTL
> run that produced the table above**, on the *first* form — `Strm` verbatim.
> An earlier RTL run passed all three (`$AB $AC $AE`); between them the check's
> transfer went from 1,024 bytes to 960 and the chunk from 64 to 96. **The cause
> is not found**, and the timings do not depend on it — the instruction streams
> execute identically whatever bytes flow. ⛔ **So the bench is validated for
> rate on the RTL and for correctness only on the emulator.** The next step is to
> make the check report *where* it mismatched (index, expected, got) as
> progress-port nibbles, which costs one more RTL run and diagnoses itself.

### 6.1 What it says

1. ⭐ **VidCore's 10 µs a byte is real, and two thirds of it is the loop.**
   `Strm`'s inner loop is `LDA ,X+` 6 + `STA n,U` 5 + `DECB` 2 + `BNE` 3 = **16
   cycles a byte**, plus ~5 more from a 24-byte chunk's bookkeeping. **The card is
   not in it.**
2. ⭐ **Unrolling and the direct page cut it by 2.2× for a copy and 2.7× for a
   fill**, with no hardware, and **the masking rule survives**: a 64-byte chunk of
   4-cycle stores masks `/IRQ` for **256 cycles against the 504 that 24 of the
   current ones spend** — so the chunk could grow further, and the per-chunk
   bookkeeping (~102 cycles) is what a longer one would amortise.
3. ⭐ **The VRAM window is the fastest path, and it already exists.** A 16-bit
   store into a mapped window carries two bytes; `PULU A,B,X,Y` fetches six in
   eleven cycles. The cost is an 8 KB map slot.
4. ⚠ **The `PSHS` blast is not the answer.** `PSHS` writes descending addresses in
   a fixed register order, so on a port that post-increments `WPTR` the bytes come
   out reversed — fine for a fill, wrong for a copy, and **span-solid already
   fills at 25.1 MB/s.**
5. ⭐ **`+$16` as a second `VDATA` alias would give 16-bit stores to the I/O-page
   port too**, with no map slot: one decode term on a register that
   `graphics.md` §13 already reserves and that decodes nowhere. It is the cheapest
   item in this document. ⚠ Unpriced, unfitted, and it needs `WSTB`'s exclusion
   rule checked (§11's `+$15` note).

### 6.2 ⚠ What this does to the improvements list

**Every cost in `software/nitros9/docs/nitros9-hardware-improvements.md` is quoted in VidCore
byte-times**, so a 2.2–3× software win moves the whole table before any silicon is
bought. §7 of that document is where the re-ranking lands.

---

## 7. The recommendation

**Three engines, each owning what the others cannot touch. Two are built.**

| | Owns | Status |
|---|---|---|
| **Scanout** | what repeats every frame: tilemap text, scroll, the display list | ✅ built; wants H9's six-bit cell row |
| **Span writer** | 1bpp → two colours, solid runs, sprites | ✅ built; wants logic modes (H3, re-costed §5.4) |
| **Copyrect** | VRAM ↔ VRAM | ❌ the missing third — collapses H1, H4, H5, H15 and the buffer class into one item |

**Not blitter-first. Copyrect-completing.** And in this order:

1. **Rewrite VidCore's streams** (§6) — measured, free, and it changes what the
   rest of the list is worth.
2. **H3's logic `WMODE`** (§5.4) — ~3 packages now that §11 exists, not 14.
3. **Copyrect, vertical-only first** (§2.3), then the general form.
4. **H9's six-bit cell row** — the console item.
5. ⛔ **Not a hardware cursor (H1) and not memory-mapped VRAM** — §2.1 and §4.
