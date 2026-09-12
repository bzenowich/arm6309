# Three Video Cards For One Slot

## What each does, what each costs, and which one to build

**Question this answers:** the project now has three video designs —
[`video/`](../video/) as specified and fitted, [`video2/`](../video2/) as planned, and a
sprite-less RGB332 derivative of the VIC-II extended to 80 columns. They are not three
versions of one card; they are three different answers, and the differences are
mostly *not* the ones the names suggest. This document compares them on features first
and cost second.

> This is a **comparison**, not a specification. `video/docs/graphics.md` and
> `video2/plan.md` are the owning documents for their cards; the VIC-II derivative has
> no document of its own and this is currently it.
>
> ⚠ **Two numbers here supersede figures quoted in conversation.** Every package count
> and every area below is measured from **one** parts list through
> `hardware/place/pack.ts`, so that the three cards cannot be compared across different
> BOM generations. Earlier VIC-II figures of "43 / 40 packages" and "fits a 180 mm
> board" came from an earlier list with one fewer control-store flash, and are
> withdrawn — see §3.1.

---

## 0. The three cards

| | [`video/`](../video/) | [`video2/`](../video2/) | **VIC-II, extended** |
|---|---|---|---|
| **Shape** | 8bpp chunky framebuffer with a drawing engine | microcoded, fixed-palette, hardware text | character/bitmap card, 1bpp + per-cell colour |
| **Programmable logic** | 3 × `ATF1508AS` | none, or 2 × `GAL22V10` | none, or 2 × `GAL22V10` |
| **Colour** | 256 of 65,536, **per pixel** | 256 fixed, **per pixel** | 256 fixed, **two per 8×8 cell** |
| **80×25 text** | 13 CPU writes/cell | **4 writes/cell, in hardware** | **4 writes/cell, in hardware** |
| **Graphics** | 640×480 8bpp | 640×480 8bpp | 320×200, 1bpp + cell colour |
| **Packages** | **33** | **59** text *or* bitmap, **67** both | **50** |
| **With 2 GALs** | — | 53 / 53 / **61, still does not place** | **44** |
| **240 mm board** | places, 59 % | text places; bitmap and dual **do not** | **places, 70 %** |
| **Status** | fitted, simulated, draws a real frame | planned; nothing built | sketched; nothing built |

⭐ **The result that decides most of this document:** the VIC-II derivative is the only
one of the three that puts **text and graphics on one board with no programmable logic
and still places.** `video2` doing both is eleven packages over, and two GALs do not
close it.

---

## 1. Why they are three shapes and not three sizes

**The cost of a video card here is bytes per second across its busiest bus**, and the
three designs sit at very different points on that ladder. Everything else follows.

| Design | Display fetch, per 8-dot cell | Busiest bus |
|---|---|---|
| A real VIC-II, 40 col | 1 glyph byte, plus a 12-bit matrix word **once per 8 lines** | **~1.2 MB/s** |
| VIC-II extended, 80 col | 4 cell bytes on one bus, 1 glyph byte on **another** | **12.6 MB/s** |
| `video2` text | 4 cell bytes + 1 glyph byte, one memory system | 15.7 MB/s |
| `video/`, `video2` bitmap | **8 pixel bytes** | **25.2 MB/s** |

⭐ **8bpp chunky is what costs the packages, not the features.** At 640 wide and one
byte per pixel a cell is eight bytes every line, and that single number forces two ×16
SRAMs, a 32-bit pixel bus, two ranks of fetch latches, a 4:1 pixel mux at dot rate and
a 4:1 read mux to get one byte back to the CPU. That is roughly **nineteen packages**
which a card carrying colour *per cell* never needs.

**The VIC-II's answer is to spend colour resolution instead of bandwidth.** One bit per
pixel and two colour bytes per 8×8 cell is 4 bytes per cell against 8, and splitting the
glyph onto its own bus halves the worst bus again. It buys back the packages exactly
where `video2` spends them.

⚠ **And the VIC-II's own trick does not transfer.** Its 40×12-bit line buffer exists
because 40 c-accesses plus 40 g-accesses do not fit in 63–65 bus cycles per line
(`reference/articles/VIC-Article.txt` §3.5). The extended card has **four access
windows per cell against a display demand of two**, so that shortage never arises and
a line buffer would move where the bytes come from without reducing how many are
needed.

