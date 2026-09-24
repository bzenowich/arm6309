/* The only minimisation in this fitter, and it is deliberately the weak kind.
 *
 * assemble.ts does not minimise - mmu.pld and clkdec.pld were hand-minimised
 * and doing it again would hide the step worth checking. The generators in
 * counter.ts and range.ts are different: they emit terms mechanically, and
 * mechanical emission produces duplicates and terms that are wholly covered by
 * a shorter one. Removing those is bookkeeping, not optimisation - it cannot
 * change the function, only the count.
 *
 * What this is NOT is a Quine-McCluskey or Espresso pass. It will not spot
 * that A&B # A&!B is A. If a generated equation is over its macrocell budget,
 * the answer is a better decomposition, not a better minimiser.
 */

export const negate = (lit: string) => (lit.startsWith("!") ? lit.slice(1) : `!${lit}`)

export const literalsOf = (conj: string) =>
  conj.split("&").map((s) => s.trim()).filter((s) => s.length > 0)

/** Drop contradictions, duplicates, and any term implied by a shorter one. */
export const reduceTerms = (terms: string[][]): string[][] => {
  const sets = terms.map((t) => new Set(t))
  const keep: string[][] = []
  for (let i = 0; i < terms.length; i++) {
    if (terms[i].some((l) => sets[i].has(negate(l)))) continue // A & !A
    const subsumed = terms.some((_, j) =>
      j !== i && sets[j].size <= sets[i].size &&
      !(sets[j].size === sets[i].size && j > i) && // on a tie, keep the first
      [...sets[j]].every((l) => sets[i].has(l)))
    if (!subsumed) keep.push([...sets[i]])
  }
  return keep
}

export const reduceConjunctions = (terms: string[]): string[] =>
  reduceTerms(terms.map(literalsOf)).map((t) => t.join(" & "))
