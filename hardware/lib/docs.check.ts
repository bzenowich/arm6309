/* Documentation freshness, checked as arithmetic rather than as discipline.
 *   npm run check:docs
 *
 * ** WHY THIS FILE EXISTS. Stale headline numbers are this repository's oldest
 * recurring defect. On 2026-09-09 SEVEN documents quoted CPLD utilisation
 * figures that no longer matched `gal/cpld/*.fit` - and several of them had
 * been wrong since the PREVIOUS session, because the only thing keeping them
 * right was somebody remembering to grep. CLAUDE.md's maintenance rules say
 * "when changing a headline number, grep for it repo-wide"; this is that grep,
 * run by CI instead of by memory.
 *
 * ** THE RULE IT ENFORCES. A spec may state a utilisation figure only if it is
 * the CURRENT one. The fitter's report is the authority - CLAUDE.md's trust
 * precedence puts design outputs above prose, and `.fit` is a design output.
 *
 * ** WHAT IT DELIBERATELY DOES NOT POLICE:
 *
 *   - history.md files and docs/design-review*.md. History is SUPPOSED to
 *     quote superseded numbers; the review documents are frozen dated records
 *     that CLAUDE.md forbids updating. Checking them would invert their job.
 *   - Lines that mark themselves historical in prose. A spec is allowed to say
 *     "vctrl WENT TO 122 of 128" while narrating how it got here, as long as
 *     it is visibly past tense. PAST_TENSE below is that vocabulary, and it is
 *     deliberately short: the more escapes this list has, the less this file
 *     is worth.
 *
 * ** AND IT IS NOT THE WHOLE PROBLEM. This catches numbers. It cannot catch a
 * paragraph that describes a mechanism the design no longer has - which is
 * what design-review2.md 1.2 found eleven of, and what census.ts is for.
 */

import { CARDS } from "../place/parts"
import { lstatSync, readdirSync, readFileSync, statSync } from "node:fs"
import { join, relative } from "node:path"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

const ROOT = join(new URL(".", import.meta.url).pathname, "..", "..")
const FITS = join(ROOT, "hardware", "gal", "cpld")

/* -- the authority: what the fitter actually reported --------------------- */

interface Fit { cells: number; io: number; ded: number }
const fits = new Map<string, Fit>()
for (const f of readdirSync(FITS).filter((n) => n.endsWith(".fit"))) {
  const text = readFileSync(join(FITS, f), "utf8")
  const num = (re: RegExp) => {
    const m = text.match(re)
    return m ? Number(m[1]) : NaN
  }
  fits.set(f.replace(/\.fit$/, ""), {
    cells: num(/Total Logic cells used\s+(\d+)\/\d+/i),
    io: num(/Total I\/O pins used\s+(\d+)\/\d+/i),
    ded: num(/Total dedicated input used:\s+(\d+)\/\d+/i),
  })
}
check(fits.size > 0, `read the fitter's own reports for ${[...fits.keys()].join(", ")}`)
for (const [name, f] of fits) {
  check(Number.isFinite(f.cells) && Number.isFinite(f.io) && Number.isFinite(f.ded),
    `${name}.fit reports all three totals`, `${f.cells}/${f.io}/${f.ded}`)
}

/* -- every markdown file that is allowed to be wrong ---------------------- */

const EXEMPT = (p: string) =>
  /(^|\/)history\.md$/.test(p) ||
  /(^|\/)design-review\d*\.md$/.test(p) ||
  /* ⭐ archive/ - 2026-09-20. An archived card's documents are a FROZEN RECORD
   * of a design that is no longer in the machine, exactly as history.md and
   * the design reviews are, and CLAUDE.md forbids rewriting a record to keep
   * a checker quiet. `archive/video/docs/graphics.md` states vaddr, vctrl and
   * vsup's utilisation as it stood when the card was retired; those .fit files
   * are still in gal/cpld and still agree, and the day they stop being
   * regenerated the prose must not start failing. See archive/README.md. */
  /^archive\//.test(p) ||
  /(^|\/)node_modules\//.test(p) ||
  /(^|\/)\.agents\//.test(p) ||
  /(^|\/)reference\//.test(p) ||
  /(^|\/)coco3_c64\.md$/.test(p) ||
  // a dated plan, disposable, and quoting the figures it was written against
  /(^|\/)workplan-[\d-]+\.md$/.test(p)

