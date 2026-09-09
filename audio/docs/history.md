# Audio — archived history

Superseded material removed from [`audio.md`](audio.md) (and its companions) when the
documentation was split into present design and archived history on 2026-09-08. The
present design is in [`audio.md`](audio.md); this file is the record of what it used
to say, and why each claim changed. Section numbers refer to `audio.md`. "Aud-*" and
"D*" identifiers are findings and decisions of the 2026-09-04 review,
[`docs/design-review.md`](../../docs/design-review.md).

---

## §7.1 / §10 / §16 item 29 — the jack got a driver (2026-09-09)

§7.1 put a **line-level** signal on a 3.5 mm connector and flagged the consequence
itself:

> ⚠ **It is a line output on a headphone-shaped connector, and that will surprise
> somebody.** 2 V p-p through 100 Ω into 32 Ω headphones is about 0.5 V p-p at the
> transducer — audible, and much quieter than any other source they will plug in. The
> card drives a line input correctly and headphones badly.
>
> **The fix is priced and not taken: +1 IC.** … **It is refused for the same reason the
> original text refuses a speaker amp** — whatever drives the machine's speakers should
> not sit on a board carrying three digital SRAMs and a 28 MHz clock.

**Taken 2026-09-09.** An `NJM4556AD` — dual, 70 mA, DIP-8 — buffers §6.2's summing
amplifiers into the jack through 470 µF and 10 Ω, and **the backplane pair stays line
level**. The two outputs stop pretending to be one signal, which is the part the original
framing got wrong: it was not a choice between two levels but a failure to notice there
were two loads.

**The objection is not overturned, it is outweighed and then answered by placement.** A
headphone amplifier still does not belong next to a CPLD; it belongs next to the jack, in
the analogue section §10 already wants physically separate. What tipped it is that the
alternative was a connector that silently underdrives everything anybody plugs into it,
and a card that cannot be listened to on a bench without an external amplifier.

**The count went 31 → 32**, §10's power estimate 330–440 mA → **340–500 mA**, and the
"where it will grow" list lost its last entry — every growth line that list has ever
carried is now spent.

⚠ **What the item leaves open is the ground**, and it is the sharper half of the original
worry: the jack is the one node on this card that leaves the board into something a person
touches, and a shell bonded to a chassis is a second ground path where §10 allows exactly
one.

---

## §5 / §5.3 / §10 / §11.1 / §16 items 0 and 19 — the memory consolidated and panning was built (2026-09-08)

Three changes landed together and the count went **29 → 31**. They are one entry
because each one's arithmetic uses the others'.

### §5 — the sample RAM was 128 KB with three empty footprints

The section read **"1 × AS6C1008-55 (128 KB), footprint for 4 (512 KB)"**, with the
coverage table calling 128 KB *"the large majority of the ProTracker corpus"* and the
recommendation *"populate one chip; leave three footprints. That is +0 cost now and
+3 ICs later, and it is the same 'leave the expansion on the board' call the video card
makes for its interleave."* §10's "where it will grow" carried **"+3 for 512 KB of
sample RAM"** as a standing line.

**Replaced by one `AS6C4008`, 512K×8, in the same 600-mil DIP-32** — all of the memory,
today, in one package, and the three footprints deleted from the board. The part became
available to this card on the same day for a reason worth recording: `ram.md` §6.2
dropped the motherboard's DIP system RAM for SIMM sockets, and the `AS6C4008` datasheet,
footprint and `hardware/lib/parts.ts` entry were left with nothing citing them. **The
machine's parts list did not grow; a line item moved from one board to another.**

The video card's §14.2 had made the same move hours earlier and the argument is the
same one: *two of the four SRAM packages were width and expansion, not capacity.*

### §5.1 — "system RAM is cheap in bandwidth but needs a mechanism the machine does not have"

The system-RAM row of §5's options table read: *"Cheap in **bandwidth**, but needs a
bus-master and an arbitration mechanism the machine does not have. Not worth inventing
for 5 %."* That was true and it read as a cost judgement that could be revisited.

**It cannot be revisited, and §5.1 now says why in three structural terms** rather than
one economic one: the backplane's last position went to physical `A20` on 2026-09-08 and
`net.md` §13.1's DMA request/grant pair lost that competition, so **there are no pins**;
`machine.md` §5 item 7's fixed-phase scheme is host-facing and keyed to `CLK25` and `E`,
which §5 item 10's rule forbids a card's internal scheduling from using; and this card's
scheduling free-runs on a 28.37516 MHz can with no integral relationship to `CLK25` at
all. The 5.4 % figure survives as arithmetic and stops being the reason.

### §16 item 0 — "should the sample RAM move into the machine's physical map?"

