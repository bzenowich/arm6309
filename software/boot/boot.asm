*******************************************************************************
* boot.asm -- the machine's first instructions, and a video bring-up.
*
* docs/machine.md 7.2 is the boot sequence; hardware/ram.md 6.4 is why it has
* no JSR in it.  video3/docs/plan.md 10 is the video register map, 5 the span
* writer, 6 the copy engine, 7 the sprite and 2.5 the four-byte cell and the
* 1024-byte stride.
*
* ⭐ RETARGETED TO video3, 2026-09-20.  Until then the video section drove
* archive/video/docs/graphics.md 13's card, which was archived that day
* (archive/README.md).  software/v3boot/v3boot.asm is the fixture this section
* was ported from, and it is still the smaller model to read first.
*
* This is assembled by A09 (software/tools/fetch-a09.sh) and executed by
* hardware/gal/verilog/machine_tb.sv on the REAL DESIGN: Greg Miller's
* cycle-accurate 6809E core in the socket, mainboard.v under it (U3, U6, U9,
* U10 generated from the same term lists the CPLD fitter compiles) and
* video3_card.v in a slot -- v3dot, v3scan, v3ptr, v3host and the v3lane GAL.
* Nothing here runs against a behavioural model of the machine; there isn't one.
*
* WHAT IT DOES, in order:
*   1. leaves boot mode with a map it wrote itself, and sizes the SIMM bank
*   2. proves the chosen SIMM answers, and that TASK selects half the map
*   2c. ⭐ ASKS WHETHER THERE IS A video3 CARD AT ALL, and skips 3-10 if not
*   3. loads 256 palette entries
*   4. paints an 8-bit test pattern with the card's span writer
*   5. draws a vertical stripe with plan 10's WADV chaining
*   6. shows it in all four VMODEs
*   7. runs the copy engine, and then the hardware sprite
*   8. tile mode - a tilemap on the four-byte cell stride
*  10. reads VRAM back, through the window and through VDATA
*  11. hands the machine to a program in ROM page 1, if there is one
*
* The picture is the point: machine_tb samples RGB at the connector for a whole
* frame and writes it out, so the pattern below is what a screenshot has to
* show, pixel for pixel, and every stage of the address path is in it.
*
* ⛔ EVERY POLL IN THE VIDEO SECTION IS BOUNDED, and that is a change from
* v3boot.asm, which leaves them unbounded and lets its bench bound them.  This
* is the machine's boot ROM: it runs on hardware that may be broken, and
* CLAUDE.md's rule -- a hang is worse than a failure -- applies to the ROM
* itself.  vwait0/vwait1 count their reads and take the error path ($E5) rather
* than spin.
*******************************************************************************

*------------------------------------------------------------------ the map --
* machine.md 3.  Two windows, one index: entry n is task n>>3, block n&7.
MAPHI   EQU     $FF90           high byte -- physical A24..A21 (ram.md 4.3)
MAPLO   EQU     $FFA0           low byte  -- physical A20..A13
TASKR   EQU     $FFB0           TASK, and $FFB0 is EVEN so it stays in boot mode
RUNSTB  EQU     $FFB1           the strobe that leaves it -- one way per reset

*--------------------------------------------------------------- the video ---
* video3/docs/plan.md 10 -- 32 bytes at $FF60.  nitros9 defs/armvid.d's IFNE V3
* block is the same map, and the two have to agree.
VBASE   EQU     $FF60
VCTRL   EQU     VBASE+$00       b1-0 VMODE, b3-2 MODE, b5-4 WMODE, b6 IRQEN, b7 DISPEN
VSCROLL EQU     VBASE+$01
VSCRLH  EQU     VBASE+$02
HSCROLL EQU     VBASE+$03
HSCRLH  EQU     VBASE+$04
SPANLEN EQU     VBASE+$05       span length - 1
WFG     EQU     VBASE+$06       ⚠ even, and WBG the odd above it - plan 5
WBG     EQU     VBASE+$07
WPTR0   EQU     VBASE+$08       A7..A0
WPTR1   EQU     VBASE+$09       A15..A8
WPTR2   EQU     VBASE+$0A       A18..A16
WADV    EQU     VBASE+$0B       00 continue, 01 next row same column, b2 step by two
VDATA   EQU     VBASE+$0C       the VRAM byte at WPTR, either way, post-increment
VSTAT   EQU     VBASE+$0D       b7 SPANBUSY b6 VBLANK b5 HBLANK b4 CBUSY b1 PBUSY b0 IRQ
PIDXL   EQU     VBASE+$0E       palette index, 16 bits - the whole LUT
PIDXH   EQU     VBASE+$0F
PDATL   EQU     VBASE+$10       GGGBBBBB
PDATH   EQU     VBASE+$11       RRRRRGGG -- the write posts the commit
CPTR0   EQU     VBASE+$12       copyrect source, 19 bits
CPTR1   EQU     VBASE+$13       ... and 2c's card probe - see there
CPTR2   EQU     VBASE+$14
CWIDTH  EQU     VBASE+$15       bytes a row
CHEIGHT EQU     VBASE+$16       rows -- ⚠ counts ONCE a copy, reload it each time
CCTRL   EQU     VBASE+$17       b0 GO; b1,b2 reserved - no direction bits (plan 6.2)
TBASE   EQU     VBASE+$18       the tile/glyph bank's A18..A14
MAPBAS  EQU     VBASE+$19       the map's A18..A16 -- three bits (plan 2.5)
SPRX    EQU     VBASE+$1A       plan 7's sprite: X7..X0
SPRY    EQU     VBASE+$1B       Y7..Y0
SPRH    EQU     VBASE+$1C       b1-0 X9..X8, b2 Y8, b7 enable

* CTRL bit patterns.  ⚠ WMODE MOVED FROM b4-3 TO b5-4 and b3-2 became MODE, so
* every one of these is a different byte from the card this ROM used to drive.
CT_OFF  EQU     $00             display off, WMODE 00 direct, MODE 00 bitmap
CT_MSK  EQU     $10             ... WMODE 01 span-mask
CT_SOL  EQU     $20             ... WMODE 10 span-solid
CT_TILE EQU     $08             MODE 10 - tile (plan 2.4)
CT_ON   EQU     $80             display ON, WMODE 00, VMODE 00 = 640x200 @ 70 Hz

