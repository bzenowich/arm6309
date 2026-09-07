/* The video card's scan-address generators - graphics.md 19 item 8's other
 * half, which says the pair is "20 of 20, zero margin" and item 15 leans on
 * that to conclude tile mode needs a third package.
 *
 * IT IS 17 OF 20, and the document already contains the numbers that say so.
 * Item 8 counts "19-bit loadable scan address, A18..A0" as 19 macrocells plus
 * a carry. Section 8 describes the same hardware differently and correctly:
 *
 *   "a separate 9-bit V-address counter supplies row bits A18..A10"
 *   "HSCROLL[9:2] preloads the H-address counter"
 *   "HSCROLL[1:0] preloads the output phase - which of the four interleaved
 *    bytes emits first"
 *
 * A1 and A0 are not address bits. The framebuffer is four 128K x 8 parts in
 * 4-way interleave (2.1), so a chip's address IS the scan address shifted
 * down two, and the bottom two bits are which chip - the mux phase, which
 * never leaves the '153s. 128K x 8 has seventeen address pins and seventeen
 * is what has to be generated.
 *
 * There is also no inter-package carry to count. The torus is 1024 x 512
 * (section 8), the row stride is exactly 1024 and the ring is exactly 512
 * rows, so the column counter wraps mod 256 at A9 and the row counter wraps
 * mod 512 at A18 - both are free binary rollovers of their own width and
 * neither ever carries into the other. Item 8's "inter-package carry /
 * terminal count" macrocell is a cost of a 19-bit flat counter that this
 * design does not build.
 *
 *   9 + 8 = 17 macrocells of 20, three spare, and the split falls on the
 *   package boundary for free because the two counters are independent.
 */

import { counterTerms } from "./jedec/counter"
import type { Design } from "./jedec/assemble"

/* A loadable counter: load wins, then count if enabled, else hold. The
 * generator gives the count-or-hold half; the load is one term per bit and
 * has to qualify the other two. */
const loadable = (
  bits: string[], enable: string, load: string, from: string[],
): string[][] => {
  const counted = counterTerms({ bits, enable })
  return bits.map((_, i) => [
    `${load} & ${from[i]}`,
    ...counted[i].map((t) => `!${load} & ${t}`),
  ])
}

/* =====================================================================
 * hadr - the column address, A9..A2
 * ===================================================================== */

const HA = ["A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9"]
const HS = ["HS2", "HS3", "HS4", "HS5", "HS6", "HS7", "HS8", "HS9"]

export const hadrDesign: Design = {
  name: "hadr",
  partNo: "ARM6309-UV4",
  location: "video card - column scan address",
  signature: "A6309V4",
  supersededBy: "graphics.md 10.1.6 - the video card is 2 x ATF1508AS",
  clockPin: 1,

  inputs: [
    /* One fetch slot in four dots, and only inside the fetch window: the
     * column must not advance through the porches. */
    { name: "FETCH", pin: 2 },
    { name: "RESET", pin: 3, activeLow: true },
    /* Asserted through horizontal blanking, from the sequencer pair.
     * HSCROLL[9:2] arrives on the register-file data path. */
    { name: "HLOAD", pin: 4 },
    { name: "HS2", pin: 5 }, { name: "HS3", pin: 6 }, { name: "HS4", pin: 7 },
    { name: "HS5", pin: 8 }, { name: "HS6", pin: 9 }, { name: "HS7", pin: 10 },
    { name: "HS8", pin: 11 }, { name: "HS9", pin: 13 },
  ],

  /* No terminal count. The torus is 1024 columns wide and this counter is
   * eight bits of a 1024-column row taken two at a time, so rolling over at
   * 256 IS the wrap to column 0 of the same row. Section 8's "the 384
   * off-screen columns are not waste" depends on exactly this. */
  cells: HA.map((name, i) => ({
    pin: 14 + i, name, assertedLow: false, s0: 1 as const, registered: true,
    terms: loadable(HA, "FETCH", "HLOAD", HS)[i],
  })),

  /* Two macrocells spare, and eight of eleven input pins used. */
  spares: [22, 23],
  ar: "RESET",
}

/* =====================================================================
 * vadr - the row address, A18..A10
 * ===================================================================== */

const VA = ["A10", "A11", "A12", "A13", "A14", "A15", "A16", "A17", "A18"]
const VS = ["VS0", "VS1", "VS2", "VS3", "VS4", "VS5", "VS6", "VS7", "VS8"]

export const vadrDesign: Design = {
  name: "vadr",
  partNo: "ARM6309-UV5",
  location: "video card - row scan address",
  signature: "A6309V5",
  supersededBy: "graphics.md 10.1.6 - the video card is 2 x ATF1508AS",
  clockPin: 1,

  inputs: [
    /* One pulse at the end of each displayed line. In the line-doubled modes
     * the sequencer withholds every second one, which is the whole of
     * line-doubling: 6.2's "line-doubling fetches every row twice". */
    { name: "ROWADV", pin: 2 },
    { name: "RESET", pin: 3, activeLow: true },
    /* Asserted through vertical blanking. VSCROLL is nine bits across
     * VSCROLL and VSCROLLH (section 13). */
    { name: "VLOAD", pin: 4 },
    { name: "VS0", pin: 5 }, { name: "VS1", pin: 6 }, { name: "VS2", pin: 7 },
    { name: "VS3", pin: 8 }, { name: "VS4", pin: 9 }, { name: "VS5", pin: 10 },
    { name: "VS6", pin: 11 }, { name: "VS7", pin: 13 },
    /* The ninth bit lands on the one free macrocell pin. */
    { name: "VS8", pin: 23 },
  ],

  /* Nine bits, rolling over at 512, which is the ring. A row past the end of
   * the ring is row 0 - that is what makes VSCROLL += 1 per frame smooth and
   * what makes the double-buffer flip of section 8 one register write.
   *
   * PIN ORDER IS NOT BIT ORDER, for the same reason it is not on vgen: a
   * loadable bit i costs i + 3 product terms, so the nine bits need 3..11
   * and the eight remaining macrocells offer 8,10,12,14,16,16,14,12,10.
   * Placing them in bit order puts the 11-term top bit on a 10-term
   * macrocell, which is what the fitter refused. */
  cells: VA.map((name, i) => ({
    pin: [14, 15, 22, 16, 21, 17, 20, 18, 19][i],
    name, assertedLow: false, s0: 1 as const, registered: true,
    terms: loadable(VA, "ROWADV", "VLOAD", VS)[i],
  })),

  spares: [],
  ar: "RESET",
}
