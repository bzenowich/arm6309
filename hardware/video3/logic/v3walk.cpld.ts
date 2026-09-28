/* v3walk - video3's sprite walker: optimizations.md §12, plan.md §6.4.
 *
 * ⭐ WHAT IT IS. A fifth ATF1508AS that loads the copy engine's nine registers
 * itself, out of tables in the register file, so a frame's actor pass is one
 * command instead of 9 register writes a rectangle. Per slot it runs up to
 * three copies - RESTORE (the save-behind back over last frame's position),
 * SAVE (the background under this frame's position) and DRAW (the shape,
 * KEYED) - and the CPU is free from the moment the command is written.
 *
 * ⭐ IT MASQUERADES AS THE CPU. Every part on the card already takes its
 * registers off the broadcast (REGWR, RA4..RA0, IDB) and writes the file's
 * shadow on WSTB, so the walker drives those same nets while it runs - v3host
 * lets go of them on WALK - and v3ptr, v3dot and the column reload cannot
 * tell a walker load from a store. No part's decode changes; v3ptr, the one
 * with no room, is not touched at all.
 *
 * ⭐ THE TABLES ARE IN THE REGISTER FILE, WHICH WAS 32 BYTES OF A 32 KB PART.
 * RFA14..RFA5 were tied low; this part drives RFA13..RFA5 as a PAGE, and every
 * table byte sits at offset +$1D of its page:
 *
 *     page = { T[2:0], SLOT[3:0], BYTE[1:0] }       (RFA13..11, 10..7, 6..5)
 *
 *     T1  STREAM A   the §12 record: X[7:0], Y[7:0], { SHAPE[4:0], X[9:8], Y[8] }
 *     T2  STREAM B   the same - two banks, so last frame's positions survive
 *                    this frame's stream and the restore needs no copy of them
 *     T3  DIM        CWIDTH[7:0], CHEIGHT[7:0], the CCTRL image (b0 is forced)
 *     T4  SAVE       a CPTR-layout pointer to the slot's save-behind rectangle
 *     T5  SHAPE 0-15, T6 SHAPE 16-31: a CPTR-layout pointer for each shape
 *     T0  never a table: page 0 is where the file's CPU registers live
 *
 * The CPU fills a table through +$1D after a SELECT on +$1E; the page follows
 * a pointer here, and every other register access - the span's WFG/WBG, the
 * reload walk, the CPU's own - sees page 0 exactly as before.
 *
 * ⭐ +$1E, SWCMD:
 *     D7 = 1  SELECT: D6..D3 = first slot, D2..D0 = table; the byte field is 0
 *     D7 = 0  GO:     D3..D0 = n - 1 slots, D4 = NR (no restore pass - the
 *                     first frame), D5 = RO (restore only - the wipe), D6 = the
 *                     bank this frame's stream is in; the restore reads the other
 *
 * ⭐ A SELECT OF TABLE 7 IS "ARM": the next GO does not start the walk, it waits
 * for VBLANK's rise and starts itself on the first E fall after it - so a frame
 * can write its GO whenever its work is done and the walk still begins at line
 * 480 and not when software noticed the blank. Between the armed GO and the
 * start, CMD holds the GO and the CPU must not touch SWCMD, SWDAT, the copy
 * engine or the VRAM port (the emulator enforces it).
 *
 * ⭐ SHAPE 31 IS "NO SHAPE". A record whose byte 2 has SHAPE = 31 is skipped by
 * whichever copy reads it: the restore of a slot whose last-frame record is
 * null, and the save and draw of one whose this-frame record is. So a parked
 * or unused slot costs a few dots, not three copies, and a slot can come and
 * go without a wipe.
 *
 * ⭐ THE ORDER IS LIFO, AND IT IS WHAT MAKES OVERLAP CORRECT. The restore pass
 * runs slots n-1 down to 0; the save-and-draw pass 0 up to n-1. Every actor is
 * restored every frame, so undoing the draws in reverse leaves the terrain
 * exactly as it was, however the rectangles overlap.
 *
 * ⚠ THE CONTRACT, which the emulator enforces: WMODE is not 11 (the key would
 * catch the restores and saves too) and WADV b2 is clear while a walk runs.
 * The CPU is /WAITed on any card access but a VSTAT read, and VSTAT b2 is WALK.
 *
 * ⭐ AND THE VBL INTERRUPT MOVED HERE, which is what paid for WALK's pin on
 * v3host (64/64 I/O): IRQPEND, IRQEN (CTRL b6), the ack on a VSTAT write and
 * the open-drain /IRQ, off the same broadcast. */

