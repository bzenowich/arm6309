/* The $FF map, checked as arithmetic rather than as prose.
 *
 * docs/machine.md 3 does this sum by hand and says "16 + 4 + 4 + 4 + 4 free +
 * 32 = 64". It is right today. This file is what keeps it right when the next
 * card proposes a window.
 */
import { WINDOWS, MMU_WINDOWS, GEOGRAPHIC_WINDOW } from "../cards/windows"
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
check(sorted[0].base === GEOGRAPHIC_WINDOW.base,
  `the map starts at ${hex(GEOGRAPHIC_WINDOW.base)}`, hex(sorted[0].base))
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
check(cardFiles.length === 5, "five card boards exist", cardFiles.join(" "))
for (const f of cardFiles) {
  const src = await Bun.file(`cards/${f}`).text()
  check(
    src.includes('from "../lib/Card"'),
    `${f} takes its edge from lib/slot.ts`,
  )
  /* Since 2026-09-08 a card also declares how long it is. place/parts.ts
   * carries the packing that justifies the number and place.check.ts asserts
   * it is the shortest that works. */
  const len = src.match(/length=\{(\d+)\}/)
  check(len !== null && [120, 180, 240].includes(Number(len[1])),
    `${f} declares a 12, 18 or 24 cm length`, len ? len[1] : "none")
}
const windowCards = new Set(WINDOWS.filter((w) => w.status !== "free").map((w) => w.card))
for (const f of cardFiles) {
  const name = f.replace(".circuit.tsx", "")
  check(windowCards.has(name), `${name} has a window in the $FF map`)
}

/* -- the OTHER half of the $FF page, and nothing checked it until 2026-09-09
 *
 * The geographic window is $FF00-$FF7F and every card lives in it. $FF80-$FFFF
 * is decoded by the MOTHERBOARD - U3 forms $FF90-$FFBF and U9 the vector page
 * - and it was prose in machine.md 3 with no arithmetic behind it. That is
 * exactly the ground design-review2.md M-1 was fought on: the repair PUT A NEW
 * WINDOW at $FF90 and there was no check that could have said whether it
 * landed on something. There is one now. */
{
  const mmu = [...MMU_WINDOWS].sort((a, b) => a.base - b.base)
  const geoEnd = GEOGRAPHIC_WINDOW.base + GEOGRAPHIC_WINDOW.size
  for (const w of mmu) {
    check(w.base >= geoEnd,
      `${w.card} is outside the geographic window, so no card loses a byte`,
      `${hex(w.base)} vs ${hex(geoEnd)}`)
    check((w.base & (w.size - 1)) === 0,
      `${w.card} is aligned to its own size`, hex(w.base))
  }
  for (let i = 1; i < mmu.length; i++) {
    check(mmu[i - 1].base + mmu[i - 1].size <= mmu[i].base,
      `${mmu[i - 1].card} and ${mmu[i].card} do not overlap`,
      `${hex(mmu[i - 1].base)}+${mmu[i - 1].size} vs ${hex(mmu[i].base)}`)
  }
  check(mmu[0].base === geoEnd,
    `the motherboard's own decode starts where the card window ends`, hex(mmu[0].base))
  const last = mmu[mmu.length - 1]
  check(last.base + last.size === 0x10000,
    "and it runs to $FFFF - the vector page is the top of it",
    hex(last.base + last.size))
  const mmuTotal = mmu.reduce((n, w) => n + w.size, 0)
  check(mmuTotal === 0x10000 - geoEnd,
    `the whole $FF page is accounted for - ${GEOGRAPHIC_WINDOW.size} geographic + ${mmuTotal} motherboard`,
    `${GEOGRAPHIC_WINDOW.size + mmuTotal}`)

  /* ⚠ THE MMU'S TWO BLOCK WINDOWS MUST CARRY THE SAME INDEX. $FF90+n and
   * $FFA0+n are the two halves of ONE entry (ram.md 4.3), which is only true
   * while both windows are sixteen bytes and both are aligned - the property
   * mmu.jedec.ts's blkhi/blklo encode and the '157 depends on. */
  const hi = mmu.find((w) => w.card === "mmu-high")!
  const lo = mmu.find((w) => w.card === "mmu-low")!
  check(hi.size === 16 && lo.size === 16 && ((hi.base ^ lo.base) & 0xfff0) === 0x0030,
    "⭐ the two block windows are 16 bytes apart in A5:A4 and carry the same " +
    "A3..A0 index - $FF90+n and $FFA0+n are the halves of one entry",
    `${hex(hi.base)} / ${hex(lo.base)}`)

  const mmuFree = mmu.filter((w) => w.status === "free").reduce((n, w) => n + w.size, 0)
  console.log(`\n      ${mmuFree} bytes free above the card window, at ${
    mmu.filter((w) => w.status === "free").map((w) => hex(w.base)).join(" ")}.`)
  console.log("      That is the machine's last motherboard-decoded block, and it is")
  console.log("      the fourth code of A7..A4 = 10xx - one literal on U3, not a term.")
}

console.log(failures === 0 ? "\n$FF map OK" : `\n${failures} failure(s)`)
process.exit(failures === 0 ? 0 : 1)
