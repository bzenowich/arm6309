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
- **Parts available before 1990.** Programmable logic is in (root `README.md`) — this card took a CPLD at §10.1, and
  not because the rule was wrong: §9.5's interrupt block does not fit a `GAL22V10`
  whole (13 equations, 10 macrocells) or split (17 inputs, 14 pins), so the GAL count
  was six and rising. It took a **second** CPLD on 2026-09-09 (§10.2), and that one is
  about pins rather than macrocells. `video/docs/graphics.md` §10.1.2 establishes that the rule was
  never a period one - Altera's first CPLD is 1988. GALs are in (the video card used 8
  before it too went to CPLDs).
- Same house rules as the video card: period-honest silicon, one card, a
  documented register map, and an honest IC count.

> **This supersedes [`graphics.md`](../../video/docs/graphics.md) §17's sound-card paragraph**, which
> assumed an **Ensoniq 5503 DOC** implemented as an MCU card. §12.3 below explains
> why the DOC is the wrong part for *this* workload even though it is the better
> part in the abstract, and §12.5 keeps the MCU card — with this document's register
> map — as the bring-up vehicle rather than the product.

> Superseded material — the IC-count re-tallies, the design-review corrections, the
> dropped digital sum and volume LUT — is archived in [history.md](history.md); this
> document describes only the present design.

---

## 0. Summary — the verdict in one table

| Question | Answer | § |
|---|---|---|
| **Discrete card, real Paula, a period sound chip, or an MCU?** | **Discrete card.** ⭐ **35 ICs** (§10) — **two** `ATF1508AS` for the logic, both fitted, back on one **100 × 180 mm** card. It reached 45 and 24 cm before programmable panning was given up and U1 absorbed the counter, the comparator and the read-back latch. | §12, §10.1, §10.2 |
| **Where does the sample data live?** | **Card-local SRAM, 512 KB in one `AS6C4008`.** The card never touches the bus for audio, and it cannot — there is no DMA pair on the backplane. | §5, §5.1 |
| **How are the four channels implemented?** | **One time-multiplexed datapath**, 8 slots per colour clock, state in a 32-bit-wide SRAM file. | §3 |
| **How is per-channel pitch generated?** | **Compare-against-a-free-running-counter**, not four down-counters. Kills 12+ ICs. | §4.2 |
| **What is the period reference clock?** | **3.546895 MHz — the Amiga PAL colour clock**, from a 28.37516 MHz crystal ÷8. Non-negotiable. | §4.1 |
| **How is volume applied?** | **By the other half of the converter.** The sample DAC's output is the *reference* of a second multiplying DAC whose code is the volume, so the product is formed in the analogue domain and is not quantised at all. No table, no multiplier, no boot upload. | §6.1 |
| **How are channels summed?** | **In the analogue domain, the way Paula does it** — one DAC per channel, its own I/V amplifier, and a two-resistor passive sum per side that *is* the fixed 4.4 kHz pole. **Fixed LRRL**: channels 0 and 3 to the left node, 1 and 2 to the right, which is wiring. No adder, no accumulator, no output sample rate, no resampling, no jitter. | §6.2 |
| **What DAC?** | **4 × AD7528** — dual 8-bit parallel multiplying DAC, on one die, with on-chip latches: **eight halves**, one sample and one volume converter per channel. Not a serial audio DAC — §6.3. **Samples are stored offset binary**, converted once by the loader — §6.1. | §6.3 |
| **Do we need the Amiga filter?** | **Yes, and not for nostalgia.** It is the reconstruction filter for channels running below ~16 kHz. Both filters, switchable. | §7 |
| **Where does mod tempo come from?** | **An on-card 16-bit timer clocked at colourclock/5 = 709.379 kHz — the Amiga's CIA clock exactly**, so `Fxx` BPM values are CIA-B-identical. Costs one slot, zero ICs. | §8.2 |
| **Which interrupt line?** | **`/FIRQ`.** Video's VBL owns `/IRQ`. A 6809 `FIRQ` is what a replayer tick should be. | §8.1 |
| **What does mod playback cost the 6309?** | **~2.7 % of a 2.098 MHz CPU** for the replayer, with a 19× worst-case margin; **~738 ms once** to upload 128 KB of samples — a ~500 ms `EORD` pass converting them to offset binary (§6.1, §16 item 27) plus a 238 ms chunked `TFM X+,Y` (§13.2). The `TFM` alone is 187 ms. | §13, [`modplayer.md`](modplayer.md) §7 |
| ⭐ **Where does the sound come out?** | **Two places, and they are different signals.** A **headphone-driven** 3.5 mm stereo jack on the card's rear edge (an `NJM4556AD`, 70 mA), and a **line-level** pair on the backplane. | §7.1 |
| **What does this card do that Paula cannot?** | No minimum period; 8 channels at half period resolution; a programmable volume curve (host software — §6.1). ⚠ **Programmable panning was given up on 2026-09-09** — it cost six packages against the two it was pitched at, and classic MOD is hard-panned anyway (§11.1). | §11 |

⭐ **Net: 35 ICs, on a 180 mm card.** The logic is **two** `ATF1508AS` — **U1**, the
host register block, and **U2**, the sequencer (§10.2) — and **the card is simulated end
to end**:
`audio_tb` writes a channel's `LC`/`LEN`/`PER` through the host port, enables it with
`DMACON`, and watches a sample byte come out of card RAM, through `PEND`, through a
converter port register and into an `AD7528`, with the buffer reloading from a shadow
the host rewrote mid-play. Thirteen of the 45 are datapath and glue packages §10's
table had never counted; §10.2.2 enumerates every one. One
oscillator, **one internal clock domain and an asynchronous host port** (§9.4), no bus
mastering, no `/WAIT`, and **no tight path at all**: the fastest thing on the card is a
state-file read at 30 ns inside a 35.24 ns slot, on a part already specified at that
grade.

**E-rate compatibility.** The card is **unaffected by the machine's E rate**. Every
audio-timing figure in this document is referred to the card's own 28.37516 MHz
crystal, not to E; the register port is asynchronous to E by construction (§9.4);
and §9.3's prefetch means there is no `/WAIT` path to close at any rate. The machine
is specified at **E = 25.175/12 = 2.0979 MHz and only that rate**
([`machine.md`](../../docs/machine.md)). The divide-by-8 **fast-E** rate (3.1469 MHz) is
experimental and not guaranteed elsewhere in the machine, but nothing on this card
breaks at it and the two figures that move both move the right way: §13.2's 128 KB
`TFM` falls from 187 ms to 125 ms — and its all-in load, §16 item 27's conversion pass
included, from ~738 ms to ~492 — and §9.4's register-tearing windows shrink by a
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
argument above is sound — 126,000 accesses per second against 18 M/s is not a memory
system. What it does *not* price is **state**: the per-channel pointers, the
host-visible counters, the converter port registers and the host-boundary staging,
which is where §10's honest package count actually goes. A card can be enormously
oversupplied in time and still cost 32 packages, and this one does.

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
Slots 5–7 are where the rare, expensive work goes — at most 126,000 channel events per
second, **seven work slots each** (§10.2.3), against **10.64 M work slots per second**:
a **12× margin** at ProTracker's top note and **3.2×** at §4.3's extended floor.
§10.2.5 has the table, and `audio_tb` counts the seven rather than asserting them.

### 3.2 The pipeline

Each slot is three pipeline stages, one slot deep each, exactly the shape of the
video card's `index latch → LUT → output latch`:

```
  stage A  (35 ns) : state-file read  -> {NEXT[15:0], PEND[7:0]}   = 24 bits
  stage B  (35 ns) : compare NEXT vs the free-running counter
  stage C  (35 ns) : on a hit, mark the channel due and queue it for slots 6-7
```

**The pipeline is three stages, and there is no table lookup in any of them.** `PEND` is the sample byte this channel's converter will take at its
*next* event, fetched in advance by the deferred slots. The per-colour-clock walk does
one 24-bit SRAM read, one 16-bit compare, and — on the ≤126,000 occasions per second
when the compare hits — sets one flag. Nothing else.

**Three things fall out, and the third is the one that matters.**

- **The card has no tight path.** Nothing in the walk but a state-file read
  and a compare: 10 ns of address setup + 12 ns of `IS61C6416AL-12` + 5 ns of setup =
  **30 ns inside a 35.24 ns slot**, on the part already specified.
- **The converters are written on events, not on colour clocks.** Each `WR` line sees
  ≤126,000 pulses per second where a per-colour-clock refresh would see 3.5 M — **a
  28× cut in digital switching** immediately beside the analogue section, on the card
  whose one genuinely new risk is exactly that (§16 item 9), and against a converter
  whose glitch impulse is 32× the 12-bit alternative's (§6.3).
- **The sample path is jitter-free.** The event-instant work is a flag and a fixed
  write window, so the converter's input changes on the exact colour clock the sample
  changed on — the property §6.2's latency argument rests on.

**The refill has slack, and §10.2.3 says how much.** After a hit the work slots
fetch the next sample byte from card RAM, advance `PTR`/`CNT` (and reload from
`LC`/`LEN` when the buffer ends — §3.3), and write the byte into `PEND`: **seven slots,
and eleven at a buffer end**. Each is a read-modify-write of one state-file word, and a
read-modify-write is two slots. The next event on that channel is at least 30 colour
clocks away even at §4.3's 118 kHz extreme, which is **90 work slots**; four coincident
channels need **twenty-eight**, so the queue drains in ten colour clocks and the
throughput floor is `PER` ≥ 10 (§10.2.5).

**And a volume write does not wait for a sample event.** `VOL` goes to the volume
converter, not through `PEND` (§6.1), so a host write queues its own deferred write to
that channel's volume half and takes effect within about a microsecond.

### 3.3 The channel state, and the shadow that makes mods work

Per channel, in the 32-bit-wide state file:

| Field | Bits | Written by | Meaning |
|---|---|---|---|
| `LC` | 19 | **host** | shadow location — where the *next* buffer starts |
| `LEN` | 16 | **host** | shadow length, **in words**, Paula-identical |
| `PER` | 16 | **host** | period, in colour clocks |
| `VOL` | 7 | **host** | 0–64 — **seven bits**, per §6.1's correction. **The left code** since §11.1 |
| `PAN` | 7 | **host** | 0–64 — **the right-hand code** (§11.1). Ignored unless `ACTRL` b5 is set, so a Paula-exact replayer never writes it |
| `PTR` | 19 | sequencer | current byte pointer |
| `CNT` | 17 | sequencer | bytes remaining in the current buffer |
| `NEXT` | 16 | sequencer | colour-clock count at which this channel next ticks |
| `PEND` | 8 | sequencer | **the sample byte the converter will take at the next event** — §3.2 |
| flags | 4 | both | DMA enable, attach-period, attach-volume, IRQ pending |

**The packing is not arbitrary.** Word 0 of each channel holds exactly
`{PEND[7:0], NEXT[15:0]}` = **24 bits**, which is why stage A of §3.2 needs one access
and not two, and why the walk needs nothing else. The 19-bit `PTR` still comes off a
single word in one read, which is what keeps the sample-RAM address path free of a
latch — and, since §9.5, the host-visible counters with it. **The file is 32 bits wide
in two `IS61C6416` packages** (§5.3); the eight bits above `PEND` are spare.

Everything the per-colour-clock walk touches is in that word, and everything else is
read only in the deferred slots. **The rest takes five more words, not two** — the
fields above are 105 bits and three 32-bit words are 96 — so the file gives each channel
**eight**, which is what makes the word address `{ch, w}` and costs nothing at 64 words
of 65,536. §10.2.1 is the layout; freeze it with the register map (§9.3).

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

- **No multiplier anywhere.** Volume is the second half of the converter (§6.1), not
  an 8×6 multiply — the product is formed in the analogue domain.
- **No adder in the audio path.** The channel sum of §6.2 is two resistors, not logic.
  The only adder on the card is the shared 16-bit `'283` chain of slots 6–7, and
  nothing in the sample path waits on it.
- **No divider anywhere.** Period is a divisor applied by comparison (§4.2), never
  computed.
- **No FIFO, no buffering, no DMA arbitration.** Sample memory is card-local and
  200× oversupplied (§2), so there is nothing to arbitrate.
- **No output sample rate.** §6.2.

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
  on a hit: PEND <- next byte;  NEXT <- NEXT + PER   (mod 65536)     (shared adder, slot 6-7)
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

⚠ **And there is a floor, at `PER` = 10.** §10.2.5's micro-ops are seven work slots
per channel event against three work slots per colour clock, so four channels at
`PER` < 10 ask for more slots than exist. `PER` = 0 or 1 — which §4.2 wanted clamped in
the sequencer, and which Case A's U2 cannot see (§16 item 31) — is the pathological case
of it. **The rule is the host's: never write `PER` < 10.** No replayer can: ProTracker's
own table stops at 113, and the sample-offset and portamento commands cannot take it
below 113 either.

**Do not emulate the floor**, but document it: a module that plays correctly here
at `PER` = 60 will not play on an Amiga, and software written against this card's
extended range does not port back. This is the same posture
[`graphics.md`](../../video/docs/graphics.md) §6.4.2 takes for the 8bpp tilemap — a deliberate,
stated superset rather than a silent divergence.

