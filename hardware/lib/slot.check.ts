/* Arithmetic on the slot pinout. Run with `npm run check`.
 *
 * Nothing here is a style rule: each assertion is a claim docs/machine.md or
 * video/docs/graphics.md 17 makes about the backplane, restated so that an edit
 * to slot.ts that breaks one of them fails loudly instead of reaching a board.
 */
import { SLOT_PINS, SLOT_PIN_COUNT, CONTACT_PINS, OPEN_DRAIN } from "./slot"

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) {
    failures++
    console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`)
  } else {
    console.log(`ok    ${claim}`)
  }
}

/* -- the machine's own signal list, docs/machine.md 2 -------------------- */
const REQUIRED = [
  ...Array.from({ length: 20 }, (_, i) => `A${i}`), // A0..A19, physical
  ...Array.from({ length: 8 }, (_, i) => `D${i}`),
  "E", "Q", "R/W",
  "CLK25",
  "/IOSEL", "/IOPAGE", "/WAIT", "/IRQ", "/FIRQ", "/NMI", "/RESET", "/HALT",
  "HSYNC", "VSYNC",
  "AUDIO_L", "AUDIO_R",
]

const present = new Set(SLOT_PINS.map((p) => p.signal))
const missing = REQUIRED.filter((s) => !present.has(s))
check(missing.length === 0, "every signal in machine.md 2 has a pin", missing.join(", "))

const known = new Set([...REQUIRED, "GND", "AGND", "+5V", "KEY", "SPARE"])
const stray = [...present].filter((s) => !known.has(s))
check(stray.length === 0, "no pin carries a signal the machine does not define", stray.join(", "))

/* -- geometry ----------------------------------------------------------- */
check(SLOT_PIN_COUNT === 72, "72 positions, 2 x 36")
check(
  SLOT_PINS.filter((p) => p.row === "A").length === 36 &&
    SLOT_PINS.filter((p) => p.row === "B").length === 36,
  "both rows are 36 long",
)
const refs = SLOT_PINS.map((p) => p.ref)
check(new Set(refs).size === refs.length, "no duplicate pin reference")
check(
  36 * 2.54 <= 100,
  "the fingers fit a 100 mm Eurocard edge",
  `${(36 * 2.54).toFixed(1)} mm of 100 mm`,
)

/* -- one contact per signal, except the rails ---------------------------- */
const counts = new Map<string, number>()
for (const p of CONTACT_PINS) counts.set(p.signal, (counts.get(p.signal) ?? 0) + 1)
const duplicated = [...counts].filter(([s, n]) => n > 1 && !["GND", "AGND", "+5V", "SPARE"].includes(s))
check(duplicated.length === 0, "no signal is doubled up", duplicated.map(([s]) => s).join(", "))

/* -- power, against docs/machine.md 8 ------------------------------------ */
/* The video card is the worst case: ~1.1-1.7 A, design to 2 A (graphics.md 14).
 * A 0.1" gold finger on 1 oz copper is good for ~1 A conservatively. */
const FINGER_A = 1.0
const WORST_CARD_A = 2.0
const p5 = counts.get("+5V") ?? 0
check(
  p5 * FINGER_A >= WORST_CARD_A * 2,
  "+5V fingers carry the worst card with 2x margin",
  `${p5} fingers = ${(p5 * FINGER_A).toFixed(1)} A against ${WORST_CARD_A} A`,
)
const gnd = counts.get("GND") ?? 0
check(gnd >= p5, "at least as many grounds as power pins", `${gnd} GND, ${p5} +5V`)

/* -- graphics.md 17: ground returns adjacent to the clock and sync lines -- */
const byRow = (row: "A" | "B") =>
  SLOT_PINS.filter((p) => p.row === row).sort((a, b) => a.position - b.position)
const neighbours = (p: { row: "A" | "B"; position: number }) =>
  byRow(p.row).filter((q) => Math.abs(q.position - p.position) === 1)

for (const clk of ["CLK25", "E", "Q", "HSYNC", "VSYNC"]) {
  const pin = SLOT_PINS.find((p) => p.signal === clk)!
  const adjacentGnd = neighbours(pin).filter((n) => n.signal === "GND").length
  check(adjacentGnd >= 2, `${clk} has a ground on both sides`, `${adjacentGnd} of 2`)
}

/* The analogue pair gets its own returns, not the digital ground -
 * graphics.md 17: "two pins and two grounds". */
for (const audio of ["AUDIO_L", "AUDIO_R"]) {
  const pin = SLOT_PINS.find((p) => p.signal === audio)!
  check(
    neighbours(pin).some((n) => n.signal === "AGND"),
    `${audio} sits beside a dedicated return`,
  )
}

/* -- open-drain lines all reach the backplane ---------------------------- */
for (const line of OPEN_DRAIN) {
  check(present.has(line), `${line} is on the slot (its pull-up is on the motherboard)`)
}

console.log(
  `\n${SLOT_PIN_COUNT} positions: ` +
    [...new Set(SLOT_PINS.map((p) => p.kind))]
      .map((k) => `${SLOT_PINS.filter((p) => p.kind === k).length} ${k}`)
      .join(", "),
)
console.log(failures === 0 ? "\nslot pinout OK" : `\n${failures} failure(s)`)
process.exit(failures === 0 ? 0 : 1)
