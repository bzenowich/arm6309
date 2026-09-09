# DriveWire

## The Development Path, the Clock the Machine Has Not Got, and Why It Is No Longer the Boot Path

**Question this answers:** `storage/docs/sdcard.md` §12 step 0 says *"get a filesystem
onto the machine over DriveWire, before any of this exists"*, and five other documents
cite that step — but nothing in the repository says what DriveWire needs from this
machine, what it costs, or which card carries it. `sdcard.md` §11.3 prices it in one
paragraph as a rejected *storage* option, which is the wrong frame: DriveWire is not a
disk, it is a **host link**, and the things it is uniquely good at are the things a
disk cannot do at all.

**Status: a plan, not a specification.** Nothing here is built. The hardware it needs
already exists on paper (`io/serial/`), the software does not, and §7 is the order.

> Superseded material is archived in [history.md](history.md); this document describes
> only the present design.

---

## 0. Summary — the verdict in one table

| | |
|---|---|
| **What it is** | NitrOS-9's virtual-disk protocol: the machine asks a host PC for 256-byte sectors over a serial link, and the host serves them out of `.dsk` images |
| **Hardware cost** | **zero ICs.** It is the I/O card's serial half (`io/serial/docs/serial.md`), a null-modem cable, and nothing else |
| **⭐ Which part decides everything** | **`serial.md` §4.5's `16C550`, not the 6551.** At 19,200 baud a 256-byte sector takes 145 ms and DriveWire is a curiosity; at 115,200 it takes 24 ms and it is a working disk. **This document is the strongest single argument for `machine.md` §6's open tier decision** |
| **Throughput** | **~11.0 KiB/s** at 115,200 baud, ~22 KiB/s at 230,400 — against `sdcard.md`'s **681 KiB/s**, so **62× slower** and it is not a storage answer |
| ⭐ **What only it can do** | **give the machine a wall clock.** There is no RTC anywhere in this design — not on the motherboard, not on a card, not in the CPU module. `OP_TIME` returns the host's date and time for **zero parts**, and NitrOS-9 already asks for it |
| **⚠ What changed** | **it is no longer the boot path.** §1's 1 MB boot ROM holds NitrOS-9, so the machine boots standalone. DriveWire becomes the **development** link — the thing that gets a *new* system onto the machine — which is what it is actually best at |
| **Software cost** | a NitrOS-9 `dwio`-class low-level driver plus the `RBF` descriptors, and a boot-ROM loader for the bare-metal case. **Nobody has looked at whether the CoCo drivers port** — §8 item 1, the same shape of unknown as `serial.md`'s `sc6551` |

---

## 1. What the boot ROM changed, and why it makes DriveWire more useful rather than less

`docs/machine.md` §7.2 used to boot this machine from an 8 KB shadow ROM inside the CPU
module, and `sdcard.md` §12 step 0's plan was circular in a way `design-review.md`
§Sys-C1 caught: DriveWire needs a running 6809 client, the client needs a ROM, and the
ROM did not exist.

**Since 2026-09-08 the motherboard carries a 1 MB boot ROM** (`machine.md` §7.2,
`hardware/ram.md` §6.7) holding the boot monitor **and a read-only ROM disk large
enough for the whole NitrOS-9 Level 2 distribution**. The circularity is gone by
construction: the machine boots, mounts `/r0` out of ROM, and is a working NitrOS-9
system with no cable, no host and no SD card.

**So DriveWire stops being the bootstrap and becomes the thing that changes the
system**, and that is a better job for it:

| | boot ROM | **DriveWire** | SD card |
|---|---|---|---|
| Boots a bare machine | **yes** | needs a client already running | needs a driver already running |
| Read speed | bus speed | 11 KiB/s | **681 KiB/s** |
| **Writable** | no — it is ROM | **yes, and the media is a file on your desk** | yes |
| **Changes without a programmer** | no | **yes** | yes, if you have a card reader |
| Gives the machine the time of day | no | **yes** | no |
| Parts | 3 ICs | **0** | 14 ICs |

⭐ **The row that matters is "writable, and the media is a file on your desk".** A
cross-assembler on the host writes a `.dsk` image; the machine mounts it as `/x0` and
runs the binary. That is the edit-compile-run loop for every piece of 6809 software
this project will ever write, and it is worth more than the 11 KiB/s suggests.

---

## 2. The protocol, and what the machine has to implement

DriveWire is a request/response protocol on a raw 8N1 serial link with no framing layer
of its own. The machine is always the initiator; the host never speaks unprompted.

> ⚠ **Opcode values and the exact response shapes below are recalled, not read off a
> primary document.** The DriveWire 4 protocol specification is not in
> [`reference/`](../reference/) and should be before any of this is written — §8 item 2.
> The *shape* of the protocol is not in doubt; the byte values are.

