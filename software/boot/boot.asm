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
*  10a. ⭐ PUTS UP THE BOOT DIALOG -- docs/boot-and-desktop.md 1
*  10b. ⭐ READS THE SD CARD -- storage/docs/sdcard.md 9.0, 9.1 and 9.5 -- to
*       decide which of 10a's three pictures is the true one
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

*--------------------------------------------------------------- the card ---
* storage/docs/sdcard.md 6.2 -- four bytes at $FF58.  10a reads the one with
* no side effect (SDSTAT is read-only and reading it starts nothing, 6.3) and
* 10b drives the other three.
*
* ⛔ SDDATA IS NEVER TOUCHED SPECULATIVELY.  A read of it returns the previous
* burst's byte AND STARTS ANOTHER, so every access below is one 10b's
* sequences meant to make; there is no "have a look at the port" anywhere in
* this ROM, and there must not be one added.
SDDATA  EQU     $FF58           R: the previous burst's byte; W: MOSI + a burst
SDSTAT  EQU     $FF59           R only
SDCTRL  EQU     $FF5A           W only
SDMOSI  EQU     $FF5B           W only, and it triggers nothing
SD_BUSY EQU     $01             SDSTAT b0: a burst is OWED or running (6.3)
SD_CD   EQU     $02             b1: 1 = a card is in the socket
SD_CS   EQU     $01             SDCTRL b0: 1 asserts the card's /CS
SD_FAST EQU     $02             b1: 1 = 12.588 MHz, 0 = the 393 kHz init clock

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
* 10a's boot dialog -- docs/boot-and-desktop.md 1.  Each state is a picture,
* so each gets a code: a testbench that only saw "the dialog ran" would not
* know WHICH of the three was drawn, and the three are the whole point.
P_DLGL  EQU     $60             the dialog is up, state "looking for a disk"
P_DLGF  EQU     $61             ... "found": SDSTAT says a card is in the socket
P_DLGQ  EQU     $62             ... the Mac's blinking question mark: no disk
P_NOTB  EQU     $63             ⭐ no toolbox in the ROM - the dialog is SKIPPED
P_BADTB EQU     $E6             ... the toolbox returned an error; B said which
* 10b's verdict, and it is written BEFORE the picture it chooses.  ⭐ $62 is
* reached two ways now and a bench has to be able to tell them apart: a socket
* with nothing in it, and a card that is there and is not bootable.  The
* second is the Mac's actual question mark and is the state 10b added.
P_SDOK  EQU     $64             ⭐ CMD58 said CCS and block 0 carries "6309"
P_SDBAD EQU     $65             ⛔ a card is in the socket and it is not bootable

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

        lbsr    dialog          ⭐ 10a - the boot dialog, below
        lbra    prog            ... and then 11, past the code it is made of

*==============================================================================
* 10a. ⭐ THE BOOT DIALOG -- docs/boot-and-desktop.md 1.
*
* A Macintosh 128K finds its video hardware, clears the screen, and puts up a
* dialog with an icon that says it is looking for a disk; the icon changes when
* it finds one, and blinks a question mark when it does not.  This is that,
* drawn with the ROM TOOLBOX (nitros9 level2/arm6309/modules/tbox.asm, ROM page
* TB.Pg = 64), which already draws Haiku windows, bevels, anti-aliased text and
* icons -- and whose icon set already has `disk`.
*
* ⚠ IT IS LAST, NOT FIRST, and that is deliberate.  The Mac's order is probe,
* clear, dialog; this ROM's sections 3-10 paint whole frames that machine_tb
* compares pixel for pixel, so a dialog drawn before them would be painted over
* by every one of them and would break every frame claim on the way past.  It
* is therefore the LAST picture the POST leaves on the screen, which is also
* the one the machine is holding when NitrOS-9 takes over -- so what a person
* sees is still "the POST ran, and then the machine went looking for a disk".
*
* ⚠ AND IT IS INSIDE 2c's SKIP: a machine with no video3 card reaches `prog`
* from `novid` without coming through here at all.
*
* ⛔ HOW THE TOOLBOX IS CALLED, AND WHY IT NEEDED NOTHING ADDED TO IT.  tbox's
* routines read `>CoG+...` and want Y = VG -- CoArm's context -- and at boot
* there is no CoArm.  But CoG is Co.Data = $6000, a LOGICAL address in CoArm's
* own map, and Co.WinA = $A000, Co.WinB = $C000 (nitros9 defs/armvid.d).  The
* POST owns the whole map, so it simply reproduces that layout:
*
*   blocks 3 and 4  ($6000-$9FFF)  SIMM, already -- the CoG scratch.  tbox's
*                                  own RAM (TB = CoG + CG.LBuf = $8A4C) is in
*                                  block 4, and so is CG.TbV
*   block 5         ($A000)        ROM page TB.Pg -- the toolbox's code, where
*                                  it expects to be running from
*   block 6         ($C000)        the toolbox's DATA pages, as tbox switches
*                                  them through TV.MapB
*
* and then calls it the way ca_tbox.asm's TbGo does: `ldd #$FF00+TB.Pg`, map
* it, `jsr >Co.WinA+3`, with B = the function, X = its parameter block (big-
* endian words) and Y = a VG.
*
* ⛔ BLOCK 6 IS THE STACK, WHICH IS WHY THE STACK MOVES.  `lds #STACK` put S at
* $E000, descending into block 6 -- the block the toolbox's data has to occupy.
* So the dialog runs on a stack of its own in block 0 (DSTK) and puts S back
* afterwards.  The variables at $C010-$C01B go under the data page too; nothing
* below reads them again, and they are SIMM bytes that the remap only HIDES, so
* they are all still there when block 6 comes back.
*
* ⭐ AND SINCE 2026-09-21 THE MACHINE HAS AN SD READER: 10b, below.  "Found"
* is no longer SDSTAT's card-detect bit -- it is a card that answered CMD58
* with CCS and whose block 0 carries the boot signature sdcard.md 9.5 defines.
* `bootchk` is where the two meet, and the question mark now means what it
* means on a Macintosh: there IS a disk and it is not a system disk.
*
* ⛔ AND A COMMENT ON A pshs/puls LINE MUST NOT START WITH A COMMA.  A09 has no
* comment delimiter and keeps parsing a REGISTER LIST across the whitespace, so
* `pshs d    ,s = pixels left` assembles as PSHS A,B,U -- four bytes where two
* were meant.  Every register list below is written out in full for the same
* reason; software/boot/README.md records what it cost.
*==============================================================================
TB_PG   EQU     64              nitros9 defs/arm6309.d TB.Pg
ROM_HI  EQU     $01             ... ROM.Hi: the map high byte of the boot ROM
TBENT   EQU     $A003           Co.WinA + 3 -- tbox.asm's Entry
COG     EQU     $6000           Co.Data, and every CG.* below is off it

