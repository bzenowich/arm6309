/* Model of the arm6309 4-channel PCM sound card — docs/audio.md.
 *
 * This is a REGISTER-LEVEL model, not a mixer. Everything the replayer does
 * goes through card_write()/card_read() at the offsets docs/audio.md §9.2
 * defines, so the replayer in mod_replay.c is a direct transliteration of the
 * 6309 assembly that will eventually replace it, and the register trace of one
 * can be diffed against the other. That is the whole reason docs/audio.md §12.5
 * says to freeze the register map before building either card.
 *
 * Time advances one COLOUR CLOCK per card_step() — 3,546,895 Hz, the Amiga PAL
 * reference (docs/audio.md §4.1). Nothing here is resampled, interpolated or
 * approximated: a channel's sample changes on the exact colour clock its period
 * counter fires, which is what docs/audio.md §6.2 builds the hardware to do.
 *
 * Deliberately NOT modelled: the 8-slot walk, the pipeline stages, and the
 * deferred queue (docs/audio.md §3). Those are how the hardware finds the time
 * to do this work, not what the work is. The one place slot timing is
 * observable to software is the DMACON-enable latch, which docs/audio.md §16
 * item 13 requires to be bounded at 4 colour clocks; §5.3 of docs/modplayer.md
 * depends on that bound and card_step() enforces it (see CARD_ENABLE_LATENCY).
 */
#ifndef ARM6309_CARD_H
#define ARM6309_CARD_H

#include <stdint.h>
#include <stddef.h>

/* ---------------------------------------------------------------- clocks -- */

#define CARD_CC_PAL      3546895L   /* colour clock, 28.37516 MHz / 8        */
#define CARD_CC_NTSC     3579545L   /* colour clock, 28.63636 MHz / 8        */
#define CARD_CIA_DIV     5          /* tempo timer prescale (audio.md §8.2)  */

/* ------------------------------------------------- direct I/O window §9.2 -- */

enum {
    A_AIDX    = 0x0,  /* state-file index; auto-increments through ADATA     */
    A_ADATA   = 0x1,  /* state-file data, post-increment                     */
    A_ADMACON = 0x2,  /* b3..0 channel DMA enable; b7 = set/clear            */
    A_AINTENA = 0x3,  /* b5..0 interrupt enable;   b7 = set/clear            */
    A_AINTREQ = 0x4,  /* read pending; write b7=0 clears the named bits      */
    A_ACTRL   = 0x5,
    A_SPTR2   = 0x6,  /* sample pointer, bits 18..16                         */
    A_SPTR1   = 0x7,  /* bits 15..8                                          */
    A_SPTR0   = 0x8,  /* bits 7..0                                           */
    A_SDATA   = 0x9,  /* sample RAM at SPTR, post-increment                  */
    A_ASTAT   = 0xA,  /* read only                                           */
    A_TIMER1  = 0xB,  /* tempo reload, bits 15..8                            */
    A_TIMER0  = 0xC,  /* bits 7..0                                           */
    A_LIDX1   = 0xD,  /* volume-LUT load index, bits 15..8   (see NOTE)      */
    A_LIDX0   = 0xE,  /* bits 7..0                                           */
    A_LDATA   = 0xF   /* volume-LUT byte at LIDX, post-increment             */
};

/* NOTE — LIDX/LDATA and the 7-bit volume.
 *
 * docs/audio.md §6.1 as first written addressed the volume LUT with
 * {curve, VOL[5:0], SAMP[7:0]}. That is one bit short: Paula's volume is 0..64,
 * which needs SEVEN bits, and a 6-bit field silently clamps every channel to
 * 63/64 of its intended level. Writing this model is what found it.
 *
 * The fix costs nothing and is strictly better: address the LUT with
 * {VOL[6:0], SAMP[7:0]} — exactly the 15 address bits of a 32K x 8 pair — and
 * make the table HOST-LOADABLE through LIDX/LDATA instead of selecting a curve
 * with an address line. The curve then stops being a hardware feature and
 * becomes table content: linear/Paula-exact, logarithmic, soft-clip, or a
 * per-machine calibration, all for the same zero packages. Entries for VOL
 * 65..127 are unreachable in Paula-compatible use and simply repeat VOL 64.
 *
 * Loading all 65,536 bytes costs one TFM burst, ~94 ms at 2.098 MHz, once at
 * boot. ACTRL bit 7 keeps the card quiet until it is done.
 */

