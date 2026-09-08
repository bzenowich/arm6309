# `io/` — keyboard, mouse and serial

**Not started.** This directory exists so that the next two cards land somewhere
deliberate instead of at the root.

| | | |
|---|---|---|
| [`ps2/`](ps2/) | PS/2 keyboard and mouse | **specified** — [`ps2/docs/ps2.md`](ps2/docs/ps2.md), 11 ICs |
| [`serial/`](serial/) | RS-232 serial | **specified** — [`serial/docs/serial.md`](serial/docs/serial.md), 3 ICs |

> ⚠ **One card since 2026-09-08.** The two documents stay separate — they specify
> different problems and neither shrank — but the *boards* merged into
> `hardware/cards/io.circuit.tsx`, **14 ICs on a 12 cm card**.
>
> **What merges them is this directory's own subject: the `$FF` map.** PS/2 holds
> `$FF50`–`$FF53` and serial `$FF54`–`$FF57`, and they are contiguous, so one card
> decodes eight bytes where two decoded four each. The machine gets a slot back — six
> cards became five against six slots.
>
> **14 is 11 + 3 with nothing shared**, which is the honest count and not the cheapest.
> The obvious saving is the second `GAL22V10`, and it is not free: `ps2.md` §9 already
> calls its GAL the fitting risk at roughly ten macrocells of ten, and the pressure is
> the `DR` latches and the `/PL` terms rather than the decode. One `ATF1508AS` would
> absorb both GALs, the `'273` and the `'244` and take the card to 11, which the retired
> house rule no longer forbids. **Neither is specified.**
>
> ⚠ **The merge does not merge the interrupt handlers.** `docs/machine.md` §4.1 still
> polls video, net, PS/2, then **serial last**, because reading the 6551's `STATUS`
> clears the interrupt and returns the error bits in the same read. One card, two
> sources, unchanged order.

**The two cards answer the "discrete or a chip?" question differently, and both are
right.** PS/2 is eleven packages of 74-series logic because no period chip decodes PS/2 —
`ps2.md` §4.5 evaluates the closest thing, a 6522 per port, and rejects it on I/O space.
Serial is three packages because the 6551 (1977) does the whole job in one, costs four
addresses, and shipped inside a CoCo. **The rule that used to bar CPLDs was retired on
2026-09-08** (root `README.md`); what decides each case is whether a period part exists,
whether it can still be bought, and whether it fits the I/O budget — in that order.

## Read this before specifying another one

[`../docs/machine.md`](../docs/machine.md) §5 open items 1 and 2 are, specifically, the
two things an I/O card runs into first. **[`ps2/docs/ps2.md`](ps2/docs/ps2.md) §3 answers
both** — take `/IRQ` as a third source, and take `$FF50`–`$FF53` — and a serial card should
either adopt those answers or argue with them, not rediscover the problem:

- ~~**There is no free `$FF` window.**~~ **There are 64 free bytes at `$FF00`–`$FF3F`**,
  and they are the whole of the 2026-09-08 widening. The geographic decode spans
  `$FF00`–`$FF7F`; video has `$FF60`–`$FF7F`, audio proposes `$FF40`–`$FF4F`, and
  `$FF50`–`$FF5F` went to PS/2, serial, storage and the net card, four bytes each.
- **Both maskable interrupt lines are claimed.** `/IRQ` is video's VBL — which is also
  NitrOS-9's system tick — and `audio.md` §8.1 takes `/FIRQ` as the *sole* source on
  purpose. Polling a keyboard from the VBL tick is a genuine option at 50–70 Hz, but it
  should be chosen rather than defaulted into.

**~~And the `$FF` map has four bytes left.~~ ~~And the `$FF` map is full.~~ And the `$FF`
map is `$FF00`–`$FF7F`, with 64 bytes free.** Audio 16, PS/2 4, serial 4, storage 4,
**net 4**, video 32 — of **128**, since `docs/machine.md` §5 item 1 closed on 2026-09-08.
[`../storage/`](../storage/) returned half the old disk-controller reservation;
[`../net/`](../net/) spent it and filled the window, and widening below `$FF40` is the
answer that took. ⚠ **A card now decodes `A0`–`A6`** — `A6` left the strobe with the
widening, and six bits answer twice. `serial/docs/serial.md` §7.1
escalates `graphics.md` §17's "widen the window now" from advice to a blocker, and
`sdcard.md` §11.1 shows it now costs throughput as well as expandability.

`ps2/docs/ps2.md` §3.1 takes **`/IRQ` as a third source** — it is open-drain, already
carries VBL and raster compare, and only `/FIRQ` is exclusive — and §3.2 takes
`$FF50`–`$FF53`. Both are still **proposals** until `docs/machine.md` records them as
taken. [`../net/`](../net/) has since joined `/IRQ` as a **fifth** source, and it is the
first one that can out-rate video's VBL (`net/docs/net.md` §3.4).

**A shared line has an order, and it is not free to choose.** `docs/machine.md` §4 records
it: **video `VSTAT`, then net `NRXST`, then PS/2 `IOSTAT`, then serial `STATUS` last.** The reason belongs to
the serial card — reading the 6551's `STATUS` *clears* the interrupt and returns the error
bits in the same read (`serial/docs/serial.md` §7.3), so its handler cannot probe cheaply
and defer; it must consume what it finds. PS/2's `IOSTAT` read has no side effects at all
(`ps2/docs/ps2.md` §8.1), which is what lets it sit in the middle. Any third I/O card
joining `/IRQ` inherits this constraint.

> ⚠ **The PS/2 card was 9 ICs until the 2026-09-04 design review.** Its central claim —
> that the `74HC595`'s storage register gives a byte of buffering for free — was false:
> `RCLK` is the bit counter's `Q0`, which fires on every edge of every frame, so the next
> frame's **start bit** overwrites the byte. A `74HC574` per port, clocked at end-of-frame,
> is what makes the buffer real. **9 → 11.** `ps2/docs/ps2.md` §5.

## The prior art is worth reading before you design anything here

Slu4's **Minimal 64x4** (local copy in `~/code/colormin/minimal/`) does PS/2 receive in
**three ICs** and full-duplex serial in **five**. `ps2/docs/ps2.md` §4.1 dissects the PS/2
circuit and adopts four of its ideas outright; [`serial/README.md`](serial/README.md) has
the UART equivalent. The general lesson both halves teach:

> **Most of what a "proper" controller contains is optional at these speeds.** A PS/2 bit
> is 60–100 µs. Anything that happens rarely — transmit, initialisation, error recovery,
> inter-line pacing — belongs in software, and anything that happens per-bit needs
> exactly one shift register and one counter.

## House rules, same as the other cards

Period-appropriate silicon (GALs yes, CPLDs and FPGAs no), a documented register map
before a board, an honest IC count, and one document per card.
