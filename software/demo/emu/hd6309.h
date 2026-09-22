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
 * ⛔ WHAT IS NOT IMPLEMENTED IS REFUSED, NOT IGNORED.  hd6309_exec() returns
 * HD6309_UNIMPL for an encoding it does not yet handle, and cpu6809.c then takes
 * the same refusal path a 6809 takes - the opcode is named and the run stops.
 * That is what makes building this out one group at a time safe: the failure mode
 * is never "it did nothing", which is the defect armio.asm:513 records.
 */
#ifndef HD6309_H
#define HD6309_H

#include "cpu6809.h"

#define HD6309_UNIMPL (-1)

/* Execute one 6309-only instruction whose opcode has already been fetched.
 * `page` is 0/1/2, `op` the raw opcode byte, `n` the cycles consumed so far
 * (the opcode and any prefix). Returns the total cycle count, or HD6309_UNIMPL
 * if this build does not implement it. */
int hd6309_exec(cpu6809 *c, int64_t base, int n, int page, uint8_t op,
                uint16_t opc_pc);

/* The 6309's own reading of TFR/EXG postbyte codes, which extends the 6809's:
 * 6 = W, 7 = V, 12/13 = the zero register, 14 = E, 15 = F. */
uint16_t hd6309_tfr_get(const cpu6809 *c, int code);
void     hd6309_tfr_set(cpu6809 *c, int code, uint16_t v);
int      hd6309_tfr_is8(int code);

#endif
