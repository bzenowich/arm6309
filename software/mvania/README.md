# `software/mvania/` — the metroidvania scene

A metroidvania-like scene, kept as the **measurement** scene: the frame budget is measured on it. It is not on the desktop.

| | |
|---|---|
| 6809 source | `../nitros9` (branch `arm6309`), `level2/arm6309/cmds/mvania.asm`, `mvaniadat.asm`, `mvaniapal.asm` (generated) |
| Generator | `bench/mkmvania.py` |
| Bench | `bench/run-v3mv.sh` (~20 min), checked by `bench/checkv3mv.py` |
| Video | `make video` / `make sheet` - `video/run-video.sh` |
| Reference | [`reference/`](reference/) |

### ⭐ `run-v3mv.sh` — the metroidvania scene, and the frame budget measured on it

`bench/v3char`, `v3copy`, `v3tile` and `v3sprite` ask *does the card do what the
plan says*. This one asks the other question: **with the card doing exactly
that, what can a game put on the screen?** `keyed-copy.md` §6.3 names a
metroidvania as this card's natural genre; `optimizations.md` entries 4 and 5
took the per-copy cost to 344 µs and built the colour key. The scene is where
that gets spent.

```sh
sh software/mvania/bench/run-v3mv.sh            # eleven runs + the tearing gate, ~20 min. Its exit code is the answer
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
