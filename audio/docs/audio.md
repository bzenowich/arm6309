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
| **Discrete card, real Paula, a period sound chip, or an MCU?** | **Discrete card.** 35 ICs, same envelope as the video card. | §12 |
| **Where does the sample data live?** | **Card-local SRAM, 128 KB** (footprint for 512 KB). The card never touches the bus for audio. | §5 |
| **How are the four channels implemented?** | **One time-multiplexed datapath**, 8 slots per colour clock, state in a 32-bit-wide SRAM file. | §3 |
| **How is per-channel pitch generated?** | **Compare-against-a-free-running-counter**, not four down-counters. Kills 12+ ICs. | §4.2 |
| **What is the period reference clock?** | **3.546895 MHz — the Amiga PAL colour clock**, from a 28.37516 MHz crystal ÷8. Non-negotiable. | §4.1 |
| **How is volume applied?** | **A host-loadable 32K×8 lookup table**, `{VOL[6:0], SAMP[7:0]} → 12-bit signed`. Same trick as the palette LUT; the volume curve is table content, not hardware. | §6.1 |
| **How are channels summed?** | **Combinatorially, asynchronously** — exactly as Paula sums four analogue currents. No output sample rate, no resampling, no jitter. | §6.2 |
| **What DAC?** | **2 × LTC7545A** — 12-bit parallel MDAC with an input latch, the current-production `AD7545A` pin-compatible. Not a serial audio DAC — §6.3. | §6.3 |
| **Do we need the Amiga filter?** | **Yes, and not for nostalgia.** It is the reconstruction filter for channels running below ~16 kHz. Both filters, switchable. | §7 |
| **Where does mod tempo come from?** | **An on-card 16-bit timer clocked at colourclock/5 = 709.379 kHz — the Amiga's CIA clock exactly**, so `Fxx` BPM values are CIA-B-identical. Costs one slot, zero ICs. | §8.2 |
| **Which interrupt line?** | **`/FIRQ`.** Video's VBL owns `/IRQ`. A 6809 `FIRQ` is what a replayer tick should be. | §8.1 |
| **What does mod playback cost the 6309?** | **~2.7 % of a 2.098 MHz CPU** for the replayer, with a 19× worst-case margin; **~187 ms once** to upload 128 KB of samples via `TFM X+,Y`. | §13, [`modplayer.md`](modplayer.md) §7 |
| **What does this card do that Paula cannot?** | No minimum period; per-channel panning (+2 ICs); 8 channels at half period resolution; a programmable volume curve. | §11 |

**Net: 35 ICs**, against the video card's 36. One oscillator, one clock domain,
no bus mastering, no `/WAIT`, and the only tight path in the design is a 35 ns
pipeline stage that is directly analogous to — and 5 ns *looser* than — the video
card's 39.7 ns dot path.

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
  stage A (35 ns) : state-file read  -> {NEXT[15:0], VOL[5:0], SAMP[7:0], DMAEN, ATT}
  stage B (35 ns) : compare NEXT vs the free-running counter
                    LUT read  {curve, VOL, SAMP} -> 12-bit signed scaled sample
  stage C (35 ns) : accumulate into the L or R sum; on a compare hit, queue
                    the channel for slots 6-7
```

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
| `VOL` | 6 | **host** | 0–64 |
| `PTR` | 19 | sequencer | current byte pointer |
| `CNT` | 17 | sequencer | bytes remaining in the current buffer |
| `NEXT` | 16 | sequencer | colour-clock count at which this channel next ticks |
| `SAMP` | 8 | sequencer | the byte currently being held out to the DAC |
| flags | 4 | both | DMA enable, attach-period, attach-volume, IRQ pending |

**The packing is not arbitrary.** Word 0 of each channel holds exactly
`{NEXT[15:0], VOL[5:0], SAMP[7:0], DMAEN, ATT}` = **32 bits**, which is why stage A
of §3.2 needs one access and not two. Everything the per-colour-clock walk touches
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

- **No adder in the audio path.** Volume is a table lookup (§6.1), not a multiply.
- **No divider anywhere.** Period is a divisor applied by comparison (§4.2), never
  computed.
- **No FIFO, no buffering, no DMA arbitration.** Sample memory is card-local and
  200× oversupplied (§2), so there is nothing to arbitrate.
- **No output sample rate.** §6.2.

The video card's "no adder anywhere" property (minimal256.md §3) survives here in
spirit: **the only adder on the card is the shared 16-bit `'283` chain in slots
6–7**, running at 126 kHz, doing work no one is waiting for.

