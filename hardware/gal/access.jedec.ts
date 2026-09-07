/* The spare-access arbiter and the WPTR pointer pair.
 *
 * graphics.md 19 item 20 asks for the arbiter to be fitted and for its grant
 * logic to be confirmed on the three cases the wire could not do. Item 12 asks
 * for a decision on span-wrap behaviour at the 1024-byte row boundary, and it
 * turns out the fit makes that decision rather than merely recording it.
 */

import { counterTerms } from "./jedec/counter"
import { place } from "./jedec/place"
import type { Cell, Design } from "./jedec/assemble"

/* =====================================================================
 * arb - the spare-access arbiter, 5.2.1
 *
 * Phase locking fixes WHEN the CPU's access happens; it says nothing about
 * WHICH of the four chips it lands on, and not even whether it happens at
 * all. So the span writer may take a chip only after a live compare.
 * ===================================================================== */

const chipIs = (sig: string, n: number) =>
  `${n & 1 ? "" : "!"}${sig}0 & ${n & 2 ? "" : "!"}${sig}1`

/* 14 budgets this part as "8 grants + 4 source selects" = 12 outputs, which
 * is more than a 22V10 has and should have been an overflow. It is not one:
 * 5.2.1's own equations end with SRCSEL[n] = GRANT_CPU[n]. That is the same
 * signal, not a second one, so the part is 8 macrocells and the four SRCSEL
 * lines are the four GRANT_CPU pins under another name. */
const arbCells: Cell[] = []
for (let n = 0; n < 4; n++) {
  /* The CPU wants VRAM this cycle and this is its chip. VREQ is formed here
   * rather than taken in: VRAMSEL and /IOPAGE are both already on the card. */
  arbCells.push({
    pin: 0, name: `GCPU${n}`, assertedLow: false, s0: 1, registered: false,
    terms: [`VRAMSEL & !IOPAGE & ${chipIs("CPUA", n)}`],
    why: n === 0 ? "SRCSEL[n] is this same pin - 5.2.1, not a second macrocell" : undefined,
  })
  /* The span writer gets the chip if it wants it and the CPU has not taken
   * it. Expanding !GRANT_CPU[n] gives four ways for the CPU not to have it:
   * it is not selecting VRAM, it is in the I/O page, or either of its two
   * address bits differs from this chip. */
  arbCells.push({
    pin: 0, name: `GSPN${n}`, assertedLow: false, s0: 1, registered: false,
    terms: [
      `SPNREQ & ${chipIs("SPNA", n)} & !VRAMSEL`,
      `SPNREQ & ${chipIs("SPNA", n)} & IOPAGE`,
      `SPNREQ & ${chipIs("SPNA", n)} & ${n & 1 ? "!" : ""}CPUA0`,
      `SPNREQ & ${chipIs("SPNA", n)} & ${n & 2 ? "!" : ""}CPUA1`,
    ],
  })
}

const arbPins = place(arbCells, [14, 15, 16, 17, 18, 19, 20, 21])

export const arbDesign: Design = {
  name: "arb",
  partNo: "ARM6309-UV6",
  location: "video card - spare-access arbiter",
  signature: "A6309V6",

  inputs: [
    { name: "VRAMSEL", pin: 1 },
    { name: "IOPAGE", pin: 2, activeLow: true },
    { name: "CPUA0", pin: 3 }, { name: "CPUA1", pin: 4 },
    { name: "SPNREQ", pin: 5 },
    { name: "SPNA0", pin: 6 }, { name: "SPNA1", pin: 7 },
  ],
  cells: arbCells.map((c) => ({ ...c, pin: arbPins[c.name] })),
  /* Two macrocells and five input pins spare. If the '153 and address-mux
   * loads want SRCSEL driven separately from GRANT_CPU, a duplicate costs one
   * product term and there is room for two of them. */
  spares: [22, 23],
}

/* =====================================================================
 * wcol / wrow - WPTR, the write and read pointer, 13 and 11
 *
 * Nineteen bits, and the same {row, column} structure as the scan address
 * because the stride is the same 1024: A9..A0 is the column within the row
 * and A18..A10 is the row on the ring.
 *
 * ITEM 12 IS DECIDED BY THE FIT, not by taste. A linear write that runs off
 * column 1023 either wraps to column 0 of the same row or advances into the
 * next row. Advancing needs a carry out of the column part, and the column
 * part is ten bits in ten macrocells with nothing left to emit one from -
 * see access.check.ts, which asserts that there is no eleventh macrocell.
 *
 * Wrapping is also the answer that matches the rest of the machine: hadr's
 * column counter wraps inside the row (scan.check.ts proves it), so a span
 * that advanced would disagree with the scanner about what follows column
 * 1023 on the same row. The torus is a torus in both directions or in
 * neither.
 * ===================================================================== */

