/* Assign equations to macrocells by product-term count.
 *
 * A 22V10's macrocells hold 8, 10, 12, 14, 16, 16, 14, 12, 10, 8 terms across
 * pins 14..23 - a palindrome, not a constant. A counter's bits need a rising
 * staircase (a loadable bit i costs i + 3 product terms, a plain enabled one
 * i + 7), so for anything past about six bits BIT ORDER IS NOT PIN ORDER and
 * the only assignment that fits pairs the two sorted sequences.
 *
 * That was done by hand for vgen and vadr, and got vadr's top bit wrong the
 * first time - the assembler refused to place an 11-term equation in a 10-term
 * macrocell, which is the fitter doing its job but is a slow way to find out.
 * This does the pairing.
 *
 * It is not a placer in the layout sense and does not try to be clever about
 * anything else: widest equation to widest macrocell, and if that does not fit
 * no other ASSIGNMENT will either.
 *
 * That last word is the whole caveat, and the message this file used to print
 * did not have it - it said "this does not fit on this part at all", which is
 * a stronger claim than the pairing supports. Sorted pairing is optimal over
 * assignments of a fixed set of equations. It says nothing about whether the
 * equations themselves are as small as they could be, and jedec/twolevel.ts
 * found one that was not: the arbiter's SPNGRANT was written at sixteen terms
 * and needs six.
 */

import { OLMC } from "./gal22v10"

export interface Placeable {
  name: string
  terms: string[]
}

/** Returns name -> pin. Throws, naming the equation, when it cannot fit. */
export const place = (
  cells: Placeable[], pins: number[],
): Record<string, number> => {
  if (cells.length > pins.length) {
    throw new Error(`${cells.length} equations for ${pins.length} macrocells`)
  }
  const byNeed = [...cells].sort((a, b) => a.terms.length - b.terms.length)
  const byCapacity = [...pins].sort((a, b) => OLMC[a].terms - OLMC[b].terms)

  const out: Record<string, number> = {}
  byNeed.forEach((cell, i) => {
    const pin = byCapacity[i]
    if (cell.terms.length > OLMC[pin].terms) {
      throw new Error(
        `${cell.name} needs ${cell.terms.length} product terms; the widest ` +
        `macrocell still free holds ${OLMC[pin].terms}. Sorted pairing is ` +
        `optimal for a FIXED set of equations, so no other assignment of ` +
        `these helps - but minimising the equation or splitting it across a ` +
        `spare macrocell might. See jedec/twolevel.ts.`,
      )
    }
    out[cell.name] = pin
  })
  return out
}
