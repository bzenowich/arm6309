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
import {
  addressMux, listEngine, mapColumn, scrollHolds, tileCadence, tileRegisters,
} from "./video.parts"
import { decodeCells, writeStrobes } from "./regfile"

/* CPUA0/CPUA1 were pins of their own beside A0/A1. They are the same two
 * lines: the arbiter's "which of the four interleaved chips is the CPU after"
 * is the physical address's low two bits, which the register decode already
 * needs on this part. Two pins for a rename, and the same kind of identity as
 * WRITESEL = SPNGRANT. */
const CPU_CHIP: Record<string, string> = { CPUA0: "A0", CPUA1: "A1" }

/* ⚠ AND CE IS SLOTTICK. hgen declares its slot enable as an input and says why
 * in the same breath - "the sequencer pair already forms the dot phase for the
 * pixel mux, so this is that signal and not a second divider". seqph produces
 * it, on this same part, and vctrl was taking it back in on a pin anyway. One
 * more identity, one more pin, and 6.4.9's cadence needed it. */
const SLOT_CE: Record<string, string> = { CE: "SLOTTICK" }

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
/* ⚠ VLOAD IS VBLANK. scan.jedec.ts declares vadr's load input as "asserted
 * through vertical blanking", which is what vdec's VBLANK already is and has
 * always been - so the signal was invented twice and produced once. Renaming it
 * here costs nothing and saves the pin that producing a second copy would have
 * needed, on a part with none to spare. Same identity as WRITESEL = SPNGRANT
 * and CE = SLOTTICK below. */
const rowMap = { ...scanMap, VLOAD: "VBLANK" }
const wptrMap = Object.fromEntries([...Array(19).keys()].map((i) => [`A${i}`, `WA${i}`]))

const mux = addressMux()