Opened 2026-09-08 when `machine.md` §5 item 7 created the sixteen 64 KB card regions and
storage and net both claimed one. The item listed what mapping would buy — a 238 ms
chunked upload becoming 188 ms unchunked, the `TFM` doubled-write exposure gone, and the
ability to stream a module larger than the sample RAM — and priced the cost as *"the
same address and data plumbing the other two cards paid — `sdcard.md` §8 priced it at
five 74-series packages"*, with the note that **128 KB is two regions of the sixteen**.
It closed: *"Not decided here. The 50 ms is minor; closing the machine's last
doubled-write exposure is not, and it is the argument that should decide this."*

**Decided 2026-09-08: no, and the price is three packages rather than five.** §5.2 has
it. The blocker is §9.5's single-source sample-RAM address — the sentence that made the
card cheap — and a memory-mapped window needs a second source, which is a 19-bit 2:1 mux
(**3 × `74HC157`**) or nineteen more pins on a CPLD at 50 of 64. The decisive difference
from storage and net is that **their port was in the way of every sector and every
frame, and this card's is used once per module load.** The two-regions note survives:
512 KB is now eight regions of the sixteen, which makes the mapped option worse rather
than better.

⚠ **The consequence recorded with the decision is that this card is the last one in the
machine whose bulk transfer targets a side-effecting port**, and that what retires the
exposure is `sdcard.md` §11.6's `TFM` firmware choice, not anything on this board.

### §3.3 / §5.3 / §10 — the state file was three `CY7C128A`

§3.3 read: *"...and why the state file is **three** `2K×8` packages rather than four."*
§10's "where it could shrink" offered **"−2 if the state file goes to 16 bits, at the
price of two accesses per slot, a 17.5 ns SRAM that did not exist in 1989, and an
address latch for `PTR` that would cost the packages back."*

**Replaced by two `IS61C6416AL-12TLI`, 64K×16, TSOP-44** — a 32-bit file in two
packages, at 12 ns rather than 15. The shrink line's premise was that width had to be
bought with *time*; it did not, because `graphics.md` §14.2.1 had just put a stocked 5 V
×16 part on the machine's parts list for the palette LUT. The old row is replaced by a
new one — **−1 more if `PEND[7:0]` moves into the CPLD and the file becomes a single
part** — which is §16 item 28 and is not costed.

⚠ **The cost is the card's first surface mount**, and the part being replaced is the
least available thing on the board: `CY7C128A` is long out of production and its DIP-24
grade is secondary-market. §17's period audit gained a row saying so, and gained a
harder one for the `AS6C4008` — a 4 Mbit SRAM is 1992–93, two years past the 1 Mbit part
that was already *"the newest silicon on the card"*.

### §11.1 / §6.2 / §7 / §10 — panning was an option and is built

§11.1 was headed **"Panning — fixed is free, programmable is +3 ICs"** and opened
*"Fixed panning is free. Which summing node a channel's volume half drives is which
package it sits in."* §6.2's converter table specified **4 × `AD7528`, eight halves**
and closed *"Hard panning is free... And programmable panning is now +3 rather than
+10 — §11.1."* §7 listed **ten amplifier channels, nine used**, and §10's "where it will
grow" carried **"+3 for programmable per-channel panning"** as a standing line. §9.3's
state-file offset 10 said `PAN` was *"ignored unless `ACTRL.5` — and unpopulated unless
that superset is built"*.

**Built 2026-09-08.** Six `AD7528` and twelve halves: one sample and **two** volume
converters per channel, driving both sides' summing nodes. Four `TL07x` packages,
**thirteen amplifier channels of fourteen** — each volume die gets its own I/V and the
two per side are voltage-summed through a matched 0.1 % pair, because a node collecting
four ladders across two dice loses §6.2's ±1 % on-die match. `+3 ICs`, exactly as
§11.1 had priced it.

**What did not change is the acceptance test**, and that is the point of the mode bit:
`ACTRL` b5 = 0 is the reset state and makes the sequencer derive the right-hand code
from `VOL` and the channel index, so ch0,3 land on L and ch1,2 on R and a Paula-exact
replayer never writes `PAN`.

### §7 / §10 / §16 item 19 — the output had no connector, and the card had no jack

§7 ended: *"**Line output**, not a speaker amp: ~2 V p-p, DC-blocked, 100 Ω series...
Whatever drives the machine's speakers is a separate concern and should not be on a card
carrying four digital SRAMs."* It never said **where the output went.**
`graphics.md` §17 had put `AUDIO_L`, `AUDIO_R` and two `AGND` returns on the backplane
and `hardware/lib/slot.ts` carried them at B32–B35 — and **nothing in the machine
consumed them**: no chassis, no rear panel, no terminating document.

