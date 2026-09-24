*******************************************************************************
* gui.asm -- the show's interpreter: a desktop, a paint program, a BBS and a
* raster demo, drawn by the 6809 from tools/mkshow.py's bytecode.
*
* tools/show.py is the format and OPS there is the dispatch order here. Every
* drawing operation is one of features.md 7's offloads, and each is the card's
* own mechanism with nothing in between:
*
*   FILL    PaintRect: span-solid strips of up to 256, chained down by WADV 01
*           - one WPTR load and one write per row per strip
*   PAT     FillRect with a pattern: span-mask, one 8-pixel column at a time,
*           the pattern row IS the mask byte
*   TEXT    glyph blits: span-mask (opaque) or sprite mode (transparent)
*   ICON    1bpp layers in sprite mode (features.md 8.4)
*   POLY    scanline polygons: the edges stepped here, the runs span-solid
*   POLYP   ... with a pattern: a solid run, then sprite-mode pattern bytes
*   IMAGE   an 8bpp copy - the one thing the card does not offload
*   CURS    the pointer: save-behind by VDATA READ-BACK (graphics.md 11), the
*           arrow in sprite mode, restored by direct writes
*   LISTHS  a split horizontal scroll by display list (graphics.md 10.3.2)
*   RASTER  a per-scanline palette by display list
*   TERM    an ANSI terminal: span-mask glyphs, VSCROLL for the scroll
*
* THE SCRIPT WINDOW. The bytecode is ROM pages from SCRPAGE, read through
* logical block 0; U is the script pointer inside it and nothing else uses U
* while the interpreter runs. Block 1 is the data window: fonts, icons, the
* image. Blocks 2-3 stay the replayer's (demo.asm).
*
* THE CHECKPOINT. `ck` is the model picture the screen is showing, or 0 while
* anything is being drawn; demo_tb reads it at each frame's first and last
* active dot, and a frame whose two readings agree is compared pixel for pixel
* against tools/show.py's picture of that id. Every operation that changes the
* screen clears it first, and CHECK sets it only once the card is idle.
*******************************************************************************

G       EQU     $C600
ck      EQU     G+$00           2  the picture on the screen (demo_tb reads it)
ckph    EQU     G+$02           2  the raster phase + 1 its list is showing, or 0
spage   EQU     G+$04           1  ROM page of the script in block 0
ox      EQU     G+$05           2
oy      EQU     G+$07           2
ctrlv   EQU     G+$09           1  CTRL without the WMODE bits
wmode   EQU     G+$0A           1  the WMODE bits CTRL holds
wadvv   EQU     G+$0B           1  shadows of WADV, WFG, WBG, SPANLEN
wfgv    EQU     G+$0C           1
wbgv    EQU     G+$0D           1
splv    EQU     G+$0E           1
cvis    EQU     G+$0F           1
cx      EQU     G+$10           2
cy      EQU     G+$12           2
lact    EQU     G+$14           1  0 no list, 1 LISTHS, 2 RASTER, 3 WAVE
ax      EQU     G+$15           2  operands
ay      EQU     G+$17           2
aw      EQU     G+$19           2
ah      EQU     G+$1B           2
ac      EQU     G+$1D           1
afg     EQU     G+$1E           1
abg     EQU     G+$1F           1
ap      EQU     G+$20           1
an      EQU     G+$21           1
av      EQU     G+$22           1
tw      EQU     G+$23           2
arem    EQU     G+$25           2
ach     EQU     G+$27           2
gp      EQU     G+$29           1  the data window's page
arow    EQU     G+$2A           1
apx     EQU     G+$2B           2
ancol   EQU     G+$2D           1
anl     EQU     G+$2E           1
apres   EQU     G+$2F           1
acol    EQU     G+$30           1
ax0     EQU     G+$31           2
scnt    EQU     G+$33           1
ssp     EQU     G+$34           1  script call depth
sstk    EQU     G+$35           12 four (page, pointer) returns
rph     EQU     G+$41           2  the phase + 1 the raster list holds
py      EQU     G+$43           2  polygons
yend    EQU     G+$45           2
nlv     EQU     G+$47           1
nrv     EQU     G+$48           1
li      EQU     G+$49           1
ri      EQU     G+$4A           1
lcur    EQU     G+$4B           1
rcur    EQU     G+$4C           1
lx8     EQU     G+$4D           3  left edge x, 16.8
lstep   EQU     G+$50           3
rx8     EQU     G+$53           3
rstep   EQU     G+$56           3
ex8     EQU     G+$59           3  edge's results
estep   EQU     G+$5C           3
dvd     EQU     G+$5F           3  24 / 16 division
dvs     EQU     G+$62           2
rem     EQU     G+$64           3
dvcnt   EQU     G+$67           1
eneg    EQU     G+$68           1
ptyp    EQU     G+$69           1  0 solid polygon, 1 patterned
xl      EQU     G+$6A           2
xr      EQU     G+$6C           2
ccnt    EQU     G+$6E           1
trow    EQU     G+$6F           1  terminal
tcol    EQU     G+$70           1
tfg     EQU     G+$71           1
tbg     EQU     G+$72           1
tbold   EQU     G+$73           1
ttop    EQU     G+$74           2
trate   EQU     G+$76           1
tpace   EQU     G+$77           1
tlen    EQU     G+$78           2
tst8    EQU     G+$7A           1  escape state: 0 text, 1 ESC, 2 CSI
tnp     EQU     G+$7B           1  CSI parameters
tpar    EQU     G+$7C           4
trows   EQU     G+$8E           1  25, 30 or 50
ry0     EQU     G+$80           2  raster definition
rn      EQU     G+$82           1
ridx    EQU     G+$83           1
rbase   EQU     G+$84           2
tmp1    EQU     G+$86           2
tmp2    EQU     G+$88           2
lhy0    EQU     G+$8A           2  the LISTHS list's two lines, as built
lhy1    EQU     G+$8C           2
lxs     EQU     G+$90           16 polygon chains, eight vertices each
lys     EQU     G+$A0           16
rxs     EQU     G+$B0           16
rys     EQU     G+$C0           16
cbuf    EQU     G+$100          256 the pointer's save-behind
pats    EQU     G+$200          256 thirty-two 8x8 patterns
rgrad   EQU     G+$300          48  raster gradients
rsin    EQU     G+$330          256 raster positions
rcols   EQU     G+$430          256 raster colours per band line
wtab    EQU     G+$530          256 the wave's offsets, 0..255
wy0     EQU     G+$630          2  first line of the wave
wn      EQU     G+$632          2  lines in it
gsaveu  EQU     G+$634          2  the script pointer while the game runs
wamp    EQU     G+$636          1  the amplitude wsc was scaled for
lgodue  EQU     G+$637          1  a VBL has come and its frame's list is not started
wsc     EQU     G+$640          560 the scaled wave, tab repeated

LROW    EQU     500             the ring row the display lists live in
NOPS    EQU     $20

