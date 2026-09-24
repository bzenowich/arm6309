#!/usr/bin/env python3
"""frame2png.py OUT [N] - the Nth frame (default: the last) of OUT/frames.bin as OUT/frame.png."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))
import frames as fr
from PIL import Image
out = sys.argv[1]
want = int(sys.argv[2]) if len(sys.argv) > 2 else None
last = None
for meta, px in fr.read(os.path.join(out, "frames.bin")):
    last = (meta, px)
    if want is not None and meta["n"] == want:
        break
meta, px = last
Image.fromarray(fr.rgb565_to_rgb8(px)).save(os.path.join(out, "frame.png"))
print(meta["n"], meta["t"], px.shape)
