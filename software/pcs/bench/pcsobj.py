#!/usr/bin/env python3
"""pcsobj.py - the library parts: RUN.s's per-part procs and its PLAY loop.

⛔ WRITTEN FROM THE 6502 AND NEVER ADJUSTED TO MATCH THE 6809.  pcsphys.py's
header says why; this module is the same contract for the half of the simulator
that is not arithmetic.  When it and pcsrun.inc disagree, RUN.s decides.

⭐⭐ A PART IS THREE PROCS AND ONE STATE BYTE.  Every one of the 43 templates
carries `DA <RUN> / DA <INIT> / DA <HIT>` at L[10..15] and a state byte at
L[8], and that is the whole of PCS's object system: the PLAY loop calls RUN
when `frame & TIME[obj] == 0`, the collision path calls HIT, and the wiring
kit's "turn off" calls INIT.  There is no class hierarchy and no message
dispatch - twenty-two HIT procs, fourteen RUN procs, ten INIT procs, and a
four-byte record.

⛔ AND THE VECTORS ARE RE-KEYED BY PART TYPE.  A saved Atari table stores
absolute 6502 addresses in L[10..15]; those cannot survive the change of
machine, so the port stores a part TYPE ID at L[10] and rebuilds the vectors on
load (`software/pcs/docs/pcs.md` 5b).  Every other offset in the record is the
original's, because the procs index them literally.

⭐ ANIMATION IS A FRAME INDEX, NOT A POINTER.  ADVANCE steps L[0..1] by L[7]
(the frame's byte length) and L[8] by one, then XOR-draws; RETREAT undoes both.
The port has no XOR (pcs.md 2), so L[0..1] and L[7] go and `L[8] & $7F` is the
frame - which is exactly what the pointer encoded.  ⚠ Bit 7 of L[8] is a
DIRECTION flag, not part of the index: KNOCKRUN advances from $80 to $82 and
then stores 2 to retreat, so the same low bits are read on the way out.

Source: `software/pcs/reference/pcs-source/RUN.s`, lines cited throughout.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pcsphys as P                                            # noqa: E402


# ── the L record ────────────────────────────────────────────────────────────
# ⚠ THE OFFSETS ARE THE ORIGINAL'S and must stay so: the procs below index them
# with literal `LDY #n`, and the ball's record is L[0..22] entire.
L_TMPL = 0              # ⭐ WAS THE BITMAP POINTER; is the TEMPLATE INDEX.  The
#                         byte that used to select the art still selects it -
#                         but by which of the 43 templates this part is, which
#                         is what indexes the generated art bank.  ⚠ Not the
#                         same thing as L[10]'s part TYPE: six bumpers are one
#                         type and six different pictures.
L_VERT = 2              # the art's top row - flippers MOVE it (FXDVERT)
L_PX = 3                # the art's left column.  ⭐ One number: chunky 8bpp
L_XM = 4                #   has no shift, so HDIV8/HMOD8 collapse (pcs.md 4)
L_HEIGHT = 5            # rows - a flipper's frames differ in height
L_WIDTH = 6             # bytes across
L_STRIDE = 7            # the frame's byte length; unused, kept for the offsets
L_STATE = 8             # ⭐ the state byte, and the animation counter
L_SCORE = 9             # b7 unwireable, b6-4 sound, b3-0 score
L_TYPE = 10             # ⭐ re-keyed: the part type id, where the 6502 had DA
# -- and the ball's tail, MOVEBALL (RUN.s:1352) --
L_BSTAT = 16
L_X1 = 17
L_Y1 = 18
L_BDX = 19
L_BDY = 20
L_BXACC = 21
L_BYACC = 22

LREC = 23               # bytes of L a library object carries

# SCORETBL / SOUNDTBL (RUN.s:1345), read out of the source rather than typed -
# ⚠ the same bytes mkpcs.py emits for the 6809, from the same place.
_TBL = {}


def _tbl(name):
    if name not in _TBL:
        import pcsasm as A
        _TBL[name] = A.block('RUN.s', name)
    return _TBL[name]


class _Lazy(object):
    def __init__(self, name):
        self._n = name

    def __getitem__(self, i):
        return _tbl(self._n)[i]

    def __len__(self):
        return len(_tbl(self._n))


SCORETBL = _Lazy('SCORETBL')
SOUNDTBL = _Lazy('SOUNDTBL')


def _sb(v):
    return v - 256 if v & 0x80 else v


class Part(object):
    """A library object at run time.

    ⭐ THE RECORD IS A BYTE ARRAY AND L IS AN OFFSET INTO IT, deliberately, so
    that the procs' reach BACKWARDS out of L is preserved.  `LDY #$FB` after
    `DEC B2+1` is L[-5] - the last X vertex, which for the four-vertex parts
    that use it is the shape's left edge, and which FLIPHIT, DRAWTARG and
    INITB2 all read.  A model that stored L as its own object would have to
    invent a field for that and would then be modelling a different program.
    """

    def __init__(self, rec, lb, kind):
        self.rec = rec              # the whole object record, as pbdata holds it
        self.lb = lb                # 3 + 2n: where L starts
        self.kind = kind            # the part type - the re-keyed L[10..15]

    def L(self, i):
        return self.rec[self.lb + i]

    def setL(self, i, v):
        self.rec[self.lb + i] = v & 0xFF

    # ⚠ L[-5]: `DEC B2+1 / LDY #$FB` is minus 256 plus 251.
    @property
    def leftx(self):
        return self.rec[self.lb - 5]

    @property
    def state(self):
        return self.L(L_STATE)

    @property
    def frame(self):
        return self.L(L_STATE) & 0x7F

    def __repr__(self):
        return '<%s state=$%02X>' % (self.kind, self.L(L_STATE))


# ── ADVANCE / RETREAT (RUN.s:1272) ──────────────────────────────────────────
def advance(sim, p):
    """One frame forward.  ⭐ The original steps the bitmap POINTER by L[7] and
    the counter by one and XOR-draws the result; the port steps the counter and
    repaints from the span database (pcs.md 2), which is the same animation."""
    p.setL(L_STATE, p.L(L_STATE) + 1)
    sim.drawn.append((sim.ptm1 & 0xFFFF, p.kind, p.L(L_STATE)))


def retreat(sim, p):
    """One frame back.  Returns the 6502's carry - clear on borrow, which is
    what INITB loops on."""
    v = p.L(L_STATE)
    p.setL(L_STATE, v - 1)
    sim.drawn.append((sim.ptm1 & 0xFFFF, p.kind, p.L(L_STATE)))
    return v != 0                                       # SBC #1: C=0 iff v==0


def initb(sim, p):
    """INITB (RUN.s:1310) - retreat until the counter is back at rest."""
    n = 0
    while p.L(L_STATE):
        if not retreat(sim, p):
            break
        n += 1
        if n > 255:                                     # ⚠ bounded: a hang is
            raise RuntimeError('INITB did not settle')  #   worse than a failure
    return


# ── TSET (RUN.s:664) ────────────────────────────────────────────────────────
def tset(p):
    """Arm the part's animation, but only if it is at rest."""
    if p.L(L_STATE) == 0:
        p.setL(L_STATE, 0x80)


# ── scoring and sound: PUTSP (RUN.s:1317) ───────────────────────────────────
def putsp(sim, p, carry):
    """PUTSP - award the part's score and start its sound, but ONLY on a hit.

    ⛔ `PUTSP BCC PUTSP4` - the carry coming out of the bounce is the gate, so
    a part that was touched and did not deflect the ball scores nothing.  Every
    HIT proc below ends `JMP PUTSP` or `JMP PUTSP2` and the difference between
    those two entry points is exactly this test."""
    if not carry:
        return carry
    return putsp2(sim, p, carry)


