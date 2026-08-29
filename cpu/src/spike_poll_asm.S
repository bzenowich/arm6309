/* Phase 1 timing spike, variant 2: polling loop in hand-written assembly.
 * cpu/docs/plan.md §5. Companion wrapper: spike_run_poll_asm() in spike_poll.c.
 *
 * Two independent budgets have to be met, and they pull in opposite
 * directions:
 *
 *   T_iter <= t_DSR = 40 ns = 6.8 core cycles
 *       The gap between consecutive IDR samples. The sample we USE is the last
 *       one taken before E fell, so it lands in [E_fall - T_iter, E_fall). Only
 *       if that is inside the datasheet's guaranteed read-data window is the
 *       sample sound. This is a correctness bound, not a performance one.
 *
 *   latency <= t_AD = 110 ns = 18.7 core cycles
 *       Hardware E falling edge -> new address on GPIOB->ODR.
 *
 * The obvious C loop cannot meet the first:
 *
 *       mov r7, r6      1      prev = cur
 *       ldr r6, [r0]    2      cur  = IDR
 *       tst r6, #E      1
 *       bne .-          3      taken branch, pipeline refill
 *                       = 7 cycles.  Over budget.
 *
 * Unrolling by two removes the register copy by alternating destinations, and
 * pays the taken branch only once per two samples:
 *
 *       ldr r6,[r0]  2  | sample A at t=2
 *       tst r6,#E    1  |
 *       beq  ...     1  | not taken
 *       ldr r7,[r0]  2  | sample B at t=6
 *       tst r7,#E    1  |
 *       bne poll     3  | taken -> next A at t=12
 *
 * Sample gaps are 4 (A->B) and 6 (B->A'), so T_iter worst case is 6 cycles
 * = 35.3 ns, inside the 40 ns bound with ~5 ns to spare. Tight, and the
 * reason this variant exists.
 *
 * Which register holds the pre-edge sample depends on where the edge landed,
 * so there are two exit paths. The drive sequence is duplicated rather than
 * branched to, keeping it 4 cycles on both:
 *
 *       ubfx r12, rPrev, #0, #8         1   extract the data byte
 *       ldr  r12, [r2, r12, lsl #2]     2   next address from the table
 *       str  r12, [r1]                  1   drive GPIOB->ODR
 *
 * Worst case latency is therefore roughly (detection <= 6) + (branch 3) +
 * (drive 4) = 13 cycles, against the 18.7 allowed.
 *
 * Everything after the store is bookkeeping in the slack half of the cycle and
 * does not affect the measured latency. Statistics are derived in C from the
 * histogram; this only maintains the histogram, the overcapture count and the
 * observed E period range.
 *
 * uint32_t spike_run_poll_asm_raw(uint32_t n_cycles,      // r0
 *                                 uint32_t *hist,         // r1, 64 words, pre-cleared
 *                                 uint16_t *period_out);  // r2, [0]=min [1]=max
 * returns: overrun count
 */

    .syntax unified
    .thumb
    .section .ccmram.text, "ax", %progbits
    .p2align 3
    .thumb_func
    .global spike_run_poll_asm_raw
    .type   spike_run_poll_asm_raw, %function

/* Peripheral addresses, resolved at assembly time -- no runtime pointer chase
 * on the hot path. See cpu/include/pinout.h for the pin assignment. */
    .equ GPIOA_IDR, 0x48000010      /* D0-D7 in bits 0-7, E in bit 8, Q in 9 */
    .equ GPIOB_ODR, 0x48000414      /* A0-A15                                */
    .equ TIM1_BASE, 0x40012C00
    .equ TIM_SR,    0x10
    .equ TIM_CNT,   0x24
    .equ TIM_CCR1,  0x34            /* hardware timestamp of the E fall      */
    .equ E_MASK,    0x100           /* PA8                                   */
    .equ CC1IF,     0x002           /* TIM1_SR: E fall captured              */
    .equ CC2IF,     0x004           /* TIM1_SR: Q fall captured              */
    .equ CC1OF,     0x200           /* TIM1_SR overcapture                   */
    .equ HIST_MAX,  63              /* SPIKE_HIST_BINS - 1                   */

