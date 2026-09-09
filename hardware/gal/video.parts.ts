/* The pieces of the video card that exist only once the GALs merge, plus the
 * three blocks graphics.md puts in v1 and nobody had written.
 *
 * Kept apart from video.cpld.ts so the partition can be argued with without
 * touching the logic.
 */

import type { Cell } from "./jedec/assemble"
import { counterTerms, loadable } from "./jedec/counter"
import { rangeTerms } from "./jedec/range"
import { H } from "./sync.timing"

/* hgen's slot counter, which the windows below are compares on. */
const HB = ["H0", "H1", "H2", "H3", "H4", "H5", "H6", "H7"]

/* ---- the scroll preloads, which were seventeen wasted pins -------------- *
 *
 * hadr and vadr take HS2..HS9 and VS0..VS8 on dedicated pins because that is
 * how a 22V10 fit had to declare them. On one die that is seventeen holes for
 * values the register file already puts on D0..D7 - the same path §9.5 uses
 * for WPTR on the audio card. Holding them here costs 17 macrocells, of which
 * there are plenty, and returns 17 pins, of which there are not. */
export const scrollHolds: Cell[] = [
  /* §8: HSCROLL[9:2] preloads the column counter and HSCROLL[1:0] preloads the
   * mux phase, so the eight bits held HERE are HSCROLL[9:2] - which is §13's
   * HSCROLL b7..b2 PLUS HSCROLLH b1..b0, not HSCROLL b7..b0. Written the
   * second way on 2026-09-07 and wrong by two bit positions: every horizontal
   * scroll would have landed at four times the column asked for, and the top
   * two bits of a 1024-wide torus would have been unreachable. HS0 and HS1
   * are on vctrl - the mux phase is seqph's. */
  /* ⭐ EACH OF THESE HAS TWO WRITE PORTS SINCE 2026-09-09, and the second one
   * is 10.3.2's list engine (19 item 32). The CPU writes through LDxx from the
   * card's internal data bus D0..D7; a descriptor writes through LWxx from the
   * PIXEL bus PB0..PB7, which is where the byte the engine just fetched is.
   *
   * ⚠ AND IT STAYS ON PB, WHICH WAS TESTED RATHER THAN ASSUMED. 10.3.3 puts
   * the same byte on D0..D7 through a '244 so that vsup can read the operand,
   * and sourcing THIS latch from D too would have made one byte instead of
   * two. The fitter refused it: with D0..D7 feeding the descriptor as well as
   * the scroll and tile registers, this part's LAB fan-in went over the
   * ATF1508AS's limit of 40 in every block and all four passes answered
   * "Grouping fail / Design does not fit". 10.3.3 records what the two
   * sources cost - one dot, in a case 10.3.1's rule already forbids.
   *
   * One extra product term per bit and no macrocell: the load terms are
   * disjoint by construction (LDxx is `WSTB & <address>` and LWxx is
   * `LMOVE & <opcode>`, and LMOVE cannot coincide with a CPU register write
   * because the engine's cycle is a granted VRAM slot), so the hold term
   * simply carries both negations.
   *
   * !! THE ENGINE CANNOT REACH HS0 OR HS1 ON vctrl - it has no input pin left.
   * 8.2's fine pair on vsup, which is the one the picture uses, IS reachable:
   * it is written by the same descriptor, in the same dot. */
  ...[2, 3, 4, 5, 6, 7].map((b) => ({
    pin: 0, name: `HS${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`LDHS & D${b}`, `LWHSL & PB${b}`, `HS${b} & !LDHS & !LWHSL`],
  })),
  ...[8, 9].map((b) => ({
    pin: 0, name: `HS${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`LDHSH & D${b - 8}`, `LWHSH & PB${b - 8}`, `HS${b} & !LDHSH & !LWHSH`],
  })),
  /* !! VSCROLL HAS ONE WRITE PORT. The engine reaching it too was built and
   * REFUSED - the fitter returned INTERNAL ERROR in pass 1, the same answer it
   * gives 19 item 31's ten-bit shadow. See 10.3.2. */
  ...[0, 1, 2, 3, 4, 5, 6, 7].map((b) => ({
    pin: 0, name: `VS${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`LDVSL & D${b}`, `VS${b} & !LDVSL`],
  })),
  { pin: 0, name: "VS8", assertedLow: false, s0: 1, registered: true,
    terms: ["LDVSH & D0", "VS8 & !LDVSH"] },
]

/* ---- §6.4's tile and character address sources ------------------------- *
 *
 * §6.4.1: "with an aligned tile set every term lands on its own address bits,
 * so there is no adder" - tile.check.ts asserts that as OR = ADD over all
 * 524,288 field combinations. TILEBASE and FONTBASE are the register-file
 * values that anchor them (§13, +$17-$19). */
export const tileRegisters: Cell[] = [
  ...[0, 1, 2, 3, 4].map((b) => ({
    pin: 0, name: `TB${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`LDTB & D${b}`, `TB${b} & !LDTB`],
  })),
  /* ⚠ FONTBASE's eight registers went with Variant B on 2026-09-08 - see
   * graphics.md 6.4.3. The register itself stays reserved at +$18. */
  /* The map byte, latched off the pixel bus one cell ahead of the tile fetch
   * (§6.4.1's "pipelined one cell ahead"). §6.4.1 prices this as "one 3-state
   * '574, or zero packages if it can be absorbed into the scan-address GAL as
   * registered macrocells" - on a CPLD it is the second. */
  /* §6.4.6's map base, +$19. */
  ...[0, 1, 2, 3, 4, 5, 6].map((b) => ({
    pin: 0, name: `MB${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`LDMB & D${b}`, `MB${b} & !LDMB`],
  })),
  ...[0, 1, 2, 3, 4, 5, 6, 7].map((b) => ({
    pin: 0, name: `MAP${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`MAPLD & PB${b}`, `MAP${b} & !MAPLD`],
  })),

  /* ⭐ AND A SECOND RANK, 2026-09-09, because ONE REGISTER PROVABLY CANNOT DO
   * IT and the card displayed every cell's right-hand neighbour.
   *
   * 6.4.9's diagram is right and the equation under it was not: in slot 2k the
   * spare access fetches map[N+1] WHILE THE DISPLAY FETCH IS STILL USING
   * code[N]. So the code the tile address reads must be held from before slot
   * 2k until after slot 2k+1 - two slots - while a new byte arrives every two
   * slots, in the front half of slot 2k. The two windows overlap, and no
   * choice of latch instant separates them: the map data is on the bus only
   * during its own half-slot, and every other half-slot belongs to the display
   * fetch. Simulated, 158 of 160 tile fetches on a line carried the next
   * cell's code. design-review2.md V-5.
   *
   * MAP is the fetch target and MAPQ is what the address mux reads, handed
   * over at the CELL boundary - which is where 6.4.9's "pipelined one cell
   * ahead" was always describing. Eight macrocells on the part that has them:
   * vaddr was at 109 of 128. */
  ...[0, 1, 2, 3, 4, 5, 6, 7].map((b) => ({
    pin: 0, name: `MAPQ${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`CELLTICK & MAP${b}`, `MAPQ${b} & !CELLTICK`],
  })),
]

/* ---- 7.4's mask serialiser, and the sentinel that deleted a counter ---- *
 *
 * ⛔ IT WAS BOOKED AS ABSORBED AND NEVER WRITTEN. 10.1.6 lists "the '165
 * span-mask serialiser" among the packages the CPLDs took and 14.1 deletes it
 * from the IC count; no design file contained it, so MASKBIT was an input to
 * vctrl that nothing on the card produced - and with it went span-mask's
 * colour selection, sprite mode's transparency, and the register-file address
 * bit 7.4 calls "the whole mechanism". design-review2.md V-1.
 *
 * Eight bits, MSB first, and MASKBIT goes to two places: seqctl, for
 * features.md 8.4's sprite mode, and rfa's RA0, which is 7.4's "choosing the
 * colour per pixel costs no macrocell and no product term - it is an address
 * line".
 *
 * It loads from D0-D7 at the POSTED VRAM WRITE, which is where the mask byte
 * is: the CPU's data on the write that started the span. Not from the '574
 * data latch, which holds the same byte one gate later. */
export const maskSerialiser: Cell[] = [
  ...[7, 6, 5, 4, 3, 2, 1].map((n) => ({
    pin: 0, name: `SR${n}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [
      `WSTBV & D${n}`,
      `!WSTBV & RETIRE & SR${n - 1}`,
      `!WSTBV & !RETIRE & SR${n}`,
    ],
  })),
  { pin: 0, name: "SR0", assertedLow: false, s0: 1, registered: true,
    terms: [`WSTBV & D0`, "!WSTBV & !RETIRE & SR0"] },

  /* ⚠ AND SPAN-SOLID FORCES IT HIGH, which is the one place the mask bit is
   * not the mask. 7.4: solid is "SPANLEN + 1 pixels, all one colour", and the
   * colour is WFG - but the file's address bit is this signal, so without the
   * force a solid span would paint whatever byte the CPU happened to write as
   * the posted data, alternating WFG and WBG down the run. Simulated: 31 of 32
   * bytes wrong.
   *
   * Direct mode needs no such term - its byte comes from 3.1.1's data latch
   * and never from the file - and sprite mode must NOT have one, because a
   * transparent pixel is exactly a zero here. */
  { pin: 0, name: "MASKBIT", assertedLow: false, s0: 1, registered: false,
    why: "the serialiser's top bit, except that span-solid is always WFG",
    terms: ["WM1 & !WM0", "SR7 & !WM1", "SR7 & WM0"] },
]

