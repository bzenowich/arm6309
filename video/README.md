# `video/` — the 256-colour video card

640×200 in **256 colours**, 80×25 text, a scrolling bitmap and a span writer, out of a
VGA connector at the standard 25.175 MHz dot clock. **The card is 33 ICs** on a 24 cm
board — 29 if the tri-state pixel bus closes at 39.7 ns and the `'153` mux is not
needed — of which the programmable logic is **3 × `ATF1508AS` in PLCC-84 and no
GALs**, alongside a three-transistor analog drive stage. **~0.6–0.95 A at 5 V, 0.75 A
nominal.**

⭐ **It grew by eight packages on 2026-09-09 and seven of them are features that were
already specified and had no hardware**: §8.2's byte-granular horizontal scroll (a
second rank of fetch latches), §9's palette **write path** — which had no producer at
all, so the CPU could not put a colour on the screen — and §10.3.3's display-list
register port. The third CPLD `vsup` went the other way: it absorbed all three
`GAL22V10`s, so **a third PLCC-84 reduced the package count by two.**

The logic is written, fitted and checked at the fuse level —
[`hardware/gal/video.cpld.ts`](../hardware/gal/video.cpld.ts) and
`hardware/gal/cpld/`, with every design also checked against Atmel's own compiler by
`npm run check:cupl`. `graphics.md` §14.1 has the line-by-line count; the path the
count took to get there (~33 → 41 → 30 → 27 → 28, with power falling from ~1.2–1.8 A)
is archived in [`docs/history.md`](docs/history.md).

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

⚠ **`vaddr` is bound by pins and LAB fan-in; `vctrl`, since 2026-09-11, by cells.**
`vctrl` is 56 of 64 I/O.
`vaddr` is 59 of 64 I/O.
`vsup` is 61 of 64 I/O.
Their cell counts are 127, 113 and 91 of 128, and `vctrl`'s is the fitter's second pass
(`docs/graphics.md` §19 item 46). ⚠ All three are fitted with **JTAG off**
(`cpld/*.fit`: the four JTAG pins carry signals), so they are programmed out of circuit.

⛔ **And `vaddr` is bound by a third thing: LAB fan-in.** An `ATF1508AS` block sees 40
signals through the switch matrix and `vaddr` peaks at **35 of 40** (`cpld/vaddr.fit`). Three
separate one-literal changes to the display list were refused there on 2026-09-09 — two
`Grouping fail / Design does not fit`, one `INTERNAL ERROR` — which is why the engine's
descriptor half moved to `vsup` rather than growing in place. It is invisible in a cell
count and a pin count; only `hardware/gal/cpld/vaddr.fit` shows it.

**Nothing further can be added to `vctrl`.** §14.2's two ×16 framebuffer parts return six
output pins by making the arbiter 2 grants instead of 8 — already worth doing, and now
the thing the card's next feature waits on.

⚠ **`vsup`'s spare room is 44 macrocells and 6 pins**, which is the shape of every
constraint on this card: a blit datapath (`blitter.md`) fits the cells and does not fit
the pins. **Blitter room is a pin question here, not a macrocell question.**

**Specified at ÷12 only.** E = 25.175/12 = 2.0979 MHz is the rate this card is
specified at. The ÷8 rate — fast-E mode, 3.1469 MHz — is **experimental and not
guaranteed**, for two reasons elsewhere in the machine (`docs/machine.md` §1.1). VRAM
read-back is not one of them: it is prefetched at `WPTR` and has no in-cycle deadline
(§11).

`graphics.md` also carries the machine-level material the other cards depend on: the
one-oscillator clock tree (§5 — the oscillator is on the **motherboard**, not this
card), the MMU (§6.3, and §6.3.1 for where it landed and why it is **5 ICs**, not 3),
the `/IOPAGE` backplane signal without which a flat VRAM map is electrically unsafe
(§6.3.2), and the backplane signal list (§17). Those have been lifted into
[`../docs/machine.md`](../docs/machine.md).