import { toCupl, type Merged } from "../../tools/gal/jedec/cupl"
import type { Cell } from "../../tools/gal/jedec/assemble"
import { sop } from "../../tools/gal/jedec/truth"
import { REGS, type RegName } from "./regmap"

const reg = (name: string, terms: string[], low = false): Cell =>
  ({ pin: 0, name, assertedLow: low, s0: 1 as const, registered: true, terms })
const comb = (name: string, terms: string[], oe?: string, low = false): Cell =>
  ({ pin: 0, name, assertedLow: low, s0: 1 as const, registered: false, terms, oe })

const B8 = [...Array(8).keys()]
const B4 = [0, 1, 2, 3]
/* the broadcast as this part SEES it: its own pins drive the same nets, so it
 * observes them on separate inputs (SREGWR, SRA4..SRA0) and decodes those */
const sdec = (r: RegName) =>
  `SREGWR & ${[4, 3, 2, 1, 0].map((b) => `${(REGS[r] >> b) & 1 ? "" : "!"}SRA${b}`).join(" & ")}`

/* -- the CPU's side: SELECT, the table port, GO, and the VBL interrupt ---- */
const host: Cell[] = [
  comb("LDSWDAT", [`${sdec("LDSWDAT")} & !WALK`]),
  comb("LDSWCMD", [`${sdec("LDSWCMD")} & !WALK`]),
  /* ⭐ THE COMMAND BYTE IS LATCHED ON EVERY REGISTER WRITE, and only what
   * happens at the END of a write decides whether it was one. A hold on
   * "not this offset" costs a term per address literal on every bit; a load on
   * "any write" costs one, and the byte is used on the dot after the write
   * ends, before another can begin. During a walk it is the walk's operand -
   * CMD3..CMD0 is n-1 and counts down through the save-and-draw pass. */
  /* ⭐ and it HOLDS while an armed GO is pending, so the scroll and CTRL
   * writes of the rest of the frame cannot take the walk's operand away */
  comb("CMDLD", ["SREGWR & !WALK & !PEND"]),
  ...B8.slice(0, 7).map((k) => reg(`CMD${k}`, k < 4
    ? sop(["CMDLD", "WALK", `D${k}`, "STEPQ", "PASSR", "KD", "CMD0", "CMD1", "CMD2", "CMD3"],
        (v) => {
          if (v.CMDLD) return v[`D${k}`]
          const n = (v.CMD0 ? 1 : 0) | (v.CMD1 ? 2 : 0) | (v.CMD2 ? 4 : 0) | (v.CMD3 ? 8 : 0)
          const dec = v.WALK && v.STEPQ && !v.PASSR && v.KD
          return ((((dec ? n - 1 : n) & 15) >> k) & 1) === 1
        })
    : [`CMDLD & D${k}`, `!CMDLD & CMD${k}`])),
  /* the ends of the three writes: each level remembered a dot, and the dot
   * after it ends is when it acts - the copy's GO and the span's WSTART are
   * the same idiom (graphics.md §19 item 37) */
  reg("SELQ", ["LDSWCMD & D7"]),
  reg("GOQ", ["LDSWCMD & !D7"]),
  reg("DATQ", ["LDSWDAT"]),
  comb("SELE", ["SELQ & !SREGWR"]),
  /* ⭐ ARM, the pending GO, and the start it waits for. RDY is VBLANK's rise
   * seen by a pending GO; the start is the next E fall after it, which is where
   * a GO written by the CPU starts too - no CPU register write is half done,
   * and the prefetch finished long ago under the contract */
  reg("ARM", ["SELE & CMD0 & CMD1 & CMD2 & !RESET", "ARM & !GOQ & !RESET", "ARM & SREGWR & !RESET"]),
  reg("PEND", ["GOQ & !SREGWR & ARM & !RESET", "PEND & !RDY & !RESET", "PEND & E & !RESET",
               "PEND & !EQ & !RESET"]),
  reg("RDY", ["PEND & VBLANK & !VBLQ & !RESET", "RDY & PEND & !RESET"]),
  reg("EQ", ["E"]),
  comb("START", ["GOQ & !SREGWR & !ARM", "RDY & EQ & !E"]),
  /* the table pointer: T, slot and byte. The byte counts 0, 1, 2 and the slot
   * steps as it wraps, so a table is written as consecutive three-byte rows */
  ...[0, 1, 2].map((k) => reg(`PT${k}`, [`SELE & CMD${k}`, `PT${k} & !SELQ`, `PT${k} & SREGWR`])),
  ...[0, 1].map((k) => reg(`PY${k}`, sop(["SELQ", "DATQ", "SREGWR", "PY0", "PY1"], (v) => {
    const by = (v.PY0 ? 1 : 0) | (v.PY1 ? 2 : 0)
    if (v.SELQ && !v.SREGWR) return false
    const nx = v.DATQ && !v.SREGWR ? (by === 2 ? 0 : by + 1) : by
    return ((nx >> k) & 1) === 1
  }))),
  ...B4.map((k) => reg(`PS${k}`, sop(["SELQ", "DATQ", "SREGWR", `CMD${k + 3}`, "PY1",
                                     "PS0", "PS1", "PS2", "PS3"], (v) => {
    if (v.SELQ && !v.SREGWR) return v[`CMD${k + 3}`]
    const s = (v.PS0 ? 1 : 0) | (v.PS1 ? 2 : 0) | (v.PS2 ? 4 : 0) | (v.PS3 ? 8 : 0)
    const nx = v.DATQ && !v.SREGWR && v.PY1 ? (s + 1) & 15 : s
    return ((nx >> k) & 1) === 1
  }))),
  /* ⭐ the VBL interrupt, moved from v3host (see the header) */
  comb("LDIRQACK", [sdec("LDIRQACK")]),
  comb("LDCTRL", [sdec("LDCTRL")]),
  reg("VBLQ", ["VBLANK"]),
  reg("IRQPEND", ["VBLANK & !VBLQ", "IRQPEND & !LDIRQACK"]),
  reg("IRQEN", ["LDCTRL & D6", "IRQEN & !LDCTRL"]),
  comb("IRQN", [], "IRQPEND & IRQEN", true),
]

