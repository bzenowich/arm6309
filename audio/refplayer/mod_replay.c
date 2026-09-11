/* The ProTracker replayer — audio/docs/modplayer.md §5.
 *
 * Structured to be transliterated into 6309 assembly, not to be idiomatic C:
 * no allocation, no recursion, no unbounded loop, and every card access goes
 * through w() so the register trace is the contract that the 6309 port has to
 * reproduce. Where C could be cleverer than the 6309 will be, the C does what
 * the 6309 will do — including the dirty-flag check in set_per()/set_vol(),
 * because an unconditional write would produce a different trace.
 */

#include <string.h>
#include "mod.h"

/* ------------------------------------------------------------- tables ----- */

/* The real ProTracker table, from period_table.c. It is copied, not computed —
 * see that file's header for why, for its provenance, and for what happens if
 * you try to derive it (40 % of the entries come out wrong and every tone
 * portamento in a finetuned instrument fails to terminate). */
static uint16_t ptab[16][36];

void mod_set_period_table(const uint16_t *t)
{
    memcpy(ptab, t, sizeof ptab);
}

static void ptab_init(void)
{
    memcpy(ptab, mod_protracker_period_table, sizeof ptab);
}

/* Row 0 of whatever table is installed. The pattern stores finetune-0 periods,
 * so this is what a note is looked up in before the finetune row is applied. */
#define period_row0 (ptab[0])

/* ProTracker's vibrato/tremolo table: a half period in 32 steps, 0..255. */
static const uint8_t vib_sine[32] = {
      0,  24,  49,  74,  97, 120, 141, 161,
    180, 197, 212, 224, 235, 244, 250, 253,
    255, 253, 250, 244, 235, 224, 212, 197,
    180, 161, 141, 120,  97,  74,  49,  24
};

#define PER_MIN 113u
#define PER_MAX 856u

/* ------------------------------------------------------- card plumbing ---- */

static const char *regname(uint8_t r)
{
    static const char *n[16] = {
        "AIDX", "ADATA", "ADMACON", "AINTENA", "AINTREQ", "ACTRL",
        "SPTR2", "SPTR1", "SPTR0", "SDATA", "ASTAT", "TIMER1", "TIMER0",
        "LIDX1", "LIDX0", "LDATA"
    };
    return n[r & 0x0Fu];
}

/* Every card write in the replayer goes through here. The trace it emits is the
 * reference the 6309 port is diffed against — timestamped by TICK, not by
 * cycle, because within-tick timing legitimately differs between the two while
 * the sequence must not. */
static void w(mod_player *p, uint8_t reg, uint8_t val)
{
    if (p->trace) {
        fprintf(p->trace, "%06lu %-7s %02X\n",
                (unsigned long)p->ticks, regname(reg), val);
    }
    card_write(p->card, reg, val);
    /* Charge the store. See the comment on mod_player::store_cc. */
    if (p->advance && p->store_cc) { p->advance(p->ctx, p->store_cc); }
}

static void set_per(mod_player *p, unsigned n, uint16_t per)
{
    mod_chan *ch = &p->ch[n];
    if (per == ch->out_period) { return; }        /* §5.2 discipline 2 */
    w(p, A_AIDX, (uint8_t)(n * 16u + ST_PER1));
    w(p, A_ADATA, (uint8_t)(per >> 8));
    w(p, A_ADATA, (uint8_t)(per & 0xFFu));
    ch->out_period = per;
}

/* Paula's volume 0..64 -> the byte the card's VOL register takes, which is the
 * volume converter's 8-bit code (audio/docs/audio.md §6.1). 4v, saturated at
 * 255 so 64 is full scale. The replayer's arithmetic and clamps all stay on
 * 0..64 and this is applied only at the write - the 6309 port does the same
 * with a 65-byte table and one indexed load (modplayer.md §5.2).
 *
 * ⚠ LEAVE IT OUT AND NOTHING BREAKS AUDIBLY: every channel plays 12 dB quiet.
 * That is how the card went two days without the ×4 (§16 item 40), so
 * test_refplayer.c asserts the bytes. */
