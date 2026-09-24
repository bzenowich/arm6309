/* Ask CUPL what our equations cost after real minimisation.
 *
 * Our flow does subsumption and nothing else (jedec/minimise.ts says so on
 * purpose). The ATF1508 fitter does Espresso, output-polarity selection and
 * foldback. This writes every GAL design out as CUPL source so the difference
 * can be measured rather than argued about.
 */

import { writeFileSync, mkdirSync } from "node:fs"
import { toGalPld } from "./jedec/galpld"
import { ALL } from "./designs"
const dir = process.argv[2] ?? "probe"   // gitignored: probe output, not a build artefact
mkdirSync(dir, { recursive: true })
for (const d of ALL) {
  writeFileSync(`${dir}/${d.name}.pld`, toGalPld(d))
  writeFileSync(`${dir}/${d.name}_n.pld`, toGalPld(d, true))
  const widest = Math.max(...d.cells.map((c) => c.terms.length))
  console.log(`${d.name}\t${d.cells.length} cells\t${d.inputs.length} inputs\twidest ${widest} terms`)
}
