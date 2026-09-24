import { place } from "../../tools/gal/jedec/place"
import type { Cell, Design } from "../../tools/gal/jedec/assemble"

/* ------------------------------------------------------------------------
 * sdbus - the storage card's bus face: the $FF58 decode, the four register
 * strobes, and the three bits of SDSTAT it drives.
 *
 * ** THE CARD (sdcard.md §3.1, NormalLuser's BE6502 interface). A read of
 * SDDATA puts the byte the PREVIOUS burst shifted in onto the bus and starts
 * the burst that fetches the next one; software never counts a clock. The
 * block comes through the port, and §4.4's chunk-and-mask discipline - 32
 * bytes with /IRQ and /FIRQ masked - is what makes a TFM loop safe against a
 * read-triggered port. 537 KiB/s.
 *
 * ** WHY THIS PART IS THE DECODE AND THE STATUS DRIVE, which is not the
 * obvious pairing: SDSTAT's b0 is BUSY and its OE is a decode, so the drive
 * has one input from the engine and one from here. Put it with SDCTRL - the
 * register it shares a data bus with - and BUSY, CD, WP and RDST all cross a
 * part boundary, which costs a pin at each end. `census.ts` searches every
 * partition and this is the one that fits two GAL22V10s; the pairing §8.1
 * assumes needs four.
 *
 * ** THE DECODE IS A0-A6, SEVEN BITS (§6.1). /IOSEL is /IOPAGE & /A7, so A7
 * comes free and A6..A2 are ours: $58 = 0101_1000. ⛔ A card matching only
 * A0-A5 answers at $FF58 AND at $FF18, which is inside the machine's free
 * space and would be found by the next card to take it, not by us.
 *
 * ** THE REGISTERS (§6.2), all four inside SEL:
 *
 *   +$0 SDDATA  R: the previous burst's byte, off the '595 -> OE595
 *               W: load the MOSI hold register -> MOSICK
 *               either way the access TRIGGERS a burst -> DATSTB
 *   +$1 SDSTAT  R: b0 a burst is owed OR running, b1 CD, b2 WP -> RDST
 *               enables D0-D2
 *   +$2 SDCTRL  W: b0 /CS, b1 clock rate, b7 soft reset -> CTRLW
 *   +$3 SDMOSI  W: load the hold register WITHOUT a burst -> MOSICK only
 *
 * ⚠ MOSICK IS ACTIVE LOW AND THE EDGE IS THE POINT. The '574 latches on a
 * RISING edge, and §6.2 requires the hold register to be loaded before the
 * '165 takes it - so the pin is held low through E-high of the write and
 * released at E-fall, which is the same instant DATSTB releases. The burst
 * cannot start before the next CLK25 edge (sdeng is registered), so the
 * order is guaranteed rather than raced.
 *
 * ⚠ AND DATSTB IS A LEVEL, NOT A PULSE. sdeng takes its FALLING edge, so a
 * burst starts when the access ENDS. §6.5's re-trigger lockout is there and
 * not here.
 *
 * ** PURELY COMBINATIONAL, so pin 1 is an ordinary input (v3lane's call).
 * ------------------------------------------------------------------------ */

/* $FF58-$FF5B, inside /IOSEL's $FF00-$FF7F window. Five literals, and they
 * ride in every term rather than costing a macrocell of their own. */
const SEL = "IOSEL & A6 & !A5 & A4 & A3 & !A2"
const R = (n: number) => `${n & 2 ? "A1" : "!A1"} & ${n & 1 ? "A0" : "!A0"}`

