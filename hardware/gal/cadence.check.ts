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
import { vaddrCpld, vramWriteStrobe } from "./video.cpld"
import { decodeCells } from "./regfile"
import { MAP_COLS } from "./tile.model"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

/* -- a sum-of-products evaluator over a named world ---------------------- */
/* ⚠ plus the port's select - VRAMSEL, and VPORT, which is VRAMSEL or +$15
 * VDATA (19 item 47) - so section 5's /WAIT is evaluated from the design's
 * cells and not restated here. The strobes beside VPORT are registered or read
 * E, and are not taken. */
const cells = new Map([...tileCadence, ...decodeCells,
  ...vramWriteStrobe.filter((c) => c.name === "VPORT")].map((c) => [c.name, c.terms]))
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
    /* 5.2.2's spare half - dots 0 and 1. seqph forms it as !PH1. */
    ["SPAREWIN", ph < 2 ? 1 : 0],
    /* A displayed line in the middle of the frame: not blanked, V even so the
     * doubled modes advance. The frame section below sweeps V properly. */
    ["VBLANK", 0], ["V0", 0], ["VMODE1", 1],
    ["TILEMODE", 1], ["SPNREQ", 0], ["SPNGRANT", 0],
    ["SPANBUSY", 0], ["RW", 1], ["A0", 0], ["A1", 0],
    /* ⛔ LRUN WAS MISSING AND THIS FILE THREW RATHER THAN FAILED, from the
     * day 10.3's engine became SPNREQ's second requester until 2026-09-09.
     * It threw where nobody looked: check:cadence has a script of its own and
     * was NOT in `npm run check`, so a whole-line cadence model sat broken
     * while 400 other claims passed. It is in the suite now. No list is
     * running in this world - the engine's slot accounting is vspan_tb's. */
    ["LRUN", 0],
    ["MAPA0", 0], ["MAPA1", 0],
    /* graphics.md 11's read prefetch: the read latch is full, so nothing asks. */
    ["RDVALID", 1],
    /* the CPU's access: none of the VRAM port's two addresses (19 item 47) */
    ["A19", 0], ["A20", 0], ["IOPAGE", 0], ["VDSEL", 0], ["E", 1],
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
  /* 8.2: the window MOVED one slot earlier, it did not lengthen - 160 slots
   * either way, because a cell is two of them and 161 misaligns every cell. */
  check(tf0 === H.backEnd && tf1 === H.activeEnd - 1,
    `TFETCH is the active window shifted one slot early, ${H.backEnd}..${H.activeEnd - 1} - 8.2's fetch lead`, `${tf0}..${tf1}`)
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
  const firstTile = H.backEnd
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

  /* And the span writer is what stands down for it.
   *
   * ⛔ DRIVE SPANBUSY, NOT SPNREQ. SPNREQ is a CELL here (`SPANBUSY & SPAREWIN
   * # LRUN & SPAREWIN`), so seeding it into the world is overwritten on the
   * first recompute pass - the request was 0 in both branches and "gated off"
   * held vacuously. design-review2.md 10's rule, one more time: an input a
   * check cannot actually drive is an input it cannot see a defect in. The
   * span writer's request only exists in the spare half, so both filters carry
   * ph < 2 as well. */
  const contended = line.filter((d) => d.v.get("MAPREQ") === 1 && d.ph < 2)
  const ok = contended.every((d) =>
    dotWorld(d.slot, d.ph, { SPANBUSY: 1 }).get("SPNREQG") === 0)
  check(ok && contended.length > 0,
    "SPNREQ is gated off for the whole of a map slot - one gate, and " +
    "arbDesign is left untouched and still checkable as a GAL22V10")
  const free = line.filter((d) =>
    d.v.get("MAPREQ") === 0 && d.v.get("MFETCH") === 1 && d.ph < 2)
  check(free.length > 0 && free.every((d) => dotWorld(d.slot, d.ph, { SPANBUSY: 1 }).get("SPNREQG") === 1),
    "⚠ and only for a map slot - which is one slot in two, so cell mode costs " +
    "the span writer HALF its spare slots, not 6.4.2's \"roughly an eighth\" " +
    "(that figure is per-chip load, and it is separately right)")
}

