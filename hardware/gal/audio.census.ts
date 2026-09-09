/* What the audio card's logic consumes that nothing produces, and what the
 * sequencer would cost.  npm run census:audio
 *
 * ⛔ WHY THIS FILE WAS REWRITTEN ON 2026-09-09. It used to answer "does the
 * card's GAL allocation fit one PLCC-84", which was settled on 2026-09-07 and
 * has been settled ever since. The question that was never asked is the one
 * design-review2.md A-1 asked from the outside: the part fits because it holds
 * a fraction of the card, and nothing in this directory said which fraction.
 *
 * So this is the audio card's version of the port census that found eleven
 * unbuilt blocks on the video card (design-review2.md, method 1): enumerate
 * every literal the fitted design READS, subtract what it and the backplane
 * PRODUCE, and print the remainder. Then price what would have to produce it.
 *
 * The rule the video card paid for: a design output can be absent and prose
 * does not notice. Prose is not evidence here; the term lists are.
 */

import { audioCpld } from "./audio.cpld"

const fmt = (n: number, w = 3) => String(n).padStart(w)
const rule = (s: string) => { console.log(`\n${s}`); console.log("=".repeat(s.length)) }

/* -- 1. the port census -------------------------------------------------- */

/** Signals the backplane brings to the card - machine.md 2's slot. */
const BACKPLANE = new Set([
  "IOSEL", "E", "RW", "RESET",
  "A0", "A1", "A2", "A3", "A4", "A5", "A6",
  "D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7",
])

/** Signals the card's own board produces without any logic in them. */
const BOARD = new Set(["SLOTCLK"])

const produced = new Set(audioCpld.cells.map((c) => c.name))
const consumed = new Set<string>()
for (const c of audioCpld.cells) {
  for (const t of [...c.terms, c.oe ?? ""].join(" & ").split("&")) {
    const n = t.trim().replace(/^!/, "")
    if (n && /^[A-Za-z_]/.test(n)) consumed.add(n)
  }
}
if (audioCpld.clock) consumed.add(audioCpld.clock)
if (audioCpld.ar) consumed.add(audioCpld.ar)

const unproduced = [...consumed]
  .filter((n) => !produced.has(n) && !BACKPLANE.has(n) && !BOARD.has(n))
  .sort()

/** Where each of them has to come from, and it is the same place. */
const OWED: Record<string, string> = {
  SET0: "8.1 bit 0 - channel 0's buffer exhausted",
  SET1: "8.1 bit 1 - channel 1's buffer exhausted",
  SET2: "8.1 bit 2 - channel 2's buffer exhausted",
  SET3: "8.1 bit 3 - channel 3's buffer exhausted",
  SET4: "8.1 bit 4 - the tempo timer expired",
  SET5: "8.1 bit 5 - a posted write to SDATA overran",
  PWBUSY: "9.2 ASTAT b6 - the depth-1 posted write has not retired",
  PFVALID: "9.2 ASTAT b7 - the prefetch latch holds the current index",
}

rule("1. What U1 reads and nothing produces")
console.log()
console.log("  Every one of these is an interrupt source or a status bit, and every")
console.log("  one of them is produced by the sequencer - which is in no design file.")
console.log()
for (const n of unproduced) console.log(`     ${n.padEnd(9)} ${OWED[n] ?? "⚠ UNCLASSIFIED"}`)
console.log(`\n  ${unproduced.length} signals. Six of them are audio.md §1 requirement 7 -`)
console.log("  the per-channel end-of-buffer interrupt - which therefore cannot fire,")
console.log("  not because the interrupt block is wrong (it is right, and simulated)")
console.log("  but because nothing on the card ever raises a request.")

/* -- 2. what U1 has left ------------------------------------------------- *
 *
 * From cpld/audio.fit, which is the fitter's own arithmetic and not ours. */
const U1 = { cells: 89, cellsOf: 128, io: 57, ioOf: 64, dedicated: 2, dedicatedOf: 4 }

rule("2. What is left on U1 after the host block")
console.log()
console.log(`  logic cells   ${fmt(U1.cells)} of ${U1.cellsOf}   ${fmt(U1.cellsOf - U1.cells)} free`)
console.log(`  I/O pins      ${fmt(U1.io)} of ${U1.ioOf}   ${fmt(U1.ioOf - U1.io)} free  (JTAG on: four pins reserved)`)
console.log(`  dedicated in  ${fmt(U1.dedicated)} of ${U1.dedicatedOf}   ${fmt(U1.dedicatedOf - U1.dedicated)} free`)

/* -- 3. the sequencer's interface, enumerated ---------------------------- *
 *
 * Case A of audio.md §10.1: the free-running counter, the comparator and the
 * adder stay outside, so the 32-bit state-file data bus never enters the
 * logic. This is the CHEAPEST case for pins, and it is still this big.
 *
 * Every line is a wire that has to exist on the board for the datapath drawn
 * in §3.2, §4.2, §6.2 and §9.5 to work. Nothing here is speculative headroom.
 */
