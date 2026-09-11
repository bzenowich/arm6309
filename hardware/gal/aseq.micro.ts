/* U2's microprogram - audio.md 10.2.3's W1..W6, as data.
 *
 * The sequencer is a microcoded engine: a work TYPE (3 bits) selects a
 * sequence, a step counter T (4 bits) walks it, and every control output is a
 * decode of (WT, T). Writing the sequences as a table rather than as equations
 * is the only way this stays reviewable - and it is the same origin discipline
 * jedec/cupl.ts states, one step further back: the table generates the terms,
 * the terms generate the CUPL and the Verilog.
 *
 * THE ONE INVARIANT THAT MAKES IT CHEAP: even T is a state-file READ, odd T is
 * a WRITE. A read holds its data for as long as the address holds (9.5), so a
 * read-modify-write is two slots and never three, and every control output that
 * distinguishes the two halves is a function of T0 alone.
 *
 * Addresses. A channel's eight words are {0, ch[1:0], w[2:0]} = 0..31; the
 * globals are $20..$25 and all of them have SFA4 = SFA3 = 0, which is why
 * SFA4 = !GLOBAL & WC1 is one term and not a mux.
 *
 *   w0  lane2 PEND      lanes1:0 NEXT[15:0]
 *   w1  lane2 CNT[16]   lanes1:0 CNT[15:0]      - bytes remaining
 *   w2  lane2 PTR[18:16] lanes1:0 PTR[15:0]
 *   w3  lane2 LC[18:16] lanes1:0 LC[15:0]
 *   w4                  lanes1:0 PER[15:0]
 *   w5                  lanes1:0 LEN[15:0]
 *   w6  lane2 VOL       lane1 reserved (was ATT)   lane0 reserved (was DAT)
 *   w7  lane2 PAN
 *
 *   $20 TIMER    $21 spare     $22 SPTR
 *   $23 spare    $24 spare     $25 host staging shadow (9.4.3)
 *
 * ⚠ $21 AND $24 WERE THE TEMPO TIMER'S - CIANEXT and W4's multiply scratch.
 * The timer is U1's counter now (8.2, 16 item 44), and slot 4 reads TIMER at
 * $20 for it to reload from.
 *
 * ⚠ LANE 3 IS UNUSED, DELIBERATELY. Every host-visible byte and every byte a
 * converter takes lives in lanes 0-2, which is what lets the read-back path be
 * three prefetch latches instead of a four-to-one mux on eight bits (four
 * '153s). 5.3's "the eight extra bits are for nothing, today" is now load
 * bearing: they are the bits that are not there.
 */

/** B-bus source. The bus is pulled down, so "none" is a hard zero and `A + 1`
 *  costs no package at all. */
export type BSrc = "zero" | "blat" | "ones"

export interface Step {
  /** word within the channel, 0-7 */
  w?: number
  /** global word, 0-5 -> $20..$25 */
  g?: number
  /** the address comes from the host offset decode, not from here (W3) */
  host?: "target" | "stage" | "commit" | "sptr"
  /** state-file lanes written; absent = this step is a read */
  wr?: number[]
  alat?: boolean
  blat?: boolean
  b?: BSrc
  cin?: boolean
  /** drive the adder's sum onto SD[15:0] */
  sum?: boolean
  /** sample RAM: read into the sample latch */
  srd?: boolean
  /** sample RAM: write from the posted-write latch */
  swr?: boolean
  /** drive the sample latch onto SD[23:16] - the PEND lane */
  sbo?: boolean
  /** capture SD[18:16] into U2's three high bits */
  cap?: boolean
  /** drive SD[18:16] from U2, incremented when `cin` carried */
  drv?: boolean
  /** the posted-write latch drives SD */
  pw?: boolean
  /** clock the addressed lane's prefetch latch */
  pf?: boolean
  /** U1 drives the free-running count onto the state file's data bus, so the
   *  adder can reach it without a seventeenth wire (10.2.2) */
  count?: boolean
  /** override the channel: W5 walks all four rather than working on WC */
  ch?: number
  /** clock that channel's converter port register out of a work slot */
  cvld?: boolean
  /** arm 6.2's volume write for the DAC A pair ("a" - port registers 0 and 1)
   *  or the DAC B pair ("b" - 3 and 2). The strobe itself is not a step: it is
   *  the frame-parity window, and the sequence waits for it. */
  varm?: "a" | "b"
  /** this step writes PEND, so 6.2's converter strobe fires for the channel.
   *  ⚠ It is a FIELD and not a step number because there are two such steps -
   *  W1's and W6's priming write - and the second one was missing. */
  pend?: boolean
  /** the sequence may end here, if the named condition holds */
  done?: "always" | "noinc" | "nocommit" | "notend"
}

