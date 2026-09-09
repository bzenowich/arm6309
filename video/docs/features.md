# What the Video Card Can Actually Do

## Modes, the Span Writer, and Nine Questions About Drawing

**Question this answers:** [`graphics.md`](graphics.md) is 3,100 lines of *why* — why
640 wide, why the LUT is one ×16 part, what the list engine cost. It is organised
around decisions, not around capability, so *"can this thing fill a polygon?"* has its
answer scattered across four sections and its arithmetic in a fifth. **This document is
the capability view.** It invents nothing; every number is `graphics.md`'s, and where it
reaches a conclusion that document does not state, the conclusion is marked.

> ⚠ **Everything with a microsecond in it scales on one unverified number.**
> `graphics.md` §7.3 assumes **a tight 6309 store loop sustains one write per 5 core
> cycles in native mode** — 2.38 µs at `E` = 2.098 MHz — and §19 item 1 flags it as the
> thing to measure first. If it is 4 cycles the CPU-bound figures improve 25 %; if it is
> 7, they fall 29 %. **The memory-side figures do not move**, because they come off the
> fetch-slot grid.

> Superseded material is archived in [history.md](history.md); this document
> describes only the present design.

---

## 0. Capability summary

| | |
|---|---|
| **Bitmap** | **640×200, 640×240, 640×400, 640×480 — all 8bpp**, 256 simultaneous colours from 65,536 (RGB565 LUT). §1 |
| **Text** | **80×25, 80×30, 80×50, 80×60**, 8×8 cells, rendered by the span writer at **13 writes/cell** — or, for a one-colour-pair console at 80×25/80×30, by cell mode at **1 write/cell** (§2.4). ⚠ **No hardware character generator** — §2.2 was dropped 2026-09-08 to afford the display list. §2 |
| **Tiles** | 8×8, **8bpp per pixel — no attribute clash**, 64:1 write compression. §1.4 |
| **Colour depth** | 8bpp everywhere. There is **no 4bpp, 2bpp or 1bpp packed mode** and no 320-wide mode. §10 |
| **Scrolling** | **Free, both axes, pixel-accurate**, by register — a 1024 × 512 ring. §1.3 |
| **Buffers** | 512 KB of VRAM = **four full 640×200 screens**. Double and triple buffering are free. §1.2 |
| **Span writer** | the card's drawing engine: **6.29 MB/s solid fill today, 25.1 MB/s once `graphics.md` §14.2's two-chip framebuffer lands**, 8 pixels per CPU write in mask mode. §3 |
| **Polygon fills** | **Yes** — scanline decomposition in the CPU, spans in hardware. **0.7 to 6.3 Mpx/s depending on span width.** §6 |
| **QuickDraw offload** | **`PaintRect`, pattern fills, glyph blits, horizontal spans and scroll: yes.** Lines, arcs, regions, colour image copies: no. §7 |
| **Sprites** | **No hardware sprites.** Software costs ~0.9 ms per 16×16 sprite per frame, so **4–6 moving objects**. §8 |
| **Mouse cursor** | **Yes, pixel-accurate in bitmap mode** — save-behind, **~0.9 ms per move, 6.4 % of the CPU while dragging and 0 % when still.** §9 |
| **Raster effects** | VBL + line-compare interrupts give a **software copper at 2–3 splits/frame** today. §4 |
| ⭐ **Display list** | **Built 2026-09-08, for zero packages.** Per-scanline `HSCROLL`, palette and mode changes with no CPU. ⚠ It shares `WPTR`, so a list clobbers the write pointer — `graphics.md` §10.3.1. §4 |
| ⚠ **Blitter** | **Deferred.** ~14 ICs and ~10 GALs for 8.7 Mpx/s of *8bpp* movement, which is the one thing the span writer cannot do. §5 |

---

## 1. Bitmap modes

### 1.1 The four resolutions

All four are 8bpp chunky, one byte per pixel, `VMODE` in `CTRL` `+$00` (`graphics.md`
§6.2, §13):

| `VMODE` | Resolution | Timing | Refresh | Frame bytes | VGA identity |
|---|---|---|---|---|---|
| `00` | **640×200** (line-doubled) | 800 × 449 | 70.09 Hz | 128,000 | 640×400 @ 70 — the DOS text timing |
| `01` | 640×240 (line-doubled) | 800 × 525 | 59.94 Hz | 153,600 | 640×480 @ 60 |
| `10` | 640×400 (progressive) | 800 × 449 | 70.09 Hz | 256,000 | 640×400 @ 70 |
| `11` | **640×480** (progressive) | 800 × 525 | 59.94 Hz | 307,200 | 640×480 @ 60 |

**The progressive modes cost no extra bandwidth** — line doubling fetches every row
twice, so 640×400 and 640×200 both fetch 640 bytes per scanline. The only cost is
memory (`graphics.md` §6.2).

**One dot clock, 25.175 MHz, and both timings are real VGA modes**, so any monitor,
LCD or scaler locks them without argument. **VSYNC polarity switches with `VMODE`** —
positive for the 449-line family, negative for the 525-line one — because that
polarity is the *only* thing distinguishing them at the connector (§6.2.1).

