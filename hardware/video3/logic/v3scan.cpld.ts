/* v3scan - video3's scan and cell addresses, as an ATF1508AS.
 *
 * hardware/video3/docs/partition.md §2.2.  This is the part the partition is least sure
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

import { toCupl, type Merged } from "../../tools/gal/jedec/cupl"
import type { Cell } from "../../tools/gal/jedec/assemble"
import { BROADCAST, decodeCells, type RegName } from "./regmap"
import { loadable } from "../../tools/gal/jedec/counter"

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

/* ⭐ THE CADENCE, MADE HERE FROM THREE PINS. v3dot sends the dot phase and the
 * request for the current slot (MRQ); every strobe this part needs is a
 * product of the three, so FETCH, GMAP, MAPLD, MCADV and FBOESCAN are terms
 * rather than five pins - which is where the pin for nothing else came from.
 *   dots 0-1  the spare access (the map's, when MRQ); dots 2-3 the display's
 *   MAPLD     dot 1 of a map access: the word is on lanes 0 and 1
 *   MCADV     the tick that ends the slot AFTER a map access - MRQ2 is MRQ a
 *             slot late - where the tile fetch stops using the old code */
const cadence: Cell[] = [
  { pin: 0, name: "MRQ2", assertedLow: false, s0: 1, registered: true,
    terms: ["DP1 & DP0 & MRQ", "MRQ2 & !DP1", "MRQ2 & !DP0"] },
  { pin: 0, name: "FETCH", assertedLow: false, s0: 1, registered: false, terms: ["DP1 & DP0"] },
  { pin: 0, name: "GMAP", assertedLow: false, s0: 1, registered: false, terms: ["MRQ & !DP1"] },
  { pin: 0, name: "MAPLD", assertedLow: false, s0: 1, registered: false, terms: ["MRQ & !DP1 & DP0"] },
  { pin: 0, name: "MCADV", assertedLow: false, s0: 1, registered: false, terms: ["DP1 & DP0 & MRQ2"] },
  /* ⭐ the map column loads on HLOAD's FIRST dot, not its level: at HSCROLL[2]
   * = 1 the first map access is slot 31, inside HLOAD, and a level load would
   * undo the step that access makes (graphics.md §6.4.9's "HLOAD closes one
   * slot earlier", done with an edge instead of a narrower window) */
  { pin: 0, name: "HLQ", assertedLow: false, s0: 1, registered: true, terms: ["HLOAD"] },
  { pin: 0, name: "MCLD", assertedLow: false, s0: 1, registered: false, terms: ["HLOAD & !HLQ"] },
]

/* ⛔ THE MAP IS ON A FOUR-BYTE CELL STRIDE, because this part can read ONE
 * of the two x16 framebuffer parts. PB and PA are part 0's data pins - lanes
 * 0 and 1 of the fetch group - and there are no pins for part 1's. On a
 * two-byte stride every odd cell's word was in part 1, where nothing could
 * read it (video3_card.v's GAP_4). So a cell is a group: code in lane 0,
 * attribute in lane 1, lanes 2 and 3 unused (plan §2.5). Tile mode's code is
 * lane 0 of the same layout. */
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
  /* ⭐ THE ATTRIBUTE NEEDS THREE STAGES, because it is used two slots after
   * the code: the code addresses the tile fetch, the attribute meets the
   * pixel that fetch produces two slots later (rank A, then rank B). So MAPA
   * -> ATQ -> ATO, stepped together on the first dot of each map access -
   * before that access overwrites MAPA - and ATO changes on exactly the edge
   * the index '574 takes the cell's first pixel.
   * ⭐ AND ATO IS THE LUT's HIGH ADDRESS BYTE ITSELF: these registers drive
   * A15..A8 through their own output enable (ATOE, v3dot's), so the ATTR
   * '574 plan §13.1 listed is not on the board. The sprite has its own two
   * lines now (v3dot's SPRA), which left the latch carrying character mode
   * alone - and it was the package the lane transceivers needed.
   * ⛔ It was two stages on MCADV into a latch clocked every dot: every cell's
   * colour two slots early, half on the cell before. */
  ...[0, 1, 2, 3, 4, 5, 6, 7].map((b) => ({
    pin: 0, name: `ATQ${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`GMAP & !DP0 & MAPA${b}`, `ATQ${b} & !GMAP`, `ATQ${b} & DP0`],
  })),
  ...[0, 1, 2, 3, 4, 5, 6, 7].map((b) => ({
    pin: 0, name: `ATO${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`GMAP & !DP0 & ATQ${b}`, `ATO${b} & !GMAP`, `ATO${b} & DP0`],
    oe: "ATOE",
  })),
]

