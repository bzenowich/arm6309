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
 * they are never pins either.
 *
 * ⚠ FETCH AND HLOAD LEFT THIS SET ON 2026-09-08. They are produced now, by
 * video.parts.ts's tileCadence, because 6.4's map fetch has to be placed
 * relative to the display fetch window and there was no window signal to place
 * it against - two range compares on hgen's counter, which was already on the
 * same part. ROWADV and VLOAD are still owed: they are the vertical half and
 * 6.2's line doubling is tangled up in them. */
const FROM_DECODE = new Set([
  "ROWADV", "VLOAD", "LDA", "LDB", "LDC", "WSTB", "VSTATWR",
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
/* +13 for 19 item 23's unfitted decode, and +17 for the framebuffer address
 * MUX, which the first version of this census missed. On a GAL the scan pair
 * and the WPTR pair tri-state onto a shared bus and the mux costs nothing;
 * inside one die two macrocells cannot drive one pin, so the 17 address pins
 * are 17 further macrocells fed by both counter sets. The counters stay - they
 * just become buried. */
const ADDRESS_MUX = 17
const mcTotal = macrocells + 13 + ADDRESS_MUX
console.log(`\n  EXTERNAL I/O:  ${total}`)
console.log(`  MACROCELLS, incl. ~13 of unfitted decode:  ${mcTotal}\n`)

/* -- what the die can swallow on top of the logic ------------------------
 *
 * The I/O figure above assumes the CPLD replaces the ten GALs and nothing
 * else. It does not have to. Several of the card's small parts exist only
 * because a GAL had no room, and every one of them that moves inside takes
 * its interface pins with it - which is the difference between the package
 * that fits and the package that does not.
 *
 * Macrocell cost is the flip side, and it runs out first. */
const ABSORB = [
  { what: "VSTAT read driven onto D0..D7 directly, deleting the '244 (12.1)",
    io: 4, ic: 1, mc: 0,
    note: "VBLANK, HBLANK, SPANBUSY and the '244's enable stop being pins" },
  { what: "CTRL's '273 becomes 8 macrocells", io: 4, ic: 1, mc: 8,
    note: "VMODE[0], IRQEN and WMODE[1:0] stop being inputs" },
  { what: "SPANLEN's '161 pair becomes a buried counter", io: 3, ic: 2, mc: 10,
    note: "TC, load and count enable stop being pins" },
  { what: "the '165 span serialiser becomes a buried shifter", io: 3, ic: 1, mc: 8,
    note: "load, shift, and RETIRE's last external load" },
  { what: "HPOL becomes a programmed constant", io: 1, ic: 0, mc: 0,
    note: "a re-burn is the fix a CPLD already offers (6.2.1)" },
  { what: "the '245's direction is R/W, a wire", io: 1, ic: 0, mc: 0,
    note: "the same finding the MMU's ISO_DIR made - gal/README.md" },
] as const

console.log(`What else the die could swallow, and what it costs\n`)
let aIo = 0, aIc = 0, aMc = 0
for (const x of ABSORB) {
  aIo += x.io; aIc += x.ic; aMc += x.mc
  console.log(`  -${fmt(x.io, 2)} I/O  -${x.ic} IC  +${fmt(x.mc, 2)} mc   ${x.what}`)
  console.log(`                             ${x.note}`)
}
console.log(`\n  all of it:  I/O ${total} -> ${total - aIo},  macrocells ${mcTotal} -> ${mcTotal + aMc},  card ICs -${aIc + CARD.length - 1}`)
if (mcTotal + aMc > 128) {
  console.log(`  ...which is ${mcTotal + aMc - 128} macrocells over an ATF1508AS. Drop the widest:`)
  const widest = [...ABSORB].sort((a, b) => b.mc - a.mc)[0]
  console.log(`     without "${widest.what}":`)
  console.log(`     I/O ${total - aIo + widest.io}, macrocells ${mcTotal + aMc - widest.mc}, card ICs -${aIc - widest.ic + CARD.length - 1}`)
}

/* Absorb only as much as the target package's pin count REQUIRES, cheapest in
 * macrocells first.
 *
 * The first version of this took everything that fitted in 128 macrocells,
 * which optimised for pins when pins were not the binding constraint, and
 * reported 128 of 128 with nothing spare. That was an artefact of the greedy
 * choice, not a property of the design: absorbing the '165 buys three pins the
 * TQFP-100 does not need and costs eight macrocells the card does. */
const TARGET_IO = 80 // ATF1508AS in TQFP-100, JTAG wired
/* Anything that costs no macrocells is free margin - take it regardless. */
const feasible = ABSORB.filter((x) => x.mc === 0)
for (const x of [...ABSORB].filter((x) => x.mc > 0).sort((a, b) => a.mc - b.mc || b.io - a.io)) {
  if (total - feasible.reduce((n, y) => n + y.io, 0) <= TARGET_IO) break
  feasible.push(x)
}
const fIo = feasible.reduce((n, x) => n + x.io, 0)
const fMc = feasible.reduce((n, x) => n + x.mc, 0)
const bestIo = total - fIo
const bestMc = mcTotal + fMc
console.log(`\n  absorbing only what the ${TARGET_IO}-pin target needs, cheapest first:`)
for (const x of ABSORB) {
  console.log(`     ${feasible.includes(x) ? "yes" : "NO "}  ${x.what}`)
}
console.log(`\n  I/O ${total} -> ${bestIo},  macrocells ${mcTotal} -> ${bestMc} of 128\n`)

/* Packages. The I/O figure a distributor quotes is BIDIRECTIONAL pins; the
 * part has four dedicated inputs on top, which this design can use because it
 * has more outputs than inputs. JTAG costs four I/O when it is wired for
 * in-system programming - in a socket you program out of circuit and get them
 * back, which is the one thing PLCC has going for it here. */
const PARTS = [
  { name: "ATF1504AS", pkg: "PLCC-84  JU84", mc: 64, io: 64, socket: true },
  { name: "ATF1508AS", pkg: "PLCC-84  JC84", mc: 128, io: 64, socket: true },
  { name: "ATF1508AS", pkg: "TQFP-100 AU100", mc: 128, io: 80, socket: false },
  { name: "ATF1508AS", pkg: "PQFP-160 QC160", mc: 128, io: 96, socket: false },
] as const
const DEDICATED_IN = 4
const JTAG = 4
console.log(`Against the 5 V parts, at ${bestMc} macrocells and ${bestIo} I/O\n`)
console.log(`  part        package          mc    I/O  +ded  -JTAG  usable  logic? pins?`)
for (const q of PARTS) {
  /* A socketed part can be programmed out of circuit, so JTAG need not be
   * wired and its four pins stay available. */
  const usable = q.io + DEDICATED_IN - (q.socket ? 0 : JTAG)
  console.log(`  ${q.name}   ${q.pkg.padEnd(15)} ${fmt(q.mc, 4)}  ${fmt(q.io, 4)}  ` +
    `${fmt(DEDICATED_IN, 4)}  ${q.socket ? "  n/a" : fmt(-JTAG, 5)}  ${fmt(usable, 6)}  ` +
    `${(q.mc >= bestMc ? "yes" : "no").padEnd(6)} ` +
    `${usable >= bestIo ? "yes" : `no, ${bestIo - usable} short`}`)
}

/* -- 6.4's two variants, which 6.4.7 recommends building ------------------
 *
 * Section 7 says "the span writer is the text engine" and reads as settled.
 * 6.4 revisits it - "that argument was about a bitmap-only card" - and 6.4.5
 * concludes "text stops being the span writer's problem", at 2 CPU writes per
 * cell against 13 and a full redraw of 9.5 ms against 62. On a machine whose
 * own 2.1 says the CPU is the constraint and not bandwidth, that is the trade
 * the card exists to make. 6.4.7: "Build Variant A."
 *
 * A is the 8bpp tile fetcher - playfields, sprites, every pixel independently
 * coloured. B is the 1bpp character generator that makes text cheap, and it is
 * the one that renders 80x25. They stack: B needs A's fetch machinery. */
const VARIANT_A = [
  ["the map byte, from the fetch latches into the address concatenation", 8, 0],
  ["linear-vs-concatenated mux on A13..A6 - product terms, not macrocells", 0, 0],
  ["the second fetch cadence and its control (19 item 15 (c))", 0, 5],
] as const
const VARIANT_B = [
  ["the glyph serialiser's load and shift ('AHC165, 6.4.6 limit 3)", 2, 0],
  ["the LUT page select - CTRL b5, out to a LUT address pin (6.4.3)", 1, 0],
  ["the three-access cadence: code, attribute, font row (6.4.3)", 0, 3],
] as const
const sum = (t: readonly (readonly [string, number, number])[]) =>
  [t.reduce((n, [, i]) => n + i, 0), t.reduce((n, [, , m]) => n + m, 0)] as const

console.log(`  6.4's tile and character modes. 6.4.5 puts 80x25 text HERE, not on`)
console.log(`  the span writer: 2 CPU writes per cell against 13, ~9.5 ms per`)
console.log(`  full redraw against ~62. 6.4.7 recommends building it.\n`)
let vIo = 0, vMc = 0
for (const [name, table] of [["A  8bpp tiles", VARIANT_A], ["B  1bpp characters - the text mode", VARIANT_B]] as const) {
  const [i, m] = sum(table)
  vIo += i; vMc += m
  console.log(`     Variant ${name}`)
  for (const [what, ii, mm] of table) console.log(`        +${ii} I/O  +${mm} mc   ${what}`)
  console.log(`        running total: ${bestIo + vIo} I/O, ${bestMc + vMc} macrocells`)
}
console.log()
for (const q of PARTS) {
  const usable = q.io + DEDICATED_IN - (q.socket ? 0 : JTAG)
  const ok = q.mc >= bestMc + vMc && usable >= bestIo + vIo
  console.log(`     ${q.name} ${q.pkg.padEnd(15)} ${ok ? "FITS" : q.mc < bestMc + vMc
    ? `${bestMc + vMc - q.mc} macrocells short` : `${bestIo + vIo - usable} pins short`}`)
}
console.log(`\n  ...and at ${bestMc + vMc} of 128 that is one part FULL.`)

/* -- 10.3's list engine, and whether two packages make room for it -------
 *
 * Its interface is almost entirely INTERNAL, which is what makes it cheap in
 * pins and expensive in macrocells: it reads VRAM through the arbiter and the
 * address path that already exist, and its MOVE opcode is "one SRAM write into
 * the register file" (10.3) - also a path that already exists. What it adds is
 * state. */
const LIST_ENGINE = [
  ["the LIST pointer, 19 bits (13, +$0B..+$0D)", 0, 19],
  ["descriptor latch and opcode decode", 0, 10],
  ["fetch/execute sequencing, BCTRL/BSTAT", 2, 6],
] as const
const [lIo, lMc] = sum(LIST_ENGINE)
console.log(`\n  10.3's list engine on top - 6.4.6 limit 1 makes it the thing that`)
console.log(`  puts a text bar over a bitmap playfield, which is what beats both`)
console.log(`  period chips:`)
for (const [what, i, m] of LIST_ENGINE) console.log(`     +${i} I/O  +${m} mc   ${what}`)
const allIo = bestIo + vIo + lIo
const allMc = bestMc + vMc + lMc
console.log(`     = ${allIo} I/O, ${allMc} macrocells\n`)

/* Two packages: macrocells add, usable I/O adds, but every net that crosses
 * costs a pin at BOTH ends. */
const CROSSING = 14
const OPTIONS = [
  { what: "1 x ATF1508AS PQFP-160", parts: 1, mc: 128, io: 96 + DEDICATED_IN - JTAG, cross: 0, area: 7.8 },
  { what: "2 x ATF1508AS PLCC-84 ", parts: 2, mc: 256, io: 2 * (64 + DEDICATED_IN), cross: CROSSING, area: 22 },
  { what: "2 x ATF1504AS PLCC-84 ", parts: 2, mc: 128, io: 2 * (64 + DEDICATED_IN), cross: CROSSING, area: 22 },
] as const
console.log(`  With 6.4 A+B and the list engine, at ${allMc} macrocells and ${allIo} external I/O\n`)
console.log(`  option                   macrocells      pins (incl. ${CROSSING} crossing nets x2)   area`)
for (const o of OPTIONS) {
  const pins = allIo + o.cross * 2
  const ok = o.mc >= allMc && o.io >= pins
  console.log(`  ${o.what}   ${fmt(allMc, 4)}/${fmt(o.mc, 4)} ${(o.mc >= allMc ? "ok " : "OVER")}` +
    `   ${fmt(pins, 4)}/${fmt(o.io, 4)} ${(o.io >= pins ? "ok " : "OVER")}` +
    `   ~${o.area} cm2   ${ok ? "FITS" : ""}`)
}
console.log(`\n  ten GAL22V10 in DIP-24, for comparison: ~26 cm2.`)
console.log(`  PLCC-84 is socketed: programmable out of circuit, so JTAG's four`)
console.log(`  pins stay available, and the part can be pulled and reseated.`)

console.log(`\n  Two ATF1504AS in PLCC-84 - socketed, and the partition that works:`)
const SPLIT = [
  ["A: scan + WPTR counters, the address mux, the arbiter", 53 + 10, 17 + 8 + 10],
  ["B: sync, sequencer, span control, decode", bestMc - 53 - 10, bestIo - 17 - 8],
] as const
for (const [what, mc, io] of SPLIT) {
  console.log(`     ${(mc <= 64 && io <= 68 ? "fits" : "OVER")}  ${fmt(mc, 3)} mc, ~${fmt(io, 2)} I/O   ${what}`)
}
console.log(`     plus ~15 inter-part nets, which cost a pin at each end.`)
console.log(`\n  NOTE: ATF1508ASV is the 3.3 V part. The 5 V device is ATF1508AS,`)
console.log(`  and the cheap listings are mostly ASV.\n`)
