/* Range compares on a counter, as product terms.
 *
 * The video card's sync GALs are almost entirely "is the line counter inside
 * this window", four times over with two of the windows mode-dependent. Doing
 * that by hand for a 10-bit counter is how a raster ends up one line short in
 * a way no simulation of the equations would catch, because the equations
 * would be checked against themselves.
 *
 * The decomposition is the ordinary one - split [lo, hi] into aligned blocks,
 * each of which is a fixed prefix with the low bits free, so one product term
 * each. What makes the result short is the second pass: the counter never
 * exceeds its modulus, so a literal can be dropped whenever doing so cannot
 * pull in a value the counter can actually reach. That is what turns "v = 448"
 * on a 10-bit counter into V8 & V7 & V6 rather than ten literals.
 *
 * Every result is verified exhaustively against the arithmetic predicate over
 * 0..max before it is returned. That is at most 1024 evaluations.
 */

import { reduceConjunctions } from "./minimise"

export interface RangeSpec {
  /** bit names, least significant first */
  bits: string[]
  /** inclusive window */
  lo: number
  hi: number
  /** the largest value the counter can reach - the modulus minus one */
  max: number
  /** literals ANDed into every term, e.g. a mode select */
  qualify?: string[]
}

/** A cube: for each bit, 1, 0 or null for "free". */
type Cube = (0 | 1 | null)[]

const cubeMatches = (c: Cube, v: number) =>
  c.every((b, i) => b === null || b === ((v >> i) & 1))

/** [lo, hi] as aligned power-of-two blocks. */
const blocks = (lo: number, hi: number, width: number): Cube[] => {
  const out: Cube[] = []
  let v = lo
  while (v <= hi) {
    /* the largest aligned block starting at v that still fits under hi */
    let k = 0
    while (k < width && (v & ((1 << (k + 1)) - 1)) === 0 && v + (1 << (k + 1)) - 1 <= hi) k++
    const cube: Cube = []
    for (let i = 0; i < width; i++) cube.push(i < k ? null : (((v >> i) & 1) as 0 | 1))
    out.push(cube)
    v += 1 << k
  }
  return out
}

export const rangeTerms = (spec: RangeSpec): string[] => {
  const { bits, lo, hi, max, qualify = [] } = spec
  const width = bits.length
  if (hi < lo) return []
  const inWindow = (v: number) => v >= lo && v <= hi

  const cubes = blocks(lo, hi, width).map((cube) => {
    /* Drop every literal that is not doing work, given that the counter
     * cannot exceed max. Greedy from the top bit down, which is where the
     * redundancy is. */
    const c = [...cube]
    for (let i = width - 1; i >= 0; i--) {
      if (c[i] === null) continue
      const was = c[i]
      c[i] = null
      let ok = true
      for (let v = 0; v <= max && ok; v++) if (cubeMatches(c, v) && !inWindow(v)) ok = false
      if (!ok) c[i] = was
    }
    return c
  })

  /* The decomposition is exact by construction and the reduction is checked
   * per literal, but the whole thing is cheap to verify outright. */
  for (let v = 0; v <= max; v++) {
    const covered = cubes.some((c) => cubeMatches(c, v))
    if (covered !== inWindow(v)) {
      throw new Error(
        `range [${lo},${hi}] over 0..${max}: value ${v} is ` +
        `${covered ? "covered but outside" : "inside but not covered"}`,
      )
    }
  }

  const terms = cubes.map((c) => {
    const lits = [...qualify]
    for (let i = width - 1; i >= 0; i--) {
      if (c[i] === null) continue
      lits.push(c[i] === 1 ? bits[i] : `!${bits[i]}`)
    }
    return lits.join(" & ")
  })
  /* Two blocks can reduce onto the same cube, or onto cubes where one covers
   * the other. That is a counting artefact of the decomposition. */
  return reduceConjunctions(terms)
}

/** Union of ranges, e.g. a blanking window that wraps the origin. */
export const unionTerms = (specs: RangeSpec[]): string[] => specs.flatMap(rangeTerms)
