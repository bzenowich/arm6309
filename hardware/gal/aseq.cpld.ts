/* U2 - the audio card's sequencer, as one ATF1508AS.  audio.md 10.2.
 *
 * U1 (audio.cpld.ts) is the host register block: the decode, ADMACON, AINTENA,
 * AINTREQ and its pending register, /FIRQ, ACTRL, the read-back path and the
 * slot counter. This is everything that makes sound.
 *
 * WHY TWO PARTS, in one line: the crossing between them is ~30 nets and costs
 * 60 pins, and merging them costs ~140 logic cells against the 128 an
 * ATF1508AS has. The split spends pins to save cells; there is no arrangement
 * of this card on one die.
 */

import { merge, toCupl, type Merged } from "./jedec/cupl"
import { aseqCells } from "./aseq.jedec"

/** What leaves U2. Everything else is the microprogram's own state. */
const EXTERNAL = new Set([
  /* the state file */
  "SFA0", "SFA1", "SFA2", "SFA3", "SFA4", "SFA5",
  "SFOE", "SFWE0", "SFWE1", "SFWE2",
  /* the sample RAM. Its /WE needs no clock gating: the address is the state
   * file's held read output and is stable across both slots of the access. */
  "SROE", "SRWE",
  /* the adder, its two operand latches and the three things that may drive the
   * shared B bus - the PER latch, the tied-high '244 pair, and the free-running
   * counter the '688 is comparing against. */
  "ALATCK", "BLATCK", "BLATOE", "ONESOE", "CNTOE", "ACIN", "SUMOE",
  /* the sample byte, on its way to PEND */
  "SROE", "SBOE",
  /* SD[18:16] - 9.5's nineteenth bit and CNT's seventeenth */
  "SDH0", "SDH1", "SDH2",
  /* 6.2's converters */
  "CVOEA", "CVC0", "CVC1", "CVC2",
  /* 9.3's host latches */
  "PFLANE", "PFCK", "PWCK", "PWOE",
  /* 8.1's six sources, as a 3-bit code - 10.2.6's lever, decoded on U1 */
  "SETA", "SETB", "SETC",
  /* 9.2's two status bits */
  "PWBUSY", "PFVALID",
])

const built = merge([], aseqCells, {
  name: "aseq", partNo: "ARM6309-UA7", location: "audio card - sequencer",
  device: "f1508ispplcc84", external: EXTERNAL,
  clock: "SLOTCLK", ar: "RESET",
})

/* RESET is the asynchronous clear and no equation reads it, so `merge` - which
 * builds the input list out of the literals the equations use - never sees it.
 * On U1 it came in with the GAL designs' own pin lists; U2 has none, so it is
 * declared here. It is the ATF1508AS's global clear, as on U1. */
export const aseqCpld: Merged = {
  ...built, inputs: [{ name: "RESET", activeLow: true }, ...built.inputs],
}

export const aseqCuplSource = () => toCupl(aseqCpld)