---

## 2. Features

### 2.1 Geometry and modes

| | `video/` | `video2` | VIC-II ext. |
|---|---|---|---|
| 640×200 @ 70 Hz | ✅ | ✅ | ✅ |
| 640×240 @ 60 Hz | ✅ | ✅ | ✅ |
| 640×400 @ 70 Hz | ✅ | ✅ | ✅ |
| 640×480 @ 60 Hz | ✅ | ✅ | ✅ |
| 320-wide mode | ❌ never costed | ❌ | ✅ **native**, pixel-doubled |
| Mode timing lives in | fitted product terms | **a ROM table** | **a ROM table** |
| Sync polarity per mode | 10 product terms (§6.2.1) | **a bit in the table** | **a bit in the table** |

⭐ **All three reach all four VGA modes**, and for the two ROM-table designs a mode
costs bytes rather than logic — which is also why line doubling and the end-of-frame
reset stop being compare logic.

### 2.2 Colour

| | `video/` | `video2` | VIC-II ext. |
|---|---|---|---|
| Simultaneous colours | **256 of 65,536** | 256 fixed | 256 fixed |
| Granularity | **per pixel** | **per pixel** (bitmap), per cell (text) | **two per 8×8 cell** |
| Palette LUT | 256 × 16 b RGB565, programmable | none | none |
| Palette effects (fades, cycling, gradients) | ✅ | ❌ | ❌ |
| Exactly neutral greys | **all 24** | 2 | 2 |
| Worst cube error | 3.7/255 | **40/255** | **40/255** |
| Dot-path margin in a 39.72 ns dot | **11.7 ns** | **~25 ns** | **~25 ns** |

⚠ **The fixed palette is a real loss and it is confined to one thing: gradients.** With
a 4-level blue grid and an 8-level red/green grid the two coincide only at 0 and 255, so
no interior grey is truly grey — photographs and dithered greyscale show it. **The 16
ANSI colours land within half a step**, so CP437 art does not. `graphics.md` §9 argues
the other way for a general-purpose card and is right to.

⭐ **What the two fixed-palette cards get back is the card's tightest timing path.**
`graphics.md` §6.1 gives index latch → 15 ns LUT → output latch 11.7 ns of margin, and
`features.md` §8 and §9 both cite that margin as the reason a hardware sprite, a
hardware cursor and a border are impossible. Deleting the LUT roughly doubles it.

### 2.3 Text

| | `video/` | `video2` | VIC-II ext. |
|---|---|---|---|
| Mechanism | span writer into the bitmap | **hardware character generator** | **hardware character generator** |
| CPU writes per cell | **13** (or 1 in cell mode) | **4** | **4** |
| Full 80×25 redraw | ~62 ms (4.8 ms cell mode) | **~19 ms** | **~19 ms** |
| Scroll one line | ~2.5 ms (0.19 ms cell mode) | **~0.77 ms**, or one register write | **~0.77 ms**, or one register write |
| At 115.2 kbaud | 36 % CPU (2.7 % cell mode) | **11 %** | **11 %** |
| Per-cell colour | ✅ 256, costs 2 of 13 writes | ✅ **fg and bg bytes** | ✅ **fg and bg bytes** |
| Programmable character set | ⛔ **no** — §6.4.3 dropped | ✅ **4 banks × 256 glyphs** | ✅ font RAM |
| 80×50 / 80×60 | ✅ span writer | ✅ 64-row ring | ✅ at 640×400 |
| 8×16 glyphs | n/a | one more font address bit | one more font address bit |

⚠ **Every microsecond above scales on `graphics.md` §7.3's unverified 5 cycles per
store**, which §19 item 1 says the repository cannot settle. It is the cheapest
measurement available on any of the three.

⭐ **`video/`'s cell mode is faster than either hardware generator** at one write per
cell — but it buys that by making the map byte the whole cell, so 256 codes are 256
(glyph, colour) **pairs**, it is capped at 32 rows, and a second colour pair is a
second 16 KB bank. The two hardware generators give per-cell colour from 256 at four
writes and no bank switching.

