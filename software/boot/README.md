# `software/boot/` — the machine's own first instructions

`boot.asm` is the ROM page 0 of [`docs/machine.md`](../../docs/machine.md) §7.2: the
sequence that leaves boot mode, and a video bring-up that puts a picture on the
connector. It is the first code this project has ever executed.

⭐ **The video half drives [`video3`](../../video3/docs/plan.md) since 2026-09-20.** It
drove [`archive/video/`](../../archive/video/docs/graphics.md) until that day, and the
two cards' register maps differ in almost every offset (`plan.md` §10). The motherboard
half — §1, §1a, §2, §2a, §2b and §11 — did not change, and neither did any of
`machine_tb`'s claims about it. [`../v3boot/v3boot.asm`](../v3boot/v3boot.asm) is the
smaller fixture the video half was ported from and is still the thing to read first.

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

⛔ **The palette writes the index for EVERY entry**, which is two register writes an
entry more than the auto-increment needs, and the reason is a live defect
(`video3/docs/history.md`, 2026-09-19): **outside `VBLANK` the posted commit fires on
every dot of `HLOAD`**, so `PIDX` steps twice and a 256-entry load that leans on the
auto-increment writes 479 entries at every other address and then wraps over the ones it
got right. `v3boot.asm` §2a asks that question on purpose and in one place; this ROM
does not depend on the answer.

Every 8-row by 128-pixel cell has a colour that **identifies where it is**, and the
palette is the identity map, so `machine_tb` can recover the framebuffer index from the
connector and compare it against the same expression stated independently. A stride
error moves a boundary, an interleave error scrambles a cell, a geometry error changes
how many fit, and a scan-address error moves the stripe.

⚠ **The program polls `VSTAT` b7 between spans** — `plan.md` §5's own rule — rather
than relying on `/WAIT`. Both work; `machine_tb` is what found out, on the card before
this one.

## §2c — is there a `video3` card at all?

⛔ **This is the one part of the retarget that is not optional.** `boot.bin` is page 0
of **every** build of this machine, including builds whose NitrOS-9 drives the archived
card, and [`software/demo/emu/machine.c`](../demo/emu/machine.c) models both (`m->v3`,
selected by `VIDEO3=1`). Sections 3–10 poll `VSTAT` at `$FF6D`; on the other card that
offset is not `VSTAT` at all but a plain register-file byte, so a poll of it reads back
whatever was written there and **can spin for ever**. `CLAUDE.md`: a hang is worse than
a failure.

So the card is identified before the video POST runs, and the whole of it is skipped
with progress `$06` if the answer is no. **The probe is `+$13`, and it cannot answer
wrong in either direction:**

| | `+$13` is | a write of `$A5`, then `$5A`, reads back as |
|---|---|---|
| **`video3`** | `CPTR1`, the copy source's middle byte — an ordinary register-file location (`v3host`'s `RDBKOE` covers it, `A4` set) | the byte that was written. **Probe passes** |
| **`archive/video`** | `VSTAT`, read "through the `'244` of §12.1, **not** the register file" (`graphics.md` §13) | `SPANBUSY`, `VBLANK`, `HBLANK`, `LRUN`, `PBUSY`, `IRQ` — and **b2 and b3 are hardwired zero**. `$A5` has b2 set and `$5A` has b3 set, so neither pattern can come back in any state of the card at any point in the frame. **Probe fails** |
| **an empty slot** | nothing | whatever the bus last carried — and a known ROM byte is read between the store and the load, `ram.md` §6.4.1's rule, so that is `$C3`. **Probe fails** |

Two patterns rather than one, so a bus stuck at either level fails one of them. The
write costs nothing on either card: `CPTR1` is reloaded before every copy, and `VSTAT`'s
write side clears an interrupt flag that cannot be pending because nothing is enabled
yet.

## §7 — the copy engine and the sprite, which replaced the display list

⛔ **`video3` has no display-list engine** (`plan.md` §0 and §1): no `BCTRL`, no `BSTAT`,
no `LRUN`, no descriptor decode, no per-scanline palette and no per-scanline scroll. The
two scenes that ran one — `P_LSTA` and `P_LSTB` — are retired, and `$20` and `$21` now
carry the two capabilities this card has that the other did not and that nothing else in
this ROM reaches.

