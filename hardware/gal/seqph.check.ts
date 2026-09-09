/* The sequencer's timing spine, and one arithmetic result about scrolling.
 *   npm run check:seqph
 */

import { writeFileSync } from "node:fs"
import { join } from "node:path"
import { assemble, fuseChecksum, toJedec, toReport } from "./jedec/assemble"
import { Gal22v10, parseJedec } from "./jedec/simulate"
import { seqphDesign } from "./seqph.jedec"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

const here = new URL(".", import.meta.url).pathname
const a = assemble(seqphDesign)
const jed = toJedec(seqphDesign, a)
writeFileSync(join(here, "seqph.jed"), jed)
writeFileSync(join(here, "seqph.doc"), toReport(seqphDesign, a))
const parsed = parseJedec(jed)
check(parsed.declaredChecksum === fuseChecksum(parsed.fuses),
  "seqph: fuse checksum, and the file reads back as written")
const gal = new Gal22v10(parsed.fuses)

const pin = (n: string) => a.usage.find((u) => u.name === n)!.pin
const io = (hs: number): Record<number, 0 | 1> =>
  ({ 2: 1, 3: (hs & 1) as 0 | 1, 4: ((hs >> 1) & 1) as 0 | 1 })

/* -- the phase, and that scroll does not move it -------------------------- */
{
  const ticks: Record<number, number[]> = {}
  let phaseBad: string | null = null
  for (const hs of [0, 1, 2, 3]) {
    gal.reset()
    ticks[hs] = []
    for (let dot = 0; dot < 32; dot++) {
      const p = gal.evaluate(io(hs))
      const ph = p[pin("PH0")] | (p[pin("PH1")] << 1)
      if (ph !== dot % 4) { phaseBad = `dot ${dot}: phase ${ph}, expected ${dot % 4}`; break }
      /* 5.2.2: dots 0-1 are the spare window, 2-3 the fetch. */
      if (p[pin("SPAREWIN")] !== (ph < 2 ? 1 : 0)) {
        phaseBad = `dot ${dot}: SPAREWIN ${p[pin("SPAREWIN")]} at phase ${ph}`; break
      }
      /* ⭐ ONE CLOCK FOR ALL FOUR CHIPS SINCE 2026-09-09 - graphics.md 8.2.
       * Item 23(a)'s per-chip early/late scheme is deleted: 19 item 28 is the
       * arithmetic that says a single latch rank cannot hold two groups
       * whichever edge you pick, and 8.2's SECOND RANK is what does. With the
       * rank select carrying the group choice, HSCROLL[1:0] leaves this
       * equation entirely - which is what this sweep now asserts, by demanding
       * the same phase for every chip at every scroll value. */
      for (let n = 0; n < 4; n++) {
        if (p[pin(`FCLK${n}`)] !== (ph === 0 ? 1 : 0)) {
          phaseBad = `dot ${dot}: HS=${hs} FCLK${n} ${p[pin(`FCLK${n}`)]} at phase ${ph}, ` +
            `expected high only at phase 0`
        }
      }
      if (p[pin("SLOTTICK")]) ticks[hs].push(dot)
      gal.clock(io(hs))
    }
    if (phaseBad) break
  }
  check(phaseBad === null, "the dot phase free-runs 0,1,2,3 and the sub-slot split is 5.2.2's",
    phaseBad ?? "")
  check(ticks[0].length === 8, "the slot tick fires once per four dots", `${ticks[0]?.length}`)
  check([1, 2, 3].every((hs) => ticks[hs].join() === ticks[0].join()),
    "THE SLOT TICK DOES NOT MOVE WITH HSCROLL - so hgen's HSYNC, which is " +
    "derived from it, does not slide with horizontal scroll")
}

/* -- the mux select is the only thing the scroll phase touches ------------ */
{
  let bad: string | null = null
  for (const hs of [0, 1, 2, 3]) {
    gal.reset()
    for (let dot = 0; dot < 4 && !bad; dot++) {
      const p = gal.evaluate(io(hs))
      const ph = p[pin("PH0")] | (p[pin("PH1")] << 1)
      const sel = p[pin("MUXSEL0")] | (p[pin("MUXSEL1")] << 1)
      if (sel !== (ph + hs) % 4) {
        bad = `HSCROLL[1:0]=${hs} phase ${ph}: mux select ${sel}, expected ${(ph + hs) % 4}`
      }
      gal.clock(io(hs))
    }
  }
  check(bad === null, "the pixel mux select is the dot phase plus HSCROLL[1:0], mod 4, " +
    "for all sixteen combinations", bad ?? "")
}

