# Design Review 2 — 2026-09-09

## What Simulation Found That Term Lists Could Not

**Question this answers:** between 2026-09-06 and 2026-09-09 the project added
tile mode, a display list, sprite mode, a boot ROM, a 32 MB map, SIMM sockets,
programmable panning, a headphone amplifier and a `16C550`. Every one of them
landed with a passing check. **The checks pass and several of the features do
not work**, and the reason is structural rather than careless: every check in
`hardware/gal/` executes *one design's equations* against *that design's model*,
and the defects below are all in the seams — a signal produced on one part and
consumed on another, a name that means two things, a latch whose contents are
right and whose lifetime is not, a package that is counted as absorbed and never
written.

> **This document is a frozen dated record, like
> [`design-review.md`](design-review.md).** Never update its findings; the specs
> and the per-component `history.md` files carry what changed after it.

**Method.** Two passes, and the second is new to this project:

1. **A port census.** Every `Merged` CPLD and every `Design` GAL was enumerated
   for signals it *consumes* and nothing in the machine *produces*. This is
   two dozen lines of TypeScript and it found eleven.
2. **Simulation.** `hardware/gal/verilog/emit.ts` generates Verilog from the
   same `Cell` term lists that `cupl.ts` compiles for the fitter, so the
   simulation runs **the fitted design and not a retyped copy** — the one-origin
   rule `jedec/cupl.ts` already states. Six testbenches run the video card, the
   audio card and the motherboard over whole frames, whole lines, whole spans
   and the boot sequence. `npm run check:video` from `hardware/`.

**Result: 122 claims verified, 16 failures across 10 distinct defects**, plus
eleven unbuilt blocks the census found and eight stale statements in the specs.

---

## 0. The findings, ranked

| # | Where | Finding | Evidence |
|---|---|---|---|
| **V-1** | video | ⛔ **Four packages were deleted from the IC count as "absorbed into the CPLDs" and the logic was never written.** `SPANLEN`'s counter, the `'165` mask serialiser, `CTRL`'s write strobe and `VSTAT`'s. The span writer has no length, no mask bit and no way to be configured | census |
| **V-2** | video | ⛔ **`WSTB` means two different things.** `rfa` produces it as the register-file write strobe; `seqctl` consumes it as §3.1.1's posted VRAM write. As wired, **writing any card register starts a span, and a posted VRAM write starts none** | `vspan_tb` |
| **V-3** | video | ⛔ **The display list cannot advance and cannot terminate.** `LADV` is produced by `vaddr` and read by nothing; `LGRANT` is declared external on `vctrl` and produced by no cell. The engine re-executes descriptor byte 0 forever | `vspan_tb` |
| **V-4** | video | ⛔ **§5.2.2's sub-slot ordering is not implemented.** `LINEAR`, `TILESEL` and `SPNGRANT` carry no phase term, so the scan address holds the shared internal bus for all four dots of every slot and a granted span removes it entirely | `vaddr_tb` |
| **V-5** | video | ⛔ **Every cell renders the next cell's tile.** `MAPLD` overwrites the code register in the first slot of the cell that still needs it. 158 of 160 tile fetches on a line carry the wrong code | `vtile_tb` |
| **V-6** | video | ⛔ **`WADV = 01` advances the row and never reloads the column**, so §7.2's chained glyph stair-steps eight pixels right per row. And `WROWADV` is buried inside `vctrl`, so on silicon the row does not advance either | `vspan_tb`, census |
| **V-7** | video | ⚠ **HSYNC is positive in the 525-line family.** `HPOL = !VMODE0` contradicts §6.2.1's own table and the VGA standard, both of which are negative-H in both families | `vsync_tb` |
| **M-1** | machine | ⛔ **The high byte of every MMU block register is unwritable.** `MAPA3` is the `'157`'s task bit *and* U9's low/high SRAM select. No task can have both bytes of a block set, so **nothing above physical 2 MB is reachable — including all of system RAM** | `mainboard_tb` |
| **M-2** | machine | ⚠ **Physical `A20`–`A13` float on the backplane during every ordinary I/O cycle.** The map SRAMs are deselected, the boot `'244` is off, and nothing else drives them | `mainboard_tb` |
| **A-1** | audio | ⛔ **The audio engine is not designed.** The card's one CPLD holds the host register block and a slot counter. §3's pipeline, §4.2's hit handling, §3.3's shadow reload, §6.2's converter write windows, §8.2's timer compare, §9.4.3's commit rule and §11.1's pan multiplexer are in no design file | census |
| **A-2** | audio | ⛔ **A channel's end-of-buffer interrupt is delivered only by coincidence.** `MERGE` fires on the trailing edge of a host *read* of `AINTREQ`, ANDed with `CCLK` — one slot in eight. Measured: **2 of 16 read phases** | `audio_tb` |

Eight stale statements in the specs are in §7, and they are corrected in this
pass.

---

## 1. The video card

### 1.1 What works, and it is most of the card

The simulation verifies 71 claims about the video card against the fitted term
lists. **The address generator is correct in every mode and at every scroll
position tested**, which is the largest single body of design on the card and
the one with the most opportunities to be wrong:

| | |
|---|---|
| **Raster geometry** | all four `VMODE` codes: 800 × 449 and 800 × 525 exactly, 96-dot HSYNC, 640 unblanked dots on every line, 400/480 active lines, `BLANK = HBLANK # VBLANK` over a whole frame |
| **Bitmap scan address** | 160 fetch slots address the right 160 groups, at `VSCROLL` 0/7/511 and `HSCROLL` 0/64/768/848 — including the column counter wrapping inside the row and the row counter wrapping 511 → 0 mid-frame |
| **Line doubling** | `VMODE 00`/`01` show each row on exactly two consecutive lines starting at display line 0; `10`/`11` show 400/480 distinct rows. §8.1's one-term parity trick works in both families |
| **Tile addressing** | 80 map accesses and 160 tile fetch slots per line; every map address is `MAPBASE \| cellRow<<7 \| cellCol`; every tile address is `TILEBASE \| code<<6 \| row<<3 \| half<<2` |
| **Cell-mode scroll** | `VSCROLL += 8` advances one cell row, `VSCROLL += 1` is pixel-smooth, `HSCROLL = 24` starts at cell 3, `HSCROLL = 768` wraps the 128-cell ring, and cell row 32 is cell row 0 |
| **All four `WMODE`s** | direct retires 1 byte, mask 8 with `WFG`/`WBG` per bit MSB-first, solid `SPANLEN`+1, sprite 8 retired and 4 written with the pointer still advancing 8 |
| **`/WAIT`** | a CPU VRAM write during a span pulls it, a read does not, and an I/O-page read never does — §7.4's polling rule holds |
| **VBL** | `/IRQ` asserts once vertical blank is reached and a `VSTAT` write clears it |

