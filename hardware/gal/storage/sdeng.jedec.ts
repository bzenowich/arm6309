import { place } from "../jedec/place"
import type { Cell, Design } from "../jedec/assemble"

/* ------------------------------------------------------------------------
 * sdeng - SDCTRL, and the burst engine that turns one bus access into
 * exactly eight SPI clocks.
 *
 * ** THE BURST (sdcard.md §3.1, §6.5). sdbus decodes an SDDATA access and
 * holds DATSTB through E-high; this part takes its FALLING edge, so the
 * burst starts when the access ends and the '574 has already latched. Eight
 * rising SCK edges later the '595 holds the byte a following read will see.
 * ⛔ AT 12.588 MHz A BURST IS 636 ns, WHICH IS LONGER THAN A BUS CYCLE, NOT
 * SHORTER - 1.33 of the machine's 476.7 ns. §6.3 said the reverse and so did
 * this header until 2026-09-20; storage_tb caught it. What makes BUSY safe to
 * ignore at speed is not the bus cycle, it is the INSTRUCTION: §6.5's margin
 * is a native-mode `STA >SDDATA` at 4-5 cycles, 1.9-2.4 us against 0.636, a
 * 3x margin. ⚠ A driver that issued an SDDATA access every bus cycle would
 * hit §6.5's lockout every time.
 *
 * ** EVERYTHING IS CLOCKED BY CLK25 AND SPICLK IS AN ENABLE, which is the
 * one real departure from §3.3's circuit and it is worth stating why. The
 * document has the '393's two taps muxed into a clock; a GAL22V10 has ONE
 * clock pin, so a part holding both SDCTRL (written at E rate) and the burst
 * counter (running at SPI rate) cannot clock them both. Clocking SDCTRL off
 * a 393 kHz tap would miss a 238 ns write strobe outright. Both taps come
 * off the '393, which counts CLK25, so both are CLK25-domain signals and
 * edge-detecting them costs one macrocell and removes the question.
 *
 * ⭐ AND IT DELETES §3.3's RUNT-PULSE HAZARD. The document's rule - "change
 * the SCK rate only with /CS high and BUSY low, then eight dummy clocks" -
 * exists because a combinational mux between two asynchronous ripple taps
 * can emit a clock edge the card sees but does not resolve. Here BUSY only
 * ever changes on SPICLK's FALLING edge (FALL below), so SCK's high phases
 * are whole ones whatever the mux is doing, and the rate can change under a
 * running card without desynchronising it. The rule is kept anyway in §9.0,
 * because a card mid-command does not care whose fault the extra edge was.
 *
 * ** WHAT IS WIRED AND NOT COMPUTED, because a pin is cheaper than a cell:
 *
 *   the '163's /CLR   <- BUSY          held clear while idle, so it counts
 *                                      1..8 from the instant BUSY rises and
 *                                      CNT8 (its Q3) is the eighth edge.
 *                                      ⭐ This is also §6.5's lockout, and
 *                                      it is structural rather than a term:
 *                                      a mid-burst access cannot reload a
 *                                      counter whose clear is deasserted.
 *   the '165's SH//LD <- BUSY          low while idle, so the shifter tracks
 *                                      the '574 and MOSI already carries bit
 *                                      7 when the first edge arrives. §6.4's
 *                                      power-up rule - DI high for 74 clocks
 *                                      - is then one write of $FF to SDMOSI.
 *   the '165's CLK    <- SCKN          ⭐ the INVERTED gated clock, so DI
 *                                      changes on SCK's falling edge and is
 *                                      stable a whole half period before the
 *                                      card samples it. §6.6's robust form,
 *                                      and see SCKN below for what paid.
 *
 * ** SOFT RESET is SDCTRL b7 and it clears BUSY, which clears the '163 with
 * it. It cannot clear SDCTRL itself - the GAL's one asynchronous-reset
 * product term is spent on /RESET (§6.4) - and it does not need to: writing
 * $00 is the same instruction.
 * ------------------------------------------------------------------------ */

/* The soft reset rides in the hold terms rather than costing a cell, so
 * every BUSY term is qualified twice: !(CTRLW & D7) is two alternatives. */
const LIVE = ["!CTRLW", "!D7"]
const qualified = (t: string) => LIVE.map((q) => `${t} & ${q}`)

