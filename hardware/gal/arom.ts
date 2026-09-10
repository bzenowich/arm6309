/* U3 - the audio card's microcode control store.  audio.md 10.3.
 *
 * THE PROBLEM THIS ANSWERS. U2 is already a microcoded engine - a work type
 * and a step counter in registers, and 36 control outputs each a
 * sum-of-products decode of (RUN, WT[2:0], T[3:0]) qualified by the host
 * state. That is what an addressed memory does for nothing, and doing it in
 * an ATF1508AS costs all three of the family's limits at once: 128 of 128
 * logic cells, 61 foldback nodes, and six of eight logic blocks at 35 of 40
 * LAB fan-in (10.2.6). Three open items are stuck behind that one fact:
 *
 *   - item 34: the 8-bit datapath is worth -4 packages and fits nothing.
 *     `Grouping fail`, all eight LABs at FanIn [40].
 *   - item 35: SD[18:16] needs FOUR behaviours (inc / dec / pass / carry) and
 *     is given one bit of ACIN to tell them apart, which cannot, because four
 *     of the nine steps that drive it have ACIN = 0. CNT[16] is neither set by
 *     the load nor decremented by the walk: the 17-bit CNT does not exist.
 *   - item 36: two live, audible defects - every loop plays one sample past
 *     its end, and LEN = 0 gives one byte instead of 65,536 words - both of
 *     which trace to item 35, on a part with nothing left to repair them with.
 *
 * Moving the decode into a memory relieves all three at once, because the
 * (WT, T) decode stops being logic and becomes an address, and every
 * qualifier stops being a term and becomes an address line.
 *
 * ⚠ REVISED 2026-09-10, SAME DAY, BY A DATASHEET. cd74hc283.pdf says a single
 * package's carry is 39 ns, not the ~15 this file first guessed from the
 * '244's. Section 5b is that arithmetic. Two things follow and neither is
 * what it looks like: the adder does NOT decide between 10.2's arrangement
 * and 10.3's, because both have exactly one window long enough and it is the
 * same window; and item 34's 8-bit datapath is OFF, because with the ALU
 * delay dominating it costs 1.6x the time to save four packages. So the
 * control store is +5 packages and not +1, and the case for it is now
 * entirely about U2 being full. This file is the
 * arithmetic of that: the microword, the address map, the image and the step
 * budget - generated from THE SAME aseq.micro.ts PROGRAM the present design's
 * term lists come from, so the two are one microprogram and can be diffed
 * step for step.
 *
 *   npm run check:arom
 *
 * ⚠ WHAT IS MEASURED HERE AND WHAT IS NOT. The microword's width, the address
 * width, the image, the step budget and which of U2's cells become table
 * content are computed from the term lists. The residue's CELL and PIN
 * figures are an ESTIMATE and say so wherever they appear: only fit1508.exe
 * settles those, and no `.fit` for this arrangement exists. CLAUDE.md's trust
 * precedence is not suspended for a design one likes.
 */

import { PROGRAM, HOSTMAP, COMMIT, STAGED, W1, W2, W3, W4, W5, W6, type Step } from "./aseq.micro"
import { aseqCells, WTC } from "./aseq.jedec"

/* ======================================================================== *
 * 1. THE ADDRESS
 *
 * Everything the present design qualifies a control output WITH becomes an
 * address line and stops being a signal. That is the whole trade, and 16 item
 * 34's transferable result is why it works: a switch matrix counts signals,
 * not literals - so the cure for fan-in is to make the qualifier cease to be
 * a signal, which registering it (item 34's reverted pipeline) does not do
 * and addressing a memory with it does.
 * ======================================================================== */

