# Ethernet for an arm6309 Machine

## 10BASE-T Without a MAC Chip, and the 56 % of the Wire the Host Can Actually Take

**Question this answers:** `~/code/applenet` is a discrete 10BASE-T card for an Apple IIe
— the framing, the Manchester coding and the CRC-32 all built rather than bought. Its
current architecture (`applenet/docs/arch-v3.md`, 2026-09-07) puts the whole MAC into two
`ATF1508AS` CPLDs and eight ICs. **What has to change for it to plug into this machine
instead?**

The answer is not the bus interface. It is that **this machine's host cannot keep up with
10 Mbit/s**, by a factor of about 2.3, and every interesting decision on the card follows
from that one number.

> **Status: specified, nothing built.** The deliverable is this document. Nothing in
> `~/code/applenet` is changed by it — that project keeps its own architecture and its
> own open items, and this card is a port, not a fork of its planning.

Paths in this document are repository-root-relative, per the convention at the bottom of
the root [`README.md`](../../README.md). References of the form `arch-v3.md §x` are to
`~/code/applenet/docs/`, which is **not** part of this repository.

---

## 0. Summary — the verdict in one table

| | |
|---|---|
| **What it is** | 10BASE-T, full duplex, switched links only. No CSMA/CD, no MAC chip, no PHY chip |
| **Silicon** | **12 ICs**, two of them `ATF1508AS-15JC84`, plus a 20 MHz can and a MagJack — §9 |
| **Address space** | **four bytes at `$FF5C`–`$FF5F` for registers, and one 64 KB physical region at `A20 = 1` for the buffers** — §4, §5.1 |
| **Interrupt** | `/IRQ`, as a **fifth** source. §6 |
| **RX buffering** | 62256, **16 banks of 2 KB — a sixteen-frame ring**, addressed by the host as memory. §3.3 |
| **TX buffering** | 6264, **4 banks of 2 KB**, likewise |
| **Hardware CRC-32** | **both directions**, bit-serial, `0xEDB88320` reflected. Not optional here — §13.4 |
| **Sustained RX** | **681 KiB/s = 56 % of the wire** — §3.1 |
| **Sustained TX** | **681 KiB/s**, because fill and transmit now overlap — §3.1 |
| **⚠ Minimum-size frames** | **dispatch-bound at ~9,600 frames/s against 14,881 arriving** — §3.4 |
| **~~The `TFM` hazard~~** | **retired.** The host reads SRAM, not a port that pops a byte — §3.2 |
| **⚠ The fit risk** | **U2 at 91 % of an `ATF1508AS` and U1 at 88 %.** Unchanged in kind; the buffer decision bought ICs and throughput, not macrocells — §7.3 |
| **House rule** | this was the **third** card to take a CPLD, and one of the three reasons the no-CPLD rule was **retired on 2026-09-08** — §12 |
| **Power** | **~430–530 mA**, of which ~250 mA is the two CPLDs. §10 |
| Period | 10BASE-T is **IEEE 802.3i-1990** — one year past the machine's line. §12 |

> **⚠ Revised 2026-09-08, and the revision is structural.** This document originally
> specified the buffers behind a prefetched, auto-incrementing `NDATA` port in the four
> bytes of `$FF` space, because that was the only address space the machine had.
> `machine.md` §5 item 1 option D and §5 item 7 gave the machine a megabyte for exactly
> this, and the card was re-specified against it: **four ICs and the `TFM` hazard came
> off, throughput rose 27 %, and the ring went from four frames to sixteen.**
> Superseded passages are marked in place rather than deleted.
## 1. Sources and confidence

| | |
|---|---|
| `~/code/applenet/docs/plan.md` | the v1 reference: §2 wire format, §4–§5.1 analogue and recovery, §6.3 Manchester/BITCLK phase, Appendix A CRC taps, Appendix B golden frame. **All carried here unchanged** |
| `~/code/applenet/docs/arch-v3.md` | the two-CPLD architecture. Carried with four changes, §2.2 |
| `~/code/applenet/docs/review.md` | 40 findings against v1. Everything marked FIXED there is assumed fixed; the four still OPEN are carried into §16 |
| [`docs/machine.md`](../../docs/machine.md) | the bus, the `$FF` map, the interrupt ownership, the clock tree, the power table |
| [`storage/docs/sdcard.md`](../../storage/docs/sdcard.md) | §4.2's argument that a `TFM` against RAM is idempotent is what §3.2 rests on, and §11.1 is the same decision this card took. **Both cards moved their buffers into `A20 = 1` on 2026-09-08** |
| [`hardware/README.md`](../../hardware/README.md) | the 72-pin slot, and the six-slot count that decides §12 |

**Not measured.** Every timing figure here is arithmetic from datasheet numbers and from
`machine.md` §1's `E` rate. Nothing on this card has been on a bench, and the one block
that most needs to be — the discrete clock recovery — has not been on a bench in
`~/code/applenet` either (`arch-v3.md` open item 2.1, `m1-notes.md` §8).

---

## 2. What this card is, and what it inherits

### 2.1 What carries over from applenet unchanged

These are not re-derived here, and this document does not get to change them:

- **The wire format.** Preamble 7×`0x55`, SFD `0xD5`, DST..payload, FCS; 64-byte minimum,
  1518-byte maximum; end of frame is "no edge for ~2 µs". `plan.md` §2.
- **Manchester encode = `serial ⊕ BITCLK`**, with `BITCLK` high during the first half-bit
  and the serializer shifting on its rising edge. `plan.md` §6.3, `review.md` §1.3.
- **Clock and data recovery with no PLL** — XOR edge detect, a ~75 ns *non-retriggerable*
  monostable for `rec_clk`, a ~2 µs retriggerable one for `NIDLE`. `plan.md` §5.1,
  `m1-notes.md` §6. **This is still the highest-risk block on the board**, and it is the
  only part of the card a reprogram cannot fix.
- **CRC-32, reflected `0xEDB88320`, shift right, feedback from Q0**, with the
  `0xDEBB20E3` residue check sampled **at byte boundaries** and not at raw EOF.
  `plan.md` Appendix A, §5.4, `review.md` §3.4.
- **The golden frame.** `plan.md` Appendix B — an ARP request with FCS `0x322A8F3D`,
  wire bytes `3d 8f 2a 32`. Any testbench written for this card is written against it.
- **In-frame lockout on the SFD detect**, because `0xD5` occurs constantly inside
  payloads. `plan.md` §5.2, `review.md` §5.2.
- **No TP_IDL generation**, and no dribble bits: the driver enable drops at the last FCS
  bit. `plan.md` §6.4.
- **NLP every 16 ms ± 8 ms**, positive-going, driver gated on only around the pulse.
  `plan.md` §7.

### 2.2 What the 6309 machine changes

Four things, and the last one is the whole shape of the card.

| | applenet | here | why |
|---|---|---|---|
| **Bus** | Apple IIe 50-pin, Φ0, `/DEVSEL`, 16 offsets at `$C0nX` | arm6309 72-pin, `E`/`Q`, `/IOSEL`, **4 offsets** at `$FF5C` **plus a 64 KB physical region** | `machine.md` §2, §3, §5 item 7 |
| **Driver ROM** | 256 bytes at `$Cn00`, plus `/IOSEL` decode | **none** | the CPU module serves an 8 KB shadow ROM from its own flash (`machine.md` §7.2); this machine has no expansion-ROM window and needs none |
| **Arbitration clock** | none — `arch-v3.md` notes "the only clock available is a bus strobe that stops when the slot is idle" | **`CLK25`, 25.175 MHz, free-running, on the backplane** | `machine.md` §2. It is what makes §4.3's fixed-phase schedule possible at all |
| **⚠ Buffers** | ping-pong behind a host port, "recommended but not required for first silicon" | **a sixteen-frame ring the host addresses as memory** | §3.3 — and `arch-v3.md`'s ping-pong does not work as written, §3.3.1 |

**The last row is the port's one real divergence.** `applenet` has an Apple II slot and no
physical address space to spare, so every byte of a frame crosses the bus through a port.
This machine, since `machine.md` §5 item 7, hands a card **64 KB of ordinary memory** —
and a buffer that is memory rather than a port is a different card: no pointer, no
prefetch, no auto-increment, and nothing for an interrupted `TFM` to corrupt.
## 3. ⚠ The host is 56 % of the wire, and that is the card

### 3.1 The three rates

The card's buffers are memory in the machine's physical map (§4.2), so the host drains a
frame with `TFM X+,Y` — RAM to RAM, both pointers incrementing, three cycles a byte. The
figure is `machine.md`'s established one: `sdcard.md` §4.4 measures a 512-byte unchunked
`TFM` at **3.01 cycles/byte**.

| | | |
|---|---|---|
| `E`, specified (`machine.md` §1.1) | 2.0979 MHz | 476.7 ns/cycle |
| `TFM` at 3.01 cycles/byte | | **1435 ns/byte** |
| **Host** | 696,977 B/s | **681 KiB/s** |
| **10BASE-T** | **1,250,000 B/s** | **1221 KiB/s** |
| **Ratio** | | **56 %** |

> ⚠ **This read 44 % until 2026-09-08**, because the port version paid a further 21 % for
> the chunk-and-mask that §3.2 no longer needs. The wire got no slower; the tax came off.

