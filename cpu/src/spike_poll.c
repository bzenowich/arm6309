/* Phase 1 timing spike, variant 1: polling loop in C.  cpu/docs/plan.md §5.
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
    uint32_t misses = 0, holdviol = 0, overruns = 0;
    uint16_t lat_worst = 0, lat_best = 0xFFFFU;
    uint16_t per_min = 0xFFFFU, per_max = 0;
    uint64_t lat_sum = 0;

    for (uint32_t i = 0; i < SPIKE_HIST_BINS; i++) {
        s_hist[i] = 0;
    }

    uint32_t s_prev = GPIOA->IDR;
    uint32_t s_cur  = s_prev;
    uint16_t slack_min = 0xFFFFU;
    uint32_t slack_late = 0;

    /* Drop any stale capture / overcapture state, then sync to a falling edge
     * of E so the first measured cycle is a whole one. */
    (void)TIM1->CCR1;
    (void)TIM1->CCR2;
    TIM1->SR = 0;
    while (!(GPIOA->IDR & MASK_E)) { }
    while (GPIOA->IDR & MASK_E) { }
    uint16_t t_edge_prev = (uint16_t)TIM1->CCR1;
    TIM1->SR = ~(uint32_t)TIM_SR_CC2IF;   /* arm the first Q-fall wait */

    for (uint32_t i = 0; i < n_cycles; i++) {
        /* ---- Wait for Q to fall, not for E to rise. ----
         *
         * Q falls at 0.75 of the bus cycle and E at 1.0, so a Q-fall capture
         * means "one quarter period to the edge". Everything before this point
         * -- the bookkeeping at the bottom of the previous iteration, and in
         * the real core the microcode step -- ran in that freed 0.75.
         *
         * The earlier structure spun on the E pin for the whole E-high phase
         * (41 core cycles at 1.79 MHz) and none of it was usable. Waiting on
         * the capture FLAG instead means work happens first and the spin only
         * absorbs whatever is left over.
         *
         * Anchoring on a real hardware event rather than a predicted time is
         * what makes this safe across the live 0.895 <-> 1.79 MHz switch
         * (cpu/docs/plan.md §2.1): if the clock speeds up, Q simply falls sooner
         * and the flag is already set. */
        uint32_t late = (TIM1->SR & TIM_SR_CC2IF) ? 1U : 0U;
        uint16_t t_work_done = (uint16_t)TIM1->CNT;
        while (!(TIM1->SR & TIM_SR_CC2IF)) { }

        if (late) {
            /* Work overran the budget: Q had already fallen before we looked,
             * so the sampling window was entered late. */
            slack_late++;
        } else {
            uint16_t slack = (uint16_t)((uint16_t)TIM1->CCR2 - t_work_done);
            if (slack < slack_min) {
                slack_min = slack;
            }
        }

        /* E is guaranteed high here: it rises at 0.56 of the cycle and Q falls
         * at 0.75. No separate wait-for-E-high is needed.
         *
         * Sample continuously, keeping the previous value. On exit s_cur is
         * the read that saw E low -- 0..1 iterations after the edge, possibly
         * past the 10 ns hold -- while s_prev was taken while E was still
         * high, inside the 40 ns setup window. s_prev is the defensible one,
         * provided T_iter <= 6 core cycles (see spike.h). */
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

        /* Clear this cycle's Q-fall flag so the next iteration's wait sees
         * only the next one. Safe here: we are past E-fall, and the next Q
         * fall is three quarters of a cycle away. */
        TIM1->SR = ~(uint32_t)TIM_SR_CC2IF;

        /* Overcapture means a second E fall arrived before we read CCR1:
         * a whole bus cycle went by unserviced. */
        if (TIM1->SR & TIM_SR_CC1OF) {
            overruns++;
            TIM1->SR = ~(uint32_t)TIM_SR_CC1OF;
        }

        /* t_AD is an ABSOLUTE 110 ns, not a fraction of the E period, so the
         * deadline is the same constant at 0.895 and 1.79 MHz -- a live speed
         * switch (cpu/docs/plan.md §2.1) does not relax it. t_AH is the floor:
         * driving the new address too early violates the hold time on the
         * outgoing one. See spike.h for the datasheet references. */
        if (lat > SPIKE_TAD_CYCLES) {
            misses++;
        }
        if (lat < SPIKE_TAH_CYCLES) {
            holdviol++;
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
    out->hold_violations = holdviol;
    out->overruns        = overruns;
    out->lat_worst       = lat_worst;
    out->lat_best        = lat_best;
    out->lat_sum         = lat_sum;
    /* Approximates the polling loop iteration period. Must be <= 6 core cycles
     * (t_DSR = 40 ns at 170 MHz) or the s_prev sample is not provably inside
     * the 6809E read-data window -- see spike.h. */
    out->lat_jitter      = (uint16_t)(lat_worst - lat_best);
    out->period_min      = per_min;
    out->period_max      = per_max;
    out->slack_min       = slack_min;
    out->slack_late      = slack_late;
    for (uint32_t i = 0; i < SPIKE_HIST_BINS; i++) {
        out->hist[i] = s_hist[i];
    }
}

/* ------------------------------------------------------------ variant 2 -- */
/* Wrapper around the hand-written assembly loop in spike_poll_asm.S.
 *
 * The assembly keeps only what it must maintain per bus cycle -- the latency
 * histogram, the overcapture count and the E period range. Everything else is
 * derivable from the histogram, so it is computed here where it is legible
 * rather than in assembly where it would cost slack cycles and clarity. */

#if defined(__arm__)

uint32_t spike_run_poll_asm_raw(uint32_t n_cycles,
                                uint32_t *hist,
                                uint16_t *period_out);

static __ccmbss uint32_t s_hist_asm[SPIKE_HIST_BINS];

void spike_run_poll_asm(uint32_t n_cycles, spike_result_t *out)
{
    uint16_t period[2] = { 0xFFFFU, 0U };

    for (uint32_t i = 0; i < SPIKE_HIST_BINS; i++) {
        s_hist_asm[i] = 0;
    }

    out->overruns = spike_run_poll_asm_raw(n_cycles, s_hist_asm, period);

    out->cycles_run      = n_cycles;
    out->period_min      = period[0];
    out->period_max      = period[1];
    out->deadline_misses = 0;
    out->hold_violations = 0;
    out->lat_sum         = 0;
    out->lat_best        = 0xFFFFU;
    out->lat_worst       = 0;

    for (uint32_t bin = 0; bin < SPIKE_HIST_BINS; bin++) {
        uint32_t n = s_hist_asm[bin];
        out->hist[bin] = n;
        if (n == 0U) {
            continue;
        }
        if (bin > SPIKE_TAD_CYCLES) out->deadline_misses += n;
        if (bin < SPIKE_TAH_CYCLES) out->hold_violations += n;
        out->lat_sum += (uint64_t)n * bin;
        if (bin < out->lat_best)  out->lat_best  = (uint16_t)bin;
        if (bin > out->lat_worst) out->lat_worst = (uint16_t)bin;
    }

    /* The top bin saturates, so a non-zero count there means "at least 63",
     * not exactly 63. That is far past any deadline, so it is a failure
     * either way -- but do not read lat_worst as exact in that case. */
    out->lat_jitter = (uint16_t)(out->lat_worst - out->lat_best);
}

#endif /* __arm__ */

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