export const ADDRESS = [
  { name: "T", bits: 4,
    why: "the step counter - a 74HC163 outside, not four macrocells. ⚠ Four bits is EXACTLY the longest sequence (W4 at 14 steps on the 8-bit datapath); a fifth costs no ROM this card can notice but does cost the counter a second package" },
  { name: "WT", bits: 3, why: "the work type - three registers on U2, driven out as pins" },
  { name: "AIDX", bits: 4,
    why: "9.3's host byte index. ⭐ This is what turns HOSTMAP, COMMIT, STAGED and the read-only offsets - HRO, HSTAGE, HCOMMIT, CL2, HW0-2, HL0-1, CW0-2, twelve cells - into table content" },
  { name: "HKIND", bits: 3,
    why: "which host port the access touched and its direction - U2's ISADATA / ISAIDX / ISSDATA / ISSPTR / ISTIMER plus HRW, encoded. ⚠ It is U2's and not the backplane's because 9.4.4's whole finding is that WHICH register was touched has to be captured on the synchronised leading edge" },
  { name: "ACOUT", bits: 1,
    why: "the adder's carry out. ⭐ Makes `done: notend` a stored decision rather than a branch, and gives item 35's four high-lane modes somewhere to come from" },
  { name: "BYTE", bits: 1,
    why: "⚠ 16 item 34's half-select, and item 34 is OFF since the '283 datasheet arrived (section 5b) - so this line is TIED LOW and the image is written to both halves. It is kept because it costs one address pin and nothing else, and because a faster adder family would put item 34 back on the table" },
] as const

export const addressBits = ADDRESS.reduce((n, f) => n + f.bits, 0)

/* ======================================================================== *
 * 2. THE MICROWORD
 *
 * ⚠ IT IS HORIZONTAL - one bit per control line, no encoding, no decoders -
 * and that was costed against the alternatives rather than assumed.
 *
 * ENCODED (25 bits, three packages) loses. Grouping the mutually exclusive
 * output enables into 2-bit fields does reach three packages, but each field
 * then needs a decoder that is also qualified by the engine phase: a '139 for
 * the two bus-source fields and a '138 for the ALU op. Three packages plus
 * two decoders is 5; four packages plus none is 4.
 *
 * OVERLAID BY PHASE (16 bits, two packages) loses harder. 10.2.3's invariant
 * says even T reads and odd T writes, so the read word and the write word
 * could share the bus - except that the invariant is not true of PROGRAM
 * (W1 steps 2 and 3 are both reads, W3 step 0 is an even write, and every
 * step of W5 alternates the wrong way), so it costs ~8 inserted no-op steps
 * to restore, W5 doubling from 6 to 12 - and W5 is the sequence that
 * suppresses the walk's converter load while it runs (10.2.3). Then the
 * overlay still has to be undone by phase, which for the level bits is the
 * same decoders again.
 *
 * ⭐ AND THE ENGINE PHASE COSTS NO GATES AT ALL, which is the property that
 * decides it: the control store's own /OE is the engine phase. In walk slots
 * every microword bit floats to its inert level on the pull-downs SD already
 * has (10.2.2), so nothing on the card has to AND anything with "is this a
 * work slot". A horizontal word is the only encoding for which that is true.
 * ======================================================================== */

export interface FieldDef {
  name: string
  bits: number
  /** where it goes: straight to the datapath, or into U2 to be merged */
  to: "datapath" | "U2"
  why: string
}

