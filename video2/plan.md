# Video 2 — A Microcoded ANSI Card

## Control Store in Flash, a Fixed RGB332 Ladder, and No Programmable Logic

**Question this answers:** [`video/docs/graphics.md`](../video/docs/graphics.md) designs a
256-colour card around three `ATF1508AS` CPLDs and a 256 × 16-bit palette LUT, and its
text mode is the span writer at 13 CPU writes per character cell. **This document
designs a different card for a narrower goal** — *render ANSI BBS screens quickly and
accurately* — out of parts that existed before 1990, with **no CPLD and no GAL**, and
with its control logic in a **flash control store** rather than in fuses.

**Short answer: the datapath transfers almost intact, the control plane is replaced by
two ROM tables, text becomes hardware at 4 CPU writes per cell, and the package count
roughly doubles — because deleting the programmable logic is exactly what the card's
own [`graphics.md`](../video/docs/graphics.md) §10.1 says costs packages.**

**Constraints taken as given (yours):**
- **Microcoded**: control store in ROM, a state machine, a register set, logic gates —
  the VLSI shape, in 74-series.
- **Flash**, not EEPROM, for the control store.
- **256 colours, fixed RGB332 palette.** No palette LUT.
- **80×25 ANSI text with a programmable character set.**
- **No tile mode, no palette LUT, no display list.**
- **Period-appropriate silicon, pre-1990** — and **no CPLDs or GALs on this card**,
  which is a stricter rule than the machine's (the root [`README.md`](../README.md)
  retired the no-CPLD rule for the machine on 2026-09-08; this card re-adopts it as a
  card rule).
- **It plugs into the existing motherboard**, unchanged.

> This is a **plan**, not the card's specification. When it becomes one it splits per
> [`CLAUDE.md`](../CLAUDE.md): a spec in the present tense plus a `history.md` beside
> it. Nothing here is built, and every number below is derived rather than measured —
> the ones that cannot be derived are marked ⚠.

---

## 0. Decisions

| | Decision | Why |
|---|---|---|
| **Control plane** | **Two flash ROM tables**: a 512-word **horizontal control store** indexed by the slot counter, and a 4,096-word **vertical table** indexed by the line counter | The slot counter *is* the microprogram counter, so there is no branch logic, no next-address field and no sequencer state at all — §4 |
| **Control store part** | **`SST39SF040`** (512K×8, 70 ns, PDIP-32, 5 V) — the part the motherboard's boot ROM already uses | One verified pinout ([`hardware/lib/parts.ts`](../hardware/lib/parts.ts) `FLASH_512K`), one programmer, one supply line for the whole machine. ⚠ 0.4 % of it is used — §4.4 |
| **Text** | **hardware character generator, 4-byte cell** `{char, fg, bg, flags}`, programmable font in VRAM | 4 CPU writes per cell against `graphics.md` §7.3's 13, **per-cell 8-bit fg and bg with no lookup anywhere**, and the cell's own fetch latches are the colour path — §6 |
| **Colour** | **fixed RGB332, 3/3/2 R-2R ladders**, `graphics.md` §9.1's drive stage unchanged | This is `graphics.md` §19 item 3's own documented retreat, taken deliberately. It deletes the LUT, its write path, and **the tightest timing path on the card** — §10 |
| **VRAM addressing** | ⭐ **flat-mapped. There is no `WPTR`** | The CPU's physical `A0`–`A18` are on the backplane and the card has room to buffer them. It deletes the pointer, the posted-write latch, `VDATA`, the read prefetch and three of `graphics.md`'s 2026-09-10 defects — §9.1 |
| **Stalls** | ⭐ **the card never asserts `/WAIT`** | With one spare access per fetch slot and no span writer competing for it, the CPU's access is always available in the slot its cycle lands in — §8.2 |
| **Span writer** | **not built in v2.0** | Its main job was text, and text is hardware now. Recorded with its price (~6 packages) as §15 item 3 |
| **Modes** | all four `VMODE` codes, and **text at 80×25 / 30 / 50 / 60** | Vertical timing is a ROM table, so a mode costs bytes rather than product terms — and the 32-row ceiling `graphics.md` §6.4.1 hit is gone |
| **IC count** | ⛔ **62 packages as budgeted, and they do not place** — against `graphics.md` §14.1's 33 | Measured with `hardware/place/pack.ts`, not estimated: 7 packages over on the longest board the machine has. **Two levers close it**; §11.2 has the numbers and §15 item 0 is the decision they force |

---

## 1. Why this card exists beside the other one

| | [`video/`](../video/) | **`video2/`** |
|---|---|---|
| Goal | a general 256-colour graphics card | **ANSI BBS screens, fast and accurate** |
| Programmable logic | 3 × `ATF1508AS` PLCC-84 | **none** |
| Control logic lives in | fuses, fitted by `fit1508.exe` | **flash, assembled by a program in this repository** |
| Colour | 256 of 65,536, RGB565 LUT | **256 fixed, RGB332** |
| Text | span writer, **13 writes/cell** | **hardware cells, 4 writes/cell** |
| Character set | none (dropped — `graphics.md` §6.4.3) | **programmable, 4 banks of 256 glyphs** |
| Tile mode / display list | both built | **neither** |
| CPU VRAM access | a pointer port at `WPTR` | **flat memory** |
| ICs | **33**, and they place | ⛔ **62 as budgeted, and they do not** — §11.2 |

**Neither supersedes the other.** They answer different questions, and the honest
summary of the trade is one line: *`video2` spends about thirty packages to remove three
CPLDs, and buys hardware text and a simpler machine interface with the change.*

---

## 2. What transfers, and what is deleted

> **Every `§` in the first two columns is `graphics.md`'s; the last column is this
> document's.** The two numbering schemes collide in several places — `§9`, `§11`,
> `§12` and `§6.4` exist in both and mean different things — so nothing outside this
> table cites a foreign section without naming its document.

| From `graphics.md` | Verdict for `video2` | § |
|---|---|---|
| **Chunky 8bpp, 4-way interleave, two ×16 SRAMs** | **Keep verbatim.** §14.2's `AS6C8016` pair, the same 158.9 ns fetch slot, the same 72 ns access budget | §8 |
| **The 158.9 ns slot grid and static arbitration** | **Keep, and it gets simpler** — one spare access per slot with only one claimant | §8.2 |
| **Spare access first, display fetch second** (§5.2.2) | **Keep. It is load-bearing**, and it is what makes the CPU read close | §8.3 |
| **640×200 geometry, 800 × 449 / 800 × 525, sync polarity per mode** (§6.2, §6.2.1) | **Keep verbatim** — and the polarity becomes a bit in a table instead of an XOR term | §5 |
| **Two ranks of fetch latches** (§8.2) | **Keep** — the text pipeline needs two ranks for its own reason, and byte-granular scroll then comes free | §6.3, §7 |
| **`74AHCT` on everything that reads an SRAM** (§14.2.6) | **Keep, and it is not a style choice** — the `AS6C8016` drives 2.4 V and `74AHC` wants 3.85 V | §11 |
| **The VGA drive stage** (§9.1, §9.2) | **Keep verbatim** — ladder, `V_be` return, emitter followers, 75 Ω source, blank-to-black through `'273` `/MR` | §10 |
| **`/IOPAGE`-qualified VRAM select, `A0`–`A6` register decode** (§6.3.2, `machine.md` §2) | **Keep. Mandatory** | §9 |
| **VBL interrupt on `/IRQ`, HSYNC/VSYNC to the CPU slot** (§12) | **Keep** — the CPU's raster compare depends on both pins | §9.4 |
| **256 × 16 palette LUT and its write path** (§9) | **Delete** — −5 packages, and the dot path loses its tightest stage | §10 |
| **Tile mode** (§6.4) | **Delete** — the character generator is what it was being used for (§6.4.8) | §6 |
| **Display list** (§10.3) | **Delete** | — |
| **`WPTR`, the posted-write path, `VDATA`, the read prefetch** (§3.1.1, §7.4, §11) | **Delete** — VRAM is flat | §9.1 |
| **Span writer, `SPANLEN`, `WADV`, `SPANBUSY`, `/WAIT`** (§7.4) | **Delete in v2.0**, priced in §15 | §15 |
| **The three CPLDs** | **Delete** — replaced by §4's two ROM tables and ~30 packages of registers and counters | §11 |