enum {
    ACTRL_LED     = 0x01,  /* + 5-pole LED filter (audio.md §7)   */
    ACTRL_BYPASS  = 0x02,  /* bypass all filtering                */
    ACTRL_NTSC    = 0x04,  /* NTSC colour clock                   */
    ACTRL_8CHAN   = 0x08,  /* audio.md §11.2 — not modelled       */
    ACTRL_PAN     = 0x20,  /* audio.md §11.1 — not modelled       */
    ACTRL_ENABLE  = 0x80   /* master enable; 0 at reset           */
};

enum {
    AINT_CH0    = 0x01,
    AINT_TIMER  = 0x10,
    AINT_FIFO   = 0x20
};

/* ------------------------------------------------- state file, §9.3 ------- */
/* AIDX = channel * 16 + offset. Multi-byte fields are big-endian, matching
 * both the 6309 and the .mod file. */
enum {
    ST_LC2 = 0,  ST_LC1 = 1,  ST_LC0 = 2,   /* 19-bit byte address  */
    ST_LEN1 = 3, ST_LEN0 = 4,               /* length, in WORDS     */
    ST_PER1 = 5, ST_PER0 = 6,               /* period, colour clocks*/
    ST_VOL  = 7,                            /* 0..64                */
    ST_DAT  = 8,                            /* direct sample write  */
    ST_ATT  = 9,                            /* b0 period, b1 volume */
    ST_PAN  = 10,
    ST_PTR2 = 11, ST_PTR1 = 12, ST_PTR0 = 13, /* read-only          */
    ST_CNT1 = 14, ST_CNT0 = 15                /* read-only, WORDS   */
};

#define CARD_STATE_BYTES   64
#define CARD_SRAM_BYTES    (512u * 1024u)   /* footprint max, audio.md §5   */
#define CARD_LUT_ENTRIES   32768u           /* {VOL[6:0], SAMP[7:0]}        */

/* docs/audio.md §16 item 13: enable-triggered work jumps the deferred queue
 * and completes within four colour clocks. modplayer.md §5.3 drops
 * ProTracker's delay loop on the strength of exactly this bound, so the model
 * enforces it rather than assuming it. */
#define CARD_ENABLE_LATENCY 4

typedef struct {
    uint32_t lc;        /* shadow location, byte address, 19 bits          */
    uint32_t len;       /* shadow length, in words                         */
    uint16_t per;
    uint8_t  vol;       /* 0..127, clamped to 64 by the LUT contents       */
    uint8_t  att;
    uint8_t  pan;

    uint32_t ptr;       /* live pointer                                    */
    uint32_t cnt;       /* live count, in BYTES                            */
    uint16_t next;      /* colour-clock count at which this channel ticks  */
    int8_t   samp;      /* the byte currently held out to the DAC          */
    uint8_t  dmaen;
    uint8_t  start_in;  /* colour clocks until an enable latches; 0 = idle */
} card_chan;

typedef struct {
    card_chan ch[4];

    uint16_t ccnt;          /* free-running colour-clock counter, §4.2     */
    uint8_t  pre5;          /* CIA prescale, §8.2                          */
    uint16_t ciacnt;
    uint16_t cianext;
    uint16_t timer;         /* reload; 0 means 65536                       */

    uint8_t  ctrl;
    uint8_t  intreq;
    uint8_t  intena;
    uint8_t  aidx;
    uint32_t sptr;
    uint16_t lidx;

    uint8_t  state[CARD_STATE_BYTES];
    uint8_t *sram;                      /* CARD_SRAM_BYTES, caller-owned   */
    uint32_t sram_bytes;                /* how much is actually populated  */
    int16_t  lut[CARD_LUT_ENTRIES];     /* 12-bit signed, §6.1             */

    /* Model-only bookkeeping, not hardware state. */
    uint64_t cc;            /* colour clocks since reset                   */
    uint32_t oob_reads;     /* sample fetches past populated RAM           */
} card_t;

void    card_reset(card_t *c, uint8_t *sram, uint32_t sram_bytes);
void    card_write(card_t *c, uint8_t reg, uint8_t val);
uint8_t card_read(card_t *c, uint8_t reg);
void    card_step(card_t *c);
int     card_firq(const card_t *c);

/* L and R as the 12-bit signed codes actually presented to the two DACs:
 * the 13-bit channel sum with its bottom bit dropped (§6.2, §6.3). */
void    card_dac(const card_t *c, int *l, int *r);

/* Write the Paula-linear volume table through LIDX/LDATA, exactly as boot code
 * would. entry = SAMP * min(VOL,64) / 4, giving 12-bit signed. */
void    card_load_linear_lut(card_t *c);

long    card_colour_clock(const card_t *c);

#endif /* ARM6309_CARD_H */
