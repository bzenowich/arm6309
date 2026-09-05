#!/usr/bin/env python3
"""Run the A/B ladder: every probe module, ours vs libopenmpt's Paula mode.

Prints one row per module. The calibration line at the top is libopenmpt scored
against ITSELF under a different Amiga filter -- same notes, different
reconstruction, which is exactly our relationship to it. That number is the
ceiling; anything near it is agreement, anything far below it is a real
divergence worth chasing.
"""
import os, subprocess, sys, tempfile
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import omptrender
from abcompare import read_wav, envelope, logspec, tuning_cents, RATE


def score(ref, ours):
    out = []
    n = min(len(ref), len(ours))
    # "Silent" has to be judged against the loudest thing in the mix, not an
    # absolute epsilon: a hard-panned probe leaves one side genuinely empty, and
    # an absolute test reports that as total disagreement.
    full = max(np.abs(ref[:n]).max(), np.abs(ours[:n]).max(), 1.0)
    for ci in (0, 1):
        r, o = ref[:n, ci].copy(), ours[:n, ci].copy()
        rr = np.sqrt((r ** 2).mean()); oo = np.sqrt((o ** 2).mean())
        quiet = full * 1e-3
        if rr < quiet and oo < quiet:
            out.append((0.0, 1.0, 0.0, 0.0)); continue
        if rr < quiet or oo < quiet:
            out.append((1.0, 0.0, float('nan'), float('nan'))); continue
        gain_db = 20.0 * np.log10(oo / rr)
        r, o = r / rr, o / oo
        er, eo = envelope(r, 480), envelope(o, 480)
        k = min(len(er), len(eo)); er, eo = er[:k], eo[:k]
        # Correlation is meaningless when the envelope is flat -- a sustained
        # note has no variance to correlate. What matters is whether the two
        # agree about WHEN there is sound: count 10 ms buckets where one is
        # audible and the other is not. That catches a missing note, an extra
        # note, and a mistimed cut, which correlation does not.
        loud = max(er.max(), eo.max()) * 0.05
        disagree = float(np.mean((er > loud) != (eo > loud)))
        sr, _ = logspec(np.ascontiguousarray(r)); so, _ = logspec(np.ascontiguousarray(o))
        nf = min(len(sr), len(so)); sr, so = sr[:nf], so[:nf]
        a = sr - sr.mean(axis=1, keepdims=True); b = so - so.mean(axis=1, keepdims=True)
        fc = (a * b).sum(1) / (np.sqrt((a * a).sum(1) * (b * b).sum(1)) + 1e-12)
        # Score only frames the reference considers audible. A probe that is
        # deliberately silent most of the time (a one-shot, a note cut) is
        # otherwise scored on the correlation of two silences, which is noise.
        frame_rms = np.sqrt(np.convolve(r ** 2, np.ones(1024) / 1024, "valid")[::1024][:len(fc)])
        audible = frame_rms > frame_rms.max() * 0.05
        if audible.sum() >= 4: fc = fc[audible]
        # Tuning offset, searched only over +/- 100 cents: we are looking for
        # detune, not for octave errors, and an unbounded search finds nonsense.
        # See abcompare.tuning_cents for why this is not the 24-bin spectrogram
        # above -- that one cannot resolve anything finer than 50 cents.
        out.append((disagree, float(np.median(fc)), tuning_cents(r, o), gain_db))
    return out


def run(path, seconds, player):
    tmp = tempfile.mkdtemp(); w = os.path.join(tmp, "o.wav")
    ref, _ = omptrender.render(path, RATE, seconds, "a500")
    p = subprocess.run([player, "--wav", w, "--seconds", str(seconds), path],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"{path}: {p.stdout}{p.stderr}")
    ours = read_wav(w); os.remove(w); os.rmdir(tmp)
    return score(ref, ours)


def main():
    d = sys.argv[1]
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0
    player = sys.argv[3] if len(sys.argv) > 3 else "build-host/refplayer"
    mods = sorted(f for f in os.listdir(d) if f.endswith(".mod"))

    cal = os.path.join(d, mods[0])
    a, _ = omptrender.render(cal, RATE, seconds, "a500")
    b, _ = omptrender.render(cal, RATE, seconds, "unfiltered")
    c = score(a, b)
    print(f"calibration (libopenmpt a500 vs unfiltered, same notes): "
          f"silence-disagreement {c[0][0]:.4f}  spectral {c[0][1]:.3f}   <- the ceiling\n")

    print(f"{'probe':16s} {'L dis':>7} {'L spec':>7} {'cents':>6} {'gain':>7} | "
          f"{'R dis':>7} {'R spec':>7} {'cents':>6}  verdict")
    bad = []
    for m in mods:
        s = run(os.path.join(d, m), seconds, player)
        (ld, ls, lc, lg), (rd, rs, rc, rg) = s
        worst_dis = max(ld, rd); worst_spec = min(ls, rs)
        ok = (worst_dis < 0.02 and worst_spec > 0.85
              and abs(lc) < 12 and (np.isnan(rc) or abs(rc) < 12))
        if not ok: bad.append(m)
        print(f"{m[:-4]:16s} {ld:7.4f} {ls:7.3f} {lc:+6.2f} {lg:+6.2f}dB | "
              f"{rd:7.4f} {rs:7.3f} {rc:+6.2f}  {'ok' if ok else '<-- DIVERGES'}")
    print()
    print(f"{len(mods)-len(bad)}/{len(mods)} probes agree" +
          (f"; chase: {', '.join(b[:-4] for b in bad)}" if bad else ""))


if __name__ == "__main__":
    main()