---

## 4. Pitch: the colour clock, and the trick that saves twelve packages

### 4.1 The clock is not negotiable, and it is a stock crystal

A ProTracker note is a `PER` value; the resulting sample rate is
`3546895 / PER` Hz. Note C-2 is `PER` = 428 → 8286 Hz. If the card's reference is
anything else, every module is transposed by the ratio.

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
  D11..D0  scaled sample, 12-bit signed     <- 2 x 32K x 8, 15 ns
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

**12-bit output, not 8.** At `VOL` = 1, an 8-bit output would reduce the sample to
±2 — two bits of resolution, and volume fades would be audibly stepped. Paula's
internal product is ~14 bits. 12 bits costs one extra SRAM and matches the DAC
(§6.3); the two low bits Paula has beyond that are below the noise floor of any
realistic analogue stage.

### 6.2 The sum is combinatorial, and that is the design's best property

Paula produces four independent current-output DACs and sums them at an analogue
node. There is **no output sample rate** anywhere in an Amiga's audio path — each
channel is a zero-order hold at its own rate, and the sum is continuous-time.

Every software mod player resamples to a fixed output rate and spends real effort
(band-limited synthesis, oversampling) hiding the damage. This card does not have
to, because it can do what Paula does:

```
  4 x 12-bit scaled values, held in the accumulators (slots 0-3)
        |
        +--> L = ch0 + ch3   (13 bits) >>1 --> LTC7545A --> I/V --> filter --> out L
        +--> R = ch1 + ch2   (13 bits) >>1 --> LTC7545A --> I/V --> filter --> out R
```

The accumulator latches update at the end of each colour-clock frame, so the DAC
input changes **at the exact colour clock on which a channel's sample changed** —
which is the same instant Paula's ladder current would change. There is no
resampling, no interpolation, no jitter, and no aliasing introduced by the mixer,
because there is no mixer sample rate to alias against.

The sum of two 12-bit signed values is 13 bits and the DAC is 12, so **the
bottom bit is dropped once, at the converter** — a wire, not a stage. A single
channel therefore reaches 11 bits of the DAC and two channels at full scale
reach all 12, which is the same headroom split Paula's four current-output
ladders make.

**The one artefact is adder settling** — a ~20 ns glitch on the DAC input at each
channel transition, ≤126,000 times a second. Those are 20 ns impulses arriving at
audio rates; the 4.4 kHz filter of §7 attenuates them by roughly 60 dB and the
DAC's own settling swallows most of what is left. If the bench disagrees, the fix
is one `'574` deglitch latch clocked at the colour clock — **+2 ICs, and it does
not change the timing model**, because the colour clock *is* the event grid.

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

> **Sourcing note.** The period part here is the **`AD7545A` (Analog Devices,
> 1983)**, and the design is written against it. It is effectively out of
> production and now trades at **~\$50**. The **`LTC7545A` is the pin-compatible,
> current-production improvement on it at ~\$9** — tighter DNL/INL over
> temperature, same 20-pin footprint, same interface. **Specify the `LTC7545A` and
> build with it**; the `AD7545A` stays in §17's period audit as the part the
> design would have used in 1989, and either drops into the same socket. This is
> the same posture [`graphics.md`](../../video/docs/graphics.md) §10.1 takes for `ATF22V10C` versus
> a classic `GAL22V10`: period-honest design, current-production BOM. The latch replaces the output `'574`s, so the parallel part
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

`LTC7545A` is a current-output multiplying DAC, so each side needs an I/V stage and
a bipolar-offset arrangement — one `TL072` handles both sides. Standard, and the
`Vref` input is a free master-volume/mute point.

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
| **"LED"** | 5-pole Butterworth: two Sallen-Key stages + the fixed pole | **≈3.3 kHz** | `ACTRL.0` |
| **Bypass** | `74HC4066` shorting both | flat to the DAC's own ZOH | `ACTRL.1` |

- **Fixed only** is the A500 default and the right setting for the acceptance test.
- **+ LED** is what a lot of period material was mixed under, and some modules
  genuinely need it.
