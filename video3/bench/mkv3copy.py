#!/usr/bin/env python3
"""Write video3/bench/v3copy.asm and v3copy.json - the copy-engine exerciser.

video3/docs/plan.md §6.  Bitmap mode makes VRAM observable: one byte is one
palette index is one pixel, so a copy that lands a byte in the wrong place is a
pixel in the wrong place.  The model applies the same copies to a numpy array
and renders; it shares the COPY LIST with the ROM and nothing else.
"""
import json, sys

W, H = 640, 200                     # the visible window at VMODE 00

# ⭐ THE KEYED SHAPE (keyed-copy.md): 16 x 16 in off-screen rows, whose
# HOLES are index 0 and whose ink never is.  A copy made in WMODE 11 does not
# write a source byte of zero, so the ink lands and the background stands.
SHR, SHC, SHW, SHH = 260, 0, 16, 16


def shape_rows():
    """The ink is 1 + ((r * 16 + c) mod 255), so it is never the key by
    accident; the holes are a block and two diagonals, so a card that
    dropped the wrong byte of a group shows as a shifted hole."""
    out = []
    for r in range(SHH):
        row = []
        for c in range(SHW):
            hole = (4 <= r <= 11 and 4 <= c <= 11) or r == c or r + c == SHW - 1
            row.append(0 if hole else 1 + ((r * 16 + c) % 255))
        out.append(row)
    return out


SHAPE = shape_rows()


def shape_fcb():
    return "".join("\n        FCB     " + ",".join("$%02X" % v for v in r)
                   for r in SHAPE)


# (label, src_row, src_col, dst_row, dst_col, w, h, rowdir, coldir, key)
#   ⛔ rowdir/coldir are ALWAYS 0.  v3ptr's fit priced the up/down counters at
#   18 macrocells and 16 cascades - the difference between 128/128 and 110/128 -
#   so the engine counts UP only and an overlapping copy stages through scratch
#   in two passes, which plan 6.2 always offered as the fallback.  The tuple
#   keeps its two fields so the model can ASSERT they are zero.
COPIES = [
    ("vertical only, non-overlapping",        0,   0, 100,   0,  64, 16, 0, 0, 0),
    ("horizontal, columns congruent mod 4",  20,   0,  28,  64,  32,  8, 0, 0, 0),
    ("horizontal, NOT congruent mod 4",      40,   1,  48,  66,  33,  8, 0, 0, 0),
    ("overlapping scroll UP, rows ascend",   60,   0,  52,   0, 128, 32, 0, 0, 0),
    # ⭐ the card has NO direction bits (plan 6.2, settled by v3ptr's fit), so an
    # overlapping DOWNWARD scroll is two ascending passes through scratch - and
    # the result must equal what a descending copy would have produced.
    ("scroll DOWN, pass 1: to scratch",      120,  0, 300,   0, 128, 32, 0, 0, 0),
    ("scroll DOWN, pass 2: back, 8 lower",   300,  0, 128,   0, 128, 32, 0, 0, 0),
    ("shift RIGHT, pass 1: to scratch",      160,  0, 320,   0,  64,  8, 0, 0, 0),
    ("shift RIGHT, pass 2: back, 8 right",   320,  0, 160,   8,  64,  8, 0, 0, 0),
    ("overlapping LEFT, columns ascend",    180,   8, 180,   0,  64,  8, 0, 0, 0),
    ("one row, one byte",                    99, 639,  98, 320,   1,  1, 0, 0, 0),
    # ⭐ THE COLOUR KEY.  Four cases, and each fails a different way of
    # getting it wrong.  The destinations are inside the pattern, so the
    # background under the holes is NOT zero and a card that wrote the key
    # bytes anyway paints them black.
    ("KEYED: the shape over the pattern",   SHR, SHC, 140, 200, SHW, SHH, 0, 0, 1),
    ("the SAME shape, NOT keyed",           SHR, SHC, 140, 240, SHW, SHH, 0, 0, 0),
    # ⚠ column 401 is 1 mod 4: the key drops ONE lane's byte enable, so a
    # keyed write on the wrong lane shows here and not at column 0.
    ("KEYED at column 401, 1 mod 4",        SHR, SHC, 178, 401, SHW, SHH, 0, 0, 1),
    # ⭐ a source that is the PATTERN, where (r * 7 + c * 3) is zero at
    # exactly one pixel of the sixteen square: the key must take that one
    # and nothing else.
    ("KEYED from the pattern: one hole",      0,   0, 170, 300, SHW, SHH, 0, 0, 1),
]
assert all(len(c) == 10 for c in COPIES)

json.dump({"w": W, "h": H, "copies": COPIES,
           "shape": {"row": SHR, "col": SHC, "rows": SHAPE}},
          open(sys.argv[2], "w"))

