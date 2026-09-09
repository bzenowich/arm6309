/* The span writer's control, checked against its state machine and against
 * the 8 x 8 geometry that defines it.  npm run check:seqctl */

import { writeFileSync } from "node:fs"
import { join } from "node:path"
import { assemble, fuseChecksum, toJedec, toReport } from "./jedec/assemble"
import { Gal22v10, parseJedec } from "./jedec/simulate"
import { seqctlDesign } from "./seqctl.jedec"
import { CELL_PIXELS, IDLE, outputs, step, type SpanIn, type SpanState } from "./seqctl.model"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

const here = new URL(".", import.meta.url).pathname
const a = assemble(seqctlDesign)
const jed = toJedec(seqctlDesign, a)
writeFileSync(join(here, "seqctl.jed"), jed)
writeFileSync(join(here, "seqctl.doc"), toReport(seqctlDesign, a))
const p = parseJedec(jed)
check(p.declaredChecksum === fuseChecksum(p.fuses),
  "seqctl: fuse checksum, and the file reads back as written")
const gal = new Gal22v10(p.fuses)
const pin = (n: string) => a.usage.find((u) => u.name === n)!.pin

const drive = (io: SpanIn): Record<number, 0 | 1> => ({
  2: 1, 3: io.wstb ? 1 : 0,
  4: (io.wmode & 1) as 0 | 1, 5: ((io.wmode >> 1) & 1) as 0 | 1,
  6: io.spngrant ? 1 : 0, 7: io.tc ? 1 : 0,
  8: (io.wadv & 1) as 0 | 1, 9: ((io.wadv >> 1) & 1) as 0 | 1,
  10: io.maskbit ? 1 : 0,
})
const readState = (): SpanState => ({
  busy: gal.regs.get(pin("SPANBUSY"))! as 0 | 1,
  mc: gal.regs.get(pin("MC0"))! | (gal.regs.get(pin("MC1"))! << 1) | (gal.regs.get(pin("MC2"))! << 2),
})

/* -- exhaustive over every state and every input ------------------------- */
{
  let bad: string | null = null
  for (let st = 0; st < 16 && !bad; st++) {
    for (let inb = 0; inb < 256 && !bad; inb++) {
      const s: SpanState = { busy: (st & 1) as 0 | 1, mc: st >> 1 }
      const io: SpanIn = {
        wstb: !!(inb & 1), spngrant: !!(inb & 2), tc: !!(inb & 4),
        wmode: (inb >> 3) & 3, wadv: (inb >> 5) & 3,
        maskbit: !!(inb & 128),
      }
      /* force the part into this state */
      gal.reset()
      gal.regs.set(pin("SPANBUSY"), s.busy)
      gal.regs.set(pin("MC0"), (s.mc & 1) as 0 | 1)
      gal.regs.set(pin("MC1"), ((s.mc >> 1) & 1) as 0 | 1)
      gal.regs.set(pin("MC2"), ((s.mc >> 2) & 1) as 0 | 1)

      const pins = gal.evaluate(drive(io))
      const want = outputs(s, io)
      for (const k of ["retire", "wen", "spanend", "wrowadv"] as const) {
        const got = pins[pin(k.toUpperCase())]
        if (got !== want[k]) {
          bad = `${k} = ${got}, expected ${want[k]} in busy=${s.busy} mc=${s.mc} ` +
            `wstb=${+io.wstb} grant=${+io.spngrant} tc=${+io.tc} wmode=${io.wmode} wadv=${io.wadv}`
        }
      }
      gal.clock(drive(io))
      const after = readState(), wantAfter = step(s, io)
      if (after.busy !== wantAfter.busy || after.mc !== wantAfter.mc) {
        bad = `state ${after.busy}/${after.mc}, expected ${wantAfter.busy}/${wantAfter.mc} ` +
          `from busy=${s.busy} mc=${s.mc} wstb=${+io.wstb} grant=${+io.spngrant}`
      }
    }
  }
  check(bad === null,
    "the fuses match the state machine over all 16 states x 256 input combinations", bad ?? "")
}

/* -- a span, run end to end, in each mode --------------------------------- */
const runSpan = (wmode: number, wadv: number, tcAfter: number, mask = 0xff) => {
  gal.reset()
  const base: SpanIn = { wstb: false, wmode, spngrant: false, tc: false, wadv, maskbit: true }
  gal.clock(drive({ ...base, wstb: true }))          // the posted write lands
  let retired = 0, written = 0, rowAdv = 0, guard = 0, busySlots = 0
  while (gal.regs.get(pin("SPANBUSY")) === 1 && guard++ < 64) {
    /* The serialiser shifts MSB first, one bit per retired byte - so the bit
     * this slot sees is the one the '165 is presenting. */
    const io: SpanIn = {
      ...base, spngrant: true, tc: retired >= tcAfter - 1,
      maskbit: ((mask >> (7 - (retired % 8))) & 1) === 1,
    }
    const pins = gal.evaluate(drive(io))
    if (pins[pin("RETIRE")]) retired++
    if (pins[pin("WEN")]) written++
    if (pins[pin("WROWADV")]) rowAdv++
    busySlots++
    gal.clock(drive(io))
  }
  return { retired, written, rowAdv, busySlots }
}

