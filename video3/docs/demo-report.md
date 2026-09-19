# video3 — the NitrOS-9 demo, and what it took

**2026-09-16, overnight.** The short version: **it runs.** NitrOS-9 boots to an
80 × 60 CP437 console on video3, moves to a 640 × 480 desktop whose file-manager panes
are filled by the real `dir` command, drags a window with the card's copy engine, shows
CP437 ANSI art through the attribute plane, and plays the game on an accelerating
scroll. The video is `software/nitros9/video/video3-demo.mp4`; §8 has what works and
what does not.

⭐ **Two answers to the brief up front.** There was no GrfDrv to replace — §0. And the
Verilator stage found **four real defects in `v3dot` that the fitter could not** — §6.

The brief: boot NitrOS-9 in 80×60 text on video3, switch to 640×480 bitmap, and build
the old `software/demo` show out of **real NitrOS-9 commands** — desktop, two-pane
file manager with a copyrect window drag, the paint program (no wave), an ANSI BBS
in 80×25 with CP437, and the Zelda game with a scroll that accelerates 1→16 px a
frame. Then a web MP4.

---

## 0. The first finding, and it saves the largest piece of work

⭐ **There is no GrfDrv in this port, and there has not been one since the console
went in.** `level2/arm6309/modules/armio.asm:9` says it outright — *"GrfDrv
(level1/modules/scf.asm), and there is no GrfDrv here."*

The brief proposed writing a new GrfDrv from scratch because the stock one assumes
flat 64 K VRAM and this card has a pointer window. **That is the right call and it
was already taken.** What exists instead is **CoArm**, a from-scratch console/graphics
server living in task 1, reached the way CoCo 3's CoWin reaches GrfDrv:

| module | lines | what it is |
|---|---|---|
| `coarm.asm` | 700 | the server: entry, dispatch, the resume stack |
| `armio.asm` | 724 | the SCF-side driver — CoWin's half, and `CoCall` |
| `ca_scr.asm` | 1068 | screens, windows, palettes |
| `ca_draw.asm` | 1074 | the drawing primitives |
| `ca_ext.asm` | 1093 | the escape protocol, ANSI/SGR |
| `ca_bmtx.asm` | 669 | text on a bitmap window |
| `ca_gpb.asm` | 591 | get/put buffers |
| `ca_text.asm`, `ca_row.asm`, `ca_tile.asm`, `ca_ptr.asm`, `ca_list.asm` | 1,417 | cell text, row ops, tiles, the pointer, the display list |
| `vidcore.asm`, `vidptr.asm`, `vidsvc.asm`, `vidxcl.asm`, `libvid.asm` | 1,555 | the card itself: the pointer window, the VBL service, exclusive mode |

**~10,500 lines, already pointer-window native.** So tonight's job is not to write a
GrfDrv. It is to **retarget that stack from `video/` to `video3/`**, and to add the
two things video3 has that `video/` does not: the copy engine and the sprite.

## 1. How far apart the two cards actually are

`defs/armvid.d` holds `video/`'s register map and `video3/docs/plan.md` §10 holds
video3's. ⭐ **The first eleven registers are identical** — `CTRL`, `VSCROLL`,
`HSCROLL`, `SPANLEN`, `WFG`, `WBG`, `WPTR` — which is most of the span writer's
working set. What moved:

| | `video/` | video3 | |
|---|---|---|---|
| `WADV` | `$14` | `$0B` | |
| `VDATA` | `$15` | `$0C` | the hot register — every VRAM byte |
| `VSTAT` | `$13` | `$0D` | |
| `PIDX` | `$10` | `$0E`–`$0F` | ⭐ **16 bits now** — the attribute plane |
| `PDATL`/`PDATH` | `$11`/`$12` | `$10`/`$11` | |
| `TILEBASE` | `$17` | `$18` | |
| `MAPBASE` | `$19` | `$19` | unchanged |
| `BCTRL` (list GO) | `$0E` | — | ⛔ **gone; no display list engine** |
| `CPTR`/`CWIDTH`/`CHEIGHT`/`CCTRL` | — | `$12`–`$17` | ⭐ new: the copy engine |
| `SPRX`/`SPRY`/`SPRH`/`SPRIDX`/`SPRDAT` | — | `$1A`–`$1E` | ⭐ new: the mouse sprite |

And `CTRL` is re-laid-out: `video/` has b5 `CELL` and b4–3 `WMODE`; video3 has
**b3–2 `MODE`** (00 bitmap, 01 character, 10 tile) and b5–4 `WMODE`.

**So the port is a register-map change plus two new features, not a rewrite.**

---

## 2. Character mode, and the eight things that broke on the way

**Result: NitrOS-9 boots to a shell on an 80 × 60 CP437 console on video3.** That is
640 × 480 character mode, which `video/` cannot do at all — its cell mode stops at
80 × 30. The screen scrolls by **copyrect**, one rectangle of 160 bytes × 59 rows.

The port itself was small, as §1 predicted: `defs/armvid.d` grew a video3 register map
behind `-DV3=1`, and `software/nitros9/mkrom.sh` grew a `V3=1` flavour. What cost the
evening was everything downstream of the map. In the order they were found:

| # | what | where it was |
|---|---|---|
| 1 | `VSTAT.LRun` defined twice once `arm6309.d` also had to know the card | defs |
| 2 | `vidsvc.asm` armed a display list through `VR.BCTRL`, which **is `CPTR`'s low byte on video3** | driver |
| 3 | ⛔ **the model exempted `$FF75` from the under-a-span rule** — `video/`'s `VDATA`. video3's is `$FF6C`, so every font stream was a violation | **emulator** |
| 4 | ⛔ **the model read WMODE from b4–3** — video3 has it at b5–4 (b3–2 became `MODE`), so span-**mask** ran as span-**solid** and painted the font as 2,048 solid pixels | **emulator** |
| 5 | `VcPal` writes an 8-bit `PIDX`; video3's is 16, so the bitmap palette landed in whatever `ATTR` bank was last used | driver |
| 6 | `IsText` tested `$18`/`$19` only, so an 80 × 60 screen **fell through to the bitmap arm of `Select`** and the card showed its own map as pixels | driver |
| 7 | `TX3.TBank * $4000` is `$10000` and **does not fit in X** — the font was written to address 0, on top of the map | driver |
| 8 | ⛔ the font went out as one 2,048-byte stream, but **`WPTR` wraps inside its 1024-byte row** — all sixteen glyph rows landed on top of each other. 163 bytes of font in a 16 K bank | driver |