> **640×480×8bpp on a 6309 is not a mode any period machine had.** It costs one bit in
> `CTRL` and a few product terms in the V-sync GAL.

### 1.2 Colour, and how much of it

**256 simultaneous, from 65,536.** The palette is a 256-entry × 16-bit RGB565 LUT, and
it is *per pixel* — there is no cell attribute, no colour clash, no per-scanline limit.
An RGB332 identity palette is loaded at boot, so software that wants to treat the index
*as* a colour can (`graphics.md` §9).

⚠ **Palette writes during active display snow**, and the card has no mechanism to
prevent it — the LUT address bus is shared by tri-state turnaround between the scanner
and the CPU. Write the palette during blanking. This is a software rule and
`graphics.md` §13.1 states it as one.

**512 KB of VRAM against a 128,000-byte screen is four full buffers.** Double
buffering, triple buffering and off-screen composition areas are free, and the flip is
a register write.

### 1.3 Scrolling is free and pixel-accurate

VRAM is a **1024 × 512 torus**. `VSCROLL` (9 bits) picks the top row, `HSCROLL`
(10 bits) the left column, and the scan-address generator wraps by construction — no
copying, no tearing, one register write per axis (`graphics.md` §8).

The row stride is **1024 for a 640-pixel screen**, so 384 bytes of every row are
off-screen. That is not waste; it is the scroll margin, and it is what makes horizontal
scrolling free.

### 1.4 Tile mode — 8bpp, and no attribute clash

`CTRL` b5 `CELL` switches the fetcher from a linear scan to a tile fetch: a map byte
selects one of 256 8×8 tiles, and **every pixel keeps its own 8bpp colour**
(`graphics.md` §6.4.2).

| | Bitmap | Tile mode |
|---|---|---|
| Screen memory | 128,000 B | **3,200 B map + 16 KB tile set** |
| CPU writes to change one cell | 64 | **1** |
| Colours | 256, per pixel | **256, per pixel** |

**64:1 write compression on exactly the workload the CPU is worst at.** The GIME's and
the VIC-II's tile modes are both 1bpp with cell attributes; this one is a strict
superset of either.

The tile address is **concatenation, not arithmetic** — every field lands on its own
address bits, so there is no adder anywhere. `hardware/gal/tile.check.ts` asserts that
by showing OR equals ADD over all 524,288 field combinations, and that the fitted
address mux computes the same addresses the model does.

⭐ **Tile mode scrolls in both axes, coarse and fine, from the same two registers as
bitmap mode.** Every field of the cell address is a slice of a scan counter §1.3
already preloads, so a scrolling tilemap costs a `HSCROLL`/`VSCROLL` write and
nothing else — no adder, no offset register, no new logic.

| | Horizontal | Vertical |
|---|---|---|
| Which cell | `HSCROLL[9:3]` | `VSCROLL[8:3]` |
| Which pixel within it | `HSCROLL[2:0]` | `VSCROLL[2:0]` |
| **Ring** | **128 cells — 1024 px** | **⚠ 32 cell rows — 256 px** |
| Off-screen margin at 80×25 | 48 cells | **7 rows** |

`hardware/gal/tile.check.ts` walks every displayed pixel at whole-cell offsets,
sub-cell offsets and across both ring wraps.

⚠ **The vertical ring is half the bitmap's.** The map address has no `A18`, so a
vertically scrolling playfield has **seven cell rows of runway** to write ahead into
rather than the bitmap's thirty-nine, and the mode reaches 80×25 and 80×30 but not
80×50 or 80×60. Horizontally there is no such asymmetry — 48 cells of margin, the
same 384 px §1.3 gives the bitmap.

The fetch sequence behind it is built and checked too — `graphics.md` §6.4.9 for the
cell cadence, §8.1 for the window signals that step the counters — and
`hardware/gal/cadence.check.ts` runs a whole line and a whole frame in each of the
four modes.

---

## 2. Text modes

### 2.1 The four text geometries

8×8 cells, so 80 columns always:

| Bitmap mode | Text | Cells |
|---|---|---|
| 640×200 | **80×25** | 2,000 |
| 640×240 | 80×30 | 2,400 |
| 640×400 | 80×50 | 4,000 |
| 640×480 | **80×60** | 4,800 |

**8-pixel cells are why the span-mask writer is exactly one write per glyph row** — the
mask byte *is* the glyph row, with nothing wasted and nothing to truncate (§3). They
also mean CP437, the CoCo 3 hi-res font and VT100 line-drawing all drop in unmodified.

### 2.2 Character mode (dropped 2026-09-08; see history.md)

Not built. `graphics.md` §6.4.3's Variant B — a 1bpp character generator colouring
text through the palette LUT's unused 127/128, at 2 CPU writes per cell — was spent
on §4's display list, which needed its macrocells, product terms and four pins.
**Text is §2.3's span writer in bitmap mode**, and every text figure in this
document is that one unless it says otherwise. The full design, its cost model, and
the trade that decided the drop are archived in
[history.md](history.md) (§6.4.3 entry).