static uint8_t vol_code(uint8_t vol)
{
    return vol >= 64u ? 0xFFu : (uint8_t)(vol << 2);
}

static void set_vol(mod_player *p, unsigned n, uint8_t vol)
{
    mod_chan *ch = &p->ch[n];
    if (vol == ch->out_volume) { return; }
    w(p, A_AIDX, (uint8_t)(n * 16u + ST_VOL));
    w(p, A_ADATA, vol_code(vol));
    ch->out_volume = vol;
}

static void set_tempo(mod_player *p)
{
    /* audio/docs/audio.md §8.2: the timer counts at colourclock/5 — the Amiga's CIA
     * rate — and 1773447 is the numerator, not the clock. Confusing the two
     * detunes every tempo by exactly 2.5x. */
    /* One crystal: §4.1, and §16 item 42. 1773447 = colourclock / 2. */
    long k = 1773447L;
    uint16_t n = (uint16_t)(k / (long)(p->bpm ? p->bpm : 125u));
    w(p, A_TIMER1, (uint8_t)(n >> 8));
    w(p, A_TIMER0, (uint8_t)(n & 0xFFu));
}

/* ------------------------------------------------------ period helpers ---- */

static uint16_t clamp_per(int v)
{
    if (v < (int)PER_MIN) { return (uint16_t)PER_MIN; }
    if (v > (int)PER_MAX) { return (uint16_t)PER_MAX; }
    return (uint16_t)v;
}

static uint8_t clamp_vol(int v)
{
    if (v < 0) { return 0; }
    if (v > 64) { return 64; }
    return (uint8_t)v;
}

/* The file stores a finetune-0 period; the note actually played is the same
 * note in the channel's finetune row. Find the note by searching row 0 the way
 * ProTracker does — first entry at or below the stored period. */
static uint16_t finetuned(uint16_t period, uint8_t ft)
{
    for (unsigned i = 0; i < 36u; i++) {
        if (period >= period_row0[i]) { return ptab[ft & 0x0Fu][i]; }
    }
    return ptab[ft & 0x0Fu][35];
}

/* Index of a period within its own finetune row — needed by arpeggio and by
 * glissando, both of which step in semitones rather than in period units. */
static unsigned period_index(uint16_t period, uint8_t ft)
{
    const uint16_t *row = ptab[ft & 0x0Fu];
    for (unsigned i = 0; i < 36u; i++) {
        if (row[i] == period) { return i; }
    }
    for (unsigned i = 0; i < 36u; i++) {
        if (period >= row[i]) { return i; }
    }
    return 35u;
}

/* ------------------------------------------------------------ triggers ---- */

/* Queued here, committed by commit_triggers() in one DMACON pair so that
 * simultaneous notes start on the same colour clock — §5.2 discipline 1. */
static void queue_trigger(mod_player *p, unsigned n, uint16_t per)
{
    mod_chan *ch = &p->ch[n];
    mod_song *s = p->song;
    unsigned sm = ch->sample;
    uint32_t lc = s->sample_addr[sm];
    uint32_t bytes = (uint32_t)s->sample_len[sm] * 2u;

    ch->period = per;

    if (ch->cmd == 0x9) {                          /* 9xx sample offset */
        uint32_t off = (uint32_t)ch->offset_mem * 256u;
        if (off >= bytes) {
            /* mt_SampleOffset past the end sets the length to one word and
             * leaves the start alone, so the channel plays two bytes of the
             * sample and falls straight into the loop. */
            bytes = 2u;
        } else {
            lc += off; bytes -= off;
        }
    }

    if (!(ch->wave_ctrl & 0x04u)) { ch->vib_pos = 0; }
    if (!(ch->wave_ctrl & 0x40u)) { ch->trem_pos = 0; }

    ch->start_lc  = lc;
    ch->start_len = (uint16_t)(bytes / 2u ? bytes / 2u : 1u);
    ch->trigger  = 1;
    ch->trig_lc  = ch->start_lc;
    ch->trig_len = ch->start_len;
}

/* mt_DoRetrg — E9x restarts DMA from n_start/n_length, which already carry any
 * 9xx offset this note was given. Nothing about the note itself changes. */
