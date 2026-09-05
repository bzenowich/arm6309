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
| 1.79 MHz (CoCo 3 fast) | 95.0 | ~48 |
| 2.0979 MHz (homebrew, **the specified rate**) | 81.0 | ~58 |
| 3.0 MHz (HD63C09E rated max) | 56.7 | ~34 |
| 3.1469 MHz (homebrew **fast-E**, experimental) | **54.0** | **~31** |

Both already exclude the ~13-cycle address-drive path.

The bottom row is the binding one and it is tighter than the 3.0 MHz row it is easy to
mistake it for: the homebrew machine divides 25.175 MHz by 8, not by an even 3 MHz, so a
bus cycle is 54.0 core cycles and the budget is ~31. Against it, the 25-cycle `TFM`
figure below keeps **~6 cycles, not 9** (`plan.md` §3.3(e)).

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
- **The `TFM` fragment is not `TFM`-shaped, so 25 cycles is a FLOOR for `TFM`, not a
  worst case.** Two specific divergences, both found in the 2026-09-04 design review.
  **(1)** `r9` is double-booked: it serves as the `ctrl_a` control-line accumulator and as
  the pinned `W` counter, so the measured body does less register pressure than the real
  step, which needs both live at once. **(2)** It decodes **2-bit** register-select
  fields, where a real `TFM` postbyte carries **two 4-bit fields** and an invalid encoding
  must take the illegal-instruction trap — so the real decode is wider and has a branch
  the fragment does not. Both push the same way. Treat the `~6 cycles spare` at fast-E
  above as an upper bound on the margin, and re-measure once the real `TFM` step exists
  in Phase 4.
- **This is a sample, not a survey.** The states measured are the ones expected to be
  expensive. Not covered: the interrupt stacking sequence, `DIVQ`/`DIVD`, indexed-indirect
  modes, and the `/HALT` entry/exit path. Any of those could be worse.
- **Lazy CC is a correctness obligation, not a free lunch.** Every path that can observe CC
  must go through `cc_materialise()` (24 cycles, paid rarely) — *including the interrupt
  stacking sequence, which stacks CC*. Getting that wrong is an accuracy bug, and accuracy
  is the whole product.
