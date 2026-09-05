/* Tests for the reference module player — audio/refplayer/.
 *
 * These check the things audio/docs/modplayer.md §9 says a test corpus must check,
 * on a synthetic module rather than on copyrighted material: the shadow
 * reload, non-looping samples, period accuracy against the colour clock, the
 * tempo mapping, the volume law, and loader rejection.
 *
 * The synthetic module is built here rather than shipped as a binary so the
 * thing under test and the thing it is tested against are both readable.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "mod.h"
#include "card.h"
#include "render.h"
#include <math.h>
#include <unistd.h>

static int failures;

static void check(int cond, const char *what)
{
    if (!cond) { printf("FAIL: %s\n", what); failures++; }
}

static void check_eq(long got, long want, const char *what)
{
    if (got != want) { printf("FAIL: %s: got %ld, want %ld\n", what, got, want); failures++; }
}

/* ---------------------------------------------------- synthetic module ---- */

static void be16w(uint8_t *p, unsigned v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }

/* One sample: 32 bytes of ramp, then a 32-byte loop of alternating +64/-64.
 * Sample 2: 16 bytes, no loop. One pattern, one row per channel. */
#define S1_LEN 64u
#define S2_LEN 16u

static size_t build_mod(uint8_t **out, unsigned period, unsigned effect, unsigned param)
{
    size_t patbytes = 1024u;
    size_t total = 1084u + patbytes + S1_LEN + S2_LEN;
    uint8_t *f = calloc(total, 1);
    uint8_t *h;

    memcpy(f, "reftest", 7);

    h = f + 20;                                   /* sample 1 */
    memcpy(h, "loop", 4);
    be16w(h + 22, S1_LEN / 2u);                   /* length, words          */
    h[24] = 0;                                    /* finetune               */
    h[25] = 64;                                   /* volume                 */
    be16w(h + 26, 16);                            /* repeat offset, words   */
    be16w(h + 28, 16);                            /* repeat length, words   */

    h = f + 20 + 30;                              /* sample 2 */
    memcpy(h, "oneshot", 7);
    be16w(h + 22, S2_LEN / 2u);
    h[25] = 64;
    be16w(h + 26, 0);
    be16w(h + 28, 1);                             /* replen 1 == no loop    */

    f[950] = 1;                                   /* song length            */
    f[951] = 127;
    f[952] = 0;                                   /* order[0] = pattern 0   */
    memcpy(f + 1080, "M.K.", 4);

    /* Row 0: ch0 plays sample 1 at `period` with the given effect. */
    {
        uint8_t *c0 = f + 1084;
        c0[0] = (uint8_t)((1u & 0xF0u) | ((period >> 8) & 0x0Fu));
        c0[1] = (uint8_t)(period & 0xFFu);
        c0[2] = (uint8_t)(((1u & 0x0Fu) << 4) | (effect & 0x0Fu));
        c0[3] = (uint8_t)param;
        /* ch1 plays sample 2, same period, no effect. */
        c0[4] = (uint8_t)((2u & 0xF0u) | ((period >> 8) & 0x0Fu));
        c0[5] = (uint8_t)(period & 0xFFu);
        c0[6] = (uint8_t)((2u & 0x0Fu) << 4);
        c0[7] = 0;
    }

    /* Sample data. */
    {
        uint8_t *d = f + 1084 + patbytes;
        for (unsigned i = 0; i < 32u; i++) { d[i] = (uint8_t)(i * 2u); }
        for (unsigned i = 32; i < S1_LEN; i++) { d[i] = (uint8_t)((i & 1u) ? 0xC0u : 0x40u); }
        for (unsigned i = 0; i < S2_LEN; i++) { d[S1_LEN + i] = 0x7F; }
    }

    *out = f;
    return total;
}

/* Probe modules go to a temp directory, never to the working directory: ctest
 * runs from the build tree and two concurrent builds would collide on the
 * name. */
static const char *write_tmp(const uint8_t *f, size_t n, char *buf, size_t buflen)
{
    const char *dir = getenv("TMPDIR");
    FILE *fp;
    static unsigned serial;

    if (!dir || !*dir) { dir = "/tmp"; }
    snprintf(buf, buflen, "%s/reftest_%lu_%u_%u.mod", dir,
             (unsigned long)getpid(), (unsigned)n, serial++);
    fp = fopen(buf, "wb");
    if (!fp) { return NULL; }
    if (fwrite(f, 1, n, fp) != n) { fclose(fp); return NULL; }
    fclose(fp);
    return buf;
}

/* ------------------------------------------------------------- the tests -- */

static uint8_t *sram;

/* The replayer charges each register store its real cost; the test only needs
 * time to pass, not audio to come out. */
static void advance_only(void *vp, unsigned cc)
{
    for (unsigned i = 0; i < cc; i++) { card_step((card_t *)vp); }
}

static void test_volume_lut(void)
{
    card_t c;
    card_reset(&c, sram, 128u * 1024u);
    card_load_linear_lut(&c);

    /* audio/docs/audio.md §6.1: entry = SAMP * min(VOL,64) / 4, 12-bit signed. */
    check_eq(c.lut[(64u << 8) | 0x7Fu], 127 * 64 / 4, "LUT: +127 at full volume");
    check_eq(c.lut[(64u << 8) | 0x80u], -128 * 64 / 4, "LUT: -128 at full volume");
    check_eq(c.lut[(0u << 8) | 0x7Fu], 0, "LUT: silence at volume 0");
    check_eq(c.lut[(32u << 8) | 0x40u], 64 * 32 / 4, "LUT: half volume");

    /* The 7-bit volume field is the whole point of the LIDX/LDATA change: at
     * 6 bits, volume 64 would have been unreachable and every channel would sit
     * 63/64 of the way up. */
    check_eq(c.lut[(65u << 8) | 0x7Fu], c.lut[(64u << 8) | 0x7Fu],
             "LUT: volume above 64 clamps rather than wrapping");
    check(c.lut[(64u << 8) | 0x7Fu] > c.lut[(63u << 8) | 0x7Fu],
          "LUT: volume 64 is louder than 63 (the 7th bit exists)");
}

