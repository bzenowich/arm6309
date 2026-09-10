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


---

## 2026-09-09 — design-review2.md's correction

### §7.1 — the series resistor's insertion loss

**Was:** *"Series `R` | **10 Ω** … Into 32 Ω it costs 2.6 dB"*.

**Why it moved:** 20·log₁₀(32 / (32 + 10)) = **−2.4 dB**. Arithmetic, and it does not
change the conclusion — 15.6 mW into 32 Ω has headroom for it either way.

### §10 and §9.4.5 — what the fitted CPLD contains

**Not superseded — annotated.** Neither section's text was wrong about what it
describes; what was wrong was §10's parts-table claim that the `ATF1508AS` holds *"the
whole of the card's logic"*, when it holds §9.5's six-GAL allocation and none of the
sequencer. §10.1.2 and §16 item 00 now say so, and `../../docs/design-review2.md` §2.1
has the census. §9.4.5's ordering rule is right and its fitted equation delivers an
interrupt one time in eight — §16 item 0a.


---

## 2026-09-09 — §9.4.5's merge

**Was:** `MERGE = CCLK & SYNCR2 & !SYNCR1`.

**Why it moved:** that is the trailing edge of a host read of `AINTREQ` rather than the
absence of one, and it made the card's interrupts undeliverable twice over — nothing
merged unless the host read the register, and even then only on the one slot in eight
where the edge met a colour clock (measured: 2 of 16 read phases). §9.4.5's own wording
is the fix: merge on the colour clock, suppressed while a read is in flight, which is
`CCLK & !SYNCR2 & !SYNCR1`. `../../docs/design-review2.md` §2.2.


---

## 2026-09-09 (second pass) — the sequencer, the second CPLD, and three signals nothing produced

The pass that closed `../../docs/design-review2.md` A-1. Everything below moved out of
[`audio.md`](audio.md) on the same day; the present design is §9.1, §9.3, §10.1, §10.2
and §16 items 00, 0b, 30 and 31.

### §10.1.2 — "What the part does not contain"

The section is now a stub. It read:

> **The fit is real and the part is two-thirds empty, and the reason is that the audio
> engine is not designed.** `audio.cpld.ts`'s complete input list is `A0`–`A3`,
> `D0`–`D7`, `E`, `RW`, `SEL`, `RESET` and `SET0`–`SET5`: address, data, the bus
> strobes, and six "an interrupt happened" flags. **There is no state-file data, no
> compare result, no `PER`, no `NEXT`, no `PEND`** — and no state-file address, no
> state-file `/WE`, no sample-RAM `/WE`, no `AD7528` `CS`/`WR`/`DAC`-select, no `'574`
> clock and no adder control among the outputs.
>
> So the following, each of which this document describes as designed, exists in no
> design file: §3.2's three-stage pipeline; §3.1's deferred-work scheduler beyond a
> one-bit handshake; ⛔ **§3.3's `LC`/`LEN` shadow copy at `CNT` = 0**, which §3.3 itself
> calls *"the single highest-value line in the sequencer GAL"*; §4.2's hit handling and
> its `PER` clamp; §6.1's `VOLCODE` derivation; §6.2's two converter write windows;
> §8.2's timer **compare and reload** (only the ÷5 prescale is built); §9.3's `AIDX`
> and `SPTR` auto-increment; §9.2's `ASTAT`; ⛔ **§9.4.3's normative multi-byte commit**;
> §11.1's pan multiplexer; §11.3's attach modulation; §11.2's 8-channel mode; and §1
> requirement 6's `DMACON` restart delay.
>
> **So §1's acceptance test cannot be evaluated from the design.** Whether this card
> plays a `.mod` accurately, whether it is jitter-free and whether panning works are all
> properties of the sequencer.

**Why it moved:** every one of those blocks now has a home, a micro-op sequence and a
package in §10.2 — which is the difference between a list of absences and a design. The
list itself was accurate and is kept here verbatim, because it is what the work
breakdown in §16 item 00 was derived from.

### §0 / §10 / §10.1 — "32 ICs, one `ATF1508AS` for the logic"

**Was**, in §0's table and §10's total: *"**32 ICs** (§10), one `ATF1508AS` PLCC-84 for
the logic"*, with §10.1 headed *"One CPLD, and why the counter and comparator stay
outside"* and §0 reading *"Net: 32 ICs — the logic is one `ATF1508AS` PLCC-84 (§10.1),
fitted at 79 of 128 logic cells and 50 of 64 I/O, and ⚠ the fit predates §11.1's panning
and §5.3's state file, both of which add terms and neither of which adds a pin"*.

**Why it moved:** `npm run census:audio` enumerates the sequencer's interface at **~69
I/O** against the **seven** U1 has left after the 2026-09-09 refit, and the merged
alternative — everything on one die, which saves the ~31 crossing nets — wants **~143
logic cells** where no `ATF1508AS` has more than 128. The split saves cells and spends
pins; the merge saves pins and spends cells; neither one-part arrangement exists. And
the same enumeration found **six datapath packages §10's table had never counted** —
the adder's two operand latches, the `$FFFF` constant, the three-state path from the sum
back to the state file, and the sample-byte hold. **32 → 39**, and §10 now says plainly
that the number is not settled until U2 is fitted and the board is drawn.

The caveat about the fit predating panning went too, and not because it was addressed:
`PAN`, the `ACTRL` b5 multiplexer and the converter chip selects are all the
*sequencer's*, so they were never going to move U1's numbers. §16 item 30.

### §9.1 — "the base is a jumper, not a wire"

**Was:** *"Decode is from the backplane's `/IOSEL` — the `$FF40`–`$FF7F` window strobe,
common to every slot — and the card completes it from `A0`–`A6`, so the base is a
jumper, not a wire."*

