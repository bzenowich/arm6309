/* Every card's parts, as footprints — the input to the placement study.
 *
 * ⚠ THIS IS A SECOND COPY OF SIX CHIP BUDGETS and that is the thing to watch.
 * Each list is transcribed from its card's own document, cited per card, and
 * place.check.ts asserts the total against the `icBudget` the tscircuit board
 * file declares. That assertion is not decoration: on 2026-09-08 the storage
 * card was recorded as 13 ICs when its own §8 table listed 14, because the
 * rows are numbered 1–13 and two of them carry more than one part. Counting
 * footprints is what found it.
 *
 * Dimensions are body sizes in millimetres. A DIP is (pins / 2) × 2.54 long
 * and 7.62 or 15.24 wide across the rows; pack.ts adds the courtyard.
 */

export type Kind = "pld" | "mem" | "bus" | "glue" | "analog" | "clk" | "conn"

export interface Part {
  /** Long axis, mm. */ l: number
  /** Across the pin rows, mm. */ w: number
  label: string
  kind: Kind
  qty: number
  /** What fits inside the package outline on the drawing. */ short: string
  /** Counts toward the card's IC total.
   *
   * ⚠ THE DOCUMENTS DISAGREE ABOUT OSCILLATORS and this flag is where that
   * lives. `audio.md` §10 numbers its 28.37516 MHz can as a row of the 29;
   * `net.md` §9 lists its 20 MHz can below the numbered rows, and
   * `serial.md` §9 says "Total: 3. Plus a 1.8432 MHz crystal". So a can is an
   * IC on one card and not on another. The footprint is placed either way —
   * it occupies board — and only the count follows the card's own document.
   */
  counted: boolean
}

const dip = (pins: number, wide: 0.3 | 0.6, label: string, kind: Kind, qty = 1): Part => ({
  l: (pins / 2) * 2.54, w: wide === 0.3 ? 7.62 : 15.24, label, kind, qty,
  short: label.split(" ")[0], counted: true,
})
const pkg = (l: number, w: number, label: string, kind: Kind, qty = 1, short?: string): Part =>
  ({ l, w, label, kind, qty, short: short ?? label.split(" ")[0], counted: true })
/** Placed, but not an IC in this card's own budget — see Part.counted. */
const uncounted = (p: Part): Part => ({ ...p, counted: false })

/** A connector or analogue block that owns a piece of the rear edge. */
export interface Rear { w: number; h: number; label: string; kind: Kind }

export interface CardSpec {
  title: string
  /** Board length in mm — one of LENGTHS. place.check.ts asserts it is minimal. */
  length: number
  /** IC count the card's own document claims. */
  ics: number
  source: string
  note: string
  rear: Rear[]
  parts: Part[]
}

/** The three lengths a card may take. 100 mm high throughout. */
export const LENGTHS = [120, 180, 240] as const
export const BOARD_H = 100
export const FINGER_W = 91.4
export const FINGER_H = 11