**The wire is still 1.8× faster than the host can drain it**, and no hardware on this card
changes that — the bottleneck is one `TFM` instruction against a 2.0979 MHz `E`. What §3.3
does with buffering buys *time*, not throughput.

| | Rate | Bound by |
|---|---|---|
| RX, port ceiling | 681 KiB/s | the `TFM` loop |
| **RX, sustained, large frames** | **681 KiB/s** while the ring holds; **0 during a ring-full drop** | the host, then the ring |
| **RX, sustained, minimum frames** | **~600 KiB/s equivalent, ~9,600 frames/s** | NitrOS-9's interrupt dispatch — §3.4 |
| **TX, sustained** | **681 KiB/s** | the host filling the buffer |

> ⚠ **TX read 373 KiB/s until 2026-09-08.** The port version was single-buffered — the
> host filled through the same pointer the transmitter read with, so a maximum-size frame
> cost 2178 µs of fill *then* 1221 µs of transmit. With the buffer memory-mapped there is
> no shared pointer: the host writes bank B while bank A transmits, TX is four-deep for
> the price of the SRAM that was already there, and **the 31 % that overlap used to cost
> is simply gone.** This was §13.3's "best-value addition on the card" and it turned out
> to be free.

### 3.2 ~~⚠ The `TFM` hazard, again~~ The `TFM` hazard, and how this card stopped having one

`sdcard.md` §4 is the machine's longest-standing hardware caveat:

> **`TFM` is the 6309's only interruptible instruction, and on resume it re-reads the
> source address.** Against a port whose read has a side effect, the re-read returns the
> wrong byte, everything after it shifts by one, and nothing detects it.

**This document originally inherited that exactly.** Its `NDATA` port returned a
prefetched byte *and* advanced the pointer, so an interrupted drain shifted the frame by
one byte from that point — past an FCS that hardware had already checked and passed.
The specified fix was `sdcard.md` §4.4's chunk-and-mask: 32-byte chunks, 3.81 cycles/byte,
**21 % of the card's throughput**, and 49 µs of added interrupt latency.

> **⚠ Retired 2026-09-08, and not by mitigating it.** `sdcard.md` §4.2's own argument is
> that the mirror-image `TFM X+,Y` against RAM **is** safe, because re-reading a memory
> location returns the same byte. The ring is memory now (§4.2). The drain is
>
> ```
>         ldx   #bank            ; the card's RX bank, mapped through the MMU
>         ldy   #buffer
>         ldw   len
>         tfm   x+,y+            ; no masking, no chunking, no 21 %
> ```
>
> and there is nothing in it for an interrupt to break. **The 21 % is what §3.1's 44 % →
> 56 % is made of.**

**What this does not do is let the machine off `TFM`.** `machine.md` §6 still lists
"settle `TFM`'s interrupt/resume behaviour from silicon" as a `cpu`-owned item, because
`sdcard.md`'s `SDDATA` is still a side-effecting port and this card still has four bytes
of registers in `$FF` space. What changed is that **no bulk transfer in this machine now
runs over a side-effecting port**, so the answer decides a correctness question about
single-byte accesses rather than about every block and every frame.

### 3.3 What buffering buys, and what it does not

A maximum-size frame occupies the wire for 1220.8 µs and the inter-frame gap adds 9.6 µs,
so back-to-back maximum frames arrive every **1230 µs**. The host drains one in
**2178 µs**. Under sustained line-rate load the ring fills at 3.54 × 10⁻⁴ banks/µs:

| RX banks | Line-rate burst absorbed before the first drop | |
|---|---|---|
| 1 (single buffer) | **0 µs** — every frame arriving during a drain is lost | |
| 2 (ping-pong) | 5.7 ms | |
| 4 | 11.3 ms | *what the port version could afford* |
| **16 (specified)** | **45.2 ms** | *what 32 KB of SRAM costs* |

**Sixteen is not a judgement call any more, and that is the point.** In the port version
each bank cost macrocells — a wider write-bank counter, a wider compare, a deeper
read-side mux — so four was a budget decision argued against `machine.md` §4's 0.8–1.3 ms
PS/2 interrupt-mask window. With the ring addressed as memory the depth is **a choice of
SRAM part**: a `62256` is the same package, the same price and the same pin count as the
`6264` it replaces, and 32 KB is 16 banks. The only cost is four more bits of write-bank
counter.

45 ms covers every interrupt-mask window in the machine with two orders of magnitude to
spare, and it covers a full TCP window burst from a peer that has no idea it is talking to
a 2 MHz machine.

**What it still does not buy is throughput.** Under sustained overload the ring is full in
45 ms and after that the card drops one frame in 1.8, forever. That is what a 2.0979 MHz
host on a 10 Mbit wire looks like, and TCP's congestion control is the mechanism that is
supposed to notice.

#### 3.3.1 ⚠ And `arch-v3.md`'s ping-pong does not work as written

`arch-v3.md` lists ping-pong as "affordable again — one bank bit per device, driving SRAM
A12, ~2 macrocells", while its "Stays cut" list keeps **one pointer per device serving
both framer and host**. Those two sentences are not compatible. A bank bit puts the host
and the framer in different 2 KB banks; it does nothing about the fact that they are at
different *offsets* within them, and one counter cannot hold two offsets.

That was the finding this card was built around, and it is worth reporting back to
`applenet` whatever this machine does — **on an Apple II it has no cheap answer**, because
that machine has no spare physical address space to map a buffer into. Here it dissolved:
the host's offset comes from the bus and the framer keeps its own pointer, so there is
nothing to share.

### 3.4 ⚠ Minimum-size frames are dispatch-bound, and the numbers are better but not good

A 64-byte frame plus preamble occupies 57.6 µs; with the gap, one arrives every 67.2 µs —
**14,881 frames/s**. The host's cost per frame is the drain (64 B ÷ 681 KiB/s = 91.9 µs)
plus one NitrOS-9 interrupt dispatch, and `machine.md` §5 item 2 records that **nobody has
measured what a dispatch costs** — the range in use across the repository is 100 to 400
cycles, i.e. 47.7 to 190.7 µs.

| | 1 frame per dispatch | **16 frames per dispatch (the ring)** |
|---|---|---|
| 100-cycle dispatch | 7,169 frames/s | **10,548 frames/s** |
| **400-cycle dispatch** | **3,540 frames/s** | **9,639 frames/s** |

- **The ring is worth 2.7× at 400 cycles**, because the driver drains every waiting frame
  inside one dispatch and sixteen is deep enough that it usually can. This is the ring's
  second job and it is the more valuable one.
- **The card reaches 65 % of the small-frame wire rate**, against 41 % for the port
  version. Small-frame floods are still the shape of traffic this machine loses.
- **⚠ Every figure in that table is a rate at which the machine does nothing else.** They
  are derived by filling the whole CPU with drain plus dispatch. What the card controls is
  the *dispatch share*: at 400 cycles and sixteen frames per dispatch it is **11.5 % of
  the machine**, against **67 % for one frame at a time**. The drain itself is
  irreducible.

  The card still has no interrupt-coalescing threshold and still cannot get one — that
  would be a fifth register in a four-byte window (§5.1). The defence is the ring plus a
  driver that drains to empty before it returns, and the honest statement is that a busy
  LAN can saturate this machine and nothing on the card will stop it.

  > **`ps2.md` §14 item 3's unmeasured dispatch cost decides four things**: serial's baud
  > ceiling, whether PS/2's FIFO comes back, `machine.md` §4.1's margins, and how much of
  > this card is usable. It is the highest-value measurement in the machine and it costs
  > one afternoon.
## 4. The bus interface

The card answers at **two** addresses, and they are different kinds of thing.

### 4.1 The registers — four bytes of `$FF` space

`machine.md` §2 settles the mechanism: **`/IOSEL` is the `$FF00`–`$FF7F` window strobe,
common to every slot**, and a card completes its own decode from `A0`–`A6` against a
jumpered base. **Seven bits, not six** — `A6` left the strobe with the 2026-09-08
widening, and a six-bit comparator would answer at `$FF5C` *and* `$FF1C`.

The card takes `A0`–`A6`, `D0`–`D7`, `R/W`, `E`, `CLK25`, `/RESET`, `/IOSEL` and `/IRQ`
for this, and it holds **no data path** here — §5 is four registers of control and status
and nothing else.

### 4.2 The buffers — one 64 KB physical region

`machine.md` §5 item 7: `A20 = 1` is sixteen regions of 64 KB, selected by physical
`A19`–`A16` against a four-position jumper, **qualified by `/IOPAGE` high**. This card
takes one region and splits it once:

| | | |
|---|---|---|
| `A15 = 0` | **32 KB, `62256`** | the RX ring — 16 banks of 2 KB |
| `A15 = 1` | **8 KB, `6264`** | TX — 4 banks of 2 KB |

The host reaches both through the MMU like any other memory: point an 8 KB block at the
region and a bank is 2 KB inside it. `A14`–`A0` come off the backplane through two
`74HC244`s onto a **shared card address bus**, and `D7`–`D0` through one `74HCT245` onto a
**shared card data bus**. Both SRAMs and both CPLDs hang on those two buses; who drives
them when is §4.3.

**Nothing here has a side effect.** No auto-increment, no read trigger, no prefetch — that
is the whole reason the buffers moved (§3.2), and any future revision that puts a
side-effecting register in this region is undoing it.

### 4.3 The schedule — three masters, no handshake