---

## 5. Sample memory: on the card, 512 KB, and one package

Paula DMAs from chip RAM. The three options here:

| Where | Bus cost | Verdict |
|---|---|---|
| **Card-local SRAM** | **zero** — the card is bus-passive except for register writes | **This.** |
| System RAM over the backplane | 4 × 28.6 kHz × 1 B = 114 KB/s = **5.4 % of a 2.098 MHz bus** | Cheap in *bandwidth*, and **there is no mechanism** — §5.1 |
| The video card's 512 KB VRAM | shares a scheduled resource | **Ruled out** — [`graphics.md`](../../video/docs/graphics.md) §17 already rejects this for the DOC card, and every word of that reasoning transfers. |

### ⭐ One `AS6C4008`, and the three spare footprints go away

**Decided 2026-09-08, alongside `graphics.md` §14.2's consolidation on the video card
and for the same reason: two of this card's four SRAM packages were *width and
expansion*, not capacity.**

| | was | **is** |
|---|---|---|
| Sample RAM | 1 × `AS6C1008` **128K×8**, footprints for 4 → 512 KB at **+3 ICs later** | **1 × `AS6C4008` 512K×8** — all 512 KB, **one DIP-32, today** |
| State file | 3 × `CY7C128A` 2K×8, 24 bits wide | **2 × `IS61C6416AL-12TLI` 64K×16**, 32 bits wide — §5.3 |
| **SRAM packages** | **4** (7 if the footprints were filled) | **3** |

⭐ **The `AS6C4008` is the part the motherboard just stopped using.** `hardware/ram.md`
§6.2 dropped the DIP system RAM for SIMM sockets, and its datasheet, footprint and
`hardware/lib/parts.ts` entry are all still in the repository with nothing citing them.
This card inherits the line item, so the machine's parts list does not grow — it moves.

| | `AS6C1008` | **`AS6C4008`** |
|---|---|---|
| Organisation | 128K×8 | **512K×8** |
| Package | 600-mil PDIP-32 | **600-mil PDIP-32** — same footprint, `A17`/`A18` on pins that were `NC`/`A16` |
| Access | 55 ns | 55 ns — and §9.5's address path has a whole 35.24 ns slot per access, so speed was never the constraint |
| Supply | 2.7–5.5 V, ~40 mA active | 2.7–5.5 V, ~40 mA active |
| **What it costs** | — | **nothing.** One package instead of one, four times the memory, and three reserved footprints deleted from the board |

**Is 512 KB enough?** It is more than enough, and now it is not an upgrade path:

| Sample data | Coverage |
|---|---|
| 64 KB | most early/chiptune modules |
| 128 KB | the large majority of the ProTracker corpus |
| **512 KB** | **everything, including the 8-channel and OctaMED material of §11.2** |

The host writes samples through an auto-incrementing `SPTR`/`SDATA` pair (§9), retired
in slot 5 — a posted write, exactly the discipline of
[`graphics.md`](../../video/docs/graphics.md) §3.1, and with far more slack. `SPTR` was
already 19 bits (§9.5) because the footprints implied 512 KB; **nothing in the address
path changes.** Upload cost is in §13.2.

### 5.1 ⚠ Sharing system RAM is not cheap-but-unwise, it is unavailable

The 5.4 % figure above has been quoted since the first draft as though bandwidth were
the objection. It is not, and the reason is worth stating once so nobody re-derives it:

- **This card cannot become a bus master.** `hardware/README.md` records that the
  backplane's last free position went to physical `A20` on 2026-09-08, and that
  `net.md` §13.1's **DMA request/grant pair lost that competition**. There are no pins.
- **`machine.md` §5 item 7's fixed-phase scheme is not a substitute.** It gives a card's
  engine one slot per bus cycle without a handshake — but it is *host*-facing, keyed to
  `CLK25` and `E`, and `machine.md` §5 item 10's rule is explicit that **a card's
  internal realtime scheduling must free-run on `CLK25` and not be derived from `E`.**
  This card's scheduling free-runs on something else again: its own 28.37516 MHz can
  (§4.1), which has no integral relationship to `CLK25` at all.
- **And the machine's memory is DRAM now** (`ram.md` §6), so a sample fetch would have
  to arbitrate against refresh as well as against the CPU.

**Card-local was the right answer for a bandwidth reason and is now the only answer for
three structural ones.**

### 5.2 ⚠ And the sample RAM does not move into `A20 = 1` either — priced at +3 ICs

`machine.md` §6 has carried an open item since the card regions were created: the
128 KB upload is a chunked `TFM X+,Y` into a *port*, which is exactly the tax
[`sdcard.md`](../../storage/docs/sdcard.md) and [`net.md`](../../net/docs/net.md)
stopped paying when their buffers became ordinary memory at `A20 = 1`. **Decided here,
and the answer is no.**

**The blocker is §9.5, and it is the same sentence that made the card cheap.** The
sample RAM's address has exactly one source — the state file's read bus, carrying `PTR`
when the sequencer fetches and `SPTR` when the host writes — and *because* there is one
source, §9.5's "address mux collapses from a mux into a chip-enable" and **the 19
address lines never enter the CPLD at all**. That is what keeps §10.1's I/O count at 57 of 64
I/O with room to be wrong by twenty.

A memory-mapped window needs a **second** source: the physical address bus, for
random-access reads and writes the host issues at arbitrary offsets.

| | |
|---|---|
| **19-bit 2:1 address mux** | **+3 × `74HC157`** — and it is the mux §9.5 deleted, put back |
| Into the CPLD instead? | **no.** 19 more pins on a part at 57 of 64 |
| Region size | ⚠ a card region is **64 KB** (`machine.md` §5 item 7) against 512 KB of sample RAM, so it needs a 3-bit bank register on top — free in the CPLD, but it means the window is *not* flat and a `TFM` still cannot cross a bank |
| **What it buys** | the doubled-write exposure of §9.4 and `modplayer.md` §4.4's conservative masking, deleted |

**+3 ICs to delete a software mask is not the trade this card should make**, and it is
a different trade from the one storage and net made: their buffers were *the* data path
and the port was in the way of every sector and every frame. This card's port is used
**once per module load** (§13.2) and never again.

> ⚠ **So the audio card is the last one in the machine carrying the `TFM`
> doubled-write exposure**, and it is not this card that retires it.
> [`sdcard.md`](../../storage/docs/sdcard.md) §11.6 is — the owner's choice about what
> this machine's 6309 does with `TFM` and an interrupt, which is firmware and costs
> zero cycles. Until that is settled, `modplayer.md` §4.4's masked upload loop stands.
> §16 item 0.

### 5.3 The state file is two packages, not three

§3.3 packs word 0 as `{NEXT[15:0], PEND[7:0]}` — **24 bits read in one access**, which
is why the state file was three `2K×8` parts. The width is real; the part count was an
artefact of nothing wider than ×8 being on the shopping list.

⭐ **`graphics.md` §14.2.1 put a ×16 part on it.** The `IS61C6416AL-12TLI` — 64K×16,
4.5–5.5 V, **12 ns**, TSOP-44 II, `/LB` and `/UB` byte enables, ~$3.28 and 1,470 in
stock — is the video card's palette LUT, and **two of them are a 32-bit state file in
two packages**:

| | 3 × `CY7C128A-15` | **2 × `IS61C6416AL-12`** |
|---|---|---|
| Width | 24 bits | **32 bits** — §3.3's field table calls the file 32-bit and it finally is |
| Access | 15 ns against a 35.24 ns slot | **12 ns** |
| Depth | 2K words, 128 used | 64K words, 128 used |
| Byte writes | one part per byte | **`/LB`/`/UB`, and the part select** — same granularity |
| Availability | ⚠ **Cypress, long out of production**; the DIP-24 grade is secondary-market | **current production, stocked** |
| **Packages** | **3** | **2** |

⚠ **The cost is surface mount**, and it is the same cost the video card took: TSOP-44 II
on a card whose other memory is a DIP-32 and whose logic is a socketed PLCC-84. Two SMD
parts on a hand-built analogue board is a real assembly decision — but the part being
replaced is the least available thing on the card, which is the argument
`graphics.md` §14.2.1 makes about the 15 ns DIP-28s and it transfers intact.

**What the eight extra bits are for: nothing, today.** Word 0 needs 24 and gets 32.
They are not spent, and §16 item 28 records that the obvious use — moving four of §3.3's
flag bits out of words 1–3 — has not been costed.

## 6. Volume, mixing, and the DAC

### 6.1 Volume is the other half of the converter

Paula applies a 6-bit volume to an 8-bit signed sample. In 1989 logic that is a
parallel multiplier (`TRW TDC1008`-class — expensive, hot, absurd at 126 kHz), or a
lookup table, or **the operation a multiplying DAC performs by definition**. It is
the third one.

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

A volume LUT would give a 12-bit product, at the price of an SRAM pair, a 15 ns
speed grade and a 65,536-byte boot upload. Here `VOL` = 1 attenuates the full 8-bit
sample by 36 dB instead of reducing it to a 12-bit value of ±2 — a better result,
reached by deleting the digital product rather than by widening it.

**The programmable volume curve is host software.** **`ACTRL` b3 = raw volume**: with
it set, `VOL` is an 8-bit attenuator code the host writes directly. A replayer that
wants a dB-linear law, a soft-clip or a per-machine calibration keeps a 65-byte table
and writes the mapped byte — one indexed load per volume change, in the tick that was
writing `VOL` anyway. The default (`ACTRL` b3 = 0) is `VOL` 0–64 with the card doing
the ×4, so the register stays Paula-identical and the acceptance test does not move.

**`VOL` is seven bits in the state file** (0–64 is 65 levels). With `ACTRL` b3 set it
is eight, and the sequencer stops shifting.

**Sample coding moves to the loader, and costs nothing there.** An 8-bit multiplying
DAC takes **unsigned** data, so a two's-complement sample byte would put full-scale
steps at every zero crossing (§6.3 — this is Aud-M1, and it is a property of the
converter). The fix is one `XOR #$80` per byte **in the loader** — §16 item 27,
decided there and nowhere else — which already walks every sample to relocate it
([`modplayer.md`](modplayer.md) §4). Samples live in card RAM **offset-binary**;
silence is `$80`. **The `.mod` converter of §13.3 does not flip this bit**; flipping it
twice is flipping it none.

**Silence is exactly zero.** At `VOLCODE` = 0 the volume DAC's ladder delivers no
current at all, so a silent or disabled channel contributes nothing — no half-scale
pedestal, no DC step at `DMACON` changes, and nothing for the output capacitor to
remove. A disabled channel forces `VOLCODE` = 0, one term in the sequencer.

### 6.2 The sum is analogue — and the currents really do sum at one node

Paula produces four independent current-output DACs and sums them at an analogue
node. There is **no output sample rate** anywhere in an Amiga's audio path — each
channel is a zero-order hold at its own rate, and the sum is continuous-time.

This card does the same, and it does it the way Paula does — **as currents at a
virtual ground** — because of one line in the AD7528 datasheet:

> `VREF A`/`VREF B` **Input Resistance Match: ±1 % max.**

That is the number the four-converter arrangement could not get. A current-mode
ladder's output scale is set by its reference resistance, which the AD7528 specifies
as **8 kΩ min / 11 kΩ typ / 15 kΩ max** — a ±30 % spread *between packages*, which is
why two ladders from separate dice summed into one I/V amplifier would sit up to
5.5 dB apart. Two ladders **on one die** match to 1 %: 0.09 dB, and it tracks over
temperature.

**So the pairing is by pair-of-channels, not by channel**, and since §11.1's panning
each pair has a volume package **per side**:

```
  AD7528 #1   DAC A = ch0 sample   DAC B = ch3 sample     -- the sample voltages
  AD7528 #2   DAC A = ch0 VOL      DAC B = ch3 VOL        --> OUT A + OUT B --> I/V --> L
  AD7528 #5   DAC A = ch0 PAN      DAC B = ch3 PAN        --> OUT A + OUT B --> I/V --> R

  AD7528 #3   DAC A = ch1 sample   DAC B = ch2 sample
  AD7528 #4   DAC A = ch1 VOL      DAC B = ch2 VOL        --> OUT A + OUT B --> I/V --> L
  AD7528 #6   DAC A = ch1 PAN      DAC B = ch2 PAN        --> OUT A + OUT B --> I/V --> R
```

**Four packages, eight halves: four sample and four volume.** Each side's two volume
ladders sit on **one** die, so the ±1 % on-die `VREF` match covers the whole summing
node and the extra amplifier pair programmable panning charged goes with it.

Within a die, both parts' `RFB` is tied to that amplifier's output. Paralleling the two
on-die feedback resistors halves the transimpedance, which is exactly the headroom split
Paula's four ladders make: **one channel alone reaches half of full scale, two at full
scale reach all of it** — and each channel still resolves all eight of its bits against
an unquantised product.

#### The write window, which is the only thing the digital side still owes

