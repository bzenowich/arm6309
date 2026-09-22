/* The 6809 core - see cpu6809.h. Every E-cycle count below is mc6809i.v's
 * state sequence, one state per cycle, and the comments name the states so a
 * count can be checked against the Verilog by reading. The decode is built at
 * first reset from transliterations of the Verilog's own decode functions
 * (addressing_mode_type, ALU16RegFromInst, IsST16, ...), which is what makes
 * its undocumented opcodes come out the way the core's do rather than the way
 * silicon's do.
 *
 * WHERE mc6809i.v DIFFERS FROM THE MC6809E DATASHEET, AND WHAT THIS FILE DOES
 * (all matched to the Verilog; test/run.sh's traces exercise every one, and
 * test/cycles.py fails if the Verilog shows any other length that is not the
 * datasheet's):
 *   SWI, SWI2       20 and 21 cycles; datasheet 19 and 20 (an extra state
 *                   before the push)
 *   SWI3            vectors through $FFFA and sets I and F, like SWI: SWI_START
 *                   assigns SWI3 and then overwrites it with an if/else
 *   PSHS/PSHU #0    6 cycles; datasheet 5 (PSH_ACTION idles once)
 *   SEX             sets no flags; datasheet sets N and Z
 *   DAA             leaves V alone; C is only ever set, never cleared
 *   CWAI + NMI      the NMI latch is not cleared by an NMI taken out of CWAI, so
 *                   the handler's first fetch takes the NMI a second time
 *   reset           S comes out of reset as $FFFD, X Y U A B DP as 0; NMI is
 *                   disarmed until S changes value (not until S is written)
 *   dummy reads     not performed: the Verilog puts PC or $FFFF on the bus in
 *                   its don't-care cycles, and nothing in this machine has a
 *                   read side effect there
 * Undocumented opcodes follow the Verilog's GHOST decode: $x1/$x2/$x5/$xB in
 * rows 0,4-7 execute as their neighbours; $4E/$5E clear the register and set
 * Z; invalid bytes are 2-byte, 2-cycle no-ops; prefixes are ignored by
 * everything but the 16-bit ops, long branches, SWI and STY/STS; indexed modes
 * $8A/$8E are 3-cycle no-ops and $87 is a 5-bit offset. The few page-2/3
 * combinations that seize the Verilog core in ALU_EA seize this one too.
 */
#include "cpu6809.h"
#include "hd6309ops.h"
#include "hd6309.h"
#include <stdio.h>
#include <stdlib.h>

#define CC_E 0x80
#define CC_F 0x40
#define CC_H 0x20
#define CC_I 0x10
#define CC_N 0x08
#define CC_Z 0x04
#define CC_V 0x02
#define CC_C 0x01

enum { M_INH, M_IMM, M_DIR, M_REL, M_IDX, M_EXT, M_INV };
/* inherent */
enum { I_NOP, I_DAA, I_SYNC, I_MUL, I_RTS, I_RTI, I_SWI, I_CWAI, I_SEX, I_ABX, I_ALU };
/* immediate */
enum { S_NONE, S_ANDCC, S_ORCC, S_PSH, S_PUL, S_TFR, S_EXG, S_A8, S_A16 };
/* ALU_EA columns, in the Verilog's priority order */
enum { E_NONE, E_SET1, E_ST8, E_LD16, E_ST16, E_SET0, E_A16, E_JSR, E_LEA };
/* ALU16 ops and registers, the Verilog's numbering */
enum { O16_SUB, O16_ADD, O16_LD, O16_CMP, O16_LEA, O16_INV = 7 };
enum { R_X, R_Y, R_U, R_S, R_D, R_INV = 7 };
enum { T_NMI, T_IRQ, T_FIRQ, T_SWI, T_SWI2 };

typedef struct {
    uint8_t mode, kind, op, reg;
    uint8_t wb, jmp, onebyte, longbr;
} dec_t;

static dec_t dec[3][256];
static uint8_t ghost[256];
static int dec_ready;

/* ---- decode, transliterated from mc6809i.v ------------------------------ */

static int addr_mode(int i)
{
    int hi = i >> 4, lo = i & 15;
    switch (hi) {
    case 0x0: return M_DIR;
    case 0x1:
        switch (lo) {
        case 0x2: case 0x3: case 0x9: case 0xD: return M_INH;
        case 0x6: case 0x7: return M_REL;
        case 0xA: case 0xC: case 0xE: case 0xF: return M_IMM;
        default: return M_INV;
        }
    case 0x2: return M_REL;
    case 0x3:
        if (lo <= 3) return M_IDX;
        if (lo <= 7) return M_IMM;
        if (lo == 9 || lo == 0xA || lo == 0xB || lo == 0xC || lo == 0xD || lo == 0xF) return M_INH;
        return M_INV;
    case 0x4: case 0x5: return M_INH;
    case 0x6: return M_IDX;
    case 0x7: return M_EXT;
    case 0x8:
        if (lo == 7 || lo == 0xF) return M_INV;
        if (lo == 0xD) return M_REL;
        return M_IMM;
    case 0x9: case 0xD: return M_DIR;
    case 0xA: case 0xE: return M_IDX;
    case 0xC: return M_IMM;
    default: return M_EXT;       /* $B, $F */
    }
}

/* casex match of {Page2, Page3, inst} against a 10-character pattern */
static int cx(int p2, int p3, int i, const char *pat)
{
    int v = (p2 << 9) | (p3 << 8) | i;
    for (int k = 0; k < 10; k++) {
        int bit = (v >> (9 - k)) & 1;
        if (pat[k] != 'x' && pat[k] - '0' != bit) return 0;
    }
    return 1;
}

