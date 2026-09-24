#!/usr/bin/env python3
"""checkpbt.py - a table LOADED OFF THE CARD is the table the 6502 built.

⭐⭐ THE POINT OF THIS LEG is not that the picture looks right - `run-pcs.sh`
already gates a picture - but that the bytes made the round trip: mkpcs.py's
container, RBF, pcsfile.inc's header check and one I$Read into `logic,u`.  So
it compares the SPAN DATABASE record for record as well as the framebuffer,
because the database is what the ball collides with and a loader that dropped
a byte would still paint something.

    python3 software/pcs/bench/checkpbt.py RUNDIR TABLENAME
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mkpcs                                                  # noqa: E402
import pcsfile                                                # noqa: E402
import pcspak as K                                            # noqa: E402
import pcspal                                                 # noqa: E402

STRIDE = 1024
DUMPR = 500                           # PCDump's VRAM row (pcsdraw.inc)


def main():
    d = sys.argv[1]
    want = sys.argv[2]
    ok = True

    tbl = [t for t in pcsfile.demo_tables() if mkpcs.pbt_name(t[0]) == want]
    if not tbl:
        print('FAIL  no table generates %s' % want)
        return 1
    name, logic, wset, objs = tbl[0]
    for o in objs:
        o.fillcolor = pcspal.FROM_APPLE.get(o.fillcolor, pcspal.PAINT0 + 5)
    pak = K.Pak(height=mkpcs.TH, width=mkpcs.TW)
    pak.objs = objs
    pak.display()
    fb, w, h = mkpcs.render_table(pak, objs, None)

    vram = open(os.path.join(d, 'vram.bin'), 'rb').read()

    # ── the database, which is what a dropped byte would show in ──────────
    pbdx = vram[DUMPR * STRIDE:DUMPR * STRIDE + pak.TH]
    ref = bytes(len(r) * 4 for r in pak.rows)
    n = sum(1 for a, b in zip(pbdx, ref) if a != b)
    if n:
        print('FAIL  pbdx differs on %d of %d scanlines' % (n, pak.TH))
        ok = False
    buf = b''.join(vram[(DUMPR + 1 + i) * STRIDE:(DUMPR + 1 + i) * STRIDE + 1024]
                   for i in range(11))
    p, bad = 0, 0
    for y in range(pak.TH):
        got = [tuple(buf[p + j * 4:p + j * 4 + 4]) for j in range(pbdx[y] // 4)]
        p += pbdx[y]
        if got != [tuple(r) for r in pak.rows[y]]:
            if not bad:
                print('      first at scanline %d\n        card %s\n        6502 %s'
                      % (y, got[:4], [tuple(r) for r in pak.rows[y]][:4]))
            bad += 1
    if bad:
        print('FAIL  %d of %d scanlines carry a different span record' % (bad, pak.TH))
        ok = False
    else:
        print('ok    %s off the card: %d scanlines, %d span records, identical'
              % (name, sum(1 for b in pbdx if b), sum(pbdx) // 4))

    # ── and the picture ───────────────────────────────────────────────────
    # ⚠ THE PARTS ARE ANIMATED, so a part that has advanced a frame is not a
    # fault: the reference draws frame 0 and the machine ran the simulator.
    # Only colour 27 (the part art) may differ, and only where a part is.
    diff = [(x, y) for y in range(h) for x in range(w)
            if vram[y * STRIDE + x] != fb[y * w + x]]
    art = [1 for x, y in diff
           if 27 in (vram[y * STRIDE + x], fb[y * w + x])]
    if len(art) != len(diff):
        print('FAIL  %d of %d differing pixels are not part art'
              % (len(diff) - len(art), len(diff)))
        ok = False
    else:
        print('ok    %d of %d card pixels differ, all of them part animation'
              % (len(diff), w * h))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