### 2.3 ⭐ Text in bitmap mode — the general text mode

Character mode was **global** anyway — cells or pixels, not both in one region
(`graphics.md` §6.4.6) — so a program needing text *over* graphics always rendered
glyphs into the bitmap with the span writer. Since 2026-09-08 that is every program
that needs text over graphics or a colour per cell; §2.4 is the console that needs
neither:

| | Character mode (not built — §2.2) | ⭐ **Span writer, in bitmap mode** |
|---|---|---|
| One cell | 2 writes, ~4.8 µs | **13 writes, ~31 µs** |
| **Scroll one line** — what a terminal does | ~0.4 ms | **~2.5 ms**, ~400 lines/s |
| Full 80×25 redraw | ~9.5 ms, 105 Hz | **~62 ms, 16 Hz** |
| At 9600 baud (~12 lines/s) | 0.5 % CPU | **3 % CPU** |
| At 115.2 kbaud (~144 lines/s) | 5 % CPU | **36 % CPU** |

**A terminal never full-redraws** — it scrolls, and 2.5 ms plus one register write is
comfortable. The 13 writes are `WPTR` ×3 + `WFG` + `WBG` + eight glyph rows, and
`npm run check:seqctl` asserts the 13.

⭐ **And where a redraw does happen, the wire is the bottleneck, not the card.** A full
80×25 ANSI art screen is 2–4 KB of escape codes: **2–4 seconds at 9600 baud** against
62 ms to draw it. The renderer is 30–60× faster than the line feeding it.

> **Both are ~3× better than the obvious alternative.** A `TFM` of a pre-rendered
> 8×8×8bpp glyph is 64 bytes at 3 cycles each ≈ 92 µs per cell, because `TFM` moves one
> pixel per cycle-triple and the span writer moves eight pixels per CPU write.

### 2.4 ⭐ Fast monochrome text — cell mode, at one write per cell

**Spend the 256 tile codes on glyphs instead of graphics and §1.4's tile mode is a
character generator** — a better one than §2.2's, which is the mode that was dropped.
Bake an 8×8 font into the tile set, one glyph per code, and a character cell is **one
CPU write of one map byte**. Nothing new is built: the mode, the address and the
register are §1.4's, and the font is data.

| | Span writer, bitmap (§2.3) | Character mode (not built — §2.2) | ⭐ **Cell mode, one colour pair** |
|---|---|---|---|
| One cell | 13 writes, ~31 µs | 2 writes, ~4.8 µs | **1 write, ~2.4 µs** |
| **Scroll one line** — what a terminal does | ~2.5 ms | ~0.4 ms | **~0.19 ms** |
| Full 80×25 redraw | ~62 ms, 16 Hz | ~9.5 ms, 105 Hz | **~4.8 ms, 210 Hz** |
| At 9600 baud (~12 lines/s) | 3 % CPU | 0.5 % CPU | **0.23 % CPU** |
| At 115.2 kbaud (~144 lines/s) | 36 % CPU | 5 % CPU | **2.7 % CPU** |
| Screen memory | 128,000 B | 2 KB font + map | **16 KB tiles + a 4 KB map ring** (3,200 B displayed) |
| Glyphs | any, 8bpp | 256, 1bpp + attribute | **256, 8bpp — antialiasing is legal** |

⭐ **The scroll is a register write.** §1.4's cell row is the scan counter's own bits,
so a scrolled line is `VSCROLL += 8` plus the 80 map bytes of the new row — not a
memmove of the map. That matters more than the redraw figure, because a terminal
scrolls and does not redraw: **115.2 kbaud stops being a third of the CPU.**

**The price is that 256 tiles are 256 (glyph, colour) pairs, not 256 glyphs.** The map
byte *is* the cell, so the same glyph in another colour is another code:

- **One fg/bg pair** buys all 256 glyphs — CP437 entire, the CoCo 3 hi-res font, or
  VT100 line drawing, in 16 KB. This is what the mode is for.
- **More pairs** are more banks: `TILEBASE` is five bits, so VRAM holds **32**, and
  switching is one register write — or a display-list `MOVE` at a scanline boundary
  (§4), which makes colour free *per region*. It is never per cell.
- **256-colour ANSI art stays in §2.3's bitmap mode**, where a cell's own colours are
  two of the thirteen writes and already paid for.

Building a bank costs **256 × 13 span-writer writes, ~7.9 ms, once** — one screen's
worth of work to make every later screen thirteen times cheaper.

⚠ **Three bounds.** The mode is **global** (§4, `graphics.md` §6.4.6), so this no more
rescues NitrOS-9 windowing than §2.2 would have. The cell row is five bits, so **32
cell rows** — 80×25 and 80×30 only. And it costs the span writer **half its spare
slots** while it is on, because the map fetch takes the card's one internal address
bus one slot in two (`graphics.md` §6.4.2).

