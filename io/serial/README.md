# `io/serial/` — RS-232 serial

One port, **3 ICs**: a **`TL16C550C`**, a `MAX232`, and a decode GAL shared with the
PS/2 half. **115,200 baud, 16-byte FIFOs each way** — `docs/serial.md` §4.5, taken
2026-09-09.

Paths below are relative to this directory.

| | |
|---|---|
| [`docs/serial.md`](docs/serial.md) | the card — part choice, the alternatives, the throughput ceiling, register map. **§4.5 and §5.4 are the revisit that changed the part; §9.1 and §9.2 are what it cost and what it deleted** |

## ⭐ The revisit, 2026-09-08 — and the part change, 2026-09-09

**The card is bound by one interrupt per byte, not by the baud rate**, and §5 has always
said so: 19,200 full duplex is 3,840 interrupts/s and **73 % of a 2.098 MHz CPU** at the
pessimistic dispatch figure. The part also caps at 19,200.

**§4 never asked whether a better UART exists.** It asks *"6551, or build one out of
logic?"*, rejects the logic options on package count, and stops. The reason is buried in
its own wording: *"a 6551 costs **four addresses**"* — and until 2026-09-08 the `$FF` map
had four bytes left in it. **A `16C550` costs eight, and eight did not exist.**

`machine.md` §5 item 1 closed on 2026-09-08. The window is `$FF00`–`$FF7F` with 64 bytes
free, and the machine has a megabyte of physical space for card buffers. So:

| | ICs | 19,200 fd | 38,400 fd | 115,200 fd | 460,800 fd |
|---|---|---|---|---|---|
| 6551 — what the card was | 3 | **75 %** | impossible | *part caps at 19,200* | — |
| ⭐ **Tier 1 — `16C550`, TAKEN** | **3** | 7 % | **13 %** | **40 %** | — |
| Tier 2 — + a ring in `A20 = 1` | ~8 | 1 % | 2 % | **5 %** | **20 %** |

**Tier 1 was taken on 2026-09-09, and it cost no packages at all.** Both this table and
`docs/serial.md` §9.1 priced it at "+1 IC"; ⚠ **that was a counting error** — the tier row
counted the baud crystal where the base total did not. Two DIPs and a GAL before, two DIPs
and a GAL after, for 6× the baud rate and **38,400 costing less CPU than 19,200 did.**

**What it closed is worth more than the throughput.** The `W65C51N` sourcing trap and the
fast-E speed grade both stop existing, because a `16C550` is current-production and is
clocked by its own crystal rather than by backplane `E` — `net.md` §13.6's lesson applied:
availability is the first question about a part, the I/O budget the second.

⭐ **And one thing nobody had costed: `machine.md` §4.1's polling order.** This card was
pinned to the end of the shared-`/IRQ` chain because reading a 6551's `STATUS` clears the
interrupt and consumes the error bits in the same read, so it could not be probed
speculatively. **A `16C550`'s `IIR` can be** — `docs/serial.md` §7.3. The machine's
polling order is a preference now rather than a rule.

⚠ **What it spent: eight bytes of the `$FF` map**, and the card's window moved to
`$FF30`–`$FF3F` — below.

⚠ **The real ceiling is not the wire.** At 115,200 you receive 5.8 screens of text a
second, and ANSI rendering on a 2 MHz 6309 is an estimated 22 % of the CPU at that rate.
**~115,200 for a console; 460,800–921,600 for file transfer**, where nothing renders.
§5.6.

**Tier 1 is the card. Tier 2 is not built** — §13 item 7, and `docs/drivewire.md` §3 is
explicit that DriveWire does not need it. ⚠ **Neither of the card's two GALs is fitted**,
and the serial one grew with the part: Intel-style strobes, an active-high `MR`, and an
open-drain inversion of `INTR`, which is totem-pole and cannot wire-OR the way the 6551's
`/IRQ` could.

## Don't build this one out of logic

Every other card in this machine is discrete because no period chip does what it needs.
Serial is the exception: the **6551 ACIA (1977)** has four registers, an on-chip
programmable baud generator that needs nothing but a 1.8432 MHz crystal, full modem
control and an interrupt output. It is *older* than most of the 74HC parts around it, and
the period rules have never barred LSI — and since 2026-09-08 they do not bar
programmable logic either (root `README.md`).

**And it shipped on this bus.** The Tandy Deluxe RS-232 Program Pak (26-2226, 1983) is a
6551 with a 1.8432 MHz crystal decoding four ports on a CoCo — a 6809 machine, where `E`
*is* `φ2`. This is the only card in the project with a commercial precedent.

> **An earlier version of this README framed the first decision as "a period RS-232 port
> (~14 ICs) or a fast host link (~5)".** That was a false choice, reached by looking only
> at the Minimal 64x4 and colormin's `backplane.md` §5 — both of which build UARTs out of
> logic because their machines reach serial through microcode strobes and so have no I/O
> window to spend. This machine has 64 bytes of window and no shortage of board area.
> `docs/serial.md` §4 rejects both, and the discrete alternative loses on package count
> anyway: 14 and 5 against 3.

## The three things worth knowing

**⚠ Not the `W65C51N`.** The one still in production has two documented defects — `TDRE`
never reads empty, and accessing the chip mid-transmission stops the transmission — which
between them remove every way of knowing when to send the next byte. Specify an `R6551A`
or a CMOS `G65SC51`. §3.3.

