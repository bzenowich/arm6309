/* Every signal this machine produces must reach something.
 *
 *   npm run check:reach
 *
 * ⛔ WHY. `design-review2.md` (2026-09-09) found **eleven blocks described as
 * fitted with no cell behind them** — signals a fitted part READ that nothing
 * produced. That direction is closed and `emit.ts`'s port census is what closed
 * it. This check is the OTHER direction, and on 2026-09-10 it turned out to be
 * open in ten places at once:
 *
 *   a signal that is PRODUCED, and that nothing reads.
 *
 * A register bit with that shape is a **feature the host can write and the card
 * cannot perform**. `ACTRL` b3 is the one that was found by hand: latched, read
 * back through `ASTAT`, and taken by no cell on either CPLD — so §6.1's "the
 * card doing the ×4" was never built, and the card was 12.04 dB below every
 * output level `audio.md` §7.1 specifies. Nothing caught it for two days
 * because every check this project owns asks whether a part computes its own
 * equations correctly, and a bit nobody reads has no equation to get wrong.
 *
 * ⚠ THE OTHER HALF OF THE CHECK IS WHAT KEEPS IT HONEST. `RESERVED` below is
 * the list of signals that are *allowed* to be unread, each with the section
 * that withdrew the feature. An entry that is no longer unread FAILS, so the
 * list cannot become a dumping ground: a feature that gets built has to be
 * taken off it, and the check is what notices.
 *
 * ⛔ AND SINCE 2026-09-18 IT ASKS THE SAME QUESTION OF INPUTS, for a card
 * with no board file. `design-review2.md`'s direction - a part reads what
 * nothing produces - was closed for the cards that HAVE one: an input no part
 * computes is the board's, and check:netlist answers for it. video3 has no
 * board file, so nothing answered for any of its 84 unproduced inputs, and
 * nineteen of them turned out to be control lines whose BLOCK HAS NOT BEEN
 * DESIGNED - both sequencers, the span writer's and the copy engine's, and the
 * four requests into v3dot's own arbiter. The datapath is fitted; the things
 * that would drive it are not. See SOURCES.
 *
 * ⚠ WHAT IT CANNOT SEE, stated because a check that overstates its reach is
 * worse than none. It reads the TERM LISTS and the hand-written board files. A
 * signal consumed by a discrete part the board model does not have — the
 * `74HC4066`'s filter switches, an SRAM's `/OE` — is invisible to it and would
 * read as dangling, so those are on `RESERVED` too, marked `board`. That is a
 * real hole and `graphics.md` §19 item 34 is its size: `archive/video/board/video.circuit.tsx`
 * is a partial board, so `check:netlist` cannot close it either.
 */

import { audioCpld } from "../../audio/logic/audio.cpld"
import { aseqCpld } from "../../audio/logic/aseq.cpld"
import { v3dot } from "../../video3/logic/v3dot.cpld"
import { v3scan } from "../../video3/logic/v3scan.cpld"
import { v3ptr } from "../../video3/logic/v3ptr.cpld"
import { v3host } from "../../video3/logic/v3host.cpld"
import { v3laneDesign } from "../../video3/logic/v3lane.jedec"
import { sdbusDesign } from "../../storage/logic/sdbus.jedec"
import { sdengDesign } from "../../storage/logic/sdeng.jedec"
import { mmuDesign } from "../../mainboard/logic/mmu.jedec"
import { clkdecDesign } from "../../mainboard/logic/clkdec.jedec"
import { u9Design } from "../../mainboard/logic/u9.jedec"
import { u10Design } from "../../mainboard/logic/u10.jedec"
import type { Cell } from "./jedec/assemble"
import { readFileSync } from "node:fs"
import { PROGRAM, type Step } from "../../audio/logic/aseq.micro"
import { join } from "node:path"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

const here = new URL(".", import.meta.url).pathname

/* ---- what a card is: the parts on it, and the board they sit on --------- */
interface Part { name: string; cells: Cell[]; external: Set<string>; inputs: string[] }
interface Card {
  name: string
  parts: Part[]
  boards: string[]
  /* ⭐ opt in to the INPUT analysis below. Only video3 does, and saying so
   * is the point: the other three cards have board files, so their unproduced
   * inputs are answered by check:netlist. video3 has no board file at all. */
  checkInputs?: boolean
  noBoard?: string
}

