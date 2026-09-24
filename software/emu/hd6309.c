/* The HD6309 instruction layer - see hd6309.h for why it is a separate file.
 *
 * Implemented so far (the set the SD and video drivers need):
 *   TFM          $1138-$113B   all four forms, hardware/cpu/docs/plan.md §4.3.1 semantics
 *   LDW/STW      $10 86/96/A6/B6, $10 97/A7/B7
 *   LDQ/STQ      $CD, $10 DC/EC/FC, $10 DD/ED/FD
 *   ADDW/SUBW/CMPW, ADDD/SUBD-class W forms  $10 80/81/8B/90/91/9B/A0/A1/AB/B0/B1/BB
 *   inter-register ADDR/ADCR/SUBR/SBCR/ANDR/ORR/EORR/CMPR   $1030-$1037
 *   PSHSW/PULSW/PSHUW/PULUW  $1038-$103B
 *   SEXW         $14
 *   LDMD         $113D
 *   TFR/EXG extended register codes (via hd6309_tfr_*)
 *
 * ⛔ Everything else returns HD6309_UNIMPL and is refused by name.
 *
 * ⚠ CYCLE COUNTS.  The 6309-only instructions below carry the counts from
 * Appendix A of The 6309 Book, via test/hd6309.tab.  For the instructions the
 * 6809 shares, native mode is applied by cpu6809.c as a DELTA from
 * hd6309_nm_delta[] rather than by recounting - see hd6309ops.h.
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

#define RD(ad)    (c->now = (uint64_t)(base + n), c->read(c->ctx, (uint16_t)(ad)))
#define WR(ad, v) (c->now = (uint64_t)(base + n), c->write(c->ctx, (uint16_t)(ad), (uint8_t)(v)))

/* ---- the wide registers -------------------------------------------------- */

static inline uint16_t getW(const cpu6809 *c) { return (uint16_t)((c->e << 8) | c->f); }
static inline void     setW(cpu6809 *c, uint16_t v) { c->e = (uint8_t)(v >> 8); c->f = (uint8_t)v; }
static inline uint16_t getD(const cpu6809 *c) { return (uint16_t)((c->a << 8) | c->b); }
static inline void     setD(cpu6809 *c, uint16_t v) { c->a = (uint8_t)(v >> 8); c->b = (uint8_t)v; }

/* ---- TFR/EXG postbyte codes, the 6309's reading -------------------------- */

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
    case 0x8: return (uint16_t)(0xFF00 | c->a);
    case 0x9: return (uint16_t)(0xFF00 | c->b);
    case 0xA: return (uint16_t)(0xFF00 | c->cc);
    case 0xB: return (uint16_t)(0xFF00 | c->dp);
    case 0xC: case 0xD: return 0;               /* the zero register */
    case 0xE: return (uint16_t)(0xFF00 | c->e);
    case 0xF: return (uint16_t)(0xFF00 | c->f);
    default:  return 0;
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
    case 0x8: c->a = (uint8_t)v; break;
    case 0x9: c->b = (uint8_t)v; break;
    case 0xA: c->cc = (uint8_t)v; break;
    case 0xB: c->dp = (uint8_t)v; break;
    case 0xC: case 0xD: break;                  /* the zero register: writes vanish */
    case 0xE: c->e = (uint8_t)v; break;
    case 0xF: c->f = (uint8_t)v; break;
    default: break;
    }
}

/* ---- flags --------------------------------------------------------------- */

static void nz16(cpu6809 *c, uint16_t r)
{
    c->cc = (uint8_t)((c->cc & ~(CC_N | CC_Z | CC_V)) |
                      ((r & 0x8000) ? CC_N : 0) | (r ? 0 : CC_Z));
}

