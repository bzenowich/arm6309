/* sdtest.c - the storage card in machine.c, driven through its four
 * registers exactly as hardware/storage/docs/sdcard.md §9 tells a driver to.
 *
 *   sh software/emu/test/run-sdtest.sh        (the exit code is the answer)
 *
 * ⚠ THERE IS NO DRIVER YET, which is why this exists: the card model went in
 * before the NitrOS-9 RBF driver, and a model nothing drives is a model
 * nothing has checked.  This is not a driver and is not meant to become one -
 * it is §9.0's initialisation, §9.1's single-block read, §9.1.1's CMD18 run
 * and §9.2's write, written out literally so that each numbered step is a
 * claim.
 *
 * ⭐ IT INCLUDES machine.c ITSELF (with `main` renamed) rather than copying
 * the model, so there is one storage card in this repository's C and not two.
 * A test that has its own copy of the thing under test passes for ever.
 *
 * ⭐ WHAT IT IS REALLY FOR: the one-byte receive pipeline.  Every SDDATA read
 * returns the PREVIOUS burst's byte, so a block is correct only if the count
 * of accesses between the $FE token and the first data byte is exactly zero -
 * §9.1's "the same failure mode as §4 and equally silent".  Claim 3 reads a
 * block of known content byte for byte, and claim 3b PUTS the off-by-one
 * there on purpose and requires the block to shift, so that a model which
 * merely returned the right bytes for the wrong reason fails.
 */
#define main machine_main
#include "../machine.c"
#undef main

#include <stdarg.h>

/* ------------------------------------------------------------------ claims */
static int nclaims, nfail;
static void claim(int ok, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    nclaims++;
    if (!ok) nfail++;
    printf(ok ? "ok    " : "FAIL  ");
    vprintf(fmt, ap);
    putchar('\n');
    va_end(ap);
}

/* ---------------------------------------------------------- the bus, in E */
/* machine.c recomputes m->dots from the CPU's cycle count once an
 * instruction; here every access moves it by hand, which is the same thing a
 * 6809 does to it and is what makes SDSTAT b0 mean anything. */
static void ecyc(int n) { m->dots += (uint64_t)n * DOTS_PER_E; }

#define SDDATA 0
#define SDSTAT 1
#define SDCTRL 2
#define SDMOSI 3

/* §6.5: at the init rate a burst is 43 bus cycles and BUSY is polled before
 * every SDDATA access.  ⚠ Bounded, and the bound is itself a claim. */
static void wait_busy(const char *where)
{
    int n = 0;
    while (sd_read(SDSTAT) & 1) {
        ecyc(2);                                  /* LDA >SDSTAT ; BITA ; BNE */
        if (++n > 100000) { claim(0, "SDSTAT b0 cleared inside 100,000 polls (%s)", where); return; }
    }
}

/* One instruction's worth of separation after each access: a native-mode
 * `STA >SDDATA` is 4-5 cycles, which is §6.5's 3x margin over a 636 ns burst. */
static void put(uint8_t v)  { wait_busy("put");  sd_write(SDDATA, v); ecyc(5); }
static uint8_t get(void)    { wait_busy("get");  uint8_t v = sd_read(SDDATA); ecyc(5); return v; }
static void mosi(uint8_t v) { wait_busy("mosi"); sd_write(SDMOSI, v); ecyc(5); }
static void ctrl(uint8_t v) { wait_busy("ctrl"); sd_write(SDCTRL, v); ecyc(5); }

/* §9.0: every command is six SDDATA writes.  The two CRCs that matter are
 * hard-coded constants; everything else ships $01. */
static void command(int c, uint32_t arg, uint8_t crc)
{
    put((uint8_t)(0x40 | c));
    put((uint8_t)(arg >> 24)); put((uint8_t)(arg >> 16));
    put((uint8_t)(arg >> 8));  put((uint8_t)arg);
    put(crc);
}

/* §9.1 step 4 / §9.3: read until a byte != $FF appears, N_CR bounded. */
static int poll_ff_timeouts, r1_reads, token_reads;
static uint8_t poll_r1(void)
{
    for (int i = 0; i < 16; i++) { uint8_t v = get(); r1_reads = i + 1; if (v != 0xFF) return v; }
    poll_ff_timeouts++;
    return 0xFF;
}

