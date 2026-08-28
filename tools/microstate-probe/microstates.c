/* Microstate cost probe -- docs/plan.md §3.3(d), §8 (top risk).
 *
 * WHY THIS EXISTS
 * ---------------
 * Every budget in plan.md rests on "a microcode step is ~15-30 core cycles".
 * That number was an estimate for code that did not exist, and Phase 1 does not
 * measure it: stub_core.c deliberately does no ALU work.  With clocking settled
 * at 170 MHz (§3.4(4)) and sampling settled by the §3.6 latch, this estimate is
 * the ONLY remaining unknown between here and a 3 MHz answer.
 *
 * The budget being tested, from §3.3(d):
 *
 *      1.79 MHz  ~48 core cycles per bus cycle for the emulator
 *      3.00 MHz  ~34 core cycles per bus cycle (with the §3.6 latch)
 *
 * Those already exclude the ~13-cycle drive path and ~10 cycles of bookkeeping,
 * so what is measured here must fit inside them on its own.
 *
 * WHAT IS MEASURED
 * ----------------
 * The states chosen are the ones expected to be expensive, not the average
 * ones -- the gates in plan.md are worst-case, so an average is useless here.
 *
 *   ms_idx_postinc   indexed addressing with post-increment: the EA cycle
 *   ms_adda          8-bit ALU with full CC update, incl. the half-carry
 *   ms_addd          16-bit ALU with CC update
 *   ms_tfm_step      6309 TFM block-transfer byte step (§4.3 "the hard one")
 *   ms_sample_ctrl   per-cycle interrupt / HALT sampling -- paid EVERY cycle
 *
 * plus the two dispatch shapes, because dispatch is not free and the §4.1
 * struct-of-function-pointers design pays for it twice per bus cycle.
 *
 * All CC computation is branchless.  A conditional branch here would cost
 * 1 or 3 cycles depending on the data, which turns a worst-case budget into a
 * guess -- exactly what this exercise is trying to eliminate.
 */

#include "cpu.h"

#ifndef PROBE_NOINLINE
#define PROBE_NOINLINE __attribute__((noinline))
#endif

/* ------------------------------------------------------------------ EA -- */

/* Indexed, post-increment: ,R+ and ,R++
 * Postbyte bits 6-5 select X/Y/U/S; bit 0 selects the increment.
 * The contiguous X,Y,U,S layout (cpu.h) is what keeps this branchless. */
PROBE_NOINLINE void ms_idx_postinc(cpu_t *c)
{
    uint32_t  pb = c->postbyte;
    uint16_t *r  = &c->x + ((pb >> 5) & 3u);
    uint32_t  v  = *r;

    c->ea = (uint16_t)v;
    *r    = (uint16_t)(v + 1u + (pb & 1u));
}

/* ----------------------------------------------------------------- ALU -- */

/* A = A + dbus, full CC update (H N Z V C).
 * The half-carry is the awkward one: it is a carry out of bit 3, which no
 * ARM flag provides, so it has to be derived from the operand XOR. */
PROBE_NOINLINE void ms_adda(cpu_t *c)
{
    uint32_t a = c->a;
    uint32_t m = c->dbus;
    uint32_t r = a + m;
    uint32_t x = a ^ m ^ r;

    uint32_t cc = c->cc & (uint32_t)~(CC_H | CC_N | CC_Z | CC_V | CC_C);
    cc |= (r >> 8) & CC_C;                       /* bit 8  -> bit 0 */
    cc |= (((a ^ r) & (m ^ r)) >> 6) & CC_V;     /* bit 7  -> bit 1 */
    cc |= (uint32_t)((r & 0xFFu) == 0u) << 2;    /*        -> bit 2 */
    cc |= (r >> 4) & CC_N;                       /* bit 7  -> bit 3 */
    cc |= (x << 1) & CC_H;                       /* bit 4  -> bit 5 */

    c->a  = (uint8_t)r;
    c->cc = (uint8_t)cc;
}

