#include <math.h>
#include <string.h>
#include <stdlib.h>
#include "render.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* ------------------------------------------------------------- biquads ---- */

static void bq_lowpass(biquad *b, double fc, double fs, double q)
{
    double w0 = 2.0 * M_PI * fc / fs;
    double c = cos(w0), s = sin(w0);
    double alpha = s / (2.0 * q);
    double a0 = 1.0 + alpha;

    b->b0 = ((1.0 - c) / 2.0) / a0;
    b->b1 = (1.0 - c) / a0;
    b->b2 = b->b0;
    b->a1 = (-2.0 * c) / a0;
    b->a2 = (1.0 - alpha) / a0;
    b->z1 = b->z2 = 0.0;
}

static double bq(biquad *b, double x)
{
    double y = b->b0 * x + b->z1;
    b->z1 = b->b1 * x - b->a1 * y + b->z2;
    b->z2 = b->b2 * x - b->a2 * y;
    return y;
}

/* ---------------------------------------------------------------- setup --- */

int render_open(render_t *r, const char *path, int out_rate, long cc_rate)
{
    double fs = (double)out_rate * RENDER_OVERSAMPLE;
    static const uint8_t hdr[44] = { 0 };

    memset(r, 0, sizeof *r);
    r->out_rate = out_rate;
    r->cc_rate  = cc_rate;
    r->step     = (double)cc_rate / fs;

    /* A500 fixed pole: 360 ohm + 0.1 uF = 4421 Hz, one pole, 6 dB/oct. This is
     * not nostalgia — it is the reconstruction filter for channels running at
     * 8-16 kHz, where the ZOH images sit on top of the audio band
     * (audio/docs/audio.md §7). */
    r->rc_k = 1.0 - exp(-2.0 * M_PI * 4421.0 / fs);

    /* The switchable "LED" filter: ONE Sallen-Key stage at 3275 Hz, on top of
     * the fixed pole — two poles switched in, three in the chain.
     *
     * The A500 has a single 2nd-order Sallen-Key section here, so the stage is
     * a 2nd-order Butterworth (Q = 1/sqrt2) and nothing else. Cascading two of
     * them made LED-on material ~24 dB/oct darker than the machine being
     * modelled, which no amount of corner-frequency tuning can compensate.
     *
     * This is still a MODEL. The component-derived response of a real A500
     * should be measured before any A/B verdict rests on the LED setting. */
    bq_lowpass(&r->led_l, 3275.0, fs, 0.7071067811865476);
    bq_lowpass(&r->led_r, 3275.0, fs, 0.7071067811865476);

    /* RENDERING ONLY — not part of the card. Without it, content between
     * 0.5 Fout and Fout folds back into the file. */
    for (int i = 0; i < 2; i++) {
        double q = (i == 0) ? 0.541 : 1.307;
        bq_lowpass(&r->aa_l[i], 0.45 * out_rate, fs, q);
        bq_lowpass(&r->aa_r[i], 0.45 * out_rate, fs, q);
    }

    if (!path) { return 0; }
    r->wav = fopen(path, "wb");
    if (!r->wav) { return -1; }
    if (fwrite(hdr, 1, sizeof hdr, r->wav) != sizeof hdr) { return -1; }
    return 0;
}

void render_set_filter(render_t *r, int led_on, int bypass)
{
    r->led_on = led_on;
    r->bypass = bypass;
}

/* ------------------------------------------------------------- the chain -- */