static void test_period_is_the_colour_clock(void)
{
    /* A channel at PER=n must fetch a new byte every n colour clocks, exactly.
     * This is audio/docs/audio.md §4.1 and §4.2 -- if it is wrong, every module is
     * detuned by the ratio. */
    card_t c;
    unsigned per = 428;                  /* ProTracker C-2 */
    unsigned ticks = 0;
    int8_t last;

    card_reset(&c, sram, 128u * 1024u);
    card_load_linear_lut(&c);
    /* i+1, never 0: a first sample of 0 is indistinguishable from the
     * reset value and the first fetch would go uncounted. */
    for (unsigned i = 0; i < 256u; i++) { sram[i] = (uint8_t)(i + 1u); }

    card_write(&c, A_AIDX, ST_LC2);
    card_write(&c, A_ADATA, 0); card_write(&c, A_ADATA, 0); card_write(&c, A_ADATA, 0);
    card_write(&c, A_ADATA, 0); card_write(&c, A_ADATA, 128);          /* LEN words */
    card_write(&c, A_ADATA, (uint8_t)(per >> 8)); card_write(&c, A_ADATA, (uint8_t)per);
    card_write(&c, A_ADATA, 64);                                       /* VOL */
    card_write(&c, A_ACTRL, ACTRL_ENABLE);
    card_write(&c, A_ADMACON, 0x81);

    for (unsigned i = 0; i < CARD_ENABLE_LATENCY + 1u; i++) { card_step(&c); }
    last = c.ch[0].samp;
    for (unsigned i = 0; i < per * 20u; i++) {
        card_step(&c);
        if (c.ch[0].samp != last) { ticks++; last = c.ch[0].samp; }
    }
    check_eq(ticks, 20, "PER=428 fetches exactly 20 samples in 20*428 colour clocks");

    /* 3546895 / 428 = 8286.2 Hz -- the Amiga's C-2. */
    check_eq(CARD_CC_PAL / (long)per, 8287L, "PER=428 is 8287 Hz on the PAL clock");
}

static void test_shadow_reload(void)
{
    /* audio/docs/audio.md §3.3 / modplayer.md §5.3: the card must reload from LC/LEN
     * AT BUFFER END, taking whatever the host wrote after the note started.
     * This is the single behaviour that makes ProTracker's one-shot-then-loop
     * idiom work, and getting it wrong plays every instrument as an endless
     * attack. */
    card_t c;
    unsigned per = 100;

    card_reset(&c, sram, 128u * 1024u);
    card_load_linear_lut(&c);
    for (unsigned i = 0; i < 64u; i++) { sram[i] = (uint8_t)(i + 1u); }

    /* Start at 0, length 8 words = 16 bytes. */
    card_write(&c, A_AIDX, ST_LC2);
    card_write(&c, A_ADATA, 0); card_write(&c, A_ADATA, 0); card_write(&c, A_ADATA, 0);
    card_write(&c, A_ADATA, 0); card_write(&c, A_ADATA, 8);
    card_write(&c, A_ADATA, 0); card_write(&c, A_ADATA, (uint8_t)per);
    card_write(&c, A_ADATA, 64);
    card_write(&c, A_ACTRL, ACTRL_ENABLE);
    card_write(&c, A_ADMACON, 0x81);

    /* The CPU takes real time to get to its next store, and the card's enable
     * latch is bounded at CARD_ENABLE_LATENCY colour clocks — so by the time
     * the loop pointer is written, PTR/CNT have already latched from the
     * one-shot LC/LEN. Modelling that gap is the whole point; without it the
     * loop pointer wins the race and the one-shot never plays. */
    for (unsigned i = 0; i < MOD_STORE_CC_DEFAULT; i++) { card_step(&c); }

    /* Now, while the one-shot is still playing, point the loop at byte 32. */
    card_write(&c, A_AIDX, ST_LC2);
    card_write(&c, A_ADATA, 0); card_write(&c, A_ADATA, 0); card_write(&c, A_ADATA, 32);
    card_write(&c, A_ADATA, 0); card_write(&c, A_ADATA, 4);          /* 8 bytes */

    /* 16 one-shot bytes, then the loop. Sample n is sram[n] = n+1. */
    {
        int seen[40];
        unsigned k = 0;
        int8_t last = 0;
        for (unsigned i = 0; i < per * 40u && k < 40u; i++) {
            card_step(&c);
            if (c.ch[0].samp != last) { last = c.ch[0].samp; seen[k++] = last; }
        }
        check_eq(seen[0], 1, "shadow: first byte is sram[0]");
        check_eq(seen[15], 16, "shadow: 16th byte is sram[15] (the one-shot ran)");
        check_eq(seen[16], 33, "shadow: loops to the NEW LC (byte 32), not back to 0");
        check_eq(seen[23], 40, "shadow: loop runs its 8 bytes");
        check_eq(seen[24], 33, "shadow: and repeats from the loop point, forever");
    }
    check(c.intreq & AINT_CH0, "shadow: buffer-end raised the channel interrupt");
}

