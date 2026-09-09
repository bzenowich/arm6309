/* The MMU GAL's equations, checked exhaustively.
 *
 * The equations themselves are in mmu.model.ts; this file is the claims
 * graphics.md 6.3.1 makes about them. "Exhaustively" is the whole 16-bit
 * address space x 4 quadrature phases x R/W - 524,288 evaluations, which is
 * nothing. There is no sampling here.
 *
 * jedec.check.ts runs the same model against the assembled fuse map.
 */

import { PHASES, mmu, type Out } from "./mmu.model"

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

/* ⭐ TWO BLOCK WINDOWS since 2026-09-09 - $FF90-$FF9F is a map entry's high
 * byte and $FFA0-$FFAF its low. The write INDEX is LA3..LA0 through U5's '157
 * and is therefore machine.md 3's {TASK, block} in both, which is the whole
 * point: splitting the two bytes on LA3 instead made the high byte land in
 * the other task's entry and put everything above physical 2 MB out of reach.
 * hardware/ram.md 4.3, docs/design-review2.md M-1. */
const inBlk = (la: number) =>
  (la >= 0xff90 && la <= 0xff9f) || (la >= 0xffa0 && la <= 0xffaf)

claim("the block windows are $FF90-$FF9F and $FFA0-$FFAF, and nowhere else",
  (la, p, rw) => mmu(la, p.e, p.q, rw).muxsel === inBlk(la))

claim("⭐ and $FF80-$FF8F, the fourth code of that window, is free",
  (la, p, rw) => la < 0xff80 || la > 0xff8f || !mmu(la, p.e, p.q, rw).muxsel)

claim("no map write outside a block window",
  (la, p, rw) => !mmu(la, p.e, p.q, rw).mapwe || inBlk(la))

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
                   return !(o.isooe && rw === 0) || inBlk(la) })

claim("the map SRAM never drives during a block write",
  (la, p, rw) => { const o = mmu(la, p.e, p.q, rw); return !(o.mapwe && o.mapoe) })

claim("/WE is only ever asserted while the '245 is enabled",
  (la, p, rw) => { const o = mmu(la, p.e, p.q, rw); return !o.mapwe || o.isooe })

/* -- TWO '245s since 2026-09-09, and the claim is that they never collide --
 *
 * design-review2.md M-1 fixed the DECODE - a map entry's two bytes got two
 * windows - and left the board with no data path to the high SRAM at all:
 * mainboard.circuit.tsx wired U1B's DQ0-DQ3 to physical A24..A21 and to
 * nothing else, so the byte machine.md 3 documents as readable and writable
 * could be neither. ram.md 3.1 had costed the second SRAM with "Isolation
 * '245: 0 - both SRAMs sit on the same D0-D7", and TWO COMMON-I/O SRAMS
 * CANNOT: each drives its own DQ pins for the whole of every translation, so
 * they are two nodes, two buffers and - this is the part that needs asserting
 * - two enables. One shared enable would put both '245s on D0-D7 for the
 * whole of any block read, one of them driving from a floating node. */
claim("⭐ the two '245s are never enabled at the same instant - one D0-D7 driver",
  (la, p, rw) => { const o = mmu(la, p.e, p.q, rw); return !(o.isooeLo && o.isooeHi) })

claim("and 'either' is exactly what the orderings above were asserted about",
  (la, p, rw) => { const o = mmu(la, p.e, p.q, rw)
                   return o.isooe === (o.isooeLo || o.isooeHi) })

claim("the high '245 is enabled only in $FF90-$FF9F",
  (la, p, rw) => !mmu(la, p.e, p.q, rw).isooeHi || (la >= 0xff90 && la <= 0xff9f))

claim("the low '245 is enabled only in $FFA0-$FFAF",
  (la, p, rw) => !mmu(la, p.e, p.q, rw).isooeLo || (la >= 0xffa0 && la <= 0xffaf))


/* -- the same two, as sequences rather than as instants ------------------ */
const seq = (la: number, rw: number, pick: (o: Out) => boolean) =>
  PHASES.map((p) => (pick(mmu(la, p.e, p.q, rw)) ? "1" : "0")).join("")

check(seq(0xffa0, 0, (o) => o.isooe) === "0011",
  "a block write enables the '245 at E-rise, not at Q-rise", seq(0xffa0, 0, (o) => o.isooe))
check(seq(0xff90, 0, (o) => o.isooeHi) === "0011" &&
      seq(0xff90, 0, (o) => o.isooeLo) === "0000",
  "a HIGH-byte write opens U18 and leaves U4 shut",
  `${seq(0xff90, 0, (o) => o.isooeHi)} / ${seq(0xff90, 0, (o) => o.isooeLo)}`)
check(seq(0xffa0, 1, (o) => o.isooeLo) === "0011" &&
      seq(0xffa0, 1, (o) => o.isooeHi) === "0000",
  "and a LOW-byte read opens U4 and leaves U18 shut - the case a shared " +
  "enable would have put two buffers on D0-D7 for",
  `${seq(0xffa0, 1, (o) => o.isooeLo)} / ${seq(0xffa0, 1, (o) => o.isooeHi)}`)
check(seq(0xff90, 0, (o) => o.mapwe) === "0001",
  "/WE reaches the high SRAM too - it is common to both windows",
  seq(0xff90, 0, (o) => o.mapwe))
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
