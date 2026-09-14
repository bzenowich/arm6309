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
 *   - VDATA reads at WPTR, post-increment;
 *   - the palette: PDATH commits and PIDX steps;
 *   - VSCROLL latched at the top of the frame, HSCROLL at every line;
 *   - cell mode's concatenated tile address (graphics.md 6.4.1);
 *   - the display list: MOVE, WAIT, END. ⭐ bench/calib.asm measured where an
 *     effect lands: a MOVE after n WAITs from a GO inside line 0 shows on line
 *     n, and a MOVE before the first WAIT on line 1. Resuming at each line's
 *     start and rendering the line after is exactly that;
 *   - the VBL interrupt twelve lines after VBLANK's rise, which is when demo_tb
 *     saw /IRQ reach the CPU, pending until VSTAT is written;
 *   - graphics.md 10.3.3's rule, enforced: a CPU write to the card's
 *     registers while a list runs is reported, and fails the run - and so is
 *     one under a span (7.4: the span's colour and column reload are read from
 *     the register file);
 *   - the audio card's tempo timer on /FIRQ, and its register stream in
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
 *     boots NitrOS-9 here.
 *
 * What it records is demo_tb's frames.bin, so tools/checkdemo.py and
 * tools/mkvideo.py read either.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cpu6809.h"

#define DOTS_PER_E   12          /* E = 25.175 MHz / 12 */
#define DOTS_LINE    800
#define DOT_PS       39722ULL

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
    int irq_pending;
    int irq_line_due;            /* the line /IRQ reaches the CPU on, or -1 */
    long list_violations, span_violations;
    uint64_t busy_until;         /* dots */
    int lrun, lwait;
    uint16_t vs_frame;
    uint64_t dots, line_start;
    int line;                    /* of the frame */
    int total_lines;

    /* audio */
    uint16_t timer;
    int timer_on;
    uint64_t next_fire;          /* cycles */
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

    /* frames */
    FILE *frames;
    uint16_t *cur, *prv;
    int frame_n, prv_w, prv_h, have_prev;
    uint16_t ck0, ph0, lrun1;
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
    if (m->wadv == 1 && !m->lrun) {
        uint32_t row = ((m->wptr >> 10) + 1) & 511;
        uint32_t col = (((uint32_t)m->wp1 & 3) << 8) | m->wp0;
        m->wptr = (row << 10) | col;
    }
}

static void vram_write(uint8_t v)
{
    stall_for_span();
    int mode = (m->ctrl >> 3) & 3, n;
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
    int slot = (m->ctrl & 0x20) ? 8 : 4;   /* cell mode takes the bus one slot in two */
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

static void video_write(uint8_t r, uint8_t v)
{
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
    case 0x0E:
        if (v & 1) { m->lrun = 1; m->lwait = 0; list_run(); }
        break;
    case 0x10: m->pidx = v; break;
    case 0x11: m->pdatl = v; break;
    case 0x12: m->pal[m->pidx++] = (uint16_t)((v << 8) | m->pdatl); break;
    case 0x13: m->irq_pending = 0; break;
    case 0x14: m->wadv = v & 3; break;
    case 0x15: vram_write(v); break;
    case 0x17: m->tilebase = v & 31; break;
    case 0x19: m->mapbase = v & 127; break;
    default: break;
    }
}


static int active_lines(void);
static int in_vblank(void);

static uint8_t video_read(uint8_t r)
{
    switch (r) {
    case 0x13: {
        uint64_t col = m->dots - m->line_start;
        return (uint8_t)((m->busy_until > m->dots ? 0x80 : 0) | (in_vblank() ? 0x40 : 0)
                         | (col >= 640 ? 0x20 : 0) | (m->lrun ? 0x10 : 0) | (m->irq_pending ? 1 : 0));
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
            if (r == 0x03 || r == 0x04 || r == 0x10 || r == 0x11 || r == 0x12)
                video_write(r, v);
        }
    }
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
    switch (r) {
    case 0x0B: m->timer = (uint16_t)((m->timer & 0xFF) | (v << 8)); break;
    case 0x0C: m->timer = (uint16_t)((m->timer & 0xFF00) | v); break;
    case 0x05:
        if ((v & 0x40) && !m->timer_on) {
            m->timer_on = 1;
            m->next_fire = m->cpu.cycles + (5ULL * m->timer * 2097917ULL) / 3546895ULL;
        }
        break;
    case 0x04: if (!(v & 0x80) && (v & 0x10)) m->firq = 0; break;
    default: break;
    }
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
    if (m->ser_in && m->ser_in_pos < m->ser_in_n && m->cpu.cycles >= m->ser_at && m->cpu.cycles >= m->rx_next) {
        if (m->rx_n < 16) {
            m->rx[(m->rx_head + m->rx_n) & 15] = m->ser_in[m->ser_in_pos++];
            m->rx_n++;
        }
        m->rx_last = m->cpu.cycles;
        m->rx_next = m->cpu.cycles + uart_bit_cycles();
    }
}