{
  /* span-mask. TC is held TRUE throughout, which would end the span early if
   * mask mode consulted SPANLEN. It does not - that is the 8 x 8 result. */
  const r = runSpan(1, 1, 1)
  check(r.retired === CELL_PIXELS,
    `span-mask retires exactly ${CELL_PIXELS} bytes - one glyph row - and does ` +
    "NOT consult SPANLEN, asserted with the '161's terminal count held true throughout",
    `${r.retired}`)
  check(r.rowAdv === 1, "and pulses WROWADV once, so WADV=01 chains to the next glyph row")

  const solid = runSpan(2, 0, 5)
  check(solid.retired === 5, "span-solid retires SPANLEN+1 bytes, ended by the '161 pair", `${solid.retired}`)
  check(solid.rowAdv === 0, "and does not advance the row when WADV=00")

  const direct = runSpan(0, 0, 99)
  check(direct.retired === 1, "a direct posted write retires exactly one byte", `${direct.retired}`)

  /* -- sprite mode, features.md 8.4 -------------------------------------- */
  /* WMODE 11: eight bytes like mask, but a zero mask bit advances the pointer
   * WITHOUT writing. The whole value of the mode is that the pointer keeps
   * moving - a mode that stalled it would draw the sprite squashed. */
  const solidMask = runSpan(3, 1, 1, 0xff)
  check(solidMask.retired === CELL_PIXELS && solidMask.written === CELL_PIXELS,
    "⭐ sprite mode with an all-ones mask writes all eight - it is span-mask " +
    "with a gate, not a different span", `${solidMask.written}/${solidMask.retired}`)

  const halfMask = runSpan(3, 1, 1, 0b11110000)
  check(halfMask.retired === CELL_PIXELS && halfMask.written === 4,
    "⚠ and with half the bits clear it RETIRES eight and WRITES four - the " +
    "pointer, the serialiser and the counter all still advance, which is what " +
    "keeps the shape the right width", `${halfMask.written} written of ${halfMask.retired}`)

  const empty = runSpan(3, 1, 1, 0x00)
  check(empty.retired === CELL_PIXELS && empty.written === 0,
    "an all-zero row writes nothing at all and still takes eight slots - " +
    "transparency costs time, not correctness", `${empty.written}`)
  check(empty.rowAdv === 1,
    "and still chains: WADV=01 advances the row whether anything was drawn or not")

  /* The three older modes must be blind to the mask bit. */
  const maskLow = runSpan(1, 1, 1, 0x00)
  check(maskLow.written === CELL_PIXELS,
    "⭐ span-mask is UNCHANGED by the new input - a zero bit still writes WBG " +
    "through the register file's address line, which is the mechanism 7.4 " +
    "describes and costs no logic here", `${maskLow.written}`)
  check(runSpan(2, 0, 5, 0x00).written === 5 && runSpan(0, 0, 99, 0x00).written === 1,
    "and so are span-solid and the direct write")
}

/* -- the geometry, and 7.3's headline number ------------------------------ */
{
  const rows = CELL_PIXELS
  const perRow = runSpan(1, 1, 1).retired
  const setupWrites = 5           // WPTR x3, WFG, WBG
  const cellWrites = setupWrites + rows
  check(perRow * rows === CELL_PIXELS * CELL_PIXELS,
    `one cell is ${rows} mask writes x ${perRow} bytes = ${perRow * rows} bytes, ` +
    "which is an 8x8 cell at 8bpp")
  check(cellWrites === 13,
    "13 CPU writes per character cell (7.3): WPTR x3 + WFG + WBG, then one per " +
    "glyph row. SPANLEN is not among them - if mask mode needed it, it would be 14",
    `${cellWrites}`)
}

/* -- the /WAIT backstop --------------------------------------------------- */
{
  gal.reset()
  const io: SpanIn = { wstb: true, wmode: 1, spngrant: false, tc: false, wadv: 0 }
  gal.clock(drive(io))
  let stillBusy = true
  for (let i = 0; i < 40; i++) {
    const s = { ...io, wstb: false }
    if (gal.evaluate(drive(s))[pin("RETIRE")]) stillBusy = false
    gal.clock(drive(s))
  }
  check(stillBusy && gal.regs.get(pin("SPANBUSY")) === 1,
    "with no grant the span stalls and SPANBUSY stays asserted - which is what " +
    "holds /WAIT on the arbiter (3.3), rather than losing the write")
}

console.log("\nThe fit\n")
console.log(`      ${seqctlDesign.partNo} seqctl  ${a.usage.length} macrocells ` +
  `(${10 - a.usage.length} free), ${seqctlDesign.inputs.length} of 14 inputs`)
console.log(failures === 0
  ? "\nThe span writer's control fits, and span-mask is eight bytes because a cell is eight wide"
  : `\n${failures} FAILED`)
if (failures) process.exit(1)
