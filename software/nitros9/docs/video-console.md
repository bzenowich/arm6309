# The NitrOS-9 video console

The window devices `/W1`… are NitrOS-9 Level 2 text and graphics windows on the video card
(`video/docs/graphics.md`), typed at on the PS/2 keyboard (`io/ps2/docs/ps2.md`). Programs
speak CoCo 3 CoWin's byte protocol to them. `docs/nitros9-av-plan.md` is the plan this
came from; this document is what is built.

```sh
sh software/nitros9/run-vid.sh        # build the ROM, run the scripted clients, judge the frames: 54 claims, ~4 min
```

**Its exit code is the answer.** It runs eight emulator sessions and
`tools/checkvid.py` makes the claims:

| Run | What is typed | What is claimed |
|---|---|---|
| `select` | `iniz w1`, `copy /dd/sys/vtp1 /w1`, `iniz w2`, `copy /dd/sys/vtw2 /w2`, Select `/W2`, Select `/W1` | every frame that shows a screen is **pixel-exact** against `tools/vtmodel.py`: `/W1` before `/W2` was made, `/W2` after its Select (640 × 480, `VMODE` 01), and `/W1` again at the end; no register write under a span or a list; the IRQ-masked times below |
| `kbd` | `iniz w1`, `shell i=/w1&`, then `echx⌫o KBD-OK >/term` on the PS/2 keyboard | the shell on `/W1` ran it (`KBD-OK` reaches `/Term`), and `/W1` shows the line as SCF edited it |
| `p2` | `iniz w3`, `copy /dd/sys/vgp2a /w3`, `iniz w4`, `copy /dd/sys/vgp2b /w4`, Select `/W4`, Select `/W3` | **pixel-exact** against `tools/vgmodel.py`: `/W3` (640 × 200) with the pointer before `/W4` was made, `/W4` (640 × 240, `VMODE` 01) after its Select, `/W3` from its store at the end; CoArm's masked time |
| `mouse` | `vgp2a` on `/W3`, then five PS/2 mouse packets | every pointer position's screen is pixel-exact and in order, the last clamped at the right edge and the bottom row; a pointer move's cost; every IRQ after boot under 1.4 ms |
| `p3` | `copy /dd/sys/vgp3 /w3` | the extension escapes and an ANSI terminal in a scrolling overlay, **pixel-exact** against `vgmodel.py` |
| `rast` | `rastbar >/w3`: raster bars, a palette list rewritten every frame by `SS.Raster` | **every frame a list ran** is the picture with `show.py`'s `raster_colours` at the phase the VBL service started (`VG.MkPh`); 90% of the phases reach the screen |
| `wave` | `wave >/w3`: an `HSCROLL` warp, the same way | the same, with `gui.asm`'s warp arithmetic |
| `game` | `overworld >/w3`: the demo's game on an exclusive tile screen | **every frame** is `mkgame.py`'s `render()` for the camera and hero records its `SS.Batch` committed (`VG.MkCam`, `VG.MkHero`); the camera steps one record a frame in 90% of pairs; the hero's flips finish in the blank (`checkdemo.py`'s rule) |

⭐ **`vtmodel.py` shares data with the 6809, not code.** It interprets the protocol itself
and renders the picture from the font (`coarmfont.asm`, read as data) and CoWin's
default colours. `vtp1` exercises every control code, reverse video, insert and delete
line, a scroll of 40 lines past the 32-row map ring, a palette change and a foreground
colour change, and escapes a text screen must swallow (GPLoad with 16 data bytes that
include `$1B`, GCSet).

`vgmodel.py` is the same for bitmap windows. Its shapes are `tools/vgshapes.py`'s
definitions, pixel for pixel: Bresenham lines, the midpoint ellipse's spans, arcs clipped by
a line, the flood fill. `vgp2a` exercises text with reverse, underline and bold, every
drawing escape, `LSet` XOR, a pattern, `GetBlk`/`PutBlk`, a GP-buffer font, transparent
text, a working area that scrolls, an overlay that is ended and one that is kept, `GCSet`
and `PutGC`.

