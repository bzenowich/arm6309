/* Package pinouts for the parts the motherboard fits.
 *
 * ⚠ PIN NUMBERS ARE UNVERIFIED. The signal names and the roles come from the
 * card documents; the DIP pin *numbers* below were written from familiarity and
 * no datasheet in reference/datasheets/ covers any of these parts. This project
 * puts a measurement in place of an estimate, so they are marked rather than
 * asserted, and hardware/README.md open item 1 lists the datasheets to fetch.
 * Only the CPU socket is confirmed - cpu/docs/plan.md 2.6 reads it off the
 * Color Computer 3 Service Manual, and 2.6.1 corroborates it against the
 * Dragon 64 schematic.
 */

export interface PartDef {
  /** DIP pin number -> signal name on the package. */
  pins: Record<number, string>
  footprint: string
  /** Where the pin numbering came from. "unverified" needs a datasheet. */
  provenance: "confirmed" | "unverified"
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

/** 2K x 8 SRAM, 15 ns - the block map. Sixteen of 2048 locations are used. */
export const MAP_SRAM: PartDef = {
  provenance: "unverified",
  footprint: "dip24_w0.6in",
  pins: {
    ...range(1, ["A7","A6","A5","A4","A3","A2","A1","A0"]),
    ...range(9, ["DQ0","DQ1","DQ2"]),
    12: "GND",
    ...range(13, ["DQ3","DQ4","DQ5","DQ6","DQ7"]),
    18: "/CE", 19: "A10", 20: "/OE", 21: "A9", 22: "A8", 23: "/WE", 24: "VCC",
  },
}

/** 74HC574 - task select, MMU enable, shadow-ROM disable. */
export const HC574: PartDef = {
  provenance: "unverified",
  footprint: "dip20_w0.3in",
  pins: {
    1: "/OE",
    ...range(2, ["D1","D2","D3","D4","D5","D6","D7","D8"]),
    10: "GND", 11: "CP",
    ...range(12, ["Q8","Q7","Q6","Q5","Q4","Q3","Q2","Q1"]),
    20: "VCC",
  },
}

/** 74HC245 - break-before-make isolation between the map SRAM and D0-D7. */
export const HC245: PartDef = {
  provenance: "unverified",
  footprint: "dip20_w0.3in",
  pins: {
    1: "DIR",
    ...range(2, ["A1","A2","A3","A4","A5","A6","A7","A8"]),
    10: "GND",
    ...range(11, ["B8","B7","B6","B5","B4","B3","B2","B1"]),
    19: "/OE", 20: "VCC",
  },
}

/** 74HC157 - quad 2:1 mux on the map SRAM address. */
export const HC157: PartDef = {
  provenance: "unverified",
  footprint: "dip16_w0.3in",
  pins: {
    1: "SEL", 2: "1A", 3: "1B", 4: "1Y", 5: "2A", 6: "2B", 7: "2Y", 8: "GND",
    9: "3Y", 10: "3B", 11: "3A", 12: "4Y", 13: "4B", 14: "4A", 15: "/E", 16: "VCC",
  },
}

/** GAL22V10. Pin roles are per-design, so the names here are this board's. */
export const gal22v10 = (io: Record<number, string>): PartDef => ({
  provenance: "unverified",
  footprint: "dip24_w0.3in",
  pins: { 1: "CLK", 12: "GND", 24: "VCC", ...io },
})

/* -- system RAM, docs/machine.md 7.1 ------------------------------------- */
/** AS6C4008-class 512K x 8, 55 ns. Four of these are the machine's 512 KB. */
export const SRAM_512K: PartDef = {
  provenance: "unverified",
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

export const UNVERIFIED_PARTS: Record<string, PartDef> = {
  MAP_SRAM, HC574, HC245, HC157, SRAM_512K,
}

/** pinLabels for a <chip>, from a PartDef. */
export const labels = (part: PartDef): Record<string, string> =>
  Object.fromEntries(
    Object.entries(part.pins).map(([n, sig]) => [`pin${n}`, sig.replace(/^\//, "n").replace(/\//g, "_")]),
  )