### 2.4 Graphics and drawing

| | `video/` | `video2` | VIC-II ext. |
|---|---|---|---|
| Drawing engine | ✅ **span writer**, 4 modes | ❌ **not in v2.0** | ❌ |
| Solid fill | 6.29 MB/s (25.1 with broadcast) | `TFM`, ~0.70 MB/s | `TFM`, ~0.70 MB/s |
| Full-screen clear | ~1.2 ms CPU | ~183 ms (bitmap), ~11 ms (text) | ~11 ms |
| 1bpp mask → 2 colours | ✅ 8 px per write | ❌ | ❌ |
| Masked sprite assist | ✅ `WMODE 11` | ❌ | ❌ |
| Tile mode | ✅ 8×8, 8bpp, 64:1 compression | ❌ | the text mode **is** the tile mode |
| Display list | ✅ `MOVE`/`WAIT`/`END` | ❌ | ❌ |
| Blitter | deferred | deferred | deferred |

⛔ **This row is where `video/` is simply ahead**, and it is not close. The span writer
is the reason that card's text, fills, clears and scroll refills are cheap, and both
other designs give it up. On a card whose documented bottleneck is the CPU
(`graphics.md` §2.1), that matters more than the package count suggests.

### 2.5 Scrolling

| | `video/` | `video2` | VIC-II ext. |
|---|---|---|---|
| Horizontal | **byte-granular**, 1024-column torus | **byte-granular** | fine, 0–7 px, by shifter delay |
| Vertical | pixel, 512-row torus | pixel / cell | cell + fine |
| Cost of a scroll | one register write | one register write | one register write |
| Per-scanline scroll | ✅ from the display list | ❌ | ❌ |

### 2.6 Host interface

| | `video/` | `video2` | VIC-II ext. |
|---|---|---|---|
| VRAM as seen by the CPU | **a pointer port** at `WPTR`, plus `VDATA` | **flat memory** | **flat memory** |
| Random access | 3 stores to reload the pointer | a store at the address | a store at the address |
| `TFM` into VRAM | via the port | ✅ **directly** | ✅ **directly** |
| VRAM readable | ✅ prefetched | ✅ | ✅ |
| **Stalls the CPU** | ⚠ **yes, up to 40.7 µs** | ⭐ **never** | ⭐ **never** |
| Window | `$FF60`–`$FF7F` | same | same |

⭐ **Flat addressing is the quiet win of both newer designs.** It deletes the 19-bit
pointer, the posted-write latch, the prefetch and its invalidation rules, the `WPTR`
reload rule software must keep, and with them most of `graphics.md`'s 2026-09-10 defect
list. What it costs is a read mux and about 27 ns of in-cycle margin, at ÷12 only.

### 2.7 Interrupts and raster effects

| | `video/` | `video2` | VIC-II ext. |
|---|---|---|---|
| VBL interrupt | ✅ on card | ✅ on card | ✅ on card |
| Raster compare | in the **CPU module** | in the CPU module | ⭐ **on the card**, `'688` pair |
| Raster splits with no CPU | ✅ the display list | ❌ | ❌ |
| `HSYNC`/`VSYNC` to the CPU slot | ✅ required | ✅ required | ✅ |

⭐ The VIC-II derivative is the only one that keeps raster compare **on the card**,
which is its own heritage — and it costs three packages to do what the CPU module
already does for free on the other two.

### 2.8 What each cannot do

| `video/` | `video2` | VIC-II ext. |
|---|---|---|
| no hardware character generator | no drawing engine | **no colour per pixel** |
| no 320-wide mode | no tile mode | no 640-wide graphics |
| cell mode capped at 32 rows, one colour pair | no display list | no drawing engine, no display list |
| palette writes snow during display | no palette effects | no palette effects |
| stalls the CPU up to 40.7 µs | **both modes will not fit one board** | no sprites (deleted by choice) |
| no hardware sprites or cursor | no hardware sprites or cursor | no hardware sprites or cursor |

---

## 3. Cost

### 3.1 Packages and board, measured

From one parts list through `hardware/place/pack.ts`, on the 100 × 240 mm board:

