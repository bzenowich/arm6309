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
     * card, so to speak. Software loads the LUT and the state file, then sets
     * ACTRL_ENABLE. The LUT comes up zeroed here where real SRAM would come up
     * undefined; zeroed is the safe direction (silence, not noise). */
    c->ctrl = 0;
}

/* ------------------------------------------------------------------- LUT -- */

void card_load_linear_lut(card_t *c)
{
    /* Written through the register interface on purpose: it exercises the same
     * LIDX/LDATA path the 6309 boot code will use, so a bug in that path shows
     * up here rather than only on hardware. */
    card_write(c, A_LIDX1, 0);
    card_write(c, A_LIDX0, 0);

    for (unsigned v = 0; v < 128u; v++) {
        unsigned vc = v > 64u ? 64u : v;          /* Paula clamps above 64  */
        for (unsigned s = 0; s < 256u; s++) {
            int sv = (int)(int8_t)(uint8_t)s;
            /* 8-bit signed x 7-bit volume is 14 bits; the LUT is 12, so the
             * bottom two bits go. audio/docs/audio.md §6.1 argues they are below the
             * noise floor of the analogue stage. */
            int e = (sv * (int)vc) / 4;
            card_write(c, A_LDATA, (uint8_t)((e >> 8) & 0xFF));
            card_write(c, A_LDATA, (uint8_t)(e & 0xFF));
        }
    }
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
    ch->vol = s[ST_VOL] & 0x7Fu;
    ch->att = s[ST_ATT] & 0x03u;
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
            c->state[i] = val;
            if (off == ST_DAT) {
                /* Direct sample write, audio/docs/audio.md §1 requirement 8. */
                c->ch[n].samp = (int8_t)val;
            } else {
                state_sync(c, n);
            }
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
        if (val & 0x80u) { c->intreq |= (val & 0x3Fu); }
        else             { c->intreq = (uint8_t)(c->intreq & ~(val & 0x3Fu)); }
        break;

    case A_ACTRL:
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
        c->timer = (uint16_t)((c->timer & 0x00FFu) | ((uint16_t)val << 8));
        break;
    case A_TIMER0:
        /* The low byte completes the 16-bit write and arms the compare, the way
         * writing a CIA timer's latch loads and starts it. Without this the
         * compare value never matches and the tempo interrupt never fires --
         * which is how this was found. */
        c->timer = (uint16_t)((c->timer & 0xFF00u) | val);
        c->cianext = (uint16_t)(c->ciacnt + c->timer);
        break;

    case A_LIDX1: c->lidx = (uint16_t)((c->lidx & 0x00FFu) | ((uint16_t)val << 8)); break;
    case A_LIDX0: c->lidx = (uint16_t)((c->lidx & 0xFF00u) | val); break;

    case A_LDATA: {
        /* The LUT is 32768 x 16 bits presented as 65536 bytes, big-endian, so
         * one TFM burst loads the whole table. */
        unsigned e = c->lidx >> 1;
        int16_t cur = c->lut[e];
        if (c->lidx & 1u) { cur = (int16_t)((cur & ~0xFF) | val); }
        else              { cur = (int16_t)((cur & 0x00FF) | ((int16_t)val << 8)); }
        /* Sign-extend the 12-bit field the hardware actually stores. */
        c->lut[e] = (int16_t)((cur & 0x0FFF) | ((cur & 0x0800) ? ~0x0FFF : 0));
        c->lidx = (uint16_t)(c->lidx + 1u);
        break;
    }

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
        if (c->timer) { s |= 0x10u; }
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
        byte = 0;
        c->oob_reads++;
    }

    if (ch->att) {
        /* Paula's attach modulation (ADKCON): the modulating channel produces
         * no audio and its data drives the next channel's period or volume.
         * Paula is word-oriented here and this card is byte-oriented, so this
         * is an adaptation, not a transcription. UNVERIFIED — no module in the
         * test corpus exercises it. See audio/docs/audio.md §11.3. */
        card_chan *t = &c->ch[(n + 1u) & 3u];
        if (ch->att & 0x01u) { t->per = (uint16_t)((t->per & 0xFF00u) | byte); }
        if (ch->att & 0x02u) { t->vol = byte & 0x7Fu; }
        ch->samp = 0;
    } else {
        ch->samp = (int8_t)byte;
    }

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

    /* Channels walk in order 0,1,2,3, matching the hardware slot walk — which
     * matters only for attach modulation, where channel n writes n+1. */
    for (unsigned n = 0; n < 4u; n++) {
        card_chan *ch = &c->ch[n];
        if (ch->dmaen && !ch->start_in && ch->per != 0u && ch->next == c->ccnt) {
            chan_tick(c, n);
        }
    }

    /* Tempo timer, slot 4. Prescaled by 5 off the colour clock so the counter
     * runs at the Amiga's CIA rate — audio/docs/audio.md §8.2. */
    if (++c->pre5 >= CARD_CIA_DIV) {
        c->pre5 = 0;
        c->ciacnt = (uint16_t)(c->ciacnt + 1u);
        if (c->ciacnt == c->cianext) {
            c->intreq |= AINT_TIMER;
            c->cianext = (uint16_t)(c->cianext + (c->timer ? c->timer : 0u));
        }
    }
}

int card_firq(const card_t *c)
{
    return (c->intreq & c->intena) != 0;
}

void card_dac(const card_t *c, int *l, int *r)
{
    int s[4];

    if (!(c->ctrl & ACTRL_ENABLE)) { *l = 0; *r = 0; return; }

    for (unsigned n = 0; n < 4u; n++) {
        unsigned v = c->ch[n].vol & 0x7Fu;
        unsigned idx = (v << 8) | (unsigned)(uint8_t)c->ch[n].samp;
        s[n] = c->lut[idx];
    }

    /* Hard-panned, 0 and 3 left, 1 and 2 right — audio/docs/audio.md §1 requirement
     * 5. Not a preference: modules are mixed for it.
     *
     * The sum of two 12-bit signed values is 13 bits and the DAC is 12, so the
     * bottom bit is dropped once, at the converter (§6.2, §6.3). */
    *l = (s[0] + s[3]) >> 1;
    *r = (s[1] + s[2]) >> 1;
}

long card_colour_clock(const card_t *c)
{
    return (c->ctrl & ACTRL_NTSC) ? CARD_CC_NTSC : CARD_CC_PAL;
}
