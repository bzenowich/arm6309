/* A GAL22V10 that runs on the fuses.
 *
 * The point of this file is that it does not read the design. It reads the
 * .jed we are about to hand a programmer, reconstructs the AND array and the
 * macrocell configuration out of the bits, and evaluates. Whatever the
 * equations meant, this is what the part will do.
 *
 * That makes the check in ../jedec.check.ts a comparison between the fuses and
 * the models in mmu.model.ts and clkdec.model.ts, rather than a restatement of
 * the equations. It cannot catch an error in gal22v10.ts - see the note on
 * provenance there - but it catches everything downstream of it.
 */

import {
  AR_ROW, COL_NEG, COL_PIN, COLS, OLMC, ROWS, SP_ROW, TOTAL_FUSES,
  s0Fuse, s1Fuse,
} from "./gal22v10"

export interface Parsed {
  fuses: Uint8Array
  declaredFuses: number
  declaredChecksum: number | null
}

export const parseJedec = (text: string): Parsed => {
  const stx = text.indexOf("\x02")
  const etx = text.indexOf("\x03")
  if (stx < 0 || etx < 0) throw new Error("no STX/ETX in the JEDEC file")
  const body = text.slice(stx + 1, etx)

  let declaredFuses = TOTAL_FUSES
  let dflt = 0
  let declaredChecksum: number | null = null

  const qf = body.match(/\*QF(\d+)/)
  if (qf) declaredFuses = Number(qf[1])
  const f = body.match(/\*F([01])/)
  if (f) dflt = Number(f[1])
  const c = body.match(/\*C([0-9a-fA-F]{1,4})/)
  if (c) declaredChecksum = parseInt(c[1], 16)

  const fuses = new Uint8Array(declaredFuses).fill(dflt)
  for (const m of body.matchAll(/\*L(\d+)([\s01]+)/g)) {
    const at = Number(m[1])
    const bits = m[2].replace(/\s/g, "")
    for (let i = 0; i < bits.length; i++) {
      if (at + i >= declaredFuses) throw new Error(`fuse ${at + i} is past *QF${declaredFuses}`)
      fuses[at + i] = bits[i] === "1" ? 1 : 0
    }
  }
  return { fuses, declaredFuses, declaredChecksum }
}

type Literal = { pin: number; want: 0 | 1 }

export class Gal22v10 {
  readonly fuses: Uint8Array
  private readonly rows: Literal[][] = []
  /* A row holding both a signal and its complement can never be true. Every
   * unused product term is exactly that - all 44 links intact - so this is
   * what keeps an unused row from being 44 signal lookups, and what keeps it
   * from reaching for pins the design never drives. */
  private readonly contradiction: boolean[] = []
  /** register state, indexed by macrocell pin */
  readonly regs = new Map<number, 0 | 1>()
  private readonly level = new Int8Array(25)
  private readonly resolving = new Set<number>()

  constructor(fuses: Uint8Array) {
    if (fuses.length !== TOTAL_FUSES) {
      throw new Error(`${fuses.length} fuses, expected ${TOTAL_FUSES}`)
    }
    this.fuses = fuses
    for (let row = 0; row < ROWS; row++) {
      const lits: Literal[] = []
      for (let col = 0; col < COLS; col++) {
        /* 0 is an intact link: this literal is part of the term. */
        if (fuses[row * COLS + col] === 0) {
          lits.push({ pin: COL_PIN[col], want: COL_NEG[col] ? 0 : 1 })
        }
      }
      this.rows.push(lits)
      const want = new Map<number, 0 | 1>()
      this.contradiction.push(lits.some((l) => {
        const seen = want.get(l.pin)
        if (seen === undefined) { want.set(l.pin, l.want); return false }
        return seen !== l.want
      }))
    }
    this.reset()
  }

  registered = (pin: number) => this.fuses[s1Fuse(pin)] === 0
  polarityHigh = (pin: number) => this.fuses[s0Fuse(pin)] === 1

  /** a row that can never be true - the assembler writes unused terms and
   *  disabled output enables as all-zero rows, which is exactly that */
  neverTrue = (row: number) => this.contradiction[row]

  /** true when the macrocell never drives its pin, so the pin is an input */
  undriven = (pin: number) => this.neverTrue(OLMC[pin].oeRow)

  reset() {
    for (const pin of Object.keys(OLMC).map(Number)) this.regs.set(pin, 0)
  }

  private row(r: number): 0 | 1 {
    if (this.contradiction[r]) return 0
    for (const lit of this.rows[r]) if (this.resolve(lit.pin) !== lit.want) return 0
    return 1
  }

