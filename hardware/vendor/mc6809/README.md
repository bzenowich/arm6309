# `mc6809` — Greg Miller's cycle-accurate MC6809/MC6809E core

**Third-party. Not written by this project.** Upstream is
[`cavnex/mc6809`](https://github.com/cavnex/mc6809), fetched 2026-09-06 at upstream commit
state of 2021-06-06. The four `.v` files are **byte-identical to upstream** and must stay
that way; Verilator's complaints are waived on the command line rather than by editing
them, so the copyright notice in `mc6809i.v` and the terms in
[`LICENSE.md`](LICENSE.md) travel intact.

## The licence choice, made explicitly

`LICENSE.md` offers two and says **"You must select one."**

> **This project selects the standard 3-clause BSD licence.**

That is the option that permits redistributing the source, which is what tracking these
files in git *is*. The condition it carries — retain the copyright notice, the conditions
and the disclaimer — is met by keeping `LICENSE.md` beside the sources and the files
unmodified. The alternative (binary-only, no citation) would forbid this directory
existing in a public repository at all.

**This matters here more than it usually would.** On 2026-09-04 this project untracked its
68000-era material because it had no right to redistribute it
(`docs/design-review.md` §Sys-M6, [`reference/68k/README.md`](../../../reference/68k/README.md)).
This directory is the opposite case, and it is written down so the difference is a
decision on the record rather than an inconsistency.

⚠ The repository still has **no licence of its own** — §Sys-M6, unresolved. That does not
affect the BSD terms above, which stand on their own for these four files.

## Why this core and not the one with "6309" in its name

[`freecores/6809_6309_compatible_core`](https://github.com/freecores/6809_6309_compatible_core)
is LGPL, implements the **HD6309 instruction set**, and is the obvious hit when you search
for a 6309 model. It is the wrong tool for this machine, and its own README says why:
it is **not cycle accurate**.

Everything this project needs a core *for* is bus behaviour:

- `hardware/gal/mmu.pld`'s entire design rests on the **E/Q quadrature** — the phase table
  in `graphics.md` §6.3.1, and the 174 ns break-before-make margin derived in
  `hardware/gal/README.md`. A core that gets the instruction set right and the cycle
  timing wrong cannot check any of it.
- `mc6809e.v`'s ports **are** the 40-pin socket in `hardware/lib/parts.ts`, one for one,
  and it takes `E` and `Q` as *inputs* — so a testbench supplies the quadrature exactly as
  `gal/mmu_tb.sv` already does.
- It was validated against a **TRS-80 Color Computer 3**, among others. That is this
  project's other target machine (`cpu/docs/plan.md`).

**And the instruction set is not what is missing.** The CPU in this machine is an
STM32G431 emulating an HD6309E (`cpu/`), and what reaches the motherboard is a **6809E
bus**. The 6309's extra registers and instructions are firmware's problem, not the
backplane's. If a 6309 *instruction* model is ever wanted — to run 6309-native code in
simulation — the freecores core is the candidate, and pulling it is a separate decision
with a separate licence (LGPL, which entangles differently from BSD).

## Files

| | |
|---|---|
| `mc6809i.v` | the core — 127 KB, the actual implementation |
| `mc6809e.v` | **MC6809E wrapper — the one this project wants.** External `E`/`Q` |
| `mc6809.v` | MC6809 wrapper — generates its own `E`/`Q` from a clock. Not this machine |
| `mc6809s.v` | a synchronous-bus variant |
| `LICENSE.md`, `UPSTREAM-README.md` | upstream, unmodified |

## Using it

It elaborates clean under Verilator with two waivers, both Verilator-specific and neither
a defect in the core:

```sh
verilator --lint-only -Wno-lint -Wno-SIDEEFFECT -Wno-UNOPTFLAT \
          --top-module mc6809e mc6809e.v mc6809i.v
```

`UNOPTFLAT` is combinational feedback, which is what a cycle-accurate model of a
combinational part looks like; `SIDEEFFECT` is a portability note about expressions.

**Nothing drives it yet.** The next step is a co-simulation that runs the real core against
`gal/mmu.v` and a model of U1/U2/U4/U5, so the map-write cycle is exercised by a CPU
executing `STA $FFA0,X` rather than by a testbench asserting phases by hand. That is the
first check in this project able to fail for a reason nobody thought of in advance.