⚠ **Two of those eight are in the emulator, not the driver** (#3 and #4), and both are the
same shape: a constant that encodes *which card this is*, written when there was only one.
Neither is visible as an error — #3 prints FAIL lines for correct code, and #4 silently
turns one span mode into another. They are worth knowing about because the rest of the
model is full of the same kind of constant.

### 2.1 What the attribute plane turned out to be

⭐ **`ATTR` is a handle to one of 256 (fg, bg) pairs**, each colour any of the screen's
256-entry palette (§9.2). The first version loaded the VGA crossing — b7–4 background,
b3–0 foreground — and that is still where the sixteen ANSI colours' pairs land, so CP437
art costs the allocator nothing.

Two consequences fell out that were not in the plan:

- **The font is 1bpp and colourless, so there are no inverse glyphs.** `video/` bakes the
  screen's colours into the tile bank and spends half its 256 codes on inverses; video3
  spends the same 2,048 writes on **256 real CP437 characters**, and reverse video is an
  `ATTR`, not a glyph. That is what makes the box-drawing and shade cells at `$B0`–`$DF`
  available at all.
- **The text cursor is a colour swap, not a glyph inversion** — so it works over ANSI art.

### 2.2 ⛔ CoArm does not fit, and the font is why

CP437 is 2 K where `video/`'s font is 1 K, and **CoArm is mapped in two 8 K blocks with no
third to be had**: eight slots, of which block 0, the kernel and the two block windows take
four, and the globals measure over 8 K so the data side cannot give one up either.

The font now lives in **`vidfnt3.asm`, inside ArmIO**, which is in the system map and has
the room; CoArm asks for it by yielding `CW.Font`, the same way it asks for memory. That
left CoArm at **15,312 of 16,384 bytes** — 1,072 spare — where shaving bytes out of
`ca_v3txt.asm` had got it to 16,381, three bytes spare, which is not a place to build from.
Dropping `ca_list.asm` under `-DV3=1` (video3 has no display list, so `SS.Raster` returns
`E$UnkSvc`) was worth 406 of those bytes.

### 2.3 The pointer is now free

⭐ video3 composites the mouse pointer in the card, so `PtrGuard` — the routine that takes
the pointer off the screen before CoArm draws anywhere near it, and puts it back — is
**`rts` under `-DV3=1`**. The save-restore-compose machinery that `video/` needs for every
drawing primitive simply has no job. ⚠ The sprite is bitmap-mode only (plan §7), so a
character screen still has no pointer.

---

## 3. The bitmap side needed nothing

⭐ **The entire bitmap drawing stack ran on video3 unchanged, first try** — text
styles, lines, circles, ellipses, arcs, fills, patterns, GP buffers, get/put blocks,
overlays with save-behind, transparency. That is `ca_draw.asm`, `ca_bmtx.asm`,
`ca_gpb.asm` and `ca_row.asm`, ~2,900 lines, and not one of them needed a conditional.

The reason is §1's: those modules reach the card only through `vidcore.asm`, and
`vidcore` reaches it only through the `VR.*` names. Change the names and the stack
moves cards. **That seam is the single most valuable thing in the existing port** and
it was not designed for this — it was designed to keep `graphics.md`'s rules in one
place.

## 4. What the demo is made of

The brief asked for the old `software/demo` show rebuilt out of **real NitrOS-9
commands**. What that turned into:

| scene | how it is driven |
|---|---|
| the 80 × 60 console | `iniz w1`, then a `shell` on it, typed at over PS/2 |
| the desktop | `copy /dd/sys/v3desk /w3` — the chrome is a stream of CoWin escapes |
| **the file manager** | ⭐ `display 1b 25 …` sets a pane as the window's `CWArea`, then **`dir /dd >/w3`** — the real `dir` command's output lands in the pane |
| the window drag | `v3drag >/w3`, a command that calls **`SS.Copy`** once a step |
| the pointer | the PS/2 mouse, on the card's sprite |
| paint | `copy /dd/sys/v3paint /w4` |
| the BBS | `copy /dd/sys/v3bbs /w2` — CP437 bytes and ANSI SGR, parsed by `ca_ext.asm` |
| the game | `overworld >/w3`, on an exclusive tile screen |

**Only one new program was written** (`v3drag`, 180 lines); everything else is
`copy`, `dir`, `display` and `shell`. The artwork is generated by
`software/nitros9/tools/v3show.py` as escape streams, which is how a CoCo 3 GUI
client worked — the escape protocol *is* the graphics API.

### 4.1 ⭐ SS.Copy, and the answer to plan §6.2 that software can give

`vidcpy3.asm` adds **`SS.Copy`**: a rectangle of the displayed bitmap screen, moved
by the card. `v3drag` calls it once a step and paints the four-pixel strip the window
vacates; the CPU touches no pixel of the window itself.

⛔ **The engine copies ascending only** — plan §6.2 rejected the direction bits
because `v3ptr` does not fit with them — so a four-pixel step across a 240-pixel
window overlaps itself and would smear. The driver **stages through off-screen VRAM**:
source → the spare rows above the visible screen → destination. Two ascending copies,
neither overlapping, both in hardware. ⭐ **So the direction bits are not needed in
silicon at all**; the same correctness is available for the cost of a second copy, and
the client cannot tell which path it got.

⛔ **And chunking re-creates the very overlap it exists to avoid.** A 640 × 480 screen
leaves only 32 spare rows, so a 112-row window stages in four passes — and for a
downward move, pass 2's *source* rows are pass 1's *destination* rows, already
overwritten. The chunks now run bottom-up when the destination is below the source and
top-down when above: a memmove's rule, one chunk at a time instead of one byte. The
first version smeared the window's text, which looked exactly like the hardware
limitation rather than like my loop.

### 4.2 Three defects in wiring one new SetStt call

| | |
|---|---|
| ⛔ the dispatch was spliced **after an `rts`** | `s4@` is a branch target, not a fall-through. The test was unreachable and the call answered `E$UnkSvc` from CoArm at the far end of the chain — an error from the right family, at the wrong distance |
| ⛔ **a caller's buffer is not readable from a driver** | A SetStt runs in the system map; the caller's `X` is in `PD.RGS`/`R$X`, not in the driver's `X`. Reading it directly assembles, links, boots, and copies whatever the system map holds at that address. `FromCallerX` is what SS.Raster already used |
| ⚠ **lwasm ends a local-label scope at every non-local definition** | Putting `CpTdLoop` in the middle of a routine put its own `ok@` in a different scope from the branches above it — *"Undefined symbol ok@"* for a label three lines below. Cross-scope targets are global labels now |

## 5. The game's transitions now accelerate

The camera path is **pre-recorded** by `software/demo/tools/mkgame.py`, not computed
in the game, so the brief's 1 → 16 px a frame belongs there. `carry()` took a constant
step and a frame count (4 px × 160 frames for a screen); it now takes a *distance* and
runs a ramp: 1, 2, 3 … 16, cruise, and ease back to 1.

| transition | was | now |
|---|---|---|
| a screen east or west, 640 px | 4 px × 160 frames | **1 → 16 → 1 px, 55 frames** |
| a screen north or south, 192 px | 2 px × 96 frames | 1 → 13 → 1 px, 27 frames |

⚠ The vertical peak is 13, not 16: a 192-pixel move cannot reach 16 and still ease
back, so `ramp()` drops the peak until the ramp fits. **16 px a frame at 70.086 Hz is
1,120 px/s**, and the card does not care — `HSCROLL` is a register — but the game's own
per-frame work doubles, because two tile columns scroll into view a frame instead of
one. The catch-up loop was already a `while` and not a fixed count, so it absorbs it.

---

## 6. ⭐ Verilator found four defects the fitter could not

The four term lists now generate Verilog through `gal/verilog/emit.ts` — the *same*
`Cell` lists the fitter compiles, so a testbench runs the design and not a second
description of it. `v3dot_tb` runs the raster for whole frames in all four VMODE
codes, and **the first time that part ran as a design rather than as a utilisation
figure, four of its terms turned out to be wrong**:

| | was | is |
|---|---|---|
| `HSYNC` | `HC < 8` — **32 dots** | `HC < 24` — 96 dots, which is what VGA at 25.175 MHz needs |
| `ACTIVE` | three disjoint runs totalling **272 dots** | `HC >= 36 AND NOT HC >= 196` — 640 dots |
| `VBLANKRAW`, 449-line family | `VC9 & VC8`, i.e. **VC ≥ 768 in a 449-line frame** — never true | `VC8 & VC7 & VC6` or `VC8 & VC7 & VC5 & VC4` — VC ≥ 432 |
| `VTC` | `VC9 & …` for a terminal count of **448**, where VC9 is clear | `VC8 & VC7 & VC6` (449) and `VC9 & VC3 & VC2` (525) |

⛔ **Every one of them fitted.** They are syntactically valid sums of products that
route and meet timing; the fitter has no opinion about whether `VC9` can be set in a
449-line frame. This is `CLAUDE.md`'s standing point in its sharpest form — *a fit is
not a check* — and it is the answer to what the Verilator stage is for.

`v3dot` is now **122 / 128 cells, 52 / 64 I/O, 0 cascades** (§10.6 refitted it for the
16×16 sprite; `history.md` has what it was), and `v3dot_tb` reports
**17 claims, 0 failed**: 800-dot lines, 96-dot HSYNC, 449 / 525 lines a frame and
400 / 480 active lines, in every VMODE.

⚠ **Two of my own testbench bugs came first, and both read as design failures.**
`LINETICK` and `FRAMEEND` are *one dot* wide — `FRAMEEND` is `LINETICK & VTC` — and
they fall together, so reading `FRAMEEND` after `LINETICK`'s negedge is always false
and the loop runs to its own bound. It reported *"a frame never ended"* for a design
whose frames end correctly. A testbench is a claim about two things.

⛔ And before any of that, **`emit.ts` could not render a term containing CUPL's
`#`.** video3's down-counters write their terminal count as `Q & !A # !B # !C`; the
fitter compiled them and the fit is real, but `toVerilog` emitted `#` into a `.v` file
that would not parse. **A term list the fitter accepts and `emit.ts` cannot render is a
design whose Verilog and whose JEDEC are not the same design** — and nothing checked
that until a video3 part was asked for both. `&` binds tighter than `#` in CUPL exactly
as it does than `|` in Verilog, so the fix is a substitution.

### 6.1 ⚠ What the Verilator stage does NOT yet reach

There is **no `video3_card.v`**. `v3dot_tb` instantiates one part, which is honest
about what it proves: the raster lives entirely inside `v3dot` and needs no board. It
does not touch plan §14 item 8 — the cadence, five requesters against one spare access
a slot — because that is a claim about all four parts, the SRAMs and the latches
together. That wrapper is the next piece of work, and the brief's "see how it interacts
with our mainboard" needs it.

## 7. The game

The tile path needed three changes that the bitmap and character paths did not:

| | |
|---|---|
| ⛔ `CT.Cell` is defined as `MD.Char` so the shared "not bitmap" code keeps working — which made a **tile** screen select **character** mode, where the card reads two bytes a cell and the game's one-byte map rendered as glyph codes and attributes | `ca_tile.asm` says `MD.Tile` |
| video3's `MAPBASE` is **three** bits selecting a whole 64 K region, where `video/`'s is seven selecting a 4 K one — so a tile map cannot sit at 124 | `TL.MBase` is 6 (`$60000`) and `TL.TBank` 28 (`$70000`) under `-DV3=1` |
| the map is on the card's **one 1024-byte stride** with no 32-row ring, so a cell is `MAPBASE × 64K + (row & 63) × 1024 + (col & 127)` | `MapAt` in `vidxcl.asm`, and `overworld.asm`'s own `maddr` |

⭐ **The hero renders** (§9.1). `overworld` builds the hero's fifteen tiles a tile a
frame by reading the background out of VRAM and compositing, and that path addressed
`video/`'s tile bank.

---

## 8. Where it stands, and what is left

**`software/nitros9/video/video3-demo.mp4`** — `sh software/nitros9/video/run-video3.sh`
rebuilds it end to end (`V3=1` for the ROM, `VIDEO3=1` for the card model).

| scene | |
|---|---|
| NitrOS-9 boots to a shell on **80 × 60 CP437**, typed at over PS/2, scrolling by copyrect | ⭐ works |
| a **640 × 480 desktop**, two panes filled by real `dir` output | ⭐ works |
| a window **dragged by the copy engine**, `SS.Copy` a step | ⭐ works |
| the **hardware sprite** pointer, toured by the PS/2 mouse | ⭐ works |
| the **paint** canvas — patterns, ellipses, arcs, the xterm colour strip | ⭐ works |
| **80 × 25 CP437 ANSI art**, the 16 × 16 attribute table | ⭐ works |
| the **overworld**, scrolling on an accelerating ramp | ⭐ works, hero and all (§9.1) |

### What I would do next, in order

1. ⭐ **The hero's tiles** — done, §9.1.
2. ⛔ **`video3_card.v`**, so the Verilator stage reaches plan §14 item 8's cadence and
   the brief's "how it interacts with our mainboard". `v3dot_tb` proves the raster; a
   card wrapper is what proves the card.
3. ⚠ **The drag leaves a title-bar artefact** on the last leg. The staging is correct
   for the cases I traced; this is not yet explained.
4. ⭐ **256-colour text** — done, §9.2: the attribute byte is a handle.
5. ⚠ **`v3scan_mq`'s 41 cascades** (`partition.md` §6 item 6) — still the only figure on
   the card that got worse, and still unexplained.

### ⛔ A correction: I reported the video finished before it was

I told you the MP4 was done — 15,114 frames, 252 seconds — on the strength of a
`DONE=` marker in a log and an `ls -lh` showing a 27 MB file with a current
timestamp. **Both were wrong.**

- The `DONE=` belonged to an **earlier invocation of the same script**, which had
  been redirected to the same log path. A later run was still going.
- The file was **mid-write**. It had `ftyp`, `free` and `mdat` and **no `moov`
  atom** — ffmpeg writes that last, so a truncated MP4 is a large, recent,
  entirely unplayable one. It was still growing while I was describing it.

⚠ This is `CLAUDE.md`'s own trap, twice over: *a marker is not the job's completion*,
and *a stale artefact reads exactly like a fresh one*. I had quoted that trap in this
very report two sections earlier and then walked into it.

`software/nitros9/video/checkmp4.py` now decides the question instead of a size
glance: it parses the atom chain, requires it to close at exactly the file's length
with `moov` present, and checks the file is not growing. `run-video3.sh` exits on it,
so the script can no longer report success on a partial file.

### ⭐ Three things worth keeping from tonight

- **The `VR.*` seam is the port's most valuable asset.** ~2,900 lines of bitmap drawing
  moved cards without a single conditional, because `vidcore.asm` is the only module
  that names a register. It was not designed for this.
- **A fit is not a check.** Four of `v3dot`'s terms were wrong and all four fitted. The
  fitter has no opinion about whether `VC9` can be set in a 449-line frame.
- **The failures that cost the most time were silent ones**: an ANSI terminal that
  dropped every byte and returned no error; a dispatch placed after an `rts`; a stale
  `.fit`; a makefile that did not rebuild what I had changed; `display` taking hex where
  I wrote decimal; and a half-written MP4 with a convincing size and timestamp. Every one
  of them produced a *plausible* result, and the last one I reported to you as finished.

---

## 9. The second pass — 2026-09-17, from the review of the first video

Seven points came back from watching §8's video. What each was, and what changed:

| # | the review said | cause | now |
|---|---|---|---|
| 1 | /W1 never has enough text to scroll | the session typed three short commands | `list /dd/sys/video3.txt` — 110 lines, generated by `v3show.py` — scrolls the 80 × 60 console by copyrect |
| 2 | no visible mouse movement; is it the pink square? | ⛔ **nothing ever sent GCSet**, so `VG.PtrOn` stayed clear and every path that moves the sprite returned early. The squares were the **text cursor** (a cell XOR `$FF`) | the desktop stream sends GCSet and turns the text cursor off. ⛔ And a second defect: a character screen's `TxPal` loads all 256 pair banks, **1 and 2 among them**, so the arrow came up orange after the BBS — a bitmap `Select` reloads the pointer's banks |
| 3 | Paint has no window scrolling | video3 has no display list, so the old per-line `HSCROLL` has no equivalent | §9.4: the canvas scrolls by **two copies a step** |
| 4 | the BBS on /W2 never appears | ⛔ the stream left the **ANSI terminal on**, and `AnsiByte` **dropped** the following `ESC $21` (Select) without an error | `ca_ext.asm` passes `ESC $21`/`$24` through in ANSI mode, and the stream turns ANSI off at its end |
| 5 | hero tiles missing; a tile row goes missing after the first vertical scroll | ⛔ **one cause**: the hero's tiles were read and written with the **map's** high byte (§9.1) | fixed |
| 6 | can `ATTR` give 256-colour pairs, or at least pick the 16 from 256? gruvbox? | the hardware always could; the driver loaded one fixed choice | §9.2 |
| 7 | the desktop is rudimentary next to the old Haiku one; put drawing in ROM | — | §9.3: the **ROM toolbox** |

And a request that came in during the work: **show every window before drawing on it**.
Every stream now starts with `DWSet` then `Select`, so the display blanks and the chrome is
drawn in view. That exposed §9.5.

### 9.1 ⛔ The hero, and the missing wall row, were one bug

`video/`'s tile bank sat at `$78000`, which is `MapHi` (7) plus `$8000`, so `overworld`
addressed the bank **with the map's high byte**. On video3 that byte is 6 — the map itself
— so the hero composited its background out of map rows 32–33 (zeros) and wrote its
finished tiles 240–255 **over map row 47**. Row 47 is off screen until the first move
south, which is exactly when the review saw a row vanish; the hero is rebuilt continually,
so the row never came back. `TileHi`/`TileLo` now name the bank (`$70000`). And
`VSCROLLH` was always written 0 — right for `video/`'s 32-row ring, wrong for video3's
64-row torus, where a camera at y ≥ 256 needs bit 8; the game now writes it.

### 9.2 ⭐ The attribute byte is a handle: 256 pairs from 256 × 256

Plan §2.2 already said it: an `ATTR` value selects a sub-palette and a glyph uses its
entries 0 and 1, so **any** 256 (fg, bg) pairs can be on the screen at once. The first
driver filled all 256 with VGA's crossing, which is one fixed choice. The 6-bit-fg / 2-bit-bg
split the review suggested is another, and it would cost ANSI art its sixteen backgrounds.

`ca_v3txt.asm`'s **`TxPair`** allocates instead: an SGR 38;5;n / 48;5;n pair, or a
16-colour one, gets a slot on first use — home slot `(bg & 15) << 4 | (fg & 15)`,
probing upward, so VGA's 256 pairs still land on their own bytes and cost nothing. A slot
that already holds the pair is reused with no palette write; when all 256 are in use,
`TxGC` keeps the ones the screen's cells show and frees the rest. The table lives in the
**shadow's padding** (each 256-byte shadow row uses 160), because CoArm's globals are
what does not fit. `TxAttr` caches the last answer per window, so a run of text in one
colour is one compare a cell.

⚠ **The limit is 256 distinct pairs on the screen at once**, not 256 colours. The BBS
shows 128 VGA pairs and 96 256-colour ones side by side; a screen that needs more gets its
home slot, which is the wrong colour and not a hang.

**The sixteen are now just SC.Pal's first sixteen**, which a character screen holds as
xterm's 256. They start as **gruvbox** (dark), and `Pal565`/`PalRange` on a character
screen change them like any other entry — `TxPalQ` reloads the pairs, where the bitmap
path would have written the LUT's low half and recoloured slot 0 alone. The BBS stream
loads gruvbox with `PalRange` to show that it can. CoArm is **15,866 of 16,384 bytes**.

### 9.3 ⭐ The ROM toolbox — QuickDraw's arrangement, for CoArm

CoArm had 1,072 bytes spare (§2.2) and a Haiku desktop needs fonts, icons, window chrome
and pictures. The boot ROM had ~800 K free. So the ROM is now split:

| ROM pages | |
|---|---|
| 3–63 | the RBF disk, 1,952 sectors (834 used) |
| 64 | **the toolbox's code** (`tbox.asm`, 2.6 K), run **in place** |
| 65–127 | its data (`software/nitros9/tools/mktbox.py`): the Haiku palette, **Noto Sans 12 px regular and bold, anti-aliased to two bits**, 31 icons (the old demo's art, re-quantised), and the 384 × 480 paint document |

`ESC $6A fn n <n bytes>` (`ca_tbox.asm`, ~150 bytes of CoArm) maps page 64 at
`Co.WinA` and calls it. The toolbox draws through CoArm's own row layer (a vector table
of `RowFill`, `RowPut`, `FillRect`, `MapB`, the palette), so it reaches the card and a
screen's store alike and inherits the working-area clip. Its functions: anti-aliased
text and centred text, icons, bevels, the Haiku window (gradient yellow tab, close and
zoom boxes, frame), rectangles, gradients, the palette, pictures, and Haiku scroll bars.

⛔ **Two rules the arrangement imposes**, both written at the top of `tbox.asm`:
`Co.WinA` *is* the toolbox while it runs, so nothing it calls may map `Co.WinA` (the GP
buffers, the character shadow); and the row layer maps a store at `Co.WinB`, so the
toolbox copies what a row needs out of its data page before every row operation.

The desktop (`v3desk`, `v3cmds`, `v3about`) and Paint (`v3paint`) are toolbox escapes.
**`v3trk`** is the Tracker: it reads a directory's real 32-byte entries and writes an icon
and a name for each, counts what does not fit ("67 items") and sizes the scroll bar's
thumb to match.

Three defects on the way, for the record: the toolbox's row clear reloaded its colour
from the loop counter, so every string sat on a black box; an inline rectangle encoded an
absolute size as `$80 + n`, so a relative −2 read as 126 and a window's panel ran off
the screen; and `v3trk` showed `.` because the first byte of that name carries the
end-of-name bit.

### 9.4 ⭐ A window scrolled by the copy engine

Without a display list, `HSCROLL` moves the whole screen, so a window scrolls the way a
Macintosh's did — move the view, draw what came in — except both halves are the card's.
The document is **the photograph `software/demo`'s desktop show was made from**
(`software/demo/build/parrots-image.jpg`, untracked, per git `790de82`), scaled to 480 rows
and cropped round the middle macaw; without it `mktbox.py` falls back to `mkparrots.py`'s
illustration. `v3paint` puts the 384 × 480 document into **VRAM's scroll margin** (columns 640–1023,
plan §4) with the toolbox's *raw* image call; the display cannot see it there. **`v3scrl`**
then scrolls a 256 × 320 view across it: each step is one `SS.Copy` inside the canvas and
one from the margin, and the CPU touches no pixel of the picture.

