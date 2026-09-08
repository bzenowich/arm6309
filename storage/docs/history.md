# Storage — archived history

Superseded passages, revision narratives and dead ends removed from
[`sdcard.md`](sdcard.md) (and from [`../README.md`](../README.md)) when the docs were
split into present design and archived history. Entries are organized by the spec section
they were removed from. The spec describes the card as it is; this file records how it
got there.

The one date that organizes most of this file: **2026-09-08**, the day `machine.md` §5
item 1 option D and §5 item 7 gave the machine a second physical megabyte, the block
buffer became memory, the `TFM` hazard was retired from the read path, and the card went
from 7 ICs at 537 KiB/s to 14 ICs at 681 KiB/s.

---

## §0 Summary — the buffer revision, and the numbers it replaced (2026-09-08)

The summary carried this revision banner:

> ⚠ **Revised 2026-09-08, and the revision is §11.1.** This card was specified around a
> read-triggered SPI port because the machine had no address space for a block buffer —
> "the clean answer we cannot afford". `machine.md` §5 item 1 option D and §5 item 7 made
> it affordable: **the buffer is memory now, the `TFM` hazard is retired rather than
> mitigated, and the sustained read rate is 29 % higher.** It cost six ICs. Superseded
> passages are marked in place rather than deleted.

("Marked in place rather than deleted" was the repo's convention until this split; this
file is where the marked passages now live.)

The chains the summary table and headline carried:

- **IC count: 7 → 13 → 14.** 7 was the original port-only card. 13 was the first count
  after the buffer revision, and it was wrong — see §8 below. 14 is current.
- **Sustained read: 528 → 681 KiB/s** (`CMD18` multi-block). 528 was the chunked port
  path after amortising the inter-block gap; 681 is the unchunked buffer copy, host-bound.
