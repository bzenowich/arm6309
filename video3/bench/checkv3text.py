#!/usr/bin/env python3
"""checkv3text.py OUT - what run-v3text.sh's session says a text call costs.

Each stream was copied twice, to /nil and to the window; the difference is the
drawing.  ⚠ The per-character figure is a SLOPE, taken between two lengths, not
a total divided by a count: a call's fixed cost is most of a short line.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import mkv3text as M                                    # noqa: E402

ok_n = fail_n = 0


def ok(c, what, got=""):
    global ok_n, fail_n
    if c:
        ok_n += 1
        print("ok    %s%s" % (what, ("  (%s)" % got) if got else ""))
    else:
        fail_n += 1
        print("FAIL  %s  (%s)" % (what, got))


def spans(out):
    """Every command's wall time, from the serial console's timestamps: the
    moment its line was typed to the moment the next prompt came back."""
    rows = [l.split() for l in open(os.path.join(out, "serial.times"))]
    t = [int(a) / 1e12 for a, _ in rows]
    txt = bytes(int(b, 16) for _, b in rows).decode("latin-1")
    got, pos = {}, 0
    # ⚠ newline="": Python's text mode turns the \r into \n on the way in and
    # the split then yields ONE line, which reads as "nothing was timed".
    # The same CR/LF trap as demo-report.md §15.3, at the other end of the pipe.
    typed = open(os.path.join(out, "typed.txt"), newline="").read()
    for line in typed.split("\r"):
        if not line.startswith("copy "):
            continue
        i = txt.find(line, pos)
        if i < 0:
            continue
        j = txt.find("DD:", i + len(line))
        if j < 0:
            continue
        pos = j
        got[line] = t[j] - t[i + len(line)]
    return got


def main(out):
    s = spans(out)
    draw = {}
    print("  stream    to /nil     to /w5        drawing   per call")
    for n in M.TIMED:
        a = s.get("copy /dd/sys/%s /nil" % n)
        b = s.get("copy /dd/sys/%s /w5" % n)
        if a is None or b is None:
            ok(False, "%s was timed" % n, "missing")
            continue
        d = b - a
        draw[n] = d
        print("  %-8s %7.3f s  %7.3f s   %8.3f s  %8.2f ms"
              % (n, a, b, d, 1000 * d / M.N))

    for n in M.TIMED:
        ok(n in draw and draw[n] > 0,
           "%s draws for longer than it streams" % n,
           "%.3f s" % draw.get(n, 0))

    if len(draw) == len(M.TIMED):
        call1 = 1000 * draw["v3t01"] / M.N
        call40 = 1000 * draw["v3t40"] / M.N
        rect = 1000 * draw["v3trct"] / M.N
        per_ch = (call40 - call1) / 39.0
        print("\n  ⭐ a toolbox call that draws nothing (Rect): %.2f ms" % rect)
        print("  ⭐ a Text call of one character:             %.2f ms" % call1)
        print("  ⭐ each further character:                   %.2f ms" % per_ch)
        print("  ⭐ a 40-character line:                      %.2f ms" % call40)
        print("     (a 19-character line works out at           %.2f ms)"
              % (call1 + 18 * per_ch))

        ok(call1 > rect, "a Text call costs more than a Rect call",
           "%.2f ms vs %.2f ms" % (call1, rect))
        ok(per_ch > 0, "a longer line costs more", "%.2f ms a character" % per_ch)
        # ⚠ the shape of the answer, not the value: the per-character slope
        # must not be so small that the call is all overhead, nor so large that
        # the fixed cost vanishes - either would mean the streams are wrong
        ok(0.05 < per_ch < 20, "the per-character slope is a plausible number",
           "%.2f ms" % per_ch)
        lin = call1 + 19 * per_ch
        ok(abs(lin - 1000 * draw["v3t20"] / M.N) < 0.5 * lin,
           "20 characters lands near the line through 1 and 40",
           "%.2f ms measured, %.2f ms predicted"
           % (1000 * draw["v3t20"] / M.N, lin))

    print("\n%d claims, %d failed" % (ok_n + fail_n, fail_n))
    sys.exit(1 if fail_n else 0)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/arm6309-v3text")
