/* Package pinouts for the parts the motherboard fits.
 *
 * Pin numbers are read off the datasheets in reference/datasheets/, which were
 * fetched 2026-09-06 from Digi-Key and Mouser for exactly this purpose. Before
 * that they were written from familiarity and marked unverified, and one of the
 * five was wrong - see MAP_SRAM below. Every part here now names its source.
 *
 * The signal *names* are this board's, and a few differ from the datasheet's on
 * purpose; where they do, the difference is noted with the part. The names are
 * what mainboard.circuit.tsx connects by, so they are load-bearing in a way the
 * numbers only become at layout.
 */

export interface PartDef {
  /** DIP pin number -> signal name on the package. */
  pins: Record<number, string>
  footprint: string
  /** Where the pin numbering came from. "unverified" needs a datasheet. */
  provenance: "confirmed" | "unverified"
  /** The document the numbering was read from. Required once confirmed. */
  source?: string
}

const range = (start: number, names: string[]) =>
  Object.fromEntries(names.map((n, i) => [start + i, n]))

/* -- the CPU module's 40-pin socket -------------------------------------- */
/* MC6809E / HD6309E DIP-40. The module plugs in here; docs/machine.md 5 item 5
 * is settled this way, so one hardware SKU serves the CoCo 3 and this machine
 * literally rather than by recompilation. */
export const CPU_SOCKET: PartDef = {
  provenance: "confirmed",
  source: "cpu/docs/plan.md 2.6 (CoCo 3 Service Manual, Cat. 26-3334, IC1)",
  footprint: "dip40_w0.6in",
  pins: {
    1: "GND", 2: "/NMI", 3: "/IRQ", 4: "/FIRQ", 5: "BS", 6: "BA", 7: "VCC",
    ...range(8, ["A0","A1","A2","A3","A4","A5","A6","A7",
                 "A8","A9","A10","A11","A12","A13","A14","A15"]),
    ...range(24, ["D7","D6","D5","D4","D3","D2","D1","D0"]),
    32: "R/W", 33: "BUSY", 34: "E", 35: "Q", 36: "AVMA",
    37: "/RESET", 38: "/LIC", 39: "TSC", 40: "/HALT",
  },
}

/* -- the five MMU packages, video/docs/graphics.md 6.3.1 ------------------ */

/** 2K x 8 SRAM, 15 ns - the block map. Sixteen of 2048 locations are used.
 *
 * This is the one part the datasheet caught. Pins 21-23 were A9/A8//WE here and
 * are /WE/A9/A8 on the part - the three were rotated. That is the 6116 numbering
 * rather than anything Cypress-specific, so the error was ours and not a
 * part-choice question. The width was wrong with it: the CY7C128A's DIP is the
 * 300-mil skinny package, not the 600-mil one drawn before. The datasheet names
 * the data pins I/O0-I/O7; DQ0-DQ7 here matches SRAM_512K below and is what the
 * motherboard connects by. */
export const MAP_SRAM: PartDef = {
  provenance: "confirmed",
  source: "reference/datasheets/CY7C128A.pdf p.1 (CY7C128A-15PC, 300-mil DIP-24)",
  footprint: "dip24_w0.3in",
  pins: {
    ...range(1, ["A7","A6","A5","A4","A3","A2","A1","A0"]),
    ...range(9, ["DQ0","DQ1","DQ2"]),
    12: "GND",
    ...range(13, ["DQ3","DQ4","DQ5","DQ6","DQ7"]),
    18: "/CE", 19: "A10", 20: "/OE", 21: "/WE", 22: "A9", 23: "A8", 24: "VCC",
  },
}

/* ⛔ HCT, NOT HC, FOR EVERY PART THAT TAKES THE CPU'S ADDRESS OR WRITE DATA -
 * since 2026-09-11. The CPU module fronts the bus with 74LVC buffers at 3.3 V
 * (cpu/docs/plan.md 2.6: "3.3 V V_OH must satisfy every downstream V_IH"), and
 * a 74HC input at V_CC = 5 V needs 0.7 x V_CC = 3.5 V to see a one. HCT's is
 * 2.0 V. U2, U4, U18, U5 and U11-U13 all read the module directly; U16 was
 * already HCT. Pinouts are identical across the two families, so - exactly as
 * HCT244 below does - the numbering is read from the HC datasheet in
 * reference/datasheets/. */

/** 74HCT574 - TASK, the one bit of $FFB0-$FFBF, clocked from D0 at E-fall.
 * Verified as drawn. The datasheet writes the data pins 1D-8D and the clock
 * CLK; D1-D8 and CP here are the older names for the same pins. */
