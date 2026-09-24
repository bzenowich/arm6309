/* hd6309.c - a complete HD6309E, beside cpu6809.c.  See hd6309.h for why it
 * is a separate core and not the 6809 with extras.
 *
 * ⭐ WHAT DECIDES WHAT.  There is no silicon on the bench yet, so every
 * behaviour here has a source, and the order of trust is:
 *
 *   1. SILICON, where it has been measured and published: hoglet67's (David
 *      Banks) logic-analyser work on real HD6309s and Tim Lindner's fuzzing,
 *      both as XRoar records them - the divides' overflow rules, the hidden
 *      M register, the illegal-instruction trap's dead cycles.  Marked
 *      [silicon] where used.
 *   2. THE 6309 BOOK (Burke & Burke), hardware/cpu/reference/: the semantics
 *      of every instruction, native mode's stacking, and every CYCLE COUNT in
 *      Appendix A, which reaches this file through test/hd6309.tab and the
 *      generated hd6309_cyc[] - the book is the only thing that says how long
 *      anything takes.
 *   3. XRoar (Ciaran Anscomb), where the book is silent: a mixed-size TFR/EXG,
 *      and the postbyte costs of indexed modes in NATIVE mode, which the book's
 *      table gives for emulation mode only.  Marked [XRoar].
 *
 * The oracle that holds this file to all of it is hardware/cpu/sim/oracle -
 * XRoar's core, fetched and built as a separate program, never copied here.
 *
 * ⭐ CYCLE COUNTS ARE TOTALS FROM THE TABLE, NOT ACCUMULATED.  `n` still walks
 * forward through every bus access so a peripheral sees each one in order at
 * a plausible cycle, but what an instruction COSTS is hd6309_cyc[][][mode]
 * plus the state-dependent part the book writes as `+`, `/` or `W`.  Adding up
 * the cycles by hand got 20 of 32 forms wrong the first time (see the old
 * version's comment, which is where cyc6309.py came from).
 */
#include "hd6309.h"
#include "hd6309ops.h"
#include <string.h>

#define CC_E 0x80
#define CC_F 0x40
#define CC_H 0x20
#define CC_I 0x10
#define CC_N 0x08
#define CC_Z 0x04
#define CC_V 0x02
#define CC_C 0x01

#define MD_NM 0x01                      /* native mode */
#define MD_FM 0x02                      /* FIRQ stacks the entire state */
#define MD_IL 0x40                      /* the last trap was an illegal instruction */
#define MD_D0 0x80                      /* ... or a division by zero */

#define VEC_TRAP 0xFFF0

/* ---- one step's context ---------------------------------------------- */

typedef struct {
    cpu6809 *c;
    int64_t base;       /* the step's first cycle */
    int n;              /* bus cycles so far - timestamps only */
    int nm;             /* native mode, sampled at the start of the step */
    int cyc;            /* what this step COSTS */
    int trap;           /* 1: take the illegal-instruction trap instead */
} S;


static inline uint8_t rd(S *s, uint16_t a)
{
    s->c->now = (uint64_t)(s->base + s->n);
    s->n++;
    return s->c->read(s->c->ctx, a);
}

static inline void wr(S *s, uint16_t a, uint8_t v)
{
    s->c->now = (uint64_t)(s->base + s->n);
    s->n++;
    s->c->write(s->c->ctx, a, v);
}

static inline uint8_t fetch8(S *s) { return rd(s, s->c->pc++); }
static inline uint16_t fetch16(S *s) { uint16_t h = fetch8(s); return (uint16_t)((h << 8) | fetch8(s)); }
static inline uint16_t rd16(S *s, uint16_t a) { uint16_t h = rd(s, a); return (uint16_t)((h << 8) | rd(s, (uint16_t)(a + 1))); }
static inline void wr16(S *s, uint16_t a, uint16_t v) { wr(s, a, (uint8_t)(v >> 8)); wr(s, (uint16_t)(a + 1), (uint8_t)v); }

/* ---- the registers -------------------------------------------------- */

static inline uint16_t getD(const cpu6809 *c) { return (uint16_t)((c->a << 8) | c->b); }
static inline void setD(cpu6809 *c, uint16_t v) { c->a = (uint8_t)(v >> 8); c->b = (uint8_t)v; }
static inline uint16_t getW(const cpu6809 *c) { return (uint16_t)((c->e << 8) | c->f); }
static inline void setW(cpu6809 *c, uint16_t v) { c->e = (uint8_t)(v >> 8); c->f = (uint8_t)v; }

/* TFR/EXG's register codes.  ⚠ A MIXED-SIZE TRANSFER IS NOT IN THE BOOK
 * ("registers of the same size"); [XRoar]: an 8-bit register reads as that
 * byte twice, and a 16-bit value written to an 8-bit register gives A, DP and
 * E its HIGH byte and B, CC and F its LOW - so TFR D,A is A's own byte and
 * TFR D,B is B's, which is the reading that makes both halves of D agree. */
int hd6309_tfr_is8(int code) { return code >= 8; }

uint16_t hd6309_tfr_get(const cpu6809 *c, int code)
{
    switch (code) {
    case 0x0: return getD(c);
    case 0x1: return c->x;
    case 0x2: return c->y;
    case 0x3: return c->u;
    case 0x4: return c->s;
    case 0x5: return c->pc;
    case 0x6: return getW(c);
    case 0x7: return c->v;
    case 0x8: return (uint16_t)((c->a << 8) | c->a);
    case 0x9: return (uint16_t)((c->b << 8) | c->b);
    case 0xA: return (uint16_t)((c->cc << 8) | c->cc);
    case 0xB: return (uint16_t)((c->dp << 8) | c->dp);
    case 0xE: return (uint16_t)((c->e << 8) | c->e);
    case 0xF: return (uint16_t)((c->f << 8) | c->f);
    default:  return 0;                          /* 12, 13: the zero register */
    }
}

void hd6309_tfr_set(cpu6809 *c, int code, uint16_t v)
{
    switch (code) {
    case 0x0: setD(c, v); break;
    case 0x1: c->x = v; break;
    case 0x2: c->y = v; break;
    case 0x3: c->u = v; break;
    case 0x4: c->s = v; break;
    case 0x5: c->pc = v; break;
    case 0x6: setW(c, v); break;
    case 0x7: c->v = v; break;
    case 0x8: c->a = (uint8_t)(v >> 8); break;
    case 0x9: c->b = (uint8_t)v; break;
    case 0xA: c->cc = (uint8_t)v; break;
    case 0xB: c->dp = (uint8_t)(v >> 8); break;
    case 0xE: c->e = (uint8_t)(v >> 8); break;
    case 0xF: c->f = (uint8_t)v; break;
    default: break;                              /* the zero register: writes vanish */
    }
}

/* ---- flags ---------------------------------------------------------- */

static inline void nz8(cpu6809 *c, uint8_t r)
{
    c->cc = (uint8_t)((c->cc & ~(CC_N | CC_Z)) | (r & 0x80 ? CC_N : 0) | (r ? 0 : CC_Z));
}
static inline void nz16(cpu6809 *c, uint16_t r)
{
    c->cc = (uint8_t)((c->cc & ~(CC_N | CC_Z)) | (r & 0x8000 ? CC_N : 0) | (r ? 0 : CC_Z));
}

