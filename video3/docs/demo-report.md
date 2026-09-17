# video3 — the NitrOS-9 demo, and what it took

**Started 2026-09-16, overnight.** A running log, newest findings appended. The
brief: boot NitrOS-9 in 80×60 text on video3, switch to 640×480 bitmap, and build
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
