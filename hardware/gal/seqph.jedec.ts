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
import { minimalSop } from "./jedec/twolevel"

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

  /* Four fetch-latch clocks, one per framebuffer chip - 19 item 23(a), and
   * no longer four copies of one term.
   *
   * 8's scroll and 5.2.2's per-chip clocking describe one mechanism from
   * opposite ends. Here is where they meet. With HSCROLL[1:0] = p the mux
   * emits chips p, p+1, p+2, p+3 in that order, so chips p..3 are emitted
   * FIRST and want the current group, and chips 0..p-1 are emitted after the
   * wrap and want the NEXT one. Two groups have to be live in the latches at
   * once, and the latches are the only place to keep them.
   *
   * The two groups come from ONE address bus and one fetch per slot, because
   * the '574s can be clocked on either side of the moment the fetched data
   * lands. The fetch occupies the back half of the slot (SPAREWIN above), so:
   *
   *   EARLY  rises at the PH 2->3 boundary, 119.1 ns in, BEFORE this slot's
   *          fetch has landed - the chip keeps the previous group
   *   LATE   rises at the PH 3->0 boundary, 158.9 ns in, after it has - the
   *          chip takes the new one
   *
   * so a chip clocked LATE holds exactly one group more than a chip clocked
   * EARLY, which is the whole of what 8 needs. EARLY is the Rev A equation
   * unchanged, which is why p = 0 still works and why nothing else on the
   * card moves.
   *
   * Nine product terms across four macrocells that were already budgeted, and
   * seqph.check.ts now computes the emitted byte sequence for every p and
   * asserts it is right - where before it could only assert it was wrong. */
  ...[0, 1, 2, 3].map((n) => {
    /* chip n is emitted before the wrap exactly when n >= p */
    const early: string[] = [], late: string[] = []
    for (let p = 0; p < 4; p++) {
      const q = `${p & 1 ? "" : "!"}HS0 & ${p & 2 ? "" : "!"}HS1`
      ;(n >= p ? early : late).push(q)
    }
    const guard = (ts: string[], edge: string) => ts.map((t) => `${edge} & ${t}`)
    return {
      pin: 0, name: `FCLK${n}`, assertedLow: false, s0: 1 as const, registered: false,
      /* Enumerated over p and then minimised, because enumerating is the only
       * way to write this that is obviously right and it produces exactly the
       * A&B # A&!B shape jedec/minimise.ts cannot reduce. FCLK3 comes out as
       * one term, which is the arithmetic saying chip 3 is never after the
       * wrap. */
      terms: minimalSop([...guard(early, "PH1 & PH0"), ...guard(late, "!PH1 & !PH0")]),
      why: n === 3 ? "chip 3 is never after the wrap, so it is EARLY for every p" : undefined,
    }
  }),

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
  supersededBy: "graphics.md 10.1.6 - the video card is 2 x ATF1508AS",
  clockPin: 1,
  inputs: [
    { name: "RESET", pin: 2, activeLow: true },
    { name: "HS0", pin: 3 }, { name: "HS1", pin: 4 },
  ],
  cells: cells.map((c) => ({ ...c, pin: pins[c.name] })),
  spares: [],
  ar: "RESET",
}
