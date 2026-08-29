# `io/ps2/` — PS/2 keyboard and mouse

**Not started.** Placeholder.

Open before anything else: the I/O window and the interrupt line — see
[`../README.md`](../README.md) and [`../../docs/machine.md`](../../docs/machine.md) §5.

Worth noting from the existing specs: PS/2 (1987) is comfortably inside this machine's
1989–90 period window, and the protocol is slow enough — ~10–16 kHz clock, host-clocked
by the device — that it is a shift register and a state machine, not a bandwidth problem.
