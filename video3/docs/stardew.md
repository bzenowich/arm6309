# A Farming Demo for video3

## Replacing `overworld`, and Spending the Whole Day on the Palette

**Question this answers:** `overworld` is the machine's flagship scene and it was written
for [`video/`](../../archive/video/), on `libvid`, in a 16-colour tile mode. That card is
archived. What replaces it, and what should the replacement be *for*?

**Short answer: a Stardew-Valley-shaped farm, and the thing it exists to show is that
this card can change the time of day without writing a pixel.** The world scrolls, the
farmer is the hardware sprite, the crops and the chickens are keyed blits — all of which
`mvania`, `monster` and `pinball` already demonstrate. **The day/night cycle is the new
claim**, and it is the one no other card in this project could make.

**Constraints taken as given (yours):**
- It replaces `overworld` rather than joining it.
- video3, through `libv3` — the access layer factored out of the other three scenes.
- The demos live on the SD card now, not in the ROM.

> **Status: specified, nothing built.** The deliverable is this document.

---

## 0. Summary — the verdict in one table

| | |
|---|---|
| **The world** | 1024 × 480 of farm, in the card's ring; the view is 640 × 200 and scrolls in both axes |
| **The farmer** | the card's one hardware sprite — free, and it is the thing the camera follows |
| **Everything else that moves** | keyed copies: chickens, crop growth stages, the dog, falling leaves |
| ⭐ **The day/night cycle** | **palette writes and nothing else.** Dawn to dusk to night over the run, at ~4 LUT entries a frame, ~240 µs inside a blank that has 353 — and **not one pixel of the world is redrawn** |
| ⚠ **What stays lit** | reserved indices the tint never touches: window glow, the lantern, fireflies. This is how pixel art does night, and it is free here |
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

⛔ **And the cost of a day cycle on this card is not the pixels, it is nothing at all.**
`pinball` already established the mechanism — its lamps and its scoreboard are palette
entries, not art — and measured a commit at ~60 µs of CPU with at most four fitting a
blank. A farm scene needs no more than that: re-tinting the world's 200-odd art colours
four at a time takes ~50 frames, and a 15-second run is about 1,050. The cycle can go
round twice and still be idle most of the time.

---

## 2. The palette, which is the design

256 entries, and the split is the specification:

| Range | Count | What |
|---|---|---|
| 0 | 1 | ⛔ the copy engine's colour key. Never a visible colour |
| 1–200 | 200 | **the world's art, and the only entries the day tint touches.** Authored at noon and re-tinted towards each key time |
| 201–230 | 30 | ⭐ **the lit set** — window glow, the lantern, the stove, fireflies, the moon. The tint never touches these, so they stay their own brightness and *become* the light as everything else darkens |
| 231–255 | 25 | the HUD: the clock face, the energy bar's ramp, the season banner. Constant, because a UI that dims with the sun is a UI nobody can read |

**Four key times, interpolated.** Dawn (a cool blue-violet wash, low contrast), day
(the authored colours, untouched), dusk (warm, orange-shifted, long shadows), night (deep
blue, heavily desaturated, ~35 % value). The driver holds the authored RGB and multiplies
towards the key time's tint; each frame it commits the next four entries it has not yet
caught up on. ⚠ **The tint is per-entry multiply-and-shift, not a lookup of 200 × 4
precomputed palettes** — 1,600 RGB565 words is 3.2 KB of data to save maybe 20 µs a
frame, and the frame has 5 ms spare.

> ⚠ **The one thing to get right: the tint must be applied to the AUTHORED colour, never
> to the current one.** Re-tinting a tinted entry compounds, and over 1,050 frames the
> world converges on black — a drift that looks like a slow bug and is very hard to spot
> in a contact sheet. The authored palette stays in RAM as the source of truth. The
> checker asserts that a full cycle returns entry-for-entry to the authored values.

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
exactly the save-behind scratch and the sprite shapes.

**Loaded from `/SD0`.** 491,520 bytes at `rbsd`'s ~130 KiB/s is **3.7 s** — a loading
screen, which is period-correct and worth showing rather than hiding. ⚠ That number is
the driver's current rate, not the card's; `CMD18` and a 6309 build together would make
it ~0.9 s (`sdcard.md` §9.4).

---

## 4. What moves, and what it costs

Per-frame budget against 14.27 ms, using `monster`'s measured figures (a copy is ~87 µs
of driver plus 0.247 µs a byte):

| | |
|---|---|
| the farmer | **0**, he is the hardware sprite; his gait costs 64 bytes when the frame changes |
| six chickens, 16 × 16, restore + keyed blit | ~0.53 ms each ⇒ **3.2 ms** |
| the dog, 24 × 16 | ~0.6 ms |
| crop growth, one plant retired to its next stage per frame | ~0.15 ms |
| the day tint, four LUT entries | **0.24 ms**, and it is in the blank |
| the HUD's clock digits, when they change | ~0.1 ms |
| scroll | **0.03 ms** |
| **left** | **~9.4 ms** |

So the scene is not close to its limit, and that is deliberate: `mvania` and `monster`
were sweeps that found where the frame breaks, and this one is a picture that should look
calm. ⚠ **If it needs to prove a ceiling, the chickens are the knob** — the same
0.53 ms-an-actor slope those scenes measured.

---

## 5. How it will be checked

The discipline the other three scenes keep, and one claim they could not make:

| | |
|---|---|
| the VRAM gate | after every actor has been restored, the world is rebuilt from the generator's own data and compared byte for byte, as `pinball` does |
| ⭐ **the palette gate** | a day cycle touches **no VRAM at all**, so the byte compare is structurally blind to the entire headline feature. The LUT's contents are read off the recording at N checkpoints and compared against the tint the driver should have reached. ⛔ **With a negative control**: a run with the cycle disabled must match the authored palette at every checkpoint and no other |
| ⛔ **the compounding gate** | one full cycle must return every art entry to its authored value. This is §2's drift, and it is the failure this scene is most likely to ship with |
| the tearing gate | the scroll pair and the LUT commits reach the card inside the blank, as `pinball` asserts |
| the negative control | with no SD card the demo must fail to load and say so, not run on a black farm |

---

## 6. Open items

1. **The art.** A 1024 × 480 farm, 200 colours, Floyd–Steinberg dithered against the
   RGB565 grid, with the lit set and the HUD set held out of the dither exactly as
   `mkpinball.py` holds its lamps out. This is the largest single piece of work.
2. ⚠ **Whether the dither survives the tint.** Floyd–Steinberg chooses neighbouring
   palette entries to average to a colour; if the tint moves those entries by different
   amounts the dithered texture can band or crawl. **Unverified, and it is the technical
   risk in this design.** The mitigation is to tint in a way that preserves the ordering
   and spacing of the ramp each dither pair came from — test it on one region before
   committing to the whole farm.
3. **Where `overworld` goes.** It is the `video/` card's scene and it is archived with it,
   but it is also the only demo with a tile/map engine. Decide whether anything in it is
   worth porting or whether this replaces it outright.
4. The farmer's sprite is 16 × 16 and the card has **one**. A scene with a dog and six
   chickens has no second sprite for any of them, which is why they are blits.
