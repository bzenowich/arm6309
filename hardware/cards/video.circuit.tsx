/* Video card - 640x200 x 256 colours, VGA out. 27 ICs - 2 ATF1508AS PLCC-84,
 * 1 GAL22V10 and 4 SRAMs - video/docs/graphics.md 14.1, 14.2.
 *
 * Bus interface AND the analogue back end. graphics.md 18 steps 1-2 require
 * benching the dot path and fitting the sequencer GALs *before* layout; the
 * CPLDs are fitted (gal/cpld/) and the dot path is not benched, so the digital
 * packages behind the interface are still not drawn here.
 *
 * What IS drawn, as of 2026-09-08, is graphics.md 9.1's drive stage. It is not
 * an IC on the count - three transistors, a diode and fifteen resistors - and
 * it was the last thing design-review.md Vid-M4 left open on this card.
 *
 * ⚠ graphics.md 14 budgeted the master oscillator on this card. machine.md 1
 * overrules it: the can is on the motherboard, because a card that carries E
 * kills the CPU when it is pulled - fatal for the bring-up sequences that run
 * before video exists. This card receives 25.175 MHz from the backplane.
 */
import { Card } from "../lib/Card"

export default () => (
  <Card name="arm6309-video" ioBase={0xff60} ioSize={32} length={180} icBudget={27}>
    {/* U1 - the host data path. */}
    <chip
      name="U1"
      footprint="dip20_w0.3in"
      pinLabels={{
        pin1: "DIR", pin19: "nOE", pin10: "GND", pin20: "VCC",
        pin2: "A1", pin3: "A2", pin4: "A3", pin5: "A4",
        pin6: "A5", pin7: "A6", pin8: "A7", pin9: "A8",
        pin18: "B1", pin17: "B2", pin16: "B3", pin15: "B4",
        pin14: "B5", pin13: "B6", pin12: "B7", pin11: "B8",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        A1: "net.D0", A2: "net.D1", A3: "net.D2", A4: "net.D3",
        A5: "net.D4", A6: "net.D5", A7: "net.D6", A8: "net.D7",
        DIR: "net.R_W", nOE: "net.VID_BUFEN",
      }}
    />

    {/* U2 - the host-side decode, and the VRAM select.
      *
      * ⚠ The VRAM select is qualified against /IOPAGE, and it is not optional.
      * graphics.md 6.3.2 and machine.md 2: without it, a task with any MMU
      * block pointed at VRAM double-drives D0-D7 on every I/O read and posts a
      * spurious VRAM write on every I/O write. The card cannot compute this
      * inhibit for itself, because logical A13-A15 never leave the
      * motherboard - which is the whole reason /IOPAGE is a backplane wire. */}
    <chip
      name="U2"
      footprint="dip24_w0.3in"
      pinLabels={{
        pin1: "CLK", pin2: "nIOSEL", pin3: "nIOPAGE", pin4: "A19",
        pin5: "A0", pin6: "A1", pin7: "A2", pin8: "A3", pin9: "A4",
        pin10: "E", pin11: "R_W", pin12: "GND",
        pin21: "VRAM_CE", pin22: "VID_BUFEN", pin23: "nIRQ", pin24: "VCC",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND", CLK: "net.CLK25",
        nIOSEL: "net.nIOSEL", nIOPAGE: "net.nIOPAGE", A19: "net.A19",
        A0: "net.A0", A1: "net.A1", A2: "net.A2", A3: "net.A3", A4: "net.A4",
        E: "net.E", R_W: "net.R_W",
        VRAM_CE: "net.VRAM_CE", VID_BUFEN: "net.VID_BUFEN",
        /* VBL and raster compare. VBL is NitrOS-9's system tick and the most
         * frequent source, which is why this card is polled first
         * (machine.md 4.1). */
        nIRQ: "net.nIRQ",
      }}
    />

    {/* U3 - the '244 that already carries other signals, two of whose channels
      * now drive HSYNC and VSYNC back to the CPU slot. graphics.md 12.2: the
      * raster-compare timer lives in the STM32 and clocks from HSYNC, and
      * without VSYNC as a hardware frame reset the line counter has no origin.
      * Resynchronising in the VBL handler jitters the frame origin by the whole
      * /IRQ dispatch latency - 1 to 6 lines, varying per frame. */}
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
        VCC: "net.V5", GND: "net.GND", n1OE: "net.GND", n2OE: "net.GND",
        "1A1": "net.HSYNC_INT", "1Y1": "net.HSYNC",
        "1A2": "net.VSYNC_INT", "1Y2": "net.VSYNC",
      }}
    />

    {/* ------------------------------------ the analogue back end, 9.1 ---- */}
    {/* graphics.md 9.1, drawn 2026-09-08. design-review.md Vid-M4 said the
      * ladders were unbuildable as listed, and the arithmetic is why:
      *
      *   VGA is double-terminated 75 ohm, 0.700 V peak white AT THE LOAD, so
      *   the card must swing 1.400 V open-circuit into 150 ohm = 9.33 mA per
      *   channel. To BE the 75 ohm source a bare ladder needs R = 75 / 2R =
      *   150, whose MSB leg pulls 5 V / 150 = 33.3 mA from a '574 rated 8 mA.
      *   4.2x over rating, and the sag is CODE-DEPENDENT, so the 6-bit green
      *   channel's DNL is destroyed before step 1 can measure it.
      *
      * The fix is a high-impedance ladder plus an emitter follower per channel:
      * per-pin current is then bounded by the leg alone (5 V / 2.00k = 2.5 mA)
      * and DNL becomes a resistor-tolerance question - 1 % on the MSB leg is
      * +/-0.32 LSB of green, so the converter is monotonic by construction.
      *
      * Ladder settling is the binding number, not the transistor: ~287 ohm
      * after the base divider into ~15 pF is tau = 4.3 ns, 3 tau = 13 ns
      * inside the 39.7 ns dot. A BC547C at 10 mA has f_T ~300 MHz.
      *
      * ⚠ NOT DRAWN: the R-2R ladders themselves. They are 5/6/5 bits off the
      * post-LUT '273 pair, which is one of the digital packages this file does
      * not carry yet. RLAD_R/G/B are the ladder outputs, and the divider and
      * follower below are what graphics.md 9.1 adds behind each one. */}

    {/* The shared V_be reference. An NPN follower into a resistive-to-ground
      * load cuts off as its emitter approaches 0 V, so the bottom code or two
      * are nonlinear. Return the ladders' 2R legs to +V_be - ONE forward-biased
      * diode of the same family, thermally coupled to the three transistors -
      * and code 0 puts each base at V_be and each emitter at 0.000 V with the
      * device just conducting.
      *
      * Residual mismatch between the shared diode and the three V_be is
      * +/-20-30 mV at the base, ~+/-2 LSB of green, and 9.2 removes even that:
      * blanking level and black level travel the IDENTICAL path, so the
      * monitor's back-porch clamp subtracts the residual exactly. That is the
      * argument for doing blanking after the LUT and nowhere else. */}
    <diode
      name="D1"
      footprint="0805"
      connections={{ pin1: "net.V5_VBE", pin2: "net.LADDER_RTN" }}
    />
    <resistor name="R1" resistance="4.7k" footprint="0805"
      connections={{ pin1: "net.V5", pin2: "net.V5_VBE" }} />
    <resistor name="R2" resistance="4.7k" footprint="0805"
      connections={{ pin1: "net.LADDER_RTN", pin2: "net.GND" }} />

    {/* One channel each: base divider, follower, emitter load, 75 ohm source.
      *
      *   R_shunt   402 ohm 1 %  - 4.85 V * R/(1000+R) = 1.40 V open-circuit
      *   Q         BC547C class, beta >= 300 - I_b = 9.33 mA / 300 = 31 uA
      *             into 287 ohm = 8.9 mV = 0.8 LSB of green
      *   R_e       1.0k to LADDER_RTN, so the follower has a load at code 0
      *   R_s       75 ohm 1 % - with the monitor's 75 gives the 2:1 divider
      *
      * Dissipation at peak white is (5 - 1.4) * 9.33 mA = 33.6 mW. TO-92. */}
    {[
      { ch: "R", n: 0 },
      { ch: "G", n: 1 },
      { ch: "B", n: 2 },
    ].map(({ ch, n }) => (
      <group key={ch}>
        <resistor name={`R${3 + n * 3}`} resistance="402" footprint="0805"
          connections={{ pin1: `net.RLAD_${ch}`, pin2: "net.LADDER_RTN" }} />
        <chip
          name={`Q${n + 1}`}
          footprint="to92"
          pinLabels={{ pin1: "E", pin2: "B", pin3: "C" }}
          connections={{ B: `net.RLAD_${ch}`, C: "net.V5", E: `net.EMIT_${ch}` }}
        />
        <resistor name={`R${4 + n * 3}`} resistance="1k" footprint="0805"
          connections={{ pin1: `net.EMIT_${ch}`, pin2: "net.LADDER_RTN" }} />
        <resistor name={`R${5 + n * 3}`} resistance="75" footprint="0805"
          connections={{ pin1: `net.EMIT_${ch}`, pin2: `net.VGA_${ch}` }} />
      </group>
    ))}

    {/* J2 - the connector. HSYNC and VSYNC are separate TTL pins, so RGB has no
      * sync tip and the whole 0-0.7 V range is picture (9.1). Each RGB return
      * is its own pin on a DE-15 and they are NOT commoned at the card.
      *
      * ⚠ FOOTPRINT: "pinrow15" is a 15-pin header, not a DE-15 receptacle. The
      * pin NUMBERING is the DE-15's and the netlist is right; the outline is
      * not. Same caveat as the slot socket - README.md open item 2 - and it
      * wants a measured footprint once a receptacle is sourced.
      *
      * Q1-Q3 also carry a placeholder: "to92" gives three leads at the right
      * pitch, and BC547 pinout is E-B-C left-to-right seen from the FLAT face,
      * which is what pin1/2/3 mean here. Confirm against the part actually
      * bought - the 2N3904's is E-B-C too but many TO-92 NPNs are not. */}
    <chip
      name="J2"
      footprint="pinrow15"
      pinLabels={{
        pin1: "RED", pin2: "GREEN", pin3: "BLUE",
        pin6: "RGND", pin7: "GGND", pin8: "BGND",
        pin10: "SGND", pin13: "HS", pin14: "VS",
      }}
      connections={{
        RED: "net.VGA_R", GREEN: "net.VGA_G", BLUE: "net.VGA_B",
        RGND: "net.AGND", GGND: "net.AGND", BGND: "net.AGND",
        SGND: "net.GND", HS: "net.HSYNC_INT", VS: "net.VSYNC_INT",
      }}
    />
  </Card>
)
