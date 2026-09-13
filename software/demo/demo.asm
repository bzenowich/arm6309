*******************************************************************************
* demo.asm -- three parrots, a scrolling overworld, and a module playing
* underneath both, on the whole machine.
*
*   sh software/demo/build.sh          assemble and lay out the 1 MB ROM
*   sh hardware/gal/verilog/run-demo.sh    run it, and make the video
*
* WHAT IT IS FOR. Every bench in this repository before this one runs the video
* card or the audio card; machine_tb runs the CPU with the video card; nothing
* has run all three together, taken an interrupt, or played a note from 6809
* code. This does all of that at once, for long enough to watch: the replayer
* runs from the audio card's /FIRQ (audio.md 8.1) the whole time, the game
* loop counts frames from the video card's VBL /IRQ (graphics.md 12.1), and the
* main line never stops using the bus between them.
*
* THE SEQUENCE
*   1. boot.asm runs its own tests, finds "6309" at ROM page 1, maps pages 1-2
*      at $8000 and jumps to $8004
*   2. mod_load uploads the samples through SPTR/SDATA and mod_start starts
*      the tempo timer; /FIRQ is unmasked and the music plays from here on
*   3. 256 palette entries: entry i is RGB332(i) in RGB565
*   4. VRAM rows 0-479 cleared with span-solid writes, VMODE 11 on
*   5. the picture, 307,200 bytes from ROM through VDATA, painting down
*   6. five seconds of it (300 VBL interrupts at 59.94 Hz) - and while it
*      stands, the tile set and the first view of the world go into VRAM
*      below row 480, where VMODE 11 does not look
*   7. cell mode, VMODE 00, and the game loop, for ever
*
* THE MAP (logical, task 0)
*   $0000 block 0   ROM window W0 - world, frames, sprites, the module header
*   $2000 block 1   ROM window W1 - the picture, tiles, and W0's next page
*   $4000 blocks 2-3  the replayer's pattern window. /FIRQ's alone
*   $8000 blocks 4-5  this code, ROM pages 1-2
*   $C000 block 6   SIMM: boot's variables and RAM vectors, this file's
*                   variables from $C200, the stack below $E000
*   $E000 block 7   ROM page 0, boot.asm, and the vectors
*******************************************************************************

        INCLUDE "build/assets.inc"
        INCLUDE "build/game.inc"

*----------------------------------------------------------------- the machine
MAPHI   EQU     $FF90
MAPLO   EQU     $FFA0
SIMPORT EQU     $FF2F           boot.asm's progress port - decodes nowhere
MARK    EQU     $FF2E           a timing mark for demo_tb - decodes nowhere either
IRQVEC  EQU     $C004           boot.asm's RAM vectors: IRQ jumps through here
FIRQVEC EQU     $C006           ... and FIRQ

*------------------------------------------------------------------- the video
VCTRL   EQU     $FF60
VSCROLL EQU     $FF61
VSCRLH  EQU     $FF62
HSCROLL EQU     $FF63
HSCRLH  EQU     $FF64
SPANLEN EQU     $FF65
WFG     EQU     $FF66
WPTR0   EQU     $FF68
WPTR1   EQU     $FF69
WPTR2   EQU     $FF6A
PIDX    EQU     $FF70
PDATL   EQU     $FF71
PDATH   EQU     $FF72
VSTAT   EQU     $FF73           b7 SPANBUSY, b6 VBLANK, b4 LRUN, b0 IRQ; a write clears IRQ
WADV    EQU     $FF74
VDATA   EQU     $FF75
TILEBAS EQU     $FF77
MAPBAS  EQU     $FF79

CT_OFF  EQU     $00
CT_SOL  EQU     $10             WMODE 10 span-solid, display off
CT_PIC  EQU     $C3             display, VBL IRQ, VMODE 11 640x480
CT_GAME EQU     $E0             display, VBL IRQ, CELL, VMODE 00 640x200

* graphics.md 6.4.1. TILEBASE is A18..A14 and the map base A18..A12, so the
* tile set is at 30 * 16384 = $78000 (ring row 480) and the map at
* 124 * 4096 = $7C000 (row 496) - both below the 480 rows VMODE 11 shows.
TB      EQU     30
MB      EQU     124

* QUICK (A09 -DQUICK) paints a strip of the picture and holds it for a moment,
* for iterating on the game without two and a half seconds of paint.
        IFD     QUICK
PICROWS EQU     16
HOLDF   EQU     20
        ELSE