⭐ **§8.1's counter-enable rule survives contact with a whole frame.** The
distinction between a *load* (idempotent, ungated) and an *enable*
(`SLOTTICK`-gated, or the counter advances four times a slot) is the kind of
thing that is invisible in a term list and fatal in a raster. It is right.

### 1.2 V-1 — the four absorbed packages do not exist

`graphics.md` §10.1.6 says the CPLDs absorbed *"`CTRL`'s `'273` (+8), the
`'161` `SPANLEN` pair (+10) and the `'165` (+8)"*, §14.1 books them as **−4
packages** in the 27-IC count, and §7.4 says the mask serialiser and the
`SPANLEN` down-counter *"live in `vctrl`"*. **They are in no design file.**

The census lists every `vctrl` and `vaddr` input that nothing on the card
produces:

| Signal | Consumer | What §-text says produces it | Cell? |
|---|---|---|---|
| `TC` | `seqctl`'s `SPANEND` for span-solid | §7.4 — "the `SPANLEN` down-counter in `vctrl`" | **none** |
| `MASKBIT` | `seqctl`'s `WEN` for sprite mode | `features.md` §8.4 — the serialiser's serial output | **none** |
| `WCTRL` | `CTRL`'s eight registered bits | §10.1.6.1 — "`CTRL` never crosses the boundary" | **none** |
| `VSTATWR` | `vdec`'s `VBLPEND` clear | §13 — "write clears IRQ" | **none** |
| `SPNREQ` | the arbiter's span request | §5.2.1's `SPNREQ` | **none** |
| `HS0`, `HS1` | `seqph`'s `MUXSEL`/`FCLK` | §8 — "`HSCROLL[1:0]` preloads the output phase" | **none** |
| `WADV0`, `WADV1` | `seqctl`'s `WROWADV` | §13 `+$14` | **none** |
| `BCTRLGO` | the list engine's `LRUN` | §10.3.1 — `BCTRL` b0 `GO` | **none** |
| `FP0`, `FP1` | `rfa`'s read-back walk | §19 item 23(b) — "a two-bit walk at span end" | **none** |
| `LGRANT` | the list engine | declared **external on `vctrl`**, produced by nothing | **none** |
| `WROWADV` | `vaddr`'s `wrow` counter | produced on `vctrl` and **not exported** | buried |

**Three consequences, and the third is the expensive one:**

1. **`CTRL` cannot be written**, so `VMODE`, `WMODE`, `CELL`, `IRQEN` and
   `DISPEN` are unreachable. The card comes up with `CTRL = 0` — display off,
   direct writes, no IRQ — and stays there.
2. **A span-solid never terminates.** `SPANEND` for `WMODE 10` is
   `RETIRE & SOLID & TC`; with no `TC`, `SPANBUSY` latches, and `/WAIT` then
   asserts on every CPU VRAM write for ever. The first `PaintRect` hangs the
   machine.
3. ⚠ **The logic does not fit the part it was deleted from, and macrocells are why.**
   `vctrl` is at **122 of 128 logic cells, 64 of 64 I/O and 4 of 4 dedicated inputs**
   (`cpld/vctrl.fit`). Writing the missing blocks costs, on `vctrl`:

   | | cells | pins |
   |---|---|---|
   | `SPANLEN` down-counter + `TC` | 9 | **−1** (`TC` stops being an input) |
   | mask serialiser + `MASKBIT` — loaded from `D0`–`D7`, which are already on the part | 8 | **−1** |
   | `HS0`/`HS1` + `WADV0`/`WADV1` registers | 4 | **−4**, **+3** for their load strobes |
   | `SPNREQ` | 1 | **−1** |
   | `FP0`/`FP1`, `LGRANT`, `WROWADV` exported | 2 | **+4** |
   | `WCTRL`/`VSTATWR`, decoded on `vaddr` where `RA0`–`RA4` are | 0 (there) | **+2** in |
   | **total on `vctrl`** | **≈24 against 6 free** | **≈ +2 against 0 free** |

   ⚠ **The pins nearly wash** — seven of the eleven missing signals are input pins today
   precisely *because* the logic behind them is absent, so building it hands most of
   them back. **The macrocells do not.** ≈24 cells against 6 is the binding number, and
   §14.2's two-×16 framebuffer does not help with it: that rewrite returns six output
   pins by making the arbiter 2 grants instead of 8, and **no cells at all**.

   **So the card as specified does not fit two `ATF1508AS` PLCC-84s**, and the shortfall
   is on the part `features.md` §8.4 already recorded as *"nothing else can be added to
   `vctrl` at all"*.

> **What to do about it is a design decision and this document does not make
> it.** The three candidates are: take §14.2's rewrite and a third package; move
> `rfa` back on-part and put the serialiser and counter on a second GAL; or
> accept the `'161` pair and the `'165` as the discrete packages they were and
> restate the count as **29 ICs**.

### 1.3 V-2 — one `WSTB`, two meanings

`rfa` produces `WSTB = REGSEL & !RW & E` — a write to `$FF60`–`$FF7F`.
`vaddr`'s `writeStrobes` decode it correctly as a register write
(`LDVSL = WSTB & RA==1`). **`seqctl` consumes the same signal as §3.1.1's
posted VRAM write**, the thing that starts a span:

```
  SPANBUSY.d = WSTB # (SPANBUSY & !SPANEND)
```

Simulated on the card as wired (`video_card.v` with `SPLIT_WSTB = 0`):

```
FAIL  writing HSCROLL does not start a span
FAIL  and a posted VRAM write DOES start one
```

**Both directions are wrong.** A `STA HSCROLL` sets `SPANBUSY` and starts
retiring bytes at whatever `WPTR` holds; a `STA` into the framebuffer produces no
`WSTB` at all and the span writer never runs.

**The fix is a second strobe**, `VRAMSEL & !RW & E`, which `vctrl` can form
locally — it already has `VRAMSEL`, `RW` and `E` — for one macrocell and no pin.
Every other testbench in this pass runs with the two split, which is why the
`WMODE` results in §1.1 are meaningful.

⚠ **And `WSTB` is a level, not a pulse.** `seqctl`'s mask counter is held at
zero by `!WSTB` for as long as it is asserted, so the retire that fires while
E is still high does not count. With the strobe split and a 6-dot E-high window
the mask modes still retire exactly eight, but the margin is not a designed one
and §7.4's "one pulse per posted write" should be built as one.

### 1.4 V-3 — the display list runs but cannot walk

`graphics.md` §10.3 and `features.md` §4 both say the engine is **built**. It
is fitted, its macrocells are real, and it does nothing useful:

```
FAIL  BSTAT b0 LRUN falls when the engine meets the $FF terminator
FAIL  the engine executed one MOVE per descriptor byte (got 5000, want 9)
FAIL  and it clobbered WPTR, which is 10.3.1's rule (got 8192)
```

Two independent breaks:

- **`LADV` is produced and dropped.** `video.parts.ts` says *"`LADV` drives
  `WPTR`'s increment"*, and `wcol`'s counter enable is `WINC` — an input to
  `vaddr` that nothing renames onto `LADV`. The pointer never moves, the same
  descriptor byte is re-fetched for ever, `LSTOP` never sees `$FF`, and `LRUN`
  never falls.
- **`LGRANT` has no producer.** `vctrl` lists it in `external` and has no cell
  for it, so `LADV`, `LFETCH` and `LMOVE` — all `LRUN & LGRANT` — are dead on
  silicon whatever `WINC` does.

⚠ **And there is a third gap that is not a wiring one.** The engine as designed
decodes **no opcode and carries no operand**: `LMOVE` is `LRUN & !LSTOP &
LGRANT`, so every descriptor byte is a `MOVE`, and nothing selects a register
or supplies a value. There is no scanline compare either, so the walk is not
locked to the raster. **What is built is a byte-fetcher that stops at `$FF`.**
`features.md` §4's "per-scanline `HSCROLL`, palette and mode changes with no
CPU" needs a `WAIT`-for-line opcode, a register address and a data byte, and
none of the three is designed.

⭐ **The 10.3.1 reload rule is unaffected and remains correct**: the engine
shares `WPTR` by construction, so the rule software has to keep is real
whatever the engine ends up executing.

### 1.5 V-4 — the spare access is not in the front half of the slot

§5.2.2 is a **specification sentence** — *"the CPU/spare access occupies the
FRONT half of the slot, the display fetch the back half"* — and §11's read
budget closes at +46.9 ns because of it and misses by −25.1 ns without it.

`seqph` builds `SPAREWIN = !PH1` faithfully. **Nothing uses it.** The signals
that actually put an address on the card's one internal bus are:

```
  MAPSEL  = MAPREQ & !PH1                 <- phase-qualified
  TILESEL = TILEMODE & !MAPSEL & !SPNGRANT   <- not
  LINEAR  = !TILEMODE & !SPNGRANT            <- not
```

Measured over a slot in bitmap mode:

```
FAIL  LINEAR is asserted for the fetch half only - 2 dots of 4 (got 4)
```

**Three consequences:**

1. **The display address is on the bus for the whole slot**, so there is no
   spare window for the CPU or the span writer to use, and §11's read budget is
   not the one the card implements.
2. **`SPNGRANT` has no phase term either**, so during a span the display fetch
   loses the address bus for **all four dots** — `LINEAR` and `TILESEL` both go
   low. A span-solid running through active display blanks the picture for its
   duration, which at §7.4's 40.7 µs bound is longer than a scanline.
3. ⚠ **§19 item 23(a)'s per-chip `FCLK` scheme cannot work with it.** The
   mechanism needs two fetch groups live at once, which needs the early and late
   clocks to catch *different* data. With the address applied at the start of the
   slot instead of at 79.4 ns, a 55 ns SRAM has settled long before the early
   edge at 119.2 ns, so both edges latch the same group and byte-granular
   horizontal scroll reverts to the Rev A failure `seqph.check.ts` says it
   fixed. `seqph.check.ts` does not see this because it models the latch
   contents as *"one more group if clocked at phase 0"* rather than deriving
   them from what is on the data bus.

**The repair is small and it is in `tileCadence`**: `SPNREQ` and the display
selects want `SPAREWIN` in them. What it is *not* is free — `vctrl` has six
cells left.

### 1.6 V-5 — the tilemap is displayed one cell to the left

§6.4.9's own diagram is right:

```
  slot     2k            2k+1          2k+2          2k+3
  spare    map[N+1]      -             map[N+2]      -
  fetch    tile N.0-3    tile N.4-7    tile N+1.0-3  tile N+1.4-7
```

In slot `2k` the spare access fetches `map[N+1]` **while the display fetch is
still using code `N`**. So the map byte must be latched at the *end* of the
cell, not the beginning. The fitted equation latches it at the beginning:

```
  MAPLD = MAPREQ & !PH1 & PH0        -- true during dot 1 of slot 2k
```

Simulated over a line at `MAPBASE = $02`, `TILEBASE = $01`:

```
      tile slot 0 (cell 0): code 26, want 23  [cell+1 would be 26]
FAIL  each cell's tile fetch carries that cell's map byte (158 wrong of 160)
      of the 158 wrong, 158 carry the NEXT cell's code exactly
```

**Every cell on the screen displays its right-hand neighbour's tile**, and the
last cell of each line displays a duplicate. With the code held constant the
address concatenation is exact — the same testbench asserts all 160 tile
addresses against the code the card is actually holding and they are right — so
this is a one-signal timing defect and not an addressing one.

⚠ **`cadence.check.ts` does not catch it because it asserts the *fetch* lead
and not the *latch* lifetime.** It counts 80 map accesses in order and measures
the lead in dots, both of which are correct. What it never asks is which code
is in the `MAP` register when a given cell's tile address is formed.

**Two candidate repairs, and they cost differently.** Move `MAPLD` to the cell
boundary (`MAPREQ` delayed one slot, ANDed with `SLOTTICK`) — one macrocell and
a slot of extra lead, so `MFETCH` opens one slot earlier still; or add a second
`MAP` register clocked at the cell boundary — eight macrocells `vctrl` does not
have and `vaddr` does.

### 1.7 V-6 — `WADV` advances the row and loses the column

§7.2 is the section that makes text cost 13 writes per cell instead of 26:

> `WADV = 01` ("next row, same column"): when a span ends, reload `WPTR[9:0]`
> from the shadow and increment `WPTR[18:10]`.

The row half is built — `seqctl`'s `WROWADV` fires at `SPANEND` for both
non-zero `WADV` codes and `wrow` counts on it. **The column reload is not.**
`wcol`'s only load path is `LDA`/`LDB` from `D0`–`D7`, which is a CPU register
write; there is no register-file read path into it and no shadow.

```
FAIL  at span end WPTR is one row on and back at the same column:
      got 5128, want 5120
```

5128 is 5120 + 8: the row advanced and the column kept the eight bytes the
span had just retired. **A chained glyph stair-steps eight pixels to the right
on every row.** §7.3's 13-writes-per-cell, its 2.5 ms line scroll and every
figure in `features.md` §2.3 rest on this working.

⚠ **And on silicon the row does not advance either**, because `WROWADV` is
produced on `vctrl` and is not in its `external` set, while `vaddr` declares it
as an input. The simulation wires the two together explicitly and says so;
the card does not.

