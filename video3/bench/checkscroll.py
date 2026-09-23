#!/usr/bin/env python3
"""checkscroll.py DIR [FRAMES] - the streaming engine's ring, byte for byte.

    python3 video3/bench/checkscroll.py /tmp/arm6309-scroll 1200

⭐ WHAT THIS ASSERTS, AND WHY IT IS THE RIGHT GATE.  The engine's whole claim
is an invariant: after any amount of travel, ring column c holds world column
c (mod 1024) for the 23 slots of the terrain window, and the other 9 hold the
tile bank's nine strips - wherever the rotation has left them.  So the model
below walks the same path the program walks, works out where every strip
ended up, and then compares all 524,288 bytes of the ring against what that
says they should be.  A rotation that loses a strip, a column composed from
the wrong world tile, a vertical band that lands a half-tile out - none of
them can survive it.

⚠ It reads `vram.bin` (VRAMDUMP=), so it checks the END STATE of a run.  The
end state is reached through every intermediate one, and a strip that was
briefly in the wrong place would have been composed over, so this is not the
weak check it might look like.
"""
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "video3" / "bench"))
import mkscroll as S                                        # noqa: E402

# the camera's path, and it has to agree with scroll.asm's PathTab
PATH = [(2, 0, 420), (2, 2, 200), (0, 2, 200), (-2, 2, 200),
        (-2, 0, 420), (-2, -2, 200), (0, -2, 200), (2, -2, 200)]
WPX, HPX = S.ZWLDW * S.ZTILE, S.ZWLDH * S.ZTILE


def walk(frames):
    """The camera, the terrain window and the nine strips, after `frames`."""
    wx, wy = 0, S.ZTILE * 20 + S.ZVBAND
    hsl, vlo = 0, S.ZTILE * 20
    col = [S.ZTSLOT - 1 + c for c in range(S.ZBCOL)]         # ring slot of strip c
    pidx, pcnt = len(PATH) - 1, 0
    for _ in range(frames):
        if pcnt == 0:
            pidx = (pidx + 1) % len(PATH)
            pcnt = PATH[pidx][2]
        pcnt -= 1
        dx, dy, _n = PATH[pidx]
        wx = (wx + dx) % WPX
        wy = (wy + dy) % HPX
        # --- the horizontal slot, and the rotation it asks for -------------
        nh = wx >> 5
        d = (nh - hsl) & S.ZWLDW - 1
        if d == 1 or d == S.ZWLDW - 1:
            right = d == 1
            new = hsl + S.ZTSLOT - 1 if right else hsl - 2   # the world slot added
            drop = hsl - 1 if right else hsl + S.ZTSLOT - 2  # ... and the one dropped
            src, dst = new & S.ZSLOTS - 1, drop & S.ZSLOTS - 1
            for c in range(S.ZBCOL):
                if col[c] == src:
                    col[c] = dst
                    break
            else:
                sys.exit("FAIL  model: no strip at ring slot %d" % src)
        hsl = nh
        # --- and the vertical band ----------------------------------------
        vlo = (wy - S.ZVBAND) & ~(S.ZVBAND - 1) & HPX - 1
    return wx, wy, hsl, vlo, col


def expect(hsl, vlo, col, maps, cells, bank):
    """The whole 1024 x 512 ring, as the invariant says it must be."""
    ring = np.zeros((S.ZRINGH, S.ZRINGW), np.uint8)
    seen = np.zeros(S.ZSLOTS, bool)
    for c in range(S.ZBCOL):                                 # the nine strips
        x = col[c] * S.ZTILE
        ring[:, x:x + S.ZTILE] = bank[:, c * S.ZTILE:(c + 1) * S.ZTILE]
        seen[col[c]] = True
    for i in range(S.ZTSLOT):                                # the terrain window
        ws = hsl - 1 + i
        x = (ws & S.ZSLOTS - 1) * S.ZTILE
        if seen[ws & S.ZSLOTS - 1]:
            sys.exit("FAIL  model: ring slot %d is both terrain and bank"
                     % (ws & S.ZSLOTS - 1))
        seen[ws & S.ZSLOTS - 1] = True
        wr = vlo
        while wr < vlo + S.ZRINGH:
            off = wr & S.ZTILE - 1
            h = min(S.ZTILE - off, vlo + S.ZRINGH - wr)
            t = maps[(wr >> 5) & S.ZWLDH - 1][ws & S.ZWLDW - 1]
            ring[np.arange(wr, wr + h) & S.ZRINGH - 1, x:x + S.ZTILE] = \
                cells[t][off:off + h]
            wr += h
    if not seen.all():
        sys.exit("FAIL  model: ring slots %s are neither"
                 % list(np.flatnonzero(~seen)))
    return ring


