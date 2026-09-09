/* U9 - the physical space decode. hardware/ram.md 6.3 and 6.7.
 *
 * The same logic as u9.pld, with the equations hand-expanded into the sum of
 * products a 22V10 implements. That expansion is the error-prone step and it
 * is what jedec.check.ts checks, against u9.model.ts.
 *
 * ram.md 11 item 6 said this part was "no longer obviously comfortable" - ten
 * outputs counted against a 22V10's ten, before counting inputs. THE COUNT WAS
 * WRONG IN BOTH DIRECTIONS and the fit is what found it:
 *
 *   - FOUR SIMM SELECTS ARE NOT NEEDED. The four windows sit at physical
 *     A24..A22 = 001, 010, 011, 100, and those four codes are already distinct
 *     in A23:A22 alone. U10 takes physical A23 and A22 as inputs and picks its
 *     own RAS; U9 says only WHETHER a SIMM answers. Three outputs became one.
 *   - TWO MAP-SRAM CHIP ENABLES ARE. They were not on the list at all. ram.md
 *     3.1 says "both SRAMs sit on the same D0-D7; the address picks which is
 *     written", and nothing had said what forms that. It is LA3, here.
 *   - BOOT AND VECSEL WENT TO U6, which already had CLK25 on pin 1, /RESET in
 *     the array and LA7/LA6 on pins. A 22V10 has one clock and one reset; a
 *     part that needs a registered mode bit either has them already or pays
 *     three pins for them.
 *
 * Net: six outputs, fourteen inputs, and the widest equation is five terms on
 * a macrocell that holds sixteen.
 */

import type { Design } from "./jedec/assemble"

