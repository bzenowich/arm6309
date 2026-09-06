/* Model of the arm6309 4-channel PCM sound card — audio/docs/audio.md.
 *
 * This is a REGISTER-LEVEL model, not a mixer. Everything the replayer does
 * goes through card_write()/card_read() at the offsets audio/docs/audio.md §9.2
 * defines, so the replayer in mod_replay.c is a direct transliteration of the
 * 6309 assembly that will eventually replace it, and the register trace of one
 * can be diffed against the other. That is the whole reason audio/docs/audio.md §12.5
 * says to freeze the register map before building either card.
 *
 * Time advances one COLOUR CLOCK per card_step() — 3,546,895 Hz, the Amiga PAL
 * reference (audio/docs/audio.md §4.1). Nothing here is resampled, interpolated or
 * approximated: a channel's sample changes on the exact colour clock its period
 * counter fires, which is what audio/docs/audio.md §6.2 builds the hardware to do.
 *
 * Deliberately NOT modelled: the 8-slot walk, the pipeline stages, and the
 * deferred queue (audio/docs/audio.md §3). Those are how the hardware finds the time
 * to do this work, not what the work is. The one place slot timing is
 * observable to software is the DMACON-enable latch, which audio/docs/audio.md §16
 * item 13 requires to be bounded at 4 colour clocks; §5.3 of audio/docs/modplayer.md
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
    A_AINTREQ = 0x4,  /* read pending; b7=1 sets, b7=0 clears named bits     */
    A_ACTRL   = 0x5,
    A_SPTR2   = 0x6,  /* sample pointer, bits 18..16                         */
    A_SPTR1   = 0x7,  /* bits 15..8                                          */
    A_SPTR0   = 0x8,  /* bits 7..0                                           */
    A_SDATA   = 0x9,  /* sample RAM at SPTR, post-increment                  */
    A_ASTAT   = 0xA,  /* read only                                           */
    A_TIMER1  = 0xB,  /* tempo reload, bits 15..8                            */
    A_TIMER0  = 0xC   /* bits 7..0                                           */
    /* $D..$F are reserved and read 0 — they were LIDX/LDATA, the volume-LUT
     * load path, deleted with the table itself. See the NOTE below. */
};

/* NOTE — where the volume went, and why VOL is seven bits.
 *
 * audio/docs/audio.md §6.1 has specified three different volume paths, and this
 * model has implemented two of them. Worth recording, because the register map
 * carries the scar:
 *
 *   1. A 32K x 8 lookup addressed {curve, VOL[5:0], SAMP[7:0]}. One bit short:
 *      Paula's volume is 0..64, which needs SEVEN bits, and a 6-bit field
 *      silently clamps every channel to 63/64 of its intended level. Writing
 *      this model is what found it.
 *   2. {VOL[6:0], SAMP[7:0]} -> 12-bit offset binary, host-loaded through a
 *      LIDX/LDATA pointer/data pair at registers $D..$F: 65,536 bytes and about
 *      94 ms of TFM at boot. Correct, and the curve became table content.
 *   3. No table at all. The card cascades two halves of an AD7528: the sample
 *      byte drives one multiplying DAC, whose output is the REFERENCE of a
 *      second whose code is the volume. The multiply happens in the analogue
 *      domain, so the product is not quantised at all -- better than the 12-bit
 *      table -- and the SRAM pair, the boot upload and the $D..$F registers all
 *      go away. That is what this model implements.
 *
 * VOL stays 0..64 and the card shifts it left two to make an 8-bit attenuator
 * code (saturating at 255, so the top step is 0.4 % narrow). ACTRL_RAWVOL makes
 * VOL the 8-bit code directly, which is where a non-Paula volume curve now
 * lives: in the host's software, not in the card's SRAM.
 *
 * Samples are stored in card RAM as OFFSET BINARY -- the converter is
 * unsigned-coded, and the loader converts once (mod_load.c, modplayer.md §4.2).
 * Silence is $80, not $00.
 */
enum {
    ACTRL_LED     = 0x01,  /* + 2-pole LED filter (audio.md §7)   */
    ACTRL_BYPASS  = 0x02,  /* bypass all filtering                */
    ACTRL_NTSC    = 0x04,  /* NTSC colour clock                   */
    ACTRL_RAWVOL  = 0x08,  /* VOL is a raw 8-bit attenuator code  */
    ACTRL_8CHAN   = 0x10,  /* audio.md §11.2 — not modelled       */
    ACTRL_PAN     = 0x20,  /* audio.md §11.1 — not modelled       */
    ACTRL_TIMER   = 0x40,  /* tempo timer runs; 0 stops it        */
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

/* audio/docs/audio.md §16 item 13: enable-triggered work jumps the deferred queue
 * and completes within four colour clocks. modplayer.md §5.3 drops
 * ProTracker's delay loop on the strength of exactly this bound, so the model
 * enforces it rather than assuming it. */
#define CARD_ENABLE_LATENCY 4

typedef struct {
    uint32_t lc;        /* shadow location, byte address, 19 bits          */
    uint32_t len;       /* shadow length, in words                         */
    uint16_t per;
    uint8_t  vol;       /* 0..64, or an 8-bit code under ACTRL_RAWVOL      */
    uint8_t  att;
    uint8_t  pan;

    uint32_t ptr;       /* live pointer                                    */
    uint32_t cnt;       /* live count, in BYTES                            */
    uint16_t next;      /* colour-clock count at which this channel ticks  */
    uint8_t  samp;      /* card byte held to the DAC: OFFSET BINARY, $80=0 */
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

    uint8_t  state[CARD_STATE_BYTES];
    uint8_t *sram;                      /* CARD_SRAM_BYTES, caller-owned   */
    uint32_t sram_bytes;                /* how much is actually populated  */

    /* Model-only bookkeeping, not hardware state. */
    uint64_t cc;            /* colour clocks since reset                   */
    uint32_t oob_reads;     /* sample fetches past populated RAM           */
} card_t;

void    card_reset(card_t *c, uint8_t *sram, uint32_t sram_bytes);
void    card_write(card_t *c, uint8_t reg, uint8_t val);
uint8_t card_read(card_t *c, uint8_t reg);
void    card_step(card_t *c);
int     card_firq(const card_t *c);

/* One channel's contribution, as (signed sample) x (8-bit volume code): the
 * product the cascaded converter pair forms in the analogue domain (§6.1).
 * +-32640 full scale, and it is not quantised on the card. */
int     card_chan_out(const card_t *c, unsigned n);

/* L and R at the two summing nodes: the analogue sum of two channels' currents
 * (§6.2). No truncation anywhere -- the sum is a wire into a virtual ground. */
void    card_dac(const card_t *c, int *l, int *r);

long    card_colour_clock(const card_t *c);

#endif /* ARM6309_CARD_H */
