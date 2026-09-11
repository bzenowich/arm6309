/* Model of the arm6309 sound card. See card.h and audio/docs/audio.md. */

#include <string.h>
#include "card.h"

/* ------------------------------------------------------------------ util -- */

static uint32_t rd19(const uint8_t *p)
{
    return ((uint32_t)(p[0] & 0x07u) << 16) | ((uint32_t)p[1] << 8) | p[2];
}

static uint16_t rd16(const uint8_t *p)
{
    return (uint16_t)(((uint16_t)p[0] << 8) | p[1]);
}

/* Paula treats LEN = 0 as 65536 words. Byte count, so 131072. */
static uint32_t len_bytes(uint32_t len_words)
{
    return len_words ? (len_words * 2u) : 131072u;
}

/* ----------------------------------------------------------------- reset -- */

void card_reset(card_t *c, uint8_t *sram, uint32_t sram_bytes)
{
    uint8_t *keep_sram = sram;
    uint32_t keep_bytes = sram_bytes;

    memset(c, 0, sizeof *c);
    c->sram = keep_sram;
    c->sram_bytes = keep_bytes;

    /* audio/docs/audio.md §13: reset leaves the card quiet — display of the audio
     * card, so to speak. Software loads the state file, then sets ACTRL_ENABLE.
     * Silence is $80 in offset binary (§6.1), so the held sample bytes do not
     * come up at zero the way memset left them. */
    c->ctrl = 0;
    for (unsigned n = 0; n < 4u; n++) { c->ch[n].samp = 0x80u; }
}

/* --------------------------------------------------------- state file ----- */

/* Re-read a channel's host-written fields after any ADATA write. Cheaper than
 * decoding which field moved, and it cannot get out of step. */
static void state_sync(card_t *c, unsigned n)
{
    card_chan *ch = &c->ch[n];
    const uint8_t *s = &c->state[n * 16u];

    ch->lc  = rd19(&s[ST_LC2]);
    ch->len = rd16(&s[ST_LEN1]);
    ch->per = rd16(&s[ST_PER1]);
    ch->vol = s[ST_VOL];
    ch->pan = s[ST_PAN];
}

static void state_publish(card_t *c, unsigned n)
{
    card_chan *ch = &c->ch[n];
    uint8_t *s = &c->state[n * 16u];
    uint32_t words = (ch->cnt + 1u) / 2u;

    s[ST_PTR2] = (uint8_t)((ch->ptr >> 16) & 0x07u);
    s[ST_PTR1] = (uint8_t)((ch->ptr >> 8) & 0xFFu);
    s[ST_PTR0] = (uint8_t)(ch->ptr & 0xFFu);
    s[ST_CNT1] = (uint8_t)((words >> 8) & 0xFFu);
    s[ST_CNT0] = (uint8_t)(words & 0xFFu);
}

/* ---------------------------------------------------------------- writes -- */

