/* Pin assignment for the HD6309E drop-in — single source of truth.
 * Mirrors docs/plan.md §3.2. Change both together.
 *
 * STM32G431CBT6, LQFP48: 42 GPIO, minus PA13/PA14 (SWD) and PG10 (NRST) = 39.
 * The CoCo 3 needs 33; we wire 35 (adding BA/BS) and spend the rest on a debug
 * console and an LED, leaving one spare.
 *
 * BUSY, /LIC, AVMA and TSC are deliberately ABSENT. The Color Computer 3
 * Service Manual (Cat. 26-3334) schematic marks BA, BS, BUSY, /LIC and AVMA all
 * NC at IC1, and §5.1 states TSC "is permanently grounded". Emulating outputs
 * nothing reads would cost the UART and the LED — a bad trade for this target.
 *
 *   PB0..PB15   A0..A15      out    one 32-bit store to GPIOB->ODR
 *   PA0..PA7    D0..D7       bidir  one byte load/store on GPIOA
 *   PA8         E            in     TIM1_CH1 (AF6) — hardware edge capture
 *   PA9         Q            in     TIM1_CH2 (AF6) — hardware edge capture
 *   PA10        R/W          out
 *   PA11        /RESET       in
 *   PA12        /HALT        in
 *   PA13/PA14   SWDIO/SWCLK  --     debug
 *   PA15        BUS_OE       out    tri-states all bus buffers during /HALT
 *   PC4         BA           out    NC on the CoCo 3; wired for other 6809E hosts
 *   PC6         BS           out    likewise
 *   PC10        UART_TX      out    USART3_TX (AF7) — debug console
 *   PC11        UART_RX      in     USART3_RX (AF7)
 *   PC13        /NMI         in     PC13-15 are input-only: limited output drive
 *   PC14        /IRQ         in
 *   PC15        /FIRQ        in
 *   PF0         LED          out    status
 *   PF1         --                  spare
 *   PG10        NRST
 *
 * EXTERNAL BUFFERS ARE MANDATORY, not a preference. DS12589 Table 12 lists
 * PA0..PA7 -- the whole data bus -- plus PB0..PB2 and PB10 as TT_a, rated
 * 3.6 V. The CoCo 3's 74LS245 drives 5 V TTL at us on every read, and the
 * board's 4.7K pull-ups take the address bus to 5 V whenever we tri-state.
 * Behind 3.3 V-powered 74LVC buffers the MCU never sees more than 3.3 V.
 * Wire this part straight to the socket and it dies. See docs/plan.md §3.5.
 *
 * E and Q sit on PA8/PA9 deliberately: one LDR of GPIOA->IDR yields the data
 * bus in bits 0-7 and the clock state in bits 8-9, saving a load on the
 * critical path. They are configured as AF6 (TIM1_CH1/CH2) so the timer can
 * timestamp edges in hardware; IDR still reflects the pin level in AF mode, so
 * the polling loop reads the same pins.
 */
#ifndef ARM6309_PINOUT_H
#define ARM6309_PINOUT_H

/* ---- GPIOA ---- */
#define PIN_D0       0U      /* D0..D7 = PA0..PA7 */
#define PIN_E        8U
#define PIN_Q        9U
#define PIN_RW      10U
#define PIN_RESET   11U
#define PIN_HALT    12U
#define PIN_SWDIO   13U
#define PIN_SWCLK   14U
#define PIN_BUS_OE  15U

#define MASK_DATA   0x00FFU
#define MASK_E      (1U << PIN_E)
#define MASK_Q      (1U << PIN_Q)
#define MASK_RW     (1U << PIN_RW)
#define MASK_RESET  (1U << PIN_RESET)
#define MASK_HALT   (1U << PIN_HALT)
#define MASK_BUS_OE (1U << PIN_BUS_OE)

/* ---- GPIOB: A0..A15, nothing else ---- */
#define MASK_ADDR   0xFFFFU

/* ---- GPIOC ---- */
#define PIN_BA       4U
#define PIN_BS       6U
#define PIN_UART_TX 10U
#define PIN_UART_RX 11U
#define PIN_NMI     13U
#define PIN_IRQ     14U
#define PIN_FIRQ    15U

#define MASK_BA     (1U << PIN_BA)
#define MASK_BS     (1U << PIN_BS)
#define MASK_NMI    (1U << PIN_NMI)
#define MASK_IRQ    (1U << PIN_IRQ)
#define MASK_FIRQ   (1U << PIN_FIRQ)

/* ---- GPIOF ---- */
#define PIN_LED      0U
#define MASK_LED    (1U << PIN_LED)
/* PF1 spare */

/* AF numbers, verified against the STM32G431 alternate-function table. */
#define AF_TIM1      6U   /* PA8 = TIM1_CH1, PA9 = TIM1_CH2   */
#define AF_USART3    7U   /* PC10 = USART3_TX, PC11 = USART3_RX */

#endif /* ARM6309_PINOUT_H */
