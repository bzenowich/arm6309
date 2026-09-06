/* Analogue model and WAV output — audio/docs/audio.md §6.2, §7.
 *
 * The card presents a continuous-time signal: each channel is a zero-order hold at
 * its own rate, driving its own converter, and the four are summed in the analogue
 * domain with no output sample rate anywhere (audio/docs/audio.md §6.2). Writing a
 * 48 kHz file therefore needs a decimation stage that the hardware does not have, and
 * it is important to keep the two apart. Everything down to and including the filters is a model of the CARD.
 * The anti-alias stage below it is a RENDERING artefact and would not exist in
 * a listener's ears.
 *
 * Chain:
 *
 *   colour clock  ---> exact area integration ---> 8 x Fout
 *   (3.546895 MHz)     (loses nothing: the input is piecewise constant)
 *                                |
 *                     fixed 4.4 kHz 1-pole RC  (A500, always in)   <- CARD
 *                     + 2-pole 3275 Hz LED filter, if enabled      <- CARD
 *                                |
 *                     4th-order Butterworth at 0.45 Fout           <- RENDER
 *                                |
 *                          decimate 8:1 ---> Fout
 *
 * Running the filters at 8 x Fout rather than at the colour clock costs nothing
 * in accuracy — the area integration is exact and the highest pole in the card
 * model is 4.4 kHz — and it is ~9x less arithmetic.
 */
#ifndef ARM6309_RENDER_H
#define ARM6309_RENDER_H

#include <stdio.h>
#include <stdint.h>

#define RENDER_OVERSAMPLE 8

typedef struct { double b0, b1, b2, a1, a2, z1, z2; } biquad;

typedef struct {
    long   cc_rate;          /* card colour clock                          */
    int    out_rate;
    double step;             /* colour clocks per intermediate sample      */
    double acc_l, acc_r, acc_n;

    double rc_l, rc_r, rc_k;         /* fixed 4.4 kHz pole                 */
    biquad led_l, led_r;             /* LED filter, one Sallen-Key stage   */
    biquad aa_l[2], aa_r[2];         /* rendering anti-alias               */

    int    phase;                    /* 0..RENDER_OVERSAMPLE-1             */
    int    led_on, bypass;

    FILE  *wav;
    uint32_t frames;
    double peak;
    uint32_t clipped;
    int      write_failed;
    double   last_l, last_r;   /* most recent emitted frame, for tests */
} render_t;

int  render_open(render_t *r, const char *path, int out_rate, long cc_rate);
void render_set_filter(render_t *r, int led_on, int bypass);
/* One colour clock of card output. Emits a WAV frame when one is due. */
void render_push(render_t *r, int l, int r_in);
int  render_close(render_t *r);

#endif /* ARM6309_RENDER_H */