*-------------------------------------------------------------- the machine --
VRAMWIN EQU     $2000           logical block 1 -- 8 KB of VRAM at a time
RAMWIN  EQU     $C000           logical block 6 -- the first SIMM
STORET  EQU     RAMWIN+$100     2a's 96-byte store target, clear of the
*                               variables at +$10..$1B and of the stack, which
*                               descends from $E000
STACK   EQU     $E000           grows down through block 6
TASKT   EQU     $A000           block 5: a different SIMM page in each task
DESCMAP EQU     $0000           the memory descriptor, block 0 (1a)
* ⭐ THE RAM VECTORS. machine.md 7.2: the vectors are in ROM and point at a fixed
* RAM jump table, "a software convention the boot monitor has to publish" - and
* this is where it is published. IRQ and FIRQ jump through these two words,
* which boot points at `halt` as soon as there is RAM. Block 6, clear of stage
* 2's store at $C000 and the variables at +$10.
IRQVEC  EQU     $C004
FIRQVEC EQU     $C006
DESCBLK EQU     $0001

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
P_NOVID EQU     $06             ⭐ 2c found no video3 card - 3..10 were SKIPPED
P_DONE  EQU     $FF             VMODE 00 shown -- sample the picture now
P_M10   EQU     $10             ... and VMODE 10, 640x400 progressive
P_M01   EQU     $11             ... 01, 640x240 doubled
P_M11   EQU     $12             ... 11, 640x480 progressive
* ⛔ $20 AND $21 USED TO BE P_LSTA AND P_LSTB, the two display lists.  video3
* has no display-list engine at all - plan 0 deletes it, and with it BCTRL,
* BSTAT, LRUN, per-scanline HSCROLL and the raster bar.  The two codes are
* reused for what the card has INSTEAD and what nothing else in this ROM
* reached: the copy engine (plan 6) and the hardware sprite (plan 7).
P_COPY  EQU     $20             plan 6's copyrect ran and read back right
P_SPR   EQU     $21             plan 7's 16x16 sprite is on the screen
P_TILE  EQU     $30             plan 2.4's tile mode - a tilemap, drawn by the CPU
P_VREAD EQU     $40             plan 10 - VRAM read back, every byte right
P_BADV  EQU     $E2             ... a byte read back wrong; vidx says which
P_BADR  EQU     $E1             no SIMM socket passed the walk, or block 6 failed
P_TASK  EQU     $07             TASK 1's map is live and distinct from TASK 0's
P_BADT  EQU     $E3             ... it is not
P_BADC  EQU     $E4             7's copyrect did not land; vidx/vgot say where
P_STUK  EQU     $E5             ⛔ a VSTAT poll ran out of patience - vwait0
P_ST0   EQU     $50             2a - the store-rate blocks: A begins
P_ST1   EQU     $51             ... A done (32 stores), B begins
P_ST2   EQU     $52             ... B done (64 stores)

*------------------------------------------------------------- geometry ------
* VMODE 00 is 640x200.  A VRAM row is 1024 bytes (plan 2.5), so a row is 1024
* apart and 8 rows are exactly one 8 KB logical block -- which is why the window
* below is re-pointed every eighth row and not more often.
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

*==============================================================================
* 1a. Size the bank.  ram.md 6.4.1: nothing in this machine knows how much
*     memory it has -- a 30-pin SIMM has no presence-detect pins -- so the ROM
*     walks the four sockets.  STILL STACKLESS: no RAM is known to work yet, so
*     no JSR, and the result lives in registers until a socket is chosen.
*
*     Per socket n, block 0 -> physical 4(n+1) MB:
*       $A5 and $5A, each read back with a ROM read between the store and the
*       load -- D0-D7 has no pull-ups, so without it an EMPTY socket reads back
*       the byte the store left on the bus, and passes;
*       then $11 at +$0000 and $22 at +$0400 -- physical A10, which a 1M x 8
*       module ignores (ram.md 6.3.1), so an aliasing module reads $22 back.
*     A socket that fails any of the three is not used.  A faulty module and an
*     absent one are the same answer, which is the right one for a boot ROM.
*
*     U's low byte collects the bitmap: bits are distinct, so OR is ADD, and
*     LEAU A,U is an add that needs no RAM.
*==============================================================================
        ldu     #0
        ldb     #$02            socket 0: map high byte (n+1)*2, A24..A22 = n+1
walk    stb     MAPHI           entry 0 = TASK 0, block 0
        clra
        sta     MAPLO
        lda     #$A5
        sta     $0000
        lda     rombyte         drive the bus with something else
        lda     $0000
        cmpa    #$A5
        bne     wnext
        lda     #$5A
        sta     $0000
        lda     rombyte
        lda     $0000
        cmpa    #$5A
        bne     wnext
        lda     #$11            the address pass
        sta     $0000
        lda     #$22
        sta     $0400           physical A10
        lda     rombyte
        lda     $0000
        cmpa    #$11
        bne     wnext
        ldx     #sockbit-2      B = 2,4,6,8 -> bit 1,2,4,8
        lda     b,x
        leau    a,u
wnext   addb    #2
        cmpb    #$0A
        bne     walk

        tfr     u,d             B = the bitmap
        tstb
        lbeq    rambad          no socket answered

* The stack, the variables and every SIMM block go in the LOWEST populated
* socket, so the machine boots on any one module in any one socket.  Ten map
* entries name SIMM pages -- blocks 0, 3, 4, 5, 6 of both tasks.
        ldx     #lowhi
        lda     b,x             that socket's map high byte
        ldx     #MAPHI
        sta     ,x
        sta     3,x
        sta     4,x
        sta     5,x
        sta     6,x
        sta     8,x
        sta     11,x
        sta     12,x
        sta     13,x
        sta     14,x

* The memory descriptor, at the base of that socket: logical $0000 now.
* ram.md 6.4.1 - the hardware will never tell anybody, so the ROM must.
*   +0   bitmap of the sockets that passed, b0 = socket 0
*   +1   total memory in 8 KB blocks, big-endian (512 per 4 MB socket)
        stb     DESCMAP
        ldx     #blks256
        lda     b,x             sockets x 2 = blocks / 256
        sta     DESCBLK
        clra
        sta     DESCBLK+1

        lds     #STACK          the first instruction after which a JSR works
        ldx     #halt           nothing has claimed an interrupt yet
        stx     IRQVEC
        stx     FIRQVEC
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

*==============================================================================
* 2b. The other task.  machine.md 3: the map index is {TASK, block}, so half of
*     the map is TASK 1 -- and until this, TASK was only ever 0 and those eight
*     entries were written and never used.  maptab points task 1's block 5 at a
*     different SIMM page from task 0's, so one logical address, $A000, is two
*     physical bytes; the ROM stores a different value under each task and
*     reads both back.  Blocks 6 and 7 are the same in both tasks, so the stack
*     and the instruction stream do not move when TASK does.
*==============================================================================
        lda     #$C3
        sta     TASKT           task 0's block 5
        lda     #$01
        sta     TASKR           TASK := 1 -- D0 is the task; RUN is not touched
        lda     #$3C
        sta     TASKT           task 1's block 5: another page
        clra
        sta     TASKR           TASK := 0
        lda     TASKT
        cmpa    #$C3
        bne     taskbad
        lda     #$01
        sta     TASKR
        lda     TASKT
        cmpa    #$3C
        bne     taskbad
        clra
        sta     TASKR           and leave it at 0
        lda     #P_TASK
        sta     SIMPORT
        bra     strate