static void test_tempo(void)
{
    /* audio/docs/audio.md §8.2. The clock is colourclock/5 and the reload is
     * 1773447/BPM. Confusing the two detunes every tempo by exactly 2.5x, which
     * is what the first draft of that section did. */
    card_t c;
    uint16_t n = (uint16_t)(1773447L / 125L);
    unsigned fires = 0;

    card_reset(&c, sram, 128u * 1024u);
    card_write(&c, A_ACTRL, (uint8_t)(ACTRL_ENABLE | ACTRL_TIMER));
    card_write(&c, A_TIMER1, (uint8_t)(n >> 8));
    card_write(&c, A_TIMER0, (uint8_t)(n & 0xFFu));
    card_write(&c, A_AINTENA, (uint8_t)(0x80u | AINT_TIMER));

    for (long i = 0; i < CARD_CC_PAL; i++) {         /* one second */
        card_step(&c);
        if (c.intreq & AINT_TIMER) { fires++; card_write(&c, A_AINTREQ, AINT_TIMER); }
    }
    check_eq(n, 14187, "tempo: BPM 125 reload is 14187");
    check(fires == 50u, "tempo: BPM 125 fires 50 times a second");

    /* ACTRL b6 is the run bit. Without it an armed timer can never be stopped
     * and there is no clean "stop the music" path. */
    card_write(&c, A_ACTRL, ACTRL_ENABLE);
    card_write(&c, A_AINTREQ, AINT_TIMER);
    for (long i = 0; i < CARD_CC_PAL; i++) { card_step(&c); }
    check(!(c.intreq & AINT_TIMER), "tempo: clearing ACTRL b6 stops the timer");
}

static void test_loader_and_playback(void)
{
    card_t c;
    mod_song s;
    mod_player p;
    uint8_t *f;
    size_t n = build_mod(&f, 428, 0, 0);
    char namebuf[256];
    const char *path = write_tmp(f, n, namebuf, sizeof namebuf);
    char err[128];

    check(path != NULL, "loader: temp file written");
    if (!path) { free(f); return; }

    card_reset(&c, sram, 128u * 1024u);
    check_eq(mod_load(&s, &c, path, err, sizeof err), 0, "loader: accepts a valid M.K. module");
    check_eq(s.npatterns, 1, "loader: one pattern");
    check_eq(s.songlength, 1, "loader: one position");

    /* §4.2: the null-loop block, and sample 0 aliased to it. */
    check_eq((long)s.sample_addr[0], MOD_NULL_LOOP, "loader: sample 0 is the null block");
    check_eq(sram[0], 0, "loader: null block is silent");
    check_eq(sram[1], 0, "loader: null block is silent");
    check_eq((long)s.sample_addr[1], MOD_SAMPLE_BASE, "loader: sample 1 follows the null block");
    check_eq((long)s.sample_rep[1], MOD_SAMPLE_BASE + 32, "loader: loop point relocated");
    check_eq(s.sample_replen[1], 16, "loader: repeat length copied verbatim, in words");

    /* §4.2: replen <= 1 means no loop, and the loop points at silence. */
    check_eq((long)s.sample_rep[2], MOD_NULL_LOOP, "loader: non-looping sample loops to silence");
    check_eq(s.sample_replen[2], 1, "loader: null loop is one word");

    /* §4.3: nothing but addresses is transformed. */
    check_eq(s.sample_len[1], S1_LEN / 2u, "loader: length copied verbatim, in words");
    check_eq(s.sample_vol[1], 64, "loader: volume copied verbatim");
    check_eq(s.sample_ft[1], 0, "loader: finetune copied as a row index");

    /* Play a second and confirm the card never reads outside populated RAM and
     * that the one-shot channel goes quiet while the looped one does not. */
    memset(&p, 0, sizeof p);
    mod_set_advance(&p, advance_only, &c, MOD_STORE_CC_DEFAULT);
    mod_start(&p, &s, &c);
    {
        long quiet_ch1 = 0, active_ch0 = 0;
        for (long i = 0; i < CARD_CC_PAL; i++) {
            if (card_firq(&c)) { mod_tick(&p); }
            card_step(&c);
            if (i > CARD_CC_PAL / 2) {
                if (c.ch[1].samp == 0) { quiet_ch1++; }
                if (c.ch[0].samp != 0) { active_ch0++; }
            }
        }
        check_eq((long)c.oob_reads, 0, "playback: no fetch outside populated RAM");
        check(quiet_ch1 > CARD_CC_PAL / 4, "playback: the non-looping sample went silent");
        check(active_ch0 > CARD_CC_PAL / 4, "playback: the looping sample kept playing");
    }
    check(p.ticks > 40u, "playback: the tempo timer drove ~50 ticks in a second");

    mod_free(&s);
    free(f);
    remove(path);
}

