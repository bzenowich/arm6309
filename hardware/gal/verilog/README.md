# Simulating the machine

`npm run check:video` from `hardware/`. It regenerates the Verilog and runs six
testbenches; it reports **122 ok and 16 FAIL**, and the failures are
[`docs/design-review2.md`](../../../docs/design-review2.md)'s findings. **They are
left failing on purpose** — a testbench edited to pass is a finding that has been
deleted. `run.sh` exits 0 either way; read the output.

## Why this exists

`hardware/gal/`'s checks are exhaustive and they are all the same shape: execute
*one design's* fuses or terms against *that design's* model. Every defect
`design-review2.md` found is in a seam that shape cannot see — a signal produced
on one part and consumed on another, a name that means two things, a latch whose
contents are right and whose lifetime is not, a package counted as absorbed and
never written.

A simulator sees seams, because it has to wire them.

## What is generated and what is written

| | |
|---|---|
| `emit.ts` | `Merged`/`Design` → Verilog. **The same `Cell` term lists `jedec/cupl.ts` compiles for `fit1508.exe`** — one origin, three devices, which is the rule `cupl.ts` states and the reason two errors got into the 22V10 fuse map on 2026-09-07 |
| `gen.ts` | writes `vaddr.v`, `vctrl.v`, `rfa.v`, `audio.v`, `u9.v`, `u10.v`. ⚠ **Do not edit those six** |
| `video_card.v` | hand-written: the card wired up — three parts, four interleaved framebuffer chips, the fetch latches and the `'153` mux. Board-level, transcribed from `hardware/cards/` and `video.cpld.ts` |
| `vshim.v` | hand-written, and ⚠ **it is a finding rather than a component**: every signal in it is an input to a fitted part that nothing on the card produces. Its size is the size of `design-review2.md` §1.2 |
| `mainboard.v` | hand-written: U3, U6, U9, U10, both map SRAMs, the `'157`, the `TASK` `'574`, the boot `'244`, both flash devices and the SIMM bank. Transcribed from `hardware/mainboard/mainboard.circuit.tsx`, which is the netlist of record |
| `*_tb.sv` | hand-written. `vsync`, `vaddr`, `vtile`, `vspan`, `audio`, `mainboard` |

`../clkdec.v` and `../mmu.v` are older, hand-written models of the same two GALs
and are run by `npm run check:sim`; `mainboard.v` instantiates them rather than
a second copy.

## What it models, and what it does not

**It models the logic**: the sum of products each macrocell forms, the register,
the one asynchronous reset. A signal is its **asserted** sense throughout, the
same convention `assemble.ts` uses for terms — a pin declared active-low is
inverted at the pin and not in the equation.

⚠ **It does not model propagation delay**, the switch matrix, product-term
cascading or the fitter's placement. Those are `fit1508.exe`'s business and
`cpld/*.fit` is where they are recorded, and every bench item in `graphics.md`
§19 and `audio.md` §16 stands untouched by anything here.

**One exception is worth stating, because it is where two findings came from:**
whether a signal carries the sub-slot phase *at all* is logic and not delay, and
so is which slot a latch is clocked in. This model sees both.
