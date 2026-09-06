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

/** 74HC574 - task select, MMU enable, shadow-ROM disable.
 * Verified as drawn. The datasheet writes the data pins 1D-8D and the clock
 * CLK; D1-D8 and CP here are the older names for the same pins. */
export const HC574: PartDef = {
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

/** 74HC245 - break-before-make isolation between the map SRAM and D0-D7.
 * Verified as drawn, names included. */
export const HC245: PartDef = {
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

/** 74HC157 - quad 2:1 mux on the map SRAM address.
 *
 * Verified as drawn. Two names differ from the datasheet, and the first one
 * carries a polarity the motherboard depends on: pin 1 is A/B with the bar over
 * the A, so SEL *low* selects the A inputs - which is why U5 ties SEL to
 * MAP_WE and puts the translate path on 1A-4A. Pin 15 is /G on the datasheet
 * and /E here. */
export const HC157: PartDef = {
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

export const PARTS: Record<string, PartDef> = {
  CPU_SOCKET, MAP_SRAM, HC574, HC245, HC157, SRAM_512K,
}

/** Derived, so it cannot go stale the way the hand-written list did. Empty
 * since 2026-09-06; a part added without a datasheet reappears here. */
export const UNVERIFIED_PARTS: Record<string, PartDef> = Object.fromEntries(
  Object.entries(PARTS).filter(([, p]) => p.provenance !== "confirmed"),
)

/** pinLabels for a <chip>, from a PartDef. */
export const labels = (part: PartDef): Record<string, string> =>
  Object.fromEntries(
    Object.entries(part.pins).map(([n, sig]) => [`pin${n}`, sig.replace(/^\//, "n").replace(/\//g, "_")]),
  )
