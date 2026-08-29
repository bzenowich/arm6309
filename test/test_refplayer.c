/* Tests for the reference module player — tools/refplayer/.
 *
 * These check the things docs/modplayer.md §9 says a test corpus must check,
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

static const char *write_tmp(const uint8_t *f, size_t n, char *buf, size_t buflen)
{
    FILE *fp;
    snprintf(buf, buflen, "reftest_%u.mod", (unsigned)n);
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

    /* docs/audio.md §6.1: entry = SAMP * min(VOL,64) / 4, 12-bit signed. */
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
     * This is docs/audio.md §4.1 and §4.2 -- if it is wrong, every module is
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
    /* docs/audio.md §3.3 / modplayer.md §5.3: the card must reload from LC/LEN
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
    /* docs/audio.md §8.2. The clock is colourclock/5 and the reload is
     * 1773447/BPM. Confusing the two detunes every tempo by exactly 2.5x, which
     * is what the first draft of that section did. */
    card_t c;
    uint16_t n = (uint16_t)(1773447L / 125L);
    unsigned fires = 0;

    card_reset(&c, sram, 128u * 1024u);
    card_write(&c, A_TIMER1, (uint8_t)(n >> 8));
    card_write(&c, A_TIMER0, (uint8_t)(n & 0xFFu));
    card_write(&c, A_AINTENA, (uint8_t)(0x80u | AINT_TIMER));

    for (long i = 0; i < CARD_CC_PAL; i++) {         /* one second */
        card_step(&c);
        if (c.intreq & AINT_TIMER) { fires++; card_write(&c, A_AINTREQ, AINT_TIMER); }
    }
    check_eq(n, 14187, "tempo: BPM 125 reload is 14187");
    check(fires == 50u, "tempo: BPM 125 fires 50 times a second");
}

static void test_loader_and_playback(void)
{
    card_t c;
    mod_song s;
    mod_player p;
    uint8_t *f;
    size_t n = build_mod(&f, 428, 0, 0);
    char namebuf[64];
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
    char namebuf[64], err[128];
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
    /* docs/audio.md §7. Two things must hold, and only the first is a matter of
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
    /* Five poles must fall far faster than one. */
    {
        double b8 = filter_rms(8000, 0, 1), l8 = filter_rms(8000, 1, 0);
        check(20.0 * log10(l8 / b8) < -25.0, "filter: LED is 5 poles, not 1");
    }
}

static void test_period_table(void)
{
    /* docs/modplayer.md §5.4 / §11 item 4. The table is copied, not computed,
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
    test_filters();

    free(sram);
    if (failures) { printf("%d failure(s)\n", failures); return 1; }
    printf("all reference-player checks passed\n");
    return 0;
}