def putsp2(sim, p, carry):
    """PUTSP2 - score and sound unconditionally, preserving the caller's carry.

    ⛔ THE SOUND NIBBLE IS MASKED HERE AND THE ORIGINAL DOES NOT MASK IT.
    RUN.s:1330 shifts L[9] right four times and indexes `SOUNDTBL-1,X` with the
    result, so bit 7 - the "unwireable" flag - lands in the index: the magnet's
    $B3 asks for entry 11 of a seven-entry table.  WIRING (RUN.s:2050) masks
    with $70 for the same field, which is what says this is a slip and not a
    convention.  One of the two bugs pcs.md 5b fixes rather than reproduces.
    """
    sc = p.L(L_SCORE)
    sim.dscore = min(255, sim.dscore + SCORETBL[sc & 0x0F])
    snd = (sc & 0x70) >> 4
    if snd:
        dosound(sim, SOUNDTBL[snd - 1])
    return carry


def dosound(sim, code):
    """DOSOUND (RUN.s:1342) - a louder effect preempts a quieter one, and an
    idle channel is $FF, which is negative and so loses to everything."""
    if _sb(code) >= _sb(sim.series):
        sim.series = code
        sim.slice = 0


def initsound(sim):
    sim.series = 0xFF
    sim.slice = 0


# ── the part procs ──────────────────────────────────────────────────────────
# Each takes (sim, part) for a RUN or INIT proc, or (sim, part, ball) for a HIT
# proc, and a HIT proc returns the 6502's carry: True means "the ball was
# deflected", which the collision walker reads as "stop here".

def null_run(sim, p):
    """NULL (RUN.s:228)."""
    return


def null_init(sim, p):
    return


def nullbounce(sim, p, b):
    """NULLBOUNCE (RUN.s:227) - `CLC / RTS`.  The ball passes through."""
    return False


def pbounce(sim, p, b):
    """PBOUNCE - the plain reflection, with no part behaviour at all."""
    return sim.world.pbounce(b, sim.tta)


# -- bumpers (RUN.s:648) ---------------------------------------------------
def bumprun(sim, p):
    """BUMPRUN - one frame of flash, then back.  ⭐ The whole animation is a
    state byte that TSET set to $80 and two calls."""
    a = p.L(L_STATE)
    if a & 0x80:
        p.setL(L_STATE, 0)
        advance(sim, p)
    elif a:
        retreat(sim, p)


def bumpinit(sim, p):
    """BUMPINIT (RUN.s:676) - clear the armed flag, then unwind the animation."""
    a = p.L(L_STATE)
    if a & 0x80:
        p.setL(L_STATE, a & 0x7F)
    initb(sim, p)


def bumphit(sim, p, b):
    """BUMPHIT (RUN.s:668) - the World's kick, and `BC = $80`: bounce with NO
    elasticity, so a bumper returns the ball at the kick's own speed."""
    tset(p)
    bdx, bdy, did = P.bounce(sim.tta, b.bdx, b.bdy, kick=sim.world.kick,
                             elastic=False, wset3=sim.world.wset[3])
    b.bdx, b.bdy = bdx, bdy
    return putsp(sim, p, did)


def kickhit(sim, p, b):
    """KICKHIT (RUN.s:684) - a bumper only on its two slanted faces.  ⭐ `TTA`
    exactly 4 or exactly 28, which is the 45 degree entry in the non-uniform
    angle table: anywhere else the kicker is an ordinary wall."""
    if sim.tta in (4, 28):
        return bumphit(sim, p, b)
    return pbounce(sim, p, b)


# -- knockers (RUN.s:691) --------------------------------------------------
def knockrun(sim, p):
    """KNOCKRUN - out over two frames, then home in one step.

    ⭐ Bit 7 of L[8] is the DIRECTION: $80 -> $81 -> $82 on the way out, then
    the proc stores 2 and the retreats read the same low bits coming back."""
    a = p.L(L_STATE)
    if a & 0x80:
        if a == 0x82:
            p.setL(L_STATE, 2)
        else:
            advance(sim, p)
    elif a:
        retreat(sim, p)


def knock1hit(sim, p, b):
    """KNOCK1HIT (RUN.s:704) - a vertical knocker.  ⛔ It does not BOUNCE: it
    SETS BDY to the World's kick, sign taken from which way the ball was going,
    and returns carry set.  A knocker is a velocity source, not a surface.

    ⚠ `EOR #$FF` IS A COMPLEMENT AND NOT A NEGATE - the reverse kick is
    -(kick+1).  One off, deliberately or not, and reproduced either way."""
    if sim.world.bmove & P.BM_HORIZ:            # `BMI`: a sideways step
        return pbounce(sim, p, b)
    k = sim.world.kick
    b.bdy = k if (sim.world.bmove & P.BM_POS) else (k ^ 0xFF)
    tset(p)
    return putsp(sim, p, True)


def knock2hit(sim, p, b):
    """KNOCK2HIT (RUN.s:717) - the same, horizontally.  ⚠ IT READS BOTH FLAGS
    THE OTHER WAY UP: `BPL` where KNOCK1HIT has `BMI`, and `BVS` where it has
    `BVC`.  A ball moving RIGHT is kicked LEFT, and a ball moving DOWN is
    kicked UP - which is the same rule stated on the other axis."""
    if not (sim.world.bmove & P.BM_HORIZ):      # `BPL`: a vertical step
        return pbounce(sim, p, b)
    k = sim.world.kick
    b.bdx = (k ^ 0xFF) if (sim.world.bmove & P.BM_POS) else k
    tset(p)
    return putsp(sim, p, True)


# -- rollovers and targets (RUN.s:727) -------------------------------------
def flashrun(sim, p):
    """FLASHRUN - lit for one frame.  ⚠ `CMP #$80 / BNE FLSHRUN3` means any
    armed value OTHER than $80 retreats, which is how a part that was armed
    while already lit does not advance twice."""
    a = p.L(L_STATE)
    if a & 0x80:
        if a == 0x80:
            advance(sim, p)
        else:
            retreat(sim, p)
    elif a:
        retreat(sim, p)


def flashhit(sim, p, b):
    """FLASHHIT (RUN.s:737) - a target: light up, and bounce normally."""
    tset(p)
    did = pbounce(sim, p, b)
    return putsp(sim, p, did)


def rollhit(sim, p, b):
    """ROLLHIT (RUN.s:741) - a rollover: light up, score, and let it THROUGH.
    ⭐ `CLC / JMP PUTSP2` - the carry is cleared before the score is awarded
    and PUTSP2 preserves it, which is how a part can score without deflecting."""
    tset(p)
    return putsp2(sim, p, False)


# -- gates (RUN.s:745) -----------------------------------------------------
def gatehit(sim, p, b):
    """GATEHIT - solid to a ball moving one way, open to one moving the other.
    ⭐ Read off BMOVE alone: `BMI` takes the horizontal case straight to the
    bounce, and only a vertical approach in the wrong direction passes."""
    if (sim.world.bmove & P.BM_HORIZ) or (sim.world.bmove & P.BM_POS):
        return putsp(sim, p, pbounce(sim, p, b))
    return False


def gate2hit(sim, p, b):
    """GATE2HIT - one-way on the sign of BDX rather than of BMOVE."""
    if b.bdx & 0x80:
        return putsp(sim, p, pbounce(sim, p, b))
    return False


