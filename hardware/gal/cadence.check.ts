/* graphics.md 6.4's cell-mode fetch cadence, simulated over a whole line.
 *
 * 19 item 15(c) was open because the cadence in video.parts.ts was a sketch: it
 * counted TC0..TC2 on SLOTTICK and split the period at TC2, and since a slot is
 * four dots and a cell is eight, that period was four cells - 16 tile bytes
 * fetched where 32 are needed, one map byte latched where four are. Nothing
 * caught it, because nothing had ever run the sequence.
 *
 * This runs it. The cadence cells are sums of products over hgen's slot counter
 * and seqph's dot phase, so a whole line is 800 dots of evaluating them and
 * counting what the sequence actually does:
 *
 *   - every displayed cell gets exactly one map access, one cell early
 *   - the tile address owns the display half of every fetch slot
 *   - 6.4.2's "9 accesses per 8 dots" and "2.25 per chip per cell" both hold
 *   - exactly one requester drives the card's single internal address bus
 *   - the span writer stands down in map slots, and the CPU waits when the map
 *     takes its chip
 *
 *   npm run check:cadence
 */

import { tileCadence } from "./video.parts"
import { H, V449, V525, SLOTS_PER_LINE, DOTS_PER_SLOT } from "./sync.timing"
import { vadrDesign } from "./scan.jedec"
import { vaddrCpld } from "./video.cpld"
import { MAP_COLS } from "./tile.model"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

/* -- a sum-of-products evaluator over a named world ---------------------- */
const cells = new Map(tileCadence.map((c) => [c.name, c.terms]))
const evalIn = (world: Map<string, number>) => {
  /* Cells read other cells (TILESEL reads MAPSEL, GCPU reads GMAP), so settle
   * by iterating. Every cadence output starts at 0 and is RECOMPUTED on each
   * pass - seeding them into the input map instead is what made the first
   * version of this file report a dead line. The cadence has no feedback, so
   * three passes over a chain three deep is a fixed point. */
  const val = new Map(world)
  for (const name of cells.keys()) if (!val.has(name)) val.set(name, 0)
  const literal = (l: string): number => {
    const neg = l.startsWith("!")
    const name = neg ? l.slice(1) : l
    const v = val.get(name)
    if (v === undefined) throw new Error(`cadence reads an undefined signal: ${name}`)
    return neg ? 1 - v : v
  }
  for (let pass = 0; pass < 4; pass++) {
    for (const [name, terms] of cells) {
      let v = 0
      for (const t of terms) {
        if (t.split(" & ").every((l) => literal(l.trim()) === 1)) { v = 1; break }
      }
      val.set(name, v)
    }
  }
  return val
}

const bitsOf = (prefix: string, value: number, n: number) =>
  [...Array(n).keys()].map((i) => [`${prefix}${i}`, (value >>> i) & 1] as const)

/** One dot of a line, in cell mode, with no CPU or span-writer activity. */
const dotWorld = (slot: number, ph: number, extra: Record<string, number> = {}) => {
  const w = new Map<string, number>([
    ...bitsOf("H", slot, 8),
    ["PH0", ph & 1], ["PH1", (ph >> 1) & 1],
    /* seqph's, derived here rather than seeded: it is dot 3, and it is what
     * turns a window into a once-per-slot counter enable. */
    ["SLOTTICK", ph === 3 ? 1 : 0],
    /* A displayed line in the middle of the frame: not blanked, V even so the
     * doubled modes advance. The frame section below sweeps V properly. */
    ["VBLANK", 0], ["V0", 0], ["VMODE1", 1],
    ["TILEMODE", 1], ["SPNREQ", 0], ["SPNGRANT", 0],
    ["SPANBUSY", 0], ["RW", 1], ["A0", 0], ["A1", 0],
    ["MAPA0", 0], ["MAPA1", 0],
    /* arbDesign's raw CPU grants, renamed on merge (video.cpld.ts). */
    ["ACPU0", 0], ["ACPU1", 0], ["ACPU2", 0], ["ACPU3", 0],
    ...Object.entries(extra),
  ])
  return evalIn(w)
}

/* -- the shape of one line ------------------------------------------------ */
const line: { slot: number; ph: number; v: Map<string, number> }[] = []
for (let slot = 0; slot < SLOTS_PER_LINE; slot++) {
  for (let ph = 0; ph < DOTS_PER_SLOT; ph++) line.push({ slot, ph, v: dotWorld(slot, ph) })
}