* ⛔ THESE OFFSETS ARE nitros9 defs/armvid.d's, COPIED.  There is no way to
* include that file here -- it is lwasm source and this is A09 -- so
* software/nitros9/mkrom.sh re-derives all 22 of them with lwasm and
* refuses to build a ROM whose two halves disagree.  Without that check a
* field that moved in the driver tree would put the dialog's clip, or its
* vector table, somewhere else and nothing would say so.
CG_DEV  EQU     $0002           the "device": PN reads WT.Parms+1 off it
CG_TMP  EQU     $0015           TPal leaves an RGB565 entry here
CG_WINB EQU     $0099           the block at Co.WinB, or $FFFF -- MapB's cache
CG_TSTR EQU     $009B           the target: 0 is the card
CG_TTOP EQU     $009D           the card's ring row of screen row 0
CG_RY   EQU     $009F           a row op: where ...
CG_RX   EQU     $00A1
CG_RN   EQU     $00A3           ... and how many pixels
CG_FH   EQU     $000B           FillRect: how many rows
CG_CX0  EQU     $00AD           the clip, SCREEN pixels, inclusive
CG_CY0  EQU     $00AF
CG_CX1  EQU     $00B1
CG_CY1  EQU     $00B3
CG_OX   EQU     $00B5           the working area's origin
CG_OY   EQU     $00B7
CG_TBV  EQU     $2F6F           TbVec: what the toolbox calls back through
WT_PCNT EQU     43              WT.Parms+1 -- the parameter BYTE COUNT

* The card's registers as offsets from U, which the row layer below loads from
* the VG it is handed.  The absolute names above are the same bytes.
R_CTRL  EQU     $00
R_SPLEN EQU     $05
R_WFG   EQU     $06
R_WPTR0 EQU     $08
R_WPTR1 EQU     $09
R_WPTR2 EQU     $0A
R_WADV  EQU     $0B
R_VDATA EQU     $0C
R_PIDXL EQU     $0E
R_PIDXH EQU     $0F
R_PDATL EQU     $10
R_PDATH EQU     $11
VGBASE  EQU     $10             VG.Base's offset in the VG handed to tbox

* tbox's function numbers (tbox.asm TbTab)
TF_TEXTC EQU    1
TF_ICON EQU     2
TF_WIN  EQU     4
TF_RECT EQU     5
TF_PAL  EQU     7

* the toolbox palette (mktbox.py's UI list, and tbox.asm's own equates)
C_PANEL EQU     2
C_DESK  EQU     6
R_PANEL EQU     32              the text ramp on a panel: 32-34, ink last
R_WHITE EQU     35              ... and on white, which is the question mark's
F_REG   EQU     0
F_BOLD  EQU     1
F_OPAQ  EQU     4               the glyph draws its own paper: one run a row

* Where the dialog is.  Screen pixels: the origin below is (0, 0), so a
* parameter IS a screen coordinate and machine_tb can state these numbers.
* ⭐ THE DIALOG IS 640x480, THE SAME MODE THE DESKTOP USES.  VMODE 11 is
* 640x480 progressive; VMODE 00, which the rest of the POST paints in, is
* 640x200 shown as 400 doubled lines.  Drawing the dialog in 00 made it a
* 400-line picture that a 480-line screen letterboxes - it read as stretched
* beside the desktop, which is the only other thing a person sees.  Ending
* the POST in the desktop's mode also means NO MODE CHANGE at the handover to
* NitrOS-9: what CoArm finds is what the ROM left.
CT_ON48 EQU     $83             display on, WMODE 00 direct, VMODE 11
DLGSCRH EQU     480             and the screen the dialog centres itself in

WINW    EQU     288
WINH    EQU     96
WINX    EQU     (640-WINW)/2
WINY    EQU     (DLGSCRH-WINH)/2
CONX    EQU     WINX+5          TWin's content area: X+5 Y+5 W-10 H-10
CONY    EQU     WINY+5
CONW    EQU     WINW-10
CONH    EQU     WINH-10
ICONX   EQU     WINX+20         the 32 x 32 `disk` icon
ICONY   EQU     WINY+28
ICONS   EQU     32
TXTX    EQU     WINX+60         the line beside it, centred in TXTW
TXTW    EQU     WINW-80
TXTY    EQU     WINY+36
DLGBLK  EQU     2               ⛔ how many times the question mark blinks -
*                               BOUNDED, like every other wait in this ROM
DLGBLF  EQU     3               ... and how many blanks a phase lasts
DLGSET  EQU     4               ⚠ and how long a STATE stands still: four, for
*                               settle's reason - machine_tb hunts a VSYNC edge
*                               and takes the frame after it, which costs two

dialog
* --- is there a toolbox in this ROM at all? -------------------------------
* ⛔ boot.bin IS ROM PAGE 0 OF EVERY BUILD, and most of them have nothing on
* page 64: machine_tb loads boot.hex alone for six of its seven scenarios, and
* a bare `npm run rom` produces an 8 KB image and no more.  So the toolbox is
* identified exactly as ca_tbox.asm identifies it - the two bytes "TB" at
* Co.WinA - and if it is not there the dialog is skipped and $63 says so.
* Nothing is on the stack yet and block 6 has not moved, so this costs a map
* write and a compare.
        lda     #TB_PG
        sta     MAPLO+5
        lda     #ROM_HI
        sta     MAPHI+5
        ldx     TBENT-3         Co.WinA
        cmpx    #$5442          "TB"
        beq     dlgrun
        lda     #$05            block 5 back to the SIMM page it had
        sta     MAPLO+5
        lda     MAPHI+6         ... in the socket 1a chose
        sta     MAPHI+5
        lda     #P_NOTB
        sta     SIMPORT
        rts

dlgrun  sts     dstksv          ⛔ the stack leaves block 6 - see the header
        lds     #DSTK
* ⛔ AND THE SIMM'S MAP HIGH BYTE IS TAKEN NOW, NOT AT THE END.  1a chose the
* socket and wrote its high byte into every SIMM entry, and section 11 recovers
* it by reading MAPHI+6 back -- but the toolbox's own MapB writes MAPHI+6 on
* its first call, so by the time the dialog is over that byte is the ROM's.
* Read before, restore after.
        lda     MAPHI+6
        sta     simmhi

* --- CoG: the fields tbox and the row layer below actually read ------------
* Each one, and why it is here.  Anything NOT set is unread on these paths:
*   CG.WinA   only ca_row's MapA, which tbox cannot call - Co.WinA is its code
*   CG.Off, CG.DBlk   DSeek/DNext, the DRAM-store back end, which CG.TStr = 0
*                     never reaches
*   CG.MFg, CG.MBg, CG.MTr   RowMask and Glyph, which have no TbVec entry at
*                     all, so no toolbox call can reach them
*   CG.CurS   CoArm's TbPalSet/TbPalShw want a screen record; ours do not
*   CG.RX, RY, RN, FH   written by tbox itself before every single call out
        ldx     #tbvec
        stx     COG+CG_TBV      TVCALL adds the entry offset to this and
