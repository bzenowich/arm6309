# `software/tools/video/` — contact sheets and demo videos, made by programs

⭐ **A demo is reviewed from its contact sheet before a video is made.** So every
program has the same two targets, and they are meant to be run in this order:

```sh
make -C software/<program> sheet    # record the run, and a contact sheet of it -> build/video/sheet.png
make -C software/<program> video    # the H.264 file OF THAT SAME RUN            -> video/*.mp4
```

`sheet` keeps the recording; `video` encodes exactly the run the sheet was made
from, so what was approved is what is published. With no sheet, or `FRESH=1`,
`video` records first. `make -C software sheet` / `video` (or `make sheet` /
`make video` at the root) do every program.

Each program's `video/run-video.sh` is a few lines: the command typed at the
shell, how long to run, and how to cut the scene. The work is in two tools here:

| | |
|---|---|
| [`record.sh`](record.sh) | boots NitrOS-9 off the system card on the host emulator (`software/emu/`), types `LINES` at the serial shell, optionally drives the mouse with a `PS2_SCRIPT`, and keeps every frame in `OUT/frames.bin`. The ROM and card are `software/nitros9/build/rom/`'s, built by `make -C software/nitros9 rom` if missing |
| [`clip.py`](clip.py) | cuts a window out of the recording — `--from/--to`, `--all`, or `--auto`, which finds the scene as the frames no one colour covers 70 % of — and encodes it at 2×, 30 fps, x264 `-crf 20`, faststart; or `--sheet` for a contact sheet. It deletes the recording afterwards unless `--keep` |

These are the settings the scroll, zelda and pinball clips of 2026-09-23 were
made with, when they were one-off commands; `software/archive/` has the
recorded-session videos from before, whose scripts are archived with them.

| Program | Output | The run |
|---|---|---|
| boot | `software/boot/video/boot-demo.mp4` | from the reset vector (`COLDBOOT=1`): the POST, the dialog, NitrOS-9 off the card, the desktop, the file manager |
| desk | `software/desk/video/desk-demo.mp4` | its own, older `run-desk.sh`, with the serial console beside the screen; `sheet` writes `build/video/sheet-*.png` |
| paint | `software/paint/video/{v3bbs,v3art,v3paint}.mp4` | each viewer; `WHICH=v3bbs` (etc.) for one. `v3art` is *we-tortuga* and needs `reference/we-tortuga.ans` |
| pcs | `software/pcs/video/pcs-play.mp4` | mode 20, played by `bench/scripts/pcsplay.ps2`. (`make tables` is the every-table sheet) |
| stardew | `software/stardew/video/stardew-demo.mp4` | `stardew 0 1050 7`, on a card with the farm's picture; `--hold 1.5` cuts the still wait before the camera moves |
| tilescroll | `software/tilescroll/video/tilescroll-actors.mp4` | `tilescroll 0 1200 5`; `ACTORS=0` → `tilescroll-demo.mp4` |
| monster, mvania | `software/<program>/video/*-demo.mp4` | the settings their benches measure |

`clip.py`'s options: `--scene CMD` (the window, off the serial log), `--all`,
`--from/--to`, `--until TEXT --tail S`, `--hold S` (no still stretch longer than S),
`--max S`, `--sheet PNG --tiles N`. `record.sh`'s: `LINES`, `SECS`, `PS2FILE`,
`CARD_DATA`/`CARD_DEMOS` (a card of its own), `EMUENV`, `NOBUILD`.

⚠ Videos are never committed (`*.mp4` is ignored): they are regenerated. Every
one needs `../nitros9` on its `arm6309` branch, and ffmpeg, which
`make -C software/tools ffmpeg` fetches into `.tools/`.
