# Audio for an arm6309 Machine
## A 4-Channel PCM Card Modelled on Paula, Built From Pre-1990 Parts

**Question this answers:** the machine now has a CPU
([`plan.md`](../../cpu/docs/plan.md)) and a 256-colour card with tilemaps and a span writer
([`graphics.md`](../../video/docs/graphics.md)). What does the sound card look like, given that
the target workload is **playing existing Amiga OCS tracker modules correctly**?

**Short answer: build a Paula, not a Paula-alike.** The mod format is not a
container of audio data — it is a *program for a specific piece of hardware*,
and every one of the ~40,000 surviving OCS modules was tuned by ear against
Paula's exact period reference, its exact volume law, its exact hard-panned
stereo, and its exact buffer-reload semantics. Get those four right and mods
play; approximate any of them and you have built a sampler that plays mods
*nearly*. The good news is that Paula is a **very** cheap chip to reproduce in
1989 logic, for a reason worth stating up front: at 28.6 kHz × 4 channels it has
roughly **900× more time per operation than the video card's dot path**. It is
not a bandwidth problem. It is a state-machine problem, and a small one.

**Constraints taken as given (yours):**
- **4 channels, 8-bit signed PCM**, Paula's model.
- **Load an existing `.mod` and play it back correctly** — this is the acceptance test.
- **Parts available before 1990.** No CPLDs, no FPGAs. GALs are in (the video card uses 8).
- Same house rules as the video card: period-honest silicon, one card, a
  documented register map, and an honest IC count.

> **This supersedes [`graphics.md`](../../video/docs/graphics.md) §17's sound-card paragraph**, which
> assumed an **Ensoniq 5503 DOC** implemented as an MCU card. §12.3 below explains
> why the DOC is the wrong part for *this* workload even though it is the better
> part in the abstract, and §12.5 keeps the MCU card — with this document's register
> map — as the bring-up vehicle rather than the product.

---

## 0. Summary — the verdict in one table

| Question | Answer | § |
|---|---|---|
| **Discrete card, real Paula, a period sound chip, or an MCU?** | **Discrete card.** **57 ICs** (§10, re-tallied), one Eurocard plus a physically separate analogue section. | §12 |
| **Where does the sample data live?** | **Card-local SRAM, 128 KB** (footprint for 512 KB). The card never touches the bus for audio. | §5 |
| **How are the four channels implemented?** | **One time-multiplexed datapath**, 8 slots per colour clock, state in a 32-bit-wide SRAM file. | §3 |
| **How is per-channel pitch generated?** | **Compare-against-a-free-running-counter**, not four down-counters. Kills 12+ ICs. | §4.2 |
| **What is the period reference clock?** | **3.546895 MHz — the Amiga PAL colour clock**, from a 28.37516 MHz crystal ÷8. Non-negotiable. | §4.1 |
| **How is volume applied?** | **A host-loadable 32K×8 lookup table**, `{VOL[6:0], SAMP[7:0]} → 12-bit signed`. Same trick as the palette LUT; the volume curve is table content, not hardware. | §6.1 |
| **How are channels summed?** | **Sequentially, into two latched accumulators**, one channel per slot, presented to the DACs once per colour clock. No output sample rate, no resampling, no jitter — the DAC input still changes on the exact colour clock a channel's sample changed on. | §6.2 |
| **What DAC?** | **2 × LTC7545A** — 12-bit parallel MDAC with an input latch, the current-production `AD7545A` pin-compatible. Not a serial audio DAC — §6.3. **Coded offset binary, not two's complement** — §6.3. | §6.3 |
| **Do we need the Amiga filter?** | **Yes, and not for nostalgia.** It is the reconstruction filter for channels running below ~16 kHz. Both filters, switchable. | §7 |
| **Where does mod tempo come from?** | **An on-card 16-bit timer clocked at colourclock/5 = 709.379 kHz — the Amiga's CIA clock exactly**, so `Fxx` BPM values are CIA-B-identical. Costs one slot, zero ICs. | §8.2 |
| **Which interrupt line?** | **`/FIRQ`.** Video's VBL owns `/IRQ`. A 6809 `FIRQ` is what a replayer tick should be. | §8.1 |
| **What does mod playback cost the 6309?** | **~2.7 % of a 2.098 MHz CPU** for the replayer, with a 19× worst-case margin; **~187 ms once** to upload 128 KB of samples via `TFM X+,Y`. | §13, [`modplayer.md`](modplayer.md) §7 |
| **What does this card do that Paula cannot?** | No minimum period; per-channel panning (+2 ICs); 8 channels at half period resolution; a programmable volume curve. | §11 |

**Net: 57 ICs**, against the video card's 36. One oscillator, **one internal clock
domain and an asynchronous host port** (§9.4), no bus mastering, no `/WAIT`, and the
only tight path in the design is a 35 ns pipeline stage that is directly analogous
to — and 5 ns *looser* than — the video card's 39.7 ns dot path.

> ⚠ **"35 ICs" and "one clock domain" are both superseded (design review — Aud-M2,
> Aud-M3, Aud-M5, and decision D9).** The old tally counted the datapath and left out
> four things that are not optional: the L/R sum path (§6.2 — ten packages the old
> §10 never listed), the host-visible counters `SPTR`/`LIDX`/`AIDX` (41 flops of
> counter — §9.5), the host-boundary synchroniser and multi-byte commit staging
> (§9.4), and the open-collector stage `/FIRQ` needs and a GAL output cannot provide
> (§8.1). "One clock domain" was true of everything downstream of the crystal and
> false at the register port, which is where the failures of §9.4 live. §10 now
> tallies **57**, itemised, with a delta table showing where the twenty-two came
> from. Every count elsewhere in *this* document has been corrected; the "35" quoted
> in [`machine.md`](../../docs/machine.md) and in
> [`graphics.md`](../../video/docs/graphics.md)'s comparison tables has not, and needs to be.

**E-rate compatibility.** The card is **unaffected by the machine's E rate**. Every
audio-timing figure in this document is referred to the card's own 28.37516 MHz
crystal, not to E; the register port is asynchronous to E by construction (§9.4);
and §9.3's prefetch means there is no `/WAIT` path to close at any rate. The machine
is specified at **E = 25.175/12 = 2.0979 MHz and only that rate**
([`machine.md`](../../docs/machine.md)). The divide-by-8 **fast-E** rate (3.1469 MHz) is
experimental and not guaranteed elsewhere in the machine, but nothing on this card
breaks at it and the two figures that move both move the right way: §13.2's 128 KB
upload falls from 187 ms to 125 ms, and §9.4's register-tearing windows shrink by a
third (~8 colour clocks per host store becomes ~5.4). The card neither requires
fast-E nor objects to it.

---

## 1. What "plays mods correctly" actually requires

This is the specification. Everything downstream is in service of it.

A ProTracker module is a stream of register writes to Paula, issued on a timer
tick, computed by a replayer whose arithmetic assumes specific hardware
behaviour. Nine things have to be right. They are cheap individually; the point
is that *all nine* are load-bearing.

| # | Requirement | Why it is load-bearing | Cost here |
|---|---|---|---|
| 1 | **Period reference = 3.546895 MHz** (PAL colour clock) | The `PER` register *is* the pitch. A different reference detunes every module by the ratio. | one crystal (§4.1) |
| 2 | **`PER` is a divisor of that clock; sample rate = 3546895 / `PER`** | Not a phase accumulator, not a fractional step. A per-channel *variable fetch clock*. This is why Amiga audio sounds like Amiga audio. | §4.2 |
| 3 | **Auto-reload from shadow `LC`/`LEN` at buffer end** | ProTracker's one-shot→loop idiom: trigger the note with `LC` = sample start, then rewrite `LC`/`LEN` to the repeat point *while the first pass is still playing*. Without the shadow, every looped instrument is wrong. | §3.3 |
| 4 | **Volume 0–64, linear, applied as an 8×6 multiply** | Volume slides, tremolo, and the `Cxx` command. 64 is unity, 65 levels. | §6.1 |
| 5 | **Hard-panned stereo: ch 0,3 → left; ch 1,2 → right** | Not a stylistic choice — modules are *mixed* for it. Centre-panning a mod makes it sound wrong in a way listeners notice immediately. | free (§6.2) |
| 6 | **`DMACON` set/clear semantics with the restart delay** | Enabling a channel reloads the pointer from `LC` and the counter from `LEN`, and the first fetch lands one sample period later. Note retriggering depends on it. | sequencer terms |
| 7 | **Per-channel end-of-buffer interrupt** | Not used by classic ProTracker (which relies on #3), but used by later players and by anything doing streaming. | §8.1 |
| 8 | **Direct `AUDxDAT` writes** (CPU-fed, no DMA) | The one-shot idiom in several players, and the only way to do software mixing. | one state-file byte |
| 9 | **`Fxx` tempo mapping identical to CIA-B timer A** | `Fxx` ≥ `$20` sets BPM; the replayer loads a CIA reload of `1773447 / BPM` against a **709,379 Hz** clock. Ticking at the wrong rate makes every song play at the wrong speed. | §8.2 |

**What is *not* required, and this is the useful half of the specification:**

- **No interpolation.** Paula has none. Adding it makes mods sound wrong (softer,
  less bright) — this is the single most common complaint about mod players that
  "improve" on the hardware.
- **No band-limited synthesis.** Paula's zero-order hold and its 4.4 kHz analogue
  filter *are* the anti-imaging strategy (§7).
- **No mixing to a common sample rate.** Paula sums four asynchronous analogue
  currents. §6.2 does the same thing digitally and gets the same result exactly,
  which is the design's nicest property.
- **No more than 4 channels, no more than 8 bits.** Everything beyond that is
  §11's optional superset, not the acceptance test.

---

## 2. The budget — why this card is small

The video card's design is dominated by one number: 39.72 ns per pixel. Every
architectural decision in [`graphics.md`](../../video/docs/graphics.md) — the 4-way interleave, the
`'153` mux, the 15 ns LUT, the pipeline discipline — exists to survive it.

The sound card's equivalent number is **31.9 µs per sample** (period 113, the
highest note ProTracker emits), and the comparison is not close:

| | Video dot path | **Audio channel** | Ratio |
|---|---|---|---|
| Event rate | 25.175 MHz | **31.4 kHz worst case** | **802×** |
| Time per event | 39.72 ns | **31.9 µs** | |
| Events/s, all channels/pixels | 25,175,000 | **125,600** | **200×** |
| Memory accesses/s needed | ~25 M | **~126 k** | **200×** |

**126,000 SRAM accesses per second is not a memory system.** A single 55 ns SRAM
delivers 18 M/s. The card has ~140× more sample-fetch bandwidth than it can
consume, before any interleaving at all.

So the whole design problem is: *how do you hold and update the per-channel state
of four independent variable-rate DMA engines using as few packages as possible?*
That is a state problem, and time-multiplexing — which the video card could not
afford anywhere — is here essentially free. **One datapath does all four
channels, plus the tempo timer, plus host access, and still idles.**

This is also why Paula itself is a small part of the Amiga chipset while Agnus
and Denise are large ones. The design is telling you the same thing Commodore's
did.

**What §2 prices is bandwidth, and bandwidth is not what this card costs.** The
argument above is sound and survives review unchanged — 126,000 accesses per second
against 18 M/s is not a memory system. What it does *not* price is **state**: the
per-channel pointers, the host-visible counters, the sum path and the host-boundary
staging, which is where §10's honest package count actually goes. A card can be
enormously oversupplied in time and still cost 57 packages, and this one does.

---

## 3. Architecture — one slot-walked datapath

### 3.1 The slot walk

One 28.37516 MHz oscillator (the Amiga PAL master crystal) drives everything:

```
28.37516 MHz  ──┬──► slot clock, 8 slots per colour clock, 35.24 ns each
                │
                └──► ÷8 ──► 3.546895 MHz colour clock   (the period reference)
                     ÷40 ─► 709.379 kHz                 (the CIA-B tempo reference)
```

Each colour clock is one **frame** of 8 slots:

| Slot | Job |
|---|---|
| 0–3 | **channels 0–3**: read state, compare event time, look up scaled sample, accumulate into L or R |
| 4 | **tempo timer**: compare, reload, raise `/FIRQ` |
| 5 | **host service**: retire one posted write, or prefetch one read (§9.3) |
| 6–7 | **deferred work**: pointer increment, length decrement, buffer reload, `LC`/`LEN` shadow copy |

Slots 0–3 run **unconditionally every colour clock**, which is what makes the
design jitter-free: a channel's sample transition always lands on its true
Paula boundary, never on a "whenever the sequencer got round to it" boundary.
Slots 6–7 are where the rare, expensive work goes — at most 126,000 pointer
updates per second against 7.1 M deferred slots per second, a **56× margin**.

### 3.2 The pipeline

Each slot is three pipeline stages, one slot deep each, exactly the shape of the
video card's `index latch → LUT → output latch`:

```
  stage A  (35 ns) : state-file read  -> {NEXT[15:0], VOL[6:0], SAMP[7:0], DMAEN}
  stage B  (35 ns) : compare NEXT vs the free-running counter
                     LUT read  {VOL, SAMP} -> 12-bit OFFSET-BINARY scaled sample
  stage C  (35 ns) : latch the scaled sample into this side's hold latch;
                     on a compare hit, queue the channel for slots 6-7
  stage D  (35-70) : add the held sample into this side's accumulator (§6.2)
```

**The pipeline is four stages, not three**, because the 12-bit sum of §6.2 does not
close in one slot: three `74HC283` ripple in ≈62 ns against a 35.24 ns slot, so the
add gets two slots and the sample it is adding has to be held across them. That is a
latency change, not a throughput change — the walk still retires one channel per slot
— and it is the same shape as the fallback below.

**Stage B is the tight path**, and it is the card's only one:

```
  address setup from the sequencer GAL      10 ns
  32K x 8 LUT SRAM, 20 ns grade             20 ns
  setup into the accumulator input latch     5 ns
                                     total  35 ns   <- exactly the slot
```

That closes at the 20 ns SRAM grade with zero margin, and at the 15 ns grade with
5 ns. **Specify 15 ns for the LUT** and bench it (§16 item 2). Note that this is
the *same* decision the video card makes at §6.1 and with *more* margin — the dot
path has 11.7 ns against a 39.7 ns budget with three parts in the chain; this has
one part in the chain.

If it does not close, the retreat is clean and costs one package: split the LUT
address across two pipeline stages by latching `{VOL, SAMP}` (stage A → A′), which
buys a whole extra slot and drops the requirement to 70 ns. **+1 `'574`, no
software change.**

### 3.3 The channel state, and the shadow that makes mods work

Per channel, in the 32-bit-wide state file:

| Field | Bits | Written by | Meaning |
|---|---|---|---|
| `LC` | 19 | **host** | shadow location — where the *next* buffer starts |
| `LEN` | 16 | **host** | shadow length, **in words**, Paula-identical |
| `PER` | 16 | **host** | period, in colour clocks |
| `VOL` | 7 | **host** | 0–64 — **seven bits**, per §6.1's correction |
| `PTR` | 19 | sequencer | current byte pointer |
| `CNT` | 17 | sequencer | bytes remaining in the current buffer |
| `NEXT` | 16 | sequencer | colour-clock count at which this channel next ticks |
| `SAMP` | 8 | sequencer | the byte currently being held out to the DAC |
| flags | 4 | both | DMA enable, attach-period, attach-volume, IRQ pending |

**The packing is not arbitrary.** Word 0 of each channel holds exactly
`{NEXT[15:0], VOL[6:0], SAMP[7:0], DMAEN}` = **32 bits**, which is why stage A
of §3.2 needs one access and not two.

> ⚠ **Corrected — the packing was one bit over, not one bit under.** This word was
> first written as `{NEXT[15:0], VOL[5:0], SAMP[7:0], DMAEN, ATT}`. §6.1's correction
> then gave `VOL` its seventh bit (0–64 is 65 levels), which makes
> `16 + 7 + 8 + 1 + 1 = 33` — one bit past the state file's 32-bit width, and the
> whole reason stage A is a single access. **`ATT` moves to word 1.** It is consulted
> only on a compare hit, which is a deferred slot that reads words 1–3 anyway, so
> moving it costs nothing and restores the exact 32. Everything the per-colour-clock walk touches
is in that word; `LC`, `LEN`, `PER`, `PTR` and `CNT` live in words 1–3 and are only
read in the deferred slots. Freeze this layout with the register map (§9.3) — it is
the reason the state file is 32 bits wide rather than 16, and the reason the design
closes at a 35 ns slot.

**The shadow is requirement #3 in §1, and it is one wire.** When `CNT` reaches
zero the sequencer copies `LC → PTR` and `LEN×2 → CNT` **at that instant**,
using whatever the host has since written into `LC`/`LEN`. That is precisely
Paula's behaviour, and it is what ProTracker's one-shot→loop idiom depends on:

```
  tick 0  : LC <- sample start,  LEN <- full length,  DMACON <- enable channel
  tick 1  : LC <- repeat start,  LEN <- repeat length          ; still playing pass 1
  ...     : buffer exhausts, sequencer copies the *new* LC/LEN ; loops forever
```

Get this wrong — copy at note-start instead of at buffer-end — and every
instrument with a loop plays its attack forever. It is the single highest-value
line in the sequencer GAL.

### 3.4 What is deliberately *not* in the datapath

- **No multiplier anywhere.** Volume is a table lookup (§6.1), not an 8×6 multiply.
  There *is* an adder in the audio path — the L/R channel sum of §6.2 — but it adds
  two 12-bit numbers twice per colour clock, which is not the same kind of object.
- **No divider anywhere.** Period is a divisor applied by comparison (§4.2), never
  computed.
- **No FIFO, no buffering, no DMA arbitration.** Sample memory is card-local and
  200× oversupplied (§2), so there is nothing to arbitrate.
- **No output sample rate.** §6.2.

> ⚠ **Superseded (design review, Aud-M2).** This section used to claim that
> **"the only adder on the card is the shared 16-bit `'283` chain in slots 6–7"**,
> while §0 and §6.2 simultaneously claimed the four channels were summed
> "combinatorially, asynchronously". Both cannot be true, and neither was costed:
> the combinatorial sum needs six `'283` and eight `'574` that appear nowhere in the
> old §10, and the sequential sum needs an adder the shared chain cannot supply
> without an operand mux that was equally unbudgeted. §6.2 now resolves it in favour
> of latched accumulation with **dedicated** 12-bit adders, and the sentence below
> replaces the false one.

The video card's "no adder anywhere" property (minimal256.md §3) survives here only
in the narrow form that matters: **there are two adders on this card and neither is
in a critical loop.** The shared 16-bit `'283` chain in slots 6–7 does `NEXT`+`PER`,
`PTR`+1 and `CNT`−1 at 126 kHz, work no one is waiting for; the two 12-bit `'283`
adders of §6.2 do the L and R channel sums at 3.55 MHz, with the whole of the
following colour clock to settle before the DAC looks at them. Neither one is ever
in the sample-fetch path, and there is still no multiplier and no divider.

---

## 4. Pitch: the colour clock, and the trick that saves twelve packages

### 4.1 The clock is not negotiable, and it is a stock crystal

A ProTracker note is a `PER` value; the resulting sample rate is
`3546895 / PER` Hz. Note C-2 is `PER` = 428 → `3,546,895 / 428` = **8287.1 Hz**. If
the card's reference is anything else, every module is transposed by the ratio.

> ⚠ **Corrected (design review, Audio NOTE).** This example previously read
> **8286 Hz**. `3,546,895 / 428 = 8287.14`; the reference model's unit test asserts
> 8287. One digit, in the document's own headline example of the number the whole
> card exists to reproduce.

| Reference | Source | Error vs PAL Amiga |
|---|---|---|
| **3.546895 MHz** | **28.37516 MHz ÷ 8 — the Amiga PAL master crystal** | **0** |
| 3.579545 MHz | 28.63636 MHz ÷ 8 — the Amiga NTSC master crystal | +0.92 %, **+16 cents** |
| 3.579545 MHz | a bare NTSC colourburst crystal (the cheapest crystal made) | as above |
| anything derived from 25.175 MHz | the video master | **no integral relationship** |

**Use 28.37516 MHz.** It is a real, purchasable crystal — it is what every PAL
Amiga has in it — and the overwhelming majority of surviving OCS modules were
composed on PAL machines. The 16-cent NTSC error is a uniform transposition
rather than detuning, so it is *survivable*, but there is no reason to accept it
for the price of one crystal.

**Provide the NTSC oscillator as a socketed second can and one bit in `ACTRL`**
(+1 part, +1 mux term) for the minority of NTSC-timed material and for anyone
comparing against an NTSC Amiga. `ACTRL` gates it to a quiet moment — a mid-song
clock swap is a glitch, exactly as the video card gates its ÷12↔÷8 switch to
vertical blank ([`graphics.md`](../../video/docs/graphics.md) §5.2).

### 4.2 Compare, do not count down

The obvious implementation of "tick every `PER` colour clocks, per channel" is
four loadable 16-bit down-counters. Priced honestly:

| Approach | Packages |
|---|---|
| 4 ch × 2 × `74HC40103` (8-bit presettable down counter) + 4 ch × 2 × `'574` to hold `PER` | **16** |
| 4 ch × 2 × `GAL22V10` (12-bit loadable counter + terminal count) | 8 GALs — and the video card already argues 18 GALs is where "why not a CPLD" bites | **8 GALs** |
| Decrement `NEXT` in the state file every colour clock | 4 channels × (read + write) at 14.2 MHz = **17.5 ns per SRAM access.** Does not exist in 1989. | — |

**None of those is the right answer. Invert the problem:**

```
  one free-running 16-bit counter, clocked at the colour clock       2 ICs
  per channel, store NEXT = the count at which this channel ticks    (in the state file)
  each slot, compare the channel's NEXT against the counter          2 ICs
  on a hit: SAMP <- next byte;  NEXT <- NEXT + PER   (mod 65536)     (shared adder, slot 6-7)
```

The comparison is a **read-only** state-file access — one access per 35 ns slot,
comfortable at any SRAM grade. The addition happens only on a hit, at ≤126 kHz,
in a deferred slot. **2 × `74HC590` + 2 × `74HC688` = 4 ICs for all four
channels**, against 16 for the counter bank.

**It is also behaviourally identical to Paula, including the edge cases**, which
is the part that matters:

- **Mid-note `PER` change** (vibrato, portamento — mods do this on nearly every
  tick): the pending `NEXT` was computed from the *old* `PER`, so the current
  sample plays out at the old rate and the new period takes effect at the next
  tick. That is exactly what a reload-on-terminal-count down-counter does.
- **`PER` = 0 or 1**: clamp in the sequencer, as Paula effectively does.
- **Counter wrap**: `NEXT` is modulo 65536 and so is the comparison. `PER` < 65536
  always, so a channel can never be lapped.

### 4.3 No minimum period — and why that is a superset, not a difference

Paula fetches one word (two samples) per audio DMA slot, and gets one slot per
channel per raster line — 227 colour clocks on PAL. That imposes a floor of
`PER` ≈ 114, and the conservative figure quoted in the hardware manual is 124
(≈28.6 kHz). ProTracker's top note B-3 is `PER` = 113, right on the edge, which
is why B-3 misbehaves on real hardware.

This card fetches from local SRAM in a deferred slot with a 56× margin (§3.1), so:

| | Paula | **This card** |
|---|---|---|
| Minimum `PER` | ~114–124 | **~30** |
| Maximum rate per channel | 28.6 kHz | **118 kHz** |
| Aggregate fetch rate at the floor | 4 × 28.6 kHz | **4 × 118 kHz = 473 k/s, vs 7.1 M/s available** |

**Do not emulate the floor**, but document it: a module that plays correctly here
at `PER` = 60 will not play on an Amiga, and software written against this card's
extended range does not port back. This is the same posture
[`graphics.md`](../../video/docs/graphics.md) §6.4.2 takes for the 8bpp tilemap — a deliberate,
stated superset rather than a silent divergence.

---

## 5. Sample memory: on the card, and why

Paula DMAs from chip RAM. The three options here:

| Where | Bus cost | Verdict |
|---|---|---|
| **Card-local SRAM** | **zero** — the card is bus-passive except for register writes | **This.** |
| System RAM over the backplane | 4 × 28.6 kHz × 1 B = 114 KB/s = **5.4 % of a 2.098 MHz bus** | Cheap in *bandwidth*, but needs a bus-master and an arbitration mechanism the machine does not have. Not worth inventing for 5 %. |
| The video card's 512 KB VRAM | shares a scheduled resource | **Ruled out** — [`graphics.md`](../../video/docs/graphics.md) §17 already rejects this for the DOC card, and every word of that reasoning transfers. |

**1 × AS6C1008-55 (128 KB), footprint for 4 (512 KB).** The same part as the video
card's framebuffer, so it is one line item across the machine.

**Is 128 KB enough?** A ProTracker module's `.mod` file is header + patterns +
sample data; the sample data is what has to be uploaded. Typical 4-channel
modules run 40–250 KB of sample data; the format's theoretical ceiling is 31
samples × 128 KB, which nothing real approaches.

| Sample data | Coverage |
|---|---|
| 64 KB | most early/chiptune modules |
| **128 KB** | **the large majority of the ProTracker corpus** |
| 512 KB | everything, including the 8-channel and OctaMED material of §11.2 |

Populate one chip; leave three footprints. That is +0 cost now and +3 ICs later,
and it is the same "leave the expansion on the board" call the video card makes
for its interleave.

The host writes samples through an auto-incrementing `SPTR`/`SDATA` pair (§9),
retired in slot 5 — a posted write, exactly the discipline of
[`graphics.md`](../../video/docs/graphics.md) §3.1, and with far more slack. Upload cost is in §13.2.

---

## 6. Volume, mixing, and the DAC

### 6.1 Volume is a lookup table, not a multiplier

Paula applies a 6-bit volume to an 8-bit signed sample. In 1989 logic that is
either an 8×6 parallel multiplier (a `TRW TDC1008`-class part — expensive, hot,
and absurd at 126 kHz) or a table.

**Table.** Address a 32K×8 pair with `{VOL[6:0], SAMP[7:0]}` — 15 bits, which is
exactly the part:

```
  A14..A8  VOL[6:0]         0..64, Paula's range
  A7..A0   SAMP[7:0]        signed
  D11..D0  scaled sample, 12-bit OFFSET BINARY  <- 2 x 32K x 8, 15 ns  (§6.3)
```

> **Corrected (build step 0).** This section first addressed the table with
> `{curve, VOL[5:0], SAMP[7:0]}`. That is one bit short: **Paula's volume is
> 0–64, which needs seven bits**, and a 6-bit field silently pins every channel
> at 63/64 of its intended level — uniform, so not detuning, but a real 0.14 dB
> of headroom thrown away and a divergence from the acceptance test for no
> reason. Writing the model in `audio/refplayer/` is what found it.
>
> The fix costs nothing and is strictly better. Give the volume its seventh bit,
> and make the table **host-loadable** through a `LIDX`/`LDATA` pointer/data pair
> (§9.2) instead of selecting a curve with an address line. Entries for VOL
> 65–127 are unreachable in Paula-compatible use and simply repeat VOL 64.

This is the **same move** the video card makes twice: the palette LUT
([`graphics.md`](../../video/docs/graphics.md) §9), and §6.4.3's use of the LUT's dead 127/128 to
hold a text-attribute colour path. Here the table is 3/4 full at `VOL` ≤ 64, and
the spare `A14` buys the curve bit for free.

What the curve bit is worth:

| Table contents | Use |
|---|---|
| `SAMP × min(VOL,64) / 4` — **exact Paula linear law** | mod playback, the acceptance test |
| anything else: logarithmic (dB-linear) volume, a soft-clip, a de-emphasis curve, a per-machine calibration | native software, and §11.4 |

**The curve stops being a hardware feature and becomes table content**, which is
strictly more capable than the address-line version and costs one `TFM` burst —
65,536 bytes, ~94 ms at 2.098 MHz — once at boot. `ACTRL` bit 7 keeps the card
quiet until it is done, which is why reset forces `ACTRL = 0`.

**And the table is where the DAC's coding is fixed, too.** The `LTC7545A` takes
unsigned data, so the entries hold the scaled sample **already biased into 12-bit
offset binary** — `entry = SAMP × min(VOL,64) / 4 + 2048`, silence = `$800`. §6.3
derives that and shows why it makes the two-term sum of §6.2 come out right with no
correction term. It is the second time in this section that something a discrete
design would have spent a package on is deleted by being table content instead.

**12-bit output, not 8.** At `VOL` = 1, an 8-bit output would reduce the sample to
±2 — two bits of resolution, and volume fades would be audibly stepped. Paula's
internal product is ~14 bits. 12 bits costs one extra SRAM and matches the DAC
(§6.3); the two low bits Paula has beyond that are below the noise floor of any
realistic analogue stage.

### 6.2 The sum is latched, not resampled — and that is still the design's best property

Paula produces four independent current-output DACs and sums them at an analogue
node. There is **no output sample rate** anywhere in an Amiga's audio path — each
channel is a zero-order hold at its own rate, and the sum is continuous-time.

Every software mod player resamples to a fixed output rate and spends real effort
(band-limited synthesis, oversampling) hiding the damage. This card does not have to,
and — this is the correction — it does not need a *continuous-time* sum in order not
to. What it needs is for the DAC input to change **on the exact colour clock on which
a channel's sample changed**, because that is the only instant at which anything in
Paula's audio path changes either. A latched sum delivers that; a combinational one
delivers it and a package count the card cannot pay.