⭐ **`vidcpy3.asm` no longer stages a copy whose destination comes first.** An ascending
copy is safe whenever the destination starts before the source in raster order — byte p is
read at step p, and only the destination's bytes 0 … p−1 have been written — so a move up
or left is one pass however much it overlaps. Only down and right go through the scratch
rows.

### 9.5 A fresh screen is filled, not copied

Showing a window before drawing on it means selecting a **new** 640 × 480 screen, and
`StoreToCard` copied its blank 307 K store to the card through `VDATA` — seconds of
black. A new bitmap screen's store is one colour until something is drawn into it, so
`SC.Fresh` records that, `Target` clears it, and `StoreToCard` fills the card with two
span-solid rectangles instead.

⚠ **The first video's 18-second black gap was the other direction**: Paint was its own
screen, so selecting it copied the desktop *into* RAM (`CardToStore`). Paint is now a
window on the desktop's screen, as a Haiku application is, and the show never swaps a
bitmap screen out.

### 9.6 Review by contact sheet

`SHEET=1 sh software/nitros9/video/run-video3.sh` runs the session and writes
`build3/sheet-1.png`, `sheet-2.png` (a full-size 640 × 480 tile every 3 s of machine time,
with the caption on screen) and `sheet-scenes.png` (each scene as it was left), through
`software/nitros9/video/sheet3.py` — about three minutes, where the H.264 file adds several
more. The session is 258.8 s of machine time, no `Error #` on the console, and no register
write under a span.