static void emit(render_t *r, double l, double u)
{
    if (!r->bypass) {
        r->rc_l += (l - r->rc_l) * r->rc_k;
        r->rc_r += (u - r->rc_r) * r->rc_k;
        l = r->rc_l;
        u = r->rc_r;
        if (r->led_on) {
            l = bq(&r->led_l, l);
            u = bq(&r->led_r, u);
        }
    }

    l = bq(&r->aa_l[1], bq(&r->aa_l[0], l));
    u = bq(&r->aa_r[1], bq(&r->aa_r[0], u));

    if (++r->phase < RENDER_OVERSAMPLE) { return; }
    r->phase = 0;

    /* The DAC codes are 12-bit signed; scale to 16-bit for the file. */
    {
        double sl = l * 16.0, sr = u * 16.0;
        r->last_l = sl; r->last_r = sr;
        int il, ir;
        double m = fabs(sl) > fabs(sr) ? fabs(sl) : fabs(sr);
        if (m > r->peak) { r->peak = m; }
        il = (int)lrint(sl); ir = (int)lrint(sr);
        if (il > 32767) { il = 32767; r->clipped++; }
        if (il < -32768) { il = -32768; r->clipped++; }
        if (ir > 32767) { ir = 32767; r->clipped++; }
        if (ir < -32768) { ir = -32768; r->clipped++; }
        if (r->wav) {
            uint8_t f[4] = { (uint8_t)(il & 0xFF), (uint8_t)((il >> 8) & 0xFF),
                             (uint8_t)(ir & 0xFF), (uint8_t)((ir >> 8) & 0xFF) };
            if (fwrite(f, 1, 4, r->wav) != 4) { r->write_failed = 1; }
        }
        r->frames++;
    }
}

void render_push(render_t *r, int l, int r_in)
{
    /* Exact area integration from the colour clock to the intermediate rate.
     * The input is piecewise constant between colour clocks, so accumulating
     * whole and fractional colour clocks loses nothing below Nyquist. */
    r->acc_l += l;
    r->acc_r += r_in;
    r->acc_n += 1.0;

    while (r->acc_n >= r->step) {
        double n = r->acc_n;
        emit(r, r->acc_l / n, r->acc_r / n);
        /* Carry the remainder forward as a fractional colour clock of the value
         * currently held, so no area is lost or double-counted at the boundary. */
        r->acc_n = n - r->step;
        r->acc_l = (double)l * r->acc_n;
        r->acc_r = (double)r_in * r->acc_n;
    }
}

int render_close(render_t *r)
{
    uint8_t h[44];
    uint32_t data = r->frames * 4u;
    uint32_t riff = 36u + data;
    uint32_t rate = (uint32_t)r->out_rate;
    uint32_t byterate = rate * 4u;

    if (!r->wav) { return 0; }
    if (r->write_failed) { fclose(r->wav); r->wav = NULL; return -1; }

    memcpy(h, "RIFF", 4);
    h[4] = (uint8_t)(riff & 0xFF); h[5] = (uint8_t)((riff >> 8) & 0xFF);
    h[6] = (uint8_t)((riff >> 16) & 0xFF); h[7] = (uint8_t)((riff >> 24) & 0xFF);
    memcpy(h + 8, "WAVEfmt ", 8);
    h[16] = 16; h[17] = h[18] = h[19] = 0;
    h[20] = 1; h[21] = 0;                        /* PCM        */
    h[22] = 2; h[23] = 0;                        /* stereo     */
    h[24] = (uint8_t)(rate & 0xFF); h[25] = (uint8_t)((rate >> 8) & 0xFF);
    h[26] = (uint8_t)((rate >> 16) & 0xFF); h[27] = (uint8_t)((rate >> 24) & 0xFF);
    h[28] = (uint8_t)(byterate & 0xFF); h[29] = (uint8_t)((byterate >> 8) & 0xFF);
    h[30] = (uint8_t)((byterate >> 16) & 0xFF); h[31] = (uint8_t)((byterate >> 24) & 0xFF);
    h[32] = 4; h[33] = 0;                        /* block align */
    h[34] = 16; h[35] = 0;                       /* bits        */
    memcpy(h + 36, "data", 4);
    h[40] = (uint8_t)(data & 0xFF); h[41] = (uint8_t)((data >> 8) & 0xFF);
    h[42] = (uint8_t)((data >> 16) & 0xFF); h[43] = (uint8_t)((data >> 24) & 0xFF);

    if (fseek(r->wav, 0, SEEK_SET) != 0) { fclose(r->wav); r->wav = NULL; return -1; }
    if (fwrite(h, 1, sizeof h, r->wav) != sizeof h) { fclose(r->wav); r->wav = NULL; return -1; }
    if (fclose(r->wav) != 0) { r->wav = NULL; return -1; }
    r->wav = NULL;
    return 0;
}
