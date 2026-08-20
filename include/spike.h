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

typedef struct {
    uint32_t cycles_run;      /* bus cycles observed                          */
    uint32_t deadline_misses; /* latency > quarter period                     */
    uint32_t overruns;        /* TIM1 overcapture: a whole E cycle was missed */

    uint16_t lat_worst;       /* core cycles, E-fall (hardware) -> addr stored */
    uint16_t lat_best;
    uint64_t lat_sum;         /* for the mean                                 */

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