### 9.7 ⚠ Also found: the video/ flavour did not build

`v3drag` was added to `CMDS` for both flavours at the first pass, and `SS.Copy` exists
only under `-DV3=1`, so `sh software/nitros9/run-emu.sh` failed to build. The video3
commands and the toolbox page are now video3's alone; the video/ ROM's page 64 is blank.
`run-emu.sh`: 23 claims, 0 failed; `SCENARIOS=nitros9 npm run check:machine`: 19 claims,
0 failed.

---

## 10. The third pass — 2026-09-17, from the review of the second video

Three points came back from the second video: the pointer was malformed and appeared
only for the mouse tour, Paint's horizontal scroll ran four times faster than its
vertical one, and the hero jumped from tile to tile where `software/demo`'s walks.
All three were measured before they were touched, from the session's own recording.

### 10.1 The pointer was never missing — it was at (0, 0)

The desktop stream sent `GCSet` as its **last** escape, so the sprite came on when the
chrome was finished and sat in the top-left corner until the first mouse packet moved
it: thirteen white pixels against the desk, for 37 s. And the arrow's eighth row was
`##@#`, which leaves a **fill pixel on the outline's outside edge** — the malformed
look. `vidptr3.asm`'s art is now closed all the way round (eight rows leave no room
for a tail, so it is an arrowhead), `v3desk` turns the pointer on immediately after
`Select` and parks it on the open desk with `PutGC`, and:

⭐ **`v3drag` drags with the pointer.** It glides to the About window's tab, a point a
tick, and every step of the drag moves the pointer with the window — `PutGC`, so the
sprite's five registers and no pixels, beside the copy engine's window and no pixels.
`session3.py`'s mouse tour then starts from where the drag left it, instead of jumping
to a corner.

### 10.2 Paint's vertical scroll was the scroll bar, not the copy

A step's two copies are the same size in both axes, and the measurement said
otherwise: **6 frames a horizontal step, 25 a vertical one**, with the vertical bar
changing on every one of those frames. The toolbox's `Scroll` repaints the whole bar
— trough, two arrow buttons, thumb, three grips — and a 320-pixel vertical bar is 320
rows of short fills where a 256-pixel horizontal one is 14.

`v3scrl` now moves **the thumb alone, by the copy engine**: one `SS.Copy` of the
thumb's rectangle, then one bar in the trough's colour over the few pixels it
uncovered. Per leg, measured on the session:

| leg | before | now |
|---|---|---|
| horizontal, 128 px | 0.58 s | **0.58 s** |
| vertical, 160 px | ~6 s | **0.67 s** |
| the whole scroll scene | 32 s | **9.4 s** |

### 10.3 ⭐ The hero: 16 frames a build became 5, and where the time went

`software/demo`'s hero is not rebuilt every frame either — on the host emulator it is
rebuilt **every 4 frames**, and at two pixels a frame that is an 8-pixel step at 17 Hz,
which reads as walking. `overworld` was rebuilding **every 16**, a 32-pixel jump.

The cause was not the OS: `overworld` did **ten compose stages a frame and then
slept**, and a hero is 150 stages. Lifting that alone gave 10 frames; a trace of
600,000 instructions said where the rest was.

| | share of the CPU |
|---|---|
| `compose1` and `copy16` | 34 % |
| `libvid`'s reads and writes | 18 % |
| the kernel and the I/O stack | **40 %** |

Four changes, in the order they paid:

| | |
|---|---|
| ⭐ **the clock became free** | a system call to ask whether a frame had ended costs **~1.4 ms** measured, and the loop made two or three a frame. The VBL service now writes its frame count into the card's spare register (`plan.md` §10's `+$1F`), so the check is one read and can be made after every stage |
| ⭐ **nothing is copied** | `cbuf` **is** four `libvid` records, so the background is read into the tile being built and written out from it in place. `copy16` is gone, and with it 12 % of the CPU |
| **the sprite's columns only** | the pixel loop ran all eight columns of every cell through two bounds tests each; it now computes the overlap once and visits only the columns inside the sprite |
| ⭐ **a third tile buffer** | with two, a build could not start until the last flip's batch was on the card, so **two frames of every hero went to waiting**. The third (codes 211–225; `mkgame.py`'s world uses 53 and now asserts it stays below `SPRA-15`) lets the next build start in the frame of the flip |

**The result, measured over 1,282 game frames: a hero every 5 frames** — 191 of 209
gaps are exactly 5 — against 16 before and 4 for the bare-metal demo. No batch waited
a blank for a busy one (`VG.MkMiss` is 0), and the camera advances one record a frame
in every frame but twelve, which are the 16 px/frame transitions.

⛔ **And one defect the change introduced, worth keeping.** The next frame's work must
start on the first VBL **after the batch went in**, not after the frame began. A VBL
that lands between the two commits nothing, and starting a frame on it hands `SS.Batch`
a second batch while the first is still waiting — which then waits a blank, and so does
every frame after it. The hero fell to **one build every 45 frames** and `VG.MkMiss`
climbed by one a frame. `bf` is the count when the batch went in, and it is what the
compose loop compares against.

### 10.4 video/ keeps the old cadence, and run-vid.sh is why

`overworld` builds both flavours. video/ has no spare register to read the count from,
and building on past the frame's start cost it two claims: the camera advanced one
record in 78 % of frame pairs where 90 % is the rule, and **the longest IRQ went to
1,403 µs against a 1,400 µs budget** — the VBL that commits a flip, taken while the
process is *running* rather than asleep, costs ~10 µs more for the map switch. So
under `-DV3=0` the hero is still a tile a frame and the flip still waits out its
commit asleep; video/ keeps the other three changes, which only remove work.
`run-vid.sh`: **54 claims, 0 failed** — including the camera claim, at 90.2 %, which
the same run fails at 88 % without these changes.

### 10.5 What a keyed copyrect would buy, and what it would cost

⚠ **Not built, and not proposed here** — this is the arithmetic for the question, so
the next pass does not have to redo it.