PICROWS EQU     480
HOLDF   EQU     300             five seconds at VMODE 11's 59.94 Hz
        ENDIF

* Progress codes, for the bench.
P_ENTER EQU     $80
P_MUSIC EQU     $81
P_PAL   EQU     $82
P_CLEAR EQU     $83
P_PIC   EQU     $84
P_GAME  EQU     $85

*------------------------------------------------------------------ variables
* In block 6, clear of boot.asm's $C000-$C1FF. EQUs rather than RMB so the
* binary stays the ROM image and nothing else.
V       EQU     $C200
fcnt    EQU     V+$00           2  VBL interrupts since they were enabled
lastf   EQU     V+$02           2
k       EQU     V+$04           2  frame record the main line has reached
pk      EQU     V+$06           2  record of the pending camera
dispk   EQU     V+$08           2  record of the camera on the screen - the bench reads it
herok   EQU     V+$0A           2  record of the hero on the screen - the bench reads it
pcamx   EQU     V+$0C           2
pcamy   EQU     V+$0E           2
cl      EQU     V+$10           1  ring coverage: leftmost world column
rt      EQU     V+$11           1  ... top world row
hvis    EQU     V+$12           1  the hero's cells are in the map
hbase   EQU     V+$13           1  ... their first tile code
hc0     EQU     V+$14           1  ... world column and row of the first cell
hr0     EQU     V+$15           1
jstate  EQU     V+$16           1  0 idle, 1 composing, 2 ready to flip
jx      EQU     V+$17           2
jy      EQU     V+$19           2
jf      EQU     V+$1B           1
jk      EQU     V+$1C           2
jtile   EQU     V+$1E           1
jbase   EQU     V+$1F           1
tx      EQU     V+$20           2  the record's hero
ty      EQU     V+$22           2
tf      EQU     V+$24           1
missed  EQU     V+$25           2  frames whose blank was over before we got to it
gtmp    EQU     V+$27           1
gtmp2   EQU     V+$28           1
gcol    EQU     V+$29           1
grow    EQU     V+$2A           1
gcnt    EQU     V+$2B           1
gpage   EQU     V+$2C           1
ptrow   EQU     V+$2D           2
sx0     EQU     V+$2F           1
sy      EQU     V+$30           1
sprb    EQU     V+$31           2  the sprite frame's first byte, in W0
ocol    EQU     V+$33           1  flip: the old rectangle
orow    EQU     V+$34           1
ohvis   EQU     V+$35           1
frow    EQU     V+$36           1
fcol    EQU     V+$37           1
jstage  EQU     V+$38           1  compose1: 0 background, 1-8 a pixel row, 9 out
sready  EQU     V+$39           1  pcamx/pcamy are ready for the IRQ to scroll to
gdelta  EQU     V+$3A           2
ci      EQU     V+$3C           1  compose1: cell within the hero's 5 x 3
cj      EQU     V+$3D           1
cpr     EQU     V+$3E           1  ... pixel row
csy     EQU     V+$3F           1  ... sprite row
ccol    EQU     V+$C0           1
gcol2   EQU     V+$C1           1
grow2   EQU     V+$C2           1
fcode   EQU     V+$C3           1
tickend EQU     V+$C4           1  replayer ticks finished, mod 256
tickirq EQU     V+$C5           1  ... as the last VBL IRQ saw it
buf     EQU     V+$40           64 bytes: one tile being composed
* the replayer's
tick    EQU     V+$80
speed   EQU     V+$81
bpm     EQU     V+$82
pdelay  EQU     V+$83
position EQU    V+$84
row     EQU     V+$85
brk_p   EQU     V+$86
brk_row EQU     V+$87
jmp_p   EQU     V+$88
jmp_pos EQU     V+$89
lp_p    EQU     V+$8A
lp_tgt  EQU     V+$8B
actrl   EQU     V+$8C
songlen EQU     V+$8D
npat    EQU     V+$8E
newrow  EQU     V+$8F
lper    EQU     V+$90
lvol    EQU     V+$92
note    EQU     V+$93
rfp     EQU     V+$95
rsm     EQU     V+$97
tmpb    EQU     V+$98
tmpb2   EQU     V+$99
tmpb3   EQU     V+$9A
tmpb4   EQU     V+$9B
tmpw    EQU     V+$9C
tmpw2   EQU     V+$9E
tmpw3   EQU     V+$A0
t24a    EQU     V+$A2
t24b    EQU     V+$A5
t24c    EQU     V+$A8
t24d    EQU     V+$AB
t24s    EQU     V+$AE
t24r    EQU     V+$B1
repoff  EQU     V+$B4
replen  EQU     V+$B6
smpn    EQU     V+$B8
ucount  EQU     V+$B9
ucount2 EQU     V+$BB
tmpg    EQU     V+$BC
order   EQU     V+$100          128
smptab  EQU     V+$180          32 * 12 = 384
chans   EQU     V+$300          4 * 40

