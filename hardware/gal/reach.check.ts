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
 * real hole and `graphics.md` §19 item 34 is its size: `cards/video.circuit.tsx`
 * is a partial board, so `check:netlist` cannot close it either.
 */

import { audioCpld } from "./audio.cpld"
import { aseqCpld } from "./aseq.cpld"
import { vctrlCpld, vaddrCpld } from "./video.cpld"
import { vsupCpld } from "./vsup.cpld"
import { v3dot } from "./video3/v3dot.cpld"
import { v3scan } from "./video3/v3scan.cpld"
import { v3ptr } from "./video3/v3ptr.cpld"
import { v3host } from "./video3/v3host.cpld"
import { mmuDesign } from "./mmu.jedec"
import { clkdecDesign } from "./clkdec.jedec"
import { u9Design } from "./u9.jedec"
import { u10Design } from "./u10.jedec"
import type { Cell } from "./jedec/assemble"
import { readFileSync } from "node:fs"
import { PROGRAM, type Step } from "./aseq.micro"
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
    boards: ["verilog/audio_card.v"],
  },
  {
    name: "video",
    parts: [part("vctrl", vctrlCpld), part("vaddr", vaddrCpld), part("vsup", vsupCpld)],
    boards: ["verilog/video_card.v", "verilog/machine.v"],
  },
  /* ⛔ VIDEO3 HAS NO BOARD FILE, and that is why it is in this check twice
   * over. `plan.md` §15 step 8 owes `video3_card.v` and `check:netlist`; until
   * they exist every pin that leaves a part reads as dangling here, so the
   * RESERVED patterns below carry the whole card's I/O as `board`. ⚠ That is a
   * hole, not a pass - the same hole `graphics.md` §19 item 34 records for the
   * video card's partial board, one size larger. */
  {
    name: "video3",
    parts: [part("v3dot", v3dot), part("v3scan", v3scan),
      part("v3ptr", v3ptr), part("v3host", v3host)],
    boards: [],
    checkInputs: true,
    noBoard: "plan.md §15 step 8: video3_card.v and check:netlist are owed",
  },
  {
    name: "motherboard",
    parts: [part("mmu", mmuDesign), part("clkdec", clkdecDesign),
      part("u9", u9Design), part("u10", u10Design)],
    boards: ["verilog/mainboard.v", "verilog/machine.v"],
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
    t = t.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/\/\/[^\n]*/g, " ")
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
  CTRL0: { why: "board", note: "§7's LED filter, into the 74HC4066 (place/parts.ts)" },
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
  WAIT: { why: "board", note: "§7.4's open-drain /WAIT; machine.v takes WAIT_OE" },

  /* ================= video: the eight per-chip grants =================== *
   * ⚠ §5.2.1's grants go to the four framebuffer SRAMs' /WE and the four
   * '153 source selects. video_card.v models the write with WEN and WPTR
   * instead, so nothing in the model wires them - which is graphics.md §19
   * item 34's partial board, not a design hole. check:netlist is what should
   * close this and cannot yet. */
  /* ⛔ GCPU0-3 WERE HERE, "board": §5.2.1's CPU grant, for a flat CPU read
   * that reserved its chip. Deleted 2026-09-11 - every CPU VRAM access is at
   * WPTR (graphics.md 11). What is left is arbDesign's own four outputs, kept
   * because that GAL22V10 is what access.check.ts and cupl.check.ts execute. */
  /* ⭐ ACPU0-3 LEFT THIS LIST 2026-09-12 WITH THEIR EQUATIONS. They were
   * arbDesign's CPU grants renamed on merge, and every one read
   * `VPORT & !CPUIDLE & CPUIDLE & ...` - false by inspection, because ARB_MAP
   * maps four different inputs onto CPUIDLE, which is `terms: []`. The .pld
   * carried them to the fitter, which minimised them away in silence. merge()
   * folds constants now (jedec/cupl.ts), so a term containing a constant-0
   * literal dies and a cell whose every term dies is dropped. */
  CPUIDLE: { why: "dead", note: "⛔ graphics.md 11: the CPU reserves no framebuffer chip, so arbDesign's two address bits, its R/W and its /IOPAGE are all renamed onto this constant 0 (video.cpld.ts ARB_MAP). Nothing reads it since the fold - it is kept as a CELL because merge() would otherwise synthesise it as an input PIN, and deleted only when ARB_MAP stops naming it" },
  GSPN0: { why: "board", note: "§5.2.1's span-writer grant, chip 0" },
  GSPN1: { why: "board", note: "§5.2.1's span-writer grant, chip 1" },
  GSPN2: { why: "board", note: "§5.2.1's span-writer grant, chip 2" },
  GSPN3: { why: "board", note: "§5.2.1's span-writer grant, chip 3" },

  /* ================= video: graphics.md 13 ============================== *
   * ⚠ CHAR IS DELIBERATELY ABSENT. video.cpld.ts builds no cell for CTRL b2 -
   * the macrocell went to the mask serialiser when §6.4.3's Variant B was
   * dropped - so there is no signal to dangle. The design is right and §13's
   * prose is what is stale: it still describes b2 as "with CELL: 0 tile, 1
   * character". A doc fix, not a silicon one. */
  /* ⭐ LDFB WAS HERE AND IS DELETED - 2026-09-10. FONTBASE's load strobe, for
   * §6.4.3's dropped Variant B: one cell on vaddr, which is the video part that
   * cannot spare them. regfile.ts has the derivation. */
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
  /* video3, and every one of these is `board` for the SAME reason: there is
   * no video3_card.v. When there is one, most of them leave this list. */
  { re: /^FBA(\d+)$/, why: "board",
    note: "plan §6: the framebuffer address, to the four AS6C8016 - v3scan and v3ptr each drive all seventeen and FBOE decides which" },
  { re: /^ATO[0-7]$/, why: "board", note: "plan §2.2: the attribute byte, to the '574 that feeds the LUT's high half" },
  { re: /^(HSYNC|VSYNC)$/, why: "board", note: "signals.md §1.9: the connector AND the backplane - graphics.md §12.2's line compare" },
  { re: /^(FOE0|FOE1|FBOESCAN|FBOEPTR|PIXOE|ATOE|PIDXOE|PIDXCE|VSTATOE|RDOE|RDBKOE|LUTWE)$/,
    why: "board", note: "output enables and write strobes for discrete parts - '574, '244, '245 and the LUT" },
  { re: /^(MUXSEL0|MUXSEL1|OMR|MK2|MS0|SI5|NSL7|CT[4-6])$/, why: "board",
    note: "plan §3: the dot path's muxes and the serialisers' state, to discrete parts" },
  { re: /^(SPRLD)$/, why: "board", note: "plan §7: loads the four '165 that hold the sprite row" },
  { re: /^RFA[0-4]$/, why: "board",
    note: "plan §5: the 32K x 8 register file's address pins. ⛔ RFA0 is v3ptr's and RFA4..RFA1 are v3host's, because §5 makes bit 0 the span-mask bit and the serialiser is on v3ptr - the rest is an ordinary address and the four-dot reload walk that drives it did not fit beside the serialiser" },
  { re: /^WEN$/, why: "board",
    note: "plan §5: the framebuffer write strobe - RETIRE except a transparent pixel in sprite mode. ⚠ NOT the same signal as RETIRE, and a mode that gated the pointer instead would draw the sprite squashed" },
  { re: /^(WSTBV|WADV[01]|RDREQ|PBUSY|WAITN|IRQN)$/, why: "board",
    note: "signals.md §1.9: the posted write, /WAIT and /IRQ open-drain, and the status the host reads" },
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
  { re: /^(CLK25|RESET)$/, why: "bus", note: "the card's 25.175 MHz dot clock and its reset" },
  { re: /^D[0-7]$/, why: "bus", note: "partition.md §3: the register broadcast - the host data bus, decoded in each part" },
  { re: /^(A[0-6]|A19|A20|E|RW|IOSEL|IOPGH)$/, why: "bus", note: "plan §10: the host bus into v3host, which owns the register decode" },
  { re: /^P[AB][0-7]$/, why: "board", note: "plan §2.5: the map WORD, two bytes from the map SRAM into v3scan" },

  /* ⛔ findings from here down */
  { re: /^(SRC0|SRC1)$/, why: "alias",
    note: "v3scan's address-mux select. v3dot exports MUXSEL0 and MUXSEL1 and nothing declares them the same net" },
  { re: /^FBOE$/, why: "alias",
    note: "⛔ WORSE THAN AN ALIAS: v3ptr AND v3scan each declare a plain FBOE, and v3dot exports TWO signals, FBOESCAN and FBOEPTR. v3scan's own comment says FBOE 'is what keeps exactly one of the two parts on the bus' - one name on both parts keeps them both on or both off, and they drive the same seventeen nets" },
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

