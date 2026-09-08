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
    title: "Video", length: 180, ics: 27, source: "video/docs/graphics.md 14.1",
    note: "640x200 x 256 colours, VGA out",
    rear: [{ w: 53, h: 17, label: "DE-15 VGA", kind: "conn" },
           { w: 53, h: 20, label: "analogue drive + R-2R", kind: "analog" }],
    parts: [
      pkg(33, 33, "ATF1508AS vaddr/vctrl", "pld", 2, "1508"),
      dip(24, 0.3, "GAL22V10 rfa", "pld"),
      /* 14.2: two x16 parts feed the dot clock where four x8 did, and one
       * holds the whole 16-bit palette. TSOP-44 II is a 10.16 x 18.42 mm body
       * with the leads on the short ends; 11.8 includes them, which is the
       * same convention dip() uses when it takes the row spacing. */
      pkg(18.4, 11.8, "AS6C8016 512Kx16", "mem", 2, "8016"),
      pkg(18.4, 11.8, "IS61C6416 64Kx16 LUT", "mem", 1, "6416"),
      dip(28, 0.6, "32Kx8 regfile", "mem"),
      dip(20, 0.3, "74AHCT574 fetch", "bus", 4),
      dip(16, 0.3, "74AHCT153 mux", "bus", 4),
      dip(20, 0.3, "74AHCT574 index", "bus"),
      dip(20, 0.3, "74AHCT273 out", "bus", 2),
      dip(20, 0.3, "74HC593 PIDX", "bus"),
      dip(20, 0.3, "74HC574 pw-data", "bus"),
      dip(20, 0.3, "74HC574 pw-addr", "bus", 3),
      dip(20, 0.3, "74HC245 rdbk", "bus"),
      dip(20, 0.3, "74HC574 vread", "bus"),
      dip(20, 0.3, "74HC244 VSTAT", "bus"),
      dip(20, 0.3, "74HC244 fanout", "bus"),
    ],
  },
  audio: {
    title: "Audio", length: 180, ics: 29, source: "audio/docs/audio.md 10",
    note: "4-channel 8-bit PCM, Paula-exact",
    rear: [{ w: 47, h: 24, label: "analogue out + filters", kind: "analog" }],
    parts: [
      pkg(33, 33, "ATF1508AS", "pld", 1, "1508"),
      pkg(20.3, 12.7, "28.375 MHz osc", "clk", 1, "OSC"),
      dip(32, 0.6, "AS6C1008 sample RAM", "mem"),
      dip(24, 0.3, "CY7C128A state file", "mem", 3),
      dip(16, 0.3, "74HC590 counter", "bus", 2),
      dip(20, 0.3, "74HC688 compare", "bus", 2),
      dip(16, 0.3, "74HC283 adder", "bus", 4),
      dip(20, 0.3, "74HC574 pipeline", "bus", 3),
      dip(20, 0.3, "74HC574 conv port", "bus", 2),
      dip(20, 0.3, "AD7528 dual MDAC", "analog", 4),
      dip(14, 0.3, "TL074", "analog", 2),
      dip(8, 0.3, "TL072", "analog"),
      dip(14, 0.3, "74HC4066", "analog"),
      dip(20, 0.3, "74HC574 pw", "bus"),
      dip(20, 0.3, "74HC574 prefetch", "bus"),
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
      dip(28, 0.6, "G65SC51 ACIA", "pld"),
      dip(16, 0.3, "MAX232", "analog"),
      uncounted(pkg(11.5, 4.7, "1.8432 MHz xtal", "clk", 1, "XTAL")),
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
