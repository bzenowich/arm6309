/* The arbiter (graphics.md 19 item 20) and the WPTR pair (item 12).
 *   npm run check:access
 */

import { writeFileSync } from "node:fs"
import { join } from "node:path"
import { assemble, fuseChecksum, toJedec, toReport, type Design } from "./jedec/assemble"
import { Gal22v10, parseJedec } from "./jedec/simulate"
import { OLMC } from "./jedec/gal22v10"
import { arbDesign, wcolDesign, wrowDesign } from "./access.jedec"
import { COLUMNS, RING_ROWS, arbitrate, nextCol, nextRow, pointer } from "./access.model"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}
const here = new URL(".", import.meta.url).pathname
const build = (design: Design, base: string) => {
  const a = assemble(design)
  const jed = toJedec(design, a)
  writeFileSync(join(here, `${base}.jed`), jed)
  writeFileSync(join(here, `${base}.doc`), toReport(design, a))
  const p = parseJedec(jed)
  check(p.declaredChecksum === fuseChecksum(p.fuses),
    `${base}: fuse checksum, and the file reads back as written`)
  return { design, assembly: a, gal: new Gal22v10(p.fuses) }
}

const arb = build(arbDesign, "arb")
const wcol = build(wcolDesign, "wcol")
const wrow = build(wrowDesign, "wrow")

