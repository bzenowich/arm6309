# Video compatibility: CoWin, GrfDrv, and what this card cannot be

**What this document is.** A gap analysis between NitrOS-9's two graphics interfaces — the
Level 2 **console window interface** (`vtio.dr` + `cowin.io`) and the **GrfDrv** renderer
behind it — and the arm6309 video card (`../../archive/video/docs/graphics.md`,
archived 2026-09-20). It says where the
hardware falls short, where the *interface* has to grow to reach features the CoCo 3 never
had, and what of the Wildbits port can be lifted rather than rewritten.

It is written against `../../../nitros9/INTRODUCTION.md` §9 and §10 (the tour), `cowin.asm`
and `grfdrv.asm` themselves, and what P0–P3 actually built (`video-console.md`). Where it
says "built", `video-console.md` is the authority; where it says "costs", the number is
from `run-vid.sh`'s `MASKLOG`/`CALLTIME` or from `graphics.md`.

**Sibling documents.** `video-console.md` is what exists. `docs/nitros9-av-plan.md` is the
plan. `docs/nitros9-hardware-improvements.md` is the ranked list of card changes; this
document feeds it and cites its H-numbers rather than repeating their cost models. Two
new items are proposed here (H18, H19) and one correction to H4's cost (§5.1); all three
belong in that list.

---

## Contents

