/* xroar_run.c - the ORACLE side of the 6309 differential test: XRoar's HD6309
 * core on a 64 K flat RAM, writing the same trace hardware/cpu/sim/test/run6309
 * writes for ours.
 *
 *   xroar_run prog.bin trace maxcyc
 *
 * Trace lines, one per instruction boundary and one per write:
 *   <cycle> <pc> <a> <b> <e> <f> <x> <y> <u> <s> <v> <dp> <cc> <md>
 *   <cycle> W <addr> <value>
 * Cycles count from the first instruction's fetch.  A write to $FFE0 ends the
 * run, as it does in cpu_run.c.
 *
 * ⭐ WHY IT INCLUDES hd6309.c.  XRoar builds its CPU through a part database
 * we do not carry; including the file reaches the static constructor directly,
 * and fetch-xroar.sh's stubs stand in for the framework around it.  See that
 * script for why the file itself is never copied into this repository.
 */
#include "hd6309.c"
#include <stdio.h>

static uint8_t mem[65536];
static FILE *tf;
static unsigned long long ncyc, cyc0, maxcyc;
static int started, done;
static struct HD6309 *H;
static int pend[6];

static void mem_cycle(void *sptr, bool rnw, uint16_t a)
{
    struct MC6809 *cpu = sptr;
    if (rnw) {
        cpu->D = mem[a];
    } else {
        if (started && !done)
            fprintf(tf, "%llu W %04x %02x\n", ncyc - cyc0, a, cpu->D);
        mem[a] = cpu->D;
        /* the interrupt port - test/run6309.c's: held to the next boundary */
        if (a >= 0xFFD0 && a <= 0xFFD5) pend[a - 0xFFD0] = 1;
        if (a == 0xFFE0) { done = 1; cpu->running = 0; }
    }
    ncyc++;
    if (started && ncyc - cyc0 >= maxcyc) cpu->running = 0;
}

static void hook(void *sptr, uint32_t pc)
{
    struct MC6809 *cpu = sptr;
    /* the interrupt port's changes land here, at the instruction boundary -
     * after this boundary's interrupt decision, as run6309.c applies them
     * after its step */
    for (int k = 0; k < 6; k++) {
        if (!pend[k]) continue;
        pend[k] = 0;
        bool *l = k < 2 ? &cpu->irq : k < 4 ? &cpu->firq : &cpu->nmi;
        *l = !(k & 1);
    }
    if (!started) { started = 1; cyc0 = ncyc; }
    if (done) return;
    fprintf(tf, "%llu %04x %02x %02x %02x %02x %04x %04x %04x %04x %04x %02x %02x %02x\n",
            ncyc - cyc0, (unsigned)pc, MC6809_REG_A(cpu), MC6809_REG_B(cpu),
            HD6309_REG_E(H), HD6309_REG_F(H), cpu->reg_x, cpu->reg_y, cpu->reg_u,
            cpu->reg_s, H->reg_v, cpu->reg_dp, cpu->reg_cc, H->reg_md);
}

int main(int argc, char **argv)
{
    if (argc < 4) { fprintf(stderr, "usage: xroar_run prog.bin trace maxcyc\n"); return 1; }
    FILE *f = fopen(argv[1], "rb");
    if (!f || fread(mem, 1, 65536, f) != 65536) { fprintf(stderr, "FAIL  xroar_run: cannot read %s\n", argv[1]); return 1; }
    fclose(f);
    tf = fopen(argv[2], "w");
    if (!tf) return 1;
    static char buf[1 << 20];
    setvbuf(tf, buf, _IOFBF, sizeof buf);
    maxcyc = strtoull(argv[3], 0, 0);

    struct part *p = hd6309_allocate();
    hd6309_initialise(p, NULL);
    H = (struct HD6309 *)p;
    struct MC6809 *cpu = &H->mc6809;
    cpu->mem_cycle = DELEGATE_AS2(void, bool, uint16, mem_cycle, cpu);
    cpu->instruction_hook = DELEGATE_AS1(void, uint32, hook, cpu);
    cpu->reset(cpu);
    cpu->running = 1;
    while (cpu->running && !done) cpu->run(cpu);
    fclose(tf);
    return 0;
}
