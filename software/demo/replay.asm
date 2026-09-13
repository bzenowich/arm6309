*******************************************************************************
* replay.asm -- the module loader and the ProTracker replayer, in 6809.
*
* audio/docs/modplayer.md is the specification and audio/refplayer/mod_replay.c
* is the contract: "structured to be transliterated into 6309 assembly", and
* every card access in it goes through w() so that "the register trace is the
* contract that the 6309 port has to reproduce". This is that transliteration,
* routine for routine and in the same order, so a diff of the two traces names
* the routine that disagrees. Where the C has a comment explaining a
* ProTracker behaviour, the routine here says which C function it is and does
* not repeat the argument.
*
* ⚠ IT IS 6809, NOT 6309 NATIVE MODE. The core in the simulation's socket is
* a 6809E (hardware/vendor/mc6809), so nothing here uses a 6309 instruction.
* modplayer.md 7's cycle budget is a native-mode estimate and this is slower.
*
* Included by demo.asm, which supplies DP = $FF (every card register is a
* direct-page address) and the RAM this file's variables live in.
*******************************************************************************

*------------------------------------------------------------- the card -------
* audio.md 9.2, as audio/refplayer/card.h numbers them.
R_AIDX    EQU     $0
R_ADATA   EQU     $1
R_ADMACON EQU     $2
R_AINTENA EQU     $3
R_AINTREQ EQU     $4
R_ACTRL   EQU     $5
R_SPTR2   EQU     $6
R_SPTR1   EQU     $7
R_SPTR0   EQU     $8
R_SDATA   EQU     $9
R_TIMER1  EQU     $B
R_TIMER0  EQU     $C
ASTAT     EQU     $FF4A           b6 host access busy - poll before every write
SDATA     EQU     $FF49

ACTRL_LED    EQU  $01
ACTRL_BYPASS EQU  $02
ACTRL_TIMER  EQU  $40
ACTRL_ENABLE EQU  $80
AINT_TIMER   EQU  $10

ST_LC2    EQU     0               the state file, per channel (card.h)
ST_PER1   EQU     5
ST_VOL    EQU     7

PER_MIN   EQU     113
PER_MAX   EQU     856

*----------------------------------------------------------- the song image --
* modplayer.md 3. One 12-byte entry per sample, entry 0 the null sample.
S_ADDR    EQU     0               3 bytes, card-RAM byte address
S_LEN     EQU     3               2, WORDS, verbatim
S_REP     EQU     5               3, card-RAM byte address
S_RLEN    EQU     8               2, WORDS
S_VOL     EQU     10
S_FT      EQU     11
S_SIZE    EQU     12

* mod_chan, one 40-byte record per channel, addressed through U.
C_SMP     EQU     0
C_PER     EQU     1               2
C_OPER    EQU     3               2  last PER written
C_TGT     EQU     5               2  3xx target
C_VOL     EQU     7
C_OVOL    EQU     8
C_FT      EQU     9
C_CMD     EQU     10
C_PAR     EQU     11
C_PSPD    EQU     12
C_VCMD    EQU     13
C_VPOS    EQU     14
C_TCMD    EQU     15
C_TPOS    EQU     16
C_WAVE    EQU     17
C_OFFM    EQU     18
C_LROW    EQU     19
C_LCNT    EQU     20
C_GLIS    EQU     21
C_SLC     EQU     22              3
C_SLEN    EQU     25              2
C_ND      EQU     27
C_NDA     EQU     28
C_NDS     EQU     29
C_NDP     EQU     30              2
C_TRIG    EQU     32
C_TLC     EQU     33              3
C_TLEN    EQU     36              2
C_N16     EQU     38              channel * 16, the state-file index base
C_SIZE    EQU     40

MODHDR    EQU     1084            31-sample header length
MODMAGIC  EQU     1080

*******************************************************************************
* wr - write A to card register B, once ASTAT b6 says the card will take it.
*
* ⚠ THE POLL IS NOT OPTIONAL. audio.md 9.2: "while b6 = 1 no access is taken:
* a write is lost", and the measured worst case is 63 slots, 2.2 us - which is
* about one store on this CPU, so back-to-back stores would lose one sometimes.
* Preserves every register but CC.
*******************************************************************************
wr      pshs    x,b             one frame: PSHS/PULS order is fixed, not textual
wr1     ldb     <ASTAT
        bitb    #$40
        bne     wr1
        ldb     ,s
        ldx     #$FF40
        abx
        sta     ,x
        puls    b,x,pc

* One entry per register, so a call site reads like mod_replay.c's w(p, A_x, v).
wAIDX   pshs    b
        ldb     #R_AIDX
        bra     wrb
wADATA  pshs    b
        ldb     #R_ADATA
wrb     lbsr    wr
        puls    b,pc

*******************************************************************************
* volcode - Paula's 0..64 to the volume converter's code: 4v, 64 -> $FF.
* mod_replay.c vol_code(). A in, A out.
*******************************************************************************
volcode cmpa    #64
        bhs     vc1
        lsla
        lsla
        rts
vc1     lda     #$FF
        rts

*******************************************************************************
* set_per - U = channel, D = period. Writes only if it changed.
*******************************************************************************
set_per cmpd    C_OPER,u
        beq     sp9
        std     C_OPER,u
        pshs    a
        lda     C_N16,u
        adda    #ST_PER1
        lbsr    wAIDX
        puls    a
        lbsr    wADATA
        tfr     b,a
        lbsr    wADATA
sp9     rts

*******************************************************************************
* set_vol - U = channel, A = volume 0..64.
*******************************************************************************
set_vol cmpa    C_OVOL,u
        beq     sv9
        sta     C_OVOL,u
        pshs    a
        lda     C_N16,u
        adda    #ST_VOL
        lbsr    wAIDX
        lda     ,s
        lbsr    volcode
        lbsr    wADATA
        puls    a