---

## 3. The machine contract — unchanged, and that is the point

**No motherboard change, no backplane change, no new signal.** The card drops into a
slot the machine already has, and every rule it must keep is one
[`docs/machine.md`](../docs/machine.md) already states:

| | |
|---|---|
| **Window** | `$FF60`–`$FF7F`, 32 bytes — `machine.md` §3, `hardware/cards/windows.ts`. **Taken by video, and `video2` is video** |
| **Decode** | `/IOSEL · A6 · A5` plus `A4`–`A0`. ⚠ **Seven bits, not six** — `machine.md` §5 item 1 A: with `A6` out of the strobe a six-bit card answers 64 bytes below its base as well |
| **VRAM select** | `A19 · /A20 · /IOPAGE(high)` — physical 0.5–1.0 MB, `machine.md` §2 |
| **Flat addressing** | physical `A0`–`A18` off the backplane, which the slot carries (`hardware/README.md`, positions A8–A31) |
| **Clock** | 25.175 MHz from slot B22. ⚠ **The oscillator stays on the motherboard** — a card that supplies E kills the CPU when it is pulled (`graphics.md` §5.1) |
| **E rate** | ÷12, 2.0979 MHz, 476.7 ns. ⚠ **This card is specified at ÷12 only** — §8.3's read budget does not close at ÷8, exactly as `graphics.md` §11's flat read did not |
| **Interrupts** | VBL on `/IRQ`, open-drain, shared — `machine.md` §4 |
| **`HSYNC`/`VSYNC`** | TTL, out to slot B24/B26, for the CPU module's raster compare — `graphics.md` §12.2. **Not optional**: without VSYNC the CPU's line counter has no origin |
| **`/WAIT`** | ⭐ **not driven.** The card has no reason to stall the machine — §8.2 |

---

## 4. The control plane: two ROM tables and no sequencer

This is the part that differs in kind from `video/`, and the whole argument for it is
one observation:

> ⭐ **The horizontal raster is already a program counter.** A line is 200 fetch slots
> and the slot counter visits them in order, every line, for ever. A control store
> indexed by that counter needs **no branch logic, no condition codes, no next-address
> field and no state register of its own** — the microprogram is 200 words long and it
> runs straight through.

### 4.1 The two tables

| | Indexed by | Width | Depth | Holds |
|---|---|---|---|---|
| **Horizontal control store** | `{TEXT, H[7:0]}` | **16 bits** — 2 × `SST39SF040` | 512 words | everything that happens within a line: sync, blanking, the fetch cadence, which source drives the VRAM address bus, which latch clocks, and when the CPU's access window opens |
| **Vertical table** | `{VMODE[1:0], V[9:0]}` | 8 bits — 1 × `SST39SF040` | 4,096 words | `VSYNC` **already at the mode's polarity**, `VBLANK`, `ROWADV`, `VLOAD`, and the VBL interrupt line |

**Horizontal timing does not depend on `VMODE`.** All four modes are 800 dots at
25.175 MHz with the same sync (`graphics.md` §6.2.1: the families differ in **V**
polarity and line count only), so the mode bits do not reach the horizontal store at
all. What does reach it is `TEXT`, because the two modes have different fetch cadences.

**The microcycle is one fetch slot — 158.9 ns.** A `SST39SF040` at 70 ns plus a
`74AHCT574` pipeline register's 5 ns setup is 75 ns inside 158.9, so the store is read
one slot ahead and the register presents its word for the whole of the next. That is an
ordinary pipelined control store and it has **83.9 ns of margin**, which is the most
comfortable timing number on this card.

### 4.2 The microword

Sixteen bits, three encoded fields and nine direct bits. The encoded fields go through
a `74HCT138` each, because their members are mutually exclusive by construction — which
is the same argument `audio.md` §10.2.6 used to fold four clocks and three selects into
one 3-bit code.

| Bits | Field | |
|---|---|---|
| `b2..b0` | **`ASRC`** | which source drives the VRAM address bus: idle / scan / cell / font / CPU. Decoded to five `/OE`s |
| `b4..b3` | **`MEM`** | idle / display read (4 bytes) / CPU read / CPU write |
| `b7..b5` | **`LATCH`** | which register clocks: fetch rank A, the char latch, the rank A→B transfer with the font shifter's load, the CPU read latch |
| `b8` | `HSYNC` | raw; polarity is fixed negative in both families (`graphics.md` §6.2.1, `HPOL` is a constant) |
| `b9` | `HBLANK` | |
| `b10` | `FETCH` | the display column counter's count enable |
| `b11` | `HLOAD` | loads the column counter from `HSCROLL` |
| `b12` | `CELLADV` | the cell boundary — one slot in two in text mode |
| `b13` | `MUXSRC` | pixel mux select source: dot phase (bitmap) or font bit (text) |
| `b14` | `CPUWIN` | the spare half-slot is offered to the CPU |
| `b15` | — | reserved |

⚠ **Every counter *enable* must carry the slot tick and a *load* must not.**
`graphics.md` §8.1 records this as a defect class of its own: both parts are clocked on
`DOTCLK`, so a window level asserted for a whole slot advances a counter four times.
`FETCH` without the gate walks 2,560 pixels across a 640-pixel line. The microword
carries the window; the dot-phase counter supplies the tick.

### 4.3 What is *not* in the control store

**Arbitration.** There is none to do — §8.2. The CPU's access is the front half of every
slot and nothing else wants it.

