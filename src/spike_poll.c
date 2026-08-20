/* Phase 1 timing spike, variant 1: polling loop in C.  docs/plan.md §5.
 *
 * Lives in CCM SRAM (zero-wait, I-bus). Flash is 4 wait states at 170 MHz and
 * would make the measurement meaningless.
 *
 * Call with interrupts disabled. Any ISR taken mid-loop lands directly in the
 * measured latency.
 */

#include "stm32g431.h"
#include "pinout.h"
#include "spike.h"

extern uint32_t stub_next_addr[256];

#define DSB() __asm__ volatile("dsb 0xF" ::: "memory")

/* Histogram in CCM so the update does not stall on flash or SRAM contention. */
static __ccmbss uint32_t s_hist[SPIKE_HIST_BINS];

__hot void spike_run_poll(uint32_t n_cycles, spike_result_t *out)
{
    uint32_t misses = 0, overruns = 0;
    uint16_t lat_worst = 0, lat_best = 0xFFFFU;
    uint16_t per_min = 0xFFFFU, per_max = 0;
    uint64_t lat_sum = 0;

    for (uint32_t i = 0; i < SPIKE_HIST_BINS; i++) {
        s_hist[i] = 0;
    }

    uint32_t s_prev = GPIOA->IDR;
    uint32_t s_cur  = s_prev;

    /* Drop any stale capture / overcapture state, then sync to a falling edge
     * of E so the first measured cycle is a whole one. */
    (void)TIM1->CCR1;
    TIM1->SR = 0;
    while (!(GPIOA->IDR & MASK_E)) { }
    while (GPIOA->IDR & MASK_E) { }
    uint16_t t_edge_prev = (uint16_t)TIM1->CCR1;

    for (uint32_t i = 0; i < n_cycles; i++) {
        /* Wait out the E-low half of the cycle. */
        while (!(GPIOA->IDR & MASK_E)) { }

        /* E is high. Sample continuously, keeping the previous sample.
         *
         * When this loop exits, s_cur is the read that saw E low — taken
         * 0..1 iterations AFTER the edge, i.e. possibly past the guaranteed
         * data hold window. s_prev is the read before it, taken while E was
         * still high, inside the setup window. s_prev is therefore the
         * defensible sample. See README, "The data sampling problem" — this
         * is an assumption the spike is meant to test, not a settled fact. */
        do { s_prev = s_cur; s_cur = GPIOA->IDR; } while (s_cur & MASK_E);

        /* ==================== critical path begins ==================== */
        GPIOB->ODR = stub_next_addr[s_prev & MASK_DATA];
        DSB();                       /* ensure the store has actually landed */
        uint16_t t_done = (uint16_t)TIM1->CNT;
        /* ===================== critical path ends ===================== */

        /* t_edge is the HARDWARE timestamp of the E falling edge, so lat
         * includes polling jitter — the term §3.3 expects to dominate. */
        uint16_t t_edge = (uint16_t)TIM1->CCR1;
        uint16_t lat    = (uint16_t)(t_done - t_edge);
        uint16_t period = (uint16_t)(t_edge - t_edge_prev);
        t_edge_prev = t_edge;

        /* Overcapture means a second E fall arrived before we read CCR1:
         * a whole bus cycle went by unserviced. */
        if (TIM1->SR & TIM_SR_CC1OF) {
            overruns++;
            TIM1->SR = ~(uint32_t)TIM_SR_CC1OF;
        }

        /* The deadline is a quarter period, recomputed every cycle so a live
         * 0.895 <-> 1.79 MHz switch (docs/plan.md §2.1) is handled without
         * any calibration. */
        if (lat > (uint16_t)(period >> 2)) {
            misses++;
        }

        if (lat > lat_worst) lat_worst = lat;
        if (lat < lat_best)  lat_best  = lat;
        lat_sum += lat;
        if (period < per_min) per_min = period;
        if (period > per_max) per_max = period;

        s_hist[lat < SPIKE_HIST_BINS ? lat : SPIKE_HIST_BINS - 1U]++;
    }

    out->cycles_run      = n_cycles;
    out->deadline_misses = misses;
    out->overruns        = overruns;
    out->lat_worst       = lat_worst;
    out->lat_best        = lat_best;
    out->lat_sum         = lat_sum;
    out->period_min      = per_min;
    out->period_max      = per_max;
    for (uint32_t i = 0; i < SPIKE_HIST_BINS; i++) {
        out->hist[i] = s_hist[i];
    }
}

/* Map how long the data bus stays valid after E falls.
 *
 * Reference sample is taken mid-E-high, where data is valid on any sane host.
 * We then wait a fixed number of core cycles past the E fall and re-sample; if
 * the data byte still matches, the bus was still holding at that offset.
 *
 * The result tells you whether the s_prev trick above is even necessary, and
 * how much room a hardware-triggered (DMA) sample would have. */
__hot void spike_characterise_data_window(uint32_t n_cycles,
                                          uint32_t out_stable[SPIKE_HIST_BINS])
{
    for (uint32_t k = 0; k < SPIKE_HIST_BINS; k++) {
        uint32_t stable = 0;

        for (uint32_t i = 0; i < n_cycles; i++) {
            /* Wait for E to rise, then take the reference mid-phase. */
            while (!(GPIOA->IDR & MASK_E)) { }
            uint32_t ref = GPIOA->IDR & MASK_DATA;

            /* Wait for E to fall. */
            while (GPIOA->IDR & MASK_E) { }

            /* Burn k core cycles, then sample. The loop below is 3 cycles per
             * iteration on M4; the exact constant does not matter because the
             * offset axis is calibrated by the same TIM1 tick everywhere
             * else — but note the resolution is coarser than 1 cycle. */
            for (volatile uint32_t d = 0; d < k; d++) { }

            if ((GPIOA->IDR & MASK_DATA) == ref) {
                stable++;
            }
        }

        out_stable[k] = stable;
    }
}
