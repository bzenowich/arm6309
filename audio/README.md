# `audio/` — the 4-channel PCM card

A **Paula**, not a Paula-alike: 4 channels of 8-bit signed PCM, built from pre-1990
parts, whose acceptance test is playing existing Amiga OCS tracker modules **correctly**.
**36 ICs**, card-local sample SRAM, no bus mastering, and **no digital multiply and no
digital sum anywhere**: volume and mixing both happen in the converters, the way Paula
does it.

> ⚠ **This README said 35 ICs, then 57.** The design review's audio findings put the
> honest figure at **57** — the channel-sum path, the host-visible counters
> `SPTR`/`LIDX`/`AIDX`, the host-boundary synchroniser and commit staging, the `ADATA`
> prefetch latch, the open-collector `/FIRQ` stage, and two more GALs were all argued for
> in prose and never costed. It is now **54**, because the digital channel sum has been
> replaced by four `LTC7545A` and a resistor pair
> ([`docs/audio.md`](docs/audio.md) §6.2). That change was recorded as being worth twelve
> packages; doing the analogue work it was waiting on showed it is worth **three** — the
> converter needs 100 ns of stable data against a 35 ns LUT window, so every channel
> needs its own hold latch, and four separate dice cannot sum as currents the way Paula's
> four on-die ladders do. Then **45**: the host-visible counters and the multi-byte commit
> staging moved into three of the state file's 2032 spare words, and the read-back `'245`
> went because the latch behind it already drives the bus (**−9**). Then **36**: an
> `AD7528` is a *dual* multiplying DAC, so cascading two halves — sample byte into the
> first, its output as the reference of the second, volume as that one's code — does the
> multiply in the analogue domain and deletes the 32K×8 volume LUT, its boot upload, six
> of the eight port latches and a state-file package (**−9**). The product stops being
> quantised at all, and `VOL` = 0 becomes exact silence.
> [`docs/audio.md`](docs/audio.md) §10 carries all four itemised deltas.

**Unaffected by the machine's E rate.** Everything on the card is referred to its own
28.37516 MHz crystal, and §9.3's prefetch means there is no `/WAIT` path to close, so the
card behaves identically at the specified **E = 2.0979 MHz** and at the experimental
divide-by-8 **fast-E** rate ([`docs/audio.md`](docs/audio.md) §0).

Paths below are relative to this directory; build commands run from the repository
root.

| | |
|---|---|
| [`docs/audio.md`](docs/audio.md) | the card — datapath, register map, DAC, filters, IC budget |
| [`docs/modplayer.md`](docs/modplayer.md) | the software — what the loader relocates and what the replayer computes |
| [`refplayer/`](refplayer/) | **host reference model** of both, in C. Builds and is tested. |
| [`test/`](test/) | unit tests for the reference model, run by `ctest` |
| [`tools/modcompare/`](tools/modcompare/) | A/B harness against libopenmpt's Paula emulation. Python, outside the build. |

## Why there is a C model of a card made of TTL

`docs/modplayer.md` §8 step 0: without a reference implementation there is nothing to
A/B against, and "it sounds about right" is not an acceptance test for a system whose
entire premise is bit-exact compatibility. The replayer here is the one that gets
transliterated into 6309 assembly, so the 6309 port has something to be diffed against —
and building it already found four spec errors.

It is host-only by construction and always will be. The card is discrete logic; there is
no firmware in this directory.

```sh
cmake -B build-host -G Ninja && cmake --build build-host   # from the repo root
build-host/refplayer --wav out.wav --trace out.trace song.mod
ctest --test-dir build-host --output-on-failure
```

## Status

**Specified; the model is validated structurally, and the tuning claim is not yet
measurable.** 15/15 single-effect probes and the whole 1112-row path through
`ode2ptk.mod` agree with libopenmpt's Paula emulation — identical row/pattern
traversal, ≤0.3 dB gain, spectral correlation at or above the calibration ceiling.

> ⚠ **"+0.0 cents tuning" is withdrawn as an exit criterion.** The A/B harness's
> spectral check runs at 24 bins/octave — **50 cents per step** — and thresholds at
> ±12 cents, so it can only return an integer multiple of 50 and can only pass at
> exactly 0. Every error the design brief is about is smaller than one step: the
> NTSC-clock mistake is **+16 cents**, the worst period-table transcription error
> **16 cents**, one finetune step **12.5 cents**. What step 0 actually closed is
> *"no tuning error larger than 50 cents"* — which excludes a wrong period table and a
> wrong note, and does not exclude a wrong crystal. The corrected method is parabolic
> interpolation of the correlation peak, or FFT peak interpolation on a single-note
> probe, either of which resolves ~1 cent: [`docs/modplayer.md`](docs/modplayer.md) §8
> and [`docs/audio.md`](docs/audio.md) §16 item 22.

The design review also overturned three specification claims that the model and the
tests had faithfully reproduced: the DAC is coded **offset binary**, not two's
complement ([`docs/audio.md`](docs/audio.md) §6.3); the channel sum is **latched**, not
combinational (§6.2); and the "LED" filter is **2-pole**, not 5-pole (§7). Each is
marked in place.

Next is `docs/audio.md` §15 step 0 — freeze the §9 register map, now with `ACTRL` b4
(8-channel), `ACTRL` b6 (timer enable), `AINTREQ`'s set form and `ASTAT` b6/b7 all
decided — which is a [machine-level](../docs/machine.md) decision, and then §12.5's MCU
bring-up card, which is what proves the map before any discrete board is laid out.