static int alu16_reg(int p2, int p3, int i)
{
    if (cx(p2, p3, i, "1010xx0011")) return R_D;
    if (cx(p2, p3, i, "1010xx1100")) return R_Y;
    if (cx(p2, p3, i, "0110xx0011")) return R_U;
    if (cx(p2, p3, i, "0110xx1100")) return R_S;
    if (cx(p2, p3, i, "0010xx1100")) return R_X;
    if (cx(p2, p3, i, "0011xx0011")) return R_D;
    if (cx(p2, p3, i, "0011xx1100")) return R_D;
    if (cx(p2, p3, i, "0010xx1110")) return R_X;
    if (cx(p2, p3, i, "0011xx1110")) return R_U;
    if (cx(p2, p3, i, "1010xx1110")) return R_Y;
    if (cx(p2, p3, i, "1011xx1110")) return R_S;
    if (cx(p2, p3, i, "0010xx0011")) return R_D;
    if (!p2 && !p3 && i == 0x3A) return R_X;
    if (!p2 && !p3 && i == 0x30) return R_X;
    if (!p2 && !p3 && i == 0x31) return R_Y;
    if (!p2 && !p3 && i == 0x32) return R_S;
    if (!p2 && !p3 && i == 0x33) return R_U;
    return R_INV;
}

static int alu16_op(int p2, int p3, int i, int *wb)
{
    *wb = 1;
    if (cx(p2, p3, i, "1010xx0011") || cx(p2, p3, i, "1010xx1100") || cx(p2, p3, i, "0110xx0011") ||
        cx(p2, p3, i, "0110xx1100") || cx(p2, p3, i, "0010xx1100")) { *wb = 0; return O16_CMP; }
    if (cx(p2, p3, i, "0011xx0011")) return O16_ADD;
    if (cx(p2, p3, i, "0011xx1100")) return O16_LD;
    if (cx(p2, p3, i, "001xxx1110")) return O16_LD;
    if (cx(p2, p3, i, "101xxx1110")) return O16_LD;
    if (cx(p2, p3, i, "0010xx0011")) return O16_SUB;
    if (!p2 && !p3 && i == 0x3A) return O16_ADD;
    if (cx(p2, p3, i, "00001100xx")) return O16_LEA;
    return O16_INV;
}

static int set0(int i)
{
    int hi = i >> 4, lo = i & 15;
    return (hi == 0 || (hi >= 4 && hi <= 7)) && lo != 1 && lo != 2 && lo != 5 && lo != 0xB && lo != 0xE;
}

static int set1(int i)
{
    int lo = i & 15;
    return (i >> 4) >= 8 && lo <= 0xB && lo != 3 && lo != 7;
}

static int onebyte(int i)
{
    int hi = i >> 4, lo = i & 15;
    if (hi == 4 || hi == 5) return 1;
    if (hi == 1) return lo == 2 || lo == 3 || lo == 9 || lo == 0xD;
    if (hi == 3) return lo >= 9 && lo != 0xC;
    return 0;
}

static void build(void)
{
    for (int i = 0; i < 256; i++) {
        int hi = i >> 4, lo = i & 15, g = i;
        if ((hi == 0 || (hi >= 4 && hi <= 7))) {
            if (lo == 1) g = hi << 4;
            if (lo == 2) g = (hi << 4) | 3;
            if (lo == 5) g = (hi << 4) | 4;
            if (lo == 0xB) g = (hi << 4) | 0xA;
        }
        ghost[i] = (uint8_t)g;
    }
    for (int pg = 0; pg < 3; pg++)
    for (int i = 0; i < 256; i++) {
        int p2 = pg == 1, p3 = pg == 2, wb16;
        dec_t d = {0};
        int regA = (i >> 4) == 4 || (i >> 4) == 8 || (i >> 4) == 9 || (i >> 4) == 0xA || (i >> 4) == 0xB;
        int op8 = ((i >> 4) & 8 ? 16 : 0) | (i & 15);
        int wb8 = !(op8 == 17 || op8 == 13 || op8 == 21);
        int op16 = alu16_op(p2, p3, i, &wb16);
        int reg16 = alu16_reg(p2, p3, i);
        d.mode = (uint8_t)addr_mode(i);
        switch (d.mode) {
        case M_INH:
            d.onebyte = (uint8_t)onebyte(i);
            switch (i) {
            case 0x12: d.kind = I_NOP; break;
            case 0x19: d.kind = I_DAA; break;
            case 0x13: d.kind = I_SYNC; break;
            case 0x3D: d.kind = I_MUL; break;
            case 0x39: d.kind = I_RTS; break;
            case 0x3B: d.kind = I_RTI; break;
            case 0x3F: d.kind = I_SWI; break;
            case 0x3C: d.kind = I_CWAI; break;
            case 0x1D: d.kind = I_SEX; break;
            case 0x3A: d.kind = I_ABX; break;
            default:   d.kind = I_ALU; d.op = (uint8_t)op8; d.reg = (uint8_t)regA; d.wb = (uint8_t)wb8;
            }
            break;
        case M_IMM:
            if (i == 0x1C) d.kind = S_ANDCC;
            else if (i == 0x1A) d.kind = S_ORCC;
            else if (i == 0x34 || i == 0x36) d.kind = S_PSH;
            else if (i == 0x35 || i == 0x37) d.kind = S_PUL;
            else if (i == 0x1F) d.kind = S_TFR;
            else if (i == 0x1E) d.kind = S_EXG;
            else if (set0(i) || set1(i)) { d.kind = S_A8; d.op = (uint8_t)op8; d.reg = (uint8_t)regA; d.wb = (uint8_t)wb8; }
            else if (op16 != O16_INV) { d.kind = S_A16; d.op = (uint8_t)op16; d.reg = (uint8_t)reg16; d.wb = (uint8_t)wb16; }
            else d.kind = S_NONE;
            break;
        case M_REL:
            d.longbr = (uint8_t)(p2 || i == 0x16 || i == 0x17);
            break;
        case M_DIR: case M_IDX: case M_EXT:
            d.jmp = (uint8_t)(((i >> 4) == 0 || (i >> 4) == 6 || (i >> 4) == 7) && (i & 15) == 0xE);
            if (set1(i)) { d.kind = E_SET1; d.op = (uint8_t)op8; d.reg = (uint8_t)regA; d.wb = (uint8_t)wb8; }
            else if (i == 0x97 || i == 0xA7 || i == 0xB7) { d.kind = E_ST8; d.reg = 1; }
            else if (i == 0xD7 || i == 0xE7 || i == 0xF7) { d.kind = E_ST8; d.reg = 0; }
            else if (op16 == O16_LD) { d.kind = E_LD16; d.op = (uint8_t)op16; d.reg = (uint8_t)reg16; }
            else if (i == 0x9F || i == 0xAF || i == 0xBF) { d.kind = E_ST16; d.reg = (uint8_t)(p2 ? R_Y : R_X); }
            else if (i == 0xDF || i == 0xEF || i == 0xFF) { d.kind = E_ST16; d.reg = (uint8_t)(p2 ? R_S : R_U); }
            else if (i == 0xDD || i == 0xED || i == 0xFD) { d.kind = E_ST16; d.reg = R_D; }
            else if (set0(i)) { d.kind = E_SET0; d.op = (uint8_t)op8; }
            else if (op16 != O16_INV && (i < 0x30 || i > 0x33)) { d.kind = E_A16; d.op = (uint8_t)op16; d.reg = (uint8_t)reg16; d.wb = (uint8_t)wb16; }
            else if (i == 0x9D || i == 0xAD || i == 0xBD) d.kind = E_JSR;
            else if (i >= 0x30 && i <= 0x33) { d.kind = E_LEA; d.op = (uint8_t)op16; d.reg = (uint8_t)reg16; }
            else d.kind = E_NONE;
            break;
        }
        dec[pg][i] = d;
    }
    dec_ready = 1;
}

