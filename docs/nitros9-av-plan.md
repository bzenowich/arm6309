# NitrOS-9 video and audio drivers — plan, 2026-09-14

**This is a plan, not a specification.** It says what driver code turns `software/demo/`
into real NitrOS-9 Level 2 applications, which decisions shape that code, and in what order
to build it. It is dated and meant to be thrown away. When an item lands, its substance goes
into a spec (a new `software/nitros9/docs/` or the card documents) and the item is deleted
from this file.

It is based on a read of `video/docs/graphics.md` and `features.md`, `audio/docs/audio.md`
and `modplayer.md`, `docs/machine.md`, `io/ps2/docs/ps2.md`, the demo sources (`demo.asm`,
`gui.asm`, `replay.asm`, `tools/show.py`, `emu/machine.c`) and `~/code/nitros9` (the CoCo 3
VTIO/CoWin/GrfDrv stack, the kernel, clock, and the `wildbits`, `coco3fpga`, `mc09l2` and
`picothing` ports). Where prose and a design output disagree, this plan follows the design
output (CLAUDE.md). §11 lists the disagreements found along the way.

---

## 0. Summary

**What gets built:**

| Module | Kind | Replaces / modelled on | Size guess |
|---|---|---|---|
| `VidCore` | subroutine module: the card's rules in one place | nothing on a CoCo; the demo's `setxy`/`wready`/`golist` | M |
| `VTArm` | SCF device driver: console, input buffer, escape parser, SetStat/GetStat | `level2/coco3/modules/vtio.asm` | L |
| `CoArm` | co-module: screens, windows, GP buffers, fonts, renderer | `cowin.asm` + `grfdrv.asm`, rewritten | **XL** |
| `KbdArm`, `MseArm` | VTArm sub-modules for PS/2 (`$FF30`) | `wildbits/keydrv_ps2`, `mousedrv_ps2` | M |
| `clock` (port variant) | VBL tick with a **variable** rate | `level2/modules/clock.asm` | S |
| `AudDrv` + `/Aud` | SCF device driver: tick-queue player, sample RAM, bell | nothing exists in NitrOS-9 | M |
| kernel FIRQ stub | `krn.asm` port conditional | `D.XFIRQ` = `D.Crash` today | S |
| `libvid` | user-space RMA library for exclusive-screen programs | `gui.asm`'s primitives, re-homed | M |
| `modplay`, `sfx` lib | user-space replayer emitting tick records | `replay.asm` | M |
| descriptors | `/Term`, `/W`, `/W1`–`/W15`, `/Aud` | `term_win80.asm`, `w*.asm` | S |
| demo applications | `desktop`, `paint`, `ansiterm`, `raster`, `overworld`, `player` | the show's scenes | L |

**The seven decisions that shape it** (§3 has the argument for each):

1. **Keep CoWin's wire protocol and write a new renderer.** Retargeting GrfDrv is not
   practical, and dropping the protocol (as Wildbits did) costs every existing windowing
   program.
2. **The renderer runs in system state, not in a GrfDrv task.** VRAM is a port in the I/O
   page (`VDATA`), so there is nothing to map.
3. **All drawing goes through five span operations**, with two back-ends: the card, and a
   DRAM backing store for screens that are not displayed.
4. **Only the VBL service touches the card from interrupt level.** It acknowledges, commits
   queued register and VRAM batches, and issues `GO`. Main-line primitives are atomic
   against `/IRQ`.
5. **Exclusive screens** for games and demos: the driver hands the card to one process and
   keeps only the tick, the frame signal and the VBL batch.
6. **Audio is a register-stream player.** The ProTracker replayer runs in user space and
   computes ticks ahead. `/FIRQ` only *commits* one precomputed tick, so it is short and
   jitter-free.
7. **`/FIRQ` gets a port-conditional kernel stub.** Stock Level 2 crashes on any FIRQ.

---

## 1. What the demos exercise, and what they get away with

The demo ROM covers the whole capability list in `features.md` §0. It does so as the
machine's only program, and a multitasking OS takes away each of the conveniences below.
Details are in the research notes; line numbers are from `software/demo/`.

| The demo does | Under NitrOS-9 this becomes |
|---|---|
| One global `WPTR` and shadowed span registers (`gui.asm:249-304`), no locking | Driver-owned registers. A primitive's `WPTR`→trigger sequence is atomic against the VBL service |
| Unbounded busy-polls: `wready`, `idle`, `vblank`, `SYNC` on `fcnt` | System state is not preempted, so a busy-wait stops the OS. Short polls stay (≤ 40.7 µs `SPANBUSY`); anything frame-length sleeps on the VBL event |
| `golist` masks both interrupts from list END to `GO`, and serves VBL itself (`gui.asm:335-360`) | `GO` belongs to the VBL service (§3.4). A list must END before VSYNC |
| `irqh` assumes `/IRQ` is only VBL and that `DP=$FF` (`demo.asm:1096-1118`) | `F$IRQ` polling entry: `$FF73`, flip `$00`, mask `$01` |
| `firqh` assumes the timer is the only source, re-enables IRQ, and runs a 4.2 ms tick (`demo.asm:1129-1140`) | Short FIRQ commit (§3.6), heavy work in user space |
| The replayer writes MMU entries 2/3 from FIRQ to read patterns from ROM (`replay.asm:968-1024`) | Impossible under kernel task maps. The module lives in the player process's memory |
| Assets addressed by ROM page (`mapgp`, `romat`) | Caller buffers, passed by pointer and `F$Move`d |
| VRAM layout by convention: tiles at row 480, map at 496, lists at 500 | A VRAM allocator per screen (§3.3) |
| The pointer and all typing are scripted in `mkshow.py` | Real PS/2 keyboard and mouse sub-drivers |
| Palette 0–15 rewritten for the BBS; `CTRL` global | Palette per screen, committed at screen select, 32 entries per blank, as the demo does |

