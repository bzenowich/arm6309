/* Microstate cost probe, tuned hot path -- hand-written.  docs/plan.md §3.3(d).
 *
 * The C probes (microstates.c, tuned.c) hit two walls that are artifacts of C
 * rather than of the problem: the AAPCS returns anything over 4 bytes through
 * memory, and llvm-mca cannot cost an indirect call.  Since §3.4(1) already
 * commits the bus loop to hand-written assembly in CCM, the honest thing is to
 * measure the assembly.
 *
 * These are measurement fragments, not linked code -- no prologues, no
 * returns, just the per-bus-cycle work with state where it will really live.
 *
 * Register allocation held across the whole run (callee-saved, set up once):
 *
 *   r0   cpu_t *            X/Y/U/S, postbyte, the things too numerous to pin
 *   r1   &GPIOA->IDR        data bus + E + Q + /HALT in one word
 *   r2   &GPIOC->IDR        /NMI /IRQ /FIRQ
 *   r3   &GPIOB->ODR        address bus
 *   r4   A                  accumulator
 *   r5   alu_a  \
 *   r6   alu_m   |          lazy condition codes: operands and raw result,
 *   r7   alu_r  /           materialised only when an instruction reads CC
 *   r8   ctrl_c            accumulated GPIOC samples (active low, AND-folded)
 *   r9   ctrl_a            accumulated GPIOA samples (ditto, for /HALT)
 *   r10  gpioa             this cycle's GPIOA word, loaded for the data bus
 *   r11  microstate table base
 *   r12  scratch
 */

    .syntax unified
    .thumb
    .text

/* ---- ALU: A = A + dbus, lazy CC ---------------------------------------
 * The naive version spends ~18 of 28 instructions materialising H/N/Z/V/C.
 * Deferring that leaves the actual arithmetic, which is nearly free. */
# LLVM-MCA-BEGIN alu_adda_lazy
    mov     r5, r4                  /* alu_a = A                        */
    ubfx    r6, r10, #0, #8         /* alu_m = data bus from the GPIOA word */
    add     r7, r4, r6              /* alu_r = A + M, carry in bit 8    */
    uxtb    r4, r7                  /* A = result                       */
# LLVM-MCA-END

/* ---- Control-line sampling -------------------------------------------
 * Paid on EVERY bus cycle, so it has to be nearly free.
 *
 * The trick is to not decode anything here.  All five inputs are active low,
 * so AND-folding the raw words means any line that was ever asserted leaves a
 * zero bit behind.  Nothing can be missed, and the invert/mask/edge-detect
 * work moves to the instruction boundary where there is slack.
 *
 * /HALT is PA12, already inside r10 -- the same word the data bus came from.
 * That is a direct payoff from the §3.2 pin assignment: it costs one AND. */
# LLVM-MCA-BEGIN ctrl_sample_fold
    ldr     r12, [r2]               /* GPIOC: /NMI /IRQ /FIRQ           */
    and     r8, r8, r12
    and     r9, r9, r10             /* /HALT, free from the data load   */
# LLVM-MCA-END

/* ---- Next-state advance ----------------------------------------------
 * One microstate = one bus cycle.  The successor is data-dependent only on
 * the post-read path; here it is a plain table walk. */
# LLVM-MCA-BEGIN next_state
    ldr     r12, [r11, #8]          /* st->next                         */
    mov     r11, r12
# LLVM-MCA-END

/* ---- One complete bus cycle, tuned -----------------------------------
 * ALU step + control sampling + next-state advance + the address store.
 * THIS is the number that must fit in ~34 core cycles at 3 MHz. */
# LLVM-MCA-BEGIN cycle_full_tuned
    mov     r5, r4
    ubfx    r6, r10, #0, #8
    add     r7, r4, r6
    uxtb    r4, r7
    ldr     r12, [r2]
    and     r8, r8, r12
    and     r9, r9, r10
    ldr     r12, [r11, #8]
    mov     r11, r12
    ldr     r12, [r11, #0]          /* next address, precomputed        */
    str     r12, [r3]               /* drive GPIOB->ODR                 */
# LLVM-MCA-END

/* ---- Indexed post-increment ------------------------------------------
 * X/Y/U/S are too numerous to pin, so this keeps its load and store.  The
 * contiguous layout (cpu.h) is what keeps the register select branchless. */
# LLVM-MCA-BEGIN idx_postinc
    ldrb    r12, [r0, #22]          /* postbyte                         */
    ubfx    r5,  r12, #5, #2        /* register select                  */
    add     r5,  r0, r5, lsl #1
    ldrh    r6,  [r5]               /* R                                */
    and     r12, r12, #1
    add     r12, r12, #1            /* +1 or +2                         */
    add     r7,  r6, r12
    strh    r7,  [r5]               /* R updated                        */
# LLVM-MCA-END

/* ---- 16-bit ALU: D = D + operand, lazy CC ---------------------------- */
# LLVM-MCA-BEGIN alu_addd_lazy
    mov     r5, r4                  /* alu_a = D (A:B pinned as one)    */
    mov     r6, r7                  /* alu_m = assembled operand        */
    add     r7, r4, r6
    uxth    r4, r7
# LLVM-MCA-END

/* ---- TFM block-transfer step ----------------------------------------- */
# LLVM-MCA-BEGIN tfm_step
    ldrb    r12, [r0, #22]          /* postbyte                         */
    ubfx    r5,  r12, #4, #2
    and     r12, r12, #3
    add     r5,  r0, r5, lsl #1
    add     r12, r0, r12, lsl #1
    ldrh    r6,  [r5]
    ldrh    r7,  [r12]
    adds    r6,  r6, #1
    adds    r7,  r7, #1
    strh    r6,  [r5]
    strh    r7,  [r12]
    subs    r9,  r9, #1             /* W--, pinned                      */
    uxth    r9,  r9
# LLVM-MCA-END