taskbad lda     #P_BADT
        sta     SIMPORT
        jmp     halt


rambad  lda     #P_BADR
        sta     SIMPORT
        jmp     halt

*==============================================================================
* 2a. What a store actually costs -- graphics.md 19 item 1.
*
*     Every CPU-cost figure in 7.3 scales on "~5 core-6309 cycles per store,
*     native mode" and nothing in this repository had ever counted one.  This
*     counts one, for the 6809E core that is really in the socket.
*
*     TWO STRAIGHT-LINE BLOCKS AND A SUBTRACTION.  Block A is 32 `sta ,x+`,
*     block B is 64, and each is bracketed by an identical `lda #imm` + `sta
*     SIMPORT`.  The difference between the two intervals is therefore EXACTLY
*     32 stores: the bracketing instructions, the progress write itself and any
*     fixed entry cost all appear in both and cancel.  There is no branch
*     inside either block, so no taken-branch cost is being folded in either.
*
*     ⚠ THE TARGET IS SIMM, NOT VRAM.  A VRAM store is posted and can meet
*     plan 5's /WAIT, which would measure the card rather than the CPU -- and
*     the card's own retire rate is already measured elsewhere.
*
*     ⚠ IT IS THE 6809 NUMBER.  vendor/mc6809 is cycle-accurate and it is a
*     6809, so this is emulation mode -- the baseline 7.3's native-mode claim
*     says it beats.  19 item 1 stays open for the 6309 figure.
*==============================================================================
strate  ldx     #STORET
        lda     #P_ST0
        sta     SIMPORT
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        lda     #P_ST1
        sta     SIMPORT
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        lda     #P_ST2
        sta     SIMPORT