**⚠ And the speed grade is part of the specification.** The 6551 sits directly on `E` as
its `φ2`, so it is the one part in the machine whose rating is indexed to the CPU clock.
**This card is specified at ÷12 only** — `E` = 2.0979 MHz, where a 2 MHz part is 5 % over
and a CMOS part is comfortable. At the machine's software-selectable **fast-E rate (÷8,
3.1469 MHz) a 2 MHz part is 57 % over** and a 3 MHz part is over too; only a genuine 4 MHz
`G65SC51` covers it. Fast-E is experimental and not guaranteed machine-wide, and this card
is one of the three independent reasons why. §3.4.

**The FIFO is what's missing, not the baud rate.** The 6551 buffers one byte each way, so
every received byte costs an interrupt — **and every transmitted byte costs another**. At
19,200 baud that is 1,920/s receive-only, or **3,840/s full duplex**, which is a terminal
with echo or either direction of a file transfer: 18 % of the CPU optimistically, **73 %
pessimistically**. The practical ceiling is **4800–19,200 baud** and the honest answer sits
toward the low end; which end exactly depends on the same unmeasured NitrOS-9 dispatch cost
that decides whether the PS/2 card's FIFO comes back. One measurement settles both. §5.

That is also why a non-standard 2× crystal is a trap: 38,400 baud is 3,840 interrupts/s
receive-only and 7,680 full duplex — 37 % of the CPU on the optimistic dispatch figure and
arithmetically impossible on the pessimistic one. The baud generator was never the limit.

> ⚠ **`/RTS` does not rescue this.** "An overrun becomes throttling rather than lost
> data" describes a 16550.
> On a 6551, **`/RTS` is a bit in `COMMAND`**, not a receiver-driven output, so throttling
> is software flow control carried on a hardware wire, driven from the ISR at a
> ring-buffer high-water mark — and the only encoding that deasserts `/RTS` also **disables
> the transmit interrupt**. `/CTS` *is* automatic on the transmitter, so that direction is
> genuinely free. §5.1, and the 2026-09-04 design review (IO-S2).

**One interaction with the card next door, recorded in neither document until now:** the
PS/2 card's software transmit runs with `/IRQ` masked for 0.8–1.3 ms every time a caps-lock
LED is updated (`../ps2/docs/ps2.md` §7.1). One byte time at 19,200 baud is 521 µs, so that
window **guarantees an overrun** and no flow-control arrangement on this card can prevent
it — the ISR that would deassert `/RTS` is precisely what is not running. §5.1 point 4.

## This card closed the `$FF` map, and then spent eight bytes of it

Four bytes at the top of the original window — and with them the `$FF40`–`$FF7F`
geographic decode was **exactly full**. [`../../storage/`](../../storage/) then returned
four, needing only half the disk-controller reservation;
[`../../net/`](../../net/) spent those on 2026-09-07; and **that is what finally closed
`machine.md` §5 item 1 on 2026-09-08.** The window became `$FF00`–`$FF7F` — 128 bytes,
64 free — and `/IOSEL` got *cheaper* in the process.

⭐ **Then this card spent eight of them, on 2026-09-09, and got a six-times-faster port
for it.** `docs/serial.md` §4.5's `16C550` has **eight** registers where a 6551 has four,
which the widened map made affordable and the original 64-byte one did not. The merged
I/O card moved to a sixteen-byte window at **`$FF30`–`$FF3F`** rather than displacing
storage and net, and handed `$FF50`–`$FF57` back: **56 bytes free, not 64.** That is the
margin doing exactly what §5 item 1 widened it to do.

⚠ **This card's decode is `A0`–`A6`, not `A0`–`A5`** — `A6` left the strobe with the
widening, so a six-bit match answers at the base **and 64 bytes below it**. It was
missing from `hardware/cards/io.circuit.tsx` entirely until the same pass, and it is on
the serial GAL now, compared once for the whole card.

`graphics.md` §17's "widen the window now" has stopped being prudent advice and become
blocking; see [`../../docs/machine.md`](../../docs/machine.md) §5 item 1, which now also
records that the squeeze costs *throughput* — `sdcard.md` §11.1's 512-byte block buffer
would delete a hazard and buy 27 % more transfer rate, and is rejected only for want of
address space.

## Status

**Specified, nothing built.** The deliverable is the document.

`docs/serial.md` §12 gives the build order. Step 0 is the `$FF` map. Step 1 is getting a
datasheet — §7.2's register layouts are recalled, there is no 6551 datasheet in
`reference/`, and four things have to be looked up rather than assumed: the `IRQB` output
structure (**open drain**, which the wire-OR onto the shared `/IRQ` depends on), the
`COMMAND` register's 2-bit `/RTS`/transmit-interrupt field, the unmaskable `/DSR`/`/DCD`
transition interrupt, and the maximum `φ2` for the grade in hand. Step 2 is the shared
interrupt-cost measurement.

**Buy a null-modem cable.** A USB-serial adapter is **also a DTE**, so the first
cable anyone plugs in has to be a crossover (`docs/serial.md` §8). The
straight-through one is for the modem.

**The NitrOS-9 driver probably exists.** The CoCo 3 tree ships an `sc6551` SCF driver for
the Deluxe RS-232 Pak — the same part on the same bus — so §3.2's "base-address change and
nothing else" posture is likely real. What still needs the ten-minute check is whether
§7.2's *recalled* register layout is the one that driver talks to.

Note that the CPU module already has a debug UART on `USART3` (`PC10`/`PC11`) — see
[`../../cpu/README.md`](../../cpu/README.md). That is a bring-up console for the emulator,
not the machine's serial port, and the two should not be confused.