void card_write(card_t *c, uint8_t reg, uint8_t val)
{
    switch (reg & 0x0Fu) {
    case A_AIDX:
        c->aidx = (uint8_t)(val % CARD_STATE_BYTES);
        break;

    case A_ADATA: {
        unsigned i = c->aidx;
        unsigned n = i / 16u, off = i % 16u;
        /* PTR/CNT are read-only; a write there is a software bug, not a mode. */
        if (off <= ST_PAN) {
            /* Offset 8 is reserved: CPU-fed samples were retired 2026-09-11
             * (audio/docs/audio.md §1 requirement 8), so a write there is
             * stored and plays nothing — exactly what the card does. */
            c->state[i] = val;
            state_sync(c, n);
        }
        c->aidx = (uint8_t)((i + 1u) % CARD_STATE_BYTES);
        break;
    }

    case A_ADMACON: {
        uint8_t mask = val & 0x0Fu;
        if (val & 0x80u) {
            for (unsigned n = 0; n < 4u; n++) {
                if ((mask >> n) & 1u) {
                    if (!c->ch[n].dmaen) {
                        /* Enable: the pointer and counter latch from the
                         * shadow. audio/docs/audio.md §16 item 13 bounds the delay,
                         * and modplayer.md §5.3 relies on the bound to drop
                         * ProTracker's delay loop — so model the delay rather
                         * than latching instantly, or the model would hide
                         * exactly the race it is meant to prove absent. */
                        c->ch[n].start_in = CARD_ENABLE_LATENCY;
                    }
                    c->ch[n].dmaen = 1;
                }
            }
        } else {
            for (unsigned n = 0; n < 4u; n++) {
                if ((mask >> n) & 1u) {
                    c->ch[n].dmaen = 0;
                    c->ch[n].start_in = 0;
                    /* Paula holds the last fetched sample when DMA stops — it
                     * does not zero the channel. That is why ProTracker sets
                     * volume to 0 rather than trusting a DMA stop to silence,
                     * and modelling it faithfully is the point of a reference. */
                }
            }
        }
        break;
    }

    case A_AINTENA:
        if (val & 0x80u) { c->intena |= (val & 0x3Fu); }
        else             { c->intena = (uint8_t)(c->intena & ~(val & 0x3Fu)); }
        break;

    case A_AINTREQ:
        /* b7 = 1 SETS the named request bits, Paula-style. It is not a
         * write-back of a read value: software raises a request to make the
         * card interrupt itself, which is how a driver hands work to its own
         * /FIRQ handler. audio.md §9.2 specifies both directions. */
        if (val & 0x80u) { c->intreq |= (val & 0x3Fu); }
        else             { c->intreq = (uint8_t)(c->intreq & ~(val & 0x3Fu)); }
        break;

    case A_ACTRL:
        /* While b6 was 0 U1 reloaded the count every colour clock, and a host
         * write is several colour clocks long, so the count holds ~TIMER at
         * the instant b6 is set. This model's writes are instantaneous. */
        if (!(c->ctrl & ACTRL_TIMER)) { c->tc = (uint16_t)~c->timer; }
        c->ctrl = val;
        break;

    case A_SPTR2: c->sptr = (c->sptr & 0x0FFFFu) | ((uint32_t)(val & 0x07u) << 16); break;
    case A_SPTR1: c->sptr = (c->sptr & 0x700FFu) | ((uint32_t)val << 8); break;
    case A_SPTR0: c->sptr = (c->sptr & 0x7FF00u) | val; break;

    case A_SDATA:
        if (c->sptr < CARD_SRAM_BYTES && c->sram) { c->sram[c->sptr] = val; }
        c->sptr = (c->sptr + 1u) & 0x7FFFFu;
        break;

    case A_ASTAT:
        break;                      /* read-only */

    case A_TIMER1:
        c->timer_hi = val;              /* staged, §9.4.3 */
        break;
    case A_TIMER0:
        /* The low byte commits both, as U2 does. It does NOT restart the
         * period: U1's counter takes TIMER at its next reload, which is what
         * writing a running CIA's latch does - audio.md §8.2, §16 item 44.
         * ⛔ This model used to restart the period on every TIMER0 write, and
         * the card it modelled never reached TIMER at all. */
        c->timer = (uint16_t)(((uint16_t)c->timer_hi << 8) | val);
        break;

    default:
        break;
    }
}

uint8_t card_read(card_t *c, uint8_t reg)
{
    switch (reg & 0x0Fu) {
    case A_ADATA: {
        unsigned i = c->aidx;
        unsigned n = i / 16u;
        state_publish(c, n);
        c->aidx = (uint8_t)((i + 1u) % CARD_STATE_BYTES);
        /* Reads are prefetched on the AIDX write and on each auto-increment,
         * so they never stall — audio/docs/audio.md §9.3. */
        return c->state[i];
    }
    case A_AINTREQ:
        return c->intreq;
    case A_ASTAT: {
        uint8_t s = 0;
        for (unsigned n = 0; n < 4u; n++) { if (c->ch[n].dmaen) { s |= (uint8_t)(1u << n); } }
        if (c->ctrl & ACTRL_TIMER) { s |= 0x10u; }     /* b4 is ACTRL b6, §9.2 */
        return s;
    }
    case A_SDATA: {
        uint8_t v = (c->sptr < CARD_SRAM_BYTES && c->sram) ? c->sram[c->sptr] : 0u;
        c->sptr = (c->sptr + 1u) & 0x7FFFFu;
        return v;
    }
    default:
        return 0;
    }
}

/* ------------------------------------------------------------------ step -- */

static void chan_reload(card_t *c, unsigned n)
{
    card_chan *ch = &c->ch[n];
    ch->ptr = ch->lc;
    ch->cnt = len_bytes(ch->len);
}

static void chan_tick(card_t *c, unsigned n)
{
    card_chan *ch = &c->ch[n];
    uint8_t byte;

    if (ch->ptr < c->sram_bytes && c->sram) {
        byte = c->sram[ch->ptr];
    } else {
        /* Silence rather than whatever is in unwritten RAM, and count it: a
         * non-zero tally here means the loader relocated something wrongly
         * (audio/docs/modplayer.md §4.6), which is worth failing a test over. */
        byte = 0x80u;                 /* offset-binary silence, §6.1 */
        c->oob_reads++;
    }

    /* No attach modulation: it was retired 2026-09-11 (audio/docs/audio.md
     * §11.3) because no ProTracker replayer writes ADKCON. */
    ch->samp = byte;

    ch->ptr = (ch->ptr + 1u) & 0x7FFFFu;

    if (--ch->cnt == 0u) {
        /* THE shadow reload — audio/docs/audio.md §3.3, requirement 3. It takes
         * whatever the host has written into LC/LEN since the buffer started,
         * which is what makes ProTracker's one-shot-then-loop idiom work. */
        chan_reload(c, n);
        c->intreq |= (uint8_t)(AINT_CH0 << n);
    }

    ch->next = (uint16_t)(ch->next + ch->per);
}