**§7.1 adds a 3.5 mm stereo PCB jack on the card's rear edge**, in parallel with the
backplane pair, which is kept unchanged. Zero ICs; it is the same two nodes wired to two
more places, and it makes the card testable on a bench with no backplane. ⚠ It also puts
a line-level signal on the connector people associate with headphones, which is §16
item 29 and is priced at +1 IC if the level is judged wrong.

### §10 / §16 item 19 — "a single-Eurocard fit"

§10's area paragraph and §16 item 19 both asserted a **single-Eurocard** fit *"asserted
and never measured"*, against *"eight converter halves and ten amplifier channels"*.
**The machine stopped using Eurocards on 2026-09-08** (`machine.md` §5 item 5): the card
format is 100 mm × 120/180/240 mm per card, and `hardware/place/` puts this card on
**18 cm** by courtyard area. The measurement item survives with the format corrected and
the analogue section restated at **twelve converter halves and thirteen amplifier
channels**, plus a rear-edge jack to place.

---

## §0 / §10 — the package-count chain: 35 → 57 → 54 → 45 → 36 → 29

The card's headline count was re-tallied five times, and the whole chain is worth
keeping because each step is an argument, not a correction of arithmetic. The
addition was never wrong — each list summed exactly as printed. What changed is what
the list included.

**35 → 57 (design review — Aud-M1, Aud-M2, Aud-M3, Aud-M4, Aud-M5, decision D9).**
The old tally counted the datapath and left out whole functions:

| Where the 22 packages came from | Δ | § |
|---|---|---|
| The L/R sum path — 4 hold latches + 6 adders. The old list had four `'574` labelled "accumulators" and no adder at all, while §6.2 claimed a combinational sum and §3.4 claimed the only adder was elsewhere. | **+10** | §6.2 |
| Host-visible counters. `SPTR`(19) + `LIDX`(16) + `AIDX`(6) = **41 flops of counter** with nowhere to live; three GALs are 30 macrocells and were already holding the sequencer. | **+6** | §9.5 |
| Host-boundary hardware: 2 staging latches for the commit-on-low-byte rule, 1 hex flip-flop for the two-flop synchronisers. | **+3** | §9.4 |
| `ADATA` read-prefetch latch — argued for in §9.3, never costed; the `'574` that *was* listed is the posted-**write** latch on the other path. | **+1** | §9.3 |
| `74HC07` open-collector stage for the wire-OR `/FIRQ`; a `GAL22V10` output is totem-pole and cannot do it. (GAL-specific — the `ATF1508AS` of §10.1 has a *Programmable Output Open Collector Option*, so the package later disappeared again.) | **+1** | §8.1 |
| Two more `GAL22V10`. | **+2** | §9.5 |
| One fewer `TL072`: the LED filter is one Sallen-Key stage per side, not two, and §6.3's bipolar offset is injected rather than subtracted. | **−1** | §7 |
| **Net** | **+22 → 57** | |

"One clock domain" fell in the same pass (Aud-M3): §0 claimed *"one oscillator, one
clock domain"* — true of everything downstream of the crystal, false exactly at the
asynchronous host port, which is where §9.4's failures live. §0 now reads "one
internal clock domain and an asynchronous host port".

**57 → 54 — the four-DAC analogue sum adopted (§6.2, §16 item 17 closed).** The
digital channel sum — fourteen packages of hold latch, adder and accumulator — was
deleted and replaced by two more converters, eight hold latches and a resistor pair.
The recorded alternative's own estimate was **−12**; it was wrong by nine packages:

| | Δ |
|---|---|
| Delete the digital sum path: 4 × `'574` hold, 6 × `'283` adder, 4 × `'273` accumulator | **−14** |
| **Per-channel DAC hold latches** — the LUT output is valid for one 35 ns slot and the converter wants `tDS` = `tWR` = **100 ns**, so each channel needs its own 12-bit latch. The recorded alternative missed this. | **+8** |
| Two more `LTC7545A` (2 → 4) | **+2** |
| One more `TL072`: **four separate dice do not match**, so each converter needs its own I/V amplifier — current-summing them as Paula does is what an 8–15 kΩ `RREF` spread forbids | **+1** |
| **Net** | **−3 → 54** |

Still the right change — it deleted the entire digital sum and its four-stage
pipeline, kept all 12 bits per channel, and cut the converter's update latency from a
frame-quantised 282–564 ns to a uniform 211 ns — but it was worth **three** packages,
not twelve. Being wrong by nine in exactly the places §16 item 17 said had to be
settled first is the argument for settling such things before quoting them.

**54 → 45 — none of it from the audio path.** The card was carrying nine packages of
state and buffering that the state file and the deferred slots were built to hold:

| Where the 9 went | Δ | § |
|---|---|---|
| `SPTR`/`LIDX`/`AIDX` move into three of the state file's 2032 spare words, incremented by the shared `'283` in a deferred slot. The state file's own outputs hold the address during the access, so no latch replaces them. | **−6** | §9.5 |
| Multi-byte commit staging becomes a shadow word in the state file; the commit is the deferred-slot copy the card already performs for `LC`/`LEN`. | **−2** | §9.4.3 |
| `74HC245` read-back buffer: the prefetch `'574` has three-state outputs and drives the host bus itself, as do the parts behind `ASTAT`/`AINTREQ`. | **−1** | §9.3 |
| **Net** | **−9 → 45** | |

In the same pass the volume LUT left the per-slot path (§3.2): no packages, but it
retired the card's only tight timing path, removed 1–2 colour clocks of
data-dependent jitter, and cut the converters' write rate by 28×. The pattern in one
sentence: **every package deleted here was state living outside the state file, or a
buffer in front of something that could already drive a bus.** The card walked 2048
words of state at 14.2 M reads a second to service 126,000 events — a 113×
over-provision — and then spent packages keeping counters somewhere else.

**45 → 36 — the volume LUT was the wrong answer to a question the converter answers
for free (§6.1).** An `AD7528` is a dual 8-bit multiplying DAC on one die; cascading
its halves puts the multiply in the analogue domain:

| Where the 9 went | Δ | § |
|---|---|---|
| The volume LUT — 2 × 32K×8, the `LIDX`/`LDATA` registers, the `LIDX` counter and the 65,536-byte boot upload — deleted. Volume becomes the code of a second converter whose reference is the first one's output. | **−2** | §6.1 |
| Converter port registers: the bus is 8 bits wide now rather than 12, and each side's two channels share one register loaded twice per frame. Eight `'574` become two. | **−6** | §6.2 |
| State-file word 0 is `{NEXT[15:0], PEND[7:0]}` — 24 bits, three packages instead of four, with the 19-bit `PTR` still arriving in one read. | **−1** | §3.3 |
| 4 × `LTC7545A` → 4 × `AD7528`. Same package count, twice the converters, and the ±1 % on-die `VREF` match is what lets §6.2 sum currents at one node. | **0** | §6.3 |
| **Net** | **−9 → 36** | |

Not a fidelity trade: the sample keeps its 8 bits (all Paula has), the volume gets 8
(`VOL` × 4), and the product is not quantised at all where the table quantised it to
12. `VOL` = 0 became exact silence instead of a `$800` pedestal. The one regression
is glitch — 160 nV·s against the `LTC7545A`'s 5 — which §3.2's 28× write-rate cut
blunts and §16 item 9 exists to measure.

**36 → 29 — the six-GAL allocation into one `ATF1508AS`.** The interrupt block fits
no `GAL22V10` in either arrangement (§9.5 — fitted 2026-09-07,
`hardware/gal/audio.jedec.ts`, both refusals asserted by `check:audio`), which took
the GAL allocation to six parts and the six parts to a single PLCC-84 CPLD. The CPLD
also absorbed the `'273` (`ACTRL`/reset), the `'174` (host-port synchronisers) and
the `'07` (`/FIRQ` open-collector stage, via the part's *Programmable Output Open
Collector Option*). Along the way the tally was quoted as "36 with five GALs, 37 once
the fit found six".

**Power and area, old figures.** 250–350 mA and a "roughly half the video card"
gloss went with the 35-package tally; the present 300–400 mA estimate arrives in the
same neighbourhood by a different route — a smaller digital section and a larger
analogue one. The old area text asserted a single-Eurocard fit at 35 packages; the
review took the count to 57 and the assertion with it; three passes brought it back
down, and the assertion has still never been measured (§16 item 19). "Carrying seven
digital SRAMs" in §7's output note became four when the LUT pair and the fourth
state-file package went.

---

## §3.2 — the pipeline had a fourth stage, then a table, then neither

Stage B originally did `LUT read {VOL,SAMP} → 12-bit sample` *every slot for every
channel*, refreshing a hold latch with a value that was almost always the one already
in it: 14.2 million lookups a second to produce 126,000 changes. That is what made
stage B "the card's only tight path", what forced a 15 ns SRAM grade, and what held a
`+1 '574` fallback in reserve (§16 item 2, since retired). Precomputing each
channel's next byte into `PEND` during the deferred slots deleted the path; §6.1 then
deleted the table itself, because the volume multiply moved into the converter.

The old arrangement also had data-dependent jitter the document did not admit to:
with the table in the loop, a channel's new sample reached its converter only after a
deferred slot had fetched the byte and written `SAMP` back — and the deferred queue
holds four channels while draining two per colour clock, so on coincident events the
third and fourth channels were **1–2 colour clocks late**, while §6.2 claimed the
converter's input changes on the exact colour clock the sample changed on. With
`PEND` the event-instant work is a flag and a fixed write window, so the claim is
finally true.