### 1.8 V-7 — HSYNC polarity in the 525-line family

§6.2.1 is unambiguous, and it is right about the standard:

| Mode | HSYNC | VSYNC |
|---|---|---|
| 640×400 @ 70 | **negative** | positive |
| 640×480 @ 60 | **negative** | negative |

`sync.jedec.ts` agrees — *"HPOL is strapped to 1 — HSYNC is negative in both
families"*. **`video.cpld.ts` does not**: `comb("HPOL", ["!VMODE0"])`, on the
argument in §10.1.6.1 that *"the 70 Hz pair is the positive-H pair"*. That
sentence is the error; the 70 Hz pair is the positive-**V** pair.

```
ok    VMODE 00: HSYNC is LOW through its pulse - negative (got 0)
ok    VMODE 00: VSYNC is HIGH through its pulse - positive (got 1)
FAIL  VMODE 01: HSYNC is LOW through its pulse - negative (got 1)
ok    VMODE 01: VSYNC is LOW through its pulse - negative (got 0)
FAIL  VMODE 11: HSYNC is LOW through its pulse - negative (got 1)
```

`VMODE 01` and `11` emit **+H/−V**, which is not a standard VGA mode
combination at 31.5 kHz. Most monitors sync on it regardless, so this is a ⚠
rather than a ⛔ — but §6.2.1's whole argument is that polarity is how the
monitor picks the vertical format, and a card that emits a non-standard pair is
not entitled to that argument.

**The fix is one character**: `HPOL` is a constant 1, exactly as `hgen`'s
comment says. It costs a macrocell it already has.

### 1.9 What the video simulation could not reach

- **The dot path.** §6.1's 11.7 ns margin, §9.1's ladder arithmetic and §9.2's
  blank-to-black are analogue and stay on the bench (§19 items 2, 3, 18).
- **The palette LUT and `PIDX`.** No design file describes the `'593` counter's
  control or the LUT-bus turnaround; §13.1's snow rule is a software rule and
  there is nothing to simulate.
- **The `'153` mux and the fetch latches** are modelled, but their *timing* is
  what §19 item 2 is about and this says nothing about it.

---

## 2. The audio card

### 2.1 A-1 — the engine is not designed

`audio.md` §10 lists the `ATF1508AS` as *"the whole of the card's logic"* and
§10.1.1 reports it fitted at 79 of 128 logic cells with 27 input pins. Both are
true. **What the part contains is the host register block and a slot counter.**

The complete input list of `audio.cpld.ts`, from the census:

```
A0 A1 A2 A3  D0..D7  E  RW  SEL  RESET  SET0..SET5
```

Address, data, the bus strobes, and six "an interrupt happened" flags. **There
is no state-file data, no compare result, no `PER`, no `NEXT`, no `PEND`.** The
complete output list is the slot decodes, `CCLK`, `CIACLK`, `DMAEN0`–`3`,
`CTRL0`–`7`, `SFCE`/`SRCE`, `FIRQ`, `RASTAT` and `S0`–`S2`. There is no
state-file address, no state-file `/WE`, no sample-RAM `/WE`, no `AD7528`
`CS`/`WR`/`DAC-select`, no `'574` clock and no adder control.

So the following, each of which the document describes as designed, is absent:

| §  | Block |
|---|---|
| §3.2 | the three-stage pipeline — state-file read, compare, mark-due |
| §3.1 | the deferred-work scheduler (there is a **one-bit** `DEFREQ`/`DEFACK` handshake and nothing behind it) |
| §3.3 | ⛔ the `LC`/`LEN` shadow copy at `CNT` = 0 — *"the single highest-value line in the sequencer GAL"* |
| §4.2 | what happens on a compare hit: `PEND` refill, `NEXT += PER`, `PTR`+1, `CNT`−1 |
| §4.2 | the `PER` = 0/1 clamp |
| §6.1 | `VOLCODE = VOL × 4`, and forcing it to 0 on a disabled channel |
| §6.2 | the two converter write windows, their `CS` decode and the `'574` clocks |
| §8.2 | the tempo timer's **compare and reload** — only the ÷5 prescale exists |
| §9.3 | `AIDX` and `SPTR` auto-increment, and the state-file address generation for either |
| §9.2 | `ASTAT` b6/b7, and `ASTAT`'s other six bits |
| §9.4.3 | ⛔ the **normative** double-buffered multi-byte commit |
| §11.1 | the pan multiplexer — §11.1's *"the term is `ch != 1,2` on one multiplexer input"* |
| §11.3 | attach modulation and `attach_target_valid` |
| §11.2 | 8-channel mode |
| §1 req 6 | `DMACON`'s restart delay |

**So the user-facing questions cannot be answered from the design.** Whether
this card plays a `.mod` accurately, whether it is jitter-free, and whether
panning works are all properties of the sequencer, and the sequencer is a
paragraph rather than a design.

⭐ **What *is* verified, and it is worth having.** The simulation runs the
part over thousands of slots:

| | |
|---|---|
| the slot walk | all eight slots visited equally; `CCLK` one slot in eight; slots 0–3 channels, 4 timer, 5 host, 6–7 deferred |
| ⭐ **the CIA-B clock** | **1000 colour clocks produce exactly 200 CIA ticks** — §8.2's ÷5 is the Amiga's clock and not an approximation |
| Paula's set/clear | `DMACON $8F` then `$05` leaves `$A`; `INTENA $BF` then `$10` clears bit 4 alone |
| `/FIRQ` | open-drain by the OE idiom: driven low when an enabled source is pending, released by masking the source without clearing the flag, flag cleared by a b7 = 0 write |
| the synchroniser | one host access produces exactly one `NEWREQ` pulse |

And the analogue and clock arithmetic re-derives correctly by hand:

| Claim | Check |
|---|---|
| 28.37516 MHz ÷ 8 = 3.546895 MHz | ✓ |
| `PER` 428 → 8287.1 Hz | 3546895/428 = 8287.14 ✓ |
| NTSC error +0.92 %, +16 cents | 1200·log₂(3579545/3546895) = 15.86 ✓ |
| CIA ÷5 = 709,379 Hz; `N` = 14,187 at BPM 125 → 50.002 Hz | ✓, and the 1-count difference from a real 8520 is 0.0070 % ✓ |
| slot 35.24 ns, colour clock 281.9 ns, 7.09 M deferred slots/s | ✓ |
| A500 filter 360 Ω / 0.1 µF and the scaled 3.6 kΩ / 0.01 µF are both 4421 Hz | ✓ |
| headphone: 2 V p-p = 0.707 V rms; 15.6 mW into 32 Ω; 22 mA rms; 470 µF → 10.6 Hz | ✓ |

⚠ **One small arithmetic slip in §7.1**: 10 Ω in series with 32 Ω is **−2.36 dB**,
not 2.6.

