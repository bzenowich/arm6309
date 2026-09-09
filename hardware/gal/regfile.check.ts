/* rfa, the register-file address GAL - graphics.md 10.1.6.3's relief.
 *   npm run check:regfile
 *
 * Two independent statements are checked here, and neither is "the fuses match
 * the equations" - jedec/cupl.check.ts does that against Atmel's own compiler.
 * These are the SPECIFICATION claims, which a second compiler cannot settle:
 *
 *   1. During a CPU access to $FF60-$FF7F, RA[4:0] is A[4:0] - the register
 *      the CPU named, and no other. (graphics.md 13)
 *   2. Otherwise RA[4:0] is the read-back source the fetch phase asks for,
 *      and WSTB never fires. (graphics.md 7.2, 13)
 */

import { writeFileSync } from "node:fs"
import { join } from "node:path"
import { assemble, fuseChecksum, toJedec, toReport } from "./jedec/assemble"
import { Gal22v10, parseJedec } from "./jedec/simulate"
import { rfaDesign } from "./regfile.jedec"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

const here = new URL(".", import.meta.url).pathname
const a = assemble(rfaDesign)
const jed = toJedec(rfaDesign, a)
writeFileSync(join(here, "rfa.jed"), jed)
writeFileSync(join(here, "rfa.doc"), toReport(rfaDesign, a))
const parsed = parseJedec(jed)
check(parsed.declaredChecksum === fuseChecksum(parsed.fuses),
  "rfa: fuse checksum, and the file reads back as written")
const gal = new Gal22v10(parsed.fuses)

const P = Object.fromEntries(a.usage.map((u) => [u.name, u.pin]))
const IN = Object.fromEntries(rfaDesign.inputs.map((i) => [i.name, i.pin]))

/** Drive every input by name; anything unnamed is 0. */
const run = (set: Record<string, 0 | 1>) => {
  const pins: Record<number, 0 | 1> = {}
  for (const i of rfaDesign.inputs) pins[i.pin] = set[i.name] ?? 0
  const out = gal.evaluate(pins)
  return {
    ra: [0, 1, 2, 3, 4].reduce((v, n) => v | (out[P[`RA${n}`]] << n), 0),
    wstb: out[P.WSTB],
  }
}
/** A CPU access to register `reg` of the 32-byte window. */
const cpu = (reg: number, rw: 0 | 1, e: 0 | 1 = 1) => run({
  IOSEL: 1, A6: 1, A5: 1, RW: rw, E: e,
  A0: (reg & 1) as 0 | 1, A1: ((reg >> 1) & 1) as 0 | 1, A2: ((reg >> 2) & 1) as 0 | 1,
  A3: ((reg >> 3) & 1) as 0 | 1, A4: ((reg >> 4) & 1) as 0 | 1,
})

/* -- 1. the CPU names the register ---------------------------------------- */
{
  let bad: string | null = null
  for (let reg = 0; reg < 32 && !bad; reg++) {
    for (const rw of [0, 1] as const) {
      const r = cpu(reg, rw)
      if (r.ra !== reg) bad = `+$${reg.toString(16)} ${rw ? "read" : "write"} -> RA=${r.ra}`
    }
  }
  check(bad === null, "all 32 registers: RA[4:0] follows A[4:0] on read and write", bad ?? "")
}

/* -- 2. WSTB is a write, in the second half of E, inside the window -------- */
{
  const w = cpu(7, 0, 1)
  check(w.wstb === 1, "WSTB fires on a write to the window while E is high")
  check(cpu(7, 1, 1).wstb === 0, "WSTB does not fire on a READ - it would clobber the register")
  check(cpu(7, 0, 0).wstb === 0,
    "WSTB does not fire before E - a 6809 write is only valid data in E's second half")
  for (const off of [{ IOSEL: 0 as const }, { A6: 0 as const }, { A5: 0 as const }]) {
    const [name] = Object.keys(off)
    const r = run({ IOSEL: 1, A6: 1, A5: 1, RW: 0, E: 1, A0: 1, A1: 1, A2: 1, ...off })
    check(r.wstb === 0, `WSTB does not fire with ${name} deasserted - REGSEL is all three`)
  }
}

