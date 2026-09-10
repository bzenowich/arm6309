# `audio/` — the 4-channel PCM card

A **Paula**, not a Paula-alike: 4 channels of 8-bit signed PCM, built from pre-1990
parts, whose acceptance test is playing existing Amiga OCS tracker modules **correctly**.
⭐ **35 ICs on an 18 cm card** — **two** `ATF1508AS`, both fitted
([`docs/audio.md`](docs/audio.md) §10.1, §10.2) — **512 KB of card-local
sample SRAM in one package**, no bus mastering, and **no digital multiply and no digital
sum anywhere**:
volume, panning and mixing all happen in the converters, the way Paula does it. Two
outputs, and they are different signals: a **headphone-driven 3.5 mm stereo jack** at the
card's rear edge, and a **line-level** pair on the backplane (§7.1).

> The IC count's path from the first tally of 35 through 57, 54, 45, 36, 29, 31 and 32
> up to **45** on 2026-09-09 when the sequencer was built, and back down to **35** the
> same day — programmable panning given up for classic MOD's fixed LRRL, and the
> counter, the comparator and the read-back latch absorbed into U1, where sixteen pins
> bought seven packages — is archived, itemised, in [docs/history.md](docs/history.md).

**Unaffected by the machine's E rate.** Everything on the card is referred to its own
28.37516 MHz crystal, and §9.3's prefetch means there is no `/WAIT` path to close, so the
card behaves identically at the specified **E = 2.0979 MHz** and at the experimental
divide-by-8 **fast-E** rate ([`docs/audio.md`](docs/audio.md) §0).

Paths below are relative to this directory; build commands run from the repository
root.

| | |
|---|---|
| [`docs/audio.md`](docs/audio.md) | the card — datapath, register map, DAC, filters, IC budget |
| [`docs/paula.md`](docs/paula.md) | **the MOS 8364 this card reproduces** — a functional overview, kept verbatim, ⚠ a *secondary* source (see its header for the trust precedence) |
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

⭐ **A MODULE PLAYS ON THE CARD ITSELF, since 2026-09-10.**
[`hardware/gal/verilog/modplay_tb.sv`](../hardware/gal/verilog/modplay_tb.sv) uploads a
module's samples into `audio_card.v` through `SPTR`/`SDATA` — real 6809 bus cycles on
the host port, `ASTAT` b6 honoured on every one — then delivers §5's register stream
tick by tick, **waiting for the card's own §8.2 timer interrupt** between ticks, and
records what the four `AD7528` pairs are given. `audio/tools/dacwav` renders that
through `render.c`'s analogue chain.

⛔ **`refplayer/card.c` is not in that pipeline at any point**, and the run script says
so at the top. What `refplayer` supplies is software: §4's loader decides where the
samples land, §5's tick engine decides which register gets which byte on which tick,
and the second of those is the trace a 6309 port is contracted to reproduce byte for
byte. The **reference** is libopenmpt and the **control** is `refplayer` scored against
the same reference — a card that scores like the control plays what the software asked
for, and one that scores worse is hardware.

**First result, on `mkprobe.py`'s note probe:** the card scores **0.9977** median
spectral correlation against libopenmpt where the control scores **0.9989**, at
**−0.01 cents**. It plays the right notes at the right pitch.

⛔ **And it found that the volume converter was being fed the SAMPLE byte** — after
the first volume change of a module, on every channel, while the state file held the
right value throughout ([`docs/audio.md`](docs/audio.md) §16 item 41). ⭐ **Repaired
the same day, by a deletion**: §16 item 39(b) already loads the port register at the
`PEND` write, so the walk's per-frame refresh was redundant — and it was landing in
the middle of W5, between a volume load and the strobe that captures it. Foldbacks on
U2 go **72 → 65** and the part still fits. The `02_setvol` probe goes from **0.7774
to 0.9901**.

⚠ **`audio_tb` could not see it, and the reason is worth carrying.** It asserts
`sfh(6) == $40` — *"VOL is one byte and goes straight through"* — which is a claim
about the **state file**, and the state file was right. **Nothing had ever compared
the converter's own pins against the file's contents.** `modplay_tb` does now, on all
four channels, every 4096 colour clocks.

⛔ **What remains is that the card plays 12 dB too quietly** — §6.1's ×4 is specified
and is not built (§16 item 40, **open**). `DACVOL` = 64 where §6.1 requires 255. It is
a level defect and nothing else: re-rendering with ×4 applied moves the probe by two
ten-thousandths, because `abcompare.py` normalises level on purpose. Where the ×4
belongs — two `74HC157`, one resistor and no raw mode, or the replayer — is a
specification decision, costed in §16 item 40.