def gate3hit(sim, p, b):
    """GATE3HIT - the mirror of it."""
    if not (b.bdx & 0x80):
        return putsp(sim, p, pbounce(sim, p, b))
    return False


# -- the magnet (RUN.s:1077) -----------------------------------------------
def maghit(sim, p, b):
    """MAGHIT - solid from above and from the sides, and it EATS a ball coming
    up into it: `SEC / RTS` with no bounce at all, so the ball is reported
    blocked and never moves.  ⚠ That is the part working, not a defect."""
    if (sim.world.bmove & P.BM_HORIZ) or (sim.world.bmove & P.BM_POS):
        return putsp(sim, p, pbounce(sim, p, b))
    return True


# -- the spinner (RUN.s:1043) ----------------------------------------------
def spinrun(sim, p):
    """SPINRUN - a knocker that re-arms itself while it still has spin left.
    ⭐ L[16] is the spin counter, set by SPINHIT from the ball's speed: each
    time the animation comes to rest the spinner takes one off it, scores one
    point, and arms itself again.  That is the ratchet sound, as a state
    machine."""
    knockrun(sim, p)
    if p.L(L_STATE) != 0:
        return
    n = p.L(L_BSTAT)
    if n == 0:
        return
    p.setL(L_BSTAT, n - 1)
    p.setL(L_STATE, 0x80)
    sim.dscore = min(255, sim.dscore + 1)


def spininit(sim, p):
    p.setL(L_BSTAT, 0)
    bumpinit(sim, p)


def spinhit(sim, p, b):
    """SPINHIT (RUN.s:1067) - half the ball's vertical speed becomes the spin,
    and the ball passes straight through."""
    a = b.bdy
    if a & 0x80:
        a ^= 0xFF
    p.setL(L_BSTAT, a >> 1)
    tset(p)
    return putsp2(sim, p, False)


# -- the eating catcher (RUN.s:1021) ---------------------------------------
def catch2run(sim, p):
    """CATCH2RUN - swallow: four frames out, then straight back to rest."""
    a = p.L(L_STATE)
    if a & 0x80:
        if a == 0x84:
            p.setL(L_STATE, 0)
        else:
            advance(sim, p)


def catch2hit(sim, p, b):
    """CATCH2HIT (RUN.s:1037) - `BSTAT = $80` is "eaten"; the PLAY loop reads
    that bit and takes the ball off the table."""
    tset(p)
    b.bstat = 0x80
    return putsp(sim, p, True)


# -- the ball itself (RUN.s:1352, 600) -------------------------------------
def moveball(sim, p):
    """MOVEBALL as a part's RUN proc: unpack L[16..22], step, pack back.

    ⭐ THE BALL IS AN OBJECT LIKE ANY OTHER and that is not a flourish - it is
    what makes multiball a matter of cloning a 23-byte record.  Its TIME is 0,
    so `frame & TIME == 0` every frame."""
    if p.L(L_BSTAT) & 0x80:                 # eaten: `BMI INITQUIT`
        return
    b = sim.ball
    b.bstat = p.L(L_BSTAT)
    b.x1 = p.L(L_X1)
    b.y1 = p.L(L_Y1)
    b.bdx = p.L(L_BDX)
    b.bdy = p.L(L_BDY)
    b.bxacc = p.L(L_BXACC)
    b.byacc = p.L(L_BYACC)
    sim.hits += P.moveball(sim.world, b, sim.ptm1 & 0xFF)
    p.setL(L_BSTAT, b.bstat)
    p.setL(L_X1, b.x1)
    p.setL(L_Y1, b.y1)
    p.setL(L_BDX, b.bdx)
    p.setL(L_BDY, b.bdy)
    p.setL(L_BXACC, b.bxacc)
    p.setL(L_BYACC, b.byacc)


def initball(sim, p):
    """INITB2 (RUN.s:626) - put the ball back on its home vertex.  ⭐ L[2] is
    the template's top row and L[-5] its left column, so "home" is where the
    editor left the ball part, which is why the ball is a part you place."""
    p.setL(L_Y1, p.L(L_VERT))
    p.setL(L_X1, p.leftx)
    p.setL(L_STRIDE, 0)
    p.setL(L_BSTAT, 0)
    p.setL(L_BDX, 0)
    p.setL(L_BDY, 0xFF)


# ⭐ The part tables - PROCS, TYPES and OF_PROCS - are at the END of this
# file, because they name every proc and the last of them is written last.



