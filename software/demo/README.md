# `software/demo/` — a desktop, a paint program, a BBS and an overworld, on the whole machine

A demo ROM for the end-to-end simulation: a 6809E, the motherboard, the video card **and**
the audio card, running from the boot ROM. It is a tour of the video card's capability list,
[`video/docs/features.md`](../../video/docs/features.md) §0, as a user would see it: a
Haiku-flavoured desktop, a MacPaint mock-up, an ANSI BBS with a few turns of TradeWars 2002,
a raster-bar window, and the scrolling tile-map game. A ProTracker module plays under all of
it from the audio card's `/FIRQ`.

```sh
sh software/demo/build.sh                      # assets, script, layout, assemble -> build/rom.hex
sh software/demo/emu/run-emu.sh 120            # the show on the host emulator, in seconds
VIDEO=1 sh software/demo/emu/run-emu.sh 120    # ... and /tmp/arm6309-emu/emu.mp4, with sound
python3 software/demo/tools/checkdemo.py /tmp/arm6309-emu software/demo/build
sh hardware/gal/verilog/run-demo.sh 118        # the whole machine, every check below,
                                               # /tmp/arm6309-demo/demo.mp4 (H.264, for the web)
POST_ONLY=1 sh hardware/gal/verilog/run-demo.sh   # the checks and the files again, no simulation
sh software/demo/bench/run-replay.sh 40        # the replayer vs refplayer, CPU alone (~2 min)
sh software/demo/bench/run-calib.sh            # bench/calib.asm on the whole machine (~15 min)
```

⚠ **Budget for the machine run.** It is about two and a half minutes of wall clock per
second of machine on a quiet host, so the 115-second show is nearly five hours, and several times
that with other simulations running. The emulator runs the same ROM in about four seconds.

| | |
|---|---|
| `demo.asm` | the main line: handoff, the interpreter's entry, the overworld (`gamego`, the game loop) and both interrupt handlers |
| `gui.asm` | the show's interpreter: every drawing primitive, the pointer, the display-list driver, the ANSI terminal |
| `replay.asm` | the module loader and replayer — `audio/refplayer/mod_replay.c`, transliterated routine for routine |
| `tools/show.py` | the bytecode format, the fonts, the palettes, the icons, and **`Model`**: the same bytes interpreted in Python |
| `tools/mkshow.py` | the story: the desktop, the windows, the paint session, the BBS transcript, the raster window |
| `tools/mkgame.py` | the tiles, the world, the hero's frames and the per-frame script, plus the Python model the checker renders from |
| `tools/mkmod.py` | ⚠ **the stand-in module**, written for the demo (see below) |
| `tools/mkparrots.py` | ⚠ **the stand-in picture**, drawn from primitives, when there is no photograph in `build/` |
| `tools/mkdemorom.py` | the 1 MB ROM layout, and `period_table.c` copied into an include |
| `tools/checkdemo.py` | the frame checker, for either the machine's recording or the emulator's |
| `tools/mkvideo.py` | the H.264 encoder for a recording |
| `tools/tracewav.c` | the audio control: `card.c` driven by a run's timed register writes |
| `emu/` | the host emulator: `cpu6809.c`, and `machine.c`, the map and both cards as the documents describe them |
| `emu/test/run.sh` | the emulator's CPU core against `mc6809e.v`, instruction by instruction |
| `bench/replay_tb.sv` | the replayer on the CPU alone, for iterating in seconds rather than hours |
| `bench/calib.asm` | the card behaviour the model and the emulator assume, measured on the machine |

`build/` is not tracked: everything in it is regenerated.

## The show

In machine seconds, from the emulator's recording of the same ROM:

| s | what happens | what it exercises (`features.md` §0) |
|---|---|---|
| 0 | the desktop is drawn: background, icons, the Deskbar | **640×480 8bpp** (`VMODE 11`); `PaintRect` as span-solid strips chained by `WADV 01`; icons as 1bpp layers in **sprite mode**; glyphs |
| 0–2 | the pointer appears and opens **Audio Player** from the Deskbar's application menu | the **mouse cursor**: save-behind by `VDATA` read-back, the arrow in sprite mode, restore by direct writes; menus drawn and repaired |
| 2–8 | Play: the module's samples upload and it starts; the player closes | the audio card's host port, under a still screen |
| 9–11 | **Files**, a dual-pane browser: a folder and two files selected | icon and row highlighting: selected icon variants, opaque span-mask text |
| 11–14 | the window is dragged by its tab | outline-while-moving: what it uncovers repaired from the desktop's element stack, the rows drawn on release |
| 15–16 | the application menu opens **Paint** | |
| 16–31 | a rubber-banded filled rectangle, a pattern fill, a solid triangle, a patterned star, typed text, rainbow brush strokes | **QuickDraw offload**: `PaintRect`, `FillRect` with a pattern (span-mask columns), **polygon fills** (edges stepped on the 6809, runs span-solid), patterned polygons (a solid run and sprite-mode pattern bytes), glyph blits, horizontal spans |
| 31–36 | the scroll bar drags the canvas 384 pixels, eased a pixel at a time, to show art drawn off the screen, and back | **scroll**: a **display list** moves `HSCROLL` on the canvas's lines only — byte-granular, `graphics.md` §19 item 49 — by patching two operand bytes a frame |
| 36–41 | Goodies > Wave: the canvas ripples and settles | a **per-scanline `HSCROLL`** list: a fine offset every two lines, rewritten every frame |
| 41–44 | File > Open... lists `parrot.img` in a file chooser | menus, a dialog, a pressed button |
| 44–52 | the photograph loads into the canvas and stays five seconds | an **8bpp copy**: the one thing §7 says the CPU does, 220,800 bytes through `VDATA` |
| 53 | the window closes; the whole desktop is redrawn | |
| 54–71 | "Connect to BBS": `ATDT`, `CONNECT 19200`, the board's menus in 80×30, TradeWars 2002 in 80×50 — two sectors, two port trades — then the board, `NO CARRIER` | **640×240** (`VMODE 01`) and **640×400** (`VMODE 10`); **text** at 13 writes a cell with a colour per cell; ANSI SGR, cursor positioning and erase; the terminal **scrolls by `VSCROLL`**, not by copying |
| 72 | back to the desktop | |
| 73–81 | "Raster Bars Demo": a window whose one palette entry is rewritten on every scanline | **display list**, per-scanline palette: three bars moving across 200 lines, every frame |
| 82–105 | "Zelda": the overworld, four screens walked through, then back to the desktop | **tiles** (cell mode, `VMODE 00` 640×200), fine scroll in both axes, the software sprite composite, the **VBL interrupt** |
| 105–109 | the Audio Player again: Stop | the replayer's timer, channels and enable turned off (`gui.asm`'s `STOP`) |

## How it is checked

