/* What a CPLD would actually absorb.
 *
 * graphics.md 10.1 sets the trigger at "eighteen GAL22V10s is where the
 * honest question becomes 'why not one CPLD'", and 15's period audit places
 * the card at 1989-90 - a year after Altera's MAX 5000, so the question is
 * not blocked by chronology. What it IS blocked by, every time so far, is
 * pins.
 *
 * So count them, from the designs rather than by hand. A signal produced by
 * one GAL and consumed only by other GALs is inter-package traffic: it costs
 * a pin at each end today and costs nothing inside one die. Everything else
 * has to reach the outside world whatever the part is.
 *
 *   npm run census
 */

import { hgenDesign, vgenDesign, vdecDesign } from "./sync.jedec"
import { hadrDesign, vadrDesign } from "./scan.jedec"
import { arbDesign, wcolDesign, wrowDesign } from "./access.jedec"
import { seqphDesign } from "./seqph.jedec"
import { seqctlDesign } from "./seqctl.jedec"
import { OLMC } from "./jedec/gal22v10"
import type { Design } from "./jedec/assemble"

const CARD: Design[] = [
  hgenDesign, vgenDesign, vdecDesign, hadrDesign, vadrDesign,
  arbDesign, wcolDesign, wrowDesign, seqphDesign, seqctlDesign,
]

/* Signals that are one net under two names. Each entry is
 * "producer.OUTPUT" -> the input names it drives on other parts. Written out
 * because the alternative is matching on spelling, and a census that depends
 * on two engineers having chosen the same word is not a census. */
const ALIASES: Record<string, string[]> = {
  "seqph.SLOTTICK": ["CE"],          // hgen and vgen advance on the slot tick
  "seqctl.RETIRE": ["WINC"],         // one retire is one column step
  "seqctl.SPANBUSY": ["SPNREQ"],     // a span in flight IS the request
  "wcol.A0": ["SPNA0"],              // WPTR[1:0] is the span writer's chip
  "wcol.A1": ["SPNA1"],
}

const produced = new Map<string, string>() // signal -> part that drives it
for (const d of CARD) for (const c of d.cells) produced.set(c.name, d.name)
for (const [key, names] of Object.entries(ALIASES)) {
  const [part] = key.split(".")
  for (const n of names) produced.set(n, part)
}

const consumers = new Map<string, string[]>()
for (const d of CARD) {
  for (const i of d.inputs) {
    consumers.set(i.name, [...(consumers.get(i.name) ?? []), d.name])
  }
}

/* -- what the packages cost today ---------------------------------------- */
let pins = 0, macrocells = 0, freeMacrocells = 0
for (const d of CARD) {
  const clock = d.clockPin === undefined ? 0 : 1
  pins += d.inputs.length + d.cells.length + clock
  macrocells += d.cells.length
  freeMacrocells += 10 - d.cells.length
}

/* -- where each produced signal actually goes ---------------------------
 *
 * A 22V10 has no buried nodes, so every register and every intermediate term
 * sits on a pin whether or not anything outside wants it. Counting GAL
 * outputs as "external I/O" therefore measures the constraint rather than the
 * need. This table says which of them a NON-GAL part or the backplane
 * actually consumes; everything else is buried the moment the parts merge.
 *
 * It is a judgement table, and it is written out so it can be argued with. */
const LEAVES: Record<string, string> = {
  HSYNC: "VGA connector, and the backplane (12.2)",
  VSYNC: "VGA connector, and the backplane",
  BLANK: "the post-LUT '273's /MR (9.2)",
  VBLANK: "VSTAT's '244 (12.1)",
  HBLANK: "VSTAT's '244",
  SPANBUSY: "VSTAT's '244",
  IRQ: "the backplane, open-drain (12.1)",
  WAIT: "the backplane, open-drain (3.3)",
  FCLK0: "chip 0's fetch '574 (5.2.2)", FCLK1: "chip 1's fetch '574",
  FCLK2: "chip 2's fetch '574", FCLK3: "chip 3's fetch '574",
  MUXSEL0: "the '153 pixel mux (6.1)", MUXSEL1: "the '153 pixel mux",
  RETIRE: "the '165's shift and the '161's count enable (7.4)",
}
/* The framebuffer address is the one output that is not a cell today: hadr /
 * vadr and wcol / wrow tri-state onto a shared bus. Inside one die it is a
 * mux whose 17 outputs are the only address pins, and BOTH counter sets - 36
 * bits - become buried. */
const MERGED_OUT = [
  ["framebuffer address A16..A0, one mux output rather than two counter sets", 17],
  ["framebuffer per-chip /WE and a common /OE", 5],
  ["register-file address RA4..RA0, /WE, /OE", 7],
  ["'165 load, '161 load, PIDX '593 load and count", 4],
  ["posted-write latch output enables, '245 direction and enable", 4],
  ["VRAM read latch clock, VSTAT '244 enable", 2],
] as const

