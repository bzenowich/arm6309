/* What a PLCC-84 would absorb on the audio card.  npm run census:audio
 *
 * Same method as census.ts for the video card: count the pins that exist only
 * because the parts are separate, then say what has to reach the outside world
 * whatever the part is. The difference is that this card is analogue-heavy, so
 * most of its 36 packages cannot move at all.
 */

import { assemble, type Design } from "./jedec/assemble"
import { OLMC_PINS } from "./jedec/gal22v10"
import {
  aseqDesign, adecDesign, admatDesign, aintenaDesign, apendDesign, buildAintreqSplit,
} from "./audio.jedec"

const fmt = (n: number, w = 3) => String(n).padStart(w)

/* §9.5's five, except that the fifth is two - audio.check.ts shows the
 * interrupt block fits a GAL22V10 in neither arrangement. The split version is
 * counted at its true size rather than the size that fits. */
const FITTED: Design[] = [aseqDesign, adecDesign, admatDesign, aintenaDesign, apendDesign]
const OVERSIZE = { name: "aintreq", macrocells: 7, inputs: 17 }

let macrocells = 0, pins = 0
for (const d of FITTED) {
  const a = assemble(d)
  macrocells += a.usage.length
  pins += d.inputs.length + d.cells.length + (d.clockPin === undefined ? 0 : 1)
}
macrocells += OVERSIZE.macrocells
pins += OVERSIZE.inputs + OVERSIZE.macrocells + 1

console.log(`\nThe audio card's programmable logic, as GAL22V10s\n`)
console.log(`  packages            ${fmt(FITTED.length + 1)}  (§9.5 budgets five; the interrupt`)
console.log(`                          block does not fit one part - audio.check.ts)`)
console.log(`  macrocells used     ${fmt(macrocells)} of ${(FITTED.length + 1) * 10}`)
console.log(`  signal pins used    ${fmt(pins)} of ${(FITTED.length + 1) * 22}`)

/* -- traffic between the packages ---------------------------------------- */
const produced = new Map<string, string>()
for (const d of [...FITTED, buildAintreqSplit()]) for (const c of d.cells) produced.set(c.name, d.name)
const consumers = new Map<string, string[]>()
for (const d of [...FITTED, buildAintreqSplit()]) for (const i of d.inputs) {
  consumers.set(i.name, [...(consumers.get(i.name) ?? []), d.name])
}
const crossing = [...produced].map(([net, from]) => ({
  net, from, to: (consumers.get(net) ?? []).filter((p) => p !== from),
})).filter((x) => x.to.length)
const crossingPins = crossing.reduce((n, x) => n + 1 + x.to.length, 0)

console.log(`\nPins that exist only because the parts are separate\n`)
for (const x of crossing.sort((a, b) => a.from.localeCompare(b.from))) {
  console.log(`     ${x.from.padEnd(8)} -> ${x.to.join(", ").padEnd(14)} ${x.net}`)
}
console.log(`\n  ${crossing.length} nets, ${crossingPins} pins.`)

/* -- what else on the card a die could swallow --------------------------- *
 * The card is 36 ICs and most of them are not logic: four SRAMs, four AD7528
 * multiplying DACs, three op-amps, a 4066, an oscillator and the passives all
 * stay exactly where they are. What CAN move: */
const ABSORB = [
  { what: "2 x 74HC590 - the free-running 16-bit colour-clock counter (§4.2)", ic: 2, mc: 16 },
  { what: "2 x 74HC688 - the 16-bit event comparator; its 32 compare inputs\n" +
          "                        become internal once the counter is (§4.2)", ic: 2, mc: 4 },
  { what: "1 x 74HC273 - ACTRL and master reset (§9.2)", ic: 1, mc: 8 },
  { what: "1 x 74HC174 - the three two-flop host synchronisers (§9.4.4)", ic: 1, mc: 6 },
  { what: "1 x 74HC07  - the open-drain /FIRQ stage. §8.1 costs this package\n" +
          "                        because \"a GAL22V10's outputs are totem-pole\"; the\n" +
          "                        ATF1508AS datasheet lists a Programmable Output Open\n" +
          "                        Collector Option, so on a CPLD it simply goes away", ic: 1, mc: 0 },
] as const
let aIc = 0, aMc = 0
console.log(`\nWhat else one die could take\n`)
for (const x of ABSORB) { aIc += x.ic; aMc += x.mc
  console.log(`     -${x.ic} IC  +${fmt(x.mc, 2)} mc   ${x.what}`) }
