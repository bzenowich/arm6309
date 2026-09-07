# `reference/datasheets/`

**Not in git** — see [`../README.md`](../README.md). Expected contents:

## The CPU and its candidates

| File | What | Cited by |
|---|---|---|
| `HD6309E_datasheet.pdf` | Hitachi HD63B09E / HD63C09E | `cpu/docs/plan.md` §3.3 — the real timing figures. **This is the authoritative one.** |
| `MC6809E.pdf` | Motorola MC6809E / MC68A09E / MC68B09E | `cpu/docs/plan.md`, `cpu/README.md` — `t_DSR`/`t_DHR`. **Superseded above 2 MHz:** its columns stop at the MC68B09E. |
| `stm32g4-refman.pdf` | ST RM0440 Rev 9, STM32G4 reference manual | `cpu/docs/plan.md`, `cpu/include/stm32g431.h` — every register constant, and the DMAMUX/EXTI verification |
| `stm32g431kb.pdf` | ST STM32G431 datasheet | `cpu/docs/plan.md` §3.2 — pin budget, and the `TT_a` 3.6 V pins that made buffers mandatory |
| `ATSAMD51G19A.pdf` | Microchip SAMD51 | `cpu/docs/plan.md` §3.7 — the MCU review, i.e. the part that was *not* chosen |

## The audio card's converters

| File | What | Cited by |
|---|---|---|
| `AD7528.pdf` | Analog Devices AD7528, **dual** 8-bit parallel multiplying DAC | `audio/docs/audio.md` §6.1–§6.3 — **the specified DAC.** The `VREF` input-resistance match (±1 %), the write timing, the glitch impulse, and the datasheet's own dual-attenuator application, which is what the card's volume stage is |
| `AD7545A.pdf` | Analog Devices AD7545A, 12-bit buffered multiplying DAC | `audio/docs/audio.md` §6.3 and §17 — **the period part.** Its `tWR` is the one number that decides whether 1989's part would actually have worked |
| `AD7545.pdf` | Analog Devices AD7545, the original | `audio/docs/audio.md` §6.3 — the pin-compatibility and timing comparison. **Note this is the plain `AD7545`, not the `AD7545A`** above; §6.3 explains why the difference matters |
| `LTC7545A.pdf` | Linear Technology LTC7545A, 12-bit parallel multiplying DAC | `audio/docs/audio.md` §6.3 — **superseded**, kept because the section's history and its `tWR`/glitch comparisons are argued against it |

## The logic the boards actually fit

Fetched 2026-09-06 to close `hardware/README.md` open item 1 — `hardware/lib/parts.ts`
carried DIP pin *numbers* written from familiarity, with no datasheet behind any of them.
Sources are named because the part on the board is a period type, not the modern SKU: the
TI `SN74HC…` sheets are the family documents, and pin numbering is what they are here for.

| File | What | Cited by |
|---|---|---|
| `CY7C128A.pdf` | Cypress CY7C128A, 2K × 8 SRAM, 15 ns (`-15PC` is the 300-mil DIP-24 grade) | `hardware/lib/parts.ts` `MAP_SRAM` — the MMU block map, `graphics.md` §6.3.1 |
| `AS6C4008.pdf` | Alliance Memory AS6C4008, 512K × 8 low-power SRAM, 55 ns, DIP-32 | `hardware/lib/parts.ts` `SRAM_512K` — the machine's system RAM, `machine.md` §7.1 |
| `sn74hc574.pdf` | TI SN74HC574 octal D flip-flop | `cpu/docs/plan.md` §3.6 (the read-data latch — the design calls for the LVC part; this is the family datasheet), and `parts.ts` `HC574` |
| `sn74hc245.pdf` | TI SN74HC245 octal bus transceiver | `parts.ts` `HC245` — break-before-make isolation between the map SRAM and D0–D7 |
| `sn74hc157.pdf` | TI SN74HC157 quad 2:1 multiplexer | `parts.ts` `HC157` — the mux on the map SRAM address |
| `sn74hc244.pdf` | TI SN74HC244 octal buffer / line driver | `graphics.md`, `ps2.md` |
| `sn74hc273.pdf` | TI SN74HC273 octal D flip-flop with clear | `graphics.md`, `ps2.md`, `audio.md` |
| `sn74hc595.pdf` | TI SN74HC595 8-bit shift register with output latch | `ps2.md` §3 — the receive shift register |
| `74hc_hct595.pdf` | Nexperia 74HC595 **and 74HCT595**, one document | `sdcard.md` §7 — the SD card's receive register is the **HCT** part deliberately, and the reason is an input threshold: 3.3 V `MISO` clears an HCT input's 2.0 V `V_IH`, so the return path needs no level shifter. That number is here and not in the TI HC sheet above |
| `sn74hc193.pdf` | TI SN74HC193 4-bit up/down counter | `ps2.md` |
| `sn74lvc125a.pdf` | TI SN74LVC125A quad bus buffer, 1.65–3.6 V | `sdcard.md` §7 — three of four gates level-shift `SCK`/`MOSI`/`/CS` down to 3.3 V; also `cpu/docs/plan.md` for the LVC family's 5 V-tolerant inputs |
| `ATF22V10C.pdf` | Microchip (Atmel) ATF22V10C — the in-production `GAL22V10` | the motherboard's U3 and U6, and the audio and I/O cards. `hardware/gal/jedec/gal22v10.ts` is built from its §10 fuse counts and §11 array diagram |
| `ATF1508AS.pdf` | Atmel/Microchip **ATF1508AS(L)**, Rev 0784P–PLD–7/05 — 5 V, 128 macrocells, 84/100/160-pin | **the video card's logic, all of it** (`graphics.md` §10.1.3). Icc vs frequency (p. 16) is the figure §14's power table needed; the DC table's separate `VCCINT` / `VCCIO` rails are why §10.1.3 can leave the 3.3 V `ATF1508ASV` question open |

## The serial card's ACIA — a gap, and a stand-in

| File | What | Cited by |
|---|---|---|
| `W65C51N.pdf` | WDC W65C51N ACIA | `io/serial/docs/serial.md` — **for the DIP-28 pinout only.** §3.3 rules this part *out*: two documented defects make polling *and* interrupts unsafe |

**Missing, and wanted:** an `R6551A` or `G65SC51` datasheet. `serial.md` §3.3 specifies one of
those two — the pre-WDC parts that implement TDRE correctly — and §3.4 makes the **speed
grade part of the specification** (2 MHz minimum at ÷12, 4 MHz for fast-E mode). Neither
part is in production, so **neither Digi-Key nor Mouser carries one**, and the numbers that
decide §3.4 are in those sheets rather than in the W65C51N's. The stand-in above is
pin-compatible and settles the package; it settles nothing else.
