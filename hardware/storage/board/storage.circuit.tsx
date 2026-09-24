/* SD card storage - 8 ICs, hardware/storage/docs/sdcard.md 8. 537 KiB/s sustained.
 *
 * The machine's one period exception, and it is honest about it: an SPI burst
 * started by the bus read strobe (sdcard.md 3.1, NormalLuser's BE6502
 * interface).
 *
 * REVISED 2026-09-20, and the revision is a RETREAT to that interface. From
 * 2026-09-08 this card carried a 2 KB SRAM the SPI engine filled and the host
 * read as memory, which retired sdcard.md 4's TFM hazard rather than
 * mitigating it and took sustained reads from 537 to 681 KiB/s. It cost seven
 * ICs, six of them address and data plumbing - and storage/logic/census.ts,
 * counting PINS rather than macrocells, then found its logic was four
 * GAL22V10s and not the two 8 budgeted. A 16-IC card for 21 %.
 *
 * So the buffer is gone and 4.4's chunk-and-mask discipline carries the read
 * path, which is what 9.2's WRITE path already did - the inconsistency 13
 * item 6 booked closes itself. The card is two GALs and six discrete
 * packages, the logic is fuse-verifiable (hardware/storage/logic/), and the
 * 21 % comes back for nothing if 11.6's option is taken: the hazard is a
 * property of this machine's own CPU firmware, not of handed-down silicon.
 */
import { Card } from "../../tools/lib/Card"

export default () => (
  <Card name="arm6309-storage" ioBase={0xff58} ioSize={4} length={120} icBudget={8}>
    {/* U1 - sdbus: the $FF58 decode, the four register strobes and SDSTAT's
      * three bits. hardware/storage/logic/sdbus.jedec.ts is the term list and
      * storage.check.ts sweeps all 8,192 inputs against Atmel's CUPL.
      *
      * The decode is A0-A6, seven bits: /IOSEL widened to $FF00-$FF7F on
      * 2026-09-08 and A6 left the strobe, so six bits would answer at $FF58
      * AND $FF18 (sdcard.md 6.1) - which the check asserts as its own claim.
      *
      * ⚠ It is purely combinational, so pin 1 is an ordinary input. */}
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

    {/* U2 - sdeng: SDCTRL, and the engine that turns one bus access into
      * exactly eight SPI clocks. sdeng.jedec.ts.
      *
      * ⭐ Everything on it is clocked by CLK25 and the SPI clock is an
      * ENABLE, which is the one departure from sdcard.md 3.3's circuit: a
      * GAL22V10 has one clock pin, and a part holding both SDCTRL (written at
      * E rate) and the burst counter (running at SPI rate) cannot clock both.
      * It also deletes 3.3's runt-pulse hazard, because BUSY then only ever
      * moves on the SPI clock's falling edge.
      *
      * ⚠ Two of its pins are wired, not computed: the '163's /CLR and the
      * '165's SH//LD are both BUSY. The first is 6.5's re-trigger lockout
      * made structural - a counter whose clear is deasserted cannot be
      * reloaded mid-burst. */}
    <chip
      name="U2"
      manufacturerPartNumber="GAL22V10D"
      footprint="dip24_w0.3in"
      connections={{ pin24: "net.V5", pin12: "net.GND" }}
    />

    {/* U3 - the receive shift register, and it is 74HCT595 and not 74HC595 for
      * one specific reason: the SD card's V_OH of ~2.48 V clears an HCT input's
      * 2.0 V V_IH, so MISO needs no level shifter at all. An HC part would read
      * a valid 3.3 V high as indeterminate (sdcard.md 7). */}
    <chip
      name="U3"
      manufacturerPartNumber="74HCT595"
      footprint="dip16_w0.3in"
      pinLabels={{
        pin1: "QB", pin2: "QC", pin3: "QD", pin4: "QE", pin5: "QF", pin6: "QG",
        pin7: "QH", pin8: "GND", pin9: "QHS", pin10: "nSRCLR", pin11: "SRCLK",
        pin12: "RCLK", pin13: "nOE", pin14: "SER", pin15: "QA", pin16: "VCC",
      }}
      connections={{
        /* nOE is sdbus's OE595 and nothing else: an SDDATA READ. ⚠ Not the
         * same term as the burst trigger - a WRITE to SDDATA also starts a
         * burst, and the '595 must not drive a bus the CPU is driving. The
         * storage_tb counts D's drivers every tick to hold the board to it. */
        VCC: "net.V5", GND: "net.GND", nSRCLR: "net.V5",
        SER: "net.MISO", SRCLK: "net.SCK_5V",
      }}
    />

    {/* U8 - 5 V to 3.3 V for SCK, MOSI and /CS. Three gates of four; LVC inputs
      * are 5 V tolerant, which is what makes one part do it. */}
    <chip
      name="U8"
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
      name="VR1"
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
