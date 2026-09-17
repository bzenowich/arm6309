# video3 — a console-first video card

## Character mode with attributes, bitmap mode with a span writer, and nothing that draws itself

**DRAFT, 2026-09-16.** ⚠ **Nothing in this document is fitted, placed, simulated or
costed.** It is a specification to be attacked, not a build. Every number is either
inherited from [`video/docs/graphics.md`](../../video/docs/graphics.md) with its
section cited, or derived here and marked. §14 lists what would refute each load-
bearing claim, and §15 is the verification this card would need before a board.

> ⛔ **NO UTILISATION FIGURE FROM `video/`'s FIT APPLIES TO THIS CARD, and an earlier
> draft of this document broke that rule.** `hardware/gal/cpld/*.fit` describes three
> parts carrying a display list, per-scanline scrolling, a one-byte map and no copy
> engine. **video3 has none of those and has no `vaddr`.** What transfers is
> *mechanism* — how an address is concatenated, why `WFG` must be even, what a fetch
> slot costs — and *arithmetic* that depends only on the timing and the parts.
> **Cell counts, fan-in and "which part has room" transfer nothing**, and quoting them
> here reads as a finding when it is a category error.
>
> ⚠ **`npm run check:docs` will not catch this.** It compares a utilisation figure
> against the fitter and passes it when the number is right — it cannot tell that the
> number was cited about a different design. That is the same blind spot its own header
> records: *"it cannot catch a paragraph that describes a mechanism the design no longer
> has."*

> **This is a third card, not a revision of the first.** `video/` is fitted,
> simulated and boots NitrOS-9; `video2/` is a microcoded alternative;
> [`docs/video-options.md`](../../docs/video-options.md) compares them. **video3
> starts from the requirement rather than from `video/`'s parts list**, and §11 is
> the component-by-component record of what was re-adopted and *why* — nothing is
> inherited because it exists.

---

## 0. The requirement

| | |
|---|---|
| **Character mode** | 80×25 / 30 / 50 / 60, **per-cell colour**: 16-colour ANSI with CP437, or 256 (fg, bg) pairs chosen from 65,536 |
| **Bitmap mode** | 640×200 / 240 / 400 / 480, chunky 8bpp, a span writer, **full copyrect** |
| **Tile mode** | 8×8 8bpp tiles, as `graphics.md` §6.4.2 |
| **One 8×8 sprite** | the mouse pointer, **bitmap mode only** |
| **Scrolling** | `VSCROLL` and `HSCROLL`, byte-granular — **in bitmap and tile mode only**. Character mode scrolls with §6's copy engine |
| ⛔ **Deleted** | **the display-list engine** — and with it per-scanline `HSCROLL`, per-scanline palette, raster bars and `SS.Raster` |

**Scrolling is the playfield's, not the console's.** The overworld's camera is one
`HSCROLL` and one `VSCROLL` write a frame from the VBL service, and those survive; what
does not is an effect needing a *different* `HSCROLL` on each scanline, which is the
display list's job and nothing else's. **`wave`'s sine warp goes; the game's scroll does
not.**

⭐ **And character mode scrolls by copying, not by a register** — §8 has the arithmetic.
That is a change from `video/`, it deletes the map ring and its runway defect, and it
costs about 0.2 % of the CPU at 115.2 kbaud.

---

## 1. The one deletion, and what it pays for

⚠ **This card deletes less than an earlier draft of this document assumed**, and the
economics are correspondingly tighter. `HSCROLL` is required (§0), so §8.2's hardware
stays; only the display-list engine goes.

| Deleted | Direct saving | What it pays for |
|---|---|---|
| **The display-list engine** | one `'244` (`graphics.md` §10.3.3 costed it) — **−1 IC** — plus `BCTRL`, `LRUN`, the armed-`GO` logic, the descriptor decode and the second write port on five registers | **the macrocells and the product terms** that §2.5's map word, §6's copy engine and §7's sprite have to come out of |

⚠ **It does not free an address-mux *source*, though, and that is worth knowing before
the equations are written.** `graphics.md` §10.3.1 records that the engine *shared*
`WPTR` rather than having a source of its own, so deleting it returns macrocells and
terms but not a mux input.

**What the mux costs is the first thing to count**, because `graphics.md` §6.4.1 found
it was the expensive part of that card and there is no reason video3 differs in kind.
§14 item 3 carries the count as a **design budget**, not as an inherited limit —
video3 has no fitted partition to inherit one from.

⚠ **What goes with the engine, in software:** `SS.Raster`, `SS.RastOff`, the `rastbar`
and `wave` clients, and H17. `software/nitros9/docs/video-compat.md` §6.1 lists them as
built; here they do not exist. **`SS.Scroll` and the frame batch's `HSCROLL`/`VSCROLL`
commit are unaffected**, so `overworld` runs.

---

## 2. Modes

### 2.1 Timing — unchanged, and inherited wholesale

`graphics.md` §6.2 and §6.2.1 transfer **verbatim**: one 25.175 MHz dot clock, 800
dots a line, two vertical families (449 and 525 lines), `VMODE[1:0]` selecting
640×200 / 240 / 400 / 480, the family latched at frame end so a mid-frame write is
safe, and **`VSYNC` polarity a function of `VMODE[0]`** — which is how a monitor
tells the two formats apart and is the one-character defect `design-review2.md` §1.8
caught.

**Required**, and required unchanged: every geometry in §0 is one of these four.

### 2.2 Character mode — `MODE = 01`

**Two bytes a cell**, and the attribute is a palette selector rather than a colour:

```
  map word    [15:8] attribute      [7:0] glyph code
  LUT address [15:8] attribute      [7:0] the glyph's pixel byte
```

| | |
|---|---|
| Glyph bank | **256 glyphs, 8×8, one byte a pixel**, 16 KB at `TILEBASE`. A byte is 0 (background) or 1 (foreground) — ⭐ **or 2–255, which renders an antialiased glyph blending background to foreground** |
| Attribute | one of **256 sub-palettes**. Each needs entries 0 and 1 only: **512 palette writes, ~2.9 ms, once** |
| Colour | **256 simultaneous (fg, bg) pairs, each of the 65,536** — 16-colour ANSI is 16 × 16 = 256 exactly, and is the CGA/EGA attribute byte with our colours |
| ⛔ Not reached | the *general* 256-colour case: 256 × 256 pairs needs sixteen attribute bits, three bytes a cell and a 24-bit LUT. That is bitmap mode's job |

**Why the glyph is a byte a pixel and not a bit.** A 1bpp glyph is eight bytes rather
than sixty-four, and it is **the reason `graphics.md` §6.4.3's Variant B was dropped**:
serialising a bit a dot and muxing foreground against background lands in the
index → LUT → output chain, which §6.1 gives **11.7 ns of margin at a 39.72 ns dot**.
A byte a pixel keeps the existing fetch, the existing `'153` mux and the existing
index latch, and moves the colour decision to the LUT's *address*. **The 8× of glyph
memory is 14 KB of 512 KB.**

