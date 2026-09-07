/* A GAL22V10 assembler: product terms in, JEDEC out.
 *
 * This is the "fitter" gal/README.md's open item 1 says the design has never
 * been through. It does not minimise - the equations in mmu.pld and clkdec.pld
 * are already hand-minimised, and doing it again in here would hide the one
 * step worth checking. What it does is place terms in macrocells, refuse to do
 * it when they do not fit, and report what it used.
 *
 * The design is stated as a sum of products per macrocell. Signals carry their
 * own sense (RESET on a pin declared !RESET is asserted when the pin is low),
 * so the equations read the way the .pld reads.
 */

import {
  ARRAY_FUSES, AR_ROW, COLS, CONFIG_BASE, OLMC, OLMC_PINS, PIN_COL, ROWS,
  SIG_BASE, SP_ROW, TOTAL_FUSES, s0Fuse, s1Fuse,
} from "./gal22v10"

export interface Signal {
  name: string
  pin: number
  /** the pin is LOW when the signal is asserted - CUPL's `PIN n = !NAME` */
  activeLow?: boolean
  /** driven by a registered macrocell, whose feedback into the array is the
   *  complement of the register rather than the pin */
  registered?: boolean
}

export interface Cell {
  pin: number
  name: string
  /** documentation, and checked against s0 below */
  assertedLow: boolean
  registered?: boolean
  /** 1 = the pin follows the sum of products, 0 = the pin is its complement */
  s0: 0 | 1
  /** sum of products for F, the function the array forms. [] = never true */
  terms: string[]
  /** output-enable term; omitted means permanently enabled */
  oe?: string
  why?: string
}

export interface Design {
  name: string
  partNo: string
  location: string
  /** up to 8 characters into the 64-bit user signature */
  signature?: string
  /** set when this part is no longer a deliverable - the fit stands as the
   *  derivation behind a decision, but nothing burns this file into silicon.
   *  The text is stamped into the JEDEC header so a stray copy says so too. */
  supersededBy?: string
  clockPin?: number
  inputs: Signal[]
  cells: Cell[]
  /** macrocell pins left undriven so the pin can serve as an input */
  spares?: number[]
  ar?: string
  sp?: string
}

export interface CellUsage {
  pin: number
  name: string
  used: number
  available: number
  registered: boolean
  s0: 0 | 1
}

export interface Assembly {
  fuses: Uint8Array
  usage: CellUsage[]
  signals: Map<string, Signal>
}

const literalsOf = (term: string): { name: string; negated: boolean }[] => {
  const t = term.trim()
  if (t === "1") return []
  return t.split("&").map((raw) => {
    const s = raw.trim()
    const negated = s.startsWith("!")
    const name = (negated ? s.slice(1) : s).trim()
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) {
      throw new Error(`cannot parse literal "${s}" in term "${term}"`)
    }
    return { name, negated }
  })
}

/** Write one product term into a row: all ones, then punch in the literals. */
const writeRow = (
  fuses: Uint8Array, row: number, term: string, signals: Map<string, Signal>,
) => {
  const base = row * COLS
  fuses.fill(1, base, base + COLS)
  for (const lit of literalsOf(term)) {
    const sig = signals.get(lit.name)
    if (!sig) throw new Error(`unknown signal "${lit.name}" in term "${term}"`)
    const col = PIN_COL[sig.pin]
    if (col === undefined) throw new Error(`pin ${sig.pin} (${sig.name}) has no array column`)
    /* The literal wants the signal true; the column that carries the signal
     * true is the complement column when the pin itself is active low - and
     * again when the signal comes from a REGISTERED macrocell, because the
     * array is fed from the register's complement rather than from the pin.
     * See simulate.ts; this was wrong until 2026-09-07 and only Atmel's own
     * CUPL output could show it. */
    const flip = (lit.negated !== !!sig.activeLow) !== !!sig.registered
    fuses[base + col + (flip ? 1 : 0)] = 0
  }
}

