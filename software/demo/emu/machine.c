/* machine.c -- the demo ROM on a host: a 6809, the map, and the video and
 * audio cards as features.md describes them, fast enough to iterate on.
 *
 *   emu ROM.bin OUTDIR SECONDS        (software/demo/emu/run-emu.sh builds it)
 *
 * ⚠ THIS IS NOT THE MACHINE. hardware/gal/verilog/run-demo.sh is: a 6809E core
 * somebody else wrote, the motherboard and both cards as fitted, at a few
 * minutes of wall clock per second of machine. This is the card as the
 * documents SAY it behaves - graphics.md 7.4, 10.3, 11, 13 - so a picture that
 * is right here and wrong there is a finding about the card or about the
 * documents, and one that is wrong here is a finding about the 6809 code,
 * found in seconds instead of hours.
 *
 * What it models, and the three places it is calibrated rather than read:
 *   - the span writer's four WMODEs, WADV 01's column reload from the CPU's
 *     last WPTR0/WPTR1 writes, and the 1024-column wrap that keeps a stream
 *     in its row;
 *   - SPANBUSY as time: four dots a retired byte (one fetch slot), twice that
 *     in cell mode, and a VDATA access under it stalls the CPU (/WAIT);
 *   - VDATA reads at WPTR, post-increment - at $FF75, and through the MMU's
 *     VRAM window: a map entry of $00:$40-$7F (physical 0.5-1.0 MB), where
 *     every address is the same port (graphics.md 6.3, vctrl.v's VRAMSEL);
 *   - the palette: PDATH commits and PIDX steps;
 *   - VSCROLL latched at the top of the frame, HSCROLL at every line;
 *   - cell mode's concatenated tile address (graphics.md 6.4.1);
 *   - the display list: MOVE, WAIT, END. ⭐ bench/calib.asm measured where an
 *     effect lands: a MOVE after n WAITs from a GO inside line 0 shows on line
 *     n, and a MOVE before the first WAIT on line 1. Resuming at each line's
 *     start and rendering the line after is exactly that;
 *   - the VBL interrupt at VSYNC's leading edge - twelve lines after VBLANK's
 *     rise in the 449-line family, which is when demo_tb saw /IRQ reach the
 *     CPU, and ten in the 525-line family (sync.timing.ts) - pending until
 *     VSTAT is written;
 *   - graphics.md 10.3.3's rule, enforced: a CPU write to the card's
 *     registers while a list runs is reported, and fails the run - and so is
 *     one under a span (7.4: the span's colour and column reload are read from
 *     the register file);
 *   - the audio card: audio/refplayer/card.c, the register-level model with
 *     the four channels, the sample RAM, the tempo timer and the interrupt
 *     block, stepped per colour clock to the CPU's time; ⚠ ASTAT b6, the host
 *     port's busy bit, is never set (card.c does not model the slot walk).
 *     And its register stream in
 *     demo_tb's card.trace format, so it can be diffed against refplayer;
 *   - the map's two tasks: TASK is bit 0 of any write to $FFB0-$FFBF
 *     (machine.md 3: U3's CTRLCP does not see A0), and the entry for a
 *     logical block is {TASK, block};
 *   - the video card's register file: a register reads back the last byte
 *     the CPU wrote to it (graphics.md 13), except VSTAT and VDATA;
 *   - the TL16C550C at $FF38 (io/serial/docs/serial.md 7): divisor latch,
 *     16-byte FIFOs drained and filled at the programmed baud rate, IIR's
 *     priorities, and INTR on the shared /IRQ. Transmitted bytes go to
 *     OUTDIR/serial.out and stdout; SERIAL_IN names a file whose bytes are
 *     received from SERIAL_AT seconds on, and SERIAL_STOP a string that ends
 *     the run when it has been transmitted. That is how software/nitros9/
 *     boots NitrOS-9 here;
 *   - the PS/2 card and a keyboard and mouse at the line level - ps2_* below,
 *     which says what it models. PS2_KBD, PS2_MOUSE and PS2_AT script them,
 *     and PS2_DEBUG traces the devices' state.
 *
 * For a session scripted like a person at the terminal (software/nitros9/
 * video/): SERIAL_GATE=str holds each line of SERIAL_IN until str has been
 * transmitted since the line before it (the shell's prompt), SERIAL_TYPE=ms
 * spaces the characters, SERIAL_THINK=ms waits after the gate opens, and a
 * $01 byte in SERIAL_IN is a one-second pause that is not sent.
 * SERIAL_TIMES=file writes "ps hex" for every transmitted byte.
 * PS2_KBD_GATE and PS2_MOUSE_GATE hold that device's script until the string
 * has been transmitted, and "w<ms>" in a PS/2 script is a pause.
 *
 * What it records is demo_tb's frames.bin, so tools/checkdemo.py and
 * tools/mkvideo.py read either. MARKS=addr moves the words each frame records
 * (checkpoint, raster phase, camera and hero records, missed flips) to five
 * words at a logical address, and writes marks.txt as demo_tb does - how
 * software/nitros9/ reads them from the video console's globals.
 *
 * LISTLOG=from,to,pc[,pc...] logs, between two machine seconds, every change of
 * LRUN and every arrival at the given PCs (up to 16, from build/demo.lst), each
 * with its raster line. Use it to find which work pushes a frame's display
 * list past line 0. It is how gui.asm's lyield and wready's /FIRQ hold were
 * found.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* a string the serial port must transmit before something may proceed */
typedef struct { const char *s; size_t n, match; int open; } gate_t;
static void gate_init(gate_t *g, const char *env)
{
    g->s = getenv(env); g->n = g->s ? strlen(g->s) : 0; g->match = 0; g->open = g->n == 0;
}
static void gate_feed(gate_t *g, uint8_t v)
{
    if (g->open || !v) return;
    if ((char)v == g->s[g->match]) { if (++g->match == g->n) { g->open = 1; g->match = 0; } }
    else g->match = ((char)v == g->s[0]) ? 1 : 0;
}
static gate_t ser_gate, kbd_gate, mouse_gate;
#include "cpu6809.h"
#include "card.h"                   /* audio/refplayer: the audio card, register level */

#define DOTS_PER_E   12          /* E = 25.175 MHz / 12 */
#define DOTS_LINE    800
#define DOT_PS       39722ULL
/* ps a byte for the copy engine: two accesses a byte out of graphics.md
 * §2.1's 8.1 M spare accesses a second = 4.05 MB/s (plan §6.1). */
#define COPY_PS      246913ULL

typedef struct {
    cpu6809 cpu;
    uint8_t rom[1 << 20];
    uint8_t *ram[65536];         /* SIMM pages, allocated on first touch */
    uint8_t maphi[16], maplo[16];
    uint8_t task;                /* $FFB0-$FFBF bit 0 */
    uint8_t progress;

    /* video */
    uint8_t vram[1 << 19];
    uint8_t ctrl, vs_lo, vs_hi, hs_lo, hs_hi, spanlen, wfg, wbg, wadv;
    uint8_t wp0, wp1;            /* the register file's +$08/+$09: WADV 01's column */
    uint32_t wptr;
    uint8_t pidx, pdatl, tilebase, mapbase;
    uint8_t regfile[32];         /* graphics.md 13: what a register reads back */
    uint16_t pal[256];

    /* ⭐ video3 (video3/docs/plan.md), selected by VIDEO3=1. A SECOND CARD
     * MODEL, not a replacement: run-emu.sh, run-vid.sh and run-nitros9 all
     * drive `video`, and swapping it out would take the regression suite with
     * it. The five functions that ARE the card - video_write, video_read,
     * vram_write, vram_read, render_line - dispatch on m->v3. */
    int v3;
    uint16_t pal3[1 << 16];      /* plan 3: the LUT is 64Kx16 and video3 uses it all */
    uint16_t pidx3;              /* plan 10: 16 bits, +$0E/+$0F */
    uint32_t cptr;               /* plan 6: copyrect source */
    uint16_t cwidth, cheight;
    uint8_t cctrl;
    uint8_t sprx_lo, spry_lo, sprh, spridx, sprshape[64];   /* plan §7: 16 x 16, four bytes a row */
    long v3_violations;

    int irq_pending;
    int irq_line_due;            /* the line /IRQ reaches the CPU on, or -1 */
    long list_violations, span_violations;
    uint64_t busy_until;         /* dots: the SPAN writer, VSTAT b7 */
    uint64_t copy_until;         /* dots: the COPY engine, VSTAT b4 */
    int lrun, lwait;
    uint16_t vs_frame;
    uint64_t dots, line_start;
    int line;                    /* of the frame */
    int total_lines;

    /* audio */
    card_t card;                 /* audio/refplayer/card.c, stepped per colour clock */
    uint8_t sram[CARD_SRAM_BYTES];
    int firq;
    int trace_tick, music_marked;
    FILE *trace, *times;

    /* serial: TL16C550C */
    uint8_t u_ier, u_lcr, u_mcr, u_scr, u_dll, u_dlm, u_fcr;
    uint8_t rx[16]; int rx_n, rx_head;
    int tx_n;                    /* bytes in the transmit FIFO + shift register */
    int thre_int;                /* THRE interrupt pending (cleared by IIR read / THR write) */
    uint64_t tx_next, rx_next;   /* cycles */
    uint64_t rx_last;            /* cycles: the last character in or out of the RX FIFO (the timeout's clock) */
    FILE *ser_out;
    const uint8_t *ser_in; long ser_in_n, ser_in_pos;
    uint64_t ser_at;             /* cycles */
    const char *ser_stop; size_t ser_stop_len, ser_match;
    int stop;
    FILE *ser_times;
    uint64_t ser_type, ser_think; /* cycles */

    /* PS/2 - io/ps2/docs/ps2.md 8; the ports and devices are ps2_* below */
    uint8_t ioctrl;
    uint8_t kdata[2], kdr[2];

    /* frames */
    FILE *frames;
    uint16_t *cur, *prv;
    int frame_n, prv_w, prv_h, have_prev;
    uint16_t ck0, ph0, lrun1;
    uint8_t m0;                         /* VMODE0 as the last frame ended: vctrl's M0 (H8) */
    uint8_t lgo;                        /* a GO written in vertical blank, held to its end: vsup's LGO (H14) */
    uint8_t ppend, in_list;             /* a CPU palette commit posted to the next HLOAD: vsup's PPEND (H7) */
    uint16_t ppval;
    long pal_violations;
    uint16_t mk_ck, mk_ph, mk_camk, mk_herok, mk_missed;   /* where the frame words are read (MARKS) */
    FILE *marks;                        /* MARKS: marks.txt, as demo_tb writes it */
    int mk_latched; uint8_t mk_hi, mk_lo; /* MARKS: the block the words live in, as mapped 5 s in */
    uint64_t frame_t;
    int frame_active;
} M;