sv9     rts

*******************************************************************************
* set_tempo - TIMER := 1773447 / bpm, from tables.inc's tempotab.
*******************************************************************************
set_tempo
        pshs    x,d
        ldb     bpm
        clra
        lslb
        rola
        ldx     #tempotab
        leax    d,x
        lda     ,x
        ldb     #R_TIMER1
        lbsr    wr
        lda     1,x
        ldb     #R_TIMER0
        lbsr    wr
        puls    d,x,pc

*******************************************************************************
* clamp_per - D (signed) into PER_MIN..PER_MAX. clamp_vol - D (signed) into 0..64,
* result in A.
*******************************************************************************
clamp_per
        cmpd    #PER_MIN
        bge     cp1
        ldd     #PER_MIN
        rts
cp1     cmpd    #PER_MAX
        ble     cp2
        ldd     #PER_MAX
cp2     rts

clamp_vol
        tsta
        bmi     cv0
        cmpd    #64
        ble     cv1
        lda     #64
        rts
cv0     clra
        rts
cv1     tfr     b,a
        rts

*******************************************************************************
* rowptr - X := ptab row for finetune B (0..15). Preserves D? no: clobbers D.
*******************************************************************************
rowptr  lda     #72
        mul
        ldx     #ptab
        leax    d,x
        rts

*******************************************************************************
* ptabat - B = finetune, A = index. Returns D = ptab[ft][index].
*******************************************************************************
ptabat  pshs    x,a
        andb    #$0F
        bsr     rowptr
        puls    a
        lsla
        leax    a,x             A <= 70, so the signed offset is safe
        ldd     ,x
        puls    x,pc

*******************************************************************************
* smpent - B = sample number. Returns X = its song-image entry.
*******************************************************************************
smpent  lda     #S_SIZE
        mul
        ldx     #smptab
        leax    d,x
        rts

*******************************************************************************
* queue_trigger - U = channel, D = period. mod_replay.c queue_trigger().
*******************************************************************************
queue_trigger
        pshs    x,y,d
        std     C_PER,u
        ldb     C_SMP,u
        bsr     smpent
        ldd     S_ADDR,x        lc -> t24a (3 bytes)
        std     t24a
        lda     S_ADDR+2,x
        sta     t24a+2
        clr     t24b            bytes = len * 2 -> t24b
        ldd     S_LEN,x
        lslb
        rola
        rol     t24b
        std     t24b+1
        lda     C_CMD,u
        cmpa    #9
        bne     qt3
* 9xx: off = offset_mem * 256 = (0, offm, 0)
        lda     t24b            off >= bytes ?
        bne     qt1             bytes >= 65536 > any off
        lda     t24b+1
        cmpa    C_OFFM,u
        bhi     qt1             bytes' middle byte above offm: bytes > off
        blo     qt0             below: off > bytes
        tst     t24b+2          equal middle bytes: bytes > off iff low byte != 0
        bne     qt1
qt0     clr     t24b            bytes = 2
        clr     t24b+1
        lda     #2
        sta     t24b+2
        bra     qt3
qt1     lda     t24a+1          lc += off
        adda    C_OFFM,u
        sta     t24a+1
        bcc     qt2
        inc     t24a
qt2     lda     t24b+1          bytes -= off
        suba    C_OFFM,u
        sta     t24b+1
        bcc     qt3
        dec     t24b
qt3     lda     C_WAVE,u
        bita    #$04
        bne     qt4
        clr     C_VPOS,u
qt4     bita    #$40
        bne     qt5
        clr     C_TPOS,u
qt5     ldd     t24a            start_lc = lc
        std     C_SLC,u
        lda     t24a+2
        sta     C_SLC+2,u
        lda     t24b            start_len = bytes / 2, or 1
        lsra
        ldd     t24b+1
        rora
        rorb
        cmpd    #0
        bne     qt6
        ldb     #1
qt6     std     C_SLEN,u
        std     C_TLEN,u
        ldd     C_SLC,u
        std     C_TLC,u
        lda     C_SLC+2,u
        sta     C_TLC+2,u
        lda     #1
        sta     C_TRIG,u
        puls    d,x,y,pc

* ⚠ The `lsra` above shifts t24b's top byte for its carry alone; the result
* in A is discarded when `ldd` reloads it. bytes <= 131,070, so bytes / 2 is
* the 16-bit value (t24b:t24b+1:t24b+2) >> 1 with t24b's bit 0 shifted in.

*******************************************************************************
* queue_retrigger - U = channel. mod_replay.c queue_retrigger().
*******************************************************************************
queue_retrigger
        pshs    d
        lda     #1
        sta     C_TRIG,u
        ldd     C_SLC,u
        std     C_TLC,u
        lda     C_SLC+2,u
        sta     C_TLC+2,u
        ldd     C_SLEN,u
        std     C_TLEN,u
        puls    d,pc

*******************************************************************************
* commit_triggers - modplayer.md 5.3, "the one sequence that must be exactly
* right". mod_replay.c commit_triggers().
*******************************************************************************
commit_triggers
        pshs    x,y,u,d
        clr     tmpb            the mask
        ldu     #chans
        lda     #1              A = this channel's bit
ct1     tst     C_TRIG,u
        beq     ct2
        tfr     a,b
        orb     tmpb
        stb     tmpb
ct2     leau    C_SIZE,u
        lsla
        cmpa    #$10
        bne     ct1
        tst     tmpb
        lbeq    ct9
* 1. one-shot pointer, full length, this note's period and volume
        ldu     #chans
