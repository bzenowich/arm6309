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

⭐ **`ATTR` is the VGA attribute byte**: b7–4 background, b3–0 foreground, sixteen ANSI
colours crossed with themselves — exactly 256 pairs, which is exactly what the LUT's high
half holds. So the 256-pair design in plan §2 *is* the CP437/ANSI model, and no mapping
layer is needed between them.

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

`v3dot` is now **117 / 128 cells, 52 / 64 I/O, 4 cascades**, and `v3dot_tb` reports
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

⚠ **The world renders and scrolls; the hero does not.** `overworld` builds the hero's
fifteen tiles a tile a frame by **reading the background out of VRAM** and compositing,
and that read path still uses `video/`'s bank geometry. The hero shows as a black
square. That is the one scene in the demo that is not finished, and it is a known,
located cause rather than a mystery.

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
| the **overworld**, scrolling on an accelerating ramp | ⚠ world yes, hero no (§7) |

### What I would do next, in order

1. ⛔ **The hero's tiles** (§7) — the one unfinished scene, and the cause is located.
2. ⛔ **`video3_card.v`**, so the Verilator stage reaches plan §14 item 8's cadence and
   the brief's "how it interacts with our mainboard". `v3dot_tb` proves the raster; a
   card wrapper is what proves the card.
3. ⚠ **The drag leaves a title-bar artefact** on the last leg. The staging is correct
   for the cases I traced; this is not yet explained.
4. ⚠ **256-colour text.** `ATTR` is the VGA byte, so `SGR 38;5;n` above 15 is masked to
   four bits in character mode. 256 foregrounds needs a second `ATTR` scheme — the LUT
   already holds 65,536 entries, so it is a software decision, not a hardware one.
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