static M *m;
static uint16_t *atexit_ring;
static unsigned *atexit_ri;

/* ------------------------------------------------------------------ memory */
static uint8_t *rampage(uint8_t hi, uint8_t lo)
{
    unsigned k = ((unsigned)hi << 8) | lo;
    if (!m->ram[k]) m->ram[k] = calloc(8192, 1);
    return m->ram[k];
}

static unsigned entry(uint16_t la) { return ((unsigned)m->task << 3) | (la >> 13); }

static uint16_t ram16(uint16_t la)
{
    /* MARKS's words are read from the block that held them 5 machine seconds in:
     * a kernel moving a map slot for a moment must not make a frame's words garbage */
    if (m->marks && la >= m->mk_ck && la < (uint16_t)(m->mk_ck + 10)) {
        if (!m->mk_latched && m->dots * DOT_PS >= 5000000000000ULL) {
            m->mk_hi = m->maphi[la >> 13]; m->mk_lo = m->maplo[la >> 13]; m->mk_latched = 1;
        }
        if (m->mk_latched) {
            uint8_t *q = rampage(m->mk_hi, m->mk_lo);
            uint16_t o = la & 0x1FFF;
            return (uint16_t)((q[o] << 8) | q[(o + 1) & 0x1FFF]);
        }
    }
    uint8_t *p = rampage(m->maphi[la >> 13], m->maplo[la >> 13]);   /* task 0: the demo's */
    uint16_t o = la & 0x1FFF;
    return (uint16_t)((p[o] << 8) | p[(o + 1) & 0x1FFF]);
}

static void stall_for_span(void)
{
    uint64_t now = m->dots;
    if (m->busy_until > now) {
        uint64_t e = (m->busy_until - now + DOTS_PER_E - 1) / DOTS_PER_E;
        m->cpu.cycles += e;
        m->dots += e * DOTS_PER_E;
    }
}


static void wstep(void)
{
    m->wptr = (m->wptr & ~(uint32_t)1023) | ((m->wptr + 1) & 1023);
}

static void span_end(void)
{
    if (m->wadv != 0 && !m->lrun) {     /* 01, 10 and 11 all advance a row: vctrl.v's WROWADV */
        uint32_t row = ((m->wptr >> 10) + 1) & 511;
        uint32_t col = (((uint32_t)m->wp1 & 3) << 8) | m->wp0;
        m->wptr = (row << 10) | col;
    }
}

static void vram_write(uint8_t v)
{
    stall_for_span();
    /* ⛔ WMODE IS IN DIFFERENT BITS ON THE TWO CARDS - b4..3 on video/ and
     * b5..4 on video3, where b3..2 became the MODE field (plan §10).  Reading
     * video/'s position on a video3 CTRL turns span-mask into span-solid,
     * which is what painted the CP437 font as 2,048 solid pixels. */
    int mode = m->v3 ? ((m->ctrl >> 4) & 3) : ((m->ctrl >> 3) & 3), n;
    switch (mode) {
    case 0:
        m->vram[m->wptr] = v; wstep(); n = 1; break;
    case 1:
        for (int i = 0; i < 8; i++) { m->vram[m->wptr] = (v & (0x80 >> i)) ? m->wfg : m->wbg; wstep(); }
        n = 8; break;
    case 2:
        n = m->spanlen + 1;
        for (int i = 0; i < n; i++) { m->vram[m->wptr] = m->wfg; wstep(); }
        break;
    default:
        for (int i = 0; i < 8; i++) { if (v & (0x80 >> i)) m->vram[m->wptr] = m->wfg; wstep(); }
        n = 8; break;
    }
    span_end();
    /* a cell mode takes the bus one slot in two: video/'s CELL is b5, and
     * video3's MODE field is b3..2 with 0 = bitmap */
    int cell = m->v3 ? (((m->ctrl >> 2) & 3) != 0) : ((m->ctrl & 0x20) != 0);
    int slot = cell ? 8 : 4;
    m->busy_until = m->dots + DOTS_PER_E + (uint64_t)n * slot;
}

static uint8_t vram_read(void)
{
    stall_for_span();
    uint8_t v = m->vram[m->wptr];
    wstep();
    return v;
}

static void list_run(void);

static int in_vblank(void);

/* ===================== video3 =====================================
 *
 * video3/docs/plan.md. What differs from `video`, and nothing else does:
 *   §10  a different register map - MODE in CTRL b3..2, PIDX 16 bits,
 *        copyrect at +$12..+$17, the sprite at +$1A..+$1E
 *   §3   the LUT address is SIXTEEN bits: the pixel byte on A7..A0 and an
 *        ATTRIBUTE on A15..A8 - the cell's in character mode, the sprite's
 *        code in bitmap mode
 *   §2.5 the character map is TWO bytes a cell on a 1024-byte stride, six-bit
 *        cell row, NO ring and NO horizontal scroll
 *   §6   a copy engine
 *   §7   one 8x8 two-bit sprite, bitmap mode only
 *   §0   no display list
 *
 * ⚠ THIS IS A FUNCTIONAL MODEL. It answers "does the ATTR path produce the
 * right pixels", which is the half of plan §14 item 1 that a model can reach.
 * It does NOT model the fetch cadence, so plan §14 item 8 - five requesters
 * against one spare access a slot - is still open and still needs Verilator.
 */

#define V3_MODE(m_)   (((m_)->ctrl >> 2) & 3)      /* 0 bitmap, 1 character, 2 tile */
#define V3_WMODE(m_)  (((m_)->ctrl >> 4) & 3)

static void vram_write(uint8_t v);
static uint8_t vram_read(void);

/* plan §6: the copy, done at once. The engine's TIME is modelled as busy_until
 * the way a span is; its ORDER is modelled exactly, because an overlapping
 * scroll that runs the wrong way is the defect this model exists to catch. */
static void v3_copy(void)
{
    uint32_t w = m->cwidth, h = m->cheight;
    if (!w || !h) return;
    /* ⛔ CCTRL b1 and b2 are RESERVED since v3ptr's fit (2026-09-16): the
     * up/down counters cost 18 macrocells and 16 cascades, the difference
     * between 128/128 and 110/128, so the engine counts UP only.  An
     * overlapping copy stages through scratch in two ascending passes. */
    int rowdir = 1, coldir = 1;
    if (m->cctrl & 6) fprintf(stderr, "FAIL  %.3f s: CCTRL b1/b2 are reserved - "
                              "the copy engine has no direction bits\n",
                              (double)m->dots * DOT_PS / 1e12);
    uint32_t sc = m->cptr & 1023, sr = (m->cptr >> 10) & 511;
    uint32_t dc = m->wptr & 1023, dr = (m->wptr >> 10) & 511;
    for (uint32_t y = 0; y < h; y++) {
        /* ⭐ CPTR and WPTR name the FIRST CELL PROCESSED and the direction bits
         * step from there (plan §6.2, corrected 2026-09-16).  Naming the ORIGIN
         * and walking inside the rectangle would need origin + h - 1, which is
         * an adder, and graphics.md 6.4.1 says this card has none. */
        uint32_t syr = (rowdir > 0 ? sr + y : sr - y) & 511;
        uint32_t dyr = (rowdir > 0 ? dr + y : dr - y) & 511;
        for (uint32_t x = 0; x < w; x++) {
            uint32_t sx = (coldir > 0 ? sc + x : sc - x) & 1023;
            uint32_t dx = (coldir > 0 ? dc + x : dc - x) & 1023;
            m->vram[((dyr << 10) | dx) & 0x7FFFF] = m->vram[((syr << 10) | sx) & 0x7FFFF];
        }
    }
    /* plan §6.1: ⛔ THE FOUR-BYTE GROUP IS WITHDRAWN (§13.3 trade 1, settled
     * in 647f4f3).  One read access and one write access move ONE byte, so
     * the engine runs at 4.05 MB/s in EVERY case and column congruence does
     * not matter.  ⚠ This model charged the withdrawn group until 2026-09-18
     * and so ran the copy at 12.59 MB/s - 3.1x the design - which is what
     * made the Paint scroll in the demo video about twice too fast.
     * hardware/video3/timing.check.ts is the arithmetic; COPY_PS agrees with
     * its BYTE_MBPS, and plan §6.1's table is the same number in ms. */
    (void)sc; (void)dc;
    m->copy_until = m->dots + DOTS_PER_E + (uint64_t)w * h * COPY_PS / DOT_PS;
}

static void v3_video_write(uint8_t r, uint8_t v)
{
    if (r != 0x0C) m->regfile[r & 31] = v;
    switch (r) {
    case 0x00: m->ctrl = v; break;
    case 0x01: m->vs_lo = v; break;
    case 0x02: m->vs_hi = v & 1; break;
    case 0x03: m->hs_lo = v; break;
    case 0x04: m->hs_hi = v & 3; break;
    case 0x05: m->spanlen = v; break;
    case 0x06: m->wfg = v; break;
    case 0x07: m->wbg = v; break;
    case 0x08: m->wp0 = v; m->wptr = (m->wptr & ~(uint32_t)0xFF) | v; break;
    case 0x09: m->wp1 = v; m->wptr = (m->wptr & ~(uint32_t)0xFF00) | ((uint32_t)v << 8); break;
    case 0x0A: m->wptr = (m->wptr & 0xFFFF) | ((uint32_t)(v & 7) << 16); break;
    case 0x0B: m->wadv = v & 3; break;
    case 0x0C: vram_write(v); break;
    case 0x0D: m->irq_pending = 0; break;
    case 0x0E: m->pidx3 = (uint16_t)((m->pidx3 & 0xFF00) | v); break;
    case 0x0F: m->pidx3 = (uint16_t)((m->pidx3 & 0x00FF) | ((uint16_t)v << 8)); break;
    case 0x10: m->pdatl = v; break;
    case 0x11: m->pal3[m->pidx3++] = (uint16_t)((v << 8) | m->pdatl); break;
    case 0x12: m->cptr = (m->cptr & ~(uint32_t)0xFF) | v; break;
    case 0x13: m->cptr = (m->cptr & ~(uint32_t)0xFF00) | ((uint32_t)v << 8); break;
    case 0x14: m->cptr = (m->cptr & 0xFFFF) | ((uint32_t)(v & 7) << 16); break;
    case 0x15: m->cwidth = (uint16_t)((m->cwidth & 0x300) | v); break;
    case 0x16: m->cheight = (uint16_t)((m->cheight & 0x100) | v); break;
    case 0x17:
        m->cwidth  = (uint16_t)((m->cwidth  & 0xFF) | ((v & 0x18) << 5));
        m->cheight = (uint16_t)((m->cheight & 0xFF) | ((v & 0x20) << 3));
        m->cctrl = v;
        if (v & 1) v3_copy();
        break;
    case 0x18: m->tilebase = v & 31; break;
    case 0x19: m->mapbase = v & 7; break;
    case 0x1A: m->sprx_lo = v; break;
    case 0x1B: m->spry_lo = v; break;
    case 0x1C: m->sprh = v; break;
    case 0x1D: m->spridx = v & 63; break;
    case 0x1E: m->sprshape[m->spridx & 63] = v; m->spridx = (uint8_t)((m->spridx + 1) & 63); break;
    default: break;
    }
}

