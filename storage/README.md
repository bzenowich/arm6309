# `storage/` — mass storage

An SD card interface: **14 ICs, 681 KiB/s sustained, four bytes of I/O space and a 64 KB
buffer region.**

Paths below are relative to this directory.

| | |
|---|---|
| [`docs/sdcard.md`](docs/sdcard.md) | the card — the SPI engine, the block buffer, the `TFM` hazard, the SD protocol sequences, the register map, the IC budget |
| [`docs/history.md`](docs/history.md) | archived history — superseded rates, the port-era design, dropped listings |

**Units:** every rate here and in `docs/sdcard.md` is **KiB/s = 1024 bytes/s** — 681 KiB/s
is 697 kB/s decimal, and the same figure everywhere it appears in the repo.

## The idea, in one line

**The bus read strobe triggers the next SPI burst.** Reading the data port returns byte N
and prefetches byte N+1 in hardware, so there is no software SPI at all — no bit-banging,
no busy-polling in the fast path. Taken from NormalLuser's
[BE6502 Fast SD Card Interface](https://github.com/NormalLuser/BE6502-Fast-SD-Card-Interface),
which measures 130 KB/s on a 5 MHz 6502.

It goes faster here for two reasons: a **fill engine** runs 512 bursts by itself and lands
each block in a 2 KB SRAM the host addresses as memory (`sdcard.md` §3.5), and the 6309
has **`TFM X+,Y+`** — a block move at three cycles a byte, one instruction per block.

## The `TFM` hazard — retired, not mitigated

**`TFM` is the 6309's only interruptible instruction, and on resume it re-reads the source
address.** Against RAM that is idempotent, which is why
[`../audio/docs/modplayer.md`](../audio/docs/modplayer.md) §4.4's fixed-destination
`TFM X+,Y` upload is safe. Against a port whose read *pops a byte*, the re-read returns
the wrong one, the block shifts by one from that point, and **nothing detects it** — not
even the block's own CRC, which ends up read at the wrong offset. Roughly one block in
seven, at this machine's interrupt load.

**⚠ This card does not face that hazard, and not by mitigating it.** The hazard was never
about `TFM`; it was about a port whose read has a side effect, and the block lands in a
2 KB SRAM the host addresses as memory, so the copy is RAM → RAM:

```
        ldx   #buffer_in_card
        ldy   #dest
        ldw   #512
        tfm   x+,y+              ; no masking, no chunking, no 21 %
```

The 21 % that chunk-and-mask would cost is the difference between 537 and 681 KiB/s.
`sdcard.md` §4.5, §11.1.

**What is still owed**: `SDDATA` is still a read-triggered port for the command path, and
the **write path is still on the port** — chunked and masked until the silicon capture
says otherwise. `sdcard.md` §12 step 1, §13 items 1 and 6.

## Three rates, not one

| | Rate | Bound by |
|---|---|---|
| Read, intra-block | **681 KiB/s** | the unchunked `TFM` copy |
| **Read, sustained, `CMD18` multi-block** | **681 KiB/s** | the host. The SPI engine fills a buffer in 326 µs while the host copies the last one in 735 µs, so **the SD card is never waited on** |
| Read, sustained, one `CMD17` per block | **253 KiB/s** | the card's ~1 ms read access latency, paid 256 times instead of once. **No buffer hides a command you did not send** |
| Write, transfer | 681 KiB/s | the `TFM` loop |
| **Write, sustained** | **126–408 KiB/s** | **the card's program time**, not the SPI clock |
| Write, one 256-byte `RBF` sector | 63 KiB/s | read-modify-write against a 512-byte SD block |

**`CMD18` READ_MULTIPLE_BLOCK costs zero hardware and is the difference between the disk
being the bottleneck and not being it.** 128 KiB of mod samples arrive in **193 ms** with
it and 505 ms without, against the 187 ms the audio card needs to swallow them — a 6 ms
gap. `sdcard.md` §5.2, §9.1.1.

## Software is most of this card

`sdcard.md` §9 is the largest section, and that is the honest shape of the thing:

- **§9.0 — initialisation.** `CMD0`/`CMD8`/`ACMD41`/`CMD58`, at 393 kHz, with the two
  mandatory CRCs as hard-coded constants. **The driver requires SDHC/SDXC** and refuses SDSC
  at init, because the byte-versus-block addressing branch fails *silently* by reading the
  wrong sector, and a branch exercised only by the other kind of card is a branch that will
  be wrong when it finally runs. §9.0.1.
- **§9.1 — reading.** `$FF` goes onto `DI` immediately after the sixth command byte, before
  any polling — the ordering both of the receive pipeline's off-by-one traps hang on. The
  block itself lands via the fill engine and is copied out of the buffer.
- **§9.2 — writing.** A real sequence: start token, data, CRC, data-response token, and the
  **busy phase** — the card holds `DO` low while it programs, which is what actually bounds
  the write rate.
- **§9.3 — errors.** R1 checked, error tokens decoded, three timeouts specified, and a
  card-change poll on the VBL tick that invalidates and re-initialises instead of writing
  the old card's sector 12 onto the new card's.
- **§9.4 — the driver.** `RBF`'s sector is 256 bytes and an SD block is 512, so it must
  deblock, which is where the 63 KiB/s single-sector write comes from.

## Two other things worth knowing

**Address cost.** Four bytes at `$FF58`–`$FF5B` — the map is `$FF00`–`$FF7F` and **this
card decodes `A0`–`A6`**, seven bits, because six would answer at `$FF18` too — plus one
64 KB physical region at `A20 = 1`, of which 2 KB is used. `sdcard.md` §6.1.

⚠ **An SD card is 1999**, and there is no arguing it into a pre-1990 machine. §10 makes the
case that the *circuit* is period-legal TTL and only the *media* is not — the same status
as the modern LCD on the video card's VGA output — but it is a real exception, it is the
only one in the machine, and §11.2 keeps a WD1773 floppy controller as the period answer if
it is refused.

## The one open item that is not a measurement

**The CPU is this project's own C11 firmware, not a part on a reel.** So the `TFM` hazard
can be specified *out of the CPU* — resume without re-reading, and with nothing to write
twice — at the cost of a fidelity divergence from a real HD63C09E. The block path no
longer runs over a port, so this buys the read path nothing; **what it buys is this
card's write path and `modplayer.md` §4.4's upload** — every remaining `TFM` against a
side-effecting port. **§11.6 prices it and deliberately does not decide it: that call is
the owner's**, to be made when §12 step 1's capture is read.

## ⚠ Fourteen ICs, and an alternative that would cost six of them

The buffer is not free: **seven of the card's 14 ICs are the buffer**, and six of those
are address and data plumbing — a `74HC4040` block-address counter, three `74HC157`s
muxing it against the backplane, a `74HCT245` on the data path, and the `6116` itself.
**The card is the machine's third largest.**

**One `ATF1508AS` would absorb both GALs, the counter and the mux — an 8-IC card.** The
no-CPLD house rule that once blocked it is retired (root `README.md`), and **it is not
taken**: unlike video, audio and net, this card's logic fits two GALs comfortably, so a
CPLD here buys packages rather than capability, and it costs the fuse-level verification
`hardware/gal/jedec/` gives a `GAL22V10`. §8.1 weighs it; §13 item 12 carries it.

## Status

**Specified, nothing built.** The deliverable is the document.

`docs/sdcard.md` §12 gives the build order. Step 0 gets a filesystem onto the machine over
DriveWire before any of this exists. **Step 1 is the silicon capture that decides what the
write path may drop — and what the core should do about `TFM`.** Step 4 — 10⁵ blocks
byte-exact with every other card's interrupts running — is the only step that can prove
the read pipeline closes, and step 7 is the only one that measures a rate anyone will
experience.

**Fast-E (`machine.md` §1's ÷8 rate): passes** — the engine fills the buffer autonomously
and the host reads SRAM, so nothing on this card races the CPU; the tightest margin left
is the command send's 3× (÷12), 2× at fast-E, and there is still no `/WAIT` path. Every
rate above is quoted at the specified ÷12 `E` = 2.0979 MHz.
