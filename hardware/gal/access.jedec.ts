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

/* One grant line back to the span writer instead of four. The sequencer only
 * ever needs to know THAT it was granted, not which chip - the arbiter has
 * already matched the chip against WPTR[1:0] to decide. Four pins saved on
 * seqctl for one macrocell here, on a part that had two spare.
 *
 * SIX TERMS, AND IT WAS SIXTEEN. Writing it as "the four per-chip grants,
 * ORed" enumerated the chip four ways and then expanded !GRANT_CPU four ways
 * inside each, and sixteen is what an OR of sixteen products costs. The chip
 * enumeration cancels: the span writer is refused exactly when the CPU wants
 * THE SAME chip, so the condition is a comparison between SPNA and CPUA and
 * not a decode of either. That is one term per address bit per direction, plus
 * the two ways the CPU is not asking at all.
 *
 * Found by minimising it - jedec/twolevel.ts, 2026-09-07 - after the ATF1508
 * fit showed the equation cascading across four macrocells on vctrl. The
 * complement is smaller still at five terms, which the 22V10's S1 bit would
 * give for nothing; it is not taken because SPNGRANT is read by name on two
 * other parts and inverting it there would cost more than it saves.
 *
 * access.check.ts compares this against the four grants ORed over every input
 * combination, so the rewrite is checked rather than argued. */
arbCells.push({
  pin: 0, name: "SPNGRANT", assertedLow: false, s0: 1, registered: false,
  terms: [
    /* the CPU's chip differs from ours in one address bit or the other */
    "SPNREQ & !SPNA0 & CPUA0",
    "SPNREQ & SPNA0 & !CPUA0",
    "SPNREQ & !SPNA1 & CPUA1",
    "SPNREQ & SPNA1 & !CPUA1",
    /* or the CPU is not after VRAM this cycle at all */
    "SPNREQ & !VRAMSEL",
    "SPNREQ & IOPAGE",
  ],
})

/* 3.3 and 12.1's open-drain idiom: the pin drives low or floats, and the
 * condition rides on the single output-enable product term. This lands here
 * rather than on the sequencer because the arbiter already has VRAMSEL and
 * /IOPAGE on its pins and had the macrocell to spare - see 10.1.1. */
arbCells.push({
  pin: 0, name: "WAIT", assertedLow: true, s0: 1, registered: false,
  why: "open-drain by the OE idiom - SPANBUSY . VRAMSEL . /IOPAGE . E",
  terms: [],
  /* NOTHING LISTENED TO THIS UNTIL 2026-09-08. E and Q are made on the
   * motherboard's U6 and that part had no /WAIT input, so this output held
   * nothing and the CPU read VRAM out from under the span writer -
   * machine.md 5 item 8. gal/clkdec.pld now has the hold term.
   *
   * The E literal is the second of the two rules that came with the fix: a
   * wait is only useful while E is high, and qualifying it here is one
   * literal where qualifying it in the divider would double the term count
   * on E itself. */
  oe: "SPANBUSY & VRAMSEL & !IOPAGE & E",
})

const arbPins = place(arbCells, [14, 15, 16, 17, 18, 19, 20, 21, 22, 23])

export const arbDesign: Design = {
  name: "arb",
  partNo: "ARM6309-UV6",
  location: "video card - spare-access arbiter",
  signature: "A6309V6",
  /* ⚠ NOT superseded any more. This design was folded into vctrl by the
   * two-CPLD rebalance and came back out on 2026-09-08: the widened $FF window
   * and physical A20 put two more inputs on vctrl, 76 I/O does not fit a
   * PLCC-84's 64, and these ten macrocells are the cheapest ten pins on that
   * part to give back. video.cpld.ts carries the argument; vctrl now fits at
   * 64 of 64. */

  inputs: [
    { name: "VRAMSEL", pin: 1 },
    { name: "IOPAGE", pin: 2, activeLow: true },
    { name: "CPUA0", pin: 3 }, { name: "CPUA1", pin: 4 },
    { name: "SPNREQ", pin: 5 },
    { name: "SPNA0", pin: 6 }, { name: "SPNA1", pin: 7 },
    /* From seqctl, for /WAIT. */
    { name: "SPANBUSY", pin: 8 },
    /* The bus clock, for /WAIT's E qualification - machine.md 5 item 8's
     * second rule. Added 2026-09-08 with the E literal on the output enable. */
    { name: "E", pin: 9 },
  ],
  cells: arbCells.map((c) => ({ ...c, pin: arbPins[c.name] })),
  spares: [],
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
  supersededBy: "graphics.md 10.1.6 - the video card is 2 x ATF1508AS",
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
  supersededBy: "graphics.md 10.1.6 - the video card is 2 x ATF1508AS",
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
