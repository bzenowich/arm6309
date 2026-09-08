/* The pieces of the video card that exist only once the GALs merge, plus the
 * three blocks graphics.md puts in v1 and nobody had written.
 *
 * Kept apart from video.cpld.ts so the partition can be argued with without
 * touching the logic.
 */

import type { Cell } from "./jedec/assemble"
import { counterTerms } from "./jedec/counter"

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
  ...[2, 3, 4, 5, 6, 7].map((b) => ({
    pin: 0, name: `HS${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`LDHS & D${b}`, `HS${b} & !LDHS`],
  })),
  ...[8, 9].map((b) => ({
    pin: 0, name: `HS${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`LDHSH & D${b - 8}`, `HS${b} & !LDHSH`],
  })),
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
   * sixteen pixels. */
  const tileSrc = (bit: number) =>
    bit >= 14 ? `TB${bit - 14}` : bit >= 6 ? `MAP${bit - 6}` : bit >= 3 ? `V${bit - 3}` : "SA2"
  /* The map's own address - base, cell row, cell column - which the mux did
   * not have at all, so MAPLD was latching a byte from an address nothing
   * generated. §19 item 16 lives here and it costs nothing: the intra-cell
   * offset is {SA2, mux phase}, and §8 already preloads the column counter
   * with HSCROLL[9:2] and the phase with HSCROLL[1:0]. Both halves are
   * therefore already scrolled. §6.4.6 calls sub-cell scroll "new logic in
   * the address concatenation"; it is not, PROVIDED the map byte for a cell
   * is fetched before that cell's first pixel - a cadence requirement, not an
   * address one. */
  const mapSrc = (bit: number) =>
    bit >= 12 ? `MB${bit - 12}` : bit >= 5 ? `SA${bit - 2}` : `V${bit + 1}`
  return [...Array(17).keys()].map((i) => {
    const bit = i + 2
    return {
      pin: 0, name: `FBA${bit}`, assertedLow: false, s0: 1 as const, registered: false,
      /* FOUR sources since 2026-09-08, and both changes that day were about
       * this list. 6.4.3's Variant B took CHARSEL out; 10.1.6.2's option 2
       * means the list engine never adds one, because it drives the address
       * through WRITESEL & WA[n] - WPTR IS its pointer.
       *
       * That second point is the whole reason the engine fits. Its own
       * nineteen-bit pointer was not just 19 registers: it was 19 more mux
       * inputs and a SIXTH product term on every one of these seventeen
       * macrocells, and an ATF15xx macrocell holds five before it cascades. */
      terms: [
        `LINEAR & SA${bit}`,
        `WRITESEL & WA${bit}`,
        `TILESEL & ${tileSrc(bit)}`,
        `MAPSEL & ${mapSrc(bit)}`,
      ],
    }
  })
}

/* ---- §6.4.2/6.4.3's fetch cadence -------------------------------------- *
 *
 * Variant A is map byte then eight tile bytes; Variant B is code, attribute
 * and one font row - "3 accesses per 8 dots against the bitmap's 8". Both are
 * a second cadence on top of §5.2.2's slot, and §19 item 15(c) names it as the
 * open question. */