void card_step(card_t *c)
{
    c->cc++;
    c->ccnt = (uint16_t)(c->ccnt + 1u);

    /* Enables retire first, and a channel that latches this clock does not also
     * tick on it — its first fetch is one period out (§1 requirement 6). */
    for (unsigned n = 0; n < 4u; n++) {
        card_chan *ch = &c->ch[n];
        if (ch->start_in && --ch->start_in == 0u) {
            chan_reload(c, n);
            ch->next = (uint16_t)(c->ccnt + ch->per);
        }
    }

    /* Channels walk in order 0,1,2,3, matching the hardware slot walk. */
    for (unsigned n = 0; n < 4u; n++) {
        card_chan *ch = &c->ch[n];
        if (ch->dmaen && !ch->start_in && ch->per != 0u && ch->next == c->ccnt) {
            chan_tick(c, n);
        }
    }

    /* Tempo timer - U1's CIA count, audio.md §8.2. Slot 4 reloads it from
     * TIMER: after a period, or every colour clock while ACTRL b6 is 0, so
     * setting b6 starts a whole period. Slot 7 of every fifth colour clock
     * advances it while b6 runs. It counts up from ~TIMER because all-ones is
     * one product term on the part; a period is TIMER ticks exactly. */
    if (!(c->ctrl & ACTRL_TIMER)) {
        c->tc = (uint16_t)~c->timer;
    } else if (c->tc == 0xFFFFu) {
        c->intreq |= AINT_TIMER;
        c->tc = (uint16_t)~c->timer;
    }
    if (c->pre5 == CARD_CIA_DIV - 1u && (c->ctrl & ACTRL_TIMER)) {
        c->tc = (uint16_t)(c->tc + 1u);
    }
    c->pre5 = (uint8_t)((c->pre5 + 1u) % CARD_CIA_DIV);
}

int card_firq(const card_t *c)
{
    return (c->intreq & c->intena) != 0;
}

int card_chan_out(const card_t *c, unsigned n)
{
    /* The sample converter is unsigned-coded and its half-scale pedestal is
     * cancelled at its own I/V node, BEFORE the volume stage (§6.3) — which is
     * why VOL = 0 is exact silence here, with no DC step to leave behind.
     *
     * VOL IS THE VOLUME CONVERTER'S CODE, taken verbatim, because that is what
     * the card does: W5 copies the state-file byte into the AD7528 unchanged.
     * Paula's 0..64 -> 4v saturated is the REPLAYER's job (mod_replay.c,
     * audio.md §6.1). This model used to do that ×4 itself, which the card
     * never did - a model above its hardware, and a control that played 12 dB
     * louder than the card it was controlling for. */
    return ((int)c->ch[n].samp - 128) * (int)c->ch[n].vol;
}

void card_dac(const card_t *c, int *l, int *r)
{
    int s[4];

    if (!(c->ctrl & ACTRL_ENABLE)) { *l = 0; *r = 0; return; }

    for (unsigned n = 0; n < 4u; n++) { s[n] = card_chan_out(c, n); }

    /* Hard-panned, 0 and 3 left, 1 and 2 right — audio/docs/audio.md §1 requirement
     * 5. Not a preference: modules are mixed for it.
     *
     * The sum is ANALOGUE on the card (§6.2): the two channels of a side are two
     * ladders on ONE die, and their currents meet at a single I/V amplifier's
     * virtual ground. Nothing is quantised or truncated there, which is why this
     * is a plain addition of two exact products. The port registers and write
     * windows are not modelled: they exist only to give the converter its 100 ns
     * of setup, and the latency they add is fixed per channel and inaudible. */
    *l = s[0] + s[3];
    *r = s[1] + s[2];
}

long card_colour_clock(const card_t *c)
{
    /* One crystal - audio.md §4.1, and §16 item 42 retired ACTRL b2. The
     * parameter stays: the signature is card.h's public API and every caller
     * passes the card it is asking about, which is the honest shape even now
     * that the answer does not depend on it. */
    (void)c;
    return CARD_CC_PAL;
}
