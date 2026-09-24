/* v3lane - video3's byte lanes and the internal bus's drivers, a GAL22V10.
 *   bun run video3/logic/v3lane.check.ts        (part of `npm run check`)
 *
 * Eleven inputs, so the sweep is exhaustive: all 2,048 of them, the fuse map
 * against a model written here from the board's rules rather than from the
 * term lists, and then the same sweep against Atmel's CUPL compiling the
 * .pld this writes (cupl/v3lane.cupl.jed) - CLAUDE.md: a GAL does
 * not ship without a CUPL reference. */

import { existsSync, readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { assemble, fuseChecksum, toJedec, toReport } from "../../tools/gal/jedec/assemble"
import { toGalPld } from "../../tools/gal/jedec/galpld"
import { Gal22v10, parseJedec } from "../../tools/gal/jedec/simulate"
import { v3laneDesign as D } from "./v3lane.jedec"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

const here = new URL(".", import.meta.url).pathname
const a = assemble(D)
const jed = toJedec(D, a)
writeFileSync(join(here, "v3lane.jed"), jed)
writeFileSync(join(here, "v3lane.doc"), toReport(D, a))
writeFileSync(join(here, "v3lane.pld"), toGalPld(D))
const p = parseJedec(jed)
check(p.declaredChecksum === fuseChecksum(p.fuses), "v3lane: fuse checksum, and the file reads back as written")
check([...toGalPld(D)].every((c) => c.charCodeAt(0) < 128), "v3lane.pld is 7-bit ASCII - CUPL's lexer is an MS-DOS program")
const gal = new Gal22v10(p.fuses)

type In = Record<string, 0 | 1>
const NAMES = D.inputs.map((i) => i.name)
const inputsOf = (bits: number): In =>
  Object.fromEntries(NAMES.map((n, i) => [n, ((bits >> i) & 1) as 0 | 1]))
/* inputs in asserted sense too: an active-low input's pin is the complement */
const pinsOf = (v: In): Record<number, 0 | 1> =>
  Object.fromEntries(D.inputs.map((i) => [i.pin, (i.activeLow ? 1 - v[i.name] : v[i.name]) as 0 | 1]))
/* each output in ASSERTED sense: every pin here is an active-low enable */
const outs = (g: Gal22v10, v: In) => {
  const pins = g.evaluate(pinsOf(v))
  return Object.fromEntries(D.cells.map((c) =>
    [c.name, c.assertedLow ? 1 - pins[c.pin] : pins[c.pin]])) as Record<string, number>
}

/* ---- the model: the board's rules, not the term lists -------------------- */
const model = (v: In) => {
  const lane = v.LANE1 * 2 + v.LANE0
  const byteAcc = v.GRD | v.GCPY | v.GSPN
  const direct = !v.WM1 && !v.WM0
  const pw = (v.GSPN && direct) || (v.GCPY && !v.CRDSEL) ? 1 : 0
  const laneRead = v.GRD || (v.GCPY && v.CRDSEL) ? 1 : 0
  const m: Record<string, number> = {
    PWOE: pw,
    /* the file has IDB unless a lane read, the '574 or a posted write does.
     * ⭐ A copy's write access keeps it off for both dots, not only the tick */
    RFOE: laneRead || pw || v.GCPY || v.WSTBV ? 0 : 1,
  }
  /* ⭐ a keyed copy write enables no byte at all, so nothing is written */
  const keySkip = v.KEY && v.WM1 && v.WM0 && v.GCPY
  for (let l = 0; l < 4; l++) {
    m[`LOE${l}`] = byteAcc && lane === l ? 1 : 0
    m[["LB0", "UB0", "LB1", "UB1"][l]] = (!v.VWE || lane === l) && !keySkip ? 1 : 0
  }
  return m
}

let bad: string | null = null
for (let bits = 0; bits < 1 << NAMES.length && !bad; bits++) {
  const v = inputsOf(bits), g = outs(gal, v), m = model(v)
  for (const k of Object.keys(m)) if (g[k] !== m[k]) {
    bad = `${k} at ${JSON.stringify(v)}: fuse map ${g[k]}, model ${m[k]}`; break
  }
}
check(bad === null, "the fuse map is the model over all 2,048 inputs - lane, byte enables, IDB's drivers", bad ?? "")

/* ---- the claims the board rests on, over the inputs the arbiter can give -- *
 * v3dot's grants are one-hot or none (one spare access, one requester), and
 * none of them coincides with a posted CPU write: WSTBV is qualified by
 * !SPANBUSY & !CBUSY (so no span or copy grant), and v3host's RDREQ is off
 * through E-high of every card access but a VDATA read (so no prefetch).
 * v3card_tb counts IDB's drivers every dot to hold the parts to that. */
const legal = (v: In) => v.GRD + v.GCPY + v.GSPN <= 1 && !(v.WSTBV && (v.GRD || v.GCPY || v.GSPN))
let twoLanes = 0, noLane = 0, fight = 0, float = 0, writeTwo = 0
for (let bits = 0; bits < 1 << NAMES.length; bits++) {
  const v = inputsOf(bits)
  if (!legal(v)) continue
  const g = outs(gal, v)
  const lanes = [0, 1, 2, 3].filter((l) => g[`LOE${l}`]).length
  const byteAcc = v.GRD | v.GCPY | v.GSPN
  if (lanes > 1) twoLanes++
  if (byteAcc && lanes !== 1) noLane++
  if (!byteAcc && lanes) noLane++
  /* IDB's drivers: the file, the '574, a lane '245 in its READ direction
   * (v3host's DIR: the prefetch and the copy's read), and the host '245 on a
   * posted write. WSTB is not here: the file's /WE turns its outputs off. */
  const laneRead = v.GRD || (v.GCPY && v.CRDSEL) ? 1 : 0
  const drivers = g.RFOE + g.PWOE + (lanes && laneRead ? 1 : 0) + v.WSTBV
  if (drivers > 1) fight++
  /* a WRITE access must have a source: the file or the '574 */
  if ((v.GSPN || (v.GCPY && !v.CRDSEL)) && !v.WSTBV && g.RFOE + g.PWOE !== 1) float++
  const bes = ["LB0", "UB0", "LB1", "UB1"].filter((n) => g[n]).length
  const keyed = v.KEY && v.WM1 && v.WM0 && v.GCPY
  if (v.VWE && bes !== (keyed ? 0 : 1)) writeTwo++
}
check(twoLanes === 0 && noLane === 0,
  "exactly one lane transceiver is on for each byte access, and none otherwise",
  `${twoLanes} with two, ${noLane} with the wrong count`)
check(fight === 0, "never two drivers on IDB - the file, the '574, a reading lane, a posted CPU write",
  `${fight} input combinations`)
check(float === 0, "and every write access has exactly one source for its byte - the file or the '574",
  `${float} input combinations`)
check(writeTwo === 0, "a write enables exactly one byte of the four - and a keyed copy's write none", `${writeTwo} input combinations`)

/* ---- the second implementation ------------------------------------------ */
const ref = join(here, "cupl", "v3lane.cupl.jed")
if (!existsSync(ref)) {
  check(false, "CUPL's v3lane.cupl.jed exists", "run tools/gal/prjbureau/cupl-reference.sh video3/logic/v3lane.pld")
} else {
  const cupl = new Gal22v10(parseJedec(readFileSync(ref, "latin1")).fuses)
  let diff: string | null = null
  for (let bits = 0; bits < 1 << NAMES.length && !diff; bits++) {
    const v = inputsOf(bits), ours = gal.evaluate(pinsOf(v)), theirs = cupl.evaluate(pinsOf(v))
    for (const c of D.cells) if (ours[c.pin] !== theirs[c.pin]) {
      diff = `${c.name} at ${bits.toString(2).padStart(11, "0")}: ours ${ours[c.pin]}, CUPL ${theirs[c.pin]}`
      break
    }
  }
  check(diff === null, "CUPL v3lane.jed: matches our fuse map over all 2,048 inputs", diff ?? "")
}

console.log(`      ${D.partNo} ${D.name}  ${a.usage.filter((u) => u.pin >= 14).length} macrocells of 10, ` +
            `${D.inputs.length} inputs`)
console.log(`\n${failures === 0 ? "0 failed" : `${failures} FAILED`}`)
process.exit(failures === 0 ? 0 : 1)