*                               jsr [,]s through it: with it unset the first
*                               rectangle jumps into whatever the SIMM holds
        ldx     #tbdev
        stx     COG+CG_DEV      PN answers WT.Parms+1 off this, which is how
*                               TStr finds a call's string and its length
        ldd     #0
        std     COG+CG_OX       the origin: parameters are screen pixels
        std     COG+CG_OY
        std     COG+CG_CX0      the clip, inclusive - FillC clamps to it and
        std     COG+CG_CY0      BlitRow drops a row outside it, so unset it
        std     COG+CG_TSTR     "the card" (the row layer below is card-only,
*                               and TImage's raw path is the only tbox code
*                               that reads it)
        std     COG+CG_TTOP     the ring row of screen row 0: VSCROLL is 0
        ldd     #639
        std     COG+CG_CX1
        ldd     #DLGSCRH-1      ⚠ 479, not 199: the clip is INCLUSIVE and in
*                               SCREEN rows, so in VMODE 00's 200 it stopped
*                               the window dead - BlitRow drops a row outside
*                               it and FillC clamps to it, so the dialog drew
*                               its frame and nothing else
        std     COG+CG_CY1
        ldd     #$FFFF          ⛔ MapB is a COMPARE against CG.WinB: a stale
        std     COG+CG_WINB     value that happens to match leaves the wrong
*                               ROM page in the window and says nothing

* --- the palette, the screen, and the dialog -------------------------------
* ⚠ THE DISPLAY IS OFF FOR THIS, which is section 3's rule and the same reason:
* a PDATH write posts a commit to the next HLOAD, and outside vertical blank
* that commit fires twice (see 3).  The toolbox's Pal writes the index for
* every entry, so it would survive it, but there is no reason to pay for the
* fetch slots either.  It goes back on before anything waits for a frame.
        clr     tbctl           CT_OFF: display off, bitmap, WMODE 00
        lda     #CT_OFF
        sta     VCTRL
        ldb     #TF_PAL         256 Haiku entries, from the toolbox's own pages
        ldx     #ppal
        lbsr    tbcall
        ldb     #TF_RECT        and the screen cleared to the desktop's blue
        ldx     #pclear
        lbsr    tbcall
        ldb     #TF_WIN         the Haiku tab and frame, titled
        ldx     #pwin
        lbsr    tbcall
        lbsr    dlgcont         the content panel
        lbsr    dlgicon         ... and the disk icon on it
        ldb     #TF_TEXTC
        ldx     #ptlook
        lbsr    tbcall

        lda     #CT_ON48        the display on, in the DESKTOP's mode
        sta     tbctl
        sta     VCTRL
        lda     #P_DLGL
        sta     SIMPORT
        lda     #DLGSET
        lbsr    dlgwait

* --- which state? ----------------------------------------------------------
* ⭐ SDSTAT b1, CARD DETECT (storage/docs/sdcard.md 6.3).  A read of SDSTAT has
* no side effect; nothing else in the four-byte window is touched.  It is the
* CHEAP half of the question and it is asked first: a socket with nothing in
* it needs no SPI at all, and 10b's reader would spend its whole bounded
* patience finding that out.
* ⚠ ON A MACHINE WITH NO STORAGE CARD nothing drives $FF59 and the answer is
* whatever the bus was holding, so this test alone can say "a card".  10b is
* what makes that harmless: a socket that answers CD and then does not answer
* CMD0 is not bootable, and the question mark is the honest picture of it.
        lda     SDSTAT
        bita    #SD_CD
        beq     dlgnone

* ⭐⭐ THE HOOK, AND IT IS WIRED (2026-09-21).  docs/boot-and-desktop.md 2:
* "found" means a card the ROM has READ A BOOT SIGNATURE OFF - 9.0's power-up,
* 9.1's CMD17, CMD58's CCS and block 0's header - and not merely a socket
* switch that is closed.  10b is that reader; it answers carry clear for a
* card this machine can boot from and carry set for everything else, and the
* question-mark picture is now the Mac's actual third state: A DISK IS IN THE
* DRIVE AND IT IS NOT A SYSTEM DISK.
*
* ⚠ THE VERDICT IS NOT HANDED TO ANYBODY.  It drives the picture and nothing
* else.  Which OS9Boot the machine actually loads is decided again, from
* scratch, by the NitrOS-9 `boot_sd` module (nitros9 level2/arm6309/modules/
* boot_sd.asm) - because that code runs in a different map with a different
* stack and cannot trust a byte this one left behind, and because a ROM that
* published a flag would have two places to get the precedence wrong.  Both
* apply the same rule (sdcard.md 9.5).
*
* ⛔ AND SINCE 2026-09-22 THIS STATE IS TERMINAL.  The ROM used to carry a
* NitrOS-9 to fall back to; it carries a boot monitor and a toolbox now, so a
* machine with no system disk has nothing to start.  The question mark blinks
* for ever rather than handing off to a kernel with nothing to load.
bootchk lbsr    sdprobe
        bcc     bootok
        lda     #P_SDBAD        a card, and not one this machine can boot
        sta     SIMPORT
        bra     dlgnone
bootok  lda     #P_SDOK
        sta     SIMPORT
        lbsr    dlgcont
        lbsr    dlgicon
        ldb     #TF_TEXTC
        ldx     #ptfound
        lbsr    tbcall
        lda     #P_DLGF
        sta     SIMPORT
        lda     #DLGSET
        lbsr    dlgwait
        bra     dlgend

* --- no disk: the Macintosh's blinking question mark -----------------------
dlgnone lbsr    dlgcont
        lbsr    dlgicon
        ldb     #TF_TEXTC
        ldx     #ptnone
        lbsr    tbcall
        lbsr    dlgqm           the question mark, on the icon
        lda     #P_DLGQ
        sta     SIMPORT
        lda     #DLGSET
        lbsr    dlgwait
        lda     #DLGBLK
        sta     nblink
dlgb1   lda     #DLGBLF
        lbsr    dlgwait
        ldb     #TF_RECT        off: the icon's box, erased
        ldx     #picbox
        lbsr    tbcall
        lda     #DLGBLF
        lbsr    dlgwait
        lbsr    dlgicon         ... and on again, with the mark
        lbsr    dlgqm