*******************************************************************************
        ORG     $8000
*******************************************************************************
        FCC     "6309"          boot.asm looks for this
        JMP     start

        INCLUDE "replay.asm"
        INCLUDE "build/tables.inc"

        SETDP   $FF

*==============================================================================
* 1-2. Take over, and start the music.
*==============================================================================
start   orcc    #$50            both masked while the vectors are pointed
        lds     #$E000
        lda     #$FF            every register this file touches is $FFxx
        tfr     a,dp
        lda     #P_ENTER
        sta     <SIMPORT
        clra
        sta     <VCTRL          display off: boot.asm left cell mode running
        ldx     #V
        ldd     #0
st1     std     ,x++
        cmpx    #V+$400
        bne     st1
        ldx     #irqh
        stx     IRQVEC
        ldx     #firqh
        stx     FIRQVEC

        lbsr    mod_load
        beq     st2
        sta     <SIMPORT        the loader's reason, and stop
        bra     *
st2     lbsr    mod_start
        andcc   #$BF            unmask FIRQ: the replayer runs from here on
        lda     #P_MUSIC
        sta     <SIMPORT

*==============================================================================
* 3. The palette. graphics.md 13.1: commit with the display off and nothing snows.
*    Entry i = RGB332(i): PDATH = RRRRRGGG, PDATL = GGGBBBBB.
*==============================================================================
        clr     <PIDX
        clrb
pal1    tfr     b,a             R: i >> 5
        lsra
        lsra
        lsra
        lsra
        lsra
        ldx     #r5tab
        lda     a,x
        sta     gtmp            RRRRR000
        tfr     b,a             G: (i >> 2) & 7
        lsra
        lsra
        anda    #7
        ldx     #g6tab
        lda     a,x             G6 = GGGGGG
        sta     gtmp2
        lsra
        lsra
        lsra                    G6 >> 3
        ora     gtmp
        sta     gtmp            PDATH
        lda     gtmp2
        anda    #7
        lsla
        lsla
        lsla
        lsla
        lsla                    (G6 & 7) << 5
        sta     gtmp2
        tfr     b,a             B: i & 3
        anda    #3
        ldx     #b5tab
        lda     a,x
        ora     gtmp2
        sta     <PDATL
        lda     gtmp
        sta     <PDATH          commits, and PIDX steps
        incb
        bne     pal1
        lda     #P_PAL
        sta     <SIMPORT

*==============================================================================
* 4. Clear rows 0-479: three 256-byte span-solids a row, colour 0.
*==============================================================================
        lda     #CT_SOL
        sta     <VCTRL
        clr     <WFG
        lda     #255
        sta     <SPANLEN
        ldd     #0
        std     ptrow
cl1     lbsr    rowptr10        WPTR := ptrow << 10
        ldb     #3
cl2     lbsr    idle
        sta     <VDATA          the trigger
        decb
        bne     cl2
        ldd     ptrow
        addd    #1
        std     ptrow
        cmpd    #480
        bne     cl1
        lbsr    idle
        clr     <VSCROLL
        clr     <VSCRLH
        clr     <HSCROLL
        clr     <HSCRLH
        clr     <WADV
        lda     #P_CLEAR
        sta     <SIMPORT

*==============================================================================
* 5. The picture. VMODE 11 is on while it paints, so it comes in down the screen
*    at the rate this CPU can move bytes - which is the honest thing to show.
*==============================================================================
        lda     #CT_PIC
        sta     <VCTRL
        ldd     #0
        std     fcnt
        std     lastf
        andcc   #$EF            unmask IRQ: the frame counter runs from here on
        lda     #PICPAGE
        sta     gpage
        lbsr    mapw1
        ldx     #$2000
        ldd     #0
        std     ptrow
pic1    lbsr    rowptr10
        ldu     #640            bytes left in this row
pic2    tfr     x,d             D = bytes to the end of the window
        coma
        comb
        addd    #$4001
        cmpd    #255
        bls     pic3
        ldd     #255
pic3    pshs    d               ... and no more than the row has
        cmpu    ,s
        bhs     pic4
        tfr     u,d
        std     ,s
pic4    tfr     u,d
        subd    ,s
        tfr     d,u
        puls    d               B = this chunk (1..255)