---

## §3.3 — word 0's packing, corrected twice

Word 0 was first written as `{NEXT[15:0], VOL[5:0], SAMP[7:0], DMAEN, ATT}`. §6.1's
correction then gave `VOL` its seventh bit (0–64 is 65 levels), which makes
16 + 7 + 8 + 1 + 1 = **33** — one bit past the state file's 32-bit width, and the
32-bit width is the whole reason stage A is a single access. The first fix moved
`ATT` to word 1 (consulted only on a compare hit, which reads words 1–3 anyway),
restoring exactly 32.

Then the word became `{NEXT[15:0], PEND[7:0]}` = **24 bits**, and the state file lost
a package. `VOL` and `SAMP` were in word 0 because stage B fed them to a volume LUT
every slot; §3.2 stopped doing that and §6.1 deleted the LUT outright, so `VOL` and
the flags joined `LC`/`LEN`/`PER`/`PTR`/`CNT` in words 1–3, where the deferred slots
read them anyway.

---

## §3.4 / §6.2 — the channel sum, superseded three times

The history is worth keeping because the first fix was correct about the fault and
wrong about the remedy — and the word "combinatorially" was reaching for the right
answer all along.

1. §3.4 originally claimed **"the only adder on the card is the shared 16-bit `'283`
   chain in slots 6–7"** while §0 and §6.2 claimed the four channels were summed
   **"combinatorially, asynchronously"**. Both could not be true, and neither was
   costed (Aud-M2).
2. The fix was **latched accumulation with dedicated 12-bit adders** — fourteen
   packages, a fourth pipeline stage, a frame-boundary clear that had to be ordered
   against the DAC's write, and a `>>1` that cost a bit of every channel. It worked;
   it was expensive.
3. **What "combinatorially" was reaching for is what Paula does: an analogue sum.**
   The four-DAC revision did that — one converter per channel, summed after the I/V
   stage — but could not sum *currents*, because four separate dice do not match
   (`RREF` 8–15 kΩ part to part put `ch0` and `ch3` up to 5.5 dB apart), so it spent
   four I/V amplifiers and eight hold latches instead. The dual `AD7528` removed the
   last obstacle: two ladders on one die match to ±1 % (0.09 dB, tracking over
   temperature), and the sum is two wires into a virtual ground, the way it is inside
   a Paula.

With the digital sum gone, §3.4's original sentence is simply true again.

---

## §4.1 — 8286 Hz

The headline pitch example previously read **8286 Hz**. `3,546,895 / 428 = 8287.14`;
the reference model's unit test asserts 8287 (design review, Audio NOTE). One digit,
in the document's own headline example of the number the whole card exists to
reproduce.

---

## §6.1 — the volume LUT, `LIDX`/`LDATA`, and the boot upload

§6.1 specified a 32K×8 SRAM pair addressed by `{VOL[6:0], SAMP[7:0]}` → 12-bit
offset binary, host-loaded through a `LIDX`/`LDATA` pointer/data pair at `+$D`–`+$F`,
and called the volume curve "table content, not hardware". Everything in that
argument was sound except its premise: the multiply did not need to happen in the
digital domain at all. Deleted with it: 2 × 32K×8 (§10), the 15 ns grade, the
`+$D`–`+$F` registers (§9.2), the `LIDX` counter (§9.5), the ~94 ms `TFM` upload at
boot, and 4 of the 8 packages of DAC hold latch — the port became 8 bits wide, not
12.

The one thing the deletion took was the **programmable volume curve**, which §6.1
was right to want; it came back as host software via `ACTRL` b3 (raw-volume mode).
The `XOR #$80` offset-binary fix, previously baked into the LUT's contents, moved to
the loader (§16 item 27). "Silence is exactly zero" replaced the old arrangement's
forcing of the LUT address to `VOL` = 0 to get `$800` onto the bus for a disabled
channel.

---

## §6.3 — the 12-bit converter, and the pedestal polarity