# ═══════════════════════════════════════════════════════════════════════════
class Sim(object):
    """RUN.s's PLAY (line 2191) - the editor's test play, and the whole of the
    simulator's control flow.

    ⚠ NOT RUN2.s's game loop.  The original has two: this one, which the PLAY
    tool runs over the table being edited, and RUN2.s's, which adds four
    players, five balls, the bonus tally and multiball.  They share every part
    proc; what RUN2.s adds is a layer on top, and it is step 3c.
    """

    def __init__(self, pbdata, pak, wset=(0, 0, 0, 0), width=160, logic=None):
        self.pbdata = bytearray(pbdata)
        # LOGIC[24] - six three-input AND gates, {in0, in1, in2, action}.
        self.logic = list(logic or [0] * 24)
        self.world = P.World(pak, wset, width)
        self.world.dispatch = self._dohit
        self.ball = P.Ball(x=0, y=0, bdx=0, bdy=0)

        # -- PLAY (RUN.s:2191): walk pbdata and key every library object ----
        self.parts = {}                 # object index -> Part   (VLO/VHI)
        self.time = {}                  # object index -> mask   (TIME)
        self.rcn = []                   # the dense run chain    (RCN)
        self.ballobj = None
        for i, (off, ln) in enumerate(_walk(self.pbdata)):
            objid, n = self.pbdata[off], self.pbdata[off + 2]
            if objid != 3:              # ⛔ `CMP #<LIBOBJ / BNE PLAY4`
                continue
            lb = off + 3 + 2 * n
            p = Part(self.pbdata, lb, TYPES[self.pbdata[lb + L_TYPE]])
            self.parts[i] = p
            # ⭐ TIME IS LIFTED OUT OF L[8] AND L[8] IS ZEROED, so the byte the
            # editor stores as "how often does this part run" becomes the byte
            # the part animates with.  One field, two meanings, disjoint in
            # time - which is why CLOSEOBJS has to put it back.
            self.time[i] = p.L(L_STATE)
            p.setL(L_STATE, 0)
            self.rcn.append(i)
            if p.kind == 'BALL':
                self.ballobj = i
        self.world.parts = self.parts
        self.runlen = len(self.rcn)

        # GLSTY (RUN.s:2247): the last scanline that carries any span at all.
        self.lasty = 0
        for y in range(len(pak.rows) - 1, -1, -1):
            if pak.rows[y]:
                self.lasty = y
                break

        self.ptm1 = self.ptm2 = 0
        self.pdl0 = 0
        self.btn0 = self.btn1 = 0
        self.dscore = self.dbonus = self.bmult = 0
        self.score1 = [0] * 9
        self.bonus = [0] * 9
        self.series, self.slice = 0xFF, 0
        self.notes = []                 # (frame, effects index) - for the bench
        self.drawn = []                 # (frame, kind, state)   - ditto
        self.hits = 0
        self.objid = self.tta = 0
        self.frameno = 0
        # ⭐ THE BENCH'S CANNED HOST INPUT.  PLAY9 reads a paddle and two
        # triggers; the port reads a mouse and two keys.  Neither is
        # reproducible, so the bench drives all three off the frame counter by
        # the rule in `_autoinput`, which the 6809 implements identically -
        # otherwise nothing that answers to the player could be gated at all.
        self.autoinput = True

        self.initobjs(0)                # `STY INITMODE / JSR INITOBJS`

    # -- INITOBJS (RUN.s:2295) -------------------------------------------
    def initobjs(self, initmode):
        for o in self.rcn:
            p = self.parts[o]
            self.objid = o
            PROCS[p.kind][1](self, p)
            # ⭐ `BIT INITMODE / BPL` - only the CLOSING pass puts TIME back
            # into L[8].  An opening pass leaves the animation counter alone.
            if initmode & 0x80:
                p.setL(L_STATE, self.time[o])

    # -- DOHIT's tail: the part's own HIT proc ---------------------------
    def _dohit(self, p, ball, obj, tta, frame):
        self.objid, self.tta, self.frameno = obj, tta, frame
        return PROCS[p.kind][2](self, p, ball)

    # -- PLAY7..PLAY12 (RUN.s:2252): one frame ---------------------------
    def step(self):
        self.ptm1 = (self.ptm1 + 1) & 0xFF
        if self.ptm1 == 0:
            self.ptm2 = (self.ptm2 + 1) & 0xFF
        self.frameno = self.ptm1
        if self.autoinput:
            _autoinput(self)

        for i in range(self.runlen):
            o = self.rcn[i]
            if self.time[o] & self.ptm1:          # `LDA TIME,X / AND PTM1`
                continue
            p = self.parts[o]
            self.objid = o
            PROCS[p.kind][0](self, p)

            # ⭐ THE DRAIN TEST, AND IT IS ONLY ASKED OF A PART WHOSE TIME IS 0
            # - which is the ball and nothing else.  `ROL / BCS / BMI` reads
            # L[16] bit 7 as "eaten" and bit 6 as "held", and a ball whose
            # bottom row is the table's last is a ball that has drained.
            if self.time[o]:
                continue
            a = p.L(L_BSTAT)
            if a & 0xC0:
                continue
            if self.ball.y2 != self.lasty:
                continue
            p.setL(L_BSTAT, 0x80)

        if (self.ptm1 & 0x1F) == 0:
            self.score()
        if (self.ptm1 & 0x07) == 0:
            self.sound()
        if (self.ptm1 & 0x03) == 0:
            self.wiring()

    def play(self, n):
        for _ in range(n):
            self.step()

    # -- WIRING (RUN.s:2050) ---------------------------------------------
    def wiring(self):
        """⭐⭐ THE WHOLE WIRING KIT IS TWENTY-FOUR BYTES.

        Six gates, each three object indices and an action byte.  ⚠ An UNUSED
        input reads $80 and so counts as satisfied - the gate is an AND over
        however many wires were actually drawn - but a gate with no real inputs
        at all never fires.  Firing awards a bonus, may bump the multiplier,
        may make a noise, and calls each input's INIT proc, which is what
        "turning the part off" means.

        ⭐ AND THE SOUND NIBBLE IS MASKED WITH $70 HERE.  PUTSP2 does the same
        shift without the mask (RUN.s:1330); that this one has it is the
        evidence that the other is a slip.
        """
        for g in range(0, 24, 4):
            n = 0
            fired = True
            for k in range(3):
                o = self.logic[g + k]
                if o == 0:
                    continue                 # GETS2: `LDA #$80`, so satisfied
                n += 1
                p = self.parts.get(o)
                v = p.L(L_STATE) if p is not None else 0x80
                if not (v & 0x80):
                    fired = False
                    break
            if not fired or n == 0:
                continue
            act = self.logic[g + 3]
            self.dbonus = min(255, self.dbonus + _tbl('BONUSTBL')[act & 0x0F])
            if act & 0x80:                   # PRBMULT (RUN.s:1963)
                if self.bmult + 1 < 6:
                    self.bmult += 1
            snd = (act & 0x70) >> 4
            if snd:
                dosound(self, SOUNDTBL[snd - 1])
            for k in range(3):
                o = self.logic[g + k]
                if o and o in self.parts:
                    p = self.parts[o]
                    self.objid = o
                    PROCS[p.kind][1](self, p)

    # -- SCORE / DOSCORE (RUN.s:1885) ------------------------------------
    def score(self):
        """⭐ THE SCORE IS NINE DECIMAL DIGITS AND THE ADD LANDS ON DIGIT 7,
        while PRSCORE prints digits 8 down to 1 - so every score is a multiple
        of ten, exactly as the machine it is imitating."""
        _doscore(self.score1, 7, self.dscore)
        _doscore(self.bonus, 5, self.dbonus)
        self.dscore = self.dbonus = 0

    # -- SOUND (RUN.s:1978) ----------------------------------------------
    def sound(self):
        """One slice of the current effect, or silence.

        ⭐ Seven effects, each a list of indices into a table of note runs, and
        the whole thing is 108 bytes.  `SERIES` is the effect's base, `SLICE`
        the step within it, and an effect ends when the next entry is zero."""
        if self.series & 0x80:
            initsound(self)
            return
        x = (self.series + self.slice) & 0xFF
        eff = _effects()
        self.notes.append((self.ptm1, eff[x]))
        self.slice = (self.slice + 1) & 0xFF
        if eff[(x + 1) & 0xFF] == 0:
            initsound(self)


def _autoinput(sim):
    """⭐ THE ONE RULE BOTH SIDES IMPLEMENT, so the flippers and the plunger can
    be gated.  ⚠ It is the BENCH's input and not the program's: `pbauto` is set
    only by the recording mode, and a real session reads the mouse and the
    keyboard into exactly these three bytes."""
    f = sim.ptm1
    sim.pdl0 = f
    sim.btn0 = 0x80 if (f & 0x18) == 0x18 else 0
    sim.btn1 = 0x80 if (f & 0x30) == 0x30 else 0


def _walk(pbdata):
    """GETOBJ / GETNEXTOBJ (RUN2.s:1053) - the offset and length of every
    record.  ⭐ pbdata[0] is BOTH the object count and the distance from
    pbdata+1 to the first record, which is why the walk needs no index."""
    n = pbdata[0]
    off = 1 + n
    out = []
    for i in range(n):
        ln = pbdata[1 + i]
        out.append((off, ln))
        off += ln
    return out


def _doscore(digits, at, delta):
    """DOSCORE2 (RUN.s:1897) - add, then carry-propagate one digit at a time."""
    v = digits[at] + delta
    digits[at] = 255 if v > 255 else v
    y = at
    while y:
        c = 0
        while digits[y] >= 10:
            digits[y] -= 10
            c += 1
        y -= 1
        digits[y] = (digits[y] + c) & 0xFF


_EFF = None


def _effects():
    global _EFF
    if _EFF is None:
        import pcsasm as A
        b = list(A.block('RUN.s', 'EFFECTS'))
        _EFF = b + [0] * (256 - len(b))
    return _EFF


