/* software/demo/bench/replay_tb.sv, in C: the replayer on cpu6809.c.
 *
 *   demo_run --rom build/rom.bin --trace replay.trace --sram replay.sram --ticks N
 *            [--itrace file [--itrace-cycles N]] [--seconds S]
 *
 * The same 64 K map through sixteen map registers, the same ROM with the reset
 * vector forced to $8004, the same register-level stand-in for the audio card's
 * host port whose only behaviour is audio.md 8.2's tempo timer on /FIRQ, and
 * the same refplayer-format register trace. --itrace adds cpu_tb's boundary
 * and write lines, which test/demo_tb.sv writes from the Verilog, so the two
 * runs can be compared instruction by instruction.
 *
 * TIMING, which is what makes it the same run and not merely the same program.
 * replay_tb acts at each falling edge of E, in this order: the bus write of the
 * cycle that edge ends, then the timer. So a write at cycle k and a timer fire
 * at cycle k both move /FIRQ from cycle k+1, the timer's after the write's;
 * and a fire is due at the cycle the ACTRL write happened plus the period, then
 * at each due cycle plus the period in force at that edge. The core reports
 * the cycle of every write (cpu.now), so the timer is caught up to that cycle
 * before the write lands, and to the last cycle of each step after it.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "../cpu6809.h"

static cpu6809 cpu;
static uint8_t rom[1 << 20], ram[1 << 20], sram[524288];
static uint8_t maplo[16], maphi[16];
static int progress, trace_tick, timer_on, sdata_n;
static long ticks;
static uint32_t sptr;
static uint16_t timer;
static int64_t next_fire = -1;
static FILE *ft, *fi;
static uint64_t itrace_cycles;
static const char *names[16] = { "AIDX", "ADATA", "ADMACON", "AINTENA", "AINTREQ", "ACTRL", "SPTR2", "SPTR1",
                                 "SPTR0", "SDATA", "ASTAT", "TIMER1", "TIMER0", "R13", "R14", "R15" };

/* one tick is 5 * TIMER colour clocks (audio.md 8.2); E is 25.175 MHz / 12 */
static int64_t period_e(void) { return (int64_t)((5ULL * timer * 2097917ULL) / 3546895ULL); }

static void fires_upto(int64_t k)
{
    while (timer_on && next_fire <= k) {
        cpu6809_set_line(&cpu, CPU6809_FIRQ, 1, (uint64_t)(next_fire + 1));
        ticks++;
        next_fire += period_e();
        if (period_e() == 0) break;          /* TIMER = 0 would fire every cycle */
    }
}

static uint8_t rd(void *ctx, uint16_t a)
{
    (void)ctx;
    if (a >= 0xFFF0) {
        if (a == 0xFFFE) return 0x80;         /* THE RESET VECTOR POINTS AT THE DEMO */
        if (a == 0xFFFF) return 0x04;
        return rom[a & 0x1FFF];
    }
    if ((a >> 8) == 0xFF) return 0x00;        /* ASTAT never busy, VSTAT idle */
    unsigned blk = a >> 13, phys = ((maplo[blk] & 0x7Fu) << 13) | (a & 0x1FFFu);
    return maphi[blk] == 0x01 ? rom[phys] : ram[phys];
}

static void wr(void *ctx, uint16_t a, uint8_t v)
{
    (void)ctx;
    int64_t k = (int64_t)cpu.now;
    fires_upto(k - 1);
    if (fi && cpu.now < itrace_cycles) fprintf(fi, "%llu W %04x %02x\n", (unsigned long long)cpu.now, a, v);
    if ((a & 0xFFF0) == 0xFF90) maphi[a & 15] = v;
    else if ((a & 0xFFF0) == 0xFFA0) maplo[a & 15] = v;
    else if (a == 0xFF2F) progress = v;
    else if ((a & 0xFFF0) == 0xFF40) {
        int r = a & 15;
        /* refplayer's p->ticks counts mod_tick() calls, and a tick's first write is AINTREQ := $10 */
        if (r == 4 && v == 0x10) trace_tick++;
        if (r < 6 || r > 9) fprintf(ft, "%06d %-7s %02X\n", trace_tick, names[r], v);
        switch (r) {
        case 6: sptr = (sptr & 0xFFFF) | ((v & 7u) << 16); break;
        case 7: sptr = (sptr & 0x700FF) | ((unsigned)v << 8); break;
        case 8: sptr = (sptr & 0x7FF00) | v; break;
        case 9: sram[sptr] = v; sptr = (sptr + 1) & 0x7FFFF; sdata_n++; break;
        case 0xB: timer = (uint16_t)((timer & 0xFF) | (v << 8)); break;
        case 0xC: timer = (uint16_t)((timer & 0xFF00) | v); break;
        case 5: if ((v & 0x40) && !timer_on) { timer_on = 1; next_fire = k + period_e(); } break;
        case 4: if (!(v & 0x80) && (v & 0x10)) cpu6809_set_line(&cpu, CPU6809_FIRQ, 0, (uint64_t)(k + 1)); break;
        default: break;
        }
    } else if (maphi[a >> 13] != 0x01 && (a >> 8) != 0xFF) {
        ram[((maplo[a >> 13] & 0x7Fu) << 13) | (a & 0x1FFFu)] = v;
    }
    fires_upto(k);
}