/* -- 1. the windows, and the one-cell lead ------------------------------- */
{
  const on = (n: string) => line.filter((d) => d.v.get(n) === 1).map((d) => d.slot)
  const span = (n: string) => {
    const s = on(n)
    return s.length ? [Math.min(...s), Math.max(...s)] : []
  }
  const [tf0, tf1] = span("TFETCH"), [mf0, mf1] = span("MFETCH")
  check(tf0 === H.backEnd + 1 && tf1 === H.activeEnd,
    `TFETCH is the active window, slots ${H.backEnd + 1}..${H.activeEnd}`, `${tf0}..${tf1}`)
  check(mf0 === tf0! - 2 && mf1 === tf1! - 2,
    "MFETCH leads it by exactly one cell - two slots - which is 6.4.1's " +
    "\"pipelined one cell ahead\" and the reason MC exists", `${mf0}..${mf1}`)
  check(span("HLOAD")[1] === mf0! - 1,
    "HLOAD closes the slot before MFETCH opens, so both column counters have " +
    "their scroll offset before the first map byte is fetched", `${span("HLOAD")}`)
  /* 640 pixels is 160 slots is 80 cells. */
  check(tf1! - tf0! + 1 === 160 && (tf1! - tf0! + 1) / 2 === MAP_COLS,
    `the fetch window is 160 slots = ${MAP_COLS} cells = 640 pixels`)

  /* ⚠ AND THE COLUMN COUNTER MUST STEP ONCE PER SLOT, NOT ONCE PER DOT. FETCH
   * is 8's enable on hadr and hadr is clocked on DOTCLK, so a bare window level
   * advances it four times a slot and puts the line four times too far along -
   * with HSCROLL still loading correctly, which is what would make it look like
   * a scroll bug rather than a clocking one. Counted per dot, the way the
   * silicon clocks it. */
  const fetchEdges = line.filter((d) => d.v.get("FETCH") === 1).length
  check(fetchEdges === 160,
    "FETCH is exactly 160 clock edges - one per slot of the window, not one " +
    "per dot - so §8's column counter walks 640 pixels and not 2,560",
    `${fetchEdges}`)
  const mcEdges = line.filter((d) => d.v.get("MCADV") === 1).length
  check(mcEdges === MAP_COLS,
    `and MCADV is exactly ${MAP_COLS} - one per cell of the map window, same gate`,
    `${mcEdges}`)
}

/* -- 2. one map access per cell, and it is the RIGHT cell ---------------- */
{
  /* MC steps on MCADV, so walk the line the way the counter does - and the way
   * it does is ONE STEP PER DOT that MCADV is high, because vaddr is clocked on
   * DOTCLK. Modelling it as one step per rising EDGE is what let a bare level
   * pass here on 2026-09-08: in silicon that counter would have run four times
   * a slot. A clock edge per dot is the honest model and it is what makes the
   * SLOTTICK gate on FETCH and MCADV load-bearing. */
  let mc = 0
  const fetchedFor: number[] = []      // map cell fetched, in order
  for (const d of line) {
    if (d.ph === 0 && d.v.get("MAPREQ") === 1) fetchedFor.push(mc)
    if (d.v.get("MCADV") === 1) mc++
  }
  check(fetchedFor.length === MAP_COLS,
    `exactly ${MAP_COLS} map accesses per line - one per displayed cell, no more`,
    `${fetchedFor.length}`)
  check(fetchedFor.every((c, i) => c === i),
    "and they are cells 0..79 in order, so MC names the cell being fetched " +
    "throughout the cell that fetches it", fetchedFor.slice(0, 6).join(","))

  /* The lead: the map byte for cell k is latched before cell k's first tile
   * fetch. MAPLD for cell k lands in slot mf0 + 2k, dot 1; the tile fetch for
   * cell k is slot tf0 + 2k, dots 2-3. */
  const mapld = line.filter((d) => d.v.get("MAPLD") === 1)
  check(mapld.length === MAP_COLS && mapld.every((d) => d.ph === 1),
    "MAPLD is one dot per cell and it is dot 1 - the boundary between 5.2.2's " +
    "spare half and the display fetch", `${mapld.length} pulses`)
  const firstTile = H.backEnd + 1
  const leadDots = (firstTile - mapld[0]!.slot) * DOTS_PER_SLOT - mapld[0]!.ph
  check(leadDots >= DOTS_PER_SLOT,
    `the map byte for a cell lands ${leadDots} dots before that cell's first ` +
    "tile fetch - a full slot of slack, not the 4.4 ns a same-slot fetch leaves",
    `${leadDots}`)
}

