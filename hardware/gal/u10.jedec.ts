/* U10 - the SIMM controller. hardware/ram.md 6.3, 6.6.
 *
 * The same logic as u10.pld, hand-expanded into the sum of products a 22V10
 * implements, and checked against u10.model.ts by jedec.check.ts.
 *
 * ram.md 6.3 gave this part one line - "SIMM timing: RAS0-RAS3, CAS, /WE, the
 * mux select, refresh request and /WAIT" - and §11 item 6 said it "has not been
 * counted at all". Counting it moved three things:
 *
 *   - ⭐ THE MUX SELECT IS `E`. It is not an output. E is high for counts 6..11
 *     of U6's divider, which is exactly the column window, so the '157s take a
 *     wire from the backplane. That is the macrocell that made this fit.
 *   - ⭐ /WAIT IS NOT NEEDED. A bus cycle is twelve CLK25 counts and the access
 *     owns six of them; a CAS-before-RAS burst is four and fits in the gap. The
 *     DRAM controller never stalls the CPU, which makes it the second thing in
 *     the machine that never does.
 *   - ⚠ THE REFRESH TIMEBASE IS A PACKAGE, and it was never on anyone's list.
 *     §6.3's "refresh needs no counter" is about the ROW counter, which
 *     CAS-before-RAS genuinely deletes. The INTERVAL timer is a different
 *     thing: 15.6 us of CLK25 is 393 counts, which is nine macrocells on a part
 *     that has ten. It is a 74HC4040 - see ram.md 6.3.1.
 *
 * Net: nine outputs, eleven inputs, two spare pins, widest equation five terms.
 */

import type { Design } from "./jedec/assemble"

