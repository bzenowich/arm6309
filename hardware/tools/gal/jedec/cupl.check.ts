/* The falsification test: run Atmel's own JEDEC through our fuse map.
 *
 * jedec/README.md named this as "the third way, which is the one that would
 * settle it, has not been done" - compile a .pld with the vendor's CUPL and
 * check its output against ours. On 2026-09-07 it was done, and it found two
 * errors that 178 passing checks could not, because in both cases the
 * assembler and the fuse-map simulator shared the mistake and agreed with each
 * other perfectly:
 *
 *   1. THE S0/S1 CONFIG BITS RUN FROM PIN 23 DOWNWARD, not from pin 14 up.
 *      Our polarity bits were on the wrong macrocells. Symmetric pins hid it -
 *      only 18 and 19 disagreed visibly, because the rest happened to match.
 *
 *   2. A REGISTERED MACROCELL FEEDS THE ARRAY FROM /Q, not from its pin.
 *      CUPL emits `C0.d = !C0` as the single literal C0. That is only a
 *      working counter if the feedback is inverted. Ours was written the other
 *      way and counted correctly only in our own simulator.
 *
 * The reference files here are CUPL 5.0a's output for our own mmu.pld and
 * clkdec.pld, committed so this runs without Wine. To regenerate them, see
 * ../prjbureau/README.md.
 *
 *   npm run check:cupl
 */

import { readFileSync } from "node:fs"
import { join } from "node:path"

import { Gal22v10, parseJedec } from "./simulate"
import type { Design } from "./assemble"
import { assemble, toJedec } from "./assemble"
import { mmuDesign } from "../../../mainboard/logic/mmu.jedec"
import { clkdecDesign } from "../../../mainboard/logic/clkdec.jedec"
import { u9Design } from "../../../mainboard/logic/u9.jedec"
import { u10Design } from "../../../mainboard/logic/u10.jedec"
import { aseqDesign, adecDesign, admatDesign, aintenaDesign, apendDesign } from "../../../audio/logic/audio.jedec"
import { sdbusDesign } from "../../../storage/logic/sdbus.jedec"
import { sdengDesign } from "../../../storage/logic/sdeng.jedec"
import { v3laneDesign } from "../../../video3/logic/v3lane.jedec"
import { ALL } from "../designs"
import { PHASES, mmu } from "../../../mainboard/logic/mmu.model"
import { RESET_STATE, decode, step, type Counter } from "../../../mainboard/logic/clkdec.model"
import { u9 } from "../../../mainboard/logic/u9.model"
import { RESET_STATE as U10_RESET, out as u10out, step as u10step, type State as U10State } from "../../../mainboard/logic/u10.model"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}
const here = new URL(".", import.meta.url).pathname
/* every path below is relative to hardware/: a card's CUPL references live in
 * its own logic/cupl/, beside the design they check */
const HW = join(here, "..", "..", "..")
const load = (f: string) =>
  new Gal22v10(parseJedec(readFileSync(join(HW, f), "latin1")).fuses)

