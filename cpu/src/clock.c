/* 170 MHz from HSI16 — no crystal, because we are slaved to the host's E/Q.
 *
 * HSI16 16 MHz / M=4 -> 4 MHz, x N=85 -> 340 MHz VCO, / R=2 -> 170 MHz.
 * VCO must land in 96..344 MHz; 340 is inside it.
 *
 * Two STM32G4 gotchas are handled here and neither is optional:
 *
 *  1. Above 150 MHz the core needs Range 1 BOOST mode (PWR_CR5.R1MODE = 0).
 *     Leave it in normal Range 1 and the part is out of spec at 170 MHz —
 *     which typically shows up as flaky behaviour, not a clean failure.
 *
 *  2. RM0440 requires the AHB prescaler be held at /2 across the switch to a
 *     frequency above 80 MHz, for at least 1 us, before going back to /1.
 *     Skipping this is a classic source of intermittent boot failures.
 *
 * Flash is set to 4 wait states BEFORE the frequency goes up, never after.
 */

#include "stm32g431.h"

void clock_init_170mhz(void)
{
    /* PWR must be clocked before its registers are writable. */
    RCC->APB1ENR1 |= RCC_APB1ENR1_PWREN;
    (void)RCC->APB1ENR1;

    /* UCPD1 dead-battery pull-downs OFF, before anything drives the bus.
     *
     * They are ENABLED out of reset (RM0440 §25.4.3) and they land on PB4 and
     * PB6 -- A4 and A6 in this pinout. Each is a ~5.1 kOhm pull-down that
     * activates when the paired CC pin's alternate signal goes high: PA9 (Q,
     * toggling at the bus rate) arms PB6, PA10 (R/W) arms PB4. Our push-pull
     * drivers win against 5.1 kOhm, so levels survive -- but it is a
     * bus-rate-modulated load on two address lines, i.e. free edge jitter,
     * and ST's own guidance is to clear it in any application that is not a
     * USB-C sink. One write. */
    PWR_CR3 |= PWR_CR3_UCPD1_DBDIS;

    /* Voltage scaling Range 1. */
    PWR_CR1 = (PWR_CR1 & ~PWR_CR1_VOS_Msk) | PWR_CR1_VOS_RANGE1;
    while (PWR_SR2 & PWR_SR2_VOSF) { }

    /* Range 1 boost mode — required above 150 MHz. */
    PWR_CR5 &= ~PWR_CR5_R1MODE;

    /* Wait states up front, plus the caches and prefetch. Code that matters
     * runs from CCM anyway, but everything else still reads from flash. */
    FLASH_ACR = (FLASH_ACR & ~FLASH_ACR_LATENCY_Msk)
              | FLASH_ACR_LATENCY_4WS
              | FLASH_ACR_PRFTEN | FLASH_ACR_ICEN | FLASH_ACR_DCEN;
    while ((FLASH_ACR & FLASH_ACR_LATENCY_Msk) != FLASH_ACR_LATENCY_4WS) { }

    /* HSI16 on. */
    RCC->CR |= RCC_CR_HSION;
    while (!(RCC->CR & RCC_CR_HSIRDY)) { }

    /* PLL off before reconfiguring. */
    RCC->CR &= ~RCC_CR_PLLON;
    while (RCC->CR & RCC_CR_PLLRDY) { }

    RCC->PLLCFGR = RCC_PLLCFGR_PLLSRC_HSI16
                 | ((4U - 1U) << RCC_PLLCFGR_PLLM_Pos)   /* M = 4  */
                 | (85U       << RCC_PLLCFGR_PLLN_Pos)   /* N = 85 */
                 | (0U        << RCC_PLLCFGR_PLLR_Pos)   /* R = 2  */
                 | RCC_PLLCFGR_PLLREN;

    RCC->CR |= RCC_CR_PLLON;
    while (!(RCC->CR & RCC_CR_PLLRDY)) { }

    /* Gotcha 2: AHB /2 across the switch. */
    RCC->CFGR = (RCC->CFGR & ~RCC_CFGR_HPRE_Msk) | RCC_CFGR_HPRE_DIV2;

    RCC->CFGR = (RCC->CFGR & ~RCC_CFGR_SW_Msk) | RCC_CFGR_SW_PLL;
    while ((RCC->CFGR & RCC_CFGR_SWS_Msk) != RCC_CFGR_SWS_PLL) { }

    /* >= 1 us at 85 MHz. Deliberately generous; this runs once at boot. */
    for (volatile uint32_t i = 0; i < 500U; i++) { }

    RCC->CFGR = (RCC->CFGR & ~RCC_CFGR_HPRE_Msk) | RCC_CFGR_HPRE_DIV1;

    /* DWT cycle counter — secondary timebase. TIM1 is the primary one because
     * it can timestamp E/Q edges in hardware (see spike.h). */
    DEMCR |= DEMCR_TRCENA;
    DWT_CYCCNT = 0;
    DWT_CTRL |= DWT_CTRL_CYCCNTENA;
}
