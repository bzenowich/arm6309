/* What would the fitter's three tricks be worth on our GALs?
 *
 * Reports, per equation: the terms we emit, the minimum for that function, and
 * the minimum for its complement. On a 22V10 the S1 bit is an XOR on the way
 * out, so the array may hold whichever of the two is smaller at no cost - a
 * choice our assembler never makes because `assertedLow` is a specification of
 * the pin's sense, not an optimisation.
 */

import { bothPolarities, type Cube } from "./jedec/twolevel"
import { literalsOf } from "./jedec/minimise"
import { OLMC } from "./jedec/gal22v10"
import { ALL } from "./designs"

const LIMIT = 11   // 2^11 minterms; past this Quine-McCluskey stops being instant

let ourTotal = 0, bestTotal = 0
const flips: string[] = []
const relieved: string[] = []
const skipped: string[] = []

for (const d of ALL) {
  for (const c of d.cells) {
    const vars: string[] = []
    const cubes: Cube[] = c.terms.map((t) => {
      let ones = 0, mask = 0
      for (const lit of literalsOf(t)) {
        const neg = lit.startsWith("!")
        const name = neg ? lit.slice(1) : lit
        let i = vars.indexOf(name)
        if (i < 0) { i = vars.length; vars.push(name) }
        mask |= 1 << i
        if (!neg) ones |= 1 << i
      }
      return { ones, mask }
    })
    if (vars.length > LIMIT) { skipped.push(`${d.name}.${c.name} (${vars.length} vars)`); continue }
    const { f, notF } = bothPolarities(cubes, vars.length)
    const ours = c.terms.length
    const best = Math.min(f, notF)
    ourTotal += ours; bestTotal += best
    const cap = OLMC[c.pin]?.terms ?? 99
    if (notF < ours) {
      flips.push(`${d.name}\t${c.name}\t${ours} -> ${notF}\t(f ${f}, cap ${cap})`)
      if (ours > cap && notF <= cap) relieved.push(`${d.name}.${c.name}`)
    }
  }
}

console.log("equations where the complement is cheaper than what we emit:")
for (const l of flips) console.log("  " + l)
console.log(`\nproduct terms, ours -> best polarity: ${ourTotal} -> ${bestTotal} ` +
  `(${ourTotal - bestTotal} fewer, ${(100 * (ourTotal - bestTotal) / ourTotal).toFixed(1)}%)`)
console.log(`equations improved: ${flips.length}`)
if (relieved.length) console.log(`equations that would newly fit their macrocell: ${relieved.join(", ")}`)
if (skipped.length) console.log(`skipped (support > ${LIMIT}): ${skipped.join(", ")}`)
