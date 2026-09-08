# Net — archived history

Superseded passages from [`net.md`](net.md), archived when the spec was split into
present design and history. The repo convention used to be "superseded text is marked,
not deleted"; the marks now live here, organized by the spec section they came from.
Nothing in this file describes the current card — read `net.md` for that.

The one structural event in this card's history is the **2026-09-08 revision**: the card
was first specified with its buffers behind a prefetched, auto-incrementing `NDATA` port
in four bytes of `$FF` space, because that was the only address space the machine had —
and filling the `$FF` map is what forced `machine.md` §5 item 1. The machine's answer
(§5 item 1 option D and §5 item 7: a 128-byte window and a megabyte of physical space at
`A20 = 1`, for one backplane pin and no ICs) paid for a rebuild the same day. Most
entries below are pieces of that one change.

## §0 The 2026-09-08 revision — port buffers became memory-mapped buffers

The spec's summary carried this notice:

> **⚠ Revised 2026-09-08, and the revision is structural.** This document originally
> specified the buffers behind a prefetched, auto-incrementing `NDATA` port in the four
> bytes of `$FF` space, because that was the only address space the machine had.
> `machine.md` §5 item 1 option D and §5 item 7 gave the machine a megabyte for exactly
> this, and the card was re-specified against it: **four ICs and the `TFM` hazard came
> off, throughput rose 27 %, and the ring went from four frames to sixteen.**

The component `README.md` carried the before/after table:

| | port version | after 2026-09-08 |
|---|---|---|
| ICs | 16 | **12** |
| Sustained RX | 537 KiB/s (44 % of the wire) | **681 KiB/s (56 %)** |
| Sustained TX | 373 KiB/s | **681 KiB/s** — fill and transmit overlap |
| RX ring | 4 frames | **16** |
| `TFM` hazard | chunk and mask, −21 % | **retired** — the host reads RAM, not a port |
| Small frames @ 400-cycle dispatch | 6,107/s, 29 % of the CPU in dispatch | **9,639/s, 11.5 %** |
| U2 fit | 118/128 | 116/128 — unchanged, and that is the honest part |

Replaced by: the memory-mapped design `net.md` now describes throughout.

## §0 Summary — corrections applied when the doc was split (2026-09-08)

