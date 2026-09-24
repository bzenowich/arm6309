#!/usr/bin/env python3
"""mkvideo.py OUT video.mp4 - the NitrOS-9 session as a 1920 x 1080 H.264 file, silent.

    left    the video card's picture, 4:3 at 1280 x 960 as a VGA monitor shows it
            (software/archive/demo/tools/mkvideo.py's rule), a caption under it
    right   the serial console, /Term on the TL16C550C: 80 columns of the VGA
            font, each byte shown from the moment the emulator transmitted it
            (OUT/serial.times, from the emulator's SERIAL_TIMES)

It reads OUT/frames.bin and OUT/serial.times, and session.py's CAPTIONS.
ffmpeg comes from software/tools/fetch-ffmpeg.sh; FFMPEG=/path overrides it.
"""
import os, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "software", "tools"))
import frames as fr  # noqa: E402
import show  # noqa: E402
# ⭐ SESSION=session3 renders the video3 demo's captions instead.  The two
# sessions are different machines - video/ and video3 - and only their
# captions differ here, so the renderer takes the module by name.
import importlib  # noqa: E402
session = importlib.import_module(os.environ.get("SESSION", "session"))  # noqa: E402

W, H, FPS = 1920, 1080, 60
SX, SY, SW, SH = 0, 60, 1280, 960           # the monitor
PX, PY, COLS = 1280, 60, 80                  # the serial panel, 8 x 16 cells
ROWS = (H - PY - 6) // 16
STALE_S = 0.05                               # mkvideo.py's: display off is no frame

BG = np.array([22, 24, 28], np.uint8)
PANEL = np.array([8, 10, 12], np.uint8)
AMBER = np.array([255, 186, 80], np.uint8)
DIM = np.array([120, 126, 136], np.uint8)
WHITE = np.array([235, 238, 242], np.uint8)

GLYPH = np.unpackbits(show.font(16)[:, :, None], axis=2).astype(bool)    # (256, 16, 8)


def text_mask(s, scale=1):
    codes = np.frombuffer(s.encode("cp437", "replace"), np.uint8)
    m = GLYPH[codes].transpose(1, 0, 2).reshape(16, -1)
    return m.repeat(scale, 0).repeat(scale, 1) if scale > 1 else m


def put_text(img, x, y, s, colour, scale=1):
    m = text_mask(s, scale)
    h, w = m.shape
    w = min(w, img.shape[1] - x)
    img[y:y + h, x:x + w][m[:, :w]] = colour


class Terminal:
    def __init__(self):
        self.grid = np.full((ROWS, COLS), 32, np.uint8)
        self.row = self.col = 0

    def newline(self):
        self.row += 1
        if self.row == ROWS:
            self.grid[:-1] = self.grid[1:]
            self.grid[-1] = 32
            self.row = ROWS - 1

    def feed(self, b):
        if b == 0x0D:
            self.col = 0
        elif b == 0x0A:
            self.newline()
        elif b == 0x08:
            self.col = max(0, self.col - 1)
        elif b >= 0x20:
            if self.col == COLS:
                self.col = 0
                self.newline()
            self.grid[self.row, self.col] = b
            self.col += 1

    def render(self, cursor):
        m = GLYPH[self.grid].transpose(0, 2, 1, 3).reshape(ROWS * 16, COLS * 8)
        if cursor:
            c = min(self.col, COLS - 1)
            m[self.row * 16 + 13:self.row * 16 + 15, c * 8:c * 8 + 8] = True
        return m


def ffmpeg_path():
    if os.environ.get("FFMPEG"):
        return os.environ["FFMPEG"]
    return subprocess.run(["sh", os.path.join(ROOT, "software/tools/fetch-ffmpeg.sh")],
                          check=True, capture_output=True, text=True).stdout.strip()


