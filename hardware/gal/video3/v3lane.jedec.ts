import type { Design } from "../jedec/assemble"

/* ------------------------------------------------------------------------
 * v3lane - video3's byte lanes: which of the framebuffer's four bytes a
 * single-byte access means, and who drives the card's internal data bus.
 *
 * ** WHAT IT IS FOR. The framebuffer is 32 bits - two x16 AS6C8016, four
 * byte lanes, one fetch group a slot (plan §2.3). Everything else on the card
 * that moves a VRAM byte is 8 bits: the register file (the span writer's
 * colour), the posted-write '574 (a CPU byte, and the copy's byte in flight),
 * and vread (the CPU's prefetch). Nothing on the board joined the two: no part
 * decoded the lane, nothing made a byte enable, and nothing chose which 8-bit
 * source drove the bus a write took its byte from (video3_card.v's GAP_1,
 * GAP_2, GAP_6 and GAP_7, and design-review2.md V-6 for the other card).
 *
 * ** THE BOARD IT DECODES FOR (video3/docs/plan.md §13.1):
 *
 *   lane c ('245 A) <-> IDB ('245 B), one 74AHCT245 a lane, DIR from v3host
 *   IDB: the register file, the posted-write '574's Q, the host '245, the
 *        CPLDs' D inputs, vread's D and the posted-write '574's D
 *
 * A byte access is v3ptr's: the prefetch (GRD, a read at WPTR), the copy
 * (GCPY, a read at CPTR then a write at WPTR) and the span writer (GSPN, a
 * write at WPTR). The lane is the low two bits of whichever column counter is
 * on the address bus, which CRDSEL chooses - v3ptr's LANE1:LANE0, the address
 * mux's own bottom two bits. CRDSEL still comes here, for the copy's phase.
 *
 * ** WHO DRIVES IDB, one at a time:
 *
 *   the lane '245     a byte access that READS - the prefetch, the copy's read
 *   the '574 (PWOE)   a write whose byte is posted - a direct-mode span
 *                     (WMODE 00: the CPU's byte) and the copy's write
 *   the host '245     a card write, E-high (WSTB, WSTBV). ⭐ WSTB needs no
 *                     term here: the register file is being WRITTEN then, and
 *                     an SRAM with /WE low has its outputs off whatever /OE says
 *   the register file everything else - the idle +$05, WFG/WBG for a span in
 *                     the three colour modes, the reload walk, a CPU read-back
 *
 * ** PURELY COMBINATIONAL, so pin 1 is an ordinary input (u9's call).
 * ------------------------------------------------------------------------ */

/* the lane of the access on the bus - v3ptr's LANE1:LANE0, which is CPTR's
 * low column bits for the copy's read and WPTR's otherwise */
const lane = (l: number) =>
  [`${(l >> 1) & 1 ? "LANE1" : "!LANE1"} & ${l & 1 ? "LANE0" : "!LANE0"}`]
const GRANTS = ["GRD", "GCPY", "GSPN"]
const LANE_NAMES = ["LB0", "UB0", "LB1", "UB1"]

export const v3laneDesign: Design = {
  name: "v3lane",
  partNo: "ARM6309-V3L",
  location: "video3 - byte lanes and the internal bus's drivers",
  signature: "A6309VL",
  inputs: [
    { name: "LANE0", pin: 1 }, { name: "LANE1", pin: 2 },
    { name: "CRDSEL", pin: 3 },
    { name: "GRD", pin: 4 }, { name: "GCPY", pin: 5 }, { name: "GSPN", pin: 6 },
    /* WMODE, from v3dot (CTRL b5..4) */
    { name: "WM0", pin: 7 }, { name: "WM1", pin: 8 },
    /* /VWE, the framebuffer's own write strobe - active low at both ends */
    { name: "VWE", pin: 9, activeLow: true }, { name: "WSTBV", pin: 10 },
    /* the 74HC4078's answer: the byte on IDB is zero, the copy's key */
    { name: "KEY", pin: 11 },
  ],
  cells: [
    /* the four lane transceivers' /OE: this access's lane, during its grant.
     * Only one lane even for a write - the other three '245s could broadcast
     * harmlessly, but a read must not, and one rule is one fewer to check. */
    ...[0, 1, 2, 3].map((l, i) => ({
      pin: [14, 23, 15, 22][i], name: `LOE${l}`, assertedLow: true, s0: 0 as const,
      terms: GRANTS.flatMap((g) => lane(l).map((t) => `${g} & ${t}`)),
    })),
    /* the byte enables, /LB0 /UB0 /LB1 /UB1: every byte, except that a WRITE
     * takes its own lane alone. A read enables all four - the display fetch
     * needs them, and a byte read's other three lanes go nowhere because
     * their '245s are off. ⭐ This is what writes one byte into a x16 part.
     *
     * ⭐⭐ AND IT IS WHERE THE COLOUR KEY LIVES (keyed-copy.md). A copy's write
     * whose byte is the key enables NO byte, so the write does not happen and
     * the destination keeps its background: a full-colour transparent blit at
     * the engine's rate, where software costs a pass a colour (plan §5's
     * sprite WMODE). The byte is on IDB for the whole write access - the
     * posted-write '574 drives it - so an 8-input NOR on the board has the
     * access to settle in, and KEY is "the byte is zero": a FIXED key,
     * because a '688 against a key register is a DIP-20 and the board has
     * room for a DIP-14 (check:place).
     * ⭐ WMODE 11 ARMS IT, and the copy grant qualifies it: sprite WMODE
     * already means "transparent" to the span writer, so it means the same to
     * the copy engine, and a plain copy still moves index 0 like any other
     * byte. ⛔ It is HERE and not on v3ptr - the part that gates VWE and would
     * have been the obvious home - because v3ptr refused it twice, with a cell
     * and with none: 124/128, every LAB at 39 of 40 inputs. This part had two
     * spare inputs and WMODE already on them. */
    ...[0, 1, 2, 3].map((l, i) => ({
      pin: [16, 21, 17, 20][i], name: LANE_NAMES[l], assertedLow: true, s0: 0 as const,
      terms: ["!VWE", ...lane(l)].flatMap((t) =>
        ["!KEY", "!WM1", "!WM0", "!GCPY"].map((n) => `${t} & ${n}`)),
    })),
    /* the posted-write '574's /OE: a direct-mode span's byte (the CPU's), or
     * the copy's write access (the byte its read access left there) */
    { pin: 18, name: "PWOE", assertedLow: true, s0: 0 as const,
      terms: ["GSPN & !WM1 & !WM0", "GCPY & !CRDSEL"] },
    /* the register file's /OE: on unless something else has IDB - a lane
     * read, the '574, or a posted CPU write coming in through the host '245 */
    { pin: 19, name: "RFOE", assertedLow: true, s0: 0 as const,
      terms: ["!GRD & !GCPY & !WSTBV & !GSPN",
              "!GRD & !GCPY & !WSTBV & WM1",
              "!GRD & !GCPY & !WSTBV & WM0"] },
  ],
}
