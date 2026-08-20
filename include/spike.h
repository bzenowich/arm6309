/* Phase 1 timing spike — measurement API.  See docs/plan.md §5.
 *
 * The question this answers: after the host drops E, how long does it actually
 * take us to get the next address onto the bus, worst case? The 6809E requires
 * that inside one quarter of an E period (23.7 core cycles at 1.79 MHz,
 * 8.5 at 5 MHz).
 *
 * Measurement is anchored on TIM1 input capture of the E falling edge, NOT on
 * when software noticed it. That difference IS the polling jitter, which
 * docs/plan.md §3.3 estimates at 4-6 core cycles and expects to dominate the
 * budget at high E rates. Measuring from a software timestamp would hide
 * exactly the term we care about.
 *
 * TIM1 runs at 170 MHz with no prescaler, so one tick == one core cycle.
 * It is 16-bit and wraps every ~385 us; all deltas use wraparound-safe
 * unsigned 16-bit subtraction. At 0.895 MHz an E period is ~1.1 us, so a wrap
 * between consecutive edges is impossible.
 */
#ifndef ARM6309_SPIKE_H
#define ARM6309_SPIKE_H

#include <stdint.h>

#define SPIKE_HIST_BINS 64U   /* latency histogram, 1 core cycle per bin */

/* MC68B09E bus timing, from the Motorola MC6809E datasheet "BUS TIMING
 * CHARACTERISTICS" table, 2 MHz column (docs/MC6809E.pdf p.3). One TIM1 tick
 * is one core cycle at 170 MHz, so ns -> ticks is ns / 5.882.
 *
 * These are ABSOLUTE times, not fractions of the E period. The CoCo 3 clocks a
 * 68B09E, so the same numbers apply at both 0.895 and 1.79 MHz — the deadline
 * does NOT relax when the machine drops to slow mode.
 *
 *   #11 t_AD  address delay from E low, MAX 110 ns  -> 18.7 cycles  (ceiling)
 *   #9  t_AH  address hold time,        MIN  20 ns  ->  3.4 cycles  (floor)
 *   #17 t_DSR read data setup,          MIN  40 ns  ->  6.8 cycles
 *   #18 t_DHR read data hold,           MIN  10 ns  ->  1.7 cycles
 *
 * So the next address must be driven in the window [3.4, 18.7] core cycles
 * after the E falling edge. Both ends are real: driving too EARLY violates the
 * hold time on the outgoing address. */
#define SPIKE_TAD_CYCLES  18U   /* 110 ns ceiling, rounded down (conservative) */
#define SPIKE_TAH_CYCLES   4U   /*  20 ns floor,   rounded up  (conservative) */
#define SPIKE_TDSR_CYCLES  6U   /*  40 ns, the polling-iteration bound         */

typedef struct {
    uint32_t cycles_run;      /* bus cycles observed                          */
    uint32_t deadline_misses; /* latency > t_AD (110 ns). MUST be 0.          */
    uint32_t hold_violations; /* latency < t_AH  (20 ns). MUST be 0.          */
    uint32_t overruns;        /* TIM1 overcapture: a whole E cycle was missed */

    uint16_t lat_worst;       /* core cycles, E-fall (hardware) -> addr stored */
    uint16_t lat_best;
    uint64_t lat_sum;         /* for the mean                                 */

    /* lat_worst - lat_best. The only variable term between cycles is WHERE in
     * the polling loop the E edge landed, so this approximates the loop
     * iteration period T_iter.
     *
     * CORRECTNESS GATE: T_iter must be <= t_DSR = 40 ns = 6 core cycles at
     * 170 MHz. The s_prev sample is taken at most one iteration before E fell,
     * so it lands in [E_fall - T_iter, E_fall). The 6809E guarantees read data
     * valid over [E_fall - 40 ns, E_fall + 10 ns]. T_iter <= 40 ns therefore
     * PROVES s_prev is inside the valid window; above it, sampling is
     * unsound no matter how good the latency looks. See README. */
    uint16_t lat_jitter;

    uint16_t period_min;      /* observed E period, core cycles               */
    uint16_t period_max;      /* min != max means the host switched speed     */

    uint32_t hist[SPIKE_HIST_BINS];
} spike_result_t;

/* Variant 1 (docs/plan.md §5): polling loop written in C.
 * Baseline. Predicted ceiling ~2 MHz.
 * Call with interrupts disabled; any ISR taken mid-loop lands in the latency. */
void spike_run_poll(uint32_t n_cycles, spike_result_t *out);

/* Variant 2: same loop hand-written in assembly. Predicted ~2.5 MHz.
 * TODO(phase1): implement once variant 1 has a measured baseline to beat. */

/* Variant 3: EXTI + DMAMUX + DMA store of a precomputed address, removing
 * polling jitter from cycles whose address does not depend on the preceding
 * read. Predicted ~3-3.5 MHz.
 * TODO(phase1): implement after variants 1-2. */

/* Characterise the host's actual data-bus valid window (see README, "The data
 * sampling problem"). Samples GPIOA->IDR at a sweep of fixed offsets either
 * side of the captured E-fall and records where the data byte is stable. The
 * datasheet guarantees only a narrow window; real hardware is usually far more
 * generous, and this measures which. */
void spike_characterise_data_window(uint32_t n_cycles,
                                    uint32_t out_stable[SPIKE_HIST_BINS]);

#endif /* ARM6309_SPIKE_H */
