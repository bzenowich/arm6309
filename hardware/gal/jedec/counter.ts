/* Binary counter equations, generated rather than hand-expanded.
 *
 * clkdec.pld's four counter bits were written out by hand and that was already
 * the fiddliest part of it. The video card's sync GALs want an 8-bit slot
 * counter and a 10-bit line counter, both with a clock enable and both
 * wrapping on a modulus that is not a power of two, and hand-expanding
 * eighteen of those is not a thing to do eighteen times.
 *
 * A bit of a binary up-counter is Q XOR (all lower bits set). With a wrap it
 * is that, suppressed at the terminal count; with a clock enable it holds
 * otherwise. Written as a sum of products:
 *
 *     D_i = EN & !TC & Q_i & !C_i        (some lower bit is clear: hold high)
 *         # EN & !TC & !Q_i & C_i        (carry in: go high)
 *         # !EN & Q_i                    (disabled: hold)
 *
 * where C_i is the AND of Q_0..Q_i-1. !C_i and !TC are complements of ANDs and
 * expand to one term per literal, so the products multiply out and then mostly
 * subsume each other - which is why this reduces afterwards rather than
 * trying to be clever up front.
 */

export interface CounterSpec {
  /** bit names, least significant first */
  bits: string[]
  /** conjunction that must hold for the counter to advance; always if absent.
   *  A partial decode of another counter is a normal thing to put here - the
   *  video card's line counter advances on "CE & H7 & H6 & H2 & H1 & H0",
   *  which is the slot counter's terminal count and costs no macrocell. */
  enable?: string
  /** terminal count as a conjunction of this counter's own bits, e.g.
   *  "H7 & H6 & H2 & H1 & H0". A partial decode is fine and is usually right:
   *  the counter never passes its modulus, so the zero bits need not be
   *  tested. Absent means free-running to the full width. */
  terminal?: string
  /** literal that clears the counter synchronously, e.g. a mode change */
  clear?: string
}

import { literalsOf, negate, reduceTerms } from "./minimise"

/** Product terms for each bit, in the order the bits were given. */
export const counterTerms = (spec: CounterSpec): string[][] => {
  const { bits, enable, terminal, clear } = spec
  /* Not counting means holding, and both the terminal count and an explicit
   * clear force zero, so they are the same suppression. */
  const stop = [
    ...(terminal ? [literalsOf(terminal)] : []),
    ...(clear ? [[clear]] : []),
  ]
  /* !(stop) as a sum of products: one alternative per stop condition, and each
   * alternative contributes the complement of one of its literals. */
  const notStop: string[][] = stop.length === 0
    ? [[]]
    : stop.reduce<string[][]>(
      (acc, cond) => acc.flatMap((prefix) => cond.map((l) => [...prefix, negate(l)])),
      [[]],
    )

  return bits.map((q, i) => {
    const carry = bits.slice(0, i)
    const en = enable ? literalsOf(enable) : []
    /* Holding costs one term per literal of the enable, because !EN is the
     * complement of a conjunction. */
    const notEn = en.map((l) => [negate(l), q])
    const terms: string[][] = []
    /* hold high: any lower bit clear */
    for (const lower of carry) {
      for (const ns of notStop) terms.push([...en, ...ns, q, negate(lower)])
    }
    /* go high on carry in */
    for (const ns of notStop) terms.push([...en, ...ns, negate(q), ...carry])
    /* disabled: hold */
    terms.push(...notEn)
    return reduceTerms(terms).map((t) => t.join(" & "))
  })
}

/** The same counter, as arithmetic - the reference the terms are checked
 *  against. Returns the next value. */
export const counterNext = (
  value: number, opts: { enable: boolean; modulus: number; clear?: boolean },
): number => {
  if (!opts.enable) return value
  if (opts.clear) return 0
  return value + 1 >= opts.modulus ? 0 : value + 1
}

/** A loadable counter: load wins, then count if enabled, else hold. The
 *  generator gives the count-or-hold half; the load is one term per bit and has
 *  to qualify the other two.
 *
 *  Lived in scan.jedec.ts until 2026-09-08, when 6.4's map column counter
 *  became the second user (video.parts.ts). Same equations, one home. */
export const loadable = (
  bits: string[], enable: string, load: string, from: string[],
): string[][] => {
  const counted = counterTerms({ bits, enable })
  return bits.map((_, i) => [
    `${load} & ${from[i]}`,
    ...counted[i].map((t) => `!${load} & ${t}`),
  ])
}
