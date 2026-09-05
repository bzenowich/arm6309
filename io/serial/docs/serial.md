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
| **Which 6551, though?** | ⚠ **Not the current-production `W65C51N`** — two documented defects make both polling *and* interrupts unsafe. `R6551A` or a CMOS `G65SC51`, and **a 4 MHz grade if fast-E mode is ever wanted.** | §3.3, §3.4 |
| **Does the card survive the machine's faster E rate?** | **Only with a 4 MHz `G65SC51`.** The card is specified at ÷12 (E = 2.0979 MHz). ÷8 "fast-E" mode puts 3.1469 MHz on `φ2` — 57 % over a 2 MHz part. | §3.4 |
| **Baud rates** | 50–19,200 from the standard crystal. A 2× crystal doubles them and **buys nothing usable** — see below. | §5 |
| **What actually limits throughput?** | **No FIFO ⇒ one interrupt per byte.** At 19,200 baud that is 1,920 interrupts/s receiving — 9 % of the CPU optimistically, 37 % pessimistically — and **double that full duplex.** | §5 |
| **Practical ceiling** | **4800–19,200 baud**, pinned by the same unmeasured NitrOS-9 dispatch cost as `ps2.md` §14 item 3. One measurement settles both. | §5 |
| **Where in the `$FF` map?** | **`$FF54`–`$FF57`, four bytes** — and **this closed the map.** The storage card has since returned four. | §7.1 |
| **Is `/RTS` flow control automatic, as §5 used to say?** | **No — not on a 6551.** `/RTS` is a command-register bit the ISR drives at a ring-buffer high-water mark. `/CTS` *is* automatic, so the transmit direction is fine. | §5.1 |
| **IC count** | **3** — ACIA, `MAX232`, decode GAL. Plus a crystal and a DE-9. | §9 |

**Net: 3 ICs**, against PS/2's 11 (`ps2.md` §9), audio's (`audio.md` §10) and the video
card's (`graphics.md` §14).

---

## 1. Sources and confidence

| Claim class | Source | Confidence |
|---|---|---|
| 6551 has an on-chip programmable baud generator, 15 rates 50–19,200 baud, crystal the only external component, independent of the CPU clock | MOS/Rockwell 6551 datasheet material; Wikipedia *MOS Technology 6551*; Jeff Tranter, *The 6551 ACIA* | **corroborated across independent sources** |
| **The CoCo Deluxe RS-232 Pak (26-2226, 1983) is a 6551 + 1.8432 MHz crystal, directly decoding four ports, interrupting via `*CART`** | CoCopedia, *Deluxe RS-232 Program Pak*; Tandy *Deluxe RS-232 Operation Manual* | **corroborated** — this is the §3.2 precedent |
| `W65C51N`: TDRE never indicates empty; and accessing the chip mid-transmission stops transmission | WDC datasheet erratum (2014); 6502.org forum threads; Wikipedia *WDC 65C51* | **corroborated, and consistent across sources** |
| Exact 6551 register bit layouts (§7.2) | recalled | ⚠ **no 6551 datasheet in `reference/` — §13 item 1.** Do not cut a board from §7.2. |
| NitrOS-9 ships a 6551 driver (`sc6551`) | NitrOS-9's CoCo 3 source tree ships an SCF driver named `sc6551` for the Deluxe RS-232 Pak | **corroborated** — the driver exists. What is *not* confirmed is that §7.2's recalled register map matches the one it talks to. §13 item 2 |
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
not true of anything else in this project. Second, **NitrOS-9's CoCo 3 tree does ship an
SCF driver called `sc6551` for exactly this Pak**, so it should work against §7's register
map with a base-address change and nothing else — the same posture as `graphics.md`
§6.3's MMU, for once obtained without designing for it. That is a stronger claim than the
previous revision made (§13 item 2 is graded up accordingly), and the ten-minute check it
prescribes is still worth doing, because what remains unconfirmed is not the driver's
existence but whether §7.2's **recalled** register layout is the layout it talks to.

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

