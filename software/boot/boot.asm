*******************************************************************************
* boot.asm -- the machine's first instructions, and a video bring-up.
*
* docs/machine.md 7.2 is the boot sequence; hardware/ram.md 6.4 is why it has
* no JSR in it.  video/docs/graphics.md 13 is the register map, 7.4 the span
* writer and 8 the 1024-byte stride.
*
* This is assembled by A09 (software/tools/fetch-a09.sh) and executed by
* hardware/gal/verilog/machine_tb.sv on the REAL DESIGN: Greg Miller's cycle-accurate 6809E core in
* the socket, mainboard.v under it (U3, U6, U9, U10 generated from the same
* term lists the CPLD fitter compiles) and video_card.v in a slot.  Nothing
* here runs against a behavioural model of the machine; there isn't one.
*
* WHAT IT DOES, in order:
*   1. leaves boot mode with a map it wrote itself
*   2. proves the SIMM answers, because everything after needs a stack
*   3. loads 256 palette entries
*   4. paints an 8-bit test pattern with the card's span writer
*   5. draws a vertical stripe with 7.2's WADV chaining
*   6. enables the display and stops
*
* The picture is the point: machine_tb samples RGB at the connector for a whole
* frame and writes it out, so the pattern below is what a screenshot has to
* show, pixel for pixel, and every stage of the address path is in it.
*******************************************************************************

*------------------------------------------------------------------ the map --
* machine.md 3.  Two windows, one index: entry n is task n>>3, block n&7.
MAPHI   EQU     $FF90           high byte -- physical A24..A21 (ram.md 4.3)
MAPLO   EQU     $FFA0           low byte  -- physical A20..A13
TASKR   EQU     $FFB0           TASK, and $FFB0 is EVEN so it stays in boot mode
RUNSTB  EQU     $FFB1           the strobe that leaves it -- one way per reset

*--------------------------------------------------------------- the video ---
VBASE   EQU     $FF60           graphics.md 13
VCTRL   EQU     VBASE+$00       b7 dispen, b6 irqen, b5 cell, b4-3 wmode, b1-0 vmode
VSCROLL EQU     VBASE+$01
VSCRLH  EQU     VBASE+$02
HSCROLL EQU     VBASE+$03
HSCRLH  EQU     VBASE+$04
SPANLEN EQU     VBASE+$05       span length - 1
WFG     EQU     VBASE+$06
WBG     EQU     VBASE+$07
WPTR0   EQU     VBASE+$08       A7..A0
WPTR1   EQU     VBASE+$09       A15..A8
WPTR2   EQU     VBASE+$0A       A18..A16
PIDX    EQU     VBASE+$10       palette index, auto-increments after PDATH
PDATL   EQU     VBASE+$11       GGGBBBBB
PDATH   EQU     VBASE+$12       RRRRRGGG -- the write commits the entry
VSTAT   EQU     VBASE+$13       b7 SPANBUSY, b6 VBLANK, b5 HBLANK, b0 IRQ
WADV    EQU     VBASE+$14       00 continue, 01 next row same column

* CTRL bit patterns
CT_OFF  EQU     $00             display off, WMODE 00 direct, VMODE 00
CT_SOL  EQU     $10             display off, WMODE 10 span-solid
CT_MSK  EQU     $08             display off, WMODE 01 span-mask
CT_ON   EQU     $80             display ON, WMODE 00, VMODE 00 = 640x200 @ 70 Hz

*-------------------------------------------------------------- the machine --
VRAMWIN EQU     $2000           logical block 1 -- 8 KB of VRAM at a time
RAMWIN  EQU     $C000           logical block 6 -- the first SIMM
STACK   EQU     $E000           grows down through block 6

* machine.md 3: $FF00-$FF2F is free and decodes nowhere.  The last byte of it
* is this simulation's progress port -- machine_tb watches the bus for it, and
* on real hardware a write there does nothing at all.
SIMPORT EQU     $FF2F

