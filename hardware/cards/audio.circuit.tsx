/* Audio card - 4-channel 8-bit PCM for ProTracker playback, Paula's fixed
 * LRRL panning. 35 ICs, audio/docs/audio.md 10: U1 (audio) and U2 (aseq) are
 * both ATF1508AS PLCC-84 and both fitted (gal/cpld/audio.fit, aseq.fit).
 *
 * NOT a board yet. What is drawn is U1's clock, reset and power pins, the
 * card's clock source, and the analogue output stage from the summing nodes
 * outward. The host bus pins, U2, the state file, the sample RAM, the adder,
 * the converters and their port registers are not drawn; audio.md 10.1 keeps
 * the datapath pinout open, and gal/pins.check.ts holds the pin senses that
 * are settled until they are.
 *
 * The one thing this card does not take from the backplane is its clock: its
 * period reference is its own 28.37516 MHz, the Amiga PAL master, and
 * audio.md 4.1 calls that non-negotiable because every module in the corpus was
 * tuned by ear against exactly that number.
 *
 * ⛔ REMOVED 2026-09-11: a 74HC574 drawn as "U2" on D0-D7 with its /OE, CP and
 * inputs unconnected. The prefetch latch it stood for is eight registers inside
 * U1 (audio.md 9.3), and U2 is the sequencer.
 */
import { Card } from "../lib/Card"

