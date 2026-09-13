# `software/demo/` — parrots, an overworld, and a module, on the whole machine

A demo ROM for the end-to-end simulation: a 6809E, the motherboard, the video card **and**
the audio card, running from the boot ROM. It shows a 640 × 480 RGB332 picture, holds it
for five seconds, and then runs a scrolling tile-map game in cell mode. A ProTracker
module plays under both, from the audio card's `/FIRQ`.

```sh
sh software/demo/build.sh                      # assets, layout, assemble -> build/rom.hex
QUICK=1 sh software/demo/build.sh              # ... with a 16-row picture and a short hold
sh software/demo/bench/run-replay.sh 40        # the replayer vs refplayer, CPU alone (~2 min)
sh hardware/gal/verilog/run-demo.sh 27         # the whole machine (~1.5-2 h), every check
                                               # below, and /tmp/arm6309-demo/demo.mp4
POST_ONLY=1 sh hardware/gal/verilog/run-demo.sh   # the checks and the file again, no simulation
```

| | |
|---|---|
| `demo.asm` | the main line: handoff, palette, the picture, the hold, the game loop, both interrupt handlers |
| `replay.asm` | the module loader and replayer — `audio/refplayer/mod_replay.c`, transliterated routine for routine |
| `tools/mkmod.py` | ⚠ **the stand-in module**, written for the demo (see below) |
| `tools/mkparrots.py` | ⚠ **the stand-in picture**, drawn from primitives. `--src photo.jpg` reduces a real one instead |
| `tools/mkgame.py` | the tiles, the world, the hero's frames and the per-frame script, plus the Python model the checker renders from |
| `tools/mkdemorom.py` | the 1 MB ROM layout, and `period_table.c` copied into an include |
| `bench/replay_tb.sv` | the replayer on the CPU alone, for iterating in seconds rather than hours. `run-replay.sh` diffs it against refplayer; all 22 probe modules from `mkprobe.py` match |
| `tools/tracewav.c` | the audio control: `card.c` driven by the run's timed register writes |
| `tools/checkdemo.py`, `tools/mkvideo.py` | the frame checker and the H.265 encoder for `demo_tb`'s recordings |

`build/` is not tracked: everything in it is regenerated.

## The picture and the module

The demo is built from two files in `build/`, which is not tracked:

```sh
python3 tools/mkparrots.py build/parrots.raw build/parrots.png --src build/parrots-image.jpg
MOD=build/Guitar-Slinger.mod sh build.sh
```

- **The picture** is centre-cropped to 4:3, resized to 640 × 480 and Floyd–Steinberg
  dithered onto RGB332. Without `--src`, `mkparrots.py` draws a stand-in illustration.
- **The module** is any 31-sample, 4-channel `M.K.` file. Without `MOD`, `mkmod.py`
  writes an original stand-in tune that uses every effect the replayer implements.
  "Guitar Slinger" is 406 KB: 41 patterns and 363 KB of samples. The samples go in the
  audio card's 512 KB, and the file takes 50 of the ROM's 128 pages. The 6809 uploads
  them in about 5 s of machine time, which is the black screen before the music starts.

## The ROM, and how boot finds it

`boot.asm` section 11: after its own tests, the boot ROM maps ROM pages 1 and 2 at `$8000`
and jumps to `$8004` if `$8000` holds `"6309"`. Without a program there, it restores the
two blocks and halts as it always did. The demo's assets start at page 3, one page boundary
each, and `build/assets.inc` gives the 6809 each one's first page.

The boot ROM's IRQ and FIRQ vectors now jump through RAM words at `$C004` and `$C006`, which
boot points at `halt`. That is `machine.md` §7.2's "fixed RAM jump table", and the demo
claims both.

## What is checked, and against what

| claim | check |
|---|---|
| the 6809 replayer writes the same register stream as `mod_replay.c` | `run-replay.sh`: refplayer's `--trace` against the bench's, byte for byte, over the whole run |
| the 6809 loader relocates the samples as `mod_load.c` does | the same script: refplayer's `--sram` image against the bytes the 6809 sent to `SDATA` |
| the stream survives the real bus and the real card | `demo_tb`'s `card.trace`, recorded at the backplane, against refplayer's |
| the picture reaches the connector | `checkdemo.py`: every frame after the paint equals `parrots.raw` through the palette, pixel for pixel |
| the game draws what its own state says | `checkdemo.py`: every game frame equals `mkgame.render()` for the camera and hero records read from the SIMM at that frame |
| the card makes the sound its register stream specifies | `run-demo.sh`: `dacwav`'s render of the RTL card's converter codes, A/B'd against libopenmpt with **`tracewav.c` as the control**: `card.c` fed the same writes at the colour clocks they reached the card |
| both interrupts are taken, and nothing fights on the bus | `demo_tb`'s claims |
| the game keeps the blank's budget | `checkdemo.py`, from `marks.txt`: when each flip started and ended against VBLANK and the first active dot, and what each replayer tick cost in E cycles |

⚠ **Why refplayer is not the audio control here.** `check:modplay` gates the card against
refplayer because both get the register stream at refplayer's timing. In this run the 6809
makes the writes, and a row tick takes it up to about 4 ms. Every note therefore starts
later than refplayer's, and scoring the card against refplayer measures the CPU. `tracewav`
replays the run's own timed writes through `card.c`, so what remains is the card.

## What it found: cell mode's fine horizontal scroll, since fixed

`graphics.md` §19 item 48, closed 2026-09-13. At `HSCROLL[2:0]` = 4 every frame the card
produced equalled a model in which pixel columns 0–3 of each cell came from the cell to
their left. The map pipeline's handover was phased on the unscrolled slot counter.
`mkgame.render_cells(..., stale_half=True)` is that model, and `checkdemo.py` still counts
frames against it, so a regression would be named rather than just counted. The demo
moves the camera in steps of 4, which is what exposed the defect.

## The budget, measured

| | |
|---|---|
| the VBL `/IRQ` | 0.381 ms (12 lines) after `VBLANK` rises, leaving 1.18 ms of the 1.563 ms blank |
| a hero flip | 0.29–0.53 ms of that, 600–1,100 E cycles, no `/WAIT` |
| a replayer tick from `/FIRQ` | 958–8,900 E cycles, mean ~2,240: 5.3% of the 6809E at 50 Hz |

A tick can run up to 4.2 ms and entering FIRQ masks IRQ too, so `firqh` unmasks IRQ. Without
that, a tick running at the VBL interrupt pushed the scroll write 13 rows into the picture.

## What it does not show

- **Timing.** Like every bench here, the simulation models logic, not propagation delay.
  A run that passes says the design is logically consistent end to end. It does not say the
  boards meet setup and hold at 25 MHz; `cpld/*.fit` and the hardware do.
- **A 6309.** The core is a 6809E. The replayer and the game use no 6309 instructions,
  so native mode would only make them faster.
