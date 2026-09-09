/* U10's behaviour - the SIMM controller - as arithmetic.
 *
 * hardware/ram.md 6.3 and 6.6. Four 30-pin sockets, CAS-before-RAS refresh, and
 * the one piece of logic on the motherboard that was never counted.
 *
 * TWO TIMEBASES, AND THAT IS THE WHOLE DESIGN:
 *
 *   the ACCESS is host-facing, so it decodes U6's divider counter C3..C0
 *   directly. RAS and CAS land at fixed counts of the bus cycle, which means
 *   they stall when E stalls - which is correct, because a stalled bus cycle
 *   is a bus cycle whose data is not wanted yet.
 *
 *   the REFRESH is not, so it must NOT touch that counter. machine.md 5 item
 *   10: a card's internal realtime scheduling free-runs on CLK25; only
 *   host-facing windows may be derived from E. /WAIT holds U6's counter
 *   (machine.md 5 item 8), so a refresh timed from C3..C0 would stop dead for
 *   the 40.7 us the video card can hold the bus - 2.6 refresh intervals, and
 *   the DRAM forgets. The refresh runs off REFCLK, which is a free-running
 *   divider of CLK25 and nothing else.
 *
 * Deliberately NOT a sum of products - u10.jedec.ts holds the terms a 22V10
 * implements. Same split as mmu/clkdec/u9, for the same reason.
 */

/** The bus cycle, in CLK25 counts of U6's divider (clkdec.pld).
 *
 * E falls at the 0 edge and rises at the 6 edge, so count 0 is E-fall and the
 * cycle is 12 counts of 39.7 ns. Everything below is derived from that and
 * from the 6809's t_AD: the address is valid 110 ns after E-fall, which is
 * 2.77 counts. */
export const NS_PER_COUNT = 1000 / 25.175
export const PHASE = {
  /** Address valid. Nothing may sample before this. */
  addrValid: 110 / NS_PER_COUNT, // 2.77
  /** RAS falls. 158.8 ns - 48.8 ns of row-address setup. */
  rasLow: 4,
  /** The '157s switch to the column half. This is E itself - see below. */
  colSelect: 6,
  /** CAS falls. 278 ns: 79 ns of row hold after RAS, 40 ns of column setup,
   *  and for a write, 49 ns of data setup (write data is valid at 229 ns). */
  casLow: 7,
  /** Both released. 238 ns of t_RAS, and 238 ns of precharge to the next. */
  release: 10,
} as const

/** ⭐ THE ROW/COLUMN MUX SELECT IS `E`, AND NOT A GAL OUTPUT AT ALL.
 *
 * E is high for counts 6..11, which is exactly the column window above. So the
 * '157s' select input is a wire to the backplane's E and this part does not
 * spend a macrocell on it - which is what let a 9-output design fit.
 *
 * It is also what a 1970s DRAM controller on a 6800-family bus would have
 * done, for the same reason: row while E is low, column while E is high. */
export const MUXCOL_IS_E = true

export interface In {
  /** U6's divider count, 0..11. Frozen while /WAIT is asserted. */
  count: number
  /** U9's space decode: this cycle addresses one of the four SIMM windows. */
  dramsel: 0 | 1
  /** Physical A23:A22 - which window. See BANK below. */
  a23: 0 | 1
  a22: 0 | 1
  rw: 0 | 1
  /** The free-running refresh timebase - a divider of CLK25, NOT of E. */
  refclk: 0 | 1
}

/** Registered state, all of it on CLK25 and none of it held by /WAIT. */
export interface State {
  /** The refresh sequencer: 00 idle, 01 CAS low, 10 RAS low, 11 RAS held. */
  rf: number
  /** The last REFCLK level a refresh consumed. `refclk != refq` is "pending",
   *  which makes ONE macrocell both the edge detector and the request latch. */
  refq: 0 | 1
}

export const RESET_STATE: State = { rf: 0, refq: 0 }

export interface Out {
  /** Active low, one per socket. */
  nRas: [0 | 1, 0 | 1, 0 | 1, 0 | 1]
  nCas: 0 | 1
  /** The SIMMs' shared /WE. Early write: it leads CAS. */
  nWe: 0 | 1
}

/** ⭐ A23:A22 already distinguish the four windows, which is why U9 spends ONE
 * output on DRAMSEL and not four on selects. ram.md 5.2 puts the windows at
 * physical A24..A22 = 001, 010, 011, 100 - so A23:A22 is 01, 10, 11, 00, and
 * those are distinct. The mapping below is that, and it is NOT in numeric
 * order: socket 3 is the one at the top of the map. */
export const BANK = (a23: 0 | 1, a22: 0 | 1): number =>
  a23 === 0 && a22 === 1 ? 0 // 4-8 M
    : a23 === 1 && a22 === 0 ? 1 // 8-12 M
      : a23 === 1 && a22 === 1 ? 2 // 12-16 M
        : 3 // 16-20 M

const not = (b: boolean): 0 | 1 => (b ? 0 : 1)

/** True while the access half of the cycle owns RAS - counts 4..9. */
export const accessWindow = (count: number) => count >= 4 && count <= 9
/** Counts 7..9 - CAS low. */
export const casWindow = (count: number) => count >= 7 && count <= 9

/** ⚠ WHEN A REFRESH MAY START, and it is the subtle part.
 *
 * A refresh takes four CLK25 ticks and must be finished, with precharge, before
 * the access's RAS falls at count 4. Starting at count 10 or 11 puts its RAS
 * low at counts 0-1 or 1-2, leaving two or three counts of precharge. Starting
 * at count 0 would put RAS low at 2-3 and leave NONE.
 *
 * ⭐ And when this cycle is not a DRAM cycle there is no access to collide
 * with, so any count will do. That second clause is what keeps refresh alive
 * during a video-card stall: /WAIT freezes C3..C0, but a stalled cycle is a
 * VRAM write (graphics.md 7.4), so DRAMSEL is low and refresh runs freely -
 * which is the property ram.md 6.6 asserts and this is where it comes from. */
export const refreshSafe = (i: In) => !i.dramsel || i.count === 10 || i.count === 11

export const step = (s: State, i: In): State => {
  const pending = i.refclk !== s.refq
  const start = pending && refreshSafe(i)
  const rf = s.rf === 0 ? (start ? 1 : 0) : (s.rf + 1) & 3
  /* The request is consumed at the end of the burst, not at its start - so a
   * REFCLK edge arriving during a burst is still seen afterwards. */
  return { rf, refq: s.rf === 3 ? i.refclk : s.refq }
}

export const out = (s: State, i: In): Out => {
  const bank = BANK(i.a23, i.a22)
  const access = !!i.dramsel && accessWindow(i.count)
  /* CAS-before-RAS: CAS from rf 01, RAS from rf 10. The order IS the refresh
   * command - a DRAM that sees CAS fall before RAS refreshes a row it counts
   * itself, which is why ram.md 6.3 has no row counter and no mux path. */
  const refCas = s.rf !== 0
  const refRas = s.rf >= 2
  return {
    nRas: [0, 1, 2, 3].map((n) =>
      not((access && bank === n) || refRas)) as [0 | 1, 0 | 1, 0 | 1, 0 | 1],
    nCas: not((!!i.dramsel && casWindow(i.count)) || refCas),
    /* Early write - /WE leads CAS by three counts, so the SIMM takes the data
     * at CAS-fall and never drives the bus. Write data is valid at 229 ns and
     * CAS falls at 278: 49 ns of setup. */
    nWe: not(access && !i.rw),
  }
}
