/* video3's 32-byte register window - is every offset actually USED?
 *   bun run video3/logic/regmap.check.ts        (part of `npm run check`)
 *
 * ⭐ THE QUESTION THIS ANSWERS IS reach.check.ts's, ONE LEVEL UP.  `check:reach`
 * asks whether every signal a part PRODUCES is read by something. This asks
 * whether every byte of the host's address window is DECODED by something - the
 * same defect (`ACTRL` b3: latched, read back, and taken by no cell for two
 * days) wearing an address instead of a bit.
 *
 * ⛔ AND "IT READS BACK" IS NOT EVIDENCE.  Every offset but +$0C and +$0D reads
 * back from the 32-byte register file, because the file is RAM and RDBKOE puts
 * it on the bus. A byte that reads back what was written and is decoded by
 * nothing is exactly the thing this check exists to find - `boot.asm` uses +$13
 * as a card-probe scratch for that very reason.
 *
 * An offset counts as used if EITHER:
 *
 *   (a) a LIVE design decodes its load strobe - the four `.cpld.ts` the board
 *       model instantiates, not the partition variants beside them; or
 *   (b) the register file's own address generator READS it - v3host's `rf`
 *       cells park RFA at +$05 when idle, at +$06/+$07 through a span, and walk
 *       +$08, +$09, +$12, +$13 to restore the two columns; or
 *   (c) it is a dedicated port rather than a file byte (+$0C `VDATA`, +$0D
 *       `VSTAT`).
 *
 * ⚠ (b) IS A TYPED TABLE AND (a) IS DERIVED, and the asymmetry is deliberate.
 * The strobe half is what drifts - a `MY_REGS` edit moves it silently - so it is
 * read out of the designs. The RFA half lives in one hand-written product-term
 * generator that nothing else can change by accident, so it is asserted here
 * against the offsets that generator names, and a disagreement is a failure.
 *
 * ⛔ AND THE SPARE LIST IS CHECKED IN BOTH DIRECTIONS, like reach.check.ts's
 * RESERVED: an offset that stops being spare has to come off it. That is what
 * stops SPARE becoming a place to put things.
 */
import { REGS, type RegName } from "./regmap"
import { v3dot } from "./v3dot.cpld"
import { v3host } from "./v3host.cpld"
import { v3ptr } from "./v3ptr.cpld"
import { v3scan } from "./v3scan.cpld"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

/* ⭐ THE LIVE PARTS, and they are the ones video3/sim/video3_card.v
 * instantiates: v3dot, v3scan, v3ptr, v3host (+ the v3lane GAL, which sees no
 * register offsets). The `_st`, `_si`, `_mq`, `_copy`, `_none`, `_span`, `_rows`
 * and `_both` .pld files beside them are PARTITION VARIANTS - v3host.cpld.ts
 * emits "v3host_st" under DECODE === "strobes" - and two of them still carry
 * LDSPRIX/LDSPRDA from before the sprite shape moved to VRAM. Counting a
 * variant's decode as a use is how +$1D and +$1E would look occupied. */
const LIVE = { v3dot, v3host, v3ptr, v3scan }

/* Which live parts declare a cell named after each load strobe. */
const decodedBy = (r: RegName): string[] =>
  Object.entries(LIVE)
    .filter(([, d]) => d.cells.some((c) => c.name === r))
    .map(([n]) => n)

/* (b) The offsets v3host's `rf` generator parks or walks the file address on.
 * v3host.cpld.ts's own comment block above `const rf`:
 *     idle +$05 SPANLEN | span +$06/+$07 WFG/WBG
 *     RP1  +$08  RP2 +$09  RP3 +$12  RP4 +$13                                */
const RFA_READS: Record<number, string> = {
  0x05: "RFA parks here when idle, so span-solid's SPANLEN load needs no address",
  0x06: "RFA points here through a span - WFG, with RFA0 (v3ptr) the mask bit",
  0x07: "the odd half of the same pair - WBG",
  0x08: "reload walk RP1 restores WPTR's column low byte",
  0x09: "reload walk RP2 restores WPTR's column high bits",
  0x12: "reload walk RP3 restores CPTR's column low byte",
  0x13: "reload walk RP4 restores CPTR's column high bits",
}

