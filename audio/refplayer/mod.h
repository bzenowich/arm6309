/* The song image, loader and replayer — audio/docs/modplayer.md.
 *
 * The split is the one that document argues for in §1: the loader runs once and
 * may do anything, the replayer runs from /FIRQ 50-102 times a second and may
 * do nothing but write card registers. They share exactly the song image below.
 *
 * mod_replay.c is written to be transliterated into 6309 assembly. It touches
 * the card only through card_write(), it allocates nothing, and it has no loop
 * whose bound is not obvious. Where a C idiom would be cheaper than what the
 * 6309 will do, the C follows the 6309.
 */
#ifndef ARM6309_MOD_H
#define ARM6309_MOD_H

#include <stdint.h>
#include <stdio.h>
#include "card.h"

#define MOD_MAX_SAMPLES  32     /* 1..31 used; entry 0 is the null sample   */
#define MOD_MAX_PATTERNS 128
#define MOD_ROWS         64
#define MOD_CHANNELS     4

/* Card RAM map, audio/docs/modplayer.md §4.2. The two zero bytes at 0 are the
 * null-loop target — the mechanism by which non-looping samples stop. */
#define MOD_NULL_LOOP    0x00000u
#define MOD_SAMPLE_BASE  0x00002u

typedef struct {
    char     title[21];
    uint8_t  order[128];
    uint8_t  songlength;
    uint8_t  npatterns;
    uint8_t *patterns;                  /* npatterns * 1024 bytes           */

    /* 32 entries so the pattern's sample number indexes directly, with entry 0
     * the null sample — audio/docs/modplayer.md §3. */
    uint32_t sample_addr[MOD_MAX_SAMPLES];    /* card-RAM byte address      */
    uint16_t sample_len[MOD_MAX_SAMPLES];     /* WORDS, verbatim            */
    uint32_t sample_rep[MOD_MAX_SAMPLES];     /* card-RAM byte address      */
    uint16_t sample_replen[MOD_MAX_SAMPLES];  /* WORDS, verbatim            */
    uint8_t  sample_vol[MOD_MAX_SAMPLES];     /* verbatim                   */
    uint8_t  sample_ft[MOD_MAX_SAMPLES];      /* table row 0..15, verbatim  */

    uint32_t sample_bytes;              /* total uploaded                   */
    int      truncated;                 /* file was short; §4.6             */
} mod_song;

/* ------------------------------------------------------------- loader ----- */

/* Parses, validates and uploads sample data into the card through SPTR/SDATA.
 * Returns 0 on success. On failure returns non-zero and writes a one-line
 * reason to `err` (audio/docs/modplayer.md §4.6 — reject loudly). */
int  mod_load(mod_song *s, card_t *c, const char *path, char *err, size_t errlen);
void mod_free(mod_song *s);

/* --------------------------------------------------------- replayer ------- */

typedef struct {
    uint8_t  sample;
    uint16_t period;          /* the note's period, before vibrato/arpeggio */
    uint16_t out_period;      /* what was last written to PER               */
    uint16_t target_period;   /* 3xx destination                            */
    uint8_t  volume;          /* 0..64                                      */
    uint8_t  out_volume;      /* what was last written to VOL               */
    uint8_t  finetune;

    uint8_t  cmd, param;      /* this row's effect                          */
    uint8_t  porta_speed;
    uint8_t  vib_cmd, vib_pos;
    uint8_t  trem_cmd, trem_pos;
    uint8_t  wave_ctrl;       /* low nibble vibrato, high nibble tremolo    */
    uint8_t  offset_mem;
    uint8_t  loop_row, loop_cnt;
    uint8_t  glissando;

    /* Where this channel's note actually starts, 9xx offset already applied.
     * ProTracker keeps it in n_start/n_length and an E9x retrigger restarts
     * from there, not from the sample's base address. */
    uint32_t start_lc;
    uint16_t start_len;

    /* Deferred by EDx until tick == note_delay. nd_armed is separate because
     * ED0 is a real delay of zero ticks, not an absent one. */
    uint8_t  note_delay, nd_armed, nd_sample;
    uint16_t nd_period;

    /* Queued at tick 0, consumed by the single DMACON write of §5.2. */
    uint8_t  trigger;
    uint32_t trig_lc;
    uint16_t trig_len;
} mod_chan;

typedef struct {
    mod_song *song;
    card_t   *card;

    uint8_t  position, row, tick, speed;
    uint8_t  bpm;
    uint8_t  pattern_delay;
    uint8_t  break_pending, break_row;
    uint8_t  jump_pending, jump_pos;
    uint8_t  loop_pending, loop_target;
    uint8_t  ended;               /* one full pass played -- see advance()  */
    uint8_t  visited[128];        /* positions already entered at row 0     */
    uint8_t  actrl;               /* shadow of ACTRL; the card cannot be read*/

    uint32_t ticks;               /* ticks since start, for the trace       */
    mod_chan ch[MOD_CHANNELS];

    FILE    *trace;               /* register-write trace, or NULL          */
    FILE    *rowtrace;            /* order/pattern/row per tick, or NULL    */

    /* THE REPLAYER IS NOT INSTANTANEOUS, and modelling it as if it were hides
     * the one race audio/docs/modplayer.md §5.3 exists to rule out: with zero elapsed
     * time between the DMACON enable and the loop-pointer write, the write
     * always beats the card's enable latch and every instrument loops from the
     * wrong place. Charging each register store its real cost makes the model
     * agree with the hardware, and makes the §5.3 ordering testable rather than
     * assumed.
     *
     * 5 core cycles per store at 2.0979 MHz, against a 3.546895 MHz colour
     * clock, is 8.45 colour clocks -- the same ~5-cycle assumption
     * video/docs/graphics.md §19 item 1 owes a measurement for. */
    unsigned store_cc;
    void   (*advance)(void *ctx, unsigned cc);
    void    *ctx;
} mod_player;

#define MOD_STORE_CC_DEFAULT 8u

/* Install the callback that charges elapsed time to register stores. Call it
 * BEFORE mod_start(), which preserves the setting across its reset. */
void mod_set_advance(mod_player *p, void (*fn)(void *, unsigned), void *ctx,
                     unsigned store_cc);

/* mod_start() plays row 0, so trace, rowtrace and any ACTRL bits the caller
 * wants (NTSC, LED, BYPASS) must be in place BEFORE it is called or the whole
 * of row 0 is missing from the contract. Those four fields are the only ones it
 * carries across its reset, along with the advance callback. */
void mod_start(mod_player *p, mod_song *s, card_t *c);
void mod_tick(mod_player *p);     /* one /FIRQ; the whole replayer          */

/* The authoritative ProTracker table, 16 finetunes x 36 notes — period_table.c.
 * Installed by mod_start(); mod_set_period_table() overrides it, which is only
 * useful for testing a variant tuning. */
extern const uint16_t mod_protracker_period_table[16][36];
void mod_set_period_table(const uint16_t *table_16x36);

#endif /* ARM6309_MOD_H */
