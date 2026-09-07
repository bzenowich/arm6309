/* The span writer's control state machine, respecified for 8 x 8 cells.
 *
 * graphics.md 14 lists "span control" among the sequencer pair's duties and
 * nothing in that document says what it is - the mechanism is inherited from
 * minimal256, which was designed around 6-pixel cells. 6.1 already says what
 * changes at 8 x 8 and stops short of the consequence:
 *
 *   "colormin's span-mask serialises a byte and stops at SPANLEN; with 6-px
 *    cells two bits per write are wasted. At 8x8 the mask byte IS the glyph
 *    row."
 *
 * THE CONSEQUENCE IS THAT SPAN-MASK MODE DOES NOT CONSULT SPANLEN AT ALL.
 * Its length is eight, always, because eight is the cell width; the byte the
 * CPU writes is exactly one glyph row and there is nothing to truncate. So
 * the length comes from a three-bit counter here - three bits because a cell
 * is eight wide - and the '161 pair's SPANLEN belongs to span-solid alone.
 *
 * That is what makes 7.3's "13 writes per character cell" arithmetic true:
 * WPTR (3) + WFG + WBG = 5 of setup, then 8 glyph rows. SPANLEN is not among
 * them. Had mask mode needed SPANLEN it would be 14, and the text engine's
 * headline number is 7 % worse.
 *
 * Everything else is one uniform per-byte handshake:
 *
 *   WSTB          a posted write has been latched (3.1.1's '574s hold the
 *                 address, the data, R/W and WMODE) - start a span
 *   SPNGRANT      the arbiter matched WPTR[1:0] against the CPU's chip and
 *                 gave the span writer a spare access (5.2.1)
 *   RETIRE        one byte goes to VRAM. Drives WPTR's WINC, the '165's
 *                 shift and the '161's count - one signal, three loads
 *   SPANEND       the last byte of the span retired
 *
 * and the mask bit itself never enters this part: the '165's serial output
 * is wired to the register file's address bit 0, which is why 13 requires
 * WFG at A0 = 0 and WBG at A0 = 1. Choosing the source colour costs no
 * macrocell and no product term - it is an address line.
 */

import { counterTerms } from "./jedec/counter"
import { place } from "./jedec/place"
import type { Cell, Design } from "./jedec/assemble"

/* WMODE[1:0], 13: 00 direct, 01 span-mask, 10 span-solid. */
const DIRECT = "!WM1 & !WM0"
const MASK = "!WM1 & WM0"
const SOLID = "WM1 & !WM0"

const MC = ["MC0", "MC1", "MC2"]
/* Zeroed at the start of every span, counting one per retired byte. Three
 * bits is the cell width and nothing else. */
const mcTerms = counterTerms({ bits: MC, enable: "RETIRE" })
  .map((bit) => bit.map((t) => `!WSTB & ${t}`))

const cells: Cell[] = [
  /* A span is in flight from the posted write until its last byte retires.
   * This is VSTAT bit 7 and it is the /WAIT condition on the arbiter. */
  {
    pin: 0, name: "SPANBUSY", assertedLow: false, s0: 1, registered: true,
    terms: ["WSTB", "SPANBUSY & !SPANEND"],
  },

  /* The arbiter has already matched the chip, so a grant while busy is
   * simply "go". One output drives WPTR's column increment, the '165's
   * shift clock and the '161's count enable: the three things that advance
   * together by construction. */
  {
    pin: 0, name: "RETIRE", assertedLow: false, s0: 1, registered: false,
    why: "also WPTR.WINC, the '165 shift and the '161 count enable",
    terms: ["SPANBUSY & SPNGRANT"],
  },

  ...MC.map((name, i) => ({
    pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
    terms: mcTerms[i],
  })),

  /* Where the three modes differ, and the only place they do.
   *
   * Direct is one byte - 3.1.1's posted write, retired into the first free
   * slot. Mask is eight, counted here. Solid is SPANLEN + 1, counted by the
   * '161 pair, whose terminal count arrives as TC.
   *
   * Loading the '161 in mask mode is harmless and is why WSTB can drive both
   * the '165's load and the '161's load with no mode qualification: mask
   * mode terminates on MC and never looks at TC. */
  {
    pin: 0, name: "SPANEND", assertedLow: false, s0: 1, registered: false,
    terms: [
      `RETIRE & ${DIRECT}`,
      `RETIRE & ${MASK} & MC2 & MC1 & MC0`,
      `RETIRE & ${SOLID} & TC`,
    ],
  },

  /* 13's WADV: 00 continue, 01 next row same column, 10 vertical. Both
   * non-zero modes advance WPTR's row at the end of the span; 01 also
   * reloads the column from 7.2's register-file shadow, which is the other
   * sequencer part's business because it drives the register-file address. */
  {
    pin: 0, name: "WROWADV", assertedLow: false, s0: 1, registered: false,
    terms: ["SPANEND & WADV0", "SPANEND & WADV1"],
  },
]

/* Seven macrocells; the widest equation is four product terms. Placed on the
 * leanest seven so the three 16-term macrocells stay free - this part has the
 * most headroom on the card and the sequencer's other half has none. */
const pins = place(cells, [14, 15, 16, 17, 20, 22, 23])

export const seqctlDesign: Design = {
  name: "seqctl",
  partNo: "ARM6309-UV10",
  location: "video card - span writer control",
  signature: "A6309VA",
  supersededBy: "graphics.md 10.1.6 - the video card is 2 x ATF1508AS",
  clockPin: 1,
  inputs: [
    { name: "RESET", pin: 2, activeLow: true },
    /* One pulse per posted write, from the E-fall latch of 3.1.1. */
    { name: "WSTB", pin: 3 },
    { name: "WM0", pin: 4 }, { name: "WM1", pin: 5 },
    { name: "SPNGRANT", pin: 6 },
    /* The '161 pair's terminal count - span-solid's length. */
    { name: "TC", pin: 7 },
    { name: "WADV0", pin: 8 }, { name: "WADV1", pin: 9 },
  ],
  cells: cells.map((c) => ({ ...c, pin: pins[c.name] })),
  spares: [18, 19, 21],
  ar: "RESET",
}