---

## 3. The span writer — what it is

**It is the card's drawing engine, and it is the reason the blitter keeps being
deferred.** `graphics.md` §7.4 is the specification; this is what it does.

### 3.1 The mechanism

The CPU writes a byte to VRAM. The card **latches the address, the data and a
2-bit `WMODE`** into `'574`s (a *posted* write — the CPU never waits), and then the
sequencer retires bytes into VRAM using the memory accesses the display is not using.

| `WMODE` | Mode | What one CPU write produces | Ends when |
|---|---|---|---|
| `00` | **direct** | one byte | the first byte retires |
| `01` | **span-mask** | **8 pixels**, each `WFG` or `WBG` per the mask bit | the eighth byte retires |
| `10` | **span-solid** | **`SPANLEN`+1 pixels**, all one colour | the `'161` pair's terminal count |

**The mask bit never enters the sequencer.** The `74HC165`'s serial output is wired
directly to the register file's address bit 0, so `WFG` sits at `A0 = 0` and `WBG` at
`A0 = 1` and *choosing the colour per pixel costs no macrocell and no product term*.
That placement rule **is** the mechanism, and it is why `graphics.md` §13 pins those
two registers to those two addresses.

`WADV` (`+$14`) chains spans: `01` is **"next row, same column"** — at span end the row
increments and the column reloads from a shadow in the register file. Set it once and a
glyph is *eight mask writes and nothing else*.

### 3.2 What it costs and what it delivers

| | |
|---|---|
| **Solid fill rate** | **25.1 MB/s with §14.2's broadcast write** — four bytes in *one* access: every byte of a solid is the same byte, and `4n`…`4n+3` are the same intra-chip address behind four byte enables. **6.29 MB/s without it** (one byte per 158.9 ns fetch slot — `WPTR` names one interleave at a time; `graphics.md` §7.4). Broadcast is the default once §5.2's rewrite lands (`graphics.md` §19 item 25) |
| **Mask fill rate** | **8 pixels per CPU write** = 3.4 Mpx/s, CPU-bound |
| Setup per span | `WPTR` ×3 + `SPANLEN` + the posted write = **5 writes ≈ 11.9 µs** |
| Full-screen clear, 640×200 | ~500 CPU writes, **~1.2 ms of CPU** — **5.1 ms to retire with broadcast** (20.3 ms without), inside a 14.3 ms frame |
| Hardware cost | the mask serialiser, `SPANLEN` counter and mask counter live in the CPLDs (`graphics.md` §10.1.6), plus `SPANBUSY` |

**The span writer is why bandwidth is not this machine's constraint.** The card has
≈32.4 M spare accesses/s against a CPU that can issue ~420,000 writes/s — **77× more
memory bandwidth than the CPU can consume** (`graphics.md` §2.1). Every drawing figure
below is a CPU figure.

---

## 4. ⭐ What the display list provides — built 2026-09-08

The list engine — the "copper" — is a small sequencer that walks a descriptor list
locked to the raster and writes the card's own registers at chosen scanlines. Its
`MOVE` opcode is one SRAM write into the register file that already exists
(`graphics.md` §10.3).

**What it buys**, all with zero CPU involvement:

- **Per-scanline `HSCROLL`** — parallax layers, sine warps, split-scroll status bars.
- **Per-scanline palette** — raster bars, gradient skies, more than 256 colours on
  screen at once.
- **Mid-frame `CTRL` changes** — §6.4.6 spells out the good one: **a text status bar
  over a bitmap playfield**, because the cell/pixel mode is a register and the list can
  write it at a scanline boundary. ⚠ With §2.2 dropped that bar is Variant A's 8bpp
  tiles rather than a character generator — 16 KB of font instead of 2 KB, and no
  attribute colour path.

> ⚠ **It did not fit v1, and macrocells were not why** (`graphics.md` §10.1.6.2). Both
> packages were fitted and both failed: PLCC-84 aborts with an internal fitter error;
> **TQFP-100 has 80 I/O instead of 64 and still fails.** What ran out was
> **switch-matrix fan-in** — an ATF1508AS logic block admits 40 of ~200 global signals,
> and a 19-bit pointer feeding a six-source 17-bit address mux does not fit through that
> window however many macrocells sit behind it.
>
> ⭐ **Both halves of that sentence were the fix.** Delete the engine's own pointer so it
> **shares `WPTR`** — 19 registers, 19 mux inputs and the mux's *sixth* product term per
> bit, all gone — and drop §2.2's character generator, and it lands on the PLCC-84 the
> card already has: `vaddr` at **64/64 I/O and 102/128 cells**, `vctrl` down to 46/64
> and 87/128. **Zero extra packages.**
>
> ⚠ **Two prices.** The engine **clobbers the CPU's write pointer**, so anything that
> starts a list reloads `WPTR` afterwards — three writes, ~7.1 µs, and a rule software
> has to keep. `graphics.md` §10.3.1 is that rule, and a per-frame list is started once
> in `VBLANK`, so in practice it is **0.05 % of a frame**.
>
> ⭐ **`WPTR` at `+$08`–`$0A` *is* the list pointer** — `LIST` at `+$0B`–`$0D` was
> deleted rather than kept as an alias, because a second address for the same nineteen
> registers is a fiction that invites the very mistake the rule guards against. Three
> register bytes came back.