static void queue_retrigger(mod_player *p, unsigned n)
{
    mod_chan *ch = &p->ch[n];

    /* No vibrato/tremolo reset: mt_DoRetrg restarts DMA and touches nothing
     * else. Only mt_SetPeriod, on a row that carries a note, rewinds them. */
    ch->trigger  = 1;
    ch->trig_lc  = ch->start_lc;
    ch->trig_len = ch->start_len;
}

/* audio/docs/modplayer.md §5.3 — the one sequence that must be exactly right. */
static void commit_triggers(mod_player *p)
{
    uint8_t mask = 0;

    for (unsigned n = 0; n < MOD_CHANNELS; n++) {
        if (p->ch[n].trigger) { mask |= (uint8_t)(1u << n); }
    }
    if (!mask) { return; }

    /* 1. one-shot pointer, full length, and this note's period and volume */
    for (unsigned n = 0; n < MOD_CHANNELS; n++) {
        mod_chan *ch = &p->ch[n];
        if (!ch->trigger) { continue; }
        w(p, A_AIDX, (uint8_t)(n * 16u + ST_LC2));
        w(p, A_ADATA, (uint8_t)((ch->trig_lc >> 16) & 0x07u));
        w(p, A_ADATA, (uint8_t)((ch->trig_lc >> 8) & 0xFFu));
        w(p, A_ADATA, (uint8_t)(ch->trig_lc & 0xFFu));
        w(p, A_ADATA, (uint8_t)(ch->trig_len >> 8));
        w(p, A_ADATA, (uint8_t)(ch->trig_len & 0xFFu));
        w(p, A_ADATA, (uint8_t)(ch->period >> 8));
        w(p, A_ADATA, (uint8_t)(ch->period & 0xFFu));
        w(p, A_ADATA, vol_code(ch->volume));
        ch->out_period = ch->period;
        ch->out_volume = ch->volume;
    }

    /* 2. stop then start. The stop is what makes a retrigger restart from the
     *    beginning instead of waiting out the current buffer. */
    w(p, A_ADMACON, mask);
    w(p, A_ADMACON, (uint8_t)(0x80u | mask));

    /* 3. the loop point, immediately, in the same tick. This does not disturb
     *    the note now playing — it only changes what the card reloads when the
     *    one-shot runs out (audio/docs/audio.md §3.3). ProTracker's delay loop is not
     *    needed here: the enable-triggered latch is bounded at 4 colour clocks,
     *    1.13 us, shorter than the gap between two 6309 stores. */
    for (unsigned n = 0; n < MOD_CHANNELS; n++) {
        mod_chan *ch = &p->ch[n];
        mod_song *s = p->song;
        unsigned sm = ch->sample;
        if (!ch->trigger) { continue; }
        w(p, A_AIDX, (uint8_t)(n * 16u + ST_LC2));
        w(p, A_ADATA, (uint8_t)((s->sample_rep[sm] >> 16) & 0x07u));
        w(p, A_ADATA, (uint8_t)((s->sample_rep[sm] >> 8) & 0xFFu));
        w(p, A_ADATA, (uint8_t)(s->sample_rep[sm] & 0xFFu));
        w(p, A_ADATA, (uint8_t)(s->sample_replen[sm] >> 8));
        w(p, A_ADATA, (uint8_t)(s->sample_replen[sm] & 0xFFu));
        ch->trigger = 0;
    }
}

/* ------------------------------------------------------------- effects ---- */

static void volslide(mod_chan *ch, uint8_t param)
{
    unsigned up = param >> 4, dn = param & 0x0Fu;
    /* ProTracker gives "up" priority when both nibbles are set. */
    ch->volume = up ? clamp_vol((int)ch->volume + (int)up)
                    : clamp_vol((int)ch->volume - (int)dn);
}