## The modules

They are on the `arm6309` branch of `../nitros9` (`software/nitros9/README.md`).

| Module | Where it runs | What it is |
|---|---|---|
| `ArmIO` | system map, bootfile | the SCF driver: one statics per window, the keyboard buffer, `SS.Ready`/`SS.SSig`/`SS.Relea`, the VBL service (`vidsvc.asm`), and every other call carried into CoArm |
| `KbdArm` | system map, bootfile | the PS/2 keyboard and mouse: `ps2.md` §11.2's initialisation, one `F$IRQ` service on `IOSTAT` for both ports, set 2 to CoCo 3 key values, 3-byte packets to a clamped position. The plan's separate `MseArm` is this module's second port |
| `CoArm` | **software task 1**, loaded from `CMDS` | CoWin's protocol and the screens, drawing through VidCore (`vidcore.asm`) |
| `libvid` | loaded from `CMDS` by its user | a subroutine module for the exclusive owner: waits, puts, gets, fills, pokes, span-solid rectangles, with the card's rules built in |
| `rastbar`, `wave`, `overworld` | `CMDS` | the scripted clients of `SS.Raster`, and of `SS.Excl`, tile screens, `libvid` and `SS.Batch` |
| `W1`–`W4` | bootfile | descriptors (`armwin.asm`): `/W1` 80 × 25 text and `/W2` 80 × 30 text, each opening its window at Init; `/W3` and `/W4`, which a client opens with `DWSet` |

`defs/armvid.d` holds every layout: the card's registers, `VG`, the statics, CoArm's
globals, windows and screen records.

### ⭐ CoArm is not in the system map

The system map is 64 K: the kernel's block, block 0's globals, the bootfile's four blocks,
and what is left for descriptors and statics. With CoArm in the bootfile, 15 K was free after
boot and `load /dd/modules/firqtst` failed with `E$MFull`. CoArm is the module that grows.

⛔ **And the shell is out of the bootfile too.** P3's ArmIO took system memory three pages
into the fourth block below the kernel's, and `firqtst` failed again, with `E$NoRAM`: a
device attached after boot needs a whole unmapped slot for its module. `SysGo` forks the
shell from `/DD/CMDS` now, which gives back 7 K.

So CoArm runs where CoCo 3's GrfDrv runs, and the kernel already had the mechanism, 16-bit
blocks included:

1. The first window's Init finds CoArm with `F$NMLink`, or loads it with `F$NMLoad` (from
   the execution directory, then `/DD/CMDS`). Neither maps it into the system.
2. `F$FModul` gives its blocks. ArmIO builds software task 1's DAT image: block 0 at slot
   0, CoArm at slots 1–2 (`$2000`, 16 K; CoArm is 15,342 bytes, and the recipe fails a
   CoArm that outgrows them), two `F$AllRAM` blocks at
   slots 3–4 (`$6000`, its globals and records), and slot 7, which the kernel forces to its
   own block. Slots 5 and 6 are CoArm's windows onto the blocks it draws from and into (GP
   buffers, text shadows, overlay saves, screen stores): it writes the image and the DAT
   itself (`MapA`, `MapB`). `D.TskIPt`'s task 1 entry points at the image.
3. **A call** (`CoCall`) is CoWin's entry to GrfDrv. ArmIO saves the system stack in `VG`,
   pushes a full RTI frame for CoArm's entry under `D.CCStk`, and jumps through `D.Flip1`,
   which loads task 1 and RTIs. CoArm runs with `/IRQ` open: the kernel's IRQ path
   switches to the system map and back (`krn.asm` `S.SysIRQ`). It returns through
   `D.Flip0`.
