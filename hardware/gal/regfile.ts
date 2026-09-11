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
  /* ⚠ LISTA/B/C AT $0B-$0D ARE GONE - 2026-09-08, graphics.md 10.3.1. The list
   * engine shares WPTR rather than carrying its own pointer (10.1.6.2 option
   * 2), so a second address for the same nineteen registers was a fiction, and
   * a fiction that invites exactly the bug 10.3.1 exists to warn about. A list
   * is started by loading WPTR at $08-$0A and writing BCTRL. $0B-$0D are free. */
  BCTRL: 0x0e,
  /* 9's palette port. ⛔ These three were in 13's table from the beginning and
   * had no decode, no strobe and no counter behind them until 2026-09-09 -
   * vsup.parts.ts has the census. They are decoded on vsup, which is the part
   * that holds PIDX and drives the LUT's two buses. */
  PIDX: 0x10, PDATL: 0x11, PDATH: 0x12,
  WADV: 0x14,
  /* ⭐ VDATA IS BUILT, 2026-09-11 - graphics.md 11, 19 item 47. The VRAM port
   * at an I/O address: vsup decodes it from the raw address (RA is a span's
   * colour while one runs) and vctrl ORs it into the posted write and /WAIT. */
  VDATA: 0x15,
  TILEBASE: 0x17, FONTBASE: 0x18, MAPBASE: 0x19,
} as const

/** A 5-bit equality against RA4..RA0, as one product term. */
export const isReg = (off: number) => isRegOn("RA", off)

/** The same equality against any five-bit field. 10.3.2's descriptor carries
 *  the register number in its low five bits, so vsup decodes a list MOVE from
 *  LD4..LD0 with the identical arithmetic - and 13's offsets stay in one
 *  table rather than being written out twice in two notations. */
export const isRegOn = (prefix: string, off: number) =>
  [4, 3, 2, 1, 0].map((b) => `${(off >> b) & 1 ? "" : "!"}${prefix}${b}`).join(" & ")

const comb = (name: string, terms: string[], why?: string): Cell =>
  ({ pin: 0, name, assertedLow: false, s0: 1, registered: false, terms, why })

const strobeHere = (name: string, off: number, why?: string) =>
  comb(name, [`WSTB & ${isReg(off)}`], why)

/* ---- on vctrl: the VRAM select, and that is now all of it ---------------
 *
 * ⚠ REGSEL, WSTB and RA0-RA4 LEFT THIS PART on 2026-09-08 for regfile.jedec.ts's
 * own GAL22V10. This file's header argues for keeping them here - "macrocells
 * are cheap and pins are not (vctrl fits at 62 of 64)" - and that was right
 * until vctrl hit 64 of 64 and graphics.md 7.4's broadcast write needed
 * signalling between vctrl and vaddr with nowhere to put it.
 *
 * The trade reversed rather than the reasoning being wrong: six pins out and
 * two back, because the new part forms RDFG/RDBG/RDLEN itself from FP1:FP0
 * instead of taking them decoded. REGSEL goes too - nothing consumed it, and
 * rfa recomputes it from IOSEL & A6 & A5, all three of which are on the card. */
export const decodeCells: Cell[] = [
  /* §6.3.2 consumer 1. One product term, and the /IOPAGE literal in it is the
   * difference between a working card and one that corrupts its framebuffer
   * on every I/O write in the machine. */
  comb("VRAMSEL", ["A19 & !A20 & !IOPAGE"],
    "6.3.2 - A19 alone matches every I/O access, because the map SRAM keeps driving it. " +
    "/A20 since 2026-09-08: the physical map is 32 MB (machine.md 5 item 1 D) and the " +
    "ring is one 512 KB quadrant of it, not the top half of a 1 MB map"),
]

/* ---- on vaddr: one strobe per write target, from the address ------------ */
const strobe = (name: string, off: number, why?: string) =>
  comb(name, [`WSTB & ${isReg(off)}`], why)

export const writeStrobes: Cell[] = [
  strobe("LDVSL", REGS.VSCROLL), strobe("LDVSH", REGS.VSCROLLH),
  strobe("LDHS", REGS.HSCROLL),  strobe("LDHSH", REGS.HSCROLLH),
  /* ⛔ LDADV LEFT THIS PART ON 2026-09-11. It was decoded here for vctrl and
   * never exported - a buried cell, substituted into nothing, while vctrl's pin
   * for it had no driver on silicon. vsup decodes it and exports it now
   * (vsup.parts.ts); this part had no other reader of it. */
  /* ⚠ BCTRLGO IS NOT DECODED HERE ANY MORE - 2026-09-09. 13's +$0E b0 is the
   * display list's GO, and the whole descriptor half of the engine moved to
   * vsup when vaddr ran out of LAB fan-in (vsup.parts.ts). LRUN is what the
   * strobe sets, so the strobe went with it; this part takes LADV back and
   * nothing else. */
  strobe("LDA", REGS.WPTRA, "WPTR's three bytes - item 23 offered a '138 for these"),
  strobe("LDB", REGS.WPTRB), strobe("LDC", REGS.WPTRC),
  strobe("LDTB", REGS.TILEBASE),
  /* ⛔ LDFB IS DELETED - 2026-09-10, graphics.md 19 item 40.
   *
   * FONTBASE's eight registers went with 6.4.3's Variant B on 2026-09-08
   * (video.parts.ts) and the strobe that loaded them did not, so vaddr carried
   * a decode of an address 13 already calls reserved, for a feature the card
   * does not have. check:reach found it: produced, and read by nothing.
   *
   * ⭐ ONE CELL, ON THE PART THAT CANNOT SPARE THEM. vaddr is at 113 of 128 and
   * 63 of 64 I/O, and 19 item 33's rewrite is already blocked on cells there -
   * "VSCROLL in the display list is refused by the fitter for want of nine". */
  strobe("LDMB", REGS.MAPBASE),
  /* ⚠ LLOAD IS DELETED - 2026-09-08, and it was carrying a defect.
   *
   * It read: WSTB & !RA4 & RA3 & !RA2 & RA1, described as "$0B-$0D, LIST's
   * three bytes under one strobe". That term matches $0A AND $0B - five bits
   * with RA0 free is two addresses, not three - and $0A IS WPTRC. So a write
   * to the write pointer's third byte also loaded the list pointer.
   *
   * It never fired in anger because the engine was not built, and the shared
   * pointer deletes both the strobe and the bug: nothing reads LLOAD now,
   * because LP0-LP18 are gone (video.parts.ts). Recorded rather than quietly
   * removed - a decode that claimed three addresses and matched two is the
   * kind of arithmetic this file is supposed to get right. */
]
