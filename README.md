# arm6309

A cycle-accurate **HD6309E** implemented on an **STM32G431CBT6**, packaged as a 40-pin
drop-in module for the **Tandy CoCo 3**, targeting a **NitrOS-9 Level 2** boot in 6309
native mode.

Full analysis, pinout rationale, timing budgets and phase plan: **[`docs/plan.md`](docs/plan.md)**.

> ⚠ **This README's timing numbers are superseded (2026-08-27).** They were derived from
> `docs/MC6809E.pdf`, whose columns stop at the 2 MHz MC68B09E. The real
> HD63B09E/HD63C09E figures are now in `docs/HD6309E_datasheet.pdf` and analysed in
> [`docs/plan.md`](docs/plan.md) §3.3. Two things changed that matter here:
> **`t_AD` is 110 ns at *both* speed grades** (the address deadline does not tighten at
> 3 MHz), and **`t_DSR` halves to 20 ns at 3 MHz** (3.4 core cycles), which puts read-data
> sampling below the floor for *any* software polling loop on this part. The fix is an
> external 74LVC574 latch — `plan.md` §3.6. Sections below that quote `t_DSR` = 40 ns,
> `t_DHR` = 10 ns or a `T_iter ≤ 6` gate are correct **only for the 1.79 MHz target**.

**Current state: Phase 1 — the timing spike.** No 6309 emulation exists yet, by design.
Phase 1 answers the one question that can invalidate the project before any core is
written: *after the host drops E, can we get the next address onto the bus inside a
quarter cycle?*

---

## The question Phase 1 answers

A 6809E bus cycle runs from one E falling edge to the next. Read data is latched at E's
fall, and the **next address must be valid before Q rises** — one quarter cycle later.

| E rate | Core cycles/bus cycle | Quarter cycle | Estimated need | Verdict |
|---|---|---|---|---|
| 0.895 MHz (CoCo 3 boot) | 190 | **47.5** | 9–14 | comfortable |
| 1.79 MHz (CoCo 3 fast) | 95 | **23.7** | 9–14 | **target** |
| 3.0 MHz (63C09E max) | 57 | 14.2 | 9–14 | marginal |
| 5.0 MHz | 34 | 8.5 | 9–14 | below the floor |

> **The table above is superseded.** The deadline is not the quarter cycle. Per the
> MC6809E datasheet (`docs/MC6809E.pdf` p.3, item 11), *Address Delay Time from E Low*
> `t_AD` is **110 ns max** for the MC68B09E — an **absolute** figure, not a fraction of
> the E period, so it is identical at 0.895 and 1.79 MHz.

**The real requirement: drive the next address in the window [3.4, 18.7] core cycles
after E falls.**

| Parameter | Symbol | Value | Core cycles @170 MHz |
|---|---|---|---|
| Address delay from E low | `t_AD` | ≤ 110 ns | **18.7** ← ceiling |
| Address hold time | `t_AH` | ≥ 20 ns | **3.4** ← floor |
| Read data setup | `t_DSR` | ≥ 40 ns | 6.8 |
| Read data hold | `t_DHR` | ≥ 10 ns | 1.7 |

Both ends bind — driving too early violates the hold time on the outgoing address.
Against an estimated 9–14 cycle critical path, the margin is **5–10 cycles**. Phase 1
replaces the estimate with measurement.

**Gate: zero deadline misses at 1.79 MHz, including across a live 0.895 ↔ 1.79 MHz
switch.** If that fails, stop and reconsider the MCU before writing the core.

---

## How the measurement works

The spike runs the *shape* of the real bus loop with a **stub** state machine — a
256-entry table indexed by the data byte, reproducing the one structural property that
sets the ceiling: **the next address depends on the byte just read**, so the lookup
cannot be hoisted out of the critical path.

Two things make the numbers trustworthy:

- **The hot loop runs from CCM SRAM** (zero wait states). Flash is 4 wait states at
  170 MHz and would make every result meaningless.
- **E is timestamped in hardware.** `PA8` is `TIM1_CH1` (AF6), so TIM1 captures the E
  falling edge in hardware while `GPIOA->IDR` still reads the same pin for polling.
  Latency is measured from the **hardware edge**, not from when software noticed it —
  and that difference *is* the polling jitter, the term expected to dominate at high E
  rates. Measuring from a software timestamp would hide exactly what we care about.

