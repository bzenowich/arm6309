# `refplayer` — the reference module player

**[`audio/docs/modplayer.md`](../../audio/docs/modplayer.md) §8, build step 0.** Everything
else in the mod-playback plan is gated on this existing:

> Without a reference implementation there is nothing to A/B against, and "it
> sounds about right" is not an acceptance test for a system whose entire premise
> is bit-exact compatibility.

```
cmake -B build-host -S . && cmake --build build-host
build-host/refplayer --wav out.wav --trace out.trace song.mod
ctest --test-dir build-host
```

## What it is

Three layers, matching the three documents:

| File | Models | Document |
|---|---|---|
| `card.c` | the sound card, at register level, one colour clock per step | [`audio.md`](../../audio/docs/audio.md) |
| `mod_load.c` | the loader — relocation and validation only | [`modplayer.md`](../../audio/docs/modplayer.md) §4 |
| `mod_replay.c` | the replayer — the tick engine and the full effect set | [`modplayer.md`](../../audio/docs/modplayer.md) §5 |
| `render.c` | the analogue chain, and the decimation that is **not** part of it | [`audio.md`](../../audio/docs/audio.md) §6.2, §7 |

`mod_replay.c` is written to be **transliterated into 6309 assembly**: no
allocation, no recursion, no unbounded loop, and every card access through one
`w()` function. Where C could be cleverer than the 6309 will be, it does what the
6309 will do — including the dirty-flag checks in `set_per()`/`set_vol()`, since
an unconditional write would produce a different trace.

## The two outputs, and why the second one matters more

- `--wav` renders stereo PCM, for listening and for A/B against an Amiga emulator.
- `--trace` writes the **register-write stream**, timestamped by tick.

The trace is the contract. Comparing audio tells you *something* is wrong;
comparing traces tells you which register write, on which tick, in which
channel. A correct 6309 replayer produces a byte-identical trace.

```
000001 ADATA   40
000001 ADMACON 0F      <- stop, then start, one write for all four channels
000001 ADMACON 8F
000001 AIDX    00      <- and the loop pointer immediately after (§5.3)
000001 ADATA   00
```

## Things this found that the documents had wrong

Writing a model is a way of reading a specification very carefully. Four things
came out of it, all now fixed in the documents:

1. **The volume LUT was one address bit short.** `audio.md` §6.1 addressed it
   with `{curve, VOL[5:0], SAMP[7:0]}`, but Paula's volume is 0..64 and needs
   **seven** bits. A 6-bit field silently pins every channel at 63/64 of its
   intended level. The fix costs nothing and is better: address the table with
   `{VOL[6:0], SAMP[7:0]}` — exactly the 15 bits of a 32K×8 pair — and make it
   **host-loadable** through `LIDX`/`LDATA`, so the curve becomes table content
   rather than a hardware feature.
2. **The tempo timer clock was wrong by 2.5×.** See `audio.md` §8.2 — `1773447`
   is the numerator ProTracker divides by BPM, not the rate the counter runs at.
3. **A model that runs the replayer in zero time hides the §5.3 race.** With no
   elapsed card time between the `DMACON` enable and the loop-pointer write, the
   write always beats the card's enable latch and every instrument loops from the
   wrong place. The replayer therefore charges each register store its real cost
   (`MOD_STORE_CC_DEFAULT`, 8 colour clocks ≈ 5 core cycles at 2.098 MHz), which
   makes the ordering **testable** instead of assumed.
4. **The LED filter model had a +0.6 dB passband bump** — 5th-order Butterworth
   Qs used where the real pole is the separate 4.4 kHz RC. A filter cannot add
   energy; `test_refplayer.c` now guards it at seven frequencies.

## What is verified, and what is not

Verified by `test_refplayer.c` and by measurement:

| | |
|---|---|
| Pitch | within **0.01 cents** of `3546895 / PER` across `PER` 113…856 |
| Shadow reload | the one-shot plays, then the loop runs from the **new** `LC` |
| Non-looping samples | go silent via the null-loop block, and never read unwritten RAM |
| Tempo | `TIMER = 1773447 / BPM`; BPM 125 fires **exactly 50 times a second** |
| Panning | ch 0,3 → L and ch 1,2 → R, with **complete** isolation |
| Volume law | `SAMP × min(VOL,64) / 4`, and volume 64 is reachable |
| Filters | monotonic; fixed pole measures −2.60 dB at 4 kHz, as a 4421 Hz pole should |
| Loader | rejects bad magic, 8-channel, zero song length; **accepts** truncated files |
| Period table | the **real** ProTracker 16 × 36 table (`period_table.c`), four invariants re-checked by the test suite |

### The period table

`period_table.c` carries the real ProTracker table, copied — never computed.
Deriving it from row 0 gets **229 of 576 entries wrong (40 %)**, worst case
**16 cents**, and every one of those 229 is a period that does not exist in its
own finetune row, so a `3xx` tone portamento slides toward a target it can never
land on and never terminates. (The same fact from another angle: **86 of the 384
octave relations are not `floor(x/2)`** — ProTracker rounded each octave
independently.)

Provenance and validation are in that file's header. In short: taken from
`pt2-clone`'s `periodTable`, with the finetune-0 row confirmed byte-for-byte
against `libopenmpt` 0.4.4 and `libmodplug` 1.0.0 — two implementations
independent of it and of each other — then checked for strict monotonicity, for
every entry lying within 1.5 of `856 / 2^(ft/96) / 2^(note/12)`, and for the
structural identity that finetune −8 is exactly one semitone below finetune 0.
`test_refplayer.c` re-runs all four, so an edit to the table cannot silently
corrupt it.

**Not verified, and load-bearing:**

- **The ten ProTracker behaviours** of [`modplayer.md`](../../audio/docs/modplayer.md)
  §10 and the position-advance ordering of §5.8 are implemented from the
  documented semantics. Published descriptions disagree with each other in
  exactly these places; only a real A/B settles them.
- **Attach modulation** (`ADKCON`) is a byte-oriented adaptation of a
  word-oriented behaviour, and no test module exercises it.
- **`E3x` glissando** is implemented; **`EFx` invert loop** is not, by decision
  ([`modplayer.md`](../../audio/docs/modplayer.md) §10.8).
- **The A500 filter component values.** The topology is modelled, not measured.

## Options

```
--wav FILE      stereo PCM out
--trace FILE    register-write trace ('-' for stdout)
--rate HZ       output sample rate (default 48000)
--seconds N     stop after N seconds (default: one pass of the song)
--ntsc          3.579545 MHz colour clock (audio.md §4.1)
--led           start with the LED filter on
--bypass        bypass all filtering -- WRONG for modules, see audio.md §7
--ram KB        populated sample RAM, 1..512 (default 128)
--info          parse and print, do not play
```

A non-zero `oob_reads` count at exit is always a loader bug, never a tolerance:
it means the card fetched sample data from RAM the loader never wrote.