export const tileCadence: Cell[] = [
  ...counterTerms({ bits: ["TC0", "TC1", "TC2"], enable: "SLOTTICK" })
    .map((terms, i) => ({
      pin: 0, name: `TC${i}`, assertedLow: false, s0: 1 as const, registered: true, terms,
    })),
  { pin: 0, name: "MAPLD", assertedLow: false, s0: 1, registered: false,
    terms: ["TILEMODE & SLOTTICK & !TC2 & !TC1 & !TC0"] },
  /* The map fetch owns the address for the first slot of the cell; the tile
   * or glyph fetch owns it afterwards. MAPLEAD is why sub-cell scroll works:
   * when a line starts mid-cell the map byte for that cell must already be
   * held, so the fetch leads by one cell rather than by one slot. */
  { pin: 0, name: "MAPSEL", assertedLow: false, s0: 1, registered: false,
    terms: ["CELL & !TC2"] },
  { pin: 0, name: "TILESEL", assertedLow: false, s0: 1, registered: false,
    terms: ["TILEMODE & TC2"] },
  { pin: 0, name: "LINEAR", assertedLow: false, s0: 1, registered: false,
    terms: ["!TILEMODE & !WRITESEL"] },
  /* ⚠ VARIANT B WAS DROPPED 2026-09-08 - graphics.md 6.4.3 and 10.1.6.2.
   * CHARSEL, GLYPHLD, GLYPHSH and LUTPAGE lived here, and the eight FONTBASE
   * registers above; what they bought was a 1bpp hardware character generator
   * at 2 CPU writes per cell against the span writer's 13.
   *
   * They were spent on the display list, which needs the macrocells, the
   * product terms and the four pins. The trade is 105 Hz full-screen text
   * against 16 Hz - and 0.38 ms per scrolled line against 2.5 ms, which is
   * the figure a terminal actually pays. A 9600-baud BBS delivers twelve
   * lines a second, so that is 3% of the CPU. Text still works; it is the
   * span writer in bitmap mode, which is what 7.1-7.3 already cost out.
   *
   * !CHARMODE dropped out of TILESEL and LINEAR above rather than being
   * deleted: with no char mode, TILEMODE alone says which it is. */
]

/* ---- §10.3's list engine ------------------------------------------------ *
 *
 * "Its MOVE opcode is one SRAM write into the register file, and the palette
 * it writes to already exists." That is why it costs almost no pins and a lot
 * of macrocells: it reads VRAM through the arbiter and the address path that
 * are already here, and writes the register file through one that is too. */
export const listEngine: Cell[] = [
  /* ⚠ THE ENGINE HAS NO POINTER OF ITS OWN - 10.1.6.2's option 2, taken
   * 2026-09-08 because it is the only thing that makes the engine fit.
   *
   * It used to carry LIST as 19 registers here (§13, +$0B..+$0D), auto-
   * incrementing as it walked, and that cost far more than 19 macrocells: 19
   * more inputs to the address mux and a SIXTH product term on each of its
   * seventeen bits, past what an ATF15xx macrocell holds before cascading.
   * With them the fitter did not report a shortage, it reported INTERNAL
   * ERROR; without them the design fits a PLCC-84.
   *
   * SO WPTR IS THE LIST POINTER. The span writer and the engine never drive
   * the address in the same slot, LADV drives WPTR's increment, and the
   * engine reaches the address bus through the mux's WRITESEL & WA[n] term
   * that already exists.
   *
   * ⚠ THE PRICE IS SOFTWARE'S, and it is not settled here: the engine
   * CLOBBERS THE CPU'S WRITE POINTER, so anything that starts a list reloads
   * WPTR afterwards. 10.3 owns that decision; this file only shows it fits. */
  /* The descriptor byte, and the opcode decode that turns it into a write. */
  ...[0, 1, 2, 3, 4, 5, 6, 7].map((b) => ({
    pin: 0, name: `LD${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`LFETCH & PB${b}`, `LD${b} & !LFETCH`],
  })),
  { pin: 0, name: "LRUN", assertedLow: false, s0: 1, registered: true,
    terms: ["BCTRLGO", "LRUN & !LSTOP"] },
  { pin: 0, name: "LSTOP", assertedLow: false, s0: 1, registered: false,
    terms: ["LRUN & LD7 & LD6 & LD5 & LD4 & LD3 & LD2 & LD1 & LD0"] },
  { pin: 0, name: "LADV", assertedLow: false, s0: 1, registered: false,
    terms: ["LRUN & LGRANT"] },
  { pin: 0, name: "LFETCH", assertedLow: false, s0: 1, registered: false,
    terms: ["LRUN & LGRANT"] },
  { pin: 0, name: "LMOVE", assertedLow: false, s0: 1, registered: false,
    terms: ["LRUN & !LSTOP & LGRANT"] },
]