The AD7528's input latches are transparent while `CS` and `WR` are low and capture on
the rising edge, so the port must be stable across it. At `VDD` = 5 V over
temperature: **`tWR` 100 ns, `tDS` 90 ns, `tCS` 100 ns, `tAS` 100 ns, `tDH` 0 ns**.
The state file presents a channel's byte for one 35.24 ns slot, so the port needs a
register in front of it.

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
| **6** | **`AD7528`** | **12 converter halves**: one sample and **two** volume converters per channel (§6.3, §11.1) |
| 2 | `74HC574` | one 8-bit port register per side — each now driving three packages instead of two |
| 0 | — | volume LUT, adders, accumulators, output registers: **none** |
| — | 4 × 0.1 % resistor + passives | the pedestal cancellation of §6.3 |

**Hard panning is what the card does by default**, and it is a mode bit rather than a
wire: `ACTRL` b5 = 0 makes the sequencer drive the right-hand code from `VOL` by the
channel's Paula side, so ch0,3 land on L and ch1,2 on R and a Paula-exact replayer never
knows the other four halves are there. **Programmable panning is §11.1**, and it is
built.

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

| | Serial (`PCM56` / `TDA1541A`) | 4 × `LTC7545A` (the 12-bit alternative) | **4 × `AD7528`** |
|---|---|---|---|
| Packages, incl. registers | 4 DAC + 8 `'165` + divider ≈ **13** | 4 DAC + 8 `'574` = **12** | **6** |
| Volume | 2 × 32K×8 LUT | 2 × 32K×8 LUT | **in the converter** |
| Output sample rate | fixed, 192 kHz ceiling | none — event-driven | **none — event-driven** |
| Boundary jitter at `PER`=113 | ±5.2 µs (16 %) | 0 | **0** |
| Channel match across a summing node | n/a | ±30 % (`RREF` spread) → 4 amplifiers | **±1 %, on-die** |
| Product resolution | 16 bit | 12 bit, quantised | **8-bit terms, analogue product** |

(The 12-bit `LTC7545A`/`AD7545A` timing analysis that preceded the dual converter is
archived in [history.md](history.md); [`AD7545.pdf`](../../reference/datasheets/) and
[`LTC7545A.pdf`](../../reference/datasheets/) remain in the repo.)

**What the cascade costs against the 12-bit part, stated plainly — and it is glitch.**

| at `VDD` = +5 V | `LTC7545A` | **`AD7528`** |
|---|---|---|
| Digital-to-analogue glitch impulse | **5 nV·s** typ | **160 nV·s** typ |
| Current settling | 1 µs to 0.01 % | 350 ns typ / 400 ns max to ½ LSB |
| `VREF`-to-`OUT` feedthrough | 5 mV p-p @10 kHz | **−70 dB** (−65 over temperature) |
| Output leakage at zero code | — | ±50 nA (±400 nA over temperature) |

**32× more glitch energy per code transition**, and this is the one axis on which the
cascade is worse than the 12-bit alternative. Three things blunt it and none of them
make it go away: §3.2 cut the number of code transitions per channel from 3.5 M/s to ≤126 k/s;
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
cancel it — the polarity is the trap. `−Vref` is one amplifier channel off `Vref`
through a matched pair, and §7 has exactly one spare.

Four resistors and one amplifier is the whole analogue overhead, and it buys the
property everything downstream leans on: **because the cancellation happens upstream
of the volume DAC, the card's output is exactly zero at `VOL` = 0 and has no
volume-dependent DC anywhere.**

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

Parts: **3 × `TL074` + 1 × `TL072`** + **1 × `74HC4066`** + passives — **fourteen
amplifier channels, thirteen used**:

| Amplifier channels | |
|---|---|
| Sample-converter I/V — one per channel, each on its own die's `RFB` (§6.2) | 4 |
| `−Vref` inverter — the pedestal cancellation of §6.3 | 1 |
| Volume I/V — one per volume die, **two per side** since §11.1's panning | 4 |
| Voltage summer — combines a side's two dice through a matched 0.1 % pair (§11.1) | 2 |
| LED Sallen-Key stages, one per side | 2 |
| **Total** | **13 of 14 = 3 × `TL074` + 1 × `TL072`** |

The `TL074` is the same part in a quad package; an `NE5532` is the better op-amp and
equally period, and `TL07x` is specified here for supply-rail simplicity.

### 7.1 The output — two of them, and only one is line level

> ⭐ **Decided 2026-09-09.** §16 item 29 asked whether a line signal on a 3.5 mm
> connector was the right call. It is not, and the answer is **+1 IC**: the jack gets a
> headphone driver and the backplane keeps the line output. The two are different
> signals for different loads, which is what the single output was pretending not to be.

| | drives | level | path |
|---|---|---|---|
| **backplane `AUDIO_L`/`AUDIO_R`** | a line input, a mixer, a chassis jack | **~2 V p-p**, DC-blocked, 100 Ω series | straight off §6.2's summing amplifiers |
| ⭐ **3.5 mm stereo jack, rear edge** | **headphones, 16–300 Ω** | the same ~2 V p-p, at **70 mA of drive** | the same nodes, through the buffer below |

**The buffer: one `NJM4556AD`** — dual, **70 mA output**, DIP-8, and a JRC part from the
early 1980s rather than a modern one. It takes §6.2's two summing-amplifier outputs as
unity-gain followers, ahead of the line path's DC block, and gets its own coupling
capacitor and series resistor into the jack.

**The arithmetic, because "add a buffer" is not a specification:**

| | |
|---|---|
| Level | 2 V p-p is **0.707 V rms**. Into 32 Ω that is **15.6 mW**, against the 1–5 mW a comfortable listening level wants — headroom, not a compromise |
| Current | 0.707 / 32 = **22 mA rms**, ~31 mA peak per channel, against the part's **70 mA**. A `TL072` manages ~10 mA short-circuit and would clip into anything below ~200 Ω, which is the whole reason this is a different package |
| Series `R` | **10 Ω** — short-circuit protection and damping. Into 32 Ω it costs **2.4 dB** (20·log₁₀(32/42)); into a 10 kΩ line input, nothing |
| Coupling `C` | **470 µF** into 32 Ω is **10.6 Hz**. The line path's 10 µF into 100 kΩ is 0.16 Hz; a headphone load is 3,000× lower and needs the capacitor 47× larger. Getting this wrong is the classic thin-sounding headphone output |
| Supply | ⚠ **the analogue section's split rails, and this changes §16 item 25.** Ten more mA of quiescent current, and up to **~60 mA** into a low-impedance load on both channels at once — §10's estimate moves to **340–500 mA** |

⚠ **The rails are not the digital card's.** §6.3 blocks the sample converters' pedestal
rather than cancelling it downstream, so the signal between the I/V stage and the output
capacitor lives between 0 and −`V_REF` — which is why §16 item 25 exists at all. **This
part rides the same split pair**, and it makes that item bigger rather than merely adding
a consumer to it: item 25 calls the rail choice *"a rail decision that costs no
packages"* because everything on those rails is an op-amp signal path drawing
milliamps. **A 70 mA driver is not.** The negative rail now needs *current capability*
and not only a voltage, which is a regulator question rather than a reference question.

⚠ **The grounds meet at one point and this is the node that tests it.** `audio.md` §10
requires analogue and digital ground to meet exactly once; the jack is the one connection
on this card that leaves the board into something a person touches, and **a jack shell
bonded to a chassis is the classic way to make a second ground path.** Use an isolated
(plastic-bushing) jack, or bond the chassis at the same single point.

⚠ **What is given up.** A headphone amplifier on a board carrying three digital SRAMs, a
28 MHz oscillator and a CPLD is exactly what §7's earlier text refused — *"whatever drives
the machine's speakers is a separate concern and should not be on a card carrying digital
SRAMs"*. **That objection is not wrong; it is outweighed.** The alternative was a
connector that silently underdrives everything anybody plugs into it, and a card that
cannot be listened to on a bench without an external amplifier. The mitigation is
placement: the driver belongs in the analogue section §10 already wants physically
separate, next to the jack, not next to the CPLD.

**Why a jack on the card at all, decided 2026-09-08.** `graphics.md` §17 put `AUDIO_L`,
`AUDIO_R` and two dedicated `AGND` returns on the backplane, and
[`hardware/lib/slot.ts`](../../hardware/lib/slot.ts) carries them at B32–B35 — but
**nothing in the machine consumes them.** There is no chassis, no rear panel and no
document that says where the pair terminates. A jack on the card's rear edge is the
connector every other output on this machine already is (`place/parts.ts` gives video a
DE-15 and the I/O card its DE-9 and mini-DINs), and it makes the card testable on a bench
with no backplane at all. **The backplane pair is kept, unchanged** — it is the line
output now rather than the only output, and if the connector is ever re-specified
(`machine.md` §5 item 5) those four positions are the first candidates to reclaim.

⚠ **The footprint is a placeholder** — `hardware/cards/audio.circuit.tsx` draws a 3-pin
header, so the netlist is right and the outline is not. Same caveat as the slot socket,
`hardware/README.md` open item 2.

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

**`/FIRQ` needs an open-collector driver.** The backplane's `/FIRQ` is a wire-OR
([`graphics.md`](../../video/docs/graphics.md) §17): every source pulls low and a
single pull-up defines the high level, and a totem-pole output driving that line is a
bus fight with whatever else is asserting it, not a wire-OR. The six sources above
are OR-ed inside the CPLD — `FIRQANY`, §10.1.1 — and the pin uses the `ATF1508AS`'s
*Programmable Output Open Collector Option* (decision D9; on the six-GAL allocation
this needed a discrete `74HC07`, because a `GAL22V10`'s outputs are totem-pole). It
is the kind of omission that is invisible on paper and immediate on a bench.

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

⭐ **Implementation: it is a fifth entry in the compare structure of §4.2, serviced in
slot 4, and it shares the counter after all.** A CIA period of `N` ticks is exactly
`5N` colour clocks, so the timer's next-fire time can be kept **in colour clocks** —
`CIANEXT`, state word `$21` — and compared against the same free-running counter the
four channels use. The only arithmetic is `CIANEXT += 5 × TIMER`, once per period at
~50 Hz: **500 work slots a second, and zero additional packages.** `5N = 4N + N` is two
doublings and an add, and a doubling is `ALAT` and `BLAT` loaded from the same read, so
there is no shifter (§10.2.3 W4).

⚠ **The obvious implementation costs 13 % of the work-slot budget and this one costs
nothing**, which is worth stating because the obvious one is what this section used to
specify: a ÷5 prescale driving a 16-bit count that the shared adder increments every five
colour clocks is 709,379 increments/s × 2 slots = **1.4 M of 10.64 M**. The ÷5 prescale
itself is still on U1 and still exact — it is `CIACLK`, on a pin, because §8.2's claim is
that this card's tempo reference **is** the Amiga's and a bench should be able to see it.

Expose it as a plain 16-bit reload register (`TIMER`, §9.2) with an enable bit, so
it is equally usable as a general-purpose periodic interrupt for anything else
the machine wants at a rate `/IRQ`'s 70.09 Hz cannot give it.

**The enable bit is `ACTRL` b6** (decision D7). Without it the timer could be
started and never stopped: once `TIMER` holds a non-zero reload the compare in slot 4
fires forever, `AINTENA` b4 can mask the interrupt but not the timer, and there is no
clean "stop the music" path at all — not for a replayer shutting down, not for
`ACTRL` b7's master enable, and not for a NitrOS-9 process being killed. `ACTRL`
b6 = 0 holds the
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

Decode is from the backplane's `/IOSEL` — the `$FF00`–`$FF7F` window strobe, common
to every slot — and the card completes it from `A0`–`A6`.
[`machine.md`](../../docs/machine.md) §2 owns the window assignment.

**`SEL = /IOSEL & A6 & !A5 & !A4`**, on U1 —
[`hardware/gal/audio.cpld.ts`](../../hardware/gal/audio.cpld.ts), and `audio_tb` sweeps
all 128 addresses of the geographic window and asserts that exactly sixteen select the
card.

⚠ **Seven bits, and `A6` is the one that matters.** The geographic window is 128 bytes,
so `/IOSEL` does not imply `A6`: a card matching only `A5`–`A0` answers at its base
**and 64 bytes below it**, and two cards driving `D0`–`D7` at once is silent.
`graphics.md`'s `REGSEL = /IOSEL & A6 & A5` carries the same three literals for the
video card. **The base is fixed in the decode, not jumpered** — a jumper costs two pins
and a mux term on a part with seven pins left, and `machine.md` §2 assigns the window
anyway. [history.md](history.md) has what this section said before 2026-09-09.

### 9.2 The direct window — 16 bytes

| Off | Name | R/W | Function |
|---|---|---|---|
| `+$0` | `AIDX` | W | state-file index; writing it **prefetches** that entry (§9.3) |
| `+$1` | `ADATA` | R/W | state-file byte at `AIDX`, **post-increment** |
| `+$2` | `ADMACON` | W | b3..0 channel DMA enable. **b7 = set/clear**, Paula's `DMACON` convention |
| `+$3` | `AINTENA` | W | b5..0 interrupt enables (§8.1). Same b7 set/clear convention |
| `+$4` | `AINTREQ` | R/W | read: pending flags. write: **b7 = 0 clears** the bits set in b5..0; **b7 = 1 sets** them, Paula's `INTREQ` convention |
| `+$5` | `ACTRL` | W | b0 LED filter, b1 filter bypass, b2 NTSC clock, **b3 raw volume** — `VOL` is an 8-bit attenuator code instead of Paula's 0–64 (§6.1), **b4 8-channel mode** (§11.2), **b5 pan enable** (§11.1 — 0 is Paula's hard pan and is the reset state), **b6 tempo-timer enable** (§8.2), b7 master enable |
| `+$6`–`$8` | `SPTR` | W | sample-RAM pointer, 19 bits, auto-increment |
| `+$9` | `SDATA` | R/W | sample-RAM byte at `SPTR`, **post-increment** — a **side-effecting port**, see the `TFM` note below |
| `+$A` | `ASTAT` | R | b3..0 channel DMA active, b4 timer running, b5 reserved (reads 0), **b6 posted-write busy**, **b7 prefetch valid** — b6/b7 defined below |
| `+$B`–`+$C` | `TIMER` | W | tempo-timer reload, 16 bits, clocked at **709,379 Hz** — load `1773447 / BPM` (§8.2) |
| `+$D`–`+$F` | — | — | **reserved, reads 0** |

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