static uint16_t add16(cpu6809 *c, uint16_t a, uint16_t b, int carry_in, int sub, int wb)
{
    unsigned bb = sub ? (unsigned)((uint16_t)~b) : b;
    unsigned r = (unsigned)a + bb + (unsigned)(sub ? !carry_in : carry_in);
    uint16_t rr = (uint16_t)r;
    uint8_t cc = (uint8_t)(c->cc & ~(CC_N | CC_Z | CC_V | CC_C));
    if (rr & 0x8000) cc |= CC_N;
    if (!rr) cc |= CC_Z;
    if (((a ^ rr) & (uint16_t)(bb ^ rr)) & 0x8000) cc |= CC_V;
    if (sub ? !(r & 0x10000) : (r & 0x10000)) cc |= CC_C;
    c->cc = cc;
    (void)wb;
    return rr;
}

/* ---- the addressing modes this layer needs ------------------------------- */

enum { AM_IMM, AM_DIR, AM_IDX, AM_EXT };

/* ⭐ CYCLE COUNTS ARE STATED AS TOTALS, NOT ACCUMULATED.
 *
 * `n` still walks forward through the fetches and accesses, because RD/WR use it
 * to timestamp each bus cycle - a peripheral has to see them in the right place.
 * But the value RETURNED is the instruction's length from Appendix A, written
 * out per form, because accumulating it by hand got 20 of 32 forms wrong and
 * every one of them was invisible: the instruction did the right thing and the
 * machine was simply the wrong speed. test/cyc6309.py is the gate that found
 * them and is what stops them coming back.
 *
 * ⚠ An indexed form's book figure is `n+`, the base plus the postbyte's own
 * cost. `idx_extra` is that cost measured against `,x`, which is the postbyte
 * the book's base assumes. */
#define IDXEXTRA(before, after) ((after) - (before) - 1)

/* hd6309_ea: the effective address for one of the four ordinary modes.
 * `n` is updated through the pointer.  For AM_IMM the "address" is PC and the
 * caller advances PC itself by the operand width. */
static uint16_t hd6309_ea(cpu6809 *c, int64_t base, int *np, int am, int *seize)
{
    int n = *np;
    uint16_t ea = 0;
    uint8_t b2;
    *seize = 0;
    switch (am) {
    case AM_IMM:
        ea = c->pc;
        break;
    case AM_DIR:
        b2 = RD(c->pc); c->pc++; n++;
        ea = (uint16_t)((c->dp << 8) | b2);
        break;
    case AM_EXT: {
        uint8_t hi = RD(c->pc); c->pc++; n++;
        uint8_t lo = RD(c->pc); c->pc++; n++;
        ea = (uint16_t)((hi << 8) | lo);
        break;
    }
    case AM_IDX:
        b2 = RD(c->pc); c->pc++; n++;
        n = cpu6809_idx_ea(c, base, n, b2, &ea, seize);
        break;
    }
    *np = n;
    return ea;
}

/* ---- TFM ----------------------------------------------------------------- */

/* The four forms, by opcode.  src_inc/dst_inc are +1, -1 or 0. */
static const struct { int si, di; } tfm_form[4] = {
    { +1, +1 },   /* $1138  TFM r+,r+  forward block move          */
    { -1, -1 },   /* $1139  TFM r-,r-  backward block move         */
    { +1,  0 },   /* $113A  TFM r+,r   output to a peripheral      */
    {  0, +1 },   /* $113B  TFM r,r+   input from a peripheral     */
};

static uint16_t *tfm_reg(cpu6809 *c, int code, int *ok)
{
    *ok = 1;
    switch (code) {
    case 0: return NULL;                 /* D - handled by the caller */
    case 1: return &c->x;
    case 2: return &c->y;
    case 3: return &c->u;
    case 4: return &c->s;
    default: *ok = 0; return NULL;
    }
}

/* A scratch cell so D can be used as a TFM pointer without special-casing every
 * access; copied back at the end and on every interrupt boundary. */
