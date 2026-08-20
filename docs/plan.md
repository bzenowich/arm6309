# arm6309 — A Cycle-Accurate HD6309E on STM32G431CB

**Primary goal:** a 40-pin drop-in module that replaces the MC68B09E in a **Tandy CoCo 3**
and boots **NitrOS-9 Level 2 in 6309 native mode**.

**Status:** planning — Phase 0 decisions locked
**Date:** 2026-08-19

---

## 0. Decisions

| Decision | Choice | Consequence |
|---|---|---|
| **MCU** | **STM32G431CBT6** (LQFP48, 42 GPIO, 170 MHz) | Pin budget closes — just barely (§3.2). Full `PA0-15` + `PB0-15` ports. |
| **Socket** | **HD6309E** — E and Q are **inputs** | Matches the CoCo 3. Clock-slaved, no stretching. |
| **Primary target** | **CoCo 3 @ 0.895 **and** 1.79 MHz**, switchable at runtime | **Feasible with ~10–15 core cycles of margin.** See §3.3. |
| **Stretch probe** | 5 MHz on boards you design | Predicted to miss by ~1.5–2×; measured in Phase 1, not assumed. |
| **Accuracy** | **L2 + mandatory `/HALT`/`BA`/`BS`** | `/HALT` is not optional on a CoCo — it is how the floppy transfers data (§2.2). |
| **Method** | Measure the ceiling first, back off as forced | Drives phase ordering in §7. |

**Success criterion:** *boots NitrOS-9 Level 2 (6309 native) from floppy on a real CoCo 3,
and a logic-analyzer capture matches a real HD63C09E in the same socket.*

---

## 1. Executive summary

**The CoCo 3 target is achievable. The 5 MHz probe is not, and that's fine.**

The CoCo 3's GIME clocks the CPU at **0.895 MHz**, switchable at runtime to **1.79 MHz**
via the SAM speed bits at `$FFD8`/`$FFD9` (`POKE 65497,0`). The stock part is an MC68B09E
rated 2 MHz.

At 1.79 MHz a bus cycle is **95 core cycles** at 170 MHz, and the binding deadline — the
post-read critical path — is a **quarter cycle, 23.7 core cycles**. The estimated floor
for that path is **9–14 core cycles**. That leaves **~10–15 cycles of margin**, and ~3–6×
headroom on average throughput. This is a comfortable fit, not a heroic one.

The earlier 5 MHz target would have given only 8.5 core cycles against the same 9–14
cycle floor. It remains in the plan as a Phase 1 measurement — worth knowing where the
wall actually is — but it is explicitly not the deliverable.

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

### 2.6 Signals the CoCo 3 does not use — **ANSWERED**

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
| GPIO (LQFP48) | **42** — `PA0-15`, `PB0-15`, `PC4/6/10/11/13/14/15`, `PF0/1`, `PG10` |

Both `PA` and `PB` are full contiguous 16-bit ports — the whole reason this package works.
The address bus is one 32-bit store; the data bus is one byte-aligned load.

### 3.2 Pin budget and pinout

Available: 42, minus `PA13`/`PA14` (SWD, keep for bring-up) and `PG10` (NRST) = **39**.

| Group | Count | Running total |
|---|---|---|
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

**LQFP48 is now comfortable and the LQFP64 question is closed.** The earlier
zero-slack concern was based on assuming every 6309E signal needed wiring; §2.6 removed
six of them.

Drive-strength constraint works out cleanly: `PC13`/`PC14`/`PC15` are backup-domain pins
with limited output drive, so they are input-only here — and they carry `/NMI`, `/IRQ`,
`/FIRQ`, which are inputs anyway.

Two pin-saving tricks, both worth taking:

- **Tie the '245 `DIR` to the buffered `R/W` in hardware.** That is literally what `R/W`
  means; no GPIO needed.