ct3     tst     C_TRIG,u
        beq     ct4
        lda     C_N16,u
        adda    #ST_LC2
        lbsr    wAIDX
        lda     C_TLC,u
        anda    #$07
        lbsr    wADATA
        lda     C_TLC+1,u
        lbsr    wADATA
        lda     C_TLC+2,u
        lbsr    wADATA
        lda     C_TLEN,u
        lbsr    wADATA
        lda     C_TLEN+1,u
        lbsr    wADATA
        lda     C_PER,u
        lbsr    wADATA
        lda     C_PER+1,u
        lbsr    wADATA
        lda     C_VOL,u
        lbsr    volcode
        lbsr    wADATA
        ldd     C_PER,u
        std     C_OPER,u
        lda     C_VOL,u
        sta     C_OVOL,u
ct4     leau    C_SIZE,u
        cmpu    #chans+4*C_SIZE
        bne     ct3
* 2. stop, then start
        lda     tmpb
        ldb     #R_ADMACON
        lbsr    wr
        ora     #$80
        lbsr    wr
* 3. the loop point, in the same tick
        ldu     #chans
ct5     tst     C_TRIG,u
        beq     ct6
        ldb     C_SMP,u
        lbsr    smpent
        lda     C_N16,u
        adda    #ST_LC2
        lbsr    wAIDX
        lda     S_REP,x
        anda    #$07
        lbsr    wADATA
        lda     S_REP+1,x
        lbsr    wADATA
        lda     S_REP+2,x
        lbsr    wADATA
        lda     S_RLEN,x
        lbsr    wADATA
        lda     S_RLEN+1,x
        lbsr    wADATA
        clr     C_TRIG,u
ct6     leau    C_SIZE,u
        cmpu    #chans+4*C_SIZE
        bne     ct5
ct9     puls    d,x,y,u,pc

*******************************************************************************
* volslide - U = channel, A = param. mod_replay.c volslide(): "up" wins.
*******************************************************************************
volslide
        pshs    d
        tfr     a,b
        lsra
        lsra
        lsra
        lsra
        beq     vs1
        tfr     a,b             D = volume + up
        clra
        addb    C_VOL,u
        adca    #0
        bra     vs2
vs1     andb    #$0F            D = volume - down
        stb     tmpb
        clra
        ldb     C_VOL,u
        subb    tmpb
        sbca    #0
vs2     lbsr    clamp_vol
        sta     C_VOL,u
        puls    d,pc

*******************************************************************************
* vibrato - U = channel, D = the period to modulate. Returns D.
* mod_replay.c vibrato() with depth_div 128, on C_WAVE's low nibble.
*******************************************************************************
vibrato pshs    x
        std     tmpw
        lda     C_VPOS,u
        lsra
        lsra
        anda    #$1F
        tfr     a,b             B = slot
        lda     C_WAVE,u
        anda    #$03
        bne     vb1
        ldx     #vibsine
        lda     b,x             sine
        bra     vb3
vb1     cmpa    #1
        bne     vb2
        lslb                    ramp: slot * 8
        lslb
        lslb
        tfr     b,a
        tst     C_VPOS,u
        bpl     vb3
        coma                    255 - amp
        bra     vb3
vb2     lda     #255
vb3     ldb     C_VCMD,u
        andb    #$0F
        mul                     D = amp * depth
        lslb                    A = D >> 7
        rola
        tfr     a,b
        clra
        std     tmpw2
        ldd     tmpw
        tst     C_VPOS,u
        bmi     vb4
        addd    tmpw2
        bra     vb5
vb4     subd    tmpw2
vb5     pshs    d
        lda     C_VCMD,u
        lsra
        lsra
        lsra
        lsra
        lsla
        lsla
        adda    C_VPOS,u
        sta     C_VPOS,u
        puls    d,x,pc

*******************************************************************************
* tone_porta - U = channel. mod_replay.c tone_porta().
*******************************************************************************
tone_porta
        pshs    d
        ldd     C_TGT,u
        beq     tp9
        ldd     C_PER,u
        cmpd    C_TGT,u
        beq     tp3
        bhi     tp2
        addb    C_PSPD,u        period < target: up by speed, to at most target
        adca    #0
        cmpd    C_TGT,u
        bls     tp1
        ldd     C_TGT,u
tp1     std     C_PER,u
        bra     tp3
tp2     subb    C_PSPD,u        period > target: down, to at least target
        sbca    #0
        cmpd    C_TGT,u
        bge     tp1
        ldd     C_TGT,u
        bra     tp1
tp3     tst     C_GLIS,u
        beq     tp9
        ldb     C_FT,u
        stb     tmpb3
        ldd     C_PER,u
        lbsr    pidx_d
        tfr     b,a
        ldb     C_FT,u
        lbsr    ptabat
        std     C_PER,u
tp9     puls    d,pc

*******************************************************************************
* e_tick0 - U = channel, row period in `note`. mod_replay.c e_tick0().
*******************************************************************************
e_tick0 pshs    d,x
        lda     C_PAR,u
        tfr     a,b
        andb    #$0F            B = x
        lsra
        lsra
        lsra
        lsra                    A = sub
        cmpa    #$0
        bne     et1
        lda     actrl           E0x - the LED filter, unless bypassed
        bita    #ACTRL_BYPASS
        lbne    et9
        bitb    #1
        beq     et0a
        anda    #$FE            LED off
        bra     et0b
et0a    ora     #ACTRL_LED
et0b    sta     actrl
        ldb     #R_ACTRL
        lbsr    wr
        lbra    et9
et1     cmpa    #$1
        bne     et2
        stb     tmpb            E1x - fine slide up
        ldd     C_PER,u
        subb    tmpb
        sbca    #0
        lbsr    clamp_per
        std     C_PER,u
        lbra    et9
et2     cmpa    #$2
        bne     et3
        clra                    E2x - fine slide down
        addd    C_PER,u
        lbsr    clamp_per
        std     C_PER,u
        lbra    et9
