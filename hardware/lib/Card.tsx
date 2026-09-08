/* The common shape of an arm6309 peripheral card.
 *
 * 100 mm high and 120, 180 or 240 mm long - Apple II proportions, with the
 * 2 x 36 fingers of lib/slot.ts along the bottom rear edge and the card's
 * connectors on the back.
 *
 * ⚠ THIS WAS A 100 x 160 mm EUROCARD until 2026-09-08, "because that is what
 * video/docs/graphics.md 14 and audio/docs/audio.md 12 both already assume".
 * Drawing the boards is what settled it: place/place.check.ts shows the video
 * card at 134.4 cm2 of courtyard against a Eurocard's 133.4 cm2 of placeable
 * area - over budget before a single routing channel. Three of the five cards
 * then turned out to fit 12 cm, so the length is per-card rather than one
 * format for all.
 *
 * The video card came back to 18 cm later the same day: graphics.md 14.2
 * consolidated seven SRAMs into four, and 101.5 cm2 fits a 15.0 cm2-per-cm
 * board with room to route. Nothing takes 24 cm any more, and the length stays
 * in LENGTHS because the packer, not this comment, decides.
 *
 * Every card takes /RESET as an input. io/ps2/docs/ps2.md did not until the
 * 2026-09-04 review (design-review.md IO-P3); nothing new should repeat that,
 * so the scaffold wires it rather than leaving it to each card.
 */
import type { ReactNode } from "react"
import { CardEdge } from "./SlotConnector"

/** The three lengths a card may take. place/parts.ts is the other half of
 *  this rule and place.check.ts asserts each card takes the shortest. */
export const LENGTHS = [120, 180, 240] as const
export type CardLength = (typeof LENGTHS)[number]
export const CARD_HEIGHT_MM = 100

export interface CardProps {
  name: string
  /** First byte of the card's window in $FF40-$FF7F. */
  ioBase: number
  /** Window size in bytes. */
  ioSize: number
  /** IC count the card's own document claims, for the budget check. */
  icBudget: number
  /** Board length in mm - the shortest of LENGTHS that holds the parts. */
  length: CardLength
  children?: ReactNode
}

export const Card = ({ name, length, children }: CardProps) => (
  <board name={name} width={`${length}mm`} height={`${CARD_HEIGHT_MM}mm`} routingDisabled>
    {/* J1 is the edge, always. Its pinout is lib/slot.ts and nothing else. */}
    <CardEdge name="J1" pcbY={-CARD_HEIGHT_MM / 2 + 6} />
    {children}
  </board>
)