- **Bypass** exists for native software using the extended period range of §4.3,
  where 118 kHz channels put the images far above the audio band and the 4.4 kHz
  pole is pure loss. **Bypass is the wrong setting for mods** and the register bit
  should be documented that way.

Parts: **3 × `TL072`** (two I/V, four filter poles) + **1 × `74HC4066`** + passives.
An `NE5532` is the better op-amp and equally period; `TL072` is specified here for
supply-rail simplicity.

**Line output**, not a speaker amp: ~2 V p-p, DC-blocked, 100 Ω series. Whatever
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
| 5 | sample-RAM posted-write FIFO drained (for `TFM`-paced upload, §13.2) |

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

Expose it as a plain 16-bit reload register (`TIMER`, §9) with an enable bit, so
it is equally usable as a general-purpose periodic interrupt for anything else
the machine wants at a rate `/IRQ`'s 70.09 Hz cannot give it.

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
| `+$4` | `AINTREQ` | R/W | read: pending flags. write: b7=0 clears the bits set in b5..0 |
| `+$5` | `ACTRL` | W | b0 LED filter, b1 filter bypass, b2 NTSC clock, b3 reserved (was the volume curve — now table content, §6.1), b4 8-channel mode (§11.2), b5 pan enable (§11.1), b7 master enable |
| `+$6`–`$8` | `SPTR` | W | sample-RAM pointer, 19 bits, auto-increment |
| `+$9` | `SDATA` | R/W | sample-RAM byte at `SPTR`, **post-increment** |
| `+$A` | `ASTAT` | R | b3..0 channel DMA active, b4 timer running, b6 write FIFO full, b7 prefetch valid |
| `+$B`–`+$C` | `TIMER` | W | tempo-timer reload, 16 bits, clocked at **709,379 Hz** — load `1773447 / BPM` (§8.2) |
| `+$D`–`+$E` | `LIDX` | W | volume-LUT load index, 16 bits, auto-increment (§6.1) |
| `+$F` | `LDATA` | R/W | volume-LUT byte at `LIDX`, **post-increment** |

`ADMACON` / `AINTENA` / `AINTREQ` keep **Paula's set/clear bit-7 convention**
deliberately: a replayer ported from 68000 writes the same constants, and the
one-line translation from `$DFF096` to `$FF42` is the whole port for that
register.

### 9.3 The state file — index/data, and why that is not a cost

Per channel, `AIDX` = `channel × 16 + offset`:

| Offset | Name | Bytes | Paula equivalent | Note |
|---|---|---|---|---|
| 0–2 | `LC` | 3 | `AUDxLC` | **byte** address into card RAM |
| 3–4 | `LEN` | 2 | `AUDxLEN` | **words**, Paula-identical — mod length fields load unchanged |
| 5–6 | `PER` | 2 | `AUDxPER` | colour clocks |
| 7 | `VOL` | 1 | `AUDxVOL` | 0–64 |
| 8 | `DAT` | 1 | `AUDxDAT` | direct sample write, CPU-fed mode (§1 req. 8) |
| 9 | `ATT` | 1 | `ADKCON` bits | b0 attach-period, b1 attach-volume (§11.3) |
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

---

## 10. Chip budget

| Qty | Part | Role |
|---|---|---|
| 1 | AS6C1008-55 (128K×8) | sample RAM (footprint for 4 → 512 KB, §5) |
| 4 | CY7C128A-15 (2K×8, 15 ns) | channel state file, **32 bits wide** (§3.1) |
| 2 | 32K×8, 15 ns | volume LUT, `{curve,VOL,SAMP}` → 12-bit (§6.1) |
| 2 | 74HC590 | free-running 16-bit colour-clock counter (§4.2) |
| 2 | 74HC688 | 16-bit event comparator (§4.2) |
| 4 | 74HC283 | shared 16-bit adder — `NEXT`+`PER`, `PTR`+1, `CNT`−1 (slots 6–7) |
| 3 | 74HC574 | pipeline latches, stages A/B/C (§3.2) |
| 4 | 74HC574 | L and R accumulators, 13 bits each (§6.2) |
| 2 | **LTC7545A** | 12-bit parallel MDAC with input latch, L and R (§6.3) |
| 3 | TL072 | I/V ×2, filter poles ×4 (§7) |
| 1 | 74HC4066 | filter select / bypass (§7) |
| 1 | 74HC574 | posted-write data latch (host → sample RAM) |
| 1 | 74HC245 | register / state-file read-back |
| 1 | 74HC273 | `ACTRL`, master reset |
| 3 | GAL22V10-15 | sequencer + slot control; address mux + decode; interrupt/timer/`DMACON` |
| 1 | 28.37516 MHz osc | PAL Amiga master (§4.1) |
| (1) | (28.63636 MHz osc) | (NTSC, socketed option, §4.1) |
| — | 3 × R-2R / passives | filter networks, output stage |
| **35** | | **(38 with the NTSC can and the §6.2 deglitch latch)** |

