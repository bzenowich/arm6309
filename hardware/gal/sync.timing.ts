/* The VGA timing the sync GALs implement, in one place.
 *
 * Both families are standard IBM/VESA timings at the 25.175 MHz dot clock, and
 * graphics.md 6.1 and 6.2 pick them: 800 x 449 at 70.09 Hz and 800 x 525 at
 * 60.0 Hz. They share the entire horizontal timing, which is why the H counter
 * has no mode input at all.
 *
 * TWO ORIGIN CHOICES ARE MADE HERE and they are not in graphics.md, because
 * nothing had needed to fix them before the equations were written. Both
 * counters start at the leading edge of their own sync pulse rather than at
 * the start of active video:
 *
 *   - the slot counter's sync window becomes h <= 23, which is two product
 *     terms instead of a window compare in the middle of the range;
 *   - the line counter's sync window becomes v <= 1 IN BOTH FAMILIES, which
 *     is ONE product term and, more importantly, the SAME term for both. A
 *     mid-range origin would have needed a mode-dependent window compare on
 *     the one output that graphics.md 6.2.1 already identifies as the
 *     tightest on the card.
 *
 * This is the conventional origin for a video timing generator and it is
 * chosen for the reason above, not by habit.
 *
 * The slot rate is the dot rate / 4 - one fetch slot per four pixels (6.1) -
 * so every horizontal boundary below is a multiple of four dots, which it is:
 * 96, 48, 640 and 16 are all divisible by 4.
 */

export const DOT_HZ = 25_175_000
export const DOTS_PER_SLOT = 4
export const SLOTS_PER_LINE = 200 // 800 dots

/** Horizontal, in slots, measured from the leading edge of HSYNC. */
export const H = {
  syncEnd: 23, //   0..23   96 dots of sync
  backEnd: 35, //  24..35   48 dots of back porch
  activeEnd: 195, // 36..195 640 dots of active video
  //                196..199  16 dots of front porch
  last: SLOTS_PER_LINE - 1,
} as const

/** Vertical, in lines, measured from the leading edge of VSYNC.
 *  VMODE[0] selects the family: 0 -> 449 lines, 1 -> 525. */
export interface VFamily {
  name: string
  lines: number
  syncEnd: number
  backEnd: number
  activeEnd: number
  /** what the monitor is told, and how: graphics.md 6.2.1 */
  vsyncPositive: boolean
}

export const V449: VFamily = {
  name: "800x449 @ 70.09 Hz (640x400 family)",
  lines: 449,
  syncEnd: 1, //     0..1     2 lines of sync
  backEnd: 36, //    2..36   35 lines of back porch
  activeEnd: 436, // 37..436 400 active lines
  //                 437..448 12 lines of front porch
  vsyncPositive: true,
}

export const V525: VFamily = {
  name: "800x525 @ 59.94 Hz (640x480 family)",
  lines: 525,
  syncEnd: 1, //     0..1     2 lines of sync
  backEnd: 34, //    2..34   33 lines of back porch
  activeEnd: 514, // 35..514 480 active lines
  //                 515..524 10 lines of front porch
  vsyncPositive: false,
}

export const family = (vmode0: 0 | 1): VFamily => (vmode0 ? V525 : V449)

/* The arithmetic that says these are the timings claimed, rather than
 * whatever was typed. */
{
  const check = (ok: boolean, what: string) => { if (!ok) throw new Error(what) }
  check(H.syncEnd + 1 === 96 / DOTS_PER_SLOT, "HSYNC is not 96 dots")
  check(H.backEnd - H.syncEnd === 48 / DOTS_PER_SLOT, "H back porch is not 48 dots")
  check(H.activeEnd - H.backEnd === 640 / DOTS_PER_SLOT, "H active is not 640 dots")
  check(H.last - H.activeEnd === 16 / DOTS_PER_SLOT, "H front porch is not 16 dots")
  for (const [f, active] of [[V449, 400], [V525, 480]] as const) {
    check(f.activeEnd - f.backEnd === active, `${f.name}: active lines`)
    check(f.syncEnd + 1 === 2, `${f.name}: sync width`)
    check(f.lines > f.activeEnd, `${f.name}: front porch`)
  }
  /* 70.09 Hz and 59.94 Hz.
   *
   * NOT 60.0. graphics.md 6.2's mode table says "60.0 Hz" for both 525-line
   * modes and 12.1 repeats it when it makes the VBL interrupt the system
   * tick. 25.175 MHz / 800 / 525 = 59.940 Hz - the standard VGA 640x480 rate,
   * which has never been 60. It is 0.1% and it matters in exactly one place:
   * a NitrOS-9 tick derived from vertical blank runs 0.1% slow, which is
   * about 86 seconds a day, so the tick divisor is not interchangeable
   * between the two mode families. */
  const rate = (f: VFamily) => DOT_HZ / (SLOTS_PER_LINE * DOTS_PER_SLOT) / f.lines
  check(Math.abs(rate(V449) - 70.086) < 0.01, `449 family is ${rate(V449).toFixed(3)} Hz`)
  check(Math.abs(rate(V525) - 59.940) < 0.01, `525 family is ${rate(V525).toFixed(3)} Hz`)
  /* 31.469 kHz line rate, shared - the thing that makes the two families
   * indistinguishable at the connector except by VSYNC polarity. */
  check(Math.abs(DOT_HZ / 800 - 31469) < 1, "line rate is not 31.469 kHz")
}
