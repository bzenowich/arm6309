/* SD card storage - 7 ICs, storage/docs/sdcard.md 8. 528 KiB/s sustained.
 *
 * The machine's one period exception, and it is honest about it: an SPI burst
 * started by the bus read strobe, so TFM's 1430 ns read interval covers a
 * 636 ns burst with 2.25x margin at the specified /12 E (sdcard.md 3.3).
 */
import { Card } from "../lib/Card"

export default () => (
  <Card name="arm6309-storage" ioBase={0xff58} ioSize={4} icBudget={7}>
    {/* U1 - decode and the burst sequencer, from geographic /IOSEL. */}
    <chip
      name="U1"
      footprint="dip24_w0.3in"
      pinLabels={{
        pin1: "CLK", pin2: "nIOSEL", pin3: "A0", pin4: "A1", pin5: "E",
        pin6: "R_W", pin7: "nRESET", pin12: "GND",
        pin20: "BURST", pin21: "SD_CS", pin22: "SCK", pin23: "BUSY", pin24: "VCC",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND", CLK: "net.CLK25",
        nIOSEL: "net.nIOSEL", A0: "net.A0", A1: "net.A1",
        E: "net.E", R_W: "net.R_W", nRESET: "net.nRESET",
        BURST: "net.BURST", SD_CS: "net.SD_CS_5V", SCK: "net.SCK_5V",
        BUSY: "net.BUSY",
      }}
      noConnect={[]}
    />

    {/* U2 - the receive shift register, and it is 74HCT595 and not 74HC595 for
      * one specific reason: the SD card's V_OH of ~2.48 V clears an HCT input's
      * 2.0 V V_IH, so MISO needs no level shifter at all. An HC part would read
      * a valid 3.3 V high as indeterminate (sdcard.md 7). */}
    <chip
      name="U2"
      manufacturerPartNumber="74HCT595"
      footprint="dip16_w0.3in"
      pinLabels={{
        pin1: "QB", pin2: "QC", pin3: "QD", pin4: "QE", pin5: "QF", pin6: "QG",
        pin7: "QH", pin8: "GND", pin9: "QHS", pin10: "nSRCLR", pin11: "SRCLK",
        pin12: "RCLK", pin13: "nOE", pin14: "SER", pin15: "QA", pin16: "VCC",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND", nSRCLR: "net.V5", nOE: "net.GND",
        SER: "net.MISO", SRCLK: "net.SCK_5V",
      }}
    />

    {/* U6 - 5 V to 3.3 V for SCK, MOSI and /CS. Three gates of four; LVC inputs
      * are 5 V tolerant, which is what makes one part do it. */}
    <chip
      name="U6"
      manufacturerPartNumber="74LVC125"
      footprint="dip14_w0.3in"
      pinLabels={{
        pin1: "n1OE", pin2: "1A", pin3: "1Y", pin4: "n2OE", pin5: "2A",
        pin6: "2Y", pin7: "GND", pin8: "3Y", pin9: "3A", pin10: "n3OE",
        pin11: "4Y", pin12: "4A", pin13: "n4OE", pin14: "VCC",
      }}
      connections={{
        /* Powered from the 3.3 V rail this card makes for itself - the
         * backplane carries 5 V only. */
        VCC: "net.V3_3", GND: "net.GND",
        n1OE: "net.GND", n2OE: "net.GND", n3OE: "net.GND", n4OE: "net.V3_3",
        "1A": "net.SCK_5V", "1Y": "net.SCK",
        "2A": "net.MOSI_5V", "2Y": "net.MOSI",
        "3A": "net.SD_CS_5V", "3Y": "net.SD_CS",
      }}
    />

    {/* The 3.3 V domain. sdcard.md 7: 500 mA with bulk capacitance, because an
      * SD card draws far more while programming than while reading, and in
      * bursts - an undersized LDO browns out the card mid-write. */}
    <chip
      name="U7"
      footprint="sot223"
      pinLabels={{ pin1: "GND", pin2: "VOUT", pin3: "VIN", pin4: "TAB" }}
      connections={{ VIN: "net.V5", VOUT: "net.V3_3", GND: "net.GND", TAB: "net.V3_3" }}
    />
    <capacitor name="C1" capacitance="10uF" footprint="0805"
      connections={{ pin1: "net.V3_3", pin2: "net.GND" }} />
    <capacitor name="C2" capacitance="100uF" footprint="1210"
      connections={{ pin1: "net.V3_3", pin2: "net.GND" }} />
  </Card>
)
