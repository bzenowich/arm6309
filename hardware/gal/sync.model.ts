/* What the video card's sync trio is supposed to do, as arithmetic.
 *
 * Deliberately not a sum of products and not a fuse map: counters are numbers
 * here and windows are comparisons, so that sync.check.ts is comparing the
 * assembled JEDECs against a statement of the raster rather than against a
 * second copy of the same equations. The generated terms in sync.jedec.ts -
 * range decomposition, the counter's carry chain, the polarity XOR - are the
 * parts most able to be subtly wrong, and they are all invisible here.
 */

import { H, V449, V525, family } from "./sync.timing"

export interface SyncState {
  h: number
  v: number
  /** the sync window, delayed one dot - what makes VBLPEND an edge */
  vsdly: 0 | 1
  pend: 0 | 1
}

export const RESET_STATE: SyncState = { h: 0, v: 0, vsdly: 0, pend: 0 }

export interface SyncIn {
  /** one dot in four: the fetch-slot rate */
  ce: boolean
  /** VMODE[0]: 0 = 449 lines, 1 = 525 */
  m0: 0 | 1
  /** a write to VSTAT clears the pending flag */
  vstatwr: boolean
}

/** The line counter's modulus, which is the whole of VMODE[0]'s effect on
 *  timing - everything else it touches is polarity or a blank window. */
export const vTerminal = (m0: 0 | 1) => family(m0).lines - 1

const inSync = (s: SyncState) => s.v <= V449.syncEnd // v <= 1, both families

/** One rising edge of the 25.175 MHz dot clock. */
export const step = (s: SyncState, io: SyncIn): SyncState => {
  const lineAdv = io.ce && s.h === H.last
  const raw = inSync(s)
  return {
    h: io.ce ? (s.h === H.last ? 0 : s.h + 1) : s.h,
    v: lineAdv ? (s.v === vTerminal(io.m0) ? 0 : s.v + 1) : s.v,
    vsdly: raw ? 1 : 0,
    /* set on the leading edge of the window, held until software clears it.
     * A level would re-arm under its own handler. */
    pend: raw && !s.vsdly ? 1 : s.pend && !io.vstatwr ? 1 : 0,
  }
}

export interface SyncOut {
  hsync: 0 | 1
  hblank: 0 | 1
  vsync: 0 | 1
  vblank: 0 | 1
  blank: 0 | 1
  vtc: 0 | 1
  /** 0 when asserted, -1 when the open-drain pin is floating */
  irq: 0 | -1
}

const bit = (b: boolean): 0 | 1 => (b ? 1 : 0)

export const outputs = (
  s: SyncState, io: { m0: 0 | 1; hpol: 0 | 1; irqen: boolean },
): SyncOut => {
  const f = family(io.m0)
  const hblank = s.h <= H.backEnd || s.h > H.activeEnd
  const vblank = s.v <= f.backEnd || s.v > f.activeEnd
  return {
    /* Polarity is XOR at the pin in both axes. HPOL is strapped high, so
     * HSYNC is negative; VSYNC follows VMODE[0], which is the only thing the
     * monitor uses to tell 449 lines from 525 (graphics.md 6.2.1). */
    hsync: bit((s.h <= H.syncEnd) !== (io.hpol === 1)),
    vsync: bit(inSync(s) !== (io.m0 === 1)),
    hblank: bit(hblank),
    vblank: bit(vblank),
    blank: bit(hblank || vblank),
    vtc: bit(s.v === vTerminal(io.m0)),
    irq: s.pend && io.irqen ? 0 : -1,
  }
}

/** The frame the raster should produce, for the check to assert against the
 *  documents rather than against itself. */
export const frameFacts = (m0: 0 | 1) => {
  const f = family(m0)
  return {
    lines: f.lines,
    activeLines: f.activeEnd - f.backEnd,
    syncLines: f.syncEnd + 1,
    vsyncPositive: f.vsyncPositive,
    activeSlots: H.activeEnd - H.backEnd,
    syncSlots: H.syncEnd + 1,
  }
}
