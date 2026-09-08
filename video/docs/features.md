# What the Video Card Can Actually Do

## Modes, the Span Writer, and Nine Questions About Drawing

**Question this answers:** [`graphics.md`](graphics.md) is 3,100 lines of *why* — why
640 wide, why the LUT is 32K×8, why the list engine does not fit. It is organised
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

---

## 0. Capability summary

| | |
|---|---|
| **Bitmap** | **640×200, 640×240, 640×400, 640×480 — all 8bpp**, 256 simultaneous colours from 65,536 (RGB565 LUT). §1 |
| **Text** | **80×25, 80×30, 80×50, 80×60**, 8×8 cells. **Any of 256 attributes → any RGB565 foreground/background pair.** §2 |
| **Tiles** | 8×8, **8bpp per pixel — no attribute clash**, 64:1 write compression. §1.4 |
| **Colour depth** | 8bpp everywhere. There is **no 4bpp, 2bpp or 1bpp packed mode** and no 320-wide mode. §10 |
| **Scrolling** | **Free, both axes, pixel-accurate**, by register — a 1024 × 512 ring. §1.3 |
| **Buffers** | 512 KB of VRAM = **four full 640×200 screens**. Double and triple buffering are free. §1.2 |
| **Span writer** | the card's drawing engine: **6.29 MB/s solid fill today, 25.1 MB/s if `graphics.md` §7.4's broadcast write is built**, 8 pixels per CPU write in mask mode. §3 |
| **Polygon fills** | **Yes** — scanline decomposition in the CPU, spans in hardware. **0.7 to 6.3 Mpx/s depending on span width.** §6 |
| **QuickDraw offload** | **`PaintRect`, pattern fills, glyph blits, horizontal spans and scroll: yes.** Lines, arcs, regions, colour image copies: no. §7 |
| **Sprites** | **No hardware sprites.** Software costs ~0.9 ms per 16×16 sprite per frame, so **4–6 moving objects**. §8 |
| **Mouse cursor** | **Yes, pixel-accurate in bitmap mode** — save-behind, **~0.9 ms per move, 6.4 % of the CPU while dragging and 0 % when still.** §9 |
| **Raster effects** | VBL + line-compare interrupts give a **software copper at 2–3 splits/frame** today. §4 |
| ⚠ **Display list** | **Specified, and it does not fit v1** — not on macrocells, on switch-matrix fan-in. §4 |
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
by showing OR equals ADD over all 524,288 field combinations.

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

### 2.2 Character mode — 256 attributes, each an arbitrary colour pair

`CTRL` b2 `CHAR` with b5 `CELL` selects a 1bpp character generator. Its colour path is
**the 127/128 of the palette LUT that the 256-entry palette does not use**
(`graphics.md` §6.4.3):

```
graphics :  LUT[ 0 | 0000000 | pixel[7:0] ]        -> RGB565
text     :  LUT[ 1 | 000000  | attr[7:0] | bit ]   -> RGB565
```

No comparator, no foreground/background mux, no second colour path — the attribute byte
rides the existing pixel bus and the glyph bit is one spare LUT address pin.

| | GIME text | **This card** |
|---|---|---|
| Attribute combinations | 8 fg × 8 bg | **256, freely defined** |
| Colour space per attribute | 64 | **65,536** |
| Foreground / background | palette entries 0–7 | **any RGB565 pair** |

**Cost per cell: 2 CPU writes (code + attribute), ~4.8 µs.** A full 80×25 redraw with
per-cell colour is **~9.5 ms**; a line scroll is **~0.4 ms**.

### 2.3 Text in bitmap mode, for when you need both

Character mode is **global** — cells or pixels, not both in one region (`graphics.md`
§6.4.6). When a program needs text *over* graphics it renders glyphs into the bitmap
with the span writer instead:

| | Character mode | Span writer, in bitmap mode |
|---|---|---|
| One cell | 2 writes, ~4.8 µs | **13 writes, ~31 µs** |
| Scroll one line | ~0.4 ms | **~2.5 ms** |
| Full 80×25 redraw | ~9.5 ms | ~62 ms |

