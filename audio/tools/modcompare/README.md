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
| 1 | **`mkprobe.py`** — 22 synthetic modules, one effect each, one channel, a sustaining looped sample | A disagreement names the effect. Nothing else is moving. |
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
| **cents** | global tuning offset, searched over ±100 cents only, resolved to **~1 cent** |
| **gain** | level difference in dB, after nothing — an honest absolute comparison |

**Envelope correlation was tried first and is the wrong tool.** A sustained note
has a flat envelope, so there is no variance to correlate and the coefficient is
noise: probes that matched perfectly scored 0.07, and one scored −0.5. Two of the
three "results" from the first run were that artefact. Correlation measures
whether two signals *vary together*; what actually matters here is whether they
agree about **when there is sound**, which is what the silence-disagreement
metric asks directly.

**The tuning number needs an instrument finer than the spectrogram.** The
spectral metric runs at 24 bins per octave, and reusing that axis for the tuning
offset makes one step **50 cents** — so an integer-bin argmax can only ever
report a multiple of 50, and `±12 cents` is a threshold it passes at exactly 0.
Every error this project is about is smaller than one step: the NTSC-clock
mistake is +16 cents, the worst period-table transcription error 16 cents, one
finetune step 12.5 cents. All three read as "+0.0 cents" on that ruler, which is
why the first fifteen probes all reported +0.0 and the number meant nothing.

`abcompare.tuning_cents()` measures it separately: a mean log-magnitude spectrum
resampled onto a log-frequency axis at 192 bins per octave — where a uniform
detune is a pure translation — cross-correlated against the reference, with
**parabolic interpolation of the correlation peak**. Verified by detuning a
rendered probe by a known amount (0, 1, 2, 3, 5, 8, 12.5, ±16, 25, −40, 50
cents): worst residual **1.1 cents**, mean 0.5, against the old instrument's
`+0.0` for everything below 25 cents. Finer axes are worse, not better — above
about 200 bins per octave the log axis oversamples the FFT and the correlation
peak goes flat.

Two more traps, both hit and both fixed here:

- **libopenmpt's stereo separation of 100 % is not hard panning.** A left-only
  probe measured `R/L = 0.333` — a third of the channel crossfed. Paula does not
  do that ([`audio.md`](../../docs/audio.md) §1 requirement 5). Set it to **200**;
  the same probe then measures `R/L = 0.0000`.
- **Scoring silent frames.** A probe that is deliberately silent most of the time
  (a one-shot, a note cut) otherwise gets scored on the correlation of two
  silences, which reads as total failure.

## The corners the first fifteen probes did not reach

A ladder that passes tells you nothing about what it does not touch. Probes
15–21 were added after a design review found real divergences in effects the
ladder scored as `ok` — because nothing in those fifteen probes varied the thing
that was wrong. Scored against the player as it was before the review:

| probe | what it varies | before | after |
|---|---|---|---|
| `15_ledfilter` | `E0x`, the only effect that reaches non-channel hardware | 0.962 | **0.999** |
| `16_tpspeed` | a `3xx` speed change on a **note-less** row | 0.519 | **0.998** |
| `17_ec0` | `EC0`, which cuts at tick 0 | 0.000 *(the note played forever)* | **1.000** |
| `18_e9noteless` | `E9x` on a row with no note | 0.887 | **0.998** |
| `19_edelay_ee` | `EDx` inside an `EEx` pattern delay | 0.994 | 0.998 |
| `20_offsetmem` | `9xx` seen on a row with no note | 0.823 | **0.999** |
| `21_loopbreak` | `E6x` sharing its row with `Dxx` | 0.070 | **0.998** |

`20_offsetmem`'s sample is deliberately two different sounds spliced at the
offset. The first version used a periodic waveform and scored 0.999 both ways —
a probe that cannot fail is worse than no probe, because it reads as coverage.

## What the ladder also disproved

The same review reported that ProTracker never rewrites the base period at tick 0
during a sustained vibrato, and that our tick-0 write was an artefact to remove.
It is not. Removing it dropped `06_vibrato` from **0.996 to 0.969**, and reading
the fundamental back out of libopenmpt's own `a500` render by autocorrelation
shows the snap plainly — 183.5 Hz at tick 0 of rows 2, 3 and 4, the un-modulated
base, against 174.9 / 187.3 / 190.5 Hz for a player that holds the modulated
value. ProTracker's `mt_CheckMoreEffects` falls through to `mt_PerNop` for every
command outside `{9,B,D,E,F,C}`, and `mt_PerNop` writes `n_period`, which
vibrato never touches. The write stayed, and `test_refplayer.c` now pins it.

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

22/22 probes agree. Calibration ceiling in brackets.

| | silence disagreement | spectral | tuning | gain |
|---|---|---|---|---|
| Probes (worst of 22) | 0.017 | 0.930 *(0.990)* | +1.96 cents | +0.25 dB |

The tuning column is the one to read differently from before: these are real
sub-cent measurements, not the old instrument's quantised zero. `04_porta`'s
+1.96 cents is a genuine small divergence in `1xx`/`2xx` portamento that the
50-cent ruler could not have shown; it is inside the ±12 cent threshold and has
not been chased.

The `ode2ptk.mod` numbers below were measured with the old tuning instrument and
their tuning column is not meaningful. They have not been re-run.

| | silence disagreement | spectral | tuning | gain |
|---|---|---|---|---|
| `ode2ptk.mod` left | 0.0012 | 0.992 *(0.982)* | *(not measurable)* | −0.01 dB |
| `ode2ptk.mod` right | 0.0031 | 0.968 *(0.982)* | *(not measurable)* | −0.01 dB |

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