/* ---- the map fetch's own cell column, 6.4.1's "one cell ahead" ---------- *
 *
 * WHY SEVEN MACROCELLS RATHER THAN REUSING SA9..SA3. 6.4.1 requires the map
 * byte "pipelined one cell ahead" of the tile fetch, and the reason is timing.
 * A slot is 158.9 ns and 5.2.2 splits it - spare access first, display fetch
 * second, 79.4 ns each. Fetching the map byte in the spare half of the SAME
 * slot that then fetches the tile row puts this chain inside one 79.4 ns half:
 * address mux (~15 ns) + SRAM (55 ns, 14.2's AS6C8016-55) + latch setup
 * (~5 ns) = 75 ns, and the tile address then has to repeat it. Two 4.4 ns
 * margins, on a card whose tightest documented path (6.1) has 11.7. One cell of
 * lead turns both into a full half-slot of slack.
 *
 * Leading by one cell means the map fetch addresses cell N while the tile fetch
 * addresses cell N-1 - and SA9..SA3 IS the cell being tile-fetched. The obvious
 * fix is SA + 1 and 6.4.1's whole argument is that there is no adder. So the
 * map keeps its own counter: same load value, HSCROLL[9:3], started one cell
 * earlier because MFETCH opens two slots before TFETCH (tileCadence below).
 * "One ahead" costs a counter, not an adder.
 *
 * Seven bits, no terminal count: the map is 128 cells wide (6.4.1's 128-byte
 * stride) and 128 is where seven bits wrap, which is the horizontal ring. */
