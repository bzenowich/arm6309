#!/usr/bin/env python3
"""A/B our reference player against libopenmpt's Paula emulation.

docs/modplayer.md §8 build step 0's remaining exit criterion. libopenmpt is not
ground truth -- it is an INDEPENDENT implementation, and the value is in
explaining every disagreement rather than in driving them to zero. Two classes
of difference are expected and are not faults:

  * libopenmpt's Amiga resampler is band-limited; ours is a zero-order hold plus
    the A500's 4.4 kHz pole, which is what the hardware does (audio.md §6.2).
    They must differ above a few kHz, and the size of that difference is a
    result, not an error.
  * absolute level, and sub-millisecond start alignment.

What must NOT differ: song length, note pitches, and where in time things
happen. Those are checked here.

usage: abcompare.py song.mod [--seconds N] [--rate HZ] [--player PATH]
"""
import argparse, os, subprocess, sys, tempfile, wave
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import omptrender

RATE = 48000


def read_wav(path):
    w = wave.open(path, "rb")
    n, ch = w.getnframes(), w.getnchannels()
    a = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float64)
    w.close()
    return a.reshape(-1, ch)


def envelope(x, hop):
    n = len(x) // hop
    return np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-12)


def best_lag(a, b, hop, max_ms=200):
    """Alignment offset in samples, from envelope cross-correlation."""
    m = min(len(a), len(b))
    a, b = a[:m] - a[:m].mean(), b[:m] - b[:m].mean()
    k = int(max_ms / 1000 * RATE / hop)
    c = np.correlate(a, b, mode="full")
    mid = len(c) // 2
    w = c[mid - k: mid + k + 1]
    return (int(np.argmax(w)) - k) * hop


def logspec(x, nfft=4096, hop=1024, bins_per_oct=24, f0=55.0, f1=16000.0):
    win = np.hanning(nfft)
    nf = 1 + (len(x) - nfft) // hop
    if nf < 2:
        return np.zeros((0, 1)), np.zeros(1)
    frames = np.lib.stride_tricks.as_strided(
        x, shape=(nf, nfft), strides=(x.strides[0] * hop, x.strides[0])) * win
    mag = np.abs(np.fft.rfft(frames, axis=1))
    fft_f = np.fft.rfftfreq(nfft, 1.0 / RATE)
    nb = int(np.log2(f1 / f0) * bins_per_oct)
    edges = f0 * 2.0 ** (np.arange(nb + 1) / bins_per_oct)
    idx = np.searchsorted(fft_f, edges)
    out = np.zeros((nf, nb))
    for i in range(nb):
        lo, hi = idx[i], max(idx[i + 1], idx[i] + 1)
        out[:, i] = mag[:, lo:hi].max(axis=1)
    return np.log10(out + 1e-6), edges[:-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mod")
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--player", default="build-host/refplayer")
    ap.add_argument("--amiga", default="a500")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp()
    ours_path = os.path.join(tmp, "ours.wav")

    ref, ref_dur = omptrender.render(args.mod, RATE, args.seconds, args.amiga)
    cmd = [args.player, "--wav", ours_path]
    if args.seconds:
        cmd += ["--seconds", str(args.seconds)]
    cmd.append(args.mod)
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        print(out.stdout, out.stderr); sys.exit(1)
    ours = read_wav(ours_path)

    print(f"module        {os.path.basename(args.mod)}")
    print(f"libopenmpt    {len(ref)/RATE:8.2f} s   (reported duration {ref_dur:.2f} s)")
    print(f"refplayer     {len(ours)/RATE:8.2f} s")
    d = abs(len(ref) - len(ours)) / RATE
    print(f"length delta  {d:8.3f} s   {'OK' if d < 0.25 else '*** MISMATCH ***'}")
    print()

    m = min(len(ref), len(ours))
    ref, ours = ref[:m], ours[:m]
    hop = 480                                    # 10 ms
    for ci, cname in ((0, "left  (ch 0,3)"), (1, "right (ch 1,2)")):
        r, o = ref[:, ci], ours[:, ci]
        # normalise level: absolute gain is not part of the comparison
        r = r / (np.sqrt((r ** 2).mean()) + 1e-9)
        o = o / (np.sqrt((o ** 2).mean()) + 1e-9)
        er, eo = envelope(r, hop), envelope(o, hop)
        lag = best_lag(er, eo, hop)
        if lag > 0:
            o2, r2 = o[lag:], r[:len(o) - lag]
        else:
            r2, o2 = r[-lag:], o[:len(r) + lag]
        n = min(len(r2), len(o2)); r2, o2 = r2[:n], o2[:n]
        er2, eo2 = envelope(r2, hop), envelope(o2, hop)
        k = min(len(er2), len(eo2))
        env_c = np.corrcoef(er2[:k], eo2[:k])[0, 1]

        sr, _ = logspec(np.ascontiguousarray(r2))
        so, _ = logspec(np.ascontiguousarray(o2))
        nf = min(len(sr), len(so)); sr, so = sr[:nf], so[:nf]

        # global tuning offset: shift the log-frequency axis for best match
        bpo = 24
        prof_r = sr.mean(axis=0) - sr.mean()
        prof_o = so.mean(axis=0) - so.mean()
        cc = np.correlate(prof_r, prof_o, mode="full")
        shift = int(np.argmax(cc)) - (len(prof_o) - 1)
        cents = shift * 1200.0 / bpo

        # per-frame spectral agreement
        a = sr - sr.mean(axis=1, keepdims=True)
        b = so - so.mean(axis=1, keepdims=True)
        num = (a * b).sum(axis=1)
        den = np.sqrt((a * a).sum(axis=1) * (b * b).sum(axis=1)) + 1e-12
        fc = num / den
        order = np.argsort(fc)
        frame_t = 1024 / RATE

        print(f"{cname}")
        print(f"  alignment lag        {lag/RATE*1000:+8.1f} ms")
        print(f"  envelope correlation {env_c:8.4f}")
        print(f"  global tuning offset {cents:+8.1f} cents  "
              f"({'OK' if abs(cents) < 12 else '*** PITCH MISMATCH ***'})")
        print(f"  spectral corr        median {np.median(fc):.4f}   "
              f"5th pct {np.percentile(fc,5):.4f}")
        worst = [f"{order[i]*frame_t:.1f}s({fc[order[i]]:.2f})" for i in range(min(5, len(order)))]
        print(f"  worst frames         {' '.join(worst)}")
        print()

    os.remove(ours_path); os.rmdir(tmp)


if __name__ == "__main__":
    main()