export const FIELDS: FieldDef[] = [
  /* -- the state file --------------------------------------------------- */
  { name: "SFA5", bits: 1, to: "datapath",
    why: "global versus channel. ⚠ SFA[4:3] is NOT here and cannot be: it is the working channel in a channel sequence, AIDX[5:4] in a host one, and the SLOT NUMBER during the walk. U2 holds all three and drives those two pins" },
  { name: "SFA20", bits: 3, to: "datapath",
    why: "the word within the channel, the global at $20+n, or - on a host step - the word 9.3's byte map puts the index on. One field for all three, because AIDX is an address line" },
  { name: "SFOE", bits: 1, to: "datapath",
    why: "⚠ ORed with the walk's read on the board, one gate of the '00 that already gates the write enables. It is also how ACTRL b5 = 0 writes a zero into a converter with no constant generator on the card: W5's zeroing steps simply leave it off and SD's pull-downs answer" },
  { name: "SFWE0", bits: 1, to: "datapath", why: "byte lane 0's write enable" },
  { name: "SFWE1", bits: 1, to: "datapath", why: "byte lane 1" },
  { name: "SFWE2", bits: 1, to: "datapath",
    why: "byte lane 2. ⭐ 9.4.3's commit mask is table content: LC writes three lanes, LEN and PER two, a read-only offset none - all read off AIDX, none of it a term" },

  /* -- the adder and its operands --------------------------------------- */
  { name: "ALATCK", bits: 1, to: "datapath", why: "the A operand takes the read bus" },
  { name: "BLATCK", bits: 1, to: "datapath", why: "the B operand takes the read bus" },
  { name: "BLATOE", bits: 1, to: "datapath", why: "B = the latched operand" },
  { name: "ONESOE", bits: 1, to: "datapath", why: "B = $FF, so A - 1 is A + $FF (10.2.2)" },
  { name: "CNTOE", bits: 1, to: "datapath",
    why: "U1 drives the free-running count onto SD, so W6 can set NEXT without a seventeenth wire" },
  { name: "ACIN", bits: 1, to: "datapath", why: "the carry in" },
  { name: "SUMOE", bits: 1, to: "datapath", why: "the sum drives SD" },

  /* -- the sample RAM and the byte on its way to PEND -------------------- */
  { name: "SROE", bits: 1, to: "datapath", why: "sample RAM read into the sample latch" },
  { name: "SRWE", bits: 1, to: "datapath", why: "sample RAM write from the posted-write latch" },
  { name: "SBOE", bits: 1, to: "datapath", why: "the sample latch drives SD[23:16], the PEND lane" },

  /* -- the host's two latches ------------------------------------------- */
  { name: "PWOE", bits: 1, to: "datapath", why: "the posted-write latch drives SD" },
  { name: "PFCK", bits: 1, to: "datapath", why: "9.3's prefetch register, inside U1" },
  { name: "PFLANE", bits: 1, to: "datapath",
    why: "which of the state file's two host-reachable lanes the index names - a pure function of AIDX, which is an address line" },

  /* -- what U2 has to merge --------------------------------------------- */
  { name: "CVOP", bits: 2, to: "U2",
    why: "6.1's volume pass: load this channel's converter port register off the read bus, or strobe the volume packages. It goes through U2 because the WALK loads the same four registers in slots 0-3 and one of them has to win" },
  { name: "HLOP", bits: 3, to: "U2",
    why: "⛔ 16 ITEM 35, AND THE REASON THIS FILE EXISTS. SD[18:16] needs { capture, pass, increment, decrement, take the carry } and the fitted design distinguishes them with ACIN, which cannot tell a decrement from a pass because both have ACIN = 0. Nine steps drive the high lane and four of them are wrong. Here it is three bits of a stored word and costs nothing to get right" },
  { name: "SEQ", bits: 2, to: "U2",
    why: "⭐ the entire next-state logic. `end` retires the work item; `chain` loads W2 without releasing the engine, which is W1's buffer-end path; `endfire` also raises 8.1's source, which U2 picks from WC or the timer. Because ACOUT is an address line, `done: notend` is a stored decision and U2 keeps no step comparator at all - LAST goes" },
]

export const SEQ = { next: 0, end: 1, chain: 2, endfire: 3 } as const
export const HLOP = { off: 0, cap: 1, pass: 2, inc: 3, dec: 4, carry: 5 } as const
export const CVOP = { off: 0, load: 1, strobe: 2 } as const

export const microwordBits = FIELDS.reduce((n, f) => n + f.bits, 0)
export const PACKAGES = Math.ceil(microwordBits / 8)

/** Bit offset of each field, LSB first, in declaration order. */
export const OFFSETS: Record<string, number> = {}
{
  let o = 0
  for (const f of FIELDS) { OFFSETS[f.name] = o; o += f.bits }
}

/* ======================================================================== *
 * 3. ENCODING A STEP
 * ======================================================================== */

export interface HostCtx {
  /** 9.3's byte index, 0-15 */
  aidx: number
  /** the host access is a read */
  read: boolean
}

export type Word = Record<string, number>

/** ⭐ The high-lane mode item 35 needs, derived from what the step is
 *  ARITHMETICALLY doing rather than from the carry in - which is the whole
 *  correction. `dec` is CNT - 1, where bit 16 must take the borrow and in the
 *  fitted design never does; `carry` is CNT = LEN + LEN, where bit 16 IS the
 *  carry out and in the fitted design is dropped. */
export const highLaneMode = (s: Step): number => {
  if (s.cap) return HLOP.cap
  if (!s.drv) return HLOP.off
  if (s.b === "ones") return HLOP.dec
  if (s.b === "blat") return HLOP.carry
  if (s.b === "zero" && s.cin) return HLOP.inc
  return HLOP.pass
}