> ⚠ **Superseded (design review, Aud-M2).** This section previously specified the
> sum as **"combinatorial, asynchronous"**, and §0 said the same. It was never
> costed. A continuously live 12-bit + 12-bit sum on each side has to be fed from
> four channel-value latches, because the LUT output is one channel wide and changes
> every slot: that is **6 × `'283` + 8 × `'574` = 14 packages**, against the four
> `'574` the old §10 listed for "accumulators". It also contradicted §3.4's "the only
> adder on the card is the shared `'283` chain in slots 6–7", which was the other
> half of the same finding. **The latched version below is what the card is.** It
> costs the *same* fourteen packages as the combinational one — the saving is not why
> it is chosen — and it is strictly better behaved: it keeps the colour-clock event
> grid intact, it presents the DAC static data instead of a settling adder output
> (which is what the transparent input latch of §6.3 requires and what deletes the
> glitch story below), and it makes §3.4 true again.

**Sequential accumulation, one channel per slot, into two latched accumulators.**
The channel walk is unchanged (`ch0..ch3` in slots 0–3); what changes is what stage D
does with each scaled sample as it falls out of the pipeline:

```
  per frame, in order, one channel per slot:

    L_ACC <- 0     + scaled(ch0)      ; a LOAD:  A = 0, no carry to propagate
    R_ACC <- 0     + scaled(ch1)      ; a LOAD
    R_ACC <- R_ACC + scaled(ch2)      ; an ADD:  full 12-bit ripple
    L_ACC <- L_ACC + scaled(ch3)      ; an ADD

  one colour clock later:
    DAC /WR pulse latches L_ACC[12:1] and R_ACC[12:1]
    each accumulator is cleared AFTER that edge, before its next LOAD
```

The accumulators are cleared once per frame, so the *first* channel of each side is a
**load** and not an add (`0 + x`), which is why no zero-forcing mux is needed on the
adder's `A` port and why the accumulators are `'273` rather than `'574` — the
asynchronous clear is the whole mechanism, and it is three packages cheaper than the
`'157` mux that would otherwise force the zero. The pairing is Paula's:
`ch0`+`ch3` → L, `ch1`+`ch2` → R.

**The DAC input therefore changes once per colour clock, on the colour clock.** There
is no resampling, no interpolation, no jitter, and no aliasing introduced by the
mixer, because there is still no mixer sample rate to alias against. The cost is a
uniform **one-to-two-colour-clock (282–564 ns) pipeline delay**, common-mode between
the two sides, which is at most 1/56 of the shortest sample period ProTracker can ask
for and identical on every channel. Nothing in §1's nine requirements can see it — a
constant delay is not jitter, and it is not even audible as delay.

**Why the sum does not time-share the `'283` chain in slots 6–7.** It could, and it
is *more* expensive that way. That chain is 16 bits wide and its operands come off
the state-file read bus; giving it a second job needs a 2:1 select on both 16-bit
operand ports — **8 × `74HC157`** — on top of the hold latch below. A dedicated
12-bit adder per side is **6 × `74HC283`** and needs no operand select at all. Two
packages cheaper, no shared-timing risk between the audio path and the pointer path,
and §3.4 gets an honest sentence instead of a false one.

**Why the add is two slots deep.** A 12-bit ripple through three `74HC283` is
`t_pd(A→C4) + t_pd(Cin→Cout) + t_pd(Cin→Σ)` ≈ 20 + 17 + 25 = **62 ns** worst case at
`74HC`, against a 35.24 ns slot. The load step has no carry to propagate and closes in
≈25 ns; the add step does not. So the scaled sample is held in a per-side latch
(`L_HOLD`/`R_HOLD`) and the adder gets **two slots — 70.5 ns** — to settle before the
accumulator clocks. One hold latch per side and not one shared latch, because the two
sides' add windows overlap by one slot (ch2's runs slots 5–6, ch3's runs 6–7).

Packages, itemised so §10 has something to add up:

| Qty | Part | Role |
|---|---|---|
| 4 | `74HC574` | `L_HOLD` / `R_HOLD` — 12 bits per side, holding the scaled sample across the add |
| 6 | `74HC283` | two 12-bit adders, one per side; Σ plus carry-out is the 13-bit result |
| 4 | `74HC273` | `L_ACC` / `R_ACC`, 13 bits each, **clearable** — `'273` and not `'574` precisely because the frame boundary needs an asynchronous clear |
| 0 | — | output register: **the `LTC7545A`'s own input latch** (§6.3), which is why there is no `'574` here |

**DAC latch timing, against the transparent-latch constraint of §6.3.** The
`LTC7545A`'s latch is transparent while `CS` and `WR` are both low and captures on
whichever rises first, so it needs `tDS` = **100 ns** of stable data before that edge
and `tDH` = **5 ns** after it — a constraint an edge-triggered `'574` would not have
imposed (§6.3), and the reason the sum has to be latched at all. Three ordering
constraints follow, and they are stated as constraints because the exact slot
placement is a sequencer-fit detail (§16 item 7) rather than something to freeze here:

| Constraint | Requirement | Available |
|---|---|---|
| **Load** path `0 + x` → accumulator | ≈25 ns (`A` = 0, no carry ripple) | **1 slot, 35.2 ns** |
| **Add** path `ACC + x` → accumulator | ≈62 ns (full 12-bit ripple) | **2 slots, 70.5 ns** |
| Accumulator static before the `/WR` edge | **100 ns → ≥ 3 slots** | the `/WR` edge sits ~3 slots into the following frame |
| Accumulator undisturbed after the `/WR` edge | 5 ns | **the clear follows the edge by a full slot, 35.2 ns** |

The third row is the one that orders the frame: **the clear must come after the DAC
latches, not before it**, and the accumulate schedule may need shifting a slot or two
into the following frame to open that window. The cost of any such shift is
**latency only** — a uniform one-to-two-colour-clock (282–564 ns) delay, common-mode
between the two sides — and **the invariant it must not break is that the DAC input
changes exactly once per colour clock, on the colour clock.** That invariant is the
whole of §6.2's claim; everything above it is scheduling.

The sum of two 12-bit **offset-binary** values is 13 bits and the DAC is 12, so
**the bottom bit is dropped once, at the converter** — bits 12..1, a wire, not a
stage. §6.3 shows why that shift is also exactly the re-biasing the offset-binary
encoding needs. A single channel therefore reaches 11 bits of the DAC and two
channels at full scale reach all 12, which is the same headroom split Paula's four
current-output ladders make.

> ⚠ **The "~20 ns adder settling glitch on the DAC input" is withdrawn (Aud-M2).**
> That artefact — and the `'574` deglitch latch the old §10 held in reserve against
> it — was a consequence of the combinational sum. The DAC is now driven from static
> latch outputs by a `/WR` pulse placed 141 ns after they settle, so no adder
> transient reaches the converter at all. What remains is the converter's *own*
> code-transition glitch, 5 nV·s on the `LTC7545A` against 400 nV·s on an `AD7545`,
> which is the half of that budget worth keeping (see the sourcing note in §6.3).
> **§16 item 8 is retired.**

> **Recorded alternative — four DACs and an analogue sum.** Paula does not add
> anything: it runs four current-output ladders into summing nodes. Doing the same
> here — 4 × `LTC7545A`, `ch0`+`ch3` into the left I/V virtual ground, `ch1`+`ch2`
> into the right — deletes both hold latches, both adders and both accumulators
> (**−14 packages**) for **+2 DACs**, keeps all 12 bits per channel instead of
> spending one on the `>>1`, and updates each converter on its *own* channel event
> rather than on the frame. It is the more Paula-exact answer and it is twelve
> packages cheaper net (**−14 digital, +2 converters**). It is **not** adopted here only because it puts four mid-scale
> pedestals and four ladders onto two summing nodes, which is an analogue design
> problem — offset injection ×4, resistor matching, and `RFB` tracking across four
> parts — that this document has not done. **Revisit it before the analogue section
> is laid out**; §16 item 17.

**Hard panning is free.** ch0,3 → L and ch1,2 → R is a wire, not a register. §11.1
buys real panning for +2 ICs if you want it; the default must stay hard-panned or
mods sound wrong (§1, requirement 5).

### 6.3 The DAC: parallel, not serial — and this is a real decision

The obvious 1980s audio DACs are serial-input: `PCM56P` (Burr-Brown, 1986, 16-bit),
`TDA1541A` (Philips, 1986, dual 16-bit). They are better converters. **They are
the wrong converters for this architecture**, and the reason is worth stating
because it is the one place the design pushes back on the parts catalogue:

A serial audio DAC needs a **fixed frame rate** — you clock 16 bits into it every
`1/Fs`. That reintroduces the output sample rate §6.2 just eliminated. At the
`TDA1541A`'s practical ceiling (~192 kHz) a channel transition quantises to 5.2 µs
against a 31.9 µs sample period: **16 % jitter on individual sample boundaries.**
That is audible as a change in timbre on the high notes, and it is exactly the
artefact that separates a good mod player from a great one.

**Use a parallel multiplying DAC with an input latch: `LTC7545A`** — 12-bit,
on-chip data latch, current output, four-quadrant multiplying, ~1 µs settling with
a fast op-amp. Two of them, one per side.

> **Sourcing note — now verified against the datasheets in `reference/datasheets/`.**
> The period part here is the **`AD7545A` (Analog Devices, 1983)**, and the design is
> written against it. It is effectively out of production and now trades at **~\$50**.
> The **`LTC7545A` is the pin-compatible, current-production improvement on it at
> ~\$9**. "Pin-compatible" is exact: **all twenty pins match**, `OUT1`/`AGND`/`DGND`,
> `DB11`–`DB0` on 4–15, `CS` 16, `WR` 17, `VDD` 18, `VREF` 19, `RFB` 20. **Specify the
> `LTC7545A` and build with it**; the `AD7545A` stays in §17's period audit as the part
> the design would have used in 1989. This is the same posture
> [`graphics.md`](../../video/docs/graphics.md) §10.1 takes for `ATF22V10C` versus a
> classic `GAL22V10`: period-honest design, current-production BOM.
>
> **Specify the `L` or `C` grade** — ±0.5 LSB DNL *and* INL over the full temperature
> range. The `K`/`B` grade is ±1 LSB DNL, which is monotonic but gives back half the
> reason for choosing this part.

> ### ⚠ The plain `AD7545` is **not** a substitute, and the part numbers differ by one letter
>
> This is the trap, and it is worth a heading because the wrong part is the one you are
> more likely to be offered.
>
> §6.2 pulses the DAC's `WR` **once per colour-clock frame — every 281.9 ns**. Against
> that budget, at `VDD` = +5 V:
>
> | | `AD7545` | `AD7545A` | `LTC7545A` |
> |---|---|---|---|
> | `tWR` write pulse width, min | **250 ns** @25 °C, **400 ns** over temperature | 100 ns | **100 ns** |
> | Verdict against a 281.9 ns frame | **does not close** | closes | closes, 2.8× |
>
> The `AD7545A` cut `tWR` to 100 ns precisely so the part could talk to faster
> processors, and the `LTC7545A` keeps that. **The plain `AD7545` cannot be clocked fast
> enough for this card at 5 V.** Raising `VDD` to +15 V would fix the timing (`tWR` 160 /
> 240 ns) but demands `VIH` = **13.5 V**, i.e. level shifters on all fourteen digital
> inputs — not an option on a 5 V card. So: the design's named period part is correct,
> and the near-identical part number silently is not.

> ### The `LTC7545A`'s real advantage here is glitch, not linearity
>
> The argument above this note is about DNL and INL over temperature, and that argument
> is fine but it is not the one that matters for **audio**:
>
> | at `VDD` = +5 V | `AD7545` | `LTC7545A` |
> |---|---|---|
> | Digital-to-analog glitch impulse | 400 nV·s typ | **5 nV·s typ** |
> | Output current settling | 2 µs max (to ½ LSB) | **1 µs** (to 0.01 %) |
> | Propagation delay | 300 ns max | **150 ns** |
> | Multiplying feedthrough, 10 kHz | 5 mV p-p | 5 mV p-p |
>
> **80× less glitch energy per code transition.** §6.2 budgets for ~20 ns adder-settling
> glitches at up to 126,000 per second and argues the §7 filter plus "the DAC's own
> settling" absorb them. The converter's own code-transition glitch is the *other* half
> of that budget, arriving on the same event grid, and on the `AD7545` it is the larger
> half. The `LTC7545A` very nearly deletes it. Settling and propagation delay are
> comfortable on either part against the 7.9 µs worst-case event spacing.

> ### The on-chip latch is transparent, not edge-triggered
>
> A design note rather than a comparison, because both parts behave the same way and it
> is not what a `'574` does. Write mode is **`CS` *and* `WR` both low — the DAC follows
> the data bus**; hold is either one high, capturing whatever was present at that edge.
> So the accumulator must present stable data *across* the latching edge:
> **`tDS` = 100 ns setup, `tDH` = 5 ns hold** on the `LTC7545A`. Comfortable inside a
> 281.9 ns frame, but it is a requirement an edge-triggered `'574` would not have
> imposed, and it constrains when in the frame the adder is allowed to settle.

The latch replaces the output `'574`s, so the parallel part
is not even more packages:

| | Serial (`PCM56` / `TDA1541A`) | **Parallel (`LTC7545A`)** |
|---|---|---|
| Packages | 2 DAC + 4 `'165` shifters + clock divider ≈ 7 | **2** |
| Output sample rate | fixed, 192 kHz ceiling | **none — event-driven** |
| Boundary jitter at `PER`=113 | ±5.2 µs (16 %) | **0** |
| Resolution | 16 bit | 12 bit |
| Settling requirement | n/a | 1 µs vs 7.9 µs worst-case event spacing ✓ |

12 bits against a source that is 8 bits of sample × 6 bits of volume is not the
limiting factor; the jitter is. Take the parallel part.

#### The converter is coded unsigned; the accumulator is not — and the LUT reconciles them

**This is the one place the design had it flatly wrong, and it was fatal.** The
`AD7545` / `AD7545A` / `LTC7545A` transfer function is
`I_OUT1 = V_REF × D / 4096` for **unsigned** `D`. The parts have no signed mode; the
datasheet's own bipolar application circuit obtains four-quadrant operation by
**inverting the MSB**, which is to say by presenting **offset binary**. Fed the
accumulator's two's complement instead, every zero crossing is a full-scale output
jump — sample `−1` = `$FFF` sits at positive full scale and sample `0` = `$000` at
negative full scale — so a quiet sine leaves the card as a square wave at twice the
frequency.

> ⚠ **Superseded (design review, Aud-M1).** §6.2 and this section previously handed
> the accumulator's two's-complement value straight to the `LTC7545A`. The conversion
> below is not optional, and it is not free-standing arithmetic: it is a property of
> the table contents *and* of the width of the sum, and getting the second half wrong
> is as audible as omitting the first.