---

## 2. What the hardware requires of any driver

These are the card rules as the design outputs implement them. **`VidCore` is the only code
that knows them.** Everything above it calls `VidCore`.

### 2.1 Video (`$FF60`–`$FF7F`, base from the descriptor)

| # | Rule | Source |
|---|---|---|
| V1 | **No register access except `VSTAT` while `SPANBUSY` (b7) is set.** A write lands in `WFG`/`WBG` and corrupts the span; the intended register is not loaded. `CTRL` and the `VSTAT` acknowledge still take effect, **and also** corrupt the colour | `regfile.jedec.ts:52-60`, g.md §19 items 38/39 |
| V2 | **No register write and no VRAM access while `LRUN` (b4).** A write in the same dot as a grant costs the list a byte; VRAM access moves the list's pointer | `video_card.v:319-323`, g.md §10.3.1 |
| V3 | **`WPTR` is the list pointer.** Reload after every `GO`. Little-endian: `+$08` low, `+$0A` high | `vaddr.v:724` |
| V4 | Register reads return **the last byte the CPU wrote** (a SRAM register file), except `VSTAT` and `VDATA`. Keep shadows of everything | `machine.v:239-256` |
| V5 | VBL acknowledge is **any write** to `VSTAT`; reading does not clear. The write is itself subject to V1/V2 | `sync.jedec.ts:266` |
| V6 | Palette `PDATH` commits snow 3 dots, so commit in blanking. Blank left after the IRQ is 1.176 ms (449-line family) or 1.112 ms (525) | g.md §13.1; `sync.timing.ts:54-72` |
| V7 | `HSCROLL`/`HSCROLLH` load every line; `VSCROLL` pair loads throughout VBLANK. Write each pair atomically | `vaddr` `HLOAD`/`VLOAD` |
| V8 | Switch `VMODE` family only just after VBLANK falls (the terminal-count decode is partial) | `vctrl.v:262-264` (inferred, not in any doc) |
| V9 | Cell mode is `VMODE` 00/01 only, and halves the span retire rate | g.md §6.4.1, §6.4.2 |
| V10 | A display list must fit in one ring row (the walk wraps at column 1024 without carrying). MOVE reaches only `+$03 +$04 +$10 +$11 +$12` | g.md §10.3.2 |
| V11 | The VBL tick is **70.086 Hz or 59.940 Hz** depending on `VMODE0` | g.md §6.2 |
| V12 | `/WAIT` holds E, and therefore interrupt dispatch, for up to 40.7 µs under a solid span. Poll b7 first | g.md §7.4 |

### 2.2 Audio (`$FF40`–`$FF4F`, base from the descriptor)

| # | Rule | Source |
|---|---|---|
| A1 | **Poll `ASTAT` b6 before every write.** A write while busy is lost and sets `AINTREQ` b5 | `aseq.jedec.ts:298`, audio.md §16 item 47 |
| A2 | `AIDX` and the multi-byte shadow (`LC`, `LEN`, `PER`, `TIMER`, `SPTR`) are **shared**. The FIRQ commit and main-line access must never interleave, so mask FIRQ around each main-line sequence | audio.md §9.4.3 |
| A3 | `ACTRL` and `AINTENA` are write-only; keep shadows | audio.md §9.2 |
| A4 | `SDATA` is **write-only in practice** (lane 2 is not prefetched) | `audio.cpld.ts:161-176`, `modplay_tb.sv:418` |
| A5 | Card RAM holds **offset binary**; XOR `$80` exactly once | audio.md §13.3 |
| A6 | Load `TIMER` before setting `ACTRL` b6. `TIMER`=0 is invalid. `N = 1773447/BPM` | audio.md §8.2 |
| A7 | Acknowledge by writing the bit with b7=0 to `AINTREQ`. Pending bits read whether or not they are enabled | audio.md §8.1 |
| A8 | Non-looping samples point their loop at the null block `$00000` (`$80 $80`); never write `LEN`=0 by accident | mp §4.2 |
| A9 | Retrigger is stop-then-start on `ADMACON`; simultaneous starts are one write | mp §5.3 |

---

## 3. Architecture decisions

### 3.1 CoWin's protocol, a new renderer

NitrOS-9's windowing API is a byte protocol written to a path: `$1B xx` escape codes
(`cowin.asm:84-195`) plus the SS.* SetStat/GetStat calls. Shell scripts, BASIC09's GFX2,
Multi-Vue and every windowing program speak it. The CoCo implementation splits into:

- **`cowin.asm` (5,760 lines).** Mostly hardware-independent: it parses parameters, manages
  the window and screen tables and GP buffers, and forwards pixels to GrfDrv.
- **`grfdrv.asm` (7,390 lines).** Entirely GIME: 1/2/4bpp packed screens mapped into
  `$8000`–`$FFFF` of its own task, with bit-mask pixel loops.

**GrfDrv cannot be retargeted.** Every one of its primitives addresses mapped screen memory
with packed pixel masks. This card has no packed modes and **no flat VRAM** (`VDATA` at
`WPTR` is the only access, g.md §6.3, §19 item 44).

**Wildbits' route** (`level1/wildbits/modules/vtio.asm`) is a monolithic text driver with
an escape subset, plus SetStat calls that hand bitmap blocks to user space. It is small, but
it offers no windows, and applications draw pixels themselves. Here that would mean every
application re-implements `VidCore`'s rules.

