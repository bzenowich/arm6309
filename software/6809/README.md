# `software/6809/` — imported 6809 code

Third-party, unmodified, kept for bring-up. Neither is written by this project and
neither has been assembled or run against `arm6309` yet.

| File | What | Provenance |
|---|---|---|
| `assist09.asm` | **ASSIST09** — Motorola's 6809 monitor ROM, 2 KB at `$F800` | © Motorola Inc. 1979. This copy is A. van der Horst's 2004 revision for HCC FIG Holland, retargeted at a 6522/ACIA at `$BE00` (`$Id: assist09.asm,v 1.5 2004/01/14$`). |
| `forth9.asm` | **FORTH for the 6809** — direct-threaded, FIG model, ROM-able | Mike Pashea, Southern Illinois University, July 1990. Primitives after Thomas Newman's 8086/88 FIG implementation. |

## Why they are here

A monitor is what you want on a bus the first time a synthesised CPU drives it: small,
self-contained, and it exercises the interesting paths — interrupts, the stack, and
character I/O — without needing a disk. `video/docs/graphics.md` §18 step 6's exit
criterion is literally "a monitor ROM prints to the 80×25 screen".

## What retargeting actually costs

Both target hardware this machine does not have. The previous revision of this file said
so and left it there; that understated it, and
[`../../docs/design-review.md`](../../docs/design-review.md) §Sys-m7 is the correction.
There are three separate problems, and only one of them is a base address.

**1. There is somewhere to put them now, and there was not before.**
[`../../docs/machine.md`](../../docs/machine.md) §7.2 has the CPU module serve logical
`$E000`–`$FFFF` from its own flash at reset. ASSIST09's 2 KB at `$F800` and the FORTH's
`$E000`-and-up ROM image both land inside that window, and the vector page comes with it.
Before that decision the machine had no ROM, no vector decode, and nowhere in the 1 MB
physical map to carve one — "ROM-able" described a property the machine could not accept.

**2. The console layer is a rewrite, not a rebase.** Both programs drive a **6850** ACIA
(the FORTH at `$9800`/`$9801`; ASSIST09 at `$BE00`), and this machine's serial card is a
**6551** ([`../../io/serial/docs/serial.md`](../../io/serial/docs/serial.md)). The two
parts are not register-compatible in any useful sense:

| | 6850 | 6551 |
|---|---|---|
| Registers | 2 — status/control, data | 4 — data, status, command, control |
| Baud rate | divide-select bits in the control register; an external clock sets the rate | on-chip generator, 15 rates from a 1.8432 MHz crystal, selected in the control register |
| Reset | master-reset bit pattern written to the control register | programmed reset by *writing* to the status address |
| Status | one register, read-only | one register, and **reading it clears the interrupt and returns the error bits in the same read** — see `machine.md` §4.1 |

So `PKEY1`/`PEMIT1` in the FORTH and ASSIST09's character I/O both need new bodies, not
new equates. That is small work — a dozen instructions each — but it is not the
find-and-replace the earlier text implied.

**3. ASSIST09's timer has no equivalent at all.** It expects a **6840 PTM** at `$E000`.
This machine has no PTM. The audio card's general-purpose timer (`audio.md` §8.2) is the
only programmable timer in the machine, it interrupts on `/FIRQ`, and it is not readable
as a 6840. ASSIST09's timer-dependent commands need either stubbing out or rewriting
against that timer — and note `$E000` is inside the shadow-ROM window, so the equate
collides with the code itself.

**Also worth knowing before bring-up:** `machine.md` §7.2's shadow ROM is served by the
CPU module, so a monitor image lives in STM32 flash rather than on an EPROM. That makes
iterating on it a firmware reflash, which is faster than a programmer — and it means the
monitor is only available on *this* machine, not on the CoCo 3 drop-in, where the
mechanism is off.

## Licensing

**Not reviewed, and at least one file needs it.** ASSIST09 carries a 1979 Motorola
copyright notice with no redistribution grant, which puts it in the same class as the
material removed from `reference/68k/` on 2026-09-04 (`design-review.md` §Sys-M6). The
FIG-model FORTH is more likely to be freely redistributable — the Forth Interest Group
published its models into the public domain — but Pashea's primitives carry no explicit
notice either way. **Check both before redistributing this repository**, and note the
project itself still has no licence of its own.
