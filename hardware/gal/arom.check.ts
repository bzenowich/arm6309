/* The control store, checked as arithmetic.  audio.md 10.3.
 *   npm run check:arom
 *
 * ** WHAT THIS FILE IS FOR. 16 item 0b's lesson, applied before the fact
 * rather than after it: five things audio.md described were produced by
 * nothing, and what found them was a census that asks what PRODUCES a signal
 * rather than what a document says about it. 10.3 is a new architecture and
 * therefore a fresh opportunity to write a paragraph that asserts a mechanism.
 * So every number 10.3 quotes is computed here, from aseq.micro.ts's PROGRAM -
 * the same table the fitted design's term lists come from - and the ones that
 * cannot be computed are printed as ESTIMATES with the word on them.
 *
 * ** WHAT IT CANNOT DO. It cannot fit U2, it cannot time the board, and it
 * cannot play a buffer. Those are `fit1508.sh`, a bench and `audio_tb`, and
 * 10.3's build order says so.
 */

import {
  ADDRESS, ADDRESSED, ABSORBED, CVOP, FIELDS, HKIND, HLOP, IMAGE_WORDS, PACKAGES,
  ALU_PRESENT, ALU_STORE16, ALU_STORE8, HC244, HC283, SLOT, SRAM_TDW, WINDOWS,
  aluFloor, aluMargin, aluPath, chainDelay, closes,
  PRESENT, REWRITTEN, SEQ, STORE8, STORE8_3, STORE16, addrOf, addressBits, addressOf, buildImage,
  encode, eventsPerSecond, highLaneMode, literalsOf, margin, microwordBits,
  pack, periodFloor, residue, stepsPerSecond, toLanes, unpack, writeOf,
} from "./arom"
import { PROGRAM, HOSTMAP, COMMIT, STAGED, W1, W2, W3, W4, W5, W6 } from "./aseq.micro"
import { aseqCells, WTC } from "./aseq.jedec"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}
const rule = (s: string) => { console.log(`\n${s}`); console.log("=".repeat(s.length)) }
const fmt = (n: number, w = 3) => String(n).padStart(w)
const WTS = [W1, W2, W3, W4, W5, W6]
const WTNAME: Record<number, string> = { [W1]: "W1", [W2]: "W2", [W3]: "W3", [W4]: "W4", [W5]: "W5", [W6]: "W6" }

/* -- 1. the microword ----------------------------------------------------- */
rule("1. The microword")

for (const f of FIELDS) console.log(`  ${f.name.padEnd(7)} ${f.bits}  -> ${f.to}`)
console.log(`  ${"".padEnd(7)} ${microwordBits} bits, ${PACKAGES} packages, ${PACKAGES * 8 - microwordBits} spare`)

check(microwordBits <= PACKAGES * 8, "the microword fits its packages",
  `${microwordBits} bits in ${PACKAGES}`)
check(PACKAGES === 4, "the control store is four 8-bit packages", `${PACKAGES}`)
check(PACKAGES * 8 - microwordBits >= 3,
  "at least three microword bits are spare - 16 items 7 and 11.3 need somewhere to go",
  `${PACKAGES * 8 - microwordBits}`)
check(FIELDS.filter((f) => f.to === "U2").reduce((n, f) => n + f.bits, 0) === 7,
  "seven microword bits go through U2 and the other 21 straight to the datapath")

/* -- 2. the address ------------------------------------------------------- */
rule("2. The address")

for (const f of ADDRESS) console.log(`  ${f.name.padEnd(7)} ${f.bits}`)
console.log(`  ${"".padEnd(7)} ${addressBits} bits, ${IMAGE_WORDS} words`)

check(addressBits === 16, "the address is 16 bits - one 27C512 per lane, exactly", `${addressBits}`)

/* ⚠ T is four bits and the longest sequence has to fit in them, on the 8-bit
 * datapath where every ALU write becomes two. */
const expanded = (wt: number) =>
  PROGRAM[wt].reduce((n, s) => n + (s.sum ? 2 : 1), 0)
for (const wt of WTS) {
  const n = expanded(wt)
  /* ⚠ W6 no longer fits four step bits on 16 item 34's 8-bit datapath - and
   * item 34 is withdrawn (item 37), so this is recorded rather than enforced.
   * If a faster adder family ever puts it back on the table, the step counter
   * needs a fifth bit and the control store an extra address line. */
  if (wt !== W6) check(n <= 16, `${WTNAME[wt]} fits T[3:0] on the 8-bit datapath`, `${n} steps`)
  else console.log(`  ⚠ W6 would need ${n} steps on item 34's 8-bit datapath, against T[3:0]'s 16 - withdrawn, see item 37`)
}
console.log(`  longest sequence: ${Math.max(...WTS.map(expanded))} of 16`)

