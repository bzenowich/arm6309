/* The arbiter's grant rule and the WPTR pointer, as arithmetic. */

export interface ArbIn {
  vramsel: boolean
  /** the PIN level: low during $FF00-$FFFF */
  nIopage: 0 | 1
  cpuChip: number
  /** the CPU's R/W. A WRITE claims no chip - see below. */
  rw: boolean
  spnreq: boolean
  spnChip: number
}

export interface ArbOut { gcpu: boolean[]; gspn: boolean[] }

/** graphics.md 5.2.1:
 *    GRANT_CPU[n]  = VREQ . R/W . (CPUCHIP == n)
 *    GRANT_SPAN[n] = SPNREQ . (SPNCHIP == n) . /GRANT_CPU[n]
 *  and SRCSEL[n] is GRANT_CPU[n], which is why it is not in this interface.
 *
 * ⛔ THE R/W LITERAL IS NEW ON 2026-09-10 and it is not a refinement - without
 * it the machine deadlocks on its first span. A CPU VRAM WRITE IS POSTED
 * (3.1.1) and needs no access of its own; claiming one makes the CPU's own
 * stalled write block the span writer that has to finish before /WAIT can
 * release it. access.jedec.ts has the loop written out, graphics.md 19 item 36
 * is the finding, and machine_tb is what could see it. */
export const arbitrate = (io: ArbIn): ArbOut => {
  const vreq = io.vramsel && io.nIopage === 1 && io.rw
  const gcpu = [0, 1, 2, 3].map((n) => vreq && io.cpuChip === n)
  return {
    gcpu,
    gspn: [0, 1, 2, 3].map((n) => io.spnreq && io.spnChip === n && !gcpu[n]),
  }
}

export const COLUMNS = 1024
export const RING_ROWS = 512

export interface Wptr { col: number; row: number }

/** The column wraps INSIDE the row and never carries. See access.check.ts:
 *  the column part has no eleventh macrocell to emit a carry from, and the
 *  display's own column counter wraps the same way. */
export const nextCol = (col: number, io: { lda: boolean; ldb: boolean; d: number; winc: boolean }) => {
  if (io.lda) return (col & 0x300) | (io.d & 0xff)
  if (io.ldb) return (col & 0x0ff) | ((io.d & 3) << 8)
  return io.winc ? (col + 1) % COLUMNS : col
}

export const nextRow = (row: number, io: { ldb: boolean; ldc: boolean; d: number; adv: boolean }) => {
  if (io.ldb) return (row & 0x1c0) | ((io.d >> 2) & 0x3f)
  if (io.ldc) return (row & 0x03f) | ((io.d & 7) << 6)
  return io.adv ? (row + 1) % RING_ROWS : row
}

export const pointer = (w: Wptr) => w.row * COLUMNS + w.col
