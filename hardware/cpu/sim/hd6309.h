/* The HD6309 layer over cpu6809.c.
 *
 * ⭐ WHY THIS IS A SEPARATE FILE.  `cpu6809.c` is not a model of a 6809; it is a
 * model of **mc6809i.v**, matched to that core's bugs on purpose (SWI at 20
 * cycles, SEX setting no flags, the GHOST decode that makes $01 execute as NEG).
 * Its value is that a count can be checked against the Verilog by reading, and
 * test/run.sh proves it instruction for instruction.  A 6309 must NOT inherit any
 * of that: on a real HD6309E $01 is OIM, not a ghost of NEG.  So the 6309 lives
 * beside the 6809 rather than inside it, `c->is6309` selects, and with it clear
 * the core is byte-identical to what the differential test has always run.
 *
 * ⭐ SINCE 2026-09-24 IT IS A COMPLETE CORE: every encoding the HD6309 defines,
 * both modes, native mode's timing and stacking, and both traps.  An encoding
 * the 6309 does not define takes the illegal-instruction trap, as on silicon;
 * a 6309 opcode on a 6809 core is still refused by name (cpu6809.c).
 */
#ifndef HD6309_H
#define HD6309_H

#include "cpu6809.h"

/* One step of an HD6309E: take a pending interrupt, or execute one
 * instruction; returns the E cycles it took and adds them to c->cycles.
 * cpu6809_step() calls this whenever c->is6309 is set. */
int hd6309_step(cpu6809 *c);

/* The 6309's own reading of TFR/EXG postbyte codes, which extends the 6809's:
 * 6 = W, 7 = V, 12/13 = the zero register, 14 = E, 15 = F. */
uint16_t hd6309_tfr_get(const cpu6809 *c, int code);
void     hd6309_tfr_set(cpu6809 *c, int code, uint16_t v);
int      hd6309_tfr_is8(int code);

#endif