static int in_vblank(void);

static uint8_t v3_video_read(uint8_t r)
{
    switch (r) {
    case 0x0C: return vram_read();
    case 0x0D: {
        uint64_t col = m->dots - m->line_start;
        /* ⚠ b4 IS THE COPY ENGINE, and it was never set here until
         * 2026-09-18: vidcpy3.asm's CpWait and ca_v3txt.asm's TxCWait poll
         * exactly this bit, so until it moved they had never once spun. */
        return (uint8_t)((m->busy_until > m->dots ? 0x80 : 0) | (in_vblank() ? 0x40 : 0)
                         | (col >= 640 ? 0x20 : 0) | (m->copy_until > m->dots ? 0x10 : 0)
                         | (m->irq_pending ? 1 : 0));
    }
    default: return m->regfile[r & 31];
    }
}

/* ===================== end video3 ================================= */

static void video_write(uint8_t r, uint8_t v)
{
    if (m->v3) { v3_video_write(r, v); return; }
    if (r != 0x15) m->regfile[r & 31] = v;
    switch (r) {
    case 0x00: m->ctrl = v; break;
    case 0x01: m->vs_lo = v; break;
    case 0x02: m->vs_hi = v & 1; break;
    case 0x03: m->hs_lo = v; break;
    case 0x04: m->hs_hi = v & 3; break;
    case 0x05: m->spanlen = v; break;
    case 0x06: m->wfg = v; break;
    case 0x07: m->wbg = v; break;
    case 0x08: m->wp0 = v; m->wptr = (m->wptr & ~(uint32_t)0xFF) | v; break;
    case 0x09: m->wp1 = v; m->wptr = (m->wptr & ~(uint32_t)0xFF00) | ((uint32_t)v << 8); break;
    case 0x0A: m->wptr = (m->wptr & 0xFFFF) | ((uint32_t)(v & 7) << 16); break;
    case 0x0E:                          /* GO: at once, or armed to the blank's end (graphics.md 10.3.1) */
        if (v & 1) {
            if (in_vblank()) m->lgo = 1;
            else { m->lrun = 1; m->lwait = 0; list_run(); }
        }
        break;
    case 0x10: case 0x11: case 0x12:
        /* graphics.md 13.1: a CPU's PDATH write posts the commit to the next
         * HLOAD, and VSTAT b1 holds until it is done; in vertical blanking, and
         * for a list's MOVE, it commits at once. A palette write while one is
         * posted breaks the rule. */
        if (m->ppend && !m->in_list && ++m->pal_violations <= 8)
            fprintf(stderr, "FAIL  %.3f s: the CPU wrote $%04X := $%02X while a palette commit was posted (PC $%04X)\n",
                    (double)m->dots * DOT_PS / 1e12, 0xFF60 + r, v, m->cpu.pc);
        if (r == 0x10) m->pidx = v;
        else if (r == 0x11) m->pdatl = v;
        else if (m->in_list || in_vblank()) m->pal[m->pidx++] = (uint16_t)((v << 8) | m->pdatl);
        else { m->ppend = 1; m->ppval = (uint16_t)((v << 8) | m->pdatl); }
        break;
    case 0x13: m->irq_pending = 0; break;
    case 0x14: m->wadv = v & 3; break;
    case 0x15: vram_write(v); break;
    case 0x17: m->tilebase = v & 31; break;
    case 0x19: m->mapbase = v & 127; break;
    default: break;
    }
}


static int active_lines(void);


static uint8_t video_read(uint8_t r)
{
    if (m->v3) return v3_video_read(r);
    switch (r) {
    case 0x13: {
        uint64_t col = m->dots - m->line_start;
        return (uint8_t)((m->busy_until > m->dots ? 0x80 : 0) | (in_vblank() ? 0x40 : 0)
                         | (col >= 640 ? 0x20 : 0) | (m->lrun ? 0x10 : 0) | (m->ppend ? 0x02 : 0)
                         | (m->irq_pending ? 1 : 0));
    }
    case 0x15: return vram_read();
    default: return m->regfile[r & 31];
    }
}

/* the list engine: walk WPTR until a WAIT or END */
static void list_run(void)
{
    int guard = 0;
    while (m->lrun && !m->lwait && guard++ < 4096) {
        uint8_t op = m->vram[m->wptr]; wstep();
        if (op & 0x80) {
            if ((op & 0x1F) == 0x1F) m->lrun = 0;
            else m->lwait = 1;
        } else {
            uint8_t v = m->vram[m->wptr]; wstep();
            uint8_t r = op & 0x1F;
            if (r == 0x03 || r == 0x04 || r == 0x10 || r == 0x11 || r == 0x12) {
                m->in_list = 1; video_write(r, v); m->in_list = 0;
            }
        }
    }
}

/* The audio card is audio/refplayer/card.c - the register-level model its
 * own benches use - stepped to the CPU's time before every access and every
 * look at /FIRQ: one colour clock is 2,097,917 / 3,546,895 E cycles. */
static void audio_catchup(void)
{
    uint64_t want = m->cpu.cycles * 3546895ULL / 2097917ULL;
    while (m->card.cc < want) card_step(&m->card);
}

static uint8_t audio_read(uint8_t r)
{
    audio_catchup();
    /* ⚠ Where the card and card.c differ, the card wins (CLAUDE.md): U1's
     * prefetch captures lanes 0-1 only (audio.cpld.ts), so SDATA and the
     * state file's lane-2 bytes - VOL and PTR[18:16] - read back as 0. */
    if (r == A_SDATA) { (void)card_read(&m->card, r); return 0; }
    if (r == A_ADATA) {
        unsigned off = m->card.aidx % 16u;
        uint8_t v = card_read(&m->card, r);
        return (off == ST_VOL || off == ST_PTR2) ? 0 : v;
    }
    return card_read(&m->card, r);
}

static void audio_write(uint8_t r, uint8_t v)
{
    static const char *names[16] = {"AIDX", "ADATA", "ADMACON", "AINTENA", "AINTREQ", "ACTRL", "SPTR2",
                                    "SPTR1", "SPTR0", "SDATA", "ASTAT", "TIMER1", "TIMER0", "R13", "R14", "R15"};
    if (r == 0 && !m->music_marked) m->music_marked = 1;
    if (r == 4 && v == 0x10) m->trace_tick++;
    if (m->trace && (r < 6 || r > 9)) {
        fprintf(m->trace, "%06d %-7s %02X\n", m->trace_tick, names[r], v);
        /* ... and when, in colour clocks (3,546,895 Hz), for tracewav's render */
        fprintf(m->times, "%llu %x %02X\n", (unsigned long long)(m->cpu.cycles * 3546895ULL / 2097917ULL), r, v);
    }
    audio_catchup();
    card_write(&m->card, r, v);
}

/* ------------------------------------------------------------------ serial */
static uint64_t uart_bit_cycles(void)
{
    unsigned div = ((unsigned)m->u_dlm << 8) | m->u_dll;
    if (!div) div = 1;
    /* 10 bits a character at 7,372,800 / 16 / div baud, in E cycles */
    return (10ULL * 16 * div * 2097917ULL) / 7372800ULL;
}

/* The receive interrupt is the FIFO reaching FCR's trigger level, or a
 * character-timeout four character times after the FIFO last moved with
 * anything in it (IIR $0C). sc16550 reads exactly the trigger level's bytes
 * on IIR $04 without checking LSR, so this distinction is not cosmetic. */
static int uart_rx_level(void)
{
    static const int trig[4] = {1, 4, 8, 14};
    int t = (m->u_fcr & 1) ? trig[(m->u_fcr >> 6) & 3] : 1;
    return m->rx_n >= t;
}

static int uart_rx_timeout(void)
{
    return m->rx_n && m->cpu.cycles >= m->rx_last + 4 * uart_bit_cycles();
}

static int uart_irq(void)
{
    if ((m->u_ier & 1) && (uart_rx_level() || uart_rx_timeout())) return 1;
    if ((m->u_ier & 2) && m->thre_int) return 1;
    return 0;
}

static uint8_t uart_read(uint8_t r)
{
    int dlab = m->u_lcr & 0x80;
    switch (r) {
    case 0:
        if (dlab) return m->u_dll;
        if (m->rx_n) { uint8_t v = m->rx[m->rx_head]; m->rx_head = (m->rx_head + 1) & 15; m->rx_n--; m->rx_last = m->cpu.cycles; return v; }
        return 0;
    case 1: return dlab ? m->u_dlm : m->u_ier;
    case 2: {
        uint8_t fifo = (m->u_fcr & 1) ? 0xC0 : 0;
        if ((m->u_ier & 1) && uart_rx_level()) return fifo | 0x04;
        if ((m->u_ier & 1) && uart_rx_timeout()) return fifo | 0x0C;
        if ((m->u_ier & 2) && m->thre_int) { m->thre_int = 0; return fifo | 0x02; }
        return fifo | 0x01;
    }
    case 3: return m->u_lcr;
    case 4: return m->u_mcr;
    case 5: return (uint8_t)((m->rx_n ? 0x01 : 0) | (m->tx_n == 0 ? 0x60 : (m->tx_n < 16 ? 0x00 : 0x00)));
    case 6: return 0xB0;                   /* DCD, DSR, CTS asserted, no deltas */
    default: return m->u_scr;
    }
}

