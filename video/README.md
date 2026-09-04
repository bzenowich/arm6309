# `video/` — the 256-colour video card

640×200 in **256 colours**, 80×25 text, a scrolling bitmap and a span writer, out of a
VGA connector at the standard 25.175 MHz dot clock. ~33 ICs, no CPLDs, no FPGAs.

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
breadboard, then fit the sync and scan-address GALs — **come before laying out
anything**, because they contain both of the design's real unknowns.

`graphics.md` also carries the machine-level material the other cards depend on: the
one-oscillator clock tree (§5), the MMU (§6.3, and §6.3.1 for where it landed), and the backplane
signal list (§17). Those have been lifted into [`../docs/machine.md`](../docs/machine.md).