static void test_loader_rejects(void)
{
    card_t c;
    mod_song s;
    uint8_t *f;
    size_t n = build_mod(&f, 428, 0, 0);
    char namebuf[256], err[128];
    const char *path;

    /* §4.6: an unknown magic must be rejected, not guessed at. */
    memcpy(f + 1080, "ZZZZ", 4);
    path = write_tmp(f, n, namebuf, sizeof namebuf);
    card_reset(&c, sram, 128u * 1024u);
    check(mod_load(&s, &c, path, err, sizeof err) != 0, "loader: rejects unknown magic");
    remove(path);

    /* §2.3: 8-channel modules are out of scope until audio.md §11.2 is built. */
    memcpy(f + 1080, "8CHN", 4);
    path = write_tmp(f, n, namebuf, sizeof namebuf);
    card_reset(&c, sram, 128u * 1024u);
    check(mod_load(&s, &c, path, err, sizeof err) != 0, "loader: rejects 8-channel modules");
    remove(path);

    /* §4.6: a zero song length is malformed. */
    memcpy(f + 1080, "M.K.", 4);
    f[950] = 0;
    path = write_tmp(f, n, namebuf, sizeof namebuf);
    card_reset(&c, sram, 128u * 1024u);
    check(mod_load(&s, &c, path, err, sizeof err) != 0, "loader: rejects zero song length");
    remove(path);

    /* §4.6: truncation is common and must NOT be rejected -- clamp and play. */
    f[950] = 1;
    path = write_tmp(f, n - 8u, namebuf, sizeof namebuf);
    card_reset(&c, sram, 128u * 1024u);
    check_eq(mod_load(&s, &c, path, err, sizeof err), 0, "loader: accepts a truncated file");
    check(s.truncated, "loader: and says so");
    mod_free(&s);
    remove(path);

    free(f);
}

/* Drive the render chain with a sine at the colour clock and return output RMS.
 * Peak tracking is not good enough here: at 8 kHz there are only six output
 * samples per cycle and peak underestimates by over a dB. */
static double filter_rms(double hz, int led, int bypass)
{
    render_t r;
    double sum = 0.0, n = 0.0;

    if (render_open(&r, NULL, 48000, CARD_CC_PAL) != 0) { return -1.0; }
    render_set_filter(&r, led, bypass);
    for (long i = 0; i < CARD_CC_PAL / 2; i++) {
        double t = (double)i / (double)CARD_CC_PAL;
        int v = (int)lrint(1000.0 * sin(2.0 * 3.14159265358979323846 * hz * t));
        uint32_t before = r.frames;
        render_push(&r, v, v);
        if (r.frames != before && i > CARD_CC_PAL / 8) { sum += r.last_l * r.last_l; n += 1.0; }
    }
    return n > 0.0 ? sqrt(sum / n) : -1.0;
}

static void test_filters(void)
{
    /* audio/docs/audio.md §7. Two things must hold, and only the first is a matter of
     * modelling taste: the fixed pole must be the A500's 4421 Hz single pole,
     * and NEITHER filter may be louder than bypass at any frequency. The second
     * is what caught a wrong Butterworth Q pair that left a +0.6 dB passband
     * bump in the LED chain -- a filter cannot add energy. */
    static const double hz[] = { 125, 250, 500, 1000, 2000, 4000, 8000 };

    for (unsigned i = 0; i < sizeof hz / sizeof hz[0]; i++) {
        double b = filter_rms(hz[i], 0, 1);
        double f = filter_rms(hz[i], 0, 0);
        double l = filter_rms(hz[i], 1, 0);
        char msg[96];

        snprintf(msg, sizeof msg, "filter: fixed never exceeds bypass at %.0f Hz", hz[i]);
        check(f <= b * 1.001, msg);
        snprintf(msg, sizeof msg, "filter: LED never exceeds fixed at %.0f Hz", hz[i]);
        check(l <= f * 1.001, msg);
    }

    /* A single pole at 4421 Hz is -2.60 dB at 4 kHz and -6.30 dB at 8 kHz. */
    {
        double b4 = filter_rms(4000, 0, 1), f4 = filter_rms(4000, 0, 0);
        double db = 20.0 * log10(f4 / b4);
        check(db < -2.4 && db > -2.8, "filter: fixed pole is 4421 Hz (-2.6 dB at 4 kHz)");
    }
    /* The LED stage is ONE 2nd-order Sallen-Key at 3275 Hz, not a cascade: a
     * real A500 has a single section there. Three independent measurements pin
     * both the order and the corner, and each of them rules out the 4-pole
     * model this replaced. Everything is measured as LED minus fixed, so the
     * always-in 4421 Hz pole cancels out.
     *
     *   at the corner       2nd-order Butterworth is -3.01 dB, by definition
     *   6 -> 12 kHz         two poles are -12.0 dB/octave (four would be -24)
     *   at 8 kHz            1/sqrt(1 + (8000/3275)^4) = -15.64 dB */
    {
        double fc = 20.0 * log10(filter_rms(3275, 1, 0) / filter_rms(3275, 0, 0));
        double f6 = 20.0 * log10(filter_rms(6000, 1, 0) / filter_rms(6000, 0, 0));
        double f12 = 20.0 * log10(filter_rms(12000, 1, 0) / filter_rms(12000, 0, 0));
        double f8 = 20.0 * log10(filter_rms(8000, 1, 0) / filter_rms(8000, 0, 0));

        check(fc < -2.7 && fc > -3.3, "filter: LED stage is -3 dB at its 3275 Hz corner");
        check(f12 - f6 < -10.5 && f12 - f6 > -13.5,
              "filter: LED stage rolls off 12 dB/octave -- two poles, not four");
        check(f8 < -15.0 && f8 > -16.3, "filter: LED stage is -15.6 dB at 8 kHz");
    }
    /* And the whole chain, LED on, against no filtering at all: the fixed pole
     * and two switched poles together. Four switched poles would put this near
     * -37 dB. */
    {
        double b8 = filter_rms(8000, 0, 1), l8 = filter_rms(8000, 1, 0);
        double db = 20.0 * log10(l8 / b8);
        check(db < -20.5 && db > -23.5, "filter: LED chain is -22 dB at 8 kHz (3 poles)");
    }
}