/* The 8-bit ALU, by the 6809's column number: 0 SUB 1 CMP 2 SBC 4 AND 5 BIT
 * 6 LD 8 EOR 9 ADC 10 OR 11 ADD.  Returns the result; the caller stores it or
 * not. */
static uint8_t alu8(cpu6809 *c, int op, uint8_t a, uint8_t b)
{
    unsigned r;
    switch (op) {
    case 0: case 1: case 2: {
        unsigned cin = op == 2 ? (c->cc & CC_C) : 0;
        r = (unsigned)a - b - cin;
        c->cc = (uint8_t)((c->cc & ~(CC_V | CC_C)) | ((r >> 8) & 1) |
                          (((a ^ b) & (a ^ r) & 0x80) ? CC_V : 0));
        break;
    }
    case 9: case 11: {
        unsigned cin = op == 9 ? (c->cc & CC_C) : 0;
        r = (unsigned)a + b + cin;
        c->cc = (uint8_t)((c->cc & ~(CC_H | CC_V | CC_C)) | ((r >> 8) & 1) |
                          ((~(a ^ b) & (a ^ r) & 0x80) ? CC_V : 0) |
                          (((a ^ b ^ r) & 0x10) ? CC_H : 0));
        break;
    }
    case 4: case 5: r = a & b; c->cc &= ~CC_V; break;
    case 6:         r = b;     c->cc &= ~CC_V; break;
    case 8:         r = a ^ b; c->cc &= ~CC_V; break;
    case 10:        r = a | b; c->cc &= ~CC_V; break;
    default:        r = 0; break;
    }
    nz8(c, (uint8_t)r);
    return (uint8_t)r;
}

/* The 16-bit ALU: 0 SUB 1 CMP 2 SBC 4 AND 5 BIT 6 LD 8 EOR 9 ADC 10 OR 11 ADD. */
static uint16_t alu16(cpu6809 *c, int op, uint16_t a, uint16_t b)
{
    uint32_t r;
    switch (op) {
    case 0: case 1: case 2: {
        unsigned cin = op == 2 ? (c->cc & CC_C) : 0;
        r = (uint32_t)a - b - cin;
        c->cc = (uint8_t)((c->cc & ~(CC_V | CC_C)) | ((r >> 16) & 1) |
                          (((a ^ b) & (a ^ r) & 0x8000) ? CC_V : 0));
        break;
    }
    case 9: case 11: {
        unsigned cin = op == 9 ? (c->cc & CC_C) : 0;
        r = (uint32_t)a + b + cin;
        c->cc = (uint8_t)((c->cc & ~(CC_V | CC_C)) | ((r >> 16) & 1) |
                          ((~(a ^ b) & (a ^ r) & 0x8000) ? CC_V : 0));
        break;
    }
    case 4: case 5: r = a & b; c->cc &= ~CC_V; break;
    case 6:         r = b;     c->cc &= ~CC_V; break;
    case 8:         r = a ^ b; c->cc &= ~CC_V; break;
    case 10:        r = a | b; c->cc &= ~CC_V; break;
    default:        r = 0; break;
    }
    nz16(c, (uint16_t)r);
    return (uint16_t)r;
}

/* The unary ops, by the 6809's low nibble: 0 NEG 3 COM 4 LSR 6 ROR 7 ASR 8 ASL
 * 9 ROL 10 DEC 12 INC 13 TST 15 CLR.  `w` is the width in bits, 8 or 16. */
static uint16_t unary(cpu6809 *c, int op, uint16_t a, int w)
{
    const uint16_t top = (uint16_t)(1u << (w - 1)), mask = (uint16_t)((1u << w) - 1);
    uint16_t r = a;
    uint8_t cc = c->cc;
    switch (op) {
    case 0:  r = (uint16_t)(-a & mask);
             cc = (uint8_t)((cc & ~(CC_V | CC_C)) | (r ? CC_C : 0) | (a == top ? CC_V : 0)); break;
    case 3:  r = (uint16_t)(~a & mask); cc = (uint8_t)((cc & ~CC_V) | CC_C); break;
    case 4:  r = (uint16_t)(a >> 1); cc = (uint8_t)((cc & ~CC_C) | (a & 1)); break;
    case 6:  r = (uint16_t)((a >> 1) | ((cc & CC_C) ? top : 0)); cc = (uint8_t)((cc & ~CC_C) | (a & 1)); break;
    case 7:  r = (uint16_t)((a >> 1) | (a & top)); cc = (uint8_t)((cc & ~CC_C) | (a & 1)); break;
    case 8:  r = (uint16_t)((a << 1) & mask);
             cc = (uint8_t)((cc & ~(CC_V | CC_C)) | ((a & top) ? CC_C : 0) | (((a ^ (a << 1)) & top) ? CC_V : 0)); break;
    case 9:  r = (uint16_t)(((a << 1) | (cc & CC_C)) & mask);
             cc = (uint8_t)((cc & ~(CC_V | CC_C)) | ((a & top) ? CC_C : 0) | (((a ^ (a << 1)) & top) ? CC_V : 0)); break;
    case 10: r = (uint16_t)((a - 1) & mask); cc = (uint8_t)((cc & ~CC_V) | (a == top ? CC_V : 0)); break;
    case 12: r = (uint16_t)((a + 1) & mask); cc = (uint8_t)((cc & ~CC_V) | (a == (uint16_t)(top - 1) ? CC_V : 0)); break;
    case 13: r = a; cc &= (uint8_t)~CC_V; break;
    case 15: r = 0; cc &= (uint8_t)~(CC_V | CC_C); break;
    default: break;
    }
    c->cc = cc;
    if (w == 8) nz8(c, (uint8_t)r); else nz16(c, r);
    /* ⚠ LSR clears N whatever the width - nz sees a zero top bit already. */
    return r;
}

/* ---- the stack ------------------------------------------------------ */

static void push8(S *s, uint16_t *sp, uint8_t v) { wr(s, --*sp, v); }
static void push16(S *s, uint16_t *sp, uint16_t v) { push8(s, sp, (uint8_t)v); push8(s, sp, (uint8_t)(v >> 8)); }
static uint8_t pull8(S *s, uint16_t *sp) { return rd(s, (*sp)++); }
static uint16_t pull16(S *s, uint16_t *sp) { uint16_t h = pull8(s, sp); return (uint16_t)((h << 8) | pull8(s, sp)); }

/* PSHS/PSHU/PULS/PULU's postbyte, PC first on the way down; returns bytes. */
static int push_mask(S *s, uint8_t m, int onU)
{
    cpu6809 *c = s->c;
    uint16_t *sp = onU ? &c->u : &c->s;
    int k = 0;
    if (m & 0x80) { push16(s, sp, c->pc); k += 2; }
    if (m & 0x40) { push16(s, sp, onU ? c->s : c->u); k += 2; }
    if (m & 0x20) { push16(s, sp, c->y); k += 2; }
    if (m & 0x10) { push16(s, sp, c->x); k += 2; }
    if (m & 0x08) { push8(s, sp, c->dp); k++; }
    if (m & 0x04) { push8(s, sp, c->b); k++; }
    if (m & 0x02) { push8(s, sp, c->a); k++; }
    if (m & 0x01) { push8(s, sp, c->cc); k++; }
    return k;
}