et3     cmpa    #$3
        bne     et4
        stb     C_GLIS,u
        lbra    et9
et4     cmpa    #$4
        bne     et6
        lda     C_WAVE,u
        anda    #$F0
        stb     tmpb
        ora     tmpb
        sta     C_WAVE,u
        lbra    et9
et6     cmpa    #$6
        bne     et7
        tstb
        bne     et6a
        lda     row             E60 - loop start
        sta     C_LROW,u
        lbra    et9
et6a    tst     C_LCNT,u
        bne     et6b
        stb     C_LCNT,u
        bra     et6c
et6b    dec     C_LCNT,u
et6c    tst     C_LCNT,u
        lbeq    et9
        lda     #1
        sta     lp_p
        lda     C_LROW,u
        sta     lp_tgt
        lbra    et9
et7     cmpa    #$7
        bne     et9x
        lda     C_WAVE,u
        anda    #$0F
        lslb
        lslb
        lslb
        lslb
        stb     tmpb
        ora     tmpb
        sta     C_WAVE,u
        lbra    et9
et9x    cmpa    #$9
        bne     eta
        tstb                    E9x at tick 0: retrigger if there is no note
        lbeq    et9
        ldd     note
        lbne    et9
        lbsr    queue_retrigger
        lbra    et9
eta     cmpa    #$A
        bne     etb
        clra
        addb    C_VOL,u
        adca    #0
        lbsr    clamp_vol
        sta     C_VOL,u
        bra     et9
etb     cmpa    #$B
        bne     etc
        stb     tmpb
        clra
        ldb     C_VOL,u
        subb    tmpb
        sbca    #0
        lbsr    clamp_vol
        sta     C_VOL,u
        bra     et9
etc     cmpa    #$C
        bne     ete
        tstb                    EC0 cuts at tick 0
        bne     et9
        clr     C_VOL,u
        bra     et9
ete     cmpa    #$E
        bne     et9
        stb     pdelay
et9     puls    d,x,pc

*******************************************************************************
* e_per_tick - U = channel. mod_replay.c e_per_tick().
*******************************************************************************
e_per_tick
        pshs    d
        lda     C_PAR,u
        tfr     a,b
        andb    #$0F
        lsra
        lsra
        lsra
        lsra
        cmpa    #$9
        bne     ep2
        tstb                    E9x: retrigger when tick % x == 0
        beq     ep9
        stb     tmpb
        lda     tick            tick % x == 0 ?
ep1     cmpa    tmpb
        blo     ep1a
        suba    tmpb
        bra     ep1
ep1a    tsta
        bne     ep9
        lbsr    queue_retrigger
        bra     ep9
ep2     cmpa    #$C
        bne     ep3
        cmpb    tick            ECx: cut on tick x
        bne     ep9
        clr     C_VOL,u
        bra     ep9
ep3     cmpa    #$D
        bne     ep9
        tst     C_NDA,u         EDx: the delayed note
        beq     ep9
        lda     tick
        cmpa    C_ND,u
        bne     ep9
        clr     C_NDA,u
        lda     C_NDS,u
        sta     C_SMP,u
        ldd     C_NDP,u
        lbsr    queue_trigger
ep9     puls    d,pc

*******************************************************************************
* row_channel - U = channel, X = its 4-byte pattern cell.
* mod_replay.c row_channel().
*******************************************************************************
row_channel
        pshs    d,x,y
        lda     ,x              sm = (c0 & $F0) | (c2 >> 4)
        anda    #$F0
        sta     tmpb
        lda     2,x
        lsra
        lsra
        lsra
        lsra
        ora     tmpb
        sta     rsm
        lda     ,x              per = (c0 & $0F) << 8 | c1
        anda    #$0F
        ldb     1,x
        std     note
        lda     2,x
        anda    #$0F
        sta     C_CMD,u
        lda     3,x
        sta     C_PAR,u
        clr     C_NDA,u
        clr     C_NDP,u
        clr     C_NDP+1,u
        lda     C_CMD,u         9xx takes its memory whenever it is seen
        cmpa    #9
        bne     rc1
        ldb     C_PAR,u
        beq     rc1
        stb     C_OFFM,u
rc1     ldb     rsm
        beq     rc2
        cmpb    #32
        blo     rc1a
        clrb
rc1a    stb     C_SMP,u         a sample number: instrument and volume, no retrigger
        lbsr    smpent
        lda     S_VOL,x
        sta     C_VOL,u
        lda     S_FT,x
        sta     C_FT,u
rc2     lda     C_CMD,u         E5x, before the lookup
        cmpa    #$E
        bne     rc3
        lda     C_PAR,u
        lsra
        lsra
        lsra
        lsra
        cmpa    #$5
        bne     rc3
        lda     C_PAR,u
        anda    #$0F
        sta     C_FT,u
rc3     ldd     note
        lbeq    rc8
        ldb     C_FT,u          finetuned(): period in D, finetune in tmpb2
        stb     tmpb2
        ldd     note
        lbsr    fin_d
        std     rfp
        lda     C_CMD,u
        cmpa    #3
        beq     rc4
        cmpa    #5
        bne     rc5
rc4     ldd     rfp             tone portamento: a destination, not a note
        std     C_TGT,u
        lda     C_CMD,u
        cmpa    #3
        bne     rc8
        lda     C_PAR,u
        beq     rc8
        sta     C_PSPD,u
        bra     rc8
rc5     cmpa    #$E
        bne     rc7
        lda     C_PAR,u
        lsra
        lsra
        lsra
        lsra
        cmpa    #$D
        bne     rc7
        lda     C_PAR,u         EDx: arm the delay
        anda    #$0F
        sta     C_ND,u
        lda     C_SMP,u
        sta     C_NDS,u
        ldd     rfp
        std     C_NDP,u
        lda     #1
        sta     C_NDA,u
        tst     C_ND,u
        bne     rc8
        clr     C_NDA,u
        ldd     rfp
        lbsr    queue_trigger
        bra     rc8