- **Intra-block read: 537 → 681 KiB/s.** 537 was the chunked (32-byte, masked) `TFM`
  against the port; the difference is entirely the chunking (§4.4's 21 %).
- The summary-table row "**So what is the problem?** `TFM` re-reads its source after an
  interrupt" became "Retired" the same day.
- The `$FF`-window row read "eight bytes at `$FF50`–`$FF57`" in the earliest revision,
  before the map shuffles recorded under §6.1 below.

**The "smallest card" framing.** "This card was the machine's smallest and is not any
more… The card was the machine's smallest and is now its third largest." True on both
dates; the spec now just states the standings.

**The retired timing claim.** The port design's central timing argument was the race
between a 636 ns burst and the `TFM` read interval: **2.25× margin at ÷12 `E`, 1.5× at
÷8 fast-E** — "still passes, so the card is not one of the three things that break at
that rate". The buffer made the race not exist: the engine fills SRAM on its own clock
and the host reads memory. The margins were retired with the port (the spec's §3.3 now
budgets the engine and the host separately). Note: `machine.md` §1's fast-E table still
cites `sdcard.md` §5 for the 2.25× → 1.5× margin.

**A stale figure fixed at the split:** the summary's CPLD note read "the arithmetic
favours it: **8 ICs against 13**", written before the 13 → 14 recount (§8 below). The
spec says 8 against 14 throughout.

Replaced by: §0's present-tense table and the ⚠ plumbing/CPLD note.

## Preamble §Units — the decimal figures (2026-09-08)

> The two headline figures in decimal are 680 KiB/s = **697 kB/s** and 537 KiB/s =
> **551 kB/s**. … Elsewhere in the repo the same figures appear as "537 KB/s"
> (`machine.md` §0); they are the same figures.

537 stopped being a headline figure when the chunking went; `machine.md` §0 now quotes
681 KiB/s. (The old text also rounded 680 KiB/s to 697 kB/s; 680 KiB/s is 696 kB/s —
681 KiB/s is the one that is 697 kB/s.) Replaced by: the single 681 KiB/s = 697 kB/s
figure.

## §2 — "a quarter of a second", corrected twice

The needs table originally promised the 128 KiB sample upload in "a quarter of a second",
then carried this correction:

> ⚠ **Superseded — "a quarter of a second" was transfer time, not elapsed time.**
> ~~"this turns it into a quarter of a second"~~ counted 131,072 bytes at 3.81 cycles each
> and nothing else. Every block also costs a command, an `N_CR` gap and the card's read
> access latency before the `$FE` token, and that last term is between 100 µs and 1 ms on a
> typical card. §5.1 redoes the sum. 243 ms is the honest figure and it needs `CMD18` to
> get there.

**243 ms** was then itself superseded by the buffer revision: the chunked-path elapsed
time became **193 ms** unchunked (§5.2). The upload row also read "Storage sustains
**528 KiB/s** multi-block — 77 % of [the audio card's 683 KiB/s intake], close enough
that the disk stops being the bottleneck", and "Load a program: 30 KB in 56 ms" (56 ms at
537 KiB/s; 44 ms at 681). Replaced by: 681 KiB/s / 193 ms / 44 ms throughout.

## §3.2 — the fixed-source `TFM` as the fast path (superseded 2026-09-08)

The original "what changes on a 6309" was that the port itself becomes the `TFM` source:

```
        ldx   #SDDATA          ; source: the port, not advanced
        ldy   #buffer          ; destination: advanced every byte
        ldw   #512
        tfm   x,y+             ; 6 cycles + 3 per byte
```

"`modplayer.md` §4.4 already uses the **mirror image** of this — `TFM X+,Y`, fixed
destination — to stream samples *to* the audio card at the same 3 cycles a byte… This is
the same trick pointed the other way, and §4 is about why that symmetry does not hold."

This was the card's whole fast path until 2026-09-08. Replaced by: the buffer copy
`TFM X+,Y+` (§4.5); the fixed-source form survives in the spec only as the §4.2
comparison of what must not be done.

## §3.3 — the port-era clock budget

The clock table's central rows were the burst-versus-`TFM` race:

| | |
|---|---|
| `TFM` read interval, ÷12 `E` (**specified**) | 3 `E` cycles = **1430 ns** |
| **Margin, ÷12** | **2.25×** |
| `TFM` read interval, ÷8 fast-E (**experimental**) | 3 `E` cycles = **953 ns** |
| **Margin, fast-E** | **1.5× — still passes** |

"**The card delivers a byte faster than the 6309 can take one.** So there is no `/WAIT`
path, no FIFO, and no busy-polling in the fast loop — which is what makes a bare `TFM`
possible at all."

Replaced by: §3.3's engine-fill (326 µs) versus host-copy (735 µs) budget; the byte-level
race no longer exists.

## §3.5 — provenance of the buffer, and a mux description corrected at the split (2026-09-08)

The section opened: "**New 2026-09-08.** §11.1 wanted this from the beginning and could
not have it; `machine.md` §5 item 1 option D and §5 item 7 made the address space exist."
And: "That is the whole point: the port version interleaved one SPI burst per `TFM` read
and therefore made the two rates compete; the buffer decouples them."

**Corrected at the split:** the address-mux row read "`FILL` high selects the counter;
`FILL` low selects backplane `A8`–`A0`, so the host reads the buffer as memory" — which
contradicted the same section's arbitration paragraph (and `machine.md` §5 item 7's
decided fixed-phase schedule, and §6.3's instruction to copy buffer *n* while filling
*n+1*). A statically-grabbed mux would lock the host out for the whole 326 µs fill and
make §5.2's overlap impossible. The spec now states the per-tick schedule: engine in
ticks 0–1, host in its window, whenever `FILL` is high. The §6.2 `FILL` caveat's
rationale clause "during which the `'157`s hold the host off the buffer" was corrected
for the same reason (the rule itself — never `FILL` at init speed — stands: `DONE` would
not arrive for 20.4 ms).

