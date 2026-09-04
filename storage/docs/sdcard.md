# Mass Storage for an arm6309 Machine
## An SD Card at 537 KB/s, and the `TFM` Hazard That Nearly Eats It

**Question this answers:** the `$FF` map has reserved eight bytes for "a disk controller"
since [`graphics.md`](../../video/docs/graphics.md) §17, and nobody has ever said what that
controller is. [`machine.md`](../../docs/machine.md) §3 now allocates every other byte in
the window. What goes in those eight, and how fast can a 6309 pull data through it?

**Short answer: a shift register, a self-resetting burst counter, and one instruction.**
The circuit is NormalLuser's BE6502 SD interface — **the bus read strobe itself triggers
the next 8-clock SPI burst**, so reading the data port returns byte N and prefetches byte
N+1 in hardware, with no software SPI at all. On a 6502 that gives 130 KB/s through an
unrolled `LDA`/`STA` loop. On a 6309 it meets **`TFM X,Y+`** — fixed source, incrementing
destination, three cycles a byte — which is *exactly* "read this port 512 times into a
buffer", and the ceiling becomes **680 KB/s**.

**And that is where it goes wrong.** `TFM` is the 6309's only interruptible instruction,
and on resume it **re-reads the source address**. Against RAM that is idempotent. Against
a port whose read pops a byte, it silently loses one and shifts the rest of the block.
§4 is the whole document.

**Constraints taken as given (yours):**
- **Parts available before 1990.** No CPLDs, no FPGAs. GALs are in.
- Same house rules as the other cards: period-honest silicon, one card, a documented
  register map, and an honest IC count.

> ⚠ **One rule is broken here and cannot be argued back.** An SD card is **1999**. §10
> makes the case that the *circuit* is period-legal and only the *media* is not — the same
> status as the modern LCD on the video card's VGA output — but it is a real exception and
> it is the only one in the machine.

---

## 0. Summary — the verdict in one table

| Question | Answer | § |
|---|---|---|
| **How is SPI generated?** | **A shift register and a self-resetting 8-clock burst counter.** No bit-banging, no SPI peripheral. | §3.1 |
| **What starts each transfer?** | **The bus read strobe.** Reading the data port returns byte N *and* fetches N+1. | §3.1 |
| **Why is that better on a 6309 than on a 6502?** | Because `TFM X,Y+` is a fixed-source block move at 3 cycles/byte — a hardware-prefetched port is the one source it was made for. | §3.2 |
| **Fast enough?** | The SPI burst is **636 ns** against `TFM`'s **1430 ns** read interval. 2.25× margin, no wait states, ever. | §3.3 |
| **⚠ So what is the problem?** | **`TFM` re-reads its source after an interrupt.** On a popping port that loses a byte and corrupts the block — about one block in seven. | §4 |
| **Can hardware fix it?** | **No.** A re-read is indistinguishable from a legitimate next read. | §4.3 |
| **So?** | **Chunk the `TFM` and mask interrupts around each chunk.** 32-byte chunks cost 21 % of peak and add 49 µs of interrupt latency. | §4.4 |
| **Net rate** | **537 KB/s** — 4× the BE6502, 2.4× a hazard-free `LDA`/`STA` loop. | §5 |
| **Address cost** | **Four bytes**, at `$FF58`–`$FF5B`. The disk reservation was eight, so **four go back to the machine.** | §6.1 |
| **IC count** | **7**, plus a 3.3 V regulator and the socket. | §8 |

**Net: 7 ICs**, against video's 33, audio's 35, PS/2's 9 and serial's 3.

---

## 1. Sources and confidence

