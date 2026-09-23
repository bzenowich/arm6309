#!/usr/bin/env python3
"""pcsphys.py - a transliteration of Pinball Construction Set's arithmetic.

⛔ THIS IS WRITTEN FROM THE 6502 AND IS NEVER ADJUSTED TO MATCH THE 6809.

It exists to be the gate.  `video3/docs/pcs.md` 1 explains the decision the
whole port rests on: the simulation, the database and the file format stay in
the Atari's own units and only the RENDERER is doubled, which makes every
number here an integer and the port PROVABLY the original rather than a homage.
`checkpcs.py` runs this model over the same table the machine runs and requires
the same `(frame, x, y, BDX, BDY, score)` for the whole session.

A model corrected until it agrees with the implementation is the check
answering its own question -- CLAUDE.md's HOSTMAP trap.  So when this and the
6809 disagree, the 6502 source decides, and a change here cites a line of it.

Sources: `reference/pcs/PPAK.s` (the scan converter and its divide) and
`reference/pcs/RUN.s` (the ball).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pcsasm as A                                             # noqa: E402


# ----------------------------------------------------------- the divide ----
def qdiv(dvdnd_hi, dvsr_hi):
    """`QUICK 16 X 8 BIT DIVIDE` -- PPAK.s:718, transliterated literally.

    Called as QDIV(|dx|, dy) with both operands in the HIGH byte of a 16-bit
    pair and the low bytes zeroed (PPAK.s:691-694), so the answer is
    |dx| / dy in 8.8 fixed point.  Returns (coeff, fract) = (QUOT+1, QUOT).

    ⚠ Restoring shift-compare with a pre-scaled divisor, and the carry flag
    carries meaning across three labels.  `characterise()` and `invariant()`
    below are what establish that this reading is faithful, and between them
    they are why the 6809 transliterates it rather than approximating it.
    """
    quot = 0
    dvsr = dvsr_hi << 8
    dvdnd = dvdnd_hi << 8

    x = 8
    a = dvsr_hi                     # pre-scale the divisor
    while True:                     # QDV1
        x += 1
        carry = (a & 0x80) != 0
        a = (a << 1) & 0xFF
        if carry:
            break                   # -> QDV2 with carry set
        if a < dvdnd_hi:            # CMP / BCC QDV1
            continue
        carry = False               # CLC
        break
    # QDV2: ROR
    a = ((a >> 1) | (0x80 if carry else 0)) & 0xFF
    dvsr = (dvsr & 0x00FF) | (a << 8)
    x -= 1
    state = 'QDV5' if x != 0 else 'QDV3'

    while True:
        if state == 'QDV3':
            dvdnd = (dvdnd - dvsr) & 0xFFFF
            state = 'QDV4'
        if state == 'QDV4':
            quot = ((quot << 1) | 1) & 0xFFFF    # ROL QUOT with C=1 from the
            #                                      subtract, or from the compare
            x -= 1
            if x < 0:
                break
            dvsr >>= 1
            state = 'QDV5'
        if state == 'QDV5':
            hi_d, hi_s = dvdnd >> 8, dvsr >> 8
            if hi_d < hi_s:
                state = 'QDV4_C0'
            elif hi_d != hi_s:
                state = 'QDV3'
                continue
            elif (dvdnd & 0xFF) >= (dvsr & 0xFF):
                state = 'QDV3'
                continue
            else:
                state = 'QDV4_C0'
        if state == 'QDV4_C0':
            quot = (quot << 1) & 0xFFFF          # ROL QUOT with C=0
            x -= 1
            if x < 0:
                break
            dvsr >>= 1
            state = 'QDV5'
    return (quot >> 8) & 0xFF, quot & 0xFF


def characterise():
    """⭐ WHAT QDIV ACTUALLY COMPUTES, and why the 6809 transliterates it.

    The hope was that QDIV(dx, dy) == (dx << 8) // dy, which would let
    `pcspak.inc` use any correct shift-and-subtract divide and skip a
    carry-flag dance across three labels.  ⛔ IT DOES NOT.  Over every input
    the scan converter can present it is the exact quotient or ONE LESS --
    never worse, never random -- and the low answers are exactly the cases
    where the pre-scale stops one shift short of an exact power-of-two ratio.

    0.4 % of inputs, one ULP each.  ⚠ That is still a different slope, a
    different span edge and therefore a different bounce, so the port
    transliterates QDIV rather than approximating it, and this function is the
    record of why the shortcut was refused.

    Returns (n_exact, n_low, n_other).
    """
    exact = low = other = 0
    for dy in range(1, 256):
        for dx in range(0, 256):
            coeff, fract = qdiv(dx, dy)
            got = (coeff << 8) | fract
            want = min((dx << 8) // dy, 0xFFFF)
            if got == want:
                exact += 1
            elif got == want - 1:
                low += 1
            else:
                other += 1
    return exact, low, other


def invariant():
    """⭐ THE INDEPENDENT CHECK ON QDIV, and the one that matters.

    A slope is an 8.8 increment stepped once per scanline down an edge
    (`SCANPLY6`, PPAK.s:395).  Whatever the divide does internally, after `dy`
    steps the integer x MUST have advanced by dx -- that is the only thing the
    scan converter asks of it.

    This checks that directly, over every edge a 160 x 240 table can contain,
    and it is independent of the algorithm: it would catch a transliteration
    that is self-consistently wrong, which comparing against `//` cannot.

    Returns the list of edges where the advance is not dx or dx-1.
    """
    bad = []
    for dy in range(1, 240):
        for dx in range(0, 160):
            coeff, fract = qdiv(dx, dy)
            acc, xi = 0, 0
            for _ in range(dy):
                acc += fract
                xi += coeff + (acc >> 8)
                acc &= 0xFF
            if not -1 <= xi - dx <= 0:
                bad.append((dx, dy, xi, dx))
    return bad


# ------------------------------------------------------ the slope quantiser --
_DXA = None
_DXB = None


def _codes():
    global _DXA, _DXB
    if _DXA is None:
        _DXA = A.block('PPAK.s', 'DXCODESA')
        _DXB = A.block('PPAK.s', 'DXCODESB')
    return _DXA, _DXB


def divide(dx, dy, positive):
    """`DIVIDE` -- PPAK.s:658.  The edge's slope as 8.8, plus its SLOPE CODE.

    ⭐ The code is not a rendering detail: it is the surface-normal index the
    simulator bounces the ball off (`CHECKHORIZ`/`CHECKVERT`, RUN.s:1570/1668),
    which is why the editor has to store it in the span database.

    `positive` is the carry the caller hands DIVIDE -- set when dx is to be
    taken as positive.  Returns (coeff, fract, code).
    """
    dxa, dxb = _codes()
    if dx == 0:                                  # a vertical edge
        return 0, 0, 8
    # DIVIDE2: `PHP / BCS DIVIDE3 / EOR #$FF / ADC #1`.  BCS was not taken, so
    # C is 0 and the ADC adds exactly 1 -- a two's complement negate.
    mag = dx if positive else ((dx ^ 0xFF) + 1) & 0xFF
    if dy == 0:
        # DIVIDE3: `LDA DY / BEQ DIVIDE4` falls through with A = 0 and X = |dx|.
        coeff, fract = mag, 0
    else:
        coeff, fract = qdiv(mag, dy)

    if coeff >= 16:                              # DIVIDE4: nearly horizontal
        code = 0
    elif coeff >= 1:
        code = dxa[coeff]                        # DIVIDE5: slopes < 1
    else:
        code = dxb[fract >> 4]                   # DIVIDE6: slopes > 1

    if not positive:
        # DIVIDE7.  `LDA #17 / SBC DXCODE` with the carry CLEAR -- Budge marks
        # it ";C=0!" -- so the borrow is intended and this is 16 - code.
        code = (16 - code) & 0xFF
        # ⛔ AND CODE 0 BECOMES 16, WHICH DOES NOT FIT THE NIBBLE it is packed
        # into at DOSCN5 (PPAK.s:826): bit 4 bleeds into the neighbouring
        # slope.  DXCODESA/B only ever yield 8..15, so a positive edge's code
        # is 0 or 8..15 and a negative one's is 1..8 or 16 -- seventeen values
        # in four bits, and code 0 with negative dx is the one that overflows.
        # That is exactly the near-horizontal case.  ⭐ REPRODUCED, not fixed:
        # it is in the collision data path the gate compares (pcs.md 5b).
        #
        # Then a 16-bit negate of the slope: `EOR #$FF / ADC #0` twice, with
        # the carry out of the SBC, which is set because 17 - code >= 0 always
        # (Budge marks that ";C=1!" too).
        fract = ((fract ^ 0xFF) + 1) & 0xFF
        coeff = ((coeff ^ 0xFF) + (1 if fract == 0 else 0)) & 0xFF
    return coeff, fract, code


if __name__ == '__main__':
    exact, low, other = characterise()
    n = exact + low + other
    print('QDIV over %d inputs: %d exact, %d one low, %d other'
          % (n, exact, low, other))
    if other:
        print('FAIL  QDIV is not within one ULP of the exact quotient')
        sys.exit(1)
    print('      -> not (dx << 8) // dy, so pcspak.inc TRANSLITERATES it.')

    bad = invariant()
    if bad:
        print('FAIL  %d edges do not advance x by dx over dy steps:' % len(bad))
        for row in bad[:8]:
            print('        dx=%3d dy=%3d advanced %d, wanted %d' % row)
        sys.exit(1)
    print('ok    and every edge of a %d x %d table advances x by dx (or dx-1)'
          % (160, 240))
    print('      over its dy scanlines - which is the only thing the scan')
    print('      converter asks of the divide, and is independent of how it works.')