/* ---- arithmetic ---------------------------------------------------------- */

static inline uint8_t alu8(uint8_t *ccp, int op, uint8_t a, uint8_t b)
{
    unsigned cc = *ccp, t, r;
    switch (op) {
    case 0:  r = (uint8_t)-a; cc = (cc & ~(CC_C | CC_V)) | (r ? CC_C : 0) | (a == 0x80 ? CC_V : 0); break;
    case 3:  r = (uint8_t)~a; cc = (cc & ~CC_V) | CC_C; break;
    case 4:  r = a >> 1; cc = (cc & ~CC_C) | (a & 1); break;
    case 6:  r = (a >> 1) | ((cc & CC_C) << 7); cc = (cc & ~CC_C) | (a & 1); break;
    case 7:  r = (a >> 1) | (a & 0x80); cc = (cc & ~CC_C) | (a & 1); break;
    case 8:  r = (uint8_t)(a << 1); cc = (cc & ~(CC_C | CC_V)) | (a >> 7) | (((a ^ (a << 1)) & 0x80) ? CC_V : 0); break;
    case 9:  r = (uint8_t)((a << 1) | (cc & CC_C)); cc = (cc & ~(CC_C | CC_V)) | (a >> 7) | (((a ^ (a << 1)) & 0x80) ? CC_V : 0); break;
    case 10: r = (uint8_t)(a - 1); cc = (cc & ~CC_V) | (a == 0x80 ? CC_V : 0); break;
    case 12: r = (uint8_t)(a + 1); cc = (cc & ~CC_V) | (a == 0x7F ? CC_V : 0); break;
    case 13: r = a; cc &= ~CC_V; break;
    case 15: r = 0; cc &= ~(CC_V | CC_C); break;
    case 16: case 17:
        t = (unsigned)a - b; r = t & 0xFF;
        cc = (cc & ~(CC_C | CC_V)) | ((t >> 8) & 1) | (((a ^ b) & (a ^ r) & 0x80) ? CC_V : 0); break;
    case 18:
        t = (unsigned)a - b - (cc & CC_C); r = t & 0xFF;
        cc = (cc & ~(CC_C | CC_V)) | ((t >> 8) & 1) | (((a ^ b) & (a ^ r) & 0x80) ? CC_V : 0); break;
    case 20: case 21: r = a & b; cc &= ~CC_V; break;
    case 22: r = b; cc &= ~CC_V; break;
    case 24: r = a ^ b; cc &= ~CC_V; break;
    case 26: r = a | b; cc &= ~CC_V; break;
    case 25: case 27:
        t = (unsigned)a + b + (op == 25 ? (cc & CC_C) : 0); r = t & 0xFF;
        cc = (cc & ~(CC_C | CC_V | CC_H)) | ((t >> 8) & 1) | ((~(a ^ b) & (a ^ r) & 0x80) ? CC_V : 0) |
             ((a ^ b ^ r) & 0x10 ? CC_H : 0);
        break;
    default: r = 0; break;       /* $4E/$5E: the ALU's default arm */
    }
    cc = (cc & ~(CC_N | CC_Z)) | (r & 0x80 ? CC_N : 0) | (r ? 0 : CC_Z);
    *ccp = (uint8_t)cc;
    return (uint8_t)r;
}

