/* rfa - the register-file address GAL, split off vctrl 2026-09-08.
 *
 * WHY IT EXISTS. regfile.ts's own header argues the opposite case, and it was
 * right when it was written: "macrocells are cheap and pins are not (vctrl
 * fits at 62 of 64), and one strobe per register costs one pin per register".
 * Six address lines and a write strobe replaced nine strobe pins.
 *
 * Then vctrl ran out of pins anyway - 64 of 64 after the widened $FF window
 * and physical A20 (10.1.6.3) - and graphics.md 7.4's broadcast write needs
 * signalling between vctrl and vaddr that there is nowhere to put. This part
 * is the relief that section names: RA0-RA4 and WSTB come off vctrl, and what
 * goes back is FP0/FP1, because this GAL can form RDFG/RDBG/RDLEN itself from
 * the fetch phase rather than taking three decoded signals.
 *
 *   6 pins out, 2 back  ->  vctrl falls to 60 of 64.
 *
 * REGSEL is recomputed here rather than carried: it is IOSEL & A6 & A5, and
 * all three are on the card already, so importing it would cost a pin to save
 * two product terms.
 */
import { place } from "./jedec/place"
import type { Cell, Design } from "./jedec/assemble"

/* REGSEL = IOSEL & A6 & A5, so !REGSEL is three terms - which is what makes
 * RA2 the widest equation here. The read-back selects are the fetch phase:
 * RDLEN/RDFG/RDBG are FP1:FP0 = 00/01/10 while the span writer is idle. */
const REGSEL = "IOSEL & A6 & A5"
const NOT_REGSEL = ["!IOSEL", "!A6", "!A5"]
const RD = {
  LEN: "!SPANBUSY & !FP1 & !FP0",
  FG: "!SPANBUSY & !FP1 & FP0",
  BG: "!SPANBUSY & FP1 & !FP0",
}
/** `!REGSEL & <rd>`, expanded - three terms, one per literal of !REGSEL. */
const gated = (rd: string) => NOT_REGSEL.map((n) => `${n} & ${rd}`)

const cells: Cell[] = [
  { pin: 0, name: "WSTB", assertedLow: false, s0: 1, registered: false,
    why: "E-qualified: a 6809 write is only valid data in the second half",
    terms: [`${REGSEL} & !RW & E`] },
  { pin: 0, name: "RA0", assertedLow: false, s0: 1, registered: false,
    terms: [`${REGSEL} & A0`, ...gated(RD.BG), ...gated(RD.LEN)] },
  { pin: 0, name: "RA1", assertedLow: false, s0: 1, registered: false,
    terms: [`${REGSEL} & A1`, ...gated(RD.FG), ...gated(RD.BG)] },
  { pin: 0, name: "RA2", assertedLow: false, s0: 1, registered: false,
    why: "the widest - three read-back sources, each three terms of !REGSEL",
    terms: [`${REGSEL} & A2`, ...gated(RD.FG), ...gated(RD.LEN), ...gated(RD.BG)] },
  { pin: 0, name: "RA3", assertedLow: false, s0: 1, registered: false,
    terms: [`${REGSEL} & A3`] },
  { pin: 0, name: "RA4", assertedLow: false, s0: 1, registered: false,
    terms: [`${REGSEL} & A4`] },
]

/* RA2 is ten terms, so it wants one of the wide macrocells. place() pairs the
 * widest equation with the widest macrocell still free, which is optimal for a
 * fixed set, and names the equation if it cannot. */
const pins = place(cells, [14, 15, 16, 17, 18, 19])

export const rfaDesign: Design = {
  name: "rfa",
  partNo: "ARM6309-UV9",
  location: "video card - register-file address",
  signature: "A6309V9",
  inputs: [
    { name: "IOSEL", pin: 1 }, { name: "A5", pin: 2 }, { name: "A6", pin: 3 },
    { name: "A0", pin: 4 }, { name: "A1", pin: 5 }, { name: "A2", pin: 6 },
    { name: "A3", pin: 7 }, { name: "A4", pin: 8 },
    { name: "RW", pin: 9 }, { name: "E", pin: 10 },
    /* From vctrl: the span-writer state the read-back mux keys off. SPANBUSY
     * is already a vctrl output (VSTAT b7); FP0/FP1 are the two new pins. */
    { name: "SPANBUSY", pin: 11 }, { name: "FP0", pin: 13 }, { name: "FP1", pin: 23 },
  ],
  cells: cells.map((c) => ({ ...c, pin: pins[c.name] })),
}
