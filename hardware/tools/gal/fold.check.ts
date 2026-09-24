/* The constant fold, checked - jedec/cupl.ts's foldConstants.
 *
 * ⛔ WHY THIS EXISTS. merge() rewrites equations now: `rename` can substitute a
 * constant-0 cell into a term, and the fold deletes what that makes impossible.
 * That is a transformation applied to EVERY merged part, and until 2026-09-12
 * nothing checked it.
 *
 * ⚠ AND THE TESTBENCHES CANNOT. verilog/emit.ts generates from the SAME folded
 * term lists the fitter compiles, so a wrong fold makes the model and the
 * silicon wrong together and agreeing - the benches would pass. cupl.check.ts
 * does not close it either: it cross-checks the standalone GAL22V10 designs
 * against Atmel's compiler and never sees a merged part.
 *
 * So this compares the equations directly, which shares nothing with either
 * path: rebuild the arbiter's cells WITHOUT folding and evaluate both forms
 * over every input combination.
 */

import { arbDesign } from "../../archive/video/logic/access.jedec"
import { rename } from "./jedec/cupl"
import { vaddrCpld, vctrlCpld } from "../../archive/video/logic/video.cpld"
import { vsupCpld } from "../../archive/video/logic/vsup.cpld"
import { audioCpld } from "../../audio/logic/audio.cpld"
import { aseqCpld } from "../../audio/logic/aseq.cpld"
import type { Cell } from "./jedec/assemble"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (ok) console.log(`ok    ${claim}`)
  else { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
}

const lits = (t: string) => t.split("&").map((s) => s.trim()).filter(Boolean)
const bare = (l: string) => l.replace(/^!/, "")

const PARTS: [string, { cells: Cell[] }][] = [
  ["vaddr", vaddrCpld as any], ["vctrl", vctrlCpld as any], ["vsup", vsupCpld as any],
  ["audio", audioCpld as any], ["aseq", aseqCpld as any],
]

/* -- 1. the fold is COMPLETE: no shipped equation still reads a constant --- */
console.log("\nThe fold leaves no constant behind\n")
for (const [name, part] of PARTS) {
  const zero = new Set(part.cells.filter((c) => c.terms.length === 0 && !c.oe).map((c) => c.name))
  const leaks: string[] = []
  for (const c of part.cells) {
    if (zero.has(c.name)) continue
    for (const t of [...c.terms, c.oe ?? ""]) {
      for (const l of lits(t)) if (zero.has(bare(l))) leaks.push(`${c.name} reads ${l}`)
    }
  }
  check(leaks.length === 0,
    `${name}: no equation reads a constant-0 cell - the fold ran and ran to completion`,
    leaks.slice(0, 4).join("; "))
}

/* -- 2. nothing survives that is false by inspection ---------------------- */
console.log("\nAnd nothing shipped is impossible\n")
for (const [name, part] of PARTS) {
  const dead: string[] = []
  for (const c of part.cells) {
    for (const t of c.terms) {
      const s = new Set(lits(t))
      if ([...s].some((l) => s.has(l.startsWith("!") ? bare(l) : `!${l}`))) dead.push(`${c.name}: ${t}`)
    }
    if (c.terms.length === 0 && !c.oe && c.name !== "CPUIDLE") dead.push(`${c.name}: no terms, no oe`)
  }
  check(dead.length === 0,
    `${name}: no term contains X & !X - vctrl.pld carried ACPU0 = VPORT & !CPUIDLE & CPUIDLE & ... until 2026-09-12`,
    dead.slice(0, 4).join("; "))
}

/* -- 3. ⭐ the arbiter, pre-fold against shipped, exhaustively ------------- *
 *
 * ARB_MAP is video.cpld.ts's, restated: if the two drift apart this claim
 * stops meaning anything, which is why it names every entry rather than
 * importing a spread. */
console.log("\nThe arbiter's folded equations against its unfolded ones\n")
{
  const ARB_MAP: Record<string, string> = {
    CPUA0: "CPUIDLE", CPUA1: "CPUIDLE",
    GCPU0: "ACPU0", GCPU1: "ACPU1", GCPU2: "ACPU2", GCPU3: "ACPU3",
    SPNREQ: "SPNREQG", SPANBUSY: "WAITSRC", RW: "CPUIDLE",
    VRAMSEL: "VPORT", IOPAGE: "CPUIDLE",
  }
  const before = rename(arbDesign, ARB_MAP).cells
  const after = new Map((vctrlCpld.cells as Cell[]).map((c) => [c.name, c]))
  const varsOf = (ts: string[]) => new Set(ts.flatMap(lits).map(bare))
  const sop = (terms: string[], env: Record<string, number>) =>
    terms.some((t) => lits(t).every((l) =>
      l.startsWith("!") ? env[bare(l)] === 0 : env[l] === 1)) ? 1 : 0

  const differ: string[] = []
  let dropped = 0
  for (const b of before) {
    const a = after.get(b.name)
    if (!a) dropped++
    const vars = [...new Set([...varsOf(b.terms), ...varsOf(a?.terms ?? []),
      ...varsOf(b.oe ? [b.oe] : []), ...varsOf(a?.oe ? [a.oe] : [])])].filter((v) => v !== "CPUIDLE")
    /* ⚠ Bounded, because an unbounded sweep on a widened arbiter would hang
     * rather than fail - CLAUDE.md's "a hang is worse than a failure". */
    if (vars.length > 16) { differ.push(`${b.name}: ${vars.length} variables, too wide to sweep`); continue }
    for (let m = 0; m < (1 << vars.length); m++) {
      const env: Record<string, number> = { CPUIDLE: 0 }
      vars.forEach((v, i) => { env[v] = (m >> i) & 1 })
      if (sop(b.terms, env) !== sop(a?.terms ?? [], env)) { differ.push(`${b.name} terms`); break }
      if (b.oe && sop([b.oe], env) !== (a?.oe ? sop([a.oe], env) : 0)) { differ.push(`${b.name}.oe`); break }
    }
  }
  check(differ.length === 0,
    "⭐ every arbiter cell computes the same function folded as unfolded, over EVERY input " +
    "combination with CPUIDLE = 0 - the fold is bookkeeping and not a change of design",
    differ.slice(0, 4).join("; "))
  check(dropped === 4,
    "and exactly four cells were dropped - ACPU0-3, the CPU grants graphics.md 11 retired",
    `${dropped}`)
}

console.log(failures === 0 ? "\nfold: 0 failed" : `\nfold: ${failures} failed`)
process.exit(failures === 0 ? 0 : 1)
