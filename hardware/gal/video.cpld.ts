/* The video card as two ATF1508AS - graphics.md §10.1.6's partition.
 *
 * Ten GAL22V10 fits, superseded as deliverables but kept as the derivation,
 * folded into two parts. The split is the one §10.1.6 proposes and it is
 * chosen for a timing reason rather than a capacity one: a net that crosses
 * between packages costs a tPD - 15 ns at the -15 grade against a 39.7 ns dot
 * period - so the dot-rate paths have to stay together.
 *
 *   vaddr   the address datapath: both counter sets and the mux between them.
 *           17 of its outputs are the framebuffer address and nothing else
 *           leaves, which is what makes it the natural cut.
 *   vctrl   everything that decides: sync, sequencer, span control, arbiter,
 *           and CTRL. Every dot-rate signal - the phase counter, SLOTTICK,
 *           FCLK0..3, MUXSEL - is on this part with whatever it clocks.
 *
 * THE ADDRESS MUX EXISTS ONLY HERE. On GALs the scan pair and the WPTR pair
 * tri-state onto a shared bus and it costs nothing; inside one die two
 * macrocells cannot drive one pin, so the 17 address outputs are 17 further
 * macrocells fed by both counter sets, and both sets become buried. That is
 * the correction §10.1.2's census carries, and it is the single biggest line
 * in this part's budget.
 */

import { merge, rename, toCupl, type Merged } from "./jedec/cupl"
import type { Cell } from "./jedec/assemble"
import { hgenDesign, vgenDesign, vdecDesign } from "./sync.jedec"
import { hadrDesign, vadrDesign } from "./scan.jedec"
import { arbDesign, wcolDesign, wrowDesign } from "./access.jedec"
import { seqphDesign } from "./seqph.jedec"
import { seqctlDesign } from "./seqctl.jedec"

/* ---- part A: the address datapath -------------------------------------- */

/* Both fits call their outputs A2..A18. They are different nets. */
const scanMap = Object.fromEntries(
  [...Array(19).keys()].map((i) => [`A${i}`, `SA${i}`]))
const wptrMap = Object.fromEntries(
  [...Array(19).keys()].map((i) => [`A${i}`, `WA${i}`]))

/* The framebuffer sees the scan address shifted down two - A1..A0 are the
 * 4-way interleave phase (§2.1) and never leave the '153s - so the mux is
 * seventeen bits wide, A18..A2. */
const addressMux: Cell[] = [...Array(17).keys()].map((i) => {
  const bit = i + 2
  return {
    pin: 0, name: `FBA${bit}`, assertedLow: false, s0: 1 as const, registered: false,
    terms: [`SCANSEL & SA${bit}`, `!SCANSEL & WA${bit}`],
  }
})

export const vaddrCpld: Merged = merge(
  [rename(hadrDesign, scanMap), rename(vadrDesign, scanMap),
   rename(wcolDesign, wptrMap), rename(wrowDesign, wptrMap)],
  addressMux,
  {
    name: "vaddr", partNo: "ARM6309-UV0A", location: "video card - address datapath",
    device: "f1508ispplcc84", clock: "DOTCLK",
    external: new Set([
      ...addressMux.map((c) => c.name),   // the framebuffer address, and only this
      "WA0", "WA1",                        // WPTR[1:0] - the span writer's chip, to vctrl's arbiter
    ]),
  },
)

/* ---- part B: everything that decides ----------------------------------- */

/* §12.1's `'244` goes away: VSTAT's live bits drive D0-7 directly on a read,
 * which is §10.1.4's first absorption and the one that costs no macrocells. */
const ctrl: Cell[] = [0, 1, 2, 3, 4, 5, 6, 7].map((i) => ({
  pin: 0, name: `CTRL${i}`, assertedLow: false, s0: 1 as const, registered: true,
  terms: [`WCTRL & D${i}`, `CTRL${i} & !WCTRL`],
}))

export const vctrlCpld: Merged = merge(
  [hgenDesign, vgenDesign, vdecDesign, seqphDesign, seqctlDesign, arbDesign],
  ctrl,
  {
    name: "vctrl", partNo: "ARM6309-UV0B", location: "video card - sync, sequencer, arbiter",
    device: "f1508ispplcc84", clock: "DOTCLK",
    external: new Set([
      "HSYNC", "VSYNC",                                  // the VGA connector and the backplane
      "BLANK",                                           // the post-LUT '273's /MR (§9.2)
      "VBLANK", "HBLANK", "SPANBUSY",                    // VSTAT, now driven onto D0-7 directly
      "IRQ", "WAIT",                                     // open-drain, wire-ORed
      "FCLK0", "FCLK1", "FCLK2", "FCLK3",                // per-chip fetch latches (§5.2.2)
      "MUXSEL0", "MUXSEL1",                              // the '153 pixel mux
      "SLOTTICK", "RETIRE",                              // to vaddr, and to the '165/'161
      "GCPU0", "GCPU1", "GCPU2", "GCPU3",                // per-chip source select (§5.2.1)
      "GSPN0", "GSPN1", "GSPN2", "GSPN3",
      "CTRL0", "CTRL1", "CTRL2", "CTRL3",
      "CTRL4", "CTRL5", "CTRL6", "CTRL7",
    ]),
  },
)

export const vaddrSource = () => toCupl(vaddrCpld)
export const vctrlSource = () => toCupl(vctrlCpld)
