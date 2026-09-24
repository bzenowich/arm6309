# `hardware/cpu/reference/`

Reference material for the CPU: the HD6309E it replaces, the STM32 that replaces it, and the part not chosen.

**Not in git**: PDFs, scans, disk images and archives under any `reference/` are `.gitignore`d (see [the root `reference/` README](../../../reference/README.md)). Expected contents, and what cites each:

| File | What | Cited by |
|---|---|---|
| `HD6309E_datasheet.pdf` | Hitachi HD63B09E / HD63C09E | `hardware/cpu/docs/plan.md` §3.3 — the real timing figures. **This is the authoritative one.** |
| `MC6809E.pdf` | Motorola MC6809E / MC68A09E / MC68B09E | `hardware/cpu/docs/plan.md`, `hardware/cpu/README.md` — `t_DSR`/`t_DHR`. **Superseded above 2 MHz:** its columns stop at the MC68B09E. |
| `stm32g4-refman.pdf` | ST RM0440 Rev 9, STM32G4 reference manual | `hardware/cpu/docs/plan.md`, `hardware/cpu/include/stm32g431.h` — every register constant, and the DMAMUX/EXTI verification |
| `stm32g431kb.pdf` | ST STM32G431 datasheet | `hardware/cpu/docs/plan.md` §3.2 — pin budget, and the `TT_a` 3.6 V pins that made buffers mandatory |
| `ATSAMD51G19A.pdf` | Microchip SAMD51 | `hardware/cpu/docs/plan.md` §3.7 — the MCU review, i.e. the part that was *not* chosen |
| `The 6309 Book (Burke & Burke).pdf` | *The 6309 Book*, Burke & Burke | `software/emu/test/mk6309tab.py` — appendix A's native-mode cycle counts (the `#` column), which `hd6309.tab` is re-derived from |