**Three bits of the map, defined precisely.**

| Bit | Definition | Behaviour on this machine |
|---|---|---|
| `ACTRL` b4 | **8-channel mode** (§11.2) | **b4, unambiguously** — decision D7. `card.h` follows the document, not the other way round: §9.2 is the deliverable. |
| `ASTAT` b6 | **posted-write busy** — 1 while the depth-1 sample-RAM posted write of §5 has not yet retired in slot 5. A further `SDATA` write while b6 = 1 is lost and sets `AINTREQ` b5 (§8.1). The path is depth 1, so "busy" is the honest word. | It can only ever read 1 to a host faster than 3.55 M/s: a 6309 store takes ~5 E cycles = 2.38 µs, and the retire takes 281.9 ns, so on this machine b6 reads 0 every time it is polled. It exists for the MCU card and for bring-up. |
| `ASTAT` b7 | **prefetch valid** — 1 when the `ADATA`/`SDATA` prefetch latch (§9.3) holds the byte for the *current* index. Cleared by a write to `AIDX`/`SPTR` and by the post-increment; set when slot 5 retires the prefetch. | The same arithmetic as b6 from the other side: the prefetch completes within one colour clock (281.9 ns) and the soonest a 6309 can look is 2.38 µs later, so **b7 reads 1 every time this machine polls it** and §9.3's "reads never stall" holds. It is not a handshake the 6309 has to honour; it is the observability that makes that claim checkable on a logic analyser, and it is a real handshake for any host fast enough to need one. |

### 9.3 The state file — index/data, and why that is not a cost

Per channel, `AIDX` = `channel × 16 + offset`:

| Offset | Name | Bytes | Paula equivalent | Note |
|---|---|---|---|---|
| 0–2 | `LC` | 3 | `AUDxLC` | **byte** address into card RAM |
| 3–4 | `LEN` | 2 | `AUDxLEN` | **words**, Paula-identical — mod length fields load unchanged |
| 5–6 | `PER` | 2 | `AUDxPER` | colour clocks. ⚠ **Never write `PER` < 10** — §4.3, §16 item 31 |
| 7 | `VOL` | 1 | `AUDxVOL` | 0–64 |
| 8 | `DAT` | 1 | `AUDxDAT` | direct sample write, CPU-fed mode (§1 req. 8) — **offset binary**, like everything else the converter sees (§6.1) |
| 9 | `ATT` | 1 | `ADKCON` bits | b0 attach-period, b1 attach-volume (§11.3). **Channel 3's bits are ignored** — there is no channel 4 and no wrap to channel 0 |
| 10 | `PAN` | 1 | — | **the right-hand volume code, 0–64** (§11.1). Ignored unless `ACTRL` b5; **the converter halves it drives are built** |
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

**That latch is a package: 1 × `74HC574`** (§10). The prefetch holds one byte of
state-file or sample-RAM data for the host to read at its leisure, and it is distinct
from the posted-write **data** latch on the opposite path, host → sample RAM — two
registers on two different buses.

**And that latch is `ADATA`/`SDATA`'s read-back path — the `74HC245` is deleted.** A
`'574` is an octal flip-flop *with three-state outputs*, so it drives the host data bus
itself; U1 supplies its enable, `PFOE`, asserted at `+$1` and `+$9` on a read and
nowhere else. **`ASTAT` and `AINTREQ` come off U1 instead**, on `D0`–`D7` as
bidirectional I/O macrocells — the same eight pins the register writes arrive on, with
an output driver and an `.oe` behind them. A `'245` would buffer sources that can
already drive the bus.

**It costs eight logic cells and one pin**, and it is what makes §8.1's interrupt
protocol — "read `AINTREQ`, then clear what you saw" — executable at all.
[`hardware/gal/verilog/audio_tb.sv`](../../hardware/gal/verilog/audio_tb.sv) reads both
registers and asserts the bus floats everywhere else. [history.md](history.md) records
that none of it was built until 2026-09-09.

**It is three `'574`s, not one** — one per state-file byte lane. Which lane a host byte
lives on is a function of `AIDX` (§10.2.1), so a single latch would need a four-to-one
multiplexer on eight bits, which is four `74HC153`. Lane 3 is unpopulated, which is what
makes it three rather than four.

⭐ **And the path now exists for the machine's card-ID byte.** `machine.md`'s planned
per-card identification byte is a constant driven onto `D0`–`D7` on a read of one
address; U1's bidirectional macrocells already do exactly that for `AINTREQ` and `ASTAT`,
so on this card the ID is a decode and eight product terms and **no new pins at all**.

The one thing left to confirm is drive: `74HC` sources 6 mA and an `ATF1508AS` output
more, so the backplane loading rule has to be met by the flip-flop directly — a check,
not a change (§16 item 26).

### 9.4 Crossing the host boundary

The card has one internal clock domain — everything downstream of the 28.37516 MHz
crystal — and an asynchronous host port. Host writes arrive a byte at a time from an
asynchronous 2.098 MHz E bus, where Paula's do not: a 68000 writes `AUD0PER` in one
bus cycle, atomically, which is why no Amiga document has this section. This card
needs it.

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

**Cost: nothing — the staging is a shadow word in the state file** (§9.5 makes the same
move for the host counters). Each channel's arriving bytes land in a shadow word at
`AIDX | $40`; the committing byte triggers one deferred-slot copy of shadow → live. The
widest field is `LC` at 3 bytes, so a 32-bit shadow word covers every field in the table
with room to spare, and the copy is the same read-hold-write the deferred slots already
do for the `LC`/`LEN` reload of §3.3.

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
clocks (564 ns) against a host that cannot return for 2.38 µs, so it is free. The
three synchronisers — write strobe, read strobe, and `E` itself for edge detection —
are six registered cells in the CPLD (§10.1.1; on the six-GAL allocation they were a
`74HC174`).

#### 9.4.5 Reads of registers the slot logic is writing

Two registers change underneath the host: `AINTREQ` (slot logic sets request bits) and
`ADATA` (slot 5 refills the prefetch latch).

⭐ **`MERGE = CCLK & !SYNCR2 & !SYNCR1`** — every colour clock, suppressed while a
synchronised host read of `AINTREQ` is in flight. `audio_tb` walks a host read across
all sixteen slot phases, raises a request in the middle of each, and asserts it survives
every one.

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

| State | Bits | Lives in |
|---|---|---|
| `SPTR` — sample-RAM pointer, 19-bit auto-increment | 19 | **the state file, word `$22`** — incremented by the shared `'283` in a work slot (§10.2.1) |
| `AIDX` — state-file index, 6-bit auto-increment | 6 | ⛔ **six registers on U2, loaded from `D0`–`D5`.** It cannot live in the state file: the sequencer would have to read the index to compute the address of the byte the index names. §10.2.1 |
| `INTENA` | 6 | **U1**, built |
| `INTREQ` + the 6-bit pending register (§9.4.5) + `/FIRQ` | 13 | **U1**, built — the block that fits no `GAL22V10`, below |
| `DMAEN` | 4 | **U1**, built |
| Tempo ÷5 prescale + timer enable | 4 | **U1**, built. ⚠ The timer's *compare and reload* are U2's (§8.2, §10.2.3 W4) |
| Slot counter | 3 | **U1**, built |
| Host decode, read-back path, synchroniser control | — | **U1**, built (§9.1, §9.3) |
| Deferred-work queue + enable-priority term (§16 item 13) | ~6 | ⚠ **U2** — §10.2, specified |
| Sequencer state machine, stage control, state-file address | ~30 | ⚠ **U2** — §10.2, specified |

> ⚠ **The interrupt block fits no `GAL22V10`, in either arrangement — which is what
> took the card's logic to §10.1's CPLDs.** Fitted 2026-09-07 —
> [`hardware/gal/audio.jedec.ts`](../../hardware/gal/audio.jedec.ts),
> `npm run check:audio`. Whole, the block is `INTREQ`(6) + pending(6) + `/FIRQ` =
> **13 equations for 10 macrocells**. Split, with the pending register on its own
> part, the six `PEND` bits stop being internal and the `INTREQ` part needs **17
> input pins where a `GAL22V10` has 14** — 11 dedicated, plus three macrocells not
> used as an output. Both refusals are asserted by `check:audio` with the fitter's
> own arithmetic, so the squeeze is recorded rather than remembered. The other four
> blocks fit — `aseq` 10/10, `adec` 10/10, `admat` 8/10, `aintena` 6/10 — and the
> pending register alone fits at 6/10, which is why a GAL allocation is **six**
> parts, not five. A pending register that is merged on a clock edge is not state
> the state file can hold, so unlike the counters it has nowhere else to go.

**Where the host-visible counter bits live: in the state file, in two of the words
§10.2.1 leaves spare.** An auto-increment is exactly the operation the deferred slots already
perform on `PTR` and `CNT`:

```
  host store to SDATA:
    deferred slot A : read state word $21          -> SPTR on the read bus
                      the read is HELD for this slot and the next
                      sample RAM /WE with the address off that same bus,
                      data from the posted-write latch
    deferred slot B : shared '283 computes SPTR+1 from the held bus
                      write it back to word $21
```

**Two slots per host write, and the address bus needs no latch** — the state file's own
SRAM outputs hold the address for as long as the sequencer holds the read, which is the
whole reason a deferred access is allowed two slots. This is the same trick the `PTR`
fetch path uses; the counters simply stop being a special case. Host-visible counters
are state and increments; the card is made of state and increments.

**The sample-RAM address has one source.** It is the state-file read bus — `PTR`
when the sequencer fetches, `SPTR` when the host writes — and nothing else drives it.
The "address mux" collapses from a mux into a chip-enable, and the 19 sample-RAM
address lines are board wiring between two memories that never enter the logic —
which is what keeps §10.1's I/O count where it is.

⚠ **And the two memories' control lines have exactly one source too, U2.** The host's
`+$1` and `+$9` decodes are `HSFREQ`/`HSRREQ` — *requests* that the sequencer retires in
slot 5, **not chip enables**. The names matter here and are not cosmetic: a decode named
for a memory pin, on a card whose sequencer drives that same pin every slot, is one name
with two meanings and two drivers on one `/CE`. [history.md](history.md) has the
rename.

**What it costs.** The two increments contend with channel work for the shared adder:
≤126 k channel events/s × ~4 slots plus ≤400 k host stores/s × 2 slots is **≈1.3 M of
7.1 M deferred slots — a 5× margin**, and the host figure is the 6309 saturating the
port with `TFM`, which only happens during the §13.2 upload. `SPTR` is 19 bits against
a 16-bit adder chain; the top three bits are a carry-in increment in the sequencer.

## 10. Chip budget

