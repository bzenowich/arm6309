/* The $FF I/O map, docs/machine.md 3, as data.
 *
 * Every window here is still *proposed* by its own card document except video's,
 * which is taken. The check in lib/cards.check.ts is what stops two proposals
 * from quietly overlapping.
 *
 * net/docs/net.md 5.1 took the last of the original 64 bytes - storage handed
 * four back, machine.md 3 called that "one small card, once", and net was
 * that card. 64 of 64 with nothing free is what forced machine.md 5 item 1,
 * and widening the window below $FF40 is the answer it took.
 */
export interface Window { card: string; base: number; size: number; status: "taken" | "proposed" | "free"; source: string }

/* Widened from $FF40-$FF7F to $FF00-$FF7F on 2026-09-08 - machine.md 5 item 1
 * option A, taken. /IOSEL is now /IOPAGE AND A7 = 0, which is one term FEWER
 * than the 64-byte version it replaces (gal/clkdec.pld).
 *
 * THE COST IS ON THE CARDS: A6 is no longer implied by the strobe, so a card
 * that matches only A0-A5 answers at its base AND 64 bytes below it. Every
 * card decodes A0-A6. gal/vctrl.pld is the one card decode that exists here
 * and it was changed with this. */
export const GEOGRAPHIC_WINDOW = { base: 0xff00, size: 0x80 }

export const WINDOWS: Window[] = [
  { card: "(free)",  base: 0xff00, size: 64, status: "free",     source: "machine.md 5 item 1 option A, taken 2026-09-08" },
  { card: "audio",   base: 0xff40, size: 16, status: "proposed", source: "audio/docs/audio.md 9.1" },
  { card: "ps2",     base: 0xff50, size: 4,  status: "proposed", source: "io/ps2/docs/ps2.md 3.2" },
  { card: "serial",  base: 0xff54, size: 4,  status: "proposed", source: "io/serial/docs/serial.md 7.1" },
  { card: "storage", base: 0xff58, size: 4,  status: "proposed", source: "storage/docs/sdcard.md 6.1" },
  { card: "net",     base: 0xff5c, size: 4,  status: "proposed", source: "net/docs/net.md 5.1" },
  { card: "video",   base: 0xff60, size: 32, status: "taken",    source: "video/docs/graphics.md 13" },
]
