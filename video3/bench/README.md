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
| `run-v3copy.sh` | §6 | **eight copies** — aligned and unaligned columns, both directions in both axes, and **four overlapping**, which is where a direction bit that walks the wrong way destroys its own source. Bitmap mode makes VRAM observable: a byte *is* a palette index *is* a pixel |
| `run-v3tile.sh` | §2.4, §8.1 | the **one-byte** code in lane 0 of a **four-byte** cell (the ROM fills lanes 1–3 with values that are never the cell's code, so a wrong stride or lane shows), 8bpp tiles with no per-cell colour limit, **both scroll axes one pixel at a time, including both ring wraps**, the six-bit cell row at row 63 rolling to 0, **and all four VMODEs** — a vertical ring wrap is a different test in a progressive family, which shows twice the picture rows. ⭐ **And that `ATTR` is zero in tile mode**: every one of the LUT's 65,536 entries is loaded bright green *except* sub-palette 0, so a leak from the attribute path paints the screen |
| `run-v3sprite.sh` | §7 | ⭐ **the shape read from VRAM** — the top 64 bytes of `MAPBASE`'s region, `$7FFC0` at `MAPBASE` 7 — with a decoy (the shape inverted) at `MAPBASE` 0's `$0FFC0`, so a card that ignores `MAPBASE` draws the wrong arrow. **Thirty-six positions in one run** — every X phase mod 8, both 4-byte phases, both screen edges, the line-doubling boundary **and all four VMODEs**, because the sprite covers eight *picture* rows either way: sixteen scanlines in the doubled families and eight in the progressive ones. The ROM writes each position to `$C208`/`$C20A`, the two words `machine.c` records with **every** frame (`overworld`'s camera mechanism), so each frame is judged against its own position |

Each generator writes an `.asm` **and** a `.json`; `../tools/v3model.py` reads the
JSON and renders from the plan.

⭐ **The ROM and the model share the JSON — the data — and no code.** Two
implementations of the plan agreeing is evidence; one implementation agreeing with
itself is not. That is the discipline `software/nitros9/tools/vtmodel.py` keeps, and
`v3model.py` reuses `software/demo/tools/frames.py` so the recording's format is not
transcribed twice either.

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