| Claim class | Source | Confidence |
|---|---|---|
| The read-triggers-next-burst topology; the self-resetting 8-clock generator; ~130 KB/s at 5 MHz | **NormalLuser, *BE6502 Fast SD Card Interface*** — <https://github.com/NormalLuser/BE6502-Fast-SD-Card-Interface> | **read directly**; a working, measured design |
| `TFM` has four forms including `TFM r0,r1+` (fixed source, incrementing destination); `W` holds the count; 3 cycles/byte | HD63B09EP Technical Reference Guide; this repo's own `plan.md` §4.3 and `modplayer.md` §4.4 | **corroborated**, and already load-bearing elsewhere in this project |
| **`TFM` is interruptible, uses a one-byte internal cache, and re-reads the source address on resume** | HD63B09EP Technical Reference; *A Memo on the Secret Features of 6309* | ⚠ **community documentation, not silicon. §13 item 1, and §4 rests entirely on it.** |
| SD SPI mode: ≤400 kHz until initialised, then up to 25 MHz; ≥74 clocks with `CS` high at power-up; `FE` data token; 2 CRC bytes per block | SD Simplified Specification, recalled | ⚠ **no SD specification in `reference/` — §13 item 2** |
| SD card `V_OH` ≥ 0.75 × `V_DD` ≈ 2.48 V, clearing a `74HCT` input's 2.0 V `V_IH` | recalled | ⚠ §13 item 2 |
| NitrOS-9 interrupt dispatch cost | ⚠ guessed, as in `ps2.md` §3.1 and `serial.md` §5 | **unverified — the same measurement again** |

**`plan.md` §7's risk table already lists "`TFM` interruptibility subtleties" as needing
"dedicated vectors from silicon capture."** This card makes that a second thing depending
on the answer, and moves it up the queue. §13 item 1.

---

## 2. What the machine needs from storage

| Need | Rate | Notes |
|---|---|---|
| Boot NitrOS-9 Level 2 | — | the machine's success criterion, inherited from `plan.md` |
| Load a program | as fast as possible | 30 KB in 56 ms at §5's rate |
| **Upload 128 KB of mod samples** | the interesting one | `modplayer.md` §4.4 already streams these to the audio card with `TFM X+,Y` at ~700 KB/s. Storage that reads at 537 KB/s roughly matches it — **the disk stops being the bottleneck**. |
| Stream audio or video off the media | sustained | possible, with the §4.4 caveat |
| Removable media a modern host can also write | — | which is the whole reason this is not a floppy controller |

That third row is the one that shaped this design. A floppy at 31 KB/s (§11.2) turns a
128 KB sample upload into a four-second wait; this turns it into a quarter of a second.

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
  64x4 for the same reason. This is now the third card in the machine built on it.
- **The burst counter self-resets.** NormalLuser wires a `'595`'s `QH` back to `SRCLR`, so
  shifting a single 1 through it produces exactly eight clocks and then clears itself — a
  counter, a terminal-count decode and a reset in one package.

> **This is the third time this project has used read-triggers-prefetch.**
> `audio.md` §9.3 (writing `AIDX` prefetches the state file so `ADATA` never stalls) and
> `ps2.md` §4.1 (the `'595` storage register) are the same move. It is becoming the
> machine's house pattern for "make the bus read free".

### 3.2 What changes on a 6309

**Drop the VIA.** NormalLuser reaches the shift register through a 6522's Port A because a
6522 was already on the Ben Eater board — the design is visibly shaped by what was free
("unused gates repurposed from the VGA interface"). We put the `'595`'s three-state output
straight on the data bus, exactly as `ps2.md` §4.1 does, and save the VIA's sixteen
addresses, which §6.1 shows we do not have.

**And then the instruction changes everything.** The 6502 needs an unrolled
`LDA`/`STA` loop, 10–12 cycles a byte. The 6309's `TFM` has a **fixed-source** form:

```
        ldx   #SDDATA          ; source: the port, not advanced
        ldy   #buffer          ; destination: advanced every byte
        ldw   #512
        tfm   x,y+             ; 6 cycles + 3 per byte
```

`modplayer.md` §4.4 already uses the **mirror image** of this — `TFM X+,Y`, fixed
destination — to stream samples *to* the audio card at ~700 KB/s. This is the same trick
pointed the other way, and §4 is about why that symmetry does not hold.

### 3.3 The clock budget

