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


# ═══════════════════════════════════════════════════════════════════════
# THE BALL
#
# ⭐⭐ ANGLES ARE 0..31 FOR A FULL TURN, AND THEY ARE NOT EVENLY SPACED.
# `angle >> 3` is the quadrant and `angle & 7` picks one of eight sub-angles:
#
#     SUB = 0, 5.625, 11.25, 22.5, 45, 67.5, 78.75, 84.375 degrees
#
# so the steps crowd towards the axes and spread out at 45.  That is not an
# approximation of an even scale - it is a deliberate one, and it is why a
# ball rolling along a nearly flat surface has fine angular resolution while a
# 45-degree wall has coarse.  Seven cosine tables cover both roles: CTBL1[s]
# is cos(SUB[s]) and CTBL2[s] is cos(90 - SUB[s]), which is sin(SUB[s]).
# ═══════════════════════════════════════════════════════════════════════

_COS = {}


def _cos(name):
    if name not in _COS:
        _COS[name] = A.block('RUN.s', name)
    return _COS[name]


# RUN.s:1160-1166's CTBL1LO/HI and CTBL2LO/HI, by name.  ⚠ Indexed from 1:
# `LDA CTBL1LO-1,X` with X = angle & 7, which is never 0 here (s == 0 skips
# the rotation entirely).
CTBL1 = [None, 'C05625', 'C1125', 'C225', 'C45', 'C675', 'C7875', 'C84375']
CTBL2 = [None, 'C84375', 'C7875', 'C675', 'C45', 'C225', 'C1125', 'C05625']


def _sb(v):
    """A byte as a signed value."""
    v &= 0xFF
    return v - 256 if v & 0x80 else v


def _neg(v):
    """`EOR #$FF / CLC / ADC #1` - two's complement in a byte."""
    return ((v ^ 0xFF) + 1) & 0xFF


def _quad(n, vx, vy):
    """One of the three 90-degree folds (QUAD1/2/3, RUN.s:1199-1220).

    QUAD1  (x, y) -> (-y,  x)
    QUAD2  (x, y) -> (-x, -y)
    QUAD3  (x, y) -> ( y, -x)
    """
    if n == 1:
        return _neg(vy), vx
    if n == 2:
        return _neg(vx), _neg(vy)
    if n == 3:
        return vy, _neg(vx)
    return vx, vy


def rotate(angle, vx, vy):
    """ROTATE (RUN.s:1117).  Rotate (vx, vy) by `angle`, both signed bytes in.

    ⭐ `(x cos t - y sin t, x sin t + y cos t)` WITH NO MULTIPLY: fold the
    vector into the first quadrant counting the folds, look the two products
    up in a pair of cosine tables, and apply the remaining quarter-turns at the
    end.  Two table reads and an add, for a rotation by any of 32 angles.
    """
    t = angle & 0xFF
    xt = t >> 3

    if _sb(vx) >= 0:
        if _sb(vy) >= 0:
            count = 0
        else:
            vx, vy = _quad(1, vx, vy)
            count = 3
    else:
        if _sb(vy) >= 0:
            vx, vy = _quad(3, vx, vy)
            count = 1
        else:
            vx, vy = _quad(2, vx, vy)
            count = 2

    total = (count + xt) & 0xFF
    if total >= 4:                       # `CMP #4 / BCC *+4 / SBC #4`
        total -= 4

    # ROT6: both components are table indices now, so 63 is the ceiling.
    if vy >= 0x40:
        vy = 0x3F
    if vx >= 0x40:
        vx = 0x3F

    s = t & 7
    if s:
        t1 = _cos(CTBL1[s])
        t2 = _cos(CTBL2[s])
        # ⭐ nx = (t1[vx] - t2[vy]) >> 2, ARITHMETICALLY.  `SBC / PHP / ROR /
        # PLP / ROR / EOR #$C0` shifts the 9-bit difference right twice,
        # feeding the SAME carry into bit 7 both times and then inverting both
        # top bits - which is a sign extension written as two rotates.
        d = (t1[vx] - t2[vy]) & 0xFF
        carry = 1 if t1[vx] >= t2[vy] else 0
        a = ((carry << 7) | (d >> 1)) & 0xFF
        a = ((carry << 7) | (a >> 1)) & 0xFF
        nx = a ^ 0xC0

        # ⭐ ny = (t2[vx] + t1[vy]) >> 2, clamped.  The first ROR takes the
        # add's carry as bit 7; a negative result there means the sum
        # overflowed nine bits, and $7F before the second shift is 63 after it.
        e = t2[vx] + t1[vy]
        a = ((e & 0x1FF) >> 1) & 0xFF
        if a & 0x80:
            a = 0x7F
        ny = a >> 1
        vx, vy = nx, ny

    for _ in range(total):               # FIXQUAD: `total` more quarter-turns
        vx, vy = _quad(1, vx, vy)
    return vx & 0xFF, vy & 0xFF