const part = (name: string,
  d: { cells: Cell[]; external?: Set<string>; inputs: { name: string }[] }): Part =>
  ({ name, cells: d.cells, external: d.external ?? new Set(d.cells.map((c) => c.name)),
     inputs: d.inputs.map((i) => i.name) })

const CARDS: Card[] = [
  {
    name: "audio",
    parts: [part("audio", audioCpld), part("aseq", aseqCpld)],
    boards: ["../../audio/sim/audio_card.v"],
  },
  /* ⭐ `video` LEFT THIS LIST ON 2026-09-20. It was vctrl, vaddr and vsup
   * against `verilog/video_card.v` and `verilog/machine.v`; the card was
   * archived that day and `video3` is the machine's video card
   * (`hardware/archive/README.md`, `docs/history.md`). Its five RESERVED entries -
   * CPUIDLE, GSPN0..3 - and the open-drain WAIT went with it, and
   * `hardware/archive/video/docs/history.md` is where they are recorded. ⚠ The board
   * files are still in `verilog/` because `machine_tb` still instantiates
   * the card; nothing takes its census any more. */
  /* ⭐ VIDEO3's BOARD IS video3_card.v since 2026-09-19 - the five parts and
   * every discrete package plan §13.1 lists, wired from the term lists by
   * v3portmap.ts, with no reach into any part. It is a MODEL of a board and
   * not a drawn one: `check:netlist` still has nothing to read (plan §15 step
   * 8), so the INPUT analysis below stays on. */
  {
    name: "video3",
    parts: [part("v3dot", v3dot), part("v3scan", v3scan),
      part("v3ptr", v3ptr), part("v3host", v3host), part("v3lane", v3laneDesign)],
    boards: ["../../video3/sim/video3_card.v"],
    checkInputs: true,
  },
  /* ⭐ STORAGE, 2026-09-20. Eight ICs and two GALs, and storage_card.v is
   * the board - hand-written, unlike video3's, because six discrete packages
   * is a thing one writes rather than generates. `checkInputs` is on for the
   * same reason it is on for video3: `check:netlist` says outright that
   * there are no netlist claims for this card yet, so this is the only thing
   * asking whether a control line has a producer. */
  {
    name: "storage",
    parts: [part("sdbus", sdbusDesign), part("sdeng", sdengDesign)],
    boards: ["../../storage/sim/storage_card.v"],
    checkInputs: true,
  },
  {
    name: "motherboard",
    parts: [part("mmu", mmuDesign), part("clkdec", clkdecDesign),
      part("u9", u9Design), part("u10", u10Design)],
    boards: ["../../mainboard/sim/mainboard.v", "../../archive/video/sim/machine.v"],
  },
]

/* ---- every identifier a term mentions ----------------------------------- */
const ID = /[A-Za-z_][A-Za-z0-9_]*/g
/* ⚠ A CELL READING ITSELF IS NOT A CONSUMER, and getting that wrong made the
 * first run of this check report every ACTRL bit as live. Every registered bit
 * holds with `X & !STROBE`, and every counter counts with its own state, so a
 * naive scan finds each of them "read" by the one cell that cannot possibly be
 * the feature. `CTRL3` is the case in point: its only mention anywhere is
 * `CTRL3 & !WCTRL`, its own hold. */
const readByOthers = (cells: Cell[]): Set<string> => {
  const s = new Set<string>()
  for (const c of cells) {
    const ids = new Set<string>()
    for (const t of c.terms) for (const m of t.match(ID) ?? []) ids.add(m)
    if (c.oe) for (const m of c.oe.match(ID) ?? []) ids.add(m)
    for (const id of ids) if (id !== c.name) s.add(id)
  }
  return s
}

/* ---- what the board does with a signal ---------------------------------- *
 *
 * ⚠ A PORT MAP IS NOT A USE. `.MAPCE_LO(mapce_lo)` says the board wired the pin
 * to a net; whether anything reads that net is the question, and it is the
 * question `design-review2.md` M-1 turned on ("U1B's DQ pins were never
 * dangling, they were on a net with three other parts and connected to the
 * wrong one"). So a port map is followed to the net it names and the NET is
 * what has to be used - which also makes the check survive the lower-case
 * renaming the motherboard does throughout.
 *
 * ⚠ And `.*` connections have no port map at all: the net's name IS the
 * signal's, so the plain search covers them. */
