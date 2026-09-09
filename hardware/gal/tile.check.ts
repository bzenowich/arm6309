/* graphics.md 6.4's address concatenation, checked exhaustively.
 *
 * ⚠ TWO OF THE THREE MODES ARE BUILT. Variant B - 6.4.3's 1bpp character
 * generator - was dropped on 2026-09-08 to afford 10.3's list engine, and its
 * claims below are marked. The model is kept deliberately: it is what a
 * rebuild would need, and it is also the evidence that the mode was costed
 * rather than waved away.
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
import { addressMux, mapColumn } from "./video.parts"

/* ⭐ THE FOUR MUX SELECTS ARE TWO ENCODED BITS since 2026-09-09 - SRC1:SRC0,
 * video.parts.ts - so a term's guard is a pair of literals rather than one.
 * 00 linear, 01 the write pointer, 10 tile, 11 map. graphics.md 14.1: two
 * crossing nets instead of four, and it is what bought vctrl the room for
 * everything docs/design-review2.md V-1 found missing. */
const TILE = "SRC1 & !SRC0"
const MAP = "SRC1 & SRC0"

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
  /* ⚠ Variant B is MODELLED AND NOT BUILT since 2026-09-08 - graphics.md
   * 6.4.3 and 10.1.6.2. It was dropped to afford §10.3's list engine, and the
   * model stays because the retreat is real: the concatenation is what a
   * rebuild would need, and nothing about it has been shown wrong. */
  check(bad === null,
    "Variant B (NOT BUILT - 6.4.3): the same, over all 524,288 combinations", bad ?? "")
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
    "Variant B (NOT BUILT) fills exactly 19 bits with every field at maximum")
  check(linearAddress({ scanRow: 511, scanCol: 1023 }) === 0x7ffff,
    "and so does the bitmap scan address - all three modes are 19 bits wide")
  /* 16 KB aligned, 2 KB aligned - the alignment the concatenation needs. */
  check((tileAddress({ tilebase: 1, code: 0, cellRow: 0, cellCol: 0 }) & 0x3fff) === 0,
    "the tile set is 16 KB aligned, which is what makes TILEBASE a field")
  check((charAddress({ fontbase: 1, code: 0, cellRow: 0 }) & 0x7ff) === 0,
    "the font is 2 KB aligned (Variant B, NOT BUILT)")
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
   * true for two modes, and the built mux has more sources than modes: the
   * write pointer and the map fetch are two of them.
   *
   * ⚠ COUNTED FROM addressMux() RATHER THAN ASSERTED AS A CONSTANT, because
   * this number decided whether the display list fits. Five sources is what an
   * ATF15xx macrocell holds before cascading, and the mux was AT five with
   * Variant B in - so 10.3's engine wanting a sixth for its own pointer is why
   * 10.1.6.2's first fit returned INTERNAL ERROR rather than an overflow.
   * Dropping Variant B and sharing WPTR are both subtractions here. */
  const mux = addressMux()
  const bits = 17 // A18..A2, what the chips see
  check(mux.length === bits, `the mux is ${bits} bits - A18..A2, not A18..A0`,
    `${mux.length}`)
  const sources = new Set(mux.map((c) => c.terms.length))
  check(sources.size === 1, "every address bit has the same number of sources",
    [...sources].join(","))
  const n = mux[0]!.terms.length
  check(n <= 5,
    `${bits} address bits x ${n} sources = ${bits * n} product terms across ` +
    "17 macrocells - within the 5 an ATF15xx macrocell has before cascading",
    `${n}`)
  check(!mux.some((c) => c.terms.some((t) => t.startsWith("CHARSEL"))),
    "Variant B's CHARSEL is not a mux source - 6.4.3, dropped 2026-09-08")
  check(!mux.some((c) => c.terms.some((t) => /^LGRANT/.test(t))),
    "and the list engine is not one either - it shares WPTR (10.1.6.2 option 2)")
}