**Why it moved:** two things. The window is `$FF00`–`$FF7F` since it widened to 128
bytes on 2026-09-08, so `/IOSEL` no longer implies `A6`; and ⛔ **`SEL` was an input pin
of the CPLD that nothing on the card or in any design file drove** — the sixteen bytes
at `$FF40` were selected by a signal that did not exist. It is
`SEL = /IOSEL & A6 & !A5 & !A4` on U1 now, hard-decoded rather than jumpered, because a
jumper costs two pins and a mux term on a part with seven pins left and
`machine.md` §2 assigns the window anyway.

### §9.3 — "that latch is the whole read-back path"

**Was:** *"**And that latch is the whole read-back path — the `74HC245` is deleted.** A
`'574` is an octal flip-flop *with three-state outputs*: enable it on `/IOSEL·R/W` and it
drives the host data bus itself. Every other readable byte on the card — `ASTAT`,
`AINTREQ`, the `ACTRL` shadow — is a CPLD output, three-state too."*

**Why it moved:** the argument is right and none of it was built. `D0`–`D7` were
*inputs* of the CPLD, the `'574` had no output enable, and **nothing on the card could
drive the host data bus** — so `AINTREQ` and `ASTAT` were unreadable and §8.1's
"read `AINTREQ`, then clear what you saw" was unexecutable. `D0`–`D7` are bidirectional
I/O macrocells now (eight logic cells, no pins) and `PFOE` enables the `'574` at `+$1`
and `+$9`.

### §9.5 / `adec` — `SFCE` and `SRCE`

**Was:** two active-low CPLD outputs named for memory pins, decoding the host's `+$1`
and `+$9`.

**Why it moved:** the sequencer drives the state file's and the sample RAM's control
lines every slot, so a second output named `SFCE` is two drivers on one `/CE` — the
shape `../../docs/design-review2.md` V-2 records for the video card's `WSTB`. They are
`HSFREQ`/`HSRREQ`, active high, and they are requests the sequencer retires in slot 5.

### §3.1 / §3.2 — the deferred-slot margins

**Was:** §3.1's *"at most 126,000 pointer updates per second against 7.1 M deferred
slots per second, a **56× margin**"*, and §3.2's *"After a hit the deferred slots fetch
the next sample byte from card RAM, advance `PTR`/`CNT` (or reload from `LC`/`LEN`), and
write the byte into `PEND`: **four slots, at most** … four coincident channels need
sixteen."*

**Why it moved:** writing the micro-ops out (§10.2.3) counts the slots. A state-file
read-modify-write is two slots, a channel hit is four of them plus the sample fetch —
**eight**, and twelve when the buffer ends. The margin is **7×** at ProTracker's top
note and **1.9×** at §4.3's extended floor, not 56×; four coincident channels need
**thirty-two** slots, not sixteen. ⭐ **The conclusion survives**: the throughput floor
is `PER` ≥ 16 and §4.3's conservative ~30 sits above it, so the extended period range is
still real. It is the *margin* that was an order of magnitude out, which matters because
§3.1 quoted it as the reason the deferred slots are not worth thinking about.

### §3.3 — "`LC`, `LEN`, `PER`, `VOL`, `PTR` and `CNT` live in words 1–3"

**Why it moved:** those fields are 105 bits and three 32-bit words are 96. The file
gives each channel eight words (§10.2.1), which costs nothing at 64 words of 65,536 and
makes the word address `{ch, w}`. §3.3's packing had already been corrected twice
before (see the entry above); this is the third.


---

## 2026-09-09 (third pass) — the sequencer was built, and six claims did not survive it

The pass that closed §16 item 00. What moved is what the *design* contradicted; the
present text is §10.2 and §16 items 00 and 0b.

### §10.2 — "specified here, not fitted"

**Was:** a work breakdown — *"§10.2 is the design … What remains is the part only
`fit1508.exe` can answer, and it is four pieces of work"*, with a table of steps a, b, c
and d, and a pin budget labelled *"an enumeration and not a fit"*.