/** The state-file word and the global flag, given the host context. */
export const addressOf = (s: Step, host?: HostCtx): { global: boolean; word: number } => {
  if (s.g !== undefined) return { global: true, word: s.g }
  if (s.w !== undefined) return { global: false, word: s.w }
  if (s.host && host) {
    switch (s.host) {
      case "stage": return STAGED.has(host.aidx)
        ? { global: true, word: 5 }                       // 9.4.3's staging shadow, $25
        : { global: false, word: HOSTMAP[host.aidx].w }   // one-byte fields go straight through
      case "sptr": return { global: true, word: 2 }       // $22
      case "commit": {
        const c = COMMIT[host.aidx]
        return c ? { global: false, word: c.w } : { global: true, word: 5 }
      }
      case "target": return { global: false, word: HOSTMAP[host.aidx].w }
    }
  }
  return { global: false, word: 0 }
}

/** The lanes a step writes - on a host step, 9.4.3's commit rule and 9.3's
 *  read-only offsets rather than the table's own `wr`. */
export const writeOf = (s: Step, host?: HostCtx): number[] => {
  if (!s.host || !host) return s.wr ?? []
  if (s.wr === undefined) return []
  const e = HOSTMAP[host.aidx]
  switch (s.host) {
    case "stage":
      if (host.read || e.ro) return []
      return [STAGED.has(host.aidx) ? 0 : e.lane]
    case "commit": {
      const c = COMMIT[host.aidx]
      return host.read || !c ? [] : c.lanes
    }
    default: return s.wr
  }
}

export const encode = (s: Step, host?: HostCtx, acout = 0): Word => {
  const a = addressOf(s, host)
  const wr = writeOf(s, host)
  const seq = s.done === undefined ? SEQ.next
    : s.done === "notend" ? (acout ? SEQ.end : SEQ.chain)
    : s.set !== undefined ? SEQ.endfire : SEQ.end
  /* W3 step 3 carries both srd and swr; the fitted design resolves it with
   * HRW at run time and here the direction is an address line. */
  const srd = s.srd && !(s.swr && host && !host.read)
  const swr = s.swr && !!host && !host.read
  return {
    SFA5: a.global ? 1 : 0,
    SFA20: a.word & 7,
    /* a step that names a word and does not write it is a read */
    SFOE: (a.global || s.w !== undefined || s.host) && wr.length === 0 && !s.cvstr ? 1 : 0,
    SFWE0: wr.includes(0) ? 1 : 0,
    SFWE1: wr.includes(1) ? 1 : 0,
    SFWE2: wr.includes(2) ? 1 : 0,
    ALATCK: s.alat ? 1 : 0,
    BLATCK: s.blat ? 1 : 0,
    BLATOE: s.b === "blat" ? 1 : 0,
    ONESOE: s.b === "ones" ? 1 : 0,
    CNTOE: s.count ? 1 : 0,
    ACIN: s.cin ? 1 : 0,
    SUMOE: s.sum ? 1 : 0,
    SROE: srd ? 1 : 0,
    SRWE: swr ? 1 : 0,
    SBOE: s.sbo ? 1 : 0,
    PWOE: s.pw ? 1 : 0,
    PFCK: s.pf ? 1 : 0,
    PFLANE: host && HOSTMAP[host.aidx].lane === 1 ? 1 : 0,
    CVOP: s.cvld ? CVOP.load : s.cvstr ? CVOP.strobe : CVOP.off,
    HLOP: highLaneMode(s),
    SEQ: seq,
  }
}

export const pack = (w: Word): number => {
  let v = 0
  for (const f of FIELDS) {
    const x = w[f.name] ?? 0
    if (x < 0 || x >= 1 << f.bits) throw new Error(`${f.name}: ${x} does not fit ${f.bits} bits`)
    v |= x << OFFSETS[f.name]
  }
  return v >>> 0
}

export const unpack = (v: number): Word => {
  const w: Word = {}
  for (const f of FIELDS) w[f.name] = (v >>> OFFSETS[f.name]) & ((1 << f.bits) - 1)
  return w
}

/* ======================================================================== *
 * 4. THE IMAGE
 * ======================================================================== */

/** HKIND: U2's five port decodes plus the direction, encoded. */
export const HKIND = {
  none: 0, adataWrite: 1, adataRead: 2, aidxWrite: 3,
  sdataWrite: 4, sdataRead: 5, sptr: 6, timer: 7,
} as const

/** ⚠ Host kinds that reach W3 with a byte index. `sptr` and `timer` are the
 *  9.2 direct-window ports and take W3's steps with AIDX ignored. */