const boardUses = (paths: string[]): Set<string> => {
  const used = new Set<string>()
  for (const p of paths) {
    let t = readFileSync(join(here, p), "utf8")
    /* ⛔ ONE PASS, ALTERNATED, and stripping the two kinds in sequence is a
     * BUG THIS CHECK SHIPPED WITH - found 2026-09-20 by storage_card.v. Its
     * line 3 is an ordinary `//` comment that happens to contain the path
     * `../storage/*.jedec.ts`, and `hardware/storage/` + `*` IS the digraph `/*`. With
     * block comments taken out first, that opened a comment which closed at
     * the next `*​/` 139 lines later, and 80 % of the file - every `always`
     * block, every use of MOSICK, DATSTB, CTRLW and RDST - vanished before
     * the scan began. ⚠ It reported those four as produced-and-unread, which
     * is this check's FINDING output: the failure mode was a false ALARM, but
     * the same swallowed region would have hidden a true one just as well.
     * Alternation gets it right because whichever delimiter comes first wins,
     * which is also what a Verilog lexer does. */
    t = t.replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g, " ")
    /* Follow every `.PIN(net)` to its net, then take the port maps out. */
    /* ⚠ CASE-INSENSITIVELY. mainboard.v spells every motherboard port in lower
     * case - `.muxsel(muxsel)` for the cell named MUXSEL - so a case-sensitive
     * search reports the whole of U3 as dangling. */
    const alias = new Map<string, string[]>()
    for (const m of t.matchAll(/\.\s*([A-Za-z_]\w*)\s*\(([^()]*)\)/g)) {
      alias.set(m[1].toUpperCase(), (m[2].match(ID) ?? []).map((n) => n.toUpperCase()))
    }
    const body = t.replace(/\.\s*[A-Za-z_]\w*\s*\([^()]*\)/g, " ")
                  /* ⚠ `[^;=]` AND NOT `[^;]`: `wire map_drives = mapce_lo && !n_mapoe;` is a
       * continuous assignment wearing a declaration's clothes, and stripping it
       * takes the use with it. That alone reported the whole of U3 as dangling. */
                  .replace(/^\s*(wire|reg|logic)\b[^;=]*;/gm, " ")
    const inBody = new Set((body.match(ID) ?? []).map((n) => n.toUpperCase()))
    for (const [pin, nets] of alias) {
      if (nets.some((n) => inBody.has(n))) used.add(pin)
    }
    for (const id of inBody) used.add(id)
  }
  return used
}

/* ======================================================================== *
 * RESERVED - signals that are allowed to be produced and read by nothing.
 *
 * Every entry names the section that makes it so. Two kinds:
 *
 *   board   its consumer is a discrete part the board model does not have.
 *           NOT a free pass: it means check:netlist is the check that should
 *           close it, and graphics.md 19 item 34 says that board is partial.
 *   stale   a register bit or field for a feature that was WITHDRAWN. The map
 *           still carries it; the card correctly does nothing with it.
 *   open    a feature that is specified, allocated a bit, and NOT BUILT.
 *           ⛔ These are the findings. Each one is a promise the register map
 *           makes that the silicon does not keep.
 * ======================================================================== */