/* -- 3. 6.4.2's access arithmetic ---------------------------------------- */
{
  /* Per cell: two display fetches of four bytes, plus one map byte. */
  const mapAccesses = line.filter((d) => d.ph === 0 && d.v.get("MAPREQ") === 1).length
  const displaySlots = line.filter((d) => d.ph === 0 && d.v.get("TFETCH") === 1).length
  const accessesPerCell = (displaySlots * 4 + mapAccesses) / MAP_COLS
  check(accessesPerCell === 9,
    "6.4.2's \"9 accesses per 8 dots\": 8 tile bytes as two four-chip display " +
    "fetches, plus one map byte", `${accessesPerCell}`)
  const perChipPerCell = (displaySlots * 4 / 4 + mapAccesses / 4) / MAP_COLS
  check(perChipPerCell === 2.25,
    "and \"2.25 accesses per chip per cell\" against the bitmap's 2.0, because " +
    "the map byte lands on one chip in four", `${perChipPerCell}`)
}

/* -- 4. exactly one source drives the card's internal address bus -------- */
{
  /* SPNGRANT is arbDesign's, not the cadence's, so it is modelled rather than
   * forced: the span writer can only be granted what it was allowed to request,
   * and SPNREQG is the gate. Forcing SPNGRANT=1 alongside MAPREQ=1 - which the
   * first version of this check did - asserts about a state the gate makes
   * unreachable, and it fails for that reason and not a real one. */
  let bad: string | null = null
  for (const d of line) {
    for (const spn of [0, 1]) {
      const gated = dotWorld(d.slot, d.ph, { SPNREQ: spn }).get("SPNREQG")!
      const v = dotWorld(d.slot, d.ph, { SPNREQ: spn, SPNGRANT: gated })
      const drivers = ["MAPSEL", "TILESEL", "LINEAR"].filter((n) => v.get(n) === 1)
      const n = drivers.length + gated
      if (n > 1) {
        bad = `slot ${d.slot} dot ${d.ph} SPNREQ=${spn}: ${drivers.join("+")}` +
          `${gated ? "+SPNGRANT" : ""}`
        break
      }
    }
    if (bad) break
  }
  check(bad === null,
    "never two sources on the card's one internal address bus - 5.2.1's " +
    "SRCSEL muxes each CHIP's source, so the CPU is independent but the map " +
    "fetch, the span writer and the display fetch are not", bad ?? "")

  /* And the span writer is what stands down for it. */
  const contended = line.filter((d) => d.v.get("MAPREQ") === 1 && d.ph < 2)
  const ok = contended.every((d) =>
    dotWorld(d.slot, d.ph, { SPNREQ: 1 }).get("SPNREQG") === 0)
  check(ok, "SPNREQ is gated off for the whole of a map slot - one gate, and " +
    "arbDesign is left untouched and still checkable as a GAL22V10")
  const free = line.filter((d) => d.v.get("MAPREQ") === 0 && d.v.get("MFETCH") === 1)
  check(free.every((d) => dotWorld(d.slot, d.ph, { SPNREQ: 1 }).get("SPNREQG") === 1),
    "⚠ and only for a map slot - which is one slot in two, so cell mode costs " +
    "the span writer HALF its spare slots, not 6.4.2's \"roughly an eighth\" " +
    "(that figure is per-chip load, and it is separately right)")
}

