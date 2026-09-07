/* An exact-ish two-level minimiser, written to answer one question the vendor
 * tools would not answer.
 *
 * The ATF1508 fitter gets a design smaller three ways: Espresso, output
 * polarity selection, and foldback. Our GAL flow does none of them. CUPL was
 * the obvious way to measure what that costs - it is already installed and it
 * is the second implementation that found our two fuse-map errors - and on the
 * first two counts it turned out not to be:
 *
 *   * -m3 saved 11 product terms across every GAL in the machine, 1.9%, and
 *     none of them on an equation that was binding.
 *   * It does not choose polarity by cost at all. Given NARROW = !(A#B#C#D)
 *     it stores A#B#C#D - four rows - and sets the polarity fuse, when
 *     !A&!B&!C&!D is one row and needs no fuse. Confirmed in the fuse plot.
 *
 * So the polarity question needs minimum-SOP for f AND for !f, which means
 * doing it here. Quine-McCluskey for the prime implicants, then essential
 * implicants and a greedy cover for the rest. Greedy is not guaranteed
 * minimal, which only matters in one direction: a reported saving is real,
 * and a reported no-saving might be understating the case.
 */

export interface Cube { /* bit i: 1 = literal true, 0 = false, - = absent */
  ones: number
  mask: number   // 1 where the variable appears
}

const bits = (x: number) => { let n = 0; while (x) { n += x & 1; x >>>= 1 } return n }

/** Expand a list of cubes over `n` variables into the minterms they cover. */
export const onSet = (cubes: Cube[], n: number): Set<number> => {
  const out = new Set<number>()
  const full = (1 << n) - 1
  for (const c of cubes) {
    const free = full & ~c.mask
    /* Walk the subsets of the free bits - the standard trick, and the reason
     * this is fine at n = 16: it is the size of the cube, not of the space. */
    for (let s = free; ; s = (s - 1) & free) {
      out.add((c.ones & c.mask) | s)
      if (s === 0) break
    }
  }
  return out
}

/** Prime implicants of an on-set over n variables, by Quine-McCluskey. */
export const primes = (on: Set<number>, n: number): Cube[] => {
  const full = (1 << n) - 1
  let layer: Cube[] = [...on].map((m) => ({ ones: m, mask: full }))
  const out: Cube[] = []
  while (layer.length) {
    const used = new Set<number>()
    const next = new Map<string, Cube>()
    for (let i = 0; i < layer.length; i++) {
      for (let j = i + 1; j < layer.length; j++) {
        const a = layer[i], b = layer[j]
        if (a.mask !== b.mask) continue
        const diff = (a.ones ^ b.ones) & a.mask
        if (bits(diff) !== 1) continue
        used.add(i); used.add(j)
        const c = { ones: a.ones & ~diff, mask: a.mask & ~diff }
        next.set(`${c.ones}:${c.mask}`, c)
      }
    }
    layer.forEach((c, i) => { if (!used.has(i)) out.push(c) })
    layer = [...next.values()]
  }
  return out
}

/** Minimum-ish cover: essentials, then greedy on what is left. */
export const cover = (on: Set<number>, pis: Cube[], n: number): Cube[] => {
  const covers = pis.map((p) => [...on].filter((m) => (m & p.mask) === (p.ones & p.mask)))
  const byMinterm = new Map<number, number[]>()
  covers.forEach((ms, i) => ms.forEach((m) => {
    if (!byMinterm.has(m)) byMinterm.set(m, [])
    byMinterm.get(m)!.push(i)
  }))
  const chosen = new Set<number>()
  for (const [, is] of byMinterm) if (is.length === 1) chosen.add(is[0])

  const left = new Set(on)
  for (const i of chosen) covers[i].forEach((m) => left.delete(m))
  while (left.size) {
    let best = -1, bestN = 0
    covers.forEach((ms, i) => {
      if (chosen.has(i)) return
      const c = ms.filter((m) => left.has(m)).length
      if (c > bestN) { bestN = c; best = i }
    })
    if (best < 0) break
    chosen.add(best)
    covers[best].forEach((m) => left.delete(m))
  }
  return [...chosen].map((i) => pis[i])
}

export const minimalTerms = (cubes: Cube[], n: number): number => {
  const on = onSet(cubes, n)
  if (on.size === 0) return 0
  if (on.size === 1 << n) return 1
  return cover(on, primes(on, n), n).length
}

/** Both polarities of the same function, as product-term counts. */
export const bothPolarities = (cubes: Cube[], n: number) => {
  const on = onSet(cubes, n)
  const off = new Set<number>()
  for (let m = 0; m < (1 << n); m++) if (!on.has(m)) off.add(m)
  const count = (s: Set<number>) =>
    s.size === 0 ? 0 : s.size === (1 << n) ? 1 : cover(s, primes(s, n), n).length
  return { f: count(on), notF: count(off) }
}

/** Render a cover back into our term-string form, for pasting into a design. */
export const toTerms = (cubes: Cube[], vars: string[]): string[] =>
  cubes.map((c) => vars
    .map((v, i) => (c.mask & (1 << i)) ? ((c.ones & (1 << i)) ? v : `!${v}`) : null)
    .filter((s): s is string => s !== null).join(" & "))

/** The cheaper of the two polarities, with its terms. */
export const bestForm = (cubes: Cube[], n: number, vars: string[]) => {
  const on = onSet(cubes, n)
  const off = new Set<number>()
  for (let m = 0; m < (1 << n); m++) if (!on.has(m)) off.add(m)
  const pick = (s: Set<number>) => s.size === 0 ? [] : cover(s, primes(s, n), n)
  const a = pick(on), b = pick(off)
  return a.length <= b.length
    ? { inverted: false, terms: toTerms(a, vars) }
    : { inverted: true, terms: toTerms(b, vars) }
}
