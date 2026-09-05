/* Phase 1 timing spike entry point.  cpu/docs/plan.md §5, §7.
 *
 * Results are left in fixed globals and read over SWD. See README for the gdb
 * recipe. A debug UART does exist in the pinout -- USART3 on PC10/PC11, 38 of
 * the 39 usable pins spent, one spare (cpu/docs/plan.md §3.2) -- but it is not
 * wired up in Phase 1, so SWD is still the only way the numbers come out.
 */

#include "stm32g431.h"
#include "pinout.h"
#include "spike.h"

void clock_init_170mhz(void);
void gpio_init(void);
void tim1_capture_init(void);
void stub_core_init(void);

#define SPIKE_CYCLES 1000000U

/* Read these from gdb. Volatile so the optimiser cannot discard the stores. */
volatile spike_result_t g_result_c;    /* variant 1: polling loop in C       */
volatile spike_result_t g_result_asm;  /* variant 2: hand-written assembly   */
volatile spike_result_t g_result_dma;  /* variant 3: DMA-driven address      */
volatile uint32_t       g_data_window[SPIKE_HIST_BINS];
volatile uint32_t       g_run_complete;

int main(void)
{
    clock_init_170mhz();
    gpio_init();
    tim1_capture_init();
    stub_core_init();

    /* Interrupts off: an ISR taken inside the loop would land straight in the
     * measured latency and there is nothing here that needs to interrupt. */
    __asm__ volatile("cpsid i" ::: "memory");

    /* How long does the host actually hold data after E falls? This decides
     * whether the s_prev sampling trick in spike_poll.c is sound, so run it
     * before trusting any latency number that depends on it. */
    spike_characterise_data_window(1000U, (uint32_t *)g_data_window);

    spike_result_t r;

    /* Variant 1: the C baseline. Expected to FAIL the t_DSR bound
     * (lat_jitter > 6) because its loop needs a register copy -- that is the
     * result, not a bug. */
    spike_run_poll(SPIKE_CYCLES, &r);
    g_result_c = r;

    /* Variant 2: hand-written assembly. This is the one that should pass
     * both gates -- lat_worst <= SPIKE_TAD_CYCLES (14, tightened from the raw
     * 18.7-cycle t_AD ceiling to cover the terms the spike cannot see; see
     * spike.h) and lat_jitter <= 6.
     *
     * It does NOT report slack_min/slack_late -- the asm loop has no
     * overrun-of-slack detection. Read variant 1's slack_late first: if it is
     * non-zero at this E rate, variant 2 was entering the sampling window late
     * too and its latency numbers are optimistic by that much again. */
    spike_run_poll_asm(SPIKE_CYCLES, &r);
    g_result_asm = r;

    /* Variant 3: DMA drives the address; no CPU in the drive path. Measures
     * the floor for cycles whose address is knowable a bus cycle ahead.
     * Check dma_timeouts AND dma_errors first: errors non-zero means the
     * channel bus-errored (configuration), errors zero with timeouts means
     * the trigger never arrived (wiring). */
    spike_dma_init();
    spike_run_dma(SPIKE_CYCLES, &r);
    g_result_dma = r;

    g_run_complete = 0x6309C0DEU;

    __asm__ volatile("cpsie i" ::: "memory");

    /* Halt here so the debugger can pick the results up. */
    for (;;) { __asm__ volatile("bkpt 0"); }
}
