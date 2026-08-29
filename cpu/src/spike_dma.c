/* Phase 1 timing spike, variant 3: hardware-driven address, no CPU in the
 * drive path.  cpu/docs/plan.md §3.4(3), §5.
 *
 * ============================ WHAT THIS DOES NOT DO ======================
 *
 * DMA offloads the ADDRESS DRIVE. It does not help with DATA SAMPLING, and
 * that is the constraint people expect it to solve.
 *
 * Read data is guaranteed valid only over [E_fall - 40 ns, E_fall + 10 ns].
 * A DMA read of GPIOA->IDR triggered by the E edge lands several cycles AFTER
 * the edge -- past the 10 ns hold. Triggering off Q's fall instead lands a
 * quarter period (140 ns at 1.79 MHz) BEFORE the edge, which is outside the
 * 40 ns setup guarantee. Neither is sound. So variant 3 still samples with the
 * same polling loop as variants 1 and 2, and the T_iter <= 6 cycle bound
 * (spike.h) applies to it unchanged.
 *
 * ============================ WHAT IT MEASURES ===========================
 *
 * One number: how long after the E falling edge does a DMA-driven address
 * actually appear on the pins?
 *
 * That number decides whether the pipelined architecture in cpu/docs/plan.md §4.2
 * is worth building. If it comes in well under variant 2's ~13 cycles, the
 * cycles whose address is knowable a bus cycle ahead -- instruction fetch
 * runs, VMA cycles, stack pushes -- can be driven by hardware and the CPU
 * spends its whole slack on the emulator instead. If it comes in near 13,
 * the added complexity buys nothing and variant 2 is the answer.
 *
 * Note the precondition: the value must ALREADY be in memory when the edge
 * arrives. Genuinely data-dependent cycles (the address depends on the byte
 * just read) can never use this path and must fall back to variant 2. So this
 * is a measurement of a ceiling for part of the workload, not a drop-in
 * replacement.
 *
 * ============================ HOW IT MEASURES ============================
 *
 * The CPU spins reading GPIOB->IDR -- the address bus read back through the
 * same pins the DMA drives -- waiting for the precomputed value to appear,
 * then timestamps against TIM1->CCR1, the hardware capture of the E edge.
 *
 * The readback spin is ldr(2) + cmp(1) + bne(3) = 6 cycles, so the result is
 * quantised to ~6 cycles and biased HIGH by up to 6. Treat it as an upper
 * bound. For a precise figure, jumper one address line to a spare timer
 * capture input and difference two hardware timestamps; PA11 is TIM1_CH4 and
 * carries /RESET, so on the bench it can be borrowed for this.
 *
 * Addresses alternate between two values so the readback always transitions.
 */

#include "stm32g431.h"
#include "pinout.h"
#include "spike.h"

/* Trigger source. Default is TIM1_CH1's capture event: it is the same E
 * falling edge, routed through hardware gpio.c already configures for
 * timestamping, so it needs one peripheral fewer than the EXTI path. Define
 * SPIKE_DMA_TRIGGER_EXTI to use EXTI + the DMAMUX request generator instead.
 * Both paths are verified against RM0440; worth measuring both once, since a
 * latency difference between them is itself informative. */
#ifndef SPIKE_DMA_TRIGGER_EXTI
#define SPIKE_DMA_TRIGGER_EXTI 0
#endif

/* The word the DMA copies to GPIOB->ODR on every trigger. In CCM so the CPU's
 * update in the slack half of the cycle cannot contend with anything. */
static __ccmbss volatile uint32_t s_dma_addr;

/* Two arbitrary, distinct 16-bit addresses. Alternating them guarantees the
 * readback spin always sees a transition. */
#define ADDR_A 0xA55AU
#define ADDR_B 0x5AA5U

