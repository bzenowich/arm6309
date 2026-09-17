/* v3scan - video3's scan and cell addresses, as an ATF1508AS.
 *
 * video3/docs/partition.md §2.2.  This is the part the partition is least sure
 * of: ~108 macrocells ESTIMATED against 128, with a third of it in the map
 * word's two-stage pipeline.  Fitting it first is what turns plan §14 item 4
 * from an estimate into a number.
 *
 * WHAT IT HOLDS
 *   HSCROLL[9:2], VSCROLL[8:0]      the scroll registers (§8.1)
 *   the column counter A9..A2       scan.jedec.ts's hadr
 *   the row counter   A18..A10      scan.jedec.ts's vadr
 *   MC6..MC0                        the map's own column counter, one cell ahead
 *   TILEBASE, MAPBASE               §2.5's concatenation bases
 *   MAP/MAPQ                        ⚠ THIRTY-TWO bits: video3's map is a WORD
 *   FBA18..FBA2                     the address bus, THREE sources, tri-stated
 *
 * ⭐ WHAT IT DOES NOT HOLD, AND WHY THAT MATTERS.  `video`'s vaddr carries WPTR
 * and the list engine as well, so its address mux is FOUR sources with one
 * spare and graphics.md §10.1.6.2 records fits that ran out at exactly that
 * point.  video3 tri-states FBA between this part and v3ptr (partition.md §1),
 * so the pointers are not here - and this mux is THREE sources, not five.
 * Halving the fan-in is the reason the tri-state is the partition rather than a
 * workaround for it.
 */

import { toCupl, type Merged } from "../jedec/cupl"
import type { Cell } from "../jedec/assemble"
import { loadable } from "../jedec/counter"

/* -- the scroll registers ------------------------------------------------
 *
 * ⚠ HSCROLL[1:0] IS NOT HERE.  signals.md §3.4: its two consumers - the fetch
 * rank enables and the dot phase - are v3dot's, so those two bits are
 * DUPLICATED there rather than routed.  graphics.md §8.2 hit the same thing and
 * went the same way.  What this part needs is HSCROLL[9:2], which is what
 * preloads the column counter. */
const scrollHolds: Cell[] = [
  ...[2, 3, 4, 5, 6, 7, 8, 9].map((b) => ({
    pin: 0, name: `HS${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`LDHS${b < 8 ? "L" : "H"} & D${b < 8 ? b : b - 8}`, `HS${b} & !LDHS${b < 8 ? "L" : "H"}`],
  })),
  ...[0, 1, 2, 3, 4, 5, 6, 7, 8].map((b) => ({
    pin: 0, name: `VS${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`LDVS${b < 8 ? "L" : "H"} & D${b < 8 ? b : b - 8}`, `VS${b} & !LDVS${b < 8 ? "L" : "H"}`],
  })),
]

/* -- the bases.  §2.5: MAPBASE is THREE bits, not seven - the map's stride is a
 * whole VRAM row, so a map region is 64 KB and 512 KB holds eight of them. */
const bases: Cell[] = [
  ...[0, 1, 2, 3, 4].map((b) => ({
    pin: 0, name: `TB${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`LDTB & D${b}`, `TB${b} & !LDTB`],
  })),
  ...[0, 1, 2].map((b) => ({
    pin: 0, name: `MB${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`LDMB & D${b}`, `MB${b} & !LDMB`],
  })),
]

/* -- ⚠ THE MAP WORD, and this is what makes the part tight.
 *
 * graphics.md §6.4.9's two-stage pipeline, doubled: video3's map is a code byte
 * AND an attribute byte (plan §2.2), and both need the same handover, because
 * the spare access fetches cell N+1 while the display is still using cell N.
 * One ×16 access carries both, so MAPLD latches sixteen bits at once. */
