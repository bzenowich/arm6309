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
  why: "open-drain by the OE idiom - SPANBUSY . VRAMSEL . /IOPAGE . E . /RW",
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
  /* !RW: ONLY WRITES WAIT, added 2026-09-08.
   *
   * 3.1.1 says what this backstop actually protects - the depth-1 posted-write
   * latch, which a second CPU write during a span would overwrite. A READ does
   * not touch that latch, and 5.2.1's arbiter already gives the CPU its chip
   * ahead of the span writer, so a read has no conflict to wait for either.
   * It was stalling anyway, for up to 7.4's 40.7 us.
   *
   * What that buys is on the other side of the card: features.md 8 and 9's
   * sprite save-behind, mouse cursor and read-modify-write pixels are all
   * VRAM READS, and they stop being exposed to the bound entirely. Writes
   * still wait, which is the throttle that keeps the CPU from outrunning the
   * span writer - that part is deliberate.
   *
   * A read during a span sees a partially retired span. That is the caller's
   * own span and VSTAT b7 says whether it has finished, so it is a software
   * rule (7.4) and not a hazard. */
  oe: "SPANBUSY & VRAMSEL & !IOPAGE & E & !RW",
})

const arbPins = place(arbCells, [14, 15, 16, 17, 18, 19, 20, 21, 22, 23])