| Op | ⚠ Code | Machine sends | Host replies | Used by |
|---|---|---|---|---|
| `OP_NOP` | `$00` | 1 byte | nothing | link probe |
| `OP_INIT` | `$49` | 1 byte | nothing | session start |
| `OP_TERM` | `$54` | 1 byte | nothing | session end |
| **`OP_READEX`** | `$D2` | op + drive + 3-byte LSN | **256 data bytes**, then takes the machine's 2-byte checksum and returns 1 error byte | **`RBF` read** |
| **`OP_WRITE`** | `$57` | op + drive + LSN + **256 bytes** + 2-byte checksum | 1 error byte | **`RBF` write** |
| `OP_GETSTAT` / `OP_SETSTAT` | `$47` / `$53` | op + drive + status code | — | `RBF` `SS_` calls |
| ⭐ **`OP_TIME`** | `$23` | 1 byte | **6 bytes** — year-1900, month, day, hour, minute, second | **§4** |
| `OP_SERREAD` | `$43` | 1 byte | 2 bytes — a channel/status pair, and data if any | §5's virtual ports |
| `OP_SERWRITE` | `$C0`+chan | op + byte | nothing | §5 |
| `OP_RESET` | `$FE`/`$FF` | 1 byte | nothing | recovery |

**Three properties of the protocol are what make it cheap to implement:**

- **The sector is 256 bytes and so is a NitrOS-9 `RBF` sector.** No blocking, no
  partial-sector arithmetic, no read-modify-write. `sdcard.md` §4 has to care about
  512-byte SD blocks; this does not.
- **The machine drives the turnaround.** There is no host-initiated traffic to poll
  for, so the driver is a straight-line write-then-read and never a state machine.
- **The checksum is a 16-bit sum of the 256 bytes, not a CRC.** `ADDD`-per-byte in the
  same loop that moves them.

### 2.1 ⚠ And one property that is a hazard on this machine

**There is no timeout in the protocol and no framing.** If the machine and the host
disagree about how many bytes are in flight — because a byte was dropped, or because
the machine reset mid-sector — the link **desynchronises silently** and every
subsequent sector is off by the same amount. DriveWire's own answer is `OP_RESET` and a
host-side idle timer.

**On this machine the failure has an extra cause**, and it is
`docs/machine.md` §4's interrupt-latency table: a PS/2 host-to-device transmit masks
interrupts for **0.8–1.3 ms**, which at 115,200 baud is **9–15 byte times**. A 16-byte
FIFO absorbs 16. **The margin is one byte to seven**, and it is the same collision
`design-review.md` §IO-P4 found against the 6551's 521 µs deadline — one part further
along.

> **The driver must therefore treat a short read as a link fault and resynchronise**,
> not as a retry-the-sector. ⚠ **And a keyboard LED update during a DriveWire transfer
> is a real risk on this machine**, not a theoretical one. The cheap mitigation is a
> software rule — the `dwio` driver holds off PS/2 host-to-device traffic for the
> duration of a sector, 24 ms — and it is stated here because no hardware fixes it.

---

## 3. Throughput, and the part that decides it

A `OP_READEX` sector is **261 bytes on the wire in one direction and 6 in the other**,
plus one host turnaround. At 8N1 a byte is 10 bit times.

| Baud | Byte time | 256-byte sector | **Sustained** | vs `sdcard.md`'s 681 KiB/s |
|---|---|---|---|---|
| **19,200** — `serial.md` §3.1's 6551 today | 521 µs | **145 ms** | **1.8 KiB/s** | 388× slower |
| 38,400 | 260 µs | 72 ms | 3.5 KiB/s | 194× |
| **115,200** — §4.5's `16C550`, tier 1 | 86.8 µs | **24 ms** | **11.0 KiB/s** | **62×** |
| 230,400 — what a CoCo 3 runs | 43.4 µs | 12 ms | 22.0 KiB/s | 31× |

**The CPU cost is the other half and it is where the 6551 really fails.** With no FIFO
the 6551 takes one interrupt per byte; at `machine.md` §5 item 2's pessimistic 400-cycle
dispatch that is 400 cycles per 521 µs, which is **37 % of the machine** for one
direction of a 19,200-baud link that is already too slow to be useful.

| | ICs | interrupts per sector | CPU during a transfer, at 400 cycles |
|---|---|---|---|
| **6551 @ 19,200** | 3 | 261 | **37 %**, for 1.8 KiB/s |
| **`16C550` @ 115,200**, FIFO trigger 14 | **4** | **19** | **~16 %**, for 11.0 KiB/s |
| `16C550` @ 230,400 | 4 | 19 | ~31 %, for 22.0 KiB/s |
| `16C550` + `serial.md` §5.4 tier 2's ring | ~9 | **1** | ~2 % |

