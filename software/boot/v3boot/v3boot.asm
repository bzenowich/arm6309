*******************************************************************************
* v3boot.asm -- a test fixture, not a boot ROM.
*
* It is the program hardware/video3/sim/v3machine_tb.sv runs on the real
* design: Greg Miller's cycle-accurate 6809E core in the socket, mainboard.v
* under it, and video3_card.v (v3dot, v3scan, v3ptr, v3host, v3lane and the
* board of hardware/video3/docs/plan.md 13.1) in the slot.  Nothing here runs against a
* behavioural model of the machine; there isn't one.
*
* ⭐ WHY IT IS NOT software/boot/boot.asm.  That ROM is the machine's boot
* monitor, and since 2026-09-20 it drives THIS card too -- hardware/video3/docs/plan.md
* 10, the same map as below (docs/history.md 7.2).  They stay two programs
* because they answer different questions.  boot.asm is a POST: it sizes the
* SIMM bank, probes for the card, bounds every poll and has an error code for
* each stage, because it runs on hardware that may be broken.  This is a
* FIXTURE for one bench: it does the smallest boot that reaches RAM and then
* spends all of its time on the card, at points in the frame chosen on purpose
* (2a), with its polls deliberately unbounded because v3machine_tb.sv is what
* bounds them.  What is here and not in boot.asm is the VBL interrupt (8) and
* the auto-increment experiment (2a); what is in boot.asm and not here is the
* card probe, tile mode and the four VMODEs.
*
* WHAT IT DOES, in order:
*   1.  writes a map, leaves boot mode, and then USES that map -- the stack and
*       the variables through block 6, the card's VRAM window through block 1
*   2a. ⭐ eight palette entries with PIDX left to auto-increment, written at
*       the TOP OF THE ACTIVE AREA so the commit takes v3host's HLOAD path and
*       not its VBLANK one -- which is the difference that matters (see below)
*   2b. 256 palette entries through PIDX/PDATL/PDATH, entry i = $(~i)(i), so a
*       displayed pixel names the index it came from
*   3.  eight direct VDATA writes, and eight post-incrementing VDATA reads back
*   4.  a span-solid, 64 bytes
*   5.  an 8x8 glyph: eight span-mask writes chained by WADV 01
*   6.  a copyrect of that glyph to somewhere else
*   7.  three 256-byte spans back to back THROUGH THE VRAM WINDOW, with no poll
*       between them -- so the card must hold the CPU with /WAIT
*   8.  display on, VBL interrupt on, and a handler that counts frames into the
*       card's own +$1F
*
* Every drawn byte's place and value is arithmetic, so the bench can predict
* the whole 640 x 200 picture: what this ROM did not draw is the background the
* bench put in VRAM before reset, and what it drew is below.
*
* ⛔ WHAT IT FOUND, 2026-09-19, and why 2b writes PIDX for every entry.
* Outside VBLANK the posted palette commit fires on EVERY DOT of HLOAD rather
* than once: v3host holds PPEND with `PPEND & ~PS0`, so PS0 is set again on
* HLOAD's second dot, the LUT is written twice one dot apart and PIDXCE steps
* the index TWICE. A 256-entry load that leans on the auto-increment therefore
* writes 479 entries at every other address, wraps, and comes back over the
* ones it got right. 2a asks that question once, deliberately and in one
* place; 2b writes the index itself so that the picture does not depend on the
* answer.
*
* ⚠ THE POLLING LOOPS HERE ARE UNBOUNDED, and deliberately: this is the
* machine's software, and software polls a status bit.  The BENCH is what
* bounds them -- every wait_progress in v3machine_tb.sv has an iteration limit
* and fails loudly, so a card that never clears SPANBUSY is a failed claim and
* not a hung simulation.
*
* Assembled by A09 (software/tools/fetch-a09.sh); sh software/boot/v3boot/mkv3rom.sh
* writes v3boot.bin / .hex / .lst beside this file.
*******************************************************************************

*------------------------------------------------------------------ the map --
* machine.md 3.  Two windows, one index: entry n is task n>>3, block n&7.
MAPHI   EQU     $FF90           high byte -- physical A24..A21 (ram.md 4.3)
MAPLO   EQU     $FFA0           low byte  -- physical A20..A13
TASKR   EQU     $FFB0           TASK, and $FFB0 is EVEN so it stays in boot mode
RUNSTB  EQU     $FFB1           the strobe that leaves it -- one way per reset