type Why = "board" | "stale" | "open" | "dead"
const RESERVED: Record<string, { why: Why; note: string }> = {
  /* ================= audio.md 9.2's ACTRL byte ========================== */
  CTRL0: { why: "board", note: "§7's LED filter, into the 74HC4066 (tools/place/parts.ts)" },
  CTRL1: { why: "board", note: "§7's filter bypass, the same 74HC4066" },
  CTRL2: { why: "stale", note: "⛔ NTSC clock. §4.1 takes ONE crystal, 28.37516 MHz, and rejects NTSC at +16 cents - the card has no second crystal and no divider select, so the bit can never do anything. ⚠ refplayer's card.c IMPLEMENTS it, which is a model above its hardware" },
  CTRL3: { why: "stale", note: "⛔ raw volume, RETIRED 2026-09-10. paula.md's AUDxVOL is 0-64, and the words 255, 8-bit volume and attenuator appear NOWHERE in it, so 256-level volume was invented. No mode is needed: VOL is the volume converter's code and the replayer writes min(4v, 255) - §6.1, §16 item 40" },
  CTRL4: { why: "stale", note: "⛔ 8-channel mode, DROPPED 2026-09-10. paula.md: Paula has four channels, numbered 0-3, so §11.2 failed §11's own question. Nothing was ever built - SFA's channel field is two bits" },
  CTRL5: { why: "stale", note: "⛔ pan enable. §11.1's programmable panning was WITHDRAWN 2026-09-09 - most of 45 ICs → 35" },

  /* ⭐ EIGHT `dead` ENTRIES WERE HERE AND ARE DELETED - 2026-09-10, audio.md
   * 16 item 42. U1's four slot decodes, its WAIDX, its CIACLK pin, and U2's
   * ISSPTR and ISTIMER: logic that cost a macrocell and bought nothing, because
   * the job moved and the cell stayed. ⚠ NONE was a broken feature, and the way
   * that was known is that the features work - modplay_tb uploads a module's
   * samples through SPTR and takes every tick from TIMER - so they were second
   * decodes of paths decoded elsewhere. The list is checked in both directions,
   * so deleting them is what forced this comment to replace them.
   *
   * ⭐ SIX ON U1 AND TWO ON U2, and the split is the point: U2 is at 128 of 128
   * logic cells and any future addition has to fit there. */

  /* ================= open-drain outputs: the pin, not the enable ======== *
   * §3.3's idiom - the pin drives low or floats, and the condition rides on
   * the output enable. The board takes the _OE and the value is a constant. */
  FIRQ: { why: "board", note: "§8.1's open-drain /FIRQ; audio_card.v takes FIRQ_OE" },
  /* ⚠ `WAIT` was here too - the `video` card's §7.4 open-drain /WAIT, whose
   * condition rode on machine.v's WAIT_OE. It left with the card on
   * 2026-09-20; video3 spells the same idiom `WAITN`, in RESERVED_RE below. */

  /* ================= `video`'s OWN ENTRIES LEFT ON 2026-09-20 ==========
   *
   * CPUIDLE (`dead`) and GSPN0..3 (`board`, §5.2.1's four per-chip
   * span-writer grants) were the archived card's, and so were the notes on
   * GCPU0-3, ACPU0-3, CHAR and LDFB that recorded what had already left. The
   * whole block is in `hardware/archive/video/docs/history.md` under this date; the
   * card is no longer one this check knows about, and an entry naming a part
   * it does not know is a failure here rather than a skip. */
}

/* ======================================================================== *
 * ⭐ RESERVED_RE - the same list, as PATTERNS, for a card whose I/O is wide
 * and regular. `FBA2`..`FBA18` is one bus and seventeen entries would say
 * seventeen times what one says once.
 *
 * ⚠ IT IS CHECKED IN BOTH DIRECTIONS TOO: a pattern that matches nothing
 * fails, so a bus that gets a consumer has to come off the list exactly as a
 * named signal does.
 * ======================================================================== */
const RESERVED_RE: { re: RegExp; why: Why; note: string }[] = [
  /* video3. ⭐ There is a video3_card.v now, and it took most of this list
   * with it: every pin a discrete part reads is read by the board file. */
  { re: /^(WAITN|IRQN)$/, why: "board",
    note: "signals.md §1.9: open-drain /WAIT and /IRQ - the value is a constant 0 and the condition rides on the output enable, which is what the board reads (WAITN_OE, IRQN_OE)" },
]

/* ======================================================================== *
 * ⛔ SOURCES - THE OTHER DIRECTION, AND THE ONE THAT WAS MISSING.
 *
 * `design-review2.md` closed "a fitted part reads what nothing produces" for
 * the cards that have a BOARD FILE: an input no part computes is the board's,
 * and check:netlist answers for it. video3 has no board file, so nothing
 * answers for any of its 84 unproduced inputs - and four of them are `RMAP`,
 * `RRD`, `RCPY` and `RSPN`, the requests into its own arbiter.
 *
 * So every input a video3 part declares has to be explained here:
 *
 *   bus       the backplane or the host - CLK25, RESET, D, A, E, R/W
 *   board     a discrete part on the card - the map SRAM's two halves
 *   ⛔ alias  a SIBLING PRODUCES IT UNDER ANOTHER NAME, and the term lists do
 *             not say so. A net that depends on two engineers choosing the
 *             same word is not a net (census.ts says this about the other
 *             card). These are findings.
 *   ⛔ unbuilt  NOTHING produces it, because the block that would has not been
 *             designed. These are the findings that matter.
 * ======================================================================== */