> ⭐ **This is the clearest case anywhere in the repository for
> `machine.md` §6's tier decision.** The `16C550` is **+1 IC** and it moves DriveWire
> from 1.8 KiB/s at 37 % of the CPU to 11.0 KiB/s at 16 % — a **6× throughput gain and
> a 2.3× cost reduction at the same time**, on the card the machine already has. Tier 2's
> ring buffer is not needed for DriveWire and should not be justified by it.

⚠ **230,400 baud is not free on the `16C550`.** It needs a `1.8432 MHz × 8` crystal or
the part's higher-speed grade, and `serial.md` §8's level shifter has to carry it —
an `MAX232`-class charge pump is specified to 120 kbit/s and 230,400 is above it.
**115,200 is the rate this document plans against**, and 230,400 is an experiment with
the driver stage understood, in the same posture `machine.md` §1.1 takes toward fast-E.

---

## 4. ⭐ The wall clock — the thing only DriveWire gives this machine

**This machine has no real-time clock.** Not on the motherboard (`hardware/ram.md` §6.7
lists every part on it), not on any of the five cards, and not in the CPU module — an
`STM32G431` has an RTC peripheral but no battery domain in
`cpu/docs/plan.md` §2.6's pinout and no crystal for it. **Every boot starts at an
unset date**, which NitrOS-9 handles but which makes every file timestamp meaningless
and every `make`-style dependency check wrong.

`OP_TIME` is one byte out and six back — **year−1900, month, day, hour, minute,
second** — and it costs **nothing but the driver call**. NitrOS-9's `setime` already
has a DriveWire path on the CoCo.

| Answer | Parts | Battery | Notes |
|---|---|---|---|
| **`OP_TIME`** | **0** | none | ⚠ needs the host link up. Right for a developer machine, useless standalone |
| A DS1307/DS3231 on the I/O card | 1 + crystal + cell | yes | ⚠ **I²C, and no card has an I²C master.** Bit-banged on spare port bits, or +1 more IC |
| The CPU module's own RTC | 0 | ⚠ **needs `VBAT` and a 32.768 kHz can**, neither of which `plan.md` §2.6 has pins for | would break the CoCo 3 drop-in SKU's pin budget |

**Recommendation: take `OP_TIME` now, because it is free, and record that the machine
still wants a standalone clock.** The boot ROM should ask for the time over DriveWire
if the link answers and leave the clock unset if it does not — which is exactly what
`OP_NOP` is for. §8 item 5.

---

## 5. The virtual channels, and what they are worth here

DriveWire multiplexes more than disks over the one link: `OP_SERREAD`/`OP_SERWRITE`
carry up to 15 virtual serial channels, which on a CoCo present as `/N0`–`/N13`
devices — a terminal, a printer, and a TCP socket the host opens on the machine's
behalf.

**On this machine the case is weaker than on a CoCo, and it is worth saying why**:

- **A terminal is not needed** — this machine has PS/2 and a 640×200 display of its
  own (`io/ps2/`, `video/`), and `graphics.md` §6.4.8's cell mode is a console at
  1 write per cell.
- **A printer is not needed** by anything.
- ⚠ **A TCP socket is genuinely tempting and it is the wrong answer here**, because
  `net/docs/net.md` is a real 10BASE-T card with a real stack problem
  (`net.md` §14.2 — nobody has looked for a NitrOS-9 network stack). A DriveWire
  socket would give the machine networking through the host for zero parts, and it
  would also be the thing that stops the net card ever getting written. **Recorded as
  available, not recommended.**

**What the channels *are* worth is `serial.md` §12's second port becoming unnecessary.**
That document notes *"a modem on one port and a DriveWire link on the other is a real
use"*; with virtual channels one physical port carries both. **One `16C550`, not two.**

---

## 6. Where the client lives — three of them, and they are different programs

This is the part `sdcard.md` §11.3 does not cover at all, and it is most of the work.

### 6.1 In the boot ROM — a bare-metal loader

**~1.5 KB of 6809, in page 0 of the boot ROM** (`machine.md` §7.2 — the ROM's first
8 KB is what `BOOT` mode makes visible). It initialises the `16C550`, does `OP_INIT`,
loads LSN 0 of drive 0 to a fixed address, and jumps.

⚠ **It runs before the map is written and therefore before there is any RAM**, so it
obeys the same constraint the rest of the boot ROM does (`ram.md` §6.4): the DRAM
controller and the map come up **first**, then this. It is not a stackless program; it
is a program that runs after the twenty stackless instructions that make a stack
possible.

**Its job is to load a NitrOS-9 boot file and nothing else.** Anything more belongs in
NitrOS-9.

### 6.2 In NitrOS-9 — the `dwio` low-level driver plus `RBF` descriptors