static int tfm_run(cpu6809 *c, int64_t base, int n, int form, uint16_t opc_pc)
{
    uint8_t pb = RD(c->pc); c->pc++; n++;
    int sc = (pb >> 4) & 15, dc = pb & 15;
    int ok1, ok2;
    uint16_t *sp = tfm_reg(c, sc, &ok1);
    uint16_t *dp = tfm_reg(c, dc, &ok2);
    uint16_t dsrc = getD(c), ddst = getD(c);

    if (!ok1 || !ok2) return HD6309_UNIMPL;     /* an invalid postbyte traps; not yet */
    if (!sp) sp = &dsrc;
    if (!dp) dp = (dc == 0 && sc == 0) ? &dsrc : &ddst;

    n += 5;                                     /* $1138.. is 6 cycles of set-up; 1 is the prefix */

    /* ⭐ hardware/cpu/docs/plan.md §4.3.1 - DECIDED 2026-09-21.  The byte in flight is
     * STORED, the pointers advance and W decrements BEFORE an interrupt is
     * recognised.  Nothing is ever held across an interrupt, so on resume there
     * is nothing to recover: the source is never re-read and the destination is
     * never written twice.  A real HD63C09E re-reads the source on the
     * fixed-source form and loses the byte; this core does not, deliberately.
     * ⚠ The interrupt is still recognised BETWEEN bytes - TFM stays
     * interruptible, at a worst-case added latency of one byte. */
    while (getW(c) != 0) {
        uint8_t v = RD(*sp);
        n++;
#ifdef HD6309_FAITHFUL_TFM
        /* ⛔ WHAT A REAL HD63C09E DOES, built only to be caught.
         * The 6309 Book, the TFM page: an interrupt "re-reads the peripheral
         * referenced by r1 WITHOUT storing the previous data byte, advancing r2,
         * or decrementing W". So the byte just read is discarded and the source
         * is read again on resume - which, for a port, is a fresh pop and a byte
         * gone. test/tfm6309.c builds this variant and REQUIRES it to fail: a
         * test that cannot see the difference between this and §4.3.1 is not
         * testing §4.3.1. */
        if (cpu6809_int_pending(c, base + n)) {
            c->pc = opc_pc;
            return n;
        }
#endif
        WR(*dp, v);
        n++;
        *sp = (uint16_t)(*sp + tfm_form[form].si);
        *dp = (uint16_t)(*dp + tfm_form[form].di);
        setW(c, (uint16_t)(getW(c) - 1));
        n++;
        if (sp == &dsrc || dp == &dsrc) setD(c, dsrc);
        if (dp == &ddst) setD(c, ddst);
        /* ⭐ THE BYTE IS COMPLETE HERE, AND THIS IS WHERE THE INTERRUPT GOES.
         * Nothing is in flight: the byte is stored, both pointers have moved and
         * W is down. Backing PC up to the opcode makes cpu6809_step take the
         * interrupt on its next call and then RE-ENTER this instruction, which
         * resumes from W/X/Y exactly where it stopped. No byte is re-read and
         * none is written twice - plan.md §4.3.1. */
        if (getW(c) != 0 && cpu6809_int_pending(c, base + n)) {
            c->pc = opc_pc;
            return n;
        }
    }
    /* ⭐ W is 0 here, ALWAYS.  Five NitrOS-9 sites depend on it, one across an
     * intervening bsr (rel.asm:400, "E=$00 already from TFM above"), and nothing
     * anywhere checks it.  hardware/cpu/docs/6309.md §5.1.5. */
    c->cc |= CC_Z;                              /* "Z' - Always set" */
    return n;
}

/* ---- the dispatch -------------------------------------------------------- */

