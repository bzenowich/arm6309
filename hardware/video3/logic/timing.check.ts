/* video3's dot path, as arithmetic.
 *   npm run check:video3
 *
 * ** WHY THIS FILE EXISTS. hardware/video3/docs/plan.md §14 item 1 is the claim the whole
 * card rests on: the palette LUT's address becomes SIXTEEN bits instead of eight
 * - the pixel byte on A7..A0 and an attribute on A15..A8 - and that this costs
 * nothing, because both halves come from latches clocked by the same dot edge so
 * the chain is unchanged in depth.
 *
 * Half of that claim is arithmetic and half is a board. THIS FILE IS THE
 * ARITHMETIC HALF, and it is here so that the numbers live somewhere a check
 * reads rather than in a paragraph - which is the defect class docs.check.ts
 * was written for and which this design already hit once, when `video`'s fitted
 * utilisation was quoted at a card that has no partition.
 *
 * ** WHAT IT CANNOT ANSWER. Fan-out, trace length and the loading of eight more
 * address lines on a TSOP-44. Those need a board file. Nothing here should be
 * read as saying the path closes - only that the BUDGET closes, and that a part
 * substitution which breaks it fails loudly instead of quietly.
 */

let failures = 0
const ok = (good: boolean, claim: string, detail = "") => {
  if (!good) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

/* -- the timing base, from graphics.md §6.1 and §6.2 ---------------------- */
const DOT_MHZ = 25.175
const DOT_NS = 1000 / DOT_MHZ
const DOTS_LINE = 800
const LINES = { "449": 449, "525": 525 } as const

ok(Math.abs(DOT_NS - 39.72) < 0.01, "the dot is 39.72 ns at 25.175 MHz", DOT_NS.toFixed(3))
ok(Math.abs(DOT_MHZ * 1e6 / DOTS_LINE / LINES["449"] - 70.086) < 0.01,
  "the 449-line family is 70.09 Hz")
ok(Math.abs(DOT_MHZ * 1e6 / DOTS_LINE / LINES["525"] - 59.940) < 0.01,
  "the 525-line family is 59.94 Hz - not 60.0, which is 86 s a day of tick drift")

/* -- the dot path ---------------------------------------------------------
 *
 * graphics.md §6.1's chain, part for part. The LUT is the IS61C6416AL-12
 * (§14.2.1), which is 12 ns where §6.1 budgeted a 15 ns part. */
const LATCH_CLK_Q = 8     // 74AHCT574 clock-to-output
const LUT_AA = 12         // IS61C6416AL-12 address access
const REG_SETUP = 5       // 74AHCT273 setup
const chain = LATCH_CLK_Q + LUT_AA + REG_SETUP
const margin = DOT_NS - chain

ok(chain === 25, "index latch -> LUT -> output register is 25 ns", `${chain} ns`)
ok(margin > 14, "which leaves 14.7 ns of margin in a dot", `${margin.toFixed(1)} ns`)

/* ⭐ THE CLAIM. The attribute latch is a second 74AHCT574 on the same dot edge,
 * so the LUT sees sixteen address lines settling together rather than eight.
 * An SRAM's address-access time is specified from the LAST address line to
 * change, so the chain is unchanged - the ATTR latch does not stack. */
const chainAttr = Math.max(LATCH_CLK_Q, LATCH_CLK_Q) + LUT_AA + REG_SETUP
ok(chainAttr === chain,
  "⭐ the ATTR latch does not lengthen the chain: t_AA is from the last line to change, " +
  "and both latches are clocked by the same dot edge")

/* ⚠ THE CRITERION IS MARGIN, NOT ZERO. graphics.md §6.1 rejected a 20 ns LUT
 * for a 640-wide card even though 8 + 20 + 5 = 33 ns "closes" in a 39.72 ns
 * dot: 6.7 ns is not a margin on a path with a switch matrix and a board in
 * it. The design point §6.1 took was 11.7 ns with a 15 ns part; MIN_MARGIN is
 * that number rounded down, and it is the line a substitution must not cross. */
const MIN_MARGIN = 10

ok(margin >= MIN_MARGIN, `and the margin clears the ${MIN_MARGIN} ns design point`,
  `${margin.toFixed(1)} ns`)

/* ⚠ the trap that would break the claim silently: a design that MUXES the
 * attribute ahead of the latch, or drives A15..A8 combinationally from the map
 * latch, puts a gate BETWEEN the register and the LUT. */
const MUX_AHEAD = 5       // a 74AHCT157-class gate delay, were one added
ok(DOT_NS - (chain + MUX_AHEAD) < MIN_MARGIN,
  "⚠ a combinational stage ahead of the LUT spends the margin below the design point - " +
  "plan §13.4 says the ATTR source is selected by output enable, not by a mux",
  `${(DOT_NS - chain - MUX_AHEAD).toFixed(1)} ns`)

/* -- the part substitutions that must fail loudly ------------------------- */
for (const [part, aa, want] of [["IS61C6416AL-12", 12, true],
                                ["a 15 ns LUT", 15, true],
                                ["a 20 ns LUT", 20, false],
                                ["a 25 ns LUT", 25, false]] as const) {
  const m = DOT_NS - (LATCH_CLK_Q + aa + REG_SETUP)
  ok((m >= MIN_MARGIN) === want,
    `${part}: ${want ? "clears" : "does NOT clear"} the ${MIN_MARGIN} ns design point`,
    `${m.toFixed(1)} ns of margin`)
}

/* -- ⭐ TRADE 3 SETTLED: the '153 mux stays, the tri-state pixel bus does not
 *
 * plan §13.3 trade 3 carried graphics.md §6.1's open question: four `74AHCT153`
 * as the default, "bench the tri-state version as the saving".  Here is the
 * arithmetic, and §19 item 2's decision for `video` already points the same way.
 *
 * ⚠ THE 74AHCT NUMBERS BELOW ARE FAMILY-TYPICAL AND NOT CITED.  graphics.md
 * §14.2.6 records that there is no 74AHCT datasheet in reference/datasheets/.
 * So the last claim in this block is the one that matters: it asks how good the
 * part would have to be for the answer to change, and the answer does not
 * depend on the estimate. */
const CPLD_CO  = 8        // ATF1508AS-15, a registered output
const MUX153   = 12       // '153 select -> Y
const T_PZH    = 10       // '574 OE asserted -> the bus is driven
const T_PHZ    = 10       // '574 OE released -> high-Z

const viaMux = CPLD_CO + MUX153 + REG_SETUP
ok(viaMux <= DOT_NS - MIN_MARGIN,
  `the '153 path closes with margin: MUXSEL -> '153 -> index latch is ${viaMux} ns`,
  `${(DOT_NS - viaMux).toFixed(1)} ns`)

/* ⛔ The tri-state bus must BREAK BEFORE MAKE.  Two '574s driving one net with
 * opposite values is not a slow path, it is a fight - so the outgoing latch has
 * to reach high-Z before the incoming one is enabled, and the two delays are
 * SEQUENTIAL inside one dot. */
const viaTri = CPLD_CO + T_PHZ + T_PZH + REG_SETUP
ok(viaTri > DOT_NS - MIN_MARGIN,
  "⛔ and the tri-state pixel bus does NOT: break-before-make puts t_PHZ and " +
  `t_PZH in series, ${viaTri} ns in a ${DOT_NS.toFixed(1)} ns dot`,
  `${(DOT_NS - viaTri).toFixed(1)} ns of margin, against a ${MIN_MARGIN} ns design point`)

/* ⚠ AND THE ARITHMETIC ALONE DOES NOT SETTLE IT - say so rather than dress it up.
 * The tri-state path misses the design point by ~3 ns under the estimates above,
 * and what it would need - t_PHZ and t_PZH each under ~8.4 ns - is INSIDE the
 * 74AHCT family's range, not outside it.  A cited datasheet could go either way,
 * which is precisely why graphics.md §14.2.6 flags that the repository does not
 * have one. */
const turnaroundBudget = DOT_NS - MIN_MARGIN - CPLD_CO - REG_SETUP
ok(turnaroundBudget / 2 > 7 && turnaroundBudget / 2 < 10,
  "⚠ the tri-state bus needs t_PHZ and t_PZH each under " +
  `${(turnaroundBudget / 2).toFixed(1)} ns - INSIDE the 74AHCT range, so the ` +
  "arithmetic narrows the question and does not close it",
  `${turnaroundBudget.toFixed(1)} ns for both, against ${T_PHZ + T_PZH} estimated`)

/* ⭐ WHAT DOES DECIDE IT IS THE LOADING, and that is not an estimate - it is a
 * count.  §6.1's table says "4 tri-state '574"; §8.2's second rank of fetch
 * latches, added AFTER that estimate, makes it eight outputs on one net.  AHCT
 * enable and disable times are specified into 50 pF, and eight off-state outputs
 * plus the index latch plus trace is comfortably past it - so the number that
 * kept the tri-state bus alive as a candidate was taken before the bus doubled. */

/* ⚠ And video3's bus is worse than the one §6.1 costed.  That table says
 * "4 tri-state '574"; §8.2's second rank of fetch latches - added later - makes
 * it EIGHT outputs on one net, all of them contributing off-state capacitance
 * whether their rank is selected or not. */
const DRIVERS = 8, DRIVERS_COSTED = 4
ok(DRIVERS > DRIVERS_COSTED,
  `⭐ eight '574 outputs would share the net, not the ${DRIVERS_COSTED} §6.1's estimate ` +
  "assumed - §8.2's second rank post-dates it, and it moves the margin the wrong way")

/* ⛔ THE DECISION, and it is a decision rather than a proof: the '153 mux stays.
 * It clears the design point; its alternative does not, under estimates whose
 * error bar is the same size as the miss, with a bus that has doubled since the
 * estimate - and graphics.md §19 item 2 already records the same choice taken for
 * `video`, with four '153 in the BOM and MUXSEL1:0 driving them.
 * ⛔ SO plan §13.3 TRADE 3 YIELDS NO BOARD ROOM, and partition.md §8's relief for
 * the cell budget has to come from trade 1 instead. */

/* -- the framebuffer side, graphics.md §2.1's cliff ----------------------- */
const SLOT_NS = 4 * DOT_NS          // four dots, four bytes across two x16 parts
const ACCESS_NS = 12 + 55 + 5       // mux + AS6C8016-55 + latch setup
ok(Math.abs(SLOT_NS - 158.9) < 0.1, "a fetch slot is 158.9 ns", SLOT_NS.toFixed(1))
ok(ACCESS_NS === 72, "a framebuffer access is 72 ns", `${ACCESS_NS} ns`)
ok(SLOT_NS - 2 * ACCESS_NS > 0,
  "two accesses fit a slot - which is the whole spare-access budget",
  `${(SLOT_NS - 2 * ACCESS_NS).toFixed(1)} ns spare`)
ok(SLOT_NS - 3 * ACCESS_NS < 0,
  "⚠ and THREE do not: there is exactly ONE spare access a slot, not two",
  `${(SLOT_NS - 3 * ACCESS_NS).toFixed(1)} ns`)

/* -- what the one spare access has to carry, plan §14 item 8 -------------- */
const SPARE_PER_SLOT = 1
const requesters = ["the map word (character and tile)", "copyrect, two accesses a group",
                    "the sprite's row fetch", "the CPU's read prefetch", "the span writer"]
ok(SPARE_PER_SLOT === 1,
  `⚠ ${requesters.length} requesters share one spare access a slot - plan §14 item 8 ` +
  `is the cadence this file cannot settle`)

/* -- ⭐ TRADE 1 SETTLED: the copy engine is byte-granular and needs NO new latch
 *
 * plan §13.3 trade 1 asked whether the copy engine's 32-bit read latch could
 * "borrow" §8.2's second fetch rank - four '574 already on the framebuffer data
 * bus.  It cannot, and the reason is not timing:
 *
 *   ⛔ A '574 HAS ONE OUTPUT ENABLE, and the fetch rank's output is committed to
 *   the PIXEL bus - the '153 mux's inputs.  §8.2 ties the two ranks together
 *   there and makes them exclusive with that enable.  Wiring the rank to the
 *   framebuffer data bus as well would mean that whenever the copy drove, BOTH
 *   ranks would be on the '153's inputs at once.  Two outputs, one net.
 *
 * ⭐ But the latch is not needed at all, because the four-byte group is not.
 * A byte-at-a-time copy reuses two latches the card already has: §11's `vread`
 * for the read and §7.4's posted-write '574 for the write.  Both reuses are safe
 * under rules that already exist - a copy moves WPTR, which is one of the things
 * RDVALID already falls on, and /WAIT holds a CPU VRAM access while CBUSY
 * exactly as it does while SPANBUSY. */
const COPY_ACC_PER_BYTE = 2          // one read access, one write access
ok(COPY_ACC_PER_BYTE === 2,
  "⭐ trade 1: a byte-granular copy is one read access and one write access, " +
  "and needs no 32-bit latch - `vread` and the posted-write '574 already exist")

/* -- the copy engine's rate, plan §6.1 ------------------------------------ */
const ACC_PER_FRAME = 115_600      // graphics.md §2.1, 70.09 Hz
const ACC_PER_S = ACC_PER_FRAME * (DOT_MHZ * 1e6 / DOTS_LINE / LINES["449"])
const WIDE_MBPS = (ACC_PER_S / COPY_ACC_PER_BYTE) * 4 / 1e6
const BYTE_MBPS = (ACC_PER_S / COPY_ACC_PER_BYTE) / 1e6
ok(Math.abs(WIDE_MBPS - 16.2) < 0.2,
  "a four-byte group would be 16.2 MB/s - ⛔ WITHDRAWN with trade 1",
  `${WIDE_MBPS.toFixed(1)} MB/s`)
ok(Math.abs(BYTE_MBPS - 4.05) < 0.1,
  "⭐ THE BUILT RATE is 4.05 MB/s, byte-granular", `${BYTE_MBPS.toFixed(2)} MB/s`)

/* what that costs the H-items copyrect exists for, against what they cost now */
for (const [what, bytes, now] of [["a 192-row window scroll (H5)", 192 * 640, 350],
                                  ["Select, 640x200 (H4)", 128000, 2600],
                                  ["GetBlk 64x64", 64 * 64, 41],
                                  ["a character-mode scrolled line", 24 * 160, 10.0]] as const) {
  const ms = bytes / (BYTE_MBPS * 1e6) * 1e3
  ok(ms < now, `${what}: ${ms.toFixed(1)} ms, against ${now} ms without an engine`,
    `${(now / ms).toFixed(0)}x`)
}

console.log(`\n${failures === 0 ? "ok" : "FAIL"}  video3's dot path and access budget, ` +
  `as arithmetic\n⚠ the fan-out half of plan §14 item 1 needs a board file and is NOT checked here\n`)
process.exit(failures === 0 ? 0 : 1)
