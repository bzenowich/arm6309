/* The video card's sync GALs - graphics.md 19 item 8, which says they do not
 * fit and offers three escapes "one of which must be chosen at fit time".
 *
 * This is fit time. The partition below is forced by PINS, not by macrocells,
 * and that is the part item 8 did not see: it counted macrocells, found 24
 * against 20, and listed moving the 8-bit slot counter off-chip as the first
 * escape. That escape does not work. Move the slot counter out and the GAL
 * that decodes both counters needs h[7:0] AND v[9:0] AND four control inputs
 * on one part - 22 inputs where a 22V10 with six outputs has 16. The counter
 * has to stay on the same package as the things that decode it.
 *
 * What does work is three parts, and the third is half empty:
 *
 *   hgen   H0..H7, HSYNC, HBLANK                      10 of 10 macrocells
 *   vgen   V0..V9                                     10 of 10
 *   vdec   VTC, VSYNC, VBLANK, BLANK, VSDLY,
 *          VBLPEND, /IRQ                               7 of 10, 3 spare
 *
 * 27 macrocells, not item 8's 24. The three it does not count are VTC (the
 * line counter's mode-dependent terminal count - it is a decode of V, so it
 * cannot live on the part that has no room left), VSDLY (the one-dot delay
 * that makes the VBL flag a pulse rather than a level, without which the
 * interrupt re-arms itself under its own handler) and VBLPEND itself, which
 * item 8 folds into the /IRQ macrocell although the OE idiom of 12.1 leaves
 * the macrocell's data pin driving a constant and no state anywhere.
 */

import { counterTerms } from "./jedec/counter"
import { rangeTerms } from "./jedec/range"
import { H, SLOTS_PER_LINE, V449, V525 } from "./sync.timing"
import type { Design } from "./jedec/assemble"

const HB = ["H0", "H1", "H2", "H3", "H4", "H5", "H6", "H7"]
const VB = ["V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9"]

/* The slot counter never passes 199, so its terminal count is a partial
 * decode: H7 & H6 puts it at 192 or above and the low three bits pick 199. */
const H_LAST = rangeTerms({ bits: HB, lo: H.last, hi: H.last, max: H.last })[0]

/* The line counter's largest reachable value is 524, in the 525-line family.
 * Every V decode is generated against that bound and not against the bound of
 * its own mode: a mode change is gated to vertical blank (19 item 5) but the
 * counter still holds a 525-family value at the instant VMODE[0] falls, and a
 * decode that assumed max = 448 could fire on it. */
const V_MAX = V525.lines - 1

const vRange = (lo: number, hi: number, qualify: string[]) =>
  rangeTerms({ bits: VB, lo, hi, max: V_MAX, qualify })

/* =====================================================================
 * hgen - the slot counter and the horizontal decodes
 * ===================================================================== */

const hCount = counterTerms({ bits: HB, enable: "CE", terminal: H_LAST })

const hSyncRaw = rangeTerms({ bits: HB, lo: 0, hi: H.syncEnd, max: H.last })
const hSyncNot = rangeTerms({ bits: HB, lo: H.syncEnd + 1, hi: H.last, max: H.last })

export const hgenDesign: Design = {
  name: "hgen",
  partNo: "ARM6309-UV1",
  location: "video card - horizontal timing",
  signature: "A6309V1",
  clockPin: 1,

  inputs: [
    /* One slot per four dots. The sequencer pair already forms the dot phase
     * for the pixel mux (14), so this is that signal and not a second
     * divider: putting a two-bit phase counter here would cost two macrocells
     * on the one part that has none. */
    { name: "CE", pin: 2 },
    { name: "RESET", pin: 3, activeLow: true },
    /* HPOL is strapped to 1 - HSYNC is negative in both families (6.2.1).
     * Carrying it as an input rather than a constant costs four product terms
     * on a macrocell with ten to spare, and makes an out-of-spec monitor a
     * re-burn instead of a cut trace. */
    { name: "HPOL", pin: 4 },
  ],

  cells: [
    /* The counter bits are in pin order deliberately: they are the only
     * observable state of the horizontal timing and a scope wants them
     * adjacent. Terms grow with bit significance (2,3,4,6,8,10,8,6) and the
     * 22V10's allocation grows the same way from pin 14, so pin order and
     * term order agree here without being made to. */
    ...HB.map((name, i) => ({
      pin: 14 + i, name, assertedLow: false, s0: 1 as const,
      registered: true, terms: hCount[i],
    })),

    /* HSYNC = raw XOR HPOL. With HPOL strapped high the pin is low through
     * the window, which is what "negative" means at the connector. */
    {
      pin: 22, name: "HSYNC", assertedLow: false, s0: 1, registered: false,
      why: "polarity carried as an input, not strapped in silicon",
      terms: [
        ...hSyncRaw.map((t) => `${t} & !HPOL`),
        ...hSyncNot.map((t) => `${t} & HPOL`),
      ],
    },

    /* Everything that is not active video: the sync pulse, the back porch and
     * the front porch. 9.2 needs this to reach the post-LUT '273 as part of
     * BLANK, and 12.1 needs it in VSTAT. */
    {
      pin: 23, name: "HBLANK", assertedLow: false, s0: 1, registered: false,
      terms: [
        ...rangeTerms({ bits: HB, lo: 0, hi: H.backEnd, max: H.last }),
        ...rangeTerms({ bits: HB, lo: H.activeEnd + 1, hi: H.last, max: H.last }),
      ],
    },
  ],

  ar: "RESET",
}