*------------------------------------------------- video3, plan.md 10 --------
VBASE   EQU     $FF60
VCTRL   EQU     VBASE+$00       b1-0 VMODE, b3-2 MODE, b5-4 WMODE, b6 IRQEN, b7 DISPEN
VSCRL   EQU     VBASE+$01
VSCRLH  EQU     VBASE+$02
HSCRL   EQU     VBASE+$03
HSCRLH  EQU     VBASE+$04
SPANLEN EQU     VBASE+$05       span length - 1
WFG     EQU     VBASE+$06
WBG     EQU     VBASE+$07
WPTR0   EQU     VBASE+$08       A7..A0
WPTR1   EQU     VBASE+$09       A15..A8
WPTR2   EQU     VBASE+$0A       A18..A16
WADV    EQU     VBASE+$0B       00 continue, 01 next row same column, b2 step by two
VDATA   EQU     VBASE+$0C       the VRAM byte at WPTR, either way, post-increment
VSTAT   EQU     VBASE+$0D       b7 SPANBUSY b6 VBLANK b5 HBLANK b4 CBUSY b1 PBUSY b0 IRQ
PIDXL   EQU     VBASE+$0E       palette index, 16 bits, ++ after PDATH
PIDXH   EQU     VBASE+$0F
PDATL   EQU     VBASE+$10       GGGBBBBB
PDATH   EQU     VBASE+$11       RRRRRGGG -- the write posts the commit
CPTR0   EQU     VBASE+$12       copyrect source, 19 bits
CPTR1   EQU     VBASE+$13
CPTR2   EQU     VBASE+$14
CWIDTH  EQU     VBASE+$15       bytes a row
CHEIGHT EQU     VBASE+$16       rows -- ⚠ counts ONCE a copy, reload it each time
CCTRL   EQU     VBASE+$17       b0 GO
FCNT    EQU     VBASE+$1F       plan 10's spare byte: the VBL service's frame count

* CTRL bit patterns.  VMODE 00 = 640x200 (400 lines, doubled), MODE 00 bitmap.
CT_OFF  EQU     $00             display off, WMODE 00 direct
CT_MSK  EQU     $10             display off, WMODE 01 span-mask
CT_SOL  EQU     $20             display off, WMODE 10 span-solid
CT_ON   EQU     $80             display ON, WMODE 00 direct
CT_ONI  EQU     $C0             ... and the VBL interrupt enabled

*-------------------------------------------------------------- the machine --
VRAMWIN EQU     $2000           logical block 1 -- the card's VRAM window
RAMWIN  EQU     $C000           logical block 6 -- the first SIMM
STACK   EQU     $E000           grows down through block 6
SIMPORT EQU     $FF2F           machine.md 3's free page; the bench watches it

* Variables.  Block 6, so nothing here is touched before step 1 has proved the
* SIMM answers.
frames  EQU     RAMWIN+$10      the VBL handler's frame counter
expect  EQU     RAMWIN+$11      the byte the VDATA read-back wants next
ptmp    EQU     RAMWIN+$12      setptr's scratch (2 bytes)

* Progress codes, in the order they are reached.
P_BOOT  EQU     $01             out of boot mode, RAM answers, stack up
P_PAL1  EQU     $02             2a's eight auto-incremented entries are written
P_PAL   EQU     $0B             256 palette entries loaded
P_DIR   EQU     $03             eight direct VDATA writes
P_RDBK  EQU     $04             ... and eight VDATA reads that matched
P_SOL   EQU     $05             the span-solid
P_GLY   EQU     $06             the WADV-chained glyph
P_CPY   EQU     $07             the copyrect
P_WAIT  EQU     $08             three unpolled 256-byte spans - the /WAIT block
P_DONE  EQU     $FF             display on -- sample the picture now
P_IRQ   EQU     $10             three VBL interrupts serviced
P_BADR  EQU     $E1             the SIMM did not answer
P_BADV  EQU     $E2             a VDATA read-back did not match

*------------------------------------------------------------- the picture ---
* A VRAM row is 1024 bytes (plan 2.5) and bitmap mode shows row (VSCROLL + y).
* Both scrolls are left at zero, so line y of the picture is VRAM row y >> 1
* in VMODE 00 and column x is byte x of it.
*
*   row  2, cols  0..7    $30 .. $37     direct VDATA writes
*   row  4, cols  0..63   $3C            span-solid, SPANLEN 63
*   rows 8..15, cols 16..23   $F1 / $B2  the glyph, ink where a mask bit is 1
*   rows 20..27, cols 32..39  the same   the copyrect of it
*   row 40, cols 0..767   $5A            three spans of 256, unpolled
*
* Everything else on the screen is whatever was in VRAM when the machine
* started, which is the bench's background.
DIRROW  EQU     2*1024
SOLROW  EQU     4*1024
GLYADR  EQU     8*1024+16
CPYADR  EQU     20*1024+32
WAITROW EQU     40*1024