export const assemble = (d: Design): Assembly => {
  const fuses = new Uint8Array(TOTAL_FUSES) // all zero: every term false, every output high-Z

  /* Pins before terms: a design can be perfectly reasonable and simply have
   * more signals than the package has holes. Reporting that as a conflict on
   * whichever pin happened to collide tells you nothing; reporting the budget
   * tells you what to change. */
  {
    const dedicated = d.clockPin === undefined ? 12 : 11
    const free = OLMC_PINS.length - d.cells.length
    const available = dedicated + free
    if (d.inputs.length > available) {
      throw new Error(
        `${d.name}: ${d.inputs.length} inputs need pins and the part has ` +
        `${available} - ${dedicated} dedicated` +
        `${d.clockPin === undefined ? "" : " (pin 1 is the clock)"} plus ` +
        `${free} macrocell${free === 1 ? "" : "s"} not used as an output. ` +
        `Every output costs an input pin as well as a macrocell.`,
      )
    }
  }

  const signals = new Map<string, Signal>()
  const claimed = new Map<number, string>()
  const claim = (pin: number, name: string) => {
    const prev = claimed.get(pin)
    if (prev) throw new Error(`pin ${pin} is both ${prev} and ${name}`)
    claimed.set(pin, name)
  }
  for (const s of d.inputs) { claim(s.pin, s.name); signals.set(s.name, s) }
  for (const c of d.cells) {
    claim(c.pin, c.name)
    /* A macrocell's own output feeds back into the array, so it is a signal
     * like any other. Its sense is the pin's sense. */
    signals.set(c.name, {
      name: c.name, pin: c.pin, activeLow: c.assertedLow, registered: c.registered,
    })
  }
  for (const pin of d.spares ?? []) claim(pin, "(spare)")
  if (d.clockPin !== undefined && !claimed.has(d.clockPin)) claimed.set(d.clockPin, "(clock)")

  /* Every macrocell starts combinational. That is not cosmetic: a macrocell
   * whose pin is used as an INPUT must be combinational, because a registered
   * macrocell feeds the array from its register and never sees the pin. */
  for (const pin of OLMC_PINS) { fuses[s0Fuse(pin)] = 1; fuses[s1Fuse(pin)] = 1 }

  const usage: CellUsage[] = []
  for (const c of d.cells) {
    const cell = OLMC[c.pin]
    if (!cell) throw new Error(`pin ${c.pin} (${c.name}) is not a macrocell`)
    if (c.terms.length > cell.terms) {
      throw new Error(
        `${c.name} needs ${c.terms.length} product terms; the macrocell on ` +
        `pin ${c.pin} has ${cell.terms}`,
      )
    }
    c.terms.forEach((t, i) => writeRow(fuses, cell.firstRow + i, t, signals))
    writeRow(fuses, cell.oeRow, c.oe ?? "1", signals)
    fuses[s0Fuse(c.pin)] = c.s0
    fuses[s1Fuse(c.pin)] = c.registered ? 0 : 1
    usage.push({
      pin: c.pin, name: c.name, used: c.terms.length, available: cell.terms,
      registered: !!c.registered, s0: c.s0,
    })
  }

  if (d.ar) writeRow(fuses, AR_ROW, d.ar, signals)
  if (d.sp) writeRow(fuses, SP_ROW, d.sp, signals)

  if (d.signature) {
    if (d.signature.length > 8) throw new Error("the user signature holds 8 characters")
    for (let i = 0; i < d.signature.length; i++) {
      const ch = d.signature.charCodeAt(i)
      if (ch > 0x7f) throw new Error("the user signature is ASCII")
      for (let b = 0; b < 8; b++) fuses[SIG_BASE + i * 8 + b] = ((ch << b) & 0x80) ? 1 : 0
    }
  }

  return { fuses, usage, signals }
}

/* -- JEDEC ---------------------------------------------------------------- */

/** 16-bit sum of the fuse array packed 8 bits to a byte, least significant
 *  bit first. Every fuse counts, including the rows we do not print. */
export const fuseChecksum = (fuses: Uint8Array): number => {
  let sum = 0, byte = 0, bit = 0
  for (const f of fuses) {
    if (f) byte |= 1 << bit
    if (++bit === 8) { sum = (sum + byte) & 0xffff; byte = 0; bit = 0 }
  }
  return (sum + byte) & 0xffff
}

const transmissionChecksum = (text: string): number => {
  let sum = 0
  for (let i = 0; i < text.length; i++) sum = (sum + text.charCodeAt(i)) & 0xffff
  return sum
}

const hex4 = (n: number) => n.toString(16).padStart(4, "0")

export const toJedec = (d: Design, a: Assembly): string => {
  const lines: string[] = []
  lines.push(`GAL-Assembler:  hardware/gal/jedec, arm6309`)
  lines.push(`Device:         GAL22V10  (Atmel ATF22V10C, GAL mode, ${TOTAL_FUSES} fuses)`)
  lines.push(`Name:           ${d.name}`)
  lines.push(`PartNo:         ${d.partNo}`)
  lines.push(`Location:       ${d.location}`)
  if (d.supersededBy) {
    lines.push(``)
    lines.push(`*** SUPERSEDED - DO NOT PROGRAM ***`)
    lines.push(`    ${d.supersededBy}`)
    lines.push(`    This fit is kept as the derivation behind that decision.`)
  }
  lines.push(``)
  lines.push(`*F0`)   // unlisted fuses default to 0
  lines.push(`*G0`)   // security fuse unprogrammed
  lines.push(`*QP24`)
  lines.push(`*QF${TOTAL_FUSES}`)

  /* Nothing but fuse data goes after an *L. A JEDEC field runs to the next
   * asterisk, so a comment on one of these lines is read as fuses. The
   * annotated version of this map is the .doc report, not this file. */
  const emit = (from: number, to: number) => {
    lines.push(`*L${String(from).padStart(4, "0")} ${Array.from(a.fuses.slice(from, to)).join("")}`)
  }
  for (let row = 0; row < ROWS; row++) emit(row * COLS, row * COLS + COLS)
  emit(CONFIG_BASE, SIG_BASE)
  emit(SIG_BASE, TOTAL_FUSES)
  lines.push(`*C${hex4(fuseChecksum(a.fuses))}`)
  lines.push(`*`)

  const body = `\x02\n${lines.join("\n")}\n\x03`
  return `${body}${hex4(transmissionChecksum(body))}\n`
}

