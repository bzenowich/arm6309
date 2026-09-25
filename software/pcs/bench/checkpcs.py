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
EDITR, EDITO = 498, 510     # ⚠ 510: PCDump fills 500..508
EDITL = 496                 # MgDump: the free-hand layer (pcsmag.inc)


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
    if len(wantpb) > 2048:
        print('FAIL  the edited table is %d bytes and mode 23 dumps 2048'
              % len(wantpb))
        return False
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



# ═══════════════════════════════════════════════════════════════════════════
# THE EDITOR WITH A MOUSE (`pcs 23`, pcsui.inc's EdLoop)
# ═══════════════════════════════════════════════════════════════════════════
UIREC = 15                  # tool, press x/y, release x/y (16-bit), op[5], answer
EDL_MISS, EDL_TOOL, EDL_PICK, EDL_BIN = 0, 1, 2, 3
ED_HAND, ED_PTR, ED_CUT, ED_HAM, ED_BRSH, ED_NTL = 0, 1, 2, 3, 4, 5
ED_PLAY, ED_MAGN, ED_WRLD, ED_DISK = 8, 9, 10, 12
EDITW = 509                         # modes 23/24: logic[24], wset[4], uqk
KEYNAMES = {'backspace': 8, 'bksp': 8, 'delete': 0x7F, 'del': 0x7F,
            'enter': 13, 'return': 13, 'space': 32}