/* Outer guard iterations; each does 8 unrolled readback checks. If the address
 * has not appeared by then the DMA is not firing -- bail rather than hang.
 * The register constants are verified against RM0440 (see stm32g431.h), so a
 * timeout most likely means a wiring or clock-enable problem rather than a
 * wrong bit position. */
#define DMA_SPIN_LIMIT 2500U

void spike_dma_init(void)
{
    RCC->AHB1ENR |= RCC_AHB1ENR_DMA1EN | RCC_AHB1ENR_DMAMUX1EN;
    (void)RCC->AHB1ENR;

    s_dma_addr = ADDR_A;

    DMA_Channel_TypeDef *ch = DMA1_CH(1);
    ch->CCR   = 0;                        /* disable before reconfiguring */
    /* via uintptr_t so the host syntax check (64-bit) stays clean */
    ch->CPAR  = (uint32_t)(uintptr_t)&GPIOB->ODR;  /* dest: the address bus */
    ch->CMAR  = (uint32_t)(uintptr_t)&s_dma_addr;  /* src: precomputed word */
    ch->CNDTR = 1U;

    /* Memory -> peripheral, 32-bit both ends, no increment either side.
     * Circular so CNDTR reloads to 1 after each transfer and the channel is
     * armed again without CPU intervention. Highest priority: this is the
     * only thing on the bus that has a deadline. */
    ch->CCR = DMA_CCR_DIR_M2P | DMA_CCR_CIRC
            | DMA_CCR_PSIZE_32 | DMA_CCR_MSIZE_32
            | DMA_CCR_PL_VHIGH;

#if SPIKE_DMA_TRIGGER_EXTI
    /* EXTI8 (PA8 = E), falling edge, into DMAMUX request generator 0. */
    RCC->APB2ENR |= RCC_APB2ENR_SYSCFGEN;
    (void)RCC->APB2ENR;

    /* EXTI8 -> port A. EXTICR[2] holds lines 8..11; nibble 0, value 0 = PA. */
    SYSCFG_EXTICR(2) &= ~0xFU;

    /* RM0440 §15.3.5 "Hardware event selection": set the mask bit in EXTI_EMR
     * and the trigger selection in EXTI_RTSR/FTSR. EMR rather than IMR -- the
     * event path drives the DMAMUX trigger without raising an interrupt. */
    EXTI_RTSR1 &= ~MASK_E;
    EXTI_FTSR1 |=  MASK_E;      /* falling edge only */
    EXTI_PR1    =  MASK_E;      /* clear stale pending */
    EXTI_EMR1  |=  MASK_E;

    DMAMUX_RGCR(0) = (DMAMUX_TRIG_EXTI(PIN_E) << DMAMUX_RGCR_SIG_ID_Pos)
                   | DMAMUX_RGCR_GPOL_FALL
                   | DMAMUX_RGCR_GE;       /* GNBREQ = 0 -> one request */
    DMAMUX_CCR(0)  = DMAMUX_REQ_GEN0;
#else
    /* TIM1 CC1 (the E falling-edge capture set up in gpio.c) as the request. */
    TIM1->DIER |= TIM_DIER_CC1DE;
    DMAMUX_CCR(0) = DMAMUX_REQ_TIM1_CH1;
#endif

    DMA1_CH(1)->CCR |= DMA_CCR_EN;
}

/* __hot: the readback spin is the measurement instrument, so it must run from
 * zero-wait CCM. Left in flash it would execute at 4 wait states and the
 * quantisation would be several times coarser than the thing being measured. */
