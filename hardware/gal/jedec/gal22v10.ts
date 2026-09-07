/* The GAL22V10 fuse map, as data.
 *
 * This is the file that decides whether the .jed we emit programs the part we
 * think it does, so its provenance matters more than its code. Every constant
 * below is corroborated by two independent sources:
 *
 *   1. reference/datasheets/ATF22V10C.pdf. Section 10's compiler-mode table
 *      gives 5828 fuses (PAL mode), 5892 (GAL mode) and 5893 (power-down).
 *      Section 11's functional logic diagram, page 10, draws the array: 44
 *      columns labelled "INPUT LINES 0..43", one AR row at the top, then ten
 *      groups each of one OE row and 8/10/12/14/16/16/14/12/10/8 term rows,
 *      then SP. 132 x 44 = 5808, + 20 config + 64 signature = 5892 exactly.
 *
 *   2. galette (github.com/simon-frankau/galette), src/chips.rs and src/gal.rs
 *      - a GAL assembler that has programmed real parts. Its GAL22V10_DATA,
 *      OLMC_ROWS_22V10, OLMC_SIZE_22V10 and PIN_TO_COL_22V10 tables agree with
 *      the datasheet reading in every entry.
 *
 * WHAT IS STILL AN ASSUMPTION. The column map and the meaning of the two
 * config bits cannot be derived from first principles - they are conventions
 * of the silicon. Two sources agreeing is good evidence and is not proof. The
 * decisive test is to compile one .pld with CUPL or galette and diff the fuse
 * array against ours; see jedec/README.md. Until that is done, everything
 * downstream of this file is self-consistent rather than verified.
 *
 * FUSE POLARITY, which is the one that bites: 0 = link intact = the signal IS
 * connected to that product term. 1 = erased = not connected. So a row of all
 * zeros is permanently FALSE (every signal ANDed with its own complement) and
 * a row of all ones is permanently TRUE (the AND of nothing). Unused product
 * terms are therefore all-zero rows, and a permanently enabled output has an
 * all-one OE row.
 */

export const COLS = 44
export const ROWS = 132

export const ARRAY_FUSES = ROWS * COLS // 5808
export const CONFIG_BASE = ARRAY_FUSES // 5808..5827, S0/S1 interleaved
export const SIG_BASE = CONFIG_BASE + 20 // 5828..5891, the 64-bit UES
export const TOTAL_FUSES = SIG_BASE + 64 // 5892 - "GAL mode" in the datasheet

export const AR_ROW = 0
export const SP_ROW = ROWS - 1

export const CLOCK_PIN = 1
export const GND_PIN = 12
export const VCC_PIN = 24
export const FIRST_OLMC_PIN = 14
export const LAST_OLMC_PIN = 23

/* Pin -> the EVEN column of its true/complement pair. Column c is the signal
 * itself, column c+1 its complement (galette's set_and adds 1 for negation;
 * the GAL16V8 example in reference/articles/gal.html shows the same, with the
 * two "high" connections landing on even columns). Pins 12 and 24 are GND and
 * VCC and have no column. */
export const PIN_COL: Readonly<Record<number, number>> = {
  1: 0, 2: 4, 3: 8, 4: 12, 5: 16, 6: 20, 7: 24, 8: 28, 9: 32, 10: 36, 11: 40,
  13: 42,
  23: 2, 22: 6, 21: 10, 20: 14, 19: 18, 18: 22, 17: 26, 16: 30, 15: 34, 14: 38,
}

/* Column -> the pin it belongs to, and whether it is the complement. */
export const COL_PIN: number[] = []
export const COL_NEG: boolean[] = []
for (const [pin, col] of Object.entries(PIN_COL)) {
  COL_PIN[col] = Number(pin); COL_NEG[col] = false
  COL_PIN[col + 1] = Number(pin); COL_NEG[col + 1] = true
}

/* Macrocell row allocation. Index is pin - 14; each group is one OE row
 * followed by that macrocell's product-term rows. The term counts are the
 * palindrome the pin placement in clkdec.pld depends on. */
const OLMC_START = [122, 111, 98, 83, 66, 49, 34, 21, 10, 1]
const OLMC_ROWS = [9, 11, 13, 15, 17, 17, 15, 13, 11, 9] // includes the OE row

export interface Macrocell {
  pin: number
  oeRow: number
  firstRow: number
  terms: number
}

export const OLMC: Readonly<Record<number, Macrocell>> = Object.fromEntries(
  OLMC_START.map((start, i) => [
    FIRST_OLMC_PIN + i,
    { pin: FIRST_OLMC_PIN + i, oeRow: start, firstRow: start + 1, terms: OLMC_ROWS[i] - 1 },
  ]),
)

export const OLMC_PINS = Object.values(OLMC).map((m) => m.pin).sort((a, b) => a - b)

/* S0 is the polarity bit: 1 = the pin follows the sum of products, 0 = the pin
 * is its complement. S1 selects the path: 0 = registered, 1 = combinational
 * (galette stores S1 as 'ac1' and reads `registered = !ac1`). They interleave,
 * S0 then S1.
 *
 * ⚠ THE ORDER RUNS FROM PIN 23 DOWNWARD, and this was wrong here until
 * 2026-09-07. It was written pin-14-upward, which is the natural reading of
 * galette's `xor[]` array - but galette fills that array with
 * `xor[num_olmcs - 1 - i]`, and the inversion means index 0 is the LAST
 * macrocell, not the first.
 *
 * Nothing in this repository could catch it. The assembler and the fuse-map
 * simulator share this file, so both put the polarity bits in the same wrong
 * places and agreed with each other perfectly; every check passed. It took
 * compiling mmu.pld with Atmel's own CUPL and finding that CUPL's JEDEC only
 * evaluates correctly under the other order - which is exactly the
 * falsification test jedec/README.md named as "the one that would settle it"
 * and listed as not done. */
export const s0Fuse = (pin: number) => CONFIG_BASE + 2 * (LAST_OLMC_PIN - pin)
export const s1Fuse = (pin: number) => CONFIG_BASE + 2 * (LAST_OLMC_PIN - pin) + 1

/* -- the map has to be self-consistent before anything else can be true ---- */
{
  const covered = new Set<number>([AR_ROW, SP_ROW])
  for (const m of Object.values(OLMC)) {
    covered.add(m.oeRow)
    for (let r = m.firstRow; r < m.firstRow + m.terms; r++) covered.add(r)
  }
  if (covered.size !== ROWS) {
    throw new Error(`row map covers ${covered.size} of ${ROWS} rows`)
  }
  if (Object.keys(PIN_COL).length * 2 !== COLS) {
    throw new Error(`column map covers ${Object.keys(PIN_COL).length * 2} of ${COLS} columns`)
  }
  const cols = new Set(Object.values(PIN_COL))
  if (cols.size !== 22) throw new Error("two pins share a column")
}
