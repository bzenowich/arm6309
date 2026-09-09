/* Audio card - 4-channel 8-bit PCM, Paula-exact, with programmable per-channel
 * panning. 31 ICs, audio/docs/audio.md 10.
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
  <Card name="arm6309-audio" ioBase={0xff40} ioSize={16} length={180} icBudget={31}>
    {/* Y1 - not the backplane's 25.175 MHz. machine.md 1's one-master rule has
      * exactly one exception and this is it. */}
    <crystal
      name="Y1"
      frequency="28.37516MHz"
      loadCapacitance="18pF"
      footprint="hc49"
      connections={{ pin1: "net.PAL_XTAL", pin2: "net.GND" }}
    />

    {/* U1 - ALL of the card's logic, audio.md 10.1. This was five GAL22V10s
      * when the card was drawn and it is one ATF1508AS now, for a reason that
      * is not package-count: 9.5's interrupt block does not fit a GAL22V10
      * whole (13 equations, 10 macrocells) or split (17 inputs, 14 pins), so
      * the GAL allocation was six and rising. The part also absorbs the '273,
      * the three '174 synchronisers and the '07, the last because an
      * ATF1508AS output has a programmable open-collector option and 8.1 needs
      * the wire-OR a GAL's totem-pole pin cannot do.
      *
      * hardware/gal/cpld/audio.jed is the fitted device: 74,136 fuses, 79 of
      * 128 logic cells, 50 of 64 I/O. Pin numbers below are the ones the
      * fitter chose and they are NOT settled - audio.md 10.1 keeps the
      * datapath pinout open, and fit1508.sh is run with -preassign ignore, so
      * every refit may move them. Only the two the fitter cannot move are
      * relied on here: the global clock and the global clear.
      *
      * Socketed. It is programmed out of circuit, so JTAG is not routed. */}
    <chip
      name="U1"
      footprint="plcc84"
      pinLabels={{
        pin83: "SLOTCLK", pin1: "nRESET",
        pin84: "VCC", pin42: "GND",
      }}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        /* 4.1: the card's own 28.37516 MHz reference, divided on-part. Not
         * the backplane's 25.175 MHz - machine.md 1's one-master rule has
         * exactly one exception and this is it. */
        SLOTCLK: "net.PAL_XTAL",
        nRESET: "net.nRESET",
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

    {/* ------------------------------------------------- the output, 7.1 --- */}
    {/* Two channels, and they must stay two. audio.md 1 requirement 5: Paula's
      * channels are 0 and 3 left, 1 and 2 right, and summing them to mono does
      * not make a module quieter, it makes it WRONG. Since 11.1's panning the
      * assignment is a mode bit rather than a wire (ACTRL b5), and the default
      * is still Paula's hard pan exactly.
      *
      * The DC block is good manners rather than load-bearing: 6.3 cancels the
      * sample converters' pedestal UPSTREAM of the volume stage, so the card's
      * output is already centred and is exactly zero when every channel is
      * silent. What the capacitor removes is zero-code leakage and amplifier
      * offsets - tens of millivolts, not half of full scale. 10 uF into 100k is
      * 0.16 Hz, four decades below anything a module contains.
      *
      * ⚠ It is a LINE output on a headphone-shaped connector: ~2 V p-p through
      * 100 ohm into 32 ohm headphones is about a quarter of the level anything
      * else they plug in will give. 7.1 prices a driver at +1 IC and refuses
      * it - audio.md 16 item 29 decides at bring-up. */}
    {["L", "R"].map((side, i) => (
      <group key={side}>
        <capacitor name={`C${i + 1}`} capacitance="10uF" footprint="1206" polarized
          connections={{ pin1: `net.SUM_${side}`, pin2: `net.OUT_${side}` }} />
        <resistor name={`R${i + 1}`} resistance="100" footprint="0805"
          connections={{ pin1: `net.OUT_${side}`, pin2: `net.AUDIO_${side}` }} />
      </group>
    ))}

    {/* J2 - 3.5 mm stereo, on the card's rear edge, added 2026-09-08.
      *
      * graphics.md 17 put AUDIO_L/AUDIO_R and two dedicated AGND returns on the
      * backplane and lib/slot.ts carries them at B32-B35 - and NOTHING in the
      * machine consumes them. There is no chassis, no rear panel and no
      * document that says where the pair terminates. The jack is the same two
      * nodes wired to two more places, it costs no ICs, and it makes the card
      * testable on a bench with no backplane at all. The backplane pair is
      * kept unchanged.
      *
      * ⚠ FOOTPRINT: "pinrow3" is a 3-pin header, not a 3.5 mm receptacle - the
      * netlist is right and the outline is not, the same caveat the slot socket
      * carries (hardware/README.md open item 2). Tip = left, ring = right,
      * sleeve = AGND, and the sleeve goes to the ANALOGUE ground: audio.md 10
      * requires analogue and digital grounds to meet at exactly one point, and
      * a jack shell bonded to a chassis is the classic way to make a second. */}
    <chip
      name="J2"
      footprint="pinrow3"
      pinLabels={{ pin1: "TIP", pin2: "RING", pin3: "SLEEVE" }}
      connections={{ TIP: "net.AUDIO_L", RING: "net.AUDIO_R", SLEEVE: "net.AGND" }}
    />

    <netlabel net="AUDIO_L" anchorSide="left" schX={4} schY={2} />
    <netlabel net="AUDIO_R" anchorSide="left" schX={4} schY={1} />
  </Card>
)
