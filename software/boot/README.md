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

`npm run check:machine` is it. The host emulator
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