rc7     clr     C_TGT,u
        clr     C_TGT+1,u
        ldd     rfp
        lbsr    queue_trigger
* the command
rc8     lda     C_CMD,u
        cmpa    #$4
        bne     rc9
        lda     C_PAR,u
        anda    #$F0
        beq     rc8a
        ldb     C_VCMD,u
        andb    #$0F
        stb     tmpb
        ora     tmpb
        sta     C_VCMD,u
rc8a    lda     C_PAR,u
        anda    #$0F
        lbeq    rc99
        ldb     C_VCMD,u
        andb    #$F0
        stb     tmpb
        ora     tmpb
        sta     C_VCMD,u
        lbra    rc99
rc9     cmpa    #$7
        bne     rcb
        lda     C_PAR,u
        anda    #$F0
        beq     rc9a
        ldb     C_TCMD,u
        andb    #$0F
        stb     tmpb
        ora     tmpb
        sta     C_TCMD,u
rc9a    lda     C_PAR,u
        anda    #$0F
        lbeq    rc99
        ldb     C_TCMD,u
        andb    #$F0
        stb     tmpb
        ora     tmpb
        sta     C_TCMD,u
        lbra    rc99
rcb     cmpa    #$B
        bne     rcc
        lda     #1
        sta     jmp_p
        lda     C_PAR,u
        sta     jmp_pos
        lbra    rc99
rcc     cmpa    #$C
        bne     rcd
        lda     C_PAR,u         set volume, clamped to 64 (param is unsigned)
        cmpa    #64
        bls     rcc1
        lda     #64
rcc1    sta     C_VOL,u
        lbra    rc99
rcd     cmpa    #$D
        bne     rce
        lda     C_PAR,u         Dxx is DECIMAL
        lsra
        lsra
        lsra
        lsra
        ldb     #10
        mul
        stb     tmpb
        lda     C_PAR,u
        anda    #$0F
        adda    tmpb
        cmpa    #63
        bls     rcd1
        clra
rcd1    sta     brk_row
        lda     #1
        sta     brk_p
        bra     rc99
rce     cmpa    #$E
        bne     rcf
        lbsr    e_tick0
        bra     rc99
rcf     cmpa    #$F
        bne     rc99
        lda     C_PAR,u
        beq     rc99
        cmpa    #$20
        bhs     rcf1
        sta     speed
        bra     rc99
rcf1    sta     bpm
        lbsr    set_tempo
rc99    puls    d,x,y,pc

* fin_d - finetuned() with the period in D and the finetune in tmpb2.
fin_d   pshs    b
        ldb     tmpb2
        stb     tmpb3
        puls    b
        std     tmpw3
        pshs    x,y
        ldy     #ptab
        clrb
fd1     ldx     tmpw3
        cmpx    ,y++
        bhs     fd2
        incb
        cmpb    #36
        bne     fd1
        decb
fd2     tfr     b,a
        ldb     tmpb3
        lbsr    ptabat
        puls    x,y,pc

*******************************************************************************
* advance - modplayer.md 5.8. mod_replay.c advance(), less `visited`, which
* only sets a flag the demo never reads.
*******************************************************************************
advance tst     lp_p
        beq     ad1
        clr     lp_p            a loop beats an advance
        lda     lp_tgt
        sta     row
        clr     brk_p
        clr     jmp_p
        rts
ad1     inc     row
        tst     brk_p
        beq     ad2
        lda     brk_row
        sta     row
        inc     position
ad2     tst     jmp_p
        beq     ad3
        lda     jmp_pos
        sta     position
        tst     brk_p
        bne     ad3
        clr     row
ad3     clr     brk_p
        clr     jmp_p
        lda     row
        cmpa    #63
        bls     ad4
        clr     row
        inc     position
ad4     lda     position
        cmpa    songlen
        blo     ad5
        clr     position
ad5     rts

*******************************************************************************
* patrow - X := the current row's 16 bytes, through blocks 2 and 3.
*
* The file sits in ROM from MODPAGE, and a row is at 1084 + pattern*1024 +
* row*16 into it. Blocks 2 AND 3 are pointed at the page holding that offset
* and the next one, so a row that straddles an 8 KB boundary reads straight
* through. ⚠ Only this file writes map entries 2 and 3, and it does so from
* /FIRQ: nothing else in the demo may use them.
*******************************************************************************
patrow  pshs    d
        ldb     position
        ldx     #order
        lda     b,x             A = pattern number
        clr     t24a            off = pattern << 10
        clrb
        lsla
        rol     t24a
        lsla
        rol     t24a
        sta     t24a+1          middle byte: (p << 2) & $FF
        clr     t24a+2
        lda     row             plus row << 4
        clr     tmpb
        lsla
        rol     tmpb
        lsla
        rol     tmpb
        lsla
        rol     tmpb
        lsla
        rol     tmpb
        adda    #MODHDR&$FF     plus 1084, low byte
        sta     t24a+2
        lda     tmpb
        adca    #MODHDR/256
        adda    t24a+1
        sta     t24a+1
        bcc     pr1
        inc     t24a
pr1     lda     t24a+1          page = off >> 13
        lsra
        lsra
        lsra
        lsra
        lsra
        sta     tmpb
        lda     t24a
        lsla
        lsla
        lsla
        adda    tmpb
        adda    #MODPAGE
        sta     <MAPLO+2
        inca
        sta     <MAPLO+3
        lda     #$01
        sta     <MAPHI+2
        sta     <MAPHI+3
        lda     t24a+1
        anda    #$1F
        adda    #$40
        tfr     a,b
        lda     t24a+2
        exg     a,b
        tfr     d,x
        puls    d,pc

