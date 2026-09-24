/* Where the display fetches from, as arithmetic.
 *
 * The torus is 1024 x 512 (graphics.md 8) and the framebuffer is four
 * 128K x 8 parts in 4-way interleave (2.1), so the byte at row r, column c
 * lives at scan address r * 1024 + c, in chip c & 3, at chip address
 * (r * 1024 + c) >> 2 = r * 256 + (c >> 2).
 *
 * Nothing here is a counter or a product term: this says what address the
 * hardware must present, and scan.check.ts asks the fuses whether they
 * present it.
 */

export const COLUMNS = 1024
export const RING_ROWS = 512
export const CHIPS = 4

export interface ScanState { col: number; row: number }

/** Column counter: eight bits of a 1024-wide row, taken four at a time. */
export const nextCol = (col: number, io: { load: boolean; hscroll: number; fetch: boolean }) =>
  io.load ? (io.hscroll >> 2) & 0xff : io.fetch ? (col + 1) & 0xff : col

/** Row counter: nine bits, wrapping on the ring. */
export const nextRow = (row: number, io: { load: boolean; vscroll: number; adv: boolean }) =>
  io.load ? io.vscroll & 0x1ff : io.adv ? (row + 1) & 0x1ff : row

/** The chip address the four framebuffer parts should see. */
export const chipAddress = (s: ScanState) => s.row * (COLUMNS / CHIPS) + s.col

/** What the display should be fetching at slot `slot` of displayed line
 *  `line`, from the scroll registers - stated in pixels and rows, not in
 *  counter bits, so that the check compares against the geometry. */
export const expected = (
  line: number, slot: number, hscroll: number, vscroll: number, doubled: boolean,
) => {
  const row = (vscroll + (doubled ? line >> 1 : line)) % RING_ROWS
  const col = ((hscroll >> 2) + slot) % (COLUMNS / CHIPS)
  return { row, col, addr: row * (COLUMNS / CHIPS) + col }
}