# ─────────────────────────────────────────────────────────────── the bounce ─
def _world():
    """The four World sliders' tables (INITWORLD, RUN.s:2169)."""
    return (A.block('RUN.s', 'GRAVTBL'), A.block('RUN.s', 'TIMETBL'),
            A.block('RUN.s', 'KICKTBL'),
            A.block('RUN.s', 'ELASTLO'), A.block('RUN.s', 'ELASTHI'))


_ELAST_OF = None


def elast_table(wset3):
    """The cosine table the elasticity slider selects.

    ⭐ EIGHT RESTITUTIONS OUT OF ONE CURVE.  ELASTLO/ELASTHI are not values,
    they are the ADDRESSES of cosine tables - so `ELAST[vn]` is
    `vn * 4 * cos(a)` for a chosen a, and `>> 2` makes it `vn * cos(a)`.  The
    slider picks which cosine.  ⚠ Positions 2 and 3 name the SAME table
    (C675), so they behave identically; reproduced, not fixed.
    """
    global _ELAST_OF
    if _ELAST_OF is None:
        # ⚠ THE COSINE TABLES ARE `HEX` LABELS, NOT EQUATES, so their addresses
        # come from the ORG and their order in the source.  RUN.s is `ORG $8200`
        # and they are the first thing in it, 64 bytes apart - which is what
        # makes ELASTLO/HI's addresses decodable at all.
        base = 0x8200
        order = ['C05625', 'C1125', 'C225', 'C45', 'C675', 'C7875', 'C84375']
        lo, hi = A.block('RUN.s', 'ELASTLO'), A.block('RUN.s', 'ELASTHI')
        out = []
        for l, h in zip(lo, hi):
            k = ((l | (h << 8)) - base) // 64
            if not 0 <= k < len(order):
                raise ValueError('ELAST entry $%04X is not a cosine table'
                                 % (l | (h << 8)))
            out.append(order[k])
        _ELAST_OF = out
    return _cos(_ELAST_OF[wset3])


def bounce(tta, bdx, bdy, kick=0, elastic=True, wset3=0):
    """BOUNCE (RUN.s:1235).  Reflect the ball off a surface.

    `tta` is defined so that rotating the velocity BY it puts the surface's
    outward normal on +Y: 0 is a floor, 16 a ceiling, 8 a rightward-facing
    wall and 24 a leftward-facing one.

    ⭐ Returns (bdx, bdy, hit).  `hit` is ALWAYS true - even when the ball was
    already moving away and nothing changed, which is what lets a ball resting
    on a bumper keep scoring, and is deliberate (MOVEB9's three-frame re-probe
    is built on it).
    """
    vx, vy = rotate(tta, bdx, bdy)
    if _sb(vy) >= 0:                      # already moving away
        return bdx, bdy, True
    vn = _neg(vy)
    if elastic:
        vn = elast_table(wset3)[vn & 0x3F] >> 2
        if vn == 0:
            vn = 1
    vn = vn + kick
    if vn > 0x3F:
        vn = 0x3F
    nx, ny = rotate((32 - tta) & 0xFF, vx, vn)
    return nx, ny, True


