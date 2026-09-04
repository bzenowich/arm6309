# Serial for an arm6309 Machine
## Three ICs, Because the Right Chip Was Made in 1977

**Question this answers:** the machine has a CPU
([`plan.md`](../../../cpu/docs/plan.md)), video
([`graphics.md`](../../../video/docs/graphics.md)), audio
([`audio.md`](../../../audio/docs/audio.md)) and input
([`ps2.md`](../../ps2/docs/ps2.md)). It has no way to talk to anything outside itself. What
does a serial port look like on a machine whose house rule is discrete logic?

**Short answer: do not build it out of logic. Use a 6551 ACIA.** One chip, four
registers, an on-chip programmable baud rate generator needing nothing but a 1.8432 MHz
crystal, full modem control, and an interrupt output. It is a 1977 part, so it is more
period-correct than the VGA connector the video card uses — and **the Tandy Deluxe RS-232
Program Pak (26-2226, 1983) is exactly this circuit on exactly this bus**, which makes
this the only card in the machine with a shipped commercial precedent.

**The interesting number is not the chip count.** It is that the 6551 has no FIFO, so it
interrupts once per byte, and **that — not the baud generator — sets the practical
throughput ceiling** at somewhere between 4800 and 19200 baud depending on a dispatch cost
nobody has measured yet. §5.

**Constraints taken as given (yours):**
- **Parts available before 1990.** No CPLDs, no FPGAs. GALs are in.
- Same house rules as the other cards: period-honest silicon, one card, a documented
  register map, and an honest IC count.

> **This supersedes [`../README.md`](../README.md)'s framing**, which said the first
> decision was "a period RS-232 port (~14 ICs) or a fast host link (~5)". That was a false
> choice, arrived at by looking only at the Minimal 64x4 and at colormin's `backplane.md`
> §5 — both of which build a UART out of discrete logic because their machines have no
> room for anything else. §4.1 and §4.2 explain why neither applies here.

---

## 0. Summary — the verdict in one table

| Question | Answer | § |
|---|---|---|
| **Discrete logic, like the other cards?** | **No.** The other cards are discrete because no period chip does what they need. For serial, one does — and it is *older* than most of the 74HC parts around it. | §3, §4 |
| **Which part?** | **6551 ACIA.** Four registers, on-chip baud generator, crystal is the only external component, full modem control, `/IRQ` out. | §3.1 |
| **Is a 6502-family part sane on a 6809 bus?** | **It shipped.** The CoCo's own Deluxe RS-232 Pak is a 6551 decoding four ports on a 6809 bus, interrupting through `*CART`. | §3.2 |
| **Which 6551, though?** | ⚠ **Not the current-production `W65C51N`** — two documented defects make both polling *and* interrupts unsafe. `R6551A` or a CMOS `G65SC51`. | §3.3 |
| **Baud rates** | 50–19,200 from the standard crystal. A 2× crystal doubles them and **buys nothing usable** — see below. | §5 |
| **What actually limits throughput?** | **No FIFO ⇒ one interrupt per byte.** At 19,200 baud that is 1,920 interrupts/s — 9 % of the CPU optimistically, 37 % pessimistically. | §5 |
| **Practical ceiling** | **4800–19,200 baud**, pinned by the same unmeasured NitrOS-9 dispatch cost as `ps2.md` §14 item 3. One measurement settles both. | §5 |
| **Where in the `$FF` map?** | **`$FF54`–`$FF57`, four bytes** — and **this closes the map exactly, with zero bytes left.** | §7.1 |
| **IC count** | **3** — ACIA, `MAX232`, decode GAL. Plus a crystal and a DE-9. | §9 |

**Net: 3 ICs**, against video's 33, audio's 35 and PS/2's 9.

---

## 1. Sources and confidence

