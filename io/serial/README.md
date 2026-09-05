# `io/serial/` — RS-232 serial

One port, **3 ICs**: a 6551 ACIA, a `MAX232`, and a decode GAL.

Paths below are relative to this directory.

| | |
|---|---|
| [`docs/serial.md`](docs/serial.md) | the card — part choice, the alternatives, the throughput ceiling, register map |

## Don't build this one out of logic

Every other card in this machine is discrete because no period chip does what it needs.
Serial is the exception: the **6551 ACIA (1977)** has four registers, an on-chip
programmable baud generator that needs nothing but a 1.8432 MHz crystal, full modem
control and an interrupt output. It is *older* than most of the 74HC parts around it, and
the period rules bar CPLDs and FPGAs, not LSI.

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

> ⚠ **`/RTS` does not rescue this, and an earlier revision of `docs/serial.md` §5 said it
> did** — "an overrun becomes throttling rather than lost data". That describes a 16550.
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

## This card closed the `$FF` map

`$FF54`–`$FF57`, four bytes — and with them the `$FF40`–`$FF7F` geographic decode was
**exactly full**. [`../../storage/`](../../storage/) has since returned four, needing only
half the disk-controller reservation, so the machine's entire I/O margin is now
`$FF5C`–`$FF5F`.

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

**Buy a null-modem cable.** `docs/serial.md` §8 used to say a straight-through cable to a
modern USB-serial adapter was what the DE-9 expected; a USB-serial adapter is **also a
DTE**, so the first cable anyone plugs in has to be a crossover. The straight-through one
is for the modem.

**The NitrOS-9 driver probably exists.** The CoCo 3 tree ships an `sc6551` SCF driver for
the Deluxe RS-232 Pak — the same part on the same bus — so §3.2's "base-address change and
nothing else" posture is likely real. What still needs the ten-minute check is whether
§7.2's *recalled* register layout is the one that driver talks to.

Note that the CPU module already has a debug UART on `USART3` (`PC10`/`PC11`) — see
[`../../cpu/README.md`](../../cpu/README.md). That is a bring-up console for the emulator,
not the machine's serial port, and the two should not be confused.
