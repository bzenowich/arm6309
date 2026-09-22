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


def tbox_equ(name):
    """An equate out of tbox.asm - the same discipline checkfiles.py uses.
    ⛔ The strike's geometry lives in TWO files (mktbox.py bakes the glyph
    positions, tbox.asm reads them) and a disagreement is silent: the ROM
    would blit from rows the host never drew. This is what makes them agree."""
    nd = os.environ.get("NITROS9DIR") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "nitros9")
    src = open(os.path.join(nd, "level2", "arm6309", "modules",
                            "tbox.asm")).read()
    m = re.search(r"^%s\s+equ\s+([^\s;*]+)" % re.escape(name), src, re.M)
    if not m:
        sys.exit("FAIL  checkv3text: tbox.asm has no %s equate" % name)
    return m.group(1)


def geometry():
    """⭐ THE STRIKE'S GEOMETRY, ASSERTED ACROSS THE TWO FILES THAT HOLD IT."""
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "software", "nitros9", "tools"))
    import mktbox as MK
    smax = int(tbox_equ("SK.Max"))
    slots = int(tbox_equ("SK.Slots"))
    bandh = int(tbox_equ("SK.BandH"))
    row = int(tbox_equ("SK.Row"))
    ok(smax == MK.STRIKE_MAXBAND,
       "tbox.asm SK.Max is mktbox.py STRIKE_MAXBAND",
       "%d vs %d" % (smax, MK.STRIKE_MAXBAND))
    end = row + slots * smax * bandh
    # ⚠ 480 is vidcpy3.asm's CpScratch, and tbox.asm's own header says so.
    ok(end <= 480,
       "⛔ the %d slots end above the copy engine's staging at row 480" % slots,
       "last strike row %d" % end)
    # ⚠ and the bench's own strip must not be inside them
    ok(not (row <= M.SK_Y < end),
       "⛔ ...and the bench composes its strip clear of them",
       "strip at row %d, strike %d-%d" % (M.SK_Y, row, end))
    return row, end


