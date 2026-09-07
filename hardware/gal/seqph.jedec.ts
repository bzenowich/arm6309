/* The sequencer's timing spine: dot phase, slot tick, sub-slot split, the
 * four per-chip fetch-latch clocks, and the pixel mux select.
 *
 * 14 describes the sequencer pair as "decode (incl. the /IOPAGE term),
 * static slot assignment, span control, reg-file addressing, mux phasing" -
 * a list of responsibilities, not a design. Most of that list cannot be
 * fitted until the span writer's state machine is written down. This part
 * can: 5.2.2 specifies the sub-slot ordering and the fetch-latch clocking
 * exactly, 6.1 fixes the four-dot slot, and 8 fixes what HSCROLL[1:0] does.
 *
 * ONE THING IS DELIBERATELY NOT SCROLL-OFFSET. The dot phase here is
 * free-running and locked to the raster; HSCROLL does not touch it. Section
 * 8 says "HSCROLL[1:0] preloads the output phase", and if that were taken to
 * mean the slot counter, the fetch-slot grid - and with it HSYNC, which hgen
 * derives from the same tick - would slide with horizontal scroll. Only the
 * MUX SELECT carries the offset. seqph.check.ts asserts the separation.
 */

import { counterTerms } from "./jedec/counter"
import { place } from "./jedec/place"
import type { Cell, Design } from "./jedec/assemble"

const PH = ["PH0", "PH1"]

/* Free-running mod-4: no terminal count needed, two bits roll over on their
 * own. This is the 25.175 MHz dot phase, and every other clock on the card
 * is derived from it. */
const phase = counterTerms({ bits: PH })

/* The mux select is the phase plus HSCROLL[1:0], modulo 4 - a two-bit adder,
 * which as sum-of-products is an XOR and an XOR-with-carry. */
const MUXSEL0 = ["PH0 & !HS0", "!PH0 & HS0"]
/* PH1 XOR HS1 XOR (PH0 & HS0) - the carry makes it a three-input XOR, which
 * is six product terms once the carry is expanded. */
const MUXSEL1 = [
  "PH1 & !HS1 & !PH0", "PH1 & !HS1 & !HS0",
  "!PH1 & HS1 & !PH0", "!PH1 & HS1 & !HS0",
  "PH1 & HS1 & PH0 & HS0", "!PH1 & !HS1 & PH0 & HS0",
]

const cells: Cell[] = [
  ...PH.map((name, i) => ({
    pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
    terms: phase[i],
  })),

  /* The slot tick. hgen's slot counter and hadr's column counter both
   * advance on it, so it is the boundary of the 158.9 ns fetch slot and it
   * must not move with scroll. */
  {
    pin: 0, name: "SLOTTICK", assertedLow: false, s0: 1, registered: false,
    terms: ["PH1 & PH0"],
  },

  /* 5.2.2: the spare access occupies the FRONT half of the slot and the
   * display fetch the back half. Read plainly, 2.2's "video -> CPU -> ..."
   * priority implies video-first, which is the ordering that misses 11's
   * read deadline by 25 ns. This is the specification sentence, as one
   * product term: dots 0-1 are the spare window, dots 2-3 the fetch. */
  {
    pin: 0, name: "SPAREWIN", assertedLow: false, s0: 1, registered: false,
    why: "5.2.2 - spare first, which is +46.9 ns against video-first's -25.1",
    terms: ["!PH1"],
  },

  /* Four fetch-latch clocks, one per framebuffer chip, each rising at the
   * end of that chip's own fetch - 144 ns into a 158.9 ns slot, 14.9 ns of
   * settling before the boundary.
   *
   * IN REV A THESE FOUR ARE THE SAME EQUATION. They are four macrocells
   * because 5.2.2 requires them to be able to differ: 5.2.1 grants each
   * chip's spare access independently, 6.4's tile mode gives the chips
   * different fetch cadences - and, which 8 does not say and should,
   * byte-granular horizontal scroll needs them to differ too. See
   * seqph.check.ts, which shows a common address bus and a common latch
   * clock cannot produce a scrolled line at all. */
  ...[0, 1, 2, 3].map((n) => ({
    pin: 0, name: `FCLK${n}`, assertedLow: false, s0: 1 as const, registered: false,
    terms: ["PH1 & PH0"],
    why: n === 0 ? "four copies in Rev A; separate macrocells so they can diverge" : undefined,
  })),

  /* Which of the four latched bytes the '153 mux emits. This is the only
   * thing HSCROLL[1:0] touches. */
  { pin: 0, name: "MUXSEL0", assertedLow: false, s0: 1, registered: false, terms: MUXSEL0 },
  { pin: 0, name: "MUXSEL1", assertedLow: false, s0: 1, registered: false, terms: MUXSEL1 },
]

const pins = place(cells, [14, 15, 16, 17, 18, 19, 20, 21, 22, 23])

export const seqphDesign: Design = {
  name: "seqph",
  partNo: "ARM6309-UV9",
  location: "video card - sequencer, timing spine",
  signature: "A6309V9",
  clockPin: 1,
  inputs: [
    { name: "RESET", pin: 2, activeLow: true },
    { name: "HS0", pin: 3 }, { name: "HS1", pin: 4 },
  ],
  cells: cells.map((c) => ({ ...c, pin: pins[c.name] })),
  spares: [],
  ar: "RESET",
}
