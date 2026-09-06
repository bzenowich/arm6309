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
check(total === GEOGRAPHIC_WINDOW.size, "the windows sum to the 64-byte geographic decode", `${total}`)

/* -- the machine's remaining margin, stated rather than discovered -------- */
const free = WINDOWS.filter((w) => w.status === "free").reduce((n, w) => n + w.size, 0)
console.log(`\n      ${free} bytes free of ${GEOGRAPHIC_WINDOW.size}. machine.md 5 item 1 is the machine's blocking decision.`)

/* -- every card carries the same edge ------------------------------------ */
const cardFiles = readdirSync("cards").filter((f) => f.endsWith(".circuit.tsx"))
check(cardFiles.length === 5, "five card boards exist", cardFiles.join(" "))
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