**A terminal never full-redraws** — it scrolls, and 2.5 ms plus one register write is
comfortable. The 13 writes are `WPTR` ×3 + `WFG` + `WBG` + eight glyph rows, and
`npm run check:seqctl` asserts the 13.

> **Both are ~3× better than the obvious alternative.** A `TFM` of a pre-rendered
> 8×8×8bpp glyph is 64 bytes at 3 cycles each ≈ 92 µs per cell, because `TFM` moves one
> pixel per cycle-triple and the span writer moves eight pixels per CPU write.

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
| **Solid fill rate** | **6.29 MB/s** — ⚠ ~~25.1~~. **One** byte per 158.9 ns fetch slot: `WPTR` names one of the four interleaved chips at a time and two accesses do not fit the 86.9 ns of slack. `graphics.md` §7.4. ⭐ **25.1 MB/s with §7.4's broadcast write**, which retires four bytes in *one* access rather than four — every byte of a solid is the same byte, and `4n`…`4n+3` are the same intra-chip address on four chips |
| **Mask fill rate** | **8 pixels per CPU write** = 3.4 Mpx/s, CPU-bound |
| Setup per span | `WPTR` ×3 + `SPANLEN` + the posted write = **5 writes ≈ 11.9 µs** |
| Full-screen clear, 640×200 | ~500 CPU writes, **~1.2 ms of CPU and ~20.3 ms to retire** (~~5.1~~) — **5.1 ms with broadcast**, back inside a 14.3 ms frame |
| Hardware cost | `74HC165`, `74HC161` ×2, 3 macrocells of mask counter, and `SPANBUSY` |

**The span writer is why bandwidth is not this machine's constraint.** The card has
≈32.4 M spare accesses/s against a CPU that can issue ~420,000 writes/s — **77× more
memory bandwidth than the CPU can consume** (`graphics.md` §2.1). Every drawing figure
below is a CPU figure.

---

## 4. What the display list would provide

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
  write it at a scanline boundary.

> ⚠ **It does not fit v1, and macrocells are not why** (`graphics.md` §10.1.6.2). Both
> packages were fitted and both failed: PLCC-84 aborts with an internal fitter error at
> 90 % logic and 95 % pins; **TQFP-100 has 80 I/O instead of 64 and still fails at 90 %
> logic.** What runs out is **switch-matrix fan-in** — an ATF1508AS logic block admits
> 40 of ~200 global signals, and a 19-bit pointer feeding a six-source 17-bit address
> mux does not fit through that window however many macrocells sit behind it.
>
> Three ways forward, none free: a third CPLD; let the engine share `WPTR` (19 registers
> and most of the fan-in saved, but it clobbers the CPU's write pointer — a
> specification decision, not a fitting one); or leave it out, which is what v1 does.

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
| Solid fill | **6.29 MB/s**, 25.1 broadcast | 8.7 Mpx/s — ⚠ *faster* today, ~~slower~~; **slower than broadcast** |
| 1bpp mask → 2 colours | 3.4 Mpx/s | 8.7 Mpx/s |
| **8bpp source → destination** | **cannot** | **8.7 Mpx/s** |
| **8bpp with transparency** | **cannot** | **8.7 Mpx/s** |
| Arbitrary 2D rect, source and destination strides | CPU sets up every scanline | in hardware |

**So the blitter still buys mainly one capability class: moving *colour image data*.**
⚠ **It also buys 38 % on solid fills**, which the 25.1 MB/s figure hid — that row read
*"slower"* until 2026-09-08. ⭐ **`graphics.md` §7.4's broadcast write takes that back
for one wide product term and a by-four counter**, at which point the blitter buys
nothing on solid fills again. Two-colour work is a factor of 2.5. Everything the
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

> ⚠ **Corrected 2026-09-08, and downward.** This table read 8.4 Mpx/s at 100 px and 25.1
> at 640, from a fill rate that assumed the span writer took all four chips' spare
> accesses in a slot. It takes one — `graphics.md` §7.4. **The setup cost is unchanged,
> so narrow spans do not move**; what moves is the ceiling, 25.1 → 6.29, and the
> crossover, 300 px → 75.
>
> **The span writer no longer beats the deferred blitter** — 6.29 Mpx/s against 8.7 — but
> it is still **9× `TFM`**, and it still covers text, fills, clears and scroll refills,
> which is what `graphics.md` §10.3 defers the blitter on. §5's conclusion is unchanged
> in kind and narrower in margin.
>
> ⭐ **And §7.4 proposes getting the 4× back** — broadcast writes, which restore 25.1
> Mpx/s and a 300-pixel crossover without a blitter. The row above shows both.

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