/* -- the arbiter, exhaustively: 128 input combinations -------------------- */
{
  const GC = [0, 1, 2, 3].map((n) => arb.assembly.usage.find((u) => u.name === `GCPU${n}`)!.pin)
  const GS = [0, 1, 2, 3].map((n) => arb.assembly.usage.find((u) => u.name === `GSPN${n}`)!.pin)
  let bad: string | null = null
  let sameChipYield = 0, cpuAbsent = 0, writeYield = 0
  /* ⛔ R/W IS SWEPT NOW AND IT WAS HELD AT 0. That is CLAUDE.md's third trap -
   * "a check that holds an input constant cannot see a defect in it" - and the
   * defect it could not see was the machine's first span deadlocking, because
   * the grant rule read the same for a posted write as for a read. 256
   * combinations, not 128. graphics.md 19 item 36. */
  for (let bits = 0; bits < 256 && !bad; bits++) {
    const vramsel = !!(bits & 1), nIopage = ((bits >> 1) & 1) as 0 | 1
    const cpuChip = (bits >> 2) & 3, spnreq = !!((bits >> 4) & 1), spnChip = (bits >> 5) & 3
    const rw = !!((bits >> 7) & 1)
    const pins = arb.gal.evaluate({
      1: vramsel ? 1 : 0, 2: nIopage, 3: (cpuChip & 1) as 0 | 1, 4: ((cpuChip >> 1) & 1) as 0 | 1,
      5: spnreq ? 1 : 0, 6: (spnChip & 1) as 0 | 1, 7: ((spnChip >> 1) & 1) as 0 | 1,
      8: spnreq ? 1 : 0, // SPANBUSY, for /WAIT
      9: 1,              // E, for /WAIT's E qualification (machine.md 5 item 8)
      10: rw ? 1 : 0,
    })
    const want = arbitrate({ vramsel, nIopage, cpuChip, rw, spnreq, spnChip })
    for (let n = 0; n < 4; n++) {
      if (pins[GC[n]] !== (want.gcpu[n] ? 1 : 0) || pins[GS[n]] !== (want.gspn[n] ? 1 : 0)) {
        bad = `chip ${n}: fuses give CPU=${pins[GC[n]]} SPAN=${pins[GS[n]]}, ` +
          `5.2.1 says ${want.gcpu[n] ? 1 : 0}/${want.gspn[n] ? 1 : 0} ` +
          `(VRAMSEL=${+vramsel} /IOPAGE=${nIopage} cpu=${cpuChip} spn=${spnChip} req=${+spnreq})`
      }
      /* Two drivers on one chip in one slot is the failure this part exists
       * to prevent, and it is worth asserting separately from the model. */
      if (pins[GC[n]] === 1 && pins[GS[n]] === 1) bad = `chip ${n} granted to both`
    }
    const vreq = vramsel && nIopage === 1 && rw
    if (vreq && spnreq && cpuChip === spnChip && pins[GS[spnChip]] === 0) sameChipYield++
    if (!vreq && spnreq && pins[GS[spnChip]] === 1) cpuAbsent++
    if (vramsel && nIopage === 1 && !rw && spnreq && cpuChip === spnChip
        && pins[GS[spnChip]] === 1) writeYield++
  }
  check(bad === null, "the arbiter matches 5.2.1 over all 256 input combinations", bad ?? "")
  /* Item 20's three cases, named. */
  check(sameChipYield > 0, "item 20 (a): CPU and span on the same chip - the span writer yields")
  check(cpuAbsent > 0, "item 20 (b): CPU absent entirely - the span writer takes the chip anyway")
  /* ⛔ THE CASE THAT DEADLOCKED THE MACHINE, now a claim: the CPU's own posted
   * VRAM write must NOT take the chip, or it blocks the span it just started
   * and /WAIT never releases. graphics.md 19 item 36. */
  check(writeYield > 0,
    "item 36: a CPU VRAM WRITE on the same chip - the span writer takes it anyway, " +
    "because a posted write needs no access of its own")
  check(arb.assembly.usage.length === 10,
    "item 20 (c): 8 grants - SRCSEL[n] IS GRANT_CPU[n], not a second macrocell - " +
    "plus the two the spare capacity was spent on: SPNGRANT and /WAIT",
    `${arb.assembly.usage.length}`)

  /* SPNGRANT is the four span grants ORed, so the sequencer needs one pin
   * instead of four: the arbiter has already matched the chip against
   * WPTR[1:0], and "which chip" is not something the span writer acts on. */
  const G = arb.assembly.usage.find((u) => u.name === "SPNGRANT")!
  /* It was sixteen terms - exactly full - because it was written as the four
   * per-chip grants ORed, which enumerates the chip four times and expands
   * !GRANT_CPU four ways inside each. The chip enumeration cancels: the span
   * writer is refused when the CPU wants THE SAME chip, so it is a comparison
   * and not a decode. Six terms, and the exhaustive check below is what says
   * the two are the same function. */
  check(G.used === 7, "SPNGRANT is 7 product terms, not the 16 it was written as",
    `${G.used}/${G.available}`)
  let orBad: string | null = null
  for (let bits = 0; bits < 256; bits++) {
    const vramsel = !!(bits & 1), nIopage = ((bits >> 1) & 1) as 0 | 1
    const cpuChip = (bits >> 2) & 3, spnreq = !!((bits >> 4) & 1), spnChip = (bits >> 5) & 3
    const pins = arb.gal.evaluate({
      1: vramsel ? 1 : 0, 2: nIopage, 3: (cpuChip & 1) as 0 | 1, 4: ((cpuChip >> 1) & 1) as 0 | 1,
      5: spnreq ? 1 : 0, 6: (spnChip & 1) as 0 | 1, 7: ((spnChip >> 1) & 1) as 0 | 1, 8: 1,
      9: 1, 10: ((bits >> 7) & 1) as 0 | 1,
    })
    const anyGrant = GS.some((p) => pins[p] === 1) ? 1 : 0
    if (pins[G.pin] !== anyGrant) orBad = `SPNGRANT ${pins[G.pin]} vs any grant ${anyGrant}`
  }
  check(orBad === null, "SPNGRANT is exactly the four span grants ORed", orBad ?? "")

  /* /WAIT is open-drain: it drives low or floats, never high. */
  const W = arb.assembly.usage.find((u) => u.name === "WAIT")!
  const held = arb.gal.evaluate({ 1: 1, 2: 1, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 1, 9: 1, 10: 0 })
  const idle = arb.gal.evaluate({ 1: 1, 2: 1, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 1, 10: 0 })
  check(held[W.pin] === 0 && idle[W.pin] === -1,
    "/WAIT pulls low on SPANBUSY . VRAMSEL . /IOPAGE . E and floats otherwise (3.3, 12.1)",
    `${held[W.pin]} / ${idle[W.pin]}`)

  /* machine.md 5 item 8's second rule: a wait is only useful while E is high,
   * and qualifying it at the source is one literal where qualifying it in the
   * divider would double the term count on E itself. This is that literal,
   * asserted rather than assumed - and it is new on 2026-09-08, along with
   * anything at all listening to this pin. */
  const eLow = arb.gal.evaluate({ 1: 1, 2: 1, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 1, 9: 0, 10: 0 })
  check(eLow[W.pin] === -1,
    "/WAIT floats while E is low - a wait only ever stretches the high half",
    `${eLow[W.pin]}`)

  /* graphics.md 7.4: only WRITES wait. The backstop protects the depth-1
   * posted-write latch, which a read does not touch - and a read that stalled
   * for up to 40.7 us is what features.md 8 and 9's save-behind and cursor
   * paths were paying. */
  const rd = arb.gal.evaluate({ 1: 1, 2: 1, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 1, 9: 1, 10: 1 })
  check(rd[W.pin] === -1,
    "/WAIT floats on a READ - only writes are throttled (7.4)", `${rd[W.pin]}`)
}

/* -- WPTR ----------------------------------------------------------------- */
const COLPIN = ["A0","A1","A2","A3","A4","A5","A6","A7","A8","A9"]
  .map((n) => wcol.assembly.usage.find((u) => u.name === n)!.pin)
const ROWPIN = ["A10","A11","A12","A13","A14","A15","A16","A17","A18"]
  .map((n) => wrow.assembly.usage.find((u) => u.name === n)!.pin)
const rd = (pins: Int8Array, map: number[]) => map.reduce((n, p, i) => n | (pins[p] << i), 0)