static void uart_write(uint8_t r, uint8_t v)
{
    int dlab = m->u_lcr & 0x80;
    switch (r) {
    case 0:
        if (dlab) { m->u_dll = v; break; }
        if (m->tx_n == 0) m->tx_next = m->cpu.cycles + uart_bit_cycles();
        if (m->tx_n < 17) m->tx_n++;
        m->thre_int = 0;
        fputc(v, m->ser_out);
        if (m->ser_times) fprintf(m->ser_times, "%llu %02X\n", (unsigned long long)(m->dots * DOT_PS), v);
        {
            int was = ser_gate.open;
            gate_feed(&ser_gate, v); gate_feed(&kbd_gate, v); gate_feed(&mouse_gate, v);
            if (!was && ser_gate.open && m->ser_at < m->cpu.cycles + m->ser_think) m->ser_at = m->cpu.cycles + m->ser_think;
        }
        fputc(v, stdout);
        fflush(stdout);
        if (m->ser_stop && v) {         /* NULs are padding, not text: they never break a match */
            if ((char)v == m->ser_stop[m->ser_match]) {
                if (++m->ser_match == m->ser_stop_len) m->stop = 1;
            } else m->ser_match = ((char)v == m->ser_stop[0]) ? 1 : 0;
        }
        break;
    case 1:
        if (dlab) { m->u_dlm = v; break; }
        if ((v & 2) && !(m->u_ier & 2) && m->tx_n == 0) m->thre_int = 1;
        m->u_ier = v & 0x0F;
        break;
    case 2:
        m->u_fcr = v;
        if (v & 2) { m->rx_n = 0; m->rx_head = 0; }
        if (v & 4) { m->tx_n = 0; }
        break;
    case 3: m->u_lcr = v; break;
    case 4: m->u_mcr = v; break;
    case 7: m->u_scr = v; break;
    default: break;
    }
}

static void uart_step(void)
{
    if (m->tx_n && m->cpu.cycles >= m->tx_next) {
        m->tx_n--;
        m->tx_next += uart_bit_cycles();
        if (m->tx_n == 0) m->thre_int = 1;
    }
    if (m->ser_in && m->ser_in_pos < m->ser_in_n && ser_gate.open && m->cpu.cycles >= m->ser_at && m->cpu.cycles >= m->rx_next) {
        uint8_t c = m->ser_in[m->ser_in_pos];
        if (c == 0x01) {                /* a pause, not sent */
            m->ser_in_pos++;
            m->ser_at = m->cpu.cycles + 2097917;
            return;
        }
        if (m->rx_n < 16) {
            m->rx[(m->rx_head + m->rx_n) & 15] = c;
            m->ser_in_pos++;
            m->rx_n++;
            if (c == '\r' && ser_gate.n) ser_gate.open = 0;
        }
        m->rx_last = m->cpu.cycles;
        m->rx_next = m->cpu.cycles + (m->ser_type > uart_bit_cycles() ? m->ser_type : uart_bit_cycles());
    }
}

/* ------------------------------------------------------------------ PS/2 */
/* io/ps2/docs/ps2.md, port 0 the keyboard and port 1 the mouse.
 *
 * THE CARD is modelled as §6 builds it, not as a byte pipe: each port's '193
 * counts falling edges of the CLK LINE - whoever pulls it - with a period of
 * eleven, the '595 shifts the DATA line on each, and the eleventh latches the
 * frame's bits 1-8 into KDATA and sets KDR. KRST/MRST hold the counter at its
 * preload. So a driver that transmits without holding KRST gets the garbage
 * §7 step 1 warns about, and one that never releases it hears nothing.
 * IOSTAT's line bits read 1 for a line held LOW (§8.1).
 *
 * THE DEVICES are PS/2 devices at the line level: they clock their own frames
 * at 80 us a bit, back off when the host holds CLK low, see a request to send
 * (CLK low >= 100 us, released with DATA low), clock the host's eleven bits in,
 * ACK, and answer §11.2's commands. A keyboard's scan codes and a mouse's
 * packets come from PS2_KBD and PS2_MOUSE, lists of hex bytes, delivered from
 * PS2_AT seconds on - the mouse's only once reporting is enabled (F4).
 *
 * WHAT IT DOES NOT: parity errors in either direction (a device answers FE to
 * a bad parity, which is all a driver can see), typematic repeat, and the
 * electrical rise time §4.2 is about. */
#define PS2_HALF 84                     /* E cycles: 40 us, half a clock period */
typedef struct {
    int mouse;
    /* the card */
    int count;                          /* the '193: edges into this frame */
    uint16_t shift;                     /* the '595, fed LSB-first */
    int clk_prev;
    /* the device */
    int dev_clk_low, dev_dat_low;
    enum { D_IDLE, D_INHIBIT, D_RTS_WAIT, D_RX, D_TX } st;
    uint64_t t;                         /* the next event, or when the inhibit began */
    int bit, phase;                     /* bit index; 0 = clock low next, 1 = high next */
    uint16_t frame;
    uint8_t out[64]; int out_n;         /* bytes the device has to send */
    uint8_t last_sent;
    int enabled;                        /* keyboard scanning / mouse reporting */
    int f4_seen;                        /* a script plays only after the host's first F4 */
    int want_arg;                       /* the command whose argument comes next */
    const char *script; uint64_t script_at, script_next;
} ps2dev;
static ps2dev ps2[2];

static int ps2_clk_low(int p) { return ((m->ioctrl >> (p * 2)) & 1) || ps2[p].dev_clk_low; }
static int ps2_dat_low(int p) { return ((m->ioctrl >> (p * 2 + 1)) & 1) || ps2[p].dev_dat_low; }

static void ps2_send(ps2dev *d, uint8_t b) { if (d->out_n < 64) d->out[d->out_n++] = b; }

static void ps2_command(ps2dev *d, uint8_t c)
{
    if (d->want_arg) {                  /* ED, F3, E8: the argument byte */
        d->want_arg = 0;
        ps2_send(d, 0xFA);
        return;
    }
    switch (c) {
    case 0xFF:                          /* reset: ACK, then the self-test result */
        d->out_n = 0; d->enabled = !d->mouse;
        ps2_send(d, 0xFA); ps2_send(d, 0xAA);
        if (d->mouse) ps2_send(d, 0x00);
        break;
    case 0xFE: ps2_send(d, d->last_sent); break;
    case 0xF2: ps2_send(d, 0xFA); if (d->mouse) ps2_send(d, 0x00); else { ps2_send(d, 0xAB); ps2_send(d, 0x83); } break;
    case 0xF4: d->enabled = 1; d->f4_seen = 1; ps2_send(d, 0xFA); break;
    case 0xF5: d->enabled = 0; ps2_send(d, 0xFA); break;
    case 0xEE: if (!d->mouse) { ps2_send(d, 0xEE); break; } /* fall through */
    case 0xED: case 0xF3: case 0xE8:
        d->want_arg = 1; ps2_send(d, 0xFA); break;
    default: ps2_send(d, 0xFA); break;
    }
}

/* the card sees a falling edge of the CLK line */
static void ps2_card_edge(int p)
{
    ps2dev *d = &ps2[p];
    if ((m->ioctrl >> (4 + p)) & 1) { d->count = 0; return; }   /* KRST/MRST: held at preload */
    d->shift = (uint16_t)((d->shift >> 1) | (ps2_dat_low(p) ? 0 : 0x400));
    if (++d->count == 11) {
        d->count = 0;
        m->kdata[p] = (uint8_t)(d->shift >> 1);     /* bits 1-8 of the frame */
        m->kdr[p] = 1;
    }
}

static void ps2_step(int p)
{
    ps2dev *d = &ps2[p];
    uint64_t now = m->cpu.cycles;
    int host_clk = (m->ioctrl >> (p * 2)) & 1, host_dat = (m->ioctrl >> (p * 2 + 1)) & 1;

    /* scripted bytes, one per 10 ms, once the device would send them */
    if (d->script && *d->script && (d->mouse ? mouse_gate.open : kbd_gate.open)
        && now >= d->script_at && now >= d->script_next && d->enabled && d->f4_seen && d->out_n == 0) {
        unsigned v; int n;
        while (*d->script == ' ') d->script++;
        if (*d->script == 'w' && sscanf(d->script + 1, "%u%n", &v, &n) == 1) {   /* w<ms>: a pause */
            d->script += n + 1;
            d->script_next = now + (uint64_t)v * 2098;
            return;
        }
        if (sscanf(d->script, " %x%n", &v, &n) == 1) { ps2_send(d, (uint8_t)v); d->script += n; }
        else d->script = NULL;
        d->script_next = now + 20979;
    }

    switch (d->st) {
    case D_IDLE:
        if (host_clk) { d->st = D_INHIBIT; d->t = now; break; }
        if (d->out_n && now >= d->t) {  /* start a frame: start, 8 data, odd parity, stop */
            uint8_t b = d->out[0], par = 1;
            for (int i = 0; i < 8; i++) par ^= (b >> i) & 1;
            d->frame = (uint16_t)(((uint16_t)b << 1) | ((uint16_t)par << 9) | 0x400);
            d->st = D_TX; d->bit = 0; d->phase = 0; d->t = now;
        }
        break;
    case D_INHIBIT:
        if (!host_clk) {
            if (now - d->t >= 2 * PS2_HALF + PS2_HALF / 2 && host_dat) {   /* >= 100 us, and a start bit */
                d->st = D_RTS_WAIT; d->t = now + 20 * PS2_HALF;
            } else {
                d->st = D_IDLE; d->t = now + 2 * PS2_HALF;
            }
        }
        break;
    case D_RTS_WAIT:
        if (now >= d->t) { d->st = D_RX; d->bit = 0; d->phase = 0; d->frame = 0; d->t = now; }
        break;
    case D_RX:                          /* eleven clocks: 8 data, parity, stop, then the ACK */
        if (now < d->t) break;
        if (d->phase == 0) {
            d->dev_clk_low = 1;
            if (d->bit == 10) d->dev_dat_low = 1;                       /* ACK */
            d->phase = 1;
        } else {
            d->dev_clk_low = 0;
            if (d->bit < 10) d->frame |= (uint16_t)((ps2_dat_low(p) ? 0 : 1) << d->bit);
            if (d->bit == 10) {
                d->dev_dat_low = 0;
                uint8_t c = (uint8_t)(d->frame & 0xFF), par = 1;
                for (int i = 0; i < 8; i++) par ^= (c >> i) & 1;
                d->st = D_IDLE; d->t = now + 20 * PS2_HALF;
                if (((d->frame >> 8) & 1) != par) ps2_send(d, 0xFE);
                else ps2_command(d, c);
            }
            d->bit++;
            d->phase = 0;
        }
        d->t = now + PS2_HALF;
        break;
    case D_TX:
        if (now < d->t) break;
        if (d->phase == 0) {
            if (host_clk) {             /* the host inhibits: abandon the frame, keep the byte */
                d->dev_dat_low = 0; d->st = D_INHIBIT; d->t = now; break;
            }
            d->dev_dat_low = !((d->frame >> d->bit) & 1);
            d->dev_clk_low = 1;
            d->phase = 1;
        } else {
            d->dev_clk_low = 0;
            if (++d->bit == 11) {
                d->dev_dat_low = 0;
                d->last_sent = d->out[0];
                memmove(d->out, d->out + 1, (size_t)--d->out_n);
                d->st = D_IDLE; d->t = now + 20 * PS2_HALF;
            }
            d->phase = 0;
        }
        d->t = now + PS2_HALF;
        break;
    }

    if (getenv("PS2_DEBUG")) {
        static int last_st[2] = {-1, -1};
        if ((int)d->st != last_st[p]) {
            fprintf(stderr, "ps2[%d] %.6f s st %d ioctrl %02X bit %d frame %03X out_n %d\n", p,
                    (double)now / 2097917.0, (int)d->st, m->ioctrl, d->bit, d->frame, d->out_n);
            last_st[p] = (int)d->st;
        }
    }
    int clk = ps2_clk_low(p);
    if (clk && !d->clk_prev) ps2_card_edge(p);
    d->clk_prev = clk;
}

