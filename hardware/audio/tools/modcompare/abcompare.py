#!/usr/bin/env python3
"""A/B our reference player against libopenmpt's Paula emulation.

hardware/audio/docs/modplayer.md §8 build step 0's remaining exit criterion. libopenmpt is not
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


# The tuning axis is measured at 6.25 cents a bin and then interpolated, which
# is a different instrument from the 24-bins-per-octave spectrogram used for
# spectral agreement. It has to be: at 24 bins per octave one step is 50 cents,
# so an integer-bin argmax can only ever report a multiple of 50 -- and every
# error this project is about is smaller than that. The NTSC-clock mistake is
# +16 cents, the worst period-table transcription error 16 cents, one finetune
# step 12.5 cents. All three read as "0.0 cents" on a 50-cent ruler.
TUNE_BPO = 192
TUNE_NFFT = 16384


def logprofile(x, nfft=TUNE_NFFT, bpo=TUNE_BPO, f0=110.0, f1=11000.0):
    """Mean log-magnitude spectrum resampled onto a log-frequency axis.

    A uniform detune is a pure TRANSLATION along that axis -- that is the whole
    reason the axis is logarithmic -- so the position of a cross-correlation
    peak against a reference measures it, and the peak is over every partial of
    every note at once rather than over one chosen tone.
    """
    hop = nfft // 2
    if len(x) < nfft:
        return None
    nf = 1 + (len(x) - nfft) // hop
    win = np.hanning(nfft)
    acc = np.zeros(nfft // 2 + 1)
    for i in range(nf):
        acc += np.abs(np.fft.rfft(x[i * hop: i * hop + nfft] * win))
    acc /= nf
    fft_f = np.fft.rfftfreq(nfft, 1.0 / RATE)
    nb = int(np.log2(f1 / f0) * bpo)
    lf = f0 * 2.0 ** (np.arange(nb) / bpo)
    return np.log10(np.interp(lf, fft_f, acc) + 1e-6)


def tuning_cents(ref, ours, max_cents=100.0):
    """Global tuning offset of `ours` against `ref`, positive = sharp.

    Parabolic interpolation of the correlation peak is what takes this from
    bin-quantised to continuous: the peak of a smooth correlation is a parabola
    near its maximum, and fitting the three samples around the argmax resolves
    it to well inside one bin. Measured against renders detuned by a known
    amount (0, 1, 2, 3, 5, 8, 12.5, +/-16, 25, -40, 50 cents) the worst residual
    is 1.1 cents and the mean is 0.5. Wider fits and finer axes were tried and
    are worse: above ~200 bins per octave the log axis oversamples the FFT, the
    correlation peak goes flat, and the argmax stops meaning anything.
    """
    a, b = logprofile(ref), logprofile(ours)
    if a is None or b is None:
        return float("nan")
    a, b = a - a.mean(), b - b.mean()
    k = max(2, int(round(max_cents * TUNE_BPO / 1200.0)))
    lags = np.arange(-k, k + 1)
    c = np.array([float(np.dot(a[k:-k], np.roll(b, int(s))[k:-k])) for s in lags])
    i = int(np.argmax(c))
    frac = 0.0
    if 0 < i < len(c) - 1:
        d = c[i - 1] - 2.0 * c[i] + c[i + 1]
        if d != 0.0:
            frac = 0.5 * (c[i - 1] - c[i + 1]) / d
            frac = max(-1.0, min(1.0, frac))
    # A positive roll shifts `ours` UP the log axis to meet `ref`, so `ours`
    # was flat by that much; the reported sign is "ours relative to ref".
    return -(float(lags[i]) + frac) * 1200.0 / TUNE_BPO


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


def score(ref, ours, label):
    """Print the comparison of `ours` against `ref` and return its metrics."""
    m = min(len(ref), len(ours))
    ref, ours = ref[:m], ours[:m]
    hop = 480                                    # 10 ms
    out = {}
    for ci, cname in ((0, "left  (ch 0,3)"), (1, "right (ch 1,2)")):
        r, o = ref[:, ci], ours[:, ci]
        # A side that is silent in the reference has nothing to score: a
        # single-channel probe leaves one pair empty, and correlating silence
        # against silence printed a +100-cent PITCH MISMATCH on every healthy
        # run (audio.md 16 item 46).
        if np.sqrt((r ** 2).mean()) < 1.0:
            print(f"{cname}\n  silent in the reference - not scored\n")
            continue
        # normalise level: absolute gain against libopenmpt is not part of
        # this comparison, because its output stage is not the card's.
        # --control compares level where it IS comparable.
        r = r / (np.sqrt((r ** 2).mean()) + 1e-9)
        o = o / (np.sqrt((o ** 2).mean()) + 1e-9)
        er, eo = envelope(r, hop), envelope(o, hop)
        lag = best_lag(er, eo, hop)
        # best_lag peaks where r[n + lag] matches o[n]: a negative lag means
        # `ours` is LATE, so it is `ours` that loses its head. Trimming the other
        # signal doubles the offset instead of removing it - which is what this
        # did until 2026-09-12, and why a card 20 ms late scored an envelope
        # correlation near zero (audio.md 16 item 46).
        if lag > 0:
            r2, o2 = r[lag:], o
        else:
            r2, o2 = r, o[-lag:]
        n = min(len(r2), len(o2)); r2, o2 = r2[:n], o2[:n]
        er2, eo2 = envelope(r2, hop), envelope(o2, hop)
        k = min(len(er2), len(eo2))
        env_c = np.corrcoef(er2[:k], eo2[:k])[0, 1]

        sr, _ = logspec(np.ascontiguousarray(r2))
        so, _ = logspec(np.ascontiguousarray(o2))
        nf = min(len(sr), len(so)); sr, so = sr[:nf], so[:nf]

        cents = tuning_cents(r2, o2)

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
        print(f"  global tuning offset {cents:+8.2f} cents  "
              f"({'OK' if abs(cents) < 12 else '*** PITCH MISMATCH ***'})")
        print(f"  spectral corr        median {np.median(fc):.4f}   "
              f"5th pct {np.percentile(fc,5):.4f}")
        worst = [f"{order[i]*frame_t:.1f}s({fc[order[i]]:.2f})" for i in range(min(5, len(order)))]
        print(f"  worst frames         {' '.join(worst)}")
        print()
        out[ci] = dict(env=env_c, cents=cents, spec_med=float(np.median(fc)),
                       spec_p5=float(np.percentile(fc, 5)), lag=lag)
    return out


def rms_db(x):
    return 20.0 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9)


# ⭐ THE GATE (--control). The run script's own rule - a card that scores worse
# than refplayer is hardware - made into an exit code. Before 2026-09-12 both
# scorings ran under `|| true` and nothing here was thresholded, so no acoustic
# result could fail check:modplay.
#
# LEVEL is first because it is the defect class that has already escaped: the
# 12 dB volume error scored 0.9903 against a control's 0.9901, because every
# metric above normalises level away. The card and refplayer share render.c's
# analogue chain, so between THEM absolute level is meaningful, and it is
# compared directly after removing their relative lag.
GATE_LEVEL_DB = 0.5        # card RMS against control RMS, per side
GATE_ENV = 0.05            # envelope correlation, below the control's
GATE_SPEC_MED = 0.02       # spectral median, below the control's
GATE_SPEC_P5 = 0.10        # spectral 5th percentile, below the control's
GATE_CENTS = 12.0          # absolute tuning offset


def gate(card, ctrl, card_scores, ctrl_scores):
    hop = 480
    fails = []
    m = min(len(card), len(ctrl))
    card, ctrl = card[:m], ctrl[:m]
    print("gate: card against control")
    for ci, cname in ((0, "left "), (1, "right")):
        c, r = card[:, ci], ctrl[:, ci]
        if ci not in ctrl_scores:
            print(f"  {cname} silent in the reference - not gated")
            continue
        lag = best_lag(envelope(r, hop), envelope(c, hop), hop)
        r2, c2 = (r[lag:], c) if lag > 0 else (r, c[-lag:])
        n = min(len(r2), len(c2))
        d = rms_db(c2[:n]) - rms_db(r2[:n])
        rows = [
            ("level vs control", f"{d:+.2f} dB", abs(d) <= GATE_LEVEL_DB,
             f"|d| <= {GATE_LEVEL_DB} dB"),
        ]
        cs, rs = card_scores.get(ci), ctrl_scores[ci]
        if cs is None:
            rows.append(("scored", "no", False, "a side the reference plays"))
        else:
            rows += [
                ("envelope corr", f"{cs['env']:.4f} vs {rs['env']:.4f}",
                 cs["env"] >= rs["env"] - GATE_ENV, f">= control - {GATE_ENV}"),
                ("spectral median", f"{cs['spec_med']:.4f} vs {rs['spec_med']:.4f}",
                 cs["spec_med"] >= rs["spec_med"] - GATE_SPEC_MED,
                 f">= control - {GATE_SPEC_MED}"),
                ("spectral 5th pct", f"{cs['spec_p5']:.4f} vs {rs['spec_p5']:.4f}",
                 cs["spec_p5"] >= rs["spec_p5"] - GATE_SPEC_P5,
                 f">= control - {GATE_SPEC_P5}"),
                ("tuning", f"{cs['cents']:+.2f} cents",
                 abs(cs["cents"]) <= GATE_CENTS, f"|c| <= {GATE_CENTS}"),
            ]
        for what, val, good, rule in rows:
            print(f"  {'ok  ' if good else 'FAIL'}  {cname} {what:<17} {val:<22} ({rule})")
            if not good:
                fails.append(f"{cname.strip()} {what}")
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mod")
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--player", default="hardware/audio/build/host/refplayer")
    ap.add_argument("--amiga", default="a500")
    # ⭐ --wav: score a WAV that already exists, instead of running the player.
    # Added 2026-09-10 so that the SAME metric and the SAME reference can be
    # pointed at hardware/audio/sim/modplay_tb.sv's render of the real card.
    # Without it this file could only ever measure the C model, which is the
    # thing the oracle README warns about: "two independent implementations of
    # one paragraph, and the A/B only ever tested one of them."
    ap.add_argument("--wav", default=None,
                    help="score this WAV instead of running --player")
    ap.add_argument("--label", default=None, help="what to call it in the output")
    ap.add_argument("--control", default=None,
                    help="also score this WAV, and exit 1 if --wav is worse than it")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp()
    ours_path = os.path.join(tmp, "ours.wav")

    ref, ref_dur = omptrender.render(args.mod, RATE, args.seconds, args.amiga)
    if args.wav:
        ours_path = args.wav
        label = args.label or os.path.basename(args.wav)
    else:
        label = args.label or "refplayer"
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
    print(f"{label:<13} {len(ours)/RATE:8.2f} s")
    d = abs(len(ref) - len(ours)) / RATE
    print(f"length delta  {d:8.3f} s   {'OK' if d < 0.25 else '*** MISMATCH ***'}")
    print()
    scores = score(ref, ours, label)
    if not args.wav:
        os.remove(ours_path)
    os.rmdir(tmp)

    if args.control:
        ctrl = read_wav(args.control)
        print(f"-- control: {os.path.basename(args.control)}")
        print()
        ctrl_scores = score(ref, ctrl, "control")
        fails = gate(ours, ctrl, scores, ctrl_scores)
        if d >= 0.25:
            fails.append("length")
        print()
        if fails:
            print(f"FAIL  the card scores worse than the control: {', '.join(fails)}")
            sys.exit(1)
        print("ok    the card scores no worse than the control on every gated metric")


if __name__ == "__main__":
    main()