static inline uint16_t alu16(uint8_t *ccp, int op, uint16_t a, uint16_t b)
{
    unsigned cc = *ccp, t, r;
    switch (op) {
    case O16_ADD:
        t = (unsigned)a + b; r = t & 0xFFFF;
        cc = (cc & ~(CC_C | CC_V)) | ((t >> 16) & 1) | ((~(a ^ b) & (a ^ r) & 0x8000) ? CC_V : 0); break;
    case O16_SUB: case O16_CMP:
        t = (unsigned)a - b; r = t & 0xFFFF;
        cc = (cc & ~(CC_C | CC_V)) | ((t >> 16) & 1) | (((a ^ b) & (a ^ r) & 0x8000) ? CC_V : 0); break;
    case O16_LD: r = b; cc &= ~CC_V; break;
    case O16_LEA: r = a; break;
    default: r = 0; break;
    }
    cc = (cc & ~CC_Z) | (r ? 0 : CC_Z);
    if (op != O16_LEA) cc = (cc & ~CC_N) | (r & 0x8000 ? CC_N : 0);
    *ccp = (uint8_t)cc;
    return (uint16_t)r;
}

static inline uint16_t get16(const cpu6809 *c, int r)
{
    switch (r) {
    case R_X: return c->x;
    case R_Y: return c->y;
    case R_U: return c->u;
    case R_S: return c->s;
    case R_D: return (uint16_t)((c->a << 8) | c->b);
    default:  return 0;
    }
}

static inline void set16(cpu6809 *c, int r, uint16_t v)
{
    switch (r) {
    case R_X: c->x = v; break;
    case R_Y: c->y = v; break;
    case R_U: c->u = v; break;
    case R_S: c->s = v; break;
    case R_D: c->a = (uint8_t)(v >> 8); c->b = (uint8_t)v; break;
    default: break;
    }
}

/* EXGTFRRegister: an 8-bit register reads as $FFnn, PC as the byte after the
 * postbyte, an undefined code as 0 */
static uint16_t tfr_get(const cpu6809 *c, int code)
{
    switch (code) {
    case 0x0: return (uint16_t)((c->a << 8) | c->b);
    case 0x1: return c->x;
    case 0x2: return c->y;
    case 0x3: return c->u;
    case 0x4: return c->s;
    case 0x5: return c->pc;
    case 0x8: return (uint16_t)(0xFF00 | c->a);
    case 0x9: return (uint16_t)(0xFF00 | c->b);
    case 0xA: return (uint16_t)(0xFF00 | c->cc);
    case 0xB: return (uint16_t)(0xFF00 | c->dp);
    default:  return 0;
    }
}

static void tfr_set(cpu6809 *c, int code, uint16_t v)
{
    switch (code) {
    case 0x0: c->a = (uint8_t)(v >> 8); c->b = (uint8_t)v; break;
    case 0x1: c->x = v; break;
    case 0x2: c->y = v; break;
    case 0x3: c->u = v; break;
    case 0x4: c->s = v; break;
    case 0x5: c->pc = v; break;
    case 0x8: c->a = (uint8_t)v; break;
    case 0x9: c->b = (uint8_t)v; break;
    case 0xA: c->cc = (uint8_t)v; break;
    case 0xB: c->dp = (uint8_t)v; break;
    default: break;
    }
}

/* ---- bus, one access per E cycle ----------------------------------------- */

#define RD(ad)    (c->now = (uint64_t)(base + n), c->read(c->ctx, (uint16_t)(ad)))
#define WR(ad, v) (c->now = (uint64_t)(base + n), c->write(c->ctx, (uint16_t)(ad), (uint8_t)(v)))

static inline int line_at(const cpu6809_line *l, int64_t m) { return m >= l->t ? l->lvl : l->prev; }

static inline void line_sync(cpu6809_line *l, int v, int64_t at)
{
    if (v != l->lvl) { l->prev = l->lvl; l->lvl = v; l->t = at; }
}

/* NMISample2's falling edge sets NMILatched at the end of the cycle it was
 * sampled in, if S has been changed by then */
static inline void nmi_resolve(cpu6809 *c, int64_t n0)
{
    if (c->nmi_edge && c->nmi_edge_t + 1 <= n0) {
        c->nmi_edge = 0;
        if (c->nmi_armed) c->nmi_latched = 1;
    }
}

/* PSH_ACTION: one byte per cycle, PC first; an empty mask still takes a cycle */
static int push(cpu6809 *c, int64_t base, int n, uint8_t m, int onU)
{
    uint16_t *sp = onU ? &c->u : &c->s;
    uint16_t other = onU ? c->s : c->u;
    if (!m) return n + 1;
    if (m & 0x80) { WR(--*sp, c->pc); n++; WR(--*sp, c->pc >> 8); n++; }
    if (m & 0x40) { WR(--*sp, other); n++; WR(--*sp, other >> 8); n++; }
    if (m & 0x20) { WR(--*sp, c->y); n++; WR(--*sp, c->y >> 8); n++; }
    if (m & 0x10) { WR(--*sp, c->x); n++; WR(--*sp, c->x >> 8); n++; }
    if (m & 0x08) { WR(--*sp, c->dp); n++; }
    if (m & 0x04) { WR(--*sp, c->b); n++; }
    if (m & 0x02) { WR(--*sp, c->a); n++; }
    if (m & 0x01) { WR(--*sp, c->cc); n++; }
    return n;
}

