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
 *   w6  lane2 VOL       lane1 ATT   lane0 DAT
 *   w7  lane2 PAN
 *
 *   $20 TIMER    $21 CIANEXT   $22 SPTR
 *   $23 spare    $24 scratch   $25 host staging shadow (9.4.3)
 *
 * ⚠ LANE 3 IS UNUSED, DELIBERATELY. Every host-visible byte and every byte a
 * converter takes lives in lanes 0-2, which is what lets the read-back path be
 * three prefetch latches instead of a four-to-one mux on eight bits (four
 * '153s). 5.3's "the eight extra bits are for nothing, today" is now load
 * bearing: they are the bits that are not there.
 */

/** B-bus source. The bus is pulled down, so "none" is a hard zero and `A + 1`
 *  costs no package at all. */
export type BSrc = "zero" | "blat" | "ones" | "count"

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
  /** raise an 8.1 interrupt source at the end of this step */
  set?: number
  /** override the channel: W5 walks all four rather than working on WC */
  ch?: number
  /** clock that channel's converter port register out of a work slot */
  cvld?: boolean
  /** which converter package pair to strobe */
  cvstr?: "vol" | "pan"
  /** the second half of a frame's converter pair - port registers 3 and 2 */
  cvb?: boolean
  /** read PAN (w7) instead of VOL (w6) when ACTRL b5 is set; when it is clear
   *  the step drives nothing and the pull-downs write a zero, which is Paula's
   *  hard pan */
  panword?: boolean
  /** this step's read is suppressed when ACTRL b5 is clear, so the port
   *  register takes the pulled-down zero */
  zeroif?: "nopan" 
  /** the sequence may end here, if the named condition holds */
  done?: "always" | "noinc" | "nocommit" | "notend"
}

/** W1 a channel event, W2 a buffer reload, W3 a host access, W4 the tempo
 *  timer's reload, W6 DMACON's restart. There is no W5 here: 6.2's converter
 *  windows are a function of the slot phase and never of the microprogram. */
export const W1 = 0, W2 = 1, W3 = 2, W4 = 3, W6 = 4, W5 = 5

export const PROGRAM: Record<number, Step[]> = {
  /* -- W1: a channel's compare hit. Seven steps, and 10.2.5 counts them ---
   * The sample byte for the NEXT event is fetched here, which is what makes
   * the event instant itself a fixed write window and not a memory access. */
  [W1]: [
    /* 0 */ { w: 2, alat: true, cap: true, srd: true },
    /* 1 */ { w: 2, wr: [0, 1, 2], b: "zero", cin: true, sum: true, drv: true },
    /* 2 */ { w: 4, blat: true },
    /* 3 */ { w: 0, alat: true },
    /* 4 */ { w: 0, wr: [0, 1, 2], b: "blat", sum: true, sbo: true },
    /* 5 */ { w: 1, alat: true, cap: true },
    /* 6 */ { w: 1, wr: [0, 1, 2], b: "ones", sum: true, drv: true, done: "notend" },
  ],
  /* -- W2: 3.3's shadow reload. The single highest-value line on the card:
   * LC and LEN are copied AT BUFFER END, so ProTracker's one-shot then loop
   * idiom works. LEN+LEN is the byte count and the carry is CNT[16], so there
   * is no shifter - and LEN = 0 becomes 131,071 bytes on the next decrement,
   * which is Paula's 65,536 words for no terms at all. */
  [W2]: [
    /* 0 */ { w: 3, alat: true, cap: true },
    /* 1 */ { w: 2, wr: [0, 1, 2], b: "zero", sum: true, drv: true },
    /* 2 */ { w: 5, alat: true, blat: true },
    /* 3 */ { w: 1, wr: [0, 1, 2], b: "blat", sum: true, drv: true, done: "always" },
  ],
  /* -- W3: a host access, retired out of the work slots (9.3, 9.4.3).
   * ⚠ EVERY W3 RUNS ALL SIX STEPS and each step's controls are gated by which
   * register was touched, because a microprogram with jumps in it needs a
   * next-address field and this one needs a counter. Six work slots per host
   * access at 400 k accesses/s is 2.4 M of 10.6 M - 10.2.5 prices it. Step 0
   * writes the byte (to the shadow, or straight through for the one-byte
   * fields 9.4.3 calls atomic already), 1-2 are the commit, 3-4 are SDATA's
   * sample-RAM access and SPTR's increment, and 5 re-prefetches at the
   * post-incremented AIDX. */
  [W3]: [
    /* 0 */ { host: "stage", wr: [0], pw: true },
    /* 1 */ { g: 5, alat: true, cap: true },
    /* 2 */ { host: "commit", wr: [0, 1, 2], b: "zero", sum: true, drv: true },
    /* 3 */ { host: "sptr", alat: true, cap: true, srd: true, swr: true, pf: true },
    /* 4 */ { host: "sptr", wr: [0, 1, 2], b: "zero", cin: true, sum: true, drv: true },
    /* 5 */ { host: "target", pf: true, done: "always" },
  ],
  /* -- W4: the tempo timer, and it is 8.2's "fifth entry in the compare
   * structure" taken literally. CIANEXT is a colour-clock count compared
   * against the same free-running counter the channels use, so the timer costs
   * NOTHING per CIA tick - only this ten-step multiply once per period, at
   * 50 Hz. 5N = 4N + N, and 4N is two doublings, so there is no shifter here
   * either: both operands come off the file and A + A is a doubling. */
  [W4]: [
    /* 0 */ { g: 0, alat: true, blat: true },
    /* 1 */ { g: 4, wr: [0, 1], b: "blat", sum: true },
    /* 2 */ { g: 4, alat: true, blat: true },
    /* 3 */ { g: 4, wr: [0, 1], b: "blat", sum: true },
    /* 4 */ { g: 0, blat: true },
    /* 5 */ { g: 4, wr: [0, 1], b: "blat", sum: true },
    /* 6 */ { g: 4, blat: true },
    /* 7 */ { g: 4, wr: [] },
    /* 8 */ { g: 1, alat: true },
    /* 9 */ { g: 1, wr: [0, 1], b: "blat", sum: true, set: 4, done: "always" },
  ],
  /* -- W6: 1 requirement 6's restart. The 0-to-1 edge of DMACON's enable bit
   * reloads the pointer and the count from the shadow, primes PEND, and sets
   * NEXT one period ahead - so the first sample lands one period after the
   * enable, exactly as Paula's does. It JUMPS THE QUEUE (16 item 13), and its
   * first four steps are W2's, so the latch the replayer depends on completes
   * in two colour clocks against the 1.13 us that item asks for. */
  [W6]: [
    /* 0 */ { w: 3, alat: true, cap: true },
    /* 1 */ { w: 2, wr: [0, 1, 2], b: "zero", sum: true, drv: true },
    /* 2 */ { w: 5, alat: true, blat: true },
    /* 3 */ { w: 1, wr: [0, 1, 2], b: "blat", sum: true, drv: true },
    /* 4 */ { w: 2, alat: true, cap: true, srd: true },
    /* 5 */ { w: 2, wr: [0, 1, 2], b: "zero", cin: true, sum: true, drv: true },
    /* 6 */ { w: 4, alat: true },
    /* 7 */ { w: 0, wr: [0, 1, 2], b: "count", sum: true, sbo: true, done: "always" },
  ],
}