# ═══════════════════════════════════════════════════════════════════════════
def selftest():
    """⭐ THE PART PROCS, CHECKED BY THEIR BEHAVIOUR.

    Each of these is a property the original has that a transliteration error
    cannot satisfy by accident - a state machine's shape, a one-way gate's
    direction, a rollover that scores without deflecting."""
    import pcspak as K
    bad = []

    class _S(object):
        def __init__(self):
            self.drawn, self.ptm1 = [], 0
            self.dscore = self.series = 0
            self.series = 0xFF
            self.slice = 0
    sim = _S()

    def mk(kind, state=0, score=0x11):
        rec = bytearray(3 + 8 + LREC)
        p = Part(rec, 11, kind)
        p.setL(L_STATE, state)
        p.setL(L_SCORE, score)
        return p

    # -- 1  the bumper: armed, one frame out, one frame back, at rest ----
    p = mk('BMP')
    tset(p)
    seen = [p.L(L_STATE)]
    for _ in range(3):
        bumprun(sim, p)
        seen.append(p.L(L_STATE))
    if seen != [0x80, 1, 0, 0]:
        bad.append('BUMPRUN cycled %s, wanted [128, 1, 0, 0]' % seen)

    # -- 2  the knocker: TWO frames out, and the direction bit is bit 7 --
    p = mk('KNOCK1')
    tset(p)
    seen = [p.L(L_STATE)]
    for _ in range(6):
        knockrun(sim, p)
        seen.append(p.L(L_STATE))
    if seen != [0x80, 0x81, 0x82, 2, 1, 0, 0]:
        bad.append('KNOCKRUN cycled %s' % [hex(v) for v in seen])

    # -- 3  TSET does not re-arm a part that is already moving -----------
    p = mk('BMP', state=1)
    tset(p)
    if p.L(L_STATE) != 1:
        bad.append('TSET re-armed a part in mid-animation')

    # -- 4  INITB unwinds however far out the part is --------------------
    p = mk('BMP', state=5)
    initb(sim, p)
    if p.L(L_STATE) != 0:
        bad.append('INITB left the counter at %d' % p.L(L_STATE))

    # -- 5  the gates, each one-way, and each a DIFFERENT way ------------
    class _W(object):
        bmove = 0
        kick = 16
        wset = (0, 0, 0, 0)

        def pbounce(self, b, tta):
            b.bdy = (-P._sb(b.bdy)) & 0xFF
            return True
    class _Sim2(_S):
        def __init__(self):
            _S.__init__(self)
            self.world = _W()
            self.tta = 0
    s2 = _Sim2()
    b = P.Ball(x=10, y=10, bdx=5, bdy=0xF0)
    for name, bmove, want in (('down', P.BM_POS, True),
                              ('up', 0, False),
                              ('sideways', P.BM_HORIZ, True)):
        s2.world.bmove = bmove
        if gatehit(s2, mk('GATE'), b) != want:
            bad.append('GATEHIT going %s did not %s'
                       % (name, 'block' if want else 'pass'))

    # ⛔ AND THE MAGNET IS THE SAME TEST WITH THE OTHER ANSWER: it blocks a
    # ball rising into it WITHOUT bouncing, which is the part holding on.
    s2.world.bmove = 0
    if maghit(s2, mk('MAG'), b) is not True:
        bad.append('MAGHIT let a rising ball through')

    # -- 6  a rollover scores and does NOT deflect -----------------------
    s2.dscore = 0
    p = mk('ROLL', score=0x44)
    if rollhit(s2, p, b) is not False:
        bad.append('ROLLHIT deflected the ball')
    if s2.dscore != SCORETBL[4]:
        bad.append('ROLLHIT scored %d, wanted %d' % (s2.dscore, SCORETBL[4]))
    if p.L(L_STATE) != 0x80:
        bad.append('ROLLHIT did not light the rollover')

    # ⛔ ... and a part that did NOT deflect scores nothing through PUTSP.
    s2.dscore = 0
    putsp(s2, mk('TARG', score=0x55), False)
    if s2.dscore != 0:
        bad.append('PUTSP scored on a miss')

    # -- 7  the spinner ratchets down, one point a frame -----------------
    p = mk('SPIN', score=0x11)
    b2 = P.Ball(x=0, y=0, bdx=0, bdy=(-24) & 0xFF)
    s2.dscore = 0
    spinhit(s2, p, b2)
    # ⚠ 11 AND NOT 12: `BPL *+4 / EOR #$FF / LSR` is a ones' complement, so -24
    # becomes 23 and halves to 11.  The same off-by-one as the knockers' kick,
    # and reproduced for the same reason - it is what the machine did.
    if p.L(L_BSTAT) != 11:
        bad.append('SPINHIT stored %d of spin, wanted 11' % p.L(L_BSTAT))
    n, guard = 0, 0
    while p.L(L_BSTAT) or p.L(L_STATE):
        spinrun(s2, p)
        guard += 1
        if guard > 500:
            bad.append('the spinner never stopped')
            break
    # ⭐ 12: ONE for the hit itself, through PUTSP2, and then one a ratchet for
    # each of the eleven units of spin.  A spinner scores twice over.
    if s2.dscore != 12:
        bad.append('the spinner scored %d over its run, wanted 12' % s2.dscore)

    # -- 8  DOSCORE carries, and the add lands on the TENS ---------------
    d = [0] * 9
    _doscore(d, 7, 25)
    if d != [0, 0, 0, 0, 0, 0, 2, 5, 0]:
        bad.append('DOSCORE made %s of 25' % d)
    _doscore(d, 7, 80)
    if d != [0, 0, 0, 0, 0, 1, 0, 5, 0]:
        bad.append('DOSCORE carried 25+80 to %s' % d)

    # -- 9  DOSOUND: louder wins, quieter does not interrupt -------------
    s3 = _S()
    dosound(s3, 0x0C)
    dosound(s3, 0x04)
    if s3.series != 0x0C:
        bad.append('a quiet effect interrupted a loud one')
    dosound(s3, 0x4C)
    if s3.series != 0x4C:
        bad.append('a loud effect did not preempt')

    # -- 10  the launcher tracks the paddle, and FIRES on the button -----
    p = mk('LAUNCH')
    s2.btn0 = 0
    for pdl, want in ((0, 0), (0x20, 1), (0x40, 2), (0xE0, 3), (0xE0, 4)):
        s2.pdl0 = pdl
        launchrun(s2, p)
        if p.L(L_STATE) != want:
            bad.append('LAUNCHRUN at paddle $%02X reached %d, wanted %d'
                       % (pdl, p.L(L_STATE), want))
    # ⛔ AND IT STOPS AT 5, whatever the paddle says.
    s2.pdl0 = 0xFF
    for _ in range(8):
        launchrun(s2, p)
    if p.L(L_STATE) != 5:
        bad.append('LAUNCHRUN wound past its last frame to %d' % p.L(L_STATE))
    s2.btn0 = 0x80
    for _ in range(8):
        launchrun(s2, p)
    if p.L(L_STATE) != 0:
        bad.append('LAUNCHRUN did not fire back to rest')

    # ⛔ THE SHOT IS NOT A BOUNCE: with the button down and the ball above the
    # plunger, BDY is SET from the paddle and the carry comes back CLEAR.
    p = mk('LAUNCH')
    p.setL(L_VERT, 100)
    s2.btn0, s2.pdl0 = 0x80, 0xFC
    b3 = P.Ball(x=10, y=90, bdx=0, bdy=0)
    if launchhit(s2, p, b3) is not False:
        bad.append('LAUNCHHIT deflected the ball instead of launching it')
    if b3.bdy != 0x3F:
        bad.append('LAUNCHHIT launched at %d, wanted 63' % b3.bdy)

    # -- 11  the flipper sweeps up while the button is down, and back ----
    p = mk('LFLIP')
    p.setL(L_VERT, 100)
    s2.btn0 = 0x80
    seen, verts = [], []
    for _ in range(9):
        fliprun(s2, p)
        seen.append(p.L(L_STATE))
        verts.append(p.L(L_VERT))
    if seen != [1, 2, 3, 4, 5, 6, 7, 7, 7]:
        bad.append('the flipper swept %s' % seen)
    # ⭐ AND THE PART ITSELF MOVED: a flipper's art changes top row and height
    # as it sweeps, which is why the hit test has to read L[2] back.
    if len(set(verts)) < 2:
        bad.append('the flipper swept without moving its art')
    s2.btn0 = 0
    for _ in range(9):
        fliprun(s2, p)
    if p.L(L_STATE) != 0:
        bad.append('the flipper did not come back to rest')
    if p.L(L_VERT) != 100:
        bad.append('the flipper came home to row %d, not 100' % p.L(L_VERT))

    # -- 12  the drop bank: four targets in one nibble -------------------
    p = mk('DROP1')
    p.setL(L_BSTAT, 0b0101)                  # two of them struck
    droprun(s2, p)
    if p.L(L_STATE) & 0x0F != 0b0101:
        bad.append('DROPRUN dropped %s' % bin(p.L(L_STATE) & 0x0F))
    p.setL(L_BSTAT, 0b1010)
    droprun(s2, p)
    if p.L(L_STATE) & 0x0F != 0x0F:
        bad.append('DROPRUN did not complete the bank')
    # ⛔ AND THE NEXT TICK STANDS THEM ALL UP AND SETS $80, which is what the
    # wiring kit reads as "this part fired".
    droprun(s2, p)
    if p.L(L_STATE) != 0x80:
        bad.append('a completed bank came to $%02X, wanted $80' % p.L(L_STATE))

    # -- 13  the wiring kit: an AND over however many wires were drawn ---
    class _Sim3(_Sim2):
        pass
    w = _Sim3()
    w.parts = {}
    w.logic = [0] * 24
    w.dbonus = 0
    w.bmult = 0
    w.objid = 0
    for i, kind in ((1, 'TARG'), (2, 'TARG'), (3, 'TARG')):
        w.parts[i] = mk(kind, score=0x55)
    w.logic[0:4] = [1, 2, 0, 0x03]           # two wires, bonus 3, no sound
    Sim.wiring(w)
    if w.dbonus != 0:
        bad.append('a gate fired with neither input on')
    w.parts[1].setL(L_STATE, 0x80)
    Sim.wiring(w)
    if w.dbonus != 0:
        bad.append('a gate fired with only one of two inputs on')
    w.parts[2].setL(L_STATE, 0x80)
    Sim.wiring(w)
    if w.dbonus != _tbl('BONUSTBL')[3]:
        bad.append('a satisfied gate awarded %d bonus' % w.dbonus)
    # ⛔ ... and it TURNED THE PARTS OFF, by calling their INIT procs.
    if w.parts[1].L(L_STATE) or w.parts[2].L(L_STATE):
        bad.append('a fired gate left its inputs on')
    # ⛔ A GATE WITH NO WIRES AT ALL NEVER FIRES, however satisfied it looks.
    w.dbonus = 0
    w.logic[4:8] = [0, 0, 0, 0x05]
    Sim.wiring(w)
    if w.dbonus != 0:
        bad.append('an unwired gate fired')

    for m in bad:
        print('FAIL  %s' % m)
    if not bad:
        print('ok    the part procs: the bumper and knocker state machines,\n'
              '      TSET\'s guard, the three one-way gates and the magnet\'s\n'
              '      hold, a rollover that scores without deflecting, PUTSP\'s\n'
              '      carry gate, the spinner\'s ratchet, DOSCORE\'s carry and\n'
              '      DOSOUND\'s priority - and the plunger tracking the paddle,\n'
              '      the flipper sweep moving the part itself, the drop bank\'s\n'
              '      nibble, and the wiring kit as an AND over the wires that\n'
              '      were actually drawn.')
    return not bad