* Progress codes, in the order they are reached.
P_BOOT  EQU     $01             out of boot mode, stack up
P_RAM   EQU     $02             the SIMM stores and reads back
P_PAL   EQU     $03             256 palette entries loaded
P_FILL  EQU     $04             the pattern is painted
P_STRP  EQU     $05             the stripe is drawn
P_DONE  EQU     $FF             VMODE 00 shown -- sample the picture now
P_M10   EQU     $10             ... and VMODE 10, 640x400 progressive
P_M01   EQU     $11             ... 01, 640x240 doubled
P_M11   EQU     $12             ... 11, 640x480 progressive
P_BADR  EQU     $E1             the SIMM did not answer

*------------------------------------------------------------- geometry ------
* VMODE 00 is 640x200.  The ring is 1024 bytes per row (graphics.md 8, and
* vspan_tb measures it), so a row is 1024 apart and 8 rows are exactly one
* 8 KB logical block -- which is why the window below is re-pointed every
* eighth row and not more often.
ROWS    EQU     200
SPANW   EQU     128             bytes per span
SPANC   EQU     5               spans per row: 5 x 128 = 640

STRIPEX EQU     256             the vertical stripe's column

*******************************************************************************
        ORG     $E000
*******************************************************************************

*==============================================================================
* 1. Boot.  machine.md 7.2: no RAM, no stack, and no JSR until the LDS below.
*==============================================================================
reset   clra
        sta     TASKR           TASK := 0 first -- the map index is {TASK,block}

* Sixteen entries, two windows, one pass.  U walks the table, X the low
* window and Y the high one.  Straight-line: there is nowhere to put a return
* address yet.
        ldx     #MAPLO
        ldy     #MAPHI
        ldu     #maptab
mapl    lda     ,u+
        sta     ,x+             physical A20..A13
        lda     ,u+
        sta     ,y+             physical A24..A21
        cmpx    #MAPLO+16
        bne     mapl

* One entry -- block 7 -- points at the ROM page this code is running from, so
* the instruction stream does not move when the map takes over.  ram.md 6.4.
        clra
        sta     RUNSTB          RUN := 1, and TASK := 0 again (A0 is not decoded)

        lds     #STACK          the first instruction after which a JSR works
        lda     #P_BOOT
        sta     SIMPORT

*==============================================================================
* 2. Prove the SIMM answers.  ram.md 6.4.1: D0-D7 has no pull-ups, so a naive
*    store-then-load passes against an EMPTY socket -- the store left the
*    pattern on the bus.  Read a known ROM byte between the store and the
*    read-back so the bus cannot be holding the answer.
*==============================================================================
        lda     #$A5
        sta     RAMWIN
        lda     rombyte         drive the bus to something else
        lda     RAMWIN
        cmpa    #$A5
        bne     rambad
        lda     #$5A            and the complement, so a stuck bus fails one
        sta     RAMWIN
        lda     rombyte
        lda     RAMWIN
        cmpa    #$5A
        bne     rambad
        lda     #P_RAM
        sta     SIMPORT
        bra     palette

rambad  lda     #P_BADR
        sta     SIMPORT
        jmp     halt

*==============================================================================
* 3. The palette.  graphics.md 13.1: writes during active display snow, so this
*    runs with the display off -- CTRL is 0 out of reset and stays that way
*    until step 6.  Entry i is $i i, which makes every index distinguishable in
*    a screenshot without a lookup table.
*==============================================================================
palette lda     #CT_OFF
        sta     VCTRL
        clra
        sta     PIDX            index 0; PIDX auto-increments after each PDATH
        clrb
pall    stb     PDATL           GGGBBBBB
        stb     PDATH           RRRRRGGG -- and this commits, and bumps PIDX
        incb
        bne     pall

        lda     #P_PAL
        sta     SIMPORT

*==============================================================================
* 4. The pattern.  Five span-solid writes per row, 128 bytes each.
*
*    index(x,y) = (y & $F8) | (x / 128)
*
*    so the top five bits name the row group and the low three the column --
*    every 8-row by 128-pixel cell has a colour that identifies where it is.
*    A stride error moves a boundary; an interleave error scrambles a cell;
*    a geometry error changes how many of them fit.
*==============================================================================
        lda     #CT_SOL
        sta     VCTRL
        lda     #SPANW-1
        sta     SPANLEN

        clr     yrow
