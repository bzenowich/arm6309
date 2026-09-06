/* Audio card - 4-channel 8-bit PCM, Paula-exact. 36 ICs, audio/docs/audio.md 10.
 *
 * Bus interface only. The card's own document is the specification and its
 * 15 step 0 is "freeze the register map", which is ahead of any board.
 *
 * The one thing this card does not take from the backplane is its clock: its
 * period reference is a second crystal, 28.37516 MHz, the Amiga PAL master, and
 * audio.md 4.1 calls that non-negotiable because every module in the corpus was
 * tuned by ear against exactly that number.
 */
import { Card } from "../lib/Card"

export default () => (
  <Card name="arm6309-audio" ioBase={0xff40} ioSize={16} icBudget={36}>
    {/* Y1 - not the backplane's 25.175 MHz. machine.md 1's one-master rule has
      * exactly one exception and this is it. */}
    <crystal
      name="Y1"
      frequency="28.37516MHz"
      loadCapacitance="18pF"
      footprint="hc49"
      connections={{ pin1: "net.PAL_XTAL", pin2: "net.GND" }}
    />

    {/* U1 - the card's decode and most of its sequencing. audio.md 9.5 moved
      * the host-visible counters and commit staging into the state file the
      * card already owns; what is left here is decode and control. */}
    <chip
      name="U1"
      footprint="dip24_w0.3in"
      pinLabels={{
        pin1: "CLK", pin2: "nIOSEL", pin3: "E", pin4: "R_W",
        pin5: "A0", pin6: "A1", pin7: "A2", pin8: "A3",
        pin12: "GND", pin23: "nFIRQ", pin24: "VCC",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND", CLK: "net.PAL_XTAL",
        nIOSEL: "net.nIOSEL", E: "net.E", R_W: "net.R_W",
        A0: "net.A0", A1: "net.A1", A2: "net.A2", A3: "net.A3",
        /* audio.md 8.1 takes /FIRQ as the sole source, so the replayer's
         * interrupt path has no polling chain. Open-drain onto the backplane;
         * the pull-up is on the motherboard (machine.md 2.1). */
        nFIRQ: "net.nFIRQ",
      }}
    />

    {/* U2 - the prefetch latch, and the whole read-back path. audio.md 9.3:
      * a '574 is a flip-flop with three-state outputs, so it drives the host
      * bus itself and the '245 that used to buffer it is deleted. */}
    <chip
      name="U2"
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
        Q1: "net.D0", Q2: "net.D1", Q3: "net.D2", Q4: "net.D3",
        Q5: "net.D4", Q6: "net.D5", Q7: "net.D6", Q8: "net.D7",
      }}
    />

    {/* The analogue pair leaves by the backplane, hard-panned. audio.md 1
      * requirement 5: Paula's channels are 0 and 3 left, 1 and 2 right, and
      * summing them to mono does not make a module quieter, it makes it wrong.
      *
      * audio.md 10 wants the analogue section physically separate; that is a
      * placement decision and this file has taken none yet. */}
    <netlabel net="AUDIO_L" anchorSide="left" schX={4} schY={2} />
    <netlabel net="AUDIO_R" anchorSide="left" schX={4} schY={1} />
  </Card>
)