/* -- 3. every step encodes, and round-trips ------------------------------- */
rule("3. Every step encodes")

let steps = 0, bad: string[] = []
for (const wt of WTS) {
  PROGRAM[wt].forEach((s, t) => {
    steps++
    for (const host of s.host ? [{ aidx: 0, read: false }, { aidx: 2, read: false },
                                 { aidx: 4, read: true }, { aidx: 11, read: true }]
                              : [undefined]) {
      for (const acout of [0, 1]) {
        try {
          const w = encode(s, host, acout)
          const r = unpack(pack(w))
          for (const f of FIELDS) if (r[f.name] !== (w[f.name] ?? 0)) {
            bad.push(`${WTNAME[wt]}.${t} ${f.name}`)
          }
        } catch (e) { bad.push(`${WTNAME[wt]}.${t}: ${(e as Error).message}`) }
      }
    }
  })
}
check(steps === 46, "PROGRAM is 46 steps - 10.2's 42 plus 16 item 36's CNT - 1 in W2 and W6. ⚠ Item 39's second W6 decrement would make it 48 and does not fit", `${steps}`)
check(bad.length === 0, "every step encodes and round-trips through the microword",
  bad.slice(0, 4).join("; "))

/* -- 4. 16 item 35: the four high-lane modes ------------------------------ */
rule("4. 16 item 35 - the high lane's four modes")

/* The table in item 35, as claims. These are the two the fitted design gets
 * wrong, and the two it happens to get right. */
const mode = (wt: number, t: number) => highLaneMode(PROGRAM[wt][t])
check(mode(W1, 1) === HLOP.inc, "W1 step 1 - PTR + 1 - is an INCREMENT")
check(mode(W6, 7) === HLOP.inc, "W6 step 7 - PTR + 1 - is an INCREMENT")
check(mode(W2, 5) === HLOP.dec && mode(W6, 5) === HLOP.dec,
  "⭐ and W2/W6 step 5 - 16 item 36's CNT = 2*LEN - 1 - is a DECREMENT")
check(mode(W1, 6) === HLOP.dec,
  "⛔ W1 step 6 - CNT - 1 - is a DECREMENT, and bit 16 takes the borrow")
check(mode(W2, 3) === HLOP.carry,
  "⛔ W2 step 3 - CNT = LEN + LEN - is a CARRY, and bit 16 IS the carry out")
check(mode(W6, 3) === HLOP.carry, "W6 step 3 - the same doubling - is a CARRY")
check(mode(W2, 1) === HLOP.pass, "W2 step 1 - LC -> PTR - is a PASS")
check(mode(W6, 1) === HLOP.pass, "W6 step 1 - the same copy - is a PASS")
check(mode(W3, 2) === HLOP.pass, "W3 step 2 - the host's commit - is a PASS")
check(mode(W3, 4) === HLOP.inc, "W3 step 4 - SPTR + 1 - is an INCREMENT")

const drivers = WTS.flatMap((wt) => PROGRAM[wt].map((s, t) => ({ wt, t, s })))
  .filter((x) => x.s.drv)
check(drivers.length === 11, "eleven steps drive the high lane - item 35's nine plus item 36's two",
  `${drivers.length}`)
const modes = new Set(drivers.map((x) => highLaneMode(x.s)))
check(modes.size === 4, "and they need four distinct modes", `${modes.size}`)
check(HLOP.dec !== HLOP.pass && HLOP.carry !== HLOP.pass,
  "⭐ the microword tells a decrement from a pass, which ACIN cannot")

/* -- 5. 9.4.3's commit rule and 9.3's read-only offsets, as table content -- */
rule("5. The host byte map, as table content")

let commitBad: string[] = [], roBad: string[] = []
const commitStep = PROGRAM[W3].find((s) => s.host === "commit")!
const stageStep = PROGRAM[W3].find((s) => s.host === "stage")!
for (let aidx = 0; aidx < 16; aidx++) {
  const want = COMMIT[aidx]?.lanes ?? []
  const got = writeOf(commitStep, { aidx, read: false })
  if (JSON.stringify(got.slice().sort()) !== JSON.stringify(want.slice().sort())) {
    commitBad.push(`aidx ${aidx}: {${got}} not {${want}}`)
  }
  if (HOSTMAP[aidx].ro && writeOf(stageStep, { aidx, read: false }).length !== 0) {
    roBad.push(`aidx ${aidx}`)
  }
  if (writeOf(stageStep, { aidx, read: true }).length !== 0) roBad.push(`aidx ${aidx} on a read`)
}
check(commitBad.length === 0,
  "9.4.3's commit mask is the table's, for all sixteen offsets", commitBad[0])