export const mapColumn: Cell[] = [
  ...loadable(
    ["MC0", "MC1", "MC2", "MC3", "MC4", "MC5", "MC6"],
    "MCADV", "HLOAD",
    ["HS3", "HS4", "HS5", "HS6", "HS7", "HS8", "HS9"],
  ).map((terms, i) => ({
    pin: 0, name: `MC${i}`, assertedLow: false, s0: 1 as const, registered: true, terms,
  })),
  /* §6.4.2's ninth access. "Display fetch per 8 dots: 9 accesses" against the
   * bitmap's 8 is exactly eight tile bytes - two slots of four through the
   * ordinary display path - PLUS ONE, and that one is the map byte, taken from
   * a spare access. A spare access names one of the four chips and the name is
   * the low two bits of the address it wants, the same identity as SPNA1/SPNA0
   * = WPTR[1:0] (5.2.1). Here they are cellCol[1:0], so four adjacent cells sit
   * on four different chips and the map load spreads evenly - which is what
   * makes 6.4.2's "2.25 accesses per chip per cell" true. */
  { pin: 0, name: "MAPA0", assertedLow: false, s0: 1, registered: false, terms: ["MC0"] },
  { pin: 0, name: "MAPA1", assertedLow: false, s0: 1, registered: false, terms: ["MC1"] },
]

/* The framebuffer address, now with four sources. §6.4.1's concatenations:
 *
 *   linear   A18..A10 scan row      A9..A2  scan column
 *   tile     A18..A14 TILEBASE      A13..A6 code   A5..A3 row  A2 col[2]
 *   char     A18..A11 FONTBASE      A10..A3 code   A2      row[2]
 *   write    A18..A0  WPTR
 *
 * A1..A0 never appear: they are the 4-way interleave phase and never leave
 * the '153s, so the chip address is A18..A2 and this is seventeen bits. */
export const addressMux = (): Cell[] => {
  /* A slot is four pixels and a cell is eight, so the byte address WITHIN a
   * tile row is the column counter's own low bit, SA2 - not a slot-counter
   * bit, which was written here on 2026-09-07 and addresses in units of
   * sixteen pixels.
   *
   * ⚠ THE ROW WITHIN THE CELL IS SA12..SA10, NOT V2..V0 - corrected
   * 2026-09-08. Both name a line and only one of them is zero at the top of
   * the display: sync.timing.ts puts BOTH counters' origin at the leading edge
   * of their own sync pulse, so active video starts at V = 37 in the 449-line
   * family and V = 35 in the 525-line one. V2..V0 as the glyph row would have
   * rotated every cell by 37 mod 8 = 5 rows in one mode and 3 in the other.
   * vadr's row counter has neither problem: VLOAD loads it from VSCROLL through
   * vertical blanking and ROWADV advances it once per DISPLAYED row
   * (scan.jedec.ts), so SA18..SA10 is zero-based at the top of the window by
   * construction - and scrolled, which is what makes VSCROLL work in cell mode
   * at all (graphics.md 6.4.8). */
  const tileSrc = (bit: number) =>
    bit >= 14 ? `TB${bit - 14}` : bit >= 6 ? `MAPQ${bit - 6}` : bit >= 3 ? `SA${bit + 7}` : "SA2"
  /* The map's own address - base, cell row, cell column - which the mux did
   * not have at all, so MAPLD was latching a byte from an address nothing
   * generated. §19 item 16 lives here and it costs nothing: the intra-cell
   * offset is {SA2, mux phase}, and §8 already preloads the column counter
   * with HSCROLL[9:2] and the phase with HSCROLL[1:0]. Both halves are
   * therefore already scrolled. §6.4.6 calls sub-cell scroll "new logic in
   * the address concatenation"; it is not, PROVIDED the map byte for a cell
   * is fetched before that cell's first pixel - a cadence requirement, not an
   * address one.
   *
   * ⚠ THE FIELDS WERE TRANSPOSED UNTIL 2026-09-08. This read
   * `bit >= 5 ? SA[bit-2] : V[bit+1]`, which puts cellCol at A11..A5 and three
   * bits of cell row at A4..A2: a map with a 32-byte COLUMN stride, a 4-byte
   * row stride, 8 addressable rows against the 25 an 80x25 needs, and the
   * HSCROLL mux phase left in A1..A0. tile.model.ts's mapAddress and
   * graphics.md 6.4.1 both say MAPBASE | cellRow<<7 | cellCol, and nothing
   * asserted the two agreed - tile.check.ts imported addressMux only to COUNT
   * it. It now derives the map address from these terms and compares.
   *
   *   A18..A12  MAPBASE      MB6..MB0
   *   A11..A7   cell row     SA17..SA13   (the row counter's own bits, / 8)
   *   A6..A0    cell column  MC6..MC0     (the MAP's own counter - see below)
   *
   * ⚠ THE COLUMN IS MC AND NOT SA9..SA3, since 2026-09-08's cadence. The map
   * fetch runs ONE CELL AHEAD of the tile fetch that consumes it (6.4.1's
   * "pipelined one cell ahead"), and SA9..SA3 is by construction the cell being
   * TILE-fetched - using it addresses the map one cell late. 6.4.1's argument
   * forbids the obvious fix, because a +1 is an adder. MC is that counter, one
   * cell in front: "one ahead" costs a counter, not an adder.
   *
   * so A1..A0 here are cellCol[1:0] = {MC1, MC0} and NOT the pixel phase.
   * That is MAPA1/MAPA0 in mapColumn. */
  const mapSrc = (bit: number) =>
    bit >= 12 ? `MB${bit - 12}` : bit >= 7 ? `SA${bit + 6}` : `MC${bit}`
  return [...Array(17).keys()].map((i) => {
    const bit = i + 2
    return {
      pin: 0, name: `FBA${bit}`, assertedLow: false, s0: 1 as const, registered: false,
      /* FOUR sources since 2026-09-08, and both changes that day were about
       * this list. 6.4.3's Variant B took CHARSEL out; 10.1.6.2's option 2
       * means the list engine never adds one, because it drives the address
       * through SPNGRANT & WA[n] - WPTR IS its pointer.
       *
       * ⚠ The write-pointer source reads SPNGRANT and not WRITESEL. They were
       * always the same signal (5.2.1) and WRITESEL was the name vctrl re-emitted
       * it under while the arbiter sat on its own GAL. The arbiter came back onto
       * vctrl on 2026-09-08 and the alias went with it.
       *
       * That second point is the whole reason the engine fits. Its own
       * nineteen-bit pointer was not just 19 registers: it was 19 more mux
       * inputs and a SIXTH product term on every one of these seventeen
       * macrocells, and an ATF15xx macrocell holds five before it cascades. */
      /* SRC1:SRC0 names the source - tileCadence's encoding, decoded here for
       * nothing, which is two crossing nets rather than four. */
      terms: [
        `!SRC1 & !SRC0 & SA${bit}`,
        `!SRC1 & SRC0 & WA${bit}`,
        `SRC1 & !SRC0 & ${tileSrc(bit)}`,
        `SRC1 & SRC0 & ${mapSrc(bit)}`,
      ],
    }
  })
}