pic5    lda     ,x+
        sta     <VDATA
        decb
        bne     pic5
        cmpx    #$4000
        bne     pic6
        inc     gpage
        lbsr    mapw1
        ldx     #$2000
pic6    cmpu    #0
        bne     pic2
        ldd     ptrow
        addd    #1
        std     ptrow
        cmpd    #PICROWS
        bne     pic1
        lda     #P_PIC
        sta     <SIMPORT

*==============================================================================
* 6. Hold it for five seconds - and use them.
*==============================================================================
        ldd     fcnt
        addd    #HOLDF
        std     ptrow           the deadline

* the tile set: 256 * 64 bytes at $78000, one 1024-byte ring row at a time -
* a VDATA stream cannot leave its row (boot/README.md, "the display list")
        lbsr    idle
        lda     #TB
        sta     <TILEBAS
        lda     #MB
        sta     <MAPBAS
        lda     #TILPAGE
        sta     gpage
        lbsr    mapw1
        ldx     #$2000
        ldd     #$8000
        std     tx
ts1     ldd     tx
        lbsr    setw7
        ldu     #1024
ts2     lda     ,x+
        sta     <VDATA
        leau    -1,u
        cmpu    #0
        bne     ts2
        cmpx    #$4000
        bne     ts3
        inc     gpage
        lbsr    mapw1
        ldx     #$2000
ts3     ldd     tx
        addd    #1024
        std     tx
        cmpd    #$C000
        bne     ts1

* the first view: record 0's camera, every covered row
        ldd     #0
        std     k
        lbsr    readrec
        ldd     pcamx
        lbsr    shr3
        stb     cl
        ldd     pcamy
        lbsr    shr3
        stb     rt
        clr     hvis
        clr     gcnt
fv1     lda     rt
        adda    gcnt
        lbsr    wrow
        inc     gcnt
        lda     gcnt
        cmpa    #26
        bne     fv1
        ldd     pk
        std     dispk
        ldd     #$FFFF          no hero on the screen yet - the bench reads this
        std     herok
        clr     jstate

* the rest of the five seconds
hold1   ldd     fcnt
        cmpd    ptrow
        blo     hold1

*==============================================================================
* 7. The game. Switch in vertical blank, then run.
*==============================================================================
        clr     sready
        lbsr    vblank
        orcc    #$50
        lda     #CT_GAME
        sta     <VCTRL
        lbsr    scrollp
        andcc   #$AF
        lda     #P_GAME
        sta     <SIMPORT
        ldd     fcnt
        std     lastf

gloop   ldd     fcnt
        cmpd    lastf
        bne     gframe
        lda     jstate          nothing new: spend the time on the hero
        cmpa    #1
        bne     gloop
        lbsr    compose1
        bra     gloop

* A vertical blank has happened (and the IRQ has already scrolled to the camera
* this loop last left ready).
gframe  subd    lastf
        std     gdelta
        ldd     fcnt
        std     lastf
* the hero, if one is built and we are still inside the blank - and no replayer
* tick finished since the IRQ, because one that did has eaten up to 5 ms: the
* blank may be nearly over while VBLANK still reads 1 (demo_tb measured seven
* flips in 276 run into the picture that way)
        lda     jstate
        cmpa    #2
        bne     gf2
        orcc    #$40
        lda     tickend
        cmpa    tickirq
        bne     gf1
        lda     <VSTAT
        bita    #$40
        beq     gf1
        lbsr    flip
        andcc   #$BF
        bra     gf2
gf1     andcc   #$BF            too late: the blank is over, try the next one
        ldd     missed
        addd    #1
        std     missed
* the next camera, unless the IRQ has not taken the last one yet
gf2     tst     sready
        bne     gloop
        ldd     k
        addd    gdelta
gf3     cmpd    #NFRAMES
        blo     gf4
        subd    #NFRAMES
        bra     gf3
gf4     std     k
        lbsr    readrec
        ldd     pcamx
        lbsr    shr3
        stb     gcol2
gf5     lda     cl
        cmpa    gcol2
        beq     gf7
        bhi     gf6
        inc     cl              right: the new column is cl + 80
        lda     cl
        adda    #80
        lbsr    wcol
        bra     gf5
gf6     dec     cl              left: the new column is cl
        lda     cl
        lbsr    wcol
        bra     gf5
gf7     ldd     pcamy
        lbsr    shr3
        stb     grow2
