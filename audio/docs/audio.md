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
| **Discrete card, real Paula, a period sound chip, or an MCU?** | **Discrete card.** **36 ICs** (§10, re-tallied four times), one Eurocard plus a physically separate analogue section. | §12 |
| **Where does the sample data live?** | **Card-local SRAM, 128 KB** (footprint for 512 KB). The card never touches the bus for audio. | §5 |
| **How are the four channels implemented?** | **One time-multiplexed datapath**, 8 slots per colour clock, state in a 32-bit-wide SRAM file. | §3 |
| **How is per-channel pitch generated?** | **Compare-against-a-free-running-counter**, not four down-counters. Kills 12+ ICs. | §4.2 |
| **What is the period reference clock?** | **3.546895 MHz — the Amiga PAL colour clock**, from a 28.37516 MHz crystal ÷8. Non-negotiable. | §4.1 |
| **How is volume applied?** | **By the other half of the converter.** The sample DAC's output is the *reference* of a second multiplying DAC whose code is the volume, so the product is formed in the analogue domain and is not quantised at all. No table, no multiplier, no boot upload. | §6.1 |
| **How are channels summed?** | **In the analogue domain, the way Paula does it** — one DAC per channel, its own I/V amplifier, and a two-resistor passive sum per side that *is* the fixed 4.4 kHz pole. No adder, no accumulator, no output sample rate, no resampling, no jitter. | §6.2 |
| **What DAC?** | **4 × AD7528** — dual 8-bit parallel multiplying DAC, on one die, with on-chip latches: eight halves, one sample and one volume converter per channel. Not a serial audio DAC — §6.3. **Samples are stored offset binary**, converted once by the loader — §6.1. | §6.3 |
| **Do we need the Amiga filter?** | **Yes, and not for nostalgia.** It is the reconstruction filter for channels running below ~16 kHz. Both filters, switchable. | §7 |
| **Where does mod tempo come from?** | **An on-card 16-bit timer clocked at colourclock/5 = 709.379 kHz — the Amiga's CIA clock exactly**, so `Fxx` BPM values are CIA-B-identical. Costs one slot, zero ICs. | §8.2 |
| **Which interrupt line?** | **`/FIRQ`.** Video's VBL owns `/IRQ`. A 6809 `FIRQ` is what a replayer tick should be. | §8.1 |
| **What does mod playback cost the 6309?** | **~2.7 % of a 2.098 MHz CPU** for the replayer, with a 19× worst-case margin; **~187 ms once** to upload 128 KB of samples via `TFM X+,Y` — ~690 ms if the loader also has to convert the samples to offset binary (§6.1, §13.2). | §13, [`modplayer.md`](modplayer.md) §7 |
| **What does this card do that Paula cannot?** | No minimum period; 8 channels at half period resolution; a programmable volume curve (now host software — §6.1); per-channel panning for +3 ICs (§11.1). | §11 |

**Net: 36 ICs**, level with the video card. One oscillator, **one internal clock
domain and an asynchronous host port** (§9.4), no bus mastering, no `/WAIT`, and
**no tight path at all**: the fastest thing on the card is a state-file read at
30 ns inside a 35.24 ns slot, on a part already specified at that grade. The 35 ns
LUT stage that used to hold that title left the per-colour-clock path in §3.2.

> ⚠ **"35 ICs" and "one clock domain" are both superseded (design review — Aud-M2,
> Aud-M3, Aud-M5, and decision D9).** The old tally counted the datapath and left out
> four things that are not optional: the L/R sum path (§6.2 — ten packages the old
> §10 never listed), the host-visible counters `SPTR`/`LIDX`/`AIDX` (41 flops of
> counter — §9.5), the host-boundary synchroniser and multi-byte commit staging
> (§9.4), and the open-collector stage `/FIRQ` needs and a GAL output cannot provide
> (§8.1). "One clock domain" was true of everything downstream of the crystal and
> false at the register port, which is where the failures of §9.4 live. §10 now
> tallies **57**, itemised, with a delta table showing where the twenty-two came
> from. Every count elsewhere in *this* document has been corrected, and so have the
> figures quoted in [`machine.md`](../../docs/machine.md) and in
> [`graphics.md`](../../video/docs/graphics.md)'s comparison tables — both now carry the
> **54** of the note below.

> ⚠ **And "57" is now 54: the four-DAC analogue sum is adopted (§6.2, §16 item 17
> closed).** The digital channel sum — fourteen packages of hold latch, adder and
> accumulator — is deleted and replaced by **two more converters, eight hold latches and
> a resistor pair**. Doing
> the analogue work that item 17 said had to come first moved the number twice more,
> both times against the alternative's own recorded estimate of **−12**:
>
> | | Δ |
> |---|---|
> | Delete the digital sum path: 4 × `'574` hold, 6 × `'283` adder, 4 × `'273` accumulator | **−14** |
> | **Per-channel DAC hold latches** — the LUT output is valid for one 35 ns slot and the converter wants `tDS` = `tWR` = **100 ns**, so each channel needs its own 12-bit latch. The recorded alternative missed this. | **+8** |
> | Two more `LTC7545A` (2 → 4) | **+2** |
> | One more `TL072`: **four separate dice do not match**, so each converter needs its own I/V amplifier (§6.3) — current-summing them as Paula does is what an 8–15 kΩ `RREF` spread forbids | **+1** |
> | **Net** | **−3 → 54** |
>
> It is still the right change — it deletes the entire digital sum and its four-stage
> pipeline, keeps all 12 bits per channel, and cuts the converter's update latency from
> a frame-quantised 282–564 ns to a uniform 211 ns — but it is worth **three** packages,
> not twelve.

> ⚠ **And "54" is now 45 — none of it from the audio path.** The card was carrying nine
> packages of state and buffering that the state file and the deferred slots were built
> to hold: `SPTR`/`LIDX`/`AIDX` move into three of the state file's 2032 spare words
> (**−6**, §9.5), multi-byte commit staging becomes a shadow word (**−2**, §9.4.3), and
> the read-back `'245` goes because the prefetch `'574` drives the bus itself (**−1**,
> §9.3). In the same pass the volume LUT left the per-slot path (§3.2): no packages, but
> it retires the card's only tight timing path, removes 1–2 colour clocks of
> data-dependent jitter, and cuts the converters' write rate by **28×**. The card walks
> 14.2 M state reads a second to service 126,000 events; the nine packages were the
> parts that had forgotten that.

> ⚠ **And 45 is now 36, because the volume LUT was the wrong answer to a question the
> converter answers for free (§6.1).** An `AD7528` is a **dual** 8-bit multiplying DAC
> on one die. Cascade its halves — sample byte into the first, its output as the
> *reference* of the second, volume as that one's code — and the multiply happens in
> the analogue domain:
>
> | | Δ |
> |---|---|
> | Volume LUT deleted: 2 × 32K×8, the `LIDX`/`LDATA` registers, and the 65,536-byte boot upload | **−2** |
> | Per-channel hold latches: the port is 8 bits wide now, not 12, and each side's two channels share one register | **−6** |
> | 4 × `LTC7545A` → 4 × `AD7528` (eight halves) | **0** |
> | State-file word 0 is `{NEXT[15:0], PEND[7:0]}` = 24 bits | **−1** |
> | **Net** | **−9 → 36** |
>
> The sample is quantised to 8 bits (Paula-exact) and the volume to 8, but **the
> product is not quantised at all** — better than the 12-bit table it replaces. `VOL`=0
> becomes exact silence with no pedestal, and because both ladders of a side sit on one
> die with `VREF` matched to **±1 %**, their currents finally sum at a single virtual
> ground the way Paula's four do. The cost is glitch: **160 nV·s against the
> `LTC7545A`'s 5** (§6.3, §16 item 9).

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
| 4 | **Volume 0–64, linear, applied as an 8×6 multiply** | Volume slides, tremolo, and the `Cxx` command. 64 is unity, 65 levels. | free — it is the second half of the converter (§6.1) |
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
  channels. §6.2 does the same thing in the same domain — one converter per channel,
  summed after the I/V stage — which is the design's nicest property.
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
per-channel pointers, the host-visible counters, the converter port registers and the
host-boundary staging, which is where §10's honest package count actually goes. A
card can be enormously oversupplied in time and still cost 36 packages, and this one
does.

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
| 0–3 | **channels 0–3**: read state, compare event time, **and on a hit clock the pre-computed value straight into this channel's DAC** |
| 4 | **tempo timer**: compare, reload, raise `/FIRQ` |
| 5 | **host service**: retire one posted write, or prefetch one read (§9.3) |
| 6–7 | **deferred work**: the sample fetch that refills `PEND` (§3.2), pointer increment, length decrement, buffer reload, `LC`/`LEN` shadow copy, volume-converter writes (§6.1), host-counter increments (§9.5) |