/* ---- §6.4's fetch cadence, and §5.2.2's slot ---------------------------- *
 *
 * ⚠ REWRITTEN 2026-09-08. What was here counted TC0..TC2 on SLOTTICK and split
 * the period at TC2 - and a slot is four dots while a cell is eight, so that
 * period was FOUR CELLS. Over it the design fetched 16 tile bytes where 32 are
 * needed and latched one map byte where four are: half a line's pixels had no
 * data and three cells in four had no code. It was a sketch of "map byte, then
 * the tile row" and graphics.md 19 item 15(c) is where it is recorded.
 *
 * THE SEQUENCE IS FIXED BY 6.4.2'S OWN ARITHMETIC - nine accesses per eight
 * dots. Eight tile bytes ARE two ordinary display fetches (four interleaved
 * chips x two slots), so in cell mode the tile address owns the display half of
 * every slot exactly as the bitmap's scan address does, and the NINTH access is
 * the map byte out of a spare window (5.2.2's front half), once per cell.
 *
 *   slot     2k          2k+1        2k+2        2k+3
 *   spare    map[N+1]    -           map[N+2]    -
 *   fetch    tile N.0-3  tile N.4-7  tile N+1.0-3  ...
 *            \_____ cell N _____/   \____ cell N+1 ____/
 *
 * The cell is two slots and its phase is H0, the slot counter's own low bit -
 * no counter of its own, which is the second thing the old TC got wrong.
 *
 * THE MAP FETCH LEADS BY ONE CELL, which is why MFETCH opens two slots before
 * TFETCH and why the map has its own column counter (mapColumn above). During
 * MFETCH's first cell - the last two slots of the back porch - the map byte for
 * screen cell 0 is fetched while the tile fetch is still idle.
 */