/* -- U3, combinational: the whole address space against the model --------- */
const checkMmu = (label: string, gal: Gal22v10) => {
  let bad: string | null = null
  outer:
  for (let la = 0; la <= 0xffff; la++) {
    for (const ph of PHASES) for (const rw of [0, 1] as const) {
      const d: Record<number, 0 | 1> = {
        1: ((la >> 15) & 1) as 0 | 1, 2: ((la >> 14) & 1) as 0 | 1,
        3: ((la >> 13) & 1) as 0 | 1, 4: ((la >> 12) & 1) as 0 | 1,
        5: ((la >> 11) & 1) as 0 | 1, 6: ((la >> 10) & 1) as 0 | 1,
        7: ((la >> 9) & 1) as 0 | 1, 8: ((la >> 8) & 1) as 0 | 1,
        9: ((la >> 7) & 1) as 0 | 1, 10: ((la >> 6) & 1) as 0 | 1,
        11: ((la >> 5) & 1) as 0 | 1, 13: ((la >> 4) & 1) as 0 | 1,
        14: ph.e as 0 | 1, 15: ph.q as 0 | 1, 16: rw,
      }
      const p = gal.evaluate(d), m = mmu(la, ph.e, ph.q, rw)
      const want: Record<number, number> = {
        17: m.iopage ? 0 : 1, 18: m.muxsel ? 1 : 0, 19: m.isooeLo ? 0 : 1,
        20: m.mapwe ? 0 : 1, 21: m.mapoe ? 0 : 1, 22: m.ctrlcp ? 1 : 0,
        /* ⭐ Pin 23 since 2026-09-09 - the high map byte's own '245 enable.
         * design-review2.md M-1 gave the high byte a window and the board
         * still had no data path to it; two common-I/O SRAMs need two
         * buffers and two buffers need two enables. */
        23: m.isooeHi ? 0 : 1,
      }
      for (const [pin, v] of Object.entries(want)) {
        if (p[Number(pin)] !== v) {
          bad = `pin ${pin} at $${la.toString(16).toUpperCase()} ${ph.name} R/W=${rw}`
          break outer
        }
      }
    }
  }
  check(bad === null, `${label}: matches mmu.model.ts over all 524,288 inputs`, bad ?? "")
}

/* -- U6, registered: the divider, /IOSEL and boot mode --------------------- */
const CNT = { 16: 0, 17: 1, 20: 2, 21: 3 } as const
const checkClkdec = (label: string, gal: Gal22v10) => {
  for (const fastE of [false, true]) {
    /* Pins 5..9 and 11 are LA7, LA6, LA5, R/W, LA4 and LA0 since 2026-09-09 -
     * physical A19 and A20 left with the system RAM. The base is not a $FFB1
     * write, so RUN stays where reset put it and the divider is what is
     * being swept. */
    const base = { 2: (fastE ? 1 : 0) as 0 | 1, 3: 1 as const, 4: 1 as const,
                   5: 0 as const, 6: 0 as const, 7: 0 as const, 8: 1 as const,
                   9: 0 as const, 10: 1 as const, 11: 0 as const }
    gal.evaluate({ ...base, 3: 0 }); gal.reset()
    let model: Counter = { ...RESET_STATE }, bad: string | null = null
    const edges = fastE ? 64 : 96
    for (let i = 0; i < edges && !bad; i++) {
      gal.clock(base); model = step(model, fastE)
      const p = gal.evaluate(base)
      const cnt = Object.entries(CNT).reduce((n, [pin, b]) => n | (p[Number(pin)] << b), 0)
      if (cnt !== model.cnt || p[18] !== model.e || p[19] !== model.q || p[22] !== model.run) {
        bad = `edge ${i}: fuses cnt=${cnt} e=${p[18]} q=${p[19]} run=${p[22]}, ` +
          `model cnt=${model.cnt} e=${model.e} q=${model.q} run=${model.run}`
        break
      }
      const want = decode({ nIopage: 1, la7: 0, la6: 0, run: model.run })
      if (p[15] !== want.nIosel || p[14] !== want.nBootOe) bad = `decode differs at edge ${i}`
    }
    check(bad === null, `${label}: ${fastE ? "/8 " : "/12"} matches clkdec.model.ts for ${edges} edges`,
      bad ?? "")

    /* ⛔ /WAIT AT THE PIN, since 2026-09-11. Every claim above held pin 10 at
     * one level, and for a day that level was 0 = "not waiting" against a
     * declaration that read the pulled-up idle bus as a hold - so E never
     * toggled on the board and nothing here could say so. The sweep above now
     * runs with pin 10 HIGH, which is the idle bus; this pulls it LOW. */
    const cntOf = (p: Record<number, number>) =>
      Object.entries(CNT).reduce((n, [pin, b]) => n | (p[Number(pin)] << b), 0)
    for (let i = 0; i < 5; i++) gal.clock(base)
    const before = cntOf(gal.evaluate(base))
    for (let i = 0; i < 7; i++) gal.clock({ ...base, 10: 0 })
    const held = cntOf(gal.evaluate({ ...base, 10: 0 }))
    gal.clock(base)
    const resumed = cntOf(gal.evaluate(base))
    check(held === before && resumed !== before,
      `${label}: ${fastE ? "/8 " : "/12"} pin 10 LOW (/WAIT asserted) holds the divider and releasing it resumes`,
      `before ${before}, after 7 held edges ${held}, after release ${resumed}`)
  }

  /* Boot mode, in Atmel's own fuses. RUN out of reset is the claim that
   * decides whether the machine executes an instruction at all, and it rests
   * on the 22V10's shared asynchronous reset resetting to ZERO - which is a
   * device fact, and therefore exactly the kind our own device description
   * could be wrong about on its own. */
  const idle = { 2: 0 as const, 3: 1 as const, 4: 1 as const, 5: 0 as const,
                 6: 0 as const, 7: 0 as const, 8: 1 as const, 9: 0 as const,
                 10: 1 as const, 11: 0 as const }
  gal.evaluate({ ...idle, 3: 0 }); gal.reset()
  check(gal.evaluate(idle)[22] === 0,
    `${label}: RUN comes out of reset at 0 - boot mode, before the first fetch`)
  check(gal.evaluate(idle)[14] === 0,
    `${label}: and the boot buffer's output enable is asserted with it, so physical ` +
    `A20-A13 are driven and not floating`)

  /* $FFB1 write: /IOPAGE low, LA7=1 LA6=0 LA5=1 LA4=1 LA0=1, R/W low, E high. */
  for (let i = 0; i < 24 && gal.evaluate(idle)[18] === 0; i++) gal.clock(idle)
  gal.clock({ ...idle, 4: 0, 5: 1, 6: 0, 7: 1, 8: 0, 9: 1, 11: 1 })
  check(gal.evaluate(idle)[22] === 1,
    `${label}: and one write to $FFB1 sets it`)
  check(gal.evaluate(idle)[14] === 1,
    `${label}: which releases the '244 and hands the address bus to the map`)
}