/* §9.1 step 5: read until the $FE data token.  Returns 0 on timeout or an
 * error token, which §9.3 says must be decoded rather than waited through. */
static uint8_t poll_token(void)
{
    for (int i = 0; i < 2000; i++) {
        uint8_t v = get();
        token_reads = i + 1;
        if (v == 0xFE) return v;
        if (v != 0xFF) return v;                  /* $00-$1F is an error token */
    }
    return 0x00;
}

/* ------------------------------------------------------------ the sequences */
/* §9.0, steps 0-8.  `skip_mosi` is claim 2's negative control: leave out step
 * 1 and the '574's power-up $00 clocks 80 LOW bits at a card that wants DI
 * high for 74 of them (§6.4). */
static int init_card(int skip_mosi, int quiet)
{
    uint8_t r1, r7[4], ocr[4];
    int loops;

    ctrl(0x00);                                   /* 0. /CS high, init clock, no burst */
    if (!skip_mosi) mosi(0xFF);                   /* 1. DI high before any clock exists */
    for (int i = 0; i < 10; i++) (void)get();     /* 2. 80 clocks with /CS high */

    ctrl(0x01);                                   /* /CS low */
    r1 = 0xFF;
    for (int try = 0; try < 10 && r1 != 0x01; try++) {   /* 3. CMD0, retry to 10 */
        command(0, 0x00000000, 0x95);
        mosi(0xFF);
        r1 = poll_r1();
    }
    if (!quiet) claim(r1 == 0x01, "§9.0 step 3: CMD0 with CRC $95 answers R1 = $01, idle (got $%02X)", r1);
    if (r1 != 0x01) { ctrl(0x00); return 0; }

    command(8, 0x000001AA, 0x87);                 /* 4. CMD8 */
    mosi(0xFF);
    r1 = poll_r1();
    for (int i = 0; i < 4; i++) r7[i] = get();
    if (!quiet) {
        claim(r1 == 0x01, "§9.0 step 4: CMD8 answers R1 = $01 (got $%02X)", r1);
        claim(r7[0] == 0x00 && r7[1] == 0x00 && r7[2] == 0x01 && r7[3] == 0xAA,
              "§9.0 step 4: and R7's four bytes echo $01AA: %02X %02X %02X %02X",
              r7[0], r7[1], r7[2], r7[3]);
    }

    loops = 0;                                    /* 5. CMD55 + ACMD41, LOOPED */
    do {
        command(55, 0x00000000, 0x01); mosi(0xFF);
        r1 = poll_r1();
        if (!quiet && loops == 0)
            claim(r1 == 0x01, "§9.0 step 5: CMD55 answers R1 = $01 (got $%02X)", r1);
        command(41, 0x40000000, 0x01); mosi(0xFF);   /* HCS = 1 */
        r1 = poll_r1();
        loops++;
    } while (r1 == 0x01 && loops < 70);
    if (!quiet) {
        claim(r1 == 0x00, "§9.0 step 5: ACMD41 with HCS = 1 reaches R1 = $00 (got $%02X)", r1);
        claim(loops == SD_ACMD41_IDLE + 1,
              "§9.0 step 5: and it took %d passes, so a driver that does not LOOP fails", loops);
    }

    command(58, 0x00000000, 0x01);                /* 6. CMD58 READ_OCR */
    mosi(0xFF);
    r1 = poll_r1();
    for (int i = 0; i < 4; i++) ocr[i] = get();
    if (!quiet) {
        claim(r1 == 0x00, "§9.0 step 6: CMD58 answers R1 = $00 (got $%02X)", r1);
        claim((ocr[0] & 0x40) != 0,
              "§9.0 step 6: and the OCR's CCS (bit 30) is set - SDHC, block addressing: %02X %02X %02X %02X",
              ocr[0], ocr[1], ocr[2], ocr[3]);
    }

    mosi(0xFF);                                   /* 8. the rate change, with /CS high */
    ctrl(0x00);
    (void)get();
    ctrl(0x02);                                   /* b1: 12.588 MHz */
    (void)get();
    return 1;
}

/* §9.1, steps 1-8.  `gap` inserts that many extra SDDATA reads between the
 * token and the transfer - §9.1's "anything inserted in that gap that
 * triggers a burst destroys it and shifts the whole block by one". */
