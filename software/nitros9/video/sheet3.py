#!/usr/bin/env python3
"""sheet3.py OUT [EVERY] - the video3 session as contact sheets, for review.

    OUT/sheet-1.png, sheet-2.png ...   a tile every EVERY seconds (default 3) of
                                       machine time, 6 across, 8 down a page
    OUT/sheet-scenes.png               the last frame before each caption -
                                       every scene as it was left

Each tile is the card's picture at full size (a 640 x 400 or x 200 screen is
stretched to 480 rows), with its machine time and the
caption that is on screen then (session3.py CAPTIONS, timed by the serial
console exactly as mkvideo.py times them).  The full-motion H.264 file takes
minutes to encode; this takes seconds, and is what a pass is reviewed from.
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "software", "demo", "tools"))
sys.path.insert(0, HERE)
import frames as fr  # noqa: E402

TW, TH, COLS, ROWS = 640, 480, 6, 8        # the card's own pixels, one for one
LABEL = 48
FONT = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", 18)


def captions(out, session):
    rows = [l.split() for l in open(os.path.join(out, "serial.times"))]
    times = [int(a) / 1e12 for a, _ in rows]
    text = bytes(int(b, 16) for _, b in rows).decode("latin-1")
    caps, pos = [], 0
    for trig, cap in session.CAPTIONS:
        i = text.find(trig, pos)
        if i < 0:
            print("warn  caption trigger %r never reached the serial port" % trig)
            continue
        pos = i + len(trig)
        caps.append((times[pos - 1], cap))
    return caps


def caption_at(caps, t):
    cur = ""
    for ct, c in caps:
        if ct <= t:
            cur = c
    return cur


def tile(px, label):
    im = Image.fromarray(fr.rgb565_to_rgb8(px))
    if im.size != (TW, TH):
        im = im.resize((TW, TH), Image.NEAREST)
    t = Image.new("RGB", (TW, TH + LABEL), (16, 18, 22))
    t.paste(im, (0, 0))
    d = ImageDraw.Draw(t)
    for k, line in enumerate(label[:2]):
        d.text((4, TH + 1 + 22 * k), line, font=FONT, fill=(255, 190, 80) if k == 0 else (200, 204, 210))
    return t


def page(tiles, path):
    rows = (len(tiles) + COLS - 1) // COLS
    sh = Image.new("RGB", (COLS * TW, rows * (TH + LABEL)), (0, 0, 0))
    for i, t in enumerate(tiles):
        sh.paste(t, ((i % COLS) * TW, (i // COLS) * (TH + LABEL)))
    sh.save(path)
    print("ok    %s: %d tiles" % (path, len(tiles)))


def main():
    out = sys.argv[1]
    every = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    session = __import__(os.environ.get("SESSION", "session3"))
    caps = captions(out, session)
    tiles, nxt = [], 0.0
    before = {}                        # caption index -> the last frame before it
    ci = 0
    prev = None
    for m, px in fr.read(os.path.join(out, "frames.bin")):
        t = m["t"]
        while ci < len(caps) and t >= caps[ci][0]:
            if prev is not None:
                before[ci] = prev
            ci += 1
        if t >= nxt:
            tiles.append(tile(px, ["%.1f s  frame %d" % (t, m["n"]), caption_at(caps, t)]))
            nxt = t + every
        prev = (t, m["n"], px)          # frames.read never changes a picture it has yielded
    if prev is not None:
        before[len(caps)] = prev
    for p in range(0, len(tiles), COLS * ROWS):
        page(tiles[p:p + COLS * ROWS], os.path.join(out, "sheet-%d.png" % (p // (COLS * ROWS) + 1)))
    scenes = []
    for k in sorted(before):
        t, n, px = before[k]
        name = caps[k - 1][1] if k else "boot"
        scenes.append(tile(px, ["%.1f s  frame %d - the scene as left" % (t, n), name]))
    page(scenes, os.path.join(out, "sheet-scenes.png"))


if __name__ == "__main__":
    main()