export const HCT574: PartDef = {
  provenance: "confirmed",
  source: "reference/datasheets/sn74hc574.pdf p.3 (SCLS148H, N package)",
  footprint: "dip20_w0.3in",
  pins: {
    1: "/OE",
    ...range(2, ["D1","D2","D3","D4","D5","D6","D7","D8"]),
    10: "GND", 11: "CP",
    ...range(12, ["Q8","Q7","Q6","Q5","Q4","Q3","Q2","Q1"]),
    20: "VCC",
  },
}

/** 74HCT245 - break-before-make isolation between the map SRAM and D0-D7.
 * Verified as drawn, names included. Its B side takes the CPU's write data. */
export const HCT245: PartDef = {
  provenance: "confirmed",
  source: "reference/datasheets/sn74hc245.pdf p.1 (SCLS131D, N package)",
  footprint: "dip20_w0.3in",
  pins: {
    1: "DIR",
    ...range(2, ["A1","A2","A3","A4","A5","A6","A7","A8"]),
    10: "GND",
    ...range(11, ["B8","B7","B6","B5","B4","B3","B2","B1"]),
    19: "/OE", 20: "VCC",
  },
}

/** 74HCT157 - quad 2:1 mux on the map SRAM address, and (U11-U13) the SIMMs'
 * row/column multiplex. Both read logical address lines from the CPU module.
 *
 * Verified as drawn. Two names differ from the datasheet, and the first one
 * carries a polarity the motherboard depends on: pin 1 is A/B with the bar over
 * the A, so SEL *low* selects the A inputs - which is why U5 ties SEL to
 * MAP_WE and puts the translate path on 1A-4A. Pin 15 is /G on the datasheet
 * and /E here. */
export const HCT157: PartDef = {
  provenance: "confirmed",
  source: "reference/datasheets/sn74hc157.pdf p.1 (SCLS113D, N package)",
  footprint: "dip16_w0.3in",
  pins: {
    1: "SEL", 2: "1A", 3: "1B", 4: "1Y", 5: "2A", 6: "2B", 7: "2Y", 8: "GND",
    9: "3Y", 10: "3B", 11: "3A", 12: "4Y", 13: "4B", 14: "4A", 15: "/E", 16: "VCC",
  },
}

/** GAL22V10. Pin roles are per-design, so the names here are this board's -
 * only the three fixed pins are the part's, and those are confirmed. */
export const gal22v10 = (io: Record<number, string>): PartDef => ({
  provenance: "confirmed",
  source: "reference/datasheets/ATF22V10C.pdf 2 fig 2-2 (24-lead PDIP)",
  footprint: "dip24_w0.3in",
  pins: { 1: "CLK", 12: "GND", 24: "VCC", ...io },
})

/* -- system RAM, docs/machine.md 7.1 ------------------------------------- */
/** AS6C4008 512K x 8, 55 ns - the machine's system RAM, one package and not
 * four (hardware/README.md, applied to machine.md 7.1 on 2026-09-06). All 32
 * pins verified, including the 25-31 block that is easiest to get wrong. */
export const SRAM_512K: PartDef = {
  provenance: "confirmed",
  source: "reference/datasheets/AS6C4008.pdf p.2 (600-mil P-DIP-32)",
  footprint: "dip32_w0.6in",
  pins: {
    1: "A18", 2: "A16", 3: "A14", 4: "A12", 5: "A7", 6: "A6", 7: "A5", 8: "A4",
    9: "A3", 10: "A2", 11: "A1", 12: "A0",
    ...range(13, ["DQ0","DQ1","DQ2"]),
    16: "GND",
    ...range(17, ["DQ3","DQ4","DQ5","DQ6","DQ7"]),
    22: "/CE", 23: "A10", 24: "/OE", 25: "A11", 26: "A9", 27: "A8", 28: "A13",
    29: "/WE", 30: "A17", 31: "A15", 32: "VCC",
  },
}

/* -- the boot address buffer, docs/machine.md 7.2 ------------------------ */
/** 74HCT244 - octal buffer. It drives physical A20-A13 to zero while boot mode
 * or the vector page has the map SRAMs deselected (gal/u9.pld, gal/clkdec.pld).
 *
 * ⭐ A '541 WAS SPECIFIED AND A '244 IS FITTED, and the reason is this file's
 * own rule. Both are octal three-state buffers and either does the job; the
 * '244 has a datasheet in reference/datasheets/ and the '541 does not, so the
 * '244 is the one whose pin numbering is read rather than remembered. That is
 * hardware/README.md open item 1 deciding a part choice, which is what it is
 * for.
 *
 * The two halves' enables are tied together - one signal, eight bits. Pin
 * names are the datasheet's except that /1OE and /2OE are written /1G and /2G
 * there. */