# ═══════════════════════════════════════════════════════════════════════
# THE BALL'S WORLD
#
# ⭐⭐ THE BALL COLLIDES WITH THE SPAN DATABASE, NOT WITH THE SCREEN.  PCS is
# often described as reading its own framebuffer; it does not.  CHECKHORIZ and
# CHECKVERT walk the same four-byte records the scan converter built, and the
# slope nibbles in them ARE the surface normals.  That is why the editor has to
# keep the database consistent through every drag, and why this port could gate
# on the database before it had a ball at all.
#
# ⛔ AND OBJECT 0 IS READ INSIDE OUT.  The backdrop is a B-polygon whose
# records are the OPEN area, so a span belonging to object 0 is free space and
# the GAPS BETWEEN its spans are wall.  Every other object's spans are solid.
# CHECKVERT switches between those two readings mid-scanline, at the first
# record whose object is 0.
# ═══════════════════════════════════════════════════════════════════════

BM_HORIZ = 0x80         # BMOVE b7: this step is horizontal
BM_POS = 0x40           # BMOVE b6: ... in the positive direction (down / right)


class Ball(object):
    """The seven bytes of L+16..L+22, and nothing else (RUN.s:1352)."""

    def __init__(self, x=0, y=0, bdx=0, bdy=0):
        self.bstat = 0
        self.x1, self.y1 = x, y
        self.bdx, self.bdy = bdx & 0xFF, bdy & 0xFF
        self.bxacc, self.byacc = 0, 0
        self.idle = 0                     # L[7], the frames since a hit

    @property
    def x2(self):
        return (self.x1 + 4) & 0xFF

    @property
    def y2(self):
        return (self.y1 + 4) & 0xFF

    def __repr__(self):
        return '(%3d,%3d) v=(%4d,%4d)' % (self.x1, self.y1,
                                          _sb(self.bdx), _sb(self.bdy))


class World(object):
    """A table the ball can be run against.

    `rows[y]` is scanline y's span records, as pcspak.Pak builds them, and
    `hit(obj, tta, ball)` is the dispatcher DOHIT reaches - PBOUNCE for a plain
    polygon, the part's own HIT proc for a library part.
    """

    def __init__(self, pak, wset=(0, 0, 0, 0), width=160):
        self.rows = pak.rows
        self.wset = list(wset)
        self.TW = width
        g, t, k, _lo, _hi = _world()
        self.gravmask = g[wset[0]]
        self.time = t[wset[1]]
        self.kick = k[wset[2]]
        self.hits = []                    # (frame, obj, tta) - for the bench
        # ⭐ BMOVE, which is not the ball's velocity but the direction of THIS
        # ONE PIXEL STEP - $40 down, $00 up, $C0 right, $80 left (MOVEB3/4/6/7).
        # Half the part procs read it and nothing else carries it.
        self.bmove = 0
        # ⭐ The library parts, by object index, and the routine that runs their
        # HIT procs.  pcsobj.Sim installs both; with neither, every object is a
        # plain polygon and DOHIT is PBOUNCE, which is what step 2's gate ran.
        self.parts = {}
        self.dispatch = None

    def pbounce(self, ball, tta):
        """PBOUNCE (RUN.s:1232) - the plain reflection, no part behaviour."""
        bdx, bdy, did = bounce(tta, ball.bdx, ball.bdy, kick=0,
                               elastic=True, wset3=self.wset[3])
        ball.bdx, ball.bdy = bdx, bdy
        return did

    def hit(self, ball, obj, tta, frame):
        """DOHIT (RUN.s:1547) - the part's own HIT proc, or PBOUNCE.

        ⛔ `LDA VHI,Y / BNE DOHIT2 / JSR PBOUNCE` - the test is whether the
        object HAS a library base at all, so a plain polygon reaches the
        reflection without a vector and a library part always has one."""
        self.hits.append((frame, obj, tta))
        p = self.parts.get(obj)
        if p is None or self.dispatch is None:
            return self.pbounce(ball, tta)
        return self.dispatch(p, ball, obj, tta, frame)


