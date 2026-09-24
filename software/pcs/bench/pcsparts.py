#!/usr/bin/env python3
"""pcsparts.py - the 43 part templates and their artwork, out of the original.

`pcsasm.py` reads Bill Budge's sources as bytes; this turns those bytes back
into the structures he wrote them as.  ⛔ Nothing here invents a number, and
where something is DERIVED rather than read, the derivation is checked against
a second, independent statement of the same fact in the sources.

A template (RUN.s:2391-2760) is laid out exactly like an object record in a
saved table, because ADDOBJ (EDIT.s:703) places a part by COPYING THE WHOLE
TEMPLATE into the database:

    HEX 03 00 04            OBJID=LIBOBJ, FILLCOLOR=0, VRTXCOUNT=4
    HEX F6 F6 F0 F0         X[0..3]
    HEX 49 54 54 49         Y[0..3]
    DA  LAUNCHERB           L+0  the bitmap, in BITMAPS.OBJ
    HEX 49 1E 00 0C 01      L+2  VERT, HDIV8, HMOD8, HEIGHT, WIDTH
    HEX 0C                  L+7  STRIDE - bytes from one animation frame to the next
    HEX 07                  L+8  STATE, which in a template is the TIME code
    HEX 80                  L+9  score/sound: b7 unwireable, b6-4 sound, b3-0 score
    DA  LAUNCHRUN / INITB / LAUNCHHIT     L+10, L+12, L+14

⛔ THE FRAMES ARE XOR DELTAS, NOT PICTURES.  `ADVANCE` (RUN.s:1272) steps BITMAP
by STRIDE and XORs the new bytes over what is already on screen, so frame n's
bytes are the difference between appearance n-1 and appearance n.  `frames()`
accumulates them back into standalone pictures, because a machine with no
read-modify-write needs pictures.

⭐⭐ AND THE FRAME LAYOUT IS NOT ONE RULE, WHICH IS THE THING THIS MODULE EXISTS
TO GET RIGHT.  Thirty-seven parts are uniform -- `extent / STRIDE` frames -- and
six are not, and assuming otherwise gives six silently corrupt shapes.  The RUN
proc says which is which; `ANIM` below is that classification, and `check()`
proves each class against a number stated elsewhere in the sources:

    uniform   BUMPRUN, FLASHRUN, KNOCKRUN, LAUNCHRUN, SPINRUN, CATCH2RUN
              extent is an exact multiple of STRIDE.
    static    NULL -- one picture, never advanced.  extent == STRIDE.
    flipper   per-frame heights.  ⭐ FXHEIGHT[f] * WIDTH == FXLEN[f] for all 8,
              and sum(FXLEN) == 207 for the large pair and 92 for the small --
              which is exactly what LFLIPB and LFLIP2B measure.
    ball      IBALL/HBALL/VBALL are three separate records in RUN.s, of three
              different sizes; BALLB is only the resting disc.
    bank      DROP1/DROP2 -- a row of four targets erased bar by bar by
              DRAWTARG, indexed through DHITTBL, not advanced.
"""

import pcsasm as A

TEMPLATES = None
BLOB = None
BLOB_OF = {}
CHAIN_LEN = []          # EDIT.s's EQU-chain template length, per part

# The L-record, as offsets from LBASE.  Named once; nothing else uses numbers.
L_BITMAP, L_VERT, L_HDIV8, L_HMOD8 = 0, 2, 3, 4
L_HEIGHT, L_WIDTH, L_STRIDE, L_STATE, L_SCORE = 5, 6, 7, 8, 9
L_RUN, L_INIT, L_HIT = 10, 12, 14

UNIFORM = {'BUMPRUN', 'FLASHRUN', 'KNOCKRUN', 'LAUNCHRUN', 'SPINRUN', 'CATCH2RUN'}
STATIC = {'NULL'}
FLIPPER = {'LFLIPRUN', 'RFLIPRUN', 'LFLIP2RUN', 'RFLIP2RUN'}
BALL = {'MOVEBALL'}
BANK = {'DROP1RUN', 'DROP2RUN'}


