*******************************************************************************
* calib.asm -- measure, on the whole machine, the card behaviour the show's
* model (tools/showmodel.py) and the emulator (emu/) assume.
*
*   sh software/archive/demo/bench/run-calib.sh        (~10 min: demo_tb on this ROM)
*
* Each phase stores its number in $C208 - demo_tb's "camera record" field -
* so every recorded frame says which phase drew it, and tools/calib.py reads
* the answers off the frames:
*
*   0  a display list GO'd as soon as VBLANK falls
*   1  the same list GO'd once HBLANK has also fallen, inside line 0
*        list: MOVE HSCROLL 3 at once; after 10 WAITs HSCROLL 16; after 100
*        HSCROLL 272; after 200 LUT[26] := $F800; after 300 LUT[26] back;
*        after 350 HSCROLL 0.  Where each lands is the answer.
*   2  static VMODE 11: a sprite-mode glyph, a mask-mode glyph and a
*      span-solid rectangle chained with WADV 01; $C20A/$C225 hold four bytes
*      read back through VDATA
*   3  VMODE 00 with VSCROLL 300: which ring rows a line-doubled frame shows
*******************************************************************************

MAPHI   EQU     $FF90
MAPLO   EQU     $FFA0
SIMPORT EQU     $FF2F
IRQVEC  EQU     $C004
FIRQVEC EQU     $C006

VCTRL   EQU     $FF60
VSCROLL EQU     $FF61
VSCRLH  EQU     $FF62
HSCROLL EQU     $FF63
HSCRLH  EQU     $FF64
SPANLEN EQU     $FF65
WFG     EQU     $FF66
WBG     EQU     $FF67
WPTR0   EQU     $FF68
WPTR1   EQU     $FF69
WPTR2   EQU     $FF6A
BCTRL   EQU     $FF6E
PIDX    EQU     $FF70
PDATL   EQU     $FF71
PDATH   EQU     $FF72
VSTAT   EQU     $FF73
WADV    EQU     $FF74
VDATA   EQU     $FF75

phase   EQU     $C208
rd1     EQU     $C20A
rd2     EQU     $C225
cnt     EQU     $C300
row     EQU     $C302
col     EQU     $C304
tmp     EQU     $C306

        ORG     $8000
        FCC     "6309"
        JMP     start

        SETDP   $FF
start   orcc    #$50
        lds     #$E000
        lda     #$FF
        tfr     a,dp
        clr     <VCTRL
        ldd     #$FFFF
        std     phase
        ldx     #irqh
        stx     IRQVEC
        stx     FIRQVEC
        lda     #$80
        sta     <SIMPORT

* palette: entry i = RGB332(i), as demo.asm
        clr     <PIDX
        clrb
pal1    tfr     b,a
        lsra
        lsra
        lsra
        lsra
        lsra
        ldx     #r5tab
        lda     a,x
        sta     tmp
        tfr     b,a
        lsra
        lsra
        anda    #7
        ldx     #g6tab
        lda     a,x
        sta     tmp+1
        lsra
        lsra
        lsra
        ora     tmp
        sta     tmp
        lda     tmp+1
        anda    #7
        lsla
        lsla
        lsla
        lsla
        lsla
        sta     tmp+1
        tfr     b,a
        anda    #3
        ldx     #b5tab
        lda     a,x
        ora     tmp+1
        sta     <PDATL
        lda     tmp
        sta     <PDATH
pal2    lda     <VSTAT          graphics.md 13.1: the commit waits for the line's HLOAD
        bita    #$02
        bne     pal2
        incb
        bne     pal1

* stripes: ring column block c (8 px, c = 0..127) is index c + 16 on rows 0-479.
* One WPTR load per block, then 480 span-solid triggers chained by WADV 01.
        lda     #$10            WMODE 10, display off
        sta     <VCTRL
        lda     #7
        sta     <SPANLEN
        lda     #1
        sta     <WADV
        clr     col
st1     lbsr    idle
        lda     col
        adda    #16
        sta     <WFG
        ldd     #0
        std     cnt
        lbsr    idle
        lda     col
        ldb     #8
        mul                     D = c * 8
        stb     <WPTR0
        sta     <WPTR1
        clr     <WPTR2