static void test_period_table(void)
{
    /* audio/docs/modplayer.md §5.4 / §11 item 4. The table is copied, not computed,
     * so the risk is not arithmetic -- it is transcription. These are the same
     * checks the table was validated against when it was installed, kept here
     * so an edit to period_table.c cannot silently corrupt it. */
    const uint16_t (*t)[36] = mod_protracker_period_table;
    double worst = 0.0;
    int notfloor = 0;

    /* 1. Every row strictly decreasing. Catches a swapped or duplicated pair. */
    for (unsigned r = 0; r < 16u; r++) {
        int ok = 1;
        for (unsigned i = 0; i + 1 < 36u; i++) { if (t[r][i] <= t[r][i + 1]) { ok = 0; } }
        if (!ok) { printf("FAIL: period table row %u is not strictly decreasing\n", r); failures++; }
    }

    /* 2. Every entry within 1.5 of 856 / 2^(ft/96) / 2^(note/12). ProTracker's
     *    roundings are inconsistent but they are still roundings; a mistyped
     *    digit lands far outside this and a transposition always does. */
    for (unsigned r = 0; r < 16u; r++) {
        int ft = (r < 8u) ? (int)r : (int)r - 16;
        for (unsigned i = 0; i < 36u; i++) {
            double th = 856.0 / pow(2.0, (double)ft / 96.0) / pow(2.0, (double)i / 12.0);
            double d = fabs((double)t[r][i] - th);
            if (d > worst) { worst = d; }
        }
    }
    check(worst < 1.5, "period table: every entry is within 1.5 of theory");

    /* 3. Finetune -8 is one whole semitone flat, so its row must be [907]
     *    followed by the finetune-0 row less its last entry. A structural
     *    identity that no plausible typo survives. */
    {
        int ok = (t[8][0] == 907u);
        for (unsigned i = 0; i < 35u; i++) { if (t[8][i + 1] != t[0][i]) { ok = 0; } }
        check(ok, "period table: ft-8 row == [907] + ft0[0..34]");
    }

    /* 4. Known anchors, independently confirmed against libopenmpt and
     *    libmodplug when the table was installed. */
    check_eq(t[0][0],  856, "period table: ft0 C-1 is 856");
    check_eq(t[0][35], 113, "period table: ft0 B-3 is 113");
    check_eq(t[7][35], 108, "period table: ft+7 B-3 is 108");
    check_eq(t[15][0], 862, "period table: ft-1 C-1 is 862");

    /* 5. And the reason it cannot be derived: most octave relations are NOT a
     *    halving. If this ever came out as 0, someone replaced the table with a
     *    computed one. */
    for (unsigned r = 0; r < 16u; r++) {
        for (unsigned i = 0; i < 24u; i++) {
            if (t[r][i + 12] != t[r][i] / 2u) { notfloor++; }
        }
    }
    check_eq(notfloor, 86, "period table: 86 of 384 octaves are not floor(x/2)");
}


/* ------------------------------------------------- capacity and formats --- */

/* Two samples totalling `bytes`, so the figure can be aimed at a RAM size.
 * Two, because a single sample's length field is 16 bits of WORDS and cannot
 * express more than 131070 bytes. */
static size_t build_big_mod(uint8_t **out, uint32_t bytes)
{
    size_t total = 1084u + 1024u + bytes;
    uint8_t *f = calloc(total, 1);
    uint8_t *h = f + 20;
    uint32_t half = (bytes / 4u) * 2u;

    memcpy(f, "big", 3);
    memcpy(h, "big1", 4);
    be16w(h + 22, (unsigned)(half / 2u));
    h[25] = 64;
    be16w(h + 28, 1);
    h += 30;
    memcpy(h, "big2", 4);
    be16w(h + 22, (unsigned)((bytes - half) / 2u));
    h[25] = 64;
    be16w(h + 28, 1);
    f[950] = 1;
    f[952] = 0;
    memcpy(f + 1080, "M.K.", 4);
    {
        uint8_t *c0 = f + 1084;
        c0[0] = 0x11; c0[1] = 0xAC;                   /* sample 1, period 428 */
    }
    for (uint32_t i = 0; i < bytes; i++) { f[1084u + 1024u + i] = (uint8_t)i; }
    *out = f;
    return total;
}

static void test_loader_capacity(void)
{
    /* modplayer.md §4.7: "Reject with a clear message. The default." The bound
     * is the RAM that is POPULATED. Checking the 512 KB of footprints instead
     * accepts a module the card cannot hold and leaves a channel fetching
     * unwritten SRAM at 28 kHz -- §4.6's nightmare case, and silent. */
    card_t c;
    mod_song s;
    uint8_t *f;
    size_t n = build_big_mod(&f, 180000u);
    char namebuf[256], err[160];
    const char *path = write_tmp(f, n, namebuf, sizeof namebuf);

    check(path != NULL, "capacity: temp file written");
    if (!path) { free(f); return; }

    memset(err, 0, sizeof err);
    card_reset(&c, sram, 128u * 1024u);
    check(mod_load(&s, &c, path, err, sizeof err) != 0,
          "capacity: 180 KB of samples is rejected at 128 KB populated");
    check(strstr(err, "128 KB") != NULL, "capacity: and the message names the populated size");

    /* The same module fits once the other SRAMs are populated (§4.7 option 3),
     * so the check is a bound and not a blanket refusal. */
    card_reset(&c, sram, 512u * 1024u);
    check_eq(mod_load(&s, &c, path, err, sizeof err), 0,
             "capacity: and accepted at 512 KB populated");
    mod_free(&s);

    /* A NULL err must not be a null dereference: the loader is called that way
     * by anything that only wants the return code. */
    card_reset(&c, sram, 128u * 1024u);
    check(mod_load(&s, &c, path, NULL, 0) != 0, "capacity: rejects with err == NULL too");

    remove(path);
    free(f);
}