* ⛔ FOR EVER.  It used to blink DLGBLK times and fall through to section 11,
* because the ROM disk was there to boot instead.  There is no ROM disk: a
* hand-off here reaches krn, whose boot_sd finds no card and cannot load
* OS9Boot, and the machine dies with a crash code instead of the picture that
* explains it.  This is the Macintosh's answer and it is the honest one.
* ⚠ nblink and DLGBLK are kept: the blink RATE is still theirs, and a bench
* that wants a bounded run bounds it with its own clock.
        bra     dlgb1

* --- put the machine back the way section 11 expects it --------------------
dlgend  lda     simmhi          the socket 1a chose, taken before MapB ran
        sta     MAPHI+5
        sta     MAPHI+6
        lda     #$06            ⚠ block 6 FIRST: the stack cannot come home
        sta     MAPLO+6         until $C000-$DFFF is the SIMM again
        lda     #$05
        sta     MAPLO+5
        lds     dstksv
        rts

* --- the pieces each state is made of --------------------------------------
* dlgcont - the content area, panel grey.  TWin leaves it C.Frame.
dlgcont pshs    b,x
        ldb     #TF_RECT
        ldx     #pcont
        lbsr    tbcall
        puls    b,x,pc

* dlgicon - the icon's 32 x 32 box, cleared and then the `disk` icon on it
dlgicon pshs    b,x
        ldb     #TF_RECT
        ldx     #picbox
        lbsr    tbcall
        ldb     #TF_ICON
        ldx     #picon
        lbsr    tbcall
        puls    b,x,pc

* dlgqm - the question mark, centred over the icon.  The ramp is the white one
* and the font asks for its paper (F.Opaq), so the glyph brings its own box and
* is legible on top of the disk.
dlgqm   pshs    b,x
        ldb     #TF_TEXTC
        ldx     #pquest
        lbsr    tbcall
        puls    b,x,pc

* dlgwait - A vertical blanks, so a state or a blink is on the screen long
* enough to be seen and long enough to be captured.  ⛔ Bounded, like settle:
* each half is vwait0/vwait1, which report $E5 rather than spin.
*
* ⛔ AND IT IS NOT `settle`, WHICH IS THE SAME WAIT.  settle counts its frames
* in `nfrm`, which is RAMWIN+$16 -- BLOCK 6, and block 6 is the toolbox's data
* page for the length of the dialog.  Calling it here would store a frame count
* into a ROM page: the write goes nowhere, `dec` reads back a byte of a font,
* and the loop ends when that byte happens to be 1.  The counter below is in
* block 0 with the rest of 10a's state, which is why 10a has any state there.
dlgwait pshs    a,b
        sta     nblnkf
dlgw1   ldb     #$40
        lbsr    vwait0
        ldb     #$40
        lbsr    vwait1
        dec     nblnkf
        bne     dlgw1
        puls    a,b,pc