Video card, for comparison: **36** (32 if the tri-state pixel bus closes).

**Where it could shrink:**
- **−2** if the §6.2 combinatorial sum is done in the accumulator instead of
  separate L/R latches (it can be; costed conservatively here).
- **−1** if the volume LUT's 12-bit output is cut to 8 (do not — §6.1).
- **−2** if the state file is 16 bits wide instead of 32, at the price of two
  accesses per slot and a 17.5 ns SRAM. Not available in 1989.

**Where it will grow:**
- **+3** for 512 KB of sample RAM.
- **+2** for per-channel panning (§11.1).
- **+1** if the §3.2 stage-B path does not close and needs the extra latch.

**Power.** Seven SRAMs, three GALs, ~15 HC packages, four op-amp channels:
estimate **250–350 mA** — roughly *half* the video card, because there are three
GALs instead of eight and nothing switches at 25 MHz. Analogue and digital
grounds must meet at exactly one point, and the `LTC7545A` reference should not
share a rail with the SRAMs. That is the only layout constraint on this card that
the video card does not also have, and it is the one that decides whether it
sounds clean.

**Area.** 35 ICs with one DIP-32, four DIP-24 and two DIP-28 fits the same
Eurocard envelope as the video card, with room for the analogue section to be
kept physically separate — which it must be.

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
discrete card is only ~25 ICs more for a part you can buy forever.

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
out which of §1's nine requirements you got wrong — **before three GALs have been
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

`W` is 16 bits, so 128 KB is three `TFM` instructions and a pointer fix-up. The
card's posted-write path retires one byte per colour clock in slot 5 —
**3.55 M/s against `TFM`'s 700 k/s**, a 5× margin, so **no `/WAIT`, no FIFO
stall, no lost writes** (§9.3).

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
| 0 | **Freeze §9's register map** and the backplane's `/FIRQ` and I/O-window assignment | one document; §16 items 4–6 answered |
| 1 | **Build the MCU card** (§12.5): STM32G431 + `LTC7545A` pair + §7's filters | plays a known module correctly through the §9 register map |
| 2 | **Write the loader, replayer and converter** against the MCU card | acceptance test: 20 varied modules, A/B against a real Amiga or a reference emulator, by ear and by capture |
| 3 | **Bench the §3.2 stage-B path** at 35 ns on a breadboard — LUT SRAM at 15 ns, driven by counters | closes with margin, or the §3.2 fallback latch is adopted |
| 4 | **Fit the sequencer GAL** with all eight slots, the shadow reload and the deferred queue | equations fit in 3 × GAL22V10; §16 item 7 answered before the 8-channel mode is promised |
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
   set/clear and the interrupt latches. **Fit it at 3 × GAL22V10 before committing
   to the budget**, and fit the 8-channel slot allocation before promising the
   mode. Same posture as [`graphics.md`](../../video/docs/graphics.md) §19 item 15.
8. **Verify the §6.2 glitch argument on the bench.** A 20 ns adder glitch at
   126 kHz *should* be inaudible after the 4.4 kHz pole. Measure it; the fallback
   is +2 ICs and no timing change, but find out before laying out the analogue
   section.
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
    software will be written against a card that does not exist. Same requirement
    as [`graphics.md`](../../video/docs/graphics.md) §19 item 13, and the MCU card of §12.5 is a
    better reference than any model.

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
- A500 filter values (360 Ω / 0.1 µF fixed pole; the 5-pole LED filter) are from
  the schematic and should be confirmed against the board revision you want to
  match — A500 and A1200 differ substantially, and the A1200's fixed pole is
  effectively absent.