const SEQ_OUT = [
  ["SFA0-SFA5", 6, "state-file word address - 32 words of channel state, the timer, SPTR, AIDX and §9.4.3's shadow"],
  ["SFWE0-3", 4, "state-file byte-lane write enables (2 x IS61C6416, /LB and /UB each)"],
  ["SFOE", 1, "state-file /OE - it drives the internal read bus"],
  ["SROE", 1, "sample RAM /OE"],
  ["SRWE", 1, "sample RAM /WE - §9.5's posted write"],
  ["SRCE", 1, "sample RAM /CE"],
  ["ALATCK", 1, "clock the adder's A latch from the read bus"],
  ["BLATCK", 1, "clock the adder's B latch (PER, or zero)"],
  ["BCLR", 1, "force B = 0, for the +1 operations"],
  ["ACIN", 1, "adder carry in"],
  ["SUMOE", 1, "drive the sum back onto the state-file data bus"],
  ["SBLCK", 1, "clock the sample-byte latch out of sample RAM"],
  ["SBOE", 1, "drive the sample byte onto the file's PEND lane"],
  ["PTR16-18", 3, "§9.5: the pointer is 19 bits and the adder is 16 - the top three are in the logic"],
  ["CVLCK/CVRCK", 2, "§6.2's two converter port registers, one per side"],
  ["CVCS1-6", 6, "the six AD7528 chip selects"],
  ["CVWR", 1, "AD7528 /WR"],
  ["CVAB", 1, "AD7528 DAC A / DAC B select"],
  ["PWCK", 1, "clock the host's posted-write data latch"],
  ["PFCK", 1, "clock the ADATA/SDATA prefetch latch"],
  ["SET0-5", 6, "§8.1's six interrupt sources - the ones §1 above is missing"],
  ["PWBUSY", 1, "ASTAT b6"],
  ["PFVALID", 1, "ASTAT b7"],
] as const
const SEQ_IN = [
  ["SLOTCLK", 1, "the 28.37516 MHz slot clock"],
  ["RESET", 1, ""],
  ["HIT", 1, "the '688 comparator: this channel's NEXT equals the free-running count"],
  ["ACOUT", 1, "the '283 chain's carry out - §4.2's wrap and the buffer-end test"],
  ["S0-S2, CCLK", 4, "the slot phase, from U1"],
  ["SEL, RW, E, A0-A3", 7, "the host access U1 has decoded, so slot 5 knows what to retire"],
  ["HSFREQ, HSRREQ", 2, "U1: the host wants the state file / the sample RAM"],
  ["DEFREQ", 1, "U1: a host access is waiting for a deferred slot"],
  ["DMAEN0-3", 4, "U1: §1 requirement 6's enable, and its rising edge is the restart"],
  ["CTRL3-7", 5, "U1: raw volume, 8-channel, pan, timer enable, master. b0/b1 are the "
    + "filter's 4066 and b2 the clock mux - board wiring off U1, not sequencer inputs"],
  /* ⭐ AND NOT D0-D7, which is the one place the pin arithmetic gets a
   * present rather than a bill. The host's byte reaches the state file through
   * the posted-write '574 (§10), which the sequencer CLOCKS and never reads -
   * the same argument §9.5 makes for the 19 sample-RAM address lines. Eight
   * pins the obvious enumeration charges and the datapath does not. */
] as const

const sum = (rows: readonly (readonly [string, number, string])[]) =>
  rows.reduce((n, r) => n + r[1], 0)
const outs = sum(SEQ_OUT), ins = sum(SEQ_IN)

rule("3. What the sequencer has to reach - Case A, the cheap case")
console.log()
console.log("  outputs")
for (const [n, c, why] of SEQ_OUT) console.log(`   ${fmt(c, 2)}  ${n.padEnd(12)} ${why}`)
console.log(`   ${fmt(outs, 2)}  total`)
console.log("\n  inputs")
for (const [n, c, why] of SEQ_IN) console.log(`   ${fmt(c, 2)}  ${n.padEnd(12)} ${why}`)
console.log(`   ${fmt(ins, 2)}  total`)
console.log(`\n  ${outs} + ${ins} = ${outs + ins} signals, of which ${outs + ins - 2} need an I/O pin`)
console.log("  (SLOTCLK and RESET take the two dedicated ones).")

/* Macrocells: every output pin is one, and the deferred micro-sequencer's own
 * state is the rest. §10.2's micro-op tables are 24 steps over 6 sequences,
 * so a 5-bit step counter, a 2-bit channel register, six due flags, the four
 * DMA edge-detect shadows, the 19-bit PTR carry and §9.4.3's commit flags:
 * call it 30 registers behind the driven pins. It is an estimate and it is
 * labelled one - every estimate on the video card was wrong until it was
 * fitted (§10.1). */
const seqMc = outs + 30

