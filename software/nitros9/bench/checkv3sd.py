#!/usr/bin/env python3
"""checkv3sd.py OUT - did a picture get PAINTED in this run?

One run of software/nitros9/bench/run-v3sd.sh, read from OUT/frames.bin, reduced to the
four numbers that bench makes its claims from:

    frames=<n> painted=<k> colours=<c> changed=<d> desk=<a> paint=<b>

    n   frame records in the recording
    c   the most distinct colours any one frame showed
    k   frames showing more than PAINT_COLOURS (default 12) of them
    d   frames whose picture differs from the one before
    a   frames that look like THE HAIKU DESKTOP
    b   frames that look like PAINT

⭐ WHY COLOURS AND NOT "THE COMMAND RAN".  The emulator records a frame
whether or not anything is happening, so a frame count says only that the
machine was clocked, and a line on the console says only that something was
typed.  A NitrOS-9 text console is two or three palette entries and it does not
move; the scene this bench loads off the SD card holds nineteen colours at
once and changes every other frame.  So "more than a dozen colours were on
the card's output, and the picture kept changing" is a claim only a program
that loaded and ran can make true - which is what the negative control (no
card in the socket, same ROM, same keystrokes) has to fail.
⚠ THE THRESHOLD IS NOT 256.  mvania's room is a stylised side-view, not the
dithered photograph monster and the mvania background use, and a first cut of
this checker asked for 64 colours and failed a run whose picture was perfect.
The number to pick is the one the CONTROL cannot reach, not the one the scene
happens to reach today - and with no card the screen is never claimed at all,
so the control records no frames whatsoever.

⭐ AND TWO SHAPES, NOT TWO FILENAMES.  `desk` and `paint` are what say WHICH
scene reached the card's output, and they are deliberately structural rather
than a checksum of an expected picture:

    desk   one colour covers >= 45% of the frame AND the frame has >= 40
           colours.  That is a desktop: a big flat background (the Haiku
           blue, 0x3333 = 49,101,156) with icons, a Deskbar and window
           chrome on it.  Nothing else in this bench has both.
    paint  >= 20% of the frame is PURE WHITE and it has >= 40 colours.
           That is Paint's page - ~34% of the screen - under Haiku chrome.

⚠ Measured, not guessed: on the first run the desktop was 50.8% one colour
with 54 colours and 5.6% white; Paint was 35.5% its top colour, 27-34% white,
50 colours; and the no-card control was ONE colour over the whole frame.  The
thresholds sit between those, and the scene's own colour VALUES are not in
the test - a repainted desktop must not fail a claim about loading a file.

⛔ Its exit code is 0 unless the recording cannot be read; the numbers are
the answer and the shell script makes the claims.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "software", "tools"))
import frames as fr  # noqa: E402

PAINT = int(os.environ.get("PAINT_COLOURS", "12"))


def main():
    if len(sys.argv) != 2:
        print("usage: checkv3sd.py OUTDIR", file=sys.stderr)
        return 2
    path = os.path.join(sys.argv[1], "frames.bin")
    if not os.path.exists(path):
        print(f"FAIL  no {path}", file=sys.stderr)
        return 1
    n = painted = changed = desk = paint = 0
    best = 0
    prev = None
    for meta, px in fr.read(path):
        n += 1
        if meta["repeat"]:
            continue                      # the same picture as the record before
        vals, counts = np.unique(px, return_counts=True)
        c = int(vals.size)
        best = max(best, c)
        if c > PAINT:
            painted += 1
        if c >= 40:
            if counts.max() / px.size >= 0.45:
                desk += 1
            if float((px == 0xFFFF).sum()) / px.size >= 0.20:
                paint += 1
        if prev is None or not np.array_equal(prev, px):
            changed += 1
        prev = px
    print(f"frames={n} painted={painted} colours={best} changed={changed} "
          f"desk={desk} paint={paint}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