/* -- what section 8 does not say ------------------------------------------
 *
 * 8 says sub-pixel horizontal smoothness "costs zero parts, because the
 * phase counter already drives the 4:1 selection". That is true of the
 * SELECT and says nothing about what the four latches hold. The arithmetic
 * below is not about this GAL - it is about the four fetch latches, and it
 * is here because this is the part that would have to fix it.
 * ------------------------------------------------------------------------ */
{
  /* Four chips in 4-way interleave: chip n holds the byte at column c where
   * c mod 4 == n, from group g at chip address g. If all four latches are
   * loaded from a common address bus at a common instant, then during slot g
   * every chip holds a byte of group g. */
  const emitted = (g: number, dot: number, p: number) => 4 * g + ((dot + p) % 4)
  const wanted = (g: number, dot: number, p: number) => 4 * g + p + dot

  const firstWrong: Record<number, number | null> = {}
  for (const p of [0, 1, 2, 3]) {
    firstWrong[p] = null
    for (let g = 0; g < 2 && firstWrong[p] === null; g++) {
      for (let dot = 0; dot < 4; dot++) {
        if (emitted(g, dot, p) !== wanted(g, dot, p)) { firstWrong[p] = 4 * g + dot; break }
      }
    }
  }
  check(firstWrong[0] === null,
    "with HSCROLL[1:0] = 0 a common latch clock emits the right byte sequence")
  check([1, 2, 3].every((p) => firstWrong[p] !== null),
    "and with HSCROLL[1:0] != 0 it does NOT: the mux wraps to chip 0 while that " +
    "chip still holds the current group, so the line steps backwards four pixels in",
    `first wrong pixel: p=1 at ${firstWrong[1]}, p=2 at ${firstWrong[2]}, p=3 at ${firstWrong[3]}`)

  /* ---- and the clock no longer carries the scroll -----------------------
   *
   * ⛔ ITEM 23(a) IS DELETED, NOT MERELY SUPERSEDED. It read the edge phase
   * out of the fuses per chip, computed the emitted byte sequence for every
   * HSCROLL[1:0], and asserted the line was contiguous - "byte-granular
   * horizontal scroll is a design". 19 item 28 is the arithmetic that says it
   * was not: a latch clocked once per slot always holds the most recent fetch,
   * so no assignment of edges produces the older group, and seqph.check.ts
   * could not see that because it modelled the latch contents as "one more
   * group if clocked at phase 0" rather than deriving them from what is on the
   * data bus at that instant. The old block is archived in history.md.
   *
   * What replaces the claim is the one below - that HSCROLL[1:0] does not
   * reach these equations at all - plus vaddr_tb's pixel check, which emits a
   * whole line at every scroll value and compares it against memory. That is
   * the check this file could not be. */
  {
    let carries: string | null = null
    for (let n = 0; n < 4 && !carries; n++) {
      const edges = [0, 1, 2, 3].map((hs) => {
        gal.reset()
        for (let dot = 0; dot < 8; dot++) {
          const p = gal.evaluate(io(hs))
          const ph = p[pin("PH0")] | (p[pin("PH1")] << 1)
          if (p[pin(`FCLK${n}`)] === 1) return ph
          gal.clock(io(hs))
        }
        return -1
      })
      if (new Set(edges).size !== 1) carries = `FCLK${n} edges by HSCROLL[1:0]: ${edges.join(",")}`
    }
    check(carries === null,
      "⭐ FCLK does not depend on HSCROLL[1:0] at all - 8.2's rank select carries " +
      "the group choice, so the four clocks are one signal and item 23(a)'s nine " +
      "product terms are gone", carries ?? "")

    const fclkPts = a.usage.filter((u) => u.name.startsWith("FCLK"))
      .reduce((n, u) => n + u.used, 0)
    check(fclkPts === 4, "and the four macrocells hold one product term each, not nine " +
      "across them - the saving that paid for pxsel's two", `${fclkPts}`)
  }
}
