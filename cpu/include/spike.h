/* Phase 1 timing spike — measurement API.  See cpu/docs/plan.md §5.
 *
 * The question this answers: after the host drops E, how long does it actually
 * take us to get the next address onto the bus, worst case? The deadline is
 * t_AD = 110 ns = 18.7 core cycles at 170 MHz — an ABSOLUTE figure from the
 * HD6309E datasheet, identical at every E rate the part is clocked at.
 *
 *   > The quarter-cycle framing this header used to carry ("23.7 core cycles
 *   > at 1.79 MHz, 8.5 at 5 MHz") was RETIRED on 2026-08-27 and is recorded
 *   > here only so the old numbers are recognisable. The deadline is not a
 *   > fraction of the E period, and there is no 5 MHz speed grade. See
 *   > cpu/docs/plan.md §3.3, which corrects both.
 *
 * Measurement is anchored on TIM1 input capture of the E falling edge, NOT on
 * when software noticed it. That difference IS the polling jitter, which
 * cpu/docs/plan.md §3.3 estimates at 4-6 core cycles and expects to dominate the
 * budget at high E rates. Measuring from a software timestamp would hide
 * exactly the term we care about.
 *
 * WHAT THE MEASUREMENT DOES NOT COUNT, AND WHICH WAY IT LEANS
 *
 * The reported latency is biased OPTIMISTIC — it flatters us — by roughly 3-5
 * core cycles against the socket-referred figure. Three terms, all one-way:
 *
 *   1. TIM1's capture path resynchronises TI1 to the timer clock even with
 *      the input filter off (ICF=0), so CCR1 lands ~2-3 core cycles AFTER the
 *      physical edge. Every cycle of that lag subtracts from the measured
 *      latency.
 *   2. t_done is read after the store retires, which is not when the pin
 *      moves: pad slew at VERY_HIGH is ~3.3 ns (~0.6 cycles) more.
 *   3. Phase 1 has no buffers (cpu/tools/stimulus/README.md), so the '541
 *      propagation (~5 ns, ~0.9 cycles) on the way out and the inbound E
 *      buffer on the way in are both absent from the number and present in
 *      the product.
 *
 * The earlier claim that the DSB makes this "conservative" was wrong: the DSB
 * costs a couple of cycles in the safe direction, and the three terms above
 * cost more than that in the unsafe one. SPIKE_TAD_CYCLES below is tightened
 * to absorb the difference.
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
 * CHARACTERISTICS" table, 2 MHz column (reference/datasheets/MC6809E.pdf p.3). One TIM1 tick
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
/* The raw datasheet ceiling, for reference and for the plan's arithmetic. */
#define SPIKE_TAD_RAW_CYCLES 18U /* 110 ns / 5.882 = 18.7, rounded down       */

/* THE PASS GATE, and it is deliberately tighter than the raw ceiling.
 *
 * 18 would be the right number if the spike measured the pin. It measures a
 * capture register and a retired store instead, and the header comment above
 * itemises ~3-5 core cycles of one-way optimism in that: capture-path
 * synchronisation (2-3), pad slew (~0.6), and the buffer propagation Phase 1's
 * unbuffered bench rig does not have but the module will (~0.9 each way).
 *
 * 18 - 4 = 14. A run that reports 14 is a socket-referred 17-19 against a
 * ceiling of 18.7, which is the honest reading of "just passed". Passing at 18
 * would mean a real 21-23 and a module that misses the deadline on hardware
 * while the bench says it is fine.
 *
 * The alternative was to keep 18 and calibrate the synchroniser offset out
 * with a second capture channel. That is strictly better and it is recorded in
 * plan.md §5 as the thing to do once a spare timer input is jumpered to an
 * address line; until then the tighter gate is the safe default, because the
 * failure mode of a gate that is too tight is a rerun, and of one that is too
 * loose is a PCB. */
#define SPIKE_TAD_CYCLES  14U   /* pass gate: 18.7 ceiling minus uncounted terms */
#define SPIKE_TAH_CYCLES   4U   /*  20 ns floor,   rounded up  (conservative)    */
#define SPIKE_TDSR_CYCLES  6U   /*  40 ns, the polling-iteration bound            */

/* Sentinels for fields a given variant does not measure. Without them a
 * caller that reuses one spike_result_t across variants (main.c does) reads
 * the previous variant's numbers and believes them. */
#define SPIKE_SLACK_UNMEASURED 0xFFFFU
#define SPIKE_LATE_UNMEASURED  0xFFFFFFFFU