| Qty | Part | Role |
|---|---|---|
| **1** | **AS6C4008-55 (512K×8)** | **sample RAM — all 512 KB in one DIP-32, §5** |
| **2** | **IS61C6416AL-12 (64K×16, 12 ns, TSOP-44)** | channel state file, **32 bits wide** — `{NEXT[15:0], PEND[7:0]}` in one read (§3.3, §5.3) |
| 4 | 74HC283 | shared 16-bit adder — `NEXT`+`PER`, `PTR`+1, `CNT`−1 (slots 6–7) |
| **2** | **74HC574** | **`ALAT` — the adder's A operand, off the state-file read bus (§10.2.2)** |
| **2** | **74HC574** | **`BLAT` — the adder's B operand: `PER`, or `LEN` for the doubling (§10.2.2)** |
| **2** | **74HC244** | **B = `$FFFF`, three-stated onto the B bus, so `A−1` is `A + $FFFF` (§10.2.2)** |
| **2** | **74HC244** | **`SUM` → the state file's data bus; the `'283` outputs are totem-pole (§10.2.2)** |
| **1** | **74HC574** | **`SBLAT` — the sample byte, held from its fetch slot to its `PEND` write (§10.2.3)** |
| **2** | **74HC574** | **converter port register, one per side — 8 bits, loaded twice per frame (§6.2). ⚠ §10.2.2 asks whether it is one per channel** |
| **4** | **AD7528** | **dual 8-bit parallel multiplying DAC, on-chip latches — eight halves: one sample and one volume converter per channel (§6.1, §6.3)** |
| **2** | **TL074** | **sample I/V ×4, volume I/V ×2, LED Sallen-Key ×2 (§7)** |
| **1** | **TL072** | **`−Vref` inverter (§6.3); one channel spare** |
| 1 | 74HC4066 | filter select / bypass (§7) |
| 1 | 74HC574 | posted-write data latch (host → sample RAM) |

| **1** | **`ATF1508AS-…JC84`, PLCC-84, socketed — U1** | the host register block: §9.1's seven-bit decode, `ADMACON`, `AINTENA`, `AINTREQ` and its pending register, `/FIRQ`, `ACTRL`, the synchronisers, §9.3's read-back path, the slot counter and the ÷5 prescale. **Fitted at 89 of 128 cells and 57 of 64 I/O** (§10.1.1) |
| **1** | **`ATF1508AS` — U2** | ⚠ **the sequencer — specified in §10.2, not fitted.** ~69 I/O and ~74 cells; the package is §10.2.6's open decision |
| 1 | 28.37516 MHz osc | PAL Amiga master (§4.1) |
| (1) | (28.63636 MHz osc) | (NTSC, socketed option, §4.1) |
| — | 3.5 mm stereo jack | **headphone output on the card's rear edge — §7.1.** The backplane pair is the line output and is a different signal |
| — | R-2R / passives | filter networks, offset-injection resistors (§6.3), output stage |
| **1** | **NJM4556AD** | **headphone driver for the 3.5 mm jack — dual, 70 mA output, DIP-8 (§7.1)** |
| **35** | | **(36 with the NTSC can)** |

⚠ **45, and thirteen of them arrived on 2026-09-09.** The table carried 32 while the
sequencer was a paragraph. Seven came from enumerating the datapath §3.2, §4.2 and §9.5
already describe — U2, the adder's two operand latches, the `$FFFF` constant, the
three-state path from the sum back to the file, and the sample-byte hold. **Six more came
from building it**, and they are the ones worth naming, because each answers a question
the enumeration could only ask: two more converter port registers (§6.2's windows collide
with the walk order), two more prefetch latches (§9.3's read-back path is one per
state-file byte lane), a `74HC138` for §10.2.6's lever, and a `74HC00` to gate the write
enables with the slot clock's second half. ⚠ **The analogue side is still an enumeration
and not a layout** — §16 item 19.

### 10.1 Two CPLDs, and why the counter and comparator stay outside

**Case A decided 2026-09-07**, from `npm run census:audio`: the counter and the
comparator stay outside the logic, because §4.2's comparator reads `NEXT` off the
state-file bus — leave it outside and those 24 bits never enter the part, absorb it
and they all become inputs.

| | Absorbed | Macrocells, est. | External I/O, est. | PLCC-84 |
|---|---|---|---|---|
| **A — chosen** | 6 GALs + `'273` + `'174` + `'07` = **9 → 1** | ~61 | ~48 | **fits** |
| B | also the `'590` counter and `'688` comparator = 13 → 1 | ~81 | ~72 | 4 pins short |

*(Both columns are the 2026-09-07 census's estimates, kept because they are what
decided Case A. §10.1.1 has what the fitter actually reports.)*

⭐ **And the logic is TWO parts, decided 2026-09-09 — for pins, not macrocells.**
`npm run census:audio` enumerates the sequencer's interface at **~69 I/O against the
seven U1 has left**, and merging the two blocks onto one die does not rescue it: the
merge saves the ~31 crossing nets and then wants **~143 logic cells**, and no
`ATF1508AS` has more than 128. The split saves cells and spends pins; the merge saves
pins and spends cells. There is no one-part arrangement of this card.

| | holds | fitted |
|---|---|---|
| **U1** `ATF1508AS` PLCC-84, socketed | the host register block — §9.1's decode, `ADMACON`, `AINTENA`, `AINTREQ` and its pending register, `/FIRQ`, `ACTRL`, the `AINTREQ` read synchroniser, the slot walk, the ÷5 tempo reference — **plus §4.2's free-running counter and comparator and §9.3's read-back latch**, which is seven packages for sixteen pins | **88 of 128 cells, 62 of 64 I/O** — §10.1.1 |
| **U2** `ATF1508AS` PLCC-84, socketed | the sequencer — §10.2 | ⚠ **128 of 128 cells, 60 of 64 I/O** — §10.2.6 |

⚠ **U2 IS EXACTLY FULL AND U1 IS NOT**, which is the whole shape of this card's logic
and the reason every reduction moved work *towards* U1. "Design fits successfully" on
both: U2 at **128 of 128 cells**, 60 of 64 I/O, 65 foldback nodes, 21 cascades and 449
product terms; U1 at **88 of 128 cells**, 62 of 64 I/O, 22 foldback, no cascades and 274
product terms. A **TQFP-100 was tried and does not help**: it takes the
pins from 62 of 64 to 62 of 80 and leaves the cells at 128 of 128, because both packages
carry the same 128 macrocells. So the PLCC-84 is the right package — it keeps the socket
and the TQFP-100 would buy eighteen pins the design does not need — and **there is
nothing left on U2 for anything else**, §16 item 7's 8-channel mode included.

⚠ **JTAG is off on U2**, which is the four pins that made it fit: 62 of 64 against 62 of
60. Both parts are programmed out of circuit, so this is the arrangement the card already
had (§10.1.1), not a concession.

**What does not move, and never could:** the three SRAMs, the four `AD7528` multiplying
DACs, the three op-amps, the `4066`, the oscillator and every passive. This is an
analogue card with a digital corner, and the CPLDs are the corner.

#### 10.1.2 What the part does not contain (superseded 2026-09-09; see history.md)

The list of blocks this section carried is now §10.2's work breakdown, in the present
tense and with a package and a pin budget behind it.

#### 10.1.1 U1, fitted — refitted twice on 2026-09-09

`hardware/gal/cpld/audio.jed` exists: **`ATF1508AS`, PLCC-84, "Design fits
successfully".** One command regenerates it —
`hardware/gal/prjbureau/fit1508.sh gal/audio.pld` — through Atmel's own CUPL and
`fit1508.exe` under Wine, on Linux, with no vendor tooling beyond what
`extract-wincupl.sh` pulls out of the WinCUPL installer.

| | |
|---|---|
| logic cells | **88 of 128** — with the counter, the comparator and §9.3's read-back latch aboard |
| I/O pins | **62 of 64**, JTAG off — 20 in, 45 out, and `SD0`–`SD15` and `D0`–`D7` are bidirectional |
| product terms | 274, 22 foldback nodes, no cascades |
| dedicated inputs | 2 of 4 — `SLOTCLK` and `RESET` |
| `SLOTCLK` | pin 83, a **global clock** — the fitter chose it |
| `RESET` | pin 1, the **global clear** |
| fitter passes | 1 failed placement; 2 succeeded with cascade logic |

⭐ **U1 got smaller when U2 arrived and then spent all of it.** It fell to 77 cells and
46 pins when the host handshake moved to U2, and the 2026-09-09 reduction spent every one
of those: sixteen state-file data pins bought **seven packages** — the `'590` counter, the
`'688` comparator and §9.3's three prefetch `'574`s — because all three want the same bus.
**Both parts are now full**, which is the honest state and the constraint on anything
added next.

⛔ **Sixteen bits of equality is where that twice went wrong, and the second time is the
one worth keeping.** Written as four nibble-equalities ANDed together it looks like 64
product terms — but a combinational intermediate in CUPL is *substituted* rather than
given a macrocell, so it multiplies four 16-term sums into **65,536**, and the fitter ran
seven minutes on it. Inverting it fixes the term count: **inequality is a sum**, two
terms per bit, thirty-two in all.

⛔ **And as one macrocell that still does not place.** Thirty-two terms reading sixteen
`SD` pins *and* sixteen counter registers is **32 signals into one logic block**, against
the 40 an `ATF1508AS` LAB takes from the switch matrix — the family's third limit, after
cells and pins, and the fitter was **killed** trying. Cells were never the constraint:
this part is smaller than U2 and the `.pld` is shorter.

⭐ **Halved, it places in two minutes and gets *smaller*.** `NEQL` and `NEQH` are sixteen
signals and sixteen terms each, and each is a **pin** — two combinational nodes would only
be substituted back into one. U2 forms the hit as `!NEQL & !NEQH`, which its array does
for nothing. The part went from unplaceable to **88 of 128 cells**, because the 32-term
version had been forcing foldback across the whole design.

**The source is generated, not written twice.** `hardware/gal/jedec/cupl.ts` emits the
`.pld` from the same `Cell` term lists that `check:audio` exercises on six GAL22V10s,
so the CPLD and the GAL fits have one origin. Writing the CUPL by hand would have made
a second source with nothing comparing it against the first — which is exactly how two
errors got into the 22V10 fuse map on 2026-09-06.

Three of the merge's wins are visible only once the parts are one part:

- **`FIRQANY`** — §8.1's condition. The GAL split could not form it, because `REQ` was
  on one part and `ENA` on another, so it had to arrive as a pin. Here it is six
  product terms.
- **`MERGE`** — §9.4.5's merge is suppressed while a host read of `AINTREQ` is in
  flight, which needs the read strobe and both synchroniser stages in one place. The
  synchronisers were a `'174` and the read strobe was on the decode GAL.
- **`PEND0-5`** — the six bits whose crossing is what made the interrupt block
  unfittable on a `GAL22V10` in either arrangement.

> ⚠ **What is verified and what is not.** The *logic* is verified: `check:audio` runs
> these equations exhaustively where that is cheap — every strobe over all 16 offsets ×
> R/W × select, Paula's set/clear over all 256 written bytes twice, the slot walk, the
> ÷5 prescale, §9.4.5's ordering. The *fuse map* is not, and cannot be: the ATF1508AS
> is not in prjbureau's database, so unlike `mmu.jed` and `clkdec.jed` this JEDEC
> cannot be read back and executed against the model. It is trusted to `fit1508.exe`.
> `hardware/gal/README.md` carries that asymmetry.

> ⚠ **The I/O headroom is still the second reason to take A**, and it is now the
> reason there is a U2. §9.5's single-source sample-RAM address is what keeps A's pin
> count low: those 19 address lines are board wiring between two memories and never
> enter the logic at all. What the 2026-09-09 census added is the rest of the
> datapath, which had never been enumerated at all — §10.2's table — and it is 69 pins.

Video card, for comparison: **28**
([`graphics.md`](../../video/docs/graphics.md) §14.1). The path from this document's
first tally of 35 through 57, 54, 45, 36, 29 and 32 to today's **39** is archived,
itemised, in [history.md](history.md).

**Where it could shrink:**
- **−2** if the two converter port registers can be merged. They cannot be as drawn:
  the two sides' write windows run concurrently and a `'574` has one clock.
- **−1** if `PEND[7:0]` moved into the CPLD and the state file became a single ×16
  part. **Not costed** — the six `PEND` bits are exactly what §9.5 says fits no
  `GAL22V10`, they are already partly in the CPLD, and eight more registers on a part at
  89 of 128 logic cells is plausible. §16 item 28.
- **−4** for the two `'688` and two `'590` if the compare moves into the shared `'283`
  under an earliest-event scheme. It is the last structural idea on the list and it has
  not been costed; the walk's 4-channels-per-colour-clock compare is what makes the
  timing exact, and giving that up is not obviously free.

**Where it will grow:**
- **+1 `TL072`** if a DC-coupled output is ever wanted.
- **+0** for 512 KB of sample RAM, **+0** for panning and **+0** for the headphone
  driver — all three are in the table above.
- ⛔ **+7 for the sequencer, and they are in the table above too since 2026-09-09** —
  U2, and the six datapath packages §10 had never counted. The previous version of this
  list ended "every growth line this list has ever carried is now spent … the next
  package this card takes will be one nobody has anticipated", and that turned out to
  be exactly right and to be seven of them. §10.2.

**Power.** Three SRAMs, **two** `ATF1508AS`, ~22 HC packages, **thirteen op-amp channels and
four `AD7528`** at 2 mA each, plus §7.1's headphone driver — ~10 mA quiescent and up to
~60 mA into a low-impedance load on both channels: estimate **340–500 mA**, and the CPLD is the term least
worth trusting — a 128-macrocell part with ~100 registers toggling at 28 MHz is not
obviously cheaper than the six GALs it replaces, whatever the package count says. §16
wants this measured. ⭐ **The consolidation of §5 is roughly power-neutral rather than a
saving**: one `AS6C4008` at ~40 mA replaces one `AS6C1008` at ~40, and two
`IS61C6416` at ~35 replace three `CY7C128A` at ~40–60 — call it **−40 to −110 mA** on
the memory, against **+2 `AD7528` and +1 `TL074` ≈ +12 mA** on the analogue. Analogue
and digital grounds must meet at exactly one point, and the `AD7528` reference must not
share a rail with the SRAMs. That is the only layout constraint on this card that the
video card does not also have, and it is the one that decides whether it sounds clean.