## §4 — the hazard as the document's centre (retired from the read path 2026-09-08)

The section heading was "⚠ The `TFM` hazard" and the intro read "§4 is the whole
document" / "This section is the reason the card is not simply 'the BE6502 design,
faster'." The retirement banner:

> **⚠ Retired 2026-09-08, and not by mitigating it.** §§4.1–4.3 below are kept because
> they are the clearest statement of the problem in the repository, `net/docs/net.md` §3.2
> cites them, and `machine.md` §6 still lists the silicon capture as a `cpu`-owned item.
> **§4.4's chunk-and-mask is superseded** — §4.5 is what the driver does now.

### §4.3 — "superseded in scope"

> ⚠ **Superseded in scope — the heading is right and the list was short by one.**
> ~~"Hardware cannot fix this"~~ is still true of *this card's* hardware, and every bullet
> above stands. But the list treats the 6309 as a fixed part, and **it is not one**: the
> CPU is C11 firmware on an STM32G431 (`machine.md` §0, `plan.md`), and §12 step 1's
> silicon capture exists to decide **what the emulator implements**, not merely to record
> what silicon does.

Replaced by: the same point stated in the spec's §4.3 closing paragraph, pointing at
§11.6. Also, §4.3's last bullet originally *rejected* the memory-mapped buffer: "It is
the clean answer, and §11.1 rejects it on address space, which is a budget problem rather
than a design one." The rejection reversed on 2026-09-08 (see §11.1 below).

### §4.4 — chunk-and-mask as the specified read fix (superseded 2026-09-08)

The section was titled "**The fix: chunk the transfer and mask around each chunk**" and
specified the read path:

```
        ldx   #SDDATA
        ldy   #buffer
        ldb   #16                  ; 16 chunks of 32
Chunk   orcc  #$50                 ; mask IRQ and FIRQ
        ldw   #32
        tfm   x,y+
        andcc #$AF                 ; unmask -- pending interrupts fire here
        decb
        bne   Chunk
```

"**Specify 32.** 537 KiB/s is still four times the BE6502 and 2.4× the hazard-free
alternative, and 49 µs is below anything else in the machine that cares."

The supersession note: "**This was the specified fix and it is not any more — §4.5.** The
listing and the chunk-size table below are kept because `net/docs/net.md` §3.2 cited
them, because `machine.md` §4's interrupt-latency table cites the 49 µs, and because if
the buffer of §3.5 is ever removed this is what comes back. **Nothing in the driver does
this now.**" — that last sentence overstated it: §9.2 step 6's *write* still chunks and
masks, which is why the spec keeps §4.4 (retitled) with the listing in write direction
and the full chunk table.

Its closing warning also carried the machine-wide caveat in its strongest form:

> **This is the one place a card's correctness depends on an undocumented CPU behaviour.**
> If §13 item 1's silicon capture shows `TFM` does *not* re-read on resume, the chunking
> can be dropped and the card runs at 680 KiB/s. If it shows something worse — a re-read at
> a different point, or a **doubled write** — the whole fast path needs rethinking, and the
> *write* path along with it (§9.2, and the same exposure on `modplayer.md` §4.4's upload).
> **Measure before writing the driver**, not after.

The "one place" claim had its own chain (recorded in the card README): it was one place,
then briefly **two** when `net/` specified the identical exposure on its data port, then
on 2026-09-08 both cards moved their buffers into `A20 = 1` and it became **none — for
bulk transfers** (the conservatively-masked write paths remain). With the masking in
place, no card's *correctness* depends on the undocumented behaviour any more; the
capture decides whether the masking can come out.

### §4.5 — title

Was "What replaced it"; now "The block path: RAM to RAM". The old §4.5 quantified the
change as "The 21 % that §4.4 cost is what §5.1's **537 → 681 KiB/s** is made of."

## §5.1 — the intra-block ceiling's chain (2026-09-08)

> ⚠ **This read 537 KiB/s until 2026-09-08**, and the difference is entirely §4.4's
> chunking. §4.5 removed the reason for it. The table §4.4 kept is still the arithmetic —
> its last row, *"512 B unchunked, 3.01 cyc/byte, 680 KiB/s"*, was always what this card
> would do if the hazard went away, and it went away.

"Three different numbers get called 'the rate'" originally introduced 537 (intra-block,
chunked), 528 (sustained `CMD18`) and 253 (per-`CMD17`); after the revision the first two
collapsed into 681. (680 vs 681: the early text rounded the 3.01-cycle rate down; 512 B /
735 µs = 681 KiB/s, which the spec uses throughout.)

## §5.2 — the old sustained-read story (2026-09-08)

> ⚠ **The old §5.2 was mostly about the card's ~1 ms read-access latency and why `CMD18`
> mattered so much** — 528 KiB/s with it against 253 KiB/s without. **`CMD18` still
> matters and the second figure is unchanged**, because a `CMD17` per block pays that
> latency 256 times and no amount of buffering hides a command that has not been sent.
> What changed is the ceiling it is measured against.

The sample-upload gap: at 528 KiB/s the 128 KiB upload took 243 ms against the audio
card's 187 ms intake — **a 56 ms gap**; at 681 KiB/s it is 193 ms — **6 ms**. "That gap
closed; it was 56 ms and it is 6 ms."

## §5.3 — write-path notes

"**Unchanged in substance**, because the bound was never the transfer… The transfer half
rises from 680 to 681 KiB/s, which is noise." And the ⚠ closed "**That is an
inconsistency this revision introduced and did not resolve** — §13 item 6" — the
inconsistency is live (spec §5.3, §13 item 6); only the this-revision framing is archived.

## §6.1 — how the four bytes came back, were spent, and the window widened (2026-09-07 / 2026-09-08)

The address-map story, in order:

1. `serial.md` §7.1 reported the `$FF40`–`$FF7F` map **exactly full at 64 of 64**, and
   the machine's open item was that there was no slack worth the name.
2. This card claimed four of the eight bytes `graphics.md` §17 had reserved for a disk
   controller — an SPI port needs four registers where a WD1773 needs five plus a latch —
   so **it gave four bytes back**: `$FF5C`–`$FF5F` free again. §6.1 called that "one
   small card, once".
3. **2026-09-07:** `net/` was that card — `net/docs/net.md` §5.1 spent the four bytes.
4. **2026-09-08:** filling the window is what closed `machine.md` §5 item 1: the
   geographic decode widened to `$FF00`–`$FF7F`, `A6` left the window strobe, and this
   card owes a seven-bit decode (the ⚠ that stays live in spec §6.1).

## §6.4 — the power-up state, previously unspecified

The section opened "The card has state that survives nothing and state that survives
everything, **and until this revision neither was specified**." The `'574` garbage row is
what caught the original §9.1's step 1: "The original §9.1 step 1 — 'ten `SDDATA` reads' —
clocks 80 bits of whatever the `'574` powered up holding. Fixed in §9.0: `SDMOSI` ← `$FF`
first, then ten reads." (`SDMOSI` itself was added to the register map in the same
revision that found this; the original map had three registers.)

## §7 — how the write rate came to be wrong

The regulator note ended: "This document sized the current from the outset and did not
model the time until now, which is how §9.2 came to claim 680 KB/s for writes." — i.e.
the busy phase was always known to exist (the regulator was sized for it) but was never
given a duration until §5.3's 126–408 KiB/s range was derived.

## §8 — the IC count: 7, then 13, then 14 (2026-09-08)

> ⚠ **13 until 2026-09-08, and it was this table's own row numbering that hid it**: the
> rows run 1 to 13, but row 13 is *two* `GAL22V10` and rows 9–11 are three `'157`, so the
> count of rows is not the count of parts. **12 single rows + 2 + … = 14.** Found while
> placing the board, which is the first thing that had to draw each package rather than
> cite it — the same way `machine.md` §7.1's four SRAMs became one.

