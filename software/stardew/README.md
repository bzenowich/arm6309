# `software/stardew/` — the farm

A Stardew-Valley-like farm scene whose day passes in the palette.

| | |
|---|---|
| 6809 source | `../nitros9` (branch `arm6309`), `level2/arm6309/cmds/stardew.asm`, `stardewdat.asm` (generated) |
| Generator | `bench/mkstardew.py` — the picture, the palette and the table |
| Bench | `bench/run-v3star.sh` (~25 min), checked by `bench/checkv3star.py` |
| Docs | [`docs/stardew.md`](docs/stardew.md) |
| Reference | [`reference/`](reference/) |

### ⭐ `run-v3star.sh` — `stardew`, and the day in the palette

`mvania` asks what a game can put on a screen when the room is already in
VRAM, `monster` what it can when the level is longer than VRAM, and
`pinball` what happens when the whole world is resident and nothing streams.
**This one is not about where the bytes are at all.** It replaces
`overworld` — the archived `video/` card's flagship — and the thing it
exists to show is [`../docs/stardew.md`](docs/stardew.md)'s headline:
⭐ **the time of day changes by palette writes and nothing else.**

```sh
sh software/stardew/bench/run-v3star.sh         # four runs + three mutations + two controls, ~25 min
python3 software/stardew/bench/mkstardew.py --tint-test    # ⚠ §6 item 2, on its own, ~25 s
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
