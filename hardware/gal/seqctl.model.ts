/* The span writer, as a state machine rather than as product terms.
 *
 * FOUR modes, one handshake. The only things that differ between them are what
 * ends the span and whether every retired byte is written:
 *
 *   direct  (WMODE 00)  one byte - 3.1.1's posted write
 *   mask    (WMODE 01)  EIGHT bytes, because a cell is eight pixels wide.
 *                       SPANLEN is not consulted. At 8 x 8 the mask byte IS
 *                       the glyph row (6.1), so there is nothing to truncate
 *                       and nothing to configure.
 *   solid   (WMODE 10)  SPANLEN + 1 bytes, counted by the '161 pair
 *   sprite  (WMODE 11)  eight bytes like mask, but a ZERO mask bit ADVANCES
 *                       THE POINTER WITHOUT WRITING. features.md 8.4.
 *
 * WHAT SPRITE MODE COSTS THIS PART, AND WHAT IT COSTS THE CARD, ARE DIFFERENT
 * NUMBERS. Here it is one input and one output: the mask bit has to reach the
 * sequencer, and a gated write enable has to leave it. On the card the mask
 * bit is the '165 serialiser's serial output, which goes to the register
 * file's address bit 0 and NOWHERE ELSE - so bringing it in costs an input pin
 * on vctrl, which is at 64 of 64. features.md 8.4 carries that arithmetic and
 * what unblocks it.
 *
 * ⭐ THE POINTER STILL ADVANCES ON A TRANSPARENT PIXEL. That is the whole
 * mode: RETIRE is unchanged, so WPTR steps, the serialiser shifts and the
 * length counter counts exactly as they do in mask mode. Only the write is
 * suppressed. A mode that stalled the pointer would draw the sprite squashed.
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
  /** ⭐ One dot per fetch slot, at the end of 5.2.2's spare window. Without it
   *  a span retires four bytes a slot: 5.2.1's arbiter is pure combinational
   *  grant logic and carries no phase, so SPNGRANT is asserted for every dot
   *  the request is. 7.4's whole timing model is one byte per 158.9 ns.
   *  docs/design-review2.md V-4. */
  spntick?: boolean
  /* 19 item 24: the list engine owns WPTR while this is high, so WADV's row
   * advance is withheld - the engine's walk is a plain +1. Defaults to false,
   * which is "no list running" and every pre-2026-09-09 case. */
  lrun?: boolean
  /** the '161 pair's terminal count - span-solid only */
  tc: boolean
  /** WADV[1:0] */
  wadv: number
  /** the mask serialiser's current bit. Read ONLY by sprite mode - in mask
   *  mode it selects WFG or WBG through the register file's address, which
   *  costs no logic here at all (7.4). */
  maskbit: boolean
}

export const retiring = (s: SpanState, io: SpanIn) =>
  s.busy === 1 && io.spngrant && io.spntick !== false

export const ending = (s: SpanState, io: SpanIn) => {
  if (!retiring(s, io)) return false
  if (io.wmode === 0) return true                        // direct: one byte
  if (io.wmode === 1) return s.mc === CELL_PIXELS - 1    // mask: the cell width
  if (io.wmode === 2) return io.tc                       // solid: SPANLEN
  return s.mc === CELL_PIXELS - 1                        // sprite: the cell width
}

/** ⭐ The whole of sprite mode, in one line.
 *
 * Every other mode writes every byte it retires. Sprite mode retires the
 * transparent ones and does not write them - so the pointer, the serialiser
 * and the counter all advance and the framebuffer keeps what was underneath.
 * That is what deletes save-behind for a masked shape: nothing outside it is
 * touched, so there is nothing to put back. */
export const writing = (s: SpanState, io: SpanIn) =>
  retiring(s, io) && (io.wmode !== 3 || io.maskbit)

export const step = (s: SpanState, io: SpanIn): SpanState => ({
  busy: io.wstb ? 1 : s.busy === 1 && !ending(s, io) ? 1 : 0,
  mc: io.wstb ? 0 : retiring(s, io) ? (s.mc + 1) % 8 : s.mc,
})

export const outputs = (s: SpanState, io: SpanIn) => ({
  retire: retiring(s, io) ? 1 : 0,
  wen: writing(s, io) ? 1 : 0,
  spanend: ending(s, io) ? 1 : 0,
  wrowadv: ending(s, io) && io.wadv !== 0 && !io.lrun ? 1 : 0,
})