`hardware/gal/README.md` gives the house cycle: within one bus cycle the order is
**E-fall, Q-rise, E-rise, Q-fall**; the address is valid at E-fall + `t_AD` (110 ns) and
write data 110 ns after Q-rise. At `E` = 2.0979 MHz one cycle is 476.7 ns and `CLK25` is
39.7 ns, so **there are twelve ticks in a bus cycle** and the address is valid from tick 3.

Three masters want the shared buses. `machine.md` §5 item 7's answer is a fixed schedule
rather than an arbiter, and this is that schedule:

| ticks | | needs |
|---|---|---|
| **0–1** | **U1** — the TX framer reads its next byte | 1 byte per 800 ns; gets one per 476.7 ns |
| **2–3** | **U2** — the RX framer writes its byte | the same |
| 4–6 | idle | |
| **7–11** | **the host**, if its decode matches | address valid since tick 3; SRAM `/OE` asserted at tick 7, data valid at tick 9 (357 ns) and **held to the end of the cycle** |

**The host's data is valid 357 ns into a cycle that needs it by ~437 ns** — 80 ns of
margin, with no register in the path and no prefetch. That is the timing the port version
needed a `74HC574` to make (`§4.2` as it stood before this revision), and it comes free
once the address arrives on the bus instead of out of a counter.

Both framers hold their byte in a register across the deferral — U1's parallel-load
serializer and U2's deserializer output latch, both of which exist for other reasons — so
a deferral of up to one bus cycle costs nothing.

> ⚠ **A stretched cycle breaks this schedule, and `/WAIT` became real on 2026-09-08.**
> `machine.md` §5 item 8 gave the divider a hold term, so **another card can now freeze
> `E` mid-cycle** — the video card's span writer is the one that does it. Two things
> follow and neither is solved here:
>
> - **The host's window must be "tick 7 until `E` falls", not "ticks 7–11".** A stretch
>   extends the hold; the SRAM's `/OE` stays asserted and the data stays valid, which is
>   harmless. **The phase counter must saturate rather than wrap**, or the host's window
>   moves under it.
> - **⚠ The framers starve.** They get slots at ticks 0–3 of a cycle that has stopped
>   advancing. A stretch longer than **~800 ns** — one byte time — overruns the RX
>   deserializer's output register and loses a byte. **A lost byte is a failed FCS, so it
>   is a dropped frame and not silent corruption**, which is the one piece of luck here.
>   **Nobody has said how long `SPANBUSY` lasts** (`graphics.md`), so nobody can say
>   whether this ever happens. §16 item 5.
>
> ⚠ **The schedule is derived at ÷12 and does not carry to fast-E unchanged.**
> `machine.md` §1.1's experimental ÷8 gives eight ticks of 39.7 ns in a 317.8 ns cycle,
> and `t_AD` does not shrink with it — the address is valid from tick 2.8, so the host's
> window is ticks 3–7 and the two framer slots have to fit in 0–2. **They do not.**
> Fast-E needs the framers interleaved on alternate cycles, which works (each then gets a
> byte per 636 ns against the 800 ns it needs) and **is not specified here.** The card is
> a ÷12 card until someone does that arithmetic.

### 4.4 Write timing

Write data is valid 110 ns after Q-rise and held past E-fall, so **every `$FF` register
strobe on this card is taken at E-fall**, which is the convention
[`hardware/gal/mmu.pld`](../../hardware/gal/mmu.pld) already uses for the motherboard's
`'574`. Writes into the buffer region are ordinary SRAM writes in the tick 7–11 window,
with `/WE` timed from `E` and `R/W`.

### 4.5 ~~Phantom reads — checked, and clean~~ Phantom reads cannot matter here

A read-triggered port dies quietly on a 6809-family bus if dead cycles land on it, and
`sdcard.md` §3.4 establishes the answer for this machine: **the core drives `$FFFF` on
every dead cycle**, outside `$FF00`–`$FF7F`.

**This card no longer needs that guarantee.** Nothing it exposes has a side effect on
read: the registers in §5 are status, and the buffers are memory. A dead cycle landing
anywhere on this card reads a byte and changes nothing.

That is worth stating because it *was* load-bearing one revision ago, and because it is
the second thing (after §3.2) that a memory-mapped buffer retires rather than mitigates.
## 5. Register map, and the memory map

### 5.1 Placement

**Four bytes at `$FF5C`–`$FF5F`, and one 64 KB region at `A20 = 1`.**

| Window | Size | Owner |
|---|---|---|
| `$FF00`–`$FF3F` | 64 | *free* |
| `$FF40`–`$FF4F` | 16 | audio |
| `$FF50`–`$FF53` | 4 | PS/2 |
| `$FF54`–`$FF57` | 4 | serial |
| `$FF58`–`$FF5B` | 4 | storage |
| **`$FF5C`–`$FF5F`** | **4** | **net — this document** |
| `$FF60`–`$FF7F` | 32 | video |

> ⚠ **This took the machine's last four bytes on 2026-09-07, and that is what closed
> `machine.md` §5 item 1 the next day.** For one day the geographic decode was 64 of 64
> with nothing free. The window is `$FF00`–`$FF7F` now — 128 bytes, 64 of them free — and
> `/IOSEL` got *cheaper* in the process. **The card's base does not move; its decode
> becomes `A0`–`A6`** (§4.1).
>
> The same decision gave the machine a megabyte of physical space (`machine.md` §5 item 1
> option D and item 7), and **that is where this card's 40 KB of SRAM went.** §13.6
> records the period alternative and why it lost — and why the map was never the
> load-bearing half of that argument.

**Four bytes is now comfortable rather than tight**, because the data path left. The port
version needed a `DATA` port, a pointer low byte, a pointer high byte, a direction-select
bit and a command register in the same four addresses, split by `R/W` to get eight
registers out of four. What is left is control, status and commands.

**What still does not fit is anything extra**: no interrupt-coalescing threshold (§3.4),
no MAC-address filter, no second status page.

The `$FF` base is a jumper and so is the region base (`machine.md` §5 item 7). Nothing
prevents two cards being jumpered alike in either space and nothing detects it; that is
the machine's known cost for window-strobe `/IOSEL` and this card inherits it twice.

### 5.2 The four registers

Read and write sides are decoded separately by `R/W` — eight registers in four addresses.

| Off | Write | Read |
|---|---|---|
| `+$0` | **`NCMD`** — strobes, below | **`NTXST`** — §5.3 |
| `+$1` | **`NTXPL`** — `TXPTR[7:0]`; **the write performs the load** | **`NRXST`** — §5.3 |
| `+$2` | **`NTXPH`** — b4:0 = `TXPTR[12:8]` | **`NRXHD`** — b3:0 = the ring bank holding the oldest undrained frame |
| `+$3` | **`NCTRL`** — b0 `RX_EN`, b1 `RX_IE`, b2 `TX_IE` | **`NRXCNT`** — b4:0 = frames waiting, 0–16 |

**`NCMD` bits are strobes**, acted on once and self-clearing:

| bit | name | effect |
|---|---|---|
| 0 | `TX_GO` | transmit from `TXPTR` to the end of its 2 KB bank. Also acks `TX_DONE` |
| 1 | `RX_ADV` | release the head bank, advance `NRXHD`, decrement `NRXCNT` |
| 2 | `ACK_TX` | clear `TX_DONE` |
| 3 | `ACK_RX` | clear `RX_OVERRUN` |
| 7 | `RESET` | reset both framers. Does not clear `NCTRL` |

**Write `NTXPH` before `NTXPL`.** `NTXPH` holds the high bits; `NTXPL` is the write that
performs the load. The other order loads the previous high bits. This is `plan.md`
§9.2.1's rule with the register names changed, and it is the only ordering constraint left
on the card.

