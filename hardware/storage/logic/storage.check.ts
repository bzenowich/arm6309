/* storage - the two GAL22V10s, against models written from the register map
 * rather than from the term lists.
 *   bun run storage/logic/storage.check.ts        (part of `npm run check`)
 *
 * sdbus is combinational and has fourteen inputs, so its sweep is exhaustive:
 * all 16,384. sdeng has state, so it is driven - the '393 and the '163 are
 * modelled here as the board wires them (sdcard.md §8 rows 4 and 5), and the
 * claims are about what the CARD does: eight clocks a burst and no more, a
 * clock that idles low, a byte latched before anything can read it, and a
 * trigger that arrives mid-burst being dropped rather than truncating one.
 *
 * ⚠ Both parts also go through Atmel's CUPL (cupl/*.cupl.jed) -
 * CLAUDE.md: a GAL does not ship without a second implementation.
 */

import { existsSync, readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { assemble, fuseChecksum, toJedec, toReport } from "../../tools/gal/jedec/assemble"
import { toGalPld } from "../../tools/gal/jedec/galpld"
import { Gal22v10, parseJedec } from "../../tools/gal/jedec/simulate"
import type { Design } from "../../tools/gal/jedec/assemble"
import { sdbusDesign } from "./sdbus.jedec"
import { sdengDesign } from "./sdeng.jedec"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

const here = new URL(".", import.meta.url).pathname
const build = (d: Design) => {
  const a = assemble(d)
  const jed = toJedec(d, a)
  writeFileSync(join(here, `${d.name}.jed`), jed)
  writeFileSync(join(here, `${d.name}.doc`), toReport(d, a))
  const pld = toGalPld(d)
  writeFileSync(join(here, `${d.name}.pld`), pld)
  const p = parseJedec(jed)
  check(p.declaredChecksum === fuseChecksum(p.fuses), `${d.name}: fuse checksum, and the file reads back as written`)
  check([...pld].every((c) => c.charCodeAt(0) < 128), `${d.name}.pld is 7-bit ASCII - CUPL's lexer is an MS-DOS program`)
  return { a, gal: new Gal22v10(p.fuses) }
}

/* pin state for a design, from signals in ASSERTED sense */
const pinsOf = (d: Design, v: Record<string, number>) =>
  Object.fromEntries(d.inputs.map((i) =>
    [i.pin, (i.activeLow ? 1 - (v[i.name] ?? 0) : (v[i.name] ?? 0)) as 0 | 1]))
const outsOf = (d: Design, g: Gal22v10, v: Record<string, number>) => {
  const p = g.evaluate(pinsOf(d, v))
  return Object.fromEntries(d.cells.map((c) =>
    [c.name, c.assertedLow ? 1 - p[c.pin] : p[c.pin]])) as Record<string, number>
}

/* ======================================================================== *
 * sdbus - exhaustive
 * ======================================================================== */
const B = build(sdbusDesign)
const BNAMES = sdbusDesign.inputs.map((i) => i.name)

/* the model: sdcard.md §6.1's decode and §6.2's four registers */
const sdbusModel = (v: Record<string, number>) => {
  const sel = v.IOSEL && v.A6 && !v.A5 && v.A4 && v.A3 && !v.A2
  const off = v.A1 * 2 + v.A0
  const rd = (n: number) => (sel && off === n && v.RW && v.E ? 1 : 0)
  const wr = (n: number) => (sel && off === n && !v.RW && v.E ? 1 : 0)
  return {
    DATSTB: sel && off === 0 && v.E ? 1 : 0,
    RDST: rd(1), CTRLW: wr(2), OE595: rd(0),
    MOSICK: wr(0) || wr(3) ? 1 : 0,
    SD0: v.BUSY | v.TRIGP, SD1: v.CD, SD2: v.WP,
  } as Record<string, number>
}

let bad: string | null = null
let drove = 0
for (let bits = 0; bits < 1 << BNAMES.length && !bad; bits++) {
  const v = Object.fromEntries(BNAMES.map((n, i) => [n, (bits >> i) & 1]))
  const g = outsOf(sdbusDesign, B.gal, v), m = sdbusModel(v)
  /* the three SDSTAT bits only mean anything while they are driven */
  const live = m.RDST ? Object.keys(m) : Object.keys(m).filter((k) => !k.startsWith("SD"))
  if (m.RDST) drove++
  for (const k of live) if (g[k] !== m[k]) { bad = `${k} at ${JSON.stringify(v)}: fuses ${g[k]}, model ${m[k]}`; break }
}
check(bad === null, "sdbus: the fuse map is the register map over all 16,384 inputs", bad ?? "")
check(drove > 0, "and SDSTAT is actually driven somewhere in the sweep - a vacuous OE would pass above", `${drove}`)

/* ⛔ §6.1's seven-bit decode, as its own claim: the card must be silent at
 * $FF18, which is $FF58 with A6 low and is inside the machine's free space. */
const at = (a: number, rw: number) => outsOf(sdbusDesign, B.gal, {
  IOSEL: 1, E: 1, RW: rw,
  A6: (a >> 6) & 1, A5: (a >> 5) & 1, A4: (a >> 4) & 1,
  A3: (a >> 3) & 1, A2: (a >> 2) & 1, A1: (a >> 1) & 1, A0: a & 1,
})
check(at(0x58, 1).OE595 === 1 && at(0x59, 1).RDST === 1 && at(0x5a, 0).CTRLW === 1,
  "sdbus: $FF58 reads data, $FF59 reads status, $FF5A writes control")
check([0x18, 0x19, 0x1a, 0x1b].every((a) =>
  at(a, 1).OE595 === 0 && at(a, 1).RDST === 0 && at(a, 0).CTRLW === 0 && at(a, 1).DATSTB === 0),
  "⛔ and it is SILENT at $FF18-$FF1B - the A6 literal §6.1 warns is a bug if it is missed")
check(at(0x58, 0).OE595 === 0 && at(0x58, 0).MOSICK === 1 && at(0x58, 0).DATSTB === 1,
  "a WRITE to SDDATA triggers a burst and loads MOSI, and the '595 stays off the bus")
check(at(0x5b, 0).MOSICK === 1 && at(0x5b, 0).DATSTB === 0,
  "§6.2: SDMOSI loads the hold register WITHOUT a burst")

/* ======================================================================== *
 * sdeng - driven, with the '393 and the '163 modelled as the board wires them
 * ======================================================================== */
const E = build(sdengDesign)

interface World {
  /* the '393, counting CLK25 (§8 row 5) */
  div: number
  /* the '163: /CLR wired to BUSY, so it is held at zero while idle */
  cnt: number
  spiPrev: number
  /* what the card's SCK pin has done */
  edges: number
  sck: number
  /* the '595's storage register loads on RCLK's rising edge */
  rclk: number
  latched: number
  busy: number
}

const fresh = (): World => ({ div: 0, cnt: 0, spiPrev: 0, edges: 0, sck: 0, rclk: 1, latched: 0, busy: 0 })

/* one CLK25 tick: read the part, run the board, then clock the part */
const tick = (w: World, v: Record<string, number>) => {
  const div2 = (w.div >> 0) & 1, div64 = (w.div >> 5) & 1
  const inp = { ...v, DIV2: div2, DIV64: div64, CNT8: (w.cnt >> 3) & 1 }
  const o = outsOf(sdengDesign, E.gal, inp)

  /* the card's SCK, and the '163 that counts it */
  if (o.SCK && !w.sck) w.edges++
  if (o.SPICLK && !w.spiPrev) w.cnt = o.BUSY ? (w.cnt + 1) & 15 : 0
  w.spiPrev = o.SPICLK
  w.sck = o.SCK
  /* the '595's storage register - RCLK is released at the end of a burst */
  if (o.RCLK && !w.rclk) w.latched++
  w.rclk = o.RCLK
  w.busy = o.BUSY

  E.gal.clock(pinsOf(sdengDesign, inp))
  w.div = (w.div + 1) & 63
  return o
}

const run = (w: World, n: number, v: Record<string, number>) => {
  let last: Record<string, number> = {}
  for (let i = 0; i < n; i++) last = tick(w, v)
  return last
}

/* --- a burst at full speed ------------------------------------------------ */
{
  const w = fresh()
  const idle = { RESET: 0, CTRLW: 0, DATSTB: 0, D0: 0, D1: 0, D7: 0 }
  /* out of reset, then select the card and the fast clock: SDCTRL = $03 */
  run(w, 4, { ...idle, RESET: 1 })
  run(w, 3, { ...idle, CTRLW: 1, D0: 1, D1: 1 })
  const armed = run(w, 3, idle)
  check(armed.CS === 1 && armed.FAST === 1, "sdeng: SDCTRL takes b0 and b1 from the bus on CTRLW")

  const before = w.edges
  /* one SDDATA access: DATSTB high through E-high, then away */
  run(w, 6, { ...idle, DATSTB: 1 })
  run(w, 40, idle)
  check(w.edges - before === 8, "⭐ one SDDATA access is EXACTLY eight SCK edges", `${w.edges - before}`)
  check(w.latched === 1, "and the '595's storage register is clocked once, at the end", `${w.latched}`)
  check(w.busy === 0, "and BUSY has fallen by 40 ticks - a burst is 636 ns, not a bus cycle")

  /* ⚠ the claim two of this repository's traps are about: nothing more
   * happens on its own. A free-running trigger would show here. */
  const after = w.edges
  run(w, 200, idle)
  check(w.edges === after, "⛔ and NOTHING further clocks with the bus idle - the trigger is an edge", `${w.edges - after}`)
}

/* --- the clock idles low, which is SPI mode 0 ----------------------------- */
{
  const w = fresh()
  const idle = { RESET: 0, CTRLW: 0, DATSTB: 0, D0: 0, D1: 0, D7: 0 }
  run(w, 4, { ...idle, RESET: 1 })
  run(w, 3, { ...idle, CTRLW: 1, D0: 1, D1: 1 })
  let high = 0
  for (let i = 0; i < 60; i++) if (tick(w, idle).SCK) high++
  check(high === 0, "sdeng: SCK idles LOW between bursts - SPI mode 0", `${high} ticks high`)
}

/* --- §6.5: a trigger during a burst is dropped, not truncating ------------ */
{
  const w = fresh()
  const idle = { RESET: 0, CTRLW: 0, DATSTB: 0, D0: 0, D1: 0, D7: 0 }
  run(w, 4, { ...idle, RESET: 1 })
  run(w, 3, { ...idle, CTRLW: 1, D0: 1, D1: 1 })
  run(w, 3, idle)
  const before = w.edges
  run(w, 6, { ...idle, DATSTB: 1 })
  /* a second access two ticks later, while the first burst is still running */
  run(w, 2, idle)
  run(w, 6, { ...idle, DATSTB: 1 })
  run(w, 60, idle)
  check(w.edges - before === 8,
    "⛔ §6.5: an access DURING a burst neither truncates it nor adds clocks - the '163's clear is wired to BUSY",
    `${w.edges - before} edges`)
}

/* --- the init rate, and that it is the one /RESET leaves behind ----------- */
{
  const w = fresh()
  const idle = { RESET: 0, CTRLW: 0, DATSTB: 0, D0: 0, D1: 0, D7: 0 }
  const o = run(w, 4, { ...idle, RESET: 1 })
  check(o.CS === 0 && o.FAST === 0,
    "§6.4: /RESET forces SDCTRL to $00 - /CS released and the 393 kHz init clock")
  /* select the card but leave the slow clock: a burst is 64x longer */
  run(w, 3, { ...idle, CTRLW: 1, D0: 1 })
  const before = w.edges
  run(w, 6, { ...idle, DATSTB: 1 })
  run(w, 200, idle)
  check(w.edges - before < 8 && w.busy === 1,
    "at the init rate a burst is 20.4 us - still running after 200 CLK25, which is why §6.3's BUSY exists",
    `${w.edges - before} edges, BUSY ${w.busy}`)
  run(w, 400, idle)
  check(w.edges - before === 8 && w.busy === 0, "and it completes in eight, slowly", `${w.edges - before}`)
}

/* --- the soft reset, SDCTRL b7 -------------------------------------------- */
{
  const w = fresh()
  const idle = { RESET: 0, CTRLW: 0, DATSTB: 0, D0: 0, D1: 0, D7: 0 }
  run(w, 4, { ...idle, RESET: 1 })
  run(w, 3, { ...idle, CTRLW: 1, D0: 1 })      /* selected, slow clock */
  run(w, 6, { ...idle, DATSTB: 1 })
  run(w, 80, idle)
  check(w.busy === 1, "a slow burst is in flight")
  run(w, 3, { ...idle, CTRLW: 1, D7: 1 })
  const o = run(w, 2, idle)
  check(o.BUSY === 0, "⭐ SDCTRL b7 clears BUSY, and the '163 with it - the card that was swapped, §9.3")
}

/* ======================================================================== *
 * the second implementation
 * ======================================================================== */
for (const { d, gal } of [{ d: sdbusDesign, gal: B.gal }, { d: sdengDesign, gal: E.gal }]) {
  const ref = join(here, "cupl", `${d.name}.cupl.jed`)
  if (!existsSync(ref)) {
    check(false, `CUPL's ${d.name}.cupl.jed exists`,
      `run tools/gal/prjbureau/cupl-reference.sh storage/logic/${d.name}.pld`)
    continue
  }
  const cupl = new Gal22v10(parseJedec(readFileSync(ref, "latin1")).fuses)
  const n = d.inputs.length
  const registered = d.cells.some((c) => c.registered)
  let diff: string | null = null

  if (!registered) {
    /* combinational: the sweep IS the equivalence */
    for (let bits = 0; bits < 1 << n && !diff; bits++) {
      const v = Object.fromEntries(d.inputs.map((i, k) => [i.name, (bits >> k) & 1]))
      const ours = gal.evaluate(pinsOf(d, v)), theirs = cupl.evaluate(pinsOf(d, v))
      for (const c of d.cells) if (ours[c.pin] !== theirs[c.pin]) {
        diff = `${c.name} at ${bits.toString(2).padStart(n, "0")}: ours ${ours[c.pin]}, CUPL ${theirs[c.pin]}`
        break
      }
    }
    check(diff === null, `CUPL ${d.name}.jed: matches our fuse map over all ${1 << n} inputs`, diff ?? "")
    continue
  }

  /* ⛔ A REGISTERED PART CANNOT BE COMPARED A VECTOR AT A TIME, and the first
   * version of this file tried: `evaluate()` reads whatever state the part is
   * already in, so ours - clocked through every sequence above - disagreed
   * with a CUPL part fresh out of its constructor on SPQ, and the mismatch
   * was the harness's, not the design's. Reset both, then drive them in
   * lockstep and compare every pin at every step. */
  const both = (v: Record<string, number>) => [gal, cupl].map((g) => g.evaluate(pinsOf(d, v)))
  const clockBoth = (v: Record<string, number>) => {
    for (const g of [gal, cupl]) g.clock(pinsOf(d, v))
  }
  const held = Object.fromEntries(d.inputs.map((i) => [i.name, 0]))
  for (let i = 0; i < 4; i++) clockBoth({ ...held, RESET: 1 })

  /* an LCG, so the walk is the same on every run and a failure is a fixture */
  let seed = 0x5deadbee
  const rnd = () => (seed = (seed * 1103515245 + 12345) >>> 0) >>> 16
  for (let step = 0; step < 20000 && !diff; step++) {
    const v = Object.fromEntries(d.inputs.map((i, k) => [i.name, (rnd() >> (k % 15)) & 1]))
    const [ours, theirs] = both(v)
    for (const c of d.cells) if (ours[c.pin] !== theirs[c.pin]) {
      diff = `${c.name} at step ${step}, ${JSON.stringify(v)}: ours ${ours[c.pin]}, CUPL ${theirs[c.pin]}`
      break
    }
    clockBoth(v)
  }
  check(diff === null,
    `CUPL ${d.name}.jed: matches our fuse map over 20,000 clocked steps from a common reset`, diff ?? "")
}

for (const { d, a } of [{ d: sdbusDesign, a: B.a }, { d: sdengDesign, a: E.a }]) {
  console.log(`      ${d.partNo} ${d.name}  ${a.usage.filter((u) => u.pin >= 14).length} macrocells of 10, ` +
              `${d.inputs.length} inputs`)
}
console.log(`\n${failures === 0 ? "0 failed" : `${failures} FAILED`}`)
process.exit(failures === 0 ? 0 : 1)
