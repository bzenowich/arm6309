# `software/pcs/reference/pcs-source/` — Pinball Construction Set, Atari 800, 1983

Bill Budge's *Pinball Construction Set* for the Atari 800, as released by the author at
[github.com/billbudge/PCS_Atari800](https://github.com/billbudge/PCS_Atari800).

⭐ **This is a build input, not reading.** `software/pcs/bench/mkpcs.py` parses these files to
generate the art bank, the palette, the part templates and the physics tables for
`pcs` — the port in `../../../nitros9/level2/arm6309/cmds/pcs.asm`. The port's whole
claim to be *the original* rests on lifting the data from here rather than redrawing or
re-deriving it, so these files are cited by line number throughout
[`../../video3/docs/pcs.md`](../../docs/pcs.md).

## ⚠ Why this one IS tracked when `../68k/`'s are not

[`../68k/README.md`](../../../../reference/68k/README.md) records what this project learned on 2026-09-04,
and states the rule it learned: **the right to redistribute is the criterion, and size
never was.** Apple's ROM carries no redistribution grant, and the Computer History
Museum's QuickDraw and MacPaint archives are licensed for non-commercial use
*distributed via CHM*, which grants nothing about onward redistribution. All three were
purged from this repository's history.

**This material is different, and only for that reason.** `LICENSE` is the **MIT
licence**, copyright © 1982 Bill Budge, which grants in as many words the right to
"use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies", on the
single condition that the notice travels with it. It does, in this directory, and the
generator reproduces the attribution in every file it writes.

⚠ **If that ever stops being true — if the upstream licence changes, or a future import
here carries no grant — this directory goes the way `../68k/` went.** The test is the
licence file, every time, and it is not satisfied by the material being small,
historical, or freely downloadable.

## What is here

| | |
|---|---|
| `LICENSE`, `README` | upstream, verbatim. ⛔ Do not edit either |
| `*.s` | the sixteen 6502 sources, with CRLF normalised to LF and the `.S` extension lowercased — **the only changes made**. Upstream names them `Disk1/EDIT.S` and so on; the two disks are flattened here because no filename collides |
| `BITMAPS.OBJ` | the 1,792-byte part-art blob, cut into shapes by the offset table at `RUN.s:100-118` |

⛔ **Not copied**: `pcs-source1.dsk` / `pcs-source2.dsk` (Atari disk images of the same
sources), the `.O` assembler output, `GPAK.OBJ` (precomputed x÷8, x mod 8 and
scanline-address tables that this machine has no use for — §4 of the port's spec says
why), the two `.PIC` title screens, and the Applesoft `MAKE*` scripts. All are either
derived, or dead on a machine with no bit-shifting to do.

## What reads what

| file | what `mkpcs.py` takes from it |
|---|---|
| `RUN.s` | the seven 64-entry cosine tables (`C05625`…`C84375`), `GRAVTBL`/`TIMETBL`/`KICKTBL`/`ELASTLO`/`ELASTHI`, `SCORETBL`, `FTTA`, `FLPVCTR`, the flipper silhouettes, and the 43 part templates |
| `EDIT.s` | the tool icons, `OBJLEN`, the template and parts-bin tables, and the screen rect records |
| `CDRAW.s` | the 36-glyph proportional mini-font and `CWIDTH` |
| `WIRE.s` | `EFFECTS`, `NOTES` and `SOUNDCODE` — the seven sound effects |
| `PPAK.s` | `DXCODESA`/`DXCODESB`, the slope quantiser that is also the surface-normal table |
| `BITMAPS.OBJ` | every part's artwork |

⚠ **`DISK.s`, `SWAP.s`, `DLIST.s`, `GOATARI.s`, `BOOT*.s`, `ZAP*.s` and `DOWNLOAD.s` are
here for provenance and are read by nothing.** They are the Atari's display list, its
DOS sector I/O, its overlay loader and the Apple II download link — the parts of the
program that are about the *machine* rather than about pinball, and the parts the port
replaces outright.
