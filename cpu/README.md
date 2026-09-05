# `cpu/` — the HD6309E module

A cycle-accurate **HD6309E** implemented on an **STM32G431CBU6 (UFQFPN48)**, packaged as a
40-pin drop-in module for the **Tandy CoCo 3**, targeting a **NitrOS-9 Level 2** boot in
6309 native mode. In the machine of [`docs/machine.md`](../docs/machine.md) this is the
CPU — and **it does not carry the MMU**: that sits on the motherboard, which is what lets
one 48-pin part serve both machines. See `docs/machine.md` §5 item 6 and
[`video/docs/graphics.md`](../video/docs/graphics.md) §6.3.1, and `docs/plan.md` §3.2 for
the pin budget that decided it.

> ⚠ **The package changed on 2026-09-04, and the old one could not have worked.** This
> README and the plan committed to the **STM32G431CB*T*6, LQFP48** and to "42 GPIO" on it.
> DS12589 Table 2 gives **38 GPIO in LQFP48, 42 in UFQFPN48**, and the four missing pads
> are exactly `PC4`, `PC6`, `PC10`, `PC11` — `BA`, `BS`, `UART_TX`, `UART_RX` in
> [`include/pinout.h`](include/pinout.h). Usable pins: **42 − SWD(2) − NRST(1) = 39 on the
> UFQFPN48**, against **38 − 2 − 1 = 35 on the LQFP48**, where the 33 mandatory CoCo 3
> signals fit but nothing else does. The `CBU6` is the same die in a QFN package, so the
> pinout, this firmware and every timing number are unchanged; QFN soldering is the whole
> cost. **The external-MMU decision survives untouched** — an in-CPU MMU wants all 39 pins
> and is further out of reach on 35, not closer. Found in review (`docs/design-review.md`
> Cpu-C1) before a board was drawn.