- **Power**: the summary quoted **~430–530 mA** while §10's own table totalled
  **~410–510 mA**; `machine.md` §8 carries 410–510, so the summary was corrected to it.
  (430–530 matches the 16-IC port version's part count.)
- **U1 fit**: the summary said **88 %**; §7.2's table sums to 114/128 = **89 %**.
- **IC count chain**: 16 → **12** (2026-09-08; see §9 below).

## §3.1 Sustained RX — 44 % of the wire became 56 % (2026-09-08)

> ⚠ **This read 44 % until 2026-09-08**, because the port version paid a further 21 % for
> the chunk-and-mask that §3.2 no longer needs. The wire got no slower; the tax came off.

Replaced by: the plain 681 KiB/s = 56 % figure — an unchunked `TFM` at 3.01 cycles/byte.

## §3.1 Sustained TX — 373 KiB/s became 681 KiB/s (2026-09-08)

> ⚠ **TX read 373 KiB/s until 2026-09-08.** The port version was single-buffered — the
> host filled through the same pointer the transmitter read with, so a maximum-size frame
> cost 2178 µs of fill *then* 1221 µs of transmit. With the buffer memory-mapped there is
> no shared pointer: the host writes bank B while bank A transmits, TX is four-deep for
> the price of the SRAM that was already there, and **the 31 % that overlap used to cost
> is simply gone.** This was §13.3's "best-value addition on the card" and it turned out
> to be free.

Replaced by: `net.md` §3.1's present statement that fill and transmit overlap.

## §3.2 The `TFM` hazard — inherited from the port design, then retired (2026-09-08)

The section was titled *"⚠ The `TFM` hazard, again"* and read:

> **This document originally inherited that exactly.** Its `NDATA` port returned a
> prefetched byte *and* advanced the pointer, so an interrupted drain shifted the frame
> by one byte from that point — past an FCS that hardware had already checked and
> passed. The specified fix was `sdcard.md` §4.4's chunk-and-mask: 32-byte chunks,
> 3.81 cycles/byte, **21 % of the card's throughput**, and 49 µs of added interrupt
> latency.
>
> **⚠ Retired 2026-09-08, and not by mitigating it.** [...] **The 21 % is what §3.1's
> 44 % → 56 % is made of.**

Replaced by: `net.md` §3.2 — the ring is memory, an interrupted `TFM X+,Y` against RAM
is idempotent (`sdcard.md` §4.2), and no bulk transfer runs over a side-effecting port.

## §3.3 Ring depth — 4 banks became 16 (2026-09-08)

Four banks was *"what the port version could afford"*:

> In the port version each bank cost macrocells — a wider write-bank counter, a wider
> compare, a deeper read-side mux — so four was a budget decision argued against
> `machine.md` §4's 0.8–1.3 ms PS/2 interrupt-mask window.

Replaced by: sixteen banks, because the depth became a choice of SRAM part (`62256` for
`6264`) plus four bits of write-bank counter.

## §3.4 Minimum-size frames — the port version's numbers (2026-09-08)

The port version reached **41 %** of the small-frame wire rate against the ring
version's 65 %: **6,107 frames/s** at a 400-cycle dispatch, with **29 % of the CPU**
spent in dispatch (against 9,639/s and 11.5 % with the sixteen-deep ring — the ring's
2.7× is per-dispatch draining, which four banks were usually too shallow to exploit).

## §4.1 Register decode — `A0`–`A5` became `A0`–`A6` (2026-09-08)

`A6` left the `/IOSEL` strobe when the window widened from `$FF00`–`$FF3F` (64 B) to
`$FF00`–`$FF7F` (128 B), so a card's own decode grew from six bits to seven. The card's
base did not move.

## §4.2 The card regions — halved to eight and restored the same day (2026-09-08)

> **The regions were halved to eight on 2026-09-08 and restored the same day.** The
> halving paid for a 512 KB system-RAM bank on the motherboard; `hardware/ram.md` §6
> then dropped the DIP SRAM for SIMM sockets, so there was nothing left to pay for.
> **Nothing on this card ever changed** — it is recorded because the jumper briefly
> said three positions.

Replaced by: sixteen regions of 64 KB, selected by `A19`–`A16` against a four-position
jumper (`machine.md` §5 item 7, `hardware/ram.md` §5.2).

## §4.3 The schedule — a `74HC574` prefetch register, and a schedule tied to `E` (2026-09-08)

Two things the present schedule shed:

- The host's 357 ns data-valid *"is the timing the port version needed a `74HC574` to
  make"* — a prefetch register that became unnecessary once the address arrived on the
  bus instead of out of a counter (80 ns of margin with no register in the path).
- The schedule's opening read *"⚠ A stretched cycle breaks a schedule tied to `E`, and
  `/WAIT` became real on 2026-09-08 — so this schedule is not tied to `E`."*
  `machine.md` §5 item 8 gave the divider a hold term the same day the card was rebuilt;
  §16 item 5 (closed 2026-09-08) recorded the fix: `graphics.md` §7.4 bounded `SPANBUSY`
  at **40.7 µs — 51 byte times**, which a framer counting bus cycles would not survive,
  so §4.3 free-runs the phase counter on `CLK25` and only resets it on E-fall. During a
  stall the CPU is on VRAM and this card's buffers are idle. `machine.md` §5 item 10
  states the general rule, because this card is the one that had the bug.

## §4.5 Phantom reads — from "checked, and clean" to "cannot matter" (2026-09-08)

The section was titled *"Phantom reads — checked, and clean"* when the card had a
read-triggered `NDATA` port and leaned on `sdcard.md` §3.4's guarantee that dead cycles
drive `$FFFF`. It closed with:

> That is worth stating because it *was* load-bearing one revision ago, and because it
> is the second thing (after §3.2) that a memory-mapped buffer retires rather than
> mitigates.

Replaced by: nothing on the card has a read side effect, so the guarantee is not needed.

## §5.1 Placement — the machine's last four bytes (2026-09-07 → 2026-09-08)

> ⚠ **This took the machine's last four bytes on 2026-09-07, and that is what closed
> `machine.md` §5 item 1 the next day.** For one day the geographic decode was 64 of 64
> with nothing free. The window is `$FF00`–`$FF7F` now — 128 bytes, 64 of them free —
> and `/IOSEL` got *cheaper* in the process. **The card's base does not move; its decode
> becomes `A0`–`A6`** (§4.1).

And four bytes used to be tight rather than comfortable:

> The port version needed a `DATA` port, a pointer low byte, a pointer high byte, a
> direction-select bit and a command register in the same four addresses, split by
> `R/W` to get eight registers out of four.

## §5.2 Four registers deleted (2026-09-08)

> ⚠ **Four registers were deleted in the 2026-09-08 revision and it is worth naming
> them, because each one was a workaround for the address space the card did not have.**
> `NDATA` (the prefetched, auto-incrementing data port — §3.2's hazard),
> `NPTRL`/`NPTRH` for the *RX* side, and the `SEL` bit that said which direction the
> data port and pointer referred to. The host now addresses the frame directly.
> `NTXPL`/`NTXPH` survive because the transmitter still needs to be told where to start.

## §5.5 The bank header — streamed, then addressed (2026-09-08)

In the port version the host had to *stream* the header out through `NDATA` before the
frame; with the ring memory-mapped it reads the two bytes wherever it likes.

## §6 Interrupt polling order — the observation that dated itself

The ⚠ note on the polling order ended *"But nobody had to choose between correctness
and frequency before"* — true when net became the fifth `/IRQ` source (2026-09-07) and
narrative since.

## §7.1 `SLOT` — new in the 2026-09-08 revision

The `SLOT` wire (and the shared-bus contention hazard it answers) did not exist in the
port version, where each CPLD had a private SRAM. The spec's ⚠ keeps the hazard; this
entry records when it appeared.

## §7.3 U2 fit — 118/128 became 116/128 (2026-09-08)

The port version's U2 was **118/128 (92 %)**. The rebuild shed the host-side pointer,
the prefetch control and the `SEL` bit (−13) and gained the sixteen-bank ring
bookkeeping and a wider framer address (+11) — net −2, and the fit risk unchanged in
kind. The spec's editorial on that:

> **A structural change that improves four things and leaves the fifth alone is the
> normal case, and a document that quietly re-scored the fifth would be the suspicious
> one.**

Stale echoes of the 92 % figure in §13.2 and §13.5 (and an 83 % for the cut order's
landing point, against §7.3's 81 %) were corrected when the doc was split.

## §7.4 Pin budgets — the shortage moved from U2 to U1 (2026-09-08)

> One revision ago U2 was at 56 of 60 and U1 at 37; moving the region decode, the SRAM
> control and the schedule onto U1 moved the shortage with them.

Replaced by: U1 at 60 of 60 (pin-limited), U2 at 49 of 60.

## §7.6 Arbitration — "one counter, two contexts", and the three priced mechanisms (2026-09-08)

The section was titled *"Arbitration — one counter, two contexts"* and *"used to be the
hardest part of the card"*: the host and the framer both needed the RX SRAM at
different offsets at the same time, and the host's offset lived in a counter on the
card. Three mechanisms were priced:

| | how | cost |
|---|---|---|
| Two counters and a mux | both offsets in macrocells; a 2:1 mux drives the address pins | 11 + 11 + 11 = **33 MC** |
| One counter and a shadow | the counter drives the pins; the shadow holds the inactive context; a swap is a simultaneous parallel load | 11 + 11 + 5 = **27 MC** |
| **One counter, host side external** *(specified until 2026-09-08)* | U2's counter drives the pins and three-states; a `'161` cascade drives them through `'244`s the rest of the time | **4 MC, +5 ICs** |

All three went when the host's offset started arriving off the backplane: **five ICs
and 4 macrocells out; three ICs and 9 macrocells in** (§4.3's phase counter and the
`SLOT` wire, plus the two `'244`s and the `'245` that were needed anyway). The
`74HC574` prefetch register went with them.

## §9 Chip budget — 16 ICs became 12 (2026-09-08)

> ⚠ **This was 16 until 2026-09-08, and the four that left are worth naming**: three
> `74HC161` and a `74HC244`/`74HC125` pair carrying the host-side RX pointer, and the
> `74HC574` that prefetched a byte for it. **All five existed to get an address to the
> SRAM that the backplane now delivers**, and the two `'244`s and the `'245` that
> replaced them are doing a simpler job. §7.6.
>
> The `6264` on the RX side became a `62256` in the same revision — same package, same
> pin count, same price, four times the ring (§3.3).

(Five out, one `'244` in: 16 → 12.) The "for scale" line also aged: it read *"video 41,
audio 29, PS/2 11, storage 13, serial 3"*; corrected against
`hardware/place/parts.ts` to video 27 (its seven SRAMs became four, `graphics.md`
§14.2), audio 29, storage 14, and I/O 14 (PS/2 and serial merged onto one board).

## §10 Power — the comparison card got lighter (2026-09-08)

The "second largest single-card draw" comparison read *"after video's 1.1–1.7 A"*;
video's consolidation (`graphics.md` §14.2, `machine.md` §8) brought that card to
~0.5–0.85 A. Net stays second. The summary's ~430–530 mA total was corrected to §10's
~410–510 mA (see §0 above).

## §12 The house rule — as it read before it was retired (2026-09-08)

> When this card was specified the rule read *"no CPLDs or FPGAs — spent, deliberately,
> on two cards"* — video, to compete with a GIME on even terms, and audio, because its
> interrupt block does not fit a `GAL22V10` either way. **This card was the third**, and
> this section said the sentence in the root README would have to change. It did.

And the slot-count premise of argument 1 moved under it:

> ⚠ **The premise moved on 2026-09-08 and the conclusion did not.** [`hardware/README.md`
> had given the machine six slots, five already claimed, when PS/2 and serial were
> separate cards.] PS/2 and serial merged onto one board, so there are **five cards and
> a spare slot** — a two-card MAC would now fit. What kills it is point 2 rather than
> the slot count [...]. **The argument is weaker than it was and still holds**, which is
> worth more than pretending it is untouched.

Replaced by: the rule as retired at the root `README.md` (period-appropriate silicon,
programmable logic in), with §12's three arguments kept as its rationale.

## §13.1 DMA — the spare pin's competition (2026-09-08)

The pin ledger was dated: *"⚠ And on 2026-09-08 the one spare pin went to something
else"* — slot position A34 became physical `A20` (`machine.md` §5 item 1 option D),
beating both the earmarked future rail and this card's wished-for bus-request/grant
pair. The spec keeps the decided competition; this entry records the date.

## §13.3 A deeper ring, a second TX buffer, a 62256 — deferred, then taken (2026-09-08)

The section priced three additions and deferred all of them, *"cheap in parts and
expensive in the one currency that is short"*. The currency stopped being short:

| | then | now |
|---|---|---|
| eight RX banks instead of four | ~5 macrocells at 92 % — "revisit after the first fit" | **sixteen**, for a `62256` in the same package. §3.3 |
| TX ping-pong | 12 macrocells on U1 plus a shadow-exchange arbiter — "the best-value addition on the card" | **four TX banks, for nothing.** The host addresses the buffer, so there is no shared pointer to ping-pong around. §3.1 |
| a `62256` | the cheap half of a change whose expensive half was macrocells | fitted |

## §13.6 The `DP8390` — round one, and the day it expired (2026-09-08)

Round one as originally written, when the machine's map had four bytes for this card:

> **It failed the second half of the test when this document was written.** The
> `DP8390`'s register file is 16 registers across four pages plus a remote-DMA data
> port and a reset port — **16 bytes at an absolute minimum and 32 as everyone actually
> decoded it.** `machine.md` §3 had **four**, and §5.1 above is what happened to those
> four.

That argument is what `machine.md` §5 item 1 cites as the strongest evidence the old
map had produced against itself — and it expired the day item 1 closed:

> ⚠ **`machine.md` §5 item 1 was closed on 2026-09-08 and the window is 128 bytes, so
> that argument no longer holds — and the decision does not change.** The reason is one
> this document did not check and should have, because it is the first question to ask
> of any part: **the `DP8390` is long obsolete.** [...] **Availability, not address
> space, is what decides this.**

The section then noted the superseded argument was *"kept rather than deleted, per the
convention at the bottom of the root `README.md`"* — the convention this history file
replaces. `net.md` §13.6 keeps both rounds in condensed present-tense form, because the
ordering they teach (availability first, I/O budget second) is what the root README and
`hardware/ram.md` cite it for.

## §14.1 The driver — what the 2026-09-08 revision deleted

> ⚠ **Three things the 2026-09-08 revision deleted from this driver**: the
> chunk-and-mask loop (§3.2), the `SEL` bit before every pointer write, and the two
> `NDATA` reads that used to fetch the header. **Building the TX frame in place is new**
> and it is worth noticing — the port version could not, because the only way into the
> buffer was a byte at a time through a register.

## §15 Build order — step 0, and step 5's origin (2026-09-08)

Step 0 was *"freeze `machine.md` §5 item 1"* — a machine-level decision the card was
blocked on; the machine settled its address spaces on 2026-09-08 and the card was
re-specified against them. Step 5 (scope the shared buses) did not exist before that
revision; it is the price of the four ICs that came off.

## §16 Open items — closed 2026-09-08

- **Item 4, the house rule** — retired at the root `README.md`, with this card's §12 as
  one of the three arguments.
- **Item 5, "§4.3's schedule assumes a bus cycle of fixed length"** — `graphics.md`
  §7.4 bounded `SPANBUSY` at 40.7 µs (51 byte times), which a framer counting bus
  cycles would not survive; §4.3 free-runs the phase counter on `CLK25` and resets it
  on E-fall, so a stretch costs the card nothing. `machine.md` §5 item 10 carries the
  general rule.
- *The `$FF` map has no room for this card* — `machine.md` §5 item 1 A; the window is
  128 bytes and the card's decode became `A0`–`A6` (§4.1).
- *Re-price the RX buffer against `A20`* — done; it is the 2026-09-08 revision. §7.6,
  §13.3.
- *The `TFM` hazard* — retired rather than mitigated (§3.2). `sdcard.md` §13 item 1
  still needs its silicon capture, but no bulk transfer on this card runs over a port
  any more.

## §17 Cross-references — a stale item range

The `review.md` row read *"the four still open are items 4–7 above"* — the numbering
from before items 4 and 5 closed; the carried-from-`applenet` items are §16's 7–10, and
the row was corrected when the doc was split.