int hd6309_exec(cpu6809 *c, int64_t base, int n, int page, uint8_t op,
                uint16_t opc_pc)
{
    int seize = 0;
    uint16_t ea, t;

    if (page == 0) {
        switch (op) {
        case 0x14:                              /* SEXW: W sign-extends into D */
            setD(c, (getW(c) & 0x8000) ? 0xFFFF : 0x0000);
            nz16(c, getW(c));
            return 2;                           /* Appendix A: 2 / 1 */
        case 0xCD: {                            /* LDQ immediate */
            uint32_t q = 0;
            for (int i = 0; i < 4; i++) { q = (q << 8) | RD(c->pc); c->pc++; n++; }
            setD(c, (uint16_t)(q >> 16)); setW(c, (uint16_t)q);
            c->cc = (uint8_t)((c->cc & ~(CC_N | CC_Z | CC_V)) |
                              ((q & 0x80000000u) ? CC_N : 0) | (q ? 0 : CC_Z));
            return 5;                           /* LDQ # : 5 / 5 */
        }
        default: return HD6309_UNIMPL;
        }
    }

    if (page == 1) {
        /* ---- inter-register $1030-$1037 --------------------------------- */
        if (op >= 0x30 && op <= 0x37) {
            uint8_t pb = RD(c->pc); c->pc++; n++;
            int sc = (pb >> 4) & 15, dc = pb & 15;
            uint16_t sv = hd6309_tfr_get(c, sc), dv = hd6309_tfr_get(c, dc);
            int eight = hd6309_tfr_is8(dc);
            uint16_t r;
            switch (op) {
            case 0x30: r = add16(c, dv, sv, 0, 0, 1); break;              /* ADDR */
            case 0x31: r = add16(c, dv, sv, c->cc & CC_C, 0, 1); break;   /* ADCR */
            case 0x32: r = add16(c, dv, sv, 0, 1, 1); break;              /* SUBR */
            case 0x33: r = add16(c, dv, sv, c->cc & CC_C, 1, 1); break;   /* SBCR */
            case 0x34: r = (uint16_t)(dv & sv); nz16(c, r); break;        /* ANDR */
            case 0x35: r = (uint16_t)(dv | sv); nz16(c, r); break;        /* ORR  */
            case 0x36: r = (uint16_t)(dv ^ sv); nz16(c, r); break;        /* EORR */
            default:   add16(c, dv, sv, 0, 1, 0); return 4;               /* CMPR */
            }
            if (eight) hd6309_tfr_set(c, dc, (uint16_t)(r & 0xFF));
            else       hd6309_tfr_set(c, dc, r);
            return 4;                           /* ADDR..EORR: 4 / 4 */
        }
        /* ---- PSHSW / PULSW / PSHUW / PULUW ------------------------------ */
        if (op >= 0x38 && op <= 0x3B) {
            uint16_t *stk = (op < 0x3A) ? &c->s : &c->u;
            if (op == 0x38 || op == 0x3A) {                 /* push W */
                WR(--(*stk), c->f); n++;
                WR(--(*stk), c->e); n++;
                return 6;                       /* PSHSW/PSHUW: 6 / 6 */
            }
            c->e = RD((*stk)++); n++;                       /* pull W */
            c->f = RD((*stk)++); n++;
            return 6;                           /* PULSW/PULUW: 6 / 6 */
        }
        /* ---- LDW/STW/ADDW/SUBW/CMPW, LDQ/STQ ---------------------------- */
        {
            int am, base_op = op & 0x3F, have = 1;
            switch (op & 0xF0) {
            case 0x80: am = AM_IMM; break;
            case 0x90: am = AM_DIR; break;
            case 0xA0: am = AM_IDX; break;
            case 0xB0: am = AM_EXT; break;
            case 0xD0: am = AM_DIR; break;
            case 0xE0: am = AM_IDX; break;
            case 0xF0: am = AM_EXT; break;
            default: have = 0; am = AM_IMM; break;
            }
            if (have) {
                int lo = op & 0x0F;
                int q = (op & 0xF0) >= 0xD0;
                if (q && (lo == 0x0C || lo == 0x0D)) {      /* LDQ / STQ */
                    int n0 = n;
                    ea = hd6309_ea(c, base, &n, am, &seize);
                    if (seize) return n;
                    /* DIR 8, IDX 8+, EXT 9 - the same for load and store */
                    int total = (am == AM_EXT) ? 9 : 8;
                    if (am == AM_IDX) total += IDXEXTRA(n0 + 1, n);
                    if (lo == 0x0C) {                        /* LDQ */
                        uint32_t v = 0;
                        for (int i = 0; i < 4; i++) { v = (v << 8) | RD((uint16_t)(ea + i)); n++; }
                        setD(c, (uint16_t)(v >> 16)); setW(c, (uint16_t)v);
                        c->cc = (uint8_t)((c->cc & ~(CC_N | CC_Z | CC_V)) |
                                          ((v & 0x80000000u) ? CC_N : 0) | (v ? 0 : CC_Z));
                    } else {                                 /* STQ */
                        uint32_t v = ((uint32_t)getD(c) << 16) | getW(c);
                        for (int i = 0; i < 4; i++) { WR((uint16_t)(ea + i), (v >> (24 - 8 * i)) & 0xFF); n++; }
                        c->cc = (uint8_t)((c->cc & ~(CC_N | CC_Z | CC_V)) |
                                          ((v & 0x80000000u) ? CC_N : 0) | (v ? 0 : CC_Z));
                    }
                    return total;
                }
                if (!q) {
                    switch (base_op & 0x0F) {
                    case 0x00: case 0x01: case 0x02: case 0x06:
                    case 0x07: case 0x0B:
                        break;
                    default: have = 0; break;
                    }
                }
                if (have && !q) {
                    int lo2 = op & 0x0F;
                    if (lo2 == 0x07 && am == AM_IMM) return HD6309_UNIMPL;  /* no STW # */
                    int n0 = n;
                    ea = hd6309_ea(c, base, &n, am, &seize);
                    if (seize) return n;
                    /* Appendix A. LDW/STW are one cheaper than the ALU forms in
                     * every mode but immediate, where LDW is 4 and they are 5. */
                    int alu = (lo2 != 0x06 && lo2 != 0x07);
                    int total = am == AM_IMM ? (alu ? 5 : 4)
                              : am == AM_DIR ? (alu ? 7 : 6)
                              : am == AM_EXT ? (alu ? 8 : 7)
                                             : (alu ? 7 : 6);
                    if (am == AM_IDX) total += IDXEXTRA(n0 + 1, n);
                    if (lo2 == 0x07) {                       /* STW */
                        WR(ea, c->e); n++;
                        WR((uint16_t)(ea + 1), c->f); n++;
                        nz16(c, getW(c));
                        return total;
                    }
                    t = (uint16_t)(RD(ea) << 8); n++;
                    t |= RD((uint16_t)(ea + 1)); n++;
                    if (am == AM_IMM) c->pc = (uint16_t)(c->pc + 2);
                    switch (lo2) {
                    case 0x00: setW(c, add16(c, getW(c), t, 0, 1, 1)); break;   /* SUBW */
                    case 0x01: add16(c, getW(c), t, 0, 1, 0); break;            /* CMPW */
                    case 0x06: setW(c, t); nz16(c, t); break;                   /* LDW  */
                    case 0x0B: setW(c, add16(c, getW(c), t, 0, 0, 1)); break;   /* ADDW */
                    default: return HD6309_UNIMPL;
                    }
                    return total;
                }
            }
        }
        return HD6309_UNIMPL;
    }

    /* ---- page 2 ($11) ---------------------------------------------------- */
    if (op >= 0x38 && op <= 0x3B) return tfm_run(c, base, n, op - 0x38, opc_pc);
    if (op == 0x3D) {                                       /* LDMD */
        uint8_t v = RD(c->pc); c->pc++; n++;
        c->md = (uint8_t)((c->md & 0xC0) | (v & 0x03));
        return 5;                               /* LDMD #: 5 / 5 */
    }
    return HD6309_UNIMPL;
}
