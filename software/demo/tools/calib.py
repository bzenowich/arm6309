#!/usr/bin/env python3
"""Read bench/calib.asm's answers off demo_tb's frames.

    python3 software/demo/tools/calib.py OUT

Prints, per phase, what the card did: on which displayed line each display-list
MOVE took effect when GO was issued at VBLANK's fall (phase 0) or once HBLANK
had also fallen (phase 1); the glyph, rectangle and read-back of phase 2; and
the ring rows a VMODE 00 frame showed with VSCROLL = 300 (phase 3).
"""
import os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import frames as fr

out = sys.argv[1]
pal = fr.palette565()
inv = np.full(65536, -1, dtype=np.int32)
inv[pal] = np.arange(256)
RED = 0xF800


def line_shift(idx_row):
    """The HSCROLL a stripe row was scanned with: ring column block c is index c + 16."""
    b0 = int(idx_row[0]) - 16
    if not 0 <= b0 < 128:
        return None
    for x in range(1, 9):
        if idx_row[x] != idx_row[0]:
            return (b0 * 8 + (8 - x)) % 1024
    return None


seen = {}
for meta, px in fr.read(os.path.join(out, "frames.bin"), legacy="--legacy" in sys.argv):
    ph = meta["camk"]
    if ph in (0, 1) and px.shape == (480, 640):
        idx = inv[px]
        shifts = [line_shift(idx[y]) for y in range(480)]
        # block 10 is index 26 at shift 0; find the colour of index-26 pixels per line
        changes = []
        prev = None
        for y in range(480):
            if shifts[y] != prev:
                changes.append((y, shifts[y]))
                prev = shifts[y]
        redlines = [y for y in range(480) if (px[y] == RED).any()]
        key = (ph, tuple(changes), (redlines[0], redlines[-1]) if redlines else None)
        seen.setdefault(key, []).append(meta["n"])
    elif ph == 2 and px.shape == (480, 640):
        key = ("p2", meta["herok"], meta["missed"])
        if key not in seen:
            idx = inv[px]
            print(f"phase 2, frame {meta['n']}: VDATA reads $C20A={meta['herok']:04X} $C225={meta['missed']:04X}"
                  "  (want 1111 1212 - indices 17 17 18 18)")
            for y in range(398, 410):
                print(f"   row {y}: sprite@100 " + " ".join(f"{int(v):02X}" for v in idx[y, 98:110])
                      + "   mask@120 " + " ".join(f"{int(v):02X}" for v in idx[y, 118:130]))
            ys = [y for y in range(480) if idx[y, 204] == 0x1C]
            xs = [x for x in range(640) if idx[390, x] == 0x1C]
            print(f"   rectangle index $1C: rows {ys[0] if ys else None}..{ys[-1] if ys else None}, "
                  f"columns {xs[0] if xs else None}..{xs[-1] if xs else None} (want 380..399, 200..215)")
        seen.setdefault(key, []).append(meta["n"])
    elif ph in (4, 5) and px.shape == (480, 640):
        idx = inv[px]
        key = ("cpu", ph, tuple(sorted(set(line_shift(idx[y]) for y in range(480)))))
        seen.setdefault(key, []).append(meta["n"])
    elif ph == 3 and px.shape[1] == 640 and meta["vmode"] == 0:
        key = ("p3",)
        if key not in seen:
            idx = inv[px]
            print(f"phase 3, frame {meta['n']}: {px.shape[0]} lines; doubled: {np.array_equal(px[0::2], px[1::2])}")
            ys = [y for y in range(px.shape[0]) if idx[y, 204] == 0x1C]
            gy = [y for y in range(px.shape[0]) if idx[y, 107] == 0xFF]
            print(f"   rectangle on lines {ys[0] if ys else None}..{ys[-1] if ys else None} (ring rows 380..399 at VSCROLL 300 -> lines 160..199)")
            print(f"   sprite glyph column 107 white on lines {gy} (ring rows 400,407)")
        seen.setdefault(key, []).append(meta["n"])

for key, ns in seen.items():
    if key[0] == "cpu":
        print(f"phase {key[1]} (CPU HSCROLL = {3 if key[1] == 4 else 5}): {len(ns)} frames, shifts seen {key[2]}")
    if key[0] in (0, 1):
        print(f"phase {key[0]}: {len(ns)} frames (first {ns[0]}): shift changes (line, HSCROLL) {list(key[1])}; "
              f"LUT[16] red on lines {key[2]}")