static int pull_mask(S *s, uint8_t m, int onU)
{
    cpu6809 *c = s->c;
    uint16_t *sp = onU ? &c->u : &c->s;
    int k = 0;
    if (m & 0x01) { c->cc = pull8(s, sp); k++; }
    if (m & 0x02) { c->a = pull8(s, sp); k++; }
    if (m & 0x04) { c->b = pull8(s, sp); k++; }
    if (m & 0x08) { c->dp = pull8(s, sp); k++; }
    if (m & 0x10) { c->x = pull16(s, sp); k += 2; }
    if (m & 0x20) { c->y = pull16(s, sp); k += 2; }
    if (m & 0x40) { uint16_t v = pull16(s, sp); if (onU) c->s = v; else c->u = v; k += 2; }
    if (m & 0x80) { c->pc = pull16(s, sp); k += 2; }
    return k;
}

/* ⭐ THE ENTIRE STATE, and NATIVE MODE ADDS W: the book (4.7) - "PC, U, Y, X,
 * DP, F, E, B, A, CC" pushed, so W sits between DP and B in memory. */
static void push_entire(S *s)
{
    cpu6809 *c = s->c;
    push16(s, &c->s, c->pc);
    push16(s, &c->s, c->u);
    push16(s, &c->s, c->y);
    push16(s, &c->s, c->x);
    push8(s, &c->s, c->dp);
    if (s->nm) { push8(s, &c->s, c->f); push8(s, &c->s, c->e); }
    push8(s, &c->s, c->b);
    push8(s, &c->s, c->a);
    push8(s, &c->s, c->cc);
}

static void vector(S *s, uint16_t v, uint8_t mask)
{
    cpu6809 *c = s->c;
    c->cc |= mask;
    c->pc = rd16(s, v);
}

/* ---- effective addresses -------------------------------------------- */

/* ⭐ THE POSTBYTE'S OWN COST, per postbyte, in each mode: Burke & Burke's
 * "Addendum to The 6309 Book: Indexed Addressing Mode Post Bytes" - which
 * corrects the book's own A-12 ([E,R] is 4, not 7; W,R is 1, not 4) and is the
 * only published source for NATIVE mode, which Hitachi never documented.
 * Transcribed from hoglet67's 6809Decoder, which carries it and validated it
 * against silicon; oracle/checkcyc.py fetches that file and requires these two
 * tables to equal it, all 512 entries.  ⛔ NEGATIVE MEANS UNDEFINED: the seven
 * postbytes a 6309 does not decode ([,-R] in four registers, and $BF $DF $FF)
 * take the illegal-instruction trap. */
static const int8_t IX_EM[256] = {
      1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,   /* 0x */
      1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,   /* 1x */
      1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,   /* 2x */
      1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,   /* 3x */
      1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,   /* 4x */
      1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,   /* 5x */
      1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,   /* 6x */
      1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,   /* 7x */
      2,  3,  2,  3,  0,  1,  1,  1,  1,  4,  1,  4,  1,  5,  1,  0,   /* 8x */
      3,  6,-21,  6,  3,  4,  4,  4,  4,  7,  4,  7,  4,  8,  4,  5,   /* 9x */
      2,  3,  2,  3,  0,  1,  1,  1,  1,  4,  1,  4,  1,  5,  1,  2,   /* Ax */
      5,  6,-21,  6,  3,  4,  4,  4,  4,  7,  4,  7,  4,  8,  4,-21,   /* Bx */
      2,  3,  2,  3,  0,  1,  1,  1,  1,  4,  1,  4,  1,  5,  1,  1,   /* Cx */
      4,  6,-21,  6,  3,  4,  4,  4,  4,  7,  4,  7,  4,  8,  4,-21,   /* Dx */
      2,  3,  2,  3,  0,  1,  1,  1,  1,  4,  1,  4,  1,  5,  1,  1,   /* Ex */
      4,  6,-21,  6,  3,  4,  4,  4,  4,  7,  4,  7,  4,  8,  4,-21,   /* Fx */
};

static const int8_t IX_NM[256] = {
      1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,   /* 0x */
      1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,   /* 1x */
      1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,   /* 2x */
      1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,   /* 3x */
      1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,   /* 4x */
      1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,   /* 5x */
      1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,   /* 6x */
      1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,   /* 7x */
      1,  2,  1,  2,  0,  1,  1,  1,  1,  3,  1,  2,  1,  3,  1,  0,   /* 8x */
      3,  5,-23,  5,  3,  4,  4,  4,  4,  6,  4,  5,  4,  6,  4,  4,   /* 9x */
      1,  2,  1,  2,  0,  1,  1,  1,  1,  3,  1,  2,  1,  3,  1,  2,   /* Ax */
      5,  5,-23,  5,  3,  4,  4,  4,  4,  6,  4,  5,  4,  6,  4,-23,   /* Bx */
      1,  2,  1,  2,  0,  1,  1,  1,  1,  3,  1,  2,  1,  3,  1,  1,   /* Cx */
      4,  5,-23,  5,  3,  4,  4,  4,  4,  6,  4,  5,  4,  6,  4,-23,   /* Dx */
      1,  2,  1,  2,  0,  1,  1,  1,  1,  3,  1,  2,  1,  3,  1,  1,   /* Ex */
      4,  5,-23,  5,  3,  4,  4,  4,  4,  6,  4,  5,  4,  6,  4,-23,   /* Fx */
};

static uint16_t ea_indexed(S *s)
{
    cpu6809 *c = s->c;
    uint8_t pb = fetch8(s);
    int cost = (s->nm ? IX_NM : IX_EM)[pb];
    uint16_t *rp, ea = 0;
    if (cost < 0) { s->trap = 1; return 0; }
    s->cyc += cost;
    switch ((pb >> 5) & 3) {
    case 0: rp = &c->x; break;
    case 1: rp = &c->y; break;
    case 2: rp = &c->u; break;
    default: rp = &c->s; break;
    }
    if (!(pb & 0x80)) {                               /* n5,R */
        int o = pb & 0x1F;
        if (o & 0x10) o -= 0x20;
        return (uint16_t)(*rp + o);
    }
    int ind = (pb >> 4) & 1;
    switch (pb & 0x0F) {
    case 0x0:
        if (ind) {                                    /* $90 $B0 $D0 $F0: the W modes, indirect */
            uint16_t w = getW(c);
            switch ((pb >> 5) & 3) {
            case 0: ea = w; break;
            case 1: ea = (uint16_t)(w + fetch16(s)); break;
            case 2: ea = w; setW(c, (uint16_t)(w + 2)); break;
            default: setW(c, (uint16_t)(w - 2)); ea = getW(c); break;
            }
        } else { ea = *rp; *rp = (uint16_t)(*rp + 1); }
        break;
    case 0x1: ea = *rp; *rp = (uint16_t)(*rp + 2); break;
    case 0x2: *rp = (uint16_t)(*rp - 1); ea = *rp; break;
    case 0x3: *rp = (uint16_t)(*rp - 2); ea = *rp; break;
    case 0x4: ea = *rp; break;
    case 0x5: ea = (uint16_t)(*rp + (int8_t)c->b); break;
    case 0x6: ea = (uint16_t)(*rp + (int8_t)c->a); break;
    case 0x7: ea = (uint16_t)(*rp + (int8_t)c->e); break;
    case 0x8: ea = (uint16_t)(*rp + (int8_t)fetch8(s)); break;
    case 0x9: ea = (uint16_t)(*rp + fetch16(s)); break;
    case 0xA: ea = (uint16_t)(*rp + (int8_t)c->f); break;
    case 0xB: ea = (uint16_t)(*rp + getD(c)); break;
    case 0xC: { int8_t o = (int8_t)fetch8(s); ea = (uint16_t)(c->pc + o); break; }
    case 0xD: { uint16_t o = fetch16(s); ea = (uint16_t)(c->pc + o); break; }
    case 0xE: ea = (uint16_t)(*rp + getW(c)); break;
    default:                                          /* $x F */
        if (ind) { ea = fetch16(s); break; }          /* $9F: [n16] */
        {                                             /* $8F $AF $CF $EF: the W modes */
            uint16_t w = getW(c);
            switch ((pb >> 5) & 3) {
            case 0: ea = w; break;
            case 1: ea = (uint16_t)(w + fetch16(s)); break;
            case 2: ea = w; setW(c, (uint16_t)(w + 2)); break;
            default: setW(c, (uint16_t)(w - 2)); ea = getW(c); break;
            }
        }
        break;
    }
    if (ind) ea = rd16(s, ea);
    return ea;
}

