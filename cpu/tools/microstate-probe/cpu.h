/* Register layout for the microstate cost probe.  cpu/docs/plan.md §3.3(d), §4.1.
 *
 * This is not the final core -- it exists to answer one question with a number
 * instead of an estimate: does one bus cycle's worth of emulator work fit in
 * the ~34 core cycles available at 3 MHz (or ~48 at 1.79 MHz)?
 *
 * Layout choices here are deliberate and load-bearing for the answer:
 *
 *   - X, Y, U, S first and contiguous.  Indexed addressing selects one of them
 *     with a 2-bit field from the postbyte, so the decode becomes a scaled
 *     load/store rather than a four-way branch.  A branch here would cost more
 *     than the addressing mode itself.
 *   - Everything the hot path touches sits inside one 128-byte window so a
 *     single base register reaches all of it with immediate offsets.
 */

#ifndef PROBE_CPU_H
#define PROBE_CPU_H

#include <stdint.h>

/* Condition codes, 6809/6309: E F H I N Z V C (bit 7 .. bit 0) */
#define CC_C 0x01u
#define CC_V 0x02u
#define CC_Z 0x04u
#define CC_N 0x08u
#define CC_I 0x10u
#define CC_H 0x20u
#define CC_F 0x40u
#define CC_E 0x80u

/* Latched interrupt / halt requests */
#define P_NMI  0x01u
#define P_IRQ  0x02u
#define P_FIRQ 0x04u
#define P_HALT 0x08u

typedef struct cpu {
    /* Must stay first and contiguous -- see header comment. */
    uint16_t x, y, u, s;

    uint16_t pc;
    uint16_t v;               /* 6309 V register            */
    uint8_t  a, b, e, f;      /* D = A:B, W = E:F, Q = D:W  */
    uint8_t  dp;
    uint8_t  cc;
    uint8_t  md;

    /* Per-cycle bus state */
    uint8_t  dbus;            /* byte latched this bus cycle */
    uint16_t ea;              /* effective address under construction */
    uint8_t  ir;              /* current opcode  */
    uint8_t  postbyte;

    /* Control-line sampling */
    uint8_t  ctrl_prev;       /* last GPIOC sample, for NMI edge detect */
    uint8_t  pending;         /* latched requests, P_* above */
} cpu_t;

/* GPIOC base 0x48000800 + IDR offset 0x10.  /NMI, /IRQ, /FIRQ on PC13..PC15
 * (cpu/include/pinout.h).  /HALT is PA12, so it arrives free in the same GPIOA
 * word the data bus is read from -- it costs no extra load. */
#define GPIOC_IDR (*(volatile uint32_t *)0x48000810u)

#endif /* PROBE_CPU_H */