*******************************************************************************
* run - the interpreter. Enter with the script at page SCRPAGE, offset 0.
*******************************************************************************
run     lda     #SCRPAGE
        sta     spage
        lbsr    mapscr
        ldu     #0
        clr     ssp
        clr     cvis
        clr     lact
        ldd     #0
        std     ck
        std     ckph
        std     ox
        std     oy
        lbsr    resync
run1    lbsr    lyield          an op's operands can outlast the blank's end
        lbsr    sb
        cmpa    #NOPS
        bhs     runbad
        lsla
        ldx     #optab
        jsr     [a,x]
        bra     run1
runbad  lda     #$E8            an opcode the table does not have
        sta     <SIMPORT
        bra     *

optab   FDB     opend,opsync,opcheck,opctrl,oppal,opfill,oppat,optext
        FDB     opicon,oppoly,oppolyp,opimage,opcurs,ophide,opshow,opcall
        FDB     opret,oporg,oplisths,oplistof,opraster,oprastdf,oppatdef,opterm
        FDB     oprate,optinit,opgame,opmusic,optext8,opstop,opwavedf,opwave

* resync - put every register the shadows describe into a known state
resync  lbsr    idle
        clr     wmode
        lda     ctrlv
        sta     <VCTRL
        clr     wadvv
        clr     <WADV
        clr     wfgv
        clr     <WFG
        clr     wbgv
        clr     <WBG
        clr     splv
        clr     <SPANLEN
        rts

*******************************************************************************
* The script window.
*******************************************************************************
* sb - A := the next script byte
sb      lda     ,u+
        cmpu    #$2000
        beq     sb1
        rts
sb1     pshs    a
        inc     spage
        bsr     mapscr
        ldu     #0
        puls    a,pc

* sw - D := the next script word, big-endian
sw      bsr     sb
        pshs    a
        bsr     sb
        tfr     a,b
        puls    a,pc

mapscr  pshs    a
        lda     spage
        sta     <MAPLO+0
        lda     #$01
        sta     <MAPHI+0
        puls    a,pc

* mapgp - block 1 := ROM page gp
mapgp   pshs    a
        lda     gp
        sta     <MAPLO+1
        lda     #$01
        sta     <MAPHI+1
        puls    a,pc

* sxy - ax, ay := the next two words plus the origin
sxy     bsr     sw
        addd    ox
        std     ax
        bsr     sw
        addd    oy
        std     ay
        rts

clrck   pshs    d
        ldd     #0
        std     ck
        puls    d,pc

*******************************************************************************
* The card.
*******************************************************************************
* wready - SPANBUSY and LRUN both clear: graphics.md 7.4 and 10.3.1 - WPTR and
* the span registers may not be loaded under a span or while a list walks WPTR
*
* ⚠ AND WHILE A LIST IS ACTIVE IT RETURNS WITH /FIRQ MASKED, until golist's GO
* (or LISTOFF) unmasks it. A replayer tick costs up to 4 ms, and one that began
* in the ~3 ms between a list's END and the blank ran past line 0, so that
* frame had no list - every 42nd frame of the paint scroll, on the beat of the
* 50 Hz timer against the 59.94 Hz frame. Held off, the tick runs while the
* next list walks, which is time the CPU cannot draw in anyway; it is late by
* 3 ms at most, and the tempo timer's period is the card's, so none is lost.
wready  pshs    a
wry1    lda     <VSTAT
        bita    #$90
        bne     wry1
        tst     lact
        beq     wry9
        orcc    #$40            a list is active: no replayer tick until its GO
wry9    puls    a,pc

* setxy - WPTR := (ay << 10) | ax, once it may be loaded
setxy   lbsr    lyield
        bsr     wready
        pshs    d
        ldd     ay
        lslb
        rola
        lslb
        rola
        anda    #7              A = y >> 6, B = (y & 63) << 2
        pshs    a
        orb     ax              ... | x >> 8
        pshs    b
        ldb     ax+1
        stb     <WPTR0
        puls    b
        stb     <WPTR1
        puls    a
        sta     <WPTR2
        puls    d,pc

* setwm - A = the WMODE bits as CTRL holds them: $00 direct, $08 mask, $10
* solid, $18 sprite
setwm   cmpa    wmode
        beq     swm9
        bsr     wready
        sta     wmode
        ora     ctrlv
        sta     <VCTRL
swm9    rts

g_wadv    cmpa    wadvv
        beq     wd9
        bsr     wready
        sta     wadvv
        sta     <WADV
wd9     rts

g_wfg     cmpa    wfgv
        beq     wf9
        bsr     wready
        sta     wfgv
        sta     <WFG
wf9     rts

g_wbg     cmpa    wbgv
        beq     wb9
        bsr     wready
        sta     wbgv
        sta     <WBG
wb9     rts

spl     cmpa    splv
        beq     g_sp9
        bsr     wready
        sta     splv
        sta     <SPANLEN
g_sp9     rts