static uint16_t vibrato(uint16_t per, const uint8_t *ctrl,
                        uint8_t cmd, uint8_t *pos, unsigned depth_div)
{
    unsigned slot = (unsigned)(*pos >> 2) & 0x1Fu;
    unsigned amp;

    switch (*ctrl & 0x03u) {
    case 0:  amp = vib_sine[slot]; break;
    case 1:  amp = slot * 8u; if (*pos & 0x80u) { amp = 255u - amp; } break;
    default: amp = 255u; break;                        /* square, and random */
    }
    amp = (amp * (unsigned)(cmd & 0x0Fu)) / depth_div;

    per = (uint16_t)((*pos & 0x80u) ? (unsigned)per - amp : (unsigned)per + amp);
    *pos = (uint8_t)(*pos + (uint8_t)((cmd >> 4) * 4u));
    return per;
}

static void tone_porta(mod_chan *ch)
{
    if (!ch->target_period) { return; }
    if (ch->period < ch->target_period) {
        ch->period = (uint16_t)(ch->period + ch->porta_speed);
        if (ch->period > ch->target_period) { ch->period = ch->target_period; }
    } else if (ch->period > ch->target_period) {
        int v = (int)ch->period - (int)ch->porta_speed;
        ch->period = (uint16_t)(v < (int)ch->target_period ? ch->target_period : (uint16_t)v);
    }
    if (ch->glissando) {
        ch->period = ptab[ch->finetune & 0x0Fu][period_index(ch->period, ch->finetune)];
    }
}

/* E commands evaluated once, at tick 0. `note` is the row's period word, zero
 * when the row carries no note — mt_RetrigNote needs it. */
static void e_tick0(mod_player *p, unsigned n, uint16_t note)
{
    mod_chan *ch = &p->ch[n];
    unsigned sub = ch->param >> 4, x = ch->param & 0x0Fu;

    switch (sub) {
    case 0x0:
        /* E0x — the only effect in the whole command set that reaches hardware
         * other than a channel register (audio/docs/modplayer.md §5.6). x=0 turns the
         * LED filter ON, x=1 turns it off. Ignored under user bypass, which is
         * a deliberate setting the module has no business overriding. */
        if (!(p->actrl & ACTRL_BYPASS)) {
            p->actrl = (uint8_t)((x & 1u) ? (p->actrl & ~ACTRL_LED)
                                          : (p->actrl | ACTRL_LED));
            w(p, A_ACTRL, p->actrl);
        }
        break;
    case 0x1: ch->period = clamp_per((int)ch->period - (int)x); break;
    case 0x2: ch->period = clamp_per((int)ch->period + (int)x); break;
    case 0x3: ch->glissando = (uint8_t)x; break;
    case 0x4: ch->wave_ctrl = (uint8_t)((ch->wave_ctrl & 0xF0u) | x); break;
    case 0x5: break;                                   /* applied before lookup */
    case 0x6:
        if (x == 0u) {
            ch->loop_row = p->row;
        } else {
            if (ch->loop_cnt == 0u) { ch->loop_cnt = (uint8_t)x; }
            else                    { ch->loop_cnt--; }
            if (ch->loop_cnt) {
                /* Per-channel in the file, per-song in effect; the last channel
                 * processed wins (audio/docs/modplayer.md §5.8). */
                p->loop_pending = 1;
                p->loop_target  = ch->loop_row;
            }
        }
        break;
    case 0x7: ch->wave_ctrl = (uint8_t)((ch->wave_ctrl & 0x0Fu) | (x << 4)); break;
    case 0x9:
        /* mt_RetrigNote runs at tick 0 too, and tick 0 divides by x with
         * remainder 0 — so a row carrying E9x and no note retriggers at once.
         * A row that does carry a note has already triggered it. */
        if (x && !note) { queue_retrigger(p, n); }
        break;
    case 0xA: ch->volume = clamp_vol((int)ch->volume + (int)x); break;
    case 0xB: ch->volume = clamp_vol((int)ch->volume - (int)x); break;
    case 0xC:
        /* EC0 cuts at tick 0, from mt_CheckMoreEffects; e_per_tick never sees
         * tick 0 and would drop it. */
        if (x == 0u) { ch->volume = 0; }
        break;
    case 0xE: p->pattern_delay = (uint8_t)x; break;
    case 0xF:
        /* EFx invert loop ("funk repeat") modifies sample data in place. It is
         * rare, it is destructive, and here the data lives in card RAM where a
         * read-modify-write costs two register accesses per byte.
         * Unimplemented by decision, not by omission — audio/docs/modplayer.md §10.8
         * and §11 item 3. */
        break;
    default: break;                                    /* E8x, EDx */
    }
}