gf8     lda     rt
        cmpa    grow2
        beq     gf10
        bhi     gf9
        inc     rt              down: the new row is rt + 25
        lda     rt
        adda    #25
        lbsr    wrow
        bra     gf8
gf9     dec     rt
        lda     rt
        lbsr    wrow
        bra     gf8
gf10    lda     #1              the strips are in: the IRQ may scroll
        sta     sready
* the hero: if nothing is being built and the record's hero is not the one
* on the screen, start building it
        lda     jstate
        lbne    gloop
        tst     hvis
        beq     gf11
        ldd     tx
        cmpd    jx
        bne     gf11
        ldd     ty
        cmpd    jy
        bne     gf11
        lda     tf
        cmpa    jf
        lbeq    gloop
gf11    ldd     tx
        std     jx
        ldd     ty
        std     jy
        lda     tf
        sta     jf
        ldd     pk
        std     jk
        clr     jtile
        clr     jstage
        lda     #SPRA           the buffer that is not on the screen
        tst     hvis
        beq     gf12
        cmpa    hbase
        bne     gf12
        adda    #15
gf12    sta     jbase
        lda     #1
        sta     jstate
        lbra    gloop

*******************************************************************************
* scrollp - the pending camera into HSCROLL/VSCROLL. VSCROLL loads through
* vertical blank and HSCROLL at every line's start, so this is written in the
* blank - by the IRQ - and both land on the same frame.
*******************************************************************************
scrollp ldd     pcamx
        stb     <HSCROLL
        anda    #$03
        sta     <HSCRLH
        ldd     pcamy
        stb     <VSCROLL
        clr     <VSCRLH         cell mode's ring is 32 rows: VSCROLL[7:3]
        ldd     pk
        std     dispk
        rts

*******************************************************************************
* readrec - record k into pcamx/pcamy/pk and the hero target tx/ty/tf.
*******************************************************************************
readrec pshs    x
        ldd     k
        lslb
        rola
        lslb
        rola
        lslb
        rola
        tfr     d,x
        lda     #FRMPAGE
        lbsr    romat
        ldd     ,x
        std     pcamx
        ldd     2,x
        std     pcamy
        lda     4,x
        lsra
        lsra
        lsra
        lsra
        sta     tf
        lda     4,x
        anda    #$0F
        ldb     5,x
        std     tx
        ldd     6,x
        std     ty
        ldd     k
        std     pk
        puls    x,pc

*******************************************************************************
* cellcode - A = world row, B = world column. Returns A = the code the map should
* hold there: one of the hero's if his cells cover it, else the world's.
* Uses W0/W1. Preserves B and X.
*******************************************************************************
cellcode
        pshs    x,b
        tst     hvis
        beq     cc2
        subb    hc0
        cmpb    #5
        bhs     cc2
        pshs    a
        suba    hr0
        cmpa    #3
        bhs     cc1
        stb     ccol            A = row within, B = column within
        ldb     #5
        mul
        addb    ccol
        addb    hbase
        tfr     b,a
        leas    1,s
        puls    x,b,pc
cc1     puls    a
cc2     ldb     ,s              world[(row << 8) | col]
        tfr     d,x
        lda     #WLDPAGE
        lbsr    romat
        lda     ,x
        puls    x,b,pc

*******************************************************************************
* ringw - A = world row, B = world column: WPTR := that cell's map byte in
* the ring, (row & 31) * 128 + (col & 127) above $7C000.
*******************************************************************************
ringw   pshs    d
        anda    #31
        andb    #127
        pshs    b
        clrb
        lsra                    row * 128 = row << 7: (row >> 1, row & 1 << 7)
        rorb
        adda    #$C0
        orb     ,s+
        lbsr    setw7
        puls    d,pc

*******************************************************************************
* wcol - A = world column. Writes rows rt .. rt+25 of it into the ring.
*******************************************************************************
wcol    pshs    d,x
        sta     gcol
        lda     rt
        sta     grow
        ldb     #26
        stb     gtmp
wc1     lda     grow
        ldb     gcol
        lbsr    cellcode
        pshs    a
        lda     grow
        lbsr    ringw
        puls    a
        sta     <VDATA
        inc     grow
        dec     gtmp
        bne     wc1
        puls    d,x,pc

*******************************************************************************
* wrow - A = world row. Writes columns cl .. cl+80 of it into the ring.
*******************************************************************************
wrow    pshs    d,x
        sta     grow
        lda     cl
        sta     gcol
        ldb     #81
        stb     gtmp
        lda     grow
        ldb     gcol
        lbsr    ringw