# ═══════════════════════════════════════════════════════════════════════════
# STEP 3b-ii: the parts the PLAYER drives, and the wiring kit.
#
# ⭐ These are the five that read the host's input - the launcher off the
# paddle, the four flippers off the two triggers - plus the two drop banks and
# the stacking catcher, which are the only parts with state beyond one byte.
# ═══════════════════════════════════════════════════════════════════════════
def _t(name, src='RUN.s'):
    return _tbl(name) if src == 'RUN.s' else None


FRAMES = ['FFRAME%d' % k for k in range(1, 9)] + \
         ['SFRAME%d' % k for k in range(1, 9)]


# ── the launcher (RUN.s:192) ──────────────────────────────────────────────
def launchrun(sim, p):
    """LAUNCHRUN - the plunger tracks the paddle until the button is pressed.

    ⭐ `PDL0 >> 5` is 0..7 and the state follows it one frame at a time, so
    pulling the plunger back IS the animation.  Pressing the button retreats it
    to rest, which is the shot.  ⚠ BTN0 bit 7 SET means pressed."""
    if sim.btn0 & 0x80:
        if p.L(L_STATE):
            retreat(sim, p)
        return
    want = sim.pdl0 >> 5
    st = p.L(L_STATE)
    if want < st:
        retreat(sim, p)
    elif want == st:
        return
    elif st < 5:
        advance(sim, p)


def launchhit(sim, p, b):
    """LAUNCHHIT (RUN.s:217) - ⛔ THE SHOT IS NOT A BOUNCE.  With the button
    down and the ball above the plunger's top row, BDY is SET from the paddle
    (`PDL0 >> 2`, so 0..63) and the proc returns carry CLEAR - the ball is not
    deflected, it is launched.  Anywhere else the plunger is an ordinary wall."""
    if (sim.btn0 & 0x80) and b.y2 < p.L(L_VERT):
        b.bdy = sim.pdl0 >> 2
        return False
    return sim.world.pbounce(b, sim.tta)


# ── the flippers (RUN.s:233) ──────────────────────────────────────────────
# ⭐ EIGHT FRAMES, AND EVERY ONE OF THEM MOVES THE PART.  A flipper's art
# changes height AND top row as it sweeps, so FXDVERT/FXHEIGHT patch L[2] and
# L[5] on the way up and FDDVERT/FHEIGHT are what the HIT proc reads back.
# ⚠ The port drops the FXLEN write into L[7]: it is the frame's BYTE LENGTH,
# which is what chained the bitmap pointer, and the port indexes its art
# instead (pcs.md 2).  L[2] and L[5] stay, because the hit test reads them.
def _flipbase(kind):
    """0 for the big flippers, 8 for the small pair - the offset into the four
    sixteen-entry tables, which hold both sizes end to end."""
    return 8 if kind in ('LFLIP2', 'RFLIP2') else 0


def _flipbtn(sim, kind):
    return sim.btn1 if kind in ('RFLIP', 'RFLIP2') else sim.btn0


def fliprun(sim, p):
    """FLIPRUN - one frame of the sweep, in whichever direction the button says."""
    base = _flipbase(p.kind)
    st = p.L(L_STATE)
    if _flipbtn(sim, p.kind) & 0x80:
        if st >= 7:
            return
        x = st + base
        p.setL(L_VERT, p.L(L_VERT) + _sb(_tbl('FXDVERT')[x + 1]))
        p.setL(L_HEIGHT, _tbl('FXHEIGHT')[x + 1])
        advance(sim, p)
        return
    if st == 0:
        return
    _flipret(sim, p, st, base)


