# `tilescroll` — history

Superseded text from [`scrolling.md`](scrolling.md), keyed by its section
numbers, with the date it moved and what replaced it. The spec says only what
is true now; this is the record of how it got there. Entries keep the
technical content verbatim.

---

## 2026-09-28 (later) — an armed walk, null records, and the records by `TFM`

The same day, `v3walk` gained an **armed GO** (SELECT 7 then GO starts the walk at the
next rise of `VBLANK`) and a **null shape** (31: every copy that reads the record is
skipped) — `hardware/video3/docs/plan.md` §6.4. `tilescroll` (edition 3) uses both, and
reorders its frame so the CPU-only work runs under the walk. `walkcast.py` dropped each
creature's fourth shape, which was its second again, to free shape 31.

### §0 — the actors row

> The default cast's walk is lines 484–522 of a 525-line frame: **0 torn lines in 1,199
> frames**, with flyers drawn as high as line 0

### §8.1 — four shapes a creature

Every creature row of the cast table said **4** shapes, the fourth drawn separately
though it equalled the second: 8 + 6 × 4 = 32, the whole shape space.

### §8.2 — "One store in the blank" (the section as it stood)

> A frame is: wait for `VBLANK` to rise, the scroll pair, **the GO**, the
> streaming, the camera, the creatures' logic, then the tables.
>
> - **The records are double-buffered.** `WRec` writes the next frame's into the
>   bank this frame's walk did not draw from, after `Logic`, so the blank holds
>   nothing but the GO. The GO's `CB` names the bank; the restore reads the other.
> - **Every slot is walked every frame.** An actor not wholly on screen is
>   **parked**: its record points at its own save cell, so its save is a copy onto
>   itself, its draw lands in its own scratch, and its restore puts the scratch
>   back — none of it reaches terrain, and the walk costs the same whoever is
>   visible. `pk` remembers, per bank and slot, who is parked.
> - **The first walk is `NR`** (nothing to put back), and the end of the run is a
>   **restore-only** walk, bounded by a poll of `VSTAT.WALK`, so the ring gate sees
>   pure terrain.
> - ⛔ **The contract** — `WMODE` not 11, `WADV` b2 clear, no copy running — is kept
>   by a `V3Wait` and a `V3Mode #WM.Direct` in front of the GO, and the emulator
>   reports any breach as a `FAIL`.

The records were written with `sta` loops straight to `SWDAT`.

### §8.3 — the parked records

> `WFix` … rewrites … every slot's `SAVE`, both shape tables, and ⚠ **the record of
> every slot parked in the bank the next walk restores from** — because that record's
> destination is a save cell too.

(`PkFix` did it; a null record points nowhere, and `PkFix`, `PkSet` and `pk` are gone.)

### §8.4 — the measurements before the armed GO

> | **m0** — 6 creatures and the hero | 1.21 ms | 484 → 522 of 525 | ⭐ **0 lines in 1,199 frames**, with keyed draws in the top 64 lines in 217 of them and as high as line 0 |
> | **s1** — 13 creatures and the hero | ~2.4 ms | 485 → 34 | ⛔ **4,916 lines in 428 frames — every one of them in lines 0–34** |
>
> ⚠ **m0 has three lines of blank to spare**, and that is the budget: another
> 16 × 16 actor is ~1,200 dots, about 1.5 lines. A cast that grows needs smaller
> kinds, or the fast actors walked first so that the overrun lands on the slow
> ones.

### `walker.md` — as first written that morning

It said SELECT took tables 1–6; that **"The walk starts when the write ends"** and, under
§4.2 *"It is not triggered by VBLANK"*, that the program must wait for `VBLANK` and write
GO first thing in the blank (`Frame`, then `WGo`); that **"No bench in this repository has
run a `TFM` into `SWDAT`"**; that the way to hide a slot without changing n was to
**park** it on its own save rectangle, which *"still does its three copies"*; that the
default cast measured **484 → 522** (1.21 ms); that s1's torn lines were all in 0–34; and
that `tilescroll`'s order was `WGo` → streaming jobs → movement and logic → `WFix`/`WRec`.

## 2026-09-28 — the actors moved to the sprite walker

`hardware/video3/docs/plan.md` §6.4 built `v3walk`, a fifth CPLD on the video
card that restores, saves and draws up to sixteen sprites from tables in the
register file on ONE command. `tilescroll` became its first user
(`scrolling.md` §8): every actor is walked every frame, there is no movement
budget, no beam line and no draw order to choose, and the cast went from
32 × 32 zelda-style creatures to seven kinds in five sizes (`walkcast.py`).
tscroll.inc's CPU actor pass (`Actors`, `Actv`, `Sort`, `Token`) is no longer
called by `tilescroll`.

### §6.2 — the strip moves in one frame (the paragraph as it stood)

The engine now moves **the scratch strip alone** in one step, as two 256-row
copies in the frame its `colslt` entry swaps: a walker saves *every* actor
*every* frame, so a strip spread over two frames carries two frames' saves.
(`CHEIGHT` is nine bits, so it cannot be one 512-row copy — the first try asked
for 512 and got 0, and left 883 bytes of residue at 1,200 frames.) The paragraph
it replaced:

> ⛔ **And that is why the strip has to move in ONE frame.** It was four pieces
> spread over two; a save taken *between* two of them was written into the
> strip's old slot, and the pieces already copied did not carry it, so the
> restore a frame later read a tile that had been left behind. 509 bytes of
> residue at 300 frames, growing with travel. It is 4.3 ms in that one frame,
> once every 32 pixels — affordable where a wrong answer is not.

### §6.4 — the hero drawn first (replaced: slot 0 is walked first)