/** ⛔ 16 ITEM 35: WHAT SD[18:16] MUST DO ON A STEP THAT DRIVES IT.
 *
 * Nine steps drive the high lane and they need FOUR behaviours, and the fitted
 * design distinguished them with `cin` and `ACOUT` - which cannot, because
 * four of them have `cin` = 0. `CNT - 1` never took the borrow and
 * `LEN + LEN` never delivered the carry, so the 17-bit CNT 3.3 advertises did
 * not exist. This function is that distinction, derived from what the step is
 * ARITHMETICALLY doing rather than from a carry in, and it is the ONE origin:
 * aseq.jedec.ts builds HM0/HM1 from it and arom.ts encodes it into HLOP. */
export type HighLaneMode = "off" | "cap" | "pass" | "inc" | "dec" | "carry"
export const highLaneMode = (s: Step): HighLaneMode => {
  if (s.cap) return "cap"
  if (!s.drv) return "off"
  if (s.b === "ones") return "dec"        // CNT - 1: bit 16 takes the BORROW
  if (s.b === "blat") return "carry"      // CNT = LEN + LEN: bit 16 IS the carry
  if (s.b === "zero" && s.cin) return "inc"
  return "pass"
}

/** W1 a channel event, W2 a buffer reload, W3 a host access, W6 DMACON's
 *  restart, W5 the volume converters. ⚠ 3 WAS W4, THE TEMPO TIMER, and is not
 *  reused: it multiplied TIMER by five into a colour-clock deadline that a
 *  16-bit compare could not hold past 65,536 colour clocks, so 125 BPM - 70,937
 *  - was out of range. U1 counts the timer itself now (audio.md 8.2, 16 item
 *  44). */
export const W1 = 0, W2 = 1, W3 = 2, W6 = 4, W5 = 5
export const SEQUENCES = [W1, W2, W3, W5, W6]