const HOSTKINDS: [number, boolean][] = [
  [HKIND.adataWrite, false], [HKIND.adataRead, true],
  [HKIND.aidxWrite, false],
  [HKIND.sdataWrite, false], [HKIND.sdataRead, true],
  [HKIND.sptr, false], [HKIND.timer, false],
]

export const addrOf = (t: number, wt: number, aidx: number, hkind: number,
                       acout: number, byte: number) =>
  (t & 15) | (WTC[wt] << 4) | (aidx << 7) | (hkind << 11) | (acout << 14) | (byte << 15)

export const IMAGE_WORDS = 1 << addressBits

/** ⚠ Written whole, not sparsely: an unprogrammed cell is $FF and $FF is not
 *  the idle word. The idle word reads nothing, writes nothing, drives nothing
 *  and ends the sequence, so a runaway T lands on it and stops. */
export const buildImage = (): Uint32Array => {
  const idle = pack(encode({ done: "always" }))
  const img = new Uint32Array(IMAGE_WORDS).fill(idle)
  for (const wt of [W1, W2, W3, W4, W5, W6]) {
    PROGRAM[wt].forEach((s, t) => {
      for (let aidx = 0; aidx < 16; aidx++) {
        for (let acout = 0; acout < 2; acout++) {
          for (let byte = 0; byte < 2; byte++) {
            if (s.host) {
              for (const [kind, read] of HOSTKINDS) {
                img[addrOf(t, wt, aidx, kind, acout, byte)] =
                  pack(encode(s, { aidx, read }, acout))
              }
            } else {
              img[addrOf(t, wt, aidx, HKIND.none, acout, byte)] =
                pack(encode(s, undefined, acout))
            }
          }
        }
      }
    })
  }
  return img
}

/** The image split into the packages that hold it. */
export const toLanes = (img: Uint32Array): Uint8Array[] =>
  [...Array(PACKAGES).keys()].map((n) => Uint8Array.from(img, (v) => (v >>> (n * 8)) & 0xff))

/* ======================================================================== *
 * 5. THE STEP BUDGET
 *
 * 10.2.5's table, recomputed. Two things move, in opposite directions.
 *
 * SLOWER: a micro-step is TWO slot times (70.5 ns) and not one, because an
 * addressed memory cannot answer inside 35.24 ns and a pipeline register on
 * its output would cost more packages than the word does.
 *
 * FASTER: the engine gets FOUR work slots per colour clock and not three,
 * because 8.2's CIANEXT moves into U1's spare cells and slot 4 stops reading
 * the state file for the timer compare. U1 already holds the free-running
 * counter and the comparator; a 16-bit register beside them is 16 of its 40
 * spare cells and NOT ONE PIN.
 *
 * ⚠ AND THIS IS WHY 16 ITEM 34'S 8-BIT DATAPATH IS NOT OPTIONAL HERE. A
 * micro-step's read and the write that follows it are one micro-step apart,
 * so the adder has ~61 ns to settle rather than the ~17 the present design
 * gives it. FOUR cascaded 74HC 4-bit adders make neither figure - a single
 * '244 buffer is 23 ns max at 4.5 V (reference/datasheets/sn74hc244.pdf), and
 * a ripple carry through four packages is several of those. TWO do make
 * 61 ns. 16 item 37 states that finding as an open item: it is INHERITED by
 * this design, not created by it.
 * ======================================================================== */

/* ======================================================================== *
 * 5b. THE ADDER, TIMED - 16 item 37, from the datasheet
 *
 * ⛔ THE ESTIMATE THIS FILE SHIPPED WITH ON 2026-09-10 WAS WRONG BY 3x, AND IT
 * WAS WRONG IN THE OPTIMISTIC DIRECTION. It reasoned from the '244's 23 ns and
 * guessed a 4-bit adder was "several of those". `cd74hc283.pdf` is now in
 * reference/datasheets and says a single package's carry is 39 ns, not ~15.
 *
 * ⭐ AND THE CONSEQUENCE IS THE OPPOSITE OF WHAT IT LOOKS LIKE. It does not
 * decide between 10.2's arrangement and 10.3's, because once a 16-bit add is
 * 186 ns BOTH have exactly one place to put it - across the walk, one
 * read-modify-write per colour clock - and that costs both the same. What it
 * does decide is 16 item 34: with the ALU delay dominating, an 8-bit datapath
 * needs TWO colour clocks per 16-bit update where a 16-bit one needs one, so
 * it costs 1.75x the time to save four packages. That trade is off.
 * ======================================================================== */