*******************************************************************************
        ORG     $E000
*******************************************************************************

*==============================================================================
* 1. Boot.  machine.md 7.2: no RAM, no stack and no JSR until the LDS below.
*==============================================================================
reset   clra
        sta     TASKR           TASK := 0 first -- the map index is {TASK,block}

* Sixteen entries, two windows, one pass.  U walks the table, X the low window
* and Y the high one.  Straight-line: there is nowhere to put a return address.
        ldx     #MAPLO
        ldy     #MAPHI
        ldu     #maptab
mapl    lda     ,u+
        sta     ,x+             physical A20..A13
        lda     ,u+
        sta     ,y+             physical A24..A21
        cmpx    #MAPLO+16
        bne     mapl

* Block 7 points at the ROM page this code is running from, so the instruction
* stream does not move when the map takes over.  ram.md 6.4.
        clra
        sta     RUNSTB          RUN := 1, and TASK := 0 again (A0 is not decoded)

* ⭐ AND NOW THE MAP IS LOAD-BEARING.  Everything below reaches RAM through
* block 6 and the card's VRAM window through block 1, so a wrong entry is a
* wrong machine and not a wrong opinion.
*
* The SIMM, the way ram.md 6.4.1 says to ask: D0-D7 has no pull-ups, so a
* naive store-then-load passes against an EMPTY socket -- the store left the
* pattern on the bus.  Read a known ROM byte between the store and the load.
        lda     #$A5
        sta     RAMWIN
        lda     rombyte
        lda     RAMWIN
        cmpa    #$A5
        lbne    rambad
        lda     #$5A            and the complement, so a stuck bus fails one
        sta     RAMWIN
        lda     rombyte
        lda     RAMWIN
        cmpa    #$5A
        lbne    rambad

        lds     #STACK          the first instruction after which a JSR works
        clr     frames
        lda     #P_BOOT
        sta     SIMPORT

*==============================================================================
* 2a. ⭐ THE AUTO-INCREMENT, ON PURPOSE AND OUT OF VBLANK.
*
*     plan 10: "PIDX is 16 bits -- the whole LUT.  Auto-increments after PDATH",
*     and 13.1's commit is posted to the next HLOAD with PBUSY covering it.  So
*     eight entries written back to back, with PIDX set ONCE, must land at eight
*     consecutive LUT addresses.
*
*     ⚠ THE TIMING IS THE EXPERIMENT.  The commit has two paths (v3host):
*     PDGO & VBLANK commits immediately, and PPEND waits for HLOAD.  A short
*     palette load right after reset takes the first path and says nothing
*     about the second, which is the one a 256-entry load spends 93 % of its
*     time in.  This waits for VBLANK to go and come back -- so the eight
*     entries below are at the TOP OF THE ACTIVE AREA, 400 lines from the next
*     VBLANK, and every one of them takes the HLOAD path.
*
*     They go in sub-palette 1 ($0100-$01FF), which bitmap mode never
*     addresses, so whatever happens here cannot colour the picture.
*==============================================================================
        jsr     wvblon          wait for VBLANK ...
        jsr     wvbloff         ... and for it to end: the active area starts
        lda     #$01
        sta     PIDXH
        clra
        sta     PIDXL
        clrb
inclp   lda     #$A0
        pshs    b
        adda    ,s
        sta     PDATL
        lda     #$B0
        adda    ,s+
        sta     PDATH           the write posts the commit, and PIDX steps
        jsr     wpal
        incb
        cmpb    #8
        bne     inclp
        lda     #P_PAL1
        sta     SIMPORT

*==============================================================================
* 2b. The palette proper: 256 entries in sub-palette 0.
*
*     ⭐ ENTRY i IS $(~i)(i): PDATL = i, PDATH = ~i.  The LUT is then invertible
*     -- a displayed pixel's low byte IS the index the card looked up, and its
*     high byte says the entry was not something else's.  The bench checks all
*     256 out of the LUT array as well, which is a path the ROM cannot see.
*
*     ⚠ AND PIDX IS WRITTEN FOR EVERY ENTRY rather than left to step itself.
*     Software that meant to use the auto-increment would write two registers
*     an entry instead of four; this writes four, so that 2a's question is
*     asked once, in one place, and the picture below does not depend on the
*     answer.
*==============================================================================
        clra
        sta     PIDXH
        clrb