/* -- 5. the CPU's chip, and when it has to wait -------------------------- */
{
  let bad: string | null = null
  for (let mapChip = 0; mapChip < 4 && !bad; mapChip++) {
    for (let cpuChip = 0; cpuChip < 4; cpuChip++) {
      const extra = {
        MAPA0: mapChip & 1, MAPA1: (mapChip >> 1) & 1,
        A0: cpuChip & 1, A1: (cpuChip >> 1) & 1,
        ACPU0: cpuChip === 0 ? 1 : 0, ACPU1: cpuChip === 1 ? 1 : 0,
        ACPU2: cpuChip === 2 ? 1 : 0, ACPU3: cpuChip === 3 ? 1 : 0,
      }
      /* a dot inside a map slot's spare window */
      const v = dotWorld(H.backEnd - 1, 0, extra)
      const granted = [0, 1, 2, 3].filter((n) => v.get(`GCPU${n}`) === 1)
      const held = v.get("MAPHOLD") === 1
      if (mapChip === cpuChip) {
        if (granted.length !== 0 || !held) {
          bad = `map=${mapChip} cpu=${cpuChip}: granted ${granted} held ${held}`
        }
      } else if (granted.length !== 1 || granted[0] !== cpuChip || held) {
        bad = `map=${mapChip} cpu=${cpuChip}: granted ${granted} held ${held}`
      }
      if (bad) break
    }
  }
  check(bad === null,
    "the map withdraws the CPU's grant on its own chip and only its own chip, " +
    "and raises MAPHOLD exactly there - 2.2's \"video before CPU\"", bad ?? "")

  /* /WAIT: 7.4's span backstop keeps its !RW; a map hold defeats it. */
  const at = (o: Record<string, number>) => dotWorld(H.backEnd - 1, 0, o)
  const same = { MAPA0: 0, MAPA1: 0, A0: 0, A1: 0 }
  const diff = { MAPA0: 1, MAPA1: 0, A0: 0, A1: 0 }
  const waits = (o: Record<string, number>) => {
    const v = at(o)
    return v.get("WAITSRC") === 1 && v.get("WAITRW") === 0
  }
  check(waits({ ...same, RW: 1, SPANBUSY: 0 }),
    "a READ whose chip the map has taken waits - it would otherwise return the " +
    "wrong byte, which 7.4's write-only rule never had to cover")
  check(waits({ ...same, RW: 0, SPANBUSY: 0 }), "and so does a write")
  check(!waits({ ...diff, RW: 1, SPANBUSY: 0 }),
    "a read that does not collide does not wait - 7.4's sprite save-behind and " +
    "read-modify-write pixels stay off the backstop")
  check(waits({ ...diff, RW: 0, SPANBUSY: 1 }),
    "and 7.4's span backstop is unchanged: SPANBUSY still waits on a write")
  check(!waits({ ...diff, RW: 1, SPANBUSY: 1 }),
    "and still does not on a read")
}

