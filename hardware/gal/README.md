# `hardware/gal/` — the programmable logic, and how it is checked

**`video/docs/graphics.md` §18 step 2 is "fit the GALs", and §18 says
"do steps 1 and 2 before laying out anything."** Nothing in this repository had a
GAL equation in it before 2026-09-06 — `grep -rn equation` returned three hits and all
three were *exit criteria saying the equations must fit*. This directory is the start of
the fitting, taken in the order the machine needs it: the MMU first, because it is the
one that gates the motherboard.

## What here is a deliverable, and what is derivation

**Two GALs are live and get burned into silicon:** the motherboard's `U3` (the MMU
sequencer) and `U6` (the E/Q divider). `mmu.jed` and `clkdec.jed` are the files a
programmer takes. The audio card's five and the decode GALs on serial, storage and
PS/2 are still unwritten and will join them.

**The video card's ten are superseded** — `graphics.md` §10.1.6 makes that card two
`ATF1508AS`. Their `.jed` and `.doc` files carry a `*** SUPERSEDED - DO NOT PROGRAM
***` banner, stamped by the writer rather than edited in, so it survives regeneration.
They are kept because the fits *are* the derivation: the sync section needing three
parts, §19 item 12's wrap-in-row, item 8's 17-of-20, and every macrocell and pin
figure the CPLD's own budget is built on came out of them. Deleting the fits deletes
the argument.

| | Live | Superseded |
|---|---|---|
| designs | `mmu`, `clkdec` | `hgen` `vgen` `vdec` `hadr` `vadr` `arb` `wcol` `wrow` `seqph` `seqctl` |
| checked against Atmel's CUPL | **both** | not required |

**The rule, and it is enforced:** a GAL does not ship without a CUPL reference.
`jedec/cupl.check.ts` carries a registry of every design and **fails the build if a
live one has no reference in `jedec/reference/`**. Generate one with
[`prjbureau/cupl-reference.sh`](prjbureau/cupl-reference.sh). This is not caution for
its own sake — on 2026-09-07 two errors survived 178 passing checks because the
assembler and the fuse-map simulator share a device description and agree with each
other whatever it says. Only a second implementation broke the tie.

`check:cupl` also prints the conventions still resting on one source, so a future
design that needs one is flagged rather than trusted. Today that is the 64-bit user
signature's bit order: our `.pld` files carry no UES directive, so CUPL wrote zeros
there and never exercised it. It is read-back data and nothing depends on it.

---

| | |
|---|---|
| [`mmu.pld`](mmu.pld) | **U3, the MMU sequencer** — CUPL, the deliverable a fitter consumes |
| [`mmu.v`](mmu.v) | the same seven equations in Verilog |
| [`mmu_tb.sv`](mmu_tb.sv) | 16 claims against `mmu.v` under **Verilator** — `npm run check:sim` |
| [`mmu.model.ts`](mmu.model.ts) | the same seven equations as arithmetic |
| [`mmu.check.ts`](mmu.check.ts) | 23 claims against that model — `npm run check` |
| [`clkdec.pld`](clkdec.pld) | **U6** — the E/Q divider, `/IOSEL`, and the system RAM's control lines |
| [`clkdec.v`](clkdec.v) + [`clkdec_tb.sv`](clkdec_tb.sv) | the same, and 15 claims under Verilator |
| [`clkdec.model.ts`](clkdec.model.ts) | U6's behaviour, *not* as a sum of products — the reference the expansion is checked against |
| [`mmu.jedec.ts`](mmu.jedec.ts), [`clkdec.jedec.ts`](clkdec.jedec.ts) | the terms, placed in macrocells |
| [`jedec/`](jedec/) | **the fitter** — assembler, fuse-map simulator, and the device description both depend on |
| [`jedec.check.ts`](jedec.check.ts) | assembles both parts and checks **the fuses** against the models — `npm run check:jedec` |
| `mmu.jed`, `clkdec.jed` + `.doc` | the output: what a programmer burns, and the fitter's report |

**The video card's sync section**, which is where the fitter earned its keep —
`graphics.md` §19 item 8 said the sync pair did not fit and left the choice of escape
to fit time:

| | |
|---|---|
| [`sync.timing.ts`](sync.timing.ts) | the two VGA timings, with the counter-origin choice that makes `VSYNC` one shared product term — and an arithmetic self-check that caught `graphics.md`'s 60.0 Hz |
| [`sync.jedec.ts`](sync.jedec.ts) | **`hgen`, `vgen`, `vdec`** — the trio, and why it is a trio |
| [`sync.model.ts`](sync.model.ts) | the raster as arithmetic: counters are numbers, windows are comparisons |
| [`sync.check.ts`](sync.check.ts) | a whole frame in each family, off the fuses — `npm run check:sync` |
| `hgen.jed`, `vgen.jed`, `vdec.jed` + `.doc` | 27 macrocells across three parts |

**The video card's scan-address pair**, which came out the other way — `graphics.md`
§19 item 8 said 20 of 20 with zero margin, and it is 17:

| | |
|---|---|
| [`scan.jedec.ts`](scan.jedec.ts) | **`hadr`, `vadr`** — the column and row counters, and why there is no carry between them |
| [`scan.model.ts`](scan.model.ts) | the 1024 × 512 torus as arithmetic |
| [`scan.check.ts`](scan.check.ts) | every address of a 400-line frame at three scroll positions — `npm run check:scan` |
| `hadr.jed`, `vadr.jed` + `.doc` | 17 macrocells of 20, three spare |

**The arbiter and the `WPTR` pair** — `graphics.md` §19 items 20 and 12:

| | |
|---|---|
| [`access.jedec.ts`](access.jedec.ts) | **`arb`, `wcol`, `wrow`** — the spare-access grant logic and the 19-bit pointer |
| [`access.model.ts`](access.model.ts) | §5.2.1's grant rule verbatim, and the pointer as arithmetic |
| [`access.check.ts`](access.check.ts) | all 128 arbiter inputs, and the wrap that decides item 12 — `npm run check:access` |
| [`jedec/place.ts`](jedec/place.ts) | pairs equations to macrocells by term count, so pin order is not hand-arithmetic |

**The sequencer's timing spine** — the one part of `graphics.md` §14's sequencer pair
that the document specifies rather than lists:

| | |
|---|---|
| [`seqph.jedec.ts`](seqph.jedec.ts) | **`seqph`** — dot phase, slot tick, §5.2.2's sub-slot split, four per-chip fetch-latch clocks, pixel mux select |
| [`seqph.check.ts`](seqph.check.ts) | the phase, that the slot tick does **not** move with `HSCROLL`, and the arithmetic that shows a common fetch-latch clock cannot render a scrolled line — `npm run check:seqph` |
| [`seqctl.jedec.ts`](seqctl.jedec.ts) | **`seqctl`** — the span writer, respecified for 8 × 8 cells (`graphics.md` §7.4) |
| [`seqctl.model.ts`](seqctl.model.ts) | its state machine: one handshake, three terminations |
| [`seqctl.check.ts`](seqctl.check.ts) | all 16 states × 128 inputs, and the eight-byte glyph row — `npm run check:seqctl` |
| [`tile.model.ts`](tile.model.ts) | §6.4's three address concatenations — bitmap, 8bpp tile, 1bpp character |
| [`tile.check.ts`](tile.check.ts) | the no-adder property, asserted as OR = ADD over all 524,288 field combinations per variant — `npm run check:tile` |

Several statements of one logic is several too many, and the count went *down* on
2026-09-06 rather than up: `mmu.check.ts` no longer carries its own copy of the
equations, and `mmu.jedec.ts` is not a fourth statement but the placement of the terms
`mmu.pld` already holds. What checks what:

    mmu.pld ─── the deliverable, read by CUPL if anyone ever runs one
    mmu.v ───── Verilator ─── mmu_tb.sv, 16 claims
    mmu.model.ts ─── mmu.check.ts, 23 claims
         └──────────── jedec.check.ts ─── mmu.jed, 524,288 evaluations of the fuses

The `.jed` is the only one of these that is a physical claim about a chip, and it is now
the most heavily checked.

---

## The register map — `machine.md` §5 item 3, proposed

That item has been open since the project began and is listed as *"the deliverable that
gates the motherboard's write-decode GAL."* It cannot stay open and have equations, so
here is the map the equations implement. It was not a free choice in most of its
particulars — the `'157` wiring already in `mainboard.circuit.tsx` constrains it almost
completely.

| Window | Size | What | Decoded by |
|---|---|---|---|
| `$FFA0`–`$FFAF` | 16 B | **16 block registers.** Entry index = `A3..A0`. Bits 6–0 = physical `A19..A13`; bit 7 spare and stored | U3, motherboard |
| `$FFB0`–`$FFBF` | 16 B | **MMU control**, aliased 16× — bit 0 = `TASK`. Canonical address `$FFB0` | U3, motherboard |

