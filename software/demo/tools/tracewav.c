/* tracewav - what audio/refplayer's card model makes of a TIMED register stream.
 *
 *   tracewav out.wav song.mod card.times
 *
 * card.times is demo_tb.sv's: one line per write the 6809 made to the card
 * after the loader, "colour-clock register byte", timed where the write
 * reached the backplane. This loads the module's samples exactly as refplayer
 * does (mod_load.c, whose sample RAM the 6809 loader reproduces byte for byte),
 * then steps card.c one colour clock at a time and applies each write on its
 * colour clock, through render.c - the analogue chain dacwav uses.
 *
 * ⭐ WHY IT EXISTS. check:modplay's gate says "a card that scores worse than
 * refplayer is hardware", and that is right when both are given the register
 * stream at refplayer's timing. In the demo the 6809 makes the writes, a row
 * tick takes it up to ~4 ms, and every note starts that much later than
 * refplayer's. So the fair control for the RTL card in that run is card.c fed
 * THE SAME WRITES AT THE SAME INSTANTS. Both renders then share one time base,
 * sample for sample, and what differs between them is the card.
 *
 * ⚠ IT LINKS card.c, which dacwav deliberately does not. That is the point: this
 * is the control, not the thing under test.
 */
#include <stdio.h>
#include <stdlib.h>
#include "mod.h"
#include "render.h"

int main(int argc, char **argv)
{
    static uint8_t sram[CARD_SRAM_BYTES];
    card_t card;
    mod_song song;
    render_t r;
    char err[200];
    long long next_cc = -1, cc = 0, writes = 0;
    unsigned reg = 0, val = 0;
    FILE *f;

    if (argc != 4) {
        fprintf(stderr, "usage: tracewav out.wav song.mod card.times\n");
        return 2;
    }
    card_reset(&card, sram, CARD_SRAM_BYTES);
    if (mod_load(&song, &card, argv[2], err, sizeof err) != 0) {
        fprintf(stderr, "tracewav: %s: %s\n", argv[2], err);
        return 1;
    }
    f = fopen(argv[3], "r");
    if (!f) { fprintf(stderr, "tracewav: cannot read %s\n", argv[3]); return 1; }
    if (render_open(&r, argv[1], 48000, card_colour_clock(&card)) != 0) {
        fprintf(stderr, "tracewav: cannot write %s\n", argv[1]);
        return 1;
    }
    render_set_filter(&r, 0, 0);

    if (fscanf(f, "%lld %x %x", &next_cc, &reg, &val) != 3) next_cc = -1;
    while (next_cc >= 0 || cc == 0) {
        while (next_cc >= 0 && next_cc <= cc) {
            card_write(&card, (uint8_t)reg, (uint8_t)val);
            writes++;
            if (fscanf(f, "%lld %x %x", &next_cc, &reg, &val) != 3) next_cc = -1;
        }
        if (next_cc < 0) break;
        {
            int l, rr;
            card_step(&card);
            card_dac(&card, &l, &rr);
            render_push(&r, l, rr);
        }
        cc++;
    }
    /* and a second of tail, so the last notes ring out as dacwav's do */
    for (long k = 0; k < card_colour_clock(&card); k++) {
        int l, rr;
        card_step(&card);
        card_dac(&card, &l, &rr);
        render_push(&r, l, rr);
    }
    fclose(f);
    render_close(&r);
    printf("tracewav: %lld writes over %lld colour clocks\n", writes, cc);
    mod_free(&song);
    return 0;
}