/* E commands evaluated on every tick. */
static void e_per_tick(mod_player *p, unsigned n)
{
    mod_chan *ch = &p->ch[n];
    unsigned sub = ch->param >> 4, x = ch->param & 0x0Fu;

    switch (sub) {
    case 0x9:                                          /* retrigger */
        if (x && (p->tick % x) == 0u) { queue_retrigger(p, n); }
        break;
    case 0xC:                                          /* note cut */
        if (p->tick == x) { ch->volume = 0; }
        break;
    case 0xD:                                          /* note delay */
        if (ch->nd_armed && p->tick == ch->note_delay) {
            ch->nd_armed = 0;
            ch->sample = ch->nd_sample;
            queue_trigger(p, n, ch->nd_period);
        }
        break;
    default: break;
    }
}

/* ------------------------------------------------------------- the row ---- */

static void row_channel(mod_player *p, unsigned n, const uint8_t *cell)
{
    mod_chan *ch = &p->ch[n];
    unsigned sm  = (unsigned)(cell[0] & 0xF0u) | (unsigned)(cell[2] >> 4);
    uint16_t per = (uint16_t)(((unsigned)(cell[0] & 0x0Fu) << 8) | cell[1]);

    ch->cmd   = cell[2] & 0x0Fu;
    ch->param = cell[3];

    /* A note delay lives for exactly its own row. */
    ch->nd_armed = 0;
    ch->nd_period = 0;

    /* mt_SampleOffset takes the parameter into memory whenever the command is
     * seen, note or not — and it does so before the note is set up, so the
     * memory this row leaves behind is the one this row's note uses. */
    if (ch->cmd == 0x9u && ch->param) { ch->offset_mem = ch->param; }

    if (sm) {
        /* §10.1: a sample number selects the instrument and sets the volume.
         * It does NOT retrigger. Retriggering here is the single most audible
         * wrong behaviour a naive player has. */
        if (sm >= MOD_MAX_SAMPLES) { sm = 0; }
        ch->sample   = (uint8_t)sm;
        ch->volume   = p->song->sample_vol[sm];
        ch->finetune = p->song->sample_ft[sm];
    }

    if (ch->cmd == 0xE && (ch->param >> 4) == 0x5u) {
        ch->finetune = ch->param & 0x0Fu;               /* E5x, before lookup */
    }

    if (per) {
        uint16_t fp = finetuned(per, ch->finetune);

        if (ch->cmd == 0x3u || ch->cmd == 0x5u) {
            /* Tone portamento takes the note as a destination and does not
             * retrigger the sample. */
            ch->target_period = fp;
            if (ch->cmd == 0x3u && ch->param) { ch->porta_speed = ch->param; }
        } else if (ch->cmd == 0xEu && (ch->param >> 4) == 0xDu) {
            ch->note_delay = (uint8_t)(ch->param & 0x0Fu);
            ch->nd_sample  = ch->sample;
            ch->nd_period  = fp;
            ch->nd_armed   = 1;
            if (ch->note_delay == 0u) { ch->nd_armed = 0; queue_trigger(p, n, fp); }
        } else {
            ch->target_period = 0;
            queue_trigger(p, n, fp);
        }
    }

    switch (ch->cmd) {
    case 0x4:                                          /* vibrato params */
        if (ch->param >> 4)      { ch->vib_cmd = (uint8_t)((ch->vib_cmd & 0x0Fu) | (ch->param & 0xF0u)); }
        if (ch->param & 0x0Fu)   { ch->vib_cmd = (uint8_t)((ch->vib_cmd & 0xF0u) | (ch->param & 0x0Fu)); }
        break;
    case 0x7:                                          /* tremolo params */
        if (ch->param >> 4)      { ch->trem_cmd = (uint8_t)((ch->trem_cmd & 0x0Fu) | (ch->param & 0xF0u)); }
        if (ch->param & 0x0Fu)   { ch->trem_cmd = (uint8_t)((ch->trem_cmd & 0xF0u) | (ch->param & 0x0Fu)); }
        break;
    case 0xB:                                          /* position jump */
        p->jump_pending = 1; p->jump_pos = ch->param;
        break;
    case 0xC:                                          /* set volume */
        ch->volume = clamp_vol((int)ch->param);
        break;
    case 0xD: {                                        /* pattern break */
        /* §10.4: the parameter is DECIMAL. D10 breaks to row 10, not 16. */
        unsigned r = (unsigned)(ch->param >> 4) * 10u + (ch->param & 0x0Fu);
        p->break_pending = 1;
        p->break_row = (uint8_t)(r > 63u ? 0u : r);
        break;
    }
    case 0xE:
        e_tick0(p, n, per);
        break;
    case 0xF:
        /* §5.7: Fxx=0 is "stop" in some trackers and "ignore" in others.
         * Ignoring it breaks fewer modules. */
        if (ch->param == 0u)        { break; }
        if (ch->param < 0x20u)      { p->speed = ch->param; }
        else                        { p->bpm = ch->param; set_tempo(p); }
        break;
    default:
        break;
    }
}