> **Signed off 2026-09-06**, and `mainboard/mainboard.circuit.tsx` now implements it.
> `docs/machine.md` §5 item 3 is closed against this section.

**`$FFA0`–`$FFA7` is task 0, blocks 0–7; `$FFA8`–`$FFAF` is task 1.** That is forced, not
chosen: the `'157` mux puts `TASK` on `MAPA3` and `LA15..LA13` on `MAPA2..0` in translate
mode, and `LA3..LA0` on the same four lines during a write. So the write index *is*
`{TASK, block}` with no permutation, and `$FFA0+n` is task `n>>3`, block `n&7`. The board
was drawn this way before anyone wrote it down; `mmu.check.ts` now asserts it.

**The control register is aliased across 16 addresses on purpose.** Decoding `$FFB0`
exactly would need `LA3..LA0` as four more GAL inputs, and the budget below has one pin
spare. Aliasing costs nothing and is ordinary for the period.

**Sixteen 7-bit block registers is the whole 2 KB SRAM's useful content** — 16 of 2048
locations, as §6.3.1 says.

---

## The pin budget, and why `/IOSEL` moved

A GAL22V10 in DIP-24 has **12 dedicated inputs** (pin 1, pins 2–11, pin 13) and **10 I/O
macrocells**. An unused macrocell's pin can be an input, so *available inputs = 12 + (10 −
outputs)*.

U3 needs 15 inputs: `LA15..LA8` for the `$FF00`–`$FFFF` page decode (8), `LA7..LA4` for
the `$FFA0`–`$FFBF` window and its split (4), and `E`, `Q`, `R/W` (3).

| Outputs | Available inputs | Needed | |
|---|---|---|---|
| 7 — with `/IOSEL` and `ISO_DIR` on the part | 15 | 16 | ✗ **over by one** |
| 7 — `ISO_DIR` off the part, `/IOSEL` on it | 15 | 15 | ✗ zero spare, and see below |
| **6 — both off the part** | **16** | **15** | ✓ **one pin spare** |

Two things came off, and both are improvements rather than concessions:

- **`ISO_DIR` is `R/W`.** The `'245`'s A side is the SRAM, its B side is `D0–D7`; a read
  wants A→B (`DIR` = 1) and a write B→A (`DIR` = 0). That is `R/W` exactly. It was a
  macrocell in the board file and it is a **wire**.
- **`/IOSEL` moves to U6.** It is `/IOPAGE · A7 · /A6` — a machine-level backplane signal,
  not MMU sequencing, and U6 (the E/Q divider) has most of a 22V10 unused. `/IOPAGE`
  stays on U3 because putting it on U6 would put a second GAL delay in series ahead of
  `MAP_OE`, and the break-before-make margin is measured from that edge.

**So it fits, with one pin spare — and it did not fit as drawn.** That is `graphics.md`
§18 step 2's exit criterion answered for this GAL, and answered "yes, but only after
three changes." Four, as it turned out: `mmu.pld` then spent the spare pin by driving it,
which is §6 below.

> **Confirmed at the fuse level 2026-09-06.** `mmu.doc`, generated by
> [`jedec.check.ts`](jedec.check.ts), reports this table's chosen row back as
> *"6 outputs, 4 macrocells not driven. Inputs: 15 used of 16 available (12 dedicated,
> 4 free macrocells) — 1 spare."*

---

## The map-write cycle, in real nanoseconds

`E` = 2.0979 MHz, period **476.7 ns**. `Q` leads `E` by 90°, so from one `E`-fall the
cycle is `Q`↑ at 119.2 ns, `E`↑ at 238.3, `Q`↓ at 357.5, `E`↓ at 476.7. Everything below
is measured from that `E`-fall. Timing figures are from
[`../../reference/datasheets/`](../../reference/datasheets/) and from `cpu/docs/plan.md`
§3.3's extraction of the HD63B09E column.

| Phase | Who moves | When | Against |
|---|---|---|---|
| Mux to `A3..A0` | address decode alone | ~110 ns (`t_AD`) + GAL | `tAW` = 12 ns → **367 ns of address set-up** |
| Map SRAM `/OE` away | `/IOPAGE` asserts | ~120 ns | `tHZOE` = **8 ns** to high-Z |
| `'245` on | `E`↑ | 238 ns + GAL + `t_en` ≈ **294 ns** | **≈ 174 ns after the SRAM let go** |
| `/WE` asserted | `Q`↓ | 357.5 ns | buffer driving for 63 ns already |
| `/WE` released | `E`↓ | 476.7 ns | `tPWE` = 12 ns → **119 ns pulse** |
| `'245` off | `E`↓ + `t_dis` | +25…50 ns | `tHD` = **0 ns** — the buffer outlives the strobe |
| Map SRAM `/OE` back | next address change | ~587 ns | buffer off ~60 ns earlier |

