# `software/boot/` — the machine's own first instructions

`boot.asm` is the ROM page 0 of [`docs/machine.md`](../../docs/machine.md) §7.2: the
sequence that leaves boot mode, and a video bring-up that puts a picture on the
connector. It is the first code this project has ever executed.

```sh
npm run rom            # from hardware/ -- assemble, and write boot.hex
npm run check:machine  # ... and run it on the real design
```

| | |
|---|---|
| `boot.asm` | the source |
| `boot.bin` | the 8 KB image — what goes in the first page of the `SST39SF040` |
| `boot.hex` | the same bytes as `$readmemh` records, loaded by `mainboard.v` |
| `boot.lst` | A09's listing, and the only place the encodings are visible |

## The assembler is not ours

**A09**, Hermann Seib's 6809/6309 assembler, fetched and built on demand by
[`../tools/fetch-a09.sh`](../tools/fetch-a09.sh). It is GPL v2 and it is **not
vendored** — the same rule `hardware/gal/verilog/oracle/fetch-paula.sh` states for
`Paula.v`, applied to a build tool. It assembles the HD6309 instruction set as well as
the 6809's, which is the CPU `cpu/README.md` says goes in the socket.

## The address mapping, which is the part that surprises

`machine.md` §7.2: in **boot mode** and in the **vector page** the `'244` drives
physical `A20`–`A13` to zero, so the ROM byte a logical address reaches is
`LA & $1FFF`. After `RUN` the block-7 map entry points back at the same physical page,
so it is the same byte. **Logical `$E000` is ROM `$0000` in both modes**, which is why
the source `ORG`s at `$E000` and the image is offset 0, and why `$FFFE` — the reset
vector — is ROM `$1FFE`.

⚠ **One entry must point at the page the code is running from**, or setting `RUN`
moves the instruction stream out from under the CPU. `hardware/ram.md` §6.4 states it
as a rule about the ROM's source; this is that source.

## What the video half draws, and why that shape

```
   index(x, y) = (y & $F8) | (x / 128)        five spans of 128 per row
   plus an 8-pixel vertical stripe at x = 256, drawn by WADV chaining
   palette entry i = $i i                      so the index is readable off RGB
```

Every 8-row by 128-pixel cell has a colour that **identifies where it is**, and the
palette is the identity map, so `machine_tb` can recover the framebuffer index from the
connector and compare it against the same expression stated independently. A stride
error moves a boundary, an interleave error scrambles a cell, a geometry error changes
how many fit, and a scan-address error moves the stripe.

⚠ **The program polls `VSTAT` b7 between spans** — `graphics.md` §7.4's own rule —
rather than relying on `/WAIT`. Both work since 2026-09-10; before that day neither
did, and `machine_tb` is what found out.

## The display list, and the two things it taught

`boot.asm` builds two lists **through the span writer** — byte by byte at `WPTR`, the
way a driver would — and starts each one out of a `VSTAT` poll, eight frames running:

| list A | 90 `WAIT`s, `MOVE PIDX/PDATL/PDATH` to make entry `$FF` magenta, 90 more, back to white | a **raster bar**: the stripe at x=256 is index `$FF`, so repainting that one entry part way down the frame is a bar with exactly two edges |
| list B | `MOVE HSCROLL,(n&63)*4` and two `WAIT`s, 200 times | **per-scanline scroll**: `machine_tb` counts the stripe standing in 64 distinct columns in ONE frame |

⛔ **A span-written byte stream cannot leave its 1024-byte row.** `WPTR` is not one
counter: `WA9`–`WA0` is a column that **wraps** at 1024 and `WA18`–`WA10` is a row that
only `WROWADV` clocks, so with `WADV = 00` the 1025th byte lands back on the first. The
first version of this code put the two lists 256 bytes apart and made list B 1261 bytes
long; it wrapped at byte 1024 and **rewrote itself over list A**, and what the engine
then walked was picture data executed as descriptors. Hence one row per list, and the
lists live at VRAM 409,600 and 410,624 — ring rows 400 and 401, past the image.

⚠ **`WAIT` counts scanlines, blanked ones included** (`graphics.md` §10.3.2). `runlist`
loads `WPTR` at vertical blank's *start* — the tear-free instant — and issues `GO` at
its *end*, so `WAIT` number *n* means line *n*. Starting at blank's start instead spends
the first ~49 `WAIT`s in the blanking. ⛔ And until 2026-09-10 it was worse than that:
`WAIT` cleared on a **level**, so a run of them collapsed to one per fetch slot and this
program's raster bar finished inside three lines of blanking — `graphics.md` §19 item 42.

## What it does not do yet

- **No `ram.md` §6.4.1 sizing walk.** It proves the first SIMM answers with a
  two-pattern read-back through a driven bus, which is that section's *method* on one
  socket; the four-socket walk that discovers how much memory the machine has is still
  to write.
- **No cell mode.** §6.4's `TILEBASE`/map base at `+$17`/`+$19` and `CHAR` have never
  been written by software; the tile fetch is exercised only by `vtile_tb`.
- **No console, no monitor, no DriveWire loader.** `machine.md` §7.2 says what page 0
  is eventually for. `software/6809/README.md` has what retargeting ASSIST09 costs.
