/* The span writer's control state machine, respecified for 8 x 8 cells.
 *
 * graphics.md 14 lists "span control" among the sequencer pair's duties and
 * nothing in that document says what it is - the mechanism is inherited from
 * minimal256, which was designed around 6-pixel cells. 6.1 already says what
 * changes at 8 x 8 and stops short of the consequence:
 *
 *   "colormin's span-mask serialises a byte and stops at SPANLEN; with 6-px
 *    cells two bits per write are wasted. At 8x8 the mask byte IS the glyph
 *    row."
 *
 * THE CONSEQUENCE IS THAT SPAN-MASK MODE DOES NOT CONSULT SPANLEN AT ALL.
 * Its length is eight, always, because eight is the cell width; the byte the
 * CPU writes is exactly one glyph row and there is nothing to truncate. So
 * the length comes from a three-bit counter here - three bits because a cell
 * is eight wide - and the '161 pair's SPANLEN belongs to span-solid alone.
 *
 * That is what makes 7.3's "13 writes per character cell" arithmetic true:
 * WPTR (3) + WFG + WBG = 5 of setup, then 8 glyph rows. SPANLEN is not among
 * them. Had mask mode needed SPANLEN it would be 14, and the text engine's
 * headline number is 7 % worse.
 *
 * Everything else is one uniform per-byte handshake:
 *
 *   WSTB          a posted write has been latched (3.1.1's '574s hold the
 *                 address, the data, R/W and WMODE) - start a span
 *   SPNGRANT      the arbiter matched WPTR[1:0] against the CPU's chip and
 *                 gave the span writer a spare access (5.2.1)
 *   RETIRE        one byte goes to VRAM. Drives WPTR's WINC, the '165's
 *                 shift and the '161's count - one signal, three loads
 *   SPANEND       the last byte of the span retired
 *
 * and the mask bit itself never enters this part: the '165's serial output
 * is wired to the register file's address bit 0, which is why 13 requires
 * WFG at A0 = 0 and WBG at A0 = 1. Choosing the source colour costs no
 * macrocell and no product term - it is an address line.
 */

import { counterTerms } from "./jedec/counter"
import { place } from "./jedec/place"
import type { Cell, Design } from "./jedec/assemble"

/* WMODE[1:0], 13: 00 direct, 01 span-mask, 10 span-solid, 11 sprite. */
const DIRECT = "!WM1 & !WM0"
const MASK = "!WM1 & WM0"
const SOLID = "WM1 & !WM0"
/* features.md 8.4. Eight bytes like mask, but a zero mask bit advances the
 * pointer without writing - which is what deletes save-behind for the shape. */
const SPRITE = "WM1 & WM0"

const MC = ["MC0", "MC1", "MC2"]
/* Zeroed at the start of every span, counting one per retired byte. Three
 * bits is the cell width and nothing else.
 *
 * ⚠ AND IT CANNOT BE A SENTINEL IN THE SERIALISER, which is worth recording
 * because it looks as though it can. Load the mask as {mask[7:0], 1} and shift
 * left, and the extra 1 does reach bit 7 after seven shifts - but SO DOES
 * MASK DATA: after k shifts bit 7 holds mask[6-k], and a set bit there fires
 * the terminator early. Simulated, a $B4 sprite ended after two bytes. A
 * counter and a shift register look interchangeable until the data is allowed
 * to be anything, and mask data is exactly that. */
const mcTerms = counterTerms({ bits: MC, enable: "RETIRE" })
  .map((bit) => bit.map((t) => `!WSTB & ${t}`))

