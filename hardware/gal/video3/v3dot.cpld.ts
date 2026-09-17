/* v3dot - video3's raster, dot path, sprite and arbiter, as an ATF1508AS.
 *
 * video3/docs/partition.md §2.1.  The part everything else is timed from, and
 * the one the census expected to be pin-bound rather than cell-bound.
 *
 * ⭐ THREE PLACEMENTS HERE ARE NOT FREE CHOICES (partition.md §2.1):
 *   CTRL, because MODE and VMODE are consumed at dot rate and exporting two
 *     bits beats importing six;
 *   the arbiter, because it has the cadence and the cadence is the reference;
 *   PIXOE / ATOE / PIDXOE, because graphics.md §13.1's "one pin doing both
 *     halves so the pair can never be half-turned" becomes, with THREE masters
 *     on a sixteen-bit LUT address, ONE PART DECIDING ALL THREE.
 */

import { toCupl, type Merged } from "../jedec/cupl"
import type { Cell } from "../jedec/assemble"
import { counterTerms, loadable } from "../jedec/counter"

/* ⭐ partition.md §8's costed escape: the sprite's two shift registers as 2 x
 * '165 rather than sixteen macrocells.  A switch, not a comment - both sides
 * fitted, the way ARM6309_LIST is in gal/video.cpld.ts. */
export const SPRSHIFT_DISCRETE = (process.env.V3_SPRSHIFT ?? "discrete") === "discrete"

const reg = (name: string, terms: string[]): Cell =>
  ({ pin: 0, name, assertedLow: false, s0: 1 as const, registered: true, terms })
const comb = (name: string, terms: string[]): Cell =>
  ({ pin: 0, name, assertedLow: false, s0: 1 as const, registered: false, terms })

/* -- the horizontal counter: 800 dots as 200 slots of four ----------------
 *
 * sync.timing.ts puts BOTH counters' origin at the leading edge of their own
 * sync pulse, which is what makes the polarity XOR affordable (§6.2.1) and what
 * makes VSYNC_raw one product term in BOTH families.  So slot 0 is the start of
 * HSYNC, not the start of the picture. */
const DOT = [0, 1].map((b) => `DP${b}`)
const SLOT = [...Array(8).keys()].map((b) => `HC${b}`)
const hcount: Cell[] = [
  ...DOT.map((n, i) => reg(n, counterTerms({ bits: DOT, enable: "" })[i])),
  ...SLOT.map((n, i) => reg(n, counterTerms({
    bits: SLOT, enable: "SLOTTICK", terminal: "HC7 & HC6 & HC2 & HC1 & HC0",
  })[i])),
]

/* -- the vertical counter, and the family latch --------------------------
 *
 * ⭐ M0 IS LOADED AT FRAME END AND NOWHERE ELSE (§6.2).  Without the latch an
 * exact compare would miss a 449 total from a line already past it and run the
 * frame on to line 960 - a second and a half of lost sync. */
const LINE = [...Array(10).keys()].map((b) => `VC${b}`)
const vcount: Cell[] = [
  ...LINE.map((n, i) => reg(n, counterTerms({
    bits: LINE, enable: "LINETICK", terminal: "VTC",
  })[i])),
  reg("M0", ["FRAMEEND & VMODE0", "M0 & !FRAMEEND"]),
]

/* -- CTRL, and the two bits of HSCROLL this part duplicates ---------------
 *
 * signals.md §3.4: HSCROLL[1:0]'s consumers - the fetch-rank enables and the
 * dot phase - are here, while the register lives on v3scan.  Both parts are on
 * the register bus, so one CPU store writes both copies: two macrocells and no
 * pins.  graphics.md §8.2 went the same way for a harder reason. */
const ctrl: Cell[] = [
  ...[0, 1, 2, 3, 4, 5, 6, 7].map((b) =>
    reg(`CT${b}`, [`LDCTRL & D${b}`, `CT${b} & !LDCTRL`])),
  ...[0, 1].map((b) => reg(`HS${b}`, [`LDHSL & D${b}`, `HS${b} & !LDHSL`])),
]

/* -- the sprite: plan §7, bitmap mode only -------------------------------
 *
 * ⛔ THE POSITION IS NOT COMPARED, IT IS COUNTED DOWN.  A ten-bit equality is
 * an XNOR per bit ANDed together, and in sum-of-products that is 2^10 product
 * terms - a CPLD substitutes a combinational intermediate where it is read, so
 * there is nowhere for the XNORs to hide.  A down-counter loaded with SPRX and
 * decremented per dot reaches zero at the same instant, and its terminal count
 * is ONE term of ten literals.  graphics.md §6.4.9 makes the same move for the
 * map's column: "one ahead costs a counter, not an adder".
 *
 * ⚠ And it removes the pixel-column counter this file had a moment ago: the
 * counter IS the comparison. */
const SHC = [...Array(10).keys()].map((b) => `SHC${b}`)
const SVC = [...Array(9).keys()].map((b) => `SVC${b}`)
const SPRXB = [...Array(10).keys()].map((b) => `SX${b}`)
const SPRYB = [...Array(9).keys()].map((b) => `SY${b}`)

