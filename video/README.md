# `video/` — the 256-colour video card

640×200 in **256 colours**, 80×25 text, a scrolling bitmap and a span writer, out of a
VGA connector at the standard 25.175 MHz dot clock. **28 ICs** — 24 if the tri-state
pixel bus closes at 39.7 ns and the `'153` mux is not needed — of which the
programmable logic is **2 × `ATF1508AS` in PLCC-84 plus one `GAL22V10`**, alongside a
three-transistor analog drive stage. **~0.5–0.85 A at 5 V, 0.65 A nominal.**

The logic is written, fitted and checked at the fuse level —
[`hardware/gal/video.cpld.ts`](../hardware/gal/video.cpld.ts) and
`hardware/gal/cpld/`, with the `rfa` `GAL22V10` checked against Atmel's own
compiler by `npm run check:cupl`. `graphics.md` §14.1 has the line-by-line count;
the path the count took to get there (~33 → 41 → 30 → 27, with power falling from
~1.2–1.8 A) is archived in [`docs/history.md`](docs/history.md).

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

⭐ **The drive stage is specified and drawn** (§9.1, §9.2, and
`hardware/cards/video.circuit.tsx` since 2026-09-08): a 1 kΩ/2 kΩ ladder, three NPN
emitter followers returned to a shared `V_be` diode, a 75 Ω series source into the
monitor's 75 Ω, and blanking by `74AHCT273` `/MR` for zero packages. **No ICs** — three
transistors, a diode and fifteen resistors — which is what closed `design-review.md`
§Vid-M4. It is still what step 1 has to measure.

⚠ **`vctrl` is full in every dimension.** `vaddr` is **109 of 128** logic cells and
61 of 64 I/O; `vctrl` is **122 of 128** and **64 of 64 I/O — plus 4 of 4 dedicated
inputs**, which `features.md` §8.4's sprite mode spent on 2026-09-09. Those totals
**include JTAG's four**, because the `ATF1508AS` shares `TMS`/`TDI`/`TDO`/`TCK` with
ordinary I/O, and both parts are still programmed in circuit (`graphics.md` §10.1.6.3).

**Nothing further can be added to `vctrl`.** §14.2's two ×16 framebuffer parts return six
output pins by making the arbiter 2 grants instead of 8 — already worth doing, and now
the thing the card's next feature waits on.

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