TIM1 runs at 170 MHz with no prescaler, so **one timer tick = one core cycle**.

---

## Where the emulator's time comes from

The CPU has to be *inside* the tight sampling loop when E falls, and work interleaved
between samples would breach `T_iter`. So every cycle spent waiting for the edge is dead
time, and **which signal you wait on decides how much of the bus cycle the emulator gets.**

At 1.79 MHz (period 559 ns = 95 core cycles; E is 315 ns low / 244 ns high):

| Wait on | Usable by the emulator | Spent sampling |
|---|---|---|
| the **E pin** — spin for it to rise, then sample | 53.5 cycles (56%) | 41.5 |
| the **Q-fall capture flag** (`TIM1_CH2`) | **71.3 cycles (75%)** | **23.8** |

Q falls at 0.75 of the cycle, so its capture flag means "one quarter period to the edge".
The loop does its work first and only then enters tight sampling. **+33% usable budget for
one flag test**, and because it anchors on a hardware event rather than a predicted time,
it survives the live 0.895 ↔ 1.79 MHz switch — a faster clock just means Q falls sooner
and the flag is already set.

`slack_min` reports what is actually left over; `slack_late` counts cycles where the work
overran and Q had already fallen.

## The data sampling problem

Worth understanding before trusting any result, and the reason
`spike_characterise_data_window()` exists.

**Now resolved, and provably so.** The MC6809E datasheet (`docs/MC6809E.pdf` p.3) gives,
for the MC68B09E: `t_DSR` = **40 ns** (item 17) and `t_DHR` = **10 ns** (item 18). Read
data is guaranteed valid over `[E_fall − 40 ns, E_fall + 10 ns]` — a **50 ns window**.

A 10 ns hold is **1.7 core cycles** — no polling loop can reliably sample *after* the
edge. So `spike_poll.c` samples continuously while E is high and keeps the **last sample
taken before E fell**:

```c
do { s_prev = s_cur; s_cur = GPIOA->IDR; } while (s_cur & MASK_E);
/* s_cur  saw E low -> 0..1 iterations AFTER the edge, past the 10 ns hold
 * s_prev was taken -> while E was still high, i.e. before the edge       */
```

If the loop's iteration period is `T_iter`, then `s_prev` lands in
`[E_fall − T_iter, E_fall)`. Which gives a clean correctness condition:

> **`T_iter ≤ t_DSR` = 40 ns = 6.8 core cycles ⟹ `s_prev` is provably inside the
> guaranteed valid window.**

**This is why variant 2 exists.** The natural C loop needs a register copy to retain the
previous sample, which costs 7 cycles per iteration — **over budget**, making its
sampling unsound no matter how good its latency looks:

```
mov r7, r6      1     prev = cur
ldr r6, [r0]    2     cur  = IDR
tst r6, #E      1
bne .-          3     taken branch, pipeline refill      = 7
```

`src/spike_poll_asm.S` unrolls by two and alternates destination registers, removing the
copy and paying the taken branch once per two samples. Verified against the actual
disassembly: **sample gaps of 4 and 6 cycles**, so `T_iter` worst case is 6 = 35.3 ns,
inside the 40 ns bound with ~5 ns spare.

**`lat_jitter`** (`lat_worst − lat_best`) measures `T_iter` on hardware: where the edge
lands within the poll loop is the only term that varies between bus cycles.

`spike_characterise_data_window()` remains useful as a cross-check — it measures how
long the *actual* host holds data past E's fall, which is typically far longer than the
10 ns minimum.

**If `T_iter` measures above 6 cycles**, the fallback is hardware sampling: a DMA read of
`GPIOA->IDR` triggered by EXTI on E's fall, giving a deterministic offset instead of
polling jitter. `PA9` is `TIM1_CH2`, so Q is already captured in hardware for exactly
this.

---

## Building

### Host checks — no cross toolchain needed

Syntax-checks every target source and unit-tests the pure-logic parts.

```sh
cmake -B build-host -G Ninja
cmake --build build-host
ctest --test-dir build-host --output-on-failure
```

