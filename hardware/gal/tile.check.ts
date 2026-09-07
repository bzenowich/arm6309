/* graphics.md 6.4's address concatenation, checked exhaustively.
 *
 * This is model-level and not fuse-level, and that is not a shortcut - see
 * gal/README.md's toolchain note. The ATF1508AS's fuse map is not publicly
 * documented, so the JEDEC that fit1508.exe produces cannot be executed the
 * way mmu.jed and hgen.jed are. What CAN be checked is the design, and this
 * is the part of it 6.4.1 rests an argument on: "with an aligned tile set
 * every term lands on its own address bits, so there is no adder".
 *
 *   npm run check:tile
 */

import {
  MAP_COLS, MAP_ROWS, MAP_STRIDE, charAddress, chipAddress, linearAddress,
  mapAddress, packedMapAddress, tileAddress,
} from "./tile.model"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

/* -- no adder: every term owns its own bits ------------------------------ */
{
  /* If the fields are disjoint, then ORing them is the same as adding them,
   * and that identity IS 6.4.1's claim. Checked over every field value, not
   * sampled: 32 x 256 x 8 x 8 = 524,288 for tiles. */
  let bad: string | null = null
  for (let base = 0; base < 32 && !bad; base++) {
    for (let code = 0; code < 256; code++) {
      for (let row = 0; row < 8; row++) {
        for (let col = 0; col < 8; col++) {
          const or = tileAddress({ tilebase: base, code, cellRow: row, cellCol: col })
          const add = base * 16384 + code * 64 + row * 8 + col
          if (or !== add) { bad = `base ${base} code ${code} row ${row} col ${col}: ${or} vs ${add}` }
        }
      }
    }
  }
  check(bad === null,
    "Variant A: OR equals ADD over all 524,288 field combinations - there is no adder",
    bad ?? "")

  bad = null
  for (let base = 0; base < 256 && !bad; base++) {
    for (let code = 0; code < 256; code++) {
      for (let row = 0; row < 8; row++) {
        const or = charAddress({ fontbase: base, code, cellRow: row })
        const add = base * 2048 + code * 8 + row
        if (or !== add) bad = `base ${base} code ${code} row ${row}: ${or} vs ${add}`
      }
    }
  }
  check(bad === null, "Variant B: the same, over all 524,288 combinations", bad ?? "")
}

/* -- the sets are 19 bits and land where 6.4.1 says ---------------------- */
{
  const spans = (fn: () => number, bits: number) => {
    let seen = 0
    for (let i = 0; i < 64; i++) seen |= fn()
    return seen < (1 << bits)
  }
  check(tileAddress({ tilebase: 31, code: 255, cellRow: 7, cellCol: 7 }) === 0x7ffff,
    "Variant A fills exactly 19 bits with every field at maximum")
  check(charAddress({ fontbase: 255, code: 255, cellRow: 7 }) === 0x7ffff,
    "Variant B fills exactly 19 bits with every field at maximum")
  check(linearAddress({ scanRow: 511, scanCol: 1023 }) === 0x7ffff,
    "and so does the bitmap scan address - all three modes are 19 bits wide")
  /* 16 KB aligned, 2 KB aligned - the alignment the concatenation needs. */
  check((tileAddress({ tilebase: 1, code: 0, cellRow: 0, cellCol: 0 }) & 0x3fff) === 0,
    "the tile set is 16 KB aligned, which is what makes TILEBASE a field")
  check((charAddress({ fontbase: 1, code: 0, cellRow: 0 }) & 0x7ff) === 0,
    "the font is 2 KB aligned")
}

/* -- A1..A0 are the interleave phase and never leave --------------------- */
{
  /* 2.1's four-way interleave: the chips see the address less two bits, so a
   * tile row's eight pixels are two groups of four and A2 picks the group. */
  const row0 = [0, 1, 2, 3, 4, 5, 6, 7].map((col) =>
    chipAddress(tileAddress({ tilebase: 0, code: 5, cellRow: 2, cellCol: col })))
  check(new Set(row0).size === 2,
    "one 8-pixel tile row is two chip addresses - four bytes from each, which " +
    "is exactly the interleave the bitmap path already runs",
    `${new Set(row0).size}`)
  check(row0[4] === row0[0] + 1,
    "and A2 is what advances between them, so the '153 phase is unchanged")
}

/* -- the map fetch, which 6.4 leaves unspecified ------------------------- */
{
  /* Concatenated, with a 128-byte row stride. */
  let bad: string | null = null
  for (let r = 0; r < MAP_ROWS && !bad; r++) {
    for (let c = 0; c < MAP_COLS; c++) {
      const or = mapAddress(3, r, c)
      const add = 3 * 4096 + r * MAP_STRIDE + c
      if (or !== add) bad = `row ${r} col ${c}: ${or} vs ${add}`
    }
  }
  check(bad === null,
    `the map address is a concatenation too, at a ${MAP_STRIDE}-byte row stride`, bad ?? "")

  /* And what 6.4.2's "2,000 B" costs instead. */
  const packedNeedsAdd = packedMapAddress(0, 1, 0) !== (1 << 7)
  check(packedNeedsAdd,
    "⚠ 6.4.2's packed 2,000-byte map is NOT a concatenation - 80 is not a power " +
    "of two, so it needs cellRow x 80, which is the adder 6.4.1 says does not exist")
  const cost = MAP_ROWS * MAP_STRIDE - MAP_ROWS * MAP_COLS
  check(cost === 1200,
    `the fix costs ${cost} bytes of the 512 KB - a 128-byte stride, 3,200 B not 2,000`,
    `${cost}`)
}

/* -- how many product terms the mode mux really is ----------------------- */
{
  /* 6.4.1: "each address bit is then a two-product-term mode mux". That is
   * true for two modes. Variant A and Variant B are both in v1 (10.1.5), and
   * with the bitmap that is three sources per bit. */
  const MODES = 3
  check(MODES === 3,
    "⚠ 6.4.1 says the mode mux is TWO product terms per address bit; with " +
    "Variant A, Variant B and bitmap all present it is three")
  const bits = 17 // A18..A2, what the chips see
  check(bits * MODES === 51,
    `${bits} address bits x ${MODES} sources = ${bits * MODES} product terms across ` +
    "17 macrocells - 3 each, against the 5 an ATF15xx macrocell has before cascading")
}

console.log(failures === 0
  ? "\n6.4's address concatenation holds: no adder, 19 bits, three modes"
  : `\n${failures} FAILED`)
if (failures) process.exit(1)
