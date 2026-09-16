/* video3's dot path, as arithmetic.
 *   npm run check:video3
 *
 * ** WHY THIS FILE EXISTS. video3/docs/plan.md §14 item 1 is the claim the whole
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

/* -- the copy engine's rate, plan §6.1 ------------------------------------ */
const ACC_PER_FRAME = 115_600      // graphics.md §2.1, 70.09 Hz
const ACC_PER_S = ACC_PER_FRAME * (DOT_MHZ * 1e6 / DOTS_LINE / LINES["449"])
const COPY_MBPS = (ACC_PER_S / 2) * 4 / 1e6
ok(Math.abs(COPY_MBPS - 16.2) < 0.2,
  "copyrect is 16.2 MB/s where the columns are congruent mod 4", `${COPY_MBPS.toFixed(1)} MB/s`)
ok(Math.abs(COPY_MBPS / 4 - 4.05) < 0.1,
  "and 4.05 MB/s byte-granular", `${(COPY_MBPS / 4).toFixed(2)} MB/s`)

console.log(`\n${failures === 0 ? "ok" : "FAIL"}  video3's dot path and access budget, ` +
  `as arithmetic\n⚠ the fan-out half of plan §14 item 1 needs a board file and is NOT checked here\n`)
process.exit(failures === 0 ? 0 : 1)