⭐ **Recommendation: keep the protocol and the VTIO/co-module split, and write `CoArm`.**
Its upper half follows `cowin.asm`'s structure (window/screen tables, parameter collection,
GP buffers). Its lower half is a new renderer built on §3.3's span operations. New
capabilities are added as escape codes in the unused range and as SS codes (§5).
Compatibility with CoCo screen types (§5.1) is a later phase and only partial: there is no
320-wide mode and no 1/2/4bpp.

⚠ **Do not name the driver `VT*`.** Level 2 SCF sends bulk text straight to GrfDrv function
`$06` if `PD.PAR`=`$80`, the driver name starts with "VT", and `G.GrfEnt` is non-zero
(`level1/modules/scf.asm:1044-1080`). `VTArm` is only a working title: use `ArmIO`, or
guarantee `G.GrfEnt` = 0.

### 3.2 No GrfDrv task

GrfDrv has its own task (task 1, reserved at `krn.asm:543`) because it must map four blocks
of screen memory. `CoArm` needs no screen mapping: `VDATA` is in the I/O page, visible in
every map. The renderer runs as ordinary system-state driver code, which removes
`D.Flip0`/`D.Flip1`, `G.GrfStk` and `G.GfBusy`.

⚠ **The price is system address space.** The CoCo keeps GrfDrv out of the bootfile for that
reason, and Wildbits caps its L2 bootfile at 32,256 bytes. Fonts, GP buffers and backing
stores live in `F$AllRAM` blocks mapped only while in use. **If `CoArm` outgrows the system
map, fall back to GrfDrv's arrangement** (its own task, entered through a flip), which
changes nothing above it. Measure the size at the end of phase 2 and decide then.

### 3.3 Five span operations, two back-ends

Every primitive in `gui.asm` and every CoWin function decomposes into:

| Op | Card back-end | DRAM back-end |
|---|---|---|
| `SpSolid x y w c` | `WMODE 10`, `SPANLEN`, one write per ≤256 px | fill |
| `SpMask x y bytes fg bg` | `WMODE 01`, 8 px per write | bit loop |
| `SpSprite x y bytes fg` | `WMODE 11`, 8 px per write, 0 = skip | bit loop |
| `SpPut x y n buf` | `WMODE 00` direct stream (TFM candidate) | `TFM` |
| `SpGet x y n buf` | `VDATA` read, +1 per byte | `TFM` |

plus a `WADV 01` "column" form of the first three, which draws a glyph or a pattern column
in 8 writes.

**Why two back-ends.** A process can draw to a window on a screen that is not displayed, but
512 KB of VRAM does not hold many screens. A text screen that scrolls by `VSCROLL` also
rotates the whole ring, and there is no VRAM-to-VRAM copy to move a screen out of the way.
So:

- **The displayed screen lives in VRAM.** A managed screen pins `HSCROLL`=0, which leaves
  columns 640–1023 of every row (196 KB) as driver scratch: lists, the pointer's sprite
  data, a tile or glyph bank.
- **Hidden screens live in DRAM.** A 640×200 screen is 128 KB and a 640×480 one 307 KB, in
  `F$AllRAM` blocks. On select, the new screen is streamed in through `VDATA` and the old
  one read out. That is ~0.2 s each way at 640×200 (~0.4 s for a switch) and ~0.45 s each way at
  640×480, assuming `TFM` at 3 cycles per byte. ⚠ `TFM` behaviour against a side-effecting port is an open machine-level
  decision (machine.md §6).
- **Text screens also keep a cell shadow** (glyph, fg, bg per cell; 14.4 KB at 80×60). It
  redraws overlay windows, scrolls sub-windows, and repaints a text screen on select
  without a pixel store.

⚠ **Scrolling is the performance cliff, and it should be written down before anyone is
surprised by it.**

| Window | How it scrolls | Cost |
|---|---|---|
| Full-screen text | `VSCROLL += 8`, clear one row | ~2.5 ms |
| Text sub-window | redraw from the cell shadow | ~31 µs per cell; a 40×20 window ≈ 25 ms per line |
| Graphics window with text in it | `SpGet` + `SpPut` per row | ≈ 1.8 ms per 640-px row; a 192-row window ≈ 350 ms |

The third row is the blitter's case (`features.md` §5). Until one exists, `CoArm` scrolls
graphics windows by clearing rather than copying unless the program asks otherwise.

The desktop's other expensive path, 8bpp image copy, is `SpPut` at CPU speed: 220,800 bytes
for the demo's photograph.

### 3.4 Interrupt ownership: the VBL service

VBL is the system tick (machine.md §4). The clock module's IRQ path calls a **`VidCore` VBL
service** first. In order, it:

1. Waits out `SPANBUSY` (≤ 40.7 µs; about double in cell mode).
2. Checks `LRUN`=0. A list still running at VSYNC is a contract violation: count it and
   acknowledge anyway.
3. Writes `VSTAT` (acknowledge).
4. **Commits the frame batch.** This holds pending `CTRL`, both scroll pairs, `TILEBASE`,
   palette entries (32 per blank, V6: a full 256 is 1.2 ms) and small queued VRAM patches (`WPTR` + bytes).
   The budget is about 0.5 ms, **measured and enforced**, and anything over carries to the
   next frame.
5. **Starts the displayed screen's list**: load `WPTR`, then `GO` (§3.4.1).
6. Wakes processes sleeping on the frame event and sends any requested frame signals.