export const vaddrCpld: Merged = merge(
  [rename(hadrDesign, scanMap), rename(vadrDesign, rowMap),
   rename(wcolDesign, wptrMap), rename(wrowDesign, wptrMap)],
  [...scrollHolds, ...tileRegisters, ...mapColumn, ...writeStrobes,
   ...(WITH_LIST ? listEngine : []), ...mux],
  {
    name: "vaddr", partNo: "ARM6309-UV0A", location: "video card - address datapath",
    device: "f1508ispplcc84", clock: "DOTCLK",
    external: new Set([
      ...mux.map((c) => c.name),   // the framebuffer address, and almost nothing else
      "WA0", "WA1",                 // WPTR[1:0] - the span writer's chip, to vctrl's arbiter
      /* §6.4.2's map fetch is a spare access too, so it names a chip the same
       * way: MAPA[1:0] = cellCol[1:0]. Two pins out, and three come back below
       * - V0..V2 are no longer imported at all. */
      "MAPA0", "MAPA1",
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
/* ⚠ FOUR MORE RENAMES SINCE 2026-09-08, all so that §6.4's map fetch can become
 * the arbiter's fourth requester WITHOUT editing arbDesign - which stays a
 * standalone GAL22V10 that access.check.ts and cupl.check.ts can execute, and
 * which is full at 10 of 10 macrocells and 10 of 10 input pins.
 *
 *   GCPU0..3 -> ACPU0..3   the raw CPU grant; tileCadence withdraws the map's
 *                          chip from it and emits the real GCPU0..3
 *   SPNREQ   -> SPNREQG    the span writer's request, gated off in a map slot
 *                          because the two share the card's one address bus
 *   SPANBUSY -> WAITSRC    /WAIT's source: the span backstop OR a map hold
 *   RW       -> WAITRW     /WAIT's read qualifier, defeated by a map hold so
 *                          that reads wait for it too (7.4 keeps its !RW)
 *
 * Renaming an input is how CPUA0/CPUA1 already reach it; renaming an output is
 * the same operation and the fuse map is untouched either way. */
const ARB_MAP: Record<string, string> = {
  ...CPU_CHIP,
  GCPU0: "ACPU0", GCPU1: "ACPU1", GCPU2: "ACPU2", GCPU3: "ACPU3",
  SPNREQ: "SPNREQG", SPANBUSY: "WAITSRC", RW: "WAITRW",
}

export const arbGalDesign = rename(arbDesign, ARB_MAP)
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
  [rename(hgenDesign, SLOT_CE), rename(vgenDesign, SLOT_CE), vdecDesign,
   seqphDesign, seqctlDesign, arbGalDesign],
  [...ctrl, ...ctrlFanout, ...tileCadence, ...decodeCells],
  {
    name: "vctrl", partNo: "ARM6309-UV0B", location: "video card - sync and sequencer",
    /* ⚠ f1508ispplcc84 SINCE 2026-09-08, and it was f1508plcc84 for a day.
     * The reasoning against JTAG was arithmetic - "the fit is 62 of 64 I/O and
     * JTAG costs four, so this part cannot have both" - and 6.4's corrected
     * cell address is what changed the input to it. V0..V2 were exported from
     * here to vaddr as the row inside the cell and were the WRONG COUNTER
     * (sync.timing.ts's V starts at the leading edge of VSYNC); the right one,
     * vadr's row counter, is already on vaddr. Three pins came back, the fit is
     * 59 of 64 with JTAG reserved, and this part is programmable in circuit.
     *
     * `JTAG=on gal/prjbureau/fit1508.sh gal/vctrl.pld` is what says so - the
     * fitter reserves TMS/TDI/TDO/TCK and reports "Design fits successfully". */
    device: "f1508ispplcc84", clock: "DOTCLK",
    external: new Set([
      "HSYNC", "VSYNC", "BLANK",
      "VBLANK", "HBLANK", "SPANBUSY",                    // VSTAT, driven onto D0-7
      "IRQ",
      "FCLK0", "FCLK1", "FCLK2", "FCLK3",
      "MUXSEL0", "MUXSEL1",
      "SLOTTICK", "RETIRE",
      /* §6.4's cadence, out to the address part and the serialiser */
      "MAPLD", "MAPSEL", "TILESEL", "LINEAR",   // CHARSEL/GLYPHLD/GLYPHSH/LUTPAGE: 6.4.3
      /* §6.4's fetch sequence, and §8's two window signals with it - census.ts
       * listed FETCH and HLOAD as "produced by the sequencer's unfitted decode
       * half" and nothing produced them. MCADV steps the map's column counter,
       * which is on vaddr because the address it feeds is. */
      "FETCH", "MCADV",
      /* The CPU's per-chip grant, with the map's chip withdrawn - 5.2.1's
       * SRCSEL[n] under its own name now that it is not arbDesign's output. */
      "GCPU0", "GCPU1", "GCPU2", "GCPU3",
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
      /* ⚠ V0..V2 LEFT THIS LIST ON 2026-09-08. They were exported as "the cell's
       * row inside the 8x8 - the sync counters' own low bits, so they cost pins
       * and not logic", and they were the wrong counter: sync.timing.ts starts
       * V at the leading edge of VSYNC, so active video begins at V = 37 or 35
       * depending on the family and V2..V0 is 5 or 3 at the top of the screen,
       * not 0. §6.4's vertical fields are vadr's row counter instead - SA12..10
       * for the row within the cell, SA17..13 for the cell row - which is on
       * vaddr already and is zero-based and VSCROLL-offset by construction.
       * Three pins back, and cell mode gains free vertical scroll with them. */
      /* §5.2.1's arbiter, back on this part. The eight per-chip grants go to
       * the SRAMs' /WE and the four '153 source selects; SPNGRANT goes to
       * vaddr's address mux, which is what WRITESEL used to be; /WAIT goes to
       * the backplane through its open drain. */
      /* ACPU0..3 are buried: the cadence gates them into GCPU0..3 above. */
      ...arbGalDesign.cells.map((c) => c.name).filter((n) => !/^ACPU\d$/.test(n)),
    ]),
  },
)


export const vaddrSource = () => toCupl(vaddrCpld)
export const vctrlSource = () => toCupl(vctrlCpld)