st2     lbsr    idle
        sta     <VDATA
        ldd     cnt
        addd    #1
        std     cnt
        cmpd    #480
        bne     st2
        inc     col
        lda     col
        cmpa    #128
        bne     st1
        lbsr    idle
        clr     <WADV

* the two lists, identical, at ring rows 500 and 501
        ldx     #$D000          build it in RAM first
        lbsr    mklist
        ldd     #500*4          WPTR = 500 << 10 = $7D000
        lbsr    setrow
        lbsr    putlist
        ldd     #501*4
        lbsr    setrow
        lbsr    putlist

        clr     <HSCROLL
        clr     <HSCRLH
        clr     <VSCROLL
        clr     <VSCRLH
        lda     #$C3            display, IRQ enable, VMODE 11
        sta     <VCTRL
        lda     #$81
        sta     <SIMPORT

* phases 0 and 1, alternating, ten frames each
        ldd     #20
        std     cnt
ph1     lbsr    vbrise
        lbsr    idle
        ldd     cnt
        bitb    #1
        bne     ph2
        ldd     #500*4
        lbsr    setrow
        clra
        clrb
        std     phase
        lbsr    vbfall
        bra     ph3
ph2     ldd     #501*4
        lbsr    setrow
        ldd     #1
        std     phase
        lbsr    vbfall
ph2a    lda     <VSTAT          ... and HBLANK
        bita    #$20
        bne     ph2a
ph3     lda     #1
        sta     <BCTRL          GO
ph4     lda     <VSTAT
        bita    #$10
        bne     ph4
        ldd     cnt
        subd    #1
        std     cnt
        bne     ph1

* phase 2: glyphs, a chained rectangle, and four bytes read back
        lbsr    vbrise
        ldd     #$FFFF
        std     phase
        clr     <HSCROLL
        clr     <HSCRLH
        lbsr    idle
        lda     #1
        sta     <WADV
