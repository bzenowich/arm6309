# `modcompare` — A/B the reference player against libopenmpt

**[`audio/docs/modplayer.md`](../../docs/modplayer.md) §8 build step 0's exit criterion.**
The reference player ([`../refplayer/`](../../refplayer/)) needs something
independent to be wrong against. libopenmpt carries Antti Lankila's Paula
emulation (`render.resampler.emulate_amiga`), which is the closest thing to a
reference Amiga renderer that can be driven headlessly.

```
python3 audio/tools/modcompare/mkprobe.py /tmp/probes     # generate the probes
python3 audio/tools/modcompare/ladder.py  /tmp/probes 8   # A/B every one of them
python3 audio/tools/modcompare/abcompare.py song.mod      # detail on one module
```

Needs `libopenmpt.so.0` and numpy. Nothing here is built or tested by CMake — it
is a bench instrument, not part of the product, and it is Python because the
analysis is the hard part and the C is not.

## Start easy, then escalate

The first attempt at this went straight at `ode2ptk.mod` ("Ode to ProTracker"),
which is a **deliberately antagonistic** test module — it walks backwards through
its own pattern with `Bxx`/`Dxx` on every row, rewrites the tempo constantly, and
exists specifically to break players. Every disagreement it produced could have
been any of a dozen causes, and the first run scored so badly it was unclear
whether the player or the metric was at fault.

So the ladder has three rungs, and they should be climbed in order:

| Rung | What | Why |
|---|---|---|
| 1 | **`mkprobe.py`** — 15 synthetic modules, one effect each, one channel, a sustaining looped sample | A disagreement names the effect. Nothing else is moving. |
| 2 | An ordinary real module | Real material, ordinary usage. |
| 3 | **`ode2ptk.mod`** and friends | Antagonistic by construction. Only meaningful once rungs 1–2 are clean. |

`libxmp`'s `test-dev/data` is a good source for rung 3 and a **bad** one for
rung 2 — it is a regression suite, so almost everything in it is pathological on
purpose. Modules are their composers' work; fetch them to a scratch directory
for testing and do not commit them.

## Calibrate the metric before trusting it

Every run prints a calibration line first: **libopenmpt scored against itself**
under two different Amiga filters. Same notes, different reconstruction — exactly
our relationship to it. That number is the ceiling. Ours scoring near it is
agreement; far below it is a real divergence.

Without that line the numbers are unreadable. It is what established that an
early score of 0.60 was a genuine bug rather than the metric's noise floor.

## What is measured, and why not correlation

| Metric | Meaning |
|---|---|
| **silence disagreement** | fraction of 10 ms buckets where one player has sound and the other does not. Catches a missing note, an extra note, a mistimed cut |
| **spectral** | median per-frame correlation of log-frequency spectra, over frames the reference considers audible |
| **cents** | global tuning offset, searched over ±1 semitone only |
| **gain** | level difference in dB, after nothing — an honest absolute comparison |

**Envelope correlation was tried first and is the wrong tool.** A sustained note
has a flat envelope, so there is no variance to correlate and the coefficient is
noise: probes that matched perfectly scored 0.07, and one scored −0.5. Two of the
three "results" from the first run were that artefact. Correlation measures
whether two signals *vary together*; what actually matters here is whether they
agree about **when there is sound**, which is what the silence-disagreement
metric asks directly.

Two more traps, both hit and both fixed here:

- **libopenmpt's stereo separation of 100 % is not hard panning.** A left-only
  probe measured `R/L = 0.333` — a third of the channel crossfed. Paula does not
  do that ([`audio.md`](../../docs/audio.md) §1 requirement 5). Set it to **200**;
  the same probe then measures `R/L = 0.0000`.
- **Scoring silent frames.** A probe that is deliberately silent most of the time
  (a one-shot, a note cut) otherwise gets scored on the correlation of two
  silences, which reads as total failure.

## The bug this found

Both players tracked each other exactly — **shifted 20 ms to the right**, which
is one tick at the default tempo. `mod_start()` armed the tempo timer, and
arming it schedules the *next* expiry, so row 0 did not play until a full tick
had elapsed. Audibly it is a beat of silence before the music starts; for an A/B
it is worse, because a constant offset also skews every RMS comparison — the
apparent 1.3× level difference across the whole probe set collapsed to **±0.3 dB**
the moment it was fixed.

Real driver code has the same obligation: play row 0, then let the timer drive
ticks 1..n.

## Results

15/15 probes and `ode2ptk.mod` agree. Calibration ceiling in brackets.

| | silence disagreement | spectral | tuning | gain |
|---|---|---|---|---|
| Probes (worst of 15) | 0.017 | 0.930 *(0.990)* | +0.0 cents | +0.25 dB |
| `ode2ptk.mod` left | 0.0012 | 0.992 *(0.982)* | +0.0 cents | −0.01 dB |
| `ode2ptk.mod` right | 0.0031 | 0.968 *(0.982)* | +0.0 cents | — |

And the sharpest result, which is not audio at all: `refplayer --rowtrace`
against libopenmpt's `get_current_order/pattern/row` over the whole of
`ode2ptk.mod` — **1112 rows, identical**, through a module built to break
exactly that logic. [`modplayer.md`](../../docs/modplayer.md) §5.8's ordering is
correct as written.

**What this does not establish.** libopenmpt is an independent implementation,
not the hardware. Its Paula resampler is band-limited where ours is a zero-order
hold plus the A500 pole ([`audio.md`](../../docs/audio.md) §6.2), so the two must
differ above a few kHz and the remaining spectral gap is partly that. Agreement
here means the two implementations read ProTracker the same way; only real
hardware settles whether that reading is right.