Slots 0–3 run **unconditionally every colour clock**, which is what makes the
design jitter-free: a channel's sample transition always lands on its true
Paula boundary, never on a "whenever the sequencer got round to it" boundary.
Slots 6–7 are where the rare, expensive work goes — at most 126,000 pointer
updates per second against 7.1 M deferred slots per second, a **56× margin**.

### 3.2 The pipeline

Each slot is three pipeline stages, one slot deep each, exactly the shape of the
video card's `index latch → LUT → output latch`:

```
  stage A  (35 ns) : state-file read  -> {NEXT[15:0], PEND[7:0]}   = 24 bits
  stage B  (35 ns) : compare NEXT vs the free-running counter
  stage C  (35 ns) : on a hit, mark the channel due and queue it for slots 6-7
```

**The pipeline is three stages, the fourth one is gone, and there is no table lookup
in any of them.** `PEND` is the sample byte this channel's converter will take at its
*next* event, fetched in advance by the deferred slots. The per-colour-clock walk does
one 24-bit SRAM read, one 16-bit compare, and — on the ≤126,000 occasions per second
when the compare hits — sets one flag. Nothing else.

> ⚠ **Superseded twice, and the second time removed the LUT from the card entirely.**
> Stage B originally did `LUT read {VOL,SAMP} → 12-bit sample` *every slot for every
> channel*, refreshing a hold latch with a value that was almost always the one already
> in it: 14.2 million lookups a second to produce 126,000 changes. That is what made
> stage B "the card's only tight path", what forced a 15 ns SRAM grade, and what held a
> `+1 '574` fallback in reserve. Precomputing into `PEND` deleted the path; §6.1 then
> deleted the table itself, because the volume multiply moved into the converter.

**Three things fall out, and the third is the one that matters.**

- **The card no longer has a tight path.** Nothing in the walk but a state-file read
  and a compare: 10 ns of address setup + 15 ns of `CY7C128A-15` + 5 ns of setup =
  **30 ns inside a 35.24 ns slot**, on the part already specified. §16 item 2 is
  retired and the fallback latch is withdrawn.
- **The converters are written on events, not on colour clocks.** Each `WR` line goes
  from 3.5 M pulses per second to ≤126,000 — **a 28× cut in digital switching**
  immediately beside the analogue section, on the card whose one genuinely new risk is
  exactly that (§16 item 9), and against a converter whose glitch impulse is 32× the
  one it replaced (§6.3).
- **It removes jitter that the old arrangement had.** With the table in the loop, a
  channel's new sample reached its converter only after a deferred slot had fetched the
  byte and written `SAMP` back — and the deferred queue holds four channels while
  draining two per colour clock, so on coincident events the third and fourth channels
  were **1–2 colour clocks late, data-dependent**. §6.2 claimed the converter's input
  changes on the exact colour clock the sample changed on. With `PEND` the event-instant
  work is a flag and a fixed write window, so that is finally true.

**The refill has enormous slack.** After a hit the deferred slots fetch the next sample
byte from card RAM, advance `PTR`/`CNT` (or reload from `LC`/`LEN` — §3.3), and write
the byte into `PEND`: four slots, at most. The next event on that channel is at least
30 colour clocks away even at §4.3's 118 kHz extreme, which is **60 deferred slots**;
four coincident channels need sixteen.

**And a volume write does not wait for a sample event.** `VOL` goes to the volume
converter, not through `PEND` (§6.1), so a host write queues its own deferred write to
that channel's volume half and takes effect within about a microsecond — the same
promptness the continuously-read table used to give, by a shorter path.

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
| `PEND` | 8 | sequencer | **the sample byte the converter will take at the next event** — §3.2 |
| flags | 4 | both | DMA enable, attach-period, attach-volume, IRQ pending |

**The packing is not arbitrary.** Word 0 of each channel holds exactly
`{NEXT[15:0], PEND[7:0]}` = **24 bits**, which is why stage A of §3.2 needs one access
and not two, why the walk needs nothing else, and why the state file is **three**
`2K×8` packages rather than four.

> ⚠ **Corrected — the packing was one bit over, not one bit under.** This word was
> first written as `{NEXT[15:0], VOL[5:0], SAMP[7:0], DMAEN, ATT}`. §6.1's correction
> then gave `VOL` its seventh bit (0–64 is 65 levels), which makes
> `16 + 7 + 8 + 1 + 1 = 33` — one bit past the state file's 32-bit width, and the
> whole reason stage A is a single access. **`ATT` moves to word 1.** It is consulted
> only on a compare hit, which is a deferred slot that reads words 1–3 anyway, so
> moving it costs nothing and restores the exact 32.
>
> ⚠ **Superseded again, and the word is now `{NEXT[15:0], PEND[7:0]}` — 24 bits, and
> the state file lost a package with it.** `VOL` and `SAMP` were in word 0 because
> stage B fed them to a volume LUT every slot. §3.2 stopped doing that (the deferred
> slots prefetch the byte into `PEND`) and §6.1 then deleted the LUT outright, because
> the volume multiply moved into the converter. `VOL` and the flags join
> `LC`/`LEN`/`PER`/`PTR`/`CNT` in words 1–3, where the deferred slots read them anyway.
> **The 19-bit `PTR` still comes off a single 24-bit read**, which is what keeps the
> sample-RAM address path free of a latch — and, since §9.5, the host-visible counters
> with it.

Everything the per-colour-clock walk touches
is in that word; `LC`, `LEN`, `PER`, `VOL`, `PTR` and `CNT` live in words 1–3
and are only read in the deferred slots. Freeze this layout with the register map (§9.3) — it is
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
- **No adder in the audio path.** The channel sum of §6.2 is two resistors, not logic.
  The only adder on the card is the shared 16-bit `'283` chain of slots 6–7, and
  nothing in the sample path waits on it.
- **No divider anywhere.** Period is a divisor applied by comparison (§4.2), never
  computed.
- **No FIFO, no buffering, no DMA arbitration.** Sample memory is card-local and
  200× oversupplied (§2), so there is nothing to arbitrate.
- **No output sample rate.** §6.2.

> ⚠ **Twice superseded, and the original sentence is true again (design review,
> Aud-M2; then the four-DAC promotion).** The history is worth keeping because the
> first fix was correct about the fault and wrong about the remedy.
>
> 1. This section originally claimed **"the only adder on the card is the shared
>    16-bit `'283` chain in slots 6–7"** while §0 and §6.2 claimed the four channels
>    were summed **"combinatorially, asynchronously"**. Both could not be true, and
>    neither was costed. Aud-M2 was right about that.
> 2. The fix was **latched accumulation with dedicated 12-bit adders** — fourteen
>    packages, a fourth pipeline stage, a frame-boundary clear that had to be ordered
>    against the DAC's write, and a `>>1` that cost a bit of every channel. It worked; it was
>    expensive; and the word "combinatorially" had been reaching for something else.
> 3. **What it was reaching for is what Paula does: an analogue sum.** §6.2 now does
>    that — one converter per channel, summed after the I/V stage — and with the
>    digital sum gone the original sentence is simply true. The adder count on this
>    card is one chain, in slots 6–7, at 126 kHz.

The video card's "no adder anywhere" property (minimal256.md §3) survives here in
nearly its full form: **there is one adder on this card and it is not in a critical
loop.** The shared 16-bit `'283` chain in slots 6–7 does `NEXT`+`PER`, `PTR`+1 and
`CNT`−1 at 126 kHz, work no one is waiting for. It is never in the sample-fetch path
and never in the audio path, and there is still no multiplier and no divider.

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

### 6.1 Volume is the other half of the converter

