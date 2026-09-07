/* U6 - the E/Q divider, /IOSEL, and the system RAM's control lines.
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
    /* PHYSICAL A19, out of the map SRAM, not off the CPU. */
    { name: "A19", pin: 7 },
    { name: "RW", pin: 8 },
  ],

  cells: [
    /* -- the divider ---------------------------------------------------- */
    /* C0 and C1 need no terminal-count term at all: both terminal counts
     * (11 = 1011 and 7 = 0111) have C1 = C0 = 1, so a plain toggle and a
     * plain XOR already land on zero. */
    { pin: 16, name: "C0", assertedLow: false, s0: 1, registered: true, terms: ["!C0"] },
    {
      pin: 17, name: "C1", assertedLow: false, s0: 1, registered: true,
      why: "C1 $ C0, expanded",
      terms: ["C1 & !C0", "!C1 & C0"],
    },

    /* C2 must be suppressed at 11, which would carry into a 12th count, but
     * not at 7, where the XOR already gives zero. Distributing
     * (C2 $ C1&C0) & !(!FAST_E & C3&C1&C0) leaves four terms: the two C2
     * terms already contain !C1 and !C0 and survive whole, and the third
     * splits on the suppression. */
    {
      pin: 20, name: "C2", assertedLow: false, s0: 1, registered: true,
      terms: ["C2 & !C1", "C2 & !C0", "!C2 & C1 & C0 & FAST_E", "!C2 & C1 & C0 & !C3"],
    },

    /* C3 exists only in /12. In fast-E mode the counter is three bits. */
    {
      pin: 21, name: "C3", assertedLow: false, s0: 1, registered: true,
      terms: ["!FAST_E & C3 & !C1", "!FAST_E & C3 & !C0", "!FAST_E & !C3 & C2 & C1 & C0"],
    },

    /* E is high for counts 6-11 (/12) or 4-7 (/8), so it decodes 5-10 or 3-6
     * of the NEXT count. Seven terms - the widest on the part, which is why
     * it is on pin 18. */
    {
      pin: 18, name: "E", assertedLow: false, s0: 1, registered: true,
      terms: [
        "!FAST_E & !C3 & C2 & C0", "!FAST_E & !C3 & C2 & C1",
        "!FAST_E & C3 & !C1", "!FAST_E & C3 & !C0",
        "FAST_E & !C3 & !C2 & C1 & C0", "FAST_E & !C3 & C2 & !C1",
        "FAST_E & !C3 & C2 & !C0",
      ],
    },

    /* Q is high for counts 3-8 (/12) or 2-5 (/8), so it decodes 2-7 or 1-4.
     * THE TAP IS DIVISOR-DEPENDENT: a quarter cycle is 3 counts at /12 and 2
     * at /8, and machine.md 1 reads as though it were 3 in both. */
    {
      pin: 19, name: "Q", assertedLow: false, s0: 1, registered: true,
      terms: [
        "!FAST_E & !C3 & C1", "!FAST_E & !C3 & C2",
        "FAST_E & !C3 & !C2 & C0", "FAST_E & !C3 & !C2 & C1",
        "FAST_E & !C3 & C2 & !C1 & !C0",
      ],
    },

    /* -- the two decodes ------------------------------------------------ */
    /* $FF40-$FF7F, common to every slot - machine.md 2, corrected from
     * "geographic, per slot". */
    { pin: 15, name: "IOSEL", assertedLow: true, s0: 0, terms: ["IOPAGE & LA7 & !LA6"] },

    /* System RAM is physical A19 = 0 and never during an I/O cycle. Both
     * terms are why /IOPAGE had to reach the backplane at all. */
    { pin: 22, name: "RAM_CE", assertedLow: true, s0: 0, terms: ["!IOPAGE & !A19"] },

    /* /OE qualified by R/W, which is not decoration: with /OE tied low the
     * SRAM drives D0-D7 from /CE time until /WE asserts while the CPU is also
     * driving write data - about 90 ns of contention on every write. */
    { pin: 14, name: "RAM_OE", assertedLow: true, s0: 0, terms: ["!IOPAGE & !A19 & RW"] },

    /* E-qualified, and decode-qualified as well. The decode is redundant - a
     * write needs CE# and WE# both low - but it keeps a glitch on /CE from
     * becoming a write. E here is this part's own output, fed back. */
    { pin: 23, name: "RAM_WE", assertedLow: true, s0: 0, terms: ["!IOPAGE & !A19 & !RW & E"] },
  ],

  /* The 22V10's asynchronous reset is ONE product term shared by every
   * registered macrocell, so the counter, E and Q all land together. There is
   * no other way to reset them on this part and no need for one. */
  ar: "RESET",
}
