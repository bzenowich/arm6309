# `hardware/mainboard/` — the motherboard

The machine's motherboard: the CPU socket, the MMU and its 32 MB map, four 30-pin
SIMM sockets, the 1 MB boot ROM, the clock, and the six-slot backplane.

| | |
|---|---|
| [`docs/ram.md`](docs/ram.md) | the memory system — the map, the SIMM windows, the boot ROM. Its history is the hardware area's shared [`../history.md`](../history.md) |
| [`board/`](board/) | `mainboard.circuit.tsx` |
| [`logic/`](logic/) | the four GAL22V10s: U3 `mmu`, U6 `clkdec`, U9 (the space decode) and U10 (the SIMM controller) — term lists, models, checks, `.pld`, the fuse maps we assemble and CUPL's in `cupl/` |
| [`sim/`](sim/) | `mainboard.v` (the board), `mainboard_tb.sv`, the generated `u9.v`/`u10.v`, and the hand-written `mmu.v`/`clkdec.v` with their own testbenches |
| [`reference/`](reference/) | the map SRAM, system RAM, boot flash and refresh counter datasheets |

The whole machine — this board with a CPU core and the cards in its slots — is
`../tools/sim/machine3.v`, run by `make -C hardware check-machine`.
