#!/usr/bin/env python3
"""mkv3text.py OUT - the streams run-v3text.sh times.

⭐ WHAT THIS EXISTS TO ANSWER.  Nothing in this repository has ever measured a
ROM toolbox text call.  `video3/bench/README.md` says so ("⛔ Does not answer -
timing"), `demo-report.md` §13 says so, and the emulator's CALLTIME cannot help:
it resolves a module by scanning task 0's map, and CoArm is mapped into ArmIO's
two block windows only while a call is running, so it answers "the module never
appeared" (§14.4).

So this measures from the outside, which needs no emulator change: N identical
toolbox calls in a file, copied to a window, timed off the serial console's own
timestamps.

⛔ AND EVERY STREAM IS TIMED TWICE, once to the window and once to /nil.  The
difference is the drawing; what it subtracts is `copy`, RBF, SCF and the escape
parser walking the same bytes - which is most of a short stream's cost and
scales with the file, so the 40-character file would otherwise look slower than
it is for a reason that has nothing to do with text.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "software", "nitros9", "tools"))
import v3show as V                                      # noqa: E402

N = 25                                                  # calls a stream
X, Y = 16, 40                                           # where they draw
SAMPLE = "The quick brown fox jumps over the lazy dogs!"  # 44, trimmed below


def setup():
    """A screen of its own, white, with the cursor off."""
    s = bytearray()
    s += V.dwset(0x13, 0, 0, 80, 60, V.PAL["white"], 2, 2)
    s += V.SELECT + V.CURSOR_OFF
    s += V.palette()
    s += V.rect(0, 0, 640, 480, "white")
    return bytes(s)


def text_run(n):
    """N Text calls of an n-character string, all at the same place: the
    cost of drawing it is what is wanted, not of moving down the page."""
    line = SAMPLE[:n]
    assert len(line) == n, "SAMPLE is too short for %d" % n
    return b"".join(V.text(X, Y, line, "white") for _ in range(N))


def nop_run():
    """⭐ THE FLOOR.  ESC $34 is Border, which video3 has none of, so CoArm's
    table sends it to EscNop: one parameter collected, nothing done, no
    toolbox entered.  Three bytes an escape - what the parser costs and
    nothing else."""
    return V.esc(0x34, 0) * N


def off_run(n):
    """⭐ THE OTHER HALF.  The same Text call, below the window: TextAt still
    walks the glyphs and composes every row into TB.Buf, and BlitRow then
    clips the lot away - so this is COMPOSITION WITHOUT THE CARD, and what
    it is short of text_run(n) is RowPut's setup and the VDATA bytes."""
    line = SAMPLE[:n]
    return b"".join(V.text(X, 600, line, "white") for _ in range(N))


def rect_run():
    """⚠ The CONTROL for a toolbox call that draws no glyphs: same escape,
    same dispatch, same ROM page mapped - and a fill instead of text."""
    return b"".join(V.rect(X, Y, 8, 17, "panel") for _ in range(N))


STREAMS = [("v3tset", setup),
           ("v3tnop", nop_run),
           ("v3t01", lambda: text_run(1)),
           ("v3t10", lambda: text_run(10)),
           ("v3t20", lambda: text_run(20)),
           ("v3t40", lambda: text_run(40)),
           ("v3t01o", lambda: off_run(1)),
           ("v3t40o", lambda: off_run(40)),
           ("v3trct", rect_run)]

# what the timing script copies, in order: each one to /nil and to the window
TIMED = ["v3tnop", "v3t01", "v3t10", "v3t20", "v3t40",
         "v3t01o", "v3t40o", "v3trct"]


def main(out):
    os.makedirs(out, exist_ok=True)
    for name, fn in STREAMS:
        b = fn()
        open(os.path.join(out, name), "wb").write(b)
        print("ok    %s/%s: %d bytes" % (out, name, len(b)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/v3text")
