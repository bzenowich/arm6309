/* The audio card's five GAL22V10s - audio.md §9.5's table, fitted.
 *
 * §9.5 assigns them: GAL 1 the slot sequencer, GAL 2 address and decode, GAL 3
 * DMACON and the tempo prescale, GAL 4 INTENA, GAL 5 INTREQ and its pending
 * register. That section arrived as a design-review correction - the previous
 * budget asked three GALs to hold the sequencer AND 41 flops of host-visible
 * counter, and "they do not fit, and the document never said where they were".
 * The counters then moved into the state file, which is why this is five parts.
 */

import { counterTerms } from "./jedec/counter"
import { place } from "./jedec/place"
import type { Cell, Design } from "./jedec/assemble"

/* Paula's set/clear register, §9.2: bit 7 of the written byte says set or
 * clear, the low bits name which, and unnamed bits are untouched. */
const setClearTerms = (strobe: string, bit: number, q: string) => [
  `${strobe} & D7 & D${bit}`,
  `${q} & !${strobe}`, `${q} & D7`, `${q} & !D${bit}`,
]

/* ===================== GAL 1 - aseq: the slot walk (§3.1) ================ */
/* ⭐ FOUR BITS, and the fourth is the frame parity. S0-S2 walk the eight slots
 * of a colour clock (3.1); S3 toggles once per colour clock, and it is the one
 * signal allowed to move an AD7528's DAC A/B select or a converter port
 * register's /OE - audio.md 6.2, 16 item 43. */
const SLOT = ["S0", "S1", "S2", "S3"]
const slotCount = counterTerms({ bits: SLOT })
const aseqCells: Cell[] = [
  ...SLOT.map((name, i) => ({
    pin: 0, name, assertedLow: false, s0: 1 as const, registered: true, terms: slotCount[i],
  })),
  /* S3's complement, as its own register so both edges leave on the same
   * clock: the /OE of port registers 3 and 2 (S3 itself is the /OE of 0 and 1).
   * Active low, so it comes out of reset with registers 3 and 2 OFF the port -
   * S3 resets to 0, which is 0 and 1 driving - and the two can never fight. */
  { pin: 0, name: "OEB", assertedLow: true, s0: 0, registered: true, terms: slotCount[3],
    why: "6.2: port registers 3 and 2 drive the converters, in DAC B frames" },
  /* The colour clock is the frame boundary and the period reference for the
   * whole card (§4.1). */
  { pin: 0, name: "CCLK", assertedLow: false, s0: 1, registered: false, terms: ["S2 & S1 & S0"] },
  /* Slots 0-3 run unconditionally every colour clock, which is what makes the
   * design jitter-free: a channel's sample transition lands on its true Paula
   * boundary, never on whenever the sequencer got round to it.
   *
   * ⛔ THE FOUR SLOT DECODES WERE HERE AND NOTHING READ THEM - deleted
   * 2026-09-10, audio.md 16 item 42. CHANSLOT, TMRSLOT, HOSTSLOT and DEFSLOT
   * decoded S2:S0 into the five phases; the deferred-work queue moved to U2 on
   * 2026-09-09 and audio.cpld.ts records what went with it - "U2 takes the
   * three counter bits and decodes the five phases ITSELF, three pins instead
   * of five". The pins went and the cells stayed, on a card where U2 is at 128
   * of 128 and U1 at 62 of 64 I/O. check:reach is what noticed. */
  /* ⚠ The deferred-work queue moved to U2 on 2026-09-09 - it is the work
   * scheduler of 10.2.3 and it needs the microprogram beside it. */
]
const aseqPins = place(aseqCells, [14, 15, 16, 17, 18, 19, 20, 21, 22, 23])
export const aseqDesign: Design = {
  name: "aseq", partNo: "ARM6309-UA1", location: "audio card - slot sequencer",
  supersededBy: "audio.md 10.1 - the audio card is 1 x ATF1508AS",
  signature: "A6309A1", clockPin: 1,
  inputs: [{ name: "RESET", pin: 2, activeLow: true }],
  cells: aseqCells.map((c) => ({ ...c, pin: aseqPins[c.name] })), ar: "RESET",
}