**Why it moved:** all four were done the same day. The estimate was **~69 I/O**; the
part is **63 of 68**, and the difference is instructive — the enumeration charged for
`D0`–`D7` (the datapath carries the host's byte through the posted-write `'574`, so only
`D0`–`D5` for `AIDX` are needed), for five decoded slot phases (three counter bits and
U2 decodes them), and for a `74HC139` and a `74HC138` that turned out to be one package.

### §3.1 / §3.2 / §10.2.5 — the deferred-slot margin, corrected a third time

**Was**, in order: §3.1's *"a **56× margin**"*; then, when the micro-ops were first
written out, *"eight deferred slots each … a **7× margin** at ProTracker's top note and
**1.9×** at §4.3's extended floor"* against 7.09 M deferred slots/s; and §3.2's *"four
coincident channels need **thirty-two**"* with a floor of `PER` ≥ 16.

**Why it moved:** 56× counted pointer updates rather than slots. 7× counted eight slots
against **two** work slots per colour clock — but the microprogram makes no distinction
between §3.1's "host service" slot 5 and its "deferred" 6–7, so there are **three**, and
a channel event is **seven** slots and not eight. `audio_tb` counts the seven rather than
asserting them. The margin is **46×** at C-2, **12×** at ProTracker's top note and
**3.2×** at §4.3's floor, and the throughput floor is `PER` ≥ 10.

### §8.2 — the tempo timer's ÷5 prescale and its own 16-bit count

**Was:** *"the timer's **own** 16-bit count lives beside its `NEXT` in one 32-bit state
word, `{CIACNT[15:0], CIANEXT[15:0]}`, and the shared adder increments it in a deferred
slot every 5 colour clocks. That is 709,379 increments/s against 7.1 M deferred slots/s —
**10 % of the deferred budget**"*.

**Why it moved:** it is 2 slots per tick, not 1 — **1.4 M of 10.64 M, 13 %** — and it is
unnecessary. A CIA period of `N` ticks is exactly `5N` colour clocks, so the timer's next
fire time is kept in **colour clocks** and compared against the same free-running counter
the channels use, which is what the section's own *"a fifth entry in the compare
structure of §4.2"* says. The only arithmetic is `CIANEXT += 5 × TIMER` once per period
at ~50 Hz — **500 work slots a second**. The ÷5 prescale stays on U1 as `CIACLK`, on a
pin, because §8.2's claim is that this card's tempo reference *is* the Amiga's.

### §9.5 — "`AIDX` … at a fixed address the sequencer knows, which is what breaks the circularity"

**Was:** `AIDX` in the state file, word `$7F`.

**Why it moved:** ⛔ **it does not break the circularity.** To find the byte `AIDX`
names, the sequencer must first *read* `AIDX` — out of the file whose address it is
computing — and Case A's U2 has no data bus. `AIDX` is six registers on U2 loaded from
`D0`–`D5`, and those six pins are the only reason U2 sees the host's data at all.
`SPTR` genuinely can stay in the file, because it is used as an **address** and the
sample RAM takes it straight off the read bus (§9.5's own single-source argument).

### §9.4.4 — the synchroniser captured that an access happened, and not which one

**Not superseded — completed.** U1's `NEWREQ` is the **trailing** edge of a synchronised
access, which is after `E` has fallen and the address may already be gone; the decoded
strobes it was meant to qualify are combinational and gone with it. Nothing on the card
captured **which register** a host access touched. U2 latches the offset and R/W on the
**leading** synchronised edge. `SYNCH`, `NEWREQ`, `DEFREQ`, `DEFACK`, `HOSTREQ`, `SYNCS`,
`HSFREQ` and `HSRREQ` left U1 with it.

### §10 / §0 — 39 ICs

**Was:** 39, of which seven had come from enumerating the datapath.

**Why it moved:** **45.** Six more came from *building* it, and each answers a question
the enumeration could only ask — two more converter port registers (§6.2's two windows
collide with the walk order), two more prefetch latches (§9.3's read-back is one per
state-file byte lane), a `74HC138` for the converter control code, and a `74HC00` to gate
the byte-lane write enables with the slot clock's second half.

### §6.2 / §16 item 31 — the converter port registers

**Was** (§16 item 31, opened the same morning): *"it is one register per channel (+2
`74HC574`, each three-stated onto its package's shared port) or a re-ordered walk … Decide
both when the board is drawn."*

**Decided: one per channel.** The walk order is §3.1's jitter argument and is not
available to trade. Their clocks and the three chip selects are one 3-bit code through a
`74HC138`, which is also §10.2.6's pin lever, so the two decisions paid for each other.


---

## 2026-09-09 (fourth pass) — 45 to 35: panning given up, and U1 absorbing seven packages

The user's question was *"I'm surprised it ballooned to 45 ICs… I see a lot of '574 and
'244 chips"*, and it was a fair one. The answer was three decisions, two of which were
reversible.

### §11.1 — programmable panning, built and then given up

**Was:** *"⭐ Panning — programmable, built, and +3 ICs … **The mechanism is one more
volume converter per channel.** Give each channel a second volume half fed from the same
sample voltage, driving the opposite side's summing node"*, with a cost table ending
*"**Total** | **+3 ICs**, where the four-converter analogue sum would have charged 10"*.

**Why it moved:** the user gave it up — *"that was originally pitched as 'just 2 chips'"* —
and the honest count was **six**: two `AD7528`, one `TL074`, and W5's second pass over all
four converter port registers. What replaces it is what every MOD already assumes, and
what §1 requirement 5 already required: **fixed LRRL**, channels 0 and 3 to the left
summing node and 1 and 2 to the right. That is which node an output is *wired* to.
`ACTRL` b5 is withdrawn and `PAN` (§9.3 offset 10) is reserved.

### §4.2 / §9.3 / §10 — the counter, the comparator and the read-back latches

**Was:** *"**2 × `74HC590` + 2 × `74HC688` = 4 ICs for all four channels**"* outside the
logic, and §9.3's read-back as *"three `'574`s, one per state-file byte lane"*.

**Why it moved:** ⭐ **sixteen pins bought seven packages.** Giving U1 the state file's
low sixteen data lines lets it hold the counter (16 registers), form the compare against
`NEXT` (a foldback tree) and latch the read-back byte — because **all three want the same
bus**, and U1 was the part with 51 spare cells and 18 spare pins while U2 had neither.
U1 hands the count back on the same sixteen pins for W6's "`NEXT` is one period from now",
which is what an I/O macrocell is for.

⚠ **Two of §9.3's sixteen bytes are no longer readable**: `VOL` (offset 7) and
`PTR[18:16]` (offset 11) live in lane 2, which U1 does not see. A replayer never reads
`VOL` back, and `PTR` is the advisory debugging window §9.4.5 already says is not atomic
across bytes.

### §10 / §0 — 45 ICs on a 240 mm card

**Why it moved:** **35, and back on 180 mm.** The card grew to 45 and 24 cm when the
sequencer was built; giving up panning and absorbing the counter, comparator and
read-back took it back under the 18 cm courtyard. `npm run check:place` is the authority
for both numbers.

### §10.2.5 — the margin, and which floor it is quoted against

**Not superseded — corrected in kind.** Every margin figure before this pass was quoted
at §4.3's `PER ≥ 16`, which is a *hardware* floor: a rate no note uses and the converters
could not reproduce. ProTracker's range is **113 to 856**. Measured at `PER` = 113, four
channels: **37 of 600 work slots**. That is the number a datapath change has to spend,
and it is why §16 item 34 records the 8-bit datapath as affordable-but-not-taken rather
than as impossible.

### §4.2's comparator — the shape that fits, and two that do not

**Not superseded — recorded, because the two failures are the useful part.** Sixteen
bits of equality went through three shapes in one afternoon:

1. **Four nibble-equalities ANDed together.** Looks like 64 product terms. A
   combinational intermediate in CUPL is *substituted* rather than given a macrocell, so
   `EQ0 & EQ1 & EQ2 & EQ3` multiplies four 16-term sums into **65,536**. The fitter ran
   seven minutes before it was killed.
2. **One `NEQ` macrocell, inequality as a sum** — two terms per bit, 32 in all. The term
   count is right and it still does not place: 32 terms reading sixteen `SD` pins *and*
   sixteen counter registers is **32 signals into one logic block**, against the 40 an
   `ATF1508AS` LAB takes from the switch matrix. ⛔ **Cells and pins were never the
   constraint** — U1's `.pld` is shorter than U2's, which fits in two minutes.
3. ⭐ **`NEQL` and `NEQH`, one per byte, each a pin.** Sixteen signals and sixteen terms
   apiece; U2 forms the hit as `!NEQL & !NEQH`. It places in two minutes **and the part
   gets smaller** — 88 of 128 cells, where the single-macrocell version had been forcing
   foldback across the whole design.

**The lesson for this repository is the third limit.** After macrocells and pins, an
`ATF1508AS` runs out of **LAB fan-in**, and its symptom is not a diagnostic — it is a
`Grouping fail`, or a killed process, on a design that is comfortably inside both of the
numbers anyone quotes.

## §6.2 — "one `'574` per side", corrected 2026-09-09

The section costed the converter feed at **two** packages:

> **One 8-bit `'574` per side**, driving both of that side's packages …
> **Two packages of latch, not eight**, because the bus is 8 bits wide rather than 12

`place/parts.ts` has carried **four** since the datapath was built, and the parts list
was right. ⚠ **One register per side cannot both hold and capture**: the walk puts
channel *N*'s byte on the bus in slot *N*, so all four arrive in slots 0–3 while the
write windows are 0–3 and 4–7 — the left side must hold `ch0` through slot 3 for its
own write in the very slot `ch3`'s byte arrives for the next window.

⭐ **Found by the user asking whether dropping panning freed them.** It does not: panning
changed which converter halves exist, not the walk order or the window structure. The
question surfaced the stale prose rather than a saving.

⛔ **And it is the class `lib/docs.check.ts` cannot catch.** That check holds utilisation
figures and IC totals against `gal/cpld/*.fit` and `place/parts.ts`; "two packages of
latch" is prose, tied to no part name and no total. Numbers are checkable; sentences are
not, and this is what that limitation looks like in practice.


---

## 2026-09-09 (fifth pass) — the 8-bit datapath, built and refused

**Nothing in the present design changed.** This entry exists because the attempt is
worth more than its absence, and because §16 item 34 now records a *measured* refusal
where it used to record an estimate.

**What was tried.** Narrowing the adder to a byte: `74HC283` 4 → 2, the sum's
three-state 2 → 1, the constant 2 → 1 — **−4 packages, 35 → 31**. The sequencing was
cheaper than the earlier estimate feared: a `BYTE` toggle holds the step counter while
the two halves of a 16-bit operation go through, so it needed **no fifth `T` bit**, only
two registers and two pins. `ALAT` and `BLAT` stayed two `'574`s each — they hold sixteen
bits and *present* eight, which is why they never halved.

**It worked.** `audio_tb` ran the whole card on it: **38 claims, 0 failed**, a channel
event at ten work slots instead of seven, the margin at ProTracker's top note 14.2× →
**7.7×**. Two real defects surfaced and were fixed on the way — the 17th and 19th bits
need to know an increment from a decrement, because `ACOUT` means "carry" on one and
"no borrow" on the other, and reading it one way for both made a 16-byte buffer 65,551
bytes long.

⛔ **The fitter refused it: `Grouping fail`, all eight LABs at `FanIn assignment [40]`.**
Not macrocells, not pins — fan-in, and the whole device rather than one block. A narrower
datapath needs *more control signals* and every one fans into the same decodes.

⚠ **And the rebalance had nowhere to go**, which is the part worth keeping. U1 is at
**62 of 64 pins**: it is pin-bound, not cell-bound, so its 40 spare cells are
unreachable — anything moved there needs signals crossing and there are two pins to
cross on. Three partitions were costed and all three are pin-fatal in one direction or
the other; §16 item 34 has the table.

**Reverted whole.** The card is 35 ICs on 18 cm, both CPLDs fitted, 483 checks and 38
simulation claims green — the state committed as `31665a4`.


---

## 2026-09-09 (sixth pass) — the microcode pipeline, attempted twice and reverted

**Nothing in the present design changed.** The card is 35 ICs on 18 cm, both CPLDs
fitted, `check` 483 and `audio_tb` 38 — the state committed as `32878bd`.

⭐ **What this pass produced is a measurement, and it is the useful part.** LAB fan-in,
which had never been read off a `.fit` before:

| | fan-in per logic block, of 40 |
|---|---|
| **U2 `aseq`** | A–D, F, G at **36**; E 28; H 11 |
| **U1 `audio`** | 25–28 across all eight |

Six of U2's eight blocks stand four signals from the wall. That is the whole explanation
for the 8-bit datapath's `Grouping fail`, and it is why the answer is not "shave a cell".

**The pipeline, and why both shapes failed.** The idea: ask a host access's meaning once
and register the answer, so a consumer reads one signal where it reads six. Two shapes
were built and simulated:

1. **Decisions clocked continuously, derived from `HRW`.** `HRW` is itself latched at
   `HSTB`, so the decisions are **two registers deep** where everything around them is
   one. The sequence can start in the very next work slot; the decision arrives stale.
   Simulation showed the card running one event ahead of itself.
2. **Decisions latched at `HSTB` from the raw signals**, one deep like `HA` and `HRW`.
   That fixes the depth and breaks something else: the existing decodes (`HW`, `HL`,
   `HRO`, `HSTAGE`) are *continuously* clocked, so they track `AIDX` as it
   auto-increments — a decision frozen at `HSTB` does not. The host's next access can
   arrive while the previous `W3` is still running, because `ASTAT` b6 clears when the
   sequence **starts**, not when it ends. Channel state landed in the wrong lanes.

⇒ **The third shape is the one to build**: decisions clocked continuously from `AIDX`
*and* `HRW`, with the work item gated so it cannot start until they have settled. That
is a change to §9.4.4's host handshake rather than to the decode, and it should be made
on its own rather than underneath a datapath change.

⚠ **And a correction that cost a pass**: U1's `88 of 128` cells reads like headroom and
is not — U1 is **pin-bound at 62 of 64**, so those 40 cells are unreachable. Anything
moved there needs signals crossing on two pins. It is `vctrl`'s lesson on a second card.


---

## 2026-09-09 (seventh pass) — `PWBUSY`, the second defect in the same flag

### §9.2 / §9.4.4 — `HACK` fired at `START`

**Was:** `HACK = START & !RSTANY & !TDUE & !DUEANY & HDUE`, so the work request *and*
`PWBUSY` cleared when the sequence **began**.

**Why it moved:** `BUSY` covers `START`→`LAST`, so the sequencer could never restart —
but `PWBUSY` is what the **host** reads, and `ASTAT` b6 said "free" while `W3` was still
running. A host polling b6 exactly as §9.2 asks could write into that window; `HSTB` set
`HDUE` again and loaded a new `AIDX`, and §9.3's continuously-clocked decodes (`HW`,
`HL`, `HRO`, `HSTAGE`) followed it **underneath the running sequence**. The observed
symptom was a channel holding `PER` = 113 after the host had written 30 — silent, and
dependent on how fast the host was.

