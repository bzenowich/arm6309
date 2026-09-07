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

4. **The scan-address pair is the next one and it will not fit either.** The sync fit
   established the rule: a counter cannot be separated from the things that decode it,
   because the pins to carry it across a package boundary do not exist. The scan pair
   is 19 address bits plus a carry in 20 macrocells, with no decode anywhere and tile
   mode still to ask for a mode mux on every bit (`graphics.md` §19 item 15).