### 2.3 Bitmap mode — `MODE = 00`

`graphics.md` §2.1's chunky 8bpp in 4-way interleave, unchanged: eight pixel bytes
per eight dots, two `AS6C8016` ×16 parts, the `'153` mux, the index latch, the LUT,
the output register. **Required** — it is the only way to reach 640×480×8bpp, and
§14.2.2's address arithmetic comes with it.

In this mode the attribute half of the LUT address carries **the sprite** (§7), and
the CPU's palette occupies sub-palette 0.

### 2.4 Tile mode — `MODE = 10`

`graphics.md` §6.4.2's Variant A verbatim: a one-byte map, 8×8 8bpp tiles, 64:1 write
compression, no per-cell colour limit. **Required** by §0, and it costs nothing that
character mode does not already build — the two share the map fetch, the cell
counters and `TILEBASE`. The only difference is that tile mode's map is one byte and
drives the LUT's low half through the glyph path, where character mode's is two and
drives both halves.

### 2.5 The cell row is six bits, the stride is a VRAM row, and there is no ring

`graphics.md` §6.4.1 gives the cell row **five** bits — 32 rows — and says so: "`VMODE`
10 and 11 need 50 and 60 rows and cell mode does not reach them." §0 requires 80×50 and
80×60, so video3 widens the field to **six bits, 64 rows**.

⭐ **And the map's row stride is 1024 — a whole VRAM row — not the 160 bytes it needs.**
§6's copy engine steps rows by the framebuffer's stride, and §8.2 makes character-mode
scrolling *depend* on that engine reaching the map, so **the map and the framebuffer
must share a stride or the engine must learn two.**

⚠ **This draft picks one stride and spends the memory, and that is a choice rather than
a constraint.** A stride select is a small mux on which bit the row step lands; whether
it is cheaper than 48 KB is a question for the equations, and §14 item 12 keeps it open.
Nothing here is fitted, so nothing here can say it does not fit.

```
  A18..A16   MAPBASE       (register, 8 positions)
  A15..A10   cell row      6 bits, 64 rows
  A9..A8     0             the stride's padding
  A7..A1     cell column   7 bits, 128 cells (80 displayed)
  A0         0 = code, 1 = attribute   -- the byte enables of one x16 access
```

Still a concatenation, still no adder. **The map costs 64 KB of the 512**, against
16 KB at a packed stride — **a real 48 KB**, and §14 item 12 is where the alternative
is booked.

⛔ **There is no horizontal scroll in character mode** (§0), so `graphics.md` §6.4.9's
phase term `H0` ⊕ `HSCROLL[2]` is **not inherited here**: a cell's phase is `H0`, a line
is **80 codes and not 81**, and §19 item 48's half cell at each end does not exist. The
term survives in tile mode, where the playfield needs it.

⛔ **And there is no ring.** The 64 rows are 64 rows, not a torus: character mode does
not load the row counter from `VSCROLL`, so nothing wraps. `graphics.md` §6.4.6 limit 2's
"32 cell rows — 256 px" and the runway arithmetic that goes with it apply to **tile
mode only**.

## 3. The pixel path — one idea, three uses

⭐ **The whole card turns on one decision: the palette LUT is 64K×16 and `video/`
uses 256 words of it.** §14.2.4's own line: *"63.5 KB of the LUT's 64"* is dead.

```
      pixel byte  ->  index latch  ->  LUT A7..A0   ---+
                                                       +--> LUT -> output register -> DAC
      ATTR byte   ->  ATTR latch   ->  LUT A15..A8  ---+
```

| Mode | What drives `ATTR` | Clocked |
|---|---|---|
| Character | the map word's attribute byte | once a **cell** — constant for eight dots |
| Bitmap | the sprite's 2-bit code, zero-extended | once a **dot** |
| Tile | zero | — |

**The timing claim, stated so it can be attacked.** Both halves of the LUT address
come from `74AHCT574`s clocked by the same dot edge, so the chain is **index latch →
LUT → output register, exactly as today**. The LUT's t<sub>AA</sub> is specified from
*any* address change, so sixteen lines settling together cost what eight do: §6.1's
budget of 8 + 12 + 5 = 25 ns in 39.72 is unchanged, and **so is the 11.7 ns of
margin.** ⚠ What is *not* unchanged is fan-out and board routing: eight more address
lines to a TSOP-44, and §14.2.6's TTL-level constraint (`V_OH` 2.4 V, so `74AHCT` and
never `74AHC`) applies to them exactly as to the rest.

⚠ **This is the card's load-bearing claim and it has not been analysed.** §14 item 1.

---

## 4. Memory

| | Part | Why it is required |
|---|---|---|
| Framebuffer | **2 × `AS6C8016`** 512K×16, 55 ns | `graphics.md` §2.1: a 72 ns access does not fit twice into a 39.72 ns dot's slot, so the interleave is a cliff and not a slope. §14.2.2: `A1` selects the part, `A0` drives `/LB`//`UB`, and seventeen address bits are generated — unchanged here |
| Palette LUT | **1 × `IS61C6416AL-12`** 64K×16 | §3 now uses **all** of it. On `video/` this part was bought for width and 99.6 % idle |
| Register file | 1 × 32K×8, 20 ns | §5, §7.2's column shadow, and §7's sprite shape |

**Address map of the 512 KB**, and ⚠ **this is a proposal, not a constraint** — every
base is a register:

| | |
|---|---|
| rows 0–479 | the picture, 1024-byte stride |
| rows 480–511 | off-screen scratch — copyrect staging and `OWSet` saves. ⭐ The sprite needs none of it (§7 composes at scan time) |
| a 64 KB region at `MAPBASE` | character mode's map, one VRAM row a cell row (§2.5) |
| columns 640–1023 of every row | **scroll margin** — `graphics.md` §8's 1024-column torus, which is what `HSCROLL` scrolls into — **and** copyrect staging when the game is not using it. 384 columns × 512 rows = 196 KB |

---

## 5. The span writer — inherited, and the reason the card is affordable

`graphics.md` §7.4 transfers **complete and unchanged**: four `WMODE`s (direct,
span-mask, span-solid, sprite), `SPANLEN` an eight-bit down-counter, the mask byte's
serial output wired to the register file's address bit 0 **so that `WFG` must sit at
an even address and `WBG` at the odd one above it**, `WADV = 01`'s column reload from
the register-file shadow, the broadcast write, and `/WAIT` on `SPANBUSY`.