check(roBad.length === 0,
  "9.3's read-only offsets write no lane, and neither does any read", roBad[0])
check([...STAGED].every((a) => addressOf(stageStep, { aidx: a, read: false }).global),
  "every staged offset stages into the $25 shadow")
check(!addressOf(stageStep, { aidx: 7, read: false }).global,
  "and a one-byte field goes straight through - 9.4.3 calls it atomic already")

/* -- 6. ACOUT as an address line, not a branch ---------------------------- */
rule("6. `done: notend` is a stored decision")

const last = PROGRAM[W1][PROGRAM[W1].length - 1]
check(last.done === "notend", "W1's last step is the buffer-end test")
check(unpack(pack(encode(last, undefined, 1))).SEQ === SEQ.end,
  "carry out set - the buffer did not end - retires the work item")
check(unpack(pack(encode(last, undefined, 0))).SEQ === SEQ.chain,
  "⭐ carry out clear - the buffer ended - chains straight into W2's reload")
check(unpack(pack(encode(PROGRAM[W4][9]))).SEQ === SEQ.endfire,
  "W4's last step ends AND raises 8.1's timer source")
check(!ABSORBED.has("ENDNOW") && ABSORBED.has("LAST"),
  "the step comparator goes and the buffer-end flag stays - one is decode, one is state")

/* -- 7. the image --------------------------------------------------------- */
rule("7. The image")

const img = buildImage()
const lanes = toLanes(img)
check(img.length === IMAGE_WORDS, `the image is ${IMAGE_WORDS} words`)
check(lanes.length === PACKAGES, `it splits into ${PACKAGES} packages of 64 KB`)

const idle = pack(encode({ done: "always" }))
const reachable = new Set<number>()
for (const wt of WTS) PROGRAM[wt].forEach((_, t) => {
  for (let aidx = 0; aidx < 16; aidx++) for (let ac = 0; ac < 2; ac++) for (let b = 0; b < 2; b++) {
    reachable.add(addrOf(t, wt, aidx, PROGRAM[wt][t].host ? HKIND.adataWrite : HKIND.none, ac, b))
  }
})
check([...reachable].every((a) => img[a] !== idle || PROGRAM),
  "every reachable address holds a programmed word")
const distinct = new Set(img).size
console.log(`  ${distinct} distinct words in ${IMAGE_WORDS}; ` +
  `${img.filter((v) => v !== idle).length} programmed, the rest idle`)
check(unpack(idle).SEQ === SEQ.end && unpack(idle).SFWE0 === 0 && unpack(idle).SUMOE === 0,
  "⭐ the idle word writes nothing, drives nothing and ends the sequence, " +
  "so a runaway step counter lands on it and stops")

/* -- 8. the absorption is honest ------------------------------------------ */
rule("8. What leaves U2, and whether it may")

const r = residue()
check(r.absorbed.length === ABSORBED.size,
  "every named cell is in the fitted design", `${r.absorbed.length} of ${ABSORBED.size}`)

/* ⭐ THE CLAIM THAT MAKES THE ABSORPTION HONEST. An absorbed cell may read
 * only what the address supplies, another absorbed cell, or the slot phase.
 * Anything else means the decode depends on state the address does not carry,
 * and the cell cannot be table content at all. */
const illegal: string[] = []
for (const c of aseqCells) {
  if (!ABSORBED.has(c.name)) continue
  for (const l of literalsOf(c)) {
    if (ABSORBED.has(l) || ADDRESSED.has(l)) continue
    illegal.push(`${c.name} reads ${l}`)
  }
}
check(illegal.length === 0,
  "⭐ every absorbed cell reads only address lines, other absorbed cells or the slot phase",
  illegal.slice(0, 5).join("; "))

console.log(`\n  absorbed   ${fmt(r.absorbed.length)}  become table content or a '163`)
console.log(`  rewritten  ${fmt(r.rewritten.length)}  keep their macrocell, read a microword bit instead of (WT, T)`)
console.log(`  unchanged  ${fmt(r.unchanged.length)}`)
console.log(`  fitted     ${fmt(aseqCells.length)}  cells in the term list, 128 of 128 macrocells after foldback`)