/* A line that visibly narrates the past may quote a superseded figure. Keep
 * this vocabulary SHORT - every entry is a hole in the check. */
const PAST_TENSE =
  /\b(was|were|used to|went to|had been|before|until|when this|earlier|previously|no longer|briefly|once |old |former|then \*\*|paragraph was written|is not built|not taken|would have|refused|it reported)\b/i

const mdFiles: string[] = []
/* ⚠ DOT-DIRECTORIES ARE SKIPPED, and `.wine_atf` is why - 2026-09-10.
 *
 * The ATF15xx toolchain's Wine prefix moved into the repository that day so it
 * would survive a sandboxed session (CLAUDE.md), and a Wine prefix contains
 * `dosdevices/z:` - a symlink to `/`. Following it walks the whole filesystem
 * and dies on the first transient entry under `/dev/fd`, which is what this
 * check did the first time it ran afterwards. Skipping every dot-directory
 * covers it and `.git` besides, and `lstat` means a symlink is never followed
 * even if one turns up outside a dot-directory. */
const walk = (dir: string) => {
  for (const e of readdirSync(dir)) {
    if (e.startsWith(".")) continue
    if (e === "node_modules" || e === "dist" || e === "obj_dir") continue
    const p = join(dir, e)
    const st = lstatSync(p)
    if (st.isSymbolicLink()) continue
    if (st.isDirectory()) walk(p)
    else if (e.endsWith(".md")) mdFiles.push(p)
  }
}
walk(ROOT)

/* -- the claims themselves ------------------------------------------------
 *
 * ⛔ UNTIL 2026-09-12 THIS SCANNED ONE LINE AT A TIME, AND STALE FIGURES LIVED
 * IN THE GAPS. Three holes, each verified by running the old regexes against
 * the lines they passed over (workplan 2026-09-12 P3 item 12):
 *
 *   - the past-tense test was LINE-scoped, so one "was" anywhere on a line
 *     exempted a live figure later on the same line;
 *   - only "N of N" matched, and the specs also write 128/128 and 56 / 64;
 *   - a figure whose part name was on the previous line was skipped, and
 *     "N of 64 pins" never matched a regex that demanded "I/O".
 *
 * So the unit of scanning is now a PARAGRAPH, a LIST ITEM or a TABLE ROW; the
 * tense test applies to the CLAUSE holding the figure; both shapes match; and
 * "pins" is I/O. Shapes:
 *
 *   "122 of 128 cells", "122/128 logic cells", "125 / 128"   -> cells
 *   "62 of 64 I/O", "56/64 pins", "53 / 64" beside a cells figure  -> io
 *   "3 of 4 dedicated"                                       -> dedicated
 *
 * A bare N/64 is I/O only where the clause also carries that part's cells
 * figure, or where its table column is headed I/O or pins - a bare 64 is also
 * a sample count or a level. A figure followed by another resource's name
 * (foldback, fan-in, PT, cascades) is not a cells figure.
 *
 * ATTRIBUTION: the nearest part name before the figure in its clause, then in
 * its unit, then the first in the unit. In audio/ the parts are also called U1
 * (`audio`) and U2 (`aseq`). A figure with no part name in its unit is skipped. */
/* ⚠ EVERY PART THE FITTER PRODUCES A REPORT FOR MUST BE NAMED HERE, or its
 * figures are silently unguarded. `aseq` (the audio sequencer, U2) and `vsup`
 * (the video card's third CPLD) were both born on 2026-09-09 and neither was
 * in this list, so their utilisation was unchecked AND their numbers were
 * being attributed to whichever other part shared the line. The audio agent
 * found it by having its own true figures reported as stale. Derive the list
 * from the .fit files rather than hard-coding it, so the next part added is
 * covered the moment it is fitted. */
