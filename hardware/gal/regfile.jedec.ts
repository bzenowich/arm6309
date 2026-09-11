/* rfa - the register-file address GAL, split off vctrl 2026-09-08.
 *
 * WHY IT EXISTS. regfile.ts's own header argues the opposite case, and it was
 * right when it was written: "macrocells are cheap and pins are not (vctrl
 * fits at 62 of 64), and one strobe per register costs one pin per register".
 * Six address lines and a write strobe replaced nine strobe pins.
 *
 * Then vctrl ran out of pins anyway - 64 of 64 after the widened $FF window
 * and physical A20 (10.1.6.3) - and graphics.md 7.4's broadcast write needs
 * signalling between vctrl and vaddr that there is nowhere to put. This part
 * is the relief that section names: RA0-RA4 and WSTB come off vctrl, and what
 * goes back is FP0/FP1, because this GAL can form RDFG/RDBG/RDLEN itself from
 * the fetch phase rather than taking three decoded signals.
 *
 *   6 pins out, 2 back  ->  vctrl falls to 60 of 64.
 *
 * REGSEL is recomputed here rather than carried: it is IOSEL & A6 & A5, and
 * all three are on the card already, so importing it would cost a pin to save
 * two product terms.
 */
import { place } from "./jedec/place"
import type { Cell, Design } from "./jedec/assemble"

/* REGSEL = IOSEL & A6 & A5, so !REGSEL is three terms - which is what makes
 * RA2 the widest equation here. The read-back selects are the fetch phase:
 * RDLEN/RDFG/RDBG are FP1:FP0 = 00/01/10 while the span writer is idle. */
const REGSEL = "IOSEL & A6 & A5"
const NOT_REGSEL = ["!IOSEL", "!A6", "!A5"]
/** `!REGSEL & <x>`, expanded - three terms, one per literal of !REGSEL. */
const gated = (x: string) => NOT_REGSEL.map((n) => `${n} & ${x}`)

/* ⛔ AND THE CPU DOES NOT GET THE FILE WHILE A SPAN IS RUNNING - 2026-09-10.
 *
 * The CPU's claim used to be REGSEL alone, so ANY access to $FF60-$FF7F took
 * RA away from the span writer for the whole bus cycle. 7.4's colour path is
 * the file's address - "RD IS WFG or WBG without a mux" - so for the twelve
 * dots of that cycle the span retired whatever byte the CPU's own address
 * named. Three retires, because a retire is one per four dots.
 *
 * ⚠ AND THE ACCESS THE MACHINE ACTUALLY MAKES IS THE ONE 7.4 TELLS IT TO
 * MAKE. §7.4's rule is "poll VSTAT at $FF73, which never waits", and §13 puts
 * VSTAT on §12.1's '244 rather than in the file - so the poll needs no file
 * access at all, and took one anyway. machine_tb drew 640x200 with the card's
 * own span writer and every span came out with a three-pixel hole in it,
 * one per poll. graphics.md 7.4, 19 item 38.
 *
 * ⭐ IT COSTS NOTHING AND GIVES TERMS BACK. The CPU's term gains a literal;
 * the span's three gated terms collapse to one, because "the CPU is not
 * taking it" is now implied by SPANBUSY itself. RA1 goes from four product
 * terms to two.
 *
 * ⚠ WHAT IT COSTS SOFTWARE, stated because it is a real rule: while SPANBUSY,
 * a read of $FF60-$FF7F returns the span's colour byte rather than the
 * register asked for, and a WRITE lands in WFG or WBG. VSTAT is exempt in both
 * directions - it is the '244 - so the polling loop 7.4 specifies is exactly
 * the access that still works. Extending /WAIT to hold register writes during
 * a span was costed and not taken: it is one product term on the arbiter's
 * output enable plus a REGSEL pin vctrl does not have, to buy a case the
 * polling rule already covers. */
const CPUSEL = `${REGSEL} & !SPANBUSY`
/** The CPU is not taking the file: `!REGSEL` (three terms) or a span is. */
const notCpu = (x: string) => [...gated(x), `SPANBUSY & ${x}`]

