#!/usr/bin/env python3
"""checkpcs.py - the span database the machine built, against the 6502's.

    python3 software/pcs/bench/checkpcs.py OUTDIR

⭐⭐ THE GATE IS THE PICTURE, AND THE PICTURE IS THE DATABASE.  `pcs 0` builds
the four-object test table `mkpcs.test_table()` defines, runs pcspak.inc's scan
converter over it and paints the result with pcsdraw.inc.  This builds the SAME
four objects through `pcspak.py` - the transliteration of PPAK.s, written from
the 6502 and never adjusted to match the 6809 - renders them the way
pcsdraw.inc does, and compares every byte of the table rectangle.

A misread slope, a span off by one, a vertex classified as a chain where it
should have been a start, a B-polygon stored the wrong way round: none of them
survives this.  It is checktilescroll.py's pattern - walk the same path in Python,
compare everything - applied to a scan converter instead of a ring.

⛔ THE MODEL IS NEVER CORRECTED TO AGREE.  When it and the 6809 differ, the
6502 decides and the fix goes wherever it was misread.  A model tuned until it
passes is the check answering its own question - CLAUDE.md's HOSTMAP trap.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mkpcs                                                   # noqa: E402
import pcsedit                                                 # noqa: E402
import pcsobj                                                  # noqa: E402
import pcsphys                                                 # noqa: E402
import pcspak as K                                             # noqa: E402
import pcspal                                                  # noqa: E402

STRIDE = 1024           # the card's VRAM row stride - plan 4
VRAMSZ = 512 * 1024


def expected(parts=None):
    """The table as PPAK.s builds it and the card shows it, at card resolution.

    ⭐ Doubling the world render is EXACT rather than approximate: PCFill sets
    dcol = 2*xl and dlen = 2*xr + 2 - 2*xl, so a world span [xl..xr] covers card
    columns [2*xl .. 2*xr+1] and a world row y covers card rows 2y and 2y+1 -
    which is what WADV 01's second trigger paints.

    ⭐ And then every library part's picture goes on top, because its polygon is
    UNFILLED and draws nothing: the span database is the collision world and the
    1bpp frame is the picture (pcs.md 2, 4).
    """
    objs = mkpcs.test_table()
    pak = K.Pak(height=mkpcs.TH, width=mkpcs.TW)
    pak.objs = objs
    pak.display()
    fb, w, h = mkpcs.render_table(pak, objs, parts)
    return pak, fb, w, h


PLAYR, PLAYS, PLAYT, PLAYD = 490, 494, 495, 496
EDITR, EDITO = 498, 505


def _stream(vram, row, n):
    """`n` bytes of a VRAM stream, reassembled across its rows.

    ⛔ The pointer's auto-increment does not carry out of a VRAM row, so pcs
    repositions every 1,024 bytes and the stream has to be read the same way.
    """
    out = bytearray()
    r = row
    while len(out) < n:
        out += vram[r * STRIDE:r * STRIDE + 1024]
        r += 1
    return bytes(out[:n])


def trajectory(vram, pak, n=600):
    """⭐⭐ THE WHOLE SIMULATOR, FRAME FOR FRAME, AGAINST A TRANSLITERATION.

    This is the claim the port is built on.  Because the world stayed in the
    Atari's own units, everything here is exact integer arithmetic - so the
    model runs the SAME table through the SAME PLAY loop and is required to
    produce the same ball, the same part states, the same score and the same
    sound state.

    Not "the ball looks right".  A reflection off by one unit, an elasticity
    table entered at the wrong offset, a gravity mask applied on the wrong
    tick, a slope nibble read from the wrong end of a record, a bumper that
    flashes for two frames instead of one, a knocker whose direction bit is
    read the wrong way up: none of them survives six hundred frames of this.
    """
    objs = mkpcs.test_table()
    sim = pcsobj.Sim(mkpcs.serialise(objs), pak, wset=mkpcs.WSET,
                     width=mkpcs.TW)
    ball = sim.parts[sim.ballobj]
    got = _stream(vram, PLAYR, n * 4)

    for f in range(1, n + 1):
        sim.step()
        i = (f - 1) * 4
        m = (ball.L(pcsobj.L_X1), ball.L(pcsobj.L_Y1),
             ball.L(pcsobj.L_BDX), ball.L(pcsobj.L_BDY))
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
            return None
    hits = len(sim.world.hits)
    struck = sorted(set(h[1] for h in sim.world.hits))
    print('    the ball agrees with RUN.s for all %d frames, %d hits on %s'
          % (n, hits, ', '.join(str(o) for o in struck)))

    # ⛔ A ball that never moved would agree trivially, and one that only ever
    # met the backdrop would prove nothing about the object system.
    if hits < 2:
        print('FAIL  the ball hit something only %d times - the run proves '
              'nothing' % hits)
        return None
    parts_struck = [o for o in struck if o in sim.parts]
    if len(parts_struck) < 5:
        print('FAIL  only %d LIBRARY PARTS were struck - the part procs are '
              'what this leg is for' % len(parts_struck))
        return None

    # -- every part's state byte, at the end of the run -------------------
    want = bytes(sim.parts[o].L(pcsobj.L_STATE) for o in sim.rcn)
    gots = _stream(vram, PLAYS, len(want))
    if gots != want:
        print('FAIL  the part states differ')
        print('      drew %s' % ' '.join('%02X' % b for b in gots))
        print('      want %s' % ' '.join('%02X' % b for b in want))
        print('      (%s)' % ' '.join(sim.parts[o].kind for o in sim.rcn))
        return None

    # -- the score, the sound, and the shape of the run -------------------
    tail = _stream(vram, PLAYT, 23)
    wtail = (bytes(sim.score1) + bytes(sim.bonus)
             + bytes((sim.dscore, sim.series, sim.slice, sim.runlen,
                      sim.lasty)))
    if tail != wtail:
        print('FAIL  the score, the sound or the run chain differs')
        for nm, a, b in (('score ', tail[:9], wtail[:9]),
                         ('bonus ', tail[9:18], wtail[9:18]),
                         ('tail  ', tail[18:], wtail[18:])):
            mark = '  ' if a == b else '<<'
            print('      %s drew %s  want %s %s'
                  % (nm, ' '.join('%d' % v for v in a),
                     ' '.join('%d' % v for v in b), mark))
        return None
    print('    %d parts in the run chain, the drain line is %d, the score is '
          '%s' % (sim.runlen, sim.lasty,
                  ''.join(str(d) for d in sim.score1).lstrip('0') or '0'))
    return sim


def edit_session(vram):
    """⭐⭐ A CONSTRUCTION SESSION, AND THE DATABASE IT LEFT BEHIND.

    `mkpcs.edit_script()` is a dozen edits - two parts out of the bin, a drag,
    a vertex moved, one pasted and cut again, a repaint, a delete - and two the
    database must REFUSE.  The machine runs them through pcsedit.inc and the
    model through pcsedit.DB, and three things are compared: what each step
    came to, every byte of the object area, and the whole span database.

    ⛔ THE REFUSALS ARE THE POINT.  An edit the database will not take has to
    leave NO TRACE, and a gate that never sees one has not checked the rollback
    at all - which is why the script deletes the backdrop and drags a
    triangle's third vertex level with the other two.
    """
    objs = mkpcs.test_table()
    db = pcsedit.DB(objs, width=mkpcs.TW, height=mkpcs.TH)
    want = pcsedit.run_script(db, mkpcs.edit_script())
    got = _stream(vram, EDITR, len(want))
    names = [mkpcs.EDIT_OPS[st[0]] for st in mkpcs.edit_script()][:len(want)]
    if got != want:
        print('FAIL  the session went differently')
        for i, (g, w) in enumerate(zip(got, want)):
            print('      %2d %-6s machine %s, EDIT.s %s %s'
                  % (i, names[i], 'refused' if g else 'took',
                     'refused' if w else 'took', '' if g == w else '<<'))
        return False
    nref = sum(want)
    if nref < 2:
        print('FAIL  only %d edit(s) were refused - the rollback is unchecked'
              % nref)
        return False
    print('    the session: %d edits, %d of them refused'
          % (len(want), nref))

    wantpb = mkpcs.serialise(db.objs)
    gotpb = _stream(vram, EDITO, len(wantpb))
    if gotpb != wantpb:
        i = next(k for k in range(len(wantpb)) if gotpb[k] != wantpb[k])
        print('FAIL  the object area differs at byte %d of %d'
              % (i, len(wantpb)))
        lo = max(0, i - 6)
        print('      drew %s' % ' '.join('%3d' % b for b in gotpb[lo:i + 10]))
        print('      want %s' % ' '.join('%3d' % b for b in wantpb[lo:i + 10]))
        print('      (%d objects, lengths %s)'
              % (wantpb[0], list(wantpb[1:1 + wantpb[0]])))
        return False
    print('    the object area matches: %d objects, %d bytes'
          % (wantpb[0], len(wantpb)))
    return _database(vram, db.pak)


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

    # ⛔ THE EDIT SESSION BEFORE THE UNEDITED DATABASE, because mode 6 dumps
    # the database AFTER the session: comparing it with the table as built is
    # comparing it with the one thing it must no longer be.  edit_session
    # compares it with the model's edited table instead.
    if len(sys.argv) > 2 and sys.argv[2] == 'edit':
        return 0 if edit_session(vram) else 1

    # ⭐⭐ THE DATABASE FIRST, because it is what the hit test and the ball
    # actually read - and because a picture can be right for the wrong reason.
    if not _database(vram, pak):
        return 1

    # ⭐ AND THE BALL BEFORE THE PICTURE, when this run was one that played:
    # every part's animation counter has moved, and the picture the card is
    # holding is each part's FINAL frame.  Rendering frame 0 and comparing
    # happened to pass, which is exactly the kind of agreement that stops
    # being true the day a part comes to rest mid-animation.
    ball = len(sys.argv) > 2 and sys.argv[2] == 'ball'
    if ball:
        sim = trajectory(vram, pak)
        if sim is None:
            return 1
        pak2, want, w, h = expected(sim.parts)

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