/* down-counter: hold at zero, so the terminal count is stable for the line */
const downTo0 = (bits: string[], en: string, load: string, from: string[]): Cell[] =>
  bits.map((q, i) => {
    const lower = bits.slice(0, i)
    const zero = bits.map((b) => `!${b}`).join(" & ")
    const borrow = lower.map((b) => `!${b}`)
    return reg(q, [
      `${load} & ${from[i]}`,
      `!${load} & !${en} & ${q}`,
      `!${load} & ${en} & ${q} & ${zero}`,
      ...(lower.length
        ? [`!${load} & ${en} & ${q} & !(${borrow.join(" & ")})`.replace(
            /!\(([^)]*)\)/, (_m, g) => g.split(" & ").map((l: string) => l.replace("!", "")).join(" # "))]
        : []),
      `!${load} & ${en} & !${q} & ${borrow.concat([]).join(" & ") || "1"}`,
    ].filter((t) => !t.includes("& 1")))
  })

const sprite: Cell[] = [
  ...SPRXB.map((n, i) => reg(n, [`LD${i < 8 ? "SPRX" : "SPRH"} & D${i < 8 ? i : i - 8}`,
                                 `${n} & !LD${i < 8 ? "SPRX" : "SPRH"}`])),
  ...SPRYB.map((n, i) => reg(n, [`LD${i < 8 ? "SPRY" : "SPRH"} & D${i < 8 ? i : 2}`,
                                 `${n} & !LD${i < 8 ? "SPRY" : "SPRH"}`])),
  reg("SPREN", ["LDSPRH & D7", "SPREN & !LDSPRH"]),
  ...[0, 1, 2, 3].map((b) => reg(`SI${b}`,
    [`LDSPRIX & D${b}`, ...counterTerms({ bits: [0,1,2,3].map((i) => `SI${i}`), enable: "LDSPRDA" })[b]
      .map((t) => `!LDSPRIX & ${t}`)])),
  ...downTo0(SHC, "ACTIVE", "HLOAD", SPRXB),
  ...downTo0(SVC, "ROWADV", "VLOAD", SPRYB),
  ...[0, 1, 2].map((b) => reg(`SW${b}`, counterTerms({
    bits: [0, 1, 2].map((i) => `SW${i}`), enable: "SPRSH", clear: "SPRHIT",
  })[b])),
  ...[0, 1, 2].map((b) => reg(`SR${b}`, counterTerms({
    bits: [0, 1, 2].map((i) => `SR${i}`), enable: "ROWADV", clear: "SPRVHIT",
  })[b])),
  /* the row's two bytes, serialised a dot at a time into the ATTR path.
   * ⭐ Affordable here and not for graphics.md §6.4.3's Variant B, and the
   * difference is one register: this output is re-registered by the ATTR latch
   * before the LUT, so it has a whole dot to settle.
   * ⚠ V3_SPRSHIFT=discrete puts it in two '165 instead - partition.md §8's
   * costed escape, and the board has already paid for it. */
  ...(SPRSHIFT_DISCRETE ? [] :
    [0, 1].map((h) => [...Array(8).keys()].map((b) => reg(`SH${h}${b}`,
      b === 7
        ? [`SPRLD & D7`, `!SPRLD & !SPRSH & SH${h}7`]
        : [`SPRLD & D${b}`, `!SPRLD & SPRSH & SH${h}${b + 1}`,
           `!SPRLD & !SPRSH & SH${h}${b}`]))).flat()),
]