static int read_block(uint32_t blk, uint8_t *dst, uint8_t *crc_out, int gap)
{
    uint8_t r1, tok;
    ctrl(0x03);                                   /* 1. /CS low, fast clock */
    command(17, blk, 0x01);                       /* 2. CMD17, argument = the BLOCK */
    mosi(0xFF);                                   /* 3. DI high, and no burst consumed */
    r1 = poll_r1();                               /* 4. R1 */
    if (r1 != 0x00) { ctrl(0x02); return 0; }
    tok = poll_token();                           /* 5. the $FE token */
    if (tok != 0xFE) { ctrl(0x02); return 0; }
    for (int i = 0; i < gap; i++) (void)get();    /* the defect, on purpose */
    for (int i = 0; i < 512; i++) dst[i] = get(); /* 6. the block */
    crc_out[0] = get(); crc_out[1] = get();       /* 7. the CRC16 */
    ctrl(0x02);                                   /* 8. /CS high ... */
    (void)get();                                  /*    ... and eight idle clocks */
    return 1;
}

/* §9.2, steps 1-11. */
static int write_block(uint32_t blk, const uint8_t *src, uint8_t *tok_first, uint8_t *tok_second,
                       int *busy_reads)
{
    uint8_t r1, v;
    ctrl(0x03);                                   /* 1. /CS low */
    command(24, blk, 0x01);                       /* 2. CMD24 */
    mosi(0xFF);                                   /* 3. R1 */
    r1 = poll_r1();
    if (r1 != 0x00) { ctrl(0x02); return 0; }
    (void)get();                                  /* 4. one idle byte */
    put(0xFE);                                    /* 5. the start token */
    for (int i = 0; i < 512; i++) put(src[i]);    /* 6. the block */
    put(0xFF); put(0xFF);                         /* 7. the two CRC16 bytes */
    mosi(0xFF);                                   /* 8. the data-response token */
    *tok_first  = get();
    *tok_second = get();
    *busy_reads = 0;                              /* 9. the program busy */
    for (int i = 0; i < 20000; i++) { v = get(); (*busy_reads)++; if (v == 0xFF) break; }
    ctrl(0x02);                                   /* 10. /CS high, one idle read */
    (void)get();
    return 1;
}

/* ---------------------------------------------------------------- the image */
static char imgpath[1024];

static void fill(uint8_t *b, uint32_t blk)        /* a pattern the card cannot guess */
{
    for (int i = 0; i < 512; i++) b[i] = (uint8_t)(blk * 7 + i * 13 + (i >> 5));
}

static void image_write(uint32_t blk, const uint8_t *b)
{
    FILE *f = fopen(imgpath, "r+b");
    if (!f) { claim(0, "the image %s is writable", imgpath); return; }
    fseek(f, (long)blk * 512, SEEK_SET);
    if (fwrite(b, 1, 512, f) != 512) claim(0, "the image took a whole block");
    fclose(f);
}

static void image_read(uint32_t blk, uint8_t *b)
{
    FILE *f = fopen(imgpath, "rb");
    memset(b, 0, 512);
    if (!f) { claim(0, "the image %s is readable", imgpath); return; }
    fseek(f, (long)blk * 512, SEEK_SET);
    if (fread(b, 1, 512, f) != 512) clearerr(f);
    fclose(f);
}