1. [The one structural fact, and what it does to GrfDrv](#1-the-one-structural-fact-and-what-it-does-to-grfdrv)
2. [The console window interface: coverage](#2-the-console-window-interface-coverage)
3. [80-column text — three paths, and what each one costs](#3-80-column-text--three-paths-and-what-each-one-costs)
4. [The GrfDrv interface: what carries, what cannot](#4-the-grfdrv-interface-what-carries-what-cannot)
5. [Hardware shortfalls, ranked](#5-hardware-shortfalls-ranked)
6. [Extensions for features the CoCo 3 does not have](#6-extensions-for-features-the-coco-3-does-not-have)
7. [Leveraging Wildbits — the font system first](#7-leveraging-wildbits--the-font-system-first)
8. [Recommended order of work](#8-recommended-order-of-work)
9. [Open questions](#9-open-questions)

---

## 1. The one structural fact, and what it does to GrfDrv

**On a CoCo 3, video memory is memory.** GrfDrv moves itself into task 1's map
(`D.Flip1`), maps the screen's 8 KB blocks in, and draws with `STA`, `STD` and — on a
6309 — `TFM`. Every optimisation in `grfdrv.asm`'s 7,390 lines and its 30-year changelog
is a cycle shaved off a loop that stores into mapped RAM. Get/put buffers, fonts, patterns
and pointers live in the *same* address space, so a blit is a memory-to-memory move.

**On this card, video memory is a port.** VRAM is 512 KB behind a 19-bit `WPTR`
(`graphics.md` §13); a CPU access is a posted write or a prefetched read at `WPTR`, through
the VRAM window or `+$15` `VDATA` (§11), post-incrementing, arbitrated against the display
fetch and subject to `/WAIT`. **There is no address at which a pixel lives.** A byte costs
a bus cycle whatever the CPU is; `TFM` through `VDATA` would help (~1.6 µs/byte against
VidCore's measured ~10 µs), and neither the emulator's core nor `machine_tb`'s `mc6809e`
executes 6309 opcodes, so it cannot be measured here yet.

Three consequences follow, and they set the shape of everything below:

| | Consequence |
|---|---|
| ⛔ | **GrfDrv cannot be ported.** Not "with effort" — its rendering core is a memory model this card does not have. `CoArm` is the replacement, and that decision is already taken (`av-plan` §3.1, §3.2) |
| ⭐ | **The span writer is the compensation, and it is a good one.** Eight pixels per CPU write in span-mask, up to 256 in span-solid, ~4× that on the broadcast path (§7.4). For *glyphs* the card is faster than a CoCo 3 per write; for *arbitrary pixels* it is slower |
| ⚠ | **Anything GrfDrv does by reading memory back costs a `VDATA` stream here.** Save-behind, XOR cursors, `LSet` logic, window scrolling, `GetBlk`. This is where H1–H5 all come from |

The interfaces *above* GrfDrv are unaffected: `gfx2` builds escape sequences and writes
them to a path, `wcreate` writes `DWSet`/`OWSet`, and a program that speaks CoWin's byte
protocol does not know what draws for it. **That is the compatibility surface worth
defending**, and §2 is its audit.

---

## 2. The console window interface: coverage

CoWin's vocabulary is the control codes (`$01`–`$0E`, `$1F xx`) and the escapes
(`$1B`, function `$20`–`$54`), dispatched through the table at `L0027` in `cowin.asm`.
CoArm's table (`coarm.asm` `EscTbl`) carries **CoWin's own parameter counts**, so every
sequence consumes exactly its parameters even where the function is refused — which is the
property that keeps a stream in sync. That is the right base and it is already built.

### 2.1 Escapes, by verdict

| Verdict | Escapes | Note |
|---|---|---|
| **Built, faithful** | `DWSet` `Select` `OWSet` `OWEnd` `DWEnd` `CWArea` `DefGPB` `KillBuf` `GPLoad` `GetBlk` `PutBlk` `PSet` `LSet` `DefColr` `Palette` `FColor` `BColor` `GCSet` `Font` `TCharSw` `Bold` `SetDPtr` `RSetDPtr` `Point` `RPoint` `Line` `RLine` `LineM` `RLineM` `Box` `RBox` `Bar` `RBar` `PutGC` `FFill` `Circle` `Ellipse` `Arc` and the two filled conics | on bitmap screens |
| **Accepted, does nothing** | `Border` `$34`, `ScaleSw` `$35`, `DWProtSw` `$36`, `PropSw` `$3F` | §2.2 |
| **Refused (`E$IWTyp`)** | every drawing escape on a fast-text screen; everything but `Select`, `DWEnd`, `DefColr`, `Palette`, `Pal565`, `PalRange` on a tile or exclusive screen | §3 |
| ⚠ **Accepted and silently ineffective** | `Font` `$3A` on a fast-text screen — it sets `WT.Font`, which only the bitmap glyph path reads | §7 fixes this |
| **Not in CoWin at all** | `$60`–`$69` — our extensions | §6 |

### 2.2 The four no-ops, and which one matters

- **`Border` `$34` — no hardware, permanently.** `graphics.md` §9.3 deletes the `BORDER`
  register for three independent reasons: VGA timing has no overscan, the porches must be
  black for the back-porch clamp, and the `'153` pixel mux has no spare input. ⚠ **This is
  not a deferral.** A program that draws a coloured border gets black. Cosmetic, and the
  cheapest honest answer is what CoArm does — accept and ignore.
- **`DWProtSw` `$36` — a policy, not hardware.** Cheap to implement in CoArm if wanted.
- **`PropSw` `$3F` — proportional spacing.** Software; unimplemented.
- ⚠ **`ScaleSw` `$35` is the one that is a compatibility problem.** CoWin scales a window's
  coordinates from a fixed logical space (0–639 × 0–191) onto the working area, using
  `Wt.SX`/`Wt.SY`, and **scaling is on by default for graphics windows**. Nearly every
  CoCo 3 `gfx2` program written against a 320- or 640-wide screen relies on it. CoArm
  makes it a no-op on the grounds that "the new screen types are never scaled" — which is
  right for a program written *for this machine* and wrong for every program ported to it.
  **This is a software gap, not a hardware one**, and it is the single highest-value
  compatibility item in this document: two multiplies per coordinate in `ca_draw.asm`'s
  entry, and a `DWSet` that computes the two factors from `SZX`/`SZY`.

### 2.3 Control codes and `$1F`

Built in full on both screen classes, with two exceptions the hardware causes:

| | |
|---|---|
| `$07` bell | nothing until `AudDrv` — it is an audio-card item, not a video one |
| `$1F $22`–`$25` underline / blink | **accepted and not drawn** — blink has no hardware anywhere on the card, underline is possible and unbuilt (§3.1 items 4 and 5) |

---

## 3. 80-column text — three paths, and what each one costs

This is the section the question was really about. The card offers three ways to put 80
columns on the screen, and **none of them is a hardware character generator**:
`graphics.md` §6.4.3's Variant B — a 1bpp glyph serialiser with a per-cell attribute byte —
was priced and dropped on 2026-09-08, its macrocells spent on the display-list engine. Its
1bpp serialiser would also have landed on the card's tightest path, the 11.7 ns of margin
in index → LUT → output (§6.1), so a rebuild is not free even in silicon.

| | **Cell mode** (`$18`, `$19`) | **Span-mask bitmap** (`$10`–`$13`) | (dropped: Variant B) |
|---|---|---|---|
| Writes per cell | **1** | 13 | 2 |
| Full 80×25 redraw | **4.8 ms** | 62 ms | 9.5 ms |
| Scroll one line | **0.19 ms** + `VSCROLL` | 2.5 ms (full-screen) or ~350 ms (windowed, H5) | 0.38 ms |
| At 115.2 kbaud | **2.7 % CPU** | 36 % | 5 % |
| Colour | **one fg/bg pair per bank** | per cell, 8bpp, free | code + attribute |
| Rows available | **25 or 30 only** | 25 / 30 / 50 / 60 | — |
| Mixes with graphics | ⛔ **no — the mode is global** | yes | no |
| Mouse pointer | ⛔ **no** (`VG.DBit`: bitmap screens only) | yes | — |
| Font changeable | rebake a bank, ~7.9 ms | per window, free (`Font`) | reload the glyph RAM |

Figures from `graphics.md` §6.4.8 and §7.3. ⚠ §7.3's store rate is measured at **6.00 E
cycles** on the 6809E core in the socket, not the ~5 the table was written for, so the
bitmap rows read about 20 % optimistic.

### 3.1 What 80 columns costs us that it does not cost a CoCo 3

A GIME 80-column text screen (`St.Sty` `$85`) is hardware: a character byte and an
attribute byte per cell, in mapped RAM, scrolled by moving `St.LStrt`. Ours is one of the
two software paths above. The shortfalls, in order of how much they hurt:

1. ⛔ **No fast text above 30 rows.** Cell mode's map address gives the cell row **five
   bits** (`SA17..SA13`, `graphics.md` §6.4.1), so the map ring is 32 cell rows.
   `VMODE` 10 and 11 — 640×400 and 640×480, i.e. **80×50 and 80×60** — cannot be cell
   screens at all. The card's most striking text modes are available only through the
   13-writes-per-cell path. This is **H9**, and `graphics.md` §6.4.6 already prices the
   fix at one bit of `MAPBASE` and 4 KB more map — nominally no packages, but on `vaddr`,
   which has **40/40 fan-in in every block** and has refused one-literal changes.
2. ⚠ **80×30 glitches under fast output.** 30 displayed rows in a 32-row ring leaves two
   spare, so more than two line feeds in one frame show a recycled row until the next
   repaint. 80×25 has seven rows of runway and is comfortable. Same fix, H9.
3. ⛔ **No per-cell colour, and no attribute plane.** A map byte *is* the whole cell, so
   256 codes are 256 (glyph, colour-pair) combinations, not 256 glyphs. `FColor`/`BColor`
   rebuild the entire bank and change the whole screen. `TILEBASE` selects among 32 banks,
   so colour can be **per region** (a display-list `MOVE` at a scanline, §10.3) but never
   per cell. ⭐ **A cheap middle ground nobody has built**: split a bank into two halves of
   128 glyphs in two colour pairs, giving ASCII in two colours at one write per cell —
   enough for a highlighted status line or a selected menu item. See H18 below.
4. ⛔ **No blink.** There is no hardware blink anywhere on the card. `$1F $24`/`$25` can
   only ever be a software timer flipping codes, which costs a write per blinking cell per
   phase. Accepting and not drawing it is the right answer.
5. **Underline is possible and not done.** Unlike blink it costs nothing at run time: bake
   the underlined variants as extra codes, or as a second bank. It costs code points, which
   is the same currency as colour (item 3).
6. ⛔ **No mouse pointer on a cell screen.** `vidptr.asm` composes the arrow into VRAM
   *pixels*; on a cell screen the bytes at the map are codes, so `PtrDraw` refuses
   (`VG.DBit`). **A Multi-Vue-style pointer-driven UI therefore cannot use the fast console
   at all** — it must be a bitmap screen, at 13 writes a cell. A hardware cursor (H1) would
   dissolve this along with everything else it dissolves; short of that, a cell-mode
   pointer can only be a code swap under a 8×8-aligned arrow.
7. **No hardware cursor for the caret either.** On fast text the caret is the code with
   bit 7 flipped, which is free; on a bitmap window it is an XOR of the cell — 64 pixels
   read and 64 written, twice per character, ~1.2 ms (H2).

### 3.2 What 80 columns costs a CoCo 3 that it does not cost us

Worth stating, because the balance is not one-sided:

- **Per-cell 8bpp colour on the bitmap path.** A GIME text cell picks from 8 foreground
  colours and 8 background; ours picks from 256, per cell, with no clash — and the two
  colour writes are 2 of the 13.
- **80×50 and 80×60 exist at all**, on the bitmap path, at 640×400 and 640×480 — and
  scroll with `VSCROLL` when the window owns the screen (512-row ring, 112 or 32 rows of
  runway respectively).
- **Antialiased glyphs are legal** in cell mode: a tile is 8bpp, so a code can be a
  greyscale glyph. Nothing exercises this.
- **The scroll is a register**, both modes, when the window is the whole screen.

### 3.3 The windowing model itself

CoWin allows 32 windows over up to a handful of screens; CoArm keeps 32 window records and
**8 screen records**. Two hardware facts bound what that means here:

- ⛔ **One picture.** The card scans one region of VRAM. A screen that is not displayed
  lives in a DRAM **store** and `Select` copies 128 KB (640×200) or 307 KB (640×480) each
  way at CPU speed, with the display off — **seconds** at 640×480. This is **H4**, and §6.4
  below shows the first two screens need not pay it.
- ⚠ **One palette.** There is one 256-entry LUT. A `Select` recommits the new screen's
  whole palette: 256 entries at a line each in the picture, or all 256 inside one vertical
  blank (512 writes ≈ 1.2 ms against a 1.56 ms blank, `graphics.md` §13.1). Two windows on
  two screens cannot show different palettes at once, which on a CoCo 3 they also cannot —
  this one is not a regression.

---

## 4. The GrfDrv interface: what carries, what cannot

§1 says the renderer cannot be ported. This section is the itemised version: for each thing
GrfDrv provides, what happens here.

| GrfDrv provides | Here | Why |
|---|---|---|
| Screen types 1–4 (2/4/16 colours, 320/640 × 200) | ⚠ **8bpp only** — types map onto `$10`–`$13` with colours 0–15 taken direct and 320-wide types x-doubled (`av-plan` §5.1, *not built*) | the pixel path is chunky 8bpp (§2.1); there is no 1/2/4bpp scan mode and adding one lands on the tightest path |
| Hardware text `$85`/`$86` | `$18`/`$19` fast text, or `$10`–`$13` bitmap text | §3 |
| The window table (`Wt.`) and screen table (`St.`) layouts | equivalents in `defs/armvid.d` | GIME register pairs, `St.LStrt`, `St.BlkOf` have no meaning here |
| 8 KB block allocation for screens and buffers | GP buffers are blocks (`ca_gpb.asm`, up to 48); **screens are VRAM rows plus a DRAM store** | VRAM is not in any map |
| `GetBlk`/`PutBlk` | built, via `WMODE 00` + `VDATA` | ⚠ **the bytes are 8bpp.** A program that `GPLoad`s a CoCo-format image, or interprets what `GetBlk` returned, sees different data |
| GPLoad-format buffers (`$1B $2B` group buf style X Y count …) | built | ⭐ **The format is depth-neutral for 1bpp content** — fonts and masks carry across byte for byte. 2/4bpp image content does not |
| Fonts, group `$C8` (`stdfonts`, `ibmedcfont`, `isolatin1font`) | ⭐ **carry unchanged** — 1bpp 8×8, and span-mask consumes a glyph row as one write | the best fit on the card. `coarmfont.asm` is `stdfonts` set 1 extracted byte for byte |
| Patterns, group `$CD` (`stdpats_2/4/16`) | ⚠ **`stdpats_2` carries** (span-mask, 2 colours). 4- and 16-colour patterns carry CoCo palette *indices*, which mean something else in a 256-entry LUT, and are drawn a pixel at a time (H6) | no span-pattern mode |
| Pointers, group `$CA` (`stdptrs`, `stdmv`) | ⚠ **shapes are 1bpp and carry; only `GCSet` group 0 is implemented**, and the arrow is drawn into VRAM at 7.9 ms a move (H1) | no hardware cursor |
| Scrolling inside GrfDrv | ⭐ `VSCROLL` when the window owns the screen; ⛔ **row-by-row read-and-write otherwise — ~350 ms for a 192-row window** (H5) | no VRAM-to-VRAM copy |
| `LSet` AND/OR/XOR line styles | read-modify-write per pixel (H3) | no logic `WMODE` |
| Overlay windows (`OWSet`/`OWEnd`) | built — saves into blocks through `VDATA` | works because §11 made VRAM readable. ⭐ **Without read-back a windowing OS would need a 128 KB shadow in system RAM**; that argument is what bought the read path |
| `co3hires.sb`: `SS.AScrn`, `SS.DScrn`, `SS.PScrn`, `SS.FScrn`, `SS.ScInf` | ⛔ **nothing** | these hand a program *mapped* screen blocks. `SS.Excl` is the analogue and it hands back the card's base instead. §6.6 |
| `vrn.dr` / `vi` / `ftdd` (title-specific shims) | ⛔ nothing, and nothing should | they exist for three commercial CoCo 3 titles |
| BASIC09 `gfx2` | ⭐ **works unchanged** wherever the escape it emits works | it writes bytes to a path |
| `wcreate` | ⭐ works, once the type numbers are agreed | it writes `DWSet`/`OWSet` |

### 4.1 The honest summary of §4

**Text and 1bpp assets port cleanly; colour bitmap assets and the renderer do not.** Fonts,
masks, pointer shapes, 2-colour patterns and the whole escape vocabulary carry. Anything
that encodes a CoCo 3 *pixel depth* or a CoCo 3 *palette index* needs a converter, and
anything that reads video memory back needs a `VDATA` stream where GrfDrv used a load.

---

## 5. Hardware shortfalls, ranked

Everything here is already in `docs/nitros9-hardware-improvements.md` with a cost model
except the three marked **new**. This is the same list read from the *interface's* side —
what a CoWin or GrfDrv program cannot get — rather than from the driver's.

| | Shortfall | Interface it breaks | Item |
|---|---|---|---|
| 1 | **No hardware cursor** | `GCSet`/`PutGC` at 7.9 ms a move, done only from the idle loop, so the pointer freezes under a busy process; `PtrGuard` on every primitive; **no pointer at all on cell screens** (§3.1 item 6) | H1 |
| 2 | **No VRAM-to-VRAM copy** | window scroll, `Select`, `GetBlk`→`PutBlk` — the whole of GrfDrv's block layer | H4, H5 |
| 3 | **Cell row is five bits** | no 80×50 / 80×60 fast text; 80×30 glitches | H9 |
| 4 | **No logic write modes** | `LSet` AND/OR/XOR, the bitmap text caret, XOR rubber-banding | H2, H3 |
| 5 | **No span-pattern mode** | `PSet` with more than two colours, patterned `Bar` and `FFill` | H6 |
| 6 | **No per-cell attributes** | per-character colour, underline and blink on a fast-text screen | ⭐ **new: H18** |
| 7 | **No `BORDER`** | `Border` `$34`, permanently | `graphics.md` §9.3 — not on the list, and should not be |
| 8 | **No 1/2/4bpp scan mode** | CoCo 3 screen types 1–4 render at 4× or 8× the memory and cannot share a CoCo image byte for byte | ⭐ **new: H19**, and ⛔ **not recommended** — it lands on the index → LUT path with 11.7 ns of margin (§6.1), for compatibility a converter buys more cheaply |
| 9 | **A display list cannot move `VSCROLL`** | no mid-frame vertical split; a status line under a scrolling playfield is a redraw | H17 |
| 10 | **`WADV` has no 128-byte stride** | a map column is a `WPTR` load per cell | H16, not recommended |

### 5.1 ⭐ One correction to H4's cost, found while writing this

`docs/nitros9-hardware-improvements.md` rank 7 prices "more VRAM with a selectable scan
start" at **≈ +2–3 packages** (another pair of `AS6C8016`s and a page select).
`graphics.md` §14.2.2 says the packages are **already fitted**: each `AS6C8016` is 512K×16
with two address pins tied off, so the two parts on the card hold **2 MB** and address
512 KB. *"Precisely the 2 MB upgrade path the moment the pointers widen to 21 bits."*

So H4's cost is **not SRAM**. It is two more bits on the scan address and on `WPTR`, both of
which land on `vaddr` — the part with 40/40 fan-in in every block, where the item's real
risk already was. The estimate should say so: **0 packages of memory, and a `vaddr`
re-partition (most likely the fourth CPLD) for the pointers.** That makes H4 cheaper than
it reads and does not make it easy.

---

## 6. Extensions for features the CoCo 3 does not have

CoWin's vocabulary has no way to say most of what this card does. The extension block
`$60`–`$7F` (unused by `cowin.asm`) and the SetStat block `$D0`–`$EF` are where it goes;
`video-console.md` is the frozen record of what P3 built.

### 6.1 Built and frozen

| Feature | Interface |
|---|---|
| RGB565, 256 entries | `$60 Pal565`, `$61 PalRange`; `Palette` `$31` keeps CoCo 6-bit and converts (`C6To565`); `FColor`/`BColor` already take a **full byte**, so 0–15 stays CoCo-compatible and 16–255 is the extension |
| 2-colour patterns, polygons, masks, images, icons | `$62`–`$68` |
| An ANSI/VT100 terminal on a window | `$69 AnsiSw` |
| Per-line `HSCROLL` and palette (display lists) | `SS.Raster` `$DA`, `SS.RastOff` `$DB` |
| Tile playfields | types `$1C`/`$1D`, `SS.TileLd` `$DC`, `SS.MapWr` `$DD`, `SS.TBank` `$DE` |
| Exclusive screens, frame sync, batched VBL commits | `SS.Excl` `$D4`, `SS.FrmWait` `$D9`, `SS.FrmSig` `$D8`, `SS.Batch` `$D7`, `libvid` |

### 6.2 Specified, not built — and what each one is for

`SS.VInfo` `$D0`, `SS.Pal565` `$D1`, `SS.VRead` `$D2`, `SS.VWrite` `$D3`, `SS.Scroll` `$D5`,
`SS.Flip` `$D6`, `SS.LineSig` `$DF`; and `libvid`'s text, icons, polygons and images.

⭐ **`SS.VInfo` should be built first and is nearly free.** It is the call a *portable*
program uses to discover that it is not on a CoCo 3: modes, VRAM size, current `VMODE`,
tick rate ×1000. Without it every program that wants 640×480 or 256 colours has to assume
the machine, which is exactly what makes CoCo software unportable in the first place.

### 6.3 ⛔ 640×400 and 640×480 are specified and have never been a screen

`DWSet` types `$12` and `$13` are in `av-plan` §5.1. `video-console.md`'s built list is
`$10`, `$11` (bitmap 200/240), `$18`, `$19` (fast text 25/30), `$1C`, `$1D` (tile). **The
two tallest modes — the ones nothing in the period had — are the two with no screen type
behind them.** What they need:

1. **Bitmap text at 80×50 and 80×60**, at 13 writes a cell (cell mode cannot reach them,
   §3.1 item 1), with `VSCROLL` scrolling when the window owns the screen. 480 rows in the
   512-row ring leaves 32 rows — four text rows — of runway, which is enough.
2. **The tick.** 640×480 is the 59.940 Hz family; `clock.asm` already takes the length from
   `VMODE0` per tick, so this is free (`README.md`, `vmodetst`).
3. ⚠ **`Select` into or out of them is 307 KB each way** — several seconds with the display
   off (H4). §6.4 is the way out for the common case.
4. ⚠ **The palette no longer fits comfortably in one blank.** A commit written in `VBLANK`
   runs at once, so a full 256-entry load is 512 writes ≈ 1.2 ms (`graphics.md` §13.1) —
   against **1.56 ms** of blank in the 449-line family (49 lines), but only **1.43 ms** in
   the 525-line one (45 lines). At 640×480 that is 84 % of the blank with the VBL service's
   own work (up to 183 µs, measured) inside it. `VcPal` should be prepared to split a full
   palette across two blanks in the 525-line family. Nothing has hit this because nothing
   runs there, and 640×240 (`$11`, also 525 lines) has the same margin today.

### 6.4 ⭐ `Select` between the first two screens should be a register write

**The ring is 512 rows and a 640×200 screen uses 200 of them.** `VSCROLL` is nine bits
(`+$01`/`+$02`), so rows 0–199 and rows 256–455 are both scannable and `Select` between two
200-line screens is *one register write in the VBL batch* — not 128 KB each way. Two
240-line screens also fit (480 ≤ 512). `av-plan` §4 already names this for double buffering
(`SS.Flip` = "`VSCROLL` to row 256 in the batch"); it applies to `Select` as well, and
`Select` is where the seconds are.

| Screens | Second page? |
|---|---|
| two × 640×200 | ⭐ yes — 200 + 200 of 512, and 112 rows spare |
| two × 640×240 | ⭐ yes — exactly 480 of 512 |
| any 640×400 or 640×480 | ⛔ no — one page until H4 |
| three or more | ⛔ no — the third pays the copy |

⚠ **Two things it costs.** The off-screen page's columns 640–1023 are the horizontal
scroll margin of *both* pages, so an `HSCROLL` list on one page can show the other's
columns; and cell mode's map ring and tile banks live in the same 512 KB, so a fast-text
screen and two bitmap pages have to be placed against each other. Neither is hard; both
need `armvid.d` to grow a VRAM allocator, which today is a fixed layout (`TL.*`).

**Recommend**: build `SS.Flip` and page-aware `Select` together, for the 200- and 240-line
types only, and leave the DRAM store as the fallback for screen three and for 400/480.

### 6.5 The sprite `WMODE` is under-used

`WMODE 11` (`graphics.md` §7.4) retires eight bytes and suppresses the writes whose mask
bit is 0 — a transparent blit at span-mask speed. `av-plan` §4 assigns it to the pointer,
the text caret and masked icons. `$64 PutMask` uses it. ⚠ **The pointer does not**: it is a
`VDATA` save-behind and compose (H1). Since save-behind is needed anyway to *restore* the
pixels, sprite mode saves only the compose half — worth measuring before assuming it helps.

### 6.6 `SS.AScrn` and friends deserve a shim, not a port

CoCo 3 games take a raw screen with `SS.AScrn`/`SS.DScrn`/`SS.PScrn`/`SS.FScrn`/`SS.ScInf`
(`co3hires.sb`) and then draw into mapped blocks. **The mapped blocks cannot exist here.**
The honest shim is: `SS.AScrn` allocates a DRAM buffer of the screen's size and returns its
block, `SS.DScrn` pushes it to VRAM (a `VDATA` stream, 128 KB, ~1.3 s at VidCore's measured
rate — or much less with a 6309 `TFM` path), `SS.ScInf` answers from the buffer,
`SS.FScrn` frees it. That makes a *slow* port possible instead of an impossible one, and it
is honest about which it is. Low priority; no program here needs it.


### 6.7 ⭐ ANSI colour — how the period did it, and what we changed (2026-09-16)

**On a period PC, ANSI art was never *rendered*. It was *stored*.** CGA, EGA and
VGA text modes hold **two bytes per cell** at `B800:0000` — a character code and
an **attribute byte**, four bits of foreground and four of background (the top
background bit being blink unless the blink-enable bit is cleared, which is
exactly the "iCE colors" trick BBS artists used to get sixteen backgrounds). The
CRTC and the character generator compose the glyph at scan time from a ROM or
loadable RAM font, at **zero CPU cost per frame**. `ANSI.SYS` and every BBS
terminal parsed the escapes and wrote char/attribute pairs, so a full 80 × 25
screen is **4,000 byte writes and colour is free**, because it rides in a byte
that is written anyway.

Three things follow, and they explain the whole shape of classic ANSI art:

- **16 colours**, because the attribute byte has four bits of foreground.
- **80 × 25 and 80 × 50**, because those are the text modes.
- **The CP437 half-blocks** (`▀ ▄ █ ░ ▒ ▓`), which are how artists got a
  160 × 100 two-colours-per-cell "bitmap" out of a text mode.

⚠ **`SGR 38;5;n` is not period.** The 256-colour form is an xterm extension from
long after; no hardware of the era had it, and on any period machine you would
have been in a bitmap mode to do it. So the two cases want opposite things from
this card:

| | Wants | We have |
|---|---|---|
| **16-colour ANSI art** | an **attribute plane** — a colour byte beside the code | ⛔ **no**: the map byte is the whole cell (§3.1 item 3, **H18**). ⭐ **Costed 2026-09-16**: `graphics.md` §6.4.10 |
| **256-colour ANSI** | a **bitmap** and sticky fg/bg registers | ⭐ **yes**: `WFG`/`WBG` are sticky registers and the driver elides unchanged writes |

| | CGA/EGA/VGA text | our cell mode | our bitmap text |
|---|---|---|---|
| VRAM bytes a cell | 2 — code + attribute | **1** — the code | 64 — 8bpp pixels |
| CPU writes a cell | 2 | **1** | 11 same-colour, 13 on a change |
| Colours a cell | 16 fg, 8 or 16 bg | one pair per **bank** | **256 fg, 256 bg** |
| A colour change costs | nothing — it is in the byte | a bank rebuild, ~6 ms | **two register writes, ~5.7 µs** |

⭐ **Our cell mode is cheaper per cell than a period text card** — one write
against two — precisely *because* it dropped the attribute byte, and that is the
same trade that makes 16-colour ANSI art impossible on it. Our bitmap text has
more colour than any period card had, at five to six times the writes.

#### What was wrong, and what is built

⛔ **Three defects, all in software, found 2026-09-16.** `DoAnsiSw` loads no
palette of its own, so ANSI colour numbers indexed straight into CoWin's
palette order — *white, blue, black, green, red, yellow, magenta, cyan*. That is
not ANSI's order, so **every ANSI colour was wrong**: `SGR 31` ("red") gave blue,
`SGR 34` ("blue") gave red, and the SGR 0 default of "7 on 0" rendered **cyan on
white**. `AnCol` added 8 for bold, and `PalDef` filled 8–15 with a *duplicate* of
0–7, so **bold was invisible**. And `AnSGR` implemented only `0 1 22 30-37 39
40-47 49` — the card's 256-entry palette was unreachable from the ANSI path at
all, though `FColor` has always taken a full byte.

| Now | |
|---|---|
| `PalDef` (`ca_scr.asm`) | **0–15 unchanged** — CoWin programs index these by number and `tools/vtmodel.py` encodes the same order. **16–231 is xterm-256's 6 × 6 × 6 cube, 232–255 its 24 greys**, so `38;5;n` is a *direct* palette index for `n ≥ 16` |
| `AnsiPal` (`ca_ext.asm`) | sixteen bytes mapping ANSI 0–15 onto **the cube's own nearest cells** (`16 160 40 184 21 165 45 254`, then the bright eight). ⭐ **It spends no palette entry**, and it fixes the order and makes bold visible in one table |
| `AnMap` | 0–15 through `AnsiPal`; **16–255 pass through as a palette index** |
| `An256` | `38;5;n` and `48;5;n`, pre-scanned before `AnSGR`'s loop and blanked to 255, which no other branch claims — so the loop runs unchanged |
| `AnSGR` | plus aixterm's `90–97` and `100–107` |

⭐ **Checked.** `run-vid.sh`'s `p3` run drives `91`, `102`, `38;5;208`,
`48;5;19`, `38;5;226`, `38;5;244` and `38;5;9` at the window and is **pixel-exact
against `tools/vgmodel.py` across 90 frames** — the model implements `AnsiPal`,
`An256` and the bright ranges from the protocol, not from the driver's code, so
the two agreeing is evidence rather than tautology. **54 claims, 0 failed.**

⚠ **Two limits, both stated rather than hidden.** `WT.AnP` is four parameters
deep, so **one** 256-colour form fits a CSI; a run that sets foreground *and*
background needs two. And `38;2;r;g;b` (truecolor) is not implemented — it would
have to quantise to the cube, and nothing has asked for it.

---

## 7. Leveraging Wildbits — the font system first

Wildbits is the most actively developed non-CoCo target in the tree (INTRODUCTION §10), and
this port already takes three things from it: the **`sc16550` UART driver** (`term_16550`),
the **set-2 scan-code tables** (`KbdArm`), and the general shape of a modern non-CoCo
Level 2 port. The font system is the next one and it is the biggest single win available.

### 7.1 What Wildbits' font system is

| Piece | What it is |
|---|---|
| **The file format** | a **data module** (`$87CD`), execution offset at header `$09`–`$0A` pointing at **2,048 bytes = 256 glyphs × 8 rows, 1bpp, MSB leftmost**. `level1/wildbits/sys/fonts/*.asm` |
| **`SS.FntLoadM` `$C0`** | load a font from a linked module |
| **`SS.FntLoadF` `$C1`** | ⭐ load a font **from a file path**, streaming the 2 KB straight into the hardware bank without linking the module — the memory-cheap path (`vtio.asm` `SSFntLoadF`) |
| **`SS.FntChar` `$C2`** | get or set **one glyph's 8 bytes** in a bank |
| **`ESC $1B $62`/`$63`** | select bank 0 or bank 1 on the console (`wild.asm` `FNSet`) |
| **`wild`'s `FNLoad`/`FNChar`/`FNSet`** | the BASIC09 wrappers over the three SetStats |
| **28 fonts** | Commodore, MSX, Apple II-ish, Phoenix EGA, gothic, uncial, emoji, banner faces, … |

### 7.2 Why it fits this card unusually well

- ⭐ **2 KB of 8×8 1bpp is exactly what the span writer eats.** A glyph row *is* one
  span-mask write (`graphics.md` §6.1 reason 2). Baking a font into a tile bank is 2,048
  span-mask writes, **~7.9 ms, once** — the number `graphics.md` §6.4.8 already quotes and
  `video-console.md` already pays at `DWSet`.
- ⭐ **`SS.FntChar` is ~30 µs here**: one glyph is 8 span-mask writes into one tile.
  Redefining characters at run time is genuinely cheap, which it is not on most targets.
- ⭐ **We have 32 banks where Wildbits has 2.** `TILEBASE` is five bits, so up to 32
  resident (font × colour-pair) banks, switched by one register write — or by a display-list
  `MOVE` at a scanline, which makes the font **per region**.
- ⭐ **`SS.FntLoadF`'s file-streaming design is the right one here for the same reason it is
  there**: CoArm runs in a task of its own with two blocks (H13), and not linking a 2 KB
  module matters.

### 7.3 What to adopt, and the one collision

**Adopt the three SetStat codes verbatim — `$C0`, `$C1`, `$C2` — with Wildbits' semantics
and its file format.** `av-plan` §5.3 chose `$D0`–`$EF` specifically to *avoid* Wildbits'
`$C0`–`$C4`; that was right for calls that have no Wildbits equivalent and wrong for these
three, which have an exact one. A font file, a `wild` script and a program that calls
`I$SetStt` with `$C1` should work on both machines unchanged.

| | Our action |
|---|---|
| `SS.FntLoadM` `$C0` | load a linked font module into a bank. On a **fast-text screen**: rebake the bank (~7.9 ms). On a **bitmap window**: it is the same thing `Font` `$3A` does with a GP buffer, so make `$C0`/`$C1` fill a GP buffer in the font group and select it |
| `SS.FntLoadF` `$C1` | the same, streamed from a path. ⚠ The 2 KB must be read into a CoArm-visible block; CoArm makes no system calls, so this is an **ArmIO** call that yields (`VG.CWait`) exactly as allocation does |
| `SS.FntChar` `$C2` | get/set one glyph — 8 span-mask writes on a cell screen, a GP-buffer patch on a bitmap one |
| ⛔ **`ESC $62`/`$63`** | **collides.** Wildbits selects font bank 0/1 there; we already use `$62 PatDef` and `$63 PatBar`, frozen by P3 and exercised by `vgp3`. **Do not move ours.** Add **`$6A FntBank <n>`** for bank select and document the collision here and in `video-console.md`. A Wildbits program that emits `$1B $62` on this machine defines a pattern — harmless, wrong, and silent, which is the worst kind; ⚠ worth a line in the port's README |
| **The 28 fonts** | copy into `/DD/SYS/FONTS` unchanged. ⭐ **This is the whole point**: it is the difference between a console with one font and a console with twenty-nine, for the cost of a directory |
| **`wild`'s `FNLoad`/`FNChar`/`FNSet`** | the BASIC09 surface comes free once the SetStats match. Whether to port `wild` itself is a separate question (§7.5) |

### 7.4 ⭐ And the backgrounds are a direct fit

`level1/wildbits/sys/backgrounds/` holds 12 paired `pixmap*`/`clut*` modules: an **8bpp
bitmap** and a **256-entry CLUT as B,G,R,A**. This card is 8bpp with a 256-entry RGB565 LUT.
The conversion is `(R>>3, G>>2, B>>3)` packed into two bytes — a build-time tool, not run-time
code — and the pixmap goes to VRAM byte for byte through `SS.VWrite` (§6.2, unbuilt).

That makes twelve ready-made background images the desktop can use, and it makes the
**pixmap/clut pair the natural interchange format for images on this machine** — closer to
our hardware than anything in the CoCo 3 tree, where every image is 1/2/4bpp and palette-
indexed into 16 entries.

### 7.5 What else of Wildbits is worth taking, and what is not

| | |
|---|---|
| ⭐ **`vtio_dma_scroll.asm`'s *structure*** | its scroll goes through the video core's block move. We have no block move (H5), so the code does not carry — but the shape (a console driver with a pluggable scroll back-end) is the shape `ca_bmtx.asm` will want when H5 or H4 lands |
| ⭐ **`defs/wildbits.d`'s SetStat discipline** | custom calls `org`'d at `$C0` and given names, so a third party can see what is taken. `defs/arm6309.d` does the same at `$D0`; say in both places which block is whose |
| **`SS.SOLIRQ` `$C3`** | Wildbits' raster/line interrupt. `av-plan` reserves `SS.LineSig` `$DF` for ours (the CPU-module line compare, `graphics.md` §12.2). ⚠ **Prefer `$C3` and Wildbits' semantics** if they fit, for the same reason as the fonts |
| **VICKY's tilemap and sprite engines** | `wild`'s `TS*`/`TM*`/`SP*` calls. Our tile interface is `SS.TileLd`/`SS.MapWr`/`SS.TBank` and is already built and frozen; **we have no sprites at all** (H15). Not worth retrofitting Wildbits' names onto a different mechanism |
| **`wild` itself** | 3,000 lines of BASIC09 glue over a machine we do not have. Take the *function list* as a checklist of what a complete interface looks like; port the calls that map |
| ⛔ **Level 1 VTIO's console model** | Wildbits' console is hardware text: a character block at `$C2` and an **attribute block at `$C3`**, both mapped, so a cell is a store and a scroll is a block move. Ours is a map behind `WPTR` with no attribute plane (§3.1 item 3). The rendering does not carry; the escape/control-code layer we already have from CoWin |

---

## 8. Recommended order of work

Ordered by value per unit of work, software first — **every item in 1–5 is software only**
and needs no card change.

| | Item | Why here |
|---|---|---|
| **1** | ⭐ **Adopt the Wildbits font system** (§7.3): `$C0`/`$C1`/`$C2`, the file format, the 28 fonts, `$6A FntBank`. Fixes `Font` `$3A` being silently ineffective on fast-text screens (§2.1) | largest visible gain for the least work, and it closes a *silent* gap |
| **2** | ⭐ **`ScaleSw` `$35`** (§2.2) | the one no-op that breaks ported CoCo 3 programs rather than merely disappointing them |
| **3** | **Screen types `$12`/`$13`** — 640×400 and 640×480 bitmap, 80×50 / 80×60 text (§6.3), with `VcPal`'s two-blank split for the 525-line family | the machine's headline modes have no screen behind them |
| **4** | **`SS.VInfo` `$D0`** (§6.2) | a portable program cannot ask what machine it is on |
| **5** | ⭐ **Page-aware `Select` + `SS.Flip`** for 200/240-line screens (§6.4) | turns a 128 KB copy into a register write, with no hardware change |
| **6** | **`SS.VRead`/`SS.VWrite` `$D2`/`$D3`**, then the Wildbits background converter (§7.4) | unlocks twelve images and the interchange format |
| **7** | **H9, the six-bit cell row** — the first *card* item, and the one the console feels | 80×50/80×60 fast text; ends the 80×30 glitch. ⚠ on `vaddr` (§5) |
| **8** | **H1, the hardware cursor** | the pointer, the bitmap caret, and cell-screen pointers all at once — `docs/nitros9-hardware-improvements.md` already ranks it 5 |
| **9** | **H18's software half: two colour pairs per bank** (§3.1 item 3), at 128 glyphs each. The hardware half — a real attribute plane — is a card revision | per-region colour on the fast console, for no silicon |
| **10** | `SS.AScrn` shim (§6.6), `DWProtSw`, `PropSw`, underline-by-glyph | completeness |

---

## 9. Open questions

1. ⚠ **Does `SS.FntLoadF` fit CoArm's no-system-calls rule cheaply?** CoArm yields to ArmIO
   for anything that sleeps or allocates (`video-console.md`). A font load is an `I$Open`,
   an `I$Seek`, a 2 KB `I$Read` and a bank rebake. The read belongs in ArmIO and the bake
   in CoArm, which means a new `VG.CWait` reason. Cheap, but it is a protocol change.
2. **Is 128 glyphs × 2 colour pairs (H18) the right split, or 64 × 4?** A menu wants two;
   a BBS ANSI screen wants more than four. Nothing has measured what a real client needs.
3. ⚠ **Does the 6309 `TFM` `VDATA` path actually give ~1.6 µs a byte?** Every estimate that
   depends on it — `Select`, `SS.VWrite`, the pointer, `SS.DScrn` — moves by ~6× on the
   answer, and **neither the host emulator's core nor `machine_tb`'s `mc6809e` executes
   6309 opcodes**, so it cannot be measured here as things stand. This is the largest
   unmeasured number in the video software.
4. **Should CoCo 3 screen types 1–4 map at all** (`av-plan` §5.1's "later phase"), or should
   a converter be the answer? §5 item 8 argues the converter; nothing has tried a real
   program either way.
5. ⚠ **`$6A FntBank` vs. re-using Wildbits' `$62`/`$63` and moving `PatDef`/`PatBar`.** P3
   froze `$62`/`$63` and `vgp3` exercises them, so this document recommends `$6A`. If
   binary compatibility with Wildbits console programs ever matters more than our own
   frozen numbers, that is the decision to revisit — and it has to be revisited before
   anything else takes `$6A`.