(`hardware/place/parts.ts` asserts the 14 against the board file's `icBudget`; the root
`README.md`'s account of the CPLD refusal still says the saving was "five packages",
which was 13 − 8.)

And the trade, stated at the moment it was made:

> ⚠ **This card went from 7 ICs to 14 on 2026-09-08, and it is worth being blunt about
> what was bought.** §11.1 — 29 % more sustained throughput and the deletion of §4's
> hazard — for **seven** packages, **six of which are address and data plumbing**. The
> card was the machine's smallest and is now its third largest.

Replaced by: the judgement, kept in the spec's §8 ⚠ ("a card whose correctness rested on
an undocumented CPU behaviour was not a card to keep for the sake of six packages").

## §8.1 — the CPLD, refused on the rule, then unblocked (2026-09-08)

The original position: the `ATF1508AS` alternative "is **not taken because it would spend
the no-CPLD house rule a fourth time**", and the section said *"if the rule is retired,
take this immediately."*

**The rule was retired on 2026-09-08** (root `README.md`, which records this card's
refusal-on-the-rule-alone as part of why). The transitional text read:

> ⚠ **The rule that blocked this was retired on 2026-09-08** (root `README.md`), and this
> section said *"if the rule is retired, take this immediately."* **It is no longer
> blocked and it has not yet been taken** — §13 item 12. … Not taken in this revision
> because it is a card re-specification and nobody has asked for one — but it is no
> longer blocked.

Replaced by: spec §8.1's standing position — not taken, because with the buffer's GAL
count at two the logic *fits* GALs comfortably, and "take this immediately" was written
when the rule was the only objection; the fuse-level-verification argument and the
packages-not-capability argument outlived the rule. §13 item 12 carries it.

(The pre-buffer §8 also had a different escape hatch: "if `SDCTRL` does not fit [the
single GAL], move it to a `'574` and the card is 8" — on the 14-IC card that same escape
makes 15, and with two GALs it should not be needed.)

## §9.0 — the initialisation that was missing

§9.0 exists because the original §9.1's steps 1–2 were the entire init sequence:

> ⚠ **Superseded — §9.1 steps 1–2 were not an initialisation sequence.**
> ~~"1. `SDCTRL`: `/CS` high, init clock. Ten `SDDATA` reads → ≥74 clocks. (power-up only)
> 2. `SDCTRL`: `/CS` low, fast clock."~~ Two things are wrong and one is missing. The
> ten reads clock **whatever the `'574` powered up holding** onto `DI`, and SD requires
> `DI` high for those 74 clocks (§6.4). Step 2 selects the fast clock *before* `CMD0`,
> violating the ≤400 kHz init requirement. And the entire dialog between them — `CMD0`,
> `CMD8`, `ACMD41`, `CMD58` — is absent, so there was no point at which the card entered
> SPI mode, reported its capacity class, or was known to be ready.

"The original §9.1 went straight from 'power-up clocks' to '`/CS` low, fast clock' and
then issued `CMD17`, which as literally written puts the card above its 400 kHz init
ceiling before it has been initialised at all."

## §9.1 — two superseded read listings

**The original listing** — kept in the doc for a long time because both of its faults
follow from the card's own register semantics:

```
 1. SDCTRL: /CS high, init clock. Ten SDDATA reads -> >=74 clocks. (power-up only)
 2. SDCTRL: /CS low, fast clock.
 3. CMD17 (READ_SINGLE_BLOCK): six SDDATA writes.
 4. Poll SDDATA until the data token $FE appears.
 5. Write $FF to SDDATA -- the hold register now clocks $FF for every read.
 6. 16 x { mask; TFM X,Y+ with W=32; unmask }        <- section 4.4
 7. Two more SDDATA reads: the CRC.
 8. SDCTRL: /CS high.
```