def main(out):
    geometry()
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

    # ⭐ the split: what a call costs before it draws, and what the card's
    # own half of the drawing costs
    if {"v3tnop", "v3t40", "v3t40o", "v3trct"} <= set(draw):
        nop = 1000 * draw["v3tnop"] / M.N
        compose = 1000 * draw["v3t40o"] / M.N
        whole = 1000 * draw["v3t40"] / M.N
        print("\n  ⭐ ESC $34, parsed and thrown away:          %.2f ms an escape" % nop)
        print("  ⭐ 40 characters COMPOSED, clipped away:     %.2f ms" % compose)
        print("  ⭐ the card's half of the same call:         %.2f ms  (%.0f%%)"
              % (whole - compose, 100 * (whole - compose) / whole))
        if "v3t01o" in draw:
            c1 = 1000 * draw["v3t01o"] / M.N
            # ⭐ the intercept of the CLIPPED line is everything a call pays
            # before it composes a glyph: the escape's bytes through CoArm,
            # the toolbox entry, the page mapped.  The slope is composition.
            slope = (compose - c1) / 39.0
            print("  ⭐ one character composed and clipped:       %.2f ms" % c1)
            print("  ⭐ so composing a character costs:           %.2f ms" % slope)
            print("  ⭐ and a call's FLOOR, before any glyph:     %.2f ms"
                  % (c1 - slope))
        ok(compose > 0 and whole > compose,
           "composing costs more than nothing and less than the whole call",
           "%.2f of %.2f ms" % (compose, whole))

    if {"v3t40", "v3t40p"} <= set(draw):
        clear = 1000 * draw["v3t40"] / M.N
        opaq = 1000 * draw["v3t40p"] / M.N
        print("\n  ⭐ 40 characters, transparent:               %.2f ms" % clear)
        print("  ⭐ 40 characters, OPAQUE (one run a row):    %.2f ms   %.2fx"
              % (opaq, clear / opaq if opaq else 0))
        ok(opaq < clear, "opaque text is faster than transparent",
           "%.2f ms vs %.2f ms" % (opaq, clear))

    # ⭐⭐ THE NUMBER THE STRIKE EXISTS FOR - docs/proportional-font.md §4.
    if {"v3tlow", "v3t40s"} <= set(draw):
        low = 1000 * draw["v3tlow"] / M.N
        sk = 1000 * draw["v3t40s"] / M.N
        print("  ⛔ the same line BELOW row 320:               %.2f ms" % low)
        # ⚠ v3tlow is ONE call and v3t40s is N, so the comparison is against
        # the composed baseline rather than against each other: what must be
        # true is that drawing low is not the SLOW path.  A composed line is
        # ~223 ms; a copied one ~54.  Anything near the former means RowCopy
        # refused and SkText fell back, which is exactly the defect the
        # disjoint test fixes and which draws the right pixels while doing it.
        if "v3t40p" in draw:
            opaq = 1000 * draw["v3t40p"] / M.N
            ok(low < opaq / 2,
               "⛔ drawing BELOW the strike's rows still COPIES, not composes",
               "%.2f ms vs %.2f ms composed" % (low, opaq))
            # ⭐⭐ AND IT IS THE STEADY STATE, which v3t40s is not: v3t40s is
            # the first strike user in the session and carries the BUILD,
            # amortised over N. v3tlow runs after it in the same (font, ramp),
            # so it is what a GUI redrawing a label actually pays.
            print("      ⭐ so the STEADY STATE is                %.2f ms"
                  " a line, %.0f us a glyph,  %.1fx"
                  % (low, (low - 2.68) / 40 * 1000, opaq / low))
            ok(low < sk,
               "⭐⭐ ...and it is CHEAPER than the run that paid for the build",
               "%.2f ms against %.2f ms, so the build is ~%.0f ms"
               % (low, sk, (sk - low) * M.N))

    if {"v3t40s", "v3t40p", "v3tnop"} <= set(draw):
        sk = 1000 * draw["v3t40s"] / M.N
        opaq = 1000 * draw["v3t40p"] / M.N
        floor = 1000 * draw["v3tnop"] / M.N
        print("  ⭐⭐ 40 characters, OUT OF THE STRIKE:        %.2f ms   %.2fx"
              % (sk, opaq / sk if sk else 0))
        print("      ...of which the call's floor is          %.2f ms" % floor)
        print("      so a glyph costs                         %.0f us"
              % ((sk - floor) / 40 * 1000))
        ok(sk < opaq,
           "⭐⭐ a 40-character line OUT OF THE STRIKE beats composing it opaque",
           "%.2f ms vs %.2f ms - %.1fx" % (sk, opaq, opaq / sk if sk else 0))
        # ⚠ AND A BOUND, because the point of the strike is that a glyph is a
        # rectangle and not a composition: the engine's own share of a 7x17
        # glyph is ~29 us, so anything above ~300 us a glyph means the copy is
        # not what the time is going on. §6 of the document owns that number.
        ok((sk - floor) / 40 * 1000 < 2000,
           "...and a glyph costs less than 2 ms, so it is a copy and not a compose",
           "%.0f us a glyph" % ((sk - floor) / 40 * 1000))

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

    # ⛔ and the pixels themselves: the two bands must be identical
    try:
        vram = open(os.path.join(out, "vram.bin"), "rb").read()
    except OSError:
        vram = b""
    if vram:
        # ⛔ THE LINE'S REAL WIDTH (mkv3text's own), not a generous guess: past
        # it the bands legitimately differ - screen on one side, untouched
        # margin on the other - and comparing that far compares the background.
        w = M.CACHE_W
        a = b"".join(vram[(M.CMP_Y1 + r) * 1024 + M.X:
                          (M.CMP_Y1 + r) * 1024 + M.X + w] for r in range(17))
        b = b"".join(vram[(M.CMP_Y2 + r) * 1024 + M.X:
                          (M.CMP_Y2 + r) * 1024 + M.X + w] for r in range(17))
        diff = sum(1 for p, q in zip(a, b) if p != q)
        ok(any(a) and diff == 0,
           "⛔ opaque text draws the SAME PIXELS as transparent",
           "%d of %d bytes differ" % (diff, len(a)))

        # ⭐ and the string cache: composed once in the margin, copied here
        c = b"".join(vram[(M.CMP_Y3 + r) * 1024 + M.X:
                          (M.CMP_Y3 + r) * 1024 + M.X + w] for r in range(17))
        dc = sum(1 for p, q in zip(b, c) if p != q)
        ok(any(c) and dc == 0,
           "⭐ a string COMPOSED OFF-SCREEN AND COPIED BACK is the same pixels",
           "%d of %d bytes differ" % (dc, len(b)))
        # ⚠ the control: the strip itself must be in the margin, or the blit
        # copied whatever happened to be there and the claim above is vacuous
        strip = b"".join(vram[(M.SK_Y + r) * 1024 + M.SK_X:
                              (M.SK_Y + r) * 1024 + M.SK_X + w] for r in range(17))
        # ⭐ and the strike: the same line, drawn as one copy a glyph
        k = b"".join(vram[(M.CMP_Y4 + r) * 1024 + M.X:
                          (M.CMP_Y4 + r) * 1024 + M.X + w] for r in range(17))
        dk = sum(1 for p, q in zip(b, k) if p != q)
        ok(any(k) and dk == 0,
           "⭐⭐ a line drawn OUT OF THE GLYPH STRIKE is the same pixels",
           "%d of %d bytes differ" % (dk, len(b)))

        # ⛔ AND BELOW THE STRIKE'S OWN ROWS - ca_row.asm's disjoint test.
        lo = b"".join(vram[(M.CMP_Y5 + r) * 1024 + M.X:
                           (M.CMP_Y5 + r) * 1024 + M.X + w] for r in range(17))
        dl = sum(1 for p, q in zip(b, lo) if p != q)
        ok(any(lo) and dl == 0,
           "⛔ ...and the same pixels BELOW row 320, where the strike lives",
           "%d of %d bytes differ" % (dl, len(b)))

        ok(any(strip) and strip == c,
           "⛔ ...and the margin really holds it, so the copy had a source",
           "%d of %d bytes differ from the band" %
           (sum(1 for p, q in zip(strip, c) if p != q), len(c)))

    print("\n%d claims, %d failed" % (ok_n + fail_n, fail_n))
    sys.exit(1 if fail_n else 0)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/arm6309-v3text")
