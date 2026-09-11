/* Does every programmable part's pin have the sense of the thing it is wired to?
 *
 *   npm run check:pins
 *
 * ⛔ WHY THIS EXISTS. On 2026-09-11 a review found NINE pins across all three
 * boards declared with the wrong sense - U6's /WAIT, the video card's /IOSEL,
 * /IOPAGE, BLANKD into the '273s' /MR, six fetch-rank /OEs and the register
 * file's /WE, the audio card's /IOSEL and seven of U2's enables - and every one
 * of them passed every check in this repository, for the same reason:
 *
 *   - verilog/emit.ts emits the ASSERTED sense of every signal and ignores
 *     activeLow/assertedLow entirely, and every hand-written wrapper inverts the
 *     backplane lines by hand (machine.v: "active low on the connector and
 *     asserted-high inside the models"). So the simulation cannot see a pin
 *     sense at all.
 *   - the fuse-map checks drive pins at whatever level their author believed,
 *     and for U6 that belief was the bug.
 *   - the cards' CPLDs are not drawn, so check:netlist has nothing to compare.
 *
 * But the fitter programs exactly what the .pld declares. A wrong `PIN = X`
 * is a JEDEC that fails on the board and a simulation that passes.
 *
 * WHAT IT ASSERTS, three ways:
 *   1. BACKPLANE. A pin named for an active-low backplane signal (lib/slot.ts,
 *      the ones spelled with a leading "/") is active-low, input or output.
 *   2. CROSSINGS. A signal that leaves one part of a card and enters another
 *      under the same name has the same sense at both ends - which is how a
 *      fix to one end cannot leave the other behind.
 *   3. CONSUMERS. Each pin in CONSUMERS below drives a discrete part pin whose
 *      datasheet sense is recorded beside it.
 *
 * ⚠ WHAT IT CANNOT SEE. CONSUMERS is a table, not a netlist: a pin not listed
 * is not checked against its consumer, and an entry is only as right as the
 * part it names. It is the list of pins whose consumer is known today, and it
 * should grow as the cards are drawn - check:netlist is what closes it for
 * good, once U1-U3 of each card exist in a .circuit.tsx.
 */

import { SLOT_PINS } from "../lib/slot"
import { vaddrCpld, vctrlCpld } from "./video.cpld"
import { vsupCpld } from "./vsup.cpld"
import { audioCpld } from "./audio.cpld"
import { aseqCpld } from "./aseq.cpld"
import { mmuDesign } from "./mmu.jedec"
import { clkdecDesign } from "./clkdec.jedec"
import { u9Design } from "./u9.jedec"
import { u10Design } from "./u10.jedec"

let failures = 0, passes = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else { passes++; console.log(`ok    ${claim}`) }
}

type Dir = "in" | "out"
interface Pin { name: string; dir: Dir; low: boolean }
interface Part { name: string; board: string; pins: Pin[] }

/* A merged CPLD's pins are its inputs and its EXTERNAL cells; buried cells
 * have no sense because they have no pin. A GAL design's cells are all pins. */
const cpld = (board: string, m: { name: string; inputs: { name: string; activeLow?: boolean }[];
  cells: { name: string; assertedLow: boolean }[]; external: Set<string> }): Part => ({
  name: m.name, board,
  pins: [
    ...m.inputs.map((i) => ({ name: i.name, dir: "in" as Dir, low: !!i.activeLow })),
    ...m.cells.filter((c) => m.external.has(c.name))
      .map((c) => ({ name: c.name, dir: "out" as Dir, low: c.assertedLow })),
  ],
})
const gal = (board: string, d: { name: string; inputs: { name: string; activeLow?: boolean }[];
  cells: { name: string; assertedLow: boolean }[] }): Part => {
  const produced = new Set(d.cells.map((c) => c.name))
  return {
    name: d.name, board,
    pins: [
      ...d.inputs.filter((i) => !produced.has(i.name))
        .map((i) => ({ name: i.name, dir: "in" as Dir, low: !!i.activeLow })),
      ...d.cells.map((c) => ({ name: c.name, dir: "out" as Dir, low: c.assertedLow })),
    ],
  }
}