/* -- W5: 6.1's volume and 11.1's pan, which are the other eight converter
 * halves. A port register loaded from the walk holds PEND and nothing else, so
 * the volume codes need their own reads - and they must be loaded and strobed
 * inside ONE frame's work slots, because the walk reloads the registers in
 * slots 0-3. Twelve steps, at the ~200 volume writes a second a replayer
 * makes, and 10.2.5 prices it at nothing.
 *
 * ⚠ IT SUPPRESSES THE WALK'S PORT-REGISTER LOAD WHILE IT RUNS, so a sample
 * transition can be late by up to four colour clocks - 1.13 us - about 200
 * times a second. That is a real departure from 3.2's "jitter-free" and it is
 * 0.9 % of one sample period on 2 % of transitions. Stated rather than hidden.
 *
 * ACTRL b5 = 0 is Paula's hard pan and it is exact: the step that would read
 * PAN instead drives nothing, and SD's pull-downs write a zero into the port
 * register. There is no constant generator on this card and it does not need
 * one. */
PROGRAM[W5] = [
  /*  0 */ { ch: 0, w: 6, cvld: true },
  /*  1 */ { ch: 1, w: 6, cvld: true, zeroif: "nopan" },
  /*  2 */ { cvstr: "vol" },
  /*  3 */ { ch: 3, w: 6, cvld: true, cvb: true },
  /*  4 */ { ch: 2, w: 6, cvld: true, cvb: true, zeroif: "nopan" },
  /*  5 */ { cvstr: "vol", cvb: true },
  /*  6 */ { ch: 0, w: 7, cvld: true, panword: true, zeroif: "nopan" },
  /*  7 */ { ch: 1, w: 7, cvld: true, panword: true },
  /*  8 */ { cvstr: "pan" },
  /*  9 */ { ch: 3, w: 7, cvld: true, cvb: true, panword: true, zeroif: "nopan" },
  /* 10 */ { ch: 2, w: 7, cvld: true, cvb: true, panword: true },
  /* 11 */ { cvstr: "pan", cvb: true, done: "always" },
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
  { w: 6, lane: 0 },                                         // DAT
  { w: 6, lane: 1 },                                         // ATT
  { w: 7, lane: 2 },                                         // PAN
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

/** Offsets that are staged rather than written straight through. Everything
 *  else is one byte and therefore atomic already - 9.4.3 says so. */
export const STAGED = new Set([0, 1, 2, 3, 4, 5, 6])