> **Speed grade matters too, and it is its own section now — §3.4.** In short: `E` is
> 2.0979 MHz (`machine.md` §1), a 1 MHz `R6551` is out, a 2 MHz `R6551A` is 5 % over, and
> a CMOS `G65SC51` at 2–4 MHz is comfortable. **Prefer the CMOS part.** If only a 2 MHz
> part can be found, the backplane's `/WAIT` (`graphics.md` §17) is the escape hatch — but
> a `/WAIT` holds `E` for the whole machine, including the replayer, so treat that as a
> last resort rather than a plan.
>
> ⚠ **This paragraph used to call `/WAIT` "stretch E".** It is a **wait state**, and the
> word "stretch" is retired on this card: `machine.md` used "stretch mode" for the
> ÷8 *faster* rate, so the two documents were using one word for opposite things. Per the
> project-wide naming decision: **`/WAIT` is a wait state; the ÷8 rate is "fast-E mode".**

### 3.4 E-rate compatibility — and the ÷8 rate the previous revision never checked

**The 6551 sits directly on `E` as its `φ2`** (§6). It is therefore the one part in this
machine whose rating is indexed to the CPU clock rate, and the machine has two clock
rates.

| Machine rate | `E` | Against a 2 MHz `R6551A`/`G65SC51-2` | Against a 3 MHz grade | Against a 4 MHz grade |
|---|---|---|---|---|
| **÷12 — specified** (`machine.md` §1) | **2.0979 MHz** | **5 % over** | comfortable | comfortable |
| ÷8 — **fast-E mode, experimental** | **3.1469 MHz** | **57 % over** | **5 % over** | comfortable |

Arithmetic: 25.175 / 8 = 3.1469 MHz; 3.1469 / 2.0 = 1.573, so **57 % over** a 2 MHz part;
3.1469 / 3.0 = 1.049, so 5 % over a 3 MHz part — the same marginal-but-usual overclock the
÷12 rate asks of a 2 MHz part, and not a margin to stack on top of an out-of-production
device of unknown provenance.

**So, the card's compatibility line:**