> **Fault 1 — byte 0 is destroyed.** §6.2 defines a write to `SDDATA` as "load the MOSI
> hold register **and** trigger a burst", and §8 item 4 has the `'163`'s terminal count
> driving `RCLK` at the end of **every** burst. The step-4 poll read that returned `$FE`
> has therefore *already* prefetched data byte 0 into the `'595`'s storage register. Step
> 5's write then triggers a further burst, and *that* burst's terminal count latches data
> byte **1** over byte 0. The `TFM` in step 6 starts at byte 1 and the block is short by
> one from beginning to end — **exactly the failure §9.1's own priming paragraph warned
> about**, designed into the listing that carried the warning.
>
> **Fault 2 — `DI` carries the wrong thing during the poll.** The hold register still
> holds the sixth byte of `CMD17` throughout step 4, so every poll burst replays that byte
> onto `DI`. A host must hold `DI` high while awaiting a response or a token; a replayed
> byte with b7 = 0 and b6 = 1 has the bit pattern of a command's first byte and a card is
> entitled to start parsing it as one.
>
> **Both are fixed by moving one line.** `$FF` goes onto `DI` immediately after the sixth
> command byte, *before* any polling.

**The corrected port-era listing** (the fix in place, but the transfer still a chunked
`TFM` against the port — superseded 2026-09-08 by the buffer flow now in the spec):

```
 (card initialised per 9.0; fast clock; /CS high)
 1. /CS low.
 2. CMD17 READ_SINGLE_BLOCK, argument = block number:  six SDDATA writes.
 3. SDMOSI <- $FF.        <-- THE FIX.  DI is now high for everything that follows.
 4. Read SDDATA until a byte != $FF appears: that is R1.  Expect $00.
 5. Read SDDATA until $FE, the data token.
 6. 16 x { orcc #$50 ; ldw #32 ; tfm x,y+ ; andcc #$AF }          -- 4.4
 7. Two more SDDATA reads: the CRC16 bytes.
 8. /CS high, then one SDDATA read: eight idle clocks.
```

Its pipeline argument: "Every read returns the byte its predecessor's burst fetched. The
step-5 read that *returns* `$FE` has already triggered the burst that fetches data byte
0… **Nothing between step 5 and step 6 touches `SDDATA`**, so the first `TFM` read
returns byte 0. … Symmetrically, the last `TFM` read triggers one more burst whose byte
is not discarded but is the first CRC byte… The pipeline closes exactly." The spec's §9.1
restates this argument for the `FILL` engine, where the same prefetched byte 0 must be
the engine's *first store* rather than the first `TFM` read.

Port-era CRC arithmetic: "It would take the sustained read rate from 528 KiB/s to 512
bytes per 7.05 ms = **71 KiB/s** — seven-eighths of the card's throughput", against "the
931 µs transfer it protects" (931 µs was the chunked 3.81-cycle copy). The spec's figures
are 681 → 73 KiB/s against the 735 µs unchunked copy.

## §9.1.1 — the port-era multi-block loop

Step 4b read "`16 x { mask ; TFM X,Y+ W=32 ; unmask }`" — the chunked port transfer —
and the section quoted "**§5.2: 528 KiB/s, 98 % of the intra-block ceiling**" and "537
KiB/s of ceiling delivering 253 KiB/s of throughput". Replaced by: the `FILL`/copy
overlap flow and 681 KiB/s host-bound.

## §9.2 — the write sequence that wasn't one

> ⚠ **Superseded — the original §9.2 was not a write sequence and its rate was wrong by
> two to five times.** ~~"`TFM X+,Y` — the fixed-destination form, the one `modplayer.md`
> §4.4 already uses, and **the one with no §4 hazard**. Writes need no chunking and no
> masking, so they run at the full 680 KB/s."~~ It named an instruction and called that a
> protocol. **Missing: the start token, the two CRC bytes, the data-response token, and —
> the one that costs real time — the busy phase.** §7 of this document already sizes the
> regulator for the programming current *because* that phase exists, so the phase was never
> in doubt; it simply never had a clock put on it. §5.3 does that: **680 KiB/s of transfer,
> 126–408 KiB/s sustained.**