/* ------------------------------------------------------- position logic --- */

/* audio/docs/modplayer.md §5.8. The order of these steps is where players diverge. */
static void advance(mod_player *p)
{
    if (p->loop_pending) {
        p->loop_pending = 0;
        p->row = p->loop_target;
        /* A Dxx or Bxx sharing this row has already been read. ProTracker acts
         * on the row's position effects in this tick or not at all, so they
         * must not survive to fire one row after the loop-back. */
        p->break_pending = 0;
        p->jump_pending = 0;
        return;                                        /* loop beats advance */
    }

    p->row++;

    if (p->break_pending) {
        p->row = p->break_row;
        p->position++;
    }
    if (p->jump_pending) {
        p->position = p->jump_pos;
        /* Bxx and Dxx on the same row means "position Bxx, row Dxx" — so this
         * must see the row the break set, not reset it to 0. */
        if (!p->break_pending) { p->row = 0; }
    }
    p->break_pending = 0;
    p->jump_pending = 0;

    if (p->row > 63u) { p->row = 0; p->position++; }

    if (p->position >= p->song->songlength) {
        /* §10.9: the restart byte at offset 951 is unreliable. Loop to 0. */
        p->position = 0;
    }

    /* "The song has played once" is not "the position counter wrapped". Most
     * modules end with a Bxx jump back into themselves, so the counter never
     * reaches songlength -- ode2ptk.mod is one, and it rendered forever until
     * this was added. The standard test is arriving at a position already
     * entered at row 0. Pattern loops (E6x) revisit rows, not positions, so
     * they do not trip it. */
    if (p->row == 0u) {
        if (p->visited[p->position & 0x7Fu]) { p->ended = 1; }
        p->visited[p->position & 0x7Fu] = 1;
    }
}

/* --------------------------------------------------------------- public --- */

void mod_set_advance(mod_player *p, void (*fn)(void *, unsigned), void *ctx,
                     unsigned store_cc)
{
    p->advance  = fn;
    p->ctx      = ctx;
    p->store_cc = store_cc;
}