⚠ **It survived the earlier repair to the same flag, on the same day.** That one fixed
how `PWBUSY` **sets** — adding `!AIDXLD`, so an index load could not wedge it — and did
not touch how it **clears**. Two defects in one four-term equation, and the first fix
read as complete. The lesson is narrow and worth keeping: *a flag has two edges, and
fixing one of them is not evidence about the other.*

**Now:** `HACK = RUN & WT2 & !WT1 & !WT0 & LAST` — the last step of the host's own
sequence. `HDUE` staying asserted throughout cannot restart anything because `START`
requires `!BUSY`. And `!AIDXLD` leaves `PWBUSY`: it existed because an index load queued
no work and could never be acknowledged, but every access queues a work item since §9.3's
prefetch was wired, so covering the index write closes the same hole for it.

**Measured, not asserted.** `audio_tb` gained three claims it did not have: that b6 is
still high **at** the sequence's last step and low after it; that four channels rewritten
back to back with no pause each keep the value the host wrote; and the worst-case wait.

| | before | after |
|---|---|---|
| host's worst wait for b6 | 43 slots, 1.5 µs | **63 slots, 2.2 µs** |
| work-slot mix, 4 channels at `PER` = 30 | — | **195 W1, 0 W3** — channel work unaffected |
| `aseq` LAB fan-in | 36,36,36,36,28,36,36,11 | **35,35,35,35,35,35,34,17** |
| `aseq` cells / I/O / Pts | 128/128, 60/64, 449 | 128/128, **61/64**, **441** |

