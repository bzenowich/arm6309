/* §19 item 23(b): the register-file decode, which the item calls "the last
 * thing on the card that has never been stated precisely". Stating it is most
 * of the work; the equations are small.
 *
 * §13 puts 32 bytes at $FF60-$FF7F. The motherboard's /IOSEL covers
 * $FF40-$FF7F (clkdec.pld), so this card's own window is its upper half - one
 * address bit, A5. That is the whole of REGSEL.
 *
 * §6.3.2 is the other half and it is not optional: physical A19 keeps being
 * emitted during an I/O cycle, so a VRAM select made of A19 alone matches
 * every I/O access in the machine - "the addressed card AND VRAM both drive
 * D0-D7". The /IOPAGE term is what stops that, and §6.3.2 requires it on the
 * posted-write capture and not only on the read path.
 *
 * WHY THE STROBES ARE DECODED HERE RATHER THAN CARRIED. Item 23's table
 * offers "1 x '138 off the register-write address" for WPTR's three load
 * strobes, which was the right answer on a card made of GALs. On a CPLD it is
 * backwards: macrocells are cheap and pins are not (vctrl fits at 62 of 64),
 * and one strobe per register costs one pin per register. Six address lines
 * and a write strobe replace nine of them, which is the same trade that
 * CTRL's double crossing paid for in §10.1.6.1.
 */

import type { Cell } from "./jedec/assemble"
import { minimalSop } from "./jedec/twolevel"

/* §13's map, as the decode sees it. The three tile registers are §6.4.6's
 * "TILEBASE / FONTBASE and the map base fit in +$17-$19, reserved in §13" -
 * which is where they go, and it settles the question §10.1.6 left open by
 * mistakenly calling the window sixteen bytes. */
export const REGS = {
  CTRL: 0x00, VSCROLL: 0x01, VSCROLLH: 0x02, HSCROLL: 0x03, HSCROLLH: 0x04,
  SPANLEN: 0x05, WFG: 0x06, WBG: 0x07,
  WPTRA: 0x08, WPTRB: 0x09, WPTRC: 0x0a,
  LISTA: 0x0b, LISTB: 0x0c, LISTC: 0x0d, BCTRL: 0x0e,
  TILEBASE: 0x17, FONTBASE: 0x18, MAPBASE: 0x19,
} as const

/** A 5-bit equality against RA4..RA0, as one product term. */
export const isReg = (off: number) =>
  [4, 3, 2, 1, 0].map((b) => `${(off >> b) & 1 ? "" : "!"}RA${b}`).join(" & ")

const comb = (name: string, terms: string[], why?: string): Cell =>
  ({ pin: 0, name, assertedLow: false, s0: 1, registered: false, terms, why })

const strobeHere = (name: string, off: number, why?: string) =>
  comb(name, [`WSTB & ${isReg(off)}`], why)

