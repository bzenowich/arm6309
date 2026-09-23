#!/usr/bin/env python3
"""checkpcs.py - the span database the machine built, against the 6502's.

    python3 video3/bench/checkpcs.py OUTDIR

⭐⭐ THE GATE IS THE PICTURE, AND THE PICTURE IS THE DATABASE.  `pcs 0` builds
the four-object test table `mkpcs.test_table()` defines, runs pcspak.inc's scan
converter over it and paints the result with pcsdraw.inc.  This builds the SAME
four objects through `pcspak.py` - the transliteration of PPAK.s, written from
the 6502 and never adjusted to match the 6809 - renders them the way
pcsdraw.inc does, and compares every byte of the table rectangle.

A misread slope, a span off by one, a vertex classified as a chain where it
should have been a start, a B-polygon stored the wrong way round: none of them
survives this.  It is checkscroll.py's pattern - walk the same path in Python,
compare everything - applied to a scan converter instead of a ring.

⛔ THE MODEL IS NEVER CORRECTED TO AGREE.  When it and the 6809 differ, the
6502 decides and the fix goes wherever it was misread.  A model tuned until it
passes is the check answering its own question - CLAUDE.md's HOSTMAP trap.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mkpcs                                                   # noqa: E402
import pcsphys                                                 # noqa: E402
import pcspak as K                                             # noqa: E402
import pcspal                                                  # noqa: E402

STRIDE = 1024           # the card's VRAM row stride - plan 4
VRAMSZ = 512 * 1024


def expected():
    """The table as PPAK.s would build it, at card resolution.

    ⭐ Doubling the world render is EXACT rather than approximate: PCFill sets
    dcol = 2*xl and dlen = 2*xr + 2 - 2*xl, so a world span [xl..xr] covers card
    columns [2*xl .. 2*xr+1] and a world row y covers card rows 2y and 2y+1 -
    which is what WADV 01's second trigger paints.
    """
    objs = mkpcs.test_table()
    pak = K.Pak(height=mkpcs.TH, width=mkpcs.TW)
    pak.objs = objs
    pak.display()

    colours = [o.fillcolor for o in objs]
    world = K.render(pak, colours, mkpcs.TW, mkpcs.TH)

    s = mkpcs.SCALE
    w, h = mkpcs.TW * s, mkpcs.TH * s
    fb = bytearray(w * h)
    for y in range(mkpcs.TH):
        row = bytearray(w)
        for x in range(mkpcs.TW):
            v = world[y * mkpcs.TW + x]
            row[x * s:x * s + s] = bytes([v]) * s
        for k in range(s):
            fb[(y * s + k) * w:(y * s + k) * w + w] = row
    return pak, fb, w, h


def trajectory(vram, pak, n=600, row=490):
    """⭐⭐ THE BALL, FRAME FOR FRAME, AGAINST A TRANSLITERATION OF RUN.s.

    This is the claim the whole port is built on.  Because the world stayed in
    the Atari's own units, the simulation is exact integer arithmetic - so the
    model can be run over the SAME table from the SAME seven bytes and required
    to produce the same (x, y, bdx, bdy) on every one of 600 frames.

    Not "the ball looks right".  A reflection off by one unit, an elasticity
    table entered at the wrong offset, a gravity mask applied on the wrong
    tick, a slope nibble read from the wrong end of a record: none of them
    survives six hundred frames of this.
    """
    w = pcsphys.World(pak, wset=mkpcs.WSET, width=mkpcs.TW)
    b = pcsphys.Ball(x=mkpcs.BALL[0], y=mkpcs.BALL[1],
                     bdx=mkpcs.BALL[2], bdy=mkpcs.BALL[3])
    got = bytes(x for r in range(0, (n * 4 + 1023) // 1024 + 1)
                for x in vram[(row + r) * STRIDE:(row + r) * STRIDE + 1024])

    hits = 0
    for f in range(1, n + 1):
        hits += pcsphys.moveball(w, b, f)
        i = (f - 1) * 4
        m = (b.x1, b.y1, b.bdx, b.bdy)
        g = tuple(got[i:i + 4])
        if g != m:
            print('FAIL  the ball diverges at frame %d of %d' % (f, n))
            print('      machine  x=%3d y=%3d bdx=%4d bdy=%4d'
                  % (g[0], g[1], pcsphys._sb(g[2]), pcsphys._sb(g[3])))
            print('      RUN.s    x=%3d y=%3d bdx=%4d bdy=%4d'
                  % (m[0], m[1], pcsphys._sb(m[2]), pcsphys._sb(m[3])))
            if f > 1:
                p = tuple(got[i - 4:i])
                print('      (the frame before, both agreed: x=%3d y=%3d '
                      'bdx=%4d bdy=%4d)'
                      % (p[0], p[1], pcsphys._sb(p[2]), pcsphys._sb(p[3])))
            return False
    print('    the ball agrees with RUN.s for all %d frames, %d hits' % (n, hits))
    # ⛔ A ball that never moved would agree trivially.  It has to have BOUNCED.
    if hits < 2:
        print('FAIL  the ball hit something only %d times - the run proves nothing'
              % hits)
        return False
    return True


def main():
    if len(sys.argv) < 2:
        print('usage: checkpcs.py OUTDIR')
        return 1
    d = sys.argv[1]
    path = os.path.join(d, 'vram.bin')
    if not os.path.isfile(path):
        print('FAIL  no vram.bin in %s' % d)
        return 1
    with open(path, 'rb') as f:
        vram = f.read()
    if len(vram) < VRAMSZ:
        print('FAIL  vram.bin is %d bytes, wanted %d' % (len(vram), VRAMSZ))
        return 1

    pak, want, w, h = expected()

    # ⭐⭐ THE DATABASE FIRST, because it is what the hit test and the ball
    # actually read - and because a picture can be right for the wrong reason.
    if not _database(vram, pak):
        return 1

    # A quick sanity line before the comparison, so a run that painted NOTHING
    # is distinguishable from one that painted the wrong thing.
    painted = sum(1 for y in range(h) for x in range(w)
                  if vram[y * STRIDE + x])
    print('    the table is %d x %d card pixels; %d of them are not index 0'
          % (w, h, painted))
    if painted == 0:
        print('FAIL  the machine painted nothing at all')
        return 1

    bad = 0
    first = None
    byrow = {}
    for y in range(h):
        base = y * STRIDE
        for x in range(w):
            got = vram[base + x]
            exp = want[y * w + x]
            if got != exp:
                bad += 1
                byrow[y] = byrow.get(y, 0) + 1
                if first is None:
                    first = (x, y, got, exp)

    total = w * h
    if bad:
        print('FAIL  %d of %d bytes differ (%.3f %%)' % (bad, total, 100.0 * bad / total))
        x, y, got, exp = first
        print('      first at card (%d, %d) - world (%d, %d): got %d, wanted %d'
              % (x, y, x // mkpcs.SCALE, y // mkpcs.SCALE, got, exp))
        rows = sorted(byrow.items(), key=lambda kv: -kv[1])[:6]
        print('      worst rows: ' + ', '.join('%d (%d)' % r for r in rows))
        _dump(vram, want, w, y)
        return 1

    # ⭐ and the ball, when this run was one that played
    if len(sys.argv) > 2 and sys.argv[2] == 'ball':
        if not trajectory(vram, pak):
            return 1
    print('ok    all %d bytes of the table are what PPAK.s builds' % total)
    print('      %d objects, %d scanlines carrying spans'
          % (len(pak.objs), sum(1 for r in pak.rows if r)))
    return 0


def _database(vram, pak):
    """pbdx and every span record, against pcspak.py's.

    The machine writes them to VRAM rows 500+ (PCDump, pcsdraw.inc) where the
    raster never looks.  ⭐ This is the real gate: two objects whose spans are
    swapped paint identically when their colours match, and the collision world
    would still be wrong.
    """
    base = 500 * STRIDE
    gotdx = list(vram[base:base + pak.TH])
    wantdx = [len(r) * 4 for r in pak.rows]
    if gotdx != wantdx:
        n = sum(1 for a, b in zip(gotdx, wantdx) if a != b)
        i = next(k for k, (a, b) in enumerate(zip(gotdx, wantdx)) if a != b)
        print('FAIL  pbdx differs on %d of %d scanlines' % (n, pak.TH))
        print('      first at scanline %d: the machine says %d bytes, PPAK.s says %d'
              % (i, gotdx[i], wantdx[i]))
        lo = max(0, i - 3)
        print('      drew %s' % gotdx[lo:i + 6])
        print('      want %s' % wantdx[lo:i + 6])
        return False

    recs = bytearray()
    for r in pak.rows:
        for (xl, obj, xr, sl) in r:
            recs += bytes((xl, obj, xr, sl))
    got = vram[(500 + 1) * STRIDE:]
    got = bytes(b for row in range(0, (len(recs) + 1023) // 1024 + 1)
                for b in vram[(501 + row) * STRIDE:(501 + row) * STRIDE + 1024])
    got = got[:len(recs)]
    if got != recs:
        i = next(k for k in range(len(recs)) if got[k] != recs[k])
        print('FAIL  the span records differ at byte %d of %d' % (i, len(recs)))
        j = (i // 4) * 4
        print('      drew %s' % ' '.join('%3d' % b for b in got[j:j + 12]))
        print('      want %s' % ' '.join('%3d' % b for b in recs[j:j + 12]))
        print('      (a record is x_left, object, x_right, slopes)')
        return False
    print('    the database matches: %d scanlines carry spans, %d records'
          % (sum(1 for r in pak.rows if r), len(recs) // 4))
    return True


def _dump(vram, want, w, y):
    """⭐ RENDER BOTH BANDS AND LOOK.  CLAUDE.md's rule: trace when the symptom
    is control flow, look at the data when it is a wrong answer of the right
    shape - and a scan converter's failures are always the second kind."""
    print('      row %d, columns 0..119, as drawn and as wanted:' % y)
    for name, src, stride in (('drew', vram, STRIDE), ('want', want, w)):
        line = ''.join('.' if src[y * stride + x] == 0 else
                       '#' if src[y * stride + x] < 16 else '+'
                       for x in range(min(120, w)))
        print('        %s %s' % (name, line))


if __name__ == '__main__':
    sys.exit(main())
