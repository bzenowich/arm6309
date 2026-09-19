# video3 — a console-first video card

## Character mode with attributes, bitmap mode with a span writer, and nothing that draws itself

**DRAFT, 2026-09-16.** ⭐ **The logic is fitted and simulated; nothing is timed, drawn
or costed.** Four `ATF1508AS` and a `GAL22V10` hold it (`partition.md`, §14 item 4),
`v3card_tb` runs the five of them as a card in every mode (§15.4), and
`npm run check:place` places the 44-IC list on 24 cm (§13.5). ⚠ **There is no timing
analysis (§14 item 1), no board file and no power budget (§14 item 13)**, so it is still
a specification to be attacked rather than a build. Every number is either inherited from
[`video/docs/graphics.md`](../../video/docs/graphics.md) with its section cited, a fit or
bench result with its file named, or derived here and marked. §14 lists what would refute
each load-bearing claim, and §15 is the verification this card would need before a board.

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
| **One 16×16 sprite** | the mouse pointer, **bitmap mode only** (§7) |
| **Scrolling** | `VSCROLL` and `HSCROLL`, **one pixel at a time** — **in bitmap and tile mode only**. Character mode ignores both registers and scrolls with §6's copy engine |
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

**A cell is a four-byte fetch group**, two bytes of which are used, and the attribute is
a palette selector rather than a colour:

```
  map cell    lane 0 glyph code     lane 2 attribute     lanes 1, 3 unused
  LUT address [15:8] attribute      [7:0] the glyph's pixel byte
```

⛔ **Four bytes and not two, because the map word has to come from one ×16 part.**
`v3scan` has sixteen data pins and no more, so on a two-byte stride every odd cell's
word would sit in the part those pins are not on. A four-byte stride puts every cell's
word in one access (§2.5). The unused half costs memory, not pins, and the map is 64 KB
a `MAPBASE` either way.

⭐ **AND THE TWO BYTES ARE LANE 0 AND LANE 2, WHICH IS WHAT KEEPS A CHARACTER AT TWO
STORES.** The sixteen pins may be wired to any two of the four lanes, and the two parts'
LOW bytes are the pair `WPTR`'s step-by-two reaches: with `WADV` b2 set (§10) a write
steps the pointer by two, so the code and the attribute are one write each and the
third write lands on the next cell. Written to lanes 0 and 1 instead, a cell took four
stores — the two bytes plus two of filler, because re-pointing `WPTR` costs three
register writes to save two. ⚠ The step is the *write pointer's*, so a span's retires
and a `VDATA` read's post-increment move by two while the bit is set: it is a mode for
cell writes, cleared for everything else.

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

`graphics.md` §6.4.2's Variant A: a one-byte code a cell, 8×8 8bpp tiles, 64:1 write
compression, no per-cell colour limit. **Required** by §0, and it costs nothing that
character mode does not already build — the two share the map fetch, the cell
counters, the four-byte cell stride and `TILEBASE`. Tile mode's code is **lane 0** of
the same layout as §2.2's; it drives the LUT's low half through the glyph path, and the
high half is **zero** — nothing drives LUT `A15..A8` in tile mode, and pull-downs hold
it (§3).

### 2.5 The cell row is six bits, the stride is a VRAM row, and there is no ring

`graphics.md` §6.4.1 gives the cell row **five** bits — 32 rows — and says so: "`VMODE`
10 and 11 need 50 and 60 rows and cell mode does not reach them." §0 requires 80×50 and
80×60, so video3 widens the field to **six bits, 64 rows**.

⭐ **And the map's row stride is 1024 — a whole VRAM row — not the 320 bytes it needs.**
§6's copy engine steps rows by the framebuffer's stride, and §8.2 makes character-mode
scrolling *depend* on that engine reaching the map, so **the map and the framebuffer
must share a stride or the engine must learn two.**

⚠ **This card picks one stride and spends the memory, and that is a choice rather than
a constraint.** A stride select is a small mux on which bit the row step lands; §14
item 12 keeps it open.

```
  A18..A16   MAPBASE       (register, 8 positions)
  A15..A10   cell row      6 bits, 64 rows
  A9         0             the stride's padding
  A8..A2     cell column   7 bits, 128 cells (80 displayed)
  A1..A0     the lane      0 = code, 2 = attribute, 1 and 3 unused
```

Still a concatenation, still no adder — `v3scan`'s address mux takes `MAPBASE`, the cell
row and its own map column counter `MC6..MC0` straight onto `FBA18..FBA2`, and the word
arrives on lanes 0 and 2 of one access. **The map costs 64 KB of the 512**, against
32 KB at the smallest power-of-two stride that holds 320 bytes — **a real 32 KB**, and
§14 item 12 is where the alternative is booked.

⭐ **`A9` is zero for every cell, so the top half of each map row is never a map
address** — which is where §7's sprite shape lives: the region's last 64 bytes,
`MAPBASE`·64K + `$FFC0`, are row 63 with `A9` set.

⛔ **Character mode ignores `HSCROLL` and `VSCROLL`, in hardware** (§0). `v3scan`'s column,
row and map-column loads and `v3dot`'s fine-scroll logic are all gated by `MODE0`, so
the registers may hold the playfield's scroll while a character screen shows and software
need not clear them — `v3card_tb`'s character frames are taken with both set. So
`graphics.md` §6.4.9's phase term `H0` ⊕ `HSCROLL[2]` is **not inherited here**: a cell's
phase is `H0`, a displayed line is **80 cells**, and §19 item 48's half cell at each end
does not exist. The term survives in tile mode, where the playfield needs it.

⛔ **And there is no ring.** The 64 rows are 64 rows, not a torus: character mode does
not load the row counter from `VSCROLL`, so nothing wraps. `graphics.md` §6.4.6 limit 2's
"32 cell rows — 256 px" and the runway arithmetic that goes with it apply to **tile
mode only**.

⭐ **The map access's cadence.** `v3dot` makes `MRQ`, a registered request for the
current slot, inside `MWIN` (slots 30–193): one access a cell, in the slot whose parity is
`HC0` = `HSCROLL[2]` — even slots 32–194 in character mode and in tile mode at
`HSCROLL[2]` = 0, odd slots 31–193 at `HSCROLL[2]` = 1, where the line takes 81 codes.
`v3scan` makes every map strobe from `MRQ` and the dot phase: `GMAP` in the spare half,
`MAPLD` on its dot 1, `MCADV` at the end of the slot after. The map column counter steps
on each access and loads on `HLOAD`'s first dot (`HLOAD` is slots 30–33). ⭐ **The
attribute takes three stages** — `MAPA` → `ATQ` → `ATO`, stepped together on the first
dot of each map access — because it meets the pixel its code's tile fetch produces two
slots later; `ATO` changes on exactly the edge the index `'574` takes the cell's first
pixel.

## 3. The pixel path — one idea, three uses

⭐ **The whole card turns on one decision: the palette LUT is 64K×16 and `video/`
uses 256 words of it.** §14.2.4's own line: *"63.5 KB of the LUT's 64"* is dead.

```
      pixel byte  ->  index latch       ->  LUT A7..A0   ---+
                                                            +--> LUT -> output register -> DAC
      ATTR byte   ->  CPLD registers    ->  LUT A15..A8  ---+
```

| Mode | What drives LUT `A15..A8` | Enable | Changes |
|---|---|---|---|
| Character | `v3scan`'s `ATO7..ATO0`, the cell's attribute — the third stage of §2.5's pipeline | `ATOE` | once a **cell** — constant for eight dots |
| Bitmap | `v3dot`'s `SPRA1..SPRA0` onto `A9..A8`, the sprite's 2-bit code re-registered; `A15..A10` pulled down | `SPRAOE` | once a **dot** |
| Tile | nothing — pull-downs, so zero | — | — |

**There is no `ATTR` latch.** The attribute's last pipeline stage is a CPLD register
already, so it drives the LUT through its own output enable, and the sprite has two lines
of its own; `v3dot` decides all three enables (`ATOE`, `SPRAOE`, `PIDXOE`), so the bus has
one master at a time by construction.

**The timing claim, stated so it can be attacked.** Both halves of the LUT address
are registers clocked by the same `CLK25` edge — the index `'574` for the low half, a
CPLD macrocell for the high half — so the chain is **register → LUT → output register,
as on `video/`**. The LUT's t<sub>AA</sub> is specified from *any* address change, so
sixteen lines settling together cost what eight do: §6.1's budget of 8 + 12 + 5 = 25 ns
in 39.72 applies, with **the 11.7 ns of margin** — ⚠ **provided an `ATF1508AS` output's
clock-to-out is no worse than the `'574`'s 8 ns**, which nothing here has checked (§14
item 1). ⚠ What is *not* unchanged is fan-out and board routing: eight more address
lines to a TSOP-44, and §14.2.6's TTL-level constraint (`V_OH` 2.4 V, so `74AHCT` and
never `74AHC`) applies to them exactly as to the rest.

⚠ **This is the card's load-bearing claim and it has not been analysed.** §14 item 1.

---

## 4. Memory

| | Part | Why it is required |
|---|---|---|
| Framebuffer | **2 × `AS6C8016`** 512K×16, 55 ns | `graphics.md` §2.1: a 72 ns access does not fit twice into a 39.72 ns dot's slot, so the interleave is a cliff and not a slope. §14.2.2: `A1` selects the part, `A0` drives `/LB`//`UB`, and seventeen address bits are generated — unchanged here |
| Palette LUT | **1 × `IS61C6416AL-12`** 64K×16 | §3 now uses **all** of it. On `video/` this part was bought for width and 99.6 % idle |
| Register file | 1 × 32K×8, 20 ns | §5 and §7.2's column shadows — 32 bytes, addressed by `RFA4..RFA0` |

