/* Microstate cost probe, TUNED variant.  cpu/docs/plan.md §3.3(d).
 *
 * microstates.c measures straightforward C with the §4.1 struct-of-function-
 * pointers shape.  It does not fit: ms_adda (31 cy) + ms_sample_ctrl (27 cy)
 * is 58 cycles before any dispatch, against a 34-cycle budget at 3 MHz.
 *
 * This file measures the same semantics after three changes, each of which
 * attacks a specific line item visible in the naive disassembly.
 *
 * 1. HOT STATE LIVES IN REGISTERS.
 *    Naive ms_adda spends 5 of its 28 instructions on ldrb/strb of a, dbus and
 *    cc.  The bus loop is hand-written assembly running from CCM for the whole
 *    run (§3.4(1)), so A, B, CC, the cpu pointer and the GPIO bases can simply
 *    stay in callee-saved registers.  Modelled here by passing them in and
 *    returning them -- the compiler then keeps them in registers exactly as a
 *    pinned loop would.
 *
 * 2. LAZY CONDITION CODES.
 *    The dominant cost is not the ADD, it is materialising H/N/Z/V/C -- about
 *    18 of the 28 instructions, because the 6809 half-carry and overflow have
 *    no ARM equivalent and must be shifted and masked into place by hand.
 *    But CC is only *read* by a handful of instructions (TFR, PSHS, ANDCC,
 *    ORCC, and the interrupt sequences).  So keep the operands and result, and
 *    materialise CC on demand.  The per-cycle ALU cost collapses; the cost
 *    moves to cc_materialise(), which is paid rarely.
 *
 *    This is a real accuracy obligation, not a free lunch: every path that can
 *    observe CC must go through cc_materialise() -- including the interrupt
 *    stacking sequence, which stacks CC.  Getting that wrong is a correctness
 *    bug, not a performance one.
 *
 * 3. ACCUMULATE CONTROL LINES RAW; DECODE AT THE SAMPLING POINT.
 *    Naive ms_sample_ctrl costs 27 cycles EVERY bus cycle to do edge detection
 *    and CC.I/CC.F masking.  None of that is needed per cycle -- the
 *    architectural question ("is an interrupt taken?") is asked only at
 *    instruction boundaries.  Per cycle we only need to not MISS an assertion,
 *    which is an OR.  Decode moves to the boundary, where there is slack.
 */

#include "cpu.h"

#ifndef PROBE_NOINLINE
#define PROBE_NOINLINE __attribute__((noinline))
#endif

/* Packed hot state, standing in for pinned registers.
 * In the real loop these never touch memory. */
typedef struct {
    uint32_t a;          /* accumulator A                              */
    uint32_t alu_a;      /* lazy CC: left operand of the last ALU op   */
    uint32_t alu_m;      /* lazy CC: right operand                     */
    uint32_t alu_r;      /* lazy CC: raw result, carry still in bit 8  */
    uint32_t ctrl_acc;   /* accumulated asserted control lines         */
} hot_t;

/* ------------------------------------------------- per-cycle, tuned -- */

/* A = A + dbus, lazy CC.  Compare ms_adda: same semantics, deferred flags. */
PROBE_NOINLINE hot_t cyc_adda_tuned(hot_t h, uint32_t dbus)
{
    h.alu_a = h.a;
    h.alu_m = dbus;
    h.alu_r = h.a + dbus;
    h.a     = h.alu_r & 0xFFu;
    return h;
}

/* Control-line sampling, tuned.  gpioc is read once; /HALT arrives free in
 * gpioa (PA12), which is the same word the data bus came from (§3.2).
 * Active low, so inverting once makes "asserted" a set bit and the accumulate
 * is a single OR.  No masking, no edge detection -- both move to the
 * instruction boundary, below. */
PROBE_NOINLINE uint32_t cyc_sample_ctrl_tuned(uint32_t acc, uint32_t gpioa,
                                              uint32_t gpioc)
{
    return acc | ((~gpioc >> 13) & 7u) | ((~gpioa >> 9) & 8u);
}

/* One complete bus cycle, tuned shape, nothing inlined away:
 * ALU step + control sampling + next-state index.  This is the number that
 * has to fit in ~34 cycles at 3 MHz / ~48 at 1.79 MHz. */
PROBE_NOINLINE hot_t cyc_full_adda_tuned(hot_t h, uint32_t gpioa,
                                         uint32_t gpioc, uint32_t dbus)
{
    h.alu_a  = h.a;
    h.alu_m  = dbus;
    h.alu_r  = h.a + dbus;
    h.a      = h.alu_r & 0xFFu;
    h.ctrl_acc = h.ctrl_acc | ((~gpioc >> 13) & 7u) | ((~gpioa >> 9) & 8u);
    return h;
}

/* Indexed post-increment, tuned: X/Y/U/S genuinely live in memory (there are
 * too many to pin), so this keeps its two accesses.  Nothing to remove. */
PROBE_NOINLINE uint32_t cyc_idx_postinc_tuned(cpu_t *c, uint32_t pb)
{
    uint16_t *r = &c->x + ((pb >> 5) & 3u);
    uint32_t  v = *r;

    *r = (uint16_t)(v + 1u + (pb & 1u));
    return v;
}

/* ------------------------------------------- paid rarely, not per cycle -- */

/* Materialise CC from the lazy ALU state.  Called only when an instruction can
 * observe CC.  This is the cost that item 2 above moved OUT of the hot path --
 * measured here so the trade is visible rather than assumed. */
PROBE_NOINLINE uint32_t cc_materialise(uint32_t cc, uint32_t a, uint32_t m,
                                       uint32_t r)
{
    uint32_t x = a ^ m ^ r;

    cc &= (uint32_t)~(CC_H | CC_N | CC_Z | CC_V | CC_C);
    cc |= (r >> 8) & CC_C;
    cc |= (((a ^ r) & (m ^ r)) >> 6) & CC_V;
    cc |= (uint32_t)((r & 0xFFu) == 0u) << 2;
    cc |= (r >> 4) & CC_N;
    cc |= (x << 1) & CC_H;
    return cc;
}

/* Decode accumulated control lines at an instruction boundary: NMI edge,
 * IRQ/FIRQ masked by CC.I/CC.F, HALT.  Also paid rarely. */
PROBE_NOINLINE uint32_t ctrl_decode(uint32_t acc, uint32_t prev, uint32_t cc)
{
    uint32_t pend = 0u;

    pend |= (acc & ~prev & 1u) * P_NMI;
    pend |= ((acc >> 1) & ~(cc >> 4) & 1u) * P_IRQ;
    pend |= ((acc >> 2) & ~(cc >> 6) & 1u) * P_FIRQ;
    pend |= (acc & 8u) ? P_HALT : 0u;
    return pend;
}
