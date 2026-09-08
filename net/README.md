# `net/` — Ethernet

**10BASE-T without a MAC or PHY chip: 12 ICs, two of them `ATF1508AS`, and 56 % of the
wire.**

Paths below are relative to this directory.

| | |
|---|---|
| [`docs/net.md`](docs/net.md) | the card — the port from `applenet`, the host-bandwidth arithmetic, the four-byte register window and the 64 KB buffer region, the macrocell budgets, the IC count |
| [`docs/history.md`](docs/history.md) | archived history — the port-buffer design this replaced, the `DP8390`'s two rounds, the closed items |

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

## The buffers are memory, not a port

The card's 40 KB of SRAM sits in **one 64 KB physical region at `A20 = 1`**
(`machine.md` §5 item 7): the host reads a received frame with a plain `TFM` against
RAM — no side-effecting data port, no chunk-and-mask tax, and nothing for an
interrupted `TFM` to corrupt. The machine's longest-standing hardware caveat is
**retired here rather than mitigated** (`docs/net.md` §3.2), TX overlaps fill and
transmit for free, and the sixteen-frame ring costs a choice of SRAM part rather than
macrocells.

⚠ **The fit risk is the card's largest.** The address space bought four ICs, 27 % of
throughput, a hazard and a four-times deeper ring — **it did not buy macrocells**.
`docs/net.md` §7.3 shows why: U2 shed the host-side pointer and prefetch control and
gained the sixteen-bank ring bookkeeping, and the two nearly cancel, leaving U2 at
116/128 (91 %) with the cut order standing. U1 has no spare pin at 60 of 60 (§7.4).

## What it costs the machine

⚠ **Four bytes of `$FF` space and one 64 KB region.** The registers are `$FF5C`–`$FF5F`
in the `$FF00`–`$FF7F` window; the card's decode is **`A0`–`A6`, seven bits**.

**It was the third card to take a CPLD, and one of the three arguments that retired the
no-CPLD house rule on 2026-09-08** (root `README.md`). The case is machine-level rather
than a matter of taste — six slots, five claimed, and a 74xx MAC is 41 ICs across two of
them; plus a software CRC-32 at 2.0979 MHz costs 22 ms per frame, eighteen times the
frame's own transmission time, and a `GAL22V10`'s ten macrocells do not hold a 33-stage
LFSR. §12.

⚠ **And it has one failure mode of its own making.** Two CPLDs three-state onto one
shared address bus and one shared data bus, on a fixed `CLK25` schedule with U1 counting
and U2 obeying a `SLOT` wire. That is `docs/net.md` §4.3 and §7.1, and §15 step 5
exists to scope it.

## The part that was nearly the answer

A **`DP8390` (1986) plus a coax transceiver is four to six ICs**, in period, with no
house-rule exception at all. It lost twice: first on I/O space — an argument the
128-byte window later dissolved — and then, decisively, on availability. The `DP8390`
is long obsolete, out of production, and what stock exists is priced as a collectable;
a design cannot rest on a part you cannot buy. **Availability is the first question
about a part and the I/O budget is the second** — `docs/net.md` §13.6 records both
rounds, and that ordering is what the root `README.md` cites.

## Status

**Specified, nothing built.** The deliverable is the document.

`docs/net.md` §15 gives the build order. **Step 1 is the discrete clock-recovery block on
perfboard, alone** — it is the highest-risk part of the design, it has never been on a
bench in either project, and it is the only block a JTAG reprogram cannot fix. **Step 5
scopes the shared buses** before anything above them is trusted.

**Fast-E (`machine.md` §1's ÷8 rate): not specified.** §4.3's bus schedule is derived at
÷12 and the two framer slots do not fit in the eight ticks ÷8 leaves. It is soluble —
interleave the framers on alternate cycles — and nobody has done the arithmetic.