/* ⭐ V3_MAPQ=discrete moves the whole map pipeline into four '574 on the pixel
 * bus (plan §13.4).  It is a switch and not a comment because BOTH sides are
 * fitted: it is the escape partition.md §5 risk 2 is plumbed to, and the fit is
 * the only thing that says what it is worth. */
export const MAPQ_DISCRETE = process.env.V3_MAPQ === "discrete"

const mapWord: Cell[] = MAPQ_DISCRETE ? [] : [
  ...[0, 1, 2, 3, 4, 5, 6, 7].map((b) => ({
    pin: 0, name: `MAP${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`MAPLD & PB${b}`, `MAP${b} & !MAPLD`],
  })),
  ...[0, 1, 2, 3, 4, 5, 6, 7].map((b) => ({
    pin: 0, name: `MAPA${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`MAPLD & PA${b}`, `MAPA${b} & !MAPLD`],
  })),
  ...[0, 1, 2, 3, 4, 5, 6, 7].map((b) => ({
    pin: 0, name: `MAPQ${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`MCADV & MAP${b}`, `MAPQ${b} & !MCADV`],
  })),
  /* ⭐ the attribute's second stage is the one that leaves the part - it drives
   * the ATTR latch's input (plan §3), which is the only 8-bit bus out of here. */
  ...[0, 1, 2, 3, 4, 5, 6, 7].map((b) => ({
    pin: 0, name: `ATO${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`MCADV & MAPA${b}`, `ATO${b} & !MCADV`],
  })),
]

/* -- the map's own column counter, one cell ahead (graphics.md §6.4.1) ----
 *
 * "One ahead" costs a counter, not an adder: addressing cell N while the scan
 * address names N-1 means SA + 1, and §6.4.1's whole argument is that there is
 * no adder on this card. */
const MC = [0, 1, 2, 3, 4, 5, 6].map((b) => `MC${b}`)
const mapColumn: Cell[] = MC.map((name, i) => ({
  pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
  terms: loadable(MC, "MCADV", "HLOAD", [3, 4, 5, 6, 7, 8, 9].map((b) => `HS${b}`))[i],
}))

/* -- ⭐ THE ADDRESS BUS: three sources, and an output enable ----------------
 *
 *   00  the bitmap scan address          SA18..SA2
 *   01  the cell/tile concatenation      TILEBASE | code | row | col
 *   10  the map fetch                    MAPBASE | cell row | cell column
 *
 * partition.md §1: v3ptr drives the same seventeen nets for WPTR and CPTR, and
 * FBOE is what keeps exactly one of the two parts on the bus.  ⛔ The grant that
 * decides it is ONE signal from ONE place - v3dot's arbiter - and never an
 * agreement between two parts. */
const tileSrc = (bit: number) =>
  bit >= 14 ? `TB${bit - 14}` : bit >= 6 ? `MAPQ${bit - 6}` : bit >= 3 ? `SA${bit + 7}` : "SA2"
/* §2.5's concatenation: MAPBASE A18..A16, cell row A15..A10, pad A9..A8,
 * cell column A7..A1, byte A0.  A0 and A1 are below this bus (the ×16 parts'
 * byte enables), so the mux carries the cell column from A2 up. */
const mapSrc = (bit: number) =>
  bit >= 16 ? `MB${bit - 16}` : bit >= 10 ? `SA${bit + 3}` : bit >= 8 ? "GND" : `MC${bit - 1}`

const addressMux: Cell[] = [...Array(17).keys()].map((i) => {
  const bit = i + 2
  return {
    pin: 0, name: `FBA${bit}`, assertedLow: false, s0: 1 as const, registered: false,
    terms: [
      `!SRC1 & !SRC0 & SA${bit}`,
      `!SRC1 &  SRC0 & ${tileSrc(bit)}`,
      ` SRC1 & !SRC0 & ${mapSrc(bit)}`,
    ].filter((t) => !t.includes("GND")),
    oe: "FBOE",
  }
})

