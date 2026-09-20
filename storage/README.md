# `storage/` — mass storage

An SD card interface: **8 ICs, 537 KiB/s sustained, four bytes of I/O space and nothing
else.**

Paths below are relative to this directory.

| | |
|---|---|
| [`docs/sdcard.md`](docs/sdcard.md) | the card — the SPI engine, the `TFM` hazard, the SD protocol sequences, the register map, the IC budget |
| [`docs/history.md`](docs/history.md) | archived history — the buffer era, superseded rates, dropped listings |

The design outputs live in `../hardware/gal/storage/`: `sdbus.jedec.ts` and
`sdeng.jedec.ts` are the two `GAL22V10`s, `storage.check.ts` is 24 claims against them,
and `census.ts` is the pin count that decided how many parts there are. Where they and
the prose disagree, they win.

⭐ **And since 2026-09-20 the software exists too**, which `sdcard.md` §9.4 called the
real cost of this card:

| | |
|---|---|
| `../hardware/gal/verilog/storage_tb.sv` | the card in Verilog against an SD card model — **55 claims** |
| `../software/demo/emu/test/run-sdtest.sh` | the same card in C, in the host emulator — **55 claims** |
| ⭐ `../software/nitros9/run-sd.sh` | **NitrOS-9 boots and uses it**: `/SD0` mounted, a host-written filesystem listed and read, a file written and deleted, and the host tools checking afterwards that the write reached the card. **17 claims, with a no-card negative control** |
| the driver | `rbsd.asm` and `sddesc.asm` in the NitrOS-9 port's `level2/arm6309/modules/` |

⚠ **It runs at ~130 KiB/s, not 537.** `rbsd` issues one `CMD17` per block and the port
builds `CPU=6809`, so it gets neither §9.1.1's multi-block amortisation nor `TFM`.
Both are software and both are open.

**Units:** every rate here and in `docs/sdcard.md` is **KiB/s = 1024 bytes/s** — 537 KiB/s
is 551 kB/s decimal, and the same figure everywhere it appears in the repo.

## The idea, in one line