const PART_RE = new RegExp(`\\b(${[...fits.keys()].join("|")})\\b`, "gi")
const ALIASES: [RegExp, RegExp, string][] = [
  [/^audio\//, /\bU1\b/g, "audio"],
  [/^audio\//, /\bU2\b/g, "aseq"],
]

interface Claim { file: string; line: number; text: string; part: string; kind: keyof Fit; value: number }
const claims: Claim[] = []

/* A table with a column headed like this is a record of a change. */
const PAST_COLUMN = /\b(before|was|old|previous|then|from)\b/i
/* Not a cells or I/O figure: another resource's count out of 128 or 64. */
const OTHER_RESOURCE = /^\s*(?:\*\*)?\s*(foldback|fan-?in|PT|product|cascade|nodes|flip|FF|registers|%)/i
const FIG = /\*{0,2}(\d+)\*{0,2}\s*(?:of|\/)\s*\*{0,2}(\d+)\*{0,2}(\s*(?:logic\s*)?(cells|macrocells|I\/O|pins|dedicated))?/gi
const CLAUSE_END = /\. |; | — |\||\n\n/

for (const file of mdFiles) {
  const rel = relative(ROOT, file)
  if (EXEMPT(rel)) continue
  const lines = readFileSync(file, "utf8").split("\n")

  // Units, each with the table header that governs it (if any).
  interface Unit { start: number; text: string; header?: string[] }
  const units: Unit[] = []
  let cur: Unit | null = null
  let header: string[] | undefined
  const cellsOf = (row: string) => row.trim().replace(/^\||\|$/g, "").split("|")
  lines.forEach((l, i) => {
    const t = l.trim()
    if (t.startsWith("|")) {
      if (cur) { units.push(cur); cur = null }
      const prev = lines[i - 1]?.trim() ?? ""
      if (!prev.startsWith("|")) header = cellsOf(t)
      else if (!/^\|[\s:|-]+\|?$/.test(t)) units.push({ start: i + 1, text: l, header })
      return
    }
    header = undefined
    if (t === "" || t.startsWith("#") || t.startsWith("```")) { if (cur) { units.push(cur); cur = null } return }
    if (/^\s*(?:>\s*)?([-*]|\d+\.)\s/.test(l) && cur) { units.push(cur); cur = null }
    if (!cur) cur = { start: i + 1, text: l }
    else cur.text += "\n" + l
  })
  if (cur) units.push(cur)

  for (const u of units) {
    const names: { at: number; part: string }[] = [...u.text.matchAll(PART_RE)]
      .map((m) => ({ at: m.index!, part: m[1].toLowerCase() }))
    for (const [dir, re, part] of ALIASES)
      if (dir.test(rel)) for (const m of u.text.matchAll(re)) names.push({ at: m.index!, part })
    if (names.length === 0) continue
    names.sort((a, b) => a.at - b.at)
    // The paragraph that opens a closed, dated item is that item's record.
    if (/CLOSED\s+20\d\d-\d\d-\d\d/.test(u.text)) continue

    const figs = [...u.text.matchAll(FIG)].map((m) => {
      const at = m.index!
      const before = u.text.slice(0, at)
      const cs = Math.max(...[". ", "; ", " — ", "|", "\n\n"].map((d) => before.lastIndexOf(d)))
      const rest = u.text.slice(at + m[0].length).search(CLAUSE_END)
      const ce = rest < 0 ? u.text.length : at + m[0].length + rest
      return { m, at, cs, ce, clause: u.text.slice(cs + 1, ce) }
    })
    for (const f of figs) {
      const { m, at, cs, clause } = f
      const a = Number(m[1]), b = Number(m[2])
      const unit = (m[4] ?? "").toLowerCase()
      if (!unit && OTHER_RESOURCE.test(u.text.slice(at + m[0].length))) continue
      if (PAST_TENSE.test(clause)) continue
      // A dated clause is a record, not a claim - unless the date is when the
      // figure STARTED being true, which is a claim that it still is.
      if (/\b20\d\d-\d\d-\d\d\b/.test(clause) && !/\b(since|as of)\s+\*{0,2}20\d\d-/i.test(clause)) continue

      let col: string | undefined
      if (u.header) col = u.header[u.text.slice(0, at).split("|").length - 2]
      /* \u26d4 AND A COLUMN HEADER NAMES THE RESOURCE. OTHER_RESOURCE is tested
       * against the text AFTER the figure, and in a table cell that text is
       * `|` - so the word never reaches it. `| cascades | foldback |`'s
       * `37/128` read as 37 of 128 CELLS, and three fitted parts were reported
       * stale against their own .fit. \u26a0 Found 2026-09-18, and it had been
       * failing since the table was written: check:docs is the LAST script in
       * npm run check's && chain, which is exactly where CLAUDE.md says a
       * failure is least visible. */
      if (col && OTHER_RESOURCE.test(col)) continue
      // A table with a "before" column records a CHANGE: its after column is
      // what the change produced on its date, not a claim about today.
      if (u.header && u.header.some((h) => PAST_COLUMN.test(h))) continue
      // ... and so does a table whose header carries a date.
      if (u.header && u.header.some((h) => /\b20\d\d-\d\d-\d\d\b/.test(h))) continue
      // An estimate is not a fit.
      if (/\bestimat/i.test(clause)) continue

      const inClause = names.filter((n) => n.at > cs && n.at < at)
      const inUnit = names.filter((n) => n.at < at)
      const part = (inClause.at(-1) ?? inUnit.at(-1) ?? names[0]).part

      let kind: keyof Fit | undefined
      if (unit === "dedicated") { if (b === 4) kind = "ded" }
      else if (unit === "cells" || unit === "macrocells") { if (b === 128) kind = "cells" }
      else if (unit === "i/o" || unit === "pins") { if (b === 64) kind = "io" }
      else if (b === 128) kind = "cells"
      else if (b === 64) {
        const paired = figs.some((g) => g !== f && g.cs === f.cs && Number(g.m[2]) === 128)
        if (paired || (col && /I\/O|pins/i.test(col))) kind = "io"
      }
      if (!kind) continue
      claims.push({
        file: rel, line: u.start + u.text.slice(0, at).split("\n").length - 1,
        text: clause.replace(/\s+/g, " ").trim(), part, kind, value: a,
      })
    }
  }
}

check(claims.length > 0,
  `found ${claims.length} present-tense utilisation claims across ${mdFiles.length} documents`)

const wrong = claims.filter((c) => {
  const f = fits.get(c.part)
  return f && f[c.kind] !== c.value
})

if (wrong.length) {
  console.error("")
  for (const c of wrong) {
    const f = fits.get(c.part)!
    console.error(`      ${c.file}:${c.line}  ${c.part} ${c.kind}: says ${c.value}, ` +
      `cpld/${c.part}.fit says ${f[c.kind]}`)
    console.error(`        ${c.text.slice(0, 260)}`)
  }
  console.error("")
}
check(wrong.length === 0,
  "every present-tense utilisation figure in the specs matches gal/cpld/*.fit - " +
  "the fitter is the authority and prose does not get a second opinion",
  wrong.length ? `${wrong.length} stale` : "")

/* -- IC counts, against place/parts.ts ------------------------------------
 *
 * ** WHY. On 2026-09-09 the video card's headline went 28 -> 33 -> 31 -> 32 ->
 * 36 in a single session, and the audio card's 32 -> 39, while `machine.md`
 * §0, `machine.md` §8, the component README and the root README all quoted it
 * independently. It is the most-quoted number on a card and nothing guarded
 * it. `place/parts.ts` is the authority because `place.check.ts` already
 * asserts its `ics` against the parts list that places on the board - so the
 * number there is the one a person could count on a bench.
 *
 * ** ATTRIBUTION IS BY DIRECTORY, NOT BY WORDS ON THE LINE. The obvious
 * heuristic - "whichever card name appears nearest" - is wrong here, and
 * wrong in a way worth recording: **"net" is both a card and an English
 * word.** It matched "Net: 39 ICs" (a net total), "+4 ICs net" (a delta) and
 * "Net: 3 ICs" (a comparison), giving fifteen false positives and no true
 * ones. A card's own documents are the reliable signal: video/** is the video
 * card, audio/** is the audio card. Shared documents are checked only where
 * the card is named in a heading-shaped way.
 *
 * ** AND ONLY TOTALS, NOT DELTAS. `+4 ICs`, `-1 IC` and `~3 ICs` are costs of
 * a change, not a card's count, so a sign or a tilde disqualifies. */
{
  /* ⭐ `video3/` SINCE 2026-09-20, and `video/` left the same day - the card
   * was archived and its documents are EXEMPT above. video3 is the machine's
   * video card and its 45 ICs are now the most-quoted number on it, which is
   * exactly the class this block exists for: the plan said 44 in five places
   * for a day after keyed-copy.md added the '4078. */
  const OWNER: Record<string, string> = {
    "video3/": "video3", "audio/": "audio",
    "net/": "net", "storage/": "storage", "io/": "io",
  }
  interface IcClaim { file: string; line: number; text: string; card: string; value: number }
  const icClaims: IcClaim[] = []

  for (const file of mdFiles) {
    const rel = relative(ROOT, file)
    if (EXEMPT(rel)) continue
    const owner = Object.entries(OWNER).find(([d]) => rel.startsWith(d))?.[1]
    readFileSync(file, "utf8").split("\n").forEach((text, i) => {
      if (PAST_TENSE.test(text)) return
      /* ⚠ ONLY THE CANONICAL PHRASINGS, and this is a real limitation.
       * "N of 128 cells" is a distinctive shape; "N ICs" is not - it is also
       * how the docs write a sub-block's cost ("List engine (5 ICs)"), a
       * rejected alternative ("41 ICs across two cards") and an estimate
       * ("~6-8 ICs"). An open regex reported 43 stale counts of which none
       * were real. So this matches only the two forms the specs use for a
       * card's TOTAL, and a total written any other way is invisible to it.
       * If that bites, the fix is a marker in the prose, not a cleverer
       * regex. */
      const totals = [
        ...text.matchAll(/\bthe card is (?:now )?\*?\*?(\d+)\*?\*? ICs\b/gi),
        ...text.matchAll(/\*\*(?:Video3|Video|Audio|Net|Storage|I\/O)\*\*[^|]*?\*\*(\d+) ICs\b/gi),
      ]
      for (const m of totals) {
        let card = owner
        if (!card) {
          const near = text.slice(0, m.index!).match(/\*\*(Video3|Video|Audio|Net|Storage|I\/O)\*\*/gi)
          if (!near) continue
          card = near[near.length - 1].replace(/\*/g, "").toLowerCase().replace("i/o", "io")
        }
        if (!CARDS[card]) continue
        icClaims.push({ file: rel, line: i + 1, text: text.trim(), card, value: Number(m[1]) })
      }
    })
  }

  const badIc = icClaims.filter((c) => CARDS[c.card].ics !== c.value)
  if (badIc.length) {
    console.error("")
    for (const c of badIc) {
      console.error(`      ${c.file}:${c.line}  ${c.card}: says ${c.value} ICs, ` +
        `place/parts.ts says ${CARDS[c.card].ics}`)
      console.error(`        ${c.text.slice(0, 130)}`)
    }
    console.error("")
  }
  check(badIc.length === 0,
    `every present-tense IC total in the specs matches place/parts.ts ` +
    `(${icClaims.length} checked) - the parts list is the authority, because ` +
    `it is what places on the board`,
    badIc.length ? `${badIc.length} stale` : "")
}

/* -- and the specs must not cite a part that has no fit at all ------------ */
{
  const unknown = [...new Set(claims.filter((c) => !fits.get(c.part)).map((c) => c.part))]
  check(unknown.length === 0,
    "and every part quoted is one the fitter has actually produced a report for",
    unknown.join(", "))
}

console.log("")
console.log(failures === 0
  ? `${claims.length} utilisation claims agree with the fitter, across ${mdFiles.length} documents`
  : `${failures} FAILURES`)
process.exit(failures === 0 ? 0 : 1)
