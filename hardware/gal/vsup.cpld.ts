/* vsup - the video card's THIRD ATF1508AS, graphics.md 10.1.7.
 *
 * ** IT IS A PACKAGE REDUCTION, NOT AN ADDITION. The card carried three
 * GAL22V10s and every one of them was a package for the same reason: a block
 * that would not fit either CPLD's PINS, never its macrocells.
 *
 *   rfa    the register-file address (10.1.6.3) - RA4..RA0, WSTB and CTRL's
 *          and VSTAT's write strobes. 8 of 10 macrocells.
 *   vlen   7.4's span-solid length counter - a package because it loaded from
 *          the register file's read bus, which is eight pins neither CPLD had.
 *          10 of 10.
 *   pxsel  8.2's fetch-rank select and HSCROLL[1:0]'s third copy - a package
 *          because vctrl is at 64 of 64 and cannot export the two bits it
 *          holds. 8 of 10.
 *
 * Three packages, 26 macrocells and 24 of 30 DIP-24 pins between them. One
 * PLCC-84 holds all three with ~100 macrocells to spare, which is the whole
 * argument: three GALs -> one CPLD is -2 packages before it does anything
 * else, and every signal that crossed between them stops being a pin.
 *
 * ** AND THE SPARE ROOM IS WHAT THE CARD WAS SHORT OF. Two things graphics.md
 * puts in v1 were unbuildable on a card of two CPLDs, both for want of pins
 * and not of logic:
 *
 *   9's palette write path   ⛔ WHICH HAD NO PRODUCER AT ALL. It costs 13 pins
 *                            - eight for the LUT's address bus and five for
 *                            the strobes - and vctrl has 0 spare and vaddr 2.
 *                            vsup.parts.ts has the census.
 *   10.3.2's register port   a list MOVE can only reach a register on the part
 *                            that decodes the descriptor, and until now that
 *                            was vaddr, which holds the scroll pair and
 *                            nothing else worth writing per scanline.
 *
 * ** WHAT IT STILL CANNOT REACH, AND WHY, is CTRL - 10.3.4 states it. vctrl's
 * D0..D7 tap the BACKPLANE data bus, because 7.4's mask serialiser loads the
 * CPU's byte at WSTBV, a posted VRAM write, at an instant when the register
 * file is still driving the card's internal bus. An operand placed on the
 * internal bus therefore never reaches CTRL's write terms, and moving vctrl's
 * data port would break either the serialiser or the span writer's colour
 * path. Mid-frame VMODE and WMODE stay CPU-only.
 *
 * ** NOTHING IS RETYPED. rfa, vlen and pxsel are merged as the same Cell term
 * lists regfile.check.ts, vlen.check.ts and pxsel.check.ts exercise as
 * GAL22V10 fuse maps, so those three checks keep running unchanged and this
 * part inherits every claim they make. Same rule audio.cpld.ts and
 * video.cpld.ts follow: one origin, several devices.
 */

import { merge, rename, toCupl, type Merged } from "./jedec/cupl"
import { rfaDesign } from "./regfile.jedec"
import { vlenDesign } from "./vlen.jedec"
import { pxselDesign } from "./pxsel.jedec"
import { listDecode, paletteWrite, spanLength, vsupStrobes } from "./vsup.parts"

/* ⚠ vlen's LOAD SOURCE IS NOT THE REGISTER FILE ANY MORE - vsup.parts.ts's
 * spanLength has the argument. RD7..RD0 were eight input pins carrying the
 * file's read bus so the counter could take 13's +$05; SPANLEN is eight
 * macrocells on this die now, so the rename is the whole change and the
 * GAL22V10 design, its fuse map and vlen.check.ts are untouched. */
const LEN_SRC: Record<string, string> =
  Object.fromEntries([0, 1, 2, 3, 4, 5, 6, 7].map((i) => [`RD${i}`, `SL${i}`]))

/* ⚠ pxsel's SECOND WRITE PORT MOVES FROM THE PIXEL BUS TO THE INTERNAL DATA
 * BUS, for the same reason vaddr's does (video.parts.ts): 10.3.3's '244 puts
 * the descriptor operand on D0..D7, so every register with a list port takes
 * its value from one bus rather than each part tapping whichever it has.
 *
 * LWHSL was a pin from vaddr and is a product term here - this die decodes the
 * descriptor now (vsup.parts.ts's listDecode), so the strobe is local, and the
 * pin runs the other way: vaddr imports it for HSCROLL[9:2]. */
const PXSEL_MAP: Record<string, string> = { PB0: "D0", PB1: "D1" }

export const vsupCpld: Merged = merge(
  [rfaDesign, rename(vlenDesign, LEN_SRC), rename(pxselDesign, PXSEL_MAP)],
  [...vsupStrobes, ...spanLength, ...listDecode, ...paletteWrite],
  {
    name: "vsup", partNo: "ARM6309-UV0C",
    location: "video card - register file, palette and list port",
    device: "f1508ispplcc84", clock: "DOTCLK",
    external: new Set([
      /* 10.1.6.3's register-file address, unchanged - to the file's own
       * address pins, and to vaddr, which decodes its own load strobes from
       * them. WSTB is the file's /WE as well. */
      "RA0", "RA1", "RA2", "RA3", "RA4", "WSTB",
      /* The two strobes rfa formed because vctrl gave up the address lines. */
      "WCTRL", "VSTATWR",
      /* 7.4's span-solid termination, to vctrl's seqctl. */
      "TC",
      /* 8.2's rank select. Six pins because a '574's /OE is one pin and the
       * two ranks share a net, so the pair must be complements on the board
       * and not inside an inverter that does not exist. */
      "OEA0", "OEA1", "OEA2", "OEB0", "OEB1", "OEB2",
      /* 9's palette write path: 13.1's turnaround on the LUT's two buses, the
       * '163 pair's load and count, and the two '573 latch enables. PIDX is
       * three packages off this die - vsup.parts.ts has why. */
      "PIXOE", "PDOE", "PWE", "PILD", "PINC", "LDPDL", "LDPDH",
      /* 10.3.3's descriptor buffer and the register file's output enable -
       * the two halves of one turnaround on the card's internal data bus. */
      "LDBOE", "RFOE",
      /* 10.3's engine, whose descriptor half is on this die now. What crosses
       * is three signals and no state: LADV is WPTR's increment, LWHSL and
       * LWHSH are 8's scroll holds, both on vaddr. LRUN is BSTAT b0 and goes
       * to vctrl's arbiter as well. */
      "LRUN", "LADV", "LWHSL", "LWHSH",
    ]),
  },
)

export const vsupSource = () => toCupl(vsupCpld)