### 2.2 A-2 — a channel interrupt is delivered one time in eight, and only after a read

§9.4.5's rule is written to make "read `AINTREQ`, then clear what you saw"
race-free, and the equation implements it literally:

```
  MERGE = CCLK & SYNCR2 & !SYNCR1
```

`SYNCR` synchronises `RINTREQ`, which is the **read** strobe for `AINTREQ`. So:

- **Nothing merges unless the host reads `AINTREQ`.** A channel that exhausts
  its buffer sets `PEND`*n*, and `PEND`*n* stays set for ever. `REQ`*n* never
  rises, `FIRQANY` never sees it, and `/FIRQ` is never asserted. §1's
  requirement 7 — the per-channel end-of-buffer interrupt — is not delivered.
- **And even a read merges only by coincidence.** `SYNCR2 & !SYNCR1` is one
  slot wide; `CCLK` is one slot in eight. Whether they coincide depends on which
  slot the read happens to deassert on:

```
ok    the pending register catches it
FAIL  and it reaches AINTREQ without the host doing anything
FAIL  every host read of AINTREQ merges the pending bit
      (merged on 2 of 16 read phases)
```

Two of sixteen read phases is exactly the one-in-eight the arithmetic predicts.

**The intent is recoverable from §9.4.5's own wording** — *"merged into
`AINTREQ` on the colour clock **after** the synchronised read strobe
deasserts"*. That describes a merge that happens **every colour clock, except
while a read is in progress**, with a latched "merge pending" that survives
until the next `CCLK`. As one equation:

```
  MERGE = CCLK & !SYNCR2 & !SYNCR1        ; merge whenever no read is in flight
```

which is one literal's difference and delivers the interrupt.

---

## 3. Boot, the memory map and the I/O map

### 3.1 Boot works, and the simulation runs it

`mainboard_tb` builds U3, U6, U9 and U10 together with the two map SRAMs, the
`'157`, the `TASK` `'574`, the boot `'244` and both flash devices, and executes
`machine.md` §7.2's sequence:

```
ok    RUN comes out of reset at 0 - the machine is in boot mode
ok    $FFFE selects the boot ROM
ok    and it reads ROM $1FFE - the '244 drives A20..A13 to zero
ok    the reset vector's high byte reads back
ok    all eight logical blocks fetch from ROM $0400
ok    STA $FFB0 sets TASK and does NOT leave boot mode - $FFB0 is even
ok    STA $FFB1 leaves boot mode - the map takes over
ok    logical $0400 with a zeroed map is physical $0000400
```

⭐ **The odd/even split at `$FFB0`/`$FFB1` earns its one literal.** Writing
`TASK` before the block registers is only possible because `$FFB0` does not
leave boot mode, and the sequence depends on it.

⭐ **And the vector page is unconditional**, boot mode or not:

```
ok    $FFC0 does not assert /IOSEL - it is the vector page
ok    and the ROM answers there unconditionally, boot mode or not
ok    at ROM $1FC0 - the '244 drives, not the map
```

`graphics.md` §16 item 8's "drop a real HD63C09E in the socket" property holds.

### 3.2 The physical map decodes correctly

With the map loaded through a back door, every region of `machine.md` §2 answers
as specified:

```
      SIMM 0 at physical  4 MB: pa 0400000  DRAMSEL 1  RAS 0001
      SIMM 1 at physical  8 MB: pa 0800000  DRAMSEL 1  RAS 0010
      SIMM 2 at physical 12 MB: pa 0c00000  DRAMSEL 1  RAS 0100
      SIMM 3 at physical 16 MB: pa 1000000  DRAMSEL 1  RAS 1000
ok    all four SIMM windows decode - 16 MB of DRAM
ok    20 MB is past the last window and DRAMSEL stays low
ok    logical $0000 -> 0.5 MB
ok    the video ring at 0.5-1.0 MB leaves /IOPAGE released - cards may answer
ok    the card-buffer megabyte at A20 = 1 leaves /IOPAGE released
ok    the boot ROM answers at physical 2.0 MB as ordinary mapped memory
ok    and /IOPAGE is pulled above 2 MB, so no card answers
ok    both flash devices answer - physical A19 picks between them
ok    $FF60 asserts /IOSEL - the video card's window
ok    $FF80 does not - the geographic window is $FF00-$FF7F
```

⭐ **`/IOPAGE`'s redefinition works exactly as §2 claims.** Below 2 MB it is
released and the video ring and the card megabyte are visible to cards; above
2 MB U9 pulls it and every card goes silent, which is what buys four backplane
pins. And **U10's four `RAS` outputs are distinct across the four windows**, so
16 MB is reachable *by the decode*.

### 3.3 M-1 — but no task can point at any of it

**`MAPA3` does two jobs and they are incompatible.**

- `mainboard.circuit.tsx` wires the `'157`'s fourth bit as `4A = TASK`,
  `4B = LA3`, so during a map write `MAPA3` is **`LA3`**.
- `u9.model.ts` uses **`LA3`** to choose which map SRAM is written —
  `$FFA0`–`$FFA7` the low byte, `$FFA8`–`$FFAF` the high byte (`ram.md` §4.1's
  Layout A).

