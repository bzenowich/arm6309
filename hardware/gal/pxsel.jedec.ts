import type { Design } from "./jedec/assemble"

/* ------------------------------------------------------------------------
 * pxsel - graphics.md 8.2's fetch-rank select, and HSCROLL[1:0]'s third copy.
 *
 * ** WHAT IT IS FOR. 19 item 28: at HSCROLL[1:0] = p, chip c must present
 * group s+1 when c < p and group s when c >= p - two fetch groups live at
 * once, out of one four-byte fetch per slot. The item costed the fix at
 * "+4 '574 and a per-chip 2:1 on 8 bits - ~+12 ICs".
 *
 * ** IT IS FOUR PACKAGES AND THIS ONE, BECAUSE THE SELECT IS STATIC PER LINE.
 * `c < p` does not vary within a line - HSCROLL is loaded at HLOAD and the
 * chip index is wiring - so the choice between the two ranks is not a mux, it
 * is an OUTPUT ENABLE. Rank A and rank B are '574s in series, both drive the
 * same eight-bit node into that chip's '153 input, and exactly one of them has
 * its /OE asserted for the whole line. 13.1 already runs the LUT's address bus
 * this way; the same trick, one bus over.
 *
 *   FBdata -> rank A ('574, clocked FCLKn) -> rank B ('574, clocked FCLKn)
 *                |                                |
 *                +---- OEA(c) ----+---- OEB(c) ---+---> '153 input c
 *
 * With the fetch lead of two slots (video.parts.ts TFETCH), rank A holds group
 * s+1 during slot s and rank B holds group s. So OEA(c) = (c < p):
 *
 *   OEA0 = p != 0        chip 0 takes the new group unless the scroll is zero
 *   OEA1 = p >= 2
 *   OEA2 = p == 3
 *   OEA3 = 0             c < p is impossible for c = 3 - chip 3 is always B
 *
 * !! OEA3 IS A CONSTANT AND IS NOT BUILT. Chip 3's rank A is still a physical
 * '574 because it is the pipeline stage feeding rank B; what it never needs is
 * an enable. Its /OE is strapped off and its /OE pin here would be a macrocell
 * driving a constant.
 *
 * ** WHY HSCROLL[1:0] IS HELD HERE AS WELL AS ON vctrl. vctrl holds it for
 * seqph's MUXSEL and is at 64 of 64 I/O, so it cannot export the two bits and
 * this part cannot import them. Two macrocells is cheaper than the pin that
 * does not exist. The two copies are written by the same two strobes in the
 * same dot, so they cannot diverge:
 *
 *   LDHS   the CPU's write to +$03, from rfa's decode, data on D1:D0
 *   LWHSL  10.3.2's list MOVE to +$03, from vaddr, data on PB1:PB0
 *
 * ** AND THAT IS WHAT MAKES PER-SCANLINE SMOOTH SCROLL WORK. Without LWHSL a
 * list would move HSCROLL[9:2] and leave the fine bits at whatever the CPU
 * last wrote - smooth or listed, not both. features.md 4.
 * ------------------------------------------------------------------------ */

const hold = (name: string, bit: number) => ({
  pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
  /* Two write ports, disjoint by construction: LDHS is a CPU register write
   * (regsel & !RW & E) and LWHSL is a granted VRAM slot. The hold term carries
   * both negations, which is the same shape scrollHolds uses on vaddr. */
  terms: [`LDHS & D${bit}`, `LWHSL & PB${bit}`, `${name} & !LDHS & !LWHSL`],
})

const cells = [
  hold("HS0", 0),
  hold("HS1", 1),
  /* OEA(c) = c < p, with p = HS1:HS0, and OEB(c) is the complement on the
   * same net. ⛔ ASSERTED LOW since 2026-09-11: each pin is a '574's /OE and
   * the board has no inverter (graphics.md 8.2). They were emitted active-high
   * under a comment that said "the board inverts", which swapped every rank -
   * a four-pixel error at every scroll but zero. pins.check.ts. */
  { pin: 0, name: "OEA0", assertedLow: true, s0: 0 as const, registered: false,
    terms: ["HS0", "HS1"] },                    /* p != 0            */
  { pin: 0, name: "OEA1", assertedLow: true, s0: 0 as const, registered: false,
    terms: ["HS1"] },                           /* p >= 2            */
  { pin: 0, name: "OEA2", assertedLow: true, s0: 0 as const, registered: false,
    terms: ["HS1 & HS0"] },                     /* p == 3            */
  /* The complements, so the board needs no inverter: a '574's /OE is active
   * low and both ranks sit on one net, so the pair must never both assert. */
  { pin: 0, name: "OEB0", assertedLow: true, s0: 0 as const, registered: false,
    terms: ["!HS1 & !HS0"] },
  { pin: 0, name: "OEB1", assertedLow: true, s0: 0 as const, registered: false,
    terms: ["!HS1"] },
  { pin: 0, name: "OEB2", assertedLow: true, s0: 0 as const, registered: false,
    terms: ["!HS1", "!HS0"] },
]

export const pxselDesign: Design = {
  name: "pxsel",
  partNo: "ARM6309-UV11",
  location: "video card - fetch-rank select (graphics.md 8.2)",
  signature: "A6309VP",
  supersededBy: "graphics.md 10.1.7 - absorbed into vsup, the third ATF1508AS, 2026-09-09",
  clockPin: 1,
  inputs: [
    { name: "RESET", pin: 2, activeLow: true },
    { name: "LDHS", pin: 3 },   /* rfa's decode of a CPU write to +$03      */
    { name: "LWHSL", pin: 4 },  /* vaddr's 10.3.2 MOVE-to-HSCROLL strobe    */
    { name: "D0", pin: 5 }, { name: "D1", pin: 6 },
    { name: "PB0", pin: 7 }, { name: "PB1", pin: 8 },
  ],
  /* Eight cells of ten. The two widest macrocells stay free, which is where a
   * per-chip rank select for a 14.2 two-chip framebuffer would go. */
  cells: cells.map((c, i) => ({ ...c, pin: [14, 15, 16, 17, 18, 19, 20, 21][i] })),
  spares: [22, 23],
  ar: "RESET",
}
