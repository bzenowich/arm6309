# `video/` — the 256-colour video card

640×200 in **256 colours**, 80×25 text, a scrolling bitmap and a span writer, out of a
VGA connector at the standard 25.175 MHz dot clock. **30 ICs** — 26 if the tri-state
pixel bus closes at 39.7 ns and the `'153` mux is not needed — of which the
programmable logic is **2 × `ATF1508AS` in PLCC-84 plus one `GAL22V10`**, alongside a
three-transistor analog drive stage. **~0.75–1.3 A at 5 V, 0.9 A nominal.**

The logic is written, fitted and checked at the fuse level —
[`hardware/gal/video.cpld.ts`](../hardware/gal/video.cpld.ts) and
`hardware/gal/cpld/`, with the arbiter's `GAL22V10` checked against Atmel's own
compiler by `npm run check:cupl`.

> ⚠ **The count has moved three times and this file was the last to hear.** It said
> ~~"~33 ICs"~~ against a §14 table that summed to 36, then **41 with 10 GALs** once
> the posted-write address latches, the arbiter, the `VSTAT` driver and the analog
> buffer stage were counted honestly. **Then `graphics.md` §10.1.6 replaced the ten
> GALs with two `ATF1508AS` on 2026-09-06 and nobody carried the arithmetic back**, so
> three counts were live at once. **30 is the reconciled figure** — `graphics.md` §14.1
> has the line-by-line derivation, and power fell with it from ~~1.2–1.8 A~~ because
> ten GALs at 70–90 mA each were most of an amp.

Paths below are relative to this directory; build commands run from the repository
root.

| | |
|---|---|
| [`docs/graphics.md`](docs/graphics.md) | the card: what carries over from `colormin`'s 256-colour design and what has to change for a 6309 machine |
| [`docs/features.md`](docs/features.md) | **what the card can do** — the four bitmap and four text modes, the span writer, polygon fills, what a blitter and a display list would add, sprites, and the mouse cursor. `graphics.md` is organised around decisions; this one is organised around capability |

Two companion documents live at machine level rather than here, because they are
comparisons rather than specification:

- [`../docs/video-comparison.md`](../docs/video-comparison.md) — this card against the
  GIME and the VIC-II
- [`../docs/coco3_c64.md`](../docs/coco3_c64.md) — GIME vs VIC-II, from a
  CPU-replacement's point of view

## Status

**Specified, nothing built.** There is no code here and no `CMakeLists.txt`; the card is
discrete logic and the deliverable is the document.

`docs/graphics.md` §18 gives the build order. Step 1 — bench the dot path on a
breadboard **including the analog drive stage** — **comes before laying out anything**,
because it contains the design's real unknowns.

⚠ **Both CPLDs are full in the dimension that matters.** `vaddr` is 101 of 128 logic
cells and 62 of 64 pins; **`vctrl` is 112 of 128 and 64 of 64** — zero spare, which is
why it has no JTAG and is programmed out of circuit. Anything added to either
displaces something else, and `graphics.md` §10.1.6.3 records what it would cost to
get in-circuit programming back.

**Specified at ÷12 only.** E = 25.175/12 = 2.0979 MHz is the rate this card is
specified at. The ÷8 rate — fast-E mode, 3.1469 MHz — is **experimental and not
guaranteed**: flat VRAM read-back does not close there (§11), and it is one of three
independent things in the machine that break at that rate.

`graphics.md` also carries the machine-level material the other cards depend on: the
one-oscillator clock tree (§5 — the oscillator is on the **motherboard**, not this
card), the MMU (§6.3, and §6.3.1 for where it landed and why it is **5 ICs**, not 3),
the `/IOPAGE` backplane signal without which a flat VRAM map is electrically unsafe
(§6.3.2), and the backplane signal list (§17). Those have been lifted into
[`../docs/machine.md`](../docs/machine.md).