*==============================================================================
* 10b. THE BOOT ROM'S SD READER -- storage/docs/sdcard.md 9.0 and 9.1.
*
* Enough of the card to answer ONE question: is the thing in the socket a
* volume this machine can boot from?  9.0's initialisation and 9.1's CMD17
* read of block 0, and nothing else -- no filesystem, no directory walk, no
* write path, no 512-byte cache.  `rbsd` (nitros9 level2/arm6309/modules/
* rbsd.asm) is the full driver and is the working model for every sequence
* here; this is about 400 of its 983 bytes.
*
* ⛔ WHAT IT DOES NOT DO IS LOAD ANYTHING.  The OS still comes out of a
* NitrOS-9 `Boot` module, and reading OS9Boot is that module's job
* (boot_sd.asm).  This reader exists so that 10a's "found" is a STATEMENT
* ABOUT THE MEDIA and not about a switch: the socket's card-detect contact is
* closed by a lump of plastic, and the picture beside it says "Disk found".
*
* ** THE SEQUENCE, and the two places it is easy to get silently wrong:
*
*   9.0 step 1, `SDMOSI <- $FF` BEFORE the 74 power-up clocks.  The '574 that
*   holds MOSI has no clear input (6.4), so at power-up it holds garbage; SD
*   requires >= 74 clocks with /CS AND DI high before CMD0, and a card that
*   is clocked with DI low through them may never enter SPI mode at all.  It
*   is one instruction and it is the difference between a card and a brick.
*   sd_model.v and the host emulator both REFUSE a CMD0 that arrives without
*   them, which is why that hazard is tested rather than described.
*
*   9.1 step 5, the data-token poll, and the one-byte pipeline behind it
*   (6.2).  A read of SDDATA returns the byte the PREVIOUS burst fetched and
*   starts the next, so the poll read that RETURNS $FE has already started
*   the burst that fetches data byte 0.  ⛔ NOTHING may touch SDDATA between
*   that read and the first data read -- anything that does destroys byte 0
*   and shifts the whole block by one, from beginning to end, in silence.
*   The skip/take loops below read SDSTAT between bytes and SDDATA only when
*   they mean to, which is what keeps that true.
*
* ** BOUNDED, LIKE EVERY OTHER WAIT IN THIS ROM.  Nothing bounds a boot ROM
* on a real machine, so every poll here counts down and reports rather than
* spinning: a card that never answers is the question-mark picture and not a
* machine that stopped.
*
* ** THE BLOCK IS NOT BUFFERED.  There is nowhere to put 512 bytes: 10a runs
* with logical block 6 pointed at a ROM page (the toolbox's data), so the
* variables at $C000 and the stack at $E000 do not exist while this runs.
* The eight bytes the verdict needs are picked out of the stream as it goes
* by and the other 504 are read and dropped, which costs three loops and no
* memory at all.
*==============================================================================

* --- the byte level -------------------------------------------------------
* sdwait - poll SDSTAT until the burst engine is idle.  BOUNDED: a burst is
* 20.4 us at the init rate, 43 bus cycles, so 4096 tries is a hundred times
* the worst case.  ⚠ 6.3: SDSTAT b0 is "a burst is OWED or running" and not
* BUSY alone -- sdeng does not raise BUSY until the SPI clock's next falling
* edge, and a poll that could not see that window would walk through it into
* a mid-burst access.  Carry set = the engine never went idle.
sdwait  pshs    a,x
        ldx     #4096
sdw1    lda     SDSTAT
        bita    #SD_BUSY
        beq     sdw2
        leax    -1,x
        bne     sdw1
        puls    a,x
        orcc    #$01
        rts
sdw2    puls    a,x
        andcc   #$FE
        rts

* sdget - one byte in.  A = the byte.  The caller must have put $FF on DI.
sdget   bsr     sdwait
        bcs     sdg9
        lda     SDDATA
sdg9    rts

* sdput - send A.  A survives.
sdput   pshs    a
        bsr     sdwait
        bcs     sdp9
        lda     ,s
        sta     SDDATA
sdp9    puls    a,pc

* sdidle - DI high without consuming a burst: 6.2's SDMOSI.  This is 9.0
* step 1 and 9.1 step 3, and in both places its POSITION is the point.
sdidle  pshs    a
        lda     #$FF
        sta     SDMOSI
        puls    a,pc

* sdsel / sddes - assert and release /CS.  SDCTRL is write-only, so the last
* value written is shadowed in `sdctl`.  A release is followed by eight idle
* clocks, which SD wants after a deselect and which the card needs in order
* to let go of DO (9.1 step 8).
sdsel   pshs    a
        lda     sdctl
        ora     #SD_CS
        sta     sdctl
        sta     SDCTRL
        puls    a,pc

sddes   pshs    a
        lda     sdctl
        anda    #$FE
        sta     sdctl
        sta     SDCTRL
        bsr     sdidle
        bsr     sdget
        puls    a,pc

* sdarg0 - the frame's 32-bit argument, zeroed.
sdarg0  clr     sdfrm+1
        clr     sdfrm+2
        clr     sdfrm+3
        clr     sdfrm+4
        rts

* sdfrmb - A = the command byte, B = the CRC byte.
* ⚠ THE TWO CRCs ARE HARD-CODED CONSTANTS and there is no generator on this
* card (9.0).  SPI mode ignores the command CRC except for CMD0, which is
* issued before the card knows it is in SPI mode, and CMD8, whose CRC the
* specification makes mandatory.  $95 and $87 are correct for those two
* ARGUMENT VALUES and for no others; everything else ships $01.
sdfrmb  sta     sdfrm
        stb     sdfrm+5
        rts

* sdsend - the six bytes at sdfrm, then 9.1 step 4s poll for R1 into A.
* The poll is up to 16 reads for a byte that is not $FF: N_CR is at most 8
* byte times and the pipeline adds one.  ⛔ THE COUNTER IS IN B AND NOTHING
* CALLED FROM HERE TOUCHES B -- sdput and sdget report through the carry, not
* through B, which is the trap rbsd.asm records paying for.
sdsend  pshs    b,x
        ldx     #sdfrm
        ldb     #6
sdsn1   lda     ,x+
        bsr     sdput
        bcs     sdsn9
        decb
        bne     sdsn1
        bsr     sdidle
        ldb     #16
sdsn2   bsr     sdget
        bcs     sdsn9
        cmpa    #$FF
        bne     sdsn8
        decb
        bne     sdsn2
        orcc    #$01
        bra     sdsn9
sdsn8   andcc   #$FE
sdsn9   puls    b,x,pc

* sdskip - read X bytes and drop them.  X > 0.
sdskip  pshs    x
sdsk1   lbsr    sdget
        bcs     sdsk9
        leax    -1,x
        bne     sdsk1
        andcc   #$FE
sdsk9   puls    x,pc

* sdtake - read B bytes into ,Y+.  B = 1..255.
sdtake  lbsr    sdget
        bcs     sdtk9
        sta     ,y+
        decb
        bne     sdtake
        andcc   #$FE
sdtk9   rts

*------------------------------------------------------------------------------
* sdinit - 9.0, step for step.  Carry clear = an SDHC/SDXC card is up and the
* card is on the fast clock.  Carry set = there is nothing here to boot from.
*------------------------------------------------------------------------------
sdinit  clr     sdctl
        clr     SDCTRL          0. /CS high, init clock, no burst in flight
        lda     SDSTAT
        bita    #SD_CD
        lbeq    sdibad          nothing in the socket
        lbsr    sdidle          1. DI HIGH BEFORE ANY CLOCK EXISTS
        ldb     #10
sdin1   lbsr    sdget           step 2 -- eighty clocks, /CS high, DI high
        lbcs    sdibad
        decb
        bne     sdin1

* 3. CMD0 GO_IDLE_STATE, /CS LOW, argument 0, CRC $95.  Expect R1 = $01.
        ldb     #10
sdin2   pshs    b
        lbsr    sdsel
        lbsr    sdarg0
        lda     #$40
        ldb     #$95
        lbsr    sdfrmb
        lbsr    sdsend
        bcs     sdin3
        cmpa    #$01
        beq     sdin4
sdin3   lbsr    sddes
        puls    b
        decb
        bne     sdin2
        lbra    sdibad
sdin4   puls    b

* 4. CMD8 SEND_IF_COND, argument $000001AA, CRC $87.  R1 = $05 is "illegal
*    command", which means a v1.x card or an MMC -- 9.0.1 REFUSES those
*    rather than supporting them, and so does this.
        lbsr    sdarg0
        lda     #$01
        sta     sdfrm+3
        lda     #$AA
        sta     sdfrm+4
        lda     #$48
        ldb     #$87
        lbsr    sdfrmb
        lbsr    sdsend
        lbcs    sdifail
        cmpa    #$01
        lbne    sdifail
        lbsr    sdget           R7 bits 31 to 24, the command echo
        lbcs    sdifail
        lbsr    sdget           bits 23 to 16, reserved
        lbcs    sdifail
        lbsr    sdget           bits 15 to 8, the voltage nibble
        lbcs    sdifail
        sta     sdtmp
        lbsr    sdget           bits 7 to 0, the check pattern
        lbcs    sdifail
        tfr     a,b
        lda     sdtmp
        cmpd    #$01AA
        lbne    sdifail

* 5. CMD55 then ACMD41 with HCS set, until R1 = $00.  Bounded by attempts
*    rather than by a clock this ROM does not have running yet.
        ldx     #2000
sdin5   pshs    x
        lbsr    sdarg0
        lda     #$77            CMD55
        ldb     #$01
        lbsr    sdfrmb
        lbsr    sdsend
        bcs     sdin6
        lbsr    sdarg0
        lda     #$40            HCS -- this host takes SDHC
        sta     sdfrm+1
        lda     #$69            ACMD41
        ldb     #$01
        lbsr    sdfrmb
        lbsr    sdsend
        bcs     sdin6
        tsta
        beq     sdin7           out of idle
sdin6   puls    x
        leax    -1,x
        bne     sdin5
        lbra    sdifail
sdin7   puls    x

* 6. CMD58 READ_OCR, and CCS is bit 30 of the four OCR bytes.  CCS = 0 is an
*    SDSC card and is REFUSED (9.0.1): its commands take a byte address where
*    these take a block number, and a driver that gets that wrong does not
*    fail, it reads the wrong sector.
        lbsr    sdarg0
        lda     #$7A            CMD58
        ldb     #$01
        lbsr    sdfrmb
        lbsr    sdsend
        lbcs    sdifail
        tsta
        lbne    sdifail
        lbsr    sdget           OCR bits 31 to 24
        lbcs    sdifail
        bita    #$40            CCS
        lbeq    sdifail
        ldb     #3
sdin8   lbsr    sdget
        lbcs    sdifail
        decb
        bne     sdin8

* 7. CMD16 is NOT sent: an SDHC block is 512 and cannot be changed.
* 8. To the fast clock, with /CS high, no burst running and idle clocks
*    either side -- 3.3s rule, and a card in the middle of a command does not
*    care whose fault an extra edge was.
        lbsr    sddes
        lbsr    sdidle
        lbsr    sdget
        lda     sdctl
        ora     #SD_FAST
        sta     sdctl
        sta     SDCTRL
        lbsr    sdget
        andcc   #$FE
        rts

sdifail lbsr    sddes
sdibad  clr     sdctl
        clr     SDCTRL          back to the safe state
        orcc    #$01
        rts

*------------------------------------------------------------------------------
* sdblk0 - 9.1: CMD17 READ_SINGLE_BLOCK of block 0, keeping the eight bytes
* the verdict is made of and dropping the other 504.  Carry set on any error.
*
* The block is RBFs LSN 0 and LSN 1 (sdcard.md 9.5): LSN 0 is the volume
* header, whose DD.BT at +$15 names OS9Boots first sector, and LSN 1 is the
* allocation bitmap, which this reader has no use for.
*------------------------------------------------------------------------------
sdblk0  lbsr    sdsel
        lbsr    sdarg0
        lda     #$51            CMD17, argument = block 0
        ldb     #$01
        lbsr    sdfrmb
        lbsr    sdsend          steps 2-4; step 3s SDMOSI is inside sdsend
        bcs     sdb9
        tsta
        bne     sdb8            any R1 bit set is an error -- 9.3

* 5. poll for $FE.  $00-$1F is an ERROR TOKEN and not filler; anything that
*    is neither $FE nor $FF is a protocol error.  Either way this is not a
*    card to boot from, so both land on the same answer.
        ldx     #10000
sdb1    lbsr    sdget
        bcs     sdb9
        cmpa    #$FE
        beq     sdb2
        cmpa    #$FF
        bne     sdb8
        leax    -1,x
        bne     sdb1
        bra     sdb8

* 6. the 512 data bytes.  ⛔ NOTHING TOUCHED SDDATA BETWEEN THE READ ABOVE
*    THAT RETURNED $FE AND THE FIRST ONE HERE, which is what makes the first
*    byte taken below LSN 0 byte 0 and not byte 1.
sdb2    ldx     #21             LSN 0 bytes $00 to $14
        lbsr    sdskip
        bcs     sdb9
        ldy     #sdbt
        ldb     #3              DD.BT at LSN 0 byte $15
        lbsr    sdtake
        bcs     sdb9
        ldx     #216            LSN 0 bytes $18 to $EF
        lbsr    sdskip
        bcs     sdb9
        ldy     #sdsig
        ldb     #5              the signature at LSN 0 byte $F0
        lbsr    sdtake
        bcs     sdb9
        ldx     #267            what is left of LSN 0, and all of LSN 1
        lbsr    sdskip
        bcs     sdb9

* 7. the two CRC16 bytes: read for the clocks, not for the value (9.1).
* 8. /CS high and eight idle clocks, which sddes does.
        lbsr    sdget
        lbsr    sdget
        lbsr    sddes
        andcc   #$FE
        rts
sdb8    orcc    #$01
sdb9    pshs    cc
        lbsr    sddes
        puls    cc
        rts

*------------------------------------------------------------------------------
* sdprobe - the whole question, in one call.  Carry CLEAR means: an SDHC or
* SDXC card came up (CMD58 said CCS), block 0 read, and LSN 0 carries this
* machines boot signature over a non-zero DD.BT.  Carry set means everything
* else, and the card is left in the safe state either way.
*
* ⭐ sdcard.md 9.5 is where the signature is defined and software/nitros9/
* mksddisk.sh is what writes it.  The four bytes are "6309" -- the SAME four
* this ROM looks for at $8000 when it hands the machine to ROM page 1
* (section 11), because one machine should have one signature and not two.
*------------------------------------------------------------------------------
sdprobe lbsr    sdinit
        bcs     sdpbad
        lbsr    sdblk0
        bcs     sdpbad
        ldd     sdsig
        cmpd    #$3633          "63"
        bne     sdpbad
        ldd     sdsig+2
        cmpd    #$3039          "09"
        bne     sdpbad
        lda     sdsig+4
        cmpa    #$01            the version of the convention, 9.5
        bne     sdpbad
* DD.BT = 0 is a volume that was formatted and never blessed: there is a
* filesystem on the card and no OS9Boot in it.  That is the question mark.
        lda     sdbt
        ora     sdbt+1
        ora     sdbt+2
        beq     sdpbad
        clr     sdctl
        clr     SDCTRL
        andcc   #$FE
        rts
sdpbad  clr     sdctl
        clr     SDCTRL
        orcc    #$01
        rts

*==============================================================================
* tbcall - B = a toolbox function, X = a parameter block: a COUNT byte and then
* the bytes themselves, big-endian words, exactly as a CoWin escape carries
* them.  The count is what PN answers, which is how tbox finds a call's string.
*
* ⚠ Y IS THE VG.  tbox.asm's header: "Y = VG, which every path here keeps" --
* it never reads the structure itself, but everything it calls back into does,
* and the row layer below reaches the card through VG.Base.
*==============================================================================
tbcall  pshs    x
        lda     ,x+
        sta     tbpcnt
        ldy     #vgstub
        jsr     TBENT
        bcs     tbcbad
        puls    x,pc
* ⛔ AND AN ERROR IS REPORTED, NOT IGNORED.  A dialog that half drew itself is
* a machine that looks broken in a way nobody can name; $E6 names it.  The map
* and the stack still have to be put back, so it goes out through dlgend.
tbcbad  lda     #P_BADTB
        sta     SIMPORT
        leas    2,s             tbcall's own saved X
        jmp     dlgend

*==============================================================================
* The row layer the toolbox draws through -- ca_tbox.asm's TbVec, for a machine
* with no CoArm in it.  tbox reaches five of these nine (TV.Rect, TV.Put,
* TV.MapB, TV.PalSet, TV.PalShw); the rest are the table's shape.
*
* ⛔⛔ THE TABLE MUST BE AS LONG AS tbox's TV.* LIST, AND NOTHING CHECKS IT.
* TVCALL is `jsr [CG.TbV + TV.<name>]` -- an ENTRY NUMBER indexed into whatever
* is at CG.TbV -- so a vector tbox has and this table does not is a jump into
* the bytes that happen to follow.  It cost a boot: the glyph strike (2026-09-22)
* gave tbox TV.CopyN at offset 24, this table ended at 18, and `SkFlush` jumped
* to tbvec+24 -- the MIDDLE of tbmapb's `cmpd`.  The dialog's question mark then
* executed four bytes of an operand, RTS'd into VRAM, and the machine ran wild
* two seconds into every no-disk boot; the "Disk found" path never flushed a
* batch and was perfect, so the defect was invisible on the card that works.
* ⚠ A new TV.* entry in tbox.asm is a new entry HERE, on the same day.
*
* ⚠ EVERY REGISTER PASSES THROUGH BOTH WAYS.  TVCALL does not save anything,
* and its callers rely on that: TPal keeps the entry number in B and the
* directory pointer in X ACROSS the palette write, and every path in tbox keeps
* Y.  So each entry below preserves all of them.
*==============================================================================
tbvec   lbra    tbrow           0  TV.Fill    A = a colour: CG.RN at (RY, RX)
        lbra    tbput           3  TV.Put     X = CG.RN bytes to put there
        lbra    tbmapb          6  TV.MapB    D = a block at Co.WinB
        lbra    tbrect          9  TV.Rect    A = a colour: CG.RN x CG.FH
        lbra    tbpset          12 TV.PalSet  B = an entry, CG.Tmp = RGB565
        lbra    tbpshw          15 TV.PalShw  (nothing: see below)
        lbra    tbdisp          18 TV.IsDisp  (nothing: see below)
        lbra    tbnocp          21 TV.Copy    ⛔ refused: there is no engine here
        lbra    tbnocp          24 TV.CopyN   ⛔ and no list of them either

*------------------------------------------------------------------------------
* tbmapb - D = a block, at Co.WinB.  ca_row.asm's MapA is the rule this
* follows: the low byte of the block is the map's low byte, and the high byte
* plus RAM.Hi is its high byte -- so $FF00+page, which is what DMap passes, is
* map high $01, the boot ROM.
*------------------------------------------------------------------------------
tbmapb  pshs    cc,a,b
        cmpd    COG+CG_WINB
        beq     tbmb1
        std     COG+CG_WINB
        orcc    #$50
        stb     MAPLO+6
        adda    #$02            $FF + RAM.Hi = $01 = ROM.Hi
        sta     MAPHI+6
tbmb1   puls    cc,a,b,pc

*------------------------------------------------------------------------------
* tbaddr - WPTR := the card address of (CG.RY, CG.RX).  U = the card's base.
* ca_row.asm's CardAddr: the ring row (CG.TTop + RY) in bits 18-10 and the
* column in bits 9-0, which on this card is row * 1024 + column (plan 2.5).
*------------------------------------------------------------------------------
tbaddr  pshs    a,b
        ldd     COG+CG_RX
        stb     R_WPTR0,u       A7..A0 -- the column's low byte
        pshs    a               ... and A9..A8, to go under the row
        ldd     COG+CG_TTOP
        addd    COG+CG_RY
        anda    #$01            the ring is 512 rows
        lslb
        rola
        lslb
        rola                    A = row >> 6, B = (row & $3F) << 2
        orb     ,s+
        stb     R_WPTR1,u
        sta     R_WPTR2,u
        puls    a,b,pc

*------------------------------------------------------------------------------
* tbrow - A = a colour: CG.RN pixels from (CG.RY, CG.RX), span-solid.
* ⚠ IN CHUNKS OF 256, because SPANLEN is one byte, and with a bounded
* SPANBUSY poll before each: plan 5 says no register may be written under a
* span, and 640 pixels is three spans.
*------------------------------------------------------------------------------
tbrow   pshs    cc,a,b,x,u
        ldd     COG+CG_RN
        lbeq    tbrw9
* ⛔ NO COMMA IN A COMMENT ON A pshs/puls LINE.  A09 has no comment delimiter
* and keeps parsing the register list across the whitespace, so
* `pshs d    ,s = pixels left` assembled as PSHS A,B,U -- four bytes where two
* were meant, every stack offset below it off by two, and the row layer drew
* with TB.Opq as its colour and then returned into the weeds.  It cost a day.
* The stack here is: 0,1 pixels left / 2 CC / 3 the colour / 4 B / 5,6 X / 7,8 U
        pshs    a,b
        ldu     VGBASE,y
        lbsr    idlespn
        lda     tbctl
        ora     #CT_SOL
        sta     R_CTRL,u
        clra
        sta     R_WADV,u        00: continue, and no step-by-two
        lda     3,s
        sta     R_WFG,u
        lbsr    tbaddr
tbrw1   ldd     ,s
        beq     tbrw8
        cmpd    #256
        bls     tbrw2
        ldd     #256
tbrw2   stb     tbchunk         256 comes out as 0, which is what SPANLEN wants
        pshs    a,b
        ldd     2,s
        subd    ,s++
        std     ,s
        lbsr    idlespn
        ldb     tbchunk
        decb                    the span's length - 1
        stb     R_SPLEN,u
        stb     R_VDATA,u       the trigger: any byte
        bra     tbrw1
tbrw8   lbsr    idlespn
        leas    2,s
tbrw9   puls    cc,a,b,x,u,pc

*------------------------------------------------------------------------------
* tbrect - A = a colour: CG.RN x CG.FH pixels from (CG.RX, CG.RY).  ca_scr.asm's
* FillRect, which is one tbrow a row with CG.RY put back at the end.
*------------------------------------------------------------------------------
tbrect  pshs    cc,a,b,x,u
        ldd     COG+CG_RY
        pshs    a,b             (0,1 the row to restore; 3 the colour - and
*                                see tbrow for why that comment has no comma)
        ldx     COG+CG_FH
        beq     tbrc9
tbrc1   lda     3,s
        lbsr    tbrow
        ldd     COG+CG_RY
        addd    #1
        std     COG+CG_RY
        leax    -1,x
        bne     tbrc1
tbrc9   puls    a,b
        std     COG+CG_RY
        puls    cc,a,b,x,u,pc

*------------------------------------------------------------------------------
* tbput - X = CG.RN bytes, at (CG.RY, CG.RX), WMODE 00 direct.
* ⚠ NO POLL BETWEEN THE BYTES, and section 10 (f) is why: a direct VDATA store
* is posted and the card's /WAIT holds the CPU off exactly as long as it needs.
*------------------------------------------------------------------------------
tbput   pshs    cc,a,b,x,u
        ldd     COG+CG_RN
        beq     tbpt9
        ldu     VGBASE,y
        lbsr    idlespn
        lda     tbctl
        sta     R_CTRL,u        WMODE 00 -- direct
        clra
        sta     R_WADV,u
        lbsr    tbaddr
        ldd     COG+CG_RN
        pshs    a,b
tbpt1   lda     ,x+
        sta     R_VDATA,u       VRAM at WPTR, post-increment
        ldd     ,s
        subd    #1
        std     ,s
        bne     tbpt1
        leas    2,s
tbpt9   puls    cc,a,b,x,u,pc

*------------------------------------------------------------------------------
* tbpset - B = a palette entry, CG.Tmp = its RGB565.  Sub-palette 0, which is
* what bitmap mode looks up (plan 2.4).
* ⚠ B IS THE ENTRY AND vwait0 TAKES ITS MASK IN B, so the entry is read off the
* stack and the poll is left to have B to itself.
*------------------------------------------------------------------------------
tbpset  pshs    cc,a,b,u
        ldu     VGBASE,y
        lbsr    idlespn
        ldb     2,s             the entry
        stb     R_PIDXL,u
        clrb
        stb     R_PIDXH,u
        ldd     COG+CG_TMP      RGB565, high byte first
        stb     R_PDATL,u       GGGBBBBB
        sta     R_PDATH,u       RRRRRGGG -- and this posts the commit
        ldb     #$02
        lbsr    vwait0          PBUSY, bounded
        puls    cc,a,b,u,pc

*------------------------------------------------------------------------------
* tbpshw - CoArm's is "the screen's 256 entries onto the card, if it is
* displayed".  There is one screen here and tbpset wrote the card's LUT
* directly, so there is nothing left to show.
* tbdisp - "Z set if this screen is displayed".  It is; and no path the toolbox
* takes calls this at all -- the entry exists so the table is TbVec's shape.
*------------------------------------------------------------------------------
tbpshw  rts
tbdisp  orcc    #$04            Z: the screen is displayed
        rts
* ⭐ THE COPY ENGINE, REFUSED -- and refusing is a documented answer, not a
* stub.  tbox.asm's TV.Copy says "carry set if it could not" and TV.CopyN says
* "carry back means COMPOSE THE WHOLE STRING", so a row layer that cannot copy
* says so and the caller draws the glyphs the long way.  That is what the boot
* dialog did before the strike existed, and it is ~30 characters once.
* ⚠ THE CARRY IS THE WHOLE CONTRACT: a `rts` with carry CLEAR claims the
* rectangle was copied and leaves the text unwritten.
tbnocp  orcc    #$01            C: this machine's row layer cannot
        rts

*==============================================================================
* The dialog's parameter blocks.  A count byte, then the call's own parameters
* -- big-endian words, as tbox.asm's header lists them.
*==============================================================================
ppal    FCB     0               7 Pal - no parameters

pclear  FCB     9               5 Rect X Y W H COLOUR: the whole screen
        FDB     0
        FDB     0
        FDB     640
        FDB     DLGSCRH
        FCB     C_DESK

pwin    FCB     16              4 Window X Y W H FLAGS title (9 + 7)
        FDB     WINX
        FDB     WINY
        FDB     WINW
        FDB     WINH
        FCB     $01             b0: the active tab
        FCC     "arm6309"

pcont   FCB     9               the content area, panel grey
        FDB     CONX
        FDB     CONY
        FDB     CONW
        FDB     CONH
        FCB     C_PANEL

picbox  FCB     9               ... and just the icon's box, for the blink
        FDB     ICONX
        FDB     ICONY
        FDB     ICONS
        FDB     ICONS
        FCB     C_PANEL

picon   FCB     6               2 Icon N X Y SEL
        FCB     1               `disk` -- mktbox.py's ICON_NAMES, entry 1
        FDB     ICONX
        FDB     ICONY
        FCB     0               not the dark variant

ptlook  FCB     26              1 TextC X W Y RAMP FONT string (8 + 18)
        FDB     TXTX
        FDB     TXTW
        FDB     TXTY
        FCB     R_PANEL
        FCB     F_REG
        FCC     "Looking for a disk"

ptfound FCB     18              (8 + 10)
        FDB     TXTX
        FDB     TXTW
        FDB     TXTY
        FCB     R_PANEL
        FCB     F_REG
        FCC     "Disk found"

ptnone  FCB     15              (8 + 7)
        FDB     TXTX
        FDB     TXTW
        FDB     TXTY
        FCB     R_PANEL
        FCB     F_REG
        FCC     "No disk"

pquest  FCB     9               the question mark, centred on the icon (8 + 1)
        FDB     ICONX
        FDB     ICONS
        FDB     ICONY+8
        FCB     R_WHITE
        FCB     F_BOLD+F_OPAQ
        FCC     "?"

* ⭐ THE FABRICATED VG.  tbox keeps Y across everything it does because the row
* layer under it reads the video globals through it; CoArm's VG is kilobytes of
* driver state, and the only field anything on these paths reads is VG.Base.
* So this is that field and the padding in front of it, in ROM -- nothing here
* ever writes to a VG.
vgstub  FCB     0,0,0,0,0,0,0,0
        FCB     0,0,0,0,0,0,0,0
        FDB     VBASE           VGBASE ($10): the card

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
* 10a's variables, and its stack, are in BLOCK 0 and not block 6.
*
* ⛔ BECAUSE BLOCK 6 IS WHERE THE TOOLBOX'S DATA GOES.  Co.WinB is $C000, so
* for the length of the dialog logical $C000-$DFFF is a ROM page and neither
* the variables above nor a stack descending from $E000 exists.  Block 0 is
* the same SIMM, is mapped throughout, and holds nothing but the memory
* descriptor at $0000-$0002 (1a).
*
* ⚠ These are all under $100 and DP is 0 out of reset and never written, so
* they assemble direct-page - which is what makes the row layer below cheap
* enough to fill 128,000 pixels with.
*==============================================================================
DSTK    EQU     $2000           the dialog's stack: block 0, descending
dstksv  EQU     $0010           where S was, two bytes
tbctl   EQU     $0012           CTRL as the row layer is to write it, WMODE 00
tbchunk EQU     $0013           tbrow: this span's length, 256 as 0
nblink  EQU     $0014           the question mark's blinks left
nblnkf  EQU     $0015           ... and the blanks left in a phase
simmhi  EQU     $0016           the SIMM's map high byte, before MapB ate it
* ⭐ THE FABRICATED WINDOW.  tbox's PN answers `WT.Parms+1` off CG.Dev, and
* that byte - the call's parameter COUNT - is the only field of a CoWin window
* record anything on these paths reads.  So the record is one byte, at the
* offset a real one would have it.
tbdev   EQU     $0020
tbpcnt  EQU     tbdev+WT_PCNT
* ⭐ 10b's, and they are here for the same reason 10a's are: while the dialog
* is up, logical block 6 is a ROM page and $C000-$DFFF is not memory.  The
* reader keeps no block buffer at all (see 10b), so this is all of it.
sdctl   EQU     $0050           the last SDCTRL written -- it is write-only
sdfrm   EQU     $0051           the six-byte command frame
sdtmp   EQU     $0057           one byte: CMD8 R7 half, across a call
sdbt    EQU     $0058           LSN 0 +$15 -- DD.BT, OS9Boot first sector
sdsig   EQU     $005B           LSN 0 +$F0 -- "6309" and a version byte

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
