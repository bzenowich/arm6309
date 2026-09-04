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

## The two things worth knowing

**⚠ Not the `W65C51N`.** The one still in production has two documented defects — `TDRE`
never reads empty, and accessing the chip mid-transmission stops the transmission — which
between them remove every way of knowing when to send the next byte. Specify an `R6551A`
or a CMOS `G65SC51`. §3.3.

**The FIFO is what's missing, not the baud rate.** The 6551 buffers one byte each way, so
every received byte costs an interrupt. At 19,200 baud that is 1,920/s — 9 % of the CPU
optimistically, 37 % pessimistically. The practical ceiling is **4800–19,200 baud**, and
which end depends on the same unmeasured NitrOS-9 dispatch cost that decides whether the
PS/2 card's FIFO comes back. One measurement settles both. §5.

That is also why a non-standard 2× crystal is a trap: 38,400 baud at 73 % of the CPU. The
baud generator was never the limit.

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
datasheet — §7.2's register layouts are recalled, and there is no 6551 datasheet in
`reference/`. Step 2 is the shared interrupt-cost measurement.

Note that the CPU module already has a debug UART on `USART3` (`PC10`/`PC11`) — see
[`../../cpu/README.md`](../../cpu/README.md). That is a bring-up console for the emulator,
not the machine's serial port, and the two should not be confused.