/* The operand's address for a DIR, IDX or EXT form - the mode from the
 * opcode's column, which hd6309_mode[] also records. */
static uint16_t ea_of(S *s, int mode)
{
    cpu6809 *c = s->c;
    switch (mode) {
    case HM_DIR: return (uint16_t)((c->dp << 8) | fetch8(s));
    case HM_EXT: return fetch16(s);
    default:     return ea_indexed(s);
    }
}

/* Read an 8- or 16-bit operand in IMM, DIR, IDX or EXT. */
static uint8_t opnd8(S *s, int mode)
{
    if (mode == HM_IMM) return fetch8(s);
    uint16_t ea = ea_of(s, mode);
    if (s->trap) return 0;
    return rd(s, ea);
}
static uint16_t opnd16(S *s, int mode)
{
    if (mode == HM_IMM) return fetch16(s);
    uint16_t ea = ea_of(s, mode);
    if (s->trap) return 0;
    return rd16(s, ea);
}

/* ---- TFM ------------------------------------------------------------ */

static const struct { int si, di; } tfm_form[4] = {
    { +1, +1 },   /* $1138  TFM r+,r+  forward block move          */
    { -1, -1 },   /* $1139  TFM r-,r-  backward block move         */
    { +1,  0 },   /* $113A  TFM r+,r   output to a peripheral      */
    {  0, +1 },   /* $113B  TFM r,r+   input from a peripheral     */
};

/* ⭐ plan.md §4.3.1 - DECIDED 2026-09-21, and it is a DECISION, not a model of
 * silicon: the byte in flight is STORED, both pointers advance and W
 * decrements BEFORE an interrupt is recognised, so on resume nothing is
 * re-read and nothing written twice.  A real HD63C09E re-reads the source on
 * the fixed-source form and loses the byte (the book, the TFM page); this
 * machine's 6309 is the project's own firmware and does not.  ⛔ So a TFM with
 * an interrupt in it is the one place this core and the oracle are REQUIRED to
 * differ.  HD6309_FAITHFUL_TFM builds silicon's behaviour, and
 * test/tfm6309.c requires that build to fail.  Returns the bytes moved. */
static int tfm_run(S *s, int form, uint16_t opc_pc)
{
    cpu6809 *c = s->c;
    uint8_t pb = fetch8(s);
    int sc = (pb >> 4) & 15, dc = pb & 15, k = 0;
    if (sc > 4 || dc > 4) { s->trap = 1; return 0; }  /* only D X Y U S are pointers */
    uint16_t regs[5] = { getD(c), c->x, c->y, c->u, c->s };
    uint16_t *sp = &regs[sc], *dp = &regs[dc];
    s->n += 3;                                          /* 6 + 3W: three past the three fetches */
    while (getW(c) != 0) {
        uint8_t v = rd(s, *sp);
#ifdef HD6309_FAITHFUL_TFM
        if (cpu6809_int_pending(c, s->base + s->n)) {
            c->pc = opc_pc;
            goto out;
        }
#endif
        s->c->m = v;
        wr(s, *dp, v);
        s->n++;
        *sp = (uint16_t)(*sp + tfm_form[form].si);
        if (dp != sp) *dp = (uint16_t)(*dp + tfm_form[form].di);
        setW(c, (uint16_t)(getW(c) - 1));
        k++;
        if (getW(c) != 0 && cpu6809_int_pending(c, s->base + s->n)) {
            c->pc = opc_pc;                            /* re-entered after the interrupt */
            goto out;
        }
    }
    /* ⭐ W is 0 here, always, and NitrOS-9 depends on it (6309.md §5.1.5);
     * and the book's TFM page: "Z' - Always set". */
    c->cc |= CC_Z;
out:
    setD(c, regs[0]); c->x = regs[1]; c->y = regs[2]; c->u = regs[3]; c->s = regs[4];
    return k;
}

/* ---- the bit operations, $1130-$1137 ---------------------------------- */

static void bitop(S *s, int op)
{
    cpu6809 *c = s->c;
    uint8_t pb = fetch8(s);
    uint16_t ea = (uint16_t)((c->dp << 8) | fetch8(s));
    int reg = pb >> 6, mb = (pb >> 3) & 7, rb = pb & 7;
    uint8_t *r;
    switch (reg) {
    case 0: r = &c->cc; break;
    case 1: r = &c->a; break;
    case 2: r = &c->b; break;
    default: s->trap = 1; return;
    }
    uint8_t m = rd(s, ea);
    int mbit = (m >> mb) & 1, rbit = (*r >> rb) & 1, out;
    switch (op) {
    case 0: out = rbit & mbit; break;               /* BAND  */
    case 1: out = rbit & !mbit; break;              /* BIAND */
    case 2: out = rbit | mbit; break;               /* BOR   */
    case 3: out = rbit | !mbit; break;              /* BIOR  */
    case 4: out = rbit ^ mbit; break;               /* BEOR  */
    case 5: out = rbit ^ !mbit; break;              /* BIEOR */
    case 6: out = mbit; break;                      /* LDBT  */
    default:                                        /* STBT: the memory bit */
        /* ⚠ BITS 5..3 ARE THE SOURCE AND 2..0 THE DESTINATION, whichever is
         * memory: for STBT the register bit is the source (hoglet67, and the
         * bytes lwasm emits for `stbt a,4,1,<$17`: postbyte $61). */
        rbit = (*r >> mb) & 1;
        m = (uint8_t)((m & ~(1 << rb)) | (rbit << rb));
        wr(s, ea, m);
        return;
    }
    *r = (uint8_t)((*r & ~(1 << rb)) | (out << rb));
}

/* ---- the traps -------------------------------------------------------- */

/* The illegal-instruction trap and the divide-by-zero trap share $FFF0 and are
 * told apart by BITMD.  The entire state is stacked, native mode's W included.
 * `total` is what the whole instruction costs, trap and all: [silicon] 20/22
 * for an undefined opcode and 21/23 behind a prefix (hoglet67's table). */
static void take_trap(S *s, uint8_t mdbit, int total)
{
    cpu6809 *c = s->c;
    c->md |= mdbit;
    c->cc |= CC_E;
    push_entire(s);
    vector(s, VEC_TRAP, CC_F | CC_I);
    s->cyc = total;
}

/* ---- interrupts ------------------------------------------------------- */

