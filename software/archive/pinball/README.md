# `software/archive/pinball/` — the pinball attempts before `pcs` (retired 2026-09-23)

Three generations of a pinball table, all replaced by Bill Budge's *Pinball
Construction Set* ([`../../pcs/`](../../pcs/)). Frozen: nothing builds or runs
these, and `run-v3pin.sh` was already out of step with the last `pinball.asm`
when it was retired. The 6809 sources are in `../nitros9`'s
`level2/arm6309/archive/` (`pinball.asm`, `pinballdat.asm`, `pcbtdat.asm`).

| Generation | Files here |
|---|---|
| 61 interned blocks (2026-09-20) | only in git history (`mkpinball.py`'s early output) |
| a 640 × 512 PCB picture read off the card (2026-09-21) | `mkpinball.py`, `pinball.json`, `pinball-art.png`, `pinball-sheets/`, `mkpcb.py`, `pcbtable.*`, `checkpcb.py`, `checkv3pin.py`, `run-v3pin.sh` |
| a 640 × 1280 table streamed through `tscroll.inc` (2026-09-23) | `mkpcbt.py`, `pcbt.bnk`, `pcbt.pal`, `pcbt.png` |

What follows is the bench's own record, as it stood in the video3 bench README.

### ⭐ `run-v3pin.sh` — `pinball`, and what the LUT is worth

`mvania` asks what a game can put on a screen when the room is already in
VRAM, and `monster` what it can when the level is longer than VRAM. **This
one asks what happens when the WHOLE WORLD is in VRAM and nothing streams
at all** — which is the case where the card's scroll costs nothing and the
work moves into the palette. It is `optimizations.md` §10, built.

```sh
sh software/archive/pinball/run-v3pin.sh          # five runs + four mutations, ~30 min. Its exit code is the answer
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
the ROM disk was full, see [`../../docs/history.md`](../../../docs/history.md)).
⛔ **And since 2026-09-22 NOTHING is: the ROM disk is gone**, pages 3–63 are
zeros, and NitrOS-9 itself is on the card.
`recipes/arm6309/arm6309.mak`'s `$(DEMOS)` builds the programs,
`software/nitros9/mkrom.sh` writes the data set to `$OUT/data` **and a whole
`system.img` beside the ROM**, and `software/nitros9/mksyscard.sh` is what
decides what a bootable card carries. ⚠ **There is no "empty socket" bench any
more** — a machine with no card does not start — so the older scene benches
pass `SDIMG=$OUT/system.img` and still pass `CMDS_EXTRA=<name>`, which now
means "add this to the card's command set".

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