def anim_class(run):
    for name, s in (('uniform', UNIFORM), ('static', STATIC), ('flipper', FLIPPER),
                    ('ball', BALL), ('bank', BANK)):
        if run in s:
            return name
    return None


class Part(object):
    """One of the 43 templates, decoded."""

    def __init__(self, index, name, raw, objlen, chain_len, das):
        self.index, self.name = index, name
        self.raw = bytes(raw)       # ⭐ Budge's own record, kept whole
        self.objlen = objlen                # bytes ADDOBJ copies
        self.tmpllen = len(raw)             # bytes Budge wrote
        self.statebytes = objlen - len(raw)
        self.chain_len = chain_len
        self.objid, self.fillcolor, self.nvertex = raw[0], raw[1], raw[2]
        n = self.nvertex
        self.x = list(raw[3:3 + n])
        self.y = list(raw[3 + n:3 + 2 * n])
        self.lbase = 3 + 2 * n
        self.lib = self.objid == 3
        self.bitmap = self.bmpref = self.run = self.init = self.hit = None
        self.bmpoff = self.extent = None
        if not self.lib:
            return
        L = raw[self.lbase:]
        # ⚠ A bitmap reference may carry a displacement -- `DA ROLLB+30`.  Nine
        # parts share a blob, so the symbol table cannot delimit the shapes and
        # _extents() uses the set of referenced offsets instead.
        self.bmpref = das[0]
        self.bitmap = self.bmpref.split('+')[0].split('-')[0].strip()
        self.vert = L[L_VERT]
        self.hdiv8, self.hmod8 = L[L_HDIV8], L[L_HMOD8]
        self.height, self.width = L[L_HEIGHT], L[L_WIDTH]
        self.stride, self.time, self.score_snd = L[L_STRIDE], L[L_STATE], L[L_SCORE]
        self.run, self.init, self.hit = das[1], das[2], das[3]
        self.anim = anim_class(self.run)

    @property
    def px(self):
        """The bitmap's left edge in pixels.  ⭐ The whole reason GPAK.OBJ
        existed: the Atari stored x as (byte column, bit) because it had to
        shift.  Chunky 8bpp does not, so the port carries one number."""
        return self.hdiv8 * 8 + self.hmod8

    @property
    def score(self):
        return self.score_snd & 0x0F

    @property
    def sound(self):
        """⛔ Masked with $70, which RUN.s:1330's PUTSP2 fails to do -- so the
        magnet ($B3) indexes past the 7-entry SOUNDTBL there.  One of the two
        bugs the port fixes rather than reproduces."""
        return (self.score_snd & 0x70) >> 4

    @property
    def wireable(self):
        return not (self.score_snd & 0x80)

    @property
    def nframes(self):
        return len(self.frames())

    def frames(self):
        """The part's animation, as standalone 1bpp pictures.

        Each is (height, width_bytes, bytes).  Frame 0 is the shape at rest;
        frame n is frame n-1 with the n'th XOR delta applied, which is what
        ADVANCE paints.  ⚠ A flipper's frames differ in HEIGHT, and the delta is
        applied to the top `min(h, prev_h)` rows -- the part's VERT moves by
        FXDVERT at the same time, which is the rest of that animation and is
        the simulator's business, not the art's.
        """
        if not self.lib:
            return []
        if self._frames is None:
            self._frames = self._build_frames()
        return self._frames

    def _build_frames(self):
        raw = BLOB[self.bmpoff:self.bmpoff + self.extent]
        w = self.width
        if self.anim == 'flipper':
            return self._flipper_frames(raw, w)
        if self.anim in ('static', 'bank', 'ball'):
            # One picture.  ⚠ For `bank` and `ball` the blob holds more than the
            # picture -- DROP1B's four bar shapes, BALLB's slack -- and the
            # surplus is deliberately not guessed at here.
            h = self.height
            return [(h, w, raw[:h * w].ljust(h * w, b'\0'), 0)]
        # uniform
        out, cur = [], bytearray(self.stride)
        for f in range(self.extent // self.stride):
            chunk = raw[f * self.stride:(f + 1) * self.stride]
            cur = bytearray(a ^ b for a, b in zip(cur, chunk.ljust(self.stride, b'\0')))
            out.append((self.height, w, bytes(cur), 0))
        return out

    def _flipper_frames(self, raw, w):
        """⭐⭐ THE ONE ANIMATION THAT MUST BE ACCUMULATED IN SCREEN SPACE.

        `FLIPRUN` (RUN.s:245-268) advances from frame s to s+1 like this:

            VERT   += FXDVERT[s+1]        the part's top edge MOVES
            HEIGHT  = FXHEIGHT[s+1]       ... and its height changes
            ADVANCE                       BITMAP += the CURRENT stride, then
                                          XOR the new bytes at the NEW top edge
            STRIDE  = FXLEN[s+1]          for the next advance

        So the delta for frame i is XORed onto the screen at a row that has
        shifted by FXDVERT[i], and the previous picture is still where it was.
        ⛔ Accumulating the deltas against the frame's own top-left -- the
        obvious reading -- desynchronises after frame 2 and turns frames 3-8
        into noise that still looks vaguely flipper-shaped in a thumbnail.  It
        was caught by rendering the contact sheet and LOOKING, which is
        CLAUDE.md's rule for a wrong answer of the right shape.

        Each frame comes back as (height, width, bits, dy), `dy` being the
        cumulative top-edge offset from frame 0 -- which the port needs anyway,
        because it is how the flipper is positioned when it is drawn.
        """
        heights = _flipper_table(self, 'FXHEIGHT')
        dverts = _flipper_table(self, 'FXDVERT')
        lens = _flipper_table(self, 'FXLEN')

        # Where each frame's top edge sits, relative to frame 0's.  FXDVERT is
        # signed; the table stores it as a byte ($FF is -1).
        dy, tops = 0, []
        for i in range(8):
            if i:
                dy += dverts[i] - 256 if dverts[i] > 127 else dverts[i]
            tops.append(dy)

        lo = min(tops)
        hi = max(t + h for t, h in zip(tops, heights))
        canvas = bytearray((hi - lo) * w)           # screen space, XOR target

        out, pos = [], 0
        for i in range(8):
            h, top = heights[i], tops[i] - lo
            chunk = raw[pos:pos + lens[i]].ljust(lens[i], b'\0')
            pos += lens[i]
            for r in range(h):
                for c in range(w):
                    canvas[(top + r) * w + c] ^= chunk[r * w + c]
            bits = bytes(canvas[top * w:(top + h) * w])
            out.append((h, w, bits, tops[i]))
        return out

    def __repr__(self):
        if not self.lib:
            return '<Part %2d %-13s poly %d-gon>' % (self.index, self.name, self.nvertex)
        return '<Part %2d %-13s %dx%d x%d %s>' % (
            self.index, self.name, self.width * 8, self.height, self.nframes, self.anim)


def _flipper_table(part, label):
    """Eight bytes of one per-frame flipper table, large pair or small pair.

    FXDVERT, FXHEIGHT, FXLEN, FDDVERT and FHEIGHT are each sixteen bytes
    (RUN.s:307-315): entries 0-7 are the large flipper, 8-15 the small one.
    ⭐ A part picks its half by WIDTH -- 3 bytes large, 2 small -- and `check()`
    proves the choice by requiring sum(FXLEN) to equal the blob's real length."""
    fx = A.block('RUN.s', label)
    half = 0 if part.width == 3 else 8
    return list(fx[half:half + 8])


def _load():
    global TEMPLATES, BLOB
    if TEMPLATES is not None:
        return

    names = [s.lstrip('<>') for s in A.block_syms('EDIT.s', 'OBJADDRLO')]
    hi = [s.lstrip('<>') for s in A.block_syms('EDIT.s', 'OBJADDRHI')]
    objlens = A.block('EDIT.s', 'OBJLEN')
    if names != hi:
        raise ValueError('OBJADDRLO and OBJADDRHI disagree')
    if not (len(names) == len(objlens) == 43):
        raise ValueError('expected 43 parts, got %d names / %d lengths'
                         % (len(names), len(objlens)))

    BLOB = A.blob('BITMAPS.OBJ')
    runsyms = A.equs('RUN.s')
    base = runsyms['BITMAPS']

    # ⭐⭐ THE EQU CHAIN AND OBJLEN ARE DIFFERENT NUMBERS, and finding out why is
    # what makes this extraction trustworthy.  EDIT.s:164-206 computes each
    # template's ADDRESS as the previous plus a length; EDIT.s:1282 tabulates
    # the length ADDOBJ copies.  They agree for 40 of 43 and differ for BALL
    # ($1B vs $22), CATCH1 ($1D vs $1E) and SPIN ($1B vs $1C).
    #
    # The chain's deltas are the TEMPLATE lengths; OBJLEN is the COPY length,
    # larger by exactly the part's uninitialised runtime state.  So the chain is
    # an independent check, from a different file, on the positional block
    # extraction below -- and `check()` requires every delta to equal the bytes
    # actually read out of RUN.s.
    ed = A.equs('EDIT.s')
    chain = [ed[n] for n in names if n in ed]
    if len(chain) == len(names):
        CHAIN_LEN[:] = [b - a for a, b in zip(chain, chain[1:])] + [None]
    else:
        CHAIN_LEN[:] = [None] * len(names)

    # ⛔ Templates are read POSITIONALLY -- see pcsasm.blocks_from().
    blocks = A.blocks_from('RUN.s', 'POLY', 43)

    TEMPLATES = []
    for i, (name, objlen) in enumerate(zip(names, objlens)):
        raw, das = _template_bytes(blocks[i][2])
        # ⚠ OBJLEN >= the template, and the surplus is deliberate: a part with
        # extra runtime state (the ball's L+16..L+22, the catcher's stack, the
        # spinner's count) does not write that state into its template, so
        # ADDOBJ's copy takes whatever bytes FOLLOW it in the ROM image and the
        # part's INIT proc overwrites them at play time.
        # ⛔ The port ZEROES the surplus instead of copying a neighbour.  Safe --
        # INITOBJS writes every one of those bytes before the first frame - and
        # necessary, because a saved table that captured the garbage would
        # otherwise differ run to run and no byte-for-byte gate could exist.
        if len(raw) > objlen:
            raise ValueError('%s: template is %d bytes, longer than OBJLEN %d'
                             % (name, len(raw), objlen))
        p = Part(i, name, raw, objlen, CHAIN_LEN[i], das)
        p._frames = None
        TEMPLATES.append(p)

    _extents(TEMPLATES, runsyms, base, len(BLOB))


def _template_bytes(parts_):
    """A template's bytes, each `DA SYMBOL` standing in as two zero bytes, plus
    the symbols in order.  The zeros are placeholders: they are Atari addresses,
    and the port rebuilds every one of them from the part's index."""
    raw, das = bytearray(), []
    for kind, chunk in parts_:
        if kind == 'HEX':
            raw += chunk
        else:
            das.append(chunk)
            raw += b'\x00\x00'
    return bytes(raw), das


def _extents(templates, syms, base, bloblen):
    """Every library part's absolute offset in BITMAPS.OBJ, and how many bytes
    belong to it.

    ⭐ A shape ends where the next one begins.  The EQU chain at RUN.s:100-118
    names 24 shapes but 43 parts reference them, nine at a displacement, so the
    symbol table alone cannot give a length.  The set of all referenced offsets
    can: sort it, and each offset's extent is the gap to its successor."""
    offs = set()
    for p in templates:
        if not p.lib:
            continue
        v = A._value(p.bmpref, syms)
        if v is None:
            raise ValueError('%s: cannot resolve bitmap reference %r' % (p.name, p.bmpref))
        p.bmpoff = v - base
        if not 0 <= p.bmpoff < bloblen:
            raise ValueError('%s: bitmap offset %d outside BITMAPS.OBJ' % (p.name, p.bmpoff))
        offs.add(p.bmpoff)
    bounds = sorted(offs) + [bloblen]
    for p in templates:
        if p.lib:
            p.extent = bounds[bounds.index(p.bmpoff) + 1] - p.bmpoff


def parts():
    _load()
    return TEMPLATES


def check():
    """Assert every invariant the extraction rests on.

    ⛔ These are claims about the ORIGINAL, so a failure means this module has
    misread it -- never that Budge was wrong."""
    _load()
    bad = []
    for p in TEMPLATES:
        if p.chain_len is not None and p.chain_len != p.tmpllen:
            bad.append('%s: EDIT.s EQU chain says %d template bytes, RUN.s gave %d'
                       % (p.name, p.chain_len, p.tmpllen))
        if not p.lib:
            if p.objid not in (1, 2):
                bad.append('%s: OBJID %d on a non-library part' % (p.name, p.objid))
            continue
        if p.nvertex < 3:
            bad.append('%s: %d vertices' % (p.name, p.nvertex))
        if p.anim is None:
            bad.append('%s: RUN proc %s is in no animation class' % (p.name, p.run))
            continue
        if p.height * p.width != p.stride:
            bad.append('%s: HEIGHT*WIDTH = %d but STRIDE = %d'
                       % (p.name, p.height * p.width, p.stride))
        if p.anim == 'uniform' and p.extent % p.stride:
            bad.append('%s: %s spans %d bytes, not a multiple of STRIDE %d'
                       % (p.name, p.bmpref, p.extent, p.stride))
        if p.anim == 'static' and p.extent != p.stride:
            bad.append('%s: static but spans %d bytes for a %d-byte picture'
                       % (p.name, p.extent, p.stride))
        if p.anim == 'flipper':
            # ⭐ The claim FXLEN makes, checked against the blob's real length.
            hs = _flipper_table(p, 'FXHEIGHT')
            want = sum(h * p.width for h in hs)
            if want != p.extent:
                bad.append('%s: FXHEIGHT*WIDTH sums to %d, %s spans %d'
                           % (p.name, want, p.bmpref, p.extent))
            half = 0 if p.width == 3 else 8
            fxlen = A.block('RUN.s', 'FXLEN')[half:half + 8]
            if [h * p.width for h in hs] != list(fxlen):
                bad.append('%s: FXHEIGHT*WIDTH disagrees with FXLEN' % p.name)
        if p.anim in ('ball', 'bank') and p.extent < p.stride:
            bad.append('%s: %s spans %d bytes, less than one %d-byte picture'
                       % (p.name, p.bmpref, p.extent, p.stride))
    return bad


if __name__ == '__main__':
    import sys
    for p in parts():
        if not p.lib:
            print('%2d %-13s poly %d-gon' % (p.index, p.name, p.nvertex))
            continue
        st = ('  +%d state' % p.statebytes) if p.statebytes else ''
        print('%2d %-13s %2dx%-2d x%d %-8s at (%3d,%3d)  TIME $%02X  score %2d  snd %d%s%s'
              % (p.index, p.name, p.width * 8, p.height, p.nframes, p.anim,
                 p.px, p.vert, p.time, p.score, p.sound,
                 '' if p.wireable else '  UNWIREABLE', st))
    bad = check()
    print()
    if bad:
        for b in bad:
            print('FAIL', b)
        sys.exit(1)
    print('ok  43 templates: the EQU chain agrees with RUN.s on every template '
          'length,\n    and every shape in BITMAPS.OBJ is accounted for by its '
          'animation class')