/* scan.jedec.ts's hadr and vadr, inherited whole (plan §11: Required).  No
 * terminal count and no inter-package carry: the torus is 1024 x 512, so each
 * counter's own binary rollover IS the wrap. */
const SA_COL = [2, 3, 4, 5, 6, 7, 8, 9].map((b) => `SA${b}`)
const HS_COL = [2, 3, 4, 5, 6, 7, 8, 9].map((b) => `HS${b}`)
const SA_ROW = [10, 11, 12, 13, 14, 15, 16, 17, 18].map((b) => `SA${b}`)
const VS_ROW = [0, 1, 2, 3, 4, 5, 6, 7, 8].map((b) => `VS${b}`)

export const v3scan: Merged = {
  name: "v3scan",
  partNo: "ARM6309-V3S",
  location: "video3 - scan and cell addresses",
  device: "f1508ispplcc84",
  clock: "CLK25",
  inputs: [
    { name: "CLK25" }, { name: "RESET", activeLow: true },
    /* the cadence, from v3dot (signals.md §3) */
    { name: "FETCH" }, { name: "HLOAD" }, { name: "VLOAD" }, { name: "ROWADV" },
    { name: "MCADV" }, { name: "MAPLD" }, { name: "SRC0" }, { name: "SRC1" },
    { name: "FBOE" },
    /* the card's internal data bus, for register writes */
    ...[0, 1, 2, 3, 4, 5, 6, 7].map((b) => ({ name: `D${b}` })),
    /* the pixel bus - a ×16 spare access delivers both map bytes at once.
     * ⭐ With the pipeline discrete, NEITHER half comes here: the code arrives
     * already staged as MAPQ, and the attribute goes straight to the ATTR latch
     * without touching this part at all. */
    ...(MAPQ_DISCRETE
      ? [0, 1, 2, 3, 4, 5, 6, 7].map((b) => ({ name: `MAPQ${b}` }))
      : [...[0, 1, 2, 3, 4, 5, 6, 7].map((b) => ({ name: `PB${b}` })),
         ...[0, 1, 2, 3, 4, 5, 6, 7].map((b) => ({ name: `PA${b}` }))]),
    /* register write strobes, decoded on v3host */
    { name: "LDHSL" }, { name: "LDHSH" }, { name: "LDVSL" }, { name: "LDVSH" },
    { name: "LDTB" }, { name: "LDMB" },
  ],
  cells: [
    ...scrollHolds,
    ...bases,
    ...mapWord,
    ...mapColumn,
    /* the column counter A9..A2 and the row counter A18..A10 - scan.jedec.ts's
     * hadr and vadr, which this part inherits whole (plan §11: Required). */
    ...SA_COL.map((name, i) => ({
      pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
      terms: loadable(SA_COL, "FETCH", "HLOAD", HS_COL)[i],
    })),
    ...SA_ROW.map((name, i) => ({
      pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
      terms: loadable(SA_ROW, "ROWADV", "VLOAD", VS_ROW)[i],
    })),
    ...addressMux,
  ],
  /* ⭐ ONLY TWO THINGS LEAVE THIS PART: the address bus, and the attribute byte
   * that feeds the ATTR latch (plan §3).  Everything else - every counter, every
   * scroll register, both map stages - the fitter may bury, which is the whole
   * argument of graphics.md §10.1.2: on GALs each of those cost a pin. */
  external: new Set([
    ...[...Array(17).keys()].map((i) => `FBA${i + 2}`),
    ...(MAPQ_DISCRETE ? [] : [0, 1, 2, 3, 4, 5, 6, 7].map((b) => `ATO${b}`)),
  ]),
}

if (import.meta.main) {
  const n = v3scan.cells.length
  console.log(`v3scan${MAPQ_DISCRETE ? " (MAPQ discrete)" : ""}: ${n} cells, ` +
              `${v3scan.inputs.length} declared inputs`)
  console.log(toCupl(v3scan))
}