/** CD74HC283, V_CC = 4.5 V, C_L = 50 pF, from reference/datasheets/cd74hc283.pdf
 *  5.5. ⚠ The card's real load is a '244 input and a short trace, nearer 15 pF,
 *  where the datasheet gives only a 5 V TYPICAL column - so there is margin
 *  here that is not quantified, and it is not spent. */
export const HC283 = {
  c25: { cinS0: 32, cinS1: 36, cinS2: 39, cinCout: 39, cinS3: 46, abCout: 39, abSn: 42 },
  c85: { cinS0: 40, cinS1: 45, cinS2: 49, cinCout: 49, cinS3: 58, abCout: 49, abSn: 53 },
}
/** SN74HC244 A -> Y, same conditions - reference/datasheets/sn74hc244.pdf. */
export const HC244 = { c25: 23, c85: 29 }
/** ⚠ ASSUMPTION, not a datasheet: the state file's data setup before /WE
 *  rises. No IS61C6416 datasheet is in the repository - 16 item 37. */
export const SRAM_TDW = 6

/** Worst-case ripple through an n-package chain: A/B of the least significant
 *  package to S3 of the most significant. */
export const chainDelay = (packages: number, t = HC283.c25) =>
  packages === 1 ? t.abSn
    : t.abCout + (packages - 2) * t.cinCout + t.cinS3

/** What the state file actually sees: the chain, plus the '244 that
 *  three-states the sum onto SD, plus the SRAM's own setup. */
export const aluPath = (packages: number, hot = false) =>
  chainDelay(packages, hot ? HC283.c85 : HC283.c25) + (hot ? HC244.c85 : HC244.c25) + SRAM_TDW

/** One slot time - 3.1's 28.37516 MHz. */
export const SLOT = 1000 / 28.37516

/** The windows an architecture can offer between the ALAT clock and the write.
 *  ⚠ Every latch clock is gated to the middle of its slot (aseq.jedec.ts's
 *  `gated()` says why), so a read slot contributes only its second half. */
export const WINDOWS = {
  /** 10.2: read slot then write slot, back to back. */
  presentAdjacent: 1.5 * SLOT,
  /** 10.2: read in slot 7, write in slot 5 of the next colour clock - the walk
   *  in between costs the engine nothing, because the walk never adds. */
  presentAcrossWalk: 6.5 * SLOT,
  /** 10.3: read micro-step then write micro-step inside one engine window. */
  storeAdjacent: 2 * SLOT,
  /** ⭐ 10.3: read on the SECOND engine micro-step, write on the FIRST of the
   *  next colour clock. Same trick, and it is why the control store costs
   *  nothing extra for the adder. */
  storeAcrossWalk: 6 * SLOT,
}

/** 4.1's PAL colour clock. */
export const CCLK = 3546895

export interface Budget {
  name: string
  /** slot times per micro-step */
  slotsPerStep: number
  /** slots per colour clock the engine owns */
  engineSlots: number
  /** steps for a channel event (W1) and for a host access (W3) */
  w1: number
  w3: number
}

export const stepsPerSecond = (b: Budget) => (CCLK * b.engineSlots) / b.slotsPerStep

/** The present design: one slot per step, three work slots (10.2.3). */
export const PRESENT: Budget = {
  name: "present - decode in macrocells", slotsPerStep: 1, engineSlots: 3, w1: 7, w3: 6,
}
/** ⚠ Priced and NOT taken: the adder cannot settle (16 item 37). */
export const STORE16: Budget = {
  name: "control store, 16-bit datapath", slotsPerStep: 2, engineSlots: 4, w1: 7, w3: 6,
}
/** The design. Every ALU write becomes two, which is item 34's measured 7 -> 10. */
export const STORE8: Budget = {
  name: "control store, 8-bit datapath", slotsPerStep: 2, engineSlots: 4, w1: 10, w3: 9,
}

/** ⚠ The fallback if 8.2's CIANEXT will not place in U1 beside the comparator
 *  (10.3.6): slot 4 keeps the timer compare and the engine keeps three slots. */
export const STORE8_3: Budget = {
  name: "control store, 8-bit datapath, CIANEXT left in the file",
  slotsPerStep: 2, engineSlots: 3, w1: 10, w3: 9,
}