/* Inputs produced by the sequencer's unfitted decode half - inside one die
 * they are never pins either. */
const FROM_DECODE = new Set([
  "FETCH", "HLOAD", "ROWADV", "VLOAD", "LDA", "LDB", "LDC", "WSTB", "VSTATWR",
])
/* HSCROLL and VSCROLL reach the counters on the register file's data path,
 * not on nineteen dedicated lines: D0..D7 with a load strobe per slice. */
const ON_DATA_BUS = new Set([...Array(10).keys()].map((i) => `HS${i}`)
  .concat([...Array(9).keys()].map((i) => `VS${i}`)))
const MERGED_IN = [
  ["CPU register interface: A4..A0, E, R/W, /IOSEL", 8],
  ["DOTCLK", 1],
] as const

/* Keyed by part AND name: the scan address (hadr/vadr) and the write pointer
 * (wcol/wrow) both call their outputs A2..A18, and they are different nets on
 * different packages. Keying on the name alone hides 14 of them. */
const interGal: { net: string; from: string; to: string[] }[] = []
const buried: string[] = []
const leaves: string[] = []
for (const d of CARD) {
  for (const c of d.cells) {
    const alias = ALIASES[`${d.name}.${c.name}`] ?? []
    const to = [...new Set([c.name, ...alias].flatMap((n) =>
      (consumers.get(n) ?? []).filter((q) => q !== d.name)))]
    if (LEAVES[c.name]) leaves.push(c.name)
    else if (to.length) interGal.push({ net: c.name, from: d.name, to })
    else buried.push(`${d.name}.${c.name}`)
  }
}
const externalIn = [...consumers.keys()]
  .filter((n) => !produced.has(n) && !FROM_DECODE.has(n) && !ON_DATA_BUS.has(n))

const interGalPins = interGal.reduce((n, x) => n + 1 + x.to.length, 0)
const fmt = (n: number, w = 3) => String(n).padStart(w)

console.log(`\nThe video card's programmable logic, as ten GAL22V10s\n`)
console.log(`  packages            ${fmt(CARD.length)}`)
console.log(`  macrocells used     ${fmt(macrocells)} of ${CARD.length * 10}  (${freeMacrocells} free)`)
console.log(`  signal pins used    ${fmt(pins)} of ${CARD.length * 22}`)

console.log(`\nPins that exist only because the parts are separate\n`)
console.log(`  ${fmt(interGal.length, 2)} inter-package nets, burning ${interGalPins} pins:`)
for (const x of interGal.sort((a, b) => a.from.localeCompare(b.from))) {
  console.log(`       ${x.from.padEnd(7)} -> ${x.to.join(", ").padEnd(12)} ${x.net}`)
}
console.log(`\n  ${fmt(buried.length, 2)} outputs nothing outside consumes - on a pin only because a`)
console.log(`     22V10 has no buried nodes:`)
console.log(`       ${buried.sort().join(" ")}`)
console.log(`\n  ${interGalPins + buried.length} of ${pins} pins - ${Math.round(100 * (interGalPins + buried.length) / pins)}% - are an artefact of the packaging.`)

console.log(`\nWhat has to reach the outside world whatever the part is\n`)
console.log(`  ${fmt(leaves.length, 2)}  outputs already fitted:`)
for (const n of leaves.sort()) console.log(`        ${n.padEnd(9)} ${LEAVES[n]}`)
let mergedOut = 0
for (const [what, n] of MERGED_OUT) { mergedOut += n; console.log(`  ${fmt(n, 2)}  ${what}`) }
console.log(`  ${fmt(externalIn.length, 2)}  inputs: ${externalIn.sort().join(" ")}`)
let mergedIn = 0
for (const [what, n] of MERGED_IN) { mergedIn += n; console.log(`  ${fmt(n, 2)}  ${what}`) }

const total = leaves.length + mergedOut + externalIn.length + mergedIn
const mcTotal = macrocells + 13
console.log(`\n  EXTERNAL I/O:  ${total}`)
console.log(`  MACROCELLS, incl. ~13 of unfitted decode:  ${mcTotal}\n`)

const PARTS = [
  { name: "ATF1502AS", mc: 32, io: 36 },
  { name: "ATF1504AS", mc: 64, io: 68 },
  { name: "ATF1508AS", mc: 128, io: 96 },
] as const
console.log(`Against the 5 V CPLDs still in production\n`)
console.log(`  part        macrocells  max I/O   logic fits?  pins fit?`)
for (const q of PARTS) {
  console.log(`  ${q.name}   ${fmt(q.mc, 8)}  ${fmt(q.io, 7)}   ` +
    `${(q.mc >= mcTotal ? "yes" : "no").padEnd(11)}  ${q.io >= total ? "yes" : "no"}`)
}
console.log()