def _ror9(a, carry):
    """`ROR` on a byte with an incoming carry - a nine-bit shift right."""
    return (((carry & 1) << 7) | (a >> 1)) & 0xFF


def checkhoriz(w, ball, x, y, frame):
    """CHECKHORIZ (RUN.s:1570).  Is column `x` solid on scanline `y`?

    ⭐ Three cases, and the third is the one that makes the ball solid rather
    than merely bouncy: x exactly on a span's left edge, x exactly on its
    right edge, or x strictly INSIDE a span that is not object 0 - which is the
    ball having got into solid material and is forced to a hit so it is pushed
    back out.
    """
    if y >= len(w.rows):
        return False
    recs = w.rows[y]
    for (xl, obj, xr, sl) in recs:
        if x == xl:
            tta = ((32 if obj else 16) - (sl & 0x0F)) & 0xFF
            if w.hit(ball, obj, tta, frame):
                _fixh(ball, obj, left=True)
                return True
            continue
        if x < xl:
            continue
        if x == xr or x > xr:
            if x == xr:
                tta = ((16 if obj else 32) - (sl >> 4)) & 0xFF
                if w.hit(ball, obj, tta, frame):
                    _fixh(ball, obj, left=False)
                    return True
            continue
        # strictly inside
        if obj != 0:
            tta = ((16 if obj else 32) - (sl >> 4)) & 0xFF
            if w.hit(ball, obj, tta, frame):
                _fixh(ball, obj, left=False)
                return True
    return False


def _fixh(ball, obj, left):
    """FIXLEFT / FIXRIGHT (RUN.s:1638).  ⭐ A ball with no horizontal speed at
    all would sit against a wall for ever, so one unit is pushed INTO the free
    side; and the pending sub-pixel step is discarded so the move does not
    happen anyway."""
    if ball.bdx == 0:
        if left:
            ball.bdx = _neg(1) if obj else 1
        else:
            ball.bdx = 1 if obj else _neg(1)
    ball.byacc = ball.byacc          # (unchanged)
    ball.bxacc &= 0x1F


def _vfix(code, bmove, rising_rule):
    """VLFIX / VRFIX (RUN.s:1828).  ⭐ "Did I land on top of it, or hit its
    side?"  A steep edge met while falling becomes a FLAT FLOOR; the thresholds
    are 6 and 11 out of the sixteen slope codes, and which one applies depends
    on the direction of travel.  This heuristic IS the game's feel."""
    down = bool(bmove & BM_POS)
    use_down = down if rising_rule else not down
    if use_down:
        flat = code >= 6
    else:
        flat = code < 11
    if not flat:
        return code
    return 0 if down else 16


def dovhit(w, ball, p1, p2, lftta, rttta, bmove, frame):
    """DOVHIT (RUN.s:1778).  Which side of the obstacle [p1, p2] is the ball on,
    and what surface did it meet?"""
    if p2 == ball.x1:
        tta = (16 - rttta) & 0xFF
        return _vdo(w, ball, tta, frame, right=True)
    mid = (_ror9((p2 + p1) & 0xFF, 1 if (p2 + p1) > 0xFF else 0) + 2) & 0xFF
    if mid < ball.x2:
        code = _vfix(rttta & 0x0F, bmove, rising_rule=False)
        tta = 0 if code == 0 else (16 - code) & 0xFF
        return _vdo(w, ball, tta, frame, right=True)
    lftta &= 0x0F
    if p1 == ball.x2:
        tta = (32 - lftta) & 0xFF
        return _vdo(w, ball, tta, frame, right=False)
    code = _vfix(lftta, bmove, rising_rule=True)
    tta = 0 if code == 0 else (32 - code) & 0xFF
    return _vdo(w, ball, tta, frame, right=False)


