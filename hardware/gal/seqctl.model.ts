/* The span writer, as a state machine rather than as product terms.
 *
 * Three modes, one handshake. The only thing that differs between the modes
 * is what ends the span:
 *
 *   direct  (WMODE 00)  one byte - 3.1.1's posted write
 *   mask    (WMODE 01)  EIGHT bytes, because a cell is eight pixels wide.
 *                       SPANLEN is not consulted. At 8 x 8 the mask byte IS
 *                       the glyph row (6.1), so there is nothing to truncate
 *                       and nothing to configure.
 *   solid   (WMODE 10)  SPANLEN + 1 bytes, counted by the '161 pair
 */

export const CELL_PIXELS = 8

export interface SpanState { busy: 0 | 1; mc: number }
export const IDLE: SpanState = { busy: 0, mc: 0 }

export interface SpanIn {
  /** a posted write has been latched at E-fall */
  wstb: boolean
  /** WMODE[1:0] as captured with it */
  wmode: number
  /** the arbiter gave the span writer a spare access this slot */
  spngrant: boolean
  /** the '161 pair's terminal count - span-solid only */
  tc: boolean
  /** WADV[1:0] */
  wadv: number
}

export const retiring = (s: SpanState, io: SpanIn) => s.busy === 1 && io.spngrant

export const ending = (s: SpanState, io: SpanIn) => {
  if (!retiring(s, io)) return false
  if (io.wmode === 0) return true                       // direct: one byte
  if (io.wmode === 1) return s.mc === CELL_PIXELS - 1    // mask: the cell width
  if (io.wmode === 2) return io.tc                       // solid: SPANLEN
  return false
}

export const step = (s: SpanState, io: SpanIn): SpanState => ({
  busy: io.wstb ? 1 : s.busy === 1 && !ending(s, io) ? 1 : 0,
  mc: io.wstb ? 0 : retiring(s, io) ? (s.mc + 1) % 8 : s.mc,
})

export const outputs = (s: SpanState, io: SpanIn) => ({
  retire: retiring(s, io) ? 1 : 0,
  spanend: ending(s, io) ? 1 : 0,
  wrowadv: ending(s, io) && io.wadv !== 0 ? 1 : 0,
})
