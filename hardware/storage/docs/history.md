# Storage — archived history

Superseded passages, revision narratives and dead ends removed from
[`sdcard.md`](sdcard.md) (and from [`../README.md`](../README.md)) when the docs were
split into present design and archived history. Entries are organized by the spec section
they were removed from. The spec describes the card as it is; this file records how it
got there.

Two dates organize this file. **2026-09-08**, the day `machine.md` §5 item 1 option D and
§5 item 7 gave the machine a second physical megabyte, the block buffer became memory, the
`TFM` hazard was retired from the read path, and the card went from 7 ICs at 537 KiB/s to
14 ICs at 681 KiB/s. And **2026-09-20**, the day that reversed: `storage/logic/census.ts`
counted the card's logic in **pins** rather than macrocells, found the buffered card was
four `GAL22V10`s and so **16 ICs rather than 14**, and the buffer came out — back to
8 ICs at 537 KiB/s, with §4.4's chunk-and-mask carrying both paths.

Entries are keyed by the spec section they were removed from; the 2026-09-08 ones come
first and the 2026-09-20 ones are collected under their own heading at the end, so a
section that moved twice appears twice.

---

## sdcard.md §4.1 and §14 — the `TFM` rule was cited to documents this project does not hold (2026-09-21)

§4.1's hazard is the present design. This records the provenance it was carried on
until the primary source was found **in `reference/`** and the operating system's
own practice was surveyed. `hardware/cpu/docs/6309.md` §5.1 is the full treatment.

**The confidence table said:**

> | **`TFM` is interruptible, uses a one-byte internal cache, and re-reads the
> source address on resume** | HD63B09EP Technical Reference; *A Memo on the
> Secret Features of 6309* | ⚠ **community documentation, not silicon. §13 item 1;
> §4's statement of the hazard, §9.1's read path and §9.2's write-path caveat all
> rest on it.** |

**and §14 said:**

> | HD63B09EP Technical Reference Guide; *A Memo on the Secret Features of 6309* |
> §4.1's `TFM` behaviour. ⚠ Neither is in `reference/` |

⭐ **Both understated the provenance.** `reference/manuals/The 6309 Book (Burke &
Burke).pdf` — which *is* in `reference/` — states the rule outright on the `TFM`
instruction page: *"The instruction is interruptible. An interrupt during Form 4
re-reads the peripheral referenced by r1 without storing the previous data byte,
advancing r2, or decrementing W; use Form 4 only with interrupts disabled."* And
NitrOS-9's `level1/modules/rb1773.asm:547-551` is an eyewitness account of the
same failure — *"the tfm will repeat a byte and lose track"* — beside the
vestigial `ldw`/`ldy` of the `TFM` its author removed because of it.

⛔ **And the correction cuts the other way for §9.2.** The old row made the
read-path and write-path caveats rest on one citation. They do not: the book names
**Form 4 only** and is silent on the fixed-destination form, and NitrOS-9 is split
1–3 on it — `llscsi.asm:637` masks its port write, `archive/drivers/tccc/tccchd.asm`
runs an unmasked 1024-byte one, in the same file whose read path it chunks into
four masked pieces. **§9.2's caveat is weaker-sourced than §9.1's, not equally
sourced**, and §12 step 1 still owes that capture.

⚠ **An interim reading on 2026-09-21 claimed NitrOS-9 "has masked exactly the
Form 3 case since 6309 support was written."** That generalised from `llscsi`
before `tccchd` was looked at, and it is wrong.

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
> they are the clearest statement of the problem in the repository, `hardware/net/docs/net.md` §3.2
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
listing and the chunk-size table below are kept because `hardware/net/docs/net.md` §3.2 cited
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
then briefly **two** when `hardware/net/` specified the identical exposure on its data port, then
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
3. **2026-09-07:** `hardware/net/` was that card — `hardware/net/docs/net.md` §5.1 spent the four bytes.
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