* sprite glyph at row 400, column 100 - white where the mask is 1
        lda     #$DB            WMODE 11
        sta     <VCTRL
        lda     #$FF
        sta     <WFG
        ldd     #400*4
        lbsr    setrow          row 400, column 0 ...
        lbsr    idle
        lda     #100
        sta     <WPTR0          ... column 100 (WPTR1 keeps row 400's bits)
        ldx     #glyph
        ldb     #8
g1      lbsr    idle
        lda     ,x+
        sta     <VDATA
        decb
        bne     g1
* mask glyph at row 400, column 120: WFG red, WBG blue
        lbsr    idle
        lda     #$CB            WMODE 01
        sta     <VCTRL
        lda     #$E0
        sta     <WFG
        lda     #$03
        sta     <WBG
        ldd     #400*4
        lbsr    setrow
        lbsr    idle
        lda     #120
        sta     <WPTR0
        ldx     #glyph
        ldb     #8
g2      lbsr    idle
        lda     ,x+
        sta     <VDATA
        decb
        bne     g2
* span-solid rectangle, 16 x 20, at row 380, column 200, one WPTR load
        lbsr    idle
        lda     #$D3            WMODE 10
        sta     <VCTRL
        lda     #15
        sta     <SPANLEN
        lda     #$1C
        sta     <WFG
        ldd     #380*4
        lbsr    setrow
        lbsr    idle
        lda     #200
        sta     <WPTR0
        ldb     #20
g3      lbsr    idle
        sta     <VDATA
        decb
        bne     g3
        lbsr    idle
        clr     <WADV
        lda     #$C3
        sta     <VCTRL
* read back: row 0, columns 14..17 -> expect 17, 17, 18, 18
        clra
        clrb
        lbsr    setrow
        lbsr    idle
        lda     #14
        sta     <WPTR0
        lda     <VDATA
        sta     rd1
        lda     <VDATA
        sta     rd1+1
        lda     <VDATA
        sta     rd2
        lda     <VDATA
        sta     rd2+1
        ldd     #2
        std     phase
        lda     #$82
        sta     <SIMPORT
        ldb     #20
w2      lbsr    vbrise
        decb
        bne     w2

* phase 3: VMODE 00, VSCROLL 8
        lbsr    vbrise
        lda     #$C0
        sta     <VCTRL
        lda     #$2C            VSCROLL = 300
        sta     <VSCROLL
        lda     #1
        sta     <VSCRLH
        ldd     #3
        std     phase
        lda     #$83
        sta     <SIMPORT
        ldb     #20
w3      lbsr    vbrise
        decb
        bne     w3
* phases 4 and 5: the CPU writes HSCROLL = 3, then 5, in VMODE 11
        lbsr    vbrise
        lda     #$C3
        sta     <VCTRL
        clr     <VSCROLL
        clr     <VSCRLH
        lda     #3
        sta     <HSCROLL
        clr     <HSCRLH
        ldd     #4
        std     phase
        ldb     #12
w4      lbsr    vbrise
        decb
        bne     w4
        lda     #5
        sta     <HSCROLL
        ldd     #5
        std     phase
        ldb     #12
w5      lbsr    vbrise
        decb
        bne     w5
        lda     #$84
        sta     <SIMPORT
done    bra     done

*******************************************************************************
* mklist - the list, into RAM at $D000; cnt := its length
*******************************************************************************
mklist  ldx     #$D000
        ldb     #1              line 1: HSCROLL 1
        bsr     waits
        ldd     #$0301
        std     ,x++
        ldd     #$0400
        std     ,x++
        ldb     #19             line 20: 2
        bsr     waits
        ldd     #$0302
        std     ,x++
        ldb     #20             line 40: 3
        bsr     waits
        ldd     #$0303
        std     ,x++
        ldb     #20             line 60: 5
        bsr     waits
        ldd     #$0305
        std     ,x++
        ldb     #20             line 80: 6
        bsr     waits
        ldd     #$0306
        std     ,x++
        ldb     #20             line 100: 7
        bsr     waits
        ldd     #$0307
        std     ,x++
        ldb     #20             line 120: 0
        bsr     waits
        ldd     #$0300
        std     ,x++
        ldb     #80             line 200: LUT[16] := $F800
        bsr     waits
        ldd     #$1010
        std     ,x++
        ldd     #$1100
        std     ,x++
        ldd     #$12F8
        std     ,x++
        ldb     #100            line 300: back to RGB332(16) = 000 100 00 -> $0240
        bsr     waits
        ldd     #$1010
        std     ,x++
        ldd     #$1140
        std     ,x++
        ldd     #$1202
        std     ,x++
        lda     #$FF
        sta     ,x+
        tfr     x,d
        subd    #$D000
        std     cnt
        rts
waits   lda     #$80
wt1     sta     ,x+
        decb
        bne     wt1
        rts

* putlist - cnt bytes from $D000 through VDATA, direct, at the loaded WPTR
putlist ldx     #$D000
        ldy     cnt
        lda     #$C3
        anda    #$7F            display off while building: WMODE 00
        sta     <VCTRL
pl1     lbsr    idle
        lda     ,x+
        sta     <VDATA
        leay    -1,y
        bne     pl1
        rts

* setrow - D = row * 4: WPTR := D << 8, which is row << 10
setrow  lbsr    idle
        clr     <WPTR0
        stb     <WPTR1
        sta     <WPTR2
        rts

idle    pshs    a
id1     lda     <VSTAT
        bmi     id1
        puls    a,pc

vbrise  pshs    a
vr1     lda     <VSTAT
        bita    #$40
        bne     vr1
vr2     lda     <VSTAT
        bita    #$40
        beq     vr2
        puls    a,pc

vbfall  pshs    a
vf1     lda     <VSTAT
        bita    #$40
        bne     vf1
        puls    a,pc

irqh    sta     <VSTAT
        rti

glyph   FCB     $81,$42,$24,$18,$18,$24,$42,$FF
r5tab   FCB     0,32,72,104,144,176,216,248
g6tab   FCB     0,9,18,27,36,45,54,63
b5tab   FCB     0,10,21,31

        END
