/* Assemble the video card's sync trio and check the fuses over whole frames.
 *
 * graphics.md 19 item 8 says the sync pair does not fit - 24 macrocells
 * wanted against 20 - and offers three escapes, "one of which must be chosen
 * at fit time". This is fit time. It reports which escape is forced and why
 * the first one listed cannot be taken, and then it runs the raster.
 *
 *   npm run check:sync
 */

import { writeFileSync } from "node:fs"
import { join } from "node:path"

import { assemble, fuseChecksum, toJedec, toReport, type Design } from "./jedec/assemble"
import { Gal22v10, parseJedec } from "./jedec/simulate"
import { OLMC } from "./jedec/gal22v10"
import { hgenDesign, vgenDesign, vdecDesign } from "./sync.jedec"
import { H, V449, V525 } from "./sync.timing"
import { RESET_STATE, frameFacts, outputs, step, type SyncState } from "./sync.model"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

const here = new URL(".", import.meta.url).pathname

const build = (design: Design, base: string) => {
  const a = assemble(design)
  const jed = toJedec(design, a)
  writeFileSync(join(here, `${base}.jed`), jed)
  writeFileSync(join(here, `${base}.doc`), toReport(design, a))
  const parsed = parseJedec(jed)
  check(parsed.declaredChecksum === fuseChecksum(parsed.fuses),
    `${base}: fuse checksum, and the file reads back as written`)
  return { design, assembly: a, gal: new Gal22v10(parsed.fuses) }
}

console.log("The three parts, and what each one costs\n")
const hgen = build(hgenDesign, "hgen")
const vgen = build(vgenDesign, "vgen")
const vdec = build(vdecDesign, "vdec")

/* -- the fit, which is what item 8 asks for ------------------------------ */
{
  const used = [hgen, vgen, vdec].reduce((n, p) => n + p.assembly.usage.length, 0)
  check(used === 27, `27 macrocells across three parts, not item 8's 24`, `${used}`)
  for (const p of [hgen, vgen, vdec]) {
    const over = p.assembly.usage.filter((u) => u.used > u.available)
    check(over.length === 0, `${p.design.name}: every equation fits its macrocell`,
      over.map((u) => `${u.name} ${u.used}/${u.available}`).join(", "))
  }
  /* vgen is the one with nothing left. Bit i of a ten-bit counter behind a
   * six-literal clock enable is i + 7 product terms, so the bits need
   * 7..16 and the part offers 8,10,12,14,16,16,14,12,10,8. Sorted pairing is
   * the only assignment that fits, and V9 lands on 16 of 16. */
  const v9 = vgen.assembly.usage.find((u) => u.name === "V9")!
  check(v9.used === v9.available && v9.used === 16,
    "vgen has no slack at all: V9 is 16 product terms in a 16-term macrocell",
    `${v9.used}/${v9.available}`)
  const tight = vgen.assembly.usage.filter((u) => u.available - u.used > 1)
  check(tight.length === 0,
    "every vgen macrocell is at its limit or one below it", `${tight.length} looser`)

  /* vdec's constraint is pins, not terms - which is the thing item 8's
   * arithmetic could not see, because it counted macrocells only. */
  const free = 10 - vdec.assembly.usage.length
  check(vdec.design.inputs.length === 11 + free,
    "vdec uses every pin it has: 11 dedicated inputs plus its 3 free macrocells",
    `${vdec.design.inputs.length} inputs, ${11 + free} available`)
}

/* -- the escape item 8 lists first, and why it is not available ----------- */
{
  /* "Move the 8-bit H slot counter into a '393 + compare terms (+1 IC)". It
   * frees eight macrocells, so on macrocell count it looks like the cheapest
   * of the three. But then one part has to decode both counters, and a
   * 22V10 does not have the pins:
   *
   *     h[7:0] + v[9:0] + VMODE0 + HPOL + IRQEN + VSTATWR  = 22 inputs
   *     a 22V10 with the six decode outputs               = 16 available
   *
   * Splitting the decodes across two parts to fix that means two GALs plus
   * the external counter, which is worse than the three GALs it was trying to
   * avoid. */
  const decodeOutputs = 6
  const needed = 8 + 10 + 4
  const available = 12 + (10 - decodeOutputs)
  check(needed > available,
    "escape 1 (H counter off-chip) is pin-bound, not macrocell-bound - it does not work",
    `${needed} inputs needed, ${available} available`)
}

/* -- the raster ---------------------------------------------------------- */
const P = { CE: 2, RESET: 3, HPOL: 4 } as const
const HPIN = [14, 15, 16, 17, 18, 19, 20, 21] // hgen H0..H7
const VPIN = [14, 23, 15, 22, 16, 21, 17, 20, 18, 19] // vgen V0..V9, sorted-fit order

const readBits = (pins: Int8Array, map: number[]) =>
  map.reduce((n, pin, i) => n | (pins[pin] << i), 0)

