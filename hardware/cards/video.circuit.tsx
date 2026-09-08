/* Video card - 640x200 x 256 colours, VGA out. 40 ICs, 9 of them GALs,
 * video/docs/graphics.md 14.
 *
 * Bus interface only. graphics.md 18 steps 1-2 require benching the dot path
 * and fitting the sequencer GALs *before* layout, and neither has happened, so
 * the 31 packages behind the interface are not drawn here.
 *
 * ⚠ graphics.md 14 budgeted the master oscillator on this card. machine.md 1
 * overrules it: the can is on the motherboard, because a card that carries E
 * kills the CPU when it is pulled - fatal for the bring-up sequences that run
 * before video exists. This card receives 25.175 MHz from the backplane.
 */
import { Card } from "../lib/Card"

export default () => (
  <Card name="arm6309-video" ioBase={0xff60} ioSize={32} length={240} icBudget={30}>
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

    {/* ⚠ Open, and it blocks this card: graphics.md 18 / design-review.md
      * Vid-M4 - the video output stage is unspecified. The R-2R ladders cannot
      * drive 75 ohm from '574 outputs, and blanking has no mechanism. No output
      * stage is drawn here because there is nothing yet to draw. */}
    <netlabel net="VGA_R" anchorSide="left" schX={6} schY={3} />
    <netlabel net="VGA_G" anchorSide="left" schX={6} schY={2} />
    <netlabel net="VGA_B" anchorSide="left" schX={6} schY={1} />
  </Card>
)
