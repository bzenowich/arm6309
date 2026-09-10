/* U2 - the audio card's sequencer.  audio.md 10.2.
 *
 * Everything here is generated from aseq.micro.ts's PROGRAM table, so the
 * microprogram has ONE origin and the fitter, Verilator and the checks all
 * read it. Adding a step is a row in that table, not an edit here.
 *
 * WHAT U2 IS AND IS NOT. It is control: a state-file address, a byte-lane
 * write enable, a latch clock, a bus enable. It never sees SD[15:0] - 10.1's
 * Case A keeps the counter, the comparator and the adder outside precisely so
 * that the 32-bit state-file bus does not become 32 pins - and the two facts it
 * needs FROM the data path arrive as one bit each: HIT from the '688 and ACOUT
 * from the '283 chain. The exceptions are SD[18:16], which are U2's own
 * bidirectional pins because 19-bit pointers do not fit a 16-bit adder (9.5),
 * and D0-D5, which is AIDX.
 */

import { counterTerms } from "./jedec/counter"
import { reduceTerms } from "./jedec/minimise"
import type { Cell } from "./jedec/assemble"
import {
  PROGRAM, HOSTMAP, COMMIT, STAGED, W1, W2, W3, W4, W5, W6, type Step,
} from "./aseq.micro"

/* -- how a (work type, step) becomes literals ---------------------------- *
 *
 * WT is re-encoded from 10.2.3's names so that the HOST sequence is the only
 * one with WT2 set: "not a host access" is then one literal instead of four,
 * and it appears in most of the equations below. */
export const WTC: Record<number, number> = { [W1]: 0, [W2]: 1, [W6]: 2, [W4]: 3, [W3]: 4, [W5]: 5 }
/* ⛔ DERIVED, NOT DECLARED. This was a hand-maintained table of sequence
 * lengths beside a table of sequences, and on 2026-09-10 they disagreed twice
 * in one afternoon: adding steps to W2 and W6 for 16 item 36 left LAST firing
 * mid-sequence, and the symptom was a channel that fell silent with no failing
 * claim anywhere - the microprogram simply stopped part-way and the engine
 * never released. One table. */
const LEN: Record<number, number> = Object.fromEntries(
  [W1, W2, W3, W4, W5, W6].map((wt) => [wt, PROGRAM[wt].length]))

const bits = (name: string, v: number, n: number) =>
  [...Array(n).keys()].map((i) => `${(v >> i) & 1 ? "" : "!"}${name}${i}`)
const stepLits = (wt: number, t: number) =>
  ["RUN", ...bits("WT", WTC[wt], 3), ...bits("T", t, 4)]

/** Terms for a control that is asserted on the given (work type, step) pairs.
 *  reduceTerms merges the adjacent ones, which is where most of the product
 *  terms go: W1 and W6 share four steps and W2 shares them again. */
const onSteps = (pairs: [number, number][]): string[] =>
  reduceTerms(pairs.map(([wt, t]) => stepLits(wt, t))).map((t) => t.join(" & "))

/** Every (work type, step) whose Step satisfies `p`. */
const where = (p: (s: Step) => boolean | undefined): [number, number][] => {
  const out: [number, number][] = []
  for (const wt of [W1, W2, W3, W4, W5, W6]) {
    PROGRAM[wt].forEach((s, t) => { if (p(s)) out.push([wt, t]) })
  }
  return out
}
/* ⚠ EVERY LATCH CLOCK IS GATED WITH THE SLOT CLOCK'S SECOND HALF, and it is
 * not decoration. A control output settles a few nanoseconds after the edge
 * that produced it, so a level asserted "for slot N" rises while SFA is still
 * moving and the SRAM has not answered - a '574 clocked on that edge captures
 * the previous slot's data. Anding !SLOTCLK moves the edge to mid-slot, by
 * which time the address is settled and the 12 ns file has answered.
 *
 * The state file's byte-lane write enables need the same thing and DO NOT get
 * it here: a write enable that glitches writes the wrong address, and a
 * glitch is a timing property this model cannot see. They are gated outside,
 * by one 74HC00 - an inverter and three gates, exactly. The sample RAM's /WE
 * needs neither: its address is the state file's held read output (9.5) and is
 * stable across both slots of the access. */
const gated = (terms: string[]) => terms.map((t) => `${t} & !SLOTCLK`)

const ctl = (name: string, p: (s: Step) => boolean | undefined, why?: string): Cell => ({
  pin: 0, name, assertedLow: false, s0: 1, registered: false, why,
  terms: onSteps(where(p)),
})

/* ======================= the work engine =============================== */

/* Deferred work runs in slots 5, 6 and 7 - WORKSLOT, from U1. 3.1 gave slot 5
 * to "host service" and 6-7 to deferred work; the microprogram makes no such
 * distinction, so the host's own sequence simply competes for all three. That
 * is 10.6 M work slots/s rather than 7.09 M, and 10.2.5's margins are quoted
 * against it. */