> ⚠ **`PB8` is `A8` and it is also `BOOT0`.** Every module must have its option bytes
> programmed — `nSWBOOT0` = 0, `nBOOT0` = 1 — **before it goes into a socket**. See
> [Provisioning](#provisioning--before-a-module-goes-into-a-socket) below.

Full analysis, pinout rationale, timing budgets and phase plan: **[`docs/plan.md`](docs/plan.md)**.

> ⚠ **This README's timing numbers are superseded (2026-08-27).** They were derived from
> `reference/datasheets/MC6809E.pdf`, whose columns stop at the 2 MHz MC68B09E. The real
> HD63B09E/HD63C09E figures are now in `reference/datasheets/HD6309E_datasheet.pdf` and analysed in
> [`cpu/docs/plan.md`](docs/plan.md) §3.3. Two things changed that matter here:
> **`t_AD` is 110 ns at *both* speed grades** (the address deadline does not tighten at
> 3 MHz), and **`t_DSR` halves to 20 ns at 3 MHz** (3.4 core cycles), which puts read-data
> sampling below the floor for *any* software polling loop on this part. The fix is an
> external 74LVC574 latch — `plan.md` §3.6. Sections below that quote `t_DSR` = 40 ns,
> `t_DHR` = 10 ns or a `T_iter ≤ 6` gate are correct **only for the 1.79 MHz target**.

**Current state: Phase 1 — the timing spike.** No 6309 emulation exists yet, by design.
Phase 1 answers the one question that can invalidate the project before any core is
written: *after the host drops E, can we get the next address onto the bus inside
`t_AD` = 110 ns?* (Earlier revisions asked it as "inside a quarter cycle"; that framing is
retired — see the marked table below.)

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
> MC6809E datasheet (`reference/datasheets/MC6809E.pdf` p.3, item 11), *Address Delay Time from E Low*
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

**Now resolved, and provably so.** The MC6809E datasheet (`reference/datasheets/MC6809E.pdf` p.3) gives,
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

`cpu/src/spike_poll_asm.S` unrolls by two and alternates destination registers, removing the
copy and paying the taken branch once per two samples. By instruction timing that gives
**sample gaps of 4 and 6 cycles**, so `T_iter` worst case is 6 = 35.3 ns, inside the 40 ns
bound with ~5 ns spare.

**Read 4/6 as the hypothesis, not as a verified fact.** The disassembly establishes the
instruction *sequence*; it cannot establish what the bus does. An AHB2 GPIO `LDR` can cost
3+ core cycles rather than the 2 it is costed at, which would make the gaps 5 and 7 =
41.2 ns — over the 40 ns bound, and the sampling unsound however good the latency looked.
That is precisely what `lat_jitter` is on hardware for.

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

## Provisioning — before a module goes into a socket

**`BOOT0` lives on `PB8`, and `PB8` is address line `A8`.** With the factory-default
option byte `nSWBOOT0` = 1 the pad is sampled *throughout* the reset phase (RM0440 §2.6),
so the part reads whatever the address bus happens to be doing at reset and boots the
**system bootloader** on a random subset of resets. It is the classic failure that works
on the bench with a debugger attached and fails in the socket — and no document in this
repository mentioned it before 2026-09-04 (`docs/design-review.md` Cpu-M2).

Program once per part, and read the bytes back — the write goes through a separate flash
sequence and a failed one is silent:

| Option bit | Value | Effect |
|---|---|---|
| `nSWBOOT0` | **0** | `BOOT0` comes from the option bit; `PB8` is a plain GPIO |
| `nBOOT0` | **1** | that option bit selects main flash |

```sh
# STM32CubeProgrammer CLI, ST-Link
STM32_Programmer_CLI -c port=SWD -ob nSWBOOT0=0 nBOOT0=1
STM32_Programmer_CLI -c port=SWD -ob displ            # verify, do not skip
```

**Alternative:** a pulldown on `PB8`. It works, but it forms a divider against the host's
4.7 K address pull-up — strong enough to hold `PB8` low at reset means ~1 K, which then
loads `A8` differently from the other fifteen address lines for the life of the board.
Two option bits cost nothing at runtime and nothing on the BOM. Also set at this point:
the `PF1` machine strap that gates the shadow boot ROM (see below).

---

## Serving the boot ROM (homebrew machine only)

Specified in [`docs/plan.md`](docs/plan.md) §4.5, **not implemented** — Phase 1 is a timing
spike and has no shadow ROM.

The homebrew machine of [`docs/machine.md`](../docs/machine.md) has no boot ROM anywhere in
its 1 MB physical map, and its reset vector at `$FFFE` lands inside the I/O page, which
overrides MMU translation by design. The machine-wide resolution puts the ROM **here**:
this module serves logical `$E000`–`$FEFF` and `$FFC0`–`$FFEF` from **~8 KB of its own
128 KB flash** with no bus cycle, keeps `$FF00`–`$FFBF` decoding normally so the boot code
can reach the MMU and the cards, and serves `$FFF0`–`$FFFF` from a 16-byte internal vector
RAM that is writable through the MMU window. A bit in the MMU window retires the shadow
ROM once the OS is up, freeing that logical space for RAM; vector service stays on.

**For the CoCo 3 and the Dragon 64 the whole mechanism is off** — those machines answer
`$E000`–`$FFFF` from their own ROM, and a drop-in that served something else would not be
a drop-in. Mode comes from a strap on `PF1`, the pinout's last spare pin, read once at
reset. Consequence worth stating plainly: with this mechanism in the CPU, a real HD63C09E
is no longer a drop-in *for the homebrew machine* — see plan §4.5.

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

Needs `arm-none-eabi-gcc` (13.2.1 verified; `spike.elf` links at 4,088 B text):

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

> Verified with `arm-none-eabi-gcc` 13.2.1: links clean at **4,088 B** text, 3,760 B bss,
> with the hot loop in CCM SRAM. What has *not* happened is silicon — no board has run it.

---

## Running the measurement

1. Wire the stimulus generator to E, Q and D0–D7 — see
   [`cpu/tools/stimulus/README.md`](tools/stimulus/README.md).
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

For variant 3, **check `dma_timeouts` and `dma_errors` before reading anything else.** A
timeout on its own only says the address never appeared, and two different faults produce
that:

| `dma_timeouts` | `dma_errors` | Diagnosis |
|---|---|---|
| 0 | 0 | the measurement is real |
| > 0 | **> 0** | the transfer was attempted and **bus-errored** (`TEIF`) — the channel configuration is wrong, typically a source address the DMA cannot reach |
| > 0 | 0 | the **trigger** never arrived — wiring, a clock enable, or the request-line ID |

> ⚠ **This README used to say a timeout "points at wiring or a clock enable rather than a
> wrong bit position", and that advice would have sent you the wrong way.** The register
> constants *are* verified against RM0440 Rev 9, but that was never the only way to get a
> timeout: until 2026-09-04 `s_dma_addr` was declared `__ccmbss`, i.e. linked at
> `0x1000xxxx`, and **RM0440 §2.4 says CCM SRAM can be accessed by DMA only through its
> alias** (`0x2000 5800` on a category-2 part). Every transfer would have bus-errored,
> `dma_timeouts` would have equalled `n_cycles`, and the project's own documentation
> would have pointed the bench at the wiring. The variable is in ordinary SRAM now, and
> `dma_errors` exists so the two failures can never be confused again
> (`docs/design-review.md` Cpu-M1).

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

The number it produces decides whether the pipelined architecture (`cpu/docs/plan.md` §4.2)
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
| `deadline_misses` | latency > the pass gate (`SPIKE_TAD_CYCLES` = **14**, see below). **Must be 0.** |
| `hold_violations` | latency < `t_AH` (4 cycles) — drove the address too early. Must be 0. |
| `overruns` | TIM1 overcapture — a whole E cycle went unserviced. Must be 0. |
| `lat_worst` | worst-case core cycles, hardware E-fall → address stored. **The number.** |
| `lat_jitter` | `lat_worst − lat_best` ≈ `T_iter`. **Must be ≤ 6** (see above). |
| `period_min`/`period_max` | differ ⇒ the host switched speed mid-run (that's the point) |
| `slack_min` | worst-case spare cycles for the emulator. **Size the microcode step against this.** Variant 1 only; variants 2 and 3 report `SPIKE_SLACK_UNMEASURED`. |
| `slack_late` | work overran the budget and Q had already fallen. Must be 0. Variant 1 only — `SPIKE_LATE_UNMEASURED` elsewhere, and that is a real limitation, not a formatting one (below). |
| `dma_timeouts` / `dma_errors` | variant 3 only; read them together, see the table above |
| `hist[]` | latency distribution, 1 core cycle per bin |

Two independent gates: **`lat_worst` ≤ 14** (the address arrives in time) and
**`lat_jitter` ≤ 6** (the data sample is provably valid). Both are worst-case, not
average — an emulator that misses one deadline in 10⁴ is simply wrong.

### Why the latency gate is 14 and not 18

> ⚠ **This README used to call the measurement "slightly conservative", on the grounds
> that the `DSB` before the timestamp costs a couple of cycles in the safe direction. It
> is not. Net, it is optimistic by roughly 3–5 core cycles** — against a claimed margin
> of 5.7 (`docs/plan.md` §3.3), which is most of the margin. Three terms, all one-way,
> all outside the number:
>
> 1. **TIM1's capture path resynchronises `TI1`** to the timer clock even with the input
>    filter off (`ICF` = 0), so `CCR1` is latched **~2–3 core cycles after the physical
>    edge**. Latency is measured from that late timestamp, so every cycle of lag is
>    subtracted from the result.
> 2. **`t_done` is read when the store retires, not when the pad moves** — ~3.3 ns
>    (~0.6 cycles) of slew at `VERY_HIGH` follows it.
> 3. **Phase 1 runs unbuffered on the bench** (`tools/stimulus/README.md`), so the `'541`
>    propagation outbound and the inbound `E` buffer — ~0.9 cycles each — are absent from
>    the measurement and present in the module.
>
> A spike reporting 17 can be a socket-referred 21, and the old 18-cycle gate would have
> passed it. (`docs/design-review.md` Cpu-M4.)

The `t_AD` ceiling is unchanged at 110 ns = **18.7** core cycles; what changed is what we
are willing to call a pass. **18 − 4 = 14**, and the constant lives in
[`include/spike.h`](include/spike.h) as `SPIKE_TAD_CYCLES`, with the raw ceiling kept
beside it as `SPIKE_TAD_RAW_CYCLES`. The failure mode of a gate that is too tight is a
rerun; of one that is too loose, a PCB.

**The better fix, once the bench allows it:** jumper an address line to a spare timer
capture input (`PA11` is `TIM1_CH4` and carries `/RESET`, so it can be borrowed) and
difference two timestamps taken *through the same capture path*. The synchroniser delay
then cancels instead of being estimated, and the gate can go back to 18 with evidence
behind it.

### What variant 2 does not measure

The assembly loop has **no overrun-of-slack detection**. Its per-cycle bookkeeping is
~35–40 core cycles, and the window from Q-fall to E-fall is 23.8 cycles at 1.79 MHz,
20.3 at 2.0979 MHz and 13.5 at fast-E 3.1469 MHz — so at the higher rates the bookkeeping
can still be running when Q falls. The loop then enters the sampling window late and folds
that cycle into `lat_worst` with nothing marking it. Variant 1 counts exactly this case in
`slack_late`, which is why **variant 2's numbers at a given rate are only trustworthy
while variant 1 reports `slack_late` = 0 at that same rate.** Variant 2 reports
`SPIKE_LATE_UNMEASURED` rather than a zero that would read as "none happened".

---

## Layout

Paths are relative to `cpu/`. Build commands run from the repository root.

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
tools/microstate-probe/   does one bus cycle's emulator work fit in the slack?
```

The 6809/6309 code that will *run on* this CPU is not here — it is guest software,
and it lives in [`../software/`](../software/).

---

## Phase 1 TODO

- [x] Variant 1 — polling loop in C (predicted ceiling ~2 MHz)
- [x] Variant 2 — hand-written assembly (`cpu/src/spike_poll_asm.S`), `T_iter` 4/6 cycles
- [x] Variant 3 — DMA-driven address (`cpu/src/spike_dma.c`)
- [x] Verify the DMAMUX/EXTI constants against RM0440 Rev 9 — all confirmed correct
- [x] Confirm the CoCo 3 pin budget against the service manual (§2.6 — six signals freed)
- [x] Verify `t_DSR` / `t_DHR` against the datasheet — 40 ns / 10 ns; deadline corrected
      from the quarter cycle to `t_AD` = 110 ns
- [x] Firmware compiles (`arm-none-eabi-gcc` 13.2.1); hot loop confirmed at `0x10000000`
- [x] Decide direct-drive vs buffers — **buffers, mandatory**: `PA0..PA7`, `PB0`, `PB1`,
      `PB2`, `PB10`, `PB13`, `PB14` (and `PC5`) are `TT_a` (3.6 V), and the CoCo drives
      5 V TTL at the data bus on every read. No 5 V control input may reach an `FT` pin
      directly either — DS12589 Table 14 caps `FT` input voltage at
      min(V_DD, V_DDA) + 4.0 V, which 5 V violates while the LDO is still ramping
- [x] Correct the package — **`STM32G431CBU6`, UFQFPN48**; the LQFP48 has 38 GPIO and
      does not bring out `PC4`/`PC6`/`PC10`/`PC11` (`plan.md` §3.2)
- [ ] Program `nSWBOOT0` = 0 / `nBOOT0` = 1 on every module and verify by read-back —
      `BOOT0` is `PB8` is `A8` (see Provisioning above). Blocks any socket test
- [ ] Confirm the GIME accepts 3.3 V `V_OH` — buffers output 3.3 V, not 5 V
- [ ] Debug console on `USART3` (`PC10`/`PC11`), so results don't need a debugger
- [ ] Variant 2 — hand-written assembly (predicted ~2.5 MHz)
- [ ] Variant 3 — EXTI + DMAMUX + DMA precomputed store (predicted ~3–3.5 MHz)
- [x] ~~Variant 4 — overclock to 180–200 MHz~~ — **dropped.** Core clock committed at
      170 MHz, in spec; see `cpu/docs/plan.md` §3.4(4). It moved no gate from fail to pass,
      and 344 MHz is the PLL VCO ceiling (any SYSCLK > 172 MHz overclocks the PLL too).
- [ ] Variant 5 — straight-line unrolled poll, uniform `T_iter` = 4 (`plan.md` §3.3(c))
- [ ] Variant 6 — external 74LVC574 read-data latch (`plan.md` §3.6) — decides 3 MHz
- [ ] Build the stimulus generator — with a '574 fitted from the start (`plan.md` §7)
- [ ] Calibrate the TIM1 capture-path offset out (jumper an address line to `TIM1_CH4`),
      which is what would justify relaxing the pass gate from 14 back towards 18
- [ ] First silicon measurement; record actuals against predictions in `cpu/docs/plan.md` §5

Beyond Phase 1, and specified rather than built: the **shadow boot ROM and vector page**
of `plan.md` §4.5 — see "Serving the boot ROM" above. It is Phase 6b, and it is what makes
the homebrew machine boot at all.

Predictions are recorded deliberately. A wrong one is informative.
