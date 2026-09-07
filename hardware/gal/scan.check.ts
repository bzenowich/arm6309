/* Assemble the scan-address pair and check the fuses against the geometry.
 *
 * graphics.md 19 item 8 says this pair is "20 of 20, zero margin" and item 15
 * concludes from that that tile mode needs a third package. Both rest on
 * counting the scan address as 19 flat bits plus a carry. Section 8 of the
 * same document describes the hardware it actually is - a 9-bit row counter
 * and an 8-bit column counter, with A1..A0 being the interleave phase and not
 * address bits at all - and that is 17 of 20.
 *
 *   npm run check:scan
 */

import { writeFileSync } from "node:fs"
import { join } from "node:path"

import { assemble, fuseChecksum, toJedec, toReport, type Design } from "./jedec/assemble"
import { Gal22v10, parseJedec } from "./jedec/simulate"
import { hadrDesign, vadrDesign } from "./scan.jedec"
import { COLUMNS, CHIPS, RING_ROWS, expected } from "./scan.model"

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
  const parsed = parseJedec(jed)
  check(parsed.declaredChecksum === fuseChecksum(parsed.fuses),
    `${base}: fuse checksum, and the file reads back as written`)
  return { design, assembly: a, gal: new Gal22v10(parsed.fuses) }
}

const hadr = build(hadrDesign, "hadr")
const vadr = build(vadrDesign, "vadr")

/* -- the count item 8 got wrong ------------------------------------------ */
{
  const used = hadr.assembly.usage.length + vadr.assembly.usage.length
  check(used === 17,
    "the scan pair is 17 macrocells of 20, not item 8's 19 + carry = 20 of 20", `${used}`)
  check(hadr.assembly.usage.length === 8 && vadr.assembly.usage.length === 9,
    "8 column bits (A9..A2) and 9 row bits (A18..A10) - section 8's own split")
  check(20 - used === 3,
    "three macrocells spare, which is what item 15 says tile mode has none of")
  for (const p of [hadr, vadr]) {
    const over = p.assembly.usage.filter((u) => u.used > u.available)
    check(over.length === 0, `${p.design.name}: every equation fits its macrocell`,
      over.map((u) => `${u.name} ${u.used}/${u.available}`).join(", "))
  }
}

/* -- the addresses ------------------------------------------------------- */
const HPIN = [14, 15, 16, 17, 18, 19, 20, 21]              // A2..A9
const VPIN = [14, 15, 22, 16, 21, 17, 20, 18, 19]          // A10..A18
const bits = (pins: Int8Array, map: number[]) =>
  map.reduce((n, pin, i) => n | (pins[pin] << i), 0)

const hIn = (fetch: 0 | 1, load: 0 | 1, hscroll: number): Record<number, 0 | 1> => {
  const hs = (hscroll >> 2) & 0xff
  const p: Record<number, 0 | 1> = { 2: fetch, 3: 1, 4: load }
  const pins = [5, 6, 7, 8, 9, 10, 11, 13]
  pins.forEach((pin, i) => { p[pin] = ((hs >> i) & 1) as 0 | 1 })
  return p
}
const vIn = (adv: 0 | 1, load: 0 | 1, vscroll: number): Record<number, 0 | 1> => {
  const p: Record<number, 0 | 1> = { 2: adv, 3: 1, 4: load }
  const pins = [5, 6, 7, 8, 9, 10, 11, 13, 23]
  pins.forEach((pin, i) => { p[pin] = ((vscroll >> i) & 1) as 0 | 1 })
  return p
}

const ACTIVE_SLOTS = 160 // 640 pixels / 4

for (const [hscroll, vscroll, doubled, lines] of [
  [0, 0, false, 400], [641, 500, false, 400], [1021, 509, true, 400],
] as const) {
  let bad: string | null = null
  let wrappedCol = false, wrappedRow = false

  hadr.gal.reset(); vadr.gal.reset()
  /* Vertical blank: load the row counter from VSCROLL. */
  vadr.gal.clock(vIn(0, 1, vscroll))

  for (let line = 0; line < lines && !bad; line++) {
    /* Horizontal blank: load the column counter from HSCROLL. */
    hadr.gal.clock(hIn(0, 1, hscroll))

    for (let slot = 0; slot < ACTIVE_SLOTS; slot++) {
      const col = bits(hadr.gal.evaluate(hIn(1, 0, hscroll)), HPIN)
      const row = bits(vadr.gal.evaluate(vIn(0, 0, vscroll)), VPIN)
      const want = expected(line, slot, hscroll, vscroll, doubled)
      if (col !== want.col || row !== want.row) {
        bad = `line ${line} slot ${slot}: fuses give row ${row} col ${col}, ` +
          `geometry says row ${want.row} col ${want.col}`
        break
      }
      if (slot > 0 && col === 0) wrappedCol = true
      hadr.gal.clock(hIn(1, 0, hscroll))
    }
    /* End of the displayed line. Line-doubled modes withhold every second
     * advance, which is the whole of line doubling. */
    const adv = doubled ? (line % 2 === 1 ? 1 : 0) : 1
    if (bits(vadr.gal.evaluate(vIn(0, 0, vscroll)), VPIN) === 0 && line > 0) wrappedRow = true
    vadr.gal.clock(vIn(adv as 0 | 1, 0, vscroll))
  }

  const label = `HSCROLL=${hscroll} VSCROLL=${vscroll}${doubled ? " doubled" : ""}`
  check(bad === null,
    `${label}: every address of a ${lines}-line frame matches the 1024x512 torus`, bad ?? "")
  if (hscroll > COLUMNS - 640) {
    check(wrappedCol, `${label}: the column wrapped inside the row, as the torus requires`)
  }
  if (vscroll + (doubled ? lines / 2 : lines) > RING_ROWS) {
    check(wrappedRow, `${label}: the row wrapped on the ring`)
  }
}

/* -- the claim the whole saving rests on --------------------------------- */
{
  /* Seventeen bits is exactly a 128K x 8's address width, which is the check
   * that A1..A0 really are the mux phase and not something that got lost. */
  const generated = hadr.assembly.usage.length + vadr.assembly.usage.length
  check(generated === Math.log2(512 * 1024 / CHIPS),
    "17 address bits is exactly one AS6C1008's address width - the interleave " +
    "phase is the other two, and it never leaves the '153s", `${generated}`)
  /* And no carry between them: the column counter's rollover must not touch
   * a row bit, or the torus is not a torus. */
  hadr.gal.reset(); vadr.gal.reset()
  vadr.gal.clock(vIn(0, 1, 7))
  hadr.gal.clock(hIn(0, 1, 1020))
  let rowMoved = false
  for (let i = 0; i < 300; i++) {
    hadr.gal.clock(hIn(1, 0, 1020))
    if (bits(vadr.gal.evaluate(vIn(0, 0, 7)), VPIN) !== 7) rowMoved = true
  }
  check(!rowMoved,
    "the column counter rolls over 256 times without disturbing the row - " +
    "no inter-package carry exists, and item 8 budgets a macrocell for one")
}

console.log("\nThe fit\n")
for (const p of [hadr, vadr]) {
  const free = 10 - p.assembly.usage.length
  console.log(`      ${p.design.partNo}  ${p.design.name}  ${p.assembly.usage.length} macrocells, ` +
    `${free} free, ${p.design.inputs.length} of ${11 + free} inputs`)
}
console.log(failures === 0
  ? "\nThe scan pair is 17 of 20 and generates the torus correctly"
  : `\n${failures} FAILED`)
if (failures) process.exit(1)
