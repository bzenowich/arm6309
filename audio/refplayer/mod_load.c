/* The module loader — audio/docs/modplayer.md §4.
 *
 * The whole job is relocation. Not one period, volume, length, finetune byte or
 * sample byte is transformed on the way through; only the two address fields
 * are computed (§4.3). If this file ever grows arithmetic on a period, that is
 * the bug.
 */

#include <stdlib.h>
#include <string.h>
#include "mod.h"

#define HDR31   1084u
#define HDR15    600u

static uint16_t be16(const uint8_t *p)
{
    return (uint16_t)(((uint16_t)p[0] << 8) | p[1]);
}

static int fail(char *err, size_t n, const char *msg)
{
    if (err && n) { snprintf(err, n, "%s", msg); }
    return -1;
}

/* audio/docs/modplayer.md §2.3. Detect by magic, never by file size. */
static int is_31_sample(const uint8_t *magic, int *chans)
{
    static const struct { const char *tag; int ch; } tags[] = {
        {"M.K.", 4}, {"M!K!", 4}, {"M&K!", 4}, {"N.T.", 4},
        {"4CHN", 4}, {"FLT4", 4},
        {"6CHN", 6}, {"8CHN", 8}, {"FLT8", 8}, {"CD81", 8}, {"OKTA", 8},
    };
    for (size_t i = 0; i < sizeof tags / sizeof tags[0]; i++) {
        if (memcmp(magic, tags[i].tag, 4) == 0) { *chans = tags[i].ch; return 1; }
    }
    return 0;
}

/* A 15-sample Soundtracker module has no magic at all, so it can only be
 * identified by ruling everything else out and then finding that the header
 * makes sense.
 *
 * The names are NOT tested for printability. Genuine Soundtracker files carry
 * junk in the unused tail of a name field -- editor leftovers, high-bit
 * characters from a non-ASCII keymap -- and a printable-only rule sends real
 * 15-sample modules to "unrecognised format". The structure has to carry the
 * whole decision instead: volumes in range, a usable song length, an order
 * table of real pattern numbers, and enough file behind them to hold the
 * patterns those numbers name. */
static int plausible_15(const uint8_t *f, size_t len)
{
    unsigned maxpat = 0;

    if (len < HDR15) { return 0; }
    for (unsigned i = 0; i < 15u; i++) {
        const uint8_t *h = f + 20u + i * 30u;
        if (h[25] > 64u) { return 0; }          /* volume                   */
    }
    if (f[470] == 0 || f[470] > 128u) { return 0; }  /* song length         */
    for (unsigned i = 0; i < 128u; i++) {
        if (f[472u + i] > 127u) { return 0; }
        if (f[472u + i] > maxpat) { maxpat = f[472u + i]; }
    }
    if (HDR15 + (size_t)(maxpat + 1u) * 1024u > len) { return 0; }
    return 1;
}