export const PROGRAM: Record<number, Step[]> = {
  /* -- W1: a channel's compare hit. Seven steps, and 10.2.5 counts them ---
   * The sample byte for the NEXT event is fetched here, which is what makes
   * the event instant itself a fixed write window and not a memory access. */
  [W1]: [
    /* 0 */ { w: 2, alat: true, cap: true, srd: true },
    /* 1 */ { w: 2, wr: [0, 1, 2], b: "zero", cin: true, sum: true, drv: true },
    /* 2 */ { w: 4, blat: true },
    /* 3 */ { w: 0, alat: true },
    /* 4 */ { w: 0, wr: [0, 1, 2], b: "blat", sum: true, sbo: true, pend: true },
    /* 5 */ { w: 1, alat: true, cap: true },
    /* 6 */ { w: 1, wr: [0, 1, 2], b: "ones", sum: true, drv: true, done: "notend" },
  ],
  /* -- W2: 3.3's shadow reload. The single highest-value line on the card:
   * LC and LEN are copied AT BUFFER END, so ProTracker's one-shot then loop
   * idiom works. LEN+LEN is the byte count and its carry out IS CNT[16], so
   * there is no shifter.
   *
   * ⭐ CNT IS LOADED AS 2*LEN - 1, NOT 2*LEN, AND THAT IS 16 ITEM 36'S D-1.
   * W1's end test is the BORROW out of CNT - 1, which fires when CNT was
   * already zero - one iteration late - so a 2*LEN-byte buffer yielded
   * 2*LEN + 1 samples on every loop. Firing on "the result is zero" instead
   * would need a sixteen-bit zero detect, which is sixteen signals into one
   * logic block on a part at 35 of 40 fan-in (item 35). Loading one less
   * costs TWO MICROCODE STEPS in a sequence that runs once per buffer end,
   * and nothing else at all.
   *
   * ⭐ AND IT FIXES D-2 IN THE SAME MOVE. LEN = 0 gives CNT = 0 - 1 = $1FFFF,
   * which is 131,072 bytes = Paula's 65,536 words, where before it gave one.
   * The 17th bit has to exist for that, which is item 35's HLOP. */
  [W2]: [
    /* 0 */ { w: 3, alat: true, cap: true },
    /* 1 */ { w: 2, wr: [0, 1, 2], b: "zero", sum: true, drv: true },
    /* 2 */ { w: 5, alat: true, blat: true },
    /* 3 */ { w: 1, wr: [0, 1, 2], b: "blat", sum: true, drv: true },
    /* 4 */ { w: 1, alat: true, cap: true },
    /* 5 */ { w: 1, wr: [0, 1, 2], b: "ones", sum: true, drv: true, done: "always" },
  ],
  /* -- W3: a host access, retired out of the work slots (9.3, 9.4.3).
   * ⚠ EVERY W3 RUNS ALL SIX STEPS and each step's controls are gated by which
   * register was touched, because a microprogram with jumps in it needs a
   * next-address field and this one needs a counter. Six work slots per host
   * access at 400 k accesses/s is 2.4 M of 10.6 M - 10.2.5 prices it. Step 0
   * writes the byte (to the shadow, or straight through for the one-byte
   * fields 9.4.3 calls atomic already), 1-2 are the commit, 3-4 are SDATA's
   * sample-RAM access and SPTR's increment, and 5 re-prefetches at the
   * post-incremented AIDX.
   *
   * ⛔ WHICH BYTE LANDS WHERE IS U2's HOST DECODE, NOT AIDX ALONE - 16 item 44.
   * Step 0 stored every posted byte at the (word, lane) AIDX named, so
   * ADMACON, AINTENA, AINTREQ and ACTRL wrote into channel fields and SPTR and
   * TIMER never reached their own words. Now only ADATA, SPTR and TIMER write
   * at all; SPTR and TIMER stage through $25 like any multi-byte field and
   * commit on their low byte to $22 and $20. */
  [W3]: [
    /* 0 */ { host: "stage", wr: [0], pw: true },
    /* 1 */ { g: 5, alat: true, cap: true },
    /* 2 */ { host: "commit", wr: [0, 1, 2], b: "zero", sum: true, drv: true },
    /* 3 */ { host: "sptr", alat: true, cap: true, srd: true, swr: true, pf: true },
    /* 4 */ { host: "sptr", wr: [0, 1, 2], b: "zero", cin: true, sum: true, drv: true },
    /* 5 */ { host: "target", pf: true, done: "always" },
  ],
  /* -- W4 (retired 2026-09-11): the tempo timer's multiply. See the note on
   * the W constants above; audio.md history.md has the ten steps. */
  /* -- W6: 1 requirement 6's restart, and it CHAINS INTO W1 ----------------
   * The 0-to-1 edge of DMACON's enable bit reloads the pointer and the count
   * from the shadow and sets NEXT, and then hands the engine to W1 without
   * releasing it - the same trick W1 already uses to reach W2.
   *
   * ⭐ THAT IS 16 ITEM 39's REPAIR, AND IT MAKES W6 SHORTER RATHER THAN
   * LONGER. W6 used to prime PEND itself, which cost it a sample fetch, a
   * pointer increment and a PEND write - and left two defects behind, because
   * its own fetch consumed a byte no W1 would ever count (so the first pass of
   * every note ran one byte past the buffer) and its PEND write raised none of
   * 6.2's WROTE flags (so the first sample of every note was never strobed
   * into the converter). Handing the fetch to W1 fixes both by DELETING the
   * duplicate rather than by correcting it: W1 already decrements CNT for
   * every byte it fetches, and W1 step 4 is the write 6.2's strobe watches.
   *
   * ⚠ NEXT IS SET TO THE BARE COUNT, not count + PER, because the chained W1
   * adds PER itself at step 4. Setting count + PER here would put the first
   * sample two periods out.
   *
   * ⚠ AND THE LAST STEP WRITES LANES 0 AND 1 ONLY. Lane 2 of word 0 is PEND,
   * and the chained W1 is about to write it; writing all three here would put
   * the top byte of the free-running counter into the converter's path for one
   * frame. */
  [W6]: [
    /* 0 */ { w: 3, alat: true, cap: true },
    /* 1 */ { w: 2, wr: [0, 1, 2], b: "zero", sum: true, drv: true },
    /* 2 */ { w: 5, alat: true, blat: true },
    /* 3 */ { w: 1, wr: [0, 1, 2], b: "blat", sum: true, drv: true },
    /* 4 */ { w: 1, alat: true, cap: true },
    /* 5 */ { w: 1, wr: [0, 1, 2], b: "ones", sum: true, drv: true },
    /* 6 */ { count: true, alat: true },
    /* 7 */ { w: 0, wr: [0, 1], b: "zero", sum: true, done: "always" },
  ],
}

