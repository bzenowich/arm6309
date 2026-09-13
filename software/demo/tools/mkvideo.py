#!/usr/bin/env python3
"""Turn demo_tb's recordings into an H.265 file.

    python3 software/demo/tools/mkvideo.py OUT demo.mp4 [--fps 70]
    python3 software/demo/tools/mkvideo.py OUT demo-web.mp4 --web

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

--wav FILE takes the sound from FILE instead of card.dac - emu/run-emu.sh passes
tracewav's render of the emulator's register writes.

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


# A frame that began longer ago than this is not on the screen any more. With the
# display off the card sends no active video at all, and demo_tb writes no frame -
# so holding the last one would show a picture a monitor is not showing.
STALE_S = 0.05


def main():
    out, mp4 = sys.argv[1], sys.argv[2]
    web = "--web" in sys.argv
    fps = float(sys.argv[sys.argv.index("--fps") + 1]) if "--fps" in sys.argv else (60.0 if web else 70.0)
    sync = dict(l.split() for l in open(os.path.join(out, "sync.txt")))
    end_s = int(sync.get("end_ps", 0)) / 1e12

    if "--wav" in sys.argv:
        wav = sys.argv[sys.argv.index("--wav") + 1]      # emu/run-emu.sh: tracewav's render
    else:
        wav = os.path.join(out, "card.wav")
        subprocess.run([os.path.join(ROOT, "build-host", "dacwav"), wav, os.path.join(out, "card.dac")],
                       check=True, stdout=subprocess.DEVNULL)
    audio_offset = int(sync["cc0_ps"]) / 1e12

    gop = int(round(fps))
    if web:
        # ⭐ FOR A BROWSER, NOT FOR REVIEW AT FULL FIDELITY. Google Drive, like most
        # web players, transcodes HEVC and caps the frame rate at 60, and when it
        # changes quality mid-play it restarts from the last keyframe. With x265's
        # default keyframes (every 3.6 s, and one at the scene cut before the
        # paint) that replayed the whole paint. So: H.264, 60 fps resampled here
        # rather than by the player, a keyframe every second with no scene-cut
        # extras, and the index at the front of the file.
        vcodec = ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high",
                  "-pix_fmt", "yuv420p", "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0"]
        label = "H.264 + AAC, web"
    else:
        vcodec = ["-c:v", "libx265", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
                  "-tag:v", "hvc1",
                  "-x265-params", f"log-level=error:keyint={gop}:min-keyint={gop}:scenecut=0"]
        label = "H.265 + AAC"
    ff = ffmpeg_path()
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OW}x{OH}", "-r", f"{fps}", "-i", "-",
           "-itsoffset", f"{audio_offset:.6f}", "-i", wav,
           "-map", "0:v", "-map", "1:a", *vcodec,
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", mp4]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    black = np.zeros((OH, OW, 3), np.uint8)
    it = fr.read(os.path.join(out, "frames.bin"))
    pending = next(it, None)
    shown, shown_t = black, -1.0
    k = 0
    while True:
        t = k / fps
        if end_s and t >= end_s:
            break
        if not end_s and pending is None and t > shown_t + 0.5:
            break
        latest = None
        while pending is not None and pending[0]["t"] <= t:
            latest = pending
            pending = next(it, None)
        if latest is not None:
            shown, shown_t = scale(fr.rgb565_to_rgb8(latest[1])), latest[0]["t"]
        frame = shown if t - shown_t <= STALE_S else black
        enc.stdin.write(frame.tobytes())
        k += 1
        if k % 700 == 0:
            print(f"      {t:6.1f} s encoded", flush=True)
    enc.stdin.close()
    rc = enc.wait()
    if rc != 0:
        sys.exit(f"FAIL  ffmpeg exited {rc}")
    print(f"ok    wrote {mp4}: {k} frames at {fps:g} fps ({k / fps:.1f} s), {label}")


if __name__ == "__main__":
    main()