| code | what it reports |
|---|---|
| `$20` | **the copy engine** (`plan.md` §6). Eight rows of sixteen bytes built with the span writer at VRAM row 404, copied to row 420 with `CPTR`/`WPTR`/`CWIDTH`/`CHEIGHT`/`CCTRL`, and read back through `VDATA`. `$E4` if a byte disagrees |
| `$21` | **the 16×16 sprite** (`plan.md` §7), composed at scan time over the pattern — so what comes out of the connector is the claim, exactly as the raster bar's was |

⚠ **Sixteen rows apart, not eight.** `plan.md` §6.2: the engine counts **up only**, so a
destination that overlaps the source ahead of the read reads back its own output. Both
rectangles are off-screen, which is also why the copy cannot disturb §8's frame.

⚠ **The sprite's colours are four LUT entries, not 512.** `plan.md` §7 loads all 256
entries of sub-palettes 1 and 2 because a general cursor sits over a general picture.
This one sits at x 32–47 of picture rows 48–63, and `index(x, y)` is constant across each
8-row by 128-pixel cell, so the sprite covers exactly indexes `$30` and `$38`. The shape
is `code(r, c) = (r + c) mod 3` — `machine_tb` states that rule and the ROM states the
64 bytes, which is what makes the table a claim and not a copy.

## Tile mode — 2,000 cells out of 256 bytes

The last scene puts a tilemap in VRAM with the span writer, points `TBASE` (`+$18`) and
`MAPBASE` (`+$19`) at it, sets `CTRL` `MODE = 10`, and lets the card paint.

⭐ **The tile set is the bytes 0..255 in order, and that is not laziness.** The tile
address is a *concatenation* — `TILEBASE | code<<6 | row<<3 | col` — so tile *n*'s
pixel (*r*, *c*) sits at `n*64 + r*8 + c`, which for four tiles is the offset itself.
Writing `i` at offset `i` makes every pixel's index equal to `(n<<6)|(r<<3)|c`; tile mode
drives the LUT's high half with **zero** (`plan.md` §2.4) so the lookup is sub-palette 0,
which §3 made the identity map — and **every pixel that reaches the connector names the
three fields that addressed it**. `machine_tb` states the whole expression independently
and checks all 256,000 of them.

The map is `code = (cellRow + cellCol) & 3`, so the tile changes across *and* down and a
row/column swap in the concatenation cannot look right.

⭐ **And the map is where this card differs most.** `plan.md` §2.5 makes a cell **four
bytes on a 1024-byte stride** — code in lane 0, attribute in lane 2, the two the fetcher
reads — where the other card had one byte on a 128-byte stride. `WADV` b2 steps `WPTR` by
**two**, so a cell is two stores rather than four, and `machine_tb` reads the map back
out of VRAM to prove the second cell's code landed at `+4` and not at `+2`. ⚠ With b2 set
`X` and `WPTR` no longer move together in `putb`, which is deliberate and said there.

⚠ The cell row is **six** bits on this card, so `plan.md` §2.5's 64 rows cover every
`VMODE` and `graphics.md` §6.4.1's "cell mode does not reach 640×400" is not inherited.
The scene is `VMODE 00` anyway, so that the frame is the same 640×200 as §4's.

## §10a — the boot dialog, and how it calls a toolbox that is not there yet

⭐ **New 2026-09-20.** [`docs/boot-and-desktop.md`](../../docs/boot-and-desktop.md) §1
is the design and says the most of it; this is what the ROM does.

A Macintosh 128K finds its video hardware, clears the screen and puts up a dialog with
an icon that says it is looking for a disk. §10a is that, drawn with the **ROM toolbox**
— `tbox.asm` on ROM page 64, the same code CoArm calls to draw Haiku windows — and it
needed **nothing added to the toolbox**: `CoG` is `$6000`, `Co.WinA` is `$A000` and
`Co.WinB` is `$C000`, all three logical addresses in CoArm's map, and the POST owns the
whole map, so it reproduces that layout and calls in exactly as `ca_tbox.asm` does.