/* -- W5: 6.1's volume, the other four converter halves -------------------
 *
 * A channel's port register carries its sample byte AND, while this runs, its
 * volume code, so W5 borrows all four and the one rule is that a borrow never
 * overlaps a write that needs the register's other contents. The strobes are
 * not steps: 6.2's windows are the frame parity and the slot phase, so W5
 * loads, arms the two DAC pairs, and HOLDS THE ENGINE until both have fired.
 *
 *   0-3  wait. A PEND write loads a port register and arms a SAMPLE window
 *        that fires within two frames; the sequence that made it ends at
 *        least two work slots later, and two more already put the first load
 *        after the latest such window. Four is margin (audio.md 6.2).
 *   4-7  read each channel's VOL into its port register; arm A after 0 and 1,
 *        B after 2 and 3. ⚠ ON T = 01xx, AND THAT IS NOT DECORATION: the
 *        address, the output enable and the four loads each collapse to one
 *        product term there. Loads on steps 2-5 fitted with FOUR CASCADES, on
 *        SFOE, SFA0 and SFA3 - the state file's address, the card's one tight
 *        path (3.2) - and T3.
 *   8-12 wait for the later window, which may be two frames away. No W1 may
 *        load a register - with a sample byte - before both volume windows
 *        fire.
 *
 * ⛔ WHAT IT REPLACES DID NOT WORK ON FOUR CHANNELS, audio.md 16 item 43. It
 * strobed a single work slot - 35 ns against the AD7528's 90 ns write pulse -
 * and it left volume codes in the registers, where the next sample write of the
 * PARTNER channel strobed them into a SAMPLE converter: 1,114 of 67,781 sample
 * writes on a four-channel module. */
PROGRAM[W5] = [
  /* 0 */ {},
  /* 1 */ {},
  /* 2 */ {},
  /* 3 */ {},
  /* 4 */ { ch: 0, w: 6, cvld: true },
  /* 5 */ { ch: 1, w: 6, cvld: true, varm: "a" },
  /* 6 */ { ch: 2, w: 6, cvld: true },
  /* 7 */ { ch: 3, w: 6, cvld: true, varm: "b" },
  /* 8 */ {},
  /* 9 */ {},
  /* 10 */ {},
  /* 11 */ {},
  /* 12 */ { done: "always" },
]

/** 9.3's sixteen host bytes, as (word, lane). AIDX[3:0] indexes this and
 *  AIDX[5:4] is the channel; the map is unchanged from 9.3 and the lane
 *  assignment was chosen to keep it that way. Big-endian within a field, so
 *  the last byte written is the low one and 9.4.3's commit rule gets its free
 *  ride from the natural write order. */
export const HOSTMAP: { w: number; lane: number; ro?: boolean }[] = [
  { w: 3, lane: 2 }, { w: 3, lane: 1 }, { w: 3, lane: 0 },   // LC, commits at 2
  { w: 5, lane: 1 }, { w: 5, lane: 0 },                      // LEN, commits at 4
  { w: 4, lane: 1 }, { w: 4, lane: 0 },                      // PER, commits at 6
  { w: 6, lane: 2 },                                         // VOL
  { w: 6, lane: 0 },                                         // reserved (was DAT)
  { w: 6, lane: 1 },                                         // reserved (was ATT)
  { w: 7, lane: 2 },                                         // reserved (was PAN)
  { w: 2, lane: 2, ro: true }, { w: 2, lane: 1, ro: true },
  { w: 2, lane: 0, ro: true },                               // PTR, read-only
  { w: 1, lane: 1, ro: true }, { w: 1, lane: 0, ro: true },  // CNT, read-only
]

/** The offsets whose arrival commits a staged multi-byte field, and the word
 *  and lanes the shadow is copied into. 9.4.3, normative. */
export const COMMIT: Record<number, { w: number; lanes: number[] }> = {
  2: { w: 3, lanes: [0, 1, 2] },   // LC, 3 bytes
  4: { w: 5, lanes: [0, 1] },      // LEN
  6: { w: 4, lanes: [0, 1] },      // PER
}

/** 9.2's direct-window ports that store into the state file, by register
 *  offset: SPTR (+$6-$8) into $22 and TIMER (+$B-$C) into $20, at the lane
 *  their byte order puts them on. Both stage through $25 like every multi-byte
 *  field and commit on their last byte, 9.4.3's rule. ⛔ Until 2026-09-11 no
 *  table said this and nothing built it: W3 put these bytes wherever AIDX
 *  pointed (audio.md 16 item 44). */
export const DIRECT: Record<number, { g: number; lane: number; commit?: boolean }> = {
  0x6: { g: 2, lane: 2 }, 0x7: { g: 2, lane: 1 }, 0x8: { g: 2, lane: 0, commit: true },
  0xb: { g: 0, lane: 1 }, 0xc: { g: 0, lane: 0, commit: true },
}

/** Offsets that are staged rather than written straight through. Everything
 *  else is one byte and therefore atomic already - 9.4.3 says so. */
export const STAGED = new Set([0, 1, 2, 3, 4, 5, 6])