def _flipret(sim, p, st, base):
    """FLPRUN4 - one frame back down.  ⚠ The two directions do NOT read the
    same table entries: up takes FXDVERT[x+1] and down takes FXDVERT[x], which
    is what makes the sweep reversible."""
    x = st + base
    retreat(sim, p)
    p.setL(L_VERT, p.L(L_VERT) - _sb(_tbl('FXDVERT')[x]))
    p.setL(L_HEIGHT, _tbl('FXHEIGHT')[x - 1])


def flipinit(sim, p):
    """FLIPINIT (RUN.s:297) - wind the sweep all the way back."""
    base = _flipbase(p.kind)
    n = 0
    while p.L(L_STATE):
        _flipret(sim, p, p.L(L_STATE), base)
        n += 1
        if n > 16:
            raise RuntimeError('FLIPINIT did not settle')


FWIDTH = {'LFLIP': 0, 'LFLIP2': 0, 'RFLIP2': 13, 'RFLIP': 19}


def fliphit(sim, p, b):
    """FLIPHIT (RUN.s:356).  ⭐⭐ THE ONE PART THAT IS NOT A POLYGON.

    A flipper's collision is resolved against its ART, row by row: each of the
    sixteen frames carries a list of (right, left) pairs, one per row, and the
    proc finds the row the ball is entering, reads that row's two ends, and
    only then decides whether the ball touched it at all.  ⭐ The kick is
    FLPVCTR indexed by WHERE ALONG THE FLIPPER the ball struck - which is why a
    tip shot is hard and worth it, and it is a table lookup.

    ⚠ The right-hand flippers are the same tables read backwards from FWIDTH.
    """
    base = _flipbase(p.kind)
    right = p.kind in ('RFLIP', 'RFLIP2')
    fdir = _flipbtn(sim, p.kind)
    bmove = sim.world.bmove

    # Which row, and which columns, is the ball entering?
    if not (bmove & P.BM_HORIZ):
        yt = (b.y2 + 1) if (bmove & P.BM_POS) else (b.y1 - 1)
        fx1, fx2 = b.x1, b.x2
    else:
        if bmove & P.BM_POS:
            fx1, fx2 = b.x1 + 1, b.x2 + 1
        else:
            fx1, fx2 = b.x1 - 1, b.x2 - 1
        yt = (b.y1 - 1) if (b.bdy & 0x80) else (b.y2 + 1)
    yt &= 0xFF

    frame = p.L(L_STATE)
    x = (frame + base) & 0xFF
    top = (p.L(L_VERT) + _sb(_tbl('FDDVERT')[x])) & 0xFF
    if top > yt:
        return False
    if ((top + _tbl('FHEIGHT')[x]) & 0x1FF) < yt:
        return False

    leftx = p.leftx
    rows = _tbl(FRAMES[x])
    i = ((yt - top) & 0xFF) * 2
    if i + 1 >= len(rows):
        return False

    if not right:
        a = (rows[i] + leftx) & 0xFF
        if a > fx2:
            return False
        e = (rows[i + 1] + leftx) & 0xFF
        if e < fx1:
            return False
        t = e
        yidx = (fx2 - leftx) & 0xFF
        tta = _tbl('FTTA')[x]
    else:
        w = FWIDTH[p.kind]
        a = (w - rows[i + 1] + leftx) & 0xFF
        if a > fx2:
            return False
        e = (w - rows[i] + leftx) & 0xFF
        if e < fx1:
            return False
        t = e
        yidx = (w - fx1 + leftx) & 0xFF
        tta = (32 - _tbl('FTTA')[x]) & 0xFF

    # ⭐ WHICH FACE?  A vertical approach takes the near face; a horizontal one
    # is decided by where along the row the ball met it.  X is $00 for the
    # striking face and $80 for the back, and FLIPH12 turns TTA by 16.
    if bmove & P.BM_HORIZ:
        if right:
            face = 0x80 if t < fx2 else 0x00
        else:
            face = 0x00 if t < fx2 else 0x80
    elif bmove & P.BM_POS:
        face = 0x00
    else:
        face = 0x80
    if face == 0x80:
        tta = (16 + tta) & 0xFF
        if tta >= 32:
            tta -= 32

    # FLIPH13: the kick, by position along the flipper - and only while the
    # flipper is actually sweeping.
    vec = _tbl('FLPVCTR')
    kick = vec[yidx] if yidx < len(vec) else 0
    if frame == 0 or frame == 7:
        kick = 0
    elif fdir & 0x80:
        kick = kick if face == 0x00 else 0
    else:
        kick = ((kick ^ 0xFF) + 1) & 0xFF if face == 0x80 else 0

    sim.tta = tta
    bdx, bdy, did = P.bounce(tta, b.bdx, b.bdy, kick=kick, elastic=True,
                             wset3=sim.world.wset[3])
    b.bdx, b.bdy = bdx, bdy
    return putsp(sim, p, did)


# ── the drop banks (RUN.s:761) ────────────────────────────────────────────
def droprun(sim, p):
    """DROPRUN - four targets in one part, one nibble of L[8] each.

    ⭐ L[16] is "hit since the last tick" and L[8]'s low nibble is "down".  The
    RUN proc moves the first into the second and redraws whichever fell; when
    all four are down it stands them all back up and sets L[8] to $80, which is
    what the WIRING kit reads as "this part fired"."""
    down = p.L(L_STATE) & 0x0F
    if down == 0x0F:
        for k in range(3, -1, -1):
            sim.drawn.append((sim.ptm1, p.kind, 0x80 | k))
        p.setL(L_STATE, 0x80)
        p.setL(L_BSTAT, 0)
        return
    a = (down ^ 0x0F) & p.L(L_BSTAT)         # up, and struck
    p.setL(L_STATE, p.L(L_STATE) | a)
    for k in range(3, -1, -1):
        if a & 1:
            sim.drawn.append((sim.ptm1, p.kind, k))
        a >>= 1


def dropinit(sim, p):
    a = p.L(L_STATE) & 0x0F
    for k in range(3, -1, -1):
        if a & 1:
            sim.drawn.append((sim.ptm1, p.kind, k))
        a >>= 1
    p.setL(L_STATE, 0)
    p.setL(L_BSTAT, 0)


def drophit(sim, p, b):
    """DROP1HIT / DROP2HIT (RUN.s:854).  ⭐ WHICH of the four did the ball
    strike?  The offset along the bank, against a four-entry threshold table -
    and a miss returns carry CLEAR, so the ball passes between the targets."""
    if p.kind == 'DROP1':
        a = (b.x2 - p.leftx) & 0xFF
    else:
        a = (b.y2 - p.L(L_VERT)) & 0xFF
    tbl = _tbl('DHITTBL')
    bit = 1
    for k in range(3, -1, -1):
        if a >= tbl[k]:
            p.setL(L_BSTAT, p.L(L_BSTAT) | bit)
            did = sim.world.pbounce(b, sim.tta)
            return putsp(sim, p, did)
        bit <<= 1
    return False


# ── the stacking catcher (RUN.s:917) ──────────────────────────────────────
def catch1init(sim, p):
    p.setL(L_STATE, 0)
    p.setL(L_BSTAT, 0)