const cells: Cell[] = [
  /* an SDDATA access of either direction: the burst trigger (§3.1) */
  { pin: 0, name: "DATSTB", assertedLow: false, s0: 1, terms: [`${SEL} & ${R(0)} & E`] },
  /* SDSTAT read: the output enable for D0-D2 below */
  { pin: 0, name: "RDST", assertedLow: false, s0: 1, terms: [`${SEL} & ${R(1)} & RW & E`] },
  /* SDCTRL write: sdeng clocks its two bits and the soft reset off this */
  { pin: 0, name: "CTRLW", assertedLow: false, s0: 1, terms: [`${SEL} & ${R(2)} & !RW & E`] },
  /* the '595's three-state output onto D0-D7 - an SDDATA READ and nothing
   * else. ⚠ Not the same term as DATSTB: a WRITE to SDDATA also triggers a
   * burst, and the '595 must not drive the bus the CPU is driving. */
  { pin: 0, name: "OE595", assertedLow: true, s0: 0, terms: [`${SEL} & ${R(0)} & RW & E`] },
  /* the '574 MOSI hold register's clock: SDDATA or SDMOSI, written. Active
   * low so the LATCHING edge is E-fall - see the header. */
  { pin: 0, name: "MOSICK", assertedLow: true, s0: 0,
    terms: [`${SEL} & ${R(0)} & !RW & E`, `${SEL} & ${R(3)} & !RW & E`] },

  /* SDSTAT (§6.3), driven onto the backplane's D0-D2 during RDST.
   * ⚠ b3 DONE is gone with the fill engine; b4-b7 read as zero, and nothing
   * drives them - a 6809 read of an undriven bit is the bus's own float and
   * the driver masks. */
  /* ⛔ b0 IS "A BURST IS OWED OR RUNNING", NOT BUSY ALONE, and the reason is
   * a start-up window software cannot otherwise see. sdeng sets TRIGP at
   * E-fall but does not raise BUSY until the SPI clock's next FALLING edge -
   * up to 64 dots, which at the init rate is 2.54 us, FIVE BUS CYCLES. A
   * driver polling "until BUSY is clear" walks straight through that window,
   * touches SDDATA mid-burst and gets §6.5's duplicated byte, which §9.1
   * calls the silent data-destroying failure. TRIGP is a real pin on sdeng,
   * so the fix is one literal and the last free pin on this part. */
  { pin: 0, name: "SD0", assertedLow: false, s0: 1, oe: "RDST", terms: ["BUSY", "TRIGP"] },
  { pin: 0, name: "SD1", assertedLow: false, s0: 1, oe: "RDST", terms: ["CD"] },
  { pin: 0, name: "SD2", assertedLow: false, s0: 1, oe: "RDST", terms: ["WP"] },
]

/* Eight equations, all of one or two terms, so any assignment fits. Pins 22
 * and 23 are kept back for TRIGP and WP, which have nowhere else to go -
 * twelve dedicated inputs are exactly used by the bus. ⚠ The part is now at
 * 22 of 22 pins and has no headroom at all. */
const pins = place(cells, [14, 15, 16, 17, 18, 19, 20, 21])

export const sdbusDesign: Design = {
  name: "sdbus",
  partNo: "ARM6309-SDB",
  location: "storage card - the $FF58 decode, the register strobes and SDSTAT",
  signature: "A6309SB",
  inputs: [
    /* the window strobe: /IOPAGE & /A7, common to every slot (machine.md §2) */
    { name: "IOSEL", pin: 1, activeLow: true },
    { name: "A6", pin: 2 }, { name: "A5", pin: 3 }, { name: "A4", pin: 4 },
    { name: "A3", pin: 5 }, { name: "A2", pin: 6 },
    { name: "A1", pin: 7 }, { name: "A0", pin: 8 },
    { name: "RW", pin: 9 },
    /* E qualifies every strobe: an address is valid long before its data is */
    { name: "E", pin: 10 },
    /* from sdeng */
    { name: "BUSY", pin: 11 },
    /* the socket's two mechanical switches, both closed to ground */
    { name: "CD", pin: 13, activeLow: true },
    { name: "WP", pin: 23, activeLow: true },
    /* from sdeng: a burst is owed but has not started yet - see SD0 */
    { name: "TRIGP", pin: 22 },
  ],
  cells: cells.map((c) => ({ ...c, pin: pins[c.name] })),
  spares: [],
}
