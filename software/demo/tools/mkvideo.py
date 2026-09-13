#!/usr/bin/env python3
"""Turn demo_tb's recordings into an H.265 file.

    python3 software/demo/tools/mkvideo.py OUT demo.mp4 [--fps 70]

  picture   frames.bin: every frame the connector carried, with the simulated
            time it started. Resampled to a constant rate by showing, at each
            output instant, the latest frame that had begun - which is what a
            monitor does - so a stall in the machine is a held frame in the
            file, not a shortened video.
  sound     card.dac through audio/tools/dacwav, which renders the four
            converter pairs through the card's analogue chain. It starts at
            colour clock 0, which sync.txt places on the same clock.

Both screen modes are shown the way a VGA monitor shows them - full screen,
4:3 - at 1280 x 960: 640 x 480 is doubled, 640 x 400 is doubled across and
stretched 2.4x down with whole rows repeated, so pixels stay sharp.

ffmpeg comes from software/tools/fetch-ffmpeg.sh (libx265); FFMPEG=/path overrides it.
"""
import os, subprocess, sys
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import frames as fr

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OW, OH = 1280, 960


def ffmpeg_path():
    if os.environ.get("FFMPEG"):
        return os.environ["FFMPEG"]
    return subprocess.run(["sh", os.path.join(ROOT, "software/tools/fetch-ffmpeg.sh")],
                          check=True, capture_output=True, text=True).stdout.strip()


def rows_map(h):
    """Source row for each of OH output rows."""
    return np.minimum((np.arange(OH) * h) // OH, h - 1)


def scale(rgb):
    h, w = rgb.shape[:2]
    if w == 0 or h == 0:
        return np.zeros((OH, OW, 3), np.uint8)
    cols = np.minimum((np.arange(OW) * w) // OW, w - 1)
    return rgb[rows_map(h)][:, cols]


def main():
    out, mp4 = sys.argv[1], sys.argv[2]
    fps = float(sys.argv[sys.argv.index("--fps") + 1]) if "--fps" in sys.argv else 70.0
    sync = dict(l.split() for l in open(os.path.join(out, "sync.txt")))
    end_s = int(sync.get("end_ps", 0)) / 1e12

    wav = os.path.join(out, "card.wav")
    subprocess.run([os.path.join(ROOT, "build-host", "dacwav"), wav, os.path.join(out, "card.dac")],
                   check=True, stdout=subprocess.DEVNULL)
    audio_offset = int(sync["cc0_ps"]) / 1e12

    ff = ffmpeg_path()
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OW}x{OH}", "-r", f"{fps}", "-i", "-",
           "-itsoffset", f"{audio_offset:.6f}", "-i", wav,
           "-map", "0:v", "-map", "1:a",
           "-c:v", "libx265", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
           "-tag:v", "hvc1", "-x265-params", "log-level=error",
           "-c:a", "aac", "-b:a", "192k", "-shortest", mp4]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    it = fr.read(os.path.join(out, "frames.bin"))
    cur = np.zeros((OH, OW, 3), np.uint8)
    pending = next(it, None)
    k = 0
    last_t = 0.0
    while True:
        t = k / fps
        if end_s and t >= end_s:
            break
        advanced = False
        while pending is not None and pending[0]["t"] <= t:
            meta, px = pending
            last_t = meta["t"]
            if not advanced or True:
                cur_px, cur_meta = px, meta
            advanced = True
            pending = next(it, None)
        if advanced:
            cur = scale(fr.rgb565_to_rgb8(cur_px))
        elif pending is None and t > last_t + 0.5:
            break
        enc.stdin.write(cur.tobytes())
        k += 1
        if k % 700 == 0:
            print(f"      {t:6.1f} s encoded", flush=True)
    enc.stdin.close()
    rc = enc.wait()
    if rc != 0:
        sys.exit(f"FAIL  ffmpeg exited {rc}")
    print(f"ok    wrote {mp4}: {k} frames at {fps} fps ({k / fps:.1f} s), H.265 + AAC")


if __name__ == "__main__":
    main()
