/* Does the 6809 core REFUSE a 6309 opcode, and only a 6309 opcode?
 *
 * ⛔ THE CLAIM THIS EXISTS FOR IS A NEGATIVE ONE, AND CLAUDE.md's EIGHTH TRAP
 * IS ABOUT EXACTLY THAT: a negated claim that can only be satisfied by the
 * thing under test EXISTING must prove the tool ran.  So this does not merely
 * assert "no refusal on 6809 code" - it asserts a COUNT in both directions,
 * and it drives every one of the 168 6309-only encodings rather than a sample.
 *
 * It also pins the two halves together.  `hd6309_only[]` is generated from
 * `hd6309.tab`, and `cpu6809.c` consults it; if the table were regenerated and
 * the header were not, or vice versa, the counts below move.
 */
#include "../cpu6809.h"
#include "../hd6309ops.h"
#include <stdio.h>
#include <string.h>

static uint8_t mem[65536];
static uint8_t rd(void *c, uint16_t a) { (void)c; return mem[a]; }
static void wr(void *c, uint16_t a, uint8_t v) { (void)c; mem[a] = v; }

static int hits;
static int last_page;
static uint8_t last_op;
static void note(void *c, int page, uint8_t op, uint16_t pc)
{
    (void)c; (void)pc;
    hits++; last_page = page; last_op = op;
}

/* Run one instruction placed at $1000 and say whether it was refused. */
static int run_one(int page, uint8_t op)
{
    cpu6809 c;
    memset(&c, 0, sizeof c);
    c.read = rd; c.write = wr; c.undef6309 = note;
    memset(mem, 0x12, sizeof mem);          /* NOP everywhere */
    mem[0xFFFE] = 0x10; mem[0xFFFF] = 0x00;
    uint16_t p = 0x1000;
    if (page == 1) mem[p++] = 0x10;
    else if (page == 2) mem[p++] = 0x11;
    mem[p] = op;
    cpu6809_reset(&c);
    hits = 0;
    cpu6809_step(&c);
    return hits;
}

int main(void)
{
    int fail = 0, refused = 0, allowed = 0, wrongname = 0;

    for (int page = 0; page < 3; page++)
        for (int op = 0; op < 256; op++) {
            int is_only = hd6309_is_only(page, (uint8_t)op);
            /* $10 and $11 are prefixes, never opcodes in their own right. */
            if (page == 0 && (op == 0x10 || op == 0x11)) continue;
            int got = run_one(page, (uint8_t)op);
            if (is_only) {
                refused += (got > 0);
                if (!got) {
                    printf("FAIL  %s$%02X (%s) was NOT refused\n",
                           page == 0 ? "" : (page == 1 ? "$10 " : "$11 "),
                           op, hd6309_name(page, (uint8_t)op));
                    fail = 1;
                } else if (last_page != page || last_op != (uint8_t)op) {
                    wrongname++; fail = 1;
                }
            } else {
                allowed += (got == 0);
                if (got) {
                    printf("FAIL  %s$%02X was refused but is not 6309-only\n",
                           page == 0 ? "" : (page == 1 ? "$10 " : "$11 "), op);
                    fail = 1;
                }
            }
        }

    if (refused != HD6309_ONLY_COUNT) {
        printf("FAIL  refused %d of %d 6309-only encodings\n",
               refused, HD6309_ONLY_COUNT);
        fail = 1;
    }
    if (wrongname) {
        printf("FAIL  %d refusals named the wrong (page, opcode)\n", wrongname);
        fail = 1;
    }
    /* ⚠ The positive control: if the refusal were wired to "always", the line
     * above would still pass. This is what makes the negative claim real. */
    if (allowed < 400) {
        printf("FAIL  only %d non-6309 encodings ran unrefused - the refusal is too wide\n",
               allowed);
        fail = 1;
    }
    if (!fail)
        printf("ok    cpu6809 refuses %d 6309-only encodings by name, and runs %d others\n",
               refused, allowed);
    return fail;
}
