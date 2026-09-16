# `video3/` — a console-first video card

**DRAFT.** [`docs/plan.md`](docs/plan.md) is the specification. Nothing here is
fitted, placed, simulated or costed; §14 of the plan lists what would refute each
load-bearing claim and §15 is the order the work would have to be done in.

⛔ **video3 has no partition yet, and no utilisation figure from `video/`'s fit applies
to it.** Mechanism and timing arithmetic transfer; cell counts, fan-in and "which part
has room" do not — plan §14 item 4.

| | |
|---|---|
| **Character mode** | 80×25 / 30 / 50 / 60, **per-cell colour** — 16-colour ANSI with CP437, or 256 (fg, bg) pairs from 65,536 |
| **Bitmap mode** | 640×200 / 240 / 400 / 480 chunky 8bpp, the span writer, **full copyrect** |
| **Tile mode** | 8×8 8bpp tiles, as `video/docs/graphics.md` §6.4.2 |
| **One 8×8 sprite** | the mouse pointer, bitmap mode only |
| **Scrolling** | `VSCROLL` and `HSCROLL`, byte-granular, **bitmap and tile only** — character mode scrolls by copying (plan §8.2), so it has no ring and no runway defect |
| ⛔ **No display list** | and so nothing per-scanline: no raster bars, no sine warp, no `SS.Raster` |

**The one idea the card turns on:** the palette LUT is `64K×16` and `video/` writes
256 words of it. video3 drives its **high eight address lines** from an attribute —
the cell's in character mode, the sprite's in bitmap mode — so per-cell colour and a
hardware cursor both arrive **without a glyph serialiser and without a mux in the
index → LUT → output chain**, which is what `graphics.md` §6.4.6 and `features.md` §8
refuse. ⚠ That claim is §14 item 1 and it is not yet analysed.

**Related documents**

| | |
|---|---|
| [`docs/signals.md`](docs/signals.md) | the control lines and their inputs — the census a partition needs |
| [`../video/docs/graphics.md`](../video/docs/graphics.md) | the fitted card video3 borrows from, component by component (plan §11) |
| [`../docs/video-options.md`](../docs/video-options.md) | how `video/`, `video2/` and the VIC-II derivative compare |
| [`../docs/video-copyrect.md`](../docs/video-copyrect.md) | where the copy engine's rates and the no-adder argument were worked out |
| [`../software/nitros9/docs/video-compat.md`](../software/nitros9/docs/video-compat.md) | the requirement — what NitrOS-9 and ANSI art need and `video/` cannot give |
