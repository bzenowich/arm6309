# `io/` — keyboard, mouse and serial

**Not started.** This directory exists so that the next two cards land somewhere
deliberate instead of at the root.

| | | |
|---|---|---|
| [`ps2/`](ps2/) | PS/2 keyboard and mouse | **specified** — [`ps2/docs/ps2.md`](ps2/docs/ps2.md), 9 ICs |
| [`serial/`](serial/) | serial | not started — [`serial/README.md`](serial/README.md) has the prior art |

## Read this before specifying another one

[`../docs/machine.md`](../docs/machine.md) §5 open items 1 and 2 are, specifically, the
two things an I/O card runs into first. **[`ps2/docs/ps2.md`](ps2/docs/ps2.md) §3 answers
both** — take `/IRQ` as a third source, and take `$FF50`–`$FF53` — and a serial card should
either adopt those answers or argue with them, not rediscover the problem:

- **There is no free `$FF` window.** The geographic decode spans `$FF40`–`$FF7F`; video
  has `$FF60`–`$FF7F`, audio proposes `$FF40`–`$FF4F`, and `$FF50`–`$FF5F` is pencilled
  in for a disk controller.
- **Both maskable interrupt lines are claimed.** `/IRQ` is video's VBL — which is also
  NitrOS-9's system tick — and `audio.md` §8.1 takes `/FIRQ` as the *sole* source on
  purpose. Polling a keyboard from the VBL tick is a genuine option at 50–70 Hz, but it
  should be chosen rather than defaulted into.

`ps2/docs/ps2.md` §3.1 takes **`/IRQ` as a third source** — it is open-drain, already
carries VBL and raster compare, and only `/FIRQ` is exclusive — and §3.2 takes
`$FF50`–`$FF53`. Both are still **proposals** until `docs/machine.md` records them as
taken.

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