int main(int argc, char **argv)
{
    const char *rom_path = "build/rom.bin", *trace_path = "build/replay.trace", *sram_path = 0, *itrace = 0;
    long want_ticks = 2001;
    for (int i = 1; i + 1 < argc; i += 2) {
        if (!strcmp(argv[i], "--rom")) rom_path = argv[i + 1];
        else if (!strcmp(argv[i], "--trace")) trace_path = argv[i + 1];
        else if (!strcmp(argv[i], "--sram")) sram_path = argv[i + 1];
        else if (!strcmp(argv[i], "--ticks")) want_ticks = atol(argv[i + 1]);
        else if (!strcmp(argv[i], "--itrace")) itrace = argv[i + 1];
        else if (!strcmp(argv[i], "--itrace-cycles")) itrace_cycles = strtoull(argv[i + 1], 0, 0);
        else { fprintf(stderr, "demo_run: unknown option %s\n", argv[i]); return 1; }
    }
    FILE *f = fopen(rom_path, "rb");
    if (!f || fread(rom, 1, sizeof rom, f) != sizeof rom) { fprintf(stderr, "FAIL  demo_run: cannot read %s\n", rom_path); return 1; }
    fclose(f);
    maplo[4] = 1; maphi[4] = 1; maplo[5] = 2; maphi[5] = 1;   /* boot.asm's handoff */
    maplo[6] = 6; maphi[6] = 2;                               /* the SIMM block */
    maplo[7] = 0; maphi[7] = 1;                               /* ROM page 0 */
    ft = fopen(trace_path, "w");
    if (!ft) return 1;
    static char tbuf[1 << 16], ibuf[1 << 20];
    setvbuf(ft, tbuf, _IOFBF, sizeof tbuf);
    if (itrace) {
        fi = fopen(itrace, "w");
        if (!fi) return 1;
        setvbuf(fi, ibuf, _IOFBF, sizeof ibuf);
        if (!itrace_cycles) itrace_cycles = ~0ULL;
    }

    cpu.read = rd;
    cpu.write = wr;
    cpu6809_reset(&cpu);
    int rc = 0;
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    int64_t stop = -1;
    for (;;) {
        if (fi && !cpu.wait && cpu.cycles < itrace_cycles)
            fprintf(fi, "%llu %04x %02x %02x %04x %04x %04x %04x %02x %02x\n", (unsigned long long)cpu.cycles,
                    cpu.pc, cpu.a, cpu.b, cpu.x, cpu.y, cpu.u, cpu.s, cpu.dp, cpu.cc);
        cpu6809_step(&cpu);
        fires_upto((int64_t)cpu.cycles - 1);
        if (stop < 0) {
            if (ticks >= want_ticks) stop = (int64_t)cpu.cycles + 20000;   /* let the last tick's writes land */
            if (progress >= 0xE0) { printf("FAIL  demo_run: the demo reported $%02X\n", progress); rc = 1; break; }
            if (cpu.cycles > 2097917ULL * 120) { printf("FAIL  demo_run: 120 s of E and only %ld ticks\n", ticks); rc = 1; break; }
        } else if ((int64_t)cpu.cycles >= stop) break;
        if (cpu.wait == 3) { printf("FAIL  demo_run: the core seized at cycle %llu\n", (unsigned long long)cpu.cycles); rc = 1; break; }
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    fclose(ft);
    if (fi) fclose(fi);
    if (sram_path) {
        f = fopen(sram_path, "w");
        if (!f) return 1;
        for (int i = 0; i < sdata_n && i < 524288; i++) fprintf(f, "%02X\n", sram[i]);
        fclose(f);
    }
    double secs = (double)(t1.tv_sec - t0.tv_sec) + (double)(t1.tv_nsec - t0.tv_nsec) * 1e-9;
    printf("demo_run: %ld ticks, %d sample bytes, progress $%02X, %llu E cycles in %.2f s host (%.1f M E cycles/s, %.0fx real time)\n",
           ticks, sdata_n, progress, (unsigned long long)cpu.cycles, secs, (double)cpu.cycles / secs / 1e6,
           (double)cpu.cycles / 2097917.0 / secs);
    return rc;
}
