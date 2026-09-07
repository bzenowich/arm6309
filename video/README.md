# `video/` — the 256-colour video card

640×200 in **256 colours**, 80×25 text, a scrolling bitmap and a span writer, out of a
VGA connector at the standard 25.175 MHz dot clock. **41 ICs** — 37 if the tri-state
pixel bus closes at 39.7 ns and the `'153` mux is not needed — of which **10 are
GAL22V10**, plus a three-transistor analog drive stage. No CPLDs, no FPGAs.
**~1.2–1.8 A at 5 V.**

The sync GALs are written, fitted and checked at the fuse level —
[`hardware/gal/sync.jedec.ts`](../hardware/gal/sync.jedec.ts), `npm run check:sync`.
That is what moved the count from 40/9: the sync section needs three parts, not two.

> ⚠ **The count and the power figure both moved.** This file, `docs/graphics.md` §0
> and `docs/machine.md` previously said ~~"~33 ICs"~~ against a §14 table that summed
> to 36; the honest number is 40 once the posted-write **address** latches (§3.1.1),
> the spare-access arbiter (§5.2.1), the `VSTAT` driver (§12.1) and the analog buffer
> stage (§9.1) are counted, and the 25.175 MHz master oscillator is moved to the
> motherboard where it belongs (§5.1). Power was stated as ~~450–650 mA~~, which was
> less than nine GALs alone. See `docs/graphics.md` §14 for the line-by-line
> arithmetic.

Paths below are relative to this directory; build commands run from the repository
root.

| | |
|---|---|
| [`docs/graphics.md`](docs/graphics.md) | the card: what carries over from `colormin`'s 256-colour design and what has to change for a 6309 machine |

Two companion documents live at machine level rather than here, because they are
comparisons rather than specification:

- [`../docs/video-comparison.md`](../docs/video-comparison.md) — this card against the
  GIME and the VIC-II
- [`../docs/coco3_c64.md`](../docs/coco3_c64.md) — GIME vs VIC-II, from a
  CPU-replacement's point of view

## Status

**Specified, nothing built.** There is no code here and no `CMakeLists.txt`; the card is
discrete logic and the deliverable is the document.

`docs/graphics.md` §18 gives the build order. Steps 1 and 2 — bench the dot path on a
breadboard **including the analog drive stage**, then fit the sync and scan-address
GALs — **come before laying out anything**, because they contain the design's real
unknowns. §19 item 8 now carries the macrocell arithmetic for both GAL pairs, and
neither has margin: the scan-address pair is 20 of 20 committed before tile mode, and
the sync pair wants 24 of 20 once blanking, status and the mode-dependent sync
polarity (§6.2.1) are counted.

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