⭐ **Both CPLDs are fitted and the card is simulated end to end.** `audio_tb` writes a
channel's `LC`/`LEN`/`PER` through the host port, enables it with `DMACON`, and watches a
sample byte come out of card RAM through `PEND`, a converter port register and into an
`AD7528` — then rewrites `LC`/`LEN` while the first pass is still playing and sees the
buffer loop to the new address and the end-of-buffer interrupt reach `/FIRQ`. 38 claims, 0 failed.

⭐ **Two audible defects were found on 2026-09-10 by running a separate Paula
implementation alongside it and diffing the output — and repaired the same day for no
package, no pin and no macrocell.** Every loop played one sample past its end, and
`LEN` = 0 gave one byte instead of Paula's 65,536 words
([`docs/audio.md`](docs/audio.md) §16 items 35 and 36). `CNT` is loaded as 2 × `LEN` − 1
now, the 17th bit exists, and `audio_tb` **counts the samples a buffer yields** — the
claim item 36 says was missing, and the reason both defects survived 43 green claims.
**225 claims across seven testbenches, 0 failed.**

⛔ **And `modcompare` was green throughout and could not have caught either.** It A/Bs
[`refplayer/`](refplayer/) — a **C model** of this card — against libopenmpt. `card.c`
ends a buffer correctly; the hardware did not. Two implementations of one paragraph, and
the A/B only ever tested one of them.

⭐ **Re-run against the repaired design, the oracle agrees** — card and an independent
Paula play the same bytes in the same cyclic order. The harness is in the tree now
([`../hardware/gal/verilog/oracle/`](../hardware/gal/verilog/oracle/), `npm run
check:oracle`); ⛔ it had been described as "entirely ours" and did not exist.

⭐ **And the same run found a third defect, now half closed: the FIRST pass of every note
read one byte past the buffer**, because W6 primed and W2 did not (§16 item 39). The
obvious repair — a second decrement in W6 — was written, measured correct, and **refused
by the fitter**. The one that worked *deleted* the duplicate instead: **W6 chains into
W1**, which already fetches and counts, so the accounting is uniform from the first pass.

⭐ **It is the only change that made the part smaller** — W6 from eleven steps to eight,
487 product terms to 461, peak LAB fan-in 39 to 37 — and the cell it freed then paid for
**item 39(b)**: the port register now loads at the `PEND` write itself, so the first
sample of a note reaches the converter instead of stopping at `PEND`. ⭐ **The card's
first pass is now the buffer exactly — `02 03 04 05` — and `check:oracle` asserts it**,
because the steady state was never wrong and asserting *that* would have caught neither
half of the defect.

⚠ **So the sequencer has a third arrangement, designed on 2026-09-10 and not decided.**
§10.3 moves the `(WT, T)` decode out of macrocells into four `27C512` with the step
counter as a `74HC163`: **40 ICs**, and items 7, 32, 35 and 36 all become reachable. It
costs 25 % of the throughput — 7.1× to 5.7× at ProTracker's top note — and it is
**measured (`npm run check:arom`, 59 claims) and not fitted**. §16 item 38 is the gate.

⛔ **One more thing designing it found, and it belongs to the design as it stands, not
to §10.3: the 16-bit `74HC283` chain was never given a propagation budget, and the
datasheet says it is 192 ns into a 53 ns window** (§16 item 37). Nothing on the card can
see that — the Verilog models logic and not timing, and the adder is inside neither
CPLD. ⭐ **The repair is free and it is a re-timing**: the walk never adds, so putting a
read and its write on either side of it gives the sum 229 ns. ⛔ What it costs is §16
item 34's 8-bit datapath, which is now withdrawn — and that is why §10.3 is five
packages rather than one.

| | | |
|---|---|---|
| **U1** the host register block, plus §4.2's counter and comparator and §9.3's read-back latch | `audio` | 88 of 128 cells, 62 of 64 I/O |
| **U2** the sequencer (§10.2) | `aseq` | ⚠ **128 of 128 cells**, 60 of 64 I/O |

⚠ **U2 is exactly full and U1 is not**, which is why every reduction this pass moved work
*to* U1 — sixteen state-file data pins there bought seven packages, because the counter,
the comparator and the read-back latch all want the same bus. **What is not closed is the analogue half**: the converter glitch, the cascaded
settling and the layout at 35 packages on an 18 cm card (§16 items 9, 10, 19).

**The model is validated structurally, and the tuning claim is not yet
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

⭐ **The CPLD fit is current** — `cpld/audio.jed` was refitted 2026-09-09 with §9.1's
decode, §9.3's read-back path and the prefetch latch's output enable, none of which had
ever been built. §16 items 0b and 30.