rowlp
* --- every eighth row, re-point block 1 at the next 8 KB of the ring.
*     The window and the pointer move together, so the address the CPU writes
*     is always the address WPTR names.
        lda     yrow
        anda    #7
        bne     norem
        lda     yrow
        lsra
        lsra
        lsra                    y >> 3 = which 8 KB page of the ring
        adda    #$40            physical A20:A19 = 01 -- VRAM (ram.md 5.2)
        sta     MAPLO+1
        clra
        sta     MAPHI+1
norem

* --- WPTR = y * 1024
        clra
        sta     WPTR0           A7..A0 = 0
        lda     yrow
        lsla
        lsla                    (y * 4) & $FF = A15..A8
        sta     WPTR1
        lda     yrow
        lsra
        lsra
        lsra
        lsra
        lsra
        lsra                    y >> 6 = A18..A16
        sta     WPTR2

* --- and the logical address that names the same byte
        lda     yrow
        anda    #7
        lsla
        lsla
        adda    #VRAMWIN/256    $20 + (y & 7) * 4
        sta     taddr
        clr     taddr+1

        clr     ccol
spanlp
* --- wait for the previous span before touching WFG: the span writer reads
*     the colour out of the register file per retire (graphics.md 7.4), so a
*     write to WFG mid-span would change the colour half way along it.
wbusy1  lda     VSTAT
        bmi     wbusy1          b7 = SPANBUSY

        lda     yrow
        anda    #$F8
        ora     ccol
        sta     WFG

* --- the trigger: a CPU write to VRAM posts, and the span writer starts.
        ldx     taddr
        sta     ,x
        ldd     taddr
        addd    #SPANW
        std     taddr

        inc     ccol
        lda     ccol
        cmpa    #SPANC
        bne     spanlp

        inc     yrow
        lda     yrow
        cmpa    #ROWS
        bne     rowlp

wbusy2  lda     VSTAT
        bmi     wbusy2
        lda     #P_FILL
        sta     SIMPORT

*==============================================================================
* 5. The stripe.  graphics.md 7.2's WADV = 01 -- "next row, same column" -- is
*    the whole text engine: the pointer advances a row and the COLUMN RELOADS,
*    so one register setup and 200 triggers draw an 8-pixel-wide vertical bar.
*    Written here because it is the one path that reloads WPTR from the
*    register file rather than from the CPU, and nothing had ever run it.
*==============================================================================
        lda     #CT_MSK
        sta     VCTRL
        lda     #$01
        sta     WADV            01 = next row, same column
        lda     #$FF
        sta     WFG             the stripe's colour
        clra
        sta     WBG

* WPTR = STRIPEX, row 0
        lda     #STRIPEX&$FF
        sta     WPTR0
        lda     #STRIPEX/256
        sta     WPTR1
        clra
        sta     WPTR2

        clr     yrow
strplp
        lda     yrow
        anda    #7
        bne     nrem2
        lda     yrow
        lsra
        lsra
        lsra
        adda    #$40
        sta     MAPLO+1
        clra
        sta     MAPHI+1
nrem2
        lda     yrow
        anda    #7
        lsla
        lsla
        adda    #VRAMWIN/256
        sta     taddr
        lda     #STRIPEX&$FF
        sta     taddr+1

wbusy3  lda     VSTAT
        bmi     wbusy3
        ldx     taddr
        lda     #$FF            the mask: eight set bits, eight WFG pixels
        sta     ,x

        inc     yrow
        lda     yrow
        cmpa    #ROWS
        bne     strplp

wbusy4  lda     VSTAT
        bmi     wbusy4
        clra
        sta     WADV            back to 00 -- continue
        lda     #P_STRP
        sta     SIMPORT

