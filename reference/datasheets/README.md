# `reference/datasheets/`

**Not in git** — see [`../README.md`](../README.md). Expected contents:

| File | What | Cited by |
|---|---|---|
| `HD6309E_datasheet.pdf` | Hitachi HD63B09E / HD63C09E | `cpu/docs/plan.md` §3.3 — the real timing figures. **This is the authoritative one.** |
| `MC6809E.pdf` | Motorola MC6809E / MC68A09E / MC68B09E | `cpu/docs/plan.md`, `cpu/README.md` — `t_DSR`/`t_DHR`. **Superseded above 2 MHz:** its columns stop at the MC68B09E. |
| `stm32g4-refman.pdf` | ST RM0440 Rev 9, STM32G4 reference manual | `cpu/docs/plan.md`, `cpu/include/stm32g431.h` — every register constant, and the DMAMUX/EXTI verification |
| `stm32g431kb.pdf` | ST STM32G431 datasheet | `cpu/docs/plan.md` §3.2 — pin budget, and the `TT_a` 3.6 V pins that made buffers mandatory |
| `sn74hc574.pdf` | TI SN74HC574 octal D flip-flop | `cpu/docs/plan.md` §3.6 — the read-data latch (the design calls for the LVC part; this is the family datasheet) |
| `ATSAMD51G19A.pdf` | Microchip SAMD51 | `cpu/docs/plan.md` §3.7 — the MCU review, i.e. the part that was *not* chosen |
| `AD7528.pdf` | Analog Devices AD7528, **dual** 8-bit parallel multiplying DAC | `audio/docs/audio.md` §6.1–§6.3 — **the specified DAC.** The `VREF` input-resistance match (±1 %), the write timing, the glitch impulse, and the datasheet's own dual-attenuator application, which is what the card's volume stage is |
| `LTC7545A.pdf` | Linear Technology LTC7545A, 12-bit parallel multiplying DAC | `audio/docs/audio.md` §6.3 — **superseded**, kept because the section's history and its `tWR`/glitch comparisons are argued against it |
| `AD7545.pdf` | Analog Devices AD7545, the original | `audio/docs/audio.md` §6.3 — the pin-compatibility and timing comparison. **Note this is the plain `AD7545`, not the `AD7545A`** the design names as its period part; §6.3 explains why the difference matters |

**Missing, and wanted:** the `AD7545A` datasheet. `audio/docs/audio.md` §6.3 names it as the
period part and §17's audit rests on it, but the file here is the plain `AD7545`. Its
`tWR` figure is the one number that decides whether the period part would actually have
worked — see §6.3.