/* -- the map's own column counter, one cell ahead (graphics.md §6.4.1) ----
 *
 * "One ahead" costs a counter, not an adder: addressing cell N while the scan
 * address names N-1 means SA + 1, and §6.4.1's whole argument is that there is
 * no adder on this card. */
const MC = [0, 1, 2, 3, 4, 5, 6].map((b) => `MC${b}`)
/* ⭐ It steps on MAPLD - after each access - so it names the next cell to
 * fetch whatever the phase, and loads from HSCROLL[9:3] (zero in character
 * mode, which has no scroll) on HLOAD's first dot. */
const mapColumn: Cell[] = MC.map((name, i) => ({
  pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
  terms: loadable(MC, "MAPLD", "MCLD", [3, 4, 5, 6, 7, 8, 9].map((b) => `HS${b} & !MODE0`))[i],
}))

/* -- ⭐ THE ADDRESS BUS: three sources, and an output enable ----------------
 *
 *   GMAP MODE
 *    0    00  the bitmap scan address          SA18..SA2
 *    0  01/10 the cell/tile concatenation      TILEBASE | code | row | col
 *    1    --  the map fetch                    MAPBASE | cell row | cell column
 *
 * ⛔ SRC0 AND SRC1 WERE INPUTS NOTHING PRODUCED, and check:reach first filed
 * them as an ALIAS of v3dot's MUXSEL0/MUXSEL1. They are not: MUXSEL is the dot
 * phase driving the pixel '153, and this is the ADDRESS source. So:
 *   - SRC1 IS THE MAP GRANT. v3scan drives the bus in the display half of the
 *     slot and for a granted map fetch (FBOESCAN = !SPARE # GMAP), so "is this
 *     the map" is exactly GMAP, which v3dot already exports.
 *   - SRC0 IS THE MODE, decoded here. The map grant takes priority, so the
 *     other two sources only have to tell bitmap from cell modes - and MODE0
 *     and MODE1 are already v3dot externals. ⚠ A SRC0 cell on v3dot was the
 *     first try: it fitted as `v3dot_src` and refused as `v3dot`, CLAUDE.md's
 *     file-name trap, so the build did not change on it. Here it costs one
 *     more pin (v3scan 64/64) and one more term a bit, and v3dot not a byte.
 *
 * partition.md §1: v3ptr drives the same seventeen nets for WPTR and CPTR, and
 * FBOESCAN (here) and FBOEPTR (there) keep exactly one on the bus.  ⛔ The grant that
 * decides it is ONE signal from ONE place - v3dot's arbiter - and never an
 * agreement between two parts. */
const tileSrc = (bit: number) =>
  bit >= 14 ? `TB${bit - 14}` : bit >= 6 ? `MAPQ${bit - 6}` : bit >= 3 ? `SA${bit + 7}` : "SA2"
/* §2.5's concatenation: MAPBASE A18..A16, cell row A15..A10, pad A9..A8,
 * cell column A7..A1, byte A0.  A0 and A1 are below this bus (the ×16 parts'
 * byte enables), so the mux carries the cell column from A2 up. */
/* §2.5's map address on the four-byte stride: MAPBASE A18..A16, cell row
 * A15..A10, pad A9, cell column A8..A2 - and lanes 0 and 1 are the word. */