**The dot.** Within a slot, four dots have to be sequenced (the pixel mux select, the
output register's clock). That is a 2-bit dot-phase counter and a decoder running at
25.175 MHz, below the microcycle, exactly as `graphics.md` §5.2.2 describes. **A
control store at dot rate is not buildable from 70 ns flash** and is not attempted.

### 4.4 The parts, and what they cost

⚠ **A `SST39SF040` is 512 K words and the horizontal store uses 512 of them.** That is
0.1 %, and the vertical table uses 0.1 % of a second. The waste is real and it is the
cheapest thing on the card — ~$2.50 each, against a `SST39SF010A` (128K×8) at a similar
price in the same package and the same pinout, differing only in that **pin 1 is `NC`
rather than `A18`** (`hardware/lib/parts.ts` `FLASH_512K` records that trap). Either
works; the 040 is specified because **it is the part the machine already stocks,
programs and has a datasheet-verified pinout for**, and a second part number buys
nothing.

⭐ **Three flash devices and one programmer for the whole machine** — the boot ROM is
two of the same part (`machine.md` §7.2).

---

## 5. Geometry — `graphics.md` §6.2, unchanged

| `VMODE` | Bitmap | Timing | Refresh | **Text** | Cell rows |
|---|---|---|---|---|---|
| `00` | **640×200** (line-doubled) | 800 × 449 | 70.09 Hz | **80×25** | 25 |
| `01` | 640×240 (line-doubled) | 800 × 525 | 59.94 Hz | 80×30 | 30 |
| `10` | 640×400 | 800 × 449 | 70.09 Hz | 80×50 | 50 |
| `11` | 640×480 | 800 × 525 | 59.94 Hz | 80×60 | 60 |

**59.94 Hz, not 60.0** — `hardware/gal/sync.timing.ts`'s arithmetic, and it matters for
exactly one thing: a NitrOS-9 tick divisor calibrated for one family runs 0.1 % wrong in
the other, about 86 seconds a day (`graphics.md` §6.2).

⭐ **Two things the ROM table gives back that the fitted design could not afford:**

- **Sync polarity is a bit, not an XOR.** `graphics.md` §6.2.1 spends 10 product terms
  on `VSYNC = raw XOR VPOL` and an argument about where the counters are zeroed. Here
  the table is indexed by `VMODE` already, so **the stored bit is the pin level**.
- **Line doubling is a bit, not a parity test.** `graphics.md` §8.1's *"advance when
  `V` is even"*
  covers both families by an accident of where active video starts; the table states
  `ROWADV` per line per mode and no accident is required.

⚠ **The table is generated, not typed.** It comes out of the same arithmetic
`hardware/gal/sync.timing.ts` already carries and `npm run check` already asserts —
§13.

---

## 6. Text mode — the four-byte cell

**This is the card's reason to exist.** A character cell is **four bytes**, and the four
bytes are one memory access.

| Byte | | |
|---|---|---|
| `+0` | **`char`** | glyph code, 0–255 |
| `+1` | **`fg`** | **foreground colour, RGB332 — any of 256** |
| `+2` | **`bg`** | **background colour, RGB332 — any of 256** |
| `+3` | **`flags`** | `b1..b0` font bank, `b2` blink, `b7..b3` reserved |

### 6.1 Why four, and why in that order

**Four is a power of two, so the cell address is a concatenation and there is no
adder** — the property `graphics.md` §6.4.1 protects everywhere and checks over all
524,288 field combinations. A cell at index *n* occupies bytes `4n`…`4n+3`, which
`graphics.md` §7.4 already establishes are *"the same intra-chip address on four
different chips"*. **One access fetches the whole cell.**

⭐ **And the order is the mechanism.** The four bytes land in the four fetch latches the
card has anyway, and the pixel mux selects among those latches. So `fg` sits at mux
input 1 and `bg` at input 2, and **choosing the colour per pixel is the mux select and
costs no package**:

```
  S1 = /bit      bit = 1  ->  input 1 = fg
  S0 =  bit      bit = 0  ->  input 2 = bg
```

One inverter. That is `graphics.md` §7.4's *"the mask bit is an address line"* trick one
level up — the font bit never enters a colour path, because **the colours are already
where the mux is looking.**

**Blink is one gate on that select**: `bit AND NOT(flags.blink AND blinkphase)`, with
`blinkphase` a bit of the line counter. Classic ANSI blink, and it is what a BBS art
screen actually uses.

### 6.2 Where things live in VRAM

Concatenation throughout; every field is a slice of a counter or a register.

```
cell fetch      A18..A15  CELLBASE[3:0]     register - 16 pages of 32 KB
                A14..A9   cellRow[5:0]      display row counter - a 64-row ring
                A8 ..A2   cellCol[6:0]      display column counter - 128 cells
                A1 ..A0   --                the four bytes, one access

font fetch      A18..A15  FONTBASE[3:0]     register
                A14..A13  bank[1:0]         flags[1:0] of the cell being fetched
                A12..A5   char[7:0]         the char byte just fetched
                A4 ..A2   row[2:0]          scanline within the cell
                A1 ..A0   00                see below
```

| | |
|---|---|
| Screen, 80×25 | **8,000 bytes displayed**, 12,800 with the 512-byte row stride |
| The ring | **64 cell rows** — 32 KB, and 80×60 fits inside it with four rows to spare |
| A font bank | 256 glyphs × 32 bytes = **8 KB**; four banks = 32 KB |
| Of 512 KB | **~10 % used at 80×25.** The rest is the bitmap's |

⭐ **The 64-row ring is what `graphics.md` §6.4.1 could not have.** Its cell row was five
bits because the fitter had no more, so cell mode reached 80×25 and 80×30 and stopped.
A sixth bit here costs one address line and one byte of `CELLBASE`'s range.

⚠ **A glyph is 32 bytes and only 8 are used**, and that is deliberate. Putting the rows
4 bytes apart forces `A1:A0 = 00` on every font fetch, so **the font byte always arrives
on the same interleave chip** and the shift register can take its parallel input from
that chip's fetch latch with no mux of its own. The alternative — rows one byte apart —
puts the byte on a different chip every scanline and needs a 4:1 selector in front of
the shifter, which is four packages. **Six kilobytes per bank of a 512 KB framebuffer,
against four packages**; it is the same trade `graphics.md` §6.4.1 makes when it spends
1,200 bytes on a 128-byte map stride to avoid a multiply.

### 6.3 The fetch cadence — two slots, one cell of lead

A cell is 8 dots = **two fetch slots**, and it needs two accesses:

```
  slot     2k                 2k+1               2k+2               2k+3
  spare    CPU                CPU                CPU                CPU
  fetch    cell N+1 (4 B)     font N+1 (1 B)     cell N+2           font N+2
           \________ displaying cell N ________/ \____ cell N+1 ____/
```

**The cell fetch leads the display by one whole cell, and that lead is a timing
requirement rather than a convenience.** `graphics.md` §6.4.9 derives the number for the
identical dependency in tile mode: fetching the code and then using it as an address in
the *same* slot is `mux 15 ns + SRAM 55 ns + setup 5 ns = 75 ns inside a 79.4 ns
half-slot`, twice over, and the card's tightest documented path has 11.7 ns. One cell of
lead gives the char byte a full slot to become an address.

⚠ **And it needs two ranks of latches, not one.** `graphics.md` §6.4.9 records exactly
this being got wrong: with one register *"158 of 160 tile fetches on a line carried the
next cell's code and the picture was displayed one cell to the left."* Rank A takes the
fetch; rank B takes rank A at the cell boundary and is what the mux reads.

⭐ **The two ranks are not a cost, because the card wants them anyway.**
`graphics.md` §8.2 needs the same two ranks in series for byte-granular horizontal
scroll in bitmap mode, and proves one rank cannot do it at any clock instant. The eight
`'574` serve both modes.

### 6.4 What text costs the CPU

⚠ **Every microsecond below scales on one unverified number** — `graphics.md` §7.3
assumes a tight 6309 store loop sustains one write per 5 core cycles in native mode,
2.38 µs at E = 2.0979 MHz, and its §19 item 1 says the repository cannot settle it. If
it is 4 cycles these improve 25 %; if 7, they fall 29 %.

| | **`video2`, hardware text** | `video/` span writer (§7.3) | `video/` cell mode (§6.4.8) |
|---|---|---|---|
| Writes per cell | **4** | 13 | 1 |
| One cell | **~9.5 µs** | ~31 µs | ~2.4 µs |
| **Scroll one line** | **1 register write + 320 stores = ~0.77 ms** | ~2.5 ms | ~0.19 ms |
| Full 80×25 redraw | **~19.0 ms — 52 Hz** | ~62 ms — 16 Hz | ~4.8 ms |
| At 9600 baud (~12 lines/s) | **0.9 % CPU** | 3 % | 0.23 % |
| At 115.2 kbaud (~144 lines/s) | **11 % CPU** | 36 % | 2.7 % |
| Clear the screen (`TFM`) | **~11.4 ms** | ~1.2 ms CPU, 5.1 ms retire | — |
| Colour | **per cell, 256 fg × 256 bg** | per cell, 256 | **one pair per 256-glyph bank** |
| Glyphs | **1,024** (4 banks) | any | 256 |
| Rows | **up to 60** | any | **32** |

**The row that decides a terminal is the scroll**, and it is a register write: the
display row counter is loaded from `VSCROLL` (§7), the ring is 64 rows, and scrolling by
one text line means `VSCROLL += 1` plus the 320 bytes of the new row — not a memmove.

⭐ **And the wire is still the bottleneck, by two orders of magnitude.** A full 80×25
ANSI art screen is 2–4 KB of escape codes: **2–4 seconds at 9600 baud against 19 ms to
draw it.** `graphics.md` §2.3 makes this argument at 62 ms and it is the argument that
dropped the character generator from that card; at 19 ms it is stronger, and the reason
to build the generator anyway is the other column — **4 writes per cell in full colour,
with no 13-write fallback and no one-colour-pair bank**.

### 6.5 The cursor is software, and that is priced

A hardware cursor is two `74HCT688` comparators against `{cellRow, cellCol}`, a blink
tap off the line counter and a gate — **3 packages**. It is not built: a terminal moves
its cursor at keystroke rate, and writing the reverse-video attribute into one cell is
4 stores ≈ 9.5 µs. **Recorded so the choice is deliberate**, per `graphics.md` §10.3.4's
convention, and it is §15 item 5.

---

## 7. Bitmap mode and scrolling — `graphics.md` §8, unchanged

8bpp chunky, one byte per pixel, 640 wide, 1024-byte row stride, a **1024 × 512 torus**
with a 640 × 200 window on it. `VSCROLL` (9 bits) picks the top row, `HSCROLL` (10 bits)
the left column, and the address generators wrap by construction.

**The same two counters serve both modes**, which is most of why text costs so little
here:

| | Bitmap | Text |
|---|---|---|
| Column counter | `A9..A2` — the 4-byte fetch group | `A8..A2` — the cell |
| Row counter | `A18..A10` — the pixel row | `A14..A9` cell row, `A4..A2` row within the cell |
| Loaded from | `HSCROLL` / `VSCROLL` | the same two registers |

⭐ **Byte-granular horizontal scroll comes free**, because §6.3 already bought the two
ranks it needs. The rank select is an **output enable and not a mux** — `c < HSCROLL[1:0]`
is constant for a whole line — which is the finding `graphics.md` §8.2 paid four
packages and one deleted design to reach.

---

## 8. Memory, the slot grid, and why nothing ever waits

### 8.1 The parts and the budget

**Two `AS6C8016-55` (512K×16), exactly as `graphics.md` §14.2.** Four bytes per access,
seventeen address bits generated, `A1` selecting the part and `A0` driving `/LB` / `/UB`.

| | |
|---|---|
| Dot | **39.72 ns** |
| Fetch slot | 4 dots = **158.9 ns** |
| Cell | 8 dots = **317.8 ns**, 3.1469 MHz |
| Per-chip access (mux 12 + SRAM 55 + setup 5) | **72 ns** |
| Accesses per slot | **two** — 2 × 72 = 144 ns ≤ 158.9 |
| Bus cycle | 476.7 ns = **3 slots** |

⚠ **The 86.9 ns of slack has no escape hatch behind it.** The `AS6C8016` is a 55 ns part
and Alliance list no faster grade (`graphics.md` §2.1); the retreat is four
`AS6C1008-45` ×8 parts, which is +2 packages and **the period-honest build** —
`graphics.md` §15 marks the 8 Mbit ×16 part as mid-90s silicon and the four ×8 as the
1989 one.

### 8.2 Nothing competes for the spare access

| Mode | Display accesses per cell | Of the four available |
|---|---|---|
| Bitmap | 2 (4 bytes each) | **2 spare** |
| Text | 2 (cell 4 B, font 1 B) | **2 spare** |

**One spare access per slot, 6.29 M/s, against a CPU that can issue ~420,000 writes/s**
(`graphics.md` §2.1) — and in `video2` **the CPU is the only claimant**. There is no span
writer, no display list and no map fetch to outrank it.

⭐ **So arbitration is a wire.** The CPU takes the front half of every slot
unconditionally, which is `graphics.md` §5.2.2's spare-first ordering with the
contention removed. **The card never asserts `/WAIT`**, never stalls the machine, and
carries none of the hazards that `machine.md` §5 item 10 has to bound at 40.7 µs — nor
the three 2026-09-10 defects that came out of stalling (`graphics.md` §19 items 36–38),
all of which are `/WAIT` and span-writer defects.

### 8.3 ⚠ The CPU read is the tightest number on the card

A flat-mapped read has an in-cycle deadline, and `graphics.md` §11 is explicit that this
is what made it refuse flat addressing. Here is the arithmetic:

| | ns from E-fall |
|---|---|
| CPU address valid (`t_AD`, self-specified — `graphics.md` §5.3) | 160 |
| Next slot boundary, worst case | 317.8 |
| Spare access, front half (72 ns) | 389.8 |
| Read latch + `'245` onto `D0`–`D7` | ~410 |
| **Data required** (`t_DSR` before E-fall) | **~437** |
| **Margin** | ⚠ **~27 ns** |

⚠ **It closes at ÷12 and it does not close at ÷8.** That is the same conclusion
`graphics.md` §11 reached about the flat read, and it is why that card prefetches
instead. The machine is specified at ÷12 (`machine.md` §1.1), so this bounds the
*experiment* and not the machine — but it is **the first thing to bench** (§14 step 1),
and if it does not hold the answer is a `/WAIT` on reads only, which costs one
package of logic and the property in §8.2.

⚠ **And `graphics.md` §19 item 6 applies with more force here**: a `/WAIT` stretch
elsewhere in the machine slides E against this card's slot grid by *N* mod 4 dots. Whole
E periods are 12 dots and 12 mod 4 = 0, so the machine's own rule protects it — but
**this card's read budget is computed from a fixed alignment and has 27 ns**, where
`graphics.md` §11's prefetch had no in-cycle deadline at all. It is the reason §14 step 1
measures the CPU access's position in the slot directly rather than inferring it from a
working read.

---

## 9. The host interface

### 9.1 ⭐ VRAM is flat memory

**A CPU access to physical 0.5–1.0 MB reads or writes the byte at that address.** No
pointer, no port, no auto-increment, no posted-write latch, no prefetch.

What this deletes from `graphics.md`, feature by feature, is most of that document's
2026-09-10 and 2026-09-11 defect list: `WPTR`'s nineteen registers (§19 item 44), the
three address `'574`s no design clocked, the posted-write strobe that re-armed a span
for ever (§19 item 37), the read prefetch's five cells and its `RDVALID` invalidation
rules (§11), `+$15 VDATA` and its five-term `WSTB` exclusion (§19 item 47), and the
`WPTR` reload rule software had to keep (§10.3.1).

**What it costs** is three `'244` to put the backplane address onto the card's VRAM
address bus, and §8.3's 27 ns.

⭐ **And what it buys software is larger than the packages.** `TFM` works on VRAM —
`TFM R,R+` is a memory fill at 3 bus cycles per byte, `TFM R+,R+` a copy — so a card
with no span writer still has a 700 KB/s fill and a block move, in the instruction set,
with no setup writes (`graphics.md` §10.2). A character cell is `STD`/`STD` at its own
address rather than three pointer stores and a mode.

### 9.2 Register map

32 bytes at `$FF60`–`$FF7F`. **Offsets are kept identical to `graphics.md` §13 wherever
the register survives**, per that section's own convention, so software, converters and
any emulator model are shared where they can be.

| Off | Name | Bits | Function | vs `graphics.md` §13 |
|---|---|---|---|---|
| `+$00` | `CTRL` | `b1..0` `VMODE` | 00 640×200/70, 01 640×240/60, 10 640×400/70, 11 640×480/60 | **same** |
| | | `b2` `TEXT` | 1 = character cells, 0 = bitmap | was `CHAR` (never built) |
| | | `b3` `BLINKEN` | 1 = `flags.b2` blinks, 0 = `flags.b2` ignored | **new** |
| | | `b6` | VBL IRQ enable | same |
| | | `b7` | display enable | same |
| `+$01` | `VSCROLL` | `b7..0` | top row: **pixel row** in bitmap, **cell row** in text | same |
| `+$02` | `VSCROLLH` | `b0` | bit 8 — bitmap only | same |
| `+$03` | `HSCROLL` | `b7..0` | leftmost column, bits 7..0 | same |
| `+$04` | `HSCROLLH` | `b1..0` | bits 9..8 | same |
| `+$05` | `CELLBASE` | `b3..0` | the cell page — 32 KB granularity | **new** (was `SPANLEN`) |
| `+$06` | `FONTBASE` | `b3..0` | the font region — 32 KB granularity | **new** (was `WFG`) |
| `+$13` | `VSTAT` | `b6` `VBLANK`, `b5` `HBLANK`, `b0` IRQ pending | **read**; write clears the IRQ. ⚠ Not a register-file location — §9.3 | same offset, `b7` `SPANBUSY` gone |
| all others | — | | **reserved.** `WPTR`, `SPANLEN`, `WFG`/`WBG`, `WADV`, `BCTRL`, `PIDX`/`PDATL`/`PDATH` and `VDATA` do not exist on this card | |

**Reset forces `CTRL = 0`** — display disabled, bitmap, no IRQ — so the machine comes up
quiet and software enables the display after loading a font. The `'273` holding `CTRL`
is what makes that true in hardware (`/MR` from backplane `/RESET`).

### 9.3 ⚠ `VSTAT` needs its own driver, and this is a known trap

`VBLANK` and `HBLANK` are the instantaneous state of the vertical table's output
register; there is nothing for a read-back buffer to read. `graphics.md` §12.1 costed
this at **+1 `74HC244` with `/OE` = "`VSTAT` is being read"**, and §19 item 43 records
what happened on the card where a status bit was put somewhere without one: the driver
polling it read back *"whatever the CPU last wrote — zero"*. The `'244` is in §11's
budget.

⚠ **And the read-back `'245` must stand off at `+$13`**, or two parts drive `D0`–`D7`.
`graphics.md` §19 item 47 records the same requirement as *modelled, not drawn*; here it
is one term of the register decode and it is drawn from the start.

### 9.4 Interrupts

**VBL only, on `/IRQ`, open-drain.** One bit of the vertical table sets a pending flag;
`CTRL` b6 enables it; the flag drives a `7407` open-collector buffer onto the shared
line. ⚠ **It must be set by an edge and cleared by a write to `VSTAT`**, or it re-arms
under its own handler — `graphics.md` §12.1 counts this as three macrocells for exactly
that reason, and in 74-series it is a `'74` and a gate.

**Raster compare stays in the CPU module** (`graphics.md` §12.2) — HSYNC clocks its
timer and VSYNC resets it, both out through the fan-out `'244`, and it is better than a
comparator on this card would be.

---

## 10. Colour: fixed RGB332, and what it gives up

**The pixel byte drives 3/3/2 R-2R ladders directly.** No LUT, no index latch, no
palette write path, no `PIDX`/`PDATL`/`PDATH`, and no `graphics.md` §13.1 snow rule —
there is no shared address bus to turn around.

**`graphics.md` §9.1's drive stage is kept verbatim and is not optional**: 1 kΩ/2 kΩ
ladders, a shared `V_be` return diode, three NPN emitter followers, a 75 Ω series
source. The arithmetic that makes it mandatory is that a ladder built to *be* the 75 Ω
source pulls 33.3 mA from a pin rated 8 mA, and the sag is code-dependent. ⚠ **A bare
ladder facing the connector is not buildable**, on this card exactly as on the other.

**Blanking still acts after the last register**, through the `74AHCT273`'s asynchronous
`/MR` (`graphics.md` §9.2): three-stating the register floats the ladder, and forcing a
palette index is meaningless when the index *is* the colour.

⚠ **`BLANK` must be delayed to match the pixel pipeline, and getting this wrong is
`graphics.md` §19 item 35** — a picture five dots right of the active window, with the
last five columns never displayed, which twelve testbenches could not see because they
compared the card's timing against its own counter. `video2`'s dot path is **shorter**:
mux → output register, two dots rather than five. The delay is a `'174` tap and it is in
§11's budget from the start, and §13 says what must assert on it.

### 10.1 What the fixed palette costs, stated plainly

`graphics.md` §9 argues against exactly this decision, and its numbers are right:

| | RGB332 direct | RGB565 LUT entry |
|---|---|---|
| Blue levels | **4, spaced 85** | 32, spaced 8.2 |
| Exactly neutral greys | **2 — black and white** | all 24 |
| Worst cube error | **40/255 (15.7 %), blue** | 3.7/255 |

**The grey ramp is the real loss**, and it is why that card keeps the LUT: with a 4-level
blue grid and an 8-level red/green grid the two coincide only at 0 and 255, so no
interior grey is actually grey. Photographs, dithered greyscale and anti-aliased text all
show it.

⭐ **And it is the right trade for this card's goal.** The 16 ANSI colours land within
half a step of the grid — ≤ 18/255 on red and green, ≤ 42/255 on blue — so a CP437 art
screen is rendered with a colour error under 7 % on the two channels the eye weights
most, and every cell can choose freely from all 256. **What suffers is gradients and
photographs, which is not what this card is for.** The decision is `graphics.md` §19
item 3's own recorded fallback — *"fall back to fixed RGB332 ladders; §9 makes that
software-invisible"* — taken as the design rather than as a retreat.

⭐ **What it buys is the card's tightest path.** `graphics.md` §6.1 gives
`index '574 → 15 ns LUT → output '574` **11.7 ns of margin in a 39.72 ns dot**, and
`features.md` §8 and §9 both cite that margin as the reason a hardware sprite, a cursor
and a border are impossible. Here the path is `'153 mux (~9 ns) → '273 setup (~5 ns)` = **14 ns, with
~25 ns of margin**, and the 15 ns LUT SRAM — a legacy part at ~$8 — leaves the BOM.

---

## 11. ⚠ Chip budget — the honest number, and it is the risk

**62 packages as budgeted.** Against `graphics.md` §14.1's 33 — and ⛔ **62 does not fit
a board, which §11.2 measures rather than guesses.**

| Group | Parts | Qty |
|---|---|---|
| **Memory and ROM** | 2 × `AS6C8016-55` (512K×16), 3 × `SST39SF040` (2 control store, 1 vertical table) | **5** |
| **Control plane** | 3 × `'574` pipeline, 2 × `'138` field decode, 1 × `'163` dot phase, 1 × `'174` blank delay | **7** |
| **Raster counters** | 2 × `'163` slot counter (8 b), 3 × `'163` line counter (10 b) | **5** |
| **Display address** | 2 × `'163` column, 3 × `'163` row, 3 × `'244` scan `/OE`, 3 × `'157` mode concatenation, 2 × `'574` `CELLBASE`/`FONTBASE`, 2 × `'244` font address group | **15** |
| **Pixel path** | 8 × `'574` fetch, two ranks; 4 × `'153` mux; 1 × `'165` font shifter; 1 × `'273` output; 2 × gates (blink, select) | **16** |
| **Host** | 3 × `'244` address, 1 × `'245` data, 1 × `'244` `VSTAT`, 1 × `'244` sync fan-out, 1 × `'138` + 1 gate decode, 1 × `'273` `CTRL`, 3 × `'574` registers, 1 × `7407` `/IRQ` | **13** |
| **Glue** | 1 × `'04` | **1** |
| | | **62** |
| — | 3 × NPN + 1 diode + resistors, 3 × R-2R SIP | VGA drive stage, **not ICs** |

⛔ **`74AHCT`, not `74AHC`, on every part that reads an SRAM output.**
`graphics.md` §14.2.6: the `AS6C8016` drives `V_OH` = 2.4 V, a `74AHC` input wants
3.85 V at `V_CC` = 5.5 V, and a `74HC` one 0.7 × `V_CC`. **Only the TTL-threshold family
can read these parts at all**, and a one-letter substitution silently breaks the dot
path. The fetch latches, the `'153`, and the output `'273` are `74AHCT`; the bus-rate
parts may be `74HCT`.

⛔ **And `HCT` and not `HC` on everything that reads the CPU**, per
`hardware/lib/parts.ts`: the module fronts the bus with 3.3 V buffers, and a `74HC`
input at 5 V needs 3.5 V to see a one.

### 11.1 Where the thirty packages went, and why nobody should be surprised

`graphics.md` §10.1.1 answers this in advance, from a census of the card's own fitted
designs:

> *"the card is programmable-logic-heavy for exactly one reason — **~54 of its
> macrocells are counter bits**, and a GAL22V10 has no buried nodes."*

`video2` deletes the tile mode, the display list, the palette write path, the span
writer and `WPTR` — and it still needs **14 packages of 4-bit counters** where the fitted
card needed none, because a `'163` holds four bits and an `ATF1508AS` holds 128. The
cross-check is that document's own archived GAL build: **41 ICs including ten
`GAL22V10`** (90 macrocells). Replacing 90 macrocells of programmable logic with
74-series, and adding a character generator and three ROMs while removing four features,
lands at about sixty. **The estimate agrees with the history, which is the only
corroboration available before the BOM is counted.**

### 11.2 ⛔ It does not place, and that is measured

**`hardware/place/pack.ts` is the repository's own skyline packer**, and the BOM above
was run through it against all three board lengths rather than estimated. `video/`'s
current card is in the same table as the control:

| | ICs | courtyard | of placeable | 240 mm |
|---|---|---|---|---|
| `video/`, today | 33 | **124.4 cm²** | 210.3 | ✅ **59 %**, skyline 76.0 mm |
| ⛔ **`video2`, as budgeted** | **62** | **175.1 cm²** | 210.3 | ⛔ **7 packages over**, skyline 91.9 of 97 mm |

⛔ **Nothing in this design places on 180 mm** — the baseline is 28 packages over there —
so 240 mm, the longest board the machine has, is the only candidate and it refuses the
BOM as written.

⚠ **And the binding constraint is not only area.** At 83 % of placeable area the skyline
reaches **91.9 mm of the 97 mm** the packer allows, so the card runs out of *height*
before it runs out of *board*. Levers that delete small packages help less than their
area suggests, which is why the two that work are the ones that delete many.

> ⚠ **`graphics.md` §14.2.4's "99.1 cm²" is stale**, and this is how it was found: the
> packer reports **124.4 cm²** for the card as it stands today. That figure was written
> for the 28-package build of 2026-09-08 and nine packages have landed since. It is the
> repository's oldest defect class — a headline number outliving the design — and
> `lib/docs.check.ts` does not guard courtyard figures, only utilisation and IC totals.
> **Raised here rather than fixed here**, because it belongs to that document.

### 11.2.1 What does place — measured

| | ICs | 240 mm | Depends on |
|---|---|---|---|
| **A** as budgeted | 62 | ⛔ 7 over | — |
| **B** = A + `74HC40103` counters | 58 | ⛔ 3 over | nothing — §11.3 |
| ⭐ **C** = B + the tri-state pixel bus | **54** | ✅ **74 %** | ⚠ **a bench result that does not exist** — `graphics.md` §19 item 2 |
| ⭐ **E** = B + text only | **52** | ✅ **71 %** | nothing — but it ends the 256-colour claim |
| **F** = B + one fetch rank | 54 | ✅ 73 % | gives up byte-granular scroll **and §6.3's text pipeline** — see below |
| **D / G** = C or F + text only | 48 | ✅ 66–67 % | both of the above |

**Two independent levers are needed and one lever is not enough.** That is the finding,
and it sharpens §15 item 0 into the first decision the design has to make:

- ⚠ **C is the cheapest route that keeps every feature, and it rests on a measurement
  nobody has taken.** `graphics.md` §19 item 2 has carried *"bench the pixel-bus
  turnaround at 39.7 ns"* since the first draft of that card, and its own BOM budgets
  the four `'153` as the **default** precisely because the tri-state version is
  unproven. **A design that only fits if an open bench item comes out the right way is
  not a design that fits.** ⭐ `video2` has one advantage here that `video/` does not:
  deleting the LUT leaves ~25 ns of margin in the dot path (§10) where that card had
  11.7, so the turnaround has much more room — **which makes it a good bet and still a
  bet.**
- **E is the route that depends on nothing**, and it costs bitmap mode — the whole of
  the "256-colour" half of the brief. Text mode keeps its per-cell 256 colours.
- ⛔ **F is a trap and is listed only to rule it out.** One fetch rank saves four
  packages, and §6.3 shows the text pipeline *cannot* work with one: rank A holds cell
  *N+1* while rank B displays cell *N*. `graphics.md` §6.4.9 records the same mistake
  costing a picture displayed one cell to the left, and `graphics.md` §8.2 proves no
  clock instant fixes it. **The four packages are not available.**

**If both levers are refused**, the remaining option is a two-board set — the machine has
six slots and five cards (`hardware/README.md` open item 5), so the space exists, and
`graphics.md` §14 already treats a piggyback as the shape a blit datapath would take.
⚠ **Nobody has costed the connector, the crossing delay or the second card edge.**

### 11.3 The levers, priced

| | Δ packages | What it costs |
|---|---|---|
| **8-bit loadable counters** (`74HC40103`) in place of `'163` pairs on the four counter chains | **−4** | ⭐ **A part the machine has already priced** — `audio.md` §4.2 costs a bank of them and rejects it there for a reason that does not apply here (sixteen packages against a shared compare). It counts **down**, which the ROM tables do not care about: a table is indexed by whatever its counter emits |
| **The tri-state pixel bus closes at 39.72 ns** and the four `'153` come out | **−4** | `graphics.md` §19 item 2's standing bench item, inherited unchanged |
| **Text only — no bitmap mode** | **−6**, measured | the scan `/OE` group and the mode concatenation mux go; the counters stay, because the cell address needs them. **It also ends the 256-colour claim** |
| **Two-byte cell** `{char, attr}` + a 16 × 8 colour file (2 × `74LS189`, 2 × `'574`, 1 × `'157`) | **+5** | ⭐ **halves every CPU figure in §6.4** — 9.5 ms redraw, 0.38 ms scroll, 5.5 % CPU at 115.2 kbaud — and gives the VGA-style "16 colours or 8 + blink" model. It costs per-cell 256-colour text. **This is the one trade in the plan that is genuinely close** — §15 item 1 |
| Four `AS6C1008` ×8 instead of two ×16 | **+2** | buys back `graphics.md` §15's 1989 date on the framebuffer |

---

## 12. Period audit

| Element | Introduced | Verdict |
|---|---|---|
| VGA, 25.175 MHz, 640×400@70 | **1987** (IBM PS/2) | period-exact — the standard clock |
| Microcode in ROM, pipelined control store | **1964** (IBM S/360), universal by 1975 | **the oldest idea on the card** |
| Character generator with a RAM font | 1977 (Apple II ROM font), 1981 (IBM MDA) — RAM fonts by **1982** (EGA) | period-exact |
| R-2R SIP ladder DAC | forever | period |
| 74-series `'163`/`'157`/`'153`/`'574`/`'165` | 1970s | period |
| **`74AHCT`** | ~1990 | ⚠ **the newest 74-series family on the card**, as on `video/`. `74F` is the period-honest substitute on the dot path — and ⛔ **not `74AHC`**, §11 |
| **Flash memory as a part class** | **1988** — Intel 28F256, 32K×8 | period, **just.** It is the same class of claim `graphics.md` §10.1.2 makes for the CPLD: the architecture's date, not the part number's |
| **`SST39SF040`** | 1990s silicon | ⚠ **outside the date, knowingly** — the same concession `graphics.md` §15 makes for the `AS6C8016`. The 1988 build is a 28F256-class part with a 12 V programming supply and a smaller control store; nothing in the design changes |
| `AS6C8016` 512K×16 | ~1995 | ⚠ outside the date; four `AS6C1008` is the 1989 build (§11.3) |

⭐ **A `MC6845` CRTC was considered and refused on one number.** It is the period-correct
answer to *"where does the raster timing live"* — MDA, CGA, the BBC Micro and the
Amstrad CPC all use one — and it would collapse §4's vertical table, the two raster
counters and the cursor into a single package. **It cannot run at this card's character
rate**: 640 dots of active video at 25.175 MHz is a 3.1469 MHz character clock, and
⚠ **the fastest part in the family (`68B45`) is a recalled 2.0 MHz and there is no 6845
datasheet in `reference/datasheets/`** — the figure needs a primary source before it is
load-bearing, and it is the whole of the refusal. It also emits a 14-bit refresh
address with a 5-bit row (16 KB, 32 rows), which reaches neither the 4-byte cell nor the
bitmap. **Recorded so the choice is deliberate rather than inherited**, and the timing
tables of §4 are the same idea done in ROM.

**The card as an architecture places at 1988–1990**, and the one part that is not period
at all is the CPU, which is the project.

---

## 13. How it gets checked — and the checks come first

⛔ **This repository's oldest defect class is a design output that is absent while the
prose does not notice** ([`CLAUDE.md`](../CLAUDE.md); `docs/design-review2.md` found
eleven blocks described as fitted with nothing behind them). **A control store in flash
is the same hazard wearing different clothes**: a ROM image is easy to describe and easy
not to generate.

So the ROM images are **build outputs, never files**, and the plan is that they are
checked three ways before a board exists:

| | |
|---|---|
| **`npm run gen:ucode`** | assembles `video2/ucode/*.ts` into the two ROM images and a listing. ⚠ **Nothing is hand-assembled and no image is checked in** — the same rule `hardware/gal/verilog/`'s generated Verilog keeps |
| **`check:ucode`** | executes the images: walks a whole frame of microwords per mode and asserts the raster geometry, the sync widths **and polarity**, the fetch cadence, that **exactly one source drives the address bus in every slot**, and that every counter enable carries the slot tick and no load does. This is `cadence.check.ts`'s shape, against a table instead of against fitted terms |
| **the timing tables are generated from `sync.timing.ts`** | the arithmetic `npm run check` already asserts for `video/`. **One origin, two devices** — the rule `audio.cpld.ts` and `graphics.md` §10.1.6 already follow |
| **`check:video2`** | Verilator, over the whole card: a hand-written `video2_card.v` instantiating the ROM images, the SRAM model, the counters and the dot path, with testbenches for the raster, the cell cadence, the font pipeline and the host port |
| ⭐ **`machine_tb`** | **the card in the machine, running 6809 code out of the boot ROM.** `graphics.md` §19 items 36–38 are three defects that twelve testbenches and 543 model claims could not find and the first executed instruction did — *"a testbench that drives `E` from its own free-running counter has a CPU that cannot be waited"*. This card does not use `/WAIT`, which makes §8.3's read the claim that needs a real CPU cycle most |
| **`check:place`** | §11.2, and it is **step 0**, not a formality |
| **`check:netlist`** | ⛔ `graphics.md` §19 item 34 is that `cards/video.circuit.tsx` is a partial board and *"that is where the next M-1 will hide"*. `video2` draws the whole card or it does not claim the check |
| **`check:pins`** | the sense of every pin against what it is wired to. It found nine inverted pins across three boards on 2026-09-11, on a machine where no simulation could see them |

⚠ **One check this card needs that `video/` does not.** The control store is indexed by
the slot counter, so **a one-word shift in the table is a whole-picture defect that
looks exactly like a timing bug.** `check:ucode` must assert the table's alignment
against the counter's own reset value and count direction — particularly if §11.3's
down-counter lever is taken.

---

## 14. Build order

| # | Step | Exit criterion |
|---|---|---|
| 0 | ⛔ **Decide which two levers close §11.2's seven packages**, then put the BOM in `hardware/place/parts.ts` and a board file in `hardware/cards/` so `check:place` asserts it rather than a scratch script | the card places on 240 mm **from the repository's own parts list**. ⚠ **Before anything else, and it is a design decision and not a counting exercise** — §11.2.1 |
| 1 | **Bench the dot path and the CPU access on a breadboard**: SRAM → fetch latch → `'153` → `'273` → ladders → drive stage at 25.175 MHz, driven by counters | 640×400@70 colour bars locked on the target monitor in both `VMODE` families; black measured at 0.000 V through the porches; DNL across all 8 red codes at the connector into 75 Ω; ⚠ **and §8.3's 27 ns measured directly, not inferred from a working read** |
| 2 | **Write the microcode assembler and the two tables; run `check:ucode`** | a whole frame of microwords executes, in all four modes, with the claims of §13 |
| 3 | **Verilate the card** — `video2_card.v` against the generated images | the raster, the cell cadence, the font pipeline and the host port |
| 4 | **Card rev A**, driven by the STM32 bus exerciser (`graphics.md` §16.1) — no 6309 core needed | registers read back; a font loads; a bitmap scans; `HSCROLL`/`VSCROLL` smooth in both axes |
| 5 | **Text mode end to end** | 80×25 from 6809 code, per-cell colour, blink, four font banks, and a scroll that is one register write |
| 6 | **`machine_tb`** — the card, the motherboard and a 6809E core running the boot ROM | a frame whose every cell is what the software wrote |
| 7 | **An ANSI renderer** in `software/`, and the acceptance test | ⭐ **a real `.ANS` file from the BBS corpus, rendered, and compared against a reference renderer** — §15 item 2 |

**Steps 0 and 1 come before layout.** They hold the two numbers that can send the design
back: whether it fits a board, and whether the flat read closes.

---

## 15. Open items

0. ⛔ **Which two levers close §11.2's seven packages. Nothing else can be drawn until
   this is answered**, and it is the one item on this list that is a decision rather
   than a measurement. The three live answers, from §11.2.1:

   | | ICs | What it spends |
   |---|---|---|
   | **C** — 8-bit counters + the tri-state pixel bus | 54 | ⚠ **an open bench item** (`graphics.md` §19 item 2). Keeps every feature, and §10's ~25 ns of dot-path margin is why it is a better bet here than on that card |
   | **E** — 8-bit counters + text only | 52 | **bitmap mode** — half the brief, and the whole of "256-colour" outside a text cell |
   | **two boards** | 62 | a connector, a crossing delay and a second card edge, **none of them costed** |

   ⭐ **C and E are not exclusive**: building C and keeping E as the retreat costs
   nothing until the bench answers, because the two differ by which packages are
   *deleted* and both place. **The order that wastes nothing is bench first, layout
   second** — which is what §14 steps 0 and 1 say, and the reason step 1 exists before
   any board is drawn.

1. ⚠ **The cell format is not finally decided, and it is the closest call in the plan.**
   Four bytes with direct RGB332 fg and bg costs **zero packages** and gives per-cell
   256-colour text; two bytes with a 16 × 8 colour file costs **+5 packages** and
   **halves every CPU figure in §6.4**. The plan recommends four. The measurement that
   would settle it is item 4's, because the whole difference is CPU time.
2. **The acceptance test has to be a real ANSI file**, not a synthetic pattern.
   `audio.md`'s equivalent is *"play an existing OCS module unmodified"* and it is what
   found two audible defects that 43 green claims did not. A `.ANS` from the corpus,
   rendered by the card and compared pixel-by-pixel against a software reference, is the
   same lever — and `graphics.md` §8.2's whole-line pixel comparison is the form it takes.
3. **The span writer is not built, and its price is recorded.** ~6 packages (a 19-bit
   address counter, a length counter and the sequencing) for solid fills at one byte per
   158.9 ns slot, or four with a broadcast write. **What it would buy on this card** is a
   full-screen bitmap clear at ~5 ms against `TFM`'s ~183 ms, and nothing at all in text
   mode. Not needed for the stated goal; not hard to add.
4. ⚠ **Confirm the 6309 store rate against native-mode cycle counts.** Every
   microsecond in §6.4 scales on `graphics.md` §7.3's unverified 5 cycles per store, and
   §19 item 1 of that document says the repository cannot settle it from the Hitachi
   datasheet, which documents emulation mode only. **It is still the cheapest
   measurement on either card.**
5. **A hardware cursor is 3 packages and is not built** (§6.5). Revisit only if the
   software cursor's ~9.5 µs per move turns out to matter, which it should not.
6. ⚠ **`graphics.md` §14.2.4's courtyard figure is stale** — it says 99.1 cm² and the
   packer says **124.4** for the card as it stands. Found while measuring §11.2 and
   **not fixed here**, because it belongs to that document and `CLAUDE.md`'s maintenance
   rule says a superseded number moves to `video/docs/history.md` with its date.
7. **Whether `video/` and `video2` share `software/`.** The register maps agree at
   `+$00`–`+$04` and at `VSTAT`, and diverge everywhere else; whether one driver serves
   both with a mode flag, or two drivers exist, is a software decision nobody has made.
8. ⚠ **Nothing here is drawn.** No `hardware/cards/video2.circuit.tsx`, no
   `hardware/place/parts.ts` entry, no ROM images, no testbench. **This document is a
   plan and the repository contains no evidence for any number in it** beyond the ones
   cited from `video/docs/graphics.md`.

---

## 16. Sources

- [`video/docs/graphics.md`](../video/docs/graphics.md) — the card this borrows from.
  §2.1 the interleave and the slot grid, §5.2.2 spare-first ordering, §6.1–6.2 geometry
  and sync polarity, §6.3.2 `/IOPAGE`, §6.4.1 the no-adder property, §6.4.9 the fetch
  cadence and the one-cell lead, §7.3 the CPU write cost, §8.2 the two fetch ranks,
  §9/§9.1/§9.2 the palette argument and the drive stage, §10.1.1 where the macrocells
  go, §11 the flat-read decision, §12 interrupts, §13 the register map, §14.1/§14.2 the
  budget and the SRAM parts, §15 the period audit, §19 items 1, 2, 3, 6, 34, 35, 43, 44.
- [`video/docs/features.md`](../video/docs/features.md) — the capability view, and §2.4's
  cell-mode text figures, which are the ones §6.4 compares against.
- [`video/docs/history.md`](../video/docs/history.md) — **§6.4.3, the dropped 1bpp
  character generator**, kept there *"because it is the design a rebuild would start
  from"*. This is that rebuild, with an 8-bit attribute pair instead of a LUT page.
  Also §10.1, the GAL-build tables §11.1 cross-checks against.
- [`docs/machine.md`](../docs/machine.md) — §1 the clock tree, §2 the backplane and
  `/IOPAGE`, §3 the `$FF` map, §4 interrupt ownership, §5 items 1, 8 and 10.
- [`hardware/README.md`](../hardware/README.md) — the 72-pin slot, the card format and
  the checks. [`hardware/lib/parts.ts`](../hardware/lib/parts.ts) — `FLASH_512K`, the
  `SST39SF040` pinout this card's control store uses, confirmed against the datasheet.
- [`CLAUDE.md`](../CLAUDE.md) — the documentation and verification rules §13 is written
  to satisfy.
