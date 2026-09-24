/* A sum of products from a truth table - for the decodes that are arithmetic
 * (a two-bit add, a parity) rather than a range, where expanding the XORs by
 * hand is where the mistakes live.
 *
 * Quine-McCluskey to the prime implicants, then a greedy cover: essential
 * primes first, then whichever prime covers the most minterms still open. Not
 * guaranteed minimal, and it does not need to be - the fitter minimises again;
 * what this guarantees is that the terms are EXACTLY the function, which
 * `sopCheck` asserts by enumeration. */

type Imp = { mask: number; bits: number; covers: Set<number> }

export const sop = (vars: string[], f: (v: Record<string, boolean>) => boolean): string[] => {
  const n = vars.length
  const env = (m: number) =>
    Object.fromEntries(vars.map((name, i) => [name, ((m >> i) & 1) === 1]))
  const ones: number[] = []
  for (let m = 0; m < 1 << n; m++) if (f(env(m))) ones.push(m)
  if (ones.length === 0) return []
  if (ones.length === 1 << n) return ["1"]

  /* combine implicants differing in one cared-for bit until nothing merges */
  let level: Imp[] = ones.map((m) => ({ mask: 0, bits: m, covers: new Set([m]) }))
  const primes: Imp[] = []
  while (level.length) {
    const next = new Map<string, Imp>()
    const used = new Set<Imp>()
    for (let i = 0; i < level.length; i++) {
      for (let j = i + 1; j < level.length; j++) {
        const a = level[i], b = level[j]
        if (a.mask !== b.mask) continue
        const d = a.bits ^ b.bits
        if (d & (d - 1)) continue
        const mask = a.mask | d, bits = a.bits & ~d
        const key = `${mask}:${bits}`
        if (!next.has(key)) next.set(key, { mask, bits, covers: new Set([...a.covers, ...b.covers]) })
        used.add(a); used.add(b)
      }
    }
    for (const imp of level) if (!used.has(imp)) primes.push(imp)
    level = [...next.values()]
  }

  /* cover */
  const open = new Set(ones)
  const chosen: Imp[] = []
  for (const m of ones) {
    const cands = primes.filter((p) => p.covers.has(m))
    if (cands.length === 1 && !chosen.includes(cands[0])) chosen.push(cands[0])
  }
  for (const p of chosen) for (const m of p.covers) open.delete(m)
  while (open.size) {
    let best = primes[0], bestN = -1
    for (const p of primes) {
      const k = [...p.covers].filter((m) => open.has(m)).length
      if (k > bestN) { best = p; bestN = k }
    }
    chosen.push(best)
    for (const m of best.covers) open.delete(m)
  }

  const terms = chosen.map((p) =>
    vars.map((name, i) => ((p.mask >> i) & 1 ? null : ((p.bits >> i) & 1 ? name : `!${name}`)))
      .filter((l): l is string => l !== null).join(" & "))
  if (!sopCheck(vars, f, terms)) throw new Error(`sop: cover of [${vars}] is wrong`)
  return terms
}

/** true when the sum of products `terms` is exactly `f` over every input */
export const sopCheck = (vars: string[], f: (v: Record<string, boolean>) => boolean,
                         terms: string[]): boolean => {
  for (let m = 0; m < 1 << vars.length; m++) {
    const v = Object.fromEntries(vars.map((name, i) => [name, ((m >> i) & 1) === 1]))
    const got = terms.some((t) => t === "1" || t.split(" & ").every((l) =>
      l.startsWith("!") ? !v[l.slice(1)] : v[l]))
    if (got !== f(v)) return false
  }
  return true
}