const cells: Cell[] = [
  /* A span is in flight from the posted write until its last byte retires.
   * This is VSTAT bit 7 and it is the /WAIT condition on the arbiter. */
  {
    pin: 0, name: "SPANBUSY", assertedLow: false, s0: 1, registered: true,
    terms: ["WSTB", "SPANBUSY & !SPANEND"],
  },

  /* The arbiter has already matched the chip, so a grant while busy is
   * simply "go". One output drives WPTR's column increment, the serialiser's
   * shift and the length counter's enable: the three things that advance
   * together by construction.
   *
   * ⚠ SPNTICK IS NEW - 2026-09-09 - and without it a span retires FOUR bytes
   * per fetch slot. 5.2.1's arbiter has no phase term at all; it is pure
   * combinational grant logic, so SPNGRANT is asserted for every dot of the
   * spare window and RETIRE fired on each. 7.4's entire timing model is one
   * byte per 158.9 ns slot - 6.29 MB/s, the 40.7 us SPANBUSY bound, the
   * polygon crossover. SPNTICK is the last dot of the spare half
   * (video.cpld.ts), so the retire lands after the access has completed and
   * exactly once per slot. design-review2.md V-4. */
  {
    pin: 0, name: "RETIRE", assertedLow: false, s0: 1, registered: false,
    why: "also WPTR's WINC, the serialiser's shift and the length counter's enable",
    terms: ["SPANBUSY & SPNGRANT & SPNTICK"],
  },

  ...MC.map((name, i) => ({
    pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
    terms: mcTerms[i],
  })),

  /* Where the three modes differ, and the only place they do.
   *
   * Direct is one byte - 3.1.1's posted write, retired into the first free
   * slot. Mask is eight, counted here. Solid is SPANLEN + 1, counted by the
   * '161 pair, whose terminal count arrives as TC.
   *
   * Loading the '161 in mask mode is harmless and is why WSTB can drive both
   * the '165's load and the '161's load with no mode qualification: mask
   * mode terminates on MC and never looks at TC. */
  {
    pin: 0, name: "SPANEND", assertedLow: false, s0: 1, registered: false,
    terms: [
      `RETIRE & ${DIRECT}`,
      `RETIRE & ${MASK} & MC2 & MC1 & MC0`,
      `RETIRE & ${SOLID} & TC`,
      /* Sprite mode is a cell wide too - it is mask mode with the write
       * gated, so it ends on the same count. */
      `RETIRE & ${SPRITE} & MC2 & MC1 & MC0`,
    ],
  },

  /* ⭐ THE WHOLE OF SPRITE MODE, AND IT IS ONE MACROCELL.
   *
   * Every other mode writes every byte it retires, so RETIRE was the write
   * strobe as well as the advance. Sprite mode splits the two: the pointer,
   * the serialiser and the counter still step on RETIRE, and only the write
   * is suppressed on a transparent pixel.
   *
   * ⚠ THE POINTER MUST STILL ADVANCE. A mode that stalled it would draw the
   * sprite squashed - which is the reason this is a second output and not a
   * qualification of RETIRE.
   *
   * ⚠ AND THE MASK BIT HAS TO GET HERE. 7.4 is explicit that it never enters
   * the sequencer: the '165's serial output is wired to the register file's
   * address bit 0 and nowhere else, because choosing WFG or WBG per pixel is
   * an address line rather than logic. Sprite mode needs it in a SECOND place,
   * and on the card that is an input pin on vctrl - features.md 8.4. */
  {
    pin: 0, name: "WEN", assertedLow: false, s0: 1, registered: false,
    why: "RETIRE, except a transparent pixel in sprite mode",
    /* RETIRE & (not sprite mode, or the mask bit is set). The complement of
     * a two-literal AND is two terms, so this is three. */
    terms: ["RETIRE & !WM1", "RETIRE & !WM0", "RETIRE & MASKBIT"],
  },

  /* 13's WADV: 00 continue, 01 next row same column, 10 vertical. Both
   * non-zero modes advance WPTR's row at the end of the span; 01 also
   * reloads the column from 7.2's register-file shadow, which is the other
   * sequencer part's business because it drives the register-file address.
   *
   * ** !LRUN IS 19 ITEM 24, CLOSED 2026-09-09, AND IT IS FREE.
   *
   * 10.3.1: the list engine has no pointer of its own - WPTR is the list
   * pointer - and the engine's walk is a plain +1. WADV changes what an
   * increment DOES, so a driver that left WADV in vertical mode and then
   * started a list got an engine that stepped by 1,024. The item costed the
   * fix as "one product term on vctrl: BCTRL.GO forces WADV to 00".
   *
   * ** GATING HERE IS CHEAPER THAN CLEARING THE REGISTER, and it is also the
   * better semantics:
   *
   *   - ZERO product terms and zero macrocells. WADV acts on nothing except
   *     this signal, so one literal on each of two existing terms is the
   *     whole of it. Clearing the WADV register instead would have needed
   *     BCTRLGO as an input pin on vctrl, WHICH IS AT 64 OF 64 I/O.
   *   - LRUN rather than BCTRLGO, so it holds for the WHOLE walk and not just
   *     the instant it starts. A mid-list write to +$14 cannot break the walk
   *     either, which BCTRL.GO alone did not cover.
   *   - THE REGISTER IS NOT DESTROYED. Software's WADV survives the list, so
   *     10.3.1's reload rule stays "reload WPTR" and does not grow a second
   *     clause. Clearing the register would have added one.
   *
   * LRUN is already a pin on vctrl (vctrl.pld) because 10.3's BSTAT b0 reads
   * it back, so on the merged part this costs nothing at all; on the
   * standalone GAL it is pin 11, which was free. */
  {
    pin: 0, name: "WROWADV", assertedLow: false, s0: 1, registered: false,
    terms: ["SPANEND & WADV0 & !LRUN", "SPANEND & WADV1 & !LRUN"],
  },
]

/* Eight macrocells; the widest equation is four product terms. Placed on the
 * leanest eight so the two 16-term macrocells stay free. */
const pins = place(cells, [14, 15, 16, 17, 20, 21, 22, 23])

export const seqctlDesign: Design = {
  name: "seqctl",
  partNo: "ARM6309-UV10",
  location: "video card - span writer control",
  signature: "A6309VA",
  supersededBy: "graphics.md 10.1.6 - the video card is 2 x ATF1508AS",
  clockPin: 1,
  inputs: [
    { name: "RESET", pin: 2, activeLow: true },
    /* One pulse per posted write, from the E-fall latch of 3.1.1. */
    { name: "WSTB", pin: 3 },
    { name: "WM0", pin: 4 }, { name: "WM1", pin: 5 },
    { name: "SPNGRANT", pin: 6 },
    /* The '161 pair's terminal count - span-solid's length. */
    { name: "TC", pin: 7 },
    { name: "WADV0", pin: 8 }, { name: "WADV1", pin: 9 },
    /* ⚠ NEW, and it is the pin features.md 8.4's proposal turned on. The mask
     * serialiser's current bit - read only by sprite mode. */
    { name: "MASKBIT", pin: 10 },
    /* One dot per fetch slot, at the end of 5.2.2's spare window. */
    { name: "SPNTICK", pin: 13 },
    /* 19 item 24: the list engine owns WPTR while this is high, and its walk
     * is a plain +1. See WROWADV. */
    { name: "LRUN", pin: 11 },
  ],
  cells: cells.map((c) => ({ ...c, pin: pins[c.name] })),
  spares: [18, 19],
  ar: "RESET",
}