for (const m0 of [0, 1] as const) {
  const f = m0 ? V525 : V449
  const facts = frameFacts(m0)

  /* Reset all three. vdec has no reset pin - the 22V10 powers its registers
   * up low and CTRL comes up with IRQEN clear, which is the argument for not
   * spending the pin. */
  hgen.gal.evaluate({ [P.CE]: 1, [P.RESET]: 0, [P.HPOL]: 1 })
  hgen.gal.reset(); vgen.gal.reset(); vdec.gal.reset()

  let model: SyncState = { ...RESET_STATE }
  let bad: string | null = null
  let activeSlots = 0, activeLines = 0, syncLines = 0, irqEdges = 0
  let prevIrq: number = -1
  const seenVsync = new Set<number>()

  /* One whole frame, at the slot rate. CE gating is checked separately
   * below; here CE is held so a step is a slot and a frame is 200 x lines. */
  const steps = facts.lines * (H.last + 1)
  for (let i = 0; i < steps && !bad; i++) {
    const hPins = hgen.gal.evaluate({ [P.CE]: 1, [P.RESET]: 1, [P.HPOL]: 1 })
    const h = readBits(hPins, HPIN)
    const hblank = hPins[23] as 0 | 1

    const vPinsNow = vgen.gal.evaluate({
      2: 1, 3: 1, 4: 0, 5: (h & 1) as 0 | 1, 6: ((h >> 1) & 1) as 0 | 1,
      7: ((h >> 2) & 1) as 0 | 1, 8: ((h >> 6) & 1) as 0 | 1, 9: ((h >> 7) & 1) as 0 | 1,
    })
    const v = readBits(vPinsNow, VPIN)

    const dIn: Record<number, 0 | 1> = { 2: m0, 3: hblank, 4: 1, 5: 0 }
    for (let b = 0; b <= 6; b++) dIn[6 + b] = ((v >> b) & 1) as 0 | 1
    dIn[13] = ((v >> 6) & 1) as 0 | 1
    dIn[6] = (v & 1) as 0 | 1; dIn[7] = ((v >> 1) & 1) as 0 | 1
    dIn[8] = ((v >> 2) & 1) as 0 | 1; dIn[9] = ((v >> 3) & 1) as 0 | 1
    dIn[10] = ((v >> 4) & 1) as 0 | 1; dIn[11] = ((v >> 5) & 1) as 0 | 1
    dIn[14] = ((v >> 7) & 1) as 0 | 1; dIn[15] = ((v >> 8) & 1) as 0 | 1
    dIn[23] = ((v >> 9) & 1) as 0 | 1
    const dPins = vdec.gal.evaluate(dIn)

    const want = outputs(model, { m0, hpol: 1, irqen: true })
    const got = {
      h, v,
      hsync: hPins[22], hblank, vsync: dPins[19], vblank: dPins[18],
      blank: dPins[17], vtc: dPins[16], irq: dPins[22],
    }
    if (got.h !== model.h || got.v !== model.v) {
      bad = `step ${i}: counters are h=${got.h} v=${got.v}, model says h=${model.h} v=${model.v}`
      break
    }
    for (const k of ["hsync", "hblank", "vsync", "vblank", "blank", "vtc", "irq"] as const) {
      if (got[k] !== want[k]) {
        bad = `${k} = ${got[k]}, expected ${want[k]} at line ${model.v} slot ${model.h}`
      }
    }
    if (bad) break

    if (!got.blank) activeSlots++
    /* /IRQ is a latched level, not a pulse: it asserts once and stays until
     * software writes VSTAT. What must happen once per frame is the EDGE. */
    if (got.irq === 0 && prevIrq !== 0) irqEdges++
    prevIrq = got.irq
    if (got.h === 0) {
      if (!got.vblank) activeLines++
      if (m0 ? got.vsync === 0 : got.vsync === 1) { syncLines++; seenVsync.add(model.v) }
    }

    /* Clock all three from the pre-edge values, which is what the silicon
     * does: every register on all three parts is on the same 25.175 MHz pin
     * 1, and vgen's line advance is hgen's terminal count read as a level. */
    hgen.gal.clock({ [P.CE]: 1, [P.RESET]: 1, [P.HPOL]: 1 })
    vgen.gal.clock({
      2: 1, 3: 1, 4: dPins[16] as 0 | 1, 5: (h & 1) as 0 | 1,
      6: ((h >> 1) & 1) as 0 | 1, 7: ((h >> 2) & 1) as 0 | 1,
      8: ((h >> 6) & 1) as 0 | 1, 9: ((h >> 7) & 1) as 0 | 1,
    })
    vdec.gal.clock(dIn)
    model = step(model, { ce: true, m0, vstatwr: false })
  }

  const label = `${f.lines}-line`
  check(bad === null, `${label}: the fuse maps match sync.model.ts for a whole frame ` +
    `(${steps.toLocaleString()} slots)`, bad ?? "")
  if (bad === null) {
    check(model.h === 0 && model.v === 0, `${label}: the raster closes - one frame returns to 0,0`,
      `h=${model.h} v=${model.v}`)
    check(activeSlots === facts.activeLines * facts.activeSlots,
      `${label}: ${facts.activeLines} x ${facts.activeSlots} unblanked slots = ` +
      `${(facts.activeLines * facts.activeSlots * 4).toLocaleString()} pixels`,
      `${activeSlots}`)
    check(activeLines === facts.activeLines, `${label}: ${facts.activeLines} active lines`, `${activeLines}`)
    check(syncLines === facts.syncLines,
      `${label}: VSYNC asserted for ${facts.syncLines} lines, ` +
      `${facts.vsyncPositive ? "positive" : "negative"} - which is how the monitor picks the format`,
      `${syncLines}`)
    check(irqEdges === 1, `${label}: /IRQ asserts exactly once per frame`, `${irqEdges}`)
  }
}