console.log(`\n  ${FITTED.length + 1} GALs + ${aIc} more packages -> 1.  Card 36 -> ${36 - (FITTED.length + 1) - aIc + 1}.`)
console.log(`  macrocells ${macrocells} + ${aMc} = ${macrocells + aMc} of 128.`)

/* -- and the pins, which is where it will be decided --------------------- *
 * Estimated, not fitted: the datapath these GALs sit in is drawn in audio.md
 * but the interfaces have never been enumerated. Flagged as an estimate
 * because every estimate on the video card was wrong until it was fitted. */
/* §9.5 matters here: "the sample-RAM address now has one source. It is the
 * state-file read bus - PTR when the sequencer fetches, SPTR when the host
 * writes - and nothing else drives it." So the sample RAM's 19 address lines
 * are BOARD WIRING between two memories and never enter the logic at all. What
 * does enter depends on how much is absorbed, and that turns out to be the
 * whole question. */
const CERTAIN = [
  ["state file: 11 address lines, driven by the sequencer", 11],
  ["state file and sample RAM control: /CE, /OE, /WE each", 6],
  ["host: D0-7, A3-A0, R/W, E, card select", 15],
  ["converter port registers and AD7528 chip selects (§6.3)", 10],
  ["/FIRQ, the 28.37516 MHz oscillator, ACTRL's analogue selects (§7)", 6],
] as const
const base = CERTAIN.reduce((n, [, c]) => n + c, 0)

console.log(`\nWhat has to reach a pin - ESTIMATED, not fitted\n`)
for (const [what, n] of CERTAIN) console.log(`     ${fmt(n, 2)}  ${what}`)
console.log(`     ${fmt(base, 2)}  base`)
console.log(`\n  ⚠ AND THE STATE-FILE DATA BUS, WHICH IS THE WHOLE QUESTION.`)
console.log(`     The 16-bit event comparator (§4.2) reads NEXT off that bus. Leave it`)
console.log(`     as 2 x '688 outside and the bus never enters the logic. Absorb it -`)
console.log(`     which is what deletes four of the seven packages above - and all 24`)
console.log(`     bits become inputs.`)

const CASES = [
  { what: "comparator stays external ('590 + '688 keep 4 packages)", io: base, mc: macrocells + 14 },
  { what: "comparator absorbed - the 24-bit state-file bus comes in", io: base + 24, mc: macrocells + aMc },
] as const

const PARTS = [
  { name: "ATF1508AS PLCC-84 ", mc: 128, io: 64 + 4, socket: true },
  { name: "ATF1508AS TQFP-100", mc: 128, io: 80 + 4 - 4, socket: false },
  { name: "ATF1508AS PQFP-160", mc: 128, io: 96 + 4 - 4, socket: false },
] as const

for (const c of CASES) {
  console.log(`\n  ${c.what}`)
  console.log(`     ${c.mc} macrocells, ~${c.io} I/O`)
  for (const q of PARTS) {
    console.log(`     ${q.name}  ${q.mc >= c.mc && q.io >= c.io ? "FITS" :
      q.mc < c.mc ? `${c.mc - q.mc} macrocells short` : `${c.io - q.io} pins short`}` +
      `${q.socket ? "   (socketed)" : ""}`)
  }
}
console.log(`\n  So the absorption that saves four packages is the same absorption that`)
console.log(`  costs the socket. That is the trade, and it is not a close call in`)
console.log(`  either direction - it is a choice between two comfortable fits.`)
console.log()
