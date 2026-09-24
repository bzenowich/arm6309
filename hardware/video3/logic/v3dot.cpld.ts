/* v3dot - video3's raster, dot path, sprite and arbiter, as an ATF1508AS.
 *
 * hardware/video3/docs/partition.md §2.1.  The part everything else is timed from, and
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

import { toCupl, type Merged } from "../../tools/gal/jedec/cupl"
import type { Cell } from "../../tools/gal/jedec/assemble"
import { BROADCAST, decodeCells, type RegName } from "./regmap"
import { counterTerms, loadable } from "../../tools/gal/jedec/counter"
import { sop } from "../../tools/gal/jedec/truth"

/* ⭐ The sprite's shift registers are four '165, two cascaded a plane
 * (partition.md §8's escape, which §5 risk 3 made a requirement): with them in
 * silicon this part answers `Design does not fit`. */

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
  /* b5..4 are WMODE, and they leave as WM0/WM1 (below) for v3ptr's span
   * writer and v3lane. ⛔ As the REGISTERS on two pins the part was refused;
   * as two combinational copies of them it fits. */
  /* ⛔ NOT b6: the VBL interrupt enable is v3host's (IRQEN, beside /IRQ), and
   * a copy here was a macrocell nothing read - check:reach, once video3 had a
   * board file to count the rest against. */
  ...[0, 1, 2, 3, 4, 5, 7].map((b) => {
    const n = `CT${b}`
    return reg(n, [`LDCTRL & D${b}`, `${n} & !LDCTRL`])
  }),
  ...[0, 1].map((b) => reg(`HS${b}`, [`LDHSL & D${b}`, `HS${b} & !LDHSL`])),
  /* ⭐ AND HSCROLL[2], for tile mode's cell phase (graphics.md §6.4.9: the map
   * access runs a slot earlier when the column counter's cells start half a
   * cell into a slot pair). One more duplicate, for the same reason as the two
   * above: it is consumed here, at slot rate, by the map request. */
  reg("HS2", ["LDHSL & D2", "HS2 & !LDHSL"]),
]

/* -- the sprite: plan §7, bitmap mode only -------------------------------
 *
 * ⛔ THE POSITION IS NOT COMPARED, IT IS COUNTED.  A ten-bit equality is an
 * XNOR per bit ANDed together, and in sum-of-products that is 2^10 product
 * terms - a CPLD substitutes a combinational intermediate where it is read, so
 * there is nowhere for the XNORs to hide.  A counter loaded with the
 * COMPLEMENT of SPRX and counted up a dot at a time is all-ones on exactly the
 * dot x = SPRX (~SPRX + SPRX = 1023), and all-ones is ONE term of ten
 * literals - vlen.jedec.ts's idiom, and counter.ts's `loadable`, which the
 * other counters on this card already prove. A register holds the hit for the
 * rest of the line (SPRY's likewise for the rest of the frame); the counter
 * runs on and cannot come round to all-ones again, because a line is 640 dots
 * and a frame 480 rows, both short of the wrap.
 * ⛔ IT WAS A HOLD-AT-ZERO DOWN-COUNTER THAT NEVER COUNTED: bit 0's
 * decrement term was dropped by a filter meant for a different term, and its
 * hold-at-zero term was `SVC0 & !SVC0`. No bench had run it; v3card_tb's first
 * sprite frame showed no sprite at all. */
const SHC = [...Array(10).keys()].map((b) => `SHC${b}`)
const SVC = [...Array(9).keys()].map((b) => `SVC${b}`)
const SPRXB = [...Array(10).keys()].map((b) => `SX${b}`)
const SPRYB = [...Array(9).keys()].map((b) => `SY${b}`)
const SR = [...Array(5).keys()].map((b) => `SR${b}`)
const allOnes = (bits: string[]) => bits.join(" & ")

