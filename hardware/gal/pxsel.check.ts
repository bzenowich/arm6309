/* graphics.md 8.2's fetch-rank select - 19 item 28's byte-granular scroll.
 *   npm run check:pxsel
 */

import { writeFileSync } from "node:fs"
import { join } from "node:path"
import { assemble, fuseChecksum, toJedec, toReport } from "./jedec/assemble"
import { Gal22v10, parseJedec } from "./jedec/simulate"
import { pxselDesign } from "./pxsel.jedec"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

const here = new URL(".", import.meta.url).pathname
const a = assemble(pxselDesign)
const jed = toJedec(pxselDesign, a)
writeFileSync(join(here, "pxsel.jed"), jed)
writeFileSync(join(here, "pxsel.doc"), toReport(pxselDesign, a))
const p = parseJedec(jed)
check(p.declaredChecksum === fuseChecksum(p.fuses), "pxsel: fuse checksum, and the file reads back as written")
const gal = new Gal22v10(p.fuses)
const pin = (n: string) => a.usage.find((u) => u.name === n)!.pin

const io = (o: { ldhs?: 0 | 1; lwhsl?: 0 | 1; d?: number; pb?: number }): Record<number, 0 | 1> => ({
  2: 1,   /* /RESET released - the only reset a 22V10 has is asynchronous */
  3: o.ldhs ?? 0, 4: o.lwhsl ?? 0,
  5: ((o.d ?? 0) & 1) as 0 | 1, 6: (((o.d ?? 0) >> 1) & 1) as 0 | 1,
  7: ((o.pb ?? 0) & 1) as 0 | 1, 8: (((o.pb ?? 0) >> 1) & 1) as 0 | 1,
})
const heldP = (pins: Record<number, number>) => pins[pin("HS0")] | (pins[pin("HS1")] << 1)
/* Each enable in ASSERTED sense - 1 is "this rank drives". The pins are the
 * '574s' /OE and are declared asserted-low (2026-09-11), so the level is
 * inverted through the declaration; chip 3's pair is strapped, rank A off and
 * rank B on. pins.check.ts is what holds the declaration to the part. */
const asserted = (name: string, pins: Record<number, number>) =>
  pxselDesign.cells.find((c) => c.name === name)!.assertedLow ? 1 - pins[pin(name)] : pins[pin(name)]
const oeA = (pins: Record<number, number>) =>
  [asserted("OEA0", pins), asserted("OEA1", pins), asserted("OEA2", pins), 0]
const oeB = (pins: Record<number, number>) =>
  [asserted("OEB0", pins), asserted("OEB1", pins), asserted("OEB2", pins), 1]

/* -- the two write ports, and that they cannot diverge -------------------- */
{
  let bad: string | null = null
  for (let v = 0; v < 4 && !bad; v++) {
    gal.reset()
    gal.clock(io({ ldhs: 1, d: v }))
    if (heldP(gal.evaluate(io({}))) !== v) bad = `CPU write of ${v} held ${heldP(gal.evaluate(io({})))}`
  }
  check(bad === null, "the CPU's write to +$03 lands in HSCROLL[1:0] - LDHS with the data on D1:D0", bad ?? "")

  bad = null
  for (let v = 0; v < 4 && !bad; v++) {
    gal.reset()
    gal.clock(io({ lwhsl: 1, pb: v }))
    if (heldP(gal.evaluate(io({}))) !== v) bad = `list MOVE of ${v} held ${heldP(gal.evaluate(io({})))}`
  }
  check(bad === null,
    "⭐ and so does 10.3.2's list MOVE - LWHSL with the data on PB1:PB0, which is what makes per-scanline scroll SMOOTH rather than four-pixel", bad ?? "")

  gal.reset()
  gal.clock(io({ ldhs: 1, d: 3 }))
  gal.clock(io({}))
  check(heldP(gal.evaluate(io({}))) === 3,
    "and neither strobe means hold - a value survives every dot in which nothing writes it")
}

/* -- OEA(c) = c < p, over every p and every chip -------------------------- */
{
  let bad: string | null = null
  for (let v = 0; v < 4 && !bad; v++) {
    gal.reset()
    gal.clock(io({ ldhs: 1, d: v }))
    const pins = gal.evaluate(io({}))
    const a4 = oeA(pins), b4 = oeB(pins)
    for (let c = 0; c < 4; c++) {
      const want = c < v ? 1 : 0
      if (a4[c] !== want) { bad = `p=${v} chip ${c}: rank A enable ${a4[c]}, want ${want}`; break }
      if (b4[c] === a4[c]) { bad = `p=${v} chip ${c}: BOTH RANKS ${a4[c]} - two '574s on one net`; break }
    }
  }
  check(bad === null,
    "rank A is enabled exactly when chip < HSCROLL[1:0], over all four scroll values and all four chips", bad ?? "")
  check(bad === null,
    "⚠ and the two enables are never equal, on any chip at any scroll value - the ranks share a net and a '574 drives hard", bad ?? "")
}

/* -- the p = 0 invariant -------------------------------------------------- */
{
  gal.reset()
  gal.clock(io({ ldhs: 1, d: 0 }))
  const pins = gal.evaluate(io({}))
  check(oeA(pins).every((x) => x === 0) && oeB(pins).every((x) => x === 1),
    "⭐ at HSCROLL[1:0] = 0 every chip reads rank B - the picture is what a one-slot fetch lead produced, which is the invariant vaddr_tb checks")
  gal.reset()
  gal.clock(io({ ldhs: 1, d: 3 }))
  const q = gal.evaluate(io({}))
  check(oeA(q)[0] === 1 && oeA(q)[1] === 1 && oeA(q)[2] === 1 && oeA(q)[3] === 0,
    "and at 3 only chip 3 still reads rank B, which is 19 item 28's `c >= p` with p at its widest")
}

console.log("")
console.log("The fit\n")
console.log(`      ${pxselDesign.partNo} ${pxselDesign.name}  ${a.usage.filter((u) => u.pin >= 14).length} macrocells, 8 of 22 signal pins`)
console.log("")
console.log(failures === 0
  ? "19 item 28's rank select fits a GAL22V10 with two macrocells and fourteen pins spare"
  : `${failures} FAILURES`)
process.exit(failures === 0 ? 0 : 1)
