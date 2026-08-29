/* arm6309 reference module player — docs/modplayer.md §8 build step 0.
 *
 * "Without a reference implementation there is nothing to A/B against, and
 *  'it sounds about right' is not an acceptance test for a system whose entire
 *  premise is bit-exact compatibility."
 *
 * Two outputs, and the second one is the important one:
 *
 *   --wav    a stereo file, for listening and for A/B against an Amiga emulator
 *   --trace  the register-write stream, timestamped by tick
 *
 * The trace is what the 6309 replayer gets diffed against. Comparing audio
 * tells you something is wrong; comparing traces tells you which register
 * write, on which tick, in which channel.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "mod.h"
#include "render.h"

/* Advancing the card from inside the replayer keeps the audio continuous while
 * the CPU is busy, and — the reason it exists — makes the enable latch of
 * docs/audio.md §16 item 13 race the loop-pointer write the way it does on real
 * hardware, instead of the replayer completing in zero time. */
typedef struct { card_t *card; render_t *render; } tick_ctx;

static void advance_cb(void *vp, unsigned cc)
{
    tick_ctx *t = vp;
    for (unsigned i = 0; i < cc; i++) {
        int l, r;
        card_step(t->card);
        card_dac(t->card, &l, &r);
        render_push(t->render, l, r);
    }
}

static void usage(void)
{
    fprintf(stderr,
      "usage: refplayer [options] file.mod\n"
      "  --wav FILE        write stereo PCM (default: none)\n"
      "  --trace FILE      write the register-write trace ('-' for stdout)\n"
      "  --rate HZ         output sample rate (default 48000)\n"
      "  --seconds N       stop after N seconds (default: one pass of the song)\n"
      "  --ntsc            use the 3.579545 MHz colour clock (audio.md §4.1)\n"
      "  --led             start with the LED filter on (audio.md §7)\n"
      "  --bypass          bypass all filtering -- WRONG for modules, see §7\n"
      "  --ram KB          populated sample RAM (default 128, max 512)\n"
      "  --info            print the parsed module and exit\n");
}