static uint8_t ps2_read(uint8_t r)
{
    switch (r) {
    case 0: m->kdr[0] = 0; return m->kdata[0];
    case 1: m->kdr[1] = 0; return m->kdata[1];
    case 2: return (uint8_t)(m->kdr[0] | (m->kdr[1] << 1) | (ps2_clk_low(0) << 2) | (ps2_dat_low(0) << 3)
                             | (ps2_clk_low(1) << 4) | (ps2_dat_low(1) << 5));
    default: return 0x00;               /* IOCTRL is write-only */
    }
}

/* ps2.md 3.1: one enable per port, IOCTRL b6 for the keyboard and b7 for the mouse */
static int ps2_irq(void) { return ((m->ioctrl & 0x40) && m->kdr[0]) || ((m->ioctrl & 0x80) && m->kdr[1]); }

/* ------------------------------------------------------------------ masked time */
/* MASKLOG=from: from that machine second on, every stretch with CC's I bit
 * set is timed, and at exit the longest are listed by where the stretch began
 * - the instruction after the ORCC, or the handler an interrupt entered - as a
 * NitrOS-9 module and offset. It is how software/nitros9/run-vid.sh measures
 * docs/nitros9-av-plan.md 3.4's "IRQ-masked time per primitive". */
static uint8_t peek(uint16_t a)          /* rd() without a device's side effects */
{
    if (a >= 0xFF00) return 0;
    uint8_t hi = m->maphi[entry(a)], lo = m->maplo[entry(a)];
    if (hi == 0x01) return m->rom[((uint32_t)lo << 13 | (a & 0x1FFF)) & 0xFFFFF];
    if (hi == 0x00 && (lo & 0xC0) == 0x40) return 0;
    return rampage(hi, lo)[a & 0x1FFF];
}

/* the module holding `a`: its name and a's offset in it, or "?" */
static void module_of(uint16_t a, char *name, size_t n, unsigned *off)
{
    snprintf(name, n, "?");
    *off = a;
    for (unsigned back = 0; back < 0x8000 && back <= a; back++) {
        uint16_t h = (uint16_t)(a - back);
        if (peek(h) != 0x87 || peek((uint16_t)(h + 1)) != 0xCD) continue;
        uint8_t par = 0;
        for (int i = 0; i < 9; i++) par ^= peek((uint16_t)(h + i));
        if (par != 0xFF) continue;
        unsigned size = ((unsigned)peek((uint16_t)(h + 2)) << 8) | peek((uint16_t)(h + 3));
        if (back >= size) continue;
        uint16_t np = (uint16_t)(h + (((unsigned)peek((uint16_t)(h + 4)) << 8) | peek((uint16_t)(h + 5))));
        size_t k = 0;
        for (; k + 1 < n && k < 15; k++) {
            uint8_t c = peek((uint16_t)(np + k));
            name[k] = (char)(c & 0x7F);
            if (c & 0x80) { k++; break; }
        }
        name[k] = 0;
        *off = back;
        return;
    }
}

typedef struct { uint16_t pc, endpc; uint8_t task; uint64_t max; long n; char mod[16]; unsigned off; char endmod[16]; unsigned endoff; } maskrec;
static maskrec masks[256];
static int nmasks;

static void mask_record(uint16_t pc, uint64_t len, uint16_t endpc)
{
    int i;
    for (i = 0; i < nmasks; i++)
        if (masks[i].pc == pc && masks[i].task == m->task) break;
    if (i == nmasks) {
        if (nmasks == 256) return;
        nmasks++;
        masks[i].pc = pc; masks[i].task = m->task; masks[i].max = 0; masks[i].n = 0;
        module_of(pc, masks[i].mod, sizeof masks[i].mod, &masks[i].off);
    }
    masks[i].n++;
    if (len > masks[i].max) {
        masks[i].max = len;
        masks[i].endpc = endpc;
        module_of(endpc, masks[i].endmod, sizeof masks[i].endmod, &masks[i].endoff);
    }
}

static int mask_cmp(const void *a, const void *b)
{
    const maskrec *x = a, *y = b;
    return x->max < y->max ? 1 : x->max > y->max ? -1 : 0;
}

/* CALLTIME=Module+$off: time every call of the routine at that offset in the
 * named module (task 0's map), from arrival to the RTS that returns past it,
 * and report the longest, the mean and the count at exit. It is how
 * run-vid.sh measures the VBL service itself, not the kernel's IRQ path around
 * it. The module is found by name once it is in memory. It also reports each
 * call's time outside the interrupts taken during it (entered at krn's
 * $FEF4/$FEF7 stubs, left when the interrupted PC and S come back). */
static struct { char name[16]; unsigned off; uint16_t addr; int resolved; int in; uint64_t t0; uint16_t s0, ret;
                uint64_t max, total; long n;
                int intr; uint16_t int_pc, int_s; uint64_t int_t0, excl, netmax, nettotal; } ct;

static void calltime_resolve(void)
{
    uint8_t t = m->task; m->task = 0;
    for (unsigned h = 0; h + 16 < 0xFF00; h++) {
        if (peek((uint16_t)h) != 0x87 || peek((uint16_t)(h + 1)) != 0xCD) continue;
        if (m->maphi[entry((uint16_t)h)] == 0x01) { h |= 0x1FFF; continue; }   /* a ROM page the ROM disk has mapped: not a loaded module */
        uint8_t par = 0;
        for (int i = 0; i < 9; i++) par ^= peek((uint16_t)(h + i));
        if (par != 0xFF) continue;
        uint16_t np = (uint16_t)(h + (((unsigned)peek((uint16_t)(h + 4)) << 8) | peek((uint16_t)(h + 5))));
        size_t k = 0; int match = 1;
        for (;; k++) {
            uint8_t c = peek((uint16_t)(np + k));
            if (k >= sizeof ct.name || (char)(c & 0x7F) != ct.name[k]) { match = 0; break; }
            if (c & 0x80) { match = ct.name[k + 1] == 0; break; }
        }
        if (match) { ct.addr = (uint16_t)(h + ct.off); ct.resolved = 1; break; }
    }
    m->task = t;
}

static uint8_t rd(void *ctx, uint16_t a)
{
    (void)ctx;
    if (a >= 0xFFC0) return m->rom[a & 0x1FFF];
    if (a >= 0xFF00) {
        if (a >= 0xFF60 && a <= 0xFF7F) return video_read((uint8_t)(a - 0xFF60));
        if (a >= 0xFF38 && a <= 0xFF3F) return uart_read((uint8_t)(a - 0xFF38));
        if (a >= 0xFF30 && a <= 0xFF33) return ps2_read((uint8_t)(a - 0xFF30));
        if (a >= 0xFF40 && a <= 0xFF4F) return audio_read((uint8_t)(a & 15));
        if (a >= 0xFF90 && a <= 0xFF9F) return m->maphi[a & 15];
        if (a >= 0xFFA0 && a <= 0xFFAF) return m->maplo[a & 15];
        return 0x00;                      /* ASTAT never busy */
    }
    uint8_t hi = m->maphi[entry(a)], lo = m->maplo[entry(a)];
    if (hi == 0x01) return m->rom[((uint32_t)lo << 13 | (a & 0x1FFF)) & 0xFFFFF];
    if (hi == 0x00 && (lo & 0xC0) == 0x40) return vram_read();  /* the VRAM window: VDATA at every address */
    return rampage(hi, lo)[a & 0x1FFF];
}