def _vdo(w, ball, tta, frame, right):
    did = w.hit(ball, w._obj, tta, frame)
    if did and ball.bdx == 0:
        ball.bdx = 1 if right else _neg(1)
    return did


def checkvert(w, ball, y, bmove, frame):
    """CHECKVERT (RUN.s:1668).  Is row `y` solid anywhere under the ball?

    ⛔⛔ TWO READINGS OF THE SAME RECORDS, AND IT ALTERNATES BETWEEN THEM.
    A span belonging to any object is itself the obstacle; a span belonging to
    object 0 is OPEN PLAYFIELD and the obstacle is the GAP between it and the
    next one, because the backdrop is a B-polygon that stores its interior.
    The walk switches at every record whose object changes: `BEQ BCHECKV2`
    leaves object mode and `BCHKV5`'s `JMP PCHECKV2` - after a `DEY` that puts
    the record back - returns to it.

    ⚠ NOT "objects first, then the backdrop".  The records are in DRAW order,
    so object 0's come FIRST on every scanline of a normal table and the
    alternation is the only thing that ever reaches an object at all.  A walk
    that leaves object mode for good sees nothing but backdrop gaps - and passes
    every test whose objects are only ever met side-on, because CHECKHORIZ
    walks the same list without the two modes.

    ⚠ Transliterated with the 6502's own Y, in bytes, because the mode switches
    re-read a record from a different offset and any tidier structure loses
    that.  `f` is the scanline's records flattened, which is what PBDX counts.
    """
    if y >= len(w.rows) or not w.rows[y]:
        # OFFBOARD (RUN.s:1661): a scanline with no records at all is an
        # invisible floor or ceiling, depending on which way the ball is going.
        # ⛔ `LDA #0 / BIT BMOVE / BVS *+4 / LDA #16 / STA TTA / JMP PBOUNCE` -
        # a TAIL CALL to the bounce, so this path takes neither DOHIT's hit
        # count nor DOVHIT's "if bdx came out zero, nudge it off the wall"
        # epilogue, and it returns the bounce's own carry.
        w._obj = 0
        tta = 0 if (bmove & BM_POS) else 16
        bdx, bdy, did = bounce(tta, ball.bdx, ball.bdy, kick=0,
                               elastic=True, wset3=w.wset[3])
        ball.bdx, ball.bdy = bdx, bdy
        return did

    f = [b for r in w.rows[y] for b in r]
    hcnt = len(f)
    Y = 1
    x = p1 = 0
    lftta = 8
    w._obj = 0
    state = 'PCHECKV2'

    while True:
        # -- object mode: the span IS the obstacle ----------------------
        if state == 'PCHECKV2':
            Y -= 1
            state = 'PCHECKV'
        if state == 'PCHECKV':
            x = f[Y]
            Y += 1
            obj = f[Y]
            if obj == 0:
                state = 'BCHECKV2'
            else:
                w._obj = obj
                if x > ball.x2:                       # CPX X2 / BCC / BNE
                    state = 'PCHKV2'
                else:
                    p1 = x
                    Y += 1
                    a = f[Y]
                    if a < ball.x1:                   # CMP X1 / BCC PCHKV3
                        state = 'PCHKV3'
                    else:
                        p2 = a
                        Y += 1
                        sl = f[Y]
                        if dovhit(w, ball, p1, p2, sl & 0x0F, sl >> 4,
                                  bmove, frame):
                            ball.byacc &= 0x1F
                            return True
                        state = 'PCHKV4'
        if state == 'PCHKV2':
            Y += 1
            state = 'PCHKV3'
        if state == 'PCHKV3':
            Y += 1
            state = 'PCHKV4'
        if state == 'PCHKV4':
            Y += 1
            if Y != hcnt:
                state = 'PCHECKV'
                continue
            return False

        # -- background mode: the obstacle is the GAP -------------------
        if state == 'BCHECKV2':
            p1 = 0                                    # the left wall
            lftta = 8
            state = 'BCHKV2'
        while True:
            if state == 'BCHECKV':
                x = f[Y]
                Y += 1
                if f[Y] != 0:
                    state = 'BCHKV4'
                else:
                    w._obj = 0
                    state = 'BCHKV2'
            if state == 'BCHKV2':
                if ball.x2 < p1 or x < ball.x1:       # LDA X2/CMP P1, CPX X1
                    state = 'BCHKV3'
                else:
                    p2 = x
                    Y += 2
                    rttta = f[Y] & 0x0F
                    Y -= 2
                    if dovhit(w, ball, p1, p2, lftta, rttta, bmove, frame):
                        ball.byacc &= 0x1F
                        return True
                    state = 'BCHKV3'
            if state == 'BCHKV3':
                Y += 1
                p1 = f[Y]
                Y += 1
                lftta = f[Y] >> 4
                Y += 1
                if Y != hcnt:
                    state = 'BCHECKV'
                    continue
                state = 'BCHKV4'
            if state == 'BCHKV4':
                # ⭐ THE LAST GAP, OUT TO THE RIGHT WALL - and it is tested BOTH
                # when the list runs out AND when an object interrupts the
                # backdrop's run, which is what makes the alternation safe.
                if ball.x2 >= p1:
                    # ⚠ `LDA #153` in a 160-wide world, and RUN.s:1864's wall
                    # clamp is 153 too while PPAK.s:774's right edge is 159.
                    # The Apple II version is self-consistent at 154/153, so
                    # this is a port slip in the ORIGINAL; reproduced, and
                    # written as TW-7 so the port has one constant for it.
                    p2 = w.TW - 7
                    if dovhit(w, ball, p1, p2, lftta, 8, bmove, frame):
                        ball.byacc &= 0x1F
                        return True
                if Y == hcnt:
                    return False
                state = 'PCHECKV2'
                break