⚠ **The fan-in relief is one signal on the hot blocks and is not a result to build on** —
it is reported because it was asked for, not because it changes what §16 item 34 says.


---

## 2026-09-09 (eighth pass) — the pipeline, now sound and still not worth having

**Nothing in the present design changed.** The card is 35 ICs on 18 cm; `aseq` is the
handshake fit committed as `8b764c1`.

⭐ **The precondition it needed is now true, and is asserted rather than assumed.**
Shape 2 of the pipeline — a host access's meaning decided once at the strobe and held in
registers — was reverted on 2026-09-09 because `AIDX` could move under a running `W3`.
§9.4.4's `HACK`-at-`LAST` repair closed exactly that, and `audio_tb` now carries the
claim: **`AIDX` never moves under a running host sequence, across 137 of them.**

⚠ **The first version of that claim was wrong and reported a defect the card does not
have.** It snapshotted at `START` — but a `W1` chaining into `W2` enters through
`ENDNOW` and never asserts `START`, so it compared a *channel* sequence against a stale
index. The trace said it plainly: `WT=1`, `HSTB=0`, `AIDXLD=0`, `AINC=0` — nothing had
moved. Scoped to `W3`, it passes. *A monitor is a claim and needs the same scepticism as
the design.*

⛔ **Built on that footing, the pipeline simulates clean and fits worse.**

| | before | with the pipeline |
|---|---|---|
| `aseq` LAB fan-in | 35,35,35,35,35,35,34,17 | **38,38,38,31,32,32,38,31** |
| foldback nodes | 61 | **94** |
| product terms | 441 | **495** |
| `audio_tb` | 43 claims, 0 failed | 43 claims, 0 failed |

⭐ **Why it fails is the useful part.** Registering a decision trades a few *substituted
literals* for a new *distinct signal* — and a switch matrix counts signals, not literals.
Nine decisions went in and perhaps two qualifiers actually left, because `HRW`, `HL0` and
`HL1` are read elsewhere too. ⛔ **It also shows the decode was never the problem**: the
36-of-40 baseline is dominated by `RUN`, `WT0`–`WT2`, `T0`–`T3` and the working state,
which every control output reads and which no host-qualifier concentration touches.

**So the 8-bit datapath was not attempted, and §16 item 35's latent `ACOUT` hole is left
recorded rather than half-fixed.** The reverted branch keeps both, and §16 item 34 now
carries the measurement instead of the estimate.


---

## 2026-09-10 — the Paula overview arrived, and the sequencer got a third arrangement

**Nothing in the present design changed.** The card is 35 ICs on 18 cm, two `ATF1508AS`,
U2 at 128 of 128. What changed is that §10.3 now exists beside §10.2, and §0 says so.

### §18 — Paula was a bibliography entry and is now a file

