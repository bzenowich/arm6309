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
| `boot.bin` | the 8 KB image — what goes in the first page of the `SST39SF040`. ⭐ **Tracked** |
| `boot.hex` | the same bytes as `$readmemh` records, loaded by `mainboard.v` |
| `boot.lst` | A09's listing, and the only place the encodings are visible |

⭐ **`boot.bin` is committed, and the other two are not.** The image is what the machine
executes, so it is a design output in the sense `CLAUDE.md` means: the fitted `.jed`
files are tracked for the same reason. It also makes the assembler a visible dependency.
`fetch-a09.sh` builds A09 from `master`, so a change in A09's output shows up as a diff
in `boot.bin` the next time `npm run rom` runs. `boot.hex` and `boot.lst` are derived
from the same assembly and are rebuilt with it.

`npm run rom` checks the image, not just that it assembled: 8,192 bytes, 8,192 `$readmemh`
records, and all seven vectors. For each one, the two bytes in the image, the value in
A09's listing and the address of the label its `FDB` names must agree, and RESET must
be `$E000`.

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

## Cell mode — 2,000 cells out of 256 bytes

The last scene puts a tilemap in VRAM with the span writer, points `TILEBASE` (`+$17`)
and the map base (`+$19`) at it, sets `CTRL` b5, and lets the card paint.

⭐ **The tile set is the bytes 0..255 in order, and that is not laziness.** §6.4.1's
tile address is a *concatenation* — `TILEBASE | code<<6 | row<<3 | col` — so tile *n*'s
pixel (*r*, *c*) sits at `n*64 + r*8 + c`, which for four tiles is the offset itself.
Writing `i` at offset `i` makes every pixel's index equal to `(n<<6)|(r<<3)|c`, and §9's
palette is the identity map, so **every pixel that reaches the connector names the three
fields that addressed it**. `machine_tb` states the whole expression independently and
checks all 256,000 of them.

The map is `code = (cellRow + cellCol) & 3`, so the tile changes across *and* down and a
row/column swap in the concatenation cannot look right. ⚠ **VMODE 00, because the cell
row is five bits** — §6.4.1: cell mode addresses 32 rows, which covers 640×200's 25 and
640×240's 30 and does not reach 640×400's 50 or 640×480's 60.

⛔ **And it is what found `graphics.md` §19 item 43.** `runlist` must wait for the
engine to stop before anything else loads `WPTR` — §10.3.1's own rule — and the bit
that says so, `LRUN`, had **no path to the data bus**: `+$0F` `BSTAT` is a register-file
address and `LRUN` is a live macrocell, so a read returned a zero that meant nothing.
The tilemap went into a pointer the engine was still walking. `LRUN` is `VSTAT` b4 now.

## Sizing memory, and the descriptor it leaves

§1a is `hardware/ram.md` §6.4.1's walk. It runs after `RUN` and before `LDS`, so it is
stackless: its state is `B` (the socket under test) and `U` (the bitmap). For each socket,
block 0 is pointed at its base, then:

1. `$A5` and `$5A` are each stored and read back, with a ROM read in between. `D0`–`D7`
   has no pull-ups, so without that read an empty socket returns the stored byte.
2. `$11` is stored at `+$0000` and `$22` at `+$0400`, and `+$0000` must still read `$11`.
   A 1M × 8 module ignores physical `A10` and fails this.

The ten SIMM map entries (blocks 0, 3, 4, 5 and 6 of both tasks) then point at the
**lowest socket that passed**, and the stack and variables go there. No socket is
mandatory. If none passes, the ROM reports `$E1` and halts.

**The memory descriptor**, at the base of that socket (logical `$0000`):

| offset | contents |
|---|---|
| `+0` | bitmap of the sockets that passed, b0 = socket 0 |
| `+1`–`+2` | total memory in 8 KB blocks, big-endian — 512 per 4 MB socket |

§2b then proves `TASK` selects half the map. The two tasks' block 5 entries name
different SIMM pages, so `$A000` is two physical bytes. The ROM stores `$C3` under
TASK 0 and `$3C` under TASK 1, reads both back, and reports `$07`, or `$E3` on a mismatch.

## Every wait in this ROM is unbounded, deliberately

The ROM polls `VSTAT` in twelve loops and none of them has a timeout, so **a video card
that never clears `SPANBUSY`, or never enters vertical blank, hangs the machine.** That
is the design for a boot ROM with no output device:

- **A timeout would have nowhere to report.** The progress port at `$FF2F` decodes
  nowhere on real hardware, so a bounded loop that fails lands in `halt`. On the bench,
  halting and hanging look the same.
- **A bound is a timing claim about the card**, and `graphics.md` §7.4's spans take up
  to 40.7 µs of `/WAIT` legitimately. Bounding twelve loops means choosing and
  maintaining twelve numbers that buy no diagnosis.

⚠ **The simulation cannot show this failure mode.** `machine_tb` bounds every stage in E
cycles and has a global backstop, so a stuck card fails the bench in seconds, while real
hardware would sit there indefinitely. **Revisit this when the ROM has a console:** then
a timeout can say which wait expired, and it should.

## What `machine_tb` checks without asking the ROM

⛔ **A stage that passes because its own `cmpa` passed is self-verified.** Stage 2 and
section 10 were, and a store that lands at the wrong cell, read back from the same wrong
cell, passes that compare. So `machine_tb` also checks these stages from outside:

| stage | read independently |
|---|---|
| 1a | the walk's four `$FF90` writes in order; the descriptor; all sixteen map entries |
| 2 | each store to `$C000` is in the chosen socket's cell one E cycle later, and each load is a byte the board *drove*, not the bus holding its last value |
| 2b | `$C3` in SIMM page 5 and `$3C` in page 7 of that socket |
| 2a | the 96 stores at `STORET`: 32 × `$50`, then 64 × `$51` |
| 10 | all 1,250 bytes the CPU loads from VRAM, window and `VDATA`, against the read sequence restated in the testbench. VRAM itself is peeked at both span starts and at the end |

**And the error paths run.** `npm run check:machine` is four runs of the bench
(`+scenario=`), and in three of them the right answer is a failure:

| scenario | population or fault | asserted |
|---|---|---|
| `main` | four sockets | the whole ROM |
| `e1` | no SIMM in any socket | the walk visits all four, reports `$E1`, and nothing runs after it |
| `s1`, `s2`, `s3` | one, two, three sockets | the descriptor's bitmap and size, all sixteen map entries, stage 2 and the two tasks, in socket 0 |
| `alias` | four sockets, a 1M × 8 in socket 0 (`ram.md` §11 item 7) | the walk rejects socket 0: bitmap `$0E`, 1,536 blocks, and everything lands in socket 1 |
| `e2` | tile byte 17 corrupted after it is written | section 10 reports `$E2` with `vidx` = 17, after exactly 18 loads |

## What it does not do yet

- **No interrupt vector is ever taken.** NMI is not wired, FIRQ and IRQ are masked from
  reset and nothing unmasks them, and the image contains no `SWI`, so the vector table is
  checked only as two bytes of ROM. All six vectors point at `halt`.

- **No console, no monitor, no DriveWire loader.** `machine.md` §7.2 says what page 0
  is eventually for. `software/6809/README.md` has what retargeting ASSIST09 costs.
