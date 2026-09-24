# `hardware/mainboard/reference/`

Reference material for the motherboard's map SRAM, system RAM, boot flash and refresh counter.

**Not in git**: PDFs, scans, disk images and archives under any `reference/` are `.gitignore`d (see [the root `reference/` README](../../../reference/README.md)). Expected contents, and what cites each:

| File | What | Cited by |
|---|---|---|
| `CY7C128A.pdf` | Cypress CY7C128A, 2K × 8 SRAM, 15 ns (`-15PC` is the 300-mil DIP-24 grade) | `hardware/tools/lib/parts.ts` `MAP_SRAM` — the MMU block map, `graphics.md` §6.3.1 |
| `AS6C4008.pdf` | Alliance Memory AS6C4008, 512K × 8 low-power SRAM, 55 ns, DIP-32 | `hardware/tools/lib/parts.ts` `SRAM_512K` — the machine's system RAM, `machine.md` §7.1 |
| `CD74HC4040.pdf` | TI CD54HC4040 / **CD74HC4040** / CD54HCT4040 / CD74HCT4040, 12-stage ripple counter | `hardware/tools/lib/parts.ts` `HC4040` and `ram.md` §6.3.1 — the refresh timebase. ⛔ **It found three rotated pins**: 12 is `Q8` (not `Q10`), 13 is `Q7` (not `Q8`), 15 is `Q10` (not `Q7`) — a 3-cycle rotation, the same shape as finding 4's map SRAM, on the same board. `hardware/history.md` has what it would have cost. `MR` active high is confirmed |
| `SST39SF040.pdf` | SST/Microchip SST39SF010A / SST39SF020A / **SST39SF040**, 512K × 8 MPF flash, DS25022A | `hardware/tools/lib/parts.ts` `FLASH_512K` and `docs/machine.md` §7.2 — **the boot ROM.** It was the board's only unverified pinout from 2026-09-06; Figure 4 (32-pin PDIP) confirms all 32 pins, including the two the note flagged: **pin 3 is A15** and **pin 31 is `/WE`**, both already right. ⚠ **Pin 1 is A18 only on the 4 Mbit part** — NC on the 010A/020A, which share the footprint, so a smaller substitute silently drops the top address line. Grades 45/55/70 ns; 600-mil PDIP |