def catch1hit(sim, p, b):
    """CATCH1HIT - ⭐ IT HOLDS THREE BALLS AND THEN GIVES THEM ALL BACK.

    L[16] counts what is stacked; `BSTAT = $20` is "this ball is held", and the
    ball's own MOVEBALL stops stepping it.  ⚠ CATCHSTOP is where each of the
    three comes to rest, so the stack is three fixed positions and not a queue.
    """
    bmove = sim.world.bmove
    if (bmove & P.BM_HORIZ) or not (bmove & P.BM_POS):
        return _catch1side(sim, p, b)
    if ((p.rec[p.lb - 7] + 3) & 0xFF) != b.x1:
        return _catch1side(sim, p, b)

    yt = p.L(L_VERT)
    t = p.L(L_BSTAT)
    if not (t & 0x80):
        if b.bstat & 0x40:
            return True
        p.setL(L_BSTAT, t | 0x80)
        b.bdx = 0
        b.bstat = 0x20
        putsp2(sim, p, False)
        return False

    stop = _tbl('CATCHSTOP')
    if not (t & 0x40):                       # `ROL / BMI CTCH1HIT6`
        if not (b.bstat & 0x20):
            return True
        k = t & 0x7F
        if k >= len(stop):
            return True
        if ((yt + stop[k] + 1) & 0xFF) != b.y2:
            return False
        t += 1
        k = t & 0x7F
        b.bstat = 0x40 if k != 3 else 0
        if k == 3:
            t = 0xC2
        p.setL(L_BSTAT, t)
        return True

    # CTCH1HIT6: giving them back
    if ((yt + 16) & 0xFF) != b.y2:
        return False
    if not (b.bstat & 0x40):
        return False
    t = (t - 1) & 0xFF
    if t == 0xC0:
        p.setL(L_STATE, 0)
        t = 0
    p.setL(L_BSTAT, t)
    b.bstat = 0
    return False


def _catch1side(sim, p, b):
    """CTCH1HIT3 - the catcher's walls.  ⚠ A TTA of 0 - a flat floor - is not
    bounced off at all: BDX is nudged one pixel and the ball is reported
    blocked, which is what walks it off the lip instead of sitting on it."""
    if sim.tta != 0:
        return sim.world.pbounce(b, sim.tta)
    b.bdx = 1
    return True


# ═══════════════════════════════════════════════════════════════════════════
# ⭐ THE TABLE THE PORT REPLACES `DA <RUN> / DA <INIT> / DA <HIT>` WITH.  A part
# type id at L[10] indexes it; the names are the 6502's, so a reader can follow
# a claim in RUN.s straight to the routine that answers it.
PROCS = {
    'POLY':      (null_run, null_init, pbounce),
    'BALL':      (moveball, initball, nullbounce),
    'BMP':       (bumprun, bumpinit, bumphit),
    'KICK':      (bumprun, bumpinit, kickhit),
    'KNOCK1':    (knockrun, bumpinit, knock1hit),
    'KNOCK2':    (knockrun, bumpinit, knock2hit),
    'ROLL':      (flashrun, bumpinit, rollhit),
    'TARG':      (flashrun, bumpinit, flashhit),
    'LANE':      (null_run, null_init, pbounce),
    'GATE':      (null_run, null_init, gatehit),
    'GATE2':     (null_run, null_init, gate2hit),
    'GATE3':     (null_run, null_init, gate3hit),
    'SPIN':      (spinrun, spininit, spinhit),
    'CATCH2':    (catch2run, bumpinit, catch2hit),
    'MAG':       (null_run, null_init, maghit),
    # -- step 3b-ii: the parts the PLAYER drives, and the two with state --
    'LAUNCH':    (launchrun, initb, launchhit),
    'LFLIP':     (fliprun, flipinit, fliphit),
    'RFLIP':     (fliprun, flipinit, fliphit),
    'LFLIP2':    (fliprun, flipinit, fliphit),
    'RFLIP2':    (fliprun, flipinit, fliphit),
    'DROP1':     (droprun, dropinit, drophit),
    'DROP2':     (droprun, dropinit, drophit),
    'CATCH1':    (null_run, catch1init, catch1hit),
}

# ⛔ THE ID IS THE INDEX INTO THIS TUPLE AND IT IS APPEND-ONLY.  A saved table
# stores the id, so inserting a type renumbers every table ever written - the
# same rule mktbox.py's ICON_NAMES carries for the desktop's art.
TYPES = ('POLY', 'BALL', 'BMP', 'KICK', 'KNOCK1', 'KNOCK2', 'ROLL', 'TARG',
         'LANE', 'GATE', 'GATE2', 'GATE3', 'SPIN', 'CATCH2', 'MAG',
         'LAUNCH', 'LFLIP', 'RFLIP', 'LFLIP2', 'RFLIP2', 'DROP1', 'DROP2',
         'CATCH1')
TYPEID = dict((n, i) for i, n in enumerate(TYPES))

# The 6502 proc names each type answers to, so `pcsparts.Part.run`/`.hit` can be
# mapped onto it and the 43 templates keyed automatically.
OF_PROCS = {
    ('NULL', 'NULL', 'PBOUNCE'): 'LANE',
    ('NULL', 'NULL', 'GATEHIT'): 'GATE',
    ('NULL', 'NULL', 'GATE2HIT'): 'GATE2',
    ('NULL', 'NULL', 'GATE3HIT'): 'GATE3',
    ('NULL', 'NULL', 'MAGHIT'): 'MAG',
    ('MOVEBALL', 'INITBALL', 'NULLBOUNCE'): 'BALL',
    ('BUMPRUN', 'BUMPINIT', 'BUMPHIT'): 'BMP',
    ('BUMPRUN', 'BUMPINIT', 'KICKHIT'): 'KICK',
    ('KNOCKRUN', 'BUMPINIT', 'KNOCK1HIT'): 'KNOCK1',
    ('KNOCKRUN', 'BUMPINIT', 'KNOCK2HIT'): 'KNOCK2',
    ('FLASHRUN', 'BUMPINIT', 'ROLLHIT'): 'ROLL',
    ('FLASHRUN', 'BUMPINIT', 'FLASHHIT'): 'TARG',
    ('SPINRUN', 'SPININIT', 'SPINHIT'): 'SPIN',
    ('CATCH2RUN', 'BUMPINIT', 'CATCH2HIT'): 'CATCH2',
    ('LAUNCHRUN', 'INITB', 'LAUNCHHIT'): 'LAUNCH',
    ('LFLIPRUN', 'FLIPINIT', 'LFLIPHIT'): 'LFLIP',
    ('RFLIPRUN', 'FLIPINIT', 'RFLIPHIT'): 'RFLIP',
    ('LFLIP2RUN', 'FLIP2INIT', 'LFLIP2HIT'): 'LFLIP2',
    ('RFLIP2RUN', 'FLIP2INIT', 'RFLIP2HIT'): 'RFLIP2',
    ('DROP1RUN', 'DROP1INIT', 'DROP1HIT'): 'DROP1',
    ('DROP2RUN', 'DROP2INIT', 'DROP2HIT'): 'DROP2',
    ('NULL', 'CATCH1INIT', 'CATCH1HIT'): 'CATCH1',
}


def kind_of(part):
    """The port's type id for one of pcsparts.py's 43 templates.

    ⭐ Keyed off the 6502 PROC NAMES, so a template whose behaviour the port has
    not implemented answers None rather than being silently mis-keyed."""
    return OF_PROCS.get((part.run, part.init, part.hit))


if __name__ == '__main__':
    import pcsparts
    okc = bad = 0
    for p in pcsparts.parts():
        if not p.lib:
            continue
        k = kind_of(p)
        if k is None:
            continue
        if k not in PROCS:
            print('FAIL  %s maps to %s, which has no procs' % (p.name, k))
            bad += 1
        else:
            okc += 1
    print('ok    %d of the 43 templates are keyed to a port part type' % okc)
    if not selftest():
        bad += 1
    sys.exit(1 if bad else 0)
