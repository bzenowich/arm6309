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
TILEBAS EQU     VBASE+$17       6.4.1's TB4..TB0 -- the tile set's A18..A14
MAPBAS  EQU     VBASE+$19       6.4.1's MB6..MB0 -- the map's A18..A12
BCTRL   EQU     VBASE+$0E       b0 GO -- starts the display list from WPTR
BSTAT   EQU     VBASE+$0F       reserved - LRUN reads back as VSTAT b4

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
P_LSTA  EQU     $20             display list A running - a palette raster bar
P_LSTB  EQU     $21             ... and B - one HSCROLL MOVE per line
P_TILE  EQU     $30             6.4's cell mode - a tilemap, drawn by the CPU
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
        lbsr    settle

        lda     #CT_ON+2        VMODE 10 - 640x400 progressive, same 70 Hz family
        sta     VCTRL
        lda     #P_M10
        sta     SIMPORT
        lbsr    settle

        lda     #CT_ON+1        VMODE 01 - 640x240, doubled to 480, 60 Hz
        sta     VCTRL
        lda     #P_M01
        sta     SIMPORT
        lbsr    settle

        lda     #CT_ON+3        VMODE 11 - 640x480 progressive, 60 Hz
        sta     VCTRL
        lda     #P_M11
        sta     SIMPORT
        lbsr    settle

        lda     #CT_ON          back to 00 for the list scenes
        sta     VCTRL

*==============================================================================
* 7. The display list.  graphics.md 10.3, and it has never been started by
*    software: vspan_tb pokes descriptors straight into the framebuffer array
*    and writes BCTRL from a task.
*
*    Two lists, because §10.3 sells two different effects and they fail
*    differently:
*
*      A  ninety WAITs and then a palette repaint - a RASTER BAR.  The stripe
*         at x = 256 is index $FF on every row, so changing that one entry part
*         way down the screen makes the stripe change colour at a line, and
*         machine_tb looks for exactly that.
*      B  one MOVE to HSCROLL per line, stepping - PER-SCANLINE SCROLL.  The
*         stripe moves left a little further on each line, so the frame carries
*         as many distinct stripe positions as the list had entries.
*
*    ⚠ A DESCRIPTOR IS WRITTEN THROUGH THE SPAN WRITER.  A CPU VRAM write is
*    posted and retires at WPTR (§3.1.1, §7.4) - the address on the bus selects
*    VRAM and nothing else - so building a list means pointing WPTR at it and
*    letting the auto-increment walk.  That is also why every byte polls VSTAT
*    b7 first: §7.4's rule, and the only alternative is 40.7 us of /WAIT.
*==============================================================================
* ⛔ A SPAN-WRITTEN BYTE STREAM CANNOT LEAVE ITS 1024-BYTE ROW.  WPTR is not
* one counter: WA9..WA0 is a column that WRAPS at 1024 and WA18..WA10 is a row
* that only WROWADV clocks, so with WADV = 00 the 1025th byte lands back on the
* first.  The first version of this code put two lists 256 bytes apart and made
* list B 1261 bytes long; it wrapped at byte 1024 and rewrote itself over list
* A, and what the engine then walked was picture data executed as descriptors.
* Hence: ONE ROW PER LIST, and no list longer than 1024 bytes.
LISTPG  EQU     50              ring page 50 = VRAM 409,600, well past the image
LPAGE   EQU     $06             ... which is $64000, so WPTR[18:16] = 6
LISTA   EQU     $4000           list A  - VRAM 409,600, ring row 400
LISTB   EQU     $4400           list B  - VRAM 410,624, ring row 401
WAITOP  EQU     $80             graphics.md 10.3.2: WAIT
ENDOP   EQU     $FF             ... and the terminator
BARIDX  EQU     $FF             the stripe's palette index

* ⚠ The map matters only for the CPU's half of the transaction.  In WMODE 00
* the address a store carries selects the VRAM window and nothing else - WPTR
* is what says where the byte lands - so X below stays at the window's base and
* the descriptors go wherever setwptr last pointed.
        lda     #$40+LISTPG     block 1 -> the descriptor page
        sta     MAPLO+1
        clra
        sta     MAPHI+1
        lda     #LPAGE
        sta     wpage

* ---- list A: a RASTER BAR - white, then magenta, then white again -------
* ⭐ BOTH EFFECTS ARE PERSISTENT, so a list that changes the palette once shows
* a bar only in the frame it runs in and a solid colour ever after. A bar that
* can be photographed has to change and change back, and the list has to be
* restarted every frame - which is what a driver does anyway, out of 12.1's VBL
* handler.
        ldd     #LISTA
        lbsr    setwptr
        ldx     #VRAMWIN
        ldb     #90
la1     lda     #WAITOP
        lbsr    putb
        decb
        bne     la1
        ldy     #barmag         entry $FF := $F81F
        lbsr    putpal
        ldb     #90