/* -- the flag is an edge, which is the whole reason VSDLY exists ---------- */
{
  /* Clear VSTAT from inside the sync window - which is where a 70 Hz handler
   * actually runs, since the 6809 takes about 10 us to enter an interrupt and
   * the window is 63.5 us. If VBLPEND were the level rather than its leading
   * edge, the flag would re-assert under the handler and the frame would
   * interrupt twice, or forever. */
  hgen.gal.reset(); vgen.gal.reset(); vdec.gal.reset()
  const vd = (v: number, wr: 0 | 1, m0: 0 | 1 = 0): Record<number, 0 | 1> => ({
    2: m0, 3: 0, 4: 1, 5: wr,
    6: (v & 1) as 0 | 1, 7: ((v >> 1) & 1) as 0 | 1, 8: ((v >> 2) & 1) as 0 | 1,
    9: ((v >> 3) & 1) as 0 | 1, 10: ((v >> 4) & 1) as 0 | 1, 11: ((v >> 5) & 1) as 0 | 1,
    13: ((v >> 6) & 1) as 0 | 1, 14: ((v >> 7) & 1) as 0 | 1,
    15: ((v >> 8) & 1) as 0 | 1, 23: ((v >> 9) & 1) as 0 | 1,
  })
  /* line 0: the edge sets the flag */
  vdec.gal.clock(vd(0, 0))
  check(vdec.gal.evaluate(vd(0, 0))[22] === 0, "VBL: /IRQ asserts on entering the sync window")
  /* still inside the window, software clears it */
  vdec.gal.clock(vd(0, 1))
  check(vdec.gal.evaluate(vd(0, 0))[22] === -1, "VBL: a VSTAT write clears /IRQ")
  /* and it must NOT come back while the window is still open */
  let rearmed = false
  for (let i = 0; i < 20; i++) {
    vdec.gal.clock(vd(i < 10 ? 0 : 1, 0))
    if (vdec.gal.evaluate(vd(i < 10 ? 0 : 1, 0))[22] === 0) rearmed = true
  }
  check(!rearmed, "VBL: /IRQ does not re-arm under its own handler, which is what VSDLY buys")
}

/* -- CE actually gates ---------------------------------------------------- */
{
  hgen.gal.reset()
  let advanced = 0
  for (let i = 0; i < 40; i++) {
    const before = readBits(hgen.gal.evaluate({ [P.CE]: 0, [P.RESET]: 1, [P.HPOL]: 1 }), HPIN)
    hgen.gal.clock({ [P.CE]: 0, [P.RESET]: 1, [P.HPOL]: 1 })
    const after = readBits(hgen.gal.evaluate({ [P.CE]: 0, [P.RESET]: 1, [P.HPOL]: 1 }), HPIN)
    if (after !== before) advanced++
  }
  check(advanced === 0, "the slot counter does not move while CE is low - 3 dots in 4")
}

console.log("\nThe fit, which is what item 8 asked for\n")
for (const p of [hgen, vgen, vdec]) {
  const free = 10 - p.assembly.usage.length
  console.log(`      ${p.design.partNo}  ${p.design.name.padEnd(5)} ` +
    `${p.assembly.usage.length} outputs, ${free} macrocell${free === 1 ? "" : "s"} free, ` +
    `${p.design.inputs.length} of ${11 + free} inputs used`)
  for (const u of [...p.assembly.usage].sort((a, b) => a.pin - b.pin)) {
    console.log(`        pin ${String(u.pin).padStart(2)}  ${u.name.padEnd(8)} ` +
      `${String(u.used).padStart(2)}/${String(u.available).padEnd(2)}` +
      `${u.used === u.available ? "  full" : ""}`)
  }
}

console.log(failures === 0
  ? "\nThe sync trio assembles, fits, and runs a correct raster in both families"
  : `\n${failures} FAILED`)
if (failures) process.exit(1)