**What you get instead, today:** VBL and line-compare interrupts (`graphics.md` §12)
give a **software copper at 2–3 splits per frame** — enough for a status bar and a
split scroll, and enough to find out whether the hardware engine is worth its packages
before building it. The line compare is in the CPU module rather than on the card, and
is *better* than the GIME's: any number of compare values, changeable per line, with
HSYNC clocking a timer and VSYNC resetting it for an absolute line number at zero
jitter.

---

## 5. What a blitter would provide

The deferred blit datapath is ~14 ICs and ~10 GALs for **~8.7 Mpx/s**
(`graphics.md` §10.1, §10.2).

**Set against what already exists, its value is narrower than it looks:**

| Operation | Span writer today | Blitter |
|---|---|---|
| Solid fill | **25.1 MB/s broadcast** (6.29 without) | 8.7 Mpx/s — **slower than broadcast** |
| 1bpp mask → 2 colours | 3.4 Mpx/s | 8.7 Mpx/s |
| **8bpp source → destination** | **cannot** | **8.7 Mpx/s** |
| **8bpp with transparency** | **cannot** | **8.7 Mpx/s** |
| Arbitrary 2D rect, source and destination strides | CPU sets up every scanline | in hardware |

**So the blitter still buys mainly one capability class: moving *colour image data*.**
With `graphics.md` §7.4's broadcast write the blitter buys nothing on solid fills.
Two-colour work is a factor of 2.5. Everything the
span writer cannot do at all is in the third and fourth rows — colour sprites, image
copies, off-screen composition of 8bpp artwork — and against `TFM`'s 0.70 Mpx/s that is
a **12×**.

**Why it stays deferred:** ~21 GALs is 1.3–1.8 A of GAL alone on a card already carrying
seven SRAMs, and the span writer plus `TFM` plus tile mode cover most of the gap — a
tilemap redraws itself from the map every frame at zero CPU, so scrolling playfields,
backgrounds and status bars stop being blitter work entirely.

---

## 6. Can the video card perform polygon fills?

**Yes — and this is the span writer's best case, not a workaround.**

A scanline polygon filler decomposes a polygon into one horizontal run per scanline.
That is *exactly* span-solid: the CPU computes the edge intersections and issues
`WPTR` + `SPANLEN` + one write; the card fills the run out of spare memory cycles.

**Cost is 5 CPU writes ≈ 11.9 µs per scanline, independent of how wide the run is**,
until the run gets wide enough that the retire time dominates at **~75 pixels**:

| Average span | Time per span | Effective rate | vs `TFM` |
|---|---|---|---|
| 8 px | 11.9 µs | 0.67 Mpx/s | 1.0× |
| 32 px | 11.9 µs | 2.7 Mpx/s | 3.8× |
| 64 px | 11.9 µs | 5.4 Mpx/s | 7.7× |
| **75 px** | 11.9 µs | **6.29 Mpx/s** | **9×** — the crossover |
| 100 px | 15.9 µs | 6.29 Mpx/s | 9× |
| **300 px** | 47.7 µs, **11.9 µs broadcast** | 6.29, **25.1 Mpx/s** | 9×, **36×** — broadcast's crossover |
| 640 px | 101.7 µs | **6.29 Mpx/s** — memory-bound | 9× |

> The non-broadcast ceiling is 6.29 Mpx/s — one access per slot, `graphics.md` §7.4
> — with the crossover at 75 px; broadcast restores 25.1 Mpx/s and a 300-pixel
> crossover without a blitter. The setup cost is the same either way, so narrow
> spans do not move. Without broadcast the span writer trails the deferred blitter
> (6.29 against 8.7 Mpx/s) but is still **9× `TFM`**, and it covers text, fills,
> clears and scroll refills, which is what `graphics.md` §10.3 defers the blitter
> on.

**What it does not do**: Gouraud or textured fills (the run is one colour), and the edge
stepping is all CPU. A flat-shaded 3D scene of, say, 40 triangles averaging 60-pixel
spans across 25 scanlines each is 1,000 spans ≈ **11.9 ms** — one frame at 70 Hz, with
nothing left over. **Flat-shaded 3D is possible and it is not fast.**

**Convex, axis-aligned and rectangular fills are the sweet spot**, and those are most of
a GUI.

---

## 7. Can we offload QuickDraw-like primitives?

**A specific, well-matched subset — and the match is closer than it has any right to
be.**