/* PUL_ACTION: one byte per cycle, CC first, then a cycle to notice it is done */
static int pull(cpu6809 *c, int64_t base, int n, uint8_t m, int onU)
{
    uint16_t *sp = onU ? &c->u : &c->s;
    uint16_t *op = onU ? &c->s : &c->u;
    uint16_t v;
    if (m & 0x01) { c->cc = RD(*sp); ++*sp; n++; }
    if (m & 0x02) { c->a = RD(*sp); ++*sp; n++; }
    if (m & 0x04) { c->b = RD(*sp); ++*sp; n++; }
    if (m & 0x08) { c->dp = RD(*sp); ++*sp; n++; }
    if (m & 0x10) { v = (uint16_t)(RD(*sp) << 8); ++*sp; n++; c->x = (uint16_t)(v | RD(*sp)); ++*sp; n++; }
    if (m & 0x20) { v = (uint16_t)(RD(*sp) << 8); ++*sp; n++; c->y = (uint16_t)(v | RD(*sp)); ++*sp; n++; }
    if (m & 0x40) { v = (uint16_t)(RD(*sp) << 8); ++*sp; n++; *op = (uint16_t)(v | RD(*sp)); ++*sp; n++; }
    if (m & 0x80) { v = (uint16_t)(RD(*sp) << 8); ++*sp; n++; c->pc = (uint16_t)(v | RD(*sp)); ++*sp; n++; }
    return n + 1;
}

/* IRQ_VECTOR_HI, IRQ_VECTOR_LO (masks set here), INT_DONTCARE */
static int vector(cpu6809 *c, int64_t base, int n, int type)
{
    uint16_t v;
    uint8_t mask;
    switch (type) {
    case T_NMI:  v = 0xFFFC; mask = CC_F | CC_I; break;
    case T_IRQ:  v = 0xFFF8; mask = CC_I; break;
    case T_FIRQ: v = 0xFFF6; mask = CC_F | CC_I; break;
    case T_SWI:  v = 0xFFFA; mask = CC_F | CC_I; break;
    default:     v = 0xFFF4; mask = 0; break;
    }
    uint8_t hi = RD(v); n++;
    uint8_t lo = RD(v + 1); n++;
    c->cc |= mask;
    c->pc = (uint16_t)((hi << 8) | lo);
    return n + 1;
}

/* from the *_START state at cycle n: START, IRQ_DONTCARE, the push,
 * IRQ_DONTCARE2, then the vector. IRQ/NMI 19 cycles with the fetch, FIRQ 10. */
static int interrupt(cpu6809 *c, int64_t base, int n, int type)
{
    if (type == T_NMI) c->nmi_latched = 0;
    if (type == T_FIRQ) c->cc &= ~CC_E; else c->cc |= CC_E;
    n += 2;
    n = push(c, base, n, type == T_FIRQ ? 0x81 : 0xFF, 0);
    n++;
    return vector(c, base, n, type);
}

/* one cycle of CWAI_POST or SYNC, at cycle base */
static int wait_step(cpu6809 *c, int64_t base)
{
    int firq = line_at(&c->l_firq, base - 2), irq = line_at(&c->l_irq, base - 2), type;
    nmi_resolve(c, base);
    if (c->wait == 2) {
        if (c->nmi_latched || firq || irq) { c->wait = 0; return 2; }   /* SYNC, SYNC_EXIT */
        return 1;
    }
    if (c->wait != 1) return 1;                                         /* seized */
    if (c->nmi_latched) { type = T_NMI; c->cc |= CC_F | CC_I; }          /* latch not cleared */
    else if (firq && !(c->cc & CC_F)) { type = T_FIRQ; c->cc |= CC_F | CC_I; }
    else if (irq && !(c->cc & CC_I)) { type = T_IRQ; c->cc |= CC_I; }
    else return 1;
    c->wait = 0;
    return vector(c, base, 1, type);
}

/* ALU_EA and what follows it, from cycle n; returns the instruction's length */
static int alu_ea(cpu6809 *c, int64_t base, int n, const dec_t *d, uint16_t ea)
{
    uint8_t v, lo;
    uint16_t w, t;
    switch (d->kind) {
    case E_SET1:
        v = RD(ea);
        if (d->reg) { v = alu8(&c->cc, d->op, c->a, v); if (d->wb) c->a = v; }
        else        { v = alu8(&c->cc, d->op, c->b, v); if (d->wb) c->b = v; }
        return n + 1;
    case E_ST8:
        v = d->reg ? c->a : c->b;
        WR(ea, v);
        alu8(&c->cc, 22, 0, v);
        return n + 1;
    case E_LD16:
        v = RD(ea); n++;
        lo = RD((uint16_t)(ea + 1)); n++;
        set16(c, d->reg, alu16(&c->cc, O16_LD, 0, (uint16_t)((v << 8) | lo)));
        return n;
    case E_ST16:
        w = get16(c, d->reg);
        alu16(&c->cc, O16_LD, 0, w);
        WR(ea, w >> 8); n++;
        WR((uint16_t)(ea + 1), w); n++;
        return n;
    case E_SET0:
        v = alu8(&c->cc, d->op, RD(ea), 0); n++;
        if (d->op == 13) return n + 2;                                  /* TST_DONTCARE1, 2 */
        n++;
        WR(ea, v);
        return n + 1;
    case E_A16:
        v = RD(ea); n++;
        lo = RD((uint16_t)(ea + 1)); n++;
        w = alu16(&c->cc, d->op, get16(c, d->reg), (uint16_t)((v << 8) | lo));
        if (d->wb) set16(c, d->reg, w);
        return n + 1;
    case E_JSR:
        t = c->pc;
        c->pc = ea;
        n += 2;                                                         /* ALU_EA, JSR_DONTCARE */
        WR(--c->s, t); n++;
        WR(--c->s, t >> 8); n++;
        return n;
    case E_LEA:
        switch (d->reg) {
        case R_X: c->x = alu16(&c->cc, d->op, ea, 0); break;
        case R_Y: c->y = alu16(&c->cc, d->op, ea, 0); break;
        case R_U: c->u = ea; break;
        case R_S: c->s = ea; break;
        default: break;
        }
        return n + 1;
    default:
        c->wait = 3;                                                    /* ALU_EA, for ever */
        return n + 1;
    }
}