**Write data is valid at 229.2 ns** — `t_DDW` ≤ 110 ns *from `Q`-rise*, not from `E`. So
at the latching edge (`/WE`↑, 476.7 ns) it has been valid for **247 ns** against the
CY7C128A-15's `tSD` of 10 ns.

**The break-before-make margin is ~174 ns and it is not delicate.** An earlier draft
enabled the `'245` at `Q`↑ instead of `E`↑; that gives ~9 ns of GAL-skew margin plus the
device asymmetry (`tHZOE` 8 ns off versus `t_en` 23 ns typ on), which *works* and would
have been the kind of number this project ends up re-deriving later. `E`↑ costs nothing
and removes the question.

> ⚠ `t_en` for the `SN74HC245` at 4.5 V reads **23 typ / 46 / 68 / 58 ns** across the
> datasheet's four columns; the 58 ns figure is taken as the −40…85 °C maximum. If that
> column reading is wrong the margin moves by 10 ns and nothing else changes.

---

## What writing the equations found

### 1. `MMU_EN` cannot do anything, and is not needed

U3 took `MMU_EN` as an input and the `'574` held it. **There is no bypass path on the
board** — the map SRAM's outputs *are* physical `A13–A19`, with nothing in between — so
"MMU disabled" could only mean floating the address bus. It is not a function this
hardware can perform.

It is also unnecessary, because of `machine.md` §7.2: the shadow ROM serves `$E000`–`$FFFF`
**from inside the CPU module without a bus cycle**, so boot code runs with no memory access
at all and can write all 16 entries through `$FFA0`–`$FFAF` before it ever needs RAM. The
identity map is a firmware loop, not a hardware state.

**Dropped.** It is one input and one macrocell back, and the `'574` falls to one live bit.

### 2. The `'157` select was tied to `MAP_WE`, giving the SRAM no address set-up

`mainboard.circuit.tsx` had `SEL: "net.MAP_WE"`. §6.3.1's phase table puts "mux switches"
in the *setup* row and "`/WE` asserted" two rows later — if they are the same signal, the
address changes at the instant the strobe asserts. `MUX_SEL` is now its own output,
asserted on address decode, which buys 367 ns against a 12 ns requirement.

### 3. `SHADOW_DIS` is latched on the motherboard and reaches nothing

`U2` `Q3` drives `net.SHADOW_DIS` and **no other pin in the design connects to it.** It
cannot ever work: the shadow ROM is inside the CPU module (§7.2), the module's connection
to the motherboard is a 6809E 40-pin socket, and every one of those 40 pins is defined.
There is no wire for this bit and there is nowhere to put one.

**It belongs in the CPU module**, which sees every `$FFBx` write on the bus and can latch
its own copy at no cost. Not fixed here — it is a `machine.md` §7.2 correction, not a GAL
one — but it is why the control register above allocates only `TASK`.

### 4. `$FFA0`–`$FFAF` cannot hold both the block registers and the vector RAM

`machine.md` §7.2 says the 16-byte vector RAM is *"writable through the `$FFA0`–`$FFAF`
window."* That window is 16 bytes and the block registers need all 16 of them. The two
claims are incompatible and one has to move; the vector RAM is CPU-module-internal, so
moving it costs the motherboard nothing. **`$FF90`–`$FF9F` is free** — nothing in this
machine decodes `$FF80`–`$FF9F` (the `$FF9x` hits in the documents are all GIME
comparisons) and §7.2 already keeps `$FF00`–`$FFBF` decoding normally during boot.

### 5. `MAPOE` is nine product terms, and the pin placement is load-bearing

Found by assembling the fuse map, which is the first thing in this project that had to
count terms rather than describe them.

    MAPOE = !iopage # blksel & RW & E

`!iopage` is the complement of an eight-way AND, and in sum-of-products form that is
**eight product terms**, not one. `MAPOE` needs nine. Every other equation on U3 needs
one. The §"Open items" claim that "the widest is an 8-input AND" was counting literals
*inside* a term; a macrocell's limit is the number of terms.