export const u9Design: Design = {
  name: "u9",
  partNo: "ARM6309-U9",
  location: "U9, motherboard",
  signature: "A6309U9",

  /* PURELY COMBINATIONAL, so pin 1 carries an address line rather than a
   * clock - the same call mmu.pld makes. The one registered bit on the
   * motherboard's decode path, RUN, is on U6 and arrives here as an input. */

  inputs: [
    /* Physical A24..A19, off the two map SRAMs. A24..A21 come from the HIGH
     * byte (ram.md 3.1) and float while boot mode has it deselected - which
     * is why every equation that reads them is qualified on RUN. */
    { name: "A24", pin: 1 },
    { name: "A23", pin: 2 },
    { name: "A22", pin: 3 },
    { name: "A21", pin: 4 },
    { name: "A20", pin: 5 },
    { name: "A19", pin: 6 },
    /* U3's term, NOT the backplane wire. This part drives the backplane's
     * /IOPAGE, so reading it back would be a combinational loop: above 2 MB
     * U9 pulls it low, which would then de-qualify the SIMM decode that
     * asserted it. machine.md 2 owns the redefinition; the two nets are the
     * price of it and netlist.check.ts asserts they stay separate. */
    { name: "IOPAGE", pin: 7, activeLow: true },
    /* U6's RUN register. 0 is boot mode - clkdec.pld explains why the sense
     * is this way round and not the other. */
    { name: "RUN", pin: 8 },
    { name: "LA7", pin: 9 },
    { name: "LA6", pin: 10 },
    { name: "LA5", pin: 11 },
    { name: "LA4", pin: 13 },
    /* On macrocell pins, which is where inputs belong when the macrocells are
     * the narrow ones: pin 14 and pin 23 hold 8 product terms each and an
     * input costs none. */
    { name: "LA3", pin: 14 },
    { name: "RW", pin: 23 },
  ],

  cells: [
    /* -- the map SRAMs, 2026-09-09 -------------------------------------- */
    /* Selected for translation on every ordinary cycle, and by the CPU during
     * a block-register access. DESELECTED for the whole of boot mode and for
     * the vector page - exactly when U6 has the buffer driving the physical
     * address instead.
     *
     * The !IOPAGE term already excludes the vector page, because the vector
     * page is inside $FF00-$FFFF. That is why this is two terms and not five.
     *
     * LA3 splits the block-register window: ram.md 4.1 Layout A puts blocks
     * 0-7's low byte at $FFA0-$FFA7 and their high byte at $FFA8-$FFAF. U3's
     * MAPWE is common to both parts and never sees LA3; the chip enable is
     * what makes a write land in one SRAM and not the other, which is the
     * cheapest place to put it - U3 has no pin for LA3 and this part does. */
    {
      pin: 15, name: "MAPCE_LO", assertedLow: true, s0: 0,
      terms: ["RUN & !IOPAGE", "IOPAGE & LA7 & !LA6 & LA5 & !LA4 & !LA3"],
    },
    {
      pin: 16, name: "MAPCE_HI", assertedLow: true, s0: 0,
      terms: ["RUN & !IOPAGE", "IOPAGE & LA7 & !LA6 & LA5 & !LA4 & LA3"],
    },

    /* -- the boot ROM ---------------------------------------------------- */
    /* Three ways in, and the first two ignore the physical address entirely:
     *
     *   RUN = 0 outside $FF00-$FFBF   boot mode. At reset the map SRAM holds
     *                                 whatever it powered up holding, so a
     *                                 decode that trusted it could not work
     *   $FFC0-$FFFF                   the vector page, forever. $FFFE is a
     *                                 reset vector and not an undriven bus
     *   physical 2.0-3.0 M            ordinary read-only memory, mapped in
     *                                 8 KB blocks like anything else
     *
     * Physical A19 picks the device; the buffer drives it low during the first
     * two, so both land in device 0's first 8 KB.
     *
     * R/W IS IN THE CHIP ENABLE and /OE is tied low on both devices. The same
     * move gal/README.md argues for the system RAM's /OE, for the same reason:
     * a part that drives during a write cycle fights the CPU for the whole of
     * E-high. Here it also means a stray write to ROM space is a no-op rather
     * than a bus fight. */
    {
      pin: 17, name: "ROMCE0", assertedLow: true, s0: 0,
      terms: [
        "!RUN & !IOPAGE & !A19 & RW",
        "IOPAGE & LA7 & LA6 & !A19 & RW",
        "!IOPAGE & !A24 & !A23 & !A22 & A21 & !A20 & !A19 & RW",
      ],
    },
    {
      pin: 20, name: "ROMCE1", assertedLow: true, s0: 0,
      terms: [
        "!RUN & !IOPAGE & A19 & RW",
        "IOPAGE & LA7 & LA6 & A19 & RW",
        "!IOPAGE & !A24 & !A23 & !A22 & A21 & !A20 & A19 & RW",
      ],
    },

    /* -- the backplane's /IOPAGE ----------------------------------------- */
    /* U3's term, plus every access above the bottom 2 MB. ram.md 5.3: cards
     * decode A0-A20 and an access at 2.5 MB would look to one exactly like an
     * access at 0.5 MB, so the motherboard silences them all instead of
     * giving every slot four more address pins it has not got.
     *
     * GATED ON RUN, and it is the subtle one. During boot the HIGH map SRAM is
     * deselected and A24..A21 float. An ungated compare would assert /IOPAGE
     * at random - and /IOSEL is /IOPAGE AND /A7 (clkdec.pld), so a random
     * assertion makes every card in the machine decode a boot fetch against
     * its jumpered base and drive D0-D7. Five terms instead of four, and it
     * is the difference between a machine that boots and one that does not.
     *
     * Sixteen product terms on pin 18, five used - this is the widest
     * equation on the part and it sits on the widest macrocell. */
    {
      pin: 18, name: "IOPAGE_BP", assertedLow: true, s0: 0,
      terms: ["IOPAGE", "RUN & A24", "RUN & A23", "RUN & A22", "RUN & A21"],
    },

    /* -- the SIMM windows ------------------------------------------------ */
    /* Four 4 MB windows at 4-20 M: physical A24..A22 = 001, 010, 011, 100.
     * WHICH window is not encoded here - those four codes are already distinct
     * in A23:A22, so U10 takes those two lines directly and picks its own RAS.
     * That is three outputs this part does not spend and two inputs U10 needs
     * anyway for its address mux. */
    {
      pin: 19, name: "DRAMSEL", assertedLow: false, s0: 1,
      terms: [
        "!IOPAGE & RUN & !A24 & !A23 & A22",
        "!IOPAGE & RUN & !A24 & A23 & !A22",
        "!IOPAGE & RUN & !A24 & A23 & A22",
        "!IOPAGE & RUN & A24 & !A23 & !A22",
      ],
    },

    /* PINS 21 AND 22 ARE DELIBERATELY NOT DECLARED, and that is two spare
     * INPUTS rather than two driven lows - the distinction mmu.pld's pin 23
     * had to learn the hard way (gal/README.md finding 6). U10 is unfitted and
     * this is the part next to it. */
  ],
}
