/* Execute exactly one instruction at $1000 and print its E cycles.
 * Used by cyc6309.py, which compares the number with Appendix A. */
#include "../cpu6809.h"
#include <stdio.h>
#include <string.h>
static uint8_t mem[65536];
static uint8_t rd(void *c, uint16_t a) { (void)c; return mem[a]; }
static void wr(void *c, uint16_t a, uint8_t v) { (void)c; mem[a] = v; }
int main(int argc, char **argv)
{
    cpu6809 c;
    if (argc < 2) return 1;
    FILE *f = fopen(argv[1], "rb");
    if (!f || fread(mem, 1, 65536, f) != 65536) return 1;
    fclose(f);
    memset(&c, 0, sizeof c);
    c.read = rd; c.write = wr;
    cpu6309_enable(&c);
    cpu6809_reset(&c);
    c.pc = 0x1000; c.s = 0x0FF0; c.x = 0x0300; c.y = 0x0300; c.u = 0x0300;
    c.cycles = 0;
    printf("%d\n", cpu6809_step(&c));
    return 0;
}
