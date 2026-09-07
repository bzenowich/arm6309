/* The audio card's five GALs, as arithmetic - audio.md §9.5's table.
 *
 * The card is one slot-walked datapath (§3.1): a 28.37516 MHz oscillator, eight
 * 35.24 ns slots per colour clock, and a fixed job per slot. Almost everything
 * that would be a counter on another design lives in the state file instead
 * (§9.5), so what is left in programmable logic is the walk itself, the host
 * decode, and three registers with Paula's set/clear convention.
 */

export const SLOTS_PER_FRAME = 8

/** §3.1: slots 0-3 are channels 0-3, 4 is the tempo timer, 5 is host service,
 *  6-7 are deferred work. */
export const enum Slot { Chan0 = 0, Timer = 4, Host = 5, Defer0 = 6, Defer1 = 7 }

export const nextSlot = (s: number) => (s + 1) % SLOTS_PER_FRAME
export const isChannel = (s: number) => s < 4
export const isTimer = (s: number) => s === Slot.Timer
export const isHost = (s: number) => s === Slot.Host
export const isDeferred = (s: number) => s >= Slot.Defer0
/** The colour clock is the frame boundary: one pulse per eight slots. */
export const isFrameEnd = (s: number) => s === SLOTS_PER_FRAME - 1

/* -- Paula's set/clear convention, §9.2 ----------------------------------
 * ADMACON, AINTENA and AINTREQ all take it: bit 7 of the written byte says
 * whether the named bits are set or cleared, and unnamed bits are untouched.
 * A replayer ported from 68000 writes the same constants it always did. */
export const setClear = (current: number, data: number, write: boolean, width: number) => {
  if (!write) return current
  const mask = data & ((1 << width) - 1)
  return (data & 0x80 ? current | mask : current & ~mask) & ((1 << width) - 1)
}

/* -- the tempo prescale, §8.2 --------------------------------------------
 * colour clock / 5 = 709,379 Hz, which is the Amiga's CIA-B clock and not an
 * approximation of it, so every replayer's Fxx arithmetic transfers unchanged.
 * The ÷5 is identical on PAL and NTSC, so the socketed NTSC can carries the
 * tempo reference with it. */
export const PRESCALE = 5
export const nextPrescale = (p: number, tick: boolean) => (tick ? (p + 1) % PRESCALE : p)
export const prescaleCarry = (p: number, tick: boolean) => tick && p === PRESCALE - 1

/* -- INTREQ and its pending register, §9.4.5 -----------------------------
 * Request bits are set into a 6-bit pending register by the slot logic and
 * merged into INTREQ on the colour clock AFTER the synchronised read strobe
 * deasserts. A write-to-clear in the same window clears only the bits the host
 * named, and any set that arrived meanwhile survives the clear. That ordering
 * is the only one under which "read AINTREQ, then clear what you saw" is
 * race-free, and it is Paula's. */
export interface IntState { req: number; pend: number }

export const stepInt = (
  s: IntState,
  io: { write: boolean; data: number; merge: boolean; setBits: number },
): IntState => {
  const named = io.data & 0x3f
  let req = s.req
  if (io.write) req = io.data & 0x80 ? req | named : req & ~named
  if (io.merge) req |= s.pend
  return {
    req: req & 0x3f,
    pend: (io.merge ? 0 : s.pend) | io.setBits,
  }
}

/** §8.1: /FIRQ is wire-ORed, so the pin drives low or floats and never high. */
export const firqAsserted = (req: number, ena: number) => (req & ena & 0x3f) !== 0