/* -- 4. the verdict, as arithmetic rather than as an opinion ------------- *
 *
 * Three levers, priced, because 71 signals against a 68-pin part is close
 * enough that "it fits" and "it does not" are both one decision away. */
const LEVERS = [
  { pins: 3, ic: 1, what: "CVCS1-6 from a 74HC138 - 3 pins in, 6 selects out" },
  { pins: 2, ic: 1, what: "SFWE0-3 from a 74HC139 - the byte lane, encoded" },
  { pins: 2, ic: 0, what: "SET0-5 as a 3-bit source code and a strobe, decoded on U1" },
] as const

const need = outs + ins - 2
const geared = need - LEVERS.reduce((n, l) => n + l.pins, 0)
const gearIc = LEVERS.reduce((n, l) => n + l.ic, 0)
const free = U1.ioOf - U1.io
const PARTS = [
  { name: "the fitted U1, as it stands       ", io: free, mc: U1.cellsOf - U1.cells },
  { name: "a 2nd ATF1508AS PLCC-84, JTAG on  ", io: 64, mc: 128 },
  { name: "a 2nd ATF1508AS PLCC-84, JTAG off ", io: 68, mc: 128 },
  { name: "a 2nd ATF1508AS TQFP-100, JTAG off", io: 84, mc: 128 },
]

/* And the other partition, because "two parts" is only right if one part is
 * wrong. Merge U1 and U2 and the ~31 nets that cross between them stop being
 * pins - 62 pins saved, which is most of why the split is expensive. What
 * survives is the board: the backplane's 20, the oscillator, ACTRL's three
 * analogue selects, PFOE and the sequencer's 38 datapath lines. The cells do
 * not shrink the same way: a buried COMBINATIONAL node costs none, but every
 * register and every driven pin still costs one. */
const MERGED = { io: 63, mc: U1.cells + seqMc - 20 }
const ONE_PART = [
  { name: "one ATF1508AS PLCC-84 for all     ", io: 68, mc: 128 },
  { name: "one ATF1508AS TQFP-100 for all    ", io: 84, mc: 128 },
  { name: "one ATF1508AS PQFP-160 for all    ", io: 96, mc: 128 },
]

rule("4. Where the sequencer can go")
console.log()
for (const p of PARTS) {
  const okIo = p.io >= need, okMc = p.mc >= seqMc
  console.log(`  ${p.name}  ${fmt(p.io, 3)} I/O free, ${fmt(p.mc, 3)} cells free  ` +
    `${okIo && okMc ? "FITS" : [
      okIo ? "" : `${need - p.io} pins short`,
      okMc ? "" : `${seqMc - p.mc} cells short`,
    ].filter(Boolean).join(", ")}`)
}
console.log(`\n  needs ~${need} I/O and ~${seqMc} cells (${outs} driven pins + ~30 registers of state).`)
console.log("  The cells are comfortable on any of them. It is decided on PINS, and it")
console.log("  is decided by three or four of them.")
console.log("\n  Levers, if the pin count has to come down\n")
for (const l of LEVERS) console.log(`     -${l.pins} pins  +${l.ic} IC   ${l.what}`)
console.log(`\n  All three: ~${geared} I/O at +${gearIc} ICs.`)
console.log("\n  And the partition that is NOT taken - everything on one die\n")
for (const p of ONE_PART) {
  console.log(`  ${p.name}  ${fmt(p.io, 3)} I/O, ${fmt(p.mc, 3)} cells  ` +
    `${p.io >= MERGED.io && p.mc >= MERGED.mc ? "FITS" : [
      p.io >= MERGED.io ? "" : `${MERGED.io - p.io} pins short`,
      p.mc >= MERGED.mc ? "" : `${MERGED.mc - p.mc} cells short`,
    ].filter(Boolean).join(", ")}`)
}
console.log(`\n  merged needs ~${MERGED.io} I/O and ~${MERGED.mc} cells. ⭐ The split saves`)
console.log("  cells and spends pins; the merge saves pins and spends cells, and there")
console.log("  is no ATF1508AS with more than 128 of them. THAT is why it is two parts.")
console.log()
console.log("  ⭐ So the audio card's logic is TWO ATF1508AS, for the same reason the")
console.log("  video card's is two: not macrocells, PINS. U1 holds the host register")
console.log("  block, the interrupt block and the slot walk; U2 holds the sequencer.")
console.log("  U2 is a PLCC-84 with JTAG off - it is programmed out of circuit like U1 -")
console.log("  and it is NOT comfortable there: it needs one of the levers above, or")
console.log("  the TQFP-100 and the socket with it.")
console.log()
console.log("  ⚠ THIS IS AN ESTIMATE AND IT IS LABELLED ONE. Every pin estimate on the")
console.log("  video card was wrong until it was fitted (audio.md §10.1). What makes")
console.log("  this one worth acting on is not its precision, it is its SIGN: the")
console.log("  smallest honest enumeration of the datapath the card already specifies")
console.log("  is ten times the seven pins U1 has left.")
console.log()