**Address map of the 512 KB**, and ⚠ **this is a proposal, not a constraint** — every
base is a register:

| | |
|---|---|
| rows 0–479 | the picture, 1024-byte stride |
| rows 480–511 | off-screen scratch — copyrect staging and `OWSet` saves. ⚠ **Less row 511's last 64 bytes when `MAPBASE` is 7**: the driver keeps the pointer's shape there, so its scratch is rows 480–510 |
| a 64 KB region at `MAPBASE` | character and tile mode's map, one VRAM row a cell row (§2.5) — ⭐ **and its last 64 bytes are §7's sprite shape**, which no map address reaches (`A9` is zero for every cell). In bitmap mode `MAPBASE` has no other use |
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
| Write side | **`WPTR`** — the pointer the span writer and the CPU port already use, with `WADV = 01`'s end-of-row behaviour (reload the column from the register-file shadow, step the row). The write access drives the byte back out of the posted-write `'574` (`PWOE`) through the destination's lane `'245`, under `VWE` |
| Read side | **`CPTR`**, a second nineteen-bit pointer, with its own column counter, its own shadow and its own row register. Its read access lands the byte in **the posted-write `'574`** — `v3host`'s `PWCK` is the CPU's VRAM write or the copy's read tick — across the source's lane `'245` and the card's internal bus. ⭐ **Its shadow is a register-file location**, not macrocells — §7.2's trick, and the reason a second pointer is affordable at all |
| Counters | a width down-counter and a height down-counter |
| ⭐ **No adder anywhere** | end-of-row is *reload the column, step the row*; the stride is 1024, a power of two; and **the CPU loads both start addresses**, so the card does no arithmetic. `graphics.md` §6.4.1 and §7.2's property is preserved |
| **No shifter and ⭐ NO LATCH either** | §13.3 trade 1, settled: the engine is **byte-granular**, so the byte in flight waits in §5's posted-write `'574`, which a CPU write cannot touch while `CBUSY` holds it off with `/WAIT`. `vread` is the CPU prefetch's alone. **Nothing new on the data path** but the four lane `'245`s every byte access needs (§13.1) |

### 6.1 What it runs at

From `graphics.md` §2.1's budget — 115,600 spare accesses a frame, 8.1 M a second —
with a copy costing one read access and one write access:

⛔ **The four-byte group is withdrawn** (§13.3 trade 1). One read access and one write
access move **one byte**, so the engine runs at **4.05 MB/s** in every case — and column
congruence stops mattering, which also deletes an alignment rule software would have had
to keep.

| | on `video/` today | here | |
|---|---|---|---|
| A window scroll, 192 rows | ~350 ms (H5) | **30.3 ms** | 12× |
| `Select` between two 200-line pages | ~2.6 s each way (H4) | **31.6 ms** | 82× |
| `GetBlk` → `PutBlk`, 64 × 64 at any x | ~41 ms | **1.0 ms** | 41× |
| A character-mode scrolled line at 80×25 (§8.2) | 20.0 ms of **CPU**, without the engine | **1.90 ms of engine** | |
| `OWSet` save and restore | a `VDATA` stream | a copy | |

⚠ **Derived from the access budget, not measured**, and every row assumes the engine
gets the spare access it asks for — §14 item 8.

### 6.2 Overlap

⛔ **SETTLED 2026-09-16 BY `v3ptr`'s FIT: there are no direction bits.** The engine
counts **up only**, and `CCTRL` b1 and b2 are reserved.

The up/down counters are what the fitter charged for, and the price is not marginal:

| fit, 2026-09-16, per-register strobes | cells | cascades |
|---|---|---|
| `v3ptr_both` — both directions | **128 / 128** | 19 |
| `v3ptr_rows` — rows only | **128 / 128** | 21 |
| ⭐ **`v3ptr` — neither, and this is the build** | **110 / 128** | **3** |

**18 macrocells and 16 cascades, and dropping one bit buys nothing** — it is
all-or-nothing. ⚠ All three are kept as fits rather than as prose: the first draft of
this table quoted 128/128 after the run that produced it had been *overwritten* by the
next variant, so `check:docs` found a number with no design output behind it. That is
`CLAUDE.md`'s first trap wearing different clothes. ⚠ And `CLAUDE.md` is explicit that *a change in cascades is a timing
change even when the cell count is flat*, so 19 → 3 is the larger half of that.

⭐ **An overlapping copy stages through scratch in two ascending passes**, which this
section always offered as the fallback for columns and which plan §4 already reserves
rows 480–510 for. `bench/v3copy` does exactly that in two of its ten copies, so the
fallback is checked and not merely promised.

**What it costs is 2× on an overlapping copy, and the common cases do not overlap
backwards**: a terminal scrolls *up*, which reads ahead of where it writes and is
ascending by construction; `Select` and `GetBlk` are disjoint regions.

⛔ **CORRECTED 2026-09-16, WRITING THE EQUATIONS.** An earlier draft said the pointers
name the rectangle's *origin* and the direction bits walk inside it. **That needs an
adder** — a descending copy would start at `origin_row + height − 1` — and
`graphics.md` §6.4.1 and §7.2 build this whole card on not having one. It was
unbuildable, and only writing `v3ptr` found it.

⭐ **`CPTR` and `WPTR` name the FIRST CELL PROCESSED**, and the direction bits say which
way to step from there. Software already computes both addresses; adding `h−1` to one of
them for a descending copy costs it nothing, and the card stays adder-free.

⚠ The end-of-row reload is unaffected: the column shadow holds **the column the copy
started at**, whichever end that is, so one mechanism serves both directions.

⭐ **And there is a free fallback if b2 turns out expensive**: stage through the
off-screen columns (§4) in two passes. 384 columns × 512 rows of scratch exist for
exactly this kind of thing, and two passes of a 4.05 MB/s engine still beat one pass of
anything else on the card. **So b2 is an optimisation, not a requirement** — and §14
item 6 records that the fitter priced it out.

### 6.3 What it removes from software

⭐ **It is the single largest item in this card's software account**, because every
`H1`–`H5` cost in `docs/nitros9-hardware-improvements.md` is a `VDATA` stream that
this engine replaces — and `video-copyrect.md` §2 records that those five are one
capability class with no software substitute.

## 7. The mouse sprite — 16×16, bitmap mode only

| | |
|---|---|
| Shape | **16×16, two bits a pixel**: 0 transparent, 1 and 2 the two cursor colours, 3 reserved. **64 bytes** — row *r* is four bytes at +*r*·4: plane 0 columns 0–7, plane 0 columns 8–15, plane 1 columns 0–7, plane 1 columns 8–15, **bit 7 leftmost**. The pixel's code is (plane 1, plane 0) |
| Where it lives | ⭐ **VRAM: the top 64 bytes of `MAPBASE`'s 64 KB region**, `MAPBASE`·64K + `$FFC0` — bitmap mode has no other use for `MAPBASE`, and no map address reaches those bytes (§2.5). With `MAPBASE` 7 it is row 511, columns 960–1023. The CPU writes it like any other VRAM, through `WPTR`/`VDATA` or the span writer |
| Per displayed sprite row | **one spare access**, in slot 8 — horizontal sync, long after the last shift and long before the first. It is `v3dot`'s `MRQ` again, which bitmap mode leaves free: `v3dot` drives `FBA5..FBA2` with the sprite row, `v3scan` the rest with `{MAPBASE, all ones}`, and the four bytes arrive on the four lanes at once |
| The shift registers | **four `'165`**, two cascaded a plane, so each plane is a sixteen-bit chain (`partition.md` §8's escape, which §5 risk 3 says is a requirement). They parallel-load **straight off the four lanes** (`/PL` = `SPRLD`), so the shape never enters a CPLD or crosses the internal bus, and they shift in **zeros** behind the shape — so the column window needs no counter |
| Per dot of the sprite's sixteen columns | two bits shift out, and `v3dot` **re-registers** them as `SPRA1..SPRA0` onto LUT `A9..A8`, with their own enable `SPRAOE` |
| Colour | sub-palettes 1 and 2, all 256 entries of each loaded with one colour: **1,024 writes, ~2.9 ms**, and only when the cursor's colours change |
| Position | `SPRX` 10 bits, `SPRY` 9 bits, enable in `SPRH` b7 — the hotspot is the shape's top-left corner. **Moving the pointer is `SPRX`/`SPRY`/`SPRH` writes** |

⭐ **Why 16×16 and not 8×8** (2026-09-17; `history.md` has the 8×8 text). An arrow with
a tail does not fit in eight rows — `software/demo`'s pointer is 16×16 and its shape is
now this card's, pixel for pixel — and eight rows made the cursor an arrowhead whose
fill reached the outline's outer edge. The price is 48 more bytes of shape and two more
`'165`. `video3/bench/run-v3sprite.sh` renders every X phase, both 4-byte phases, the
edges, the line-doubling boundary and all four `VMODE`s against `v3model.py`, and all 36
positions match pixel for pixel; `v3card_tb` renders it from the parts at three positions
in both families (§15.4).

⭐ **Why a serialiser is affordable here and was not for Variant B.** §6.4.6 limit 3
refuses a glyph serialiser because its output feeds a foreground/background mux
*inside* index → LUT → output. Here the shift register's output is **re-registered by
`v3dot` before it reaches the LUT**, so the serialiser has a whole dot period to settle
and the critical path is untouched. **The register is the difference.**

⭐ **The position is counted, not compared.** A ten-bit equality is 2<sup>10</sup>
product terms in sum-of-products; instead each axis is an **up-counter loaded with the
complement** — `~SPRX` at `HLOAD`, `~SPRY` in vertical blanking — which is all-ones on
exactly the dot (row) the sprite starts, and all-ones is one term. The hit is held in a
register (`SHQ` for the rest of the line, `SVQ` for the rest of the frame), and the
horizontal window and its hit exist **only inside `ACTIVE`**, so a row loaded in slot 8
is not shifted out in the blanking before the picture. The sprite row `SR` is five bits:
rows 0–15, then it stops.

⚠ **No save-behind exists and none is needed** — the sprite is composed at scan time,
so `vidptr.asm`'s 7.9 ms of `VDATA` traffic and its `PtrGuard` on every primitive both
disappear. That is the single largest software saving this card offers. ⚠ **The shape
is ordinary VRAM, though**, so a copy or a clear that reaches `MAPBASE`'s last 64 bytes
changes the pointer; the driver keeps its scratch clear of row 511 for that reason (§4).

---

## 8. Scrolling — the playfield's by register, the console's by copy

### 8.1 Bitmap and tile mode

`graphics.md` §8 inherited whole: the scan counters have their own loadable registers
and sync generation is untouched.

| | |
|---|---|
| Vertical | the row counter loads from `VSCROLL` in vertical blanking and steps once a displayed row (§8.1). A 512-row torus in bitmap, 64 cell rows in tile mode |
| Horizontal | `HSCROLL`, **10 bits — 0 to 1023**, a **1024-column torus**, stepping **one pixel** at a time. `graphics.md` §8.2's two ranks of fetch latches with an output-enable select, because `c < HSCROLL[1:0]` is constant for a line |

⛔ **Per-*scanline* scrolling is gone, not scrolling.** One `HSCROLL` a frame is a
register write from the VBL service, which is how `overworld` moves its camera.

### 8.2 ⭐ Character mode scrolls by copying, and here is why

`video/` scrolls a text screen with `VSCROLL += 8` and a 32-row ring
(`graphics.md` §6.4.8). video3 does not, and the reason is arithmetic rather than
taste. One scrolled line at 80×25 — 24 rows of 320 bytes moved (80 four-byte cells,
§2.2), one row cleared:

| | card work | CPU work |
|---|---|---|
| `VSCROLL += 8` | one register write | **clear one row: ~540 µs** |
| **§6's copyrect** | 7,680 bytes at 4.05 MB/s = **1.90 ms of engine** | six register writes + **the same ~540 µs clear** |
| the same move by CPU, no engine | — | ⛔ **20.0 ms** |

⚠ **Derived, by scaling the two-byte cell's figures to four bytes** (271 µs, 3,840 bytes
and 10.0 ms, `history.md`); the driver port's own measurement is in §12.