static uint8_t rd(void *ctx, uint16_t a)
{
    (void)ctx;
    if (a >= 0xFFC0) return m->rom[a & 0x1FFF];
    if (a >= 0xFF00) {
        if (a >= 0xFF60 && a <= 0xFF7F) return video_read((uint8_t)(a - 0xFF60));
        if (a >= 0xFF38 && a <= 0xFF3F) return uart_read((uint8_t)(a - 0xFF38));
        if (a >= 0xFF90 && a <= 0xFF9F) return m->maphi[a & 15];
        if (a >= 0xFFA0 && a <= 0xFFAF) return m->maplo[a & 15];
        return 0x00;                      /* ASTAT never busy */
    }
    uint8_t hi = m->maphi[entry(a)], lo = m->maplo[entry(a)];
    if (hi == 0x01) return m->rom[((uint32_t)lo << 13 | (a & 0x1FFF)) & 0xFFFFF];
    return rampage(hi, lo)[a & 0x1FFF];
}

static void wr(void *ctx, uint16_t a, uint8_t v)
{
    (void)ctx;
    if (a >= 0xFF00) {
        if (a >= 0xFF60 && a <= 0xFF7F) {
            /* graphics.md 10.3.1 and 10.3.3: while LRUN the engine owns WPTR and a
             * CPU register write can take a descriptor byte from it */
            if (m->lrun && ++m->list_violations <= 8)
                fprintf(stderr, "FAIL  %.3f s: the CPU wrote $%04X := $%02X while a display list ran (PC $%04X)\n",
                        (double)m->dots * DOT_PS / 1e12, a, v, m->cpu.pc);
            /* graphics.md 7.4: a span's colour and WADV 01's column reload are read
             * from the register file, and a CPU register access takes it away */
            if (a != 0xFF75 && m->busy_until > m->dots && ++m->span_violations <= 8)
                fprintf(stderr, "FAIL  %.3f s: the CPU wrote $%04X := $%02X under a span (PC $%04X)\n",
                        (double)m->dots * DOT_PS / 1e12, a, v, m->cpu.pc);
            video_write((uint8_t)(a - 0xFF60), v);
        }
        else if (a >= 0xFF90 && a <= 0xFF9F) m->maphi[a & 15] = v;
        else if (a >= 0xFFA0 && a <= 0xFFAF) m->maplo[a & 15] = v;
        else if (a >= 0xFF40 && a <= 0xFF4F) audio_write((uint8_t)(a & 15), v);
        else if (a >= 0xFF38 && a <= 0xFF3F) uart_write((uint8_t)(a - 0xFF38), v);
        else if (a >= 0xFFB0 && a <= 0xFFBF) m->task = v & 1;
        else if (a == 0xFF2F) {
            m->progress = v;
            fprintf(stderr, "      %8.3f s  progress $%02X\n", (double)m->dots * DOT_PS / 1e12, v);
        }
        return;
    }
    uint8_t hi = m->maphi[entry(a)], lo = m->maplo[entry(a)];
    if (hi == 0x01) return;
    rampage(hi, lo)[a & 0x1FFF] = v;
}

/* ------------------------------------------------------------------ video out */
static int vlines(void) { return (m->ctrl & 1) ? 525 : 449; }
static int active_lines(void) { return (m->ctrl & 1) ? 480 : 400; }
static int in_vblank(void) { return m->line >= active_lines(); }