la2     lda     #WAITOP
        lbsr    putb
        decb
        bne     la2
        ldy     #barwht         ... and back to $FFFF
        lbsr    putpal
        lda     #ENDOP
        lbsr    putb

* ---- list B: one MOVE HSCROLL per line, for a whole frame ---------------
* ⚠ The operand's bits 7..2 are HSCROLL[9..2] (vspan_tb measures it), so an
* operand of 4n scrolls by 4n pixels - byte-granular, which is what 8.2 bought.
* The step wraps every 64 lines so the stripe sweeps the screen repeatedly and
* the frame carries many distinct positions rather than one.
        ldd     #LISTB
        lbsr    setwptr
        ldx     #VRAMWIN
        clr     lstep
        clr     lstep+1
lb1     lda     #$03            MOVE HSCROLL, (pair & 63) * 4
        lbsr    putb
        lda     lstep+1
        anda    #63
        lsla
        lsla
        lbsr    putb
        lda     #WAITOP         ... and hold it for two lines, so 400 lines of
        lbsr    putb
        lda     #WAITOP         descriptor cost 800 bytes and stay inside the
        lbsr    putb            row that the paragraph above is about
        ldd     lstep
        addd    #1
        std     lstep
        cmpd    #200            200 pairs = the whole visible frame
        bne     lb1
        lda     #ENDOP
        lbsr    putb

* ---- run list A, restarted every vertical blank -------------------------
        lda     #P_LSTA
        sta     SIMPORT
        ldd     #LISTA
        lbsr    runlist

* ---- and list B ---------------------------------------------------------
        lda     #P_LSTB
        sta     SIMPORT
        ldd     #LISTB
        lbsr    runlist

        clra                    leave the scroll where a reader expects it
        sta     HSCROLL
        sta     HSCRLH

*==============================================================================
* 8. Cell mode.  graphics.md 6.4, and until now only vtile_tb had reached it -
*    which drives the fetch and reads back the ADDRESS the card asks for.  This
*    puts a tilemap in VRAM with the span writer, points the two base registers
*    at it, sets CTRL b5, and lets the card paint 2,000 cells out of 256 bytes
*    of tile data.  What comes out of the connector is the claim.
*
* ⭐ THE TILE SET IS THE BYTES 0..255 IN ORDER, and that is not laziness.
*    6.4.1's address is a CONCATENATION - TILEBASE | code<<6 | row<<3 | col -
*    so the byte holding tile n's pixel (r, c) sits at n*64 + r*8 + c, which
*    for four tiles is exactly the offset itself.  Writing i at offset i makes
*    every pixel's INDEX equal to (n<<6)|(r<<3)|c, and 9's palette is the
*    identity map, so every pixel that reaches the connector names the three
*    fields that addressed it.  A row field off by one, a column field on the
*    wrong address bit, a map byte fetched for the neighbouring cell - each
*    moves a different part of that number, and machine_tb states the whole
*    expression independently.
*
* ⚠ VMODE 00, BECAUSE THE CELL ROW IS FIVE BITS.  6.4.1: cell mode addresses
*    32 rows, which covers 640x200's 25 and 640x240's 30 and does not reach
*    640x400's 50 or 640x480's 60.  vtile_tb runs VMODE 10 because it is
*    checking addresses and not a picture; a picture has to stay inside the
*    field.
*==============================================================================
TILEB   EQU     8               tile set at 8 * 16,384  = VRAM 131,072
MAPB    EQU     40              map      at 40 * 4,096  = VRAM 163,840
TBPAGE  EQU     $02             ... which is $20000, so WPTR[18:16] = 2
TBLOW   EQU     $0000
MBPAGE  EQU     $02             ... and $28000
MBLOW   EQU     $8000
CELLS   EQU     80              cells across, 640 / 8
CROWS   EQU     25              cell rows, 200 / 8
MSTRIDE EQU     128             6.4.1's map row stride - a power of two, so the
*                               map fetch is a concatenation and not a multiply

        lda     #TBPAGE
        sta     wpage
        ldd     #TBLOW
        lbsr    setwptr
        ldx     #VRAMWIN
        clra                    256 bytes: four tiles, every pixel distinct
tset    lbsr    putb
        inca
        bne     tset

* The map: code = (cellRow + cellCol) & 3, so the tile changes both across and
* down and a row/column swap in 6.4.1's concatenation cannot look right.
        lda     #MBPAGE
        sta     wpage
        clr     yrow
mrow    lda     yrow
        ldb     #MSTRIDE
        mul                     D = cellRow * 128, and no carry: 24*128 < 64 K
        addd    #MBLOW
        lbsr    setwptr
        ldx     #VRAMWIN
        clr     ccol
