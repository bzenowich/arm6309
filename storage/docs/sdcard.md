# Mass Storage for an arm6309 Machine
## An SD Card at 681 KiB/s, and the `TFM` Hazard It Stopped Having

**Question this answers:** the `$FF` map has reserved eight bytes for "a disk controller"
since [`graphics.md`](../../video/docs/graphics.md) §17, and nobody has ever said what that
controller is. [`machine.md`](../../docs/machine.md) §3 allocates every other byte in
the window. What goes in those eight, and how fast can a 6309 pull data through it?

**Short answer: a shift register, a self-resetting burst counter, and a block buffer the
host reads as memory.** The SPI engine is NormalLuser's BE6502 SD interface — **the read
strobe itself triggers the next 8-clock SPI burst** — so there is no software SPI anywhere
on the card; on a 6502 that alone gives 130 KiB/s through an unrolled `LDA`/`STA` loop.
Here the engine also fills a 2 KB SRAM by itself — 512 bursts per block, 326 µs, into one
of four buffers in the card's 64 KB region at `A20 = 1` (§3.5) — and the 6309 copies the
block out with **`TFM X+,Y+`** at three cycles a byte: **681 KiB/s sustained**, with the
SD card never waited on (§5.2). What a `CMD17` per block sees is far lower, because a
block does not begin until the card has found it — §5 and §9.1.1.

**⚠ The `TFM` hazard is retired, not mitigated — and that is a property of the design,
not a fix bolted onto it.** `TFM` is the 6309's only interruptible instruction, and on
resume it **re-reads the source address**. Against RAM that is idempotent. Against a port
whose read pops a byte, it silently loses one and shifts the rest of the block. This
card's block path never runs `TFM` against a port: the buffer is memory, and a re-read of
memory returns the same byte (§4). What still faces the port is §9.0's byte-at-a-time
initialisation and §9.2's write path — §4 states the hazard in full, because the write
path's mirror image of it is still open (§13 item 6).

**Constraints taken as given (yours):**
- **Parts available before 1990.** Programmable logic is in — GALs, and CPLDs where a GAL will not carry the design (root `README.md`).
- Same house rules as the other cards: period-honest silicon, one card, a documented
  register map, and an honest IC count.

**Units.** Every rate in this document is **KiB/s = 1024 bytes/s**, and is written `KiB/s`.
The headline figure in decimal is 681 KiB/s = **697 kB/s**. `modplayer.md` §4.4's
"~700 k writes/s" is decimal and is the *same* 3-cycle rate — 699,306 B/s = **683 KiB/s** —
so the two documents agree.

> ⚠ **One rule is broken here and cannot be argued back.** An SD card is **1999**. §10
> makes the case that the *circuit* is period-legal and only the *media* is not — the same
> status as the modern LCD on the video card's VGA output — but it is a real exception and
> it is the only one in the machine.

> Superseded material is archived in [history.md](history.md); this document describes
> only the present design.

---

## 0. Summary — the verdict in one table

| Question | Answer | § |
|---|---|---|
| **How is SPI generated?** | **A shift register and a self-resetting 8-clock burst counter.** No bit-banging, no SPI peripheral. | §3.1 |
| **Where do the bytes land?** | **In a 2 KB SRAM the host addresses as memory** — four 512-byte block buffers in the card's 64 KB region at `A20 = 1`. | §3.5, §6.5 |
| **What drives a block transfer?** | **A 9-bit address counter and a "fill" bit.** The host writes a command; the engine runs 512 bursts by itself and raises a status bit. | §3.5 |
| **What about `TFM`'s interrupt re-read?** | **Retired, not mitigated.** The host copies RAM → RAM, and a re-read of RAM is idempotent (§4.2). **No chunking, no masking.** | §4 |
| **Is `TFM` settled, then?** | **Not for the machine** — `SDDATA` is still a side-effecting port and §9.0's initialisation still uses it. But **no bulk transfer in this machine runs over a port**, so the silicon capture decides a single-byte question. | §4.5 |
| **Read rate, intra-block** | **681 KiB/s** — the unchunked `TFM`, which is the only kind. | §5.1 |
| **Read rate, sustained** | **681 KiB/s** with `CMD18` multi-block and double buffering: the SPI engine fills a buffer in 326 µs while the host copies the previous one in 735 µs, so **the host is the bottleneck and the card never waits on the SD card at all.** | §5.2 |
| **Write rate** | 681 KiB/s of *transfer*, but the card's program time bounds the sustained rate to **126–408 KiB/s**, and to **~63 KiB/s** for a 256-byte `RBF` sector that needs read-modify-write. | §5.3, §9.2, §9.4.1 |
| **Which cards?** | **SDHC/SDXC only.** Block addressing, fixed 512-byte blocks, no SDSC byte-address branch to get silently wrong. | §9.0 |
| **What happens on an error?** | R1 checked, error tokens decoded, three timeouts specified, card-change polled on the VBL tick. | §9.3 |
| **Address cost** | **Four bytes at `$FF58`–`$FF5B`, plus one 64 KB physical region at `A20 = 1`** of which 2 KB is used. | §6.1 |
| **IC count** | **14**, plus a 3.3 V regulator and the socket. | §8 |

**Net: 14 ICs**, against video's 30, audio's 29, net's 12, PS/2's 11 and serial's 3.

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

