/* GPIO and TIM1 setup for the HD6309E pinout.  See include/pinout.h.
 *
 * Everything on the bus is set to VERY_HIGH output speed: at 1.79 MHz the
 * quarter-cycle deadline is 23.7 core cycles and slew rate is not somewhere to
 * give away nanoseconds.
 */

#include "stm32g431.h"
#include "pinout.h"

static void moder_set(GPIO_TypeDef *p, uint32_t pin, uint32_t mode)
{
    p->MODER = (p->MODER & ~(3U << (pin * 2U))) | (mode << (pin * 2U));
}

static void af_set(GPIO_TypeDef *p, uint32_t pin, uint32_t af)
{
    uint32_t idx = pin >> 3U;
    uint32_t sh  = (pin & 7U) * 4U;
    p->AFR[idx] = (p->AFR[idx] & ~(0xFU << sh)) | (af << sh);
}

void gpio_init(void)
{
    RCC->AHB2ENR |= RCC_AHB2ENR_GPIOAEN | RCC_AHB2ENR_GPIOBEN
                  | RCC_AHB2ENR_GPIOCEN | RCC_AHB2ENR_GPIOFEN;
    (void)RCC->AHB2ENR;

    /* ---- GPIOB: A0..A15, all outputs, max slew ---- */
    GPIOB->MODER   = 0x55555555U;   /* every pin = output */
    GPIOB->OSPEEDR = 0xFFFFFFFFU;   /* every pin = very high speed */
    GPIOB->OTYPER  = 0x00000000U;   /* push-pull */
    GPIOB->ODR     = 0xFFFFU;       /* $FFFF, the 6809 dead-cycle address */

    /* ---- GPIOA ----
     * PA0..PA7  D0..D7      input for now (direction follows R/W later)
     * PA8, PA9  E, Q        AF6 = TIM1_CH1 / TIM1_CH2
     * PA10      R/W         output
     * PA11,PA12 /RESET,/HALT input
     * PA13,PA14 SWD          left exactly as reset left them
     * PA15      BUS_OE      output
     *
     * MODER is built by hand rather than with moder_set() per pin so that
     * PA13/PA14 are provably untouched — clobbering them costs the debugger. */
    {
        uint32_t m = GPIOA->MODER;
        m &= ~0x03FFFFFFU;          /* clear pins 0..12  (bits 0..25)  */
        m &= ~(3U << 30);           /* clear pin 15      (bits 30..31) */
        m |= (GPIO_MODE_AF     << (PIN_E      * 2U));
        m |= (GPIO_MODE_AF     << (PIN_Q      * 2U));
        m |= (GPIO_MODE_OUTPUT << (PIN_RW     * 2U));
        m |= (GPIO_MODE_OUTPUT << (PIN_BUS_OE * 2U));
        GPIOA->MODER = m;
    }
    GPIOA->OSPEEDR = 0xFFFFFFFFU;
    GPIOA->PUPDR   = 0x00000000U;   /* external buffers define the levels */
    af_set(GPIOA, PIN_E, AF_TIM1);
    af_set(GPIOA, PIN_Q, AF_TIM1);

    /* ---- GPIOC: BA, BS out; /NMI, /IRQ, /FIRQ in; USART3 on PC10/PC11 ----
     * PC13..PC15 are backup-domain pins with limited output drive, which is
     * why the pinout puts only inputs there.
     *
     * BUSY, /LIC and AVMA are absent by design: the CoCo 3 leaves them NC
     * (see include/pinout.h). BA/BS are wired anyway for other 6809E hosts. */
    moder_set(GPIOC, PIN_BA,      GPIO_MODE_OUTPUT);
    moder_set(GPIOC, PIN_BS,      GPIO_MODE_OUTPUT);
    moder_set(GPIOC, PIN_NMI,     GPIO_MODE_INPUT);
    moder_set(GPIOC, PIN_IRQ,     GPIO_MODE_INPUT);
    moder_set(GPIOC, PIN_FIRQ,    GPIO_MODE_INPUT);
    moder_set(GPIOC, PIN_UART_TX, GPIO_MODE_AF);
    moder_set(GPIOC, PIN_UART_RX, GPIO_MODE_AF);
    af_set(GPIOC, PIN_UART_TX, AF_USART3);
    af_set(GPIOC, PIN_UART_RX, AF_USART3);
    GPIOC->OSPEEDR |= (GPIO_SPEED_VERY_HIGH << (PIN_BA * 2U))
                    | (GPIO_SPEED_VERY_HIGH << (PIN_BS * 2U));

    /* ---- GPIOF: status LED. PF1 spare. ---- */
    moder_set(GPIOF, PIN_LED, GPIO_MODE_OUTPUT);

    /* Bus buffers enabled (not halted), R/W = read. */
    GPIOA->BSRR = MASK_RW;
    GPIOA->BSRR = (uint32_t)MASK_BUS_OE << 16;  /* active low */
}

/* TIM1 as the measurement timebase: 170 MHz, free-running 16-bit, with input
 * capture on E (CH1, falling) and Q (CH2, rising). One tick == one core cycle,
 * so latencies read directly in core cycles. */
void tim1_capture_init(void)
{
    RCC->APB2ENR |= RCC_APB2ENR_TIM1EN;
    (void)RCC->APB2ENR;

    TIM1->CR1 = 0;
    TIM1->PSC = 0;             /* 170 MHz */
    TIM1->ARR = 0xFFFFU;       /* free-running, wraps every ~385 us */

    /* CC1 -> TI1 (E), CC2 -> TI2 (Q), no input filter or prescaler: a filter
     * would add its own latency to the very edge we are trying to timestamp. */
    TIM1->CCMR1 = TIM_CCMR1_CC1S_TI1 | TIM_CCMR1_CC2S_TI2;

    /* Both channels capture FALLING edges (CC1P/CC2P = 1).
     *
     * CC1 = E: the bus-cycle boundary, and the reference all latency is
     * measured against.
     *
     * CC2 = Q: Q falls at 0.75 of the bus cycle, E at 1.0, so a Q-fall
     * capture says "one quarter period until the next E fall". That is the
     * last hardware anchor before the edge, and the spike loops use its
     * capture FLAG to decide when to stop doing useful work and enter the
     * tight sampling loop. Without it the CPU has to spin through the whole
     * E-high phase and that time is unavailable to the emulator. */
    TIM1->CCER = TIM_CCER_CC1E | TIM_CCER_CC1P
               | TIM_CCER_CC2E | TIM_CCER_CC2P;

    TIM1->EGR = TIM_EGR_UG;    /* load PSC/ARR */
    TIM1->SR  = 0;
    TIM1->CR1 = TIM_CR1_CEN;
}