It fits where it sits — pin 21's macrocell holds 12 — but it would **not** fit on pin 14
or pin 23, which hold 8. So U3's pin assignment was already load-bearing and nothing said
so. `clkdec.pld` knew this about itself and wrote the counts next to each pin; `mmu.pld`
did not.

There is also a cheaper form, and it is free. The pin is declared active low, so the
macrocell can form the complement directly and let the polarity bit do nothing:

    !MAPOE = iopage & (!LA7 # LA6 # !LA5 # LA4 # !RW # !E)

**Six terms instead of nine**, same pin, same behaviour — `jedec.check.ts` compares both
against `mmu.model.ts` over the whole address space. A fitter would have chosen this
silently and never mentioned it. It is the clearest example of what writing the fuses
buys: the choice becomes a line in a file with a reason attached.

### 6. `SPARE = 'b'0` spent the spare pin

The budget table above chooses the row *"6 outputs → 16 available inputs, 15 needed, one
pin spare."* But `mmu.pld` declared `PIN 23 = SPARE` and drove it to zero, and a driven
pin is a **seventh output** — which is the row above it, 15 available against 15 needed,
nothing left. The table and the file disagreed and the file was losing.

`PIN 23` is now undeclared. The macrocell holds it at high-Z, and it is a sixteenth input
if the board ever wants one. `jedec.check.ts` asserts it: *pin 23 is left at high-Z, so
it is a spare INPUT and not a driven low.*

Related, and checked for the same reason: **a macrocell pin used as an input has to be
combinational and must never drive.** A registered macrocell feeds the array from its
register and its pin is not an array input at all. U3 puts `E`, `Q` and `R/W` on pins
14–16, so this is the kind of thing that would work in every simulation and fail on the
bench.

---

## U6 — the divider, and the one subtle thing in it

`clkdec.pld` carries three jobs on one part: the `E`/`Q` divider (`machine.md` §1),
`/IOSEL` (which U3 had no room for), and the system RAM's `/CE`, `/OE` and `/WE` (which
nothing drove at all until 2026-09-06 — `hardware/README.md` open item 4).

**The Q tap is divisor-dependent, and that is the exit criterion `graphics.md` §18 step 0
names.** `machine.md` §1 says *"Q = same divider, 3 dots early."* Three dots is a quarter
cycle at ÷12 and **135°** at ÷8. `Q` has to lead `E` by 90° in both, so the tap is **3
counts at ÷12 and 2 at ÷8** — and `clkdec_tb.sv` asserts the ÷8 case as
*"Q leads E by 2 and NOT by 3"*, because the sentence in `machine.md` reads as though it
were 3 in both.

**`E` and `Q` are registered and decoded from the *next* count**, not combinationally from
the current one. A combinational decode of a 4-bit counter glitches wherever several bits
change together, and this output is the machine's clock.

Three tricks keep it inside a 22V10, and the product terms are counted rather than hoped:

- **The terminal-count decodes are partial.** 11 is `1011` and 7 is `0111`, and neither
  needs its zero bits tested because the counter never reaches 15. One product term each
  instead of four.
- **`C0` and `C1` need no terminal-count term at all.** Both terminal counts have
  `C1 = C0 = 1`, so a plain toggle and a plain XOR already land on zero.
- **Pin placement follows the equations.** A 22V10's macrocells hold 8, 10, 12, 14, 16,
  16, 14, 12, 10, 8 terms across pins 14–23. `E` (7 terms) and `Q` (5) sit on the two
  16-term macrocells; nothing else exceeds 4.

The four counter bits come out on pins nothing connects to — **four free test points** on
the signal hardest to characterise from outside. A 22V10 has no buried nodes, so they were
going to be driven anyway.

### `/OE` is qualified by `R/W`, and that is not decoration

The AS6C4008's truth table permits tying `/OE` low and letting `/CE` and `/WE` do
everything. **This machine's bus timing does not.** With `/OE` grounded the SRAM drives
`D0–D7` from `/CE` time (~140 ns) until `/WE` asserts at E-rise (238 ns), while the CPU is
also driving write data from ~229 ns — about **90 ns of contention on every write**. One
macrocell removes it.

`RAM_WE` carries the decode as well as `E` and `R/W`. That term is redundant — a write
needs `CE#` and `WE#` both low — but it costs nothing and keeps a glitch on `/CE` from
becoming a write.

### The decode is downstream of the MMU

