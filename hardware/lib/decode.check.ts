/* Every card completes its own $FF decode, checked across all cards at once.
 *   npm run check:decode
 *
 * ** THE RULE. docs/machine.md 5 item 1 widened the geographic window from
 * $FF40-$FF7F to $FF00-$FF7F on 2026-09-08, and /IOSEL became /IOPAGE AND
 * /A7 - one product-term literal FEWER than the 64-byte decode it replaced.
 * The saving is on the motherboard and the cost is on the cards:
 *
 *   ** WITH A6 OUT OF THE STROBE, A CARD THAT MATCHES SIX ADDRESS BITS
 *   ANSWERS AT ITS BASE *AND* 64 BYTES BELOW IT - two cards driving D0-D7 at
 *   once, silently, on a bus with no arbitration and no way to notice.
 *
 * ** WHY THIS FILE EXISTS RATHER THAN A PARAGRAPH. The rule was written down
 * in machine.md, in cards/windows.ts, and in lib/cards.check.ts's header. The
 * audio card still shipped a decode that read NO address bits at all - `SEL`
 * was an input pin, driven by nothing in any design file and by nothing on the
 * board - and it survived a design review, a port census and 460-odd passing
 * claims. A rule three documents state and nothing executes is a rule the next
 * card will break too.
 *
 * lib/cards.check.ts already proves the WINDOWS do not overlap. This proves
 * each card's LOGIC actually distinguishes its window from the aliases the
 * strobe no longer excludes. They are different claims: audio's window was
 * correct and unique in windows.ts the whole time it was undecodable.
 *
 * ** WHAT A CARD MUST READ is fixed by its window size, because /IOSEL
 * supplies A7 and nothing below it:
 *
 *   16 bytes ($FF40)  A6, A5, A4         3 bits above the 4 the offsets use
 *   32 bytes ($FF60)  A6, A5             2 bits above the 5 the offsets use
 *
 * A card may of course read MORE (the offsets themselves); it may not read
 * fewer. A0-A3 are register selects, not decode, so they are not required
 * here - a card that decodes its base correctly cannot alias another card.
 */

import { WINDOWS, GEOGRAPHIC_WINDOW } from "../cards/windows"
import type { Cell, Design } from "../gal/jedec/assemble"
import type { Merged } from "../gal/jedec/cupl"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}
const hex = (n: number) => `$${n.toString(16).toUpperCase()}`

/* -- every literal a design reads, and every name it produces ------------- */
const literalsOf = (cells: Cell[]) => {
  const read = new Set<string>()
  for (const c of cells) {
    for (const t of [...c.terms, ...(c.oe ? [c.oe] : [])]) {
      for (const l of t.split("&")) {
        const s = l.trim().replace(/^!/, "")
        if (s && s !== "1" && s !== "0") read.add(s)
      }
    }
  }
  return read
}
const producedBy = (cells: Cell[]) => new Set(cells.map((c) => c.name))

/* -- the cards whose logic exists ----------------------------------------
 *
 * A card with no design file yet cannot be checked and is not a failure - it
 * is storage, net and io, which are windows in windows.ts and nothing else so
 * far. What IS a failure is a card whose logic exists and does not decode. */
interface Card { window: string; cells: Cell[]; note: string }
const cards: Card[] = []

const load = async () => {
  try {
    const { audioCpld } = await import("../gal/audio.cpld")
    cards.push({ window: "audio", cells: (audioCpld as Merged).cells, note: "gal/audio.cpld.ts" })
  } catch (e) { check(false, "audio card design loads", String(e).slice(0, 120)) }
  try {
    /* The video card's own decode is rfa's REGSEL - graphics.md 10.1.6.3 moved
     * it off vctrl, so this is where the card's base is matched. */
    const { rfaDesign } = await import("../gal/regfile.jedec")
    cards.push({ window: "video", cells: (rfaDesign as Design).cells, note: "gal/regfile.jedec.ts (rfa)" })
  } catch (e) { check(false, "video card design loads", String(e).slice(0, 120)) }
}

await load()

/* -- the check ------------------------------------------------------------ */
const BITS_FOR = (size: number): string[] => {
  /* /IOSEL supplies A7. The card must match every address bit from A6 down to
   * the first bit its own offsets use. */
  const offsetBits = Math.log2(size)
  const need: string[] = []
  for (let b = 6; b >= offsetBits; b--) need.push(`A${b}`)
  return need
}

check(cards.length > 0, "at least one card's decode logic exists to be checked")

for (const card of cards) {
  const w = WINDOWS.find((x) => x.card === card.window)
  if (!w) { check(false, `${card.window} has a window in cards/windows.ts`); continue }

  const read = literalsOf(card.cells)
  const made = producedBy(card.cells)
  const need = BITS_FOR(w.size)
  const missing = need.filter((b) => !read.has(b))

  check(missing.length === 0,
    `${card.window} (${hex(w.base)}, ${w.size} bytes) matches ${need.join(", ")} itself - ` +
    `so it cannot answer ${GEOGRAPHIC_WINDOW.size / 2} bytes below its base as well`,
    missing.length ? `${card.note} never reads ${missing.join(", ")}` : "")

  /* ⛔ AND THE SELECT MUST BE PRODUCED, NOT IMPORTED. Audio's `SEL` read the
   * right shape of nothing: it was an input pin, so the equations looked
   * plausible and the card had no decode at all. A select that arrives as a
   * pin has to be driven by something, and for these cards nothing does. */
  const strobes = ["IOSEL", "IOPAGE"]
  const usesStrobe = strobes.some((s) => read.has(s))
  check(usesStrobe,
    `${card.window} qualifies its decode with the motherboard's strobe`,
    usesStrobe ? "" : `${card.note} reads neither ${strobes.join(" nor ")}`)

  /* ⛔ AND NO SELECT MAY ARRIVE AS A PIN. Audio's `SEL` read the right shape
   * of nothing: it was an input, so the equations looked plausible while the
   * card had no decode at all and no design file or board net drove it.
   *
   * ⚠ The property is "imported, pre-decoded select", NOT "has a cell called
   * something SEL". The video card computes its own `regsel` as an inline
   * product (gal/rfa.pld) and never names a cell for it - which is correct and
   * which an earlier version of this check called a failure. What is checked
   * is that every select-shaped literal the design READS is either produced
   * here or is the motherboard's own strobe. */
  const imported = [...read]
    .filter((n) => /SEL$/.test(n) && !made.has(n) && !strobes.includes(n))
  check(imported.length === 0,
    `${card.window} takes no pre-decoded select as a pin - it derives its own, ` +
    `which is the defect audio shipped where nothing anywhere drove it`,
    imported.length ? `${card.note} imports ${imported.join(", ")}` : "")
}

/* -- and the rule itself is still the rule -------------------------------- */
check(GEOGRAPHIC_WINDOW.size === 0x80,
  "the geographic window is still 128 bytes, which is what makes A6 the card's job",
  hex(GEOGRAPHIC_WINDOW.size))

console.log("")
console.log(failures === 0
  ? `${cards.length} cards complete their own decode; the aliasing machine.md 5 item 1 warns about is impossible`
  : `${failures} FAILURES`)
process.exit(failures === 0 ? 0 : 1)