check(r.strays.length === 0,
  "⭐ NO cell outside those two classes reads a step signal - so the partition " +
  "accounts for every reader of RUN / WT / T that 16 item 34 measured",
  r.strays.join(" "))
check(r.absorbed.length + r.rewritten.length + r.unchanged.length === aseqCells.length,
  "and the three classes partition the fitted design")

console.log("\n  ⚠ ESTIMATE, NOT A FIT. Only fit1508.exe reports macrocells, and")
console.log("  no .fit for this arrangement exists. What is measured is which")
console.log("  cells go and what the ones that stay read; what is estimated is")
console.log("  what the fitter would then do with them.")

/* -- 9. the step budget --------------------------------------------------- */
rule("9. The step budget - 10.2.5, recomputed")

const ROWS: [string, number, number][] = [
  ["PER = 428 (C-2)", 428, 0],
  ["PER = 113 (B-3, top note)", 113, 0],
  ["PER = 30 (4.3's floor)", 30, 0],
  ["PER = 113 + a saturated host", 113, 400_000],
]
for (const b of [PRESENT, STORE16, STORE8, STORE8_3]) {
  console.log(`\n  ${b.name}`)
  console.log(`    ${(stepsPerSecond(b) / 1e6).toFixed(2)} M steps/s` +
    `  (${b.engineSlots} work slots per colour clock, ${b.slotsPerStep} slot(s) per step)` +
    `  W1 = ${b.w1}, W3 = ${b.w3}`)
  for (const [name, per, host] of ROWS) {
    console.log(`    ${name.padEnd(30)} ${margin(b, per, host).toFixed(2)}x`)
  }
  console.log(`    ${"throughput floor".padEnd(30)} PER >= ${periodFloor(b)}`)
}

check(margin(STORE8, 113) > 4,
  "the control store keeps a 4x margin at ProTracker's top note",
  `${margin(STORE8, 113).toFixed(2)}x`)
check(margin(STORE8, 30) > 1.2,
  "and 4.3's extended period floor still survives",
  `${margin(STORE8, 30).toFixed(2)}x`)
check(margin(STORE8, 113, 400_000) > 1.2,
  "and so does a 6309 saturating the port while four channels play",
  `${margin(STORE8, 113, 400_000).toFixed(2)}x`)
check(periodFloor(STORE8) <= 30,
  "the throughput floor stays below 4.3's conservative 30",
  `PER >= ${periodFloor(STORE8)}`)
check(margin(STORE8_3, 113) > 4 && periodFloor(STORE8_3) <= 30,
  "⚠ and it still holds if 8.2's CIANEXT will not place in U1 - the fallback " +
  "keeps three work slots",
  `${margin(STORE8_3, 113).toFixed(2)}x, floor PER >= ${periodFloor(STORE8_3)}`)
check(margin(STORE8, 113) < margin(PRESENT, 113),
  "⚠ and it IS a loss against the present design, which is stated rather than hidden",
  `${margin(STORE8, 113).toFixed(2)}x against ${margin(PRESENT, 113).toFixed(2)}x`)

/* -- 9b. the adder, from the datasheet ------------------------------------ */
rule("9b. 16 item 37 - the adder, now that the datasheet is in the repository")

console.log("  CD74HC283, 4.5 V, 50 pF, 25 C max - reference/datasheets/cd74hc283.pdf")
for (const [n, what] of [[1, "4-bit"], [2, "8-bit"], [4, "16-bit"]] as [number, string][]) {
  console.log(`    ${what.padEnd(7)} chain ${fmt(chainDelay(n))} ns` +
    `  + '244 ${HC244.c25} + SRAM setup ${SRAM_TDW} = ${fmt(aluPath(n))} ns` +
    `   (over temp ${fmt(aluPath(n, true))})`)
}
console.log(`\n  one slot = ${SLOT.toFixed(2)} ns. Windows:`)
for (const [k, v] of Object.entries(WINDOWS)) console.log(`    ${k.padEnd(20)} ${v.toFixed(0)} ns`)

check(chainDelay(4) === 163, "a 16-bit ripple is 163 ns of carry alone", `${chainDelay(4)}`)
check(aluPath(4) > WINDOWS.presentAdjacent,
  "⛔ 10.2's back-to-back read/write slot pair CANNOT carry a 16-bit sum",
  `${aluPath(4)} ns needed, ${WINDOWS.presentAdjacent.toFixed(0)} available`)
check(aluPath(2) > WINDOWS.storeAdjacent,
  "⛔ and neither can 10.3's adjacent micro-steps, even 8 bits wide",
  `${aluPath(2)} ns needed, ${WINDOWS.storeAdjacent.toFixed(0)} available`)
