/* U6's behaviour - the divider, /IOSEL and boot mode - stated the way
 * clkdec.v states it.
 *
 * Deliberately NOT a sum of products. clkdec.pld holds the equations in the
 * hand-expanded form a 22V10 can implement - C1 as an XOR pair, C2 as four
 * terms after the terminal-count suppression is distributed, E and Q as
 * seven and five decode terms - and expanding them by hand is the step most
 * likely to be wrong. This file says what the counter is supposed to do in
 * the arithmetic clkdec.v uses, so that jedec.check.ts compares the fuses
 * against an independent statement rather than against the same one twice.
 *
 * clkdec_tb.sv checks clkdec.v against machine.md's claims under Verilator;
 * this is a transcription of that module's behavioural half.
 */

/* RUN rides with the counter because it is a registered macrocell on the same
 * part, sharing the same clock and the same asynchronous reset. RUN = 0 is
 * BOOT MODE, and it is zero at reset because a 22V10 resets to zero and has
 * no per-macrocell preset - machine.md 7.2 and clkdec.pld. */
export interface Counter { cnt: number; e: 0 | 1; q: 0 | 1; run: 0 | 1 }

export const RESET_STATE: Counter = { cnt: 0, e: 0, q: 0, run: 0 }

/** One rising edge of the 25.175 MHz master. */
/* /WAIT holds every registered macrocell - machine.md 5 item 8. It is a
 * third argument rather than a field of Counter because it is an input to the
 * part, not state inside it. */
export const step = (s: Counter, fastE: boolean, wait = false, setRun = false): Counter => {
  /* RUN is NOT held by /WAIT. It is not part of the divider; it is a mode bit
   * that happens to live on the same part, and holding it would mean a $FFB1
   * write during a stretched cycle did nothing. */
  const run = (s.run || setRun ? 1 : 0) as 0 | 1
  if (wait) return { ...s, run }
  const nxt = (fastE ? s.cnt === 7 : s.cnt === 11) ? 0 : s.cnt + 1
  return {
    cnt: nxt,
    run,
    /* E and Q are decoded from the NEXT count, not the current one - a
     * combinational decode of the counter glitches where several bits change
     * together, and this output is the machine's clock. */
    e: (fastE ? nxt >= 4 : nxt >= 6) ? 1 : 0,
    /* THE Q TAP IS DIVISOR-DEPENDENT. Q leads E by a quarter cycle in both
     * modes, which is 3 counts at /12 and 2 at /8 - graphics.md 18 step 0. */
    q: (fastE ? nxt >= 2 && nxt <= 5 : nxt >= 3 && nxt <= 8) ? 1 : 0,
  }
}

export interface DecodeIn {
  nIopage: 0 | 1 // the PIN level: low when the cycle is $FF00-$FFFF
  la7: 0 | 1
  la6: 0 | 1
  /* ⚠ LA5 and LA4 reach this decode since 2026-09-09. The buffer's enable is
   * the complement of U9's map-SRAM chip enable, and that needs the two block
   * windows - clkdec.pld. */
  la5: 0 | 1
  la4: 0 | 1
  run: 0 | 1 // the RUN register's own output - 0 is boot mode
}

export interface DecodeOut {
  nIosel: 0 | 1
  nBootOe: 0 | 1
}

const not = (b: boolean): 0 | 1 => (b ? 0 : 1)

/** $FFB1, the strobe that sets RUN. Level, over E-high, on a write. */
export const setsRun = (i: {
  nIopage: 0 | 1; la7: 0 | 1; la6: 0 | 1; la5: 0 | 1; la4: 0 | 1; la0: 0 | 1
  rw: 0 | 1; e: 0 | 1
}): boolean =>
  !i.nIopage && !!i.la7 && !i.la6 && !!i.la5 && !!i.la4 && !!i.la0 && !i.rw && !!i.e

export const decode = (i: DecodeIn): DecodeOut => {
  const iopage = !i.nIopage
  /* ⭐ The buffer drives exactly when the map SRAMs do not, which is the
   * complement of u9.model.ts's nMapCeLo/nMapCeHi and is written as that
   * rather than as a list of modes - clkdec.pld has what the list got wrong
   * in both directions. The vector page falls out: $FFC0-$FFFF is an I/O
   * cycle and not a block access, so the SRAMs are off there already. */
  const blkhi = iopage && !!i.la7 && !i.la6 && !i.la5 && !!i.la4
  const blklo = iopage && !!i.la7 && !i.la6 && !!i.la5 && !i.la4
  const mapsel = (!!i.run && !iopage) || blkhi || blklo
  return {
    /* $FF00-$FF7F: the I/O page with A7 = 0. */
    nIosel: not(iopage && !i.la7),
    nBootOe: not(!mapsel),
  }
}
