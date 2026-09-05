# E/Q stimulus generator — requirements

The Phase 1 spike needs a host that behaves like the timing half of a CoCo 3: it drives
E, Q and a data bus, and the spike measures whether we can keep up. This is bench
equipment, not part of the product.

## Signals to generate

| Signal | Direction (from generator) | Notes |
|---|---|---|
| `E` | out → `PA8` | the bus-cycle clock |
| `Q` | out → `PA9` | **leads E by 90°**, same frequency |
| `D0..D7` | out → `PA0..PA7` | must **vary** — see below |
| `A0..A15` | in ← `PB0..PB15` | optional; useful to confirm we drive sane addresses |

## Requirements

1. **Q leads E by exactly 90°.** The whole deadline is defined by the E-fall → Q-rise
   quarter cycle. Phase error here shows up directly as a wrong answer. Verify with a
   scope before trusting any measurement.

2. **Frequency sweepable**, at minimum covering 0.5 – 5 MHz. The spike sweeps upward
   until deadline misses appear; that frequency is the project's real ceiling.

3. **Runtime speed switching**, 0.895 ↔ 1.79 MHz, changing between one cycle and the
   next with no gap or notification. This reproduces the GIME behaviour described in
   `cpu/docs/plan.md` §2.1 — software on a CoCo 3 flips speed by poking `$FFD9`, and the bus
   loop must handle it without any calibration. **The spike does not recompute anything
   per cycle** — an earlier version of this file claimed it recomputed the deadline from
   the measured period every cycle, and it does not. The deadline is a fixed constant
   (`SPIKE_TAD_CYCLES` in `cpu/include/spike.h`), which is correct precisely *because*
   `t_AD` is an absolute 110 ns rather than a fraction of the E period, so a speed switch
   does not move it. What has to survive the switch is the *anchoring*: the loop waits on
   TIM1's Q-fall capture flag, a hardware event, so a faster clock simply means the flag
   is already set. `period_min` ≠ `period_max` in the result is how you confirm the
   generator actually switched. **It needs testing, not assuming.**

4. **Data must vary per cycle.** A constant byte makes the stub table lookup hit the
   same entry every time, which is friendly to the branch predictor and the memory
   system in a way real code is not. A counter is adequate; a pseudorandom sequence is
   better. Holding D0–D7 with pull-ups produces a flattering, useless measurement.

5. **Data valid window must be controllable.** The most valuable thing this rig can do
   is narrow the window in which D0–D7 are valid around E's fall, to find where sampling
   breaks. See the "data sampling problem" section in the top-level README — this is the
   assumption most likely to be wrong.

## Suggested implementation

A **Raspberry Pi Pico** is a good fit: PIO can generate E and Q with exact phase
relationships and cycle-accurate data timing, independent of the CPU, and it is the same
approach [`strickyak/tfr9`](https://github.com/strickyak/tfr9) uses to drive a real
6309E. A second STM32 with timer-driven DMA works too.

A bench function generator can produce E and Q if it has two phase-locked channels, but
it cannot drive the data bus, so it only gets you the clock-side half of the measurement.

## Levels

The generator runs at **3.3 V directly into the STM32** for Phase 1 — no buffers. The
74LVC level-shifting described in `cpu/docs/plan.md` §3.5 belongs to Phase 7, on the real
carrier PCB against a 5 V CoCo 3. Keep the bench rig simple; do not let level shifting
become a variable while establishing the timing baseline.

Note that this means Phase 1 measures the MCU's timing **without** the ~5 ns each-way
buffer propagation delay that the real module will have. Budget for it: ~0.9 core cycles
each way against the `t_AD` ceiling of 18.7 core cycles (110 ns, absolute at every E rate
— `plan.md` §3.3). Both ways land *outside* the measured number and *inside* the real
one, which is one of the three terms that make the spike optimistic rather than
conservative, and one of the reasons the pass gate is 14 and not 18. See
`cpu/include/spike.h`.

Also worth stating for the same reason: the deadline is **not** the quarter cycle. Earlier
versions of this file and of the top-level README framed it that way ("23.7 core cycles at
1.79 MHz, 8.5 at 5 MHz"); requirement 1 above still needs Q at exactly 90°, because Q's
fall is the slack anchor, but nothing about the deadline is period-relative.