### Firmware

Needs `arm-none-eabi-gcc` (13.2.1 verified; `build-arm/spike.elf` links at 3,968 B text):

```sh
# Debian/Ubuntu
sudo apt install gcc-arm-none-eabi
# or the ARM GNU toolchain from developer.arm.com, then:
#   cmake -B build-arm -DCMAKE_TOOLCHAIN_FILE=cmake/arm-none-eabi.cmake \
#         -DTOOLCHAIN_PREFIX=/path/to/arm-none-eabi-

cmake -B build-arm -DCMAKE_TOOLCHAIN_FILE=cmake/arm-none-eabi.cmake -G Ninja
cmake --build build-arm
```

Produces `build-arm/spike.elf`, `.bin`, `.hex` and a link map.

> The firmware has **not been compile-verified** — there is no ARM toolchain in this
> environment. Host syntax checks pass with `-Wall -Wextra -Wshadow -Wundef
> -Wconversion`, but expect to shake out linker-script and startup issues on first build.

---

## Running the measurement

1. Wire the stimulus generator to E, Q and D0–D7 — see
   [`tools/stimulus/README.md`](tools/stimulus/README.md).
2. Flash `spike.elf` (`openocd`, `st-flash`, `probe-rs`, or a ST-Link GUI).
3. The firmware runs the characterisation sweep, then one million bus cycles, then hits
   a `bkpt`.
4. Read results over SWD. (A debug UART is available on `PC10`/`PC11` — `USART3` — since
   the CoCo 3 leaves `BUSY`/`/LIC`/`AVMA` unconnected and frees those pins; wiring it up
   is a TODO below.)

```gdb
target extended-remote localhost:3333
print/x g_run_complete          # expect 0x6309c0de
print g_result_c                # variant 1, C
print g_result_asm              # variant 2, assembly
print g_result_dma              # variant 3, DMA-driven
print g_data_window
```

Variant 1 is expected to **fail** the `lat_jitter` ≤ 6 gate — that is the measurement,
not a defect. Variant 2 is the one that should pass both gates.

For variant 3, **check `dma_timeouts` before reading anything else**: non-zero means the
DMA never fired. The register constants are verified against RM0440 Rev 9, so a timeout
points at wiring or a clock enable rather than a wrong bit position.

### What variant 3 does and does not buy

It offloads the **address drive** to hardware — no CPU in the path at all. It does **not**
help with **data sampling**, which is the constraint people expect DMA to solve: a DMA
read triggered by the E edge lands past `t_DHR` (10 ns), and one triggered by Q's fall
lands before `t_DSR` (40 ns). Neither is sound, so variant 3 still needs a polling loop
for data and **`T_iter` ≤ 6 still applies**.

It also requires the address to be known a **full bus cycle ahead**. That holds for
instruction-fetch runs, VMA cycles and stack operations, but never for genuinely
data-dependent cycles. So it measures a floor for part of the workload, not a replacement
for variant 2.

The number it produces decides whether the pipelined architecture (`docs/plan.md` §4.2)
is worth building. If DMA latency lands well under variant 2's ~13 cycles, pipelineable
cycles can be driven by hardware and the CPU spends its whole slack on emulation. **If it
lands near or above 13 — which is entirely plausible, since triggered DMA on STM32 is
often 10–25 cycles — the complexity buys nothing and variant 2 is the answer.**

Measurement caveat: the readback spin samples every 4 core cycles, so the result is
quantised to 4 and biased high by roughly another 3 for the exit branch. Good enough to
separate 13 from 18; not good enough to trust the last cycle. For a precise figure,
jumper an address line to a spare timer capture input and difference two hardware
timestamps.

Key fields in `g_result`:

| Field | Meaning |
|---|---|
| `deadline_misses` | latency > `t_AD` (18 cycles). **Must be 0.** |
| `hold_violations` | latency < `t_AH` (4 cycles) — drove the address too early. Must be 0. |
| `overruns` | TIM1 overcapture — a whole E cycle went unserviced. Must be 0. |
| `lat_worst` | worst-case core cycles, hardware E-fall → address stored. **The number.** |
| `lat_jitter` | `lat_worst − lat_best` ≈ `T_iter`. **Must be ≤ 6** (see above). |
| `period_min`/`period_max` | differ ⇒ the host switched speed mid-run (that's the point) |
| `slack_min` | worst-case spare cycles for the emulator. **Size the microcode step against this.** |
| `slack_late` | work overran the budget and Q had already fallen. Must be 0. |
| `hist[]` | latency distribution, 1 core cycle per bin |

Two independent gates: **`lat_worst` ≤ 18** (the address arrives in time) and
**`lat_jitter` ≤ 6** (the data sample is provably valid). Both are worst-case, not
average — an emulator that misses one deadline in 10⁴ is simply wrong.

The measurement is slightly **conservative**: a `DSB` before the timestamp ensures the
GPIO store has actually landed, which costs a couple of cycles. That errs in the safe
direction.

---

## Layout

```
docs/plan.md              full feasibility analysis and phase plan
include/pinout.h          pin assignment — single source of truth, mirrors plan §3.2
include/stm32g431.h       minimal hand-rolled registers (no CMSIS/HAL dependency)
include/spike.h           measurement API and result struct
src/startup.c             vector table, .data/.ccmram copy, .bss zero
src/clock.c               170 MHz via HSI16+PLL, incl. boost mode + AHB/2 gotchas
src/gpio.c                pinout config, TIM1 input capture on E and Q
src/stub_core.c           256-entry stub state table
src/spike_poll.c          variant 1: polling loop in C, plus the variant 2 wrapper
src/spike_poll_asm.S      variant 2: hand-written Thumb-2 polling loop
src/spike_dma.c           variant 3: DMA drives the address, no CPU in the path
src/main.c                entry point; results land in globals for gdb
linker/stm32g431cb.ld     128K flash / 22K SRAM / 10K CCM, with the .ccmram section
test/test_stub_core.c     host unit test for the stub table
tools/stimulus/           requirements for the E/Q generator
```

---

## Phase 1 TODO

- [x] Variant 1 — polling loop in C (predicted ceiling ~2 MHz)
- [x] Variant 2 — hand-written assembly (`src/spike_poll_asm.S`), `T_iter` 4/6 cycles
- [x] Variant 3 — DMA-driven address (`src/spike_dma.c`)
- [x] Verify the DMAMUX/EXTI constants against RM0440 Rev 9 — all confirmed correct
- [x] Confirm the CoCo 3 pin budget against the service manual (§2.6 — six signals freed)
- [x] Verify `t_DSR` / `t_DHR` against the datasheet — 40 ns / 10 ns; deadline corrected
      from the quarter cycle to `t_AD` = 110 ns
- [x] Firmware compiles (`arm-none-eabi-gcc` 13.2.1); hot loop confirmed at `0x10000000`
- [x] Decide direct-drive vs buffers — **buffers, mandatory**: `PA0..PA7`, `PB0..PB2`
      and `PB10` are `TT_a` (3.6 V), and the CoCo drives 5 V TTL at the data bus on
      every read
- [ ] Confirm the GIME accepts 3.3 V `V_OH` — buffers output 3.3 V, not 5 V
- [ ] Debug console on `USART3` (`PC10`/`PC11`), so results don't need a debugger
- [ ] Variant 2 — hand-written assembly (predicted ~2.5 MHz)
- [ ] Variant 3 — EXTI + DMAMUX + DMA precomputed store (predicted ~3–3.5 MHz)
- [x] ~~Variant 4 — overclock to 180–200 MHz~~ — **dropped.** Core clock committed at
      170 MHz, in spec; see `docs/plan.md` §3.4(4). It moved no gate from fail to pass,
      and 344 MHz is the PLL VCO ceiling (any SYSCLK > 172 MHz overclocks the PLL too).
- [ ] Variant 5 — straight-line unrolled poll, uniform `T_iter` = 4 (`plan.md` §3.3(c))
- [ ] Variant 6 — external 74LVC574 read-data latch (`plan.md` §3.6) — decides 3 MHz
- [ ] Build the stimulus generator
- [ ] First silicon measurement; record actuals against predictions in `docs/plan.md` §5

Predictions are recorded deliberately. A wrong one is informative.
