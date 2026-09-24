#!/usr/bin/env python3
"""checkv3copyn.py OUT N - SS.CopyN lands the same pixels as SS.Copy.

⛔ THE POINT.  `SS.CopyN` walks a table of rectangles inside the driver, and
until this existed nothing asked whether it walks it correctly - `v3cpyb` only
timed it.  A walk that stops one entry short, runs one entry long, or reuses a
stale block keeps every timing figure honest and puts the pixels in the wrong
place.

The two dumps are the SAME rectangles by the two paths.  They must be equal
byte for byte, and the screen must not be blank - a comparison of two empty
screens passes for the wrong reason, which is why `drew` is a claim of its own.
"""
import os
import sys

ok_n = fail_n = 0


def ok(c, what, got=""):
    global ok_n, fail_n
    if c:
        ok_n += 1
        print("ok    %s%s" % (what, ("  (%s)" % got) if got else ""))
    else:
        fail_n += 1
        print("FAIL  %s  (%s)" % (what, got))


def main(out, n):
    a = open(os.path.join(out, "list.bin"), "rb").read()
    b = open(os.path.join(out, "one.bin"), "rb").read()
    ok(len(a) == len(b) == 512 * 1024, "both dumps are a whole VRAM",
       "%d and %d bytes" % (len(a), len(b)))

    # the screen, where the rectangles landed
    scr_a = b"".join(a[r * 1024:r * 1024 + 640] for r in range(480))
    scr_b = b"".join(b[r * 1024:r * 1024 + 640] for r in range(480))
    diff = sum(1 for p, q in zip(scr_a, scr_b) if p != q)
    ok(diff == 0, "⛔ SS.CopyN lands the SAME PIXELS as SS.Copy",
       "%d of %d bytes differ" % (diff, len(scr_a)))

    # ⚠ and that anything was drawn at all: two blank screens match
    bg = max(set(scr_b), key=scr_b.count)
    drew = sum(1 for p in scr_b if p != bg)
    ok(drew > 5000, "⚠ and the rectangles actually drew something",
       "%d bytes are not the background" % drew)

    # the LAST rectangle in particular - a walk that stops short loses it
    last_x, last_y = (n - 1) * 3, (n - 1) * 5
    px = b[last_y * 1024 + last_x]
    ok(px != bg, "the LAST entry of the table was walked",
       "rectangle %d at (%d, %d) is $%02X" % (n - 1, last_x, last_y, px))

    print("\n%d claims, %d failed" % (ok_n + fail_n, fail_n))
    sys.exit(1 if fail_n else 0)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 24)
