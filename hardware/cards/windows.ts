/* The $FF I/O map, docs/machine.md 3, as data.
 *
 * Every window here is still *proposed* by its own card document except video's,
 * which is taken. The check in lib/cards.check.ts is what stops two proposals
 * from quietly overlapping.
 */
export interface Window { card: string; base: number; size: number; status: "taken" | "proposed" | "free"; source: string }

export const GEOGRAPHIC_WINDOW = { base: 0xff40, size: 0x40 }

export const WINDOWS: Window[] = [
  { card: "audio",   base: 0xff40, size: 16, status: "proposed", source: "audio/docs/audio.md 9.1" },
  { card: "ps2",     base: 0xff50, size: 4,  status: "proposed", source: "io/ps2/docs/ps2.md 3.2" },
  { card: "serial",  base: 0xff54, size: 4,  status: "proposed", source: "io/serial/docs/serial.md 7.1" },
  { card: "storage", base: 0xff58, size: 4,  status: "proposed", source: "storage/docs/sdcard.md 6.1" },
  { card: "(free)",  base: 0xff5c, size: 4,  status: "free",     source: "handed back by storage" },
  { card: "video",   base: 0xff60, size: 32, status: "taken",    source: "video/docs/graphics.md 13" },
]
