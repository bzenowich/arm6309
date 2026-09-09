/* Assemble both motherboard GALs, then check the FUSES.
 *
 * gal/README.md open item 1 says "nothing has been fitted" and that the pin
 * budget is arithmetic rather than a fitter's report. This is the report, and
 * it is stronger than one: the .jed files are written, read back, and the
 * reconstructed AND array is evaluated against mmu.model.ts and
 * clkdec.model.ts. What is checked is the bit pattern a programmer will burn,
 * not the equations it came from.
 *
 * The one thing it cannot check is jedec/gal22v10.ts itself - if the column
 * map were wrong, the assembler and the simulator would share the error and
 * agree with each other. See the provenance note there.
 *
 *   npm run check:jedec
 */

import { writeFileSync } from "node:fs"
import { join } from "node:path"

import { assemble, fuseChecksum, toJedec, toReport, type Design } from "./jedec/assemble"
import { Gal22v10, parseJedec } from "./jedec/simulate"
import { TOTAL_FUSES } from "./jedec/gal22v10"
import { PHASES, mmu } from "./mmu.model"
import { RESET_STATE, decode, setsRun, step, type Counter } from "./clkdec.model"
import { MAP, paOf, u9 } from "./u9.model"
import { BANK, RESET_STATE as U10_RESET, accessWindow, casWindow, out as u10out, refreshSafe, step as u10step, type State as U10State } from "./u10.model"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

const here = new URL(".", import.meta.url).pathname

/** Assemble, write the .jed and the report, and read the .jed back. */
const build = (design: Design, base: string) => {
  const a = assemble(design)
  const jed = toJedec(design, a)
  writeFileSync(join(here, `${base}.jed`), jed)
  writeFileSync(join(here, `${base}.doc`), toReport(design, a))

  const parsed = parseJedec(jed)
  check(parsed.declaredFuses === TOTAL_FUSES,
    `${base}: the file declares ${TOTAL_FUSES} fuses - GAL mode, not PAL and not power-down`,
    `*QF${parsed.declaredFuses}`)
  check(parsed.declaredChecksum === fuseChecksum(parsed.fuses),
    `${base}: the fuse checksum matches the fuses it is a checksum of`)
  check(parsed.fuses.every((v, i) => v === a.fuses[i]),
    `${base}: what was written is what is read back`)
  return { design, assembly: a, gal: new Gal22v10(parsed.fuses) }
}

/* ======================================================================== */
console.log("U3 - the MMU sequencer\n")
const u3 = build((await import("./mmu.jedec")).mmuDesign, "mmu")

/* Pins 14-16 carry E, Q and R/W into a part whose macrocells they are. That
 * only works if those macrocells never drive and are combinational - a
 * registered macrocell feeds the array from its register and its pin is not
 * an input at all. It is the mistake this arrangement invites. */
{
  const bad = u3.gal.checkInputPins([14, 15, 16])
  check(bad.length === 0, "E, Q and R/W reach the array as inputs on macrocell pins", bad.join("; "))
}
check(u3.gal.undriven(23), "pin 23 is left at high-Z, so it is a spare INPUT and not a driven low")

