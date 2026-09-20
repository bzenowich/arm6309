#!/usr/bin/env python3
"""checkv3sd.py OUT - did a picture get PAINTED in this run?

One run of video3/bench/run-v3sd.sh, read from OUT/frames.bin, reduced to the
four numbers that bench makes its claims from:

    frames=<n> painted=<k> colours=<c> changed=<d>

    n   frame records in the recording
    c   the most distinct colours any one frame showed
    k   frames showing more than PAINT_COLOURS (default 12) of them
    d   frames whose picture differs from the one before

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

⛔ Its exit code is 0 unless the recording cannot be read; the numbers are
the answer and the shell script makes the claims.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "software", "demo", "tools"))
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
    n = painted = changed = 0
    best = 0
    prev = None
    for meta, px in fr.read(path):
        n += 1
        if meta["repeat"]:
            continue                      # the same picture as the record before
        c = int(np.unique(px).size)
        best = max(best, c)
        if c > PAINT:
            painted += 1
        if prev is None or not np.array_equal(prev, px):
            changed += 1
        prev = px
    print(f"frames={n} painted={painted} colours={best} changed={changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
