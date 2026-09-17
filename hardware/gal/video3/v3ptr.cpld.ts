/* v3ptr - video3's pointers, span writer and copy engine, as an ATF1508AS.
 *
 * video3/docs/partition.md §2.3.  The other half of the tri-stated FBA bus:
 * v3scan drives it for the scan and map addresses, this part for WPTR and CPTR,
 * and v3dot's arbiter is the one place that decides which (partition.md §1).
 *
 * ⭐ SO THIS MUX IS TWO SOURCES.  `video`'s vaddr carries four with one spare and
 * graphics.md §10.1.6.2 records fits that ran out there.  v3scan's fit already
 * showed three is cheap; this is the other half of that claim.
 *
 * ⛔ AND THE POINTERS NAME THE FIRST CELL PROCESSED, not the rectangle's origin
 * (plan §6.2, corrected while writing this file).  Naming the origin and walking
 * inside it means starting at origin + height - 1, which is an ADDER, and
 * graphics.md §6.4.1 and §7.2 build this card on not having one.
 */

import { toCupl, type Merged } from "../jedec/cupl"
import type { Cell } from "../jedec/assemble"
import { counterTerms, loadable } from "../jedec/counter"

/* ⭐ V3_COPYDIR picks which of the copy engine's direction bits are BUILT.
 * plan §6.2 says the column bit is "an optimisation, not a requirement" because
 * an overlapping copy can stage through the off-screen columns in two passes -
 * and the same trick works on rows, where plan §4 keeps rows 480-511 as scratch.
 * It is a switch and not a comment because the fit is the only thing that can
 * say what they cost.
 *   both (default) | rows | none */
export const COPYDIR = process.env.V3_COPYDIR ?? "none"
const DIRC = COPYDIR === "both" ? "CDIRC" : null
const DIRR = COPYDIR === "none" ? null : "CDIRR"

/* -- an up/down counter, which counter.ts does not have ------------------
 *
 * Bit i toggles when every lower bit is 1 counting up, or 0 counting down.
 * ⚠ This is the one block on the part whose product-term cost grows with
 * width, so it is where a refusal would come from. */
const upDown = (bits: string[], en: string, dir: string | null, load?: string,
                from?: string[]): Cell[] =>
  dir === null
    /* up only: counter.ts's own terms, which cost a fraction of the pair */
    ? bits.map((q, i) => ({
        pin: 0, name: q, assertedLow: false, s0: 1 as const, registered: true,
        terms: load && from
          ? loadable(bits, en, load, from)[i]
          : counterTerms({ bits, enable: en })[i],
      }))
  : bits.map((q, i) => {
    const lower = bits.slice(0, i)
    const up = [`!${dir}`, en, ...lower]
    const dn = [dir, en, ...lower.map((b) => `!${b}`)]
    const hold = [`!${en}`, q]
    const terms = [
      /* hold when not enabled, or when enabled but not toggling */
      hold.join(" & "),
      ...(lower.length ? lower.map((b) => [en, q, `!${b}`, `!${dir}`].join(" & ")) : []),
      ...(lower.length ? lower.map((b) => [en, q, b, dir].join(" & ")) : []),
      /* toggle 0 -> 1 */
      [`!${q}`, ...up].join(" & "),
      [`!${q}`, ...dn].join(" & "),
    ]
    return {
      pin: 0, name: q, assertedLow: false, s0: 1 as const, registered: true,
      terms: load && from ? [`${load} & ${from[i]}`, ...terms.map((t) => `!${load} & ${t}`)] : terms,
    }
  })

/* -- WPTR: the span writer's, the CPU port's and copyrect's destination ---
 *
 * The column reloads at end-of-row from the register file (graphics.md §7.2):
 * rfa points the file at +$08 then +$09 and each byte lands on the SAME load
 * path the CPU's own write uses, so the reload costs no latch and no mux - it
 * is LDWA/LDWB driven by the sequencer instead of by a store. */
const WCOL = [...Array(10).keys()].map((b) => `WC${b}`)
const WROW = [...Array(9).keys()].map((b) => `WR${b}`)
const wptr: Cell[] = [
  ...WCOL.map((name, i) => ({
    pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
    terms: loadable(WCOL, "WINC", "LDWCOL",
      [...Array(10).keys()].map((b) => (b < 8 ? `D${b}` : `D${b - 8}`)))[i],
  })),
  ...upDown(WROW, "WROWADV", DIRR, "LDWROW",
    [...Array(9).keys()].map((b) => (b < 6 ? `D${b + 2}` : `D${b - 6}`))),
]

/* -- CPTR: the copy engine's source -------------------------------------- */
const CCOL = [...Array(10).keys()].map((b) => `CC${b}`)
const CROW = [...Array(9).keys()].map((b) => `CR${b}`)
const cptr: Cell[] = [
  ...upDown(CCOL, "CSTEP", DIRC, "LDCCOL",
    [...Array(10).keys()].map((b) => (b < 8 ? `D${b}` : `D${b - 8}`))),
  ...upDown(CROW, "CROWADV", DIRR, "LDCROW",
    [...Array(9).keys()].map((b) => (b < 6 ? `D${b + 2}` : `D${b - 6}`))),
]