[`paula.md`](paula.md) is a functional overview of the MOS 8364, added verbatim with a
provenance header. ⚠ **It is a secondary source and is labelled one**: the *Hardware
Reference Manual* outranks it, and §16 item 36's differential oracle outranks them both.
That precedence is not decoration — the oracle has already overturned one thing this
document said about Paula (§4.2's *"`PER` = 0 or 1: clamp in the sequencer, as Paula
effectively does"*; Paula does not clamp anywhere, its floor comes from Agnus's DMA
rate). ⚠ **And the one thing deliberately not taken from it is the DMA architecture**:
Paula does not arbitrate the bus, this card has no Agnus and no bus mastering, and its
sample RAM is card-local (§2, §5), so "samples must live in chip RAM" has no analogue
here.

### §10.2.6 — "there is nothing left on U2", and what that was blocking

The fitted sequencer is a microcoded engine whose control store is built out of
**macrocells**: 36 control outputs, each a sum-of-products decode of
(`RUN`, `WT[2:0]`, `T[3:0]`) qualified by the host state. It stands at 128 of 128 cells,
61 foldback nodes and six of eight blocks at 35 of 40 LAB fan-in, and five open items
were stuck behind that one fact — §16 items 7, 32, 34, 35 and 36, **two of which are
live audible defects**.

§10.3 moves the decode into four `27C512` and every qualifier into an address line.
⭐ **The reason it works is §16 item 34's own measurement, read the other way round**:
if a switch matrix counts *signals* rather than *literals*, the cure for fan-in is not to
register a qualifier — that adds a signal, which is why item 34's pipeline made it worse,
35 → 38 — but to make the qualifier **stop being a signal**, which is what addressing a
memory with it does.

| | present | §10.3 |
|---|---|---|
| ICs | 35 | **36** (+4 `27C512`, +1 `74HC163`, −4 datapath) |
| U2's 149 term-list cells | all on the part | 44 absorbed, 18 rewritten, 87 unchanged |
| step rate | 10.64 M/s | 7.09 M/s |
| margin at `PER` = 113 | 12.1× | **5.7×** |
| throughput floor | `PER` ≥ 10 | **`PER` ≥ 20** |

⚠ **It is measured and not fitted**, and §16 item 38 is the gate. `npm run check:arom`
computes the microword, the address map, the image and the budget from the same
`PROGRAM` table the fitted design's term lists come from — 59 claims — and prints the
macrocell and pin figures as **estimates**, with the word on them, because only
`fit1508.exe` settles those.

### §0 / §10.2.3 — two claims that did not survive designing it

⛔ **"No tight path at all."** §0's sentence is *"the fastest thing on the card is a
state-file read at 30 ns inside a 35.24 ns slot"*, and **the `'283` chain is not in it
and never was in any other sentence either.** §10.2.3's read-modify-write is two
consecutive slots, so a 16-bit ripple carry through four `74HC283` has roughly 50 ns —
against a single `74HC244` buffer at 23 ns max at 4.5 V, the only 74HC propagation figure
in the repository. ⚠ **Nothing on the card can see it**: the Verilog models logic and not
timing, and the `'283`s are inside neither CPLD, so `cpld/*.fit` does not see them
either. §16 item 37 is now that finding, and it belongs to the **present** design.

⛔ **"Even `T` is a state-file read, odd `T` is a write."** `aseq.micro.ts`'s header
states it as *the one invariant that makes it cheap*, and `PROGRAM` does not obey it:
W1 steps 2 and 3 are both reads, W3 step 0 is an even write and step 5 an odd read, and
every step of W5 alternates the wrong way. It was found by trying to *use* it — the
16-bit two-package microword §10.3.4 prices and rejects depends on it being true — and
the lesson is narrow: **an invariant a document states and a table does not hold is not
an invariant, and the way to find out is to build something that needs it.**


---

## 2026-09-10 (second pass) — the `'283` datasheet, and what it decided and did not

**Same day, and it revised the section written that morning.** §10.3's first version
argued from the `74HC244`'s 23 ns that four cascaded 4-bit adders would be "several of
those". [`cd74hc283.pdf`](../../reference/datasheets/cd74hc283.pdf) is now in the
repository and says a single package's carry is **39 ns**, not ~15.

⛔ **The estimate was wrong by 3× and it was wrong in the optimistic direction**, which
is the direction that matters: it made a hole look smaller than it is. §16 item 37 now
carries the datasheet's own figures.

| | first version, 2026-09-10 morning | the datasheet |
|---|---|---|
| a 16-bit ripple | "roughly 50 ns available, several `'244`s needed" | **163 ns of carry, 192 ns to the state file** |
| an 8-bit ripple | ~108 ns, "and two cascaded make 61 ns" | **114 ns — it does not** |
| what closes it | the 8-bit datapath and a 2-slot micro-step | ⭐ **a re-timing that costs neither** |

### What it decided

⛔ **§16 item 34, the 8-bit datapath, is withdrawn.** It was priced on package count with
the ALU assumed free. It is not free: an 8-bit sum still needs the across-the-walk window,
so it buys no time and costs **two** colour clocks per 16-bit update where a 16-bit adder
costs one — four packages for 1.6× the time, and a throughput floor at `PER` ≥ 32 against
§4.3's 30. ⚠ **The consequence lands on §10.3: it costs five packages now, not one**,
because item 34 was paying for four of them. **40 ICs, not 36.**

### What it did NOT decide, which was the surprise

⭐ **It does not choose between §10.2's arrangement and §10.3's.** Once a 16-bit sum is
192 ns, both have exactly one window long enough and it is the *same* window — the walk,
which never adds and whose four slots are therefore free settling time. One
read-modify-write per colour clock in both; W1 = 4 colour clocks in §10.2 and 5 in
§10.3, a **25 %** difference rather than the 2× the first version's slot arithmetic
implied. **The case for the control store is now entirely that U2 is at 128 of 128 cells,
which is where it started.**

### And one claim became true