int main(int argc, char **argv)
{
    const char *path = NULL, *wavpath = NULL, *tracepath = NULL;
    int rate = 48000, ntsc = 0, led = 0, bypass = 0, info_only = 0;
    double seconds = 0.0;
    unsigned long ramkb = 128;

    card_t card;
    mod_song song;
    mod_player player;
    render_t render;
    uint8_t *sram = NULL;
    char err[160] = { 0 };
    long cc;
    uint64_t cc_limit = 0;
    int rc = 1;

    for (int i = 1; i < argc; i++) {
        const char *a = argv[i];
        if      (!strcmp(a, "--wav")     && i + 1 < argc) { wavpath = argv[++i]; }
        else if (!strcmp(a, "--trace")   && i + 1 < argc) { tracepath = argv[++i]; }
        else if (!strcmp(a, "--rate")    && i + 1 < argc) { rate = atoi(argv[++i]); }
        else if (!strcmp(a, "--seconds") && i + 1 < argc) { seconds = atof(argv[++i]); }
        else if (!strcmp(a, "--ram")     && i + 1 < argc) { ramkb = strtoul(argv[++i], NULL, 10); }
        else if (!strcmp(a, "--ntsc"))   { ntsc = 1; }
        else if (!strcmp(a, "--led"))    { led = 1; }
        else if (!strcmp(a, "--bypass")) { bypass = 1; }
        else if (!strcmp(a, "--info"))   { info_only = 1; }
        else if (a[0] == '-' && a[1])    { usage(); return 2; }
        else                             { path = a; }
    }
    if (!path || rate < 8000 || rate > 192000) { usage(); return 2; }
    if (ramkb == 0 || ramkb > 512) {
        fprintf(stderr, "refplayer: --ram must be 1..512 (audio.md §5)\n");
        return 2;
    }

    sram = calloc(CARD_SRAM_BYTES, 1);
    if (!sram) { fprintf(stderr, "refplayer: out of memory\n"); return 1; }

    card_reset(&card, sram, (uint32_t)(ramkb * 1024u));
    if (ntsc) { card_write(&card, A_ACTRL, ACTRL_NTSC); }
    cc = card_colour_clock(&card);

    if (mod_load(&song, &card, path, err, sizeof err) != 0) {
        fprintf(stderr, "refplayer: %s: %s\n", path, err);
        goto out;
    }

    printf("%-14s %s\n", "title:", song.title);
    printf("%-14s %u positions, %u patterns\n", "song:", song.songlength, song.npatterns);
    printf("%-14s %lu bytes of %lu KB card RAM%s\n", "samples:",
           (unsigned long)song.sample_bytes, ramkb,
           song.truncated ? "  (file was truncated; clamped, §4.6)" : "");
    printf("%-14s %ld Hz (%s)\n", "colour clock:", cc, ntsc ? "NTSC" : "PAL");
    if (!mod_period_table_is_authoritative()) {
        printf("%-14s period table rows 1-15 are COMPUTED, not the ProTracker\n"
               "%-14s table. Finetune and 3xx results are provisional --\n"
               "%-14s docs/modplayer.md §11 item 4.\n", "warning:", "", "");
    }
    if (info_only) { rc = 0; goto out_song; }

    if (render_open(&render, wavpath, rate, cc) != 0) {
        fprintf(stderr, "refplayer: cannot write %s\n", wavpath ? wavpath : "(none)");
        goto out_song;
    }
    render_set_filter(&render, led, bypass);

    {
        static tick_ctx tc;
        tc.card = &card; tc.render = &render;
        mod_set_advance(&player, advance_cb, &tc, MOD_STORE_CC_DEFAULT);
    }
    mod_start(&player, &song, &card);
    if (led)    { card_write(&card, A_ACTRL, (uint8_t)(ACTRL_ENABLE | ACTRL_LED | (ntsc ? ACTRL_NTSC : 0))); }
    if (bypass) { card_write(&card, A_ACTRL, (uint8_t)(ACTRL_ENABLE | ACTRL_BYPASS | (ntsc ? ACTRL_NTSC : 0))); }

    if (tracepath) {
        player.trace = strcmp(tracepath, "-") ? fopen(tracepath, "w") : stdout;
        if (!player.trace) {
            fprintf(stderr, "refplayer: cannot write %s\n", tracepath);
            goto out_render;
        }
    }

    if (seconds > 0.0) { cc_limit = (uint64_t)(seconds * (double)cc); }

    /* The main loop is the machine: step the card one colour clock at a time
     * and service /FIRQ when it asserts, exactly as the 6309 will. Nothing here
     * knows what a "sample rate" is -- that lives in render.c, on the other
     * side of the card's analogue output. */
    for (;;) {
        int l, r;

        if (card_firq(&card)) { mod_tick(&player); }

        card_step(&card);
        card_dac(&card, &l, &r);
        render_push(&render, l, r);

        /* Track the filter setting the module itself may have changed via E0x. */
        render_set_filter(&render,
                          (card.ctrl & ACTRL_LED) != 0,
                          (card.ctrl & ACTRL_BYPASS) != 0);

        if (cc_limit) {
            if (card.cc >= cc_limit) { break; }
        } else if (player.ended) {
            break;
        }
    }

    printf("%-14s %lu ticks, %.1f s, %u frames at %d Hz\n", "played:",
           (unsigned long)player.ticks, (double)card.cc / (double)cc,
           render.frames, rate);
    printf("%-14s %.1f %% of full scale%s\n", "peak:",
           100.0 * render.peak / 32768.0,
           render.clipped ? "  *** CLIPPED ***" : "");

    /* A non-zero count here means the loader relocated something wrongly and
     * the card fetched from unwritten RAM -- docs/modplayer.md §4.6. It is
     * always a bug, never a tolerance. */
    if (card.oob_reads) {
        printf("%-14s %lu sample fetches past populated RAM -- LOADER BUG\n",
               "ERROR:", (unsigned long)card.oob_reads);
        rc = 1;
    } else {
        rc = 0;
    }

    if (player.trace && player.trace != stdout) { fclose(player.trace); }

out_render:
    if (render_close(&render) != 0) {
        fprintf(stderr, "refplayer: error writing %s\n", wavpath ? wavpath : "wav");
        rc = 1;
    }
out_song:
    mod_free(&song);
out:
    free(sram);
    return rc;
}