const engine: Cell[] = [
  { pin: 0, name: "RUN", assertedLow: false, s0: 1, registered: false,
    why: "a work slot with a sequence in it", terms: ["WORKSLOT & BUSY"] },
  { pin: 0, name: "WORKSLOT", assertedLow: false, s0: 1, registered: false,
    why: "slots 5, 6 and 7 - 3.1's host service and deferred work, together",
    terms: ["S2 & S1", "S2 & S0"] },

  /* The step counter. It advances once per work slot and reloads to zero when
   * the sequence ends, so a sequence's length is a decode and not a modulus. */
  ...[0, 1, 2, 3].map((i) => ({
    pin: 0, name: `T${i}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [
      ...counterTerms({ bits: ["T0", "T1", "T2", "T3"], enable: "RUN", clear: "LAST" })[i]
        .map((t) => `${t}`),
    ],
  })),
  { pin: 0, name: "LAST", assertedLow: false, s0: 1, registered: false,
    why: "the final step of the sequence in progress",
    terms: onSteps(([W1, W2, W3, W4, W5, W6] as number[]).map((wt) => [wt, LEN[wt] - 1])) },

  /* 16 item 13's bounded latch is this priority order: a DMACON restart jumps
   * the queue, so LC/LEN reach PTR/CNT within two colour clocks of the enable
   * and the replayer needs no delay loop. */
  { pin: 0, name: "RSTANY", assertedLow: false, s0: 1, registered: false,
    terms: [0, 1, 2, 3].map((i) => `RST${i}`) },
  { pin: 0, name: "DUEANY", assertedLow: false, s0: 1, registered: false,
    terms: [0, 1, 2, 3].map((i) => `DUE${i}`) },
  { pin: 0, name: "START", assertedLow: false, s0: 1, registered: false,
    terms: ["WORKSLOT & !BUSY & RSTANY", "WORKSLOT & !BUSY & TDUE",
      "WORKSLOT & !BUSY & DUEANY", "WORKSLOT & !BUSY & HDUE",
      "WORKSLOT & !BUSY & VDIRTY"] },

  { pin: 0, name: "BUSY", assertedLow: false, s0: 1, registered: true,
    terms: ["START", "BUSY & !LAST", "ENDNOW"] },

  /* The work type latched at START, and W1's chain into W2 at ENDNOW. */
  { pin: 0, name: "ENDNOW", assertedLow: false, s0: 1, registered: false,
    why: "W1 ended on a buffer end, so W2 follows without releasing the engine",
    terms: [`RUN & !WT2 & !WT1 & !WT0 & ${bits("T", 6, 4).join(" & ")} & !ACOUT`] },
  { pin: 0, name: "WT0", assertedLow: false, s0: 1, registered: true,
    /* W1 = 000, W2 = 001, W6 = 010, W4 = 011, W3 = 100, W5 = 101. ⚠ The host
     * sequence is the ONLY one with WT0 clear and WT2 set, and getting that
     * wrong put every host access on W5's microprogram - which reads volume
     * codes out of the state file and strobes converters, so nothing the host
     * wrote ever landed and every claim below the decode failed at once. */
    terms: ["ENDNOW", "START & !RSTANY & TDUE",
      "START & !RSTANY & !TDUE & !DUEANY & !HDUE", "WT0 & !START & !ENDNOW"] },
  { pin: 0, name: "WT1", assertedLow: false, s0: 1, registered: true,
    terms: ["START & RSTANY", "START & !RSTANY & TDUE", "WT1 & !START & !ENDNOW"] },
  { pin: 0, name: "WT2", assertedLow: false, s0: 1, registered: true,
    terms: ["START & !RSTANY & !TDUE & !DUEANY & HDUE",
      "START & !RSTANY & !TDUE & !DUEANY & !HDUE", "WT2 & !START & !ENDNOW"] },

  /* The channel a sequence is working on, lowest-numbered first. */
  { pin: 0, name: "WC0", assertedLow: false, s0: 1, registered: true,
    terms: ["RPICK1", "RPICK3", "DPICK1", "DPICK3", "WC0 & !START"] },
  { pin: 0, name: "WC1", assertedLow: false, s0: 1, registered: true,
    terms: ["RPICK2", "RPICK3", "DPICK2", "DPICK3", "WC1 & !START"] },
  /* Lowest-numbered first, for both queues. Written out because a priority
   * encoder that is "obviously" symmetric is how a channel gets serviced twice
   * and its neighbour never. */
  ...[0, 1, 2, 3].map((n) => ({
    pin: 0, name: `RPICK${n}`, assertedLow: false, s0: 1 as const, registered: false,
    terms: [["START & RSTANY", ...[0, 1, 2, 3].slice(0, n).map((i) => `!RST${i}`),
      `RST${n}`].join(" & ")],
  })),
  ...[0, 1, 2, 3].map((n) => ({
    pin: 0, name: `DPICK${n}`, assertedLow: false, s0: 1 as const, registered: false,
    terms: [["START & !RSTANY & !TDUE", ...[0, 1, 2, 3].slice(0, n).map((i) => `!DUE${i}`),
      `DUE${n}`].join(" & ")],
  })),
]

/* ======================= what makes work ================================ */

/* A channel's compare is looked at in its own walk slot, and only then: the
 * '688 is comparing that channel's NEXT against the free-running counter
 * because that is the word the walk has on the bus. 3.1's jitter argument is
 * exactly this - slots 0-3 run unconditionally, every colour clock. */
const CHSEL = (n: number) => `QCHAN & ${n & 2 ? "" : "!"}S1 & ${n & 1 ? "" : "!"}S0`
const sources: Cell[] = [
  ...[0, 1, 2, 3].map((n) => ({
    pin: 0, name: `DUE${n}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`${CHSEL(n)} & !NEQL & !NEQH & DMAEN${n} & CTRL7`, `DUE${n} & !CLR${n}`],
  })),
  ...[0, 1, 2, 3].map((n) => ({
    pin: 0, name: `CLR${n}`, assertedLow: false, s0: 1 as const, registered: false,
    terms: [`DPICK${n}`],
  })),
  /* The tempo timer's compare shares the comparator and lands in slot 4,
   * where the walk has $21 - CIANEXT - on the bus. 8.2. */
  { pin: 0, name: "TDUE", assertedLow: false, s0: 1, registered: true,
    terms: ["QTMR & !NEQL & !NEQH & CTRL6", "TARM", "TDUE & !TACK"] },
  { pin: 0, name: "TACK", assertedLow: false, s0: 1, registered: false,
    terms: ["START & !RSTANY & TDUE"] },
  /* Arming: CTRL6's 0-to-1 edge, so CIANEXT is set from the counter the first
   * time rather than from whatever the SRAM powered up holding. */
  { pin: 0, name: "TQ", assertedLow: false, s0: 1, registered: true, terms: ["CTRL6"] },
  { pin: 0, name: "TARM", assertedLow: false, s0: 1, registered: false,
    terms: ["CTRL6 & !TQ"] },

  /* 1 requirement 6: DMACON's enable edge restarts the channel. */
  ...[0, 1, 2, 3].map((n) => ({
    pin: 0, name: `DMAQ${n}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`DMAEN${n}`],
  })),
  ...[0, 1, 2, 3].map((n) => ({
    pin: 0, name: `RST${n}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`DMAEN${n} & !DMAQ${n}`, `RST${n} & !RCLR${n}`],
  })),
  ...[0, 1, 2, 3].map((n) => ({
    pin: 0, name: `RCLR${n}`, assertedLow: false, s0: 1 as const, registered: false,
    terms: [`RPICK${n}`],
  })),
]