static int interrupt(S *s, int type)
{
    cpu6809 *c = s->c;
    c->took_int = 1;
    int entire = type != CPU6809_FIRQ || (c->md & MD_FM);
    if (type == CPU6809_NMI) c->nmi_latched = 0;
    if (entire) {
        c->cc |= CC_E;
        push_entire(s);
    } else {
        c->cc &= (uint8_t)~CC_E;
        push16(s, &c->s, c->pc);
        push8(s, &c->s, c->cc);
    }
    switch (type) {
    case CPU6809_NMI:  vector(s, 0xFFFC, CC_F | CC_I); break;
    case CPU6809_FIRQ: vector(s, 0xFFF6, CC_F | CC_I); break;
    default:           vector(s, 0xFFF8, CC_I); break;
    }
    /* IRQ/NMI 19 in emulation, and native mode's two bytes of W cost two. */
    return entire ? (s->nm ? 21 : 19) : 10;
}

/* ⭐ THE LINES, THE DATASHEET'S WAY: an interrupt is taken at a boundary if
 * its line was asserted by the START OF THE LAST CYCLE of the instruction
 * before - sampled in that cycle.  So IRQ and FIRQ read the line at
 * `base - 1`, and an NMI edge counts once it is a cycle old.  cpu6809.c's
 * `base - 2` is mc6809i.v's, one cycle more conservative and that Verilog
 * core's own; this machine's 6309 is the project's firmware, and the oracle
 * samples as this does. */
#define SAMPLE 1
static void nmi_resolve(cpu6809 *c, int64_t base)
{
    if (c->nmi_edge && c->nmi_edge_t + SAMPLE <= base) {
        c->nmi_edge = 0;
        if (c->nmi_armed) c->nmi_latched = 1;
    }
}

/* One cycle of CWAI's wait or SYNC's, as cpu6809.c's wait_step does. */
static int wait_step(S *s)
{
    cpu6809 *c = s->c;
    int firq = cpu6809_line_at(c, CPU6809_FIRQ, s->base - SAMPLE);
    int irq = cpu6809_line_at(c, CPU6809_IRQ, s->base - SAMPLE);
    nmi_resolve(c, s->base);
    if (c->wait == 2) {                               /* SYNC */
        if (c->nmi_latched || firq || irq) { c->wait = 0; return 2; }
        return 1;
    }
    /* CWAI: the state is already stacked; only the vector remains. */
    uint16_t v;
    uint8_t mask;
    if (c->nmi_latched) { c->nmi_latched = 0; v = 0xFFFC; mask = CC_F | CC_I; }
    else if (firq && !(c->cc & CC_F)) { v = 0xFFF6; mask = CC_F | CC_I; }
    else if (irq && !(c->cc & CC_I)) { v = 0xFFF8; mask = CC_I; }
    else return 1;
    c->wait = 0;
    vector(s, v, mask);
    /* the vector's two reads and nothing else: [XRoar] - the book gives CWAI
     * as ">=20" and silicon has not been asked how the wake is split */
    return 2;
}

/* ---- the step ------------------------------------------------------- */

static int exec_page0(S *s, uint8_t op, uint16_t opc_pc);
static int exec_page1(S *s, uint8_t op);
static int exec_page2(S *s, uint8_t op, uint16_t opc_pc);

int hd6309_step(cpu6809 *c)
{
    S st = { c, (int64_t)c->cycles, 0, c->md & MD_NM, 0, 0 };
    S *s = &st;
    const uint16_t s0 = c->s;
    int page = 0;
    uint8_t op;
    uint16_t opc_pc;

    c->took_int = 0;
    cpu6809_sync_lines(c, s->base);
    if (c->wait) { s->cyc = wait_step(s); goto done; }

    nmi_resolve(c, s->base);
    if (c->nmi_latched) { s->cyc = interrupt(s, CPU6809_NMI); goto done; }
    if (!(c->cc & CC_F) && cpu6809_line_at(c, CPU6809_FIRQ, s->base - SAMPLE)) { s->cyc = interrupt(s, CPU6809_FIRQ); goto done; }
    if (!(c->cc & CC_I) && cpu6809_line_at(c, CPU6809_IRQ, s->base - SAMPLE)) { s->cyc = interrupt(s, CPU6809_IRQ); goto done; }

    opc_pc = c->pc;
    op = fetch8(s);
    /* ⚠ ONE PREFIX.  A second $10/$11 after the first is, on a 6309, the
     * instruction byte of an undefined encoding - and so a trap below. */
    if (op == 0x10 || op == 0x11) { page = op == 0x10 ? 1 : 2; op = fetch8(s); }
    if (!hd6309_is_defined(page, op)) {
        take_trap(s, MD_IL, (s->nm ? 22 : 20) + (page != 0));
        goto done;
    }
    s->cyc = hd6309_cyc[page][op][s->nm];
    switch (page) {
    case 0:  exec_page0(s, op, opc_pc); break;
    case 1:  exec_page1(s, op); break;
    default: exec_page2(s, op, opc_pc); break;
    }
    /* An undefined postbyte, or TFM's or a bit op's register: [hoglet67,
     * "TODO: validate actual"] the bytes fetched so far and then 21/23. */
    if (s->trap) take_trap(s, MD_IL, s->n + (s->nm ? 23 : 21));

done:
    if (s->cyc < s->n) s->cyc = s->n;                 /* never less than the bus it used */
    c->cycles += (uint64_t)s->cyc;
    if (c->s != s0) c->nmi_armed = 1;
    return s->cyc;
}

/* The 6809 rows every page shares: a column's operand mode. */
static int col_mode(uint8_t op)
{
    switch (op >> 4) {
    case 0x0: case 0x9: case 0xD: return HM_DIR;
    case 0x6: case 0xA: case 0xE: return HM_IDX;
    case 0x7: case 0xB: case 0xF: return HM_EXT;
    default: return HM_IMM;
    }
}

static int branch_taken(uint8_t cc, int cond)
{
    int n = (cc >> 3) & 1, v = (cc >> 1) & 1, z = (cc >> 2) & 1, cy = cc & 1;
    switch (cond) {
    case 0x0: return 1;
    case 0x1: return 0;
    case 0x2: return !(z | cy);
    case 0x3: return z | cy;
    case 0x4: return !cy;
    case 0x5: return cy;
    case 0x6: return !z;
    case 0x7: return z;
    case 0x8: return !v;
    case 0x9: return v;
    case 0xA: return !n;
    case 0xB: return n;
    case 0xC: return !(n ^ v);
    case 0xD: return n ^ v;
    case 0xE: return !(n ^ v) && !z;
    default:  return (n ^ v) || z;
    }
}

/* Read-modify-write on memory, $00-$0F / $60-$6F / $70-$7F, the 6309's
 * AIM/OIM/EIM/TIM among them. */
static void rmw_mem(S *s, uint8_t op)
{
    cpu6809 *c = s->c;
    int lo = op & 15, mode = col_mode(op);
    if (lo == 1 || lo == 2 || lo == 5 || lo == 0xB) {  /* OIM AIM EIM TIM: #imm first */
        uint8_t im = fetch8(s);
        s->c->m = im;                                     /* [silicon] */
        uint16_t ea = ea_of(s, mode);
        if (s->trap) return;
        uint8_t v = rd(s, ea), r;
        switch (lo) {
        case 1:  r = v | im; break;
        case 5:  r = v ^ im; break;
        default: r = v & im; break;
        }
        c->cc &= (uint8_t)~CC_V;
        nz8(c, r);
        if (lo != 0xB) wr(s, ea, r);
        return;
    }
    uint16_t ea = ea_of(s, mode);
    if (s->trap) return;
    if (lo == 0xE) { c->pc = ea; return; }             /* JMP */
    uint8_t v = lo == 0xF ? 0 : rd(s, ea);
    if (lo == 0xF) rd(s, ea);                          /* CLR reads it first, as a 6809 does */
    uint8_t r = (uint8_t)unary(c, lo, v, 8);
    if (lo != 0xD) { s->c->m = r; wr(s, ea, r); }
}