The walker draws in slot order and the hero is slot 0, so he is first by
construction, and a whole cast's walk (~1.2 ms) ends inside the 1.43 ms blank
anyway. The section as it stood:

> **6.4 ⭐ And the hero is drawn FIRST among the draws.** A copy here is **485 µs**
> and not the 313 the engine's 1024 bytes would suggest — the register protocol
> is the other half — so a seven-actor pass is **10.2 ms** and the beam reaches
> his row 224 at **1,430 + 224 × 31.78 = 8,549 µs**. Drawn in his sorted place he
> was erased under the raster in **84 %** of frames: on screen, a hero who
> flickers on and off in half-second blocks. Drawn first he is written at
> `(2N+1)` copies rather than `(2N+rank)`, and is **missing in 0 of 1,076 scene
> frames**. ⚠ The price is that a creature standing above him is drawn over him
> rather than behind; they are 32 pixels across in a 640 × 480 view and he is at
> its centre, so it is rare — and a hero who flickers is not a trade against
> anything.
> 
> ⚠ **THE MEASUREMENT THAT NEARLY WASN'T.** The first count said he was still
> missing 9 % of the time, and those 109 frames were **the recording continuing
> after the program had finished and wiped the actors off**. The scene's own end
> marker (progress `$F7`) is 10 ms before the first "missing" frame. ⛔ A bench
> that measures a scene must bound the window with something the SCENE emits, not
> with the length of the recording.

### §6.5 — the movement budget (withdrawn)

With the walker there is nothing to budget: a resting creature costs exactly
what a moving one does, and the whole cast ends in the blank. `ZTOPB`, `ZMOVE`
and `Token` went; the flying kinds now go to the top 64 rows **on purpose**,
because those are the rows the measurement is about. The section as it stood:

### 6.5 ⭐⭐ Most of them are standing still, and that is the whole budget

**2026-09-23.** The creatures in the top half of the screen tore frequently —
the pass was 7.3 ms and the raster reaches screen row 150 at 6.2 ms. The fix
was not to draw faster:

> *not every on-screen creature needs to be moving in every frame. Limit it to
> just 1–2 moving creatures trying to reach their goal positions, with the
> others resting. Once one reaches its goal it can rest, and that frees up
> another to start on a path toward its goal.*

⭐ **And a resting actor costs nothing at all.** The ring does not move when
the camera scrolls — `HSCROLL` and `VSCROLL` change what the raster *reads*,
not what is written — so an actor that does not move **stays drawn, for free,
for as long as it likes**. ⛔ It also cannot tear, because nothing rewrites it.
Only the movers cost the three copies, and `Token` keeps at most `ZMOVE` = 2 of
them walking.

| | |
|---|---|
| **⛔ only pairs with an ACTIVE member count** | skipping a resting actor leaves its pixels in the world while the others take their saves, so a mover's save captures it and the ghost returns when that mover leaves. The overlap test wakes a resting actor that an *active* one is standing on — ⚠ but testing **every** pair cost the whole optimisation, because some pair of six actors in a 640 × 480 view is nearly always within 40 pixels. Two resting creatures on each other are harmless: neither is redrawn, so neither takes a save |
| **⛔ and `Sort` and `Actv` are not in the pass** | they are pure arithmetic with nothing to draw, and at its head they were **2.9 ms of 6809 in front of 4.4 ms of copies**. Moved to the end of `Logic`: **7.3 ms → 3.5 ms median, 4.45 p90**. §11's lesson, paid for a second time |
| **⭐ a token needs the creature to be BELOW the beam line** | the raster reaches screen row *R* at 1430 + 31.78·*R* µs, so a 4.45 ms pass is ahead of everything below row 95. `ZTOPB` = 112 is the line: a creature may only hold a movement token below it, and one that drifts above stops — which is indistinguishable from the resting it does anyway. ⛔ **This is `zelda`'s top wall said a different way**: there the room's geometry kept actors out of the dangerous rows, here the movement budget does |
| **⭐ the budget counts VISIBLE movers only** | an actor off screen costs nothing to move — `Actors` skips it entirely, since save and draw are both gated on visibility — so one that walks out of view keeps walking for free and never denies a slot to a creature the player can see. ⚠ That also settles what happens when a mover leaves mid-journey: **nothing**. It is not interrupted and nobody is woken in its place, which is what stops a resting creature jerking into motion the instant another scrolls off the edge. Walking back into view over budget, it stops where it is — it has just arrived, so standing still is what that looks like |

**The result**, measured over 1,074 scene frames with the octorok's red (the one
body colour no terrain tile shares):

| | before | after |
|---|---|---|
| torn sprites | **4.31 %**, all in screen rows 60–119 | ⭐ **0.12 %** — one in 802, in the top 60 rows |
| the hero | 0 of 1,077 missing | 1 of 1,074 |
| the actor pass | 7.3 ms median | **3.5 ms**, 4.45 at p90 |

⚠ **The moblin cannot be measured this way**: its body green is `$30`, and so
is the forest's lit canopy. A census on a colour the terrain shares reports
90 % torn and means nothing.

### §6.6 — `STEP1` and `STEPD`

Each kind has its own step now (`KindTab`'s `K.STP`), and a diagonal takes it ×
181/256. The sentence it replaced:

> A camera moving two pixels in *each* axis crosses the ground at 2.83 — **41 %
> faster than a cardinal leg**. `PathTab` is in **8.8 pixels a frame** and a
> diagonal leg is **362** rather than 512, which is 2/√2; the camera carries a
> fraction (`cax`, `cay`) so the whole part can be added each frame and the rest
> kept. The creatures do the same with a one-byte 0.8 fraction an axis: `STEP1`
> is `$FF` and `STEPD` is `$B5`.