static void render_line(int y)
{
    if (y == 0) {
        m->vs_frame = (uint16_t)((m->vs_hi << 8) | m->vs_lo);
        m->ck0 = ram16(0xC600);
        m->ph0 = ram16(0xC602);
        m->frame_t = m->dots * DOT_PS;
    }
    if (y == 1) m->lrun1 = (uint16_t)m->lrun;
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
    uint16_t camk = ram16(0xC208), herok = ram16(0xC20A), missed = ram16(0xC225);
    uint16_t ck1 = ram16(0xC600), ph1 = ram16(0xC602);
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
        int act = active_lines();
        if (m->line == act) {                 /* VBLANK rises */
            m->irq_line_due = act + 12;       /* ... and /IRQ follows, as demo_tb measured */
            if (m->frame_active) emit_frame();
            m->frame_active = 0;
        }
        if (m->line == m->irq_line_due) {
            if (m->ctrl & 0x40) m->irq_pending = 1;
            m->irq_line_due = -1;
        }
        if (m->line >= vlines()) m->line = 0;
        if (m->lrun && m->lwait) { m->lwait = 0; list_run(); }
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
    if (getenv("SERIAL_IN")) {
        FILE *si = fopen(getenv("SERIAL_IN"), "rb");
        if (!si) { fprintf(stderr, "FAIL  cannot read SERIAL_IN %s\n", getenv("SERIAL_IN")); return 1; }
        static uint8_t buf[1 << 16];
        m->ser_in_n = (long)fread(buf, 1, sizeof buf, si);
        fclose(si);
        m->ser_in = buf;
        m->ser_at = (uint64_t)(atof(getenv("SERIAL_AT") ? getenv("SERIAL_AT") : "0") * 2097917.0);
    }
    if (getenv("SERIAL_STOP") && *getenv("SERIAL_STOP")) {
        m->ser_stop = getenv("SERIAL_STOP");
        m->ser_stop_len = strlen(m->ser_stop);
    }
    m->cur = calloc(640 * 512, 2);
    m->prv = calloc(640 * 512, 2);
    double secs = atof(argv[3]);

    /* boot.asm's handoff (software/boot/README.md): ROM pages 1-2 at blocks 4-5,
     * ROM page 0 at block 7, the SIMM at block 6 */
    for (int i = 0; i < 16; i++) { m->maphi[i] = 0x02; m->maplo[i] = (uint8_t)i; }
    m->maphi[4] = 1; m->maplo[4] = 1;
    m->maphi[5] = 1; m->maplo[5] = 2;
    m->maphi[7] = 1; m->maplo[7] = 0;

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
        m->cpu.irq = (m->irq_pending && (m->ctrl & 0x40)) || uart_irq();
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
        if (trace_n > 0 && (!getenv("TRACE_AT") || m->dots * DOT_PS >= (uint64_t)(atof(getenv("TRACE_AT")) * 1e12))) {
            trace_n--;
            fprintf(stderr, "PC %04X A %02X B %02X X %04X Y %04X U %04X S %04X CC %02X DP %02X T %d\n", m->cpu.pc, m->cpu.a,
                    m->cpu.b, m->cpu.x, m->cpu.y, m->cpu.u, m->cpu.s, m->cpu.cc, m->cpu.dp, m->task);
        }
        int e = cpu6809_step(&m->cpu);
        m->dots = m->cpu.cycles * DOTS_PER_E;
        if (m->timer_on && m->cpu.cycles >= m->next_fire) {
            m->firq = 1;
            m->next_fire += (5ULL * m->timer * 2097917ULL) / 3546895ULL;
        }
        raster();
        uart_step();
        if (m->stop) { fprintf(stderr, "      %8.3f s  SERIAL_STOP seen\n", (double)m->dots * DOT_PS / 1e12); break; }
        (void)e;
        if (m->dots >= next_report) {
            fprintf(stderr, "      %8.3f s  prog $%02X  frames %d  ck %u\n", (double)m->dots * DOT_PS / 1e12,
                    m->progress, m->frame_n, ram16(0xC600));
            next_report += (uint64_t)(5e12 / DOT_PS);
        }
        if (m->progress >= 0xE0) { fprintf(stderr, "FAIL  the ROM reported $%02X\n", m->progress); break; }
    }
    fclose(m->frames);
    fclose(m->trace);
    fclose(m->times);
    fclose(m->ser_out);
    snprintf(path, sizeof path, "%s/sync.txt", argv[2]);
    f = fopen(path, "w");
    fprintf(f, "cc0_ps 0\nend_ps %llu\n", (unsigned long long)(m->dots * DOT_PS));
    fclose(f);
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
    if (atexit_ring) {
        fprintf(stderr, "last PCs:");
        for (unsigned i = 0; i < 256; i++) fprintf(stderr, "%s%04X", i % 16 ? " " : "\n  ", atexit_ring[(*atexit_ri + i) & 255]);
        fprintf(stderr, "\n");
    }
    fprintf(stderr, "emu: %d frames, progress $%02X, %.1f s of machine, %ld register writes under a list, %ld under a span\n",
            m->frame_n, m->progress, (double)m->dots * DOT_PS / 1e12, m->list_violations, m->span_violations);
    return m->list_violations || m->span_violations ? 1 : 0;
}