static void wr(void *ctx, uint16_t a, uint8_t v)
{
    (void)ctx;
    /* ⭐ WATCH=addr[,addr...]: every write to one of those logical addresses,
     * with the PC and the task that made it.  For finding who smashes a system
     * global - the trace shows instructions, not their effects. */
    {
        static int init; static uint16_t w[8]; static int nw;
        if (!init) {
            init = 1;
            const char *e = getenv("WATCH");
            while (e && *e && nw < 8) { w[nw++] = (uint16_t)strtol(e, (char **)&e, 16); if (*e == ',') e++; }
        }
        for (int i = 0; i < nw; i++)
            if (a == w[i])
                fprintf(stderr, "WATCH %.4f s: $%04X := $%02X  PC $%04X task %d  S $%04X"
                        "  bytes %02X %02X %02X %02X\n",
                        (double)m->dots * DOT_PS / 1e12, a, v, m->cpu.pc, m->task, m->cpu.s,
                        peek((uint16_t)(m->cpu.pc - 2)), peek((uint16_t)(m->cpu.pc - 1)),
                        peek(m->cpu.pc), peek((uint16_t)(m->cpu.pc + 1)));
    }
    if (a >= 0xFF00) {
        if (a >= 0xFF60 && a <= 0xFF7F) {
            /* graphics.md 10.3.1 and 10.3.3: while LRUN the engine owns WPTR and a
             * CPU register write can take a descriptor byte from it */
            if (m->lrun && ++m->list_violations <= 8)
                fprintf(stderr, "FAIL  %.3f s: the CPU wrote $%04X := $%02X while a display list ran (PC $%04X)\n",
                        (double)m->dots * DOT_PS / 1e12, a, v, m->cpu.pc);
            /* graphics.md 7.4: a span's colour and WADV 01's column reload are read
             * from the register file, and a CPU register access takes it away */
            /* ⚠ VDATA IS AT A DIFFERENT OFFSET ON EACH CARD - $15 on video/,
             * $0C on video3 (plan §10) - and it is the one register exempt
             * from the rule, because a VRAM byte is not a register-file read.
             * Hard-coding $FF75 made every video3 font stream a violation. */
            if (a != (m->v3 ? 0xFF6CU : 0xFF75U) && m->busy_until > m->dots
                && ++m->span_violations <= 8)
                fprintf(stderr, "FAIL  %.3f s: the CPU wrote $%04X := $%02X under a span (PC $%04X)\n",
                        (double)m->dots * DOT_PS / 1e12, a, v, m->cpu.pc);
            video_write((uint8_t)(a - 0xFF60), v);
        }
        else if (a >= 0xFF90 && a <= 0xFF9F) m->maphi[a & 15] = v;
        else if (a >= 0xFFA0 && a <= 0xFFAF) m->maplo[a & 15] = v;
        else if (a >= 0xFF40 && a <= 0xFF4F) audio_write((uint8_t)(a & 15), v);
        else if (a >= 0xFF38 && a <= 0xFF3F) uart_write((uint8_t)(a - 0xFF38), v);
        else if (a == 0xFF33) m->ioctrl = v;
        else if (a >= 0xFFB0 && a <= 0xFFBF) m->task = v & 1;
        else if (a == 0xFF2E && m->marks)     /* a timing mark: demo.asm's MARK */
            fprintf(m->marks, "%llu M%u\n", (unsigned long long)(m->dots * DOT_PS), v);
        else if (a == 0xFF2F) {
            m->progress = v;
            fprintf(stderr, "      %8.3f s  progress $%02X\n", (double)m->dots * DOT_PS / 1e12, v);
        }
        return;
    }
    uint8_t hi = m->maphi[entry(a)], lo = m->maplo[entry(a)];
    if (hi == 0x01) return;
    if (hi == 0x00 && (lo & 0xC0) == 0x40) { vram_write(v); return; }   /* the VRAM window */
    rampage(hi, lo)[a & 0x1FFF] = v;
}

/* ------------------------------------------------------------------ video out */
/* The line-count family is vctrl's M0: VMODE0 taken where a frame ends, so a
 * CTRL write mid-frame changes the family at the next frame (graphics.md 6.2) */
static int vlines(void) { return m->m0 ? 525 : 449; }
static int active_lines(void) { return m->m0 ? 480 : 400; }
static int in_vblank(void) { return m->line >= active_lines(); }

static void v3_render_line(int y);

static void render_line(int y)
{
    if (y == 0) {
        m->vs_frame = (uint16_t)((m->vs_hi << 8) | m->vs_lo);
        m->ck0 = ram16(m->mk_ck);
        m->ph0 = ram16(m->mk_ph);
        m->frame_t = m->dots * DOT_PS;
        if (m->marks) fprintf(m->marks, "%llu A\n", (unsigned long long)(m->dots * DOT_PS));
    }
    if (y == 1) m->lrun1 = (uint16_t)m->lrun;
    if (m->v3) { v3_render_line(y); return; }
    uint16_t *row = m->cur + (size_t)y * 640;
    uint32_t hs = ((uint32_t)m->hs_hi << 8) | m->hs_lo;
    int vmode = m->ctrl & 3;
    uint32_t py = (vmode == 0 || vmode == 1) ? (uint32_t)(y / 2) : (uint32_t)y;
    uint32_t ry = (m->vs_frame + py) & 511;
    if (m->ctrl & 0x20) {
        uint32_t tb = (uint32_t)m->tilebase << 14, mb = (uint32_t)m->mapbase << 12;
        for (int x = 0; x < 640; x++) {
            uint32_t cx = (hs + x) & 1023;
            uint8_t code = m->vram[(mb + ((ry >> 3) & 31) * 128 + ((cx >> 3) & 127)) & 0x7FFFF];
            row[x] = m->pal[m->vram[(tb + ((uint32_t)code << 6) + ((ry & 7) << 3) + (cx & 7)) & 0x7FFFF]];
        }
    } else {
        const uint8_t *src = m->vram + (ry << 10);
        for (int x = 0; x < 640; x++) row[x] = m->pal[src[(hs + x) & 1023]];
    }
}

/* plan §3: row[x] = LUT[ (ATTR << 8) | pixel ]. The three modes differ only in
 * where the two halves come from. */
static void v3_render_line(int y)
{
    uint16_t *row = m->cur + (size_t)y * 640;
    int vmode = m->ctrl & 3;
    uint32_t py = (vmode == 0 || vmode == 1) ? (uint32_t)(y / 2) : (uint32_t)y;
    uint32_t hs = ((uint32_t)m->hs_hi << 8) | m->hs_lo;
    uint32_t tb = (uint32_t)m->tilebase << 14, mb = (uint32_t)m->mapbase << 16;
    int mode = V3_MODE(m);

    if (mode == 1) {
        /* plan §2.5: two bytes a cell on a 1024-byte stride, six-bit cell row,
         * ⛔ NO ring and NO horizontal scroll - a line is 80 codes, not 81. */
        uint32_t crow = (py >> 3) & 63, grow = py & 7;
        for (int x = 0; x < 640; x++) {
            uint32_t ma = (mb + (crow << 10) + (((uint32_t)x >> 3) << 1)) & 0x7FFFF;
            uint8_t code = m->vram[ma], attr = m->vram[(ma + 1) & 0x7FFFF];
            uint8_t px = m->vram[(tb + ((uint32_t)code << 6) + (grow << 3)
                                     + ((uint32_t)x & 7)) & 0x7FFFF];
            row[x] = m->pal3[((uint16_t)attr << 8) | px];
        }
        return;
    }
    uint32_t ry = (m->vs_frame + py) & 511;
    if (mode == 2) {                    /* tile: one map byte, ATTR is zero */
        for (int x = 0; x < 640; x++) {
            uint32_t cx = (hs + x) & 1023;
            uint8_t code = m->vram[(mb + (((ry >> 3) & 63) << 10) + ((cx >> 3) & 127)) & 0x7FFFF];
            row[x] = m->pal3[m->vram[(tb + ((uint32_t)code << 6) + ((ry & 7) << 3)
                                        + (cx & 7)) & 0x7FFFF]];
        }
        return;
    }
    /* bitmap: ⭐ ATTR carries the sprite, and ONLY here (plan §7) */
    const uint8_t *src = m->vram + (ry << 10);
    uint32_t sx = ((uint32_t)(m->sprh & 3) << 8) | m->sprx_lo;
    uint32_t sy = ((uint32_t)(m->sprh & 4) << 6) | m->spry_lo;
    int on = (m->sprh & 0x80) != 0;
    for (int x = 0; x < 640; x++) {
        uint16_t attr = 0;
        if (on && py >= sy && py < sy + 16 && (uint32_t)x >= sx && (uint32_t)x < sx + 16) {
            /* a row is four bytes: the low plane's two, then the high plane's */
            uint32_t sr = py - sy, sc = (uint32_t)x - sx;
            const uint8_t *sh = m->sprshape + sr * 4 + (sc >> 3);
            unsigned b = 7 - (sc & 7);
            attr = (uint16_t)(((sh[2] >> b) & 1) * 2 + ((sh[0] >> b) & 1));
        }
        row[x] = m->pal3[(attr << 8) | src[(hs + x) & 1023]];
    }
}

static void emit_frame(void)
{
    int w = 640, h = active_lines();
    int same = m->have_prev && m->prv_w == w && m->prv_h == h;
    int nrows = (h + 7) / 8;
    uint8_t bitmap[64] = {0};
    int changed = 0;
    if (same) {
        for (int y = 0; y < h; y++)
            if (memcmp(m->cur + (size_t)y * 640, m->prv + (size_t)y * 640, 640 * 2)) {
                bitmap[y >> 3] |= (uint8_t)(1 << (y & 7));
                changed++;
            }
    }
    uint8_t rep = !same ? 0 : changed == 0 ? 1 : 2;
    uint16_t camk = ram16(m->mk_camk), herok = ram16(m->mk_herok), missed = ram16(m->mk_missed);
    uint16_t ck1 = ram16(m->mk_ck), ph1 = ram16(m->mk_ph);
    uint64_t t = m->frame_t;
    fputc('F', m->frames);
    fwrite(&m->frame_n, 4, 1, m->frames);
    fwrite(&t, 8, 1, m->frames);
    uint16_t hdr[] = {(uint16_t)w, (uint16_t)h, camk, herok, missed};
    fwrite(hdr, 2, 5, m->frames);
    uint8_t b3[] = {m->progress, (uint8_t)(m->ctrl & 3), rep};
    fwrite(b3, 1, 3, m->frames);
    uint16_t ck[] = {m->ck0, ck1, m->ph0, ph1};
    fwrite(ck, 2, 4, m->frames);
    fputc(m->lrun1, m->frames);
    if (rep == 0) {
        fwrite(m->cur, 2, (size_t)w * h, m->frames);
    } else if (rep == 2) {
        fwrite(bitmap, 1, (size_t)nrows, m->frames);
        for (int y = 0; y < h; y++)
            if (bitmap[y >> 3] & (1 << (y & 7))) fwrite(m->cur + (size_t)y * 640, 2, 640, m->frames);
    }
    memcpy(m->prv, m->cur, (size_t)w * h * 2);
    m->prv_w = w; m->prv_h = h; m->have_prev = 1;
    m->frame_n++;
}