/* ============= GAL 2 - adec: the host decode (§9.2's sixteen bytes) ====== */
/* §9.5: "the address mux of GAL 2 collapses from a mux into a chip-enable",
 * because the sample-RAM address now has one source - the state file's read
 * bus - and nothing else drives it. */
const reg = (n: number) =>
  `SEL & ${n & 8 ? "" : "!"}A3 & ${n & 4 ? "" : "!"}A2 & ${n & 2 ? "" : "!"}A1 & ${n & 1 ? "" : "!"}A0`
const adecCells: Cell[] = [
  /* ⛔ WAIDX WENT THE SAME WAY - deleted 2026-09-10. "A host write to AIDX",
   * decoded here and read by nothing; U2 decodes it itself as ISAIDX, and that
   * is the copy 9.3's prefetch rule is built on. */
  { pin: 0, name: "WDMACON", assertedLow: false, s0: 1, registered: false, terms: [`${reg(0x2)} & !RW`] },
  { pin: 0, name: "WINTENA", assertedLow: false, s0: 1, registered: false, terms: [`${reg(0x3)} & !RW`] },
  { pin: 0, name: "WINTREQ", assertedLow: false, s0: 1, registered: false, terms: [`${reg(0x4)} & !RW`] },
  { pin: 0, name: "WCTRL", assertedLow: false, s0: 1, registered: false, terms: [`${reg(0x5)} & !RW`] },
  { pin: 0, name: "RINTREQ", assertedLow: false, s0: 1, registered: false, terms: [`${reg(0x4)} & RW`] },
  { pin: 0, name: "RASTAT", assertedLow: false, s0: 1, registered: false, terms: [`${reg(0xa)} & RW`] },
  /* HOST ACCESS REQUESTS, NOT CHIP ENABLES. These were `SFCE`/`SRCE`, active
   * low, until 2026-09-09 - two names that read as "state-file chip enable"
   * and "sample-RAM chip enable" on a card whose sequencer drives both
   * memories every slot. Two drivers on one /CE is design-review2.md V-2's
   * shape exactly (one name, two meanings), so they are renamed to what they
   * are: the host is asking for an access, and the sequencer retires it in
   * slot 5 (audio.md 9.3). Active high, because nothing downstream of them is
   * a memory pin. */
  /* ⚠ `HSFREQ`, `HSRREQ` and `HOSTREQ` left on 2026-09-09. U2 decodes +$1 and
   * +$9 for itself out of the offset it latches at 9.4.4's leading edge, which
   * is the only capture on the card that happens while the address is still
   * there. audio.md 10.2. */
]
const adecPins = place(adecCells, [14, 15, 16, 17, 18, 19, 20, 21, 22, 23])
export const adecDesign: Design = {
  name: "adec", partNo: "ARM6309-UA2", location: "audio card - host decode",
  supersededBy: "audio.md 10.1 - the audio card is 1 x ATF1508AS",
  signature: "A6309A2",
  inputs: [{ name: "SEL", pin: 1 }, { name: "A0", pin: 2 }, { name: "A1", pin: 3 },
    { name: "A2", pin: 4 }, { name: "A3", pin: 5 }, { name: "RW", pin: 6 }, { name: "E", pin: 7 }],
  cells: adecCells.map((c) => ({ ...c, pin: adecPins[c.name] })),
}

/* ========== GAL 3 - admat: DMACON and the tempo prescale (§8.2) ========== */
const PRE = ["P0", "P1", "P2"]
/* colour clock / 5 = 709,379 Hz - the Amiga's CIA-B clock itself and not an
 * approximation, so every replayer's Fxx arithmetic transfers unchanged. The
 * terminal count is 4 and the counter never reaches 5, so P2 decodes it alone. */
