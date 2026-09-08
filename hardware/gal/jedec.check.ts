/* Assemble both motherboard GALs, then check the FUSES.
 *
 * gal/README.md open item 1 says "nothing has been fitted" and that the pin
 * budget is arithmetic rather than a fitter's report. This is the report, and
 * it is stronger than one: the .jed files are written, read back, and the
 * reconstructed AND array is evaluated against mmu.model.ts and
 * clkdec.model.ts. What is checked is the bit pattern a programmer will burn,
 * not the equations it came from.
 *
 * The one thing it cannot check is jedec/gal22v10.ts itself - if the column
 * map were wrong, the assembler and the simulator would share the error and
 * agree with each other. See the provenance note there.
 *
 *   npm run check:jedec
 */

import { writeFileSync } from "node:fs"
import { join } from "node:path"

import { assemble, fuseChecksum, toJedec, toReport, type Design } from "./jedec/assemble"
import { Gal22v10, parseJedec } from "./jedec/simulate"
import { TOTAL_FUSES } from "./jedec/gal22v10"
import { PHASES, mmu } from "./mmu.model"
import { RESET_STATE, decode, step, type Counter } from "./clkdec.model"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

const here = new URL(".", import.meta.url).pathname

/** Assemble, write the .jed and the report, and read the .jed back. */
const build = (design: Design, base: string) => {
  const a = assemble(design)
  const jed = toJedec(design, a)
  writeFileSync(join(here, `${base}.jed`), jed)
  writeFileSync(join(here, `${base}.doc`), toReport(design, a))

  const parsed = parseJedec(jed)
  check(parsed.declaredFuses === TOTAL_FUSES,
    `${base}: the file declares ${TOTAL_FUSES} fuses - GAL mode, not PAL and not power-down`,
    `*QF${parsed.declaredFuses}`)
  check(parsed.declaredChecksum === fuseChecksum(parsed.fuses),
    `${base}: the fuse checksum matches the fuses it is a checksum of`)
  check(parsed.fuses.every((v, i) => v === a.fuses[i]),
    `${base}: what was written is what is read back`)
  return { design, assembly: a, gal: new Gal22v10(parsed.fuses) }
}

/* ======================================================================== */
console.log("U3 - the MMU sequencer\n")
const u3 = build((await import("./mmu.jedec")).mmuDesign, "mmu")

/* Pins 14-16 carry E, Q and R/W into a part whose macrocells they are. That
 * only works if those macrocells never drive and are combinational - a
 * registered macrocell feeds the array from its register and its pin is not
 * an input at all. It is the mistake this arrangement invites. */
{
  const bad = u3.gal.checkInputPins([14, 15, 16])
  check(bad.length === 0, "E, Q and R/W reach the array as inputs on macrocell pins", bad.join("; "))
}
check(u3.gal.undriven(23), "pin 23 is left at high-Z, so it is a spare INPUT and not a driven low")

/* The exhaustive part: the whole 16-bit address space x 4 quadrature phases
 * x R/W, read off the fuse map and compared with the model mmu.check.ts makes
 * its claims about. 524,288 evaluations. */
{
  let mismatch: string | null = null
  outer:
  for (let la = 0; la <= 0xffff && !mismatch; la++) {
    for (const ph of PHASES) {
      for (const rw of [0, 1] as const) {
        const driven: Record<number, 0 | 1> = {
          1: ((la >> 15) & 1) as 0 | 1, 2: ((la >> 14) & 1) as 0 | 1,
          3: ((la >> 13) & 1) as 0 | 1, 4: ((la >> 12) & 1) as 0 | 1,
          5: ((la >> 11) & 1) as 0 | 1, 6: ((la >> 10) & 1) as 0 | 1,
          7: ((la >> 9) & 1) as 0 | 1, 8: ((la >> 8) & 1) as 0 | 1,
          9: ((la >> 7) & 1) as 0 | 1, 10: ((la >> 6) & 1) as 0 | 1,
          11: ((la >> 5) & 1) as 0 | 1, 13: ((la >> 4) & 1) as 0 | 1,
          14: ph.e as 0 | 1, 15: ph.q as 0 | 1, 16: rw,
        }
        const pins = u3.gal.evaluate(driven)
        const m = mmu(la, ph.e, ph.q, rw)
        /* The model reports signals as asserted; these pins are declared
         * active low, so the pin is the complement. MUXSEL and CTRLCP are
         * already pin levels in the model. */
        const want: Record<number, number> = {
          17: m.iopage ? 0 : 1,
          18: m.muxsel ? 1 : 0,
          19: m.isooe ? 0 : 1,
          20: m.mapwe ? 0 : 1,
          21: m.mapoe ? 0 : 1,
          22: m.ctrlcp ? 1 : 0,
        }
        for (const [pin, v] of Object.entries(want)) {
          if (pins[Number(pin)] !== v) {
            mismatch = `pin ${pin} = ${pins[Number(pin)]}, expected ${v} at ` +
              `$${la.toString(16).toUpperCase().padStart(4, "0")} ${ph.name} R/W=${rw}`
            break outer
          }
        }
      }
    }
  }
  check(mismatch === null,
    "the fuse map matches mmu.model.ts over all 65,536 addresses x 4 phases x R/W",
    mismatch ?? "")
}