/* The exhaustive part: the whole 16-bit address space x 4 quadrature phases
 * x R/W, read off the fuse map and compared with the model mmu.check.ts makes
 * its claims about. 524,288 evaluations. */
{
  let mismatch: string | null = null
  outer:
  for (let la = 0; la <= 0xffff && !mismatch; la++) {
    for (const ph of PHASES) {
      for (const rw of [0, 1] as const) {
        const driven: Record<number, 0 | 1> = {
          1: ((la >> 15) & 1) as 0 | 1, 2: ((la >> 14) & 1) as 0 | 1,
          3: ((la >> 13) & 1) as 0 | 1, 4: ((la >> 12) & 1) as 0 | 1,
          5: ((la >> 11) & 1) as 0 | 1, 6: ((la >> 10) & 1) as 0 | 1,
          7: ((la >> 9) & 1) as 0 | 1, 8: ((la >> 8) & 1) as 0 | 1,
          9: ((la >> 7) & 1) as 0 | 1, 10: ((la >> 6) & 1) as 0 | 1,
          11: ((la >> 5) & 1) as 0 | 1, 13: ((la >> 4) & 1) as 0 | 1,
          14: ph.e as 0 | 1, 15: ph.q as 0 | 1, 16: rw,
        }
        const pins = u3.gal.evaluate(driven)
        const m = mmu(la, ph.e, ph.q, rw)
        /* The model reports signals as asserted; these pins are declared
         * active low, so the pin is the complement. MUXSEL and CTRLCP are
         * already pin levels in the model. */
        const want: Record<number, number> = {
          17: m.iopage ? 0 : 1,
          18: m.muxsel ? 1 : 0,
          19: m.isooe ? 0 : 1,
          20: m.mapwe ? 0 : 1,
          21: m.mapoe ? 0 : 1,
          22: m.ctrlcp ? 1 : 0,
        }
        for (const [pin, v] of Object.entries(want)) {
          if (pins[Number(pin)] !== v) {
            mismatch = `pin ${pin} = ${pins[Number(pin)]}, expected ${v} at ` +
              `$${la.toString(16).toUpperCase().padStart(4, "0")} ${ph.name} R/W=${rw}`
            break outer
          }
        }
      }
    }
  }
  check(mismatch === null,
    "the fuse map matches mmu.model.ts over all 65,536 addresses x 4 phases x R/W",
    mismatch ?? "")
}

/* ======================================================================== */
console.log("\nU6 - the divider, /IOSEL and boot mode\n")
const u6 = build((await import("./clkdec.jedec")).clkdecDesign, "clkdec")

check(u6.gal.polarityAssumptionMatters().length === 0,
  "no registered macrocell that is read back is active low, so the feedback " +
  "polarity assumption in simulate.ts carries no weight",
  u6.gal.polarityAssumptionMatters().join(", "))

check(u6.gal.undriven(23),
  "U6 pin 23 is left at high-Z, so it is a spare INPUT and not a driven low " +
  "- the macrocell RAM_WE vacated when the system RAM left the board")

/* The divider, against the behavioural counter. This is the check that the
 * hand expansion of C1's XOR, C2's suppression term and E and Q's decodes is
 * the same function - the step gal/README.md counts product terms for and
 * nothing has ever executed. */
const CNT_PINS = { 16: 0, 17: 1, 20: 2, 21: 3 } as const
const readCounter = (pins: Int8Array): Counter => {
  let cnt = 0
  for (const [pin, bit] of Object.entries(CNT_PINS)) cnt |= pins[Number(pin)] << bit
  return { cnt, e: pins[18] as 0 | 1, q: pins[19] as 0 | 1, run: pins[22] as 0 | 1 }
}

