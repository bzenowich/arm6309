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

/* §10.3's list engine. It is the one block whose presence changes the answer to
 * "does the video card fit in two parts", so it is a switch and not a comment,
 * and both sides of it are fitted.
 *
 * ⚠ IT DEFAULTS TO BUILT AS OF 2026-09-08, which it did not before. Two changes
 * that day bought the room, and both cost something:
 *
 *   - 10.1.6.2 option 2: the engine shares WPTR instead of carrying its own
 *     19-bit pointer, so it clobbers the CPU's write pointer.
 *   - 6.4.3's Variant B, the 1bpp character generator, is gone.
 *
 * ARM6309_LIST=0 builds the card without it, which is the state every fit in
 * graphics.md before 2026-09-08 describes. */
export const WITH_LIST = process.env.ARM6309_LIST !== "0"

const scanMap = Object.fromEntries([...Array(19).keys()].map((i) => [`A${i}`, `SA${i}`]))
const wptrMap = Object.fromEntries([...Array(19).keys()].map((i) => [`A${i}`, `WA${i}`]))

const mux = addressMux()

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
  /* ⚠ CHARMODE went with Variant B on 2026-09-08 - graphics.md 6.4.3. CTRL's
   * CHAR bit stays reserved; nothing reads it. */
  comb("TILEMODE", ["CELL"]),
  /* ⚠ WRITESEL WAS AN ALIAS HERE AND IT IS GONE - 2026-09-08, second round.
   * It existed because the arbiter was off-part: SPNGRANT came IN and was
   * re-emitted under the name vaddr's mux reads. With the arbiter back on this
   * part SPNGRANT is produced here, so vaddr reads it directly and 5.2.1's
   * "WRITESEL is SPNGRANT" stops being a rename and goes back to being an
   * identity - one macrocell and one pin for a wire. */
]

/* CPUA0/CPUA1 are physical A0/A1 - the arbiter's "which of the four chips is
 * the CPU after" is the address's low two bits, and this part decodes them
 * anyway. The rename is the same identity as WRITESEL = SPNGRANT.
 *
 * ⚠ Exported as well as merged, because access.check.ts and cupl.check.ts both
 * check arbDesign standalone and a GAL22V10 fuse map is the only form either of
 * them can execute. */
export const arbGalDesign = rename(arbDesign, CPU_CHIP)
export const arbGal = arbGalDesign

/* ⚠ THE ARBITER WENT OUT AND CAME BACK, BOTH ON 2026-09-08, and the round trip
 * is the argument for why this part is a PLCC-84 rather than a TQFP100.
 *
 * OUT, in the morning. The window widening and physical A20 put two more inputs
 * here (A6 on REGSEL, /A20 on VRAMSEL - regfile.ts) and 76 I/O does not fit a
 * PLCC-84's 64. The arbiter was the cheapest ten pins to give back: eight
 * grants, WAIT and SPNGRANT are ten macrocells against a GAL22V10's ten, and
 * its inputs are all backplane or already-exported signals.
 *
 * BACK, once three other things had taken pins off this part and none of them
 * were about the arbiter: rfa took RA0-RA4 and WSTB with the nine inputs that
 * only fed them (-14), and 6.4.3's Variant B took CHARSEL, GLYPHLD, GLYPHSH and
 * LUTPAGE (-4). vctrl reached 46 of 64 and 87 of 128, and a part at two-thirds
 * capacity beside a GAL22V10 doing ten macrocells of work is a package nobody
 * is buying anything with. Merged: 62 of 64 and 97 of 128.
 *
 * ⚠ AND THAT COSTS JTAG - 2 spare pins against the 4 it needs, so vctrl joins
 * vaddr and the audio card's part in being programmed out of circuit. 14.2's
 * two-chip framebuffer is what buys it back: two grants instead of eight is six
 * output pins, and that is a 5.2 rewrite rather than a rebalance.
 *
 * ⚠ THE GAL DESIGN IS NOT DELETED. access.jedec.ts still carries arbDesign,
 * access.check.ts still exercises its fuses against access.model.ts, and
 * jedec/cupl.check.ts still sweeps it against Atmel's own compiler over all
 * 1,024 inputs. Merging a design into a CPLD costs no verification here - that
 * is how the sync trio and the scan pair already work. */
export const vctrlCpld: Merged = merge(
  [hgenDesign, vgenDesign, vdecDesign, seqphDesign, seqctlDesign, arbGalDesign],
  [...ctrl, ...ctrlFanout, ...tileCadence, ...decodeCells],
  {
    name: "vctrl", partNo: "ARM6309-UV0B", location: "video card - sync and sequencer",
    /* ⚠ f1508plcc84, NOT f1508ispplcc84. The fit is 64 of 64 I/O and 4 of 4
     * dedicated inputs with ZERO spare, and JTAG costs four I/O - so this part
     * cannot have both. It is programmed out of circuit, which is what the
     * audio card's U1 already does.
     *
     * If in-circuit programming is wanted back, four pins have to come from
     * somewhere: RA0-RA4 and WSTB onto a second GAL22V10 is the obvious six,
     * at the cost of exporting RDFG/RDBG/RDLEN. Nobody has needed it yet. */
    device: "f1508plcc84", clock: "DOTCLK",
    external: new Set([
      "HSYNC", "VSYNC", "BLANK",
      "VBLANK", "HBLANK", "SPANBUSY",                    // VSTAT, driven onto D0-7
      "IRQ",
      "FCLK0", "FCLK1", "FCLK2", "FCLK3",
      "MUXSEL0", "MUXSEL1",
      "SLOTTICK", "RETIRE",
      /* §6.4's cadence, out to the address part and the serialiser */
      "MAPLD", "MAPSEL", "TILESEL", "LINEAR",   // CHARSEL/GLYPHLD/GLYPHSH/LUTPAGE: 6.4.3
      /* §10.3's engine holds the address bus through SPNGRANT, so what vctrl
       * owes it is the grant and nothing else. */
      ...(WITH_LIST ? ["LGRANT"] : []),
      /* ⚠ RA0-RA4, WSTB and REGSEL left this part on 2026-09-08 for
       * regfile.jedec.ts's own GAL22V10 - §10.1.6.3's relief, taken. vaddr
       * still takes the same six signals; only the chip driving them moved.
       * What goes back is FP0/FP1, so that part can form the read-back
       * selects itself. Six pins out, two back. */
      "FP0", "FP1",
      "VRAMSEL", "HLOAD", "ROWADV",
      /* The cell's row and column inside the 8x8 - §6.4's geometry. These are
       * the sync counters' own low bits, so they cost pins and not logic. */
      "V0", "V1", "V2",
      /* §5.2.1's arbiter, back on this part. The eight per-chip grants go to
       * the SRAMs' /WE and the four '153 source selects; SPNGRANT goes to
       * vaddr's address mux, which is what WRITESEL used to be; /WAIT goes to
       * the backplane through its open drain. */
      ...arbGalDesign.cells.map((c) => c.name),
    ]),
  },
)


export const vaddrSource = () => toCupl(vaddrCpld)
export const vctrlSource = () => toCupl(vctrlCpld)