### 8.4 ⭐ One change would make the span writer a real sprite engine

**Proposal, not specification.** Add a fourth `WMODE`: **span-mask-transparent**, where
a `0` mask bit **advances the pointer without asserting `/WE`** instead of writing
`WBG`.

- **What it buys:** 1bpp masked sprites and icons at **8 pixels per CPU write, composited
  over whatever is underneath** — and it deletes save-behind for the *mask* case, because
  nothing outside the shape is touched. A 16×16 masked sprite becomes ~95 µs against
  ~1,000 µs, an order of magnitude.
- **What it costs:** the retire logic already computes `RETIRE = SPANBUSY · SPNGRANT`
  and already routes the mask bit to the register file's `A0`. Suppressing `/WE` on a
  `0` bit is **one product term on an existing output plus one `CTRL` code** — `WMODE`
  has a free encoding at `11`, and `seqctl` is the roomiest GAL on the card at **7
  macrocells of 10 and 8 of 14 input pins**.
- ⚠ **What is unknown:** whether the mask bit is available at the sequencer at the right
  moment. §7.4 is explicit that *"the mask bit never enters the sequencer"* — it goes
  straight to the register file's address pin — so this proposal **needs it in a second
  place**, and that is a real input-pin and timing question, not a formality. **Fit it
  before believing this paragraph.**

This is the highest-value cheap change this document found, and it is recorded as an
open item rather than a decision.

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
| **Per-region mode mixing** | Cell/pixel is global. A list engine could switch it *per scanline* (§4), and the list engine does not fit v1 |
| **Colour image blits** | §5 — this is the blitter's whole remaining value |
| **A border colour** | `BORDER` was deleted: VGA timing has no overscan, the porches must be black for the back-porch clamp, and the `'153` pixel mux has no spare input (`graphics.md` §9.3) |
| **Palette writes during active display** | They snow. Write during blanking (§1.2) |
| **Fine horizontal scroll in tile mode** | Needs a 3-bit offset into the tile row — new logic in the address concatenation, not the free `HSCROLL` of bitmap mode (`graphics.md` §6.4.6) |

---

## 11. Open items this document raises

These are capability questions, and `graphics.md` §19 does not carry them.

0. **⚠ CORRECTED 2026-09-08 — the fill rate was 4× too high.** Every figure that depended
   on the span writer's *memory* bound has moved: 25.1 → **6.29 MB/s**, because `WPTR`
   names one interleaved chip at a time. `graphics.md` §7.4 has the derivation, and §7.3's
   own full-screen-clear row was wrong the same way. **The CPU-bound figures did not
   move**, which is most of them.

   ⭐ **And §7.4 proposes getting the 4× back the same day** — *broadcast writes*: in
   span-solid every byte is the same byte and four consecutive addresses are one
   intra-chip address on four chips, so a quad needs one address, one data byte and four
   `/WE`. **25.1 MB/s, a 300-pixel polygon crossover, a 5.1 ms full-screen clear and a
   10.2 µs `SPANBUSY` bound.** ⚠ **It is a proposal, not a build**: the arbitration is
   real work, because during a `/WAIT` stall only three chips are free and the span
   writer has to learn how many it got. Every figure in this document is the **today**
   figure unless it says otherwise.
1. **⚠ Measure the store rate.** Every microsecond figure above scales on
   `graphics.md` §7.3's unverified 5-cycles-per-store. It is `graphics.md` §19 item 1
   and it is the cheapest measurement on the card.
2. **⭐ Fit the transparent span-mask mode** (§8.4). One product term and a `WMODE`
   code on paper; an order of magnitude for sprites and the mouse pointer; and it needs
   the mask bit somewhere §7.4 explicitly does not put it.
3. **Decide the list engine's three options** (§4). Sprites, splits and mid-frame mode
   changes all wait on it, and `graphics.md` §10.1.6.2 leaves the choice open.
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
