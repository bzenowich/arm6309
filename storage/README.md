# `storage/` — mass storage

An SD card interface: **14 ICs, 681 KiB/s sustained, four bytes of I/O space and a 64 KB
buffer region.**

Paths below are relative to this directory.

| | |
|---|---|
| [`docs/sdcard.md`](docs/sdcard.md) | the card — the SPI engine, the `TFM` hazard, the SD protocol sequences, the register map, the IC budget |

**Units:** every rate here and in `docs/sdcard.md` is **KiB/s = 1024 bytes/s**. The same
figures appear decimally elsewhere in the repo — 537 KiB/s is 551 kB/s — and are the same
figures. `sdcard.md` §0.

## The idea, in one line

**The bus read strobe triggers the next SPI burst.** Reading the data port returns byte N
and prefetches byte N+1 in hardware, so there is no software SPI at all — no bit-banging,
no busy-polling in the fast path. Taken from NormalLuser's
[BE6502 Fast SD Card Interface](https://github.com/NormalLuser/BE6502-Fast-SD-Card-Interface),
which measures 130 KB/s on a 5 MHz 6502.

It goes faster here because the 6309 has **`TFM X,Y+`** — a block move with a *fixed
source* and incrementing destination, three cycles a byte. That is exactly "read this port
512 times into a buffer", and it is one instruction.

## That used to be where it went wrong

**`TFM` is the 6309's only interruptible instruction, and on resume it re-reads the source
address.** Against RAM that is idempotent, which is why
[`../audio/docs/modplayer.md`](../audio/docs/modplayer.md) §4.4's mirror-image
`TFM X+,Y` upload is safe. Against a port whose read *pops a byte*, the re-read returns
the wrong one, the block shifts by one from that point, and **nothing detects it** — not
even the block's own CRC, which ends up read at the wrong offset. At ~200 interrupts/s
against a 735 µs block, roughly **one block in seven**.

**⚠ Retired 2026-09-08, and not by mitigating it.** The hazard was never about `TFM`; it
was about a port whose read has a side effect. `machine.md` §5 item 1 option D gave the
machine a megabyte of physical space for card buffers, so **the block lands in a 2 KB SRAM
the host addresses as memory** and the copy is RAM → RAM:

```
        ldx   #buffer_in_card
        ldy   #dest
        ldw   #512
        tfm   x+,y+              ; no masking, no chunking, no 21 %
```

The 21 % that chunk-and-mask cost is what **537 → 681 KiB/s** is made of. §4.5, §11.1.

**What is still owed**: `SDDATA` is still a read-triggered port for the command path, so
the machine still wants its silicon capture — but for a single-byte question rather than
for every block. §13 item 1.

⚠ **~~This is the only place in the machine where a card's correctness depends on an
undocumented CPU behaviour.~~** It was, then briefly it was two (`../net/` had the
identical exposure on its data port), and **on 2026-09-08 both cards moved their buffers
into the machine's new physical space and it became none — for bulk transfers.** The
capture is still owed on two of its three questions: dummy cycles driving `$FFFF`, and
whether a destination can be written twice. §12 step 1, §13 item 1.

## Three rates, not one

**537 KiB/s is the intra-block ceiling**, not a throughput: it is what the `TFM` loop does
*after* the card has sent its data token. Every block also costs a command and the card's
own read access latency, and every write costs the card's flash program time. Those are the
terms that decide what anyone actually experiences.

| | Rate | Bound by |
|---|---|---|
| Read, intra-block | **681 KiB/s** ~~537~~ | the unchunked `TFM` copy |
| **Read, sustained, `CMD18` multi-block** | **681 KiB/s** ~~528~~ | the host. The SPI engine fills a buffer in 326 µs while the host copies the last one in 735 µs, so **the SD card is never waited on** |
| Read, sustained, one `CMD17` per block | **253 KiB/s** | the card's ~1 ms read access latency, paid 256 times instead of once. **Unchanged — no buffer hides a command you did not send** |
| Write, transfer | 681 KiB/s | the `TFM` loop |
| **Write, sustained** | **126–408 KiB/s** | **the card's program time**, not the SPI clock |
| Write, one 256-byte `RBF` sector | 63 KiB/s | read-modify-write against a 512-byte SD block |

**`CMD18` READ_MULTIPLE_BLOCK costs zero hardware and is the difference between the disk
being the bottleneck and not being it.** 128 KiB of mod samples arrive in **193 ms** with
it and 505 ms without, against the 187 ms the audio card needs to swallow them —
**a 56 ms gap closed to 6 ms.** §5, §9.1.1.

## Software is most of this card

The document's §9 is now the largest section, and that is the honest shape of the thing:

- **§9.0 — initialisation.** `CMD0`/`CMD8`/`ACMD41`/`CMD58`, at 393 kHz, with the two
  mandatory CRCs as hard-coded constants. **The driver requires SDHC/SDXC** and refuses SDSC
  at init, because the byte-versus-block addressing branch fails *silently* by reading the
  wrong sector, and a branch exercised only by the other kind of card is a branch that will
  be wrong when it finally runs. §9.0.1.
- **§9.1 — reading.** `$FF` goes onto `DI` immediately after the sixth command byte, before
  any polling. Doing it after the token poll — as this document originally specified —
  destroys data byte 0 of every block and replays a command byte on `DI` while the card is
  answering. The superseded listing is kept in place, because both faults follow from the
  card's own register semantics and the corrected listing differs by the order of two lines.
- **§9.2 — writing.** A real sequence: start token, data, CRC, data-response token, and the
  **busy phase** — the card holds `DO` low while it programs, which is what actually bounds
  the write rate.
- **§9.3 — errors.** R1 checked, error tokens decoded, three timeouts specified, and a
  card-change poll on the VBL tick that invalidates and re-initialises instead of writing
  the old card's sector 12 onto the new card's.
- **§9.4 — the driver.** `RBF`'s sector is 256 bytes and an SD block is 512, so it must
  deblock, which is where the 63 KiB/s single-sector write comes from.

## Two other things worth knowing

**It gives four bytes back to the `$FF` map.** `serial.md` §7.1 reported the map exactly
full; an SPI port needs four registers where the WD1773 the reservation was sized for
needs five plus a latch, so `$FF5C`–`$FF5F` is free again. §6.1. ⚠ **Those four bytes
were spent on 2026-09-07** by [`../net/`](../net/) — `sdcard.md` §6.1 called them "one
small card, once", and the net card is that card. Filling the window is what closed
`machine.md` §5 item 1 the next day: the map is `$FF00`–`$FF7F` now, and **this card
decodes `A0`–`A6`**.

⚠ **An SD card is 1999**, and there is no arguing it into a pre-1990 machine. §10 makes the
case that the *circuit* is period-legal TTL and only the *media* is not — the same status
as the modern LCD on the video card's VGA output — but it is a real exception, it is the
only one in the machine, and §11.2 keeps a WD1773 floppy controller as the period answer if
it is refused.

## The one open item that is not a measurement

**The CPU is this project's own C11 firmware, not a part on a reel.** So the `TFM` hazard
can be specified *out of the CPU* — resume without re-reading — which deletes the chunking,
the masking and the 21 % tax and takes sustained reads to 667 KiB/s, at the cost of a
fidelity divergence from a real HD63C09E. **§11.6 prices it and deliberately does not decide
it: that call is the owner's.** It should be made when §12 step 1's capture is read, because
that is when the information is on the table.

⚠ **And it now has a second card behind it.** `net/docs/net.md` §3.2 pays the same 21 %
tax for the same reason, and unlike a disk block a dropped Ethernet frame cannot be
re-read — so the argument for specifying the hazard out of the CPU is stronger than it
was when only this card made it.

⚠ **§11.1 was taken the same day, which changes what the question is for.** The block
path no longer runs over a port, so specifying the hazard out of the CPU would no longer
buy this card anything. **What it would still buy is `modplayer.md` §4.4's upload and this
card's own write path**, which §13 item 6 admits is still on the port — so the option is
alive and its constituency changed.

## ⚠ Six ICs, and an alternative that would have cost one

The buffer is not free: **7 ICs became 14**, and six of the seven are address and data
plumbing — a `74HC4040` block-address counter, three `74HC157`s muxing it against the
backplane, and a `74HCT245` on the data path. **The card was the machine's smallest and is
now its third largest.**

**One `ATF1508AS` would absorb both GALs, the counter and the mux — an 8-IC card.** It is
~~not taken because it would spend the no-CPLD house rule a fourth time~~ — ⚠ **the rule
was retired on 2026-09-08** and this is no longer blocked. **It has not been taken
either**: unlike video, audio and net, this card's logic fits two GALs comfortably, so a
CPLD here buys packages rather than capability, and it costs the fuse-level verification
`hardware/gal/jedec/` gives a `GAL22V10`. §8.1 weighs it; §13 item 12 carries it.

## Status

**Specified, nothing built.** The deliverable is the document.

`docs/sdcard.md` §12 gives the build order. Step 0 gets a filesystem onto the machine over
DriveWire before any of this exists. **Step 1 is the silicon capture that decides whether
§4 is real — and then what the core should do about it.** Step 4 — 10⁵ blocks byte-exact
with every other card's interrupts running — is the only step that can prove the mitigation
works, and step 7 is the only one that measures a rate anyone will experience.

**Fast-E (`machine.md` §1's ÷8 rate): passes.** The burst margin falls from 2.25× to 1.5×
and there is still no `/WAIT` path. But fast-E is experimental and not guaranteed
machine-wide, so every rate above is quoted at the specified ÷12 `E` = 2.0979 MHz.