/** 10.2.5's rows: channel events per second, four channels at a period. */
export const eventsPerSecond = (per: number) => (CCLK / per) * 4

export const margin = (b: Budget, per: number, hostStores = 0) =>
  stepsPerSecond(b) / (eventsPerSecond(per) * b.w1 + hostStores * b.w3)

/** The floor: four channels at one W1 per PER colour clocks. */
export const periodFloor = (b: Budget) =>
  Math.ceil((4 * b.w1 * b.slotsPerStep) / b.engineSlots)

/* -- and what the budget becomes once the ADDER is the binding resource --- *
 *
 * ⛔ The tables above price WORK SLOTS, and with a 39 ns carry per package
 * that is no longer what runs out. A 16-bit sum is 192 ns from the ALAT edge
 * to the state file's setup, and the only window either architecture has that
 * long is the one that STRADDLES THE WALK - so at most one read-modify-write
 * retires per colour clock, in both, and colour clocks are the budget.
 *
 * ⭐ THE DISCIPLINE THIS IMPOSES IS THE INVARIANT 10.3.4 FOUND TO BE FALSE.
 * "Even T reads, odd T writes" was stated by aseq.micro.ts and not obeyed by
 * PROGRAM; under this rule the microprogram has no choice - a read must land
 * on the LAST engine step of a colour clock and its write on the FIRST of the
 * next - so the parity becomes true by construction rather than by assertion.
 */
export interface AluBudget {
  name: string
  /** packages in the chain */
  adder: number
  /** the window this architecture can offer, ns */
  window: number
  /** engine steps per colour clock, and how many of them can be reads */
  stepsPerCclk: number
  /** colour clocks per 16-bit read-modify-write */
  cclkPerRmw: number
  /** colour clocks for one channel event - 10.2.3's W1 */
  w1cclk: number
}

/** W1 is three read-modify-writes (PTR + 1, NEXT + PER, CNT - 1) plus one
 *  auxiliary read (PER into BLAT) and the first RMW's own read colour clock.
 *  The present arrangement has three engine slots per colour clock and can
 *  retire a write and two reads in one; the control store has two engine
 *  micro-steps and can retire a write and one read. */
const w1 = (cclkPerRmw: number, spareReads: number) =>
  3 * cclkPerRmw + 1 + (spareReads >= 2 ? 0 : 1)

export const ALU_PRESENT: AluBudget = {
  name: "10.2, 16-bit adder, RMW across the walk",
  adder: 4, window: WINDOWS.presentAcrossWalk, stepsPerCclk: 3,
  cclkPerRmw: 1, w1cclk: w1(1, 2),
}
export const ALU_STORE16: AluBudget = {
  name: "10.3, 16-bit adder, RMW across the walk",
  adder: 4, window: WINDOWS.storeAcrossWalk, stepsPerCclk: 2,
  cclkPerRmw: 1, w1cclk: w1(1, 1),
}
export const ALU_STORE8: AluBudget = {
  name: "10.3, 16 item 34's 8-bit adder",
  adder: 2, window: WINDOWS.storeAcrossWalk, stepsPerCclk: 2,
  cclkPerRmw: 2, w1cclk: w1(2, 1),
}

/** Does the sum reach the state file in time, at 25 C and over temperature? */
export const closes = (b: AluBudget, hot = false) => b.window >= aluPath(b.adder, hot)

export const aluMargin = (b: AluBudget, per: number) =>
  CCLK / (eventsPerSecond(per) * b.w1cclk)

export const aluFloor = (b: AluBudget) => 4 * b.w1cclk

/* ======================================================================== *
 * 6. WHAT LEAVES U2
 *
 * Every cell in the fitted sequencer is either content for the control store
 * or state that stays. The split is by name so it can be read straight
 * against gal/cpld/aseq.fit.
 * ======================================================================== */

/** Cells whose whole job is decoding (WT, T) and the host qualifiers - which
 *  is to say, cells that BECOME the microword or its address. */