/* ======================= the host boundary ============================== */

/* 9.4.4's two-flop synchroniser, and the thing the card did not have: the
 * LEADING edge. U1's NEWREQ is the trailing edge of a synchronised access,
 * which is after E has fallen and the address may already be gone - so which
 * register was touched was never captured anywhere. Here the offset and R/W
 * are latched on the leading edge, two slots into the access, and the work
 * item reads them at its leisure. */
const host: Cell[] = [
  { pin: 0, name: "HSY1", assertedLow: false, s0: 1, registered: true, terms: ["SEL & E"] },
  { pin: 0, name: "HSY2", assertedLow: false, s0: 1, registered: true, terms: ["HSY1"] },
  { pin: 0, name: "HSTB", assertedLow: false, s0: 1, registered: false,
    why: "9.4.4: one slot wide, on the leading edge of a synchronised access",
    terms: ["HSY1 & !HSY2"] },
  ...[0, 1, 2, 3].map((i) => ({
    pin: 0, name: `HA${i}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`HSTB & A${i}`, `HA${i} & !HSTB`],
  })),
  { pin: 0, name: "HRW", assertedLow: false, s0: 1, registered: true,
    terms: ["HSTB & RW", "HRW & !HSTB"] },
  /* ⭐ EVERY host access asks for a work item, index writes included - 9.3
   * says writing AIDX prefetches that entry and until 2026-09-09 nothing did,
   * so the first read after an index write returned the byte the PREVIOUS
   * index named. PWBUSY keeps its own `!AIDXLD`: an index load is not a posted
   * write and has nothing to retire. */
  { pin: 0, name: "HDUE", assertedLow: false, s0: 1, registered: true,
    terms: ["HSTB", "HDUE & !HACK"] },
  /* ⛔ IT FIRED AT `START` UNTIL 2026-09-09, WHICH IS WHERE THE SEQUENCE BEGINS.
   * `BUSY` covers START->LAST so the SEQUENCER could not restart - but `PWBUSY`
   * is what the HOST reads, and it had already gone low while W3 was still
   * running. `ASTAT` b6 said "free" mid-sequence, so a host polling it exactly
   * as 9.2 asks could still write into the window: `HSTB` set `HDUE` again and
   * loaded a new `AIDX`, and the continuously-clocked decodes (`HW`, `HL`,
   * `HRO`, `HSTAGE`) followed it UNDERNEATH the running sequence. A channel
   * kept its old period after the host had written a new one.
   *
   * ⚠ It survived the 2026-09-09 repair that made the flag SET correctly. Two
   * defects in one flag, and the first fix looked complete.
   *
   * The acknowledgement is the last step of the host's own sequence. `HDUE`
   * staying asserted throughout cannot restart anything, because `START`
   * requires `!BUSY`. */
  { pin: 0, name: "HACK", assertedLow: false, s0: 1, registered: false,
    why: "9.2: the host's access is retired when its sequence ENDS",
    terms: ["RUN & WT2 & !WT1 & !WT0 & LAST"] },

  /* Which of 9.2's registers. */
  { pin: 0, name: "ISADATA", assertedLow: false, s0: 1, registered: false,
    terms: ["!HA3 & !HA2 & !HA1 & HA0"] },
  /* ⛔ A WRITE TO AIDX MUST NOT BEHAVE LIKE A WRITE TO ADATA. It queues a work
   * item now, so that 9.3's "writing it PREFETCHES that entry" is finally
   * true - and by the time that item runs AIDX holds the NEW index, so W3
   * step 0 left ungated would store the index value into the state file at the
   * location the index names. Only the prefetch may run. */
  { pin: 0, name: "ISAIDX", assertedLow: false, s0: 1, registered: false,
    terms: ["!HA3 & !HA2 & !HA1 & !HA0"] },
  { pin: 0, name: "ISSDATA", assertedLow: false, s0: 1, registered: false,
    terms: ["HA3 & !HA2 & !HA1 & HA0"] },
  { pin: 0, name: "ISSPTR", assertedLow: false, s0: 1, registered: false,
    terms: ["!HA3 & HA2 & HA1 & !HA0", "!HA3 & HA2 & HA1 & HA0", "HA3 & !HA2 & !HA1 & !HA0"] },
  { pin: 0, name: "ISTIMER", assertedLow: false, s0: 1, registered: false,
    terms: ["HA3 & !HA2 & HA1 & HA0", "HA3 & HA2 & !HA1 & !HA0"] },

  /* 9.3's index. ⛔ IT CANNOT LIVE IN THE STATE FILE, which is what 9.5 said
   * it did - "at a fixed address the sequencer knows, which is what breaks the
   * circularity". It does not break it: the sequencer would have to READ the
   * index to compute the address of the byte the index names, and Case A's U2
   * has no data bus. Six registers here, and D0-D5 is the only reason U2 sees
   * the host's data at all. */
  { pin: 0, name: "AIDXLD", assertedLow: false, s0: 1, registered: false,
    terms: ["HSTB & !A3 & !A2 & !A1 & !A0 & !RW"] },
  { pin: 0, name: "AINC", assertedLow: false, s0: 1, registered: false,
    why: "9.2: ADATA post-increments",
    terms: ["RUN & WT2 & !WT1 & !WT0 & LAST & ISADATA"] },
  ...[0, 1, 2, 3, 4, 5].map((i) => ({
    pin: 0, name: `AIDX${i}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [
      `AIDXLD & D${i}`,
      ...counterTerms({ bits: ["AIDX0", "AIDX1", "AIDX2", "AIDX3", "AIDX4", "AIDX5"],
        enable: "AINC" })[i].map((t) => `!AIDXLD & ${t}`),
    ],
  })),
]