| QuickDraw-ish primitive | Offloaded? | How, and what it costs |
|---|---|---|
| **`PaintRect` / `EraseRect`** (solid) | **✅ fully** | span-solid, one span per row. A 200×100 rect is 100 spans ≈ **1.2 ms** |
| **`FillRect` with an 8×8 pattern** | **✅ fully** | ⭐ **span-mask *is* a pattern engine.** A QuickDraw pattern is 8×8 1bpp and a mask byte is one pattern row against `WFG`/`WBG`. Same cost as text: 8 px per write |
| **`CopyBits`, 1bpp source → 2 colours** | **✅ fully** | span-mask, 8 px/write — glyphs, icons, stipples |
| **Horizontal `LineTo`** | **✅ fully** | span-solid |
| **Vertical `LineTo`** | ⚠ partly | `WADV = 10` advances by the row stride, so no address arithmetic per pixel — but still **1 CPU write per pixel** |
| **Diagonal / arbitrary `LineTo`** | ❌ | Bresenham per pixel, ~2.4 µs/px. 640 px ≈ 1.5 ms |
| **`FrameRect`** | ⚠ partly | two horizontal spans free, two vertical edges at 1 write/px |
| **Polygon / `PaintPoly`** | **✅ via scanlines** | §6 |
| **`ScrollRect`, whole screen** | **✅ free** | `VSCROLL`/`HSCROLL`, one register write, no copying |
| **`ScrollRect`, sub-region** | ❌ | needs the blitter; `TFM` per row otherwise |
| **`CopyBits`, 8bpp → 8bpp** | ❌ | `TFM` at 0.70 Mpx/s, or the blitter at 8.7 |
| **`CopyMask` / transparency on colour** | ❌ | the one thing §5 says the blitter is for |
| **Arcs, ovals, regions, clipping** | ❌ | CPU. Clipping is free *at the span level* — clip the run endpoints before writing `SPANLEN` |
| **`TextBox` / glyph runs** | **✅ fully** | span-mask in bitmap mode, or character mode |

**The shape of the answer**: everything that decomposes into *horizontal runs of one or
two colours* is hardware; everything that needs *per-pixel colour from a source image*
is CPU or a blitter. A GUI's fills, frames, patterns, text and scrolling are in the
first group. Its icons and images are in the second.

⚠ **One structural gap for a windowing system**, and `graphics.md` §11 names it: without
VRAM read-back a windowing OS must keep a 128 KB shadow of the screen in system RAM — a
quarter of the machine's 512 KB. **Read-back is specified and built** (§11 reverses
colormin's write-only decision precisely for this), so damage repair, save-behind and
read-modify-write are all available.

---

## 8. Do we have a way to handle sprites?

**No hardware sprites, and none is affordable.** A hardware sprite needs a scan-position
comparator, a shape fetcher and a priority mux *in the pixel path* — and the pixel path
is the tightest timing on the card: `graphics.md` §6.1 gives index → LUT → output
**11.7 ns of margin at a 39.7 ns dot**, and §6.4.6 already spends part of that on the
character serialiser. **A cursor or sprite mux does not fit in what is left.**

Three software routes, and they are very different:

### 8.1 Span-mask sprites — 2 colours, no transparency

A 16×16 sprite is 2 cells wide by 16 rows: 5 writes of setup + 16 mask writes, reload
the column, 3 + 16 more = **40 writes ≈ 95 µs**. That is **4.3× faster than an 8bpp
`TFM`** of the same rectangle.

⚠ **But span-mask writes *both* colours.** A `0` bit writes `WBG`, it does not skip —
so the sprite is an opaque 2-colour rectangle and cannot composite over a background.

### 8.2 `TFM` sprites — full colour, and the honest cost

Flat-mapped VRAM (`graphics.md` §6.3) means the CPU can `TFM` straight into the
framebuffer. A 16×16 sprite is 16 rows of 16 bytes — the rows are not contiguous, stride
is 1024 — so 16 separate `TFM`s ≈ **412 µs**. Transparency needs a per-pixel test, which
`TFM` cannot do, so masked colour sprites fall back to a load/compare/store loop at
roughly **2.5× that**.

### 8.3 The real cost is save-behind, not drawing

Any software sprite over a bitmap must restore what it covered:

| Per 16×16 sprite, per frame | |
|---|---|
| restore the previous position | 412 µs |
| save the new position | 412 µs |
| draw (span-mask) | 95 µs |
| **total** | **~0.92 ms** |

**A 14.27 ms frame at 70 Hz therefore holds about 15 moving 16×16 objects at 100 % CPU,
or 4–6 at a sane 30 %.** Save-behind is 90 % of that, which is the number to attack.

**Tile mode is the way out for backgrounds** — a tilemap regenerates itself every frame
at zero CPU, so nothing needs saving behind — but the sprite cannot then be composited
into it, because in tile mode the map *is* the display.

### 8.4 ⭐ `WMODE 11` — sprite mode, and the span writer becomes a sprite engine

> **BUILT 2026-09-09.** This section was a proposal with an open question at its centre —
> *"whether the mask bit is available at the sequencer"* — and `graphics.md` §7.4 was
> explicit that it is not. Fitting it answered the question: **the mask bit becomes a
> pin, and the part had exactly enough left.** `hardware/gal/seqctl.jedec.ts`,
> `npm run check:seqctl`, and `gal/cpld/vctrl.fit`.