So a write to `$FFA8` (block 0's **high** byte) is steered to the high SRAM
**and addressed at entry 8**, which is task 1's block 0. Translation for task 0
reads entry 0 of both SRAMs. Simulated:

```
      after writing $FFA0 = $00 and $FFA8 = $02:
        entry  8:  low $00   high $02
      TASK is 0, so translation of block 0 reads entry 0.
FAIL  $FFA8 sets the high byte of TASK 0's block 0
FAIL  logical $0000 -> physical 4 MB (got 0000000, want 0400000)
FAIL  TASK 1's block 0 is not 4 MB either (got 0000000)
```

**Neither task can have both bytes set:**

| | low byte `A20..A13` | high byte `A24..A21` |
|---|---|---|
| TASK 0 → entries 0–7 | writable at `$FFA0`–`$FFA7` | **never written** |
| TASK 1 → entries 8–15 | **never written** | writable at `$FFA8`–`$FFAF` |

⛔ **The consequence is that nothing above physical 2 MB is reachable**, which
is all of system RAM, all four SIMMs and the whole of §7.2's ROM disk above the
first megabyte. A machine that boots and cannot find its memory.

**The root cause is that `ram.md` §4 never chose.** §4 presents Layout A and
Layout B and closes with *"Neither is obviously right… the decision belongs to
whoever owns the NitrOS-9 port."* `u9.jedec.ts` implements Layout A. `machine.md`
§3 and §5 item 3 describe Layout B (*"index = `A3..A0` = `{TASK, block}`"*,
*"`$FFA0+n` is task `n>>3`, block `n&7`"*, *"Bits 7–0 are physical `A20..A13`"*).
**The board is wired for B's index and decoded for A's byte select**, which is
neither.

**Both repairs are cheap and they are different machines:**

| | what changes | what it costs |
|---|---|---|
| **Take Layout A** | `MAPA3` must be `TASK` during a write as well as during a translation — i.e. the `'157`'s fourth bit stops being muxed and is strapped to `TASK` | **one trace.** 8 blocks × 2 bytes in the sixteen addresses; two tasks still exist and are selected by `TASK`, one map addressable at a time. `machine.md` §3 and §5 item 3 are then wrong and must be rewritten |
| **Take Layout B** | the high bytes need their own window — `ram.md` §4.2 puts them at `$FFB8`–`$FFBF` — and U9's `LA3` select becomes an `LA4`/`LA3` decode | **one more decode term**, and `$FFB0`–`$FFBF` stops being two aliased bits |

⚠ **`ram.md` §3.2's 256-context widening interacts with both**, and it is the
argument for A: with `TASK` widened to 8 bits the `'157`'s fourth bit has to
come from the register anyway, which is Layout A's wiring exactly.

### 3.4 M-2 — the physical address floats during every I/O cycle

`mmu.v` gives the map SRAMs `n_mapoe = ~(~iopage | (blksel & rw & e))` and U9
gives them `nMapCe = !((run && !iopage) || (blksel && …))`. So on any
`$FF00`–`$FF7F` cycle — every audio, video, serial, PS/2, storage and net
register access — **both map SRAMs are deselected**. U6's boot `'244` is off
too, because `RUN` is set and the address is not the vector page.

```
FAIL  something drives them - the map is deselected and the '244 is off, so if
      this fails they float on the backplane
```

**Nothing drives physical `A20`–`A13`.** `graphics.md` §6.3.2 consumer 3 says
they should be *"parked at a defined pattern during an I/O cycle rather than
carrying a stale translation"*, and `machine.md` §2 repeats it. **Parked and
floating are not the same thing.**

It is not a *logical* hazard — every card qualifies its physical decode on
`/IOPAGE`, which is exactly what §6.3.2 exists for, and the simulation confirms
the cards stay silent. It is an *electrical* one: eight backplane lines float
through every I/O cycle into the CPLD and GAL inputs of six cards, which is
CMOS input crowbar current and an oscillation risk on a bus with clock and sync
lines beside it.

**Three repairs, cheapest first:** extend the `'244`'s output enable to cover
every `$FFxx` cycle (one literal on U6 — it already forms the condition for
`VECSEL`); or bus-hold on the eight lines; or pull-downs, which
`machine.md` §7.2's own note rejects for `VECSEL` on settling-time grounds and
which have the same problem here.

### 3.5 SIMM population — 1 required, 3 optional

**There is no presence detection anywhere, and none is proposed.** U9 asserts
`DRAMSEL` for any address in 4–20 MB and U10 turns it into a `RAS` regardless
of whether a module is in the socket; a read from an empty socket returns
whatever the bus floats to. That is period-normal — no 1990 machine detected
SIMMs in hardware — but it makes memory sizing a **boot-monitor obligation that
no document currently states**. `machine.md` §7.2's boot sequence ends at
`lds #stacktop` with no sizing pass, and `ram.md` §6.4 has none either.

⚠ **And `ram.md` §6.3 offers a module size the mux mapping cannot use.** §6.3's
table says *"×8 or ×9, 1 MB or 4 MB each — 4 to 16 MB"*, while §6.3.1's own
mux mapping paragraph says a 1M×8 module **will not work** in the row `A10`–`A0`
/ column `A21`–`A11` wiring and needs a different one, *"a rewire, not a
jumper"*. **Only 4M×8 works as drawn**, so the machine is 4, 8, 12 or 16 MB and
never 1, 2 or 3. `machine.md` §0's "4–16 MB" is right by accident; §6.3's
"1 MB or 4 MB each" is not.

---

## 4. Serial

**No design artefact exists** — neither of the I/O card's two GALs is fitted
(`serial.md` §13 item 4), so there is nothing to simulate and this section is a
document review.

### 4.1 The maximum rate, verified

| Claim | Check |
|---|---|
| `TL16C550C`, 7.3728 MHz crystal | baud = xtal/(16 × divisor); divisor 1 → **460,800**; divisor 4 → **115,200** ✓ |
| 16-byte FIFO, 14-byte trigger, 115,200 baud | 115,200/10 = 11,520 B/s ÷ 14 = **823 interrupts/s** |
| §0 and `machine.md` §4.1 say **~1,030/s** | ⚠ **wrong** — 1,030/s implies 11.2 bytes per interrupt. The correct figure at a 14-byte trigger is **823/s**, which strengthens the argument rather than weakening it |
| `MAX232` rated 120 kbit/s | ✓ — and it is what pins the card at 115,200 |
| §5.4's tier table and §5.6 quote **460,800 and 921,600** | ⚠ **not reachable through a `MAX232`.** 460,800 needs a `MAX232A` (200 kbit/s) at least, and 921,600 needs neither part. §0's own "115,200 is what the card is planned at, because §8's level shifter is specified to 120 kbit/s" is the correct statement and §5.4/§5.6 contradict it |

**So the verified maximum is 115,200 baud**, level-shifter-bound, with the UART
and the crystal capable of 460,800 if §8's part is changed. §5.6's file-transfer
ceiling of 460,800–921,600 is a CPU calculation with no level shifter behind it.

### 4.2 Buffering and IRQ handling

**The FIFO and the `IIR` reasoning are sound and are the best-argued change in
the repository this week.** §7.3's conclusion — that a `16C550` can be probed
without being serviced, which releases `machine.md` §4.1's polling order — is
correct and correctly *not* acted on.

⚠ **Three things the card owes and has not been given:**

1. **`INTR` is active-high and totem-pole** (§9.1). The open-drain inversion is
   one macrocell on a GAL that **is not fitted**. Until it is, the card cannot
   join the wire-OR.
2. **`MR` is active-high** (§9.1) and the backplane's `/RESET` is not — another
   macrocell on the same unfitted GAL.
3. **`LCR` bit 7 spans two addresses** (§7.2). §10.3 must run initialisation
   with interrupts masked, and there is no other card in the machine with a mode
   bit that changes what two of its registers *are*.

⚠ **And §13 item 12 is stale**: *"`IRQB` open drain is assumed, not read"* is a
6551 item. §9.1 already establishes that the `16C550`'s `INTR` is **not** open
drain, so the item's answer is known and its mitigation is already in the
design.

### 4.3 The register map is recalled, not read

§13 item 1 is still open and it is the blocking one: **no `16C550` datasheet is
in `reference/datasheets/`**, so §7.2's eight-register layout and §7.3's `IIR`
encoding are from memory. `hardware/cards/io.circuit.tsx` marks the pinout
unverified. **Do not cut a board.**

---

## 5. PS/2

Also specification-only, and the design is careful. Two observations:

- ⭐ **The `'574` second-stage latch (§5.1) is the right call and is the kind
  of thing this review found missing elsewhere**: the `'595`'s storage register
  looks like a byte of buffering and is overwritten by the next frame's start
  bit. Recognising that cost two packages and bought the frame time.
- ⚠ **The transmit window is the machine's worst interrupt-latency case and it
  is unowned.** §7's host-to-device transmit masks `/IRQ` for **0.8–1.3 ms**,
  which is longer than a maximum Ethernet frame's arrival (`net.md` §3.3 sizes
  the RX ring for it) and, at 115,200 baud with a 14-byte FIFO trigger, longer
  than **13 FIFO fills** — so an LED update during a download still overruns the
  serial port, exactly as `design-review.md` §IO-P4 says, and the `16C550`
  reduces the damage without removing it. `serial.md` §13 item 11 leaves the
  choice to the owner and it is still not made.
