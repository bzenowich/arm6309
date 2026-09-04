# `io/serial/` — serial

**Not started.** Placeholder — but two things are already known, and both come from the
same place [`../ps2/docs/ps2.md`](../ps2/docs/ps2.md) §4.1 got its design.

## What the Minimal 64x4 shows

Slu4's machine does **full-duplex serial in five packages**: a `74HC165` transmit
shifter, a `74HC595` receive shift-and-store, a `74HC161` and a `74HC193` for bit timing,
and one `74HC00` of glue. Same shape as the PS/2 receiver, same `'595` storage-register
trick, and `UART_RTS` for flow control.

**It is five packages because the rate is fixed.** The sheet says so plainly: *"UART
bitrate 500 kbps, 1 start bit, 7 data bits, 2 stop bits, new line LF, transmit line delay
~10 ms."* One rate, seven data bits, no divisor register, and the inter-line delay in
software. It is a fast link to a host PC for loading programs — not an RS-232 port.

**A programmable-baud card costs roughly three times that.** colormin's
`~/code/colormin/docs/backplane.md` §5 prices the same circuit plus a proper baud
generator — a 1.8432 MHz oscillator, a `'393`/`'161` divider tree, a `'151` selecting the
bit clock from a `RATE[2:0]` field, and a `'74` resynchroniser because the oscillator is
asynchronous to the bus — at **~14 ICs**, plus level shifting.

So the first design decision for this card is not a circuit, it is a question: **is this a
period RS-232 port, or a fast link to a modern host?** They are 14 ICs and 5 ICs and they
are not the same card.

## Read before specifying it

[`../../docs/machine.md`](../../docs/machine.md) §5 items 1 and 2. `../ps2/docs/ps2.md`
§3 answers both — `/IRQ` as a shared source, and a small window carved from
`$FF50`–`$FF5F` — and a serial card should either adopt those answers or argue with them,
not rediscover the problem. Note that PS/2 took `$FF50`–`$FF53` and the disk controller
still has a claim on the rest.

Note also that the CPU module already has a debug UART on `USART3` (`PC10`/`PC11`) — see
[`../../cpu/README.md`](../../cpu/README.md). That is a bring-up console for the emulator,
not the machine's serial port, and the two should not be confused.