palloop stb     PIDXL           the index, every time
        stb     PDATL
        tfr     b,a
        coma
        sta     PDATH           the write posts the commit
        jsr     wpal
        incb
        bne     palloop
        lda     #P_PAL
        sta     SIMPORT

*==============================================================================
* 3. Eight direct VDATA writes at row 2, and eight reads back.
*    ⚠ NO POLL BETWEEN THE WRITES.  A direct write is one retire, and the card
*    holds the CPU with /WAIT if it is still busy (plan 5) -- so the loop is
*    written the way a driver would write it, and the hardware is what spaces
*    it.
*==============================================================================
        lda     #CT_OFF
        sta     VCTRL
        clr     WADV
        ldx     #DIRROW
        clrb
        jsr     setw
        ldb     #$30
        lda     #8
dirloop stb     VDATA
        incb
        deca
        bne     dirloop
        jsr     wspan
        lda     #P_DIR
        sta     SIMPORT

* The read-back.  A VDATA read is the card's prefetch (plan 11's '574): the
* first one after WPTR moves has to fetch, and the CPU is held for it.
        ldx     #DIRROW
        clrb
        jsr     setw
        lda     #$30
        sta     expect
        ldb     #8
rdloop  lda     VDATA
        cmpa    expect
        lbne    vbad
        inc     expect
        decb
        bne     rdloop
        lda     #P_RDBK
        sta     SIMPORT

*==============================================================================
* 4. A span-solid: SPANLEN is "length - 1", one write is 64 bytes of WFG.
*==============================================================================
        lda     #$3C
        sta     WFG
        lda     #63
        sta     SPANLEN
        lda     #CT_SOL
        sta     VCTRL
        ldx     #SOLROW
        clrb
        jsr     setw
        clra
        sta     VDATA           the trigger; the byte itself is not used
        jsr     wspan
        lda     #P_SOL
        sta     SIMPORT

*==============================================================================
* 5. The glyph.  plan 10's WADV 01 is "next row, same column": at span end the
*    row steps and the column comes back from WPTR's own shadow, so eight
*    span-mask writes are an 8 x 8 cell and the ROM never rewrites the pointer.
*    A mask bit of 1 is WFG and a 0 is WBG, bit 7 leftmost.
*==============================================================================
        lda     #$F1
        sta     WFG
        lda     #$B2
        sta     WBG
        lda     #CT_MSK
        sta     VCTRL
        lda     #$01
        sta     WADV
        ldx     #GLYADR
        clrb
        jsr     setw
        ldx     #glyph
        ldb     #8
glyloop lda     ,x+
        sta     VDATA
        decb
        bne     glyloop
        jsr     wspan
        clr     WADV
        lda     #P_GLY
        sta     SIMPORT

*==============================================================================
* 6. The copyrect.  plan 6: CPTR the source, WPTR the destination, CWIDTH and
*    CHEIGHT plain byte and row counts, CCTRL b0 GO.  WMODE is back to 00, so
*    the colour key is not armed and every byte moves (keyed-copy.md).
*==============================================================================
        lda     #CT_OFF
        sta     VCTRL
        ldy     #CPTR0
        ldx     #GLYADR
        clrb
        jsr     setptr
        ldx     #CPYADR
        clrb
        jsr     setw
        lda     #8
        sta     CWIDTH
        sta     CHEIGHT
        lda     #$01
        sta     CCTRL           GO
        jsr     wcopy
        lda     #P_CPY
        sta     SIMPORT