**Area.** 35 packages — one DIP-32 SRAM, **two TSOP-44 SRAMs**, **two PLCC-84** (U1
socketed; U2's package is §10.2's open decision), **six DIP-20 converters**, four op-amp packages, a DIP-8 headphone driver and the rest
DIP-14/16/20 logic.
**The analogue section is eight converter halves and eight amplifier channels** since
programmable panning was given up (§11.1) — and the original one-board assertion was
about a **Eurocard**, which the machine stopped using on 2026-09-08 (`machine.md` §5
item 5). ⭐ **`npm run check:place` places the 35 packages on 18 cm and reports it as the
shortest length that works** — the card reached 24 cm at 45 packages and came back. That
is a courtyard-area check and not a layout. The question is no longer "does it need a
second card"; it is whether the analogue section can be kept physically separate on the
same 18 cm board.
**Measure the layout — §16 item 19.**

---

### 10.2 The sequencer — U2

⭐ **Built, fitted and simulated, 2026-09-09.** This section was a work breakdown for
half a day; it is now the description of a part.
[`hardware/gal/aseq.micro.ts`](../../hardware/gal/aseq.micro.ts) is the microprogram,
[`aseq.jedec.ts`](../../hardware/gal/aseq.jedec.ts) turns it into term lists,
[`aseq.cpld.ts`](../../hardware/gal/aseq.cpld.ts) is the part, and
[`verilog/audio_card.v`](../../hardware/gal/verilog/audio_card.v) wires U1, U2 and the
datapath together so `audio_tb` can play a buffer.

**What the simulation actually does**, because "the sequencer works" is not a claim:
it writes channel 0's `LC`, `LEN`, `PER` and `VOL` through §9.3's index/data window,
enables the channel with `DMACON`, and then asserts that `LC` reached `PTR`, that
`LEN × 2` reached `CNT` in bytes, that `PEND` was primed from card RAM, that the next
compare advanced `NEXT` by exactly `PER` and `PTR` by exactly one and `CNT` down by
exactly one, that the byte reached an `AD7528` through a converter port register, that
rewriting `LC`/`LEN` **while the first pass was still playing** made the buffer loop to
the new address, and that the buffer end raised `SET0` on U2, `PEND0` and `AINTREQ` b0
on U1 and pulled `/FIRQ` low with the host doing nothing at all.

#### 10.2.1 The state file, laid out

Sixty-four words of 32 bits, `SFA[5:0]`. Eight words per channel at `{0, ch, w}`, and
six globals at `$20`. ⚠ **Lane 3 is unpopulated, deliberately**: every host-visible byte
and every byte a converter takes lives in lanes 0–2, and that is what makes §9.3's
read-back path three `'574`s rather than a four-to-one multiplexer on eight bits.

| Word | lane 2 | lanes 1:0 |
|---|---|---|
| `w0` | `PEND` | `NEXT[15:0]` — the walk's one read, §3.3's 24 bits |
| `w1` | `CNT[16]` | `CNT[15:0]` — bytes remaining |
| `w2` | `PTR[18:16]` | `PTR[15:0]` |
| `w3` | `LC[18:16]` | `LC[15:0]` |
| `w4` | — | `PER[15:0]` |
| `w5` | — | `LEN[15:0]` |
| `w6` | `VOL` | lane 1 `ATT`, lane 0 `DAT` |
| `w7` | `PAN` | — |
| `$20` | | `TIMER` |
| `$21` | | `CIANEXT` — the colour-clock count the timer fires on |
| `$22` | `SPTR[18:16]` | `SPTR[15:0]` |
| `$24` | | the ×5 scratch |
| `$25` | | §9.4.3's host staging shadow |

⭐ **§9.3's host byte map is unchanged**, and the lane assignment above was chosen to
keep it that way: a 16-entry decode of `AIDX[3:0]` gives the word and the lane, and it is
registered so it costs the address equations one literal instead of eight terms.

⛔ **`AIDX` cannot live in the state file, and §9.5 said it did.** *"At a fixed address
the sequencer knows, which is what breaks the circularity"* — it does not break it: the
sequencer would have to **read** the index in order to compute the address of the byte
the index names, and Case A's U2 has no data bus. `AIDX` is six registers on U2, loaded
from `D0`–`D5`, and those six pins are the only reason U2 sees the host's data at all.

#### 10.2.2 The datapath — §10's table was thirteen packages short

Case A keeps the arithmetic outside the logic, so U2 drives control and never sees the
data. That is what keeps its pin count survivable, and it is also what makes the external
datapath much bigger than §10 ever counted:

| Qty | Part | Role | in §10 before? |
|---|---|---|---|
| — | ~~`74HC590` ×2, `74HC688` ×2~~ | ⭐ **inside U1 since 2026-09-09** — the counter is 16 registers and the compare a foldback tree, and both wanted the same sixteen state-file data lines U1 now has | **−4** |
| 4 | `74HC283` | the 16-bit adder | yes |
| 2 | `74HC574` | **`ALAT`** — the A operand, latched off the read bus | 3 "pipeline latches" |
| 2 | `74HC574` | **`BLAT`** — the B operand | ⛔ **no** |
| 2 | `74HC244` | **B = `$FFFF`**, so `A − 1` is `A + $FFFF` | ⛔ **no** |
| 2 | `74HC244` | **`SUM` → `SD[15:0]`** — the `'283` outputs would fight the file on every read | ⛔ **no** |
| 1 | `74HC574` | **`SBLAT`** — the sample byte, held from its fetch slot to its `PEND` write | 3 "pipeline latches" |
| **4** | `74HC574` | converter port register, **one per channel** (§6.2) | 2 |
| — | ~~`74HC244` ×2, `74HC574` ×2~~ | ⚠ **the 8-bit datapath is NOT taken** — §16 item 34 | — |
| — | ~~`74HC574` ×3~~ | ⭐ **inside U1 since 2026-09-09** — the read-back byte is eight registers on the part that already drives `D0`–`D7` for `AINTREQ` and `ASTAT` | **−3** |
| **1** | `74HC138` | the converter control code — §10.2.6's lever | ⛔ **no** |
| **1** | `74HC00` | the byte-lane write enables, gated with the slot clock's second half | ⛔ **no** |
| 1 | `74HC574` | posted-write data latch, host → sample RAM | yes |

⭐ **The B bus is shared with the comparator, and that is the trick that pays for
everything else.** The `'688` compares `NEXT` against whatever is on it; the walk slots
put the free-running counter there and the work slots put `PER`, or `$FFFF`, or nothing.
It is pulled **down**, so "nothing driving" is a hard zero — which is how `A + 1` costs no
package, and how `ACTRL` b5 = 0 writes a zero into a converter with **no constant
generator anywhere on the card**. There is no shifter and no inverter either: `LEN × 2` is
`ALAT` and `BLAT` both loaded from `LEN`, and `5 × TIMER` is two doublings and an add.

⚠ **Two of the six new packages are answers to questions §10.2 could only ask.** §6.2's
*two* converter port registers collide with the walk order — channel 0's byte reaches the
read bus in slot 0 and channel 3's in slot 3, and one register cannot hold both across two
four-slot windows — so there are four, three-stated onto the port each pair shares, and
their clocks come out of the `74HC138`. And a write enable asserted for a whole slot
writes during the address's settling time, so the three byte lanes are gated with the slot
clock's second half by one `74HC00`: an inverter and three gates, exactly. The sample
RAM's `/WE` needs none — its address is the state file's **held** read output (§9.5) and
is stable across both slots of the access.

#### 10.2.3 The micro-ops

Work runs in **slots 5, 6 and 7**. §3.1 gave slot 5 to "host service" and 6–7 to
deferred work; the microprogram makes no such distinction, so the host's own sequence
competes for all three — **10.6 M work slots per second** rather than 7.09 M. Every step
is one slot, and **even steps read, odd steps write**: a state-file read holds its data
for as long as the address holds (§9.5), so a read-modify-write is two slots and never
three.

| | steps | what |
|---|---|---|
| **W1** | **7** | a channel's compare hit: fetch the next sample byte at `PTR` and advance it, `NEXT += PER`, write the byte into `PEND`, `CNT − 1`. The carry out of the last step **is** the buffer end |
| **W2** | 4 | §3.3's shadow reload: `LC → PTR` and `LEN + LEN → CNT`, using whatever the host has written since. **W1 chains straight into it** without releasing the engine |
| **W3** | 6 | a host access: the byte to its lane or to §9.4.3's shadow, the commit, `SDATA`'s sample-RAM access and `SPTR` increment, and a re-prefetch at the post-incremented `AIDX` |
| **W4** | 10 | the tempo timer: `CIANEXT += 5 × TIMER`, once per period |
| **W5** | 12 | §6.1's volume and §11.1's pan — the other eight converter halves |
| **W6** | 8 | §1 requirement 6's `DMACON` restart. **It jumps the queue** |

⭐ **`LEN` = 0 is Paula's 65,536 words for free.** W2 writes `CNT` = 0 and W1's next
decrement takes it to `$1FFFF` = 131,071 bytes. No special case, no term.

⭐ **The tempo timer costs nothing per CIA tick**, which is what §8.2 meant by *"a fifth
entry in the compare structure of §4.2"* and is not what §8.2's implementation note
described. `CIANEXT` is a **colour-clock** count compared against the same free-running
counter the channels use, in slot 4; the only arithmetic is W4's ×5, once per timer
period at ~50 Hz. The ÷5 prescale that note specified would have cost **1.4 M work slots
a second — 13 % of the budget** — to do the same thing.

⚠ **W5 suppresses the walk's converter-port load while it runs**, so a sample transition
can be late by up to four colour clocks — 1.13 µs — about 200 times a second. That is a
real departure from §3.2's "jitter-free": 0.9 % of one sample period, on 2 % of
transitions. Stated rather than hidden.

#### 10.2.4 Paula's quirks, enumerated — §16 item 3

| Quirk | This card |
|---|---|
| `LC`/`LEN` copied at buffer end, not at note start | W2, triggered by W1 step 7's `ACOUT` |
| First fetch one period after `DMACON` enable | W6 primes `PEND` and sets `NEXT` = count + `PER` |
| `LEN` = 0 means 65,536 words | falls out of the 17-bit `CNT` — no term |
| `LEN` = 1 is one word, two bytes | `CNT` = 2 |
| `DMACON` cleared mid-buffer | W1 is not entered; `PTR`/`CNT` freeze; §6.1 forces `VOLCODE` = 0, so the held sample is silent |
| `PER` written mid-note | already correct — `NEXT` was computed from the old `PER` (§4.2) |
| `PER` = 0 or 1 | ⚠ **not clamped in hardware** — §10.2.2 |
| Attach (§11.3), ch *n* → ch *n*+1 | W1 step 5 writes the fetched byte to `ch+1,4` or `ch+1,5` instead of `PEND`. **Channel 3 modulates nothing**: the term is `ch != 3` |

#### 10.2.5 What it costs in slots — and §3.1's 56× is 46×

A channel event is **seven work slots**, measured by `audio_tb` rather than counted by
hand, and twelve when the buffer ends. Against **10.64 M work slots/s** (three per colour
clock, §10.2.3):