**The conversion costs nothing, because the LUT is content.** §6.1's volume table is
host-loaded, so it stores the scaled sample **already biased into 12-bit offset
binary**:

```
  entry = SAMP x min(VOL,64) / 4  +  2048        ; SAMP signed, entry 0..4095
  silence (VOL = 0)                          ->  $800
```

No GAL term, no MSB inverter, no extra package: the inversion the datasheet draws in
discrete logic is folded into the 32,768 bytes the loader writes at boot anyway. This
is the third time §6.1's "make it table content" move pays. **A channel that is not
enabled must present `$800`, not `$000`**, and the sequencer gets that for free by
forcing the LUT address to `VOL` = 0 for a channel with `DMAEN` = 0 — a single term,
and the one place where forgetting it would put a DC step on the output at every
`DMACON` change.

**The doubled offset is not an error to correct — it is exactly the bias the 13-bit
sum needs.** Adding two 12-bit offset-binary values gives

```
  (A + 2048) + (B + 2048)  =  (A + B) + 4096
```

and `4096 = 2^12` is precisely the bias of a **13-bit** offset-binary number. So the
13-bit accumulator output *is* the offset-binary encoding of `A + B`, with no
correction term anywhere. §6.2's `>>1` — wiring accumulator bits 12..1 to the DAC —
then lands on the 12-bit offset-binary encoding of the half-sum:

```
  floor( ((A + B) + 4096) / 2 )  =  floor((A + B)/2) + 2048
```

Both steps have to be right together. Subtract 2048 once "to fix the double offset"
and the output is biased by half full scale; take bits 11..0 instead of 12..1 and the
sum wraps at every loud passage. The arithmetic is three lines and it is written out
here because the alternative is discovering it on a bench with an oscilloscope.

#### The analogue side then owes a half-scale pedestal

Code `$800` is mid-scale ladder current, not zero, so the I/V output sits at half of
full scale when the card is silent. The datasheet's bipolar circuit removes that with
a **second amplifier per side** — I/V converter, then an offset subtractor referenced
through `RFB` and a matched resistor pair — and §7 allots **one** amplifier per side.
That circuit does not fit the budget as drawn, and the choice has to be made
explicitly rather than inherited from a figure.

**Decision: inject the offset as a current at the I/V summing node.** One resistor per
side from `V_REF` to the amplifier's virtual ground, sized for half of full-scale
ladder current — `R = 2 × R_FB`, i.e. ≈22 kΩ against the part's nominal 11 kΩ ladder,
a 0.1 % metal-film part. One amplifier per side, no second stage, and §7's op-amp
count goes *down* rather than up.

**What that costs, stated plainly.** The injected current flows through a discrete
resistor while the signal current flows through the on-chip R-2R ladder, so **the
offset does not track the ladder over temperature.** That tracking is exactly what
`RFB` exists for, and it is why the datasheet spends a second amplifier. A 25 ppm/°C
mismatch against the ladder's ~50 ppm/°C is ≈0.03 % of full scale over a 20 °C
excursion — about **1.2 LSB of DC wander** at the I/V output.

**It is inaudible, and for a structural reason rather than a lucky one:** §7's output
is DC-blocked, so the pedestal and every slow drift of it are removed by the output
capacitor before the line stage. What the drift actually costs is a little of the I/V
amplifier's headroom, not accuracy, and the *signal* gain still tracks through `RFB`
because the signal path is unchanged. If a future revision wants a DC-coupled output
— a subwoofer feed, a modular rack — the offset subtractor goes back in at **+1
`TL072`** and `RFB` does the tracking properly. Recorded so the trade is visible
rather than silently made.

The `V_REF` input remains a free master-volume/mute point, with the caveat that
`V_REF` now also sets the pedestal: pulling it to zero mutes cleanly, but *varying*
it moves signal and offset together, which is what you want, and moves the injected
offset only to the extent the resistor tracks — which is the same 0.03 % as above.

---

## 7. The filter chain — necessary, not nostalgic

It is easy to read the Amiga's low-pass as period colouration. It is not. **It is
the reconstruction filter for a zero-order hold running at the channel's rate**,
and mod samples routinely run at 8–16 kHz, where the images sit right on top of
the audio band. Remove it and low-rate instruments acquire a metallic ring that
is not in the source material.

Build both of the Amiga's filters, switchable, plus a bypass:

| Stage | Circuit | Cutoff | `ACTRL` |
|---|---|---|---|
| **Fixed** | 1-pole RC, 360 Ω + 0.1 µF, as an A500 | **≈4.4 kHz, 6 dB/oct** | always in, unless bypassed |
| **"LED"** | **one 2-pole Butterworth Sallen-Key stage**, in series with the fixed pole | **3275 Hz, 12 dB/oct** | `ACTRL.0` |
| **Bypass** | `74HC4066` shorting both | flat to the DAC's own ZOH | `ACTRL.1` |

- **Fixed only** is the A500 default and the right setting for the acceptance test.
- **+ LED** is what a lot of period material was mixed under, and some modules
  genuinely need it.
- **Bypass** exists for native software using the extended period range of §4.3,
  where 118 kHz channels put the images far above the audio band and the 4.4 kHz
  pole is pure loss. **Bypass is the wrong setting for mods** and the register bit
  should be documented that way.

> ⚠ **Superseded (design review, Aud-M4; decision D7).** This table previously
> specified the LED filter as **"5-pole Butterworth: two Sallen-Key stages + the
> fixed pole"** at ≈3.3 kHz. **The A500's LED filter is second-order.** The chain on
> a real A500 is a fixed 1-pole RC at ≈4.4 kHz — which the row above has right — plus
> a *switchable* **2nd-order** Butterworth Sallen-Key at ≈3.2–3.3 kHz, and every
> faithful model implements it that way: `pt2-clone` and libopenmpt's `a500` filter
> are both two-pole, and the 3275 Hz corner already used by this project's reference
> renderer *is* `pt2-clone`'s two-pole corner, transplanted under four poles it never
> had.
>
> **The error is two whole poles.** The old table's LED path was five poles end to end
> (two Sallen-Key stages plus the fixed one); the real one is three (one Sallen-Key
> stage plus the fixed one). That is **12 dB/octave of roll-off the A500 does not
> have**, and as asymptotes above the 3275 Hz corner:
>
> | Above cutoff | Correct (3-pole) | As specified (5-pole) | Error |
> |---|---|---|---|
> | 6.55 kHz — one octave | ≈18 dB down | ≈30 dB down | **12 dB too dark** |
> | 13.1 kHz — two octaves | ≈36 dB down | ≈60 dB down | **24 dB too dark** |
>
> LED-on material would have lost most of its top two octaves. That is not a subtlety;
> it is a direct violation of the "Paula-exact" acceptance test of §1, on the one path
> in the analogue chain that a module can switch at will with `E0x`
> ([`modplayer.md`](modplayer.md) §5.6).
>
> **Nothing caught it** because the A/B ladder has no probe that toggles `E0x`, so
> the filter was only ever compared in its fixed-pole state. See §16 item 18.

Parts: **2 × `TL072`** + **1 × `74HC4066`** + passives — **four amplifier channels,
not six**:

| Amplifier channels | Was | Now |
|---|---|---|
| I/V converter, one per side | 2 | 2 |
| Bipolar offset subtractor, one per side | (unbudgeted — §6.3) | **0**, offset injected at the summing node |
| LED Sallen-Key stages | 4 (two per side) | **2** (one per side) |
| **Total** | **6 = 3 × `TL072`** | **4 = 2 × `TL072`** |

Both corrections push the same way: the LED filter is one stage per side (Aud-M4) and
§6.3's bipolar offset is a current injected at the I/V summing node rather than a
second amplifier. **−1 `TL072`** against the old §10, which is the only line in this
document's re-tally that goes down.
An `NE5532` is the better op-amp and equally period; `TL072` is specified here for
supply-rail simplicity.

**Line output**, not a speaker amp: ~2 V p-p, **DC-blocked**, 100 Ω series. The
blocking capacitor is now load-bearing rather than good manners: it is what removes
§6.3's half-scale pedestal and its drift. Size it against the following load —
10 µF into 100 kΩ is 0.16 Hz, four decades below anything a module contains. Whatever
drives the machine's speakers is a separate concern and should not be on a card
carrying seven digital SRAMs.

---

## 8. Interrupts and the tempo timer

### 8.1 `/FIRQ`, and why

[`graphics.md`](../../video/docs/graphics.md) §17 puts both `/IRQ` and `/FIRQ` on the backplane
open-drain, and notes "the DOC wants one of its own". Take `/FIRQ`:

- The video card's VBL owns `/IRQ` and is NitrOS-9's system tick.
- A replayer tick is short, frequent, and register-light — **which is exactly what
  a 6809 `FIRQ` is for.** `FIRQ` stacks only `PC` and `CC`; the handler saves what
  it uses. On a 6309 in native mode that is the difference between ~12 cycles of
  entry overhead and ~21.
- It keeps audio timing independent of video timing, which matters because the
  video card's VBL is **70.09 Hz** (§graphics 6.2) and a mod tick is 50 Hz or a
  BPM-derived rate. Deriving one from the other is not possible cleanly.

Sources, OR-ed into one open-drain `/FIRQ`, each with an enable and a latched flag
in `AINTREQ`:

| Bit | Source |
|---|---|
| 0–3 | channel 0–3 buffer exhausted (Paula's `INTREQ` bits 7–10) |
| 4 | **tempo timer expired** |
| 5 | **sample-RAM posted-write overrun** — a write to `SDATA` arrived while the previous one had not retired, and the byte was lost. Sticky; write-1-to-clear like the rest of `AINTREQ` |

> ⚠ **Bit 5 restated (design review, Audio NOTE).** It used to read *"sample-RAM
> posted-write FIFO drained (for `TFM`-paced upload)"*, and that motivation does not
> survive its own document. §13.2 proves the depth-1 posted-write path retires at
> **3.55 M/s against `TFM`'s 700 k/s** — a 5× margin — so a *drain* interrupt can
> never fire, has no consumer, and could not pace anything if it did: `TFM` is a
> single interruptible instruction that resumes where it left off, not a loop that
> waits on a flag. What is actually worth an interrupt is the **failure** that margin
> is protecting against, because without `/WAIT` (§9.3) an overrun loses the byte
> **silently** and a silently corrupted sample upload is exactly §4.6's nightmare
> case one level down. So the bit is inverted in meaning: it is now a sticky error
> flag with a real consumer — the loader, which checks it once after each `TFM`
> burst. On a 2.098 MHz 6309 it can never set; on the §12.5 MCU card, or on any
> future host that can outrun 3.55 M/s, it can.

**`/FIRQ` needs an open-collector stage, and a GAL cannot provide one.** The
backplane's `/FIRQ` is a wire-OR
([`graphics.md`](../../video/docs/graphics.md) §17): every source pulls low and a single
pull-up defines the high level. A `GAL22V10`'s outputs are **totem-pole** — driving a
shared line from one is a bus fight with whatever else is asserting it, not a
wire-OR. The six sources above are OR-ed inside the interrupt GAL, and the resulting
single term is then buffered by **one `74HC07`** (hex open-drain buffer, `V_OL` ≤
0.33 V at 4 mA, tolerant of the line being held low by another card) before it
reaches the backplane. **+1 IC**, decision D9, and it is the kind of omission that is
invisible on paper and immediate on a bench.

### 8.2 The tempo timer is CIA-B, and it costs nothing

ProTracker's `Fxx` command sets ticks-per-row for `xx` ≤ `$1F` and **BPM** for
`xx` ≥ `$20`. On an Amiga the BPM case reprograms **CIA-B timer A**, clocked at
the E-clock — 1/10 of the CPU clock, which is itself twice the colour clock:

```
  CIA clock = colourclock x 2 / 10 = colourclock / 5 = 709,379 Hz   (PAL)
                                                    = 715,909 Hz   (NTSC)
```

The replayer's reload is `N = 1773447 / BPM` on PAL (`1789773 / BPM` on NTSC),
because the tick rate wanted is `BPM x 2/5` Hz and `1773447 = colourclock / 2`
is the numerator that falls out of `N = f_cia x 2.5 / BPM`. **The constant in the
replayer source is colourclock/2; the clock the counter runs at is
colourclock/5.** Those are different numbers and confusing them detunes the tempo
by exactly 2.5×.

So: **clock the timer at colourclock ÷ 5 = 709,379 Hz — the Amiga's CIA clock,
not an approximation of it — and the `Fxx` arithmetic in every existing replayer
transfers unchanged.** No rescaling, no divide, no table. The ÷5 is the same on
both standards, so the NTSC oscillator option of §4.1 carries the tempo reference
with it for free.

| BPM | `N = 1773447 / BPM` | Tick rate at 709,379 Hz | Wanted (`BPM × 2/5`) |
|---|---|---|---|
| 32 (slowest useful) | 55,420 | 12.800 Hz | 12.80 |
| **125 (the default)** | **14,187** | **50.002 Hz** | **50.00** |
| 255 (fastest) | 6,954 | 102.010 Hz | 102.00 |

16 bits reaches down to BPM 28, below anything a module uses.

Implementation: it is a fifth entry in the compare structure of §4.2, serviced in
**slot 4**. The nuance is that it counts at 1/5 the colour clock, so it cannot
share the free-running counter — instead the timer's *own* 16-bit count lives
beside its `NEXT` in one 32-bit state word, `{CIACNT[15:0], CIANEXT[15:0]}`, and
the shared adder increments it in a deferred slot every 5 colour clocks. That is
709,379 increments/s against 7.1 M deferred slots/s — **10 % of the deferred
budget, and zero additional packages.** The ÷5 prescale is three macrocells in the
sequencer GAL.

Expose it as a plain 16-bit reload register (`TIMER`, §9.2) with an enable bit, so
it is equally usable as a general-purpose periodic interrupt for anything else
the machine wants at a rate `/IRQ`'s 70.09 Hz cannot give it.

**The enable bit is `ACTRL` b6** (decision D7). It was promised here and never
allocated in §9.2, which left the map with a timer that could be started and never
stopped: once `TIMER` holds a non-zero reload the compare in slot 4 fires forever,
`AINTENA` b4 can mask the interrupt but not the timer, and there is no clean "stop
the music" path at all — not for a replayer shutting down, not for `ACTRL` b7's
master enable, and not for a NitrOS-9 process being killed. `ACTRL` b6 = 0 holds the
timer's count in reset and inhibits the slot-4 compare; b6 = 1 loads `TIMER` and
runs. Writing `TIMER` while b6 = 0 is the ordinary way to arm it, and the
double-buffered commit of §9.4 means the two-byte write is atomic either way.

**The reload is one count short of a real 8520, and the claim is "CIA-B-identical",
so it has to be stated.** A real 8520 in continuous mode counts down to zero and
reloads on the *following* cycle, so the period is **latch + 1** counts; this card's
compare structure (§4.2) gives period = **latch** exactly. At the default `N` = 14,187:

| | Counts per period | Tick rate at 709,379 Hz |
|---|---|---|
| **This card** | 14,187 | **50.00204 Hz** |
| Real CIA-B timer A | 14,188 | 49.99852 Hz |
| Difference | 1 count | **0.0070 %** |

That is 42 ms of drift over a ten-minute module played alongside an Amiga — below
anything a listener can hear and far below the tolerance of the `Fxx` mapping itself
(BPM 125 wants 50.000 Hz; both numbers are nearer than the BPM quantisation).
**It changes nothing musically and it is not left implicit**, because "CIA-B-identical"
is the load-bearing claim of §1 requirement 9 and a reader porting a replayer is
entitled to know which of the two arithmetics the card implements. Adding the +1 is a
single term in the sequencer GAL if exactness is preferred to the simpler compare;
**decide it with the GAL fit, §16 item 20**, and note that existing replayer constants
transfer unchanged either way because the reload value is the same number.

---

## 9. Register map

### 9.1 Placement

[`graphics.md`](../../video/docs/graphics.md) §13 takes **`$FF60–$FF7F`** (32 bytes) for video, on
the argument that it is spare on a real CoCo 3. The next spare region under the
same argument is **`$FF40–$FF5F`** (cartridge/disk on a CoCo 3, and this machine
has neither at that address).

**Propose `$FF40–$FF4F` — 16 bytes — for audio**, leaving `$FF50–$FF5F` free for a
disk controller. Sixteen bytes is enough because the per-channel state goes
through an index/data window rather than being mapped flat (§9.2).

Decode is geographic, from the backplane's per-slot `/IOSEL`
([`graphics.md`](../../video/docs/graphics.md) §17), so the base is a jumper, not a wire.

### 9.2 The direct window — 16 bytes

| Off | Name | R/W | Function |
|---|---|---|---|
| `+$0` | `AIDX` | W | state-file index; writing it **prefetches** that entry (§9.3) |
| `+$1` | `ADATA` | R/W | state-file byte at `AIDX`, **post-increment** |
| `+$2` | `ADMACON` | W | b3..0 channel DMA enable. **b7 = set/clear**, Paula's `DMACON` convention |
| `+$3` | `AINTENA` | W | b5..0 interrupt enables (§8.1). Same b7 set/clear convention |
| `+$4` | `AINTREQ` | R/W | read: pending flags. write: **b7 = 0 clears** the bits set in b5..0; **b7 = 1 sets** them, Paula's `INTREQ` convention |
| `+$5` | `ACTRL` | W | b0 LED filter, b1 filter bypass, b2 NTSC clock, b3 reserved (was the volume curve — now table content, §6.1), **b4 8-channel mode** (§11.2), b5 pan enable (§11.1), **b6 tempo-timer enable** (§8.2), b7 master enable |
| `+$6`–`$8` | `SPTR` | W | sample-RAM pointer, 19 bits, auto-increment |
| `+$9` | `SDATA` | R/W | sample-RAM byte at `SPTR`, **post-increment** — a **side-effecting port**, see the `TFM` note below |
| `+$A` | `ASTAT` | R | b3..0 channel DMA active, b4 timer running, b5 reserved (reads 0), **b6 posted-write busy**, **b7 prefetch valid** — b6/b7 defined below |
| `+$B`–`+$C` | `TIMER` | W | tempo-timer reload, 16 bits, clocked at **709,379 Hz** — load `1773447 / BPM` (§8.2) |
| `+$D`–`+$E` | `LIDX` | W | volume-LUT load index, 16 bits, auto-increment (§6.1) |
| `+$F` | `LDATA` | R/W | volume-LUT byte at `LIDX`, **post-increment** |

`ADMACON` / `AINTENA` / `AINTREQ` keep **Paula's set/clear bit-7 convention**
deliberately: a replayer ported from 68000 writes the same constants, and the
one-line translation from `$DFF096` to `$FF42` is the whole port for that
register. **`AINTREQ`'s set form is part of that convention and is normative**, not
an accident of one implementation: writing `$80 | mask` raises the selected request
bits exactly as a 68000 write to `$DFF09C` does. It is the only way to test the
`/FIRQ` path and the `AINTENA` mask without waiting for a real buffer exhaust, it is
what the §12.5 MCU card's self-test uses, and a frozen map with an undocumented write
behaviour in it is not frozen. Software that is not testing the interrupt path should
never issue it.

> ⚠ **`SDATA` and `ADATA` are ports whose access has a side effect, and §13.2 streams
> `TFM` into one of them.** The post-increment is what makes `TFM X+,Y` the right
> instruction (§13.2) and it is also what makes the transfer sensitive to the 6309's
> unsettled `TFM` interrupt/resume behaviour: a resumed `TFM` that re-executes its
> **destination write** stores one byte twice, advances `SPTR` one step too far, and
> shifts every remaining byte of the upload by one address —
> **silent sample corruption, intermittent, dependent on where an interrupt lands.**
> This is the same exposure [`sdcard.md`](../../storage/docs/sdcard.md) §4 analyses for
> its own data port, and question **(b)** of that document's §12 step 1 silicon capture
> answers it for both cards at once. The mitigation is the storage card's — chunk the
> `TFM`, mask across each chunk — costed for this card in
> [`modplayer.md`](modplayer.md) §4.4, where it is nearly free because the upload is on
> no latency-critical path. [`sdcard.md`](../../storage/docs/sdcard.md) §11.6 records a
> third option that would delete the hazard for both cards by specifying `TFM`'s resume
> behaviour in the CPU firmware; **that is a machine-level decision, not this card's.**

**The three bits the map freeze has to settle, settled.**

| Bit | Definition | Why this and not something else |
|---|---|---|
| `ACTRL` b4 | **8-channel mode** (§11.2) | **b4, unambiguously.** The reference header defined it at b3; b3 is the *reserved* bit vacated when the volume curve became table content (§6.1), and reusing a vacated bit for a new mode is how a map acquires two meanings for one position. Decision D7 fixes b4 and `card.h` follows the document, not the other way round — §9.2 is the deliverable. |
| `ASTAT` b6 | **posted-write busy** — 1 while the depth-1 sample-RAM posted write of §5 has not yet retired in slot 5. A further `SDATA` write while b6 = 1 is lost and sets `AINTREQ` b5 (§8.1). | It was a placeholder called "write FIFO full", which named a FIFO the card does not have. The path is depth 1, so "busy" is the honest word. It can only ever read 1 to a host faster than 3.55 M/s: a 6309 store takes ~5 E cycles = 2.38 µs, and the retire takes 281.9 ns, so on this machine b6 reads 0 every time it is polled. It exists for the MCU card and for bring-up. |
| `ASTAT` b7 | **prefetch valid** — 1 when the `ADATA`/`SDATA` prefetch latch (§9.3) holds the byte for the *current* index. Cleared by a write to `AIDX`/`SPTR` and by the post-increment; set when slot 5 retires the prefetch. | Also a placeholder. Same arithmetic as b6 from the other side: the prefetch completes within one colour clock (281.9 ns) and the soonest a 6309 can look is 2.38 µs later, so **b7 reads 1 every time this machine polls it** and §9.3's "reads never stall" holds. It is not a handshake the 6309 has to honour; it is the observability that makes that claim checkable on a logic analyser, and it is a real handshake for any host fast enough to need one. |

### 9.3 The state file — index/data, and why that is not a cost

Per channel, `AIDX` = `channel × 16 + offset`:

| Offset | Name | Bytes | Paula equivalent | Note |
|---|---|---|---|---|
| 0–2 | `LC` | 3 | `AUDxLC` | **byte** address into card RAM |
| 3–4 | `LEN` | 2 | `AUDxLEN` | **words**, Paula-identical — mod length fields load unchanged |
| 5–6 | `PER` | 2 | `AUDxPER` | colour clocks |
| 7 | `VOL` | 1 | `AUDxVOL` | 0–64 |
| 8 | `DAT` | 1 | `AUDxDAT` | direct sample write, CPU-fed mode (§1 req. 8) |
| 9 | `ATT` | 1 | `ADKCON` bits | b0 attach-period, b1 attach-volume (§11.3). **Channel 3's bits are ignored** — there is no channel 4 and no wrap to channel 0 |
| 10 | `PAN` | 1 | — | §11.1, ignored unless `ACTRL.5` |
| 11–15 | `PTR`/`CNT` | 5 | — | **read-only**, current pointer and remaining count |

> **The `LC` / `LEN` asymmetry is deliberate and must be frozen early.** `LEN` stays
> in words so `.mod` header fields copy straight in; `LC` becomes a byte address
> because the card's RAM is byte-wide and a word pointer would forbid odd sample
> starts (which the `9xx` sample-offset command produces). The loader does one
> shift; the replayer does none. **Open item — §16 item 5.**

**Does index/data cost the replayer anything?** A typical non-zero tick writes
`PER` and `VOL` for four channels: 12 bytes flat, 24 bytes through index/data
(the auto-increment means one `AIDX` write covers `PER`+`VOL` in a run). At ~5
core cycles per store that is **60 cycles vs ~120 cycles, out of a ~1,200-cycle
tick** — under 5 % of the replayer, against saving 16 bytes of a scarce I/O page
and getting a uniform read-back path. Take the window.

**Reads never stall.** Writing `AIDX` triggers a state-file read into a latch in
slot 5; `ADATA` reads the latch; the post-increment triggers the next prefetch.
This is exactly [`graphics.md`](../../video/docs/graphics.md) §11's `VDATA` prefetch argument, and
it means the card needs **no `/WAIT` path at all** — the only card in the machine
that does not.

**That latch is a package, and it was not in the budget.** The prefetch holds one byte
of state-file or sample-RAM data for the host to read at its leisure: **1 × `74HC574`**
(§10). The `'574` the old §10 *did* list is the posted-write **data** latch on the
opposite path, host → sample RAM; they are two different registers on two different
buses and the argument for the read one was made without ever costing it (Aud-M5).
The `74HC245` read-back buffer is also not a substitute — it is a transceiver, not
storage, and something has to hold the byte across the 2.38 µs between the prefetch
and the host's read.

### 9.4 Crossing the host boundary — the part §0 said did not exist

> ⚠ **Superseded (design review, Aud-M3).** §0 claimed **"one oscillator, one clock
> domain."** The first half is true and the second half is true of everything
> downstream of the crystal — and false exactly where it matters. **Host writes arrive
> a byte at a time from an asynchronous 2.098 MHz E bus**, and Paula's registers do
> not: a 68000 writes `AUD0PER` in one bus cycle, atomically, which is why no Amiga
> document has this section and why this one did not either. §0 now reads "one
> internal clock domain, asynchronous host port", and the rest of this section is the
> content that claim was standing in for.

**The scale of the problem, in colour clocks.** A 6309 store to an I/O address takes
~5 core cycles at 2.0979 MHz = **2.383 µs**, and a colour clock is 281.9 ns, so
consecutive bytes of a multi-byte register arrive **≈8.45 colour clocks apart**. The
card runs 8 slots per colour clock and services every channel every colour clock, so
between two bytes of one host register write the sequencer has walked all four
channels **eight times**. Anything that is half-written is live, and live for a long
time by this card's standards.

#### 9.4.1 A torn `PER` is an out-of-range period, not a rounding error

`PER` is two bytes at state-file offsets 5–6. Consider the commonest write in a
module — a note change from C-2 to B-3, `PER` 353 → 113:

```
  live value   $0161 = 353
  high byte    $01 -> $00     ; now live: $0061 =  97   <-- for ~8.45 colour clocks
  low  byte    $61 -> $71     ; now live: $0071 = 113
```

**97 is below Paula's ~114 DMA floor and below anything ProTracker can emit.** It is
inside this card's extended range (§4.3), so nothing clamps it. A channel whose
compare fires inside that ~8-colour-clock window schedules its next tick as
`NEXT + 97` instead of `NEXT + 113`: that sample plays **16 % short**, 3.6× shorter
than the note that was actually sounding. One sample at the wrong length is a click.
On a sustained lead under vibrato — where `PER` is rewritten on **every tick** — it is
a click 50 times a second on that channel.

**The general bound is worse than the example.** A torn two-byte field takes the
high byte of one value and the low byte of the other, so the transient period is
`(new & $FF00) | (old & $00FF)`, which for a large interval can land anywhere in the
16-bit range regardless of how close the two endpoints are. The direction depends only
on byte order and the magnitude only on which nibble changed; neither is controllable
from software, and neither is visible in a register trace, which records the two
stores and not the value that was live between them.

#### 9.4.2 The 5-byte loop shadow is the one that fetches arbitrary RAM

§3.3's one-shot→loop idiom is requirement #3 of §1, and it is written as five
consecutive stores through `AIDX`/`ADATA`: `LC` (3 bytes) then `LEN` (2). That is
**~40 colour clocks, 11.3 µs, of exposure per channel per note** during which `LC` and
`LEN` are a mixture of the old buffer's values and the new one's.

The sequencer copies `LC → PTR` and `LEN×2 → CNT` **at the instant `CNT` reaches
zero** — that instant is not synchronised to anything the host is doing. If the first
(one-shot) pass exhausts inside those 11.3 µs, the channel reloads a **torn pointer**:
one byte of the new repeat address and two of the old, which on a 19-bit pointer is a
jump of up to 64 KB into whatever else is in card RAM, played at the note's rate until
the torn `CNT` runs out. Audibly: a burst of another instrument, or of unwritten SRAM.

**How often:** ProTracker writes the shadow on tick 1, 20 ms after the trigger, so the
window is 11.3 µs out of 20 ms — **0.06 % of note triggers** land in it. At four
channels and 125 BPM that is on the order of **once a minute** of ordinary music, with
nothing in the trace to distinguish the bad note from the 3,000 good ones. It is
exactly the bug class §16 item 13 already kills for the `DMACON`-enable path, left
alive on the path that runs 50 times as often.

#### 9.4.3 The rule: multi-byte host fields are double-buffered and commit on the low byte

**Normative.** Every host-written multi-byte field is staged and lands in the state
file in **one deferred-slot write**, on the arrival of its **last (low) byte**:

| Field | Bytes | Offsets | Commits on |
|---|---|---|---|
| `LC` | 3 | 0,1,2 (big-endian, `LC[18:16]` first) | offset 2 |
| `LEN` | 2 | 3,4 | offset 4 |
| `PER` | 2 | 5,6 | offset 6 |
| `TIMER` | 2 | `+$B`,`+$C` | `+$C` |

Nothing else needs it: `VOL`, `DAT`, `ATT` and `PAN` are one byte each and are
therefore atomic already, and `SPTR`/`LIDX` are pointers into a linear write stream
where a torn value can only mis-place the *next* byte, not a live playing pointer —
they commit on their own low byte anyway because they are counters (§9.5) and the
load is one operation.

**The natural write order already satisfies this**, which is what makes the rule
cheap. `ADATA` post-increments, so a replayer writing `LC` then `LEN` then `PER`
issues offsets 0,1,2,3,4,5,6 in ascending order, and each field's low byte is its last
— the same big-endian order the `.mod` format and the 6309 both use. **The card does
not need the host's cooperation to be safe, but it gets a free ride from it.**

**The model already does exactly this for `TIMER`**, and for exactly this reason:
tearing broke the tempo when the reference player wrote the two bytes separately, so
`TIMER` was given commit-on-low-byte semantics. The finding here is that `PER`, `LC`
and `LEN` needed the same rule and never got it — the fix is to generalise a rule the
design had already discovered once.

**Cost: 2 × `74HC574` of staging** (§10). The widest field is `LC` at 3 bytes, of which
2 are staged and the third is the committing byte, arriving on the existing posted-write
data path; 16 bits of staging covers every field in the table.

#### 9.4.4 The synchroniser, which is the only defence the card has

§9.3's "no `/WAIT` path at all" is a real property and it has a consequence: **the card
cannot ask the host to wait while it makes up its mind.** Every host access must be
captured on the first attempt, which makes the metastability margin of the input
synchroniser the whole of the boundary discipline.

`/IOSEL`, `E` and `R/W` are asynchronous to the 28.37516 MHz slot clock. They are
qualified into a single access strobe and passed through a **two-flop synchroniser with
a full slot between the stages**:

```
  async strobe --> FF1 (slot clock) --> FF2 (slot clock) --> sequencer, slot 5
                   ^ resolution window = 1 slot = 35.24 ns
```

The arithmetic that decides the stage count, at `74HC`'s ~2 ns metastability time
constant and a worst-case 400 k accesses/s:

| Resolution window | `exp(t/τ)` | MTBF |
|---|---|---|
| ½ slot (17.6 ns) | 6.6 × 10³ | **~10 minutes — unusable** |
| 1 slot (35.2 ns) | 4.4 × 10⁷ | ~40 days |
| **2 slots (70.5 ns)** | **1.9 × 10¹⁵** | **~10¹¹ years** |

**Specify two slots** — one flop clocked at the slot rate, a second a slot later, the
access retired in slot 5 of the following colour clock. The latency is ≤2 colour
clocks (564 ns) against a host that cannot return for 2.38 µs, so it is free.
**1 × `74HC174`** (hex D flip-flop) carries three such synchronisers — write strobe,
read strobe, and `E` itself for edge detection — with none spare.

#### 9.4.5 Reads of registers the slot logic is writing

Two registers change underneath the host: `AINTREQ` (slot logic sets request bits) and
`ADATA` (slot 5 refills the prefetch latch).

- **`AINTREQ`.** A set event arriving during a host read must neither be lost nor
  produce a half-updated byte. Request bits are set into a 6-bit **pending** register by
  the slot logic and merged into `AINTREQ` on the colour clock *after* the synchronised
  read strobe deasserts; a write-to-clear in the same window clears only the bits the
  host named, and any set that arrived meanwhile survives the clear. This is Paula's
  behaviour and it is the only ordering under which "read `AINTREQ`, then clear what you
  saw" is race-free.
- **`ADATA`.** The prefetch latch is written only in slot 5 and read only through the
  `'245`; the state file itself is written only in deferred slots. The host therefore
  reads a byte-atomic snapshot, and `ASTAT` b7 says whether it is the snapshot for the
  current index (§9.2). Multi-byte *reads* — `PTR`/`CNT` at offsets 11–15 — are **not**
  atomic across bytes and are documented as advisory: they are a debugging window, and a
  host that needs a coherent pointer should stop the channel first.

### 9.5 Where every host-visible counter bit lives

> ⚠ **Added (design review, Aud-M5).** The old §10 tallied 35 packages with **three**
> `GAL22V10` = 30 macrocells total, and asked those 30 macrocells to hold the entire
> slot sequencer *and* 41 flops of host-visible counter. They do not fit, and the
> document never said where they were. This section says.

| State | Bits | Lives in | Packages |
|---|---|---|---|
| `SPTR` — sample-RAM pointer, 19-bit auto-increment | 19 | `74HC593` ×3 (8-bit binary counter with input register, 3-state) | **3** |
| `LIDX` — volume-LUT load index, 16-bit auto-increment | 16 | `74HC593` ×2 | **2** |
| `AIDX` — state-file index, 6-bit auto-increment | 6 | `74HC593` ×1 | **1** |
| `INTENA` | 6 | GAL 4 | — |
| `INTREQ` (+ 6-bit pending register, §9.4.5) | 12 | GAL 5 | — |
| `DMAEN` | 4 | GAL 3 | — |
| Tempo ÷5 prescale + timer enable | 4 | GAL 3 | — |
| Slot counter | 3 | GAL 1 | — |
| Deferred-work queue + enable-priority term (§16 item 13) | ~6 | GAL 1 / GAL 5 | — |
| Sequencer state machine, stage control | ~8 | GAL 1 | — |
| Address mux, decode, host synchroniser control | — | GAL 2 | — |
| | | **`GAL22V10` ×5** | **5** |

**Why `'593` and not `'161`.** A `74HC161` is 4 bits, so `SPTR` alone would be five
packages and the three counters together **ten**. The `74HC593` is an 8-bit binary
counter with a parallel input register and three-state outputs — host-loadable in the
two-step way a byte-at-a-time port wants anyway, and directly capable of driving the
sample-RAM and LUT address buses. **41 counter bits in 6 packages instead of 11.**

**Why five GALs and not three.** `INTENA`(6) + `INTREQ`(12) + `DMAEN`(4) = 22
registered bits with feedback, before a single term of sequencer. A `GAL22V10` has ten
macrocells. Three of them cannot hold the interrupt block, let alone the block *and*
the slot walk *and* the deferred queue. Five is 50 macrocells and the table above uses
essentially all of them — **which is a fit that has to be proven, not asserted**
(§16 item 7, now the sharper question). The video card runs 8 GALs and argues 18 is
where "why not a CPLD" bites, so five is comfortably inside the house rule; the risk
is not the count, it is that the sequencer GAL is doing the most interesting work on
the card with no spare macrocells.

---

## 10. Chip budget

| Qty | Part | Role |
|---|---|---|
| 1 | AS6C1008-55 (128K×8) | sample RAM (footprint for 4 → 512 KB, §5) |
| 4 | CY7C128A-15 (2K×8, 15 ns) | channel state file, **32 bits wide** (§3.1) |
| 2 | 32K×8, 15 ns | volume LUT, `{VOL[6:0],SAMP[7:0]}` → 12-bit **offset binary** (§6.1, §6.3) |
| 2 | 74HC590 | free-running 16-bit colour-clock counter (§4.2) |
| 2 | 74HC688 | 16-bit event comparator (§4.2) |
| 4 | 74HC283 | shared 16-bit adder — `NEXT`+`PER`, `PTR`+1, `CNT`−1 (slots 6–7) |
| **6** | **74HC283** | **L and R sum adders, 12 bits each (§6.2)** |
| 3 | 74HC574 | pipeline latches, stages A/B/C (§3.2) |
| **4** | **74HC574** | **`L_HOLD` / `R_HOLD`, 12 bits each — hold the scaled sample across the two-slot add (§6.2)** |
| 4 | 74HC273 | `L_ACC` / `R_ACC`, 13 bits each — **`'273`, not `'574`: the frame boundary needs an asynchronous clear** (§6.2) |
| 2 | **LTC7545A** | 12-bit parallel MDAC with input latch, L and R (§6.3) |
| **2** | **TL072** | **I/V ×2 + one LED Sallen-Key per side (§7) — down one, see below** |
| 1 | 74HC4066 | filter select / bypass (§7) |
| 1 | 74HC574 | posted-write data latch (host → sample RAM) |
| **2** | **74HC574** | **multi-byte commit staging — `LC`/`LEN`/`PER`/`TIMER` (§9.4.3)** |
| **1** | **74HC574** | **`ADATA`/`SDATA` read-prefetch latch (§9.3)** |
| **6** | **74HC593** | **`SPTR` ×3, `LIDX` ×2, `AIDX` ×1 — the host-visible counters (§9.5)** |
| **1** | **74HC174** | **two-flop host-port synchronisers ×3 (§9.4.4)** |
| 1 | 74HC245 | register / state-file read-back |
| 1 | 74HC273 | `ACTRL`, master reset |
| **1** | **74HC07** | **open-drain buffer for the wire-OR `/FIRQ` (§8.1, decision D9)** |
| **5** | **GAL22V10-15** | **sequencer/queue; address mux + decode; `DMACON`/timer; `INTENA`; `INTREQ`+pending (§9.5)** |
| 1 | 28.37516 MHz osc | PAL Amiga master (§4.1) |
| (1) | (28.63636 MHz osc) | (NTSC, socketed option, §4.1) |
| — | R-2R / passives | filter networks, offset-injection resistors (§6.3), output stage |
| **57** | | **(58 with the NTSC can)** |

Video card, for comparison: **36** (32 if the tri-state pixel bus closes). **This card
is no longer the small one**, and the honest statement of that is the point of the
table below.

> ⚠ **The old total of 35 is superseded (design review — Aud-M1, Aud-M2, Aud-M3,
> Aud-M4, Aud-M5, decision D9).** The addition was never wrong: the list summed to 35
> exactly as printed. What was wrong is what the list left out, and it left out
> whole functions rather than spare gates.

| Where the 22 packages came from | Δ | § |
|---|---|---|
| The L/R sum path — 4 hold latches + 6 adders. The old list had four `'574` labelled "accumulators" and no adder at all, while §6.2 claimed a combinational sum and §3.4 claimed the only adder was elsewhere. | **+10** | §6.2 |
| Host-visible counters. `SPTR`(19) + `LIDX`(16) + `AIDX`(6) = **41 flops of counter** with nowhere to live; three GALs are 30 macrocells and were already holding the sequencer. | **+6** | §9.5 |
| Host-boundary hardware: 2 staging latches for the commit-on-low-byte rule, 1 hex flip-flop for the two-flop synchronisers. | **+3** | §9.4 |
| `ADATA` read-prefetch latch — argued for in §9.3, never costed; the `'574` that *was* listed is the posted-**write** latch on the other path. | **+1** | §9.3 |
| `74HC07` open-collector stage for the wire-OR `/FIRQ`; a `GAL22V10` output is totem-pole and cannot do it. | **+1** | §8.1 |
| Two more `GAL22V10`. | **+2** | §9.5 |
| One fewer `TL072`: the LED filter is one Sallen-Key stage per side, not two, and §6.3's bipolar offset is injected rather than subtracted. | **−1** | §7 |
| **Net** | **+22 → 57** | |

**Where it could shrink:**
- **−12** if §6.2's recorded alternative is taken: four `LTC7545A` summing as currents
  at the two I/V nodes, deleting both hold latches, both adders and both accumulators
  for +2 DACs. It is cheaper *and* more Paula-exact; it is not adopted only because
  the analogue design has not been done (§16 item 17).
- **−1** if the volume LUT's 12-bit output is cut to 8 (do not — §6.1).
- **−2** if the state file is 16 bits wide instead of 32, at the price of two
  accesses per slot and a 17.5 ns SRAM. Not available in 1989.

**Where it will grow:**
- **+3** for 512 KB of sample RAM.
- **+2** for per-channel panning (§11.1).
- **+1** if the §3.2 stage-B path does not close and needs the extra latch.
- **+1 `TL072`** if a DC-coupled output is ever wanted and §6.3's injected offset has
  to become a proper `RFB`-referenced subtractor.

**Power.** Seven SRAMs, five GALs, ~30 HC packages, four op-amp channels: estimate
**400–500 mA**. The old figure of 250–350 mA and its "roughly half the video card"
gloss went with the old package count; this card is now **comparable to** the video
card rather than half of it, even though nothing on it switches at 25 MHz. Analogue
and digital grounds must meet at exactly one point, and the `LTC7545A` reference
should not share a rail with the SRAMs. That is the only layout constraint on this
card that the video card does not also have, and it is the one that decides whether it
sounds clean.

**Area, and this is now an open question rather than a reassurance.** 57 packages —
one DIP-32, four DIP-24, two DIP-28, six DIP-16 counters, five DIP-24 GALs — **does
not obviously fit the video card's single-Eurocard envelope while keeping the analogue
section physically separate**, which §16 item 9 says is non-negotiable for the noise
floor. The old text asserted the fit at 35 and that assertion does not carry to 57.
Either the card goes double-height, or the analogue section becomes a small mezzanine,
or §6.2's four-DAC alternative buys back twelve packages and the question goes away.
**Decide before layout — §16 item 19.**

---

## 11. What this card does that Paula cannot

Presented as opt-in, because **the default configuration must be Paula-exact** or
the acceptance test in §1 is meaningless. Each of these is a register bit that
software has to ask for.

### 11.1 Per-channel panning — +2 ICs

Widen the volume LUT to **four** 32K×8 parts and hold *two* 12-bit outputs per
entry: `{curve, VOL, SAMP} → (L gain, R gain)`, with the pan applied inside the
table. Slots 0–3 then accumulate into both sides in the same pass — **no extra
slots, no extra adder, no change to the pipeline.** The `PAN` byte (§9.3) selects
one of a small set of precomputed pan tables via the curve bits.

That is a genuinely cheap way to get something Paula never had, and it costs
nothing when disabled (`ACTRL.5` = 0 selects the hard-panned table pair).

### 11.2 Eight channels — a slot-allocation question, not a hardware one

The state file has room; the slot walk does not. Eight channels at full period
resolution needs 8 slots for channels alone plus timer and host — 12 slots per
colour clock at **42.6 MHz**, which is not a 1989 SRAM.

The asymmetric answer fits inside the existing 8-slot frame:

```
  colour clock even : slots 0-3 = ch 0-3,  slots 6-7 = ch 4,5
  colour clock odd  : slots 0-3 = ch 0-3,  slots 6-7 = ch 6,7
```

**Channels 0–3 keep full Paula period resolution; channels 4–7 tick on a
2-colour-clock grid** (half the pitch resolution — ~0.9 % worst case at the top
note, ~15 cents). That is the right asymmetry: 4-channel modules — the acceptance
test — are exact, and 8-channel OctaMED/FastTracker material, which is rarer and
was never Paula-exact anyway (the Amiga plays it by software-mixing pairs into
Paula's four channels, at *worse* fidelity than this), gets a mode bit and the
deferred slots.

**Cost: sequencer terms only, +0 ICs.** But it takes slots 6–7 away from deferred
pointer work, so the §3.1 margin drops from 56× to ~2×. **Fit and verify before
promising it (§16 item 7).**

### 11.3 Paula's own extras, for free

- **Attach modulation** (`ADKCON`'s period/volume attach: channel *n* modulates
  *n+1*). Rarely used, but some modules and several demos need it, and it is a
  couple of sequencer terms plus the `ATT` byte already reserved in §9.3. **Build it.**
  **Channel 3 modulates nothing.** On Paula the attach chain is 0→1, 1→2, 2→3 and
  stops: `AUD3DAT` has no consumer, so setting channel 3's attach bits does nothing at
  all. **This card does the same, explicitly: no wrap to channel 0.** It is stated here
  because a wrap is the natural thing to write when the channel index is three bits of
  a slot counter and `+1` costs nothing — and because a card and a model that disagree
  about a rarely-exercised corner is exactly how a divergence survives to a GAL. The
  sequencer term is `attach_target_valid = (ch != 3)`.
- **Extended period range** (§4.3) — already free.
- **Programmable volume curve** (§6.1) — already free.

### 11.4 What is *not* worth building

- **16-bit samples.** The LUT is addressed by an 8-bit sample; 16-bit needs a real
  multiplier and a wider path throughout. It also has nothing to do with mods.
- **Hardware interpolation.** §1: it makes mods sound *wrong*.
- **A synthesis engine** (FM, wavetable envelopes, ADSR). The card is a sample
  player; envelopes belong in the replayer, where every tracker already puts them.
- **A sampler input.** Tempting and period-honest (the Amiga's sound digitisers
  were ubiquitous) but it is a separate card: an ADC, an anti-alias filter, and a
  clean analogue front end do not want to share a board with four DACs.

---

## 12. The four alternatives, and why each is rejected

### 12.1 A real MOS 8364 Paula — rejected

The obvious move, and it does not work.

- **Paula does not do its own DMA.** In an Amiga, *Agnus* fetches audio words and
  hands them to Paula via `AUDxDAT`; Paula only raises DMA requests. A bare Paula
  needs an Agnus, or an Agnus substitute — **which is most of this card anyway**,
  minus the parts that are cheap.
- **CPU-fed mode is out of reach.** Feeding `AUDxDAT` in software is 4 × 28.6 kHz ×
  2 bytes = **229 KB/s**, roughly 8× what a 2.098 MHz 6309 can sustain.
- **16-bit bus, 28 MHz clocking, 48-pin DIP**, and a custom Commodore part that is
  scarce, irreplaceable, and rising in price. Designing a machine around a part
  you cannot buy a second of is the one sourcing mistake that cannot be fixed
  later.

### 12.2 Ricoh RF5C68 — the near miss

Genuinely close, and worth recording because it is the strongest single-chip
candidate: **8 PCM channels, 8-bit, per-channel start/loop/step/volume/pan,
64 KB wave RAM, ~1988–89** (Sega System 18, later the Mega-CD). One chip plus RAM
plus a DAC would be a ~10-IC card.

Three problems, in increasing order of seriousness:

1. **It is a phase accumulator, not a variable fetch clock.** Pitch is a
   fractional address step, so mod `PER` values need a reciprocal — a divide per
   note, or a 1,712-entry lookup table. Solvable, and the table is small.
2. **It uses `$FF` as an end-of-sample marker** rather than a length counter, so
   sample data cannot contain `$FF`. Mod samples must be pre-clamped at load time.
   Audible only on loud material, but it is a real edit to the source data.
3. **Availability.** Arcade and Mega-CD pulls only, no second source, and no
   datasheet from the manufacturer. Same failure mode as §12.1, one step less severe.

Problem 1 alone would be acceptable. Problem 3 is what rules it out — and the
discrete card is ~47 ICs more (§10's honest 57 against a ~10-IC `RF5C68` card) for
parts you can buy forever. That gap was quoted as ~25 when §10 said 35; it is the one
place in this document where the re-tally makes a rejected alternative look
meaningfully better, and it is recorded rather than glossed. Availability still
decides it.

### 12.3 Ensoniq 5503 DOC — the right chip for the wrong job

[`graphics.md`](../../video/docs/graphics.md) §17 assumed this part, and that assumption should be
retired. The DOC is *better silicon* than Paula: 32 oscillators, 8-bit PCM,
16-bit phase accumulators, one-shot/loop/sync/swap modes, halt interrupts, its
own 64–128 KB wave RAM. The Apple IIgs played mods with it.

But measured against §1's specification:

| §1 requirement | DOC |
|---|---|
| Period reference = 3.546895 MHz | **no** — a phase accumulator against its own oscillator clock |
| `PER` as a direct divisor | **no** — needs a reciprocal per note |
| `LC`/`LEN` shadow reload | **no** — loop mode restarts from the *same* pointer; the one-shot→loop idiom has no equivalent |
| Volume 0–64 linear | 8-bit volume, different law |
| Hard-panned 0,3 / 1,2 | its 32 oscillator outputs are **time-multiplexed on one 3-bit select**, needing external demux + sample-and-hold + DACs |
| `$00` cannot appear in wave data | forces sample pre-clamping |

**Every one of those is a translation layer in the replayer**, and requirement 3
is the one that cannot be translated at all — the shadow reload has to be
emulated by taking an interrupt at buffer end and rewriting the pointer, which
reintroduces a hard-real-time interrupt at up to 126 kHz. The DOC is an excellent
32-voice synthesiser and a poor Paula.

It also has the same sourcing problem as §12.1 and §12.2.

### 12.4 Generate the audio in the `arm6309` STM32 itself — rejected on first principles

The machine's CPU is already a 170 MHz microcontroller with a DAC and DMA. Why not
mix four channels there?

**Because [`plan.md`](../../cpu/docs/plan.md) §4.1 forbids it.** The bus loop is hard real time:
every action is keyed off an observed edge, the budget is 54–81 core cycles per
bus cycle, and **a hardware ISR is forbidden — it would blow `t_AD`**
([`graphics.md`](../../video/docs/graphics.md) §12.2 restates this for the raster-compare
interrupt, and reaches the same conclusion). A mixer needs either an ISR or a
polling slot inside the loop, and there is no room for either. The CPU emulator
is the one piece of this machine with no spare time in it.

### 12.5 An MCU sound card — **not rejected; retained as the bring-up vehicle**

A second STM32G431 on a small card, with the **register map of §9** and a DAC,
does everything in this document in ~500 lines of C and **6–8 ICs**. It is not
period-honest, and the whole point of the exercise is that the card should be.

But it is worth building **first**, and for the same reason
[`graphics.md`](../../video/docs/graphics.md) §16 gives for the bus exerciser: it decouples the
software from the hardware. With the MCU card on the bench you can write the
loader, the replayer and the `.mod` converter, run the acceptance test, and find
out which of §1's nine requirements you got wrong — **before five GALs have been
fitted.** Then the discrete card is a drop-in replacement that has to match a
known-good reference, and any disagreement is a bug with a bisector attached.

That is exactly the A/B lever [`plan.md`](../../cpu/docs/plan.md) §6.2 builds the whole
validation strategy on, applied one level up.

**So: freeze §9's register map first. The register map is the deliverable; the
implementation is a choice, and the machine should be able to hold both.**

---

## 13. Software

> **The loader and replayer now have their own document,
> [`modplayer.md`](modplayer.md), and a working reference implementation in
> [`audio/refplayer/`](../refplayer/)** — which is what found the volume-LUT
> and tempo-clock errors corrected in §6.1 and §8.2. The document covers the
> `.mod` format, what the loader must and must not transform, the tick engine, the full effect command set, the
> position-advance ordering, and the ProTracker behaviours that are load-bearing.
> This section is the summary and the cost model; that one is the specification.

### 13.1 What the replayer costs

A ProTracker replayer does two different amounts of work. On **tick 0 of a row**
it reads four pattern entries and triggers notes; on the other ticks it applies
per-channel effects (arpeggio, portamento, vibrato, tremolo, volume slide) and
writes `PER` and/or `VOL`.

Estimated against a **2.098 MHz 6309 in native mode**, at the same assumed
~5 core cycles per store that [`graphics.md`](../../video/docs/graphics.md) §7.3 uses — and with
the same warning, that **every figure here scales on that assumption** (§16 item 1):

| Work | Cycles | Rate | Cycles/s |
|---|---|---|---|
| Plain tick: 4 channels × effect + `PER`/`VOL` writes | ~900 | 50 Hz | 45,000 |
| Row tick: pattern fetch, decode, note triggers, `DMACON` | ~2,000 extra | 8.33 Hz (125 BPM, 6 ticks/row) | 16,700 |
| **Total** | | | **~62,000** |

**≈3 % of the CPU.** Even at 4× the estimate it is 12 %, and the replayer runs
from `FIRQ` (§8.1) so the entry overhead is minimal. **Mod playback is not a CPU
problem on this machine** — which is worth saying plainly, because on the CoCo 3
hardware this replaces, software audio playback consumes essentially the entire
processor.

Compare against the machine's other loads: an 80×25 text scroll is ~2.5 ms of CPU
([`graphics.md`](../../video/docs/graphics.md) §7.3). Music plays underneath the console with
room to spare.

### 13.2 Loading a module

```
  1. read the .mod from disk into system RAM        (I/O bound)
  2. parse the 20-byte title, 31 sample headers, pattern table
  3. copy sample data to card RAM through SPTR/SDATA
  4. build the per-channel LC table from sample offsets
  5. write ACTRL, load TIMER for the initial BPM, start
```

Step 3 is the only interesting one, and the 6309 has exactly the right
instruction for it. **`TFM X+,Y`** — source auto-increments, **destination
fixed** — streams a block to a fixed I/O port at **3 cycles/byte**, which is
`SDATA`'s auto-increment doing the addressing on the card side:

| | Cycles | Time @ 2.098 MHz |
|---|---|---|
| `LDA ,X+` / `STA SDATA` loop | ~10/byte | 625 ms for 128 KB |
| **`TFM X+,Y`** | **3/byte** | **187 ms for 128 KB** |

`W` is 16 bits and `TFM` treats `W` = 0 as 65,536 nowhere — it stops — so 128 KB is
**three** `TFM` instructions and a pointer fix-up: `65,535 + 65,535 + 2 = 131,072`.
([`modplayer.md`](modplayer.md) §4.4 states the same arithmetic; they agree.) The
card's posted-write path retires one byte per colour clock in slot 5 —
**3.55 M/s against `TFM`'s 700 k/s**, a 5× margin, so **no `/WAIT`, no FIFO
stall, no lost writes** (§9.3). At the experimental fast-E rate the numbers become
1.05 M/s against 3.55 M/s, still 3.4×, and the upload falls to 125 ms.

**The margin is not the only thing that can go wrong with this transfer.** `SDATA` is
a side-effecting port and `TFM`'s interrupt/resume behaviour is unsettled, which is a
silent-corruption hazard rather than a throughput one; §9.2 states it and
[`modplayer.md`](modplayer.md) §4.4 costs the mitigation (chunk at 32 bytes, mask
across each chunk: 187 ms becomes 238 ms).

**The margin is checkable, which is the point of `ASTAT` b6 and `AINTREQ` b5.** The
card has no `/WAIT`, so an overrun would lose the byte silently and produce a sample
upload that is wrong in one place — the worst possible failure for a loader. The
loader reads `AINTREQ` once after each `TFM` burst; bit 5 sticky-set means a byte was
dropped and the upload must be redone. On this machine it can never set. That is the
right relationship between a proof and an assertion: the arithmetic says it cannot
happen, and the hardware says so too if it ever does.

This is the second concrete payoff for `TFM` in the machine, after
[`graphics.md`](../../video/docs/graphics.md) §10.2's bulk RAM movement, and both of them exist
because the CPU is a 6309 and not a 6809.

### 13.3 The `.mod` converter, and what it has to do

Almost nothing, which is the point of §1 and §4.1:

| Field | Transformation |
|---|---|
| Sample data | **copy verbatim** — 8-bit signed, same encoding |
| Sample length (words) | **copy verbatim** into `LEN` |
| Repeat offset / repeat length | **copy verbatim**; the replayer writes them into `LC`/`LEN` on tick 1 (§3.3) |
| Period values in patterns | **copy verbatim** — same reference clock |
| Finetune | **copy verbatim** — it indexes the same period tables |
| Volume 0–64 | **copy verbatim** |
| `Fxx` BPM | **copy verbatim** — same CIA-B arithmetic (§8.2) |
| Sample start address | +base, and >>0 (byte addressed, §9.3) |

The only real edit is relocating samples into card RAM and building the address
table. **There is no resampling, no requantisation, no retuning, and no format
conversion**, and that is the strongest single argument for every decision in
§4.1, §6.1 and §8.2. A converter that has to do arithmetic is a converter that
has a rounding error, and mods are unforgiving about rounding errors in `PER`.

### 13.4 NitrOS-9 fit

The card wants a small `SCF`-style driver or a dedicated subroutine module: an
`init` that clears the state file, a sample-upload entry, and an `FIRQ` service
routine. NitrOS-9's interrupt polling is `IRQ`-oriented; a `FIRQ` handler that
bypasses the OS entirely is both faster and — because it touches nothing the
kernel owns — safer. Document it as a *hard* `FIRQ` owner: the audio card is the
only `/FIRQ` source in the machine, so no polling chain is needed.

---

## 14. Where this sits — the comparison

| | CoCo 3 (what this replaces) | C64 SID 6581 | **Amiga Paula** | Ensoniq 5503 | **This card** |
|---|---|---|---|---|---|
| Year | 1986 | 1982 | 1985 | 1985 | **1989–90 parts** |
| Channels | 1, software-driven | 3 | **4** | 32 | **4** (8, §11.2) |
| Synthesis | none — raw DAC | subtractive | **8-bit PCM** | 8-bit PCM | **8-bit PCM** |
| Sample memory | system RAM, CPU-fed | none | 512 KB chip RAM, DMA | 64–128 KB, DMA | **128–512 KB, DMA** |
| Resolution | 6 bit | 4-bit master volume | **8 bit × 6-bit volume** | 8 bit × 8-bit volume | **8 bit × 6-bit volume, 12-bit out** |
| Max rate/channel | CPU-bound | n/a | **28.6 kHz** | ~26 kHz | **118 kHz** (§4.3) |
| Stereo | mono | mono | **hard-panned L/R** | multiplexed | **hard-panned, or panned (§11.1)** |
| CPU cost of music | **~100 %** | ~2 % | ~2 % | ~2 % | **~3 %** (§13.1) |
| Analogue filter | none | **per-voice, resonant** | fixed 4.4 kHz + LED | none | **both Amiga filters + bypass** |
| Plays `.mod` unmodified | no | no | **yes** | with a translation layer | **yes** |

The honest summary: **this is a Paula, one clock generation later, with the
DMA-slot limit removed and a better volume path.** It is not more capable than
Paula in any way that matters to the acceptance test, and that is deliberate.

---

## 15. Build order

| # | Step | Exit criterion |
|---|---|---|
| 0 | **Freeze §9's register map** and the backplane's `/FIRQ` and I/O-window assignment | one document; §16 items 4–6 answered; and the four bits the review found open are now decided in §9.2 — `ACTRL` b4 = 8-channel, `ACTRL` b6 = timer enable, `AINTREQ`'s set form documented, `ASTAT` b6/b7 defined |
| 1 | **Build the MCU card** (§12.5): STM32G431 + `LTC7545A` pair + §7's filters | plays a known module correctly through the §9 register map |
| 2 | **Write the loader, replayer and converter** against the MCU card | acceptance test: 20 varied modules, A/B against a real Amiga or a reference emulator, by ear and by capture |
| 3 | **Bench the §3.2 stage-B path** at 35 ns on a breadboard — LUT SRAM at 15 ns, driven by counters | closes with margin, or the §3.2 fallback latch is adopted |
| 4 | **Fit the sequencer GALs** with all eight slots, the shadow reload, the deferred queue and the interrupt block | equations fit in **5 × GAL22V10** as allocated in §9.5, with the host-visible counters in `'593`s and not in macrocells; §16 item 7 answered before the 8-channel mode is promised |
| 5 | **Discrete card rev A**, driven by the STM32 bus exerciser ([`graphics.md`](../../video/docs/graphics.md) §16.1) — no 6309 core needed | state file reads back; a single channel plays a sine from card RAM at a known `PER` |
| 6 | **All four channels + the shadow reload** | the step-2 module set plays **identically** to the MCU card, sample-for-sample where captured |
| 7 | **Analogue bring-up**: I/V, both filters, bypass, grounding | THD and noise floor measured; no digital hash from the SRAMs in the output |
| 8 | **Tempo timer + `/FIRQ`** under NitrOS-9 | music plays under a running console with no tick loss |
| 9 | **Supersets** (§11), only after step 6 passes | |

**Step 2 gates everything.** Until a module plays correctly through the §9
register map on *any* implementation, the discrete card is being built against a
specification that has not been tested.

---

## 16. Open items

1. **Confirm the CPU store rate.** §13.1's ~3 % and §13.2's 187 ms both scale on
   "~5 core cycles per store, native mode" — the same assumption
   [`graphics.md`](../../video/docs/graphics.md) §19 item 1 already flags. Measure it once and both
   documents get their numbers.
2. **Bench the stage-B path at 35 ns** (§3.2): GAL address out → 32K×8 LUT →
   accumulator setup. This is the card's only tight path and it decides between
   15 ns and 20 ns SRAM and the +1 `'574` fallback.
3. **Enumerate Paula's reload and `DMACON` quirks** before writing the sequencer
   GAL: the exact instant of the `LC`/`LEN` copy, the first-fetch delay after DMA
   enable, behaviour when `LEN` = 0 or 1, and what happens when `DMACON` is cleared
   mid-buffer. These are the things that make or break §1 requirements 3 and 6,
   they are all documented behaviour, and they are all cheap **if enumerated
   before the fit**. Verify each against the MCU card in step 2.
4. **Freeze the I/O window** at `$FF40–$FF4F` (§9.1) or elsewhere, with the video
   card's `$FF60–$FF7F` and a future disk controller in the same picture.
5. **Freeze the `LC` byte / `LEN` word asymmetry** (§9.3). It is a one-line
   decision that every piece of software downstream depends on.
6. **Confirm `/FIRQ` ownership** (§8.1) — the audio card as the sole source, with
   no polling chain, needs to be stated in the backplane spec, not assumed.
7. **GAL fit, and the 8-channel question** (§11.2). The sequencer carries the
   8-slot walk, the compare, the shadow reload, the deferred queue, `DMACON`
   set/clear and the interrupt latches. §9.5 now allocates **5 × GAL22V10 = 50
   macrocells and uses essentially all of them**, having moved 41 bits of
   host-visible counter out into `74HC593`s where they belong. **Fit it at five
   before committing to the budget** — the question is no longer "do the counters
   fit" (they do not, and they are gone) but whether the sequencer and the interrupt
   block fit with no spare macrocells, which is a worse place to be. Fit the
   8-channel slot allocation before promising the mode. Same posture as
   [`graphics.md`](../../video/docs/graphics.md) §19 item 15.
8. ~~**Verify the §6.2 glitch argument on the bench.**~~ — **retired.** It was a
   consequence of the combinational sum, which §6.2 no longer specifies. The DAC is
   driven from static latch outputs 141 ns after they settle, so there is no adder
   transient on the converter input to measure and no deglitch latch to hold in
   reserve. What is still worth measuring is the converter's own code-transition
   glitch (5 nV·s) against the analogue noise floor, which is item 9's job.
9. **Measure the analogue noise floor with the digital section running.** Seven
   SRAMs and a 28 MHz slot clock on the same board as a 12-bit DAC is the one
   genuinely new risk this card carries that the video card does not. Single-point
   ground, separate `LTC7545A` reference rail, and physical separation — then
   measure.
10. **`LTC7545A` settling with the chosen op-amp.** 1 µs against a 7.9 µs worst-case
    event spacing (§6.3) is a 8× margin on paper; confirm with the actual I/V
    stage, since the margin is what allows the parallel DAC to replace the serial
    one.
11. **Sample-RAM sizing.** Survey the actual module corpus you intend to play and
    confirm 128 KB covers it, or populate all four sockets from the start. The
    footprints cost nothing; the decision costs a rebuild.
12. **Decide whether the NTSC oscillator ships** (§4.1). It is one part and one
    mux term, and the answer depends entirely on how much NTSC-timed material you
    care about.
13. **Guarantee the `DMACON`-enable latch within 4 colour clocks.** The replayer
    writes `LC`/`LEN` for the loop point *immediately after* enabling the channel,
    in the same tick ([`modplayer.md`](modplayer.md) §5.3). That is only safe if
    the sequencer has already copied `LC → PTR` and `LEN → CNT`. A deferred slot
    normally does it within one or two colour clocks, but the queue can hold four
    channels. **Specify a bounded latch — enable-triggered work jumps the deferred
    queue, ≤4 colour clocks (1.13 µs)** — rather than leaving the replayer to
    insert ProTracker's 68000-era delay loop. It is a priority term in the
    sequencer GAL, and it removes a whole class of intermittent bug.
14. **Emulator model.** Whatever host-side emulator the project runs must model the
    state file, the compare timing, the shadow reload and the `FIRQ` sources — or
    software will be written against a card that does not exist. **It must also model
    the host boundary of §9.4**: the byte-serial arrival of multi-byte fields at ~8.45
    colour clocks apart, and the commit-on-low-byte rule that makes them atomic. A
    model that applies a two-byte `PER` write instantly is *hiding* the class of bug
    §9.4.1 describes rather than testing it — the same failure mode
    [`modplayer.md`](modplayer.md) §8 already records for a model that runs the replayer
    in zero card time. Same requirement as
    [`graphics.md`](../../video/docs/graphics.md) §19 item 13, and the MCU card of §12.5 is a
    better reference than any model.
15. **The `AD7545A` datasheet is not in `reference/datasheets/`** — the plain
    `AD7545` and the `LTC7545A` are. §6.3's `tWR` = 100 ns figure for the `AD7545A`,
    which is the whole reason the period part is viable at all, is second-hand.
    **§17's period audit rests on it**, so verify it against the real datasheet
    before that audit is taken as settled — and note that the plain `AD7545`, which
    *is* in the repo, would not have worked in 1989 either.
16. **The `LTC7545A`'s production status is unverified.** §6.3 calls it
    "current-production" and prices it at ~\$9; neither figure has been checked
    against a distributor or against Analog Devices' lifecycle page. If it has gone
    NRND the argument does not collapse — the `AD7545A` still drops into the same
    socket — but the BOM note does.
17. **Decide §6.2's four-DAC analogue sum before the analogue section is laid out.**
    4 × `LTC7545A` summing as currents at the two I/V virtual grounds is **twelve
    packages cheaper** than the latched digital sum, keeps all 12 bits per channel
    instead of spending one on the `>>1`, updates each converter on its own channel
    event, and is what Paula actually does. What it needs and this document has not
    done is the analogue work: four mid-scale offset injections onto two summing
    nodes, resistor matching, and `RFB` tracking across four parts. **It is the single
    largest lever on §10's count**, and it has to be pulled before layout or not at
    all.
18. **Probe the LED filter against libopenmpt's `a500` behaviour.** Aud-M4 — the
    filter was specified, modelled and unit-tested as 5-pole for as long as it was,
    because **no probe in the A/B ladder ever issues `E0x`**, so every comparison ran
    with the filter in one state. Add a single-note probe that toggles `E0x` mid-note
    and compare the transition against libopenmpt's `a500` LED path. The pass condition
    is the three-pole chain of §7 — the fixed ≈4.4 kHz pole plus a **12 dB/octave**
    Sallen-Key at 3275 Hz — and the failure it exists to catch is the old five-pole
    specification's extra 12 dB/octave, which shows up as 24 dB of missing level two
    octaves above the corner. Until that probe exists, "both Amiga
    filters, switchable" is an unverified claim about the half of §7 the acceptance
    test can hear.
19. **Confirm the card fits its envelope at 57 packages** (§10). The old text asserted
    a single-Eurocard fit at 35 with the analogue section kept physically separate;
    that assertion does not carry. Double-height card, analogue mezzanine, or item 17.
20. **Decide the CIA `latch + 1`** (§8.2). A real 8520 in continuous mode takes
    `latch + 1` counts per period; the compare structure of §4.2 takes `latch`. The
    difference is 0.0070 % — 42 ms over a ten-minute module — and it is one term in
    the sequencer GAL. Decide it *with* the fit, because "CIA-B-identical" is §1
    requirement 9 and the document should say which of the two it means.
21. **Scope the DAC output across a zero crossing** before anything else in the
    analogue bring-up (§6.3). Aud-M1 was a full-scale error that no amount of listening
    to the digital side would have found: play a slow full-amplitude sine at a long
    `PER`, trigger on the accumulator's `$800` code, and confirm the output is
    continuous there. It is a five-minute measurement that discriminates
    offset-binary-correct from two's-complement-wrong, and it should be step 0 of
    build step 7.
22. **Fix the tuning measurement before quoting a tuning result.** The A/B harness's
    spectral check runs at 24 bins/octave — **50 cents per step** — and then thresholds
    at ±12 cents, so it can only ever return an integer multiple of 50 and can only
    pass at exactly 0. Every error this document's §4.1 is about is smaller than one
    step: the NTSC-clock mistake is **+16 cents**, the worst period-table
    transcription error **16 cents**, one finetune step **12.5 cents**. The instrument
    cannot see any of them. Parabolic interpolation of the correlation peak, or FFT
    peak interpolation on a single-note probe, resolves ~1 cent and costs a few lines;
    until then the "+0.0 cents" figure quoted in
    [`modplayer.md`](modplayer.md) §8 and [`../README.md`](../README.md) means "within
    the quantisation of an instrument too coarse to test the claim."

---

## 17. Period audit

| Element | Introduced | Verdict |
|---|---|---|
| Paula (MOS 8364) as the model | **1985** | the design premise |
| 28.37516 MHz crystal | 1985 (Amiga PAL master) | period-exact, and still purchasable |
| `AD7545A` 12-bit buffered MDAC | **1983** | period — **built as `LTC7545A`**, its pin-compatible current-production replacement (§6.3) |
| `TL072` / `NE5532` | 1978 / 1979 | period |
| `74HC` logic | 1982 | period |
| `74HC688` 8-bit comparator | 1984 | period |
| `74HC593` 8-bit counter with input register | 1984 | period — the six host-visible counter packages of §9.5 |
| `74HC07` open-drain hex buffer | 1982 (the bipolar `7407` is 1965) | period — the `/FIRQ` stage of §8.1 |
| `GAL22V10` | 1986 | period (the video card already uses 8) |
| `CY7C128A` 2K×8, 15 ns | 1985 | period |
| 32K×8 SRAM, 15 ns | ~1988 | period |
| AS6C1008 (128K×8 SRAM) | 1 Mbit SRAMs ~1989–90 | **the newest silicon on the card** — same part, same caveat as the video card |
| ProTracker / the `.mod` format | 1987–1990 | the workload |

**The card places at 1989–1990**, driven by the 1 Mbit SRAM — the same date and
the same driving part as the video card, which is the coherence check that
matters. Unlike the video card, nothing here needs `74AHCT`: the fastest signal
on the board is a 35 ns slot, and plain `74HC` covers it.

Pulling back to 1988 is easy and nearly free here: 4 × `62256` for 128 KB of
sample RAM (+3 ICs, −0 capability). Unlike the video card, that substitution
costs nothing but packages, so **if a 1988 date matters to you, this is the card
that can have it.**

**The one part that is not period at all is the CPU**, unchanged from
[`graphics.md`](../../video/docs/graphics.md) §15 — and, if §12.5's bring-up card ends up shipping,
the sound card too. That is a decision to make deliberately, not to inherit.

---

## 18. Sources and cross-references

- [`graphics.md`](../../video/docs/graphics.md) — §3.1 (posted writes), §5 (one clock, static
  arbitration), §9 (the palette LUT argument this card's volume LUT copies),
  §11 (the `VDATA` prefetch this card's `ADATA` copies), §12 (interrupt
  placement), §13 (register-map conventions), §14 (chip-budget format), §15
  (period audit), §16 (the bus exerciser), **§17 (the DOC assumption this
  document supersedes)**.
- [`plan.md`](../../cpu/docs/plan.md) — §2.1 (edge-driven bus loop), §4.1 (no hardware ISR — the
  reason for §12.4), §4.3 (`TFM`), §6.2 (the A/B validation lever §12.5 reuses).
- `~/code/colormin/docs/backplane.md` — slot model, open-drain interrupt lines,
  the mono `AUDIO` node that [`graphics.md`](../../video/docs/graphics.md) §17 already argues should
  be stereo.
- **Amiga hardware behaviour** — Paula's register set, `DMACON`/`INTREQ`
  semantics, the audio DMA slot allocation, and the CIA-B tempo path. **Every
  behavioural claim in §1, §4.2 and §4.3 is from the documented model and must be
  re-verified against real hardware or a cycle-accurate emulator in build step 2**
  (§16 item 3). The reload semantics of §3.3 are the ones to check first and
  hardest — the entire acceptance test rests on them.
- A500 filter values (360 Ω / 0.1 µF fixed pole; the **2-pole** LED Sallen-Key at
  3275 Hz) are from the schematic and from the two implementations that are checked
  against real hardware — `pt2-clone` and libopenmpt's `a500` filter, both of which
  model LED as second-order. Confirm against the board revision you want to
  match — A500 and A1200 differ substantially, and the A1200's fixed pole is
  effectively absent. ⚠ The earlier "5-pole LED filter" reading of the schematic was
  wrong (§7, Aud-M4).