- **One shared `BUS_OE`** for the address '541s, the data '245, and the `R/W` buffer — all
  three float together and only together, during `/HALT`.

```
PB0..PB15   A0..A15      out    one 32-bit store to GPIOB->ODR
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
PF1         --                  spare
PG10        NRST
```

Totals: 20 outputs (`A0-15`, `R/W`, `BUS_OE`, `BA`, `BS`), 8 bidirectional (`D0-7`),
8 inputs (`E`, `Q`, `/RESET`, `/HALT`, `/NMI`, `/IRQ`, `/FIRQ`, `UART_RX`), plus
`UART_TX` and `LED`. **38 of 39, one spare.**

`BUSY`, `/LIC`, `AVMA` and `TSC` are deliberately absent — §2.6 confirmed the CoCo 3
does not connect them. Adding them later costs the UART and the LED, which is the wrong
trade for this target.

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

**Confirmed against Tandy's own numbers.** Service manual Figure 5-3, "MC68B09E
Read/Write Timing at 0.89 MHz" (parenthesised values are for 1.78 MHz), gives E period
**1117 ns (559 ns)** and **E-fall to Q-rise 279 ns (140 ns)**. That E-fall-to-Q-rise
figure *is* the address deadline, and 140 ns at 170 MHz is **23.8 core cycles** — the
estimate below was 23.7. The budget is right.

| E rate | Period | Core cycles/bus cycle | **Quarter cycle (the deadline)** | Verdict |
|---|---|---|---|---|
| **0.895 MHz** (CoCo 3 boot) | 1118 ns | 190.0 | **47.5** | very comfortable |
| **1.79 MHz** (CoCo 3 fast) | 559 ns | 95.0 | **23.7** | **target — fits with margin** |
| 2.0 MHz (68B09E max) | 500 ns | 85.0 | 21.3 | fits |
| 3.0 MHz (63C09E max) | 333 ns | 56.7 | 14.2 | marginal |
| 4.0 MHz | 250 ns | 42.5 | 10.6 | unlikely |
| 5.0 MHz (stretch probe) | 200 ns | 34.0 | **8.5** | **below the floor** |

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

- **At 1.79 MHz: 23.7 available vs 9–14 needed → ~10–15 cycles of margin.** Workable.
- **At 5 MHz: 8.5 available vs 9–14 needed → misses outright.** Polling jitter alone
  (4–6 cycles) eats more than half the budget.

**Average throughput** is the second constraint. A microcoded core step costs ~15–30 core
cycles typical, ~50–60 worst case. At 1.79 MHz there are 95 core cycles per bus cycle —
**~3–6× headroom**. At 5 MHz there are 34, leaving no slack even on average.

### 3.4 Ways to buy headroom (mostly insurance at 1.79 MHz)

1. **Hand-written assembly on the hot path**, hot loop in **CCM SRAM** (zero-wait — flash
   is 4 WS at 170 MHz), interrupts disabled inside the bus loop, loop aligned. Do this
   regardless of target rate.
2. **Exploit the 6809's own dead cycles.** The real CPU inserts VMA cycles precisely where
   it needs settling time, notably in indexed addressing. Where a VMA cycle sits between
   the last operand byte and the data access, the emulator inherits a full extra cycle.
   Quantify in Phase 3 rather than assuming.
3. **Hardware-assisted edge response.** STM32G4's DMAMUX can trigger DMA from an EXTI line:
   E-fall → EXTI → DMA writes a *precomputed* word to `GPIOB->ODR`, removing polling
   jitter. Helps every cycle whose address does not depend on the immediately preceding
   read. Does not rescue the data-dependent cycles that set the ceiling — so it is a
   route to 3 MHz, not to 5.
4. **Overclock the G4.** Rated 170 MHz; many parts run 180–200. Buys ~15%. Not something
   to design around, and not needed for the CoCo 3.