**Required, and it is what makes bitmap text possible at all**: eight pixels a write
in mask mode, up to 256 in solid, 25.1 MB/s broadcast. Deleting it would put a
640×480 clear at 366 ms of CPU (`docs/video-copyrect.md` §4).

⚠ **One inherited rule is load-bearing and easy to lose in a rewrite**: span-mask
does **not** consult `SPANLEN`. Its length is three bits, fixed at eight, because
eight is the cell width — and `graphics.md` §7.4 says a cell would be 14 writes
rather than 13 if it did.

---

## 6. Copyrect — full, not vertical-only

**The engine copies a rectangle from anywhere to anywhere in VRAM.**
[`docs/video-copyrect.md`](../../docs/video-copyrect.md) §2 is where the mechanism and
its rate were worked out; §2.3 there explains why the vertical-only subset was ever
considered and what the general form costs on top.

| | |
|---|---|
| Write side | **`WPTR`** — the pointer the span writer and the CPU port already use, with `WADV = 01`'s end-of-row behaviour (reload the column from the register-file shadow, step the row) |
| Read side | **`CPTR`**, a second nineteen-bit pointer with its own column counter, its own shadow and its own row register. ⭐ **Its shadow is a register-file location**, not macrocells — §7.2's trick, and the reason a second pointer is affordable at all |
| Counters | a width down-counter and a height down-counter |
| ⭐ **No adder anywhere** | end-of-row is *reload the column, step the row*; the stride is 1024, a power of two; and **the CPU loads both start addresses**, so the card does no arithmetic. `graphics.md` §6.4.1 and §7.2's property is preserved |
| **No shifter anywhere** | a byte-granular copy needs none. The four-byte fast path is taken **only when the source and destination columns are congruent mod 4** — otherwise the engine falls to one byte an access |

### 6.1 What it runs at

From `graphics.md` §2.1's budget — 115,600 spare accesses a frame, 8.1 M a second —
with a copy costing one read access and one write access:

| | rate | |
|---|---|---|
| Columns congruent mod 4 — **every vertical move, and every 8-pixel-aligned blit** | **16.2 MB/s** | four bytes an access |
| Any other x | **4.05 MB/s** | one byte an access, **and still 40× what a `VDATA` stream costs** (`video-copyrect.md` §6) |

| | on `video/` today | here |
|---|---|---|
| A window scroll, 192 rows | ~350 ms (H5) | **7.6 ms** |
| `Select` between two 200-line pages | ~2.6 s each way (H4) | **7.9 ms** |
| `GetBlk` → `PutBlk`, 64 × 64 at an arbitrary x | ~41 ms | **1.0 ms** |
| `OWSet` save and restore | a `VDATA` stream | a copy |

⚠ **Derived from the access budget, not measured**, and every row assumes the engine
gets the spare access it asks for — §14 item 8.

### 6.2 Overlap

`CCTRL` carries **b1 row direction** and **b2 column direction**, so a copy that
overlaps its own source runs away from the overlap in either axis.

⭐ **`CPTR` and `WPTR` name the rectangle's ORIGIN in both axes, and the direction
bits say which way the engine walks *inside* it.** One convention for both axes: a
descending copy does not mean the pointers name the far corner. ⚠ The first model
written to §6 had two conventions — rows counting down from the origin, columns
counting in from the far edge — and **only an overlapping copy in the wrong axis
would have caught it**, which is what `bench/v3copy` exists to do.

⭐ **And there is a free fallback if b2 turns out expensive**: stage through the
off-screen columns (§4) in two passes. 384 columns × 512 rows of scratch exist for
exactly this kind of thing, and two passes of a 16.2 MB/s engine still beat one pass of
anything else on the card. **So b2 is an optimisation, not a requirement** — §14
item 6. ⚠ Whether it *is* expensive is a question for the equations; nothing here has
been fitted.

### 6.3 What it removes from software

⭐ **It is the single largest item in this card's software account**, because every
`H1`–`H5` cost in `docs/nitros9-hardware-improvements.md` is a `VDATA` stream that
this engine replaces — and `video-copyrect.md` §2 records that those five are one
capability class with no software substitute.

## 7. The mouse sprite — 8×8, bitmap mode only

| | |
|---|---|
| Shape | **8×8, two bits a pixel**: 0 transparent, 1 and 2 the two cursor colours, 3 reserved. **16 bytes**, written through `SPRIDX`/`SPRDAT` |
| Where it lives | ⭐ **the register file**, not VRAM — so the spare-access arbiter, the map latch and the fetch cadence are all untouched |
| Per displayed sprite row | **one** register-file read of two bytes into two eight-bit shift registers |
| Per dot of the sprite's eight columns | two bits shift out into the **`ATTR` latch** |
| Colour | sub-palettes 1 and 2, all 256 entries of each loaded with one colour: **1,024 writes, ~2.9 ms**, and only when the cursor's colours change |
| Position | `SPRX` 10 bits, `SPRY` 9 bits, enable in `SPRH` b7 |

⭐ **Why a serialiser is affordable here and was not for Variant B.** §6.4.6 limit 3
refuses a glyph serialiser because its output feeds a foreground/background mux
*inside* index → LUT → output. Here the shift register's output is **re-registered by
the `ATTR` latch before it reaches the LUT**, so the serialiser has a whole dot period
to settle and the critical path is untouched. **The register is the difference.**

⚠ **The X compare is the part to check.** "This dot is the sprite's first" is an
equality against a 10-bit counter, and then an 8-state down-counter runs the window —
equality, not magnitude, and `graphics.md` §6.4.9 already runs compares at this rate.
But it is dot-rate logic in a CPLD and it has not been fitted. §14 item 2.

⚠ **No save-behind exists and none is needed** — the sprite is composed at scan time,
so `vidptr.asm`'s 7.9 ms of `VDATA` traffic and its `PtrGuard` on every primitive both
disappear. That is the single largest software saving this card offers.

---

## 8. Scrolling — the playfield's by register, the console's by copy

### 8.1 Bitmap and tile mode

`graphics.md` §8 inherited whole: the scan counters have their own loadable registers
and sync generation is untouched.

| | |
|---|---|
| Vertical | the row counter loads from `VSCROLL` in vertical blanking and steps once a displayed row (§8.1). A 512-row torus in bitmap, 64 cell rows in tile mode |
| Horizontal | `HSCROLL`, 10 bits, a **1024-column torus** — §8.2's two ranks of fetch latches with an output-enable select, because `c < HSCROLL[1:0]` is constant for a line |

⛔ **Per-*scanline* scrolling is gone, not scrolling.** One `HSCROLL` a frame is a
register write from the VBL service, which is how `overworld` moves its camera.

### 8.2 ⭐ Character mode scrolls by copying, and here is why

`video/` scrolls a text screen with `VSCROLL += 8` and a 32-row ring
(`graphics.md` §6.4.8). video3 does not, and the reason is arithmetic rather than
taste. One scrolled line at 80×25 — 24 rows of 160 bytes moved, one row cleared:

| | card work | CPU work |
|---|---|---|
| `VSCROLL += 8` | one register write | **clear one row: 271 µs** |
| **§6's copyrect** | 3,840 bytes at 16.2 MB/s = **237 µs of engine** | six register writes + **the same 271 µs clear** |
| the same move by CPU, no engine | — | ⛔ **10.0 ms** |

⭐ **The clear dominates and both paths pay it**, so at 115.2 kbaud (~144 lines a
second) the two cost **3.9 % and 4.1 % of the CPU**. The difference is noise; the
copy is the engine's time, not the CPU's. At 80×60 the engine's share is 583 µs and
the CPU's is unchanged.

**What copying buys for that 0.2 %:**

| | |
|---|---|
| ⭐ no ring | 64 rows are 64 rows. `graphics.md` H9's defect — *more line feeds in a frame than the runway has rows shows a recycled row* — **does not exist here**, at any geometry |
| ⭐ no ring bookkeeping | `video/`'s driver keeps "a shadow of its codes, **by ring row**" and repaints the map from it at `Select` (`video-console.md`). A map that never rotates needs neither |
| ⭐ no `VSCROLL` in cell mode | the row counter's load and wrap are tile mode's alone |

⚠ **And the last row of that table is the catch**: the CPU move is 10.0 ms, so
**character mode without the copy engine is not viable at terminal speeds.** §6 is
not an optimisation here, it is a dependency — which is why §2.5 spends 48 KB to give
the map the framebuffer's stride.

> **Both answers are period-honest, and which is right depends on the machine.** An
> IBM PC's BIOS scrolled by moving 4,000 bytes with `rep movsw`; a VT100 relinked line
> pointers; the CoCo 3's GrfDrv changed the GIME's `St.LStrt` and moved nothing. The
> deciding number here is that **our clear alone costs what a PC's whole scroll did**,
> so the copy is nearly free beside it.

## 9. Interrupts

`graphics.md` §12.1's VBL interrupt, **required**: it is NitrOS-9's system tick, and
the tick's length follows `VMODE[0]` (70.086 Hz or 59.940 Hz). Open-drain `/IRQ`
through a product-term output enable, the pending flag set by an edge, `VSTAT` b0
read and any write to `VSTAT` clearing it.

⛔ **§12.2's raster-compare interrupt is not on this card** — it never was; it is two
GPIO pins and a timer in the CPU module, and `HSYNC`/`VSYNC` still reach the backplane
for it.

---

## 10. Register map — 32 bytes at `$FF60`–`$FF7F`