/* advance the raster to the current dot */
static void raster(void)
{
    while (m->dots >= m->line_start + DOTS_LINE) {
        m->line_start += DOTS_LINE;
        m->line++;
        if (m->ppend) { m->pal[m->pidx++] = m->ppval; m->ppend = 0; }   /* the posted commit, in this line's HLOAD */
        int act = active_lines();
        if (m->line == act) {                 /* VBLANK rises */
            if (m->marks) fprintf(m->marks, "%llu V\n", (unsigned long long)(m->line_start * DOT_PS));
            /* ... and /IRQ follows at VSYNC's leading edge: after the front porch,
             * which is 12 lines in the 449-line family and 10 in the 525-line one
             * (hardware/gal/sync.timing.ts). demo_tb measured the 12. */
            m->irq_line_due = act + (m->m0 ? 10 : 12);
            if (m->frame_active) emit_frame();
            m->frame_active = 0;
        }
        if (m->line == m->irq_line_due) {
            if (m->ctrl & 0x40) m->irq_pending = 1;
            m->irq_line_due = -1;
        }
        int armed = 0;
        if (m->line >= vlines()) { m->line = 0; m->m0 = m->ctrl & 1; armed = m->lgo; }
        if (m->lrun && m->lwait) { m->lwait = 0; list_run(); }
        /* after the WAIT release: an armed list starts inside line 0, as a GO
         * written there would, and its first WAIT is line 1's (10.3.2) */
        if (armed) { m->lgo = 0; m->lrun = 1; m->lwait = 0; list_run(); }
        if (m->line < act) {
            if (m->line == 0) m->frame_active = (m->ctrl & 0x80) != 0;
            if (m->frame_active) render_line(m->line);
        }
    }
}