| Design | Packages | Courtyard | 240 mm |
|---|---|---|---|
| `video/`, 3 × `ATF1508AS` | **33** | 124.4 cm² | places, 59 % |
| `video2` text, no PLD | 59 | 166.7 cm² | places, 79 % |
| `video2` text, 2 GALs | 53 | 153.3 cm² | places, 73 % |
| `video2` bitmap, no PLD | 59 | 166.1 cm² | ⛔ **3 over** |
| `video2` bitmap, 2 GALs | 53 | 152.7 cm² | places, 73 % |
| `video2` both, no PLD | 67 | 185.9 cm² | ⛔ **11 over** |
| `video2` both, 2 GALs | 61 | 172.5 cm² | ⛔ **5 over** |
| VIC-II 40 col, no PLD | 44 | 128.1 cm² | places, 61 % |
| VIC-II 40 col, 2 GALs | **38** | 115.2 cm² | places, 55 % |
| **VIC-II 80×25, no PLD** | **50** | 147.6 cm² | **places, 70 %** |
| **VIC-II 80×25, 2 GALs** | **44** | 134.7 cm² | **places, 64 %** |

⚠ **Nothing here fits a 180 mm board**, including the 40-column VIC-II at 38 packages.
An earlier figure said it did; that BOM carried one control-store flash where this one
carries two, and a second DIP-32 on a 0.6" body is what the 180 mm skyline refuses.
**The board length is set by the largest packages, not by the count.**

⭐ **In this architecture text and bitmap cost the same — 59 each — and only having
both costs more.** The character generator and the 8bpp fetch path are alternatives of
similar size; the extra eight packages in the dual card are the concatenation mux that
remaps counter bits between two address schemes, plus the font path riding on top of
the wider pixel path.

### 3.2 Programmable logic

**Two `GAL22V10` are worth six packages on either discrete design**, because a 22V10
macrocell carries its own product-term output enable: the counter becomes its own bus
driver and the `'244` rank leaves with the `'163`s. Five plus three packages become
two. `video/`'s own archived GAL build spent exactly two on the scan address.

⚠ **A 22V10 is 1986** — older than the 74AHCT the dot path requires and far older than
the framebuffer. On the period axis the GALs make either card *more* honest, not less.
The rule against them is a style rule, and the root [`README.md`](../README.md) retired
the machine-wide version of it on that argument.

### 3.3 Power — ⚠ estimated, none of it measured

| | |
|---|---|
| `video/` | **0.5–0.85 A, 0.65 A nominal** — `graphics.md` §14.1, derived from datasheets |
| The discrete designs | ⚠ **no honest figure exists.** Order-of-magnitude: ~15 AHCT packages at dot rate at 9–22 mA plus ~35 HCT at bus rate at 2–6 mA plus three flash and the SRAM — call it **0.4–0.9 A** and design for 1 A |

⚠ **Do not assume the discrete cards are lighter because they have no CPLDs.** Three
`ATF1508AS` in reduced-power mode are ~300–360 mA; fifty 74-series packages are
plausibly the same or more. **This is the least-supported comparison in the document**
and it wants a measurement on each.

---

## 4. Period standing

| | `video/` | `video2` | VIC-II ext. |
|---|---|---|---|
| Architecture dates to | 1989–90 | 1988–90 | **1982–85** |
| Newest part class | `AS6C8016` ×16 SRAM, ~1995 | same, plus flash (~1988 as a class) | same |
| Programmable logic | CPLD — 1988 as an architecture | none, or GAL (1986) | none, or GAL (1986) |
| Microcode in ROM | — | **1964**, universal by 1975 | — |
| Character generator with a RAM font | — | 1982 (EGA) | **1982** |

⭐ **The VIC-II derivative is the most period-plausible of the three by a wide margin**,
which is unsurprising: it is a 1982 architecture with its colour path widened. What
keeps all three outside a strict 1989 is the same two parts — the ×16 SRAM and the
flash — and `graphics.md` §15 already books that knowingly.

---

## 5. What the VIC-II article settled, and what it did not

