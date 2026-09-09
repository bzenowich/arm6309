# `audio/` — the 4-channel PCM card

A **Paula**, not a Paula-alike: 4 channels of 8-bit signed PCM, built from pre-1990
parts, whose acceptance test is playing existing Amiga OCS tracker modules **correctly**.
**32 ICs** — one `ATF1508AS` CPLD in a PLCC-84 socket holds all the logic
([`docs/audio.md`](docs/audio.md) §10.1) — **512 KB of card-local sample SRAM in one
package**, no bus mastering, and **no digital multiply and no digital sum anywhere**:
volume, panning and mixing all happen in the converters, the way Paula does it. Two
outputs, and they are different signals: a **headphone-driven 3.5 mm stereo jack** at the
card's rear edge, and a **line-level** pair on the backplane (§7.1).

> The IC count's path from the first tally of 35 through 57, 54, 45 and 36 to 29, and
> then to 31 on 2026-09-08 when programmable panning was built and the memory
> consolidated, and to **32** on 2026-09-09 with the headphone driver, is archived,
> itemised, in [docs/history.md](docs/history.md).

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

> ⚠ **The tuning claim is unmeasured.** The A/B harness's spectral check resolves
> **50 cents per step** and thresholds at ±12 cents, so it can only pass at exactly
> 0 — and every error the design brief is about is smaller than one step: the
> NTSC-clock mistake is **+16 cents**, the worst period-table transcription error
> **16 cents**, one finetune step **12.5 cents**. What the A/B closed is *"no tuning
> error larger than 50 cents"* — which excludes a wrong period table and a wrong
> note, and does not exclude a wrong crystal. The fix is ~1-cent peak interpolation:
> [`docs/modplayer.md`](docs/modplayer.md) §8 and [`docs/audio.md`](docs/audio.md)
> §16 item 22.

The design-review findings the model had faithfully reproduced — DAC coding, the
channel-sum costing, the LED filter's order — are archived in
[docs/history.md](docs/history.md); the specs describe only the present design.

Next is `docs/audio.md` §15 step 0 — freeze the §9 register map, with `ACTRL` b4
(8-channel), **`ACTRL` b5 (pan enable)**, `ACTRL` b6 (timer enable), `AINTREQ`'s set
form and `ASTAT` b6/b7 all decided in §9.2 — which is a
[machine-level](../docs/machine.md) decision, and then §12.5's MCU bring-up card, which
is what proves the map before any discrete board is laid out.

⚠ **The CPLD fit is one day behind the document** — `cpld/audio.jed` was fitted before
panning and before the state file changed width. Neither adds a pin; §16 item 30 is the
refit.
