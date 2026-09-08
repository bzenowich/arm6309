# `net/` — Ethernet

**10BASE-T without a MAC or PHY chip: 12 ICs, two of them `ATF1508AS`, and 56 % of the
wire.**

Paths below are relative to this directory.

| | |
|---|---|
| [`docs/net.md`](docs/net.md) | the card — the port from `applenet`, the host-bandwidth arithmetic, the four-byte register window and the 64 KB buffer region, the macrocell budgets, the IC count |

## Where it comes from

`~/code/applenet` is a discrete 10BASE-T card for an Apple IIe — framing, Manchester
coding and CRC-32 all built rather than bought. Its current architecture (`arch-v3.md`)
puts the whole MAC on **one card, in two `ATF1508AS` PLCC-84 devices** — U1 the TX
domain, U2 the RX domain — plus the discrete analogue stages and the no-PLL clock
recovery block, for eight ICs in total.

**That partition is taken here unchanged**, and so is everything the wire decides: the
frame format, `Manchester = serial ⊕ BITCLK`, the `74HC86`/`'221`/`'123` recovery chain,
the reflected `0xEDB88320` CRC with its `0xDEBB20E3` residue check, and the golden ARP
frame that any testbench is written against. This card is a port, not a fork.

## The one number that shapes everything

**The 6309 can copy 681 KiB/s and 10BASE-T delivers 1221 KiB/s.**

At `E` = 2.0979 MHz a `TFM X+,Y` moves a byte every 1435 ns. The wire is **1.8× faster
than the host can drain it**, and every decision on this card is downstream of that:

- **The RX buffer is a sixteen-frame ring** — 45 ms of line-rate burst absorbed, and a
  driver that drains sixteen frames per interrupt is **2.7× faster** than one that drains
  one. `docs/net.md` §3.3.
- ⚠ **Minimum-size frames are interrupt-dispatch-bound**, at ~9,600 frames/s against
  14,881 arriving — 65 % of the wire, and that 9,600 is a rate at which the machine does
  nothing else. The ring cuts the dispatch share from 67 % of the CPU to 11.5 %. §3.4.

## ⚠ Rebuilt against the machine's new address spaces, 2026-09-08

This card was specified with its buffers behind a prefetched, auto-incrementing port in
four bytes of `$FF` space, because that was the only address space the machine had. **It
filled the `$FF` map doing it, and that is what forced `machine.md` §5 item 1.** The
machine's answer — a 128-byte window and a megabyte of physical space for card buffers,
for one backplane pin and no ICs — paid for a rebuild:

| | port version | now |
|---|---|---|
| ICs | 16 | **12** |
| Sustained RX | 537 KiB/s (44 % of the wire) | **681 KiB/s (56 %)** |
| Sustained TX | 373 KiB/s | **681 KiB/s** — fill and transmit finally overlap |
| RX ring | 4 frames | **16** |
| `TFM` hazard | chunk and mask, −21 % | **retired** — the host reads RAM, not a port |
| Small frames @ 400-cycle dispatch | 6,107/s, 29 % of the CPU in dispatch | **9,639/s, 11.5 %** |
| U2 fit | 118/128 | 116/128 — **unchanged, and that is the honest part** |

**The address space bought four ICs, 27 % of throughput, a hazard and a four-times deeper
ring. It did not buy macrocells.** `docs/net.md` §7.3 shows why: U2 shed the host-side
pointer and prefetch control and gained the sixteen-bank ring bookkeeping, and the two
nearly cancel. **The fit risk is still the card's largest** and the cut order is still
there.

## What it costs the machine

⚠ **Four bytes of `$FF` space and one 64 KB region.** `$FF5C`–`$FF5F` were the last four
bytes of the old 64-byte window; the window is `$FF00`–`$FF7F` now and 64 bytes are free.
The card's decode is **`A0`–`A6`, seven bits** — `A6` left the strobe with the widening.

⚠ **It is the third card to spend the no-CPLD house rule**, on a rule the root
`README.md` says is already spent on two. The argument is a machine-level one — six
slots, five claimed, and a 74xx MAC is 41 ICs across two of them; plus a software CRC-32
at 2.0979 MHz costs 22 ms per frame, eighteen times the frame's own transmission time.
**The rule should be restated or retired rather than quietly broken.** §12.

⚠ **And it gained one failure mode.** Two CPLDs now three-state onto one shared address
bus and one shared data bus, on a fixed `CLK25` schedule with U1 counting and U2 obeying
a `SLOT` wire. That is `docs/net.md` §4.3 and §7.1, and §15 step 5 exists to scope it.

## The part that was nearly the answer

A **`DP8390` (1986) plus a coax transceiver is four to six ICs**, in period, with no
house-rule exception at all. §13.6 argued it lost on I/O space — and **that argument
expired the next day** when the window widened.

**The card keeps the dual-`ATF1508AS` design anyway, for the better reason:** the
`DP8390` is long obsolete, out of production, and what stock exists is priced as a
collectable. A design cannot rest on a part you cannot buy. **Availability is the first
question about a part and the I/O budget is the second** — §13.6 records both rounds,
because the superseded one is what `machine.md` §5 item 1 cites.

## Status

**Specified, nothing built.** The deliverable is the document.

`docs/net.md` §15 gives the build order. **Step 1 is the discrete clock-recovery block on
perfboard, alone** — it is the highest-risk part of the design, it has never been on a
bench in either project, and it is the only block a JTAG reprogram cannot fix. **Step 5 is
new**: scope the shared buses before trusting anything above them.

**Fast-E (`machine.md` §1's ÷8 rate): not specified.** §4.3's bus schedule is derived at
÷12 and the two framer slots do not fit in the eight ticks ÷8 leaves. It is soluble —
interleave the framers on alternate cycles — and nobody has done the arithmetic.