const WCOL = ["A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9"]
const WROW = ["A10", "A11", "A12", "A13", "A14", "A15", "A16", "A17", "A18"]

/* The column takes WPTR bytes 0 and 1: D7..D0 -> A7..A0, then D1..D0 ->
 * A9..A8. One strobe per byte, decoded by the sequencer. */
/* A bit holds through every strobe EXCEPT the one that loads it. Gating the
 * hold on both strobes is wrong and is not subtle: writing byte 1 would then
 * clear bits 7..0, so the CPU could never write a pointer above 255 without
 * the low byte being destroyed by the next write. */
const wcolTerms = WCOL.map((_, i) => {
  const counted = counterTerms({ bits: WCOL, enable: "WINC" })[i]
  const mine = i < 8 ? "LDA" : "LDB"
  const load = i < 8 ? `LDA & D${i}` : `LDB & D${i - 8}`
  return [load, ...counted.map((t) => `!${mine} & ${t}`)]
})
const wcolCells: Cell[] = WCOL.map((name, i) => ({
  pin: 0, name, assertedLow: false, s0: 1, registered: true, terms: wcolTerms[i],
}))
const wcolPins = place(wcolCells, [14, 15, 16, 17, 18, 19, 20, 21, 22, 23])

export const wcolDesign: Design = {
  name: "wcol",
  partNo: "ARM6309-UV7",
  location: "video card - WPTR column",
  signature: "A6309V7",
  clockPin: 1,
  inputs: [
    { name: "D0", pin: 2 }, { name: "D1", pin: 3 }, { name: "D2", pin: 4 },
    { name: "D3", pin: 5 }, { name: "D4", pin: 6 }, { name: "D5", pin: 7 },
    { name: "D6", pin: 8 }, { name: "D7", pin: 9 },
    { name: "LDA", pin: 10 }, { name: "LDB", pin: 11 },
    /* One byte written, or one span byte retired. */
    { name: "WINC", pin: 13 },
  ],
  cells: wcolCells.map((c) => ({ ...c, pin: wcolPins[c.name] })),
  /* Ten macrocells and eleven input pins: every one of both is used, and
   * that is the whole of item 12's answer. */
  spares: [],
}

/* The row takes the top of byte 1 and the bottom of byte 2: D7..D2 ->
 * A15..A10, then D2..D0 -> A18..A16. WROW is the sequencer's advance - one
 * pulse for WADV = 01 ("next row, same column", 7.2, where the column is
 * reloaded from the register-file shadow through LDA/LDB) and for WADV = 10
 * (vertical, advance by the 1024 stride). */
const wrowTerms = WROW.map((_, i) => {
  const counted = counterTerms({ bits: WROW, enable: "WROWADV" })[i]
  const mine = i < 6 ? "LDB" : "LDC"
  const load = i < 6 ? `LDB & D${i + 2}` : `LDC & D${i - 6}`
  return [load, ...counted.map((t) => `!${mine} & ${t}`)]
})
const wrowCells: Cell[] = WROW.map((name, i) => ({
  pin: 0, name, assertedLow: false, s0: 1, registered: true, terms: wrowTerms[i],
}))
const wrowPins = place(wrowCells, [14, 15, 16, 17, 18, 19, 20, 21, 22])

export const wrowDesign: Design = {
  name: "wrow",
  partNo: "ARM6309-UV8",
  location: "video card - WPTR row",
  signature: "A6309V8",
  clockPin: 1,
  inputs: [
    { name: "D0", pin: 2 }, { name: "D1", pin: 3 }, { name: "D2", pin: 4 },
    { name: "D3", pin: 5 }, { name: "D4", pin: 6 }, { name: "D5", pin: 7 },
    { name: "D6", pin: 8 }, { name: "D7", pin: 9 },
    { name: "LDB", pin: 10 }, { name: "LDC", pin: 11 },
    { name: "WROWADV", pin: 13 },
  ],
  cells: wrowCells.map((c) => ({ ...c, pin: wrowPins[c.name] })),
  spares: [23],
}
