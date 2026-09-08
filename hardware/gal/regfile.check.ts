/* rfa, the register-file address GAL - graphics.md 10.1.6.3's relief.
 *   npm run check:regfile
 *
 * Two independent statements are checked here, and neither is "the fuses match
 * the equations" - jedec/cupl.check.ts does that against Atmel's own compiler.
 * These are the SPECIFICATION claims, which a second compiler cannot settle:
 *
 *   1. During a CPU access to $FF60-$FF7F, RA[4:0] is A[4:0] - the register
 *      the CPU named, and no other. (graphics.md 13)
 *   2. Otherwise RA[4:0] is the read-back source the fetch phase asks for,
 *      and WSTB never fires. (graphics.md 7.2, 13)
 */

import { writeFileSync } from "node:fs"
import { join } from "node:path"
import { assemble, fuseChecksum, toJedec, toReport } from "./jedec/assemble"
import { Gal22v10, parseJedec } from "./jedec/simulate"
import { rfaDesign } from "./regfile.jedec"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

const here = new URL(".", import.meta.url).pathname
const a = assemble(rfaDesign)
const jed = toJedec(rfaDesign, a)
writeFileSync(join(here, "rfa.jed"), jed)
writeFileSync(join(here, "rfa.doc"), toReport(rfaDesign, a))
const parsed = parseJedec(jed)
check(parsed.declaredChecksum === fuseChecksum(parsed.fuses),
  "rfa: fuse checksum, and the file reads back as written")
const gal = new Gal22v10(parsed.fuses)

const P = Object.fromEntries(a.usage.map((u) => [u.name, u.pin]))
const IN = Object.fromEntries(rfaDesign.inputs.map((i) => [i.name, i.pin]))

/** Drive every input by name; anything unnamed is 0. */
const run = (set: Record<string, 0 | 1>) => {
  const pins: Record<number, 0 | 1> = {}
  for (const i of rfaDesign.inputs) pins[i.pin] = set[i.name] ?? 0
  const out = gal.evaluate(pins)
  return {
    ra: [0, 1, 2, 3, 4].reduce((v, n) => v | (out[P[`RA${n}`]] << n), 0),
    wstb: out[P.WSTB],
  }
}
/** A CPU access to register `reg` of the 32-byte window. */
const cpu = (reg: number, rw: 0 | 1, e: 0 | 1 = 1) => run({
  IOSEL: 1, A6: 1, A5: 1, RW: rw, E: e,
  A0: (reg & 1) as 0 | 1, A1: ((reg >> 1) & 1) as 0 | 1, A2: ((reg >> 2) & 1) as 0 | 1,
  A3: ((reg >> 3) & 1) as 0 | 1, A4: ((reg >> 4) & 1) as 0 | 1,
})

/* -- 1. the CPU names the register ---------------------------------------- */
{
  let bad: string | null = null
  for (let reg = 0; reg < 32 && !bad; reg++) {
    for (const rw of [0, 1] as const) {
      const r = cpu(reg, rw)
      if (r.ra !== reg) bad = `+$${reg.toString(16)} ${rw ? "read" : "write"} -> RA=${r.ra}`
    }
  }
  check(bad === null, "all 32 registers: RA[4:0] follows A[4:0] on read and write", bad ?? "")
}

/* -- 2. WSTB is a write, in the second half of E, inside the window -------- */
{
  const w = cpu(7, 0, 1)
  check(w.wstb === 1, "WSTB fires on a write to the window while E is high")
  check(cpu(7, 1, 1).wstb === 0, "WSTB does not fire on a READ - it would clobber the register")
  check(cpu(7, 0, 0).wstb === 0,
    "WSTB does not fire before E - a 6809 write is only valid data in E's second half")
  for (const off of [{ IOSEL: 0 as const }, { A6: 0 as const }, { A5: 0 as const }]) {
    const [name] = Object.keys(off)
    const r = run({ IOSEL: 1, A6: 1, A5: 1, RW: 0, E: 1, A0: 1, A1: 1, A2: 1, ...off })
    check(r.wstb === 0, `WSTB does not fire with ${name} deasserted - REGSEL is all three`)
  }
}

/* -- 3. outside the window, the fetch phase owns the address -------------- */
{
  /* graphics.md 13: the span writer reads its length, foreground and
   * background out of the register file in fetch phases 0, 1 and 2. The
   * addresses are the register numbers those three live at. */
  const SPANLEN = 0x05, WFG = 0x06, WBG = 0x07
  const idle = (fp: number) => run({ SPANBUSY: 0, FP0: (fp & 1) as 0 | 1, FP1: ((fp >> 1) & 1) as 0 | 1 })
  check(idle(0).ra === SPANLEN, "fetch phase 0 addresses SPANLEN", `${idle(0).ra}`)
  check(idle(1).ra === WFG, "fetch phase 1 addresses WFG", `${idle(1).ra}`)
  check(idle(2).ra === WBG, "fetch phase 2 addresses WBG", `${idle(2).ra}`)
  check([0, 1, 2].every((fp) => idle(fp).wstb === 0),
    "read-back never asserts WSTB - the register file is only written by the CPU")

  /* SPANBUSY gates the read-back: while a span is retiring the register file
   * is not being re-read, so the address parks rather than cycling. */
  const busy = [0, 1, 2].map((fp) =>
    run({ SPANBUSY: 1, FP0: (fp & 1) as 0 | 1, FP1: ((fp >> 1) & 1) as 0 | 1 }).ra)
  check(busy.every((v) => v === 0), "SPANBUSY parks the read-back address", busy.join(","))
}

/* -- 4. the CPU wins the address while it is accessing the window --------- */
{
  /* Both can be true at once - a CPU register access during an idle fetch
   * phase - and the CPU's A[4:0] has to win, or the access reads the wrong
   * register. The equations are OR-of-products with !REGSEL on every
   * read-back term, so this is a real claim about that gating. */
  let bad: string | null = null
  for (let reg = 0; reg < 32 && !bad; reg++) {
    for (let fp = 0; fp < 3; fp++) {
      const r = run({
        IOSEL: 1, A6: 1, A5: 1, RW: 1, E: 1, SPANBUSY: 0,
        FP0: (fp & 1) as 0 | 1, FP1: ((fp >> 1) & 1) as 0 | 1,
        A0: (reg & 1) as 0 | 1, A1: ((reg >> 1) & 1) as 0 | 1, A2: ((reg >> 2) & 1) as 0 | 1,
        A3: ((reg >> 3) & 1) as 0 | 1, A4: ((reg >> 4) & 1) as 0 | 1,
      })
      if (r.ra !== reg) bad = `+$${reg.toString(16)} during fetch phase ${fp} -> RA=${r.ra}`
    }
  }
  check(bad === null, "a CPU access beats the read-back in every fetch phase", bad ?? "")
}

/* Twelve dedicated inputs (1-11, 13) plus pin 23's macrocell used as an input,
 * which is legal and is where FP1 lands. */
console.log(`\nrfa: ${a.usage.length} macrocells of 10, ` +
  `${rfaDesign.inputs.length} inputs on 12 dedicated pins + pin 23`)
if (failures) { console.error(`\n${failures} FAILED`); process.exit(1) }
console.log("rfa OK")