/* ⭐ THE SHAPE IS IN VRAM, and the row counter is its address (plan §7).
 * A sprite row is one spare access in horizontal blanking - four bytes, one
 * fetch group - and the four '165 load straight off the four byte lanes of the
 * framebuffer's data bus, so the shape never enters a CPLD and never crosses
 * the register file. This part drives FBA5..FBA2 with the row, v3scan drives
 * the rest with the base (MAPBASE's top 64 bytes, which bitmap mode has no
 * other use for).
 * ⛔ It was in the register file, above +$1F, and nothing could reach it: the
 * file's address is RFA4..RFA0, and a shape read needs a sixth and seventh
 * bit, an arbiter against the span writer's colour reads, and four '165 load
 * strobes - about fifteen pins, on a card whose four parts had nine between
 * them. partition.md §3.1 rejected VRAM as "v3dot on the arbiter and PB on it";
 * the '165s on the lanes take neither. */
const sprite: Cell[] = [
  ...SPRXB.map((n, i) => reg(n, [`LD${i < 8 ? "SPRX" : "SPRH"} & D${i < 8 ? i : i - 8}`,
                                 `${n} & !LD${i < 8 ? "SPRX" : "SPRH"}`])),
  ...SPRYB.map((n, i) => reg(n, [`LD${i < 8 ? "SPRY" : "SPRH"} & D${i < 8 ? i : 2}`,
                                 `${n} & !LD${i < 8 ? "SPRY" : "SPRH"}`])),
  reg("SPREN", ["LDSPRH & D7", "SPREN & !LDSPRH"]),
  ...SHC.map((q, i) => reg(q, loadable(SHC, "ACTIVE", "HLOAD", SPRXB.map((b) => `!${b}`))[i])),
  ...SVC.map((q, i) => reg(q, loadable(SVC, "ROWADV", "VLOAD", SPRYB.map((b) => `!${b}`))[i])),
  /* the hits, held: from the dot (row) the counter is all-ones on, to the end
   * of the line (frame) */
  /* ⚠ INSIDE ACTIVE, both ways: held only while the picture runs, and the
   * window only there. The row is loaded in slot 8, and a hit still held from
   * the line before - or an all-ones counter straight after HLOAD, at SPRX 0 -
   * shifted the whole row out in the blanking before it (v3card_tb). */
  reg("SHQ", ["SHQ & ACTIVE", `${allOnes(SHC)} & ACTIVE`]),
  reg("SVQ", ["SVQ & !VLOAD", `${allOnes(SVC)} & ROWADV`]),
  /* the sprite row, 0..15 - and it IS the shape address. Counts picture rows
   * from SPRY and stops at 16 (SR4), so nothing past the shape is fetched;
   * cleared through vertical blanking. */
  ...SR.map((q, i) => reg(q, loadable(SR, "ROWADV & SPRROW", "VLOAD", SR.map(() => "0"))[i]
    .filter((t) => !t.endsWith("& 0")))),
  /* ⭐ the two sprite bits onto LUT A9..A8, re-registered here (plan §3's
   * "the register is the difference": the '165 output has a whole dot to
   * settle). Zero outside the sprite, so bitmap and tile mode read
   * sub-palette 0; stood off in character mode and during a palette turn. */
  ...[0, 1].map((b) => ({ ...reg(`SPRA${b}`, [`SQ${b} & SPRACT`]), oe: "SPRAOE" })),
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
 * ⭐ ACTIVE IS A REGISTER, set on the tick that ends slot 35 and cleared on
 * the one that ends slot 195. As a decode it was `HC >= 36 AND NOT HC >= 196`,
 * and CUPL substitutes an intermediate into every product that reads it - so
 * ACTIVE, HBLANK, BLANK and the sprite counter's enable each carried the
 * comparators' whole sum, and one term more in HC >= 36 (HC 40..43, 0010 10xx,
 * matched none of the old four: every line blanked sixteen pixels in, which
 * v3card_tb's first frame showed and v3dot_tb alone did not) was enough for
 * the fitter to refuse the part. A register costs one cell and makes every
 * reader one literal.
 *   The clear needs no exact 195: `HC7 & HC6 & HC1 & HC0` is 195 or 199 below
 * HLAST, and at 199 ACTIVE is already clear. */
const ACTSET = "SLOTTICK & !HC7 & !HC6 & HC5 & !HC4 & !HC3 & !HC2 & HC1 & HC0"  // HC = 35
const ACTCLR = ["SLOTTICK", "HC7", "HC6", "HC1", "HC0"]                         // HC = 195
/* the fine scroll, as the rank select and the '153 phase see it: zero in
 * character mode, which has no horizontal scroll (plan §2.5) */
const FINE = ["DP1", "DP0", "HS1", "HS0", "MODE0"]
const p = (v: Record<string, boolean>) => v.MODE0 ? 0 : (v.HS1 ? 2 : 0) + (v.HS0 ? 1 : 0)
const dp = (v: Record<string, boolean>) => (v.DP1 ? 2 : 0) + (v.DP0 ? 1 : 0)
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
  /* ⭐ THE SPARE WINDOW IS DOTS 0-1, THE DISPLAY ACCESS DOTS 2-3. SPARE is also
   * the fetch ranks' CLOCK: it rises on the edge that ends the display access,
   * which is when the group is on the lanes - a '574 needs an edge, and this
   * is a register bit's own output rather than a decode. */
  comb("SPARE", ["!DP1"]),
  /* ⭐ HC 30-33: every counter that starts a line loads here. The scan column
   * counter counts every slot (v3scan steps on DP1 & DP0) and the load wins,
   * so it holds HSCROLL through slot 33 and names group 0 in slot 34, two
   * slots before the picture - rank A, then rank B. The map column loads on
   * this window's FIRST dot (v3scan's HLQ), which is what lets the first map
   * access be as early as slot 31. Always blank: ACTIVE starts at 36. */
  comb("HLOAD", ["!HC7 & !HC6 & HC5 & !HC4 & !HC3 & !HC2 & !HC1",
                 "!HC7 & !HC6 & !HC5 & HC4 & HC3 & HC2 & HC1"]),
  comb("VLOAD", ["VBLANK"]),
  comb("ROWADV", ["LINETICK & VACTIVE & !DBLHOLD"]),
  /* ⛔ AND THE PAIR's PHASE IS SET EVERY FRAME. DBLHOLD toggled on every
   * line, and both families have an ODD number of lines (449, 525), so which
   * line of a doubled pair advanced the row flipped from one frame to the next
   * - every other frame of a 200- or 240-row picture was a line out, and
   * v3card_tb's second doubled frame showed row 1 on line 1. Held set through
   * vertical blanking, so the first picture line is always a pair's first. */
  reg("DBLHOLD", ["VBLANK & !CT1", "LINETICK & !DBLHOLD & !CT1", "DBLHOLD & !LINETICK"]),
  /* ⭐ THE MAP CADENCE - graphics.md §6.4.9, rebuilt. ⛔ It never ran: MAPLD was
   * `SPARE & CELLTICK` and the grant `SPARE & (CELLTICK & MODE)`, and CELLTICK
   * is dot 3 while SPARE is dots 0-1, so neither could ever be true and
   * character and tile mode fetched no map at all.
   *
   * MRQ is the request for the CURRENT slot, a register loaded on the tick
   * that ends the slot before - so every grant, the address mux's select and
   * the map latch read one literal where the decode was a sum that CUPL would
   * have substituted into all of them. One access a cell, in the slot whose
   * parity is HC0 == HSCROLL[2] (the cell phase, H0 xor HS2):
   *
   *   HS2 = 0   access 32, 34 .. 194   code handed over at the end of 33 .. 195
   *   HS2 = 1   access 31, 33 .. 193   handed over at the end of 32 .. 194
   *
   * The code for cell k is fetched a cell ahead of its tile fetch (§6.4.9's
   * lead), and at HS2 = 1 the line takes 81 codes. The trailing accesses past
   * the picture fetch cells nobody sees; the one at 194 is what closes the last
   * attribute into the ATTR latch (below). MWIN is the window, 30..193, as a
   * register for the same reason ACTIVE is one.
   *
   * ⭐ AND IN BITMAP MODE THE SAME REQUEST IS THE SPRITE's ROW FETCH, once a
   * line in slot 8 - horizontal sync, long after the last shift and long
   * before the first. Bitmap mode has no map, so the grant, the load strobe
   * and v3scan's address source are free. */
  reg("MWIN", ["SLOTTICK & !HC7 & !HC6 & !HC5 & HC4 & HC3 & HC2 & !HC1 & HC0",   // set, end of 29
               ...["DP1", "DP0", "HC7", "HC6", "HC0"].map((l) => `MWIN & !${l}`)]), // clear, end of 193
  reg("MRQ", [
    "SLOTTICK & MWIN & MODE0 & HC0",                       // character: HS2 is zero
    "SLOTTICK & MWIN & MODE1 & HC0 & !HS2",                // tile, HS2 = 0: even slots
    "SLOTTICK & MWIN & MODE1 & !HC0 & HS2",                // tile, HS2 = 1: odd slots
    "SLOTTICK & SPREN & !MODE0 & !MODE1 & SPRROW & " +     // the sprite row, slot 8
      "!HC7 & !HC6 & !HC5 & !HC4 & !HC3 & HC2 & HC1 & HC0",
    "MRQ & !DP1", "MRQ & !DP0",
  ]),
  comb("MAPREQ", ["MRQ"]),
  /* the dot-path clocks and enables */
  /* ⭐ THE '153 PHASE IS THE DOT PLUS HSCROLL[1:0] (graphics.md §8.2): at fine
   * scroll p the leftmost pixel of a slot is byte p of the group. */
  comb("MUXSEL0", sop(FINE, (v) => ((dp(v) + p(v)) & 1) === 1)),
  comb("MUXSEL1", sop(FINE, (v) => ((dp(v) + p(v)) & 2) === 2)),
  comb("PIXOE", ["!PALTURN"]),
  /* ⭐ v3scan's ATO drives LUT A15..A8 in character mode and nowhere else:
   * the sprite drives A9..A8 itself (SPRA), and tile mode's ATTR is zero,
   * which the pull-downs on A15..A8 give when nothing drives them. */
  comb("ATOE", ["!PALTURN & MODE0"]),
  comb("PIDXOE", ["PALTURN"]),
  comb("SPRAOE", ["!PALTURN & !MODE0"]),
  /* ⭐ THE '273 PAIR's /MR, AND IT HAS TO BE THE BLANKING THE PIXEL SEES.
   * plan §3's chain puts two registers after the '153 - the index '574, then
   * the '273 - so a dot reaches the connector two dots after BLANK says it
   * may. /MR on the undelayed BLANK blanked the first two pixels of every line
   * and showed two from past its end (v3card_tb). video/ delayed its blank for
   * the same reason (BLANKD). OMR is the second stage, inverted: asserted =
   * the pixel may show. */
  reg("BD1", ["BLANK"]),
  reg("OMR", ["!BD1"]),
  /* ⭐ THE RANK SELECT IS PER CHIP (graphics.md §8.2): at fine scroll p, chip c
   * shows the NEXT group exactly when c < p. Chip 3 is always rank B, so its
   * pair is strapped on the board. ⛔ It was one pair for all four chips, and
   * the '153 phase was the bare dot - so a scroll that was not a multiple of
   * four showed the wrong rank on some chips and the wrong byte on all. Each
   * pair is a complement in silicon: a '574 has one /OE and the board has no
   * inverter. */
  comb("OEA0", sop(["HS1", "HS0", "MODE0"], (v) => p(v) > 0)),
  comb("OEB0", sop(["HS1", "HS0", "MODE0"], (v) => !(p(v) > 0))),
  comb("OEA1", sop(["HS1", "HS0", "MODE0"], (v) => p(v) > 1)),
  comb("OEB1", sop(["HS1", "HS0", "MODE0"], (v) => !(p(v) > 1))),
  comb("OEA2", sop(["HS1", "HS0", "MODE0"], (v) => p(v) > 2)),
  comb("OEB2", sop(["HS1", "HS0", "MODE0"], (v) => !(p(v) > 2))),
  /* the sprite: from SPRX to the end of the line, because the '165 chains shift
   * in zeros behind the shape - so the window needs no counter of its own */
  comb("SPRACT", ["SPREN & !MODE1 & !MODE0 & SPRROW & SPRHIT & ACTIVE"]),
  comb("SPRSH", ["SPRACT"]),
  /* the '165s' parallel load, while the row is on the lanes */
  comb("SPRLD", ["MRQ & !DP1 & DP0 & !MODE0 & !MODE1"]),
  /* the row, onto FBA5..FBA2 for the sprite's access; v3scan drives the rest */
  ...[2, 3, 4, 5].map((b) => ({
    ...comb(`FBA${b}`, [`SR${b - 2}`]), oe: "MRQ & !DP1 & !MODE0 & !MODE1" })),
  /* ⭐ the arbiter.  ONE place decides the spare access, and every bus enable
   * follows from it - so no two parts ever drive the address bus. The map
   * (or the sprite row) outranks everything: refuse it and the picture is
   * wrong, every frame. Then the CPU's prefetch, the copy, the span writer. */
  comb("GMAP", ["SPARE & MAPREQ"]),
  comb("GRD", ["SPARE & !MAPREQ & RDREQ"]),
  comb("GCPY", ["SPARE & !MAPREQ & !RDREQ & RCPY"]),
  comb("GSPN", ["SPARE & !MAPREQ & !RDREQ & !RCPY & SPANBUSY"]),
  comb("FBOEPTR", ["GRD", "GCPY", "GSPN"]),
  /* ⛔ these were declared as INPUTS in the draft the fitter refused.  Every one
   * is a decode of this part's own counters: importing them spent five pins on
   * signals nothing else produces. */
  comb("HLAST", ["HC7 & HC6 & HC2 & HC1 & HC0"]),
  reg("ACTIVE", [ACTSET, ...ACTCLR.map((t) => `ACTIVE & !${t}`)]),
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
  comb("SPRVHIT", [allOnes(SVC), "SVQ"]),
  comb("SPRHIT", [allOnes(SHC), "SHQ"]),
  comb("SPRROW", ["SPRVHIT & !SR4"]),
  comb("VMODE0", ["CT0"]),
  comb("MODE0", ["CT2"]),
  comb("MODE1", ["CT3"]),
  comb("WM0", ["CT4"]),
  comb("WM1", ["CT5"]),
]