§6.3 specified a 12-bit `LTC7545A` per channel and spent two pages establishing that
the plain `AD7545` could not be clocked fast enough at 5 V (`tWR` 250 ns at 25 °C,
400 ns over temperature, against a 281.9 ns frame) while the `AD7545A` and `LTC7545A`
could (`tWR` 100 ns). That analysis was correct and is why
[`AD7545.pdf`](../../reference/datasheets/) and
[`LTC7545A.pdf`](../../reference/datasheets/) are still in the repo. It stopped being
load-bearing when the multiply moved into the analogue domain: with an 8-bit cascade
there is nothing for the extra four bits to carry. §16 item 15 (the missing `AD7545A`
datasheet) and item 16 (the `LTC7545A`'s unverified production status and ~$9 price)
retired with it.

An earlier revision also had the pedestal-cancellation resistor's polarity
**backwards** — a resistor to `+Vref` doubles the pedestal rather than cancelling it.
And before the cancellation moved upstream of the volume stage, the design carried a
`$800` silence convention, doubled-offset arithmetic in the digital sum, and an
"output capacitor is load-bearing" argument — all deleted rather than corrected once
the output became exactly zero at `VOL` = 0.

---

## §7 — the LED filter was specified 5-pole; the A500's is 2nd-order (Aud-M4, D7)

The filter table specified the LED filter as **"5-pole Butterworth: two Sallen-Key
stages + the fixed pole"** at ≈3.3 kHz. **The A500's LED filter is second-order**:
the real chain is a fixed 1-pole RC at ≈4.4 kHz plus a *switchable* 2nd-order
Butterworth Sallen-Key at ≈3.2–3.3 kHz. Every faithful model implements it that way —
`pt2-clone` and libopenmpt's `a500` filter are both two-pole, and the 3275 Hz corner
already used by this project's reference renderer *is* `pt2-clone`'s two-pole corner,
transplanted under four poles it never had.

The error was two whole poles — 12 dB/octave of roll-off the A500 does not have:

| Above cutoff | Correct (3-pole) | As specified (5-pole) | Error |
|---|---|---|---|
| 6.55 kHz — one octave | ≈18 dB down | ≈30 dB down | **12 dB too dark** |
| 13.1 kHz — two octaves | ≈36 dB down | ≈60 dB down | **24 dB too dark** |

LED-on material would have lost most of its top two octaves — a direct violation of
the "Paula-exact" acceptance test of §1, on the one path a module can switch at will
with `E0x`. **Nothing caught it** because the A/B ladder has no probe that toggles
`E0x`, so the filter was only ever compared in its fixed-pole state — which is why
§16 item 18 exists. §18's sources note also carried the wrong 5-pole reading of the
A500 schematic.

The amplifier-channel budget's evolution across the revisions:

| Amplifier channels | As first written | After Aud-M4 | 4 × `LTC7545A` | Cascade (present) |
|---|---|---|---|---|
| Sample-converter I/V | — | — | — | 4 |
| `−Vref` inverter | — | — | — | 1 |
| Summing I/V | 2 | 2 | 4, one per converter | 2 |
| Bipolar offset subtractor | (unbudgeted) | 0, offset injected | 0, DC-blocked | 0 — cancelled upstream |
| LED Sallen-Key stages | 4 (two per side) | **2** (one per side) | 2 | 2 |
| **Total** | 6 = 3 × `TL072` | 4 = 2 × `TL072` | 6 = 3 × `TL072` | **9 of 10 = 2 × `TL074` + 1 × `TL072`** |

Three packages either way; the shape changed rather than the count. The four
amplifiers that used to exist because *four separate dice do not match* became four
amplifiers that exist because there are four sample converters, and the summing
amplifiers went back to two because the ±1 % on-die `VREF` match lets the currents
meet.

---

## §8.1 — `AINTREQ` bit 5, and the `/FIRQ` stage

**Bit 5** used to read *"sample-RAM posted-write FIFO drained (for `TFM`-paced
upload)"* (restated by design review, Audio NOTE). That motivation does not survive
its own document: §13.2 proves the depth-1 posted-write path retires at 3.55 M/s
against `TFM`'s 700 k/s — a 5× margin — so a *drain* interrupt can never fire, has
no consumer, and could not pace anything if it did (`TFM` is a single interruptible
instruction, not a loop that waits on a flag). The bit was inverted in meaning: it is
now a sticky **overrun error** flag with a real consumer — the loader, once after
each `TFM` burst. On a 2.098 MHz 6309 it can never set; on the §12.5 MCU card, or
any host faster than 3.55 M/s, it can.

**The `/FIRQ` stage** was a discrete **`74HC07`** (+1 IC, decision D9) for as long as
the logic was GALs: a `GAL22V10`'s outputs are totem-pole, and driving a wire-OR line
from one is a bus fight. On the CPLD the pin uses the `ATF1508AS`'s *Programmable
Output Open Collector Option* and the package is gone. §17's period table carried the
`74HC07` row (1982; bipolar `7407` 1965) and a `GAL22V10` row (1986) for the same
reason; both left with the CPLD consolidation.

---

## §8.2 — the timer enable that was promised and never allocated

`ACTRL` b6 (decision D7) was promised in §8.2 and never allocated in §9.2, which
left the map with a timer that could be started and never stopped: once `TIMER` holds
a non-zero reload the compare in slot 4 fires forever, `AINTENA` b4 can mask the
interrupt but not the timer, and there is no clean "stop the music" path — not for a
replayer shutting down, not for `ACTRL` b7's master enable, and not for a NitrOS-9
process being killed.

---

