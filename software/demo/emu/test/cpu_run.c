/* The emulator side of the differential test: cpu6809.c on the same 64 K flat
 * RAM, the same schedule, the same trace format as cpu_tb.sv.
 *
 *   cpu_run prog.bin prog.sched c.trace maxcyc [cov.out]
 *
 *   cpu_run --report a.cov b.cov ...         (exit 1 if a documented opcode never ran)
 *
 * Exit 2 if the core seized (an opcode the generator should not have made).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../cpu6809.h"

typedef struct { uint8_t mem[65536]; FILE *f; int done; long nwrite, nvec[3]; } sys_t;

static uint8_t rd(void *ctx, uint16_t a)
{
    sys_t *s = ctx;
    if (a == 0xFFF8) s->nvec[0]++;
    else if (a == 0xFFF6) s->nvec[1]++;
    else if (a == 0xFFFC) s->nvec[2]++;
    return s->mem[a];
}

static cpu6809 cpu;

/* coverage: documented opcodes executed, and indexed postbyte forms */
static long cov[3][256], covidx[256];
static int documented(int pg, int op)
{
    static const uint8_t bad1[] = { 0x01, 0x02, 0x05, 0x0B, 0x14, 0x15, 0x18, 0x1B, 0x38, 0x3E, 0x41, 0x42, 0x45,
        0x4B, 0x4E, 0x51, 0x52, 0x55, 0x5B, 0x5E, 0x61, 0x62, 0x65, 0x6B, 0x71, 0x72, 0x75, 0x7B, 0x87, 0x8F,
        0xC7, 0xCD, 0xCF, 0x10, 0x11 };
    static const uint8_t p2[] = { 0x3F, 0x83, 0x8C, 0x8E, 0x93, 0x9C, 0x9E, 0x9F, 0xA3, 0xAC, 0xAE, 0xAF, 0xB3,
        0xBC, 0xBE, 0xBF, 0xCE, 0xDE, 0xDF, 0xEE, 0xEF, 0xFE, 0xFF };
    static const uint8_t p3[] = { 0x3F, 0x83, 0x8C, 0x93, 0x9C, 0xA3, 0xAC, 0xB3, 0xBC };
    unsigned k;
    if (pg == 0) { for (k = 0; k < sizeof bad1; k++) if (bad1[k] == op) return 0; return 1; }
    if (pg == 1) { if (op >= 0x21 && op <= 0x2F) return 1; for (k = 0; k < sizeof p2; k++) if (p2[k] == op) return 1; return 0; }
    for (k = 0; k < sizeof p3; k++) if (p3[k] == op) return 1;
    return 0;
}
static void cover(const uint8_t *m, uint16_t pc)
{
    int pg = 0, op = m[pc];
    if (op == 0x10 || op == 0x11) { pg = op == 0x10 ? 1 : 2; op = m[(uint16_t)(pc + 1)]; pc++; }
    cov[pg][op]++;
    int hi = op >> 4;
    if ((hi == 6 || hi == 0xA || hi == 0xE || (op >= 0x30 && op <= 0x33)))
        covidx[m[(uint16_t)(pc + 1)] & 0x80 ? m[(uint16_t)(pc + 1)] & 0x9F : 0]++;
}

static void wr(void *ctx, uint16_t a, uint8_t v)
{
    sys_t *s = ctx;
    if (s->done) return;
    fprintf(s->f, "%llu W %04x %02x\n", (unsigned long long)cpu.now, a, v);
    s->mem[a] = v;
    s->nwrite++;
    if (a == 0xFFE0) s->done = 1;
}

static void report(const char *who)
{
    int ndoc = 0, nhit = 0, nund = 0, nidx = 0;
    char miss[4096] = "";
    for (int pg = 0; pg < 3; pg++)
        for (int op = 0; op < 256; op++) {
            if (documented(pg, op)) {
                ndoc++;
                if (cov[pg][op]) nhit++;
                else if (strlen(miss) < 4000) sprintf(miss + strlen(miss), " %s%02X", pg == 0 ? "" : pg == 1 ? "10" : "11", op);
            } else if (cov[pg][op] && !(pg == 0 && (op == 0x10 || op == 0x11))) nund++;
        }
    static const uint8_t forms[] = { 0x00, 0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x88, 0x89, 0x8B, 0x8C, 0x8D,
        0x91, 0x93, 0x94, 0x95, 0x96, 0x98, 0x99, 0x9B, 0x9C, 0x9D, 0x9F };
    for (unsigned k = 0; k < sizeof forms; k++) if (covidx[forms[k]]) nidx++;
    printf("%s: coverage: %d of %d documented opcodes, %d undocumented, %d of %d indexed forms%s%s\n",
           who, nhit, ndoc, nund, nidx, (int)sizeof forms, *miss ? "; missing" : "", miss);
}