/* =====================================================================
 * vgen - the line counter, and nothing else, because there is no room
 * ===================================================================== */

/* The line advances on the last slot of the line. That conjunction is the
 * slot counter's terminal count, read back across the backplane as five pins
 * rather than eight - the partial decode pays for itself twice. Using it as
 * the clock enable rather than as a separate LINEADV macrocell on hgen is
 * what keeps hgen at ten. */
const LINE_ADV = `CE & ${H_LAST}`

const vCount = counterTerms({ bits: VB, enable: LINE_ADV, terminal: "VTC" })

export const vgenDesign: Design = {
  name: "vgen",
  partNo: "ARM6309-UV2",
  location: "video card - line counter",
  signature: "A6309V2",
  clockPin: 1,

  inputs: [
    { name: "CE", pin: 2 },
    { name: "RESET", pin: 3, activeLow: true },
    /* From vdec. The line counter's modulus depends on VMODE[0], and the
     * decode of it cannot live on this part - all ten macrocells are counter
     * bits. The round trip is combinational and it has an entire line to
     * settle in: V changes once per 31.78 us, so the 15 ns through vdec is
     * not in any critical path despite crossing two packages. */
    { name: "VTC", pin: 4 },
    /* The five bits of the slot counter's terminal count. */
    { name: "H0", pin: 5 }, { name: "H1", pin: 6 }, { name: "H2", pin: 7 },
    { name: "H6", pin: 8 }, { name: "H7", pin: 9 },
  ],

  /* PIN ORDER IS NOT BIT ORDER HERE AND CANNOT BE. A ten-bit counter behind a
   * six-literal clock enable costs bit i exactly i + 7 product terms, so the
   * bits want 7,8,9,...,16 and the 22V10 offers 8,10,12,14,16,16,14,12,10,8.
   * The only assignment that fits pairs them in sorted order, which
   * interleaves the bits across the package: even bits climb pins 14..18 and
   * odd bits descend pins 23..19. This is a zero-slack fit - V9 needs all 16
   * terms of pin 19's macrocell. */
  cells: [
    { pin: 14, name: "V0", assertedLow: false, s0: 1, registered: true, terms: vCount[0] },
    { pin: 23, name: "V1", assertedLow: false, s0: 1, registered: true, terms: vCount[1] },
    { pin: 15, name: "V2", assertedLow: false, s0: 1, registered: true, terms: vCount[2] },
    { pin: 22, name: "V3", assertedLow: false, s0: 1, registered: true, terms: vCount[3] },
    { pin: 16, name: "V4", assertedLow: false, s0: 1, registered: true, terms: vCount[4] },
    { pin: 21, name: "V5", assertedLow: false, s0: 1, registered: true, terms: vCount[5] },
    { pin: 17, name: "V6", assertedLow: false, s0: 1, registered: true, terms: vCount[6] },
    { pin: 20, name: "V7", assertedLow: false, s0: 1, registered: true, terms: vCount[7] },
    { pin: 18, name: "V8", assertedLow: false, s0: 1, registered: true, terms: vCount[8] },
    { pin: 19, name: "V9", assertedLow: false, s0: 1, registered: true, terms: vCount[9] },
  ],

  ar: "RESET",
}

/* =====================================================================
 * vdec - every decode of the line counter, and the VBL interrupt
 * ===================================================================== */

const vSyncRaw = vRange(0, V449.syncEnd, [])
const vSyncNot = vRange(V449.syncEnd + 1, V_MAX, [])