4. **CoArm makes no system calls.** Where it must wait for the frame batch to reach the
   card or for a VBL, or needs blocks allocated or freed, it yields (`VG.CWait`: batch,
   frame, alloc, free). ArmIO sleeps or makes the call, then calls `CF.Resume`, and CoArm
   continues from the same stack. `VG.CBusy` keeps other windows' calls out meanwhile.
   ⛔ **CoArm's entry does not touch `S` until it knows the call.** A resumed call's stack is
   under `Co.Stack` and `/IRQ` is open, so an entry that loaded `Co.Stack` first let an IRQ
   stack over it, and `Resume` returned into the clock (`video/README.md`).

**What both maps see is block 0.** `VG`, the video globals, is at `$1100`, in the page a
CoCo 3 gives GrfDrv's globals. CoArm's stack is under `$1F00`, and the flip's frame is above
it. The I/O page is decoded ahead of the map, so the card is in every map.

⚠ **Two things this costs.** A window call pays a task switch each way
(`docs/nitros9-hardware-improvements.md` H13). And CoArm's own memory is two blocks: eight
screen records and 32 window records live there, and everything larger is in blocks it maps.

## VidCore: the card's rules

`vidcore.asm` (CoArm) and `vidsvc.asm` (ArmIO) are the only code that touches the video
card. The rules are plan §2.1's V1–V12:

| Rule | How it is kept |
|---|---|
| V1, V12: no register access but `VSTAT` under `SPANBUSY` | every register write follows `VcWait`, a bounded poll of b7 and b4 (16,384 polls, 39 ms: a card that holds either bit that long is reported, not waited on) |
| V2: nothing while `LRUN` | `VcWait` polls b4. A VDATA stream re-checks between chunks |
| V3: `WPTR` is the list's pointer | `VG.PtrGen` counts the service's uses of `WPTR`. A stream that sees it move waits the list out and reloads its own position (`VcRePtr`) |
| V4: shadow everything | `VG.Ctrl`, both scrolls, `WFG`, `WBG`, `WADV`, `SPANLEN`, both bases. `ArmIO` reads the register file into them once, at start |
| V5, V7: acknowledge, scrolls | only the VBL service writes `VSTAT` and the scroll pairs, from the frame batch |
| V6: a palette commit is posted, and `PBUSY` must be clear | `VcPal`, from CoArm's main line: an entry at a time behind a masked `VcWait`, then a poll of `VSTAT` b1 with `/IRQ` open (bounded like `VcWait`). The card holds the commit to the next line's blank, so the service does not carry palettes |
| V8: a family change | nothing: `CTRL` goes in the frame batch and the card takes the new family at the end of the frame (`graphics.md` §6.2) |
| V11: the tick follows `VMODE0` | the service returns `VMODE0` in carry, and the clock chooses the tick's length from it |

⛔ **The clock calls the service from `VBLTick`, on the system stack.** The first build called
it from `SvcIRQ`, which runs straight from the vector on the interrupted code's `S` in the
system map, before the kernel's `XIRQ` moves to the system stack. An interrupt taken in user
state pushed its return into whatever system memory sat at the user's stack address. `SvcIRQ`
now only recognises the VBL; the kernel calls `VBLTick` through `D.SvcIRQ`.

**The masking rule** (plan §3.4). A main-line sequence masks `/IRQ` from its first register
write to its trigger write. A VDATA stream is cut into chunks of 24 writes with `/IRQ` open
between them. **Measured** by the emulator's `MASKLOG`: CoArm's longest masked stretch is
**361 µs**, and ArmIO's, moving the pointer, **220 µs**. ⭐ **`VcWait` waits a running
display list out with `/IRQ` open**: a list runs most of a frame, and the first build polled it
masked for 7.4 ms.

**The VBL service** (`VcSvc`): the clock calls it on each VBL through `D.VBLSt`, once the
console is up. It waits out a span, counts a list still running (`VG.LRunV`), acknowledges,
then commits the batch: both scroll pairs, `TILEBASE`/`MAPBASE`, and `CTRL` with the main
line's `WMODE` kept. **Measured** by the emulator's `CALLTIME`: at most **183 µs**, mean
97 µs, against plan §3.4's 0.5 ms. It returns the `VMODE0` of `CTRL` as it found it
(`VG.TkFam`), since the frame that just ended was in that family whatever the batch wrote.