def moveball(w, ball, frame):
    """MOVEBALL (RUN.s:1352).  One frame of the ball.

    ⭐⭐ ONE PIXEL AT A TIME, Y THEN X, AND THE STEP IS ONLY COMMITTED WHEN THE
    PROBE SAYS CLEAR - so the ball never overlaps geometry and never has to be
    pushed out of it.  Moving both axes and then testing gives no way to know
    which face was met, and a ball in a corner leaves along the diagonal it
    arrived on.

    ⭐ Gravity is not an acceleration constant: it is HOW OFTEN one unit is
    taken off BDY.  The slider picks a mask, and `(frame & mask) == 0` is the
    whole of it - eight strengths from one decrement, with terminal velocity a
    clamp at -47.
    """
    ball.bxacc = (ball.bxacc + _sb(ball.bdx)) & 0xFF
    ball.byacc = (ball.byacc + _sb(ball.bdy)) & 0xFF
    htcnt = [0]

    if (frame & w.gravmask) == 0:
        v = (_sb(ball.bdy) - 1)
        if v < 0 and v < _sb(0xD1):
            v = _sb(0xD1)                 # terminal velocity
        ball.bdy = v & 0xFF

    real_hit = w.hit

    def counted(*a):
        htcnt[0] += 1
        return real_hit(*a)
    w.hit = counted

    try:
        while True:                       # MOVEB2
            if ball.bstat & 0x80:
                break
            ya = _sb(ball.byacc)
            if ya < 0:                                    # MOVEB3: down
                ball.byacc = (ball.byacc + 0x20) & 0xFF
                w.bmove = BM_POS                          # $40: down
                if not checkvert(w, ball, (ball.y2 + 1) & 0xFF, BM_POS, frame):
                    ball.y1 = (ball.y1 + 1) & 0xFF
            elif ball.byacc >= 0x20:                      # MOVEB4: up
                ball.byacc = (ball.byacc - 0x20) & 0xFF
                w.bmove = 0                               # $00: up
                if not checkvert(w, ball, (ball.y1 - 1) & 0xFF, 0, frame):
                    ball.y1 = (ball.y1 - 1) & 0xFF
            else:
                if _sb(ball.bxacc) >= 0 and ball.bxacc < 0x20:
                    break                                 # -> MOVEB9
            if ball.bstat & 0x80:
                break
            xa = _sb(ball.bxacc)
            if xa < 0:                                    # MOVEB7: left
                ball.bxacc = (ball.bxacc + 0x20) & 0xFF
                w.bmove = BM_HORIZ                        # $80: left
                a = checkhoriz(w, ball, (ball.x1 - 1) & 0xFF, ball.y1, frame)
                b = a or checkhoriz(w, ball, (ball.x1 - 1) & 0xFF, ball.y2, frame)
                if not b and ball.x1 != 0:
                    ball.x1 = (ball.x1 - 1) & 0xFF
            elif ball.bxacc >= 0x20:                      # MOVEB6: right
                ball.bxacc = (ball.bxacc - 0x20) & 0xFF
                w.bmove = BM_HORIZ | BM_POS               # $C0: right
                a = checkhoriz(w, ball, (ball.x2 + 1) & 0xFF, ball.y1, frame)
                b = a or checkhoriz(w, ball, (ball.x2 + 1) & 0xFF, ball.y2, frame)
                if not b and ball.x2 < 153:
                    ball.x1 = (ball.x1 + 1) & 0xFF
    finally:
        w.hit = real_hit

    # MOVEB9.  ⭐ A RESTING BALL RE-PROBES ITS OWN FLOOR.  After three frames
    # with no hit at all it tests the row below itself once more, which is what
    # keeps a ball sitting on a bumper scoring and a ball in a pocket held.
    ball.idle = (ball.idle + 1) & 0xFF
    if htcnt[0]:
        ball.idle = 0
    elif ball.idle >= 3:
        w.bmove = BM_POS
        checkvert(w, ball, (ball.y2 + 1) & 0xFF, BM_POS, frame)
        ball.idle = 0
    return htcnt[0]