const PARTS: Part[] = [
  gal("mainboard", mmuDesign), gal("mainboard", clkdecDesign),
  gal("mainboard", u9Design), gal("mainboard", u10Design),
  cpld("video", vaddrCpld), cpld("video", vctrlCpld), cpld("video", vsupCpld),
  cpld("audio", audioCpld), cpld("audio", aseqCpld),
]

const find = (part: string, name: string): Pin => {
  const p = PARTS.find((x) => x.name === part)
  if (!p) throw new Error(`no part ${part}`)
  const pin = p.pins.find((x) => x.name === name)
  /* A table entry naming a pin that does not exist is a failure, not a skip:
   * a rename must not turn a claim into nothing. */
  if (!pin) throw new Error(`${part} has no pin ${name} - update CONSUMERS`)
  return pin
}

/* -- 1. the backplane --------------------------------------------------- */
console.log("\n      1. every pin named for an active-low backplane signal is active-low\n")
const ACTIVE_LOW_BP = [...new Set(SLOT_PINS.map((p) => p.signal).filter((s) => s.startsWith("/"))
  .map((s) => s.slice(1)))]
/* _BP and _MB are this repository's two spellings of "the same signal, on the
 * backplane / on the motherboard only" - u9's IOPAGE_BP, the page term's
 * IOPAGE_MB net. Both carry the signal's sense. */
const bpName = (n: string) => n.replace(/_(BP|MB)$/, "")
const bpHits: string[] = []
for (const part of PARTS) {
  for (const pin of part.pins) {
    if (!ACTIVE_LOW_BP.includes(bpName(pin.name))) continue
    bpHits.push(`${part.name}.${pin.name}`)
    check(pin.low, `${part.board} ${part.name}: ${pin.dir === "in" ? "input" : "output"} ${pin.name} ` +
      `is active-low, like /${bpName(pin.name)} on the slot`)
  }
}
/* Vacuity guard: the pins that exposed this class must be among those checked. */
for (const must of ["clkdec.WAIT", "vsup.IOSEL", "vctrl.IOPAGE", "vctrl.WAIT", "vctrl.IRQ",
  "audio.IOSEL", "audio.FIRQ", "u9.IOPAGE_BP", "aseq.RESET"]) {
  check(bpHits.includes(must), `and ${must} is one of the ${bpHits.length} backplane pins checked`)
}

/* -- 2. crossings between parts of one card ------------------------------ */
console.log("\n      2. a signal crossing between two parts has one sense at both ends\n")
let crossings = 0
for (const board of ["mainboard", "video", "audio"]) {
  const parts = PARTS.filter((p) => p.board === board)
  for (const src of parts) {
    for (const out of src.pins.filter((p) => p.dir === "out")) {
      for (const dst of parts) {
        if (dst === src) continue
        const inp = dst.pins.find((p) => p.dir === "in" && p.name === out.name)
        if (!inp) continue
        crossings++
        check(inp.low === out.low,
          `${board}: ${src.name}.${out.name} -> ${dst.name}.${inp.name} agree ` +
          `(${out.low ? "active-low" : "active-high"})`,
          `driver ${out.low ? "low" : "high"}, receiver ${inp.low ? "low" : "high"}`)
      }
    }
  }
}
check(crossings >= 20, `and there are ${crossings} crossings, not a vacuous handful`)
check(PARTS.some((p) => p.name === "vaddr" && p.pins.some((x) => x.name === "WSTB" && x.dir === "in")),
  "including WSTB, vsup to vaddr - the crossing a one-ended fix would have split")