5. **Escape hatch: a faster MCU.** The core is portable C11 (§4.4), so an STM32H723 at
   550 MHz makes 5 MHz straightforward. Reserve, not plan.

### 3.5 Electrical

- The CoCo 3 is 5 V; the G4 is 3.3 V. **Verify FT/FT_a tolerance per pin in DS12589 before
  the PCB** — not all G4 pins are 5 V-tolerant.
- Driving 5 V logic from 3.3 V: fine for LS/ALS/HCT (V_IH = 2.0 V), **not** plain HC
  (V_IH = 3.5 V). Check what the CoCo 3 actually uses on each bus.
- **74LVC245** on the data bus (`DIR` ← buffered `R/W`), **74LVC541 ×2** on the address bus,
  plus a buffer for `R/W` — all with `OE` ← `BUS_OE` for `/HALT` tri-stating. ~5 ns each,
  already in the §3.3 budget.
- **74LVC specifically, not 74HC/74AHC.** §2.6 found 4.7 K pull-ups to 5 V on all 16
  address lines and 47 K on `R/W`. When we tri-state under `/HALT`, those pull-ups drag
  the lines to 5 V while our buffer outputs are high-Z — which is only safe on a family
  with no clamp diode to V_CC. 74LVC is rated for 5.5 V on its I/O regardless of V_CC;
  74HC/AHC would clamp and conduct. When actively driving high, the LVC output
  (~10–25 Ω) easily wins against a 4.7 K pull-up and the line sits near 3.3 V, which is
  comfortably above the 2.0 V V_IH of the LS parts downstream.
- The module draws power from the socket's 5 V; include a 3.3 V LDO and proper decoupling.
- Clock: HSI16 + PLL to 170 MHz. No crystal — we are slaved to the GIME's E/Q.

---

## 4. Software architecture

### 4.1 Microcoded core, one state per bus cycle

Not a `switch (opcode)` interpreter. An explicit state machine where **every state emits
exactly one bus cycle**:

```c
typedef struct microstate {
    uint16_t (*addr)(cpu_t *);      /* address to drive this cycle       */
    uint8_t   rw;                   /* read or write                     */
    void    (*action)(cpu_t *);     /* register/ALU work for this cycle  */
    const struct microstate *next;  /* successor (may be patched)        */
} microstate_t;
```

Forced by §3.3, not chosen for elegance:

- The post-read path collapses to an indexed table lookup — the only shape that fits in a
  quarter cycle.
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
- Deadline misses detected in-loop with the **DWT cycle counter**: timestamp E-fall,
  timestamp address-store, flag any cycle exceeding the quarter-cycle budget.
- **Worst case, not average.** An emulator that misses one deadline in 10⁴ is simply wrong.
- Sweep E upward until misses appear. That frequency is the real ceiling.

**Variants**, since the difference between them is the engineering question:
1. Software polling loop, C.
2. Software polling loop, hand-written assembly.
3. EXTI + DMAMUX + DMA precomputed store (§3.4(3)).
4. (2) or (3) with the G4 overclocked to 180–200 MHz.

**Exit criteria:**
- **Hard gate: zero deadline misses at 1.79 MHz**, including across a live speed switch.
- Measured max-E-frequency per variant, recorded.

**Predictions on record** (worth checking honestly — a wrong prediction here is
informative):
variant 1 ≈ 2 MHz · variant 2 ≈ 2.5 MHz · variant 3 ≈ 3–3.5 MHz.
**1.79 MHz should pass on variant 1 or 2 with room to spare.** If it does not, stop and
reconsider the MCU before writing a single instruction of the core.

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
**Exit:** zero deadline misses at 1.79 MHz including a live speed switch; ceiling measured
per variant.

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
**Exit:** worst-case DWT within budget at 1.79 MHz with ≥20% margin. Confirm the real core
did not blow the Phase 1 numbers.

