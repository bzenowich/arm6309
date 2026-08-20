/* Minimal STM32G431 register definitions.
 *
 * Deliberately hand-rolled rather than pulling in CMSIS/HAL: the Phase 1 spike
 * touches five peripherals, and a self-contained header keeps the repo
 * buildable with nothing but arm-none-eabi-gcc. It also compiles cleanly on the
 * host, so `gcc -fsyntax-only` is a usable check without a cross toolchain.
 *
 * Offsets per RM0440. Verify against the reference manual before trusting any
 * bit position here.
 */
#ifndef ARM6309_STM32G431_H
#define ARM6309_STM32G431_H

#include <stdint.h>

#define __IO volatile

/* ------------------------------------------------------------------ GPIO -- */

typedef struct {
    __IO uint32_t MODER;    /* 0x00 */
    __IO uint32_t OTYPER;   /* 0x04 */
    __IO uint32_t OSPEEDR;  /* 0x08 */
    __IO uint32_t PUPDR;    /* 0x0C */
    __IO uint32_t IDR;      /* 0x10 */
    __IO uint32_t ODR;      /* 0x14 */
    __IO uint32_t BSRR;     /* 0x18 */
    __IO uint32_t LCKR;     /* 0x1C */
    __IO uint32_t AFR[2];   /* 0x20, 0x24 */
    __IO uint32_t BRR;      /* 0x28 */
} GPIO_TypeDef;

#define GPIOA ((GPIO_TypeDef *)0x48000000UL)
#define GPIOB ((GPIO_TypeDef *)0x48000400UL)
#define GPIOC ((GPIO_TypeDef *)0x48000800UL)
#define GPIOF ((GPIO_TypeDef *)0x48001400UL)

#define GPIO_MODE_INPUT  0x0U
#define GPIO_MODE_OUTPUT 0x1U
#define GPIO_MODE_AF     0x2U
#define GPIO_MODE_ANALOG 0x3U

#define GPIO_SPEED_VERY_HIGH 0x3U

/* ------------------------------------------------------------------- RCC -- */

typedef struct {
    __IO uint32_t CR;          /* 0x00 */
    __IO uint32_t ICSCR;       /* 0x04 */
    __IO uint32_t CFGR;        /* 0x08 */
    __IO uint32_t PLLCFGR;     /* 0x0C */
    uint32_t      RESERVED0[2];
    __IO uint32_t CIER;        /* 0x18 */
    __IO uint32_t CIFR;        /* 0x1C */
    __IO uint32_t CICR;        /* 0x20 */
    uint32_t      RESERVED1;
    __IO uint32_t AHB1RSTR;    /* 0x28 */
    __IO uint32_t AHB2RSTR;    /* 0x2C */
    __IO uint32_t AHB3RSTR;    /* 0x30 */
    uint32_t      RESERVED2;
    __IO uint32_t APB1RSTR1;   /* 0x38 */
    __IO uint32_t APB1RSTR2;   /* 0x3C */
    __IO uint32_t APB2RSTR;    /* 0x40 */
    uint32_t      RESERVED3;
    __IO uint32_t AHB1ENR;     /* 0x48 */
    __IO uint32_t AHB2ENR;     /* 0x4C */
    __IO uint32_t AHB3ENR;     /* 0x50 */
    uint32_t      RESERVED4;
    __IO uint32_t APB1ENR1;    /* 0x58 */
    __IO uint32_t APB1ENR2;    /* 0x5C */
    __IO uint32_t APB2ENR;     /* 0x60 */
} RCC_TypeDef;

#define RCC ((RCC_TypeDef *)0x40021000UL)

#define RCC_CR_HSION      (1U << 8)
#define RCC_CR_HSIRDY     (1U << 10)
#define RCC_CR_PLLON      (1U << 24)
#define RCC_CR_PLLRDY     (1U << 25)

#define RCC_CFGR_SW_Msk   (3U << 0)
#define RCC_CFGR_SW_PLL   (3U << 0)
#define RCC_CFGR_SWS_Msk  (3U << 2)
#define RCC_CFGR_SWS_PLL  (3U << 2)
#define RCC_CFGR_HPRE_Msk (0xFU << 4)
#define RCC_CFGR_HPRE_DIV1 (0x0U << 4)
#define RCC_CFGR_HPRE_DIV2 (0x8U << 4)

#define RCC_PLLCFGR_PLLSRC_HSI16 (2U << 0)
#define RCC_PLLCFGR_PLLM_Pos     4     /* field holds M-1 */
#define RCC_PLLCFGR_PLLN_Pos     8
#define RCC_PLLCFGR_PLLREN       (1U << 24)
#define RCC_PLLCFGR_PLLR_Pos     25    /* 00:/2 01:/4 10:/6 11:/8 */

#define RCC_AHB2ENR_GPIOAEN (1U << 0)
#define RCC_AHB2ENR_GPIOBEN (1U << 1)
#define RCC_AHB2ENR_GPIOCEN (1U << 2)
#define RCC_AHB2ENR_GPIOFEN (1U << 5)