export const CARDS: Record<string, CardSpec> = {
  video: {
    title: "Video", length: 240, ics: 33, source: "video/docs/graphics.md 14.1",
    note: "640x200 x 256 colours, VGA out",
    rear: [{ w: 53, h: 17, label: "DE-15 VGA", kind: "conn" },
           { w: 53, h: 20, label: "analogue drive + R-2R", kind: "analog" }],
    parts: [
      /* ⭐ THREE ATF1508AS SINCE 2026-09-09 - graphics.md 10.1.7. vsup absorbs
       * the three GAL22V10s (rfa, vlen, pxsel) and carries 9's palette write
       * path and 10.3.3's list register port, neither of which had anywhere to
       * live on a card of two CPLDs. Three GALs out, one CPLD in: -2. */
      pkg(33, 33, "ATF1508AS vaddr/vctrl/vsup", "pld", 3, "1508"),
      /* 14.2: two x16 parts feed the dot clock where four x8 did, and one
       * holds the whole 16-bit palette. TSOP-44 II is a 10.16 x 18.42 mm body
       * with the leads on the short ends; 11.8 includes them, which is the
       * same convention dip() uses when it takes the row spacing. */
      pkg(18.4, 11.8, "AS6C8016 512Kx16", "mem", 2, "8016"),
      pkg(18.4, 11.8, "IS61C6416 64Kx16 LUT", "mem", 1, "6416"),
      dip(28, 0.6, "32Kx8 regfile", "mem"),
      /* ⭐ EIGHT, IN TWO RANKS - graphics.md 8.2, 19 item 28. Byte-granular
       * horizontal scroll needs two fetch groups live at once and one rank of
       * latches provably cannot hold them; the rank select is an output enable
       * because `c < HSCROLL[1:0]` is constant for a whole line. */
      dip(20, 0.3, "74AHCT574 fetch", "bus", 8),
      dip(16, 0.3, "74AHCT153 mux", "bus", 4),
      dip(20, 0.3, "74AHCT574 index", "bus"),
      dip(20, 0.3, "74AHCT273 out", "bus", 2),
      /* ⭐ 9's PALETTE WRITE PATH, and none of it existed before 2026-09-09 -
       * design-review2.md's defect class, found again. 19 item 9 closed at the
       * same time: the 74HC593 the parts list carried is DISCONTINUED, so PIDX
       * is two loadable '163s with ordinary outputs plus a '244 onto 13.1's
       * LUT address bus, and the two '573s are 13's +$11/+$12 - the 16-bit
       * entry a card with an 8-bit bus has to assemble somewhere. */
      dip(16, 0.3, "74AHCT163A PIDX", "bus", 2),
      dip(20, 0.3, "74AHCT244 pidx-oe", "bus"),
      dip(20, 0.3, "74HC573 PDAT", "bus", 2),
      /* 10.3.3: the display list's descriptor byte, from the pixel bus onto
       * the card's internal data bus, for the dot a granted engine slot lasts.
       * It is what makes a list MOVE reach a register at all. */
      dip(20, 0.3, "74HCT244 lbyte", "bus"),
      dip(20, 0.3, "74HC574 pw-data", "bus"),
      /* ⚠ NO ADDRESS LATCH - graphics.md 3.1.1, 19 item 44, 2026-09-11. Three
       * '574s for the posted write's physical address were listed here and no
       * design clocked them: every CPU VRAM access is at WPTR. */
      dip(20, 0.3, "74HCT245 rdbk", "bus"),
      dip(20, 0.3, "74HCT574 vread", "bus"),
      dip(20, 0.3, "74HC244 VSTAT", "bus"),
      dip(20, 0.3, "74HC244 fanout", "bus"),
    ],
  },
  audio: {
    title: "Audio", length: 180, ics: 35, source: "audio/docs/audio.md 10",
    note: "4-channel 8-bit PCM, Paula-exact, panned",
    /* audio.md 7.1: the output is line level on a 3.5 mm stereo jack at the
     * rear edge, in parallel with the backplane's AUDIO_L/R pair. Nothing
     * consumed that pair - there is no chassis and no rear panel - and this
     * is what makes the card testable with no backplane at all. */
    rear: [{ w: 47, h: 24, label: "analogue out + filters", kind: "analog" },
           { w: 14, h: 13, label: "3.5 mm hp", kind: "conn" }],
    parts: [
      /* 10.1: TWO, since 2026-09-09. U1 is the host register block and is
       * fitted at 89 of 128 logic cells and 57 of 64 I/O; U2 is the sequencer
       * of 10.2, ~69 I/O, and its package is that section's open decision -
       * a PLCC-84 is one pin short before any of its three levers. Drawn as
       * two PLCC-84 because that is the choice this footprint has to make. */
      pkg(33, 33, "ATF1508AS", "pld", 2, "1508"),
      pkg(20.3, 12.7, "28.375 MHz osc", "clk", 1, "OSC"),
      /* 5: 512 KB in one package, the part the motherboard stopped using when
       * ram.md 6.2 went to SIMM sockets. 5.3: the state file is two x16 parts
       * where it was three x8 - TSOP-44 II, the same body the video card's
       * framebuffer takes, and 32 bits wide where word 0 needs 24. */
      dip(32, 0.6, "AS6C4008 sample RAM", "mem"),
      pkg(18.4, 11.8, "IS61C6416 state file", "mem", 2, "6416"),
      dip(16, 0.3, "74HC283 adder", "bus", 4),
      /* 10.2.2: the datapath, enumerated on 2026-09-09. The three "pipeline
       * latches" this list carried were never the adder's operand registers,
       * and nothing here had counted the $FFFF constant or the three-state
       * path from the sum back onto the state file's data bus. Six packages,
       * and none of them is new design - every one is required by the
       * datapath 3.2, 4.2 and 9.5 already describe. */
      dip(20, 0.3, "74HC574 ALAT", "bus", 2),
      dip(20, 0.3, "74HC574 BLAT", "bus", 2),
      dip(20, 0.3, "74HC244 B=$FFFF", "bus", 2),
      dip(20, 0.3, "74HC244 sum OE", "bus", 2),
      dip(20, 0.3, "74HC574 sample hold", "bus", 1),
      /* 6.2's windows collide with the walk order at two registers per side -
       * ch0's byte is on the bus in slot 0 and ch3's in slot 3, and one
       * register cannot hold both across two four-slot windows. One per
       * channel, three-stated onto the package port each shares. */
      dip(20, 0.3, "74HC574 conv port", "bus", 4),
      /* 10.2.6's lever, pulled: four port-register clocks and three chip
       * selects are mutually exclusive, so they are one 3-bit code and eight
       * decoder outputs with nothing left over. */
      dip(16, 0.3, "74HC138 conv ctl", "bus", 1),
      /* The state file's byte-lane write enables, gated with the slot clock's
       * second half - an inverter and three gates, exactly. */
      dip(14, 0.3, "74HC00 /WE gate", "bus", 1),
      /* 6.3: eight halves - one sample and one volume converter per channel.
       * Programmable panning was given up on 2026-09-09; classic MOD's fixed
       * LRRL is which summing node an output is wired to, and the second
       * volume half per channel went with it, and a TL074 with that. */
      dip(20, 0.3, "AD7528 dual MDAC", "analog", 4),
      dip(14, 0.3, "TL074", "analog", 2),
      dip(8, 0.3, "TL072", "analog"),
      dip(14, 0.3, "74HC4066", "analog"),
      /* 7.1: the jack is a headphone output and the backplane pair is a line
       * output - two signals, not one. 70 mA into 32 ohm where a TL072 would
       * clip below ~200. It belongs beside the jack in the analogue section,
       * not beside the CPLD. */
      dip(8, 0.3, "NJM4556A hp drv", "analog"),
      dip(20, 0.3, "74HC574 pw", "bus"),
    ],
  },
  net: {
    title: "Net", length: 120, ics: 12, source: "net/docs/net.md 9",
    note: "10BASE-T, no MAC or PHY chip",
    rear: [{ w: 35, h: 23, label: "RJ45 MagJack", kind: "conn" },
           { w: 35, h: 16, label: "TX filter", kind: "analog" }],
    parts: [
      pkg(33, 33, "ATF1508AS U1/U2", "pld", 2, "1508"),
      uncounted(pkg(20.3, 12.7, "20 MHz osc", "clk", 1, "OSC")),
      dip(28, 0.6, "62256 RX ring", "mem"),
      dip(24, 0.6, "6264 TX", "mem"),
      dip(20, 0.3, "74HC244 addr", "bus", 2),
      dip(20, 0.3, "74HCT245 data", "bus"),
      dip(16, 0.3, "SN75C1168", "analog"),
      dip(14, 0.3, "74HC86 edge", "glue"),
      dip(16, 0.3, "74HC221 rec_clk", "glue"),
      dip(16, 0.3, "74HC123 NIDLE", "glue"),
      dip(16, 0.3, "74HC4020 NLP", "glue"),
    ],
  },
  storage: {
    title: "Storage", length: 120, ics: 14, source: "storage/docs/sdcard.md 8",
    note: "SD over SPI, 681 KiB/s",
    rear: [{ w: 33, h: 26, label: "SD socket", kind: "conn" },
           { w: 27, h: 13, label: "3V3 LDO", kind: "analog" }],
    parts: [
      dip(24, 0.3, "GAL22V10", "pld", 2),
      dip(24, 0.6, "6116 block buffer", "mem"),
      dip(16, 0.3, "74HCT595 MISO", "bus"),
      dip(16, 0.3, "74HC165 MOSI", "bus"),
      dip(20, 0.3, "74HC574 hold", "bus"),
      dip(16, 0.3, "74HC163 burst", "glue"),
      dip(14, 0.3, "74HC393 divider", "clk"),
      dip(14, 0.3, "74LVC125 3V3", "bus"),
      dip(16, 0.3, "74HC4040 blkaddr", "glue"),
      dip(16, 0.3, "74HC157 addr mux", "bus", 3),
      dip(20, 0.3, "74HCT245 data", "bus"),
    ],
  },
  io: {
    title: "I/O", length: 120, ics: 14, source: "io/ps2/docs/ps2.md 9 + io/serial/docs/serial.md 9",
    note: "PS/2 keyboard + mouse and RS-232, one card",
    rear: [{ w: 31, h: 19, label: "DE-9 serial", kind: "conn" },
           { w: 28, h: 20, label: "mini-DIN kbd", kind: "conn" },
           { w: 28, h: 20, label: "mini-DIN mouse", kind: "conn" }],
    parts: [
      dip(24, 0.3, "GAL22V10 ps2", "pld"),
      dip(24, 0.3, "GAL22V10 serial", "pld"),
      /* serial.md 4.5 tier 1, taken 2026-09-09: a 16C550 replaces the 6551
       * ONE FOR ONE. The "+1 IC" that tier was priced at counted the baud
       * crystal in one row and not the other (serial.md 9.1). It is a bigger
       * package - DIP-40 against DIP-28 - and that is the real cost here. */
      dip(40, 0.6, "TL16C550C UART", "pld"),
      dip(16, 0.3, "MAX232", "analog"),
      uncounted(pkg(11.5, 4.7, "7.3728 MHz xtal", "clk", 1, "XTAL")),
      dip(20, 0.3, "74HC273 IOCTRL", "bus"),
      dip(20, 0.3, "74HC244 IOSTAT", "bus"),
      dip(14, 0.3, "7407 open-coll", "glue"),
      dip(14, 0.3, "74HCT132 Schmitt", "glue"),
      dip(16, 0.3, "74HC595 shift", "bus", 2),
      dip(16, 0.3, "74HC193 bitcnt", "glue", 2),
      dip(20, 0.3, "74HC574 latch", "bus", 2),
    ],
  },
}

/** ICs as the card's own document counts them — see Part.counted. */
export const icCount = (c: CardSpec) =>
  c.parts.reduce((n, p) => n + (p.counted ? p.qty : 0), 0)

/** Every footprint that occupies board, counted or not. */
export const footprintCount = (c: CardSpec) => c.parts.reduce((n, p) => n + p.qty, 0)
