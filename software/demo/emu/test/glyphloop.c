/* Run glyphloop.asm and report E cycles between the marks.
 *
 * docs/proportional-font.md §5.3 and §5.4 estimated these by reading the source;
 * this measures them. Not a gate - a measurement - so it prints and returns 0
 * unless the program fails to run.
 */
#include "../cpu6809.h"
#include <stdio.h>
#include <string.h>

#define DONE 0x0500
#define MARK 0x0502
#define GLYPHS 40

static uint8_t mem[65536];
static cpu6809 c;
static int done;
static uint64_t at[8];

static uint8_t rd(void *x, uint16_t a) { (void)x; return mem[a]; }
static void wr(void *x, uint16_t a, uint8_t v)
{
    (void)x;
    if (a == MARK) { if (v < 8) at[v] = c.cycles; return; }
    if (a == DONE) { done = 1; return; }
    mem[a] = v;
}

int main(int argc, char **argv)
{
    if (argc < 2) { fprintf(stderr, "usage: glyphloop glyphloop.bin\n"); return 1; }
    FILE *f = fopen(argv[1], "rb");
    if (!f || fread(mem, 1, 65536, f) != 65536) { printf("FAIL  cannot read %s\n", argv[1]); return 1; }
    fclose(f);

    memset(&c, 0, sizeof c);
    c.read = rd; c.write = wr;
    cpu6309_enable(&c);
    cpu6809_reset(&c);
    for (long i = 0; i < 20000000 && !done; i++) cpu6809_step(&c);
    if (!done) { printf("FAIL  glyphloop did not finish (pc=$%04X)\n", c.pc); return 1; }

    struct { const char *what; int a, b; } runs[] = {
        { "6809, today's map (§5.3)",              1, 2 },
        { "6309 STW pairs, today's map",           3, 4 },
        { "6309 STQ+STW+STA, §5.4's re-order",     5, 6 },
    };
    printf("\n  a strike glyph, %d of them, E cycles for the CPU's own work\n\n", GLYPHS);
    printf("  %-38s %8s %8s %9s\n", "", "total", "a glyph", "µs a glyph");
    printf("  %s\n", "---------------------------------------------------------------------");
    double base = 0;
    for (unsigned i = 0; i < sizeof runs / sizeof *runs; i++) {
        double tot = (double)(at[runs[i].b] - at[runs[i].a]);
        double per = tot / GLYPHS;
        if (i == 0) base = per;
        printf("  %-38s %8.0f %8.2f %9.2f%s\n", runs[i].what, tot, per, per / 2.0979,
               i ? "" : "");
        if (i) printf("  %-38s %8s %8s %9s   (%.2f× the 6809 form)\n", "", "", "", "", base / per);
    }
    printf("\n  a 40-character line: %.2f ms of CPU, 6809; %.2f ms, 6309 re-ordered\n\n",
           (double)(at[2] - at[1]) / 2.0979 / 1000.0,
           (double)(at[6] - at[5]) / 2.0979 / 1000.0);
    return 0;
}
