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

Both target hardware this machine does not have: ASSIST09 wants an ACIA at `$BE00`, and
the FORTH assumes its own I/O. Retargeting them at
[`../../docs/machine.md`](../../docs/machine.md)'s `$FF` map is work that has not been
done.

**Licensing has not been reviewed.** ASSIST09 carries a 1979 Motorola copyright notice.
Check before redistributing either file as part of anything.
