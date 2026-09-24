# `hardware/storage/reference/`

Reference material for the storage card's level shifting and its receive register.

**Not in git**: PDFs, scans, disk images and archives under any `reference/` are `.gitignore`d (see [the root `reference/` README](../../../reference/README.md)). Expected contents, and what cites each:

| File | What | Cited by |
|---|---|---|
| `74hc_hct595.pdf` | Nexperia 74HC595 **and 74HCT595**, one document | `sdcard.md` §7 — the SD card's receive register is the **HCT** part deliberately, and the reason is an input threshold: 3.3 V `MISO` clears an HCT input's 2.0 V `V_IH`, so the return path needs no level shifter. That number is here and not in the TI HC sheet above |
| `sn74lvc125a.pdf` | TI SN74LVC125A quad bus buffer, 1.65–3.6 V | `sdcard.md` §7 — three of four gates level-shift `SCK`/`MOSI`/`/CS` down to 3.3 V; also `hardware/cpu/docs/plan.md` for the LVC family's 5 V-tolerant inputs |