def emit(i, c):
    _, sr, sc, dr, dc, w, h, rd, cd, key = c
    src = (sr << 10) | sc
    dst = (dr << 10) | dc
    ctrl = 1 | (rd << 1) | (cd << 2) | ((w >> 8 & 3) << 3) | ((h >> 8 & 1) << 5)
    # ⭐ WMODE 11 ARMS THE KEY, and nothing else does: in any other WMODE
    # the same copy moves index 0 like any other byte.  CTRL goes back to 00
    # afterwards, so a card that latched the mode fails the next plain copy.
    arm = ("        lda     #$30            WMODE 11 arms the key\n"
           "        sta     <VCTRL\n") if key else ""
    dis = "        clr     <VCTRL          and the key is off again\n" if key else ""
    return arm + f"""* {c[0]}
        lda     #${src >> 16 & 7:02X}
        sta     <CPTR2
        lda     #${src >> 8 & 0xFF:02X}
        sta     <CPTR1
        lda     #${src & 0xFF:02X}
        sta     <CPTR0
        lda     #${dst >> 16 & 7:02X}
        sta     <WPTR2
        lda     #${dst >> 8 & 0xFF:02X}
        sta     <WPTR1
        lda     #${dst & 0xFF:02X}
        sta     <WPTR0
        lda     #${w & 0xFF:02X}
        sta     <CWIDTH
        lda     #${h & 0xFF:02X}
        sta     <CHEIGHT
        lda     #${ctrl:02X}
        sta     <CCTRL          GO
cw{i:02d}    lda     <VSTAT
        bmi     cw{i:02d}
""" + dis

src = f"""*******************************************************************************
* v3copy.asm -- video3's copy engine on the host emulator.  GENERATED by
* bench/mkv3copy.py; edit the generator.
*
*   sh video3/bench/run-v3copy.sh
*
* plan 6.  Bitmap mode makes VRAM observable: a byte IS a palette index IS a
* pixel, so a copy that puts a byte in the wrong place is visible.  The list
* covers aligned and unaligned columns, both directions in both axes, and four
* overlapping copies - which is where a direction bit that walks the wrong way
* destroys its own source.
*******************************************************************************

VCTRL   EQU     $FF60
VSCROLL EQU     $FF61
WPTR0   EQU     $FF68
WPTR1   EQU     $FF69
WPTR2   EQU     $FF6A
WADV    EQU     $FF6B
VDATA   EQU     $FF6C
VSTAT   EQU     $FF6D
PIDXL   EQU     $FF6E
PIDXH   EQU     $FF6F
PDATL   EQU     $FF70
PDATH   EQU     $FF71
CPTR0   EQU     $FF72
CPTR1   EQU     $FF73
CPTR2   EQU     $FF74
CWIDTH  EQU     $FF75
CHEIGHT EQU     $FF76
CCTRL   EQU     $FF77
SIMPORT EQU     $FF2F

row     EQU     $C100
seed    EQU     $C102

        ORG     $8000
        FCC     "6309"
        JMP     start

        SETDP   $FF
start   orcc    #$50
        lds     #$E000
        lda     #$FF
        tfr     a,dp
        clr     <VCTRL          display off, bitmap, WMODE 00
        clr     <WADV
        clr     <VSCROLL
        clr     <VSCROLL+1

* --- sub-palette 0: entry i = i * $0101, so a pixel's value is recoverable
        clr     <PIDXH
        clr     <PIDXL
        clrb
pal1    stb     <PDATL
        stb     <PDATH
        incb
        bne     pal1

* --- the pattern: VRAM[r][c] = (r * 7 + c * 3) & $FF
        clr     row
        clr     row+1
fr1     ldd     row
        lslb
        rola
        lslb
        rola                    D = row * 4 -> WPTR1:WPTR0 is row * 1024
        clr     <WPTR0
        stb     <WPTR1
        sta     <WPTR2          WPTR = row * 1024, so the row starts at WPTR1
        ldb     row+1
        lda     #7
        mul                     B = row * 7, low byte
        stb     seed
        ldy     #{W}
fc1     lda     seed
        sta     <VDATA
        adda    #3
        sta     seed
        leay    -1,y
        bne     fc1
        ldd     row
        addd    #1
        std     row
        cmpd    #{H}
        blo     fr1

* --- the keyed shape into off-screen rows: its holes are index 0
        ldx     #shape
        ldd     #{SHR}
        std     row
shr1    ldd     row
        lslb
        rola
        lslb
        rola
        anda    #7
        sta     <WPTR2
        stb     <WPTR1
        lda     #${SHC & 0xFF:02X}
        sta     <WPTR0
        ldb     #{SHW}
shc1    lda     ,x+
        sta     <VDATA
        decb
        bne     shc1
        ldd     row
        addd    #1
        std     row
        cmpd    #{SHR + SHH}
        blo     shr1

* --- the copies
{"".join(emit(i, c) for i, c in enumerate(COPIES))}
* --- bitmap mode, 640x200, display on
        lda     #$80            b7 display, MODE 00 bitmap, VMODE 00
        sta     <VCTRL
        lda     #$A0
        sta     SIMPORT
done    bra     done

* the shape, row by row: 0 is the key and the ink never is
shape{shape_fcb()}
        END
"""
open(sys.argv[1], "w").write(src)
print(f"wrote {sys.argv[1]} and {sys.argv[2]} ({len(COPIES)} copies)")
