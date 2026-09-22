* tfm.asm - exercise all four TFM forms against RAM and against a PORT.
*
* ⭐ THE POINT OF THIS PROGRAM IS TO BE RUN TWICE: once with interrupts quiet
* and once with the runner asserting /IRQ throughout. cpu/docs/plan.md §4.3.1
* says the two runs must produce IDENTICAL memory and an identical port log -
* no byte re-read, none written twice - and that is the whole of the divergence
* this project chose. On a real HD63C09E the second run would lose bytes on the
* fixed-source form.
*
* The runner models $FF00 as a side-effecting port: every READ pops the next
* byte of an incrementing sequence, every WRITE appends to a log. That is
* sdcard.md §3.1's SDDATA in miniature, which is what makes the test relevant.

N           equ       32

SRC         equ       $0100             source pattern, N bytes
DST1        equ       $0200             form 1 destination
DST2        equ       $0300             form 4 destination (from the port)
DST3        equ       $0380             form 2 destination
RES         equ       $0400             results: three W values, then a done flag
PORT        equ       $FF00
DONE        equ       $0500             a write here ends the run
ACK         equ       $0501             a write here drops the device's /IRQ

            org       $1000

start       lds       #$0FF0
            andcc     #$AF              interrupts ON - the runner decides

* ---- fill SRC with a known pattern ------------------------------------
            ldx       #SRC
            clra
fill        sta       ,x+
            inca
            cmpa      #N
            bne       fill

* ---- form 1: TFM r+,r+  RAM -> RAM ------------------------------------
            ldx       #SRC
            ldy       #DST1
            ldw       #N
            tfm       x+,y+
            stw       RES+0             must be 0

* ---- form 4: TFM r,r+   PORT -> RAM -----------------------------------
* The fixed source is the port. This is the form the book says loses a byte
* on a real 6309 unless interrupts are masked. Nothing is masked here.
            ldx       #PORT
            ldy       #DST2
            ldw       #N
            tfm       x,y+
            stw       RES+2             must be 0

* ---- form 3: TFM r+,r   RAM -> PORT -----------------------------------
* The fixed destination is the port. The book is silent on this form; the
* runner's log says whether any byte went out twice.
            ldx       #SRC
            ldy       #PORT
            ldw       #N
            tfm       x+,y
            stw       RES+4             must be 0

* ---- form 2: TFM r-,r-  backward --------------------------------------
            ldx       #SRC+N-1
            ldy       #DST3+N-1
            ldw       #N
            tfm       x-,y-
            stw       RES+6             must be 0

* ---- a few of the other new instructions ------------------------------
            ldq       #$12345678
            stq       RES+8             D=$1234 W=$5678

            ldw       #$00FF
            addw      #$0001
            stw       RES+12            $0100

            ldx       #$1000
            ldy       #$0234
            addr      x,y
            sty       RES+14            $1234

            lda       #$FF
            ldb       #$00
            ldw       #$8000
            sexw
            std       RES+16            $FFFF, W's sign

            ldw       #N
            stw       RES+18            W survives

            clra
            sta       DONE              end the run
            bra       *

            org       $FFF8
            fdb       irq               IRQ
            fdb       irq               FIRQ
            fdb       irq               NMI (unused)
            fdb       start             RESET

            org       $0F00
irq         sta       ACK               acknowledge, exactly as a device wants
            rti