static void test_loader_15_sample(void)
{
    /* modplayer.md §2.2. Two things about the 15-sample format are traps: the
     * repeat offset is in BYTES, not words -- the only field that is -- and the
     * files themselves carry junk in the unused tail of a name, so a
     * printable-names heuristic bounces genuine modules. */
    card_t c;
    mod_song s;
    char namebuf[256], err[160];
    const char *path;
    size_t total = 600u + 1024u + 64u;
    uint8_t *f = calloc(total, 1);
    uint8_t *h = f + 20;

    memcpy(f, "soundtracker", 12);
    memcpy(h, "st-sample", 9);
    h[12] = 0xFFu;                                    /* junk in the name tail */
    h[13] = 0x8Au;
    be16w(h + 22, 32);                                /* 64 bytes             */
    h[25] = 64;
    be16w(h + 26, 32);                                /* repeat offset, BYTES */
    be16w(h + 28, 16);                                /* repeat length, words */
    f[470] = 1;                                       /* song length          */
    f[472] = 0;
    {
        uint8_t *c0 = f + 600;
        c0[0] = 0x11; c0[1] = 0xAC;
    }
    for (unsigned i = 0; i < 64u; i++) { f[600u + 1024u + i] = (uint8_t)i; }

    path = write_tmp(f, total, namebuf, sizeof namebuf);
    check(path != NULL, "15-sample: temp file written");
    if (!path) { free(f); return; }

    card_reset(&c, sram, 128u * 1024u);
    check_eq(mod_load(&s, &c, path, err, sizeof err), 0,
             "15-sample: accepted despite non-printable bytes in a sample name");
    check_eq((long)s.sample_addr[1], MOD_SAMPLE_BASE, "15-sample: sample 1 relocated");
    check_eq((long)s.sample_rep[1], MOD_SAMPLE_BASE + 32,
             "15-sample: repeat offset read as BYTES, not words");
    check_eq(s.sample_replen[1], 16, "15-sample: repeat length is still words");
    mod_free(&s);
    remove(path);
    free(f);
}

/* ------------------------------------------------------------- effects ---- */

/* A one-pattern module whose 64 rows the caller fills, and one 1024-byte
 * looping sample -- long enough that a 9xx offset lands inside it. */
typedef struct { uint8_t smp; uint16_t per; uint8_t eff; uint8_t par; } cellspec;

#define E_LEN 1024u

static size_t build_effect_mod(uint8_t **out, const cellspec rows[MOD_ROWS][MOD_CHANNELS])
{
    size_t total = 1084u + 1024u + E_LEN;
    uint8_t *f = calloc(total, 1);
    uint8_t *h = f + 20;

    memcpy(f, "effects", 7);
    memcpy(h, "saw", 3);
    be16w(h + 22, E_LEN / 2u);
    h[25] = 64;
    be16w(h + 26, E_LEN / 4u);                        /* loop the second half */
    be16w(h + 28, E_LEN / 4u);
    f[950] = 1;
    f[952] = 0;
    memcpy(f + 1080, "M.K.", 4);

    for (unsigned r = 0; r < MOD_ROWS; r++) {
        for (unsigned ci = 0; ci < MOD_CHANNELS; ci++) {
            const cellspec *cs = &rows[r][ci];
            uint8_t *b = f + 1084u + r * 16u + ci * 4u;
            b[0] = (uint8_t)((cs->smp & 0xF0u) | ((cs->per >> 8) & 0x0Fu));
            b[1] = (uint8_t)(cs->per & 0xFFu);
            b[2] = (uint8_t)(((cs->smp & 0x0Fu) << 4) | (cs->eff & 0x0Fu));
            b[3] = cs->par;
        }
    }
    for (unsigned i = 0; i < E_LEN; i++) { f[1084u + 1024u + i] = (uint8_t)(i * 3u); }
    *out = f;
    return total;
}

/* Count register writes in a trace, restricted to one tick when tick >= 0. */
static int trace_count(FILE *t, long tick, const char *reg)
{
    char line[80];
    int n = 0;

    rewind(t);
    while (fgets(line, sizeof line, t)) {
        long tk; char name[16]; unsigned v;
        if (sscanf(line, "%ld %15s %x", &tk, name, &v) != 3) { continue; }
        if (tick >= 0 && tk != tick) { continue; }
        if (strcmp(name, reg) == 0) { n++; }
    }
    return n;
}

/* Load `rows` and run `ticks` replayer ticks after mod_start's row-0 tick.
 * The card is stepped for the store charge but nothing is rendered. */
static void run_effect_mod(const cellspec rows[MOD_ROWS][MOD_CHANNELS],
                           card_t *c, mod_song *s, mod_player *p,
                           unsigned ticks, FILE *trace)
{
    uint8_t *f;
    size_t n = build_effect_mod(&f, rows);
    char namebuf[256], err[160];
    const char *path = write_tmp(f, n, namebuf, sizeof namebuf);

    card_reset(c, sram, 128u * 1024u);
    if (mod_load(s, c, path, err, sizeof err) != 0) {
        printf("FAIL: effect module did not load: %s\n", err); failures++;
        free(f); return;
    }
    memset(p, 0, sizeof *p);
    mod_set_advance(p, advance_only, c, MOD_STORE_CC_DEFAULT);
    p->trace = trace;
    mod_start(p, s, c);
    for (unsigned i = 0; i < ticks; i++) { mod_tick(p); }
    remove(path);
    free(f);
}