The backplane carries the 25.175 MHz system master (`machine.md` §2, "the master lets any
card phase-lock to video"), so the card needs no oscillator of its own.

| | |
|---|---|
| Transfer clock | 25.175 / 2 = **12.588 MHz** — inside SD's 25 MHz ceiling with margin |
| One 8-clock burst | **636 ns** |
| `TFM` read interval | 3 `E` cycles = **1430 ns** |
| **Margin** | **2.25×** |
| Init clock | 25.175 / 64 = **393 kHz** — inside SD's 400 kHz init ceiling |
| One burst at init speed | 20.4 µs = 43 `E` cycles — **must be polled**, §6.3 |

**The card delivers a byte faster than the 6309 can take one.** So there is no `/WAIT`
path, no FIFO, and no busy-polling in the fast loop — which is what makes a bare `TFM`
possible at all. The `÷2`/`÷64` selection is one control bit and one divider package.

---

## 4. ⚠ The `TFM` hazard

This section is the reason the card is not simply "the BE6502 design, faster".

### 4.1 What `TFM` does when interrupted

`TFM` is the only interruptible instruction on the 6309. It moves one byte at a time
through a **one-byte internal cache**, and interrupts are recognised between bytes. The
documented behaviour on resume is that **if the cached byte was destroyed, `TFM` re-reads
the source address to get it back.**

For an ordinary RAM source that is invisible — re-reading RAM returns the same byte.

### 4.2 Why `modplayer.md`'s `TFM` is safe and this one is not

The asymmetry is exact, and it is easy to miss because both look like "a `TFM` against an
I/O port":

| | `TFM X+,Y` — `modplayer.md` §4.4 | `TFM X,Y+` — this card |
|---|---|---|
| Source | **RAM**, incrementing | **the port**, fixed |
| Destination | the port, fixed | RAM, incrementing |
| What re-reading the source does | returns the same RAM byte | **pops a byte and arms the next burst** |
| Result of an interrupt mid-instruction | nothing | **byte lost; the rest of the block shifts by one** |

The audio card's upload path is safe *because* it is the fixed-destination form. Invert the
direction and the safety inverts with it.

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
- **Not triggering on read** kills `TFM` outright and drops the card to §5's `LDA`/`STA`
  rate.
- **A 512-byte memory-mapped block buffer would fix it completely** — reads become
  non-side-effecting and `TFM X+,Y+` walks it with no hazard at all. It is the clean
  answer, and §11.1 rejects it on address space, which is a budget problem rather than a
  design one.

### 4.4 The fix: chunk the transfer and mask around each chunk

Masking interrupts makes the instruction atomic; chunking keeps the masked window short.

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

**A masked `/FIRQ` is delayed, not lost**, so the replayer tick survives: 49 µs of latency
against `modplayer.md`'s 20 ms tick period is 0.25 %, and the tick's own work is ~2,200
cycles of a 41,960-cycle budget. The choice of chunk size is a straight trade:

| Chunk | cyc/byte | KB/s | Interrupt latency added |
|---|---|---|---|
| 16 B | 4.62 | 443 | 26 µs |
| **32 B** | **3.81** | **537** | **49 µs** |
| 64 B | 3.41 | 601 | 94 µs |
| 512 B (unchunked) | 3.01 | 680 | **735 µs — and one block in seven is corrupt** |

**Specify 32.** 537 KB/s is still four times the BE6502 and 2.4× the hazard-free
alternative, and 49 µs is below anything else in the machine that cares.

> **This is the one place a card's correctness depends on an undocumented CPU behaviour.**
> If §13 item 1's silicon capture shows `TFM` does *not* re-read on resume, the chunking
> can be dropped and the card runs at 680 KB/s. If it shows something worse — a re-read at
> a different point, or a doubled write — the whole fast path needs rethinking. **Measure
> before writing the driver**, not after.

---

## 5. Transfer rates

| Approach | cyc/byte | KB/s | Hazard |
|---|---|---|---|
| `TFM X,Y+`, unchunked | 3.01 | 680 | ⚠ **corrupts ~1 block in 7** |
| **`TFM X,Y+`, 32-byte chunks, masked** | **3.81** | **537** | none |
| `LDA >SDDATA` / `STA ,Y+` loop | 9 | 228 | none — each `LDA` is atomic |
| Bit-banged SPI on port bits | ~40 | 51 | none |
| **BE6502 measured, 5 MHz 6502** | 10–12 | **130** | n/a |

For scale: a 512-byte block takes **931 µs**; 30 KB loads in **56 ms**; `modplayer.md`'s
128 KB of samples arrive in **238 ms**, against the 187 ms the audio card needs to swallow
them. **Storage and the audio card are within 30 % of each other**, which is the right
place for them to be.

---

## 6. Register map

### 6.1 Placement — and four bytes go back

**Propose `$FF58`–`$FF5B`, four bytes**, from the eight `graphics.md` §17 reserved for a
disk controller.

| Window | Size | Owner |
|---|---|---|
| `$FF40`–`$FF4F` | 16 | audio |
| `$FF50`–`$FF53` | 4 | PS/2 |
| `$FF54`–`$FF57` | 4 | serial |
| **`$FF58`–`$FF5B`** | **4** | **storage — this document** |
| **`$FF5C`–`$FF5F`** | **4** | ***free — returned to the machine*** |
| `$FF60`–`$FF7F` | 32 | video |

`serial.md` §7.1 reported the map exactly full at 64 of 64. **This card gives four bytes
back**, because an SPI port needs three registers where a WD1773 needs five plus a latch.
That does not resolve `machine.md` §5 item 1 — four bytes is one small card, once — but it
is the first movement in the other direction.

### 6.2 The three registers

| Off | Name | R/W | Function |
|---|---|---|---|
| `+$0` | `SDDATA` | R | the byte from the **previous** burst; **the read triggers the next** |
| `+$0` | `SDDATA` | W | load the MOSI hold register **and** trigger a burst |
| `+$1` | `SDSTAT` | R | §6.3 |
| `+$2` | `SDCTRL` | W | b0 `/CS`, b1 clock speed (0 = 393 kHz init, 1 = 12.588 MHz), b7 reset |
| `+$3` | — | | reserved |

**The MOSI hold register persists.** Every burst parallel-loads the `'165` from it, so
software writes `$FF` once before a block read and every read-triggered burst clocks `$FF`
out, which is what SD requires of a host that is receiving. Writing `SDDATA` again changes
it — that is how commands are sent.

### 6.3 `SDSTAT`

| Bit | Name | Meaning |
|---|---|---|
| 0 | `BUSY` | a burst is in progress. **Only meaningful at init speed** — §3.3 |
| 1 | `CD` | card detect, from the socket's mechanical switch |
| 2 | `WP` | write protect, likewise |
| 3–7 | — | read 0 |

`BUSY` exists for the 393 kHz init path, where a burst is 20.4 µs — 43 bus cycles — and
must be polled. **In the fast path it is never read**, because §3.3's 2.25× margin
guarantees the burst has finished before `TFM` comes back. A driver that polls `BUSY`
inside the block loop has thrown away the entire design.

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

---

## 8. Chip budget

| # | Part | Function |
|---|---|---|
| 1 | **74HCT595** | MISO shift + storage; three-state onto the data bus; **`HCT` for §7's reason** |
| 2 | 74HC165 | MOSI shift, parallel-loaded from the hold register at each burst |
| 3 | 74HC574 | MOSI hold register — §6.2's persistence |
| 4 | 74HC163 | burst counter: eight clocks, terminal count drives `RCLK` and clears `BUSY` |
| 5 | 74HC393 | clock divider, `÷2` and `÷64` taps off the 25.175 MHz master |
| 6 | 74LVC125 | 3.3 V level shift for `SCK`, `MOSI`, `/CS` |
| 7 | GAL22V10 | decode from `/IOSEL`; `SDCTRL`; `SDSTAT` readback; the read-strobe trigger |

**Total: 7.** Plus a 3.3 V LDO, an SD socket, and passives.

> **The GAL is the fitting risk**, as on the PS/2 card. Four control bits registered, three
> status bits three-stated onto the bus, the trigger term and the decode terms come to
> roughly ten macrocells of a `GAL22V10`'s ten. **If it does not fit, `SDCTRL` moves to a
> `74HC574` and the card is 8.** §12 step 3.
>
> NormalLuser's self-resetting `'595` burst generator (§3.1) would replace #4 with a part
> that also gates the clock; a `'163` is used here because the `÷2`/`÷64` selection and the
> `RCLK` timing are easier to reason about from a counter with a terminal count. Either is
> one package — decide on the bench.

---

## 9. Software

### 9.1 Reading a block

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

**Step 4 primes the pipeline, so step 6 needs no dummy read.** Every read returns the byte
its predecessor's burst fetched, so the read that *found* `$FE` already started fetching
data byte 0, and the first `TFM` read returns it. Getting this off by one shifts the whole
block, which is the same failure mode as §4 and equally silent — **check it against a
block of known content at §12 step 4**, not by inspection.

Symmetrically, the last `TFM` read triggers one more burst whose byte is not discarded but
is the first CRC byte, which step 7 then collects.

### 9.2 Writing

`TFM X+,Y` — the fixed-destination form, the one `modplayer.md` §4.4 already uses, and
**the one with no §4 hazard**. Writes need no chunking and no masking, so they run at the
full 680 KB/s. The asymmetry is worth stating in the driver's comments, because it looks
like an inconsistency and is not.

### 9.3 The driver

**There is no drop-in.** Unlike `serial.md` §3.2's 6551, which inherits NitrOS-9's CoCo
driver by having the same register map, this card's map is new and a NitrOS-9 `RBF` driver
has to be written. CoCoSDC and DriveWire are prior art for SD-backed storage under
NitrOS-9 but neither speaks to this map. **That is the real cost of this card** and it is
larger than the seven ICs. §13 item 4.

---

## 10. Period audit — and the exception

| Part | First available | Verdict |
|---|---|---|
| 74HC/HCT595, '165, '574, '163, '393 | 1980s HC family | in period |
| GAL22V10 | 1986 | in period; the machine already uses 11 |
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
should be built instead — at 31 KB/s, seventeen times slower.

> A period-legal 3.3 V interface is possible without the `'LVC125`: resistor dividers on
> the three outputs. At 12.588 MHz, a 1 kΩ/2 kΩ divider into ~20 pF settles in ~13 ns
> against a 39.7 ns clock period, so it would work. It is uglier and less robust; it is
> offered because the "one exception" argument above is cleaner if the *only* anachronism
> is the card itself. §13 item 6.

---

## 11. The alternatives

### 11.1 A 512-byte memory-mapped block buffer — the clean answer we cannot afford

Expose the card's block buffer as 512 bytes of address space. Reads become
non-side-effecting, `TFM X+,Y+` walks it at 3 cycles/byte, and **§4's hazard disappears
entirely** — no chunking, no masking, 680 KB/s, and a simpler driver.

**Rejected on address space, not on merit.** The `$FF40`–`$FF7F` geographic window is 64
bytes total (§6.1). The 1 MB physical map has no room either: `graphics.md` §6.3 fixes
`A19 = 0` as 512 KB of system RAM and `A19 = 1` as the video card's 512 KB ring, with
nothing spare.

**This is the strongest argument yet for `machine.md` §5 item 1.** Widening the machine's
I/O map would not merely make room for future cards; it would delete a hazard from an
existing one and buy 27 % more throughput. Record it there.

### 11.2 A WD1773 floppy controller — the period answer

~5 ICs, entirely in period, and NitrOS-9 already drives it because it is what a CoCo uses.
**250 kbit/s ⇒ ~31 KB/s**, seventeen times slower than §5, on media that is no longer
manufactured and that a modern host cannot easily write.

**Not rejected — kept.** This is the same posture `audio.md` §6.3 takes toward the
`AD7545A`: the part the design *would* have used in 1989 stays in the period audit, and the
buildable one goes in the BOM. If §10's exception is refused, this is what gets built.

### 11.3 DriveWire over the serial card — zero extra hardware

NitrOS-9's DriveWire serves virtual disks over a serial link, and `serial.md`'s card
exists. Zero ICs.

**Rejected as the primary path, kept as a bootstrap.** A CoCo runs DriveWire at 230,400
baud through its bit-banger; `serial.md` §3.1's 6551 tops out at **19,200 = 1.9 KB/s**, and
§5 there shows the interrupt load is what bounds it, not the baud generator. That is 280×
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

~40 cycles a byte, **51 KB/s**.

**Rejected on speed alone**, and it is worth noting *why* the argument is different from
`serial.md` §4.4's rejection of bit-banged async serial. There, an interrupt mid-character
corrupts the data because the *far end* is timing the bits. Here **the host generates the
clock**, so an interrupt merely stretches one SPI clock and the card does not care. Bit-banged
SPI is *correct*; it is only slow. If the §4 hazard ever proves worse than expected, this is
the safe fallback.

---

## 12. Build order

| # | Step | Exit criterion |
|---|---|---|
| 0 | **Get a filesystem onto the machine over DriveWire** (§11.3), before any of this exists | NitrOS-9 boots and mounts a virtual disk |
| 1 | **⚠ Settle `TFM`'s interrupt/resume behaviour from silicon** — `plan.md` §7 already wants this | a capture from a real HD63C09E showing whether the source is re-read, and at what point. **This gates §4, §9 and the driver.** |
| 2 | **SPI engine on the bus exerciser** (`graphics.md` §16.1), init clock only, no 6309 core | `CMD0`/`CMD8` accepted; the card's `CID` register reads back correctly |
| 3 | **Fit the GAL**; switch to the fast clock | burst measured at ≤636 ns; §8's macrocell arithmetic confirmed, or the card becomes 8 ICs |
| 4 | **Block read with chunked `TFM`** against a block of known content | **10⁵ blocks, byte-exact, with video, audio, PS/2 and serial interrupts all running.** This is the step that catches §4 and §9.1's off-by-one; nothing else will. |
| 5 | **Write path** (§9.2), and regulator behaviour under write current | writes verified on a host; no brown-out, no read corruption during write bursts |
| 6 | **NitrOS-9 `RBF` driver** | a mounted filesystem, `dir` and `copy` working |
| 7 | **Sustained throughput under a running replayer** | §5's 537 KB/s measured, with **no lost replayer ticks** and no corrupted blocks |

**Step 1 gates everything after it**, and step 4 is the only step that can prove §4's
mitigation actually works.

---

## 13. Open items

1. **⚠ `TFM`'s interrupt/resume behaviour is community documentation, not silicon**, and
   §4 — the central section of this document — rests entirely on it. `plan.md` §7's risk
   table already lists it; **this card makes it two things depending on the answer and
   should move it up the queue.** If the re-read does not happen, the card runs 27 % faster
   and the driver gets simpler. §12 step 1.

2. **No SD specification is in `reference/`.** The 400 kHz init ceiling, the 74-clock
   power-up, the `$FE` data token, the CRC bytes and the `V_OH` figure §7 relies on are all
   recalled. Add the SD Simplified Specification before §12 step 2.

3. **SPI mode is optional in the modern SD specification.** SDHC is reliable; large SDXC
   cards may not honour it. Same sourcing-risk class as `ps2.md`'s `CD40105B` — establish a
   known-good card and record the part number.

4. **No NitrOS-9 driver exists** (§9.3), and writing one is a larger job than building the
   card. Unlike `serial.md`'s 6551 there is no compatible map to inherit. Consider whether
   matching the CoCoSDC's register map instead would buy an existing driver — **that
   trade has not been evaluated and probably should be, before §12 step 6.**

5. **Regulator sizing for write current** (§7). Cards draw far more, and in bursts, while
   programming. The failure mode is a card that reads perfectly and corrupts writes.

6. **Whether to use resistor dividers instead of the `'LVC125`** (§10), so that the *only*
   anachronism in the machine is the card itself rather than the card plus its support
   logic. Aesthetic, but this project's period audits have been worth keeping honest.

7. **The `$FF` map still has no slack worth the name.** §6.1 hands four bytes back; that is
   one small card, once. `machine.md` §5 item 1 remains the machine's blocking decision, and
   §11.1 shows it now costs throughput as well as expandability.

---

## 14. Sources and cross-references

| | |
|---|---|
| **NormalLuser, *BE6502 Fast SD Card Interface*** | <https://github.com/NormalLuser/BE6502-Fast-SD-Card-Interface> — the origin of §3.1. Read-triggers-next-burst, and the self-resetting 8-clock generator |
| [`plan.md`](../../cpu/docs/plan.md) | §4.3 `TFM` as "the hard one"; §7's risk table, which §13 item 1 escalates |
| [`modplayer.md`](../../audio/docs/modplayer.md) | §4.4 the mirror-image `TFM X+,Y`, and why it is safe where §4's is not |
| [`machine.md`](../../docs/machine.md) | §2 the 25.175 MHz master this card divides; §3 the `$FF` map; §5 item 1, which §11.1 reinforces |
| [`graphics.md`](../../video/docs/graphics.md) | §6.3 the physical map with no room for §11.1's buffer; §16.1 the bus exerciser; §17 the disk-controller reservation this card claims half of |
| [`ps2.md`](../../io/ps2/docs/ps2.md) | §4.1 the `'595` storage-register pattern; §4.2 the `HC`-versus-`HCT` lesson §7 repeats |
| [`serial.md`](../../io/serial/docs/serial.md) | §7.1 the full `$FF` map §6.1 gives back to; §4.4 the bit-banging argument §11.5 distinguishes itself from |
| HD63B09EP Technical Reference Guide; *A Memo on the Secret Features of 6309* | §4.1's `TFM` behaviour. ⚠ Neither is in `reference/` |
