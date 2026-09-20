# `video3/bench/` — the host-emulator model

**video3 is modelled in `software/demo/emu/machine.c` beside `video/`, not instead
of it.** `VIDEO3=1` selects it; without it the emulator is the card it always was,
so `run-emu.sh`, `run-vid.sh` and `software/nitros9/run-emu.sh` are unaffected.

```sh
sh video3/bench/run-v3.sh            # all three, ~1 min. Its exit code is the answer
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