> ⚠ **Four registers were deleted in the 2026-09-08 revision and it is worth naming them,
> because each one was a workaround for the address space the card did not have.**
> `NDATA` (the prefetched, auto-incrementing data port — §3.2's hazard), `NPTRL`/`NPTRH`
> for the *RX* side, and the `SEL` bit that said which direction the data port and pointer
> referred to. The host now addresses the frame directly. `NTXPL`/`NTXPH` survive because
> the transmitter still needs to be told where to start.

### 5.3 `NTXST` and `NRXST`

**Neither read has a side effect.** That is a requirement, not a convenience —
`machine.md` §4.1 fixes the shared-`/IRQ` polling order around exactly this property, and
the 6551 is last in that order because it lacks it.

**`NTXST`** (`+$0`, R):

| bit | name | meaning |
|---|---|---|
| 0 | `TX_DONE` | the last transmission finished and the line returned to idle (latched) |
| 1 | `TX_BUSY` | the transmitter is running (live) |
| 2 | `TX_IE` | read-back of the enable |
| 3 | `LINK_UP` | activity seen within the link window (live) |
| 7:4 | — | read 0, tied, never floating |

**`NRXST`** (`+$1`, R):

| bit | name | meaning |
|---|---|---|
| 0 | `RX_READY` | at least one complete frame waits in the ring — `NRXCNT` ≠ 0 |
| 1 | `RX_OVERRUN` | the ring was full and a frame was dropped (latched) |
| 2 | `RX_EN` | read-back |
| 3 | `RX_IE` | read-back |
| 4 | `LINK_UP` | live |
| 5 | `IN_FRAME` | the framer is mid-frame (live) |
| 6 | `RING_FULL` | all sixteen banks hold undrained frames (live) |
| 7 | **`CARD_IRQ`** | **this card is asserting `/IRQ`** — the OR of both devices' enabled sources |

`CARD_IRQ` is what lets the shared-`/IRQ` handler answer "was it us?" in one read. It
costs one wire from U1 to U2 (§7.1) and it is worth it: §3.4 shows dispatches are the
scarce thing.

`NRXHD` and `NRXCNT` together are the drain loop's whole state — where the oldest frame
is and how many follow it. Under §3.4's arithmetic that loop is the card's most important
piece of software.

### 5.4 Reset state

`/RESET` (backplane, `machine.md` §2.1) and `NCMD` bit 7 both force:

| | |
|---|---|
| `RX_EN` | **0** — the receiver is disarmed until the driver arms it |
| `TX_IE`, `RX_IE` | 0 |
| ring | empty; `NRXHD` = 0, `NRXCNT` = 0, the framer's write bank = 0 |
| `TX_BUSY`, `TX_DONE`, `RX_OVERRUN` | 0 |
| `/IRQ` | released |
| line driver | disabled; NLP generation **runs** |
| **the SRAMs** | **untouched.** Reset clears the bookkeeping, not the banks — a frame that survives a reset is garbage the driver must not be handed, which is why `NRXCNT` is what gates it |

`/RESET` is the CPLDs' **global clear on the dedicated GCLR pin** (§7.5), so it costs no
product term and it is genuinely asynchronous — which `arch-v3.md` notes the GAL-based v2
had to contort itself to preserve.

NLP generation runs from reset because a link that is not up when the driver loads is a
link that takes 100 ms to come up when it does.

### 5.5 The bank header, and what a bank looks like

Each 2 KB bank holds **two header bytes at offsets 0 and 1, then the frame from offset
2**. 1518 + 2 = 1520 of 2048.

| offset | contents |
|---|---|
| 0 | `RXLEN[7:0]` |
| 1 | b2:0 `RXLEN[10:8]`, b7 `CRC_OK`, b6:3 = 0 |
| 2… | DST, SRC, type, payload, FCS |

`RXLEN` is the DST..FCS byte count as written, so it includes the four FCS bytes exactly
as `plan.md` §9.2.1's `RXLEN` did. `CRC_OK` is the `0xDEBB20E3` residue match sampled at
the last byte boundary (`plan.md` §5.4).

**The framer writes the header at end of frame**, not at the start: the pointer is preset
to 2 at `frame_start`, and when `NIDLE` falls the framer loads 0, writes, increments,
writes, and then commits the bank. Both writes land inside the 9.6 µs inter-frame gap,
which is 240 `CLK25` ticks against the ~8 needed.

**This is what deletes the per-bank length latches.** `review.md` §6.5 found that
applenet's single-copy `RXLEN`/`CRC_OK` could not serve two banks and specified a latch
pair per bank muxed by `RX_BANK`. **Sixteen banks would be sixteen pairs — 208
macrocells**, which is more than either device has in total. Putting the length in the
buffer costs three macrocells of state machine and two bytes of a RAM that is 74 % used.

> **This is the trick that makes a sixteen-deep ring possible at all**, and it only works
> because the host can address the header. In the port version the host had to *stream*
> the header out through `NDATA` before the frame; here it reads two bytes wherever it
> likes, twice if it wants to.

**The TX side has no header.** The host writes the frame end-aligned in a 2 KB bank and
points `TXPTR` at its first byte; terminal count at the end of the bank means "SRAM data
exhausted → pad, then FCS". That is `plan.md` §6's end-aligned trick, unchanged, and it is
why there is no `TXLEN` register.

## 6. Interrupts

**`/IRQ`, open-drain, as a fifth source.** `machine.md` §4: `/FIRQ` belongs to audio
alone and is exclusive by design; `/IRQ` already carries video's VBL and raster compare,
PS/2 and serial, and its handler already polls. `/NMI` remains wrong for the reason it
was wrong for PS/2 — it would pre-empt the replayer tick that `/FIRQ`'s exclusivity
exists to protect.

Both CPLDs drive `/IRQ` through the **`ATF1508AS`'s programmable open-collector output
option**, so there is no external open-drain gate and no pull-down network. This is the
same feature `audio.md` §8.1 spends, and the pull-up is already on the motherboard
(`machine.md` §2.1, 3.3 kΩ).

Three maskable sources:

| source | enable | cleared by |
|---|---|---|
| `RX_READY` — the ring is not empty (`NRXCNT` ≠ 0) | `RX_IE` | draining to empty with `RX_ADV` |
| `RX_OVERRUN` | `RX_IE` | `ACK_RX` |
| `TX_DONE` | `TX_IE` | `ACK_TX`, or the next `TX_GO` |

**Proposed polling order: video `VSTAT` → net `NRXST` → PS/2 `IOSTAT` → serial `STATUS`.**

`machine.md` §4.1's order has exactly one hard constraint — **serial last**, because
reading the 6551's `STATUS` clears the interrupt and returns the error bits in the same
read. Net goes second because its status read has no side effects at all, and because
under load it is the most frequent source in the machine after (and sometimes ahead of)
VBL.

> ⚠ **This card makes `machine.md` §4.1's order correctness-driven rather than
> frequency-driven, and that is worth saying out loud.** At §3.4's rates net can raise
> 9,600 interrupts/s and serial 1,920, against VBL's 50–70. The frequency ordering is
> now *serial, net, video, PS/2* and the specified order is *video, net, PS/2, serial* —
> they are nearly reversed. The specified order is still right, because the 6551's
> destructive read is a correctness matter and polling cost is not. But nobody had to
> choose between them before.

**Ack-window race.** `review.md` §7.2's finding carries: an event landing during the ack
window can be lost. The driver rule is the same — **re-read `NRXST` after acking** and
handle anything still or newly set before `RTI`. §3.4's drain-to-empty loop does this
naturally.

---

## 7. The two CPLDs

### 7.1 Partition — one device per realtime domain

`arch-v3.md`'s seam, taken unchanged and for its reasons: 10BASE-T is full duplex on
separate pairs, TX and RX are independent realtime domains, and they cannot share a CRC
register (`review.md` §3.1 found that as a blocker).

- **U1 — TX domain.** The 20 MHz oscillator, `BITCLK`, the serializer, the TX CRC LFSR,
  FCS append, NLP gating, the TX buffer, the TX registers — **and the region decode and
  the §4.3 phase schedule for the whole card**, because one of them has to own it.
- **U2 — RX domain.** `rec_clk`/`rec_data`/`NIDLE`/`LINK_UP` from the discrete recovery
  block, the deserializer, SFD detect and in-frame lockout, the RX CRC LFSR and residue
  compare, the ring bookkeeping, and the RX registers.

**Four signals cross between them:**

| | direction | why |
|---|---|---|
| `LINK_UP` | U2 → U1 | U1 gates transmission on it |
| `TXIRQ` | U1 → U2 | so `NRXST` b7 can report card-wide `/IRQ` in one read — §5.3 |
| **`SLOT`** | **U1 → U2** | **U2's two-tick window in the §4.3 schedule.** U1 owns the phase counter; U2 is told when to drive the shared buses rather than deriving it, so the two cannot disagree about a bus they both drive |
| `CARRIER` | U2 → U1 | optional, for deferral; unused on a switched link |

> ⚠ **`SLOT` is new in the 2026-09-08 revision and it is the one genuinely new failure
> mode.** Two devices three-stating onto one address bus and one data bus is a contention
> hazard that the private-SRAM-per-device arrangement did not have. It is answered by
> making the schedule single-sourced — U1 counts, U2 obeys — rather than by two counters
> that are supposed to agree. **Both devices' output enables must also be
> break-before-make**, which on an `ATF1508AS` is a product term on the enable and not a
> macrocell.

### 7.2 U1 — TX, the host port and the schedule

| block | MC |
|---|---|
| TX read pointer, 13-bit loadable → shared address bus A0–A12 | 13 |
| serializer 8, bit counter mod-8 3, `BITCLK` ÷2 1 | 12 |
| TX control FFs (`TX_ACTIVE`, `GO_PEND`, `TX_DONE`, `TX_IE`, byte-clock edge, `last_byte`) | 6 |
| **TX CRC-32 LFSR + `fb`** | **33** |
| FCS shift-out control (`TX_FCS_MODE`, serializer source FSM) | 4 |
| NLP: ÷2 of the `'4020`'s 128 Hz, plus a 100 ns pulse from the 20 MHz domain | 3 |
| `$FF` TX port: decode 5, stored bits (`TXPTR12:8`, `TX_IE`) 6, read mux 8 | 19 |
| **region decode** (`/IOPAGE`, `A20`, `A19`–`A16` vs jumper, `A15`) **and both SRAMs' `/CE`, `/OE`, `/WE`** | 6 |
| **the §4.3 phase counter, the host window and `SLOT`** | 6 |
| shared data-bus driver | 8 |
| Manchester XOR, `drv_en`, `/IRQ`, `TXIRQ` | 4 |
| **total** | **114 / 128 (89 %)** |

Three of `arch-v3.md`'s U1 blocks are gone, and its own cut order is why:

- **The NLP divider (−13).** A `74HC4020` off `E` gives 128 Hz; U1 divides by two for a
  15.6 ms NLP period, inside the 16 ± 8 ms window. `arch-v3.md`'s cut 1 verbatim — one IC
  for thirteen macrocells of completely uncritical logic.
- **Pad-to-60 (−6).** Software pads. `arch-v3.md`'s cut 2, and cheaper here: the host
  builds the frame in the card's own SRAM, TX is not the starved direction (§3.1), and a
  `memset` of at most 18 bytes is noise against a 2178 µs fill. **The cost is that
  software can now violate the 64-byte minimum**, and the driver is the only writer.
- **The host-side TX data path (−16).** The host writes the TX buffer directly through the
  `'245` and the shared bus; U1 drives neither the slot data bus for frame bytes nor a
  pointer for the host. It kept only the eight macrocells that put status and its own
  framer reads on the shared bus.

### 7.3 U2 — RX, and this is still the fit risk

| block | MC |
|---|---|
| deserializer 8, bit counter 3, SFD compare + in-frame lockout 2 | 13 |
| framer write address: 11-bit in-bank counter + 4-bit write bank + wrap | 16 |
| ring bookkeeping: head-bank counter 4, outstanding count 5, full/empty compare 3 | 12 |
| RX control FFs (`IN_FRAME`, `RX_EN`, `RX_IE`, `NIDLE` sync ×2, `LINK_UP`, `RX_OVERRUN`, `TX`-side mirror) | 8 |
| **RX CRC-32 LFSR + `fb`** | **33** |
| residue compare, 4 × 8-bit product term + AND 5; byte-boundary `crc_ok` re-latch 2 | 7 |
| EOF header-write FSM | 3 |
| RX polarity auto-detect (§8.3) | 2 |
| shared data-bus driver | 8 |
| `$FF` RX port: decode 5, stored bits 3, read mux 8 | 16 |
| `/IRQ`, LINK LED | 2 |
| **total** | **116 / 128 (91 %)** |

> ⚠ **91 % will very likely not fit, and this is still the card's largest technical risk.**
> `arch-v3.md` flags 91 % as the level at which ATF15xx fitters get unhappy — from
> switch-matrix routing pressure, not logic capacity.
>
> **The memory-mapped buffer did not relieve this, and saying so is the point of the
> table.** It bought four ICs, 27 % of throughput, the `TFM` hazard and a four-times
> deeper ring. It did **not** buy macrocells: U2 shed the host-side pointer, the prefetch
> control and the `SEL` bit (−13) and gained the ring bookkeeping for sixteen banks and a
> wider framer address (+11). The two nearly cancel. **A structural change that improves
> four things and leaves the fifth alone is the normal case, and a document that quietly
> re-scored the fifth would be the suspicious one.**

**The cut order, in the order to take it:**

| | cut | −MC | what it costs |
|---|---|---|---|
| 1 | **ring bookkeeping → software.** Give each bank a third header byte holding "occupied"; the framer checks the next bank's flag at EOF (one SRAM read in a 9.6 µs gap) and the driver clears it after draining | **8** | `NRXHD` and `NRXCNT` go; the driver tracks its own read index. **Cheap, and it is the first cut for a reason: the header trick already works** (§5.5) |
| 2 | RX polarity auto-detect (§8.3) | 2 | back to a jumper, which is where `applenet` left it |
| 3 | ring 16 banks → 8 | 2 | §3.3's burst absorption falls from 45 ms to 23 ms, which is still ample |
| 4 | `RX_OVERRUN` as a distinct latch (fold into `RING_FULL`) | 1 | the driver cannot distinguish "full now" from "dropped one" |
| 5 | **RX CRC → software** | 33 | **do not.** §13.4: 22 ms per frame at 2.0979 MHz |

Cuts 1–3 land at **104 / 128 (81 %)**, which is where this device should be built the
first time if the fitter argues at all. **Fit U2 before laying out the board** — that is
open item 1.

### 7.4 Pin budgets

Both parts are `ATF1508AS-15JC84`: 64 user I/O and 4 dedicated inputs, **60 user I/O with
JTAG ISP enabled** (TDI/TMS/TCK/TDO take pins 14/23/62/71). JTAG is enabled on both — a
10-pin header goes on the card, because in-circuit reprogramming is worth a great deal
during bring-up and because §7.3's cut order may be exercised after the board exists.

| | U1 | U2 |
|---|---|---|
| slot: `A0`–`A6`, `D0`–`D7`, `/IOSEL`, `R/W` | 17 | 17 |
| region decode: `A20`, `A19`–`A16`, `A15`, `/IOPAGE`, jumper | 8 | — |
| shared card address bus | 13 (drives A0–A12) | 15 |
| shared card data bus | 8 | 8 |
| both SRAMs' `/CE`, `/OE`, `/WE` | 5 | — |
| PHY / recovery | 2 | 3 |
| NLP divider input | 1 | — |
| inter-device (`LINK_UP`, `TXIRQ`, `SLOT`, `CARRIER`) | 4 | 4 |
| `/IRQ`, LED | 2 | 2 |
| **user I/O used** | **60 / 60** | **49 / 60** |

> ⚠ **U1 is now the pin-limited device, at 60 of 60, and this is a change of character.**
> One revision ago U2 was at 56 of 60 and U1 at 37; moving the region decode, the SRAM
> control and the schedule onto U1 moved the shortage with them. **There is no spare pin
> on U1**, so anything added there costs something else first.
>
> The relief, if it is needed: **`CARRIER` is unused on a switched link** (`plan.md` §2.4
> — no CSMA/CD, no deferral) and can come off both devices for a pin each; the second LED
> can go; and the region-base jumper can be four pins rather than five if the `A15` split
> is hard-wired instead of decoded. Any one of them is enough.

### 7.5 Clocks, domains and crossings

| | U1 | U2 |
|---|---|---|
| pin 1, **GCLR** | `/RESET` | `/RESET` |
| pin 2, **GCLK2** | `E` | `E` |
| pin 83, **GCLK1** | **`CLK25`** | **`CLK25`** |
| pin 81, **GCLK3** (an I/O pin — the fitter must be told) | 20 MHz oscillator | `rec_clk` |

`arch-v3.md` observes that its RX device has no free-running clock — "the only clock
available is a bus strobe that stops when the slot is idle". **This machine's backplane
carries a 25.175 MHz master to every slot** (`machine.md` §2, put there so any card can
phase-lock to video), and both devices take it. It is what makes §4.3's schedule possible
at all, and it is the single largest thing the port gains.

> ⚠ **U1 now needs four clocks — `CLK25`, `E`, 20 MHz and the global clear** — and an
> `ATF1508AS` has exactly three global clocks plus GCLR. The 20 MHz bit clock goes on
> GCLK3, which is pin 81, **an I/O pin the fitter must be told about**, and it is the one
> that matters most: the serializer and the CRC LFSR are the 100 ns path. Verify the
> fitter honoured it before believing a timing report.

**Every crossing needs a stated synchroniser**, and `arch-v3.md` is right that this is a
bug class the 74xx version did not have. The list:

| signal | from | to |
|---|---|---|
| `NIDLE`, `rec_data` | asynchronous | `rec_clk` (two-stage) |
| `byte_ready`, `frame_start` | `rec_clk` | `CLK25` (two-stage) |
| `RX_ADV`, `ACK_RX`, `RX_EN`, `TX_GO`, `NTXPL` load | `E` | `CLK25` (two-stage) |
| `RX_READY`, `RING_FULL`, `RX_OVERRUN`, `NRXCNT`, `NRXHD` | `CLK25` | `E` (two-stage; the count and the bank are Gray-coded or read twice) |
| `TX_DONE`, `TX_BUSY` | 20 MHz | `E` |
| `LINK_UP`, `CARRIER`, `TXIRQ` | device to device | two-stage at the receiving end |
| **`SLOT`** | **U1's `CLK25` domain** | **U2's `CLK25` domain — same clock, same edge, no synchroniser, and that is exactly why it is a wire and not a handshake** |

This list is a review checklist item, not something a testbench is expected to find.

### 7.6 ~~Arbitration — one counter, two contexts~~ Arbitration is §4.3, and it is nine macrocells

**This section used to be the hardest part of the card**, and it is worth keeping its
shape because it is the clearest measure of what the address space bought.

The problem was that the host and the framer both needed the RX SRAM at different offsets
at the same time, and the host's offset lived in a counter on the card. Three mechanisms
were priced:

| | how | cost |
|---|---|---|
| Two counters and a mux | both offsets in macrocells; a 2:1 mux drives the address pins | 11 + 11 + 11 = **33 MC** |
| One counter and a shadow | the counter drives the pins; the shadow holds the inactive context; a swap is a simultaneous parallel load | 11 + 11 + 5 = **27 MC** |
| **One counter, host side external** *(specified until 2026-09-08)* | U2's counter drives the pins and three-states; a `'161` cascade drives them through `'244`s the rest of the time | **4 MC, +5 ICs** |

**All three are gone.** The host's offset comes off the backplane (§4.2), so there is no
second counter, no shadow, no mux and no `'161` cascade. What replaced them is §4.3's
phase counter and the `SLOT` wire — **six macrocells on U1 and three on U2** — plus the
two `'244`s and the `'245` that get the bus onto the card, which were needed anyway.

**Five ICs and 4 macrocells out; three ICs and 9 macrocells in.** The `74HC574` prefetch
register went with them, because §4.3's 80 ns of margin does not need one.

## 8. The analogue front end and the recovery block

### 8.1 Unchanged, and still the risk

`plan.md` §4 and §5.1 carry verbatim: a `SN75C1168` quad differential transceiver, a 1:1
MagJack with integrated magnetics, the classic 10BASE-T transmit filter network, and the
no-PLL recovery chain — `74HC86` edge detect with an RC delay, a `74HC221` for the ~75 ns
non-retriggerable recovered clock, a `74HC123` for the ~2 µs `NIDLE` and the ~100 ms
`LINK_UP`.

Component values are `m1-notes.md` §6's, which are a desk pass and **not** a bench result:
edge delay `330 Ω / 100 pF`, `rec_clk` `1 kΩ / 100 pF` (≈70 ns), `NIDLE` `4.7 kΩ / 1 nF`
(≈2.1 µs). All timing capacitors C0G/NP0. All monostables socketed. `R10` and `R11` as
trimmers.

> ⚠ **A CPLD has no analogue delay element and this block cannot move inside one.**
> `arch-v3.md` prices the alternative — 4–8× oversampling, i.e. a 40–80 MHz recovery
> state machine — and rejects it as a from-scratch redesign of the project's
> highest-risk block. That judgement carries. **This is the only part of the card a JTAG
> reprogram cannot fix**, which is why §15's build order puts it first, alone, before
> anything else exists.

### 8.2 NLP timing comes from `E`, not from `VSYNC`

The NLP period must be 16 ± 8 ms. The backplane carries `VSYNC` (`machine.md` §2), which
at 50–70 Hz is 14–20 ms and would be a free timebase — **zero ICs and zero macrocells.**

**Not taken.** `VSYNC` exists only if the video card is present and running, and this
machine's own bring-up sequence is headless: `sdcard.md` §12 step 0 boots NitrOS-9 over
DriveWire before video exists. A card whose link drops when the video card is pulled is a
card that fails during exactly the sessions it is most useful in.

So: a `74HC4020` divides `E` by 16,384 to 128 Hz, U1 divides by two, and the NLP period is
**15.6 ms**. One IC, one macrocell, and no cross-card dependency.

### 8.3 RX pair polarity — and a proposal to close `applenet`'s oldest open item

`review.md` §1.4 has been open since v1: **a swapped RX pair inverts Manchester, and the
inversion is undetectable and fatal.** The card sees a valid-looking bitstream that never
matches an SFD. The recorded fix is a jumper.

Two macrocells do better. While hunting, U2 compares the deserializer window against
`0xD5` **and** against `0x2A` (`0xD5` inverted). A match on the second sets a polarity
bit that XORs `rec_data` for the rest of the frame; the bit is re-evaluated on the next
frame. The compare is one product term either way — `arch-v3.md` already notes the SFD
compare is literally one — and the invert is one macrocell on `rec_data`.

**The honest caveats:** it is untested, a corrupted preamble could latch the wrong
polarity for one frame (the CRC then rejects it, which is the correct outcome), and it is
first on §7.3's cut list. **Keep the jumper footprint on the board regardless.**

---

## 9. Chip budget

| # | Part | Role |
|---|---|---|
| 1 | `ATF1508AS-15JC84` | **U1** — TX domain, the `$FF` TX registers, the region decode, the §4.3 schedule |
| 2 | `ATF1508AS-15JC84` | **U2** — RX domain, the ring, the `$FF` RX registers |
| 3 | `62256` 32K×8, 55 ns | **RX ring — 16 banks of 2 KB.** Region `A15 = 0` |
| 4 | `6264` 8K×8, 55 ns | TX — 4 banks of 2 KB. Region `A15 = 1` |
| 5 | `74HC244` | backplane `A7`–`A0` → shared card address bus |
| 6 | `74HC244` | backplane `A14`–`A8` → the same, plus the `A15` SRAM select |
| 7 | `74HCT245` | backplane `D7`–`D0` ↔ shared card data bus. **HCT because it faces the slot** |
| 8 | `74HC86` | RX edge detect |
| 9 | `74HC221` | `rec_clk`, ~75 ns, **non-retriggerable** — `m1-notes.md` §6 |
| 10 | `74HC123` | `NIDLE` ~2 µs and `LINK_UP` ~100 ms, both retriggerable |
| 11 | `74HC4020` | NLP timebase, `E` ÷ 16,384 — §8.2 |
| 12 | `SN75C1168` | differential line driver and receiver |
| — | 20 MHz oscillator can | TX bit clock — §11 |
| — | RJ45 MagJack, 1:1 | e.g. `HR911105A` |
| — | | TX filter network, 100 Ω RX termination, LEDs, decoupling, JTAG header, two jumper blocks (`$FF` base, region base) |

**12 ICs.** For scale: video 41, audio 29, PS/2 11, storage 13, serial 3.

> ⚠ **This was 16 until 2026-09-08, and the four that left are worth naming**: three
> `74HC161` and a `74HC244`/`74HC125` pair carrying the host-side RX pointer, and the
> `74HC574` that prefetched a byte for it. **All five existed to get an address to the
> SRAM that the backplane now delivers**, and the two `'244`s and the `'245` that replaced
> them are doing a simpler job. §7.6.
>
> The `6264` on the RX side became a `62256` in the same revision — same package, same
> pin count, same price, four times the ring (§3.3).

**`74HCT` only where a part's input is driven from the slot** — here that is the `'245`
and the two `'244`s. Both CPLDs accept TTL levels natively (`V_IH(min)` = 2.0 V) and
everything else is on-card (`machine.md` §2.1, `plan.md` §12).

> ⚠ **The `'244`s are `74HC` and face the slot, which contradicts the rule above.** They
> are address inputs, and the machine's address lines are driven by the CPU module's own
> `'541` buffers at full CMOS levels rather than by an NMOS part (`plan.md` §2.6), so
> `V_OH` is not the 2.4 V the rule exists for. **This is the one place on the card where
> that argument is being made rather than the rule being followed**, and if the CPU
> module's buffers are ever changed it is where to look first. `74HCT244` if in doubt —
> it costs nothing.

**Decoupling is not optional and under-decoupled CPLDs look like logic bugs.** 100 nF at
each of the eight VCC pins per device (2 VCCINT + 6 VCCIO), plus bulk. `arch-v3.md` says
the same and it is worth repeating because it is a classic bring-up failure.

**PLCC-84 sockets are through-hole and hand-solderable**, so the Eurocard fits the same
build method as the rest of the machine. Confirm footprint availability before layout —
`arch-v3.md`'s open item, still open.

## 10. Power

| | typ |
|---|---|
| 2 × `ATF1508AS`, reduced-power mode on the `E` domain and the NLP path, full power on the bit path | **220–250 mA** |
| `62256` + `6264`, active | ~60 mA |
| 7 × 74HC/HCT, switching | ~40 mA |
| `SN75C1168` driving a terminated pair | ~60 mA |
| 20 MHz oscillator can | ~30 mA |
| **total** | **~410–510 mA** |

**Reduced-power mode is per-macrocell and it is fatal in the wrong place.** It adds
`tRPA` = 13 ns at -15 to `tLAD`/`tLAC`/`tTIC`/`tACL`/`tSEXP` — harmless on the `E`-domain
host port and the NLP divider, and unusable on anything in the 100 ns bit path: the
serializer, the deserializer, both CRC LFSRs and both framer pointers stay full power.
**§4.3's phase counter and the shared-bus drivers stay full power too**, because a
two-tick window is 79 ns and 13 ns of it is 16 %.

Without reduced-power mode the pair is 320 mA of standby before any dynamic current.

**This must be measured before a PCB is committed**, as `arch-v3.md` says. Against a
machine `machine.md` §8 estimates at 2.5–3.5 A it is not alarming; it is the second
largest single-card draw after video's 1.1–1.7 A, and it is the only figure on this card
that cannot be derived from a datasheet with confidence.

## 11. Clocks — and the machine's third crystal

**The bit rate must be 10.000 MHz and the backplane cannot supply it.** 25.175 / 10 =
2.5175, not an integer, and 10BASE-T's tolerance is ±100 ppm. So a **20 MHz can** goes on
the card and U1 divides by two, exactly as `plan.md` §11 specifies.

That makes three oscillators in the machine: 25.175 MHz on the motherboard, 28.37516 MHz
on the audio card (`audio.md` §4.1, non-negotiable because every module in the corpus was
tuned by ear against it), and 20 MHz here. `machine.md` §1's "one oscillator, everything
derived" had one exception; it now has two, and this one is forced by an external
standard rather than chosen.

**The RX side needs no oscillator**, because the bit clock is recovered from the incoming
transitions (§8.1). `CLK25` from the backplane serves U2's arbiter, not its bit timing —
the two must not be confused, and nothing in the `rec_clk` domain is allowed to depend on
`CLK25`.

---

## 12. Period audit, and the house rule this card retired

**10BASE-T is IEEE 802.3i, ratified in 1990.** The machine's implicit line is 1989. So:

| | |
|---|---|
| Ethernet itself (802.3, 10BASE5) | **1983** — comfortably in period |
| 10BASE2 thin coax (802.3a) | **1985** — in period |
| **10BASE-T over twisted pair** | **1990** — one year out |
| Every part on this card | 1980s |
| The RJ45 MagJack | 1990s in this exact form |

This is the machine's **second** period exception, after the SD card, and a much smaller
one: the *format* is a year late, not the *silicon*. §13.5 records the period-exact
alternative, which is 10BASE2 and costs a different analogue front end and nothing else.

### ~~The house rule~~ The house rule, and this card is what retired it

**The root [`README.md`](../../README.md)'s no-CPLD rule was retired on 2026-09-08**,
and the argument below is one of the three reasons. It is kept because it is the
argument, not because the conclusion is still in doubt.

When this card was specified the rule read *"no CPLDs or FPGAs — spent, deliberately,
on two cards"* — video, to compete with a GIME on even terms, and audio, because its
interrupt block does not fit a `GAL22V10` either way. **This card was the third**, and
this section said the sentence in the root README would have to change. It did.

**The argument, and it is a machine-level one rather than a taste one:**

1. **The slot budget forbids the 74xx design.** `applenet`'s v2 measured a discrete
   10BASE-T MAC at **41 ICs across two cards** — it needed two because the logic does not
   fit one Apple II card. A 100 × 160 Eurocard is larger, but not by enough to also carry
   two SRAMs, the MagJack, the filter network and the analogue section. Two cards means
   two slots. [`hardware/README.md`](../../hardware/README.md) gives the machine
   **six slots, five of them already claimed**. There is one.
2. **The CRC has no software escape at 2.0979 MHz.** A table-driven CRC-32 over 1518
   bytes at ~30 cycles/byte is **~22 ms per frame** — eighteen times a frame's own
   transmission time. `arch-v3.md`'s own cut order says that if only one hardware CRC
   survives it must be the RX one; here neither can go.
3. **A `GAL22V10` cannot hold any of it.** Ten macrocells against 33 for one LFSR.

**What the rule says now.** Period-appropriate silicon, and **programmable logic is in**
— GALs, and CPLDs where a GAL will not carry the design. Point 3 above is that test,
stated before the rule was written to match it.

[`io/README.md`](../../io/README.md) had already derived the working version —
*"what decides each case is whether a period part exists that fits the I/O budget"* —
and §13.6 added the term it was missing, at this card's expense: **availability comes
first.** A `DP8390` exists and fits; you cannot buy one.

---

## 13. What was considered and not taken

### 13.1 ⚠ DMA — and the backplane forecloses it

The one change that would break §3.1's ceiling is not to move bytes through the CPU at
all. A bus-mastering card writing frames straight into system RAM would run at the SRAM's
speed and cost the host one interrupt per frame instead of a 1,518-byte copy.

**It cannot be built on this backplane.** [`hardware/lib/slot.ts`](../../hardware/lib/slot.ts)
has no bus-request/bus-grant pair; `machine.md` §2.1 records `/HALT` as "tied high on the
motherboard through 4.7 kΩ — nothing in this machine drives it, and saying so is the
point"; and `BA`/`BS`, which are how a 6809-family CPU announces it has released the bus,
never leave the CPU module.

> ⚠ **And on 2026-09-08 the one spare pin went to something else.** `machine.md` §5 item 1
> option D made slot position A34 physical `A20`. That competition is decided: a seventh
> signal position would now have to come out of the ground or power allocation.
>
> **The card did better out of it than it would have out of DMA.** DMA was wanted for
> §3.1's ceiling, and `A20` does not raise that — the ceiling is one `TFM` against a
> 2.0979 MHz `E` either way. What `A20` bought instead is everything §7.6 lists: the
> `TFM` hazard retired, five ICs deleted, the ring four times deeper, and TX overlap for
> free. **DMA would have bought one number; the address space bought five.**

**What is still true** is that this is the first card in the machine that would actually
want bus mastering, and that the pins could have been reserved for free while
`machine.md` §5 item 5 was open. It is recorded for whoever revisits the connector.

### 13.2 A third CPLD

U2 at 92 % (§7.3) has an obvious answer: move the host port and the ring's host side into
a third device, which fits comfortably (~49 macrocells, ~46 pins) and takes U2 to ~73 %.

**Not taken**, for two reasons and neither is elegance: it adds ~160 mA of standby to a
card that is already the machine's second largest draw, and it spends the house rule
three times on one card. §7.3's cut order reaches 83 % without it. **If U2 fails on pins
rather than macrocells, this becomes the answer** (§7.4).

### 13.3 ~~A deeper ring, a second TX buffer, a 62256~~ Taken — all three, 2026-09-08

This section used to price three additions and defer all of them, "cheap in parts and
expensive in the one currency that is short". **The currency stopped being short.**

| | then | now |
|---|---|---|
| eight RX banks instead of four | ~5 macrocells at 92 % — "revisit after the first fit" | **sixteen**, for a `62256` in the same package. §3.3 |
| TX ping-pong | 12 macrocells on U1 plus a shadow-exchange arbiter — "the best-value addition on the card" | **four TX banks, for nothing.** The host addresses the buffer, so there is no shared pointer to ping-pong around. §3.1 |
| a `62256` | the cheap half of a change whose expensive half was macrocells | fitted |

**What paid for all three is `machine.md` §5 item 1 option D and §5 item 7** — a megabyte
of physical space at `A20 = 1`, bought with one backplane pin and no ICs. The card's whole
buffer subsystem stopped being a macrocell problem and became a choice of SRAM part.

**The deferred alternative that is left**: 64 KB of RX ring instead of 32, i.e. 32 banks,
which needs a larger part or a second `62256` and one more bit of write-bank counter.
§3.3's 45 ms is already two orders of magnitude past any interrupt-mask window in the
machine, so there is no argument for it that this document can make.

### 13.4 One CPLD with software CRC

`arch-v3.md` shows a single `ATF1508AS` holds the whole card at ~122/128 if the CRC goes
to software. On an Apple IIe that is a defensible trade. **Here it is not**: §12's 22 ms
per frame is 18× the frame's own transmission time and would cap the card at roughly 45
frames/s. The second CPLD is not a luxury on this machine, it is the thing that makes the
card work at all.

### 13.5 10BASE2 instead of 10BASE-T

**The period-exact answer** (802.3a, 1985), and the digital half of this card does not
change by a single macrocell — Manchester, framing and CRC are identical. What changes is
the analogue front end: a coax transceiver and a BNC tee in place of the differential
driver and the MagJack, no NLP (10BASE2 has no link-integrity mechanism), and CSMA/CD
becomes real because the segment is genuinely shared — which is precisely the
simplification `plan.md` §1 takes and would have to give back.

**Not taken** because collision detect, backoff and deferral are a substantial addition to
a device already at 92 %, and because nothing in 2026 has a 10BASE2 port to plug into.
It is recorded because it is the honest answer to "could this have been built in 1989".

### 13.6 A period Ethernet controller — the `DP8390`, and why it lost twice

`io/README.md` sets the test: *"what decides each case is whether a period part exists
that fits the I/O budget"*. Serial passed it — a 6551 is one chip and four addresses.
Ethernet has such a part on paper: the **National `DP8390` NIC (1986)** plus a `DP8392`
coax transceiver, buffer RAM and a latch — **four to six ICs**, no CPLD, no house-rule
exception, and a design shipping in volume before this machine's notional date.

**It failed the second half of the test when this document was written.** The `DP8390`'s
register file is 16 registers across four pages plus a remote-DMA data port and a reset
port — **16 bytes at an absolute minimum and 32 as everyone actually decoded it.**
`machine.md` §3 had **four**, and §5.1 above is what happened to those four.

> ⚠ **`machine.md` §5 item 1 was closed on 2026-09-08 and the window is 128 bytes, so
> that argument no longer holds — and the decision does not change.** The reason is one
> this document did not check and should have, because it is the first question to ask of
> any part: **the `DP8390` is long obsolete.** It is not in production, distributor stock
> is gone, and what is offered is priced as a collectable rather than as a component.
> A design cannot rest on a part you cannot buy at a sane price, and "four ICs" is not
> four ICs if one of them is a hunt.
>
> **So the card keeps the dual-`ATF1508AS` design of §7, unchanged**, and now for a
> better reason than the one it was chosen with. The `ATF1508AS` is in production, in a
> hand-solderable PLCC-84, programmable in circuit over JTAG, and already on this
> machine's audio card. **Availability, not address space, is what decides this**, and
> that ordering is worth carrying to the next card: the I/O budget is the second
> question.
>
> **The superseded argument is kept rather than deleted**, per the convention at the
> bottom of the root `README.md`. It was true on the day it was written, it is what
> `machine.md` §5 item 1 cites as the strongest evidence the map had produced against
> itself, and deleting it would make the machine's own history unreadable.

**One thing does survive both rounds**, and it is a project argument rather than an
engineering one: `applenet/docs/plan.md` §1's stated primary purpose is *learning Ethernet
framing at the bit level*, and a `DP8390` is exactly the chip that hides all of it. On a
card whose reason to exist is the framing, buying the framing is not a saving.

---

## 14. Software

**This is the largest cost on the card and it is not specified here.**

### 14.1 The driver

- **RX**: `/IRQ` → read `NRXST` → `CARD_IRQ` says it was us → `NRXCNT` says how many and
  `NRXHD` says where the oldest one is. For each frame: map the bank, read the two header
  bytes for `RXLEN` and `CRC_OK`, then

  ```
          ldx   #bank+2          ; the frame, in the card's SRAM
          ldy   #buffer
          ldw   len
          tfm   x+,y+
  ```

  then `NCMD` = `RX_ADV`. **Loop until `NRXCNT` reads zero before `RTI`** — §3.4 is why,
  and it is the single most important line of the driver.
- **TX**: build DST..payload **in the card's TX bank directly** — there is no reason to
  build it in system RAM and copy — **pad to 60 bytes** (§7.2 moved this to software),
  end-align it so the last byte is the last byte of the bank, write `NTXPH` then `NTXPL`
  with the first byte's offset, then `NCMD` = `TX_GO`.
- The host computes no CRC and does no Manchester. It shuffles bytes and builds headers,
  which is the point.

> ⚠ **Three things the 2026-09-08 revision deleted from this driver**: the chunk-and-mask
> loop (§3.2), the `SEL` bit before every pointer write, and the two `NDATA` reads that
> used to fetch the header. **Building the TX frame in place is new** and it is worth
> noticing — the port version could not, because the only way into the buffer was a
> byte at a time through a register.

### 14.2 ⚠ And above the driver there is nothing

**NitrOS-9 Level 2 has no TCP/IP stack that this document can point at.** That is a
statement of ignorance, not a finding — it is `machine.md` §6's `serial` row all over
again ("confirm whether NitrOS-9's `sc6551` exists; it is the card's entire software
cost"), and it should be resolved by looking before anyone buys a MagJack.

What the card is definitely good for without a stack, because these are raw-frame
problems:

- **ARP and ICMP echo** — the golden frame in `plan.md` Appendix B is an ARP request, and
  answering pings is the classic first light for a hand-built MAC.
- **A boot/transfer protocol of the machine's own** — DriveWire's framing over Ethernet
  instead of over the serial card, which would be dramatically faster than
  `sdcard.md` §12 step 0's serial path and is a few hundred bytes of 6309.
- **A `TFTP`-shaped loader**, which needs UDP and nothing above it.

**Anything TCP-shaped is a port, not a driver**, and §3.4's interrupt arithmetic says a
naive one will not survive contact with a busy LAN. This is a bigger software cost than
`storage`'s RBF driver, which `sdcard.md` §13 item 4 already calls "larger than the card".

> **One thing got structurally easier.** A memory-mapped ring means a stack can parse a
> frame **in place** and copy only the payload it keeps — an ARP or ICMP responder never
> has to copy at all. §3.1's 681 KiB/s is the cost of a full copy, and a driver that is
> clever about what it copies is not bound by it.

---

## 15. Build order

**Step 0 — ~~freeze `machine.md` §5 item 1~~ done.** The machine settled its address
spaces on 2026-09-08 (`machine.md` §5 items 1 and 7) and this card was re-specified
against them. What is left is the card's own work.

1. **The recovery block, alone, on perfboard.** `m1-notes.md` §§3–4 is the procedure and
   it is written for exactly this: 20 MHz can, ÷2, a `'165` shifting a known pattern,
   `'86` Manchester, the `75C1168`, magnetics, an RJ45 loopback plug (pin 1→3, 2→6), then
   the `'221` and `'123`. **Pass = 1,000 bits with no errors and one clean `rec_clk` pulse
   per bit.** Nothing else on this card matters until this passes, and it is the only
   block a reprogram cannot fix (§8.1).
2. **Fit U2, then U1.** §7.3 — before layout, and with the cut order in hand. **U1's pin
   budget is now the tighter of the two at 60 of 60** (§7.4), so fit it rather than
   assuming it.
3. **Write both devices' Verilog and the testbench**, against `plan.md` Appendix B's
   golden ARP frame and Appendix A's `"123456789"` → `0xCBF43926` vector. The testbench
   clocks TX serializer through RX deserializer on one bench, which is the thing the
   per-GAL equation benches in this repository cannot do.
4. **Bench the `$FF` registers with no SRAM on the card** — `NTXST`/`NRXST` reads and
   `NCTRL` writes against a running machine. This is where §4.4's E-fall strobe gets
   proven.
5. **⚠ Bench the §4.3 schedule, and do it before trusting anything above it.** Two
   devices three-state onto one address bus and one data bus; the `SLOT` wire is what
   keeps them apart and it is the card's one new failure mode (§7.1). **Scope the shared
   buses for overlap with the host's window and with each other**, with both framers
   running and the host hammering the region. This step did not exist before 2026-09-08
   and it is the price of the four ICs that came off.
6. **Loopback the whole card**: the RJ45 plug from step 1, TX → RX, one frame, `CRC_OK`
   set, `RXLEN` right, the header where §5.5 says, in the bank `NRXHD` names.
7. **A real switch**, then a real host: ARP request out, ARP reply in and checked.
8. **Measure §3.1 and §3.4.** The sustained RX rate with the ring, the frames/s ceiling
   at whatever a NitrOS-9 dispatch actually costs, and the drop rate under a small-frame
   flood. **These are the numbers this document is least confident about**, and every one
   of them is arithmetic today.
9. **Measure the current draw** (§10), with reduced-power mode configured as specified.

---

## 16. Open items

**Blocking a board:**

1. **⚠ U2 does not obviously fit** — 116/128 macrocells, §7.3. Fit it before layout; the
   cut order is there and cuts 1–3 reach 81 %.
2. **⚠ U1 has no spare pin** — 60 of 60, §7.4. It took the region decode, the SRAM
   control and the §4.3 schedule in the 2026-09-08 revision and that is where the pins
   went. Three separate reliefs are listed; none has been chosen.
3. **⚠ The `SLOT` handshake and the shared buses** — §7.1, §15 step 5. The one failure
   mode this card gained rather than shed.
4. ~~**⚠ The house rule**~~ **CLOSED 2026-09-08** — retired at the root `README.md`,
   with this card's §12 as one of the three arguments.
5. **⚠ §4.3's schedule assumes a bus cycle of fixed length, and `/WAIT` broke that.**
   `machine.md` §5 item 8 made `/WAIT` work on 2026-09-08; the video card asserts it while
   its span writer runs, and this card's framers get no slot while `E` is frozen. **A
   stretch longer than 800 ns drops a received frame.** Two things are needed: the phase
   counter must saturate rather than wrap, and **`graphics.md` must bound `SPANBUSY`'s
   duration**, which no document does. **This is the highest-priority item on the card
   that is not a fit.**
6. **⚠ §4.3's schedule is a ÷12 schedule.** Fast-E needs the framers interleaved on
   alternate bus cycles and nobody has done that arithmetic.

**Carried from `applenet`, unchanged and still open:**

7. **Recovery margin (`review.md` §2.1)** — the recovered-clock sampling window is ~35 ns
   of a 50 ns budget, on paper, never scoped. The project's oldest risk.
8. **RX pair polarity (`review.md` §1.4)** — §8.3 proposes two macrocells that close it
   and admits they are untested. Keep the jumper footprint.
9. **TX filter and MagJack choice** (`arch-v3.md` open item 8.3) and **shield/chassis
   ground** (8.5).
10. **PLCC-84 socket footprint availability.**

**Measurement, and shared with the machine:**

11. **⚠ NitrOS-9's interrupt dispatch cost.** `ps2.md` §14 item 3. It decides four things
    (§3.4) and it is the cheapest high-value measurement in the machine.
12. **Power** (§10) — bench it before a PCB.
13. **Clock-domain crossings** (§7.5) — the synchroniser list is a review item, not a
    testbench item.

**Software:**

14. **⚠ Does a NitrOS-9 network stack exist?** §14.2. It is the card's largest cost and
    nobody has looked.

**Closed 2026-09-08:**

- ~~*The `$FF` map has no room for this card.*~~ `machine.md` §5 item 1 A — the window is
  128 bytes. The card's decode became `A0`–`A6` (§4.1).
- ~~*Re-price the RX buffer against `A20`.*~~ Done; it is this revision. §7.6, §13.3.
- ~~*The `TFM` hazard.*~~ Retired rather than mitigated — §3.2. `sdcard.md` §13 item 1
  still needs its silicon capture, but no bulk transfer on this card runs over a port any
  more.

---

## 17. Cross-references

| | |
|---|---|
| [`docs/machine.md`](../../docs/machine.md) | §2 backplane, §3 the `$FF` map this card fills, §4/§4.1 interrupts and polling order, §5 item 1, §8 power |
| [`storage/docs/sdcard.md`](../../storage/docs/sdcard.md) | §3.4 phantom reads, §4 the `TFM` hazard, §6.2 the prefetched port idiom, §11.6 the CPU-side fix |
| [`io/README.md`](../../io/README.md) | the "does a period part fit the I/O budget?" test that §13.6 applies and fails |
| [`audio/docs/audio.md`](../../audio/docs/audio.md) | §8.1 the `ATF1508AS` open-collector `/IRQ` output, §9.3 the `'574` that drives the bus itself |
| [`hardware/README.md`](../../hardware/README.md) | the 72-pin slot, the six-slot count §12 depends on, and the `$FF` map as data |
| [`hardware/gal/README.md`](../../hardware/gal/README.md) | the house bus cycle — E-fall, Q-rise, E-rise, Q-fall — that §4.2 and §4.3 are written against |
| `~/code/applenet/docs/plan.md` | the wire format, the analogue front end, the recovery block, the CRC taps, the golden frame |
| `~/code/applenet/docs/arch-v3.md` | the two-CPLD architecture, and §3.3.1's finding against it |
| `~/code/applenet/docs/review.md` | 40 findings; the four still open are items 4–7 above |