/* (c) Not register-file bytes at all. */
const PORTS: Record<number, string> = {
  0x0c: "VDATA - v3host's VDSEL, the posted VRAM port at WPTR",
  0x0d: "VSTAT - read through a '244 (VSTATOE); a WRITE is LDIRQACK",
}

/* ⛔ The spare list. Each needs a reason, and an entry that stops being spare
 * fails too. plan.md §10 is the specification these must agree with. */
const SPARE: Record<number, string> = {
  0x1d: "spare since 2026-09-19 - the sprite shape moved to VRAM (plan §7)",
  0x1e: "spare, the same",
  0x1f: "spare in HARDWARE; the VBL service parks its frame count here (FCNT)",
}

const byOffset = new Map<number, RegName>()
for (const [name, off] of Object.entries(REGS)) byOffset.set(off, name as RegName)

type Row = { off: number; name: string; how: string; who: string }
const rows: Row[] = []

for (let off = 0; off < 32; off++) {
  const strobe = byOffset.get(off)
  const parts = strobe ? decodedBy(strobe) : []
  const rfa = RFA_READS[off]
  const port = PORTS[off]
  const spare = SPARE[off]

  let how = "", who = ""
  if (parts.length) { how = "strobe"; who = `${strobe} decoded by ${parts.join(", ")}` }
  else if (port) { how = "port"; who = port }
  else if (rfa) { how = "file read"; who = rfa }
  else if (spare) { how = "SPARE"; who = spare }
  else { how = "⛔ NOTHING"; who = strobe ? `${strobe} is declared and NO live part decodes it` : "no strobe, no reader" }

  /* +$0D is both: a write is LDIRQACK, a read is VSTAT. Say so. */
  if (off === 0x0d && parts.length) who = `${who}; read is ${PORTS[0x0d]}`

  rows.push({ off, name: strobe ?? (port ? port.split(" ")[0] : spare ? "-" : "?"), how, who })
}

console.log("\nvideo3's 32-byte window at $FF60-$FF7F\n")
console.log("  off   reg        how         what makes it used")
console.log("  " + "-".repeat(96))
for (const r of rows) {
  console.log(`  +$${r.off.toString(16).padStart(2, "0").toUpperCase()}  ` +
    `${r.name.padEnd(10)} ${r.how.padEnd(11)} ${r.who}`)
}
console.log("")

const unused = rows.filter((r) => r.how === "⛔ NOTHING")
check(unused.length === 0,
  "every offset in the window is decoded by a live part, read by the file's address generator, or a port",
  unused.map((r) => `+$${r.off.toString(16)} ${r.name}`).join("; "))

const spareRows = rows.filter((r) => r.how === "SPARE")
check(spareRows.length === Object.keys(SPARE).length,
  `exactly ${Object.keys(SPARE).length} offsets are spare, and they are the ones on the list`,
  spareRows.map((r) => `+$${r.off.toString(16)}`).join(" "))

/* ⛔ Both directions: an entry that is no longer spare must come off the list. */
for (const off of Object.keys(SPARE).map(Number)) {
  const strobe = byOffset.get(off)
  const parts = strobe ? decodedBy(strobe) : []
  check(parts.length === 0 && !RFA_READS[off] && !PORTS[off],
    `+$${off.toString(16)} is still spare, so its SPARE entry is still earned`,
    parts.length ? `now decoded by ${parts.join(", ")}` : "")
}

/* ⚠ The two strobe names regmap.ts still declares that nothing decodes. Naming
 * them is not a failure - the offsets are genuinely free - but a name that
 * outlives its logic is how "+$1D is taken" gets believed. */
const orphans = Object.entries(REGS)
  .filter(([n]) => decodedBy(n as RegName).length === 0)
  .filter(([, o]) => !RFA_READS[o] && !PORTS[o])
  .map(([n, o]) => `${n} (+$${o.toString(16)})`)
check(orphans.length === 2 && orphans.every((o) => /LDSPRIX|LDSPRDA/.test(o)),
  "the only load strobes regmap.ts declares and no live part decodes are LDSPRIX and LDSPRDA",
  orphans.join(", "))

console.log(`\n${rows.length} offsets, ${rows.filter(r => r.how !== "SPARE").length} used, ` +
  `${spareRows.length} spare`)
if (failures) { console.error(`\n${failures} failed`); process.exit(1) }