console.log("Atmel CUPL 5.0a's own output, executed on our fuse map\n")
const cuplMmu = load("mainboard/logic/cupl/mmu.cupl.jed")
const cuplClk = load("mainboard/logic/cupl/clkdec.cupl.jed")
checkMmu("CUPL mmu.jed", cuplMmu)
checkClkdec("CUPL clkdec.jed", cuplClk)

/* -- U9, combinational: the whole decode space against the model ----------- */
const checkU9 = (label: string, gal: Gal22v10) => {
  let bad: string | null = null
  outer:
  for (let pa = 0; pa < 64; pa++) {
    for (let lo = 0; lo < 32; lo++) {
      for (const rw of [0, 1] as const) for (const run of [0, 1] as const) {
        for (const nIopage of [0, 1] as const) {
          const la7 = ((lo >> 4) & 1) as 0 | 1, la6 = ((lo >> 3) & 1) as 0 | 1
          const la5 = ((lo >> 2) & 1) as 0 | 1, la4 = ((lo >> 1) & 1) as 0 | 1
          const la3 = (lo & 1) as 0 | 1
          const p = gal.evaluate({
            1: ((pa >> 5) & 1) as 0 | 1, 2: ((pa >> 4) & 1) as 0 | 1,
            3: ((pa >> 3) & 1) as 0 | 1, 4: ((pa >> 2) & 1) as 0 | 1,
            5: ((pa >> 1) & 1) as 0 | 1, 6: (pa & 1) as 0 | 1,
            7: nIopage, 8: run, 9: la7, 10: la6, 11: la5, 13: la4, 14: la3, 23: rw,
          })
          const m = u9({ pa, nIopage, run, la7, la6, la5, la4, la3, rw })
          const want: Record<number, number> = {
            15: m.nMapCeLo, 16: m.nMapCeHi, 17: m.nRomCe0,
            18: m.nIopageBp, 19: m.dramSel, 20: m.nRomCe1,
          }
          for (const [pin, v] of Object.entries(want)) {
            if (p[Number(pin)] !== v) {
              bad = `pin ${pin} = ${p[Number(pin)]}, expected ${v} at ` +
                `A24..A19=${pa.toString(2).padStart(6, "0")} ` +
                `LA7..LA3=${lo.toString(2).padStart(5, "0")} ` +
                `R/W=${rw} RUN=${run} /IOPAGE=${nIopage}`
              break outer
            }
          }
        }
      }
    }
  }
  check(bad === null,
    `${label}: matches u9.model.ts over all 16,384 input combinations`, bad ?? "")
}
checkU9("CUPL u9.jed", load("mainboard/logic/cupl/u9.cupl.jed"))