And the second-order correction: "**'writes need no chunking and no masking' was
asserted, not established.** The correct statement is 'no chunking *pending* §12 step 1's
answer'" — which is the caveat the spec's §9.2 now carries in present tense.

## §9.3 — what the original error handling was

"Nothing in the original §9 could fail. There was no R1 check, no error-token decode, no
timeout anywhere, and no story at all for a card arriving or leaving. A `CMD17` for an
out-of-range block, or for a card that has been pulled, sets an R1 error bit and then
sends **no token, ever** — and the specified poll loop waits for it forever." Also: "The
original listing skipped straight past every [error token], because `$00`–`$1F` is
neither `$FF` nor `$FE` and the loop tested only for `$FE`." And on the card-swap ladder:
"That is a strict improvement on the previous specification, whose behaviour was to
notice nothing at all."

## §11.1 — "the clean answer we cannot afford", then taken (2026-09-08)

The section was the buffer proposed, rejected, re-opened and adopted; the spec keeps only
the decision and its cost. The full narrative:

> **~~Rejected on address space, not on merit.~~** The `$FF40`–`$FF7F` window was 64 bytes
> and the 1 MB physical map had no room either: `graphics.md` §6.3 fixed `A19 = 0` as
> 512 KB of system RAM and `A19 = 1` as the video card's ring, with nothing spare.
>
> **`machine.md` §5 item 1 option D put physical `A20` on the backplane.** The map SRAM's
> eighth bit was already stored and drove nothing, so a second megabyte cost one pin and
> no parts, and §5 item 7 divided it into sixteen 64 KB regions. **This card takes one and
> uses 2 KB of it.**
>
> **And the arbitration turned out not to need `/WAIT`.** That was this section's last
> objection when it was re-opened. `machine.md` §5 item 7's answer is a fixed `CLK25`
> phase — the host owns the buffer in ticks 7–11 of each bus cycle and the fill engine
> takes ticks 0–1 — so nothing is deferred by more than one bus cycle and the `'595`'s
> storage register absorbs that. §3.5.

"**Every word of that came true**, which is unusual enough for a rejected alternative to
be worth saying plainly. §3.5 is the circuit, §4.5 is the hazard going away, §5 is the
rate." — and: "**What it cost, which this section never estimated:** six ICs (§8), of
which five are address and data plumbing, and a second `GAL22V10`. This section said 'the
clean answer we cannot afford' and priced only the address space; the plumbing is the
part that was invisible from here."

> **This section was cited as "the strongest argument yet for `machine.md` §5 item 1"**,
> and it was — `machine.md` §5 item 1 quotes it. It is worth recording that the argument
> worked: the item closed, and this is one of the two cards that spent the result.

## §11.6 — what the firmware option was priced against (2026-09-08)

Before the buffer, specifying the hazard out of the CPU bought the *read* path:

| | chunked, as specified | with the firmware fix |
|---|---|---|
| Intra-block read (§5.1) | 537 KiB/s | **680 KiB/s** (+27 %) |
| Sustained read, `CMD18` (§5.2) | 528 KiB/s | **667 KiB/s** |
| 128 KiB of samples (§5.2) | 243 ms | **193 ms** — against the audio card's 187 ms intake, i.e. exactly matched |
| Sustained write (§5.3) | 126–408 KiB/s | unchanged — program-bound, not transfer-bound |
| Masked interrupt window | 49 µs, 16 times a block | **none** |
| Read-block driver | a 16-iteration chunk loop with `ORCC`/`ANDCC` | **one `TFM`** |
| §12 step 4's 10⁵-block test | required | **still required** |