/* ---------------------------------------------------------------------- run */
int main(int argc, char **argv)
{
    static M mm;
    static uint8_t want[512], got[512], other[512];
    uint8_t crc[2];
    const char *dir = argc > 1 ? argv[1] : ".";

    m = &mm;
    setvbuf(stdout, NULL, _IOLBF, 0);

    /* ---- 0. an empty socket, which is every other bench in this repository */
    unsetenv("SDIMG");
    sd_reset();
    claim((sd_read(SDSTAT) & 2) == 0, "no SDIMG: SDSTAT's CD reads 0 - the socket is empty");
    claim(sd_read(SDDATA) == 0x00, "no SDIMG: SDDATA reads $00, the '595's power-up value, as before this card existed");
    {
        int allff = 1;
        ctrl(0x01);
        command(0, 0x00000000, 0x95);
        mosi(0xFF);
        for (int i = 0; i < 16; i++) if (get() != 0xFF) allff = 0;
        claim(allff, "no SDIMG: CMD0 answers $FF for ever - every command fails cleanly and the machine boots");
        ctrl(0x00);
    }

    /* ---- the image: 64 blocks of known content, created by the model itself */
    snprintf(imgpath, sizeof imgpath, "%s/sd.img", dir);
    remove(imgpath);
    setenv("SDIMG", imgpath, 1);
    setenv("SDBLOCKS", "64", 1);
    sd_reset();
    claim(sd.present && sd.nblocks == 64,
          "SDIMG names a file that does not exist: the model creates it, 64 blocks (%ld)", sd.nblocks);
    claim((sd_read(SDSTAT) & 6) == 2, "SDSTAT: CD = 1 (a card is in the socket) and WP = 0");
    for (uint32_t b = 0; b < 64; b++) { fill(want, b); image_write(b, want); }

    /* ---- 1. §9.0's initialisation, in full */
    printf("-- §9.0 initialisation\n");
    claim(init_card(0, 0), "§9.0: the card initialised");
    claim(sd.power_ok && !sd.bad_powerup && sd.card_up,
          "§9.0: and the card counted its 74 power-up clocks (initclk %d) before CMD0", sd.initclk);
    /* ⭐ THE PIPELINE IN ONE NUMBER, and it is storage_tb.sv's claim verbatim:
     * the first read after the sixth command byte returns the byte the card
     * sent DURING it, two more are the model's N_CR, and the fourth is R1. A
     * '165 that loaded at the end of a burst instead of tracking the '574
     * would move R1 to the fifth - the defect that bench found on 2026-09-20. */
    claim(r1_reads == 4,
          "⭐ §6.2: R1 is the 4th read after the sixth command byte - receive off by one, transmit by none (%d)",
          r1_reads);
    claim(!sd.crc0_bad && !sd.crc8_bad, "§9.0: CMD0 shipped CRC $95 and CMD8 shipped $87");

    /* ---- 2. ⭐ the negative control: no §9.0 step 1, no card */
    printf("-- §6.4 the negative control: SDMOSI <- $FF omitted\n");
    {
        int allff = 1;
        sd_reset();
        claim(sd.hold == 0x00, "§6.4: the '574 powers up holding $00 on purpose - it has no clear input");
        init_card(1, 1);
        claim(!sd.power_ok && sd.bad_powerup,
              "§6.4: 80 clocks of a $00 hold register never reach SD's 74 with DI high (initclk %d)", sd.initclk);
        claim(!sd.card_up, "§6.4: so the card never enters SPI mode");
        ctrl(0x01);
        for (int t = 0; t < 10; t++) {
            command(0, 0x00000000, 0x95);
            mosi(0xFF);
            for (int i = 0; i < 16; i++) if (get() != 0xFF) allff = 0;
        }
        claim(allff, "⭐ §6.4: and CMD0 answers $FF for ever - ten retries, 160 reads, not one of them not-$FF");
        ctrl(0x00);
        poll_ff_timeouts = 0;      /* those N_CR timeouts were the point of the section */
    }

    /* ---- 3. §9.1's read, byte for byte */
    printf("-- §9.1 CMD17\n");
    sd_reset();
    claim(init_card(0, 1), "§9.1: a freshly initialised card");
    fill(want, 5);
    claim(read_block(5, got, crc, 0), "§9.1: CMD17 for block 5 answered R1 = $00 and the $FE token");
    {
        int first = -1;
        for (int i = 0; i < 512; i++) if (got[i] != want[i]) { first = i; break; }
        claim(first < 0, "⭐ §9.1 steps 3-8: all 512 bytes are the block's, in order (first difference %d)", first);
        claim(token_reads == SD_READ_LAT + 1,
              "§9.1 step 5: the $FE token is the %dth read after R1 - the card's N_AC, four byte times", token_reads);
        /* the CRC16 the card computed over what it sent */
        uint16_t c = 0;
        for (int i = 0; i < 512; i++) c = sd_crc16b(c, want[i]);
        claim(crc[0] == (uint8_t)(c >> 8) && crc[1] == (uint8_t)c,
              "§9.1 step 7: the two CRC16 bytes are the card's CRC over the block ($%02X%02X)", crc[0], crc[1]);
    }
    /* ⭐ 3b. the off-by-one, on purpose: one extra SDDATA read in the gap */
    {
        int shifted = 1;
        read_block(5, got, crc, 1);
        for (int i = 0; i < 511; i++) if (got[i] != want[i + 1]) { shifted = 0; break; }
        claim(shifted,
              "⭐ §9.1: ONE triggering access between the token and the transfer shifts the whole block by one"
              " - the silent defect the section is about");
    }
    claim(read_block(5, got, crc, 0) && memcmp(got, want, 512) == 0,
          "§9.1: and the next read is correct again, so the shift was the access and not the card");

    /* ---- 4. §9.2's write, and the file on disc */
    printf("-- §9.2 CMD24\n");
    {
        uint8_t t1, t2; int busy;
        for (int i = 0; i < 512; i++) want[i] = (uint8_t)(0xA5 ^ (i * 3) ^ (i >> 4));
        claim(write_block(9, want, &t1, &t2, &busy), "§9.2: CMD24 for block 9 answered R1 = $00");
        claim(t1 == 0xFF,
              "⛔ §9.2 step 8's ONE read returns $FF: the pipeline puts the data-response token on the NEXT read");
        claim((t2 & 0x1F) == 0x05, "§9.2 step 8: and that read is the token, $05 accepted (got $%02X)", t2);
        claim(busy == SD_PROG_BYTES + 1,
              "§9.2 step 9: the card held DO low for %d reads and then released it", busy - 1);
        claim(read_block(9, got, crc, 0) && memcmp(got, want, 512) == 0,
              "§9.2: CMD17 reads back every byte CMD24 wrote");
        image_read(9, other);
        claim(memcmp(other, want, 512) == 0, "§9.2: and the file on disc holds the block");
        image_read(8, other); fill(want, 8);
        claim(memcmp(other, want, 512) == 0, "§9.2: and block 8, its neighbour, is untouched");
    }

    /* ---- 5. §9.1.1's CMD18 run, then CMD12 */
    printf("-- §9.1.1 CMD18 and CMD12\n");
    {
        uint8_t r1, tok, v;
        int ok = 1, busy = 0;
        uint8_t stuff_ff;
        ctrl(0x03);
        command(18, 20, 0x01);
        mosi(0xFF);
        r1 = poll_r1();
        claim(r1 == 0x00, "§9.1.1 step 3: CMD18 answers R1 = $00 (got $%02X)", r1);
        for (uint32_t n = 0; n < 3; n++) {
            tok = poll_token();
            if (tok != 0xFE) { ok = 0; break; }
            for (int i = 0; i < 512; i++) got[i] = get();
            (void)get(); (void)get();                 /* the CRC16 */
            fill(want, 20 + n);
            if (memcmp(got, want, 512) != 0) { ok = 0; break; }
        }
        claim(ok, "⭐ §9.1.1 step 4: three consecutive blocks, 20-22, each preceded by its own $FE token, all correct");
        command(12, 0x00000000, 0x01);                /* 5. STOP_TRANSMISSION */
        mosi(0xFF);
        /* ⚠ 5a's "discard ONE stuff byte" is one read, and it is the right
         * COUNT for the wrong reason: what the '595 is holding here is the
         * data byte the card was still STREAMING when the sixth command byte
         * landed, and CMD12's own stuffing byte is one of the $FFs the poll
         * below walks through.  storage_tb.sv records the same thing. */
        stuff_ff = get();
        claim(stuff_ff != 0xFF,
              "§9.1.1 step 5a: the first read after CMD12 is the in-flight stream byte ($%02X), discarded", stuff_ff);
        v = poll_r1();
        claim(v == 0x00, "§9.1.1 step 5b: CMD12's R1 is $00, past the stuffing byte (got $%02X)", v);
        for (int i = 0; i < 1000; i++) { busy++; if (get() == 0xFF) break; }
        claim(busy > 1 && busy < 10, "§9.1.1 step 5c: R1b's busy phase ended after %d reads", busy);
        ctrl(0x02); (void)get();                      /* 6. /CS high, one idle read */
        /* and the card is out of the stream: an ordinary command answers again */
        ctrl(0x03);
        command(13, 0x00000000, 0x01);
        mosi(0xFF);
        v = poll_r1();
        {
            uint8_t v2 = get();
            claim(v == 0x00 && v2 == 0x00,
                  "§9.2 step 11: CMD13 SEND_STATUS answers two $00 bytes, so CMD12 really stopped the stream"
                  " (got $%02X $%02X)", v, v2);
        }
        ctrl(0x02); (void)get();
    }

    /* ---- 6. §6.3/§6.5: SDSTAT b0, at both rates, and the lockout */
    printf("-- §6.3 SDSTAT b0 and §6.5 the lockout\n");
    {
        long drop0, burst0;
        uint8_t dup_a, dup_b;

        /* the fast clock: 8 x 2 dots, plus up to one for the first falling edge */
        ctrl(0x03);
        wait_busy("rate");
        sd_write(SDDATA, 0xFF);
        claim((sd_read(SDSTAT) & 1) == 1, "§6.3: at 12.588 MHz SDSTAT b0 is set the instant the access ends");
        m->dots += 15;
        claim((sd_read(SDSTAT) & 1) == 1, "§6.3: still set 15 dots later - a burst is 16, LONGER than a bus cycle");
        m->dots += 40;
        claim((sd_read(SDSTAT) & 1) == 0, "§6.3: and clear 40 dots after that (636 ns in all)");

        /* the init clock: 8 x 64 dots, plus up to 64 waiting for that edge */
        ctrl(0x01);
        wait_busy("rate");
        sd_write(SDDATA, 0xFF);
        claim((sd_read(SDSTAT) & 1) == 1, "§6.3: at 393 kHz SDSTAT b0 is set at once - sdbus ORs TRIGP into it,"
                                          " so the wait for the clock edge is inside the busy window");
        m->dots += 200;
        claim((sd_read(SDSTAT) & 1) == 1, "§6.3: and still set 200 CLK25 ticks later");
        m->dots += 500;
        claim((sd_read(SDSTAT) & 1) == 0, "§6.3: clear by 700 - 512 dots of burst, 20.4 us");

        /* §6.5: a trigger during a burst is DROPPED, and the read duplicates */
        ctrl(0x03);
        wait_busy("lockout");
        burst0 = sd.bursts;
        dup_a = sd_read(SDDATA);                    /* starts a burst; returns the last byte */
        drop0 = sd.dropped;
        dup_b = sd_read(SDDATA);                    /* mid-burst: dropped */
        claim(sd.dropped == drop0 + 1, "§6.5: an SDDATA access during a burst is DROPPED, not queued");
        claim(dup_b == dup_a, "§6.5: and the read still returns the '595's current byte - a duplicate, not a lost byte");
        m->dots += 64;
        claim((sd_read(SDSTAT) & 1) == 0 && sd.bursts == burst0 + 1,
              "§6.5: one burst ran its eight clocks and the dropped access started no second one"
              " (%ld bursts, %ld dropped)", sd.bursts - burst0, sd.dropped - drop0);

        /* §6.2: SDMOSI loads the hold register WITHOUT a burst */
        ctrl(0x03);
        wait_busy("sdmosi");
        { long b0 = sd.bursts;
          sd_write(SDMOSI, 0x5A);
          claim(sd.bursts == b0 && (sd_read(SDSTAT) & 1) == 0 && sd.hold == 0x5A,
                "§6.2: SDMOSI loads the hold register and triggers nothing"); }
        /* §6.2: SDDATA's write loads it too, and the burst sends THAT byte */
        { long b0 = sd.bursts;
          sd_write(SDDATA, 0xC3);
          claim(sd.bursts == b0 + 1 && sd.pend_mosi == 0xC3,
                "§6.2: a write to SDDATA latches the '574 before the burst it triggered, so the burst sends it"); }
        m->dots += 128; sd_settle();

        /* §6.2/§6.4: SDCTRL b7's soft reset clears a burst in flight */
        ctrl(0x01);
        wait_busy("soft");
        sd_write(SDDATA, 0xFF);
        claim((sd_read(SDSTAT) & 1) == 1, "§6.4: a burst is running at the init rate");
        sd_write(SDCTRL, 0x81);
        claim((sd_read(SDSTAT) & 1) == 0, "§6.4: SDCTRL b7 clears BUSY and the '163 with it");
        claim(poll_ff_timeouts == 0, "no poll in this run hit its N_CR bound");
    }

    ctrl(0x00);
    printf("%d claims, %d failed        (image %s)\n", nclaims, nfail, imgpath);
    return nfail != 0;
}