`A19` is a **physical** address line, so it does not exist until the map SRAM has
propagated: `t_AD` 110 + map 15 + GAL 10 + RAM access 55 = **190 ns**, against ~437 ns
before the CPU samples. Comfortable — but it means system RAM can never be faster than the
translation, which is worth knowing before anyone proposes a faster part.


---

## Toolchain

**Decided 2026-09-06: Verilator for digital verification, ngspice for analogue. No visual
simulator.** Logisim Evolution was considered and dropped: its delay model is unit-delay,
and every defect this machine has produced has been a timing or arithmetic defect, so it
would pass designs that fail on silicon. It also has no path to a netlist, which would
make a `.circ` file a second description of the machine with no check over it — the
failure mode `/IOSEL` and `machine.md` §7.1 already demonstrated twice.

| Job | Tool | Status |
|---|---|---|
| GAL equations → JEDEC | [`jedec/`](jedec/), written here | ✓ `npm run check:jedec` and `check:sync` — five parts assemble, fit and are checked at the fuse level |
| **CPLD equations → JEDEC** | Microchip `fit1508.exe` under Wine | ⚠ **not attempted, and not worth rewriting** — see below |
| **CPLD JEDEC → a programmed part, on Linux** | [prjbureau](https://github.com/whitequark/prjbureau) `fuseconv` → SVF → OpenOCD | ⚠ **the fuse map CSVs exist; prjbureau's own status table says "Untested" for both ATF1504 and ATF1508** |
| **CPLD JEDEC → executed against the models** | prjbureau `database.json` | ✗ **"Partial" for the 1508, and absent from the checked-in database — 1502 and 1504 only** |
| Counter and window equations | [`jedec/counter.ts`](jedec/counter.ts), [`jedec/range.ts`](jedec/range.ts) | ✓ generated, not hand-expanded; every range decode verifies itself exhaustively before it is returned |
| An independent JEDEC, to falsify `jedec/gal22v10.ts` | `galette`, or WinCUPL under Wine | ⚠ **not run** — wanted once, not as a dependency ([`jedec/README.md`](jedec/README.md)) |
| Digital verification | **Verilator** 5.020 | ✓ `npm run check:sim`, 16 claims, `-Wall` clean |
| Analogue — the video output stage (`design-review.md` §Vid-M4) and the audio ladder | **ngspice** | ✓ installed, **nothing written yet** |
| Equations | `bun`, already here | ✓ `npm run check`, 23 claims |
| A CPU to drive it | [`../vendor/mc6809`](../vendor/mc6809) — Greg Miller's cycle-accurate MC6809E, BSD | ✓ elaborates; **nothing drives it yet** |

Two GALs are written of roughly twenty in the machine. `npm run check:sim` runs both
testbenches; `npm run check` runs the equation check.

`mmu.v` has now been through Verilator and passes 16 claims exhaustively over the address
space, `-Wall` clean. **Both parts have now been fitted** — not by a compiler, but by
assembling the fuse map directly and then executing it: `jedec.check.ts` writes
`mmu.jed` and `clkdec.jed`, reads them back, reconstructs the AND array out of the bits
and compares it with `mmu.model.ts` and `clkdec.model.ts`. "It fits a 22V10" is no longer
arithmetic in this document; it is a placement that either succeeded or the assembler
refused. See [`jedec/README.md`](jedec/README.md) for what that is worth and, more to the
point, what it is not worth.

The lint was not free of information. `-Wall` objected that `la[3:0]` was unused, which is
**true and is the design**: this GAL has no `LA3..LA0` pins, the entry index goes to the
`'157`, and that is exactly why `$FFB0` is aliased across sixteen addresses. `mmu.v`'s port
is `[15:4]` now, so the model states it rather than tolerating it.

---

## What the CPLD fitter knows that we do not — measured, 2026-09-07

Having the ATF1508 fitter beside our own raised an obvious question: it makes a
design smaller three ways we do not, so how many GALs is that costing us?

It costs none, and the measurement is worth keeping because the answer is not
the intuitive one.

**The three techniques, and what each is worth here.**

| | What it does | Measured on this machine |
|---|---|---|
| Espresso | true two-level minimisation | **1.9%** — 11 product terms across every GAL, none on a binding equation |
| Polarity selection | store `!f` and let the output XOR invert; the 22V10's S1 bit is free | **5.5%** — 14 equations, one of them large |
| Foldback | split a wide equation across a spare macrocell | **negative** — it buys terms by spending macrocells |

`gal/minimise.probe.ts` runs the first past CUPL's own minimiser;
`gal/polarity.probe.ts` runs the second past `jedec/twolevel.ts`, a
Quine-McCluskey minimiser written for the purpose.

**Why none of it reduces the part count.** Across the machine's eighteen
GAL22V10s:

```
macrocells    159 of 180   88%
product terms 645 of 1746  37%
```

Eight of seventeen fitted designs sit at exactly 10 of 10 macrocells. Six of
146 equations have no product-term slack. **Every GAL overflow in this project
was macrocells or pins and not one was term width** — `aintreq` is 13
equations for 10 macrocells, `aintreq-split` is 17 inputs for 14 pins, the sync
section needed a third part for outputs. All three of the fitter's techniques
work on the 37%, and foldback actively trades the resource we have for the one
we do not.

**Two things CUPL turned out not to do**, both worth knowing before reaching
for it as an authority on cost:

- Its minimiser saved 1.9% and nothing that mattered.
- **It does not choose output polarity by cost.** Given `NARROW = !(A#B#C#D)`
  it stores `A#B#C#D` — four rows — and sets the polarity fuse, where
  `!A&!B&!C&!D` is one row and needs no fuse. Confirmed in its own fuse plot.
  This is why `jedec/twolevel.ts` exists.

### The one real find: `SPNGRANT` was sixteen terms and needs six

The arbiter's grant line was written as "the four per-chip grants, ORed", which
enumerates the chip four ways and then expands `!GRANT_CPU` four ways inside
each. Sixteen products, in a 16-term macrocell, recorded here and in
`access.check.ts` as *exactly full* — which read as a tight fit and was really a
bad expansion.

The chip enumeration cancels. The span writer is refused exactly when the CPU
wants **the same** chip, so the condition is a comparison between `SPNA` and
`CPUA`, not a decode of either: one term per address bit per direction, plus the
two ways the CPU is not asking at all. Six terms. The complement is five, which
the S1 bit would give for nothing; it is not taken because `SPNGRANT` is read by
name on two other parts.

`access.check.ts` compares the new form against the four grants ORed over every
input combination, so the rewrite is verified rather than argued.

**It changed nothing on the CPLD.** `vctrl` refits at exactly 100 logic cells
and 331 product terms either way — the ATF1508 fitter had been minimising it
internally all along. The waste was only ever in the GAL path and in what the
source claimed about itself.

### The claim in `place.ts` that had to be weakened

The placer used to refuse an over-wide equation with *"sorted pairing is
optimal, so this does not fit on this part at all."* Sorted pairing is optimal
over **assignments of a fixed set of equations**. It says nothing about whether
the equations are as small as they could be, and `SPNGRANT` is the counter-
example. The message now says which of the two it means.

## Open items

1. ~~**Nothing has been fitted.**~~ **CLOSED 2026-09-06** by [`jedec/`](jedec/). It
   closed with a correction: this item said *"product terms are all small (the widest is
   an 8-input AND)"*, which counts literals inside a term, and the macrocell's limit is
   **terms**. `MAPOE` is nine of them — see §5 below. The remaining doubt is not about
   fitting but about the device description the fitter uses, and it is item 3.
