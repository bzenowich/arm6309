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

/* ⭐ 8.1's SIX SOURCES ARRIVE AS A 3-BIT CODE, not as six pins - 10.2.6's
 * lever, and this is its other half. U2 is the part with no pins to spare;
 * U1 is at 57 of 64 and has cells. Code 7 is "nothing", which is the idle
 * state, so a quiet card drives a constant and the decode never glitches. */
const setDecode: Cell[] = [0, 1, 2, 3, 4, 5].map((i) => ({
  pin: 0, name: `SET${i}`, assertedLow: false, s0: 1 as const, registered: false,
  terms: [[2, 1, 0].map((b) => `${(i >> b) & 1 ? "" : "!"}${"CBA"[2 - b]}`)
    .map((x) => x.replace(/([!]?)([ABC])/, "$1SET$2")).join(" & ")],
}))

const merged: Cell[] = [
  ...ctrl,
  ...setDecode,
  ...sync("SYNCR", "RINTREQ"),   // the AINTREQ read strobe
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
  /* ⚠ THE HOST HANDSHAKE LEFT THIS PART ON 2026-09-09, for U2. U1's version
   * synchronised "an access happened" and produced its TRAILING edge - which
   * is after E has fallen and the address may already be gone, so WHICH
   * register was touched was never captured anywhere. U2 latches the offset
   * and R/W on the LEADING synchronised edge instead (10.2), which is the only
   * place that can act on it. `SYNCH`, `NEWREQ`, `DEFREQ`, `DEFACK`,
   * `HOSTREQ`, `SYNCS`, `HSFREQ` and `HSRREQ` went with it.
   *
   * The AINTREQ read synchroniser stays: 9.4.5's MERGE is U1's own. */

  /* ================== 9.1's decode, which nothing produced ================
   *
   * ⛔ `SEL` WAS A PIN AND NOTHING ON THE CARD DROVE IT until 2026-09-09.
   * audio.md 9.1 says the card "completes its own decode from A0-A6", and
   * hardware/cards/audio.circuit.tsx wires neither the address bus nor a
   * select to U1 - so the sixteen bytes at $FF40 were decoded by a signal that
   * exists in no design file and on no board. Same shape as design-review2.md
   * V-3's LGRANT.
   *
   * ⚠ AND SEVEN BITS, NOT SIX. The geographic window widened to 128 bytes
   * ($FF00-$FF7F) on 2026-09-08, so /IOSEL no longer implies A6 and a card
   * that matches only A5..A0 answers at its base AND 64 bytes below it - two
   * cards driving D0-D7 at once, silently. gal/regfile.jedec.ts carries the
   * same three literals for the video card's $FF60 window (IOSEL & A6 & A5).
   * Audio is $FF40-$FF4F: A6 = 1, A5 = 0, A4 = 0, and A3..A0 pick the
   * register. */
  { pin: 0, name: "SEL", assertedLow: false, s0: 1, registered: false,
    why: "9.1: $FF40-$FF4F out of the 128-byte geographic window - SEVEN bits",
    terms: ["IOSEL & A6 & !A5 & !A4"] },

  /* ================= 9.3's read-back path, which was absent ==============
   *
   * ⛔ THE CARD COULD NOT BE READ. audio.md 9.3 says "every other readable
   * byte on the card - ASTAT, AINTREQ, the ACTRL shadow - is a CPLD output,
   * three-state too", and deletes a '245 on that argument. It is the right
   * argument and it was never built: D0-D7 were INPUTS of this part and
   * nothing anywhere drove the host data bus with AINTREQ or ASTAT. The read
   * strobes existed (RINTREQ, RASTAT); the data did not.
   *
   * The repair is the pin type the argument assumed: an ATF1508AS I/O
   * macrocell is bidirectional, so D0-D7 stay the same eight pins and gain an
   * output driver and an .oe. Zero pins, eight macrocells.
   *
   * ⚠ ADATA/SDATA ARE NOT HERE. Those two come off the '574 prefetch latch
   * (9.3), which has its own three-state outputs; what this part owes it is
   * the enable, PFOE below. */
  { pin: 0, name: "HRD", assertedLow: false, s0: 1, registered: false,
    why: "a host read this part answers: AINTREQ or ASTAT, inside E",
    terms: ["RINTREQ & E", "RASTAT & E"] },
  ...[
    /* bit,  AINTREQ (+$4)     ASTAT (+$A)  - 9.2's two readable registers */
    ["D0", "REQ0", "DMAEN0"],
    ["D1", "REQ1", "DMAEN1"],
    ["D2", "REQ2", "DMAEN2"],
    ["D3", "REQ3", "DMAEN3"],
    ["D4", "REQ4", "CTRL6"],    // b4: the tempo timer is running (8.2's enable)
    ["D5", "REQ5", null],       // b5: reserved, reads 0
    ["D6", null, "PWBUSY"],     // b6: posted-write busy   (9.2)
    ["D7", null, "PFVALID"],    // b7: prefetch valid      (9.2)
  ].map(([name, req, stat]) => ({
    pin: 0, name: name as string, assertedLow: false, s0: 1 as const, registered: false,
    bidir: true,
    terms: [
      ...(req ? [`RINTREQ & ${req}`] : []),
      ...(stat ? [`RASTAT & ${stat}`] : []),
    ],
    oe: "HRD",
  })),

  /* ⚠ THE PREFETCH ENABLE MOVED TO U2 on 2026-09-09, and it became three.
   * 9.3's read-back path is one '574 per state-file byte lane, and which lane
   * a host byte lives on is a function of AIDX - which is U2's register,
   * because the sequencer cannot read the index out of the file whose address
   * the index computes. audio.md 10.2.1. */
]

/* What leaves U1. Everything here that is not a memory or converter control
 * goes to U2, the sequencer (audio.md 10.2): the slot phase, the colour clock,
 * the mode bits, the DMA enables, the host's two access requests, the decoded
 * select and the deferred-work request. RASTAT stopped being a pin on
 * 2026-09-09 - it is the ASTAT read strobe and its only consumer is the D-bus
 * driver above, which is now on this part. */
const EXTERNAL = new Set([
  /* U2 takes the three counter bits and decodes the five phases itself -
   * three pins instead of five, on the part that has none to spare. CCLK
   * stays a pin because it is 4.1's colour clock and a scope wants it. */
  "S0", "S1", "S2", "CCLK",
  "SEL",
  "D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7",
  "DMAEN0", "DMAEN1", "DMAEN2", "DMAEN3",
  "CIACLK", "FIRQ",
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
