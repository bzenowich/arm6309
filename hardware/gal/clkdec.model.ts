/* U6's behaviour, stated the way clkdec.v states it.
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

export interface Counter { cnt: number; e: 0 | 1; q: 0 | 1 }

export const RESET_STATE: Counter = { cnt: 0, e: 0, q: 0 }

/** One rising edge of the 25.175 MHz master. */
export const step = (s: Counter, fastE: boolean): Counter => {
  const nxt = (fastE ? s.cnt === 7 : s.cnt === 11) ? 0 : s.cnt + 1
  return {
    cnt: nxt,
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
  a19: 0 | 1 // PHYSICAL A19, out of the map SRAM
  a20: 0 | 1 // PHYSICAL A20, likewise - the map SRAM's eighth output bit
  rw: 0 | 1
  e: 0 | 1
}

export interface DecodeOut {
  nIosel: 0 | 1
  nRamCe: 0 | 1
  nRamOe: 0 | 1
  nRamWe: 0 | 1
}

const not = (b: boolean): 0 | 1 => (b ? 0 : 1)

export const decode = (i: DecodeIn): DecodeOut => {
  /* A20 = 0 as well: the map is 2 MB and system RAM is its bottom quarter. */
  const ramsel = !!i.nIopage && !i.a19 && !i.a20
  return {
    /* $FF00-$FF7F: the I/O page with A7 = 0. la6 is unused - clkdec.pld. */
    nIosel: not(!i.nIopage && !i.la7),
    nRamCe: not(ramsel),
    /* /OE is qualified by R/W: with it tied low the SRAM drives D0-D7 from
     * /CE time until /WE asserts, about 90 ns of contention on every write. */
    nRamOe: not(ramsel && !!i.rw),
    nRamWe: not(ramsel && !i.rw && !!i.e),
  }
}
