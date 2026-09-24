/* Minimal Cortex-M4 startup: vector table, .data / .ccmram copy, .bss zero.
 *
 * The .ccmram copy is what puts the bus loop in zero-wait CCM SRAM; without it
 * the hot path would execute from 4-wait-state flash and every Phase 1 number
 * would be wrong. */

#include <stdint.h>

extern uint32_t _sidata, _sdata, _edata;
extern uint32_t _sbss,  _ebss;
extern uint32_t _siccm, _sccm, _eccm;
extern uint32_t _sccmbss, _eccmbss;
extern uint32_t _stack_top;

int  main(void);
void Reset_Handler(void);

static void Default_Handler(void)
{
    for (;;) { __asm__ volatile("bkpt 0"); }
}

void NMI_Handler(void)        __attribute__((weak, alias("Default_Handler")));
void HardFault_Handler(void)  __attribute__((weak, alias("Default_Handler")));
void MemManage_Handler(void)  __attribute__((weak, alias("Default_Handler")));
void BusFault_Handler(void)   __attribute__((weak, alias("Default_Handler")));
void UsageFault_Handler(void) __attribute__((weak, alias("Default_Handler")));
void SVC_Handler(void)        __attribute__((weak, alias("Default_Handler")));
void DebugMon_Handler(void)   __attribute__((weak, alias("Default_Handler")));
void PendSV_Handler(void)     __attribute__((weak, alias("Default_Handler")));
void SysTick_Handler(void)    __attribute__((weak, alias("Default_Handler")));

__attribute__((section(".isr_vector"), used))
void (* const g_vectors[])(void) = {
    (void (*)(void))&_stack_top,
    Reset_Handler,
    NMI_Handler,
    HardFault_Handler,
    MemManage_Handler,
    BusFault_Handler,
    UsageFault_Handler,
    0, 0, 0, 0,
    SVC_Handler,
    DebugMon_Handler,
    0,
    PendSV_Handler,
    SysTick_Handler,
    /* Peripheral IRQs are unused: the bus loop runs with interrupts off. */
};

static void copy_range(const uint32_t *src, uint32_t *dst, uint32_t *end)
{
    while (dst < end) { *dst++ = *src++; }
}

static void zero_range(uint32_t *dst, uint32_t *end)
{
    while (dst < end) { *dst++ = 0; }
}

void Reset_Handler(void)
{
    copy_range(&_sidata, &_sdata, &_edata);
    copy_range(&_siccm,  &_sccm,  &_eccm);
    zero_range(&_sbss,     &_ebss);
    zero_range(&_sccmbss,  &_eccmbss);

    /* Enable the FPU (CP10/CP11 full access) before any code that might use
     * it — the toolchain is configured for hard float. */
    *(volatile uint32_t *)0xE000ED88UL |= (0xFU << 20);
    __asm__ volatile("dsb; isb");

    (void)main();

    for (;;) { __asm__ volatile("bkpt 0"); }
}
