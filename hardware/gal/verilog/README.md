# Simulating the machine

`npm run check:video` from `hardware/`. It regenerates the Verilog and runs the six
testbenches in `run.sh`'s default `TBS` — `audio`, `mainboard`, `storage`, `v3dot`,
`v3card`, `v3machine` — and reports **320 claims, 0 failed**. ⚠ `run.sh` exits 0
whether a claim failed or not, so **the count is what decides the status**; read the
`FAIL` lines.

⭐ **Five more are asked for by name**: `vsync`, `vaddr`, `vtile`, `vspan` and `vpal`,
the **archived** `video` card's, 115 claims — `TBS="vsync vaddr vtile vspan vpal" sh
run.sh`. They left the default on 2026-09-20 when `video3` became the machine's video
card ([`../../../archive/README.md`](../../../archive/README.md)); `video_card.v` and
the generated `vaddr.v`/`vctrl.v`/`vsup.v` are still here because `machine_tb` and
`demo_tb` still instantiate the card.

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
| `gen.ts` | writes `vaddr.v`, `vctrl.v`, `vsup.v`, `rfa.v`, `vlen.v`, `pxsel.v`, `audio.v`, `aseq.v`, `u9.v`, `u10.v`, `v3dot.v`, `v3scan.v`, `v3ptr.v`, `v3host.v`, `v3lane.v`, `sdbus.v`, `sdeng.v`. ⚠ **Do not edit any of them** — change the `.jedec.ts`/`.cpld.ts` and re-run |
| `video_card.v` | hand-written: the **archived** `video` card wired up — three parts, four interleaved framebuffer chips, the fetch latches and the `'153` mux. Board-level, transcribed from `hardware/cards/` and `video.cpld.ts`. ⚠ Kept because `machine.v` instantiates it and `boot.asm` drives it |
| `video3_card.v` | ⭐ the machine's video card since 2026-09-20 — generated port maps (`v3portmap.ts`) around the five parts and every discrete package `plan.md` §13.1 lists. A model of a board rather than a drawn one |
| `vshim.v` | hand-written, and ⚠ **it is a finding rather than a component**: every signal in it is an input to a fitted part that nothing on the card produces. Its size is the size of `design-review2.md` §1.2 |
| `mainboard.v` | hand-written: U3, U6, U9, U10, both map SRAMs, the `'157`, the `TASK` `'574`, the boot `'244`, both flash devices and the SIMM bank. Transcribed from `hardware/mainboard/mainboard.circuit.tsx`, which is the netlist of record |
| `tl16c550.v` | hand-written, and ⚠ **a bus model of a bought part, not a design output**: the serial card's TL16C550C (`io/serial/docs/serial.md` §7), for `machine.v`'s `SERIAL = 1`. It is the console that `machine_tb +scenario=nitros9` types at, and it must behave as `software/demo/emu/machine.c`'s UART does |
| `*_tb.sv` | hand-written. In the default run: `audio`, `mainboard`, `storage`, `v3dot`, `v3card`, `v3machine`. By name: `vsync`, `vaddr`, `vtile`, `vspan`, `vpal` (archived `video`), `machine`, `modplay`, `demo` |

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
