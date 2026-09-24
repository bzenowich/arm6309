#!/usr/bin/env python3
"""clip.py REC OUT.mp4 [options] - a recording, as an H.264 file or a contact sheet.

The second half of every program's demo video (software/<program>/video/
run-video.sh); record.sh is the first.  REC is the directory record.sh wrote:
REC/frames.bin, the emulator's recording.

  --from T --to T     the window, in machine seconds
  --all               the whole recording
  --scene CMD         ⭐ the program's own run: from the moment the shell has
                      echoed CMD to the moment it echoes --end (default
                      "echo DONE-arm6309", which is only typed once CMD has
                      returned), read off REC/serial.times - less the blank
                      frames at either end while the screen is being set up
  --auto              the SCENE: from the first frame whose commonest colour
                      covers less than 70 % of the screen (a scene, not a text
                      console) to the last - after --after seconds if given
  --after T           ignore everything before T (the boot) when looking
  --pad S             seconds of context kept either side of an --auto window
  --until TEXT        end --tail seconds after the console first shows TEXT
  --tail S            (default 3)
  --hold S            no still picture lasts longer than S seconds: time spent
                      on frames identical to the one before, beyond S, is cut
                      (a program loading, or waiting, is not something to watch)
  --max S             at most S seconds of video
  --sheet PNG         a contact sheet of --tiles frames instead of the video
  --tiles N           tiles on the sheet                         (default 12)
  --scale K           pixels a card pixel                        (default 2)
  --fps F             frames a second of video                   (default 30)
  --keep              leave REC/frames.bin; it is deleted otherwise

These are the settings the scroll, zelda and pinball clips were made with on
2026-09-23 - 2x nearest-neighbour, 30 fps, x264 -preset slow -crf 20, faststart
- which were typed as one-off commands then and are a program now.

⭐ REVIEW THE SHEET FIRST.  It takes seconds; the video takes minutes, and a
demo pass is approved from its sheet before the full-motion file is made.
"""
import argparse
import os
import shutil
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "software", "tools"))
import frames as fr                                     # noqa: E402
from PIL import Image, ImageDraw                        # noqa: E402


