# `software/monster/` — Mayhem in Monsterland

A block-streamed platform world in the style of *Mayhem in Monsterland*.

| | |
|---|---|
| 6809 source | `../nitros9` (branch `arm6309`), `level2/arm6309/cmds/monster.asm`, `monsterdat.asm` (generated) |
| Generator | `bench/mkmonster.py`, from `bench/monster.json` and `bench/monster-art.png` |
| Bench | `bench/run-v3mon.sh` (~6 min), checked by `bench/checkv3mon.py` |
| Video | `make video` / `make sheet` - `video/run-video.sh` |
| Reference | [`reference/`](reference/) |

### ⭐ `run-v3mon.sh` — `monster`, the block-streamed platform world

`mvania` asks what a game can put on a screen when the whole room is already
in VRAM. **This one asks what it can put there when the level is longer than
VRAM**, and it is `optimizations.md`'s priority list — entries 1, 2 and 3 —
built as one scene rather than three experiments.

```sh
sh software/monster/bench/run-v3mon.sh          # nine runs + two mutations, ~6 min. Its exit code is the answer
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