Paula applies a 6-bit volume to an 8-bit signed sample. In 1989 logic that is a
parallel multiplier (`TRW TDC1008`-class — expensive, hot, absurd at 126 kHz), or a
lookup table, or **the operation a multiplying DAC performs by definition**. This
section specified the table for a long time. It is the third one.

**Cascade two converters per channel.** The sample byte drives an 8-bit multiplying
DAC against a fixed reference; its I/V output becomes the **reference** of a second
8-bit multiplying DAC whose code is the volume:

```
  SAMP[7:0] -->| DAC |--> I/V --> Vs  = -Vref * SAMP/256      (a voltage, 8-bit steps)
                  ^
                Vref (fixed)

  Vs ------------>| DAC |--> I ~= Vs * VOLCODE/256            (the multiply, in analogue)
                     ^
                  VOLCODE = VOL x 4
```

That is not a trick; it is the AD7528's own headline application — *"Digitally
Controlled Dual Telephone Attenuator … ideal for stereo audio signal level control"*,
input into `VREF`, code sets attenuation (§6.3, and the datasheet in
[`reference/datasheets/`](../../reference/datasheets/)).

**What it costs in resolution: nothing, and it gains.**

| | Quantised to | Note |
|---|---|---|
| Sample | **8 bits** | Paula-exact, and all the source has |
| Volume | **8 bits** | `VOLCODE` = `VOL` × 4, saturated at 255 — one shift in the sequencer |
| **The product** | **not at all** | it is formed as a current, not as a number |

The table it replaces produced a **12-bit** product and spent an SRAM pair, a 15 ns
speed grade and a 65,536-byte boot upload doing it. `VOL` = 1 now attenuates the full
8-bit sample by 36 dB instead of reducing it to a 12-bit value of ±2, which is the
argument the old "12-bit output, not 8" paragraph was making — reached by deleting the
digital product rather than by widening it.

> ⚠ **Superseded — the volume LUT, `LIDX`/`LDATA` and the boot upload are all deleted.**
> §6.1 previously addressed a 32K×8 pair with `{VOL[6:0], SAMP[7:0]}` → 12-bit offset
> binary, host-loaded through a `LIDX`/`LDATA` pointer/data pair, and called the volume
> curve "table content, not hardware". Everything in that argument was sound except its
> premise: the multiply did not need to happen in the digital domain at all. Gone with
> it are **2 × 32K×8** (§10), the 15 ns grade, the `+$D`–`+$F` registers (§9.2), the
> `LIDX` counter (§9.5), the ~94 ms `TFM` upload at boot, and 4 of the 8 packages of
> DAC hold latch — the port is 8 bits wide now, not 12.
>
> **The one thing it took with it was the programmable volume curve**, which §6.1 was
> right to want. It comes back in software: **`ACTRL` b3 = raw volume**, and `VOL`
> becomes an 8-bit attenuator code the host writes directly. A replayer that wants a
> dB-linear law, a soft-clip or a per-machine calibration keeps a 65-byte table and
> writes the mapped byte — one indexed load per volume change, in the tick that was
> writing `VOL` anyway. The default (`ACTRL` b3 = 0) is `VOL` 0–64 with the card doing
> the ×4, so the register stays Paula-identical and the acceptance test does not move.