/* -- 5. the CPU takes no chip, and when it has to wait --------------------- *
 *
 * ⛔ THIS SECTION ASSERTED THE OPPOSITE UNTIL 2026-09-11: "the map withdraws
 * the CPU's grant on its own chip, and raises MAPHOLD exactly there", and "a
 * read that does not collide does not wait". Both were about a flat CPU read
 * that reserved the chip its physical address named - and no part has that
 * address. Every CPU VRAM access is at WPTR: a write retires there, a read is
 * prefetched from there (graphics.md 11), so the CPU collides with nothing and
 * the only reasons to wait are the span in flight and the prefetch. */
{
  const at = (o: Record<string, number>) => dotWorld(H.backEnd - 2, 0, o)
  /* arbDesign's oe, as merged: WAITSRC & VPORT & !CPUIDLE & E & !CPUIDLE, with
   * VPORT = VRAMSEL # VDSEL (19 item 47). The access is the VRAM window unless
   * a caller says otherwise. */
  const WINDOW = { A19: 1, A20: 0, IOPAGE: 0, VDSEL: 0, E: 1 }
  const waitsAt = (o: Record<string, number>) => {
    const v = at({ ...WINDOW, ...o })
    return v.get("WAITSRC") === 1 && v.get("VPORT") === 1 && v.get("E") === 1
      && v.get("CPUIDLE") === 0
  }
  const waits = waitsAt
  check(waits({ RW: 0, SPANBUSY: 1 }), "7.4's span backstop: a write waits while a span is in flight")
  check(!waits({ RW: 0, SPANBUSY: 0, RDVALID: 0 }),
    "and a write does not wait for the read prefetch - it has nothing to read")
  check(waits({ RW: 1, SPANBUSY: 1 }),
    "⭐ a READ waits on a span in flight too - the span's retires move WPTR, which is where the read is")
  check(waits({ RW: 1, SPANBUSY: 0, RDVALID: 0 }),
    "⭐ and on a prefetch that has not filled the read latch yet")
  check(!waits({ RW: 1, SPANBUSY: 0, RDVALID: 1 }),
    "a read with the latch full and no span does not wait")
  /* ⭐ 19 item 47: +$15 VDATA is the same port in the I/O page */
  const VDATA = { A19: 0, IOPAGE: 1, VDSEL: 1 }
  check(waits({ ...VDATA, RW: 0, SPANBUSY: 1 }) && waits({ ...VDATA, RW: 1, SPANBUSY: 1 })
    && waits({ ...VDATA, RW: 1, SPANBUSY: 0, RDVALID: 0 }),
    "⭐ VDATA at +$15 waits exactly as the window does - on a span for either direction, and on the prefetch for a read - though it is in the I/O page")
  check(!waits({ A19: 0, IOPAGE: 1, VDSEL: 0, RW: 0, SPANBUSY: 1 })
    && !waits({ A19: 1, A20: 0, IOPAGE: 1, VDSEL: 0, RW: 1, SPANBUSY: 1 }),
    "and no other I/O cycle waits - not even one whose translated A19 happens to point at VRAM (6.3.2)")
  /* the map slot, which used to hold the CPU */
  const mapDot = line.find((d) => d.v.get("MAPREQ") === 1 && d.ph < 2)!
  check(!dotWorld(mapDot.slot, mapDot.ph, { RW: 1 }).get("WAITSRC") && !(at({}).get("MAPHOLD")),
    "and a map slot makes nobody wait - MAPHOLD is gone with the chip it protected")
  /* the prefetch's request and grant */
  const spare = line.find((d) => d.v.get("MAPREQ") === 0 && d.ph < 2)!
  check(dotWorld(spare.slot, spare.ph, { RDVALID: 0 }).get("SPNREQ") === 1,
    "an empty read latch asks for the spare access, in the spare half")
  check(dotWorld(mapDot.slot, mapDot.ph, { RDVALID: 0 }).get("SPNREQG") === 0,
    "and yields it to the map, like every other requester")
  check(dotWorld(spare.slot, 1, { RDVALID: 0, SPNGRANT: 1 }).get("SGRANT") === 1
    && dotWorld(spare.slot, 1, { RDVALID: 0, SPNGRANT: 1, SPANBUSY: 1 }).get("SGRANT") === 0,
    "SGRANT is the granted dot, withheld from everyone but the span writer while a span runs")
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