export const tileCadence: Cell[] = [
  /* The display fetch window, in slots. 8's column counter reloads at HLOAD and
   * advances on FETCH, and both were listed in census.ts as "produced by the
   * sequencer's unfitted decode half" - nothing generated them. They are two
   * window compares on hgen's counter, which is on this part. */
  /* ⭐ IT OPENS ONE SLOT BEFORE ACTIVE VIDEO SINCE 2026-09-09, and that slot is
   * the whole of 19 item 28's fetch lead. 8.2's second latch rank holds the
   * PREVIOUS group, so the address bus has to run one group ahead of the
   * picture for the pair to straddle a group boundary.
   *
   * !! THE WINDOW MOVES BY TWO SLOTS, AND IT DOES NOT LENGTHEN - 34..193 for
   * the same 160 slots. Two, not one, because rank B is a series latch and a
   * series latch holds the OLDER value: during display slot d rank A holds the
   * fetch from d-1 and rank B the fetch from d-2, so for B to carry the base
   * group the address has to run two slots ahead of the picture and rank A
   * then carries base+1. Built with a one-slot lead first, and vaddr_tb's
   * pixel check is what said so - the ranks were the right way round and the
   * lead was one short. And two is the shift that keeps H0's cell parity: a
   * cell is two fetch slots, so an ODD shift swaps every cell's halves.
   * At HSCROLL[1:0] = 0
   * every chip reads rank B and the displayed line is bit-identical to what a
   * one-slot lead produced - which is the invariant vaddr_tb checks. */
  { pin: 0, name: "TFETCH", assertedLow: false, s0: 1, registered: false,
    terms: rangeTerms({ bits: HB, lo: H.backEnd, hi: H.activeEnd - 1, max: H.last }) },
  /* Two slots - one cell - earlier, and it ends two slots earlier too: the last
   * cell of a line has no successor to fetch a code for. */
  { pin: 0, name: "MFETCH", assertedLow: false, s0: 1, registered: false,
    terms: rangeTerms({ bits: HB, lo: H.backEnd - 2, hi: H.activeEnd - 3, max: H.last }) },
  /* ⚠ AND IT IS SLOTTICK-GATED, because everything here is clocked on DOTCLK.
   * 8's column counter takes this as its ENABLE, so a level asserted for the
   * whole window would advance it four times a slot - once per dot - and put
   * the line four times too far along. Written as a bare level on 2026-09-08
   * and caught by the frame check the same day: SLOTTICK is one dot wide, so
   * the increment lands once a slot. Every counter enable on this part carries
   * it; a LOAD does not, because a load is idempotent.
   *
   * ⚠ THE DOT IS 0, NOT 3, SINCE 2026-09-09 - seqph.jedec.ts has the
   * measurement. A counter advances on the edge that ENDS the dot its enable
   * is high in, so dot 0 puts the advance one dot AFTER FCLK's rising edge and
   * dot 3 puts it on the same edge, under the latch. Measured: dot 3 is 636 of
   * 640 pixels wrong. */
  { pin: 0, name: "FETCH", assertedLow: false, s0: 1, registered: false,
    terms: ["TFETCH & SLOTTICK"] },
  /* Through the sync pulse and the back porch, up to the slot before MFETCH
   * opens: both column counters take their scroll offset here. */
  /* ⚠ AND IT CLOSES ONE SLOT EARLIER SINCE 2026-09-09. 8.2's fetch lead moved
   * MFETCH's opening from 34 to 33, and HLOAD ran to 33 - so for one slot the
   * column counters were being LOADED while the map fetch was already using
   * them. cadence.check.ts caught it as an overlap the moment it was taught
   * about LRUN and put back into `npm run check`. */
  { pin: 0, name: "HLOAD", assertedLow: false, s0: 1, registered: false,
    terms: rangeTerms({ bits: HB, lo: 0, hi: H.backEnd - 3, max: H.last }) },

  /* ---- the vertical window, §8 ------------------------------------------ *
   *
   * ROWADV is "one pulse at the end of each displayed line" (scan.jedec.ts) and
   * VLOAD is "asserted through vertical blanking". Both were listed in
   * census.ts as the sequencer's unfitted decode half, and without them the row
   * counter never takes VSCROLL and never steps - in EITHER mode, so this was
   * the bitmap's gap as much as the tilemap's.
   *
   * ⚠ VLOAD IS NOT BUILT, BECAUSE IT ALREADY EXISTS. "Asserted through vertical
   * blanking" is VBLANK's definition, and vdec has produced VBLANK all along -
   * vadr's input is renamed to it on merge (video.cpld.ts). The same identity
   * as WRITESEL = SPNGRANT: two names, one signal, and on a part at 64 of 64
   * I/O the difference is a pin.
   *
   * ROWADV fires in the LAST slot of the line. TFETCH ends at slot 195 and
   * MFETCH at 193, so slot 199 is clear of both this line's fetch and the next
   * line's, which is what lets the row counter be stable across a whole line's
   * worth of map and tile addresses. */
  { pin: 0, name: "HEND", assertedLow: false, s0: 1, registered: false,
    terms: rangeTerms({ bits: HB, lo: H.last, hi: H.last, max: H.last }) },
  /* §6.2's line doubling lives here and nowhere else: "the sequencer withholds
   * every second one, which is the whole of line-doubling" (scan.jedec.ts).
   * VMODE1 = 0 is the doubled pair - 640x200 in the 449-line family and 640x240
   * in the 525-line one, both 200/240 rows over 400/480 active lines - and
   * VMODE1 = 1 is 640x400 and 640x480, one row per line.
   *
   * WHICH LINES TO WITHHOLD IS ONE TERM IN BOTH FAMILIES, and that is luck
   * worth writing down. A doubled row must advance at the end of the SECOND
   * displayed line of the pair, so the test is on the parity of V minus the
   * first active line - 37 in the 449 family, 35 in the 525 (sync.timing.ts).
   * Both are ODD, so display-line parity is V's parity inverted in both, and
   * "advance when V is even" covers the pair. It is the same accident that
   * gives vdec its "v <= 1 in both families" sync window.
   *
   *   ROWADV = /VBLANK . HEND . SLOTTICK . (VMODE1 # /V0)
   *
   * SLOTTICK for the same reason FETCH carries it: HEND is a whole slot and the
   * part is clocked on DOTCLK, so without it the row would advance FOUR times a
   * line and the picture would scan at a quarter height. */
  { pin: 0, name: "ROWADV", assertedLow: false, s0: 1, registered: false,
    terms: ["!VBLANK & HEND & SLOTTICK & VMODE1", "!VBLANK & HEND & SLOTTICK & !V0"] },

  /* One map access per cell, in the FIRST slot of the map cell - H0 is the cell
   * phase. The counter steps in the second, so MC names one cell throughout the
   * cell that fetches it. */
  /* ⭐ AND THE PARITY IS UNTOUCHED BY 8.2's FETCH LEAD, because that lead is
   * TWO slots and not one. A cell is two fetch slots and H0 is the cell phase,
   * so an odd shift swaps every cell's two halves for the rest of the line -
   * vtile_tb reported exactly that, 80 wrong of 160. An even shift cannot:
   * both windows move by 2 and H0 means what it always meant. */
  { pin: 0, name: "MAPREQ", assertedLow: false, s0: 1, registered: false,
    terms: ["TILEMODE & MFETCH & H0"] },
  { pin: 0, name: "MCADV", assertedLow: false, s0: 1, registered: false,
    terms: ["TILEMODE & MFETCH & !H0 & SLOTTICK"] },
  /* 5.2.2's spare access is dots 0-1 (SPAREWIN = !PH1) and the display fetch is
   * dots 2-3. The map byte is latched on the boundary between them - true
   * during dot 1, so the register clocks at the dot 1 -> 2 edge. */
  { pin: 0, name: "MAPLD", assertedLow: false, s0: 1, registered: false,
    terms: ["MAPREQ & !PH1 & PH0"] },
  /* ⭐ THE CELL BOUNDARY - the second half of V-5's repair. MAPLD fills the
   * fetch rank in the front half of the cell's FIRST slot; this hands it to
   * the rank the address mux reads, at the end of the cell's LAST slot, where
   * nothing is using the old value any more. One dot per cell.
   *
   * H0 is the cell phase (6.4.9), so the last dot of the odd slot is
   * H0 & SLOTTICK - and MFETCH bounds it to the cells that have a code. */
  { pin: 0, name: "CELLTICK", assertedLow: false, s0: 1, registered: false,
    terms: ["TILEMODE & MFETCH & !H0 & SLOTTICK"] },

  /* ---- who owns the address bus ---------------------------------------- *
   *
   * ⚠ ONE INTERNAL ADDRESS BUS, and this is the constraint that shapes the rest.
   * 5.2.1's SRCSEL[n] muxes each CHIP's address source between the CPU's bus and
   * the card's, so the CPU is independent per chip - but the display fetch, the
   * span writer and the map fetch all drive the card's single bus and are
   * therefore mutually exclusive in TIME. The map owns it for its spare window;
   * the tile address has it the rest of the time. */
  { pin: 0, name: "MAPSEL", assertedLow: false, s0: 1, registered: false,
    terms: ["MAPREQ & !PH1"] },
  /* ⚠ AND THE DISPLAY SOURCES CARRY THE PHASE TOO, since 2026-09-09. 5.2.2 is
   * a specification sentence - "the CPU/spare access occupies the FRONT half
   * of the slot, the display fetch the back half" - and 11's read budget
   * closes at +46.9 ns because of it and misses by -25.1 ns without it.
   * seqph forms SPAREWIN = !PH1 faithfully and NOTHING READ IT: MAPSEL was
   * phase-qualified and these two were not, so the display address held the
   * card's one internal bus for all four dots of every slot and there was no
   * spare window for the CPU or the span writer to use at all. The other
   * direction was worse: SPNGRANT has no phase term either, so a granted span
   * took the bus for the WHOLE slot and the display fetch got nothing - a
   * span-solid running through active video blanked the picture for up to
   * 40.7 us. design-review2.md V-4.
   *
   * PH1 is the back half. One literal each, and it is the difference between
   * 2.1's access budget being a budget and being arithmetic about a card that
   * does something else. */
  { pin: 0, name: "TILESEL", assertedLow: false, s0: 1, registered: false,
    terms: ["TILEMODE & PH1 & !SPNGRANT"] },
  { pin: 0, name: "LINEAR", assertedLow: false, s0: 1, registered: false,
    terms: ["!TILEMODE & PH1 & !SPNGRANT"] },

  /* ⭐ FOUR SOURCES, TWO PINS - 2026-09-09, and it is what bought the column
   * reload its last hole.
   *
   * The address mux on vaddr has exactly four sources and this part was
   * exporting all four selects as separate signals. They are mutually
   * exclusive by construction, so two bits name them and vaddr decodes them
   * back for nothing - a combinational intermediate on a CPLD costs no
   * macrocell and no pin, which is the same fact 10.1.6.1 used to keep CTRL
   * on this part.
   *
   *   00 linear   01 the write pointer   10 tile   11 map
   *
   * SPNGRANT stops crossing with them. It is read on this part by seqctl's
   * RETIRE and by LGRANT, and off it only by the mux - so the encoding is the
   * whole of its export. */
  { pin: 0, name: "SRC0", assertedLow: false, s0: 1, registered: false,
    terms: ["SPNGRANT", "MAPSEL"] },
  { pin: 0, name: "SRC1", assertedLow: false, s0: 1, registered: false,
    terms: ["TILESEL", "MAPSEL"] },

  /* ---- the arbiter's fourth requester ----------------------------------- *
   *
   * 2.2's priority is "video -> CPU -> list engine -> span -> blit" and the map
   * byte is VIDEO: refuse it and the cell displays a stale code, every frame.
   * So it outranks both of the arbiter's existing requesters, and the two ranks
   * are refused in two different places because they collide in two different
   * ways.
   *
   * THE SPAN WRITER collides on the BUS, so it stands down for the whole of a
   * map slot - SPNREQ is gated before it reaches the arbiter, which is one gate
   * rather than five and leaves arbDesign untouched and still checkable as a
   * standalone GAL22V10.
   *
   * ⚠ That costs the span writer HALF its spare slots in cell mode, not the
   * "roughly an eighth" 6.4.2 quotes. Both numbers are right about different
   * things: per-CHIP load does rise only 2.0 -> 2.25, because the map hits one
   * chip in four; but the map takes the shared bus one slot in two, and slots
   * are what the span writer actually queues for. graphics.md 6.4.2 carries the
   * correction. */
  { pin: 0, name: "SPNREQG", assertedLow: false, s0: 1, registered: false,
    terms: ["SPNREQ & !MAPREQ"] },

  /* ⭐ AND SPNREQ ITSELF, which nothing produced. 5.2.1's arbiter takes it as
   * an input and no cell on the card formed it, so the span writer never
   * asked for an access and no span ever retired a byte (design-review2.md
   * V-1). It is the request, and it is where 5.2.2's front half is imposed:
   * the spare access is dots 0-1 and the display fetch dots 2-3.
   *
   * ⭐ AND IT CARRIES THE LIST ENGINE. 10.3's engine reaches the framebuffer
   * "through the arbiter and the address path that already exist", which means
   * through this request and through the mux's SPNGRANT term - so one requester
   * covers both, and the span writer outranks the engine because a span in
   * flight cannot be interrupted. */
  { pin: 0, name: "SPNREQ", assertedLow: false, s0: 1, registered: false,
    terms: ["SPANBUSY & SPAREWIN", "LRUN & SPAREWIN"] },
  /* One dot per slot, at the END of the spare window - the access has
   * completed by then. seqctl's RETIRE and the engine's LADV both take it,
   * which is what makes the retire rate 7.4's one byte per 158.9 ns fetch
   * slot rather than one per dot. */
  { pin: 0, name: "SPNTICK", assertedLow: false, s0: 1, registered: false,
    terms: ["!PH1 & PH0"] },
  /* 10.3's grant. vctrl declared it external and produced no cell, so LADV,
   * LFETCH and LMOVE - all LRUN & LGRANT - were dead on silicon and the engine
   * re-executed descriptor byte 0 for ever. The span writer has priority: a
   * span in flight owns the pointer they share. */
  { pin: 0, name: "LGRANT", assertedLow: false, s0: 1, registered: false,
    terms: ["LRUN & !SPANBUSY & SPNGRANT & SPNTICK"] },
  /* THE CPU collides per CHIP, because its address path is its own. GMAP is the
   * map's chip and the CPU's grant - which is 5.2.1's SRCSEL[n], the thing that
   * would otherwise point that chip at the CPU's address - is withdrawn for it.
   * ACPU is arbDesign's GCPU, renamed on merge (video.cpld.ts). */
  ...[0, 1, 2, 3].map((n) => ({
    pin: 0, name: `GMAP${n}`, assertedLow: false, s0: 1 as const, registered: false,
    terms: [`MAPREQ & ${n & 1 ? "" : "!"}MAPA0 & ${n & 2 ? "" : "!"}MAPA1`],
  })),
  ...[0, 1, 2, 3].map((n) => ({
    pin: 0, name: `GCPU${n}`, assertedLow: false, s0: 1 as const, registered: false,
    terms: [`ACPU${n} & !GMAP${n}`],
  })),

  /* ---- and the CPU therefore has to be able to wait --------------------- *
   *
   * A refused CPU access is a lost one unless /WAIT stretches the cycle, so the
   * map's chip collision joins the span writer's on the backstop. It is a
   * DIFFERENT KIND of wait and the difference matters: 7.4's is up to 40.7 us
   * and only writes take it, this one is a single 158.9 ns slot and it has to
   * apply to reads as well, because a read whose chip is pointed elsewhere
   * returns the wrong byte just as surely.
   *
   * arbDesign is not touched. Its /WAIT already reads two inputs on the output
   * enable - SPANBUSY and R/W - and both are renamed on merge to signals formed
   * here, so the pin, the open-drain idiom and access.check.ts's assertions
   * about them all stand:
   *
   *   oe = WAITSRC & VRAMSEL & !IOPAGE & E & !WAITRW
   *
   * WAITSRC = SPANBUSY # MAPHOLD and WAITRW = RW & !MAPHOLD, so a map hold
   * asserts for reads and writes alike while 7.4's span backstop keeps its
   * !RW exactly as before. */
  { pin: 0, name: "MAPHOLD", assertedLow: false, s0: 1, registered: false,
    terms: [
      "MAPREQ & !MAPA0 & !A0 & !MAPA1 & !A1",
      "MAPREQ & MAPA0 & A0 & !MAPA1 & !A1",
      "MAPREQ & !MAPA0 & !A0 & MAPA1 & A1",
      "MAPREQ & MAPA0 & A0 & MAPA1 & A1",
    ] },
  { pin: 0, name: "WAITSRC", assertedLow: false, s0: 1, registered: false,
    terms: ["SPANBUSY", "MAPHOLD"] },
  { pin: 0, name: "WAITRW", assertedLow: false, s0: 1, registered: false,
    terms: ["RW & !MAPHOLD"] },

  /* ⚠ VARIANT B WAS DROPPED 2026-09-08 - graphics.md 6.4.3 and 10.1.6.2.
   * CHARSEL, GLYPHLD, GLYPHSH and LUTPAGE lived here, and the eight FONTBASE
   * registers above; what they bought was a 1bpp hardware character generator
   * at 2 CPU writes per cell against the span writer's 13. They were spent on
   * the display list. !CHARMODE dropped out of TILESEL and LINEAR above rather
   * than being deleted: with no char mode, TILEMODE alone says which it is. */
]