const mapSrc = (bit: number) =>
  bit >= 16 ? `MB${bit - 16}` : bit >= 10 ? `SA${bit + 3}` : bit === 9 ? "GND" : `MC${bit - 2}`
/* ⭐ the sprite's row fetch, in bitmap mode: the top 64 bytes of MAPBASE's
 * region, {MB, all ones}, and v3dot drives the row onto FBA5..FBA2 */
const sprSrc = (bit: number) => (bit >= 16 ? `MB${bit - 16}` : "VCC")

const addressMux: Cell[] = [...Array(17).keys()].map((i) => {
  const bit = i + 2
  return {
    pin: 0, name: `FBA${bit}`, assertedLow: false, s0: 1 as const, registered: false,
    terms: [
      `!GMAP & !MODE0 & !MODE1 & SA${bit}`,
      `!GMAP & MODE0 & ${tileSrc(bit)}`,
      `!GMAP & MODE1 & ${tileSrc(bit)}`,
      `GMAP & MODE0 & ${mapSrc(bit)}`,
      `GMAP & MODE1 & ${mapSrc(bit)}`,
      ...(bit >= 6 ? [`GMAP & !MODE0 & !MODE1 & ${sprSrc(bit)}`] : []),
    ].filter((t) => !t.includes("GND")).map((t) => t.replace(" & VCC", "")),
    /* the display half is DP1; the spare half only for a map access - and
     * FBA5..FBA2 not for the sprite's, which are v3dot's row */
    oe: bit >= 6 ? "DP1 # MRQ" : "DP1 # MRQ & MODE0 # MRQ & MODE1",
  }
})

/* scan.jedec.ts's hadr and vadr, inherited whole (plan §11: Required).  No
 * terminal count and no inter-package carry: the torus is 1024 x 512, so each
 * counter's own binary rollover IS the wrap. */
const SA_COL = [2, 3, 4, 5, 6, 7, 8, 9].map((b) => `SA${b}`)
/* ⛔ character mode has no scroll in either axis (plan §2.5), so the loads
 * see zero there whatever the registers hold */
const HS_COL = [2, 3, 4, 5, 6, 7, 8, 9].map((b) => `HS${b} & !MODE0`)
const SA_ROW = [10, 11, 12, 13, 14, 15, 16, 17, 18].map((b) => `SA${b}`)
const VS_ROW = [0, 1, 2, 3, 4, 5, 6, 7, 8].map((b) => `VS${b} & !MODE0`)

/* the offsets this part answers to.  LDHSL is also decoded on v3dot - the
 * broadcast makes a shared register free, where a strobe made it a fan-out. */
const MY_REGS: RegName[] = ["LDHSL", "LDHSH", "LDVSL", "LDVSH", "LDTB", "LDMB"]

export const v3scan: Merged = {
  name: "v3scan",
  partNo: "ARM6309-V3S",
  location: "video3 - scan and cell addresses",
  device: "f1508ispplcc84",
  clock: "CLK25",
  inputs: [
    { name: "CLK25" }, { name: "RESET", activeLow: true },
    /* the cadence, from v3dot (signals.md §3) */
    { name: "DP0" }, { name: "DP1" }, { name: "MRQ" },
    { name: "HLOAD" }, { name: "VBLANK" }, { name: "ROWADV" },
    { name: "MODE0" }, { name: "MODE1" }, { name: "ATOE" },
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
    /* ⭐ the register broadcast, decoded HERE (partition.md §3).  Six lines
     * carry all 30 offsets; the six strobes this part used to take were six
     * pins on v3host too, and that part had none to spare. */
    ...BROADCAST.map((n) => ({ name: n })),
  ],
  cells: [
    ...decodeCells(MY_REGS),
    ...cadence,
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
      terms: loadable(SA_ROW, "ROWADV", "VBLANK", VS_ROW)[i],
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