| Off | Name | |
|---|---|---|
| `+$00` | `CTRL` | b1..0 `VMODE`; b3..2 `MODE` (00 bitmap, 01 character, 10 tile); b5..4 `WMODE`; b6 VBL IRQ enable; b7 display enable |
| `+$01`–`$02` | `VSCROLL` | 9 bits |
| `+$03`–`$04` | `HSCROLL` | 10 bits |
| `+$05` | `SPANLEN` | span length − 1 |
| `+$06` | `WFG` | ⚠ **must stay at an even offset** — §5 |
| `+$07` | `WBG` | ⚠ **must stay at the odd offset above `WFG`** |
| `+$08`–`$0A` | `WPTR` | 19 bits, auto-increment. **Copyrect's destination** |
| `+$0B` | `WADV` | 00 continue, 01 next row same column, 10 by the stride |
| `+$0C` | `VDATA` | the VRAM byte at `WPTR`, read or write, post-increment |
| `+$0D` | `VSTAT` | b7 `SPANBUSY`, b6 `VBLANK`, b5 `HBLANK`, b4 `CBUSY`, b1 `PBUSY`, b0 IRQ pending. **Read through a `'244`** — live macrocells have no register-file path (§12.1's reason) |
| `+$0E`–`$0F` | `PIDX` | **16 bits** — the whole LUT. Auto-increments after `PDATH` |
| `+$10` | `PDATL` | `GGGBBBBB` |
| `+$11` | `PDATH` | `RRRRRGGG`; the write posts the commit to the next `HLOAD` |
| `+$12`–`$14` | `CPTR` | **copyrect source**, 19 bits |
| `+$15` | `CWIDTH` | bytes a row, low 8 |
| `+$16` | `CHEIGHT` | rows, low 8 |
| `+$17` | `CCTRL` | b0 `GO`; b1 row direction; b2 column direction; b4..3 `CWIDTH[9:8]`; b5 `CHEIGHT[8]` |
| `+$18` | `TILEBASE` | the tile bank, or character mode's glyph bank — ⭐ **one register, because a glyph *is* a tile** |
| `+$19` | `MAPBASE` | |
| `+$1A` | `SPRX` | b7..0 |
| `+$1B` | `SPRY` | b7..0 |
| `+$1C` | `SPRH` | b1..0 `SPRX[9:8]`, b2 `SPRY[8]`, b7 sprite enable |
| `+$1D` | `SPRIDX` | shape byte index 0–15, auto-increments after `SPRDAT` |
| `+$1E` | `SPRDAT` | shape byte |
| `+$1F` | — | reserved |

**There is no `BCTRL`, no `BSTAT` and no `BORDER`** — no display list to start, and
VGA has no overscan (§9.3). Reset forces `CTRL = 0`: display off, bitmap, direct
writes, no interrupt.

⚠ **`+$06`/`+$07` is the only placement constraint in the map**, and it is a
mechanism rather than a convention: the span-mask bit *is* the register file's address
bit 0 (§5).

## 11. Component census — what is re-adopted, and why

**The rule this card was drafted under: nothing is inherited because it exists.**

| Component | `video/` § | Verdict |
|---|---|---|
| One 25.175 MHz clock, 800-dot line, two V families | §6.2 | **Required** — §0's four geometries are exactly these |
| `VSYNC` polarity from `VMODE[0]` | §6.2.1 | **Required** — it is how the monitor identifies the format |
| Frame-end `VMODE` latch (`M0`) | §6.2 | **Required** — a mid-frame mode write otherwise costs 1.5 s of lost sync |
| Chunky 8bpp, 4-way interleave, 2 × ×16 | §2.1, §14.2 | **Required** — 640×480×8bpp has no other datapath |
| `'153` pixel mux, index latch, output register | §6.1 | **Required** — and §3 adds one latch beside it |
| Posted-write capture on E-fall | §3.1.1 | **Required** — the span writer's trigger |
| Span writer, four `WMODE`s, `WADV`, broadcast | §7.4 | **Required** — §5 |
| Register file + `'245` read-back | §3.2 | **Required** — and §7 puts the sprite shape in it |
| `WFG`/`WBG` adjacency as an address line | §7.4 | **Required** — it is why per-pixel colour selection is free |
| VRAM read prefetch, `VDATA`, `/WAIT` on both | §11 | **Required** — save-behind, read-modify-write, and the CPU's only way in |
| Cell addressing by concatenation | §6.4.1 | **Required**, ⚠ **widened**: six-bit row, two-byte map (§2.5) |
| Map fetch pipelined one cell ahead, two-stage `MAP`/`MAPQ` | §6.4.9 | **Required**, ⚠ **doubled** — the map is a word now |
| `VSCROLL` and the row counter's `VLOAD`/`ROWADV` | §8.1 | **Required** — §8 |
| VBL interrupt, three macrocells, open-drain | §12.1 | **Required** — the NitrOS-9 tick |
| `VSTAT` through a `'244` | §12.1 | **Required** — live macrocells have no register-file path |
| Posted palette commit, `PBUSY` | §13.1 | **Required** — a commit in the picture otherwise snows |
| 256×16 RGB565 LUT | §9 | **Required**, ⚠ **and now fully addressed** (§3) |
| R-2R ladders, drive stage, blank-to-black | §9.1, §9.2 | **Required** — unchanged analog |
| **Display-list engine** | §10.3 | ⛔ **Deleted** — §0, and §1 spends what it frees |
| `HSCROLL`, two ranks of fetch latches, `pxsel`'s rank select | §8.2 | **Required** — §0 needs a scrolling playfield, and §8.2's "the select is an output enable" is what makes byte granularity cost four latches rather than twelve ICs |
| `HSCROLL`'s cell-phase term and the 81-code line | §6.4.9, §19 item 48 | ⚠ **Tile mode only.** §0 has no horizontal scroll in character mode, so a text line is 80 codes and the half cell at each end does not arise |
| `VSCROLL`'s load and wrap **in cell mode** | §6.4.6 limit 2, §6.4.8 | ⛔ **Not inherited for character mode** — §8.2 scrolls it by copying. Retained for tile mode |
| **Per-scanline `HSCROLL`, per-scanline palette, the second write ports** | §13, §10.3.2 | ⛔ **Deleted** — they were the list engine's, and only the list engine's |
| **`BORDER`** | §9.3 | ⛔ **Never existed** — VGA has no overscan and the porches must be black |
| **Variant B's glyph serialiser** | §6.4.3 | ⛔ **Not rebuilt** — §2.2 reaches per-cell colour without it |
| **Blit datapath** | §10.1, `features.md` §5 | ⛔ **Not built.** §6 is a *copy* engine — two pointers, two counters, no shifter, no logic modes, no source-and-destination strides. `features.md` §5's fourteen ICs bought arbitrary strides and transparency, which §0 does not ask for |
| `SPANLEN` as its own part (`vlen`) | §14.1 | ⚠ **Open** — it was a `GAL22V10` because it loaded from eight pins; whether it absorbs here depends on the partition. §14 item 4 |
| `rfa`, the register-file address GAL | §10.1.6.3 | ⚠ **Open** — same |

---

## 12. What software gains and loses

| | |
|---|---|
| ⭐ **Gains** | per-cell colour in the fast console — so **ANSI art renders at 2 writes a cell instead of 11–13**; all 256 CP437 code points (inverse is an attribute bit, not half the font); 80×50 and 80×60 fast text; a mouse pointer that costs four register writes instead of 7.9 ms and a `PtrGuard` on every primitive; window scroll and `Select` in single-digit milliseconds |
| ⛔ **Loses** | `SS.Raster`, `SS.RastOff` and everything per-scanline — `rastbar`'s colour bands and `wave`'s sine warp. ⭐ **`overworld` is unaffected**: its camera is one `HSCROLL` write a frame through `SS.Batch`, not a list |
| ⚠ **Unchanged** | the CoWin protocol, the escape set, the extensions `$60`–`$69`, the status calls, the VBL service and the frame batch |

---

## 13. The discrete parts, derived

**Every row below is derived from a requirement in §0–§9, not from `video/`'s parts
list.** `video/`'s BOM (`hardware/place/parts.ts`) is quoted only as the *reference
implementation of a mechanism* — where a row says "as `video/`", the mechanism is the
same and the reason is restated. ⚠ **Nothing here is placed or costed**; the
programmable-logic count is deliberately absent, because §14 item 4 says video3 has no
partition yet.

### 13.1 Required, and why

| Part | n | Required by |
|---|---|---|
| **`AS6C8016` 512K×16** | **2** | §2.3. A 72 ns access does not fit twice into a 158.9 ns slot, so the interleave is a cliff and not a slope (`graphics.md` §2.1) — and 640×480×8bpp needs 307,200 bytes. Two ×16 parts give four bytes an access and seventeen address bits |
| **`IS61C6416AL-12` 64K×16** | **1** | §3. ⭐ **And video3 is the first design that needs the whole part**: `video/` bought 64K words for *width* and wrote 256 of them; here A15..A8 carry the attribute |
| **32K×8 register file** | **1** | §5. ⛔ **It cannot be macrocells**: the span-mask bit *is* this SRAM's address bit 0, which is what makes per-pixel colour selection free. It also holds `SPANLEN`, `WPTR`'s and `CPTR`'s column shadows and §7's sprite shape |
| **R-2R ladders, 5/6/5 bits + 3 buffers** | 3 + 3 | §9.1. RGB565 out of the output register. **Not ICs**, counted on their own line as in `video/` |
| `74AHCT574` fetch latches | **8** | §2.3 and §8.1. Four hold one access's 32 bits; the second four are `graphics.md` §8.2's — byte-granular `HSCROLL` needs two fetch groups live at once. ⚠ **§13.3 has the trade** |
| `74AHCT153` 4:1 mux | **4** | §2.3. One of the four latched bytes per dot. ⚠ 0 if the tri-state turnaround closes at 39.72 ns — `graphics.md` §19 item 2, unchanged here |
| `74AHCT574` index latch | **1** | §3. LUT A7..A0 |
| ⭐ `74AHCT574` **`ATTR` latch** | **1** | §3. **NEW.** LUT A15..A8 — the cell attribute in character mode |
| `74AHCT273` output register | **2** | §3, §9.2. Sixteen bits post-LUT, and its `/MR` is what blank-to-black drives |
| `74AHCT163A` `PIDX` low | **2** | §10. Counts, because a sub-palette load walks entries |
| ⭐ `74AHCT574` `PIDX` high | **1** | §10. **NEW, and a latch rather than a counter** — software sets the sub-palette and walks within it, so the high byte never counts. **That is one package rather than two more `'163`** |
| `74AHCT244` `PIDX` onto the LUT bus | **2** | §13.1 of `graphics.md`. **Sixteen bits now, so two** |
| `74HC573` `PDATL`/`PDATH` | **2** | §10. The LUT word is sixteen bits and the bus is eight; something has to assemble it |
| `74HC574` posted-write data | **1** | §5. The span writer's byte, fanned to all four lanes — which is what makes the broadcast write free |
| `74HCT245` register-file read-back | **1** | §10. `WFG`, `WPTR` and the rest onto `D0`–`D7` |
| `74HCT574` `vread` | **1** | §6 and `VDATA`. The prefetched VRAM byte |
| `74HC244` `VSTAT` | **1** | §10. `SPANBUSY`, `CBUSY` and `PBUSY` are live macrocells with no register-file path |
| `74HC244` fan-out | **1** | §9 and `graphics.md` §12.2 — `HSYNC`/`VSYNC` to a backplane pin at TTL, plus clock fan-out |
| ⚠ `74AHCT574` copy-read latch | **4** | §6. ⛔ **The one genuinely new datapath.** The posted-write `'574` fans *one* byte to four lanes; a copy needs **four distinct bytes** on the write bus, so the engine reads into a 32-bit latch and drives it back. §13.3 asks whether the fetch latches can do this instead |

**Discrete total as drawn: 36**, against `video/`'s 30. ⚠ **Plus programmable logic,
count unknown** (§14 item 4) — and §13.5 says what the board allows.

### 13.2 Not required — deleted with a reason

| Part | `video/` | Why video3 does not need it |
|---|---|---|
| `74HCT244` list-descriptor byte | 1 | §0 deletes the display-list engine, and this package existed only to put a descriptor byte on the internal data bus (`graphics.md` §10.3.3) |
| Posted-write **address** latches | 0 | `video/` listed three and no design ever clocked them (§3.1.1, §19 item 44). ⭐ Recorded so video3 does not re-add them: **every CPU VRAM access is at `WPTR`**, so the physical address selects the window and nothing else |
| A dot-clock oscillator | 0 | `graphics.md` §5.3 — the card is clock-slaved to the backplane, and should stay so |
| `BORDER` hardware | 0 | §9.3: VGA has no overscan, the porches must be black for the back-porch clamp |
| A sprite shape store | 0 | §7 puts it in the register file, so no package and no VRAM access |

### 13.3 ⚠ Three trades to settle before the equations

1. ⭐ **The copy-read latch may be free.** The second rank of fetch latches
   (`graphics.md` §8.2) is four `'574` on the same 32-bit bus with output enables
   already. **If a copy's read can borrow them, §13.1's last row goes to 0 and the
   discrete total is 31.** The risk is that copies run in spare accesses interleaved
   with display fetches that want both ranks — **a cadence question** (§14 item 8), and
   the single largest package swing on the card.
2. **Byte-granular `HSCROLL` costs four packages.** The second fetch rank exists
   only so a line can start part-way through a fetch group. **Four-pixel granularity
   needs one rank** and saves four ICs; a scrolling playfield at four-pixel steps is
   visibly chunky. **A gameplay decision, not an engineering one** — it should be taken
   deliberately rather than inherited.
3. ⛔ **SETTLED 2026-09-16: the `'153` mux stays, and this trade yields no board room.**
   `npm run check:video3` has the arithmetic. The `'153` path — `MUXSEL` → `'153` →
   index latch — is **25 ns in a 39.72 ns dot, 14.7 ns of margin**, the same depth as
   the LUT path. The tri-state alternative must **break before make**, because two
   `'574` on one net with opposite values is a fight and not a slow path, so `t_PHZ`
   and `t_PZH` are **in series**: 33 ns, **6.7 ns of margin**, under the design point.

   ⚠ **And it is a decision, not a proof.** The miss is ~3 ns and what the bus would
   need — `t_PHZ` and `t_PZH` each under ~8.4 ns — is *inside* the 74AHCT family's
   range, so the arithmetic narrows the question rather than closing it; `graphics.md`
   §14.2.6 records that the repository has no 74AHCT datasheet.

   ⭐ **What decides it is a count, not an estimate.** §6.1's table costs "**4** tri-state
   `'574`". §8.2's second rank of fetch latches — added *after* that estimate — makes it
   **eight** outputs on one net, all of them contributing off-state capacitance whether
   their rank is selected or not, and AHCT enable and disable times are specified into
   50 pF. **The number that kept the tri-state bus alive as a candidate was taken before
   the bus doubled.** `graphics.md` §19 item 2 has already taken the same decision for
   `video/`: four `'153` are in the BOM and `MUXSEL1:0` drives them.

### 13.4 ⚠ Two things that could move between silicon and packages

Recorded because they are partition choices, and §14 item 4 says the partition is not
written:

- **The map word's two-stage latch.** `graphics.md` §6.4.9 needs the map pipelined one
  cell ahead, with `MAP` fetched while `MAPQ` is still being displayed. video3's map is
  a **word**, so that is 32 bits of pipeline. In programmable logic it is macrocells; as
  two `'574` it is two packages. **Whichever is cheaper is a fit's answer.**
- **The sprite's two bits onto LUT A9:A8.** Either the `ATTR` latch carries them
  (one 8-bit mux ahead of it) or a CPLD macrocell drives those two lines directly while
  the `ATTR` latch stands off. ⚠ **The second is cheaper and puts two drivers on two LUT
  address lines** — which wants `graphics.md` §13.1's discipline, where *one* pin does
  both halves of a turnaround so the bus can never have two masters.

### 13.5 ⭐ What the board says — measured, not estimated

`hardware/place/parts.ts` carries video3 as an **alternate** (a design that is not in
the machine — it replaces `video`, so it cannot own `$FF60` and cannot be a `CARDS`
entry), and `npm run check:place` places it through the same skyline packer that
measures every other card:

| | ICs | courtyard | 240 mm |
|---|---|---|---|
| `video`, the built card | 33 | 124.4 cm² | places, 59 % |
| **video3 as drawn, 3 programmable parts** | **39** | 143 cm² | **places, 67 %** |
| **video3 as drawn, 4** | **40** | 150 cm² | **places, 73 %** |
| **video3 as drawn, 5** | 41 | 166 cm² | ⛔ **does not place** |
| video3 without the copy latch, 4 | 36 | 137 cm² | places, 68 % |

⛔ **THE PARTITION HAS A CEILING OF FOUR PARTS, and 240 mm is the longest board there
is.** A PLCC-84 is 33 × 33 mm, so the fifth one is worth three DIP-20s of skyline and
the board refuses it. **That is a constraint on §14 item 4 that no amount of prose
would have produced** — and it is the reason this list exists as a file rather than as
a table in this document.

**The trades of §13.3 against it:**

| | discrete | with 4 parts |
|---|---|---|
| As drawn | **36** | 40 — places |
| Copy latch borrows the fetch rank (trade 1) | 32 | 36 — places |
| … and `HSCROLL` goes four-pixel (trade 2) | 28 | 32 |
| … and the tri-state pixel bus closes (trade 3) | 24 | 28 |

⚠ **The `ics` figure in `parts.ts` assumes three programmable parts and says so in its
own comment.** It is a placeholder, not a finding; what is *asserted* is that the list
totals its own claim and that 24 cm is the shortest length that holds it.

> ⭐ **This section used to say 35 and it was wrong.** Writing the parts list found the
> arithmetic error immediately — which is the argument for keeping counts in a file a
> check reads rather than in a paragraph. `docs.check.ts`'s own header: *"stale headline
> numbers are this repository's oldest recurring defect."*

## 14. Open items

0. ⛔ **ONLY TRADE 1 CAN PAY FOR THE CELL BUDGET'S ESCAPE, and it is unsettled.**
   [`partition.md`](partition.md) §8 measured that the board is full: four programmable
   parts **plus** the discrete `MAP`/`MAPQ` latches §13.4 offers as a cell-budget escape
   **do not place**. §13.3 trade 3 is now settled the other way — the `'153` mux stays —
   so **the only remaining payer is trade 1: whether the copy engine's read latch can
   borrow §8.2's second fetch rank.** ⛔ That makes a *cadence* question (§14 item 8)
   the gate on a *macrocell* question (§14 item 4), and nothing else on the card
   couples those two.
1. ⛔ **§3's timing claim has not been analysed.** *"Sixteen address lines settling
   together cost what eight do"* is the card's load-bearing assumption, and everything
   in §2.2 and §7 rests on it. It wants the LUT's datasheet numbers against a real
   fan-out and a real board, not an argument. **Nothing else should be drawn until
   this is answered.**
2. ⚠ **§7's sprite compare is dot-rate logic and unfitted.** Equality against the
   column counter plus an eight-state window counter is the cheap form; whether it
   fits beside the cell counters is a fit, not an estimate.
3. ⚠ **The framebuffer address mux is the first thing to count, and this is the
   budget rather than a verdict.** The sources video3 needs are the bitmap scan
   address, the cell/tile concatenation, the write pointer, the map fetch, and §6's
   `CPTR` — **five**. An ATF15xx macrocell holds about five before it cascades
   (`graphics.md` §6.4.1 states that as a property of the family, not as a fit
   result), so five is *at* the budget and a sixth source is where cascading starts.
   ⛔ **This is a number to design against and then check, not a limit inherited from
   anywhere** — see item 4.
4. ⚠ **The partition is drafted — [`partition.md`](partition.md) — and it comes out at
   FOUR parts, which §13.5 says is the most that places.** ⛔ **video3 is therefore at
   its ceiling**, and every count in it is an estimate rather than a fit. **NO NUMBER
   FROM `video/`'s FIT APPLIES HERE.**
   `video/` is three `ATF1508AS` whose utilisation is recorded in
   `hardware/gal/cpld/*.fit`; **those figures describe a different design** — one with
   a display list, per-scanline scrolling, a one-byte map and no copy engine. video3
   has none of that and has no `vaddr`. ⚠ **An earlier draft of this document quoted
   `video/`'s cell and fan-in counts as if they constrained video3, and used them to
   justify §2.5's stride and to call §6.2's column direction doubtful.** Both are
   withdrawn: they are open questions for the equations, not settled by another card's
   report. **What transfers from `video/` is mechanism and arithmetic; what does not
   transfer is utilisation.**
5. ⚠ **`vlen` and `rfa`** (§11's last two rows) exist on `video/` for partition
   reasons that may not survive a re-partition.
6. **§6.2's column-direction bit is uncosted.** If it turns out expensive, overlapping
   horizontal copies stage through the off-screen columns in two passes — **a software
   rule, not a lost capability**.
7. ⚠ **The sub-palette load cost is a software rule**: 512 entries for character
   mode's 256 pairs, 512 more for the sprite's two colours, ~2.9 ms each, and §13.1's
   `PBUSY` rule applies to every one of them.
8. ⛔ **The spare-access budget has four requesters now and has not been re-derived.**
   `graphics.md` §6.4.2 already halves the span writer's slots in cell mode, because
   the map fetch takes the internal address bus one slot in two. video3 adds **the map
   *word*** (same access, wider), **copyrect** (two accesses a group), **the sprite row
   fetch**, and the CPU's read prefetch — against one spare access a slot.
   `cadence.check.ts`'s equivalent is what decides whether §6.1's rates are real.
9. ⭐ **CLOSED by §8.2.** `video/`'s ring-runway defect — H9's *more line feeds in a
   frame than the ring has spare rows shows a recycled row* — **does not exist here**,
   because character mode has no ring.
10. ⭐ **CLOSED by §2.5.** The 81st code a scrolled text line would fetch does not
    arise, because character mode has no horizontal scroll.
11. ⛔ **Character mode DEPENDS on §6, and the two must be scheduled together.** The
    CPU move is **10.0 ms a line** (§8.2), so if copyrect does not fit, character mode
    does not work at terminal speeds and the ring has to come back with its defect.
    They are not independent features.
12. ⚠ **One stride or two — open** (§2.5). This draft gives the map the framebuffer's
    1024-byte stride so §6's engine needs no second one, at **48 KB**. The alternative
    is a stride select — a mux on which bit the row step lands — for 16 KB of map.
    **Cost both when the equations are written**; the draft's choice is a default, not
    a finding.

## 15. What would have to be built to believe it

Each step gates the next, and the first two are **done**.

| | | |
|---|---|---|
| ✅ 1 | **The parts list**, as an *alternate* in `hardware/place/parts.ts` | `npm run check:place` — §13.5. It found the ceiling of four programmable parts, and an arithmetic error in this document |
| ✅ 2 | **The dot path and access budget as arithmetic** | `npm run check:video3` (`hardware/video3/timing.check.ts`) — the half of §14 item 1 that does not need a board |
| ✅ 2b | **A functional model in the host emulator**, beside `video/`'s and selected by `VIDEO3=1` | `sh video3/bench/run-v3.sh` — **character mode, tile mode, the copy engine and the sprite, all pixel-exact** against `tools/v3model.py`, which renders from §2.2/§2.4/§2.5/§3/§6/§7/§8.1 and shares only *data* with the ROM. Mutation-tested. **This is where the driver gets written.** ⚠ It cannot see the cadence (§14 item 8) |
| ✅ 2c | **The control-line census** — [`signals.md`](signals.md) | what the lines are and what generates them, block by block. It is the input to the partition, and it surfaced three things: the LUT address bus now has masters on **both** halves, `ATCLK` must not be mode-dependent, and the copy engine is the only requester wanting **two** spare accesses |
| 3 | **The dot path as a schematic**, and nothing else yet | it is settled by §3 and §13, it does **not** depend on the partition, and it is what §14 item 1's *other* half needs. ⛔ Drawing the rest first would encode a partition that does not exist |
| ✅ 4a | **The partition** — [`partition.md`](partition.md) | **four parts**, which §13.5 says is the most that places. ⛔ **So video3 is exactly at its ceiling**: there is no fifth part, and no room for a feature that needs one |
| 4b | **Term lists, then a pin census from them, then a fit** | in that order. `partition.md` §6 |
| 5 | **`reach` and `census` from the first term list, not retrofitted** | they are the pair that caught `ACTRL` b3 unbuilt for two days and `design-review2`'s eleven blocks described as fitted with nothing behind them |
| 6 | **A cadence check** — §14 item 8 | five requesters, one spare access a slot |
| 7 | **Verilator** — §15.1 |
| 8 | **The board file and `check:netlist`** | and `lib/netlist.check.ts`'s *reachability* form: ⚠ "a stub check is not the fix — U1B's `DQ` pins were never dangling, they were on a net with three other parts and connected to the wrong one" |

### 15.1 ⭐ Verilator — and the one lesson that decides how it is built

`graphics.md` is unambiguous about which benches found defects and why:

> ⛔ **"AND THE ONE THING NONE OF THEM DID UNTIL 2026-09-10 IS EXECUTE AN INSTRUCTION."**
> `mainboard_tb` walks the boot sequence as twenty literal bus cycles and `vspan_tb`
> writes registers from a task, so both check that each part does what its author
> thought when driven the way its author expected. `machine_tb` hands the bus to a CPU
> core somebody else wrote and lets the boot ROM drive — **and three defects fell out
> of the first run that had survived everything else.**
>
> ⚠ **The reason none of the older benches could see any of them is the same reason**,
> and it is worth stating as a rule: **a testbench that drives `E` from its own
> free-running counter has a CPU that cannot be waited.** `/WAIT` is the only signal on
> this backplane that changes what the CPU *does* rather than what it reads.

**So video3's bench ladder is built from the top down, not the bottom up.** The unit
benches exist to localise a failure the machine bench found, not to earn confidence on
their own.

| Bench | Instantiates | What only it can assert |
|---|---|---|
| `v3dot_tb` | the fetch latches, the mux, both LUT latches, the LUT, the output register | §3: that the `ATTR` half of the address is stable across a cell in character mode and per-dot in bitmap, and that the two never have two masters — `video_card.v`'s `PIXOE` assertion, generalised |
| `v3char_tb` | the whole card | a CP437 screen with 256 attribute pairs, **the 80×50 and 80×60 geometries**, and §8.2's copy-scroll — the modes `video/` cannot reach at all |
| `v3copy_tb` | the whole card | §6: aligned and unaligned, both directions, an overlapping scroll, and **that a copy under a span waits** |
| `v3sprite_tb` | the whole card | §7: the sprite at every X phase including the two that straddle a slot boundary, and that it is **off** in character mode |
| ⭐ **`v3machine_tb`** | **`mc6809e` + the motherboard + video3 + the audio card** | §15.2 — and it is the only one that can be believed |

⚠ **`v3dot_tb` is the exception to "top down"**, and deliberately: §14 item 1 gates the
whole design, so the path it covers wants a bench before the rest exists.

### 15.2 The machine bench, and why the audio card is in it

`machine_tb` already instantiates `mc6809e`, `mainboard.v`, `video_card.v`, `audio_card.v`
and a `tl16c550.v` bus model, and `SCENARIOS=nitros9` boots NitrOS-9 Level 2 to a shell.
**video3's bench should be that one with `video_card.v` replaced**, not a new harness —
so that what changes between a passing run and a failing one is the card.

Three things only the machine bench can answer, and each is a seam rather than a part:

| | |
|---|---|
| **Arbitration against a real CPU** | §14 item 8's five requesters meet a CPU that can be `/WAIT`ed. `graphics.md` §19 items 36–38 were all seams of exactly this kind — the arbiter refusing the span writer a chip the CPU's stalled write was holding, a level-triggered `SPANBUSY` over an `E`-high that `/WAIT` makes unbounded, and a poll rule that took the register file away from the span whose colour it was |
| **The audio card's `/FIRQ` against video3's `/IRQ`** | two cards, one backplane, and `machine_tb` already asserts that **no cycle has two drivers on `D0`–`D7` or on `A20`–`A13`**. video3 adds a copy engine that wants the bus in spare accesses; the assertion is the same and the traffic is not |
| **The tick** | §9's VBL is NitrOS-9's clock, and `SCENARIOS=nitros9` is what proves a shell comes up on it |

### 15.3 ⚠ The NitrOS-9 driver is a rewrite, not a port, and it is on the critical path

`software/nitros9/docs/video-compat.md` and `video-console.md` describe a driver built
against `video/`. **What carries and what does not:**

| | |
|---|---|
| ⭐ **Carries unchanged** | CoWin's protocol and escape set, the `$60`–`$69` extensions, the status calls, `CoArm`'s task-1 residency and `CoCall`, the VBL service's shape, `KbdArm`, and 2026-09-16's `AnsiPal`/`An256`/`PalDef` work — **the ANSI colour path is the same code**, and its palette lands in sub-palette 0 |
| ⛔ **Deleted** | `SS.Raster`, `SS.RastOff`, `ca_list.asm`, and the `rastbar` and `wave` clients (§0) |
| ⛔ **Rewritten** | `vidptr.asm` — **the pointer becomes four register writes**, so the save-behind, `PtrGuard` and the idle-loop mechanism all go; the fast-text screen, which gains a real attribute plane and loses its ring (§8.2); and `ca_scr.asm`'s `Select`, which becomes a copy |
| ⭐ **New** | an attribute-pair allocator (256 pairs from 65,536, §14 item 7), a `SS.Copy`-shaped call over §6, and CP437 as the default font |

⛔ **And the driver is not optional to the hardware's verification.** `graphics.md` §19
items 36–38 were found by a boot ROM driving the card, not by a testbench writing
registers — so **`SCENARIOS=nitros9` on `v3machine_tb` is the acceptance test**, and the
driver has to exist before the card can be believed. That makes §15.3 concurrent with
§15.1, not subsequent to it.

⚠ **One thing to settle early, because it is cheap and it de-risks everything after
it**: the host emulator (`software/demo/emu/machine.c`) models `video/`'s card
register-for-register. A video3 model there runs in seconds where `v3machine_tb` runs in
minutes, and `software/nitros9/run-vid.sh`'s pixel-exact models
(`tools/vtmodel.py`, `tools/vgmodel.py`) are already written against the *protocol*
rather than the driver — **so they are reusable, and they are what would catch a
character-mode attribute bug before any RTL exists.**