/* Is an interrupt pending as of E cycle `at`?  Exposed for hd6309.c's TFM,
 * which is the only interruptible instruction and must ask between bytes.
 * ⚠ It resolves the NMI edge as a side effect, exactly as cpu6809_step does. */
int cpu6809_int_pending(cpu6809 *c, int64_t at)
{
    nmi_resolve(c, at);
    if (c->nmi_latched) return 1;
    if (!(c->cc & CC_F) && line_at(&c->l_firq, at - 2)) return 1;
    if (!(c->cc & CC_I) && line_at(&c->l_irq, at - 2)) return 1;
    return 0;
}

void cpu6309_enable(cpu6809 *c)
{
    c->is6309 = 1;
    c->e = c->f = 0;
    c->v = 0;
    c->md = 0;                   /* 6809 emulation mode until LDMD says otherwise */
}

void cpu6809_reset(cpu6809 *c)
{
    if (!dec_ready) build();
    c->a = c->b = c->dp = 0;
    c->x = c->y = c->u = 0;
    c->s = 0xFFFD;
    c->cc = CC_F | CC_I;
    c->cycles = 0;
    c->now = 0;
    c->wait = 0;
    c->nmi_armed = c->nmi_latched = c->nmi_edge = 0;
    c->nmi_edge_t = 0;
    c->l_irq = (cpu6809_line){ c->irq, c->irq, 0 };
    c->l_firq = (cpu6809_line){ c->firq, c->firq, 0 };
    c->l_nmi = (cpu6809_line){ c->nmi, c->nmi, 0 };
    c->pc = (uint16_t)((c->read(c->ctx, 0xFFFE) << 8) | c->read(c->ctx, 0xFFFF));
}

void cpu6809_set_line(cpu6809 *c, int line, int level, uint64_t at)
{
    level = level != 0;
    cpu6809_line *l = line == CPU6809_IRQ ? &c->l_irq : line == CPU6809_FIRQ ? &c->l_firq : &c->l_nmi;
    if (line == CPU6809_NMI && level && !l->lvl) { c->nmi_edge = 1; c->nmi_edge_t = (int64_t)at; }
    line_sync(l, level, (int64_t)at);
    if (line == CPU6809_IRQ) c->irq = level;
    else if (line == CPU6809_FIRQ) c->firq = level;
    else c->nmi = level;
}

/* The indexed effective address, INDEXED_BASE onward.  ⚠ Lifted out of
 * cpu6809_step 2026-09-21 so hd6309.c can reach it; the arms are unchanged and
 * the differential test against mc6809e.v is what says so.  `*seize` is set for
 * the postbytes the Verilog's PostIllegalState swallows ($8A, $8E), on which the
 * caller must abandon the instruction exactly as the inline version did. */
int cpu6809_idx_ea(cpu6809 *c, int64_t base, int n, uint8_t b2,
                  uint16_t *eap, int *seize)
{
    uint16_t ea = 0, t;
    uint8_t lo;
    int mode = (b2 & 0x80) ? (b2 & 15) : 7;
    int ind = (b2 & 0x80) ? (b2 >> 4) & 1 : 0;
    uint16_t *rp;
    *seize = 0;
    switch ((b2 >> 5) & 3) {
    case 0: rp = &c->x; break;
    case 1: rp = &c->y; break;
    case 2: rp = &c->u; break;
    default: rp = &c->s; break;
    }
    switch (mode) {
        case 4: ea = *rp; n += 1; break;                                /* straight to ALU_EA or INDIRECT_HI */
        case 7: {                                                       /* DONTCARE3 */
            int o = b2 & 0x1F;
            if (o & 0x10) o -= 0x20;
            ea = (uint16_t)(*rp + o); n += 2; break;
        }
        case 8:  ea = (uint16_t)(*rp + (int8_t)RD(c->pc)); c->pc++; n += 2; break;
        case 12: { int8_t o = (int8_t)RD(c->pc); c->pc++; ea = (uint16_t)(c->pc + o); n += 2; break; }
        case 6:  ea = (uint16_t)(*rp + (int8_t)c->a); n += 2; break;
        case 5:  ea = (uint16_t)(*rp + (int8_t)c->b); n += 2; break;
        case 11: ea = (uint16_t)(*rp + ((c->a << 8) | c->b)); n += 5; break;  /* DOFF1, DOFF2, 16OFF2, 16OFF3 */
        case 0:  ea = *rp; *rp = (uint16_t)(*rp + 1); n += 3; break;          /* 16OFF2, 16OFF3 */
        case 1:  ea = *rp; *rp = (uint16_t)(*rp + 2); n += 4; break;          /* 16OFF0, 16OFF2, 16OFF3 */
        case 2:  *rp = (uint16_t)(*rp - 1); ea = *rp; n += 3; break;
        case 3:  *rp = (uint16_t)(*rp - 2); ea = *rp; n += 4; break;
        case 9:                                                          /* 16OFFSET_LO, 16OFF1, 2, 3 */
            t = (uint16_t)(RD(c->pc) << 8); c->pc++; n++;
            t |= RD(c->pc); c->pc++; n++;
            ea = (uint16_t)(*rp + t); n += 3; break;
        case 13:                                                         /* ... and PC16OFF_DONTCARE */
            t = (uint16_t)(RD(c->pc) << 8); c->pc++; n++;
            t |= RD(c->pc); c->pc++; n++;
            ea = (uint16_t)(c->pc + t); n += 4; break;
        case 15:                                                         /* IDX_EXTIND_LO, IDX_EXTIND_DONTCARE */
            t = (uint16_t)(RD(c->pc) << 8); c->pc++; n++;
            t |= RD(c->pc); c->pc++; n++;
            ea = t; n += 1; break;
    default: *seize = 1; *eap = 0; return n + 1;              /* $8A, $8E: PostIllegalState */
    }
    if (ind) {                                                      /* INDIRECT_HI, _LO, _DONTCARE */
        uint8_t hi = RD(ea); n++;
        lo = RD((uint16_t)(ea + 1)); n++;
        ea = (uint16_t)((hi << 8) | lo);
        n++;
    }
    *eap = ea;
    return n;
}