⛔ **The first measurement was 1.57 ms.** The service waited for VBLANK to fall on a
family change (1.2 ms after the IRQ) and committed 32 palette entries a blank; then 468 µs
with a main-line family wait and 16 entries. The card's frame-end family latch and posted
palette commit (`docs/nitros9-hardware-improvements.md`, "Taken") removed both.

## The fast-text screen (types `$18`, `$19`)

Cell mode (`graphics.md` §6.4.8): one map write per character. **The font is baked into
tile bank 1** in the screen's two colours. Codes `$00`–`$7F` are CoWin's standard 8 × 8
font (NitrOS-9's `stdfonts` set 1), and `$80`–`$FF` are the same glyphs inverted. The
bank is 2,048 span-mask writes, eight to a glyph with `WADV` 00. The map is at `MAPBASE`
0, in a ring of 32 cell rows.

- **A line feed at the bottom row is `VSCROLL` += 8** in the next blank, and one cleared
  row. `/W2`'s 30 rows leave two spare ring rows, so a screen can scroll more than two
  lines in a frame before the recycled rows show.
- **Reverse video and the cursor are the inverted half of the font.** The cursor is the
  code under it with bit 7 flipped. It is taken off before each change and put back after.
- **Every screen keeps a shadow of its codes**, by ring row. A screen that is not
  displayed is drawn in the shadow only. Select repaints the map from it.
- **Select** turns the display off in the next blank. It rebuilds the font bank if the
  colours differ, paints the map, and queues the palette, the bases and the scroll. Then
  it writes the palette (`VcPal`: a line an entry, at once in vertical blank) and turns the display on. Nothing half-drawn is seen.
- **`FColor` and `BColor` change the whole screen**, and rebuild the bank: 256 codes hold
  one colour pair (`graphics.md` §6.4.8).

### The protocol

| | |
|---|---|
| Control codes | `$01` home, `$02` X+32 Y+32, `$03` erase line, `$04` erase to end of line, `$05 $20`/`$21` cursor off/on, `$06` right, `$07` bell (nothing, until AudDrv), `$08` left (column 0 goes to the end of the line above), `$09` up, `$0A` down (scrolling at the bottom), `$0B` erase to end of screen, `$0C` clear, `$0D` return |
| `$1F` | `$20`/`$21` reverse on/off, `$30` insert line, `$31` delete line. `$22`–`$25` (underline, blink) are accepted and not drawn |
| `$1B` | **every escape CoWin defines consumes exactly its parameters** (CoWin's own counts), and GPLoad its data. On a fast-text screen: DWSet (types `$18`, `$19`), Select, DWEnd, DefColr, Palette (CoCo 3 six-bit colours), FColor, BColor; the drawing escapes answer `E$IWTyp` |

## Bitmap screens and windows (types `$10`–`$13`)

`DWSet` with a bitmap type makes a screen: 640 × 200 (`$10`, `$12`), 640 × 240 (`$11`,
`$13`), line-doubled in `VMODE` 00 or 01. The card has one picture's VRAM, so **a screen
that is not displayed lives in its store**, 640 × H bytes in DRAM blocks, and every
primitive draws into the card or the store through one row layer (`ca_row.asm`:
`RowFill`, `RowPut`, `RowGet`, `RowMask`, `Glyph`).

- **Text** is span-mask: a glyph is eight `WADV` 01 writes. Reverse swaps the colours,
  underline sets the glyph's last row, bold ORs it shifted, transparent text uses the
  mask's transparent colour. A GP buffer can be the font (`Font`).
- **The text cursor is an XOR of its 8 × 8 cell**, read back and written, only on the
  displayed window that has the keyboard. A character drawn over it clears it first.
- **A line feed at the bottom** is `VSCROLL` += 8 when the window is the whole screen and
  alone on it; otherwise rows are read back and written up (`BmScroll`).
- **Drawing** is `ca_draw.asm`: spans for everything, merged runs for lines and outlines,
  `LSet` AND/OR/XOR by reading the row back, patterns from a GP buffer, `FFill` by a
  scanline stack.
- **GP buffers** are blocks of their own (`ca_gpb.asm`), up to 48. `GetBlk` keeps the
  screen's pixels, `PutBlk` writes 8 bpp or 1 bpp (style 5) buffers clipped to the window.
- **Overlays** (`OWSet`) save what they cover into blocks when asked, and put it back at
  `OWEnd`.
- **Select** takes the pointer off and the display off in the next blank, copies the old
  screen's VRAM to its store, the new store to VRAM (or repaints a text screen), changes
  family if it must, commits the palette and the scrolls, and turns the display on.
  ⚠ 640 × 200 is 128 K each way at CPU speed (`docs/nitros9-hardware-improvements.md` H4).

## The pointer and the mouse

`KbdArm` takes the mouse's 3-byte packets on the second port, clamps the position to the
displayed screen and records it in `VG`. **The pointer is drawn into VRAM** (`vidptr.asm`):
only the pixels under the arrow's row runs are kept (`PtrRun`, 106 of the 16 × 16 box), read
back through `VDATA` a run at a time, and the arrow is composed into the same runs from
`PtrArt` (outline, fill, or keep). A row is one masked stretch: a fast `VSTAT` check, one
`WPTR` load (`PtrLoad`), and the run. CoArm takes it off wherever its drawing would cover it (`PtrGuard`) and puts
it back when the call ends. `GCSet` turns it on and off, `PutGC` places it, and `SS.Mouse`
returns CoWin's packet: buttons, the screen position, and the position in the working area.

⛔ **A move is 7.9 ms of VDATA traffic, 7.3 ms of it outside interrupts, measured, so it is
not done in the IRQ.** Saving the whole box took 15.6 ms. The first build moved it from
KbdArm's service: every packet masked `/IRQ` for 15 ms, and the
16C550's FIFO covers 1.4 ms at 115.2 kbaud. The service now only records the position.
**The kernel's idle loop moves it**: `fnproc.asm` calls `VG.Idle` (ArmIO's `PtrIdle`)
with `/IRQ` masked before it waits for an interrupt, and PtrIdle moves the pointer with
`/IRQ` open between the stream's chunks. A CoArm call's end moves it too. ⚠ **So a
process that computes without sleeping freezes the pointer** until it does.

⛔ **And the measurement found a clock bug that masked every device IRQ.** `clock.asm`'s
`DoPoll` ended with `TSTB`, which leaves carry alone, so it returned D.Poll's "no more
devices" carry even when a device had been serviced. The kernel took every non-tick IRQ
as unclaimed and returned to the interrupted code with `/IRQ` masked, until something
unmasked it: 3 ms under the shell, 6 ms inside the pointer's stream. `DoPoll` sets carry
explicitly now. After boot, the longest IRQ is **881 µs**.

## Display lists (`SS.Raster`)

`SS.Raster` gives the displayed bitmap screen a list, from a table (`armvid.d` `RT.*`): an
`HSCROLL` value or an RGB565 palette entry for each band of scanlines from a first scanline,
and a tag. CoArm composes the list (`ca_list.asm`): the first scanline's `WAIT`s, each
entry's `MOVE`s and `WAIT`s, the register put back as the screen has it, and `END`, at most a
ring row of 1,024 bytes. It writes it into the one of two ring rows below the screen that the
service is not starting, and points the service at it in one masked store, so no frame starts
a list half written.

**The VBL service arms it** (`vidsvc.asm` `VcGo`): it loads `WPTR` and writes `GO` while
`VBLANK` is high, and the card starts the walk as the blank ends (`graphics.md` §10.3.1's armed
`GO`), so `WAIT` *n* is line *n* with no poll. `VG.LArm` records that the list owns `WPTR`
before `LRUN` shows it, and `VcWait` waits the blank out while it is set. **The longest IRQ
with a list on is 722 µs, measured**; polling for the blank's end took 1.66 ms. A service
that finds the blank already over starts nothing that frame (`VG.LLate`). The tag + 1 of the
list started is `VG.MkPh`, which the emulator's `MARKS` records with each frame.

A bitmap screen's ring columns 640–1023 are colour 0 after Select, so an `HSCROLL` list shows
something defined past the screen's right edge. `SS.RastOff` stops the starts; the last list
ran to its end and put back what it moved.

## Tile screens, the exclusive screen, and `SS.Batch`

A **tile screen** (`DWSet` `$1C` 640 × 200, `$1D` 640 × 240) is cell mode with nothing of
CoArm's in it: displayed, `TILEBASE` is 30 and `MAPBASE` 124 (`armvid.d` `TL.*`). CoArm keeps
no copy, so it is for a program that owns the screen. Text and drawing on it do nothing;
Select, DWEnd and the palette escapes work.

**`SS.Excl`** claims the displayed screen for the calling process (plan §3.5). CoArm draws
nothing on it and takes the pointer off, no Select happens until it is given back, and it
returns the card's base. It is given back by `SS.Excl` with Y = 0, by the screen going, or when
ArmIO finds the owner gone (`XCheck`, before every call). ⚠ SCF never tells a window driver
that a path closed, so there is no release on close.

The owner has:

| | |
|---|---|
| `SS.TileLd` | 16,384 bytes of tiles into a bank, a ring row at a time; not the map's bank |
| `SS.MapWr` | a rectangle of map codes, `WPTR` reloaded where the ring's 128 columns wrap |
| `SS.TBank` | `TILEBASE` in the next blank |
| `SS.Batch` | records the next VBL commits, in order, first thing in the service: register writes (the scroll pairs, the bases), puts, pokes (a byte each at many addresses, one `WPTR2` load), and two tags for `VG.MkCam` and `VG.MkHero`. A batch waiting for its blank makes the next one wait (`VG.MkMiss` counts it) |
| `SS.FrmWait`, `SS.FrmSig` | sleep until a VBL is served (X := the count), or a signal every *n* frames. ⚠ `SS.FrmSig` is built and no run exercises it. ⭐ **On video3 the service also writes the count's low byte into the card's spare register** (`plan.md` §10's `+$1F`), so a process holding the screen reads a frame end instead of calling: the call costs ~1.4 ms, which is a tenth of a frame |

⭐ **SCF hands the driver a whole RUN of printable characters on video3**
(`video3/docs/demo-report.md` §11). Stock `scf.asm` already does this for a CoCo 3 — it
scans past the control characters and calls GrfDrv once — but the test is the driver's
name and `G.GrfEnt`, so this port failed it and paid the trip into the driver, a task
flip and CoArm's per-character setup for **every byte**: ~900 instructions a character,
and the 80 × 60 console listed at 9.7 lines a second. Under `IFNE V3` the same scan now
calls the vector the video globals publish at `VBL.WrBlk`; ArmIO's `WrBlk` copies the run
into `VG.WBuf` and makes one `CF.WriteN` call, and CoArm's `TxPutRun` writes it into the
shadow and pushes it to the card with one `WPTR` load, one pair lookup and one cursor
update. **24.3 lines a second**, and the screen is an 80-column simulation of the file
row for row.

⛔ **Y is the video globals in every CoArm routine** — `vidcore` finds the card with
`ldu VG.Base,y` — and the first `TxPutRun` borrowed Y for the run's pointer. `VcPtr` then
read two characters of the listed text as the card's address and wrote `WPTR` into
CoArm's own code, which became a direct-page store to `D.VIRQ`; the next tick jumped
through it. The same shape waits for anything entered with a register convention: a
`/FIRQ` service gets **U = `D.FIRQSt`**.
| **`libvid`** | a subroutine module the owner links: `VlWait`, `VlPut` and `VlGet` (a `WPTR` and up to 16 bytes), `VlFill`, `VlPoke` (up to 13 addresses) and `VlRect` (span-solid). Each waits for the card, reloads `WPTR`, reads `CTRL`'s `WMODE` and `WADV` back and sets them, and masks `/IRQ` for the call: **398 µs** at most, measured. Not built: text, icons, polygons and images |

**`overworld` is the demo's game on these** (`software/demo/demo.asm`'s loop): it steps the
camera through the frame records by the frames `SS.FrmWait` says passed, writes the map
strips that scroll into view with `libvid`, builds the hero's fifteen tiles by reading the
background tiles back out of VRAM, and hands the scroll, the hero's flip and the two
record numbers to one `SS.Batch`. So camera and hero change in the same blank. **Measured:
every one of 1,519 frames is `render()`'s; the camera steps one record a frame in 90% of
pairs; the 67 flips start 0.51–0.64 ms after `VBLANK` rises and take 0.47–0.78 ms, none into
the picture.**

⭐ **How much of a frame the hero gets is the card's difference.** On video3 the build runs
stages until the frame ends, because the frame count is a register read (`+$1F`) — **a hero
every 5 frames**, where ten stages a frame and then sleeping was 16. On video/ the count is a
~1.4 ms system call, and asking for it mid-build cost the camera its one-record-a-frame claim
and took the flip's IRQ over the 16C550's 1.4 ms, so video/ still builds **a tile a frame**.
Both keep the rest: `cbuf` **is** four `libvid` records, so a tile is read and written in place
rather than copied; the sprite loop visits only the columns inside the sprite; and there are
**three hero buffers**, so the next build starts in the frame of the flip.
`video3/docs/demo-report.md` §10.3 has the trace and the numbers.

⛔ **Three things the first runs found.** The hero's next build began in the pass that queued
the flip, and wrote into the buffer still on the screen until that batch's blank — which is
why there are three buffers now, and not two. A map column
as 26 `libvid` puts cost enough to miss one frame in five; one poke per half-column fixed it.
And 15 single-cell puts in the flip took up to 1.04 ms of the blank, 4% of flips into the
picture; `BT.Poke`, and committing the batch before the palette, fixed that.

## The extensions (`$60`–`$69`)

| | |
|---|---|
| `$60` Pal565 PRN HI LO, `$61` PalRange FIRST COUNT (HI LO)×COUNT | RGB565 entries (`ca_tile.asm`) |
| `$62` PatDef P B×8, `$63` PatBar X1 Y1 X2 Y2 | an 8 × 8 1bpp pattern, which becomes the window's; a rectangle in it, 1 foreground and 0 background, aligned to screen rows and columns mod 8 |
| `$64` PutMask GRP BUF X Y | a 1bpp buffer (style 5): 1 bits in the foreground, 0 left |
| `$65` Poly NL NR (X Y)×, `$66` PolyPat | a filled polygon by `show.py`'s rule: a left and a right chain from the top vertex to the bottom one, 16 vertices in all, edges stepped in 16.8 from (x0 << 8) + 128, line y covering [xl, xr) — `gui.asm`'s `polyfill`'s format, not plan §5.2's single list |
| `$67` Image GRP BUF X Y | PutBlk, for an 8bpp buffer |
| `$68` Icon GRP BUF X Y SEL | a buffer holding `show.py`'s `Icon` blob, each layer's 1 bits in its colour or its selected colour |
| `$69` AnsiSw F | the device's bytes as an ANSI terminal's (`show.py`'s `Model.t_bytes`): CR, LF, BS, and CSI `m J H f K C D A B`; a line full wraps before the next glyph. `ESC $69 0` turns it off |

## The status calls

| | |
|---|---|
| GetStat | `SS.Ready`, `SS.EOF`, `SS.Mouse` (ArmIO); `SS.ScSiz`, `SS.ScTyp`, `SS.FBRgs`, `SS.Cursr` (CoArm) |
| SetStat | `SS.SSig`, `SS.Relea`, `SS.FrmWait`, `SS.FrmSig`, `SS.Batch`, `SS.TileLd`, `SS.MapWr`, `SS.TBank`, `SS.CFont` (ArmIO); `SS.Raster`, `SS.RastOff`, `SS.Excl` (CoArm). The codes are `defs/arm6309.d`'s |

## ⭐ The console's font, changed under the text (`SS.CFont`)

**A character cell is a code and an ATTR byte, and the card fetches the glyph
out of a VRAM bank every frame.** So replacing the bank's 2,048 bytes changes
every character *already on the screen* — all 4,800 cells of an 80 × 60
console — with **nothing repainted, no cost per cell, and the map never
touched**. It is sixteen writes of 128 bytes.

```
/DD: changefont uncial >/w1
```

`SS.CFont` ($E0, `vidfnt3.asm`'s `XCFont`) takes **X = 2,048 bytes: 256 glyphs,
8 × 8, one bit a pixel, eight bytes each, in code order**. ⭐ That is the format
NitrOS-9's own font modules are already in — `level1/wildbits/sys/fonts/*.asm`
are exactly this — so the 27 wildbits faces drop in without conversion.
`software/nitros9/tools/mkfonts.py` reads the glyph bytes out of that source and
writes each face to `/DD/SYS/FONT.<name>`; `changefont` reads one and hands it
over. **Nothing is assembled and no font module is loaded**: the ROM never links
them.

It shares `F3Row` with the built-in bank, so a downloaded face and CP437 reach
the card by the same path, and `changefont cp437` puts the original back.

- ⚠ **The bank is the SCREEN's, not the window's.** Every window on the
  character screen changes together; there is one bank (`TX3.TBank`).
- ⛔ **Refused on a bitmap screen** (`E$IllArg`). `TX3.TBank` is a fixed VRAM
  address a bitmap screen keeps something else at. video3's MODE is CTRL b3..2.
- ⚠ **A short file is refused too** — a font is 2,048 bytes exactly.
- ⚠ **It costs no CoArm**, which is why it is a SetStat in ArmIO rather than
  an escape: CoArm is **16,383 of the 16,384 bytes** ArmIO maps it in.

## The keyboard

`KbdArm` initialises the keyboard port by `ps2.md` §11.2: phase, `FF` → `FA AA`, `F4` →
`FA`. Transmit is `ps2tst`'s, with `/IRQ` masked for **1.9 ms** a byte, at Init only. It puts
one service on the polling table for **both** ports' ready bits.

It sets both of `IOCTRL`'s enables, b6 `KIRQEN` and b7 `MIRQEN` (`ps2.md` §8.2), and clears
them at Term. ⛔ **The first build took only `KDR` when one `IRQEN` served both ports**: the
mouse's power-on bytes were waiting in `MDR`, so enabling the keyboard raised `/IRQ` for a
port no service claimed, IOMan's poll found no claimant, and the kernel returned from the IRQ
with interrupts masked for 40 ms. A port with no service now stays quiet with its enable
clear.

Scan codes (set 2, Wildbits' tables) become CoCo 3 key values. The arrows are `$0C $0A $08
$09`, Esc is BREAK `$05`, and F1/F2 are `$B1`/`$B2`. Shift, Ctrl, Alt and Caps Lock are
tracked, and Pause's eight bytes are swallowed. The window's interrupt, quit and pause
characters signal rather than buffer. Keys go to the window whose screen is displayed.

## What it does not do yet

- **Plan §5.3's other calls**: `SS.VInfo`, `SS.Pal565`, `SS.VRead`, `SS.VWrite`, `SS.Scroll`,
  `SS.Flip`, `SS.LineSig`; and `libvid`'s text, icons, polygons and images.
- **`show` through the driver** — plan phase P5, with the applications.
- **Pointer shapes.** Any `GCSet` group but 0 is the arrow.
- **LEDs and typematic.** A transmit masks `/IRQ` for ~10 ms (`ps2.md` §7.1), so Caps Lock's
  state is kept and not shown.
- **A console only on the emulator.** Nothing has run it on `machine_tb`.