**The script is bytecode, and two things run it.** `mkshow.py` writes `build/script.bin`
through `show.Script`. The 6809 interprets it (`gui.asm`), and `show.Model` interprets the same
bytes in Python, drawing into a 1024 × 512 ring the way `features.md` says the card does.
They share the script and nothing else: not a line of drawing code, not the polygon rule
(`Model.spans` and `gui.asm`'s `po*` are each written from the rule, which `show.py` states).

**A checkpoint is a picture the screen must be.** `CHECK id` in the script stores the
model's picture of the screen, and the 6809 writes `id` to `$C600` once the card is idle.
Every drawing operation clears it first. `demo_tb` reads the word at each frame's first and
last active dots, so a frame is judged only if nothing was drawn while it was scanned, and
then it must equal the picture **pixel for pixel**, through the palette. A checkpoint that
depends on a display list is judged only if a list was running at line 1, and the raster
window's frames are judged at the phase whose list that frame ran (`$C602`).

| claim | check |
|---|---|
| every one of the script's checkpoints reached the connector, and every frame judged at one is the model's picture | `checkdemo.py` against `build/show.npz` |
| the raster bars are right at every phase | `checkdemo.py`: each frame's list phase rendered by `show.raster_colours` |
| a list-driven picture had its list | `checkdemo.py`: `LRUN` at line 1, from the bench |
| the game draws what its own state says | `checkdemo.py`: every game frame equals `mkgame.render()` for the camera and hero records read from the SIMM at that frame |
| the game keeps the blank's budget | `checkdemo.py`, from `marks.txt` |
| the 6809 replayer writes the same register stream as `mod_replay.c` | `run-demo.sh`: refplayer's trace against the backplane's, byte for byte, over the whole run |
| the 6809 loader relocates the samples as `mod_load.c` does | `run-replay.sh` on `build/rom-replay.bin`, the replayer alone |
| the card makes the sound its register stream specifies | `run-demo.sh`: `dacwav`'s render of the RTL card's converter codes, A/B'd against libopenmpt with `tracewav.c` as the control |
| both interrupts are taken, and nothing fights on the bus | `demo_tb`'s claims |

⚠ **Why refplayer is not the audio control here.** `check:modplay` gates the card against
refplayer because both get the register stream at refplayer's timing. In this run the 6809
makes the writes, and a row tick takes it up to about 4 ms. Every note therefore starts
later than refplayer's, and scoring the card against refplayer measures the CPU. `tracewav`
replays the run's own timed writes through `card.c`, so what remains is the card.

## The emulator, and what it is for

⚠ **`emu/` is not the machine.** It is the card as the documents say it behaves, and a 6809
that is. It runs the ROM forty times faster than real time, writes the same `frames.bin`,
`card.trace` and `card.times` as `demo_tb`, and `checkdemo.py` reads either. A picture that is
right in the emulator and wrong on the machine is a finding about the card or the documents.
A picture that is wrong in the emulator is a bug in the 6809 code, found in seconds.

- **The CPU core** is checked against `mc6809e.v` by `emu/test/run.sh`: every register at
  every instruction boundary and every write with its E cycle, over generated programs with
  random interrupts and over the whole replayer. Where the Verilog differs from the
  datasheet (SWI's cycle count, SEX's flags, SWI3's vector), the core does what the Verilog
  does. `cpu6809.h` lists the differences.
- **The card** is `machine.c`. Three of its behaviours are measured rather than read, by
  `bench/calib.asm` on the machine. An effect after *n* list `WAIT`s from a `GO` inside line
  0 shows on line *n*, and one before the first `WAIT` shows on line 1. Palette `MOVE`s land
  the same way. `VDATA` reads return the byte at `WPTR` and step it. `calib.asm` also
  confirms sprite and mask bit order, `WADV 01`'s column reload and `VSCROLL` in a
  line-doubled mode.
- **What it cannot see**: anything the documents get wrong. It found none of the machine's
  defects, and was not meant to.

## The picture and the module

```sh
cp photo.jpg software/demo/build/parrots-image.jpg     # the picture parrot.img is made from
MOD=path/to/song.mod sh software/demo/build.sh         # the module (it is copied to demo.mod)
```

- **`parrot.img`** is `build/parrots-image.jpg` scaled to 640 wide, centre-cropped to 640 × 345
  (the canvas) and Floyd–Steinberg dithered onto the desktop palette's 6 × 8 × 5 cube. Without
  a photograph, `mkparrots.py` draws a stand-in illustration.
- **The palettes.** The desktop is 16 Haiku colours and a 240-colour cube (`show.gui_palette`).
  The BBS swaps the first 16 for ANSI's. The game loads RGB332. Each is written with the
  display off or in vertical blanks, 32 entries a blank (`graphics.md` §13.1).
- **The fonts** are console-setup's `Uni2-VGA16` and `Uni2-VGA8`, read from
  `/usr/share/consolefonts` at build time and mapped to CP437. The shade and half-block
  cells, which those fonts lack, are drawn by `show.font`.
- **The module** is any 31-sample, 4-channel `M.K.` file. Without `MOD`, `mkmod.py` writes an
  original stand-in tune that uses every effect the replayer implements. "Guitar Slinger" is
  406 KB: 41 patterns and 363 KB of samples, uploaded in about five seconds of machine time
  while the desktop stands.

## The ROM, and how boot finds it

`boot.asm` section 11: after its own tests, the boot ROM maps ROM pages 1 and 2 at `$8000`
and jumps to `$8004` if `$8000` holds `"6309"`. The code is 10.9 KB of those 16. The assets
start at page 3, one page boundary each, and `build/assets.inc` gives the 6809 each one's
first page: the module, the script, the fonts, the icons, the picture, and the game's tiles,
world, sprites and frame records.

**The logical map while the show runs.** Block 0 is the script window: `U` is the script
pointer inside it, and it moves on a page at a time. Block 1 is the data window: fonts, icons
or picture. Blocks 2–3 are the replayer's pattern window and belong to `/FIRQ`. Blocks 4–5
are the code. Block 6 is the SIMM: boot's variables, `demo.asm`'s from `$C200`, `gui.asm`'s
from `$C600`, and the stack. Block 7 is boot's page and the vectors.

The boot ROM's IRQ and FIRQ vectors jump through RAM words at `$C004` and `$C006`, which
boot points at `halt` and the demo claims.

`build/rom-replay.bin` is the same image assembled with `REPLAY`: it loads and plays the
module and does nothing else. It exists for the benches that have no video card
(`run-replay.sh`, `emu/test/run.sh`), where the show would wait for a vertical blank that
never comes.

## What it found

- ⛔ **A display-list `HSCROLL` with bits 1..0 ≠ 0 scrambled the line** — `graphics.md` §19
  item 49, closed 2026-09-13. `calib.asm` listed 1, 2, 3, 5, 6 and 7: a CPU write displayed
  exactly, and a listed one showed each four-pixel group's bytes in the wrong order, because
  the list wrote `vsup`'s copy of the fine bits and not `vctrl`'s, which the pixel mux selects
  on. `vctrl`'s copy now has the list's write port, and `vaddr_tb` sweeps a listed `HSCROLL`
  over every pixel of a line. The paint program's scroll and its wave use it.
- ⛔ **The VBL interrupt's acknowledgement broke chained fills, twice.** The first machine
  run drew one and a half strips of the desktop's background and stopped: the handler's
  `VSTAT` write landed under a `WADV 01` span-solid, which §7.4's rule forbids, and
  `vblwork` now waits out `SPANBUSY` first. The next run drew the Files window's tab at
  column 64, which was a **card defect** — `graphics.md` §19 item 50, closed 2026-09-13: the
  column reload after a chained span is two register-file reads on the dot `SPANBUSY`
  falls, and the `VSTAT` poll that saw it fall kept the file's address, so the column
  loaded `VSTAT`'s byte (the handler's last acknowledgement, `$40`). The reload owns the
  address for its two dots now, and `vspan_tb` polls across a chained span's end at 24
  phases. The emulator reports a card register write under a span or a running list.
- **Cell mode's fine horizontal scroll** — `graphics.md` §19 item 48, closed 2026-09-13. At
  `HSCROLL[2:0]` = 4 every frame the card produced equalled a model in which pixel columns
  0–3 of each cell came from the cell to their left. `mkgame.render_cells(...,
  stale_half=True)` is that model, and `checkdemo.py` still counts game frames against it, so
  a regression would be named rather than just counted.

## The budget, measured

| | |
|---|---|
| the VBL `/IRQ` | 0.381 ms (12 lines) after `VBLANK` rises, leaving 1.18 ms of the 1.563 ms blank |
| a hero flip | 0.29–0.53 ms of that, 600–1,100 E cycles, no `/WAIT` |
| a replayer tick from `/FIRQ` | 958–8,900 E cycles, mean ~2,240: 5.3% of the 6809E at 50 Hz |

A tick can run up to 4.2 ms and entering FIRQ masks IRQ too, so `firqh` unmasks IRQ. Without
that, a tick running at the VBL interrupt pushed the scroll write 13 rows into the picture.

⚠ **And a tick can cost a display list its frame.** A list must be started inside line 0 for
its `WAIT`s to mean lines. So while a list is active, `gui.asm`'s `wready` returns with
`/FIRQ` masked from the end of one list to the next `GO`, and `golist` masks `/IRQ` too for
the blank. The replayer's tick waits up to about 3 ms and then runs while the list walks.
Without that, a tick that began just before the blank ran past line 0 every 42nd frame of the
paint scroll: 50 Hz beating against 59.94 Hz.

⚠ **A list that runs every frame leaves the CPU the rest of the frame to draw in, and no
more.** The list owns `WPTR` from its `GO` to its `END` (`graphics.md` §10.3.1). The paint
canvas's list ends at line 430, which leaves about 2 ms before the blank. Each drag step of
the scroll bar is ~8 ms of drawing: the pointer's save-behind and restore, and the thumb's
changed columns. So a step takes about five frames, and the list has to be restarted from
*inside* the drawing. `lyield`, at the top of every `setxy` and every script op, does that
once the blank's VBL has come. Until 2026-09-14 only `SYNC` started the list, at the end of
a step. The list then ran in one frame of two, and every other frame showed the canvas at
`HSCROLL` 0: a 30 Hz flicker that a 60 fps player showed as flicker, or as a jump, depending
on which frames it kept.

⚠ **The VBL interrupt is served inside `golist`.** Its handler acknowledges by writing
`VSTAT`, and a register write while a list walks costs the list a descriptor byte
(`graphics.md` §10.3.3). `/IRQ` arrives a dozen lines into the blank, so with interrupts
masked around the `GO` it would be taken just after it. The emulator raises `/IRQ` on that
line and fails a run that writes a card register under `LRUN`. Before `golist` served the
request, the show made 321 such writes.

## What it does not show

- **Timing.** Like every bench here, the simulation models logic, not propagation delay.
  A run that passes says the design is logically consistent end to end. It does not say the
  boards meet setup and hold at 25 MHz; `cpld/*.fit` and the hardware do.
- **A 6309.** The core is a 6809E. Nothing here uses a 6309 instruction.
- **Double buffering** (§0's "Buffers") is not exercised: the desktop uses 480 of the ring's
  512 rows, and nothing flips.
- **Cell-mode text** (§2.4, one write a cell) is not exercised. The terminal is span-writer
  text, which is the mode a colour BBS needs.
