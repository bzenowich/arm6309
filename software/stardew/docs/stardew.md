# A Farming Demo for video3

## Replacing `overworld`, and Spending the Whole Day on the Palette

**Question this answers:** `overworld` is the machine's flagship scene and it was written
for [`video/`](../../../hardware/archive/video/), on `libvid`, in a 16-colour tile mode. That card is
archived. What replaces it, and what should the replacement be *for*?

**Short answer: a Stardew-Valley-shaped farm, and the thing it exists to show is that
this card can change the time of day without writing a pixel.** The world scrolls, the
farmer is the hardware sprite, the crops and the chickens are keyed blits — all of which
`mvania`, `monster` and `pinball` already demonstrate. **The day/night cycle is the new
claim**, and it is the one no other card in this project could make.

**Constraints taken as given (yours):**
- It replaces `overworld` rather than joining it.
- video3, through `v3lib.inc` — the access layer the other three scenes include.
- The demos live on the SD card now, not in the ROM.

> **Status: built, 2026-09-21.** The scene is the port's
> `level2/arm6309/cmds/stardew.asm`, its art and its palette are
> `software/stardew/bench/mkstardew.py`, and its bench is `software/stardew/bench/run-v3star.sh` with
> `checkv3star.py`. ⭐ The desktop's Applications menu launches it
> ([`../../docs/boot-and-desktop.md`](../../desk/docs/boot-and-desktop.md) §3.2).
> Superseded numbers are in [`history.md`](../../../hardware/video3/docs/history.md).

---

## 0. Summary — the verdict in one table

| | |
|---|---|
| **The world** | 1024 × 480 of farm, in the card's ring; the view is 640 × 200 and scrolls in both axes |
| **The farmer** | the card's one hardware sprite — free, and it is the thing the camera follows |
| **Everything else that moves** | keyed copies: chickens, crop growth stages, the dog |
| ⭐ **The day/night cycle** | **palette writes and nothing else.** Dawn to dusk to night over the run — and ⛔ **not one pixel of the world is redrawn**, which the bench states as one claim: the run *with* the cycle and the run *without* it leave the 1024 × 480 world byte for byte the same |
| ⚠ **What it costs, measured** | **0.185 ms a frame inside a 354 µs blank** for six LUT writes, and **1.378 ms outside it** for the arithmetic. ⛔ The two are separate and have to be: a tint entry is 250 µs of multiplying on this CPU and the blank could not hold one, let alone four (§2) |
| ⚠ **What stays lit** | reserved indices the tint never touches: window glow, the lantern, the stove, fireflies, the moon on the pond. This is how pixel art does night, and it is free here |
| **Where it lives** | `/SD0`, art and all — the world is bigger than a ROM module and that is the point |

---

## 1. Why this scene, and why now

Three scenes exist and each answered a different question: `mvania` "what fits on a screen
already in VRAM", `monster` "what fits when the level is longer than VRAM", `pinball`
"what happens when the whole world is resident and nothing streams". All three are about
**where the bytes are**.

This one is about **the look**. A farming sim is the genre that most rewards 256
simultaneous colours — earth, foliage, water and sky in one frame, none of them flat —
and it is the genre where *time passing* is the whole feeling. On a 16-colour card a day
cycle is a palette swap and it looks like one. Here the palette is 256 entries of
RGB565, so dawn can actually be dawn.

⛔ **And the cost of a day cycle on this card is not the pixels.** `pinball` established
the mechanism — its lamps and its scoreboard are palette entries, not art — and the copy
engine never hears about it. What the day costs here is **1.55 ms a frame** of a 14.27 ms
frame (11.79 ms against the same scene with the cycle disabled at 10.24), and only
**0.185 ms** of that is inside the blank. Re-tinting the world's 200 art colours six at a time takes 34
frames, and a 15-second run is about 1,050.

---

## 2. The palette, which is the design

256 entries, and the split is the specification:

| Range | Count | What |
|---|---|---|
| 0 | 1 | ⛔ the copy engine's colour key. Never a visible colour |
| 1–200 | 200 | **the world's art, and the only entries the day tint touches.** Authored at noon and re-tinted towards each key time |
| 201–230 | 30 | ⭐ **the lit set** — window glow, the lantern, the stove, fireflies, the moon. The tint never touches these, so they stay their own brightness and *become* the light as everything else darkens |
| 231–255 | 25 | the HUD: the day bar, its marker, the energy bar. Constant, because a UI that dims with the sun is a UI nobody can read |

