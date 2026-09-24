# `software/archive/zelda/` — the Zelda-like room game (retired 2026-09-24)

⛔ **Retired 2026-09-24**, and frozen: nothing builds or runs it. Its source is in
`../nitros9`'s `level2/arm6309/archive/` (`zelda.asm`, `zeldadat.asm`). The world
that stayed is [`../../tilescroll/`](../../tilescroll/), which took zelda's hero and
creatures with it (`bench/cast.py`).

`zelda` is a room game: the overworld as a video3 bitmap playfield with a keyed blit for every actor. It replaced `overworld`, the tile-mode version for the archived `video` card (`../archive/overworld/`).

| | |
|---|---|
| 6809 source | `../nitros9` (branch `arm6309`), `level2/arm6309/cmds/zelda.asm`, `zeldadat.asm` (generated) |
| Generators | `bench/mkgame.py` is the world's terrain model (it writes `model.npz`); `bench/mkzelda.py` builds the tile bank, the keyed art and `zeldadat.asm` from it |
| Data | `bench/zelda.bnk`, `bench/zelda.art` — copied to the card's `/SD0/DATA` by `software/nitros9/mkrom.sh` |
| Bench | ⚠ none yet |
| Video | `make video` / `make sheet` - `video/run-video.sh` |
| Reference | [`reference/`](reference/) |