"+27 % on reads and a driver that is one instruction, against one entry in the divergence
ledger and one mode bit."

**§11.1 was taken the same day, which changed what the question is for.** The 27 %
arrived without the capture and without the divergence; the option's remaining
constituency is the write side — this card's §9.2 masking and `modplayer.md` §4.4's
upload — which is how the spec's §11.6 now prices it. (For a while the argument had a
second card behind it: `net.md` §3.2 paid the same 21 % read tax and a dropped Ethernet
frame cannot be re-read — but net moved its buffers into `A20 = 1` the same day and left
the constituency too.)

## §12 — port-era build-order wording

- Step 3's escape read "or the card becomes **8** ICs" (the 7-IC card plus an `SDCTRL`
  `'574`); on the 14-IC card the same escape makes 15.
- Step 4 was "**Block read with chunked `TFM`** against a block of known content", and
  named §4's hazard as what it catches.
- Step 7 read "**§5.2 predicts 528 KiB/s** — not the 537 KiB/s intra-block ceiling, which
  is not a throughput and cannot be measured over a file. Exit at ≥500 KiB/s sustained…
  If the measured rate lands nearer §5.2's `CMD17` column, the driver is not issuing
  `CMD18`." At 681 the ceiling and the sustained prediction are the same number, so the
  spec's step 7 keeps only the measured-over-a-file distinction; the ≥500 exit bar
  (≈95 % of 528) became ≥650 (≈95 % of 681).
- The closing line was "step 4 is the only step that can prove §4's mitigation actually
  works" — there is no mitigation to prove any more; step 4 proves the pipeline.

## §13 item 1 — the downgrade (2026-09-08)

> **~~⚠ `TFM`'s interrupt/resume behaviour~~ — downgraded 2026-09-08, not closed.** §4
> was the central section of this document and rested entirely on community
> documentation. **§4.5 retired the exposure**: the block path copies RAM to RAM, and
> §4.2's own argument says a re-read of RAM is idempotent. The 27 % this item promised
> arrived without the capture.

Replaced by: the item restated in present tense (two of three capture questions still
decide something).

## §13 item 8 — the `$FF` map, closed (2026-09-08)

> **~~The `$FF` map still has no slack worth the name.~~ CLOSED 2026-09-08** —
> `machine.md` §5 item 1. The window is `$FF00`–`$FF7F` and 64 bytes are free. ⚠ **What
> this card owes as a result is a seven-bit decode** (§6.1): `A6` left the strobe, and
> six bits answer at `$FF58` and `$FF18` both. *Superseded text follows.* §6.1 hands four
> bytes back; that is one small card, once. `machine.md` §5 item 1 remains the machine's
> blocking decision, and §11.1 shows it now costs throughput as well as expandability.

The seven-bit-decode residue lives in spec §6.1's ⚠; the give-back story is under §6.1
above.

## `../README.md` — narrations removed from the card README

The README carried the same chains in shorter form; archived here rather than
re-narrated: "**That used to be where it went wrong**" (the hazard intro, superseded by
the retirement); the ⚠ chain "**~~This is the only place in the machine where a card's
correctness depends on an undocumented CPU behaviour.~~** It was, then briefly it was two
(`../net/` had the identical exposure on its data port), and on 2026-09-08 both cards
moved their buffers into the machine's new physical space and it became none — for bulk
transfers"; the `$FF5C`–`$FF5F` spend of 2026-09-07 and the window widening (§6.1 above);
the rates table's ~~537~~/~~528~~ strikethroughs; "**7 ICs became 14** … The card was the
machine's smallest and is now its third largest"; "the rule was retired on 2026-09-08 and
this is no longer blocked"; and §11.6's re-scoping note "**§11.1 was taken the same day,
which changes what the question is for.**" The README's units note also equated
537 KiB/s = 551 kB/s, per the preamble entry above.