/* -- the walk -----------------------------------------------------------
 *
 * ⭐ A COPY IS THREE GROUPS OF SIX DOTS, then a wait:
 *
 *   G0  WPTR  +$08 +$09 +$0A       G1  CPTR  +$12 +$13 +$14
 *   G2  CWIDTH, CHEIGHT, CCTRL     +$15 +$16 +$17 - and the CCTRL write is GO
 *
 * Each byte is a READ dot (the file drives IDB from the table's page; this
 * part latches it) and a WRITE dot (this part drives IDB, asserts REGWR and
 * RA, and WSTB writes the file's page-0 shadow - which is what the column
 * reload reads at every row end). A group is PLAIN - a pointer or DIM copied
 * byte for byte - or a REFORMAT of a stream record into pointer layout:
 *
 *   plain     J0 rd b0  J1 wr +0   J2 rd b1  J3 wr +1   J4 rd b2  J5 wr +2
 *   reformat  J0 rd b2  J1 rd b1   J2 wr +1  J3 wr +2   J4 rd b0  J5 wr +0
 *             +1 = { Y[5:0], X[9:8] }   +2 = { Y[8:6] }   +0 = X[7:0]
 *
 * which is §12.2's "pure bus wiring": no adder, the bytes only move lanes.
 *
 *   RESTORE   G0 reformat(old bank)   G1 SAVE      G2 DIM
 *   SAVE      G0 SAVE                 G1 reformat  G2 DIM
 *   DRAW      G0 reformat(new bank)   G1 SHAPE[s]  G2 DIM,  keyed
 *
 * ⚠ The shape number is the record's byte 2, latched in DRAW's G0 and used as
 * the slot of G1's page - so SHAPE's G1 reads cost nothing extra either.
 * ⚠ 18 dots of loads, 0.71 us, against a 32 x 32 copy's 253 us. */