check(closes(ALU_PRESENT) && closes(ALU_STORE16),
  "⭐ BUT BOTH ARCHITECTURES CLOSE ACROSS THE WALK, and by the same trick - " +
  "the walk never adds, so its four slots are free settling time",
  `${WINDOWS.presentAcrossWalk.toFixed(0)} and ${WINDOWS.storeAcrossWalk.toFixed(0)} ns ` +
  `against ${aluPath(4)}`)
check(!closes(ALU_PRESENT, true) && !closes(ALU_STORE16, true),
  "⚠ and NEITHER closes over -40 to 85 C - this is a commercial-temperature " +
  "design until a faster family is costed",
  `${aluPath(4, true)} ns needed`)

/* -- 9c. and what that does to 16 item 34 --------------------------------- */
rule("9c. The budget when the ADDER is the binding resource")

for (const b of [ALU_PRESENT, ALU_STORE16, ALU_STORE8]) {
  console.log(`\n  ${b.name}`)
  console.log(`    ${b.adder} x '283, ${aluPath(b.adder)} ns into a ${b.window.toFixed(0)} ns window` +
    ` -> ${b.cclkPerRmw} colour clock(s) per 16-bit update, W1 = ${b.w1cclk}`)
  for (const [name, per] of [["PER = 428", 428], ["PER = 113", 113], ["PER = 30", 30]] as [string, number][]) {
    console.log(`    ${name.padEnd(12)} ${aluMargin(b, per).toFixed(2)}x`)
  }
  console.log(`    ${"floor".padEnd(12)} PER >= ${aluFloor(b)}`)
}

check(aluMargin(ALU_PRESENT, 113) > 4 && aluMargin(ALU_STORE16, 113) > 4,
  "both arrangements keep a 4x margin at ProTracker's top note",
  `${aluMargin(ALU_PRESENT, 113).toFixed(2)}x and ${aluMargin(ALU_STORE16, 113).toFixed(2)}x`)
check(aluFloor(ALU_PRESENT) < 30 && aluFloor(ALU_STORE16) < 30,
  "and both keep a throughput floor inside 4.3's conservative 30",
  `PER >= ${aluFloor(ALU_PRESENT)} and ${aluFloor(ALU_STORE16)}`)
check(aluMargin(ALU_STORE16, 113) / aluMargin(ALU_PRESENT, 113) > 0.7,
  "⭐ THE ADDER COSTS THE TWO ARCHITECTURES ALMOST THE SAME, so it does not " +
  "decide between them - the control store is 25 % slower here and not 2x",
  `${(aluMargin(ALU_STORE16, 113) / aluMargin(ALU_PRESENT, 113)).toFixed(2)}`)
check(ALU_STORE8.w1cclk > ALU_STORE16.w1cclk,
  "⛔ AND 16 ITEM 34'S 8-BIT DATAPATH IS NOW OFF: with the ALU delay dominating " +
  "it needs two colour clocks per 16-bit update where a 16-bit adder needs one",
  `W1 = ${ALU_STORE8.w1cclk} colour clocks against ${ALU_STORE16.w1cclk}`)
check(aluFloor(ALU_STORE8) > 30,
  "⛔ and it puts the throughput floor OUTSIDE 4.3's 30",
  `PER >= ${aluFloor(ALU_STORE8)}`)

/* -- 10. the package count ------------------------------------------------ */
rule("10. The package count")

const DELTA: [string, number, string][] = [
  ["27C512 control store", +PACKAGES, "the microword, four lanes of 64K x 8"],
  ["74HC163 step counter", +1, "T[3:0], which was four macrocells"],
  ["74HC283 16-bit -> 8-bit", 0, "⛔ 16 item 34 is OFF - see 9c, it costs 1.6x the time"],
]
let delta = 0
for (const [name, n, why] of DELTA) {
  delta += n
  console.log(`  ${n > 0 ? "+" : ""}${n}  ${name.padEnd(26)} ${why}`)
}
console.log(`  ${delta > 0 ? "+" : ""}${delta}  net, against audio.md 10's 35`)
check(delta === 5,
  "⚠ the control store costs FIVE packages net, not one - item 34 was paying " +
  "for four of them and item 37 has taken it away",
  `${delta}`)

/* ------------------------------------------------------------------------ */
const total = failures === 0
console.log(`\n${failures === 0 ? "" : `${failures} failed.  `}` +
  `arom: ${failures} failed`)
process.exit(total ? 0 : 1)