export const HCT244: PartDef = {
  provenance: "confirmed",
  source: "reference/datasheets/sn74hc244.pdf p.1 (SCLS243D, N package)",
  footprint: "dip20_w0.3in",
  pins: {
    1: "/1OE", 2: "1A1", 3: "2Y4", 4: "1A2", 5: "2Y3", 6: "1A3", 7: "2Y2",
    8: "1A4", 9: "2Y1", 10: "GND", 11: "2A1", 12: "1Y4", 13: "2A2",
    14: "1Y3", 15: "2A3", 16: "1Y2", 17: "2A4", 18: "1Y1", 19: "/2OE",
    20: "VCC",
  },
}

/* -- the boot ROM, docs/machine.md 7.2 ----------------------------------- */
/** SST39SF040 512K x 8 flash, 70 ns, PDIP-32. Two of them are the 1 MB boot
 * ROM at physical 2.0-3.0 M; physical A19 picks between them (gal/u9.pld).
 *
 * ⭐ CONFIRMED 2026-09-10 against the datasheet, and the numbering below was
 * right on all 32 pins. It had been the only unverified pinout on the board
 * since 2026-09-06, written from the JEDEC 32-pin byte-wide flash convention -
 * the same way the map SRAM was written before hardware/history.md's finding 4
 * caught three rotated pins in it.
 *
 * THE TWO THINGS THE UNVERIFIED NOTE SAID TO CHECK, both now read off Figure 4
 * (32-pin PDIP, top view), and both were already correct:
 *   1. pin 3 is A15 on this part and A14 on the AS6C4008 above it - the
 *      address block is NOT the same permutation, and it was not written as
 *      though it were
 *   2. pin 31 is /WE here and A15 on the SRAM
 * Getting either wrong swaps address lines and the ROM reads as noise.
 *
 * ⚠ PIN 1 IS A18 ONLY ON THE 4 Mbit PART. It is NC on the SST39SF010A and
 * SST39SF020A, which share this datasheet and this footprint - so a 1 or
 * 2 Mbit substitute silently loses the top address line rather than failing
 * to fit. The 512K x 8 device is the one machine.md 7.2 specifies.
 *
 * The 600-mil body is the datasheet's own ("A 600 mil, 32-pin PDIP is also
 * available"), which is the dimension finding 4 got wrong on the map SRAM.
 * Grades are 45/55/70 ns; 70 is the one ram.md budgets.
 */
export const FLASH_512K: PartDef = {
  provenance: "confirmed",
  source: "reference/datasheets/SST39SF040.pdf fig 4 (DS25022A, 32-pin PDIP)",
  footprint: "dip32_w0.6in",
  pins: {
    1: "A18", 2: "A16", 3: "A15", 4: "A12", 5: "A7", 6: "A6", 7: "A5", 8: "A4",
    9: "A3", 10: "A2", 11: "A1", 12: "A0",
    ...range(13, ["DQ0","DQ1","DQ2"]),
    16: "GND",
    ...range(17, ["DQ3","DQ4","DQ5","DQ6","DQ7"]),
    22: "/CE", 23: "A10", 24: "/OE", 25: "A11", 26: "A9", 27: "A8", 28: "A13",
    29: "A14", 30: "A17", 31: "/WE", 32: "VCC",
  },
}

/* -- system memory, hardware/ram.md 6 ------------------------------------ */
/** 30-pin SIMM socket, x8 or x9. Four of them are all of the machine's RAM -
 * 4 to 16 MB of DRAM (ram.md 6.3).
 *
 * ⚠ UNVERIFIED. A 30-pin SIMM's pinout is a JEDEC standard and this is it from
 * familiarity, not from a document; the socket itself also has no measured
 * footprint (hardware/README.md open item 2 covers the slot socket and this is
 * the same problem). Names are the JEDEC signal names.
 *
 * A 4 MB module is 4M x 8: 11 row and 11 column address lines, which is A0-A10
 * plus the A11 that only 16 MB modules use. Both are brought out. */
export const SIMM30: PartDef = {
  provenance: "unverified",
  footprint: "pinrow30",
  pins: {
    1: "VCC", 2: "/CAS", 3: "DQ0", 4: "A0", 5: "A1", 6: "DQ1", 7: "A2",
    8: "A3", 9: "GND", 10: "DQ2", 11: "A4", 12: "A5", 13: "DQ3", 14: "A6",
    15: "A7", 16: "DQ4", 17: "A8", 18: "A9", 19: "A10", 20: "DQ5",
    21: "/WE", 22: "GND", 23: "DQ6", 24: "NC", 25: "DQ7", 26: "DQ8",
    27: "/RAS", 28: "/CASP", 29: "NC", 30: "VCC",
  },
}

