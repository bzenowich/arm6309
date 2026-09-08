/* The placement study, checked as arithmetic rather than as a drawing.
 *
 * Every other check in this directory asserts a claim about connectivity or
 * about a fuse map. This one asserts the two claims a *drawing* makes: that
 * every package a card's document lists lands on the board that card declares,
 * and that the board is the shortest one that holds it.
 *
 * ⚠ IT EXISTS BECAUSE COUNTING ROWS IS NOT COUNTING PARTS. On 2026-09-08 the
 * storage card was published as 13 ICs against its own §8 table of 14 — the
 * table's rows run 1 to 13 and two of them carry more than one package. The
 * assertion that `icCount(spec)` equals the board file's `icBudget` is the one
 * that catches that, and it caught nothing until the parts were enumerated.
 *
 *   npm run check:place
 */
import { readFileSync } from "node:fs"
import { join } from "node:path"

import { CARDS, LENGTHS, BOARD_H, icCount, footprintCount, type CardSpec } from "./parts"
import { pack, fits } from "./pack"
import { WINDOWS } from "../cards/windows"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}
const here = new URL(".", import.meta.url).pathname

/* -- every card takes one of the three lengths --------------------------- */
for (const [key, c] of Object.entries(CARDS)) {
  check((LENGTHS as readonly number[]).includes(c.length),
    `${key} is 12, 18 or 24 cm`, `${c.length} mm`)
}

/* -- every package lands, and the skyline stays on the board -------------- */
for (const [key, c] of Object.entries(CARDS)) {
  const r = pack(c)
  check(r.over.length === 0, `${key}: every package places on ${c.length / 10} cm`,
    r.over.join(", "))
  check(r.skyline <= BOARD_H - 3, `${key}: placement stays inside 100 mm`,
    `${r.skyline.toFixed(1)} mm`)
  check(r.courtyard <= r.placeable,
    `${key}: courtyard fits the placeable area`,
    `${r.courtyard} of ${r.placeable} cm²`)
}

/* -- and the length is minimal, which is what makes it a choice ----------- */
for (const [key, c] of Object.entries(CARDS)) {
  const shortest = LENGTHS.find((L) => fits(c, L))
  check(shortest === c.length, `${key}: ${c.length / 10} cm is the shortest that works`,
    shortest === undefined ? "fits none of them" : `${shortest / 10} cm does`)
}

/* -- the count matches the board file, which matches the document ---------
 *
 * cards/*.circuit.tsx carries `icBudget`, transcribed from the card's own
 * chip budget. Two independent transcriptions of the same table disagreeing is
 * exactly the error this file was written for. */
const budgets = new Map<string, number>()
for (const f of ["video", "audio", "net", "storage", "io"]) {
  let src: string
  try { src = readFileSync(join(here, `../cards/${f}.circuit.tsx`), "utf8") }
  catch { check(false, `cards/${f}.circuit.tsx exists`); continue }
  const m = src.match(/icBudget=\{(\d+)\}/)
  if (!m) { check(false, `cards/${f}.circuit.tsx declares icBudget`); continue }
  budgets.set(f, Number(m[1]))
}
for (const [key, c] of Object.entries(CARDS)) {
  const b = budgets.get(key)
  if (b === undefined) continue
  check(icCount(c) === c.ics, `${key}: the parts list totals its own claim`,
    `${icCount(c)} vs ${c.ics}`)
  check(icCount(c) === b, `${key}: and agrees with cards/${key}.circuit.tsx`,
    `${icCount(c)} vs icBudget ${b}`)
}

/* -- every card in the study has a window, and vice versa ----------------- */
const windowed = new Set(WINDOWS.filter((w) => w.status !== "free").map((w) => w.card))
for (const key of Object.keys(CARDS)) {
  check(windowed.has(key), `${key} has a window in the $FF map`)
}
for (const w of WINDOWS) {
  if (w.status === "free") continue
  check(w.card in CARDS, `the $FF map's "${w.card}" is a drawn card`)
}

/* -- the report ----------------------------------------------------------- */
console.log("\nBoard census\n")
const pct = (c: CardSpec) => {
  const r = pack(c)
  return Math.round((100 * r.courtyard) / r.placeable)
}
let area = 0
for (const [key, c] of Object.entries(CARDS)) {
  const r = pack(c)
  area += (c.length * BOARD_H) / 100
  console.log(`      ${c.title.padEnd(8)} ${String(c.length / 10).padStart(2)} cm  ` +
    `${String(icCount(c)).padStart(2)} ICs  ${String(footprintCount(c)).padStart(2)} footprints  ` +
    `${String(r.courtyard).padStart(6)} of ${String(r.placeable).padStart(6)} cm²  ` +
    `${String(pct(c)).padStart(3)} %`)
}
console.log(`\n      ${Object.keys(CARDS).length} cards, ${area.toFixed(0)} cm² of board.` +
  ` Cut to the longest they would be ${((LENGTHS[2] * BOARD_H) / 100) * Object.keys(CARDS).length} cm².`)

console.log(failures === 0 ? "\nplacement OK" : `\n${failures} failure(s)`)
process.exit(failures === 0 ? 0 : 1)
