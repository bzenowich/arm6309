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
import { arbDesign, wcolCellsFor, wcolDesign, wrowDesign } from "./access.jedec"
import { seqphDesign } from "./seqph.jedec"
import { seqctlDesign } from "./seqctl.jedec"
import {
  addressMux, listEngine, mapColumn, maskSerialiser, scrollHolds, tileCadence,
  tileRegisters, columnReload,
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
  /* ⚠ wcol IS MERGED WITH 7.2's RELOAD and checked without it - access.jedec.ts
   * has the arithmetic. Thirteen inputs is not a GAL22V10, and the reload
   * changes nothing about the counting or the wrap that access.check.ts
   * exercises. One generator, two forms. */
  [rename(hadrDesign, scanMap), rename(vadrDesign, rowMap),
   rename({ ...wcolDesign, cells: wcolCellsFor(true) }, wptrMap),
   rename(wrowDesign, wptrMap)],
  [...scrollHolds, ...tileRegisters, ...mapColumn, ...columnReload,
   ...writeStrobes, ...(WITH_LIST ? listEngine : []), ...mux],
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
      /* 7.2's reload walk, to rfa - which points the register file at WPTR's
       * own bytes for the two dots it lasts. */
      "RP0", "RP1",
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
  ctrlBit(0, "VMODE0"), ctrlBit(1, "VMODE1"),
  /* ⚠ b2 CHAR IS NOT BUILT. It went with 6.4.3's Variant B on 2026-09-08 and
   * nothing has read it since, so the macrocell it cost is spent on the mask
   * serialiser instead. 13 keeps the bit reserved against a rebuild. */
  ctrlBit(3, "WM0"),    ctrlBit(4, "WM1"),    ctrlBit(5, "CELL"),
  ctrlBit(6, "IRQEN"),  ctrlBit(7, "DISPEN"),
]

/* ---- 13's +$14, WADV, and 8's HSCROLL[1:0] ------------------------------
 *
 * ⛔ NEITHER EXISTED. Both were inputs to this part that nothing on the card
 * produced (design-review2.md V-1): WADV0/WADV1 meant 7.2's chaining could not
 * be selected, and HS0/HS1 meant the mux-phase preload - "sub-pixel horizontal
 * smoothness costs zero parts, because the phase counter already drives the
 * 4:1 selection" (8) - had no register behind it.
 *
 * They live here rather than beside the other scroll bits on vaddr because
 * seqph's MUXSEL and FCLK read them at DOT rate, and 10.1.6 forbids a crossing
 * net on a dot-rate path. What crosses instead is their load strobe, which is
 * decoded from the register address on the part that has it. */