> **`VOL` is still seven bits in the state file** (0–64 is 65 levels — the correction
> that build step 0 found, and the reason word 0's packing was re-derived twice). With
> `ACTRL` b3 set it is eight, and the sequencer stops shifting.

**Sample coding moves to the loader, and costs nothing there.** An 8-bit multiplying
DAC takes **unsigned** data, so a two's-complement sample byte would put full-scale
steps at every zero crossing (§6.3 — this is Aud-M1, and it survives every change to
this section because it is a property of the converter). The fix used to be baked into
the LUT's contents. It is now one `XOR #$80` per byte in the loader, which already
walks every sample to relocate it ([`modplayer.md`](modplayer.md) §4). Samples live in
card RAM **offset-binary**; silence is `$80`.

**Silence is exactly zero, and that is new.** At `VOLCODE` = 0 the volume DAC's ladder
delivers no current at all, so a silent or disabled channel contributes nothing —
no half-scale pedestal, no DC step at `DMACON` changes, and nothing for the output
capacitor to remove. The old arrangement had to force the LUT address to `VOL` = 0 for
a disabled channel to get `$800` onto the bus; the new one forces `VOLCODE` = 0, which
is the same single term and a better result.

### 6.2 The sum is analogue — and the currents really do sum at one node

Paula produces four independent current-output DACs and sums them at an analogue
node. There is **no output sample rate** anywhere in an Amiga's audio path — each
channel is a zero-order hold at its own rate, and the sum is continuous-time.

This card does the same, and it can now do it the way Paula does — **as currents at a
virtual ground** — because of one line in the AD7528 datasheet:

> `VREF A`/`VREF B` **Input Resistance Match: ±1 % max.**

That is the number the four-converter arrangement could not get. A current-mode
ladder's output scale is set by its reference resistance, which the AD7528 specifies
as **8 kΩ min / 11 kΩ typ / 15 kΩ max** — a ±30 % spread *between packages*, which is
why summing two separate dice into one I/V amplifier put `ch0` and `ch3` up to 5.5 dB
apart and why the previous revision spent an amplifier per channel to escape it. Two
ladders **on one die** match to 1 %: 0.09 dB, and it tracks over temperature.

**So the pairing is by side, not by channel:**

```
  AD7528 #1   DAC A = ch0 sample   DAC B = ch3 sample     |
  AD7528 #2   DAC A = ch0 volume   DAC B = ch3 volume     |--> OUT A + OUT B
                                                          |    into ONE I/V --> L
  AD7528 #3   DAC A = ch1 sample   DAC B = ch2 sample     |
  AD7528 #4   DAC A = ch1 volume   DAC B = ch2 volume     |--> OUT A + OUT B
                                                          |    into ONE I/V --> R
```

Each side's two volume ladders share a summing node and an amplifier, with both
parts' `RFB` tied to that amplifier's output. Paralleling the two on-die feedback
resistors halves the transimpedance, which is exactly the headroom split Paula's four
ladders make and the one the old digital `>>1` produced: **one channel alone reaches
half of full scale, two at full scale reach all of it** — except that here each
channel still resolves all eight of its bits against an unquantised product.

> ⚠ **Superseded — three times now, and this is the one the word "combinatorially"
> was reaching for.** (1) The sum was specified as "combinatorial, asynchronous" and
> never costed — read as digital logic it needs 14 packages the tally did not have.
> (2) Aud-M2 replaced it with latched accumulation through dedicated 12-bit adders:
> correct, costed, ten packages, a fourth pipeline stage and a bit off every channel.
> (3) The four-DAC analogue sum deleted all of that but could not sum currents,
> because four separate dice do not match, so it spent four I/V amplifiers and eight
> hold latches instead. **The dual converter removes the last obstacle**: the sum is
> two wires into a virtual ground, the way it is inside a Paula.

#### The write window, which is the only thing the digital side still owes

The AD7528's input latches are transparent while `CS` and `WR` are low and capture on
the rising edge, so the port must be stable across it. At `VDD` = 5 V over
temperature: **`tWR` 100 ns, `tDS` 90 ns, `tCS` 100 ns, `tAS` 100 ns, `tDH` 0 ns**.
The state file presents a channel's byte for one 35.24 ns slot, so — exactly as
before — the port needs a register in front of it.

**One 8-bit `'574` per side**, driving both of that side's packages, with the frame
split into two fixed windows:

| Slots | Left `'574` | Right `'574` |
|---|---|---|
| 0–3 | `ch0`'s byte; `CS` on #1, `DAC A/B` = A, `WR` low, captures at the end of slot 3 | `ch1`, `CS` on #3, select A |
| 4–7 | `ch3`'s byte; `CS` on #1, `DAC A/B` = B, `WR` low, captures at the end of slot 7 | `ch2`, `CS` on #3, select B |

Each window is **4 slots — 141 ns**, against 100 ns of `tWR`/`tCS`/`tAS` and 90 ns of
`tDS`: **40 % margin on every one of them**, and `tDH` = 0 is satisfied by the register
simply not moving. **A window is used only when that channel's compare hit** — at most
once per channel per colour clock, which is exactly the two windows a side has.

**The windows run one frame behind the compare**, because a channel's byte comes off
the state file in its own walk slot and the window it belongs to may already have
started. So: hit in frame *N* (§3.2), converter written in frame *N+1*. The latency is
**10 or 11 slots — 353 or 388 ns — fixed per channel** by which window that channel
owns. A constant per-channel offset of one slot is not jitter; it is 0.1 % of the
shortest sample period ProTracker can ask for, identical on every note, and nothing in
§1's nine requirements can see it.

Volume writes are host-driven and rare (≤50 Hz per channel). One borrows a window,
asserting `CS` on the volume package instead of the sample package, which displaces
one sample write by one colour clock about once every 70,000 frames.

**Two packages of latch, not eight**, because the bus is 8 bits wide rather than 12
and each side's two channels can share a register that is loaded twice per frame.

Packages, itemised so §10 has something to add up:

| Qty | Part | Role |
|---|---|---|
| 4 | **`AD7528`** | 8 converter halves: one sample + one volume per channel, paired by side (§6.3) |
| 2 | `74HC574` | one 8-bit port register per side |
| 0 | — | volume LUT, adders, accumulators, output registers: **none** |
| — | 4 × 0.1 % resistor + passives | the pedestal cancellation of §6.3 |

**Hard panning is free.** ch0,3 → L and ch1,2 → R is which package a channel's volume
half sits in. And **programmable panning is now +3 rather than +10** — §11.1.

### 6.3 The converter: parallel, not serial — and dual, and cascaded

A serial audio DAC (`PCM56P`, `TDA1541A` — better converters) needs a **fixed frame
rate**: you clock 16 bits into it every `1/Fs`, which reintroduces the output sample
rate §6.2 exists to eliminate. At the `TDA1541A`'s practical ceiling (~192 kHz) a
channel transition quantises to 5.2 µs against a 31.9 µs sample period — **16 %
jitter on individual sample boundaries**, audible as a change in timbre on high notes,
and exactly the artefact that separates a good mod player from a great one. That
argument has survived every revision of this section and it is why the part is
parallel.

**`AD7528` — dual 8-bit multiplying DAC, on-chip latches, 20-pin 0.3" DIP, +5 V,
four-quadrant, separate `VREF` and `RFB` per half, DACs on one die.** Analog Devices,
1985. Specify the **L / C / U grade**: ±½ LSB relative accuracy and ±1 LSB gain
error, monotonic over the full temperature range on every grade.

| | Serial (`PCM56` / `TDA1541A`) | 4 × `LTC7545A` (superseded) | **4 × `AD7528`** |
|---|---|---|---|
| Packages, incl. registers | 4 DAC + 8 `'165` + divider ≈ **13** | 4 DAC + 8 `'574` = **12** | **6** |
| Volume | 2 × 32K×8 LUT | 2 × 32K×8 LUT | **in the converter** |
| Output sample rate | fixed, 192 kHz ceiling | none — event-driven | **none — event-driven** |
| Boundary jitter at `PER`=113 | ±5.2 µs (16 %) | 0 | **0** |
| Channel match across a summing node | n/a | ±30 % (`RREF` spread) → 4 amplifiers | **±1 %, on-die** |
| Product resolution | 16 bit | 12 bit, quantised | **8-bit terms, analogue product** |

> ⚠ **Superseded — the `LTC7545A`, and the `AD7545`/`AD7545A` argument with it.** This
> section specified a 12-bit `LTC7545A` per channel and spent two pages establishing
> that the plain `AD7545` could not be clocked fast enough at 5 V (`tWR` 250 ns at
> 25 °C, 400 ns over temperature, against a 281.9 ns frame) while the `AD7545A` and
> `LTC7545A` could (`tWR` 100 ns). That analysis was correct and is why
> [`AD7545.pdf`](../../reference/datasheets/) and
> [`LTC7545A.pdf`](../../reference/datasheets/) are still in the repo. It stops being
> load-bearing here because the card no longer needs a 12-bit converter: with the
> multiply in the analogue domain there is nothing for the extra four bits to carry.
> **§16 item 15's missing `AD7545A` datasheet is retired with it**, and §17's period
> audit now rests on a part whose datasheet is present.

**What the change costs, stated plainly — and it is glitch.**

| at `VDD` = +5 V | `LTC7545A` | **`AD7528`** |
|---|---|---|
| Digital-to-analogue glitch impulse | **5 nV·s** typ | **160 nV·s** typ |
| Current settling | 1 µs to 0.01 % | 350 ns typ / 400 ns max to ½ LSB |
| `VREF`-to-`OUT` feedthrough | 5 mV p-p @10 kHz | **−70 dB** (−65 over temperature) |
| Output leakage at zero code | — | ±50 nA (±400 nA over temperature) |

**32× more glitch energy per code transition**, and this is the one axis on which the
cascade is worse than what it replaces. Three things blunt it and none of them make it
go away: §3.2 cut the number of code transitions per channel from 3.5 M/s to ≤126 k/s;
the glitch enters *before* the volume stage, so it attenuates with the channel's own
volume; and §7's 4.4 kHz pole sits between it and the output. **Measure it — §16
item 9 is now specifically about this**, and it is the reason to buy the L/C/U grade
rather than the J.

Settling is 400 ns per stage and there are two in series, against a **7.9 µs**
worst-case event spacing — a 10× margin. Feedthrough at `VOLCODE` = 0 means a muted
channel leaks its sample at −65 dB, where Paula leaks nothing; that is below the
analogue noise floor the card is trying to hit anyway (§16 item 9). The zero-code
leakage current is DC and lands on the summing node as a fraction of an LSB of offset,
which §7's output capacitor removes along with everything else.

#### The sample DAC's pedestal, cancelled before the multiply

The sample converter is unsigned-coded (§6.1), so its I/V output sits at half of full
scale — `Vref/2` — when the sample byte is `$80`. That pedestal has to go *before* the
volume stage, because a pedestal multiplied by a changing volume is a DC step on every
volume slide — an audible click at about −48 dB, arriving at tick rate.

**One 0.1 % resistor per channel, from that converter's virtual ground to a reference
of the polarity opposite `Vref`, sized `R = 2 × RFB`.** The ladder current flows *into*
the virtual ground, so a resistor to `+Vref` would double the pedestal rather than
cancel it — the polarity is the trap, and an earlier revision of this document had it
backwards. `−Vref` is one amplifier channel off `Vref` through a matched pair, and §7
has exactly one spare.

Four resistors and one amplifier is the whole analogue overhead, and it buys something
the previous three revisions all had to work around: **because the cancellation happens
upstream of the volume DAC, the card's output is exactly zero at `VOL` = 0 and has no
volume-dependent DC anywhere.** The `$800` silence convention, the doubled-offset
arithmetic of the digital sum, and the "output capacitor is load-bearing" argument are
all deleted rather than corrected.

`Vref` remains a free master-volume/mute point, now common to four sample converters:
pull it to zero and the card is silent. It must be **one buffered reference feeding all
four parts** — four ladders in parallel are ~2.75 kΩ, and series impedance between the
buffer and an individual part becomes a gain error on that channel alone (§16 item 24).

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
| **Fixed** | 1-pole RC after the side's summing amplifier — **3.6 kΩ + 0.01 µF**, the A500's 360 Ω / 0.1 µF scaled ten to one | **4421 Hz, 6 dB/oct** | always in, unless bypassed |
| **"LED"** | **one 2-pole Butterworth Sallen-Key stage**, in series with the fixed pole | **3275 Hz, 12 dB/oct** | `ACTRL.0` |
| **Bypass** | `74HC4066` shorting both | flat to the converter's own ZOH | `ACTRL.1` |

The pole is an ordinary RC again, driven by an op-amp output, because §6.2 sums the
two channels of a side **as currents at that amplifier's virtual ground** rather than
as voltages through a resistor pair. Scaling the network ten to one keeps the A500's
corner while leaving the `74HC4066`'s ~70 Ω on-resistance a 2 % perturbation when the
switch shorts the series resistor, and it costs the amplifier a tenth of the load the
A500's own 360 Ω would have.

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

Parts: **2 × `TL074` + 1 × `TL072`** + **1 × `74HC4066`** + passives — **ten amplifier
channels, nine used**:

| Amplifier channels | As first written | After Aud-M4 | 4 × `LTC7545A` | **Now (cascade)** |
|---|---|---|---|---|
| Sample-converter I/V | — | — | — | **4** — one per channel, each on its own die's `RFB` (§6.2) |
| `−Vref` inverter | — | — | — | **1** — the pedestal cancellation of §6.3 |
| Summing I/V | 2, one per side | 2 | 4, one per converter | **2** — the two volume ladders of a side sum at one virtual ground |
| Bipolar offset subtractor | (unbudgeted) | 0, offset injected | 0, DC-blocked | **0** — cancelled upstream of the volume stage |
| LED Sallen-Key stages | 4 (two per side) | **2** (one per side) | 2 | 2 |
| **Total** | 6 = 3 × `TL072` | 4 = 2 × `TL072` | 6 = 3 × `TL072` | **9 of 10 = 2 × `TL074` + 1 × `TL072`** |

Three packages either way, and the shape changed rather than the count: the four
amplifiers that used to exist because *four separate dice do not match* are now four
amplifiers that exist because there are four sample converters, and the summing
amplifiers went back to two because the ±1 % on-die `VREF` match lets the currents meet
(§6.2). The `TL074` is the same part in a quad package; an `NE5532` is the better
op-amp and equally period, and `TL07x` is specified here for supply-rail simplicity.
**Line output**, not a speaker amp: ~2 V p-p, **DC-blocked**, 100 Ω series. The
blocking capacitor is back to being good manners rather than load-bearing: §6.3
cancels the sample converters' pedestal upstream of the volume stage, so the card's
output is already centred and is exactly zero when every channel is silent. What the
capacitor still removes is the converters' zero-code leakage and the amplifiers' own
offsets — tens of millivolts, not half of full scale. Size it against the following load —
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
| `+$5` | `ACTRL` | W | b0 LED filter, b1 filter bypass, b2 NTSC clock, **b3 raw volume** — `VOL` is an 8-bit attenuator code instead of Paula's 0–64 (§6.1), **b4 8-channel mode** (§11.2), b5 pan enable (§11.1), **b6 tempo-timer enable** (§8.2), b7 master enable |
| `+$6`–`$8` | `SPTR` | W | sample-RAM pointer, 19 bits, auto-increment |
| `+$9` | `SDATA` | R/W | sample-RAM byte at `SPTR`, **post-increment** — a **side-effecting port**, see the `TFM` note below |
| `+$A` | `ASTAT` | R | b3..0 channel DMA active, b4 timer running, b5 reserved (reads 0), **b6 posted-write busy**, **b7 prefetch valid** — b6/b7 defined below |
| `+$B`–`+$C` | `TIMER` | W | tempo-timer reload, 16 bits, clocked at **709,379 Hz** — load `1773447 / BPM` (§8.2) |
| `+$D`–`+$F` | — | — | **reserved, reads 0.** Was `LIDX`/`LDATA`, the volume-LUT load path, deleted with the table itself (§6.1) |

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
| 8 | `DAT` | 1 | `AUDxDAT` | direct sample write, CPU-fed mode (§1 req. 8) — **offset binary**, like everything else the converter sees (§6.1) |
| 9 | `ATT` | 1 | `ADKCON` bits | b0 attach-period, b1 attach-volume (§11.3). **Channel 3's bits are ignored** — there is no channel 4 and no wrap to channel 0 |
| 10 | `PAN` | 1 | — | §11.1, ignored unless `ACTRL.5` — and unpopulated unless that superset is built |
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

**And that latch is the whole read-back path — the `74HC245` is deleted.** A `'574` is
an octal flip-flop *with three-state outputs*: enable it on `/IOSEL·R/W` and it drives
the host data bus itself. Every other readable byte on the card — `ASTAT`, `AINTREQ`,
the `ACTRL` shadow — is a `GAL22V10` output, and those are three-state too. The `'245`
was buffering sources that can already drive the bus.

> ⚠ **Superseded.** This section previously argued the `'245` "is not a substitute" for
> the prefetch latch, which is true and answers a question nobody asked: a transceiver
> cannot *store*. What it does not do is establish that anything has to *buffer* a
> latch that already drives three-state outputs onto the bus. **−1 package** (§10).
> The one thing to confirm is drive: `74HC` sources 6 mA, the same as the `'245` it
> replaces, so the backplane loading rule has to be met by the same margin it was
> already being met by — it is a check, not a change (§16 item 26).

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
therefore atomic already, and `SPTR` is a pointer into a linear write stream
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

**Cost: nothing — the staging is a shadow word in the state file** (§9.5 makes the same
move for the host counters). Each channel's arriving bytes land in a shadow word at
`AIDX | $40`; the committing byte triggers one deferred-slot copy of shadow → live. The
widest field is `LC` at 3 bytes, so a 32-bit shadow word covers every field in the table
with room to spare, and the copy is the same read-hold-write the deferred slots already
do for the `LC`/`LEN` reload of §3.3.

> ⚠ **Superseded.** This rule first cost **2 × `74HC574`** of discrete staging. That was
> state living outside the state file, which is what the whole card is for; the two
> packages are deleted and the rule is unchanged.

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
- **`ADATA`.** The prefetch latch is written only in slot 5 and drives the host bus
  directly (§9.3); the state file itself is written only in deferred slots. The host therefore
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
| `SPTR` — sample-RAM pointer, 19-bit auto-increment | 19 | **the state file, word `$7D`** — incremented by the shared `'283` in a deferred slot | **0** |
| `AIDX` — state-file index, 6-bit auto-increment | 6 | **the state file, word `$7F`** — at a fixed address the sequencer knows, which is what breaks the circularity | **0** |
| `INTENA` | 6 | GAL 4 | — |
| `INTREQ` (+ 6-bit pending register, §9.4.5) | 12 | GAL 5 | — |
| `DMAEN` | 4 | GAL 3 | — |
| Tempo ÷5 prescale + timer enable | 4 | GAL 3 | — |
| Slot counter | 3 | GAL 1 | — |
| Deferred-work queue + enable-priority term (§16 item 13) | ~6 | GAL 1 / GAL 5 | — |
| Sequencer state machine, stage control | ~8 | GAL 1 | — |
| Address mux, decode, host synchroniser control | — | GAL 2 | — |
| | | **`GAL22V10` ×5** | **5** |

> ⚠ **Superseded — the counters are gone, not cheaper.** This section first put the 41
> bits in **6 × `74HC593`** (8-bit counter, input register, three-state outputs),
> arguing that was better than eleven `'161`. Both answers were wrong about the
> question: **the card already owns 2048 words of 32-bit state and uses sixteen of
> them**, and it already owns a 16-bit adder that runs at 126 kHz against 7.1 M
> deferred slots per second. Host-visible counters are state and increments; the card
> is made of state and increments.

**Where the 41 bits actually live: in the state file, in three of its 2032 spare
words.** An auto-increment becomes exactly the operation the deferred slots already
perform on `PTR` and `CNT`:

```
  host store to SDATA:
    deferred slot A : read state word $7D          -> SPTR on the read bus
                      the read is HELD for this slot and the next
                      sample RAM /WE with the address off that same bus,
                      data from the posted-write latch
    deferred slot B : shared '283 computes SPTR+1 from the held bus
                      write it back to word $7D
```

**Two slots per host write, and the address bus needs no latch** — the state file's own
SRAM outputs hold the address for as long as the sequencer holds the read, which is the
whole reason a deferred access is allowed two slots. This is the same trick the `PTR`
fetch path uses; the counters simply stop being a special case.

**The sample-RAM address now has one source.** It is the state-file read bus — `PTR`
when the sequencer fetches, `SPTR` when the host writes — and nothing else drives it.
The "address mux" of GAL 2 collapses from a mux into a chip-enable, which is the part
of this change that should *free* macrocells rather than spend them. (The LUT address
bus it used to share this argument with no longer exists: §6.1 deleted the table.)

**What it costs.** The two increments contend with channel work for the shared adder:
≤126 k channel events/s × ~4 slots plus ≤400 k host stores/s × 2 slots is **≈1.3 M of
7.1 M deferred slots — a 5× margin**, and the host figure is the 6309 saturating the
port with `TFM`, which only happens during the §13.2 upload. `SPTR` is 19 bits against
a 16-bit adder chain; the top three bits are a carry-in increment in the sequencer GAL.

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
| **3** | CY7C128A-15 (2K×8, 15 ns) | channel state file, **24 bits wide** — `{NEXT[15:0], PEND[7:0]}` in one read (§3.3) |
| 2 | 74HC590 | free-running 16-bit colour-clock counter (§4.2) |
| 2 | 74HC688 | 16-bit event comparator (§4.2) |
| 4 | 74HC283 | shared 16-bit adder — `NEXT`+`PER`, `PTR`+1, `CNT`−1 (slots 6–7) |
| 3 | 74HC574 | pipeline latches, stages A/B/C (§3.2) |
| **2** | **74HC574** | **converter port register, one per side — 8 bits, loaded twice per frame (§6.2)** |
| **4** | **AD7528** | **dual 8-bit parallel multiplying DAC, on-chip latches — eight halves: one sample and one volume converter per channel (§6.1, §6.3)** |
| **2** | **TL074** | **sample I/V ×4, summing I/V ×2, LED Sallen-Key ×2 (§7)** |
| **1** | **TL072** | **`−Vref` inverter (§6.3); one channel spare** |
| 1 | 74HC4066 | filter select / bypass (§7) |
| 1 | 74HC574 | posted-write data latch (host → sample RAM) |
| **1** | **74HC574** | **`ADATA`/`SDATA` read-prefetch latch (§9.3)** |
| **1** | **74HC174** | **two-flop host-port synchronisers ×3 (§9.4.4)** |
| 1 | 74HC273 | `ACTRL`, master reset |
| **1** | **74HC07** | **open-drain buffer for the wire-OR `/FIRQ` (§8.1, decision D9)** |
| **5** | **GAL22V10-15** | **sequencer/queue; address mux + decode; `DMACON`/timer; `INTENA`; `INTREQ`+pending (§9.5)** |
| 1 | 28.37516 MHz osc | PAL Amiga master (§4.1) |
| (1) | (28.63636 MHz osc) | (NTSC, socketed option, §4.1) |
| — | R-2R / passives | filter networks, offset-injection resistors (§6.3), output stage |
| **36** | | **(37 with the NTSC can)** |

Video card, for comparison: **36** (32 if the tri-state pixel bus closes). **This card
is no longer the small one**, and the honest statement of that is the point of the two
tables below.

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

**Then the four-DAC analogue sum was adopted (§6.2), and 57 became 54.** This is the
second re-tally, and it moved the opposite way for once:

| Where the 3 packages went | Δ | § |
|---|---|---|
| The whole digital sum path deleted: 4 × `'574` hold, 6 × `'283` adder, 4 × `'273` accumulator. With it go the fourth pipeline stage, the two-slot add, the frame-boundary clear ordering and the `>>1`. | **−14** | §6.2 |
| Per-channel DAC hold latches, 12 bits × 4. **The cost the recorded alternative missed:** `tDS` = `tWR` = 100 ns against a LUT output valid for one 35.24 ns slot. No two channels can share a package — they capture on different slot edges. | **+8** | §6.2 |
| Two more `LTC7545A`, 2 → 4: one per channel. | **+2** | §6.3 |
| One more `TL072`, 2 → 3: **four separate dice, four I/V amplifiers.** `RREF` is specified 8–15 kΩ part to part, so summing two ladders into one amplifier sets the two channels' relative level by parts binning — up to 5.5 dB. Paula's four ladders are on one die; these are not. | **+1** | §6.2, §7 |
| **Net** | **−3 → 54** | |

The alternative recorded in the previous revision costed this at **−12**. It was wrong
by nine packages in the same two places the analogue work was undone — which is exactly
what §16 item 17 said would have to be settled before the trade could be taken
seriously, and is the argument for settling such things before quoting them.

**Then 54 became 45, and none of it came from the audio path.** The card was carrying
nine packages of state and buffering that the state file and the deferred slots were
already built to hold:

| Where the 9 went | Δ | § |
|---|---|---|
| `SPTR`/`LIDX`/`AIDX` move into three of the state file's 2032 spare words, incremented by the shared `'283` in a deferred slot. The state file's own outputs hold the address during the access, so no latch replaces them. | **−6** | §9.5 |
| Multi-byte commit staging becomes a shadow word in the state file; the commit is the deferred-slot copy the card already performs for `LC`/`LEN`. | **−2** | §9.4.3 |
| `74HC245` read-back buffer: the prefetch `'574` has three-state outputs and drives the host bus itself, as do the `GAL22V10`s behind `ASTAT`/`AINTREQ`. | **−1** | §9.3 |
| **Net** | **−9 → 45** | |

**The pattern is one sentence: every package deleted here was state living outside the
state file, or a buffer in front of something that could already drive a bus.** The
card walked 2048 words of state at 14.2 M reads a second to service 126,000 events — a
113× over-provision — and then spent packages keeping counters somewhere else.

**Then 45 became 36, and this time it was the audio path.** The volume LUT was the
right answer to the wrong question: it did in a 32K×8 SRAM pair what the second half of
a multiplying DAC does for nothing (§6.1).

| Where the 9 went | Δ | § |
|---|---|---|
| The volume LUT — 2 × 32K×8, the `LIDX`/`LDATA` registers, the `LIDX` counter and the 65,536-byte boot upload — deleted. Volume becomes the code of a second converter whose reference is the first one's output. | **−2** | §6.1 |
| Converter port registers: the bus is 8 bits wide now rather than 12, and each side's two channels share one register loaded twice per frame. Eight `'574` become two. | **−6** | §6.2 |
| State-file word 0 is `{NEXT[15:0], PEND[7:0]}` — 24 bits, three packages instead of four, with the 19-bit `PTR` still arriving in one read. | **−1** | §3.3 |
| 4 × `LTC7545A` → 4 × `AD7528`. Same package count, twice the converters, and the ±1 % on-die `VREF` match is what lets §6.2 sum currents at one node. | **0** | §6.3 |
| **Net** | **−9 → 36** | |

**And it is not a fidelity trade.** The sample keeps its 8 bits (all Paula has), the
volume gets 8 (`VOL` × 4), and **the product is not quantised at all** where the table
quantised it to 12. `VOL` = 0 became exact silence instead of a `$800` pedestal. The
one regression is glitch — 160 nV·s against the `LTC7545A`'s 5 — which §3.2's 28× cut
in write rate blunts and §16 item 9 now exists to measure.

**Where it could shrink:**
- **−2** if the two converter port registers can be merged. They cannot be as drawn:
  the two sides' write windows run concurrently and a `'574` has one clock.
- **−2** if the state file goes to 16 bits, at the price of two accesses per slot, a
  17.5 ns SRAM that did not exist in 1989, and an address latch for `PTR` that would
  cost the packages back.
- **−4** for the two `'688` and two `'590` if the compare moves into the shared `'283`
  under an earliest-event scheme. It is the last structural idea on the list and it has
  not been costed; the walk's 4-channels-per-colour-clock compare is what makes the
  timing exact, and giving that up is not obviously free.

**Where it will grow:**
- **+3** for 512 KB of sample RAM.
- **+3** for programmable per-channel panning (§11.1) — two more `AD7528` and one more
  amplifier package, where the digital sum charged 2 and the four-converter analogue
  sum charged 10.
- **+1 `TL072`** if a DC-coupled output is ever wanted.

**Power.** Four SRAMs, five GALs, ~15 HC packages, ten op-amp channels and four
`AD7528` at 2 mA each: estimate **300–400 mA**. The old figure of 250–350 mA and its
"roughly half the video card" gloss went with the 35-package tally; at 36 the card is
back in that neighbourhood, but by a different route — it is a smaller digital section
and a larger analogue one. Analogue and digital grounds must meet at exactly one point,
and the `AD7528` reference must not share a rail with the SRAMs. That is the only
layout constraint on this card that the video card does not also have, and it is the
one that decides whether it sounds clean.

**Area.** 36 packages — one DIP-32, three DIP-24, five DIP-24 GALs, four DIP-20
converters, three op-amps and the rest DIP-16 and DIP-20 logic — against **35**, which
is the count this document asserted a single-Eurocard fit at before the review. The
assertion is not restored by arriving back at the same number (it was never measured,
and the analogue section has grown from two converters and four amplifier channels to
four and ten), but the question is no longer "does it need a second card". **Measure
the layout, with the analogue section physically separate — §16 item 19.**

---

## 11. What this card does that Paula cannot

Presented as opt-in, because **the default configuration must be Paula-exact** or
the acceptance test in §1 is meaningless. Each of these is a register bit that
software has to ask for.

### 11.1 Panning — fixed is free, programmable is +3 ICs

The number in this heading has been +2, then +10, and is now +3. It is worth the
three lines it takes to say why, because it is the clearest illustration of what the
architecture actually charges for.

| Sum | Programmable panning costs | Because |
|---|---|---|
| Digital accumulator | **+2** | widen the volume LUT to hold `(L gain, R gain)`; the accumulators already existed |
| Four 12-bit converters, analogue sum | **+10** | nothing to steer: a second converter *and* a second hold latch per channel, plus the wider LUT |
| **Cascaded dual converters (now)** | **+3** | a second **volume half** per channel — and halves come two to a package |

**Fixed panning is free.** Which summing node a channel's volume half drives is which
package it sits in, and any fixed law beyond hard-panning is a resistor pair from that
half's I/V output into both nodes.

**Programmable panning is two more `AD7528` and one more amplifier package.** Give
each channel a second volume half fed from the same sample voltage: eight volume
halves plus four sample halves is twelve, which is six packages rather than four. The
replayer then writes two codes per channel — `VOL` for the left and `PAN` (§9.3
offset 10) for the right — and computes both itself, which is where a pan law belongs
anyway. The one wrinkle is that each side's node now collects four volume halves
across two dice, so the ±1 % on-die match of §6.2 no longer covers the whole node:
give each die its own I/V amplifier and voltage-sum the two per side through a matched
0.1 % pair. That is the +1 amplifier package.

**The port registers do not change**, because volume codes are written at host rate,
not at event rate (§6.2). Neither does the slot walk, the state file, or anything in
§3. Paula could not pan either, so none of this touches the acceptance test.

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
discrete card is ~26 ICs more (§10's honest 36 against a ~10-IC `RF5C68` card) for
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
| **`TFM` + an in-place `LDD`/`EORD #$8080`/`STD` pass** | **~11/byte** | **~690 ms for 128 KB** |

**That third row is §6.1's offset-binary conversion, and whether you pay it depends on
where the file came from.** Card RAM holds samples offset binary because the converter
is unsigned-coded; a `.mod` holds them two's complement. If the module was prepared
offline (§13.3 — one `XOR $80` per byte, on a machine where that is free), the loader
still issues a verbatim `TFM` and the row above it stands. If an unmodified `.mod` is
being loaded from disk, the loader XORs each sector buffer in place before the `TFM`
and the upload costs **about 690 ms rather than 187**, once per module. A one-gate
hardware alternative is recorded as §16 item 27.

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
| Sample data | **`XOR $80`** — the card's converter is unsigned-coded, so card RAM holds offset binary (§6.1). One instruction per byte, and the only transformation in this table |
| Sample length (words) | **copy verbatim** into `LEN` |
| Repeat offset / repeat length | **copy verbatim**; the replayer writes them into `LC`/`LEN` on tick 1 (§3.3) |
| Period values in patterns | **copy verbatim** — same reference clock |
| Finetune | **copy verbatim** — it indexes the same period tables |
| Volume 0–64 | **copy verbatim** |
| `Fxx` BPM | **copy verbatim** — same CIA-B arithmetic (§8.2) |
| Sample start address | +base, and >>0 (byte addressed, §9.3) |

The real edits are relocating samples into card RAM, building the address table, and
flipping one bit of every sample byte. **There is still no resampling, no
requantisation, no retuning and no arithmetic** — an `XOR` is not a rounding error, and
it is exactly reversible — and that is the strongest single argument for every decision
in §4.1, §6.1 and §8.2. A converter that has to do arithmetic is a converter that has a
rounding error, and mods are unforgiving about rounding errors in `PER`. Doing the
`XOR` here rather than in the loader is what keeps §13.2's upload a verbatim `TFM`.

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
| 1 | **Build the MCU card** (§12.5): STM32G431 + one `AD7528` + §7's filters. It sums in software and drives one converter pair, not §6.2's eight halves — what it validates is the register map and the replayer, and the cascade is step 7's job | plays a known module correctly through the §9 register map |
| 2 | **Write the loader, replayer and converter** against the MCU card | acceptance test: 20 varied modules, A/B against a real Amiga or a reference emulator, by ear and by capture |
| 3 | **Bench the §3.2 stage-A path** at 35 ns on a breadboard — sequencer address out → `CY7C128A-15` state file → compare-input setup, 30 ns budgeted | closes with margin. The old stage-B LUT path is gone (§16 item 2), and with it the 15 ns LUT and the fallback latch |
| 4 | **Fit the sequencer GALs** with all eight slots, the shadow reload, the deferred queue, the host-counter increments and the interrupt block | equations fit in **5 × GAL22V10** as allocated in §9.5, with the host-visible counters in the state file and not in macrocells; §16 item 7 answered before the 8-channel mode is promised |
| 5 | **Discrete card rev A**, driven by the STM32 bus exerciser ([`graphics.md`](../../video/docs/graphics.md) §16.1) — no 6309 core needed | state file reads back; a single channel plays a sine from card RAM at a known `PER` |
| 6 | **All four channels + the shadow reload** | the step-2 module set plays **identically** to the MCU card, sample-for-sample where captured |
| 7 | **Analogue bring-up**: four sample I/V stages, the cascade into the volume halves, the two summing amplifiers, both filters, bypass, grounding | THD and noise floor measured; **converter glitch measured** (§16 item 9); **channel-to-channel gain matched** (§16 item 23); no digital hash from the SRAMs in the output |
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
2. ~~**Bench the stage-B path at 35 ns**~~ — **retired.** The LUT is no longer read in
   a 35 ns pipeline stage: §3.2 precomputes each channel's next value into `PEND`
   during the deferred slots, so the lookup has a **70.5 ns** window and a **55 ns**
   part covers it with margin. The `+1 '574` fallback is withdrawn with it. What is now
   the fastest path on the card is the state-file read — 10 + 15 + 5 = 30 ns against
   the slot, on the `CY7C128A-15` already specified — and it wants the same bench hour
   the LUT path was going to get.
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
   host-visible counter into the state file where they belong (§9.5). The sequencer
   gained the increment and shadow-commit micro-sequences in the same pass, and lost
   the address mux — the net is unproven either way. **Fit it at five
   before committing to the budget** — the question is no longer "do the counters
   fit" (they do not, and they are gone) but whether the sequencer and the interrupt
   block fit with no spare macrocells, which is a worse place to be. The four-DAC sum
   does not move this: **four `WR` lines and four latch clocks is eight control
   signals, exactly what the digital sum needed** for two holds, two accumulators, two
   clears and two writes (§6.2). Fit the 8-channel slot allocation before promising
   the mode. Same posture as
   [`graphics.md`](../../video/docs/graphics.md) §19 item 15.
8. ~~**Verify the §6.2 glitch argument on the bench.**~~ — **retired, twice over.** It
   was a consequence of the combinational sum, which §6.2 has not specified since
   Aud-M2; and there is now no adder on the card's audio path at all. Each converter is
   driven from a private hold latch that has been static for 105.7 ns when `WR` rises,
   so there is no digital transient to measure. What is still worth measuring is the
   converters' own code-transition glitch (5 nV·s, now four of them) against the
   analogue noise floor, which is item 9's job.
9. **Measure the analogue noise floor and the converter glitch with the digital
   section running.** Four SRAMs and a 28 MHz slot clock on the same board as eight
   converter halves is the one genuinely new risk this card carries that the video card
   does not, and §6.3 made one half of it worse on purpose: the `AD7528`'s glitch
   impulse is **160 nV·s against the `LTC7545A`'s 5**. Three things were argued to
   blunt it — §3.2's 28× cut in write rate, the fact that the glitch enters *before*
   the volume stage and so scales with the channel's own volume, and §7's 4.4 kHz
   pole — and none of them is a measurement. **Play a full-scale tone at low volume
   and look for the glitch rate in the spectrum.** Single-point ground, one buffered
   reference on its own rail (item 24), physical separation. This is the measurement
   that decides whether the cascade was the right trade.
10. **Cascaded settling with the chosen op-amp.** Two converters in series settle in
    400 ns each (§6.3) against a 7.9 µs worst-case event spacing — a 10× margin on
    paper, but the second stage's reference is the first stage's *output*, so it cannot
    start settling until the first has. Confirm with the actual amplifiers: four sample
    I/V stages driving four volume-converter reference inputs is a load the datasheet's
    application circuits do not draw.
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
15. ~~**The `AD7545A` datasheet is not in `reference/datasheets/`.**~~ — **retired.**
    §6.3 no longer specifies that part, or any 12-bit converter: the volume multiply
    moved into the converter and the card takes 8-bit halves. **`AD7528.pdf` is in the
    repo**, and every figure §6.1–§6.3 rests on — the ±1 % `VREF` match, `tWR`/`tDS`,
    the glitch impulse, the gain-error grades — is read from it rather than quoted
    second-hand. §17's audit now rests on a datasheet that is present.
16. **The `LTC7545A`'s production status is unverified.** §6.3 calls it
    "current-production" and prices it at ~\$9; neither figure has been checked
    against a distributor or against Analog Devices' lifecycle page. If it has gone
    NRND the argument does not collapse — the `AD7545A` still drops into the same
    socket — but the BOM note does.
17. ~~**Decide §6.2's four-DAC analogue sum before the analogue section is laid
    out.**~~ — **closed: adopted.** It is the primary design (§6.2). Doing the analogue
    work this item asked for is what settled it, and it settled the three claims the
    recorded version made — two against it, one for:
    - **"Twelve packages cheaper" was wrong — it is three** (§10's second delta table).
      The recorded alternative missed the per-channel hold latches the converter's
      100 ns `tDS`/`tWR` forces against a 35 ns LUT window (+8), and the second pair of
      I/V amplifiers the bullet below forces (+1 `TL072`).
    - **"Summing as currents at the two I/V virtual grounds" does not work.** `RREF` is
      specified 8–15 kΩ part to part, so two ladders sharing one feedback resistor set
      their relative level by parts binning — up to **5.5 dB** between `ch0` and `ch3`.
      Paula's four ladders are one die; four `LTC7545A` are four. Each converter keeps
      its own I/V amplifier and the sum happens one stage later, in voltage.
    - **"Keeps all 12 bits per channel, updates each converter on its own channel
      event, and is what Paula actually does" was right**, and is why it is adopted
      anyway at a fifth of the saving. What it left behind is items 23–25.
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
19. **Confirm the card fits its envelope at 36 packages** (§10). The old text asserted
    a single-Eurocard fit at 35, with the analogue section kept physically separate,
    and the review took the count to 57 and the assertion with it. Three passes have
    brought it back to **36**: the four-DAC analogue sum (−3), the state file absorbing
    the host port (−9), and the converter absorbing the volume multiply (−9). **The
    number is back where the assertion was made, but the assertion still has not been
    measured** — and the shape has changed underneath it: the digital section is
    smaller than it has ever been and the analogue section is twice what it was, at
    eight converter halves and ten amplifier channels. Measure it, with the analogue
    section physically separate. This is the last thing standing between the card and
    a layout.
20. **Decide the CIA `latch + 1`** (§8.2). A real 8520 in continuous mode takes
    `latch + 1` counts per period; the compare structure of §4.2 takes `latch`. The
    difference is 0.0070 % — 42 ms over a ten-minute module — and it is one term in
    the sequencer GAL. Decide it *with* the fit, because "CIA-B-identical" is §1
    requirement 9 and the document should say which of the two it means.
21. **Scope each sample converter's output across a zero crossing** before anything
    else in the analogue bring-up (§6.3). Aud-M1 was a full-scale error that no amount
    of listening to the digital side would have found, and the coding it is about has
    survived every revision of §6: play a slow full-amplitude sine at a long `PER`,
    trigger on the `$80` byte, and confirm the output is continuous there. Four times,
    one per channel, **on the sample converters' I/V outputs** — that is where the
    pedestal cancellation lives, and it is upstream of everything that would mask a
    mistake in it. It is a five-minute measurement that discriminates
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
23. **Measure channel-to-channel gain matching on real parts** (§6.2, §7). The whole
    reason the currents may share a summing node is the `AD7528`'s **±1 % `VREF` input
    resistance match**, which holds *within* a package and not between packages —
    which is why §6.2 pairs channels by side rather than by channel, and why getting
    the pairing wrong at layout would produce a card that works and is quietly
    mis-balanced. **Verify across parts from different date codes**: play the same
    full-scale tone on each channel in turn and compare levels. Pass condition ≤0.1 dB
    channel to channel. The failure this exists to catch is two ladders from different
    dice sharing one feedback resistor — the 5.5 dB error the previous revision spent
    four amplifiers to avoid.
24. **One buffered `V_REF` for four converters** (§6.3). Four ladders in parallel are
    ~2.75 kΩ, and any series impedance between the reference and an individual part
    becomes a gain error on that channel alone — the same failure as item 23, arriving
    through the reference instead of the feedback. Star-distribute from a buffer, and
    measure the level of each channel with the other three at full scale to catch it.
25. **Rails for the analogue switch and the LED stage** (§6.3). With the pedestal
    blocked rather than cancelled, the signal between the I/V stage and the output
    capacitor lives between 0 and −`V_REF`. The `74HC4066` and the Sallen-Key stage must
    be powered to pass it, which means split rails and a `VSS` below −`V_REF`. It is a
    rail decision and costs no packages, but it is not the single-5 V card the digital
    section is, and it should be in the schematic before the mezzanine question of item
    19 is answered.
26. **Confirm the prefetch `'574` can drive the backplane alone** (§9.3). Deleting the
    `74HC245` puts a `74HC` flip-flop's outputs directly on the host data bus. `74HC`
    sources 6 mA, which is what the `'245` sourced, so the loading rule is the one the
    card was already meeting — but it was being met by a part chosen for it, and it is
    now being met by a part chosen for something else. Count the loads on the bus,
    including whatever the backplane spec permits a future card to add, before the
    package is deleted from the BOM rather than from the document.
27. **Decide where the offset-binary conversion happens** (§6.1, §13.2). Card RAM holds
    samples offset binary; a `.mod` holds them two's complement. Three places can flip
    that bit, and the choice is a load-time-versus-package trade nobody has made:
    - **The offline converter** (§13.3) — free, and the loader keeps its verbatim
      `TFM` at 187 ms. Only works for modules prepared in advance.
    - **The loader**, `LDD`/`EORD #$8080`/`STD` over each sector buffer before the
      `TFM` — **~690 ms rather than 187 ms** for a full 128 KB image, once per module,
      and it works on any unmodified `.mod` straight off the disk.
    - **One gate**: an inverter on bit 7 of the sample-RAM-to-state-file fetch path
      only, leaving card RAM two's complement and `SDATA` read-back verbatim.
      **+1 package**, and it makes `DAT` (§9.3 offset 8) the one register that does
      *not* follow the rule, because it writes the state file directly. A single
      exception in a register map is worth more than 500 ms of load time only if
      modules are loaded often.

---

## 17. Period audit

| Element | Introduced | Verdict |
|---|---|---|
| Paula (MOS 8364) as the model | **1985** | the design premise |
| 28.37516 MHz crystal | 1985 (Amiga PAL master) | period-exact, and still purchasable |
| `AD7528` **dual** 8-bit multiplying DAC | **1985** | period, and the datasheet is in the repo — the sample/volume cascade of §6.1 is its own headline application. Four of them, eight halves |
| `TL072` / `NE5532` | 1978 / 1979 | period |
| `74HC` logic | 1982 | period |
| `74HC688` 8-bit comparator | 1984 | period |
| `74HC07` open-drain hex buffer | 1982 (the bipolar `7407` is 1965) | period — the `/FIRQ` stage of §8.1 |
| `GAL22V10` | 1986 | period (the video card already uses 8) |
| `CY7C128A` 2K×8, 15 ns | 1985 | period |
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