⭐ **The clear dominates the CPU and both paths pay it**, so at 115.2 kbaud (~144 lines
a second) the two cost **7.8 % and 8.0 % of the CPU**. The difference is noise. ⚠ The
copy is **1.90 ms of *engine*** — 27 % of the engine at that line rate, and the engine
becomes the limit only past ~500 lines a second, which no serial port reaches. At
80×60 it is 4.7 ms of engine and the CPU's share is unchanged. ⚠ **4.05 MB/s assumes
every spare access**, and in character mode the map takes one slot in two during the
picture (§2.5), so the engine times are lower bounds — §14 item 8.

**What copying buys for that 0.2 %:**

| | |
|---|---|
| ⭐ no ring | 64 rows are 64 rows. `graphics.md` H9's defect — *more line feeds in a frame than the runway has rows shows a recycled row* — **does not exist here**, at any geometry |
| ⭐ no ring bookkeeping | `video/`'s driver keeps "a shadow of its codes, **by ring row**" and repaints the map from it at `Select` (`video-console.md`). A map that never rotates needs neither |
| ⭐ no `VSCROLL` in cell mode | the row counter's load and wrap are tile mode's alone |

⚠ **And the last row of that table is the catch**: the CPU move is 20.0 ms, so
**character mode without the copy engine is not viable at terminal speeds.** §6 is
not an optimisation here, it is a dependency — which is why §2.5 spends 32 KB to give
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
read (`v3host`'s `IRQPEND`, onto the `VSTAT` `'244`) and any write to `VSTAT` clearing
it. The enable, `CTRL` b6, is held on `v3host` beside `/IRQ`.

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
| `+$0B` | `WADV` | b1..0: 00 continue, 01 next row same column, 10 by the stride. ⭐ **b2: `WPTR` steps by TWO**, which is what makes §2.2's cell two stores — ⚠ every advance of `WPTR` steps by two while it is set, a span's retires and a `VDATA` read's post-increment included |
| `+$0C` | `VDATA` | the VRAM byte at `WPTR`, read or write, post-increment |
| `+$0D` | `VSTAT` | b7 `SPANBUSY`, b6 `VBLANK`, b5 `HBLANK`, b4 `CBUSY`, b1 `PBUSY`, b0 IRQ pending. **Read through a `'244`** — live macrocells have no register-file path (§12.1's reason) |
| `+$0E`–`$0F` | `PIDX` | **16 bits** — the whole LUT. Auto-increments after `PDATH` |
| `+$10` | `PDATL` | `GGGBBBBB` |
| `+$11` | `PDATH` | `RRRRRGGG`; the write posts the commit to the next `HLOAD` |
| `+$12`–`$14` | `CPTR` | **copyrect source**, 19 bits |
| `+$15` | `CWIDTH` | bytes a row, low 8 |
| `+$16` | `CHEIGHT` | rows, low 8 |
| `+$17` | `CCTRL` | b0 `GO`; b1 and b2 reserved — there are no direction bits (§6.2); b4..3 `CWIDTH[9:8]`; b5 `CHEIGHT[8]` |
| `+$18` | `TILEBASE` | the tile bank, or character mode's glyph bank — ⭐ **one register, because a glyph *is* a tile** |
| `+$19` | `MAPBASE` | |
| `+$1A` | `SPRX` | b7..0 |
| `+$1B` | `SPRY` | b7..0 |
| `+$1C` | `SPRH` | b1..0 `SPRX[9:8]`, b2 `SPRY[8]`, b7 sprite enable |
| `+$1D` | — | ⭐ **spare**, like `+$1F`: a register-file byte that reads back what was written and has no function. The sprite shape is in VRAM (§7) |
| `+$1E` | — | ⭐ **spare**, the same |
| `+$1F` | `FCNT` | ⭐ **spare — no logic reads or writes it**, and a byte of the register file like the others, so it reads back what was written. **The VBL service keeps the low byte of its frame count there**, which is how a process holding the screen sees a frame end for the price of one read where asking the driver is a ~1.4 ms system call (`overworld`'s hero — `demo-report.md` §10) |

⚠ **`+$1F` assumes the register file decodes all 32 offsets**, which is what a 32-byte
file addressed by `RA4..RA0` does and what the emulator's model does. Nothing in the
design reads the byte, so no fit and no equation depends on it; if a future revision
gives `+$1F` a function, the driver loses a convenience and not a feature.

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
| `'153` pixel mux, index latch, output register | §6.1 | **Required** — and §3 drives the LUT's high half beside it, from CPLD registers rather than a latch |
| Posted-write capture on E-fall | §3.1.1 | **Required** — the span writer's trigger |
| Span writer, four `WMODE`s, `WADV`, broadcast | §7.4 | **Required** — §5 |
| Register file + `'245` read-back | §3.2 | **Required** — `WFG`/`WBG`, `SPANLEN` and the column shadows; the `'245` also carries a card write onto the internal bus |
| `WFG`/`WBG` adjacency as an address line | §7.4 | **Required** — it is why per-pixel colour selection is free |
| VRAM read prefetch, `VDATA`, `/WAIT` on both | §11 | **Required** — save-behind, read-modify-write, and the CPU's only way in |
| Cell addressing by concatenation | §6.4.1 | **Required**, ⚠ **widened**: six-bit row, four-byte cell (§2.5) |
| Map fetch pipelined one cell ahead, two-stage `MAP`/`MAPQ` | §6.4.9 | **Required**, ⚠ **widened** — the code keeps two stages and the attribute takes three (§2.5), all in `v3scan` |
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
| `SPANLEN` as its own part (`vlen`) | §14.1 | ⭐ **Absorbed** — `SPANLEN` is `v3ptr`'s `NSL7..NSL0`, `vlen`'s complement-and-count-up idiom, on the part that already takes the internal bus |
| `rfa`, the register-file address GAL | §10.1.6.3 | ⭐ **Absorbed** — `RFA4..RFA1` are `v3host`'s (the decode and §7.2's reload walk), `RFA0` is `v3ptr`'s (the mask bit) |
| ⭐ **Byte lanes: four `'245`s and a lane decode** | §14.2.2 | **New** — `video/` puts the CPU byte on all four lanes and selects with `/LB`//`UB`; video3 has four 8-bit sources and a copy that reads a lane, so each lane gets a transceiver to the internal bus and `v3lane` decodes their enables and the byte enables (§13.1) |

---

## 12. What software gains and loses

| | |
|---|---|
| ⭐ **Gains** | per-cell colour in the fast console — so **ANSI art renders at 4 `VDATA` writes a cell instead of 11–13** (code, attribute and the two unused lanes, §2.2); all 256 CP437 code points (inverse is an attribute bit, not half the font); 80×50 and 80×60 fast text; a mouse pointer that costs four register writes instead of 7.9 ms and a `PtrGuard` on every primitive; window scroll and `Select` in single-digit milliseconds |
| ⛔ **Loses** | `SS.Raster`, `SS.RastOff` and everything per-scanline — `rastbar`'s colour bands and `wave`'s sine warp. ⭐ **`overworld` is unaffected**: its camera is one `HSCROLL` write a frame through `SS.Batch`, not a list |
| ⚠ **Unchanged** | the CoWin protocol, the escape set, the extensions `$60`–`$69`, the status calls, the VBL service and the frame batch |
| ⚠ **What the four-byte cell and the VRAM shape cost the driver** | the NitrOS-9 port (`ca_v3txt`, `ca_tile`, `overworld`, `vidptr3`, `vidxcl`, `vidcore`, `vidsvc`, `vidcpy3`, `armvid.d`), the emulator and the `video3/bench` generators follow §2.2, §2.5 and §7. The driver port reports the console **~8.5 % slower a character** (four `VDATA` writes a cell, not two) and a copy-scroll of **320 bytes a row** (`CWIDTH` needs its ninth bit) costing **+1.8 ms a line at 80×60**; the copy engine's scratch rows are **480–510**, because the shape is in row 511; and ⛔ **CoArm is at exactly its 16,384-byte limit** |