const LOW = new Set(["OEA0", "OEA1", "OEA2", "OEB0", "OEB1", "OEB2", "PIXOE", "PIDXOE",
  "SPRLD", "SPRSH", "LDPIDXL", "LDPIDXH"])

/* the offsets this part answers to */
const MY_REGS: RegName[] = [
  "LDCTRL", "LDHSL", "LDSPRX", "LDSPRY", "LDSPRH",
  /* ⭐ the palette's four load strobes, for the discrete latches (plan §13.1):
   * PIDX low ('163 /LD), PIDX high ('574 clock), PDATL and PDATH ('573 LE).
   * Nothing made them - v3host decodes PDATH for its own commit and nothing
   * else - and a '138 cannot: +$0E/+$0F and +$10/+$11 differ in all of
   * RA4..RA1, which is four enables' worth of condition on a part with three.
   * Decoded here off the broadcast, a term each. */
  "LDPIDXL", "LDPIDXH", "LDPDATL", "LDPDATH",
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
    { name: "RDREQ" }, { name: "RCPY" }, { name: "SPANBUSY" },
    { name: "PALTURN" },
    /* the two '165 chains' serial outputs, one per plane */
    { name: "SQ0" }, { name: "SQ1" },
  ],
  cells: [
    ...decodeCells(MY_REGS),...hcount, ...vcount, ...ctrl, ...sprite, ...dotPath]
    /* ⭐ the pins whose consumer is active-low (check:pins holds each to the
     * discrete part it drives); the equations stay in asserted sense */
    .map((c) => (LOW.has(c.name) ? { ...c, assertedLow: true } : c)),
  external: new Set([
    "HSYNC", "VSYNC", "BLANK", "HBLANK", "VBLANK", "OMR",
    /* the dot path */
    "MUXSEL0", "MUXSEL1", "PIXOE", "ATOE", "PIDXOE",
    "OEA0", "OEB0", "OEA1", "OEB1", "OEA2", "OEB2",
    "SPRLD", "SPRSH", "SPRA0", "SPRA1", "FBA2", "FBA3", "FBA4", "FBA5",
    /* the cadence: the dot phase itself, the request, and the line loads -
     * v3scan, v3ptr and v3host make their own ticks from these */
    "DP0", "DP1", "SPARE", "MRQ", "HLOAD", "ROWADV",
    "GRD", "GCPY", "GSPN", "FBOEPTR",
    "MODE0", "MODE1",
    "LDPIDXL", "LDPIDXH", "LDPDATL", "LDPDATH", "WM0", "WM1",
]),
}

if (import.meta.main) {
  console.log(`v3dot: ${v3dot.cells.length} cells, ${v3dot.inputs.length} declared inputs`)
  console.log(toCupl(v3dot))
}