/* -- the refresh timebase, hardware/ram.md 6.3.1 ------------------------- */
/** 74HC4040 - 12-stage ripple counter, free-running on CLK25. Q8 toggles every
 * 256 counts = 10.16 us, and U10 refreshes on every transition, so 512 rows
 * take 5.2 ms against the DRAM's 8 ms.
 *
 * ⚠ IT MUST BE CLK25 AND NOT E. machine.md 5 item 10: /WAIT holds U6's divider
 * (machine.md 5 item 8), so a refresh timed from the bus would stop dead for
 * the 40.7 us the video card can hold it - 2.6 refresh intervals, and the DRAM
 * forgets. This package exists because that interval cannot come from anything
 * already on the board.
 *
 * ⛔ CONFIRMED 2026-09-10, AND THREE PINS WERE ROTATED - THE SAME SHAPE, ON
 * THE SAME BOARD, AS hardware/history.md FINDING 4. The note that stood here
 * said "the Q outputs are NOT in pin order on this part, which is exactly what
 * gets written from memory wrongly: check Q0-Q11 individually". They were
 * written from memory, and pins 12, 13 and 15 were a 3-cycle rotation of the
 * truth:
 *
 *     pin 12   was Q10   is Q8    <- the tap the design actually uses
 *     pin 13   was Q8    is Q7
 *     pin 15   was Q7    is Q10
 *
 * ⚠ WHAT IT WOULD HAVE COST, and why nothing caught it: mainboard.circuit.tsx
 * connects `Q8: "net.REFCLK"` BY NAME, so the netlist is right and
 * check:netlist is happy. The error is in the pin NUMBER behind the name, so
 * it appears for the first time at layout - the REFCLK trace would have gone
 * to physical pin 13, which is Q7, and ram.md 6.3.1's 10.16 us refresh
 * interval would have been 5.08 us. DRAM retention still holds (2.6 ms against
 * 8), so it would not have failed; it would have quietly spent twice the
 * refresh bandwidth forever. Finding 4's sentence again: a name-level netlist
 * check cannot see a number-level footprint error.
 *
 * Q1' on the datasheet is the first stage and is Q0 here - the names below are
 * this board's 0-based ones, per the file header. MR IS ACTIVE HIGH, which the
 * old note also said and which the datasheet confirms ("a high voltage level
 * on the MR line resets all counters to their zero state"). */
export const HC4040: PartDef = {
  provenance: "confirmed",
  source: "reference/datasheets/CD74HC4040.pdf p.1 (CD74HC4040E, 16 Ld PDIP)",
  footprint: "dip16_w0.3in",
  pins: {
    1: "Q11", 2: "Q5", 3: "Q4", 4: "Q6", 5: "Q3", 6: "Q2", 7: "Q1", 8: "GND",
    9: "Q0", 10: "CLK", 11: "MR", 12: "Q8", 13: "Q7", 14: "Q9", 15: "Q10",
    16: "VCC",
  },
}

export const PARTS: Record<string, PartDef> = {
  CPU_SOCKET, MAP_SRAM, HCT574, HCT245, HCT157, SRAM_512K, HCT244, FLASH_512K,
  SIMM30, HC4040,
}

/** Derived, so it cannot go stale the way the hand-written list did.
 *
 * ⛔ IT SAID "Empty since 2026-09-06" UNTIL 2026-09-10 AND IT WAS NEVER EMPTY -
 * FLASH_512K, SIMM30 and HC4040 were all in it, and nothing imported this
 * export, so no check ever read the list and the prose beside it drifted for
 * four days. Same shape as CLAUDE.md's "a design output can be absent, and
 * prose does not notice": a derived value nobody asserts on is not a check.
 * lib/netlist.check.ts now pins the contents against KNOWN_UNVERIFIED. */
export const UNVERIFIED_PARTS: Record<string, PartDef> = Object.fromEntries(
  Object.entries(PARTS).filter(([, p]) => p.provenance !== "confirmed"),
)

/** pinLabels for a <chip>, from a PartDef. */
export const labels = (part: PartDef): Record<string, string> =>
  Object.fromEntries(
    Object.entries(part.pins).map(([n, sig]) => [`pin${n}`, sig.replace(/^\//, "n").replace(/\//g, "_")]),
  )