export default () => (
  <Card name="arm6309-audio" ioBase={0xff40} ioSize={16} length={180} icBudget={35}>
    {/* OSC1 - not the backplane's 25.175 MHz. machine.md 1's one-master rule
      * has exactly one exception and this is it.
      *
      * ⛔ AN OSCILLATOR CAN, since 2026-09-11 - audio.md 10's "1 x 28.37516 MHz
      * osc" and place/parts.ts. It was drawn as a bare crystal with one leg
      * grounded, into a CPLD's global clock input, which has no amplifier to
      * make it oscillate. Same half-can pinout as the motherboard's OSC1. */}
    <chip
      name="OSC1"
      footprint="dip8_w0.3in"
      pinLabels={{ pin1: "EN", pin4: "GND", pin5: "OUT", pin8: "VCC" }}
      connections={{ EN: "net.V5", GND: "net.GND", VCC: "net.V5", OUT: "net.PAL_OSC" }}
      noConnect={["pin2", "pin3", "pin6", "pin7"]}
    />

    {/* U1 - the host interface, the interrupt block, the timer and the free-
      * running counter (audio.md 10.1). hardware/gal/cpld/audio.fit is the
      * fitted device: 107 of 128 cells, 62 of 64 I/O. Pin numbers are the ones
      * the fitter chose and they are NOT settled - fit1508.sh runs with
      * -preassign ignore, so every refit may move them. Only what the fitter
      * cannot move is drawn: the global clock, the global clear, and power.
      *
      * ⛔ PIN 84 IS NOT VCC. It was drawn tied to +5 V, and on an ATF1508AS
      * pin 84 is INPUT/OE1 - the fit puts CNTOE there. The part's eight VCC and
      * eight GND pins are below, all of them (2026-09-11).
      *
      * Socketed. It is programmed out of circuit, so JTAG is not routed. */}
    <chip
      name="U1"
      footprint="plcc84"
      pinLabels={{
        pin83: "SLOTCLK", pin1: "nRESET",
        pin3: "VCC1", pin13: "VCC2", pin26: "VCC3", pin38: "VCC4",
        pin43: "VCC5", pin53: "VCC6", pin66: "VCC7", pin78: "VCC8",
        pin7: "GND1", pin19: "GND2", pin32: "GND3", pin42: "GND4",
        pin47: "GND5", pin59: "GND6", pin72: "GND7", pin82: "GND8",
      }}
      connections={{
        VCC1: "net.V5", VCC2: "net.V5", VCC3: "net.V5", VCC4: "net.V5",
        VCC5: "net.V5", VCC6: "net.V5", VCC7: "net.V5", VCC8: "net.V5",
        GND1: "net.GND", GND2: "net.GND", GND3: "net.GND", GND4: "net.GND",
        GND5: "net.GND", GND6: "net.GND", GND7: "net.GND", GND8: "net.GND",
        /* 4.1: the card's own 28.37516 MHz reference, divided on-part. */
        SLOTCLK: "net.PAL_OSC",
        nRESET: "net.nRESET",
      }}
    />

    {/* ------------------------------------------------- the output, 7.1 --- */}
    {/* Two channels, and they must stay two. audio.md 1 requirement 5: Paula's
      * channels are 0 and 3 left, 1 and 2 right, and summing them to mono does
      * not make a module quieter, it makes it WRONG. The assignment is wiring -
      * Paula's hard pan exactly, and not a mode bit (ACTRL b5 is reserved).
      *
      * The DC block is good manners rather than load-bearing: 6.3 cancels the
      * sample converters' pedestal UPSTREAM of the volume stage, so the card's
      * output is already centred and is exactly zero when every channel is
      * silent. What the capacitor removes is zero-code leakage and amplifier
      * offsets - tens of millivolts, not half of full scale. 10 uF into 100k is
      * 0.16 Hz, four decades below anything a module contains.
      *
      * ⚠ THE BACKPLANE PAIR IS LINE LEVEL AND THE JACK IS NOT, and that is
      * the resolution of audio.md 16 item 29: a line signal on a 3.5 mm
      * connector reaches headphones at about a quarter of the level anything
      * else they plug in gives. U9 buffers the same two nodes for the jack. */}
    {["L", "R"].map((side, i) => (
      <group key={side}>
        <capacitor name={`C${i + 1}`} capacitance="10uF" footprint="1206" polarized
          connections={{ pin1: `net.SUM_${side}`, pin2: `net.OUT_${side}` }} />
        <resistor name={`R${i + 1}`} resistance="100" footprint="0805"
          connections={{ pin1: `net.OUT_${side}`, pin2: `net.AUDIO_${side}` }} />
      </group>
    ))}

    {/* U9 - the headphone driver, added 2026-09-09 (audio.md 7.1, 16 item 29).
      *
      * An NJM4556AD: dual, 70 mA output, DIP-8, and a 1980s JRC part rather
      * than a modern one. It taps SUM_L/SUM_R - the SAME nodes the line output
      * takes, ahead of that path's DC block - as a unity-gain follower, then
      * its own coupling capacitor and a series resistor into the jack.
      *
      * THE ARITHMETIC, because "add a buffer" is not a specification:
      *   2 V p-p is 0.707 V rms; into 32 ohm that is 22 mA rms and ~31 mA
      *   peak per channel, against the part's 70 mA. 0.707^2 / 32 = 15.6 mW,
      *   where a comfortable listening level is 1-5 mW - so there is headroom
      *   rather than a compromise.
      *   10 ohm in series is short-circuit protection and damping, not a
      *   divider: into 32 ohm it costs 2.4 dB (20 log 32/42) and into a 10 kohm line input
      *   nothing at all.
      *   470 uF into 32 ohm is 10.6 Hz, three decades below anything a module
      *   contains. The line path's 10 uF into 100 kohm is 0.16 Hz; a headphone
      *   load is 3,000 times lower and needs the capacitor 47 times larger.
      *
      * ⚠ IT IS A SEPARATE PATH, NOT A REPLACEMENT. The backplane pair stays
      * line level, because that is what a chassis jack or a mixer wants and
      * this machine has no chassis yet (hardware/README.md).
      *
      * ⚠ ANALOGUE GROUND, and it matters more here than anywhere else on the
      * card: this is the one node that leaves the board into something a
      * person touches, and audio.md 10 requires analogue and digital grounds
      * to meet at exactly ONE point. A jack shell bonded to a chassis is the
      * classic way to make a second. */}
    <chip
      name="U9"
      manufacturerPartNumber="NJM4556AD"
      footprint="dip8_w0.3in"
      pinLabels={{
        pin1: "OUT_A", pin2: "nIN_A", pin3: "IN_A", pin4: "VEE",
        pin5: "IN_B", pin6: "nIN_B", pin7: "OUT_B", pin8: "VCC",
      }}
      connections={{
        /* ⚠ THE ANALOGUE SECTION'S SPLIT RAILS, not +5 and ground. audio.md
         * 16 item 25: with 6.3's pedestal blocked rather than cancelled, the
         * signal between the I/V stage and the output capacitor lives between
         * 0 and -V_REF, so the analogue side needs a VSS below -V_REF and this
         * part rides the same pair.
         *
         * ⚠ AND IT CHANGES THAT ITEM. Item 25 is a rail decision that "costs
         * no packages" because everything on those rails is an op-amp signal
         * path drawing milliamps. This part draws up to ~60 mA into a
         * low-impedance load on both channels, from rails sized for
         * microamps - so the negative rail now needs current capability, not
         * just a voltage. audio.md 7.1. */
        VCC: "net.VA_POS", VEE: "net.VA_NEG",
        /* Unity-gain followers: output tied to the inverting input, signal
         * on the non-inverting one. No gain to set and no resistors to match. */
        IN_A: "net.SUM_L", nIN_A: "net.HP_L", OUT_A: "net.HP_L",
        IN_B: "net.SUM_R", nIN_B: "net.HP_R", OUT_B: "net.HP_R",
      }}
    />
    {["L", "R"].map((side, i) => (
      <group key={`hp${side}`}>
        <capacitor name={`C${i + 3}`} capacitance="470uF" footprint="1210" polarized
          connections={{ pin1: `net.HP_${side}`, pin2: `net.HPO_${side}` }} />
        <resistor name={`R${i + 3}`} resistance="10" footprint="0805"
          connections={{ pin1: `net.HPO_${side}`, pin2: `net.JACK_${side}` }} />
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
      * sleeve = AGND.
      *
      * DRIVEN BY U9, not by the line output: audio.md 7.1 and 16 item 29. The
      * backplane pair is line level and this is not. */}
    <chip
      name="J2"
      footprint="pinrow3"
      pinLabels={{ pin1: "TIP", pin2: "RING", pin3: "SLEEVE" }}
      connections={{ TIP: "net.JACK_L", RING: "net.JACK_R", SLEEVE: "net.AGND" }}
    />

    <netlabel net="AUDIO_L" anchorSide="left" schX={4} schY={2} />
    <netlabel net="AUDIO_R" anchorSide="left" schX={4} schY={1} />
  </Card>
)