/* -- 3. outside the window, the SPAN WRITER owns the address -------------- *
 *
 * ⭐ REWRITTEN 2026-09-09. This used to check a two-bit walk on FP1:FP0 that
 * presented SPANLEN, WFG and WBG in turn while the span writer was IDLE - and
 * nothing on the card produced FP0 or FP1, nothing received the three values,
 * and every term carried !SPANBUSY, so DURING a span the file address was $00
 * and the span writer would have retired CTRL's byte into the framebuffer.
 * design-review2.md V-1.
 *
 * What replaces it is 7.4's own sentence: "the serialiser's serial output is
 * wired to the register file's address bit 0, which is why 13 requires WFG at
 * A0 = 0 and WBG at A0 = 1". The file is addressed LIVE, and the mask bit is
 * the address line. */
{
  const SPANLEN = 0x05, WFG = 0x06, WBG = 0x07

  /* Idle: the file holds SPANLEN, which is what vlen loads at the posted
   * write - no walk, no phase, no state. */
  check(run({ SPANBUSY: 0 }).ra === SPANLEN,
    "idle, the file addresses SPANLEN - which is how the length counter is " +
    "loaded without a phase of its own", `${run({ SPANBUSY: 0 }).ra}`)

  /* Running: the mask bit picks the colour, one address line and no logic. */
  check(run({ SPANBUSY: 1, MASKBIT: 0 }).ra === WBG,
    "⭐ during a span a 0 mask bit addresses WBG - 7.4's table",
    `${run({ SPANBUSY: 1, MASKBIT: 0 }).ra}`)
  check(run({ SPANBUSY: 1, MASKBIT: 1 }).ra === WFG,
    "⭐ and a 1 addresses WFG - a glyph's set bits are its ink, and the whole " +
    "mechanism is one address line",
    `${run({ SPANBUSY: 1, MASKBIT: 1 }).ra}`)

  check([0, 1].every((m) => run({ SPANBUSY: 1, MASKBIT: m as 0 | 1 }).wstb === 0) &&
        run({ SPANBUSY: 0 }).wstb === 0,
    "and none of it asserts WSTB - the register file is only written by the CPU")

  /* 13 pins WFG and WBG to $06 and $07 for exactly this reason: they must be
   * adjacent and differ in bit 0 alone, or the mask bit is not an address. */
  check((WFG ^ WBG) === 1 && (WFG & ~1) === (WBG & ~1),
    "13's WFG at A0 = 0 and WBG at A0 = 1 is a PLACEMENT RULE and this is it")

  /* ⭐ 7.2's column reload, which is the other thing this part does with the
   * file. vaddr walks RP1:RP0 through 01 and 10 at span end and this part
   * points the file at WPTR's own bytes for those two dots, so the counter
   * reloads through the load path the CPU's write already uses.
   * design-review2.md V-6. */
  const WPTRA = 0x08, WPTRB = 0x09
  check(run({ RP0: 1 }).ra === WPTRA,
    "⭐ reload dot 1 addresses WPTR's low byte at +$08", `${run({ RP0: 1 }).ra}`)
  check(run({ RP1: 1 }).ra === WPTRB,
    "⭐ and dot 2 its middle byte at +$09 - 7.2's two deferrable file reads",
    `${run({ RP1: 1 }).ra}`)
  check(run({ RP0: 1 }).wstb === 0 && run({ RP1: 1 }).wstb === 0,
    "and neither asserts WSTB - the reload READS the file")
  check(run({ SPANBUSY: 0, RP0: 0, RP1: 0 }).ra === SPANLEN,
    "and the walk returns the file to SPANLEN when it ends")
}

/* -- 4. the CPU wins the address while it is accessing the window --------- */
{
  /* Both can be true at once - a CPU register access during an idle fetch
   * phase - and the CPU's A[4:0] has to win, or the access reads the wrong
   * register. The equations are OR-of-products with !REGSEL on every
   * read-back term, so this is a real claim about that gating. */
  let bad: string | null = null
  for (let reg = 0; reg < 32 && !bad; reg++) {
    for (const busy of [0, 1] as const) {
      for (const mask of [0, 1] as const) {
        const r = run({
          IOSEL: 1, A6: 1, A5: 1, RW: 1, E: 1, SPANBUSY: busy, MASKBIT: mask,
          A0: (reg & 1) as 0 | 1, A1: ((reg >> 1) & 1) as 0 | 1, A2: ((reg >> 2) & 1) as 0 | 1,
          A3: ((reg >> 3) & 1) as 0 | 1, A4: ((reg >> 4) & 1) as 0 | 1,
        })
        if (r.ra !== reg) {
          bad = `+$${reg.toString(16)} with SPANBUSY=${busy} MASKBIT=${mask} -> RA=${r.ra}`
        }
      }
    }
  }
  check(bad === null,
    "a CPU access beats the span writer's own address, span running or not", bad ?? "")
}

/* ⭐ Twelve dedicated inputs (1-11, 13) and nothing on a macrocell pin: FP0 and
 * FP1 went, MASKBIT came, and the two strobes vctrl could not decode moved
 * here. Eight macrocells of ten, pins 22 and 23 free. */
{
  const widest = a.usage.reduce((m, u) => Math.max(m, u.used), 0)
  check(a.usage.length === 8,
    "⭐ eight macrocells of ten - WSTB, RA4..RA0, and CTRL's and VSTAT's write " +
    "strobes, which vctrl gave up the address lines to decode", `${a.usage.length}`)
  check(widest <= 16, "and the widest equation fits its macrocell", `${widest}`)
}
console.log(`\nrfa: ${a.usage.length} macrocells of 10, ` +
  `${rfaDesign.inputs.length} inputs on 12 dedicated pins`)
if (failures) { console.error(`\n${failures} FAILED`); process.exit(1) }
console.log("rfa OK")