**Four key times, interpolated.** Dawn (a cool blue-violet wash, low contrast), day
(the authored colours, untouched), dusk (warm, orange-shifted), night (deep blue,
heavily desaturated, ~30 % value). The driver holds the authored RGB and multiplies
towards the key time's tint. ⚠ **The tint is per-entry multiply-and-shift, not a lookup
of 200 × 4 precomputed palettes** — 1,600 RGB565 words is 3.2 KB of data that grows with
the palette. What *is* precomputed is the other axis: **256 phases × six coefficients**,
1.5 KB that does not grow with the palette at all, emitted by `mkstardew.py` as data so
that the 6809 and the checker cannot disagree about an interpolation.

**The contract, per channel**, with gain `g` (128 = unity), offset `o`, the entry's fixed
rounding bias `d` and a shift `s` of 3 for red and blue and 2 for green:

```
v = (c * g) >> 7 ; clamp 255 ; v += o ; clamp ; v += d ; clamp ; v >> s
```

⭐ **128 is unity exactly**, and that is what makes "a whole day comes home" a bit-exact
claim rather than a rounding argument. `stardew.asm`'s `TintC` and `mkstardew.py`'s
`pipeline()` are two implementations of this and must agree bit for bit; they share the
data — the authored RGB, the bias byte, the coefficient table — and no code.

⛔ **The arithmetic cannot live in the blank, and this is the design's one surprise.**
Nine multiplies and six clamps an entry **measured 250 µs** on the 2.098 MHz 6809E, so
four of them is 1.0 ms against a blank that has 354. What has to be inside the blank is
the **write**, which is two register stores. So a frame *computes* six words into a RAM
buffer in its own slack — where there are milliseconds — and the **next** frame's blank
*writes* them, at ~31 µs an entry including a live `VSTAT` check before each one. ⚠ The
consequence is that an entry's colour lags the day by up to the round-robin's own depth
(8 of 256 phases at the scene's own rate), so the scene reports its **commit cursor**
every frame and the checker reads which entry was written at which phase off the
recording rather than replaying the schedule.

> ⚠ **The one thing to get right: the tint must be applied to the AUTHORED colour, never
> to the current one.** Re-tinting a tinted entry compounds, and over 1,050 frames the
> world converges on black — a drift that looks like a slow bug and is very hard to spot
> in a contact sheet. The authored palette is copied into RAM at start-up and is the
> source of truth; the checker asserts that a full cycle returns entry-for-entry to it,
> and `stardew`'s mode b5 is the mutation that breaks it on purpose (§5).

---

## 3. The world and the camera

**1024 × 480 in the ring**, which is the whole farm: the house and its porch, a tilled
field of crop rows, a barn, a pond with a dock, a path, the forest edge. The view is
640 × 200 and the camera follows the farmer, so ~400 columns and ~280 rows are off-screen
at any moment — a real world to walk around in rather than a strip.

⭐ **Nothing streams.** At 1024 × 480 the farm is 491,520 bytes and the ring is 524,288,
so the whole world fits with 32 KB to spare and the scroll is two register writes, as
`pinball` established. ⚠ **That spends the ring**, which is the trade: there is no room
for `monster`'s clean band, so the actors restore with save-behind, and the 32 KB left is
exactly the keyed art bank (ring rows 480–495), the save-behind scratch (496–511) and
the sprite's shape in row 511's last 64 bytes at `MAPBASE` 7.

⛔ **Save-behind means three phases and not two**: every restore runs before any save and
every save before any draw, because a save must see pristine world. `pinball`'s gate
found the two-phase version, and two chickens in one place is not a corner case.
⛔ **And the crop retirement goes between the restores and the saves** — it is the one
place it can go, because a crop stage *changes* the world and is never restored. ⚠ The
actor sweep is what found that: at the scene's own seven actors nothing stood on a plot
at the moment one grew, and at twenty a chicken did.

**The camera is clamped** to 0–384 and 0–280, so no rectangle in this scene ever crosses
the ring's seam. `monster` is what exercises the wrap.

**Loaded from `/SD0`**, a VRAM row at a time — one `I$Read` of 1,024 bytes and one
`VDATA` run — into ring rows 0–479. ⭐ **The loading screen is free**: both scroll
registers are zero while it runs, so the top of the farm appears row by row as it
arrives.

---

## 4. What moves, and what it costs

Measured on the host emulator, at the scene's own cast of seven (six chickens and the
dog) plus the HUD, against a 14.27 ms frame:

| | ms a frame |
|---|---|
| the farmer | **0**, he is the hardware sprite; his gait costs 64 `VDATA` writes when the frame changes |
| the scroll pair, written in the blank | **0.043** |
| ⭐ the day's LUT writes, in the same blank | **0.185** |
| the sprite's gait, when it changed | 0.085 |
| the game's logic — the camera, the farmer's walk, every actor's ellipse | 2.152 |
| ⭐ the day's *arithmetic*, six entries, outside the blank | **1.378** |
| the restores, and the crop retirement between them and the saves | 2.242 |
| the saves and the draws | 5.692 |
| **what is left of the frame** | **2.48** |

| | |
|---|---|
| ⭐ **what the day costs** | **1.55 ms a frame** against the same scene with the cycle off (11.79 against 10.24), of which **0.185 is in the blank** and the rest is multiplying |
| ⭐ **what the OS call costs** | `SS.Scroll` instead of the blank write: **+1.08 ms a frame** (11.79 → 12.87). §8's 1.05 ms of IOMan, SCF and the kernel, measured now on a **fourth** scene |
| ⭐ **the most actors that fit** | **9**, from the sweep's slope — **4.495 ms of frame + 1.015 ms an actor**. The work first passes 14.27 ms at 12, and the first dropped frame is at 12 |
| ⛔ **~2.4 ms of that 4.495 fixed cost is the HUD** | it follows the camera, and this card has one buffer, so 160 × 16 is restored, saved and redrawn **every** frame — three 2,560-byte rectangles and a keyed marker. A status bar that did not move would be free |
| ⛔ **the blank an exclusive owner really has** | the poll returns **1,186 µs into a 1,559 µs blank** and leaves **354**. `monster` and `pinball` measured the same. The scroll pair plus six LUT writes is **228 µs** at worst, which is why `SWMAXPW` is six |

⚠ **This is tighter than a farm looks.** 2.48 ms spare at seven actors is not `monster`'s
5.2 or `pinball`'s 9.7, and two lines are why: the HUD's three big rectangles (~2.4 ms of
the 4.495 ms an empty frame costs), and the tint's 1.378 ms of multiplying. Both are the
price of features the other scenes do not have. ⚠ **If it needs more room, the HUD is the knob** — not the chickens.

⛔ **And that is why there are no falling leaves**, which §0 originally listed beside the
chickens and the dog. An actor is 1.013 ms whatever it is a picture of — it is three copy
rectangles — so a drift of leaves is not decoration, it is the whole remaining budget.
The cast is a table (`CastTab`, emitted by `mkstardew.py`) and adding them is one record
each; what there is no room for is the time.

---

## 5. How it is checked

`software/stardew/bench/run-v3star.sh`: four runs, three mutations and two negative controls.
The discipline the other three scenes keep, and ⭐ **two claims they could not make**:

| | |
|---|---|
| the VRAM gate | after every actor and the HUD have been restored, the world is rebuilt from `stardew.pic` and the crop stages the scene's own retirement count says it grew, and compared byte for byte — the keyed art bank with it. ⭐ And separately: outside the crop plots the world is the file exactly, which is what says 491,520 bytes came off the card unaltered |
| ⭐ **the palette gate** | a day cycle touches **no VRAM at all**, so the byte compare is structurally blind to the entire headline feature. The LUT is read off the **recording**, **index by index**: the world is known and the camera is in the marks, so every pixel's index is known — and the **modal colour of an index's pixels is what the card's LUT held for it**. That is compared with the tint the driver should have reached, which the commit-cursor marks say. ⛔ **With a negative control**: mode b0 writes no LUT entry and must read the authored palette at every checkpoint and no other |
| ⛔ **the compounding gate** | one full cycle must return every art entry to its authored value. The scene ends by pinning the day at noon and putting all 200 entries back through the same arithmetic at unity gain, after which the LUT must be the authored palette bit for bit. This is §2's drift, and it is the failure this scene was most likely to ship with |
| ⭐ the join, as a claim | the camera the scene reported has to be the camera the card showed — ~89 % of the view's pixels carry their own index's colour at the worst checkpoint. ⚠ And the join itself is **physical**: a field's pixels were decided in the blank *before* its first active line, so the frame mark is the last `$10` before that `A`. The camera cannot choose between candidates, because when it is clamped at an edge two consecutive frames report the same one |
| the tearing gate | `$11` is marked when the scroll pair is in the card and `$12` when the frame's LUT writes are, and both must land in `[V, A)`. ⭐ With a control — the actor phase must end in the **picture** |
| ⛔ the mutations | **b5** applies the tint to the value the card holds instead of the authored one, and the compounding gate must catch it; **b6** draws actor 0 and never restores it and **b3** skips the final Wipe, and the VRAM gate must catch both. ⚠ A palette mutation breaks both of the palette gate's claims and no VRAM claim, which is the asymmetry that made a second gate necessary in the first place |
| ⛔ the negative controls | with **no card** the program is not findable and the machine says so; with a card carrying the **program and no world** the scene's own error path answers, and not one frame of scene is drawn. ⛔ **And that path ends its window**: a `DWSet` with no matching `DWEnd` leaves the window *defined*, so the next one answers `E$WADef` — which at the shell reads as `Error #184` and under the desktop reads as a desktop that never repaints again |