---

## 13. The discrete parts, derived

**Every row below is derived from a requirement in §0–§9, not from `video/`'s parts
list.** `video/`'s BOM (`hardware/place/parts.ts`) is quoted only as the *reference
implementation of a mechanism* — where a row says "as `video/`", the mechanism is the
same and the reason is restated. The list places (§13.5); ⚠ **nothing here is drawn or
costed in current** (§14 item 13). The programmable logic is `partition.md`'s — four
`ATF1508AS` and the `v3lane` `GAL22V10` — and is counted in §13.5, not here.

### 13.1 Required, and why

| Part | n | Required by |
|---|---|---|
| **`AS6C8016` 512K×16** | **2** | §2.3. A 72 ns access does not fit twice into a 158.9 ns slot, so the interleave is a cliff and not a slope (`graphics.md` §2.1) — and 640×480×8bpp needs 307,200 bytes. Two ×16 parts give four bytes an access and seventeen address bits |
| **`IS61C6416AL-12` 64K×16** | **1** | §3. ⭐ **And video3 is the first design that needs the whole part**: `video/` bought 64K words for *width* and wrote 256 of them; here A15..A8 carry the attribute |
| **32K×8 register file** | **1** | §5. ⛔ **It cannot be macrocells**: the span-mask bit *is* this SRAM's address bit 0, which is what makes per-pixel colour selection free. It also holds `SPANLEN` and `WPTR`'s and `CPTR`'s column shadows |
| **R-2R ladders, 5/6/5 bits + 3 buffers** | 3 + 3 | §9.1. RGB565 out of the output register. **Not ICs**, counted on their own line as in `video/` |
| `74AHCT574` fetch latches | **8** | §2.3 and §8.1. Four hold one access's 32 bits; the second four are `graphics.md` §8.2's — **one-pixel** `HSCROLL` needs two fetch groups live at once, because a four-byte fetch group is four pixels. ⚠ **§13.3 trade 2** |
| `74AHCT153` 4:1 mux | **4** | §2.3. One of the four latched bytes per dot. ⚠ 0 if the tri-state turnaround closes at 39.72 ns — `graphics.md` §19 item 2, unchanged here |
| `74AHCT574` index latch | **1** | §3. LUT A7..A0 |
| `74AHCT273` output register | **2** | §3, §9.2. Sixteen bits post-LUT, and its `/MR` is what blank-to-black drives |
| `74AHCT163A` `PIDX` low | **2** | §10. Counts, because a sub-palette load walks entries |
| ⭐ `74AHCT574` `PIDX` high | **1** | §10. **NEW, and a latch rather than a counter** — software sets the sub-palette and walks within it, so the high byte never counts. **That is one package rather than two more `'163`** |
| `74AHCT244` `PIDX` onto the LUT bus | **2** | §13.1 of `graphics.md`. **Sixteen bits now, so two** |
| `74HC573` `PDATL`/`PDATH` | **2** | §10. The LUT word is sixteen bits and the bus is eight; something has to assemble it |
| `74HC574` posted-write data | **1** | §5 and §6. The CPU's byte for a direct-mode write, **and the copy's byte in flight** — `PWCK` is the CPU's VRAM write or the copy's read; `PWOE` (`v3lane`) puts it on the internal bus for the write access |
| ⭐ `74AHCT245` **lane transceivers** | **4** | §4 and §6. **NEW.** The framebuffer is 32 bits and every other VRAM byte path is 8 — the register file (a span's colour), the posted-write `'574` and `vread`. One `'245` a lane, A on the internal bus; `DIR` from `v3host`, high = internal bus to lane, **held for the whole access** so it has turned before `/WE`; `/OE` from `v3lane` for the one lane of a prefetch, a copy access or a span retire |
| `74HCT245` register-file read-back | **1** | §10. `WFG`, `WPTR` and the rest onto `D0`–`D7` — and, the other way, a card write onto the internal bus |
| `74HCT574` `vread` | **1** | `VDATA`. The prefetched VRAM byte — `RDCK` is the prefetch's alone |
| ⭐ `74HC165` sprite shift registers | **4** | §7. Two cascaded a plane, loaded off the four lanes; their serial outputs go to `v3dot` (`SQ0`, `SQ1`) |
| `74HC244` `VSTAT` | **1** | §10. `SPANBUSY`, `CBUSY` and `PBUSY` are live macrocells with no register-file path |
| `74HC244` fan-out | **1** | §9 and `graphics.md` §12.2 — `HSYNC`/`VSYNC` to a backplane pin at TTL, plus clock fan-out |

**Discrete total: 39**, against `video/`'s 30, **plus five programmable parts — 44 ICs**
(§13.5). The one new datapath is the four lane `'245`s; §13.3 trade 1 made the copy
engine byte-granular, so it needs no latch of its own.

⭐ **And no `'138` for the palette's load strobes.** `PIDX` low (`'163` `/LD`, +$0E),
`PIDX` high (`'574` clock, +$0F), `PDATL` and `PDATH` (`'573` LEs, +$10/+$11) are
`v3dot`'s `LDPIDXL`/`LDPIDXH`/`LDPDATL`/`LDPDATH`, a term each off the register
broadcast. A `'138` cannot decode them: +$0E/+$0F and +$10/+$11 differ in all of
`RA4..RA1`, which is four enables' worth of condition on a part with three.

### 13.2 Not required — deleted with a reason

| Part | `video/` | Why video3 does not need it |
|---|---|---|
| `74HCT244` list-descriptor byte | 1 | §0 deletes the display-list engine, and this package existed only to put a descriptor byte on the internal data bus (`graphics.md` §10.3.3) |
| Posted-write **address** latches | 0 | `video/` listed three and no design ever clocked them (§3.1.1, §19 item 44). ⭐ Recorded so video3 does not re-add them: **every CPU VRAM access is at `WPTR`**, so the physical address selects the window and nothing else |
| A dot-clock oscillator | 0 | `graphics.md` §5.3 — the card is clock-slaved to the backplane, and should stay so |
| `BORDER` hardware | 0 | §9.3: VGA has no overscan, the porches must be black for the back-porch clamp |
| A sprite shape store | 0 | §7 puts it in VRAM, in `MAPBASE`'s last 64 bytes: no package, and one spare access a sprite line that bitmap mode has free |

### 13.3 ⚠ Three trades to settle before the equations

1. ⛔ **SETTLED 2026-09-16: there is no copy-read latch, and "borrow the fetch rank"
   was never possible.** A `'574` has **one** output enable, and the fetch rank's output
   is committed to the *pixel* bus — `graphics.md` §8.2 ties both ranks to the `'153`'s
   inputs and makes them exclusive with that enable. Wiring a rank to the framebuffer
   data bus as well would put **both ranks on the `'153`'s inputs** whenever the copy
   drove. Two outputs, one net.

   ⭐ **But the latch is not needed, because the four-byte group is not.** A
   byte-granular copy reuses a latch the card already has — §5's posted-write `'574`,
   which the read access clocks and the write access drives back out — and the reuse is
   safe under a rule that already exists: `/WAIT` holds a CPU VRAM access while `CBUSY`
   exactly as it does while `SPANBUSY`, so no CPU byte lands in it mid-copy. `vread`
   stays the prefetch's, and a copy moves `WPTR`, which is one of the things `RDVALID`
   already falls on.

   **It costs 4× the copy time and buys four packages** — and those four are what pays
   for the sprite's `'165`s (`partition.md` §8). ⭐ It also deletes an alignment rule:
   with no fast path, column congruence stops mattering to software.
2. ⭐ **SETTLED 2026-09-16: `HSCROLL` steps ONE PIXEL, and the second fetch rank stays.**

   ⚠ **First, the words.** A fetch group is four bytes, and this card is chunky 8bpp, so
   a fetch group is **four pixels**. `graphics.md` §8.2's "byte-granular" therefore means
   **one pixel** — the finest step there is — and the alternative is **four**. The same
   phrase means the *coarsest* step on the GIME, where a byte is two or four pixels
   (`docs/coco3_c64.md` §5), and that ambiguity has already misled one reading of this
   section. **video3 says "one pixel".**

   | | `HSCROLL[1:0]` | fetch ranks | step |
   |---|---|---|---|
   | **as built** | used | **2** — 8 × `'574` | **1 pixel** |
   | the alternative | forced to 0 | 1 — 4 × `'574` | 4 pixels |

   **What the second rank buys is not resolution, it is a floor on speed.** 4 px a frame
   at 70 Hz is 280 px/s and looks fine — it is what the demo does. What one-pixel
   granularity adds is everything *slower*: a walking-pace camera at 1 px a frame is
   70 px/s, and at four-pixel steps that becomes **4 px every four frames, 17.5 steps a
   second**, which is visible judder.

   ⚠ **And the demo does not exercise it.** `software/demo/tools/mkgame.py`'s overworld
   is `carry(±4, 0, 160)`: over 512 frames the camera's X takes 161 distinct values and
   **every one is a multiple of 4**. The other one-pixel user, `wave`'s sine warp, went
   with the display list (§0).

   ⭐ **It is kept anyway, and the reason is asymmetry rather than need.** §13.3 trade 1
   returned the four packages this trade used to be the payer for, so the board places at
   **44 ICs, 78 %** with everything (§13.5) — the cost is affordable *now*, and the
   capability is **unrecoverable later**. Nothing on this card can substitute: there is
   one 16 × 16 sprite and it is bitmap-only, and copyrect is 31.6 ms a screen, twice a
   frame. ⭐ And the rank select is per chip, as `graphics.md` §8.2 has it — `v3dot`'s
   `OEA0..2`/`OEB0..2`, chip 3 strapped to rank B — with the `'153` phase `MUXSEL` = dot +
   `HSCROLL[1:0]`; `v3card_tb` displays fine scrolls 1, 2 and 3.

   ⚠ **The one thing that would reopen it is power** — §14 item 13.
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

### 13.4 Two things that could move between silicon and packages — both in silicon

- **The map word's pipeline is in `v3scan`.** `graphics.md` §6.4.9 needs the map
  pipelined one cell ahead, with `MAP` fetched while `MAPQ` is still being displayed;
  video3's code takes those two stages and its attribute three (`MAPA` → `ATQ` → `ATO`,
  §2.5), and the last stage drives LUT `A15..A8` itself. `partition.md` §2.2 has the
  discrete alternative and why it was not taken.