*==============================================================================
* 6. Show it, in every mode the card has.  graphics.md 13's VMODE is two bits
*    and 6.2 calls all four native, and until now only 00 had ever been reached
*    by software - vsync_tb drives the register from a task.  The pattern stays
*    where it is: the ring is 1024 x 512 and the modes differ only in how much
*    of it they scan and whether they double, so one framebuffer answers all
*    four and the SHAPE of what comes out is the claim.
*
*    machine_tb captures a frame per scene.  The handshake is the card's own
*    VBLANK - poll VSTAT b6 - which is 12.1's tear-free instant and the thing a
*    real driver waits on anyway.
*==============================================================================
        clra
        sta     VSCROLL
        sta     VSCRLH
        sta     HSCROLL
        sta     HSCRLH

        lda     #CT_ON          VMODE 00 - 640x200, doubled to 400 lines
        sta     VCTRL
        lda     #P_DONE
        sta     SIMPORT
        bsr     settle

        lda     #CT_ON+2        VMODE 10 - 640x400 progressive, same 70 Hz family
        sta     VCTRL
        lda     #P_M10
        sta     SIMPORT
        bsr     settle

        lda     #CT_ON+1        VMODE 01 - 640x240, doubled to 480, 60 Hz
        sta     VCTRL
        lda     #P_M01
        sta     SIMPORT
        bsr     settle

        lda     #CT_ON+3        VMODE 11 - 640x480 progressive, 60 Hz
        sta     VCTRL
        lda     #P_M11
        sta     SIMPORT
        bsr     settle

        lda     #CT_ON          back to 00 for anything after this
        sta     VCTRL

halt    bra     halt

*==============================================================================
* settle - give the capture a whole frame to find, by waiting four vertical
* blanks on VSTAT b6.  ⚠ FOUR, not one: machine_tb hunts a VSYNC edge and then
* takes the frame after it, so a scene has to stand still for longer than the
* two frames that costs.
*
* ⭐ AND IT IS THE HANDSHAKE A DRIVER WOULD USE.  13.1's palette rule and
* 12.1's VBL handler both say "do it in vertical blank", and this is the poll
* that finds it - so the wait is the machine exercising a documented path
* rather than a testbench convenience.
*==============================================================================
settle  pshs    a,b
        ldb     #4
vblnot  lda     VSTAT           wait until NOT in vertical blank
        bita    #$40
        bne     vblnot
vblin   lda     VSTAT           ... then for the edge into it
        bita    #$40
        beq     vblin
        decb
        bne     vblnot
        puls    a,b,pc

*==============================================================================
* The map table: sixteen entries of (low, high), index {TASK, block}.
*
*   block 0,3,4,5,6   SIMM 0, physical 4 MB + n * 8 KB   (A24..A21 = 0010)
*   block 1,2         the video ring, physical 0.5 MB    (A20:A19 = 01)
*   block 7           the boot ROM's own page 0, 2 MB    (A21 = 1)
*
* Task 1's eight entries are the same, so a task switch changes nothing yet.
* ram.md 5.2 is the physical map they name.
*==============================================================================
maptab
        FCB     $00,$02         block 0  $0000  SIMM0 + 0
        FCB     $40,$00         block 1  $2000  ring page 0   <- moved, above
        FCB     $41,$00         block 2  $4000  ring page 1
        FCB     $03,$02         block 3  $6000  SIMM0 + 3
        FCB     $04,$02         block 4  $8000  SIMM0 + 4
        FCB     $05,$02         block 5  $A000  SIMM0 + 5
        FCB     $06,$02         block 6  $C000  SIMM0 + 6   <- stack and vars
        FCB     $00,$01         block 7  $E000  ROM page 0  <- running here
        FCB     $00,$02
        FCB     $40,$00
        FCB     $41,$00
        FCB     $03,$02
        FCB     $04,$02
        FCB     $05,$02
        FCB     $06,$02
        FCB     $00,$01

rombyte FCB     $C3             a known ROM byte, for the read-back test

*==============================================================================
* Variables.  Block 6, which is the SIMM -- so nothing here is touched before
* step 2 has proved the SIMM answers.
*==============================================================================
yrow    EQU     RAMWIN+$10      current row, 0..199
ccol    EQU     RAMWIN+$11      current span within the row, 0..4
taddr   EQU     RAMWIN+$12      the logical address the trigger writes (2 bytes)

*==============================================================================
* The vector page.  machine.md 7.2: $FFC0-$FFFF is served by the ROM
* unconditionally, which is the whole reason $FFFE is a reset vector and not an
* undriven bus.  In ROM these are at $1FF2-$1FFF.
*==============================================================================
        ORG     $FFF2
        FDB     halt            SWI3
        FDB     halt            SWI2
        FDB     halt            FIRQ
        FDB     halt            IRQ
        FDB     halt            SWI
        FDB     halt            NMI
        FDB     reset           RESET

        END     reset