**The bus read strobe triggers the next SPI burst.** Reading the data port returns byte N
and prefetches byte N+1 in hardware, so there is no software SPI at all — no bit-banging,
no busy-polling in the fast path. Taken from NormalLuser's
[BE6502 Fast SD Card Interface](https://github.com/NormalLuser/BE6502-Fast-SD-Card-Interface),
which measures 130 KB/s on a 5 MHz 6502.

It goes four times faster here for one reason: the 6309 has **`TFM`**, a block move at
three cycles a byte, one instruction per chunk. The card delivers a byte every 636 ns and
the instruction asks for one every 1430 ns, so nothing ever waits.

## The `TFM` hazard — mitigated, in both directions

**`TFM` is the 6309's only interruptible instruction, and on resume it re-reads the source
address.** Against RAM that is idempotent, which is why
[`../audio/docs/modplayer.md`](../audio/docs/modplayer.md) §4.4's fixed-destination
`TFM X+,Y` upload is safe. Against a port whose read *pops a byte*, the re-read returns
the wrong one, the block shifts by one from that point, and **nothing detects it** — not
even the block's own CRC, which ends up read at the wrong offset. Roughly one block in
seven, at this machine's interrupt load.

**The fix is software, and it is the same loop on the read path and the write path:**

```
        ldx   #SDDATA              ; the port: fixed source
        ldy   #dest
        ldb   #16                  ; 16 chunks of 32
Chunk   orcc  #$50                 ; mask IRQ and FIRQ -- the chunk is now atomic
        ldw   #32
        tfm   x,y+
        andcc #$AF                 ; pending interrupts fire here
        decb
        bne   Chunk
```

An instruction that cannot be interrupted cannot be resumed, so there is nothing to
re-read. It costs **21 %** — 680 KiB/s unchunked against 537 — and 49 µs of added
interrupt latency, which is below anything else in the machine that cares.
`sdcard.md` §4.4.

**What is still owed**: whether the masking can come out at all. That is
[`sdcard.md`](docs/sdcard.md) §12 step 1's silicon capture, and on this card it is now
worth 21 % rather than nothing. §13 item 1.

## Three rates, not one

| | Rate | Bound by |
|---|---|---|
| Read, intra-block | **537 KiB/s** | the 32-byte chunked `TFM`, 3.81 cycles a byte |
| **Read, sustained, `CMD18` multi-block** | **537 KiB/s** | the same `TFM` loop. The card's read-ahead collapses the inter-block gap to a few byte times, so **the ceiling is the sustained rate** |
| Read, sustained, one `CMD17` per block | **253 KiB/s** | the card's ~1 ms read access latency, paid 256 times instead of once |
| Write, transfer | 537 KiB/s | the `TFM` loop |
| **Write, sustained** | **126–408 KiB/s** | **the card's program time**, not the SPI clock |
| Write, one 256-byte `RBF` sector | 63 KiB/s | read-modify-write against a 512-byte SD block |

**`CMD18` READ_MULTIPLE_BLOCK costs zero hardware and is the difference between the disk
being the bottleneck and not being it.** 128 KiB of mod samples arrive in **238 ms** with
it and 505 ms without, against the 187 ms the audio card needs to swallow them.
`sdcard.md` §5.2, §9.1.1.

## Software is most of this card

`sdcard.md` §9 is the largest section, and that is the honest shape of the thing:

- **§9.0 — initialisation.** `CMD0`/`CMD8`/`ACMD41`/`CMD58`, at 393 kHz, with the two
  mandatory CRCs as hard-coded constants. **The driver requires SDHC/SDXC** and refuses SDSC
  at init, because the byte-versus-block addressing branch fails *silently* by reading the
  wrong sector, and a branch exercised only by the other kind of card is a branch that will
  be wrong when it finally runs. §9.0.1.
- **§9.1 — reading.** `$FF` goes onto `DI` immediately after the sixth command byte, before
  any polling — the ordering both of the receive pipeline's off-by-one traps hang on. The
  block itself is the chunked `TFM`, and nothing may touch `SDDATA` between the token poll
  and the first read of it.
- **§9.2 — writing.** A real sequence: start token, data, CRC, data-response token, and the
  **busy phase** — the card holds `DO` low while it programs, which is what actually bounds
  the write rate.
- **§9.3 — errors.** R1 checked, error tokens decoded, three timeouts specified, and a
  card-change poll on the VBL tick that invalidates and re-initialises instead of writing
  the old card's sector 12 onto the new card's.
- **§9.4 — the driver.** `RBF`'s sector is 256 bytes and an SD block is 512, so it must
  deblock, which is where the 63 KiB/s single-sector write comes from.

## Two other things worth knowing

**Address cost.** Four bytes at `$FF58`–`$FF5B` and no physical address space at all — the
map is `$FF00`–`$FF7F` and **this card decodes `A0`–`A6`**, seven bits, because six would
answer at `$FF18` too. That is a checked claim: `storage.check.ts` sweeps the decode over
all 8,192 input combinations and asserts the card is silent at `$FF18`–`$FF1B`.
`sdcard.md` §6.1.

⚠ **An SD card is 1999**, and there is no arguing it into a pre-1990 machine. §10 makes the
case that the *circuit* is period-legal TTL and only the *media* is not — the same status
as the modern LCD on the video card's VGA output — but it is a real exception, it is the
only one in the machine, and §11.2 keeps a WD1773 floppy controller as the period answer if
it is refused.

## The one open item that is not a measurement

**The CPU is this project's own C11 firmware, not a part on a reel.** So the `TFM` hazard
can be specified *out of the CPU* — resume without re-reading, and with nothing to write
twice — at the cost of a fidelity divergence from a real HD63C09E. What it buys is
**537 → 680 KiB/s on the read path**, an unmasked write path, and
`modplayer.md` §4.4's upload with them: every remaining `TFM` against a side-effecting
port in the machine, made unconditionally safe at once. **§11.6 prices it and deliberately
does not decide it: that call is the owner's**, to be made when §12 step 1's capture is
read.

## Eight ICs, and how the number was arrived at

Two `GAL22V10`s and six discretes: `74HCT595`, `74HC165`, `74HC574`, `74HC163`,
`74HC393`, `74LVC125`, plus a 3.3 V LDO and the socket.

**Two GALs because of PINS, not macrocells.** `../hardware/gal/storage/census.ts` counts
the pins every net needs and searches every partition of the card's logic: `sdbus` is the
decode, the strobes and the `SDSTAT` drive at 22 pins with none spare, and `sdeng` is
`SDCTRL` and the burst engine at 18 with four. ⛔ **The same search says the
memory-mapped block-buffer variant needs four GALs** — its region decode alone is
16 pins — which made that card 16 ICs rather than the 14 it claimed, and which is why the
buffer came out on 2026-09-20 and this card is the machine's smallest. `sdcard.md` §8.1,
`docs/history.md`.

**Three packages do a second job for a wire rather than a macrocell**, and that is what
keeps the logic inside two parts: the `'163`'s `/CLR` and the `'165`'s `SH//LD` are both
tied to `BUSY`, and the `'165`'s `CLK` is tied to `SCK`. The first makes the re-trigger
lockout structural; the second means `MOSI` already carries bit 7 when the first clock
edge arrives; the third is the accepted hold-time risk of §6.6.

## Status

**The logic is built and checked; the card is not.** `../hardware/gal/storage/` holds both
`GAL22V10` term lists, `storage.check.ts` (**24 claims** — the decode swept over all 8,192
input combinations, the burst engine driven with the `'393` and `'163` modelled as the
board wires them, and both parts compared against Atmel's CUPL), and `census.ts`, which
runs as part of `npm run check`. `../hardware/gal/verilog/storage_card.v` is the board
model and `../hardware/place/parts.ts` asserts the eight packages.

**What is not built: the board, the NitrOS-9 `RBF` driver, and every rate above.** Nothing
has been placed, programmed, or put in front of a real SD card, and every figure in §5 is
derived rather than measured.

`docs/sdcard.md` §12 gives the build order. Step 0 got a filesystem onto the machine over
DriveWire before any of this existed; since 2026-09-08 the machine boots NitrOS-9 out of
its own 1 MB ROM (`machine.md` §7.2) and DriveWire is the *development* link rather than
the bootstrap — [`docs/drivewire.md`](../docs/drivewire.md). **Step 1 is the silicon
capture that decides whether either path may drop its masking — and what the core should
do about `TFM`.** Step 4 — 10⁵ blocks byte-exact with every other card's interrupts
running — is the only step that can prove both the read pipeline and the masking, and
step 7 is the only one that measures a rate anyone will experience.

**Fast-E (`machine.md` §1's ÷8 rate): passes.** The card delivers a byte every 636 ns
against a `TFM` read every 1430 ns at ÷12 — a **2.25×** margin, **1.5×** at fast-E — and
there is still no `/WAIT` path. The tightest software margin is the six-byte command
send's 3× (÷12), 2× at fast-E. Every rate above is quoted at the specified ÷12
`E` = 2.0979 MHz.
