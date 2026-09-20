/* storage - how many programmable parts the card needs, for BOTH shapes of
 * it, by counting PINS and searching every partition.
 *   bun run gal/storage/census.ts
 *
 * ⛔ WHY THIS EXISTS BEFORE ANY TERM LIST DOES. `sdcard.md` §8 row 13 budgets
 * the card's logic as **two GAL22V10s**, and §8.1 derives that from a
 * MACROCELL estimate: "the decode from /IOSEL, the burst trigger, SDCTRL and
 * SDSTAT were already roughly ten macrocells of a GAL22V10's ten ... that is
 * not a fit; it is a second part". The estimate is about equations. ⚠ **A
 * GAL22V10's binding constraint here is not equations, it is PINS** - 22
 * usable of 24 - and nothing in the document counted them.
 *
 * Whether the EQUATIONS then fit is `assemble()`'s answer and is a separate
 * question. A part that is over on pins never reaches it.
 *
 * ⭐ AND IT SEARCHES THE PARTITION RATHER THAN ASSUMING ONE. The first
 * version of this file split the card into decode / registers / engine
 * because that is how §8.1 describes it, found the port card needed three
 * parts, and was WRONG: a signal that crosses a part boundary costs a pin at
 * each end, so WHERE the boundary goes changes the answer. Moving the SDSTAT
 * drive next to the engine that produces BUSY - rather than next to the
 * SDCTRL register it shares a data bus with - deletes four crossings and
 * takes the port card from three parts to two. The units below are therefore
 * the smallest pieces the card divides into, and every way of grouping them
 * is tried.
 *
 * ---------------------------------------------------------------------------
 * ⭐ TWO SHAPES, AND THE DIFFERENCE IS ONE DECISION.
 *
 *   BUFFERED  §11.1, taken 2026-09-08 - a 512-byte block buffer mapped as
 *             memory at `A20 = 1`, filled by an engine on the card. Reads
 *             become non-side-effecting, so §4's `TFM` hazard is gone from
 *             the read path: 681 KiB/s unchunked.
 *   PORT      NormalLuser's BE6502 interface as §3.1 describes it and no
 *             more: the read strobe triggers the next burst and the block
 *             comes through the port. §4.4's chunk-and-mask discipline makes
 *             it safe - 32-byte chunks, 537 KiB/s, 49 us of added interrupt
 *             latency - which is ALREADY what §9.2's write path does.
 * ------------------------------------------------------------------------- */

/** the smallest pieces the card's logic divides into */
type Unit = "dec" | "ctrl" | "stat" | "eng" | "buf" | "fill"
const BUFFER_UNITS: Unit[] = ["buf", "fill"]

interface Net {
  name: string
  why: string
  /** the unit whose equations drive it, or "ext" for a pin coming from the
   *  backplane, the socket or a discrete part */
  from: Unit | "ext"
  /** units that must see it */
  to: Unit[]
  only?: "buffer"
}