| code | state |
|---|---|
| `$60` | *looking for a disk* — the Haiku window, the toolbox's own `disk` icon, and the line |
| `$64` | ⭐ §10b's verdict: the card came up, `CMD58` said `CCS`, and block 0 carries the boot signature |
| `$65` | ⭐ ...or it did not, and there **is** a card in the socket |
| `$61` | *found* — drawn after `$64` |
| `$62` | *no disk* — the Macintosh's blinking question mark, on the icon. Reached after `$65` (a card that is not bootable) or straight from the card-detect test (an empty socket) |
| `$63` | ⚠ **no toolbox**: ROM page 64 did not answer `"TB"`, and the dialog was skipped |
| `$E6` | the toolbox returned an error; the map and the stack are put back first |

⛔ **`$63` is the usual answer, and that is not a defect.** `boot.bin` is page 0 of every
build, and page 64 only exists in a NitrOS-9 ROM built with `-DV3=1`
(`recipes/arm6309/arm6309.mak`: `TBOX = tbox` is inside that `ifneq`). A bare
`npm run rom` produces 8 KB and no more, and six of `check:machine`'s seven default
scenarios load exactly that. The signature test is `ca_tbox.asm`'s own — the two bytes
`"TB"` at `Co.WinA` — and it costs one map write and a compare.

⛔ **THE STACK MOVES, and this is the part to know before editing.** `Co.WinB` is
`$C000`, which is where `lds #STACK` was descending from `$E000`; for the length of the
dialog block 6 is a **ROM page**. So §10a's stack is `DSTK` in block 0 and its variables
are at `$0010`–`$004B`, also block 0. ⚠ **It therefore cannot call `settle`**: `settle`
counts its frames in `nfrm` at `RAMWIN+$16`, which is block 6 — the store would go to a
ROM page, the `dec` would read back a byte of a font, and the loop would end when that
byte happened to be 1. `dlgwait` is the same wait with its counter in block 0, and it
takes the number of blanks in `A`.

⚠ **And the SIMM's map high byte is read before the toolbox runs, not after.** §11
recovers it with `lda MAPHI+6`; the toolbox's own `MapB` writes `MAPHI+6` on its first
call, so by the end of the dialog that byte is the ROM's. `simmhi` holds it.

⚠ **`boot.asm` carries a second copy of `defs/armvid.d`'s offsets**, because A09 cannot
include lwasm source. [`checkcg.py`](../nitros9/tools/checkcg.py) re-derives all 22 with
lwasm and `software/nitros9/mkrom.sh` refuses a ROM whose two halves disagree.

### ⛔ A09 has no comment delimiter, and a comma in a comment is a register

The trap that cost this section a day, written down because it will be paid
again otherwise. A09 takes everything after the operand as a comment — except
that it keeps parsing a **register list** across the whitespace, so

```
        pshs    d               ,s = pixels left; 3,s = the colour
```

assembled as `PSHS A,B,U` (postbyte `$46`): **four bytes where two were meant.**
Every stack offset in the routine was then off by two, the row layer took the
toolbox's transparent-key byte for its colour, and the `puls` at the end
returned into VRAM. ⚠ In isolation `pshs d` assembles correctly, which is why a
one-line test of it proves nothing; it is the comment that does it.

Two rules follow, and §10a keeps both: **a `pshs`/`puls` comment never starts
with a comma**, and every register list is written out in full — `pshs
cc,a,b,x,u`, never `cc,d,x,u`. The encodings are in `boot.lst` and are worth a
look after any edit to them: `$06` is `A,B` and `$46` is `A,B,U`.

## §10b — the SD reader, and what *found* now means

⭐ **New 2026-09-21.** [`storage/docs/sdcard.md`](../../storage/docs/sdcard.md) §9.0,
§9.1 and §9.5 are the design. §10b is ~640 bytes: the card's initialisation and one
`CMD17` read of block 0, and **nothing else** — no filesystem, no directory walk, no
write path, and **no block buffer at all**. Its whole output is which of §10a's three
pictures is true; `boot_sd.asm` in the NitrOS-9 tree is what actually loads `OS9Boot`,
and it runs the same test again from scratch rather than being told the answer.

