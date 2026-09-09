/* The audio card's five GALs - audio.md §9.5's allocation, fitted and checked.
 *
 * Four of the five fit. The fifth does not, and it does not fit in either of
 * the two ways it can be arranged, which is the result this check exists to
 * record.
 *
 *   npm run check:audio
 */

import { writeFileSync } from "node:fs"
import { join } from "node:path"
import { assemble, fuseChecksum, toJedec, toReport, type Design } from "./jedec/assemble"
import { Gal22v10, parseJedec } from "./jedec/simulate"
import {
  aseqDesign, adecDesign, admatDesign, aintenaDesign, apendDesign,
  buildAintreqWhole, buildAintreqSplit,
} from "./audio.jedec"
import {
  PRESCALE, SLOTS_PER_FRAME, isChannel, isDeferred, isFrameEnd, isHost, isTimer,
  nextSlot, setClear,
} from "./audio.model"
import { audioCpld } from "./audio.cpld"
import { aseqCpld } from "./aseq.cpld"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}
const here = new URL(".", import.meta.url).pathname
const build = (d: Design) => {
  const a = assemble(d)
  writeFileSync(join(here, `${d.name}.jed`), toJedec(d, a))
  writeFileSync(join(here, `${d.name}.doc`), toReport(d, a))
  const p = parseJedec(toJedec(d, a))
  check(p.declaredChecksum === fuseChecksum(p.fuses), `${d.name}: fuse checksum`)
  return { design: d, assembly: a, gal: new Gal22v10(p.fuses) }
}

console.log("The four that fit\n")
const aseq = build(aseqDesign)
const adec = build(adecDesign)
const admat = build(admatDesign)
const aintena = build(aintenaDesign)
const apend = build(apendDesign)

const pinOf = (p: { assembly: { usage: { name: string; pin: number }[] } }, n: string) =>
  p.assembly.usage.find((u) => u.name === n)!.pin

/* -- the slot walk, §3.1 -------------------------------------------------- */
{
  const SL = ["S0", "S1", "S2"].map((n) => pinOf(aseq, n))
  aseq.gal.reset()
  let bad: string | null = null, model = 0
  for (let i = 0; i < 40 && !bad; i++) {
    const p = aseq.gal.evaluate({ 2: 1, 3: 0 })
    const slot = SL.reduce((n, pin, b) => n | (p[pin] << b), 0)
    if (slot !== model) { bad = `step ${i}: slot ${slot}, model ${model}`; break }
    const want = {
      CHANSLOT: isChannel(slot) ? 1 : 0, TMRSLOT: isTimer(slot) ? 1 : 0,
      HOSTSLOT: isHost(slot) ? 1 : 0, DEFSLOT: isDeferred(slot) ? 1 : 0,
      CCLK: isFrameEnd(slot) ? 1 : 0,
    }
    for (const [n, v] of Object.entries(want)) {
      if (p[pinOf(aseq, n)] !== v) bad = `${n} = ${p[pinOf(aseq, n)]}, expected ${v} in slot ${slot}`
    }
    aseq.gal.clock({ 2: 1, 3: 0 }); model = nextSlot(model)
  }
  check(bad === null,
    `aseq: the slot walk is ${SLOTS_PER_FRAME} slots and every phase decode agrees ` +
    "with §3.1 over five frames", bad ?? "")
  check(!bad, "aseq: slots 0-3 are the channels, 4 the timer, 5 host service, 6-7 deferred")
}

/* -- the host decode, §9.2's sixteen bytes -------------------------------- */
{
  const STROBE: Record<string, [number, boolean]> = {
    WAIDX: [0x0, false], WDMACON: [0x2, false], WINTENA: [0x3, false],
    WINTREQ: [0x4, false], WCTRL: [0x5, false], RINTREQ: [0x4, true], RASTAT: [0xa, true],
  }
  let bad: string | null = null
  for (let off = 0; off < 16 && !bad; off++) {
    for (const rw of [0, 1] as const) for (const sel of [0, 1] as const) {
      const p = adec.gal.evaluate({ 1: sel, 2: (off & 1) as 0|1, 3: ((off>>1)&1) as 0|1,
        4: ((off>>2)&1) as 0|1, 5: ((off>>3)&1) as 0|1, 6: rw, 7: 1 })
      for (const [name, [want, isRead]] of Object.entries(STROBE)) {
        const on = sel === 1 && off === want && (rw === 1) === isRead
        if (p[pinOf(adec, name)] !== (on ? 1 : 0)) {
          bad = `${name} at +$${off.toString(16)} R/W=${rw} SEL=${sel}`
        }
      }
    }
  }
  check(bad === null, "adec: every strobe fires at exactly its offset, over all 16 x R/W x SEL",
    bad ?? "")
}