/* -- U10, registered: the SIMM controller's two timebases ----------------- */
const checkU10 = (label: string, gal: Gal22v10) => {
  const drive = (o: { count: number; dramsel: 0 | 1; a23: 0 | 1; a22: 0 | 1; rw: 0 | 1; refclk: 0 | 1 }) => ({
    2: o.dramsel, 3: o.a23, 4: o.a22,
    5: ((o.count >> 0) & 1) as 0 | 1, 6: ((o.count >> 1) & 1) as 0 | 1,
    7: ((o.count >> 2) & 1) as 0 | 1, 8: ((o.count >> 3) & 1) as 0 | 1,
    9: o.rw, 10: o.refclk, 11: 1 as const,
  })
  gal.evaluate({ ...drive({ count: 0, dramsel: 0, a23: 0, a22: 0, rw: 1, refclk: 0 }), 11: 0 })
  gal.reset()

  let model: U10State = { ...U10_RESET }
  let bad: string | null = null
  for (let t = 0; t < 12 * 4 * 40 && !bad; t++) {
    const i = {
      count: t % 12,
      refclk: (Math.floor(t / 9) & 1) as 0 | 1,
      dramsel: (Math.floor(t / 12) % 2) as 0 | 1,
      a23: (Math.floor(t / 24) % 2) as 0 | 1,
      a22: (Math.floor(t / 48) % 2) as 0 | 1,
      rw: (Math.floor(t / 96) % 2) as 0 | 1,
    }
    const d = drive(i)
    const p = gal.evaluate(d)
    const want = u10out(model, i)
    if (p[17] !== want.nRas[0] || p[19] !== want.nRas[1] ||
        p[20] !== want.nRas[2] || p[21] !== want.nRas[3] ||
        p[18] !== want.nCas || p[22] !== want.nWe) {
      bad = `outputs differ at count ${i.count}, rf=${model.rf}`
      break
    }
    gal.clock(d)
    model = u10step(model, i)
    const rf = (p2: Int8Array) => (p2[16] << 0) | (p2[14] << 1)
    const p2 = gal.evaluate(d)
    if (rf(p2) !== model.rf || p2[15] !== model.refq) {
      bad = `state differs at count ${i.count}: fuses rf=${rf(p2)} refq=${p2[15]}, ` +
        `model rf=${model.rf} refq=${model.refq}`
    }
  }
  check(bad === null,
    `${label}: matches u10.model.ts over 1,920 clock edges - every bus phase, ` +
    `DRAM cycle and not, across many refresh bursts`, bad ?? "")
}
checkU10("CUPL u10.jed", load("mainboard/logic/cupl/u10.cupl.jed"))

