/* I/O card - PS/2 keyboard and mouse, and RS-232. 14 ICs, 12 cm.
 *
 * TWO CARDS UNTIL 2026-09-08, and what merges them is the $FF map rather than
 * the logic: ps2.md 3.2 takes four bytes and serial.md 7.1 the four above it.
 * One card decodes one window where two decoded two, and the machine gets a
 * slot back - six cards became five against six slots (hardware/README.md).
 *
 * SERIAL'S PART CHANGED ON 2026-09-09 and the count did not: serial.md 4.5's
 * 16C550 replaced the 6551 one-for-one. serial.md 5.4 and 9.1 both priced the
 * tier at "+1 IC" and that was a COUNTING ERROR - the tier table counted the
 * baud crystal as a package and the base count did not. Two DIPs and a GAL
 * before, two DIPs and a GAL after.
 *
 * The window moved to $FF30-$FF3F and doubled to sixteen bytes with it,
 * because a 16C550 has EIGHT registers where a 6551 has four and the eight
 * bytes this card held at $FF50 were wedged between audio at $FF40 and
 * storage at $FF58. cards/windows.ts carries that argument.
 *
 * 14 is 11 + 3 with nothing shared, which is the honest count and not the
 * cheapest one. The obvious saving is the second GAL22V10, and it is not free:
 * ps2.md 9 already calls its GAL the fitting risk at roughly ten macrocells of
 * ten, and the pressure is the DR latches and the /PL terms rather than the
 * decode. One ATF1508AS would absorb both GALs, the '273 and the '244 and take
 * the card to 11, which the retired house rule no longer forbids (root
 * README.md). Neither is specified; this file draws the 14.
 *
 * BOTH HALVES STAY SEPARATE ON /IRQ. machine.md 4.1 polls video, then net,
 * then PS/2, then serial LAST - because reading the 6551's STATUS clears the
 * interrupt and returns the error bits in the same read. Merging the cards
 * does not merge the handlers, and the order is unchanged.
 */
import { Card } from "../lib/Card"

/* Six packages, twice. ps2.md 12: '595 shift + storage, '193 bit counter
 * preset to 1010 = 10, '574 second-stage latch whose /OE is the read strobe. */
const Port = ({ id }: { id: "KB" | "MS" }) => (
  <group name={`port_${id}`}>
    <chip
      name={`U${id === "KB" ? 6 : 7}`}
      footprint="dip16_w0.3in"
      pinLabels={{
        pin1: "QB", pin2: "QC", pin3: "QD", pin4: "QE", pin5: "QF", pin6: "QG",
        pin7: "QH", pin8: "GND", pin9: "QHS", pin10: "nSRCLR", pin11: "SRCLK",
        pin12: "RCLK", pin13: "nOE", pin14: "SER", pin15: "QA", pin16: "VCC",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        /* ~OE tied enabled, /SRCLR tied high - it drives the '574, not the bus. */
        nOE: "net.GND", nSRCLR: "net.V5",
        SER: `net.${id}_DATA_S`, SRCLK: `net.${id}_CLK_S`,
      }}
    />
    <chip
      name={`U${id === "KB" ? 8 : 9}`}
      footprint="dip16_w0.3in"
      pinLabels={{
        pin1: "B", pin2: "QB", pin3: "QA", pin4: "nDOWN", pin5: "nUP",
        pin6: "QC", pin7: "QD", pin8: "GND", pin9: "D", pin10: "C",
        pin11: "nPL", pin12: "nTCU", pin13: "nTCD", pin14: "MR",
        pin15: "A", pin16: "VCC",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        /* preset strapped to 1010 = 10 - the eleven-bit PS/2 frame less start */
        A: "net.GND", B: "net.V5", C: "net.GND", D: "net.V5",
        MR: "net.GND", nPL: `net.${id}_PL`, nTCD: `net.${id}_TCD`,
        nUP: "net.V5",
      }}
    />
    <chip
      name={`U${id === "KB" ? 10 : 11}`}
      footprint="dip20_w0.3in"
      pinLabels={{
        pin1: "nOE", pin11: "CP", pin10: "GND", pin20: "VCC",
        pin2: "D1", pin3: "D2", pin4: "D3", pin5: "D4",
        pin6: "D5", pin7: "D6", pin8: "D7", pin9: "D8",
        pin19: "Q1", pin18: "Q2", pin17: "Q3", pin16: "Q4",
        pin15: "Q5", pin14: "Q6", pin13: "Q7", pin12: "Q8",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        /* Clocked by the DR latch at end-of-frame; /OE from the read strobe
         * drives the data bus directly. QA-QH of the '595 land on D7-D0
         * reversed - ps2.md 5.1. */
        CP: `net.${id}_DR`, nOE: `net.${id}_RD`,
        Q1: "net.D0", Q2: "net.D1", Q3: "net.D2", Q4: "net.D3",
        Q5: "net.D4", Q6: "net.D5", Q7: "net.D6", Q8: "net.D7",
      }}
    />
  </group>
)

