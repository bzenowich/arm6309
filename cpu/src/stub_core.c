/* Stub state machine for the Phase 1 spike.
 *
 * This is NOT a 6309. It exists to reproduce the one structural property that
 * sets the timing ceiling: the address driven in cycle N+1 depends on the data
 * byte read at the end of cycle N, so the lookup cannot be hoisted out of the
 * critical path or precomputed a cycle early.
 *
 * A real microcoded core (cpu/docs/plan.md §4.1) resolves the same dependency with
 * the same shape — an indexed load from a table in CCM SRAM — so the measured
 * latency here should track the real thing closely. The stub deliberately does
 * no ALU work: Phase 1 measures the floor, and Phase 6 re-measures with the
 * real core to confirm it did not blow the budget.
 *
 * uint32_t rather than uint16_t so the load is a single LDR with a scaled
 * register offset and needs no width conversion before the store to ODR.
 * 1 KB in CCM SRAM.
 */

#include <stdint.h>
#include "stm32g431.h"

__ccmdata uint32_t stub_next_addr[256];

/* Scrambled so nothing is constant-foldable and consecutive data bytes do not
 * produce consecutive addresses — a real program's address stream is not
 * sequential, and we do not want an accidentally cache- or bus-friendly
 * pattern flattering the measurement. */
void stub_core_init(void)
{
    uint32_t x = 0x6309U;

    for (uint32_t i = 0; i < 256U; i++) {
        /* xorshift, then fold the index in so the entry genuinely depends on
         * the data byte */
        x ^= x << 13; x ^= x >> 17; x ^= x << 5;
        stub_next_addr[i] = (x ^ (i * 0x9E37U)) & 0xFFFFU;
    }
}