- **The `/IRQ` cost is unmeasurable until the dispatch cost is measured.**
  `ps2.md` §14 item 3 is cited by four documents as the highest-value
  measurement in the machine, and this review agrees: it decides serial's
  ceiling, PS/2's FIFO, `machine.md` §4.1's order and how much of the net card
  is usable.

---

## 6. Ethernet

Also specification-only — the two `ATF1508AS` are `~/code/applenet`'s and are
not in this repository, so **nothing about the framers, the CRC or the clock
recovery can be checked here**. What can be checked is the arithmetic that
decides the card, and it holds:

| Claim | Check |
|---|---|
| `TFM` at 3.01 cycles/byte, E = 2.0979 MHz | 1435 ns/byte → 696,977 B/s = **681 KiB/s** ✓ |
| 10BASE-T = 1221 KiB/s; host is 56 % | ✓ |
| Max frame + preamble = 1220.8 µs; +IFG = 1230 µs; drain = 2178 µs | ✓ |
| Ring fills at 3.54 × 10⁻⁴ banks/µs; 16 banks = **45.2 ms** | ✓ |
| Min frame 57.6 µs + 9.6 = 67.2 µs → **14,881 frames/s** | ✓ |
| 16 frames per dispatch at 400 cycles → **9,639 frames/s** | 91.9 + 190.7/16 = 103.8 µs ✓ |