2. **No independent JEDEC has been produced.** The assembler and the fuse-map simulator
   share `jedec/gal22v10.ts`, so they cannot catch an error in it. Compiling one `.pld`
   with galette or CUPL and diffing the fuse array would retire this permanently; it
   needs the tool once, not as a dependency.
3. **The other cards' GALs are mostly untouched.** The video card's sync trio is done
   (`sync.check.ts`); its scan-address pair, sequencer pair and arbiter are not, nor is
   audio's sequencer, nor the decode GALs on serial, storage and PS/2. The assembler
   takes equations as they are written; what it does not do is minimise, and the
   video sequencers are where that may start to matter.

4. ~~**The scan-address pair will not fit either.**~~ **CLOSED** — it is 17 of 20 with
   three spare. The rule from the sync fit still holds but does not bind there:
   nothing decodes the scan address, it goes straight to the framebuffer's address
   pins. **The `WPTR` pair, the arbiter and the sequencer's timing spine are fitted
   too.** What remains is the sequencer's other half — and it does not fit in the one
   part left. `graphics.md` §19 item 23 carries the budget: 20 macrocells wanted
   against 10 left, on an enumeration of that document's own list of duties. It is a
   budget rather than a fit because the span writer's state machine is inherited from
   minimal256 and has never been written down. **That is now the blocking item for the
   card's GAL count**, and it is a specification job, not a fitting one.