/* -- 6. a whole FRAME: ROWADV, VLOAD and 6.2's line doubling -------------- *
 *
 * The row counter is what 8's vertical scroll actually moves, and until
 * 2026-09-08 nothing drove it: ROWADV and VLOAD were declared as vadr inputs
 * and produced by nobody, so VSCROLL was never loaded and the row never
 * stepped - in EITHER mode. This runs a frame in each of 12's four VMODE codes
 * and at several scroll positions, and asserts which row each displayed line
 * actually shows.
 */
{
  /* VLOAD is not a signal: vadr's load input is renamed to VBLANK on merge,
   * because "asserted through vertical blanking" is VBLANK's definition. Assert
   * the rename is really there rather than trusting the comment. */
  const rowIn = vadrDesign.inputs.map((i) => i.name)
  check(rowIn.includes("VLOAD"),
    "vadr still declares VLOAD - the rename is at merge, so the standalone " +
    "design and its GAL22V10 checks are untouched", rowIn.join(","))
  const merged = new Set(vaddrCpld.cells.map((c) => c.name))
  check(!merged.has("VLOAD"),
    "and nothing produces a second copy of it - VBLANK is the one signal, which " +
    "is what keeps this off a part at 64 of 64 I/O")

  const V = { 0: V449, 1: V525 } as const

  /* ROWADV depends on the line only through VBLANK, V0 and VMODE1, so count its
   * pulses over ONE line for each of the eight combinations rather than
   * evaluating 800 dots x 525 lines x 4 modes x 5 scroll positions. The count is
   * what matters and counting it per dot is what catches a missing SLOTTICK
   * gate - a whole-slot level scores 4 here, not 1. */
  const stepCache = new Map<string, number>()
  const steps = (vblank: number, v0: number, vmode1: number) => {
    const key = `${vblank}${v0}${vmode1}`
    const hit = stepCache.get(key)
    if (hit !== undefined) return hit
    let n = 0
    for (let slot = 0; slot < SLOTS_PER_LINE; slot++) {
      for (let ph = 0; ph < DOTS_PER_SLOT; ph++) {
        if (dotWorld(slot, ph, { VBLANK: vblank, V0: v0, VMODE1: vmode1 })
          .get("ROWADV") === 1) n++
      }
    }
    stepCache.set(key, n)
    return n
  }
  check(steps(0, 0, 1) === 1 && steps(0, 1, 1) === 1,
    "ROWADV is ONE clock edge per displayed line in the undoubled modes - the " +
    "SLOTTICK gate, without which a whole-slot level would step the row four " +
    "times a line and scan the picture at quarter height",
    `${steps(0, 0, 1)},${steps(0, 1, 1)}`)
  check(steps(0, 0, 0) === 1 && steps(0, 1, 0) === 0,
    "and in a doubled mode it fires on even V only - 6.2's \"withholds every " +
    "second one\"", `${steps(0, 0, 0)},${steps(0, 1, 0)}`)
  check(steps(1, 0, 1) === 0 && steps(1, 1, 0) === 0,
    "and never during vertical blanking, where VBLANK is holding the counter " +
    "at VSCROLL instead")

  /* One frame, one mode, one scroll offset: which row does each displayed line
   * put on screen? */
  const frame = (vmode1: number, vmode0: 0 | 1, vscroll: number) => {
    const fam = V[vmode0]
    let row = 0
    const shown: number[] = []
    for (let v = 0; v < fam.lines; v++) {
      const vblank = v >= fam.backEnd + 1 && v <= fam.activeEnd ? 0 : 1
      if (vblank) row = vscroll                     // VLOAD = VBLANK, a load
      else shown.push(row)                          // this line displays `row`
      row = (row + steps(vblank, v & 1, vmode1)) % 512
    }
    return shown
  }

  /* 12's four codes: VMODE1 = 0 is the doubled pair (640x200, 640x240) and
   * VMODE1 = 1 is one row per line (640x400, 640x480). */
  const MODES = [
    { vmode1: 0, vmode0: 0 as const, name: "640x200", rows: 200, dbl: 2 },
    { vmode1: 0, vmode0: 1 as const, name: "640x240", rows: 240, dbl: 2 },
    { vmode1: 1, vmode0: 0 as const, name: "640x400", rows: 400, dbl: 1 },
    { vmode1: 1, vmode0: 1 as const, name: "640x480", rows: 480, dbl: 1 },
  ]
  let bad: string | null = null
  for (const m of MODES) {
    for (const vscroll of [0, 1, 8, 200, 509]) {
      const shown = frame(m.vmode1, m.vmode0, vscroll)
      const want = [...Array(shown.length).keys()]
        .map((i) => (vscroll + Math.floor(i / m.dbl)) % 512)
      const i = shown.findIndex((r, k) => r !== want[k])
      if (i >= 0) {
        bad = `${m.name} VSCROLL=${vscroll}: display line ${i} shows row ` +
          `${shown[i]}, wanted ${want[i]}`
        break
      }
      if (shown.length !== m.rows * m.dbl) {
        bad = `${m.name}: ${shown.length} displayed lines, wanted ${m.rows * m.dbl}`
        break
      }
    }
    if (bad) break
  }
  check(bad === null,
    "every displayed line of every VMODE shows the row VSCROLL puts there, at " +
    "five scroll positions including the 512-row wrap - so vertical scroll " +
    "works, and it works in bitmap and cell mode alike", bad ?? "")

  /* 6.2's doubling, called out on its own because getting it wrong doubles or
   * halves the picture rather than failing visibly. */
  {
    const rows = (m: typeof MODES[number]) =>
      new Set(frame(m.vmode1, m.vmode0, 0)).size
    const ok = MODES.every((m) => rows(m) === m.rows)
    check(ok, "and each mode visits exactly its own number of rows - 200, 240, " +
      "400, 480 - which is 6.2's line doubling being in ROWADV and nowhere else",
      MODES.map((m) => `${m.name}:${rows(m)}`).join(" "))
    const two = frame(0, 0, 0)
    check(two[0] === two[1] && two[1] !== two[2],
      "a doubled mode shows each row on exactly two consecutive lines, and the " +
      "pair starts on display line 0 - the parity that works in both families " +
      "because 37 and 35 are both odd (sync.timing.ts)",
      `${two.slice(0, 4)}`)
  }

  /* The row must not move under the fetch it is feeding. */
  {
    const moves = line.filter((d) =>
      dotWorld(d.slot, d.ph, { VBLANK: 0, V0: 0, VMODE1: 1 }).get("ROWADV") === 1)
    const tf = line.filter((d) => d.v.get("TFETCH") === 1).map((d) => d.slot)
    const mf = line.filter((d) => d.v.get("MFETCH") === 1).map((d) => d.slot)
    const clash = moves.filter((d) => tf.includes(d.slot) || mf.includes(d.slot))
    check(clash.length === 0 && moves.length === 1,
      `ROWADV is one dot per line and it is clear of both fetch windows - slot ` +
      `${moves[0]?.slot} against TFETCH ending at ${Math.max(...tf)}, so the row ` +
      "counter is stable across every map and tile address of a line",
      `${moves.length} pulses`)
  }
}

console.log(failures === 0
  ? "\n6.4's cadence runs a line: 80 cells, 80 map bytes, one bus, one waiter"
  : `\n${failures} FAILED`)
if (failures) process.exit(1)