*==============================================================================
* 2c. ⭐ IS THERE A video3 CARD IN THE SLOT?  AND THIS IS NOT OPTIONAL.
*
*     boot.bin is ROM page 0 of EVERY build of this machine, including builds
*     whose NitrOS-9 drives archive/video/'s card, and software/demo/emu models
*     both (machine.c's m->v3).  Sections 3..10 below poll VSTAT; on the other
*     card $FF6D is not VSTAT at all but a plain register-file byte, so a poll
*     of it reads back whatever was last written there and CAN SPIN FOR EVER.
*     CLAUDE.md: a hang is worse than a failure.  So the card is identified
*     first, and if it is not this one the whole video section is skipped and
*     $06 says so.
*
*     THE PROBE IS +$13, AND HERE IS WHY IT CANNOT ANSWER WRONG EITHER WAY:
*       video3            +$13 is CPTR1, the copy source's middle byte.  It is
*                         an ordinary register-file location: v3host's RDBKOE
*                         covers it (A4 is set), so a read gives back the byte
*                         that was written.
*       archive/video     +$13 is VSTAT, and graphics.md 13 says it is read
*                         "through the '244 of 12.1, not the register file".
*                         That '244 carries SPANBUSY, VBLANK, HBLANK, LRUN,
*                         PBUSY and IRQ -- and b2 and b3 are hardwired zero.
*                         $A5 has b2 set and $5A has b3 set, so NEITHER of the
*                         two patterns below can ever be read back from it, in
*                         any state of the card, at any point in the frame.
*       an empty slot     nothing drives D0-D7 (it has no pull-ups), so the
*                         bus holds whatever it last carried.  The ROM byte
*                         read between the store and the load is what makes
*                         that visible -- ram.md 6.4.1's rule, used here for
*                         the same reason it is used on the SIMM.
*
*     Two patterns rather than one, so that a bus stuck at either level fails
*     one of them.  A write to +$13 costs nothing on either card: on video3 it
*     is CPTR1, reloaded before every copy; on the other it clears an interrupt
*     flag that cannot be pending, because no interrupt is enabled yet.
*==============================================================================
vprobe  lda     #$A5
        sta     CPTR1
        lda     rombyte         drive the bus with something else
        lda     CPTR1
        cmpa    #$A5
        bne     novid
        lda     #$5A
        sta     CPTR1
        lda     rombyte
        lda     CPTR1
        cmpa    #$5A
        bne     novid
        clra
        sta     CPTR1           and leave it where 7's copy expects it
        lbra    palette

novid   lda     #P_NOVID
        sta     SIMPORT
        jmp     prog

*==============================================================================
* 3. The palette.  plan 10: a PDATH write POSTS the commit to the next HLOAD,
*    and writes during active display cost a fetch slot, so this runs with the
*    display off -- CTRL is 0 out of reset and stays that way until step 6.
*    Entry i is $i i, which makes every index distinguishable in a screenshot
*    without a lookup table.
*
* ⛔ AND THE INDEX IS WRITTEN FOR EVERY ENTRY rather than left to step itself,
*    which is v3boot.asm's rule and the reason for it is a live defect:
*    OUTSIDE VBLANK THE POSTED COMMIT FIRES ON EVERY DOT OF HLOAD.  v3host
*    holds PPEND with `PPEND & ~PS0`, so PS0 is set again on HLOAD's second
*    dot, the LUT is written twice one dot apart and PIDXCE steps the index
*    TWICE.  A 256-entry load that leans on the auto-increment therefore writes
*    479 entries at every other address, wraps, and comes back over the ones it
*    got right.  v3boot.asm section 2a asks that question once, deliberately
*    and in one place; this ROM writes four registers an entry so that the
*    picture below does not depend on the answer.
*==============================================================================
palette lda     #CT_OFF
        sta     VCTRL
        clra
        sta     WADV            00: continue, and no step-by-two (plan 10)
        sta     PIDXH           sub-palette 0 -- what bitmap and tile mode use
* A is the index and B the poll mask: vwait0 preserves both, so the loop needs
* no RAM and the index is never in the register the mask is passed in.
pall    sta     PIDXL           ⛔ the index, every time - see above
        sta     PDATL           GGGBBBBB
        sta     PDATH           RRRRRGGG -- and this posts the commit
        ldb     #$02
        lbsr    vwait0          VSTAT b1 PBUSY covers the posted commit
        inca
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
* --- every eighth row, re-point block 1 at the next 8 KB of VRAM.
*     The window and the pointer move together, so the address the CPU writes
*     is always the address WPTR names.
        lda     yrow
        anda    #7
        bne     norem
        lda     yrow
        lsra
        lsra
        lsra                    y >> 3 = which 8 KB page of the framebuffer
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
*     the colour out of the register file per retire (plan 5), so a write to
*     WFG mid-span would change the colour half way along it.
        ldb     #$80
        lbsr    vwait0          b7 = SPANBUSY

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

        ldb     #$80
        lbsr    vwait0
        lda     #P_FILL
        sta     SIMPORT

*==============================================================================
* 5. The stripe.  plan 10's WADV = 01 -- "next row, same column" -- is the whole
*    text engine: at span end the pointer advances a row and the COLUMN RELOADS
*    from the register-file shadow, so one register setup and 200 triggers draw
*    an 8-pixel-wide vertical bar.  Written here because it is the one path
*    that reloads WPTR from the register file rather than from the CPU.
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

        ldb     #$80
        lbsr    vwait0
        ldx     taddr
        lda     #$FF            the mask: eight set bits, eight WFG pixels
        sta     ,x

        inc     yrow
        lda     yrow
        cmpa    #ROWS
        bne     strplp

        ldb     #$80
        lbsr    vwait0
        clra
        sta     WADV            back to 00 -- continue
        lda     #P_STRP
        sta     SIMPORT

*==============================================================================
* 6. Show it, in every mode the card has.  plan 2.1 inherits graphics.md 6.2
*    verbatim: VMODE is two bits and all four are native, and until now only 00
*    had ever been reached by software.  The pattern stays where it is: the
*    framebuffer is 1024 x 512 and the modes differ only in how much of it they
*    scan and whether they double, so one framebuffer answers all four and the
*    SHAPE of what comes out is the claim.
*
*    machine_tb captures a frame per scene.  The handshake is the card's own
*    VBLANK - poll VSTAT b6 - which is the tear-free instant and the thing a
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

        lda     #CT_ON          back to 00 for the last two scenes
        sta     VCTRL

*==============================================================================
* 7. ⭐ WHAT video3 HAS INSTEAD OF A DISPLAY LIST.
*
*    ⛔ SECTION 7 USED TO BE THE DISPLAY LIST - two lists, a raster bar and a
*    per-scanline HSCROLL sweep, and P_LSTA / P_LSTB.  video3 deletes the
*    engine outright (plan 0 and 1): no BCTRL, no BSTAT, no LRUN, no descriptor
*    decode, no per-scanline palette and no per-scanline scroll.  Deleting the
*    code and stopping there would have cost this ROM two capabilities' worth
*    of coverage, so the two progress codes now carry the two things this card
*    has that the other did not and that nothing else in this ROM reaches:
*
*      7a  THE COPY ENGINE (plan 6).  Eight rows of sixteen bytes built with
*          the span writer, copied somewhere else with CPTR/WPTR/CWIDTH/
*          CHEIGHT/CCTRL, and read back through VDATA byte for byte.  It is
*          off-screen on purpose - VRAM rows 404 and 420, past the 200 the
*          picture uses - so it cannot disturb section 8's frame, and it reads
*          back through VDATA; machine_tb reads the same 128 bytes out of the
*          array, without the ROM's opinion of them.
*      7b  THE SPRITE (plan 7).  A 16 x 16 two-bit shape in the top 64 bytes of
*          MAPBASE's 64 KB, composed at scan time over the pattern - so what
*          comes out of the connector is the claim, exactly as the raster bar's
*          was.
*==============================================================================
* --- 7a.  The source, the copy, and the read-back --------------------------
CPPAGE  EQU     $06             WPTR/CPTR A18..A16 for both rectangles
CPSLOW  EQU     $5000           VRAM 413,696 -- row 404, well past the picture
CPDLOW  EQU     $9000           ... 430,080 -- row 420
* ⚠ SIXTEEN ROWS APART, NOT EIGHT.  plan 6.2: the engine counts UP only, so a
* copy whose destination overlaps its source AHEAD of the read reads back its
* own output - eight rows apart, the fourth row copied would be the second row
* written.  An overlapping copy stages through scratch in two passes; this one
* simply does not overlap.
CPW     EQU     16              bytes a row
CPH     EQU     8               rows

        lda     #CPPAGE
        sta     wpage
        clr     cprow
cpfill  lda     cprow
        lsla
        lsla
        adda    #CPSLOW/256     the row's high byte: $50 + row * 4
        clrb
        lbsr    setwptr
        ldx     #VRAMWIN
        clr     cpcol
cpf1    lda     cprow
        lsla
        lsla
        lsla
        lsla                    row * 16
        adda    cpcol
        adda    #$80            $80 + row * 16 + col: distinct and never zero
        lbsr    putb
        inc     cpcol
        lda     cpcol
        cmpa    #CPW
        bne     cpf1
        inc     cprow
        lda     cprow
        cmpa    #CPH
        bne     cpfill

* ⚠ WADV IS ALREADY 00 AND MUST BE.  b2 is the WRITE POINTER's step, and the
* copy's destination is WPTR: a GO with b2 set would walk the destination two
* bytes a byte.  plan 10 says so and software/demo/emu reports it as a fault.
        lbsr    idlespn
        ldd     #CPSLOW
        lbsr    setcptr         the source
        ldd     #CPDLOW
        lbsr    setwptr         ... and the destination
        lda     #CPW
        sta     CWIDTH
        lda     #CPH
        sta     CHEIGHT         ⚠ counts once a copy - reloaded above each time
        lda     #$01
        sta     CCTRL           GO.  b1 and b2 are reserved (plan 6.2)
        ldb     #$10
        lbsr    vwait0          VSTAT b4 CBUSY

* The read-back, through VDATA's post-increment - one row at a time, because
* the pointer's column wraps at 1024 and the rows are 1024 apart.
        clr     cprow
cpchk   lbsr    idlespn
        lda     cprow
        lsla
        lsla
        adda    #CPDLOW/256
        clrb
        lbsr    setwptr
        clr     cpcol
cpc1    lda     cprow
        lsla
        lsla
        lsla
        lsla
        adda    cpcol
        adda    #$80            what cpfill put at that byte of the source
        sta     cpexp
        lda     VDATA
        sta     vgot
        lda     cprow
        lsla
        lsla
        lsla
        lsla
        adda    cpcol
        sta     vidx            which byte, if this one is wrong
        lda     vgot
        cmpa    cpexp
        lbne    copybad
        inc     cpcol
        lda     cpcol
        cmpa    #CPW
        bne     cpc1
        inc     cprow
        lda     cprow
        cmpa    #CPH
        bne     cpchk
        clr     wpage
        lda     #P_COPY
        sta     SIMPORT

* --- 7b.  The sprite -------------------------------------------------------
* plan 7: the shape is the top 64 bytes of MAPBASE's 64 KB region -- MAPBASE 7
* puts it at $7FFC0, VRAM row 511 columns 960..1023, which no map address and
* no part of this ROM's picture reaches.  A row is four bytes: plane 0 columns
* 0-7 and 8-15, then plane 1's, bit 7 leftmost, and the pixel's code is
* (plane 1, plane 0).  The shape below is code(r, c) = (r + c) mod 3, so every
* row of it differs from its neighbours and so does every column; code 0 is
* transparent and codes 1 and 2 are the two cursor colours.  Code 3 is never
* used -- plan 7 reserves it.
*
* ⭐ THE COLOURS ARE FOUR PALETTE ENTRIES, NOT 512.  plan 7 loads all 256
* entries of sub-palettes 1 and 2 because a general cursor sits over a general
* picture; this one sits at x 32..47 of picture rows 48..63, and section 4's
* index(x, y) is constant across each 8-row by 128-pixel cell -- so the sprite
* covers exactly two background indexes, $30 and $38, and four LUT entries say
* everything 512 would.
SPRSHL  EQU     $FFC0           the shape's A15..A0 with MAPBASE 7
SPRPG   EQU     $07
SPRPX   EQU     32              the hotspot: the shape's top-left corner
SPRPY   EQU     48
SPRC1   EQU     $5A             sub-palette 1: entry $5A5A
SPRC2   EQU     $A5             sub-palette 2: entry $A5A5

        lda     #SPRPG
        sta     MAPBAS          ⚠ three bits on this card, not seven
        sta     wpage
        ldd     #SPRSHL
        lbsr    setwptr
        ldx     #VRAMWIN
        ldu     #sprsh
        ldb     #64
sprlp   lda     ,u+
        lbsr    putb
        decb
        bne     sprlp
        clr     wpage

* the two cursor colours, in the two sub-palettes the codes address
        lda     #$01
        ldb     #$30
        lbsr    sprpal
        lda     #$01
        ldb     #$38
        lbsr    sprpal
        lda     #$02
        ldb     #$30
        lbsr    sprpal
        lda     #$02
        ldb     #$38
        lbsr    sprpal

        lda     #SPRPX
        sta     SPRX
        lda     #SPRPY
        sta     SPRY
        lda     #$80
        sta     SPRH            enable; X9..X8 and Y8 are all zero here
        lda     #P_SPR
        sta     SIMPORT
        lbsr    settle
        clra
        sta     SPRH            ... and off again: 8 below is not bitmap mode

*==============================================================================
* 8. Tile mode.  plan 2.4, and until now only v3card_tb had reached it.  This
*    puts a tilemap in VRAM with the span writer, points the two base registers
*    at it, sets MODE = 10, and lets the card paint 2,000 cells out of 256
*    bytes of tile data.  What comes out of the connector is the claim.
*
* ⭐ THE TILE SET IS THE BYTES 0..255 IN ORDER, and that is not laziness.
*    The tile address is a CONCATENATION - TILEBASE | code<<6 | row<<3 | col -
*    so the byte holding tile n's pixel (r, c) sits at n*64 + r*8 + c, which
*    for four tiles is exactly the offset itself.  Writing i at offset i makes
*    every pixel's INDEX equal to (n<<6)|(r<<3)|c, and 3's palette is the
*    identity map, so every pixel that reaches the connector names the three
*    fields that addressed it.  Tile mode drives the LUT's high half with ZERO
*    (plan 2.4), so the lookup is sub-palette 0 and the identity holds.
*
* ⭐ AND THE MAP IS A FOUR-BYTE CELL ON A 1024-BYTE STRIDE (plan 2.5), which is
*    the biggest single difference from the card this ROM used to drive: there
*    the cell was one byte on a 128-byte stride.  The code is lane 0 and the
*    attribute lane 2 -- tile mode ignores the attribute -- and WADV b2 makes
*    WPTR step by TWO, so a cell is two stores and not four.  The map's address
*    is {MAPBASE[2:0], cellrow[5:0], 0, cellcol[6:0], lane[1:0]}; the cell row
*    is SIX bits here, so plan 2.5's 64 rows cover every VMODE and
*    graphics.md 6.4.1's "cell mode does not reach 640x400" is not inherited.
*    VMODE 00 anyway, so that the picture is the same 640 x 200 as section 4's.
*==============================================================================
TILEB   EQU     8               tile set at 8 * 16,384  = VRAM 131,072
MAPB    EQU     3               map      at 3 * 65,536  = VRAM 196,608
TBPAGE  EQU     $02             ... which is $20000, so WPTR[18:16] = 2
TBLOW   EQU     $0000
MBPAGE  EQU     $03             ... and $30000
CELLS   EQU     80              cells across, 640 / 8
CROWS   EQU     25              cell rows, 200 / 8

        lbsr    idlespn
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
* down and a row/column swap in the concatenation cannot look right.
*
* ⚠ X AND WPTR NO LONGER MOVE TOGETHER, and that is the point of b2.  X is a
* logical address and all it does is select VRAM; WPTR is what says where the
* byte lands, and with b2 set it steps by two -- so the code goes to lane 0 and
* the filler to lane 2 and the third store is the next cell's.
        lbsr    idlespn
        lda     #MBPAGE
        sta     wpage
        lda     #$04
        sta     WADV            ⭐ plan 2.5: WPTR steps by TWO
        clr     yrow
mrow    lbsr    idlespn
        lda     yrow
        lsla
        lsla                    cellRow * 1024, high byte (rows 0..24)
        clrb
        lbsr    setwptr
        ldx     #VRAMWIN
        clr     ccol
mcol    lda     yrow
        adda    ccol
        anda    #3
        lbsr    putb            the code -- lane 0
        clra
        lbsr    putb            the attribute -- lane 2, ignored in tile mode
        inc     ccol
        lda     ccol
        cmpa    #CELLS
        bne     mcol
        inc     yrow
        lda     yrow
        cmpa    #CROWS
        bne     mrow
        lbsr    idlespn
        clra
        sta     WADV            back to one byte a step
        clr     wpage

        lda     #TILEB
        sta     TBASE
        lda     #MAPB
        sta     MAPBAS
        clra                    tile mode scrolls through the same two
        sta     VSCROLL         registers as bitmap mode, so start them at the
        sta     VSCRLH          top left
        sta     HSCROLL
        sta     HSCRLH
        lda     #CT_ON+CT_TILE  display ON, MODE 10 tile, VMODE 00
        sta     VCTRL
        lda     #P_TILE
        sta     SIMPORT
        lbsr    settle

*==============================================================================
* 10. plan 10: VRAM reads back.
*
* A read is a write run backwards.  The address a load carries selects the VRAM
* window and nothing else; WPTR says which byte, and it post-increments - so X+
* walks a read exactly as putb walks a write.  Three passes:
*   (a) the tile set just drawn, 256 bytes of 0..255, read back while tile mode
*       is on and the map fetch takes every other spare access;
*   (b) a store and a load back to back with NO VSTAT poll between them, 32
*       times - so the load has to wait on /WAIT for the store's span to retire
*       and for the prefetch of the byte after it;
*   (c) the whole of (b)'s area read back, so both halves of (b) are checked;
*   (d) a load issued while a 256-byte span-solid is still retiring.  The
*       prefetch is normally done long before the CPU's next cycle, so (b)
*       never waits; this does - for the whole span - and then gets the byte
*       the span stopped in front of;
*   (e) and the span's 256 bytes read back.
* And the same port at its other address, +$0C VDATA, which needs no MMU block
* at all:
*   (f) 64 stores through VDATA with no poll, read back through the window;
*   (g) the same 64 read back through VDATA, the first waiting on the prefetch;
*   (h) two span-solids started back to back through VDATA and a VDATA load
*       straight after - the second store waits for the first span with E high,
*       which is when a register-file write at +$0C would repaint the span;
*   (i) and the two spans' 512 bytes read back through VDATA.
* Every setwptr is preceded by idlespn: WPTR may not be loaded under a span.
*==============================================================================
SCRPAGE EQU     $06             VRAM row 402 - beside 7a's rectangles, off the
SCRLOW  EQU     $4800           screen
SCRN    EQU     64

* (a) the tile set
        lbsr    idlespn
        lda     #TBPAGE
        sta     wpage
        ldd     #TBLOW
        lbsr    setwptr
        ldx     #VRAMWIN
        clrb
vra     lda     ,x+             the byte at WPTR, and WPTR moves on
        stb     vidx
        cmpa    vidx
        lbne    vbad
        incb
        bne     vra

* (b) prefill with i ^ $A5 ...
        lbsr    idlespn
        lda     #SCRPAGE
        sta     wpage
        ldd     #SCRLOW
        lbsr    setwptr
        ldx     #VRAMWIN
        clrb
vrf     tfr     b,a
        eora    #$A5
        lbsr    putb
        incb
        cmpb    #SCRN
        bne     vrf
* ... then store 2i ^ $3C and load straight back, no poll
        lbsr    idlespn
        ldd     #SCRLOW
        lbsr    setwptr
        ldx     #VRAMWIN
        clrb                    B = 2i
vrb     tfr     b,a
        eora    #$3C
        sta     ,x              posted: retires at base+2i, and WPTR goes to 2i+1
        incb                    B = 2i+1
        lda     ,x              waits for that retire and the prefetch of 2i+1
        sta     vgot
        stb     vidx
        tfr     b,a
        eora    #$A5            the prefill's byte at 2i+1
        cmpa    vgot
        lbne    vbad
        incb                    B = 2i+2, which is where WPTR is now
        cmpb    #SCRN
        bne     vrb

* (c) and the whole area back: stores at the even bytes, the prefill at the odd
        lbsr    idlespn
        ldd     #SCRLOW
        lbsr    setwptr
        ldx     #VRAMWIN
        clrb
vrc     lda     ,x+
        sta     vgot
        stb     vidx
        tfr     b,a
        bitb    #1
        bne     vrc1
        eora    #$3C
        bra     vrc2
vrc1    eora    #$A5
vrc2    cmpa    vgot
        lbne    vbad
        incb
        cmpb    #SCRN
        bne     vrc

* (d) the byte after the span, prefilled ...
SPAT    EQU     $5C             what sits at base+256 before the span
SFG     EQU     $C7             the span's colour
        lbsr    idlespn
        ldd     #SCRLOW+256
        lbsr    setwptr
        lda     #SPAT
        lbsr    putb
* ... then a 256-byte span-solid and a load straight after the store that starts it
        lbsr    idlespn
        ldd     #SCRLOW
        lbsr    setwptr
        lda     #SFG
        sta     WFG
        lda     #255
        sta     SPANLEN
        lda     #CT_ON+CT_TILE+CT_SOL display on, tile, WMODE 10 span-solid
        sta     VCTRL
        sta     ,x              starts the span - 256 retires, one per fetch slot
        lda     ,x              and this waits for all of them, and the prefetch
        sta     vgot
        clr     vidx
        cmpa    #SPAT
        lbne    vbad
        lbsr    idlespn
        lda     #CT_ON+CT_TILE  back to direct writes
        sta     VCTRL
* (e) the span itself
        ldd     #SCRLOW
        lbsr    setwptr
        clrb
vre     lda     ,x+
        sta     vgot
        stb     vidx
        cmpa    #SFG
        lbne    vbad
        incb
        bne     vre

* (f) VDATA stores, no poll, and the window reads them back
VDX     EQU     $96
        lbsr    idlespn
        ldd     #SCRLOW
        lbsr    setwptr
        clrb
vrf2    tfr     b,a
        eora    #VDX
        sta     VDATA           the same posted write: retires at WPTR, which moves on
        incb
        cmpb    #SCRN
        bne     vrf2
        lbsr    idlespn
        ldd     #SCRLOW
        lbsr    setwptr
        ldx     #VRAMWIN
        clrb
vrf3    lda     ,x+
        sta     vgot
        stb     vidx
        tfr     b,a
        eora    #VDX
        cmpa    vgot
        lbne    vbad
        incb
        cmpb    #SCRN
        bne     vrf3

* (g) and VDATA reads them back too - the first load waits for the prefetch
        lbsr    idlespn
        ldd     #SCRLOW
        lbsr    setwptr
        clrb
vrg     lda     VDATA
        sta     vgot
        stb     vidx
        tfr     b,a
        eora    #VDX
        cmpa    vgot
        lbne    vbad
        incb
        cmpb    #SCRN
        bne     vrg

* (h) two span-solids through VDATA, the second store under the first span
VMARK   EQU     $3A             what the stores carry - never the span's colour
SFG2    EQU     $E4
        lbsr    idlespn
        ldd     #SCRLOW+512
        lbsr    setwptr
        lda     #SPAT
        sta     VDATA           the byte after both spans
        lbsr    idlespn
        ldd     #SCRLOW
        lbsr    setwptr
        lda     #SFG2
        sta     WFG
        lda     #255
        sta     SPANLEN
        lda     #CT_ON+CT_TILE+CT_SOL display on, tile, WMODE 10 span-solid
        sta     VCTRL
        lda     #VMARK
        sta     VDATA           span 1: 256 x WFG
        sta     VDATA           waits for span 1 on /WAIT, then span 2
        lda     VDATA           waits for span 2 and the prefetch
        sta     vgot
        lda     #$FF
        sta     vidx
        lda     vgot
        cmpa    #SPAT
        lbne    vbad
        lbsr    idlespn
        lda     #CT_ON+CT_TILE  back to direct writes
        sta     VCTRL
* (i) both spans, 512 bytes, through VDATA
        ldd     #SCRLOW
        lbsr    setwptr
        ldy     #512
vri     lda     VDATA
        sta     vgot
        tfr     y,d
        stb     vidx
        lda     vgot
        cmpa    #SFG2
        lbne    vbad
        leay    -1,y
        bne     vri

        clr     wpage
* Leave the card somewhere a program handed page 1 can recognise: the display
* on, bitmap, direct writes, WADV 00, no sprite and no interrupt - which is
* reset's CTRL with the display bit set, and shows section 4's pattern.
        lbsr    idlespn
        clra
        sta     WADV
        sta     SPRH
        lda     #CT_ON
        sta     VCTRL
        lda     #P_VREAD
        sta     SIMPORT

*==============================================================================
* 11. A program in ROM. machine.md 7.2: everything after page 0 is for "a
*     read-only ROM disk", and until there is one the handoff is the simplest
*     that could work - ROM pages 1 and 2 at blocks 4 and 5, and if $8000 holds
*     "6309", jump to $8004 with the stack, the RAM vectors and every test above
*     behind it. Otherwise the two blocks go back to the SIMM and the ROM stops,
*     exactly as it did before this section existed.
*
* ⚠ The card is left in bitmap mode with the display on, direct writes, WADV
* 00, no sprite and no interrupt - so a program that finds it does not inherit
* tile mode, a sprite or a scroll.  A machine with no video3 card (2c) reaches
* this label without ever having written $FF60-$FF7F except for the probe's
* two bytes.
*==============================================================================
prog    lda     #$01            ROM page 1 at $8000, page 2 at $A000
        sta     MAPLO+4
        sta     MAPHI+4
        lda     #$02
        sta     MAPLO+5
        lda     #$01
        sta     MAPHI+5
        ldx     $8000
        cmpx    #$3633          "63"
        bne     noprog
        ldx     $8002
        cmpx    #$3039          "09"
        bne     noprog
        jmp     $8004
noprog  lda     #$04
        sta     MAPLO+4
        lda     #$05
        sta     MAPLO+5
        lda     MAPHI+6         the SIMM socket 1a chose
        sta     MAPHI+4
        sta     MAPHI+5
halt    bra     halt

* The interrupt vectors' way into RAM - see IRQVEC.
irqtr   jmp     [IRQVEC]
firqtr  jmp     [FIRQVEC]

vbad    lda     #P_BADV         vidx holds the index, vgot the byte
        sta     SIMPORT
        bra     halt

copybad lda     #P_BADC         7a's copy: vidx the byte, vgot what came back
        sta     SIMPORT
        bra     halt

* ⛔ A POLL THAT RAN OUT OF PATIENCE.  vwait0/vwait1 come here rather than
* spinning, so a card that never clears a status bit is a REPORTED fault and
* not a machine that stopped.
vstuck  lda     #P_STUK
        sta     SIMPORT
        bra     halt

*==============================================================================
* vwait0 / vwait1 - poll VSTAT until the bits in B are clear (vwait0) or set
* (vwait1), BOUNDED.
*
* ⭐ THE BOUND IS THE WHOLE POINT, and it is the one place this ROM differs in
* kind from software/v3boot/v3boot.asm, whose header says its polls are
* unbounded on purpose because its bench bounds them.  Nothing bounds a boot
* ROM on a real machine.  65,536 reads is about 0.3 s at this machine's E rate
* - longer than any span (a 256-byte span-solid is ~1,000 dots), any copy
* (128 bytes here) and any frame (359,200 dots), and short enough that a dead
* card reports $E5 instead of hanging the POST.
*
* A, B and X survive; the mask is reached at 3,S, under the pushed A and X.
*==============================================================================
vwait1  pshs    b
        pshs    a,x
        ldx     #0
vw11    lda     VSTAT
        bita    3,s
        bne     vwok
        leax    -1,x
        bne     vw11
        bra     vwbad

vwait0  pshs    b
        pshs    a,x
        ldx     #0
vw01    lda     VSTAT
        bita    3,s
        beq     vwok
        leax    -1,x
        bne     vw01
vwbad   puls    a,x
        puls    b
        jmp     vstuck
vwok    puls    a,x
        puls    b,pc

*==============================================================================
* idlespn - wait for SPANBUSY (VSTAT b7) to clear.  plan 5 / 10: WPTR may not
* be loaded, and no register may be written, while a span is retiring.
*==============================================================================
idlespn pshs    b
        ldb     #$80
        lbsr    vwait0
        puls    b,pc

*==============================================================================
* sprpal - A = the sub-palette (PIDXH), B = the entry (PIDXL); write the cursor
* colour that sub-palette carries.  plan 7: a sprite pixel's code is the LUT's
* A9..A8, so code 1 reads sub-palette 1 and code 2 sub-palette 2 at the
* background byte's own index.
*==============================================================================
sprpal  pshs    a,b
        sta     PIDXH
        stb     PIDXL
        cmpa    #$01
        bne     sp2
        lda     #SPRC1
        bra     sp3
sp2     lda     #SPRC2
sp3     sta     PDATL
        sta     PDATH           the write posts the commit
        ldb     #$02
        lbsr    vwait0          PBUSY
        puls    a,b,pc

*==============================================================================
* setwptr - D = the 16-bit VRAM offset; WPTR := {wpage, D}.  plan 10's
* +$08..+$0A, little-endian.
* setcptr - the same for CPTR at +$12..+$14.
*==============================================================================
setwptr stb     WPTR0
        sta     WPTR1
        pshs    a
        lda     wpage
        sta     WPTR2
        puls    a,pc

setcptr stb     CPTR0
        sta     CPTR1
        pshs    a
        lda     wpage
        sta     CPTR2
        puls    a,pc

*==============================================================================
* putb - retire A into VRAM at WPTR, one byte, WMODE 00.
*
* X names a byte in logical space and post-increments; the address is what
* selects VRAM and WPTR is what says where the byte lands.  ⚠ With WADV b2 set
* the two no longer step together - section 8 says why that is deliberate.
*==============================================================================
putb    pshs    b
        ldb     #$80
        lbsr    vwait0          plan 5: poll SPANBUSY, bounded
        sta     ,x+
        puls    b,pc

*==============================================================================
* settle - give the capture a whole frame to find, by waiting four vertical
* blanks on VSTAT b6.  ⚠ FOUR, not one: machine_tb hunts a VSYNC edge and then
* takes the frame after it, so a scene has to stand still for longer than the
* two frames that costs.
*
* ⭐ AND IT IS THE HANDSHAKE A DRIVER WOULD USE.  plan 10's palette rule and
* plan 9's VBL interrupt both say "do it in vertical blank", and this is the poll
* that finds it - so the wait is the machine exercising a documented path
* rather than a testbench convenience.
*==============================================================================
settle  pshs    a,b
        lda     #4
        sta     nfrm
setl1   ldb     #$40
        lbsr    vwait0          wait until NOT in vertical blank
        ldb     #$40
        lbsr    vwait1          ... then for the edge into it
        dec     nfrm
        bne     setl1
        puls    a,b,pc

*==============================================================================
* The map table: sixteen entries of (low, high), index {TASK, block}.
*
*   block 0,3,4,5,6   SIMM 0, physical 4 MB + n * 8 KB   (A24..A21 = 0010)
*   block 1,2         the video card's VRAM, physical 0.5 MB  (A20:A19 = 01)
*   block 7           the boot ROM's own page 0, 2 MB    (A21 = 1)
*
* Task 1's eight entries are the same except block 5, which 2b uses to prove
* the task bit selects half the map.  The SIMM entries' high byte, $02, is
* socket 0's and 1a rewrites it for the lowest socket that passed.
* ram.md 5.2 is the physical map they name.
*==============================================================================
maptab
        FCB     $00,$02         block 0  $0000  SIMM0 + 0
        FCB     $40,$00         block 1  $2000  VRAM page 0   <- moved, above
        FCB     $41,$00         block 2  $4000  VRAM page 1
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
        FCB     $07,$02         block 5  $A000  SIMM + 7    <- task 1 only
        FCB     $06,$02
        FCB     $00,$01

rombyte FCB     $C3             a known ROM byte, for the read-back test

* 1a's tables, indexed by B.
sockbit FCB     1,0,2,0,4,0,8   B = 2,4,6,8 (from sockbit-2) -> the socket's bit
lowhi   FCB     $00,$02,$04,$02,$06,$02,$04,$02 bitmap -> lowest socket's high byte
        FCB     $08,$02,$04,$02,$06,$02,$04,$02
blks256 FCB     0,2,2,4,2,4,4,6 bitmap -> sockets x 2, which is blocks / 256
        FCB     2,4,4,6,4,6,6,8

* 7b's sprite shape, 16 rows of four bytes: plane 0 columns 0-7 and 8-15, then
* plane 1's, bit 7 leftmost.  code(r, c) = (r + c) mod 3, which has period
* three down the rows - so the sixteen rows are A B C A B C ... and a row slip
* by one or two is a wrong pixel.  machine_tb states the rule rather than the
* bytes, which is what makes the table a claim and not a copy.
sprsh
        FCB     $49,$24,$24,$92         row  0   (r mod 3 = 0)
        FCB     $92,$49,$49,$24         row  1   (1)
        FCB     $24,$92,$92,$49         row  2   (2)
        FCB     $49,$24,$24,$92         row  3
        FCB     $92,$49,$49,$24         row  4
        FCB     $24,$92,$92,$49         row  5
        FCB     $49,$24,$24,$92         row  6
        FCB     $92,$49,$49,$24         row  7
        FCB     $24,$92,$92,$49         row  8
        FCB     $49,$24,$24,$92         row  9
        FCB     $92,$49,$49,$24         row 10
        FCB     $24,$92,$92,$49         row 11
        FCB     $49,$24,$24,$92         row 12
        FCB     $92,$49,$49,$24         row 13
        FCB     $24,$92,$92,$49         row 14
        FCB     $49,$24,$24,$92         row 15

*==============================================================================
* Variables.  Block 6, which is the SIMM -- so nothing here is touched before
* step 2 has proved the SIMM answers.
*==============================================================================
yrow    EQU     RAMWIN+$10      current row, 0..199
ccol    EQU     RAMWIN+$11      current span or cell within the row
taddr   EQU     RAMWIN+$12      the logical address the trigger writes (2 bytes)
cprow   EQU     RAMWIN+$14      7a's rectangle row
cpcol   EQU     RAMWIN+$15      ... and column
nfrm    EQU     RAMWIN+$16      settle's frame counter
wpage   EQU     RAMWIN+$17      WPTR[18:16] for the next setwptr/setcptr
cpexp   EQU     RAMWIN+$18      7a's expected byte
vidx    EQU     RAMWIN+$1A      section 10's byte index - which byte, on a failure
vgot    EQU     RAMWIN+$1B      ... and the byte that was read

*==============================================================================
* The vector page.  machine.md 7.2: $FFC0-$FFFF is served by the ROM
* unconditionally, which is the whole reason $FFFE is a reset vector and not an
* undriven bus.  In ROM these are at $1FF2-$1FFF.
*==============================================================================
*
* ⭐ THE SIX INTERRUPT VECTORS POINT AT $FEEE-$FEFD, WHICH IS WHERE A CoCo 3's
* DO. That is not in this page's fixed $FFC0-$FFFF window: it is logical
* block 7, so what runs is whatever block 7 holds. In boot mode, and under any
* program handed page 1 (software/demo/), block 7 is this ROM page and the six
* entries below are its own jumps - to the same RAM vectors as before. Under
* NitrOS-9 block 7 is the kernel's RAM block in every map, and NitrOS-9's krn
* ends at $FF00 with its BRA stubs at exactly these addresses
* (docs/nitros9-av-plan.md 8 item X3). One ROM serves both.
        ORG     $FEEE
vswi3   jmp     halt            $FEEE  SWI3
vswi2   jmp     halt            $FEF1  SWI2
vfirq   jmp     firqtr          $FEF4  FIRQ - through FIRQVEC
virq    jmp     irqtr           $FEF7  IRQ - through IRQVEC
vswi    jmp     halt            $FEFA  SWI
vnmi    jmp     halt            $FEFD  NMI

        ORG     $FFF2
        FDB     vswi3           SWI3
        FDB     vswi2           SWI2
        FDB     vfirq           FIRQ
        FDB     virq            IRQ
        FDB     vswi            SWI
        FDB     vnmi            NMI
        FDB     reset           RESET

        END     reset