/* ---- 7.2's column reload, and the text engine's other half -------------- *
 *
 * ⛔ WADV = 01 ADVANCED THE ROW AND KEPT THE COLUMN. 7.2 is the section that
 * takes a character cell from 26 CPU writes to 13 - "set it once and a glyph
 * becomes eight mask writes and nothing else" - and it does that by reloading
 * WPTR's column from a shadow at span end. wcol's only load path was the CPU's
 * own three-byte register write, so a chained glyph stepped eight pixels right
 * on every row and every figure in 7.3 and features.md 2.3 was against
 * hardware that did not exist. docs/design-review2.md V-6.
 *
 * ⭐ AND 7.2's "the shadow is free" IS TRUE, just not in the way it said. That
 * section puts the shadow in the register file and spends "two deferrable file
 * reads" restoring it - which needs a two-cycle sequencer, a second set of
 * load strobes that wcol can distinguish from wrow's, and two pins on a part
 * that has none. Ten registers on vaddr cost ten macrocells and NOTHING ELSE:
 * they load on exactly the strobes that load the counter, so software writes
 * WPTR once and the shadow follows, and the reload is WROWADV, which already
 * crosses to this part for the row.
 *
 * ⚠ BOTH CHAINING MODES RELOAD IT. 13's WADV = 10 is "advance by the stride",
 * which is a vertical line: one pixel per span, so the column advances by one
 * and has to come back too. WROWADV is already SPANEND & (WADV0 # WADV1). */