export default () => (
  <Card name="arm6309-io" ioBase={0xff30} ioSize={16} icBudget={14} length={120}>
    {/* ---------------------------------------------------- PS/2 half --- */}

    {/* U1 - the PS/2 half: four register strobes, the two DR latches, the two
      * /PL terms, and open-drain /IRQ.
      *
      * ⭐ IT DOES NOT COMPARE THE BASE. U14 does that once for the whole card
      * and hands over CARD_SEL; this part adds A3 (0 = PS/2, 1 = serial) and
      * A1:A0. Two inputs instead of four, on a part ps2.md 9 already calls the
      * card's fitting risk at roughly ten macrocells of ten - and the window
      * moving to sixteen bytes on 2026-09-09 would otherwise have cost it
      * A4, A5 and A6 as well.
      *
      * ⚠ A6 was missing from this card's decode entirely until that pass;
      * the strobe is /IOPAGE AND /A7, so A6 is not implied by it and a
      * six-bit match answers 64 bytes below the base too (machine.md 2). It
      * is on U14 now, once. */}
    <chip
      name="U1"
      footprint="dip24_w0.3in"
      pinLabels={{
        pin1: "CLK", pin2: "CARD_SEL", pin3: "A0", pin4: "A1", pin5: "E",
        pin6: "R_W", pin7: "nRESET", pin8: "KB_TCD", pin9: "MS_TCD",
        pin10: "A3", pin12: "GND",
        pin18: "KB_PL", pin19: "MS_PL", pin20: "KB_DR", pin21: "MS_DR",
        pin22: "KB_RD", pin23: "nIRQ", pin24: "VCC",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        CARD_SEL: "net.CARD_SEL", A0: "net.A0", A1: "net.A1", A3: "net.A3",
        E: "net.E", R_W: "net.R_W",
        /* ⚠ New since the 2026-09-04 review. This card had no power-on reset
         * path at all until design-review.md IO-P3; the serial card already
         * did it right. */
        nRESET: "net.nRESET",
        nIRQ: "net.nIRQ",
        KB_TCD: "net.KB_TCD", MS_TCD: "net.MS_TCD",
        KB_PL: "net.KB_PL", MS_PL: "net.MS_PL",
        KB_DR: "net.KB_DR", MS_DR: "net.MS_DR", KB_RD: "net.KB_RD",
      }}
      noConnect={["CLK"]}
    />

    {/* U2 - IOCTRL. A '273 and not a '574 precisely because its asynchronous
      * /MR clears all eight bits from backplane /RESET (ps2.md 8.4). */}
    <chip
      name="U2"
      footprint="dip20_w0.3in"
      pinLabels={{
        pin1: "nMR", pin11: "CP", pin10: "GND", pin20: "VCC",
        pin2: "Q1", pin3: "D1", pin4: "D2", pin5: "Q2", pin6: "Q3",
        pin7: "D3", pin8: "D4", pin9: "Q4",
        pin12: "Q5", pin13: "D5", pin14: "D6", pin15: "Q6",
        pin16: "Q7", pin17: "D7", pin18: "D8", pin19: "Q8",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND", nMR: "net.nRESET",
        D1: "net.D0", D2: "net.D1", D3: "net.D2", D4: "net.D3",
        D5: "net.D4", D6: "net.D5", D7: "net.D6", D8: "net.D7",
      }}
    />

    {/* U3 - IOSTAT, six status bits three-stated onto the bus. */}
    <chip
      name="U3"
      footprint="dip20_w0.3in"
      pinLabels={{
        pin1: "n1OE", pin19: "n2OE", pin10: "GND", pin20: "VCC",
        pin2: "1A1", pin4: "1A2", pin6: "1A3", pin8: "1A4",
        pin18: "1Y1", pin16: "1Y2", pin14: "1Y3", pin12: "1Y4",
        pin11: "2A1", pin13: "2A2", pin15: "2A3", pin17: "2A4",
        pin9: "2Y1", pin7: "2Y2", pin5: "2Y3", pin3: "2Y4",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        "1Y1": "net.D0", "1Y2": "net.D1", "1Y3": "net.D2", "1Y4": "net.D3",
        "2Y1": "net.D4", "2Y2": "net.D5",
      }}
    />

    {/* U4 - 7407 open-collector, 4 of 6 gates: the whole transmit datapath.
      * U5 - 74HCT132 Schmitt, all four gates consumed by 2 ports x CLK/DATA.
      * HCT and not HC for the reason ps2.md 4.2 gives. */}
    <chip name="U4" footprint="dip14_w0.3in" pinLabels={{ pin7: "GND", pin14: "VCC" }}
      connections={{ VCC: "net.V5", GND: "net.GND" }} />
    <chip name="U5" footprint="dip14_w0.3in" pinLabels={{ pin7: "GND", pin14: "VCC" }}
      connections={{ VCC: "net.V5", GND: "net.GND" }} />

    <Port id="KB" />
    <Port id="MS" />

    {/* ps2.md 12: two polyfuses, because a shorted mini-DIN pin 4 without one
      * takes down the whole backplane rail. Each port's +5 V goes through one. */}
    <fuse name="F1" currentRating="0.5A" footprint="1206" connections={{ pin1: "net.V5", pin2: "net.KB_VBUS" }} />
    <fuse name="F2" currentRating="0.5A" footprint="1206" connections={{ pin1: "net.V5", pin2: "net.MS_VBUS" }} />

    {/* -------------------------------------------------- serial half --- */}

    {/* U12 - the UART. A TL16C550C, not the 6551 this card carried until
      * 2026-09-09 - serial.md 4.5's tier 1, taken.
      *
      * THREE OF THIS CARD'S PROBLEMS STOP EXISTING with the part:
      *   - no FIFO. A 6551 takes one interrupt per byte; this takes one per
      *     fourteen, which is what moves DriveWire from 37 % of the CPU to
      *     16 % (drivewire.md 3)
      *   - 19,200 baud. This reaches 115,200 from the same crystal
      *   - the sourcing trap AND the speed grade. serial.md 3.3's W65C51N
      *     defect and 3.4's fast-E rating both go: this part is clocked by
      *     its own crystal and never sees backplane E at all
      *
      * ⚠ THE PINOUT IS UNVERIFIED. There is no TL16C550C datasheet in
      * reference/datasheets/ and the numbering below is written from
      * familiarity - the failure mode hardware/history.md finding 4 records.
      * Check the PDIP-40 package specifically: TI's current catalogue lists
      * FN (PLCC-44) and PT (TQFP-48), and whether the DIP is still made is
      * the first question about the part (net.md 13.6).
      *
      * ⚠ INTR IS ACTIVE HIGH AND TOTEM-POLE. The 6551's /IRQ was open-drain
      * and wire-ORed onto the backplane directly; THIS PART CANNOT. It goes
      * to U14, which inverts it onto the shared line through an open-drain
      * macrocell - machine.md 5 item 9's idiom, and one macrocell.
      *
      * ADS is tied low (no address latching - the 6809 bus holds its address
      * for the whole cycle) and BAUDOUT feeds RCLK, which is the standard
      * arrangement when receive and transmit share one rate. */}
    <chip
      name="U12"
      manufacturerPartNumber="TL16C550CN"
      footprint="dip40_w0.6in"
      pinLabels={{
        pin1: "D0", pin2: "D1", pin3: "D2", pin4: "D3", pin5: "D4",
        pin6: "D5", pin7: "D6", pin8: "D7", pin9: "RCLK", pin10: "SIN",
        pin11: "SOUT", pin12: "CS0", pin13: "CS1", pin14: "nCS2",
        pin15: "nBAUDOUT", pin16: "XIN", pin17: "XOUT", pin18: "nWR",
        pin19: "WR", pin20: "GND", pin21: "RD", pin22: "nRD", pin23: "nDDIS",
        pin24: "nTXRDY", pin25: "ADS", pin26: "A2", pin27: "A1", pin28: "A0",
        pin29: "nRXRDY", pin30: "INTR", pin31: "nOUT2", pin32: "nRTS",
        pin33: "nDTR", pin34: "nOUT1", pin35: "MR", pin36: "nCTS",
        pin37: "nDSR", pin38: "nDCD", pin39: "nRI", pin40: "VCC",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        D0: "net.D0", D1: "net.D1", D2: "net.D2", D3: "net.D3",
        D4: "net.D4", D5: "net.D5", D6: "net.D6", D7: "net.D7",
        /* Eight registers, so THREE address lines where the 6551 needed two.
         * That is what moved the card's window - windows.ts. */
        A0: "net.A0", A1: "net.A1", A2: "net.A2",
        /* Intel-style strobes, synthesised from E and R/W on U14 - one
         * product term each (serial.md 9.1). The active-high halves are
         * tied off. */
        nRD: "net.SER_RD", nWR: "net.SER_WR", RD: "net.GND", WR: "net.GND",
        CS0: "net.V5", CS1: "net.V5", nCS2: "net.SER_CS",
        ADS: "net.GND",
        /* MR is ACTIVE HIGH where backplane /RESET is active low, so it comes
         * from U14 inverted. The 6551 took /RESET straight through, which
         * serial.md 6 called out as a property this card had for free; it
         * costs one macrocell now. */
        MR: "net.SER_MR",
        INTR: "net.SER_INTR",
        XIN: "net.BAUD_XTAL",
        /* Receive and transmit share one rate. */
        nBAUDOUT: "net.BAUDOUT", RCLK: "net.BAUDOUT",
      }}
      noConnect={["nTXRDY", "nRXRDY", "nDDIS", "nOUT1", "nOUT2", "nRI", "XOUT"]}
    />

    {/* 7.3728 MHz, and it is the UART's own - not the backplane master.
      *
      * ⭐ FOUR TIMES THE 6551's 1.8432 MHz, and it costs the same. 115,200 is
      * then divisor 4 and 460,800 is divisor 1, so the rate this machine plans
      * against (drivewire.md 3) and the one it might want later come off one
      * can. serial.md 9.1 specified it with the tier.
      *
      * ⚠ THE LEVEL SHIFTER IS THE CEILING, not the crystal: an MAX232-class
      * charge pump is specified to 120 kbit/s, so 230,400 and above need U13
      * reconsidered (serial.md 8). 115,200 is what the card is planned at. */}
    <crystal
      name="Y1"
      frequency="7.3728MHz"
      loadCapacitance="18pF"
      footprint="hc49"
      connections={{ pin1: "net.BAUD_XTAL", pin2: "net.GND" }}
    />
  </Card>
)