export const ABSORBED = new Set([
  /* the state-file address and its write enables */
  "GBL", "SFA5", "SFA2", "SFA1", "SFA0", "SFOE", "SFWE0", "SFWE1", "SFWE2",
  /* the adder, its operands and the three things that may drive the B bus */
  "ALATCK", "BLATCK", "BLATOE", "ONESOE", "CNTOE", "ACIN", "SUMOE",
  /* the sample RAM and the byte on its way to PEND */
  "SROE", "SRWE", "SBOE",
  /* the host's latches */
  "PWOE", "PFCK", "PFLANE",
  /* ⭐ 9.3's byte map, entire - this is AIDX being an address line */
  "HRO", "HSTAGE", "HCOMMIT", "CL2", "HW0", "HW1", "HW2", "HL0", "HL1",
  "CW0", "CW1", "CW2",
  /* the high lane's control. ⚠ SDH0-2 themselves STAY: they are the inc/dec
   * arithmetic item 35 is about, and arithmetic is not decode */
  "SDHCAP", "SDHOE",
  /* W5's half of the converter ops. The walk's half stays - it is the slot
   * phase, which the microprogram never sees */
  "CVB", "CVCSV",
  /* the step comparator: SEQ is a field now */
  "LAST",
  /* ⭐ and the step counter itself, which becomes a 74HC163 outside */
  "T0", "T1", "T2", "T3",
  /* 8.1's timer source, which is SEQ = endfire */
  "FIRE4",
])

/** Cells that STAY on U2 and are rewritten: they keep their job and their
 *  state, and the (WT, T) decode inside them is replaced by a microword bit.
 *  ⚠ This is the class that makes the census honest. A cell here has NOT been
 *  costed away - it still occupies a macrocell - and what it stops doing is
 *  reading seven step signals, which is the thing 16 item 34 measured as the
 *  fan-in driver. */
export const REWRITTEN = new Map<string, string>([
  ["WT0", "SEQ"], ["WT1", "SEQ"], ["WT2", "SEQ"],
  ["ENDNOW", "SEQ"], ["HACK", "SEQ"], ["AINC", "SEQ"], ["VDIRTY", "SEQ"],
  ["CVBUSY", "CVOP"], ["CVLD0", "CVOP"], ["CVLD1", "CVOP"],
  ["CVLD2", "CVOP"], ["CVLD3", "CVOP"],
  ["WROTE0", "CVOP"], ["WROTE1", "CVOP"], ["WROTE2", "CVOP"], ["WROTE3", "CVOP"],
  ["SFA4", "SFA5"], ["SFA3", "SFA5"],
])

export interface Residue {
  absorbed: string[]
  rewritten: string[]
  unchanged: string[]
  /** cells that are neither absorbed nor rewritten and still read a step
   *  signal. ⚠ This list must be EMPTY, or the partition is wrong. */
  strays: string[]
}

const STEP = /^(T[0-3]|WT[0-2]|RUN)$/

export const literalsOf = (c: { terms: string[]; oe?: string }) =>
  [...c.terms, c.oe ?? ""].join(" & ").split("&")
    .map((t) => t.trim().replace(/^!/, ""))
    .filter((n) => n && /^[A-Za-z_]/.test(n))

export const residue = (): Residue => {
  const absorbed: string[] = [], rewritten: string[] = [],
    unchanged: string[] = [], strays: string[] = []
  for (const c of aseqCells) {
    if (ABSORBED.has(c.name)) { absorbed.push(c.name); continue }
    if (REWRITTEN.has(c.name)) { rewritten.push(c.name); continue }
    unchanged.push(c.name)
    if (literalsOf(c).some((l) => STEP.test(l))) strays.push(c.name)
  }
  return { absorbed, rewritten, unchanged, strays }
}

/** ⭐ The claim that makes the absorption honest: an absorbed cell may read
 *  ONLY things the control store's address supplies, other absorbed cells, or
 *  the slot phase (which the board merges). Anything else means the decode
 *  depends on state the address does not carry, and the cell cannot be table
 *  content at all. */
export const ADDRESSED = new Set([
  /* the address lines themselves, and how aseq.jedec spells them */
  "RUN", "WT0", "WT1", "WT2", "T0", "T1", "T2", "T3", "ACOUT",
  "AIDX0", "AIDX1", "AIDX2", "AIDX3", "AIDX4", "AIDX5",
  /* HKIND is these six, encoded */
  "HRW", "ISADATA", "ISAIDX", "ISSDATA", "ISSPTR", "ISTIMER",
  /* the slot phase, merged on the board or on U2 - never in the table */
  "S0", "S1", "S2", "QCHAN", "QTMR", "SLOTCLK",
  /* the working channel, which drives SFA[4:3] from U2 and not from the ROM */
  "WC0", "WC1",
])
