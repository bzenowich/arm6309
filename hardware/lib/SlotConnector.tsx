/* The two ends of an arm6309 expansion slot, both generated from lib/slot.ts.
 *
 * SlotSocket  - motherboard side: the card-edge receptacle.
 * CardEdge    - card side: 2 x 36 gold fingers on the board's front edge.
 *
 * Because both read the same table, a card and the motherboard cannot disagree
 * about what A17 is.
 */
import {
  SLOT_PINS,
  SLOT_PIN_COUNT,
  slotPinLabels,
  slotConnections,
  slotNoConnect,
} from "./slot"

const PITCH_MM = 2.54
const FINGER_W = 1.6
const FINGER_H = 8.0

interface SlotProps {
  name: string
  /** Geographic /IOSEL net for this slot. Every other signal is bussed. */
  ioselNet?: string
  pcbX?: number
  pcbY?: number
  pcbRotation?: number
  schX?: number
  schY?: number
}

/* ---------------------------------------------------------------- socket -- */
/* A 72-way 0.1" card-edge receptacle. Footprinted as a DIP body for now: the
 * pad grid and pin numbering are right, the body outline is not. Swap for a
 * measured footprint once a receptacle is sourced - hardware/README.md, open
 * item 1. */
export const SlotSocket = ({ name, ioselNet, ...pos }: SlotProps) => (
  <connector
    {...pos}
    name={name}
    footprint={`dip${SLOT_PIN_COUNT}_w0.4in`}
    pinLabels={slotPinLabels()}
    connections={slotConnections(ioselNet)}
    noConnect={slotNoConnect()}
    schPinArrangement={{
      leftSide: {
        direction: "top-to-bottom",
        pins: SLOT_PINS.filter((p) => p.row === "A").map((p) => p.ref),
      },
      rightSide: {
        direction: "top-to-bottom",
        pins: SLOT_PINS.filter((p) => p.row === "B").map((p) => p.ref),
      },
    }}
  />
)

/* ------------------------------------------------------------ card edge -- */
/* Row A on the top copper, row B on the bottom, position 1 at the left looking
 * at the component side. The key at position 6 is a routed notch through the
 * board, so neither layer gets a finger there. */
const fingerX = (position: number) =>
  (position - (36 + 1) / 2) * PITCH_MM

export const CardEdge = ({ name, ioselNet, ...pos }: SlotProps) => (
  <connector
    {...pos}
    name={name}
    pinLabels={slotPinLabels()}
    connections={slotConnections(ioselNet)}
    noConnect={slotNoConnect()}
    schPinArrangement={{
      leftSide: {
        direction: "top-to-bottom",
        pins: SLOT_PINS.filter((p) => p.row === "A").map((p) => p.ref),
      },
      rightSide: {
        direction: "top-to-bottom",
        pins: SLOT_PINS.filter((p) => p.row === "B").map((p) => p.ref),
      },
    }}
  >
    <footprint>
      {SLOT_PINS.filter((p) => p.kind !== "key").map((p, _i) => (
        <smtpad
          key={p.ref}
          portHints={[p.ref, `pin${SLOT_PINS.indexOf(p) + 1}`]}
          pcbX={fingerX(p.position)}
          pcbY={0}
          width={FINGER_W}
          height={FINGER_H}
          shape="rect"
          layer={p.row === "A" ? "top" : "bottom"}
        />
      ))}
      {/* the polarising notch at position 6 */}
      <cutout
        shape="rect"
        pcbX={fingerX(6)}
        pcbY={0}
        width={2.0}
        height={FINGER_H}
      />
    </footprint>
  </connector>
)