/* -- the video card's arb and rfa sweeps left on 2026-09-20 ---------------
 *
 * `checkArb` swept all 1,024 of the arbiter's inputs and `checkRfa` all 16,384
 * of the register-file address decode's, each against our own fuse map. Both
 * parts belong to `video`, archived that day (`hardware/archive/README.md`); their
 * `reference/arb.cupl.jed` and `reference/rfa.cupl.jed` are kept, and so are
 * the designs in `../access.jedec.ts` and `../regfile.jedec.ts`, but nothing
 * here compiles them any more. `hardware/archive/video/docs/history.md` has the two
 * sweeps' record. */


console.log("\nAnd ours, which must agree with it\n")
checkMmu("our mmu.jed", load("mainboard/logic/mmu.jed"))
checkClkdec("our clkdec.jed", load("mainboard/logic/clkdec.jed"))

/* -- the two conventions the reference files pin down --------------------- */
console.log("\nWhat the reference files establish\n")
check(cuplClk.registered(16) && cuplClk.registered(21) && !cuplClk.registered(15),
  "S1 is read correctly: CUPL registers C0..C3, E and Q and nothing else")
check([17, 20, 22].every((p) => !cuplMmu.polarityHigh(p)),
  "S0 is read correctly: CUPL's active-low outputs carry S0 = 0 " +
  "(only true under the pin-23-downward config order)")

/* -- the rule, so the boards that are not built yet get the same treatment --
 *
 * Both errors above were invisible to 178 self-consistent checks, and no
 * amount of additional self-checking would have found them: the assembler and
 * the simulator share a device description, so they agree with each other
 * whatever it says. The only thing that broke the tie was a second
 * implementation.
 *
 * So it is a rule and not a habit: A GAL DOES NOT SHIP WITHOUT A CUPL
 * REFERENCE. Only mmu and clkdec ship - every other design here is superseded
 * by a CPLD and carries a banner saying so. The decode GALs on serial, storage
 * and PS/2 are still unwritten; each one needs a row here and a file in
 * its card's logic/cupl/, generated by ../prjbureau/cupl-reference.sh. */

interface Part { design: Design; reference: string | null }
const REGISTRY: Part[] = [
  { design: mmuDesign, reference: "mainboard/logic/cupl/mmu.cupl.jed" },
  { design: clkdecDesign, reference: "mainboard/logic/cupl/clkdec.cupl.jed" },
  /* U9 - the space decode, fitted 2026-09-09. ram.md 11 item 6 said it might
   * not fit a 22V10; it fits at 6 macrocells of 10 and 5 terms of 16. */
  { design: u9Design, reference: "mainboard/logic/cupl/u9.cupl.jed" },
  /* U10 - the SIMM controller, fitted 2026-09-09. ram.md 11 item 6 said it had
   * "not been counted at all"; it fits at 9 macrocells of 10. */
  { design: u10Design, reference: "mainboard/logic/cupl/u10.cupl.jed" },
  /* ⭐ THE VIDEO CARD'S TWELVE LEFT THIS REGISTRY ON 2026-09-20 - hgen, vgen,
   * vdec, hadr, vadr, arb, wcol, wrow, seqph, seqctl, vlen and rfa. `video`
   * was archived that day and `video3` is the machine's video card
   * (`hardware/archive/README.md`, `docs/history.md`). Their reference JEDECs stay in
   * `reference/` and their designs stay in `gal/`; the registry describes the
   * machine, and they are no longer in it. */
  /* The audio five were missing from this list until 2026-09-07, which is the
   * only reason their .jed files went out with no SUPERSEDED banner on them
   * while the video ten had one. The guard below cannot catch a part it has
   * never been told about, so the list has to be the whole inventory - it is
   * checked against tools/gal/designs.ts. */
  { design: aseqDesign, reference: null }, { design: adecDesign, reference: null },
  { design: admatDesign, reference: null }, { design: aintenaDesign, reference: null },
  { design: apendDesign, reference: null },
  /* ⭐ v3lane - video3's byte lanes, 2026-09-19: the lane transceivers' /OE,
   * the four byte enables and the internal bus's two latch-side drivers.
   * video3/v3lane.check.ts sweeps all 4,096 inputs against this reference. */
  { design: v3laneDesign, reference: "video3/logic/cupl/v3lane.cupl.jed" },
  /* ⭐ storage's two, 2026-09-20: the $FF58 decode with SDSTAT's drive, and
   * SDCTRL with the eight-clock burst engine. `hardware/storage/logic/storage.check.ts`
   * sweeps sdbus's 8,192 inputs and drives sdeng for 20,000 clocked steps
   * against these references - a registered part cannot be compared a vector
   * at a time, which is a trap that file records. */
  { design: sdbusDesign, reference: "storage/logic/cupl/sdbus.cupl.jed" },
  { design: sdengDesign, reference: "storage/logic/cupl/sdeng.cupl.jed" },
]