void mod_start(mod_player *p, mod_song *s, card_t *c)
{
    void (*keep_fn)(void *, unsigned) = p->advance;
    void *keep_ctx = p->ctx;
    unsigned keep_cc = p->store_cc;
    FILE *keep_trace = p->trace;
    FILE *keep_rowtrace = p->rowtrace;
    uint8_t keep_actrl = p->actrl;

    memset(p, 0, sizeof *p);
    p->advance  = keep_fn;
    p->ctx      = keep_ctx;
    p->store_cc = keep_cc ? keep_cc : MOD_STORE_CC_DEFAULT;
    p->trace    = keep_trace;
    p->rowtrace = keep_rowtrace;
    p->actrl    = keep_actrl;
    p->song = s;
    p->card = c;
    p->speed = 6;
    p->bpm   = 125;
    p->tick  = 0;
    p->position = 0;
    p->row = 0;
    p->visited[0] = 1;

    ptab_init();

    for (unsigned n = 0; n < MOD_CHANNELS; n++) {
        p->ch[n].sample     = 0;
        p->ch[n].out_period = 0xFFFFu;                 /* force the first write */
        p->ch[n].out_volume = 0xFFu;
        p->ch[n].start_lc   = MOD_NULL_LOOP;
        /* Never 0: LEN = 0 means 65536 words to the card, so an E9x on a
         * channel that has never had a note would run away through RAM. */
        p->ch[n].start_len  = 1;
    }


    /* Quiet, then configured, then enabled — the card comes up with ACTRL = 0
     * precisely so this order is possible (audio/docs/audio.md §9.2). */
    for (unsigned n = 0; n < MOD_CHANNELS; n++) {
        w(p, A_AIDX, (uint8_t)(n * 16u));
        for (unsigned i = 0; i < 11u; i++) { w(p, A_ADATA, 0); }
    }
    w(p, A_ADMACON, 0x0Fu);                            /* all channels off */
    w(p, A_AINTREQ, 0x3Fu);                            /* clear all pending */
    w(p, A_AINTENA, (uint8_t)(0x80u | AINT_TIMER));

    /* TIMER goes down BEFORE ACTRL b6, which is modplayer.md §4's order and
     * audio.md §8.2's rule: setting b6 loads the counter from whatever TIMER
     * holds, and before this write that is reset garbage - a period of up to
     * 65,535 ticks, or 0, which fires every colour clock. Whatever the caller
     * asked for -- LED, BYPASS -- rides in the same shadow, so the card and
     * the shadow can never disagree and every later E0x is computed from what
     * the card actually holds. DMA is already off, so enabling is silent. */
    set_tempo(p);
    p->actrl = (uint8_t)(p->actrl | ACTRL_ENABLE | ACTRL_TIMER);
    w(p, A_ACTRL, p->actrl);

    /* Play row 0 now rather than waiting for the timer's first expiry. Arming
     * the timer schedules the NEXT tick, so without this the song begins one
     * whole tick late -- 20 ms at the default tempo, which is silence before
     * the first note and a constant offset against every other player. Found by
     * A/B: our output tracked libopenmpt's exactly, shifted 20 ms right. */
    mod_tick(p);
}