**Compatibility with fast-E (`machine.md` §1's ÷8 rate): passes, and easily.** The SPI
burst races nothing on the CPU side, because the engine fills the buffer autonomously and
the host reads SRAM. What constrains the card is `machine.md` §5 item 7's bus schedule,
which is a ÷12 schedule (§3.5); the tightest software margin, the six-byte command send,
is 3× at ÷12 and 2× at fast-E (§6.5). Every rate in this document is quoted at the
specified ÷12 `E` = 2.0979 MHz.

---

## 1. Sources and confidence

| Claim class | Source | Confidence |
|---|---|---|
| The read-triggers-next-burst topology; the self-resetting 8-clock generator; ~130 KB/s at 5 MHz (the source's own decimal figure; 127 KiB/s) | **NormalLuser, *BE6502 Fast SD Card Interface*** — <https://github.com/NormalLuser/BE6502-Fast-SD-Card-Interface> | **read directly**; a working, measured design |
| `TFM` has four forms including `TFM r0,r1+` (fixed source, incrementing destination); `W` holds the count; 3 cycles/byte | HD63B09EP Technical Reference Guide; this repo's own `plan.md` §4.3 and `modplayer.md` §4.4 | **corroborated**, and already load-bearing elsewhere in this project |
| **`TFM` is interruptible, uses a one-byte internal cache, and re-reads the source address on resume** | HD63B09EP Technical Reference; *A Memo on the Secret Features of 6309* | ⚠ **community documentation, not silicon. §13 item 1; §4's statement of the hazard and §9.2's write-path caveat rest on it.** |
| SD SPI mode: ≤400 kHz until initialised, then up to 25 MHz; ≥74 clocks with `CS` high at power-up; `FE` data token; 2 CRC bytes per block | SD Simplified Specification, recalled | ⚠ **no SD specification in `reference/` — §13 item 2** |
| Initialisation dialog: `CMD0` with `CS` low and CRC `$95`; `CMD8` with CRC `$87` and check-pattern echo; `ACMD41` with `HCS`; `CMD58`/`CCS`; `CMD16` for SDSC only | SD Simplified Specification, recalled | ⚠ §13 item 2 — **§9.0 is entirely recalled and must be re-derived from the spec** |
| Write protocol: `$FE` start token, 2 CRC bytes, data-response token `xxx00101`, then `DO` held low for the program time | SD Simplified Specification, recalled | ⚠ §13 item 2 |
| Timing ceilings: `N_CR` 0–8 byte times; read access `N_AC` typically 100 µs–1 ms, spec ceiling **100 ms**; single-block program time typically 250 µs–3 ms, spec ceiling **250 ms** | SD Simplified Specification, recalled | ⚠ §13 item 2 — **§5's sustained arithmetic is only as good as these** |
| `CMD18`/`CMD12` multi-block read; internal read-ahead makes the inter-block gap negligible | SD Simplified Specification, recalled; the mechanism CoCoSDC-class devices use to reach their sustained rates | ⚠ §13 item 2 |
| **The CPU is C11 firmware on an STM32G431, not silicon** | [`machine.md`](../../docs/machine.md) §0; [`plan.md`](../../cpu/docs/plan.md) | **certain** — and §4.3 and §11.6 turn entirely on it |
| SD card `V_OH` ≥ 0.75 × `V_DD` ≈ 2.48 V, clearing a `74HCT` input's 2.0 V `V_IH` | recalled | ⚠ §13 item 2 |
| NitrOS-9 interrupt dispatch cost | ⚠ guessed, as in `ps2.md` §3.1 and `serial.md` §5 | **unverified — the same measurement again** |

**`plan.md` §7's risk table already lists "`TFM` interruptibility subtleties" as needing
"dedicated vectors from silicon capture."** This card's write path is a second thing
depending on the answer, and moves it up the queue. §13 item 1.

---

## 2. What the machine needs from storage

| Need | Rate | Notes |
|---|---|---|
| Boot NitrOS-9 Level 2 | — | the machine's success criterion, inherited from `plan.md` |
| Load a program | as fast as possible | 30 KB in 44 ms at §5's rate |
| **Upload 128 KiB of mod samples** | the interesting one | `modplayer.md` §4.4 already streams these to the audio card with `TFM X+,Y` at 3 cycles a byte = **683 KiB/s**. Storage sustains **681 KiB/s** multi-block — the disk keeps pace with the audio card and is not the bottleneck. With a `CMD17` per block it is **253 KiB/s** and the disk is firmly the bottleneck again. §5.2, §9.1.1. |
| Stream audio or video off the media | sustained | possible, with the §9.1.1 caveat |
| Removable media a modern host can also write | — | which is the whole reason this is not a floppy controller |

That third row is the one that shaped this design. A floppy at 30.5 KiB/s (§11.2) turns a
128 KiB sample upload into a **4.2-second** wait; this turns it into **193 ms** — but only
with `CMD18`. The same upload issued as 256 separate `CMD17`s takes **505 ms**, more than
twice as long, for reasons that are nothing to do with the SPI clock. §5.2, §9.1.1.

---

## 3. The circuit

### 3.1 The idea, and where it comes from

NormalLuser's BE6502 interface does something better than fast bit-banging: **it removes
software from the SPI path entirely.**

```
 read strobe on SDDATA ──► trigger ──► burst counter: 8 clocks of SCK
                                          │
        SD DO (MISO) ──► SER  ┌───────────┴──► SRCLK
                              │ 74HCT595 (shift + storage)
                              │        RCLK ◄── burst complete
                              │
                     storage ─┴──► ~OE ◄── the same read strobe
                                    │
                                  D0-D7
```

Reading `SDDATA` does two things at once: it puts the byte from the **previous** burst on
the data bus, and it starts the burst that fetches the **next** one. Software never sees a
clock, never counts a bit, and never polls a busy flag in the fast path.

Two details from that design are worth taking verbatim:

- **The `'595`'s separate storage register**, again. It holds byte N stable on the bus while
  byte N+1 shifts in behind it — the same property `ps2.md` §4.1 borrows from the Minimal
  64x4 for the same reason. This is the third card in the machine built on it.
- **The burst counter self-resets.** NormalLuser wires a `'595`'s `QH` back to `SRCLR`, so
  shifting a single 1 through it produces exactly eight clocks and then clears itself — a
  counter, a terminal-count decode and a reset in one package.

> **This is the third time this project has used read-triggers-prefetch.**
> `audio.md` §9.3 (writing `AIDX` prefetches the state file so `ADATA` never stalls) and
> `ps2.md` §4.1 (the `'595` storage register) are the same move. It is the machine's house
> pattern for "make the bus read free".

### 3.2 What changes on a 6309

**Drop the VIA.** NormalLuser reaches the shift register through a 6522's Port A because a
6522 was already on the Ben Eater board — the design is visibly shaped by what was free
("unused gates repurposed from the VGA interface"). We put the `'595`'s three-state output
straight onto the buffer's local data bus (§3.5), and save the VIA's sixteen addresses,
which §6.1 shows we do not have.

**And then the instruction changes everything.** The 6502 needs an unrolled `LDA`/`STA`
loop, 10–12 cycles a byte. The 6309 has **`TFM`** — a block move at 3 cycles a byte, one
instruction for "move this block". `modplayer.md` §4.4 streams samples *to* the audio card
with the fixed-destination form `TFM X+,Y` at exactly that rate — **683 KiB/s**, which
`modplayer.md` quotes decimally as "~700 k writes/s". This card's block copy is
`TFM X+,Y+` out of §3.5's buffer (§4.5, §5.1). §4 is about why the obvious alternative —
`TFM X,Y+`, with the data port itself as the fixed source — is the one form this machine
must never use for bulk data.

### 3.3 The clock budget

The backplane carries the 25.175 MHz system master (`machine.md` §2, "the master lets any
card phase-lock to video"), so the card needs no oscillator of its own.

| | |
|---|---|
| Transfer clock | 25.175 / 2 = **12.588 MHz** — inside SD's 25 MHz ceiling with margin |
| One 8-clock burst | **636 ns** |
| Engine fill, 512 bursts | **326 µs** per block (§3.5) |
| Host copy, `TFM X+,Y+` at ÷12 `E` | 3 `E` cycles/byte = 1430 ns → **735 µs** per block |
| Init clock | 25.175 / 64 = **393 kHz** — inside SD's 400 kHz init ceiling |
| One burst at init speed | 20.4 µs = 43 `E` cycles — **must be polled**, §6.3 |

**The engine fills a buffer 2.25× faster than the host empties one**, which is what makes
§5.2's double buffering work. The tightest software margin at speed is not a block
transfer at all but the six-byte command send — a 3× margin, §6.5. There is no `/WAIT`
path, no FIFO, and no busy-polling in the fast path. The `÷2`/`÷64` selection is one
control bit and one divider package.

**The `'393` is a ripple counter**, and its `÷2` and `÷64` taps are therefore in no fixed
phase relationship with one another. Switching the speed-select bit muxes between two
asynchronous clocks and can emit a **runt `SCK` pulse** — a clock edge the card sees but
does not resolve, after which the host and the card disagree about the bit position for the
rest of the session, silently. **Rule: change the `SCK` rate only with `/CS` high and `BUSY` low**,
and follow the change with eight dummy clocks (one `SDDATA` read) before asserting `/CS`.
§9.0 step 8 is the only place in the machine that does this.

### 3.4 Two bus-level checks that pass

Both are the sort of thing that kills a side-effecting I/O port quietly, so they are
recorded even though the answer is "fine".

**Phantom reads.** A 6809/6309 emits *dummy* bus cycles — the `VMA`-equivalent dead cycles
inside indexed addressing, `TFR`/`EXG`, and the stacking sequences — and on this family
those cycles **drive `$FFFF`**, not the last address and not a partially-formed effective
address. Vector fetches drive `$FFF0`–`$FFFF`. Both are outside the `$FF00`–`$FF7F`
geographic window (§6.1), so **no dummy cycle can ever land on `SDDATA` and pop a byte.**
This is the classic way a read-triggered port dies on a 6502 or 6809 bus and it is worth one
paragraph to say it was checked and is absent.

> **This is a requirement on the CPU firmware, not just an observation about silicon.**
> The 6309 here is C11 on an STM32 (§1). If the emulator's dead cycles were to drive the
> operand address, or simply hold the previous address, a dead cycle inside an indexed
> instruction that happened to reference `$FF58` would pop a byte and shift the stream —
> §4's failure mode arriving by a different door. **The core must drive `$FFFF` on every
> dead cycle.** §12 step 1 checks it in the same capture.

**Burst versus read strobe.** The burst is triggered by the read strobe and the `'595`'s
storage register is what gets read, so the byte presented is stable for the whole cycle
regardless of what the shift register is doing behind it. The `RCLK` that latches the
next byte fires at the *end* of the burst, 636 ns later, long after the strobe has gone
away. There is no window in which a read returns a half-shifted byte.

### 3.5 The block buffer, and the engine that fills it

| | |
|---|---|
| **The buffer** | a `6116`, 2K×8, 55 ns — **four 512-byte block buffers** |
| **Where** | the card's 64 KB region at `A20 = 1`, offsets `$0000`–`$07FF`. `machine.md` §5 item 7: sixteen regions of 64 KB, selected by physical `A19`–`A16` against a four-position jumper, **qualified by `/IOPAGE` high** |
| **What fills it** | a **`74HC4040` 9-bit address counter** and a `FILL` bit in `SDCTRL`. Setting `FILL` makes the burst engine self-trigger: byte, `/WE`, increment, repeat, 512 times, then clear `FILL` and set `DONE` |
| **The address mux** | three `74HC157`s. With `FILL` low they select backplane `A8`–`A0` always; with `FILL` high the select follows `machine.md` §5 item 7's phase schedule — the engine's counter in its ticks 0–1 slot, the backplane in the host's window — **so the host reads the buffer as memory even while a fill runs** |
| **The data path** | one `74HCT245` between the backplane `D0`–`D7` and the buffer's data bus. The `'595`'s outputs are on that local bus, not the slot bus |

**The engine is 326 µs per block and the host is 735 µs**, so with two of the four buffers
in flight the SD card is never the bottleneck (§5.2): the engine's fill rate and the
host's copy rate never compete for the same bus.

**Bus arbitration is `machine.md` §5 item 7's fixed schedule and it costs this card
nothing.** The host owns the buffer in ticks 7–11 of each bus cycle; the engine takes
ticks 0–1. The engine needs a byte per 636 ns and gets one per 476.7 ns, and its byte
survives the deferral in the `'595`'s storage register — **which already exists for
§3.4's reason** and earns its keep twice.

> ⚠ **The `'595` is doing two jobs and neither faces the slot bus.** In the BE6502
> original — and in any single-glance reading of §3.1's diagram — its three-state output
> drives the host data bus; here it drives the buffer's local bus, and its `/OE` is the
> engine's write window rather than a bus-read decode. **This is the single most likely
> place to get the build wrong**, because the part is unchanged and its wiring is not.

---

## 4. The `TFM` hazard, and how this card stopped having one

> ⚠ **Retired, not mitigated.** The hazard below is real; this card's block path simply
> does not face it, because the block copy is RAM to RAM (§4.5). §§4.1–4.3 state the
> problem in full: `net/docs/net.md` §3.2 cites them, §9.2's write path still faces the
> hazard's mirror image, and `machine.md` §6 keeps the silicon capture as a `cpu`-owned
> item.

### 4.1 What `TFM` does when interrupted

`TFM` is the only interruptible instruction on the 6309. It moves one byte at a time
through a **one-byte internal cache**, and interrupts are recognised between bytes. The
documented behaviour on resume is that **if the cached byte was destroyed, `TFM` re-reads
the source address to get it back.**

For an ordinary RAM source that is invisible — re-reading RAM returns the same byte.

### 4.2 Why `modplayer.md`'s `TFM` is safe and a port-source `TFM` is not

The asymmetry is exact, and it is easy to miss because both look like "a `TFM` against an
I/O port":

| | `TFM X+,Y` — `modplayer.md` §4.4 | `TFM X,Y+` — a port-source block read |
|---|---|---|
| Source | **RAM**, incrementing | **the port**, fixed |
| Destination | the port, fixed | RAM, incrementing |
| What re-reading the source does | returns the same RAM byte | **pops a byte and arms the next burst** |
| Result of an interrupt mid-instruction | nothing | **byte lost; the rest of the block shifts by one** |

The audio card's upload path is safe *because* it is the fixed-destination form. Invert the
direction and the safety inverts with it — which is why this card's block path reads a
buffer (§4.5) and not the port.

**And the failure is silent.** There is no error bit; the block simply contains the wrong
bytes from the interruption point onward, and the two CRC bytes at the end are read at the
wrong offset so they do not catch it either.

**How often?** A 512-byte `TFM` runs for 735 µs. Against the machine's interrupt load —
video VBL at 70 Hz, the replayer's `/FIRQ` at 50–102 Hz, plus PS/2 and serial, call it
~200/s — that is **0.15 expected hits per block. Roughly one block in seven.**

### 4.3 Hardware cannot fix this

Worth stating plainly, because the instinct is to design around it:

- **A "return the previous byte on re-read" rule is unimplementable.** A `TFM` resume read
  and a legitimate next read are the same bus cycle. The card cannot tell them apart.
- **Deepening the buffer does not help.** A FIFO read still pops.
- **Not triggering on read** kills `TFM` outright and drops the card to an `LDA`/`STA`
  rate.
- **A memory-mapped block buffer fixes it completely** — reads become non-side-effecting
  and `TFM X+,Y+` walks it with no hazard at all. It is the clean answer, **and it is the
  one taken**: §3.5 is the circuit, §11.1 records the decision.

The list above treats the 6309 as a fixed part, and **it is not one**: the CPU is C11
firmware on an STM32G431 (`machine.md` §0, `plan.md`), so the hazard can also be specified
*out of the CPU* — resume without re-reading the source. §11.6 prices that option; it is
the owner's call and this document does not make it.

### 4.4 Chunk-and-mask — retired from the read path, still the write path's discipline

Masking interrupts makes a `TFM` atomic; chunking keeps the masked window short. The
block *read* does not need this — its source is memory (§4.5). **§9.2 step 6's write
does**, pending §12 step 1's answer on doubled writes, and it is the only place in the
machine the technique survives:

```
        ldx   #buffer
        ldy   #SDDATA
        ldb   #16                  ; 16 chunks of 32
Chunk   orcc  #$50                 ; mask IRQ and FIRQ
        ldw   #32
        tfm   x+,y
        andcc #$AF                 ; unmask -- pending interrupts fire here
        decb
        bne   Chunk
```

**A masked `/FIRQ` is delayed, not lost**, so the replayer tick survives: 49 µs of latency
against `modplayer.md`'s 20 ms tick period is 0.25 %, and the tick's own work is ~2,200
cycles of a 41,960-cycle budget. The choice of chunk size is a straight trade:

| Chunk | cyc/byte | KiB/s | Interrupt latency added |
|---|---|---|---|
| 16 B | 4.62 | 443 | 26 µs |
| **32 B** | **3.81** | **537** | **49 µs** |
| 64 B | 3.41 | 601 | 94 µs |
| 512 B (unchunked) | 3.01 | 680 | **735 µs — and, against a port, one block in seven corrupt** |

**Specify 32.** 49 µs is below anything else in the machine that cares, and `machine.md`
§4's interrupt-latency table carries it. These are *intra-block* figures — what a `TFM`
loop achieves once the transfer is under way; the unchunked 3.01-cycle row is the read
path's rate (§5.1), reached without masking because the source is memory.

> **With the masking in place the write path is safe whatever §12 step 1's capture says;
> what the capture decides is whether the masking can come out.** And its answer is an
> input to an implementation choice (§11.6), not a constraint handed down by silicon.
> Three outcomes, not two: silicon re-reads and we match it (the write path stays
> chunked); silicon does not re-read (the masking goes, for free); silicon re-reads and we
> deliberately diverge (the masking goes, and a divergence goes in the ledger `machine.md`
> §5 item 6 keeps). **Measure before writing the driver, not after** — §12 step 1.

### 4.5 The block path: RAM to RAM

The hazard was never about `TFM`. It was about **a port whose read has a side effect**,
and §4.2 already contains the answer: against RAM, a re-read is idempotent. §3.5's buffer
is RAM. The block read is

```
        ldx   #buffer_in_card    ; the card's block buffer, mapped through the MMU
        ldy   #dest
        ldw   #512
        tfm   x+,y+              ; no masking, no chunking, no 21 %
```

and an interrupt landing anywhere inside it re-reads a memory location and gets the same
byte back. **The unchunked copy is 21 % faster than the chunked one** — 681 KiB/s against
537 (§4.4's table, §5.1).

**Three things this does not do:**

1. **It does not settle `TFM` for the machine.** `SDDATA` (§6.2) is still a read-triggered
   port and §9.0's initialisation drives the card through it a byte at a time.
   Single-byte reads are not `TFM` loops, so the exposure is gone in practice — but
   `machine.md` §6's capture is still owed, and §11.6's option to specify the hazard out
   of the CPU is still on the table for its own reasons.
2. **It does not remove the phantom-read requirement.** §3.4's rule — the core drives
   `$FFFF` on every dead cycle — still protects `SDDATA`. The buffer does not need it.
3. **It does not help the write path.** §9.2 still pushes 512 bytes out through the port…
   ⚠ **and it should not have to.** The buffer is bidirectional and the engine can drain
   it as easily as fill it; `SDCTRL` would need a direction bit and the write path becomes
   symmetric. **This document specifies the read path against the buffer and leaves the
   write path on the port**, which is an inconsistency, not a design — §13 item 6.

---

## 5. Transfer rates

Three different numbers get called "the rate" — and two of them are the same number,
which is the clearest sign the buffer is the right shape.

### 5.1 The intra-block ceiling

**681 KiB/s.** A `TFM X+,Y+` of 512 bytes from the card's buffer into system RAM, at
3.01 cycles/byte against `E` = 2.0979 MHz: 735 µs a block.

**Nothing about the SPI side sets this number.** The engine fills the buffer on its own
clock and the host reads memory; the two rates never compete, which is what §5.2 is about.

### 5.2 Sustained read: the host, and nothing else

| | per 512-byte block | |
|---|---|---|
| SPI engine fills a buffer | **326 µs** | 512 × 636 ns |
| host copies a buffer | **735 µs** | 512 × 1435 ns |
| **sustained, `CMD18` + double buffering** | **735 µs → 681 KiB/s** | **the host is the bottleneck** |

**With four buffers (§3.5) and `CMD18` READ_MULTIPLE_BLOCK, the SD card is never waited
on.** It streams into buffer *n+1* while the host copies buffer *n*, and it finishes
2.25× before the host does.

**`CMD18` is still what makes the number real.** A `CMD17` per block pays the card's
~1 ms read-access latency 256 times per 128 KiB instead of once, and no amount of
buffering hides a command that has not been sent: **253 KiB/s** — §9.1.1.

**128 KiB of mod samples** arrive in **193 ms**, against the 187 ms the audio card needs
to swallow them (`modplayer.md`) — a 6 ms gap.

### 5.3 Sustained write: the program time, not the clock, is the story

The bound is not the transfer: the card holds `DO` low while it programs, and §9.2's busy
phase is what sets **126–408 KiB/s**. The transfer half is 681 KiB/s, which is not the
story.

⚠ **The write path is still on the port** (§4.5 item 3), so it still pays §4.4's masking
tax in the form the buffer exists to delete — §13 item 6.

---

## 6. Register map

### 6.1 Placement — four bytes, and one region

**`$FF58`–`$FF5B`, four bytes**, from the eight `graphics.md` §17 reserved for a disk
controller — **plus one 64 KB physical region at `A20 = 1`** (`machine.md` §5 item 7), of
which this card uses 2 KB.

| Window | Size | Owner |
|---|---|---|
| `$FF00`–`$FF3F` | 64 | *free* |
| `$FF40`–`$FF4F` | 16 | audio |
| `$FF50`–`$FF53` | 4 | PS/2 |
| `$FF54`–`$FF57` | 4 | serial |
| **`$FF58`–`$FF5B`** | **4** | **storage — this document** |
| `$FF5C`–`$FF5F` | 4 | net |
| `$FF60`–`$FF7F` | 32 | video |

An SPI port needs four registers where the WD1773 the reservation was sized for needs five
plus a latch, so half the eight-byte reservation went spare; `net/docs/net.md` §5.1 holds
it. The geographic decode is `$FF00`–`$FF7F`.

> ⚠ **Two consequences for this card, and the first one is a bug if it is missed.**
>
> - **The decode is `A0`–`A6`, seven bits.** `A6` is not in the window strobe, so a card
>   matching only `A0`–`A5` answers at `$FF58` **and** at `$FF18`.
> - **The region base is a second jumper**, four positions against physical `A19`–`A16`,
>   and the region decode is qualified by **`/IOPAGE` high** — a buffer is a
>   physical-memory decode and `machine.md` §2's rule is not optional for it. ⭐ `/IOPAGE`
>   also silences the card above 2 MB, for nothing: the map is 32 MB and `A21`–`A24`
>   never leave the motherboard — `machine.md` §2.

### 6.2 The registers

| Off | Name | R/W | Function |
|---|---|---|---|
| `+$0` | `SDDATA` | R | the byte from the **previous** burst; **the read triggers the next** |
| `+$0` | `SDDATA` | W | load the MOSI hold register **and** trigger a burst |
| `+$1` | `SDSTAT` | R | §6.3 |
| `+$2` | `SDCTRL` | W | b0 `/CS`, b1 clock rate, **b2 `FILL`**, **b3 `BUF[1:0]` low**, **b4 `BUF[1:0]` high**, b7 soft reset. **`$00` is the safe state and is what `/RESET` forces** — §6.4 |
| `+$3` | `SDMOSI` | W | load the MOSI hold register *without* triggering a burst |

**`SDDATA` is the slow path**, used by §9.0's initialisation and §9.1's command phase —
the six command bytes, the R1 response, the data token poll. It is never used for a
512-byte transfer, which is why §4's hazard does not reach it.

**`FILL` is the whole engine.** Writing it with `BUF` selecting one of the four 512-byte
buffers (§3.5) starts the block: the burst engine self-triggers, the `'4040` counts, and
512 bytes land in the buffer. `FILL` self-clears at terminal count and `SDSTAT` bit 3
goes high.

> ⚠ **`FILL` must not be set with `/CS` high or the clock at 393 kHz.** At init speed a
> block is 20.4 ms of engine occupancy, and `DONE` does not arrive until it ends. The GAL
> qualifies `FILL` on the fast-clock bit; **that is one product term and it is not
> optional**, because the failure is a card that appears to hang.

**The MOSI hold register persists.** Every burst parallel-loads the `'165` from it, so
software writes `$FF` once before a block read and every burst clocks `$FF` out, which is
what SD requires of a host that is receiving. Writing `SDDATA` again changes it — that is
how commands are sent. **The `'574`'s clock edge must lead the `'165`'s parallel load**, so
the load is taken from the burst's own first clock rather than from the write strobe;
otherwise a write to `SDDATA` shifts out the *previous* hold value.

**`SDMOSI` at `+$3` is the clean primitive** — a way to set MOSI without consuming a byte
time. Two places need it:

- **Power-up.** The `'574` has no clear input, so at power-up the hold register contains
  garbage and the very first burst would clock garbage onto `DI` — precisely what the
  74-clock power-up sequence must not do. `SDMOSI` sets `DI` = `$FF` before any clock
  exists. §6.4.
- **Turning the line around.** Going from "sending a command" to "receiving a response"
  is a pure change of what `DI` carries, not a transfer; with `SDMOSI` it costs no burst
  and cannot disturb the receive pipeline's off-by-one.

### 6.3 `SDSTAT`

| Bit | Name | Meaning |
|---|---|---|
| 0 | `BUSY` | a burst is in progress. **Only meaningful at init speed** — §3.3 |
| 1 | `CD` | card detect, from the socket's mechanical switch |
| 2 | `WP` | write protect, likewise |
| **3** | **`DONE`** | **a `FILL` block finished; the buffer `BUF` named is complete** (latched, cleared by the next `FILL`) |
| 4–7 | — | read 0 |

`BUSY` exists for the 393 kHz init path, where a burst is 20.4 µs — 43 bus cycles — and
must be polled. **In the command path it is never read at speed**, because a 636 ns burst
finishes long before the next bus cycle can ask for another byte.

**`DONE` is what the block path polls**, and a 512-byte fill is 326 µs — 684 bus cycles —
so it is polled, not raced. ⚠ **A driver that polls `DONE` in a tight loop wastes the
326 µs the buffer exists to overlap**: the point of four buffers is to start the next
`FILL` and copy the previous one, and only then look at `DONE`. §5.2.

> **`DONE` is deliberately not an interrupt.** `machine.md` §4's `/IRQ` already carries
> five sources and §4.1's polling order is already correctness-constrained; a sixth
> source for an event the driver is about to poll anyway would cost a backplane wire, a
> GAL macrocell this card has not got (§8), and a line in that order. **The card polls;
> the hardware does not shout** — the same call this section already makes for `CD`.

`CD` and `WP` are mechanical switch inputs and are **not** interrupt sources. There is no
card-change interrupt and this document does not propose one: it would cost a GAL macrocell
the card does not have (§8), a wire on the backplane, and an entry in `machine.md` §4's
shared-`/IRQ` ownership and in that handler's polling order — and a 14.3 ms `VBL` poll
(§9.3) already beats any human hand by three orders of magnitude. The driver polls; the
hardware does not shout.

### 6.4 Power-up and `/RESET` state

The card has state that survives nothing and state that survives everything.

| Element | Power-up | On backplane `/RESET` | Consequence |
|---|---|---|---|
| `SDCTRL` (GAL macrocells) | `$00` — a `GAL22V10`'s registers power up reset | **forced to `$00`** | `/CS` **high**, **init clock** selected. Both are the safe state, which is why b0 and b1 are defined active-high in §6.2 |
| Burst counter (`'163`), `BUSY` | cleared by the same `/RESET` term | cleared | no burst can be in flight across a reset |
| **MOSI hold register (`'574`)** | ⚠ **garbage — the `'574` has no clear input** | ⚠ **still garbage** | `DI` is undefined until software writes it. **This is why §9.0 step 1 is a write, not a read.** |
| `'595` receive storage | garbage | garbage | harmless; the first byte read after any command is discarded by the protocol anyway |

**The `'574` is the one that matters.** SD's power-up sequence requires ≥74 clocks with
`CS` **and `DI` both high**; a card that sees `DI` low during those clocks may interpret the
pattern as the start of a command and fail to enter SPI mode. Ten bare `SDDATA` reads
would clock 80 bits of whatever the `'574` powered up holding onto `DI` — which is why
§9.0 writes `SDMOSI` ← `$FF` first, then reads.

Adding a clear to the `'574` was considered and rejected: the `'574` is a clocked octal
register with no `MR` pin, so it would have to become a `'273`, which has no three-state
output — irrelevant here, since the hold register never drives the bus — but the swap buys
nothing that one instruction does not.

### 6.5 Re-triggering during a burst

**Specified: the trigger is locked out while `BUSY` is high.** `BUSY` is a registered GAL
macrocell, set by the trigger term and cleared by the `'163`'s terminal count; the trigger
term is qualified with `/BUSY`. **Cost: one input on an existing product term, zero
macrocells.**

What lockout does and does not buy:

- **It prevents the hardware failure.** Without it, an `SDDATA` access mid-burst reloads
  the `'163` mid-count and truncates the burst to fewer than eight clocks. Host and card
  then disagree about the bit position for the rest of the session, and **every subsequent
  byte is wrong** — the worst failure on the card, because it is permanent and silent.
- **It does not prevent the software failure.** A locked-out read still returns the `'595`'s
  current contents, which is the *previous* byte again. The stream gains a duplicate rather
  than losing a byte, and the block still shifts. Lockout converts an unrecoverable framing
  error into an ordinary off-by-one.

So the software rule stands and is stronger than §6.3's:

- **At init speed (393 kHz), poll `BUSY` before *every* `SDDATA` access.** A burst is
  20.4 µs = 43 bus cycles; nothing in software is that slow by accident.
- **At full speed no access can overlap**, and the tightest case is the six-byte command
  send: a native-mode `STA >SDDATA` is 4–5 cycles = 1.9–2.4 µs against a 0.636 µs burst —
  a 3× margin, the smallest on the card, and the reason §9.0 never sends commands with
  `TFM`.

> **Recorded alternative: defer the trigger instead of dropping it.** A pending-trigger
> flip-flop would make a mid-burst access queue a second burst rather than lose one, which
> is strictly better behaviour. **It costs one macrocell**; it arrives with §8.1's 8-IC
> version, if that version happens.

### 6.6 The MOSI hold-time race on the shared `SCK` edge

**Recorded as a risk, not designed out.** In SPI mode 0 the card **samples `DI` on `SCK`'s
rising edge**. If the `'165`'s `SRCLK` is that same rising edge, `DI` changes and is sampled
at the same instant, and correctness rests on the `'165`'s **minimum** propagation delay
exceeding the card's input hold time `t_IH`.

**HC datasheets specify maximum propagation delays only.** A minimum is not guaranteed, and
"it is obviously several nanoseconds" is an argument from physics, not from a datasheet.
`t_IH` for an SD card is a few nanoseconds, and this is the arrangement NormalLuser's board
runs at 130 KiB/s without trouble (§1), so the risk is real but small.

**The robust alternative is to clock the `'165` on the *inverted* `SCK`**, so `DI` changes
on the falling edge and is stable for a full half-period — 39.7 ns at 12.588 MHz — before
the card samples it. That is what a mode-0 master does, and it turns an unspecified margin
into a specified one.

**It costs one gate the card does not have.** The `'574` is eight bits fully used; the
`'393`'s outputs are counter taps, not spare inverters; the `'125`'s fourth gate is a
non-inverting buffer; and the GALs are full (§8). The candidates are therefore:

| Source of the inverter | Cost |
|---|---|
| A GAL macrocell, emitting both polarities of the gated burst clock | **1 macrocell** — available only if §8's overflow moves `SDCTRL` to a `'574` and frees four. **This is the first claim on those four.** |
| A 15th package (`74HC04`) | **1 IC** |
| Leave it | zero, and §12 step 3 measures whether it matters |

§13 item 9. §12 step 3 is where it gets decided, on the bench, with a scope on `DI`.

---

## 7. The 3.3 V domain

SD cards are 3.3 V and **not 5 V tolerant**. The machine is 5 V TTL throughout, so this
card carries the only level-shifted domain in it.

| Direction | Signals | Part |
|---|---|---|
| 5 V → 3.3 V | `SCK`, `MOSI`, `/CS` | **`74LVC125`** at 3.3 V — LVC inputs are 5 V tolerant. 3 gates of 4. |
| 3.3 V → 5 V | `MISO` | **nothing** — the card's `V_OH` ≥ 0.75 × `V_DD` ≈ 2.48 V clears a `74HCT` input's 2.0 V `V_IH`. **This is why the receive shift register is `74HCT595` and not `74HC595`.** |
| supply | — | a +5 V → +3.3 V LDO, 500 mA, with bulk capacitance |

The `HC`-versus-`HCT` point is the same one `ps2.md` §4.2 takes from the Minimal 64x4, for
the same reason and with the same consequence if ignored: an `HC` input wants 3.5 V and
will read a valid 3.3 V high as indeterminate.

> **Size the regulator for writes, not reads.** SD cards draw far more current while
> programming than while reading, and in bursts. An undersized LDO or thin bulk
> capacitance produces a card that reads perfectly and corrupts writes — §13 item 5.
>
> **That programming phase is §9.2 step 9's busy phase**, and §5.3 puts a clock on it:
> 250 µs to several ms per block, 250 ms by the specification. This section and §5.3 are
> the same fact seen from two sides — the current the regulator must supply, and the time
> the driver must wait.

---

## 8. Chip budget

| # | Part | Function |
|---|---|---|
| 1 | **74HCT595** | MISO shift + storage; three-state onto **the buffer's local data bus** — §3.5, not the slot bus |
| 2 | 74HC165 | MOSI shift, parallel-loaded from the hold register at each burst |
| 3 | 74HC574 | MOSI hold register — §6.2's persistence |
| 4 | 74HC163 | burst counter: eight clocks, terminal count drives `RCLK` and clears `BUSY` |
| 5 | 74HC393 | clock divider, `÷2` and `÷64` taps off the 25.175 MHz master |
| 6 | 74LVC125 | 3.3 V level shift for `SCK`, `MOSI`, `/CS` |
| 7 | **6116** 2K×8, 55 ns | **the block buffer — four 512-byte buffers.** §3.5 |
| 8 | **74HC4040** | **the fill engine's 9-bit block address counter** |
| 9–11 | **74HC157** ×3 | **address mux: the counter during the engine's slot, backplane `A8`–`A0` otherwise** |
| 12 | **74HCT245** | **backplane `D7`–`D0` ↔ the buffer's local data bus** |
| 13 | **GAL22V10** ×2 | decode from `/IOSEL` **and** the `A20 = 1` region; `SDCTRL` including `FILL`/`BUF`; `SDSTAT`; the burst trigger; the `machine.md` §5 item 7 bus phase |

**Total: 14.** Plus a 3.3 V LDO, an SD socket, and passives. (The rows number 1–13
because two of them carry more than one package — count footprints, not rows;
`hardware/place/parts.ts` asserts the 14.)

> ⚠ **Seven of the fourteen packages are the buffer, and it is worth being blunt about
> what they buy**: §3.5 — 29 % more sustained throughput than a chunked port path, and
> the deletion of §4's hazard from the read path — for seven packages, **six of which are
> address and data plumbing**. The card is the machine's third largest. Whether that is a
> good trade is a judgement, and this document's is that a card whose correctness rested
> on an undocumented CPU behaviour was not a card to keep for the sake of six packages.

### 8.1 Two GALs, and the one-package alternative that is not taken

The card's logic does not fit one `GAL22V10`. The decode from `/IOSEL`, the burst trigger,
`SDCTRL` and `SDSTAT` were already roughly ten macrocells of a `GAL22V10`'s ten; add the
region compare (`A19`–`A16` against a jumper, plus `A20`, `A15`, `/IOPAGE`), the
`FILL`/`BUF` control bits, the `'157` select, the `'4040` clock and clear, the `'245`
enable and direction, and `machine.md` §5 item 7's two-tick engine window. **That is not a
fit; it is a second part**, and §8 row 13 is budgeted as two.

> **One `ATF1508AS` absorbs both GALs, the `'4040` and the three `'157`s** — the counter
> is 9 macrocells, the mux is 9 more, and the part has 128 with 60 I/O. The card would be
> **8 ICs**: `'595`, `'165`, `'574`, `'163`, `'393`, `'LVC125`, `6116`, CPLD. Cheaper
> than 14, fewer things to get wrong, and in-circuit reprogrammable.
>
> **The no-CPLD house rule that once refused this is retired** (root
> [`README.md`](../../README.md)), so nothing blocks it — and **it is not taken**. What
> weighs:
>
> | For | Against |
> |---|---|
> | **8 ICs against 14** — six packages, all of them address and data plumbing | **~160 mA against two GALs' ~140–180 mA** — roughly a wash, not the saving CPLDs give on bigger cards |
> | one part to fit instead of two, and in-circuit reprogrammable over JTAG | ⚠ **fuse-level verification is lost.** `hardware/gal/jedec/` reads a `GAL22V10`'s fuse map back and executes it; prjbureau rates the ATF1508AS database *"Partial"* and its programming path *"Untested"* (`graphics.md` §10.1.6) |
> | the same decision video, audio and net all reached | this card is the only one whose logic **fits two GALs comfortably**. The others took CPLDs because a GAL could not carry them |
>
> **That last row is the real argument against**, and it is not a rule — it is that a
> CPLD here buys packages rather than capability, which is the weakest case for one in
> the machine. §13 item 12 carries the question.

**What the second GAL costs elsewhere**: nothing on the backplane, ~50 mA, and one more
part to program. **What it does not cost is the `74HC574` escape hatch** — §12 step 3's
"if `SDCTRL` does not fit, move it to a `'574`" would make the card 15, and with two
parts it should not be needed.

---

## 9. Software

`SDMOSI` (§6.2) is used throughout for "put a byte on `DI` without transferring". A card
built without that register does the same thing with a write to `SDDATA`, which costs one
extra byte time and is otherwise identical; every sequence below is annotated where the
difference matters.

### 9.0 Initialisation

**Everything in this section runs at the 393 kHz init clock**, with `BUSY` polled before
every `SDDATA` access (§6.5). The card is not clocked at 12.588 MHz until step 8 — SD's
init ceiling is 400 kHz, and a card commanded above it before initialisation completes is
in an undefined state.

```
 0. /RESET, or SDCTRL <- $00.  /CS high, init clock, no burst in flight.   -- 6.4
 1. SDMOSI <- $FF.             DI is now high, and no clock has been issued yet.
                               (No SDMOSI: SDDATA <- $FF, which is itself one burst.)
 2. Ten SDDATA reads with /CS high.  80 clocks >= the required 74, DI high throughout.
                               (No SDMOSI: nine reads; step 1's write was the tenth.)
 3. CMD0  GO_IDLE_STATE.   arg $00000000, CRC $95, WITH /CS LOW.
                           Expect R1 = $01 (idle). Retry to 10 attempts, then fail.
 4. CMD8  SEND_IF_COND.    arg $000001AA, CRC $87.
                           R1 = $01 plus a 4-byte R7 whose low 12 bits echo $1AA
                                                        -> v2.00+ card, continue.
                           R1 = $05 (illegal command)   -> v1.x card or MMC: REJECT, 9.0.1.
 5. ACMD41 loop:          CMD55 (arg 0), then ACMD41 with HCS=1 (arg $40000000),
                           until R1 = $00.  Timeout 1 s (70 VBL ticks).  -- 9.3
 6. CMD58 READ_OCR.        Check CCS, bit 30 of the 4-byte OCR.
                           CCS = 1 -> SDHC/SDXC, block addressing.  Continue.
                           CCS = 0 -> SDSC, byte addressing.        REJECT, 9.0.1.
 7. CMD16 is NOT sent.     SDHC block length is fixed at 512 and cannot be changed.
 8. SDMOSI <- $FF; /CS high; one SDDATA read (8 idle clocks); SDCTRL b1 <- 1 (fast
    clock); one more SDDATA read.  Only then /CS low for the first real command.
                           -- 3.3: the '393 is a ripple counter and the speed bit may
                              only change with /CS high, or a runt SCK results.
```

**The two CRCs are hard-coded constants.** There is no CRC7 generator on this card and none
is needed: SPI mode ignores the command CRC except for `CMD0` (which is issued before the
card knows it is in SPI mode) and `CMD8` (whose CRC the spec makes mandatory). `$95` and
`$87` are those two constants, correct for those two argument values and no others; every
other command ships `$01` (CRC field zero, stop bit set) or `$FF`. Likewise the two CRC16
bytes after a data block are sent as `$FF $FF` and ignored by the card, because CRC checking
is off unless `CMD59` turns it on and this driver never does. **Two bytes of table, no
logic** — but it must be written down, because a driver author who does not know this will
either go looking for the CRC hardware or send zeros to `CMD0` and never get past step 3.

#### 9.0.1 The card class decision: **SDHC/SDXC only**

**Decided: the driver requires `CCS` = 1 and refuses anything else at step 6.**

| | SDHC/SDXC (`CCS` = 1) | SDSC (`CCS` = 0) |
|---|---|---|
| `CMD17`/`CMD18`/`CMD24`/`CMD25` argument | **block number** | byte address = block × 512 |
| Block length | fixed 512 | set by `CMD16` |
| Capacity | 4 GB–2 TB | ≤ 2 GB |

**Why require one class rather than support both.** The branch is a multiply by 512 in one
direction and not the other, and **getting it wrong does not fail — it reads the wrong
sector.** That is the same class of defect as §4's shifted block and §9.1's off-by-one:
silent, data-destroying, and invisible to any test that runs on the card the author happened
to have in the socket. A branch that is exercised only when someone inserts the other kind of
card is a branch that will be wrong when it finally runs. Deleting it is worth more than the
twenty bytes it costs.

**Why SDHC is the right one to keep.** SDSC is ≤2 GB and is now the *harder* card to buy;
SDHC 4–32 GB is ordinary stock and is what §13 item 3's known-good-card entry was always
going to name. The rejection is clean — the driver reports no media and says why — rather
than a corrupt filesystem. And per §13 item 3, large **SDXC** cards are the ones that may
not honour SPI mode at all, so the known-good part should be an SDHC in the 4–32 GB range
even though `CCS` = 1 admits both.

**Recorded, not built:** SDSC support is a flag latched from `CMD58`, `LBA << 9` instead of
`LBA` in four commands, and one `CMD16` at init — perhaps twenty bytes. If it is ever added,
it must be added with a card of each class on the bench, not by inspection.

### 9.1 Reading a block — card already initialised

```
 (card initialised per 9.0; fast clock; /CS high)
 1. /CS low.
 2. CMD17 READ_SINGLE_BLOCK, argument = block number:  six SDDATA writes.
 3. SDMOSI <- $FF.            DI is now high for everything that follows, and no burst
                              is consumed, so the receive pipeline is untouched.
                              (No SDMOSI: SDDATA <- $FF here instead. It costs one byte
                              time, which is free -- N_CR is at least one byte anyway.)
 4. Read SDDATA until a byte != $FF appears: that is R1.  Expect $00.
                              Any non-zero bit is an error -- decode and abort, 9.3.
                              Timeout: 16 reads (N_CR is at most 8 byte times).
 5. Read SDDATA until $FE, the data token.
                              $FF          = the card is still thinking; keep polling.
                              $00-$1F      = an ERROR TOKEN. Decode and abort, 9.3.
                              anything else = protocol error. Abort.
                              Timeout: 100 ms.  -- 9.3
 6. SDCTRL: FILL, with BUF naming a free buffer.  The engine runs 512 bursts and lands
    the block in the buffer -- 326 us.  Poll SDSTAT DONE.               -- 3.5, 6.3
 7. TFM X+,Y+ the 512 bytes out of the buffer (4.5) -- or leave them where they are
    until they are wanted; the buffer is memory.
 8. Two SDDATA reads: the two CRC16 bytes.
 9. /CS high, then one SDDATA read: eight idle clocks, which SD wants after deselect
    and which the card needs in order to release DO.
```

**Why step 3 is where it is.** `$FF` must go onto `DI` immediately after the sixth
command byte, *before* any polling. Done after the token poll instead, two things break,
and both follow from this card's own register semantics (§6.2): a triggering write in the
gap between token and transfer overwrites the already-prefetched data byte 0 — the poll
read that returns `$FE` has prefetched byte 0 into the `'595` — so the block starts at
byte 1 and is short by one from beginning to end; and until `DI` is set high, every poll
burst replays the sixth command byte onto `DI`, and a replayed byte with b7 = 0 and
b6 = 1 has the bit pattern of a command's first byte, which a card is entitled to start
parsing as one.

**The pipeline off-by-one is at step 6, and it is the card's most delicate ordering.**
Every `SDDATA` read returns the byte its predecessor's burst fetched, so the step-5 read
that *returns* `$FE` has already triggered the burst that fetches data byte 0 into the
`'595`'s storage register. The engine must therefore write the `'595`'s current contents
into the buffer *before* triggering its own first burst — store, then fetch, 512 times —
or every block lands shifted by one. Symmetrically, the engine's final trigger leaves the
first CRC byte in the `'595`, step 8's two reads collect both CRC bytes, and step 9's
read consumes the trailing idle byte: the pipeline closes exactly — on paper. Getting
this off by one is the same failure mode as §4 and equally silent — **check it against a
block of known content at §12 step 4**, not by inspection.

**The CRC16 is read and not checked, and that is a considered decision.** A table-driven
CRC16 on a 6309 costs roughly 25 cycles a byte: 512 × 25 = 12,800 cycles = **6.1 ms per
block, more than eight times the 735 µs copy it protects** (§5.1). It would take the
sustained read rate from 681 KiB/s to 512 bytes per ~6.8 ms = **73 KiB/s** — nine-tenths
of the card's throughput spent re-checking a CRC the card has already checked internally.
And it would not even catch an off-by-one, because a block shifted by one shifts its CRC
bytes with it. The two bytes are read because the protocol requires the clocks, not
because anything looks at them. **The block-level integrity check is §12 step 4's 10⁵
known-content blocks, run once, not a check run forever.**

#### 9.1.1 Reading many blocks — `CMD18`, and why it is not optional

`CMD17` pays the card's read access latency `N_AC` **once per block**, and at a typical
1 ms that latency swallows most of the budget: **253 KiB/s of throughput against a
681 KiB/s ceiling**. `CMD18` READ_MULTIPLE_BLOCK pays it once per *run*: the `$FE` token
still precedes every block, but the card's internal read-ahead has the next block
waiting, so the inter-block gap collapses to a few byte times. **It costs zero hardware
and no new register**, and it is how CoCoSDC-class devices reach their quoted sustained
rates. §5.2: 681 KiB/s, host-bound.

```
 1. /CS low.
 2. CMD18 READ_MULTIPLE_BLOCK, argument = the FIRST block number: six SDDATA writes.
 3. SDMOSI <- $FF.  Poll for R1 = $00 as 9.1 step 4.
 4. For each block n:
      a. Read SDDATA until $FE.   Error token / timeout handling exactly as 9.1 step 5.
                                  For blocks after the first this is typically one read.
      b. SDCTRL: FILL, BUF = n mod 4.  While the engine fills buffer n, TFM buffer n-1
         out to its destination; only then poll DONE.               -- 5.2, 6.3
      c. Two SDDATA reads: the CRC16.
 5. CMD12 STOP_TRANSMISSION: six SDDATA writes.
      a. Discard ONE stuff byte -- CMD12 alone sends a stuffing byte before its R1.
      b. Read R1 (expect $00).
      c. CMD12's response is R1b: an R1 FOLLOWED BY A BUSY PHASE. Read SDDATA until
         it returns $FF.  Timeout 250 ms.  -- 9.3
 6. /CS high, one idle SDDATA read.  TFM the last buffer out.
```

**`CMD12` is not optional and is not only for the normal exit.** A card left in multi-block
streaming keeps sending data, and the next command the driver issues will be answered with
block data rather than a response. Every abort path in §9.3 — error token, token timeout,
card removed — must send `CMD12` before it does anything else. The one exception is a card
that has physically gone away, where `/CS` high and a full §9.0 re-init is the only recovery.

**The driver should read whole tracks, not whole sectors.** Between the 512-byte block and
`RBF`'s 256-byte sector (§9.4.1) and the `CMD18` amortisation, the natural unit of transfer is
"as many consecutive blocks as the caller asked for", and the driver should push the
multi-block decision up to the point where it knows that. A one-sector-at-a-time driver gets
§9.1.1's 253 KiB/s and none of §5.2's 681.

### 9.2 Writing a block

```
 (card initialised per 9.0; fast clock; /CS high;  SDSTAT b2 WP checked -- 9.3)
 1. /CS low.
 2. CMD24 WRITE_BLOCK, argument = block number: six SDDATA writes.
 3. SDMOSI <- $FF.  Read SDDATA until != $FF: R1, expect $00.  N_CR timeout.
 4. One SDDATA read: at least one idle byte is required between the response and the
    start token.
 5. SDDATA <- $FE, the start token for a single block.
 6. 512 data bytes:  16 x { mask ; TFM X+,Y W=32 ; unmask }     <- see the caveat below
 7. SDDATA <- $FF twice: the two CRC16 bytes. Ignored by the card (9.0), but the
    clocks are mandatory.
 8. SDMOSI <- $FF; one SDDATA read: the DATA-RESPONSE TOKEN.  Mask with $1F:
        $05  (xxx0 0101)  accepted
        $0B  (xxx0 1011)  rejected, CRC error       -> the block was NOT written
        $0D  (xxx0 1101)  rejected, write error     -> the block was NOT written
        anything else                               -> protocol error, abort
 9. BUSY PHASE. Read SDDATA until it returns $FF. The card holds DO low and every read
    returns $00 for the whole program time: 250 us to several ms typically, 250 ms by
    the specification.  Timeout 250 ms (18 VBL ticks).  -- 9.3, 5.3
10. /CS high, one idle SDDATA read.
11. Recommended: CMD13 SEND_STATUS. Two response bytes (R2), both $00 on success. This
    is the only way to learn that a block the card ACCEPTED failed to program.
```

**Step 6 and the interrupt question.** The write is `TFM X+,Y` against a port whose *write*
has a side effect — it loads the hold register and triggers a burst, and the burst advances
the stream. §12 step 1's capture might show "a doubled write". A doubled write here
duplicates a byte in the middle of a block, shifts every byte after it, and leaves the CRC
bytes, the data-response token and the busy poll all one byte out of step: **the same
silent corruption as §4, on the outbound path.**

> ⚠ **"Writes need no chunking and no masking" cannot be asserted — only measured.**
> `TFM X+,Y` is safe against a *re-read* of the source, which is what §4.2's table
> compares; it is not automatically safe against a *re-write* of the destination, and
> nothing has established that the destination cannot be written twice. Step 6 is
> therefore chunked and masked, exactly as §4.4, and the masking comes *out* if and only
> if §12 step 1 says it can. The cost of being wrong here is silent data loss on the
> write path; the cost of being conservative is §5.3's already-program-bound rate falling
> by a further 21 % of a term that is not the bottleneck. **The conservative choice is
> nearly free and is taken.**
>
> **The same exposure applies to `modplayer.md` §4.4's sample upload.** That `TFM X+,Y`
> targets `ADATA`/`SDATA`, whose write auto-increments the card-side address
> (`audio.md` §13.2) — a write side effect by the same definition. A doubled write there
> duplicates a sample byte and shifts the rest of the instrument. **That document should
> carry the same caveat**; this one cannot edit it, so it is recorded here and in §13
> item 10.

#### 9.2.1 `CMD25` multi-block write — and why it is not the win `CMD18` was

`CMD25` WRITE_MULTIPLE_BLOCK exists, uses `$FC` as the per-block start token and `$FD` as
the stop token, and requires a busy poll after **every** block as well as after the stop
token. `ACMD23` SET_WR_BLK_ERASE_COUNT before it lets some cards pre-erase and program
faster.

**It removes the per-block command overhead — about 44 µs of §5.3's 1.975 ms — and nothing
else.** The program time `T_p` is the term that matters and `CMD25` does not shorten it;
at best a card overlaps the programming of block N with the transfer of block N+1, which is
a card property and not a host one. **Expect a few per cent, not the 2× that `CMD18` buys on
the read side.** Implement it if §12 step 5 shows a card that pipelines; do not plan a rate
around it.

### 9.3 Errors, timeouts, and the card that was swapped

A `CMD17` for an out-of-range block, or for a card that has been pulled, sets an R1 error
bit and then sends **no token, ever** — so every wait below has a decode and a timeout,
and a poll loop that tests only for the happy byte will hang the machine on the day a
card misbehaves.

**R1** — one byte, b7 always 0. Expect `$00` after init, `$01` during it.

| Bit | Meaning | Driver action |
|---|---|---|
| 0 | in idle state | expected during §9.0, an error after it |
| 1 | erase reset | abort, re-init |
| 2 | **illegal command** | in §9.0 step 4 this is the v1.x/MMC signal (§9.0.1); anywhere else, a driver bug |
| 3 | **command CRC error** | the constants in §9.0 are wrong, or `SCK` framing is lost (§6.5) |
| 4 | erase sequence error | abort |
| 5 | **address error** | out-of-range block, or `CCS` was misread (§9.0.1) |
| 6 | parameter error | abort |

**Error tokens.** While waiting for `$FE`, a byte whose top three bits are zero (`$00`–`$1F`)
is an error token, not filler:

| Bit | Meaning |
|---|---|
| 0 | error |
| 1 | CC error — an internal card controller fault |
| 2 | card ECC failed — **the block is unreadable; this is media failure, report it** |
| 3 | out of range |
| 4 | card is locked |

**Timeouts.** One poll iteration is `LDA >SDDATA` + `CMPA` + `BNE` ≈ 10 `E` cycles =
**4.8 µs**, which is the unit all of these are counted in.

| Wait | Spec ceiling | Implementation | Iterations |
|---|---|---|---|
| R1 after any command (`N_CR`) | 8 byte times = 5.1 µs | count reads | **16** |
| Data token after `CMD17`/`CMD18` (`N_AC`) | **100 ms** | 16-bit down-counter | **20,000** ≈ 96 ms |
| Busy after a write, and after `CMD12` | **250 ms** | count `VBL` ticks (70 Hz, 14.3 ms) | **18 ticks** ≈ 257 ms |
| `ACMD41` idle loop (§9.0 step 5) | 1 s by convention | `VBL` ticks | **70** |

The two long ones use the `VBL` tick rather than a counter because 20,000 iterations of a
tight loop is already 96 ms of a CPU that has a replayer to run; a busy poll should sleep
between samples, and the tick is the machine's only clock. `VBL` is latched in `VSTAT`
(`graphics.md` §12) so it survives §9.2's masked windows.

**Recovery ladder**, in order: retry the command once → `/CS` high, 8 idle clocks, `CMD12`
if a multi-block read was open, then retry → full §9.0 re-initialisation → mark the drive
not ready and report `E$NotRdy`. A driver that does not have all four rungs will, on the day
a card misbehaves, either hang the machine or corrupt a filesystem.

**Card change.** `SDSTAT` b1 `CD` is a mechanical switch and is not an interrupt (§6.3).

- **Poll it on the `VBL` tick** — 70 Hz, 14.3 ms. Debounce by requiring **three consecutive
  agreeing samples**, ≈43 ms, which is longer than any switch bounce and shorter than any
  hand.
- **On 1 → 0 (removed):** mark the drive not ready; invalidate the 512-byte block cache and
  every `RBF` sector buffer derived from it; **discard dirty buffers without attempting to
  flush them** — the media they belong to is gone, and writing them to whatever is inserted
  next is precisely the corruption this is here to prevent.
- **On 0 → 1 (inserted):** set media-changed; run §9.0 on the next access, not on the
  interrupt-time edge.
- **Check `WP` (b2) at mount and before every write**, and return `E$WP` without touching
  the card.

> ⚠ **The honest limit: `RBF` has no media-change notification for already-open paths.**
> A card swapped while a file is open cannot be made safe by a driver. What this
> specification buys is that the driver **detects** the swap and fails subsequent I/O,
> instead of writing the old card's sector 12 onto the new card's sector 12. Any dirty
> buffer held at the moment of removal is lost.

### 9.4 The driver

**There is no drop-in.** Unlike `serial.md` §3.2's 6551, which inherits NitrOS-9's CoCo
driver by having the same register map, this card's map is new and a NitrOS-9 `RBF` driver
has to be written. CoCoSDC and DriveWire are prior art for SD-backed storage under
NitrOS-9 but neither speaks to this map. **That is the real cost of this card** and it is
larger than the fourteen ICs. §13 item 4.

#### 9.4.1 Deblocking: `RBF`'s sector is 256 bytes and the card's block is 512

This is not a detail. NitrOS-9's `RBF` addresses media in **256-byte logical sectors**; an
SDHC card's block is **512 bytes and cannot be changed** (§9.0 step 7). Every access
therefore crosses a 2:1 boundary.

| `RBF` operation | What the driver must actually do | Cost (§5.2, §5.3) |
|---|---|---|
| Read logical sector `N` | Read physical block `N >> 1`, hand back half of it | ~1.8 ms, but a one-block cache makes the *other* half free |
| Read `N` sectors, sequential | `CMD18` over `⌈N/2⌉` blocks | **the good case** — 681 KiB/s, and half as many commands as sectors |
| **Write one logical sector** | **Read-modify-write:** read block `N >> 1`, patch 256 bytes, write it back | **~3.95 ms for 256 bytes = 63 KiB/s** |
| Write both halves of a block | one write, if a write-back cache holds the block until both are dirty | ~126 KiB/s |

**Three consequences.** The single-sector write is the worst path on the card by a factor of
six against §5.3's headline, and it is the path `RBF` uses for directory and bitmap updates —
the small, frequent, latency-visible writes. A **512-byte block cache with write-back** is
therefore not an optimisation but part of the specification, and it costs 512 bytes of
system-global storage per drive on a Level 2 machine. And the driver's size estimate in §13
item 4 grows accordingly: deblocking, a cache with a dirty bit, and the flush-on-close and
flush-on-media-change paths are all code that a 6551-style drop-in would never have needed.

**This strengthens §13 item 4 rather than complicating it.** CoCoSDC's driver already solves
deblocking against the same 512-byte SD block and the same 256-byte `RBF` sector, and it is
debugged. Matching CoCoSDC's register map would inherit the deblocking, the cache and the
media-change handling along with the driver — which is a larger prize than "buy an existing
driver" makes it sound. **Evaluate that before §12 step 6, not after.**

(Formatting the media with 512-byte `RBF` sectors instead is not evaluated here: `RBF`'s
on-disk structures and the CoCo-side tooling both assume 256, so it is a filesystem change
rather than a driver change. Recorded as unexamined.)

---

## 10. Period audit — and the exception

| Part | First available | Verdict |
|---|---|---|
| 74HC/HCT595, '165, '574, '163, '393, '4040, '157, '245 | 1980s HC family | in period |
| 6116 | early 1980s | in period |
| GAL22V10 | 1986 | in period; the machine already uses eleven |
| **SD card** | **1999** | ⚠ **out of period. No argument available.** |
| **74LVC125, 3.3 V LDO** | **1990s** | ⚠ out of period — but they exist *only* to serve the SD card |

**The honest framing.** The logic on this card is 1980s TTL and would have been buildable
in 1989. What is not period is the **device on the end of the socket**, and the 3.3 V
domain exists solely because that device needs it — so it is one exception, not two.

That is the same status as the modern LCD on the video card's VGA output, or the
USB-serial adapter on the other end of `serial.md`'s DE-9 cable: the *machine* is period,
its *peripherals* are what you can buy. The difference is that this one is inside the case,
which is why it is written down here rather than waved away.

**If the exception is unacceptable, §11.2's floppy controller is the period answer** and
should be built instead — at 30.5 KiB/s, over twenty times slower.

> A period-legal 3.3 V interface is possible without the `'LVC125`: resistor dividers on
> the three outputs. At 12.588 MHz, a 1 kΩ/2 kΩ divider into ~20 pF settles in ~13 ns
> against a 39.7 ns clock period, so it would work. It is uglier and less robust; it is
> offered because the "one exception" argument above is cleaner if the *only* anachronism
> is the card itself. §13 item 7.

---

## 11. The alternatives

### 11.1 A 512-byte memory-mapped block buffer — taken (2026-09-08)

**This is the design.** Expose the card's block buffer as address space: reads become
non-side-effecting, `TFM X+,Y+` walks it at 3 cycles/byte, and §4's hazard disappears from
the read path entirely — no chunking, no masking, 681 KiB/s, and a simpler driver. §3.5 is
the circuit, §4.5 is the hazard going away, §5 is the rate.

The address space it needs is `machine.md` §5 item 1 option D's second megabyte —
physical `A20`, one backplane pin, no parts — divided by §5 item 7 into sixteen 64 KB
regions with a fixed-phase bus schedule in place of `/WAIT`. This card takes one region
and uses 2 KB of it. **What it costs is six ICs** (§8), five of them address and data
plumbing, and a second `GAL22V10`.

The adoption narrative — this was long "the clean answer we cannot afford", and the
argument for affording it is what helped close `machine.md` §5 item 1 — is archived in
[history.md](history.md).

### 11.2 A WD1773 floppy controller — the period answer

~5 ICs, entirely in period, and NitrOS-9 already drives it because it is what a CoCo uses.
**250 kbit/s ⇒ 31,250 B/s = 30.5 KiB/s**, over twenty times slower than §5.2's sustained
rate, on media that is no longer manufactured and that a modern host cannot easily write.

**Not rejected — kept.** This is the same posture `audio.md` §6.3 takes toward the
`AD7545A`: the part the design *would* have used in 1989 stays in the period audit, and the
buildable one goes in the BOM. If §10's exception is refused, this is what gets built.

### 11.3 DriveWire over the serial card — zero extra hardware

NitrOS-9's DriveWire serves virtual disks over a serial link, and `serial.md`'s card
exists. Zero ICs.

**Rejected as the primary path, kept as a bootstrap.** A CoCo runs DriveWire at 230,400
baud through its bit-banger; `serial.md` §3.1's 6551 tops out at **19,200 baud = 1,920 B/s = 1.9 KiB/s**, and
§5 there shows the interrupt load is what bounds it, not the baud generator. That is 360×
slower than this card. But it needs no hardware at all, which makes it the right way to get
a filesystem onto the machine before this card exists — §12 step 0.

### 11.4 SCSI — in period, and genuinely good

A 5380-class SCSI controller is a 1986 part and a legitimate period answer for a hard disk.
One chip plus a drive, and fast enough to embarrass everything above.

**Not rejected; out of scope.** Period drives are large, loud, and dying, and the machine
gains nothing from a fixed disk that it does not gain from removable media a modern host can
write. Worth revisiting if this project ever wants a "period-pure" configuration alongside
the practical one.

### 11.5 Bit-banged SPI on port bits — 0 ICs

~40 cycles a byte, **51 KiB/s**.

**Rejected on speed alone**, and it is worth noting *why* the argument is different from
`serial.md` §4.4's rejection of bit-banged async serial. There, an interrupt mid-character
corrupts the data because the *far end* is timing the bits. Here **the host generates the
clock**, so an interrupt merely stretches one SPI clock and the card does not care. Bit-banged
SPI is *correct*; it is only slow. If §9.2's write-path exposure ever proves worse than
expected, this is the safe fallback.

### 11.6 Specify the hazard out of the CPU — the option that costs fidelity, not silicon

Every alternative above changes *this card*. This one does not touch the card at all.

**The 6309 in this machine is C11 firmware on an STM32G431** (`machine.md` §0,
[`plan.md`](../../cpu/docs/plan.md)). §12 step 1's capture tells us what a real HD63C09E
does with `TFM` and an interrupt. **It does not tell us what our core must do.**

**The change:** implement `TFM` interrupt recognition as *complete the current byte, take
the interrupt, resume at the next byte with nothing cached*. The one-byte cache is then
never live across an interrupt, so there is nothing to recover and nothing to re-read —
and, by the same construction, nothing to write twice. It is a boundary condition in the
`TFM` state machine, not extra work: **zero firmware cycles.**

**What it buys — and the constituency is the write side, not the read side.** The block
read already runs unchunked (§4.5), so the fix buys reads nothing. What it deletes is
§9.2 step 6's chunk-and-mask on this card's write path, and the identical conservative
masking `modplayer.md` §4.4's sample upload should carry (§13 item 10) — every remaining
`TFM` against a side-effecting port in the machine, made unconditionally safe at once.

**What it costs is fidelity.** The machine's 6309 becomes observably different from an
HD63C09E: a program that arranges an interrupt during a `TFM` whose source or destination
is a side-effecting port would behave differently here than on real silicon. Nothing in
NitrOS-9 does that, and no CoCo software can, because a CoCo has no such port — so the
divergence is invisible to every program that currently exists. **But "invisible" is a
judgement, and this project keeps a divergence ledger (`machine.md` §5 item 6) precisely
so that such judgements are recorded rather than assumed.**

**Where it must not be on: the CoCo 3 drop-in SKU.** That target's entire value is being
indistinguishable from the part it replaces (`machine.md` §0's two-targets table), and it
does not have this card in the first place. Gate the behaviour per-SKU, or behind a mode bit
in the CPU's own control space, defaulting **off**.

**And it does not delete the masked path from the driver.** If `graphics.md` §16's "drop a
real HD63C09E in" property is kept, a driver that assumes the fix would corrupt writes on
real silicon. The masked loop stays as the compatible path and the mode bit selects between
them — about ten bytes of driver.

> **Priced, not decided.** An unmasked write path and a machine with no `TFM` caveat
> anywhere, against one entry in the divergence ledger and one mode bit. **The fidelity
> call is the owner's**, and this document does not make it. It should be settled when
> §12 step 1's capture is read, because that is when the information is on the table.
> §13 item 11.

---

## 12. Build order

| # | Step | Exit criterion |
|---|---|---|
| 0 | **Get a filesystem onto the machine over DriveWire** (§11.3), before any of this exists | NitrOS-9 boots and mounts a virtual disk |
| 1 | **⚠ Settle `TFM`'s interrupt/resume behaviour from silicon** — `plan.md` §7 already wants this | a capture from a real HD63C09E answering **three** questions: **(a)** is the *source* re-read on resume, and at what point — the recorded behaviour §4 rests on; **(b)** **can the *destination* be written twice** — gates §9.2's masking, and `modplayer.md` §4.4's upload with it; **(c)** do dummy bus cycles drive `$FFFF` — gates §3.4, and is a requirement on the core whatever silicon says. **Then §11.6's choice, which is the owner's.** |
| 2 | **Full §9.0 initialisation on the bus exerciser** (`graphics.md` §16.1), init clock only, no 6309 core | `CMD0` → `CMD8` check-pattern echo → `ACMD41` → `CMD58` with `CCS` = 1; the card's `CID` reads back correctly; **an SDSC card is refused cleanly rather than mis-addressed** (§9.0.1) |
| 3 | **Fit the GALs**; switch to the fast clock | burst measured at ≤636 ns; §8's macrocell arithmetic confirmed, or the card becomes 15 ICs (§8.1); **§6.6's `DI` hold margin scoped at the card's own pin**, and the inverted-`SCK` decision taken |
| 4 | **Block read through the buffer** (§9.1: `FILL`, `DONE`, `TFM X+,Y+`) against a block of known content | **10⁵ blocks, byte-exact, with video, audio, PS/2 and serial interrupts all running.** This is the step that catches §9.1's pipeline off-by-one; nothing else will. |
| 5 | **Write path** (§9.2), and regulator behaviour under write current | data-response `$05` on every block; **the busy phase observed and its duration logged**; `CMD13` clean; no brown-out, no read corruption during write bursts; **the sustained write rate measured and recorded against §5.3's range** — this is the step that decides where in 126–408 KiB/s the truth is |
| 6 | **NitrOS-9 `RBF` driver**, with §9.4.1's deblocking and block cache, and §9.3's recovery ladder | a mounted filesystem, `dir` and `copy` working; **and the error paths exercised**: an out-of-range `CMD17` returns R1 b5 and does not hang; an unreadable block yields an error token and is reported, not skipped; a card pulled mid-transfer leaves the drive not-ready with no corruption; a card reinserted re-initialises and remounts |
| 7 | **Sustained throughput under a running replayer** | **the multi-block (`CMD18`) sustained rate measured over a file — §5.2 predicts 681 KiB/s, host-bound** — not computed from the intra-block arithmetic. Exit at ≥650 KiB/s sustained, with **no lost replayer ticks** and no corrupted blocks. If the measured rate lands nearer 253 KiB/s, the driver is not issuing `CMD18` (§9.1.1). |

**Step 1 gates the write path and the §11.6 decision**, and step 4 is the only step that
can prove the read pipeline closes. **Step 7 is the only step that measures a rate anyone
will experience**; every other number in this document is a component of it.

---

## 13. Open items

1. **`TFM`'s interrupt/resume behaviour — two of §12 step 1's three questions still
   decide something.** §4's statement of the hazard rests entirely on community
   documentation, and the block path no longer depends on the answer (§4.5: RAM to RAM,
   and a re-read of RAM is idempotent). What is still owed: whether dummy cycles drive
   `$FFFF` (§3.4 — a *requirement on the CPU firmware*, not an observation), and
   **whether the destination can be written twice** (§9.2, and `modplayer.md` §4.4's
   upload). The source-re-read question no longer decides anything on this card, and
   `net/docs/net.md` §3.2 no longer depends on it either. **`machine.md` §6 should be
   re-scoped rather than closed.**

2. **No SD specification is in `reference/`.** Everything protocol-shaped in this document
   is recalled: the 400 kHz init ceiling, the 74-clock power-up, the `$FE` token, the CRC
   bytes, the `V_OH` figure §7 relies on, the whole of §9.0's init dialog, §9.2's
   write sequence, and §9.3's `N_CR` / `N_AC` / program-time ceilings, which §5.2 and §5.3's
   arithmetic are built on. **Add the SD Simplified Specification before §12 step 2**,
   and re-derive §9 from it.

3. **SPI mode is optional in the modern SD specification.** SDHC is reliable; large SDXC
   cards may not honour it. Same sourcing-risk class as `ps2.md`'s `CD40105B` — establish a
   known-good card and record the part number. §9.0.1 requires `CCS` = 1, which admits SDXC;
   **the known-good part should nonetheless be an SDHC in the 4–32 GB range**, which is
   where SPI-mode support is safest.

4. **No NitrOS-9 driver exists** (§9.4), and writing one is a larger job than building the
   card — deblocking, a 512-byte write-back block cache, and flush-on-close and
   flush-on-media-change paths (§9.4.1). Unlike `serial.md`'s 6551 there is no compatible
   map to inherit. **Matching the CoCoSDC's register map would inherit its deblocking and
   media-change handling as well as its driver**, which is a bigger prize than "buy a
   driver" makes it sound. **That trade has not been evaluated and should be, before §12
   step 6.**

5. **Regulator sizing for write current** (§7). Cards draw far more, and in bursts, while
   programming. The failure mode is a card that reads perfectly and corrupts writes. §5.3
   gives the *duration* of that phase as well as §7's current; §12 step 5 measures both.

6. **⚠ The write path is still on the port, and that is an inconsistency.** §4.5
   item 3: the buffer is bidirectional and the fill engine could drain it as easily as
   fill it, for one direction bit in `SDCTRL` and a `/OE` term. **The read path is
   specified against the buffer while §9.2 pushes 512 bytes out through `SDDATA`** —
   so the write path still pays §4.4's chunk-and-mask tax and still carries the
   doubled-write exposure that item 1 keeps open. **Do this before §12 step 5**; it is a
   small change to a card that is all on paper, and leaving it is the sort of asymmetry
   that turns into a bug report.

7. **Whether to use resistor dividers instead of the `'LVC125`** (§10), so that the *only*
   anachronism in the machine is the card itself rather than the card plus its support
   logic. Aesthetic, but this project's period audits have been worth keeping honest.

8. **Closed** — the `$FF` map slack (`machine.md` §5 item 1; see
   [history.md](history.md)). The live residue is §6.1's ⚠: the decode is seven bits,
   because six answer at `$FF58` and `$FF18` both.

9. **The `'165`'s clock edge is the same edge the card samples `DI` on** (§6.6), so the
   `DI` hold margin is whatever an `HC` part's *unspecified minimum* propagation delay
   happens to be. It works on NormalLuser's board; it is not designed. The robust fix —
   clocking the `'165` on inverted `SCK` — costs one gate the card does not have, and is
   first in the queue for the four macrocells that free up if §8's overflow moves
   `SDCTRL` to a `'574`. **Decide at §12 step 3, with a scope on the card's `DI` pin.**

10. **The write-side `TFM` exposure is not confined to this card.** §9.2's caveat — a
   doubled write against a port whose write has a side effect — applies equally to
   `modplayer.md` §4.4's `TFM X+,Y` upload into `ADATA`/`SDATA`, whose write auto-increments
   the card-side address (`audio.md` §13.2). **That document should carry the same
   "pending §12 step 1" caveat**, and does not; this one cannot edit it.

11. **⚠ Whether to specify the `TFM` hazard out of the CPU firmware** (§11.6). This is the
    one open item that is not a measurement, a purchase or a piece of research: it is a
    **decision the owner has to make**, between a machine with no `TFM` caveat anywhere
    and an entry in the NitrOS-9 divergence ledger. It is priced in §11.6 and deliberately
    left undecided here. It should be settled at the same time as §12 step 1's capture is
    read, because that is when the information is on the table.

12. **⚠ Whether to take the `ATF1508AS`** (§8.1). No longer blocked — the no-CPLD house
    rule is retired (root `README.md`) — and not taken: **8 ICs against 14**, weighed
    against losing `hardware/gal/jedec/`'s fuse-level verification and against the fact
    that this card's logic fits two GALs comfortably, so a CPLD buys packages rather than
    capability. Taking it is a card re-specification; re-open the question if the card is
    ever opened up for another reason (§13 item 6 is a candidate).

---

## 14. Sources and cross-references

| | |
|---|---|
| **NormalLuser, *BE6502 Fast SD Card Interface*** | <https://github.com/NormalLuser/BE6502-Fast-SD-Card-Interface> — the origin of §3.1. Read-triggers-next-burst, and the self-resetting 8-clock generator |
| [`plan.md`](../../cpu/docs/plan.md) | §4.3 `TFM` as "the hard one"; §7's risk table, which §13 item 1 keeps live |
| [`modplayer.md`](../../audio/docs/modplayer.md) | §4.4 the fixed-destination `TFM X+,Y`, why it is safe against a re-read (§4.2), and the doubled-write caveat it should carry (§13 item 10) |
| [`machine.md`](../../docs/machine.md) | §2 the 25.175 MHz master this card divides; §3 the `$FF` map; §5 items 1 and 7, the `A20 = 1` space and bus schedule §3.5 is built on; §5 item 6 the divergence ledger §11.6 would write into; §6 the capture ownership |
| [`net/docs/net.md`](../../net/docs/net.md) | §3.2 cites §4's hazard statement and §4.2's idempotence argument; §5.1 holds `$FF5C`–`$FF5F` |
| [`graphics.md`](../../video/docs/graphics.md) | §16.1 the bus exerciser; §16 the "drop a real HD63C09E in" property §11.6 weighs; §17 the disk-controller reservation this card claims half of |
| [`ps2.md`](../../io/ps2/docs/ps2.md) | §4.1 the `'595` storage-register pattern; §4.2 the `HC`-versus-`HCT` lesson §7 repeats |
| [`serial.md`](../../io/serial/docs/serial.md) | §3.1 the 6551 that bounds §11.3's DriveWire bootstrap; §4.4 the bit-banging argument §11.5 distinguishes itself from |
| HD63B09EP Technical Reference Guide; *A Memo on the Secret Features of 6309* | §4.1's `TFM` behaviour. ⚠ Neither is in `reference/` |
| [`audio.md`](../../audio/docs/audio.md) | §9.3 the read-triggers-prefetch pattern §3.1 shares; §13.2 `ADATA`/`SDATA`'s auto-increment, which makes §9.2's doubled-write caveat apply there too |
| SD Simplified Specification (Physical Layer, SPI mode) | §9.0's init dialog, §9.1's tokens, §9.2's write sequence, §9.3's R1/error tokens and timeout ceilings. ⚠ **Not in `reference/` — §13 item 2, and §9 is entirely recalled until it is** |
| NitrOS-9 `RBF` — 256-byte logical sectors | §9.4.1's deblocking. ⚠ recalled, and the CoCoSDC driver is the place to check it against |