*==============================================================================
* 7. ⭐ THE /WAIT BLOCK, and the only part of this ROM written to be refused.
*
*    Three 256-byte span-solids, triggered through the VRAM WINDOW -- block 1,
*    a plain physical cycle with A19 = 1 and A20 = 0, which is the card's other
*    trigger (v3host's VPORT) and the one that goes through the map.  There is
*    NO poll between them: a span of 256 bytes is hundreds of dots and the next
*    store arrives a handful of cycles later, so the card must stretch E with
*    /WAIT until the span it is still running retires.  If it does not, the
*    second and third triggers are dropped and the picture is 256 bytes wide
*    instead of 768.
*==============================================================================
        lda     #$5A
        sta     WFG
        lda     #255
        sta     SPANLEN
        lda     #CT_SOL
        sta     VCTRL
        ldx     #WAITROW
        clrb
        jsr     setw
        ldx     #VRAMWIN        any address in the window; the byte lands at WPTR
        clra
        sta     ,x
        sta     ,x              ⭐ this store is the one that is held
        sta     ,x
        jsr     wspan
        lda     #P_WAIT
        sta     SIMPORT

*==============================================================================
* 8. Show it, and take the tick.  plan 9: CTRL b6 enables the VBL interrupt,
*    VSTAT b0 is the pending flag and ANY write to VSTAT clears it.
*==============================================================================
        clra
        sta     HSCRL
        sta     HSCRLH
        sta     VSCRL
        sta     VSCRLH
        sta     VSTAT           clear anything pending from before the enable
        lda     #CT_ONI
        sta     VCTRL
        lda     #P_DONE
        sta     SIMPORT
        andcc   #$EF            unmask IRQ; F stays set, there is no FIRQ source

* ⭐ AND IT TURNS THE TICK OFF AGAIN, which is not tidiness: the bench compares
* the count in the card's +$1F against the count in RAM, and a handler that is
* still running between those two reads makes them disagree by one. Masking
* first, then clearing CTRL b6, freezes both.
wfrm    lda     frames
        cmpa    #3
        blo     wfrm
        orcc    #$10            mask IRQ - the count stops here
        lda     #CT_ON
        sta     VCTRL           display still on, interrupt off
        clra
        sta     VSTAT           and nothing left pending
        lda     #P_IRQ
        sta     SIMPORT
halt    bra     halt

vbad    lda     #P_BADV
        sta     SIMPORT
        bra     halt

rambad  lda     #P_BADR
        sta     SIMPORT
        bra     halt

*==============================================================================
* Subroutines.  All of them are below the first LDS, so the stack exists.
*==============================================================================
* X = A15..A0, B = A18..A16 -> WPTR
setw    ldy     #WPTR0
* Y = the pointer's base register, X = A15..A0, B = A18..A16
setptr  stx     ptmp
        lda     ptmp+1
        sta     ,y
        lda     ptmp
        sta     1,y
        stb     2,y
        rts

* The three status polls.  VSTAT is read through plan 10's '244, not the
* register file.
wspan   lda     VSTAT
        bmi     wspan           b7 SPANBUSY
        rts
wcopy   lda     VSTAT
        bita    #$10            b4 CBUSY
        bne     wcopy
        rts
wpal    lda     VSTAT
        bita    #$02            b1 PBUSY
        bne     wpal
        rts
* VBLANK is VSTAT b6 - 2a's experiment needs to be somewhere definite in the
* frame, and these two are how software says where.
wvblon  lda     VSTAT
        bita    #$40
        beq     wvblon
        rts
wvbloff lda     VSTAT
        bita    #$40
        bne     wvbloff
        rts

*==============================================================================
* The VBL service.  IRQ stacks the whole machine state, so this may use A
* freely and RTI puts everything back.
*==============================================================================
irqh    clra
        sta     VSTAT           any write to VSTAT clears the pending flag
        inc     frames
        lda     frames
        sta     FCNT            plan 10: the spare byte holds the frame count
        rti

*==============================================================================
* Tables.
*==============================================================================
maptab
        FCB     $00,$02         block 0  $0000  SIMM0 + 0
        FCB     $40,$00         block 1  $2000  the card's VRAM window, page 0
        FCB     $41,$00         block 2  $4000  ... page 1
        FCB     $03,$02         block 3  $6000  SIMM0 + 3
        FCB     $04,$02         block 4  $8000  SIMM0 + 4
        FCB     $05,$02         block 5  $A000  SIMM0 + 5
        FCB     $06,$02         block 6  $C000  SIMM0 + 6   <- stack and vars
        FCB     $00,$01         block 7  $E000  ROM page 0  <- running here
        FCB     $00,$02         task 1, the same: nothing here changes TASK
        FCB     $40,$00
        FCB     $41,$00
        FCB     $03,$02
        FCB     $04,$02
        FCB     $05,$02
        FCB     $06,$02
        FCB     $00,$01

rombyte FCB     $C3             a known ROM byte, for the read-back test

* The glyph: eight mask bytes, every row different and none of them a mirror
* of itself, so a row slip or a reversed bit order is a wrong pixel.
glyph   FCB     $F0,$C8,$A4,$92,$89,$45,$23,$17

*==============================================================================
* The vector page.  machine.md 7.2: $FFC0-$FFFF is served by the ROM
* unconditionally, and block 7 is this same ROM page once RUN is set, so a
* vector may point straight at a handler here -- this fixture has no need for
* boot.asm's RAM jump table.
*==============================================================================
        ORG     $FFF2
        FDB     halt            SWI3
        FDB     halt            SWI2
        FDB     halt            FIRQ  - nothing on this machine asserts it
        FDB     irqh            IRQ   - the card's VBL
        FDB     halt            SWI
        FDB     halt            NMI
        FDB     reset           RESET

        END     reset