* lyield - start this frame's display list, if the blank's VBL has come and
* nothing has started the list yet.
*
* ⛔ WITHOUT THIS THE PAINT SCROLL FLICKERED AT 30 HZ. The list owns WPTR from
* its GO to its END (10.3.1). For the paint canvas that is line 430, so the CPU
* draws only in the ~2 ms before the blank. A scroll-bar drag step was ~16 ms
* of drawing (HIDE, the thumb's FILLs, CURS, SHOW), and only SYNC started the
* list, at the end of the step. So the list ran in one frame of two, and every
* other frame showed the whole canvas at HSCROLL 0. The emulator's recording
* and the machine's video both had LRUN at line 1 going 1, 0, 1, 0 through the
* drag. A 60 fps player that kept one frame in two showed a jump or a smooth
* scroll, depending on which frame it kept, and VLC showed the flicker.
* checkdemo.py now counts those frames.
*
* It is called from setxy, which is where every primitive loads WPTR from
* scratch, so a GO just before costs no primitive its pointer: setxy's wready
* then waits the list out before it loads. It is also called before each script
* op, because an op's operands can carry it past the blank's end. ax and ay
* belong to the caller, and golist uses them, so they are kept across it.
lyield  tst     lact
        beq     ly9
        tst     lgodue
        beq     ly9
        pshs    a
        lda     <VSTAT
        bita    #$40            still in the vertical blank?
        puls    a
        beq     ly9             no: this frame has gone without its list
        pshs    d,x
        ldd     ax
        ldx     ay
        pshs    d,x
        lbsr    golist
        puls    d,x
        std     ax
        stx     ay
        puls    d,x
ly9     rts

*******************************************************************************
* END, SYNC, CHECK, CTRL, PAL, ORG, PATDEF, RATE
*******************************************************************************
opend   bra     *

opsync  lbsr    sb
        sta     scnt
sy1     tst     lact
        bne     sy3
        ldx     fcnt
sy2     cmpx    fcnt
        beq     sy2
        bra     sy8
sy3     lbsr    golist
sy8     dec     scnt
        bne     sy1
        rts

* golist - start this frame's display list inside line 0 of the next frame.
* 10.3.2: WAIT counts scanlines from the GO, so the GO has to land at the
* same place every frame or the effects move; it is issued when VBLANK falls.
*
* ⚠ BOTH INTERRUPTS ARE MASKED FROM THE LAST LIST'S END TO THE GO, for two
* reasons. A replayer tick that runs past the blank costs the frame its list.
* And 10.3.3: a CPU register write in a dot the engine is granted costs the
* list a descriptor byte - and the VBL interrupt's handler writes VSTAT. /IRQ
* reaches the CPU ~0.4 ms after VBLANK rises, so taken normally it would land
* just after this GO, with the list walking. The request is served here
* instead, in the blank, before the GO.
golist  lbsr    wready          the last list has ended
        orcc    #$50
        clr     lgodue          our own setxy must not start it (lyield). Not
*                               before the orcc: a VBL served in wready sets it
gl1     lda     <VSTAT          into the vertical blank
        bita    #$40
        beq     gl1
        ldd     #0
        std     ax
        ldd     #LROW
        std     ay
        lbsr    setxy           WPTR := the list, while nothing is drawing
        lda     lact            2 RASTER, 3 WAVE: the phase the list holds
        cmpa    #2
        blo     gl3
        ldd     rph
        std     ckph
gl3     lda     <VSTAT          the VBL request, when it comes, is served at
        bita    #$01            once - it arrives a dozen lines into the blank,
        beq     gl3a            so the work is long done when the blank ends
        lbsr    vblwork
        bra     gl3
gl3a    bita    #$40
        bne     gl3
gl4     lda     #1
        sta     <BCTRL          GO
        clr     lgodue          this frame's list is started
        andcc   #$AF
        rts

opcheck lbsr    sw
        lbsr    idle
        std     ck
        rts

* CTRL v - and both scrolls back to 0, because every scene starts unscrolled
opctrl  lbsr    clrck
        lbsr    sb
        anda    #$E7
        sta     ctrlv
        lbsr    resync
        clr     <VSCROLL
        clr     <VSCRLH
        clr     <HSCROLL
        clr     <HSCRLH
        rts

* PAL first count (hi lo)*count. With the display on, 32 entries a vertical
* blank (graphics.md 13.1: a commit during active display snows).
oppal   lbsr    clrck
        lbsr    sb
        sta     ac              the next index
        lbsr    sb
        sta     an              entries left (0 = 256)
pa1     tst     ctrlv
        bpl     pa2
        lbsr    vblank
pa2     lda     ac
        sta     <PIDX
        lda     #32
        sta     acol
pa3     lbsr    sw
        stb     <PDATL
        sta     <PDATH          commits; PIDX steps
pa4     lda     <VSTAT          graphics.md 13.1: outside vertical blanking the commit
        bita    #$02            waits for the line's HLOAD, and b1 holds until it is done
        bne     pa4
        inc     ac
        dec     an
        beq     pa9
        tst     ctrlv
        bpl     pa3             display off: no need to wait for a blank
        dec     acol
        bne     pa3
        bra     pa1
pa9     rts

oporg   lbsr    sw
        std     ox
        lbsr    sw
        std     oy
        rts

oppatdef
        lbsr    sb
        ldb     #8
        mul
        addd    #pats
        tfr     d,x
        ldb     #8
g_pd1     lbsr    sb
        sta     ,x+
        decb
        bne     g_pd1
        rts

oprate  lbsr    sb
        sta     trate
        sta     tpace
        rts

*******************************************************************************
* FILL x y w h c - PaintRect
*******************************************************************************
opfill  lbsr    clrck
        lbsr    sxy
        lbsr    sw
        std     aw
        lbsr    sw
        std     ah
        lbsr    sb
        pshs    a
        lda     #$10
        lbsr    setwm
        puls    a
        lbsr    g_wfg
* rect - ax ay aw ah in WFG: strips of up to 256 across, each one WPTR load and
* one span-solid trigger per row, chained down by WADV 01
rect    lda     #1
        lbsr    g_wadv
g_rc1     ldd     aw
        cmpd    #256
        bls     g_rc2
        ldd     #256
g_rc2     std     tw
        decb
        tfr     b,a
        lbsr    spl
        lbsr    setxy
        ldx     ah
g_rc3     tst     <VSTAT          the reload is WADV's: never under a span
        bmi     g_rc3
        sta     <VDATA
        leax    -1,x
        bne     g_rc3
        ldd     ax
        addd    tw
        std     ax
        ldd     aw
        subd    tw
        std     aw
        bne     g_rc1
        rts

*******************************************************************************
* PAT x y w h fg bg p - FillRect with a pattern: span-mask, a column at a time
*******************************************************************************
oppat   lbsr    clrck
        lbsr    sxy
        lbsr    sw
        std     aw
        lbsr    sw
        std     ah
        lbsr    sb
        sta     afg
        lbsr    sb
        sta     abg
        lbsr    sb
        ldb     #8
        mul
        addd    #pats
        std     apx
        lda     #$08
        lbsr    setwm
        lda     afg
        lbsr    g_wfg
        lda     abg
        lbsr    g_wbg
        lda     #1
        lbsr    g_wadv
pt1     lbsr    setxy
        lda     ay+1
        anda    #7
        sta     arow
        ldy     ah
        ldx     apx
pt2     lda     arow
        lda     a,x             the pattern row is the mask
pt3     tst     <VSTAT
        bmi     pt3
        sta     <VDATA
        lda     arow
        inca
        anda    #7
        sta     arow
        leay    -1,y
        bne     pt2
        ldd     ax
        addd    #8
        std     ax
        ldd     aw
        subd    #8
        std     aw
        bne     pt1
        rts

*******************************************************************************
* TEXT x y fg bg n chars (8x16) and TEXT8 (8x8) - glyph blits
*******************************************************************************
optext  ldb     #16
        bra     tx0
optext8 ldb     #8
tx0     stb     ah+1
        lbsr    clrck
        lbsr    sxy
        lbsr    sb
        sta     afg
        lbsr    sb
        sta     abg
        lbsr    sb
        sta     an
        lda     abg
        cmpa    #$FF
        beq     tx1
        lda     #$08            opaque: span-mask, WBG behind
        lbsr    setwm
        lda     abg
        lbsr    g_wbg
        bra     tx2
tx1     lda     #$18            transparent: sprite mode
        lbsr    setwm
tx2     lda     afg
        lbsr    g_wfg
        lda     #1
        lbsr    g_wadv
        lda     #GFXPAGE
        sta     gp
        lbsr    mapgp
tx3     lbsr    sb
        ldb     ah+1
        cmpb    #16
        bne     tx4
        mul                     glyph * 16, in the first 4 KB
        addd    #$2000
        bra     tx5
tx4     mul                     glyph * 8, from 4 KB
        addd    #$3000
tx5     tfr     d,x
        lbsr    setxy
        ldb     ah+1
tx6     lda     ,x+
tx7     tst     <VSTAT
        bmi     tx7
        sta     <VDATA
        decb
        bne     tx6
        ldd     ax
        addd    #8
        std     ax
        dec     an
        bne     tx3
        rts

*******************************************************************************
* ICON x y n v - layers of 1bpp in sprite mode
*******************************************************************************
opicon  lbsr    clrck
        lbsr    sxy
        lbsr    sb
        sta     an
        lbsr    sb
        sta     av
        lda     #$18
        lbsr    setwm
        lda     #1
        lbsr    g_wadv
        lda     #ICNPAGE        the table: (page, offset) per icon
        sta     gp
        lbsr    mapgp
        ldb     an
        lda     #3
        mul
        addd    #$2000
        tfr     d,x
        lda     ,x
        adda    #ICNPAGE
        sta     gp
        ldx     1,x
        lbsr    mapgp
        leax    $2000,x
        lda     ,x+
        sta     ancol
        lda     ,x+
        sta     ah+1
        lda     ,x+
        sta     anl
        ldd     ax
        std     ax0
ic1     lda     ,x+             normal colour
        ldb     ,x+             selected colour
        tst     av
        beq     ic2
        tfr     b,a
ic2     lbsr    g_wfg
        lda     ,x+
        sta     apres
        ldd     ax0
        std     ax
        clr     acol
ic3     lsr     apres
        bcc     ic5
        lbsr    setxy
        ldb     ah+1
ic4     lda     ,x+
ic4a    tst     <VSTAT
        bmi     ic4a
        sta     <VDATA
        decb
        bne     ic4
ic5     ldd     ax
        addd    #8
        std     ax
        inc     acol
        lda     acol
        cmpa    ancol
        bne     ic3
        dec     anl
        bne     ic1
        rts

*******************************************************************************
* POLY c nl nr chains, POLYP fg bg p nl nr chains - features.md 6
*
* The chains run from the top vertex to the bottom one, left and right. Each
* edge steps x in 16.8 from (x0 << 8) + 128 by sign(dx) * (|dx| << 8) / dy per
* scanline, and a scanline covers [xl >> 8, xr >> 8). tools/show.py's
* Model.spans is the same rule, written again.
*******************************************************************************
oppoly  lbsr    clrck
        lbsr    sb
        sta     ac
        clr     ptyp
        bra     po1
oppolyp lbsr    clrck
        lbsr    sb
        sta     afg
        lbsr    sb
        sta     abg
        lbsr    sb
        ldb     #8
        mul
        addd    #pats
        std     apx
        lda     #1
        sta     ptyp
po1     lbsr    sb
        sta     nlv
        lbsr    sb
        sta     nrv
        ldx     #lxs
        ldb     nlv
        lbsr    rdchain
        ldx     #rxs
        ldb     nrv
        lbsr    rdchain
        lda     #0
        lbsr    g_wadv
        ldd     lys
        std     py
        ldb     nlv
        decb
        lslb
        ldx     #lys
        ldd     b,x
        std     yend
        clr     li
        clr     ri
        lda     #$FF
        sta     lcur
        sta     rcur
po2     ldd     py
        cmpd    yend
        lbhs    po9
* left: step past every vertex at or above this line, then set its edge up
po3     lda     li
        inca
        cmpa    nlv
        bhs     po4
        lsla
        ldx     #lys
        ldd     a,x
        cmpd    py
        bhi     po4
        inc     li
        bra     po3
po4     lda     li
        cmpa    lcur
        beq     po5
        sta     lcur
        ldx     #lxs
        lbsr    edge
        ldd     ex8
        std     lx8
        lda     ex8+2
        sta     lx8+2
        ldd     estep
        std     lstep
        lda     estep+2
        sta     lstep+2
po5     lda     ri
        inca
        cmpa    nrv
        bhs     po6
        lsla
        ldx     #rys
        ldd     a,x
        cmpd    py
        bhi     po6
        inc     ri
        bra     po5
po6     lda     ri
        cmpa    rcur
        beq     po7
        sta     rcur
        ldx     #rxs
        lbsr    edge
        ldd     ex8
        std     rx8
        lda     ex8+2
        sta     rx8+2
        ldd     estep
        std     rstep
        lda     estep+2
        sta     rstep+2
* the run
po7     ldd     lx8
        std     xl
        ldd     rx8
        std     xr
        subd    xl
        ble     po8
        lbsr    polyrun
* step both edges
po8     lda     lx8+2
        adda    lstep+2
        sta     lx8+2
        ldd     lx8
        adcb    lstep+1
        adca    lstep
        std     lx8
        lda     rx8+2
        adda    rstep+2
        sta     rx8+2
        ldd     rx8
        adcb    rstep+1
        adca    rstep
        std     rx8
        ldd     py
        addd    #1
        std     py
        lbra    po2
po9     rts

* rdchain - B vertices into X (x words) and X+16 (y words), plus the origin
rdchain stb     ccnt
rdc1    lbsr    sw
        addd    ox
        std     ,x
        lbsr    sw
        addd    oy
        std     16,x
        leax    2,x
        dec     ccnt
        bne     rdc1
        rts

* edge - A = vertex index, X = its chain's x array (y array at X+16): the edge
* from vertex A to A+1 into ex8 and estep
edge    pshs    x,y
        lsla
        leax    a,x
        ldd     ,x              x0
        std     ex8
        lda     #128
        sta     ex8+2
        ldd     18,x            dy = y1 - y0
        subd    16,x
        std     dvs
        clr     eneg
        ldd     2,x             dx = x1 - x0
        subd    ,x
        bpl     ed1
        inc     eneg
        coma
        comb
        addd    #1
ed1     std     dvd             (|dx| << 8) / dy
        clr     dvd+2
        lbsr    div24
        tst     eneg
        beq     ed2
        com     dvd
        com     dvd+1
        com     dvd+2
        lda     dvd+2
        adda    #1
        sta     dvd+2
        ldd     dvd
        adcb    #0
        adca    #0
        std     dvd
ed2     ldd     dvd
        std     estep
        lda     dvd+2
        sta     estep+2
        puls    x,y,pc

* div24 - dvd (24 bits) := dvd / dvs (16 bits), unsigned
div24   clr     rem
        clr     rem+1
        clr     rem+2
        lda     #24
        sta     dvcnt
dv1     lsl     dvd+2
        rol     dvd+1
        rol     dvd
        rol     rem+2
        rol     rem+1
        rol     rem
        tst     rem
        bne     dv2
        ldd     rem+1
        cmpd    dvs
        blo     dv3
dv2     ldd     rem+1
        subd    dvs
        std     rem+1
        bcc     dv2a
        dec     rem
dv2a    inc     dvd+2
dv3     dec     dvcnt
        bne     dv1
        rts

* polyrun - xl..xr-1 on line py: span-solid, and for a patterned polygon the
* pattern over it in sprite mode
polyrun lda     #$10
        lbsr    setwm
        lda     ac
        tst     ptyp
        beq     g_pr1
        lda     abg
g_pr1     lbsr    g_wfg
        ldd     xl
        std     ax
        ldd     py
        std     ay
        lbsr    setxy
        ldd     xr
        subd    xl
        std     arem
pr2     ldd     arem
        cmpd    #256
        bls     pr3
        ldd     #256
pr3     std     tw
        decb
        tfr     b,a
        lbsr    spl
        sta     <VDATA
        ldd     arem
        subd    tw
        std     arem
        bne     pr2
        tst     ptyp
        bne     pr4
        rts
* the pattern: whole 8-pixel blocks from xl & ~7, the ends masked off
pr4     lda     #$18
        lbsr    setwm
        lda     afg
        lbsr    g_wfg
        ldd     xl
        andb    #$F8
        std     ax
        lbsr    setxy
        ldx     apx
        lda     py+1
        anda    #7
        lda     a,x
        sta     arow            this line's pattern row
pr5     lda     arow
        pshs    a
        ldd     xl              head: pixels left of xl are not the run's
        subd    ax
        ble     pr7
        lda     #$FF            A := $FF >> (xl - ax), the pixels from xl on
pr6     lsra
        decb
        bne     pr6
        anda    ,s
        sta     ,s
pr7     ldd     xr              tail: pixels from xr on are not either
        subd    ax
        cmpd    #8
        bge     pr9
        ldb     #8
        subb    xr+1
        addb    ax+1            B = 8 - (xr - ax), 1..7
        lda     #$FF
pr8     lsla
        decb
        bne     pr8
        anda    ,s
        sta     ,s
pr9     puls    a
pr9a    tst     <VSTAT
        bmi     pr9a
        sta     <VDATA
        ldd     ax
        addd    #8
        std     ax
        cmpd    xr
        blo     pr5
        rts

*******************************************************************************
* IMAGE x y w h - 8bpp from the image asset: the CPU moves every byte
*******************************************************************************
opimage lbsr    clrck
        lbsr    sxy
        lbsr    sw
        std     aw
        lbsr    sw
        std     ah
        lda     #$00
        lbsr    setwm
        lda     #0
        lbsr    g_wadv
        lda     #IMGPAGE
        sta     gp
        lbsr    mapgp
        ldx     #$2000
im1     lbsr    setxy
        ldd     aw
        std     arem
im2     tfr     x,d             D = bytes to the end of the window
        coma
        comb
        addd    #$4001
        cmpd    #255
        bls     im3
        ldd     #255
im3     cmpd    arem
        bls     im4
        ldd     arem
im4     std     ach
        ldd     arem
        subd    ach
        std     arem
        ldb     ach+1
im5     lda     ,x+
        sta     <VDATA
        decb
        bne     im5
        cmpx    #$4000
        bne     im6
        inc     gp
        lbsr    mapgp
        ldx     #$2000
im6     ldd     arem
        bne     im2
        ldd     ay
        addd    #1
        std     ay
        ldd     ah
        subd    #1
        std     ah
        bne     im1
        rts

*******************************************************************************
* The pointer. Save-behind is read back through VRAM; the arrow is two
* layers in sprite mode, so nothing outside its shape is written.
*******************************************************************************
* vwin - block 1 := the VRAM window (graphics.md 6.3), where every address is
* the VDATA port: a load or a store of D there moves two bytes at WPTR.
*
* ⚠ THE POINTER IS HALF OF A SCROLL-BAR DRAG STEP'S TIME. With a display list
* running every frame the CPU draws only between the list's END and the next
* blank (lyield), and a byte at a time, lda <VDATA / sta ,x+, the save-behind
* alone took 3.5 ms of it. ldd VRAMW / std ,x++ is 14 E cycles a pair against 30.
* Every other user of block 1 maps it before it reads (mapgp, romat), so it is
* left pointing here.
VRAMW   EQU     $2000           block 1, when vwin has pointed it
vwin    clr     <MAPHI+1
        lda     #$40
        sta     <MAPLO+1
        rts

opcurs  lbsr    clrck
        lbsr    sw
        std     tmp1
        lbsr    sw
        std     tmp2
        tst     cvis
        beq     cu1
        bsr     chide
        ldd     tmp1
        std     cx
        ldd     tmp2
        std     cy
        lbra    cshow
cu1     ldd     tmp1
        std     cx
        ldd     tmp2
        std     cy
        rts

ophide  lbsr    clrck
chide   tst     cvis
        beq     ch9
        clr     cvis
        lda     #$00
        lbsr    setwm
        lda     #0
        lbsr    g_wadv
        ldd     cx
        std     ax
        ldd     cy
        std     ay
        lbsr    vwin
        ldx     #cbuf
        lda     #CURH
        sta     ccnt
ch1     lbsr    setxy
        ldd     ,x++            eight pairs: CURW is 16 (show.py)
        std     VRAMW
        ldd     ,x++
        std     VRAMW
        ldd     ,x++
        std     VRAMW
        ldd     ,x++
        std     VRAMW
        ldd     ,x++
        std     VRAMW
        ldd     ,x++
        std     VRAMW
        ldd     ,x++
        std     VRAMW
        ldd     ,x++
        std     VRAMW
        ldd     ay
        addd    #1
        std     ay
        dec     ccnt
        bne     ch1
ch9     rts

opshow  lbsr    clrck
cshow   tst     cvis
        bne     cs9
        inc     cvis
        lda     #$00
        lbsr    setwm
        lda     #0
        lbsr    g_wadv
        ldd     cx
        std     ax
        ldd     cy
        std     ay
        lbsr    vwin
        ldx     #cbuf
        lda     #CURH
        sta     ccnt
cs1     lbsr    setxy
        ldd     VRAMW            graphics.md 11: the byte at WPTR, and WPTR steps
        std     ,x++
        ldd     VRAMW
        std     ,x++
        ldd     VRAMW
        std     ,x++
        ldd     VRAMW
        std     ,x++
        ldd     VRAMW
        std     ,x++
        ldd     VRAMW
        std     ,x++
        ldd     VRAMW
        std     ,x++
        ldd     VRAMW
        std     ,x++
        ldd     ay
        addd    #1
        std     ay
        dec     ccnt
        bne     cs1
        lda     #$18
        lbsr    setwm
        lda     #1
        lbsr    g_wadv
        lda     #CUR_BLACK
        lbsr    g_wfg
        ldx     #curol
        bsr     ccol2
        lda     #CUR_WHITE
        lbsr    g_wfg
        ldx     #curfl
        bsr     ccol2
cs9     rts
* ccol2 - the two 16-row columns of one layer at the pointer
ccol2   ldd     cx
        std     ax
        ldd     cy
        std     ay
        lbsr    g_ccol
        ldd     cx
        addd    #8
        std     ax
g_ccol    lbsr    setxy
        ldb     #CURH
g_cc2     lda     ,x+
cc3     tst     <VSTAT
        bmi     cc3
        sta     <VDATA
        decb
        bne     g_cc2
        rts

*******************************************************************************
* CALL off24, RET - script subroutines
*******************************************************************************
opcall  lbsr    sb              off24: page = off >> 13, pointer = off & $1FFF
        sta     tmp1
        lbsr    sw
        std     tmp2
        ldb     ssp             push (page, U)
        lda     #3
        mul
        ldx     #sstk
        abx
        lda     spage
        sta     ,x
        stu     1,x
        inc     ssp
        lda     tmp1
        lsla
        lsla
        lsla
        ldb     tmp2
        lsrb
        lsrb
        lsrb
        lsrb
        lsrb
        stb     tmp1+1
        ora     tmp1+1
        adda    #SCRPAGE
        sta     spage
        lbsr    mapscr
        ldd     tmp2
        anda    #$1F
        tfr     d,u
        rts

opret   dec     ssp
        ldb     ssp
        lda     #3
        mul
        ldx     #sstk
        abx
        lda     ,x
        sta     spage
        ldu     1,x
        lbsr    mapscr
        rts

*******************************************************************************
* LISTHS y0 y1 v, LISTOFF - a split horizontal scroll by display list
*
* The list: y0 WAITs, MOVE HSCROLL/HSCROLLH := v, y1 - y0 WAITs, MOVE both
* back to 0, END. It is rebuilt whole - under 1 KB - in ring row LROW, and
* golist starts it every frame. graphics.md 10.3.2's per-scanline scroll.
*******************************************************************************
oplisths
        lbsr    clrck
        lbsr    sw
        std     tmp1            y0
        lbsr    sw
        std     tmp2            y1
        lbsr    sw
        std     aw              v
        lda     #$00
        lbsr    setwm
        lda     #0
        lbsr    g_wadv
* the same two lines as the list already there: patch its MOVE operands only
        lda     lact
        cmpa    #1
        bne     lh0
        ldd     tmp1
        cmpd    lhy0
        bne     lh0
        ldd     tmp2
        cmpd    lhy1
        bne     lh0
        ldd     tmp1
        std     ax
        ldd     #LROW
        std     ay
        lbsr    setxy
        lda     #$03
        sta     <VDATA
        lda     aw+1
        sta     <VDATA
        lda     #$04
        sta     <VDATA
        lda     aw
        anda    #3
        sta     <VDATA
        rts
lh0     ldd     tmp1
        std     lhy0
        ldd     tmp2
        std     lhy1
        ldd     #0
        std     ax
        ldd     #LROW
        std     ay
        lbsr    setxy
        ldx     tmp1
        beq     lh2
        lda     #$80
lh1     sta     <VDATA
        leax    -1,x
        bne     lh1
lh2     lda     #$03
        sta     <VDATA
        lda     aw+1
        sta     <VDATA
        lda     #$04
        sta     <VDATA
        lda     aw
        anda    #3
        sta     <VDATA
        ldd     tmp2
        subd    tmp1
        tfr     d,x
        beq     lh4
        lda     #$80
lh3     sta     <VDATA
        leax    -1,x
        bne     lh3
lh4     ldx     #lhtail
        ldb     #5
lh5     lda     ,x+
        sta     <VDATA
        decb
        bne     lh5
        lda     #1
        sta     lact
        rts
lhtail  FCB     $03,$00,$04,$00,$FF

oplistof
        lbsr    clrck
        lbsr    wready
        clr     lact
        clr     <HSCROLL
        clr     <HSCRLH
        ldd     #0
        std     ckph
        andcc   #$BF            wready held the replayer off for the GO: no more GOs
        rts

*******************************************************************************
* RASTDEF y0 n idx base grad sin, RASTER ph - raster bars by display list
*
* Band line i is scanlines y0 + 2i and y0 + 2i + 1. Its colour is the base,
* unless one of three bars covers it: bar b is centred on band line
* sin[(ph + 85 b) & 255] and coloured grad[b][distance] out to distance 7,
* later bars over earlier. The list: y0 WAITs (written once), then per band
* line MOVE PIDX,idx / PDATL,lo / PDATH,hi / WAIT / WAIT, then the base back
* and END. Each phase rewrites the band's 8n + 7 bytes.
*******************************************************************************
oprastdf
        lbsr    clrck
        lbsr    sw
        std     ry0
        lbsr    sb
        sta     rn
        lbsr    sb
        sta     ridx
        lbsr    sw
        std     rbase
        ldx     #rgrad
        ldb     #48
rd1     lbsr    sb
        sta     ,x+
        decb
        bne     rd1
        ldx     #rsin
        clrb
rd2     lbsr    sb
        sta     ,x+
        decb
        bne     rd2
        lda     #$00            the y0 WAITs, once
        lbsr    setwm
        lda     #0
        lbsr    g_wadv
        ldd     #0
        std     ax
        ldd     #LROW
        std     ay
        lbsr    setxy
        ldx     ry0
        lda     #$80
rd3     sta     <VDATA
        leax    -1,x
        bne     rd3
        lda     #$FF            END, until the first RASTER writes a band
        sta     <VDATA
        clr     rph
        clr     rph+1
        lda     #2
        sta     lact
        rts

opraster
        lbsr    sb
        sta     tmp1            ph
* every band line starts at the base colour
        ldx     #rcols
        lda     rn
        sta     acol
ra1     ldd     rbase
        std     ,x++
        dec     acol
        bne     ra1
* three bars
        clr     tmp2            bar
ra2     lda     tmp2            centre = sin[(ph + 85 * bar) & 255]
        ldb     #85
        mul
        addb    tmp1
        ldx     #rsin
        abx                     unsigned: an 8-bit index register offset is signed
        lda     ,x
        sta     tmp2+1
        clr     acol            i
ra3     lda     acol
        suba    tmp2+1          distance
        bpl     ra4
        nega
ra4     cmpa    #8
        bhs     ra5
        pshs    a               grad[bar][d]: rgrad + (bar * 8 + d) * 2
        lda     tmp2
        lsla
        lsla
        lsla
        adda    ,s+
        lsla
        ldx     #rgrad
        leax    a,x
        ldd     ,x
        pshs    d
        ldb     acol
        clra
        lslb
        rola
        ldx     #rcols
        leax    d,x
        puls    d
        std     ,x
ra5     inc     acol
        lda     acol
        cmpa    rn
        bne     ra3
        inc     tmp2
        lda     tmp2
        cmpa    #3
        bne     ra2
* the band, into the list after the WAITs
        lda     #$00
        lbsr    setwm
        lda     #0
        lbsr    g_wadv
        ldd     ry0
        std     ax
        ldd     #LROW
        std     ay
        lbsr    setxy
        ldx     #rcols
        ldb     rn
ra6     lda     #$10
        sta     <VDATA
        lda     ridx
        sta     <VDATA
        lda     #$11
        sta     <VDATA
        lda     1,x
        sta     <VDATA
        lda     #$12
        sta     <VDATA
        lda     ,x++
        sta     <VDATA
        lda     #$80
        sta     <VDATA
        sta     <VDATA
        decb
        bne     ra6
        lda     #$10
        sta     <VDATA
        lda     ridx
        sta     <VDATA
        lda     #$11
        sta     <VDATA
        lda     rbase+1
        sta     <VDATA
        lda     #$12
        sta     <VDATA
        lda     rbase
        sta     <VDATA
        lda     #$FF
        sta     <VDATA
        ldb     tmp1
        clra
        addd    #1
        std     rph
        rts

*******************************************************************************
* The terminal - TINIT, TERM n bytes
*
* 80 x 25, 30 or 50 cells of 8 x 8 - VMODE 00, 01 or 10. A cell is span-mask with
* WADV 01: one WPTR load and eight glyph rows (features.md 2.3). The screen's
* top is ring row ttop, and a scroll is VSCROLL := ttop + 8 and one blank row
* written below the old bottom - graphics.md 8's scroll, not a copy.
*******************************************************************************
optinit lbsr    clrck
        lbsr    sb
        sta     trows
        clr     trow
        clr     tcol
        lda     #7
        sta     tfg
        clr     tbg
        clr     tbold
        clr     tst8
        ldd     #0
        std     ttop
        lbsr    wready
        clr     <VSCROLL
        clr     <VSCRLH
        clr     <HSCROLL
        clr     <HSCRLH
        ldd     #0
        std     ax
        std     ay
        lbsr    tscreen
        clra
        lbsr    tclear
        rts
* tscreen - aw, ah := the whole screen, 640 x rows * 8
tscreen ldd     #640
        std     aw
        lda     trows
        ldb     #8
        mul
        std     ah
        rts

* tclear - ax ay aw ah in colour A, span-solid
tclear  pshs    a
        lda     #$10
        lbsr    setwm
        puls    a
        lbsr    g_wfg
        lbra    rect

opterm  lbsr    clrck
        lbsr    sw
        std     tlen
te1     ldd     tlen
        beq     te9
        subd    #1
        std     tlen
        lbsr    sb
        bsr     tchar
        tst     trate
        beq     te1
        dec     tpace
        bne     te1
        lda     trate
        sta     tpace
        ldx     fcnt            one frame's worth has gone out
te2     cmpx    fcnt
        beq     te2
        bra     te1
te9     rts

* tchar - one byte into the terminal
tchar   ldb     tst8
        beq     tc10
        cmpb    #1
        beq     tc20
        lbra    tc30
tc10    cmpa    #27
        bne     tc11
        inc     tst8
        rts
tc11    cmpa    #13
        bne     tc12
        clr     tcol
        rts
tc12    cmpa    #10
        bne     tc13
        lbra    tlf
tc13    cmpa    #8
        bne     tc14
        tst     tcol
        beq     tc19
        dec     tcol
        rts
tc14    cmpa    #7
        beq     tc19
        tsta
        beq     tc19
        lbra    tglyph
tc19    rts
tc20    cmpa    #'[
        bne     tc21
        inc     tst8
        clr     tnp
        clr     tpar
        clr     tpar+1
        clr     tpar+2
        clr     tpar+3
        rts
tc21    clr     tst8
        rts
* CSI: digits and ';' collect up to four parameters; a final byte acts
tc30    cmpa    #'0
        blo     tc32
        cmpa    #'9
        bhi     tc32
        suba    #'0
        pshs    a
        ldx     #tpar
        ldb     tnp
        abx
        lda     ,x              p = p * 10 + digit
        ldb     #10
        mul
        addb    ,s+
        stb     ,x
        rts
tc32    cmpa    #';
        bne     tc33
        lda     tnp
        cmpa    #3
        bhs     tc39
        inc     tnp
tc39    rts
tc33    clr     tst8
        cmpa    #'m
        lbeq    tsgr
        cmpa    #'J
        lbeq    ted
        cmpa    #'H
        lbeq    tcup
        cmpa    #'f
        lbeq    tcup
        cmpa    #'K
        lbeq    tel
        cmpa    #'C
        beq     tcuf
        cmpa    #'D
        beq     tcub
        cmpa    #'A
        beq     tcuu
        cmpa    #'B
        beq     tcud
        rts
* the count parameter, at least 1
tcnt    lda     tpar
        bne     tn1
        inca
tn1     rts
tcuf    bsr     tcnt
        adda    tcol
        cmpa    #79
        bls     tf1
        lda     #79
tf1     sta     tcol
        rts
tcub    bsr     tcnt
        pshs    a
        lda     tcol
        suba    ,s+
        bcc     tb1
        clra
tb1     sta     tcol
        rts
tcuu    bsr     tcnt
        pshs    a
        lda     trow
        suba    ,s+
        bcc     tu1
        clra
tu1     sta     trow
        rts
tcud    bsr     tcnt
        adda    trow
        cmpa    trows
        blo     td1
        lda     trows
        deca
td1     sta     trow
        rts
tcup    lda     tpar
        beq     g_tp1
        deca
g_tp1   cmpa    trows
        blo     g_tp2
        lda     trows
        deca
g_tp2   sta     trow
        lda     tpar+1
        beq     g_tp3
        deca
g_tp3     cmpa    #79
        bls     tp4
        lda     #79
tp4     sta     tcol
        rts
ted     lda     tpar            only 2J: clear and home
        cmpa    #2
        bne     tj9
        ldd     #0
        std     ax
        ldd     ttop
        std     ay
        lbsr    tscreen
        clra
        lbsr    tclear
        clr     trow
        clr     tcol
tj9     rts
tel     lda     tcol            erase to the end of the line, in the background
        cmpa    #80
        bhs     tk9
        ldb     #8
        mul
        std     ax
        lda     trow
        ldb     #8
        mul
        addd    ttop
        std     ay
        lda     #80
        suba    tcol
        ldb     #8
        mul
        std     aw
        ldd     #8
        std     ah
        lda     tbg
        lbsr    tclear
tk9     rts
tsgr    ldx     #tpar
        ldb     tnp
        incb
tg1     lda     ,x+
        pshs    b
        bsr     sgr1
        puls    b
        decb
        bne     tg1
        rts
sgr1    tsta
        bne     sg1
        lda     #7
        sta     tfg
        clr     tbg
        clr     tbold
        rts
sg1     cmpa    #1
        bne     sg2
        sta     tbold
        rts
sg2     cmpa    #22
        bne     sg3
        clr     tbold
        rts
sg3     cmpa    #30
        blo     sg9
        cmpa    #37
        bhi     sg4
        suba    #30
        sta     tfg
        rts
sg4     cmpa    #39
        bne     sg5
        lda     #7
        sta     tfg
        rts
sg5     cmpa    #40
        blo     sg9
        cmpa    #47
        bhi     sg6
        suba    #40
        sta     tbg
        rts
sg6     cmpa    #49
        bne     sg9
        clr     tbg
sg9     rts

* tlf - a line feed: down a row, or scroll
tlf     lda     trow
        inca
        cmpa    trows
        beq     tl1
        sta     trow
        rts
tl1     ldd     ttop
        addd    #8
        anda    #1
        std     ttop
        lbsr    wready
        stb     <VSCROLL        loads in the vertical blank (graphics.md 8)
        sta     <VSCRLH
        ldd     #0
        std     ax
        lda     trows           the new bottom row: ttop + (rows - 1) * 8
        deca
        ldb     #8
        mul
        addd    ttop
        std     ay
        ldd     #640
        std     aw
        ldd     #8
        std     ah
        clra
        lbra    tclear

* tglyph - A = a character at the cursor, then the cursor steps
tglyph  pshs    a
        lda     tcol
        cmpa    #80
        blo     tgl1
        clr     tcol
        bsr     tlf
tgl1    lda     #$08
        lbsr    setwm
        lda     tfg
        tst     tbold
        beq     tgl2
        adda    #8
tgl2    lbsr    g_wfg
        lda     tbg
        lbsr    g_wbg
        lda     #1
        lbsr    g_wadv
        lda     tcol
        ldb     #8
        mul
        std     ax
        lda     trow
        ldb     #8
        mul
        addd    ttop
        std     ay
        lda     #GFXPAGE
        sta     gp
        lbsr    mapgp
        puls    a
        ldb     #8
        mul
        addd    #$3000
        tfr     d,x
        lbsr    setxy
        ldb     #8
tgl3    lda     ,x+
tgl4    tst     <VSTAT
        bmi     tgl4
        sta     <VDATA
        decb
        bne     tgl3
        inc     tcol
        rts

*******************************************************************************
* GAME, MUSIC
*******************************************************************************
opgame  lbsr    clrck
        stu     gsaveu          gamego comes back here after one pass of the world
        lbsr    gamego
        ldu     gsaveu
        lbsr    mapscr
        clr     lact
        lbsr    resync
        rts

opmusic pshs    u               the replayer's routines use U
        lbsr    mod_load
        beq     mu1
        sta     <SIMPORT        the loader's reason, and stop
        bra     *
mu1     lbsr    mod_start
        andcc   #$BF            unmask FIRQ: the replayer runs from here on
        lda     #P_MUSIC
        sta     <SIMPORT
        puls    u
        lbsr    mapscr          the loader used block 0
        rts

*******************************************************************************
* STOP - the audio player's Stop: the tempo timer's interrupt, the four
* channels' DMA and the card's enable, off, in that order (mod_start turns them
* on in the other). /FIRQ stays masked from here on.
*******************************************************************************
opstop  orcc    #$40
        pshs    u
        lda     #$10            AINTENA: clear the timer's enable (b7 = 0 clears)
        ldb     #R_AINTENA
        lbsr    wr
        lda     #$0F            ADMACON: clear all four channels
        ldb     #R_ADMACON
        lbsr    wr
        lda     actrl
        anda    #$3F            ACTRL: master enable and tempo timer off
        sta     actrl
        ldb     #R_ACTRL
        lbsr    wr
        lda     #$10            AINTREQ: and the request that may be pending
        ldb     #R_AINTREQ
        lbsr    wr
        puls    u
        lda     #P_STOP
        sta     <SIMPORT
        rts

*******************************************************************************
* WAVEDF y0 n tab(256), WAVE ph amp - a sine warp of 2n lines from y0, by
* display list: lines y0 + 2i and y0 + 2i + 1 are scrolled by
* (tab[(ph + 2i) & 255] * amp) >> 8 pixels - a fine HSCROLL MOVE every two
* lines, which graphics.md 19 item 49 is what makes smooth rather than in fours.
* The list: y0 WAITs (written once), then per entry MOVE HSCROLL,v / WAIT /
* WAIT, then HSCROLL back to 0 and END. HSCROLLH is never written: the offsets
* are 0..amp, and the register holds 0.
*
* ⚠ THE REWRITE HAS TO FIT BETWEEN THE LIST'S END AND THE NEXT BLANK, or that
* frame has no list. A MUL per entry did not; the scaled table is rebuilt only
* when the amplitude changes, and it runs 560 entries long so the per-frame
* loop never wraps.
*******************************************************************************
opwavedf
        lbsr    clrck
        lbsr    sw
        std     wy0
        lbsr    sw
        std     wn
        ldx     #wtab
        clrb
wv1     lbsr    sb
        sta     ,x+
        decb
        bne     wv1
        lda     #$FF            no scaled table yet: no amplitude is $FF
        sta     wamp
        lda     #$00
        lbsr    setwm
        lda     #0
        lbsr    g_wadv
        ldd     #0
        std     ax
        ldd     #LROW
        std     ay
        lbsr    setxy
        ldx     wy0
        lda     #$80
wv2     sta     <VDATA
        leax    -1,x
        bne     wv2
        lda     #$FF            END, until the first WAVE writes the lines
        sta     <VDATA
        clr     rph
        clr     rph+1
        lda     #3
        sta     lact
        rts

opwave  lbsr    sb
        sta     tmp1            ph
        lbsr    sb
        sta     tmp1+1          amp
        cmpa    wamp
        beq     wv5
        sta     wamp            wsc[k] := tab[k & 255] * amp >> 8, k < 560
        pshs    u
        ldx     #wtab
        ldu     #wsc
        ldy     #560
wv6     tfr     x,d             the table index is X's low byte
        ldx     #wtab
        abx
        lda     ,x
        ldb     wamp
        mul
        sta     ,u+
        leay    -1,y
        beq     wv7
        tfr     u,d
        subd    #wsc
        tfr     d,x             X := k, and its low byte indexes the table
        bra     wv6
wv7     puls    u
wv5     lda     #$00
        lbsr    setwm
        lda     #0
        lbsr    g_wadv
        ldd     wy0
        std     ax
        ldd     #LROW
        std     ay
        lbsr    setxy
        ldx     #wsc
        ldb     tmp1
        abx                     X := wsc + ph
        ldy     wn
        ldb     #$03
wv3     stb     <VDATA
        lda     ,x++
        sta     <VDATA
        lda     #$80
        sta     <VDATA
        sta     <VDATA
        leay    -1,y
        bne     wv3
        ldx     #wvtail
        ldb     #3
wv4     lda     ,x+
        sta     <VDATA
        decb
        bne     wv4
        ldb     tmp1+1          rph := (amp << 8 | ph) + 1
        stb     rph
        ldb     tmp1
        stb     rph+1
        ldd     rph
        addd    #1
        std     rph
        rts
wvtail  FCB     $03,$00,$FF
