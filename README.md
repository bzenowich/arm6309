# arm6309

A cycle-accurate **HD6309E** implemented on an **STM32G431CBT6**, packaged as a 40-pin
drop-in module for the **Tandy CoCo 3**, targeting a **NitrOS-9 Level 2** boot in 6309
native mode.

Full analysis, pinout rationale, timing budgets and phase plan: **[`docs/plan.md`](docs/plan.md)**.

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

The quarter-cycle column is **confirmed by Tandy's own documentation**: Color Computer 3
Service Manual Figure 5-3 gives E-fall to Q-rise as **279 ns at 0.89 MHz, 140 ns at
1.78 MHz**. At 170 MHz, 140 ns is 23.8 core cycles.

The "estimated need" column is still a prediction from `docs/plan.md` §3.3. Phase 1
replaces it with measurements.

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

## The data sampling problem

Worth understanding before trusting any result, and the reason
`spike_characterise_data_window()` exists.

The 6809E guarantees read data is valid only in a narrow window around E's fall —
roughly `[E_fall − t_DSR, E_fall + t_DHR]`. `t_DSR` (setup) and `t_DHR` (hold) are on the
order of **40 ns and 10 ns**.

> ⚠️ **Those two numbers are from memory and remain unverified — this is the project's
> most important open item** (`docs/plan.md` §10.3). The CoCo 3 service manual's
> Figure 5-3 shows the *shape* of the read-data window but gives no setup/hold figures;
> they come from the Motorola/Hitachi datasheet, and they differ between the 1 MHz and
> 2 MHz parts. Confirm before relying on any of what follows.

If the hold really is ~10 ns, that is **1.7 core cycles** at 170 MHz. A polling loop with
~5-cycle iterations cannot reliably land inside it. So `spike_poll.c` instead uses the
**last sample taken while E was still high** (`s_prev`), which should fall inside the
setup window:

```c
do { s_prev = s_cur; s_cur = GPIOA->IDR; } while (s_cur & MASK_E);
/* s_cur saw E low  -> 0..1 iterations AFTER the edge, maybe past hold
 * s_prev was taken -> while E was still high, inside setup            */
```

But `s_prev` is roughly 30–70 ns before the edge, and a 40 ns setup guarantee does not
cover the far end of that. **Strictly by datasheet minimums, neither sample is
guaranteed.** In practice real hosts hold data far longer than the minimum — the bus
does not change until the CPU drives the next address — but "in practice" is not a
foundation for a cycle-accurate part.

Hence `spike_characterise_data_window()`: it measures how long the *actual* host holds
data past E's fall. Run it on the real CoCo 3 before trusting anything downstream.

**If the real window turns out too narrow**, the fallback is hardware sampling: a DMA
read of `GPIOA->IDR` triggered by EXTI on E's fall (or on Q's fall, a quarter cycle
earlier), giving a deterministic sample offset instead of polling jitter. `PA9` is
`TIM1_CH2`, so Q is already captured in hardware for exactly this.

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

Needs `arm-none-eabi-gcc` (**not currently installed in this environment**):

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
print g_result
print g_data_window
```

Key fields in `g_result`:

| Field | Meaning |
|---|---|
| `deadline_misses` | latency exceeded a quarter period. **Must be 0.** |
| `overruns` | TIM1 overcapture — a whole E cycle went unserviced. Must be 0. |
| `lat_worst` | worst-case core cycles, hardware E-fall → address stored. **The number.** |
| `period_min`/`period_max` | differ ⇒ the host switched speed mid-run (that's the point) |
| `hist[]` | latency distribution, 1 core cycle per bin |

`lat_worst` is the result. Compare it against the quarter-cycle column in the table
above. Worst case only — an emulator that misses one deadline in 10⁴ is simply wrong.

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
src/spike_poll.c          variant 1: polling loop (the measurement)
src/main.c                entry point; results land in globals for gdb
linker/stm32g431cb.ld     128K flash / 22K SRAM / 10K CCM, with the .ccmram section
test/test_stub_core.c     host unit test for the stub table
tools/stimulus/           requirements for the E/Q generator
```

---

## Phase 1 TODO

- [x] Variant 1 — polling loop in C (predicted ceiling ~2 MHz)
- [x] Confirm the CoCo 3 pin budget against the service manual (§2.6 — six signals freed)
- [ ] **Verify `t_DSR` / `t_DHR` against the datasheet** — see "data sampling problem"
- [ ] Debug console on `USART3` (`PC10`/`PC11`), so results don't need a debugger
- [ ] Variant 2 — hand-written assembly (predicted ~2.5 MHz)
- [ ] Variant 3 — EXTI + DMAMUX + DMA precomputed store (predicted ~3–3.5 MHz)
- [ ] Variant 4 — overclock to 180–200 MHz
- [ ] Build the stimulus generator
- [ ] First silicon measurement; record actuals against predictions in `docs/plan.md` §5

Predictions are recorded deliberately. A wrong one is informative.