- **The sprite's two bits onto LUT `A9:A8` are `v3dot`'s `SPRA1..SPRA0`**, re-registered,
  with their own enable. There is no `ATTR` latch to stand off: `v3dot` decides `ATOE`,
  `SPRAOE` and `PIDXOE`, so `graphics.md` §13.1's discipline — *one* part deciding every
  master so the bus can never have two — holds by construction, and `v3card_tb` asserts
  it every dot (`LUTA_FIGHT`).

### 13.5 ⭐ What the board says — measured, not estimated

`hardware/place/parts.ts` carries video3 as an **alternate** (a design that is not in
the machine — it replaces `video`, so it cannot own `$FF60` and cannot be a `CARDS`
entry), and `npm run check:place` places it through the same skyline packer that
measures every other card. **The card is 44 ICs**: four `ATF1508AS` in PLCC-84, the
`v3lane` `GAL22V10` in DIP-24, and §13.1's 39 discrete packages.

| | ICs | courtyard | 240 mm |
|---|---|---|---|
| `video`, the built card | 33 | 124.4 cm² | places, 59 % |
| ⭐ **video3 as built** — four `ATF1508AS` + `v3lane` + 39 | **44** | 163.9 cm² | **places, 78 %** — `check:place` asserts it, and that 24 cm is the shortest length that holds it |
| video3 without `v3lane` and the lane `'245`s | 39 | 149.1 cm² | places, 71 % — the card that could not move a byte (§14 item 18) |
| video3 with a fifth `ATF1508AS` | 45 | 176.5 cm² | ⛔ **does not place** |
| video3 with a fifth `ATF1508AS` **instead of** `v3lane` | 44 | 173.1 cm² | ⛔ **does not place** |

⛔ **THE CEILING IS FOUR PLCC-84s, and 240 mm is the longest board there is.** A
PLCC-84 is 33 × 33 mm, so a fifth one is worth three DIP-20s of skyline and the board
refuses it — even in place of the GAL, at the same IC count. **What the ceiling limits
is PLCC-84 area, not programmable parts**: `v3lane` is a DIP-24 and places beside four
`'245`s. That is a constraint on §14 item 4 that no amount of prose would have produced,
and it is the reason this list exists as a file rather than as a table in this document.

**The trades of §13.3 against it:**

| | |
|---|---|
| Trade 1 — no copy latch | taken: **−4**, and they paid for the sprite's four `'165` (`partition.md` §8's escape, §5 risk 3's requirement) |
| `MAP`/`MAPQ` discrete (`partition.md` §8's other escape) | **not taken** — `v3scan` holds the map word in silicon (§13.4) |
| The `ATTR` `'574` | **gone** — `v3scan`'s `ATO` drives the LUT itself (§3), and its package went to the lane transceivers |
| ⛔ trade 3, the tri-state pixel bus | **settled the other way** |
| ⛔ trade 2, four-pixel `HSCROLL` | **settled the other way** — one pixel is kept |

## 14. Open items

0. ⭐ **CLOSED 2026-09-16 — both cell-budget escapes are paid for.** §13.3 trade 1 is
   settled: the copy engine is byte-granular and needs no latch, which returns four
   packages, and they pay for the sprite's four `'165` — `partition.md` §5 risk 3's
   escape, which `v3dot` requires. Risk 2's escape, `MAP`/`MAPQ` in four `'574`, was not
   needed: `v3scan` holds the map word in silicon (§13.4). `npm run check:place` places
   the card as built, **44 ICs** (§13.5), so the package budget does not gate the
   macrocell budget.
1. ⛔ **§3's timing claim has not been analysed.** *"Sixteen address lines settling
   together cost what eight do"* is the card's load-bearing assumption, and everything
   in §2.2 and §7 rests on it. It wants the LUT's datasheet numbers against a real
   fan-out and a real board, not an argument. **Nothing else should be drawn until
   this is answered.**
2. ⭐ **CLOSED 2026-09-19 — §7's sprite position logic is fitted and simulated.** It is
   **counted, not compared** (§7): up-counters loaded with `~SPRX`/`~SPRY`, all-ones on
   the sprite's first dot and row, hit registers `SHQ`/`SVQ`, and a five-bit row that
   stops at 16 — in `v3dot`'s fit beside the raster. `v3card_tb` renders the sprite from
   the parts at (101, 37) and (3, 0) in `VMODE` 11 and at (618, 190) in `VMODE` 00, every
   pixel of each frame against the expected picture, and found three defects on the way
   (§15.4, 20–22).
3. ⚠ **The framebuffer address mux is the first thing to count, and this is the
   budget rather than a verdict.** The sources video3 needs are the bitmap scan
   address, the cell/tile concatenation, the write pointer, the map fetch, and §6's
   `CPTR` — **five**. An ATF15xx macrocell holds about five before it cascades
   (`graphics.md` §6.4.1 states that as a property of the family, not as a fit
   result), so five is *at* the budget and a sixth source is where cascading starts.
   ⛔ **This is a number to design against and then check, not a limit inherited from
   anywhere** — see item 4.
4. ⭐ **The partition is [`partition.md`](partition.md): four `ATF1508AS` and one
   `GAL22V10`**, and §13.5 says four PLCC-84s is the most that places — **so video3 is at
   its ceiling**. **ALL FIVE ARE FITTED:**

   | | cells | I/O | cascades | |
   |---|---|---|---|---|
   | `v3dot` | 121/128 | 63/64 | ⚠ **5** | the raster, the dot path, the sprite, the arbiter, the palette's load strobes |
   | `v3scan` | 112/128 | 63/64 | 3 | the scan and cell addresses, the map word, the attribute onto the LUT |
   | `v3ptr` | **124/128** | 58/64 | 3 | the pointers, the span writer, the copy's decodes, the lane, `VWE`, the step |
   | `v3host` | 58/128 | ⛔ **64/64** | 0 | the backplane, the registers, the palette commit, the copy's phase machine, the reload walk |
   | `v3lane` | a `GAL22V10`: 10 of 10 macrocells, 10 inputs | | | the lane `'245`s' enables, the byte enables, `PWOE`, `RFOE` — with a CUPL reference and `gal/video3/v3lane.check.ts` in `npm run check` |

   `v3scan_mq` — the same part with the map word in four `'574` — is the discrete
   alternative, and its fit is of the 2026-09-16 term list (`partition.md` §2.2). ⚠ It
   predates §2.5's four-byte cell and three-stage attribute, so it prices a design that
   no longer exists and is kept only as the evidence for that decision.

   ⛔ **NO NUMBER FROM `video/`'s FIT APPLIES HERE.** `video/` is three `ATF1508AS` whose
   utilisation is recorded in `hardware/gal/cpld/*.fit`; **those figures describe a
   different design** — one with a display list, per-scanline scrolling, a one-byte map
   and no copy engine. **What transfers from `video/` is mechanism and arithmetic; what
   does not transfer is utilisation.**
5. ⭐ **CLOSED 2026-09-19 — `vlen` and `rfa` are absorbed** (§11's last two rows).
   `SPANLEN` is `v3ptr`'s, and the register file's address is `v3host`'s `RFA4..RFA1` and
   `v3ptr`'s `RFA0`.
6. ⭐ **CLOSED by `v3ptr`'s fit.** The direction bits cost **18 macrocells and 16
   cascades** — `v3ptr_both` against `v3ptr`, §6.2's table — so they are not built, and
   an overlapping copy stages through scratch in two ascending passes.
   `bench/v3copy` checks it.
7. ⚠ **The sub-palette load cost is a software rule**: 512 entries for character
   mode's 256 pairs, 512 more for the sprite's two colours, ~2.9 ms each, and §13.1's
   `PBUSY` rule applies to every one of them.
8. ⚠ **The spare-access budget has five requesters and no cadence check.** In `v3dot`'s
   priority order: **the map** (character and tile mode, one access a cell — every other
   slot through the picture, §2.5), which in bitmap mode is **the sprite's row fetch**
   instead (one access a line, slot 8); **the CPU's read prefetch**; **copyrect** (two
   accesses a byte); and **the span writer** (one a retire) — against one spare access a
   slot. ⭐ **What `v3card_tb` shows**: a 13 × 5 copy under character mode lands byte for
   byte in **exactly 130 granted copy accesses for 65 bytes** — two a byte, the same count
   as in bitmap mode — while the map takes its one access a cell. ⚠ That is a count of
   accesses, not of time: how long the copy waits behind the map, and whether the span
   writer and the prefetch still get slots under a running copy, are what a
   `cadence.check.ts` equivalent would decide, and it is not written. §6.1's rates are
   derived, not measured.