/* ---- on vctrl: the two selects, the strobe, and the file address -------- */
export const decodeCells: Cell[] = [
  /* §6.3.2 consumer 1. One product term, and the /IOPAGE literal in it is the
   * difference between a working card and one that corrupts its framebuffer
   * on every I/O write in the machine. */
  comb("VRAMSEL", ["A19 & !A20 & !IOPAGE"],
    "6.3.2 - A19 alone matches every I/O access, because the map SRAM keeps driving it. " +
    "/A20 since 2026-09-08: the physical map is 2 MB (machine.md 5 item 1 D) and the " +
    "ring is its second quarter, not the top half of a 1 MB map"),

  /* $FF60-$FF7F: the upper half of the motherboard's /IOSEL window.
   *
   * A6 joined on 2026-09-08. /IOSEL widened to $FF00-$FF7F (machine.md 5 item 1
   * A) and A6 left the strobe, so IOSEL & A5 alone matches $FF60-$FF7F AND
   * $FF20-$FF3F - the card would answer twice. Every card on this backplane
   * decodes A0-A6 now. */
  comb("REGSEL", ["IOSEL & A6 & A5"]),

  /* The posted-write strobe. E-qualified, because a 6809 write is only valid
   * data in the second half of the cycle, and §6.3.2 wants the capture gated
   * by /IOPAGE too - which it is, through REGSEL. */
  comb("WSTB", ["REGSEL & !RW & E"]),

  /* The file address: the CPU's low five bits during a register access, and
   * the sequencer's own during everything else. §7.4's two deferrable reads
   * are WFG and WBG, which differ only in bit 0 - §13.1 already requires that
   * placement, so the internal side is one selected constant and not a mux. */
  ...[0, 1, 2, 3, 4].map((b) => comb(`RA${b}`, minimalSop([
    `REGSEL & A${b}`,
    ...(((REGS.WFG >> b) & 1) ? ["!REGSEL & RDFG"] : []),
    ...(((REGS.WBG >> b) & 1) ? ["!REGSEL & RDBG"] : []),
    ...(((REGS.SPANLEN >> b) & 1) ? ["!REGSEL & RDLEN"] : []),
  ]), b === 0 ? "13.1's WFG-at-A0=0 / WBG-at-A0=1 rule is what keeps this one term" : undefined)),

  /* §7.4's "two deferrable file reads" at span end, plus the length read, as
   * a stated micro-sequence rather than three signals arriving from nowhere.
   * Item 23 says the internal side of the file address "has never been stated
   * precisely"; this is the statement. A span needs SPANLEN, WFG and WBG once
   * each and none of them changes while it runs, so a two-bit walk at span
   * end fetches all three for the NEXT span - which is what makes them
   * deferrable. Two macrocells and three decodes. */
  ...[0, 1].map((b) => ({
    pin: 0, name: `FP${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: b === 0
      ? ["SPANEND & !FP0"]
      : ["SPANEND & FP1 & !FP0", "SPANEND & !FP1 & FP0", "!SPANEND & FP1"],
  })),
  comb("RDLEN", ["!SPANBUSY & !FP1 & !FP0"]),
  comb("RDFG", ["!SPANBUSY & !FP1 & FP0"]),
  comb("RDBG", ["!SPANBUSY & FP1 & !FP0"]),

  /* The two register writes that are not loads of a counter: CTRL and the
   * VSTAT-side strobe. They were pins into this part until item 23 gave it
   * the file address to decode them from. */
  strobeHere("WCTRL", REGS.CTRL),
  strobeHere("VSTATWR", REGS.SPANLEN),

  /* hgen's terminal count is hgen's, and hgen is on this part. */
  comb("HLAST", ["H7 & H6 & H5 & H4 & H3 & H2 & H1 & H0"]),

  /* The scan pair's two controls. Both are raster positions, not register
   * writes, so they are here rather than in the strobe decode below. */
  comb("HLOAD", ["HBLANK & SLOTTICK"],
    "8 - the column counter preloads from HSCROLL[9:2] at the start of each line's fetch"),
  comb("ROWADV", ["HLAST & SLOTTICK & !VBLANK"]),
]

/* ---- on vaddr: one strobe per write target, from the address ------------ */
const strobe = (name: string, off: number, why?: string) =>
  comb(name, [`WSTB & ${isReg(off)}`], why)

export const writeStrobes: Cell[] = [
  strobe("LDVSL", REGS.VSCROLL), strobe("LDVSH", REGS.VSCROLLH),
  strobe("LDHS", REGS.HSCROLL),  strobe("LDHSH", REGS.HSCROLLH),
  strobe("LDA", REGS.WPTRA, "WPTR's three bytes - item 23 offered a '138 for these"),
  strobe("LDB", REGS.WPTRB), strobe("LDC", REGS.WPTRC),
  strobe("LDTB", REGS.TILEBASE), strobe("LDFB", REGS.FONTBASE),
  strobe("LDMB", REGS.MAPBASE),
  /* LIST is three bytes and one strobe: the pointer loads a byte at a time
   * and the engine is reserved (§10.3), so the byte select rides on RA1..RA0
   * inside the pointer rather than costing three macrocells here. */
  comb("LLOAD", [`WSTB & !RA4 & RA3 & !RA2 & RA1`],
    "$0B-$0D, LIST's three bytes under one strobe"),
]
