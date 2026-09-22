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
import mktbox as T                                      # noqa: E402

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


def opaque_run(n):
    """⭐ The same line with FONT bit 2 set: tbox.asm fills the row with the
    ramp's paper instead of KEY, so BlitRow emits ONE run.  What it saves is
    the KEY fill, the run scan and ~10 RowPut calls a row; what it costs is
    the paper's bytes over VDATA."""
    line = SAMPLE[:n]
    # ⛔ textp, NOT text.  Call 0 picks the strike when it can (2026-09-22),
    # and an opaque 40-character line is exactly when it can - so this would
    # have measured the strike twice and reported it as 1.0x faster than
    # itself.  TTextP (13) is the composed path, kept for this.
    return b"".join(V.textp(X, Y, line, "white", opaque=True) for _ in range(N))


CMP_Y1, CMP_Y2, CMP_N = 100, 140, 40         # the two bands checkv3text compares
# ⭐ the third band: the same line again, but COMPOSED ONCE IN THE MARGIN and
# copied here by the engine. docs/proportional-font.md §4 and keyed-copy.md
# §3.2 - the string cache. It must be pixel-identical to the opaque band.
CMP_Y3 = 180
CMP_Y4 = 240                                 # ⭐ the same line out of the STRIKE
# ⭐ AND THE SAME LINE BELOW ROW 320, which is where the strike itself lives.
# RowCopy used to refuse a destination at or after its source in raster order,
# so every glyph drawn lower than its own band was silently composed instead
# of copied (ca_row.asm, the disjoint test). This band is that gate.
CMP_Y5 = 350
# ⛔ THE STRIP GOES ABOVE THE STRIKE.  Three slots of 51 rows start at 320, so
# the margin from 320 to 473 belongs to tbox.asm's SK.* and 480-510 to
# CpScratch. 400 was inside slot 1 and the strip was being overwritten by the
# next strike built.
SK_X, SK_Y = 640, 240                        # where the strip is composed
CACHE_W = T.text_width(SAMPLE[:CMP_N], False)  # the line's real width, 225
MARK1, MARK2 = 200, 220                      # the two 8x1 markers, before and after


def compare_run():
    """⛔ THE CORRECTNESS GATE for opaque text.  The same line twice, the
    transparent path at CMP_Y1 and the opaque one at CMP_Y2, on paper that
    IS the ramp's paper.  Every pixel of the two bands must come out
    identical - an optimisation that changes how pixels are made has to
    prove they are the same pixels."""
    line = SAMPLE[:CMP_N]
    return (V.text(X, CMP_Y1, line, "white")
            + V.textp(X, CMP_Y2, line, "white", opaque=True))


def cache_run():
    """⛔ THE CORRECTNESS GATE for the string cache.  The same line composed
    ONCE into the margin with TStrip and then copied onto the screen with
    TBlit, against the opaque band that composed it in place.  Every pixel has
    to match: a 145x saving that draws different pixels is not a saving.
    ⚠ The strip is composed at x=640, which is outside every window there is -
    so this also proves TStrip really does take the clip off and put it back."""
    line = SAMPLE[:CMP_N]
    # ⛔ THE TEXT'S REAL WIDTH, NOT A GUESS.  `8 * CMP_N + 16` was 336 where
    # the line is 225, and the extra 111 columns are what made this claim fail
    # for a day: BEYOND the text, the in-place band shows the WHITE SCREEN the
    # setup drew and the strip shows margin nobody has written. The glyphs
    # were identical the whole time. text_width() is what tbox.asm's TextW
    # answers, so the two cannot disagree.
    w = T.text_width(line, False)
    # ⚠ THREE BLITS, AND THE TWO SMALL ONES ARE INSTRUMENTS.  A hang in the
    # middle one used to stop the whole session with nothing to say; a marker
    # before and after says whether the call path works at all and whether it
    # ever got past.  They are cheap and they stay.
    import os
    if os.environ.get("BLITZERO"):
        # ⚠ THE SECOND BISECT: a blit of ZERO size.  RowCopy returns at its
        # first test without touching the card at all, so this exercises the
        # whole call and return path - escape, dispatch, TVCALL, TbVec, and
        # back - and nothing else.  If THIS wedges, the copy engine is
        # innocent and the fault is in how RowCopy is reached or returned from.
        return (V.strip(SK_X, SK_Y, line, "white", opaque=True)
                + V.blit(SK_X, SK_Y, X, MARK1, 0, 0))
    if os.environ.get("STRIPONLY"):
        # ⚠ THE BISECT: the compose half alone.  If the session still wedges
        # with no TBlit in it at all, the copy engine is not the cause.
        return V.strip(SK_X, SK_Y, line, "white", opaque=True)
    return (V.strip(SK_X, SK_Y, line, "white", opaque=True)
            + V.blit(SK_X, SK_Y, X, MARK1, 8, 1)
            + V.blit(SK_X, SK_Y, X, CMP_Y3, w, 17)
            + V.blit(SK_X, SK_Y, X, MARK2, 8, 1))