int main(int argc, char **argv)
{
    if (argc > 1 && !strcmp(argv[1], "--report")) {
        /* sum the coverage files of several runs */
        for (int i = 2; i < argc; i++) {
            static long c2[3][256], i2[256];
            FILE *cf = fopen(argv[i], "rb");
            if (!cf || fread(c2, sizeof c2, 1, cf) != 1 || fread(i2, sizeof i2, 1, cf) != 1) { fprintf(stderr, "cannot read %s\n", argv[i]); return 1; }
            fclose(cf);
            for (int p = 0; p < 3; p++) for (int o = 0; o < 256; o++) cov[p][o] += c2[p][o];
            for (int o = 0; o < 256; o++) covidx[o] += i2[o];
        }
        report("all seeds");
        int missing = 0;
        for (int p = 0; p < 3; p++) for (int o = 0; o < 256; o++) if (documented(p, o) && !cov[p][o]) missing = 1;
        return missing;
    }
    static sys_t sys;
    static uint64_t ev_t[1 << 20];
    static int ev_l[1 << 20], ev_v[1 << 20];
    int nev = 0, ei = 0;
    if (argc < 5) { fprintf(stderr, "usage: cpu_run prog.bin prog.sched trace maxcyc [cov.out] | cpu_run --report cov...\n"); return 1; }
    FILE *f = fopen(argv[1], "rb");
    if (!f || fread(sys.mem, 1, 65536, f) != 65536) { fprintf(stderr, "FAIL  cpu_run: cannot read %s\n", argv[1]); return 1; }
    fclose(f);
    f = fopen(argv[2], "r");
    if (f) {
        unsigned long long t;
        while (nev < (1 << 20) && fscanf(f, "%llu %d %d", &t, &ev_l[nev], &ev_v[nev]) == 3) ev_t[nev++] = t;
        fclose(f);
    }
    uint64_t maxcyc = strtoull(argv[4], 0, 0);
    sys.f = fopen(argv[3], "w");
    if (!sys.f) return 1;
    static char buf[1 << 20];
    setvbuf(sys.f, buf, _IOFBF, sizeof buf);

    cpu.ctx = &sys;
    cpu.read = rd;
    cpu.write = wr;
    cpu6809_reset(&cpu);
    long nbound = 0;
    int rc = 0;
    while (!sys.done) {
        while (ei < nev && ev_t[ei] <= cpu.cycles) {
            cpu6809_set_line(&cpu, ev_l[ei], ev_v[ei], ev_t[ei]);
            ei++;
        }
        if (!cpu.wait) {
            if (cpu.cycles >= maxcyc) break;
            fprintf(sys.f, "%llu %04x %02x %02x %04x %04x %04x %04x %02x %02x\n",
                    (unsigned long long)cpu.cycles, cpu.pc, cpu.a, cpu.b, cpu.x, cpu.y,
                    cpu.u, cpu.s, cpu.dp, cpu.cc);
            nbound++;
            cover(sys.mem, cpu.pc);
        }
        if (cpu.wait == 3) { fprintf(stderr, "FAIL  cpu_run: the core seized at cycle %llu\n", (unsigned long long)cpu.cycles); rc = 2; break; }
        cpu6809_step(&cpu);
        if (cpu.cycles > maxcyc + 200000) { fprintf(stderr, "FAIL  cpu_run: no boundary near maxcyc\n"); rc = 1; break; }
    }
    fclose(sys.f);
    report("cpu_run");
    if (argc > 5) {
        FILE *cf = fopen(argv[5], "wb");
        if (cf) { fwrite(cov, sizeof cov, 1, cf); fwrite(covidx, sizeof covidx, 1, cf); fclose(cf); }
    }
    printf("cpu_run: %ld boundaries, %ld writes, %llu cycles; vector fetches IRQ %ld FIRQ %ld NMI %ld\n",
           nbound, sys.nwrite, (unsigned long long)cpu.cycles, sys.nvec[0], sys.nvec[1], sys.nvec[2]);
    return rc;
}