/* D = D + operand, CC update (N Z V C -- no half-carry on 16-bit ops). */
PROBE_NOINLINE void ms_addd(cpu_t *c)
{
    uint32_t d = ((uint32_t)c->a << 8) | c->b;
    uint32_t m = c->ea;
    uint32_t r = d + m;

    uint32_t cc = c->cc & (uint32_t)~(CC_N | CC_Z | CC_V | CC_C);
    cc |= (r >> 16) & CC_C;                       /* bit 16 -> bit 0 */
    cc |= (((d ^ r) & (m ^ r)) >> 14) & CC_V;     /* bit 15 -> bit 1 */
    cc |= (uint32_t)((r & 0xFFFFu) == 0u) << 2;   /*        -> bit 2 */
    cc |= (r >> 12) & CC_N;                       /* bit 15 -> bit 3 */

    c->a  = (uint8_t)(r >> 8);
    c->b  = (uint8_t)r;
    c->cc = (uint8_t)cc;
}

/* TFM r0+,r1+ -- one byte per bus cycle, W counts down, interruptible.
 * Postbyte nibbles select the source and destination pointer registers. */
PROBE_NOINLINE void ms_tfm_step(cpu_t *c)
{
    uint32_t  pb  = c->postbyte;
    uint16_t *src = &c->x + ((pb >> 4) & 3u);
    uint16_t *dst = &c->x + (pb & 3u);
    uint32_t  w   = ((uint32_t)c->e << 8) | c->f;

    *src = (uint16_t)(*src + 1u);
    *dst = (uint16_t)(*dst + 1u);
    w    = (w - 1u) & 0xFFFFu;

    c->e = (uint8_t)(w >> 8);
    c->f = (uint8_t)w;
}

/* ------------------------------------------------- per-cycle overhead -- */

/* Interrupt and HALT sampling.  This is NOT optional and NOT per-instruction:
 * it happens on every bus cycle, so its cost is added to every state.
 *
 * /HALT is PA12, already present in `gpioa` -- the same word the data bus was
 * read from -- so it costs no extra load.  That is a direct payoff from the
 * §3.2 pin assignment.  /NMI, /IRQ, /FIRQ are on PC13-15 and need one load.
 *
 * /NMI is edge-triggered, so it needs the previous sample retained.  /IRQ and
 * /FIRQ are level-triggered and masked by CC.I / CC.F. */
PROBE_NOINLINE void ms_sample_ctrl(cpu_t *c, uint32_t gpioa)
{
    uint32_t ctrl = GPIOC_IDR;
    uint32_t prev = c->ctrl_prev;
    uint32_t cc   = c->cc;
    uint32_t pend = c->pending;

    /* Active low; invert once so 1 == asserted.  NMI,IRQ,FIRQ -> bits 0..2. */
    uint32_t now = (~ctrl >> 13) & 7u;

    pend |= (now & ~prev & 1u) * P_NMI;                  /* edge  */
    pend |= ((now >> 1) & ~(cc >> 4) & 1u) * P_IRQ;      /* level, CC.I  */
    pend |= ((now >> 2) & ~(cc >> 6) & 1u) * P_FIRQ;     /* level, CC.F  */
    pend |= ((~gpioa >> 12) & 1u) * P_HALT;              /* PA12, free   */

    c->ctrl_prev = (uint8_t)now;
    c->pending   = (uint8_t)pend;
}

/* ------------------------------------------------------------ dispatch -- */

/* Shape B -- the §4.1 design, verbatim: one indirect call for the address,
 * one for the action, then follow `next`. */
typedef struct microstate {
    uint16_t (*addr)(cpu_t *);
    void     (*action)(cpu_t *);
    const struct microstate *next;
    uint8_t rw;
} microstate_t;

extern const microstate_t *g_state;

PROBE_NOINLINE uint32_t dispatch_fnptr(cpu_t *c)
{
    const microstate_t *st = g_state;
    uint32_t addr = st->addr(c);

    st->action(c);
    g_state = st->next;

    return addr | ((uint32_t)st->rw << 16);
}

/* Shape C -- flat jump table, actions inlined, next state as a plain index.
 * Same semantics, no indirect calls, no per-state struct load. */
enum { MS_IDX_POSTINC, MS_ADDA, MS_ADDD, MS_TFM_STEP, MS_COUNT };

PROBE_NOINLINE uint32_t dispatch_switch(cpu_t *c, uint32_t op, uint32_t gpioa)
{
    switch (op) {
    case MS_IDX_POSTINC: ms_idx_postinc(c); break;
    case MS_ADDA:        ms_adda(c);        break;
    case MS_ADDD:        ms_addd(c);        break;
    default:             ms_tfm_step(c);    break;
    }
    ms_sample_ctrl(c, gpioa);
    return c->ea;
}