/* Tick numbers are 1-based and mod_start plays row 0 tick 0 as tick 1. */
#define TICK_OF(row, t) ((long)((row) * 6u + (t) + 1u))

static void test_effect_toneporta_speed(void)
{
    /* ProTracker's mt_TonePortamento takes a new speed from a non-zero
     * parameter on every tick it runs -- note or not. Modules accelerate a
     * slide with note-less 305 / 310 / 320 rows, and a player that only reads
     * the parameter on a row that carries a note slides at the first speed
     * forever. */
    static cellspec rows[MOD_ROWS][MOD_CHANNELS];
    card_t c; mod_song s; mod_player p;
    uint16_t before, after;
    unsigned guard = 0;

    memset(rows, 0, sizeof rows);
    rows[0][0].smp = 1; rows[0][0].per = 214;              /* two octaves up  */
    rows[8][0].per = 428; rows[8][0].eff = 3; rows[8][0].par = 0x01;
    for (unsigned r = 9; r < 16u; r++) { rows[r][0].eff = 3; }
    for (unsigned r = 16; r < 24u; r++) { rows[r][0].eff = 3; rows[r][0].par = 0x10; }

    run_effect_mod(rows, &c, &s, &p, 0, NULL);

    /* Rows 9..15 slide at 1 period unit a tick; row 16 changes the parameter
     * with no note in the cell. */
    while ((p.row != 16u || p.tick != 1u) && guard++ < 1000u) { mod_tick(&p); }
    check(p.row == 16u, "3xx: probe reached row 16");
    before = p.ch[0].period;
    mod_tick(&p);
    after = p.ch[0].period;
    check_eq((long)after - (long)before, 16,
             "3xx: a note-less parameter change sets the new slide speed");
    mod_free(&s);
}

static void test_effect_vibrato_row_snap(void)
{
    /* A continuing 4xy writes the BASE period at tick 0 of every row, so the
     * pitch snaps back for one tick at each row boundary. This looks like a
     * bug and is not: ProTracker's mt_CheckMoreEffects falls through to
     * mt_PerNop for every command outside {9,B,D,E,F,C}, and mt_PerNop writes
     * n_period -- which vibrato never touches, because vibrato modulates the
     * hardware register only.
     *
     * Measured, not assumed. Rendering 06_vibrato through libopenmpt's a500
     * Paula emulation and reading the fundamental back with autocorrelation
     * gives 183.5 Hz at tick 0 of rows 2, 3 and 4 -- the un-modulated base --
     * against 174.9 / 187.3 / 190.5 Hz for a player that holds the modulated
     * value. Removing this write drops the probe's spectral agreement with
     * libopenmpt from 0.996 to 0.969. It is pinned here because it is exactly
     * the kind of thing a later reader tidies away. */
    static cellspec rows[MOD_ROWS][MOD_CHANNELS];
    card_t c; mod_song s; mod_player p;

    memset(rows, 0, sizeof rows);
    rows[0][0].smp = 1; rows[0][0].per = 428;
    rows[0][0].eff = 4; rows[0][0].par = 0x48;
    for (unsigned r = 1; r < 8u; r++) { rows[r][0].eff = 4; rows[r][0].par = 0x48; }

    run_effect_mod(rows, &c, &s, &p, 5, NULL);             /* row 0, ticks 0..5 */
    check(p.ch[0].out_period != 428, "4xy: vibrato displaced the period during row 0");

    mod_tick(&p);                                          /* row 1, tick 0     */
    check_eq(p.ch[0].out_period, 428,
             "4xy: tick 0 of the next row writes the base period back (mt_PerNop)");
    mod_free(&s);
}

static void test_effect_e_commands(void)
{
    /* Three ProTracker tick-0 behaviours the E dispatcher used to drop. */
    static cellspec rows[MOD_ROWS][MOD_CHANNELS];
    card_t c; mod_song s; mod_player p;
    FILE *t = tmpfile();

    if (!t) { printf("FAIL: tmpfile() for the trace\n"); failures++; return; }

    memset(rows, 0, sizeof rows);
    rows[0][0].smp = 1; rows[0][0].per = 428;              /* plain note       */
    rows[1][0].eff = 0xE; rows[1][0].par = 0x93;           /* E9x, no note     */
    rows[2][0].eff = 0xE; rows[2][0].par = 0xC0;           /* EC0, cut at t=0  */

    run_effect_mod(rows, &c, &s, &p, 18, t);

    check_eq(trace_count(t, 1, "ADMACON"), 2,
             "trace: row 0's DMACON stop/start pair is at tick 1");
    check_eq(trace_count(t, TICK_OF(1, 0), "ADMACON"), 2,
             "E9x: retriggers at tick 0 of a row that carries no note");
    {
        /* EC0 at tick 0: e_per_tick never sees tick 0, so without the tick-0
         * case the cut simply never happens. */
        int found = 0;
        char line[80];
        rewind(t);
        while (fgets(line, sizeof line, t)) {
            long tk; char name[16]; unsigned v;
            if (sscanf(line, "%ld %15s %x", &tk, name, &v) != 3) { continue; }
            if (tk == TICK_OF(2, 0) && strcmp(name, "ADATA") == 0 && v == 0) { found = 1; }
        }
        check(found, "EC0: cuts the volume at tick 0, not never");
    }
    fclose(t);
    mod_free(&s);
}

