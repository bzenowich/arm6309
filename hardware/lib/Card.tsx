/* The common shape of an arm6309 peripheral card.
 *
 * 100 x 160 mm Eurocard, because that is what video/docs/graphics.md 14 and
 * audio/docs/audio.md 12 both already assume, with the 2 x 36 fingers of
 * lib/slot.ts along the front edge.
 *
 * Every card takes /RESET as an input. io/ps2/docs/ps2.md did not until the
 * 2026-09-04 review (design-review.md IO-P3); nothing new should repeat that,
 * so the scaffold wires it rather than leaving it to each card.
 */
import type { ReactNode } from "react"
import { CardEdge } from "./SlotConnector"

export const EUROCARD = { width: "100mm", height: "160mm" } as const

export interface CardProps {
  name: string
  /** First byte of the card's window in $FF40-$FF7F. */
  ioBase: number
  /** Window size in bytes. */
  ioSize: number
  /** IC count the card's own document claims, for the budget check. */
  icBudget: number
  children?: ReactNode
}

export const Card = ({ name, children }: CardProps) => (
  <board name={name} {...EUROCARD} routingDisabled>
    {/* J1 is the edge, always. Its pinout is lib/slot.ts and nothing else. */}
    <CardEdge name="J1" pcbY={-76} />
    {children}
  </board>
)