const cIn = (d: number, lda: 0|1, ldb: 0|1, winc: 0|1): Record<number, 0|1> => {
  const p: Record<number, 0|1> = { 10: lda, 11: ldb, 13: winc }
  for (let i = 0; i < 8; i++) p[2 + i] = ((d >> i) & 1) as 0 | 1
  return p
}
const rIn = (d: number, ldb: 0|1, ldc: 0|1, adv: 0|1): Record<number, 0|1> => {
  const p: Record<number, 0|1> = { 10: ldb, 11: ldc, 13: adv }
  for (let i = 0; i < 8; i++) p[2 + i] = ((d >> i) & 1) as 0 | 1
  return p
}

/* Write the three bytes the CPU writes, and read the pointer back. */
{
  let bad: string | null = null
  for (const value of [0, 1, 1023, 1024, 0x3ffff, 0x2aaaa, 0x15555, 319 * 1024 + 640]) {
    const b0 = value & 0xff, b1 = (value >> 8) & 0xff, b2 = (value >> 16) & 0x07
    wcol.gal.clock(cIn(b0, 1, 0, 0)); wcol.gal.clock(cIn(b1, 0, 1, 0))
    wrow.gal.clock(rIn(b1, 1, 0, 0)); wrow.gal.clock(rIn(b2, 0, 1, 0))
    const got = { col: rd(wcol.gal.evaluate(cIn(0, 0, 0, 0)), COLPIN),
                  row: rd(wrow.gal.evaluate(rIn(0, 0, 0, 0)), ROWPIN) }
    if (pointer(got) !== value) {
      bad = `wrote $${value.toString(16)}, read back $${pointer(got).toString(16)}`
      break
    }
  }
  check(bad === null, "WPTR loads as three bytes and reads back as one 19-bit pointer", bad ?? "")
}

/* The wrap, which is item 12. */
{
  const start = 1020
  wcol.gal.clock(cIn(start & 0xff, 1, 0, 0)); wcol.gal.clock(cIn(start >> 8, 0, 1, 0))
  wrow.gal.clock(rIn(0x2c, 1, 0, 0)); wrow.gal.clock(rIn(0, 0, 1, 0)) // row 11
  const rowBefore = rd(wrow.gal.evaluate(rIn(0, 0, 0, 0)), ROWPIN)
  const seen: number[] = []
  let rowMoved = false
  for (let i = 0; i < 8; i++) {
    seen.push(rd(wcol.gal.evaluate(cIn(0, 0, 0, 1)), COLPIN))
    wcol.gal.clock(cIn(0, 0, 0, 1))
    if (rd(wrow.gal.evaluate(rIn(0, 0, 0, 0)), ROWPIN) !== rowBefore) rowMoved = true
  }
  check(seen.join(",") === "1020,1021,1022,1023,0,1,2,3",
    "item 12: a linear write wraps to column 0 of the SAME row at the 1024 boundary",
    seen.join(","))
  check(!rowMoved,
    "item 12: and it does not advance the row - which matches hadr, whose scan " +
    "column wraps the same way, so writer and scanner agree about column 1023")
}

/* Why it wraps: there is no macrocell left to carry from. */
{
  const free = 10 - wcol.assembly.usage.length
  const dedicated = 11
  check(free === 0 && wcolDesign.inputs.length === dedicated,
    "item 12 is decided by the fit: wcol is 10 of 10 macrocells AND 11 of 11 " +
    "input pins, so a carry out of the column has nowhere to come from",
    `${free} macrocells, ${dedicated - wcolDesign.inputs.length} pins free`)
  const widest = Math.max(...Object.values(OLMC).map((m) => m.terms))
  check(wcol.assembly.usage.every((u) => u.used <= u.available) &&
        wcol.assembly.usage.some((u) => u.used > widest - 6),
    "wcol fits only on the sorted pairing - its top bit needs 12 of 16 terms")
}

/* The row advance: WADV = 01 and 10 both come here as one pulse. */
{
  wrow.gal.clock(rIn(0xfc, 1, 0, 0)); wrow.gal.clock(rIn(7, 0, 1, 0)) // row 511
  const before = rd(wrow.gal.evaluate(rIn(0, 0, 0, 0)), ROWPIN)
  wrow.gal.clock(rIn(0, 0, 0, 1))
  const after = rd(wrow.gal.evaluate(rIn(0, 0, 0, 0)), ROWPIN)
  check(before === RING_ROWS - 1 && after === 0,
    "the row advance wraps on the ring, so a vertical span cannot leave the torus",
    `${before} -> ${after}`)
}

console.log("\nThe fit\n")
for (const p of [arb, wcol, wrow]) {
  const free = 10 - p.assembly.usage.length
  const avail = (p.design.clockPin === undefined ? 12 : 11) + free
  console.log(`      ${p.design.partNo}  ${p.design.name.padEnd(4)} ` +
    `${p.assembly.usage.length} macrocells (${free} free), ` +
    `${p.design.inputs.length} of ${avail} inputs`)
}
console.log(failures === 0
  ? "\nThe arbiter and the WPTR pair fit, and item 12 has an answer"
  : `\n${failures} FAILED`)
if (failures) process.exit(1)