const walk: Cell[] = [
  reg("WALK", ["START & !RESET", "WALK & !ENDQ & !RESET"]),
  /* ⭐ THE WAIT: CBUSY rises two edges after the GO write (v3ptr's GOQ), so
   * two filler dots and then J2 holds until the engine AND the reload walk
   * after its last row are both done */
  /* ⭐ NO SHAPE: SHAPE = 31 in the record a reformat group has just read. B
   * is valid from J1 and a reformat writes nothing before J2, so the copy is
   * abandoned with no register touched but - in SAVE, whose reformat is G1 -
   * WPTR, which the next copy reloads. It steps exactly as a finished copy
   * does, so the pass, the slot and the count need nothing new: a null SAVE
   * steps to DRAW, whose G0 reads the same record and steps again */
  comb("NUL", ["WALK & J1 & RF & B3 & B4 & B5 & B6 & B7"]),
  comb("WNEXT", ["W & J2 & !CBUSY & !RP1 & !RP2 & !RP3 & !RP4", "NUL"]),
  reg("STEPQ", ["WNEXT"]),
  /* registered a dot early, so the step itself is two literals */
  reg("ENDQ", ["WNEXT & PASSR & !WS0 & !WS1 & !WS2 & !WS3 & CMD5",
               "WNEXT & !PASSR & KD & !CMD0 & !CMD1 & !CMD2 & !CMD3"]),
  /* the step's dot is a W dot, so a null's STEPQ writes nothing */
  reg("W", ["G2 & J5", "W & !STEPQ", "NUL"]),
  reg("J0", ["START", "STEPQ & !ENDQ", "J5"]),
  reg("J1", ["J0"]),
  reg("J2", ["J1 & !NUL", "W & J2 & CBUSY", ...[1, 2, 3, 4].map((r) => `W & J2 & RP${r}`)]),
  reg("J3", ["J2 & !W"]),
  reg("J4", ["J3"]),
  reg("J5", ["J4"]),
  reg("G0", ["START", "STEPQ & !ENDQ", "G0 & !J5 & !STEPQ"]),
  reg("G1", ["G0 & J5", "G1 & !J5 & !STEPQ"]),
  reg("G2", ["G1 & J5", "G2 & !J5"]),
  /* the pass (1 = restore) and the kind within save-and-draw (1 = draw) */
  reg("PASSR", ["START & !CMD4", "WALK & PASSR & !STEPQ",
                ...B4.map((b) => `WALK & PASSR & WS${b}`)]),
  reg("KD", ["WALK & KD & !STEPQ", "STEPQ & !PASSR & !KD"]),
  /* 1 while the group is a reformat: RESTORE's and DRAW's G0, SAVE's G1 */
  reg("RF", ["START & !CMD4", "G0 & J5 & !PASSR & !KD",
             ...B4.map((b) => `STEPQ & PASSR & WS${b}`),
             "STEPQ & !PASSR & !KD", "WALK & RF & !J5 & !STEPQ"]),
  /* 1 on a read dot - registered, so the page and the latches take one literal */
  reg("RDQ", ["START", "STEPQ & !ENDQ", "J5 & !G2", "J0 & !W & RF", "J1 & !W & !RF", "J3"]),
  /* the walk's slot: n-1 down to 0 restoring, then 0 up to n-1 */
  ...B4.map((k) => reg(`WS${k}`, sop(["START", "CMD4", `CMD${k}`, "STEPQ", "PASSR", "KD",
                                     "WS0", "WS1", "WS2", "WS3"], (v) => {
    if (v.START) return !v.CMD4 && v[`CMD${k}`]
    const s = (v.WS0 ? 1 : 0) | (v.WS1 ? 2 : 0) | (v.WS2 ? 4 : 0) | (v.WS3 ? 8 : 0)
    let nx = s
    if (v.STEPQ && v.PASSR && s) nx = s - 1
    if (v.STEPQ && !v.PASSR && v.KD) nx = (s + 1) & 15
    return ((nx >> k) & 1) === 1
  }))),
  /* ⭐ THE TWO LATCHES. L takes every read; on a plain write IDB is L anyway,
   * and a reformat's two middle writes are the only dots it must hold. B takes
   * a record's byte 2 on a reformat's J0 and keeps it for the whole copy. */
  ...B8.map((k) => reg(`L${k}`, [`RDQ & D${k}`, `!RDQ & L${k}`])),
  ...B8.map((k) => reg(`B${k}`, [`RDQ & J0 & RF & D${k}`, `B${k} & !J0`, `B${k} & !RF`,
                                `B${k} & !RDQ`])),
]