static int exec_page0(S *s, uint8_t op, uint16_t opc_pc)
{
    cpu6809 *c = s->c;
    (void)opc_pc;
    uint16_t t;
    uint8_t b;
    switch (op >> 4) {
    case 0x0: case 0x6: case 0x7:
        rmw_mem(s, op);
        return 0;
    case 0x4: case 0x5: {
        uint8_t *r = (op >> 4) == 4 ? &c->a : &c->b;
        *r = (uint8_t)unary(c, op & 15, *r, 8);
        return 0;
    }
    case 0x2:
        b = fetch8(s);
        if (branch_taken(c->cc, op & 15)) c->pc = (uint16_t)(c->pc + (int8_t)b);
        return 0;
    default: break;
    }
    switch (op) {
    case 0x12: return 0;                                                   /* NOP */
    case 0x13:                                                             /* SYNC */
        /* A line already up ends it at once, at the book's minimum (4/3,
         * which silicon's table agrees with); only otherwise does it wait. */
        if (!(c->irq || c->firq || c->nmi_latched || c->nmi_edge)) c->wait = 2;
        return 0;
    case 0x14:                                                             /* SEXW */
        setD(c, (c->e & 0x80) ? 0xFFFF : 0x0000);
        /* ⚠ the flags are of the 32-bit result, Q */
        c->cc = (uint8_t)((c->cc & ~(CC_N | CC_Z)) | (c->e & 0x80 ? CC_N : 0) |
                          ((getD(c) | getW(c)) ? 0 : CC_Z));
        return 0;
    case 0x16: t = fetch16(s); c->pc = (uint16_t)(c->pc + t); return 0;   /* LBRA */
    case 0x17: t = fetch16(s); push16(s, &c->s, c->pc); c->pc = (uint16_t)(c->pc + t); return 0;  /* LBSR */
    case 0x19: {                                                           /* DAA */
        /* [silicon] hoglet67, on an exhaustive test: C is only ever set, V is
         * bit 7 of the sum XOR C, and - "not widely known" - with C set and A
         * in $80..$99 a 6309 corrects by a different amount than a 6809 does
         * ($80 becomes $00, not $E0). */
        unsigned a = c->a, h = (c->cc & CC_H) != 0, cy = c->cc & CC_C, cor = 0;
        if (h || (a & 0x0F) > 9) cor |= 0x06;
        if (cy || (a & 0xF0) > 0x90 || ((a & 0xF0) > 0x80 && (a & 0x0F) > 9)) cor |= 0x60;
        if (cy && a >= 0x80 && a <= 0x99) {
            if (a == 0x99) cor = 0x68 - h;
            else if (a == 0x98) cor = 0x68;
            else if (a >= 0x90) cor += 0x10;
            else cor += 0x20;
        }
        unsigned r = a + cor;
        cy |= (r >> 8) & 1;
        c->a = (uint8_t)r;
        c->cc = (uint8_t)((c->cc & ~(CC_V | CC_C)) | cy | ((((r >> 7) & 1) ^ cy) ? CC_V : 0));
        nz8(c, c->a);
        return 0;
    }
    case 0x1A: c->cc |= fetch8(s); return 0;                               /* ORCC */
    case 0x1C: c->cc &= fetch8(s); return 0;                               /* ANDCC */
    case 0x1D:                                                             /* SEX */
        /* [silicon] N and Z of B - which is the same as of D - and V is NOT
         * cleared, "contrary to some documentation" (hoglet67's tests). */
        c->a = (c->b & 0x80) ? 0xFF : 0x00;
        nz8(c, c->b);
        return 0;
    case 0x1E: {                                                           /* EXG */
        b = fetch8(s);
        uint16_t va = hd6309_tfr_get(c, b >> 4), vb = hd6309_tfr_get(c, b & 15);
        hd6309_tfr_set(c, b >> 4, vb);
        hd6309_tfr_set(c, b & 15, va);
        return 0;
    }
    case 0x1F:                                                             /* TFR */
        b = fetch8(s);
        hd6309_tfr_set(c, b & 15, hd6309_tfr_get(c, b >> 4));
        return 0;
    case 0x30: case 0x31: case 0x32: case 0x33: {                          /* LEAX Y S U */
        t = ea_indexed(s);
        if (s->trap) return 0;
        switch (op & 3) {
        case 0: c->x = t; c->cc = (uint8_t)((c->cc & ~CC_Z) | (t ? 0 : CC_Z)); break;
        case 1: c->y = t; c->cc = (uint8_t)((c->cc & ~CC_Z) | (t ? 0 : CC_Z)); break;
        case 2: c->s = t; break;
        default: c->u = t; break;
        }
        return 0;
    }
    case 0x34: case 0x36: b = fetch8(s); s->cyc += push_mask(s, b, op == 0x36); return 0;   /* PSHS PSHU */
    case 0x35: case 0x37: b = fetch8(s); s->cyc += pull_mask(s, b, op == 0x37); return 0;   /* PULS PULU */
    case 0x39: c->pc = pull16(s, &c->s); return 0;                        /* RTS */
    case 0x3A: c->x = (uint16_t)(c->x + c->b); return 0;                  /* ABX */
    case 0x3B:                                                             /* RTI */
        c->cc = pull8(s, &c->s);
        if (c->cc & CC_E) {
            c->a = pull8(s, &c->s);
            c->b = pull8(s, &c->s);
            if (s->nm) { c->e = pull8(s, &c->s); c->f = pull8(s, &c->s); }
            c->dp = pull8(s, &c->s);
            c->x = pull16(s, &c->s);
            c->y = pull16(s, &c->s);
            c->u = pull16(s, &c->s);
            s->cyc = s->nm ? 17 : 15;
        }
        c->pc = pull16(s, &c->s);
        return 0;
    case 0x3C:                                                             /* CWAI */
        c->cc &= fetch8(s);
        c->cc |= CC_E;
        push_entire(s);
        c->wait = 1;
        return 0;
    case 0x3D: {                                                           /* MUL */
        s->c->m = c->b;                                                      /* [silicon] */
        uint16_t r = (uint16_t)(c->a * c->b);
        setD(c, r);
        c->cc = (uint8_t)((c->cc & ~(CC_Z | CC_C)) | (r ? 0 : CC_Z) | ((r >> 7) & 1));
        return 0;
    }
    case 0x3F:                                                             /* SWI */
        c->cc |= CC_E;
        push_entire(s);
        vector(s, 0xFFFA, CC_F | CC_I);
        return 0;
    case 0x8D: b = fetch8(s); push16(s, &c->s, c->pc); c->pc = (uint16_t)(c->pc + (int8_t)b); return 0;  /* BSR */
    case 0x9D: case 0xAD: case 0xBD:                                       /* JSR */
        t = ea_of(s, col_mode(op));
        if (s->trap) return 0;
        push16(s, &c->s, c->pc);
        c->pc = t;
        return 0;
    case 0xCD: {                                                           /* LDQ # */
        uint16_t hi = fetch16(s), lo = fetch16(s);
        setD(c, hi); setW(c, lo);
        /* [silicon] V is NOT cleared - hoglet67's random testing */
        c->cc = (uint8_t)((c->cc & ~(CC_N | CC_Z)) | (hi & 0x8000 ? CC_N : 0) |
                          ((hi | lo) ? 0 : CC_Z));
        return 0;
    }
    default: break;
    }
    /* $80-$FF: the accumulator rows */
    {
        int lo = op & 15, mode = col_mode(op);
        int isB = op >= 0xC0;
        uint8_t *acc = isB ? &c->b : &c->a;
        if (lo == 7) {                                                     /* STA STB */
            t = ea_of(s, mode);
            if (s->trap) return 0;
            wr(s, t, *acc);
            c->cc &= (uint8_t)~CC_V;
            nz8(c, *acc);
            return 0;
        }
        if (lo == 3 || lo == 0xC || lo == 0xE) {                           /* SUBD ADDD CMPX LDD LDX LDU */
            uint16_t v = opnd16(s, mode);
            if (s->trap) return 0;
            if (lo == 3) { if (isB) setD(c, alu16(c, 11, getD(c), v)); else setD(c, alu16(c, 0, getD(c), v)); }
            else if (lo == 0xC) { if (isB) setD(c, alu16(c, 6, 0, v)); else alu16(c, 1, c->x, v); }
            else { if (isB) c->u = alu16(c, 6, 0, v); else c->x = alu16(c, 6, 0, v); }
            return 0;
        }
        if (lo == 0xD || lo == 0xF) {                                      /* STD STX STU */
            t = ea_of(s, mode);
            if (s->trap) return 0;
            uint16_t v = lo == 0xD ? getD(c) : (isB ? c->u : c->x);
            wr16(s, t, v);
            c->cc &= (uint8_t)~CC_V;
            nz16(c, v);
            return 0;
        }
        uint8_t v = opnd8(s, mode);
        if (s->trap) return 0;
        uint8_t r = alu8(c, lo, *acc, v);
        if (lo != 1 && lo != 5) *acc = r;
        return 0;
    }
}

