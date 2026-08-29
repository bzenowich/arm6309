# `io/` — keyboard, mouse and serial

**Not started.** This directory exists so that the next two cards land somewhere
deliberate instead of at the root.

| | |
|---|---|
| [`ps2/`](ps2/) | PS/2 keyboard and mouse |
| [`serial/`](serial/) | serial |

## Read this before specifying either one

[`../docs/machine.md`](../docs/machine.md) §5 open items 1 and 2 are, specifically, the
two things an I/O card runs into first, and neither has an answer yet:

- **There is no free `$FF` window.** The geographic decode spans `$FF40`–`$FF7F`; video
  has `$FF60`–`$FF7F`, audio proposes `$FF40`–`$FF4F`, and `$FF50`–`$FF5F` is pencilled
  in for a disk controller.
- **Both maskable interrupt lines are claimed.** `/IRQ` is video's VBL — which is also
  NitrOS-9's system tick — and `audio.md` §8.1 takes `/FIRQ` as the *sole* source on
  purpose. Polling a keyboard from the VBL tick is a genuine option at 50–70 Hz, but it
  should be chosen rather than defaulted into.

Settle both in `docs/machine.md` before writing a card spec against them.

## House rules, same as the other cards

Period-appropriate silicon (GALs yes, CPLDs and FPGAs no), a documented register map
before a board, an honest IC count, and one document per card.