/* The fitter's report: what went where, and how much of the part is left.
 * This is the artefact gal/README.md open item 1 actually wants. */
export const toReport = (d: Design, a: Assembly): string => {
  const out: string[] = []
  out.push(`${d.name} - ${d.partNo}, ${d.location}`)
  if (d.supersededBy) {
    out.push(`*** SUPERSEDED - DO NOT PROGRAM *** ${d.supersededBy}`)
  }
  out.push(`GAL22V10, ${TOTAL_FUSES} fuses, checksum ${hex4(fuseChecksum(a.fuses))}`)
  out.push(``)
  out.push(`  pin  signal      terms  of   path           polarity`)
  out.push(`  ---  ----------  -----  ---  -------------  ------------------`)
  for (const u of [...a.usage].sort((x, y) => x.pin - y.pin)) {
    out.push(
      `  ${String(u.pin).padStart(3)}  ${u.name.padEnd(10)}  ` +
      `${String(u.used).padStart(5)}  ${String(u.available).padStart(3)}  ` +
      `${(u.registered ? "registered" : "combinational").padEnd(13)}  ` +
      `${u.s0 ? "pin follows terms" : "pin is complement"}`,
    )
  }
  for (const pin of d.spares ?? []) {
    out.push(`  ${String(pin).padStart(3)}  ${"(spare)".padEnd(10)}  ${"-".padStart(5)}  ` +
      `${String(OLMC[pin].terms).padStart(3)}  undriven       usable as an input`)
  }
  const notes = d.cells.filter((c) => c.why)
  if (notes.length) {
    out.push(``)
    for (const c of notes) out.push(`  ${c.name}: ${c.why}`)
  }

  /* The pin budget gal/README.md works out by hand: available inputs are the
   * dedicated pins plus every macrocell not used as an output. Pin 1 is a
   * dedicated input unless the design needs it as the one clock the part has. */
  const outputs = a.usage.length
  const freeMacrocells = OLMC_PINS.length - outputs
  const dedicated = d.clockPin === undefined ? 12 : 11
  const available = dedicated + freeMacrocells
  const used = d.inputs.length
  out.push(``)
  out.push(`  ${outputs} outputs, ${freeMacrocells} macrocell${freeMacrocells === 1 ? "" : "s"} not driven.`)
  out.push(`  Inputs: ${used} used of ${available} available ` +
    `(${dedicated} dedicated${d.clockPin === undefined ? "" : " - pin 1 is the clock"}, ` +
    `${freeMacrocells} free macrocell${freeMacrocells === 1 ? "" : "s"}) - ` +
    `${available - used} spare.`)
  out.push(``)

  const rowLabel: string[] = []
  rowLabel[AR_ROW] = "AR  asynchronous reset"
  rowLabel[SP_ROW] = "SP  synchronous preset"
  for (const m of Object.values(OLMC)) {
    rowLabel[m.oeRow] = `pin ${m.pin} OE`
    for (let i = 0; i < m.terms; i++) rowLabel[m.firstRow + i] = `pin ${m.pin} term ${i}`
  }
  out.push(`  fuse map - 0 is an intact link, so an all-zero row is never true`)
  out.push(``)
  for (let row = 0; row < ROWS; row++) {
    const base = row * COLS
    const bits = Array.from(a.fuses.slice(base, base + COLS)).join("")
    const used = bits.includes("0") && bits.includes("1")
    const blank = /^0+$/.test(bits) ? "  (never)" : /^1+$/.test(bits) ? "  (always)" : ""
    out.push(`  L${String(base).padStart(4, "0")} ${bits}  ${rowLabel[row]}${used ? "" : blank}`)
  }
  const cfg = Array.from(a.fuses.slice(CONFIG_BASE, SIG_BASE)).join("")
  out.push(`  L${CONFIG_BASE} ${cfg}  S0,S1 per macrocell, pin 14 first`)
  const sig = Array.from(a.fuses.slice(SIG_BASE, TOTAL_FUSES)).join("")
  out.push(`  L${SIG_BASE} ${sig}  user signature${d.signature ? ` "${d.signature}"` : ""}`)
  return out.join("\n") + "\n"
}