/* -- what it drives ------------------------------------------------------ */
const WRD = "WALK & !W & !RDQ"
/* RA on a write dot. Every other dot is a don't-care, because REGWR is low */
const RA: string[][] = [
  ["!G2 & J3 & !RF", "!G2 & J2 & RF", "G2 & J1", "G2 & J5"],
  ["G0 & !RF & J5", "G0 & RF & J3", "G1 & !RF & !J5", "G1 & RF & !J3", "G2 & !J1"],
  ["G1 & !RF & J5", "G1 & RF & J3", "G2"],
  ["G0"],
  ["G1", "G2"],
]
/* the reformat's two middle bytes: +1 = { L[5:0], B[2:1] }, +2 = { B0, L7, L6 } */
const P1 = (k: number) => (k === 0 ? "B1" : k === 1 ? "B2" : `L${k - 2}`)
const P2 = (k: number) => (k === 0 ? "L6" : k === 1 ? "L7" : k === 2 ? "B0" : null)
/* the page's table: which one each group reads */
const T0 = ["RF & PASSR & CMD6", "RF & !PASSR & !CMD6", "G2", "KD & G1 & !B7"]
const T1 = ["RF & PASSR & !CMD6", "RF & !PASSR & CMD6", "G2", "KD & G1 & B7"]
const T2 = ["!RF & G0", "!RF & G1"]
const out: Cell[] = [
  /* ⭐ the broadcast, while WALK - v3host's copies float then */
  comb("REGWR", [WRD], "WALK"),
  ...RA.map((t, b) => comb(`RA${b}`, t, "WALK")),
  comb("WSTB", [WRD], "WALK", true),
  /* ⭐ CPURF is v3ptr's "the CPU owns the file": 1 on a write dot so RFA0 is
   * RA0, and 0 otherwise so RFA0 idles at 1 - +$1D's bit 0 on a read dot */
  comb("CPURF", [WRD], "WALK"),
  /* RFA4..RFA1: +$1D (1110) on a read dot, RA on a write dot; v3host's own
   * reload walk has them while RP1..RP4 run */
  comb("RFA1", RA[1].map((t) => `!RDQ & ${t}`), "WALK & !RP1 & !RP2 & !RP3 & !RP4"),
  comb("RFA2", ["RDQ", ...RA[2]], "WALK & !RP1 & !RP2 & !RP3 & !RP4"),
  comb("RFA3", ["RDQ", "G0"], "WALK & !RP1 & !RP2 & !RP3 & !RP4"),
  comb("RFA4", ["RDQ", "G1", "G2"], "WALK & !RP1 & !RP2 & !RP3 & !RP4"),
  /* ⭐ THE PAGE: the pointer during a CPU +$1D write, the table on a read dot,
   * and 0 everywhere else - so a write dot lands on the page-0 shadow */
  comb("RFA5", ["LDSWDAT & PY0", "RDQ & J2 & !RF", "RDQ & J1 & RF"]),
  comb("RFA6", ["LDSWDAT & PY1", "RDQ & J4 & !RF", "RDQ & J0 & RF"]),
  ...B4.map((k) => comb(`RFA${7 + k}`, [`LDSWDAT & PS${k}`, `RDQ & KD & G1 & B${3 + k}`,
                                       `RDQ & !G1 & WS${k}`, `RDQ & !KD & WS${k}`])),
  ...[T0, T1, T2].map((t, k) => comb(`RFA${11 + k}`, [`LDSWDAT & PT${k}`, ...t.map((x) => `RDQ & ${x}`)])),
  /* the data a write dot drives onto IDB. ⭐ CCTRL's b0 is forced: the walk's
   * last load of a copy is always GO */
  ...B8.map((k) => comb(`WD${k}`, [
    `J1 & L${k}`, `J5 & L${k}`, `J3 & !RF & L${k}`,
    ...(P2(k) ? [`J3 & RF & ${P2(k)}`] : []), `J2 & ${P1(k)}`,
    ...(k === 0 ? ["G2 & J5"] : []),
  ], WRD)),
  /* v3lane's key, for the draw copy alone */
  comb("WKEY", ["WALK & KD"]),
]

export const v3walk: Merged = {
  name: "v3walk",
  partNo: "ARM6309-V3W",
  location: "video3 - the sprite walker and the VBL interrupt",
  device: "f1508ispplcc84",
  clock: "CLK25",
  inputs: [
    { name: "CLK25" }, { name: "RESET", activeLow: true },
    /* the broadcast, observed - the same nets its own outputs drive */
    { name: "SREGWR" }, ...[0, 1, 2, 3, 4].map((b) => ({ name: `SRA${b}` })),
    ...B8.map((b) => ({ name: `D${b}` })),
    /* the copy engine and v3host's column reload, which the wait watches */
    { name: "CBUSY" }, ...[1, 2, 3, 4].map((r) => ({ name: `RP${r}` })),
    { name: "VBLANK" },
    /* ⭐ the CPU's E, which an armed GO's start waits to fall */
    { name: "E" },
  ],
  cells: [...host, ...walk, ...out],
  external: new Set([
    "REGWR", "RA0", "RA1", "RA2", "RA3", "RA4", "WSTB", "CPURF",
    ...[...Array(13).keys()].map((i) => `RFA${i + 1}`),
    ...B8.map((k) => `WD${k}`),
    "WKEY", "WALK", "IRQN", "IRQPEND",
  ]),
}

if (import.meta.main) {
  const regs = v3walk.cells.filter((c) => c.registered).length
  console.log(`v3walk: ${v3walk.cells.length} cells (${regs} registers), ` +
    `${v3walk.inputs.length} inputs, ${v3walk.external.size} outputs`)
  console.log(toCupl(v3walk))
}