/* -- 3. named consumers -------------------------------------------------- */
console.log("\n      3. pins whose consumer is a discrete part, against that part's pin\n")
interface Consumer { part: string; pin: string; drives: string; low: boolean; where: string }
const CONSUMERS: Consumer[] = [
  /* mainboard - mainboard.circuit.tsx draws every one of these */
  { part: "mmu", pin: "MAPWE", drives: "CY7C128A /WE (U1, U1B)", low: true, where: "mainboard.circuit.tsx" },
  { part: "mmu", pin: "MAPOE", drives: "CY7C128A /OE (U1, U1B)", low: true, where: "mainboard.circuit.tsx" },
  { part: "mmu", pin: "ISOOE_LO", drives: "74HCT245 /OE (U4)", low: true, where: "mainboard.circuit.tsx" },
  { part: "mmu", pin: "ISOOE_HI", drives: "74HCT245 /OE (U18)", low: true, where: "mainboard.circuit.tsx" },
  { part: "clkdec", pin: "BOOTOE", drives: "74HCT244 /1G /2G (U16)", low: true, where: "mainboard.circuit.tsx" },
  { part: "u9", pin: "ROMCE0", drives: "SST39SF040 /CE (U14)", low: true, where: "mainboard.circuit.tsx" },
  { part: "u9", pin: "ROMCE1", drives: "SST39SF040 /CE (U15)", low: true, where: "mainboard.circuit.tsx" },
  { part: "u9", pin: "MAPCE_LO", drives: "CY7C128A /CE (U1)", low: true, where: "mainboard.circuit.tsx" },
  { part: "u9", pin: "MAPCE_HI", drives: "CY7C128A /CE (U1B)", low: true, where: "mainboard.circuit.tsx" },
  ...[0, 1, 2, 3].map((n) => ({ part: "u10", pin: `RAS${n}`, drives: `30-pin SIMM /RAS (SIMM${n})`,
    low: true, where: "mainboard.circuit.tsx" })),
  { part: "u10", pin: "CAS", drives: "30-pin SIMM /CAS, all four", low: true, where: "mainboard.circuit.tsx" },
  { part: "u10", pin: "DWE", drives: "30-pin SIMM /WE, all four", low: true, where: "mainboard.circuit.tsx" },

  /* video card - graphics.md; the parts are not drawn yet */
  { part: "vctrl", pin: "BLANKD", drives: "74AHCT273 /MR (post-LUT pair)", low: true, where: "graphics.md 9.2" },
  { part: "vsup", pin: "WSTB", drives: "register-file SRAM /WE", low: true, where: "vsup.cpld.ts, graphics.md 10.1.6.3" },
  ...["OEA0", "OEA1", "OEA2", "OEB0", "OEB1", "OEB2"].map((pin) => ({
    part: "vsup", pin, drives: "74AHCT574 /OE (fetch ranks)", low: true, where: "graphics.md 8.2" })),

  /* audio card - audio.md 10.2.2; the parts are not drawn yet */
  { part: "aseq", pin: "BLATOE", drives: "74HC574 /OE (BLAT)", low: true, where: "audio.md 10.2.2" },
  { part: "aseq", pin: "ONESOE", drives: "74HC244 /1G /2G (B = $FFFF)", low: true, where: "audio.md 10.2.2" },
  { part: "aseq", pin: "SUMOE", drives: "74HC244 /1G /2G (SUM -> SD)", low: true, where: "audio.md 10.2.2" },
  { part: "aseq", pin: "SBOE", drives: "74HC574 /OE (SBLAT)", low: true, where: "audio.md 10.2.2" },
  { part: "aseq", pin: "PWOE", drives: "74HC574 /OE (posted-write latch)", low: true, where: "audio.md 10.2.2" },
  { part: "aseq", pin: "SROE", drives: "AS6C4008 /OE (sample RAM)", low: true, where: "audio.md 10.2.2" },
  { part: "aseq", pin: "SRWE", drives: "AS6C4008 /WE (sample RAM)", low: true, where: "audio.md 10.2.2" },
]
for (const c of CONSUMERS) {
  const pin = find(c.part, c.pin)
  check(pin.low === c.low,
    `${c.part}.${c.pin} is ${c.low ? "active-low" : "active-high"}: it drives ${c.drives} - ${c.where}`,
    `declared ${pin.low ? "active-low" : "active-high"}`)
}

console.log(`\n${passes} claims, ${failures} failed`)
if (failures) process.exit(1)