| Claim class | Source | Confidence |
|---|---|---|
| 6551 has an on-chip programmable baud generator, 15 rates 50–19,200 baud, crystal the only external component, independent of the CPU clock | MOS/Rockwell 6551 datasheet material; Wikipedia *MOS Technology 6551*; Jeff Tranter, *The 6551 ACIA* | **corroborated across independent sources** |
| **The CoCo Deluxe RS-232 Pak (26-2226, 1983) is a 6551 + 1.8432 MHz crystal, directly decoding four ports, interrupting via `*CART`** | CoCopedia, *Deluxe RS-232 Program Pak*; Tandy *Deluxe RS-232 Operation Manual* | **corroborated** — this is the §3.2 precedent |
| `W65C51N`: TDRE never indicates empty; and accessing the chip mid-transmission stops transmission | WDC datasheet erratum (2014); 6502.org forum threads; Wikipedia *WDC 65C51* | **corroborated, and consistent across sources** |
| Exact 6551 register bit layouts (§7.2) | recalled | ⚠ **no 6551 datasheet in `reference/` — §13 item 1.** Do not cut a board from §7.2. |
| NitrOS-9 ships a 6551 driver (`sc6551`) | recalled; not confirmed by search | ⚠ **§13 item 2.** The *hardware* precedent is verified; the driver claim is not. |
| Non-standard crystals to multiply the baud rates | 6502.org community practice | ⚠ out of the part's specification |
| NitrOS-9 interrupt dispatch cost | ⚠ **guessed at 100–400 cycles**, as in `ps2.md` §3.1. §5's whole ceiling rests on it | **unverified — §13 item 3** |

---

## 2. What this card is for

Worth stating, because it decides how much of the 6551's capability is wired up.

| Use | Rate needed | Wanted? |
|---|---|---|
| **Terminal / console** — NitrOS-9's second `/t` device | 9600 comfortable | yes |
| **Modem** — 1989–90 means 1200/2400 baud | 2400 | yes, and it needs §8's second package |
| **File transfer** to a modern host (Kermit, XMODEM) | as fast as §5 allows | yes |
| **Printer** | 9600 | falls out |
| **Loading system software** | — | **no** — that is the disk controller's job |

That last row is why this card is not the Minimal 64x4's (§4.2). Slu4's machine has no disk,
so serial *is* the mass-storage path and 500 kbps is worth building hardware for. This
machine boots NitrOS-9 from floppy.

---

## 3. The verdict: a 6551 ACIA

### 3.1 What you get for one package

| | |
|---|---|
| Registers | **four** — data, status, command, control |
| Baud generator | **on-chip**, 15 programmable rates, 50–19,200 |
| External timing parts | **a 1.8432 MHz crystal.** That is the whole list. |
| Framing | 5/6/7/8 data bits, 1/1.5/2 stop, odd/even/mark/space/none parity |
| Modem control | `/RTS`, `/DTR` out; `/CTS`, `/DSR`, `/DCD` in |
| Interrupt | open-drain `/IRQ` out — joins the line `ps2.md` §3.1 established |
| Buffering | **none.** One byte each way. This is §5. |

The baud generator is the part that matters for the chip count. colormin's
`backplane.md` §5 spends a canned oscillator, a `'393`/`'161` divider tree, a `'151` rate
mux, a `'273` rate register and a `'74` resynchroniser — **five packages** — to produce
what the 6551 does with a crystal and two capacitors, and the 6551 throws in the UART.

### 3.2 The precedent — this exact circuit shipped on this exact bus

The obvious objection is that the 6551 is a 6502-family part with a `φ2` interface, and
this is a 6809 machine. **Tandy shipped it anyway, on a CoCo, in 1983:** the Deluxe RS-232
Program Pak (26-2226) is a 6551 with a 1.8432 MHz crystal, directly decoding four ports,
sending interrupts through the cartridge port's `*CART` line.

On a 6809, `E` *is* `φ2` — same shape, same relationship to `R/W` and to valid data. This
is not a clever adaptation; it is what the part was already doing in this family of
machines.

**Two things follow.** First, the electrical risk on this card is close to zero, which is
not true of anything else in this project. Second, if NitrOS-9's CoCo `sc6551` driver
exists (⚠ §13 item 2) it should work against §7's register map with a base-address change
and nothing else — the same posture as `graphics.md` §6.2's GIME-compatible MMU, for once
obtained without designing for it.