/* ---- and one the analysis above cannot see ------------------------------ *
 * graphics.md 13's +$15 VDATA - "read or write VRAM byte at WPTR,
 * post-increment". It was retired on 2026-09-11 as a second address for the
 * window's port and BUILT the same day (19 item 47), for tasks and handlers
 * with no MMU block to spare. The claim is turned round again: the map names
 * it, so something must decode it, and the decode must leave its part. */
{
  const regs = readFileSync(join(here, "regfile.ts"), "utf8")
  const decoded = /\bVDATA\s*:/.test(regs)
  const vsupSrc = readFileSync(join(here, "vsup.cpld.ts"), "utf8")
  const exported = /"VDSEL"/.test(vsupSrc)
  check(decoded && exported,
    "graphics.md §13's +$15 VDATA is decoded and its select leaves vsup for vctrl's " +
    "posted write and /WAIT - the map names it, so a part must build it",
    !decoded ? "VDATA is not in regfile.ts's map" : !exported ? "VDSEL is not exported" : "")
}

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
console.log("      ⭐ ON THE THREE BUILT CARDS no promised feature is missing, as of")
console.log("      2026-09-11: §11's readable VRAM is built at WPTR, through the window")
console.log("      and through +$15 VDATA.")
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
console.log("      \u26a0 And the four `alias` entries are NOT progress: they are one net")
console.log("      under two names, which is a defect the fitter cannot see.")

process.exit(failures === 0 ? 0 : 1)
