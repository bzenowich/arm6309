/* The span-solid length counter - graphics.md 7.4, and design-review2.md V-1.
 *   npm run check:vlen
 */

import { writeFileSync } from "node:fs"
import { join } from "node:path"
import { assemble, fuseChecksum, toJedec, toReport } from "./jedec/assemble"
import { Gal22v10, parseJedec } from "./jedec/simulate"
import { vlenDesign } from "./vlen.jedec"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

const here = new URL(".", import.meta.url).pathname
const a = assemble(vlenDesign)
const jed = toJedec(vlenDesign, a)
writeFileSync(join(here, "vlen.jed"), jed)
writeFileSync(join(here, "vlen.doc"), toReport(vlenDesign, a))
const p = parseJedec(jed)
check(p.declaredChecksum === fuseChecksum(p.fuses), "vlen: fuse checksum")
const gal = new Gal22v10(p.fuses)

const pin = (n: string) => a.usage.find((u) => u.name === n)!.pin
const io = (o: { rd: number; wstbv: 0 | 1; busy: 0 | 1; retire: 0 | 1 }): Record<number, 0 | 1> => ({
  ...Object.fromEntries([0, 1, 2, 3, 4, 5, 6, 7].map((i) => [2 + i, ((o.rd >> i) & 1) as 0 | 1])),
  10: o.wstbv, 11: o.busy, 13: o.retire,
})
/** The counter's own value, read back off the complemented state. */
const value = (pins: Record<number, number>) =>
  255 - [0, 1, 2, 3, 4, 5, 6, 7].reduce((v, i) => v | (pins[pin(`NSL${i}`)] << i), 0)

/* -- one span of every length, end to end -------------------------------- */
{
  let bad: string | null = null
  /* 13: SPANLEN is "span length - 1", so a load of N must retire N + 1 bytes
   * before TC. Every length from 0 to 255. */
  for (let n = 0; n <= 255 && !bad; n++) {
    gal.reset()
    /* The posted write: WSTBV high, SPANBUSY not yet set. */
    gal.clock(io({ rd: n, wstbv: 1, busy: 0, retire: 0 }))
    let seen = gal.evaluate(io({ rd: n, wstbv: 1, busy: 1, retire: 0 }))
    if (value(seen) !== n) { bad = `load ${n} gave ${value(seen)}`; break }

    /* ⚠ And the file has switched to WFG/WBG by now, so a second edge of the
     * same strobe must NOT reload. This is the !SPANBUSY literal, asserted. */
    gal.clock(io({ rd: 0xa1, wstbv: 1, busy: 1, retire: 0 }))
    seen = gal.evaluate(io({ rd: 0xa1, wstbv: 1, busy: 1, retire: 0 }))
    if (value(seen) !== n) { bad = `reloaded from the colour byte: ${value(seen)}`; break }

    let retires = 0
    for (let i = 0; i < 300; i++) {
      const now = gal.evaluate(io({ rd: 0xa1, wstbv: 0, busy: 1, retire: 1 }))
      if (now[pin("TC")] === 1) break
      gal.clock(io({ rd: 0xa1, wstbv: 0, busy: 1, retire: 1 }))
      retires++
    }
    if (retires !== n) bad = `SPANLEN ${n}: TC after ${retires} retires, want ${n}`
  }
  check(bad === null,
    "every SPANLEN from 0 to 255 asserts TC on the (SPANLEN + 1)th retired byte, " +
    "and a second edge of WSTBV does not reload it", bad ?? "")
}

/* -- it does not count when nothing retired ------------------------------ */
{
  gal.reset()
  gal.clock(io({ rd: 31, wstbv: 1, busy: 0, retire: 0 }))
  const before = value(gal.evaluate(io({ rd: 0, wstbv: 0, busy: 1, retire: 0 })))
  for (let i = 0; i < 8; i++) gal.clock(io({ rd: 0, wstbv: 0, busy: 1, retire: 0 }))
  const after = value(gal.evaluate(io({ rd: 0, wstbv: 0, busy: 1, retire: 0 })))
  check(before === 31 && after === 31,
    "and holds while no byte is being retired - the retire rate is the arbiter's, " +
    "not the dot clock's", `${before} -> ${after}`)
}

/* -- the fit ------------------------------------------------------------- */
{
  const widest = a.usage.reduce((m, u) => Math.max(m, u.used), 0)
  check(a.usage.length === 10,
    "eight counter bits, the load term and TC - ten macrocells of ten",
    `${a.usage.length}`)
  check(widest <= 16, "and the widest equation fits the widest macrocell", `${widest}`)
  const tc = a.usage.find((u) => u.name === "TC")!
  check(tc.used === 1,
    "⭐ TC is ONE product term, because the counter holds the complement: " +
    "SPANLEN = 0 is ~SPANLEN = 255, an eight-literal AND", `${tc.used}`)
}

console.log(failures === 0 ? "\nvlen OK" : `\n${failures} failure(s)`)
process.exit(failures === 0 ? 0 : 1)