### 3.3 Which 6551 — and the trap in the current-production part

⚠ **Do not specify the `W65C51N`**, which is the one still in production and therefore the
one you will be offered. Two documented defects, and between them they remove every way of
knowing when to send the next byte:

1. **TDRE never indicates empty.** Bit 4 of the status register reads permanently ready, so
   polling it always says "send now" and the transmitter is overrun.
2. **Accessing the chip while it is transmitting stops the transmission.** So the interrupt
   route is unsafe too.

WDC's own workaround is a **software delay loop** sized to the baud rate, which on a
machine with a `/FIRQ` replayer tick means blocking the CPU for a character time on every
byte. That is not acceptable here.

**Specify the NMOS `R6551A` or a CMOS `G65SC51`** — the pre-WDC parts, both of which
implement TDRE correctly. Both are out of production and both are readily available used,
which is the same posture `audio.md` §6.3 takes for the `AD7545A`, inverted: there the
period part was the problem and the modern one the fix; here it is the other way round.

> **Speed grade matters too.** `E` is 2.0979 MHz (`machine.md` §1). A 1 MHz `R6551` is out;
> a 2 MHz `R6551A` is 5 % over; a CMOS `G65SC51` at 2–4 MHz is comfortable. **Prefer the
> CMOS part.** If only a 2 MHz part can be found, the backplane's `/WAIT` ("stretch E",
> `graphics.md` §17) is the escape hatch — but stretching `E` stretches it for the whole
> machine, including the replayer, so treat that as a last resort rather than a plan.

---

## 4. The alternatives, and why each is rejected

### 4.1 A discrete UART with a real baud generator — ~14 ICs

colormin's `backplane.md` §5 designs exactly this: the Minimal 64x4's UART transplanted,
plus a 1.8432 MHz oscillator, a `'393`/`'161` divider tree, a `'151` selecting the bit
clock from a `RATE[2:0]` field, a `'273` holding it, and a `'74` resynchronising the
data-ready flag because the oscillator is asynchronous to the bus.

**It is a good design for a machine that has no I/O window to spend.** The Minimal 64x4
reaches its UART through microcode strobes (`/TI`, `/TO`, `UART_DR`), so the card costs it
*zero* addresses — and when addresses are free and packages are the currency, building the
UART out of logic is rational.

Here the currency is reversed. This machine has 64 bytes of I/O window (§7.1) and no
shortage of board area, and a 6551 costs **four addresses and one package** against
fourteen packages and a register map somebody has to invent. Reject.

### 4.2 The Minimal 64x4's fixed-rate UART — 5 ICs

`'165` transmit shifter, `'595` receive shift-and-store, `'161` and `'193` for bit timing,
one `'00` of glue — genuinely five packages, and the same `'595` storage-register trick
`ps2.md` §4.1 borrows.

**It is five packages because the rate is fixed.** The sheet says so: *"UART bitrate
500 kbps, 1 start bit, 7 data bits, 2 stop bits, new line LF, transmit line delay ~10 ms."*
One rate, seven data bits, no divisor register, inter-line pacing in software. It is a fast
private link to a host PC for loading programs, not an RS-232 port — it cannot talk to a
modem, a terminal or a printer, because none of those run at 500 kbps 7N2.

§2 says this machine loads from disk, so the one job that design is optimised for is a job
this card does not have. Reject — but note that **it is still five packages against three**,
so even on its own terms it does not win.

### 4.3 A 6850 ACIA plus an MC14411 — the Motorola-family answer

Tempting on family grounds: this is a 6809 machine, and the 6850 is Motorola's ACIA with
only two registers.

But **the 6850 has no baud generator** — it takes an external clock at 16× or 64× the bit
rate. So it needs an `MC14411` bit-rate generator (which outputs all rates simultaneously)
plus a `'151` to select one, plus the rate register to drive it: **four packages to the
6551's one**, for a part with fewer features and, unlike §3.2, no shipped CoCo precedent.

