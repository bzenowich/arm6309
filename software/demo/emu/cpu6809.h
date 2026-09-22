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

    /* ---- HD6309 ---------------------------------------------------------
     * ⭐ `is6309` selects. With it CLEAR this core is byte-identical to the
     * 6809 the differential test has always run against mc6809e.v, and every
     * 6309-only encoding is refused (see undef6309 below). With it SET, the
     * encodings hd6309.c implements execute and the rest are still refused.
     * ⚠ The GHOST decode is a 6809 property and does NOT apply in 6309 mode:
     * $01 is OIM on an HD6309E, not a ghost of NEG. */
    int is6309;
    uint8_t e, f;                /* W = E:F;  Q = D:W = A:B:E:F */
    uint16_t v;                  /* the 6309's V scratch register */
    uint8_t md;                  /* b0 native mode, b1 FIRQ-stacks-like-IRQ */
    int irq, firq, nmi;          /* input line levels, 1 = asserted (active) */
    uint64_t cycles;             /* E cycles executed since reset */
    void *ctx;
    uint8_t (*read)(void *ctx, uint16_t addr);
    void (*write)(void *ctx, uint16_t addr, uint8_t v);

    /* ⭐ Called when a 6309-ONLY opcode is fetched, before it is decoded.
     * `page` is 0/1/2 for no prefix, $10, $11; `op` is the RAW byte (not the
     * ghost-mapped one); `pc` addresses the opcode itself.
     *
     * ⛔ THE DEFAULT IS TO ABORT, AND THAT IS THE POINT.  Without this hook a
     * 6309 instruction decodes as its 6809 ghost - $01 OIM executes as NEG,
     * $1138 TFM as an invalid 2-cycle no-op - and the machine runs on to a
     * plausible wrong answer.  armio.asm:513 is the standing rule that exists
     * because of it: "a TFM here assembled, linked, booted - and copied
     * NOTHING."  Set this to observe instead of dying; leave it NULL to die.
     * It is also the seam a real 6309 core plugs into. */
    void (*undef6309)(void *ctx, int page, uint8_t op, uint16_t pc);

    uint64_t now;                /* E cycle of the access in progress (valid inside read/write) */
    int wait;                    /* 0 running, 1 CWAI, 2 SYNC, 3 seized (see cpu6809.c) */
    int nmi_armed;               /* S has changed since reset (mc6809i.v NMIMask) */
    int nmi_latched;             /* an NMI edge is latched and not yet taken */
    int nmi_edge;                /* an edge seen, not yet visible to the core */
    int64_t nmi_edge_t;
    cpu6809_line l_irq, l_firq, l_nmi;
} cpu6809;

enum { CPU6809_IRQ, CPU6809_FIRQ, CPU6809_NMI };

/* Make this core an HD6309E. Call before cpu6809_reset(). */
void cpu6309_enable(cpu6809 *c);

/* The indexed effective address, exposed for hd6309.c. */
int  cpu6809_idx_ea(cpu6809 *c, int64_t base, int n, uint8_t b2,
                    uint16_t *eap, int *seize);

int  cpu6809_int_pending(cpu6809 *c, int64_t at);

void cpu6809_reset(cpu6809 *c);   /* PC from $FFFE/$FFFF, CC = I|F set */
int  cpu6809_step(cpu6809 *c);    /* take a pending interrupt or execute one instruction; returns E cycles consumed and adds them to c->cycles */
/* Set a line to `level` as of E cycle `at` (at <= c->cycles). */
void cpu6809_set_line(cpu6809 *c, int line, int level, uint64_t at);

#endif