To keep that safe, **every main-line span op masks `/IRQ` from its first register write to
its trigger write.** That is ≤ 12 µs of setup (5 writes, features.md §3.2). The retire runs
after the unmask, and the service's step 1 waits it out. ⚠ Total IRQ-masked time per
primitive has never been measured; phase 1 measures it.

**Main-line drawing and lists.** While `LRUN` is set, drawing cannot proceed (V2). `VidCore`
knows the list's last `WAIT` line, so it can tell a short remaining run (poll) from a long
one (sleep to the next frame). ⚠ **A frame-long list therefore throttles drawing on that
screen to about one blank's worth per frame.** That is inherent in the shared `WPTR`
(features.md §4). Programs with full-frame lists are exclusive-screen programs in practice.

#### 3.4.1 When to issue `GO` — the one real timing problem

A `WAIT` counts scanlines from `GO`. The demo issues `GO` "just after VBLANK falls" by busy
polling with interrupts masked (`gui.asm:335-360`), which is 1.1 ms masked every frame. Under
the OS there are three options:

- **(a) Poll in the service.** Keep IRQ masked in the VBL service until VBLANK falls. It
  works today and costs ~1.1 ms of masked time per frame, only while a list is active. The
  16C550's 16-byte FIFO covers ~1.4 ms at 115.2 kbaud, so it is marginal.
- **(b) `GO` immediately, with a prefix.** `GO` at step 5 with 37 `WAIT`s prepended (35 in
  the 525-line family). Effects then land late by the service's dispatch latency, in whole
  lines: 48–191 µs is ≈ 2–6 lines, and it varies (machine.md §4, ps2.md §14 item 3). Raster
  bars jitter visibly.
- **(c) An armed `GO`, a hardware change.** A `GO` written during VBLANK arms, and VBLANK's
  falling edge starts the list. Software then issues `GO` from step 5 with zero jitter and no
  masked wait. ⚠ `vsup`'s fit margin is thin (g.md §19 item 46), so this needs a fit before
  it is a plan.

**Recommendation: (a) now, (c) proposed as a hardware item** (§10). (b) is the fallback if
(a)'s masked time hurts serial.

### 3.5 Exclusive screens and `libvid`

The show's per-cell cost is 13 writes, ~31 µs. A NitrOS-9 system call round-trip is
unmeasured, and on Level 2 plausibly several hundred µs. **So drawing must be batched.**
CoWin's protocol already batches: one `I$Write` carries many escape sequences, and that is
the path for windowed programs. A game or a demo scene also wants no path overhead at all.

`SS.Excl` (§5.3) claims the displayed screen and the card:

- The driver stops drawing, the pointer and palette management for that screen. It returns
  the register base and the VRAM geometry.
- **It keeps** the tick, the VBL acknowledge and the frame batch (§3.4 step 4), which is how
  a game gets its scroll and flip into the blank without running code at interrupt level.
  `demo.asm`'s `flip` (0.29–0.53 ms) and `scrollp` fit the batch budget as they stand.
- The process draws directly through **`libvid`**: `gui.asm`'s `setxy`, `rect`, `pat`,
  `text`, `icon`, `poly`, `image` and cursor routines, re-homed as a position-independent
  RMA library with V1–V3 built in and interrupt masking per op as in §3.4.
