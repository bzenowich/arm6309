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
import { BROADCAST, decodeCells, type RegName } from "./regmap"
import { counterTerms, loadable } from "../jedec/counter"

/* ⭐ partition.md §8's costed escape: the sprite's shift registers as '165
 * rather than macrocells.  A switch, not a comment - both sides fitted, the
 * way ARM6309_LIST is in gal/video.cpld.ts.
 *
 * ⚠ FOUR OF THEM SINCE 2026-09-17, not two: the sprite is 16 x 16 (plan §7),
 * so a row is 32 bits and each plane is two cascaded '165. */
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
  /* SPRIDX: 64 shape bytes (16 rows x 4), so six bits where 8 x 8 had four */
  ...[0, 1, 2, 3, 4, 5].map((b) => reg(`SI${b}`,
    [`LDSPRIX & D${b}`, ...counterTerms({ bits: [0,1,2,3,4,5].map((i) => `SI${i}`), enable: "LDSPRDA" })[b]
      .map((t) => `!LDSPRIX & ${t}`)])),
  ...downTo0(SHC, "ACTIVE", "HLOAD", SPRXB),
  ...downTo0(SVC, "ROWADV", "VLOAD", SPRYB),
  /* the window counters: sixteen columns and sixteen rows (plan §7), so four
   * bits each where the 8 x 8 sprite had three */
  ...[0, 1, 2, 3].map((b) => reg(`SW${b}`, counterTerms({
    bits: [0, 1, 2, 3].map((i) => `SW${i}`), enable: "SPRSH", clear: "SPRHIT",
  })[b])),
  ...[0, 1, 2, 3].map((b) => reg(`SR${b}`, counterTerms({
    bits: [0, 1, 2, 3].map((i) => `SR${i}`), enable: "ROWADV", clear: "SPRVHIT",
  })[b])),
  /* the row's two bytes, serialised a dot at a time into the ATTR path.
   * ⭐ Affordable here and not for graphics.md §6.4.3's Variant B, and the
   * difference is one register: this output is re-registered by the ATTR latch
   * before the LUT, so it has a whole dot to settle.
   * ⚠ V3_SPRSHIFT=discrete puts it in two '165 instead - partition.md §8's
   * costed escape, and the board has already paid for it. */
  ...(SPRSHIFT_DISCRETE ? [] :
    [0, 1].map((h) => [...Array(16).keys()].map((b) => reg(`SH${h}${b}`,
      b === 15
        ? [`SPRLD & D7`, `!SPRLD & !SPRSH & SH${h}15`]
        : [`SPRLD & D${b % 8}`, `!SPRLD & SPRSH & SH${h}${b + 1}`,
           `!SPRLD & !SPRSH & SH${h}${b}`]))).flat()),
]

/* -- the dot path, the cadence, the arbiter ------------------------------ */
/* ⛔ THE DOT PATH'S THREE WINDOW TERMS WERE WRONG, and the fitter had no way
 * to say so - they are syntactically fine and they routed.  `v3dot_tb`
 * measured them the first time the part ran as a design rather than as a
 * utilisation figure:
 *
 *   HSYNC    32 dots, where VGA 640x480 at 25.175 MHz needs 96
 *   ACTIVE   272 dots in three disjoint runs, where it needs 640
 *   VSYNC    `VC1 # VC2 # VC3` in the 525-line family, which is not a range
 *            at all - it is high for most of the frame
 *
 * HC counts SLOTS of four dots, 0..199 (HLAST is 199), so the line is:
 *   HC   0.. 23   HSYNC          96 dots
 *   HC  24.. 35   back porch     48
 *   HC  36..195   ACTIVE        640
 *   HC 196..199   front porch    16   = 800
 *
 * The two range comparators are their own cells: a CPLD has about five
 * product terms before it cascades, and `HC >= 36 AND NOT HC >= 196` as one
 * flat sum is far more than that. */