type Src = "bus" | "board" | "alias" | "unbuilt"
const SOURCES: { re: RegExp; why: Src; note: string }[] = [

  /* ⭐ STORAGE needs no entry here, and finding that out is what fixed
   * `boardUses` above. Every input its two GALs declare is produced by the
   * backplane, by a discrete package or by the other GAL, and storage_card.v
   * wires all of them - so the board explains the lot and the both-directions
   * guard rejects any entry added anyway. That guard is what caught five
   * redundant ones here on 2026-09-20. */

  /* ⛔ findings from here down */
  /* ⭐ THE FOUR ALIASES LEFT 2026-09-19, and one of them was not an alias.
   *   FBOE (x2)  a true alias: v3ptr now reads FBOEPTR and v3scan FBOESCAN,
   *              the two grants v3dot already exported. ⛔ One name on both
   *              enables had kept them both on or both off the same nets.
   *   SRC0/SRC1  ⛔ FILED HERE AS AN ALIAS OF MUXSEL0/1, AND WRONG: MUXSEL is
   *              the dot phase driving the pixel '153 and SRC is v3scan's
   *              ADDRESS source. SRC1 is GMAP and SRC0 is the mode,
   *              both decoded on v3scan from signals v3dot already exports. A guess in this table about
   *              what a signal IS was wrong twice in two days - RSTART was the
   *              other - and both times the prior art in video/ was right. */
  /* ⭐ BOTH SEQUENCERS LEFT THIS LIST ON 2026-09-19 WITH THEIR EQUATIONS, and
   * the list being checked in both directions is what forced it. RETIRE,
   * SPANEND, WINC, WROWADV, RSPN are v3ptr's span sequencer; CGO folded into
   * CBUSY's own term; CDONE, CSTEP, CROWADV, CWLOAD, CRDSEL and RCPY are the
   * copy's phase machine, which lives on v3host because v3ptr does not fit
   * with both (plan §14 item 14). What is left of the four arbiter requests
   * is the two nobody has written yet. */
  /* ⭐ AND THE LAST SIX LEFT THIS LIST ON 2026-09-19, which empties it. None
   * of them needed a new block:
   *
   *   RMAP    is v3dot's own CELLTICK, mode-qualified - the map word is
   *           fetched once a cell and MAPLD was already `SPARE & CELLTICK`
   *   RRD     is v3host's RDREQ, `!RDVALID` - §11's request under its own
   *           name, which video/ spells the same way
   *   WRCYC   `!RW & E`: a 6809E write is only valid in E's second half
   *   RDCK    `GRD & !RDVALID`, active low so the '574's rising edge is the
   *           END of the granted access - vsup.parts.ts's, minus its !LRUN
   *   RSTART  `RPQ & !E`, §11's post-increment. ⚠ An earlier note here
   *           guessed it meant "the copy has started" from the name alone;
   *           vsup.parts.ts says it is the dot after a VRAM read's E falls
   *   IRQEN   CTRL b6, decoded on v3ptr beside WMODE - v3host gates /IRQ
   *           with it and has neither the CTRL decode nor a data bus
   *
   * ⚠ What is left in this table is `bus`, `board` and the four `alias`
   * entries, and an alias is a defect rather than a gap. */
]

