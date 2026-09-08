/* Net card - 10BASE-T, no MAC or PHY chip. 12 ICs, net/docs/net.md 9.
 *
 * Bus interface only. The card's own document is the specification, and its
 * 15 step 0 is a machine-level decision rather than a card one: this card
 * takes the last four bytes of the $FF map (net.md 5.1, machine.md 5 item 1).
 *
 * Ported from ~/code/applenet's arch-v3 - one card, two ATF1508AS PLCC-84,
 * U1 the TX domain and U2 the RX domain. That partition and the whole discrete
 * recovery block carry over unchanged. What this machine takes away is the
 * $Cn00 driver ROM, because the CPU module serves an 8 KB shadow ROM from its
 * own flash (machine.md 7.2).
 *
 * REVISED 2026-09-08. The buffers were behind a prefetched auto-incrementing
 * port in four bytes of $FF space, because that was the only address space the
 * machine had - and filling the $FF map is what forced machine.md 5 item 1.
 * Its answer (option D, physical A20, and item 7's 64 KB card regions) paid for
 * a rebuild: 16 ICs -> 12, 44 % of the wire -> 56 %, a four-frame ring -> 16,
 * and the TFM hazard retired rather than mitigated. What it did NOT buy is
 * macrocells - net.md 7.3 is blunt about that.
 */
import { Card } from "../lib/Card"

