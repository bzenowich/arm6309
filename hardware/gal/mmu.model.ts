/* The MMU GAL's equations, as arithmetic - the model, on its own.
 *
 * Split out of mmu.check.ts on 2026-09-06 so that the JEDEC check can compare
 * the fuse map against the same equations these claims are made about, rather
 * than against a second copy of them. mmu.check.ts asserts what this model
 * does; jedec.check.ts asserts that mmu.jed does the same thing.
 *
 * mmu.pld is the deliverable and mmu.v is what Verilator will drive once it
 * is installed. Neither runs today, and the equations are the part of this
 * design most easily got wrong - so they are restated here in the one
 * language this repository can already execute, and the claims
 * graphics.md 6.3.1 makes about them are checked exhaustively.
 *
 * "Exhaustively" is the whole 16-bit address space x 4 quadrature phases x
 * R/W - 524,288 evaluations, which is nothing. There is no sampling here.
 *
 * Keep in step with mmu.pld by hand. Seven equations.
 */

/* -- the four quadrature phases, in the order a cycle visits them -------- */
/* Q leads E by 90 degrees: E-fall, Q-rise, E-rise, Q-fall, E-fall. */
export const PHASES = [
  { name: "ph0 E0 Q0 (address becomes valid)", e: 0, q: 0 },
  { name: "ph1 E0 Q1 (Q has risen)", e: 0, q: 1 },
  { name: "ph2 E1 Q1 (E has risen)", e: 1, q: 1 },
  { name: "ph3 E1 Q0 (Q has fallen)", e: 1, q: 0 },
] as const

export interface Out {
  iopage: boolean   // asserted (the pin is inverted)
  muxsel: boolean
  isooe: boolean    // asserted
  mapwe: boolean    // asserted
  mapoe: boolean    // asserted
  ctrlcp: boolean   // the PIN level, not the term - high is the idle state
}

/* -- the equations ------------------------------------------------------ */
export const mmu = (la: number, e: number, q: number, rw: number): Out => {
  const bit = (n: number) => (la >> n) & 1
  const iopage = (la & 0xff00) === 0xff00
  const mmusel = iopage && !!bit(7) && !bit(6)
  /* TWO block windows, 2026-09-09. LA3 is the task bit of the write index
   * (mmu.pld), so it cannot also choose which of the two map SRAMs a write
   * lands in - that is what the window does now. $FF90-$FF9F is the high
   * byte, $FFA0-$FFAF the low, $FFB0-$FFBF control, $FF80-$FF8F free. */
  const blkhi = mmusel && !bit(5) && !!bit(4)
  const blklo = mmusel && !!bit(5) && !bit(4)
  const blksel = blkhi || blklo
  const ctlsel = mmusel && !!bit(5) && !!bit(4)
  return {
    iopage,
    muxsel: blksel,
    isooe: blksel && !!e,
    mapwe: blksel && !rw && !!e && !q,
    mapoe: !iopage || (blksel && !!rw && !!e),
    ctrlcp: !(ctlsel && !rw && !!e),
  }
}
