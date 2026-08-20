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
volatile spike_result_t g_result;
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
    spike_run_poll(SPIKE_CYCLES, &r);

    g_result       = r;
    g_run_complete = 0x6309C0DEU;

    __asm__ volatile("cpsie i" ::: "memory");

    /* Halt here so the debugger can pick the results up. */
    for (;;) { __asm__ volatile("bkpt 0"); }
}