export default () => (
  <Card name="arm6309-net" ioBase={0xff5c} ioSize={4} icBudget={12}>
    {/* Y1 - the bit rate must be 10.000 MHz +/-100 ppm and 25.175 / 10 is not
      * an integer, so the backplane cannot supply it. net.md 11: this is the
      * machine's third oscillator, and unlike audio's it is forced by an
      * external standard rather than chosen. */}
    <crystal
      name="Y1"
      frequency="20MHz"
      loadCapacitance="18pF"
      footprint="hc49"
      connections={{ pin1: "net.BITOSC", pin2: "net.GND" }}
    />

    {/* U1 - TX domain. 96 of 128 macrocells, 37 of 60 user I/O (net.md 7.2).
      * Serializer, TX CRC-32 LFSR, FCS append, Manchester XOR, NLP gating, the
      * TX buffer and the host's TX-side port.
      *
      * Only the pins the fitter cannot move are named: GCLR takes /RESET, so
      * the card's asynchronous reset costs no product term; GCLK2 takes E, the
      * host domain; GCLK1 takes the 20 MHz bit clock. Everything else is left
      * for the fitter - net.md 7.4 keeps the datapath pinout open and hand
      * placing I/O before a fit is how you get an unroutable design.
      *
      * /IRQ is the ATF1508AS's programmable open-collector output option, the
      * same feature audio.md 8.1 spends. The pull-up is on the motherboard
      * (machine.md 2.1) and there is no open-drain gate on this card. */}
    <chip
      name="U1"
      footprint="plcc84"
      pinLabels={{
        pin1: "nRESET", pin2: "E", pin83: "BITOSC",
        pin84: "VCC", pin42: "GND",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        nRESET: "net.nRESET", E: "net.E", BITOSC: "net.BITOSC",
      }}
    />

    {/* U2 - RX domain. 116 of 128 macrocells, still the card's largest
      * technical risk: net.md 7.3 gives a five-step cut order and says to fit
      * this device before laying out the board. U1 is now the pin-limited one
      * at 60 of 60 (net.md 7.4) - it took the region decode, both SRAMs'
      * control lines and the 4.3 bus schedule in the 2026-09-08 revision.
      *
      * GCLK1 takes CLK25. That is the thing this machine gives the port and
      * applenet does not have - arch-v3 notes its RX device's only clock is a
      * bus strobe that stops when the slot is idle, and machine.md 2 puts a
      * free-running 25.175 MHz master on every slot. It clocks the arbiter of
      * net.md 7.6, and nothing in the rec_clk domain may depend on it.
      *
      * GCLK3 is pin 81, an I/O pin rather than a dedicated input, so the
      * fitter has to be told that rec_clk belongs there. */}
    <chip
      name="U2"
      footprint="plcc84"
      pinLabels={{
        pin1: "nRESET", pin2: "E", pin83: "CLK25", pin81: "REC_CLK",
        pin84: "VCC", pin42: "GND",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        nRESET: "net.nRESET", E: "net.E", CLK25: "net.CLK25",
        REC_CLK: "net.REC_CLK",
      }}
    />

    {/* U5 - the shared card data bus. Backplane D0-D7 on the A side, the
      * card's local data bus on the B side; both SRAMs and both CPLDs hang on
      * that bus and net.md 4.3 says who drives it when. 74HCT because it faces
      * the slot (machine.md 2.1); both CPLDs take TTL levels natively, so the
      * level rule lands on the buffers and not on them.
      *
      * It is also the single D0-D7 load machine.md 2.1's bus loading table
      * counts for this card. Two 74HC244s carry backplane A14-A0 onto the
      * shared address bus alongside it - net.md 9 explains why those are HC
      * and this is HCT. */}
    <chip
      name="U5"
      manufacturerPartNumber="74HCT245"
      footprint="dip20_w0.3in"
      pinLabels={{
        pin1: "DIR", pin19: "nOE", pin10: "GND", pin20: "VCC",
        pin2: "A1", pin3: "A2", pin4: "A3", pin5: "A4",
        pin6: "A5", pin7: "A6", pin8: "A7", pin9: "A8",
        pin18: "B1", pin17: "B2", pin16: "B3", pin15: "B4",
        pin14: "B5", pin13: "B6", pin12: "B7", pin11: "B8",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND", DIR: "net.R_W",
        A1: "net.D0", A2: "net.D1", A3: "net.D2", A4: "net.D3",
        A5: "net.D4", A6: "net.D5", A7: "net.D6", A8: "net.D7",
      }}
    />

    {/* U6 - the RX ring. 62256, 32K x 8, sixteen banks of 2 KB, at A15 = 0 of
      * the card's 64 KB region (net.md 4.2). The host addresses it through the
      * MMU like any other memory; U2's framer pointer three-states onto the
      * same address bus in its two-tick slot.
      *
      * THIS PART IS WHY THE CARD LOST FOUR ICs AND A HAZARD. It replaced a
      * 6264 plus three 74HC161s, a '244, a '125 and a '574 - all of which
      * existed to get a host-side address to an SRAM that the backplane now
      * delivers (net.md 7.6). Same package, same price, four times the ring.
      *
      * A 2 KB bank is two header bytes then the frame (net.md 5.5), which is
      * what deletes the per-bank length latches review.md 6.5 asked for:
      * sixteen of those would be 208 macrocells, more than either device has
      * in total. */}
    <chip
      name="U6"
      manufacturerPartNumber="62256"
      footprint="dip28_w0.6in"
      pinLabels={{
        pin1: "A14", pin2: "A12", pin3: "A7", pin4: "A6", pin5: "A5",
        pin6: "A4", pin7: "A3", pin8: "A2", pin9: "A1", pin10: "A0",
        pin11: "DQ0", pin12: "DQ1", pin13: "DQ2", pin14: "GND",
        pin15: "DQ3", pin16: "DQ4", pin17: "DQ5", pin18: "DQ6", pin19: "DQ7",
        pin20: "nCE", pin21: "A10", pin22: "nOE", pin23: "A11", pin24: "A9",
        pin25: "A8", pin26: "A13", pin27: "nWE", pin28: "VCC",
      }}
      connections={{ VCC: "net.V5", GND: "net.GND" }}
    />

    {/* U16 - the only analogue crossing. tx_manch out, rx_logic in, plus the
      * driver enable; everything else on the wire side is the MagJack, the TX
      * filter network and the 100 ohm RX termination.
      *
      * The recovery chain behind it ('86 edge detect, '221 for the ~75 ns
      * non-retriggerable rec_clk, '123 for NIDLE and LINK_UP) is net.md 8.1
      * and it stays discrete: a CPLD has no analogue delay element, and it is
      * the one block on this card a JTAG reprogram cannot fix. */}
    <chip
      name="U16"
      manufacturerPartNumber="SN75C1168"
      footprint="dip16_w0.3in"
      pinLabels={{ pin8: "GND", pin16: "VCC" }}
      connections={{ VCC: "net.V5", GND: "net.GND" }}
    />

    {/* The card asserts /IRQ as a fifth source (net.md 6, machine.md 4). Both
      * CPLDs drive it open-collector and independently; NRXST bit 7 is what
      * lets the shared handler answer "was it us?" in one read.
      *
      * The proposed polling order is video, net, PS/2, serial - and net is
      * what makes machine.md 4.1's order correctness-driven rather than
      * frequency-driven, because under load this card raises more interrupts
      * than VBL does. */}
    <netlabel net="nIRQ" anchorSide="left" schX={4} schY={2} />
  </Card>
)