/* ======================================================================== */
console.log("\nU6 - the divider and the RAM decode\n")
const u6 = build((await import("./clkdec.jedec")).clkdecDesign, "clkdec")

check(u6.gal.polarityAssumptionMatters().length === 0,
  "no registered macrocell that is read back is active low, so the feedback " +
  "polarity assumption in simulate.ts carries no weight",
  u6.gal.polarityAssumptionMatters().join(", "))

/* The divider, against the behavioural counter. This is the check that the
 * hand expansion of C1's XOR, C2's suppression term and E and Q's decodes is
 * the same function - the step gal/README.md counts product terms for and
 * nothing has ever executed. */
const CNT_PINS = { 16: 0, 17: 1, 20: 2, 21: 3 } as const
const readCounter = (pins: Int8Array): Counter => {
  let cnt = 0
  for (const [pin, bit] of Object.entries(CNT_PINS)) cnt |= pins[Number(pin)] << bit
  return { cnt, e: pins[18] as 0 | 1, q: pins[19] as 0 | 1 }
}

for (const fastE of [false, true]) {
  const label = fastE ? "/8 (fast-E)" : "/12"
  const base = { 2: (fastE ? 1 : 0) as 0 | 1, 3: 1 as const, 4: 1 as const,
                 5: 0 as const, 6: 0 as const, 7: 0 as const, 8: 1 as const,
                 9: 0 as const, 10: 0 as const }

  /* Reset is asserted by pulling pin 3 LOW, and it is a level: it holds. */
  u6.gal.evaluate({ ...base, 3: 0 })
  check(readCounter(u6.gal.evaluate({ ...base, 3: 0 })).cnt === 0,
    `${label}: /RESET low holds the counter at zero`)
  u6.gal.clock({ ...base, 3: 0 })
  const held = readCounter(u6.gal.evaluate({ ...base, 3: 0 }))
  check(held.cnt === 0 && held.e === 0 && held.q === 0,
    `${label}: a clock edge while /RESET is low changes nothing`)

  let model: Counter = { ...RESET_STATE }
  let bad: string | null = null
  let sawE0 = false, sawE1 = false
  const period = fastE ? 8 : 12
  for (let i = 0; i < period * 8 && !bad; i++) {
    u6.gal.clock(base)
    model = step(model, fastE)
    const got = readCounter(u6.gal.evaluate(base))
    if (got.cnt !== model.cnt || got.e !== model.e || got.q !== model.q) {
      bad = `edge ${i}: fuses gave cnt=${got.cnt} e=${got.e} q=${got.q}, ` +
        `model says cnt=${model.cnt} e=${model.e} q=${model.q}`
      break
    }
    if (got.e) sawE1 = true; else sawE0 = true

    /* Every combination of the five decode inputs, at this phase. A20 (pin 9)
     * joined them on 2026-09-08 with the 2 MB map. */
    for (let bits = 0; bits < 32 && !bad; bits++) {
      const d = { ...base,
        4: ((bits >> 4) & 1) as 0 | 1, 5: ((bits >> 3) & 1) as 0 | 1,
        6: ((bits >> 2) & 1) as 0 | 1, 7: ((bits >> 1) & 1) as 0 | 1,
        9: (bits & 1) as 0 | 1, 10: 0 as const }
      for (const rw of [0, 1] as const) {
        const pins = u6.gal.evaluate({ ...d, 8: rw })
        const want = decode({ nIopage: d[4], la7: d[5], la6: d[6], a19: d[7], a20: d[9], rw, e: got.e })
        const got4 = { nIosel: pins[15], nRamCe: pins[22], nRamOe: pins[14], nRamWe: pins[23] }
        for (const k of ["nIosel", "nRamCe", "nRamOe", "nRamWe"] as const) {
          if (got4[k] !== want[k]) {
            bad = `${k} = ${got4[k]}, expected ${want[k]} with ` +
              `/IOPAGE=${d[4]} LA7=${d[5]} LA6=${d[6]} A19=${d[7]} A20=${d[9]} R/W=${rw} E=${got.e}`
          }
        }
      }
    }
  }
  check(bad === null, `${label}: the fuse map matches clkdec.model.ts for ${period * 8} edges ` +
    `and all 64 decode inputs at each`, bad ?? "")
  check(sawE0 && sawE1, `${label}: the decode sweep covered E low and E high`)
}

/* ======================================================================== */
console.log("\nThe fitting, which is the thing that had never been done\n")
for (const { design, assembly } of [u3, u6]) {
  for (const u of [...assembly.usage].sort((a, b) => a.pin - b.pin)) {
    console.log(`      ${design.partNo} pin ${String(u.pin).padStart(2)}  ` +
      `${u.name.padEnd(7)} ${String(u.used).padStart(2)}/${String(u.available).padEnd(2)} terms`)
  }
  const worst = assembly.usage.reduce((a, b) =>
    b.used / b.available > a.used / a.available ? b : a)
  check(true, `${design.partNo} fits: ${assembly.usage.length} macrocells, ` +
    `tightest is ${worst.name} at ${worst.used} of ${worst.available}`)
}

console.log(failures === 0
  ? "\nBoth GALs assemble, fit, and their fuse maps match the models"
  : `\n${failures} FAILED`)
if (failures) process.exit(1)