wr2     lda     grow
        ldb     gcol
        lbsr    cellcode
        sta     <VDATA
        inc     gcol
        dec     gtmp
        beq     wr9
        lda     gcol
        bita    #127            the ring wrapped, and WPTR's column does not
        bne     wr2
        lda     grow
        ldb     gcol
        lbsr    ringw
        bra     wr2
wr9     puls    d,x,pc

*******************************************************************************
* compose1 - one stage of building the hero's tile `jtile` into buffer jbase.
*
* Tile t is cell (i, j) = (t mod 5, t div 5) of the 5 x 3 the hero can touch.
* Its background is the WORLD's tile there - not the ring's, which may be the
* hero - and every sprite byte that lands in it and is not SPRKEY replaces the
* background's. Ten stages per tile, none longer than ~64 stores, so the main
* line comes back to look at the frame counter often enough to catch a blank.
*   stage 0     the background tile into buf
*   stage 1-8   pixel row (stage - 1) of the sprite, over buf
*   stage 9     buf to VRAM at the tile's address
*******************************************************************************
compose1
        pshs    d,x,y,u
        lda     jtile           i, j
        clrb
cm1     cmpa    #5
        blo     cm2
        suba    #5
        incb
        bra     cm1
cm2     sta     ci
        stb     cj
        lda     jstage
        lbne    cp20
* ---- stage 0: the background
        ldd     jx
        lbsr    shr3
        addb    ci
        stb     ccol
        ldd     jy
        lbsr    shr3
        addb    cj
        tfr     b,a
        ldb     ccol
        tfr     d,x
        lda     #WLDPAGE
        lbsr    romat
        ldb     ,x              the code
        lda     #64
        mul
        tfr     d,x
        lda     #TILPAGE
        lbsr    romat
        ldu     #buf
        ldb     #64
cp3     lda     ,x+
        sta     ,u+
        decb
        bne     cp3
        lbra    cp90
cp20    cmpa    #9
        lbeq    cp30
* ---- stages 1-8: one pixel row
        deca
        sta     cpr             pixel row
        lda     jy+1            sy = j*8 + row - oy
        anda    #7
        sta     ccol
        lda     cj
        lsla
        lsla
        lsla
        adda    cpr
        suba    ccol
        cmpa    #16             0 <= sy < 16, unsigned
        lbhs    cp90
        sta     csy
        lda     jf              the frame: frame * 512 into the sprites
        ldb     #2
        mul
        tfr     b,a
        clrb
        tfr     d,x
        lda     #SPRPAGE
        lbsr    romat
        lda     csy
        ldb     #32
        mul
        leay    d,x             Y = sprite row sy
        lda     cpr             U = buf row
        ldb     #8
        mul
        ldu     #buf
        leau    d,u
        lda     jx+1            sx = i*8 - ox, for column 0
        anda    #7
        sta     ccol
        lda     ci
        lsla
        lsla
        lsla
        suba    ccol
        clrb                    pixel column
cp5     cmpa    #32             0 <= sx < 32
        bhs     cp6
        pshs    a
        lda     a,y             A is 0..31 here, so the signed offset is safe
        cmpa    #SPRKEY
        beq     cp5a
        sta     b,u
cp5a    puls    a
cp6     inca
        incb
        cmpb    #8
        bne     cp5
        bra     cp90
* ---- stage 9: out to VRAM, at the tile's address
cp30    lda     jbase
        adda    jtile
        ldb     #64
        mul
        addd    #$8000
        lbsr    setw7
        ldu     #buf
        ldb     #64
cp31    lda     ,u+
        sta     <VDATA
        decb
        bne     cp31
        clr     jstage
        inc     jtile
        lda     jtile
        cmpa    #15
        bne     cp99
        lda     #2
        sta     jstate
        bra     cp99
cp90    inc     jstage
cp99    puls    d,x,y,u,pc

*******************************************************************************
* flip - in vertical blank: put the built buffer in the map at the new cells,
* and give the old cells back to the world.
*******************************************************************************
flip    pshs    d,x,y
        lda     #1              mark: the flip starts (demo_tb's marks.txt)
        sta     <MARK
        lda     hc0             the old rectangle, kept for the restore
        sta     ocol
        lda     hr0
        sta     orow
        lda     hvis
        sta     ohvis
        ldd     jx
        lbsr    shr3
        stb     hc0
        ldd     jy
        lbsr    shr3
        stb     hr0
        lda     jbase
        sta     hbase
        lda     #1
        sta     hvis