int cpu6809_step(cpu6809 *c)
{
    const int64_t base = (int64_t)c->cycles;
    const uint16_t s0 = c->s;
    int n, page = 0;
    uint8_t op, b2, lo, raw = 0;
    uint16_t opc_pc = 0;
    uint16_t ea, t;
    const dec_t *d;

    if (c->nmi != c->l_nmi.lvl) cpu6809_set_line(c, CPU6809_NMI, c->nmi, (uint64_t)base);
    line_sync(&c->l_irq, c->irq != 0, base);
    line_sync(&c->l_firq, c->firq != 0, base);

    if (c->wait) { n = wait_step(c, base); goto done; }

    /* FETCH_I1: interrupts are recognised here, on levels sampled two cycles ago */
    n = 0;
    nmi_resolve(c, base);
    if (c->nmi_latched) { n = interrupt(c, base, 1, T_NMI); goto done; }
    if (!(c->cc & CC_F) && line_at(&c->l_firq, base - 2)) { n = interrupt(c, base, 1, T_FIRQ); goto done; }
    if (!(c->cc & CC_I) && line_at(&c->l_irq, base - 2)) { n = interrupt(c, base, 1, T_IRQ); goto done; }

    /* ⚠ THE RAW BYTE IS KEPT, BECAUSE `ghost[]` DESTROYS THE EVIDENCE.  $01 is
     * OIM on a 6309 and ghosts to $00 NEG here, so a check made after the
     * mapping sees a perfectly ordinary 6809 instruction. */
    raw = RD(c->pc); op = ghost[raw]; c->pc++; n = 1;
    opc_pc = (uint16_t)(c->pc - 1);
    if (op == 0x10 || op == 0x11) {                                     /* FETCH_I1V2; first prefix wins */
        page = op == 0x10 ? 1 : 2;
        do {
            raw = RD(c->pc); op = ghost[raw]; c->pc++; n++;
            if (n > 0x20000) { c->wait = 3; goto done; }
        } while (op == 0x10 || op == 0x11);
    }
    if (hd6309_is_only(page, raw)) {
        if (c->is6309) {
            int r = hd6309_exec(c, base, n, page, raw, opc_pc);
            if (r != HD6309_UNIMPL) { n = r; goto done; }
            /* ⛔ falls through to the refusal: an encoding this build does not
             * implement is NAMED and stops, never executed as its 6809 ghost. */
        }
        if (c->undef6309) {
            c->undef6309(c->ctx, page, raw, opc_pc);
        } else {
            fprintf(stderr,
                    "cpu6809: 6309-only opcode %s (%s$%02X) at $%04X after %llu E cycles.\n"
                    "  This core is a 6809 (it models mc6809i.v). Executing it as its 6809\n"
                    "  ghost would give a wrong answer silently - see docs/6309.md.\n",
                    hd6309_name(page, raw),
                    page == 0 ? "" : (page == 1 ? "$10 " : "$11 "),
                    raw, opc_pc, (unsigned long long)c->cycles);
            abort();
        }
    }
    d = &dec[page][op];

    /* FETCH_I2 */
    if (d->mode == M_INH && d->onebyte) {
        b2 = 0;                                                         /* read and not consumed */
    } else {
        b2 = RD(c->pc); c->pc++;
    }
    n++;

    switch (d->mode) {
    case M_INH:
        switch (d->kind) {
        case I_NOP: break;
        case I_DAA: {
            uint8_t a = c->a, cor = 0;
            if ((c->cc & CC_C) || (a >> 4) > 9 || ((a >> 4) > 8 && (a & 15) > 9)) cor = 0x60;
            if ((c->cc & CC_H) || (a & 15) > 9) cor |= 0x06;
            unsigned r = (unsigned)a + cor;
            c->a = (uint8_t)r;
            c->cc = (uint8_t)((c->cc & ~(CC_N | CC_Z)) | ((r >> 8) & 1) | (c->a & 0x80 ? CC_N : 0) | (c->a ? 0 : CC_Z));
            break;
        }
        case I_SYNC: c->wait = 2; break;
        case I_MUL: {                                                   /* MUL_ACTION x 9 */
            uint16_t r = (uint16_t)(c->a * c->b);
            c->a = (uint8_t)(r >> 8); c->b = (uint8_t)r;
            c->cc = (uint8_t)((c->cc & ~(CC_Z | CC_C)) | (r ? 0 : CC_Z) | ((r >> 7) & 1));
            n += 9;
            break;
        }
        case I_RTS:
            t = (uint16_t)(RD(c->s) << 8); c->s++; n++;
            c->pc = (uint16_t)(t | RD(c->s)); c->s++; n++;
            n++;
            break;
        case I_RTI:
            c->cc = RD(c->s); c->s++; n++;
            n = pull(c, base, n, (c->cc & CC_E) ? 0xFE : 0x80, 0);
            break;
        case I_SWI:                                                     /* SWI_START, IRQ_DONTCARE, push, IRQ_DONTCARE2 */
            c->cc |= CC_E;
            n += 2;
            n = push(c, base, n, 0xFF, 0);
            n++;
            n = vector(c, base, n, page == 1 ? T_SWI2 : T_SWI);
            break;
        case I_CWAI:                                                    /* CWAI, CWAI_DONTCARE1, push, then wait */
            c->cc = (uint8_t)(CC_E | (c->cc & b2 & 0x7F));
            n += 2;
            n = push(c, base, n, 0xFF, 0);
            c->wait = 1;
            break;
        case I_SEX: c->a = (c->b & 0x80) ? 0xFF : 0x00; break;
        case I_ABX: c->x = (uint16_t)(c->x + c->b); n++; break;
        default:
            if (d->reg) { b2 = alu8(&c->cc, d->op, c->a, 0); if (d->wb) c->a = b2; }
            else        { b2 = alu8(&c->cc, d->op, c->b, 0); if (d->wb) c->b = b2; }
            break;
        }
        break;

    case M_IMM:
        switch (d->kind) {
        case S_ANDCC: c->cc &= b2; n++; break;
        case S_ORCC:  c->cc |= b2; n++; break;
        case S_PSH:   n = push(c, base, n + 3, b2, op & 2); break;
        case S_PUL:   n = pull(c, base, n + 2, b2, op & 2); break;
        case S_TFR:   tfr_set(c, b2 & 15, tfr_get(c, b2 >> 4)); n += 4; break;
        case S_EXG: {
            uint16_t va = tfr_get(c, b2 >> 4), vb = tfr_get(c, b2 & 15);
            tfr_set(c, b2 >> 4, vb);
            tfr_set(c, b2 & 15, va);
            n += 6;
            break;
        }
        case S_A8:
            if (d->reg) { op = alu8(&c->cc, d->op, c->a, b2); if (d->wb) c->a = op; }
            else        { op = alu8(&c->cc, d->op, c->b, b2); if (d->wb) c->b = op; }
            break;
        case S_A16:                                                     /* 16IMM_LO [, 16IMM_DONTCARE] */
            lo = RD(c->pc); c->pc++; n++;
            t = alu16(&c->cc, d->op, get16(c, d->reg), (uint16_t)((b2 << 8) | lo));
            if (d->wb) set16(c, d->reg, t);
            if (d->op != O16_LD) n++;
            break;
        default: break;
        }
        break;

    case M_REL: {
        int take;
        uint8_t cc = c->cc;
        if (op == 0x8D || op == 0x16 || op == 0x17) take = 1;
        else switch (op & 15) {
            case 0x0: take = 1; break;
            case 0x1: take = 0; break;
            case 0x2: take = !(cc & (CC_Z | CC_C)); break;
            case 0x3: take = (cc & (CC_Z | CC_C)) != 0; break;
            case 0x4: take = !(cc & CC_C); break;
            case 0x5: take = (cc & CC_C) != 0; break;
            case 0x6: take = !(cc & CC_Z); break;
            case 0x7: take = (cc & CC_Z) != 0; break;
            case 0x8: take = !(cc & CC_V); break;
            case 0x9: take = (cc & CC_V) != 0; break;
            case 0xA: take = !(cc & CC_N); break;
            case 0xB: take = (cc & CC_N) != 0; break;
            case 0xC: take = !(((cc >> 3) ^ (cc >> 1)) & 1); break;
            case 0xD: take = ((cc >> 3) ^ (cc >> 1)) & 1; break;
            case 0xE: take = !(((cc >> 3) ^ (cc >> 1)) & 1) && !(cc & CC_Z); break;
            default:  take = (((cc >> 3) ^ (cc >> 1)) & 1) || (cc & CC_Z); break;
        }
        if (!d->longbr) {                                               /* BRA_DONTCARE */
            n++;
            if (take) {
                t = c->pc;
                c->pc = (uint16_t)(c->pc + (int8_t)b2);
                if (op == 0x8D) {                                       /* BSR_DONTCARE1, 2, RETURNLOW, HIGH */
                    n += 2;
                    WR(--c->s, t); n++;
                    WR(--c->s, t >> 8); n++;
                }
            }
        } else {                                                        /* LBRA_OFFSETLOW, LBRA_DONTCARE */
            lo = RD(c->pc); c->pc++; n++;
            n++;
            if (take) {                                                 /* LBRA_DONTCARE2 */
                t = c->pc;
                c->pc = (uint16_t)(c->pc + ((b2 << 8) | lo));
                n++;
                if (op == 0x17) {
                    n += 2;
                    WR(--c->s, t); n++;
                    WR(--c->s, t >> 8); n++;
                }
            }
        }
        break;
    }

    case M_DIR:                                                         /* DIRECT_DONTCARE */
        ea = (uint16_t)((c->dp << 8) | b2);
        n++;
        if (d->jmp) { c->pc = ea; break; }
        n = alu_ea(c, base, n, d, ea);
        break;

    case M_EXT:                                                         /* EXTENDED_ADDRLO, EXTENDED_DONTCARE */
        lo = RD(c->pc); c->pc++; n++;
        ea = (uint16_t)((b2 << 8) | lo);
        n++;
        if (d->jmp) { c->pc = ea; break; }
        n = alu_ea(c, base, n, d, ea);
        break;

    case M_IDX: {
        int seize = 0;
        n = cpu6809_idx_ea(c, base, n, b2, &ea, &seize);
        if (seize) goto done;
        if (d->jmp) { c->pc = ea; break; }
        n = alu_ea(c, base, n, d, ea);
        break;
    }

    default: break;                                                     /* invalid: 2 bytes, 2 cycles */
    }

done:
    c->cycles += (uint64_t)n;
    if (c->s != s0) c->nmi_armed = 1;
    return n;
}
