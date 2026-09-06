/* The MMU GAL's equations, as arithmetic.
 *
 * mmu.pld is the deliverable and mmu.v is what Verilator will drive once it
 * is installed. Neither runs today, and the equations are the part of this
 * design most easily got wrong - so they are restated here in the one
 * language this repository can already execute, and the claims
 * graphics.md 6.3.1 makes about them are checked exhaustively.
 *
 * "Exhaustively" is the whole 16-bit address space x 4 quadrature phases x
 * R/W - 524,288 evaluations, which is nothing. There is no sampling here.
 *
 * Keep in step with mmu.pld by hand. Seven equations.
 */

/* -- the four quadrature phases, in the order a cycle visits them -------- */
/* Q leads E by 90 degrees: E-fall, Q-rise, E-rise, Q-fall, E-fall. */
const PHASES = [
  { name: "ph0 E0 Q0 (address becomes valid)", e: 0, q: 0 },
  { name: "ph1 E0 Q1 (Q has risen)", e: 0, q: 1 },
  { name: "ph2 E1 Q1 (E has risen)", e: 1, q: 1 },
  { name: "ph3 E1 Q0 (Q has fallen)", e: 1, q: 0 },
] as const

interface Out {
  iopage: boolean   // asserted (the pin is inverted)
  muxsel: boolean
  isooe: boolean    // asserted
  mapwe: boolean    // asserted
  mapoe: boolean    // asserted
  ctrlcp: boolean   // the PIN level, not the term - high is the idle state
}

/* -- the equations ------------------------------------------------------ */
const mmu = (la: number, e: number, q: number, rw: number): Out => {
  const bit = (n: number) => (la >> n) & 1
  const iopage = (la & 0xff00) === 0xff00
  const mmusel = iopage && !!bit(7) && !bit(6) && !!bit(5)
  const blksel = mmusel && !bit(4)
  const ctlsel = mmusel && !!bit(4)
  return {
    iopage,
    muxsel: blksel,
    isooe: blksel && !!e,
    mapwe: blksel && !rw && !!e && !q,
    mapoe: !iopage || (blksel && !!rw && !!e),
    ctrlcp: !(ctlsel && !rw && !!e),
  }
}

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

const ADDRS = Array.from({ length: 0x10000 }, (_, i) => i)
const every = (pred: (la: number, ph: typeof PHASES[number], rw: number) => boolean) => {
  for (const la of ADDRS) for (const ph of PHASES) for (const rw of [0, 1]) {
    if (!pred(la, ph, rw)) return `$${la.toString(16).toUpperCase().padStart(4, "0")} ${ph.name} R/W=${rw}`
  }
  return null
}
const claim = (text: string, pred: Parameters<typeof every>[0]) =>
  check(every(pred) === null, text, every(pred) ?? "")

/* -- decode, machine.md 2 and 3 ----------------------------------------- */
claim("/IOPAGE is asserted for $FF00-$FFFF and nowhere else",
  (la, p, rw) => mmu(la, p.e, p.q, rw).iopage === (la >= 0xff00))

claim("the block window is $FFA0-$FFAF and nowhere else",
  (la, p, rw) => mmu(la, p.e, p.q, rw).muxsel === (la >= 0xffa0 && la <= 0xffaf))

claim("no map write outside $FFA0-$FFAF",
  (la, p, rw) => !mmu(la, p.e, p.q, rw).mapwe || (la >= 0xffa0 && la <= 0xffaf))

claim("no map write on a read cycle",
  (la, p, rw) => !mmu(la, p.e, p.q, rw).mapwe || rw === 0)

claim("the control latch never clocks outside $FFB0-$FFBF",
  (la, p, rw) => mmu(la, p.e, p.q, rw).ctrlcp || (la >= 0xffb0 && la <= 0xffbf))

/* -- the two orderings graphics.md 6.3.1 calls load-bearing -------------- */
/* The '245's direction is R/W - a wire, not a macrocell (gal/README.md), and
 * that is what makes this claim direction-aware rather than absolute. The
 * buffer drives the SRAM's I/O pins only on a write; on a read its A side is
 * an input and the SRAM is the only driver, so both being enabled together
 * during a block read is correct and is asserted separately below. */