const HGE36 = ["HC7", "HC6", "HC5 & HC4", "HC5 & HC2"]      // HC >= 36
const HGE196 = ["HC7 & HC6 & HC2"]                          // HC >= 196
const dotPath: Cell[] = [
  comb("SLOTTICK", ["DP1 & DP0"]),
  comb("HBLANK", ["!ACTIVE"]),
  /* HC < 24: 96 dots */
  comb("HSYNC", ["!HC7 & !HC6 & !HC5 & !HC4", "!HC7 & !HC6 & !HC5 & !HC3"]),
  /* VC < 2: two lines, in BOTH families.  640x400 at 70 Hz and 640x480 at
   * 60 Hz both take a two-line VSYNC; what differs between them is the
   * POLARITY, and that is not this term's business. */
  comb("VSYNC", ["!VC9 & !VC8 & !VC7 & !VC6 & !VC5 & !VC4 & !VC3 & !VC2 & !VC1"]),
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
  comb("SPRACT", ["SPREN & !MODE1 & !MODE0 & SPRROW & !SW3"]),
  comb("SPRSH", ["SPRACT"]),
  comb("SPRLD", ["HBLANK & SPRROW & HC3 & !HC4"]),
  /* ⭐ the arbiter.  ONE place decides the spare access, and FBOE follows from
   * it - so the two parts on the address bus can never both drive. */
  /* ⛔ RMAP AND RRD WERE INPUT PINS THAT NOTHING PRODUCED - the two requests
   * of the four that had no requester (check:reach, 2026-09-18). Neither
   * needed a block:
   *
   *   RMAP  ⭐ IS THIS PART'S OWN CELLTICK. The map word is fetched once a
   *         cell and MAPLD is already `SPARE & CELLTICK`, so a separate
   *         request signal would have been the same decode under a second
   *         name - and importing it spent a pin on a signal this part makes.
   *         ⚠ QUALIFIED BY MODE, which MAPLD is not: bitmap mode has no map,
   *         and granting it an access there would spend the slot's only spare
   *         on a fetch nothing reads.
   *   RRD   is v3host's RDREQ - `!RDVALID`, "the prefetch wants a refill".
   *         §11's request under its own name, and video/ spells it the same
   *         way (video.parts.ts: "!RDVALID & SPAREWIN").
   *
   * ⚠ The priority order is unchanged; only the names of the top two
   * requests are. */
  comb("MAPREQ", ["CELLTICK & MODE0", "CELLTICK & MODE1"]),
  comb("GMAP", ["SPARE & MAPREQ"]),
  comb("GRD", ["SPARE & !MAPREQ & RDREQ"]),
  comb("GCPY", ["SPARE & !MAPREQ & !RDREQ & RCPY"]),
  comb("GSPN", ["SPARE & !MAPREQ & !RDREQ & !RCPY & RSPN"]),
  comb("FBOESCAN", ["!SPARE", "GMAP"]),
  comb("FBOEPTR", ["GRD", "GCPY", "GSPN"]),
  /* ⛔ these were declared as INPUTS in the draft the fitter refused.  Every one
   * is a decode of this part's own counters: importing them spent five pins on
   * signals nothing else produces. */
  comb("HLAST", ["HC7 & HC6 & HC2 & HC1 & HC0"]),
  comb("HGE36", HGE36),
  comb("HGE196", HGE196),
  comb("ACTIVE", ["HGE36 & !HGE196"]),
  comb("VACTIVE", ["!VBLANKRAW"]),
  /* ⛔ THE 449-LINE FAMILY'S BOTTOM BLANKING NEVER FIRED.  `VC9 & VC8` needs
   * VC >= 768 and that frame is 449 lines, so the picture ran to the last
   * line and the frame never ended - which is what v3dot_tb measured as "901
   * lines" (its own bound), in every mode.
   *
   *   449 lines:  0..31 blank, 32..431 active (400), 432..448 blank
   *   525 lines:  0..31 blank, 32..511 active (480), 512..524 blank
   *
   * The 525 family's `VC9 & M0` was right; the other needed VC >= 432, which
   * over 0..448 is VC8&VC7&VC6 (448 itself) or VC8&VC7&VC5&VC4 (432..447). */
  comb("VBLANKRAW", ["!VC9 & !VC8 & !VC7 & !VC6 & !VC5",
                     "VC9 & M0",
                     "VC8 & VC7 & VC6 & !M0",
                     "VC8 & VC7 & VC5 & VC4 & !M0"]),
  /* ⛔ AND SO DID THE TERMINAL COUNT, for the same reason: 448 is
   * 0b0111000000, so VC9 is CLEAR there and `VC9 & ...` can never match; 524
   * is 0b1000001100, where VC8 is clear and `VC9 & VC8 & ...` cannot either.
   * Each value is unique in its own range, so three literals name it. */
  comb("VTC", ["VC8 & VC7 & VC6 & !M0", "VC9 & VC3 & VC2 & M0"]),
  comb("SPRVHIT", SVC.map((b) => `!${b}`).join(" & ").split("\u0000")),
  comb("SPRHIT", SHC.map((b) => `!${b}`).join(" & ").split("\u0000")),
  comb("SPRROW", ["SPRVHIT", "!SR3"]),
  comb("MODE0", ["CT2"]),
  comb("MODE1", ["CT3"]),
  comb("VMODE0", ["CT0"]),
]

/* the offsets this part answers to */
const MY_REGS: RegName[] = [
  "LDCTRL", "LDHSL", "LDSPRX", "LDSPRY", "LDSPRH", "LDSPRIX", "LDSPRDA",
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
    /* ⭐ the register broadcast, decoded HERE (partition.md §3).  LDHSL is
     * decoded on v3scan too - a shared register is free on the broadcast,
     * where a strobe made it a fan-out. */
    ...BROADCAST.map((n) => ({ name: n })),
    { name: "RDREQ" }, { name: "RCPY" }, { name: "RSPN" },
    { name: "PALTURN" },
  ],
  cells: [
    ...decodeCells(MY_REGS),...hcount, ...vcount, ...ctrl, ...sprite, ...dotPath],
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