**A fourth `WMODE`. In `11`, a `0` mask bit advances the pointer without asserting the
write strobe**, instead of writing `WBG`.

| `WMODE` | Mode | Length | A `0` mask bit |
|---|---|---|---|
| `00` | direct | 1 byte | — |
| `01` | span-mask | 8 | writes `WBG` |
| `10` | span-solid | `SPANLEN`+1 | — |
| **`11`** | **sprite** | **8** | **writes nothing** |

⭐ **The pointer still advances, and that is the whole mode.** `RETIRE` is unchanged, so
`WPTR` steps, the serialiser shifts and the length counter counts exactly as in mask
mode — only the write is suppressed. A mode that stalled the pointer on a transparent
pixel would draw the sprite squashed, and `check:seqctl` asserts the eight-retired /
four-written case directly.

#### What it buys

**1bpp masked sprites and icons at 8 pixels per CPU write, composited over whatever is
underneath** — and it deletes save-behind for the *mask* case, because nothing outside
the shape is touched.

| 16 × 16 masked sprite | before | **with `WMODE 11`** |
|---|---|---|
| draw | 95 µs (span-mask, but it paints the background too) | **95 µs** |
| save behind | 412 µs | **0** |
| restore | 412 µs | **0** |
| **per move** | **~919 µs** | **~95 µs** |

**An order of magnitude**, and §9's mouse cursor is the case that feels it: 0.92 ms per
move becomes 0.095 ms, so dragging at 70 Hz falls from **6.4 % of the CPU to 0.7 %**.

⚠ **It does not delete save-behind for everything.** A sprite drawn over a *moving*
background still needs the background redrawn, and §5's blitter is still what a general
one wants. What it deletes is the save-and-restore pair for a shape over a **static**
background, which is the mouse cursor, the text caret, icons, and the overwhelming
majority of what a desktop actually moves.

#### What it cost

| | |
|---|---|
| `seqctl`'s logic | **one macrocell** — `WEN`, which is `RETIRE` except a transparent pixel in sprite mode. Three product terms. The part goes 7 → **8 of 10** |
| `SPANEND` | one more term, because sprite mode ends on the cell width like mask mode |
| ⚠ **`vctrl`'s pins** | **two.** `MASKBIT` in, `WEN` out — and `RETIRE` and `WEN` are two signals now where one did both jobs |
| ⚠ **`vctrl`'s cells** | 121 → **122 of 128** |

> ⚠ **AND IT SPENT THE LAST TWO PINS ON THE PART.** `vctrl` was quoted at "64 of 64 I/O"
> everywhere, and that number was never the whole story: an `ATF1508AS` PLCC-84 also has
> **four dedicated input pins** that are not I/O, and two of them were free. The fit is
> now **64/64 I/O *and* 4/4 dedicated** — `cpld/vctrl.fit`, "Design fits successfully".
>
> **Nothing else can be added to `vctrl` at all.** §14.2's consolidation is what returns
> pins: two ×16 framebuffer parts make the arbiter 2 grants instead of 8 and hand back
> six outputs. That was already worth doing; it is now the thing standing between this
> card and its next feature.

#### The question this answered, and it was the right question to ask

§7.4 says the mask bit *"never enters the sequencer"* — the serialiser's serial output is
wired to the register file's address bit 0, and choosing `WFG` or `WBG` per pixel is an
**address line** rather than logic. That is what makes span-mask free.

**Sprite mode needs the same bit in a second place, and a second place is a pin.** The
proposal that stood here estimated "one product term on an existing output plus one
`CTRL` code" and marked the pin question as unknown; the product-term estimate was
right, and the pin question was the whole cost. ⭐ **`check:seqctl` also asserts that
span-mask is *unchanged* by the new input** — a `0` bit still writes `WBG` through the
address line, so the mechanism §7.4 describes is intact and the new mode sits beside it.

---

## 9. Can we handle a mouse cursor with pixel accuracy in bitmap mode?

**Yes, in software, and the cost is comfortable.**

Pixel accuracy is not in question — the framebuffer is chunky 8bpp and flat-mapped, so
a cursor lands wherever the driver puts it, with no cell grid and no colour clash. The
question is what redrawing it costs.

**Save-behind is the right mechanism** and `graphics.md` §11 lists it as one of the five
things VRAM read-back was reversed *for*:

| Per cursor move, 16×16 | |
|---|---|
| restore the old position | 412 µs |
| save the new position | 412 µs |
| draw the shape (span-mask) | 95 µs |
| **total** | **~0.92 ms** |

| | |
|---|---|
| Dragging, redrawn every frame at 70 Hz | **6.4 % of the CPU** |
| Typical pointer motion, ~40 moves/s | **3.7 %** |
| Stationary | **0 %** |

**And it is tear-free for free**, because `graphics.md` §12.1 makes vertical blank the
system tick — move the cursor in the VBL handler and the save, draw and restore all
happen while the beam is off the screen.

