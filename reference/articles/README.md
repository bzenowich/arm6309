# `reference/articles/`

Prior art and design history — writing rather than specification. **Not in git** — see
[`../README.md`](../README.md).

| File | What | Cited by |
|---|---|---|
| `folklore-apple2-mouse-card.pdf` | Andy Hertzfeld, *Apple II Mouse Card*, folklore.org, June 1981. Burrell Smith's two-chip mouse interface: a 6522 VIA and a dual flip-flop, where the Apple II division later shipped "more than a dozen" chips. | `io/ps2/docs/ps2.md` §4.4 — the interrupt argument, the derive-it-from-the-bus habit, and §4.4(c)'s rejection of interrupt-per-notch |
| `gal.html` + `gal_files/` | Frank DeCaire, *Generic Array Logic Devices*, January 2017. Reverse-engineers the GAL16V8 JEDEC fuse map by hand, having failed to find a PALASM in any language but FORTRAN, and programs a part from it. | `hardware/gal/jedec/README.md` — the fuse-polarity convention (`0` is an intact link), and the demonstration that hand-writing a fuse map is ordinary rather than exotic |

| `VIC-Article.txt` | Christian Bauer, *The MOS 6567/6569 video controller (VIC-II) and its application in the Commodore 64*, 2024-09-29. The canonical VIC-II reference: the block diagram, all 47 registers, the four access types (`c`/`g`/`p`/`s`), Bad Lines, the VC/VCBASE/RC/VMLI counter model, sprite DMA, priority and collision, and the raster geometry of all three chip types. | [`docs/video-options.md`](../../docs/video-options.md) §1 and §5 — the fetch-rate ladder, the line-buffer argument, and which recalled VIC-II figures it settled |

Originals at <https://www.folklore.org/Apple_II_Mouse_Card.html>,
<https://www.decaire.net/2017/01/22/generic-array-logic-devices/> and
<https://www.cebix.net>.

**What cites it, and for what.** [`docs/video-options.md`](../../docs/video-options.md)
compares three video designs for one slot, the third being a sprite-less RGB332 VIC-II
derivative extended to 80 columns. It leans on this article for the pixel clock and the
977.5 ns cell time, the per-revision raster geometry, the four access types, the
VC/VCBASE/RC/VMLI counter model, and §3.5's reason for the 40×12-bit line buffer —
which is bandwidth (40 c-accesses plus 40 g-accesses against 63–65 cycles), not the
CPU-cycle argument that comparison first gave.

**On its evidential standing, because it is not the same kind of source as the other
two.** It is a technical reference rather than a narrative, and far more precise —
cycle-by-cycle access diagrams, exact counter widths, per-revision raster geometry.
But §1 says plainly that **no schematics of the VIC are available**, that the internal
model is inferred from black-box testing, and that where several models fit the
observations "a descriptive model has been chosen that explains the observed phenomena
with the minimally required circuitry". So it is strong evidence for *timing,
geometry and observable behaviour*, and weaker evidence for *internal structure* —
the VC/VCBASE pair is the arrangement that fits, not the one anybody has seen on a
die. ⛔ **It carries no die-area, chip-area or transistor-count data of any kind**, so
the common claim that the sprite engine is the VIC's largest block by area is not
supported here. What the block diagram does show is that of the sixteen functional
blocks it draws, **three are wholly sprite-specific** — the 8×24-bit sprite data
buffers, the `MC0`–`MC7` counters and the sprite data sequencer — and a fourth, the
priority and collision MUX, exists mostly for them. That is a count of blocks on a
diagram, not of area on a die, and the two are not the same claim.

**The GAL article is about the 16V8, and this machine's parts are 22V10s.** Nearly
everything specific in it — `SYN`, `AC0`, `AC1`, the `PTD` fuses, "simple mode" — is
16V8 OLMC plumbing that the 22V10 does not have; the 22V10 has two config bits per
macrocell and no mode word. What transfers is the method, the fuse polarity, and the
warning about how long it takes to get right by trial and error.

**These are narratives, not schematics.** `ps2.md` §1 grades this one accordingly: a
first-hand account by someone who wrote the driver, which is strong evidence for *why* a
design was shaped a certain way and weak evidence for any specific pin.