* the new cells: five contiguous map bytes a row, so one WPTR load a row -
* unless the ring's column wraps inside the five, which takes the slow path
        lda     hc0
        anda    #127
        cmpa    #123
        bhi     flslow
        clr     frow
        ldb     hbase
        stb     fcode
fl1     lda     hr0
        adda    frow
        ldb     hc0
        lbsr    cellw
        lda     fcode
        ldb     #5
fl2     sta     <VDATA
        inca
        decb
        bne     fl2
        sta     fcode
        inc     frow
        lda     frow
        cmpa    #3
        bne     fl1
        bra     flold
flslow  clr     frow            one WPTR load per cell
        ldb     hbase
        stb     fcode
fls1    clr     fcol
fls2    lda     hr0
        adda    frow
        ldb     hc0
        addb    fcol
        lbsr    cellw
        lda     fcode
        sta     <VDATA
        inc     fcode
        inc     fcol
        lda     fcol
        cmpa    #5
        bne     fls2
        inc     frow
        lda     frow
        cmpa    #3
        bne     fls1
* the old cells outside the new rectangle go back to the world. One mapping of
* the world for all of them: the old rectangle's first cell, and +256 a row.
flold   tst     ohvis
        lbeq    fl9
        lda     orow            the same rectangle? nothing to give back
        cmpa    hr0
        bne     flo0
        lda     ocol
        cmpa    hc0
        lbeq    fl9
flo0    lda     orow
        ldb     ocol
        tfr     d,x
        lda     #WLDPAGE
        lbsr    romat
        tfr     x,y             Y = world[orow][ocol]
* the two moves the hero makes nearly every time: one column across, or one row
* down or up, in place. Each gives back one edge of the old rectangle and no
* cell of it needs testing.
        lda     orow
        cmpa    hr0
        bne     flrow
        lda     ocol            same row: one column?
        inca
        cmpa    hc0
        bne     flc1
        clrb                    moved right: the old left column goes back
        bra     flcol
flc1    suba    #2
        cmpa    hc0
        bne     flgen
        ldb     #4              moved left: the old right column
flcol   stb     fcol
        clr     frow
flc2    lda     orow
        adda    frow
        ldb     ocol
        addb    fcol
        lbsr    cellw
        ldb     fcol
        lda     b,y
        sta     <VDATA
        leay    256,y
        inc     frow
        lda     frow
        cmpa    #3
        bne     flc2
        lbra    fl9
flrow   lda     ocol            same column: one row?
        cmpa    hc0
        bne     flgen
        anda    #127            ... and no ring wrap inside its five
        cmpa    #123
        bhi     flgen
        lda     orow
        inca
        cmpa    hr0
        bne     flr1
        clrb                    moved down: the old top row goes back
        bra     flrw
flr1    suba    #2
        cmpa    hr0
        bne     flgen
        leay    512,y           moved up: the old bottom row
        ldb     #2
flrw    stb     frow
        lda     orow
        adda    frow
        ldb     ocol
        lbsr    cellw           five contiguous cells, one WPTR load (the flip's
        ldb     #0              fast path has already ruled out a ring wrap in
flr2    lda     b,y              the new rectangle, and the old is one row away)
        sta     <VDATA
        incb
        cmpb    #5
        bne     flr2
        lbra    fl9
* anything else: every old cell, tested against the new rectangle
flgen   clr     frow
fl3     lda     orow
        adda    frow
        sta     grow2           this row, in the world
        suba    hr0
        cmpa    #3
        blo     fl3a
        lda     #$FF            the whole row is outside: every column goes back
        sta     gtmp
        bra     fl3b
fl3a    clr     gtmp
fl3b    clr     fcol
fl4     tst     gtmp
        bne     fl4a
        lda     ocol
        adda    fcol
        suba    hc0
        cmpa    #5
        blo     fl5
fl4a    lda     grow2
        ldb     ocol
        addb    fcol
        lbsr    cellw
        ldb     fcol
        lda     b,y
        sta     <VDATA
fl5     inc     fcol
        lda     fcol
        cmpa    #5
        bne     fl4
        leay    256,y
        inc     frow
        lda     frow
        cmpa    #3
        bne     fl3
fl9     ldd     jk
        std     herok
        clr     jstate
        lda     #2              mark: the flip is done
        sta     <MARK
        puls    d,x,y,pc

*******************************************************************************
* cellw - A = world row, B = world column: WPTR := that cell's map byte, the flip's
* fast version of ringw - no stack, no WPTR2 (it is 7 for every write the game
* makes, and nothing carries into it: the pointer's row bits move only on
* WROWADV). Clobbers D.
*******************************************************************************
cellw   andb    #127
        anda    #31
        lsra                    row * 128: bit 0 of the row is bit 7 of the low byte
        bcc     cw1
        orb     #$80