/* ---- the analysis ------------------------------------------------------- */
let dangling: string[] = []
for (const card of CARDS) {
  const produced = new Set<string>()
  for (const p of card.parts) for (const c of p.cells) produced.add(c.name)
  const read = new Set<string>()
  for (const p of card.parts) for (const n of readByOthers(p.cells)) read.add(n)
  const board = boardUses(card.boards)

  /* ⚠ AND AN ACTIVE-LOW CELL IS SPELLED `n_X` ON THE BOARD. mainboard.v wires
   * U3's MAPOE to `n_mapoe`, U6's BOOTOE to `n_bootoe`, and so on for every
   * asserted-low output on the motherboard. */
  const onBoard = (n: string) =>
    board.has(n.toUpperCase()) || board.has(`N_${n.toUpperCase()}`)
  const bad = [...produced].filter((n) => !read.has(n) && !onBoard(n)).sort()
  dangling.push(...bad)

  const unexplained = bad.filter((n) =>
    !(n in RESERVED) && !RESERVED_RE.some((r) => r.re.test(n)))
  check(unexplained.length === 0,
    `${card.name}: every signal it produces is read by a term, by the board, or is on RESERVED`,
    unexplained.length ? `unexplained: ${unexplained.join(", ")}` : "")
}

/* ⚠ and the patterns in both directions too - a pattern that matches nothing
 * is a bus that grew a consumer and was left on the list. */
{
  const idle = RESERVED_RE.filter((r) => !dangling.some((n) => r.re.test(n)))
  check(idle.length === 0,
    "and every RESERVED_RE pattern still matches something dangling",
    idle.length ? idle.map((r) => String(r.re)).join(", ") : "")
}

/* ---- ⛔ THE INPUT ANALYSIS - every input has a producer, or a reason ---- */
const FINDINGS: { card: string; part: string; name: string; why: Src; note: string }[] = []
const SRC_SEEN = new Set<RegExp>()
for (const card of CARDS) {
  if (!card.checkInputs) continue
  const madeBy = new Map<string, string[]>()
  for (const p of card.parts) {
    for (const c of p.cells) {
      if (!madeBy.has(c.name)) madeBy.set(c.name, [])
      madeBy.get(c.name)!.push(p.name)
    }
  }
  const board = boardUses(card.boards)
  const unexplained: string[] = []
  const seen = new Set<string>()
  for (const p of card.parts) {
    for (const i of p.inputs) {
      if (madeBy.has(i) || board.has(i.toUpperCase())) continue
      const hit = SOURCES.find((r) => r.re.test(i))
      if (!hit) { unexplained.push(`${p.name}.${i}`); continue }
      SRC_SEEN.add(hit.re)
      if (hit.why === "bus" || hit.why === "board") continue
      const key = `${p.name}.${i}`
      if (!seen.has(key)) {
        seen.add(key)
        FINDINGS.push({ card: card.name, part: p.name, name: i, why: hit.why, note: hit.note })
      }
    }
  }
  check(unexplained.length === 0,
    `${card.name}: every input a part declares has a producer, a board, or an entry in SOURCES`,
    unexplained.length ? `unexplained: ${unexplained.join(", ")}` : "")
}
{
  const idle = SOURCES.filter((r) => !SRC_SEEN.has(r.re))
  check(idle.length === 0,
    "and every SOURCES pattern still matches an input nothing produces - a signal that " +
    "gains a producer has to leave the list",
    idle.length ? idle.map((r) => String(r.re)).join(", ") : "")
}

/* ⚠ AND THE LIST MUST NOT BECOME A DUMPING GROUND. An entry that is no longer
 * dangling is a feature somebody built and did not take off the list, and the
 * note beside it is then a lie about the present design. */
const stale = Object.keys(RESERVED).filter((n) => !dangling.includes(n))
check(stale.length === 0,
  "and every RESERVED entry is still unread - a built feature has to leave the list",
  stale.length ? `no longer dangling: ${stale.join(", ")}` : "")

