# `software/tilescroll/` — Explore: a world of any size, streamed through the ring

`tilescroll` roams a 4096 × 2048 world in `VMODE` 11's square 640 × 480, with the tile bank rotating through the 384 × 512 rectangle of ring the raster never looks at. It is desk's **Explore** icon.

| | |
|---|---|
| 6809 source | `../nitros9` (branch `arm6309`), `level2/arm6309/cmds/tilescroll.asm`, `tilescrolldat.asm` (generated), `modules/tscroll.inc`, `modules/tsdata.inc` |
| Generator | `bench/mktilescroll.py`, with the hero and creatures in `bench/cast.py` (drawn for the retired `zelda`) |
| Bench | `bench/run-tilescroll.sh` — the ring checked byte for byte by `bench/checktilescroll.py`, with two mutations required to fail |
| Docs | [`docs/scrolling.md`](docs/scrolling.md) |
| Video | `make video` (`ACTORS=0` for the engine alone) and `make sheet` - `video/run-video.sh`, the recording in `build/video/` |
| Reference | [`reference/`](reference/) |