/* -- the fitted mux computes the modelled address ------------------------ *
 *
 * ⚠ THIS IS THE ASSERTION THAT DID NOT EXIST UNTIL 2026-09-08, and its absence
 * is why video.parts.ts spent a day computing a different map address from the
 * one tile.model.ts and 6.4.1 specify. The file already imported addressMux -
 * to COUNT its product terms - and never evaluated it. Counting a mux does not
 * check what it computes.
 *
 * The method: every mux term is `SELECT & SOURCE`, and every source is one bit
 * of one field. Give the fields values, build the counters those sources are
 * bits of, and read the address back out of the terms. If the design and the
 * model disagree anywhere, they disagree here.
 */
{
  const mux = addressMux()
  const named = (cells: { name: string; terms: string[] }[], n: string) =>
    cells.find((c) => c.name === n)?.terms[0] ?? ""

  /* SA is the 19-bit scan address: SA9..SA0 the pixel column, SA18..SA10 the
   * row (tile.model.ts's linearAddress). The cell fields are those counters
   * divided by eight, so a cell position plus a position inside it is one SA. */
  const scan = (cellRow: number, rowIn: number, cellCol: number, colIn: number) =>
    ((cellRow * 8 + rowIn) << 10) | (cellCol * 8 + colIn)

  /* Every source the mux is allowed to name, as a bit of something. */
  const value = (src: string, f: {
    sa: number; mapbase: number; tilebase: number; code: number; mc: number
  }): number => {
    const m = /^([A-Z]+)(\d+)$/.exec(src)
    if (!m) return -1
    const [, field, idx] = m as unknown as [string, string, string]
    const bit = Number(idx)
    switch (field) {
      case "SA": return (f.sa >>> bit) & 1
      /* The map's own cell column, one cell ahead of SA - see mapColumn. Its
       * VALUE for a given screen cell is that cell's column either way; what
       * changed on 2026-09-08 is which counter carries it. */
      case "MC": return (f.mc >>> bit) & 1
      case "MB": return (f.mapbase >>> bit) & 1
      case "TB": return (f.tilebase >>> bit) & 1
      case "MAP": return (f.code >>> bit) & 1
      /* ⭐ MAPQ is the map byte's SECOND rank, 2026-09-09. MAP is the fetch
       * target and MAPQ is what this mux reads, handed over at the cell
       * boundary - one register could not hold a code across the two slots
       * that need it while a new one arrived in the middle, and the card
       * displayed every cell's right-hand neighbour. Its VALUE for a given
       * screen cell is that cell's code either way, which is why this check
       * did not see the defect. docs/design-review2.md V-5. */
      case "MAPQ": return (f.code >>> bit) & 1
      /* NOT a throw: an unknown source is a FAILING check, not a crash, or a
       * regression takes the rest of the file down with it. */
      default: return -1
    }
  }

  /* Read A18..A2 out of the terms guarded by one select, then put back the two
   * bits the mux does not carry. */
  const assemble = (select: string, low: number, f: {
    sa: number; mapbase: number; tilebase: number; code: number; mc: number
  }) => {
    let addr = low & 3
    for (const cell of mux) {
      const bit = Number(/^FBA(\d+)$/.exec(cell.name)![1])
      const term = cell.terms.find((t) => t.startsWith(`${select} & `))
      if (!term) return -1
      const v = value(term.slice(select.length + 3), f)
      if (v < 0) return -1
      addr |= v << bit
    }
    return addr
  }

  /* -- neither of them reads the sync counter, checked FIRST ------------- */
  {
    /* V is measured from the leading edge of VSYNC (sync.timing.ts), so it is
     * 37 or 35 at the top of active video depending on the family - never 0,
     * and not the same in both modes. vadr's SA is loaded from VSCROLL at
     * vblank and stepped once per displayed row, so it is. Any V in a cell-mode
     * term is the bug of 2026-09-08 coming back. */
    const cellTerms = mux.flatMap((c) =>
      c.terms.filter((t) => t.startsWith(`${TILE} & `) || t.startsWith(`${MAP} & `)))
    const usesV = cellTerms.filter((t) => /\bV\d+$/.test(t))
    check(usesV.length === 0,
      "no cell-mode address bit reads the sync line counter V - the vertical " +
      "fields are vadr's row counter, which is zero-based and VSCROLL-offset",
      usesV.join(" "))
  }

  /* -- the map fetch ----------------------------------------------------- */
  {
    /* A1..A0 are not the pixel phase for this fetch: they are cellCol[1:0],
     * which the design names MAPA1/MAPA0 so the arbiter can be told which chip
     * to grant. Same identity as SPNA[1:0] = WPTR[1:0]. */
    const mapa = [named(mapColumn, "MAPA0"), named(mapColumn, "MAPA1")]
    check(mapa[0] === "MC0" && mapa[1] === "MC1",
      "MAPA1/MAPA0 are MC1/MC0 - cellCol[1:0] off the map's own counter, the " +
      "chip the map byte lives on", mapa.join(","))

    let bad: string | null = null
    for (let r = 0; r < MAP_ROWS && !bad; r++) {
      for (let c = 0; c < MAP_COLS && !bad; c++) {
        /* The map byte must be the same for every one of the cell's 64 pixels,
         * so sweep the position INSIDE the cell as well and demand it does not
         * move. The transposed version failed exactly here. */
        for (let ri = 0; ri < 8 && !bad; ri++) {
          for (let ci = 0; ci < 8; ci++) {
            const sa = scan(r, ri, c, ci)
            const f = { sa, mapbase: 0x5b, tilebase: 0, code: 0, mc: c }
            const low = c & 3
            const got = assemble(MAP, low, f)
            const want = mapAddress(0x5b, r, c)
            if (got !== want) {
              bad = `cell (${r},${c}) pixel (${ri},${ci}): mux ${got} vs model ${want}`
              break
            }
          }
        }
      }
    }
    check(bad === null,
      "the fitted map mux computes tile.model.ts's mapAddress for all 25 x 80 " +
      "cells, and does not move within a cell", bad ?? "")
  }

  /* -- the tile fetch ---------------------------------------------------- */
  {
    /* Mirror image: the tile address depends on the CODE and the position
     * inside the cell, and must not depend on where the cell sits on screen.
     * A1..A0 are col[1:0] here, which IS the pixel phase - so the tile fetch
     * needs no chip name and rides the ordinary display path. */
    let bad: string | null = null
    for (let code = 0; code < 256 && !bad; code++) {
      for (let ri = 0; ri < 8 && !bad; ri++) {
        for (let ci = 0; ci < 8 && !bad; ci++) {
          for (const [r, c] of [[0, 0], [24, 79], [13, 41]] as [number, number][]) {
            const sa = scan(r, ri, c, ci)
            const f = { sa, mapbase: 0, tilebase: 0x1d, code }
            const low = ci & 3
            const got = assemble(TILE, low, f)
            const want = tileAddress({ tilebase: 0x1d, code, cellRow: ri, cellCol: ci })
            if (got !== want) {
              bad = `code ${code} px (${ri},${ci}) at cell (${r},${c}): ` +
                `mux ${got} vs model ${want}`
              break
            }
          }
        }
      }
    }
    check(bad === null,
      "the fitted tile mux computes tileAddress for all 256 codes x 64 pixels, " +
      "and does not depend on where the cell is on screen", bad ?? "")
  }

}

