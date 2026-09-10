/* dacwav — turn the RTL card's converter log into a WAV.
 *
 *   dacwav out.wav card.dac [--rate 48000] [--cc 3546895] [--led] [--bypass]
 *
 * WHAT THIS IS, AND WHAT IT IS NOT.
 *
 * hardware/gal/verilog/modplay_tb.sv plays a module on audio_card.v - the real
 * design, U1 and U2 generated from the term lists the fitter compiles - and
 * records the four sample codes and four volume codes the AD7528 pairs are
 * given, one row per change. That log is the card's DIGITAL output and it is
 * complete: the converters hold their codes between rows, which is not a
 * compression of the signal, it IS the signal (audio.md §6.2).
 *
 * ⚠ EVERYTHING BELOW THE CONVERTERS HAS NO RTL AND CANNOT HAVE ANY. The
 * multiply is analogue - the sample byte drives one AD7528 half whose output is
 * the REFERENCE of the second, whose code is the volume (§6.1) - and the two
 * channels of a side meet at one I/V amplifier's virtual ground (§6.2). So the
 * arithmetic here is two multiplies and two adds, and the filters after it are
 * audio/refplayer/render.c, which is a model of the card's ANALOGUE chain.
 *
 * ⛔ IT IS NOT audio/refplayer/card.c. Nothing in this tool models the state
 * file, the pointer, the counter, the period compare, the DMA, the interrupt
 * block or the host port; all of those are the RTL's, and the whole point of
 * the exercise is that they are. render.c is linked, card.c is not, and the
 * link line in CMakeLists.txt is the enforcement.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "render.h"

int main(int argc, char **argv)
{
    const char *wav = NULL, *dac = NULL;
    int rate = 48000, led = 0, bypass = 0;
    long cc_rate = 3546895L;                 /* PAL colour clock, audio.md §4.1 */
    render_t r;
    FILE *f;
    long long cc = 0, prev_cc = 0, rows = 0;
    int s[4] = { 128, 128, 128, 128 }, v[4] = { 0, 0, 0, 0 };
    int ns[4], nv[4];
    long long emitted = 0;

    for (int i = 1; i < argc; i++) {
        const char *a = argv[i];
        if      (!strcmp(a, "--rate") && i + 1 < argc) rate = atoi(argv[++i]);
        else if (!strcmp(a, "--cc")   && i + 1 < argc) cc_rate = strtol(argv[++i], NULL, 10);
        else if (!strcmp(a, "--led"))    led = 1;
        else if (!strcmp(a, "--bypass")) bypass = 1;
        else if (!wav) wav = a;
        else if (!dac) dac = a;
    }
    if (!wav || !dac) {
        fprintf(stderr, "usage: dacwav out.wav card.dac [--rate HZ] [--cc HZ] [--led] [--bypass]\n");
        return 2;
    }

    f = fopen(dac, "r");
    if (!f) { fprintf(stderr, "dacwav: cannot read %s\n", dac); return 1; }
    if (render_open(&r, wav, rate, cc_rate) != 0) {
        fprintf(stderr, "dacwav: cannot write %s\n", wav);
        return 1;
    }
    render_set_filter(&r, led, bypass);

    /* The hold. Each row says "from this colour clock on, the converters carry
     * these codes"; the gap to the next row is how long they carry them. */
    while (fscanf(f, "%lld %d %d %d %d %d %d %d %d", &cc,
                  &ns[0], &ns[1], &ns[2], &ns[3],
                  &nv[0], &nv[1], &nv[2], &nv[3]) == 9) {
        long long n = cc - prev_cc;
        for (long long k = 0; k < n; k++) {
            /* §6.1: the sample converter is unsigned-coded and its half-scale
             * pedestal is cancelled at its own I/V node, before the volume
             * stage — which is why VOL = 0 is exact silence with no DC step. */
            int l = (s[0] - 128) * v[0] + (s[3] - 128) * v[3];
            int rr = (s[1] - 128) * v[1] + (s[2] - 128) * v[2];
            render_push(&r, l, rr);
            emitted++;
        }
        memcpy(s, ns, sizeof s);
        memcpy(v, nv, sizeof v);
        prev_cc = cc;
        rows++;
    }
    fclose(f);

    if (render_close(&r) != 0) { fprintf(stderr, "dacwav: write failed\n"); return 1; }
    printf("dacwav: %lld rows, %lld colour clocks, %u frames at %d Hz, peak %.1f%%\n",
           rows, emitted, r.frames, rate, 100.0 * r.peak / 32768.0);
    return 0;
}