for (const fastE of [false, true]) {
  const label = fastE ? "/8 (fast-E)" : "/12"
  /* Pins 5..9 and 11 are LA7, LA6, LA5, R/W, LA4 and LA0. The base holds them
   * at a value that is NOT a $FFB1 write, so RUN stays where reset put it. */
  const base = { 2: (fastE ? 1 : 0) as 0 | 1, 3: 1 as const, 4: 1 as const,
                 5: 0 as const, 6: 0 as const, 7: 0 as const, 8: 1 as const,
                 9: 0 as const, 10: 0 as const, 11: 0 as const }

  /* Reset is asserted by pulling pin 3 LOW, and it is a level: it holds. */
  u6.gal.evaluate({ ...base, 3: 0 })
  check(readCounter(u6.gal.evaluate({ ...base, 3: 0 })).cnt === 0,
    `${label}: /RESET low holds the counter at zero`)
  u6.gal.clock({ ...base, 3: 0 })
  const held = readCounter(u6.gal.evaluate({ ...base, 3: 0 }))
  check(held.cnt === 0 && held.e === 0 && held.q === 0,
    `${label}: a clock edge while /RESET is low changes nothing`)
  check(held.run === 0,
    `${label}: ⭐ and RUN comes out of reset at ZERO, which IS boot mode - ` +
    `a 22V10 has one shared asynchronous reset and it resets to zero, so a ` +
    `bit that had to come up SET could not live on this part`)

  let model: Counter = { ...RESET_STATE }
  let bad: string | null = null
  let sawE0 = false, sawE1 = false
  const period = fastE ? 8 : 12
  for (let i = 0; i < period * 8 && !bad; i++) {
    u6.gal.clock(base)
    model = step(model, fastE)
    const got = readCounter(u6.gal.evaluate(base))
    if (got.cnt !== model.cnt || got.e !== model.e || got.q !== model.q || got.run !== model.run) {
      bad = `edge ${i}: fuses gave cnt=${got.cnt} e=${got.e} q=${got.q} run=${got.run}, ` +
        `model says cnt=${model.cnt} e=${model.e} q=${model.q} run=${model.run}`
      break
    }
    if (got.e) sawE1 = true; else sawE0 = true

    /* Every combination of the four decode inputs, at this phase: /IOPAGE,
     * LA7, LA6 and RUN's own feedback. */
    for (let bits = 0; bits < 8 && !bad; bits++) {
      const d = { ...base,
        4: ((bits >> 2) & 1) as 0 | 1, 5: ((bits >> 1) & 1) as 0 | 1,
        6: (bits & 1) as 0 | 1 }
      const pins = u6.gal.evaluate(d)
      const want = decode({ nIopage: d[4], la7: d[5], la6: d[6], run: got.run })
      const got2 = { nIosel: pins[15], nBootOe: pins[14] }
      for (const k of ["nIosel", "nBootOe"] as const) {
        if (got2[k] !== want[k]) {
          bad = `${k} = ${got2[k]}, expected ${want[k]} with ` +
            `/IOPAGE=${d[4]} LA7=${d[5]} LA6=${d[6]} RUN=${got.run}`
        }
      }
    }
  }
  check(bad === null, `${label}: the fuse map matches clkdec.model.ts for ${period * 8} edges ` +
    `and all 8 decode inputs at each`, bad ?? "")
  check(sawE0 && sawE1, `${label}: the decode sweep covered E low and E high`)
}

/* Boot mode's own claims. The sweep above never sets RUN, deliberately - it
 * is checking the divider. This checks the latch. */
console.log("\n      boot mode - machine.md 7.2\n")
{
  /* $FFxx is /IOPAGE low (pin 4 = 0). $FFB1 is LA7=1 LA6=0 LA5=1 LA4=1 LA0=1;
   * a write is R/W low; the term is qualified on E, so run the counter until
   * E is high. */
  const hold = { 2: 0 as const, 3: 1 as const, 10: 0 as const }
  const addr = (la7: 0|1, la6: 0|1, la5: 0|1, la4: 0|1, la0: 0|1, rw: 0|1, iopage: 0|1) =>
    ({ ...hold, 4: iopage, 5: la7, 6: la6, 7: la5, 8: rw, 9: la4, 11: la0 })

  const reset = () => { u6.gal.evaluate({ ...addr(0,0,0,0,0,1,1), 3: 0 }); u6.gal.clock({ ...addr(0,0,0,0,0,1,1), 3: 0 }) }
  /** Clock until E is high, then apply `d` for one edge. Returns RUN. */
  const strobe = (d: Record<number, 0 | 1>) => {
    for (let i = 0; i < 24; i++) {
      const idle = { ...addr(0, 0, 0, 0, 0, 1, 1) }
      if (u6.gal.evaluate(idle)[18] === 1) break
      u6.gal.clock(idle)
    }
    u6.gal.clock(d)
    return u6.gal.evaluate({ ...addr(0, 0, 0, 0, 0, 1, 1) })[22]
  }

  reset()
  check(u6.gal.evaluate({ ...addr(0,0,0,0,0,1,1) })[22] === 0,
    "out of reset RUN is 0 - the machine is in boot mode before it fetches anything")

  reset()
  check(strobe(addr(1, 0, 1, 1, 1, 0, 0)) === 1,
    "a WRITE to $FFB1 sets RUN - one store leaves boot mode, and it is the " +
    "last instruction machine.md 7.2's boot sequence executes")

  for (const [name, d] of [
    ["$FFB0 - TASK, which boot code must write FIRST and which must not leave boot mode",
      addr(1, 0, 1, 1, 0, 0, 0)],
    ["a READ of $FFB1 - the strobe is a write", addr(1, 0, 1, 1, 1, 1, 0)],
    ["$FFA1 - a block register, not the control window", addr(1, 0, 1, 0, 1, 0, 0)],
    ["$FF51 - a card's window", addr(0, 1, 0, 1, 1, 0, 0)],
    ["$00B1 - the same low byte, outside the I/O page", addr(1, 0, 1, 1, 1, 0, 1)],
  ] as const) {
    reset()
    const p = d as Record<number, 0 | 1>
    /* The model agrees it is not the strobe - so this checks the fuses and
     * clkdec.model.ts together rather than against a hardcoded expectation. */
    check(!setsRun({ nIopage: p[4], la7: p[5], la6: p[6], la5: p[7], la4: p[9],
                     la0: p[11], rw: p[8], e: 1 }),
      `      (model agrees ${name} is not the $FFB1 strobe)`)
    check(strobe(p) === 0, `and ${name} does not`)
  }

  /* Once set, nothing but /RESET clears it: a wild store cannot put the
   * machine back into boot mode over live RAM. */
  reset()
  strobe(addr(1, 0, 1, 1, 1, 0, 0))
  for (let i = 0; i < 40; i++) u6.gal.clock(addr(0, 0, 0, 0, 0, 1, 1))
  check(u6.gal.evaluate({ ...addr(0,0,0,0,0,1,1) })[22] === 1,
    "and RUN stays set through 40 edges of ordinary cycles - it is one-way " +
    "per reset, like the shadow-ROM disable machine.md 7.2 replaced")
  u6.gal.evaluate({ ...addr(0,0,0,0,0,1,1), 3: 0 })
  check(u6.gal.evaluate({ ...addr(0,0,0,0,0,1,1), 3: 0 })[22] === 0,
    "and /RESET puts it back - asynchronously, because that is the only " +
    "reset a 22V10 has")
}

