# `video3/bench/` — the host-emulator model

**video3 is modelled in `software/demo/emu/machine.c` beside `video/`, not instead
of it.** `VIDEO3=1` selects it; without it the emulator is the card it always was,
so `run-emu.sh`, `run-vid.sh` and `software/nitros9/run-emu.sh` are unaffected.

```sh
sh video3/bench/run-v3.sh            # all four, ~1 min. Its exit code is the answer
sh video3/bench/run-v3mv.sh          # ⭐ the metroidvania scene, ~20 min
sh video3/bench/run-v3mon.sh         # ⭐ the block-streamed platform world, ~6 min
sh video3/bench/run-v3pin.sh         # ⭐ the pinball table, READ OFF THE CARD, ~30 min
sh video3/bench/run-v3star.sh        # ⭐ the farm, and the DAY in the palette, ~25 min
sh video3/bench/run-v3sd.sh          # ⭐ the desktop, Paint and a demo OFF THE SD CARD, ~3 min
sh video3/bench/run-v3desk.sh        # ⭐ THE DESKTOP SHELL, CLICKED AT, ~3 min
sh video3/bench/run-v3files.sh       # ⭐ ITS FILE MANAGER, AND THE LISTING READ, ~11 min
```

⭐ **`run-v3desk.sh` is the one that drives a program with a MOUSE.** Everything else
here types a command and reads the picture; this one runs `desk` (the shell -
`docs/boot-and-desktop.md` §3) off the card and clicks at it with a `PS2_SCRIPT`
(`software/demo/emu/ps2script.h`), then reads every answer off the recorded frames:
the menu bar's rows, the pull-down appearing where nothing was, the highlight landing
on the item the pointer is over, the rectangle's CRC coming back to what was under it,
and **Paint's own page** as the evidence that a menu item forked a program. ⛔ With a
control that walks the bar and never clicks, in which the pull-down's rectangle must
hold exactly **one** picture for the whole run - a desktop that drew a menu on a timer
would pass every other claim. ⭐ Its geometry and its menu table are **parsed out of
`desk.asm`**, so an item renamed or un-greyed moves the claims with it. **47 claims.**

⭐ **`run-v3files.sh` is the one that READS THE SCREEN BACK AS TEXT.** `desk`'s file
manager (`docs/boot-and-desktop.md` §3.6) lists a real directory, so the question is
not "did something get drawn" but "is what was drawn what is on the card". It
rebuilds every candidate name out of **the ROM's own font blob** — the two-bits-a-pixel
glyphs `software/nitros9/tools/mktbox.py` wrote into ROM pages 65 on — and matches
them against the pixels of each row; the names it prints are then compared with what
the host's **`os9 dir`** says is on the image. Two independent readers of one
directory, and the card's output in between. ⛔ With a control whose window is already
up (`desk /w3 N /SD0/DATA`) and whose mouse walks the list, both scroll arrows, the
menu bar and a desktop icon **without ever pressing** — the list must hold exactly one
picture, and **it must still be the real listing**, so a blank window is not what
passes it. ⭐ And a third run driving **`v3trk`** into the same rectangle from the
shell, because since 2026-09-21 the two programs share one directory reader
(`modules/v3dir.inc`). **65 claims.**

