# `video3/bench/` — the host-emulator model

**video3 is modelled in `software/demo/emu/machine.c` beside `video/`, not instead
of it.** `VIDEO3=1` selects it; without it the emulator is the card it always was,
so `run-emu.sh`, `run-vid.sh` and `software/nitros9/run-emu.sh` are unaffected.

```sh
sh video3/bench/run-v3.sh            # all four, ~1 min. Its exit code is the answer
sh video3/bench/run-v3mv.sh          # ⭐ the metroidvania scene, ~20 min
sh video3/bench/run-v3mon.sh         # ⭐ the block-streamed platform world, ~6 min
sh video3/bench/run-v3pin.sh         # ⭐ the pinball table, and the palette as a feature, ~20 min
sh video3/bench/run-v3sd.sh          # ⭐ a demo loaded OFF THE SD CARD, ~1 min
```

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
sh video3/bench/run-v3pin.sh          # five runs + two mutations, ~20 min. Its exit code is the answer
```

| | |
|---|---|
| The scene | `pinball`, a NitrOS-9 command in the port's tree (`level2/arm6309/cmds/pinball.asm`). A **640 × 512 table** — 327 KB of the card's 512 KB ring, two and a half screens tall — with `VSCROLL` following the ball, a scripted ball on the **hardware sprite**, extra balls as **keyed blits with save-behind**, and flippers **pre-composed over their own background**. Fifteen seconds at 70 Hz |
| ⭐ The scoreboard scrolls, and that is the hardware's answer and not a compromise | `VSCROLL` is latched in vertical blanking (plan §8.1), so it cannot change mid-frame and **there is no vertical split**. The six-digit scoreboard is therefore part of the playfield, at the bottom, and the view shows it when the ball is low |
| ⭐ **The lamps and the score are PALETTE writes** | 50 of the 256 LUT entries are reserved — 8 lamps and 6 seven-segment digits — and the table is *painted* with them, after the dither, so nothing else can be them. A bumper lighting is then **three register writes** and a score digit twenty-one, and the copy engine never hears about it. `mkpinball.py` asserts no art **or sprite** colour equals a reserved one |
| ⭐ No OS call per frame | `VSCROLL` and the frame's LUT commits go straight at the card inside the blank the frame poll already waited for, `monster`'s entry-1 path. **0.032 ms** against `SS.Scroll`'s **1.12** |
| The instrument | a store to **`$FF2E`**, as the other two scenes use. Twelve a frame, about 34 µs of 14,270, inside every number below |
| ⛔ The VRAM gate | The table is decided by DATA: every byte of ring rows 0–511, columns 0–639 is the block its map names, with each flipper's **rest frame composed over one rectangle**. `checkv3pin.py` rebuilds all of it from `pinball.json` — the bank, the map, the keyed art and the **eight composed flipper frames** — and compares byte for byte. Only the save-behind scratch is excluded, because it is the one region nothing can predict |
| ⭐ **The LAMP gate, which the other two scenes did not need** | A palette feature **touches no VRAM at all**, so the gate above is blind to the whole of it. It is read off the **recording** instead: each reserved entry's colour is unique in the picture, so "the lamp is lit in some frames and out in others" is a claim about what the card really produced. ⛔ With a negative control — **mode b1 writes no LUT at all and not one lamp may light** |
| ⛔ The tearing gate | `$11` is marked the instant the `VSCROLL` stores are done and `marks.txt` carries `VBLANK`'s rise and each frame's first active line, so "the pair reached the card inside the blank" is read off the recording. ⭐ And the **LUT commits are inside the same claim**: they have to fit the blank too, or a commit posts to the next `HLOAD` |

#### What it measured, 2026-09-20

A frame is 14.27 ms. The scene's own cast is three balls — one on the sprite,
two as keyed blits:

| | ms a frame |
|---|---|
| `VSCROLL`, written in the blank | **0.032** |
| ⭐ the lamps and the scoreboard, committed in the same blank | **0.175** |
| the sprite's shape, when the ball's highlight turned | 0.154 |
| the physics, and the lamp/score bookkeeping with it | 1.631 |
| the two flippers | 0.619 |
| ⭐ the two blit balls: a restore, a save-behind and a keyed blit each | **1.968** |
| what is left of the frame | **9.67** |

| | |
|---|---|
| ⭐ **the most balls that fit** | **9** — eight blit balls from the sweep's slope (**1.674 ms of frame + 1.459 ms a blit ball**), and the sprite ball is free. The work first passes 14.3 ms at nine blits and the first dropped frame is there too |
| ⭐ **what the OS call costs** | `SS.Scroll` instead of the blank write: **+1.09 ms a frame** (4.59 → 5.68). §8's 1.05 ms of IOMan, SCF and the kernel, measured now on a **third** scene |
| ⭐ **what the palette scoreboard costs** | **0.70 ms a frame** against mode b1, of which only **0.16** is the LUT writes themselves; the rest is deciding what changed, and it is deliberately outside the blank |
| ⭐ **what pre-composing the flippers buys** | blitting them every frame instead of on a change is **+0.73 ms** (0.62 → 1.36). Eight rectangles built once at start-up |
| ⛔ **the blank an exclusive owner really has** | the poll returns **1,186 µs into a 1,559 µs blank** and leaves **353** — `monster`'s measurement again. The scroll pair plus up to four LUT commits is **326 µs** at worst, which is why `MAXPW` is four |
| the table's own score | **065440** in fifteen seconds on three balls |

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

`run-v3pin.sh` ends by running two deliberately broken scenes and **requiring
the gate to fail**:

| Mutation | What the gate says |
|---|---|
| mode b5 — each ball's save-behind is taken one ROW below where it draws | 35,255 bytes differ, first at ring row 81 column 112 |
| mode b6 — blit ball 1 is drawn and never restored | 13,296 bytes differ, first at ring row 84 column 406 |

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

⭐ **The demos are not in the ROM any more** (2026-09-20; the ROM disk was full,
see [`../docs/history.md`](../docs/history.md)). `recipes/arm6309/arm6309.mak`'s
`$(DEMOS)` builds them and `software/nitros9/mksddisk.sh` puts them on an SD
image; the ROM disk is the kernel, the shell, the shared modules and a rescue
command set, with ~65 K free. `run-v3pin.sh` and the other older scene benches
boot with an **empty socket** and type their command at `/DD`, so they still
pass `CMDS_EXTRA=<name>` — but nothing has to be **given back** any more, and
the recipe's disk rule now depends on the command list itself (`.cmdlist`), so
nothing has to delete `romdisk.dsk` either.

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

### ⭐ `run-v3sd.sh` — a demo that is **not in the ROM**, run off the SD card

```sh
sh video3/bench/run-v3sd.sh           # two runs, 20 claims, ~1 min. Its exit code is the answer
```

Every other bench here types a command that is *inside the boot ROM*. This one
boots the machine with **both** cards — video3 and the storage card at `$FF58`
(`storage/docs/sdcard.md` §9.4) — `chd`/`chx` to `/SD0/CMDS`, and runs `mvania`
from a card that `software/nitros9/mksddisk.sh` wrote with the host's `os9`
tools. It is about **where the program came from**, so it runs 28 frames of
scene and no more; `run-v3mv.sh` is what measures the scene.

⭐ **The claim is that a picture was PAINTED, not that a command was typed.**
`checkv3sd.py` reduces the recording to `frames`, `painted` (frames showing
more than a dozen distinct colours) and `changed`, and the bench asks for 20
painted and 20 changed frames. ⚠ **The first cut asked for 64 colours and
failed a run whose picture was perfect** — `mvania`'s room is a stylised
side-view with nineteen colours, not a dithered photograph. The threshold to
pick is the one the *control* cannot reach.

⛔ **And the control is the same ROM, the same keystrokes and an empty socket.**
`/SD0` must refuse at §9.0 with `E$NotRdy`, the demo must be `E$PNNF` rather
than a hang, and **no frame may be recorded at all** — with nothing to claim
the screen the card never displays, which is a sharper negative than "no
colours". Two more claims say the ROM disk does *not* carry the demo, one asked
of the machine (`dir /dd/cmds`) and one of `romdisk.dsk` on the host, because
without them the run above would prove nothing.

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