## §9.1 — "geographic" decode, until 2026-09-06

§9.1 said "decode is geographic, from the backplane's per-slot `/IOSEL`, so the base
is a jumper, not a wire" — and the two halves of that sentence contradicted each
other. A per-slot decode fixes each card's window by position, which leaves a
base-address jumper nothing to select — and this card's window is 16 bytes where
PS/2's is 4, which no slot-sized decode produces. `/IOSEL` is the `$FF40`–`$FF7F`
window strobe, common to every slot, and the card completes the decode from `A0`–`A6`
(first written `A0`–`A5`, one line short of a 16-byte window at that base). The claim
came from `graphics.md` §17, which copied it from colormin, where it was true;
`machine.md` §2 now owns the window assignment.

---

## §9.2 — the map-freeze rationale

`ACTRL` b4 (8-channel mode): the reference header defined it at **b3**; b3 is the
reserved bit vacated when the volume curve became table content, and reusing a
vacated bit for a new mode is how a map acquires two meanings for one position —
hence b4, decision D7, with `card.h` following the document. `ASTAT` b6 was a
placeholder called "write FIFO full", which named a FIFO the card does not have (the
path is depth 1, so "busy" is the honest word); b7 was likewise a placeholder before
being defined as prefetch-valid. `+$D`–`+$F` were `LIDX`/`LDATA`, the volume-LUT
load path, deleted with the table itself.

---

## §9.3 — the prefetch latch, and the `'245`

The prefetch latch was argued for in §9.3 and never costed (Aud-M5); the `'574` the
old §10 *did* list is the posted-write **data** latch on the opposite path. Then the
`74HC245` read-back buffer went too: the old text argued the `'245` "is not a
substitute" for the prefetch latch — true, and an answer to a question nobody asked
(a transceiver cannot store) — without ever establishing that anything has to
*buffer* a latch that already drives three-state outputs onto the bus. −1 package;
the drive check (74HC sources 6 mA) became §16 item 26.

---

## §9.4 — the host boundary the document said did not exist

§9.4's heading was "Crossing the host boundary — the part §0 said did not exist"
(Aud-M3; see the §0 entry above). The commit-on-low-byte staging rule first cost
**2 × `74HC574`** of discrete staging — state living outside the state file, which
is what the whole card is for; the packages were deleted and the rule kept as a
shadow word. §9.4.3 also carried the observation that the reference model had
already discovered the rule once: tearing broke the tempo when the reference player
wrote `TIMER`'s two bytes separately, so `TIMER` was given commit-on-low-byte
semantics — the finding was that `PER`, `LC` and `LEN` needed the same rule and
never got it. The three two-flop synchronisers of §9.4.4 were a discrete `74HC174`
before the CPLD absorbed them.

---

## §9.5 — where the counters lived before the state file

§9.5 itself was **added** by the review (Aud-M5): the old §10 tallied 35 packages
with three `GAL22V10` = 30 macrocells total, and asked those 30 macrocells to hold
the entire slot sequencer *and* 41 flops of host-visible counter (`SPTR` 19 +
`LIDX` 16 + `AIDX` 6). They do not fit, and the document never said where they were.

The first repair put the 41 bits in **6 × `74HC593`** (8-bit counter, input
register, three-state outputs), arguing that beat eleven `'161`. Both answers were
wrong about the question: the card already owns 2048 words of 32-bit state and uses
sixteen, and already owns a 16-bit adder running at 126 kHz against 7.1 M deferred
slots per second — so the counters moved into three spare state-file words and the
packages went away. (`LIDX` itself was later deleted with the volume LUT.)

The GAL allocation then grew from the review's five to six when the interrupt block
was actually fitted (2026-09-07): `INTREQ`(6) + pending(6) + `/FIRQ` = 13 equations
for 10 macrocells whole, or 17 input pins against 14 split — both refusals asserted
by `check:audio`. "Why five GALs and not three" — `INTENA`(6) + `INTREQ`(12) +
`DMAEN`(4) = 22 registered bits with feedback before a single term of sequencer —
was the standing argument until the fit answered it with "neither": six GALs, which
is what took the card to the single CPLD. The risk was never the count; it was that
the fit had not been run. The old §9.5 allocation table (GAL 1–5 by function, with
the `INTREQ` row marked "does not fit") is condensed in the present table's "CPLD"
rows.

---

## §11.1 — programmable panning: +2, then +10, then +3

| Sum | Programmable panning costs | Because |
|---|---|---|
| Digital accumulator | **+2** | widen the volume LUT to hold `(L gain, R gain)`; the accumulators already existed |
| Four 12-bit converters, analogue sum | **+10** | nothing to steer: a second converter *and* a second hold latch per channel, plus the wider LUT |
| **Cascaded dual converters (present)** | **+3** | a second volume half per channel — and halves come two to a package |

