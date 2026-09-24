# `hardware/io/ps2/reference/`

Reference material for the PS/2 card's shift register and counter, and prior art for the mouse.

**Not in git**: PDFs, scans, disk images and archives under any `reference/` are `.gitignore`d (see [the root `reference/` README](../../../../reference/README.md)). Expected contents, and what cites each:

| File | What | Cited by |
|---|---|---|
| `sn74hc595.pdf` | TI SN74HC595 8-bit shift register with output latch | `ps2.md` §3 — the receive shift register |
| `sn74hc193.pdf` | TI SN74HC193 4-bit up/down counter | `ps2.md` |
| `folklore-apple2-mouse-card.pdf` | Andy Hertzfeld, *Apple II Mouse Card*, folklore.org, June 1981. Burrell Smith's two-chip mouse interface: a 6522 VIA and a dual flip-flop, where the Apple II division later shipped "more than a dozen" chips. | `hardware/io/ps2/docs/ps2.md` §4.4 — the interrupt argument, the derive-it-from-the-bus habit, and §4.4(c)'s rejection of interrupt-per-notch |