export const u10Design: Design = {
  name: "u10",
  partNo: "ARM6309-U10",
  location: "U10, motherboard",
  signature: "A6309U10",

  /* Registered - the refresh sequencer runs on CLK25 and MUST, because /WAIT
   * freezes everything derived from E and a frozen refresh is lost data. */
  clockPin: 1,

  inputs: [
    /* U9's space decode. It already carries !IOPAGE and RUN, so this part
     * needs neither: during boot DRAMSEL is low, which means refresh runs from
     * the moment /RESET releases and the DRAM is ready before machine.md 7.2's
     * boot sequence hands it a stack. */
    { name: "DRAMSEL", pin: 2 },
    /* ⭐ Physical A23:A22, taken directly rather than as four selects from U9.
     * ram.md 5.2 puts the windows at A24..A22 = 001, 010, 011, 100, so A23:A22
     * is 01, 10, 11, 00 - already distinct. That is three outputs U9 does not
     * spend, and two inputs this part needs for its address mux anyway. */
    { name: "A23", pin: 3 },
    { name: "A22", pin: 4 },
    /* U6's divider count. THE BUS PHASE, and it is host-facing on purpose:
     * these freeze when /WAIT freezes them, and so does the access. */
    { name: "C0", pin: 5 },
    { name: "C1", pin: 6 },
    { name: "C2", pin: 7 },
    { name: "C3", pin: 8 },
    { name: "RW", pin: 9 },
    /* ⚠ A FREE-RUNNING DIVIDER OF CLK25, not of E - the 74HC4040's Q8, one
     * toggle per 256 counts = 10.16 us. Every transition is one refresh, so
     * 512 rows take 5.2 ms against the DRAM's 8 ms. It must not be derived
     * from E: machine.md 5 item 10, and the 40.7 us the video card can hold
     * the bus is 2.6 refresh intervals. */
    { name: "REFCLK", pin: 10 },
    { name: "RESET", pin: 11, activeLow: true },
    /* PIN 13 IS FREE, and so is pin 23 below. */
  ],

  cells: [
    /* -- the refresh sequencer ------------------------------------------ */
    /* Four states: 00 idle, 01 CAS low, 10 RAS low, 11 RAS held, back to 00.
     * CAS-before-RAS - the DRAM counts the row itself, which is what deletes
     * the row counter and its mux path (ram.md 6.3).
     *
     * ⚠ RAS IS LOW FOR TWO COUNTS - 79 ns. That is the tightest number on this
     * part: t_RAS min is ~70 ns on a 70 ns module and ~60 on a 60 ns one, so
     * the margin is 9 ns or 19. A third count needs a five-state sequencer,
     * which is a third macrocell this part has not got. ram.md 6.3.1 makes it
     * a speed-grade requirement instead. */
    {
      pin: 16, name: "RF0", assertedLow: false, s0: 1, registered: true,
      why: "00 -> 01 on a pending request in a safe window; 10 -> 11",
      terms: [
        /* start = pending & safe, distributed: pending is REFCLK xor REFQ and
         * safe is "not a DRAM cycle" or "count 10 or 11". */
        "!RF1 & !RF0 & REFCLK & !REFQ & !DRAMSEL",
        "!RF1 & !RF0 & REFCLK & !REFQ & C3 & !C2 & C1",
        "!RF1 & !RF0 & !REFCLK & REFQ & !DRAMSEL",
        "!RF1 & !RF0 & !REFCLK & REFQ & C3 & !C2 & C1",
        "RF1 & !RF0",
      ],
    },
    {
      pin: 14, name: "RF1", assertedLow: false, s0: 1, registered: true,
      why: "01 -> 10, 10 -> 11",
      terms: ["!RF1 & RF0", "RF1 & !RF0"],
    },

    /* ⭐ ONE MACROCELL IS BOTH THE EDGE DETECTOR AND THE REQUEST LATCH.
     * REFQ holds the REFCLK level that the last refresh consumed, so
     * `REFCLK != REFQ` is "a request is outstanding" - and it is updated at the
     * END of the burst, so an edge arriving mid-burst is still seen afterwards
     * rather than lost. A separate pending flag would have been a tenth
     * macrocell and there is no tenth. */
    {
      pin: 15, name: "REFQ", assertedLow: false, s0: 1, registered: true,
      terms: ["REFQ & !RF1", "REFQ & !RF0", "REFCLK & RF1 & RF0"],
    },

    /* -- the four /RAS --------------------------------------------------- */
    /* An access asserts one; a refresh asserts all four, because every bank
     * has to be refreshed and CAS-before-RAS is a broadcast.
     *
     * The access window is counts 4..9 - RAS falls 158.8 ns after E-fall,
     * which is 48.8 ns after the address goes valid at t_AD, and releases at
     * count 10 leaving 238 ns of precharge. */
    ...([[0, "!A23 & A22"], [1, "A23 & !A22"], [2, "A23 & A22"], [3, "!A23 & !A22"]] as const)
      .map(([n, bank], i) => ({
        pin: [17, 19, 20, 21][i],
        name: `RAS${n}`,
        assertedLow: true as const,
        s0: 0 as const,
        terms: [
          `DRAMSEL & ${bank} & !C3 & C2`,
          `DRAMSEL & ${bank} & C3 & !C2 & !C1`,
          "RF1",
        ],
      })),

    /* -- /CAS, common to all four sockets -------------------------------- */
    /* Counts 7..9 for an access: 79 ns of row hold after RAS, 40 ns of column
     * setup, and - for a write - 49 ns of data setup, because 6809 write data
     * is valid at 229 ns and this falls at 278.
     *
     * Low for the whole of a refresh burst, RF != 00, which is what puts it
     * before RAS. */
    {
      pin: 18, name: "CAS", assertedLow: true, s0: 0,
      terms: [
        "DRAMSEL & !C3 & C2 & C1 & C0",
        "DRAMSEL & C3 & !C2 & !C1",
        "RF0",
        "RF1",
      ],
    },

    /* -- the SIMMs' shared /WE ------------------------------------------- */
    /* EARLY WRITE: /WE leads CAS by three counts, so the module takes its data
     * at CAS-fall and never drives D0-D7 at all. A late write would put the
     * SIMM's output on the bus during a write cycle, which is the same
     * contention gal/README.md argues about for the system RAM's /OE. */
    {
      pin: 22, name: "DWE", assertedLow: true, s0: 0,
      terms: ["DRAMSEL & !RW & !C3 & C2", "DRAMSEL & !RW & C3 & !C2 & !C1"],
    },

    /* PIN 23 IS DELIBERATELY NOT DECLARED - a spare INPUT and not a driven
     * low, the distinction mmu.pld's pin 23 had to learn (gal/README.md
     * finding 6). With pin 13 that is two spare inputs. */
  ],

  /* The 22V10's one asynchronous reset, shared by the sequencer and REFQ, so
   * the part comes out of reset idle with no request outstanding. */
  ar: "RESET",
}