def rgb(px):
    d = px.astype(np.int32)
    return np.dstack([((d >> 11) & 31) * 255 // 31,
                      ((d >> 5) & 63) * 255 // 63,
                      (d & 31) * 255 // 31]).astype(np.uint8)


def is_scene(px):
    """a scene rather than a text console: no one colour covers 70 % of it"""
    _, c = np.unique(px[::4, ::4], return_counts=True)
    return c.max() < 0.7 * c.sum()


def blank(px):
    """a screen being cleared, or set up and not yet drawn on: one colour
    near enough, or no more than three - a pointer and a stray row on a flat
    field is still a blank screen, where every real scene has dozens"""
    _, c = np.unique(px[::4, ::4], return_counts=True)
    return c.max() >= 0.98 * c.sum() or len(c) <= 3


def serial_window(rec, cmd, end):
    """(t0, t1) in seconds: after CMD's echo, up to END's - from serial.times"""
    path = os.path.join(rec, "serial.times")
    if not os.path.exists(path):
        sys.exit("FAIL  clip.py: no %s (record.sh writes it)" % path)
    text, times = [], []
    for line in open(path):
        ps, hx = line.split()
        text.append(chr(int(hx, 16)))
        times.append(int(ps) / 1e12)
    s = "".join(text)
    i = s.find(cmd)
    if i < 0:
        sys.exit("FAIL  clip.py: the console never showed %r" % cmd)
    t0 = times[i + len(cmd) - 1]
    j = s.find(end, i + len(cmd))
    t1 = times[j] if j >= 0 else None
    return t0, t1


def ffmpeg():
    for c in (os.path.join(ROOT, ".tools", "ffmpeg", "ffmpeg"), shutil.which("ffmpeg")):
        if c and os.path.exists(c):
            return c
    subprocess.run(["sh", os.path.join(ROOT, "software", "tools", "fetch-ffmpeg.sh")], check=True)
    return os.path.join(ROOT, ".tools", "ffmpeg", "ffmpeg")


def window(path, a):
    """the (t0, t1) to encode, and the picture size"""
    if a.scene:
        t0, t1 = serial_window(a.rec, a.scene, a.end)
        first = last = None
        shape = None
        for m, px in fr.read(path):
            t = m["t"]
            if t < t0:
                continue
            if t1 is not None and t > t1:
                break
            shape = px.shape
            if not blank(px):
                first = t if first is None else first
                last = t
        if first is None:
            sys.exit("FAIL  clip.py: nothing but blank frames after %r" % a.scene)
        return max(t0, first - a.pad), last + a.pad, shape
    if a.all or (a.from_ is not None and a.to is not None and not a.auto):
        t0 = t1 = None
        for m, px in fr.read(path):
            shape = px.shape
            t0 = m["t"] if t0 is None else t0
            t1 = m["t"]
            if not a.all:
                return a.from_, a.to, shape
        return t0, t1, shape
    t0 = t1 = None
    shape = None
    last = None
    for m, px in fr.read(path):
        t = m["t"]
        shape = px.shape
        last = t
        if t < a.after:
            continue
        if is_scene(px):
            if t0 is None:
                t0 = t
            t1 = t
    if t0 is None:
        sys.exit("FAIL  clip.py: no scene in %s after %.1f s - use --from/--to" % (path, a.after))
    t0 = max(0.0, t0 - a.pad)
    t1 = min(last, t1 + a.pad)
    if a.from_ is not None:
        t0 = a.from_
    if a.to is not None:
        t1 = a.to
    return t0, t1, shape


def frames_in(path, t0, t1, hold):
    """(effective seconds from t0, meta, pixels) for the window, with every still
    stretch longer than HOLD cut down to HOLD"""
    cut = 0.0
    still = None
    prev = None
    for m, px in fr.read(path):
        t = m["t"]
        if t < t0:
            prev = t
            continue
        if t > t1:
            return
        if hold is not None and m["repeat"] and prev is not None:
            still = prev if still is None else still
            if t - still > hold:
                cut += t - prev
                prev = t
                continue
        elif not m["repeat"]:
            still = None
        prev = t
        yield t - t0 - cut, m, px


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("rec")
    ap.add_argument("out")
    ap.add_argument("--from", dest="from_", type=float)
    ap.add_argument("--to", type=float)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--scene")
    ap.add_argument("--end", default="echo DONE-arm6309")
    ap.add_argument("--until")
    ap.add_argument("--tail", type=float, default=3.0)
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--after", type=float, default=0.0)
    ap.add_argument("--pad", type=float, default=0.5)
    ap.add_argument("--max", type=float)
    ap.add_argument("--hold", type=float)
    ap.add_argument("--sheet")
    ap.add_argument("--tiles", type=int, default=12)
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.rec, "frames.bin")
    if not os.path.exists(path):
        sys.exit("FAIL  clip.py: no %s - run record.sh first" % path)
    t0, t1, (h, w) = window(path, a)
    if a.until:
        t1 = min(t1, serial_window(a.rec, a.until, a.until)[0] + a.tail)
    if a.max and t1 - t0 > a.max:
        t1 = t0 + a.max
    print("      window %.2f .. %.2f s of machine time (%.1f s), %d x %d" % (t0, t1, t1 - t0, w, h))

    if a.sheet:
        cols = 3
        rows = (a.tiles + cols - 1) // cols
        tw, th = w // 2, h // 2
        length = 0.0
        for te, m, px in frames_in(path, t0, t1, a.hold):
            length = te
        want = [length * k / max(1, a.tiles - 1) for k in range(a.tiles)]
        sheet = Image.new("RGB", (cols * tw, rows * (th + 16)), (18, 18, 24))
        d = ImageDraw.Draw(sheet)
        i = 0
        for te, m, px in frames_in(path, t0, t1, a.hold):
            while want and te >= want[0] - 1e-9:
                x, y = (i % cols) * tw, (i // cols) * (th + 16)
                sheet.paste(Image.fromarray(rgb(px)).resize((tw, th), Image.LANCZOS), (x, y + 16))
                d.text((x + 4, y + 3), "%.1f s" % m["t"], fill=(255, 205, 90))
                want.pop(0)
                i += 1
            if not want:
                break
        os.makedirs(os.path.dirname(os.path.abspath(a.sheet)), exist_ok=True)
        sheet.save(a.sheet)
        print("ok    %s: %d tiles" % (a.sheet, i))
        return

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    W, H = w * a.scale, h * a.scale
    enc = subprocess.Popen([ffmpeg(), "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", "%dx%d" % (W, H), "-r", "%g" % a.fps, "-i", "-", "-an",
                            "-c:v", "libx264", "-preset", "slow", "-crf", "20",
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart", a.out],
                           stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    nxt, n = 0.0, 0
    end = t1 - t0
    for te, m, px in frames_in(path, t0, t1, a.hold):
        if px.shape != (h, w):          # a mode change inside the window: letterbox it
            canvas = np.zeros((h, w), px.dtype)
            canvas[:min(h, px.shape[0]), :min(w, px.shape[1])] = px[:h, :w]
            px = canvas
        while nxt <= te and nxt <= end:
            enc.stdin.write(Image.fromarray(rgb(px)).resize((W, H), Image.NEAREST).tobytes())
            n += 1
            nxt += 1.0 / a.fps
    enc.stdin.close()
    if enc.wait() != 0:
        sys.exit("FAIL  ffmpeg failed on %s" % a.out)
    print("ok    %s: %d frames = %.1f s at %d x %d" % (a.out, n, n / a.fps, W, H))
    if not a.keep:
        os.remove(path)


if __name__ == "__main__":
    main()
