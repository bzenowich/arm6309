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
import { mmuDesign } from "./mmu.jedec"
import { clkdecDesign } from "./clkdec.jedec"
import { u9Design } from "./u9.jedec"
import { u10Design } from "./u10.jedec"
import type { Cell } from "./jedec/assemble"
import { readFileSync } from "node:fs"
import { join } from "node:path"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

const here = new URL(".", import.meta.url).pathname

/* ---- what a card is: the parts on it, and the board they sit on --------- */
interface Part { name: string; cells: Cell[]; external: Set<string> }
interface Card { name: string; parts: Part[]; boards: string[] }

const part = (name: string, d: { cells: Cell[]; external?: Set<string> }): Part =>
  ({ name, cells: d.cells, external: d.external ?? new Set(d.cells.map((c) => c.name)) })

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
  CTRL3: { why: "stale", note: "⛔ raw volume, RETIRED 2026-09-10. paula.md's AUDxVOL is 0-64, and the words 255, 8-bit volume and attenuator appear NOWHERE in it, so 256-level volume was invented. ⚠ §6.1's ×4 is still not built - §16 item 40 - but it is a DATAPATH gap with no bit behind it now, and no signal-level census can see it" },
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
   * logic cells and is where 11.3's attach chain has to go. */

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
  GCPU0: { why: "board", note: "§5.2.1's CPU grant / SRCSEL[0]" },
  GCPU1: { why: "board", note: "§5.2.1's CPU grant / SRCSEL[1]" },
  GCPU2: { why: "board", note: "§5.2.1's CPU grant / SRCSEL[2]" },
  GCPU3: { why: "board", note: "§5.2.1's CPU grant / SRCSEL[3]" },
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

  const unexplained = bad.filter((n) => !(n in RESERVED))
  check(unexplained.length === 0,
    `${card.name}: every signal it produces is read by a term, by the board, or is on RESERVED`,
    unexplained.length ? `unexplained: ${unexplained.join(", ")}` : "")
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
  const micro = readFileSync(join(here, "aseq.micro.ts"), "utf8")
  /* ⚠ CUT AT HOSTMAP. The host map is what lets a field be WRITTEN, and being
   * writable is precisely what DAT, ATT and PAN already are - reading it as
   * evidence of a consumer is the check answering its own question. */
  const prog = micro.slice(micro.indexOf("PROGRAM"), micro.indexOf("HOSTMAP"))
  /* offset -> the (word, lane) audio.md 9.3 puts it at */
  const FIELD: Record<string, { w: number; lane: number; why: Why; note: string }> = {
    DAT: { w: 6, lane: 0, why: "open", note: "§1 requirement 8's CPU-fed sample" },
    ATT: { w: 6, lane: 1, why: "open", note: "Paula's ADKCON bits - §11.3 says Build it" },
    PAN: { w: 7, lane: 2, why: "stale", note: "§11.1's panning, withdrawn 2026-09-09" },
  }
  const live: string[] = []
  for (const [name, f] of Object.entries(FIELD)) {
    /* a step that names this word AND this lane, anywhere but HOSTMAP */
    const re = new RegExp(`w:\\s*${f.w}\\b[^}]*lane:\\s*${f.lane}\\b|lane:\\s*${f.lane}\\b[^}]*w:\\s*${f.w}\\b`)
    if (re.test(prog)) live.push(name)
  }
  check(live.length === 0,
    "audio.md §9.3: DAT, ATT and PAN are storable and no microcode step reads them - " +
    "three register-map promises the sequencer does not keep",
    live.length ? `now read: ${live.join(", ")}` : "")
}

/* ---- and one the analysis above cannot see ------------------------------ *
 * graphics.md 13 puts VDATA at +$15 - "read or write VRAM byte at WPTR,
 * post-increment", which is §11's readable VRAM. regfile.ts is the register
 * decode of record and has no entry for it, so there is no signal to dangle:
 * the feature is absent rather than unread, and only the MAP knows it was
 * promised. */
{
  const regs = readFileSync(join(here, "regfile.ts"), "utf8")
  const decoded = /\bVDATA\s*:/.test(regs)
  check(!decoded,
    "graphics.md §13's +$15 VDATA is in the register map and NOT in regfile.ts's " +
    "decode - §11's readable VRAM is promised and absent",
    decoded ? "it is decoded now - take this claim out and give it a real one" : "")
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

/* ---- the headline, so a reader does not have to count ------------------- */
const byWhy = (w: Why) => Object.entries(RESERVED).filter(([, v]) => v.why === w)
console.log("")
console.log(`      ${dangling.length} signals produced and read by nothing:`)
const EXTRA: Record<string, number> = { open: 2, stale: 1 }   // DAT, ATT; and PAN
for (const w of ["open", "stale", "dead", "board"] as Why[]) {
  const n = byWhy(w).length + (EXTRA[w] ?? 0)
  console.log(`        ${w.padEnd(6)} ${n}${w === "open" ? "   <- register bits the host can write and the card cannot perform" : ""}`)
  for (const [name] of byWhy(w)) {
    console.log(`          ${name.padEnd(9)} ${(WHERE.get(name) ?? ["?"]).join(", ")}`)
  }
}
console.log("")
console.log("      open is audio.md §9.3's DAT and ATT - state-file FIELDS with no")
console.log("      signal of their own; stale counts PAN alongside them.")
console.log("")
console.log("      ⚠ TWO MORE MISSING FEATURES HAVE NO SIGNAL AT ALL, and no census")
console.log("      of this shape can see them: graphics.md §13's +$15 VDATA, absent")
console.log("      from the decode and asserted separately above, and audio.md")
console.log("      §6.1's volume ×4, a datapath that was never built (§16 item 40).")
console.log("      FOUR missing features, not two.")

process.exit(failures === 0 ? 0 : 1)
