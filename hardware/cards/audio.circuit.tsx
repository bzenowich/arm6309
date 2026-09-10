/* Audio card - 4-channel 8-bit PCM, Paula-exact, with programmable per-channel
 * panning. 39 ICs, audio/docs/audio.md 10 - and that number moved from 32 on
 * 2026-09-09, when the sequencer was enumerated (10.2) and turned out to be a
 * SECOND ATF1508AS plus six datapath packages the chip budget had never
 * counted. It is an enumeration and not a fit; 16 item 00 is what closes it.
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
  <Card name="arm6309-audio" ioBase={0xff40} ioSize={16} length={180} icBudget={35}>
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
      * when the card was drawn and it is TWO ATF1508AS now (10.1, 10.2 - and
      * only U1 is drawn here), for a reason that
      * is not package-count: 9.5's interrupt block does not fit a GAL22V10
      * whole (13 equations, 10 macrocells) or split (17 inputs, 14 pins), so
      * the GAL allocation was six and rising. The part also absorbs the '273,
      * the three '174 synchronisers and the '07, the last because an
      * ATF1508AS output has a programmable open-collector option and 8.1 needs
      * the wire-OR a GAL's totem-pole pin cannot do.
      *
      * hardware/gal/cpld/audio.jed is the fitted device: 89 of 128 logic
      * cells, 57 of 64 I/O, refitted 2026-09-09 with 9.1's decode and 9.3's
      * read-back path, neither of which had ever been built. Pin numbers below are the ones the
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
      *   divider: into 32 ohm it costs 2.6 dB and into a 10 kohm line input
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