/* ⭐ REWRITTEN 2026-09-09, and it is 7.4's mechanism rather than a walk
 * towards it.
 *
 * ⛔ WHAT WAS HERE: a two-bit walk on FP1:FP0 that presented SPANLEN, WFG and
 * WBG in turn while the span writer was IDLE, "fetching all three for the next
 * span" - and nothing on the card produced FP0 or FP1, nothing received the
 * three values, and every term of the walk carried !SPANBUSY, so DURING a span
 * the file address was $00 and the span writer would have retired CTRL's byte
 * into the framebuffer. design-review2.md V-1.
 *
 * ⭐ WHAT REPLACES IT is the sentence 7.4 already wrote: "the serialiser's
 * serial output is wired to the register file's address bit 0, which is why 13
 * requires WFG at A0 = 0 and WBG at A0 = 1. Choosing the source colour per
 * pixel costs no macrocell and no product term - it is an address line." So
 * the file is addressed LIVE during the span and the mask bit is RA0:
 *
 *   REGSEL          the CPU's own access          RA = A4..A0
 *   span in flight  $06 or $07, per the mask bit  RA = 0011 !MASKBIT
 *   idle            $05, SPANLEN                  RA = 00101
 *   reload, dot 1   $08, WPTR's low byte          RA = 01000
 *   reload, dot 2   $09, its middle byte          RA = 01001
 *
 * The idle case is what loads the length counter: the file presents SPANLEN
 * continuously while no span is running, so the counter's load at the posted
 * write needs no walk, no phase and no state. FP0, FP1 and the two macrocells
 * they would have cost on vctrl are all deleted. */
const SPAN = ["SPANBUSY"]
/* ⭐ AND A THIRD STATE, 2026-09-09: 7.2's column reload. vaddr walks RP1:RP0
 * through 01 and 10 at span end (video.parts.ts) and this part points the file
 * at WPTR's own low and middle bytes for those two dots, so wcol reloads
 * through the load path the CPU's write already uses. That is what 7.2 means
 * by "two deferrable file reads to restore the column ... no latch, no mux" -
 * and it is what makes the text engine's 13 writes per cell real rather than
 * 26. design-review2.md V-6. */
const IDLE = gated("!SPANBUSY & !RP0 & !RP1")
const RELOAD_A = gated("RP0")      // $08, WPTR's low byte
const RELOAD_B = gated("RP1")      // $09, its middle byte

