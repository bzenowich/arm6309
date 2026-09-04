# `storage/` — mass storage

An SD card interface: **7 ICs, 537 KB/s, four bytes of I/O space.**

Paths below are relative to this directory.

| | |
|---|---|
| [`docs/sdcard.md`](docs/sdcard.md) | the card — the SPI engine, the `TFM` hazard, register map, IC budget |

## The idea, in one line

**The bus read strobe triggers the next SPI burst.** Reading the data port returns byte N
and prefetches byte N+1 in hardware, so there is no software SPI at all — no bit-banging,
no busy-polling in the fast path. Taken from NormalLuser's
[BE6502 Fast SD Card Interface](https://github.com/NormalLuser/BE6502-Fast-SD-Card-Interface),
which measures 130 KB/s on a 5 MHz 6502.

It goes faster here because the 6309 has **`TFM X,Y+`** — a block move with a *fixed
source* and incrementing destination, three cycles a byte. That is exactly "read this port
512 times into a buffer", and it is one instruction.

## And that is where it goes wrong

**`TFM` is the 6309's only interruptible instruction, and on resume it re-reads the source
address.** Against RAM that is idempotent, which is why
[`../audio/docs/modplayer.md`](../audio/docs/modplayer.md) §4.4's mirror-image
`TFM X+,Y` upload is safe. Against a port whose read *pops a byte*, the re-read returns
the wrong one, the block shifts by one from that point, and **nothing detects it** — not
even the block's own CRC, which ends up read at the wrong offset.

At ~200 interrupts/s against a 735 µs block, that is roughly **one block in seven**.

Hardware cannot fix it: a `TFM` resume read and a legitimate next read are the same bus
cycle. The fix is to **chunk the transfer and mask interrupts around each chunk** — 32-byte
chunks cost 21 % of peak and add 49 µs of interrupt latency, which is nothing against a
20 ms replayer tick. §4.

⚠ **This is the only place in the machine where a card's correctness depends on an
undocumented CPU behaviour.** `plan.md` §7 already wanted `TFM` interruptibility settled by
silicon capture; this makes it two things waiting on that answer.

## Two other things worth knowing

**It gives four bytes back to the `$FF` map.** `serial.md` §7.1 reported the map exactly
full; an SPI port needs three registers where the WD1773 the reservation was sized for
needs five plus a latch, so `$FF5C`–`$FF5F` is free again. §6.1.

⚠ **An SD card is 1999**, and there is no arguing it into a pre-1990 machine. §10 makes the
case that the *circuit* is period-legal TTL and only the *media* is not — the same status
as the modern LCD on the video card's VGA output — but it is a real exception, it is the
only one in the machine, and §11.2 keeps a WD1773 floppy controller as the period answer if
it is refused.

## Status

**Specified, nothing built.** The deliverable is the document.

`docs/sdcard.md` §12 gives the build order. Step 0 gets a filesystem onto the machine over
DriveWire before any of this exists. **Step 1 is the silicon capture that decides whether
§4 is real.** Step 4 — 10⁵ blocks byte-exact with every other card's interrupts running — is
the only step that can prove the mitigation works.
