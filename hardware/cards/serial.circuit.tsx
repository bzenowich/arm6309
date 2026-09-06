/* RS-232 serial card - 3 ICs, io/serial/docs/serial.md 13.
 *
 * Three ICs because one period chip does the job, against PS/2's eleven because
 * none does. The ACIA's speed grade is part of the specification, not a
 * preference (serial.md 3.4), and the in-production W65C51N is defective for
 * this use: its TDRE bit is broken (3.3). Source an R6551A or a G65SC51.
 */
import { Card } from "../lib/Card"

export default () => (
  <Card name="arm6309-serial" ioBase={0xff54} ioSize={4} icBudget={3}>
    {/* U1 - the ACIA. Four registers, which is exactly why the card asks for
      * four bytes. /IRQ is the fourth source on the shared line, and it is
      * polled last: reading STATUS clears the interrupt and returns the error
      * bits in the same read (machine.md 4.1). */}
    <chip
      name="U1"
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

    {/* U2 - RS-232 levels for TxD/RxD//RTS//CTS, +5 V only. A second one buys
      * full modem control and takes the card to 4 (serial.md 8). */}
    <chip
      name="U2"
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

    {/* U3 - the four-byte window decode from geographic /IOSEL, with the
      * base-address jumper. */}
    <chip
      name="U3"
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