(`hardware/tools/place/parts.ts` asserts the 14 against the board file's `icBudget`; the root
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

---

# 2026-09-20 — the buffer removed, and the card back to eight ICs

**The reversal of everything 2026-09-08 decided.** The storage card is NormalLuser's
BE6502 SD interface (`sdcard.md` §3.1) and nothing more: the memory-mapped block buffer
and its engine are gone, the card uses no physical address space at all, and §4.4's
chunk-and-mask — which §9.2's write path already ran — is now the discipline on the read
path too. **14 ICs at 681 KiB/s became 8 ICs at 537.**

**What settled it was a count nobody had made.** `hardware/storage/logic/census.ts` lists
every net the card's logic needs and searches *every* partition of it, rejecting any part
over a `GAL22V10`'s 22 usable pins. §8.1 had derived "two GALs" from a **macrocell**
estimate; pins are the binding constraint, and in pins the **buffered** card is **four**
`GAL22V10`s — so it was a **16-IC card, not the 14 §8 claimed**. What breaks it is the
region decode: 16 pins for that unit alone. The port card fits two, `dec+stat` at 22 pins
with none spare and `ctrl+eng` at 18 with four, and those two are `sdbus` and `sdeng`,
which are now built and checked (24 claims, `storage/logic/storage.check.ts`).

**The 21 % is recoverable and the route is §11.6**, not the buffer: if the 6309 firmware
resumes `TFM` without re-reading the source, the masking comes out and the port path is
680 KiB/s. §12 step 1's silicon capture still decides it.

## §0 Summary — the buffer-era table (2026-09-20)

The rows that moved, and what they said:

| Question | The 2026-09-08 answer |
|---|---|
| **Where do the bytes land?** | **In a 2 KB SRAM the host addresses as memory** — four 512-byte block buffers in the card's 64 KB region at `A20 = 1`. (§3.5, §6.5) |
| **What drives a block transfer?** | **A 9-bit address counter and a "fill" bit.** The host writes a command; the engine runs 512 bursts by itself and raises a status bit. (§3.5) |
| **What about `TFM`'s interrupt re-read?** | **Retired, not mitigated.** The host copies RAM → RAM, and a re-read of RAM is idempotent (§4.2). **No chunking, no masking.** (§4) |
| **Is `TFM` settled, then?** | **Not for the machine** — `SDDATA` is still a side-effecting port and §9.0's initialisation still uses it. But **no bulk transfer in this machine runs over a port**, so the silicon capture decides a single-byte question. (§4.5) |
| **Read rate, intra-block** | **681 KiB/s** — the unchunked `TFM`, which is the only kind. |
| **Read rate, sustained** | **681 KiB/s** with `CMD18` multi-block and double buffering: the SPI engine fills a buffer in 326 µs while the host copies the previous one in 735 µs, so **the host is the bottleneck and the card never waits on the SD card at all.** |
| **Address cost** | **Four bytes at `$FF58`–`$FF5B`, plus one 64 KB physical region at `A20 = 1`** of which 2 KB is used. |
| **IC count** | **14**, plus a 3.3 V regulator and the socket. |

and the plumbing/CPLD note under it:

> ⚠ **Half of this card is the buffer's plumbing, and each of those packages buys exactly
> one thing.** A `6116` for the buffer, a `74HC4040` for the block address, a `74HCT245`
> for the data path, and three `74HC157`s to mux the address between the engine's counter
> and the backplane — the price of the buffer being memory rather than a port, and the
> same price [`../../net/`](../../net/) pays for the same reason.
>
> The one-package alternative is an `ATF1508AS` absorbing the counter, the mux and both
> `GAL22V10`s — an **8-IC card against 14**. The no-CPLD house rule that once blocked it
> is retired (root `README.md`), so nothing rules it out; **it is not taken**, because
> this card's logic fits two GALs comfortably, so a CPLD here buys packages rather than
> capability. §8.1 weighs it; §13 item 12 carries it.

The fast-E paragraph went with it — "The SPI burst races nothing on the CPU side, because
the engine fills the buffer autonomously and the host reads SRAM. What constrains the card
is `machine.md` §5 item 7's bus schedule, which is a ÷12 schedule (§3.5)" — and the
burst-versus-`TFM` race it had replaced came back (§3.3 below).

**The chains:** IC count **7 → 13 → 14 → 8**; intra-block read **537 → 681 → 537 KiB/s**;
sustained read **528 → 681 → 537**; the card was the machine's smallest, then its third
largest, and is its smallest again.

## §3.3 — the engine-versus-host budget, and the runt-pulse rule (2026-09-20)

The buffer-era clock table's two middle rows were

| | |
|---|---|
| Engine fill, 512 bursts | **326 µs** per block (§3.5) |
| Host copy, `TFM X+,Y+` at ÷12 `E` | 3 `E` cycles/byte = 1430 ns → **735 µs** per block |

with "**The engine fills a buffer 2.25× faster than the host empties one**, which is what
makes §5.2's double buffering work." Replaced by the *return* of the port-era
burst-versus-`TFM` race — 636 ns against 1430 ns, **2.25× at ÷12 and 1.5× at fast-E** —
which is the form `machine.md` §1's fast-E table had gone on citing throughout.

**And the runt-pulse hazard was deleted by the way the engine had to be built.** The rule
read:

> Switching the speed-select bit muxes between two asynchronous clocks and can emit a
> **runt `SCK` pulse** … **Rule: change the `SCK` rate only with `/CS` high and `BUSY`
> low**, and follow the change with eight dummy clocks (one `SDDATA` read) before
> asserting `/CS`.

A `GAL22V10` has one clock pin, and a part holding both `SDCTRL` (written at `E` rate) and
the burst counter (running at SPI rate) cannot clock both — clocking `SDCTRL` off a
393 kHz tap would miss a 238 ns write strobe outright. So everything on `sdeng` is clocked
by `CLK25` and the SPI clock is an enable; `BUSY` then only ever changes on the SPI clock's
falling edge, and `SCK`'s high phases are whole ones whatever the mux is doing. **The rule
is kept anyway** (spec §3.3, §9.0 step 8), because a card mid-command does not care whose
fault an extra edge was.

## §3.5 — the block buffer and its engine (removed 2026-09-20)

The whole section, verbatim:

> | | |
> |---|---|
> | **The buffer** | a `6116`, 2K×8, 55 ns — **four 512-byte block buffers** |
> | **Where** | the card's 64 KB region at `A20 = 1`, offsets `$0000`–`$07FF`. `machine.md` §5 item 7: sixteen regions of 64 KB, selected by physical `A19`–`A16` against a four-position jumper, **qualified by `/IOPAGE` high** |
> | **What fills it** | a **`74HC4040` 9-bit address counter** and a `FILL` bit in `SDCTRL`. Setting `FILL` makes the burst engine self-trigger: byte, `/WE`, increment, repeat, 512 times, then clear `FILL` and set `DONE` |
> | **The address mux** | three `74HC157`s. With `FILL` low they select backplane `A8`–`A0` always; with `FILL` high the select follows `machine.md` §5 item 7's phase schedule — the engine's counter in its ticks 0–1 slot, the backplane in the host's window — **so the host reads the buffer as memory even while a fill runs** |
> | **The data path** | one `74HCT245` between the backplane `D0`–`D7` and the buffer's data bus. The `'595`'s outputs are on that local bus, not the slot bus |
>
> **The engine is 326 µs per block and the host is 735 µs**, so with two of the four buffers
> in flight the SD card is never the bottleneck (§5.2): the engine's fill rate and the
> host's copy rate never compete for the same bus.
>
> **Bus arbitration is `machine.md` §5 item 7's fixed schedule and it costs this card
> nothing.** The host owns the buffer in ticks 7–11 of each bus cycle; the engine takes
> ticks 0–1. The engine needs a byte per 636 ns and gets one per 476.7 ns, and its byte
> survives the deferral in the `'595`'s storage register — **which already exists for
> §3.4's reason** and earns its keep twice.
>
> > ⚠ **The `'595` is doing two jobs and neither faces the slot bus.** In the BE6502
> > original — and in any single-glance reading of §3.1's diagram — its three-state output
> > drives the host data bus; here it drives the buffer's local bus, and its `/OE` is the
> > engine's write window rather than a bus-read decode. **This is the single most likely
> > place to get the build wrong**, because the part is unchanged and its wiring is not.

Replaced by: nothing — there is no buffer. The `'595` drives the backplane's `D0`–`D7`
directly again (spec §3.2, §8), so the section's closing warning — that the part is
unchanged and its wiring is not — stopped applying with it.

## §4 — "Retired, not mitigated" (2026-09-20)

The section was headed "The `TFM` hazard, and how this card stopped having one" and opened

> ⚠ **Retired, not mitigated.** The hazard below is real; this card's block path simply
> does not face it, because the block copy is RAM to RAM (§4.5). §§4.1–4.3 state the
> problem in full: `hardware/net/docs/net.md` §3.2 cites them, §9.2's write path still faces the
> hazard's mirror image, and `machine.md` §6 keeps the silicon capture as a `cpu`-owned
> item.

Replaced by: "Mitigated, not retired" — every bulk transfer on the card runs `TFM`
against the port, in both directions, and §4.4 is the answer on both.

§4.3's last bullet read "**A memory-mapped block buffer fixes it completely** … It is the
clean answer, **and it is the one taken**: §3.5 is the circuit, §11.1 records the
decision." It is still the clean answer; it is not taken, because it doubles the card from
8 packages to 16 (§8.1).

§4.4 was titled "**Chunk-and-mask — retired from the read path, still the write path's
discipline**" and carried the write-direction listing alone, with "The block *read* does
not need this — its source is memory (§4.5). **§9.2 step 6's write does** … and it is the
only place in the machine the technique survives". Replaced by: both directions, the same
loop, in the spec's §4.4.

## §4.5 — the block path, RAM to RAM (dropped 2026-09-20)

The whole section, verbatim:

> The hazard was never about `TFM`. It was about **a port whose read has a side effect**,
> and §4.2 already contains the answer: against RAM, a re-read is idempotent. §3.5's buffer
> is RAM. The block read is
>
> ```
>         ldx   #buffer_in_card    ; the card's block buffer, mapped through the MMU
>         ldy   #dest
>         ldw   #512
>         tfm   x+,y+              ; no masking, no chunking, no 21 %
> ```
>
> and an interrupt landing anywhere inside it re-reads a memory location and gets the same
> byte back. **The unchunked copy is 21 % faster than the chunked one** — 681 KiB/s against
> 537 (§4.4's table, §5.1).
>
> **Three things this does not do:**
>
> 1. **It does not settle `TFM` for the machine.** `SDDATA` (§6.2) is still a read-triggered
>    port and §9.0's initialisation drives the card through it a byte at a time.
>    Single-byte reads are not `TFM` loops, so the exposure is gone in practice — but
>    `machine.md` §6's capture is still owed, and §11.6's option to specify the hazard out
>    of the CPU is still on the table for its own reasons.
> 2. **It does not remove the phantom-read requirement.** §3.4's rule — the core drives
>    `$FFFF` on every dead cycle — still protects `SDDATA`. The buffer does not need it.
> 3. **It does not help the write path.** §9.2 still pushes 512 bytes out through the port…
>    ⚠ **and it should not have to.** The buffer is bidirectional and the engine can drain
>    it as easily as fill it; `SDCTRL` would need a direction bit and the write path becomes
>    symmetric. **This document specifies the read path against the buffer and leaves the
>    write path on the port**, which is an inconsistency, not a design — §13 item 6.

Replaced by: §4.4, which is what the read path does now. Item 3's ⚠ — that the write path
"should not have to" stay on the port — is what §13 item 6 booked, and it closed by the
read path joining the write path rather than the other way round.

## §5.1 / §5.2 — the buffer's rates (2026-09-20)

§5 opened "Three different numbers get called 'the rate' — and two of them are the same
number, which is the clearest sign the buffer is the right shape." Two of them are still
the same number, for a different reason: the card's read-ahead collapses the inter-block
gap, so the intra-block ceiling *is* the sustained rate.

§5.1 read: "**681 KiB/s.** A `TFM X+,Y+` of 512 bytes from the card's buffer into system
RAM, at 3.01 cycles/byte against `E` = 2.0979 MHz: 735 µs a block. **Nothing about the SPI
side sets this number.** The engine fills the buffer on its own clock and the host reads
memory; the two rates never compete, which is what §5.2 is about."

§5.2, "Sustained read: the host, and nothing else", verbatim:

> | | per 512-byte block | |
> |---|---|---|
> | SPI engine fills a buffer | **326 µs** | 512 × 636 ns |
> | host copies a buffer | **735 µs** | 512 × 1435 ns |
> | **sustained, `CMD18` + double buffering** | **735 µs → 681 KiB/s** | **the host is the bottleneck** |
>
> **With four buffers (§3.5) and `CMD18` READ_MULTIPLE_BLOCK, the SD card is never waited
> on.** It streams into buffer *n+1* while the host copies buffer *n*, and it finishes
> 2.25× before the host does.
>
> **`CMD18` is still what makes the number real.** A `CMD17` per block pays the card's
> ~1 ms read-access latency 256 times per 128 KiB instead of once, and no amount of
> buffering hides a command that has not been sent: **253 KiB/s** — §9.1.1.
>
> **128 KiB of mod samples** arrive in **193 ms**, against the 187 ms the audio card needs
> to swallow them (`modplayer.md`) — a 6 ms gap.

Replaced by: 537 KiB/s from the 931 µs chunked `TFM`, with `CMD18` still mandatory and
§9.1.1's 253 KiB/s single-block figure unchanged. The elapsed figures moved with it:
the 128 KiB sample upload **193 ms → 238 ms** against the audio card's 187 ms intake
(the gap **6 ms → 51 ms**), and "load a program, 30 KB" **44 ms → 56 ms**.

§5.3 kept its 126–408 KiB/s — the bound was never the transfer — and lost its closing ⚠,
"**The write path is still on the port** (§4.5 item 3), so it still pays §4.4's masking
tax in the form the buffer exists to delete — §13 item 6", which is no longer an
asymmetry.

## §6.1 — the 64 KB region (2026-09-20)

The placement section was "four bytes, and one region": "**`$FF58`–`$FF5B`, four bytes** …
**plus one 64 KB physical region at `A20 = 1`** (`machine.md` §5 item 7), of which this
card uses 2 KB." Its second ⚠ bullet:

> - **The region base is a second jumper**, four positions against physical `A19`–`A16`,
>   and the region decode is qualified by **`/IOPAGE` high** — a buffer is a
>   physical-memory decode and `machine.md` §2's rule is not optional for it. ⭐ `/IOPAGE`
>   also silences the card above 2 MB, for nothing: the map is 32 MB and `A21`–`A24`
>   never leave the motherboard — `machine.md` §2.

Replaced by: no physical address space at all. The first bullet — the seven-bit `A0`–`A6`
decode — stays, and is now a checked claim rather than a warning (`storage.check.ts`
sweeps all 8,192 input combinations and asserts silence at `$FF18`–`$FF1B`).

## §6.2 / §6.3 — the register bits the buffer needed (2026-09-20)

`SDCTRL` was

| Off | Name | R/W | Function |
|---|---|---|---|
| `+$2` | `SDCTRL` | W | b0 `/CS`, b1 clock rate, **b2 `FILL`**, **b3 `BUF[1:0]` low**, **b4 `BUF[1:0]` high**, b7 soft reset. **`$00` is the safe state and is what `/RESET` forces** — §6.4 |

with:

> **`FILL` is the whole engine.** Writing it with `BUF` selecting one of the four 512-byte
> buffers (§3.5) starts the block: the burst engine self-triggers, the `'4040` counts, and
> 512 bytes land in the buffer. `FILL` self-clears at terminal count and `SDSTAT` bit 3
> goes high.
>
> ⚠ **`FILL` must not be set with `/CS` high or the clock at 393 kHz.** At init speed a
> block is 20.4 ms of engine occupancy, and `DONE` does not arrive until it ends. The GAL
> qualifies `FILL` on the fast-clock bit; **that is one product term and it is not
> optional**, because the failure is a card that appears to hang.

and `SDSTAT` was

| Bit | Name | Meaning |
|---|---|---|
| **3** | **`DONE`** | **a `FILL` block finished; the buffer `BUF` named is complete** (latched, cleared by the next `FILL`) |
| 4–7 | — | read 0 |

with "**`DONE` is what the block path polls**, and a 512-byte fill is 326 µs — 684 bus
cycles — so it is polled, not raced. ⚠ **A driver that polls `DONE` in a tight loop wastes
the 326 µs the buffer exists to overlap**", and the note that `DONE` was deliberately not
an interrupt for the same reasons `CD` is not.

Replaced by: `SDCTRL` b0/b1/b7 only, b2–b6 unimplemented; `SDSTAT` b0 `BUSY`, b1 `CD`,
b2 `WP`. ⚠ **And "4–7 read 0" was wrong even then** — `sdbus` three-states `D0`–`D2` for
an `SDSTAT` read and drives nothing else, so b3–b7 are whatever the bus floats to and the
driver masks. The design output is what says so.

§6.2 also carried "**The `'574`'s clock edge must lead the `'165`'s parallel load**, so the
load is taken from the burst's own first clock rather than from the write strobe" —
replaced by the built answer: `MOSICK` is **active low**, so its latching edge is `E`-fall,
and `sdeng` takes `DATSTB`'s falling edge and is registered on `CLK25`, so the hold
register is loaded before the burst it triggered can start, by construction.

§6.5's recorded alternative ended "**It costs one macrocell**; it arrives with §8.1's 8-IC
version, if that version happens." The 8-IC version happened without it: `sdeng` is full at
10 of 10, so the pending-trigger flop is no longer free. §6.5's lockout also stopped being
a product term and became a wire — the `'163`'s `/CLR` is tied to `BUSY`.

§6.6's inverter table offered "**1 macrocell** — available only if §8's overflow moves
`SDCTRL` to a `'574` and frees four. **This is the first claim on those four.**", and a
"15th package". The four never freed; the package would be a ninth.

## §8 — the fourteen-IC table (2026-09-20)

Verbatim:

> | # | Part | Function |
> |---|---|---|
> | 1 | **74HCT595** | MISO shift + storage; three-state onto **the buffer's local data bus** — §3.5, not the slot bus |
> | 2 | 74HC165 | MOSI shift, parallel-loaded from the hold register at each burst |
> | 3 | 74HC574 | MOSI hold register — §6.2's persistence |
> | 4 | 74HC163 | burst counter: eight clocks, terminal count drives `RCLK` and clears `BUSY` |
> | 5 | 74HC393 | clock divider, `÷2` and `÷64` taps off the 25.175 MHz master |
> | 6 | 74LVC125 | 3.3 V level shift for `SCK`, `MOSI`, `/CS` |
> | 7 | **6116** 2K×8, 55 ns | **the block buffer — four 512-byte buffers.** §3.5 |
> | 8 | **74HC4040** | **the fill engine's 9-bit block address counter** |
> | 9–11 | **74HC157** ×3 | **address mux: the counter during the engine's slot, backplane `A8`–`A0` otherwise** |
> | 12 | **74HCT245** | **backplane `D7`–`D0` ↔ the buffer's local data bus** |
> | 13 | **GAL22V10** ×2 | decode from `/IOSEL` **and** the `A20 = 1` region; `SDCTRL` including `FILL`/`BUF`; `SDSTAT`; the burst trigger; the `machine.md` §5 item 7 bus phase |
>
> **Total: 14.** Plus a 3.3 V LDO, an SD socket, and passives. (The rows number 1–13
> because two of them carry more than one package — count footprints, not rows;
> `hardware/tools/place/parts.ts` asserts the 14.)
>
> > ⚠ **Seven of the fourteen packages are the buffer, and it is worth being blunt about
> > what they buy**: §3.5 — 29 % more sustained throughput than a chunked port path, and
> > the deletion of §4's hazard from the read path — for seven packages, **six of which are
> > address and data plumbing**. The card is the machine's third largest. Whether that is a
> > good trade is a judgement, and this document's is that a card whose correctness rested
> > on an undocumented CPU behaviour was not a card to keep for the sake of six packages.

and the ⚠ under it:

> ⚠ **Seven of the fourteen packages are the buffer, and it is worth being blunt about
> what they buy**: §3.5 — 29 % more sustained throughput than a chunked port path, and
> the deletion of §4's hazard from the read path — for seven packages, **six of which are
> address and data plumbing**. The card is the machine's third largest. Whether that is a
> good trade is a judgement, and this document's is that a card whose correctness rested
> on an undocumented CPU behaviour was not a card to keep for the sake of six packages.

⛔ **And the 14 was itself wrong.** `storage/logic/census.ts` counts pins rather than
macrocells: row 13's "GAL22V10 ×2" is four parts, not two, because the region decode alone
needs 16 pins. The buffered card was **16 ICs**. Replaced by: spec §8's eight-package
table — two GALs and six discretes.

## §8.1 — "Two GALs, and the one-package alternative that is not taken" (2026-09-20)

Verbatim:

> The card's logic does not fit one `GAL22V10`. The decode from `/IOSEL`, the burst trigger,
> `SDCTRL` and `SDSTAT` were already roughly ten macrocells of a `GAL22V10`'s ten; add the
> region compare (`A19`–`A16` against a jumper, plus `A20`, `A15`, `/IOPAGE`), the
> `FILL`/`BUF` control bits, the `'157` select, the `'4040` clock and clear, the `'245`
> enable and direction, and `machine.md` §5 item 7's two-tick engine window. **That is not a
> fit; it is a second part**, and §8 row 13 is budgeted as two.
>
> > **One `ATF1508AS` absorbs both GALs, the `'4040` and the three `'157`s** — the counter
> > is 9 macrocells, the mux is 9 more, and the part has 128 with 60 I/O. The card would be
> > **8 ICs**: `'595`, `'165`, `'574`, `'163`, `'393`, `'LVC125`, `6116`, CPLD. Cheaper
> > than 14, fewer things to get wrong, and in-circuit reprogrammable.
> >
> > **The no-CPLD house rule that once refused this is retired** (root
> > [`README.md`](../../../README.md)), so nothing blocks it — and **it is not taken**. What
> > weighs:
> >
> > | For | Against |
> > |---|---|
> > | **8 ICs against 14** — six packages, all of them address and data plumbing | **~160 mA against two GALs' ~140–180 mA** — roughly a wash, not the saving CPLDs give on bigger cards |
> > | one part to fit instead of two, and in-circuit reprogrammable over JTAG | ⚠ **fuse-level verification is lost.** `hardware/tools/gal/jedec/` reads a `GAL22V10`'s fuse map back and executes it; prjbureau rates the ATF1508AS database *"Partial"* and its programming path *"Untested"* (`graphics.md` §10.1.6) |
> > | the same decision video, audio and net all reached | this card is the only one whose logic **fits two GALs comfortably**. The others took CPLDs because a GAL could not carry them |
> >
> > **That last row is the real argument against**, and it is not a rule — it is that a
> > CPLD here buys packages rather than capability, which is the weakest case for one in
> > the machine. §13 item 12 carries the question.
>
> **What the second GAL costs elsewhere**: nothing on the backplane, ~50 mA, and one more
> part to program. **What it does not cost is the `74HC574` escape hatch** — §12 step 3's
> "if `SDCTRL` does not fit, move it to a `'574`" would make the card 15, and with two
> parts it should not be needed.

⚠ **The macrocell estimate in the first paragraph is the thing to notice**: it is about
equations, and a `GAL22V10`'s binding constraint here is **pins**, 22 usable of 24.
Nothing had counted them until `census.ts`. Replaced by: spec §8.1's partition search —
`dec+stat` 22 pins / 0 spare, `ctrl+eng` 18 / 4, and the finding that the buffered card is
four parts. The `ATF1508AS` case was packages and nothing else, and it was **the only
thing that made the buffered card affordable in packages** (8 against 16); with the card
already at 8 it has nothing left to buy.

Also dropped: "**What the second GAL costs elsewhere**: nothing on the backplane, ~50 mA,
and one more part to program. **What it does not cost is the `74HC574` escape hatch** —
§12 step 3's 'if `SDCTRL` does not fit, move it to a `'574`' would make the card 15, and
with two parts it should not be needed." `SDCTRL` fits: `sdeng` is 10 macrocells of 10.

## §9 — the `FILL` steps (2026-09-20)

§9.1's read listing had the transfer as two steps against the buffer:

```
 6. SDCTRL: FILL, with BUF naming a free buffer.  The engine runs 512 bursts and lands
    the block in the buffer -- 326 us.  Poll SDSTAT DONE.               -- 3.5, 6.3
 7. TFM X+,Y+ the 512 bytes out of the buffer (4.5) -- or leave them where they are
    until they are wanted; the buffer is memory.
```

and its pipeline paragraph put the off-by-one inside the engine: "The engine must
therefore write the `'595`'s current contents into the buffer *before* triggering its own
first burst — store, then fetch, 512 times — or every block lands shifted by one."
Replaced by: the chunked `TFM` at step 6, and the port-era statement of where the pipeline
closes — nothing between step 5 and step 6 touches `SDDATA`, so the first `TFM` read
returns byte 0.

§9.1.1 step 4b read "`SDCTRL: FILL, BUF = n mod 4.  While the engine fills buffer n, TFM
buffer n-1 out to its destination; only then poll DONE.`", and its step 6 ended "`TFM the
last buffer out.`" The CRC arithmetic moved with the copy time: **681 → 537 KiB/s**, the
735 µs copy back to **931 µs**, and the cost of checking CRC16 in software from
"512 bytes per ~6.8 ms = **73 KiB/s**" back to "~7.05 ms = **71 KiB/s**".

## §11.1 — the buffer, taken 2026-09-08 and reversed 2026-09-20

The section, verbatim:

> **This is the design.** Expose the card's block buffer as address space: reads become
> non-side-effecting, `TFM X+,Y+` walks it at 3 cycles/byte, and §4's hazard disappears from
> the read path entirely — no chunking, no masking, 681 KiB/s, and a simpler driver. §3.5 is
> the circuit, §4.5 is the hazard going away, §5 is the rate.
>
> The address space it needs is `machine.md` §5 item 1 option D's second megabyte —
> physical `A20`, one backplane pin, no parts — divided by §5 item 7 into sixteen 64 KB
> regions with a fixed-phase bus schedule in place of `/WAIT`. This card takes one region
> and uses 2 KB of it. **What it costs is six ICs** (§8), five of them address and data
> plumbing, and a second `GAL22V10`.
>
> The adoption narrative — this was long "the clean answer we cannot afford", and the
> argument for affording it is what helped close `machine.md` §5 item 1 — is archived in
> [history.md](history.md).

**Reversed 2026-09-20.** What it bought was real and is not disputed: 21 % of the read
rate and §4's hazard off the read path. What it cost was mispriced. This section said "six
ICs (§8), five of them address and data plumbing, and a second `GAL22V10`"; the count in
pins is **eight** packages — six discretes and **two more GALs**, because the region decode
is 16 pins on its own — so the card was 16 ICs rather than 14, twice the port card.
`storage/logic/census.ts` is the derivation. The 21 % is recoverable for nothing through
§11.6, which is a boundary condition in the CPU's own `TFM` state machine rather than
eight packages and a megabyte of physical address space.

§11.6's own pricing table went back to the form archived under §11.6 above: the firmware
option buys the **read** path again — 537 → 680 KiB/s — and not only the write path.

## §12 / §13 — build order and open items (2026-09-20)

- Step 3's exit was "§8's macrocell arithmetic confirmed, or the card becomes 15 ICs
  (§8.1)". The arithmetic is confirmed and the unit is macrocells per part: `sdbus` 8 of
  10, `sdeng` 10 of 10.
- Step 4 was "**Block read through the buffer** (§9.1: `FILL`, `DONE`, `TFM X+,Y+`)"; it
  is the chunked `TFM` again, and it catches §4's hazard again as well as the pipeline.
- Step 7 predicted "**681 KiB/s, host-bound**" with a ≥650 KiB/s exit bar; 537 KiB/s and
  ≥510.
- **Item 1** had been downgraded on 2026-09-08 to "two of §12 step 1's three questions
  still decide something … The source-re-read question no longer decides anything on this
  card." It decides 21 % again.
- **Item 6** — "⚠ The write path is still on the port, and that is an inconsistency" —
  **closed** by the read path joining it.
- **Item 12** — "⚠ Whether to take the `ATF1508AS`" — **closed** by the card shrinking
  instead.
