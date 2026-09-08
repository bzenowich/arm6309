# arm6309 — A Cycle-Accurate HD6309E on STM32G431CB

**Primary goal:** a 40-pin drop-in module that replaces the MC68B09E in a **Tandy CoCo 3**
and boots **NitrOS-9 Level 2 in 6309 native mode**.

**Status:** planning — Phase 0 decisions locked; Phase 1 written, not yet measured
**Date:** 2026-09-04

> Superseded material is archived in [history.md](history.md); this document describes
> only the present design.

---

## 0. Decisions

| Decision | Choice | Consequence |
|---|---|---|
| **MCU** | **STM32G431CBU6** (UFQFPN48, 42 GPIO, 170 MHz) | Pin budget closes — just barely (§3.2). Full `PA0-15` + `PB0-15` ports, and `PC4`/`PC6`/`PC10`/`PC11` bonded out. |
| **Core clock** | **170 MHz, in spec** | Overclocking to 200 MHz evaluated and **rejected** (§3.4(4)): it moves no gate from fail to pass, and 344 MHz is the PLL VCO ceiling. |
| **Data sampling** | **External 74LVC574 latch, clocked by E-fall** | §3.6. Mandatory at 3 MHz (`t_DSR` = 20 ns is below the software floor); worthwhile at 1.79 MHz. ~$0.30, +1 package. |
| **Socket** | **HD6309E** — E and Q are **inputs** | Matches the CoCo 3. Clock-slaved; we never hold E, and there is no `/WAIT` path into this module. |
| **Primary target** | **CoCo 3 @ 0.895 **and** 1.79 MHz**, switchable at runtime | **Feasible with 5–10 core cycles of deadline margin and ~48 cycles/bus cycle for the emulator.** See §3.3. |
| **Optional rate probe** | **3 MHz** (HD63C09E rated max) on boards you design | Reachable with the §3.6 latch; throughput-limited, not deadline-limited. 5 MHz is not a target — no such speed grade exists (§3.3). On the homebrew machine the corresponding rate is **fast-E, 3.1469 MHz**, which is experimental and not guaranteed (§3.3(e)). |
| **Accuracy** | **L2 + mandatory `/HALT`/`BA`/`BS`** | `/HALT` is not optional on a CoCo — it is how the floppy transfers data (§2.2). |
| **Method** | Measure the ceiling first, back off as forced | Drives phase ordering in §7. |

**Success criterion:** *boots NitrOS-9 Level 2 (6309 native) from floppy on a real CoCo 3,
and a logic-analyzer capture matches a real HD63C09E in the same socket.*

---

## 1. Executive summary

**The CoCo 3 target is achievable. 3 MHz is achievable with one added $0.30 part
(§3.6). The 5 MHz probe is not, and that's fine.**

The CoCo 3's GIME clocks the CPU at **0.895 MHz**, switchable at runtime to **1.79 MHz**
via the SAM speed bits at `$FFD8`/`$FFD9` (`POKE 65497,0`). The stock part is an MC68B09E
rated 2 MHz.

At 1.79 MHz a bus cycle is **95 core cycles** at 170 MHz. The binding deadline is `t_AD`
= **110 ns = 18.7 core cycles** (§3.3 — *not* the quarter cycle, and not period-relative),
against an estimated **9–14 cycle** floor for the post-read path. That leaves **5–10
cycles of margin** on the deadline and ~48 cycles per bus cycle for the emulator.
A comfortable fit, not a heroic one.

**2 MHz — the HD63B09E's rated maximum — is comfortable at 170 MHz with no added parts:**
both gates pass and the emulator gets ~41 cycles per bus cycle.

**3 MHz is reachable too, still at 170 MHz — and not for the obvious reason.**
The HD63C09E numbers hold `t_AD` at 110 ns across both speed grades, so the
address-drive path — the thing variant 2 was hand-written for — keeps its full margin at
3 MHz. What halves is `t_DSR` (40 → 20 ns), which puts read-data sampling **below the
floor for any software polling loop on this part, at any clock it can reach**. One
74LVC574 clocked by E's falling edge moves that sample into hardware and dissolves the
constraint (§3.6): ~$0.30, one extra package, ~34 core cycles per bus cycle left for the
emulator.

**The core clock is committed at 170 MHz, in spec.** Overclocking to 200 MHz was
evaluated in detail and rejected (§3.4(4)): it moves no gate from fail to pass at any
target rate, and the PLL VCO ceiling of 344 MHz means any SYSCLK above 172 MHz
overclocks the analog PLL as well as the core.

**5 MHz is not a target.** No 6309E speed grade above the HD63C09E exists, so 3 MHz is
the fastest rate any datasheet supports (§3.3).

Prior art supports the approach: **MCL6809**, a Teensy-based cycle-exact 6809E drop-in,
has been demonstrated on vintage Tandy hardware, and a real **HD63C09E is already a
known-good drop-in upgrade** for CoCo 1/2/3 running NitrOS-9. That last fact is
enormously useful — it means a perfect A/B reference exists for the exact socket.

---

## 2. CoCo 3 host requirements

These are load-bearing and several are not optional. **Verify each against the CoCo 3
service manual schematic before committing the PCB.**

### 2.1 Runtime clock switching

The GIME switches the CPU between 0.895 MHz and 1.79 MHz **while software is running**
(`$FFD8`/`$FFD9`, SAM R1). Consequences for the design:

- The bus loop must be **purely edge-driven**. No calibrated delays, no assumed E period,
  no "wait N cycles then sample". Every action keys off an observed E or Q transition.
- Worst-case timing must be met at **1.79 MHz** even though the machine boots at 0.895.
- There is no notification of the switch — it just happens between one cycle and the next.

### 2.2 `/HALT` is how the floppy works — mandatory

The CoCo disk controller (FD502) has no true DMA. `DRQ` from the FDC is gated onto the
6809E's `/HALT` pin:

1. CPU issues a read-sector command, then reads the FDC data register.
2. The FDC drops `DRQ` right after that read, which **halts the CPU**.
3. The FDC assembles the next byte and raises `DRQ`; the CPU **unhalts**, stores the byte,
   and reads the data register again — halting itself once more.
4. Repeat per byte. At end of sector, `INTRQ` fires a real **`/NMI`**.

Therefore:

- `/HALT` must be honored **at the end of the current instruction** (the real part finishes
  the instruction, then stops).
- `BA` and `BS` must both go **high** while halted.
- The address bus, data bus, and `R/W` must go **high-Z** while halted — this is why the
  buffers need an `OE` (§3.2).
- Halt/unhalt latency must be short and consistent; it happens **once per byte** of every
  sector transfer. NitrOS-9 boots from floppy, so this path is on the critical route to
  the success criterion.
- `/HALT` takes **precedence over interrupts**.

### 2.3 Interrupts

`/NMI` from the FDC `INTRQ`; `/IRQ` and `/FIRQ` from the GIME (60 Hz vertical, horizontal
sync, keyboard, serial). Standard, but sampling must occur at the architecturally correct
point in each instruction.

### 2.4 6309-specific, NitrOS-9-specific

- NitrOS-9 optionally uses 6309 opcodes and **native mode** (`MD` bit 0). Native mode is
  ~15–30% faster and is the whole point of the upgrade.
- The **illegal-instruction trap** (`$FFF0`) must be correct. Historically, when 6309
  opcodes were first added to NitrOS-9, illegal-opcode trapping *halted* CoCos when code
  was subtly wrong — meaning this trap is genuinely exercised and must behave exactly.
- Divide-by-zero trap also vectors through `$FFF0`.

### 2.5 Cycle accuracy actually matters here

CoCo 3 software does cycle-timed GIME video tricks. This is not a machine where
"close enough" timing passes. It is also why the CoCo 3 is a good validation target:
if raster-timed demos render correctly, the timing is right.

### 2.6 Signals the CoCo 3 does not use

Read directly off the *Color Computer 3 Service Manual* (Cat. No. 26-3334) NTSC
schematic, p.103, IC1 `68B09E`:

| Pin | Signal | CoCo 3 connection |
|---|---|---|
| 33 | `BUSY` | **NC** |
| 38 | `/LIC` | **NC** |
| 5 | `BS` | **NC** |
| 6 | `BA` | **NC** |
| 36 | `AVMA` | **NC** |
| 39 | `TSC` | **tied to GND** (explicit ground symbol; §5.1: "permanently grounded") |

All five outputs are labelled `NC` on the drawing. §5.1 independently lists the control
inputs the machine uses as exactly `RESET*`, `HALT*`, `NMI*`, `IRQ*`, `FIRQ*`.

Other connections at IC1, useful for the carrier design:

| Pin | Signal | Connection |
|---|---|---|
| 34 | `EIN` | `ECLK` from the GIME |
| 35 | `QIN` | `QCLK` from the GIME |
| 37 | `/RESET` | `RST` net via D12 (1N4148/1S953) |
| 40 | `/HALT` | 4.7 K pull-up to 5 V (R5) |
| 2, 3, 4 | `/NMI`, `/IRQ`, `/FIRQ` | pulled up alongside `/HALT` |
| 32 | `R/W` | **47 K pull-up to 5 V** |
| 8–23 | `A0..A15` | **4.7 K pull-ups to 5 V** — resistor networks MP1/MP2, 4.7 K ×16 |
| 24–31 | `D7..D0` | B-side of IC3, a **74LS245** transceiver |
| 7 | `VCC` | with C1 0.1 µF + C2 10 µF decoupling |

**Consequences:** six signals drop out of the pin budget, taking it from 39-of-39 to
**33-of-39 with 6 spare** (§3.2). The L3 work in §2 disappears for this target. `BUS_OE`
stays — see §2.2; it is not a 6309 pin but the buffer tri-state control, and it is what
makes the `/HALT` floppy path work.

Three further facts from the same source, all load-bearing:

- **The data bus already passes through a 74LS245 (IC3)** between the CPU socket and the
  rest of the machine. LS-family inputs need V_IH = 2.0 V, so 3.3 V drive is in spec —
  confirming the §3.5 analysis.
- **Every address line carries a 4.7 K pull-up to 5 V** (MP1/MP2), and `R/W` a 47 K
  pull-up. This matters twice over: the bus does not truly float when we tri-state it
  under `/HALT`, and our buffers must tolerate 5 V on their outputs while in high-Z.
  74LVC does (no clamp diode to V_CC); many families do not. See §3.5.
- **The GIME gates addresses to memory during active E only**: "this timing is modified
  by the ACVC chip so that the addresses are available to the memory only during the
  active E time. This presents no problem as long as the memory is sufficiently fast."

### 2.6.1 The Dragon 64 leaves the same six signals unused — second UFQFPN48 target

Read off `reference/schematics/Dragon64-schematic.tiff`, sheet 1 of 3, "C.P.U. 64K (PAL)", drawing
CD 4180S, IC38 `6809EP`:

| Pin | Signal | Dragon 64 connection |
|---|---|---|
| 5 | `BS` | **NC** — bare stub, no net label |
| 6 | `BA` | **NC** |
| 33 | `BUSY` | **NC** |
| 36 | `AVMA` | **NC** |
| 38 | `/LIC` | **NC** |
| 39 | `TSC` | **tied to 0V** |

**That is the same six-signal set as the CoCo 3, exactly.** The five outputs are drawn as
short unterminated stubs grouped on the left edge of the symbol; `TSC` runs to an explicit
ground symbol.

Everything else is wired as §3.2 budgets it:

| Pin | Signal | Connection |
|---|---|---|
| 34, 35 | `E`, `Q` | from IC39, a **`74LS783` SAM** — the CoCo 1/2 arrangement, not a GIME |
| 37 | `/RESET` | `RESET` net via the D19 `1N914` / D20 `1N3592` network |
| 2, 3, 4, 40 | `/NMI`, `/IRQ`, `/FIRQ`, `/HALT` | all four are labelled buses reaching the PIAs and the cartridge port |
| 32 | `R/W` | bus |
| 8–23 | `A0..A15` | bus |
| 24–31 | `D7..D0` | bus |

**Consequence: the Dragon 64 needs the same 33 pins as the CoCo 3, so one part covers
both targets with no change to the pin budget or the pinout** — the UFQFPN48 of §3.2.
`BUS_OE` still earns its pin — `/HALT` is a bus here too, reaching the cartridge port, so the DMA-release path
of §2.2 applies unchanged.

Three items to close before calling the Dragon 64 supported. None of them is pin count:

- **`t_AD` comes from the `74LS783`, not a GIME.** The 110 ns figure used throughout §3.3
  is a CoCo 3 number. The Dragon's address-setup requirement is set by the SAM's DRAM
  multiplexer at a nominal ~0.89 MHz with no CoCo 3-style 1.79 MHz mode, so the deadline
  should be *looser* — but take the number off the `74LS783` datasheet rather than
  assuming it.
- **Data-bus buffering not traced.** The CoCo 3 gives us IC3, a `74LS245`, between the
  socket and the machine (§2.6), which is what puts 3.3 V drive in spec. The Dragon sheet
  has a `74LS244` at IC25, but that is an address buffer; whether anything buffers the CPU
  data bus is unresolved. Until it is, assume **unbuffered** and re-run the §3.5 drive
  analysis against whatever the data bus actually loads.
- **Socketed or soldered** — the schematic cannot say. Same §2.7 caveat as the CoCo 3.

### 2.7 Mechanical

- 40-pin DIP footprint, socket-compatible.
- **Height clearance under the CoCo 3 RF shield is a real constraint.** Measure before
  layout; a tall module will not fit with the shield installed.
- The CPU may be **soldered** rather than socketed depending on board revision — budget
  for desoldering and fitting a machined-pin socket.

---

## 3. Feasibility analysis

### 3.1 STM32G431CB resources (verified against `modm-devices` device XML)

