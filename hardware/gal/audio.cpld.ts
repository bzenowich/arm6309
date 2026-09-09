/* The audio card as one ATF1508AS - audio.md §10.1, case A.
 *
 * Six GAL22V10 designs plus the three packages a CPLD absorbs, folded into one
 * part. Nothing is retyped: the equations are the same Cell objects
 * audio.check.ts exercises, so the CPLD and the GAL fits have one origin.
 *
 * Three things stop being pins the moment the parts merge, and two of them
 * were inputs the GAL version had to be told:
 *
 *   FIRQANY  the GALs could not compute it - REQ is on one part and ENA on
 *            another, so §8.1's condition had to arrive as a pin. Here it is
 *            six product terms.
 *   MERGE    §9.4.5 wants the colour clock after the synchronised read strobe
 *            deasserts. The synchronisers were a '174 and the read strobe was
 *            on the decode GAL; now both are here.
 *   PEND0-5  the six bits whose crossing is what made the interrupt block
 *            unfittable on a 22V10 in either arrangement.
 */

import { merge, toCupl, type Merged } from "./jedec/cupl"
import type { Cell } from "./jedec/assemble"
import {
  aseqDesign, adecDesign, admatDesign, aintenaDesign, apendDesign, buildAintreqSplit,
} from "./audio.jedec"

/* The '273 that holds ACTRL (§9.2). On the card it clocked on the write
 * strobe; here every register shares the slot clock, so it becomes an enabled
 * hold. b0 LED filter, b1 bypass, b2 NTSC, b3 raw volume, b4 8-channel,
 * b5 pan, b6 tempo-timer enable, b7 master enable. */
const ctrl: Cell[] = [0, 1, 2, 3, 4, 5, 6, 7].map((i) => ({
  pin: 0, name: `CTRL${i}`, assertedLow: false, s0: 1 as const, registered: true,
  terms: [`WCTRL & D${i}`, `CTRL${i} & !WCTRL`],
}))

/* The '174's three two-flop synchronisers (§9.4.4). A host strobe is
 * asynchronous to the 28.37516 MHz slot clock and has to be caught twice
 * before the sequencer may act on it. */
const sync = (name: string, from: string): Cell[] => [
  { pin: 0, name: `${name}1`, assertedLow: false, s0: 1, registered: true, terms: [from] },
  { pin: 0, name: `${name}2`, assertedLow: false, s0: 1, registered: true, terms: [`${name}1`] },
]

const merged: Cell[] = [
  ...ctrl,
  ...sync("SYNCH", "HOSTREQ"),   // the posted write / prefetch request
  ...sync("SYNCR", "RINTREQ"),   // the AINTREQ read strobe
  ...sync("SYNCS", "SFCE"),      // state-file access
  /* §9.4.5: a request bit set by the slot logic merges into INTREQ on a colour
   * clock, and NOT while a host read of AINTREQ is in flight - so a set
   * arriving during a read is neither lost nor half-seen.
   *
   * ⛔ IT READ `CCLK & SYNCR2 & !SYNCR1` UNTIL 2026-09-09, which is the
   * TRAILING EDGE of a host read rather than the absence of one, and it made
   * the card's interrupts undeliverable in two independent ways:
   *
   *   - nothing merged unless the host READ AINTREQ. A channel that exhausted
   *     its buffer set PENDn, PENDn stayed set, REQn never rose, FIRQANY never
   *     saw it and /FIRQ was never asserted. §1 requirement 7 - the per-channel
   *     end-of-buffer interrupt - was not delivered at all;
   *   - and even then only by coincidence. `SYNCR2 & !SYNCR1` is one slot wide
   *     and CCLK is one slot in eight, so whether a read merged anything
   *     depended on which slot it happened to deassert on. Measured over the
   *     phase: 2 of 16.
   *
   * docs/design-review2.md A-2. The repair is one literal, and it is what
   * §9.4.5's own wording describes: merge on the colour clock, suppressed
   * while a read is in flight. */
  { pin: 0, name: "MERGE", assertedLow: false, s0: 1, registered: false,
    why: "9.4.5: every colour clock EXCEPT while a host read is in flight",
    terms: ["CCLK & !SYNCR2 & !SYNCR1"] },
  /* §8.1's condition, which the GAL split could not form. */
  { pin: 0, name: "FIRQANY", assertedLow: false, s0: 1, registered: false,
    terms: [0, 1, 2, 3, 4, 5].map((i) => `REQ${i} & ENA${i}`) },
  { pin: 0, name: "NEWREQ", assertedLow: false, s0: 1, registered: false,
    terms: ["SYNCH2 & !SYNCH1"] },
]

const EXTERNAL = new Set([
  "S0", "S1", "S2", "CCLK",
  "CHANSLOT", "TMRSLOT", "HOSTSLOT", "DEFSLOT",
  "SFCE", "SRCE",
  "DMAEN0", "DMAEN1", "DMAEN2", "DMAEN3",
  "CIACLK", "FIRQ", "RASTAT",
  "CTRL0", "CTRL1", "CTRL2", "CTRL3", "CTRL4", "CTRL5", "CTRL6", "CTRL7",
])

export const audioCpld: Merged = merge(
  [aseqDesign, adecDesign, admatDesign, aintenaDesign, apendDesign, buildAintreqSplit()],
  merged,
  {
    name: "audio", partNo: "ARM6309-UA0", location: "audio card",
    device: "f1508ispplcc84", external: EXTERNAL,
    /* 28.37516 MHz, the Amiga PAL master crystal (4.1) - eight 35.24 ns slots
     * per colour clock, and everything on the card is referred to it. */
    clock: "SLOTCLK",
  },
)

export const audioCuplSource = () => toCupl(audioCpld)
