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

  /* The slot tick. hgen's slot counter and hadr's column counter both advance
   * on it, so it is the boundary of the 158.9 ns fetch slot and it must not
   * move with scroll.
   *
   * ⭐ IT IS DOT 0, AND THAT IS A DECISION AS OF 2026-09-09 - it reached this
   * value by accident (an unguarded whole-file replace while 8.2's FCLK was
   * being rewritten caught `PH1 & PH0` here too) and it is kept on the merits.
   *
   * ⚠ IT WAS `PH1 & PH0` - dot 3 - AND DOT 3 DOES NOT WORK. Put back and
   * measured: vaddr_tb's pixel check reported 636 OF 640 PIXELS WRONG at
   * HSCROLL 0 and 159 of 160 tile addresses wrong in vtile_tb. The reason is
   * ordering. SLOTTICK is a counter ENABLE, so a counter advances on the edge
   * that ENDS the dot it is high in:
   *
   *   dot 0   the scan column advances at the PH 0 -> 1 boundary, one dot
   *           AFTER the fetch latches clock, so the address the memory was
   *           presenting is safely captured before it moves
   *   dot 3   it advances on the PH 3 -> 0 boundary, which is the SAME edge
   *           FCLK rises on - the address moves under the latch
   *
   * The old per-chip FCLK scheme (19 item 23(a), deleted with 8.2) hid that by
   * clocking two of the four chips a dot later. With one clock for all four
   * there is nothing left to hide it, and dot 0 is the phase that orders the
   * two edges correctly.
   *
   * ⚠ AND IT IS ALSO WHY vsync_tb HUNG. Its frame-start wait read
   * `SLOTTICK == 0 && PH == 0`, which named the first dot of a slot while the
   * tick was at dot 3 and is UNSATISFIABLE now. A `forever` with no bound is a
   * hang and not a failure: run.sh's exit code cannot see it and neither can
   * the claim count. The condition is `PH == 0` alone. */
  {
    pin: 0, name: "SLOTTICK", assertedLow: false, s0: 1, registered: false,
    terms: ["!PH1 & !PH0"],
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
  /* ⛔ ONE CLOCK, NOT FOUR EQUATIONS - 2026-09-09, and 19 item 23(a)'s
   * per-chip early/late scheme is deleted with it.
   *
   * 23(a) tried to make one latch rank hold two groups by clocking chips
   * `p..3` at the PH 2->3 boundary and `0..p-1` at PH 3->0, "so a chip clocked
   * LATE holds exactly one group more than a chip clocked EARLY". 19 item 28
   * is the arithmetic that says it cannot work - a latch clocked once per slot
   * always holds the most recent fetch, whichever edge you pick - and 8.2 is
   * what does work: a SECOND RANK in series, selected per chip by an output
   * enable. With the rank select carrying the group choice there is nothing
   * left for the clock phase to carry, and HS0/HS1 leave this equation
   * entirely.
   *
   * ⚠ AND THE OLD SCHEME WAS ACTIVELY WRONG ONCE THE RANKS EXISTED. vaddr_tb's
   * pixel check reported chip 3 alone wrong at HSCROLL[1:0] = 0 - it was the
   * one chip the p-dependent phase still moved. Nine product terms across four
   * macrocells, deleted; the four clocks are now the same signal.
   *
   * 5.2.2 puts the edge at the PH 3 -> 0 boundary: after this slot's fetch has
   * landed on the pixel bus, and after the phase-3 pixel has been emitted from
   * the OLD contents. Clocking a dot earlier - inside PH 3 - makes the chip
   * displayed at phase 3 read this slot's fetch instead of last slot's, which
   * vaddr_tb reports as exactly one pixel in four wrong at every scroll value. */
  ...[0, 1, 2, 3].map((n) => ({
    pin: 0, name: `FCLK${n}`, assertedLow: false, s0: 1 as const, registered: false,
    terms: ["!PH1 & !PH0"],
    why: n === 0 ? "one clock for all four chips - 8.2's rank select carries the group choice" : undefined,
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