/* -- Paula's set/clear convention, §9.2 ----------------------------------- */
const checkSetClear = (
  part: typeof admat, strobePin: number, dataPins: Record<number, number>,
  width: number, name: string, prefix: string, fixed: Record<number, 0 | 1> = {},
) => {
  let bad: string | null = null
  const drive = (data: number, w: 0 | 1): Record<number, 0 | 1> => {
    const io: Record<number, 0 | 1> = { 2: 1, [strobePin]: w, ...fixed }
    for (const [bit, pin] of Object.entries(dataPins)) io[pin] = ((data >> Number(bit)) & 1) as 0 | 1
    return io
  }
  part.gal.reset()
  let model = 0
  /* every combination of write data and set/clear, twice over */
  for (let round = 0; round < 2 && !bad; round++) {
    for (let data = 0; data < 256 && !bad; data++) {
      part.gal.clock(drive(data, 1))
      model = setClear(model, data, true, width)
      const p = part.gal.evaluate(drive(0, 0))
      const got = [...Array(width).keys()].reduce(
        (n, i) => n | (p[pinOf(part, `${prefix}${i}`)] << i), 0)
      if (got !== model) bad = `wrote $${data.toString(16)}: got ${got}, model ${model}`
    }
  }
  check(bad === null, `${name}: Paula's set/clear over all 256 written bytes, twice`, bad ?? "")
}
checkSetClear(admat, 3, { 0: 5, 1: 6, 2: 7, 3: 8, 7: 9 }, 4, "admat DMACON", "DMAEN", { 4: 0 })
checkSetClear(aintena, 3, { 0: 4, 1: 5, 2: 6, 3: 7, 4: 8, 5: 9, 7: 10 }, 6, "aintena", "ENA")

/* -- the tempo prescale, §8.2 --------------------------------------------- */
{
  const P = ["P0", "P1", "P2"].map((n) => pinOf(admat, n))
  admat.gal.reset()
  const io = (cclk: 0 | 1): Record<number, 0 | 1> =>
    ({ 2: 1, 3: 0, 4: cclk, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0 })
  const seen: number[] = []
  for (let i = 0; i < 12; i++) {
    seen.push(P.reduce((n, pin, b) => n | (admat.gal.evaluate(io(1))[pin] << b), 0))
    admat.gal.clock(io(1))
  }
  check(seen.slice(0, 10).join(",") === "0,1,2,3,4,0,1,2,3,4",
    `admat: the tempo prescale is ÷${PRESCALE} - the CIA-B clock itself, not an ` +
    "approximation, so every replayer's Fxx arithmetic transfers unchanged", seen.join(","))
}

/* -- the pending register, §9.4.5 ----------------------------------------- */
{
  const PP = [0, 1, 2, 3, 4, 5].map((i) => pinOf(apend, `PEND${i}`))
  const io = (merge: 0 | 1, set: number): Record<number, 0 | 1> => {
    const d: Record<number, 0 | 1> = { 2: 1, 3: merge }
    for (let i = 0; i < 6; i++) d[4 + i] = ((set >> i) & 1) as 0 | 1
    return d
  }
  apend.gal.reset()
  apend.gal.clock(io(0, 0b010101))
  const held = PP.reduce((n, pin, b) => n | (apend.gal.evaluate(io(0, 0))[pin] << b), 0)
  apend.gal.clock(io(0, 0b101010))
  const both = PP.reduce((n, pin, b) => n | (apend.gal.evaluate(io(0, 0))[pin] << b), 0)
  apend.gal.clock(io(1, 0))
  const merged = PP.reduce((n, pin, b) => n | (apend.gal.evaluate(io(0, 0))[pin] << b), 0)
  check(held === 0b010101 && both === 0b111111 && merged === 0,
    "apend: sets accumulate and the merge clears them - the ordering §9.4.5 needs " +
    "for \"read AINTREQ, then clear what you saw\" to be race-free",
    `${held.toString(2)} / ${both.toString(2)} / ${merged}`)
}

/* -- and the one that does not fit ---------------------------------------- */
console.log("\nGAL 5, which §9.5 budgets at 12 macrocells on a 10-macrocell part\n")
{
  const refused = (build: () => Design) => {
    try { assemble(build()); return null } catch (e) { return (e as Error).message }
  }
  const whole = refused(buildAintreqWhole)
  const split = refused(buildAintreqSplit)
  check(whole !== null && /13 equations for 10 macrocells/.test(whole),
    "together: INTREQ + pending + /FIRQ is 13 macrocells and the part has 10", whole ?? "FITS")
  check(split !== null && /17 inputs need pins and the part has 14/.test(split),
    "apart: moving pending off-part makes the six PEND bits into pins, and 17 " +
    "inputs need holes the part has 14 of", split ?? "FITS")
  console.log(`      whole: ${whole}`)
  console.log(`      split: ${split}`)
}

/* -- the port census, as a check rather than as a report ------------------
 *
 * ⭐ THE ONE THAT WOULD HAVE FOUND THREE OF 2026-09-09's FOUR DEFECTS. `SEL`,
 * the host read-back path and the prefetch latch's output enable were each a
 * paragraph in audio.md describing a mechanism, and each was a signal the
 * design READ or a pin the board needed that NOTHING PRODUCED. That is a
 * property of the term lists, so it can be asserted instead of noticed:
 * enumerate every literal the merged design reads, subtract what it produces
 * and what the backplane and the card's own board supply, and require the
 * remainder to be exactly a list somebody has written down with a reason.
 *
 * `npm run census:audio` prints the same set at length. This is the half that
 * FAILS - design-review2.md's method 1 found eleven unbuilt blocks on the
 * video card by hand, and a census nobody runs is a census. */