9. ⭐ **CLOSED by §8.2.** `video/`'s ring-runway defect — H9's *more line feeds in a
   frame than the ring has spare rows shows a recycled row* — **does not exist here**,
   because character mode has no ring.
10. ⭐ **CLOSED by §2.5.** The 81st code a scrolled text line would fetch does not
    arise, because character mode has no horizontal scroll.
11. ⛔ **Character mode DEPENDS on §6, and the two must be scheduled together.** The
    CPU move is **20.0 ms a line** (§8.2), so if copyrect does not fit, character mode
    does not work at terminal speeds and the ring has to come back with its defect.
    They are not independent features.
14. ⭐ **CLOSED 2026-09-19 — both sequencers are built, split across two parts, and
    `v3card_tb` runs them** (§15.4). `history.md` has the record: the 2026-09-18 census
    that found the four parts were a datapath and an arbiter with **19 control lines**
    nothing produced, the `V3_SEQ` variants, and the refusals that forced the split.

    **The span writer is on `v3ptr`**, a port of `video/`'s `seqctl.jedec.ts` minus the
    display list's `!LRUN`, with `TC` folded in because `SPANLEN` is on the same part.
    The mask loads on `WSTBV`, the posted write's level, while the CPU's byte is on
    `IDB`; the span **starts on `WSTART`**, the one-dot edge `v3host` makes at the end of
    that write, when the `'245` has let go and the file is back at +$05 — so `SPANLEN`
    loads with no address of its own.

    **The copy engine is split.** `CEOR` and `CHLAST` stay on `v3ptr` beside the ten and
    nine counter bits they decode, and the **phase machine** is on `v3host`. Two accesses
    a byte with one spare access a slot is **two slots a byte**, so the phase is all the
    state the sequence needs. Seven signals cross: `CBUSY`, the two decodes, and
    `CRDSEL`/`CSTEP`/`CROWADV`/`CWLOAD`/`CDONE`; `v3host` also makes the copy's request
    `RCPY` and the lane `'245`s' `DIR`. ⚠ **Both sequencers on `v3ptr` does not
    fit**, and not for cells: the refusal is LAB grouping, with Nodes+FB already over
    125 % on one — so `partition.md` §2.3's "~10 macrocells for the span and copy
    sequencers" does not describe this part, and §4's "a fifth part for the copy
    engine — it does not place" closes the other way out.

    ⭐ **The tick is a literal, not a macrocell.** Both sequencers need the spare window's
    *last* dot, because the arbiter is pure combinational grant logic and a step on every
    dot of the window would move four bytes a slot (`design-review2.md` V-4). `SPARE` is
    `!DP1`, the grants contain it, and `v3dot` exports `DP0` — so `GSPN & DP0` *is* the
    tick, for one literal on a term the receiver has anyway.

    **`WMODE` is `v3dot`'s**, `CTRL` b5..4, sent as two **combinational** pins `WM0`/`WM1`
    to `v3ptr` and `v3lane` (`partition.md` §3).

    ⭐ **§7.2's end-of-row column reload** is a one-hot four-dot walk on `v3host`, so the
    states *are* the strobes: `RP1` → +$08 → `WC7..WC0`, `RP2` → +$09 → `WC9..WC8`, and
    `RP3`/`RP4` → +$12/+$13 for `CPTR`, only when `CRLD` says the trigger was a copy's.
    The walk is also what gives the register file an address at all: `RFA4..RFA1` are
    `v3host`'s, which is the decode, and **`RFA0` is `v3ptr`'s**, because §5 makes the
    file's bit 0 the mask bit and the serialiser is there. ⚠ **Two strobes a pointer**,
    because +$09 carries `WC9..WC8` in D1..D0 **and `WR5..WR0` in D7..D2**, so reusing the
    CPU's `LDWP1` would undo the row advance the same span just made. ⚠ **And separate
    from the CPU's**: `LDA # RLDA` is the obvious saving, and `access.jedec.ts` records
    that CUPL substitutes the intermediate, every hold term doubles, and the fitter
    aborts.

    The requests into `v3dot`'s arbiter and the rest of the control lines:

    | | |
    |---|---|
    | `RMAP` | `MRQ`, `v3dot`'s registered request for the current slot (§2.5) — the map's in character and tile mode, the sprite row's in bitmap mode |
    | `RRD` | `v3host`'s `RDREQ`: `!RDVALID`, **and only while the internal bus is free** — not at `WSTART`, not while `SPANBUSY`, not through the reload walk, and not through E-high of any card access but the `VDATA` read that is waiting for it |
    | `RCPY` | `v3host`'s, `CBUSY` **and no reload walk**: the walk's last two dots are the next slot's spare window, where the copy's next read would put a lane on the bus the walk is loading `CPTR`'s column across |
    | `RSPN` | `SPANBUSY` itself — a span in flight *is* the request |
    | `WRCYC` | `!RW & E`. ⚠ A 6809E write is only valid in E's second half |
    | `RDCK` | the `vread` `'574`'s clock, **active low** so the rising edge ends the access — **the prefetch's alone** (`GRD & !RDVALID`) |
    | `PWCK` | the posted-write `'574`'s clock, active low for the same reason: `WSTBV`, the CPU's VRAM write, **or the copy's read tick** — trade 1's byte in flight |
    | `RSTART` | `RPQ & !E`, §11's **post-increment** — the dot after a VRAM read's E falls. It reaches `WPTR` as `v3host`'s `WSTEP = CSTEP # RSTART`: one pin, because every `v3ptr` LAB is at 38 or 39 of the fitter's 40 inputs and a third `WINC` term did not fit |
    | `IRQEN` | `CTRL` b6, on `v3host`, which pays a data-bus pin for it — `v3ptr` refused it, and `v3dot` keeps no copy |

    **`SPANLEN`, `CWIDTH` and `CHEIGHT` are down-counters built up**: `counter.ts` has only
    an up-counter, so each holds the complement and counts up, and the terminal decode is
    one product term (`vlen.jedec.ts`'s idiom). It is `..11110`, not `..11111`, because
    `CWIDTH` is the plain byte count N and the counter is sampled before the edge that
    steps it. `CWIDTH` loads at every row end **and while idle** (`CWLOAD = CROWADV #
    !CBUSY`), so the first row starts from it too. **The mask's retire count is a ninth
    serialiser bit**, `MS8`, loaded as 1 behind the eight: it reaches `MS1` with only zeros
    above it on exactly the eighth retire, one cell where a counter was three.

    The fits are item 4's. ⚠ **`v3dot`'s cascades are five and `v3scan`'s three.**
    `CLAUDE.md`: a change in cascades is a timing change even when the cell count is flat.
    Nothing on this card has been timed (item 1), so it is recorded rather than assessed.

    ⛔ **`v3host` is 64/64 — full — and `v3ptr` has six cells**, with Nodes+FB at 133 % and
    seven of its eight LABs at 39 of 40 inputs — the card's ceiling, and `partition.md`
    §7.1's point that the binding constraint is pins. `keyed-copy.md` §7.2's keyed compare
    wants **eight** pins on whichever part gates the write strobe. That part is now
    `v3ptr`, which makes `VWE` for both writers, and it has **seven**: the `74HC688`
    version — one pin — is the only one that fits anywhere on this card.

15. ⭐ **CLOSED 2026-09-18 — three pin senses, by `npm run check:pins`.**
    `v3host`'s `reg`/`comb` helpers hard-coded `assertedLow: false`, so nothing on
    that part *could* be declared active-low: `/IOSEL` was an active-high input and
    the open-drain `/WAIT` and `/IRQ` active-high outputs, while the terms used the
    asserted sense throughout. Fixed, and the card is in the check, so the class
    cannot come back. ⭐ **Rule 3 (`CONSUMERS`) reaches video3 too** — `video3_card.v` is
    its board — and found that none of video3's pins driving an active-low discrete
    input had been declared active-low (§15.4, defect 30).

13. ⛔ **THERE IS NO POWER BUDGET, and §13 measures packages and never watts.**
    `graphics.md` §14.1 costs `video/` at **~0.6–0.95 A** from its datasheets; video3 has
    four `ATF1508AS` and a `GAL22V10` where `video/` has three CPLDs, 39 discrete
    packages where it has 30 — the sprite's four `'165` among them at dot rate — and
    **not one of them has been costed in current.** ⚠ The dot path is where it would
    bite: §14.1's figure has ~15 AHCT packages switching at 25.175 MHz at 9–22 mA each.
    **This is the only open item that could reopen a settled trade** — §13.3 trade 2's
    four fetch latches are the cheapest thing to give back, and giving them back is a
    deletion rather than a redesign.
12. ⚠ **One stride or two — open** (§2.5). The map has the framebuffer's 1024-byte
    stride so §6's engine needs no second one, at **32 KB** — §2.2's four-byte cell makes
    a row 320 bytes, so a packed map would take a 512-byte stride. The alternative is a
    stride select, a mux on which bit the row step lands. **Cost both before a board**;
    the choice is a default, not a finding.
16. ⭐ **CLOSED 2026-09-19 — the map is fetched.** `MAPLD` and the map grant were
    products of `SPARE` (dots 0–1) and `CELLTICK` (dot 3), so neither could fire and
    character and tile mode fetched no map. Both now come from `MRQ`, `v3dot`'s registered
    per-slot request (§2.5), and `v3card_tb` renders character mode at 80 × 60 and 80 × 25
    and tile mode at both cell phases, every pixel (§15.4, defect 15).
17. ⭐ **CLOSED 2026-09-19 — the sprite is in the card model.** Its shape is in VRAM,
    `MAPBASE`'s last 64 bytes (§7), fetched in one spare access a line and loaded straight
    into the four `'165`s off the lanes, so no register-file address beyond `RFA4..RFA0`
    is needed. `video3_card.v` has the four `'165`s and `v3card_tb` renders the sprite
    (item 2).
18. ⭐ **CLOSED 2026-09-19 — the board has every signal it needs from a package.**
    `video3_card.v` reached into its parts for seven (`GAP_1`–`GAP_7`); it now reaches into
    none outside the benches' back doors, and `check:reach` counts it as video3's board:

    | | now |
    |---|---|
    | `GAP_1` the byte lane | `v3ptr`'s `LANE1:LANE0`, its address mux's two low bits — `WPTR`'s or, for the copy's read, `CPTR`'s |
    | `GAP_2` `/VWE`, `/VOE`, the byte enables | `VWE` is `v3ptr`'s, for both writers (a span retire, the copy's `CSTEP`); the byte enables are `v3lane`'s — all four for a read, the lane alone for a write |
    | `GAP_3` the fetch ranks' clock | `SPARE`, whose rising edge ends the display access |
    | `GAP_4` the map word's part select | gone: §2.2's four-byte cell puts every word in part 0 |
    | `GAP_5` `VSTAT` b0 | `v3host`'s `IRQPEND` |
    | `GAP_6` the copy's write data | the copy reads into the posted-write `'574` (`PWCK`) and writes from it (`PWOE`) |
    | `GAP_7` the write data's source | the internal bus has one driver at a time — a lane `'245`, the posted-write `'574` (`PWOE`), the host `'245` or the register file (`RFOE`) — decoded by `v3lane` |

    ⭐ **And no `'138` for the palette's load strobes**: `v3dot` decodes all four off the
    broadcast (§13.1), because a `'138` cannot.