*Found* was `SDSTAT` b1 — a mechanical switch closed by a lump of plastic. It is now a
card that answered `CMD58` with `CCS` and whose block 0 carries `"6309"` and a version
byte at LSN 0 `+$F0`, over a non-zero `DD.BT`. ⭐ **That gives the question mark its
real Macintosh meaning**: there is a disk in the drive and it is not a system disk.

| | |
|---|---|
| ⛔ **§9.0 step 1 comes before the 74 clocks** | `SDMOSI <- $FF` with no burst, *then* ten `SDDATA` reads. The `'574` that holds MOSI has no clear input (§6.4), so at power-up it holds garbage, and a card clocked with `DI` low through its power-up sequence may never enter SPI mode. One instruction. `sd_model.v` and the host emulator both **refuse** a `CMD0` that arrives without it, so the hazard is tested rather than described |
| ⛔ **Nothing touches `SDDATA` between the `$FE` token and the first data byte** | the read that *returns* `$FE` has already started the burst that fetches data byte 0 (§6.2's one-byte pipeline). Anything inserted there destroys byte 0 and shifts the whole block by one, silently, from beginning to end |
| **There is nowhere to put 512 bytes** | §10a runs with block 6 pointed at a ROM page, so `$C000`'s variables and the `$E000` stack do not exist while this runs. The eight bytes the verdict needs — `DD.BT` at `+$15` and the signature at `+$F0` — are picked out of the stream by three skip loops and two take loops, and the other 504 are read and dropped |
| **The card is left safe either way** | `SDCTRL <- $00`: `/CS` high, the init clock, no burst in flight. `rbsd`'s own `Init` then starts from where §9.0 expects to |
| **Every poll is bounded** | `sdwait` counts 4,096, the R1 poll 16, the token poll 10,000, `CMD0` retries ten times and `ACMD41` 2,000. A card that never answers is a picture, not a hang |

⛔ **Two things that made it silently wrong on the way, both worth knowing.** A comment
that begins with `+` is parsed as part of the operand by A09 — `ldx #21   +$00..+$14`
assembles as `LDX #21+$00..`, which is the same trap as the comma below wearing a plus
sign. And in `boot_sd.asm`, the deblocking routine takes "keep this half" in `B` and the
even case called it with `B = 0`, so the half the caller asked for was the half that was
dropped: `DD.BT` read as zero, the card read as unblessed, and the machine booted from
the ROM disk and said nothing. **The bench's `s`/`r` character is what found it.**

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

## Every wait in this ROM is BOUNDED, since 2026-09-20

⛔ **This reverses what this section used to say.** Until the retarget the ROM polled
`VSTAT` in twelve loops with no timeout, on the argument that a bound is a timing claim
about the card and that a failed bound has nowhere to report. Two things changed:

- **§2c gave it somewhere to go.** A ROM that already has an error path and a progress
  code for "no card" has one for "the card stopped answering": `$E5`.
- **The reason a bound was expensive was twelve numbers; there is one.** Every poll goes
  through `vwait0`/`vwait1`, which count **65,536 reads** — about 0.3 s at this machine's
  E rate, longer than any span (a 256-byte span-solid is ~1,000 dots), any copy and any
  frame (359,200 dots), and short enough that a dead card reports rather than hangs.

⚠ [`../v3boot/v3boot.asm`](../v3boot/v3boot.asm) still leaves its polls unbounded and
says so: it is a **fixture**, and `v3machine_tb` bounds every stage of it. A boot ROM on
real hardware has no bench underneath it, which is the whole difference.

## ⛔ Only one check in this repository executes this ROM from reset

`npm run check:machine` is it — and since 2026-09-20 two of its runs are asked for by
name, `SCENARIOS="disk nodisk"`, which are the only things anywhere that execute §10a:
they load a **`V3=1`** 1 MB ROM (the one with a toolbox on page 64) and read the dialog
off `RGB` at the connector, pixel by pixel, with `machine3.v`'s `sd_cd` as the only
difference between them. The host emulator
([`software/demo/emu/machine.c`](../demo/emu/machine.c)) **starts the CPU at `$8004`**
with the map, the stack and the SIMM descriptor pre-set the way §1–§1a would have left
them — `m->cpu.pc = 0x8004` — so `software/nitros9/run-emu.sh`, `run-sd.sh` and
`video3/bench/run-v3sd.sh` boot NitrOS-9 **without running a single instruction of this
file**. The one path that does run it there is `reboot`: `F$Debug` re-enters the reset
vector with the map live, and `run-emu.sh`'s two reboot claims are the only emulator
claims this ROM can fail.

⚠ **So a change here is verified by `check:machine` or it is not verified.** That is
also why §2c matters more than it looks: the emulator will happily boot NitrOS-9 against
either card whatever page 0 says, and the day a real machine has the other card in the
slot, the probe is the only thing standing between the POST and a spin.

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
| 7a | both rectangles in VRAM, and that `CWIDTH`/`CHEIGHT` stopped the engine at their edges |
| 7b | every pixel of the sprite frame, and the 64 shape bytes against the rule rather than the table |
| 8 | the map in VRAM: `code` at `MAPBASE`·64K + row·1024 + col·4, which is the four-byte cell `WADV` b2 writes two stores at a time |
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

⚠ **And there is an eighth answer this ROM can give that no scenario asserts yet**: `$06`,
§2c's "no `video3` card". It is what the host emulator prints with `VIDEO3` unset, which
is how `software/nitros9/run-emu.sh` and `run-sd.sh` boot today.

## The RAM vectors, and a program in ROM

`machine.md` §7.2 puts the vectors in ROM, pointing "at a fixed RAM jump table", and says
the boot monitor has to publish that convention. This is it.

**The six interrupt vectors point at `$FEEE`–`$FEFD`, the CoCo 3's addresses.** That is
logical block 7, not the fixed `$FFC0`–`$FFFF` window, so what runs there depends on what
block 7 holds:

| Block 7 holds | `$FEEE`–`$FEFD` is |
|---|---|
| **this ROM page**: boot mode, and any program handed page 1 (`software/demo/`) | page 0's own jumps. IRQ goes through the word at **`$C004`**, FIRQ through **`$C006`**, and SWI, SWI2, SWI3 and NMI go to `halt` |
| **NitrOS-9's kernel block** (`software/nitros9/`) | `krn`'s BRA stubs. The kernel ends at `$FF00` so they land exactly here |

`$C004` and `$C006` are in block 6, the SIMM. Boot sets both to `halt` as soon as the
stack is up. `mkrom.sh` checks each vector against its label, so the table and the jumps
are one claim.

**Section 11** hands over to a program in ROM. After the VRAM read-back, boot maps ROM
pages 1 and 2 at `$8000` and `$A000`. If `$8000` holds `"6309"`, it jumps to `$8004`, with
the stack, the map and the RAM vectors set up. Otherwise it points the two blocks back at
the SIMM and halts as before. `machine_tb` loads page 0 only, so it takes the second path.
`software/demo/` and `software/nitros9/` take the first.

## What it does not do yet

- **Boot itself takes no interrupt.** FIRQ and IRQ stay masked through every test here,
  and the image contains no `SWI`. `software/demo/` is what takes both: the video card's
  VBL `/IRQ` and the audio card's `/FIRQ`, through the RAM vectors above. ⚠ So the
  VBL interrupt `plan.md` §9 makes NitrOS-9's system tick is **not** in this POST;
  `v3boot.asm` §8 and `v3machine_tb` are where it is exercised.

- **Character mode is not in the POST.** §8 runs `MODE = 10`, tile mode, because its
  picture is an arithmetic function of the byte the CPU wrote. Character mode
  (`plan.md` §2.2) puts an **attribute** on the LUT's high half and needs 512 palette
  entries and a glyph bank to say anything; `v3card_tb`'s char group is where it is
  checked. An open item, not a deliberate omission.

- **No console, no monitor, no DriveWire loader.** `machine.md` §7.2 says what page 0
  is eventually for. `software/6809/README.md` has what retargeting ASSIST09 costs.

- ⚠ **§10b reads block 0 and never reads block 1.** It is a *probe*, not a loader: the
  ROM does not load `OS9Boot` itself and has no reason to — the handoff at §11 is to
  ROM page 1, and it is the NitrOS-9 loader there, and `boot_sd` after it, that read the
  card for real. A ROM that could load a program off a card would be a different
  machine's ROM, and `sdcard.md` §13 item 14 is where that trade is recorded.