def main(d, frames):
    tiles, index = S.tileset()
    m, _terr = S.world(index)
    art = S.art_bank()
    allt = list(tiles) + [None] * (S.ZART0 - len(tiles)) + art
    bank = S.bank(allt)
    cells = np.zeros((S.ZNTILE, S.ZTILE, S.ZTILE), np.uint8)
    for n, t in enumerate(allt):
        if t is not None:
            cells[n] = t
    wx, wy, hsl, vlo, col = walk(frames)
    print("after %d frames: camera (%d, %d), window slots %d..%d, vlo %d"
          % (frames, wx, wy, hsl - 1, hsl + S.ZTSLOT - 2, vlo))
    print("             the nine strips are at ring slots %s" % col)
    want = expect(hsl, vlo, col, m, cells, bank)
    live = np.frombuffer((pathlib.Path(d) / "vram.bin").read_bytes(),
                         np.uint8).reshape(S.ZRINGH, S.ZRINGW)
    # ⛔ AND THE SCRATCH TILES ARE NOT PREDICTABLE.  Each actor's save-behind
    # rides in a bank tile (there is nowhere else), so after the run those
    # ZMXAC tiles hold whatever was last saved into them - terrain from
    # wherever the actor happened to be standing.  The invariant has nothing
    # to say about them and they are masked out here rather than asserted.
    mask = np.ones_like(want, bool)
    for a in range(S.ZMXAC):
        t = S.ZSCR0 + a
        x = col[t // S.ZBROW] * S.ZTILE
        y = (t % S.ZBROW) * S.ZTILE
        mask[y:y + S.ZTILE, x:x + S.ZTILE] = False
    bad = int(((live != want) & mask).sum())
    ok = 0
    print("%s  the ring is what the invariant says: %d of %d bytes differ"
          % ("ok   " if bad == 0 else "FAIL ", bad, want.size))
    ok += bad == 0
    if bad:
        # ⭐ WHICH SLOTS, because "524,288 bytes differ" names nothing
        for sl in range(S.ZSLOTS):
            x = sl * S.ZTILE
            n = int((live[:, x:x + S.ZTILE] != want[:, x:x + S.ZTILE]).sum())
            if n:
                kind = "bank" if sl in col else "terrain"
                print("     ring slot %2d (%s): %d bytes" % (sl, kind, n))
    # ⛔ AND THE LEAK CHECK, OVER THE 21 SLOTS THE VIEW CAN REACH.  Index 0 is
    # the copy engine's key and mkscroll refuses it in every terrain tile, so a
    # zero on screen is a rectangle nobody painted.  ⚠ NOT over the whole ring:
    # the bank's unused tile slots are zero and its sixteen actor shapes are
    # keyed, so 88,272 bytes of legitimate index 0 live there - a whole-ring
    # leak check reports all of them and reads exactly like a real defect.
    z = 0
    for i in range(S.ZVSLOT):
        x = ((hsl + i) & S.ZSLOTS - 1) * S.ZTILE
        z += int((live[:, x:x + S.ZTILE] == 0).sum())
    print("%s  no index-0 leak in the %d slots the view can reach: %d bytes" %
          ("ok   " if z == 0 else "FAIL ", S.ZVSLOT, z))
    ok += z == 0
    print("%d claims, %d failed" % (2, 2 - ok))
    return 0 if ok == 2 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1200))