const loadable2 = (name: string, strobe: string): Cell[] =>
  [0, 1].map((b) => ({
    pin: 0, name: `${name}${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`${strobe} & D${b}`, `${name}${b} & !${strobe}`],
  }))

const comb = (name: string, terms: string[]): Cell =>
  ({ pin: 0, name, assertedLow: false, s0: 1, registered: false, terms })

/* ⛔ 3.1.1'S POSTED VRAM WRITE HAD NO STROBE, and seqctl was reading the
 * register-file one instead.
 *
 * rfa produces WSTB as `REGSEL & /RW & E` - a write to $FF60-$FF7F - which is
 * exactly right for vaddr's register strobes and exactly wrong for the signal
 * that starts a span. As wired, WRITING ANY CARD REGISTER STARTED A SPAN and a
 * posted VRAM write started none: both directions broken by one name meaning
 * two things. design-review2.md V-2.
 *
 * The second strobe is one macrocell on a part that already has all three
 * literals - VRAMSEL is formed here (regfile.ts) and R/W and E are pins. */
const vramWriteStrobe: Cell[] = [
  comb("WSTBV", ["VRAMSEL & !RW & E"]),
]

const ctrlFanout: Cell[] = [
  /* vdec spells VMODE's low bit M0. */
  comb("M0", ["VMODE0"]),
  /* ⛔ HPOL IS A CONSTANT AND THIS READ `!VMODE0` UNTIL 2026-09-09.
   *
   * 10.1.6.1 derived it from "the 70 Hz pair is the positive-H pair", and
   * 6.2.1's own table says the opposite in the row above the one that was
   * read: HSYNC is NEGATIVE in both families and it is VSYNC that switches.
   * That is also the VGA standard - 640x400@70 is -H/+V and 640x480@60 is
   * -H/-V, and there is no standard mode at 31.5 kHz with +H. VMODE 01 and
   * VMODE 11 were emitted as +H/-V. design-review2.md V-7.
   *
   * hgen carries HPOL as an input rather than strapping it in silicon
   * (sync.jedec.ts) so that an out-of-spec monitor is a re-burn and not a cut
   * trace; on this part the strap is a constant, and a constant is written as
   * a tautology because both the 22V10 assembler and CUPL read term lists. */
  comb("HPOL", ["VMODE0", "!VMODE0"]),
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
/* seqctl's "a posted write has been latched" is WSTBV and not rfa's register
 * strobe - design-review2.md V-2, and the comment on vramWriteStrobe. */
const SPAN_STB: Record<string, string> = { WSTB: "WSTBV" }

export const vctrlCpld: Merged = merge(
  [rename(hgenDesign, SLOT_CE), rename(vgenDesign, SLOT_CE), vdecDesign,
   seqphDesign, rename(seqctlDesign, SPAN_STB), arbGalDesign],
  [...ctrl, ...ctrlFanout, ...vramWriteStrobe,
   ...loadable2("HS", "LDHS"), ...loadable2("WADV", "LDADV"),
   ...maskSerialiser, ...tileCadence, ...decodeCells],
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
      /* ⚠ RETIRE AND WEN ARE TWO SIGNALS SINCE features.md 8.4's sprite mode.
       * RETIRE advances the pointer, the serialiser and the length counter;
       * WEN is the framebuffer's write strobe, and in WMODE 11 a transparent
       * pixel asserts the first and not the second. Every other mode has them
       * identical, which is why one signal did both jobs until now. */
      /* ⚠ SLOTTICK IS NOT EXPORTED, since 2026-09-09. It was, from the days
       * when hgen took CE as an input pin and this part fed its own output
       * back in; the rename made that internal and the export outlived it.
       * Nothing off this part consumes it - the fetch latches take FCLK, the
       * mux takes MUXSEL, the counters take FETCH and MCADV - and it is the
       * one pin that bought the column reload its room. */
      "RETIRE", "WEN",
      /* §6.4's cadence, out to the address part and the serialiser. ⭐ The four
       * mux-source selects are two encoded bits since 2026-09-09 - SRC1:SRC0,
       * video.parts.ts - which is where vctrl's last two pins came from. */
      "MAPLD", "SRC0", "SRC1",   // CHARSEL/GLYPHLD/GLYPHSH/LUTPAGE: 6.4.3
      /* §6.4's fetch sequence, and §8's two window signals with it - census.ts
       * listed FETCH and HLOAD as "produced by the sequencer's unfitted decode
       * half" and nothing produced them. MCADV steps the map's column counter,
       * which is on vaddr because the address it feeds is. */
      "FETCH", "MCADV",
      /* The CPU's per-chip grant, with the map's chip withdrawn - 5.2.1's
       * SRCSEL[n] under its own name now that it is not arbDesign's output. */
      "GCPU0", "GCPU1", "GCPU2", "GCPU3",
      /* §10.3's engine holds the address bus through SPNGRANT, so what vctrl
       * owes it is the grant and nothing else - and since 2026-09-09 it
       * actually produces it (video.parts.ts). */
      ...(WITH_LIST ? ["LGRANT"] : []),
      /* ⭐ 7.4's mask bit, to rfa's RA0 - which is the colour path - and the
       * cell-boundary tick that hands the map byte over on vaddr. */
      "MASKBIT", "CELLTICK",
      /* 7.2's row advance. It was produced here and NOT exported, so on
       * silicon WPTR's row could not advance at all - design-review2.md V-6. */
      "WROWADV",
      /* ⚠ RA0-RA4, WSTB and REGSEL left this part on 2026-09-08 for
       * regfile.jedec.ts's own GAL22V10 - §10.1.6.3's relief, taken. vaddr
       * still takes the same six signals; only the chip driving them moved.
       *
       * ⭐ FP0/FP1 WENT WITH THEM on 2026-09-09. They carried a read-back walk
       * that nothing produced and nothing received; 7.4's mask bit does the
       * job as an address line, which is what that section always said.
       * regfile.jedec.ts. Two pins and two macrocells deleted rather than
       * built. */
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
       * the SRAMs' /WE and the four '153 source selects; /WAIT goes to the
       * backplane through its open drain.
       *
       * ⭐ SPNGRANT NO LONGER CROSSES. It was vaddr's mux select - 5.2.1's
       * "WRITESEL is SPNGRANT" - and the mux takes SRC1:SRC0 now. On this part
       * it is still read by seqctl's RETIRE and by LGRANT, so it stays a cell;
       * it just stops being a pin. */
      /* ACPU0..3 are buried: the cadence gates them into GCPU0..3 above. */
      ...arbGalDesign.cells.map((c) => c.name)
        .filter((n) => !/^ACPU\d$/.test(n) && n !== "SPNGRANT"),
    ]),
  },
)


export const vaddrSource = () => toCupl(vaddrCpld)
export const vctrlSource = () => toCupl(vctrlCpld)