const cells: Cell[] = [
  /* ⛔ AND NOT AT +$15, WHICH IS VDATA - 2026-09-11, graphics.md 11, 19 item 47.
   * VDATA is the VRAM port at an I/O address, so its store is a POSTED VRAM
   * write (vctrl's WSTBV) and not a register write. Left in, this strobe would
   * write the file's byte at RA too - and while a span runs RA is WFG or WBG,
   * not +$15, and /WAIT holds E high for the whole span: the CPU's byte would
   * become the colour of every pixel still to retire. Five terms, one per
   * literal of +$15's address. */
  /* ⛔ ASSERTED LOW since 2026-09-11: this pin IS the register file's /WE, and
   * the board has no inverter. It was emitted active-high. pins.check.ts. */
  { pin: 0, name: "WSTB", assertedLow: true, s0: 0, registered: false,
    why: "E-qualified: a 6809 write is only valid data in the second half - and not VDATA's",
    terms: ["!A4", "A3", "!A2", "A1", "!A0"].map((l) => `${REGSEL} & !RW & E & ${l}`) },
  /* $05 is 00101 and $06/$07 are 0011x, so bit 0 is 1 when idle and the mask
   * bit during a span - which is the whole of 7.4's colour selection. */
  /* ⚠ IT IS THE COMPLEMENT OF THE MASK BIT, and 13's placement is why. WFG
   * sits at $06 and WBG at $07, so A0 = 0 selects the FOREGROUND - and 7.4's
   * table says a `0` mask bit writes WBG, which is A0 = 1. A glyph's 1 bits
   * are its ink. On a '165 that is the /QH pin rather than QH and costs
   * nothing; here it is one literal. */
  { pin: 0, name: "RA0", assertedLow: false, s0: 1, registered: false,
    why: "7.4: the mask bit IS the register file's address bit 0, inverted",
    terms: [`${CPUSEL} & A0`, "SPANBUSY & !MASKBIT", ...IDLE,
      ...RELOAD_B] },
  { pin: 0, name: "RA1", assertedLow: false, s0: 1, registered: false,
    terms: [`${CPUSEL} & A1`, ...SPAN] },
  /* Bit 2 is 1 in $05, $06 and $07 alike and 0 in $08/$09. */
  { pin: 0, name: "RA2", assertedLow: false, s0: 1, registered: false,
    terms: [`${CPUSEL} & A2`, ...notCpu("!RP0 & !RP1")] },
  /* Bit 3 is the reload's own, and nothing else's. */
  { pin: 0, name: "RA3", assertedLow: false, s0: 1, registered: false,
    terms: [`${CPUSEL} & A3`, ...RELOAD_A, ...RELOAD_B] },
  { pin: 0, name: "RA4", assertedLow: false, s0: 1, registered: false,
    terms: [`${CPUSEL} & A4`] },

  /* ⭐ TWO STROBES THIS PART CAN FORM AND vctrl CANNOT, 2026-09-09. CTRL's
   * write strobe and VSTAT's were inputs to vctrl that nothing produced - so
   * CTRL could not be written at all (no VMODE, no WMODE, no CELL, no IRQEN,
   * no display enable) and the VBL flag could not be cleared, which left /IRQ
   * asserted for ever after the first frame. design-review2.md V-1.
   *
   * They belong here because RA4..RA0 are here: vctrl gave those six signals
   * up to this part on 2026-09-08 (10.1.6.3) and has no way to decode a
   * register address any more. Two macrocells on a part that had four free. */
  { pin: 0, name: "WCTRL", assertedLow: false, s0: 1, registered: false,
    terms: [`${REGSEL} & !RW & E & !A4 & !A3 & !A2 & !A1 & !A0`] },
  { pin: 0, name: "VSTATWR", assertedLow: false, s0: 1, registered: false,
    terms: [`${REGSEL} & !RW & E & A4 & !A3 & !A2 & A1 & A0`] },
]

/* RA0 is the widest at seven terms, so it wants one of the wide macrocells.
 * place() pairs the widest equation with the widest macrocell still free,
 * which is optimal for a fixed set, and names the equation if it cannot.
 * Eight macrocells of ten, and pins 22 and 23 stay free. */
const pins = place(cells, [14, 15, 16, 17, 18, 19, 20, 21])

export const rfaDesign: Design = {
  name: "rfa",
  partNo: "ARM6309-UV9",
  location: "video card - register-file address",
  signature: "A6309V9",
  supersededBy: "graphics.md 10.1.7 - absorbed into vsup, the third ATF1508AS, 2026-09-09",
  inputs: [
    /* ⛔ /IOSEL is an active-low backplane strobe; declared active-high until
     * 2026-09-11, so the fitted decode selected on every cycle OUTSIDE the
     * window. pins.check.ts. */
    { name: "IOSEL", pin: 1, activeLow: true }, { name: "A5", pin: 2 }, { name: "A6", pin: 3 },
    { name: "A0", pin: 4 }, { name: "A1", pin: 5 }, { name: "A2", pin: 6 },
    { name: "A3", pin: 7 }, { name: "A4", pin: 8 },
    { name: "RW", pin: 9 }, { name: "E", pin: 10 },
    /* From vctrl: the span-writer state the read-back mux keys off. SPANBUSY
     * is already a vctrl output (VSTAT b7); FP0/FP1 are the two new pins. */
    { name: "SPANBUSY", pin: 11 },
    /* ⭐ The serialiser's serial output, and 7.4's whole colour path. It
     * replaced FP0/FP1, which were two pins carrying a walk nothing produced
     * and nothing received. */
    { name: "MASKBIT", pin: 13 },
    /* 7.2's reload walk, from vaddr. Two macrocell pins used as inputs, which
     * is what pins 22 and 23 were being kept for. */
    { name: "RP0", pin: 22 }, { name: "RP1", pin: 23 },
  ],
  cells: cells.map((c) => ({ ...c, pin: pins[c.name] })),
}