### Why the GAL fitter does not become a CPLD fitter

The reason is not that the ATF1508AS is complicated. It is that **we wrote `jedec/`
from the ATF22V10C datasheet's fuse map, and the ATF1508AS datasheet does not have
one.** Both PDFs are in `reference/datasheets/`; grep decides it:

| | `ATF22V10C.pdf` | `ATF1508AS.pdf` |
|---|---|---|
| fuse counts | §10: "(5828 Fuses)", "(5892 Fuses)", "(5893 Fuses)" | **no hits** |
| a numbered array | §11: "Functional Logic Diagram", `INPUT LINES 0..43` | **no hits** |
| "fuse map" / "fuse number" anywhere | — | **no hits** |

The 1508 datasheet describes the architecture exactly and numbers nothing:

> *"Each of the 128 macrocells generates a buried feedback that goes to the global bus.
> Each input and I/O pin also feeds into the global bus. The switch matrix in each
> logic block then selects 40 individual signals from the global bus."*

**So there are two problems, and the GAL had only the second.**

1. **Which fuse is which.** The 22V10's datasheet answers it — that is what
   `gal22v10.ts`'s provenance note is citing. For the ATF1508AS it is published
   nowhere, which is exactly why [prjbureau](https://github.com/whitequark/prjbureau)
   exists and why its method is **fuzzing the vendor fitter** rather than reading a
   datasheet.
2. **Which logic goes where.** On a 22V10 this is placement alone: every product term
   reaches every input, so there is no routing and `jedec/place.ts` is thirty lines.
   On an ATF15xx each logic block sees **40 signals selected from a global bus of
   ~200**, and its **16 macrocells share that same 40** — so assignment and routing
   are coupled, and an equation's signal needs constrain every other equation in its
   block.

**The order is forced, and it settles the question.** A fitter emits fuses; you cannot
emit fuses you cannot name. So "write a 1508 fitter" and "extend prjbureau to the
1508" are not alternatives — **the second is step one of the first**, and it is the
step that is fuzzing rather than arithmetic.

Problem 2 is the interesting one and may be tractable by hand *for this design*
specifically, because it is already partitioned by function: the line counter's ten
macrocells reference about fourteen distinct signals, well inside a block's forty.
A general fitter would have to search; ours would only have to be checked. But that
is worth nothing until problem 1 is solved.

**But the assembler was never the valuable half.** What caught bugs here was
[`jedec/simulate.ts`](jedec/simulate.ts) — reading the fuse map back and executing it
against the models. That found the `WPTR` hold-gating defect, which is invisible in a
macrocell count, a product-term count and a pin budget, and it found the aliasing bug
in its own API. **That half is worth having for a CPLD too**, and it needs one thing:
a documented fuse map.

[prjbureau](https://github.com/whitequark/prjbureau) is that documentation, and its
coverage decides what is possible:

prjbureau's own status table, from `docs/intro.rst`:

| | Fuse database | Programming |
|---|---|---|
| ATF1502AS/ASV/ASL | **Complete** | **Complete** |
| ATF1504AS/ASV/ASL | Near-complete | Untested |
| **ATF1508AS/ASV/ASL** | **Partial** | **Untested** |

and the checked-in `database.json` carries 1502AS/BE and 1504AS/BE only — no 1508
entry at all. The stated reason is not architectural: *"peculiarities of the toolchain
result in practical difficulties producing complete fuse map documentation."*

So on Linux, for the part `graphics.md` §10.1.6 selects: **the design can be fitted
(Wine), programmed (prjbureau + OpenOCD, no Atmel Windows tooling), and verified at
the model level — but the fitted JEDEC cannot be executed.** On an ATF1504AS it could
be. That is a live input to the part choice and `graphics.md` §10.1.6 carries it.

**A placement rule, from three counters fitted.** A loadable counter bit *i* costs
*i* + 3 product terms and a plain enabled one *i* + 7, so a wide counter wants a
rising staircase of capacity while a 22V10 offers the palindrome 8, 10, 12, 14, 16,
16, 14, 12, 10, 8. **Past about six bits, bit order is not pin order** — only the
sorted pairing fits, and it interleaves the bits across the package. `vgen`, `vadr`
and (predictably) the `WPTR` pair all land on it. The assembler refuses the naive
order rather than letting it through, which is how `vadr`'s top bit was caught.