claim("break before make: nothing drives the map SRAM's pins while it drives",
  (la, p, rw) => { const o = mmu(la, p.e, p.q, rw); return !(o.mapoe && o.isooe && rw === 0) })

claim("the '245 is never enabled toward the SRAM outside a block write",
  (la, p, rw) => { const o = mmu(la, p.e, p.q, rw)
                   return !(o.isooe && rw === 0) || (la >= 0xffa0 && la <= 0xffaf) })

claim("the map SRAM never drives during a block write",
  (la, p, rw) => { const o = mmu(la, p.e, p.q, rw); return !(o.mapwe && o.mapoe) })

claim("/WE is only ever asserted while the '245 is enabled",
  (la, p, rw) => { const o = mmu(la, p.e, p.q, rw); return !o.mapwe || o.isooe })

/* -- the same two, as sequences rather than as instants ------------------ */
const seq = (la: number, rw: number, pick: (o: Out) => boolean) =>
  PHASES.map((p) => (pick(mmu(la, p.e, p.q, rw)) ? "1" : "0")).join("")

check(seq(0xffa0, 0, (o) => o.isooe) === "0011",
  "a block write enables the '245 at E-rise, not at Q-rise", seq(0xffa0, 0, (o) => o.isooe))
check(seq(0xffa0, 0, (o) => o.mapwe) === "0001",
  "/WE is one phase wide and starts a quarter cycle after the buffer", seq(0xffa0, 0, (o) => o.mapwe))
check(seq(0xffa0, 0, (o) => o.muxsel) === "1111",
  "the mux is switched for the whole cycle, so the SRAM gets address set-up")
check(seq(0xffa0, 0, (o) => o.mapoe) === "0000",
  "the map SRAM is off for every phase of a block write")
check(seq(0xffa0, 1, (o) => o.mapoe) === "0011",
  "a block read turns the map SRAM back on, for E-high only", seq(0xffa0, 1, (o) => o.mapoe))
check(seq(0xffa0, 1, (o) => o.isooe) === seq(0xffa0, 1, (o) => o.mapoe),
  "on a block read the SRAM and the '245 open together - A-to-B, one driver")
check(seq(0x1234, 0, (o) => o.mapoe) === "1111",
  "translation is live for every phase of an ordinary memory cycle")
check(seq(0xffb0, 0, (o) => o.ctrlcp) === "1100",
  "the control latch's clock pin falls at E-rise and rises at E-fall", seq(0xffb0, 0, (o) => o.ctrlcp))

/* Exactly one rising edge per control write - the bug the first draft had. */
const edges = (la: number, rw: number) => {
  const lv = [...PHASES.map((p) => mmu(la, p.e, p.q, rw).ctrlcp), mmu(la, 0, 0, rw).ctrlcp]
  return lv.slice(1).filter((v, i) => v && !lv[i]).length
}
check(edges(0xffb0, 0) === 1, "one rising edge on the '574 clock per control write", `${edges(0xffb0, 0)}`)
check(edges(0xffb0, 1) === 0, "no rising edge on a control read")
check(edges(0xffa0, 0) === 0, "no rising edge on a block write")

/* -- the register map, docs/machine.md 5 item 3 -------------------------- */
/* Entry index is A3..A0, and the translate index is {TASK, LA15..LA13}, so
 * $FFA0+n is task (n>>3), block (n&7). The '157 wiring in
 * mainboard.circuit.tsx assumes exactly this and nothing enforced it. */
const entryOf = (addr: number) => addr - 0xffa0
check(entryOf(0xffa0) === 0 && entryOf(0xffa7) === 7,
  "$FFA0-$FFA7 are task 0 blocks 0-7")
check(entryOf(0xffa8) === 8 && entryOf(0xffaf) === 15,
  "$FFA8-$FFAF are task 1 blocks 0-7")
check((entryOf(0xffa8) >> 3) === 1 && (entryOf(0xffa8) & 7) === 0,
  "entry bit 3 is TASK, bits 2-0 are the block - the '157's 4A/4B wiring")

console.log(failures === 0 ? "\nMMU GAL equations OK" : `\n${failures} FAILED`)
if (failures) process.exit(1)