def ps2_gestures(path):
    """Every left-button press and its release, in card pixels, out of the
    PS/2 script - the pointer the SCRIPT believes in, which is the one a test
    author means (emu/ps2script.h).  ⚠ Only what moves the pointer or the left
    button is read; times do not matter here, only order.
    ⭐ And every key the editor is given, as ('key', byte): `type` a byte a
    character, `key tap NAME` one byte - except the key that ends PLAY,
    which the game takes."""
    import shlex
    import pcskit
    _n, px0, py0, pw, ph = pcskit.tools()[ED_PLAY]
    # a press on PLAY hands the mouse to the game until a key comes back
    hit_play = lambda g: (0 <= g[0] // 2 - px0 < pw           # noqa: E731
                          and 0 <= g[1] // 2 - py0 < ph)
    x = y = 0
    down = None
    play = False
    out = []
    for raw in open(path):
        line = raw.split('#')[0].split(';')[0].strip()
        if not line:
            continue
        w = shlex.split(line)
        if w[0] == 'at':
            w = w[2:]
        elif w[0].startswith('+'):
            w = w[1:]
        if not w:
            continue
        if w[0] == 'type':
            if not play:
                out.extend(('key', ord(c)) for c in
                           w[1].encode().decode('unicode_escape'))
            play = False                # ⭐ the key that ends PLAY
        elif w[:2] == ['key', 'tap']:
            k = w[2].lower()
            if not play:
                out.append(('key', KEYNAMES[k] if k in KEYNAMES else ord(w[2])))
            play = False
        if play and w[0] in ('down', 'up', 'click'):
            continue                    # ⭐ PLAYING: the buttons are flippers
        if w[0] == 'origin':
            x, y = int(w[1]), int(w[2])
        elif w[:2] == ['move', 'to']:
            x, y = int(w[2]), int(w[3])
        elif w[:2] == ['move', 'by']:
            x, y = x + int(w[2]), y + int(w[3])
        elif w[:2] == ['down', 'left']:
            down = (x, y)
        elif w[:2] == ['up', 'left'] and down is not None:
            out.append(down + (x, y))
            down = None
            play = hit_play(out[-1])
        elif w[:2] == ['click', 'left']:
            out.append((x, y, x, y))
            play = hit_play(out[-1])
    return out


def _pksel(db, wx, wy):
    """SELECTPOLY as PKSel does it: the LAST span on the row that holds x,
    skipping the backdrop."""
    if not 0 <= wy < db.TH:
        return None
    hit = None
    for (xl, obj, xr, _sl) in db.pak.rows[wy]:
        if obj and xl <= wx <= xr:
            hit = obj
    return hit


def _selpoint(db, wx, wy, hammer):
    """SELECTPOINT (EDIT.s:1038): polygons only, |dx| < 8 and |dy| < 8, the
    smallest sum and the first on a tie.  In hammer mode the candidate is the
    midpoint of the edge ENDING at each vertex."""
    best = None
    md = 0xFF
    for i, o in enumerate(db.objs):
        if o.objid not in (K.POLY, K.BPOLY):
            continue
        for v in range(o.n):
            cx, cy = o.x[v], o.y[v]
            if hammer:
                p = v - 1 if v else o.n - 1
                cx, cy = (o.x[p] + cx) // 2, (o.y[p] + cy) // 2
            dx, dy = abs(cx - wx), abs(cy - wy)
            if dx >= 8 or dy >= 8:
                continue
            if dx + dy < md:
                md = dx + dy
                best = (i, v, cx, cy, o.n)
    return best


def _op(db, op):
    return pcsedit.run_script(db, [tuple(op)])[0]


def ui_model(gestures, db, mag=None, disk=None):
    """⭐ WHAT EdLoop MUST HAVE DONE, from the script's points alone: the tool,
    the colour, and for every gesture the record it writes - `(tool, px, py,
    rx, ry, op0..op4, answer)` - with each edit applied to `db` as it goes.

    ⭐ `mag`, a dict, is the magnifier's state (pcsmag.inc): `up`, the `box`,
    and the free-hand `layer` every plot goes into - left as the session left
    it, for ui_session to compare with what the machine drew and dumped.
    ⭐ It is also the TABLE's: `db`, `wset` and `layer` are what a DISK LOAD
    replaces, so the table the session ends with is `mag['db']`.
    ⭐ `disk` is a pcsdisk.Panel, the card's files in it."""
    import pcskit
    import pcsparts
    import pcsmag
    if mag is None:
        mag = {}
    mag.setdefault('up', False)
    mag.setdefault('box', None)
    mag.setdefault('layer', pcsmag.Layer())
    mag.setdefault('wset', list(mkpcs.WSET))
    mag['db'] = db
    import pcsdisk
    if disk is None:
        disk = pcsdisk.Panel({})
    tools = pcskit.tools()
    boxes = mkpcs.bin_boxes()
    parts = pcsparts.parts()
    tw, th = mkpcs.TW, mkpcs.TH
    pkx, pky, cell = pcskit.picker()
    pkx += 2 * pcskit.KX                # the panel's own origin -> card pixels
    tool, pk = ED_HAND, 0
    recs = []
    sb = lambda v: max(-128, min(127, v)) & 0xFF      # noqa: E731
    for g in gestures:
        if g[0] == 'key':
            # ⭐ A KEY IS THE NAME FIELD'S while DISK is up, and otherwise
            # only `q` means anything: the editor ends.
            if disk.up:
                recs.append([tool, 0, 0, 0, 0] + disk.key(g[1]) + [0xFF])
            elif g[1] in (ord('q'), ord('Q')):
                break
            continue
        px, py, rx, ry = g
        db = mag['db']
        wx, wy, rwx, rwy = px // 2, py // 2, rx // 2, ry // 2
        op, res, extra = [0] * 5, 0xFF, None
        # ⭐ DISK, while it is up (pcsdisk.inc's DkAct, through MgAct)
        if disk.up:
            r = disk.press(px, py, mag)
            if r is not None:
                recs.append([tool, px, py, rx, ry] + r[0] + [r[1]])
                continue
        # ⭐ THE MAGNIFIER FIRST, while it is up (MgAct): a gesture it takes is
        # one record and nothing else happens.
        if mag['up']:
            took = True
            if px < tw * 2:
                mag['box'] = pcsmag.box_at(rwx, rwy)
                op = [0, pcsmag.EDL_MBOX, mag['box'][0], mag['box'][1], 0]
            elif pcsmag.in_viewer(px, py):
                bx, by = mag['box']
                x0, y0 = pcsmag.fat(px, py)
                x1, y1 = pcsmag.fat(rx, ry)
                pts = [(bx + x, by + y) for x, y in pcsmag.line(x0, y0, x1, y1)]
                cc = mag['layer'].plot(pts, pcspal.PICK0 + pk)
                op, res = [0, pcsmag.EDL_PLOT, len(pts), cc, 0], 0
            elif pcsmag.in_quit(px, py):
                mag['up'] = False
                op = [0, pcsmag.EDL_MQUIT, 0, 0, 0]
            elif (0 <= px - pkx < pcspal.PICKW * cell
                  and 0 <= py - pky < pcspal.PICKH * cell):
                took = False            # the picker is the editor's
            elif wx >= pcsmag.TOOLX:
                mag['up'] = False       # a tool ends it, and is taken
                took = False
            if took:
                recs.append([tool, px, py, rx, ry] + op + [res])
                continue
        if px < tw * 2:
            if tool == ED_HAND:
                o = _pksel(db, wx, wy)
                if o is not None:
                    if rx >= tw * 2:
                        op = [mkpcs.PE_DEL, o, 0, 0, 0]
                    elif (rwx - wx, rwy - wy) != (0, 0):
                        op = [mkpcs.PE_DRAG, o, sb(rwx - wx), sb(rwy - wy), 0]
            elif tool == ED_BRSH:
                o = _pksel(db, wx, wy) or 0
                op = [mkpcs.PE_PAINT, o, pcspal.PICK0 + pk, 0, 0]
            else:
                sp = _selpoint(db, wx, wy, tool == ED_HAM)
                if sp is not None:
                    obj, v, mx, my, n = sp
                    if tool == ED_PTR:
                        op = [mkpcs.PE_DRAGP, obj, v, rwx, rwy]
                    elif tool == ED_CUT:
                        op = [mkpcs.PE_CUT, obj, v, 0, 0]
                    else:
                        op = [mkpcs.PE_PASTE, obj, (v - 1) % n, 0, 0]
                        extra = (obj, mx, my)
        elif (0 <= px - pkx < pcspal.PICKW * cell
              and 0 <= py - pky < pcspal.PICKH * cell):
            pk = ((py - pky) // cell * pcspal.PICKW + (px - pkx) // cell)
            op = [0, EDL_PICK, pk, 0, 0]
        else:
            hit = next((i for i, (_n, x, y, w, h) in enumerate(tools)
                        if 0 <= wx - x < w and 0 <= wy - y < h), None)
            if hit is not None:
                op = [0, EDL_TOOL, hit, 0, 0]
                if hit < ED_NTL:
                    tool = hit
                elif hit == ED_MAGN:
                    mag['up'] = True
                    mag['box'] = mag['box'] or (pcsmag.BX0, pcsmag.BY0)
                elif hit == ED_DISK:
                    disk.open()
            elif tool == ED_HAND:
                b = next((i for i, (x, y, w, h) in enumerate(boxes)
                          if 0 <= wx - x <= w and 0 <= wy - y <= h), None)
                if b is not None and rx >= tw * 2:
                    op = [0, EDL_BIN, b, 0, 0]
                elif b is not None:
                    p = parts[b]
                    w = max(p.x) - min(p.x)
                    h = max(p.y) - min(p.y)
                    tx = max(1, min(tw - 2 - w, rwx - wx + min(p.x)))
                    ty = max(1, min(th - 2 - h, rwy - wy + min(p.y)))
                    op = [mkpcs.PE_ADD, b, tx, ty, 0]
        if op[0]:
            res = _op(db, op)
        recs.append([tool, px, py, rx, ry] + op + [res])
        # ⭐ THE HAMMER IS TWO EDITS: the paste, and then DRAGPOINT of the new
        # vertex - found again by where it is, because ALIGNPOLY may rotate.
        if extra and res == 0:
            obj, mx, my = extra
            o = db.objs[obj]
            k = next((i for i in range(o.n) if (o.x[i], o.y[i]) == (mx, my)),
                     None)
            if k is not None:
                op = [mkpcs.PE_DRAGP, obj, k, rwx, rwy]
                recs.append([tool, px, py, rx, ry] + op + [_op(db, op)])
    return recs


def _uirecs(vram):
    s = _stream(vram, EDITR, 2 * 1024)
    out = []
    for i in range(0, len(s) - UIREC, UIREC):
        r = s[i:i + UIREC]
        if r[0] == 0xFF:
            return out
        out.append([r[0], r[1] << 8 | r[2], r[3] << 8 | r[4],
                    r[5] << 8 | r[6], r[7] << 8 | r[8]] + list(r[9:15]))
    return None


def _uifmt(r):
    t = ('hand', 'ptr', 'cut', 'ham', 'brush')
    op = r[5]
    if op:
        what = '%-5s %s' % (mkpcs.EDIT_OPS[op], r[6:10])
        what += ' refused' if r[10] else ' took'
    else:
        what = ('-', 'tool %d' % r[7], 'colour %d' % r[7],
                'bin %d let go off the table' % r[7],
                'magnifier box to (%d, %d)' % (r[7], r[8]),
                'fat bits: %d in colour %d' % (r[7], r[8]),
                'magnifier QUIT',
                'key %r, name %d long' % (chr(r[7]), r[8]),
                'list row %d picked, name %d long' % (r[7], r[8]),
                'LOAD: pferr %d, %d objects' % (r[7], r[8]),
                'SAVE: pferr %d, %d listed' % (r[7], r[8]),
                'DISK QUIT', 'MORE: page at %d' % r[7],
                )[r[6]] if r[6] < 13 else '?'
        if r[6] in (9, 10):
            what += ' refused' if r[10] else ' took'
    return '%-5s (%3d,%3d)->(%3d,%3d)  %s' % (
        t[r[0]] if r[0] < 5 else r[0], r[1], r[2], r[3], r[4], what)


def ui_session(vram, script, base=None, magnify=False, card=None, start=None,
               minq=0):
    """⭐⭐ THE EDITOR, DRIVEN: every gesture EdLoop recorded against the one the
    script made and the edit the model makes of it; then the object area, the
    span database and the picture the session left.

    ⛔ THE POSITIONS ARE COMPARED FIRST AND EXACTLY.  A press the machine saw
    somewhere else - a missed click, a pointer that is not where the script
    believes - makes every later answer a comparison of two different
    sessions, and says so here rather than as a mystery twenty edits on.

    ⭐ `card` is /SD0/DATA as the session found it, name -> bytes, and `start`
    the table `pcs 23 N name.pbt` loaded: the DISK leg.  The Panel it returns
    in `disk` holds the files the session must have left behind.

    ⭐ `minq` is how many mouse samples the session must have taken off the
    queue UISamp fills during a repaint (pcsin.inc): the close-gesture legs,
    whose gestures only land if the queue carried them.  ⛔ A leg that asks for
    it and gets 0 is a leg that proved nothing about the queue, however well
    its records match.
    """
    gest = ps2_gestures(script)
    got = _uirecs(vram)
    if got is None:
        print('FAIL  the gesture stream has no end marker - EdLoop never returned')
        return False
    import pcsdisk
    import pcsmag
    mag = {}
    if start:
        t = pcsdisk.parse(card[start])
        db = pcsedit.DB(t.objs, t.logic, width=mkpcs.TW, height=mkpcs.TH)
        mag['wset'], mag['layer'] = list(t.wset), pcsmag.Layer(t.layer)
    else:
        db = pcsedit.DB(base() if base else mkpcs.demo_table(),
                        width=mkpcs.TW, height=mkpcs.TH)
    disk = pcsdisk.Panel(card or {})
    want = ui_model(gest, db, mag, disk)
    db = mag['db']
    ok = True
    for i in range(max(len(got), len(want))):
        g = got[i] if i < len(got) else None
        w = want[i] if i < len(want) else None
        if g != w:
            ok = False
        print('    %2d %s  %s' % (i, _uifmt(g) if g else '(nothing)',
                                  '' if g == w else '<< wanted ' +
                                  (_uifmt(w) if w else 'nothing')))
    if not ok:
        print('FAIL  the machine\'s session is not the one the script makes')
        return False
    kinds = set(r[5] for r in want if r[5])
    nref = sum(1 for r in want if r[5] and r[10])
    print('    %d gestures, %d records: %d edits of %d kinds, %d refused'
          % (len(gest), len(want), sum(1 for r in want if r[5]),
             len(kinds), nref))
    # ⛔ A SESSION THAT NEVER REACHED AN OPERATION HAS NOT TESTED IT.
    missing = [mkpcs.EDIT_OPS[k] for k in range(1, 8) if k not in kinds]
    if base:
        missing, nref = [], 1       # a demo builds; it is not the coverage gate
    if magnify:
        # ⛔ THE MAGNIFIER'S OWN COVERAGE instead: the box moved, a line drawn,
        # a line ERASED by the toggle, and QUIT - or the leg has not seen them.
        import pcsmag
        mk = [(r[6], r[8]) for r in want if r[5] == 0]
        missing = [n for n, ok_ in (
            ('box move', any(k == pcsmag.EDL_MBOX for k, _ in mk)),
            ('fat-bit line', any(k == pcsmag.EDL_PLOT and c for k, c in mk)),
            ('toggled erase', any(k == pcsmag.EDL_PLOT and not c for k, c in mk)),
            ('QUIT', any(k == pcsmag.EDL_MQUIT for k, _ in mk))) if not ok_]
        nref = 1
    if card is not None:
        # ⛔ THE DISK PANEL'S OWN COVERAGE: a name typed, a table picked, a
        # LOAD that took and one that was refused, a SAVE over a name already
        # saved, and QUIT.
        dk = [(r[6], r[10]) for r in want if r[5] == 0]
        saves = [r for r in want if r[5] == 0 and r[6] == pcsdisk.EDL_DSAVE
                 and not r[10]]
        missing = [n for n, ok_ in (
            ('key', any(k == pcsdisk.EDL_KEY for k, _ in dk)),
            ('list pick', any(k == pcsdisk.EDL_DPICK for k, _ in dk)),
            ('LOAD', (pcsdisk.EDL_DLOAD, 0) in dk),
            ('refused LOAD', (pcsdisk.EDL_DLOAD, 1) in dk),
            ('second SAVE', len(saves) >= 2),
            ('DISK QUIT', any(k == pcsdisk.EDL_DQUIT for k, _ in dk)))
            if not ok_]
        nref = 1
    ui_session.disk = disk
    if missing:
        print('FAIL  the session never made a %s' % ', '.join(missing))
        return False
    if nref < 1:
        print('FAIL  nothing was refused - the rollback is unchecked')
        return False

    wantpb = mkpcs.serialise(db.objs)
    if len(wantpb) > 2048:
        print('FAIL  the edited table is %d bytes and mode 23 dumps 2048'
              % len(wantpb))
        return False
    gotpb = _stream(vram, EDITO, len(wantpb))
    if gotpb != wantpb:
        i = next(k for k in range(len(wantpb)) if gotpb[k] != wantpb[k])
        print('FAIL  the object area differs at byte %d of %d' % (i, len(wantpb)))
        lo = max(0, i - 6)
        print('      drew %s' % ' '.join('%3d' % b for b in gotpb[lo:i + 10]))
        print('      want %s' % ' '.join('%3d' % b for b in wantpb[lo:i + 10]))
        return False
    print('    the object area matches: %d objects, %d bytes'
          % (wantpb[0], len(wantpb)))
    if not _database(vram, db.pak):
        return False

    if not _layer(vram, mag['layer']):
        return False
    # ⭐ THE TABLE'S WIRING AND ITS WORLD, which nothing on the screen shows
    wantw = bytes(db.logic) + bytes(mag['wset'])
    gotw = _stream(vram, EDITW, len(wantw))
    if gotw != wantw:
        print('FAIL  logic+wset: got %s' % list(gotw))
        print('      wanted     %s' % list(wantw))
        return False
    print('    logic and wset match: %s, %s' % (list(db.logic[:8]), mag['wset']))
    qk = _stream(vram, EDITW, len(wantw) + 2)[-2:]
    queued = qk[0] << 8 | qk[1]
    print('    %d mouse samples came off the queue a repaint held' % queued)
    if queued < minq:
        print('FAIL  the queue carried %d samples and this leg needs %d: its '
              'gestures were never made during a repaint' % (queued, minq))
        return False

    # ⭐ AND THE PICTURE: the last repaint is the whole table, every part at its
    # frame 0, over the free-hand layer.  ⚠ The sprite is composited at scan
    # time and is not in VRAM.
    fb, w, h = mkpcs.render_table(db.pak, db.objs, layer=mag['layer'])
    table = bytes(fb)
    if mag['up']:
        # ⭐ Still up: its frame is on the table and the fat bits are in the kit
        pcsmag.frame(fb, w, *mag['box'])
        vw = pcsmag.viewer(table, w, *mag['box'])
        vbad = [(x, y) for (x, y), c in vw.items() if vram[y * STRIDE + x] != c]
        if vbad:
            x, y = vbad[0]
            print('FAIL  %d of %d viewer pixels differ; first at card (%d, %d): '
                  'got %d, wanted %d' % (len(vbad), len(vw), x, y,
                                         vram[y * STRIDE + x], vw[(x, y)]))
            return False
        print('ok    all %d pixels of the fat bits are the table\'s, read back'
              % len(vw))
    bad = [(x, y) for y in range(h) for x in range(w)
           if vram[y * STRIDE + x] != fb[y * w + x]]
    if bad:
        x, y = bad[0]
        print('FAIL  %d of %d table pixels differ; first at card (%d, %d): '
              'got %d, wanted %d' % (len(bad), w * h, x, y,
                                     vram[y * STRIDE + x], fb[y * w + x]))
        return False
    print('ok    all %d bytes of the edited table are what the model builds'
          % (w * h))
    return True


def card_files(img, tmp):
    """/SD0/DATA's `.pbt` files off an image, name -> bytes.  ⛔ `os9 copy`
    of a missing file says `error 216` and EXITS 0, so a file counts only if
    it was written."""
    import subprocess
    lst = subprocess.run(['os9', 'dir', img + ',DATA'], capture_output=True,
                         text=True, check=True).stdout
    names = [w for ln in lst.splitlines()[1:] for w in ln.split()
             if w.lower().endswith('.pbt')]
    if not names:
        raise SystemExit('FAIL  no .pbt on %s - `os9 dir` read nothing' % img)
    out = {}
    for n in names:
        f = os.path.join(tmp, n)
        if os.path.exists(f):
            os.remove(f)
        subprocess.run(['os9', 'copy', '%s,DATA/%s' % (img, n), f],
                       capture_output=True, check=True)
        if not os.path.isfile(f):
            raise SystemExit('FAIL  os9 copy wrote no %s' % n)
        with open(f, 'rb') as fh:
            out[n.lower()] = fh.read()
    return out


def disk_session(vram, script, start, before, after):
    """⭐⭐ SAVE AND LOAD: the session against the model, and then the card.
    Every file the model's panel holds must be on the card after the run
    byte for byte, and no other `.pbt` may have appeared or changed."""
    import tempfile
    tmp = tempfile.mkdtemp()
    card0 = card_files(before, tmp)
    if not ui_session(vram, script, card=card0, start=start):
        return False
    want = ui_session.disk.files
    got = card_files(after, tmp)
    ok = True
    for n in sorted(set(want) | set(got)):
        w, g = want.get(n), got.get(n)
        if w == g:
            tag = 'saved' if card0.get(n) != w else 'untouched'
            print('    %-12s %5d bytes, %s' % (n, len(w), tag))
            continue
        ok = False
        if w is None or g is None:
            print('FAIL  %s is %s the card and %s the model' % (
                n, 'on' if g else 'not on', 'in' if w else 'not in'))
        else:
            i = next((k for k in range(min(len(w), len(g))) if w[k] != g[k]),
                     min(len(w), len(g)))
            print('FAIL  %s: %d bytes on the card, %d in the model; first '
                  'difference at byte %d' % (n, len(g), len(w), i))
    new = [n for n in want if card0.get(n) != want[n]]
    if ok and not new:
        print('FAIL  nothing was saved')
        return False
    if ok:
        print('ok    %d file(s) saved, every byte as PFSave must write them: %s'
              % (len(new), ', '.join(new)))
    return ok


def _layer(vram, layer):
    """⭐ THE LAYER THE MACHINE KEPT, dumped by MgDump to EditL: its count and
    as many triples as two VRAM rows hold, against the model's."""
    want = layer.blob()
    n = want[0] << 8 | want[1]
    cap = 2 + 3 * min(n, 682)
    got = _stream(vram, EDITL, cap)
    if got[:2] != want[:2]:
        print('FAIL  the layer holds %d pixels; the model says %d'
              % (got[0] << 8 | got[1], n))
        return False
    if got != want[:cap]:
        i = next(k for k in range(cap) if got[k] != want[k])
        t = (i - 2) // 3
        print('FAIL  the layer differs at pixel %d: got %s, wanted %s'
              % (t, tuple(got[2 + 3 * t:5 + 3 * t]), tuple(want[2 + 3 * t:5 + 3 * t])))
        return False
    print('    the layer matches: %d pixels' % n)
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

    if len(sys.argv) > 2 and sys.argv[2] == 'kit':
        return 0 if kit_panel(vram) else 1

    # ⛔ THE EDIT SESSION BEFORE THE UNEDITED DATABASE, because mode 6 dumps
    # the database AFTER the session: comparing it with the table as built is
    # comparing it with the one thing it must no longer be.  edit_session
    # compares it with the model's edited table instead.
    if len(sys.argv) > 2 and sys.argv[2] == 'edit':
        return 0 if edit_session(vram) else 1

    # ⭐ MODE 23: the editor with a mouse, against the PS/2 script that drove it.
    minq = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[2] in ("ui", "ui-mag") else 0
    if len(sys.argv) > 3 and sys.argv[2] == 'ui':
        return 0 if ui_session(vram, sys.argv[3], minq=minq) else 1
    # ⭐ MODE 23 AGAIN, WITH THE MAGNIFIER: the fat bits, the layer they draw.
    if len(sys.argv) > 3 and sys.argv[2] == 'ui-mag':
        return 0 if ui_session(vram, sys.argv[3], magnify=True, minq=minq) else 1
    # ⭐ MODE 23 OFF A CARD, WITH DISK: the session, then every file it saved
    # read back out of the card the machine left, against the model's bytes.
    if len(sys.argv) > 6 and sys.argv[2] == 'ui-disk':
        return 0 if disk_session(vram, *sys.argv[3:7]) else 1
    # ⭐ MODE 24: the same, on a NEW table - the backdrop and nothing else.
    if len(sys.argv) > 3 and sys.argv[2] == 'ui-empty':
        return 0 if ui_session(vram, sys.argv[3], mkpcs.empty_table) else 1

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


def kit_panel(vram):
    """⭐ THE KIT PANEL, EVERY CARD PIXEL, against pcskit.py.

    x 320..639, y 0..479: DRAWKIT's thirteen tools and parts bin, the strip
    under them, and the 12 x 10 picker with its frame on the current colour -
    which `pcs 22` starts at cell 0, white.
    ⚠ The bitmap and this comparison come out of the same model, so what this
    proves is the MACHINE's half - the doubling, the placement, WM.Mask's bit
    order and both colours, and the picker's cells and frame.  That the model
    is DRAWKIT is pcskit.py's self-test and a picture a person has looked at.
    """
    import pcskit
    import pcspal
    want = pcskit.card(pcspal.UI_PANEL, pcspal.UI_INK, 0)
    W, H = 2 * pcskit.KW, 480
    bad, first = 0, None
    for y in range(H):
        for x in range(W):
            got = vram[y * STRIDE + 320 + x]
            if got != want[y * W + x]:
                bad += 1
                if first is None:
                    first = (x, y, got, want[y * W + x])
    ink = sum(1 for v in want if v == pcspal.UI_INK)
    if bad:
        x, y, g, w = first
        print('FAIL  the kit panel: %d card pixels differ; first at panel (%d, %d):'
              ' got %d, wanted %d' % (bad, x, y, g, w))
        return False
    print('ok    the kit panel: all %d card pixels are pcskit.py\'s, %d of them ink,'
          % (W * H, ink))
    print('      and the 12 x 10 picker with its frame on white')
    return True


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
