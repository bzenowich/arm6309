#!/usr/bin/env python3
"""pcsworld.py - the editor's WORLD panel, modelled (pcs.md §8, pcsworld.inc).

EDIT.s's WORLDSTART drew four vertical tracks - gravity, speed, kick and
elasticity - and DOSLIDE took a level 0..7 from how far below a track's top
the pointer was, against SLDXDY's thresholds 2, 5, 8 .. 23: one level every
three Atari rows, 0 above the first.  The port keeps the rule at card scale,
a level every ST card rows, and commits the level from the RELEASE; so every
gesture is a pure function of its press and its release, which is what lets
checkpcs.py model a session from the script alone.

`Panel.press` is WoAct: a record's `op` and answer, or None for a press the
tool column takes (the panel ends and the tool is the editor's).
`Panel.knobs` is the picture: for each track, which level's box is the knob.
"""
TOOLX = 536                 # a press here ends the panel and takes the tool
TW, ST = 28, 16             # a track's width, card rows a level
TH = 8 * ST + 8
KW, KH = 20, 12             # the knob, inside the frame
HITM = 12                   # a track takes a press this far either side
QX, QY, QW, QH = 398, 432, 60, 24
# (frame x, frame y, heading x, heading y, heading) in wset's order
TRACKS = ((354, 48, 325, 20, 'GRAVITY'), (458, 48, 442, 20, 'SPEED'),
          (354, 264, 343, 236, 'KICK'), (458, 264, 411, 236, 'ELASTICITY'))
NAMES = ('gravity', 'speed', 'kick', 'elasticity')

# records' op[1] kinds (EDL.* in pcsworld.inc), after pcsdisk's 7..12
EDL_WSET, EDL_WQUIT = 13, 14


def hit(px, py):
    """WoHit: the track a press is on, or None."""
    for i, (x, y, _hx, _hy, _t) in enumerate(TRACKS):
        if 0 <= px - (x - HITM) < TW + 2 * HITM and 0 <= py - y < TH:
            return i
    return None


def level(i, y):
    """WoLvl: DOSLIDE's rule - 0 above the first level, 7 past the last."""
    dy = y - TRACKS[i][1] - 4
    return 0 if dy < 0 else min(dy // ST, 7)


def knob(i, lvl):
    """The knob's box, (x, y, w, h), at level `lvl` on track i (WoBox)."""
    x, y = TRACKS[i][0], TRACKS[i][1]
    return (x + (TW - KW) // 2, y + 4 + ST * lvl, KW, KH)


class Panel(object):
    def __init__(self):
        self.up = False

    def open(self):
        self.up = True

    def press(self, px, py, rx, ry, wset):
        """WoAct.  `wset` is the table's, and a slider edits it in place."""
        if px >= TOOLX:
            self.up = False
            return None
        i = hit(px, py)
        if i is not None:
            new, old = level(i, ry), wset[i]
            wset[i] = new
            return [0, EDL_WSET, i, new, old], 0
        if 0 <= px - QX < QW and 0 <= py - QY < QH:
            self.up = False
            return [0, EDL_WQUIT, 0, 0, 0], 0xFF
        return [0] * 5, 0xFF


def _selftest():
    assert [level(0, y) for y in (0, 48, 51, 52, 67, 68, 163, 164, 400)] == \
        [0, 0, 0, 0, 0, 1, 6, 7, 7]
    assert hit(354 - 12, 48) == 0 and hit(354 - 13, 48) is None
    assert hit(354 + 28 + 11, 48 + TH - 1) == 0 and hit(354 + 40, 48) is None
    assert hit(460, 300) == 3 and hit(460, 264 + TH) is None
    p, w = Panel(), [1, 2, 3, 4]
    p.open()
    assert p.press(360, 60, 360, 1000, w) == ([0, 13, 0, 7, 1], 0) and w[0] == 7
    assert p.press(460, 300, 999, 0, w) == ([0, 13, 3, 0, 4], 0) and w[3] == 0
    assert p.press(330, 470, 330, 470, w) == ([0] * 5, 0xFF) and p.up
    assert p.press(400, 440, 400, 440, w) == ([0, 14, 0, 0, 0], 0xFF)
    assert not p.up
    p.open()
    assert p.press(560, 250, 560, 250, w) is None and not p.up
    # the knobs of one track never overlap: a level is ST rows and the box KH
    assert KH < ST and KH % 2 == 0
    print('ok    pcsworld.py self-test')


if __name__ == '__main__':
    _selftest()