*******************************************************************************
* mod_tick - one /FIRQ, the whole replayer. mod_replay.c mod_tick().
*******************************************************************************
mod_tick
        clr     newrow
        tst     tick
        bne     mt0
        tst     pdelay
        bne     mt0
        inc     newrow
mt0     lda     #AINT_TIMER     clear the timer request: the sole /FIRQ source
        ldb     #R_AINTREQ
        lbsr    wr
        tst     newrow
        beq     mt2
* ---- a fresh row
        lbsr    patrow
        ldu     #chans
mt1     lbsr    row_channel
        leax    4,x
        leau    C_SIZE,u
        cmpu    #chans+4*C_SIZE
        bne     mt1
        lbra    mt8
* ---- a repeat (EEx) or an ordinary tick
mt2     tst     tick
        bne     mt4
        dec     pdelay
        ldu     #chans
mt3     lda     C_CMD,u         EDx re-arms on every repeat
        cmpa    #$E
        bne     mt3a
        lda     C_PAR,u
        anda    #$F0
        cmpa    #$D0
        bne     mt3a
        ldd     C_NDP,u
        beq     mt3a
        lda     C_PAR,u
        anda    #$0F
        sta     C_ND,u
        lda     #1
        sta     C_NDA,u
mt3a    leau    C_SIZE,u
        cmpu    #chans+4*C_SIZE
        bne     mt3
mt4     ldu     #chans
mt5     ldd     C_PER,u
        std     lper
        lda     C_VOL,u
        sta     lvol
        lda     C_CMD,u
        lbeq    fx0
        cmpa    #$1
        lbeq    fx1
        cmpa    #$2
        lbeq    fx2
        cmpa    #$3
        lbeq    fx3
        cmpa    #$4
        lbeq    fx4
        cmpa    #$5
        lbeq    fx5
        cmpa    #$6
        lbeq    fx6
        cmpa    #$7
        lbeq    fx7
        cmpa    #$A
        lbeq    fxa
        cmpa    #$E
        lbeq    fxe
        lbra    fx99
fx0     lda     C_PAR,u         arpeggio
        lbeq    fx99
        lda     tick
fx0a    cmpa    #3
        blo     fx0b
        suba    #3
        bra     fx0a
fx0b    clrb
        cmpa    #1
        bne     fx0c
        ldb     C_PAR,u
        lsrb
        lsrb
        lsrb
        lsrb
        bra     fx0d
fx0c    cmpa    #2
        bne     fx0d
        ldb     C_PAR,u
        andb    #$0F
fx0d    stb     tmpb4           add
        ldb     C_FT,u
        stb     tmpb3
        ldd     C_PER,u
        lbsr    pidx_d
        addb    tmpb4
        cmpb    #35
        bls     fx0e
        ldb     #35
fx0e    tfr     b,a
        ldb     C_FT,u
        lbsr    ptabat
        std     lper
        lbra    fx99
fx1     ldd     C_PER,u         portamento up
        subb    C_PAR,u
        sbca    #0
        lbsr    clamp_per
        std     C_PER,u
        std     lper
        lbra    fx99
fx2     clra                    portamento down
        ldb     C_PAR,u
        addd    C_PER,u
        lbsr    clamp_per
        std     C_PER,u
        std     lper
        lbra    fx99
fx3     lda     C_PAR,u         tone portamento: a new speed from any non-zero param
        beq     fx3a
        sta     C_PSPD,u
fx3a    lbsr    tone_porta
        ldd     C_PER,u
        std     lper
        lbra    fx99
fx4     ldd     lper
        lbsr    vibrato
        std     lper
        lbra    fx99
fx5     lbsr    tone_porta
        ldd     C_PER,u
        std     lper
        lda     C_PAR,u
        lbsr    volslide
        lda     C_VOL,u
        sta     lvol
        lbra    fx99
fx6     ldd     lper
        lbsr    vibrato
        std     lper
        lda     C_PAR,u
        lbsr    volslide
        lda     C_VOL,u
        sta     lvol
        lbra    fx99
fx7     lda     C_TPOS,u        tremolo
        lsra
        lsra
        anda    #$1F
        tfr     a,b             B = slot
        lda     C_WAVE,u
        lsra
        lsra
        lsra
        lsra
        anda    #$03
        bne     fx7a
        ldx     #vibsine
        lda     b,x
        bra     fx7c
fx7a    cmpa    #1
        bne     fx7b
        lslb
        lslb
        lslb
        tfr     b,a
        tst     C_TPOS,u
        bpl     fx7c
        coma
        bra     fx7c
fx7b    lda     #255
fx7c    ldb     C_TCMD,u
        andb    #$0F
        mul                     amp * depth / 64: A = D >> 6
        lslb
        rola
        lslb
        rola
        sta     tmpb
        clra
        ldb     C_VOL,u
        tst     C_TPOS,u
        bmi     fx7d
        addb    tmpb
        adca    #0
        bra     fx7e
fx7d    subb    tmpb
        sbca    #0
fx7e    lbsr    clamp_vol
        sta     lvol
        lda     C_TCMD,u
        lsra
        lsra
        lsra
        lsra
        lsla
        lsla
        adda    C_TPOS,u
        sta     C_TPOS,u
        lbra    fx99
fxa     lda     C_PAR,u
        lbsr    volslide
        lda     C_VOL,u
        sta     lvol
        bra     fx99
fxe     lbsr    e_per_tick
        ldd     C_PER,u
        std     lper
        lda     C_VOL,u
        sta     lvol
fx99    ldd     lper
        lbsr    set_per
        lda     lvol
        lbsr    set_vol
        leau    C_SIZE,u
        cmpu    #chans+4*C_SIZE
        lbne    mt5