⭐ **§3.3.1 is a genuine finding reported upstream** — `arch-v3.md`'s ping-pong
scheme keeps one pointer per device serving both framer and host, which cannot
work once the two are in different banks at different offsets. The repair here
(the host's offset comes from the bus, the framer keeps its own pointer) is
correct and is what the `A20 = 1` region buys.

⚠ **Three things this review cannot confirm and flags as such:**

1. **Tx/Rx of real frames.** The framers are not in this repository. The golden
   frame (`plan.md` Appendix B, FCS `0x322A8F3D`) is the right acceptance test
   and there is nothing here to run it against.
2. **The fit risk is the real one.** §0 puts U2 at 91 % and U1 at 89 % of an
   `ATF1508AS` **before** this machine's bus interface is added, and the video
   card is this review's demonstration of what happens when a card is specified
   past its parts.
3. ⚠ **The card cannot coalesce interrupts and cannot be given a threshold**,
   because that would be a fifth register in a four-byte window (§5.1). The
   `$FF` map now has **56 free bytes**; four more for this card is a change
   `machine.md` §3 can absorb, and §3.4's *"the honest statement is that a busy
   LAN can saturate this machine"* is a decision that was made when the window
   was full and has not been revisited since it stopped being.

---

## 7. Stale documentation, corrected in this pass

Per the convention in the root `README.md`, superseded text moves to the
component's `history.md` and the spec is rewritten in the present tense.

| # | Document | Was | Is |
|---|---|---|---|
| D-1 | `video/docs/features.md` §3.2 | "≈32.4 M spare accesses/s… **77×** more memory bandwidth" | `graphics.md` §14.2.3 replaced the four ×8 framebuffer parts with two ×16: **8.1 M/s and 15×** |
| D-2 | `video/docs/features.md` §3.1 | a three-row `WMODE` table, and the mask serialiser and length counter as a `74HC165` and a `'161` pair | four modes since §8.4's sprite mode; both parts were booked into the CPLDs by `graphics.md` §10.1.6 (**and see V-1**) |
| D-3 | `video/docs/graphics.md` §6.4.6, `features.md` §1.4 | cell row is "`VSCROLL[8:3]`" | `SA17..SA13` is five bits — **`VSCROLL[7:3]`**. The 32-row ring the same tables state is the giveaway |
| D-4 | `video/docs/graphics.md` §14 | the motherboard census is "**17 ICs**" | 18 since `ram.md` §6.3.1's refresh timebase |
| D-5 | `io/ps2/docs/ps2.md` §0 | "Moved from `$FF30` on 2026-09-09" | the card moved **to** `$FF30`, from `$FF50` |
| D-6 | `io/serial/docs/serial.md` §0 | "The card as specified is 3 ICs and 19,200 baud… The 6551 design is the specified one and the tiers are proposals" | §9.1 took the `TL16C550C` on 2026-09-09; the same table's own rows say so |
| D-7 | `io/serial/docs/serial.md` §2 | "This machine boots NitrOS-9 from floppy" | `machine.md` §7.2 — a 1 MB boot ROM with a ROM disk; there is no floppy controller in the machine |
| D-8 | `io/serial/docs/serial.md` §0, `docs/machine.md` §4.1 | "~1,030 interrupts/s at 115,200 with a 14-byte trigger" | **823/s** — 11,520 B/s ÷ 14 |

**Not corrected, because they are decisions rather than errors** —
`serial.md` §3 and §5 are written against the 6551 and are the *reasoning* that
produced the part change, which §4.5 and §9.2 both say explicitly. They are left
in place with their existing pointers.

---

## 8. What this review did not cover

- **`storage/`**, at the owner's instruction.
- **Analogue.** The video card's drive stage (`graphics.md` §9.1), the audio
  card's converter cascade and filters (`audio.md` §6, §7), and every timing
  margin in either. Simulation says nothing about any of them and the bench
  items in both documents stand unchanged.
- **`cpu/`.** `plan.md`'s emulator, its microcode budget and `TFM`'s
  interrupt/resume behaviour (`machine.md` §6) are untouched here.
- **NitrOS-9.** The divergence ledger `machine.md` §5 item 6 says nobody keeps
  is still not kept, and this review adds to it: `machine.md` §3's MMU register
  description and `ram.md` §4's Layout A are two different register sets and
  the port has to be written against one of them.

---

## 9. The tooling this review leaves behind

| | |
|---|---|
| `hardware/gal/verilog/emit.ts` | `Merged`/`Design` → Verilog, from the same term lists `cupl.ts` compiles for the fitter. One origin, three devices |
| `hardware/gal/verilog/gen.ts` | emits `vaddr.v`, `vctrl.v`, `rfa.v`, `audio.v`, `u9.v`, `u10.v` |
| `hardware/gal/verilog/video_card.v` | the video card wired: three parts, four interleaved framebuffer chips, the fetch latches and the `'153` mux |
| `hardware/gal/verilog/vshim.v` | ⚠ **the size of V-1, as one file.** Every signal in it is an input to a fitted part that nothing on the card produces |
| `hardware/gal/verilog/mainboard.v` | U3, U6, U9, U10, both map SRAMs, the `'157`, the `TASK` `'574`, the boot `'244`, both flash devices and the SIMM bank |
| six testbenches | `vsync`, `vaddr`, `vtile`, `vspan`, `audio`, `mainboard` |
| `npm run check:video` | generates and runs all six — **122 ok, 16 FAIL** as of this document |

⚠ **The failures are left failing on purpose.** Every one of them is a finding
above, and a testbench that is edited to pass is a finding that has been
deleted. `run.sh` exits 0 either way; read the output.


---

## 10. Addendum — disposition, 2026-09-09

**The findings above are frozen; this section is not part of them.** It records
what was done about each, the same day, and where the work landed. Every claim
here is checked by `npm run check` and `npm run check:video` from `hardware/`.

| # | Disposition |
|---|---|
| **M-1** | ⭐ **Fixed.** A map entry's two bytes get **two windows** — `$FF90`–`$FF9F` high, `$FFA0`–`$FFAF` low — out of 32 bytes that decoded nowhere and outside the geographic window, so no card loses a byte. U3's decode is the same size; **U9 gives back a pin**. `ram.md` §4.3, `machine.md` §3 |
| **M-2** | ⭐ **Fixed**, by the same equation as M-3 |
| **M-3** | ⭐ **Fixed.** ⚠ **And it is a finding this document did not have.** The first pass modelled the physical address bus as `map_drives # buf_drives`, and an OR cannot see a fight. U6's boot-buffer enable is now the literal complement of U9's chip enable — three terms where the old list was two — and `mainboard_tb` asserts **exactly one driver, always**. `machine.md` §2 |
| **V-1** | ⭐ **Fixed**, at **+1 IC**. `CTRL`'s `'273` and the `'165` really are absorbable and are on `vctrl`; the `'161` pair is not, because §7.4 loads it from the register file's read bus and that is eight pins neither CPLD has. It is `vlen`, a `GAL22V10`, 10 macrocells of 10, checked over all 256 lengths. The card is **28 ICs** |
| **V-2** | ⭐ **Fixed.** `WSTBV = VRAMSEL & /RW & E` on `vctrl`, one macrocell |
| **V-3** | ⭐ **Wiring fixed** — `WINC = RETIRE # LADV` on `vaddr`, `LGRANT` on `vctrl`, and the engine walks and terminates. ⚠ **The descriptor format is still undesigned** and is now `graphics.md` §19 item 32 |
| **V-4** | ⭐ **Phase qualification fixed** — `LINEAR`, `TILESEL` and `SPNREQ` carry the half-slot, and `RETIRE` carries `SPNTICK` so a span retires once per slot rather than four times. ⚠ **The two-live-groups problem is not**, and it is not a wiring defect: `graphics.md` §19 item 28 has the arithmetic and three costed options |
| **V-5** | ⭐ **Fixed.** The map byte is a two-stage pipeline — `MAP` fetches, `MAPQ` feeds the address mux, `CELLTICK` hands over at the cell boundary. Eight macrocells on `vaddr`; one register provably cannot do it |
| **V-6** | ⭐ **Fixed**, as §7.2's own "two deferrable file reads": `WROWADV` starts a two-dot walk, `rfa` points the file at `+$08`/`+$09`, and the counter loads through the path the CPU's write already uses. ⚠ Ten shadow registers on `vaddr` is what the fitter refuses |
| **V-7** | ⭐ **Fixed.** `HPOL` is a constant |
| **A-1** | ⚠ **Not fixed, and not a fix.** The audio sequencer is design work — §2.1's list is fifteen blocks — and it is `audio.md` §16 item 00 |
| **A-2** | ⭐ **Fixed.** `MERGE = CCLK & !SYNCR2 & !SYNCR1`, one literal, and `audio_tb` walks a host read across all sixteen slot phases |
| **D-1…D-8** | ⭐ Corrected in the same pass, with `history.md` entries |

### What the repairs cost, in one table

| | before | after |
|---|---|---|
| video card ICs | 27 | **28** — `vlen` |
| `vctrl` | 122 of 128 cells, 64 of 64 I/O, 4 of 4 dedicated | **104 of 128**, 64 of 64, 3 of 4 |
| `vaddr` | 109 of 128, 61 of 64 | **122 of 128**, 61 of 64 |
| `rfa` | 6 of 10 macrocells | **8 of 10** |
| U9 | 6 macrocells, 14 inputs | 6 macrocells, **13** — `LA3` left |
| U6 `BOOTOE` | 2 product terms | **3**, and it is one rule instead of a list |
| U3 | 6 outputs, 15 inputs | unchanged — `!MAPOE` stays 6 terms |
| audio CPLD | 79 of 128 | unchanged |
| **simulation** | **122 ok, 16 FAIL** | ⭐ **140 ok, 0 FAIL** |

⭐ **The room came from an encoding, not a rewrite.** `vaddr`'s address mux has
four sources and `vctrl` was exporting all four selects; they are mutually
exclusive, so two bits name them and `vaddr` decodes them back for nothing.
Two pins, and `vctrl` fell eighteen cells.

### Three things this pass learned that are worth keeping

1. **A check that holds an input constant cannot see a defect in it.**
   `jedec.check.ts`'s complementarity sweep held `LA5` and `LA4` at zero, which
   is the one code that never reaches the map SRAM's third select condition —
   so it passed while the boot sequence fought itself sixteen times. It sweeps
   all four bits now, and it asserts *both* directions: never two drivers, and
   never none.
2. **A model that ORs its drivers cannot see a bus fight.** M-3 is in this
   document only because `mainboard.v` was rewritten to count drivers instead.
3. **A sentinel in a shift register cannot tell itself from data.** Replacing
   `seqctl`'s three-bit counter with a ninth bit in the serialiser looked free
   and ended a `$B4` sprite after two bytes. `seqctl.jedec.ts` records the
   attempt beside the counter it did not replace.
