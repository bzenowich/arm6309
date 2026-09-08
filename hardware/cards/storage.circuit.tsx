/* SD card storage - 13 ICs, storage/docs/sdcard.md 8. 681 KiB/s sustained.
 *
 * The machine's one period exception, and it is honest about it: an SPI burst
 * started by the bus read strobe (sdcard.md 3.1).
 *
 * REVISED 2026-09-08. sdcard.md 11.1 wanted a memory-mapped block buffer from
 * the beginning and called it "the clean answer we cannot afford" - the $FF
 * window was 64 bytes and the 1 MB physical map was fully spent. machine.md 5
 * item 1 option D and item 7 made it affordable, so the SPI engine now fills a
 * 2 KB SRAM the host reads as memory. That RETIRED the TFM hazard rather than
 * mitigating it (a re-read of RAM is idempotent - sdcard.md 4.2's own
 * argument), and took sustained reads from 528 to 681 KiB/s.
 *
 * It cost six ICs, five of them address and data plumbing. One ATF1508AS would
 * absorb both GALs, the counter and the mux for an 8-IC card.
 *
 * That was refused on the no-CPLD house rule, which was retired on 2026-09-08
 * (root README.md), so it is no longer blocked - and it has not been taken.
 * Unlike video, audio and net, this card's logic fits two GALs comfortably, so a
 * CPLD here buys packages rather than capability and gives up the fuse-level
 * verification hardware/gal/jedec/ provides. sdcard.md 8.1, 13 item 12.
 */
import { Card } from "../lib/Card"

export default () => (
  <Card name="arm6309-storage" ioBase={0xff58} ioSize={4} icBudget={13}>
    {/* U1 - decode and the burst sequencer, from geographic /IOSEL.
      *
      * The decode is A0-A6 now, seven bits: /IOSEL widened to $FF00-$FF7F on
      * 2026-09-08 and A6 left the strobe, so six bits would answer at $FF58
      * AND $FF18 (sdcard.md 6.1). This part also gained FILL/BUF (sdcard.md
      * 6.2) and the A20 = 1 region compare, which is why sdcard.md 8 budgets
      * the GAL as two packages. */}
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

    {/* U7 - the block buffer. 6116, 2K x 8, four 512-byte buffers, at offset 0
      * of the card's 64 KB region at A20 = 1 (machine.md 5 item 7). The host
      * reads it through the MMU as ordinary memory, which is the whole of
      * sdcard.md 4.5: there is nothing here for an interrupted TFM to break.
      *
      * Filled by a 74HC4040 9-bit counter and the FILL bit; three 74HC157s mux
      * that counter against backplane A8-A0. Those four packages plus this one
      * and the '245 are the six ICs the revision cost. */}
    <chip
      name="U7"
      manufacturerPartNumber="6116"
      footprint="dip24_w0.6in"
      pinLabels={{
        pin1: "A7", pin2: "A6", pin3: "A5", pin4: "A4", pin5: "A3",
        pin6: "A2", pin7: "A1", pin8: "A0", pin9: "DQ0", pin10: "DQ1",
        pin11: "DQ2", pin12: "GND", pin13: "DQ3", pin14: "DQ4", pin15: "DQ5",
        pin16: "DQ6", pin17: "DQ7", pin18: "nCE", pin19: "A10", pin20: "nOE",
        pin21: "nWE", pin22: "A9", pin23: "A8", pin24: "VCC",
      }}
      connections={{ VCC: "net.V5", GND: "net.GND" }}
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
        /* nOE is no longer tied low onto the slot bus: the '595 now three-states
         * onto the buffer's LOCAL data bus, and its enable is the fill engine's
         * write window rather than a bus-read decode. sdcard.md 3.5 flags this
         * as the most likely place to get the revision wrong, because the part
         * is unchanged and its wiring is not. */
        VCC: "net.V5", GND: "net.GND", nSRCLR: "net.V5",
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
