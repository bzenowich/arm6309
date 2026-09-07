/* The video card as two ATF1508AS - graphics.md §10.1.6, rebalanced.
 *
 * The cut follows the address bus. Everything that can drive the framebuffer
 * address is on ONE part, because every such source that is not costs its full
 * width in crossing nets - nineteen for the write pointer, nineteen more for
 * the list engine's. Everything that decides is on the other, and every
 * dot-rate signal is with whatever it clocks, because a crossing net costs a
 * tPD of 15 ns against a 39.7 ns dot period.
 *
 *   vaddr   scan counters, WPTR, the scroll and tile registers, §10.3's list
 *           engine, and the five-source address mux they all feed
 *   vctrl   sync trio, sequencer, span control, arbiter, CTRL, and §6.4's
 *           second fetch cadence
 */

import { merge, rename, toCupl, type Merged } from "./jedec/cupl"
import type { Cell } from "./jedec/assemble"
import { hgenDesign, vgenDesign, vdecDesign } from "./sync.jedec"
import { hadrDesign, vadrDesign } from "./scan.jedec"
import { arbDesign, wcolDesign, wrowDesign } from "./access.jedec"
import { seqphDesign } from "./seqph.jedec"
import { seqctlDesign } from "./seqctl.jedec"
import { addressMux, listEngine, scrollHolds, tileCadence, tileRegisters } from "./video.parts"
import { decodeCells, writeStrobes } from "./regfile"

/* CPUA0/CPUA1 were pins of their own beside A0/A1. They are the same two
 * lines: the arbiter's "which of the four interleaved chips is the CPU after"
 * is the physical address's low two bits, which the register decode already
 * needs on this part. Two pins for a rename, and the same kind of identity as
 * WRITESEL = SPNGRANT. */
const CPU_CHIP: Record<string, string> = { CPUA0: "A0", CPUA1: "A1" }

/* §10.3's list engine is built only when asked for. It is the one block whose
 * presence changes the answer to "does the video card fit in two parts", so it
 * is a switch and not a comment, and both sides of it are fitted. */
export const WITH_LIST = process.env.ARM6309_LIST === "1"

const scanMap = Object.fromEntries([...Array(19).keys()].map((i) => [`A${i}`, `SA${i}`]))
const wptrMap = Object.fromEntries([...Array(19).keys()].map((i) => [`A${i}`, `WA${i}`]))

const mux = addressMux(WITH_LIST)

export const vaddrCpld: Merged = merge(
  [rename(hadrDesign, scanMap), rename(vadrDesign, scanMap),
   rename(wcolDesign, wptrMap), rename(wrowDesign, wptrMap)],
  [...scrollHolds, ...tileRegisters, ...writeStrobes,
   ...(WITH_LIST ? listEngine : []), ...mux],
  {
    name: "vaddr", partNo: "ARM6309-UV0A", location: "video card - address datapath",
    device: "f1508ispplcc84", clock: "DOTCLK",
    external: new Set([
      ...mux.map((c) => c.name),   // the framebuffer address, and almost nothing else
      "WA0", "WA1",                 // WPTR[1:0] - the span writer's chip, to vctrl's arbiter
      ...(WITH_LIST ? ["LRUN"] : []),  // BSTAT, and the arbiter's third requester
    ]),
  },
)

/* CTRL, §12's `+$00`, was a '273 on the parts list and it is eight macrocells
 * here. It is WRITE-ONLY - §12 gives reads their own register, VSTAT - which
 * is what lets it stay entirely inside the part.
 *
 * THAT MATTERS MORE THAN IT LOOKS. Before this the merge exported CTRL0..7 as
 * eight pins AND took HPOL, M0, IRQEN, WM0, WM1, TILEMODE and CHARMODE back in
 * as seven more - the same register, crossing the boundary twice, fifteen pins
 * to hold a byte that never leaves. That was the whole of vctrl's pin overrun.
 *
 * b2 is the one bit-map change: §12 spends three bits on VMODE and defines
 * four codes, so b2 was already dead space. It is now CHAR, which with b5's
 * CELL gives §6.4 both of its modes for nothing. */