---

## 6. Open items

1. **The art** — done. `software/stardew/bench/mkstardew.py`: a 1024 × 480 farm, 200 colours by
   median cut over its own pixels, **snapped to the grid the LUT really stores** and then
   Floyd–Steinberg dithered against it, with the lit set and the HUD set painted in
   *after* the dither. ⛔ Index 0 is the key and the search never returns it;
   `assert_key_free` checks it anyway. ⭐ **And the reserved colours are nudged to RGB565
   words no art entry ever takes at any of the 256 phases** — a harder thing to ask than
   `pinball` asked, because there the art never moved. 90 % of the 65,536 words are free
   at every phase, so it costs nothing.

2. ⚠ **Whether the dither survives the tint — measured, and it does.**
   `python3 software/stardew/bench/mkstardew.py --tint-test` renders one region (the pond's depth
   ramp and the grass beside it), dithers it against the whole farm's palette, and at
   each of the 256 phases compares the **displayed** picture with the **ideal** — the same
   continuous tone with the same affine tint in floating point — on 4 × 4 block means,
   which is the scale at which banding is visible.

   | bias | band at noon | dawn / dusk / night | worst block | levels, noon → night |
   |---|---|---|---|---|
   | none | 6.13 | 6.37 / 6.35 / 6.32 | 37.7 | 113 → 77 |
   | ⭐ hash | **4.94** | 5.50 / 5.20 / **3.75** | **27.0** | 126 → 77 |
   | ramp-ordered | 5.28 | 5.44 / 5.49 / 3.40 | 29.8 | 119 → 79 |

   ⭐ **The low-frequency error at every key time is within ±0.6 of the noon floor, and
   lower at night.** The reason is structural and worth stating: a per-channel affine
   tint **commutes with averaging**, so the tint itself cannot break a dither — only the
   requantisation to 5/6/5 afterwards can. What that costs is **texture, not
   smoothness**: 113 of the region's distinct LUT words collapse to 77 at night's ~0.3
   gain, which is what five output bits at that gain means and which no palette can
   prevent.

   ⚠ **Crawl is real and sub-LSB.** One phase step moves up to 87 % of the region's
   entries (34 % on average), but a 4 × 4 block's own colour by at most **9 of 255** —
   one red LSB, and only where a block is a single flat index — and 2.2 on average.

   **The mitigation taken** is a fixed per-entry rounding bias, one byte of data an
   entry, added before the truncation so that the two members of a dither pair do not
   round the same way: **−23 % mean banding error and −28 % worst block**. ⚠ **And the
   ramp-ordered bias is worse than the hash**, which is the counter-intuitive part:
   ordering the bias by luminance correlates it with the ramp again, which is the
   opposite of what is wanted.

3. **Where `overworld` goes.** Still open. It is the `video/` card's scene and is
   archived with it, and it is still the only demo with a tile/map engine — nothing in
   this scene needed one, because a farm that fits in VRAM has no map.

4. The farmer's sprite is 16 × 16 and the card has **one**. A scene with a dog and six
   chickens has no second sprite for any of them, which is why they are blits.

5. ⚠ **`software/nitros9/mksddisk.sh`'s `ALL` list does not name `stardew`.** A bench
   that asks for the demo by name gets it; a call with no names still builds a card
   without it. The two lists are deliberately not derived from one another
   (`mksddisk.sh`'s own note), so this is a one-word change somebody has to make.