### Phase 7 — PCB and CoCo 3 integration (3–4 weeks)
40-pin DIP-footprint carrier: G431CB, 74LVC541 ×2, 74LVC245, `R/W` buffer, 3.3 V LDO,
decoupling, SWD header. **Height-checked against the RF shield (§2.7).**
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
| `/HALT` floppy path wrong or too slow | **High** | It gates NitrOS-9 boot. §2.2 is explicit; test at §6.3(c) before attempting a boot. |
| Native-mode cycle counts wrong | **High** | NitrOS-9 runs native, and MAME is known-buggy exactly there. Silicon capture (§6.2(1)) is the oracle. |
| ~~Pin budget has zero slack~~ | **Closed** | §2.6 confirmed six signals are unconnected on the CoCo 3. 35 of 39 used for the bus, leaving a debug UART, an LED and a spare. LQFP48 stands. |
| Mechanical fit under the RF shield | Medium | Measure in Phase 2; constrains component height and PCB stack-up. |
| CPU soldered, not socketed | Medium | Budget desoldering and a machined-pin socket. |
| Live clock switching breaks the loop | Medium | Purely edge-driven design (§2.1); explicitly tested in Phase 1. |
| No off-the-shelf test suite | Medium | RTL differential model + silicon rig (§6). Budget Phase 5 properly. |
| GIME setup/hold stricter than assumed | Medium | A/B logic-analyzer capture against a real 6309E in the same socket. |
| `TFM` interruptibility subtleties | Medium | Dedicated vectors from silicon capture. |
| Per-pin 5 V tolerance assumptions wrong | Medium | Verify FT/FT_a in DS12589 before PCB; LVC buffers regardless. |
| 5 MHz stretch unreachable | Low / expected | Not the deliverable. Measured in Phase 1 for information. |
| Flash wait states cause jitter | Low | Hot loop in CCM SRAM (zero-wait). |

---

## 9. Parts

- **STM32G431CBT6** (LQFP48) ×2
- 74LVC541 ×2 (address), 74LVC245 ×1 (data), 74LVC125/AHCT125 (`R/W` + control)
- 3.3 V LDO, decoupling, 40-pin machined-pin header/socket
- Second MCU or signal generator for the Phase 1 E/Q stimulus, with runtime speed switching
- **HD63C09E ×2** — the A/B reference and the capture rig
- **A CoCo 3**, floppy controller, and a NitrOS-9 Level 2 boot disk
- Logic analyzer, ≥100 MS/s, ≥32 channels (16 address + 8 data + control)
- CoCo 3 service manual (schematics)

---

## 10. Open questions

1. ~~Does the CoCo 3 connect `TSC`/`/LIC`/`AVMA`/`BUSY`/`BA`/`BS`?~~ **Answered** — see
   §2.6. All five outputs NC, `TSC` grounded.
2. ~~LQFP48 or LQFP64?~~ **Answered** — LQFP48, with 4 pins to spare.
3. **What are `t_DSR` and `t_DHR` for the 68B09E / HD63C09E?** The read-data setup and
   hold window around E's fall. The service manual's Figure 5-3 shows the shape but not
   the numbers; they come from the Motorola/Hitachi datasheet. This is the **most
   important open item** — the entire data-sampling strategy depends on it. See the
   README's "data sampling problem".
4. **Which CoCo 3 board revision**, and is the CPU socketed?
5. **Height available under the RF shield?**
6. **NitrOS-9 build** — Curtis Boyle's "Ease of Use" distribution, or a stock upstream
   build? Affects how much 6309-specific code is exercised.

---

## 11. References

- STM32G431CB datasheet DS12589 — <https://www.st.com/resource/en/datasheet/stm32g431cb.pdf>
- GPIO/package data verified against <https://github.com/modm-io/modm-devices> (`devices/stm32/stm32g4-31_41.xml`)
- MC6809E datasheet — <https://www.bitsavers.org/components/motorola/_dataSheets/6809E.pdf>
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