**Two alternatives, both worse:**

- **XOR cursor** — no save buffer, but read-modify-write of 256 bytes twice per move is
  **~1.95 ms**, and in 8bpp the XOR of an arbitrary palette index is not reliably a
  visible colour.
- **Hardware overlay** — rejected in §8 above: the pixel path has 11.7 ns of margin and
  a cursor mux does not fit in it.

⚠ **§8.4's transparent-mask proposal would take this to ~95 µs per move, 0.7 % of the
CPU**, because a masked cursor touches only its own pixels and needs no save-behind at
all for the shape — only for the bounding box it leaves behind. It is the single change
that most improves the pointer.

---

## 10. What the card cannot do

Stated plainly, because a capability document that only lists capabilities is a
brochure.

| | Why |
|---|---|
| **Any width but 640** | There is no 320-wide or pixel-doubled mode. `VMODE`'s four codes are all 640 (§1.1), so there is **no 40-column text mode** and no low-resolution mode with cheaper full-screen operations. A 320-wide mode would mean a second fetch cadence — the same class of change as §6.4's tile fetch, so *cheap but not free*, and **nobody has designed it** |
| **Any depth but 8bpp** | No packed 1/2/4bpp modes. A 640×200 screen is 128,000 bytes whatever it contains, so full-screen operations cost the same for a two-colour image as for a photograph |
| **Hardware sprites** | §8 — the pixel path has 11.7 ns of margin |
| **Hardware cursor** | §9, same reason |
| **Per-region mode mixing** | Cell/pixel is global — but ⭐ **the list engine switches it per scanline** (§4), and it is built |
| **A hardware character generator** | ⚠ §2.2, dropped 2026-09-08 to afford the list engine. Text is the span writer at 13 writes/cell (§2.3), or cell mode at 1 write/cell where one colour pair will do (§2.4) |
| **Colour image blits** | §5 — this is the blitter's whole remaining value |
| **A border colour** | `BORDER` was deleted: VGA timing has no overscan, the porches must be black for the back-porch clamp, and the `'153` pixel mux has no spare input (`graphics.md` §9.3) |
| **Palette writes during active display** | They snow. Write during blanking (§1.2) |
| **Per-cell colour in tile mode** | The map byte is the whole cell, so 256 codes are 256 (glyph, colour) pairs. Colour is per *bank* — one register write, or per scanline region from the display list — never per cell (§2.4) |
| **Cell mode at 80×50 or 80×60** | The map's cell row is five bits, so cell mode reaches 32 rows. 640×400 and 640×480 text is the span writer's (`graphics.md` §6.4.1) |

---

## 11. Open items this document raises

These are capability questions, and `graphics.md` §19 does not carry them.

0. **Land §5.2's rewrite so the broadcast write is fitted, not just designed.**
   `graphics.md` §14.2 delivers the mechanism — two ×16 SRAMs, one spare access per
   slot, one grant, four byte enables — giving **25.1 MB/s, a 300-pixel polygon
   crossover, a 5.1 ms full-screen clear and a 10.2 µs `SPANBUSY` bound**; the
   2-grant arbiter and per-chip clocking rewrite is `graphics.md` §19 item 25's
   confirmation. The CPU-bound figures — most of them — do not depend on it.
1. **⚠ Measure the store rate.** Every microsecond figure above scales on
   `graphics.md` §7.3's unverified 5-cycles-per-store. It is `graphics.md` §19 item 1
   and it is the cheapest measurement on the card.
2. **⭐ Fit the transparent span-mask mode** (§8.4). One product term and a `WMODE`
   code on paper; an order of magnitude for sprites and the mouse pointer; and it needs
   the mask bit somewhere §7.4 explicitly does not put it.
3. **The list engine — decided and built 2026-09-08**: the engine shares `WPTR`
   and §2.2's character generator came out to pay for it. The shared pointer means
   a list clobbers `WPTR`; `graphics.md` §10.3.1 carries the reload rule.
4. **Nobody has costed a 320-wide mode** (§10), and it is the cheapest way to halve the
   cost of every full-screen operation.
5. **The software-sprite budget has never been measured**, only computed (§8.3). Four
   to six objects is an arithmetic claim.

---

## 12. Cross-references

| | |
|---|---|
| [`graphics.md`](graphics.md) | the card. §2.1 bandwidth, §6.1–6.4 geometry and modes, §7.4 the span writer, §10 blitter and list engine, §11 read-back, §12 interrupts, §13 the register map |
| [`../../docs/machine.md`](../../docs/machine.md) | §1 the clock tree every timing here derives from, §2 the backplane, §3 the `$FF60`–`$FF7F` window |
| [`../../docs/video-comparison.md`](../../docs/video-comparison.md) | this card against the GIME and the VIC-II |
| [`../../hardware/gal/`](../../hardware/gal/) | `tile.check.ts` (the no-adder property), `seqctl.check.ts` (the 13 writes per cell), `vctrl.pld` (the fitted sequencer and arbiter) |