> **Specified at ÷12 only.** This card is guaranteed at `E` = 2.0979 MHz. **Fast-E mode
> (÷8, 3.1469 MHz) requires a genuine 4 MHz-grade `G65SC51`**; with any 2 MHz part it is
> out of spec by 57 %, and with a 3 MHz part it is out of spec by 5 % with no headroom
> left for the ÷12 case's own 5 %. This matches the machine-level position — ÷8 is
> **experimental and not guaranteed**, and this is one of three independent reasons why
> (`machine.md` §5; the others are the video card's VRAM read-back and the real
> HD63C09E's 333 ns `t_cyc` minimum).

**The failure mode is worse than "out of spec".** Fast-E is *software-selectable*, so
nothing stops a program flipping the machine into it **with the serial driver live and a
transfer in flight** — which takes the ACIA out of its rating mid-session, with no reset,
no notification, and a symptom (occasional corrupted bytes) indistinguishable from a bad
cable. If fast-E mode is ever exposed to user software, the driver needs either a 4 MHz
part underneath it or a hook that quiesces the port across the transition.

> ⚠ **The previous revision worked the speed-grade numbers only at 2.0979 MHz** and did
> not mention ÷8 at all, in a document that otherwise re-derives everything. Corrected per
> the 2026-09-04 design review (IO-S1).

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
interrupt, and 8N1 framing means ten bits per byte.

**This table is half-duplex, receive-only** — read the next one before quoting it:

| Baud | Bytes/s | Rx interrupts/s | @100 cyc | @400 cyc ⚠ |
|---|---|---|---|---|
| 300 | 30 | 30 | 0.1 % | 0.6 % |
| 1200 | 120 | 120 | 0.6 % | 2.3 % |
| **2400** (period modem) | 240 | 240 | **1.1 %** | **4.6 %** |
| 4800 | 480 | 480 | 2.3 % | 9.2 % |
| **9600** (terminal) | 960 | 960 | **4.6 %** | **18.3 %** |
| **19200** (the part's max) | 1920 | 1920 | **9.2 %** | **36.6 %** |
| 38400 (2× crystal) | 3840 | 3840 | 18.3 % | 73.2 % |

**And almost nothing this card is for is half duplex.** The 6551 raises `/IRQ` on `TDRE`
as well as `RDRF`, so an interrupt-driven transmitter costs **one more interrupt per byte
sent**. §2's use list is three rows of full duplex:

- a **terminal with local echo off** — every character received is a character the host
  echoes back, so 1:1;
- **XMODEM/Kermit** — the ACK/NAK per block is light, but the *sending* direction of a
  file transfer is a full-rate transmit stream with a light return channel, and it costs
  exactly the same per byte;
- a **login shell**, which is a terminal.

| Baud | Full-duplex interrupts/s | @100 cyc | @400 cyc ⚠ |
|---|---|---|---|
| **2400** | 480 | 2.3 % | **9.2 %** |
| 4800 | 960 | 4.6 % | 18.3 % |
| **9600** | 1,920 | **9.2 %** | **36.6 %** |
| **19200** | **3,840** | **18.3 %** | **73.2 %** |

Compare `audio.md` §13's replayer at 2.7 %.

> ⚠ **The previous revision's table counted receive interrupts only** and drew the ceiling
> from it. Corrected per the 2026-09-04 design review (IO-S3): 19,200 baud full duplex is
> 3,840 interrupts/s, which at the pessimistic dispatch figure is **73 % of the CPU** —
> the number the previous revision attached to the 38,400 "trap" row is what 19,200
> actually costs a terminal.

**The practical ceiling is still 4800–19,200 baud, but the conclusion moves toward the low
end.** 9600 full duplex is 9.2 %/36.6 % — the figures the old table showed for 19,200
receive-only, and a rate this card was calling comfortable. Which end you land on depends
entirely on NitrOS-9's interrupt dispatch cost — **the same unmeasured number that decides
whether `ps2.md`'s FIFO comes back** (`ps2.md` §14 item 3). One measurement settles both
cards, and §12 step 2 is that measurement. Set the rate to the job (§5.2), and treat
19,200 as a file-transfer burst rate rather than a console rate.

**Which is why the 2× crystal is a trap.** Community practice runs the 6551 with a
3.6864 MHz crystal to double every rate, ⚠ out of spec but widely done. It would give
38,400 baud — at 73 % of the CPU. **The baud generator was never the limit.** Do not
specify a non-standard crystal; specify 1.8432 MHz and spend the effort on §12 step 2
instead.

**Two things do help. One of them is free and the other is not what the previous revision
thought it was.**

### 5.1 Flow control — `/CTS` is automatic, `/RTS` is software over a hardware wire

> ### ⚠ "An overrun becomes throttling rather than lost data" describes a 16550, not a 6551. Superseded 2026-09-04.
>
> **The bullet below was wrong, and it was called the single most valuable thing to wire:**
>
> > - **Hardware flow control.** The 6551 drives `/RTS` and reads `/CTS`. With `/RTS`
> >   wired (§8) an overrun becomes *throttling* rather than lost data — the far end stops
> >   and waits. This turns "too fast" from a correctness bug into a performance number,
> >   and it is the single most valuable thing to wire on the connector.
>
> **On a 6551, `/RTS` is a bit in `COMMAND` (§7.2). It is not driven by the receiver.**
> Nothing in the part connects "the receive holding register is full" to the `/RTS` pin;
> the 1-byte holding register filling produces `RDRF`, an interrupt, and — if nobody
> reads it in time — the overrun bit. The far end is never told. Found in the 2026-09-04
> design review (IO-S2).

**What is actually true**, and it is still worth wiring, just differently:

| Direction | Mechanism | Automatic? |
|---|---|---|
| **Transmit — `/CTS` in** | the 6551's transmitter **stops on its own** when `/CTS` is deasserted | **yes.** This direction needs nothing from software and is genuinely free |
| **Receive — `/RTS` out** | a `COMMAND` bit the **ISR** writes | **no.** Software flow control carried on a hardware wire |

So the receive direction is: keep a **ring buffer** in system RAM, and have the ISR deassert
`/RTS` when the buffer crosses a **high-water mark** and re-assert it at a low-water mark.
Four consequences, all of which have to be designed for rather than assumed:

1. **Throttling is an ISR action, so it happens at ring-buffer scale, not
   holding-register scale.** The 1-byte holding register cannot be the trigger; by the
   time it is full the next byte is already arriving.

2. **While throttled, interrupt-driven transmit is off.** §7.2's `COMMAND` register packs
   `/RTS` state and transmitter-interrupt control into **one 2-bit field**, and the only
   encoding that deasserts `/RTS` **also disables the transmit interrupt**. A full-duplex
   driver therefore *cannot* throttle receive and keep an interrupt-driven transmit
   running: it must either stop transmitting for the duration of the throttle, or fall
   back to polling `TDRE` while throttled. This is a 6551 quirk with no workaround in
   hardware, and it is the reason to check §7.2 against a real datasheet before writing
   the driver (§13 item 1).

3. **The high-water mark needs headroom, because the far end does not stop instantly.**
   A modern USB-serial bridge has its own FIFO and will deliver **1–2 more characters**
   after `/RTS` drops — more if its driver batches. Leave at least 4 bytes of slack; the
   cost is a few bytes of RAM and the failure it prevents is the one the flow control was
   for.

4. **Flow control does not survive an `/IRQ`-masked window, and the machine has a long
   one.** `ps2.md` §7.1's software transmit runs with `/IRQ` masked for **0.8–1.3 ms**
   every time a caps-lock or num-lock LED is updated. At 19,200 baud one byte time is
   10 / 19,200 = **521 µs**, so a masked LED update spans **1.5–2.5 byte times** and the
   overrun has already happened before any ISR can react — including the ISR that would
   have deasserted `/RTS`. Flow control is a *rate* mitigation; it does nothing about a
   *latency* spike. `ps2.md` §7.1 tabulates the options and the choice is the owner's;
   from this card's side the observable is an overrun count, and §12 step 7 should measure
   it **with the PS/2 card present and LEDs being updated**, not on a quiet bench.

**It is still worth wiring** — `/CTS` costs nothing and works, and ISR-driven `/RTS` turns
a sustained rate mismatch from lost data into a slower transfer. What it is not is a
safety net that makes overruns impossible.

### 5.2 Set the rate to the job

Free, and the more effective of the two. A terminal at 9600 costs 4.6 % half duplex and
9.2 % full at the optimistic dispatch figure — 18.3 % and 36.6 % at the pessimistic one; a
modem at 2400 costs 1.1 % and 2.3 % optimistically, 4.6 % and 9.2 % pessimistically.
**Nothing forces 19,200**, and §5's second table is the argument for not reaching for it by
default.

> **If a genuinely fast link is ever needed**, the fallback is the one `ps2.md` §5.3 keeps
> in reserve: two `CD40105B` between the ACIA and the bus, 16 bytes deep, cutting interrupts
> by 16×. **+2 ICs, and the card is 5.** Do not build it before §12 step 2 says it is
> needed — that is exactly the mistake `ps2.md` §3.1 records.

---

## 6. Bus interface

Straightforward, and §3.2 is the reason to expect it to be.

| 6551 pin | Connect to |
|---|---|
| `φ2` | backplane `E` — **and this is why §3.4's speed grade is a card-level constraint**: the part is clocked by whatever rate the machine is running at |
| `R/W` | backplane `R/W` |
| `CS0`, `/CS1` | the decode GAL, from geographic `/IOSEL` and `A2`–`A5` |
| `RS0`, `RS1` | `A0`, `A1` |
| `D0`–`D7` | backplane `D0`–`D7` |
| `/IRQ` | backplane `/IRQ`, **open-drain — confirm this on the datasheet, §12 step 1** — third card on the line after video and PS/2 |
| `/RES` | backplane `/RESET` — **the whole card comes up in a defined state from one pin**, which is the property `ps2.md` §8.4 had to add two changes to acquire |
| `XTLI`, `XTLO` | 1.8432 MHz crystal + two load capacitors |

The 6551 decodes its own four registers from `RS0`/`RS1`, so the GAL only has to select the
four-byte window inside the slot — a handful of terms, and the base address becomes a
jumper like every other card's.

**Reset is worth one sentence, because it is free here and was not free elsewhere.** The
6551's programmed reset (§10.3 step 1) and its hardware `/RES` both leave the transmitter
and receiver disabled and the interrupt cleared, so a `/RESET` pulse cannot leave this card
holding the shared `/IRQ` low. That is the failure `ps2.md` §8.4 documents on the card next
door, and the reason this row exists in the table rather than being assumed.

**This card is LAST in the shared-`/IRQ` polling chain**, after video's `VSTAT` and PS/2's
`IOSTAT` — `machine.md` §4 records the order, and §7.3 explains why it has to be this way
round. The short version: **reading `STATUS` clears the interrupt and returns the error
bits in the same read**, so this card's handler cannot be a cheap probe. Every other
source on the line can be looked at and passed over; this one cannot be looked at without
being serviced.

---

## 7. Register map

### 7.1 Placement — and the `$FF` map is now **full**

**Propose `$FF54`–`$FF57`**, the four bytes immediately above PS/2.

| Window | Size | Owner |
|---|---|---|
| `$FF40`–`$FF4F` | 16 | audio — `audio.md` §9.1 |
| `$FF50`–`$FF53` | 4 | PS/2 — `ps2.md` §3.2 |
| **`$FF54`–`$FF57`** | **4** | **serial — this document** |
| `$FF58`–`$FF5B` | 4 | storage — `storage/docs/sdcard.md` §6.1, added after this document |
| `$FF5C`–`$FF5F` | 4 | **free** — the storage card returned half the disk reservation |
| `$FF60`–`$FF7F` | 32 | video — `graphics.md` §13 |
| | **64** | **of 64 in the `$FF40`–`$FF7F` geographic decode** |

> ### ⚠ This allocation closed the I/O map. Four bytes have since come back.
>
> **Updated:** `storage/docs/sdcard.md` §6.1 needed only half the disk reservation, so
> `$FF5C`–`$FF5F` is free. The paragraph below stands otherwise — four bytes is one small
> card, once.
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

**That single property fixes this card's position in the shared-`/IRQ` chain: last.**
`machine.md` §4 records the order as **video `VSTAT` → PS/2 `IOSTAT` → serial `STATUS`**,
and the reasoning is asymmetric rather than a matter of priority:

| Source | Can its status be read speculatively? | |
|---|---|---|
| Video `VSTAT` | yes | and it is the system tick, so it is the most frequent source — first for speed, not for correctness |
| PS/2 `IOSTAT` | yes — **no side effects at all** (`ps2.md` §8.1) | can sit anywhere; sits in the middle |
| **Serial `STATUS`** | **no** — the read clears `/IRQ` and consumes `RDRF`, the overrun bit, the parity and framing bits and the `/DSR`/`/DCD` bits in one go | **must be last, and must be serviced where it is read** |

**The consequence for §10.2's handler: no probe-and-defer.** A handler that reads `STATUS`
to decide "not mine" and returns has already destroyed the error bits and dropped the
interrupt; the byte it did not take is still in the receive register and the overrun that
follows is unattributable. Read it once, at the end of the chain, and act on everything it
returns.

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

**Connector: DE-9 male, wired as DTE** — the AT convention, 1984, in period, and the right
choice: it is what a modem (a DCE) expects on the other end of a straight-through cable,
which is §2's modem row.

> ⚠ **"…and what a straight-through cable to a modern USB-serial adapter expects" was
> wrong.** A USB-serial adapter is **also a DTE** — it presents the same DE-9 male pinout
> this card does, driving pin 3 and listening on pin 2, exactly as this card does. Two
> DTEs connected straight through have both transmitters shouting at each other and both
> receivers listening to nothing. **The first cable anyone plugs into this card will be a
> null-modem crossover** (2↔3, 7↔8 for `/RTS`/`/CTS`, 5 straight through), and the bench
> should have one before §12 step 5. A straight-through cable is for the modem.
> Corrected per the 2026-09-04 design review (IO-S4).

> **Full modem control needs a second package.** `/DTR` out plus `/DCD` and `/DSR` in do
> not fit the first `MAX232`'s two-and-two. Add a second `MAX232` (or one `MAX238`) **if
> §2's modem row matters**, and the card is 4 ICs.
>
> ⚠ **If they are left off, tie the 6551's `/DCD` and `/DSR` inputs *low* (asserted), not
> high.** They are active-low "the far end is there" inputs; deasserting them can leave the
> transmitter permanently blocked and the status register reporting a carrier that never
> arrives. This is the classic way to build a serial card that does nothing at all.
>
> **Strapping them low buys a second thing that is easy to miss.** A **transition** on
> either input sets the 6551's interrupt-pending bit, and — unlike the receiver and
> transmitter interrupts — **there is no `COMMAND` bit that masks it.** Strapped low they
> never transition, so they never interrupt, and the two-package card gets a clean
> interrupt source for free.
>
> **The moment the second `MAX232` goes on, that changes**, and it changes silently: with
> a real modem attached, **every carrier drop, every re-train, and every `/DSR` bounce
> raises `/IRQ`** with `RDRF` clear and no error bit set. §10.2's handler must therefore
> read and act on `STATUS` bits 5 and 6 — not because the driver wants modem status, but
> because nothing else will acknowledge the interrupt, and this card is last in the chain
> (§7.3) with nobody behind it to notice. Recorded per the 2026-09-04 design review
> (IO-S5).

---

## 9. Chip budget

| # | Part | Function |
|---|---|---|
| 1 | `G65SC51` (or `R6551A`) | the ACIA — **not `W65C51N`**, §3.3. **Speed grade is part of the specification, not a preference: 2 MHz minimum for ÷12, 4 MHz for fast-E — §3.4** |
| 2 | `MAX232` | RS-232 levels for `TxD`/`RxD`/`/RTS`/`/CTS`, +5 V only |
| 3 | GAL22V10 | four-byte window decode from geographic `/IOSEL`, base-address jumper |

**Total: 3.** Plus a 1.8432 MHz crystal, two load capacitors, four charge-pump capacitors,
a DE-9 — and **a null-modem crossover cable in the bench kit**, §8.

**4** with §8's second `MAX232` for full modem control. **5** with §5's `CD40105B` FIFO
pair, and only if §12 step 2 says so.

**Sourcing note, and it belongs here rather than in §13:** row 1 is the only part on this
card that cannot be substituted with a jellybean, and it now has **two** attributes to
match, not one — *not* a `W65C51N` (§3.3), **and** a speed grade adequate for the E rate
the machine will actually run at (§3.4). A `G65SC51P-2` covers the specified ÷12 rate and
**does not cover fast-E mode**; only a genuine 4 MHz grade does. Record which grade was
bought, because the difference is invisible on the bench at ÷12 and shows up as occasional
corrupted bytes at ÷8.

For scale: PS/2 is 11 (`ps2.md` §9), audio's count is in `audio.md` §10 and the video
card's in `graphics.md` §14; serial is **3**. The card is small because the problem was
solved commercially in 1977 and this project's period rules — which bar CPLDs and FPGAs,
not LSI — allow the solution.

---

## 10. Software

### 10.1 `sc6551` exists — check the register map, then use it

**`sc6551` exists** — NitrOS-9's CoCo 3 tree ships it as an SCF driver for the Deluxe
RS-232 Pak (§1, §3.2, §13 item 2). §3.2's precedent means §7's register map should be the
*same* map that driver already talks to, so the port should be a base-address change.
**Check that before writing anything** — it is potentially the entire software cost of the
card, and the thing to verify is §7.2's recalled bit layout, not the driver's existence.

Two things the stock driver will not do, and both belong to this machine rather than to
the Pak: **§5.1's ring-buffer `/RTS` throttling** (the Pak's driver may or may not
implement a high-water mark, and if it does it inherits the transmit-interrupt conflict of
§5.1 point 2), and **§10.2's modem-status handling** if §8's second `MAX232` is ever
fitted.

### 10.2 The interrupt handler

**Third and last card on `/IRQ`**, after video's `VSTAT` and PS/2's `IOSTAT` — §7.3, and
`machine.md` §4 records the order. The chain ends here:

```
;   ... video VSTAT first, then PS/2 IOSTAT (both side-effect-free probes) ...
        lda   SERSTAT        ; ONE read. It clears this card's interrupt AND
        sta   <SavStat       ; returns every status bit; keep it, do not re-read
        bita  #%00001000     ; RDRF  - a byte arrived
        beq   ChkErr
        ldb   SERDATA        ; take it before anything else, then ring-buffer it
ChkErr  lda   <SavStat
        bita  #%00000111     ; overrun (2), framing (1), parity (0) - all three
        bne   SerErr         ; count them; an overrun is the §5 failure mode
        lda   <SavStat
        bita  #%01100000     ; /DSR (6), /DCD (5) - unmaskable, §8
        bne   SerMdm         ; strapped low they never fire; with a modem they do
```

**Three rules, and they all come from the single-read property (§7.3):**

1. **Read `STATUS` exactly once per interrupt and save it.** The read is what clears
   `/IRQ`, and it consumes the error bits at the same time. A handler that reads it twice
   sees the second read empty and loses whatever the first one reported.
2. **No probe-and-defer.** `STATUS` must be read whether or not this card caused the
   interrupt — a shared `/IRQ` line means every handler in the chain looks — but because
   this read has side effects, looking *is* servicing. That is why the chain is ordered to
   put this card last.
3. **Check the modem-status bits, even though they are strapped inactive.** With §8's
   `/DCD` and `/DSR` tied low they never transition and bits 5–6 never fire. **With §8's
   second `MAX232` and a real modem they fire on every carrier drop and every `/DSR`
   bounce, and no `COMMAND` bit can mask them** — so a handler that only tests `RDRF` and
   the error bits acknowledges the interrupt (the `STATUS` read did that) but takes no
   action and logs nothing, which is an invisible interrupt load rather than a hang.
   Count them at minimum; on a carrier drop, tell the driver.

> ⚠ **The previous revision's sketch checked `RDRF` and overrun only**, and re-read
> `STATUS` for each test. Corrected per the 2026-09-04 design review (IO-S5).

### 10.3 Initialisation

1. Write `RESET` (`+$1`) — value ignored.
2. `CONTROL`: baud rate, 8 data bits, 1 stop bit. **Pick the rate from §5's table, not from
   the part's maximum.**
3. `COMMAND`: no parity, receiver interrupt enabled, transmitter interrupt as the driver
   prefers, `/DTR` and `/RTS` asserted. **Note that the last two are one 2-bit field**, so
   "transmitter interrupt as the driver prefers" and "`/RTS` asserted" are not independent
   choices — §5.1 point 2, and §7.2 must be checked against a datasheet before this line is
   written.
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
| 1 | **Get a datasheet** and correct §7.2/§7.3 against it; source an `R6551A` or `G65SC51`, **not a `W65C51N`**, in a grade §3.4 allows. Four things to look up specifically: **(a) `IRQB` output structure = open drain** — §6 wire-ORs it as the fourth source on a shared line that touches three other cards, and the NMOS parts document it, but the part actually bought will come from one of two out-of-production families; a push-pull variant needs a series diode, and nobody will find that out except by looking. **(b)** the `COMMAND` 2-bit `/RTS`/transmit-interrupt field (§5.1 point 2). **(c)** the `/DSR`/`/DCD` transition interrupt and its absence of an enable bit (§8, §10.2). **(d)** the maximum `φ2` for the exact grade in hand (§3.4) | §13 items 1 and 5 closed; the four lookups recorded in §7.2/§7.3/§3.4 with the datasheet cited |
| 2 | **Measure NitrOS-9's interrupt dispatch cost** — shared with `ps2.md` §13 step 8 | §5's ceiling becomes a number; the FIFO question is settled for both cards |
| 3 | **Breadboard the ACIA on the bus exerciser** (`graphics.md` §16.1) — no 6309 core needed | registers read back; the baud generator runs; `TDRE` behaves, confirming the part is not a `W65C51N` |
| 4 | **Loopback at 9600**, `TxD` to `RxD` | a byte written appears in the receive register with no framing or parity error |
| 5 | **A real terminal** over a **null-modem cable** (§8), then a real modem over a straight-through one | characters both ways; `/CTS` observed to stop the transmitter on its own; **ISR-driven `/RTS` observed to throttle at the ring-buffer high-water mark** — §5.1, and confirm the far end still delivers 1–2 characters after `/RTS` drops |
| 6 | **NitrOS-9 driver** — `sc6551` if it exists, else write one | a login shell on `/t2` under a running replayer, with **no lost replayer ticks at the §5 rate** |
| 7 | **Sustained transfer at the §5 ceiling, full duplex, with the PS/2 card in the backplane and LED updates being sent** (`ps2.md` §7.1, §13 step 9) | measured overrun count with flow control on, and a recorded CPU cost — **and an honest count of the overruns caused by PS/2's masked transmit window, which flow control cannot prevent (§5.1 point 4)**. Zero is not the expected answer at 19,200 |

**Step 2 gates step 6**, and it is the same measurement the PS/2 card is waiting on.
**Step 7 is shared with `ps2.md` §13 step 9** and cannot be run on either card alone.

---

## 13. Open items

1. **No 6551 datasheet is in `reference/`.** §7.2 and §7.3 are recalled bit layouts.
   **Blocks §12 step 3** — do not cut a board against them.

2. **`sc6551` exists — what is unconfirmed is the register map** (§10.1). ~~The claim that
   NitrOS-9 ships a driver for it is unverified.~~ **Graded up 2026-09-04:** NitrOS-9's
   CoCo 3 tree does ship an `sc6551` SCF driver for the Deluxe RS-232 Pak, so §3.2's
   "base-address change and nothing else" posture is likely real. The ten minutes in the
   source tree is still worth spending, but on a different question: does the driver's
   register usage match §7.2's **recalled** layout? That merges this item into item 1.

3. **NitrOS-9's interrupt dispatch cost is a guess**, 100–400 cycles, and §5's entire
   ceiling rests on it — 19,200 baud is either 9 % of the CPU or 37 %. **Shared with
   `ps2.md` §14 item 3; one measurement closes both.**

4. **The `$FF` map is full** (§7.1). Now the machine's highest-priority open item, not this
   card's. Raised to `machine.md` §5 item 1.

5. **Part sourcing.** `R6551A` and `G65SC51` are out of production; the in-production
   `W65C51N` is defective for this use (§3.3). Confirm a source before committing, and
   record it — this is the one part on the card that cannot be substituted with a
   jellybean.

6. **Speed grade, and the fast-E question** (§3.4). `E` at ÷12 is 2.0979 MHz — 5 % over a
   2 MHz `R6551A`; prefer CMOS. **At ÷8 it is 3.1469 MHz, 57 % over, and only a 4 MHz
   `G65SC51` covers it.** The card is specified at ÷12 and fast-E is experimental
   machine-wide, but fast-E is *software-selectable*, so decide whether the driver must
   refuse it, quiesce across it, or whether a 4 MHz part is simply bought. The `/WAIT`
   fallback holds `E` for the whole machine, replayer included, and should not be planned
   on. **Owner's decision; this card cannot make it alone.**

7. **One port only.** §7.1 has no room for a second, and §2 does not need one. If a second
   is ever wanted it is item 4's problem first, not a circuit problem.

8. **The `/IRQ`-masked window on the PS/2 card costs this card data** (§5.1 point 4,
   `ps2.md` §7.1). 0.8–1.3 ms with `/IRQ` off against a 521 µs byte time at 19,200 baud is
   a guaranteed overrun per LED update, and no flow-control arrangement on this card
   prevents it. `ps2.md` §7.1 tabulates four mitigations; **the choice is the owner's**,
   §12 step 7 measures whichever is chosen, and doing nothing is defensible if 19,200 is
   only ever a burst rate.

9. **`IRQB` open drain is assumed, not read** (§6, §12 step 1). The wire-OR onto a line
   shared with three other cards depends on it. NMOS parts document it; the part bought
   may not be one. One datasheet lookup, one diode if the answer is wrong.

---

## 14. Sources and cross-references

| | |
|---|---|
| [`machine.md`](../../../docs/machine.md) | §3 the `$FF` map this card closes; §5 item 1, now blocking |
| [`ps2.md`](../../ps2/docs/ps2.md) | §3.1 the `/IRQ` decision this card follows; §5.3 the FIFO fallback; §14 item 3 the shared measurement; **§7.1 the `/IRQ`-masked transmit window that defeats §5.1's flow control**; §8.1 the side-effect-free status read that lets PS/2 sit ahead of this card in the chain |
| [`docs/design-review.md`](../../../docs/design-review.md) | §6, 2026-09-04. IO-S1 (§3.4), IO-S2 (§5.1), IO-S3 (§5), IO-S4 (§8), IO-S5 (§8, §10.2), IO-S6 (§13 item 2), IO-S7 (§12 step 1) |
| [`audio.md`](../../../audio/docs/audio.md) | §8.1 why `/FIRQ` outranks `/IRQ`, which is what kills §4.4 |
| [`graphics.md`](../../../video/docs/graphics.md) | §16.1 the bus exerciser; §17 the backplane and the widen-the-window warning |
| **CoCopedia, *Deluxe RS-232 Program Pak*; Tandy *Deluxe RS-232 Operation Manual*** | §3.2's precedent — a 6551 on a 6809 bus, shipped |
| Wikipedia, *MOS Technology 6551* and *WDC 65C51*; Jeff Tranter, *The 6551 ACIA*; 6502.org forum | §3.1 and §3.3 |
| `~/code/colormin/docs/backplane.md` §5 | the discrete alternative §4.1 rejects |
| **Minimal 64x4 Rev 1.4 Redux, sheet 2/9 "UART"** | Carsten Herting (slu4), CC BY-NC-SA 4.0. The fixed-rate design §4.2 rejects |