/* -- the copy's width and height ----------------------------------------
 *
 * The width is a register AND a working counter, because it reloads every row;
 * the height counts once, so its register IS the counter and software reloads
 * it for the next copy. */
const CW = [...Array(10).keys()].map((b) => `CW${b}`)
const CWN = [...Array(10).keys()].map((b) => `CWN${b}`)
const CH = [...Array(9).keys()].map((b) => `CH${b}`)
const counters: Cell[] = [
  ...CW.map((name, i) => ({
    pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`LDCW & ${i < 8 ? `D${i}` : `D${i - 8}`}`, `${name} & !LDCW`],
  })),
  ...CWN.map((name, i) => ({
    pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
    terms: loadable(CWN, "CSTEP", "CWLOAD", CW)[i],
  })),
  ...CH.map((name, i) => ({
    pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
    terms: loadable(CH, "CROWADV", "LDCH", [...Array(9).keys()].map((b) =>
      (b < 8 ? `D${b}` : "D0")))[i],
  })),
]

/* -- the span writer: graphics.md §7.4, inherited whole -------------------
 *
 * ⭐ The serialiser's serial output IS the register file's address bit 0, which
 * is what makes per-pixel colour selection free - so RFA and the serialiser are
 * on one part by construction, not by choice. */
const MASK = [...Array(8).keys()].map((b) => `MS${b}`)
const spanWriter: Cell[] = [
  ...MASK.map((name, i) => ({
    pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
    terms: i === 7
      ? [`WSTB & D7`, `!WSTB & !RETIRE & ${name}`]
      : [`WSTB & D${i}`, `!WSTB & RETIRE & MS${i + 1}`, `!WSTB & !RETIRE & ${name}`],
  })),
  ...[...Array(8).keys()].map((b) => ({
    pin: 0, name: `SL${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: loadable([...Array(8).keys()].map((i) => `SL${i}`), "RETIRE", "WSTB",
      [...Array(8).keys()].map((i) => `D${i}`))[b],
  })),
  ...[...Array(3).keys()].map((b) => ({
    pin: 0, name: `MK${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: counterTerms({ bits: [...Array(3).keys()].map((i) => `MK${i}`),
                          enable: "RETIRE", clear: "WSTB" })[b],
  })),
  ...[0, 1].map((b) => ({
    pin: 0, name: `WADV${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`LDWADV & D${b}`, `WADV${b} & !LDWADV`],
  })),
  { pin: 0, name: "SPANBUSY", assertedLow: false, s0: 1, registered: true,
    terms: ["WSTB", "SPANBUSY & !SPANEND"] },
  { pin: 0, name: "CBUSY", assertedLow: false, s0: 1, registered: true,
    terms: ["CGO", "CBUSY & !CDONE"] },
]

/* -- the address bus: TWO sources, and an output enable ------------------ */
const addressMux: Cell[] = [...Array(17).keys()].map((i) => {
  const bit = i + 2
  const w = bit >= 10 ? `WR${bit - 10}` : `WC${bit}`
  const c = bit >= 10 ? `CR${bit - 10}` : `CC${bit}`
  return {
    pin: 0, name: `FBA${bit}`, assertedLow: false, s0: 1 as const, registered: false,
    terms: [`!CRDSEL & ${w}`, `CRDSEL & ${c}`],
    oe: "FBOE",
  }
})

export const v3ptr: Merged = {
  name: "v3ptr",
  partNo: "ARM6309-V3P",
  location: "video3 - pointers, span writer, copy engine",
  device: "f1508ispplcc84",
  clock: "CLK25",
  inputs: [
    { name: "CLK25" }, { name: "RESET", activeLow: true },
    ...[0, 1, 2, 3, 4, 5, 6, 7].map((b) => ({ name: `D${b}` })),
    /* the span writer's handshake, from v3dot */
    { name: "WSTB" }, { name: "RETIRE" }, { name: "SPANEND" }, { name: "WINC" },
    { name: "WROWADV" }, { name: "LDWCOL" }, { name: "LDWROW" }, { name: "LDWADV" },
    /* the copy engine's, likewise */
    { name: "CGO" }, { name: "CDONE" }, { name: "CSTEP" }, { name: "CROWADV" },
    { name: "CWLOAD" }, ...(DIRR ? [{ name: "CDIRR" }] : []),
    ...(DIRC ? [{ name: "CDIRC" }] : []), { name: "CRDSEL" },
    { name: "LDCCOL" }, { name: "LDCROW" }, { name: "LDCW" }, { name: "LDCH" },
    /* the bus grant - one signal, from one place */
    { name: "FBOE" },
  ],
  cells: [...wptr, ...cptr, ...counters, ...spanWriter, ...addressMux],
  /* the address bus, and the three status bits v3host assembles into VSTAT */
  external: new Set([
    ...[...Array(17).keys()].map((i) => `FBA${i + 2}`),
    "SPANBUSY", "CBUSY",
  ]),
}

if (import.meta.main) {
  console.log(`v3ptr (copydir=${COPYDIR}): ${v3ptr.cells.length} cells, ` +
              `${v3ptr.inputs.length} declared inputs`)
  console.log(toCupl(v3ptr))
}