**The hardware.** `CCTRL` b1 and b2 are reserved since the direction bits were dropped
(§6.2). A *keyed* copy — skip the write when the source byte is the sprite key — needs
no adder, no latch and no direction: the byte is already latched in `vread` on the read
access and goes out through the posted-write `'574` on the write (§6's last row), so the
compare gates the write access. `v3ptr` has **18 macrocells and 20 pins spare**
(`partition.md` §2.3): ~8 pins to bring `vread` into the part, or one pin and a `'688`
comparator, plus a `CCTRL` bit and a term. ⚠ **It needs a fit.** `v3ptr_rows` and
`v3ptr_both` went from 3 cascades to 19–21 and filled the part, and `CLAUDE.md` is
explicit that cascades are a timing change even when cells are flat.

**What software could do with it, in tile mode: a hero every 1–2 frames, not
instantly.** ⛔ **A tile is not a rectangle to the engine**: the engine steps a row by
the 1024-byte stride, and a tile's eight rows are one 64-byte run at `TILEBASE +
code × 64`. So a hero is ~15 plain copies (a background tile is one 64-byte row) plus
~80 keyed row copies of 8 bytes, each seven or eight register writes from the CPU. The
engine's own time is nothing; the register writes are the cost.

**In bitmap mode a keyed copy would be one copy for the whole figure** — 32 × 16 is a
rectangle on the stride — plus one to restore what it covered. That is the attractive
version, and ⛔ **the scroll is what refuses it.** In tile mode the playfield is a map
and `HSCROLL` moves it for one register write; in bitmap mode the incoming columns have
to be drawn, and at 16 px a frame that is two tile columns — 50 tiles, 400 row copies a
frame. Switching modes does not help either: **in tile mode the picture exists only as
map codes and tiles**, composed at scan time, so there are no playfield pixels in VRAM
for a bitmap pass to overlay. A bitmap playfield would have to be blitted from the tile
bank first — 2,000 tiles, ~16,000 row copies a screen.

⭐ **And the save-and-restore the scheme is built around is already free in tile mode**:
the hero's background is the world's tile code, so giving a cell back is writing that
code into the map. That is what `flip` does, in the same batch as the scroll, in one
blank — which is also the page flip. The two hero buffers (now three) *are* the flip.

**Page flipping, since the question was asked directly.** VRAM is 512 KB — `WPTR` is 19
bits — on a fixed 1024-byte stride, so the address space is **512 rows** and a page
costs its full height in rows whatever its width:

| mode | one page | two pages | fits in 512 rows |
|---|---|---|---|
| 640 × 480 | 480 rows | 960 | ⛔ **no** |
| 640 × 400 | 400 | 800 | ⛔ **no** |
| 640 × 240 | 240 | 480 | ⭐ yes, with rows 480–511 left for staging — exactly |
| 640 × 200 (the game's, row-doubled to 400) | 200 | 400 | ⭐ yes, 112 rows spare |

So **640 × 480 cannot be page-flipped on this card and 640 × 200 can**, with 112 rows
(114 KB) over for sprite art and saves — and the flip is one `VSCROLL` write in the
blank, since §8.1's row counter loads from it over a 512-row torus. ⚠ The 384 off-screen
columns of every row (196 KB, §4) are the other place art can live, and cost no rows.

### 10.6 ⭐ The sprite is 16 × 16

Asked for after the pointer landed: `software/demo`'s arrow, which is 16 × 16 with a
tail, in place of eight rows that could only hold an arrowhead. The shape is
`show.py`'s `cursor_masks()` art character for character, and it is now in three places
that agree — `vidptr3.asm`'s 64 bytes, `video3/bench/mkv3sprite.py`'s generator, and the
emulator.

| | 8 × 8 | 16 × 16 |
|---|---|---|
| shape | 16 bytes, two a row | **64 bytes, four a row** — the low plane's columns 0–7 and 8–15, then the high plane's |
| `SPRIDX` | 4 bits | **6** |
| the window counters | 3 bits each | **4 each** (sixteen columns, sixteen rows) |
| the shift registers | 2 × `'165` | **4 × `'165`**, two cascaded a plane |
| `v3dot` | `history.md` has the 8×8 fit | ⭐ **122 / 128 cells, 0 cascades, `Design fits successfully`** |
| the card's parts list | the `'165` were not in it at all | **39 ICs**, the four `'165` included — `partition.md` §5 risk 3 calls them a requirement, so they belong in the list |

⭐ **Cascades fell from four to zero**, so the part got *easier* to route, which
`CLAUDE.md`'s rule about cascades being a timing change makes worth saying out loud.
`video3/bench/run-v3sprite.sh` is the check that matters: 36 positions — every X phase,
both 4-byte phases, the left and right edges, the line-doubling boundary and all four
`VMODE`s — every pixel the model's.

⛔ **And one thing this did NOT fix, because it was already broken.** The sprite's row
*fetch* has no design output behind it: `v3dot` emits one `SPRLD` and the `'165` take
their parallel data from `D`, but **nothing drives `RFA`** — the register file's address
— during the fetch, so one strobe cannot deliver two different bytes, let alone four.
`partition.md` §6.1 already carries this as one of its two open correctness gaps (with
`WPTR`'s end-of-row reload, which is blocked on the same missing address generator), and
16 × 16 makes it four bytes a row instead of two. **The counters, the store and the
`'165` are sized for it; the fetch sequencer is still owed.**

### 10.7 The top row of trees had black between the canopies

From watching the third pass's video: after the last vertical scroll, the top border
row's trees have black between them where the sand should be. ⭐ **It was the tile art,
and the measurement is what said so** — `mkgame.py`'s `tree` metatile is sixteen art
pixels wide and its canopy filled that width, so the outline colour sat in the edge
columns of the six widest rows. Border trees are placed side by side, so two outlines
met and the pair read as a black gap rather than as two outlines. The canopy's widest
rows now start one pixel in, which leaves **four screen pixels of sand** between
adjacent canopies, and the tree keeps its outline all the way round.

⚠ **It was never a defect of this card, this driver or this pass**, and three
measurements are what establish that before anything was changed:

| | |
|---|---|
| every video3 game frame is `mkgame.render()` | **1,382 of 1,382**, pixel for pixel — the comparison `checkvid.py` makes for `video/` and which nothing had run against a video3 recording until now (`gamediff.py`, in the session's scratch) |
| the top 48 scanlines after the last vertical scroll | **byte-identical** to the same screen at the game's start, so nothing degraded during the scroll |
| the art | unchanged since `b446902`, the commit that first ran the demo on the whole machine — the same black is in `software/demo`'s own video |

It reads as new at that moment because the camera only returns to screen (0, 0) at the
end, where that border row lies along the top of the picture with sand behind it. The
bottom border row has the same edges and always hid them against the cliff band: 1,120
black pixels in the top sixteen rows against 128 in the bottom sixteen.

⚠ **Both shows change appearance**, because both draw from `tiles.bin`:
`software/demo`'s emulator run and `checkdemo.py` re-ran against the regenerated model —
**1,169 of 1,169 game frames exact** — and the video3 session was re-run and re-encoded.

---

## 11. The console's speed — where it went, and 2.5× of it back

From watching the third pass's video: the 80 × 60 console lists a file at about ten
lines a second. **Measured, it is 9.7** — 17 line feeds and 665 characters in 1.77 s of
machine time, ~2.7 ms a character — and the question was what limits it.

### 11.1 Neither the card nor `list`

A 600,000-instruction trace during the listing, by module:

| | share |
|---|---|
| **CoArm** | **72%** |
| ArmIO + SCF + IOMan + the kernel — the trip into the driver, per byte | 24% |
| RBF + the ROM disk, reading the file | 1.6% |
| ⭐ **`list` itself** | **0.02%** — 121 instructions in the whole trace |

The card's share is **2.2%**: 17 scrolls at ~2.3 ms of copy engine, plus 2.6% of CPU
waiting on it. `plan.md` §8.2 costed character-mode scrolling and concluded the scroll
is nearly free; that holds. **What it never costed is the per-character path**, and that
is what sets the rate: ~900 instructions a character, of which CoArm's own share is the
stream loop, the shadow write, **the cursor erased and redrawn once per character**, and
**the colour-pair allocator looked up once per character**.

### 11.2 SCF already had the answer — for a CoCo 3

⭐ Stock `scf.asm` has a fast path that hands GrfDrv a **whole run** of printable
characters (`call.grf`, callcode 6). It is gated on the driver module being named
`VTIO` and on `G.GrfEnt`, so this port fails it at the first compare and falls into the
byte-at-a-time path. The options were: impersonate VTIO (a name check, CoCo 3's static
layout at `V.ParmCnt` and `V.WinNum`, a fabricated CoWin window table at `WinBase`
**which is the page this port's globals live in**, and a second calling convention in
CoArm), or generalise the test in our own fork. ⚠ **`WGlobal` is `$1000` and `WinBase`
`$1290`, and `VG.Addr` is `$1100`**: `armvid.d` picked that page *because CoCo 3's
GrfDrv globals are not used here*, and option A would have made them used again.

So `scf.asm` gained an `IFNE V3` fast path of its own: the same scan for a run of bytes
≥ `$20`, then a call through **`VBL.WrBlk`** — a vector the video globals publish
(`D.VBLSt` already points at them). Control characters still go down the stock path, so
CR, LF, pause and end-of-record are untouched. ArmIO's `WrBlk` copies the run into
`VG.WBuf` (block 0, which CoArm's task can see) and makes **one** `CF.WriteN` call;
`TxPutRun` writes the whole run into the shadow and pushes it to the card with **one**
`WPTR` load, one pair lookup and one cursor update.

| | lines a second |
|---|---|
| before | **9.7** |
| SCF's fast path alone — one driver call and one task flip a run | 11.9 |
| ⭐ **+ `TxPutRun`: one card write a run** | **24.3** |

The screen is checked against an 80-column simulation of the file: **58 of 59 rows
identical**, the 59th being the cursor's block. (The file's eighteen 80-character lines
wrap and *then* take the file's own newline, which is what any 80-column terminal does.)

### 11.3 ⛔ Y IS THE VIDEO GLOBALS, EVERYWHERE IN CoArm

The first two attempts at `TxPutRun` ended in a wild jump in task 1 some calls later.
The cause is worth the section:

**`vidcore` finds the card with `ldu VG.Base,y`.** Y is CoArm's globals pointer for the
whole of a call, and `TxPutRun` borrowed it for the run's source pointer. So `VcPtr`
read *two bytes of the text being listed* as the card's base — `$2036`, a space and a
'6' — and the card's `WPTR` registers were written into CoArm's own code at `$2040`,
which became `NEG <$AD`: a direct-page write to **`D.VIRQ`, the kernel's tick vector**.
The next clock interrupt jumped through it into empty RAM.

⚠ **Everything the static reading suggested was wrong.** It was not the row-wrap path,
not the growth of CoArm's globals, not an oversized shadow write (a hard clamp changed
nothing), and not a stack leak — `TxPutRun` entered at `S=$1EFE` and returned balanced
at `$1F00` every time.

⭐ **What found it in one run: `WATCH=addr` in `software/demo/emu/machine.c`**, added
during this pass. It prints every write to an address with the PC, the stack pointer and
the opcode bytes. Watching `D.VIRQ` gave the instruction; watching CoArm's own code gave
`sta VR.WPTR2,u` with a text-derived `U`. **A trace shows instructions; this shows
effects**, which is the half that was missing.

⚠ And the rule generalises to the audio card: a `/FIRQ` service is entered with
**U = `D.FIRQSt`** (`krn.asm`'s `ArmFIRQ`), so U there is what Y is here. The kernel
stacks D, DP, X, Y and U around the call, which is the guard CoArm's convention lacks.

### 11.4 ⚠ video3 only, and why

Every piece of this is under `IFNE V3` — the SCF path, `VG.WrBlk`, `VG.WBuf`,
`CF.WriteN`, `WrBlk`, `CoWriteN` and `TxPutRun`. On `video/` the fast path cost two of
`run-vid.sh`'s claims: the camera's one-record-a-frame share fell to 89% where 90% is
the rule, and the flip's IRQ went to **1,403 µs against a 1,400 µs budget**, because a
CoArm call that takes a whole run is longer and the VBL lands inside one more often —
an IRQ taken in a process costs ~10 µs more for the map switch. ⛔ **And merely growing
VG moved those numbers too**: both claims sit on their thresholds (88.2%, 89.1%, 90.2%
across builds), so the `video/` build's globals are byte for byte what they were, and
`run-vid.sh` is **54 claims, 0 failed** again.

### 11.5 What is left, measured

After the change, during a listing (300,000 instructions):

| | share |
|---|---|
| `Strm` — the byte-at-a-time `VDATA` stream | **16.2%** |
| `TxClrRow` — blanking the new row after a scroll | 3.7% |
| `TxShC2`, `TxWr`, `TxCard` | 8.3% |
| `TxPair` + `TxPEnt` | 3.3% |
| `TxCurOn` (once a run now) | 1.9% |
| the kernel, SCF and IOMan (one call a run now) | 28% |

### 11.6 ⭐ The scrolled row is blanked by the copy engine

Per line the card took ~90 bytes of text and **~160 bytes of blanks**, so the clear was
two thirds of the traffic. The map has 64 rows and the tallest character screen is 60,
so **row 63 holds a row of spaces in the window's own pair** (`TX3.Blank`), and
`TxClrCd` has the engine copy it into the new bottom row: seven register writes and no
`VDATA` at all. A clear whose ATTR the template does not hold is streamed as before and
**becomes** the new template, which pays for itself on the next scrolled line. ⚠ A
`Select` invalidates it — the template lives in the map of whichever screen is
displayed.

**Measured**: 28 of 29 clears in a traced listing are engine copies, `Strm` falls from
**16.2 % to 9.8 %** of the CPU, and the listing's scroll span goes 2.4 s → 2.3 s. The
rate barely moves because the card was no longer the limit: what remains is the
per-line trip through the kernel, SCF and IOMan (one `I$Write` a line, which is
`list`'s business) and CoArm's shadow work.

| the 110-line file | scroll span | lines a second |
|---|---|---|
| before this pass | 8.9 s | 9.7 |
| SCF's fast path | 4.8 s | 11.9 |
| `TxPutRun` | 2.4 s | 24.3 |
| ⭐ **+ the engine clear** | **2.3 s** | **~24** |

⭐ **3.9× end to end.** ⚠ Next, and to be measured rather than assumed: `VcChunk`, the
stream's chunk size — each chunk costs a `VcWait` and a pointer check, and a row of
text is several of them.

## 12. A real `.ans` in the BBS scene — 2026-09-17

Blocktronics' **"we-tortuga"** (80 × 889 of CP437, from the 2016 *Block 'n' Roll*
pack) scrolls through `/W2` after the colour-pair screen, drawn by `ca_ext.asm`'s
own ANSI terminal. The window is the piece's middle: the top of the blue sky down
to the bottom of the pirate with the hook — **grid rows 142–406**, 265 rows.

⚠ **The file is parsed and re-emitted, not copied** (`v3show.py`'s `art_grid`,
`stream_art`). Copying 164 KB would spend most of it on `CUF` runs and on
sequences this terminal does not implement; re-emitting keeps the stream to SGR
and CP437, and lets the demo choose a window.

### 12.1 ⭐ SAUCE flags bit 0 is iCE colour

The piece sets it, so **SGR 5 is a bright background, not blink** — 16 background
colours, not 8. `ca_ext.asm` learned SGR 5 and 25 and `WT.AnIce`; `AnCol` ORs bit
3 into the background while it is set. Without this the whole lower half of the
piece loses its magenta and reads black.

### 12.2 ⛔ The palette is indexed by the SGR NUMBER, not the DOS attribute

`art_grid` stores the SGR colour (30+n) and that is the index `PalRange` writes,
so entry **1 is red and 4 is blue** — the DOS attribute table has those two the
other way round. The first version of `VGA16` was in attribute order, which
swapped red with blue and brown with cyan.

⚠ **And it chose the wrong 51 rows of the piece as well.** The window had been
picked by measuring "how much blue is in this row"; with blue reading as red the
measurement landed 435 rows below the sky, on something that only looked like sky
to a colour-blind test. **The picture is the arbiter of where things are** — the
window is now stated in `we-tortuga.ans.png`'s own pixel rows (2270–6500), and
the decoder is checked against that PNG rather than trusted: for all 21,200 cells
of the window, the colours the reference paints are a subset of the `(fg, bg)`
pair as decoded. 0 mismatches.

### 12.3 ⚠ A palette load recolours what is still on the screen

Loading the DOS palette while the BBS screen was still up turned it from gruvbox
to blue for three seconds — a character screen takes a palette change live
(`TxPalQ` reloads the pairs), which is the feature, but here it showed. The
session clears `/W2` with `$0C` first.

⛔ **And the palette cannot travel with the art.** `AnsiByte` passes only `ESC [`,
`ESC $69`, `ESC $21` and `ESC $24` through, so a `PalRange` sent while the ANSI
terminal is on is **dropped with no error**. It is its own stream, `v3pal`, copied
before `display 1b 69 01`.

### 12.4 Measured: 4.6 rows a second

265 rows take **57 s** of a 285 s session. This is the per-character path at full
stretch and §11's work does not help: dense art changes colour almost every cell,
so `TxPutRun`'s run never starts and every cell pays its own `TxAttr`. The lever
is the number of rows, not the rate.

## 13. A word processor, and NitrOS-9's other font system — 2026-09-18

⛔ **THE PREMISE WAS WRONG, AND CHECKING IT FIRST IS THE WHOLE STORY.** The
scene was asked for as "the 18 fonts wildbits included". There is no 18
anywhere in either tree — the nearest are `RowH equ 18`, the Tracker list's row
pitch, and the 19 px window tab. What is actually there:

| where | how many | what |
|---|---|---|
| the ROM toolbox | **2** | Noto Sans Regular and Bold, 12 px on a 17 px line, proportional, 2 bpp anti-aliased. `FontMap` clamps at **4** and the directory reserves four slots |
| wildbits | **27 usable of 28** | `level1/wildbits/sys/fonts/*.asm`, 8 × 8, 1 bpp, plain Data modules. **None is in the arm6309 ROM** |
| NitrOS-9 stock | 5 | `stdfonts` (3 sets), isolatin1, ibmedc — also 8 × 8 |

So the demo shows the **wildbits** faces, through **NitrOS-9's own downloadable
font path**, not the toolbox's.

### 13.1 ⭐ A font is data on the wire, not a module in the ROM

`ESC $2B GPLoad grp buf sty xs ys n` + n bytes puts a face in a GP buffer
(`ca_gpb.asm`; type 5 is 1 bpp, and it makes the buffer itself, so `DefGPB`
is not needed first). `ESC $3A Font grp buf` sets `WT.Font`, and
`ca_bmtx.asm`'s `GlyphOf` then reads the glyph for a code at **code × 8**.
Buffers are CoArm's, not a path's, and `GPMax` is **48** — so all 27 are
resident at once and cost `F$AllRAM` blocks, **not** ROM disk space and not
any of CoArm's 16 KB window, which has one byte free.

`mkfonts.py` reads the bytes out of the wildbits source. ⚠ **Nothing is
assembled**: the ROM never loads them as modules.

### 13.2 ⚠ The parse is checked against the picture, not trusted

A font that parses is not a font that is *there*. `mkfonts.py` requires whole
8-byte glyphs and asserts that codes 32–126 hold real ink, so a face whose
glyphs live elsewhere cannot load as 2 KB of spaces. `jessefont.asm` is
rejected by it — 1,031 bytes, not a multiple of 8. ⚠ It also reads **both
radixes**: most files are `$hex`, `jessefont.asm` draws its glyphs as
`%binary` so the source looks like the letter, and reading only hex made it
look like a 160-byte file rather than an incomplete 1,031-byte one.

### 13.3 The two scenes

- **`v3write`** — the window, menu bar and ruler from the ROM toolbox, a letter
  on the page, and ⭐ **the Font menu pulled down with all 27 names each drawn
  in its own face**, the current one highlighted and the hardware sprite on it.
  A dropdown over text is the one thing a word processor shows that a specimen
  sheet cannot, and here it genuinely occludes: the page and the menu are
  painted in order into the same window.
- **`v3spec`** — the same window, menu closed: two columns, the name in the
  ROM's proportional Noto Sans and the sample beside it in the 8 × 8 face.
  ⭐ **Both font systems on one line.**

### 13.4 ⚠ Three things the hardware decided

- **Text on a bitmap window is placed in CELLS** (`$02 X+32 Y+32`), and a cell
  is the 8 × 8 glyph box. Every coordinate in the layout is a multiple of 8;
  the specimen's line pitch is 24 px because 20 does not exist, and the letter
  is on a 2-cell pitch because an 8 × 8 face set solid has no room under it.
- **A toolbox payload is 64 bytes**, so a caption is one line of 58.
- ⛔ **Only the FIRST stream on a device may `DWSet`.** The second is
  `E$WADef`, "Window already defined" — the rule `stream_cmds` and
  `stream_about` already follow on /W3. `v3spec` draws into the window
  `v3write` left. The session **failed** rather than drawing nothing, because
  `run-video3.sh` greps the console for `Error #`.

⚠ `w5.dd` is new: the app gets its own window device rather than borrowing
Paint's.

## 14. ⛔ The copy engine's model ran 3.1× too fast — 2026-09-18

Asked whether the Paint scroll was physically real, and it was not, by a
specific and traceable amount.

`software/demo/emu/machine.c` charged a copy like this:

```c
int wide = ((sc & 3) == (dc & 3));
uint64_t groups = wide ? ((uint64_t)w + 3) / 4 * h : (uint64_t)w * h;
```

— the **four-byte group**, which `plan.md` §6.1 withdrew with trade 1
(`647f4f3`, 2026-09-16): *"One read access and one write access move one byte,
so the engine runs at 4.05 MB/s in every case."* That commit updated the spec,
`timing.check.ts`, `partition.md`, `signals.md` and `parts.ts` — and not the
emulator, whose copy timing was unchanged since video3's first commit
`173a3b9`. **The model implemented a design that had been deleted**, and
because Paint's scroll has its columns congruent mod 4 it took the fast path
every time: **12.59 MB/s against the design's 4.05**.

⛔ **And the worse half is not about speed.** The model's `VSTAT` set b7, b6,
b5 and b0 and **never b4** — `VSTAT.CBusy`. `vidcpy3.asm`'s `CpWait` and
`ca_v3txt.asm`'s `TxCWait` poll exactly that bit, and are the only code that
waits on the copy engine. **They had never once spun.** The copy's time was
charged through `SPANBUSY` instead and absorbed by the next `VcWait`, so the
accounting roughly worked by accident while the code that would really wait on
the card went untested. It is the repository's own trap, again: *a model that
is more capable than the hardware cannot fail*.

**Fixed**: `COPY_PS` is 246,913 ps a byte (4.05 MB/s, byte-granular, no
congruence path) and `copy_until` drives b4. The model now agrees with
`plan.md` §6.1's own table — a 192-row window scroll is **30.3 ms**, a console
scrolled line **2.33 ms** against its quoted 2.3.

⭐ **And there is a proof the bit works.** Moving the charge off b7 and onto
b4 made the scroll scene **slower** (6.37 s → 8.82 s). b7 was the only path by
which that time used to reach the CPU, so it can now only be arriving through
`CpWait`.

⚠ **What is still not settled**: 4.05 MB/s is arithmetic from the access
budget, not a measurement; `plan.md` §14 item 8 (five requesters, one spare
access a slot) is open; the copy is **third** in `v3dot`'s arbiter, behind the
map fetch and the CPU prefetch; and `CpWait` gives up after `VcPolls` = 16,384
polls without reporting anything.

⭐ **§14's poll-budget worry is settled, and it was wrong twice over**
(2026-09-18). The budget is not 39 ms: a poll is ~18 E cycles, so 16,384 of
them is **140 ms**. And `CpWait` does not come near it — `CALLTIME` over a whole
demo run is **2,946 calls, longest 20.5 ms, mean 1.87 ms**, seven times inside
the budget, and the longest is exactly `v3scrl`'s 256 × 320 view copy (81,920
bytes at 0.247 µs). Its carry is now tested rather than thrown away, and the
demo runs clean with the test in.

⛔ **What the investigation did find is worse and older**: every exit in
`DoCopy` used `puls d,x,y,u,pc`, which restores `B` from the `D` pushed on
entry — so `SS.Copy`'s carry was right and its **error number was whatever the
caller had in `B`**. A failed copy reported "Error #012". Fixed by dropping the
saved `D` instead of pulling it.

## 15. `changefont`, and two traps on the way — 2026-09-18

The console's glyph bank from the shell: `changefont uncial` and all 4,800 cells
of the 80 × 60 screen change face, with **nothing repainted**. The mechanism,
the format and the refusals are in `software/nitros9/docs/video-console.md`
("The console's font, changed under the text"); this records what it cost.

**Verified two ways, not one.** The screen — a `dir /dd/cmds` listing drawn
*before* the command still on screen, in uncial afterwards — and the VRAM:
**256 of 256 glyphs in the bank match `uncial`'s bytes exactly** (`VRAMDUMP`).
Plus the refusals: `changefont nosuchface` → `Error #216`, `changefont` alone →
usage and `Error #187`.

### 15.1 ⛔ Adding a field to the middle of VG grew CoArm by two bytes

`VG.F3Buf` and `VG.F3Src` went in beside `VG.WBuf` and the build failed with
*"coarm is more than the two blocks ArmIO maps it in"*. Nothing in CoArm
changed: the new fields moved **every VG offset after them**, two of CoArm's
`,y` operands crossed the 8-bit indexed boundary and took a byte each, and
CoArm — which is **16,383 of 16,384** — would not link. ⚠ **New VG fields go
at the END of VG**, and `armvid.d` now says so where they are.

### 15.2 ⛔ The `os9` macro resets lwasm's local-label scope

Five `Undefined symbol x@` errors, every one a `@` label referenced across a
system call. `v3drag.asm`'s `VErr` and `Exit` are global for this reason;
`changefont.asm`'s `Usage1`, `RErr`, `Short`, `Say` and `Err` now are too, with
the reason written where they are defined.

### 15.3 ⚠ Two hours of the debugging was the test harness, not the machine

A hand-written `typed.txt` used `\n`. **OS-9 wants `\r`** — the shell echoed
every line and ran none of them, the prompt returned instantly, and the run hit
its wall clock with `frames 0`. It read exactly like a hung machine, and I
looked at the ROM first. ⭐ **What settled it was running the known-good ROM
through the same harness** and getting the identical non-answer: the harness was
the variable, so the harness was the bug. `session3.py`'s own `typed.txt` is
`\r`-terminated and always was.

### 15.4 ⚠ `CALLTIME` cannot see CoArm — so the toolbox is still unmeasured

`CALLTIME=CoArm+$37B0` answered `0 calls, the module never appeared`, twice
(the module name is case-sensitive, and fixing that changed nothing).
`calltime_resolve()` scans **task 0's map** for a module header, and CoArm is
mapped into ArmIO's two block windows only *while a call runs* — the resolver
polls every 65,536 instructions and never lands inside one. The timing arm also
requires `m->task == 0`.

⚠ **Superseded the same day by §16, which measures it.** What stood here was
arithmetic — ~165 ms for a 19-character line, ~9 ms a character — and it was
**40% low**. The route that does not need the emulator changed is a bench:
`video3/bench/run-v3text.sh`.

## 16. ⭐ What a toolbox text call costs, measured — 2026-09-18

The first measurement of `tbox.asm` in this repository. `video3/bench/run-v3text.sh`
boots NitrOS-9 (the toolbox is only reachable through CoArm's `ESC $6A`, so there
is no bare-metal route), copies streams of **25 identical calls**, and times them
off the serial console's own timestamps.

⛔ **Every stream is timed TWICE, once to the window and once to `/nil`**, and
the difference is the drawing. What that subtracts is `copy`, RBF and SCF walking
the same bytes — which scales with the file, so the 40-character stream would
otherwise have looked slow for a reason that has nothing to do with text.

| | measured |
|---|---|
| a toolbox call that draws nothing (`Rect`) | **13.58 ms** |
| a `Text` call of one character | **23.87 ms** |
| ⭐ each further character | **11.52 ms** |
| a 40-character line | **473 ms** |
| a 19-character line | 231 ms |

⚠ **The per-character figure is a SLOPE**, taken between two lengths, not a
total divided by a count: a call's fixed cost is most of a short line. The check
holds the shape rather than the value, and one of its claims is a cross-check
that was not tuned — 20 characters measured **246.48 ms** against **242.79 ms**
predicted by the line through 1 and 40.

⭐ **And it settles §13's open question.** At 11.52 ms a character, a 40-character
line is 473 ms; its ~885 `VDATA` bytes at 16 E cycles each are **6.8 ms — 1.4%**.
So the text path is CPU-bound by ~70×, and the emulator charging nothing for a CPU
VRAM write is the right answer *here*, where it was wrong by 3.1× for the copy
engine (§14). The cost is `GRow`, the `KEY` fill and `BlitRow`'s run scan — three
loops of ~25 cycles a byte over the whole text box — and per-run `RowPut` setup at
~500 cycles for 2.1 bytes a call.

⚠ **This is why the desktop takes seconds to draw**, and it is the number to beat
if it ever should: the About window's four lines are ~1.3 s between them.

### 16.1 ⭐ Where the 473 ms goes — the split

Four more streams, and the decomposition closes to within 0.3%: `ESC $34` is a
no-op CoArm parses and throws away; the same `Text` call at `y = 600` composes
every row and is then clipped away by `BlitRow`, so it is **composition without
the card**.

| a 40-character line, 473.26 ms | ms | share |
|---|---|---|
| the call's floor, before any glyph | 11.14 | 2% |
| parsing its 40 payload bytes | ~40 | 8% |
| composition — `GRow`, the `KEY` fill, the run scan | ~228 | **48%** |
| the card's half — `RowPut` setup and `VDATA` | 194.47 | **41%** |
| of which `VDATA` pixels | 6.8 | **1.4%** |

Per character **~1.0 + ~5.7 + ~4.9 = 11.55 ms** against a measured slope of
**11.52**. `ESC $34` alone is **2.69 ms for three bytes**, so CoArm's escape path
is **~1 ms a byte** — the same order as §11's 2.7 ms a character on the console,
and the reason a call's floor is 11 ms before it draws anything.

⭐ **It reorders the optimisation list.** ~188 ms of the card's half is per-run
`RowPut` setup, ~395 runs at **2.1 bytes a call**, and those runs exist only
because the text is transparent. **Opaque text — one run a row, 395 calls
becoming 17 — is the single biggest software win**, not the modest one it looked
like before the split. `video3/docs/keyed-copy.md` carries the rest.

---

## 17. ⛔ The window drag's leftover, and `Vacate` in closed form — 2026-09-18

The backing-store drag (`v3drag.asm`) left two kinds of debris beside the
window's title tab. Both were in `Vacate` — the routine that puts back the
part of the desktop the window has just stopped covering — and both were the
same mistake twice: **working the L-shape's difference out by hand, case by
case, instead of writing it down.**

### 17.1 ⛔ `MaxStep` was a hand-written 8 against a path whose longest step is 12

`InB` re-bases the backing region *before* the window leaves it, because `NewB`
takes the hole — the background under the window — out of the **old** store,
and the old store only has it while the window is inside the old region. Its
margin therefore has to be at least the longest step the path can take.

It was `Step equ 8`, left behind from when the figure-8 was quantised to an
8-pixel lattice. The smooth path that replaced it samples the curve 300 times
and moves by whatever the difference is — **up to 12 pixels**. So the window
could overshoot the region by 4, the hole came back from outside what had been
saved, and the store filled with black: black lines beside the tab, flickering
from **188 s** and stuck by **194 s**.

⚠ **The fix is that the constant is no longer written by hand.**
`video3/bench/mklegs.py` emits `MaxStep equ <the longest delta>` immediately
above the leg table it generates, so the margin cannot drift from the path
again. Changing the curve changes both in one run.

### 17.2 ⛔ And the white staircase: the notch rectangle was one case short

Under the black lines was a second artefact that survived them — a diagonal
run of **white** pixels climbing up and to the right of the title, one small
mark a step, permanent once drawn. White is the tab's right bevel.

The hand-worked `Vacate` restored, for a step `(dx, dy)`:

- one strip per axis that moved (correct), and
- the tab's right edge over `TabH` rows, and
- the "notch" beside the tab over `dy` rows **starting at `TabW`**.

On a **down-left** step (`dx < 0, dy > 0`) that leaves `|dx| × dy` pixels at
`(TabW + dx, TabH)` — inside the old body, covered by neither the new tab nor
the new body — untouched. Up to 5 × 8 pixels, once a step, along the whole
down-left arc of the figure-8.

⭐ **It has a closed form.** Write `OB` for the old bounding box, `NB` for the
new one and `N` for the notch beside the tab at the **new** position. The
window is `NB \ N`, so

```
old-L \ new-L  =  (old-L \ NB) ∪ (old-L ∩ N)  ⊆  (OB \ NB) ∪ (OB ∩ N)
```

`OB \ NB` is one strip per axis that moved — the two the old code already had
right — and `OB ∩ N` is **one** rectangle:

```
x = pwx + dx + TabW          w = WinW - TabW - max(0, dx)
y = pwy + max(0, dy)         h = TabH + min(0, dy)
```

Three copies, never four, and no case analysis past the sign of each delta.

⚠ **The superset costs nothing**, which is what makes it worth taking. A pixel
in `OB \ NB` or `OB ∩ N` that the old window did **not** cover is desktop, and
the store holds desktop there — restoring it writes what is already on the
screen. Only the pixels that were window change. ⚠ And `Vacate` still runs
**before** `DrawW`, because the notch rectangle is at the new position and can
fall inside the old L; restoring it afterwards would erase what was just drawn.

⭐ **The lesson is the one this repository keeps paying for in a different
costume**: a difference of two shapes enumerated by hand has as many cases as
the author remembered, and the one that is missing is invisible until it is on
the screen. `w` and `h` above are positive for every step this path can take —
`WinW - TabW - MaxStep` and `TabH - MaxStep` — which is a property of the
formula, not of a case list.

### 17.3 The BBS field is the palette entry, not 2,000 dithered cells

Unrelated, same day: `v3bbs` drew its background by filling all 25 rows with
CP437's light-shade block in blue, the way ANSI art has to fake a mid-tone when
it only has sixteen colours. gruvbox's background is `#282828`, and **this card
has a palette** — `TxAnsiP` already puts `#282828` at index 0 and `PalRange`
loads it again. So the field is simply the background colour: the same grey, no
dither texture behind the colour tables, and **2,000 fewer cells to draw**
(the stream went 8,299 → 6,127 bytes).

---

## 18. ⭐ Paint, rebuilt from the bare-metal show — 2026-09-18

The brief was to make the NitrOS-9 Paint scene do what `software/demo`'s
desktop show does between **17 s and 48 s** — the wider canvas, the shapes and
fills, the type, the band of colour, the scrolling — without the wave, and
with three things the old show did not have: a **vertical** scroll, a picture
opened through a **Choose File dialog**, and that picture **dragged round a
circle** and put back. Then a close box, and the desktop again.

### 18.1 ⛔ Paint has a screen of its own, and that is what makes the close box work

Everything else in this demo is a window on the desktop's screen. Paint is now
a NitrOS-9 **screen** (`DWSet` style `$13`), and the reason is the last item on
the list: a full-screen window over the desktop can only be *closed* by
redrawing the desktop, which takes ten seconds. A screen's pixels live in a
DRAM store when it is not displayed (`ca_scr.asm`), so `DWEnd` on Paint hands
the display back and **the desktop is simply there again**.

⛔ **And a new screen comes up in CoWin's own palette.** Every colour in
`v3show.py` is an index into the *toolbox's* 256; `v3desk` loads them with the
toolbox's `Pal` call for the desktop's screen, and Paint needs its own. Without
that one line the entire window is drawn in somebody else's sixteen — which is
exactly how the first run came out, and it looks like a corrupted palette
rather than a missing call.

### 18.2 The canvas is 320 × 320, and the arithmetic says why

`canvas width + horizontal scroll = 384`, because **384 is the margin** —
columns 640-1023 are the only off-screen store the copy engine can reach
(`plan.md` §4), so the document cannot be wider. The old scene spent 256 on the
canvas and 128 on the pan; this one spends **320 on the canvas and 64 on the
pan**, and takes the reveal it lost horizontally back vertically: the document
is 480 rows against a 320-row canvas, so the **vertical scroll is 160 rows** and
brings in a whole band of picture.

⭐ **So the page the viewer paints is the document's first page.** `v3scrl`'s
first act is now one `SS.Copy` of the *canvas into the margin*, over a corner
that `mktbox.py` deliberately leaves white. Scrolling away from it and back
brings the same pixels home: measured over the whole scroll, **317 of 629
recorded frames are byte-identical to the frame before it started**, and the
last one is exact.

⚠ **The ROM picture is therefore composed for an L, not a rectangle.** All that
is ever seen of it is the 64 columns past the canvas and the 160 rows below it,
so the sun sits in the right-hand strip and the range, the water and the caption
are all below row 320.

### 18.3 ⛔ `window()` CLEARS WHAT IT FRAMES

`tbox.asm`'s `TWin` fills the frame with `C.Panel` before it draws the border
(`Fill 1,1,-2,-2`). So "rename the window" is not a patch — a title changed after
the fact takes the canvas, the notes and the palette strip with it. Both the
original draw and the reopen therefore go through one `paint_chrome()`, and they
differ only in the title and the words.

⚠ **The close box is the same trap from the other side.** Pressing it must not
call `window()` again, or the picture goes. It is the 12 × 12 bevel `TWin` puts
at `(7, -15)` of the frame, so pressing it is one sunken bevel in that place —
**14 bytes**.

### 18.4 What the page is drawn with

All of it is CoArm's own primitives, on the canvas, with the tool lit in the
palette as each is used:

| | |
|---|---|
| the filled rectangle | `Bar` and `Box` |
| the hatched one | `PatDef` + **`PatBar`** — the brick pattern, orange on pale |
| the triangle | **`Poly`**, two chains of two |
| the star | **`PolyPat`**, three times (see below) — ⚠ with the ink the *sparse* colour, because pattern 4 sets one bit in eight, so black on gold is a gold star ruled with diagonals and the other way round is a black star with gold threads |
| the type | the ROM toolbox's Noto Sans |
| the band | six `Bar`s, left to right |

⚠ **Both polygon chains run down, and must start and finish on the same row.**
CoArm walks y from the left chain's first vertex to its last and wants an x from
each chain on every row of it.

⛔ **AND A POLY IS ONE SPAN A ROW, WHICH A FIVE-POINTED STAR IS NOT.** Below
the star's bottom inner vertex every row is **two** runs, one down each leg, and
a left-chain/right-chain polygon cannot say that. Handed the ten vertices as one
pair of chains, CoArm paints between them: the notch between the legs fills
solid and the star comes out with a webbed foot. Nothing is wrong with the model
or the card - they implement the same rule - the shape being asked for was
impossible.

So `v3show.star()` cuts across that vertex and returns **three** chain pairs, the
body and a leg each, drawn with one `PatDef`; the pattern tiles from the working
area's origin rather than from the shape, so there is no seam where they meet.

⚠ **The general rule: decompose at every vertex where the silhouette splits,
and check it against `vgmodel.poly_spans` before running the machine.** That is
CoArm's own span rule in twenty lines of Python, and it showed the webbed foot
in a second - where seeing it on the card costs a twenty-five minute demo run.

⚠ **Nothing clips to the canvas.** The window's working area is the whole
screen, so every coordinate in `stream_draw` is asserted into the canvas in
Python.

### 18.5 The drag is the window drag with the hard half removed

`v3grab` walks the picture round a 50-pixel circle. Paint's page is **a
colour**, so there is no backing store to keep: a step is one `SS.Copy` out of
the margin and at most **one white `Bar` per axis that moved**. The copy goes
first — each strip is outside the new rectangle by construction, so painting
them after cannot erase it, and the picture is never absent from the page,
which is the defect §17 spent a day on.

⭐ The circle comes from `video3/bench/mklegs.py circle 25 56 emit`, the same
generator that emits `v3drag`'s figure-8: it eases out from the centre to the
rim, goes round once and eases back, so **the last step lands exactly on the
first** — and the generator asserts it.

⛔ **One 6809 bug worth recording**: the run length cannot live in `B` while the
two deltas are read, because `SExt` clobbers `B`. A count of 3 becomes whatever
the last delta was. It goes on the stack.

### 18.6 ⛔ `DWEnd` frees a screen; it does not show another

The close box appeared to work and then showed a **flat blue screen** for a
second. `ca_scr.asm`'s `ScrFree` clears `CG.Disp` and stops: with no screen
selected the card simply keeps whatever pixels were last written to it, and the
next thing to draw is what you see. ⭐ **It takes a `Select` on the desktop's
window** — `display 1b 21 >/w3` — and then the desktop is back, icons, Tracker,
Deskbar and all, out of its DRAM store.

⚠ Worth stating as a rule, because the symptom is so misleading: *closing* a
screen and *showing* another are two operations, and a demo that does only the
first looks like a driver that lost the other screen's pixels.

### 18.7 What it costs

The scene runs from **257 s to 339 s** of machine time and the whole demo is
now **369 s** against 289. Where it goes:

| | s |
|---|---|
| the chrome, and the page into the margin | 12 |
| the page painted, shape by shape | 17 |
| the two scrolls, out and back | 8 |
| the File menu and the Choose File dialog | 8 |
| `parrot.img` opened: the repaint and the picture into the margin | 11 |
| the circle, 76 steps | 17 |
| the hold, the close box, and the desktop | 8 |

⚠ **The two 11-12 s repaints are the toolbox's escape path, not the card.**
§16.1 measured it: CoArm's `ESC` handling is ~1 ms a byte and a toolbox text
call's floor is 11 ms before it draws a glyph. The palette strip alone is 38
calls. Nothing here is the copy engine, which does the scroll's whole document
and the drag's 76 pictures inside one of those seconds.