/* -- the dot path, the cadence, the arbiter ------------------------------ */
const ACTIVE_H = "HC5 & !HC7 # HC7 & !HC6 & !HC5 & !HC4 & !HC3 & !HC2"
const dotPath: Cell[] = [
  comb("SLOTTICK", ["DP1 & DP0"]),
  comb("HBLANK", ["!ACTIVE"]),
  comb("HSYNC", ["!HC7 & !HC6 & !HC5 & !HC4 & !HC3"]),
  comb("VSYNC", ["!VC9 & !VC8 & !VC7 & !VC6 & !VC5 & !VC4 & !VC3 & !VC2 & !VC1 & !VMODE0",
                 "VC1 & VMODE0", "VC2 & VMODE0", "VC3 & VMODE0"]),
  comb("VBLANK", ["VBLANKRAW"]),
  comb("BLANK", ["HBLANK", "VBLANK", "!CT7"]),
  comb("FRAMEEND", ["SLOTTICK & HLAST & VTC"]),
  comb("LINETICK", ["SLOTTICK & HLAST"]),
  /* the cadence v3scan and v3ptr are timed from (signals.md §1.1) */
  comb("FETCH", ["ACTIVE"]),
  comb("SPARE", ["!DP1"]),
  comb("CELLTICK", ["SLOTTICK & !HC0"]),
  comb("HLOAD", ["HBLANK & HC4 & !HC5"]),
  comb("VLOAD", ["VBLANK"]),
  comb("ROWADV", ["LINETICK & VACTIVE & !DBLHOLD"]),
  comb("MCADV", ["CELLTICK"]),
  comb("MAPLD", ["SPARE & CELLTICK"]),
  reg("DBLHOLD", ["LINETICK & !DBLHOLD & !CT1", "DBLHOLD & !LINETICK"]),
  /* the dot-path clocks and enables */
  comb("MUXSEL0", ["DP0"]),
  comb("MUXSEL1", ["DP1"]),
  comb("PIXOE", ["!PALTURN"]),
  comb("ATOE", ["!PALTURN & MODE1 # !PALTURN & MODE0"]),
  comb("PIDXOE", ["PALTURN"]),
  comb("OMR", ["!BLANK"]),
  comb("FOE0", ["HS0 # HS1"]),
  comb("FOE1", ["!HS0 & !HS1"]),
  ...(SPRSHIFT_DISCRETE ? [] : [comb("SPRA0", ["SPRACT & SH00"]),
                                comb("SPRA1", ["SPRACT & SH10"])]),
  comb("SPRACT", ["SPREN & !MODE1 & !MODE0 & SPRROW & !SW2"]),
  comb("SPRSH", ["SPRACT"]),
  comb("SPRLD", ["HBLANK & SPRROW & HC3 & !HC4"]),
  /* ⭐ the arbiter.  ONE place decides the spare access, and FBOE follows from
   * it - so the two parts on the address bus can never both drive. */
  comb("GMAP", ["SPARE & RMAP"]),
  comb("GRD", ["SPARE & !RMAP & RRD"]),
  comb("GCPY", ["SPARE & !RMAP & !RRD & RCPY"]),
  comb("GSPN", ["SPARE & !RMAP & !RRD & !RCPY & RSPN"]),
  comb("FBOESCAN", ["!SPARE", "GMAP"]),
  comb("FBOEPTR", ["GRD", "GCPY", "GSPN"]),
  /* ⛔ these were declared as INPUTS in the draft the fitter refused.  Every one
   * is a decode of this part's own counters: importing them spent five pins on
   * signals nothing else produces. */
  comb("HLAST", ["HC7 & HC6 & HC2 & HC1 & HC0"]),
  comb("ACTIVE", [ACTIVE_H]),
  comb("VACTIVE", ["!VBLANKRAW"]),
  comb("VBLANKRAW", ["!VC9 & !VC8 & !VC7 & !VC6 & !VC5", "VC9 & M0", "VC9 & VC8 & !M0"]),
  comb("VTC", ["VC9 & VC7 & VC6 & VC4 & !M0", "VC9 & VC8 & VC3 & VC2 & M0"]),
  comb("SPRVHIT", SVC.map((b) => `!${b}`).join(" & ").split("\u0000")),
  comb("SPRHIT", SHC.map((b) => `!${b}`).join(" & ").split("\u0000")),
  comb("SPRROW", ["SPRVHIT", "!SR2"]),
  comb("MODE0", ["CT2"]),
  comb("MODE1", ["CT3"]),
  comb("VMODE0", ["CT0"]),
]

export const v3dot: Merged = {
  name: "v3dot",
  partNo: "ARM6309-V3D",
  location: "video3 - raster, dot path, sprite, arbiter",
  device: "f1508ispplcc84",
  clock: "CLK25",
  inputs: [
    { name: "CLK25" }, { name: "RESET", activeLow: true },
    ...[0, 1, 2, 3, 4, 5, 6, 7].map((b) => ({ name: `D${b}` })),
    /* ⛔ the sprite's shape arrives on D, not on sixteen pins of its own.  An
     * earlier draft invented SPA/SPB and the fitter refused the part at 75 IOs;
     * the register file already drives this bus and this part is already on it. */
    { name: "LDCTRL" }, { name: "LDHSL" }, { name: "LDSPRX" }, { name: "LDSPRY" },
    { name: "LDSPRH" }, { name: "LDSPRIX" }, { name: "LDSPRDA" },
    { name: "RMAP" }, { name: "RRD" }, { name: "RCPY" }, { name: "RSPN" },
    { name: "PALTURN" },
  ],
  cells: [...hcount, ...vcount, ...ctrl, ...sprite, ...dotPath],
  external: new Set([
    "HSYNC", "VSYNC", "BLANK", "OMR", "MUXSEL0", "MUXSEL1", "PIXOE", "ATOE",
    "PIDXOE", "FOE0", "FOE1", ...(SPRSHIFT_DISCRETE ? ["SPRLD", "SPRSH"] : ["SPRA0", "SPRA1"]),
    "SLOTTICK", "FETCH", "SPARE", "CELLTICK", "HLOAD", "VLOAD", "ROWADV",
    "MCADV", "MAPLD", "GMAP", "GRD", "GCPY", "GSPN", "FBOESCAN", "FBOEPTR",
    "MODE0", "MODE1", "M0", "HBLANK", "VBLANK",
  ]),
}

if (import.meta.main) {
  console.log(`v3dot (sprshift=${SPRSHIFT_DISCRETE ? "discrete" : "silicon"}): ` +
              `${v3dot.cells.length} cells, ${v3dot.inputs.length} declared inputs`)
  console.log(toCupl(v3dot))
}
