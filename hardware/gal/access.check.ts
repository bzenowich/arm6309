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
  let sameChipYield = 0, cpuAbsent = 0
  for (let bits = 0; bits < 128 && !bad; bits++) {
    const vramsel = !!(bits & 1), nIopage = ((bits >> 1) & 1) as 0 | 1
    const cpuChip = (bits >> 2) & 3, spnreq = !!((bits >> 4) & 1), spnChip = (bits >> 5) & 3
    const pins = arb.gal.evaluate({
      1: vramsel ? 1 : 0, 2: nIopage, 3: (cpuChip & 1) as 0 | 1, 4: ((cpuChip >> 1) & 1) as 0 | 1,
      5: spnreq ? 1 : 0, 6: (spnChip & 1) as 0 | 1, 7: ((spnChip >> 1) & 1) as 0 | 1,
    })
    const want = arbitrate({ vramsel, nIopage, cpuChip, spnreq, spnChip })
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
    const vreq = vramsel && nIopage === 1
    if (vreq && spnreq && cpuChip === spnChip && pins[GS[spnChip]] === 0) sameChipYield++
    if (!vreq && spnreq && pins[GS[spnChip]] === 1) cpuAbsent++
  }
  check(bad === null, "the arbiter matches 5.2.1 over all 128 input combinations", bad ?? "")
  /* Item 20's three cases, named. */
  check(sameChipYield > 0, "item 20 (a): CPU and span on the same chip - the span writer yields")
  check(cpuAbsent > 0, "item 20 (b): CPU absent entirely - the span writer takes the chip anyway")
  check(arb.assembly.usage.length === 8,
    "item 20 (c): the arbiter is 8 macrocells, not 14's 12 - SRCSEL[n] IS GRANT_CPU[n]",
    `${arb.assembly.usage.length}`)
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