| Exerciser | plan | What only it can catch |
|---|---|---|
| `run-v3char.sh` | §2.2, §2.5, §3, §2.1 | ⭐ **all four geometries — 80×25, 80×30, 80×50 and 80×60** — with the active-line count and the `CTRL` read-back asserted per frame. The last two are what `video` cannot reach in cell mode at all (`graphics.md` §6.4.1's five-bit cell row), so they are the reason this card exists. And the attribute reaching the LUT's **high** eight address lines: Row 0 walks the *attribute* under one glyph, row 1 walks the *glyph* under one attribute, the rest mixes both — so ignoring the attribute, swapping the two halves of the address, or reading the map on the wrong stride each fail on a different row. A cell is **four** bytes — the code at **+0**, the attribute at **+2** and the odd two never read — and the ROM fills those two with a code and an attribute that are not the cell's, so reading the wrong lanes fails too. ⭐ **And the map goes in with `WADV` b2 set** (§2.5's step-by-two), in two passes: the first from an *odd* address fills the decoy lanes, the second from the even one writes the cell in **two** stores. A pointer that steps by one lays the cell down on top of the decoys and every row is wrong |
| `run-v3copy.sh` | §6, keyed-copy.md | **fourteen copies** — aligned and unaligned columns, both directions in both axes, and **four overlapping**, which is where a direction bit that walks the wrong way destroys its own source. Bitmap mode makes VRAM observable: a byte *is* a palette index *is* a pixel. ⭐ **And four of them are the COLOUR KEY**: a 16 × 16 shape whose holes are index 0 and whose ink never is, copied over a background that is not zero — once keyed (the ink lands, the background stands), once **not** keyed with everything else the same (the holes land as black), once keyed at **column 401, 1 mod 4**, because the key drops one lane's byte enable and a keyed write on the wrong lane shows there and not at column 0, and once keyed from a source whose only zero is a **single pixel**. ⛔ `WMODE` 11 arms it and nothing else does, so the run writes `CTRL` back to 00 after each keyed copy and a card that latched the mode fails the next plain one |
| `run-v3tile.sh` | §2.4, §8.1 | the **one-byte** code in lane 0 of a **four-byte** cell (the ROM fills lanes 1–3 with values that are never the cell's code, so a wrong stride or lane shows), 8bpp tiles with no per-cell colour limit, **both scroll axes one pixel at a time, including both ring wraps**, the six-bit cell row at row 63 rolling to 0, **and all four VMODEs** — a vertical ring wrap is a different test in a progressive family, which shows twice the picture rows. ⭐ **And that `ATTR` is zero in tile mode**: every one of the LUT's 65,536 entries is loaded bright green *except* sub-palette 0, so a leak from the attribute path paints the screen |
| `run-v3sprite.sh` | §7 | ⭐ **the shape read from VRAM** — the top 64 bytes of `MAPBASE`'s region, `$7FFC0` at `MAPBASE` 7 — with a decoy (the shape inverted) at `MAPBASE` 0's `$0FFC0`, so a card that ignores `MAPBASE` draws the wrong arrow. **Thirty-six positions in one run** — every X phase mod 8, both 4-byte phases, both screen edges, the line-doubling boundary **and all four VMODEs**, because the sprite covers eight *picture* rows either way: sixteen scanlines in the doubled families and eight in the progressive ones. The ROM writes each position to `$C208`/`$C20A`, the two words `machine.c` records with **every** frame (`overworld`'s camera mechanism), so each frame is judged against its own position |

Each generator writes an `.asm` **and** a `.json`; `../tools/v3model.py` reads the
JSON and renders from the plan.

⭐ **The ROM and the model share the JSON — the data — and no code.** Two
implementations of the plan agreeing is evidence; one implementation agreeing with
itself is not. That is the discipline `software/nitros9/tools/vtmodel.py` keeps, and
`v3model.py` reuses `software/demo/tools/frames.py` so the recording's format is not
transcribed twice either.

### ⭐ `run-v3mv.sh` — the metroidvania scene, and the frame budget measured on it

`bench/v3char`, `v3copy`, `v3tile` and `v3sprite` ask *does the card do what the
plan says*. This one asks the other question: **with the card doing exactly
that, what can a game put on the screen?** `keyed-copy.md` §6.3 names a
metroidvania as this card's natural genre; `optimizations.md` entries 4 and 5
took the per-copy cost to 344 µs and built the colour key. The scene is where
that gets spent.

```sh
sh video3/bench/run-v3mv.sh            # eleven runs + the tearing gate, ~20 min. Its exit code is the answer
```

| | |
|---|---|
| The scene | `mvania`, a NitrOS-9 command in the port's tree (`level2/arm6309/cmds/mvania.asm`). A 1024 × 240 room at ring rows 0-239 with a **clean copy at 240-479**, the 640 × 200 view scrolled over it by `HSCROLL`/`VSCROLL` with **no refill**, the hero on the card's one hardware sprite, and every other actor drawn either by the span writer's **sprite `WMODE`** or by a **⭐ keyed copy** — and undrawn with a plain copy from the clean page |
| The instrument | a store to **`$FF2E`**, which decodes nowhere on the board (`demo.asm`'s `MARK`) and which the emulator timestamps into `marks.txt` in picoseconds. One byte a phase boundary, so the cost split is read off the recording rather than estimated. ⚠ Seven stores a frame, ~17 µs of 14,300, and they are inside every number |
| The sweep | 2, 4, 6 … 28 actors, 45 frames a step — about fifteen seconds |
| The modes | `mvania`'s mode argument is a bit field, and each bit is one leg of the experiment: keyed copy against sprite `WMODE`, the card's own registers against `SS.CopyN`, merged restores against one a rectangle, interleaved against two phases, one run with **no restores at all**, and ⭐ **four ways to commit the scroll** — `SS.Scroll`, `SS.Batch`, a register write mid-frame (which tears) and a register write in the blank |
| ⛔ The tearing gate | **the scroll pair has to reach the card inside `VBLANK`**, which is the whole reason the commit is the VBL service's. It is not an opinion: the emulator writes `VBLANK`'s rise (`V`) and each frame's first active line (`A`) into `marks.txt` beside the marks, so a ROM built with `-DBTMARK=1` (`defs/armvid.d`) marks every commit and `checkv3mv.py --blank` reads each against the blank it claims. ⭐ **With a negative control**: mode 9 writes the same two registers wherever the raster is, and **616 of its 630 writes are in the picture** — a blank is 49 lines of 449, so a gate that could not fail would still read ~11% |
| ⛔ The gate | **not the timings.** The scene ends by restoring every actor, and nothing but the actors ever writes ring rows 0-239 — so **the live page must then equal the clean page byte for byte**, which `checkv3mv.py` asserts against a `VRAMDUMP`. One pixel left behind by the merge, a dropped rectangle or a wrong source row fails it, where a timing run would call the same frame a good measurement |
| The output | `checkv3mv.py` prints the budget per actor count and writes the **contact sheets** the scene is reviewed from |
| ⭐ What it found, 2026-09-19 | **the scroll commit was the biggest line item in the frame** — 1.90 ms of 14.3 for four register writes and two tags, more than every actor restore together. The split says only 0.77 ms of it was the driver's (`F$Move` 0.49, validating the records 0.16, building them 0.11, the `VG.BtOn` handshake 0.07, **the `F$Sleep` on a pending batch 0.00**); the other 1.05 ms is IOMan, SCF and the return. `SS.Scroll` takes the 0.77 out — **1.90 → 1.13 ms, and 18 actors → 19** — and mode b8, which needs no call at all, gets **21**. `optimizations.md` entry 9 |

### ⭐ What the scene is for, and what it must show

⛔ **THE SCENE IS THE CARD'S SHOP WINDOW, and the thing to show off is COLOUR.**
video3's whole argument is a 64K × 16 LUT the picture addresses with a byte a pixel
(plan §3) — 256 simultaneous colours out of 65,536 in bitmap mode, where the machine's
other card has a 16-entry palette. The scene should look like it:

| | |
|---|---|
| the room | a **256-colour** background, dithered with **Floyd–Steinberg** so the gradients and the texture read as photographic rather than as flat fills. `mkmvania.py` is where the art is made, so the dither belongs there |
| the actors | **several DIFFERENT colourful sprites**, not one shape recoloured — the keyed copy blits full colour at the engine's rate (`keyed-copy.md` §0), and a three-colour blit is cheaper than a single software pass, so there is no reason for the cast to be monochrome |
| ⚠ the one rule the art must keep | **index 0 is the key** and cannot be a visible colour anywhere in the room or the art. `mkmvania.py` asserts it |

⚠ **The sweep is not the demo.** What is built ramps the actor count to find where the
frame breaks, which is what the measurements needed; the fifteen seconds a viewer
should see is a room traversed, not a stress test.

⭐ **`mvaniapal.asm` and `mvaniadat.asm` are generated** by `bench/mkmvania.py`
and checked in beside the source that includes them; the room's geometry, the
palette, the masks and the **keyed art** exist in that script and nowhere else.

⚠ **Index 0 is the key and therefore not a colour.** The card's key is fixed at
index 0 (`keyed-copy.md`), so the actor art's transparent pixels are 0 and no
visible pixel in the scene may be — the generator asserts it.

⛔ **One buffer, and the work runs during the visible picture.** With the
restores and the draws in two phases, every actor is missing from the rows the
raster scans between the two — three of twelve actors reach the recording.
Interleaving the pair per actor (mode bit 6) costs exactly the same copies and
fixes it, which is why the scene's own mode is the interleaved one and the
two-phase modes are there to be measured.

### ⭐ `run-v3mon.sh` — `monster`, the block-streamed platform world

`mvania` asks what a game can put on a screen when the whole room is already
in VRAM. **This one asks what it can put there when the level is longer than
VRAM**, and it is `optimizations.md`'s priority list — entries 1, 2 and 3 —
built as one scene rather than three experiments.

```sh
sh video3/bench/run-v3mon.sh          # nine runs + two mutations, ~6 min. Its exit code is the answer
```

| | |
|---|---|
| The scene | `monster`, a NitrOS-9 command in the port's tree (`level2/arm6309/cmds/monster.asm`). A 10,240-pixel side-scrolling level **streamed through the card's 1024-column ring** a 16-pixel column at a time, a hero on the hardware sprite that runs and jumps the pits, and a cast of eight different creatures as **full-colour keyed blits**. Fifteen seconds at 70 Hz |
| ⭐ No OS call per frame | An exclusive owner has already waited for the blank — `VR.FCnt` is the VBL service's own count in a register — so `HSCROLL`, `VSCROLL` and, when the gait changes, the sprite's 64-byte shape are written **straight at the card inside that blank**, after reading `VSTAT` b6 back. **0.042 ms** against `SS.Scroll`'s **1.14** |
| ⭐ The block stream | The level is a map in DRAM (two bytes a column: the archetype of its TOP strip and of its BOT strip); the art is a bank of **tall strips** in VRAM, composed at start-up out of 16 × 16 blocks. The incoming column is blitted **832 pixels ahead of the view's left edge**, in the 384 columns of ring the 640-wide view does not show, so the level is as long as DRAM allows and the picture stays in **bitmap** mode — which is what keeps the sprite, the keyed blits and 256 colours |
| ⭐ The art | `mkmonster.py`. **256 colours**, median-cut out of the art itself, **snapped to the 5/6/5 grid the LUT really stores** and then **Floyd–Steinberg dithered against it**. Eight creatures, two animation frames each, six hero gaits. ⛔ **LUT entry 0 is bright magenta**: index 0 is the copy engine's key, nothing visible may be it, and a leak is then unmistakable rather than merely wrong |
| The instrument | a store to **`$FF2E`**, as `mvania` uses. Ten a frame, about 29 µs of 14,300, inside every number below |
| ⭐ The tags, which `mvania` could not carry | `optimizations.md` §8 left this open: a scene that makes no driver call cannot write `VG.MkCam`/`VG.MkHero`, because they are in the **system** map — which is why `mvania`'s in-blank mode stayed a measurement mode. `monster` sends the camera and the actor count **as marks**, and `checkv3mon.py` joins `marks.txt` to `frames.bin` on the **timestamp**: both carry picoseconds off the same clock. A tag costs twelve E cycles instead of a system call |
| ⛔ The gate | **not the timings, and not "the live page equals a clean page" either.** Every byte of the playfield is *decided* — it is the strips the level map names, for the 64 level columns the ring holds at the scroll the run ended on — so `checkv3mon.py` **rebuilds the whole of VRAM from `monster.json`** and compares. The live band, the clean band, both strip banks and the keyed art, byte for byte. ⭐ And the scene reports **which** level column it last filled, as four nibble marks, so the compare does not have to replay the scene's arithmetic — and the arithmetic is then a *separate* claim instead of the check's own assumption |
| ⛔ The tearing gate | `$11` is marked the instant the four scroll stores are done, and `marks.txt` carries `VBLANK`'s rise and each frame's first active line, so "the pair reached the card inside the blank" is read off the recording. ⭐ With a negative control — the actor phase must end in the **picture** — and with the decline path checked in both directions: a frame that finds the blank gone declines rather than tears, and every decline followed a frame that had already overrun |

#### What it measured, 2026-09-20

A frame is 14.27 ms. At the scene's own cast of twelve, on the host emulator:

| | ms a frame |
|---|---|
| the scroll pair, written in the blank | **0.042** |
| the sprite's gait, when it changed (every fourth frame) | 0.128 |
| ⭐ the column refill, at 4 px a frame | **0.399** |
| the game's logic — camera, hero, terrain-following cast | 2.776 |
| ⭐ the actors: a restore and a keyed blit each | **5.672** |
| what is left of the frame | **5.24** |

| | |
|---|---|
| ⭐ **the most actors that fit** | **18**, from the sweep's slope: **0.501 ms of frame + 0.740 ms an actor**. The work first passes 14.3 ms at 19 and the first dropped frame is at 18 |
| ⭐ **what the OS call costs** | `SS.Scroll` instead of the blank write: **+1.09 ms a frame**, 21 actors → 19. §8's 1.05 ms of IOMan, SCF and the kernel, measured again on a different scene |
| ⭐ **what the column stream costs** | 2 px a frame **0.18**, 4 px **0.35**, 8 px **0.65** ms a frame (against mode b1, which does no refill). ⚠ That is **~1.4 ms a column** for three rectangles and 4,608 bytes — §7.1's arithmetic for the same three is 1.69 ms, so **the per-rectangle cost issued from the card's own registers is ~87 µs here and not 183** |
| interleaved against two phases | the same copies and, at twelve actors, 9.03 ms against 9.23 — so the thing that makes the scene *look* right is free |
| ⛔ **the blank an exclusive owner really has** | §8 says the poll returns twelve lines into a forty-nine-line blank, leaving ~1.1 ms. **Measured: it returns 1,186 µs into a 1,558 µs blank and leaves 353.** The twelve lines are where the *interrupt* arrives; `VR.FCnt` is written much later in the service. Four register writes still fit with 70× to spare, and the 64-byte sprite shape (~0.3 ms) deliberately does **not** — it is outside the gate, because the raster does not read the shape until the sprite's own rows, 240 scanlines in |

#### ⭐ The mutations, and one of them was real

`run-v3mon.sh` ends by running two deliberately broken scenes and **requiring the
gate to fail**:

| Mutation | What the gate says |
|---|---|
| mode b5 — the refill takes its art from level column `c + 1` | 873 bytes differ, first at ring row 0 column 1008 |
| mode b6 — actor 0 is drawn and never restored | 8 bytes differ, first at ring row 125. ⚠ Only eight, because the column stream itself wipes a trail older than 256 frames — the gate catches it, and the number is small for a reason worth knowing |

⛔ **And the gate caught a real one before either of those was written.**
`monster.asm` had the TOP strip's block-row count as a literal `8` after
`mkmonster.py` moved to `7`; every strip but the first was composed out of the
wrong blocks. **The picture still looked like a platform world** — hills, turf,
platforms, all plausible — and every timing was unaffected. Only the byte
compare saw it. The geometry is now *emitted* by the generator (`MNTR`, `MNBR`,
`MNTOPH`, `MNRTOP` …) and restated nowhere.

⛔ **And a second one the gate could not see, which is the other half of the
lesson.** `Spawn` ignored the position its caller had computed and used its own
— `worldx + 664 + (kind × 37 & 127)` — which put half the kinds past the range
test three lines later, so four of the eight spawned and died on the same frame
for ever. VRAM was correct at every instant; the cast just ran at five to nine
of its twelve and **the frame budget was measured on a scene that could not
fill itself**. What found it was reading the contact sheet's labels.

⚠ **The ring's seam is exercised on purpose.** A restore rectangle at ring
column 1009 wraps inside its row — the copy's column counter is ten bits and
the row steps only when `CWIDTH` runs out (plan §6), which is exactly what a
1024-column torus means. `mvania` declined to test it (its `XWRAP` is 1008);
`monster` marks `$17` on every frame one happens and `checkv3mon.py` **refuses
to call the gate meaningful until one has** — 278 frames of 1,050 in the scene.

⚠ **The geometry is tight and the clean band is why.** All 512 ring rows are
spoken for: 208 of live playfield, 208 of strip bank, 96 of clean copy. The
clean band has to cover every row an actor can stand on, so the cast flies in
playfield rows 112–192 and the top 104 pixels of the picture hold only
scenery. The hardware sprite has no such limit and the hero jumps into it,
which is a fair demonstration of what a sprite buys over a blit.

### ⭐ `run-v3pin.sh` — `pinball`, and what the LUT is worth

`mvania` asks what a game can put on a screen when the room is already in
VRAM, and `monster` what it can when the level is longer than VRAM. **This
one asks what happens when the WHOLE WORLD is in VRAM and nothing streams
at all** — which is the case where the card's scroll costs nothing and the
work moves into the palette. It is `optimizations.md` §10, built.

```sh
sh video3/bench/run-v3pin.sh          # five runs + four mutations, ~30 min. Its exit code is the answer
```

| | |
|---|---|
| The scene | `pinball`, a NitrOS-9 command in the port's tree (`level2/arm6309/cmds/pinball.asm`). A **640 × 512 table** — 327 KB of the card's 512 KB ring, two and a half screens tall — with `VSCROLL` following the ball, a scripted ball on the **hardware sprite**, extra balls as **keyed blits with save-behind**, and flippers **pre-composed over their own background**. Fifteen seconds at 70 Hz |
| ⭐ **The table is a FILE** (2026-09-21) | `mkpcb.py`'s `pcbtable.pic` — a 1984 circuit board, **327,680 bytes**, one palette index a pixel, **exactly 640 SD blocks** — goes on the card in `DATA` and the scene reads it straight into VRAM rows 0–511. ⛔ It **cannot** be a module: that is five times the address space one may occupy, which is why the table was 61 interned 16 × 16 blocks composed by 1,280 copies until this bench got a card in its socket. `optimizations.md` §10.2 |
| ⭐ **Art and collision are separate** | The picture is a picture. The physics reads `pcbtable.json`'s **40 × 32 grid** — `colmap` and the `idmap` that says *which* bumper, target, rollover, kicker or return lane a cell is — carried as 2,560 bytes of module data by `mkpinball.py`. ⛔ Nothing in the scene derives a wall from a pixel; `checkpcb.py` (299 claims, 11 mutations) is what asserts that the two agree |
| ⭐ A loading screen, and it is not hidden | 320 KB is **11.1 s at 28.9 KiB/s** — one `CMD17` a 512-byte block and a 6809 shifting every byte through SPI by hand. The view is parked at the **bottom** of the table while it arrives, over a banner and a progress bar; ⛔ they are drawn in ring rows 312–511, which the picture itself overwrites, so nothing the loading screen drew survives into the VRAM gate |
| ⭐ The scoreboard scrolls, and that is the hardware's answer and not a compromise | `VSCROLL` is latched in vertical blanking (plan §8.1), so it cannot change mid-frame and **there is no vertical split**. The six-digit scoreboard is therefore part of the playfield, at the bottom, and the view shows it when the ball is low |
| ⭐ **The lamps and the score are PALETTE writes** | 50 of the 256 LUT entries are reserved — 8 lamps and 6 seven-segment digits — and the table is *painted* with them, after the dither, so nothing else can be them. A bumper lighting is then **three register writes** and a score digit twenty-one, and the copy engine never hears about it. `mkpinball.py` asserts no art **or sprite** colour equals a reserved one |
| ⭐ No OS call per frame | `VSCROLL` and the frame's LUT commits go straight at the card inside the blank the frame poll already waited for, `monster`'s entry-1 path. **0.032 ms** against `SS.Scroll`'s **1.12** |
| The instrument | a store to **`$FF2E`**, as the other two scenes use. Twelve a frame, about 34 µs of 14,270, inside every number below |
| ⛔ The VRAM gate | ⭐ **The expected VRAM IS the file.** Ring rows 0–511, columns 0–639 must be `pcbtable.pic` byte for byte — the same 327,680 bytes the card carries — and the spare columns the keyed art and the **eight flipper frames composed out of that picture**. Only the save-behind scratch is excluded, because it is the one region nothing can predict. It is a shorter model than the block composition it replaced and a stronger claim |
| ⭐ **The collision gate** | Art and collision are separate files now, so "the table looks right" says nothing about whether the ball can hit any of it. Every `Hit` marks its **kind** at `$FF2E` (`$01`–`$0C`) and the union over the runs must cover every kind the grid carries. ⛔ A scene whose `ColMap` was all zeroes paints, scrolls, keeps its budget and passes the gate above |
| ⛔ **The score gate** | `pinball` emits its six digits as nibble marks after the `Wipe`, and **`000000` fails**. This table has twice run perfectly and scored nothing for ever — a plunger that bounced instead of firing, and a lane mouth that returned the ball's own speed — and neither is visible to a gate about pixels or one about microseconds |
| ⭐ **The LAMP gate, which the other two scenes did not need** | A palette feature **touches no VRAM at all**, so the gate above is blind to the whole of it. It is read off the **recording** instead: each reserved entry's colour is unique in the picture, so "the lamp is lit in some frames and out in others" is a claim about what the card really produced. ⛔ With a negative control — **mode b1 writes no LUT at all and not one lamp may light** |
| ⛔ The tearing gate | `$11` is marked the instant the `VSCROLL` stores are done and `marks.txt` carries `VBLANK`'s rise and each frame's first active line, so "the pair reached the card inside the blank" is read off the recording. ⭐ And the **LUT commits are inside the same claim**: they have to fit the blank too, or a commit posts to the next `HLOAD` |

#### What it measured, 2026-09-21 (the table off the card)

A frame is 14.27 ms. The scene's own cast is three balls — one on the sprite,
two as keyed blits:

| | ms a frame |
|---|---|
| `VSCROLL`, written in the blank | **0.032** |
| ⭐ the lamps and the scoreboard, committed in the same blank | **0.299** |
| the sprite's shape, when the ball's highlight turned | 0.154 |
| the physics, and the lamp/score bookkeeping with it | 2.435 |
| the two flippers | 0.776 |
| ⭐ the two blit balls: a restore, a save-behind and a keyed blit each | **1.968** |
| what is left of the frame | **8.59** |

| | |
|---|---|
| ⭐ **what the table costs to load** | **11.09 s for 327,680 bytes — 28.9 KiB/s**, once, at start-up, with a loading screen over it. rbsd reads one 512-byte block a `CMD17` and a 6809 shifts every byte through SPI by hand; the 1,280 copy-engine rectangles it replaced took about half a second, and could not have drawn this picture |
| ⭐ **the most balls that fit** | **8** — seven blit balls from the sweep's slope (**2.622 ms of frame + 1.484 ms a blit ball**), and the sprite ball is free. The work first passes 14.3 ms at eight blits and the first dropped frame is there too |
| ⭐ **what the OS call costs** | `SS.Scroll` instead of the blank write: **+1.09 ms a frame** (5.68 → 6.77). §8's 1.05 ms of IOMan, SCF and the kernel, measured now on a **third** scene |
| ⭐ **what the palette scoreboard costs** | **1.48 ms a frame** against mode b1 (5.68 → 4.20), of which **0.30** is the LUT writes themselves; the rest is deciding what changed, and it is deliberately outside the blank. ⚠ It is twice what the interned table measured because the **bonus ladder** steps a lamp every sixteenth scoring event and the queue now runs at its `MAXPW` of four almost every frame |
| ⭐ **what pre-composing the flippers buys** | blitting them every frame instead of on a change is **+1.68 ms** (5.68 → 7.36) — more than before, because a flipper frame is now 56 × 64 rather than 48 × 32. Eight rectangles built once at start-up |
| ⛔ **the blank an exclusive owner really has** | the poll returns **1,186 µs into a 1,558 µs blank** and leaves **353** — `monster`'s measurement again. The scroll pair plus four LUT commits is **326 µs** at worst, which is why `MAXPW` is four and why it is now nearly all of the blank |
| the table's own score | **392,970** in fifteen seconds on three balls, and **598,350** over the sweep |
| ⭐ **every collision kind was met** | all twelve `pcbtable.json` carries, over the five runs — `solid`, `slope_r`, `slope_l`, `bumper`, `target`, `rollover`, `kicker`, `drain`, `flip_l`, `flip_r`, `return`, `plunger` |

⚠ **THE THREE-BALL SCENE DOES NOT REACH THE FLIPPERS, and the lamp gate said
so.** The bumper nest at the top of the board keeps the cast there: `m0` meets
`solid`, `bumper`, `target`, `rollover`, `kicker` and `plunger` and nothing
else, so `D7` and `D8` — the slingshots' and the flippers' lamps — had no
source at all and the gate reported `MISSING lamp 6 lit` with every other
claim green. The sweep's fifteen balls do reach them. ⭐ What closed it is a
**bonus ladder**: every sixteenth *scoring event* steps a lamp along the eight
inserts, which is what a 1984 table does with the panel it has — and which is
driven by scoring and by nothing else, so a table that hits nothing still
lights nothing and the gate keeps its teeth.

⚠ **And the scoreboard is only ever on screen when a ball is at the bottom**,
because `VSCROLL` follows ball 0 and the six digits are painted into the
backplane at the foot of the table. The one moment that is true is while a
ball **waits in the shooter lane**, so `Launch` serves it there at rest and
the `KPLNG` cell is what throws it, 60 frames later — long enough for the
camera's 8 rows a frame to pan the 300 rows down and back. Before that the
digits were never once in the picture, and `segon`/`segoff` were two of the
gate's eighteen states that nothing could satisfy.

#### ⛔ Why save-behind here, where `monster` uses a clean band

`monster` restores from a clean copy of a 96-row band and says why that beats
save-behind. **It does not transfer, and the reason is arithmetic:**

- a *static* clean copy of this table is 327 KB on top of the table's 327 KB
  and the ring is 512 KB — it cannot exist;
- a *scrolling* clean band, which is `monster`'s actual shape, has to be
  refilled as the camera moves, and here the camera is driven by the **ball**
  — up to eight rows a frame, 5,120 bytes, about **1.35 ms**. Two balls' third
  copies are 0.30 ms. The trade is four times the wrong way round, and it is
  the camera's *speed* that reverses it. `monster`'s clean band was free
  because it rode a refill the scene was doing anyway.

⚠ **And save-behind costs more than its third copy: it costs the interleave.**
A save must see pristine table, so **every restore has to run before any save
and every save before any draw** — three phases, where `monster` interleaves
restore-and-draw per actor and bench/README.md records why that looks better.
Two phases is not enough and the gate said so: a ball saved after another was
drawn captures the other ball, and its restore paints that ghost into the
table for the rest of the run. Multiball puts two balls in the same plunger
lane, so it is not a corner case — it was 2,067 bytes of trail.

#### ⭐ The mutations, and the one thing no gate here could see

`run-v3pin.sh` ends by running four deliberately broken scenes and **requiring
the gate to fail**. ⭐ The last two are the gate on the path the scene gained
when its table became a file:

| Mutation | What the gate says |
|---|---|
| mode b5 — each ball's save-behind is taken one ROW below where it draws | 39,316 bytes differ, first at ring row 16 column 16 |
| mode b6 — blit ball 1 is drawn and never restored | 26,892 bytes differ, first at ring row 16 column 117 |
| ⭐ mode b8 — the picture is loaded to the WRONG VRAM ADDRESS, one row low, so the whole table is rotated through the ring | 241,116 bytes differ, first at ring row 0 column 0 |
| ⭐ mode b9 — the load is TRUNCATED at ring row 448, so the last four cell rows of the backplane keep the loading screen | 39,009 bytes differ, first at ring row 448 column 0 — **64 rows and no more**, which is what says it is a truncation and not a rotation |

⛔ **And the b9 mutation was itself wrong for one run, which is worth the
note.** `PicLd` read the mutation flags with `ldd #0` followed by
`ldb mode,u` — a test that *leaves the mode's high byte in the low half of
D*, so mode 512 started the load at ring row **two** and the truncation
mutation was really a rotation. It failed the gate either way, which is
exactly how a mutation that tests the wrong thing stays green; what caught it
was reading *where* the differences were and finding them spread evenly over
all 512 rows instead of confined to the last 64.

⛔ **AND THE DEFECT THAT COST A DAY WAS INVISIBLE TO EVERY ONE OF THEM.**
`Move` set its axis flag with `lda #1` — and **A was the cell kind**. Every
*vertical* collision therefore arrived at the collision switch as `KSOLID`,
so every bumper, every rollover, the drain, the plunger and the lane's own
kicker were plain walls. The ball bounced up and down the plunger lane for
the whole fifteen seconds, and:

- the **VRAM gate passed** — it is about pixels, and the pixels were right;
- the **frame budget was measured** — it is about microseconds, and the
  microseconds were real;
- the **tearing gate passed**, the sheets looked like a pinball table, and the
  scene reported **000000** four runs running.

⭐ **What found it was the LAMP gate** — a claim about the *picture over time*
rather than about the machine — because a table where nothing is ever hit is
a table where no lamp ever lights. ⚠ A scene bench needs at least one claim
that the scene *did something*, and neither of the other two has one.

⚠ **Two smaller ones worth the same note.** `LampHit` lit each bumper's cap
and never the ring the five of them share, so LUT entry 209 was allocated,
painted and written by nobody — `npm run check:reach`'s question asked about
a palette instead of a macrocell. And `LAMP_OFF[7]` was `(30, 26, 40)` while
the ball's sprite outline was `(24, 26, 40)`: different in eight bits, **the
same RGB565**, and the lamp gate spent a run reading a ball as a lamp.
`mkpinball.py` asserts the whole reserved set against the art palette, the
three sprite banks and the key.

⭐ **Neither the demos nor their data are in the ROM any more** (2026-09-20;
the ROM disk was full, see [`../docs/history.md`](../docs/history.md)).
`recipes/arm6309/arm6309.mak`'s `$(DEMOS)` builds the programs,
`software/nitros9/mkrom.sh` writes the data set to `$OUT/data`, and
`software/nitros9/mksddisk.sh` puts both on an SD image. The ROM disk is the
kernel, the shell, the shared modules, `errmsg` and a rescue command set,
with **350 K of its 488 K free**. The older scene benches boot with an **empty
socket** and type their command at `/DD`, so they pass `CMDS_EXTRA=<name>` —
but nothing has to be **given back** any more, and the recipe's disk rule now
depends on the command list itself (`.cmdlist`), so nothing has to delete
`romdisk.dsk` either.

⭐ **`run-v3pin.sh` is no longer one of them** (2026-09-21). Its table is
327,680 bytes of picture, so there **is** no empty-socket version of that
scene: the bench builds a card with `pinball` in `CMDS` and `pcbtable.pic`
plus `pcbtable.pal` in `DATA`, boots with it in the socket and `chx
/sd0/cmds` before typing. ⚠ `chd` is deliberately not done, because it would
change the prompt and with it the bench's `SERIAL_GATE`. And `mkrom.sh` puts
the same two files in `$OUT/data` under `V3=1`, so a **full** demo card —
the one the desktop's Applications menu forks the scene from — carries them
too; `run-v3pin.sh` claims both, by copying the picture back off the image
and comparing it byte for byte with the source.

### ⭐ They were mutation-tested, because a green check proves nothing on its own

Three deliberate breaks in `v3model.py`, one per exerciser, and **each fails the
check it should**:

| Mutation | Fails |
|---|---|
| ⭐ **let the sprite leak into character mode** (in `machine.c`, the *card*) | `v3char` |
| swap the sprite's high and low shape bits | `v3sprite` |
| ignore the column-direction bit | `v3copy` |
| swap the map word's code and attribute | `v3char` |
| ignore `HSCROLL` | `v3tile` |
| a five-bit cell row instead of six | `v3tile` |
| read the map on the wrong stride (in `machine.c`: one or two bytes a tile cell, two a character cell) | `v3tile`, `v3char` |
| read the attribute from lane 1 instead of lane 2 (in `machine.c`) | `v3char` |
| ⭐ **ignore the colour key** (in `v3model.py`) | `v3copy` — 322 pixels |
| ⭐ **key in EVERY `WMODE`, not only 11** (in `machine.c`, the *card*) | `v3copy` — 234 pixels |
| ⭐ ignore `WADV` b2 — `wstep()` always by one (in `machine.c`) | `v3char` |
| read the sprite's shape at `MAPBASE` 0 whatever `MAPBASE` says (in `machine.c`) | `v3sprite` |
| line-double in every VMODE | `v3char` |
| expect the wrong active-line count | `v3char` |

`graphics.md`'s trap list is explicit that *a check that reports nothing reads exactly
like passing*; this is the cheapest defence against writing one.

⚠ **`v3tile` sets each scroll, lets it settle, and only THEN marks the frame** at
`$C208`/`$C20A` — `VSCROLL` is taken by a frame-start latch, so a frame marked at the
instant of the write could carry the previous scroll and be judged against the new one.

⚠ **And a hole the mutation test did not find**, fixed rather than relied on: the ROM
records its sprite position in `$C208`/`$C20A`, which start at zero — and `(0,0)` is a
test position, so frames recorded while the screen was still being built could have
been judged as if the sprite were live. The ROM now writes `$FFFF` there until the
screen is up, so those frames are skipped **explicitly**.

### ⭐ `run-v3star.sh` — `stardew`, and the day in the palette

`mvania` asks what a game can put on a screen when the room is already in
VRAM, `monster` what it can when the level is longer than VRAM, and
`pinball` what happens when the whole world is resident and nothing streams.
**This one is not about where the bytes are at all.** It replaces
`overworld` — the archived `video/` card's flagship — and the thing it
exists to show is [`../docs/stardew.md`](../docs/stardew.md)'s headline:
⭐ **the time of day changes by palette writes and nothing else.**

```sh
sh video3/bench/run-v3star.sh         # four runs + three mutations + two controls, ~25 min
python3 video3/bench/mkstardew.py --tint-test    # ⚠ §6 item 2, on its own, ~25 s
```

| | |
|---|---|
| The scene | `stardew`, a NitrOS-9 command in the port's tree (`level2/arm6309/cmds/stardew.asm`). A **1024 × 480 farm** — 491,520 of the ring's 524,288 bytes — read off `/SD0` straight into VRAM rows 0..479, a 640 × 200 view scrolled over it in **both** axes, the farmer on the hardware sprite, six chickens and a dog as **keyed blits with save-behind**, crops that grow, and a HUD that follows the camera |
| ⭐ The day | 256 phases, four key times, and the driver holds the **authored** 8-bit RGB and multiplies towards the phase's six coefficients. The lit set (LUT 201–230 — windows, lanterns, the stove, fireflies, the moon on the pond) is never touched, so it *becomes* the light as everything else darkens |
| ⛔ The ring is spent, so there is no clean band | 491,520 of 524,288 bytes are the world. The actors restore with **save-behind**, which forces **three phases** — every restore before any save and every save before any draw (`pinball`'s finding, and two chickens in one place is not a corner case) |
| The instrument | a store to **`$FF2E`**, as the other three scenes use. Seventeen a frame, ~57 µs of 14,270 |
| ⛔ The VRAM gate | every byte of the world is `stardew.pic` with exactly the crop stages the scene's own retirement count says it grew, and the keyed art bank with it. ⭐ And separately: outside the crop plots the world is the file **byte for byte**, which is what says 491,520 bytes came off the card unaltered |
| ⭐ **THE PALETTE GATE, which no other scene here needed** | ⛔ A day cycle **touches no VRAM at all**, so the byte compare is structurally blind to the whole feature. The LUT is read off the **recording** instead, and **index by index**: the world is known and the camera is in the marks, so every pixel's palette index is known, and the **modal colour of an index's pixels IS what the card's LUT held**. ⛔ With a negative control — mode b0 writes no LUT entry and must read the authored palette at every checkpoint |
| ⛔ **The compounding gate** | `stardew.md` §2: the tint must be applied to the **authored** colour, never the current one, or it compounds and the world converges on black over a thousand frames. The scene ends by pinning the day at noon and putting every entry back through the same arithmetic at unity gain — after which the LUT must be the authored palette **bit for bit** |
| ⭐ The one-line statement of the feature | the run **with** the cycle and the run **without** it leave the world byte for byte the same, and their palettes do not agree |
| The sheets | `stardew-sheets/`, beside this file - the fifteen seconds as a contact sheet, labelled with the camera, the day's phase and the cast |
| ⛔ The tearing gate | `$11` is marked when the scroll pair is in and `$12` when the frame's LUT writes are, and `marks.txt` carries `VBLANK`'s rise and each frame's first active line — so "both reached the card inside the blank" is read off the recording |

#### ⭐ Three things it found

⛔ **The tint cannot be done in the blank, and `stardew.md` §2's budget for it
was wrong by 4×.** Nine multiplies and six clamps an entry measured **250 µs**
on this CPU, so "four entries in 0.24 ms inside a blank that has 353" is not
merely tight, it is impossible. What has to be in the blank is the **write**,
which is two register stores. The scene therefore **computes** `SWMAXPW` words
in the frame's own slack and **writes** them in the next frame's blank, at
~31 µs an entry — and six now fit where four of the original shape did not.

⛔ **And the palette gate caught a defect on its first green run of everything
else.** `PalPrep` saved its loop counter with `pshs b` around a call that
**returns in D**, and `puls b` put the counter back over the answer's low
byte: every LUT word had the right `PDATH` and a `PDATL` of 1..6. That is a
whole-world colour error — every blue and the low two bits of every green —
and **the VRAM gate passed it, the tearing gate passed it, and a contact
sheet looks like a farm at dusk.** Only a claim about the LUT's *contents*
saw it. ⚠ `pinball`'s lamp gate is the same lesson (`bench/README.md`
above): a scene needs at least one claim about what the picture *is*, not
only about what the machine did.

⛔ **AND A DEMO THAT FAILS HAS TO LEAVE THE MACHINE USABLE.** `stardew`'s first
error path printed its message and exited without a `DWEnd`, so the window it
had `DWSet` stayed **defined** — and the next `DWSet` on it answered
`E$WADef`. At the shell that is visible (`stardew` twice in a row:
`Error #184 - Window already defined`); under the desktop it is not, because
`desk` forks the scene, the scene fails, and `desk`'s own `Setup` then cannot
have its window back. The error path now ends the window; ⚠ the **successful**
path deliberately does not, because `DWEnd` frees the screen's store and that
path's VRAM is what the gate dumps.

⚠ **The join has to be physical, not nearest-match.** A recorded field's
pixels were decided in the blank **before** its first active line, so the
frame mark to use is the last `$10` before that `A` — and the camera cannot
be used to pick between candidates, because **when the camera is clamped at
an edge two consecutive frames report the same one**. Three checkpoints of
twelve were joined one frame early that way, which presented as exactly one
batch of six LUT entries carrying the previous sweep's phase.

### ⭐ `run-v3sd.sh` — the desktop, Paint and a demo, all **off the SD card**

```sh
sh video3/bench/run-v3sd.sh           # two runs, 29 claims, ~3 min. Its exit code is the answer
```

Every other bench here types a command that is *inside the boot ROM*, and
reads data that is inside it too. This one boots the machine with **both**
cards — video3 and the storage card at `$FF58` (`storage/docs/sdcard.md`
§9.4) — and runs the Haiku desktop, Paint, `changefont` and `mvania` from a
card that `software/nitros9/mksddisk.sh` wrote with the host's `os9` tools. It
is about **where the program and its data came from**, so the scene is 28
frames and no more; `run-v3mv.sh` is what measures a scene.

⭐ **Two halves, and they are found two different ways.** The desktop and
Paint are *streams*, `copy`d to a window — so the path is the caller's
already, and `copy /sd0/data/v3desk /w3` is the whole change.
`changefont` is a program that opens a file **for itself**, and it now names
the face without a directory and lets `DOpen` (card, then `/DD/SYS`) decide;
`overworld`, `rastbar` and `wave` do the same.

⛔ **Everything `copy` and `display` do comes before `chx /sd0/cmds`**, and
that is not tidiness: after the execution directory moves to the card, the
only things the shell can fork are the card's own commands and shell+'s
merged built-ins. `copy` lives in `/DD/CMDS` and becomes unfindable.

⭐ **The claim is that a picture was PAINTED, not that a command was typed.**
`checkv3sd.py` reduces the recording to `frames`, `painted`, `changed` and two
*shapes*:

| | |
|---|---|
| `desk` | one colour over ≥ 45% of the frame **and** ≥ 40 colours — a big flat background with icons, a Deskbar and window chrome on it |
| `paint` | ≥ 20% of the frame **pure white** and ≥ 40 colours — Paint's page under Haiku chrome |

⚠ Measured and not guessed: the finished desktop is 50.8% one colour with 54
colours; Paint is 35.5% its top colour, 27–34% white, 50 colours; the no-card
control is **one colour over the whole frame**. The scene's own colour values
are deliberately not in the test, so repainting the desktop cannot fail a
claim about loading a file. ⚠ An earlier cut asked for **64 colours** and
failed a run whose picture was perfect — `mvania`'s room is a stylised
side-view, not a dithered photograph. The number to pick is the one the
*control* cannot reach.

⛔ **And the control is the same ROM, the same keystrokes and an empty
socket.** `/SD0` refuses at §9.0 with `E$NotRdy`; every `copy` says so;
`changefont`'s bare name misses **both** legs of `DOpen` and reports the ROM's
`E$PNNF`; and the demo is `E$PNNF` rather than a hang. ⛔ **A blank screen is
not a pass**: `iniz w3` and `display 1b 21` need no card, so the control still
records eleven hundred frames — of nothing. `desk` and `paint` must both be
zero.

⭐ **One error is expected in the card run and it is deliberate.**
`changefont /sd0/data/nosuchface` gives an explicit path to a face that is not
there, and an override the caller asks for is not second-guessed. The bench
requires **exactly one** `Error #` — two would mean the *first* `changefont`,
a bare name that goes through `DOpen`, had not found its face on the card. So
the count is the positive claim about `DOpen` as well.

Five more claims say the ROM disk carries none of it — `mvania` not in
`/DD/CMDS`, the desktop, Paint and the faces not in `/DD/SYS`, `errmsg` still
there — asked both of the machine and of `romdisk.dsk` on the host.

## ⚠ What this model does and does not answer

| | |
|---|---|
| ⭐ **Answers** | plan §14 item 1's *functional* half — does the attribute reach the LUT's high eight address lines and produce the right pixel? And it is where a NitrOS-9 driver can be written and run in seconds |
| ⛔ **Does not answer** | **the fetch cadence.** Plan §14 item 8 — five requesters against one spare access a slot — is invisible here, because the model renders a whole line at once. Only Verilator sees it |
| ⛔ **Does not answer** | **the hardware's** timing. `npm run check:video3` has the arithmetic; the board has the rest |
| ⭐ **Answers, since 2026-09-18** | **the SOFTWARE's** timing, for the ROM toolbox: `run-v3text.sh` times N identical `Text` calls on a booted NitrOS-9 and reports the per-call and per-character cost (`demo-report.md` §16). ⚠ It is the only bench here that boots the OS — the toolbox is reached through CoArm's `ESC $6A`, so there is no bare-metal route |

## ⚠ One duplication, declared

`v3tile`'s **tile bank is a formula at both ends** — `(t × 7 + p) & 255`. 16 KB of
tiles plus 8 KB of map does not fit the two ROM pages, so the map (the part that
actually *addresses*) is a table the ROM streams and the JSON carries, and the bank is
computed on each side from constants in the JSON. Everything else shares data only.

### ⭐ plan §7's "bitmap mode only", asserted as a negative with a control

The last phase of `v3char` arms the sprite — an all-opaque 8 × 8 at (32, 8), written
into VRAM at `MAPBASE`'s top like any shape, over a cell whose attribute is `$2A` — **reads `SPRH` back to prove the register took the
enable**, and then requires character mode to show no trace of it. Without that
read-back the phase would assert nothing; with it, a leak is 64 pixels of sub-palette
1 where `$2A` belongs.

⭐ **`bench/v3sprite` is the positive control**: the same `SPRH` write puts a sprite on
screen at 36 positions. A negative test alone cannot tell "correctly suppressed" from
"never worked", and the pair can.

**Mutation-tested against the card, not the model**: patching `v3_render_line` so the
sprite overrides `ATTR` in character mode fails the check and localises it to
`(32,16)`, cell (4,1) — exactly where it was armed.

## Not yet written
- **A NitrOS-9 driver.** This is where it gets written — plan §15.3.