spike_run_poll_asm_raw:
    push    {r2, r4-r11, lr}        /* r2 = period_out, kept on the stack */

    mov     r5, r0                  /* loop counter                       */
    mov     r4, r1                  /* histogram base                     */
    ldr     r0, =GPIOA_IDR
    ldr     r1, =GPIOB_ODR
    ldr     r2, =stub_next_addr
    ldr     r3, =TIM1_BASE

    movs    r9, #0                  /* overruns                           */
    movw    r10, #0xFFFF            /* period_min                         */
    movs    r11, #0                 /* period_max                         */

    /* Drop any stale capture and overcapture state. */
    ldr     r12, [r3, #TIM_CCR1]
    movs    r12, #0
    str     r12, [r3, #TIM_SR]

    /* Sync to a falling edge so the first measured cycle is a whole one. */
0:  ldr     r7, [r0]
    tst     r7, #E_MASK
    beq     0b
1:  ldr     r7, [r0]
    tst     r7, #E_MASK
    bne     1b
    ldr     r8, [r3, #TIM_CCR1]
    uxth    r8, r8                  /* t_edge_prev                        */
    mvn     r7, #CC2IF              /* arm the first Q-fall wait          */
    str     r7, [r3, #TIM_SR]

/* ---------------------------------------------------------------- cycle -- */
    .p2align 3
.Lcycle:
    /* Wait for Q to FALL, not for E to rise.
     *
     * Q falls at 0.75 of the bus cycle and E at 1.0, so this flag means "one
     * quarter period to the edge". Everything before it -- the bookkeeping at
     * the bottom of the loop, and in the real core the microcode step -- runs
     * in that freed 0.75 of the cycle. Spinning on the E pin instead would
     * burn the whole E-high phase (41 core cycles at 1.79 MHz) for nothing.
     *
     * Anchored on a hardware capture rather than a predicted time, so it
     * survives the live 0.895 <-> 1.79 MHz switch: a faster clock just means
     * Q falls sooner and the flag is already set. */
2:  ldr     r7, [r3, #TIM_SR]
    tst     r7, #CC2IF
    beq     2b

    /* Prime the alternating sample registers. E is guaranteed high here: it
     * rises at 0.56 of the cycle, Q falls at 0.75. */
    ldr     r7, [r0]

    /* ============ Sampling window opens here. ============ */
    .p2align 2
.Lpoll:
    ldr     r6, [r0]                /* 2  sample A                        */
    tst     r6, #E_MASK             /* 1                                  */
    beq     .Ledge_prev_r7          /* 1 not taken / 3 taken              */
    ldr     r7, [r0]                /* 2  sample B                        */
    tst     r7, #E_MASK             /* 1                                  */
    bne     .Lpoll                  /* 3 taken                            */

    /* E fell between sample B and the next sample A: pre-edge value is r6. */
    ubfx    r12, r6, #0, #8         /* 1  data byte                       */
    ldr     r12, [r2, r12, lsl #2]  /* 2  next address                    */
    str     r12, [r1]               /* 1  DRIVE                           */
    b       .Lmeasure

    /* E fell between sample A and sample B: pre-edge value is r7. */
.Ledge_prev_r7:
    ubfx    r12, r7, #0, #8         /* 1                                  */
    ldr     r12, [r2, r12, lsl #2]  /* 2                                  */
    str     r12, [r1]               /* 1  DRIVE                           */
    /* fall through */

/* ------------------------------------------------- slack: bookkeeping -- */
.Lmeasure:
    dsb                             /* the store must have actually landed */
    ldr     r12, [r3, #TIM_CNT]     /* t_done                              */
    /* CCR1 is read ~7+ cycles after the edge. The capture path has a
     * synchroniser (no input filter is configured), so it should be latched
     * well before this -- but if it were not, we would read the PREVIOUS
     * capture and compute a latency of roughly one whole E period. That shows
     * up as a lone spike in the top histogram bin rather than as plausible
     * noise, so the failure is self-announcing. Worth confirming on silicon. */
    ldr     r6,  [r3, #TIM_CCR1]    /* t_edge, captured in hardware        */
    sub     r12, r12, r6
    uxth    r12, r12                /* latency, core cycles                */

    sub     lr, r6, r8
    uxth    lr, lr                  /* E period, core cycles               */
    uxth    r8, r6                  /* t_edge_prev = t_edge                */

    /* Clear this cycle's Q-fall flag so the wait at the top of the next
     * iteration sees only the next one. Safe here -- we are past E-fall and
     * the next Q fall is three quarters of a cycle away. Writing 0 clears;
     * the 1s leave every other flag alone. */
    mvn     r7, #CC2IF
    str     r7, [r3, #TIM_SR]

    /* Overcapture: a second E fall arrived before we read CCR1, so a whole
     * bus cycle went unserviced. */
    ldr     r7, [r3, #TIM_SR]
    tst     r7, #CC1OF
    beq     3f
    add     r9, r9, #1
    mvn     r7, #CC1OF
    str     r7, [r3, #TIM_SR]
3:

    /* Track the E period range: min != max means the host switched speed
     * mid-run, which is exactly what cpu/docs/plan.md §2.1 requires us to
     * survive. */
    cmp     lr, r10
    it      lo
    movlo   r10, lr
    cmp     lr, r11
    it      hi
    movhi   r11, lr

    /* hist[min(latency, 63)]++ */
    mov     r7, r12
    cmp     r7, #HIST_MAX
    it      hi
    movhi   r7, #HIST_MAX
    ldr     lr, [r4, r7, lsl #2]
    add     lr, lr, #1
    str     lr, [r4, r7, lsl #2]

    subs    r5, r5, #1
    bne     .Lcycle

/* --------------------------------------------------------------- exit -- */
    ldr     r3, [sp]                /* period_out                          */
    strh    r10, [r3, #0]
    strh    r11, [r3, #2]
    mov     r0, r9                  /* return overruns                     */
    pop     {r2, r4-r11, pc}

    .size spike_run_poll_asm_raw, . - spike_run_poll_asm_raw