int main(int argc, char **argv)
{
    if (argc < 4) { fprintf(stderr, "usage: emu ROM.bin OUTDIR SECONDS\n"); return 2; }
    static M mm;
    m = &mm;
    FILE *f = fopen(argv[1], "rb");
    if (!f || fread(m->rom, 1, sizeof m->rom, f) != sizeof m->rom) { fprintf(stderr, "FAIL  cannot read %s\n", argv[1]); return 1; }
    fclose(f);
    char path[1024];
    snprintf(path, sizeof path, "%s/frames.bin", argv[2]);
    m->frames = fopen(path, "wb");
    snprintf(path, sizeof path, "%s/card.trace", argv[2]);
    m->trace = fopen(path, "w");
    snprintf(path, sizeof path, "%s/card.times", argv[2]);
    m->times = fopen(path, "w");
    snprintf(path, sizeof path, "%s/serial.out", argv[2]);
    m->ser_out = fopen(path, "wb");
    if (!m->frames || !m->trace || !m->ser_out) { fprintf(stderr, "FAIL  cannot write in %s\n", argv[2]); return 1; }
    /* the frame words: demo.asm's and gui.asm's by default; MARKS=addr (hex, task 0's
     * logical map) reads them as five words there - checkpoint, raster phase, camera
     * record, hero record, missed flips - and writes OUTDIR/marks.txt: VBLANK's
     * rise (V), each frame's first active line (A) and writes to $FF2E (M<n>), in ps */
    m->mk_ck = 0xC600; m->mk_ph = 0xC602; m->mk_camk = 0xC208; m->mk_herok = 0xC20A; m->mk_missed = 0xC225;
    if (getenv("MARKS")) {
        uint16_t b = (uint16_t)strtoul(getenv("MARKS"), NULL, 16);
        m->mk_ck = b; m->mk_ph = b + 2; m->mk_camk = b + 4; m->mk_herok = b + 6; m->mk_missed = b + 8;
        snprintf(path, sizeof path, "%s/marks.txt", argv[2]);
        m->marks = fopen(path, "w");
    }
    if (getenv("SERIAL_IN")) {
        FILE *si = fopen(getenv("SERIAL_IN"), "rb");
        if (!si) { fprintf(stderr, "FAIL  cannot read SERIAL_IN %s\n", getenv("SERIAL_IN")); return 1; }
        static uint8_t buf[1 << 16];
        m->ser_in_n = (long)fread(buf, 1, sizeof buf, si);
        fclose(si);
        m->ser_in = buf;
        m->ser_at = (uint64_t)(atof(getenv("SERIAL_AT") ? getenv("SERIAL_AT") : "0") * 2097917.0);
    }
    /* the PS/2 devices power up: a keyboard sends its self-test result and
     * scans; a mouse sends AA 00 and waits for F4 (ps2.md 2.3, 11.2) */
    ps2[1].mouse = 1;
    for (int p = 0; p < 2; p++) {
        ps2[p].enabled = !ps2[p].mouse;
        ps2_send(&ps2[p], 0xAA);
        if (ps2[p].mouse) ps2_send(&ps2[p], 0x00);
        ps2[p].t = 104895;              /* 50 ms after reset */
        ps2[p].script = getenv(p ? "PS2_MOUSE" : "PS2_KBD");
        ps2[p].script_at = (uint64_t)(atof(getenv("PS2_AT") ? getenv("PS2_AT") : "0") * 2097917.0);
    }
    gate_init(&ser_gate, "SERIAL_GATE");
    gate_init(&kbd_gate, "PS2_KBD_GATE");
    gate_init(&mouse_gate, "PS2_MOUSE_GATE");
    m->ser_type = (uint64_t)(atof(getenv("SERIAL_TYPE") ? getenv("SERIAL_TYPE") : "0") * 2097.917);
    m->ser_think = (uint64_t)(atof(getenv("SERIAL_THINK") ? getenv("SERIAL_THINK") : "0") * 2097.917);
    if (getenv("SERIAL_TIMES") && !(m->ser_times = fopen(getenv("SERIAL_TIMES"), "w"))) {
        fprintf(stderr, "FAIL  cannot write SERIAL_TIMES %s\n", getenv("SERIAL_TIMES")); return 1;
    }
    if (getenv("SERIAL_STOP") && *getenv("SERIAL_STOP")) {
        m->ser_stop = getenv("SERIAL_STOP");
        m->ser_stop_len = strlen(m->ser_stop);
    }
    m->v3 = getenv("VIDEO3") && atoi(getenv("VIDEO3"));
    if (m->v3) fprintf(stderr, "emu: ⭐ VIDEO3 - video3/docs/plan.md's card, not video/'s\n");
    card_reset(&m->card, m->sram, CARD_SRAM_BYTES);
    m->cur = calloc(640 * 512, 2);
    m->prv = calloc(640 * 512, 2);
    double secs = atof(argv[3]);

    /* boot.asm's handoff (software/boot/README.md): ROM pages 1-2 at blocks 4-5,
     * ROM page 0 at block 7, the SIMM at block 6 */
    for (int i = 0; i < 16; i++) { m->maphi[i] = 0x02; m->maplo[i] = (uint8_t)i; }
    m->maphi[4] = 1; m->maplo[4] = 1;
    m->maphi[5] = 1; m->maplo[5] = 2;
    m->maphi[7] = 1; m->maplo[7] = 0;
    /* ... and the memory descriptor its SIMM walk leaves at logical $0000 of
     * the lowest populated socket (software/boot/README.md): the socket
     * bitmap, then the total in 8 KB blocks. EMU_SIMMS sockets, from 0; 4 by
     * default. The demo never reads it. */
    {
        int n = getenv("EMU_SIMMS") ? atoi(getenv("EMU_SIMMS")) : 4;
        uint8_t *p0 = rampage(0x02, 0x00);
        p0[0] = (uint8_t)((1 << n) - 1);
        p0[1] = (uint8_t)((n * 512) >> 8);
        p0[2] = (uint8_t)((n * 512) & 0xFF);
    }

    m->irq_line_due = -1;
    m->cpu.ctx = m;
    m->cpu.read = rd;
    m->cpu.write = wr;
    cpu6809_reset(&m->cpu);
    m->cpu.pc = 0x8004;

    /* TRACE=n prints the PC and registers of the first n instructions */
    long trace_n = getenv("TRACE") ? atol(getenv("TRACE")) : 0;
    uint64_t end_dots = (uint64_t)(secs * 1e12 / DOT_PS);
    uint64_t next_report = 0;
    while (m->dots < end_dots) {
        m->cpu.irq = (m->irq_pending && (m->ctrl & 0x40)) || uart_irq() || ps2_irq();
        audio_catchup();
        m->firq = card_firq(&m->card);
        m->cpu.firq = m->firq;
        {   /* the last 256 PCs, for RINGDUMP; WILD stops at 16 NEG <$00s in a row, a CPU running through empty RAM */
            static uint16_t ring[256]; static unsigned ri, zeros;
            ring[ri++ & 255] = (uint16_t)m->cpu.pc;
            if (getenv("RINGDUMP")) { atexit_ring = ring; atexit_ri = &ri; }
            if (getenv("WILD")) {
                zeros = (rd(m, m->cpu.pc) == 0 && rd(m, (uint16_t)(m->cpu.pc + 1)) == 0) ? zeros + 1 : 0;
                if (zeros == 16) { fprintf(stderr, "WILD at %.3f s, task %d\n", (double)m->dots * DOT_PS / 1e12, m->task); atexit_ring = ring; atexit_ri = &ri; break; }
            }
        }
        {   /* LISTLOG=from,to,addr[,addr...]: between two machine seconds, log each
             * frame's list GO, list END and arrivals at the given PCs, with the
             * raster line - for finding where a frame's work overruns the blank */
            static int init, nadr; static unsigned adr[16]; static double lf, lt; static int lr_prev;
            if (!init) {
                init = 1;
                const char *e = getenv("LISTLOG");
                if (e) {
                    char buf[256]; strncpy(buf, e, 255); buf[255] = 0;
                    char *tok = strtok(buf, ",");
                    lf = atof(tok ? tok : "0"); tok = strtok(NULL, ","); lt = atof(tok ? tok : "0");
                    while ((tok = strtok(NULL, ",")) && nadr < 16) adr[nadr++] = (unsigned)strtoul(tok, NULL, 16);
                } else lt = -1;
            }
            double now_s = (double)m->dots * DOT_PS / 1e12;
            if (now_s >= lf && now_s <= lt) {
                for (int i = 0; i < nadr; i++)
                    if (m->cpu.pc == adr[i]) fprintf(stderr, "LL %.4f line %3d pc %04X\n", now_s, m->line, m->cpu.pc);
                if (m->lrun != lr_prev) fprintf(stderr, "LL %.4f line %3d LRUN %d\n", now_s, m->line, m->lrun);
                lr_prev = m->lrun;
            }
        }
        if (trace_n > 0 && (!getenv("TRACE_AT") || m->dots * DOT_PS >= (uint64_t)(atof(getenv("TRACE_AT")) * 1e12))) {
            trace_n--;
            char nm[16]; unsigned off;
            module_of(m->cpu.pc, nm, sizeof nm, &off);
            fprintf(stderr, "PC %04X A %02X B %02X X %04X Y %04X U %04X S %04X CC %02X DP %02X T %d %s+$%04X\n", m->cpu.pc, m->cpu.a,
                    m->cpu.b, m->cpu.x, m->cpu.y, m->cpu.u, m->cpu.s, m->cpu.cc, m->cpu.dp, m->task, nm, off);
        }
        {   /* CALLTIME */
            static int init;
            if (!init) {
                init = 1;
                const char *e = getenv("CALLTIME");
                if (e && sscanf(e, "%15[^+]+$%x", ct.name, &ct.off) == 2) ct.name[15] = 0; else ct.name[0] = 0;
            }
            if (ct.name[0]) {
                static long tick;
                if (!ct.resolved && (tick++ & 0xFFFF) == 0) calltime_resolve();
                if (ct.resolved && m->task == 0) {
                    if (!ct.in && m->cpu.pc == ct.addr) {
                        ct.in = 1; ct.t0 = m->cpu.cycles; ct.s0 = m->cpu.s; ct.intr = 0; ct.excl = 0;
                        ct.ret = (uint16_t)((peek(m->cpu.s) << 8) | peek((uint16_t)(m->cpu.s + 1)));
                    } else if (ct.in && m->cpu.pc == ct.ret && m->cpu.s == (uint16_t)(ct.s0 + 2)) {
                        uint64_t d = m->cpu.cycles - ct.t0;
                        ct.in = 0; ct.n++; ct.total += d;
                        if (d > ct.max) ct.max = d;
                        uint64_t net = d - ct.excl;
                        ct.nettotal += net;
                        if (net > ct.netmax) ct.netmax = net;
                    }
                }
            }
        }
        uint8_t cc_was = m->cpu.cc;
        uint16_t pc_was = m->cpu.pc, s_was = m->cpu.s;
        uint64_t cyc_was = m->cpu.cycles;
        int e = cpu6809_step(&m->cpu);
        if (ct.in) {                        /* CALLTIME: an interrupt inside the timed call */
            if (!ct.intr && (m->cpu.pc == 0xFEF7 || m->cpu.pc == 0xFEF4) && (pc_was >> 8) != 0xFE) {
                ct.intr = 1; ct.int_pc = pc_was; ct.int_s = s_was; ct.int_t0 = cyc_was;
            } else if (ct.intr && m->cpu.pc == ct.int_pc && m->cpu.s == ct.int_s) {
                ct.intr = 0; ct.excl += m->cpu.cycles - ct.int_t0;
            }
        }
        {
            static int init; static double from = -1; static uint64_t since; static uint16_t since_pc;
            if (!init) { init = 1; if (getenv("MASKLOG")) from = atof(getenv("MASKLOG")); }
            if (from >= 0 && (double)m->dots * DOT_PS / 1e12 >= from) {
                if (!(cc_was & 0x10) && (m->cpu.cc & 0x10)) { since = m->cpu.cycles - (uint64_t)e; since_pc = m->cpu.pc; }
                else if ((cc_was & 0x10) && !(m->cpu.cc & 0x10) && since) mask_record(since_pc, m->cpu.cycles - since, m->cpu.pc);
                /* MASKTRACE=from,to: each change of I between two machine seconds, where it happened */
                if (getenv("MASKTRACE") && ((cc_was ^ m->cpu.cc) & 0x10)) {
                    double f = 0, t = 0; sscanf(getenv("MASKTRACE"), "%lf,%lf", &f, &t);
                    double now_s = (double)m->dots * DOT_PS / 1e12;
                    if (now_s >= f && now_s <= t) {
                        char nm[16]; unsigned off;
                        module_of(m->cpu.pc, nm, sizeof nm, &off);
                        fprintf(stderr, "I=%d %.6f s  PC $%04X %s+$%04X task %d S $%04X\n", (m->cpu.cc & 0x10) ? 1 : 0, now_s, m->cpu.pc, nm, off, m->task, m->cpu.s);
                    }
                }
                /* MASKSAMPLE=us: inside a masked stretch longer than that, where the time goes */
                if ((m->cpu.cc & 0x10) && since && getenv("MASKSAMPLE") && m->cpu.cycles - since > (uint64_t)(atof(getenv("MASKSAMPLE")) * 2.097917)) {
                    static uint64_t last_sample; static int nsamples;
                    if (m->cpu.cycles - last_sample > 2000 && nsamples < 64) {
                        char nm[16]; unsigned off;
                        module_of(m->cpu.pc, nm, sizeof nm, &off);
                        fprintf(stderr, "MASKED %.4f s  %.1f ms in  %s+$%04X\n", (double)m->dots * DOT_PS / 1e12,
                                (double)(m->cpu.cycles - since) / 2097.917, nm, off);
                        last_sample = m->cpu.cycles; nsamples++;
                    }
                }
            }
        }
        m->dots = m->cpu.cycles * DOTS_PER_E;
        raster();
        uart_step();
        ps2_step(0);
        ps2_step(1);
        if (m->stop) { fprintf(stderr, "      %8.3f s  SERIAL_STOP seen\n", (double)m->dots * DOT_PS / 1e12); break; }
        (void)e;
        if (m->dots >= next_report) {
            fprintf(stderr, "      %8.3f s  prog $%02X  frames %d  ck %u\n", (double)m->dots * DOT_PS / 1e12,
                    m->progress, m->frame_n, ram16(0xC600));
            next_report += (uint64_t)(5e12 / DOT_PS);
        }
        /* $E0-$EF are errors (boot.asm's $E1-$E3); $FF is boot.asm's "done", which
         * a reboot back through the boot ROM reaches on its way to page 1 */
        if ((m->progress & 0xF0) == 0xE0) { fprintf(stderr, "FAIL  the ROM reported $%02X\n", m->progress); break; }
    }
    fclose(m->frames);
    fclose(m->trace);
    fclose(m->times);
    fclose(m->ser_out);
    if (m->ser_times) fclose(m->ser_times);
    snprintf(path, sizeof path, "%s/sync.txt", argv[2]);
    f = fopen(path, "w");
    fprintf(f, "cc0_ps 0\nend_ps %llu\n", (unsigned long long)(m->dots * DOT_PS));
    fclose(f);
    if (getenv("VRAMDUMP")) {   /* VRAMDUMP=file: all 512 KB of VRAM, at exit */
        FILE *vf = fopen(getenv("VRAMDUMP"), "wb");
        if (vf) { fwrite(m->vram, 1, sizeof m->vram, vf); fclose(vf); }
    }
    if (getenv("DUMP")) {   /* DUMP=addr,len: logical memory through task 0's map, at exit */
        unsigned da = 0, dl = 0;
        sscanf(getenv("DUMP"), "%x,%x", &da, &dl);
        uint8_t t = m->task; m->task = 0;
        for (unsigned i = 0; i < dl; i++) {
            if (i % 32 == 0) fprintf(stderr, "\n%04X:", (da + i) & 0xFFFF);
            fprintf(stderr, " %02X", rd(m, (uint16_t)(da + i)));
        }
        fprintf(stderr, "\n");
        m->task = t;
    }
    if (ct.name[0])
        fprintf(stderr, "CALLTIME %s+$%04X: %ld calls, longest %.1f us, mean %.1f us; outside interrupts longest %.1f us, mean %.1f us%s\n",
                ct.name, ct.off, ct.n,
                (double)ct.max * 1e6 / 2097917.0, ct.n ? (double)ct.total / ct.n * 1e6 / 2097917.0 : 0.0,
                (double)ct.netmax * 1e6 / 2097917.0, ct.n ? (double)ct.nettotal / ct.n * 1e6 / 2097917.0 : 0.0,
                ct.resolved ? "" : " (the module never appeared)");
    if (nmasks) {
        qsort(masks, (size_t)nmasks, sizeof masks[0], mask_cmp);
        for (int i = 0; i < nmasks && i < 24; i++)
            fprintf(stderr, "MASK %8.1f us  %s+$%04X to %s+$%04X  (PC $%04X task %d, %ld stretches)\n",
                    (double)masks[i].max * 1e6 / 2097917.0, masks[i].mod, masks[i].off, masks[i].endmod, masks[i].endoff,
                    masks[i].pc, masks[i].task, masks[i].n);
    }
    if (atexit_ring) {
        fprintf(stderr, "last PCs:");
        for (unsigned i = 0; i < 256; i++) fprintf(stderr, "%s%04X", i % 16 ? " " : "\n  ", atexit_ring[(*atexit_ri + i) & 255]);
        fprintf(stderr, "\n");
    }
    /* ⭐ VRAMOUT=file writes the whole 512 K of VRAM at exit.  Debugging a
     * driver against a card that has no memory-mapped VRAM is otherwise
     * guesswork: the map, the glyph bank and the bitmap are all just
     * "somewhere the span writer put them". */
    {
        const char *vo = getenv("VRAMOUT");
        if (vo) {
            FILE *f = fopen(vo, "wb");
            if (f) { fwrite(m->vram, 1, sizeof m->vram, f); fclose(f);
                     fprintf(stderr, "emu: VRAM -> %s (%zu bytes)\n", vo, sizeof m->vram); }
        }
        const char *ro = getenv("REGOUT");
        if (ro) {
            FILE *f = fopen(ro, "w");
            if (f) {
                fprintf(f, "ctrl %02X vmode %d mode %d wmode %d\n", m->ctrl, m->ctrl & 3,
                        (m->ctrl >> 2) & 3, (m->ctrl >> 4) & 3);
                fprintf(f, "tilebase %02X mapbase %02X vs %d hs %d\n", m->tilebase, m->mapbase,
                        (m->vs_hi << 8) | m->vs_lo, (m->hs_hi << 8) | m->hs_lo);
                fprintf(f, "sprh %02X sprx %d spry %d\n", m->sprh,
                        ((m->sprh & 3) << 8) | m->sprx_lo, ((m->sprh & 4) << 6) | m->spry_lo);
                for (int i = 0; i < 32; i++) fprintf(f, "reg %02X = %02X\n", i, m->regfile[i]);
                fclose(f);
            }
        }
    }
    fprintf(stderr, "emu: %d frames, progress $%02X, %.1f s of machine, %ld register writes under a list, %ld under a span\n",
            m->frame_n, m->progress, (double)m->dots * DOT_PS / 1e12, m->list_violations, m->span_violations);
    return m->list_violations || m->span_violations ? 1 : 0;
}