def sk_run(n):
    """⭐ THE STRIKE, TIMED - docs/proportional-font.md §4.  N calls of the
    same line out of the glyph strike.  The FIRST builds it, at about what
    drawing 95 characters costs; the other N-1 are one copy-engine rectangle
    a glyph, which is what a GUI redrawing a label actually pays.
    ⚠ So this measures the STEADY STATE, and the build is amortised over N -
    which is the honest thing to compare against opaque_run, because a strike
    that is rebuilt every call is not a cache and nobody should use it."""
    line = SAMPLE[:n]
    return b"".join(V.sktext(X, Y, line, "white") for _ in range(N))


def strike_run():
    """⛔ THE CORRECTNESS GATE for the glyph strike (docs/proportional-font.md
    §4).  The same line drawn out of the strike, against the opaque band that
    composed it in place.  Every pixel has to match: a strike that draws
    different pixels is a different font, not a faster one."""
    return V.sktext(X, CMP_Y4, SAMPLE[:CMP_N], "white")


def low_run():
    """⛔ THE GATE FOR ca_row.asm's DISJOINT TEST.  The same line out of the
    strike, drawn BELOW row 320 - which is below the bands it is copied from.
    Under the old raster-order rule RowCopy refused every one of these copies
    and SkText composed instead: the right pixels, four times slower, and
    nothing said so. Compared against the composed band, it is also the proof
    that a copy upward in raster order is safe when the rectangles are
    disjoint, which they always are here (source x >= 640, destination
    x < 640)."""
    line = SAMPLE[:CMP_N]
    # ⚠ N of them, because this is a TIMED stream as well as a pixel gate:
    # the pixels say it is right and the clock says it took the fast path.
    return b"".join(V.sktext(X, CMP_Y5, line, "white") for _ in range(N))


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
           ("v3t40p", lambda: opaque_run(40)),
           ("v3tcmp", compare_run),
           ("v3tcache", cache_run),
           ("v3tstrk", strike_run),
           ("v3t40s", lambda: sk_run(40)),
           ("v3tlow", low_run),
           ("v3t01o", lambda: off_run(1)),
           ("v3t40o", lambda: off_run(40)),
           ("v3trct", rect_run)]

# what the timing script copies, in order: each one to /nil and to the window
TIMED = ["v3tnop", "v3t01", "v3t10", "v3t20", "v3t40", "v3t40p", "v3t40s",
         "v3tlow",
         "v3t01o", "v3t40o", "v3trct"]


def main(out):
    os.makedirs(out, exist_ok=True)
    for name, fn in STREAMS:
        b = fn()
        open(os.path.join(out, name), "wb").write(b)
        print("ok    %s/%s: %d bytes" % (out, name, len(b)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/v3text")
