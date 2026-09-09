/* U3, the MMU sequencer, as product terms placed in macrocells.
 *
 * The same logic as mmu.pld. This is the form the assembler consumes, and it
 * differs from the CUPL file in two places where writing the fuses forced a
 * decision CUPL would have made silently. Both are noted below.
 */

import type { Design } from "./jedec/assemble"

/* $FF00-$FFFF - the term machine.md 2 brings to the backplane. */
const PAGE = "LA15 & LA14 & LA13 & LA12 & LA11 & LA10 & LA9 & LA8"
/* TWO block windows since 2026-09-09, and mmu.pld says why at length: a map
 * entry is sixteen bits across two SRAMs, the write index is LA3..LA0 through
 * U5's '157, and LA3 is therefore the TASK bit. Using it to pick the SRAM as
 * well - ram.md 4.1's Layout A - put the high byte in the other task's entry
 * and made everything above physical 2 MB unreachable. Two windows instead,
 * out of the 32 bytes at $FF80-$FF9F that decode nowhere. */
const BLK_HI = `${PAGE} & LA7 & !LA6 & !LA5 & LA4` // $FF90-$FF9F, high byte
const BLK_LO = `${PAGE} & LA7 & !LA6 & LA5 & !LA4` // $FFA0-$FFAF, low byte
/* $FFB0-$FFBF, the control register, aliased 16 times. */
const CTL = `${PAGE} & LA7 & !LA6 & LA5 & LA4`

export const mmuDesign: Design = {
  name: "mmu",
  partNo: "ARM6309-U3",
  location: "U3, motherboard",
  signature: "A6309U3",

  /* Pin 1 carries an address line, not a clock: nothing on this part is
   * registered, and a 2.0979 MHz bus cycle gets all the sequencing it needs
   * from E and Q in quadrature. Pins 14-16 are macrocells used as inputs,
   * which is what the pin budget in gal/README.md spends to make this fit. */
  inputs: [
    { name: "LA15", pin: 1 }, { name: "LA14", pin: 2 },
    { name: "LA13", pin: 3 }, { name: "LA12", pin: 4 },
    { name: "LA11", pin: 5 }, { name: "LA10", pin: 6 },
    { name: "LA9", pin: 7 }, { name: "LA8", pin: 8 },
    { name: "LA7", pin: 9 }, { name: "LA6", pin: 10 },
    { name: "LA5", pin: 11 }, { name: "LA4", pin: 13 },
    { name: "E", pin: 14 }, { name: "Q", pin: 15 }, { name: "RW", pin: 16 },
  ],

  cells: [
    { pin: 17, name: "IOPAGE", assertedLow: true, s0: 0, terms: [PAGE] },

    /* The mux switches on address decode alone, so the map SRAM sees its
     * write index from t_AD after E-fall - 367 ns of set-up against the
     * CY7C128A-15's 12 ns tAW. Tying this to MAPWE, as the board did, gave
     * it none. */
    { pin: 18, name: "MUXSEL", assertedLow: false, s0: 1, terms: [BLK_HI, BLK_LO] },

    /* E-high only, read or write. Turning the '245 on at E-rise rather than
     * Q-rise is what makes break-before-make comfortable: MAPOE has been away
     * since address time, so the margin is ~174 ns rather than ~9. */
    { pin: 19, name: "ISOOE", assertedLow: true, s0: 0,
      terms: [`${BLK_HI} & E`, `${BLK_LO} & E`] },

    /* Inside that window and a further quarter cycle later, so the buffer is
     * already driving. Releases at E-fall, before the buffer does. */
    /* Common to both SRAMs; the chip enable is what makes a write land in one
     * and not the other (u9.jedec.ts), and since 2026-09-09 that enable is the
     * WINDOW rather than LA3. */
    { pin: 20, name: "MAPWE", assertedLow: true, s0: 0,
      terms: [`${BLK_HI} & !RW & E & !Q`, `${BLK_LO} & !RW & E & !Q`] },

    /* MAPOE IS THE ONE EQUATION ON THIS PART THAT IS NOT ONE PRODUCT TERM,
     * and gal/README.md does not say so. As written in mmu.pld it is
     *
     *     MAPOE = !PAGE # BLK & RW & E
     *
     * and !PAGE is the complement of an eight-way AND, which is eight
     * separate product terms. That is 9, not 1. The README's "the widest is
     * an 8-input AND" is counting literals in a term, and the macrocell's
     * limit is terms.
     *
     * It fits either way - pin 21's macrocell has 12 - but the complement is
     * cheaper, and the pin is declared active low, so the macrocell can form
     * !MAPOE directly and let the polarity bit do nothing:
     *
     *     !MAPOE = PAGE & (!LA7 + LA6 + LA5&LA4 + !LA5&!LA4 + !RW + !E)
     *
     * Six terms with S0 = 1, against ten with S0 = 0. ⭐ It is STILL six with
     * two block windows: !(blkhi # blklo) is !LA7 + LA6 + LA5&LA4 + !LA5&!LA4,
     * which is four alternatives where the single window's !LA5 + LA4 was two
     * - and the two that grew are exactly the two the union deleted. A fitter
     * picks this silently; writing the fuses makes it a decision with a
     * reason. */
    {
      pin: 21, name: "MAPOE", assertedLow: true, s0: 1,
      why: "implemented complemented: 6 terms rather than 10",
      terms: [
        `${PAGE} & !LA7`, `${PAGE} & LA6`,
        `${PAGE} & LA5 & LA4`, `${PAGE} & !LA5 & !LA4`,
        `${PAGE} & !RW`, `${PAGE} & !E`,
      ],
    },

    /* The '574 must see ONE rising edge per control write, at E-fall, where
     * write data has been valid for 247 ns. The obvious equation
     * (ctlsel & !RW & !E) is wrong: E-low happens twice in a cycle and the
     * first is before write data exists. So the TERM is asserted for E-high
     * and the PIN is the complement - it falls at E-rise, which the '574
     * ignores, and rises at E-fall, which is the edge. */
    { pin: 22, name: "CTRLCP", assertedLow: true, s0: 0, terms: [`${CTL} & !RW & E`] },
  ],

  /* PIN 23 IS LEFT UNDRIVEN, and mmu.pld drives it low (`SPARE = 'b'0`).
   * That difference is the whole pin budget. gal/README.md's table chooses
   * the row "6 outputs, 16 available inputs, 15 needed, one pin spare" - but
   * a driven SPARE is a seventh output, which is the row above it: 15
   * available, 15 needed, nothing left. Undriven, the macrocell holds the pin
   * at high-Z and it is a sixteenth input if the board ever wants one. */
  spares: [23],
}