void mod_tick(mod_player *p)
{
    /* Three tick kinds, not two: a fresh row, an EEx repeat of it, and an
     * ordinary tick. The repeat runs the per-tick effect path exactly as
     * ProTracker's mt_NoNewAllChannels does, which is what makes a delayed note
     * fire once per repeat (audio/docs/modplayer.md §10.10) -- but it does not
     * re-read the row, so the tick-0-only effects do not run again. */
    int newrow = (p->tick == 0u && p->pattern_delay == 0u);

    p->ticks++;

    /* The path through the song -- order, pattern, row, speed, tempo -- is a
     * far sharper comparison against another implementation than the audio is.
     * §5.8's ordering either matches or it does not, and a diff says on which
     * row it stopped matching. */
    if (p->rowtrace) {
        fprintf(p->rowtrace, "%lu %u %u %u %u %u %u\n",
                (unsigned long)p->ticks, p->position,
                p->song->order[p->position], p->row, p->tick, p->speed, p->bpm);
    }

    /* Sole /FIRQ source, so no polling chain: it was us (audio/docs/audio.md §8.1). */
    w(p, A_AINTREQ, AINT_TIMER);

    if (newrow) {
        const uint8_t *pat = p->song->patterns
                           + (size_t)p->song->order[p->position] * 1024u
                           + (size_t)p->row * 16u;
        for (unsigned n = 0; n < MOD_CHANNELS; n++) {
            row_channel(p, n, pat + n * 4u);
        }
    } else {
        if (p->tick == 0u) {
            p->pattern_delay--;
            /* mt_NoteDelay re-reads the row's note word on every repeat, so the
             * delay re-arms. ED0 has to arm too, and fires on this very tick. */
            for (unsigned n = 0; n < MOD_CHANNELS; n++) {
                mod_chan *ch = &p->ch[n];
                if (ch->cmd == 0xEu && (ch->param >> 4) == 0xDu && ch->nd_period) {
                    ch->note_delay = (uint8_t)(ch->param & 0x0Fu);
                    ch->nd_armed = 1;
                }
            }
        }
        for (unsigned n = 0; n < MOD_CHANNELS; n++) {
            mod_chan *ch = &p->ch[n];
            uint16_t per = ch->period;
            uint8_t  vol = ch->volume;

            switch (ch->cmd) {
            case 0x0:                                  /* arpeggio */
                if (ch->param) {
                    unsigned k = p->tick % 3u;
                    unsigned add = (k == 1u) ? (unsigned)(ch->param >> 4)
                                 : (k == 2u) ? (unsigned)(ch->param & 0x0Fu) : 0u;
                    unsigned i = period_index(ch->period, ch->finetune) + add;
                    per = ptab[ch->finetune & 0x0Fu][i > 35u ? 35u : i];
                }
                break;
            case 0x1:
                ch->period = clamp_per((int)ch->period - (int)ch->param);
                per = ch->period;
                break;
            case 0x2:
                ch->period = clamp_per((int)ch->period + (int)ch->param);
                per = ch->period;
                break;
            case 0x3:
                /* mt_TonePortamento takes a new speed from a non-zero parameter
                 * every time it runs, note or not -- 305 / 310 / 320 on
                 * note-less rows is how modules accelerate a slide. 5xx's
                 * parameter is a volume slide and must never land here. */
                if (ch->param) { ch->porta_speed = ch->param; }
                tone_porta(ch); per = ch->period;
                break;
            case 0x4:
                per = vibrato(per, &ch->wave_ctrl, ch->vib_cmd, &ch->vib_pos, 128u);
                break;
            case 0x5:
                tone_porta(ch); per = ch->period; volslide(ch, ch->param); vol = ch->volume;
                break;
            case 0x6:
                per = vibrato(per, &ch->wave_ctrl, ch->vib_cmd, &ch->vib_pos, 128u);
                volslide(ch, ch->param); vol = ch->volume;
                break;
            case 0x7: {
                uint8_t wc = (uint8_t)(ch->wave_ctrl >> 4);
                unsigned slot = (unsigned)(ch->trem_pos >> 2) & 0x1Fu;
                unsigned amp = (wc & 3u) == 0u ? vib_sine[slot]
                             : (wc & 3u) == 1u ? (slot * 8u) : 255u;
                if ((wc & 3u) == 1u && (ch->trem_pos & 0x80u)) { amp = 255u - amp; }
                amp = (amp * (unsigned)(ch->trem_cmd & 0x0Fu)) / 64u;
                vol = clamp_vol((ch->trem_pos & 0x80u) ? (int)ch->volume - (int)amp
                                                       : (int)ch->volume + (int)amp);
                ch->trem_pos = (uint8_t)(ch->trem_pos + (uint8_t)((ch->trem_cmd >> 4) * 4u));
                break;
            }
            case 0xA:
                volslide(ch, ch->param); vol = ch->volume;
                break;
            case 0xE:
                e_per_tick(p, n); per = ch->period; vol = ch->volume;
                break;
            default:
                break;
            }

            set_per(p, n, per);
            set_vol(p, n, vol);
        }
    }

    commit_triggers(p);

    if (newrow) {
        /* Tick 0 writes PER/VOL after the trigger commit so the dirty-flag
         * shadows are already up to date and nothing is written twice. */
        for (unsigned n = 0; n < MOD_CHANNELS; n++) {
            /* Unconditional, including for a channel in the middle of a
             * vibrato: mt_CheckMoreEffects falls through to mt_PerNop for every
             * command outside {9,B,D,E,F,C}, so ProTracker writes the BASE
             * period at tick 0 and the pitch really does snap back for one tick
             * at every row boundary. Suppressing it is audible and wrong --
             * see test_effect_vibrato_row_snap. */
            set_per(p, n, p->ch[n].period);
            set_vol(p, n, p->ch[n].volume);
        }
    }

    if (++p->tick >= p->speed) {
        p->tick = 0;
        if (p->pattern_delay == 0u) { advance(p); }
    }
}