__hot void spike_run_dma(uint32_t n_cycles, spike_result_t *out)
{
    uint32_t timeouts = 0, overruns = 0;
    uint16_t lat_worst = 0, lat_best = 0xFFFFU;
    uint16_t per_min = 0xFFFFU, per_max = 0;
    uint64_t lat_sum = 0;
    uint32_t hist[SPIKE_HIST_BINS];

    for (uint32_t i = 0; i < SPIKE_HIST_BINS; i++) {
        hist[i] = 0;
    }

    (void)TIM1->CCR1;
    TIM1->SR = 0;

    uint32_t nxt = ADDR_B;
    uint16_t t_edge_prev = (uint16_t)TIM1->CCR1;

    for (uint32_t i = 0; i < n_cycles; i++) {
        /* Arm the next transfer. The DMA will copy this to GPIOB->ODR on the
         * coming E fall, with no CPU involvement -- this is the whole point.
         * Written here, in the slack, roughly a full bus cycle ahead. */
        s_dma_addr = nxt;

        /* Spin on the address-bus readback. GPIOB carries only A0..A15, so the
         * upper IDR bits read zero and no masking is needed.
         *
         * The checks are unrolled so the sample path is ldr(2) + cmp(1) +
         * beq(1, not taken) = 4 cycles with no backward branch between
         * samples. A guard counter inside the loop would add cmp + beq + add
         * = 3 more, making the instrument coarser than the quantity it
         * measures -- DMA latency is expected around 10-20 cycles, and at
         * 9-cycle granularity we could not tell 13 from 18. Checking the
         * guard once per 8 samples keeps both the tight path and the timeout.
         *
         * Measured latency is therefore true latency + [0,4) quantisation +
         * ~3 for the taken exit branch. Biased high, consistently. */
#define SPIN_CHECK() do { if (GPIOB->IDR == nxt) goto found; } while (0)

        for (uint32_t guard = 0; guard < DMA_SPIN_LIMIT; guard++) {
            SPIN_CHECK(); SPIN_CHECK(); SPIN_CHECK(); SPIN_CHECK();
            SPIN_CHECK(); SPIN_CHECK(); SPIN_CHECK(); SPIN_CHECK();
        }
#undef SPIN_CHECK

        /* Fell out of the guard: the DMA never drove the bus. */
        timeouts++;
        t_edge_prev = (uint16_t)TIM1->CCR1;
        nxt = (nxt == ADDR_A) ? ADDR_B : ADDR_A;
        continue;

    found: ;
        uint16_t t_done = (uint16_t)TIM1->CNT;
        uint16_t t_edge = (uint16_t)TIM1->CCR1;

        uint16_t lat    = (uint16_t)(t_done - t_edge);
        uint16_t period = (uint16_t)(t_edge - t_edge_prev);
        t_edge_prev = t_edge;

        if (TIM1->SR & TIM_SR_CC1OF) {
            overruns++;
            TIM1->SR = ~(uint32_t)TIM_SR_CC1OF;
        }

        if (lat > lat_worst) lat_worst = lat;
        if (lat < lat_best)  lat_best  = lat;
        lat_sum += lat;
        if (period < per_min) per_min = period;
        if (period > per_max) per_max = period;
        hist[lat < SPIKE_HIST_BINS ? lat : SPIKE_HIST_BINS - 1U]++;

        nxt = (nxt == ADDR_A) ? ADDR_B : ADDR_A;
    }

    out->cycles_run      = n_cycles;
    out->overruns        = overruns;
    out->dma_timeouts    = timeouts;
    out->lat_worst       = lat_worst;
    out->lat_best        = lat_best;
    out->lat_sum         = lat_sum;
    out->lat_jitter      = (uint16_t)(lat_worst - lat_best);
    out->period_min      = per_min;
    out->period_max      = per_max;

    /* The deadline still applies -- the address has to arrive within t_AD
     * however it gets there. There is no hold check: the DMA cannot fire
     * before the edge that triggers it, so t_AH cannot be violated by this
     * path. */
    out->deadline_misses = 0;
    out->hold_violations = 0;
    for (uint32_t bin = 0; bin < SPIKE_HIST_BINS; bin++) {
        out->hist[bin] = hist[bin];
        if (bin > SPIKE_TAD_CYCLES) {
            out->deadline_misses += hist[bin];
        }
    }
}