# ═══════════════════════════════════════════════════════════════════════
def physics_selftest():
    """⭐ THE BALL, CHECKED BY ITS BEHAVIOUR rather than by reading it.

    These are the properties a pinball simulation has to have, stated so that
    a transliteration error cannot satisfy them by accident.
    """
    import pcspak as K
    bad = []

    # -- 1  ROTATE's identities ----------------------------------------
    for vx, vy in ((20, 10), (-20, 10), (20, -10), (-20, -10), (63, 0), (0, 63)):
        x, y = rotate(0, vx & 0xFF, vy & 0xFF)
        if (_sb(x), _sb(y)) != (vx, vy):
            bad.append('rotate by 0 changed (%d,%d) to (%d,%d)'
                       % (vx, vy, _sb(x), _sb(y)))
    for vx, vy in ((20, 10), (-13, 7)):
        x, y = vx & 0xFF, vy & 0xFF
        for _ in range(4):                       # four quarter-turns
            x, y = rotate(8, x, y)
        if (_sb(x), _sb(y)) != (vx, vy):
            bad.append('four rotations by 8 did not return (%d,%d)' % (vx, vy))
    x, y = rotate(8, 20, 0)                      # +90: (1,0) -> (0,1)
    if (_sb(x), _sb(y)) != (0, 20):
        bad.append('rotate by 8 put (20,0) at (%d,%d), wanted (0,20)'
                   % (_sb(x), _sb(y)))

    # -- 2  the bounce off the four cardinal surfaces --------------------
    for tta, vin, want in ((0, (20, -20), (20, 20)),      # a floor
                           (16, (20, 20), (20, -20)),     # a ceiling
                           (8, (-20, 10), (20, 10)),      # a wall facing right
                           (24, (20, 10), (-20, 10))):    # ... and facing left
        x, y, did = bounce(tta, vin[0] & 0xFF, vin[1] & 0xFF, elastic=False)
        if (_sb(x), _sb(y)) != want:
            bad.append('bounce tta=%d on (%d,%d) gave (%d,%d), wanted (%d,%d)'
                       % (tta, vin[0], vin[1], _sb(x), _sb(y), want[0], want[1]))
    # ⭐ and a surface the ball is already leaving is a HIT that changes nothing
    x, y, did = bounce(0, 20, 20, elastic=False)
    if not did or (_sb(x), _sb(y)) != (20, 20):
        bad.append('a ball leaving a floor was not reported as an unchanged hit')

    # -- 3  the elasticity slider names the cosine tables ---------------
    for i in range(8):
        elast_table(i)
    want = ['C84375', 'C7875', 'C675', 'C675', 'C45', 'C225', 'C1125', 'C05625']
    if _ELAST_OF != want:
        bad.append('the elasticity slider maps to %s' % (_ELAST_OF,))
    # ⚠ positions 2 and 3 ARE the same table in the original.  Asserted so that
    # a future "fix" has to argue with this line.
    if _ELAST_OF[2] != _ELAST_OF[3]:
        bad.append('elasticity 2 and 3 no longer name the same table')
    # and a harder bounce comes back faster than a soft one
    soft = bounce(0, 0, _neg(40), elastic=True, wset3=0)[1]
    hard = bounce(0, 0, _neg(40), elastic=True, wset3=7)[1]
    if not 0 < _sb(soft) < _sb(hard) <= 40:
        bad.append('elasticity is not monotonic: soft %d, hard %d'
                   % (_sb(soft), _sb(hard)))

    # -- 4  gravity is a RATE, and the mask is what sets it -------------
    # GRAVTBL is FF 7F 3F 1F 0F 07 03 01, so slider n fires 2^n times in 256
    # frames: the weakest setting takes one unit off BDY once every 256 frames
    # and the strongest every other frame.  ⭐ Eight strengths out of a single
    # `DEC`, which is why there is no acceleration constant anywhere.
    g = A.block('RUN.s', 'GRAVTBL')
    for i, m in enumerate(g):
        n = sum(1 for f in range(256) if (f & m) == 0)
        if n != (1 << i):
            bad.append('gravity %d fires %d times in 256 frames, wanted %d'
                       % (i, n, 1 << i))

    # -- 5  ⭐⭐ THE INVARIANT THAT MATTERS: a ball in a closed box stays in it.
    back = K.Obj(K.BPOLY, 1, [10, 150, 150, 10], [10, 10, 200, 200])
    back.align()
    pak = K.Pak(height=240, width=160)
    pak.objs = [back]
    pak.display()
    for wset in ((5, 3, 3, 4), (7, 1, 0, 7), (0, 7, 7, 0)):
        w = World(pak, wset=wset)
        b = Ball(x=80, y=20, bdx=12, bdy=0)
        for f in range(1, 2000):
            moveball(w, b, f)
            if not (9 <= b.x1 and b.x2 <= 151 and 9 <= b.y1 and b.y2 <= 201):
                bad.append('world %s: the ball left the box at frame %d, %s'
                           % (wset, f, b))
                break
        if not w.hits:
            bad.append('world %s: the ball never hit anything in 2000 frames'
                       % (wset,))
    return bad


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

    bad = physics_selftest()
    for b in bad:
        print('FAIL ', b)
    if bad:
        sys.exit(1)
    print('ok    the ball: ROTATE\'s identities, the bounce off all four')
    print('      cardinal surfaces, the elasticity slider naming its cosine')
    print('      tables (2 and 3 the same, as in the original), gravity as a')
    print('      rate, and a ball that stays inside a closed box for 2,000')
    print('      frames at three different World settings.')
