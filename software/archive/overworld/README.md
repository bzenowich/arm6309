# `software/archive/overworld/` — the tile-mode overworld (retired 2026-09-23)

`overworld` drew the Zelda-like world in the archived `video/` card's tile mode,
through the `libvid` subroutine module. [`../../zelda/`](../../zelda/) is the same
world as a video3 bitmap playfield and replaced it. The 6809 sources
(`overworld.asm`, `libvid.asm`) are in `../nitros9`'s `level2/arm6309/archive/`.

| File | What |
|---|---|
| `vgmodel.py` | the game's streams (`vggame`) and the video card model they were checked against; `software/nitros9/mkrom.sh` ran `--emit` until the retirement |
| `vgshapes.py` | shapes for the same |
| `checkvid.py` | the checker the archived `video/` benches used |

The world's terrain model, `mkgame.py`, is **not** here: it is live, in
`../../zelda/bench/`, because `mkzelda.py` builds `zelda`'s world from it.
