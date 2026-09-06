# `hardware/gal/` — the programmable logic, and how it is checked

**`video/docs/graphics.md` §18 step 2 is "fit the GALs", and §18 says
"do steps 1 and 2 before laying out anything."** Nothing in this repository had a
GAL equation in it before 2026-09-06 — `grep -rn equation` returned three hits and all
three were *exit criteria saying the equations must fit*. This directory is the start of
the fitting, taken in the order the machine needs it: the MMU first, because it is the
one that gates the motherboard.

| | |
|---|---|
| [`mmu.pld`](mmu.pld) | **U3, the MMU sequencer** — CUPL, the deliverable a fitter consumes |
| [`mmu.v`](mmu.v) | the same seven equations in Verilog |
| [`mmu_tb.sv`](mmu_tb.sv) | 16 claims against `mmu.v` under **Verilator** — `npm run check:sim` |
| [`mmu.check.ts`](mmu.check.ts) | the same seven equations again, 23 claims — `npm run check` |

Three statements of one logic is two too many, and it is deliberate for exactly as long
as the toolchain is absent — see **Toolchain** below. `mmu.check.ts` runs today.

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
three changes."

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
| GAL equations → JEDEC | `galette` (or WinCUPL for ATF-specific fitting) | ⚠ **not installed** — the one gap left |
| Digital verification | **Verilator** 5.020 | ✓ `npm run check:sim`, 16 claims, `-Wall` clean |
| Analogue — the video output stage (`design-review.md` §Vid-M4) and the audio ladder | **ngspice** | ✓ installed, **nothing written yet** |
| Equations, today | `bun`, already here | ✓ `npm run check`, 23 claims |
| A CPU to drive it | [`../vendor/mc6809`](../vendor/mc6809) — Greg Miller's cycle-accurate MC6809E, BSD | ✓ elaborates; **nothing drives it yet** |

`mmu.v` has now been through Verilator and passes 16 claims exhaustively over the address
space, `-Wall` clean. **Nothing here has been through a fitter**, so "it fits a 22V10" is
still arithmetic in this document and not a fitter's report — and that is the one thing
neither simulator can answer.

The lint was not free of information. `-Wall` objected that `la[3:0]` was unused, which is
**true and is the design**: this GAL has no `LA3..LA0` pins, the entry index goes to the
`'157`, and that is exactly why `$FFB0` is aliased across sixteen addresses. `mmu.v`'s port
is `[15:4]` now, so the model states it rather than tolerating it.

---

## Open items

1. **Nothing has been fitted.** The pin budget is arithmetic, not a fitter's report.
   Product terms are all small (the widest is an 8-input AND) and the 22V10's leanest
   macrocell has 8, so it should fit — *should*.
2. **U6 has not been written.** It gains `/IOSEL` from this work, and it still owns the
   ÷12 / ÷8 `E`/`Q` divider, which is a state machine and the harder of the two.
3. **The other cards' GALs are untouched** — nine on video, five on audio's sequencer,
   plus decode GALs on serial, storage and PS/2.