- `SS.Excl` is refused while another exclusive owner exists, and released on path close or
  process death (the driver's Term/close path).

⚠ NitrOS-9 cannot stop a user process from writing `$FF60` without `SS.Excl`; the I/O page
is in every map. That is a convention, as it is on the CoCo.

### 3.6 Audio: a register-stream player

The demo's replayer runs its whole tick inside FIRQ: up to 4.2 ms, remapping the MMU and
re-enabling IRQ. Under Level 2 none of that can stay. Instead:

- **`AudDrv` owns a ring of tick records.** Each record is a compact form of the register
  stream `refplayer` already emits: `AIDX`+`ADATA` runs, `ADMACON`, `ACTRL`, `TIMER`, END.
- **The FIRQ commit** acknowledges the timer, then writes the next record with A1's poll per
  byte. A trigger tick is ≤ ~40 writes, well under a millisecond, and a normal tick is a few
  writes. Then RTI.
- **The replayer is a user process** (`modplay`) that keeps the ring topped up. Below a low
  mark the driver sends it a signal. A ring of 32 ticks is 0.64 s at 50 Hz, which covers any
  scheduling delay.
- **Register timing is set by the card's timer, not by the CPU.** That is better than the
  demo, whose notes start up to 4 ms late (`software/demo/README.md`, "Why refplayer is not
  the audio control here"), and it makes `modplay`'s stream comparable **byte for byte and
  tick for tick** with `refplayer`'s trace.
- **The driver validates each record** against the path's channel-ownership mask, so the
  music and sound effects can share the card (§6.3).

### 3.7 The FIRQ stub

`krn.asm:102` sets `D.XFIRQ` to `D.Crash`. `FIRQVCT` (`krn.asm:1428`) forces task 0 and
DP=0 on an entry that stacked only PC and CC, so a stock handler cannot return. The port
needs an `IFNE arm6309` stub that:

1. Pushes the registers it uses.
2. Selects the system map and DP.
3. Calls the audio service through a vector `AudDrv` installs.
4. Restores the task map it interrupted and returns.

It must be re-entrant against `/IRQ`, which a 6809 masks on FIRQ entry anyway. **Keep IRQ
masked for the whole commit**: it is short, and that avoids nesting the kernel's IRQ path
inside FIRQ.

---

## 4. Video: feature coverage

Every capability in `features.md` §0, with the mechanism that provides it and the API that
exposes it (§5).

| Card feature | Driver mechanism | API | Demo that needs it |
|---|---|---|---|
| 4 × `VMODE`, 640×200/240/400/480 8bpp | Screen types; mode set in the VBL batch (V8) | `DWSet` types `$10`–`$13` | all |
| Display enable | Blank the screen during select and palette load | internal | all |
| 256 of 65,536 colours, RGB565 LUT | Per-screen 256-entry palette shadow, committed across blanks | `Palette` (6-bit, legacy), `Pal565`, `SS.Pal565` | desktop, BBS, game |
| 1024×512 ring, free scroll both axes | Console `VSCROLL`; exclusive `SS.Scroll` via the batch | `SS.Scroll` | BBS, game, paint |
| 512 KB VRAM, double buffering | Flip = `VSCROLL` to row 256 in the batch (exclusive, 200/240-line) | `SS.Flip` | game |
| `WMODE 10` span-solid | `SpSolid` | `Bar`, `Box`, `CWArea` clear, horizontal `Line` | desktop, paint |
| `WMODE 01` span-mask | `SpMask`: glyphs, 2-colour patterns | text, `PSet` pattern with ≤2 colours, `PatBar` | desktop, BBS |
| `WMODE 11` sprite | `SpSprite`: pointer, text caret, masked icons | `GCSet` cursor, `PutMask` | desktop |
| `WMODE 00` direct + `VDATA` read | `SpPut`/`SpGet`: GP buffers, save-behind, backing store | `GetBlk`, `PutBlk`, `OWSet` save, `SS.VRead`/`SS.VWrite` | paint image, pointer |
| `WADV 01` column chaining | Inside `SpMask`/`SpSprite`/`SpSolid` column forms | internal | all text |
| Polygon fill (CPU edges, span runs) | Edge stepper → `SpSolid`/`SpSprite` | `Poly`, `PolyPat` | paint |
| QuickDraw subset | Arcs, ellipses, `FFill`, diagonal lines in CPU, emitted as spans | `Circle`, `Ellipse`, `Arc`, `FFill`, `Line` | paint |
| Cell mode + `TILEBASE`/`MAPBASE` (tiles) | Tile screen type: bank upload, map writes, batch-committed bank switch | `DWSet` types `$1C`/`$1D`, `SS.TileLd`, `SS.MapWr`, `SS.TBank` | overworld |
| Cell mode as a console, 1 write/cell | Fast-text screen type; font baked into a bank at `DWSet` (~7.9 ms) | `DWSet` types `$18`/`$19` | `/Term` default |
| Display list: per-line `HSCROLL` | List composer in `VidCore`; lists in scratch columns (≤384 B) or a free row (≤1024 B) | `SS.Raster` (HScroll table) | paint wave, scroll bar |
| Display list: per-line palette | Same composer, 6 bytes per entry move | `SS.Raster` (palette table) | raster bars |
| VBL interrupt | Tick, frame event, batch, list `GO` | `SS.FrmSig`, `SS.FrmWait`, `SS.Batch` | game, all animation |
| `VMODE` changes tick rate | `VidCore` tells `clock` the family on each mode commit | internal | — |
| Mouse cursor, pixel-accurate | `SpSprite` shape + `SpGet` save of the bounding box, moved in the VBL batch | `GCSet`, `SS.Mouse` | desktop |
| Line compare (CPU module) | **Not built**; reserve an API like Wildbits' `SS.SOLIRQ` | `SS.LineSig` (reserved) | — |
| *Not provided by the card* | blitter, hardware sprites, `CHAR`, `BORDER` | `Border` accepted as a no-op | — |

---

## 5. API draft

Numbers are **proposals** and need to be frozen in `defs/arm6309.d` before any program uses
them. Existing CoWin codes keep their meaning.

### 5.1 Screen types (`DWSet` STY)

| STY | Screen | Notes |
|---|---|---|
| `$10`–`$13` | bitmap 640×200 / 240 / 400 / 480, 8bpp | text 80×25 / 30 / 50 / 60 via span-mask |
| `$18`, `$19` | fast text 80×25, 80×30 (cell mode) | one fg/bg pair per bank; up to 32 banks |
| `$1C`, `$1D` | tile playfield 640×200, 640×240 (cell mode) | exclusive-oriented |
| `$FF` | current screen | as CoWin |
| 1, 2 (CoCo 40/80-col text) | later phase: map to `$18`, with 40 columns as a 16×8 wide font | |
| 5–8 (CoCo 320/640×192) | later phase: map to `$10`, x doubled for 320-wide types, colours 0–15 direct | |

### 5.2 Escape extensions (proposed range `$60`–`$7F`, unused by `cowin.asm`)

| Code | Name | Params |
|---|---|---|
| `$60` | `Pal565` | prn, hi, lo |
| `$61` | `PalRange` | first, count, (hi lo)×count |
| `$62` | `PatDef` | pat#, 8 bytes (1bpp pattern, 2-colour fast path) |
| `$63` | `PatBar` | x1 y1 x2 y2 (uses fg/bg and current pattern) |
| `$64` | `PutMask` | grp buf x y (1bpp mask buffer drawn in `FColor`, transparent) |
| `$65` | `Poly` | n, (x y)×n (filled, `FColor`) |
| `$66` | `PolyPat` | n, (x y)×n (current pattern) |
| `$67` | `Image` | grp buf x y (8bpp GP buffer, `SpPut`, clipped) |
| `$68` | `Icon` | grp buf x y sel (multi-layer 1bpp, `show.py:215-233` format) |
| `$69` | `AnsiSw` | 0/1: ANSI/VT100 interpretation on this window (the `gui.asm:1412-1773` subset) |

### 5.3 SetStat / GetStat (proposed block `$D0`–`$EF`)

This avoids Wildbits' `$C0`–`$C4` and the third-party `$C7`–`$CB` in `defs/os9.d`.

| Code | Call | Direction | Effect |
|---|---|---|---|
| `$D0` | `SS.VInfo` | Get | card identity, modes, VRAM size, current `VMODE`, tick rate ×1000 |
| `$D1` | `SS.Pal565` | Get/Set | palette range to or from the caller's buffer |
| `$D2` | `SS.VRead` | Get | rectangle of 8bpp pixels to the caller's buffer |
| `$D3` | `SS.VWrite` | Set | rectangle of 8bpp pixels from the caller's buffer (bulk image) |
| `$D4` | `SS.Excl` | Set | claim or release exclusive screen; returns base and geometry |
| `$D5` | `SS.Scroll` | Set | `HSCROLL`, `VSCROLL` at the next VBL |
| `$D6` | `SS.Flip` | Set | `VSCROLL` page flip at the next VBL |
| `$D7` | `SS.Batch` | Set | queue register and `WPTR`+bytes patches for the next VBL (bounded) |
| `$D8` | `SS.FrmSig` | Set | signal on each or every *n*th frame |
| `$D9` | `SS.FrmWait` | Set | sleep until the next frame (a system-state wait, not a signal) |
| `$DA` | `SS.Raster` | Set | install or patch the screen's HSCROLL table and/or palette table; the driver composes the list |
| `$DB` | `SS.RastOff` | Set | remove the list |
| `$DC` | `SS.TileLd` | Set | upload one tile bank (256×64 B) from the caller |
| `$DD` | `SS.MapWr` | Set | write a rectangle of map cells |
| `$DE` | `SS.TBank` | Set | `TILEBASE` at the next VBL |
| `$DF` | `SS.LineSig` | Set | reserved for the CPU-module line compare |

| Code | Call | Direction | Effect |
|---|---|---|---|
| `$E0` | `SS.AInfo` | Get | channels, stereo map (LRRL), sample RAM free, underruns, overruns |
| `$E1` | `SS.AChan` | Set | claim or release a channel mask for this path |
| `$E2` | `SS.SAlloc` | Set | allocate sample RAM → card address |
| `$E3` | `SS.SFree` | Set | free it |
| `$E4` | `SS.SLoad` | Set | address, signed/offset flag, buffer, length → `SPTR`/`SDATA` in FIRQ-masked chunks |
| `$E5` | `SS.AQueue` | Set | append tick records; returns ring free space |
| `$E6` | `SS.ASig` | Set | signal on low water |
| `$E7` | `SS.AStart` | Set | `TIMER`, `AINTENA`, `ACTRL` b6/b7 |
| `$E8` | `SS.AStop` | Set | flush the ring and silence owned channels |
| `$E9` | `SS.APlay` | Set | immediate trigger on an owned channel: address, length, loop, period, volume (effects) |
| `$EA` | `SS.AFilter` | Set | LED filter (`ACTRL` b0) |
| `$EB` | `SS.AChPos` | Get | advisory `PTR`/`CNT` per channel (visualisers, player position) |
| `SS.Tone` `$98` | existing | Set | bell and tone on an unowned channel, from a square-wave sample uploaded at Init |

---

## 6. Audio: modules and coverage

### 6.1 `AudDrv`

- **Static storage**: shadows for `ACTRL`/`AINTENA`/`TIMER`, the tick ring, a sample-RAM free
  list (512 KB, first `$00002` bytes reserved for the null block, then the bell sample),
  per-path channel masks, and underrun/overrun counters.
- **Init**: reset the card to a known state (reset leaves `TIMER`/`SPTR` as garbage, A6);
  write the null block and the bell sample; install the FIRQ vector; `AINTENA` = timer only.
- **FIRQ service** (§3.6): acknowledge; commit one record if the ring has one, else count an
  underrun and hold; signal the owner at low water; acknowledge and count overruns (b5).
- **Main-line access** masks FIRQ around each multi-byte sequence (A2). An upload chunk is
  32 bytes, so a tick can be delayed by at most one chunk (~0.5 ms).
- **Stop.** `SS.AStop` needs one agreed order. `gui.asm:1805-1824` and mp §5.7 disagree
  (mp: clear `ACTRL` b6 **first**, then `ADMACON`), so settle it in audio.md before
  implementing.

### 6.2 Card feature coverage

| Card feature | Driver mechanism |
|---|---|
| 4 channels: `LC`, `LEN`, `PER`, `VOL`, loop by shadow reload | tick-record ops; `SS.APlay` |
| `ADMACON` set/clear, restart edge | tick-record op, masked to the path's channels |
| Tempo timer, 709,379 Hz ÷ `TIMER` | `SS.AStart`; `TIMER` op in a record (ProTracker `Fxx`) |
| `/FIRQ`: timer (b4) | commit service |
| `/FIRQ`: channel buffer end (b0–3) | not enabled for music; reserved for PCM streaming (§6.4) |
| `/FIRQ`: host overrun (b5) | counted, reported by `SS.AInfo` |
| 512 KB sample RAM, write-only | allocator + `SS.SLoad`; no read-back (A4) |
| `ACTRL` LED filter, bypass, master | `SS.AFilter`; master enable owned by the driver |
| Advisory `PTR`/`CNT` | `SS.AChPos` |
| Fixed LRRL stereo | reported by `SS.AInfo`; effects choose a channel for their side |
| *Retired*: `DAT`, `ATT`, `PAN`, 8-channel, raw volume | not exposed (`audio-scope`: ProTracker only) |

### 6.3 `modplay` and the effects library

- **`modplay`** is `replay.asm`'s transliteration of `mod_replay.c`, turned inside out:
  `mod_tick` emits a record instead of writing registers. It keeps state in its own data
  area rather than at `$C200`, and uses the existing ×4 in `volcode`.
- ⚠ **Pattern storage**: 64 patterns are 64 KB and do not fit a 64 KB process beside the
  code. Either keep patterns in `F$AllRAM` blocks and map one window as the demo maps ROM,
  or read patterns from the file on demand (mp §11 item 7 is this question).
- **Loader**: reads the `.mod` from a file, uploads each sample with `SS.SLoad`, and builds
  `smptab` from `SS.SAlloc`'s addresses instead of the running `SPTR`.
- **`sfx`** (a library, and a BASIC09 subroutine later): claim one or two channels with
  `SS.AChan`, upload short samples, trigger with `SS.APlay`. `modplay` accepts a channel
  mask and leaves claimed channels alone, which needs `C_OPER`/`C_OVOL` reset on release.

### 6.4 Later: PCM streaming

The Paula method: a ring in sample RAM, `SS.SLoad` per chunk, and each channel's
buffer-end interrupt (b0–3) re-points `LC`/`LEN`. 8-bit only, at rates of 3,546,895/`PER`
(22.0 kHz at `PER` 161). ⚠ A channel parked on the 2-byte null loop interrupts every two
samples, so enable only the streaming channels. Not needed by any demo.

---

## 7. Demos → applications

| Scene | Application | Built on | Replaces in the demo |
|---|---|---|---|
| Desktop, Files, window drag | `desktop` | windowed: `DWSet $13`, overlay windows, `Icon`, `PutMask`, `GCSet` pointer, PS/2 mouse | `mkshow.py`'s Stage, scripted pointer |
| Paint (rects, patterns, polygons, text, brush) | `paint` | windowed: `Bar`, `PatBar`, `Poly`/`PolyPat`, text; `Image` for `parrot.img` | `FILL`/`PAT`/`POLY`/`IMAGE` opcodes |
| Canvas scroll bar and Wave | `paint` | `SS.Raster` HScroll table; the window's rows only | `LISTHS`, `WAVEDF`/`WAVE` |
| BBS / TradeWars | `ansiterm` over `/T1` (serial) or DriveWire | a `$11`/`$12` window with `AnsiSw` on; scroll by `VSCROLL` when full-screen | `gui.asm` terminal |
| Raster bars | `raster` | exclusive screen + `SS.Raster` palette table, patched every frame | `RASTDEF`/`RASTER` |
| Overworld | `overworld` | exclusive tile screen: `SS.TileLd`, `SS.MapWr`, `SS.Batch` for scroll and flip, `SS.FrmWait` loop, `libvid` for the hero composite | `gamego`, `irqh`'s `scrollp`, `flip` |
| Audio Player | `player` (GUI) + `modplay` | `/Aud` | `MUSIC`/`STOP`, `firqh` |

⭐ **The show itself can survive as a test.** `show` is a player that reads `script.bin`
from a file and issues the same drawing through the driver. `show.Model` still renders the
expected frames, so `checkdemo.py`'s pixel-for-pixel judgement carries over to the driver
unchanged. That is the cheapest end-to-end check this plan can have.

---

## 8. Prerequisites outside the drivers

None of these is driver code, but no driver runs without them.

| # | Item | Why it blocks | Where |
|---|---|---|---|
| X1 | ✅ **landed 2026-09-14**: `software/nitros9/README.md` | | |
| X2 | Memory-manager patch for a block number wider than 8 bits. ⭐ **No longer blocks booting**: 8-bit blocks on a fixed high byte give 2 MB (`software/nitros9/README.md`). It is what the other 14 MB need | more than 2 MB of RAM | machine.md §5 item 6, `ram.md` §9 |
| X3 | ✅ **landed 2026-09-14**: the vectors point at `$FEEE`–`$FEFD` (`software/boot/README.md`) | | |
| X4 | Clock: VBL tick through `F$IRQ` on `$FF73`, **with a runtime ticks-per-second** instead of assembly-time `TkPerSec`; a fractional accumulator for 70.086 Hz | V11; timekeeping drifts ~86–106 s/day otherwise | `level2/modules/clock.asm` |
| X5 | FIRQ stub (§3.7) | audio | `krn.asm` |
| X6 | ✅ **landed 2026-09-14**: `/Term` on Wildbits' `sc16550` | | |
| X7 | **Emulator upgrades.** MMU tasks, register-file read-back and the 16C550 landed 2026-09-14. Still to do: VBL 10 lines in the 525 family, `WADV 10`, PS/2, and the audio host boundary from `audio/refplayer/card.c` (`machine.c` reads `$FF40`–`$FF4F` as 0, never busy) | every driver iteration; the machine run is 4.5 h | audio.md §16 item 14, g.md §19 item 13 |
| X8 | **Measure** Level 2 system-call round trip, IRQ dispatch cost and `TFM` into `VDATA`/`SDATA` | sizes batching (§3.5), decides §3.4.1, validates §3.3 | ps2.md §14 item 3 |

⚠ **`/IOPAGE` may move** (machine.md §5 item 15, decided and not built): per-slot 32-byte
windows at `$FE00`–`$FEFF`. **Every base address comes from a descriptor from day one.**

---

## 9. Order of work, and the check that closes each phase

| Phase | Work | Closed by |
|---|---|---|
| **P0** | X1–X7; boot NitrOS-9 to a serial shell on the emulator. ⭐ **Both halves landed 2026-09-14**: `software/nitros9/run-emu.sh` (11 claims) and `machine_tb +scenario=nitros9` (12 claims, from reset on the RTL). Still open: X4, X5 and the rest of X7 | `emu` reaches `Shell` and runs `dir` from the ROM disk; the same on `machine_tb` as a new scenario |
| **P1** | `VidCore` (V1–V12 and the VBL service); fast-text `/Term` on cell mode; `KbdArm`; CoWin control codes `$01`–`$0D`, `$1F` | a scripted client's output: emulator frames vs a Python model of the expected text screen; `VidCore` IRQ-masked time measured |
| **P2** | `CoArm` bitmap screens and windows: `DWSet`/`OWSet`/`Select`, span-mask text, cell shadow, `Bar`/`Box`/`Line`/`Circle`/`Ellipse`/`Arc`/`FFill`, GP buffers, `Get`/`PutBlk`, fonts, palettes, backing store and screen switch, `MseArm` + `GCSet` pointer | `show` (§7) re-run through the driver, frames judged by `checkdemo.py`; decide §3.2's task question on measured size |
| **P3** | Extensions: `PatBar`, `PutMask`, `Icon`, `Poly`, `Image`, `AnsiSw`; `SS.Raster`; `SS.Batch`/`FrmSig`/`FrmWait`; `SS.Excl` + `libvid`; tile screens | raster and wave checkpoints at every phase (`show.raster_colours`); overworld frames vs `mkgame.render()`, and the flip budget (≤2 % into active video, as `checkdemo.py` asserts today) |
| **P4** *(parallel with P1–P3 once X5 and X7 land)* | `AudDrv`, bell/`SS.Tone`, `modplay`, `sfx` | `modplay`'s committed register stream vs `refplayer`'s trace, **byte for byte and tick for tick**; `dacwav` render A/B'd against libopenmpt with the `check:modplay` gate |
| **P5** | The six applications of §7 | each scene's checkpoints, in the emulator; one `run-demo.sh`-style machine run at the end |
| **P6** | CoCo screen-type mapping (§5.1), a BASIC09 subroutine module (Wildbits' `wild.asm` is the pattern), GFX2 | stock `display`-driven window scripts render |

---

## 10. Hardware questions this plan raises

Each needs the repository's usual treatment (a fit, a check, a spec entry) before it counts.

1. **Armed `GO`** (§3.4.1c). A `GO` during VBLANK starts the list on VBLANK's fall. It
   removes ~1.1 ms of masked time per frame, or visible jitter.
2. **A list-END event** (a `VSTAT` bit, optionally an IRQ). `VidCore` would not have to
   infer when drawing may resume (§3.4).
3. **A tick without a video card.** Nothing drives the NitrOS-9 tick if the video card is
   absent or its IRQ is disabled (design-review.md Sys-m6). The audio `TIMER` on `/FIRQ` is
   the obvious stand-in, and nothing connects them.
4. **`SDATA` read-back** (A4) would let `AudDrv` verify an upload. Low priority.
5. **The CPU-module line compare has no register map** (g.md §12.2). Its suggested GIME
   `$FF92/$FF93` address collides with the MMU high-byte window.

---

## 11. Documentation discrepancies found while researching

Design outputs are authoritative; these are prose fixes for the specs and their `history.md`
files, **not yet made**.

| Where | Says | Design output says |
|---|---|---|
| machine.md §4.1 (~l.504) | `VSTAT` is read-to-clear | **write**-to-clear (`sync.jedec.ts:266`) |
| graphics.md §10.3.1 sample (~l.2597) | `list>>16` to `+$08` | `WPTR` is little-endian; `+$08` is the low byte |
| graphics.md §10.3.1 (~l.2621) | "`BSTAT` b0 `LRUN`" | `VSTAT` b4 |
| graphics.md §13 `WADV` | `10` vertical, `11` reserved | 01, 10 and 11 all advance a row (`vctrl.v:335-337`) |
| graphics.md §13 reset | register file undefined | CPLD-held registers reset to 0; file, LUT and `PIDX` undefined |
| graphics.md §9 | RGB332 identity palette at boot | `boot.asm:426-439` loads `LUT[i] = $iiii` |
| graphics.md §6.4.6, features.md §0 | a list can change `CTRL` mid-frame | it cannot (§10.3.4) |
| `emu/machine.c` | VBL 12 lines after VBLANK in both families; file reads 0; `WADV 10` ignored | 10 lines in the 525 family; last-written byte; `WADV 10` = 01 |
| modplayer.md §5.7 vs `gui.asm:1805-1824` | stop order | disagree with each other |
| audio.md §9.2 | `SDATA` R/W | lane 2 not prefetched |

---

## 12. Decisions — taken 2026-09-14

The owner accepted all four:

1. **CoWin protocol compatibility** (§3.1). `CoArm` implements the `$1B` protocol and
   extends it; a Wildbits-style driver without windows is not pursued.
2. **Exclusive screens and direct register access** for games and demos (§3.5), through
   `SS.Excl` and `libvid`.
3. **§10's hardware items 1–2 (armed `GO`, list-END event) are pursued.** Each is fitted
   and checked on `vsup` before any driver depends on it. Until then `VidCore` uses
   §3.4.1's option (a).
4. **The replayer runs in user space** (§3.6). `AudDrv` commits precomputed tick records
   and does not parse modules.
