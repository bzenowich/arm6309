/* A cycle-counting 6809 (not 6309) for the host-side emulator of this machine.
 *
 * ⭐ THE REFERENCE IS NOT THE DATASHEET, IT IS hardware/vendor/mc6809/mc6809i.v -
 * the core every machine simulation runs. The emulator exists to predict the RTL
 * machine, so where the two disagree (cycle counts, SEX's flags, SWI3's vector)
 * this file does what the Verilog does and says so where it does it.
 * test/run.sh is the proof: it runs both on the same programs and interrupt
 * schedules and diffs every register at every instruction boundary and every
 * write with its E cycle.
 *
 * Time. `cycles` counts E cycles since reset; cycle 0 is the one that fetches
 * the first opcode from the reset vector's address (mc6809i.v's three reset
 * states before it are not counted). During a read or write callback `now` is
 * the index of the E cycle that access occupies, so a peripheral can be cycle
 * exact without the core stopping mid-instruction. The core does not perform
 * the Verilog's don't-care reads, so only real operand, stack and vector
 * accesses reach `read`.
 *
 * Interrupt lines are levels, 1 = asserted. The Verilog samples them at the
 * fall of Q and acts on them two E cycles later (one for NMI's edge), so a
 * change the caller makes between steps counts as happening at `cycles`, the
 * first cycle of the next step. A peripheral that knows the cycle it changed a
 * line in says so with cpu6809_set_line(), which is exact provided the same line
 * does not change twice within one instruction.
 */
#ifndef CPU6809_H
#define CPU6809_H

#include <stdint.h>

typedef struct cpu6809_line { int lvl, prev; int64_t t; } cpu6809_line;

typedef struct cpu6809 {
    uint8_t a, b, dp, cc;
    uint16_t x, y, u, s, pc;
    int irq, firq, nmi;          /* input line levels, 1 = asserted (active) */
    uint64_t cycles;             /* E cycles executed since reset */
    void *ctx;
    uint8_t (*read)(void *ctx, uint16_t addr);
    void (*write)(void *ctx, uint16_t addr, uint8_t v);

    uint64_t now;                /* E cycle of the access in progress (valid inside read/write) */
    int wait;                    /* 0 running, 1 CWAI, 2 SYNC, 3 seized (see cpu6809.c) */
    int nmi_armed;               /* S has changed since reset (mc6809i.v NMIMask) */
    int nmi_latched;             /* an NMI edge is latched and not yet taken */
    int nmi_edge;                /* an edge seen, not yet visible to the core */
    int64_t nmi_edge_t;
    cpu6809_line l_irq, l_firq, l_nmi;
} cpu6809;

enum { CPU6809_IRQ, CPU6809_FIRQ, CPU6809_NMI };

void cpu6809_reset(cpu6809 *c);   /* PC from $FFFE/$FFFF, CC = I|F set */
int  cpu6809_step(cpu6809 *c);    /* take a pending interrupt or execute one instruction; returns E cycles consumed and adds them to c->cycles */
/* Set a line to `level` as of E cycle `at` (at <= c->cycles). */
void cpu6809_set_line(cpu6809 *c, int line, int level, uint64_t at);

#endif