typedef struct {
    uint32_t cycles_run;      /* bus cycles observed                          */
    uint32_t deadline_misses; /* latency > SPIKE_TAD_CYCLES. MUST be 0.       */
    uint32_t hold_violations; /* latency < t_AH  (20 ns). MUST be 0.          */
    uint32_t overruns;        /* TIM1 overcapture: a whole E cycle was missed */
    uint32_t dma_timeouts;    /* variant 3: the address never appeared.       */
    uint32_t dma_errors;      /* variant 3: of those, how many were a DMA
                               * transfer error (TEIF). Non-zero means the
                               * channel configuration is wrong -- typically
                               * a source the DMA cannot reach. Zero errors
                               * with non-zero timeouts means the TRIGGER
                               * never arrived instead: wiring, a clock
                               * enable, or the request-line ID.             */

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

    /* Emulator budget, measured from E-fall to Q-fall (0.75 of the bus cycle).
     * The loops do their bookkeeping there and only then enter tight sampling,
     * so this is the room a real microcode step would have.
     *
     * slack_min  worst-case spare core cycles after bookkeeping finished.
     *            Size the microcode step against THIS, not against the period.
     * slack_late number of cycles where the work overran the budget and Q had
     *            already fallen. Must be 0. Non-zero means the emulator step
     *            does not fit and the sampling window was entered late.
     *
     * REPORTED BY VARIANT 1 ONLY. Variants 2 and 3 set both to
     * SPIKE_SLACK_UNMEASURED / SPIKE_LATE_UNMEASURED, and that is a real
     * limitation of variant 2, not a formatting detail: the assembly loop has
     * no overrun-of-slack detection at all. Its per-cycle bookkeeping is
     * ~35-40 cycles, which at 3 MHz (14.2 cycles from Q-fall to E-fall) can
     * finish AFTER Q has already fallen. It then enters the sampling window
     * late, and the cycle is folded into lat_worst with nothing to mark it.
     * Variant 1 counts exactly those cycles in slack_late. So: when variant 2
     * and variant 1 disagree at a high E rate, variant 1's slack_late is the
     * one that explains it, and variant 2's numbers at that rate are only
     * trustworthy while variant 1 reports slack_late = 0.
     *
     * Variant 1's bookkeeping is heavier, so its slack_min is a conservative
     * lower bound. */
    uint16_t slack_min;
    uint32_t slack_late;

    uint32_t hist[SPIKE_HIST_BINS];
} spike_result_t;

/* Variant 1 (cpu/docs/plan.md §5): polling loop written in C.
 * Baseline. Predicted ceiling ~2 MHz.
 * Call with interrupts disabled; any ISR taken mid-loop lands in the latency. */
void spike_run_poll(uint32_t n_cycles, spike_result_t *out);

/* Variant 2: the same loop hand-written in assembly (cpu/src/spike_poll_asm.S).
 *
 * Not merely an optimisation. The C loop needs a register copy to keep the
 * previous sample, which pushes its iteration to ~7 core cycles -- over the
 * 6.8-cycle t_DSR bound, making its data sampling unsound however good its
 * latency looks. The assembly unrolls by two and alternates destination
 * registers, which by instruction timing gives sample gaps of 4 and 6 cycles
 * -- a prediction the run is testing, not an established fact, since an AHB2
 * GPIO load can cost more than the 2 cycles the sequence is costed at. Variant
 * 1 is the baseline; this is the one expected to be correct.
 *
 * Same contract as spike_run_poll(). Call with interrupts disabled. */
void spike_run_poll_asm(uint32_t n_cycles, spike_result_t *out);

/* Variant 3: the address is driven by DMA on the E edge, with no CPU in the
 * drive path at all (cpu/src/spike_dma.c).
 *
 * IMPORTANT: this does NOT relax the sampling bound. DMA offloads the address
 * drive, not the data read -- a DMA read triggered by the E edge lands past
 * t_DHR, and one triggered by Q's fall lands before t_DSR. Variant 3 still
 * needs a polling loop for data, so T_iter <= 6 cycles still applies.
 *
 * It also requires the address to be known a full bus cycle ahead, which is
 * true for instruction fetch runs, VMA cycles and stack operations but never
 * for genuinely data-dependent cycles. So it measures a floor for part of the
 * workload, not a replacement for variant 2.
 *
 * Call spike_dma_init() once before spike_run_dma(). Check dma_timeouts AND
 * dma_errors in the result before trusting anything else -- they separate the
 * two failures that produce an identical timeout: a channel that bus-errored
 * (dma_errors non-zero: source address, channel config) from a trigger that
 * never arrived (dma_errors zero: wiring, clock enable, request-line ID). */
void spike_dma_init(void);
void spike_run_dma(uint32_t n_cycles, spike_result_t *out);

/* Characterise the host's actual data-bus valid window (see README, "The data
 * sampling problem"). Samples GPIOA->IDR at a sweep of fixed offsets either
 * side of the captured E-fall and records where the data byte is stable. The
 * datasheet guarantees only a narrow window; real hardware is usually far more
 * generous, and this measures which. */
void spike_characterise_data_window(uint32_t n_cycles,
                                    uint32_t out_stable[SPIKE_HIST_BINS]);

#endif /* ARM6309_SPIKE_H */