The real client: a `dwio`-equivalent supplying `OP_READEX`/`OP_WRITE` under a normal
`rbdw`-class `RBF` driver, with `/x0`–`/x3` descriptors. **This is where the port
question lives** — the CoCo's DriveWire drivers bit-bang the *bit-banger* port and time
the bits in software, and **none of that transfers**: this machine's link is a
`16C550` with a FIFO and an interrupt.

> ⚠ **So "NitrOS-9 already has DriveWire" is true and misleading.** What ports is the
> protocol layer and the `RBF` plumbing; what has to be rewritten is the byte layer,
> because the CoCo's is a software UART. It is a smaller job than writing a driver from
> nothing and a larger one than "it already exists". **Nobody has looked** — §8 item 1.

### 6.3 On the host — an existing program, unmodified

DriveWire 4 (Java) and `pyDriveWire` both serve the protocol over a serial port and
neither cares what is on the far end. **Nothing to write.** ⚠ Both expect the CoCo's
default 230,400; both are configurable, and §3 plans against 115,200.

---

## 7. Build order

Phased so each step is independently useful, and so the part decision comes first
because everything else is priced against it.

| # | Step | Exit criterion |
|---|---|---|
| **0** | **⭐ Decide `serial.md` §5.4's tier** — `machine.md` §6 has it open, and §3 above is the argument | the I/O card is 4 ICs with a `16C550`, or DriveWire is planned at 1.8 KiB/s and this document is mostly moot |
| 1 | **Get the DriveWire 4 protocol specification into [`reference/`](../reference/)** | §2's ⚠ table is read off a document rather than recalled |
| 2 | **Host end first, against a terminal emulator** | `pyDriveWire` answers an `OP_NOP` and an `OP_TIME` typed by hand |
| 3 | **§6.1's boot-ROM loader**, on the bench, with the ROM socketed | a 256-byte sector arrives, checksum matches, at 115,200 |
| 4 | **`OP_TIME` in the boot monitor** (§4) | the machine knows the date |
| 5 | **§6.2's NitrOS-9 driver** — the byte layer rewritten around the FIFO | `/x0` mounts a `.dsk` and `dir` works |
| 6 | **Measure the interrupt collision of §2.1** | a PS/2 LED update during a sector transfer, on a scope, with the failure either observed or bounded |
| 7 | The edit-compile-run loop closes | a binary cross-assembled on the host runs on the machine without touching a programmer |

---

## 8. Open items

1. **⚠ Does NitrOS-9's DriveWire client port to a FIFO UART?** §6.2. The protocol and
   `RBF` layers should; the byte layer is a software UART and will not. **The largest
   unknown in this document**, and the same shape as `serial.md` §13 item 2's `sc6551`
   question — which should be answered in the same sitting, because both are "read the
   NitrOS-9 source once".
2. **The protocol specification is not in `reference/`.** §2's opcode table is recalled.
   Build order step 1.
3. **⚠ The PS/2 interrupt collision of §2.1 is unmeasured** and the margin is one byte
   to seven. It shares a root cause with `design-review.md` §IO-P4 and
   `machine.md` §4's table; **all three want the same single measurement** of NitrOS-9's
   dispatch cost (`ps2.md` §14 item 3).
4. **230,400 baud needs a level shifter that carries it** (§3) and a crystal choice on
   the I/O card. Not planned for; recorded so the rate is not assumed.
5. **The machine still has no standalone clock** (§4). `OP_TIME` is free and is not an
   answer when the cable is out.
6. **Which drive numbers, and does `/x0` collide with `sdcard.md`'s naming?** Both cards
   want `RBF` devices and neither document names them. Trivial, and it will be a
   conflict at exactly the wrong moment if nobody writes it down.
7. **⚠ The virtual TCP socket of §5 would undercut `net/`.** Recorded as a decision
   somebody should make deliberately rather than discover.

---

## 9. Cross-references

| | |
|---|---|
| [`io/serial/docs/serial.md`](../io/serial/docs/serial.md) | §4.5 and §5.4 — the `16C550` this document depends on; §8 the level shifter; §12 the second-port question §5 answers |
| [`storage/docs/sdcard.md`](../storage/docs/sdcard.md) | §11.3, which priced DriveWire as a storage option and rejected it correctly; §12 step 0, which this document replaces |
| [`docs/machine.md`](machine.md) | §7.2 the boot ROM that ended the circularity; §4 the interrupt table §2.1 reads; §6 the open tier decision |
| [`hardware/ram.md`](../hardware/ram.md) | §6.4 the boot path, and §6.7 the ROM |
| [`io/ps2/docs/ps2.md`](../io/ps2/docs/ps2.md) | §7's host-to-device transmit, which is the hazard in §2.1 |
