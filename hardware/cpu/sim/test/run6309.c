/* run6309.c - OUR side of the 6309 differential test: hd6309.c (through
 * cpu6809_step with is6309 set) on a 64 K flat RAM, writing the trace
 * oracle/xroar_run.c writes for XRoar's core.
 *
 *   run6309 prog.bin trace maxcyc
 *
 * Trace lines, one per instruction boundary and one per write:
 *   <cycle> <pc> <a> <b> <e> <f> <x> <y> <u> <s> <v> <dp> <cc> <md>
 *   <cycle> W <addr> <value>
 * A write to $FFE0 ends the run.
 */
#include <stdio.h>
#include <stdlib.h>
#include "../cpu6809.h"

static uint8_t mem[65536];
static FILE *tf;
static cpu6809 cpu;
static int done;

static uint8_t rd(void *ctx, uint16_t a) { (void)ctx; return mem[a]; }

/* ⭐ THE INTERRUPT PORT, the same in oracle/xroar_run.c: a write to $FFD0-$FFD5
 * raises or lowers IRQ, FIRQ or NMI, so the PROGRAM decides where an interrupt
 * arrives and both cores take it at the same instruction boundary. */
/* ⚠ THE CHANGE LANDS AT THE NEXT INSTRUCTION BOUNDARY, not in the write's
 * cycle: WHERE inside an instruction its write falls is a bus-timing model
 * (XRoar puts a store's write after its dead cycles, this core as soon as the
 * address is known), and this test is of interrupt entry, stacking and
 * return - not of that. */
static int pend[6];
static void port(uint16_t a) { if (a >= 0xFFD0 && a <= 0xFFD5) pend[a - 0xFFD0] = 1; }
static void apply_port(void)
{
    static const int line[6] = { CPU6809_IRQ, CPU6809_IRQ, CPU6809_FIRQ, CPU6809_FIRQ, CPU6809_NMI, CPU6809_NMI };
    for (int k = 0; k < 6; k++)
        if (pend[k]) { pend[k] = 0; cpu6809_set_line(&cpu, line[k], !(k & 1), cpu.cycles); }
}

/* A step's writes, held until the step says whether it was an instruction
 * (its boundary line goes first) or an interrupt entry (no boundary line). */
static char wbuf[1 << 16];
static size_t wlen;

static void wr(void *ctx, uint16_t a, uint8_t v)
{
    (void)ctx;
    if (done) return;
    if (wlen < sizeof wbuf - 64)
        wlen += (size_t)snprintf(wbuf + wlen, sizeof wbuf - wlen, "%llu W %04x %02x\n",
                                 (unsigned long long)cpu.now, a, v);
    mem[a] = v;
    port(a);
    if (a == 0xFFE0) done = 1;
}

int main(int argc, char **argv)
{
    if (argc < 4) { fprintf(stderr, "usage: run6309 prog.bin trace maxcyc\n"); return 1; }
    FILE *f = fopen(argv[1], "rb");
    if (!f || fread(mem, 1, 65536, f) != 65536) { fprintf(stderr, "FAIL  run6309: cannot read %s\n", argv[1]); return 1; }
    fclose(f);
    tf = fopen(argv[2], "w");
    if (!tf) return 1;
    static char buf[1 << 20];
    setvbuf(tf, buf, _IOFBF, sizeof buf);
    unsigned long long maxcyc = strtoull(argv[3], 0, 0);
    cpu.read = rd;
    cpu.write = wr;
    cpu6309_enable(&cpu);
    cpu6809_reset(&cpu);
    /* ⚠ The registers reset leaves UNDEFINED, as the oracle leaves them - so
     * the traces agree from the first line.  (Silicon defines none of them
     * but DP, CC and MD; every generated chunk loads the rest before use.) */
    cpu.a = cpu.b = cpu.e = cpu.f = 0xFF;
    cpu.x = cpu.y = cpu.u = cpu.s = cpu.v = 0xFFFF;
    /* ⚠ A BOUNDARY IS AN INSTRUCTION'S, NOT A STEP'S: a step that enters an
     * interrupt prints no boundary, as XRoar's hook fires only on a fetch. */
    char line[160];
    while (!done && cpu.cycles < maxcyc) {
        int waiting = cpu.wait;
        snprintf(line, sizeof line, "%llu %04x %02x %02x %02x %02x %04x %04x %04x %04x %04x %02x %02x %02x\n",
                 (unsigned long long)cpu.cycles, cpu.pc, cpu.a, cpu.b, cpu.e, cpu.f,
                 cpu.x, cpu.y, cpu.u, cpu.s, cpu.v, cpu.dp, cpu.cc, cpu.md);
        wlen = 0;
        cpu6809_step(&cpu);
        if (!waiting && !cpu.took_int) fputs(line, tf);
        fwrite(wbuf, 1, wlen, tf);
        apply_port();
    }
    fclose(tf);
    return 0;
}