cw1     adda    #$C0
cw2     tst     <VSTAT          graphics.md 7.4: never under a posted write
        bmi     cw2
        stb     <WPTR0
        sta     <WPTR1
        rts

*******************************************************************************
* Small things.
*******************************************************************************
* shr3 - D := D >> 3
shr3    lsra
        rorb
        lsra
        rorb
        lsra
        rorb
        rts

* idle - wait for SPANBUSY (VSTAT b7) to clear. graphics.md 7.4 and 13: WPTR
* may not be loaded under a span, and a posted write is one.
idle    pshs    a
id1     lda     <VSTAT
        bmi     id1
        puls    a,pc

* setw7 - WPTR := $70000 + D, once the card is idle.
setw7   bsr     idle
        stb     <WPTR0
        sta     <WPTR1
        pshs    a
        lda     #$07
        sta     <WPTR2
        puls    a,pc

* rowptr10 - WPTR := ptrow << 10: ring row ptrow, column 0.
rowptr10
        bsr     idle
        pshs    d
        clr     <WPTR0
        ldd     ptrow
        lslb
        rola
        lslb
        rola
        stb     <WPTR1
        sta     <WPTR2
        puls    d,pc

* mapw1 - block 1 := ROM page gpage
mapw1   pshs    a
        lda     gpage
        sta     <MAPLO+1
        lda     #$01
        sta     <MAPHI+1
        puls    a,pc

* romat - A = an asset's first page, X = an offset into it. Points blocks 0 and
* 1 at the page holding that offset and the next, and returns X at it in block
* 0, so anything up to 8 KB long reads straight through a page boundary.
romat   pshs    d
        sta     tmpg
        tfr     x,d
        lsra
        lsra
        lsra
        lsra
        lsra
        adda    tmpg
        sta     <MAPLO+0
        inca
        sta     <MAPLO+1
        lda     #$01
        sta     <MAPHI+0
        sta     <MAPHI+1
        tfr     x,d
        anda    #$1F
        tfr     d,x
        puls    d,pc

* vblank - return just after VBLANK rises
vblank  pshs    a
vb01    lda     <VSTAT
        bita    #$40
        bne     vb01
vb02    lda     <VSTAT
        bita    #$40
        beq     vb02
        puls    a,pc

* The palette's three expansions: 3 bits of red to RRRRR000, 3 of green to six,
* 2 of blue to five - mkparrots.py expand332() is the same arithmetic.
r5tab   FCB     0,32,72,104,144,176,216,248
g6tab   FCB     0,9,18,27,36,45,54,63
b5tab   FCB     0,10,21,31

*******************************************************************************
* The interrupts. boot.asm's vectors jump through IRQVEC and FIRQVEC.
*******************************************************************************
* /IRQ - the video card's VBL (graphics.md 12.1). Count it, and clear it.
irqh    orcc    #$40            HSCROLL is two registers: no /FIRQ between them
        ldd     fcnt
        addd    #1
        std     fcnt
        lda     tickend         which replayer tick had finished at this blank
        sta     tickirq
        tst     sready          the main line left a camera ready: scroll to it
        beq     ih1
        lbsr    scrollp
        clr     sready
ih1     sta     <VSTAT          any write clears the request
        rti

* /FIRQ - the audio card's tempo timer (audio.md 8.1). FIRQ stacks only PC and
* CC, so everything the replayer uses is saved here.
*
* ⚠ AND IT UNMASKS IRQ, because a 6809 entering FIRQ masks both. A row tick
* costs up to ~8,800 E cycles (4.2 ms) and the blank after the VBL IRQ is 1.2 ms,
* so a tick that happened to be running at the IRQ held the scroll write into
* the top of the next picture - demo_tb measured it as a 13-row tear, twice in
* 388 frames. The IRQ handler touches nothing the replayer does, and masks FIRQ
* itself for its two HSCROLL writes; RTI puts this handler's F back.
firqh   pshs    d,dp,x,y,u
        andcc   #$EF            let the VBL IRQ in - see below
        lda     #$FF
        tfr     a,dp
        lda     #3              mark: a tick starts (demo_tb's marks.txt)
        sta     <MARK
        lbsr    mod_tick
        inc     tickend         a tick has finished
        lda     #4              ... and ends
        sta     <MARK
        puls    d,dp,x,y,u
        rti

        END