/* The (word, lane) a host byte lands on, decoded from AIDX[3:0]. Registered,
 * because these feed the address and the write enables and a combinational
 * copy would multiply every one of those equations by eight terms. */
const mapBit = (f: (e: typeof HOSTMAP[0]) => boolean) =>
  reduceTerms(HOSTMAP.flatMap((e, off) => f(e) ? [bits("AIDX", off, 4)] : []))
    .map((t) => t.join(" & "))
const hostmap: Cell[] = [
  ...[0, 1, 2].map((b) => ({
    pin: 0, name: `HW${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: mapBit((e) => ((e.w >> b) & 1) === 1),
  })),
  ...[0, 1].map((b) => ({
    pin: 0, name: `HL${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: mapBit((e) => ((e.lane >> b) & 1) === 1),
  })),
  { pin: 0, name: "HRO", assertedLow: false, s0: 1, registered: true,
    why: "9.3: PTR and CNT are read-only",
    terms: mapBit((e) => e.ro === true) },
  { pin: 0, name: "HSTAGE", assertedLow: false, s0: 1, registered: true,
    why: "9.4.3: a byte of a multi-byte field goes to the shadow, not to the field",
    terms: reduceTerms([...STAGED].map((off) => bits("AIDX", off, 4)))
      .map((t) => t.join(" & ")) },
  { pin: 0, name: "HCOMMIT", assertedLow: false, s0: 1, registered: true,
    why: "9.4.3: this byte is a field's last, so the shadow lands in one write",
    terms: reduceTerms(Object.keys(COMMIT).map((k) => bits("AIDX", Number(k), 4)))
      .map((t) => t.join(" & ")) },
  /* ⭐ CW0-2 AND CL2 ARE GONE, AND THEY COST NOTHING TO DELETE. For every
   * offset that commits, 9.4.3's commit word is the SAME word 9.3's byte map
   * already puts that offset on - LC commits into w3 and its bytes live in
   * w3, LEN into w5, PER into w4 - so `CW` was a second decode of AIDX
   * computing what `HW` had already computed. And CL2, "only LC's commit
   * reaches lane 2", is `HCOMMIT & HW1`: of the three committing offsets, only
   * LC's has bit 1 of its word set (3 = 011 against 5 = 101 and 4 = 100).
   *
   * Four registered macrocells, deleted, with no package and no pin behind
   * them - which is what paid for HM0/HM1 below. `checkCommitWord` in
   * audio.check.ts asserts the identity rather than trusting this paragraph. */
]

/* ======================= the control outputs ============================ *
 *
 * Everything below is a decode of (WT, T) out of PROGRAM, except W3's, which
 * are gated by WHICH register the host touched and so are written out. `where`
 * is restricted to the four table-driven sequences for exactly that reason. */

const NOHOST = (p: (s: Step) => boolean | undefined): [number, number][] => {
  const out: [number, number][] = []
  for (const wt of [W1, W2, W4, W5, W6]) PROGRAM[wt].forEach((s, t) => { if (p(s)) out.push([wt, t]) })
  return out
}
const on = (p: (s: Step) => boolean | undefined) => onSteps(NOHOST(p))
/** `RUN & WT2 & T == t`, the shape every W3 term has. */
const w3 = (t: number, extra?: string) =>
  `RUN & WT2 & !WT1 & !WT0 & ${bits("T", t, 4).join(" & ")}${extra ? ` & ${extra}` : ""}`

/* -- the state-file address --------------------------------------------- *
 *
 * Walk slots 0-3 read channel {S1,S0} word 0 - the 24 bits 3.3 packs so that
 * the compare needs ONE access. Slot 4 reads $21, the timer's CIANEXT, against
 * the same comparator. Slots 5-7 are the microprogram's. */
const GLOBALSTEPS = NOHOST((s) => s.g !== undefined)
const addr: Cell[] = [
  { pin: 0, name: "GBL", assertedLow: false, s0: 1, registered: false,
    why: "this access is one of the six words at $20",
    terms: ["QTMR", ...onSteps(GLOBALSTEPS), w3(1), w3(3), w3(4),
      w3(0, "HSTAGE")] },
  { pin: 0, name: "SFA5", assertedLow: false, s0: 1, registered: false, terms: ["GBL"] },
  /* ⭐ THE STATE FILE'S OUTPUT ENABLE IS A PIN, and it earns its place twice.
   * It keeps the file off the bus on every write, and it is how ACTRL b5 = 0
   * reaches Paula's hard pan: W5's zeroing steps simply do not turn it on, and
   * SD's pull-downs put $00 into the port register. There is no constant
   * generator on this card. */
  { pin: 0, name: "SFOE", assertedLow: true, s0: 0, registered: false,
    terms: ["QCHAN", "QTMR",
      ...onSteps(NOHOST((s) => s.wr === undefined && s.zeroif === undefined
        && (s.w !== undefined || s.g !== undefined))),
      w3(1, "HCOMMIT & !HRW"), w3(3, "ISSDATA"), w3(5)] },
  { pin: 0, name: "SFA4", assertedLow: false, s0: 1, registered: false,
    terms: ["QCHAN & S1", "RUN & !GBL & !WT2 & WC1",
      "RUN & !GBL & WT2 & !WT0 & AIDX5",
      ...onSteps(NOHOST((s) => s.ch !== undefined && ((s.ch >> 1) & 1) === 1))] },
  { pin: 0, name: "SFA3", assertedLow: false, s0: 1, registered: false,
    terms: ["QCHAN & S0", "RUN & !GBL & !WT2 & WC0",
      "RUN & !GBL & WT2 & !WT0 & AIDX4",
      ...onSteps(NOHOST((s) => s.ch !== undefined && ((s.ch >> 0) & 1) === 1))] },
  ...[0, 1, 2].map((b) => ({
    pin: 0, name: `SFA${b}`, assertedLow: false, s0: 1 as const, registered: false,
    terms: [
      /* slot 4 is $21 */
      ...(b === 0 ? ["QTMR"] : []),
      /* the table's own words */
      ...onSteps(NOHOST((s) => s.w !== undefined && ((s.w >> b) & 1) === 1)),
      ...onSteps(NOHOST((s) => s.g !== undefined && ((s.g >> b) & 1) === 1)),
      /* W3: the shadow at $25, SPTR at $22, or the host's own byte */
      ...(((5 >> b) & 1) === 1 ? [w3(0, "HSTAGE"), w3(1)] : []),
      ...(((2 >> b) & 1) === 1 ? [w3(3), w3(4)] : []),
      w3(0, `!HSTAGE & HW${b}`), w3(5, `HW${b}`), w3(2, `HW${b}`),
    ],
  })),
]

/* -- the byte-lane write enables ---------------------------------------- *
 *
 * ⚠ THEY ARE GATED WITH THE SLOT CLOCK ON THE BOARD, not here. SFA is
 * combinational out of registered state, so it settles a few nanoseconds after
 * the edge, and a /WE asserted for the whole slot would write during that
 * settling. One 74HC00 - an inverter and three gates, exactly - makes each
 * lane's /WE the second half of the slot. The sample RAM needs none: its
 * address is the state file's held read output and is stable across both slots
 * of the access (9.5). */
const lanes: Cell[] = [0, 1, 2].map((l) => ({
  pin: 0, name: `SFWE${l}`, assertedLow: false, s0: 1 as const, registered: false,
  terms: [
    ...on((s) => s.wr?.includes(l)),
    /* W3 step 0: the host's byte, at the lane 9.3 puts it on - and never at a
     * read-only offset, which is what makes PTR and CNT read-only. */
    w3(0, `!HRW & !HRO & !ISAIDX & !ISSDATA & ${bits("HL", l, 2).join(" & ")}`),
    /* W3 step 2: 9.4.3's commit. Lane 2 only for LC, which is the 19-bit one. */
    ...(l < 2 ? [w3(2, "HCOMMIT & !HRW")] : [w3(2, "HCOMMIT & !HRW & HW1")]),
    /* W3 step 4: SPTR's post-increment. */
    w3(4, "ISSDATA"),
  ],
}))

/* -- the adder and its two operand latches ------------------------------- */
const alu: Cell[] = [
  { pin: 0, name: "ALATCK", assertedLow: false, s0: 1, registered: false,
    terms: gated([...on((s) => s.alat), w3(1, "HCOMMIT & !HRW"), w3(3, "ISSDATA")]) },
  { pin: 0, name: "BLATCK", assertedLow: false, s0: 1, registered: false,
    terms: gated(on((s) => s.blat)) },
  { pin: 0, name: "BLATOE", assertedLow: false, s0: 1, registered: false,
    terms: on((s) => s.b === "blat") },
  { pin: 0, name: "ONESOE", assertedLow: false, s0: 1, registered: false,
    why: "B = $FFFF, so A - 1 is A + $FFFF and the card has no inverter",
    terms: on((s) => s.b === "ones") },
  /* The free-running counter drives the shared B bus during the walk, because
   * that is what the '688 compares NEXT against; the microprogram borrows it
   * once, for W6's NEXT = count + PER. */
  /* ⚠ U1 hands the free-running count back on the state file's own bus, for
   * W6's "NEXT is one period from now". The walk does not need it any more:
   * 4.2's comparator moved into U1 WITH the counter on 2026-09-09, so nothing
   * outside this card is comparing and the bus is free. */
  { pin: 0, name: "CNTOE", assertedLow: false, s0: 1, registered: false,
    terms: on((s) => s.count === true) },
  { pin: 0, name: "ACIN", assertedLow: false, s0: 1, registered: false,
    terms: [...on((s) => s.cin), w3(4, "ISSDATA")] },
  { pin: 0, name: "SUMOE", assertedLow: false, s0: 1, registered: false,
    terms: [...on((s) => s.sum), w3(2, "HCOMMIT & !HRW"), w3(4, "ISSDATA")] },
]

/* -- the sample RAM, and the byte that becomes PEND ---------------------- */
const sample: Cell[] = [
  { pin: 0, name: "SROE", assertedLow: false, s0: 1, registered: false,
    terms: [...on((s) => s.srd), w3(3, "ISSDATA & HRW")] },
  { pin: 0, name: "SRWE", assertedLow: false, s0: 1, registered: false,
    terms: [w3(3, "ISSDATA & !HRW")] },
  { pin: 0, name: "SBOE", assertedLow: false, s0: 1, registered: false,
    why: "the fetched byte drives the PEND lane while word 0 is written",
    terms: on((s) => s.sbo) },
]

/* -- SD[18:16], which are U2's own pins ---------------------------------- *
 *
 * 9.5: the pointer is 19 bits and the adder is 16. The top three ride here,
 * captured on the read half and driven back on the write half, incremented
 * when the 16-bit add carried. For CNT it is one bit - the 17th - and the same
 * three pins carry it, because CNT's high bit and PTR's high bits are the same
 * lane of different words. */
const high: Cell[] = [
  { pin: 0, name: "SDHCAP", assertedLow: false, s0: 1, registered: false,
    terms: [...on((s) => s.cap), w3(1, "HCOMMIT & !HRW"), w3(3, "ISSDATA")] },
  { pin: 0, name: "SDHOE", assertedLow: false, s0: 1, registered: false,
    terms: [...on((s) => s.drv), w3(2, "HCOMMIT & !HRW"), w3(4, "ISSDATA")] },
  /* The captured value. */
  ...[0, 1, 2].map((i) => ({
    pin: 0, name: `SDQ${i}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`SDHCAP & SDH${i}`, `SDQ${i} & !SDHCAP`],
  })),

  /* ⛔ 16 ITEM 35, REPAIRED - AND THE MODE NEEDED NO STORAGE AT ALL.
   *
   * The first repair gave the lane two registered mode bits decoded from
   * (WT, T). It was correct and it DID NOT FIT: a registered bit has to hold
   * across the five walk slots between one work slot and the next, that hold
   * term is a sixth product on two more macrocells, and `fit1508.exe` answered
   * `INTERNAL ERROR` on a part already at 128 of 128 with two logic blocks at
   * 40 of 40 fan-in.
   *
   * ⭐ THE MODE IS ALREADY ON THE BOARD. Three control outputs this design has
   * always had distinguish all four cases, on the very step that needs them,
   * with no register and no hold:
   *
   *     ACIN    the carry in   -> the step is an INCREMENT   (PTR + 1, SPTR + 1)
   *     ONESOE  B = $FFFF      -> the step is a DECREMENT    (CNT - 1)
   *     BLATOE  B = the latch  -> the step is CNT = LEN + LEN, so bit 16 IS the carry
   *     none of the three      -> a PASS (a copy, or the host's commit)
   *
   * They are mutually exclusive on every one of the eleven steps that drive
   * the lane, because no step ever carries in AND sums against $FFFF or the
   * latch. ⚠ What the fitted design got wrong was never that the information
   * was missing - it was that it read ONLY `ACIN`, and `ACIN` = 0 covers three
   * of the four cases. Two more literals, and nothing else.
   *
   * A subtract here is A + $FFFF, so its borrow is !ACOUT and not ACOUT. */
  { pin: 0, name: "SDH0", assertedLow: false, s0: 1, registered: false, bidir: true,
    oe: "SDHOE",
    terms: [
      "!ACIN & !ONESOE & !BLATOE & SDQ0",                       // pass
      "ACIN & SDQ0 & !ACOUT", "ACIN & !SDQ0 & ACOUT",           // + carry in
      "ONESOE & SDQ0 & ACOUT", "ONESOE & !SDQ0 & !ACOUT",       // - borrow
      "BLATOE & ACOUT",                                          // bit 16 IS the carry
    ] },
  { pin: 0, name: "SDH1", assertedLow: false, s0: 1, registered: false, bidir: true,
    oe: "SDHOE",
    terms: [
      "!ACIN & !ONESOE & !BLATOE & SDQ1",
      "ACIN & SDQ1 & !ACOUT", "ACIN & SDQ1 & !SDQ0",
      "ACIN & !SDQ1 & ACOUT & SDQ0",
      "ONESOE & SDQ1 & ACOUT", "ONESOE & SDQ1 & SDQ0",
      "ONESOE & !SDQ1 & !ACOUT & !SDQ0",
    ] },
  { pin: 0, name: "SDH2", assertedLow: false, s0: 1, registered: false, bidir: true,
    oe: "SDHOE",
    terms: [
      "!ACIN & !ONESOE & !BLATOE & SDQ2",
      "ACIN & SDQ2 & !ACOUT", "ACIN & SDQ2 & !SDQ0", "ACIN & SDQ2 & !SDQ1",
      "ACIN & !SDQ2 & ACOUT & SDQ1 & SDQ0",
      "ONESOE & SDQ2 & ACOUT", "ONESOE & SDQ2 & SDQ0", "ONESOE & SDQ2 & SDQ1",
      "ONESOE & !SDQ2 & !ACOUT & !SDQ1 & !SDQ0",
    ] },
]

/* -- the host's two latches ---------------------------------------------- */
const port: Cell[] = [
  { pin: 0, name: "PWCK", assertedLow: false, s0: 1, registered: false,
    why: "the posted-write latch takes the host's byte on the synchronised edge",
    terms: gated(["HSTB & !RW"]) },
  { pin: 0, name: "PWOE", assertedLow: false, s0: 1, registered: false,
    terms: [...on((s) => s.pw), w3(0, "!HRW & !ISAIDX & !ISSDATA"), w3(3, "ISSDATA & !HRW")] },
  /* ⚠ NOT SLOT-GATED, and the reason is the whole of why gating exists. Every
   * other latch clock here drives a '574 outside, which needs its rising edge
   * in the middle of the slot - after the address has settled. This one drives
   * a REGISTER INSIDE U1 (9.3's read-back moved there on 2026-09-09), and a
   * register samples on the slot edge, by which time `!SLOTCLK` has gone: the
   * gate that makes an external latch correct makes an internal one never
   * capture at all. It read back zero for every byte on the card. */
  { pin: 0, name: "PFCK", assertedLow: false, s0: 1, registered: false,
    terms: [w3(5), w3(3, "ISSDATA & HRW")] },
  /* ⭐ THE PREFETCH LATCHES WENT TO U1 on 2026-09-09, with the counter and the
   * comparator - three '574s and their three output enables for two pins.
   * What is left here is when to capture (PFCK) and which of the state file's
   * two reachable lanes (PFLANE). U1 drives the host bus off the same
   * bidirectional macrocells AINTREQ and ASTAT already use. */
  { pin: 0, name: "PFLANE", assertedLow: false, s0: 1, registered: false,
    why: "9.3: which byte lane the host's index names",
    terms: ["HL0"] },
  /* W6 reads the free-running count out of U1, a byte at a time. */
  /* 9.2's two status bits, which had no producer at all before U2. */
  /* ⛔ `!AIDXLD`, AND WITHOUT IT THE FIRST INDEX WRITE WEDGED THE CARD.
   *
   * 9.2's busy flag says "a posted write is waiting for the sequencer to
   * retire it". An AIDX load is NOT such a write - AIDXLD loads the index
   * here, and no micro-op is needed - which is exactly why HDUE (the work
   * REQUEST, above) already carries `!AIDXLD`. This did not, so `wr($00)`
   * raised busy with nothing asking the engine to run: `HACK` needs `HDUE`,
   * `HDUE` was never set, and PWBUSY stayed high for ever.
   *
   * A host obeying 9.2 then waited on a flag that could not clear, and a host
   * ignoring 9.2 lost every subsequent byte to the overrun that flag exists to
   * report. audio_tb caught it as PWBUSY = 1 with HDUE = 0.
   *
   * One literal, and it is the same qualification HDUE has always had. */
  /* ⭐ AND `!AIDXLD` GOES, WHICH CLOSES THE SAME HOLE FOR INDEX WRITES. It was
   * there because an index load queued no work and so could never be
   * acknowledged - it would have wedged the flag. Every host access queues a
   * work item now (9.3's "writing AIDX prefetches that entry"), so every one
   * is acknowledged, and covering the index write means a host that honours
   * b6 cannot move `AIDX` under a running sequence either. */
  { pin: 0, name: "PWBUSY", assertedLow: false, s0: 1, registered: true,
    terms: ["HSTB & !RW", "PWBUSY & !HACK"] },
  { pin: 0, name: "PFVALID", assertedLow: false, s0: 1, registered: true,
    terms: ["PFCK", "PFVALID & !AIDXLD & !AINC"] },
]

/* -- 6.2's converter windows, which are the slot phase and nothing else --- *
 *
 * A channel's PEND is on the read bus in its own walk slot; its port register
 * captures it there, and the AD7528 is written four slots later - 6.2's "one
 * frame behind the compare". The four port registers' clocks and their output
 * enables are a 74HC139 on the board decoding S2..S0, so none of that costs a
 * pin here. What DOES cost pins is the chip select and the write strobe, and
 * the write strobe is gated by whether the channel actually hit - which is
 * 3.2's 28x cut in switching beside the analogue section, and the only reason
 * it survives. */
const conv: Cell[] = [
  /* Channel n's port register captured PEND in walk slot n; registers 0 and 1
   * drive their packages' ports in slots 4-7, registers 3 and 2 in slots 0-3,
   * so a frame's two halves are DAC A and DAC B of the same two packages.
   * THREE chip selects cover six packages, because a pair's left and right are
   * always written together out of two different port registers - which is
   * what deletes 10.2.6's 74HC138 lever before it was pulled. */
  { pin: 0, name: "CVBUSY", assertedLow: false, s0: 1, registered: false,
    terms: ["RUN & WT2 & !WT1 & WT0"] },
  { pin: 0, name: "CVB", assertedLow: false, s0: 1, registered: false,
    why: "W5's second half: port registers 3 and 2, DAC B",
    terms: onSteps(NOHOST((s) => s.cvb === true)) },
  { pin: 0, name: "CVOEA", assertedLow: false, s0: 1, registered: false,
    terms: ["!QCHAN & !CVBUSY", "CVBUSY & !CVB"] },
  /* ⚠ CVOEB AND CVAB ARE NOT PINS. CVOEA's complement is exactly "registers 3
   * and 2 drive", and the AD7528's DAC A/B select is the same bit again, so
   * the board takes one output and one inverter where the obvious enumeration
   * charged three pins. */
  /* "this channel's PEND changed in the frame just gone". W1 step 4 is the
   * write that changes it. Gating the strobe on it is 3.2's 28x cut in
   * switching next to the analogue section, and the whole reason the converter
   * is written on events rather than on colour clocks. */
  ...[0, 1, 2, 3].map((n) => ({
    pin: 0, name: `WROTE${n}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [...onSteps(NOHOST((s) => s.pend === true))
      .map((t) => `${t} & ${bits("WC", n, 2).join(" & ")}`),
      `WROTE${n} & !${n < 2 ? "S2" : "QCHAN"} `.trim(),
      `WROTE${n} & !S1`, `WROTE${n} & !S0`],
  })),
  { pin: 0, name: "CVCSS", assertedLow: false, s0: 1, registered: false,
    why: "6.2: the two sample packages, in the half-frame after the hit",
    terms: ["!QCHAN & !CVBUSY & WROTE0", "!QCHAN & !CVBUSY & WROTE1",
      "QCHAN & !CVBUSY & WROTE2", "QCHAN & !CVBUSY & WROTE3"] },
  { pin: 0, name: "CVCSV", assertedLow: false, s0: 1, registered: false,
    terms: onSteps(NOHOST((s) => s.cvstr === "vol")) },
  /* The port registers' load: the walk in slots 0-3, W5 out of a work slot.
   * W5 has to suppress the walk's load while it runs, or the walk would put
   * PEND back into a register W5 has just filled with a volume code. */
  /* ⭐ 10.2.6'S LEVER, PULLED, AND IT IS THE ONLY ONE. Six converter control
   * lines - four port-register clocks and three chip selects - are mutually
   * exclusive: a step that loads a register never strobes a package. So they
   * are ONE 3-bit code through a 74HC138, whose eight outputs are exactly
   * idle, four clocks and three selects, with nothing left over.
   *
   *   0  idle          5  /CS on the two sample packages   (#1, #3)
   *   1  clock reg 0   6  /CS on the two volume packages   (#2, #4)
   *   2  clock reg 1   7  /CS on the two pan packages      (#5, #6)
   *   3  clock reg 2
   *   4  clock reg 3
   *
   * -6 pins for +0 ICs, because the 74HC139 the port-register clocks were
   * going to need is the package this replaces. And the AD7528's /WR is tied
   * low: its latch is transparent while CS and WR are both low and captures on
   * the rising edge of either, so /CS alone is the strobe - one more pin that
   * turns out not to be one. */
  ...[0, 1, 2, 3].map((n) => ({
    pin: 0, name: `CVLD${n}`, assertedLow: false, s0: 1 as const, registered: false,
    terms: [`QCHAN & !CVBUSY & ${bits("S", n, 2).join(" & ")}`,
      ...onSteps(NOHOST((s) => s.cvld === true && s.ch === n))],
  })),
  { pin: 0, name: "CVC0", assertedLow: false, s0: 1, registered: false,
    terms: ["CVLD0", "CVLD2", "CVCSS"] },
  { pin: 0, name: "CVC1", assertedLow: false, s0: 1, registered: false,
    terms: ["CVLD1", "CVLD2", "CVCSV"] },
  { pin: 0, name: "CVC2", assertedLow: false, s0: 1, registered: false,
    terms: ["CVLD3", "CVCSS", "CVCSV"] },
  /* A host write that lands on VOL (offset 7) or PAN (offset 10) asks for a
   * W5. Both are cleared by the one sequence, because W5 writes all eight
   * halves and there is no point running it twice. */
  { pin: 0, name: "VDIRTY", assertedLow: false, s0: 1, registered: true,
    terms: [w3(0, "!HRW & !HRO & !ISAIDX & !ISSDATA & !AIDX3 & AIDX2 & AIDX1 & AIDX0"),
      "VDIRTY & !VACK"] },
  { pin: 0, name: "VACK", assertedLow: false, s0: 1, registered: false,
    terms: ["START & !RSTANY & !TDUE & !DUEANY & !HDUE"] },
]

/* -- 8.1's six sources, encoded ------------------------------------------ *
 *
 * 10.2.6's third lever: a 3-bit source code rather than six lines, decoded
 * back into SET0-5 on U1. Code 7 is "nothing", which is the idle state. */
const irq: Cell[] = [
  ...[0, 1, 2, 3].map((n) => ({
    pin: 0, name: `FIRE${n}`, assertedLow: false, s0: 1 as const, registered: false,
    why: "this channel's buffer ran out - 1 requirement 7",
    terms: [`ENDNOW & ${bits("WC", n, 2).join(" & ")}`],
  })),
  { pin: 0, name: "FIRE4", assertedLow: false, s0: 1, registered: false,
    terms: onSteps(NOHOST((s) => s.set === 4)) },
  { pin: 0, name: "FIRE5", assertedLow: false, s0: 1, registered: false,
    why: "8.1 bit 5: a posted write arrived while the previous had not retired",
    terms: ["HSTB & !RW & PWBUSY"] },
  { pin: 0, name: "NOFIRE", assertedLow: false, s0: 1, registered: false,
    terms: ["!FIRE0 & !FIRE1 & !FIRE2 & !FIRE3 & !FIRE4 & !FIRE5"] },
  { pin: 0, name: "SETA", assertedLow: false, s0: 1, registered: false,
    terms: ["FIRE1", "FIRE3", "FIRE5", "NOFIRE"] },
  { pin: 0, name: "SETB", assertedLow: false, s0: 1, registered: false,
    terms: ["FIRE2", "FIRE3", "NOFIRE"] },
  { pin: 0, name: "SETC", assertedLow: false, s0: 1, registered: false,
    terms: ["FIRE4", "FIRE5", "NOFIRE"] },
]

/* Slot-phase decodes, from U1's three counter bits. Taking S0-S2 rather than
 * five decoded phases is three pins instead of five, and U2 has 68. */
const phase: Cell[] = [
  { pin: 0, name: "QCHAN", assertedLow: false, s0: 1, registered: false, terms: ["!S2"] },
  { pin: 0, name: "QTMR", assertedLow: false, s0: 1, registered: false,
    terms: ["S2 & !S1 & !S0"] },
]

export const aseqCells: Cell[] = [
  ...phase, ...engine, ...sources, ...host, ...hostmap,
  ...addr, ...lanes, ...alu, ...sample, ...high, ...port, ...conv, ...irq,
]