#define RCC_APB1ENR1_PWREN  (1U << 28)
#define RCC_APB2ENR_TIM1EN  (1U << 11)

/* ------------------------------------------------------------------- PWR -- */

#define PWR_BASE 0x40007000UL
#define PWR_CR1 (*(__IO uint32_t *)(PWR_BASE + 0x00))
#define PWR_SR2 (*(__IO uint32_t *)(PWR_BASE + 0x14))
#define PWR_CR5 (*(__IO uint32_t *)(PWR_BASE + 0x80))

#define PWR_CR1_VOS_Msk     (3U << 9)
#define PWR_CR1_VOS_RANGE1  (1U << 9)
#define PWR_SR2_VOSF        (1U << 10)
#define PWR_CR5_R1MODE      (1U << 8)   /* 0 = boost mode (needed above 150 MHz) */

/* ----------------------------------------------------------------- FLASH -- */

#define FLASH_ACR (*(__IO uint32_t *)(0x40022000UL + 0x00))

#define FLASH_ACR_LATENCY_Msk (0xFU << 0)
#define FLASH_ACR_LATENCY_4WS (0x4U << 0)
#define FLASH_ACR_PRFTEN      (1U << 8)
#define FLASH_ACR_ICEN        (1U << 9)
#define FLASH_ACR_DCEN        (1U << 10)

/* ------------------------------------------------------------------ TIM1 -- */
/* Used as the measurement timebase: 170 MHz, no prescaler, with input capture
 * on E (CH1) and Q (CH2) so edges get a hardware timestamp independent of any
 * software polling jitter. */

typedef struct {
    __IO uint32_t CR1;    /* 0x00 */
    __IO uint32_t CR2;    /* 0x04 */
    __IO uint32_t SMCR;   /* 0x08 */
    __IO uint32_t DIER;   /* 0x0C */
    __IO uint32_t SR;     /* 0x10 */
    __IO uint32_t EGR;    /* 0x14 */
    __IO uint32_t CCMR1;  /* 0x18 */
    __IO uint32_t CCMR2;  /* 0x1C */
    __IO uint32_t CCER;   /* 0x20 */
    __IO uint32_t CNT;    /* 0x24 */
    __IO uint32_t PSC;    /* 0x28 */
    __IO uint32_t ARR;    /* 0x2C */
    __IO uint32_t RCR;    /* 0x30 */
    __IO uint32_t CCR1;   /* 0x34 */
    __IO uint32_t CCR2;   /* 0x38 */
    __IO uint32_t CCR3;   /* 0x3C */
    __IO uint32_t CCR4;   /* 0x40 */
    __IO uint32_t BDTR;   /* 0x44 */
} TIM_TypeDef;

#define TIM1 ((TIM_TypeDef *)0x40012C00UL)

#define TIM_CR1_CEN     (1U << 0)
#define TIM_CCER_CC1E   (1U << 0)
#define TIM_CCER_CC1P   (1U << 1)   /* 1 = falling edge for input capture */
#define TIM_CCER_CC2E   (1U << 4)
#define TIM_CCER_CC2P   (1U << 5)
#define TIM_SR_CC1IF    (1U << 1)
#define TIM_SR_CC2IF    (1U << 2)
#define TIM_SR_CC1OF    (1U << 9)   /* overcapture: an edge was missed */
#define TIM_SR_CC2OF    (1U << 10)
#define TIM_EGR_UG      (1U << 0)

/* CCMR1 input-capture mode: CC1S=01 maps IC1 to TI1, CC2S=01 maps IC2 to TI2. */
#define TIM_CCMR1_CC1S_TI1 (1U << 0)
#define TIM_CCMR1_CC2S_TI2 (1U << 8)

/* ------------------------------------------------------------- DWT / SCB -- */

#define DEMCR      (*(__IO uint32_t *)0xE000EDFCUL)
#define DEMCR_TRCENA (1U << 24)
#define DWT_CTRL   (*(__IO uint32_t *)0xE0001000UL)
#define DWT_CYCCNT (*(__IO uint32_t *)0xE0001004UL)
#define DWT_CTRL_CYCCNTENA (1U << 0)

/* ------------------------------------------------------------ attributes -- */

/* On the target these place code and data in zero-wait CCM SRAM. On the host
 * they collapse to nothing so the same sources still compile for syntax
 * checking and for the stub-core unit test. */
#if defined(__arm__)
#define __hot     __attribute__((section(".ccmram.text"), noinline, aligned(8)))
#define __ccmdata __attribute__((section(".ccmram.data"), aligned(4)))
#define __ccmbss  __attribute__((section(".ccmram.bss"), aligned(4)))
#else
#define __hot
#define __ccmdata
#define __ccmbss
#endif

#endif /* ARM6309_STM32G431_H */