/* ---- the state file's own three holes ----------------------------------- *
 * audio.md 9.3's offsets are FIELDS in an SRAM, not signals, so the analysis
 * above cannot see them. What makes one live is a microcode step that reads
 * its (word, lane); HOSTMAP is only what lets the host WRITE it. */
{
  /* ⛔ READ FROM THE PROGRAM ITSELF, since 2026-09-11. This was a regex for
   * `w: 6 … lane: 0` in the source text - and `Step` has no `lane` field, so
   * no step could ever match and the claim could not fail. A step reads a
   * lane when it is a read (no `wr`) at that word AND something on the step
   * takes the lane: the operand latches take SD[15:0], lanes 0 and 1; the
   * high-bit capture and the converter port register take SD[23:16], lane 2.
   * HOSTMAP is still not evidence - being writable is what a retired field is. */
  const lanesTaken = (st: Step): number[] => [
    ...(st.alat || st.blat ? [0, 1] : []),
    ...(st.cap || st.cvld || st.sbo ? [2] : []),
  ]
  const reads = (w: number, lane: number) =>
    Object.values(PROGRAM).flat().some((st) => st.w === w && !st.wr && lanesTaken(st).includes(lane))
  /* offset -> the (word, lane) audio.md 9.3 puts it at */
  const FIELD: Record<string, { w: number; lane: number; why: Why; note: string }> = {
    DAT: { w: 6, lane: 0, why: "stale", note: "§1 requirement 8's CPU-fed sample, RETIRED 2026-09-11 - no ProTracker replayer writes AUDxDAT" },
    ATT: { w: 6, lane: 1, why: "stale", note: "Paula's ADKCON bits, RETIRED 2026-09-11 - no ProTracker replayer writes ADKCON (§11.3)" },
    PAN: { w: 7, lane: 2, why: "stale", note: "§11.1's panning, withdrawn 2026-09-09" },
  }
  const live = Object.entries(FIELD).filter(([, f]) => reads(f.w, f.lane)).map(([n]) => n)
  /* The control: VOL is word 6 lane 2 and W5 reads it into the converter port
   * registers. If this rule cannot see VOL, it cannot see anything. */
  check(reads(6, 2),
    "and the rule sees a live field when there is one - VOL, word 6 lane 2, read by W5 into the port registers")
  check(live.length === 0,
    "audio.md §9.3: DAT, ATT and PAN are storable and no microcode step reads them - " +
    "three retired fields, and the card must not perform them",
    live.length ? `now read: ${live.join(", ")}` : "")
}

/* ---- the `video` card's one hand-written claim left on 2026-09-20 --------
 * It read `graphics.md` §13's +$15 VDATA out of `regfile.ts` and asserted
 * that `vsup.cpld.ts` exported VDSEL, because the analysis above cannot see
 * a decode that crosses parts. `video3` is the machine's video card and
 * `v3card_tb` exercises its own VDATA port directly, so the claim went with
 * the card it was about. `hardware/archive/video/docs/history.md` has it. */

/* ---- which part each one is on, computed ---------------------------------- *
 * ⚠ BECAUSE PROSE GETS THIS WRONG. This card has two CPLDs and the video card
 * has three, and a sentence like "four of the eight are on U1" is exactly the
 * kind of claim that drifts from the designs and is never checked again. It is
 * derived here instead. */
const WHERE = new Map<string, string[]>()
for (const card of CARDS) {
  for (const p of card.parts) {
    for (const c of p.cells) {
      if (!WHERE.has(c.name)) WHERE.set(c.name, [])
      WHERE.get(c.name)!.push(`${card.name}/${p.name}`)
    }
  }
}
const homeless = Object.keys(RESERVED).filter((n) => !WHERE.has(n))
check(homeless.length === 0,
  "every RESERVED entry names a cell that exists on a part this check knows about",
  homeless.length ? homeless.join(", ") : "")

/* ---- the direction census.ts counted and did not check ------------------- *
 *
 * ⛔ A PIN ON ONE PART THAT ANOTHER PART COMPUTES AND KEEPS. design-review2.md
 * closed "a fitted part reads what nothing produces" by counting every signal
 * some part PRODUCES - and a cell counts as produced whether or not it leaves
 * its part. Found 2026-09-11 in cpld/*.fit: vctrl reads LDHS (pin 51) and LDADV
 * (pin 9), which only vaddr and vsup compute, and buried; vsup reads WSTBV
 * (pin 31), which only vctrl computes, and buried. Three input pins with no
 * driver on silicon - HSCROLL[1:0] and WADV unwritable, span-solid's length
 * never loaded - and every simulation green, because emit.ts makes every cell a
 * Verilog port and the board file wires the net.
 *
 * So: an input of one part that is a cell of another must be in that part's
 * external set. An input no part produces is the board's or the backplane's,
 * and check:netlist is what answers for those. */
{
  const bad: string[] = []
  for (const card of CARDS) {
    for (const p of card.parts) {
      for (const i of p.inputs) {
        const producers = card.parts.filter((q) => q !== p && q.cells.some((c) => c.name === i))
        if (producers.length && !producers.some((q) => q.external.has(i))) {
          bad.push(`${card.name}: ${p.name} reads ${i}, which ${producers.map((q) => q.name).join(" and ")} compute${producers.length > 1 ? "" : "s"} and nobody exports`)
        }
      }
    }
  }
  for (const b of bad) console.log(`      ${b}`)
  check(bad.length === 0,
    "every input pin that another part computes is an OUTPUT pin of that part - a cell is not a net until it leaves its package",
    bad.length ? `${bad.length} undriven` : "")
}