const ctrlBit = (i: number, name: string): Cell => ({
  pin: 0, name, assertedLow: false, s0: 1, registered: true,
  terms: [`WCTRL & D${i}`, `${name} & !WCTRL`],
})

const ctrl: Cell[] = [
  ctrlBit(0, "VMODE0"), ctrlBit(1, "VMODE1"), ctrlBit(2, "CHAR"),
  ctrlBit(3, "WM0"),    ctrlBit(4, "WM1"),    ctrlBit(5, "CELL"),
  ctrlBit(6, "IRQEN"),  ctrlBit(7, "DISPEN"),
]

const comb = (name: string, terms: string[]): Cell =>
  ({ pin: 0, name, assertedLow: false, s0: 1, registered: false, terms })

const ctrlFanout: Cell[] = [
  /* vdec spells VMODE's low bit M0. */
  comb("M0", ["VMODE0"]),
  /* Sync polarity is not a register bit and never was: §12's four codes are
   * 70 Hz at VMODE0 = 0 and 60 Hz at VMODE0 = 1, and the 70 Hz pair is the
   * positive-H pair. A pin for this was a pin for a NOT gate. */
  comb("HPOL", ["!VMODE0"]),
  comb("TILEMODE", ["CELL & !CHAR"]),
  comb("CHARMODE", ["CELL & CHAR"]),
  /* The write pointer owns the address bus exactly when the arbiter has given
   * the span writer a chip. It is the same signal as SPNGRANT under the name
   * the address part's mux uses. */
  comb("WRITESEL", ["SPNGRANT"]),
]

export const vctrlCpld: Merged = merge(
  [hgenDesign, vgenDesign, vdecDesign, seqphDesign, seqctlDesign,
   rename(arbDesign, CPU_CHIP)],
  [...ctrl, ...ctrlFanout, ...tileCadence, ...decodeCells],
  {
    name: "vctrl", partNo: "ARM6309-UV0B", location: "video card - sync, sequencer, arbiter",
    device: "f1508ispplcc84", clock: "DOTCLK",
    external: new Set([
      "HSYNC", "VSYNC", "BLANK",
      "VBLANK", "HBLANK", "SPANBUSY",                    // VSTAT, driven onto D0-7
      "IRQ", "WAIT",
      "FCLK0", "FCLK1", "FCLK2", "FCLK3",
      "MUXSEL0", "MUXSEL1",
      "SLOTTICK", "RETIRE",
      "GCPU0", "GCPU1", "GCPU2", "GCPU3",
      "GSPN0", "GSPN1", "GSPN2", "GSPN3",
      /* §6.4's cadence, out to the address part and the serialiser */
      "MAPLD", "MAPSEL", "TILESEL", "CHARSEL", "LINEAR", "GLYPHLD", "GLYPHSH", "LUTPAGE",
      /* §19 item 23(b): the file address and one write strobe, in place of one
       * strobe pin per register. The address part decodes its own. */
      "RA0", "RA1", "RA2", "RA3", "RA4", "WSTB",
      "VRAMSEL", "REGSEL", "HLOAD", "ROWADV",
      /* The cell's row and column inside the 8x8 - §6.4's geometry. These are
       * the sync counters' own low bits, so they cost pins and not logic. */
      "V0", "V1", "V2",
      /* WRITESEL used to arrive here as an input from nowhere. The span
       * sequencer is on this part, so it is an output. LISTSEL is not: §10.3's
       * arbitration is not designed, and until it is, the address part takes
       * it as an input rather than this part inventing it. */
      "WRITESEL",
    ]),
  },
)

export const vaddrSource = () => toCupl(vaddrCpld)
export const vctrlSource = () => toCupl(vctrlCpld)