| Resource | Value |
|---|---|
| Core | Cortex-M4F @ 170 MHz (5.882 ns/cycle) |
| Flash | 128 KB — **4 wait states at 170 MHz** |
| SRAM1 / SRAM2 | 16 KB / 6 KB |
| CCM SRAM | 10 KB @ `0x10000000`, **`rwx`, zero-wait, on the I-bus** |
| GPIO (**UFQFPN48**) | **42** — `PA0-15`, `PB0-15`, `PC4/6/10/11/13/14/15`, `PF0/1`, `PG10` |
| GPIO (LQFP48, for contrast) | 38 — the same list **minus `PC4`, `PC6`, `PC10`, `PC11`** |

Both `PA` and `PB` are full contiguous 16-bit ports — the whole reason this package works.
The address bus is one 32-bit store; the data bus is one byte-aligned load.

**The package matters and the two 48-pin options are not interchangeable.** DS12589
Table 2 gives the GPIO count as "38 in LQFP48, 42 in UFQFPN48", and the four-pin
difference is precisely `PC4`, `PC6`, `PC10`, `PC11` — which is precisely `BA`, `BS`,
`UART_TX`, `UART_RX` in §3.2.

### 3.2 Pin budget and pinout

On the **UFQFPN48**: available 42, minus `PA13`/`PA14` (SWD, keep for bring-up) and
`PG10` (NRST) = **39**.

> ⚠ **The two 48-pin packages are not interchangeable, and only the UFQFPN48 works
> here** (machine-wide decision D4). The LQFP48 bonds out **38 GPIO, not 42** (DS12589
> Table 2: "38 in LQFP48, 42 in UFQFPN48"; its pinout figure carries `PA0-15`, `PB0-15`,
> `PC13/14/15`, `PF0/1`, `PG10` and nothing else on port C). `PC4`, `PC6`, `PC10` and
> `PC11` are **not bonded out** on LQFP48 — and those four carry `BA`, `BS`, `UART_TX`
> and `UART_RX`. The LQFP48 arithmetic is 38 − 2 (SWD) − 1 (NRST) = **35 usable**: the
> 33 mandatory CoCo 3 signals fit, but the only spares are `PF0`/`PF1`, so on that
> package there is no `BA`, no `BS`, and no debug UART — and configuring `GPIOC`
> registers for pins with no pads behind them fails silently. The **STM32G431CB*U*6,
> UFQFPN48** is the same die with the same peripheral set and all 42 GPIO, so the pinout
> below, `cpu/include/pinout.h` and the firmware work verbatim; QFN soldering is the
> entire cost. The alternative — LQFP48 with `BA`/`BS`/UART deleted from every table —
> is rejected: it costs the debug UART on a board that has never been brought up, for no
> saving. Ordering note: the `modm-devices` XML is a family pin list, not a per-package
> bonding table; DS12589 Table 2 and the package pinout figures are the authority (§11).
> How the wrong package got committed, and how it was caught, is archived in
> [history.md](history.md).

| Group | Count | Running total |
|---|---|---|
| **UFQFPN48 GPIO** | 42 | — |
| − `PA13`/`PA14` (SWD), `PG10` (NRST) | −3 | **39 usable** |
| `A0..A15` | 16 | 16 |
| `D0..D7` | 8 | 24 |
| `R/W` | 1 | 25 |
| `E`, `Q` (inputs) | 2 | 27 |
| `/RESET`, `/NMI`, `/IRQ`, `/FIRQ`, `/HALT` | 5 | 32 |
| `BUS_OE` (buffer tri-state for `/HALT`) | 1 | **33** |
| *optional:* `BA`, `BS` | 2 | 35 |
| *optional:* `BUSY`, `/LIC`, `AVMA` | 3 | 38 |
| *not needed:* `TSC` — grounded on the CoCo 3 (§2.6) | 0 | 38 |

**The CoCo 3 needs 33 of 39 pins. Six spare.** §2.6 settled this: `BA`, `BS`, `BUSY`,
`/LIC` and `AVMA` are all NC on the board, and `TSC` is grounded, so none of them need a
pin for this target.

**Recommendation — wire `BA`/`BS`, skip `BUSY`/`/LIC`/`AVMA`/`TSC`.** That is **35 used,
4 spare**. Rationale:

- `BA`/`BS` are the two most likely to matter to third-party hardware, and the cost of
  driving them is one store to `GPIOC->ODR` in the *slack* part of the cycle — **not** on
  the post-read deadline (§3.3).
- The remaining 4 spare pins buy a **debug UART (2 pins) and a status LED**, which are
  worth considerably more during bring-up than emulating outputs nothing reads. The
  UART in particular removes the "results only readable over SWD" limitation of the
  Phase 1 spike.
- `BUS_OE` stays. Not a 6309 pin — it is the buffer tri-state, and without it the
  `/HALT` floppy path (§2.2) cannot release the bus and NitrOS-9 will not boot. On a
  stock CoCo 3 nothing else drives the bus during `/HALT`, so this is strictly
  insurance for DMA cartridges — but it is one pin.

**The 48-pin part is comfortable and LQFP64 is not needed:** §2.6 removes six signals
from the must-wire list. This holds only on the **UFQFPN48** — on LQFP48 the same
accounting gives 35 usable pins against 33 used, and the "6 spare / 4 spare" numbers
here do not exist there (see the ⚠ block at the head of this section).

Drive-strength constraint works out cleanly: `PC13`/`PC14`/`PC15` are backup-domain pins
with limited output drive, so they are input-only here — and they carry `/NMI`, `/IRQ`,
`/FIRQ`, which are inputs anyway.

Two pin-saving tricks, both worth taking:

- **Derive the data-buffer enables from the buffered `R/W` in hardware.** That is
  literally what `R/W` means; no GPIO needed. (§3.6 splits the data path into a '574 for
  reads, enabled by `/R/W`, and a '541 for writes, enabled by `R/W` — both `OE`s are
  active low. `/R/W` is not free: it comes from the inverter on §3.6's BOM.)
- **One shared `BUS_OE`** for the address '541s, the write '541 and the `R/W` gate — the
  parts that face the backplane. They float together and only together, during `/HALT`.
  The read '574 is deliberately **not** in that set: its outputs face only `PA0..PA7`, so
  it has nothing to contend with and needs no `BUS_OE` term (§3.6).

```
PB0..PB15   A0..A15      out    one 32-bit store to GPIOB->ODR
              (PB8 = A8 is also BOOT0 — see the provisioning note below)
PA0..PA7    D0..D7       bidir  one byte load/store on GPIOA
PA8         E            in     same IDR read as the data bus   <-- deliberate
PA9         Q            in     same IDR read as the data bus   <-- deliberate
PA10        R/W          out
PA11        /RESET       in
PA12        /HALT        in
PA13/PA14   SWDIO/SWCLK  --     reserved for debug
PA15        BUS_OE       out    low-Z/high-Z for all bus buffers
PC4         BA           out
PC6         BS           out
PC10        UART_TX      out    USART3_TX (AF7) — debug console
PC11        UART_RX      in     USART3_RX (AF7)
PC13        /NMI         in     PC13-15 are input-only here: limited output drive
PC14        /IRQ         in
PC15        /FIRQ        in
PF0         LED          out    status
PF1         STRAP        in     §4.5 machine-mode strap — the last pin
PG10        NRST
```

Totals: 20 outputs (`A0-15`, `R/W`, `BUS_OE`, `BA`, `BS`), 8 bidirectional (`D0-7`),
8 inputs (`E`, `Q`, `/RESET`, `/HALT`, `/NMI`, `/IRQ`, `/FIRQ`, `UART_RX`), plus
`UART_TX` and `LED`, plus the `PF1` strap. **39 of 39, none spare** — on the UFQFPN48;
the same map needs 39 pins of the LQFP48's 35, i.e. it does not fit (§3.1). The last
spare pin goes to §4.5's machine-mode strap on `PF1`.

**`PB8` is `A8` and it is also `BOOT0`. That is a provisioning obligation, not a
pinout problem.** On the STM32G431 `BOOT0` shares `PB8`, and with the shipping default
option byte `nSWBOOT0` = 1 the pad is sampled **for the whole of the reset phase**
(RM0440 §2.6). `A8` sits on a `'541` input whose level at reset is undefined, so a module
shipped with factory option bytes boots the **system bootloader** on some resets and
flash on others — intermittently, and more often in the socket than on the bench, because
a connected debugger holds reset differently. Every module must be programmed with:

| Option bit | Value | Effect |
|---|---|---|
| `nSWBOOT0` | **0** | `BOOT0` is taken from the option bit; `PB8` is a plain GPIO |
| `nBOOT0` | **1** | that option bit selects main flash |

This is a one-time step per part, recorded in §7 Phase 6 as a gate. **Alternative:** a
pulldown on `PB8`. It works, but it fights the host's 4.7 K address pull-up as a divider
— strong enough to hold `PB8` low at reset against 5 V through 4.7 K means ~1 K, which
then loads `A8` differently from the other fifteen lines for the life of the board. Two
option bits cost nothing at runtime and nothing on the BOM. Take the option bits.

`BUSY`, `/LIC`, `AVMA` and `TSC` are deliberately absent — §2.6 confirmed the CoCo 3
does not connect them. Adding them later costs the UART and the LED, which is the wrong
trade for this target.

#### The same package covers the homebrew machine, and that decided its MMU

This document is written against the CoCo 3 drop-in, but the pin budget above is what
settled the *other* target's architecture, so record the arithmetic here where it lives.

[`docs/machine.md`](../../docs/machine.md) §5 item 6 asks the homebrew machine to give up
`BA`/`BS` and spend the pins differently:

| | CoCo 3 drop-in | homebrew, **MMU in the CPU** | homebrew, **MMU on the motherboard** |
|---|---|---|---|
| `A0..A15`, `D0..D7`, `R/W`, `E`, `Q` | 27 | 27 | 27 |
| `A16..A19` | — | **4** | 0 |
| `/RESET`, `/NMI`, `/IRQ`, `/FIRQ`, `/HALT` | 5 | 5 | 5 |
| `BUS_OE` | 1 | 1 | 1 |
| `BA`, `BS` | 2 | — | — |
| HSYNC, VSYNC in — `graphics.md` §12.2 | — | 2 | 2 |
| Machine strap `PF1` — §4.5 | 1 | 1 | 1 |
| UART ×2, LED | 3 | 1 — LED only, no room for the UART | 3 |
| **of 39** | **39**, none spare | **41 — does not fit** | **39**, none spare |

> ⚠ **Both target columns stand at exactly 39 of 39 — nothing is left over on either.**
> Two rows are easy to miss because they come from elsewhere:
>
> - **VSYNC.** Counting HSYNC pulses yields a line number *with no origin* — the
>   raster-compare timer needs a frame reset too, and resynchronising in the VBL handler
>   jitters by interrupt-dispatch latency (1–6 lines). VSYNC is therefore a hardware
>   input (`graphics.md` §12.2).
> - **The `PF1` machine strap**, which §4.5's shadow ROM needs in order to keep the
>   "one firmware, three machines" property. It is the pinout's last spare pin.
>
> The next CPU-side signal anyone wants costs the debug UART, and it should be a
> deliberate trade rather than a discovery during layout. §10.7's strap-versus-build-flag
> question is also a pin question: the build-flag alternative is what buys the spare back.
>
> **The in-CPU MMU column does not fit at all** — 41 pins against 39. It is also rejected
> on one-SKU grounds (below), so the question is retired rather than merely settled.

An in-CPU MMU costs the debug UART on a board that has never been brought up. Moving it
to 3 ICs on the motherboard ([`graphics.md`](../../video/docs/graphics.md) §6.3.1) returns
A16–A19, and **one STM32G431CBU6 then serves the CoCo 3, the Dragon 64 (§2.6.1) and the
homebrew machine** — one pinout, one board-support file, one firmware. That, plus the
48-pin part being cheaper and better stocked, is why the machine took the external MMU
rather than the LQFP64.

The homebrew column changes nothing above it: the bus loop, the §3.6 read latch and the
§3.3 budget are identical, and E/Q remain inputs there too (`graphics.md` §5.3 keeps
`arm6309` clock-slaved on both targets).

Design notes:

- **E and Q on `PA8`/`PA9`** — one `LDR` of `GPIOA->IDR` yields the data bus in bits 0–7
  *and* the clock state in bits 8–9. Saves a whole load on the critical path.
- **`/NMI`, `/IRQ`, `/FIRQ` on `PC13-15`** — those are backup-domain pins with limited
  output drive, safe only as inputs. Interrupt lines are inputs, so this is free.
- **Address bus on `PB`, not `PA`**, so `PA13`/`PA14` stay available for SWD. `PB3`/`PB4`
  are JTAG pins but free under 2-wire SWD.
- **Data-bus direction** is set during the *address-drive* step, when `R/W` is already
  known — deliberately kept off the post-read critical path.

### 3.3 Timing budget

A bus cycle runs from one falling edge of E to the next. Q leads E by 90°. Address and
`R/W` valid **before Q rises**; read data latched **at E's falling edge**; write data
driven before E rises.

At 170 MHz (5.882 ns per core cycle):

**The authoritative timing source is `reference/datasheets/HD6309E_datasheet.pdf`.**
Its p.3 gives AC characteristics for **HD63B09E and HD63C09E in adjacent columns**, and
Hitachi holds `t_AD` at **110 ns for both grades**: the address deadline does *not*
tighten at 3 MHz. (Two earlier framings of this deadline — the quarter cycle, then an
extrapolation from the MC6809E datasheet — were wrong in different directions; see
[history.md](history.md).)

**Datasheet timing — `reference/datasheets/HD6309E_datasheet.pdf` p.3, "AC CHARACTERISTICS".**
One core cycle = 5.882 ns at 170 MHz, the committed core clock (§0).

| Parameter | Symbol | HD63B09E (2 MHz) | HD63C09E (3 MHz) | Core cycles @170 MHz |
|---|---|---|---|---|
| Cycle time (min) | `t_cyc` | 500 ns | **333 ns** | 85.0 / **56.7** |
| Address delay | `t_AD` | ≤ 110 ns | **≤ 110 ns** | **18.7** |
| Address hold | `t_AH` | ≥ 20 ns | ≥ 20 ns † | 3.4 |
| Read data setup | `t_DSR` | ≥ 40 ns | **≥ 20 ns** | 6.8 / **3.4** |
| Read data hold | `t_DHR` | ≥ 20 ns | ≥ 20 ns | 3.4 |
| Write data delay from Q | `t_DDW` | ≤ 110 ns | **≤ 70 ns** | 18.7 / **11.9** |
| Write data hold | `t_DHW` | ≥ 30 ns | ≥ 30 ns † | 5.1 |
| Peripheral read access | `t_ACC` | 330 ns | 185 ns | — |
| Control delay (`BUSY`,`/LIC`,`AVMA`) | `t_CD` | ≤ 200 ns | ≤ 130 ns | — |
| Interrupt/`HALT`/`RESET`/`TSC` setup | `t_PCS` | ≥ 110 ns | **≥ 70 ns** | 18.7 / **11.9** |
| E low / E high (min) | `t_PWEL`/`t_PWEH` | 210 / 220 ns | 140 / 140 ns | — |
| E↔Q phase offsets (min) | `t_EQ1..4` | 100 ns | 65 ns | — |

† `t_AH` relaxes to 10 ns and `t_DHW` to 20 ns below 0 °C. Use the 0–75 °C column —
the module runs warm under the RF shield (§2.7), never cold.

**Note the *shape* of the 2 → 3 MHz change, because it redirects the whole design.**
`t_AD` and `t_AH` do not move. Everything that tightens is a setup or delay figure:
`t_DSR` halves (40 → 20 ns), `t_DDW` falls to 70 ns, `t_PCS` falls to 70 ns. So 3 MHz
does **not** squeeze the address-drive path. It squeezes **read-data sampling, write-data
delivery, and control-input setup.** §3.6 exists because of the first of those; the
other two are load-bearing gates that no variant yet measures (§8).

**These are absolute times, not fractions of the E period.** For any one part the same
`t_AD` applies at every rate it is clocked at, so on the CoCo 3 the 110 ns holds at both
0.895 and 1.79 MHz — **the deadline does not relax in slow mode.**

Also worth recording, since `reference/datasheets/MC6809E.pdf` disagrees: Motorola specifies `t_DHR` as
**10 ns**, Hitachi as **20 ns**. Design against 10 ns — it is the stricter number and the
CoCo 3 ships with a Motorola part in the socket.

**The address must be driven in the window [3.4, 18.7] core cycles after E falls.**
Both ends bind: driving too *early* violates `t_AH`, the hold time on the outgoing
address. Against an estimated 9–14 cycle floor for the critical path (below), the margin
is **5–10 cycles, not 10–15**.

| E rate | Period | Core cycles @170 MHz | `t_AD` | `t_DSR` | Verdict |
|---|---|---|---|---|---|
| **0.895 MHz** (CoCo 3 boot) | 1118 ns | 190.0 | 18.7 cy | 6.8 cy | throughput easy, deadline same |
| **1.79 MHz** (CoCo 3 fast) | 559 ns | 95.0 | 18.7 cy | 6.8 cy | **target — both gates clear** |
| 2.0 MHz (HD63B09E max) | 500 ns | 85.0 | 18.7 cy | 6.8 cy | same deadline; throughput fine |
| **3.0 MHz (HD63C09E max)** | 333 ns | 56.7 | 18.7 cy | **3.4 cy** | **needs §3.6 latch; drive path fine** |
| 5.0 MHz | 200 ns | 34.0 | n/a † | n/a † | out of spec for every 6309E grade |

† There is no speed grade above HD63C09E, and no datasheet supports 5 MHz. The
best-documented overclock found is 4 MHz (HD63C09 non-E, 16 MHz crystal ÷ 4, Digicool
Things). 5 MHz is not a target; if it is ever revisited, the deadline would have to be
derived from whatever the host's memory system needs, not from a Hitachi spec.

**The picture at 3 MHz inverts the intuition.** The
address-drive path — the thing variant 2 was hand-written to optimise — has **18.7
cycles of budget against a ~13-cycle path, i.e. 5.7 cycles spare, unchanged from
1.79 MHz.** What fails is read-data sampling, where the budget halves to 3.4 cycles.
No amount of assembly tuning fixes that (§3.3(c)); §3.6 does.

**The binding constraint is the post-read critical path.** From "read data valid at E-fall"
to "next address stored", in hand-written assembly with pointers preloaded:

| Step | Core cycles |
|---|---|
| E-fall detection — polling loop iteration jitter | 4–6 |
| `LDR` `GPIOA->IDR` (samples D0-7 *and* E/Q together) | 2–3 |
| Table lookup: next microstate/address from the data byte | 2–3 |
| `STR` `GPIOB->ODR` (drive address) | 1–2 |
| **Total floor** | **9–14** |

Plus ~5 ns (≈1.7 core cycles) of 74LVC buffer propagation each way.

Note what is **not** in that budget: the status outputs (`BA`/`BS`/`BUSY`/`/LIC`/`AVMA`)
need a second store to `GPIOC->ODR`, but they are updated in the *slack* portion of the
cycle, not inside the quarter-cycle deadline. They cost average throughput, not margin.
Same for the data-bus direction change, which happens during the address-drive step.

- **18.7 available (`t_AD`) vs 9–14 needed → 5–10 cycles of margin.** Workable, but
  tighter than the earlier period-relative model suggested, and the same at both CoCo 3
  clock speeds.
- Polling jitter alone is 4–6 cycles of that budget. It is the single largest term and
  the main argument for the hand-written assembly variant.

**(c) Read-data sampling — provable at 1.79 MHz, impossible in software at 3 MHz.**
Read data is guaranteed valid over `[E_fall − t_DSR, E_fall + t_DHR]`. `t_DHR` is
10 ns (Motorola) / 20 ns (Hitachi) — 1.7 to 3.4 core cycles — so **no polling loop can
reliably sample after the edge** at any speed grade. The sample must be taken *before*
E falls.

The `s_prev` trick in `spike_poll.c` samples continuously while E is high and keeps the
**last sample taken before E fell**. If the polling loop's iteration period is `T_iter`,
that sample lands in `[E_fall − T_iter, E_fall)`. So:

> **`T_iter ≤ t_DSR` ⟹ the sample is provably inside the guaranteed valid window.**

The bound is a hard function of the speed grade, and it is where 3 MHz breaks:

| Grade | `t_DSR` | `T_iter` budget @170 MHz | Software poll achieves |
|---|---|---|---|
| HD63B09E (≤2 MHz) | 40 ns | 6.8 cy | 6 cy (rolled) / 4 cy (unrolled) — **passes** |
| HD63C09E (3 MHz) | **20 ns** | **3.4 cy** | 4 cy best case — **fails** |

The floor for an M4 polling loop is 4 cycles per sample: `LDR` (2) + `TST` (1) +
untaken `B` (1). That is not improvable — three instructions with no slack — so
**software sampling cannot meet a 20 ns `t_DSR` on this part at any clock it can reach.**
(Even at 200 MHz, 4 cycles is exactly 20.0 ns: the limit, with zero margin. That was one
of the arguments against overclocking — see §3.4(4).) §3.6 moves the sample into hardware
and dissolves the constraint entirely.

Two consequences for the Phase 1 code as written:

- **The rolled loop's 4/6 gap pattern is avoidable.** `spike_poll_asm.S` pays a 3-cycle
  taken branch once per unrolled pair, giving gaps of 4 and 6 — *by instruction timing.*
  Note what that is worth: reading the disassembly establishes the instruction sequence,
  not the bus. An AHB2 GPIO `LDR` can cost 3+ cycles rather than the 2 it is costed at
  here, which would make the gaps 5 and 7 = 41.2 ns and fail the 40 ns soundness bound.
  **4/6 is the hypothesis `lat_jitter` is measuring, not an established fact**, and the
  straight-line variant below is worth building regardless because it removes the
  question rather than answering it. Since the sampling window
  is *bounded* (a quarter period after the Q-fall flag), the loop can be replaced by
  straight-line `LDR`/`TST`/`BEQ` triplets — each exiting to its own drive sequence, so
  the register-copy problem never arises — making every gap uniformly 4. ~5 samples cover
  3 MHz, ~7 cover 1.79 MHz; a rolled loop remains at the end as a safety net for a slower
  host than predicted. This is a strict improvement at 1.79 MHz and the only way software
  sampling gets close at 3 MHz. Costs ~30 instructions of CCM out of 10 KB.
- `spike_result_t.lat_jitter` (`lat_worst − lat_best`) measures `T_iter` on hardware,
  since where the edge lands in the poll loop is the only term that varies between
  cycles. It stays a first-class Phase 1 objective **for the 1.79 MHz gate**; at 3 MHz
  the answer is already known and the measurement to make instead is §3.6's.

**(d) Average throughput — and not all of the cycle is usable.**

The whole period is *not* available to the emulator. The CPU has to be *in* the tight
sampling loop when E falls, and any work interleaved between samples would breach
`T_iter`. So every cycle spent waiting for the edge is dead time.

Timeline of one bus cycle at 1.79 MHz (period 559 ns = 95 core cycles), from the service
manual's Figure 5-3 — note E is not a 50% duty cycle, it is 315 ns low / 244 ns high:

| Event | Time | Core cycles |
|---|---|---|
| E falls — drive address | 0 ns | 0 |
| E rises | 315 ns | 53.5 |
| **Q falls** | 419 ns | **71.3** |
| E falls | 559 ns | 95.0 |

**Waiting on the E pin costs the whole E-high phase.** The obvious loop structure spins
for E to rise, then samples until it falls — so the emulator only gets the E-low phase,
**53.5 cycles**, and the 41.5-cycle E-high phase is burned watching a pin.

**Waiting on Q's falling-edge capture instead recovers most of it.** Q falls at 0.75 of
the cycle, so its capture flag says "one quarter period to the edge". The loop does its
work first and only then enters tight sampling, which now needs to cover just the last
quarter period:

| | Usable by the emulator | Spent sampling |
|---|---|---|
| Spin on the E pin | 53.5 cycles (56%) | 41.5 |
| **Spin on the Q-fall flag** | **71.3 cycles (75%)** | **23.8** |

**+33% usable budget**, at both CoCo 3 clock speeds, and it costs one flag test. Implemented
in both polling variants; `slack_min` and `slack_late` in `spike_result_t` measure what is
actually left over.

Crucially this stays anchored on a *hardware event*, not a predicted time, so it survives
the live 0.895 ↔ 1.79 MHz switch (§2.1): a faster clock just means Q falls sooner and the
flag is already set.

Against a microcode step of ~15–30 cycles typical plus ~10 for drive and bookkeeping, the
throughput ceiling moves from **~2.4 MHz to ~3.2 MHz**.

**With the §3.6 latch the sampling window disappears entirely** — the CPU no longer has
to be in a poll loop for *correctness*, only for latency — and the budget opens up
further:

All rows at the committed 170 MHz core clock (§0), against a microcode step estimated at
**15–30 cycles**:

| E rate | Sampling | Cycles/bus cycle | − poll | − drive (~13) − bookkeeping (~10) | Microcode budget |
|---|---|---|---|---|---|
| **1.79 MHz** (target) | poll | 95.0 | − 23.8 | − 23 | **~48 cy** |
| 1.79 MHz | latch | 95.0 | — | − 23 | ~72 cy |
| **2.0 MHz** (HD63B09E max) | poll | 85.0 | − 21.3 | − 23 | **~41 cy** |
| 3 MHz | poll | 56.7 | − 14.2 | − 23 | ~20 cy — *and unsound, §3.3(c)* |
| **3 MHz** | **latch** | 56.7 | — | − 23 | **~34 cy** |

**Read across the second column, not the first.** What decides 3 MHz is not the core
clock — it is whether read data is sampled in hardware or software. At 170 MHz with the
§3.6 latch, 3 MHz has ~34 cycles for a step estimated at 15–30, i.e. **4–19 cycles of
slack depending where the real step lands.** That is the whole ballgame, and it is why
the microcode step cost is the top risk in §8 rather than anything about clocking.

**The microcode step cost is measured, not estimated.**
`cpu/tools/microstate-probe/` compiles candidate microstates with the firmware's exact flags
and runs each body through `llvm-mca`'s Cortex-M4 model. See that directory's README for
method and caveats. Headline result:

| Shape | Per bus cycle | vs 34 cy (3 MHz) | vs 48 cy (1.79 MHz) |
|---|---|---|---|
| **§4.1 as specified** — function-pointer struct, eager CC | **~80 cy** | 2.4× over | 1.7× over |
| Tuned, typical (8-bit ALU step) | **14 cy** | 20 spare | 34 spare |
| Tuned, worst measured (`TFM` step) | **25 cy** | 9 spare | 23 spare |

Component costs, tuned hot path (`cpu/tools/microstate-probe/tuned.S`):

| Component | Cycles | Paid |
|---|---|---|
| 8-bit or 16-bit ALU step, lazy CC | 5 | per cycle |
| Control-line sampling (AND-fold) | 5 | per cycle |
| Next-state advance | 4 | per cycle |
| Indexed post-increment EA | 10 | when addressing |
| `TFM` block-transfer step | 16 | during `TFM` |
| `cc_materialise()` | 24 | only when CC is read |
| `ctrl_decode()` | 14 | only at instruction boundaries |

**So 3 MHz fits, and the 15–30 estimate was pessimistic** — but only for a hot path built
the way §4.1 now describes. The naive shape misses the budget at *every* target rate,
including 1.79 MHz, which makes this a design constraint rather than an optimisation.

*Refinement, not yet implemented:* the E edge can be predicted from
`CCR2 + P/4 − margin` even under the live 0.895 ↔ 1.79 MHz switch (§2.1), which
invalidates any prediction made from the last observed period — **predict using the
fastest possible period, not the last observed one**, i.e. always assume 1.79 MHz.
After a switch you are then early, never late;
at 0.895 MHz you poll ~3× longer than necessary and lose nothing, because those cycles
were dead anyway. Worth ~+6–8 cycles per bus cycle. Moot once §3.6 lands, but correct.

**(e) The homebrew machine's actual E rates — 2.0979 and 3.1469 MHz.**

Everything above analyses 0.895 / 1.79 / 2.0 / 3.0 MHz, which are CoCo 3 and
datasheet-grade numbers. The homebrew machine of
[`docs/machine.md`](../../docs/machine.md) runs neither. Its E comes from the 25.175 MHz
video master clock, and the two divider settings give **2.0979 MHz** and **3.1469 MHz**.
Every "3 MHz" row above is therefore ~5 % optimistic for that machine, and the
difference is large enough to move a conclusion.

| | division | E | `t_cyc` | Core cycles @170 MHz |
|---|---|---|---|---|
| **Default — the only specified rate** | 25.175 / **12** | **2.0979 MHz** | 476.7 ns | **81.0** |
| **fast-E mode** — experimental, not guaranteed | 25.175 / **8** | **3.1469 MHz** | 317.8 ns | **54.0** |

Re-running §3.3(d)'s budget at the real rates, same terms (drive ~13, bookkeeping ~10):

| E rate | Sampling | Cycles/bus cycle | − poll | − 23 | Microcode budget | `TFM` @25 cy |
|---|---|---|---|---|---|---|
| **2.0979 MHz** | poll | 81.0 | − 20.3 | − 23 | **~38 cy** | 13 spare |
| **2.0979 MHz** | latch | 81.0 | — | − 23 | **~58 cy** | 33 spare |
| 3.1469 MHz (fast-E) | poll | 54.0 | − 13.5 | − 23 | ~18 cy — *and unsound, §3.3(c)* | −7 |
| **3.1469 MHz (fast-E)** | **latch** | 54.0 | — | − 23 | **~31 cy** | **6 spare** |

**The fast-E row is the one to watch.** The table in §3.3(d) budgets 3.0 MHz at 56.7
core cycles and ~34 with the latch, leaving 9 spare against the probe's measured 25-cycle
`TFM` worst case. At the machine's real 3.1469 MHz the bus cycle is **54.0** core cycles,
the budget is **~31**, and `TFM` keeps **~6 cycles, not 9**. That is still positive, but
it is 6 cycles of margin on a 25-cycle figure that the probe's own README calls a floor
rather than a worst case (the fragment is not `TFM`-shaped —
`cpu/tools/microstate-probe/README.md`). Treat fast-E as unproven on throughput as well
as everything else below.

**`t_cyc` at both rates, against the real silicon — and this is where fast-E dies.**

- **2.0979 MHz → `t_cyc` = 476.7 ns**, which is **below the HD63B09E's 500 ns minimum**.
  The 2 MHz grade cannot be clocked at the homebrew machine's *default* rate. Consequence
  for us: the A/B reference part of §6.2(1) must be an **HD63C09E**, and the C-grade
  column is the one that applies — `t_DSR` = **20 ns**, not 40. So **§3.6's latch is
  mandatory at this machine's default rate**, not only at fast-E. Our own budget does not
  move; we already design against the C-grade numbers.
- **3.1469 MHz → `t_cyc` = 317.8 ns**, which is **below the HD63C09E's 333 ns minimum**.
  There is no grade above HD63C09E (§3.3 footnote), so **no real 6309E is in spec at
  fast-E**. Two consequences, and the second is the expensive one: a real part may or may
  not work there, and **§6.2's silicon A/B reference cannot be captured at that rate at
  all** — the oracle the whole validation strategy is ranked around does not exist above
  ~3 MHz. Anything measured at fast-E is measured against our own model.

**Machine-wide decision D5 applies here verbatim: divide-by-12 (2.0979 MHz) is the
default and the only rate the machine is specified at.** fast-E (3.1469 MHz) is
**experimental and not guaranteed**, and three independent subsystems break there — video
VRAM read-back does not close (`video/docs/graphics.md` §11), a 2 MHz 6551 is 57 % over
rating (`io/docs/serial.md` §3.3), and the `t_cyc` violation above. The CPU module's
position: fast-E is a probe, it needs the §3.6 latch, it has ~6 cycles of `TFM` margin,
and it has no silicon reference. **Per naming decision D6 this rate is "fast-E mode";
it is never called "stretch mode", and "/WAIT" is reserved for a wait state or E-hold.**

### 3.4 Ways to buy headroom — taken, and rejected

Items 1–3 and 5 are live options; **items 4 and 6 are recorded rejections**, kept so the
reasoning is not repeated.

1. **Hand-written assembly on the hot path**, hot loop in **CCM SRAM** (zero-wait — flash
   is 4 WS at 170 MHz), interrupts disabled inside the bus loop, loop aligned. Do this
   regardless of target rate.
2. **Exploit the 6809's own dead cycles.** The real CPU inserts VMA cycles precisely where
   it needs settling time, notably in indexed addressing. Where a VMA cycle sits between
   the last operand byte and the data access, the emulator inherits a full extra cycle.
   Quantify in Phase 3 rather than assuming.
3. **Hardware-assisted address drive** (implemented as spike variant 3,
   `cpu/src/spike_dma.c`). The E falling edge triggers a DMA transfer of a *precomputed*
   word to `GPIOB->ODR`, with no CPU in the drive path.

   Two limits, both important:

   - **It does not help data sampling.** A DMA read triggered by the E edge lands past
     `t_DHR` (10 ns); one triggered by Q's fall lands a quarter period early, well before
     `t_DSR` opens (40 ns at the 2 MHz grade, 20 ns at 3 MHz). Neither is sound, so a
     polling loop is still required for data and the `T_iter ≤ t_DSR` bound stands
     unchanged. **§3.6 lifts this limitation** — once the byte is latched and held, DMA
     and interrupts can read it.
   - **It needs the address a full bus cycle ahead.** True for instruction-fetch runs,
     VMA cycles and stack operations; never for genuinely data-dependent cycles, which
     must fall back to variant 2.

   Whether this is worth building is an empirical question, and variant 3 exists to
   answer it: triggered DMA on STM32 is commonly 10–25 core cycles, so it may well come
   in **worse** than variant 2's ~13. That would be a useful negative result.
4. **Overclock the G4 to 200 MHz — evaluated and rejected (2026-08-28).**
   **The core clock is committed at 170 MHz** (§0). The analysis is recorded because
   the conclusion is not the obvious one.

   It would have bought ~+29% of microcode budget at 3 MHz (34 → 44 cycles, §3.3(d)) and
   nothing at all at 1.79 or 2 MHz, where the budget is already comfortable. **No gate
   moves from fail to pass**, at any target rate — including 3 MHz, which is gated by
   `t_DSR` and solved in-spec by §3.6. So the entire upside was throughput headroom on
   one optional target, against the following:

   **You cannot overclock the core without also overclocking the PLL VCO, and there is
   no configuration that avoids it.** DS12589 Rev 6, Table 45 (PLL characteristics):

   | Symbol | Parameter | Range 1 Boost | Range 1 |
   |---|---|---|---|
   | `fVCO_OUT` | PLL VCO output | — | **96 – 344 MHz** |
   | `fPLL_R_OUT` | PLL R output | **8 – 170 MHz** | 8 – 150 MHz |

   `PLLR` ∈ {2, 4, 6, 8}, so `SYSCLK = VCO / R` with `R ≥ 2`. **Maximum in-spec SYSCLK
   is 344 / 2 = 172 MHz.** `cpu/src/clock.c` already runs the VCO at 340 MHz — *98.8% of the
   ceiling*. Reaching 200 MHz requires VCO = 400 MHz, **16% over max**. So 200 MHz is
   three simultaneous spec violations: the digital core (+18%), `fPLL_R_OUT` (+18%), and
   the analog VCO (+16%). The VCO is the one to worry about — analog blocks fail by
   losing lock intermittently, not by stopping cleanly, and they degrade with temperature
   and V_DD far more sharply than digital logic does.

   Further drawbacks, roughly in order of how much they should matter here:

   - **The thermal environment is the worst case, not the bench case.** Overclock margin
     shrinks as temperature rises, and this module lives under the CoCo 3 RF shield
     (§2.7) with no airflow, in a machine that already runs warm. Validating at 25 °C
     says little about 55–60 °C under the shield. **Characterise hot or not at all.**
   - **V_DD sensitivity against a 1986 supply.** Margin scales with V_DD; the module runs
     from the socket's 5 V through an LDO. The largest supply disturbance is floppy motor
     spin-up — which coincides exactly with the `/HALT` path (§2.2) that gates the boot
     criterion.
   - **The failure mode is silent, rare, and lands where it cannot be observed.** The
     design premise is worst-case: one deadline miss in 10⁴ is wrong. A marginal silicon
     path failing 1-in-10⁸ passes every bring-up test, then corrupts a sector during a
     NitrOS-9 boot — indistinguishable from a flaky drive or bad 40-year-old media.
   - **It confounds the Phase 1 measurement.** A deadline miss could be architectural or
     marginal silicon, with no way to tell. §7 already orders this correctly (variant 4
     last); keep that ordering and treat the overclock as a *delta* against an in-spec
     baseline, never folded into it.
   - **Per-part variation makes it unpublishable.** Headroom varies by die and process
     corner, so requiring 200 MHz means hand-binning. Acceptable for a personal build;
     not for §7 Phase 8.
   - **TIM1 goes out of spec too** — APB2 at SYSCLK, specified to 170 MHz. It is both the
     Q-fall flag source and the instrument producing every number in `spike_result_t`.
   - **Flash wait states become undefined**, which squeezes CCM. The latency table is
     characterised to 170 MHz. The hot loop is in CCM (zero-wait) so the bus loop is
     insulated, but this forces the *whole* real core into CCM — microstate tables, both
     cycle tables, flag tables — and **CCM is only 10 KB**. The overclock aggravates a
     Phase 6 budget that will already be tight.
   - **The gain is ~13% on the drive path, not 18%.** Of the ~13-cycle path at 170 MHz
     (76 ns), roughly 10 ns is 74LVC buffer propagation (§3.5) — fixed silicon delay that
     does not scale. 170 MHz: 76 + 10 = 86 ns. 200 MHz: 65 + 10 = 75 ns.

   **Decision: 170 MHz, in spec, full stop.** §3.6 is mandatory, in-spec, deterministic
   and costs $0.30; 200 MHz was optional throughput carrying three simultaneous spec
   violations, an unmanufacturable per-part dependency, and a failure mode that would be
   indistinguishable from a bad floppy. The right way to spend the 10 cycles it would
   have bought is to make the microcode step cheaper — which is free, in spec, and has to
   be done anyway.

   **Reopen only if** the measured microcode step lands above ~34 cycles at 3 MHz *and*
   3 MHz has become a real requirement rather than a stretch. In that case prefer the
   §3.7 H7 escape hatch: it is in spec, it brings DCMI, and it does not make the design
   depend on which die you happened to buy.
5. **Escape hatch: a faster MCU.** The core is portable C11 (§4.4), so an STM32H723 at
   550 MHz makes higher rates straightforward. Reserve, not plan. Note it brings a second
   advantage unrelated to clock rate: the H7 has **DCMI**, a parallel-capture peripheral
   that latches a byte on an external clock edge in hardware — the on-chip equivalent of
   §3.6. See §3.7.

6. **Hardware mechanisms evaluated and rejected.** Recorded so they are not re-litigated.
   All were checked against RM0440 Rev 9, the copy in `docs/`.

   - **EXTI interrupt on E-fall — cannot work, and it is not a tuning problem.** An
     interrupt fires *after* the edge, and `t_DHR` is 10–20 ns (1.7–3.4 core cycles).
     Cortex-M4 exception entry is 12 cycles minimum plus the EXTI synchroniser plus the
     ISR's first instruction: ~15 cycles late to catch a value guaranteed for under 4.
     **No ISR can ever read the data bus.** Even used only to store a precomputed
     address, 12 + 4 ≈ 16 cycles against 18.7 leaves nothing, and entry latency is not
     even constant (a multi-cycle `LDM` in flight delays it) — jitter being the exact
     thing this design exists to eliminate.
   - **EXTI on Q-fall to wake the poll loop — strictly worse than the flag test.** The
     current `LDR`/`TST`/`BEQ` on `TIM1_SR` costs ~4 cycles; exception entry costs 12+
     and exit ~10 more, and you would enter the ISR only to start polling for E anyway.
     The apparent win ("the emulator needn't voluntarily check") is illusory: a microcode
     step must *complete* before its result is needed, so preemption mid-step helps only
     if every step is resumable, which costs more than the check.
   - **Timer/quadrature encoder mode on E and Q — produces the wrong kind of object.**
     E and Q genuinely are in quadrature, and TIM1/2/3/4/8 encoder mode would decode them
     into a counter advancing 4× per bus cycle. But a counter is *state you must poll*,
     at the same `LDR` cost as reading the pin or the flag, and input capture already
     gives strictly more information: a **cycle-exact 170 MHz timestamp** of the edge.
     Encoder mode's real purposes — direction and revolution counting — are meaningless
     here (E/Q never reverse), missed-cycle detection is already free from `CC1OF`
     overcapture, and it would consume the very CH1/CH2 channels now capturing E and Q.
   - **DMAMUX synchronisation / request generator — gates the *request*, not the
     *sample*.** RM0440 §13.4.4–13.4.5 (pp. 425–427): the sync block propagates a
     *pending DMA request* on an edge of `dmamux_syncx`. It sits upstream of the DMA
     controller, which then arbitrates and reads `IDR` **when the transfer executes**.
     Precisely-triggered request, sloppily-timed sample — exactly backwards. This is why
     item 3 above cannot be extended to the data path.
   - **Circular DMA continuously sampling `IDR` into a ring buffer** (a hardware `s_prev`)
     fails downstream instead: recovering the right entry means reading `CCR1`, computing
     an index, loading the sample, *then* the table lookup and store — 20+ cycles, over
     `t_AD` even at the 2 MHz grade.
   - **There is no way to latch a parallel group of input pins on the G431.** RM0440
     §9.3.1: *"The input data register (GPIOx_IDR) captures the data present on the I/O
     pin at every AHB clock cycle."* Free-running, with no freeze or capture-enable bit
     anywhere in the GPIO register set. RM0440 Table 2 confirms the G431/G441 column has
     **no FSMC and no QUADSPI**, and no STM32G4 has DCMI. Moving up to a G473 for its
     FSMC would not help regardless: FSMC is a bus *master* that generates its own
     address and control and samples on its own timing — there is no mode where it slaves
     to an external E clock.

   **The underlying reason none of it helps:** the post-read path is a *data-dependent
   handoff* — sample a byte, index a table with it, drive the result — inside 18.7 core
   cycles. Every hardware mechanism inserts a handoff (exception entry, DMA arbitration,
   peripheral-register visibility) between "value exists" and "CPU can act on it", and on
   this part that handoff alone exceeds the whole budget. The polling loop wins because it
   *fuses* the two: the value is in a register on the instruction after the sample.
   Nothing on a G431 beats that — which is what makes §3.6 an external part rather than a
   peripheral configuration.

### 3.5 Electrical

- The CoCo 3 is 5 V; the G4 is 3.3 V, and **most pins this design needs are not
  5 V-tolerant.** `PA0..PA7` (the entire data bus), `PB0`, `PB1`, `PB2`, `PB10`, `PB13`,
  `PB14` and `PC5` are `TT_a` — rated **3.6 V** (DS12589 Table 12, pp.52–53). Behind
  3.3 V-powered buffers this is fine; the MCU never sees more than 3.3 V. **Without
  buffers it is destructive on every read cycle.** This is what makes buffers mandatory
  rather than optional.

  On this pinout that means **six** of the sixteen address lines are 3.6 V pins
  (`A0`, `A1`, `A2`, `A10`, `A13`, `A14`); `PC5` carries nothing here. The full `TT_a`
  list is mirrored in `cpu/include/pinout.h`.
- Driving 5 V logic from 3.3 V: fine for LS/ALS/HCT (V_IH = 2.0 V), **not** plain HC
  (V_IH = 3.5 V). Check what the CoCo 3 actually uses on each bus.
- **74LVC574** for read data and **74LVC541** for write data (§3.6),
  **74LVC541 ×2** on the address bus, a
  **74LVC541** for the seven control inputs, a **74LVC1G125** for `R/W` out and a
  **74LVC2G04** for `/E` and `/R/W`. `BUS_OE` gates the address buffers, the write
  buffer and the `R/W` gate — the parts that face the backplane — and deliberately not
  the '574, whose outputs face only the MCU. Full drawing and the enable polarities in
  §3.6; ~5 ns each, already in the §3.3 budget.
- **`LVC`, not `HC` — this is a purchasing trap, not a preference.** The SN74**HC**574
  datasheet gives `VI` max = `VCC` (inputs clamp to the rail, so not 5 V tolerant) and
  `VIH` = 0.7 × `VCC`. Powered at 3.3 V its inputs are over-stressed by the CoCo's 5 V
  data bus and `VIH` = 2.31 V leaves 90 mV against the LS245's 2.4 V `VOH`; powered at
  5 V its outputs destroy the `TT_a` pins on every read. **SN74LVC574A** is 5.5 V tolerant
  at any `VCC` and has `VIH` = 2.0 V.
#### Open-drain instead of buffers? No.

Tempting, given the CoCo 3 already has 4.7 K pull-ups on all 16 address lines: drive the
STM32 pins open-drain, sink only, and let the existing pull-ups do the rising edge. No
level shifting, no buffers, and tri-stating for `/HALT` is free.

**The rising edge is far too slow.** The MC6809E datasheet's own bus-timing test load
(Figure 3, p.4) uses **90 pF for A0–A15**. With the CoCo's 4.7 K pull-up:

```
tau  = 4.7 kOhm x 90 pF                    = 423 ns
rise to V_IH 2.0 V from a 5 V rail:
t    = -tau x ln(1 - 2.0/5.0) = 423 x 0.51 = 216 ns
```

Against a `t_AD` budget of **110 ns**, the passive rise alone is **~2x over** — before
any emulator work happens at all. Real CoCo bus capacitance with a cartridge or Multi-Pak
attached is higher than 90 pF, making it worse.

Getting there passively would need ~1 K pull-ups (tau ≈ 90 ns, rise ≈ 46 ns), which means
adding 16 resistors and sinking 5 mA per line — **80 mA** with the bus all-low, plus the
ground bounce that implies. Not worth it. And the data bus has **no** pull-ups on the
CoCo 3 (D0–D7 go straight to IC3), so open-drain there would not work at all without
adding them.

**Open-drain is ruled out on timing, not on levels.**

#### Direct push-pull with no buffers? **No — ruled out on 5 V tolerance.**

**DS12589 Table 12 (`reference/datasheets/stm32g431kb.pdf` pp.52–53) lists `PA0`–`PA7` as `TT_a`, every
one of them.** `TT` means **3.6 V tolerant I/O** — not 5 V. `PB0`, `PB1`, `PB2` and `PB10`
are `TT_a` as well.

That is fatal in the most direct way possible:

- The CoCo 3's 74LS245 (IC3) drives **5 V TTL into the data bus on every read cycle**.
  Straight into `TT_a` pins rated 3.6 V. Not marginal — over-stressed on every read.
- `A0`, `A1`, `A2` sit on `TT_a` pins that the board's 4.7 K pull-ups would take to 5 V
  every time we tri-state for `/HALT`.

Nor can this be dodged by reassigning pins. The G431 is an analog-heavy part and its
`TT_a` pins are exactly the ADC/op-amp-capable ones, which are scattered through `PA` and
the low end of `PB`. **There is no way to form a contiguous 8-bit data port or a
contiguous 16-bit address port entirely from 5 V-tolerant pins** — and the contiguity is
what makes the single-store address write and single-load data read possible in the first
place (§3.2).

**Buffers are therefore architecturally required, not a design preference.** They are
doing two jobs, and the second one is the non-negotiable one: level shifting, and
protecting 3.6 V pins from a 5 V bus.

The §3.2 pinout is compatible as-is — behind 3.3 V-powered buffers, the MCU never sees
more than 3.3 V, so `TT_a` is fine. `BUS_OE` stays.

<details>
<summary>What the direct-drive option would have bought, had it been available</summary>

Recorded because it is the right answer on a 5 V-tolerant MCU, and worth revisiting if
the part ever changes: it would have freed `BUS_OE` (tri-stating becomes one
`GPIOB->MODER` write), saved ~1.7 core cycles per direction of buffer propagation against
an 18.7-cycle deadline, and cut parts and board area under the RF shield. Driving high,
the STM32's ~10–25 Ω output dominates the 4.7 K pull-up and the line would have sat near
3.3 V, comfortably above the 2.0 V `V_IH` of the LS parts downstream.
</details>

One risk is independent of the buffers and worth stating separately:

**3.3 V `V_OH` must satisfy every downstream `V_IH`.** The buffers output 3.3 V, not 5 V.
LS/LSTTL wants 2.0 V and is fine. **The GIME is the unknown** — it is a custom gate array,
and if its inputs are CMOS-level (`0.7 × V_DD` = 3.5 V) then 3.3 V is marginal. Buffers
do not fix this; only a 5 V-powered translator would. Probably only answerable by
measurement on real hardware, and it stays open (§10.3b).

#### Buffer selection

- **74LVC specifically, not 74HC/74AHC.** §2.6 found 4.7 K pull-ups to 5 V on all 16
  address lines and 47 K on `R/W`. When we tri-state under `/HALT`, those pull-ups drag
  the lines to 5 V while our buffer outputs are high-Z — which is only safe on a family
  with no clamp diode to V_CC. 74LVC is rated for 5.5 V on its I/O regardless of V_CC;
  74HC/AHC would clamp and conduct. When actively driving high, the LVC output
  (~10–25 Ω) easily wins against a 4.7 K pull-up and the line sits near 3.3 V, which is
  comfortably above the 2.0 V V_IH of the LS parts downstream.
- The module draws power from the socket's 5 V; include a 3.3 V LDO and proper decoupling.
- Clock: HSI16 + PLL to 170 MHz. No crystal — we are slaved to the GIME's E/Q.

### 3.6 The read-data latch — mandatory at 3 MHz, valuable at 1.79

**One 74LVC574 octal D flip-flop, clocked by E's falling edge, latches D0–D7 in hardware
at exactly the right instant.** It costs about $0.30 and it is the single highest-value
change in this document.

The motivation is §3.3(c): at the HD63C09E's `t_DSR` of 20 ns, software sampling has a
3.4-cycle budget at 170 MHz against a hard 4-cycle floor for an M4 poll. That gate cannot
be met in software at any clock this part can reach. It is met trivially in hardware.

**We are already committed to external buffers** — §3.5 made them mandatory, since
`PA0..PA7` are `TT_a` (3.6 V) and the CoCo drives 5 V TTL on every read. So there is
already a chip in the data path. Make it an edge-triggered one.

#### Timing

| | Available (HD63C09E) | 74LVC574 needs | Margin |
|---|---|---|---|
| Setup before E-fall | `t_DSR` = 20 ns | ~2–3 ns | ~7–10× |
| Hold after E-fall | `t_DHR` = 10 ns (Motorola) / 20 ns (Hitachi) | ~1.5 ns | ~7–13× |

Both ends clear by close to an order of magnitude, at the *tightest* speed grade.
**TODO: confirm `t_su`/`t_h` against the chosen vendor's LVC574 datasheet** — the figures
above are typical for the family, not verified for a specific part number.

**Subtract the inverter from the hold column.** The '574 clocks on a rising edge, so the
clock is `/E` and something has to invert it (see *Board impact* below). At 5.2 ns worst
case for a `'1G04` the hold budget is 10 − 5.2 − 1.5 = **~3.3 ns**, not the ~8.5 ns this
table implies. Still positive, still fine, but it is a 3× margin rather than a 7×, and it
is the reason the inverter goes between the socket and the '574 clock and **nothing else
does**.

#### What it buys

1. **The `T_iter ≤ t_DSR` gate disappears.** Sampling correctness moves into hardware,
   where it belongs. This is what makes 3 MHz reachable at all.
2. **The quarter-cycle poll window returns to the emulator** — the CPU no longer sits in
   a loop for correctness, only for latency. +14.2 cycles at 3 MHz, +23.8 at 1.79 MHz.
   See the budget table in §3.3(d).
3. **DMA and interrupts become usable for the data path**, because the byte is now *held*
   until the next E-fall rather than existing for 10 ns. This lifts the limitation
   recorded in §3.4(3).
4. **Variant 2's hand-tuned unrolled loop becomes optional.** The poll can go back to C.

#### What it does not buy

It does not help the address-drive deadline. `t_AD` still requires noticing E fell and
storing the next address, ~11–13 cycles, and the latch adds ~5 ns of clock-to-Q before
the byte is stable. Per §3.3 that gate has 5.7 cycles of margin at every rate through
3 MHz, so it does not need help — but do not expect the latch to provide any.

#### Why an external part beats the on-chip alternatives

Counterintuitively, the flip-flop is *better positioned* than any capture peripheral
would be: **the latched byte lands on GPIO pins**, returned by the same single 2-cycle
AHB2 `LDR` that already reads E and Q on `PA8`/`PA9`. §3.2's core optimisation — one
`LDR` yielding the data bus in bits 0–7 and the clock state in bits 8–9 — survives with
the latch and dies with any peripheral that delivers the byte to a peripheral register.
See §3.7 for the worked comparison.

#### Board impact — the glue, drawn properly

The bus is bidirectional, so the data path is split into a read path and a write path;
without the split the '574 would fight the MCU when it drives `PA0..PA7` for writes.

**Data path**

| Part | Function | Clock / enable | Notes |
|---|---|---|---|
| `74LVC574` | host `D0-7` → `PA0..PA7`, latched | `CLK` ← **`/E`** (rising edge of `/E` = falling edge of `E`) | `/OE` ← **`/R/W`**: outputs live during reads (`R/W` = 1) |
| `74LVC541` | `PA0..PA7` → host `D0-7` | `/OE1` ← **`R/W`**, `/OE2` ← **`BUS_OE`** | drives the bus during writes (`R/W` = 0), floats under `/HALT` |

Read the enable column as active-low throughout: a `'541`/`'574` output stage is on when
its `/OE` is **low**. `R/W` = 1 means read, so the *read* latch is enabled by `/R/W` and
the *write* buffer by `R/W`. Take both
from the **host-side** `R/W` net rather than from `PA10`, so the enables stay correct
during `/HALT` when another master owns the line.

**The `'574` does not need `BUS_OE`, and this is deliberate.** Its outputs face `PA0..PA7`
and nothing else — never the host bus — so there is nothing on the backplane for it to
contend with, and no reason to tri-state it for `/HALT`. `/R/W` alone is the whole enable
term; no OR gate is needed. The one thing
`/OE ← /R/W` must do is get the latch off `PA0..PA7` while the MCU drives them for a
write, which it does.

**Two inverted signals are needed, and one package supplies both:** `/E` for the `'574`
clock and `/R/W` for its `/OE`. **One `74LVC2G04` (dual inverter)** — or two `'1G04`s, or
one `'1G14` where a Schmitt input is wanted on `E`. Swapping an address `'541` for an
inverting `'540` is the other way to get an inversion, but it inverts eight lines to
obtain one, so the dual gate is cheaper and clearer.

**The `'574` clock must come off `E` directly, not through the input buffer, and this is
the tightest number in the section.** Data is guaranteed held only to `E_fall + t_DHR` =
**10 ns** (Motorola; Hitachi says 20 — design to 10, §3.3). The clock edge arrives late by
whatever is in its path:

| Path to the `'574` clock | Delay | Hold margin left of 10 ns |
|---|---|---|
| `E` → `'1G04` → `CLK` | ~3.5 ns typ, 5.2 ns max @3.3 V | **~4.8 ns worst case** |
| `E` → `'541` → `'1G04` → `CLK` | ~5 + 5.2 = 10.2 ns max | **negative — does not work** |

So `E` from the socket feeds the inverter directly, and separately feeds the `'541` that
drives `PA8`. The layout note at the end of this section ("`E` must reach the `'574`
clock no later than it reaches `PA8`") is satisfied by construction with margin to
spare, and the inverter's propagation is charged against `t_DHR`, not against `t_AD`.

**Control inputs and the `R/W` output — counted.**

| Signal | Direction | Channels |
|---|---|---|
| `E`, `Q`, `/RESET`, `/HALT`, `/NMI`, `/IRQ`, `/FIRQ` | host → MCU | 7 |
| `R/W` | MCU → host, tri-stated by `BUS_OE` | 1 |
| **Total** | | **8** |

Eight channels do not fit in one 4-channel `74LVC125`. The
inputs never need to tri-state — they are inputs — so they do not need `'125` channels at
all: **one `74LVC541` carries all seven with a channel spare**, `/OE` tied low. `R/W` is
the only signal that must float under `/HALT`, so it takes **one `74LVC1G125`** with
`/OE` ← `BUS_OE`.

**No 5 V control input may be wired directly to the MCU, tolerant pin or not.** DS12589
Table 14 (absolute maximum ratings) caps the input voltage on an `FT` pin at
**min(V_DD, V_DDA) + 4.0 V**, which is a *relative* limit: it is only 5.5 V once the rails
are up, and during LDO ramp-up — when the host is already driving `E`, `Q` and `/RESET` at
5 V — `V_DD` is somewhere between 0 and 3.3 V and the limit is below 5 V with it. The
`74LVC` inputs are rated 5.5 V **independent of `V_CC`**, which is exactly why the whole
control set goes through the `'541`. This applies to the `FT` pins as well as the `TT_a`
ones of §3.5; `TT_a` is worse (3.6 V absolute), but neither may see the socket directly.

**Glue budget:** `74LVC574` ×1 (data in), `74LVC541` ×1 (data out),
`74LVC541` ×2 (address), `74LVC541` ×1 (control in), `74LVC1G125` ×1 (`R/W` out),
`74LVC2G04` ×1 (inverters) — **7 packages**. Under a dollar in parts; the real cost is
board area under the RF shield (§2.7). **The §3.2 pinout is unaffected.**

#### Two things to verify on hardware

- **The failure mode inverts.** Reading `IDR` too *early* now returns the previous
  cycle's byte. Detection latency is ≥4 cycles (23 ns) against the '574's ~5 ns
  clock-to-Q, so it is safe by a wide margin — but it is a different failure than the one
  the spike was written to catch.
- **E must reach the '574 clock no later than it reaches `PA8`.** Layout note: drive both
  from the same buffer output.

### 3.7 MCU alternatives evaluated

Recorded so the choice is not re-litigated. **The STM32G431CB stands** — the die, in the
**UFQFPN48** package per §3.2. The comparison below is about silicon, and none of it
turns on the package.

#### ATSAMD51G19A — rejected

Evaluated because it has **PCC** (Parallel Capture Controller, datasheet §52): one clock,
up to 14-bit parallel data, DMA-capable — the on-chip equivalent of §3.6, and exactly the
thing the G431 lacks. On the 48-pin G package PCC survives: `CLK` on `PA14`,
`DATA[7:0]` on `PA16–PA23`, `DEN1`/`DEN2` on `PA12`/`PA13` (optional via `MR.ALWYS=1`).
It also brings 192 KB SRAM / 512 KB flash against 32 KB / 128 KB, and `PA00–PA25` is a
contiguous 26-pin run.

Two apparent blockers that are **not** blockers, in fairness: `PA14` (PCC_CLK) sits inside
the only contiguous 16-bit run, but A0–A13 on `PA00–PA13` plus A14–A15 on `PA24`/`PA25`
recovers a single 32-bit store at zero runtime cost, because the address comes from a
lookup table that can hold the pre-scrambled word (the trick `stub_next_addr` already
uses). And PCC samples on the rising edge only (§52.6.1, no polarity bit) — feed it
inverted E, free given the buffers.

It loses on six counts:

1. **120 MHz against 170 MHz** (`fCPU` max, Table 54-5). `t_AD` is absolute time, so this
   is a straight 29% cut in the budget with the least margin: 110 ns is **13.2 cycles at
   120 MHz vs 18.7 at 170**, against a ~13-cycle path — roughly zero margin at the
   primary target, where the G431 has 5.7.
2. **PCC delivers the byte to the wrong place.** §52.6.1: *"the PCC samples the data at
   rising edge of the sensor clock, **and resynchronises it with the PCC clock domain**"*,
   with the standing constraint that `CLK_APB_PCC` ≥ 2 × `PCC_CLK`. The byte appears in
   `RHR`, an APB register, behind a clock-domain crossing — a streaming design, not a
   low-latency one. Against §3.6, where the byte lands on GPIO pins inside the `LDR` that
   already reads E and Q, **a $0.30 flip-flop is architecturally better positioned than
   the on-chip peripheral.**
3. **GPIO is slower.** Datasheet §32.1: *"The PORT is connected to the high-speed bus
   matrix through an AHB/APB bridge."* §32.5.3 adds *"One clock cycle latency can be
   observed on the APB access in case of concurrent PORT accesses."* The G431's GPIO is
   on AHB2 at core clock. The address store is the most deadline-critical instruction in
   the design. (SAMD51 has no IOBUS — that was the SAMD21's M0+ feature.)
4. **No CCM, no TCM — a determinism regression.** §3.4(1) depends on the G431's CCM at
   `0x10000000`: `rwx`, zero-wait, on the I-bus. The SAMD51 has only a cache in front of
   flash, and a cache is precisely wrong for a design whose every gate is worst-case.
   Running from SRAM is possible, but SAMD51 SRAM sits on the AHB matrix and contends
   with DMA — active exactly when PCC is streaming.
5. **Writes need the pins back.** PCC is input-only and `PA16–PA23` are its only data pins
   on this package; the budget (14+2 address, 8 data, CLK, E, Q, `R/W`, 5 control,
   `BUS_OE`, 2 SWD ≈ 36 of 38 GPIO) leaves no room for a separate write path. Every write
   cycle needs a PMUX switch on `PA16–23` and a switch back — `WRCONFIG` can do it in one
   or two writes, but it is a per-cycle peripheral mode change on a bus that must be
   cycle-exact.
6. **Not 5 V tolerant either**, so §3.5's buffers remain mandatory — no BOM saving — and
   at roughly $5–8 it costs *more* than G431 + '574 (~$3.30).

**Verdict:** the one capability it adds is supplied better and more cheaply by an external
latch, while it gives back 29% of the core clock on the gate no peripheral can help. It
would win a different project — one sampling-bound rather than deadline-bound, at a low
enough rate for `t_AD` to be comfortable. Not this one.

#### STM32H723 — held in reserve

See §3.4(5). 550 MHz, and it has **DCMI** — a genuine parallel-capture peripheral clocked
by an external PIXCLK. Two independent advantages, either of which would settle the
question at rates above 3 MHz. Rejected for now on cost (~$20 against ~$3) and because
§3.6 makes it unnecessary. Revisit only if the microcode step measures far above the
15–30 cycle estimate.

---

## 4. Software architecture

### 4.1 Microcoded core, one state per bus cycle

Not a `switch (opcode)` interpreter. An explicit state machine where **every state emits
exactly one bus cycle**.

**The obvious mechanism misses the budget, and that is measured, not estimated.** A
per-state struct carrying two function pointers (address and action) with
eagerly-computed condition codes costs **~80 core cycles per bus cycle — over budget at
every target rate, including 1.79 MHz** (`cpu/tools/microstate-probe/`). Two indirect
calls cost ~8 cycles of pipeline refill alone, the per-state struct load costs more, and
eager CC computation costs 31 cycles for an 8-bit ADD. The shape — one state, one bus
cycle — is retained conceptually; the mechanism is the three rules below.

**Three rules, all measurement-driven. They are constraints, not optimisations.**

1. **Dispatch by index into a jump table, not by function pointer.** The successor is a
   table index the hot loop advances (4 cycles), not a pointer chased through a struct.
   Actions are inlined into the loop, not called.
2. **Condition codes are lazy.** Keep the ALU operands and raw result in pinned registers;
   materialise H/N/Z/V/C only when an instruction can observe CC. An 8-bit ALU step goes
   from 31 cycles to 5. **This is an accuracy obligation:** every path that can read CC
   must go through `cc_materialise()` — *including the interrupt stacking sequence, which
   stacks CC*. Missing one is a correctness bug, and accuracy is the product.
3. **Control lines are AND-folded raw, decoded at instruction boundaries.** All five
   inputs are active low, so `AND`-ing the raw port words into an accumulator loses
   nothing and costs 5 cycles per bus cycle instead of 27. Edge detection and `CC.I`/
   `CC.F` masking happen where there is slack.

**Known divergence from silicon in rule 3, and it is an accuracy question, not a
performance one.** The AND-fold samples `/NMI`, `/IRQ`, `/FIRQ` and `/HALT` at whatever
instant the fold instruction happens to execute — wherever the microcode step put it in
the bus cycle, which varies with the path taken. Real silicon samples those inputs at a
**defined** point, with `t_PCS` setup before it (110 ns at the B grade, 70 ns at the C
grade — §3.3). The fold never *loses* an assertion, which is what it was chosen for; what
it can do is notice one a bus cycle earlier or later than the part would, when the edge
lands near the sampling boundary. Visible as a one-bus-cycle shift in interrupt
recognition in a trace diff, and only there. Recorded in §8 and to be pinned against the
§6.2(1) silicon capture once cycle accuracy is the product rather than the goal.

Hot state pinned in callee-saved registers for the whole run: `A`, the lazy-CC triple,
both control accumulators, the `cpu_t *`, and the GPIO base addresses. `X`/`Y`/`U`/`S`
stay in memory — too numerous to pin — laid out contiguously so indexed register select
is a scaled load rather than a four-way branch.

Forced by §3.3, not chosen for elegance:

- The post-read path collapses to an indexed table lookup — the only shape that fits
  inside `t_AD` (18.7 core cycles at 170 MHz, §3.3).
- Dead/VMA cycles are ordinary states driving `$FFFF`, so L2 accuracy falls out of the
  structure rather than being retrofitted.
- Cycle counts become structural instead of a hand-maintained table that drifts.
- Interrupt and `/HALT` sampling happen at well-defined points in every state.

### 4.2 Pipelining

Run the emulator **one bus cycle ahead** wherever the next transaction is knowable, so the
timing-critical code only stores a precomputed descriptor. This is also what makes the DMA
trick in §3.4(3) usable. It fails exactly when the next address depends on data just read
— hence the short, table-driven post-read path.

### 4.3 6309-specific work beyond the 6809

- **Registers:** `E`, `F` (→ `W` = E:F, `Q` = D:W = A:B:E:F), `V`, zero-register `Z`, `MD`.
- **`MD` modes** via `LDMD` (`$11 $3D`): bit 0 `NM` (native), bit 1 `FM` (FIRQ stacks like
  IRQ), bit 6 `/IL` (illegal-instruction trap), bit 7 `/DZ` (divide-by-zero).
- **Two cycle-count tables.** Native mode is shorter for many instructions (`LDA direct` is
  4 cycles in emulation mode, **3** in native). Doubles the validation surface. **NitrOS-9
  runs native**, so this table is on the critical path to the success criterion.
- **New instructions:** inter-register `ADDR`/`SUBR`/`ANDR`/`ORR`/`EORR`/`CMPR`; bit ops
  `BAND`/`BIAND`/`BOR`/`LDBT`/`STBT`; `MULD`, `DIVD`, `DIVQ`; `LDQ`/`STQ`, `ADDW`.
- **`TFM` block transfer** — the hard one. Interruptible mid-transfer, per-byte bus cycles,
  specific state on interrupt/resume. Budget real time.
- **Traps** — illegal instruction and divide-by-zero both vector through `$FFF0` (§2.4).
- **`BUSY`** asserted during read-modify-write and `TFM`.
- **`/HALT` state machine** per §2.2 — instruction-boundary entry, `BA`=`BS`=1, buses to
  high-Z via `BUS_OE`, precedence over interrupts.

### 4.4 Portability

Freestanding **C11**, bus interface behind a narrow `read8`/`write8`/`cycle_tick`
interface. Must build and run identically on desktop and on the MCU. Non-negotiable — the
validation strategy (§6) and the escape hatch (§3.4(5)) both depend on it.

### 4.5 Boot — the shadow ROM and vector page live in the CPU module

**Machine-wide decision D1.** Without this mechanism the homebrew machine cannot boot:
no ROM chip exists anywhere in its physical map, and the reset vector at `$FFFE` lands
inside the I/O page — which overrides MMU translation by design — so nothing decodes
there (`docs/machine.md`). The resolution puts the boot ROM **in this module**, served
from STM32 flash with no bus cycle at all, because that is the one place in the machine
that already has non-volatile storage and an address decoder.

**This is specification, not implementation.** Phase 1 is a timing spike and has no
shadow ROM; the mechanism lands with the core, in Phase 6b (§7).

#### 4.5.1 What the module serves

| Logical range | Served from | When |
|---|---|---|
| `$E000`–`$FEFF` | STM32 flash, **shadow ROM** | from reset until the OS clears the disable bit |
| `$FF00`–`$FFBF` | **nothing — decodes normally** | always: cards and the MMU answer here |
| `$FFC0`–`$FFEF` | STM32 flash, shadow ROM | same as `$E000`–`$FEFF` |
| `$FFF0`–`$FFFF` | 16-byte internal **vector RAM** | **always**, disable bit or not |

Three rules, and the second is the one that is easy to get wrong:

1. **A shadowed read never becomes a bus cycle.** The emulator resolves the address
   internally and supplies the byte from flash. Externally the cycle still happens — E, Q
   and the address are the host's, and cycle accuracy is unaffected — but the module
   ignores `D0..D7` and drives `BUS_OE`/`R/W` as it would for any read. Nothing on the
   backplane responds, because nothing is decoded there while the shadow is on.
2. **`$FF00`–`$FFBF` is carved out and must keep decoding normally.** The boot code has to
   talk to the MMU, the video card and storage while it is running, and all of that lives
   in the I/O page. A shadow that covered the whole of `$FF00`–`$FFFF` would work exactly
   until the first register access.
3. **Vector service is unconditional.** `$FFF0`–`$FFFF` comes from the vector RAM whether
   the shadow ROM is enabled or not, which is what lets the OS retarget the vectors after
   it has switched the shadow off. The RAM is initialised from flash at reset to point
   into the shadow ROM, so the reset vector is valid on the first fetch.

#### 4.5.2 Control, and turning the whole thing off

- **Disable bit** — one bit in the MMU control window (`docs/machine.md` and D3's
  74HC574 own the exact register and bit; this module reads the same write). Setting it
  retires `$E000`–`$FEFF` and `$FFC0`–`$FFEF`, freeing that logical space for RAM once
  NitrOS-9 is up. It is a one-way switch per reset by design: nothing re-enables the
  shadow except a reset, so a wild store cannot bring the ROM back over live RAM.
- **Vector RAM is writable through the MMU window**, 16 bytes, so the OS installs its own
  vectors and the shadow ROM's are only the bootstrap set.
- **Machine-mode gating.** On the **CoCo 3 and the Dragon 64 the entire mechanism is
  off** — those machines have their own ROM in the socket's address space, and a module
  that answered `$E000`–`$FFEF` from flash would be a drop-in that boots something else.
  Mode is read once at reset from the **`PF1` strap** (§3.2's remaining spare pin: pulled
  up = drop-in, tied low on the homebrew motherboard), which keeps one firmware image
  serving all three machines as §3.2 intends. **Recorded alternative:** a build-time flag
  and two images, which costs nothing electrically and gives up the single-image
  property. *Owner's call; the strap is what this document specifies.*
- **Recorded alternative to the whole feature** (D1): an 8 KB EPROM plus decode on the
  motherboard — 2 ICs, no CPU divergence, but the `$FF00`–`$FFBF` carve-out has to be
  drawn in real logic instead of being a range test in firmware. If that is taken
  instead, this section becomes dead and the drop-in property below is restored.

> ⚠ **Consequence for the drop-in claim.** `video/docs/graphics.md` §16.8's "you can drop
> a real HD63C09E into the homebrew machine" property **does not hold** with the shadow
> ROM in the CPU: a real 6309 has no flash and the machine has no boot ROM without it.
> The property survives only under the EPROM alternative; the trade is live (§10.8).

#### 4.5.3 Cost

| Item | Cost |
|---|---|
| Shadow ROM image | **~8 KB of the 128 KB** internal flash (6.3 %) |
| Vector RAM | 16 bytes of SRAM, plus 16 bytes of flash for the reset image |
| Per-cycle cost | one range test on the address the microcode is about to drive |
| Pins | one, `PF1`, the last spare — or zero, under the build-flag alternative |

The flash budget is comfortable: Phase 1 links at ~4 KB and the core is not expected to
approach 100 KB, so an 8 KB guest-code region does not compete with anything. The
per-cycle cost is the term to watch — it lands in the microcode step measured in
§3.3(d), not in the `t_AD` path, because the decision "does this read come from flash?"
is made when the address is *formed*, one step before it is driven.

---

## 5. Phase 1 in detail — the timing spike

**Runs before any emulator work.** It answers the only question that can invalidate the
project, on hardware, in about a week.

**Build:** a bare-metal G431CB program using the §3.2 pinout, running the exact
critical-path sequence — poll E, `LDR GPIOA->IDR`, index a table with the data byte,
`STR GPIOB->ODR` — driven by a **stub** state machine (plausible microstates, no real 6309
semantics). Timing shape of the real thing, none of the logic.

**Drive it:** a second MCU or signal generator producing E and Q at 90°, sweepable, and
able to **switch between 0.895 and 1.79 MHz mid-run** to exercise §2.1.

**Measure:**
- Deadline misses detected in-loop against a **hardware TIM1 timestamp** of E-fall:
  timestamp E-fall, timestamp address-store, flag any cycle exceeding the pass gate
  (`SPIKE_TAD_CYCLES`). The `t_AD` budget is 110 ns = 18.7 core cycles at 170 MHz — *not*
  the quarter cycle; see §3.3 — but **the gate is 14, not 18**, and the four missing
  cycles are the point:

  > **The measurement is biased optimistic, not conservative.** The `DSB` before the
  > timestamp errs in the safe direction, by a
  > couple of cycles — but three larger terms err the other way. **(1)** TIM1's capture
  > path resynchronises `TI1` to the timer clock even with the input filter off
  > (`ICF` = 0), so `CCR1` is latched **~2–3 core cycles after the physical edge**, and
  > every cycle of that lag subtracts from the measured latency. **(2)** `t_done` is read
  > when the store retires, not when the pad moves: ~3.3 ns (~0.6 cycles) of slew at
  > `VERY_HIGH` follows it. **(3)** Phase 1 runs unbuffered on the bench
  > (`cpu/tools/stimulus/README.md`), so the `'541` propagation outbound and the `'541`
  > on the inbound `E` are both absent from the number and present in the product,
  > ~0.9 cycles each. **Net ~3–5 cycles of optimism against a claimed margin of 5.7** — a
  > spike reporting 17 could be a socket-referred 21, and an 18-cycle gate would pass it.
  >
  > **The gate is 14** (`cpu/include/spike.h`, `SPIKE_TAD_CYCLES`; the raw 18 is kept
  > alongside as `SPIKE_TAD_RAW_CYCLES` for the arithmetic). A gate that is too tight
  > costs a rerun; one that is too loose costs a PCB.
  >
  > **The better fix, when the bench allows it: calibrate the offset out.** Jumper an
  > address line to a spare timer capture input — `PA11` is `TIM1_CH4` and carries
  > `/RESET`, so it can be borrowed — and difference two hardware timestamps taken
  > through the same capture path. The synchroniser delay then cancels instead of being
  > guessed at, and the gate can go back to 18 with evidence behind it. Until that
  > measurement exists, 14 stands.
- **Worst case, not average.** An emulator that misses one deadline in 10⁴ is simply wrong.
- Sweep E upward until misses appear. That frequency is the real ceiling.

**Variants**, since the difference between them is the engineering question:
1. Software polling loop, C.
2. Software polling loop, hand-written assembly (rolled; `T_iter` 4/6).
3. EXTI + DMAMUX + DMA precomputed store (§3.4(3)).
4. *Dropped* — this slot held the 200 MHz overclock of (2)/(3), rejected in §3.4(4).
   The core clock is committed at 170 MHz, so there is no overclocked variant to measure.
5. **Straight-line unrolled poll** (§3.3(c)), uniform `T_iter` = 4.
6. **External '574 latch** (§3.6). The one that decides whether 3 MHz is reachable.

**Exit criteria:**
- **Hard gate: zero deadline misses at 1.79 MHz**, including across a live speed switch.
- Measured max-E-frequency per variant, recorded.
- `T_iter` measured per software variant, against `t_DSR` = 40 ns (2 MHz grade) and
  20 ns (3 MHz grade).

**Predictions on record** (worth checking honestly — a wrong prediction here is
informative), sized against the real HD63C09E numbers:

| Variant | Predicted ceiling | Reasoning |
|---|---|---|
| 1 — C poll | ~2 MHz | `T_iter` ≈ 7, fails `t_DSR` = 40 ns |
| 2 — asm poll, rolled | ~2.5 MHz | `T_iter` = 6, passes 40 ns, fails 20 ns |
| 3 — DMA address drive | ~3–3.5 MHz for the drive path only | does not address sampling |
| 5 — asm poll, straight-line | ~2.9 MHz | `T_iter` = 4 = 23.5 ns, still over 20 ns |
| **6 — '574 latch** | **≥3 MHz, throughput-limited** | sampling gate removed entirely |

**1.79 MHz should pass on variant 1 or 2 with room to spare.** If it does not, stop and
reconsider the MCU before writing a single instruction of the core. **3 MHz should pass
only on variant 6** — and if variants 1–5 confirm that, the negative result is as
valuable as the positive one, because it retires software sampling permanently.

---

## 6. Validation strategy

**Accuracy claims are worth exactly what you can prove.**

### 6.1 There is no off-the-shelf 6809/6309 test suite

Confirmed: `SingleStepTests/ProcessorTests` (JSON per-instruction suites with bus activity,
covering 6502/65816/68000/8088/Z80/SPC700) has **no 6809 or 6309 set**. Producing one would
be a genuine contribution and is the natural by-product of doing this properly.

### 6.2 Reference sources, ranked by trustworthiness

1. **A real HD63C09E in the same CoCo 3 socket (best).** Since a real 6309 is a known-good
   CoCo 3 upgrade, you get a perfect A/B reference: same board, same GIME, same software,
   swap only the CPU. Capture both with a logic analyzer and diff. Nothing beats this.
2. **`strickyak/tfr9`-style capture rig** — a Pi Pico providing RAM/peripherals to a real
   6309E. The inverse of this project, and an ideal blueprint for generating targeted
   instruction-level traces outside the CoCo.
3. **Hitachi `HD63B09EP Technical Reference Guide`** and **Darren Atkinson's *Motorola 6809
   and Hitachi 6309 Programming Reference*** — authoritative cycle tables for both modes.
4. **RTL cores** — `cavnex/mc6809` (cycle-accurate Verilog 6809), `Nitrobotics/hd6309`
   (Verilog 6309). Simulate under Verilator/Icarus for automated cycle-by-cycle diffing.
5. **MAME `hd6309.cpp`** — fine for functional semantics. **Do not trust it for native-mode
   cycle counts:** MAME bug 09174 reports native-mode branch cycle counts as incorrect.
   Since NitrOS-9 runs native, this matters. Cross-check only, never the oracle.

### 6.3 Test layers

1. **Unit** — per-instruction state transitions, all addressing modes, both `MD` modes.
2. **Differential fuzzing** — randomized state + random opcode, single-step, diff against
   the RTL model. Shakes out the long tail and undocumented opcodes.
3. **Cycle-count regression** — assert against transcribed datasheet tables for both modes.
   Fail the build on drift.
4. **Bus-trace diff** — full traces vs RTL simulation and vs captured silicon.
5. **On-target timing** — DWT worst-case instrumentation, continuously, not just Phase 1.
6. **System-level, escalating on real CoCo 3 hardware:**
   - a. Boots to Color BASIC.
   - b. Survives a live 0.895 ↔ 1.79 MHz speed switch.
   - c. Reads a floppy sector (exercises the `/HALT` path, §2.2).
   - d. **Boots NitrOS-9 Level 2, 6809 mode.**
   - e. **Boots NitrOS-9 Level 2, 6309 native mode.** ← success criterion
   - f. Runs cycle-timed GIME video software correctly (§2.5).

---

## 7. Development phases

Ordered so the highest-risk unknown resolves first. Each gate is hard.

### Phase 1 — Timing spike (1 week) ← **start here**
Per §5. Bare-metal bus loop with a stub state machine on real G431CB silicon.
The stimulus generator needs a '574 fitted on the data path to exercise variant 6 (§3.6);
wire it in from the start rather than retrofitting.
**Exit:** zero deadline misses at 1.79 MHz including a live speed switch; ceiling measured
per variant; `T_iter` measured per software variant.

### Phase 2 — Reference material and skeleton (2–3 days)
CoCo 3 service-manual schematic reviewed for §2.6 and §2.2 specifics. Datasheets collected.
**Both cycle-count tables transcribed to machine-readable CSV/JSON** (test data, not prose).
Repo, CMake (host + `arm-none-eabi`), CI.
**Exit:** tables machine-readable; `/HALT`, `BA`/`BS`, `TSC`/`/LIC`/`AVMA`/`BUSY` usage on
the CoCo 3 confirmed in writing; `make test` green on host.

### Phase 3 — Core, 6809 subset (2–3 weeks)
Microcoded state machine, full 6809 instruction set, L2 accuracy, `/HALT` state machine,
host-only. RTL golden model and differential fuzzer stood up alongside.
**Exit:** bus-trace diff against `cavnex/mc6809` clean over ≥10M randomized instructions.

### Phase 4 — 6309 extensions (2–3 weeks)
New registers, `MD` modes, new instruction classes, `TFM`, both traps, `BUSY`. Native-mode
cycle table wired into regression.
**Exit:** clean differential run against the 6309 RTL model; cycle regression green in both
modes.

### Phase 5 — Silicon ground truth (1–2 weeks, parallel with 3–4)
Capture rig with a real HD63C09E. Traces for targeted sequences — especially `TFM`,
interrupts, `/HALT` entry/exit, and undocumented corners.
**Exit:** captured traces match the software core; discrepancies resolved in favour of
silicon.

### Phase 6 — Bring-up on target (1 week)
Real core into the Phase 1 bus loop. Hot loop in CCM SRAM, interrupts off.

**Provisioning, before any part goes into a socket — do this first, once per module:**

| Step | Value | Why |
|---|---|---|
| Option bytes `nSWBOOT0` / `nBOOT0` | **0** / **1** | `BOOT0` is `PB8` is `A8` (§3.2). With the factory default the part samples the address bus at every reset and boots the system bootloader on some of them. |
| Read back and verify the option bytes | — | They are programmed through a separate flash controller sequence and a failed write is silent. |
| Machine strap `PF1` | pulled up on a drop-in carrier, tied low on the homebrew motherboard | Selects the §4.5 shadow ROM off/on. |

**Exit:** option bytes verified on every module in circulation; worst-case DWT within
budget at 1.79 MHz with ≥20% margin. Confirm the real core did not blow the Phase 1
numbers.

### Phase 6b — Shadow boot ROM and vector page (3–5 days, homebrew target only)
§4.5. Shadow-ROM window served from internal flash, the 16-byte vector RAM, the
disable bit read off the MMU window's write, and the `PF1` machine gating that turns all
of it off for the CoCo 3 and the Dragon 64. The guest-side boot image is `software/`'s
problem; this phase is the mechanism that serves it.
**Exit:** the homebrew machine fetches its reset vector and executes from `$E000` with no
motherboard ROM; the disable bit frees `$E000`–`$FEFF` for RAM and the machine keeps
running; `$FF00`–`$FFBF` decodes to cards throughout; a module strapped for the CoCo 3
serves nothing and boots Color BASIC from the machine's own ROM exactly as in §6.3(a).

### Phase 7 — PCB and CoCo 3 integration (3–4 weeks)
40-pin DIP-footprint carrier: **G431CBU6 (UFQFPN48)**, 74LVC541 ×2 (address), 74LVC574
(data in, §3.6), 74LVC541 (data out), 74LVC541 (control in), 74LVC1G125 (`R/W` out),
74LVC2G04 (`/E`, `/R/W`), 3.3 V LDO, decoupling, SWD header. The §3.6 glue table is the
schematic; note in particular that `E` reaches the '574 clock through the inverter
**directly**, not via the control-input '541.
**Height-checked against the RF shield (§2.7)**, which now has one more package under it.
**Exit:** the §6.3 escalation ladder, through (e) — NitrOS-9 Level 2 in 6309 native mode,
booted from floppy on a real CoCo 3.

### Phase 8 — Polish and publish (1–2 weeks)
§6.3(f) cycle-timed video software. Emit test vectors in `ProcessorTests` JSON format and
contribute upstream.

**Rough total:** 11–15 weeks of focused hobby time.

---

## 8. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Lazy-CC materialisation missed on some path** | **High** | §4.1 rule 2 trades per-cycle cost for an obligation: every path that can observe CC must call `cc_materialise()`, incl. interrupt stacking. A miss is an accuracy bug, not a slow path. Make it a fuzzing invariant in §6.3(2), not a code-review item. |
| **Microstate sample is not a survey** | Medium | The probe covers ALU, indexed post-inc and `TFM`. Not covered: interrupt stacking, `DIVQ`/`DIVD`, indexed-indirect, `/HALT` entry/exit. Re-run the probe as each lands in Phase 3/4. |
| `/HALT` floppy path wrong or too slow | **High** | It gates NitrOS-9 boot. §2.2 is explicit; test at §6.3(c) before attempting a boot. |
| `t_DDW` = 70 ns and `t_PCS` = 70 ns at 3 MHz | Medium | Gates (§3.3) that no variant currently measures. Size the write path and the interrupt//HALT sampling path against them before Phase 6. |
| LVC574 setup/hold not verified for a specific part | Low | §3.6 uses typical LVC figures. Confirm against the chosen vendor's datasheet; margin is ~7–10× so this is a formality. |
| Native-mode cycle counts wrong | **High** | NitrOS-9 runs native, and MAME is known-buggy exactly there. Silicon capture (§6.2(1)) is the oracle. |
| **Interrupt recognition shifts by one bus cycle** | Medium | §4.1 rule 3 AND-folds the control inputs at an undefined instant in the cycle; silicon samples at a defined point with `t_PCS` setup. Never loses an assertion, can notice one a cycle early or late. Pin against the §6.2(1) silicon capture; a trace diff is the only thing that sees it. |
| Option bytes not programmed on a module | **High** | `BOOT0` = `PB8` = `A8`: a factory-default part boots the bootloader on a random subset of resets (§3.2). Gate in §7 Phase 6, verified by read-back, not by "it booted once". |
| §4.5 shadow ROM competes for microcode budget | Low | One range test per formed address, in the step measured by §3.3(d), not on the `t_AD` path. Re-run `cpu/tools/microstate-probe/` once it is written. |
| fast-E (3.1469 MHz) has no silicon reference | Medium | `t_cyc` 317.8 ns < the HD63C09E's 333 ns minimum, so §6.2(1)'s A/B capture cannot be taken there at all (§3.3(e)). Per D5 the machine is specified at 2.0979 MHz; fast-E is a probe and is validated against our own model only. |
| Mechanical fit under the RF shield | Medium | Measure in Phase 2; constrains component height and PCB stack-up. |
| CPU soldered, not socketed | Medium | Budget desoldering and a machined-pin socket. |
| Live clock switching breaks the loop | Medium | Purely edge-driven design (§2.1); explicitly tested in Phase 1. |
| No off-the-shelf test suite | Medium | RTL differential model + silicon rig (§6). Budget Phase 5 properly. |
| GIME setup/hold stricter than assumed | Medium | A/B logic-analyzer capture against a real 6309E in the same socket. |
| `TFM` interruptibility subtleties | Medium | Dedicated vectors from silicon capture. |
| Per-pin 5 V tolerance assumptions wrong | Medium | Verify FT/FT_a in DS12589 before PCB; LVC buffers regardless. |
| Flash wait states cause jitter | Low | Hot loop in CCM SRAM (zero-wait). |

---

## 9. Parts

- **STM32G431CBU6** (**UFQFPN48** — the LQFP48 does not bond out `PC4`/`PC6`/`PC10`/
  `PC11` and cannot carry the §3.2 pinout) ×2
- 74LVC541 ×2 (address), **74LVC574 ×1 (data in — the §3.6 latch)**,
  **74LVC541 ×1 (data out)**, **74LVC541 ×1 (the seven control inputs)**,
  **74LVC1G125 ×1 (`R/W` out, tri-stated by `BUS_OE`)**,
  **74LVC2G04 ×1 (`/E` for the '574 clock, `/R/W` for its `/OE`)**
  — the §3.6 drawing is the authority for the glue
- 3.3 V LDO, decoupling, 40-pin machined-pin header/socket
- Second MCU or signal generator for the Phase 1 E/Q stimulus, with runtime speed switching
- **HD63C09E ×2** — the A/B reference and the capture rig
- **A CoCo 3**, floppy controller, and a NitrOS-9 Level 2 boot disk
- Logic analyzer, ≥100 MS/s, ≥32 channels (16 address + 8 data + control)
- CoCo 3 service manual (schematics)

---

## 10. Open questions

1. *Answered* — the CoCo 3 leaves `BA`/`BS`/`BUSY`/`/LIC`/`AVMA` unconnected and
   grounds `TSC` (§2.6).
2. *Answered* — 48 pins, and specifically the **UFQFPN48**: LQFP48 bonds out only 38
   GPIO and drops `BA`/`BS`/UART (§3.2). The homebrew machine's MMU stays on the
   motherboard either way — it is the pin *budget*, not the package, that moved it
   there, and an in-CPU MMU is further out of reach on 35 pins than on 39
   (`docs/machine.md` §5 item 6).
3. *Answered* — `t_DSR` 40 ns (B grade) / **20 ns** (C grade), `t_DHR` 20 ns Hitachi /
   10 ns Motorola, `t_AD` **110 ns at both grades**
   (`reference/datasheets/HD6309E_datasheet.pdf` p.3; §3.3).
3c. *Answered in part* — 3 MHz is confirmed from Hitachi's own documents (`t_cyc` min
   333 ns; the non-E datasheet's crystal table specifies 12 MHz and 8 MHz AT-cut parts
   with the internal ÷4, giving the 3 MHz and 2 MHz grades). **5 MHz is unsupported by
   any datasheet** and is not a target — see the footnote in §3.3.
3d. *Answered* — yes, with the §4.1 rules: measured 14 cycles typical / 25 worst against
   34 available at 3 MHz (`cpu/tools/microstate-probe/`, §3.3(d)). The naive shape costs
   ~80 and misses at every rate, so the rules are a design constraint, not a tuning
   option.
3a. *Answered* — no. `PA0..PA7` and six of the address pins are `TT_a`, 3.6 V only
   (DS12589 Table 12, pp.52–53). Buffers are mandatory; direct drive is ruled out
   (§3.5).
3b. **What is the GIME's input `V_IH`?** Our buffers output 3.3 V. If the GIME wants
   CMOS levels (~3.5 V) that is marginal, and only a 5 V-powered translator fixes it.
   **Still open**, and probably only answerable by measurement on real hardware.
4. **Which CoCo 3 board revision**, and is the CPU socketed?
5. **Height available under the RF shield?**
6. **NitrOS-9 build** — Curtis Boyle's "Ease of Use" distribution, or a stock upstream
   build? Affects how much 6309-specific code is exercised.
7. **§4.5 machine gating: `PF1` strap, or a build-time flag and two images?** The strap
   keeps the "one firmware serves all three machines" property of §3.2 and spends the
   last spare pin; the flag keeps the pin and gives up the property. This document
   specifies the strap. **Owner's call**, and it wants making before the Phase 7 carrier
   is drawn, because the strap needs a pull-up on the drop-in carrier and a ground on the
   homebrew motherboard.
8. **§4.5 or the EPROM alternative?** D1 records both. Taking the EPROM restores
   `graphics.md` §16.8's real-6309-drop-in property for the homebrew machine and costs 2
   ICs plus an `$FF00`–`$FFBF` carve-out drawn in logic. Taking §4.5 costs ~8 KB of flash
   and a pin. Recorded here because the decision belongs to the machine, not to this
   module, and this module implements whichever wins.

---

## 11. References

- **HD63B09E / HD63C09E datasheet** — `reference/datasheets/HD6309E_datasheet.pdf`. **The authoritative
  bus-timing source for this project** (p.3, AC characteristics, both grades in adjacent
  columns). Supersedes `reference/datasheets/MC6809E.pdf` for everything in §3.3.
- STM32G431CB datasheet DS12589 Rev 6 — `reference/datasheets/stm32g431kb.pdf`. Table 45 (PLL
  characteristics, p.106) is the source for the §3.4(4) VCO ceiling; Table 12 (pp.52–53)
  for the `TT_a` 5 V-tolerance finding in §3.5.
  <https://www.st.com/resource/en/datasheet/stm32g431cb.pdf>
- **RM0440 Rev 9** — `reference/datasheets/stm32g4-refman.pdf`. §9.3.1 (GPIO `IDR` free-running),
  Table 2 §1.6 (no FSMC/QUADSPI on G431), §13.4.4–13.4.5 (DMAMUX sync/request generator).
  Sources for §3.4(6).
- **SAM D5x/E5x family datasheet** — `reference/datasheets/ATSAMD51G19A.pdf`. §52 (PCC), §32 (PORT behind
  the APB bridge), Table 54-5 (`fCPU` 120 MHz). Sources for §3.7.
- GPIO/package data verified against <https://github.com/modm-io/modm-devices> (`devices/stm32/stm32g4-31_41.xml`).
  **Caveat learned the hard way (§3.2):** that XML is a family pin list. It is not a
  per-package bonding table, and reading it as one is what put `BA`/`BS`/`UART` on pins
  the LQFP48 does not have. DS12589 Table 2 and the package pinout figures are the
  authority for which pads exist on which part number.
- MC6809E datasheet — `reference/datasheets/MC6809E.pdf`. Retained for the Motorola part actually in the
  CoCo 3 socket, and because its `t_DHR` (10 ns) is stricter than Hitachi's (20 ns).
  <https://www.bitsavers.org/components/motorola/_dataSheets/6809E.pdf>
- HD63C09 overclocking to 4 MHz (16 MHz crystal ÷ 4) — <https://digicoolthings.com/hd63c09-plcc-packaged-cpus-received-tested/>
- Darren Atkinson, *Motorola 6809 and Hitachi 6309 Programming Reference* — <https://colorcomputerarchive.com/repo/Documents/Books/Motorola%206809%20and%20Hitachi%206309%20Programming%20Reference%20(Darren%20Atkinson).pdf>
- HD63B09EP Technical Reference Guide — <https://colorcomputerarchive.com/repo/Documents/Microprocessors/HD6309/HD63B09EP%20Technical%20Reference%20Guide.pdf>
- Chris Lomont, *Color Computer 1/2/3 Hardware Programming* — <https://www.lomont.org/software/misc/coco/Lomont_CoCoHardware.pdf>
- Sock's GIME register reference — <https://www.6809.org.uk/sock/gime.html>
- CoCo `/HALT` floppy transfer mechanism — <https://www.kernelcrash.com/blog/os-9-and-nitros-9-on-the-color-computer-and-dragon/2023/02/25/>
- CoCo DMA / invisible RAM (bus timing notes) — <https://www.go4retro.com/2020/03/12/coco-dma-invisible-ram/>
- NitrOS-9 project — <https://sourceforge.net/p/nitros9/wiki/Main_Page/>
- NitrOS-9 "Ease of Use" — <https://www.lcurtisboyle.com/nitros9/nitros9.html>
- 6309 CoCo 3 upgrade experience report — <http://richg42.blogspot.com/2014/02/coco-3-upgrades-hitachi-6309-cpu-512kb.html>
- MCL6809, Teensy-based cycle-exact 6809E drop-in — <https://hackaday.io/project/196991-mcl6809-drop-in-motorola-6809e-emulator>
- TFR/9, real 6309E + Pi Pico peripherals (capture-rig blueprint) — <https://github.com/strickyak/tfr9>
- `cavnex/mc6809`, cycle-accurate Verilog 6809 — <https://github.com/cavnex/mc6809>
- `Nitrobotics/hd6309`, Verilog 6309 — <https://github.com/Nitrobotics/hd6309>
- MAME HD6309 core — <https://github.com/mamedev/mame/blob/master/src/devices/cpu/m6809/hd6309.cpp>
- MAME bug 09174, native-mode branch cycle counts — <https://mametesters.org/view.php?id=9174>
- `SingleStepTests/ProcessorTests` (no 6809/6309 set) — <https://github.com/SingleStepTests/ProcessorTests>