static int exec_page1(S *s, uint8_t op)
{
    cpu6809 *c = s->c;
    uint16_t t;
    if (op >= 0x21 && op <= 0x2F) {                                        /* long branches */
        t = fetch16(s);
        if (branch_taken(c->cc, op & 15)) {
            c->pc = (uint16_t)(c->pc + t);
            if (!s->nm) s->cyc++;                                          /* the book's `5/6` */
        }
        return 0;
    }
    if (op >= 0x30 && op <= 0x37) {                                        /* ADDR ... CMPR */
        uint8_t pb = fetch8(s);
        int src = pb >> 4, dst = pb & 15, k = op & 7;
        static const int alu_of[8] = { 11, 9, 0, 2, 4, 10, 8, 1 };
        if (!(dst & 8)) {
            /* A 16-bit operation.  [XRoar/silicon] an 8-bit source widens:
             * A or B as D, E or F as W, CC zero-extended, DP as DP:M. */
            uint16_t a = hd6309_tfr_get(c, dst), b;
            switch (src) {
            case 0x8: case 0x9: b = getD(c); break;
            case 0xE: case 0xF: b = getW(c); break;
            case 0xA: b = c->cc; break;
            case 0xB: b = (uint16_t)((c->dp << 8) | s->c->m); break;
            default:  b = hd6309_tfr_get(c, src); break;
            }
            uint16_t r = alu16(c, alu_of[k], a, b);
            if (k != 7) hd6309_tfr_set(c, dst, r);
        } else {
            /* An 8-bit operation: a 16-bit source gives its LOW byte. */
            uint8_t a = (uint8_t)hd6309_tfr_get(c, dst);
            uint8_t b = (uint8_t)hd6309_tfr_get(c, src);
            uint8_t r = alu8(c, alu_of[k], a, b);
            if (k != 7) {
                switch (dst) {
                case 0x8: c->a = r; break;
                case 0x9: c->b = r; break;
                case 0xA: c->cc = r; break;
                case 0xB: c->dp = r; break;
                case 0xE: c->e = r; break;
                case 0xF: c->f = r; break;
                default: break;
                }
            }
        }
        return 0;
    }
    switch (op) {
    case 0x38: push8(s, &c->s, c->f); push8(s, &c->s, c->e); return 0;   /* PSHSW */
    case 0x39: c->e = pull8(s, &c->s); c->f = pull8(s, &c->s); return 0; /* PULSW */
    case 0x3A: push8(s, &c->u, c->f); push8(s, &c->u, c->e); return 0;   /* PSHUW */
    case 0x3B: c->e = pull8(s, &c->u); c->f = pull8(s, &c->u); return 0; /* PULUW */
    case 0x3F:                                                             /* SWI2 */
        c->cc |= CC_E;
        push_entire(s);
        vector(s, 0xFFF4, 0);
        return 0;
    default: break;
    }
    if ((op >> 4) == 4) { setD(c, unary(c, op & 15, getD(c), 16)); return 0; }   /* NEGD ... CLRD */
    if ((op >> 4) == 5) { setW(c, unary(c, op & 15, getW(c), 16)); return 0; }   /* COMW ... CLRW */
    {
        int lo = op & 15, mode = col_mode(op);
        int hi = op >= 0xC0;
        if (hi) {
            /* $CE LDS; $DC.. LDQ, STQ, LDS, STS */
            if (lo == 0xE) { uint16_t v = opnd16(s, mode); if (!s->trap) c->s = alu16(c, 6, 0, v); return 0; }
            if (lo == 0xF) {
                t = ea_of(s, mode); if (s->trap) return 0;
                wr16(s, t, c->s); c->cc &= (uint8_t)~CC_V; nz16(c, c->s); return 0;
            }
            t = ea_of(s, mode); if (s->trap) return 0;
            if (lo == 0xC) {                                               /* LDQ */
                uint16_t h = rd16(s, t), l = rd16(s, (uint16_t)(t + 2));
                setD(c, h); setW(c, l);
            } else {                                                       /* STQ */
                wr16(s, t, getD(c)); wr16(s, (uint16_t)(t + 2), getW(c));
            }
            /* [silicon] LDQ leaves V alone - hoglet67's "random testing".
             * STQ clears it, as the book says and every store does: silicon
             * has not been asked (hoglet67 sets STQ's N and Z and says nothing
             * of V), so the book decides. */
            c->cc = (uint8_t)((c->cc & ~(CC_N | CC_Z | (lo == 0xC ? 0 : CC_V))) |
                              (c->a & 0x80 ? CC_N : 0) | ((getD(c) | getW(c)) ? 0 : CC_Z));
            return 0;
        }
        /* $80-$BF: SUBW CMPW SBCD CMPD ANDD BITD LDW STW EORD ADCD ORD ADDW CMPY - LDY STY */
        if (lo == 7 || lo == 0xF) {
            t = ea_of(s, mode); if (s->trap) return 0;
            uint16_t v = lo == 7 ? getW(c) : c->y;
            wr16(s, t, v); c->cc &= (uint8_t)~CC_V; nz16(c, v);
            return 0;
        }
        uint16_t v = opnd16(s, mode);
        if (s->trap) return 0;
        switch (lo) {
        case 0x0: setW(c, alu16(c, 0, getW(c), v)); break;
        case 0x1: alu16(c, 1, getW(c), v); break;
        case 0x2: setD(c, alu16(c, 2, getD(c), v)); break;
        case 0x3: alu16(c, 1, getD(c), v); break;
        case 0x4: setD(c, alu16(c, 4, getD(c), v)); break;
        case 0x5: alu16(c, 5, getD(c), v); break;
        case 0x6: setW(c, alu16(c, 6, 0, v)); break;
        case 0x8: setD(c, alu16(c, 8, getD(c), v)); break;
        case 0x9: setD(c, alu16(c, 9, getD(c), v)); break;
        case 0xA: setD(c, alu16(c, 10, getD(c), v)); break;
        case 0xB: setW(c, alu16(c, 11, getW(c), v)); break;
        case 0xC: alu16(c, 1, c->y, v); break;
        case 0xE: c->y = alu16(c, 6, 0, v); break;
        default: s->trap = 1; break;
        }
        return 0;
    }
}