const NETS: Net[] = [
  /* -- from the backplane (machine.md §2) ---------------------------------- */
  { name: "CLK25", why: "the master - pin 1 of any part with a register", from: "ext", to: ["dec", "ctrl", "buf"] },
  { name: "IOSEL", why: "$FF00-$FF7F window strobe", from: "ext", to: ["dec"] },
  { name: "A6", why: "§6.1 - the decode is A0-A6, SEVEN bits: a card matching", from: "ext", to: ["dec"] },
  { name: "A5", why: "only A0-A5 answers at $FF58 AND at $FF18", from: "ext", to: ["dec"] },
  { name: "A4", why: "$FF58 = 0101_1000", from: "ext", to: ["dec"] },
  { name: "A3", why: "", from: "ext", to: ["dec"] },
  { name: "A2", why: "", from: "ext", to: ["dec"] },
  { name: "A1", why: "which of the four registers", from: "ext", to: ["dec"] },
  { name: "A0", why: "", from: "ext", to: ["dec"] },
  { name: "RW", why: "read or write", from: "ext", to: ["dec"] },
  { name: "E", why: "a register write is strobed on E-high", from: "ext", to: ["dec", "buf"] },
  { name: "RESET", why: "§6.4 - SDCTRL to $00, and no burst in flight", from: "ext", to: ["ctrl", "eng"] },

  /* -- the buffer's region decode (§6.1, machine.md §5 item 7) ------------- */
  { name: "Q", why: "⭐ !E & !Q IS the engine's slot - machine.md §5 item 7", from: "ext", to: ["buf"], only: "buffer" },
  { name: "IOPAGE", why: "a physical decode is qualified on /IOPAGE HIGH", from: "ext", to: ["buf"], only: "buffer" },
  { name: "A20", why: "card buffers live at A20 = 1", from: "ext", to: ["buf"], only: "buffer" },
  { name: "A19", why: "which of sixteen 64 KB regions, against", from: "ext", to: ["buf"], only: "buffer" },
  { name: "A18", why: "a four-position jumper - §6.1", from: "ext", to: ["buf"], only: "buffer" },
  { name: "A17", why: "", from: "ext", to: ["buf"], only: "buffer" },
  { name: "A16", why: "", from: "ext", to: ["buf"], only: "buffer" },
  { name: "J1", why: "the jumper", from: "ext", to: ["buf"], only: "buffer" },
  { name: "J0", why: "", from: "ext", to: ["buf"], only: "buffer" },

  /* -- the data bus: SDCTRL reads it, SDSTAT drives it --------------------- */
  { name: "D0", why: "SDCTRL b0 /CS in; SDSTAT b0 BUSY out", from: "stat", to: ["ctrl"] },
  { name: "D1", why: "SDCTRL b1 rate in; SDSTAT b1 CD out", from: "stat", to: ["ctrl"] },
  { name: "D2", why: "SDSTAT b2 WP out (SDCTRL b2 FILL in, buffered)", from: "stat", to: ["ctrl"] },
  { name: "D7", why: "SDCTRL b7 soft reset in", from: "ext", to: ["ctrl"] },
  { name: "D3", why: "SDCTRL b3 BUF0 in; SDSTAT b3 DONE out", from: "stat", to: ["ctrl"], only: "buffer" },
  { name: "D4", why: "SDCTRL b4 BUF1 in", from: "ext", to: ["ctrl"], only: "buffer" },

  /* -- the socket and the discrete parts ----------------------------------- */
  { name: "CD", why: "card-detect switch", from: "ext", to: ["stat"] },
  { name: "WP", why: "write-protect switch", from: "ext", to: ["stat"] },
  { name: "DIV2", why: "'393 tap, 12.588 MHz - §3.3", from: "ext", to: ["eng"] },
  { name: "DIV64", why: "'393 tap, 393 kHz init clock", from: "ext", to: ["eng"] },
  { name: "RCO", why: "'163 terminal count - the burst's eighth clock", from: "ext", to: ["eng"] },
  { name: "CNT512", why: "'4040 Q9 - the fill's 512th byte", from: "ext", to: ["fill"], only: "buffer" },

  /* -- what the logic drives ------------------------------------------------ */
  { name: "CTRLW", why: "the SDCTRL write strobe", from: "dec", to: ["ctrl"] },
  { name: "RDST", why: "the SDSTAT read - the status drive's output enable", from: "dec", to: ["stat"] },
  { name: "DATSTB", why: "an SDDATA access - the burst trigger, §6.5 qualifies it", from: "dec", to: ["eng"] },
  { name: "MOSICK", why: "the '574 MOSI hold register's clock", from: "dec", to: [] },
  { name: "OE595", why: "the '595's three-state output enable", from: "dec", to: [] },
  { name: "CS", why: "SDCTRL b0 -> the 'LVC125 -> the card's /CS", from: "ctrl", to: [] },
  { name: "FAST", why: "SDCTRL b1 - selects the DIV2 tap", from: "ctrl", to: ["eng"] },
  { name: "SPICLK", why: "the muxed tap: the '163's clock, and the engine's own pin 1", from: "eng", to: ["eng"] },
  { name: "SCK", why: "the gated clock the card sees - exactly eight per burst", from: "eng", to: [] },
  { name: "RCLK", why: "the '595's storage clock (and the '4040's, buffered)", from: "eng", to: ["fill"] },
  { name: "SHLD", why: "the '165's parallel load, from the hold register", from: "eng", to: [] },
  { name: "BUSY", why: "§6.5's lockout - and it is the '163's /LOAD, wired direct", from: "eng", to: ["stat"] },

  { name: "FILL", why: "SDCTRL b2 - the engine; also the '4040's MR", from: "ctrl", to: ["buf", "fill"], only: "buffer" },
  { name: "BUF0", why: "SDCTRL b3 - which 512-byte buffer, to the '157s", from: "ctrl", to: [], only: "buffer" },
  { name: "BUF1", why: "SDCTRL b4", from: "ctrl", to: [], only: "buffer" },
  { name: "DONE", why: "§6.3 b3 - a FILL block finished", from: "fill", to: ["stat"], only: "buffer" },
  { name: "FILLEND", why: "clears FILL at the 512th byte", from: "fill", to: ["ctrl"], only: "buffer" },
  { name: "BUFOE", why: "the '245's /OE - registers and the buffer window", from: "buf", to: [], only: "buffer" },
  { name: "RAMCE", why: "the 6116's /CE ⚠ /OE is tied LOW: an SRAM with /WE low", from: "buf", to: [], only: "buffer" },
  { name: "RAMWE", why: "has its outputs off whatever /OE says, so /OE costs 0", from: "buf", to: [], only: "buffer" },
  { name: "MUXSEL", why: "the three '157s - the engine's counter or the backplane", from: "buf", to: [], only: "buffer" },
]