int mod_load(mod_song *s, card_t *c, const char *path, char *err, size_t errlen)
{
    FILE *f = NULL;
    uint8_t *raw = NULL;
    long fsize;
    size_t got;
    unsigned nsamples, hdr, order_at, len_at;
    int chans = 4;
    int rc = -1;

    memset(s, 0, sizeof *s);

    f = fopen(path, "rb");
    if (!f) { return fail(err, errlen, "cannot open file"); }
    if (fseek(f, 0, SEEK_END) != 0) { goto done_io; }
    fsize = ftell(f);
    if (fsize < (long)HDR15) { fail(err, errlen, "file too short to be a module"); goto done; }
    rewind(f);

    /* §4.1 says stream sample data rather than buffering the file. This is the
     * host reference, where reading the file whole costs nothing and keeps the
     * loader auditable; the 6309 loader must stream, and the only difference is
     * where the bytes come from in step 5 below. */
    raw = malloc((size_t)fsize);
    if (!raw) { fail(err, errlen, "out of memory"); goto done; }
    got = fread(raw, 1, (size_t)fsize, f);
    if (got != (size_t)fsize) { fail(err, errlen, "short read"); goto done; }

    if ((size_t)fsize >= HDR31 && is_31_sample(raw + 1080, &chans)) {
        if (chans != 4) { fail(err, errlen, "6/8-channel module: audio.md §11.2 mode is unbuilt"); goto done; }
        nsamples = 31; hdr = HDR31; order_at = 952; len_at = 950;
    } else if (plausible_15(raw, (size_t)fsize)) {
        nsamples = 15; hdr = HDR15; order_at = 472; len_at = 470;
    } else {
        fail(err, errlen, "unrecognised format (no known magic, and not a 15-sample module)");
        goto done;
    }

    memcpy(s->title, raw, 20);
    s->title[20] = 0;

    s->songlength = raw[len_at];
    if (s->songlength == 0 || s->songlength > 128u) {
        fail(err, errlen, "bad song length"); goto done;
    }
    memcpy(s->order, raw + order_at, 128);

    /* §2.1: pattern count is 1 + max over the WHOLE 128-entry table, not just
     * the first songlength entries. Getting this wrong shifts every sample by a
     * multiple of 1 KB, which is the most common loader bug there is. */
    {
        unsigned maxpat = 0;
        for (unsigned i = 0; i < 128u; i++) {
            if (s->order[i] > 127u) { fail(err, errlen, "order entry > 127"); goto done; }
            if (s->order[i] > maxpat) { maxpat = s->order[i]; }
        }
        s->npatterns = (uint8_t)(maxpat + 1u);
    }

    {
        size_t pbytes = (size_t)s->npatterns * 1024u;
        if (hdr + pbytes > (size_t)fsize) {
            fail(err, errlen, "pattern data runs past end of file"); goto done;
        }
        s->patterns = malloc(pbytes);
        if (!s->patterns) { fail(err, errlen, "out of memory"); goto done; }
        memcpy(s->patterns, raw + hdr, pbytes);
    }

    /* ------------------------------------------------- sample relocation -- */

    /* §4.2: two bytes of silence at card address 0, and sample 0 aliased to
     * them, so "no sample given" and a corrupt pattern byte are both safe by
     * construction rather than by a test in the FIRQ path.
     *
     * Silence is $80, not $00: card RAM holds OFFSET BINARY (audio.md §6.1), and
     * $00 would be full-scale NEGATIVE — a DC step, not silence. This is the one
     * place the conversion has to be written out rather than XORed in a loop. */
    card_write(c, A_SPTR2, 0); card_write(c, A_SPTR1, 0); card_write(c, A_SPTR0, 0);
    card_write(c, A_SDATA, 0x80);
    card_write(c, A_SDATA, 0x80);

    s->sample_addr[0] = MOD_NULL_LOOP;
    s->sample_rep[0]  = MOD_NULL_LOOP;
    s->sample_len[0]  = 1;
    s->sample_replen[0] = 1;

    {
        size_t src = hdr + (size_t)s->npatterns * 1024u;
        uint32_t dst = MOD_SAMPLE_BASE;

        for (unsigned n = 1; n <= nsamples; n++) {
            const uint8_t *h = raw + 20u + (n - 1u) * 30u;
            uint32_t words   = be16(h + 22);
            uint32_t repoff  = be16(h + 26);
            uint32_t replen  = be16(h + 28);
            uint32_t bytes   = words * 2u;
            uint32_t avail;

            s->sample_ft[n]  = h[24] & 0x0Fu;   /* row index; do NOT sign-extend */
            s->sample_vol[n] = h[25] > 64u ? 64u : h[25];

            /* §4.6: truncated modules are common — a BBS transfer that stopped
             * short. Clamp and play on rather than rejecting; that is the
             * difference between playing 98 % of the corpus and 90 %. */
            avail = (src < (size_t)fsize) ? (uint32_t)((size_t)fsize - src) : 0u;
            if (bytes > avail) { bytes = avail; s->truncated = 1; }

            /* §4.7: the bound is the RAM that is POPULATED, not the 512 KB of
             * footprints. Checking the footprint accepts a module the card
             * cannot hold and leaves the channel fetching unwritten SRAM at
             * 28 kHz. Reject, loudly. */
            if (dst + bytes > c->sram_bytes) {
                if (err && errlen) {
                    snprintf(err, errlen,
                             "sample data needs %lu KB, card has %lu KB (modplayer.md §4.7)",
                             (unsigned long)((dst + bytes + 1023u) / 1024u),
                             (unsigned long)(c->sram_bytes / 1024u));
                }
                goto done;
            }

            s->sample_addr[n] = dst;
            s->sample_len[n]  = (uint16_t)(bytes / 2u);

            for (uint32_t i = 0; i < bytes; i++) {
                /* One SDATA store per byte, and the byte is converted on the
                 * way: the card's sample converter is unsigned-coded, so card
                 * RAM holds OFFSET BINARY and silence is $80
                 * (audio.md §6.1, modplayer.md §4.2). The loader is where the
                 * flip happens -- audio.md §16 item 27, decided -- so the .mod
                 * converter must NOT also do it; twice is none. On the 6309 it
                 * is an in-place LDD/EORD #$8080/STD pass over each sector
                 * buffer before the TFM, two bytes per instruction; modplayer.md
                 * §4.4 costs it. It is the only transformation the sample stream
                 * gets. */
                card_write(c, A_SDATA, (uint8_t)(raw[src + i] ^ 0x80u));
            }

            /* §4.2: replen <= 1 word means "no loop", and the idiom is to point
             * the loop at the silent word rather than to stop the channel —
             * because Paula has no stop, and neither does this card. */
            /* §2.2: the original 15-sample Soundtracker stores the repeat
             * OFFSET in bytes -- the one field in the format that is not in
             * words. Doubling it puts the loop past the end of most samples,
             * where the branch below then silences them outright. Every
             * 31-sample descendant stores words, and is unambiguous. */
            repoff = (nsamples == 15u) ? (repoff & ~1u) : repoff * 2u;

            if (replen <= 1u || repoff >= bytes) {
                s->sample_rep[n] = MOD_NULL_LOOP;
                s->sample_replen[n] = 1;
            } else {
                uint32_t rb = repoff;
                if (rb + replen * 2u > bytes) { replen = (bytes - rb) / 2u; }
                s->sample_rep[n] = dst + rb;
                s->sample_replen[n] = (uint16_t)(replen ? replen : 1u);
            }

            src += bytes;
            dst += bytes;
        }
        s->sample_bytes = dst - MOD_SAMPLE_BASE;
    }

    rc = 0;
    goto done;

done_io:
    fail(err, errlen, "seek failed");
done:
    if (rc != 0) { free(s->patterns); s->patterns = NULL; }
    free(raw);
    if (f) { fclose(f); }
    return rc;
}

void mod_free(mod_song *s)
{
    free(s->patterns);
    s->patterns = NULL;
}