export const vdecDesign: Design = {
  name: "vdec",
  partNo: "ARM6309-UV3",
  location: "video card - vertical decodes and VBL",
  signature: "A6309V3",
  clockPin: 1,

  /* No RESET pin, and that is deliberate rather than an omission: the only
   * register here is VBLPEND, the 22V10 powers its registers up low (ATF22V10C
   * datasheet 4.7), and CTRL resets to 0 so IRQEN is low until software says
   * otherwise. The pin it saves is the only spare this part has. */
  inputs: [
    { name: "M0", pin: 2 },       // VMODE[0]: 0 = 449 lines, 1 = 525
    { name: "HBLANK", pin: 3 },   // from hgen
    { name: "IRQEN", pin: 4 },    // CTRL bit 6
    { name: "VSTATWR", pin: 5 },  // a write to VSTAT clears the pending flag
    { name: "V0", pin: 6 }, { name: "V1", pin: 7 }, { name: "V2", pin: 8 },
    { name: "V3", pin: 9 }, { name: "V4", pin: 10 }, { name: "V5", pin: 11 },
    { name: "V6", pin: 13 },
    /* THREE macrocell pins carrying inputs, and exactly three are available:
     * seven of this part's ten macrocells are outputs. Eleven dedicated
     * inputs plus three is fourteen, and fourteen is what the decodes need.
     * There is no spare pin on this part. */
    { name: "V7", pin: 14 }, { name: "V8", pin: 15 }, { name: "V9", pin: 23 },
  ],

  cells: [
    /* The mode-dependent modulus, sent back to vgen. Two terms, and the
     * partial decodes are exact against a counter that reaches 524: 448 is
     * the only reachable value with V8, V7 and V6 all set and V9 clear, and
     * 524 the only one with V9, V3 and V2 all set. */
    {
      pin: 16, name: "VTC", assertedLow: false, s0: 1, registered: false,
      terms: [
        ...vRange(V449.lines - 1, V449.lines - 1, ["!M0"]),
        ...vRange(V525.lines - 1, V525.lines - 1, ["M0"]),
      ],
    },

    /* VSYNC = raw XOR VMODE[0], and this is the output 6.2.1 says the monitor
     * uses to pick the vertical format. The sync window is v <= 1 in BOTH
     * families - that is what the origin choice in sync.timing.ts buys, and it
     * is why this is ten product terms rather than a mode-dependent window
     * compare doubled by the XOR. */
    {
      pin: 19, name: "VSYNC", assertedLow: false, s0: 1, registered: false,
      why: "polarity is a function of VMODE[0] - graphics.md 6.2.1",
      terms: [
        ...vSyncRaw.map((t) => `${t} & !M0`),
        ...vSyncNot.map((t) => `${t} & M0`),
      ],
    },

    /* Everything outside active video, in whichever family is selected. */
    {
      pin: 18, name: "VBLANK", assertedLow: false, s0: 1, registered: false,
      terms: [
        ...vRange(0, V449.backEnd, ["!M0"]),
        ...vRange(V449.activeEnd + 1, V449.lines - 1, ["!M0"]),
        ...vRange(0, V525.backEnd, ["M0"]),
        ...vRange(V525.activeEnd + 1, V525.lines - 1, ["M0"]),
      ],
    },

    /* The post-LUT '273's /MR (9.2): blank is black, asynchronously, rather
     * than an output enable. */
    {
      pin: 17, name: "BLANK", assertedLow: false, s0: 1, registered: false,
      terms: ["VBLANK", "HBLANK"],
    },

    /* One dot of delay on the sync window, so the flag below sets on an edge.
     * Without it VBLPEND is a level for the whole window and re-arms itself
     * under its own handler: the 6809 takes about 10 us to enter an
     * interrupt and the window is 63.5 us, so the handler would clear the
     * flag and be interrupted again by the same frame. */
    {
      pin: 20, name: "VSDLY", assertedLow: false, s0: 1, registered: true,
      terms: vSyncRaw,
    },
    {
      pin: 21, name: "VBLPEND", assertedLow: false, s0: 1, registered: true,
      terms: [...vSyncRaw.map((t) => `${t} & !VSDLY`), "VBLPEND & !VSTATWR"],
    },

    /* 12.1's open-drain idiom: a 22V10's outputs are totem-pole, so the data
     * is a constant 0 and the condition goes on the output enable. The pin
     * drives low or floats, never high, and the macrocell's single OE product
     * term is spent doing it. */
    {
      pin: 22, name: "IRQ", assertedLow: true, s0: 1, registered: false,
      why: "open-drain by the OE idiom - the one OE term is spent",
      terms: [],
      oe: "VBLPEND & IRQEN",
    },
  ],
}