`reference/articles/VIC-Article.txt` (Christian Bauer, 2024-09-29) is the primary
source for the third column, and it confirmed every figure this comparison rests on:
the 8.18/7.88 MHz pixel clock and eight pixels per bus cycle, so a cell is **977.5 ns**;
63/64/65 cycles per line; 40×25 with 8×8 cells; the 1K×4 colour RAM on `D8`–`D11`; the
40×12-bit line buffer; and the VC/VCBASE/RC/VMLI counter model, which §3.7.2 states was
chosen over "a more elaborate one with a +40 adder". §3.8.1 confirms the per-sprite
state component by component.

⛔ **It contains no die-area, chip-area or transistor data of any kind**, and §1 says
plainly that no VIC schematics are available. **So "the sprite engine is the largest
block by chip area" is unverified here**, and the discrete estimate that follows from
it — that eight sprites would be **~100 packages**, more than the rest of the card — is
arithmetic from the per-sprite state list, not from silicon.

---

## 6. How to choose

**If the machine wants one general-purpose video card and CPLDs are acceptable:**
build `video/`. It is 33 packages, it is fitted, it is simulated, it draws a real frame
out of its own boot ROM, and it is the only one of the three with a drawing engine. The
other two are more interesting on paper and neither has run.

**If the goal is ANSI text and programmable logic is refused:** the VIC-II derivative
at **50 packages** beats `video2` at 67, places where `video2` does not, and gives the
same 4-writes-per-cell hardware text with a programmable character set. The price is
graphics: two colours per 8×8 cell instead of 256 per pixel.

**If 8bpp chunky graphics are non-negotiable and CPLDs are refused:** build `video2` as
**one mode or the other**, with two GALs, at 53 packages. Both modes on one board is
eleven over and two GALs do not close it; that decision has to be taken before anything
is drawn.

⚠ **And if the answer is "both modes, no CPLDs, one board" — that card does not exist
yet.** The options are a two-board set, more GALs than either analysis contemplates, or
accepting the VIC-II derivative's cell colour.

---

## 7. Open items

1. ⚠ **Nothing but `video/` has been fitted, simulated or benched.** `graphics.md`'s
   three worst defects were found by executing an instruction, not by reading a
   schematic, and neither new design has executed anything.
2. ⚠ **The store rate.** Every CPU-cost figure in §2.3 scales on `graphics.md` §7.3's
   unverified 5 cycles per store — `graphics.md` §19 item 1.
3. ⚠ **Power on the discrete designs** (§3.3) is an order-of-magnitude guess.
4. **Neither new design is in `hardware/place/parts.ts`.** Until each has an entry and
   a board file with an `icBudget`, `npm run check:place` asserts none of §3.1.
5. **The VIC-II derivative has no specification.** This document is the only account of
   it; the register map, the microword and the fetch cadence are unwritten.
6. ⚠ **The 27 ns CPU-read margin** both flat-addressed designs depend on is derived
   from a fixed alignment between `E` and the fetch slot, and closes at ÷12 only.

---

## 8. Sources

| | |
|---|---|
| [`video/docs/graphics.md`](../video/docs/graphics.md) | the first card: §2.1 bandwidth, §6.1–6.4 geometry and modes, §7 text and the span writer, §9 the palette argument, §10.3 the display list, §11 readable VRAM, §14 the budget, §15 the period audit |
| [`video/docs/features.md`](../video/docs/features.md) | the same card by capability — §2 text, §3 the span writer, §8 sprites, §10 what it cannot do |
| [`video2/plan.md`](../video2/plan.md) | the second card, and §11 its budget |
| [`video2/bitmap-datapath.pdf`](../video2/bitmap-datapath.pdf) | its bitmap datapath drawn subsection by subsection, with the recount that moved 62 to 67 |
| [`reference/articles/VIC-Article.txt`](../reference/articles/VIC-Article.txt) | Christian Bauer on the VIC-II — §3.1 the block diagram, §3.4 geometry, §3.5 Bad Lines, §3.6 access types, §3.7.2 VC and RC, §3.8 sprites |
| [`docs/video-comparison.md`](video-comparison.md) | ⚠ **a different comparison** — `video/` against the GIME and the real VIC-II, rather than these three against each other |
| `hardware/place/pack.ts` | every package count and area in §3.1 |