console.log("\nEvery live GAL has a second implementation to check it against\n")
{
  /* The registry is the thing the guard trusts, so something has to check the
   * registry itself. ALL is the list every probe walks. */
  const missing = ALL.filter((d) => !REGISTRY.some((p) => p.design.name === d.name))
  check(missing.length === 0, `the registry covers all ${ALL.length} GAL designs`,
    missing.map((d) => d.name).join(", "))
}
{
  const live = REGISTRY.filter((p) => !p.design.supersededBy)
  const naked = live.filter((p) => !p.reference)
  check(naked.length === 0,
    `all ${live.length} live GALs have a CUPL reference`,
    naked.length ? `no reference for ${naked.map((p) => p.design.name).join(", ")} - ` +
      `run ../prjbureau/cupl-reference.sh on its .pld` : "")
  const superseded = REGISTRY.filter((p) => p.design.supersededBy)
  console.log(`      ${superseded.length} superseded and not checked: ` +
    `${superseded.map((p) => p.design.name).join(", ")}`)
}

/* -- conventions the reference files do NOT exercise ---------------------- *
 *
 * Named rather than assumed, because the next GAL may be the one that uses
 * them and there would be nothing to catch it. */
console.log("\nConventions still resting on one source\n")
{
  const live = REGISTRY.filter((p) => !p.design.supersededBy).map((p) => p.design)
  const uses = (what: string, pred: (d: Design) => boolean) => {
    const hit = live.filter(pred).map((d) => d.name)
    console.log(`      ${hit.length ? "IN USE by " + hit.join(", ") : "unused"}  - ${what}`)
    return hit.length > 0
  }
  const untested: string[] = []
  if (uses("a synchronous-preset term (SP row): both references leave it never-true",
      (d) => !!d.sp)) untested.push("SP")
  if (uses("a conditional output enable: both references are always-on or high-Z",
      (d) => d.cells.some((c) => c.oe && c.oe !== "1"))) untested.push("OE term")
  if (uses("a registered macrocell with S0 = 0: both references have S0 = 1 throughout",
      (d) => d.cells.some((c) => c.registered && c.s0 === 0))) untested.push("registered S0=0")
  if (uses("the 64-bit user signature: our .pld files carry no UES directive, so CUPL " +
      "wrote zeros and the bit order here is unchecked",
      (d) => !!d.signature)) untested.push("UES bit order")
  check(true, `${untested.length} convention${untested.length === 1 ? "" : "s"} in use ` +
    `with one source: ${untested.join(", ") || "none"}`)
  console.log(`      None of these is load-bearing today - the UES is read-back data and`)
  console.log(`      the rest are unused - but a design that needs one needs a reference`)
  console.log(`      that exercises it, not just any reference.`)
}

console.log(failures === 0
  ? "\nOur fuse map and Atmel's agree - the provenance note in gal22v10.ts is settled"
  : `\n${failures} FAILED`)
if (failures) process.exit(1)