static void test_effect_note_delay_repeat(void)
{
    /* modplayer.md §10.10: EDx x EEx -- the delayed note triggers once per
     * REPEAT of the row, not once per row. The repeat never re-reads the row,
     * so the delay has to be re-armed from what the row left behind. */
    static cellspec rows[MOD_ROWS][MOD_CHANNELS];
    card_t c; mod_song s; mod_player p;
    FILE *t = tmpfile();

    if (!t) { printf("FAIL: tmpfile() for the trace\n"); failures++; return; }

    memset(rows, 0, sizeof rows);
    rows[0][0].smp = 1; rows[0][0].per = 428;
    rows[0][0].eff = 0xE; rows[0][0].par = 0xD3;           /* delay 3 ticks    */
    rows[0][1].eff = 0xE; rows[0][1].par = 0xE1;           /* repeat the row 1x */

    run_effect_mod(rows, &c, &s, &p, 18, t);

    check_eq(trace_count(t, TICK_OF(0, 3), "ADMACON"), 2,
             "EDx: the delayed note triggers on tick 3 of the row");
    check_eq(trace_count(t, TICK_OF(1, 3), "ADMACON"), 2,
             "EDx x EEx: and again on tick 3 of the pattern-delay repeat");
    fclose(t);
    mod_free(&s);
}

static void test_effect_offset(void)
{
    /* 9xx: ProTracker's mt_SampleOffset takes the parameter into memory
     * whenever the command is seen, and an E9x retrigger restarts from the
     * offset start it left in n_start -- not from the sample's base address. */
    static cellspec rows[MOD_ROWS][MOD_CHANNELS];
    card_t c; mod_song s; mod_player p;

    memset(rows, 0, sizeof rows);
    rows[0][0].eff = 9; rows[0][0].par = 0x01;             /* seen, no note    */
    rows[1][0].smp = 1; rows[1][0].per = 428; rows[1][0].eff = 9;  /* param 0  */
    rows[2][0].eff = 0xE; rows[2][0].par = 0x93;           /* E9x retrigger    */

    run_effect_mod(rows, &c, &s, &p, 0, NULL);
    check_eq(p.ch[0].offset_mem, 0x01,
             "9xx: the parameter enters memory on a row with no note");

    for (unsigned i = 0; i < 6u; i++) { mod_tick(&p); }    /* into row 1        */
    check_eq((long)p.ch[0].start_lc, (long)s.sample_addr[1] + 256,
             "9xx: a zero parameter replays the remembered offset");
    check_eq(p.ch[0].start_len, (E_LEN - 256u) / 2u, "9xx: and shortens the length");

    for (unsigned i = 0; i < 6u; i++) { mod_tick(&p); }    /* into row 2        */
    check_eq((long)p.ch[0].trig_lc, (long)s.sample_addr[1] + 256,
             "E9x: the retrigger keeps the 9xx offset");
    mod_free(&s);
}

static void test_effect_loop_and_break(void)
{
    /* modplayer.md §5.8: an E6x loop-back wins the row. A Dxx sharing that row
     * has already been read, so it must not survive to fire one row AFTER the
     * loop -- a teleport ProTracker does not do. */
    static cellspec rows[MOD_ROWS][MOD_CHANNELS];
    card_t c; mod_song s; mod_player p;
    uint8_t seen_row[8], seen_pos[8];
    unsigned k = 0;

    memset(rows, 0, sizeof rows);
    rows[0][0].eff = 0xE; rows[0][0].par = 0x60;           /* loop point       */
    rows[2][0].eff = 0xE; rows[2][0].par = 0x61;           /* loop once        */
    rows[2][1].eff = 0xD; rows[2][1].par = 0x20;           /* break to row 20  */

    run_effect_mod(rows, &c, &s, &p, 0, NULL);
    seen_row[k] = p.row; seen_pos[k] = p.position; k++;
    while (k < 6u) {
        mod_tick(&p);
        if (p.tick == 0u && (p.row != seen_row[k - 1] || p.position != seen_pos[k - 1])) {
            seen_row[k] = p.row; seen_pos[k] = p.position; k++;
        }
    }
    check_eq(seen_row[1], 1, "E6x: row 1 follows row 0");
    check_eq(seen_row[2], 2, "E6x: row 2 follows row 1");
    check_eq(seen_row[3], 0, "E6x: the loop wins the row it shares with Dxx");
    check_eq(seen_row[4], 1, "E6x: and the Dxx does not fire a row later");
    check_eq(seen_pos[4], 0, "E6x: nor does it advance the position");
    mod_free(&s);
}

int main(void)
{
    sram = calloc(CARD_SRAM_BYTES, 1);
    if (!sram) { return 1; }

    test_period_table();
    test_volume_lut();
    test_period_is_the_colour_clock();
    test_shadow_reload();
    test_tempo();
    test_loader_and_playback();
    test_loader_rejects();
    test_loader_capacity();
    test_loader_15_sample();
    test_filters();
    test_effect_toneporta_speed();
    test_effect_vibrato_row_snap();
    test_effect_e_commands();
    test_effect_note_delay_repeat();
    test_effect_offset();
    test_effect_loop_and_break();

    free(sram);
    if (failures) { printf("%d failure(s)\n", failures); return 1; }
    printf("all reference-player checks passed\n");
    return 0;
}