* ---- both kinds
mt8     lbsr    commit_triggers
        tst     newrow
        beq     mt10
        ldu     #chans
mt9     ldd     C_PER,u         tick 0 writes the BASE period, unconditionally
        lbsr    set_per
        lda     C_VOL,u
        lbsr    set_vol
        leau    C_SIZE,u
        cmpu    #chans+4*C_SIZE
        bne     mt9
mt10    inc     tick
        lda     tick
        cmpa    speed
        blo     mt11
        clr     tick
        tst     pdelay
        bne     mt11
        lbsr    advance
mt11    rts

* pidx_d - period_index() with D = period and tmpb3 = finetune.
pidx_d  pshs    x,y,a
        std     tmpw3
        ldb     tmpb3
        andb    #$0F
        lbsr    rowptr
        tfr     x,y
        clrb
pd1     ldx     tmpw3
        cmpx    ,y++
        beq     pd9
        incb
        cmpb    #36
        bne     pd1
        leay    -72,y
        clrb
pd2     ldx     tmpw3
        cmpx    ,y++
        bhs     pd9
        incb
        cmpb    #36
        bne     pd2
        ldb     #35
pd9     puls    a,x,y,pc

*******************************************************************************
* mod_load - modplayer.md 4, mod_load.c: parse the file in ROM, relocate the
* samples into card RAM through SPTR/SDATA, and build the song image.
* Returns Z set on success; on failure A holds the reason.
*
* Uses block 0 as its window onto the file and nothing else.
*******************************************************************************
mod_load
* the header is in the file's first page
        lda     #MODPAGE
        sta     <MAPLO+0
        lda     #$01
        sta     <MAPHI+0
        ldx     #MODMAGIC
        ldd     ,x
        cmpd    #$4D2E          "M."
        bne     ml0
        ldd     2,x
        cmpd    #$4B2E          "M.K."
        beq     ml1
ml0     lda     #$E8            not a 31-sample 4-channel module
        rts
ml1     lda     950             song length
        beq     ml0
        cmpa    #128
        bhi     ml0
        sta     songlen
* order table, and the pattern count from ALL 128 entries (mod_load.c)
        ldx     #952
        ldy     #order
        clr     tmpb            max
        ldb     #128
ml2     lda     ,x+
        sta     ,y+
        cmpa    #127
        bhi     ml0
        cmpa    tmpb
        bls     ml3
        sta     tmpb
ml3     decb
        bne     ml2
        lda     tmpb
        inca
        sta     npat
* src = 1084 + npat * 1024 -> t24s
        clr     t24s
        lsla                    npat << 10: (npat >> 6, (npat << 2) & $FF, 0)
        rol     t24s
        lsla
        rol     t24s
        adda    #MODHDR/256
        sta     t24s+1
        bcc     ml4
        inc     t24s
ml4     lda     #MODHDR&$FF
        sta     t24s+2
* the null sample at card address 0: $80 $80, and entry 0 aliased to it
        clra
        ldb     #R_SPTR2
        lbsr    wr
        ldb     #R_SPTR1
        lbsr    wr
        ldb     #R_SPTR0
        lbsr    wr
        lda     #$80
        ldb     #R_SDATA
        lbsr    wr
        lbsr    wr
        ldx     #smptab
        ldb     #S_SIZE
ml5     clr     ,x+
        decb
        bne     ml5
        ldd     #1
        std     smptab+S_LEN
        std     smptab+S_RLEN
        clr     t24d            dst = 2
        clr     t24d+1
        lda     #2
        sta     t24d+2
* the 31 samples
        lda     #1
        sta     smpn
ml6     lda     #MODPAGE        the header page again: the upload moves block 0
        sta     <MAPLO+0
        ldb     smpn
        decb
        lda     #30
        mul
        addd    #20
        tfr     d,y             Y = this sample's 30-byte header
        ldb     smpn
        lbsr    smpent          X = its song-image entry
        lda     24,y
        anda    #$0F
        sta     S_FT,x
        lda     25,y
        cmpa    #64
        bls     ml7
        lda     #64
ml7     sta     S_VOL,x
        ldd     22,y            bytes = words * 2 -> t24b
        clr     t24b
        lslb
        rola
        rol     t24b
        std     t24b+1
        ldd     26,y
        std     repoff
        ldd     28,y
        std     replen
* clamp to what the file holds: avail = MODLEN - src
        lda     #MODLEN2
        ldb     #MODLEN/256
        stb     t24c+1
        sta     t24c
        lda     #MODLEN&$FF
        suba    t24s+2
        sta     t24c+2
        lda     t24c+1
        sbca    t24s+1
        sta     t24c+1
        lda     t24c
        sbca    t24s
        sta     t24c
        bcc     ml8
        clr     t24c            src past the end: nothing available
        clr     t24c+1
        clr     t24c+2
ml8     ldd     t24c            if bytes > avail, bytes = avail
        cmpd    t24b
        bhi     ml9
        blo     ml8a
        lda     t24c+2
        cmpa    t24b+2
        bhs     ml9
ml8a    ldd     t24c
        std     t24b
        lda     t24c+2
        sta     t24b+2
ml9     ldd     t24d            addr = dst
        std     S_ADDR,x
        lda     t24d+2
        sta     S_ADDR+2,x
        lda     t24b            len = bytes / 2
        lsra
        lda     t24b+1
        rora
        ldb     t24b+2
        rorb
        std     S_LEN,x
* upload `bytes` bytes from file offset src, flipped to offset binary
        pshs    x
        lbsr    upload
        puls    x