/* -- 6.4.6 limit 2: cell mode scrolls in BOTH axes ----------------------- *
 *
 * The question this answers is "can a game scroll a tilemap", and it is a
 * question about the ADDRESS PATH ONLY - the fetch cadence that would drive it
 * is 19 item 15(c) and is not built. What is checked here is that for a given
 * (HSCROLL, VSCROLL) every displayed pixel resolves to the right cell of the
 * map and the right pixel of the right tile, wrapping at the ring.
 *
 * The model of the counters is 8's: the column counter holds HSCROLL[9:2] plus
 * the fetch progress and the mux phase carries HSCROLL[1:0], so the source
 * column for screen pixel x is (HSCROLL + x) mod 1024; vadr holds VSCROLL plus
 * the row progress, so the source row for screen line y is (VSCROLL + y) mod
 * 512. seqph.check.ts is what asserts the emitted byte sequence matches that
 * for every phase; this asserts the address does.
 */
{
  const mux = addressMux()
  const RING_COLS = 1024, RING_ROWS = 512
  const CELL = 8

  const srcOf = (hscroll: number, vscroll: number, x: number, y: number) => {
    const col = (hscroll + x) % RING_COLS
    const row = (vscroll + y) % RING_ROWS
    return { col, row, sa: (row << 10) | col }
  }

  /* Re-derived from the mux, not asserted as constants - same method as the
   * blocks above, so a bit that moves is caught here too. */
  const addrOf = (select: string, sa: number,
                  f: { mapbase: number; tilebase: number; code: number; mc: number },
                  low: number) => {
    let addr = low & 3
    for (const cell of mux) {
      const bit = Number(/^FBA(\d+)$/.exec(cell.name)![1])
      const term = cell.terms.find((t) => t.startsWith(`${select} & `))!
      const src = term.slice(select.length + 3)
      const m = /^([A-Z]+)(\d+)$/.exec(src)!
      const idx = Number(m[2])
      const v = m[1] === "SA" ? (sa >>> idx) & 1
        : m[1] === "MC" ? (f.mc >>> idx) & 1
        : m[1] === "MB" ? (f.mapbase >>> idx) & 1
        : m[1] === "TB" ? (f.tilebase >>> idx) & 1
        : (f.code >>> idx) & 1
      addr |= v << bit
    }
    return addr
  }

  /* 640x200, the mode 6.4.8 costs out. Four scroll positions: origin, a whole
   * cell in each axis, a sub-cell offset in each axis, and one that wraps both
   * rings. */
  const CASES: [number, number, string][] = [
    [0, 0, "origin"],
    [8, 8, "one whole cell in each axis"],
    [3, 5, "sub-cell in both axes - the fine-scroll case"],
    [1021, 253, "wrapping both rings"],
  ]
  const MAPBASE = 0x5b, TILEBASE = 0x1d

  let bad: string | null = null
  for (const [h, v, label] of CASES) {
    if (bad) break
    for (let y = 0; y < 200 && !bad; y += 7) {        /* 7 is coprime with 8 */
      for (let x = 0; x < 640; x += 3) {              /* and 3 with 8 and 4 */
        const { col, row, sa } = srcOf(h, v, x, y)
        /* What the display is asking for, straight from the scroll offsets. */
        const wantCellCol = (col >> 3) % 128
        const wantCellRow = (row >> 3) % 32
        const wantColIn = col % CELL
        const wantRowIn = row % CELL

        const gotMap = addrOf(MAP, sa,
          { mapbase: MAPBASE, tilebase: 0, code: 0, mc: wantCellCol }, wantCellCol & 3)
        if (gotMap !== mapAddress(MAPBASE, wantCellRow, wantCellCol)) {
          bad = `${label}: screen (${x},${y}) -> map cell (${wantCellRow},${wantCellCol}) ` +
            `but the mux addressed ${gotMap}`
          break
        }
        const code = 0xa7
        const gotTile = addrOf(TILE, sa,
          { mapbase: 0, tilebase: TILEBASE, code, mc: 0 }, col % 4)
        if (gotTile !== tileAddress({ tilebase: TILEBASE, code, cellRow: wantRowIn, cellCol: wantColIn })) {
          bad = `${label}: screen (${x},${y}) -> tile pixel (${wantRowIn},${wantColIn}) ` +
            `but the mux addressed ${gotTile}`
          break
        }
      }
    }
  }
  check(bad === null,
    "cell mode scrolls in BOTH axes: every displayed pixel resolves to the " +
    "right map cell and the right tile pixel, at whole-cell and sub-cell " +
    "offsets and across both ring wraps", bad ?? "")

  /* The two rings are not the same size, and a game has to know which. */
  {
    const colsSeen = new Set<number>(), rowsSeen = new Set<number>()
    for (let i = 0; i < 4096; i++) {
      const { col, row } = srcOf(0, 0, i % RING_COLS, 0)
      colsSeen.add((col >> 3) % 128)
      rowsSeen.add((srcOf(0, i, 0, 0).row >> 3) % 32)
    }
    check(colsSeen.size === 128,
      "the horizontal ring is 128 cells - 1024 px, the same torus the bitmap " +
      "scrolls on, so 80 displayed columns leave 48 cells of margin",
      `${colsSeen.size}`)
    check(rowsSeen.size === 32,
      "⚠ the VERTICAL ring is 32 cell rows - 256 px, HALF the bitmap's 512, " +
      "because the map address has no A18: 25 displayed rows leave SEVEN of " +
      "margin, not 39", `${rowsSeen.size}`)
  }

  /* Sub-cell scroll is the half that costs nothing, and it is worth saying
   * which bits carry it: 6.4.6 limit 2 claims {SA2, mux phase} horizontally
   * and SA12..SA10 vertically. */
  {
    const at = (h: number, v: number) => {
      const { col, row } = srcOf(h, v, 0, 0)
      return [col % CELL, row % CELL]
    }
    const offsets = [0, 1, 2, 3, 4, 5, 6, 7].map((k) => at(k, k))
    check(offsets.every(([c, r], k) => c === k && r === k),
      "sub-cell scroll is free in both axes: HSCROLL[2:0] is the pixel within " +
      "the cell row and VSCROLL[2:0] is the row within the cell, so VSCROLL += 1 " +
      "per frame is as smooth in cell mode as in bitmap mode")
  }
}

console.log(failures === 0
  ? "\n6.4's address concatenation holds: no adder, 19 bits, three modes (two built)"
  : `\n${failures} FAILED`)
if (failures) process.exit(1)