export const columnReload: Cell[] = [
  /* A two-dot walk, started by the row advance and returning to idle on its
   * own. State 01 points the file at WPTR's low byte and loads it; state 10
   * does the same for the middle byte; 00 is idle.
   *
   * ⚠ ONE DOT PER BYTE, and the address leads the load by a whole dot: rfa
   * switches the file's address on the edge that ENTERS a state and this part
   * loads on the edge that LEAVES it, so the 20 ns register file and rfa's
   * ~10 ns have 39.7 ns to settle in. That is the same order as 6.1's index ->
   * LUT -> output chain and it is on a path used once per span rather than
   * once per dot. */
  { pin: 0, name: "RP0", assertedLow: false, s0: 1, registered: true,
    terms: ["!RP1 & !RP0 & WROWADV"] },
  { pin: 0, name: "RP1", assertedLow: false, s0: 1, registered: true,
    terms: ["!RP1 & RP0"] },
  /* ⚠ TWO STROBES AND NOT ONE, and wrow is why: its own LDB loads the row's
   * low six bits, so a reload that reused the CPU's strobe would undo the row
   * advance the same span just made. */
  { pin: 0, name: "RLDA", assertedLow: false, s0: 1, registered: false,
    terms: ["RP0 & !RP1"] },
  { pin: 0, name: "RLDB", assertedLow: false, s0: 1, registered: false,
    terms: ["RP1 & !RP0"] },
]