| | events/s, 4 ch | slots/s | margin |
|---|---|---|---|
| `PER` = 428 (C-2) | 33,148 | 232 k | **46×** |
| `PER` = 113 (B-3, ProTracker's top note) | 125,552 | 879 k | **12×** |
| `PER` = 30 (§4.3's extended floor) | 472,919 | 3.31 M | **3.2×** |
| …plus a 6309 saturating `SDATA` at 400 k stores/s × 6 | | 5.71 M | **1.9×** |

**The throughput floor is `PER` ≥ 10**, from 4 × 7 slots per `PER` colour clocks against
three slots per colour clock. §4.3's conservative ~30 sits three times above it, so the
extended period range survives the real micro-op count — and `audio_tb` runs four
channels at `PER` = 16 and asserts that no channel is left permanently due.

⚠ **§3.1's 56× was never the right number and neither was §10.2's first 7×.** The first
counted pointer updates rather than slots; the second counted seven slots against two
work slots per colour clock instead of three. Both are archived.

#### 10.2.6 The pin budget, and the one lever that was pulled

U2 is **37 outputs and 26 inputs**, and the fitter reports **60 of 64 I/O and 128 of
128 logic cells** — "Design fits successfully" on the first pass, with 76 foldback nodes,
18 cascades and 469 product terms. `npm run check:audio` prints the interface and asserts
it is **closed in both directions**: every signal U1 reads is produced by U2, the
backplane or the board, and every signal U2 reads is a U1 output or the `'688` and the
`'283` chain answering it. Seventeen nets cross from U1 to U2 and five come back.

⛔ **There is nothing left.** 128 of 128 is not a comfortable fit and it is not presented
as one. A **TQFP-100 was fitted as well** and takes the pins to 62 of 80 while leaving the
cells at 128 of 128 — both packages carry the same 128 macrocells — so the larger package
buys pin headroom this design does not need and costs the socket. **The PLCC-84 with JTAG
off is the answer, and the next thing added to this card has to displace something.**

⭐ **One lever was pulled, and it is named because a pin count that comes down without a
reason is a feature that has been quietly dropped.** Four converter port-register clocks
and three `AD7528` chip selects are mutually exclusive — a step that loads a register
never strobes a package — so they are **one 3-bit code and a `74HC138`**, whose eight
outputs are exactly idle, four clocks and three selects with nothing left over.
**−6 pins, +1 IC.** Two more turned out not to be levers at all: the `AD7528`'s `/WR` is
tied low (its latch is transparent while `CS` and `WR` are both low and captures on the
rising edge of either, so `/CS` alone is the strobe), and `CVOEB` and the DAC A/B select
are both `CVOEA`'s complement, which is an inverter rather than two pins.

**Three levers were costed and not needed**: a `74HC139` on the byte lanes, `SET0`–`SET5`
left as six lines, and the TQFP-100. `SET0`–`SET5` **is** encoded — a 3-bit source code
decoded back on U1 — but that one paid for itself twice, because it also moved six
macrocells onto the part that had them.

⚠ **What the pin budget cost elsewhere is on U1**, and it is worth stating: the host
handshake moved to U2 entirely. U1's version synchronised *"an access happened"* and
produced its **trailing** edge, which is after `E` has fallen and the address may already
be gone — so **which register was touched was never captured anywhere**. U2 latches the
offset and R/W on the leading synchronised edge instead, which is the only place on the
card that can act on it.

---

## 11. What this card does that Paula cannot

Presented as opt-in, because **the default configuration must be Paula-exact** or
the acceptance test in §1 is meaningless. Each of these is a register bit that
software has to ask for.

### 11.1 Panning (given up 2026-09-09; see history.md)

⛔ **Programmable per-channel panning was pitched at "+2 ICs" and cost six**, and it is
not in the card. §6.3's twelve halves are eight; the second volume converter per channel,
the extra `AD7528` pair, the extra `TL074` and W5's second pass over all four port
registers all went with it.

⭐ **What replaces it is what every MOD already assumes: fixed LRRL.** Channels 0 and 3
sum at the left node, 1 and 2 at the right — Paula's hard pan, bit-exact, and **it is
which node an output is wired to rather than any logic at all.** `ACTRL` b5 is withdrawn
and `PAN` (§9.3 offset 10) reads and writes as reserved.

**The acceptance test is untouched**: §1 requirement 5 *is* hard-panned stereo, and this
is the arrangement it names.

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

- **16-bit samples.** The converters are 8-bit halves and Paula's format is 8-bit;
  16-bit needs a wider path throughout. It also has nothing to do with mods.
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
discrete card is ~19 ICs more (§10's 29 against a ~10-IC `RF5C68` card) for parts you
can buy forever. Availability decides it.

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
out which of §1's nine requirements you got wrong — **before a CPLD has been
fitted.** Then the discrete card is a drop-in replacement that has to match a
known-good reference, and any disagreement is a bug with a bisector attached.

That is exactly the A/B lever [`plan.md`](../../cpu/docs/plan.md) §6.2 builds the whole
validation strategy on, applied one level up.

**So: freeze §9's register map first. The register map is the deliverable; the
implementation is a choice, and the machine should be able to hold both.**

---

## 13. Software

> **The loader and replayer have their own document,
> [`modplayer.md`](modplayer.md), and a working reference implementation in
> [`audio/refplayer/`](../refplayer/).** The document covers the
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

**That third row is §6.1's offset-binary conversion, and it is always paid here.**
Card RAM holds samples offset binary because the converter is unsigned-coded; a `.mod`
holds them two's complement. **§16 item 27 is decided: the loader flips the bit**, for
every module regardless of where the file came from. It XORs each sector buffer in
place before the `TFM`, and the upload costs **about 690 ms rather than 187**, once per
module — ~738 ms with the chunking of [`modplayer.md`](modplayer.md) §4.4 applied to
the `TFM` half.

**The 187 ms row is therefore the card's transfer rate, not a load time anybody sees.**
It is still the right number for §13.1's store-rate argument and for item 1's scaling,
and it is what the fast-E figure below is computed from — but no module loads in
187 ms, because none of them arrive pre-converted any more. Anything quoting a
user-visible load time should quote ~738 ms.

`W` is 16 bits and `TFM` treats `W` = 0 as 65,536 nowhere — it stops — so 128 KB is
**three** `TFM` instructions and a pointer fix-up: `65,535 + 65,535 + 2 = 131,072`.
([`modplayer.md`](modplayer.md) §4.4 states the same arithmetic; they agree.) The
card's posted-write path retires one byte per colour clock in slot 5 —
**3.55 M/s against `TFM`'s 700 k/s**, a 5× margin, so **no `/WAIT`, no FIFO
stall, no lost writes** (§9.3). At the experimental fast-E rate the numbers become
1.05 M/s against 3.55 M/s, still 3.4×, and the `TFM` falls to 125 ms — the all-in load,
conversion pass included, to ~492 ms.

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
| Sample data | **copy verbatim.** ⚠ The offset-binary conversion is **not** done here — §16 item 27 puts it in the loader, and doing it twice cancels it |
| Sample length (words) | **copy verbatim** into `LEN` |
| Repeat offset / repeat length | **copy verbatim**; the replayer writes them into `LC`/`LEN` on tick 1 (§3.3) |
| Period values in patterns | **copy verbatim** — same reference clock |
| Finetune | **copy verbatim** — it indexes the same period tables |
| Volume 0–64 | **copy verbatim** |
| `Fxx` BPM | **copy verbatim** — same CIA-B arithmetic (§8.2) |
| Sample start address | +base, and >>0 (byte addressed, §9.3) |

The real edits are relocating samples into card RAM and building the address table.
**There is no resampling, no requantisation, no retuning and no arithmetic** — and that
is the strongest single argument for every decision in §4.1, §6.1 and §8.2. A converter
that has to do arithmetic is a converter that has a rounding error, and mods are
unforgiving about rounding errors in `PER`.

**The first row's "verbatim" is deliberate, and it is the trap.**
The conversion is a single bit that must be flipped exactly once between the file and
the converter, and §16 item 27 puts that flip in the loader — so an offline converter
that also flipped it would hand the loader a pre-flipped file, the loader would flip it
back, and the card would be fed two's complement: **Aud-M1 in full, a full-scale step
at every zero crossing.** `XOR $80` is its own inverse, so the doubly-flipped file is a
structurally valid `.mod` of the right length with a plausible-looking waveform, and
nothing short of playing it or scoping it (§16 item 21) will say otherwise. The rule is
one line and the whole project depends on it: **the loader flips, the converter does
not.**

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
| Sample memory | system RAM, CPU-fed | none | 512 KB chip RAM, DMA | 64–128 KB, DMA | **512 KB, DMA** |
| Resolution | 6 bit | 4-bit master volume | **8 bit × 6-bit volume** | 8 bit × 8-bit volume | **8 bit × 64-level volume, unquantised product (§6.1)** |
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
| 0 | **Freeze §9's register map** and the backplane's `/FIRQ` and I/O-window assignment | one document; §16 items 4–6 answered; `ACTRL` b4 = 8-channel, `ACTRL` b6 = timer enable, `AINTREQ`'s set form and `ASTAT` b6/b7 all decided in §9.2 |
| 1 | **Build the MCU card** (§12.5): STM32G431 + one `AD7528` + §7's filters. It sums in software and drives one converter pair, not §6.2's eight halves — what it validates is the register map and the replayer, and the cascade is step 7's job | plays a known module correctly through the §9 register map |
| 2 | **Write the loader, replayer and converter** against the MCU card | acceptance test: 20 varied modules, A/B against a real Amiga or a reference emulator, by ear and by capture |
| 3 | **Bench the §3.2 stage-A path** at 35 ns on a breadboard — sequencer address out → `IS61C6416AL-12` state file → compare-input setup, 27 ns budgeted | closes with margin |
| 4 | **Fit the card's logic** with all eight slots, the shadow reload, the deferred queue, the host-counter increments and the interrupt block | ⛔ **half done, and the half that is done is the host block.** §10.1.1's U1 carries the slot walk, the interrupt block, `ACTRL`, the decode and the read-back path, fitted at 89 of 128 logic cells. **The shadow reload, the deferred queue and the host-counter increments are U2** — specified in §10.2, not fitted, §16 item 00. §16 item 7's 8-channel slot allocation is downstream of that again |
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

00. **⭐ CLOSED 2026-09-09 — the sequencer is built, fitted and simulated.** §10.2 is
    the part: `gal/aseq.micro.ts` is the microprogram, `gal/aseq.jedec.ts` the term
    lists, `gal/aseq.cpld.ts` the `ATF1508AS`, `verilog/audio_card.v` the board between
    it and U1, and `audio_tb` plays a buffer through the whole path — host port, state
    file, sample RAM, `PEND`, converter port register, `AD7528` — reloads it from a
    shadow the host rewrote mid-play, and delivers the end-of-buffer interrupt.

    ⚠ **What is NOT closed, and it is the analogue half.** §16 items 9, 10, 19, 23 and
    25 are unchanged: the converter glitch, the cascaded settling, the layout at 45
    packages on 18 cm, the channel-to-channel gain match and the split rails. **The
    digital side of §1's acceptance test can now be evaluated from the design; the
    analogue side still cannot be evaluated from anything but a bench.** And §16 item 7's
    8-channel mode remains unfitted — the microprogram has room for two more work types
    and the slot walk does not.

0a. **CLOSED 2026-09-09 — the end-of-buffer interrupt is delivered.**
    `MERGE = CCLK & !SYNCR2 & !SYNCR1`, one literal against the equation that fired only
    on the trailing edge of a host read. §9.4.5, and `audio_tb` walks the read across all
    sixteen slot phases. ⚠ **It is delivered by U1 and nothing raises it yet**: `SET0`–
    `SET5` are item 00's outputs.

0b. **⚠ NEW 2026-09-09 — five things the card could not do, and now can.** §9.1's
    decode, §9.3's read-back path, the prefetch latch's output enable, §9.5's `AIDX`
    (which cannot live where §9.5 put it) and §9.4.4's capture of *which* register a host
    access touched were all described in this document and produced by nothing.
    **The class of defect is what to take from it**: each was a paragraph asserting a
    mechanism, and what found them was the port census in `npm run check:audio` — which
    asks what *produces* a signal, not what a document says about it. It now runs in both
    directions across the U1/U2 boundary, so a card whose two dice each fit and do not
    join cannot pass.

0. **DECIDED 2026-09-08 — the sample RAM stays card-local and off the physical map.**
   §5.2 has the arithmetic: memory-mapping it needs a second source on the 19-bit
   sample-RAM address bus, and §9.5's whole cheapness rests on there being one. That is
   **+3 × `74HC157`**, or 19 more pins on a part at 57 of 64.

   > ⚠ **The consequence is real and it is recorded rather than solved: this card is the
   > last one in the machine whose bulk transfer targets a side-effecting port**, so it
   > is the last one exposed to the 6309's unsettled `TFM` resume behaviour (§9.2,
   > `modplayer.md` §4.4). **The thing that retires it is not on this card** — it is
   > `sdcard.md` §11.6's owner's choice about what this machine's `TFM` does with an
   > interrupt, which costs zero firmware cycles and closes the exposure everywhere at
   > once. **Until then the masked upload loop stands.**

1. **Confirm the CPU store rate.** §13.1's ~3 % and §13.2's 187 ms both scale on
   "~5 core cycles per store, native mode" — the same assumption
   [`graphics.md`](../../video/docs/graphics.md) §19 item 1 already flags. Measure it once and both
   documents get their numbers.
2. **Retired — the stage-B LUT bench.** The LUT left the card (§3.2, §6.1). The
   fastest path on the card is the state-file read — 10 + **12** + 5 = **27 ns** against
   the 35.24 ns slot, on the `IS61C6416AL-12` §5.3 specified — and build step 3 gives it
   the bench hour the LUT path was going to get.
3. **ENUMERATED 2026-09-09 — §10.2.4 has the table:** the exact instant of the
   `LC`/`LEN` copy (W2, on the buffer-end carry), the first-fetch delay after DMA
   enable (W6), `LEN` = 0 as Paula's 65,536 words — which falls out of a 17-bit `CNT`
   for no terms at all — `LEN` = 1, and `DMACON` cleared mid-buffer. ⚠ **One did not
   survive the enumeration**: §4.2's `PER` = 0/1 clamp needs to *see* `PER`, and Case A's
   U2 does not have the data bus (§16 item 31). **Still open: verify each against the
   MCU card in step 2.**
4. **Freeze the I/O window** at `$FF40–$FF4F` (§9.1) or elsewhere, with the video
   card's `$FF60–$FF7F` and a future disk controller in the same picture.
5. **Freeze the `LC` byte / `LEN` word asymmetry** (§9.3). It is a one-line
   decision that every piece of software downstream depends on.
6. **Confirm `/FIRQ` ownership** (§8.1) — the audio card as the sole source, with
   no polling chain, needs to be stated in the backplane spec, not assumed.
7. **The 8-channel fit** (§11.2). The sequencer carries the 8-slot walk, the
   compare, the shadow reload, the deferred queue, `DMACON` set/clear and the
   interrupt latches, and the base design is fitted (§10.1.1). The 8-channel slot
   allocation is not — **fit it before promising the mode**. The four-DAC sum does
   not move this: four `WR` lines and four latch clocks is eight control signals,
   exactly what the digital sum needed (§6.2). Same posture as
   [`graphics.md`](../../video/docs/graphics.md) §19 item 15.
8. **Retired — the digital-sum glitch bench.** There is no adder in the card's audio
   path (§6.2). Each converter is driven from a hold latch that has been static for
   105.7 ns when `WR` rises, so there is no digital transient to measure; the
   converters' own code-transition glitch against the analogue noise floor is
   item 9's job.
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
15. **Retired — the missing `AD7545A` datasheet.** §6.3 no longer specifies that
    part, or any 12-bit converter. **`AD7528.pdf` is in the repo**, and every figure
    §6.1–§6.3 rests on — the ±1 % `VREF` match, `tWR`/`tDS`, the glitch impulse, the
    gain-error grades — is read from it rather than quoted second-hand. §17's audit
    rests on a datasheet that is present.
16. **Lapsed — the `LTC7545A` is no longer on the card.** §6.3 specifies the
    `AD7528`, whose datasheet is in the repo, so the 12-bit part's production status
    and price no longer carry a BOM note.
17. **Closed: adopted.** §6.2's four-DAC analogue sum is the primary design. Doing
    the analogue work this item asked for is what settled it: the recorded "−12
    packages" estimate was really −3 (it had missed the per-channel hold latches the
    converter's 100 ns `tDS`/`tWR` forces, and a second amplifier pair), and separate
    dice cannot sum as currents at all — `RREF` is specified 8–15 kΩ part to part, up
    to 5.5 dB between channels — which is the obstacle the dual `AD7528`'s ±1 %
    on-die match removes (§6.3). What the adoption left behind is items 23–25.
18. **Probe the LED filter against libopenmpt's `a500` behaviour.** **No probe in
    the A/B ladder issues `E0x`**, so every comparison runs with the filter in one
    state. Add a single-note probe that toggles `E0x` mid-note and compare the
    transition against libopenmpt's `a500` LED path. The pass condition is the
    three-pole chain of §7 — the fixed ≈4.4 kHz pole plus a **12 dB/octave**
    Sallen-Key at 3275 Hz — and the failure it exists to catch is a wrong filter
    order, which shows up as tens of dB of missing or excess level two octaves above
    the corner (Aud-M4 was exactly that — history.md §7). Until the probe exists,
    "both Amiga filters, switchable" is an unverified claim about the half of §7 the
    acceptance test can hear.
19. **⚠ Confirm the card fits its envelope at 35 packages, back on 18 cm**
    (§10, §7.1). The one-board fit has been asserted and never measured, and the card's
    shape is digital-light and analogue-heavy — **twelve converter halves and thirteen
    amplifier channels** since §11.1's panning, against the eight and ten this item was
    first written about. (The original assertion was about a **Eurocard**;
    `machine.md` §5 item 5's card format replaced it.) ⚠ **`npm run check:place` refuses
    18 cm at 35 packages and reports it as the shortest that works** — the
    consequence of §10.2's enumeration that is not a pin or a package but a board.
    Measure it, with the analogue section physically separate and a rear-edge jack to
    place as well. This is the last thing standing between the card and a layout, and it
    is now also a question for whoever owns the machine's card lengths.
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
    dice sharing one feedback resistor — the 5.5 dB error §6.2's by-side pairing
    exists to avoid.
24. **One buffered `V_REF` for four converters** (§6.3). Four ladders in parallel are
    ~2.75 kΩ, and any series impedance between the reference and an individual part
    becomes a gain error on that channel alone — the same failure as item 23, arriving
    through the reference instead of the feedback. Star-distribute from a buffer, and
    measure the level of each channel with the other three at full scale to catch it.
25. **⚠ Rails for the analogue switch, the LED stage — and now the headphone driver**
    (§6.3, §7.1). With the pedestal blocked rather than cancelled, the signal between the
    I/V stage and the output capacitor lives between 0 and −`V_REF`. The `74HC4066` and
    the Sallen-Key stage must be powered to pass it, which means split rails and a `VSS`
    below −`V_REF`. It is not the single-5 V card the digital section is, and it should
    be in the schematic before the mezzanine question of item 19 is answered.

    ⚠ **This item got bigger on 2026-09-09, and it is no longer "costs no packages".** It
    was a rail *voltage* question because everything on those rails was an op-amp signal
    path drawing milliamps. §7.1's `NJM4556AD` draws up to **~60 mA into a low-impedance
    load on both channels at once**, from the same pair. **The negative rail now needs
    current capability**, which is a regulator or charge-pump question rather than a
    reference-divider one — and that is the difference between a rail that can be derived
    and one that has to be built.
26. **Confirm the prefetch `'574` can drive the backplane alone** (§9.3). Deleting the
    `74HC245` puts a `74HC` flip-flop's outputs directly on the host data bus. `74HC`
    sources 6 mA, which is what the `'245` sourced, so the loading rule is the one the
    card was already meeting — but it was being met by a part chosen for it, and it is
    now being met by a part chosen for something else. Count the loads on the bus,
    including whatever the backplane spec permits a future card to add, before the
    package is deleted from the BOM rather than from the document.
27. **Closed: the loader flips the bit** (§6.1, §13.2). `LDD`/`EORD #$8080`/`STD`
    over each sector buffer before the `TFM`, which is what
    [`../refplayer/`](../refplayer/) models (`mod_load.c`). The cost is **~690 ms
    rather than 187 ms** for a full 128 KB image, or **~738 ms** with
    [`modplayer.md`](modplayer.md) §4.4's chunked `TFM`, once per module. The offline
    converter lost on scope — a `.mod` player whose fast path requires a proprietary
    pre-processing step is a player for a curated library, not for the corpus — and
    the one-gate inverter on the fetch path lost on packages and on the register-map
    exception it would carve for `DAT` (§9.3 offset 8).

    > **What this decision creates is a rule with no local check: the loader flips,
    > and the `.mod` converter must not.** `XOR $80` is its own inverse, so flipping
    > twice restores two's complement and reinstates Aud-M1 — a full-scale step at
    > every zero crossing — out of two components that are each individually correct.
    > The doubly-flipped file is a valid `.mod` and nothing in
    > [`modplayer.md`](modplayer.md) §4.6's validation table can reject it. §13.3's
    > first row says "copy verbatim" for this reason, and item 21's zero-crossing
    > scope is the measurement that catches it if anyone gets it wrong anyway.

28. **⚠ NEW — the state file's spare byte.** §5.3 makes the file 32 bits wide where
    word 0 needs 24. Two things could use the eighth byte and neither is costed: moving
    §3.3's flag bits into word 0, or — the bigger one — moving `PEND[7:0]`
    into the CPLD and dropping the state file to **one** ×16 package (§10, "where it
    could shrink"). ⚠ **The second got harder on 2026-09-09**: it would put `PEND` on
    U2, and U2 is the part with no pins to spare (§10.2.6). U1 has the room, at 89 of
    128 logic cells — and is on the wrong side of the card.

29. **CLOSED 2026-09-09 — the jack gets a driver and the backplane keeps the line
    output.** §7.1. An `NJM4556AD` at +1 IC, and the two outputs stop pretending to be
    one signal. The objection this item recorded — that a headphone amplifier does not
    belong on a board with three digital SRAMs and a 28 MHz clock — **is not wrong and is
    outweighed**: the alternative was a connector that silently underdrives everything
    plugged into it. It is answered by placement rather than by argument, in the analogue
    section §10 already wants physically separate.

    ⚠ **What is still open is the ground.** The jack is the one node on this card that
    leaves the board into something a person touches, and a shell bonded to a chassis is
    a second ground path where §10 allows exactly one. Isolated bushing, or bond the
    chassis at the same single point — **and check it on the bench, because it is
    inaudible on a scope and obvious in headphones.**

30. **CLOSED 2026-09-09 — U1 is refitted.** 89 of 128 logic cells, 57 of 64 I/O, 289
    product terms, "Design fits successfully" (§10.1.1). ⚠ **The fit did not hold for
    the reason this item expected it to**: §11.1's `PAN` field and §5.3's byte enables
    cost nothing because they are the sequencer's, and the sequencer is not on U1. What
    moved the numbers was item 0b's three repairs.

31. **CLOSED 2026-09-09 — the converter port registers are one per channel**, and
    programmable panning is gone, so the second question this item carried went with it.
    §6.2's two, one per side, collide with the walk order: channel 0's byte reaches the
    read bus in slot 0 and channel 3's in slot 3, and one register cannot hold both
    across two four-slot windows. It is **four `74HC574`**, three-stated onto the port
    each pair shares, with their clocks and the three chip selects decoded from one
    `74HC138` — the same package that is §10.2.6's pin lever, so the two decisions paid
    for each other. The walk order was the alternative and it is §3.1's jitter argument,
    which is not available to trade.

    ⚠ **Still open: §4.2's `PER` = 0/1 clamp has no home.** Case A's U2 never sees `PER`.
    A replayer cannot emit `PER` < 10 and a broken one taking the card to a 3.5 MHz fetch
    rate is a denial of service rather than a corruption, so the answer taken is **the
    software rule, stated in §4.3 and §9.3**, with a zero-detect gate (+1 IC) as the
    fallback if a bench ever needs it.

32. **⚠ U2 is full and U1 is not.** U2 is the sequencer and it has no spare cells;
    U1 has room and 18 spare pins, which is why the counter, the comparator and the
    read-back latch all went there. §16 item 7's 8-channel mode and §11.3's attach chain
    still have to **displace** something on U2 or move to U1.

33. **⭐ CLOSED 2026-09-09 — writing `AIDX` now prefetches, as §9.3 always said.**
    ⛔ **It never did.** The prefetch ran at the *end* of an `ADATA` access, so the first
    read after an index write returned the byte the **previous** index named. It was
    invisible while the read-back was three `'574`s capturing all three lanes and
    choosing one at read time — the two offsets a test happened to compare lived in the
    same word — and it became a hard failure the moment U1 captured a single lane.
    Every host access queues a work item now, with W3's write step gated off for an index
    write (`!ISAIDX`) so the index cannot store itself into the location it names.
    `audio_tb` reads `PER`'s two bytes back and gets what it wrote.

34. **⚠ NEW 2026-09-09 — the 8-bit datapath, costed and NOT taken.** Narrowing the adder
    to a byte halves the `'283` chain, the `$FF` constant and the sum three-state: **−4
    packages**, and the measured margin can afford it — a channel event would go from
    seven work slots to ten, and four channels at ProTracker's top note use **37 of 600**
    slots today (§10.2.5). **What stops it is `ALAT` and `BLAT`.** Each must still hold
    sixteen bits and present eight, so each is still two `'574`s with their output
    enables acting as the byte multiplexer — the "halved" latches are not halved, and the
    saving is 4 rather than the 6 it looks like. It also wants two more U2 pins for the
    byte select on a part with three, and a fifth `T` bit on a part at 128 of 128 cells.
    **Take it only with a U2 rebalance in the same pass** — §9.3's `AIDX` and its
    sixteen-entry offset decode are eighteen registers that would sit naturally on U1.

---

## 17. Period audit

| Element | Introduced | Verdict |
|---|---|---|
| Paula (MOS 8364) as the model | **1985** | the design premise |
| 28.37516 MHz crystal | 1985 (Amiga PAL master) | period-exact, and still purchasable |
| `AD7528` **dual** 8-bit multiplying DAC | **1985** | period, and the datasheet is in the repo — the sample/volume cascade of §6.1 is its own headline application. **Four of them, eight halves** |
| `TL072` / `NE5532` | 1978 / 1979 | period |
| `74HC` logic | 1982 | period |
| `74HC688` 8-bit comparator | 1984 | period |
| `ATF1508AS` CPLD (§10.1) | CPLDs as an architecture are **1988** (MAX 5000 — [`graphics.md`](../../video/docs/graphics.md) §10.1.2); the `ATF1508AS` itself is a later part in that class | admitted by the machine's programmable-logic rule (root `README.md`) — the period argument is the architecture's date, not the part number's |
| ~~`CY7C128A` 2K×8, 15 ns~~ → **`IS61C6416` 64K×16, 12 ns** | 1985 → **~1996** | ⚠ **the state file's part moved forward a decade** (§5.3). The 2 KB × 15 ns part is period and out of production; the ×16 part is neither. Same posture as the framebuffer's `AS6C8016` on the video card, and it is a *width* substitution rather than a capability the era did not have — 24-bit-wide state files were built out of three byte-wide parts, which is exactly what this replaces |
| AS6C4008 (512K×8 SRAM) | 4 Mbit SRAMs ~1992–93 | ⚠ **the largest period stretch in the memory** — a 512 KB static RAM in one DIP-32 is early-1990s. The 128K×8 it replaces was already flagged as the newest silicon on the card (§5); this is two years later again, for three fewer packages |
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
  arbitration), §11 (the `VDATA` prefetch this card's `ADATA` copies), §12 (interrupt
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
  effectively absent.
