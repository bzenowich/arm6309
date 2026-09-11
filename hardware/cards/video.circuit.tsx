/* Video card - 640x200 x 256 colours, VGA out. 33 ICs - 3 ATF1508AS PLCC-84
 * (vaddr, vctrl, vsup), no GALs, 4 SRAMs and 26 packages of 74-series -
 * video/docs/graphics.md 14.
 *
 * Bus interface AND the analogue back end. graphics.md 18 steps 1-2 require
 * benching the dot path before layout; the CPLDs are fitted (gal/cpld/) and
 * the dot path is not benched, so the digital packages behind the interface -
 * the three CPLDs, the SRAMs, the fetch ranks and the dot path - are still not
 * drawn here. Their pin senses are held by gal/pins.check.ts until they are.
 *
 * What IS drawn is graphics.md 9.1's drive stage. It is not an IC on the
 * count - three transistors, a diode and ten resistors.
 *
 * ⚠ graphics.md 14 budgeted the master oscillator on this card. machine.md 1
 * overrules it: the can is on the motherboard, because a card that carries E
 * kills the CPU when it is pulled - fatal for the bring-up sequences that run
 * before video exists. This card receives 25.175 MHz from the backplane.
 *
 * ⛔ REMOVED 2026-09-11: a GAL22V10 "U2" doing the host decode. No such part
 * has existed since vsup absorbed rfa (graphics.md 10.1.7) - the register
 * window is vsup's REGSEL and the VRAM select vctrl's VRAMSEL - and the drawn
 * one lacked A5, A6 and A20 besides. When the CPLDs are drawn, their pins come
 * from gal/vsup.pld and gal/vctrl.pld.
 */
import { Card } from "../lib/Card"

export default () => (
  <Card name="arm6309-video" ioBase={0xff60} ioSize={32} length={240} icBudget={33}>
    {/* U1 - the host data path, graphics.md 14's "74HC245 register read-back".
      *
      * ⛔ D0-D7 ARE ON THE B SIDE since 2026-09-11. A '245 passes A->B with DIR
      * high, and DIR is R/W, so a CPU READ must be card-to-host: A is the card's
      * internal data bus and B the backplane. It was drawn the other way round,
      * with the B side unconnected - a read drove the host bus INTO the card.
      *
      * ⚠ nOE HAS NO PRODUCER YET. The phantom U2 drove it; graphics.md 11 and
      * 12.1 need it to stand off at +$13 (VSTAT's '244) and +$15 (VDATA), and no
      * CPLD pin list carries that enable - a designer decision, recorded in the
      * three-board review of 2026-09-11 (V-07). The net is named for it. */}
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
        A1: "net.VD0", A2: "net.VD1", A3: "net.VD2", A4: "net.VD3",
        A5: "net.VD4", A6: "net.VD5", A7: "net.VD6", A8: "net.VD7",
        B1: "net.D0", B2: "net.D1", B3: "net.D2", B4: "net.D3",
        B5: "net.D4", B6: "net.D5", B7: "net.D6", B8: "net.D7",
        DIR: "net.R_W", nOE: "net.RBOE",
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
    {/* ⛔ R1 FEEDS THE DIODE AND THE DIODE IS TO GROUND, since 2026-09-11. It was
      * drawn V5 -> R1 -> D1 -> LADDER_RTN -> R2 -> GND: a divider with a diode
      * in series, which puts the return at (5 - 0.65) / 2 = 2.2 V rather than
      * one V_be. R2 is deleted; ~0.9 mA through 4.7k biases D1. */}
    <diode
      name="D1"
      footprint="0805"
      connections={{ anode: "net.LADDER_RTN", cathode: "net.GND" }}
    />
    <resistor name="R1" resistance="4.7k" footprint="0805"
      connections={{ pin1: "net.V5", pin2: "net.LADDER_RTN" }} />

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
          pinLabels={{ pin1: "C", pin2: "B", pin3: "E" }}
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
      * is its own pin on a DE-15.
      *
      * ⚠ FOOTPRINT: "pinrow15" is a 15-pin header, not a DE-15 receptacle. The
      * pin NUMBERING is the DE-15's and the netlist is right; the outline is
      * not. Same caveat as the slot socket - README.md open item 2 - and it
      * wants a measured footprint once a receptacle is sourced.
      *
      * Q1-Q3 also carry a placeholder: "to92" gives three leads at the right
      * pitch. ⛔ The BC547 is C-B-E left-to-right seen from the FLAT face,
      * which is what pin1/2/3 mean here; it was drawn E-B-C, which is the
      * 2N3904's order - and a 2N3904 (hFE 100-300) does not meet 9.1's
      * beta >= 300. Corrected 2026-09-11. Confirm against the part bought.
      *
      * ⛔ THE RGB RETURNS ARE THE CARD'S GROUND, since 2026-09-11. They were on
      * net.AGND, which the card edge carries to slot B33/B35 - the audio pair's
      * dedicated returns, kept away from 25.175 MHz on purpose (lib/slot.ts).
      * The three returns are commoned at the connector to the card's ground;
      * where that ground meets the plane is a layout decision. */}
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
        RGND: "net.GND", GGND: "net.GND", BGND: "net.GND",
        SGND: "net.GND", HS: "net.HSYNC_INT", VS: "net.VSYNC_INT",
      }}
    />
  </Card>
)
