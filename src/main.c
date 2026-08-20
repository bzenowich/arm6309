/* Phase 1 timing spike entry point.  docs/plan.md §5, §7.
 *
 * There are no spare pins for a UART (the pinout uses all 39), so results are
 * left in a fixed global and read over SWD. See README for the gdb recipe.
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
     * both gates -- lat_worst <= 18 and lat_jitter <= 6. */
    spike_run_poll_asm(SPIKE_CYCLES, &r);
    g_result_asm = r;

    /* Variant 3: DMA drives the address; no CPU in the drive path. Measures
     * the floor for cycles whose address is knowable a bus cycle ahead.
     * Check dma_timeouts first -- non-zero means the DMA never fired. */
    spike_dma_init();
    spike_run_dma(SPIKE_CYCLES, &r);
    g_result_dma = r;

    g_run_complete = 0x6309C0DEU;

    __asm__ volatile("cpsie i" ::: "memory");

    /* Halt here so the debugger can pick the results up. */
    for (;;) { __asm__ volatile("bkpt 0"); }
}