const cells: Cell[] = [
  /* SDCTRL b0 and b1 (§6.2). $00 is the safe state - /CS released, init
   * clock - and `ar` below is what makes /RESET force it. */
  { pin: 0, name: "CS", assertedLow: false, s0: 1, registered: true,
    terms: ["CTRLW & D0", "!CTRLW & CS"] },
  { pin: 0, name: "FAST", assertedLow: false, s0: 1, registered: true,
    terms: ["CTRLW & D1", "!CTRLW & FAST"] },

  /* the '393's two taps, selected: 25.175/2 = 12.588 MHz for transfer,
   * 25.175/64 = 393 kHz for the init sequence SD caps at 400 (§3.3) */
  { pin: 0, name: "SPICLK", assertedLow: false, s0: 1,
    terms: ["FAST & DIV2", "!FAST & DIV64"] },
  /* one CLK25 of delay, so the two edges below are visible */
  { pin: 0, name: "SPQ", assertedLow: false, s0: 1, registered: true, terms: ["SPICLK"] },
  /* sdbus's DATSTB, delayed, so its falling edge is visible */
  { pin: 0, name: "DATQ", assertedLow: false, s0: 1, registered: true, terms: ["DATSTB"] },
  /* a burst is owed. ⚠ Cleared by BUSY rising, so a trigger that arrives
   * mid-burst is DROPPED and not queued - §6.5's specified behaviour, and
   * its note records the pending flop as the thing a bigger part would buy. */
  { pin: 0, name: "TRIGP", assertedLow: false, s0: 1, registered: true,
    terms: ["!DATSTB & DATQ", "TRIGP & !BUSY"] },

  /* the burst itself: eight SCK edges, started and ended on FALL */
  /* ⭐ FALL IS INLINED, and that is what pays for SCKN below. It was a cell
   * of its own - `!SPICLK & SPQ`, SPICLK's falling edge - and the only place
   * it is used is here, so folding it in costs BUSY four product terms
   * (!FALL is `SPICLK # !SPQ`, two alternatives) and takes this equation to
   * 8 of its macrocell's 16. The freed macrocell is §6.6's inverted clock. */
  { pin: 0, name: "BUSY", assertedLow: false, s0: 1, registered: true,
    terms: [
      ...qualified("TRIGP & !BUSY & !SPICLK & SPQ"),
      ...qualified("BUSY & !CNT8"),
      ...qualified("BUSY & SPICLK"),
      ...qualified("BUSY & !SPQ"),
    ] },

  /* the gated clock the card sees. Idles LOW, which is SPI mode 0. */
  { pin: 0, name: "SCK", assertedLow: false, s0: 1, terms: ["SPICLK & BUSY"] },
  /* ⭐ §6.6's ROBUST FORM, TAKEN 2026-09-20. The same gated clock inverted,
   * for the '165 alone: MOSI then changes on SCK's FALLING edge and is
   * stable for a full half period - 39.7 ns at 12.588 MHz - before the card
   * samples it on the rising one. That is what a mode-0 master does.
   * ⛔ The alternative it replaces rested on an UNSPECIFIED number: with the
   * '165 clocked by SCK itself, DI changes and is sampled at the same
   * instant and correctness needs the '165's MINIMUM propagation delay to
   * exceed the card's hold time - and HC datasheets specify maxima only.
   * §6.6 priced this at one macrocell the part did not have or a 15th
   * package; inlining FALL above found the macrocell, so it costs neither
   * and the bench no longer has to decide it. */
  { pin: 0, name: "SCKN", assertedLow: true, s0: 0, terms: ["SPICLK & BUSY"] },
  /* the '595's storage clock. ⚠ Held low through the burst and RELEASED at
   * its end: the rising edge that moves the shift register into the storage
   * register is BUSY falling, 636 ns after the access that asked for it
   * (§3.4's second check: the byte a read returns is the PREVIOUS burst's,
   * and it has been in the storage register since that burst ended). */
  { pin: 0, name: "RCLK", assertedLow: true, s0: 0, terms: ["BUSY"] },
]

const pins = place(cells, [14, 15, 16, 17, 18, 19, 20, 21, 22, 23])

export const sdengDesign: Design = {
  name: "sdeng",
  partNo: "ARM6309-SDE",
  location: "storage card - SDCTRL and the eight-clock burst engine",
  signature: "A6309SE",
  clockPin: 1,
  inputs: [
    { name: "RESET", pin: 2, activeLow: true },
    /* sdbus's two strobes */
    { name: "CTRLW", pin: 3 },
    { name: "DATSTB", pin: 4 },
    /* the '393's taps */
    { name: "DIV2", pin: 5 }, { name: "DIV64", pin: 6 },
    /* the '163's Q3: the eighth clock of a counter held clear while idle */
    { name: "CNT8", pin: 7 },
    /* the data bus, for SDCTRL's three live bits */
    { name: "D0", pin: 8 }, { name: "D1", pin: 9 }, { name: "D7", pin: 10 },
  ],
  cells: cells.map((c) => ({ ...c, pin: pins[c.name] })),
  /* All ten macrocells are used. Pins 11 and 13 are dedicated INPUTS and are
   * the only headroom - an output needs a macrocell, which is why §6.6's
   * inverted clock had to be paid for by inlining FALL and not by a pin. */
  spares: [],
  /* §6.4: /RESET forces SDCTRL to $00 and leaves no burst in flight */
  ar: "RESET",
}
