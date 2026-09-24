# `software/paint/` — Paint, the BBS and ANSI art

`v3paint`, `v3bbs` and `v3art` are one program (`v3strm.inc`): open a recorded CoArm stream, send it to standard output and hold the picture up. Each is a desktop icon.

| | |
|---|---|
| 6809 source | `../nitros9` (branch `arm6309`), `level2/arm6309/cmds/v3paint.asm`, `v3bbs.asm`, `v3art.asm`, `v3strm.inc` |
| Generator | `tools/v3show.py` writes the streams; `software/nitros9/mkrom.sh` runs it |
| Video | `make video-bbs`, `video-art`, `video-paint` (and `sheet-*`) - `video/run-video.sh` |
| Reference | [`reference/`](reference/): Blocktronics' *we-tortuga* ANSI and its reference render — not this project's work, so not tracked. ⚠ **`v3art` is we-tortuga and nothing else** since 2026-09-24: without the file there is no `v3art` (the project's own piece that stood in is in `../archive/paint/`) |