Family tidiness is not worth three packages and a register map. Reject.

### 4.4 Bit-banging on two port bits — 0 ICs

The CoCo's own built-in serial is a software "bit-banger" on PIA1, and NitrOS-9 drives it.
Zero hardware is hard to argue with.

**Reject, and the reason is specific to this machine.** Bit-banging needs the CPU to hold
timing to a fraction of a bit period. `audio.md` §8.1 puts a replayer tick on `/FIRQ`,
which on a 6809 **outranks `/IRQ` and cannot be masked by it** — so a replayer tick
arriving mid-character corrupts the bit timing and there is no priority arrangement that
prevents it. A machine that plays music cannot bit-bang serial. That is worth recording
because it is the one place the audio card's design constrains another card's.

---

## 5. Throughput — the FIFO is what is missing, not the baud rate

**This is the engineering content of the card**, and it is the reason a faster crystal is
not the upgrade it looks like.

The 6551 holds **one byte** in each direction. Every received byte therefore costs one
interrupt, and 8N1 framing means ten bits per byte:

| Baud | Bytes/s | Interrupts/s | @100 cyc | @400 cyc ⚠ |
|---|---|---|---|---|
| 300 | 30 | 30 | 0.1 % | 0.6 % |
| 1200 | 120 | 120 | 0.6 % | 2.3 % |
| **2400** (period modem) | 240 | 240 | **1.1 %** | **4.6 %** |
| 4800 | 480 | 480 | 2.3 % | 9.2 % |
| **9600** (terminal) | 960 | 960 | **4.6 %** | **18.3 %** |
| **19200** (the part's max) | 1920 | 1920 | **9.2 %** | **36.6 %** |
| 38400 (2× crystal) | 3840 | 3840 | 18.3 % | 73.2 % |

Compare `audio.md` §13's replayer at 2.7 %.

**So the practical ceiling is 4800–19,200 baud**, and which end depends entirely on
NitrOS-9's interrupt dispatch cost — **the same unmeasured number that decides whether
`ps2.md`'s FIFO comes back** (`ps2.md` §14 item 3). One measurement settles both cards, and
§12 step 2 is that measurement.

**Which is why the 2× crystal is a trap.** Community practice runs the 6551 with a
3.6864 MHz crystal to double every rate, ⚠ out of spec but widely done. It would give
38,400 baud — at 73 % of the CPU. **The baud generator was never the limit.** Do not
specify a non-standard crystal; specify 1.8432 MHz and spend the effort on §12 step 2
instead.

**Two things do help, and both are free:**

- **Hardware flow control.** The 6551 drives `/RTS` and reads `/CTS`. With `/RTS` wired
  (§8) an overrun becomes *throttling* rather than lost data — the far end stops and waits.
  This turns "too fast" from a correctness bug into a performance number, and it is the
  single most valuable thing to wire on the connector.
- **Set the rate to the job.** A terminal at 9600 costs 4.6 %; a modem at 2400 costs 1.1 %.
  Nothing forces 19,200.

> **If a genuinely fast link is ever needed**, the fallback is the one `ps2.md` §5 keeps in
> reserve: two `CD40105B` between the ACIA and the bus, 16 bytes deep, cutting interrupts
> by 16×. **+2 ICs, and the card is 5.** Do not build it before §12 step 2 says it is
> needed — that is exactly the mistake `ps2.md` §3.1 records.

---

## 6. Bus interface

Straightforward, and §3.2 is the reason to expect it to be.

| 6551 pin | Connect to |
|---|---|
| `φ2` | backplane `E` |
| `R/W` | backplane `R/W` |
| `CS0`, `/CS1` | the decode GAL, from geographic `/IOSEL` and `A2`–`A5` |
| `RS0`, `RS1` | `A0`, `A1` |
| `D0`–`D7` | backplane `D0`–`D7` |
| `/IRQ` | backplane `/IRQ`, open-drain — third card on the line after video and PS/2 |
| `/RES` | backplane `/RESET` |
| `XTLI`, `XTLO` | 1.8432 MHz crystal + two load capacitors |

The 6551 decodes its own four registers from `RS0`/`RS1`, so the GAL only has to select the
four-byte window inside the slot — a handful of terms, and the base address becomes a
jumper like every other card's.

---

## 7. Register map

### 7.1 Placement — and the `$FF` map is now **full**

**Propose `$FF54`–`$FF57`**, the four bytes immediately above PS/2.

| Window | Size | Owner |
|---|---|---|
| `$FF40`–`$FF4F` | 16 | audio — `audio.md` §9.1 |
| `$FF50`–`$FF53` | 4 | PS/2 — `ps2.md` §3.2 |
| **`$FF54`–`$FF57`** | **4** | **serial — this document** |
| `$FF58`–`$FF5F` | 8 | disk controller, reserved |
| `$FF60`–`$FF7F` | 32 | video — `graphics.md` §13 |
| | **64** | **of 64 in the `$FF40`–`$FF7F` geographic decode** |

> ### ⚠ This allocation closes the I/O map exactly. There are **zero** bytes left.
>
> `graphics.md` §17 already said *"widen the window now — it is a decode term today and a
> board respin later."* That advice has stopped being prudent and become **blocking**:
> after this card there is no room for a second serial port, a third PS/2 port, a network
> interface, a SCSI controller, or anything else anybody thinks of later — and the disk
> controller's eight bytes are a guess made on its behalf by two cards that took theirs
> first.
>
> **`machine.md` §5 item 1 must be resolved before the backplane is laid out**, and it is
> now the highest-priority open item in the machine rather than a note. §13 item 4.

### 7.2 The four registers

⚠ **Recalled layouts — §13 item 1.** Correct against a datasheet before cutting a board.

| Off | Name | R/W | Function |
|---|---|---|---|
| `+$0` | `DATA` | R/W | read: received byte, clears `RDRF`. write: transmit byte, clears `TDRE` |
| `+$1` | `STATUS` | R | §7.3 |
| `+$1` | `RESET` | W | programmed reset — the written value is ignored |
| `+$2` | `COMMAND` | R/W | parity mode, echo, transmitter interrupt control and `/RTS` state, receiver interrupt disable, `/DTR` state |
| `+$3` | `CONTROL` | R/W | baud rate select, receiver clock source, data-word length, stop bits |

### 7.3 `STATUS`

| Bit | Meaning |
|---|---|
| 0 | parity error |
| 1 | framing error |
| 2 | **overrun** — a byte arrived before the last was read. §5's failure mode |
| 3 | `RDRF` — receive data register full |
| 4 | `TDRE` — transmit data register empty. ⚠ **broken on the `W65C51N`, §3.3** |
| 5 | `/DCD` state |
| 6 | `/DSR` state |
| 7 | interrupt pending — **reading `STATUS` clears it** |

Reading `STATUS` clears the interrupt, so the `/IRQ` handler's first action on this card is
a `STATUS` read, and the error bits it carries must be consumed in that same read.

---

## 8. Level shifting and the connector

**`MAX232` (Maxim, 1987)** — RS-232 line driver and receiver with an on-chip charge pump,
so the card needs **only +5 V**. The period-correct alternative is a `1488`/`1489` pair,
which is two packages *and* wants ±12 V that the backplane does not carry
(`graphics.md` §17's signal list). The `MAX232` is both newer-feeling and simpler; it is
in period, and it wins.

One `MAX232` provides **two drivers and two receivers**:

| Direction | Signal | Purpose |
|---|---|---|
| out | `TxD` | data |
| in | `RxD` | data |
| out | `/RTS` | **hardware flow control — §5's mitigation** |
| in | `/CTS` | hardware flow control |

**Connector: DE-9 male, wired as DTE** — the AT convention, 1984, in period, and what a
straight-through cable to a modern USB-serial adapter expects.

> **Full modem control needs a second package.** `/DTR` out plus `/DCD` and `/DSR` in do
> not fit the first `MAX232`'s two-and-two. Add a second `MAX232` (or one `MAX238`) **if
> §2's modem row matters**, and the card is 4 ICs.
>
> ⚠ **If they are left off, tie the 6551's `/DCD` and `/DSR` inputs *low* (asserted), not
> high.** They are active-low "the far end is there" inputs; deasserting them can leave the
> transmitter permanently blocked and the status register reporting a carrier that never
> arrives. This is the classic way to build a serial card that does nothing at all.

---

## 9. Chip budget

| # | Part | Function |
|---|---|---|
| 1 | `G65SC51` (or `R6551A`) | the ACIA — **not `W65C51N`**, §3.3 |
| 2 | `MAX232` | RS-232 levels for `TxD`/`RxD`/`/RTS`/`/CTS`, +5 V only |
| 3 | GAL22V10 | four-byte window decode from geographic `/IOSEL`, base-address jumper |

**Total: 3.** Plus a 1.8432 MHz crystal, two load capacitors, four charge-pump capacitors
and a DE-9.

**4** with §8's second `MAX232` for full modem control. **5** with §5's `CD40105B` FIFO
pair, and only if §12 step 2 says so.

For scale: video 33, audio 35, PS/2 9, serial **3**. The card is small because the problem
was solved commercially in 1977 and this project's period rules — which bar CPLDs and
FPGAs, not LSI — allow the solution.

---

## 10. Software

### 10.1 If `sc6551` exists, use it

⚠ §13 item 2. NitrOS-9's CoCo support is believed to include a 6551 driver for the RS-232
Pak. §3.2's precedent means §7's register map is the *same* map that driver already talks
to, so the port should be a base-address change. **Check this before writing anything** —
it is potentially the entire software cost of the card.

### 10.2 The interrupt handler

Third card on `/IRQ`, after video's VBL/raster compare and PS/2. The chain is:

```
        lda   SERSTAT        ; the read clears this card's interrupt
        bita  #%00001000     ; RDRF - a byte arrived?
        ...
        bita  #%00000100     ; overrun - we were too slow (5)
```

`STATUS` must be read whether or not this card caused the interrupt, because that read is
what clears it — a shared `/IRQ` line means every handler in the chain looks.

### 10.3 Initialisation

1. Write `RESET` (`+$1`) — value ignored.
2. `CONTROL`: baud rate, 8 data bits, 1 stop bit. **Pick the rate from §5's table, not from
   the part's maximum.**
3. `COMMAND`: no parity, receiver interrupt enabled, transmitter interrupt as the driver
   prefers, `/DTR` and `/RTS` asserted.
4. Read `STATUS` once to clear any pending interrupt before enabling `/IRQ`.

---

## 11. Period audit

| Part | First available | Verdict |
|---|---|---|
| 6551 ACIA | **1977** | in period by a decade; **older than the 74HC family around it** |
| 6551 on a CoCo | **1983** (Tandy 26-2226) | not merely plausible — commercially shipped |
| `MAX232` | 1987 | in period, contemporary with the VGA connector `graphics.md` §15 justifies |
| GAL22V10 | 1986 | in period; the machine already uses 10 |
| DE-9 serial connector | 1984 (IBM PC/AT) | in period |
| `CD40105B` *(fallback only, §5)* | early 1980s | in period; sourcing is the problem, not the date |

**This is the most period-honest card in the machine.** Video needs the 25.175 MHz
VGA-clock argument, audio needs the `AD7545A` → `LTC7545A` substitution, PS/2 needs the
1987 interface date. Serial needs nothing — every part predates the target window, and the
central one shipped inside a CoCo.

---

## 12. Build order

| # | Step | Exit criterion |
|---|---|---|
| 0 | **Resolve `machine.md` §5 item 1 — the `$FF` map is full** (§7.1). This is no longer a note | the window is widened, or the machine is declared closed to further cards |
| 1 | **Get a datasheet** and correct §7.2/§7.3 against it; source an `R6551A` or `G65SC51`, **not a `W65C51N`** | §13 items 1 and 5 closed |
| 2 | **Measure NitrOS-9's interrupt dispatch cost** — shared with `ps2.md` §13 step 8 | §5's ceiling becomes a number; the FIFO question is settled for both cards |
| 3 | **Breadboard the ACIA on the bus exerciser** (`graphics.md` §16.1) — no 6309 core needed | registers read back; the baud generator runs; `TDRE` behaves, confirming the part is not a `W65C51N` |
| 4 | **Loopback at 9600**, `TxD` to `RxD` | a byte written appears in the receive register with no framing or parity error |
| 5 | **A real terminal**, then a real modem | characters both ways; `/RTS`/`/CTS` observed to throttle when the driver stalls |
| 6 | **NitrOS-9 driver** — `sc6551` if it exists, else write one | a login shell on `/t2` under a running replayer, with **no lost replayer ticks at the §5 rate** |
| 7 | **Sustained transfer at the §5 ceiling** | measured overrun count of zero with flow control on, and a recorded CPU cost |

**Step 2 gates step 6**, and it is the same measurement the PS/2 card is waiting on.

---

## 13. Open items

1. **No 6551 datasheet is in `reference/`.** §7.2 and §7.3 are recalled bit layouts.
   **Blocks §12 step 3** — do not cut a board against them.

2. **`sc6551` is unconfirmed** (§10.1). The hardware precedent of §3.2 is verified; the
   claim that NitrOS-9 ships a driver for it is not. This is the difference between a card
   with no software cost and a card that needs a driver written, so it is worth ten minutes
   in the NitrOS-9 source tree.

3. **NitrOS-9's interrupt dispatch cost is a guess**, 100–400 cycles, and §5's entire
   ceiling rests on it — 19,200 baud is either 9 % of the CPU or 37 %. **Shared with
   `ps2.md` §14 item 3; one measurement closes both.**

4. **The `$FF` map is full** (§7.1). Now the machine's highest-priority open item, not this
   card's. Raised to `machine.md` §5 item 1.

5. **Part sourcing.** `R6551A` and `G65SC51` are out of production; the in-production
   `W65C51N` is defective for this use (§3.3). Confirm a source before committing, and
   record it — this is the one part on the card that cannot be substituted with a
   jellybean.

6. **Speed grade** (§3.3). `E` at 2.0979 MHz is 5 % over a 2 MHz `R6551A`. Prefer CMOS;
   the `/WAIT` fallback stretches `E` for the whole machine and should not be planned on.

7. **One port only.** §7.1 has no room for a second, and §2 does not need one. If a second
   is ever wanted it is item 4's problem first, not a circuit problem.

---

## 14. Sources and cross-references

| | |
|---|---|
| [`machine.md`](../../../docs/machine.md) | §3 the `$FF` map this card closes; §5 item 1, now blocking |
| [`ps2.md`](../../ps2/docs/ps2.md) | §3.1 the `/IRQ` decision this card follows; §5 the FIFO fallback; §14 item 3 the shared measurement |
| [`audio.md`](../../../audio/docs/audio.md) | §8.1 why `/FIRQ` outranks `/IRQ`, which is what kills §4.4 |
| [`graphics.md`](../../../video/docs/graphics.md) | §16.1 the bus exerciser; §17 the backplane and the widen-the-window warning |
| **CoCopedia, *Deluxe RS-232 Program Pak*; Tandy *Deluxe RS-232 Operation Manual*** | §3.2's precedent — a 6551 on a 6809 bus, shipped |
| Wikipedia, *MOS Technology 6551* and *WDC 65C51*; Jeff Tranter, *The 6551 ACIA*; 6502.org forum | §3.1 and §3.3 |
| `~/code/colormin/docs/backplane.md` §5 | the discrete alternative §4.1 rejects |
| **Minimal 64x4 Rev 1.4 Redux, sheet 2/9 "UART"** | Carsten Herting (slu4), CC BY-NC-SA 4.0. The fixed-rate design §4.2 rejects |
