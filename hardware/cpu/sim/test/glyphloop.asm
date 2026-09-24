* glyphloop.asm - what a strike glyph costs the CPU, three ways.
*
* software/toolbox/docs/proportional-font.md §5.3 estimates the 6809 blit loop at 56 E cycles a
* glyph and §5.4 estimates a 6309 STQ form at ~30. Both were read off the source.
* This runs them and counts, so the document can stop estimating.
*
* ⚠ THE REGISTERS HERE ARE PLAIN RAM, not a card. The point is the CPU's own
* cost - the loads, the stores and the loop - which is what §5.3 and §5.4 count.
* /WAIT and the engine are §6's business and are not modelled.
*
* ⛔ AND THE 6309 FORM ASSUMES §5.4's RE-ORDERED MAP. On the real card WPTR is
* at +$08 and CPTR at +$12, ten bytes apart, so STQ can reach neither pair of
* pairs. What is measured is the instruction sequence a contiguous map would
* allow, which is exactly the thing §5.4 asks the re-order to buy.

GLYPHS      equ       40                one 40-character line
TAB         equ       $0200             the per-string record list
DONE        equ       $0500
MARK        equ       $0502             a write here timestamps

* the card window, laid out as §5.4 would
CPW         equ       $0600             CPTR0,CPTR1,WPTR0,WPTR1
CW          equ       $0604             CWIDTH
CH          equ       $0605             CHEIGHT
CCTRL       equ       $0606

* and as it is today: WPTR at +$08, CPTR at +$12 of a 32-byte window
WIN         equ       $0620
WPTR0       equ       $08
WPTR1       equ       $09
CPTR0       equ       $12
CPTR1       equ       $13
CWIDTH      equ       $15
CHEIGHT     equ       $16
CCTRLO      equ       $17

            org       $1000

start       lds       #$0FF0

* ---- build a plausible record list: 5 bytes a glyph ---------------------
            ldx       #TAB
            ldb       #GLYPHS
bld         lda       #$7C              CPTR hi
            sta       ,x+
            lda       #$40              CPTR lo
            sta       ,x+
            lda       #$08              WPTR hi
            sta       ,x+
            lda       #$20              WPTR lo
            sta       ,x+
            lda       #7                width
            sta       ,x+
            decb
            bne       bld

* ======== 1. the 6809 loop, §5.3, against today's map ====================
            lda       #1
            sta       MARK
            ldy       #TAB
            ldx       #GLYPHS
            ldu       #WIN
l6809       ldd       ,y++              CPTR pair, pre-swapped
            std       CPTR0,u
            ldd       ,y++              WPTR pair, pre-swapped
            std       WPTR0,u
            lda       ,y+               this glyph's width
            sta       CWIDTH,u
            ldd       #(17*256)+1       CHEIGHT, and CCTRL with GO
            sta       CHEIGHT,u
            stb       CCTRLO,u
            leax      -1,x
            bne       l6809
            lda       #2
            sta       MARK

* ======== 2. the same loop with 6309 wide stores, today's map ============
* STQ cannot reach both pointer pairs on this map, so the best it does is
* STW for each pair and STW for CWIDTH:CHEIGHT.
            lda       #3
            sta       MARK
            ldy       #TAB
            ldx       #GLYPHS
            ldu       #WIN
l6309a      ldw       ,y++
            stw       CPTR0,u
            ldw       ,y++
            stw       WPTR0,u
            lda       ,y+
            sta       CWIDTH,u
            ldd       #(17*256)+1
            sta       CHEIGHT,u
            stb       CCTRLO,u
            leax      -1,x
            bne       l6309a
            lda       #4
            sta       MARK

* ======== 3. §5.4's re-ordered map, STQ + STW + STA ======================
            lda       #5
            sta       MARK
            ldy       #TAB
            ldx       #GLYPHS
            ldu       #CPW
l6309b      ldq       ,y                both pointer pairs, 4 bytes
            stq       ,u                FOUR register bytes, one instruction
            leay      4,y
            ldb       ,y+               width
            stb       CW-CPW,u
            lda       #17
            sta       CH-CPW,u
            lda       #1
            sta       CCTRL-CPW,u
            leax      -1,x
            bne       l6309b
            lda       #6
            sta       MARK

            clra
            sta       DONE
            bra       *

            org       $FFF8
            fdb       stop              IRQ
            fdb       stop              SWI
            fdb       stop              NMI
            fdb       start             RESET

            org       $0F00
stop        rti