⭐ **§10.3.4 rejected the 16-bit two-package microword because "even `T` reads, odd `T`
writes" is asserted by `aseq.micro.ts` and not obeyed by `PROGRAM`.** The across-the-walk
rule *forces* that parity — a read must land on the last engine step of a colour clock
and its write on the first of the next — so the invariant becomes true by construction.
The narrow microword is not taken, but it is **no longer refused for the reason it was**,
and §16 item 38's gate says to re-price it while the microprogram is open.

### "The shipped card"

⚠ §16 item 36 said *"two live defects on the shipped card"*. **Nothing has been built**;
the machine is in design. Corrected — they are defects in a fitted, simulated design in
its first week, which is where they are cheapest, and the reason to record them at this
volume is that neither the fitter nor `audio_tb` found them.


---

## 2026-09-10 (third pass) — items 35 and 36 closed in the fitted part, for nothing

**The card is still 35 ICs and two `ATF1508AS`.** What changed is that the two audible
defects §16 item 36 recorded that morning are repaired, measured, and fitted — and that
the repair cost **no package, no pin and no macrocell**.

### §10.2.4 / §16 item 35 — "the 17-bit `CNT` does not exist"

**Was:** `SD[18:16]` driven by `SDQ` XOR (`ACIN` & `ACOUT`), so four behaviours were
told apart by one bit that is zero in three of them.

⭐ **Now: `ACIN`, `ONESOE` and `BLATOE`** — three control outputs the design has always
produced, mutually exclusive on every driving step, read directly by the three lane
equations. **Two extra literals on three equations.** The information was never missing;
the equation was only reading a third of it.

⛔ **The first repair was two registered mode bits and it did not fit**, and both of its
failures are worth keeping:

- a registered decode of (`WT`, `T`) must be decoded from the **preceding** step, because
  a register's terms are evaluated on the edge that *ends* a step;
- and it must **hold across the five walk slots** between one work slot and the next.
  Without the hold it survived where two steps fell in the same colour clock and vanished
  where they did not — `carry` landed, `dec` did not, `CNT[16]` took a silent zero — which
  is a defect that *looks intermittent and is not*.
- With the hold it was correct and `fit1508.exe` answered **`INTERNAL ERROR`**. ⚠ CLAUDE.md's
  first trap fired verbatim: the previous `.fit` stayed in place and read like a passing
  one. The hash is what caught it.

⭐ **`CW0`–`CW2` and `CL2` paid for it, and they were free to delete.** For every offset
that commits, §9.4.3's commit word is the same word §9.3's byte map already puts that
offset on, so `CW` was a second decode of `AIDX` computing what `HW` had computed. `CL2`
is `HCOMMIT & HW1`. Four registered macrocells, gone.

| `aseq` | before | after |
|---|---|---|
| logic cells | 128/128 | 128/128 |
| I/O | 61/64 | 61/64 |
| flip-flops | 60 | **56** |
| foldback | 61 | **71** |
| product terms | 441 | **487** |
| cascades | 21 | **1** |
| LAB fan-in | 35,35,35,35,35,35,34,17 | ⚠ **39,39,39,33,39,34,39,27** |

⚠ **It fitted and it spent everything it freed.** §16 item 32 is tighter, not looser.

### §10.2.3 / §16 item 36 — D-1 and D-2

`CNT` is loaded as **2 × `LEN` − 1**, so the borrow out of `CNT − 1` lands where the
buffer ends rather than one iteration later, and `LEN` = 0 becomes `$1FFFF` = 131,072
bytes = Paula's 65,536 words. **Two microcode steps**: W2 four → six, W6 nine → eleven,
in sequences that run once per buffer end and once per note.

### The claim that was missing, and why writing it was the hard part

Item 36 ended *"nothing anywhere counts how many samples a buffer yields"*. `audio_tb`
counts them now — `4 4 4 4 4` for a two-word loop — and getting there needed **isolation
in both directions**, neither of which the earlier attempt had:

- the channel under test set up from scratch, with the write **verified to have landed**
  before anything is measured;
- and **every other channel excluded from the count**. Without that, an unfiltered count
  of W1 starts counted channels 1–3's events too and reported *"4, 7, 5, 6, 5 samples"*
  for the same four-byte buffer — a number that looks like a defect and is an instrument
  fault.

⛔ And the earlier `LEN` = 0 attempt had gone **vacuously green**: the write never landed
and the claim measured a channel that was not running. *A passing claim that tests
nothing is worse than a failing one, because it reports green.*

### ⛔ What this says about `modcompare`, which is green and always was

`audio/tools/modcompare/` A/Bs `audio/refplayer/` — **a C model of this card** — against
libopenmpt's Paula emulation, and has reported near-perfect agreement since 2026-09-04.
**It could not have caught either defect.** `card.c` ends a buffer with
`if (--ch->cnt == 0u)`, which is right; the hardware ended it on a borrow, which was not.
Two independent implementations of the same prose, and the A/B only ever tested one of
them. The card was not in the loop, and on 2026-09-04 it could not have been — there was
no Verilator model and the logic was five GALs.

**What modcompare validates is the replayer and the register-level model**: the effect
engine, the period table, the tempo mapping, the `LC`/`LEN` shadow idiom. That is real
and it is build step 0's exit criterion. **What it says about the hardware is nothing**,
and the only thing that does is a testbench that runs the design — which is why item 36's
oracle found in one afternoon what six days of green A/B did not.


---

## 2026-09-10 (fourth pass) — the oracle rebuilt, run, and it found a third defect

**Nothing in the present design changed except one open item's status.** The card is
35 ICs, `aseq` fits, and §16 items 35 and 36 stay closed.

### §16 item 36 — "the card half of the harness is entirely ours"

⛔ **It did not exist.** Only `fetch-paula.sh` had been committed; `run-oracle.sh` and
both testbenches were named in a comment and produced by nothing. Same defect class as
item 0b, in the tooling this time. [`gal/verilog/oracle/`](../../hardware/gal/verilog/oracle/)
is the rebuilt harness — two testbenches and a runner that builds them as **separate
binaries** so nothing links against `Paula.v`, whose licence is still unsettled.