const preCount = counterTerms({ bits: PRE, enable: "CCLK", terminal: "P2" })
const admatCells: Cell[] = [
  ...[0, 1, 2, 3].map((i) => ({
    pin: 0, name: `DMAEN${i}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: setClearTerms("WDMACON", i, `DMAEN${i}`),
  })),
  ...PRE.map((name, i) => ({
    pin: 0, name, assertedLow: false, s0: 1 as const, registered: true, terms: preCount[i],
  })),
  /* ⛔ CIACLK WAS HERE, ON A PIN, AND NOTHING TOOK IT - deleted 2026-09-10.
   *
   * 8.2's tempo clock is colour clock / 5, and the timer is COUNTED BY THE
   * MICROCODE against the shared adder - "a ÷5 prescale driving a 16-bit count
   * that the shared adder increments every five". So this output was the
   * prescale's edge presented to a card that does its counting elsewhere.
   *
   * The pin it freed was earmarked for 16 item 40's VOL4 select, which is not
   * needed: the replayer writes the converter's code instead. CCLK stays - 4.1 says a scope wants the
   * colour clock, and that sentence is why it is a pin at all; there was never
   * an equivalent one for this. */
]
const admatPins = place(admatCells, [14, 15, 16, 17, 18, 19, 20, 21, 22, 23])
export const admatDesign: Design = {
  name: "admat", partNo: "ARM6309-UA3", location: "audio card - DMACON and tempo prescale",
  supersededBy: "audio.md 10.1 - the audio card is 1 x ATF1508AS",
  signature: "A6309A3", clockPin: 1,
  inputs: [{ name: "RESET", pin: 2, activeLow: true }, { name: "WDMACON", pin: 3 },
    { name: "CCLK", pin: 4 }, ...[0, 1, 2, 3, 7].map((b, i) => ({ name: `D${b}`, pin: 5 + i }))],
  cells: admatCells.map((c) => ({ ...c, pin: admatPins[c.name] })), ar: "RESET",
}

/* ================== GAL 4 - aintena: INTENA (§8.1) ====================== */
const aintenaCells: Cell[] = [0, 1, 2, 3, 4, 5].map((i) => ({
  pin: 0, name: `ENA${i}`, assertedLow: false, s0: 1 as const, registered: true,
  terms: setClearTerms("WINTENA", i, `ENA${i}`),
}))
const aintenaPins = place(aintenaCells, [14, 15, 16, 17, 18, 19, 20, 21, 22, 23])
export const aintenaDesign: Design = {
  name: "aintena", partNo: "ARM6309-UA4", location: "audio card - INTENA",
  supersededBy: "audio.md 10.1 - the audio card is 1 x ATF1508AS",
  signature: "A6309A4", clockPin: 1,
  inputs: [{ name: "RESET", pin: 2, activeLow: true }, { name: "WINTENA", pin: 3 },
    ...[0, 1, 2, 3, 4, 5, 7].map((b, i) => ({ name: `D${b}`, pin: 4 + i }))],
  cells: aintenaCells.map((c) => ({ ...c, pin: aintenaPins[c.name] })), ar: "RESET",
}

/* ====== GAL 5 - aintreq: INTREQ, its pending register, /FIRQ (§9.4.5) ====
 *
 * THIS IS THE ONE THAT DOES NOT FIT, and §9.5's own table says so without
 * drawing the conclusion: it budgets "INTREQ (+ 6-bit pending register) | 12"
 * for one GAL22V10, and a GAL22V10 has ten macrocells. With §8.1's /FIRQ it is
 * thirteen.
 *
 * The obvious repair is to split the pending register onto its own part, and
 * that does not work either - it moves the problem from macrocells to pins.
 * Both attempts are built below and audio.check.ts asserts that both are
 * refused, with the fitter's own arithmetic as the evidence.
 */

const reqCells = (withFirq: boolean, pendLocal: boolean): Cell[] => [
  ...[0, 1, 2, 3, 4, 5].map((i) => ({
    pin: 0, name: `REQ${i}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`WINTREQ & D7 & D${i}`, `PEND${i} & MERGE`,
      `REQ${i} & !WINTREQ`, `REQ${i} & D7`, `REQ${i} & !D${i}`],
  })),
  ...(pendLocal ? [0, 1, 2, 3, 4, 5].map((i) => ({
    pin: 0, name: `PEND${i}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`SET${i}`, `PEND${i} & !MERGE`],
  })) : []),
  /* §8.1: /FIRQ is wire-ORed, so the pin drives low or floats and never high.
   * On a GAL22V10 that is the output-enable idiom, and audio.md costs a 74HC07
   * beside it because a GAL's totem-pole pin cannot do the wire-OR itself. */
  ...(withFirq ? [{ pin: 0, name: "FIRQ", assertedLow: true, s0: 1 as const,
    registered: false, terms: [] as string[], oe: "FIRQANY" }] : []),
]

const dataPins = (from: number) =>
  [0, 1, 2, 3, 4, 5, 7].map((b, i) => ({ name: `D${b}`, pin: from + i }))

/** §9.5 as written: everything on one part. Refused on MACROCELLS. */
export const buildAintreqWhole = (): Design => {
  const cells = reqCells(true, true)
  const pins = place(cells, [14, 15, 16, 17, 18, 19, 20, 21, 22, 23])
  return {
    name: "aintreq", partNo: "ARM6309-UA5", location: "audio card - INTREQ and pending",
    signature: "A6309A5", clockPin: 1,
    inputs: [{ name: "RESET", pin: 2, activeLow: true }, { name: "WINTREQ", pin: 3 },
      { name: "MERGE", pin: 4 }, { name: "FIRQANY", pin: 5 }, ...dataPins(6),
      ...[0, 1, 2, 3, 4, 5].map((i) => ({ name: `SET${i}`, pin: 13 + i }))],
    cells: cells.map((c) => ({ ...c, pin: pins[c.name] })), ar: "RESET",
  }
}

/** The repair: pending on its own part. Refused on PINS - the six PEND bits
 *  stop being internal and there is nowhere on a 22V10 to receive them
 *  alongside six data bits and the control. */
export const buildAintreqSplit = (): Design => {
  const cells = reqCells(true, false)
  const pins = place(cells, [14, 15, 16, 17, 18, 19, 20, 21, 22, 23])
  return {
    name: "aintreq-split", partNo: "ARM6309-UA5", location: "audio card - INTREQ only",
    signature: "A6309A5", clockPin: 1,
    /* Eleven dedicated pins and three macrocells left over is fourteen holes;
     * this needs seventeen. The assignment below fills every legal pin and
     * still leaves three signals with nowhere to go. */
    inputs: [{ name: "RESET", pin: 2, activeLow: true }, { name: "WINTREQ", pin: 3 },
      { name: "MERGE", pin: 4 }, { name: "FIRQANY", pin: 5 }, ...dataPins(6),
      ...[0, 1, 2].map((i) => ({ name: `PEND${i}`, pin: 13 + i })),
      ...[3, 4, 5].map((i) => ({ name: `PEND${i}`, pin: 21 + i - 3 }))],
    cells: cells.map((c) => ({ ...c, pin: pins[c.name] })), ar: "RESET",
  }
}

/** The half that does fit, kept so the census can count it. */
const apendCells: Cell[] = [0, 1, 2, 3, 4, 5].map((i) => ({
  pin: 0, name: `PEND${i}`, assertedLow: false, s0: 1 as const, registered: true,
  terms: [`SET${i}`, `PEND${i} & !MERGE`],
}))
const apendPins = place(apendCells, [14, 15, 16, 17, 18, 19, 20, 21, 22, 23])
export const apendDesign: Design = {
  name: "apend", partNo: "ARM6309-UA6", location: "audio card - INTREQ pending register",
  supersededBy: "audio.md 10.1 - the audio card is 1 x ATF1508AS",
  signature: "A6309A6", clockPin: 1,
  inputs: [{ name: "RESET", pin: 2, activeLow: true }, { name: "MERGE", pin: 3 },
    ...[0, 1, 2, 3, 4, 5].map((i) => ({ name: `SET${i}`, pin: 4 + i }))],
  cells: apendCells.map((c) => ({ ...c, pin: apendPins[c.name] })), ar: "RESET",
}