* the loop: repoff in words -> bytes
        ldd     repoff
        clr     t24r
        lslb
        rola
        rol     t24r
        std     t24r+1          t24r = repoff * 2
        ldd     replen
        cmpd    #1
        lbls    mlnull
        ldd     t24r            repoff >= bytes -> no loop
        cmpd    t24b
        lbhi    mlnull
        blo     ml10
        lda     t24r+2
        cmpa    t24b+2
        lbhs    mlnull
* rb + replen*2 > bytes ? replen = (bytes - rb) / 2
ml10    ldd     replen
        clr     t24c
        lslb
        rola
        rol     t24c
        addb    t24r+2
        stb     t24c+2
        adca    t24r+1
        sta     t24c+1
        lda     t24c
        adca    t24r
        sta     t24c            t24c = rb + replen*2
        ldd     t24c
        cmpd    t24b
        bhi     ml11
        blo     ml12
        lda     t24c+2
        cmpa    t24b+2
        bls     ml12
ml11    lda     t24b+2          replen = (bytes - rb) / 2
        suba    t24r+2
        sta     t24c+2
        lda     t24b+1
        sbca    t24r+1
        sta     t24c+1
        lda     t24b
        sbca    t24r
        lsra
        lda     t24c+1
        rora
        ldb     t24c+2
        rorb
        std     replen
ml12    ldd     replen
        bne     ml13
        ldb     #1
ml13    std     S_RLEN,x
        lda     t24d+2          rep = dst + rb
        adda    t24r+2
        sta     S_REP+2,x
        lda     t24d+1
        adca    t24r+1
        sta     S_REP+1,x
        lda     t24d
        adca    t24r
        sta     S_REP,x
        bra     ml14
mlnull  clr     S_REP,x
        clr     S_REP+1,x
        clr     S_REP+2,x
        ldd     #1
        std     S_RLEN,x
* src += bytes; dst += bytes
ml14    lda     t24s+2
        adda    t24b+2
        sta     t24s+2
        lda     t24s+1
        adca    t24b+1
        sta     t24s+1
        lda     t24s
        adca    t24b
        sta     t24s
        lda     t24d+2
        adda    t24b+2
        sta     t24d+2
        lda     t24d+1
        adca    t24b+1
        sta     t24d+1
        lda     t24d
        adca    t24b
        sta     t24d
        inc     smpn
        lda     smpn
        cmpa    #32
        lbne    ml6
        clra                    Z: success
        rts

*******************************************************************************
* upload - t24b bytes from file offset t24s into SDATA, each XOR $80.
* modplayer.md 4.2: card RAM is offset binary, the file is two's complement,
* and the loader is where the flip happens (audio.md 16 item 27).
*******************************************************************************
upload  ldd     t24b+1
        std     ucount
        lda     t24b
        sta     ucount2
        ldd     t24s            Y = logical address in block 0, A = page
        std     t24c
        lda     t24s+2
        sta     t24c+2
up1     lda     ucount2         done?
        bne     up2
        ldd     ucount
        beq     up9
up2     lda     t24c+1          page = off >> 13, window = off & $1FFF
        lsra
        lsra
        lsra
        lsra
        lsra
        sta     tmpb
        lda     t24c
        lsla
        lsla
        lsla
        adda    tmpb
        adda    #MODPAGE
        sta     <MAPLO+0
        lda     t24c+1
        anda    #$1F
        ldb     t24c+2
        tfr     d,y
up3     lda     ,y+
        eora    #$80
up4     ldb     <ASTAT          9.2's handshake, per byte
        bitb    #$40
        bne     up4
        sta     <SDATA
        ldd     ucount          count down (24 bits)
        subd    #1
        std     ucount
        bcc     up5
        dec     ucount2
up5     inc     t24c+2          offset up
        bne     up6
        inc     t24c+1
        bne     up6
        inc     t24c
up6     lda     ucount2
        bne     up7
        ldd     ucount
        beq     up9
up7     cmpy    #$2000          off the end of the window: re-map
        bne     up3
        bra     up2
up9     rts

*******************************************************************************
* mod_start - mod_replay.c mod_start(): reset, quiet, configure, enable, and
* play row 0 at once.
*******************************************************************************
mod_start
        ldx     #chans
        ldb     #4*C_SIZE
ms1     clr     ,x+
        decb
        bne     ms1
        clr     position
        clr     row
        clr     tick
        clr     pdelay
        clr     brk_p
        clr     brk_row
        clr     jmp_p
        clr     jmp_pos
        clr     lp_p
        clr     lp_tgt
        clr     actrl
        lda     #6
        sta     speed
        lda     #125
        sta     bpm
        ldu     #chans
        clra
ms2     sta     C_N16,u
        ldx     #$FFFF
        stx     C_OPER,u
        ldb     #$FF
        stb     C_OVOL,u
        ldx     #1
        stx     C_SLEN,u
        adda    #16
        leau    C_SIZE,u
        cmpu    #chans+4*C_SIZE
        bne     ms2
* quiet, then configured, then enabled
        ldu     #chans
ms3     lda     C_N16,u
        lbsr    wAIDX
        clra
        ldb     #11
ms4     lbsr    wADATA
        decb
        bne     ms4
        leau    C_SIZE,u
        cmpu    #chans+4*C_SIZE
        bne     ms3
        lda     #$0F
        ldb     #R_ADMACON
        lbsr    wr
        lda     #$3F
        ldb     #R_AINTREQ
        lbsr    wr
        lda     #$90            set: the timer request
        ldb     #R_AINTENA
        lbsr    wr
        lbsr    set_tempo
        lda     actrl
        ora     #$C0            master enable, tempo timer
        sta     actrl
        ldb     #R_ACTRL
        lbsr    wr
        lbra    mod_tick

vibsine FCB     0,24,49,74,97,120,141,161
        FCB     180,197,212,224,235,244,250,253
        FCB     255,253,250,244,235,224,212,197
        FCB     180,161,141,120,97,74,49,24