⭐ **Re-run against the repaired design, it agrees.** Card and Paula play the same bytes
in the same cyclic order — `02 03 04 05` repeating for a two-word loop. D-1 and D-2 are
confirmed fixed by an implementation that shares nothing with ours but the hardware
reference manual.

### ⚠ Four harness bugs, every one of which looked like a finding first

An oracle is a claim and needs the same scepticism as the design. Paula does not fetch
its own samples — it raises a request and *Agnus* owns the pointer — so an Agnus is part
of the oracle, and getting it wrong produces confident nonsense:

| Symptom | Cause |
|---|---|
| `AUDxLEN`/`AUDxPER` read back 0, `DMACON` fine | RGA left asserted for the data colour clock wrote every register twice, the second time with zero. ⚠ **DMACON survived because "clear no bits" is a no-op** — the bug hid itself in three registers out of four |
| `fetches=0` — looks like a chip that never asks | Paula's control outputs are four-bit **rotating** shift registers; they only read as "bit *i* is channel *i*" while `cck` is high |
| `fetches=1`, then silence | Paula **holds** the request until answered; an Agnus that waits for a rising edge answers once |
| the sample walking off the end of the buffer | the restart flag is `dmasen \| lenfin`, not `dmasen` — and `lenfin` is `lenctr == 1`, which is the same "one less" convention item 36's repair arrived at independently |

### §16 item 39 — the third defect, and the first repair that would not fit

The steady state is exact and the **first pass is not**: `03 04 05 06` out of a four-byte
sample, because W6 primes and W2 does not, so both loading `CNT` = 2 × `LEN` − 1 leaves
the enable path one short. And the primed byte is never strobed into the converter, so
the first sample of every note is skipped.

⛔ **The repair was written, measured correct, and refused.** Two more microcode steps in
W6; `fit1508.exe` answered `INTERNAL ERROR`. **§16 item 32 stopped being a forecast**:
the card carries a known first-pass defect because the part has no room for the fix, and
that is the strongest evidence §10.3 has.

### ⛔ And a new fitter trap, which is why the refusal was nearly missed

`fit1508.exe` answered `INTERNAL ERROR` **and wrote a `.jed` and a `.fit` anyway.**
`fit1508.sh`'s only test was "does a JEDEC exist", so it printed `wrote …`, exited 0, and
copied out a report claiming a plausible 128/128 cells and a *better* LAB fan-in than the
design that really did fit. ⚠ **"Design fits successfully" is in the fitter's stdout and
not in the `.fit`**, so nothing downstream can recover it. The script now requires that
sentence and refuses `INTERNAL ERROR`; CLAUDE.md's first trap has the sibling recorded
beside it.

### And one hand-maintained table that disagreed with the table beside it

`aseq.jedec.ts` carried a `LEN` map of sequence lengths next to `PROGRAM`, and adding
steps to W2 and W6 left `LAST` firing mid-sequence — a channel that fell silent with **no
failing claim anywhere**, because the microprogram simply stopped part-way. It is derived
from `PROGRAM` now.


---

## 2026-09-10 (fifth pass) — W6 chains into W1, and the part gets smaller

**The card is still 35 ICs.** What changed is that §16 item 39(a) is closed and `aseq`
came **down** — the only change all day that did.

### §10.2.3 W6 — eleven steps of priming became eight steps of handover

**Was:** W6 reloaded `PTR`/`CNT`, then did its own sample fetch, its own pointer
increment and its own `PEND` write, and set `NEXT` = count + `PER`.

⛔ **Two defects lived in that duplication.** W6's fetch consumed a byte no W1 would ever
count, so the first pass of every note ran one byte past the buffer; and its `PEND` write
raised none of §6.2's `WROTE` flags, so the first sample was never strobed.

**The obvious repair — a second `CNT − 1` pair in W6 — was written, measured correct, and
refused by `fit1508.exe`.**

⭐ **Now:** W6 sets `PTR`, `CNT` and `NEXT` = the bare count and **chains into W1**, the
way W1 already chains into W2. W1 does the first fetch, counts it like any other, adds
`PER` itself, and its `PEND` write is the one §6.2 already watches.

| `aseq` | priming W6 | chained W6 |
|---|---|---|
| steps in W6 | 11 | **8** |
| logic cells | 128 / 128 | **127 / 128** |
| product terms | 487 | **461** |
| foldback | 71 | **69** |
| cascades | 1 | **0** |
| peak LAB fan-in | 39 of 40 | **37 of 40** |

⭐ **Deleting the duplicate was cheaper than correcting it, and that is the transferable
part.** Every other repair this day *added* — a mode, a step, a term — and each cost the
part more than the last. This one removed work that was already being done elsewhere and
paid for itself twice over. ⚠ **One spare cell is not headroom**: what it shows is that
the cheap moves left on this part are deletions, and §16 item 7 and §11.3 are additions.

The chain is one combinational cell (`CHAIN1`, derived from W6's own length), one literal
on `WT1`'s hold term and one term on `BUSY`.

### ⚠ What is NOT closed

The first `PEND` write of a note still is not strobed into the converter — §6.2's `WROTE`
flag is held only until the next slot 7, so it reaches the `AD7528` when the writing step
lands in a slot from which it survives to the following walk, and not otherwise. In
steady state it always does. **The oracle measures the residue**: three samples on the
first pass, four on every one after, four fetched throughout.

### §9.2 — a testbench that did not obey the register map it was testing

§8.1 bit 5 is `HSTB & !RW & PWBUSY`: it fires on **any** host write arriving while the
previous has not retired, not only on `ADATA`. `audio_tb` honoured b6 in `adata`/`aidx`
and nowhere else, and got away with it because the engine was quick enough. A longer
enable sequence made the next write overrun, `AINTREQ` b5 latched, `/FIRQ` would not
release — **and it presented as an interrupt defect.** Every write waits on b6 now.
