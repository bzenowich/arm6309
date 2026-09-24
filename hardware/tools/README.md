# `hardware/tools/` — what every card shares

| | |
|---|---|
| [`lib/`](lib/) | the 72-pin slot as one table (`slot.ts`), the tscircuit card edge and socket, the part pinouts (`parts.ts`), the `$FF` window map (`windows.ts`), and the machine-wide checks: slots, cards, decode, netlist, and **`docs.check.ts`**, which holds every utilisation figure in the prose to the fitter's reports |
| [`place/`](place/) | the placement study — each card's IC budget and length, and `render.ts`'s board sheet |
| [`gal/`](gal/) | the logic toolchain: the JEDEC assembler and its GAL22V10 model (`jedec/`), the Atmel CUPL cross-check (`jedec/cupl.check.ts`), the fitter and CUPL wrappers (`prjbureau/`), `cpld.gen.ts` (writes each CPLD's `.pld` into its card's `logic/`), and the checks that span cards: `pins`, `reach`, `fold`. [`gal/README.md`](gal/README.md) is the long version |
| [`sim/`](sim/) | the Verilog side: `emit.ts` and `gen.ts` turn every card's term lists into Verilog in that card's `sim/`; `run.sh` compiles and runs the card testbenches, `run-machine.sh` the whole machine (`machine3.v`, `machine_tb.sv`). [`sim/README.md`](sim/README.md) |

Everything runs from `hardware/` — see the root `CLAUDE.md` for the commands.
