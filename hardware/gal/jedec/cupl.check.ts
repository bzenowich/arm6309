/* The falsification test: run Atmel's own JEDEC through our fuse map.
 *
 * jedec/README.md named this as "the third way, which is the one that would
 * settle it, has not been done" - compile a .pld with the vendor's CUPL and
 * check its output against ours. On 2026-09-07 it was done, and it found two
 * errors that 178 passing checks could not, because in both cases the
 * assembler and the fuse-map simulator shared the mistake and agreed with each
 * other perfectly:
 *
 *   1. THE S0/S1 CONFIG BITS RUN FROM PIN 23 DOWNWARD, not from pin 14 up.
 *      Our polarity bits were on the wrong macrocells. Symmetric pins hid it -
 *      only 18 and 19 disagreed visibly, because the rest happened to match.
 *
 *   2. A REGISTERED MACROCELL FEEDS THE ARRAY FROM /Q, not from its pin.
 *      CUPL emits `C0.d = !C0` as the single literal C0. That is only a
 *      working counter if the feedback is inverted. Ours was written the other
 *      way and counted correctly only in our own simulator.
 *
 * The reference files here are CUPL 5.0a's output for our own mmu.pld and
 * clkdec.pld, committed so this runs without Wine. To regenerate them, see
 * ../prjbureau/README.md.
 *
 *   npm run check:cupl
 */

import { readFileSync } from "node:fs"
import { join } from "node:path"

import { Gal22v10, parseJedec } from "./simulate"
import { OLMC } from "./gal22v10"
import { PHASES, mmu } from "../mmu.model"
import { RESET_STATE, decode, step, type Counter } from "../clkdec.model"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}
const here = new URL(".", import.meta.url).pathname
const load = (f: string) =>
  new Gal22v10(parseJedec(readFileSync(join(here, f), "latin1")).fuses)

/* -- U3, combinational: the whole address space against the model --------- */
const checkMmu = (label: string, gal: Gal22v10) => {
  let bad: string | null = null
  outer:
  for (let la = 0; la <= 0xffff; la++) {
    for (const ph of PHASES) for (const rw of [0, 1] as const) {
      const d: Record<number, 0 | 1> = {
        1: ((la >> 15) & 1) as 0 | 1, 2: ((la >> 14) & 1) as 0 | 1,
        3: ((la >> 13) & 1) as 0 | 1, 4: ((la >> 12) & 1) as 0 | 1,
        5: ((la >> 11) & 1) as 0 | 1, 6: ((la >> 10) & 1) as 0 | 1,
        7: ((la >> 9) & 1) as 0 | 1, 8: ((la >> 8) & 1) as 0 | 1,
        9: ((la >> 7) & 1) as 0 | 1, 10: ((la >> 6) & 1) as 0 | 1,
        11: ((la >> 5) & 1) as 0 | 1, 13: ((la >> 4) & 1) as 0 | 1,
        14: ph.e as 0 | 1, 15: ph.q as 0 | 1, 16: rw,
      }
      const p = gal.evaluate(d), m = mmu(la, ph.e, ph.q, rw)
      const want: Record<number, number> = {
        17: m.iopage ? 0 : 1, 18: m.muxsel ? 1 : 0, 19: m.isooe ? 0 : 1,
        20: m.mapwe ? 0 : 1, 21: m.mapoe ? 0 : 1, 22: m.ctrlcp ? 1 : 0,
      }
      for (const [pin, v] of Object.entries(want)) {
        if (p[Number(pin)] !== v) {
          bad = `pin ${pin} at $${la.toString(16).toUpperCase()} ${ph.name} R/W=${rw}`
          break outer
        }
      }
    }
  }
  check(bad === null, `${label}: matches mmu.model.ts over all 524,288 inputs`, bad ?? "")
}

/* -- U6, registered: the divider and the decodes -------------------------- */
const CNT = { 16: 0, 17: 1, 20: 2, 21: 3 } as const
const checkClkdec = (label: string, gal: Gal22v10) => {
  for (const fastE of [false, true]) {
    const base = { 2: (fastE ? 1 : 0) as 0 | 1, 3: 1 as const, 4: 1 as const,
                   5: 0 as const, 6: 0 as const, 7: 0 as const, 8: 1 as const }
    gal.evaluate({ ...base, 3: 0 }); gal.reset()
    let model: Counter = { ...RESET_STATE }, bad: string | null = null
    const edges = fastE ? 64 : 96
    for (let i = 0; i < edges && !bad; i++) {
      gal.clock(base); model = step(model, fastE)
      const p = gal.evaluate(base)
      const cnt = Object.entries(CNT).reduce((n, [pin, b]) => n | (p[Number(pin)] << b), 0)
      if (cnt !== model.cnt || p[18] !== model.e || p[19] !== model.q) {
        bad = `edge ${i}: fuses cnt=${cnt} e=${p[18]} q=${p[19]}, ` +
          `model cnt=${model.cnt} e=${model.e} q=${model.q}`
        break
      }
      const want = decode({ nIopage: 1, la7: 0, la6: 0, a19: 0, rw: 1, e: model.e })
      if (p[15] !== want.nIosel || p[22] !== want.nRamCe ||
          p[14] !== want.nRamOe || p[23] !== want.nRamWe) bad = `decode differs at edge ${i}`
    }
    check(bad === null, `${label}: ${fastE ? "/8 " : "/12"} matches clkdec.model.ts for ${edges} edges`,
      bad ?? "")
  }
}

console.log("Atmel CUPL 5.0a's own output, executed on our fuse map\n")
const cuplMmu = load("reference/mmu.cupl.jed")
const cuplClk = load("reference/clkdec.cupl.jed")
checkMmu("CUPL mmu.jed", cuplMmu)
checkClkdec("CUPL clkdec.jed", cuplClk)

console.log("\nAnd ours, which must agree with it\n")
checkMmu("our mmu.jed", load("../mmu.jed"))
checkClkdec("our clkdec.jed", load("../clkdec.jed"))

/* -- the two conventions the reference files pin down --------------------- */
console.log("\nWhat the reference files establish\n")
check(cuplClk.registered(16) && cuplClk.registered(21) && !cuplClk.registered(15),
  "S1 is read correctly: CUPL registers C0..C3, E and Q and nothing else")
check([17, 20, 22].every((p) => !cuplMmu.polarityHigh(p)),
  "S0 is read correctly: CUPL's active-low outputs carry S0 = 0 " +
  "(only true under the pin-23-downward config order)")

console.log(failures === 0
  ? "\nOur fuse map and Atmel's agree - the provenance note in gal22v10.ts is settled"
  : `\n${failures} FAILED`)
if (failures) process.exit(1)