static int exec_page2(S *s, uint8_t op, uint16_t opc_pc)
{
    cpu6809 *c = s->c;
    uint16_t t;
    if (op >= 0x30 && op <= 0x37) { bitop(s, op & 7); return 0; }
    if (op >= 0x38 && op <= 0x3B) { s->cyc += 3 * tfm_run(s, op - 0x38, opc_pc); return 0; }
    switch (op) {
    case 0x3C: {                                                           /* BITMD */
        uint8_t im = fetch8(s);
        s->c->m = im;                                                        /* [silicon] */
        uint8_t tst = im & (MD_D0 | MD_IL);
        /* ⚠ [XRoar] only Z, and only the bits tested are cleared; the book
         * says N and V too, and that bits 6 and 7 are cleared. */
        c->cc = (uint8_t)((c->cc & ~CC_Z) | ((c->md & tst) ? 0 : CC_Z));
        c->md &= (uint8_t)~tst;
        return 0;
    }
    case 0x3D: c->md = (uint8_t)((c->md & (MD_D0 | MD_IL)) | (fetch8(s) & (MD_NM | MD_FM))); return 0;  /* LDMD */
    case 0x3F:                                                             /* SWI3 */
        c->cc |= CC_E;
        push_entire(s);
        vector(s, 0xFFF2, 0);
        return 0;
    default: break;
    }
    if ((op >> 4) == 4) { c->e = (uint8_t)unary(c, op & 15, c->e, 8); return 0; }   /* COME ... CLRE */
    if ((op >> 4) == 5) { c->f = (uint8_t)unary(c, op & 15, c->f, 8); return 0; }   /* COMF ... CLRF */
    {
        int lo = op & 15, mode = col_mode(op);
        int isF = op >= 0xC0;
        uint8_t *acc = isF ? &c->f : &c->e;
        if (!isF && (lo == 3 || lo == 0xC)) {                              /* CMPU CMPS */
            uint16_t v = opnd16(s, mode);
            if (!s->trap) alu16(c, 1, lo == 3 ? c->u : c->s, v);
            return 0;
        }
        if (!isF && (lo == 0xD || lo == 0xE)) {                            /* DIVD DIVQ */
            /* ⭐ [silicon] hoglet67's measured rules, which settle what the
             * book leaves open.  The time depends on the operands: +1 for a
             * negative dividend, +1 for a negative divisor, -1 for DIVD's two's
             * complement overflow, -13/-21 for a range overflow, which stops
             * early. */
            int q = lo == 0xE;
            uint32_t dv = q ? opnd16(s, mode) : opnd8(s, mode);
            if (s->trap) return 0;
            if (dv == 0) {                                                 /* Z set, N V clear */
                c->cc = (uint8_t)((c->cc & ~(CC_N | CC_V)) | CC_Z);
                c->m = 0;
                take_trap(s, MD_D0, s->cyc + (q ? (s->nm ? -8 : -10) : (s->nm ? 0 : -2)));
                return 0;
            }
            uint32_t a = q ? (((uint32_t)getD(c) << 16) | getW(c)) : getD(c);
            uint32_t signbit = q ? 0x80000000u : 0x8000u, mask = q ? 0xFFFFFFFFu : 0xFFFFu;
            int signq = 0, signr = 0;
            if (a & signbit) { a = (uint32_t)(-a) & mask; signq ^= 1; signr ^= 1; s->cyc++; }
            if (dv & (q ? 0x8000u : 0x80u)) { dv = (q ? 0x10000u : 0x100u) - dv; signq ^= 1; s->cyc++; }
            uint32_t quo = a / dv, rem = a % dv;
            c->m = signq ? 0xFF : 0x00;
            if (quo > (q ? 0xFFFFu : 0xFFu)) {                             /* range overflow */
                /* ⚠ undocumented: the dividend's MAGNITUDE is left in D (Q),
                 * and N is its sign */
                c->cc = (uint8_t)((c->cc & ~(CC_N | CC_Z | CC_V | CC_C)) | CC_V | (signr ? CC_N : 0));
                if (q) { setD(c, (uint16_t)(a >> 16)); setW(c, (uint16_t)a); } else setD(c, (uint16_t)a);
                s->cyc -= q ? 21 : 13;
                return 0;
            }
            if (rem > 0 && signr) rem = (q ? 0x10000u : 0x100u) - rem;     /* whatever the overflow */
            c->cc = (uint8_t)((c->cc & ~(CC_V | CC_C)) | (quo & 1));
            if (quo > (q ? 0x7FFFu : 0x7Fu)) {                             /* two's complement overflow */
                c->cc |= CC_V;
                if (!q) s->cyc--;                                          /* DIVQ saves nothing */
            } else if (quo > 0 && signq) quo = (q ? 0x10000u : 0x100u) - quo;
            if (q) { setD(c, (uint16_t)rem); setW(c, (uint16_t)quo); nz16(c, (uint16_t)quo); }
            else { c->a = (uint8_t)rem; c->b = (uint8_t)quo; nz8(c, c->b); }
            return 0;
        }
        if (!isF && lo == 0xF) {                                           /* MULD */
            uint16_t v = opnd16(s, mode);
            if (s->trap) return 0;
            int na = (c->a & 0x80) != 0, nb = (v & 0x8000) != 0;
            int32_t r = (int32_t)(int16_t)getD(c) * (int16_t)v;
            /* [silicon] a cycle for each negative operand, and one to negate a
             * negative product */
            s->cyc += na + nb + (na ^ nb);
            c->m = (na ^ nb) ? 0xFF : 0x00;
            setD(c, (uint16_t)((uint32_t)r >> 16));
            setW(c, (uint16_t)r);
            /* ⚠ N and Z of the whole 32-bit result, as the book says and
             * hoglet67 measured.  (XRoar sets N instead of Z when D is 0 - a
             * slip in its source, not silicon.) */
            c->cc = (uint8_t)((c->cc & ~(CC_N | CC_Z)) | (r < 0 ? CC_N : 0) | (r ? 0 : CC_Z));
            return 0;
        }
        if (lo == 7) {                                                     /* STE STF */
            t = ea_of(s, mode); if (s->trap) return 0;
            wr(s, t, *acc); c->cc &= (uint8_t)~CC_V; nz8(c, *acc);
            return 0;
        }
        uint8_t v = opnd8(s, mode);
        if (s->trap) return 0;
        uint8_t r = alu8(c, lo, *acc, v);
        if (lo != 1) *acc = r;
        return 0;
    }
}