/* ======================================================================== */
console.log("\nU9 - the physical space decode\n")
const u9g = build((await import("./u9.jedec")).u9Design, "u9")

{
  const bad = u9g.gal.checkInputPins([14, 23])
  check(bad.length === 0,
    "LA3 and R/W reach the array as inputs on macrocell pins 14 and 23 - the " +
    "two 8-term macrocells, where an input costs nothing and an output would " +
    "have had the least room", bad.join("; "))
}
check(u9g.gal.undriven(21) && u9g.gal.undriven(22),
  "pins 21 and 22 are left at high-Z - two spare INPUTS, not two driven lows")

/* The exhaustive part: every value of the six physical address lines this
 * part sees, x every logical decode input, x R/W x RUN x /IOPAGE. 64 x 32 x 8
 * = 16,384 evaluations, read off the fuse map. */
{
  let bad: string | null = null
  outer:
  for (let pa = 0; pa < 64; pa++) {
    for (let lo = 0; lo < 32; lo++) {
      for (const rw of [0, 1] as const) {
        for (const run of [0, 1] as const) {
          for (const nIopage of [0, 1] as const) {
            const la7 = ((lo >> 4) & 1) as 0 | 1, la6 = ((lo >> 3) & 1) as 0 | 1
            const la5 = ((lo >> 2) & 1) as 0 | 1, la4 = ((lo >> 1) & 1) as 0 | 1
            const la3 = (lo & 1) as 0 | 1
            const driven: Record<number, 0 | 1> = {
              1: ((pa >> 5) & 1) as 0 | 1, 2: ((pa >> 4) & 1) as 0 | 1,
              3: ((pa >> 3) & 1) as 0 | 1, 4: ((pa >> 2) & 1) as 0 | 1,
              5: ((pa >> 1) & 1) as 0 | 1, 6: (pa & 1) as 0 | 1,
              7: nIopage, 8: run, 9: la7, 10: la6, 11: la5, 13: la4,
              14: la3, 23: rw,
            }
            const pins = u9g.gal.evaluate(driven)
            const m = u9({ pa, nIopage, run, la7, la6, la5, la4, la3, rw })
            const want: Record<number, number> = {
              15: m.nMapCeLo, 16: m.nMapCeHi, 17: m.nRomCe0,
              18: m.nIopageBp, 19: m.dramSel, 20: m.nRomCe1,
            }
            for (const [pin, v] of Object.entries(want)) {
              if (pins[Number(pin)] !== v) {
                bad = `pin ${pin} = ${pins[Number(pin)]}, expected ${v} at ` +
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
  }
  check(bad === null,
    "the fuse map matches u9.model.ts over all 64 physical x 32 logical x " +
    "R/W x RUN x /IOPAGE - 16,384 evaluations", bad ?? "")
}

/* The claims that are worth naming rather than leaving inside the sweep. */
{
  const at = (byte: number, o: Partial<Parameters<typeof u9>[0]> = {}) =>
    u9({ pa: paOf(byte), nIopage: 1, run: 1, la7: 0, la6: 0, la5: 0, la4: 0, la3: 0, rw: 1, ...o })

  check(at(MAP.romBase).nRomCe0 === 0 && at(MAP.romBase).nRomCe1 === 1,
    "physical 2.0 M reads the ROM's first device")
  check(at(MAP.romTop - 1).nRomCe1 === 0 && at(MAP.romTop - 1).nRomCe0 === 1,
    "and physical 2.99 M its second - A19 picks, and nothing else does")
  check(at(MAP.romTop).nRomCe0 === 1 && at(MAP.romTop).nRomCe1 === 1,
    "and 3.0 M is past the top of it")
  check(at(MAP.romBase, { rw: 0 }).nRomCe0 === 1,
    "a WRITE to ROM space selects nothing - R/W is in the chip enable, so a " +
    "stray store is a no-op and not a bus fight (/OE is tied low)")

  check(at(0, { run: 0 }).nRomCe0 === 0,
    "⭐ in boot mode the ROM answers at physical zero, where the '244 parks " +
    "the address - the machine fetches its reset vector before the map means " +
    "anything at all")
  check(at(0, { run: 0, nIopage: 0, la7: 1, la6: 0 }).nRomCe0 === 1,
    "and stands down for $FF00-$FFBF, so the MMU and the cards answer during " +
    "boot - which is what machine.md 7.2's carve-out is")
  check(at(0, { run: 0, nIopage: 0, la7: 1, la6: 1 }).nRomCe0 === 0,
    "but NOT for $FFC0-$FFFF")
  check(at(0, { run: 1, nIopage: 0, la7: 1, la6: 1 }).nRomCe0 === 0,
    "⭐ and the vector page reads the ROM forever, boot mode or not - $FFFE " +
    "is a reset vector and not an undriven bus, which is what makes a real " +
    "HD63C09E a valid part for the socket again (graphics.md 16 item 8)")

  check(at(MAP.simmBase).dramSel === 1 && at(MAP.simmTop - 1).dramSel === 1,
    "the four SIMM windows answer across 4-20 M")
  check(at(MAP.simmBase - 1).dramSel === 0 && at(MAP.simmTop).dramSel === 0,
    "and not below 4 M or above 20 M")
  check(at(MAP.simmBase, { run: 0 }).dramSel === 0,
    "⚠ and not during boot, when A24..A22 are floating off a deselected SRAM")

  check(at(0x100000).nIopageBp === 1 && at(0x1fffff).nIopageBp === 1,
    "a card may answer anywhere in the bottom 2 MB")
  check(at(0x200000).nIopageBp === 0 && at(0x1ffffff).nIopageBp === 0,
    "⭐ and nowhere above it - ram.md 5.3's four backplane pins, bought with " +
    "one open-drain output and no card changes")
  check(at(0x200000, { run: 0 }).nIopageBp === 1,
    "⚠ and the above-2 MB pull is gated on RUN, because during boot A24..A21 " +
    "float: an ungated compare would assert /IOPAGE at random, and /IOSEL is " +
    "/IOPAGE AND /A7, so every card would decode a boot fetch")
  check(at(0, { nIopage: 0 }).nIopageBp === 0,
    "and U3's own term passes through, boot or not")

  const blk = { nIopage: 0 as const, la7: 1 as const, la6: 0 as const, la5: 1 as const, la4: 0 as const }
  check(at(0, { ...blk, la3: 0, rw: 0 }).nMapCeLo === 0 &&
        at(0, { ...blk, la3: 0, rw: 0 }).nMapCeHi === 1,
    "$FFA0-$FFA7 selects the LOW map SRAM alone - ram.md 4.1 Layout A, and " +
    "the chip enable is what splits it because U3's MAPWE never sees LA3")
  check(at(0, { ...blk, la3: 1, rw: 0 }).nMapCeHi === 0 &&
        at(0, { ...blk, la3: 1, rw: 0 }).nMapCeLo === 1,
    "and $FFA8-$FFAF the HIGH one")
  check(at(0).nMapCeLo === 0 && at(0).nMapCeHi === 0,
    "both are selected for an ordinary cycle - translation needs A24..A13 at once")
  check(at(0, { run: 0 }).nMapCeLo === 1 && at(0, { run: 0 }).nMapCeHi === 1,
    "⭐ and both are deselected for the whole of boot mode, which is exactly " +
    "when U6 has the buffer driving instead - the two conditions are the same " +
    "two conditions, on two parts")
  check(at(0, { nIopage: 0, la7: 1, la6: 1 }).nMapCeLo === 1,
    "and for the vector page, for the same reason")
}

/* U6 and U9 have to agree about the changeover, and they are different parts
 * with different equations. This is the one claim that spans them. */
console.log("\n      the boot buffer and the map SRAMs never drive together\n")
{
  let overlap: string | null = null
  for (const run of [0, 1] as const) {
    for (const nIopage of [0, 1] as const) {
      for (let lo = 0; lo < 4; lo++) {
        const la7 = ((lo >> 1) & 1) as 0 | 1, la6 = (lo & 1) as 0 | 1
        const bootoe = decode({ nIopage, la7, la6, run }).nBootOe
        const m = u9({ pa: 0, nIopage, run, la7, la6, la5: 0, la4: 0, la3: 0, rw: 1 })
        /* Both asserted low. The map SRAM also needs U3's /MAPOE, which is
         * deasserted for the whole of any $FFxx cycle - so this is the
         * conservative test: /CE alone against the buffer. */
        if (bootoe === 0 && (m.nMapCeLo === 0 || m.nMapCeHi === 0)) {
          overlap = `RUN=${run} /IOPAGE=${nIopage} LA7=${la7} LA6=${la6}`
        }
      }
    }
  }
  check(overlap === null,
    "over every combination of RUN, /IOPAGE, LA7 and LA6: the '244's output " +
    "enable and the map SRAMs' chip enables are never both asserted",
    overlap ?? "")

  /* And the changeover itself. RUN is set by a write to $FFB1, which is an
   * $FFxx cycle - and during ANY $FFxx cycle the map SRAMs are deselected
   * anyway. So the edge that hands the address bus over happens inside a
   * cycle where the SRAM is already off for an independent reason. */
  const during = u9({ pa: 0, nIopage: 0, run: 0, la7: 1, la6: 0, la5: 1, la4: 1, la3: 0, rw: 0 })
  check(during.nMapCeLo === 1 && during.nMapCeHi === 1,
    "⭐ and the handover edge is free: RUN is set by a write to $FFB1, which " +
    "is an $FFxx cycle, and the map SRAMs are deselected for every $FFxx " +
    "cycle - so there is no instant at which one turns on as the other turns off")
}

/* ======================================================================== */
console.log("\nU10 - the SIMM controller\n")
const u10g = build((await import("./u10.jedec")).u10Design, "u10")

check(u10g.gal.undriven(23),
  "pin 23 is left at high-Z - a spare INPUT, and with pin 13 that is two")

/* The registered half. The refresh sequencer is the only state on this part
 * and it is what machine.md 5 item 10's rule exists for, so it is swept
 * against the model over a whole refresh period at every bus phase. */
const RF_PINS = { 16: 0, 14: 1 } as const
const readU10 = (pins: Int8Array): U10State => ({
  rf: (pins[16] << 0) | (pins[14] << 1),
  refq: pins[15] as 0 | 1,
})

{
  /* Drive: DRAMSEL, A23, A22, C0-C3, R/W, REFCLK, /RESET. */
  const drive = (o: Partial<Record<string, 0 | 1>> & { count: number }) => ({
    2: (o.dramsel ?? 0) as 0 | 1, 3: (o.a23 ?? 0) as 0 | 1, 4: (o.a22 ?? 0) as 0 | 1,
    5: ((o.count >> 0) & 1) as 0 | 1, 6: ((o.count >> 1) & 1) as 0 | 1,
    7: ((o.count >> 2) & 1) as 0 | 1, 8: ((o.count >> 3) & 1) as 0 | 1,
    9: (o.rw ?? 1) as 0 | 1, 10: (o.refclk ?? 0) as 0 | 1, 11: 1 as const,
  })

  u10g.gal.evaluate({ ...drive({ count: 0 }), 11: 0 })
  u10g.gal.clock({ ...drive({ count: 0 }), 11: 0 })
  const r = readU10(u10g.gal.evaluate(drive({ count: 0 })))
  check(r.rf === 0 && r.refq === 0,
    "out of reset the refresh sequencer is idle with no request outstanding")

  /* A whole refresh period at every phase of the bus cycle, with the DRAM
   * being accessed and not, in both R/W directions - 12 counts x 2 x 2 x the
   * REFCLK toggle. The model and the fuses step together. */
  let model: U10State = { ...U10_RESET }
  let bad: string | null = null
  let sawRefresh = false, sawAccess = false
  for (let t = 0; t < 12 * 4 * 40 && !bad; t++) {
    const count = t % 12
    /* REFCLK toggles every 256 CLK25 counts; compress it here so the sweep
     * exercises many bursts without running 256 x 512 edges. */
    const refclk = (Math.floor(t / 9) & 1) as 0 | 1
    const dramsel = (Math.floor(t / 12) % 2) as 0 | 1
    const a23 = (Math.floor(t / 24) % 2) as 0 | 1
    const a22 = (Math.floor(t / 48) % 2) as 0 | 1
    const rw = (Math.floor(t / 96) % 2) as 0 | 1
    const i = { count, dramsel, a23, a22, rw, refclk }
    const d = drive(i as never)

    const pins = u10g.gal.evaluate(d)
    const want = u10out(model, i)
    const got = {
      nRas: [pins[17], pins[19], pins[20], pins[21]],
      nCas: pins[18], nWe: pins[22],
    }
    for (let n = 0; n < 4; n++) {
      if (got.nRas[n] !== want.nRas[n]) {
        bad = `/RAS${n} = ${got.nRas[n]}, expected ${want.nRas[n]} at count ${count} ` +
          `DRAMSEL=${dramsel} A23:A22=${a23}${a22} rf=${model.rf}`
      }
    }
    if (!bad && got.nCas !== want.nCas) bad = `/CAS = ${got.nCas}, expected ${want.nCas} at count ${count} rf=${model.rf}`
    if (!bad && got.nWe !== want.nWe) bad = `/WE = ${got.nWe}, expected ${want.nWe} at count ${count} R/W=${rw}`
    if (model.rf !== 0) sawRefresh = true
    if (dramsel && accessWindow(count)) sawAccess = true

    u10g.gal.clock(d)
    model = u10step(model, i)
    const stepped = readU10(u10g.gal.evaluate(d))
    if (!bad && (stepped.rf !== model.rf || stepped.refq !== model.refq)) {
      bad = `state: fuses rf=${stepped.rf} refq=${stepped.refq}, ` +
        `model rf=${model.rf} refq=${model.refq} at count ${count}`
    }
  }
  check(bad === null,
    "the fuse map matches u10.model.ts over 1,920 clock edges - every bus " +
    "phase, DRAM cycle and not, both R/W directions, across many refresh bursts",
    bad ?? "")
  check(sawRefresh && sawAccess, "and the sweep covered both a refresh burst and an access")
}

/* The claims worth naming, against the model. */
{
  const at = (o: Partial<Parameters<typeof u10out>[1]> & { count: number }, rf = 0, refq: 0 | 1 = 0) =>
    u10out({ rf, refq }, { dramsel: 1, a23: 0, a22: 1, rw: 1, refclk: 0, ...o } as never)

  check(at({ count: 3 }).nRas[0] === 1 && at({ count: 4 }).nRas[0] === 0,
    "RAS falls at count 4 - 158.8 ns, which is 48.8 ns after the address goes " +
    "valid at the 6809's t_AD of 110 ns")
  check(at({ count: 6 }).nCas === 1 && at({ count: 7 }).nCas === 0,
    "and CAS at count 7 - 79 ns of row hold after RAS, and 49 ns of write-data " +
    "setup, because 6809 write data is valid at 229 ns")
  check(at({ count: 9 }).nRas[0] === 0 && at({ count: 10 }).nRas[0] === 1 &&
        at({ count: 10 }).nCas === 1,
    "both release at count 10 - 238 ns of t_RAS, and 238 ns of precharge")

  check([0, 1, 2, 3].every((n) =>
    at({ count: 5, a23: (n === 1 || n === 2 ? 1 : 0), a22: (n === 0 || n === 2 ? 1 : 0) } as never)
      .nRas.filter((v) => v === 0).length === 1),
    "⭐ exactly one /RAS per access, and A23:A22 alone picks it - which is why " +
    "U9 spends ONE output on DRAMSEL and not four on selects")
  check(BANK(0, 1) === 0 && BANK(1, 0) === 1 && BANK(1, 1) === 2 && BANK(0, 0) === 3,
    "and the four windows at physical A24..A22 = 001/010/011/100 map to four " +
    "distinct A23:A22 codes - NOT in numeric order")

  check(at({ count: 5, dramsel: 0 }).nRas.every((v) => v === 1) &&
        at({ count: 5, dramsel: 0 }).nCas === 1,
    "no DRAMSEL, no access - U9's decode is the only thing that starts one")
  check(at({ count: 5, rw: 0 }).nWe === 0 && at({ count: 7, rw: 0 }).nCas === 0,
    "⚠ EARLY WRITE: /WE leads CAS by three counts, so the module takes its data " +
    "at CAS-fall and never drives D0-D7")
  check(at({ count: 5, rw: 1 }).nWe === 1, "and a read never asserts it")

  /* Refresh. */
  check(at({ count: 5, dramsel: 0 }, 1).nCas === 0 && at({ count: 5, dramsel: 0 }, 1).nRas[0] === 1,
    "⭐ CAS-BEFORE-RAS: the burst's first state drops CAS with RAS still high, " +
    "which is the command that makes the DRAM count its own row - and is why " +
    "ram.md 6.3 has no row counter and no mux path for one")
  check(at({ count: 5, dramsel: 0 }, 2).nRas.every((v) => v === 0),
    "and its second drops ALL FOUR /RAS, because every bank has to be refreshed")
  check(at({ count: 5, dramsel: 0 }, 3).nRas.every((v) => v === 0) &&
        at({ count: 5, dramsel: 0 }, 0).nRas.every((v) => v === 1),
    "⚠ RAS is low for exactly TWO counts - 79 ns against a t_RAS min of ~70 ns " +
    "on a 70 ns module. A third needs a five-state sequencer and a macrocell " +
    "this part has not got, so it is a speed-grade requirement instead")

  check(refreshSafe({ count: 10, dramsel: 1 } as never) &&
        refreshSafe({ count: 11, dramsel: 1 } as never) &&
        !refreshSafe({ count: 0, dramsel: 1 } as never),
    "a burst may start at count 10 or 11 of a DRAM cycle and NOT at 0 - four " +
    "counts from 0 would put its RAS at 2..3 and leave the access no precharge")
  check([0, 3, 5, 9].every((count) => refreshSafe({ count, dramsel: 0 } as never)),
    "⭐ and at any count when the cycle is not a DRAM cycle - which is what " +
    "keeps refresh alive through a 40.7 us video stall, because a stalled " +
    "cycle is a VRAM write and DRAMSEL is low (machine.md 5 item 10)")
}

/* ======================================================================== */
console.log("\nThe fitting, which is the thing that had never been done\n")
for (const { design, assembly } of [u3, u6, u9g, u10g]) {
  for (const u of [...assembly.usage].sort((a, b) => a.pin - b.pin)) {
    console.log(`      ${design.partNo} pin ${String(u.pin).padStart(2)}  ` +
      `${u.name.padEnd(7)} ${String(u.used).padStart(2)}/${String(u.available).padEnd(2)} terms`)
  }
  const worst = assembly.usage.reduce((a, b) =>
    b.used / b.available > a.used / a.available ? b : a)
  check(true, `${design.partNo} fits: ${assembly.usage.length} macrocells, ` +
    `tightest is ${worst.name} at ${worst.used} of ${worst.available}`)
}

console.log(failures === 0
  ? "\nAll four motherboard GALs assemble, fit, and their fuse maps match the models"
  : `\n${failures} FAILED`)
if (failures) process.exit(1)
