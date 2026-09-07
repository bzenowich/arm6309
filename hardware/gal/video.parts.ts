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
  ...[2, 3, 4, 5, 6, 7, 8, 9].map((b) => ({
    pin: 0, name: `HS${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: b < 10 ? [`LDHS & D${b - 2}`, `HS${b} & !LDHS`] : [],
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
  ...[0, 1, 2, 3, 4, 5, 6, 7].map((b) => ({
    pin: 0, name: `FB${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`LDFB & D${b}`, `FB${b} & !LDFB`],
  })),
  /* The map byte, latched off the pixel bus one cell ahead of the tile fetch
   * (§6.4.1's "pipelined one cell ahead"). §6.4.1 prices this as "one 3-state
   * '574, or zero packages if it can be absorbed into the scan-address GAL as
   * registered macrocells" - on a CPLD it is the second. */
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
export const addressMux = (withList = true): Cell[] => {
  const tileSrc = (bit: number) =>
    bit >= 14 ? `TB${bit - 14}` : bit >= 6 ? `MAP${bit - 6}` : bit >= 3 ? `V${bit - 3}` : "H2"
  const charSrc = (bit: number) =>
    bit >= 11 ? `FB${bit - 11}` : bit >= 3 ? `MAP${bit - 3}` : "V2"
  return [...Array(17).keys()].map((i) => {
    const bit = i + 2
    return {
      pin: 0, name: `FBA${bit}`, assertedLow: false, s0: 1 as const, registered: false,
      /* Five sources, which is exactly what an ATF15xx macrocell holds before
       * it has to cascade. The list engine is the fifth and it is why the
       * engine belongs on this part: its pointer feeds the address mux, so
       * putting it anywhere else makes nineteen crossing nets.
       *
       * Its select is LGRANT itself, not a separate LISTSEL pin: the engine
       * drives the address exactly when it holds the grant, the same identity
       * that makes vctrl's WRITESEL and SPNGRANT one signal. */
      terms: [
        `LINEAR & SA${bit}`,
        `WRITESEL & WA${bit}`,
        `TILESEL & ${tileSrc(bit)}`,
        `CHARSEL & ${charSrc(bit)}`,
        ...(withList ? [`LGRANT & LP${bit}`] : []),
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
  { pin: 0, name: "TILESEL", assertedLow: false, s0: 1, registered: false,
    terms: ["TILEMODE & !CHARMODE & TC2"] },
  { pin: 0, name: "CHARSEL", assertedLow: false, s0: 1, registered: false,
    terms: ["CHARMODE & TC2"] },
  { pin: 0, name: "LINEAR", assertedLow: false, s0: 1, registered: false,
    terms: ["!TILEMODE & !CHARMODE & !WRITESEL"] },
  /* Variant B's serialiser: the glyph bit goes straight to a spare LUT address
   * pin, so what the logic owns is the load and the shift (§6.4.3). */
  { pin: 0, name: "GLYPHLD", assertedLow: false, s0: 1, registered: false,
    terms: ["CHARMODE & SLOTTICK & TC1 & !TC0"] },
  { pin: 0, name: "GLYPHSH", assertedLow: false, s0: 1, registered: false,
    terms: ["CHARMODE & !SLOTTICK"] },
  /* §6.4.3's LUT page select: graphics is page 0, text page 1. One CTRL bit. */
  { pin: 0, name: "LUTPAGE", assertedLow: false, s0: 1, registered: false,
    terms: ["CHARMODE"] },
]

/* ---- §10.3's list engine ------------------------------------------------ *
 *
 * "Its MOVE opcode is one SRAM write into the register file, and the palette
 * it writes to already exists." That is why it costs almost no pins and a lot
 * of macrocells: it reads VRAM through the arbiter and the address path that
 * are already here, and writes the register file through one that is too. */
export const listEngine: Cell[] = [
  /* LIST, 19 bits (§13, +$0B..+$0D), auto-incrementing as it walks. */
  ...counterTerms({ bits: [...Array(19).keys()].map((i) => `LP${i}`), enable: "LADV" })
    .map((terms, i) => ({
      pin: 0, name: `LP${i}`, assertedLow: false, s0: 1 as const, registered: true,
      terms: terms.map((t) => `!LLOAD & ${t}`).concat(i < 8 ? [`LLOAD & D${i}`] : []),
    })),
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