const GAL = 22  /* pins usable for signals on a GAL22V10: 1, 2-11, 13, 14-23 */

/** every way of partitioning a set - the search this file exists to do */
const partitions = <T,>(xs: T[]): T[][][] => {
  if (xs.length === 0) return [[]]
  const [first, ...rest] = xs
  return partitions(rest).flatMap((p) => [
    [[first], ...p],
    ...p.map((_, i) => p.map((g, j) => (i === j ? [first, ...g] : g))),
  ])
}

/** the pins one part needs: every net it drives, and every net it reads */
const pinsOf = (part: Unit[], nets: Net[]) => {
  const has = (u: Unit | "ext") => u !== "ext" && part.includes(u)
  return nets.filter((n) => has(n.from) || n.to.some(has)).map((n) => n.name)
}

const score = (buffered: boolean) => {
  const nets = NETS.filter((n) => buffered || n.only !== "buffer")
  const units = (["dec", "ctrl", "stat", "eng", ...(buffered ? BUFFER_UNITS : [])] as Unit[])
  let best: { parts: Unit[][]; pins: string[][] } | null = null
  for (const p of partitions(units)) {
    const pins = p.map((part) => pinsOf(part, nets))
    if (pins.some((x) => x.length > GAL)) continue
    if (!best || p.length < best.parts.length) best = { parts: p, pins }
  }
  return { nets, units, best, tried: partitions(units).length }
}

const shapes = { BUFFERED: score(true), PORT: score(false) }

for (const [name, s] of Object.entries(shapes)) {
  console.log(`\n      ${name} - ${s.nets.length} nets, ${s.tried} partitions of ${s.units.length} units tried\n`)
  if (!s.best) {
    console.log(`      ⛔ NO partition puts every part inside a GAL22V10's ${GAL} pins.`)
    for (const u of s.units) {
      const n = pinsOf([u], s.nets).length
      console.log(`         ${u} alone is ${n} pins${n > GAL ? `  ⛔ ${n - GAL} OVER on its own` : ""}`)
    }
    continue
  }
  s.best.parts.forEach((part, i) => {
    const pins = s.best!.pins[i]
    console.log(`      ${part.join("+").padEnd(10)} ${String(pins.length).padStart(2)} pins (${GAL - pins.length} spare)`)
    console.log(`            ${pins.join(" ")}`)
  })
  console.log(`\n      -> ${s.best.parts.length} GAL22V10s, minimum over every partition`)
}

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

console.log("")
const buf = shapes.BUFFERED, port = shapes.PORT
check(buf.best?.parts.length === 4,
  "⛔ the BUFFERED card needs FOUR GAL22V10s, not the two §8 row 13 budgets",
  `${buf.best?.parts.length} parts, best of ${buf.tried} partitions`)
check(pinsOf(["buf"], buf.nets).length === 16,
  "   and what breaks it is the region decode - nine of its pins are address and jumper",
  `${pinsOf(["buf"], buf.nets).length} pins for that unit alone`)
check(port.best?.parts.length === 2,
  "⭐ the PORT card - NormalLuser's, §3.1 and nothing more - fits TWO",
  `${port.best?.parts.length}`)

/* §8's table, with the logic replaced by what the search just found. */
const BOTH = ["74HCT595", "74HC165", "74HC574", "74HC163", "74HC393", "74LVC125"]
const BUFONLY = ["6116", "74HC4040", "74HC157", "74HC157", "74HC157", "74HCT245"]
const icsPort = BOTH.length + (port.best?.parts.length ?? 0)
const icsBuf = BOTH.length + BUFONLY.length + (buf.best?.parts.length ?? 0)
console.log("")
check(icsPort === 8, "the port card is 8 ICs plus the LDO and the socket", `${icsPort}`)
check(icsBuf === 16, "⛔ and the buffered card is 16, where §8 totals 14", `${icsBuf}`)
console.log(`      (§8.1's one-ATF1508AS version of the buffered card stays 8, and is`)
console.log(`      the only thing that makes the buffer affordable in packages.)`)

console.log(`\n      ⭐ 8 ICs and two fuse-verifiable GALs at 537 KiB/s, against 8 ICs`)
console.log(`      and one ATF1508AS at 681. The 21 % is what the buffer buys, and`)
console.log(`      §11.6 can have it back for nothing: the hazard the buffer exists`)
console.log(`      to dodge is a property of OUR CPU firmware, not of handed-down`)
console.log(`      silicon. ⚠ §12 step 1 measures the real part before that is taken.`)
console.log(`\n${failures === 0 ? "0 failed" : `${failures} FAILED`}`)
process.exit(failures === 0 ? 0 : 1)