mcol    lda     yrow
        adda    ccol
        anda    #3
        lbsr    putb
        inc     ccol
        lda     ccol
        cmpa    #CELLS
        bne     mcol
        inc     yrow
        lda     yrow
        cmpa    #CROWS
        bne     mrow
        clr     wpage

        lda     #TILEB
        sta     TILEBAS
        lda     #MAPB
        sta     MAPBAS
        clra                    cell mode scrolls through the same two
        sta     VSCROLL         registers as bitmap mode - 6.4.1's note about
        sta     VSCRLH          vadr - so start them at the top left
        sta     HSCROLL
        sta     HSCRLH
        lda     #CT_ON+$20      display ON, CELL, VMODE 00
        sta     VCTRL
        lda     #P_TILE
        sta     SIMPORT
        lbsr    settle

halt    bra     halt

*==============================================================================
* putpal - append "MOVE PIDX,$FF / MOVE PDATL,lo / MOVE PDATH,hi" to the list.
* Y points at a three-byte table: PIDX operand, PDATL, PDATH.  13's second write
* port on +$10..+$12 is what makes a palette reachable from a descriptor at all,
* and PDATH is the write that commits.
*==============================================================================
putpal  pshs    a
        lda     #$10
        lbsr    putb
        lda     ,y+
        lbsr    putb
        lda     #$11
        lbsr    putb
        lda     ,y+
        lbsr    putb
        lda     #$12
        lbsr    putb
        lda     ,y+
        lbsr    putb
        puls    a,pc

barmag  FCB     BARIDX,$1F,$F8  entry $FF := $F81F, magenta
barwht  FCB     BARIDX,$FF,$FF  ... and back to white

*==============================================================================
* runlist - start the list at D at every vertical blank, for eight frames.
*
* ⭐ THIS IS THE DRIVER SHAPE, not a testbench convenience. 10.3.1: the engine
* shares WPTR, so a list is started by loading WPTR and writing BCTRL - and it
* clobbers WPTR on the way through, so every frame has to load it again. 12.1's
* VBL handler is where that belongs.
*==============================================================================
runlist pshs    a,b
        std     lstart
        lda     #8
        sta     lframe
rl1     ldb     #1
        lbsr    vblonly         the tear-free instant: load WPTR here
        ldd     lstart
        lbsr    setwptr
* ⚠ ... BUT GO AT BLANK'S END, NOT AT ITS START.  10.3.2's WAIT resumes at the
* next SCANLINE and HLOAD has no vertical term, so blanked lines count: a list
* GO'd at the top of vertical blank spends its first ~49 WAITs there and the
* effect lands 49 lines higher than the descriptor count says.  Waiting out the
* blank costs one poll and makes WAIT number n mean line n.
rl2     lda     VSTAT
        bita    #$40
        bne     rl2
        lda     #$01            BCTRL.GO
        sta     BCTRL
        dec     lframe
        bne     rl1
* ⛔ AND WAIT FOR THE LAST ONE TO STOP.  10.3.1: while LRUN is set the engine
* OWNS WPTR - it is walking it - so the next thing that loads WPTR is writing a
* register another master is using, and every byte it retires lands wherever
* the engine has got to.  Without this poll the tilemap below was written into
* a moving target: its 256 bytes came out interleaved with the descriptors the
* engine was still fetching, at addresses that skipped.  machine_tb saw
* LRUN = 1 through the whole of it.  The wait is bounded by the list's own
* terminator, which is what ENDOP is for.
rl3     lda     VSTAT           b4 LRUN - and 13 says why it is HERE and not
        bita    #$10            at +$0F, which is a register file location and
        bne     rl3             cannot carry a macrocell's live state
        puls    a,b,pc

*==============================================================================
* setwptr - D = the 16-bit VRAM offset; WPTR := D (the top three bits are zero
* for everything this ROM addresses).  §13's +$08..+$0A, little-endian.
*==============================================================================
setwptr stb     WPTR0
        sta     WPTR1
        pshs    a
        lda     wpage
        sta     WPTR2
        puls    a,pc

*==============================================================================
* putb - retire A into VRAM at WPTR, one byte, WMODE 00.
*
* X names the same byte in logical space and post-increments with WPTR: the
* address is what selects VRAM and WPTR is what says where the byte lands, and
* keeping them in step is what makes this readable rather than merely working.
*==============================================================================
putb    pshs    b
pb1     ldb     VSTAT           §7.4: poll b7, SPANBUSY
        bmi     pb1
        sta     ,x+
        puls    b,pc

*==============================================================================
* vblonly - wait B vertical blanks and return immediately after the edge, so a
* caller gets the whole of the next frame rather than the tail of this one.
*==============================================================================
vblonly pshs    a
vo1     lda     VSTAT
        bita    #$40
        bne     vo1
vo2     lda     VSTAT
        bita    #$40
        beq     vo2
        decb
        bne     vo1
        puls    a,pc

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
lstep   EQU     RAMWIN+$14      list B's line counter while it is built (2 bytes)
lframe  EQU     RAMWIN+$16      runlist's frame counter
wpage   EQU     RAMWIN+$17      WPTR[18:16] for the next setwptr -- see 13
lstart  EQU     RAMWIN+$18      runlist's list address, reloaded every frame

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