  private sop(pin: number): 0 | 1 {
    const m = OLMC[pin]
    for (let i = 0; i < m.terms; i++) if (this.row(m.firstRow + i)) return 1
    return 0
  }

  private resolve(pin: number): number {
    const v = this.level[pin]
    if (v !== -2) return v
    const m = OLMC[pin]
    if (!m) throw new Error(`pin ${pin} is not driven and is not a macrocell`)
    if (this.resolving.has(pin)) throw new Error(`combinational loop through pin ${pin}`)
    this.resolving.add(pin)
    let out: number
    if (this.registered(pin)) {
      /* THE ARRAY SEES THE COMPLEMENT OF Q, not the pin level. Established
       * 2026-09-07 against Atmel CUPL's own JEDEC for clkdec.pld: CUPL emits
       * `C0.d = !C0` as the single literal C0 rather than !C0, which only
       * evaluates to a working counter if the feedback is inverted. Our own
       * map, written the other way, worked only under the other assumption -
       * and every check passed either way, because the assembler and this
       * file shared the mistake. */
      out = 1 - this.regs.get(pin)!
    } else if (!this.row(m.oeRow)) {
      out = -1 // high-Z, and nothing external is driving it
    } else {
      const f = this.sop(pin)
      out = this.polarityHigh(pin) ? f : 1 - f
    }
    this.resolving.delete(pin)
    this.level[pin] = out
    return out
  }

  /** The level a registered macrocell drives on its PIN, which applies S0 and
   *  is not what the array sees. */
  pinLevel(pin: number): number {
    const q = this.regs.get(pin)!
    return this.polarityHigh(pin) ? q : 1 - q
  }

  /** Apply a set of externally driven pins and read every pin back.
   *  -1 in the result is high-Z.
   *
   *  Returns a COPY. It used to return the internal buffer, which meant two
   *  evaluate() calls kept in two variables silently aliased each other - a
   *  check comparing "before" against "after" then compared "after" with
   *  itself and passed for the wrong reason. Found in access.check.ts. */
  evaluate(driven: Record<number, 0 | 1>): Int8Array {
    this.level.fill(-2)
    for (const [pin, v] of Object.entries(driven)) this.level[Number(pin)] = v
    /* The asynchronous reset is a level, not an edge: while its term is true
     * the registers are held at zero. */
    if (this.row(AR_ROW)) { this.reset(); this.level.fill(-2)
      for (const [pin, v] of Object.entries(driven)) this.level[Number(pin)] = v }
    for (const pin of Object.keys(OLMC).map(Number)) this.resolve(pin)
    /* Report the pin, not the feedback, for registered macrocells. */
    const out = this.level.slice()
    for (const pin of Object.keys(OLMC).map(Number)) {
      if (this.registered(pin) && !(pin in driven)) out[pin] = this.pinLevel(pin)
    }
    return out
  }

  /** One rising edge on pin 1. */
  clock(driven: Record<number, 0 | 1>) {
    this.evaluate(driven)
    if (this.row(AR_ROW)) { this.reset(); return }
    const preset = this.row(SP_ROW)
    const next = new Map<number, 0 | 1>()
    for (const pin of Object.keys(OLMC).map(Number)) {
      if (!this.registered(pin)) continue
      next.set(pin, preset ? 1 : this.sop(pin))
    }
    for (const [pin, v] of next) this.regs.set(pin, v)
  }

  /* -- structural checks the design can get wrong ------------------------- */

  /** A macrocell pin used as an input must never drive, and must be
   *  combinational: a registered macrocell feeds the array from its register
   *  and the pin is not an input at all. */
  checkInputPins(pins: number[]): string[] {
    const bad: string[] = []
    for (const pin of pins) {
      if (!OLMC[pin]) continue
      if (!this.undriven(pin)) bad.push(`pin ${pin} is driven by its macrocell and from outside`)
      if (this.registered(pin)) bad.push(`pin ${pin} is registered, so its pin is not an array input`)
    }
    return bad
  }

  /** Feedback from a registered macrocell is taken after the polarity bit in
   *  this model (datasheet 4.7: reset drives the register low and "the output
   *  state will depend on the polarity of the output buffer"). Where every
   *  registered macrocell that is read back has S0 = 1, the two possible
   *  readings agree and the assumption carries no weight. */
  polarityAssumptionMatters(): number[] {
    const read = new Set<number>()
    /* Only live rows count. Every unused product term is all-zero, which puts
     * a literal for all 22 signals in it, and reading those would name every
     * macrocell on the part. */
    this.rows.forEach((lits, row) => {
      if (this.neverTrue(row)) return
      for (const l of lits) if (OLMC[l.pin]) read.add(l.pin)
    })
    return [...read].filter((p) => this.registered(p) && !this.polarityHigh(p))
  }
}