/* ---- the headline, so a reader does not have to count ------------------- */
const byWhy = (w: Why) => Object.entries(RESERVED).filter(([, v]) => v.why === w)
console.log("")
console.log(`      ${dangling.length} signals produced and read by nothing:`)
const EXTRA: Record<string, number> = { stale: 3 }   // DAT, ATT and PAN
for (const w of ["open", "stale", "dead", "board"] as Why[]) {
  const pat = RESERVED_RE.filter((r) => r.why === w)
  const n = byWhy(w).length + (EXTRA[w] ?? 0) +
            dangling.filter((d) => pat.some((r) => r.re.test(d))).length
  console.log(`        ${w.padEnd(6)} ${n}${w === "open" ? "   <- register bits the host can write and the card cannot perform" : ""}`)
  for (const [name] of byWhy(w)) {
    console.log(`          ${name.padEnd(9)} ${(WHERE.get(name) ?? ["?"]).join(", ")}`)
  }
  for (const r of pat) {
    const hits = dangling.filter((d) => r.re.test(d))
    console.log(`          ${String(r.re).padEnd(9)} x${hits.length}  video3`)
  }
}

/* ---- ⛔ and the other direction's findings, which are the new ones ------ */
console.log("")
console.log(`      ${FINDINGS.length} inputs a part reads that nothing on its card produces:`)
for (const w of ["unbuilt", "alias"] as Src[]) {
  const f = FINDINGS.filter((x) => x.why === w)
  if (!f.length) continue
  console.log(`        ${w}   ${f.length}${w === "unbuilt" ? "   <- control lines whose BLOCK HAS NOT BEEN DESIGNED" : "   <- one net, two names, and nothing says so"}`)
  const seen = new Set<string>()
  for (const x of f) {
    console.log(`          ${`${x.part}.${x.name}`.padEnd(18)}`)
    if (!seen.has(x.note)) { seen.add(x.note); console.log(`            ${x.note}`) }
  }
}
console.log("")
console.log("      stale counts audio.md §9.3's DAT, ATT and PAN alongside the bits -")
console.log("      state-file FIELDS with no signal of their own.")
console.log("")
console.log("      ⭐ ON THE FOUR CARDS THIS CENSUS COVERS - audio, video3, storage and")
console.log("      the motherboard - no promised feature is missing. ⚠ `video` left the")
console.log("      census on 2026-09-20 when it was archived; `machine_tb` still builds")
console.log("      the card and nothing counts it (hardware/archive/README.md).")
console.log("      ⚠ What a census of this shape still cannot see is a feature with no")
console.log("      register behind it at all - which is how §6.1's volume x4 hid.")
console.log("")
console.log("      \u2b50 AND VIDEO3'S TWO SEQUENCERS WERE BUILT 2026-09-19, which is")
console.log("      what emptied most of the second list. The span writer's is v3ptr's")
console.log("      (117 -> 119/128, cascades flat at 3); the copy engine's phase machine")
console.log("      is v3host's, because v3ptr does not fit with both. \u00a77.2's column")
console.log("      reload and the register file's address followed, and on 2026-09-19")
console.log("      the last six - RMAP, RRD, WRCYC, RDCK, RSTART and IRQEN.")
console.log("      \u2b50 NOTHING IS UNBUILT. Every signal any video3 part reads is now")
console.log("      produced by a part, by the board, or by the backplane.")
console.log("      \u2b50 And no aliases: the four were one net under two names (FBOE) or")
console.log("      not an alias at all (SRC), and video3_card.v wires every pin from")
console.log("      the term lists, where v3card_tb runs the card end to end.")
console.log("      \u26a0 What this census cannot see is a net the BOARD needs and no")
console.log("      package lets out - video3_card.v's GAP_1..GAP_7.")

process.exit(failures === 0 ? 0 : 1)
