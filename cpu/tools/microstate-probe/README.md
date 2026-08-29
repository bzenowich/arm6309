# Microstate cost probe

Answers the question that `cpu/docs/plan.md` §8 lists as the top risk: **does one bus cycle's
worth of emulator work fit in the available core cycles?**

Every budget in the plan rested on "a microcode step is ~15–30 core cycles" — an estimate
for code that did not exist. Phase 1 does not measure it, because `cpu/src/stub_core.c`
deliberately does no ALU work. With the core clock settled at 170 MHz (§3.4(4)) and data
sampling settled by the §3.6 latch, this was the last unknown before a 3 MHz answer.

```sh
./measure.sh                 # needs arm-none-eabi-gcc and llvm-mca-18
OPT=-O3 ./measure.sh         # or any other optimisation level
```

## The budget being tested

From `plan.md` §3.3(d), at 170 MHz with the §3.6 latch:

| E rate | Cycles/bus cycle | Available for emulator work |
|---|---|---|
| 1.79 MHz | 95.0 | ~48 |
| 3.0 MHz | 56.7 | ~34 |

Both already exclude the ~13-cycle address-drive path.

## Result

**Naive C in the `plan.md` §4.1 shape does not fit. A tuned hot path fits with room.**

| | Per bus cycle | vs 34 (3 MHz) |
|---|---|---|
| §4.1 shape, eager CC, straightforward C | **~80 cycles** | 2.4× over |
| Tuned, typical (8-bit ALU) | **14 cycles** | 20 spare |
| Tuned, worst measured (TFM step) | **25 cycles** | 9 spare |

## Files

| File | What it is |
|---|---|
| `cpu.h` | Register layout. X/Y/U/S contiguous so indexed decode is branchless. |
| `microstates.c` | Naive baseline — the §4.1 struct-of-function-pointers shape, eager condition codes. |
| `tuned.c` | Same semantics with lazy CC and register-resident state. Partly defeated by the AAPCS (see below). |
| `tuned.S` | The tuned hot path hand-written, which is what §3.4(1) commits to anyway. **These are the numbers that matter.** |
| `measure.sh` | Compiles with the firmware's exact flags, runs each body through `llvm-mca`. |

## What made the difference

Three changes, each attacking a line item visible in the naive disassembly:

1. **AND-fold the control lines instead of decoding them** — 27 → 5 cycles, the single
   biggest win and it is free. All five control inputs are active low, so AND-ing the raw
   port words into an accumulator means any line ever asserted leaves a zero bit behind.
   Nothing can be missed; the edge detection and `CC.I`/`CC.F` masking move to the
   instruction boundary, where there is slack.
2. **Lazy condition codes** — the dominant cost was materialising H/N/Z/V/C (about 18 of
   `ms_adda`'s 28 instructions), because the 6809 half-carry and overflow have no ARM
   equivalent. Keeping the operands and raw result, and materialising on demand, takes an
   8-bit ALU step from 31 cycles to 5.
3. **Pin hot state in registers** — the bus loop is hand-written assembly running from CCM
   for the whole run, so A, CC, the cpu pointer and the GPIO base addresses never need to
   touch memory.

One pinout choice paid off directly: **`/HALT` on `PA12` arrives in the same `GPIOA` word
as the data bus**, so sampling it costs one `AND` rather than a second load. That is
`plan.md` §3.2 earning its keep.

## Caveats — read before trusting these numbers

- **`llvm-mca` is a model, not silicon.** Its Cortex-M4 model is a simple in-order scalar
  pipeline that assumes every access hits with no wait states. That matches the hot loop's
  real home (CCM SRAM, zero-wait) but it is still a model. Phase 1 on hardware remains the
  arbiter.
- **`llvm-mca` cannot cost an indirect call.** It reports absurd figures for `blx reg`, so
  the ~80-cycle naive total is part measured (31 + 27 for the two called bodies) and part
  hand-derived (~24 for dispatch, including two pipeline refills at ~4 cycles each).
- **The AAPCS returns anything over 4 bytes through memory**, which is why `tuned.c`'s
  `cyc_adda_tuned` measures 26 cycles rather than the 5 that `tuned.S` shows for identical
  semantics. The C file is kept because it documents the intent readably; the `.S` is the
  measurement.
- **Functions containing branches are counted as if every instruction executes** — an
  over-estimate, i.e. the safe direction.
- **This is a sample, not a survey.** The states measured are the ones expected to be
  expensive. Not covered: the interrupt stacking sequence, `DIVQ`/`DIVD`, indexed-indirect
  modes, and the `/HALT` entry/exit path. Any of those could be worse.
- **Lazy CC is a correctness obligation, not a free lunch.** Every path that can observe CC
  must go through `cc_materialise()` (24 cycles, paid rarely) — *including the interrupt
  stacking sequence, which stacks CC*. Getting that wrong is an accuracy bug, and accuracy
  is the whole product.
