/* The arm6309 expansion slot — 72-pin 0.1" card edge, 2 x 36.
 *
 * Single source of truth for the backplane pinout. The motherboard's slot
 * sockets and every card's edge fingers are generated from this table, so the
 * two ends cannot disagree.
 *
 * Signal list: docs/machine.md 2, which is itself collated from
 * video/docs/graphics.md 17. Nothing is invented here; the only decisions this
 * file takes are *where* each signal sits, and those are argued in
 * hardware/README.md.
 *
 * Sizing. A 100 mm Eurocard edge at 0.1" pitch holds 39 positions; 36 leaves
 * 8.6 mm for the keying notch and mechanical margin. 45 signals + 2 audio
 * returns leave 25 positions for power, ground and the key.
 *
 * A34 WAS THE ONE SPARE AND IT IS NOW PHYSICAL A20 - machine.md 5 item 1
 * option D, taken 2026-09-08. It doubles the physical map to 2 MB for one
 * pin and no ICs: the map SRAM is already byte-wide and its eighth bit was
 * already stored and read back (gal/README.md), so A20 costs a trace out of
 * a latch that was carrying it anyway.
 *
 * THERE IS NO SPARE PIN NOW. net/docs/net.md 13.1 wanted two of them for a
 * DMA request/grant pair and hardware/README.md wanted one for a future
 * rail; A20 beat both on the arithmetic and that competition is over, not
 * deferred. A seventh signal position would have to come out of the ground
 * or power allocation, and slot.check.ts is what says what that costs.
 */

export type PinKind = "signal" | "power" | "ground" | "key" | "spare"

export interface SlotPin {
  /** "A12" / "B3" - row letter, then 1..36 counting from the card's front edge. */
  ref: string
  row: "A" | "B"
  position: number
  /** Net name, or KEY / SPARE for the positions that carry nothing. */
  signal: string
  kind: PinKind
}

/* Row A: the address bus, the CPU control inputs, and the bulk of the power.
 * Row B: data, the clocks, the interrupts and the analogue pair.
 *
 * A ground sits on both sides of every clock and sync line (B18-B27), and the
 * address and data fields carry a ground every four positions. The audio pair
 * is at the far end of row B from the clock group, each line with its own
 * dedicated return, so the analogue section never shares a return path with
 * 25.175 MHz. */
const ROW_A = [
  "GND", "+5V", "/RESET", "/HALT", "/WAIT", "KEY",
  "GND", "A0", "A1", "A2", "A3",
  "GND", "A4", "A5", "A6", "A7",
  "GND", "A8", "A9", "A10", "A11",
  "GND", "A12", "A13", "A14", "A15",
  "GND", "A16", "A17", "A18", "A19",
  "GND", "+5V", "A20", "+5V", "GND",
] as const

const ROW_B = [
  "GND", "+5V", "/IOSEL", "/IOPAGE", "R/W", "KEY",
  "GND", "D0", "D1", "D2", "D3",
  "GND", "D4", "D5", "D6", "D7",
  "GND", "E", "GND", "Q", "GND",
  "CLK25", "GND", "HSYNC", "GND", "VSYNC",
  "GND", "/IRQ", "/FIRQ", "/NMI", "GND",
  "AUDIO_L", "AGND", "AUDIO_R", "AGND", "+5V",
] as const

const kindOf = (signal: string): PinKind => {
  if (signal === "KEY") return "key"
  if (signal === "SPARE") return "spare"
  if (signal === "+5V") return "power"
  if (signal === "GND" || signal === "AGND") return "ground"
  return "signal"
}

const buildRow = (row: "A" | "B", signals: readonly string[]): SlotPin[] =>
  signals.map((signal, i) => ({
    ref: `${row}${i + 1}`,
    row,
    position: i + 1,
    signal,
    kind: kindOf(signal),
  }))

export const SLOT_PINS: SlotPin[] = [...buildRow("A", ROW_A), ...buildRow("B", ROW_B)]

export const SLOT_PIN_COUNT = SLOT_PINS.length

/** Pins that actually get a contact - everything but the two key positions. */
export const CONTACT_PINS = SLOT_PINS.filter((p) => p.kind !== "key")

/* Open-drain lines. Their pull-ups live on the motherboard, 3.3k, because four
 * cards declare open-drain outputs and no card document placed the resistors -
 * docs/machine.md 2.1. */
export const OPEN_DRAIN = ["/IRQ", "/FIRQ", "/WAIT", "/NMI", "/IOPAGE"] as const

/** Carried per slot rather than bussed. Everything else is common to all slots. */
export const GEOGRAPHIC = ["/IOSEL"] as const

/** tscircuit pin labels: numeric pin index -> its slot reference. Pin 1 is A1,
 * pin 37 is B1. Labels are unique so a selector never resolves to two pins;
 * the signal a pin carries is applied separately, by slotConnections(). */
export const slotPinLabels = (): Record<string, string> => {
  const labels: Record<string, string> = {}
  SLOT_PINS.forEach((p, i) => {
    labels[`pin${i + 1}`] = p.ref
  })
  return labels
}

/** ref -> net selector, for a <chip connections={...}>. Key and spare positions
 * are omitted; pass them through noConnect instead.
 *
 * ioselNet lets each slot's geographic /IOSEL land on its own net while every
 * other signal stays bussed. */
export const slotConnections = (
  ioselNet = "net.nIOSEL",
): Record<string, string> => {
  const conns: Record<string, string> = {}
  for (const p of SLOT_PINS) {
    if (p.kind === "key" || p.kind === "spare") continue
    conns[p.ref] = p.signal === "/IOSEL" ? ioselNet : `net.${sanitize(p.signal)}`
  }
  return conns
}

/** The key and spare positions, for noConnect. */
export const slotNoConnect = (): string[] =>
  SLOT_PINS.filter((p) => p.kind === "key" || p.kind === "spare").map((p) => p.ref)

/** Net name for a pin, made safe for a tscircuit selector (no / or +). */
export const netNameFor = (p: SlotPin): string => sanitize(p.signal)

export const sanitize = (signal: string): string =>
  signal
    .replace(/^\//, "n")     // /IRQ  -> nIRQ
    .replace(/^\+5V$/, "V5") // +5V   -> V5
    .replace(/\//g, "_")     // R/W   -> R_W