The clearest illustration of what the architecture actually charges for.

---

## §12.2 — the RF5C68 gap

The gap between the discrete card and a ~10-IC `RF5C68` card was quoted as ~25 when
§10 said 35, ~26 at 36, and is ~19 at 29. The middle figure was the one place the
review's re-tally made a rejected alternative look meaningfully better, recorded
rather than glossed. Availability decided it at every count.

---

## §13.3 / §16 item 27 — where the `XOR $80` went

§13.3's converter table used to carry an `XOR $80` on its first row; item 27 moved
the flip to the loader (`LDD`/`EORD #$8080`/`STD`, ~690 ms rather than 187 ms for
128 KB, or ~738 ms chunked). The alternatives and why they lost, in full: the
**offline converter** was free and kept the loader's verbatim `TFM` at 187 ms, but
only for modules prepared in advance — a player whose fast path requires a
proprietary pre-processing step is a player for a curated library, not for the
corpus, and the corpus is the entire reason §4.1 refuses to resample (rejected on
scope, not cost). The **one-gate inverter** on the sample-RAM-to-state-file fetch
path left card RAM two's complement for +1 package — but made `DAT` the one register
that does not follow the rule, a permanent cost paid by every future reader of §9,
against a card whose §16 item 19 problem was being one package over its envelope
(rejected on packages and on the register-map exception).

---

## §14 — the resolution row

The comparison table's resolution entry read "8 bit × 6-bit volume, **12-bit out**"
while the volume LUT existed; the product is now formed in the analogue domain and
is not quantised at all.

---

## §16 — retired and rewritten open items

- **Item 2** (bench the stage-B LUT path at 35 ns) — retired when `PEND`
  precomputation gave the lookup a 70.5 ns window, then mooted entirely when §6.1
  deleted the LUT; the `+1 '574` fallback latch was withdrawn with it.
- **Item 7** — was "fit the sequencer at **5 × GAL22V10** before committing to the
  budget"; the fit was run, found six, and the six became the CPLD. The item now
  covers only the unfitted 8-channel slot allocation.
- **Item 8** (verify the §6.2 glitch argument on the bench) — retired twice over: it
  was a consequence of the combinational sum, which §6.2 stopped specifying at
  Aud-M2, and there is now no adder in the audio path at all.
- **Items 15–17** — see the §6.3 and §0/§10 entries above.
- **Item 19** — the envelope item tracked the count through 35 → 57 → 36 → 29; the
  single-Eurocard assertion has never been measured at any of them.
- **Build step 4** — was "equations fit in 5 × GAL22V10 as allocated in §9.5"; done
  2026-09-07 as the `ATF1508AS` fit instead.

---

## §18 / §10.1 comparison — cross-references that moved

§18 credited `graphics.md` §9 as "the palette LUT argument this card's volume LUT
copies" — gone with the LUT. §10.1's I/O-headroom note originally read "the I/O
figure was estimated, not fitted", and the estimate (~48) came in at 49 against the
fit — closer than this project's estimates usually manage; the surviving text keeps
only the headroom argument. The "video card, for comparison: 36 (32 if the tri-state
pixel bus closes) — this card is no longer the small one" framing tracked video's
own chain down to 27, where the two cards land within two packages of each other.

---

## `modplayer.md` — the order table at 470 (design review, Audio NOTE)

The 15-sample Soundtracker row read *"order at 470"*. The 15-sample header is 20
bytes of title plus 15 × 30-byte sample headers = 470, and offset 470 is where the
*songlength* byte sits; the order table is at **472**. Reading it from 470 shifts it
two bytes and plays the wrong patterns from the first position — the 15-sample
analogue of the pattern-count bug, with the same signature: a module that loads
without complaint and is simply not the song. The loader had it right; the table did
not. The correct layout is in `modplayer.md` §4.

## `README.md` — "+0.0 cents tuning" withdrawn as an exit criterion

The README claimed step 0 closed with "+0.0 cents tuning". The A/B harness's
spectral check runs at 24 bins/octave — **50 cents per step** — thresholded at
±12 cents, so it can only return an integer multiple of 50 and can only pass at
exactly 0; every error the design brief is about (a wrong crystal at +16 cents, one
finetune step at 12.5) is smaller than one step. What step 0 actually closed is *"no
tuning error larger than 50 cents"*. The limitation is kept live in `modplayer.md`
§8 and `audio.md` §16 item 22, with parabolic/FFT peak interpolation (~1 cent) as
the corrected method.

The README also summarised the review's three overturned specification claims —
offset-binary DAC coding (Aud-M1), the latched-then-analogue channel sum (Aud-M2),
and the 2-pole LED filter (Aud-M4) — and the full IC-count chain; both summaries are
covered by the entries above.
