/* The $FF map, checked as arithmetic rather than as prose.
 *
 * docs/machine.md 3 does this sum by hand and says "16 + 4 + 4 + 4 + 4 free +
 * 32 = 64". It is right today. This file is what keeps it right when the next
 * card proposes a window.
 */
import { WINDOWS, GEOGRAPHIC_WINDOW } from "../cards/windows"
import { readdirSync } from "node:fs"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}
const hex = (n: number) => `$${n.toString(16).toUpperCase()}`

/* -- the decode a card needs, which the window's size fixes ---------------
 * The strobe supplies every address bit above the window. A card must match
 * the rest itself, and the machine's whole 2026-09-08 widening turns on this
 * number going from 6 to 7 - machine.md 2. */
const cardDecodeBits = Math.log2(GEOGRAPHIC_WINDOW.size)
check(Number.isInteger(cardDecodeBits), "the window is a power of two", `${GEOGRAPHIC_WINDOW.size}`)
check(cardDecodeBits === 7, "a card decodes A0-A6 - seven bits, not six", `A0-A${cardDecodeBits - 1}`)
check(
  (GEOGRAPHIC_WINDOW.base & (GEOGRAPHIC_WINDOW.size - 1)) === 0,
  "the window is aligned to its own size",
  hex(GEOGRAPHIC_WINDOW.base),
)

const sorted = [...WINDOWS].sort((a, b) => a.base - b.base)

/* -- no overlaps. Every window but video's is still a proposal, and proposals
 *    are exactly what overlap silently. */
for (let i = 1; i < sorted.length; i++) {
  const prev = sorted[i - 1]
  const cur = sorted[i]
  check(
    prev.base + prev.size <= cur.base,
    `${prev.card} and ${cur.card} do not overlap`,
    `${hex(prev.base)}+${prev.size} vs ${hex(cur.base)}`,
  )
}

/* -- no gaps, and the window is exactly filled --------------------------- */
check(sorted[0].base === GEOGRAPHIC_WINDOW.base, "the map starts at $FF40")
for (let i = 1; i < sorted.length; i++) {
  check(
    sorted[i - 1].base + sorted[i - 1].size === sorted[i].base,
    `no gap between ${sorted[i - 1].card} and ${sorted[i].card}`,
  )
}
const total = WINDOWS.reduce((n, w) => n + w.size, 0)
check(total === GEOGRAPHIC_WINDOW.size,
  `the windows sum to the ${GEOGRAPHIC_WINDOW.size}-byte geographic decode`, `${total}`)

/* -- the machine's remaining margin, stated rather than discovered -------- */
const free = WINDOWS.filter((w) => w.status === "free").reduce((n, w) => n + w.size, 0)
console.log(`\n      ${free} bytes free of ${GEOGRAPHIC_WINDOW.size}. machine.md 5 item 1 is the machine's blocking decision.`)
if (free === 0) {
  console.log("      There is no margin left. The next card cannot be addressed at all")
  console.log("      without widening or paging the window - machine.md 5 item 1.")
} else {
  console.log(`      ${free} of those bytes came from widening the window below $FF40 on`)
  console.log("      2026-09-08. It is the only expansion the map has left that costs")
  console.log("      nothing: the next one is a decode term, not the deletion of one.")
}

/* -- every card carries the same edge ------------------------------------ */
const cardFiles = readdirSync("cards").filter((f) => f.endsWith(".circuit.tsx"))
check(cardFiles.length === 6, "six card boards exist", cardFiles.join(" "))
for (const f of cardFiles) {
  const src = await Bun.file(`cards/${f}`).text()
  check(
    src.includes('from "../lib/Card"'),
    `${f} takes its edge from lib/slot.ts`,
  )
}
const windowCards = new Set(WINDOWS.filter((w) => w.status !== "free").map((w) => w.card))
for (const f of cardFiles) {
  const name = f.replace(".circuit.tsx", "")
  check(windowCards.has(name), `${name} has a window in the $FF map`)
}

console.log(failures === 0 ? "\n$FF map OK" : `\n${failures} failure(s)`)
process.exit(failures === 0 ? 0 : 1)
