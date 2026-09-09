/* U6 - the E/Q divider, /IOSEL, and boot mode.
 *
 * The same logic as clkdec.pld, with the equations hand-expanded into the sum
 * of products a 22V10 implements. That expansion is the error-prone step and
 * it is what jedec.check.ts checks, against the behavioural counter in
 * clkdec.model.ts.
 *
 * PIN PLACEMENT IS LOAD-BEARING. A 22V10's macrocells hold 8, 10, 12, 14, 16,
 * 16, 14, 12, 10, 8 terms across pins 14..23, so E (7 terms) and Q (5) sit on
 * the two 16-term macrocells. The counter bits land on pins nothing connects
 * to, which makes them four test points on the signal hardest to probe.
 */

import type { Design } from "./jedec/assemble"

export const clkdecDesign: Design = {
  name: "clkdec",
  partNo: "ARM6309-U6",
  location: "U6, motherboard",
  signature: "A6309U6",

  /* Pin 1 is the only clock a 22V10 has, and every registered macrocell on
   * the part shares it. */
  clockPin: 1,

  inputs: [
    { name: "FAST_E", pin: 2 },
    { name: "RESET", pin: 3, activeLow: true },
    /* From U3. This part does not form /IOPAGE - putting it here would add a
     * second GAL delay in series ahead of MAP_OE. */
    { name: "IOPAGE", pin: 4, activeLow: true },
    { name: "LA7", pin: 5 },
    { name: "LA6", pin: 6 },
    /* LA5 and LA4 select $FFA0-$FFBF and then its two halves. They took the
     * pins physical A19 and A20 held for the system RAM's decode until
     * 2026-09-09 - hardware/ram.md 6.2 deleted that part a day earlier. */
    { name: "LA5", pin: 7 },
    { name: "RW", pin: 8 },
    { name: "LA4", pin: 9 },
    /* /WAIT from the backplane, active high after the slot's open-drain
     * inversion. It holds every registered macrocell below - machine.md 5
     * item 8, and clkdec.pld carries the two rules that go with it. */
    { name: "WAIT", pin: 10 },
    /* $FFB0 even is TASK, $FFB1 odd is BOOT - machine.md 3. One literal, and
     * it is what lets boot code write TASK without leaving boot mode. */
    { name: "LA0", pin: 11 },
  ],

  cells: [
    /* -- the divider ---------------------------------------------------- */
    /* C0 and C1 need no terminal-count term at all: both terminal counts
     * (11 = 1011 and 7 = 0111) have C1 = C0 = 1, so a plain toggle and a
     * plain XOR already land on zero. */
    { pin: 16, name: "C0", assertedLow: false, s0: 1, registered: true, terms: ["!C0 & !WAIT", "C0 & WAIT"] },
    {
      pin: 17, name: "C1", assertedLow: false, s0: 1, registered: true,
      why: "C1 $ C0, expanded",
      terms: ["C1 & !C0 & !WAIT", "!C1 & C0 & !WAIT", "C1 & WAIT"],
    },

    /* C2 must be suppressed at 11, which would carry into a 12th count, but
     * not at 7, where the XOR already gives zero. Distributing
     * (C2 $ C1&C0) & !(!FAST_E & C3&C1&C0) leaves four terms: the two C2
     * terms already contain !C1 and !C0 and survive whole, and the third
     * splits on the suppression. */
    {
      pin: 20, name: "C2", assertedLow: false, s0: 1, registered: true,
      terms: ["C2 & !C1 & !WAIT", "C2 & !C0 & !WAIT", "!C2 & C1 & C0 & FAST_E & !WAIT",
        "!C2 & C1 & C0 & !C3 & !WAIT", "C2 & WAIT"],
    },

    /* C3 exists only in /12. In fast-E mode the counter is three bits. */
    {
      pin: 21, name: "C3", assertedLow: false, s0: 1, registered: true,
      terms: ["!FAST_E & C3 & !C1 & !WAIT", "!FAST_E & C3 & !C0 & !WAIT",
        "!FAST_E & !C3 & C2 & C1 & C0 & !WAIT", "C3 & WAIT"],
    },

    /* E is high for counts 6-11 (/12) or 4-7 (/8), so it decodes 5-10 or 3-6
     * of the NEXT count. Seven terms - the widest on the part, which is why
     * it is on pin 18. */
    {
      pin: 18, name: "E", assertedLow: false, s0: 1, registered: true,
      terms: [
        "!FAST_E & !C3 & C2 & C0 & !WAIT", "!FAST_E & !C3 & C2 & C1 & !WAIT",
        "!FAST_E & C3 & !C1 & !WAIT", "!FAST_E & C3 & !C0 & !WAIT",
        "FAST_E & !C3 & !C2 & C1 & C0 & !WAIT", "FAST_E & !C3 & C2 & !C1 & !WAIT",
        "FAST_E & !C3 & C2 & !C0 & !WAIT",
        "E & WAIT",
      ],
    },

    /* Q is high for counts 3-8 (/12) or 2-5 (/8), so it decodes 2-7 or 1-4.
     * THE TAP IS DIVISOR-DEPENDENT: a quarter cycle is 3 counts at /12 and 2
     * at /8, and machine.md 1 reads as though it were 3 in both. */
    {
      pin: 19, name: "Q", assertedLow: false, s0: 1, registered: true,
      terms: [
        "!FAST_E & !C3 & C1 & !WAIT", "!FAST_E & !C3 & C2 & !WAIT",
        "FAST_E & !C3 & !C2 & C0 & !WAIT", "FAST_E & !C3 & !C2 & C1 & !WAIT",
        "FAST_E & !C3 & C2 & !C1 & !C0 & !WAIT",
        "Q & WAIT",
      ],
    },

    /* -- the two decodes ------------------------------------------------ */
    /* $FF00-$FF7F. One literal: the widening in clkdec.pld deleted LA6. */
    { pin: 15, name: "IOSEL", assertedLow: true, s0: 0, terms: ["IOPAGE & !LA7"] },

    /* -- boot mode, 2026-09-09 ------------------------------------------ */
    /* machine.md 7.2. RUN = 0 is boot mode and it is zero AT RESET, which is
     * not a preference: a 22V10 has one asynchronous reset term shared by
     * every registered macrocell and it resets to ZERO. A bit that had to
     * come up SET could not live on this part, so the register holds /BOOT
     * and the board carries RUN.
     *
     * Set by one write to $FFB1, cleared by nothing but /RESET - so a wild
     * store cannot put the machine back into boot mode over live RAM. $FFB0
     * (LA0 = 0) is TASK and does not set it, which is what lets boot code
     * write TASK, then the map, then $FFB1, in that order. */
    {
      pin: 22, name: "RUN", assertedLow: false, s0: 1, registered: true,
      terms: ["RUN", "IOPAGE & LA7 & !LA6 & LA5 & LA4 & LA0 & !RW & E"],
    },

    /* The '244 drives physical A20-A13 whenever the map SRAMs do not. U9
     * forms their /CE from the same two conditions, so the changeover is one
     * signal seen by two parts rather than two decodes that have to agree.
     *
     * VECSEL is ONE product term because /IOPAGE already means "logical
     * $FF00-$FFFF" - $FFC0-$FFFF is that page with A7 and A6 both high, and
     * both are on this part already. */
    {
      pin: 14, name: "BOOTOE", assertedLow: true, s0: 0,
      terms: ["!RUN", "IOPAGE & LA7 & LA6"],
    },
  ],

  /* The 22V10's asynchronous reset is ONE product term shared by every
   * registered macrocell, so the counter, E, Q and RUN all land together.
   * There is no other way to reset them on this part and no need for one -
   * and RUN = 0 IS boot mode, which is why the register holds that sense
   * rather than its complement. */
  ar: "RESET",
}