export const arbDesign: Design = {
  name: "arb",
  partNo: "ARM6309-UV6",
  location: "video card - spare-access arbiter",
  signature: "A6309V6",
  /* ⚠ SUPERSEDED AGAIN, and the round trip took one day. The two-CPLD rebalance
   * folded this design into vctrl; the morning of 2026-09-08 pulled it back out,
   * because the widened $FF window and physical A20 put vctrl at 76 I/O against
   * a PLCC-84's 64 and these ten macrocells were the cheapest ten pins to give
   * back; and the evening put it in again, because three unrelated changes -
   * rfa (-14 pins), 6.4.3's Variant B (-4) - had left vctrl at 46 of 64 with a
   * GAL22V10 beside it doing ten macrocells of work.
   *
   * THE DESIGN IS STILL CHECKED. access.check.ts executes its fuses against
   * access.model.ts and jedec/cupl.check.ts sweeps it against Atmel's compiler
   * over all 1,024 inputs, exactly as it does for the sync trio and the scan
   * pair, which have been inside a CPLD since 2026-09-06. A GAL22V10 fuse map
   * is the only form either check can execute, so the standalone design is the
   * verification and not a leftover. */
  supersededBy: "graphics.md 10.1.6.3 - merged back into vctrl 2026-09-08",

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
    /* R/W, so that only WRITES wait - see the output enable below. */
    { name: "RW", pin: 10 },
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

/* ⭐ THE COLUMN LOADS FROM ITS SHADOW AND NOT FROM D0-D7 - 2026-09-09, and it
 * is what makes 7.2's chaining fit.
 *
 * 7.2 buys "13 writes per character cell" instead of 26 with WADV = 01, "next
 * row, same column": at span end the row advances and THE COLUMN RELOADS FROM
 * A SHADOW. The row half was built and the column half was not, so a chained
 * glyph advanced its row and kept the eight columns the span had just retired,
 * stepping eight pixels right on every row. Every figure in 7.3 and
 * features.md 2.3 rests on it. docs/design-review2.md V-6.
 *
 * ⚠ AND THE OBVIOUS WIRING DOES NOT FIT. Adding the shadow as a THIRD load
 * source alongside D0-D7 puts ten more signals into the ten macrocells that
 * already read the data bus, and the ATF1508's switch matrix admits 40 of ~200
 * per logic block: the fitter aborts with INTERNAL ERROR, which is the same
 * wall 10.1.6.2 hit with the list engine's own pointer.
 *
 * ⭐ SO THE SHADOW IS THE REGISTER FILE, WHICH IS WHAT 7.2 SAID: "a CPU write
 * to WPTR's low and middle bytes ALSO strobes the register file... at span end
 * the sequencer takes two deferrable file reads to restore the column. No
 * latch, no mux." The file already stores every register the CPU writes, and
 * the '245 of 3.2 already puts its output on the same internal data bus the
 * CPU's writes arrive on - so the reload uses THIS PART'S EXISTING LOAD PATH
 * with a second pair of strobes, and costs ten macrocells nowhere.
 *
 * RLDA and RLDB are those strobes. video.parts.ts sequences them: WROWADV
 * starts a two-dot walk, rfa points the file at $08 and then $09, and each
 * byte lands on the load path the CPU's own write already uses.
 *
 * ⚠ WHAT DOES NOT WORK is the obvious thing, and it is worth recording. Ten
 * shadow REGISTERS on vaddr - loaded beside this counter, read back into it -
 * is the same repair with no sequencer, and the fitter refuses it: vaddr is at
 * 118 of 128 logic cells and ten more will not GROUP, whether they arrive as a
 * third load source (INTERNAL ERROR, which is 10.1.6.2's fan-in wall) or as
 * the only one (Grouping fail). The two-cycle read is not the cheap option
 * chosen over an elegant one; it is the one that fits.
 *
 * ⚠ AND BOTH CHAINING MODES RELOAD. 13's WADV = 10 is "advance by the stride",
 * a vertical line at one pixel per span - so its column advances by one and
 * has to come back too. WROWADV is already SPANEND & (WADV0 # WADV1). */
/* ⭐ THREE LOAD SOURCES SINCE 2026-09-09, and the third is 7.2's whole text
 * engine.
 *
 * 7.2 buys "13 writes per character cell" instead of 26 with WADV = 01, "next
 * row, same column": at span end the row advances and THE COLUMN RELOADS FROM
 * A SHADOW. The row half was built; the column half was not, and wcol's only
 * load path was the CPU's own register write - so a chained glyph advanced its
 * row and kept the eight columns the span had just retired, stepping eight
 * pixels right on every row. Every figure in 7.3 and features.md 2.3 rests on
 * it. docs/design-review2.md V-6.
 *
 * The shadow is `wcolShadow` in video.parts.ts - ten registers loaded on
 * exactly the strobes that load this counter, so software writes WPTR once and
 * the shadow follows for free, which is what 7.2 means by "the shadow is
 * free". WROWADV is the reload, because it is already the signal that says a
 * span ended in a chaining mode, and it already crosses to this part. */
/** The column counter's terms, with or without 7.2's reload.
 *
 * ⚠ TWO FORMS, ONE GENERATOR, and the reason is a pin budget rather than a
 * choice - the same shape audio.jedec.ts uses for its interrupt block.
 *
 * WITH the reload this is thirteen inputs (D0-D7, both CPU strobes, both
 * reload strobes, WINC) on a part with eleven pins, so it is not a GAL22V10
 * design any more. WITHOUT it, it is the ten-macrocell eleven-input fit item
 * 12's answer rests on - and the reload changes nothing about the counting or
 * the wrap, which is what access.check.ts is for. So the check builds the
 * standalone form and video.cpld.ts merges the other.
 *
 * ⚠ AND ORing THE STROBES DOES NOT WORK, which is worth recording because it
 * is the obvious escape. `LDCA = LDA # RLDA` keeps the part at eleven inputs -
 * and CUPL substitutes combinational intermediates, so every hold term becomes
 * `!(LDA # RLDA)` = `!LDA & (!RP0 # RP1)`, two terms where there was one,
 * across all ten macrocells. The ATF1508 fitter aborts with INTERNAL ERROR. */
export const wcolTermsFor = (withReload: boolean) => WCOL.map((_, i) => {
  const counted = counterTerms({ bits: WCOL, enable: "WINC" })[i]
  const cpu = i < 8 ? "LDA" : "LDB"
  const rld = i < 8 ? "RLDA" : "RLDB"
  const d = i < 8 ? `D${i}` : `D${i - 8}`
  const srcs = withReload ? [cpu, rld] : [cpu]
  const hold = srcs.map((m) => `!${m}`).join(" & ")
  return [
    ...srcs.map((m) => `${m} & ${d}`),
    ...counted.map((t) => `${hold} & ${t}`),
  ]
})

export const wcolCellsFor = (withReload: boolean): Cell[] =>
  WCOL.map((name, i) => ({
    pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
    terms: wcolTermsFor(withReload)[i],
  }))

const wcolCells = wcolCellsFor(false)
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
