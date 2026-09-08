/* I/O card - PS/2 keyboard and mouse, and RS-232. 14 ICs, 12 cm.
 *
 * TWO CARDS UNTIL 2026-09-08, and what merges them is the $FF map rather than
 * the logic: ps2.md 3.2 takes $FF50-$FF53 and serial.md 7.1 takes
 * $FF54-$FF57, which are contiguous. One card decodes eight bytes where two
 * decoded four each, and the machine gets a slot back - six cards became five
 * against six slots (hardware/README.md).
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
  <Card name="arm6309-io" ioBase={0xff50} ioSize={8} icBudget={14} length={120}>
    {/* ---------------------------------------------------- PS/2 half --- */}

    {/* U1 - decode, four register strobes, the two DR latches, the two /PL
      * terms, and open-drain /IRQ. */}
    <chip
      name="U1"
      footprint="dip24_w0.3in"
      pinLabels={{
        pin1: "CLK", pin2: "nIOSEL", pin3: "A0", pin4: "A1", pin5: "E",
        pin6: "R_W", pin7: "nRESET", pin8: "KB_TCD", pin9: "MS_TCD",
        pin12: "GND",
        pin18: "KB_PL", pin19: "MS_PL", pin20: "KB_DR", pin21: "MS_DR",
        pin22: "KB_RD", pin23: "nIRQ", pin24: "VCC",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        nIOSEL: "net.nIOSEL", A0: "net.A0", A1: "net.A1",
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

    {/* U12 - the ACIA. Four registers, which is exactly why the card asks for
      * four bytes. /IRQ is the fourth source on the shared line, and it is
      * polled last: reading STATUS clears the interrupt and returns the error
      * bits in the same read (machine.md 4.1). */}
    <chip
      name="U12"
      manufacturerPartNumber="R6551A"
      footprint="dip28_w0.6in"
      pinLabels={{
        pin1: "GND", pin2: "CS0", pin3: "nCS1", pin4: "nRES", pin5: "RxC",
        pin6: "XTLI", pin7: "XTLO", pin8: "nRTS", pin9: "nCTS", pin10: "TxD",
        pin11: "nDTR", pin12: "RxD", pin13: "RS0", pin14: "RS1",
        pin15: "VCC", pin16: "nDCD", pin17: "nDSR",
        pin18: "D0", pin19: "D1", pin20: "D2", pin21: "D3",
        pin22: "D4", pin23: "D5", pin24: "D6", pin25: "D7",
        pin26: "nIRQ", pin27: "PHI2", pin28: "R_W",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        D0: "net.D0", D1: "net.D1", D2: "net.D2", D3: "net.D3",
        D4: "net.D4", D5: "net.D5", D6: "net.D6", D7: "net.D7",
        RS0: "net.A0", RS1: "net.A1",
        R_W: "net.R_W", PHI2: "net.E",
        /* serial.md 6 wires backplane /RESET straight to the ACIA - the card
         * ps2.md 950 holds up as getting this right. */
        nRES: "net.nRESET",
        nIRQ: "net.nIRQ",
        nCS1: "net.SER_CS",
        XTLI: "net.BAUD_XTAL",
      }}
    />

    {/* U13 - RS-232 levels for TxD/RxD//RTS//CTS, +5 V only. A second one buys
      * full modem control and takes the card to 4 (serial.md 8). */}
    <chip
      name="U13"
      manufacturerPartNumber="MAX232"
      footprint="dip16_w0.3in"
      pinLabels={{
        pin1: "C1P", pin2: "V+", pin3: "C1N", pin4: "C2P", pin5: "C2N",
        pin6: "V-", pin7: "T2OUT", pin8: "R2IN", pin9: "R2OUT", pin10: "T2IN",
        pin11: "T1IN", pin12: "R1OUT", pin13: "R1IN", pin14: "T1OUT",
        pin15: "GND", pin16: "VCC",
      }}
      connections={{ VCC: "net.V5", GND: "net.GND" }}
    />

    {/* U14 - the four-byte window decode from geographic /IOSEL, with the
      * base-address jumper. */}
    <chip
      name="U14"
      footprint="dip24_w0.3in"
      pinLabels={{
        pin1: "CLK", pin2: "nIOSEL", pin3: "A2", pin4: "A3", pin5: "A4",
        pin6: "A5", pin7: "E", pin12: "GND", pin23: "SER_CS", pin24: "VCC",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        nIOSEL: "net.nIOSEL", E: "net.E",
        A2: "net.A2", A3: "net.A3", A4: "net.A4", A5: "net.A5",
        SER_CS: "net.SER_CS",
      }}
      noConnect={["CLK"]}
    />

    {/* 1.8432 MHz, and it is the ACIA's own. Not the backplane master. */}
    <crystal
      name="Y1"
      frequency="1.8432MHz"
      loadCapacitance="18pF"
      footprint="hc49"
      connections={{ pin1: "net.BAUD_XTAL", pin2: "net.GND" }}
    />
  </Card>
)