def captions(times, data):
    """Each caption from the transmitted byte that completes its trigger, in order."""
    text = data.decode("latin-1")
    out, pos = [], 0
    for trig, cap in session.CAPTIONS:
        i = text.find(trig, pos)
        if i < 0:
            sys.exit(f"FAIL  caption trigger {trig!r} never reached the serial port")
        pos = i + len(trig)
        out.append((times[pos - 1], cap))
    return out


def main():
    out, mp4 = sys.argv[1], sys.argv[2]
    sync = dict(l.split() for l in open(os.path.join(out, "sync.txt")))
    end_s = int(sync["end_ps"]) / 1e12 + 2.0
    rows = [l.split() for l in open(os.path.join(out, "serial.times"))]
    times = [int(a) / 1e12 for a, _ in rows]
    data = bytes(int(b, 16) for _, b in rows)
    caps = captions(times, data)

    ff = ffmpeg_path()
    gop = FPS
    enc = subprocess.Popen(
        [ff, "-y", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high", "-pix_fmt", "yuv420p",
         "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0", "-movflags", "+faststart", mp4],
        stdin=subprocess.PIPE)

    img = np.empty((H, W, 3), np.uint8)
    img[:] = BG
    img[PY - 2:, PX:] = PANEL
    put_text(img, 16, 14, "arm6309  NitrOS-9 Level 2", WHITE, 2)
    put_text(img, PX + 8, 22, "/Term  serial console, TL16C550C", AMBER)
    off = np.zeros((SH, SW, 3), np.uint8)
    put_text(off, SW // 2 - 16 * 11, SH // 2 - 16, "display off", np.array([70, 74, 80], np.uint8), 2)

    term = Terminal()
    it = fr.read(os.path.join(out, "frames.bin"))
    pending = next(it, None)
    shown, shown_t, shown_key = None, -1.0, None
    scaled = off
    bi, ci = 0, -1
    panel_key = None
    maps = {}
    k = 0
    while True:
        t = k / FPS
        if t >= end_s:
            break
        # the picture
        latest = None
        while pending is not None and pending[0]["t"] <= t:
            latest = pending
            pending = next(it, None)
        if latest is not None:
            h, w = latest[1].shape
            if (h, w) not in maps:
                maps[(h, w)] = (np.minimum((np.arange(SH) * h) // SH, h - 1)[:, None],
                                np.minimum((np.arange(SW) * w) // SW, w - 1)[None, :])
            ry, rx = maps[(h, w)]
            shown, shown_t = fr.rgb565_to_rgb8(latest[1][ry, rx]), latest[0]["t"]
        live = shown is not None and t - shown_t <= STALE_S
        key = id(shown) if live else None
        if key != shown_key or latest is not None:
            img[SY:SY + SH, SX:SX + SW] = shown if live else off
            shown_key = key
        # the console
        changed = False
        while bi < len(times) and times[bi] <= t:
            term.feed(data[bi])
            bi += 1
            changed = True
        blink = int(t * 2) % 2 == 0
        if changed or panel_key != blink:
            m = term.render(blink)
            region = img[PY:PY + ROWS * 16, PX:PX + COLS * 8]
            region[:] = PANEL
            region[m] = AMBER
            panel_key = blink
        # the caption and the clock
        nci = ci
        while nci + 1 < len(caps) and caps[nci + 1][0] <= t:
            nci += 1
        if nci != ci:
            ci = nci
            img[SY + SH:H, SX:SX + SW] = BG
            put_text(img, SX + 16, SY + SH + 14, caps[ci][1][:78], WHITE, 2)
        if k % 6 == 0:
            img[8:52, PX - 440:PX - 8] = BG
            put_text(img, PX - 440, 14, f"machine time {t:6.1f} s", DIM, 2)
        enc.stdin.write(img.tobytes())
        k += 1
        if k % 1800 == 0:
            print(f"      {t:6.1f} s encoded", flush=True)
    enc.stdin.close()
    if enc.wait() != 0:
        sys.exit("FAIL  ffmpeg failed")
    print(f"ok    wrote {mp4}: {k} frames at {FPS} fps ({k / FPS:.1f} s)")


if __name__ == "__main__":
    main()