/* ---- §10.3's list engine ------------------------------------------------ *
 *
 * "Its MOVE opcode is one SRAM write into the register file, and the palette
 * it writes to already exists." That is why it costs almost no pins and a lot
 * of macrocells: it reads VRAM through the arbiter and the address path that
 * are already here, and writes the register file through one that is too. */
export const listEngine: Cell[] = [
  /* ⭐ WPTR'S INCREMENT, which is the defect that made the engine a loop.
   * video.parts.ts said "LADV drives WPTR's increment" and wcol's counter
   * enable is WINC - an input to vaddr that nothing renamed onto LADV, so the
   * pointer never moved, the same descriptor byte was re-fetched for ever,
   * LSTOP never saw $FF and LRUN never fell (design-review2.md V-3).
   *
   * One cell, and it is the right shape: the span writer and the engine share
   * the pointer by construction (10.1.6.2) and never drive it in the same
   * slot, so they share its enable too. */
  { pin: 0, name: "WINC", assertedLow: false, s0: 1, registered: false,
    terms: ["RETIRE", "LADV"] },

  /* ⚠ AND WINC IS ALL THAT IS LEFT OF THE ENGINE ON THIS PART - 2026-09-09.
   *
   * 10.3.2's descriptor decode - LD, LPH, LWAIT, LSTOP, LRUN, LADV and the
   * MOVE strobes, sixteen cells - moved to vsup (vsup.parts.ts). Two things
   * forced it and neither was macrocells:
   *
   *   ⛔ THIS PART WILL NOT TAKE ANOTHER LITERAL. It fits at 124 of 128 cells
   *      and 160 of 128 nodes with LAB FAN-IN AT 40 OF 40 IN EVERY BLOCK,
   *      which is the ATF1508AS switch matrix's limit and not a capacity one.
   *      Three separate one-literal changes to the engine were tried on
   *      2026-09-09 and the fitter answered "Grouping fail / Design does not
   *      fit" to two of them and "INTERNAL ERROR" to the third. Fan-in is what
   *      this family runs out of after cells and pins, and it is what stopped
   *      the v1 engine on a TQFP-100 as well (features.md 4).
   *
   *   ⭐ AND A SECOND COPY IS WORSE THAN A MOVED ONE. vsup needs the opcode's
   *      register field to reach 9's palette, so for one afternoon both parts
   *      carried the latch - vaddr's off the pixel bus, vsup's off the card's
   *      internal data bus - and vpal_tb proved they could disagree. One home
   *      for the decode, one net for the byte, and the question does not
   *      arise.
   *
   * What crosses now is three signals in and none of the state: LADV for this
   * increment, and LWHSL/LWHSH for 8's scroll holds above. LGRANT stopped
   * crossing to this part in the same move.
   *
   * 10.3.1's rule is unchanged and is still the price of 10.1.6.2 option 2:
   * the engine walks WPTR, so anything that starts a list reloads it after. */
]