console.log("\nThe port census - every input has a producer, or a reason\n")
{
  const BACKPLANE = new Set([
    "IOSEL", "E", "RW", "RESET",
    "A0", "A1", "A2", "A3", "A4", "A5", "A6",
    "D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7",
  ])
  const BOARD = new Set(["SLOTCLK"])
  /* Signals U2 - the sequencer of audio.md §10.2 - owes U1. Every entry is a
   * signal that is UNBUILT, and the list is here so that adding a twelfth
   * unproduced input has to be a deliberate act with a line of prose behind
   * it rather than something a merge does quietly. */
  const FROM_SEQUENCER: Record<string, string> = {
    SETA: "8.1's six sources, as a 3-bit code - 10.2.6's lever",
    SETB: "8.1 sources, bit 1", SETC: "8.1 sources, bit 2",
    PWBUSY: "9.2 ASTAT b6", PFVALID: "9.2 ASTAT b7",
  }
  const produced = new Set(audioCpld.cells.map((c) => c.name))
  const consumed = new Set<string>()
  for (const c of audioCpld.cells) {
    for (const t of [...c.terms, c.oe ?? ""].join(" & ").split("&")) {
      const n = t.trim().replace(/^!/, "")
      if (n && /^[A-Za-z_]/.test(n)) consumed.add(n)
    }
  }
  if (audioCpld.clock) consumed.add(audioCpld.clock)
  if (audioCpld.ar) consumed.add(audioCpld.ar)

  const orphan = [...consumed].filter(
    (n) => !produced.has(n) && !BACKPLANE.has(n) && !BOARD.has(n)).sort()
  const u2 = new Set(aseqCpld.cells.filter((c) => aseqCpld.external.has(c.name))
    .map((c) => c.name))
  const unexpected = orphan.filter((n) => !(n in FROM_SEQUENCER))
  const gone = Object.keys(FROM_SEQUENCER).filter((n) => !orphan.includes(n)).sort()
  check(unexpected.length === 0,
    `every signal U1 reads is produced, on the backplane, or one of the ` +
    `${Object.keys(FROM_SEQUENCER).length} U2 owes it`,
    unexpected.length ? `NOTHING PRODUCES ${unexpected.join(", ")}` : "")
  check(gone.length === 0,
    "and the list has no dead entries - a signal that gained a producer leaves it",
    gone.join(", "))
  /* ⭐ AND THE OTHER DIRECTION, which is the whole of what "two parts" costs:
   * every signal U1 owes U2 must actually be an output of U2, and every signal
   * U2 reads must be an output of U1 or come off the board. A card whose two
   * dice each fit and do not join is design-review2.md V-3 with a package
   * boundary through it. */
  const wanted = Object.keys(FROM_SEQUENCER).filter((n) => !u2.has(n))
  check(wanted.length === 0, "and U2 actually drives every one of them", wanted.join(", "))

  const u1out = new Set(audioCpld.cells.filter((c) => audioCpld.external.has(c.name))
    .map((c) => c.name))
  const BOARDIN = new Set([...BACKPLANE, ...BOARD, "HIT", "ACOUT"])
  const u2orphan = aseqCpld.inputs.map((i) => i.name)
    .filter((n) => !u1out.has(n) && !BOARDIN.has(n)).sort()
  check(u2orphan.length === 0,
    "and every signal U2 reads is a U1 output, a backplane line, or the '688 " +
    "and the '283 chain answering it",
    u2orphan.length ? `NOTHING PRODUCES ${u2orphan.join(", ")}` : "")
  console.log(`      U1 -> U2  ${aseqCpld.inputs.map((i) => i.name)
    .filter((n) => u1out.has(n)).length} nets`)
  console.log(`      U2 -> U1  ${Object.keys(FROM_SEQUENCER).length} nets`)
  console.log(`      U2 pins   ${u2.size} out, ${aseqCpld.inputs.length} in`)

  /* ⚠ AND THE SEVEN-BIT DECODE. The geographic window is 128 bytes since
   * 2026-09-08, so a card that matches only A5..A0 answers at its base AND 64
   * bytes below it - two cards on D0-D7 at once, silently. Every card decode
   * in this repository has to read A6, and audio's did not read ANY address
   * bit above A3 until SEL stopped being a pin. */
  const readsA6 = consumed.has("A6") && consumed.has("A5") && consumed.has("A4")
  check(readsA6 && produced.has("SEL"),
    "9.1: the card completes its own decode - SEL is produced here from A6, A5 and A4, " +
    "not taken as a pin the board does not drive",
    `${produced.has("SEL") ? "" : "SEL is an input; "}${readsA6 ? "" : "A6/A5/A4 unread"}`)
}

console.log(failures === 0
  ? "\nFour of §9.5's five fit. The interrupt block does not fit a GAL22V10 either way."
  : `\n${failures} FAILED`)
if (failures) process.exit(1)