19. ⭐ **CLOSED 2026-09-19 — `HSCROLL` steps one pixel in the model.** The rank select is
    per chip — `v3dot`'s `OEA0..2`/`OEB0..2`, chip 3's pair strapped — and the `'153`
    phase is `MUXSEL` = dot + `HSCROLL[1:0]`, as `graphics.md` §8.2 has it. `v3card_tb`
    displays bitmap mode at fine scrolls 1, 2 and 3 and at `HSCROLL` 1021 / `VSCROLL` 509,
    a wrap of both axes, and asserts every chip has exactly one rank on, every dot
    (§15.4, defect 19).

## 15. What would have to be built to believe it

Each step gates the next, and the first two are **done**.

| | | |
|---|---|---|
| ✅ 1 | **The parts list**, as an *alternate* in `hardware/place/parts.ts` | `npm run check:place` — §13.5. It found the ceiling of four PLCC-84s, and an arithmetic error in this document |
| ✅ 2 | **The dot path and access budget as arithmetic** | `npm run check:video3` (`hardware/video3/timing.check.ts`) — the half of §14 item 1 that does not need a board |
| ✅ 2b | **A functional model in the host emulator**, beside `video/`'s and selected by `VIDEO3=1` | `sh video3/bench/run-v3.sh` — **character mode, tile mode, the copy engine and the sprite, all pixel-exact** against `tools/v3model.py`, which renders from §2.2/§2.4/§2.5/§3/§6/§7/§8.1 and shares only *data* with the ROM. Mutation-tested. **This is where the driver gets written.** ⚠ It cannot see the cadence (§14 item 8) |
| ✅ 2c | **The control-line census** — [`signals.md`](signals.md) | what the lines are and what generates them, block by block. It is the input to the partition, and it surfaced three things: the LUT address bus now has masters on **both** halves, the attribute's clock must not be mode-dependent, and the copy engine is the only requester wanting **two** spare accesses |
| 3 | **The dot path as a schematic**, and nothing else yet | it is settled by §3 and §13, it does **not** depend on the partition, and it is what §14 item 1's *other* half needs. ⛔ Drawing the rest first would encode a partition that does not exist |
| ✅ 4a | **The partition** — [`partition.md`](partition.md) | **four `ATF1508AS` and the `v3lane` `GAL22V10`**, and §13.5 says four PLCC-84s is the most that places. ⛔ **So video3 is exactly at its ceiling**: there is no fifth PLCC-84, and no room for a feature that needs one |
| 4b | **Term lists, then a pin census from them, then a fit** | ⭐ term lists and fits for all five parts (§14 item 4); ⚠ the pin census from them is not written — `partition.md` §6 |
| ✅ 5 | **`reach` and `census` from the first term list, not retrofitted** | they are the pair that caught `ACTRL` b3 unbuilt for two days and `design-review2`'s eleven blocks described as fitted with nothing behind them. ⭐ `check:reach` covers video3 and counts `video3_card.v` as its board; `check:pins` holds every pin to the discrete part it drives |
| 6 | **A cadence check** — §14 item 8 | five requesters, one spare access a slot |
| 7 | **Verilator** — §15.1 | ⭐ **started**: `v3dot_tb` (17 claims) and `v3card_tb` (57) run in `npm run check:video`, and the card bench is §15.4. `v3machine_tb` is not built |
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
| `v3dot_tb` — **built** | `v3dot` alone | the raster in all four `VMODE`s — line length, `HSYNC` width, frame length, the active area — for **17 claims**. Its wire list is generated from the term list (`v3portmap.ts`'s `rewriteTb`), so a changed port cannot stop it compiling unnoticed |
| `v3char_tb` | the whole card | ⭐ **covered by `v3card_tb`**: character mode at 80 × 60 and 80 × 25, every pixel `{attribute, glyph pixel}`, and a copy under it. ⚠ Not 80 × 30 or 80 × 50, and not a CP437 font — the bench's glyphs are arithmetic |
| `v3copy_tb` | the whole card | §6: every width class, an overlapping scroll staged through scratch, and **that a copy under a span waits**. `v3card_tb` has two copies, one in bitmap mode and one under character mode |
| `v3sprite_tb` | the whole card | ⭐ **covered by `v3card_tb`** at three positions — (101, 37), (3, 0) and (618, 190), both families — and **off** in character mode. ⚠ Not every X phase: `run-v3sprite.sh` does that on the emulator |
| ⭐ **`v3card_tb`** — **built, §15.4** | **the five parts and the board around them**, `video3_card.v`, driven by a 6809E bus model that honours `/WAIT` | the seams between parts and packages: the register file, the palette path, both sequencers, the reload, the picture in all three modes with both scrolls and the sprite, and the bus fights and floats no single part can see |
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

### 15.4 ⭐ `v3card_tb` — the card as a card, and what it found

`hardware/gal/verilog/video3_card.v` is the five parts — `v3dot`, `v3scan`, `v3ptr`,
`v3host` and `v3lane` — wired to the discrete parts of §13.1: the two framebuffer parts
and their four lane `'245`s, the register file, the fetch ranks, the `'153`, the index
`'574`, the four sprite `'165`s, the LUT and its `'273`s, the `PIDX`/`PDAT` latches, the
posted-write and `vread` `'574`s, the `VSTAT` `'244` and the host `'245`. ⭐ **Every net
between two parts is the term lists' own**: the port maps and the wire list are generated
by `v3portmap.ts` (run by `gen.ts`) from the `.cpld.ts`/`.jedec.ts` inputs and externals,
so a buried cell cannot become a net by being mentioned, and the hand-written board
reaches into no part outside the benches' back doors. ⭐ **The buses are resolved, not
chosen**: the internal data bus, the framebuffer address, each byte lane and the LUT's
high address byte are nets with explicit drivers, and every dot counts how many drive —
two is a fight, a sample with none is a float. `check:reach` counts the file as video3's
board.

`v3card_tb` drives it one 6809E bus cycle at a time, **stretching E-high while `/WAIT` is
asserted** with `clkdec`'s semantics, and a bound turns a hang into a failure. It runs in
`npm run check:video` as `v3card` — **61 claims, 0 failed** (the suite: 373, 0 failed):

| | |
|---|---|
| the palette | four writes land at LUT entries 0..3, and `PIDX` walks |
| direct `VDATA` | eight writes land at `WPTR`, `WPTR`+1, …, nothing either side moves, and eight reads return them in order, **post-incrementing** |
| the cell write | ⭐ **`WADV` b2**: two `VDATA` writes fill a cell's lanes 0 and 2 and the pointer lands on the next cell, and with the bit clear it steps by one again |
| the span writer | a mask of `$86` is `F1 B2 B2 B2 B2 F1 F1 B2` — **bit 7 first** — four back-to-back `$FF` masks are 32 `WFG` pixels with the CPU held by `/WAIT` while each span runs; span-solid is **one `SPANLEN`, many spans**; `WADV` 01 chains four masks down four rows at the same column |
| the copy | a 13 × 5 copy lands byte for byte in every lane and row, `CBUSY` sets and clears in `VSTAT`, nothing around it moves, and it takes **130 granted accesses for 65 bytes** — two a byte, §6.1's 4.05 MB/s (the claim allows 130–150) |
| bitmap | whole 640 × 480 frames at `HSCROLL`/`VSCROLL` 0/0, 5/0, 2/3, 7/0 and 1021/509 — **fine scrolls 1, 2 and 3 and a wrap of both axes** — each 480 lines of 640 and **every pixel the byte at its scrolled address through the LUT** |
| the sprite | a 16 × 16 shape whose every row and column differ, at (101, 37) and (3, 0) in `VMODE` 11 and (618, 190) in `VMODE` 00: every pixel of the frame, sprite and background |
| character mode | `VMODE` 11 (80 × 60), then `VMODE` 00 (80 × 25) **on two consecutive frames**, with `HSCROLL`, `VSCROLL` and the sprite all set: every pixel `{attribute, glyph pixel}` of its own cell |
| a copy under character mode | 13 × 5 lands byte for byte in **exactly 130 accesses** — two a byte, beside the map's one a cell (§14 item 8) |
| tile mode | `HSCROLL` 13, 6 and 16 — **both cell phases** (`HSCROLL[2]` 1 and 0) and fine scrolls 1, 2 and 0 — with `VSCROLL` 11, 0 and 500: every pixel its scrolled cell's tile, `ATTR` zero |
| the board | `v3scan`, `v3ptr` and `v3dot` never two on the address bus; never two drivers on D7..D0; never two masters on the LUT address; **never two drivers on the internal bus, and never a sample of it undriven; no byte written from a lane nothing drives; each chip's fetch ranks exactly one on**; and `/WAIT` always released |

⛔ **It found the defects below, every one of which had fitted** — the first fourteen in
bitmap mode, the rest when character mode, tile mode, the sprite, the fine scroll and a
board with byte lanes went in. Each is fixed in the term lists with a ⛔ comment at the
fix; the list is the card's argument for §15.1's "top down". Rows 29 and 30 are the two
static checks, once the card had a board for them to read:

| | found | the design now |
|---|---|---|
| 1 | every register write started a span — `WSTB` is a level over E-high | spans start on `WSTART`, the edge at the end of a VRAM-port write; the mask loads on `WSTBV` |
| 2 | one `PDATH` write filled entries 0..3, then 0, 2, 4 | the commit runs on an edge (`PDQ`/`PDGO`), and `PS0..PS3` is a pure one-dot shift register, as `video/`'s `vsup` has it |
| 3 | every `VSTAT` poll put the `'245` and the `'244` on D7..D0 together | `RDBKOE` excludes +$0C and +$0D |
| 4 | a register read returned the odd neighbour | `CPURF`, the CPU's claim on the file, drives `RFA0` for register accesses — `REGWR` only saw writes |
| 5 | the span mask came out mirrored | `MS`*i* loads from `D`(7−*i*) — a wire, not a term |
| 6 | a `VDATA` write did not wait for a running span | `!IOPGH` is in `VRAMSEL`, as `graphics.md` §6.3.2 requires, not on `/WAIT` |
| 7 | a write held by `/WAIT` still reached the card and corrupted the span | `v3host`'s strobes are qualified by `!BUSY`, and `/WAIT` holds any card write on `CARDBUSY` — a copy and the reload walk included |
| 8 | a copy restarted for ever, and its first row was 1,023 bytes | `GO` is an edge (`GOQ`), and `CWLOAD = CROWADV # !CBUSY` loads the width while idle |
| 9 | span-solid painted `WBG` | `RFA0`'s span term is qualified by `WM0`: solid is always `WFG` |
| 10 | `VDATA` reads did not post-increment | `RSTART` reaches `WPTR`, inside `WSTEP` |
| 11 | the scan column counter stepped every dot | `FETCH` is `SLOTTICK`, and `HLOAD` moved to HC 32–33, two slots before the picture — the load wins over the count |
| 12 | `HC >= 36` missed HC 40–43, so every line blanked sixteen pixels in | `ACTIVE` is a **register** on `v3dot`, set at the tick ending slot 35 and cleared at slot 195 — which is also what made `v3dot` fit again |
| 13 | the `'273`'s `/MR` on undelayed `BLANK` lost the first two pixels | `OMR` is on `v3host` behind two registers, `BD1`/`BD2`, and the model's `/MR` is asynchronous |
| 14 | `v3dot_tb` had not compiled since `4a7d398`, which replaced its `RMAP`/`RRD` inputs — `check:video` was not run after that change | repaired |
| 15 | the map was never fetched: `MAPLD` = `SPARE & CELLTICK` and the grant `SPARE & CELLTICK & MODE`, and `CELLTICK` is dot 3 where `SPARE` is dots 0–1 — **character and tile mode showed no map at all** (the character-mode frame) | `MRQ`, a registered per-slot request inside `MWIN` (slots 30–193), parity `HC0` = `HSCROLL[2]`; `v3scan` derives `MAPLD`/`GMAP`/`MCADV`/`FETCH`/`FBOESCAN` from `MRQ`, `DP1`, `DP0` and `MRQ2` — which freed pins; the map column counter steps on each access and loads on `HLOAD`'s first dot, and `HLOAD` is HC 30–33 |
| 16 | every odd cell's map word was in the framebuffer part `v3scan` cannot read — `GAP_4` (the character-mode frame) | the four-byte cell stride, §2.2 and §2.5 |
| 17 | every cell's attribute arrived two slots early, half of it on the cell before (the character-mode frame) | three attribute stages, `MAPA` → `ATQ` → `ATO`, stepped on the first dot of each map access (§2.5) |
| 18 | the attribute leaked into tile mode — `ATOE` was on there (the tile-mode frames: "`ATTR` zero") | `ATOE` is character mode only, and pull-downs give tile mode zero |
| 19 | fine scroll: one rank-enable pair for all four chips and an un-rotated `'153` phase, so a scroll not a multiple of four showed the wrong rank on some chips and the wrong byte on all (the bitmap frames at `HSCROLL` 5, 2 and 7) | per-chip `OEA0..2`/`OEB0..2` (chip 3 strapped) and `MUXSEL` = dot + `HSCROLL[1:0]`, as `graphics.md` §8.2 — §14 item 19 |
| 20 | the sprite's position counters never counted: a helper dropped bit 0's decrement term and held zero with `q & !q` — the first sprite frame showed no sprite | up-counters loaded with `~SPRX`/`~SPRY`, all-ones on the hit, and hit registers `SHQ`/`SVQ` (§7) |
| 21 | a hit held from the line before shifted the loaded row out in horizontal blanking (the sprite frames, at `SPRX` 3) | the window and its hit only inside `ACTIVE` |
| 22 | the window counters were still the 8 × 8 sprite's, `SR3`/`SW3` (the sprite frames) | `SR` is five bits — rows 0–15, then stop — and the `'165`s' shifted-in zeros end the columns |
| 23 | line doubling's pair phase flipped every frame — both families have an odd line count and `DBLHOLD` toggled every line, so one doubled frame in two was a line out (the second consecutive 80 × 25 frame) | `DBLHOLD` held set through vertical blanking; the bench takes two consecutive doubled frames |
| 24 | no byte path between the 8-bit internal bus and the 32-bit framebuffer: no lane decode, no byte enables, no source enable — `GAP_1`, `GAP_2`, `GAP_6`, `GAP_7` (the internal-bus and lane fight/float claims, and every VRAM write) | four `74AHCT245` lane transceivers (`DIR` from `v3host`, held for the whole access), the `v3lane` GAL (`LOE0..3`, `/LB0 /UB0 /LB1 /UB1`, `PWOE`, `RFOE`), `v3ptr`'s `LANE1:0`, and `VWE` (`v3ptr`) the framebuffer's `/WE` for both writers |
| 25 | the copy's byte never reached the framebuffer: it was read into `vread`, which drives the backplane (the 13 × 5 copy) | the copy's read lands in the posted-write `'574` (`PWCK` = `WSTBV` or the copy's read tick) and its write drives it back out (`PWOE`); `vread` is the prefetch's alone |
| 26 | span-solid wrote **one** byte: a `VDATA` write invalidates the prefetch, and the prefetch took the internal bus on the very dot `WSTART` loaded `SPANLEN` from the file (span-solid, "exactly 20 `WFG` bytes") | `RDREQ` is off at `WSTART`, while `SPANBUSY`, through the reload walk, and through E-high of any card access but a `VDATA` read |
| 27 | the copy's next read overlapped the reload walk on the internal bus ("never two drivers on the internal data bus") | `RCPY` = `CBUSY` and no walk |
| 28 | the fetch ranks had no clock, and `VSTAT` b0 no producer — `GAP_3`, `GAP_5` | the ranks clock on `SPARE`'s rising edge, the end of the display access; `v3host` exports `IRQPEND`, paid for by moving `OMR`'s two-register blank delay to `v3dot` |
| 29 | **`check:reach`**, with `video3_card.v` as video3's board and `v3lane` a part: `CT6` on `v3dot` was `CTRL` b6, a register nothing read (`v3host` owns `IRQEN`); `RSPN` was `SPANBUSY` under a second name | both removed; and `v3ptr`'s three-bit mask counter `MK2..0` became one marker bit, `MS8` |
| 30 | **`check:pins`**: none of video3's pins driving an active-low discrete input was declared active-low | declared, and `check:pins` holds each to its consumer — `OEA`/`OEB`, `PIXOE`, `PIDXOE`, `SPRLD`, `SPRSH` (the `'165`s' `CLK INH`), `LDPIDXL` (`'163` `/LD`), `LDPIDXH` (`'574` clock), `VWE`, `WSTB`, `RDBKOE`, `VSTATOE`, `RDOE`, `LUTWE`, `RDCK`, `PWCK` and the GAL's ten — 249 claims |
| 31 | `v3dot_tb`'s hand-kept wire list had fallen out of step with the part again | generated between two markers by `v3portmap.ts`'s `rewriteTb` |

⚠ **What it does not reach**: a CPU — the bus is a task honouring `/WAIT`, not
`mc6809e` running a driver (§15.2's `v3machine_tb`); the cadence's *time*, as against
its access counts (§14 item 8); 80 × 30 and 80 × 50, every sprite X phase, and an
overlapping copy (§15.1's table); and the timing. It is a model of the logic, as every
wrapper in `hardware/gal/verilog/` is.
