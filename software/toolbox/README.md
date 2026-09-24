# `software/toolbox/` — the ROM toolbox

The boot ROM's reusable drawing routines — text in proportional faces through a glyph strike, rectangles, copies, icons — called by `boot.asm`'s boot dialog before there is an OS and by CoArm after.

| | |
|---|---|
| 6809 source | `../nitros9` (branch `arm6309`), `level2/arm6309/modules/tbox.asm` (ROM page 64 on, built under `V3=1`); the host callback tables in CoArm and in `software/boot/boot.asm` must match its `TV.*` equates |
| Tools | `tools/mktbox.py` (the ROM pages: fonts, icons, the document), `tools/mkfonts.py`, `tools/mkcp437.py` |
| Bench | `bench/run-v3text.sh` — what a text call costs, and the glyph strike pixel for pixel against composition |
| Docs | [`docs/proportional-font.md`](docs/proportional-font.md) |
| Reference | [`reference/`](reference/): `parrots-image.jpg`, the photograph the toolbox's document page shows (supplied, not tracked) |

