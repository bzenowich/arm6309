# `pcs` — Pinball Construction Set on the arm6309

[`billbudge/PCS_Atari800`](https://github.com/billbudge/PCS_Atari800) is Bill Budge's 1983
*Pinball Construction Set* for the Atari 800, MIT-licensed: **11,538 lines of 6502** across
sixteen files, vendored here at [`software/pcs/reference/pcs-source/`](../reference/pcs-source/). It is four
programs sharing a screen — a direct-manipulation **editor**, a **magnifier**, a **wiring
kit**, and a **simulator** that plays the table you built — in **320 × 192 at 1 bpp** (ANTIC
mode F) and a 48 KB address space it overlaid three ways (`EDIT`, `WIRE` and `DISK` all
`ORG $A000`, swapped by `SWAP.s`).

⚠ It was cross-developed **on an Apple II** and downloaded over a parallel cable
(`MAKE1`–`MAKE3` are Applesoft `BLOAD` scripts, `DOWNLOAD.s` is the link), which is why
`ORG` is the Atari address and `OBJ` the Apple staging address, why the comments say "READ
THE PADDLES" over code that reads a joystick, and why the three paint colours are the Apple
II's hi-res bit patterns. ⭐ The Apple II sources
([`billbudge/PCS_AppleII`](https://github.com/billbudge/PCS_AppleII)) are worth reading
beside them: the physics is **byte-for-byte identical** between the two, which is how
several readings here were confirmed.

Here it is a NitrOS-9 Level 2 program on **640 × 480 chunky 8 bpp** (`VMODE` 11) with a
256-entry LUT, a copy engine, a span writer, one hardware sprite and a PS/2 mouse, forked
from `desk`'s **Pinball** icon like `monster` and `tilescroll` from theirs (§8).

---

## 1. ⭐⭐ The WORLD is the original's, and only the RENDERER is doubled

`RUN.s` tunes the ball with four tables (`INITWORLD`, `RUN.s:2170`), eight levels each,
each patched into the code as a self-modifying immediate:

```
GRAVTBL HEX FF7F3F1F0F070301     gravity — a MASK: apply -1 to BDY when (tick & mask)==0
TIMETBL HEX 302018100C080401     speed   — the WAIT between ticks, so the TICK RATE
KICKTBL HEX 04080C1018202838     kick
ELASTLO HEX 80400000C0804000     elasticity — eight ENTRY POINTS into one response
ELASTHI HEX 8383838382828282       table, which is how one table gives eight curves
```

Gravity is not an acceleration constant at all — it is *how often* you subtract one from
`BDY`, terminal velocity clamped at `$D1`. ⚠ **Every one of these is counted in TICKS**, one
pass of `PLAY`'s object walk, and a tick is not a frame (§5b's last paragraph): at the
default gravity 5 the ball gains 1/256 row a tick², so how hard it falls is set by how
many ticks a second the machine runs. Position is pixels plus an 8-bit accumulator.
Every coordinate in the program is a **single byte** (table x 0–159, y 0–239 here).

**So the simulation, the database and the file format stay in the original's units, and the
renderer multiplies by two on the way to the screen.** `PC.Scale` applies nowhere else.

| | |
|---|---|
| ⭐⭐ **The port is provably the original** | every number is exact integer arithmetic, so a Python transliteration can be the gate and the 6809 is required to produce the **identical ball trajectory, frame for frame**. Not "it feels right" — it is the same simulation |
| ⭐ **Nothing has to be widened** | otherwise all 43 part templates, the span database and the file format need 16-bit coordinates |
| ⭐ **Nothing is chunky** | vertices sit on even pixels, but the scan converter runs at 2× with doubled slopes |

## 2. ⭐⭐ The span database is a DISPLAY LIST, because this card cannot XOR

⛔ **Every composite in PCS is an XOR** — the cursor, menu highlights, the drag preview,
polygon fill, wires, vertex dots, even the brush (which repaints by filling with
`old ^ new`, `EDIT.s:1151`). Drawing a thing twice erases it, and that is the entire undo
and animation mechanism.

⛔ **video3 has no read-modify-write.** The span writer writes `WFG`/`WBG`; the copy engine
copies. There is no raster op.

⭐ **It does not need one.** `PPAK.s`'s scan converter already maintains exactly the
structure a repaint needs. Its output is **not just a picture** — it is a per-scanline,
z-ordered list of spans with the object index and the edge slopes:

```
record (4 bytes)  x_left | object index | x_right | (slope_right << 4) | slope_left
```

in draw order, later on top. That is a retained display list, a hit-test structure and the
collision model at once. **Repainting scanline *y* is walking its records in order and
emitting one span-solid write per span**, at the object's `FILLCOLOR`. Damage is a row
range; nothing is ever XORed and nothing is saved behind.

| XOR idiom in the original | here |
|---|---|
| cursor (`XDRAWCRSR`, save-behind) | ⭐ **the hardware sprite** — two register writes |
| drag preview (`DRAWOBJ` twice a frame) | ⭐ **the copy engine, keyed on index 0** (§8): the part drawn once, alone, in the margin, and each move a save-under and a transparent copy. A vertex drag is a rubber band whose pixels are read back first |
| menu highlight (`SELECT` XOR-inverts a rect) | repaint the rect in a highlight colour |
| brush repaint (`old ^ new` fill) | ⛔ **store the new colour and redraw.** `PAINTOBJ` stores `new XOR old` and XOR-blits; the Apple II diff proved that cannot survive 256 colours |
| animation (`ADVANCE`/`RETREAT` step a bitmap pointer and XOR-draw) | ⭐ a **frame INDEX**: `L[8] & $7F` is exactly what the pointer encoded |
| `$55` over `$AA` → `$FF` | ⛔ gone, and not missed — a 1bpp dither artefact |

⚠ **This is the one place the port is an adaptation rather than a transliteration**, and it
is forced by the hardware. The semantics it preserves are: draw order is object order,
index 0 is the background `BPOLYGON`, and `FILLCOLOR = 0` means unfilled-but-solid.

⛔ **The database's LAYOUT is not the original's either.** `PPAK.s` keeps the records in a
gap buffer between `membtm` and `$7A40`, with `MAKEHOLE` sliding the hole about. The port
uses a per-scanline singly-linked list with a free list: the same content, O(1) appends,
one walk to remove an object, and `MAKEHOLE`, `GETSCAN`, `MOVEUP` and `MOVEDOWN` deleted
outright. The bench compares the database's **content**, so the layout is free.

## 3. The layout — ⭐ a 160 × 240 world, which at 2× is exactly the screen

⚠ **The table is 160 × 192 in the original, not 320 × 192.** `TABLEB` is x 0–159 and `KITB`
is x 160–319 (`EDIT.s:1376`), confirmed by `PPAK.s:774`'s `LDX #159` and `RUN.s:1864`'s
`X2 >= 153` wall clamp.

**The table gets the extra rows — a 160 × 240 world:**

```
 x 0..319      THE TABLE          160 x 240 world at 2x  = 320 x 480, the full screen height
 x 320..639    the kit panel      160 x 192 at 2x        = 320 x 384
 y 384..479    ⭐ ...which leaves 96 rows UNDER the kit panel for a permanent
               score / bonus / player strip
```

⭐ The taller table costs nothing and fixes something: the original had **no status area in
the editor** and had to blank the parts bin during play to print `BONUS X`, `BONUS` and
`PLAYER 1` into it (`RUN.s:1958`).

⚠ `y` is still one byte, so no coordinate widens. What grows is `PBDX[192] → [240]`, the
scanline tables and the drain test's `LASTY`. ⚠ A table authored for a 192-row world loads
into the top of a 240-row one — worth a version byte in the file.

⚠ **`PC.TW-7` is 153, and the original is not self-consistent about it.** `RUN.s:1864`'s
wall clamp and `CHECKVERT`'s right-hand gap both say 153 in a 160-wide world, while
`PPAK.s:774`'s right edge says 159. The Apple II version is self-consistent at 154/153, so
this is a port slip in the *original*; it is reproduced, written as one constant.

## 4. What the machine gives us, and what it takes away

| | |
|---|---|
| ⭐⭐ **The original's 1bpp art renders VERBATIM, in colour** | `WM.Mask` takes the CPU's written byte *as a bitmap* and expands it to 8 pixels choosing `WFG`/`WBG`; `WM.Sprite` writes **nothing** for a 0 bit. So `DRAWBITS`, `XOFFDRAW` and `MASKS` collapse into one span write — **8 pixels a store, with transparency, in any colour** |
| ⭐⭐ **A third of the 6502 does not port at all** | `HDIV8`/`HMOD8`, `LEFTMASK`/`RIGHTMASK`, `XOFFDRAW`'s shifter and the 6,144-byte `GPAK.OBJ` table of x÷8, x mod 8 and row addresses. **Chunky 8 bpp has no shift**: `WPTR` is a byte address *is* a pixel address, and a row is `(y << 10) + x`. The port carries ONE `px` where the Atari had `HDIV8` and `HMOD8` |
| ⭐ **The screen is not in our address space** | the Atari spent 7.5 KB of 48 on the framebuffer and had to overlay `EDIT`/`WIRE`/`DISK`. **We have the whole 64 KB, and no overlays** |
| ⭐ **The margin is 196 KB of free VRAM** | columns 640–1023 × 512 rows. The editor composes its repaints there, and a dragged part and what is under it (§8) |
| ⛔ **No XOR** | §2 |
| ⚠ **A click can be missed** | a polled loop that repaints or scan-converts cannot see the button while it works, so the editor **queues** it: the left button's changes are sampled once a frame inside `PCWait` and once a scanline inside the scan converter, and `UIPoll` hands them out before it looks at the live mouse (§8) |
| ⭐ **The margin below row 320 is ours as well** | the ROM toolbox's glyph strike (column 640, rows 320–472) belongs to the screen it was built for and is dropped whenever the display screen changes. `pcs` `DWSet`s a screen of its own and writes no window text through the toolbox, so no strike is ever built there — and the kit's cache (`KitBin`, §8) lives at columns 640–1023, rows 320–481 |

## 5. The data

**The record** (`GETINFO`, `PPAK.s:209`) — kept exactly, with `FILLCOLOR` reinterpreted:

| Off | Size | Field |
|---|---|---|
| 0 | 1 | `OBJID` — `1` POLYGON, `2` BPOLYGON (the complement/backdrop, always object 0), `3` LIBOBJ |
| 1 | 1 | `FILLCOLOR` — ⭐ a palette index; `0` = unfilled but **solid**. ⭐ On a `LIBOBJ` it is the colour of the part's **art**, and `0` is `UI_PART` — its polygon is always drawn as unfilled |
| 2 | 1 | `VRTXCOUNT` — 3…63 |
| 3 | n | X coords, 1 byte each |
| 3+n | n | Y coords |
| 3+2n | 16+ | the library tail, `L` |

**The library tail `L`**, and ⚠ **the offsets are the original's** because every part proc
indexes them with a literal:

| | |
|---|---|
| `L[0..1]` | was the bitmap pointer; **unused here** (§2) |
| `L[2]` | the art's top row — ⚠ a flipper MOVES it as it sweeps |
| `L[3]` | the art's left column. ⭐ One number where the Atari had `HDIV8`/`HMOD8` |
| `L[5]`, `L[6]` | height in rows, width in bytes |
| `L[7]` | was the frame's byte length; **unused — except for the BALL, where it is the idle counter** |
| `L[8]` | ⭐ **the state byte**, and the animation counter. Bit 7 is a DIRECTION flag and also "this part fired", which is what the wiring kit reads |
| `L[9]` | b7 unwireable, b6–4 sound, b3–0 score |
| `L[10]` | ⛔ **the part TYPE ID**, where the 6502 had three addresses (§5b) |
| `L[16..22]` | the ball's own record: `BSTAT, X1, Y1, BDX, BDY, BXACC, BYACC`. Other parts use `L[16]` as a second state byte |

**The database** heads with `LOGIC[24]` (six 3-input AND gates × 4 bytes) and `WSET[4]`
(gravity, speed, kick, elasticity), exactly as it heads the Atari's `$4B00` and for the same
reason: they are the first bytes of a saved table. `PBDATA[0]` is the object count **and**
the offset from `PBDATA+1` to the first record, which is why the walk needs no index.

⚠ **Keep the original's limits** — 127 objects, 63 vertices, **8 active edge records**
(`PPAK.s:568`), 32-byte span-DB headroom with rollback on overflow. They are part of what
the construction set *is*.

⛔ **And the eight is PER OBJECT, not per scanline.** The active list belongs to the polygon
being scanned, so one polygon may have four spans on a line and the next gets its own eight;
there is no cap on spans per scanline anywhere in `PPAK.s`. ⚠ This spec and the bench both
claimed otherwise until the edit gate went looking for a refusal and could not provoke one.

**The colour picker** replaces `EDIT.s`'s three paint pots (`$FF`, `$55`, `$AA`,
artefact colours on the Atari). It is a 12 × 10 grid of palette entries **32–151**
(`pcspal.PICK`): a row of greys from white to black, then nine rows of twelve hues from
dark to light, sampled from the reference picker supplied on 2026-09-24. Cells are 8 × 8
card pixels, centred in the kit panel under the tool column (x 432–527, y 360–439), and the
current colour carries a one-pixel frame, white on a dark cell and black on a light one.
A white box, a pixel thick and two pixels clear of the cells, surrounds the grid. A
table's `FILLCOLOR` is the entry number, so ⚠ **entries 32–151 are file format** and are
append-only. Entries 1–3 stay the translation of an imported table's dither masks, and the
editor starts on white (cell 0), the original's `COLOR = $FF`.

**The tool icons are redrawn** (`pcsicons.py`, 2026-09-24) at the card's own resolution,
white on a **black** panel: the original's were drawn for one Atari hi-res pixel a world
unit and came out doubled. Each is centred in its tool's `CMDMENU` rectangle, so the
picture and the hit test are the same rectangle.

**The tool column is `CMDMENU`'s less its three paint pots** (`pcskit.TOOLS`): HAND,
POINTER, SCISSOR, HAMMER, BRUSH, then PLAY, MAGN, WORLD, WIRE and DISK, and the index
in that list is the tool (`ED.*`). The pots — WHITE, GREEN, VIOLET — chose the colour,
which is the picker's job here, so they are gone from the column, and the five tools
under them sit 30 world rows higher, in the room they took; `CMDMENU`'s gap above PLAY
is kept. The bin's
parts keep their own art, because it is also what the table shows; the bin's polygon entry
is an icon and is redrawn too.

⭐ **`pcs` is a resident core and four libraries** (`pcscore.inc`, 2026-09-24). A process
here has seven 8 KB slots (the eighth is the kernel's), and one module had filled them.
The **core** (24.5 KB, three slots — ⛔ `pcs.asm` refuses to assemble past them, because a core in a fourth slot leaves no room to map a library and every run says `PCS-NOLIB`) keeps what the frame loop calls sixty times a second:
the simulator, the scan converter, the drawing primitives, the game. The **libraries**
are modules of their own, each under 8 KB, paged through **one window slot**:

| | library | exports |
|---|---|---|
| 1 | `pcsed`: the editor's database operations, the templates, the bench's edit script | `PESnap`, `PERoll`, `PERun` |
| 2 | `pcsui`: the editor's screen (the kit, the icons) and its event loop | `KitDraw`, `IconDraw`, `KitBin`, `EdLoop` |
| 3 | `pcsfl`: tables in and out (the file layer, `Build`, the built-in tables) | `PFArg`, `Build` |
| 4 | `pcsmg`: the magnifier and the WORLD panel (§8), the colour picker, the kit panel's redraw, and mode 3's text screen | `MgAct`, `MgOn`, `MgShow`, `MgDump`, `PickDraw`, `KitPnl`, `TxTest`, `WoLive` |

`LibInit` loads them (`F$Link`, else `F$Load` from the execution directory), reads each
one's block out of the process's own DAT image (`F$GPrDsc`), and unmaps it (`F$ClrBlk`),
which leaves it linked and in memory. A core call to a library export lands on a
generated stub that maps the library in (`F$MapBlk`, skipped if it is already there),
calls the entry, and **maps back whichever library was there before**, so a library can
call the core that calls another library and return to its own code. A library calls the
core through `cvtab`, a table of addresses in the shared data area, by way of a
four-byte trampoline per routine (`pcsstub.inc`), so its source is unchanged. `LibFini`
unlinks all four on every exit.

⛔ **The window is one fixed address**, and every return into it depends on that: there
is exactly one free slot, and `LibMap` refuses (`PCS-NOLIB`) if `F$MapBlk` answers
anything else. ⛔ **The stack is never paged**: it is at the top of the data area.
⚠ **Two lists are file format between the modules**, `pcslxp.inc` (the exports) and
`pcscve.inc` (the core routines a library may call). Each is one source expanded two
ways, and both are append-only. ⚠ **A library over 8 KB fails to assemble**, and a card
must carry all five modules: a card with `pcs` alone answers `PCS-NOLIB`.

**The art.** `BITMAPS.OBJ` (1,792 bytes) with the offset table at `RUN.s:100`. ⭐
`mkpcs.py` reads all of it straight out of the original sources, doubles each byte's bits,
and emits the art bank — **the parts are Budge's drawings, not redrawn ones**.

⭐⭐ **The free-hand layer is a whole 160 × 240 bitmap in RAM of its own** (`pcsdraw.inc`'s
`Ly*`). The Apple II's magnifier toggled bits of the hi-res screen, and the screen was the
drawing; here the span database is the picture (§2), so what the magnifier draws is a layer
composed **over the spans and under the parts' art** on every repaint. It is eight 8 KB
blocks from `F$AllRAM` (`LyInit`, at `Build`), 32 world rows a block at 256 bytes a row, and
`lycnt[240]` counts each row's pixels — so a repaint skips an empty row without mapping it,
and a row's page is cleared when its count leaves 0 rather than all 64 KB at start-up.
⛔ **There is no slot to give it**: the layer's blocks are paged through the **library
window**, by core code only (`LyOpen` … `LyClose`), which puts the caller's library back
before it returns. No library may be called between the two. `PCPaint` opens once per
repaint and maps a block only when the row crosses into the next 32. `LibFini` empties the
window before `F$DelRAM` gives the blocks back. **Every pixel of the table can be drawn
on**; there is no capacity to refuse.

⭐ **A table file carries its layer after the payload**: `"PL"`, a big-endian count
(≤ 38,400), and `(y, x, colour)` triples. The loader reads them in chunks of 64, refuses a
count over 38,400 or a triple off the table or in colour 0 (`PF.ELay`), and a file with
nothing after the payload has no layer — so every table written before this reads as it
did. `PFSave` writes the section in row order.

### 5a. The simulator

**The ball** is a 5 × 5 disc; `BDX`/`BDY` are signed bytes in **1/32 px per tick**, clamped
to ±63; `BXACC`/`BYACC` are the sub-pixel accumulators. **`BDY` positive is up-screen.**
Motion is one pixel at a time, Y then X, and *the step is only committed when the probe says
clear* — so the ball never overlaps geometry.

**Angles** are 0–31 for a full turn and ⚠ **non-uniform**: `SUB[0..7] = 0, 5.625, 11.25,
22.5, 45, 67.5, 78.75, 84.375°` — crowded towards the axes and coarse at 45, so a ball
rolling along a nearly flat surface gets fine angular resolution where it matters. `ROTATE`
folds into the first quadrant, then does `(x cos θ − y sin θ, x sin θ + y cos θ)` with **two
lookups and no multiply**, out of ⭐ **seven 64-entry cosine tables**. The same tables are
the elasticity curve: `ELAST[vn]` is `vn · 4 · cos a` and `>> 2` makes it `vn · cos a`, so
the slider picks *which cosine*.

⛔ **The quadrant fold applied is the INVERSE of the fold owed**, and only the 180° case is
its own inverse. Using one number for both folds `(12, -12)` to `(-12, -12)`, whereupon
`ROT6`'s ceiling clamps both components to `$3F`.

**Collision** is `CHECKHORIZ` (`RUN.s:1570`) and `CHECKVERT` (`RUN.s:1668`) walking the
scanline's span records. ⛔ **Object 0 is read inside out**: the backdrop is a B-polygon
whose *records* are the open playfield, so the GAPS between them are wall. ⛔⛔ **And
`CHECKVERT` ALTERNATES between its two readings**, at every record where the object changes
— `BEQ BCHECKV2` leaves object mode and `BCHKV5`'s `JMP PCHECKV2` returns to it. Records are
in draw order, so object 0's come **first** on every scanline of a normal table and the
alternation is the only thing that ever reaches an object at all. ⚠ A walk that leaves
object mode for good passes any test whose objects are only met side-on, because
`CHECKHORIZ` has no modes.

`DOVHIT`'s `VLFIX`/`VRFIX` flatten a steep edge to a floor when the ball is falling onto it,
with thresholds 6 and 11 out of the sixteen slope codes. ⚠ That heuristic **is** the game's
feel.

**Each part is three procs and one state byte** — `RUN` (called when `frame & TIME[obj] ==
0`), `INIT` (the wiring's "turn off"), `HIT` (returns carry = "the ball was deflected").
There is no class hierarchy and no message dispatch: twenty-two HIT procs, fourteen RUN
procs, ten INIT procs, and a four-byte record.

⭐⭐ **The flipper is the one part that is not a polygon.** Its collision is resolved against
its **art**, row by row: each of sixteen frames carries a list of (right, left) pairs, one a
row, and the proc finds the row the ball is entering, reads that row's two ends, and only
then decides whether it was touched. The kick is `FLPVCTR` indexed by **where along the
flipper** the ball struck — the tip shot is a table lookup. The right-hand flippers are the
same tables read backwards from `FWIDTH`.

⭐ **The ball is an object like any other** — keyed by `PLAY`, homed by its own `INIT` proc,
and **its home polygon sits in the span database and is not solid**, which is what
`NULLBOUNCE` is for. A port that quietly dropped the ball from the display list would pass
every picture test and renumber the objects underneath every saved table.

**Scores are 9-byte decimal digit arrays.** The add lands on digit 7 while the print runs 8
down to 1, so ⭐ every score is a multiple of ten, exactly as on the machine it is imitating.

**Sound** is one POKEY channel: seven effect sequences of warbling note pairs, 108 bytes of
effects plus 96 of notes. They port as square tones on one channel of the audio card,
keeping the wiring kit's eight-way assignment.

⛔ **There is no tilt and no nudge in the Atari version** — none anywhere in the sources. So
the mouse has nothing to do during play, and the keyboard carries flippers and plunger.

### 5b. The seven known bugs, and what we do with each

A bit-exact gate means the *model* must have them too, so this is an explicit list:

| | |
|---|---|
| `ELASTLO/HI[2] == [3]` (`RUN.s:2188`) | ⭐ **reproduce** — elasticity 2 and 3 behave alike, and that is what the slider did |
| `VRFIX` + rising gives `TTA = 0` where 16 is right (`RUN.s:1811`) | ⭐ **reproduce** — a ball rising into the right of an overhang hovers. Asymmetric, and it is the feel |
| slope code 17 overflows its nibble (`PPAK.s:826`) | ⭐ **reproduce** — it is in the collision data path the gate compares |
| `BOUNCE` returns "hit" even when nothing changed | ⭐ **reproduce** — deliberate for resting balls (`MOVEB9`'s 3-frame re-probe) |
| `EOR #$FF` where a negate was meant (knockers, the spinner) | ⭐ **reproduce** — the reverse kick is one larger, and `-24` gives 11 of spin, not 12 |
| `PUTSP2` does not mask `L[9]` bit 7 (`RUN.s:1330`) | ⛔ **fix** — it reads past a 7-entry table, so the magnet's `$B3` asks for entry 11. `WIRING` masks with `$70` for the same field, which is the evidence it is a slip |
| sleeper stride 22 vs 23 bytes copied (`RUN2.s:416`/`917`) | ⛔ **fix** — adjacent extra balls corrupt each other |
| saved tables hold **absolute 6502 addresses** in `L[0..1]` and `L[10..15]` | ⛔ **re-key by part type id**; the vectors are rebuilt on load. ⛔ The type list is **append-only**: inserting one renumbers every table ever written |

⭐⭐ **And the tick rate, which is not the frame rate.** The original is a busy-wait:
`PLAY` reads the paddle, calls `WAIT(TIMETBL[speed])` and walks the objects, as fast as
that lets it — no VBL anywhere. Gravity, the flipper sweep, every part's `TIME` mask, the
launch and the drain delay are all counted in those passes, **ticks**. Measured off
`reference/pcs.mp4` (the Apple II session; the ball tracked frame by frame through
20:20–24:40) the ball falls at ~700 video px/s², ~415 rows/s² at 1.68 px a row; at
1/256 row/tick² that is **~300 ticks a second** at speed 3, and the fastest falls put a
floor of ~210 under it.

So a game (`PGTurn`, `pcsgame.inc`) is **paced off the card's VBL counter**:
`PCTICKTBL` (`mkpcs.py`'s `tick_rates`, from the Apple's `WAIT` cost
`(26+27A+5A²)/2` at 1.0227 MHz plus a ~2,540-cycle pass fitted to put speed 3 on 300)
gives each speed's ticks per VBL in 8.8 — 114, 184, 237, **300**, 333, 363, 386 and 398
ticks a second — and each pass runs `PBTick` as many times as the VBLs gone owe, then
repaints once over the damage all of them left (`PBPnt`). A pass may claim at most
`PG.MaxV` = 8 VBLs, so a machine that falls further behind slows the game rather than
jumping it. ⚠ **The bench's `Play` (mode 4) still runs one tick a step**, which is what
`pcsobj.py`'s trajectory is compared against; the pacing is the game's alone.

⭐ **A tick takes no damage; the repaint asks what changed** (`PBDiff`, §8). Damage taken
every tick was the union of every position the ball passed through between two repaints,
and at ~30 ticks a repaint that was a 77-row band for a picture drawn twice.

⚠ **Measured on the host emulator in mode 20 on `demo2`** (2026-09-25): 300–313 ticks a
second with the ball on the plunger, and **229–341 through the launch and while the
flippers work**, mostly ~290. A flipper repaint is 118–142 ms and the median repaint
27 ms. The object walk is six instructions a part that does not run (`PBTick`); the rest
is the repaint.

⭐ **The plunger is held and let go**, as in the Apple II session. The left button down
pulls the spring — `PG.Pull` = 3 into `PDL0` a VBL, full at 191 in about a second — and
letting go sets `pfire` for `PG.Fire` passes: `LAUNCHHIT` (`RUN.s:217`) gives a ball on the
plunger `BDY = PDL0 >> 2`, up to 47, and `LAUNCHRUN` lets the spring's picture back. So the
launch speed is proportional to how long the button was held. Under `pbauto` `pfire` is
`BTN0` and nothing else changed. ⚠ `BTN0` is also the left flipper, as the Atari's trigger
0 was, so working that flipper pulls the plunger too; it fires only a ball that is on it.

## 6. Where it lives

```
nitros9/level2/arm6309/cmds/pcs.asm        main, modes, the event loop: THE CORE
nitros9/level2/arm6309/cmds/pcscore.inc    ... loading and paging the libraries
nitros9/level2/arm6309/cmds/pcsvars.inc    the data area, shared by all five modules
nitros9/level2/arm6309/cmds/pcslxp.inc     the libraries' exports     (append-only)
nitros9/level2/arm6309/cmds/pcscve.inc     the core's, to libraries   (append-only)
nitros9/level2/arm6309/cmds/pcsstub.inc    a library's entry table and trampolines
nitros9/level2/arm6309/cmds/pcs{ed,ui,fl,mg}.asm   the four LIBRARIES
nitros9/level2/arm6309/cmds/pcsdat.asm     GENERATED — art, palette, templates, tables
nitros9/level2/arm6309/cmds/pcsdata.inc    the data area
nitros9/level2/arm6309/cmds/pcspak.inc     PPAK.s — scan converter + span DB  (the core)
nitros9/level2/arm6309/cmds/pcsdraw.inc    CDRAW.s — blits, rects, the VRAM streams, the free-hand layer
nitros9/level2/arm6309/cmds/pcsrun.inc     RUN.s — the ball
nitros9/level2/arm6309/cmds/pcsobj.inc     RUN.s — the part procs and the PLAY loop
nitros9/level2/arm6309/cmds/pcsedit.inc    EDIT.s — the editor's database operations
nitros9/level2/arm6309/cmds/pcswire.inc    WIRE.s — the wiring kit                 (step 5)
nitros9/level2/arm6309/cmds/pcsfile.inc    DISK.s — PFLoad and PFSave, the file itself
nitros9/level2/arm6309/cmds/pcsdisk.inc    DISK.s — the DISK panel: the name, the catalogue, LOAD and SAVE (library 3)
nitros9/level2/arm6309/cmds/pcsui.inc      EDIT.s — DRAWKIT, the kit panel, and MAIN, the editor's event loop
nitros9/level2/arm6309/cmds/pcsmag.inc     EDIT.s — MAGNIFY, the fat bits (library 4)
nitros9/level2/arm6309/cmds/pcsworld.inc   EDIT.s — WORLDSTART and DOSLIDE, the four sliders (library 4)

arm6309/software/pcs/bench/pcsasm.py             a reader for the 6502 sources' data directives
arm6309/software/pcs/bench/pcsparts.py           the 43 templates and their art
arm6309/software/pcs/bench/pcspal.py             the palette
arm6309/software/pcs/bench/pcspak.py             PPAK.s — the scan converter, modelled
arm6309/software/pcs/bench/pcsphys.py            RUN.s — the ball, modelled
arm6309/software/pcs/bench/pcsobj.py             RUN.s — the part procs, modelled
arm6309/software/pcs/bench/pcskit.py             EDIT.s's DRAWKIT - the kit panel, rendered
arm6309/software/pcs/bench/pcsicons.py           the tool icons, redrawn at card resolution
arm6309/software/pcs/bench/mkpcs.py              the generator, and the bench's table
arm6309/software/pcs/bench/checkpcs.py           the gate
arm6309/software/pcs/bench/run-pcs.sh            the bench
arm6309/software/pcs/bench/pcsdisk.py            the DISK panel and the .pbt reader, modelled
arm6309/software/pcs/bench/pcsworld.py           the WORLD panel, modelled
arm6309/software/pcs/bench/scripts/pcsedit.ps2   e0's editor session, as a mouse script
arm6309/software/pcs/bench/scripts/pcsdisk.ps2   d0's SAVE and LOAD session
arm6309/software/pcs/bench/scripts/pcsworld.ps2  w0's four sliders
arm6309/software/pcs/bench/scripts/mkpcsbuild.py writes pcsbuild.ps2: e1's table built from nothing, and the demo's
arm6309/software/pcs/video/run-build.sh          that session as a contact sheet or a video
```

## 7. Verification — `sh software/pcs/bench/run-pcs.sh`

⛔ **The model is checked before the machine is built.** `pcspak.py`, `pcsphys.py` and
`pcsobj.py` carry their own self-tests; if the transliteration is broken there is no point
finding out on a 6809 six minutes later.

⛔ **THE MODEL IS NEVER CORRECTED TO AGREE WITH THE 6809.** When they differ the 6502
decides and the fix goes wherever it was misread. A model tuned until it passes is the check
answering its own question — CLAUDE.md's `HOSTMAP` trap. ⚠ Correcting the model against the
**6502** is the one direction that is allowed, and it has happened twice.

The legs:

| | |
|---|---|
| `m0` | the scan converter: all 153,600 bytes of the table rectangle, and the span database record for record |
| `m4` | ⭐⭐ **the whole simulator**, 600 frames — the ball's `(x, y, BDX, BDY)` every frame, every part's state byte, and the score, the sound and the run chain |
| `m6` | ⭐⭐ **the editor**: a twelve-edit session through `pcsedit.inc`, two of them required to be refused, and the step results, the object area and the span database it leaves, against `pcsedit.py` |
| `e0` | ⭐⭐ **the editor with a mouse** (`pcs 23`): `scripts/pcsedit.ps2`'s 22 gestures through `EdLoop` — every gesture's record against what `checkpcs.py` works out from the **script's points alone**, then the object area, the span database and all 153,600 bytes of the table. ⛔ The same recording against a script that dragged one part two units further must fail |
| `e1` | ⭐⭐ **a table built from nothing** (`pcs 24`): `scripts/pcsbuild.ps2`, generated by `mkpcsbuild.py`, pulls fifteen parts out of the bin, stretches a polygon into the launcher's divider by four vertex drags, paints, **PLAYs the table twice** with a bumper moved between — and every gesture, the object area, the span database and the picture are checked exactly as `e0`'s are, starting from `mkpcs.empty_table`. ⚠ The games are a scripted hand and not reproducible to the frame; the checker skips the mouse while a game is up, which is sound because PLAY hands the editor back the table it left |
| `e2` | ⭐ **the magnifier** (`pcs 23`, `scripts/pcsmag.ps2`): lines of fat bits drawn and one **erased by the brush's toggle**, a miss on the panel, the box moved, QUIT, a tool that ends it, and left up at the end — every gesture's record against `pcsmag.py`, the layer `MgDump` streams to `EditL` (count and triples), the table with the layer composed in and the box's frame on it, and **every pixel of the viewer**. ⛔ The leg fails unless it saw a box move, a drawn line, a toggled erase and QUIT |
| `w0` | ⭐ **the WORLD panel** (`pcs 23`, `scripts/pcsworld.ps2`): gravity dragged past the bottom of its track, speed past the top, kick down and back up before the release, elasticity released wide of its track, a miss, QUIT, WORLD again and gravity once more from beside its frame — every record against `pcsworld.py`, the `wset` off `EditW`, and with the panel left up **every level's knob box on all four tracks**, the knob where `wset` says and nowhere else. ⛔ The leg fails unless every slider moved, level 0 and level 7 were both reached, and it saw a miss and QUIT |
| `c0`, `c2` | ⭐ **`e0` and `e2` again, gesture after gesture**: the same scripts with every `at` pulled in to 0.3 of its time, so each gesture starts while the last one's repaint is still running. Every check `e0` and `e2` make, and a floor of four samples taken off the mouse queue |
| `cX` | ⛔ `c0`'s script on `pcs 25` — mode 23 with the queue switched off — **required to fail on the records**, so `c0` cannot be passing because its gestures happened to fall between repaints |
| `d0` | ⭐⭐ **SAVE and LOAD** (`pcs 23 N demo2l.pbt`, `scripts/pcsdisk.ps2`), on the leg's **own copy of the card**: a part added and a line of fat bits drawn, the table SAVEd as `mytbl`, two parts deleted and SAVEd again over the same name, `demo1` picked off the catalogue and LOADed, `nosuch` typed and **refused**, and `mytbl` LOADed back. Every record and key against `pcsdisk.py`; the table the session ended on — object area, span database, layer, and `logic`/`wset` off `EditW` — and the picture; then ⭐ **every `.pbt` on the card the machine left**, read out with `os9 copy`, byte for byte against the files the model's panel holds. ⛔ The leg fails unless it saw a key, a pick, a LOAD taken and one refused, two SAVEs and QUIT |
| `f1` | ⭐ `demo2l.pbt` — demo2 with 1,206 layer pixels in its trailer (`pcsmag.demo_layer`) — loaded off the card: the database record for record, the picture with the layer in it, and every layer pixel not under a part's art on the card |
| `k0` | ⭐ **the editor's kit panel**: `pcs 22`'s whole 320 × 480 panel column, every card pixel, against `pcskit.py` — the parts bin, the redrawn tool icons, and the 12 × 10 colour picker with its frame on the current colour |
| `m1` | ⛔ MUTATION: the midpoint x rounding is dropped, so every sloped edge moves |
| `m2` | ⛔ MUTATION: a B-polygon paints its RECORDS instead of their complement — the bug that looks plausible on screen while inverting the ball's world |
| `m5` | ⛔ MUTATION: `BOUNCE` rotates back by `TTA` instead of `32 - TTA`. ⛔ The two are the SAME for `tta` 0 and 16, so a ball in a box of flat walls behaves identically and only a slope tells them apart |

⭐ **The picture includes the parts' art**, and the ball leg compares it against each part's
**final** frame and position — not against frame 0, which happened to pass and stops being
true the day a part comes to rest mid-animation. Tightening it is what found the missing
repaint.

⛔ **`fcb 6   ,8` emits ONE byte.** lwasm ends the operand field at the first space, so
printf padding turned `PCPIdx` into a table half its length: every part found the wrong
frame and it assembled without a murmur. `mkpcs.py`'s `_checkgen` now refuses any `fcb`/`fdb`
whose operand ends at a space, on every generation. ⚠ Same defect class as `grep '^FAIL'`
matching nothing — it reads exactly like success.

⭐ **The gate requires at least five LIBRARY PARTS to have been struck.** A ball that only
ever met the backdrop proves nothing about the object system, and that is exactly the run an
earlier table gave — 600 frames and 21 bounces agreeing over a collision walk that was
reading half the world.

⚠ **The bench drives the player.** A mouse and two keys are not reproducible, so the
recording mode fills `PDL0`/`BTN0`/`BTN1` off the frame counter by one rule that `pcsobj.py`
implements identically. Without it nothing that answers to the player could be gated.

⚠ Needs `../nitros9` on its `arm6309` branch, so it is in no aggregate. ⛔ Its exit code is
the answer.

## 8. Open

- ⭐ **The animation's repaint is built.** A part whose picture is not the one on the
  screen damages a rectangle; at the end of the pass it is **erased**, repainted from the
  span database and every picture over it put back. ⛔ The erase is not optional and not
  obvious: a library part's polygon is unfilled, `PCFill` refuses colour 0, and the
  backdrop paints its *complement* — so a repaint never writes the open playfield at all,
  and the previous frame stays underneath.
  ⭐ **The damage is what changed since the last repaint, not since the last tick**
  (`PBDiff`). The screen's version of every part — its state byte, its picture's top row
  and its left column (the ball's are `Y1`/`X1`), by run-chain slot in `dwst`/`dwtp`/`dwx` —
  is compared at the repaint, and a part that differs damages where it **was drawn** and
  where it **is**. `PBPlay2` takes the record for the table as keyed. One tick a repaint
  (the bench's `Play`) finds exactly the damage the tick made.
  ⭐ **The damage is four rectangles, and each is composed in the margin.** A part's
  rectangle is its top row down the height of **the tallest frame of its own template**,
  and its left column across **the widest**, plus a column either side (`PBDmP`, off
  `PCPIdx`/`PCFrm`) — the ball's is seven rows by ten columns. A rectangle widens a band
  whose rows it touches, else takes an empty one, else widens the last (`PBDmR`). Each band
  is composed off-screen at columns 640..1023 in chunks of at most 160 world rows
  (`PBRepB`), then copied onto the table by the copy engine in one rectangle, so a
  repaint never shows a wiped band. ⭐ **Only the band's columns** (`pcxl`..`pcxr`): the
  wipe, the spans (`PCSpn` clips), the pictures (`PBArt` skips one outside) and the copy
  back all stop at the window. A picture half in it is blitted whole, and what lands
  outside is margin that is never copied.
  ⭐ **`PCBlit` works down the columns**: it culls a picture wholly outside
  `pcclo`/`pcchi` before touching the card, clips the top and bottom by arithmetic, and
  sends each byte-column as one pointer and `bh` `VDATA` stores under `WADV` 01 (next
  row, same column). ⭐ `PCIsB` reads the part's kind out of `objkind`, a table
  `PKColrs` fills when a table is keyed, instead of walking the object area per picture.
  ⭐ Together (2026-09-25, `demo2`): a ball-only repaint ~8–27 ms and a flipper repaint
  118–142 ms. After a whole ball of play the table is bit-identical to the table at rest,
  but for the mouse pointer.
- ⛔ **Every exit puts the card's write state back** (`Bye`): `WADV` 00 and `CTRL`'s
  WMODE bits as `Claim` found them, before the claim is released. PLAY ends on `WADV`
  01, and the toolbox and CoArm assume 00 - a desk repainting over it drew its whole
  screen as columns squeezed into the left of the frame. `run-v3desk.sh`'s `pin` leg
  plays before it quits and compares the desktop it gets back with the one it left.
- ⚠ **Whether a VRAM pointer's auto-increment carries out of a row** is an open question
  about the card or the emulator's model of it. The bench's streams reposition at every row
  boundary, so they do not depend on the answer — but `graphics.md` §19 should settle it.
- ⚠ **A game dips below its 300 ticks a second while the flippers work** (§5b): ~290 on
  average, 229 at the worst. A flipper repaint is 118–142 ms, of which the span walk
  (`PCRow`, `PCSpn`, `PCIsB`, `PCFill`) is ~30 % — it walks every record on a row whatever
  the window — and resolving every part's picture per band before rejecting it (`PBArtI`,
  `PBCur`, `PBArt`) ~20 %.
- ⭐⭐ **The editor's database operations agree with the model** (`m6`, in the default
  bench). The twelve-edit session (two parts out of the bin, a drag, a vertex moved, one
  pasted and cut again, three paints, a delete, and two edits that must be refused)
  leaves the same step results, the same object area byte for byte, and the same span
  database as `pcsedit.py`. ⚠ **The editor opens a table as loaded**: mode 6 snapshots the
  object area before `PBPlay` keys the parts and restores it before the session, because
  `PBPlay` borrows every part's `L[8]` and runs every INIT proc. `PBClose` (`CLOSEOBJS`)
  is the way back from a game, and it runs the INIT procs again, as the original does.
  ⭐ **Every edit re-keys**: `vlo`/`rcn` point into the object area, which `PERbld`
  rewrites, so `EdDone` runs `PBKey` (`PBPlay`'s first half) before it draws a part.
- ⭐⭐ **The editor has a mouse** (`pcs 23`, `pcsui.inc`'s `EdLoop` — `EDIT.s`'s `MAIN`).
  ⭐ **One gesture is a press and its release, and the edit is made on the release**:
  the database operation is atomic and its rollback is the whole refusal, so the port
  does not re-run it at every mouse step the way the original re-XORs a rubber band.
  The press is classified in this order:
  - **on the table** (card x < 320), by the current tool. The **hand** picks with
    `SELECTPOLY` (the last span on the row that holds x, never the backdrop) and drags
    by the release less the press, in world units; released over the kit, the part is
    **deleted**. The **pointer**, **scissors** and **hammer** pick with `SELECTPOINT`
    (a polygon's vertex, or for the hammer the midpoint of the edge ending at it, within
    7 units on both axes, the smallest sum and the first on a tie) and then move the
    vertex to the release point, cut it, or paste a new one there — ⭐ the hammer's paste
    is **two edits**: the new vertex is found again by where it is, because `ALIGNPOLY`
    may have rotated the polygon, and then dragged to the release. The **brush** paints
    what `SELECTPOLY` finds, or the backdrop on a miss, with the picker's colour; painting
    a colour an object already has clears it to 0. ⭐ **A library part takes the brush
    too, and it is its art that changes colour**: the original's `PAINTOBJ` returns
    without touching one (`CMP #<LIBOBJ / BEQ PAINTO4`) because a 1bpp picture had
    nothing to take a colour, while `WM.Sprite` draws the art in any palette entry. So
    the part's `FILLCOLOR` is its picture's — `PKColrs` gives it to `artcolr` for
    `PBArt` and keeps `objcolr` at 0, so the collision polygon stays invisible — and
    `0` is `UI_PART`, which is what every shipped table's parts hold. Nothing the
    simulation reads changes.
  - **on the picker**: the colour.
  - **on a tool**: the first five (hand, pointer, scissors, hammer, brush) become the
    tool; **PLAY** plays the table, **MAGN** opens the magnifier and **DISK** the DISK
    panel (both below); the other five are recorded and not yet built.
  - **on the parts bin**, with the hand: the template is added where it is released,
    keeping the offset it was grabbed at, and ⚠ its corner is **clamped inside the
    table's border** (1 .. 158 − w, 1 .. 238 − h) rather than refused. Released over the
    kit, nothing is added.

  ⭐⭐ **The drag is live, and the card moves it** (`pcsui.inc`'s `Pv*`). At the press
  the part's rows are recomposed **without it**, and the part is drawn alone onto index
  0 in the margin, at (640, 0). Each mouse step is then three copies and no CPU pixel:
  the save-under back, the screen at the new place into the save-under, and the part
  over it with `WM.Sprite`, which skips index 0. ⭐ **The preview is the commit's own
  arithmetic** — `EdHand`'s displacement with `PEDrag`'s clamp, and `EdBXY` for a part
  out of the bin, which `EdBin` calls too — so where it is let go is where it lands.
  Over the kit there is **no preview**, because letting go there deletes it (or adds
  nothing). The margin holds a part up to 192 × 320 with its save-under beside it, or
  384 × 160 with it below; a larger one moves on the release. ⭐ A **vertex** drag
  (pointer or hammer) is a rubber band: the two edges meeting at the dragged point, in
  `PCC.Hilite`, drawn by Bresenham a card pixel at a time, with each pixel read back
  through `VDATA` first and given back in reverse order.
  ⭐⭐ **And the repaint is only the rows an edit touched, with no flash.** The press
  and the release each add the object's rows (its polygon and its art, or every row for
  the backdrop) to a damage range, and `RpRows` repaints that range **in the margin** —
  wiped, painted and its art blitted there, through the painter's `pcox`/`pcoy` offset
  and `pcclo`/`pcchi` clip — in bands of up to 160 world rows, each copied onto the
  screen whole. The screen never shows a wiped row. The painter's object filter
  (`pcfmd`: all, all but one, or one alone) is what composes the table without the
  dragged part and the part without the table. A paint still re-fills through
  `PEPaint`, which draws on the screen.
  ⭐ **A gesture made while the editor is busy is kept** (`pcsin.inc`). While
  `EdLoop` runs, `UISamp` reads `SS.Mouse` at most once a frame — from `PCWait`, which
  every VRAM-bound loop goes through, and once a scanline from `PKSweep`, because an
  edit's scan conversion is ~0.4 s of CPU with no VRAM access at all — and queues each
  change of the left button with the pointer where it happened, eight deep. `UIPoll`
  takes from the queue before it asks the mouse, so the gesture comes out exactly as
  it was made. `EdPlay` switches it off for the game and on again after.
  ⭐ **And the kit panel is a copy.** The parts bin is drawn once into the margin
  (`KitBin`, columns 640–1023 below row 320) and every later redraw is two copy-engine
  rectangles; the picker is streamed a cell row at a time and doubled by copies; and
  `PTBox` fills a box's first rows and copy-doubles the rest.
  ⭐ **Every gesture writes fifteen bytes** to the `EditR` stream: the tool after it, the
  press and the release in card pixels (16-bit, big-endian), the five-byte operation
  (the `PE` tuple, or 0 and a kind: 1 tool, 2 colour, 3 a part let go over the kit, 0
  nothing), and the answer (0 took, 1 refused, `$FF` no edit). A hammer paste writes two
  records. The stream ends with `$FF`, and `EditO` then carries 2,048 bytes of the object
  area. `q` ends the session.
  ⚠ **The pointer is at (0, 0) when `pcs` starts** — the mouse is relative — so a PS/2
  script for it begins `origin 0 0`.
  ⭐⭐ **PLAY, and back to the editor with the table intact** (`EdPlay`). The kit is
  cleared and `PGPanel`'s score strip (BONUS X / BONUS / BALL) drawn where it was, as
  the original blanked its bin; the game is `pcs 20`'s, mouse and all (`status.md`
  §4); `q` or the fifth ball ends it. ⭐ **The table comes back as it was left, not as
  the game left it**: a game borrows every part's `L[8]` and runs every INIT proc, and
  the original's way home, `CLOSEOBJS`, runs them again — so a ball would come back to
  its INIT place rather than where the editor put it. The object area and the wiring
  are snapshotted before the game and rolled back after it (the editor's own undo,
  `PESnap`/`PERoll`), and the table is recomposed in the margin. The span database is
  not touched by a game at all.
  ⭐ **Mode 24 is the editor on a NEW table** — the backdrop's walls and nothing else
  (`pcsfl.asm`'s `PCEmpty`) — which is how the Apple II session in
  `reference/pcs-apple2-editor.mp4` starts. ⛔ **The World sliders take their defaults
  before any table is built** (`PC.WGrav`…`PC.WElast`), and a file's own overwrite
  them; a table built in the module would otherwise play at `wset` = 0, gravity once
  in 256 frames. The WORLD panel (below) edits them.
  ⭐⭐ **The magnifier** (`pcsmag.inc`, EDIT.s's MAGNIFY). MAGN clears the parts bin to
  the panel colour and puts there a **viewer** of 24 × 40 world pixels, each an 8-pixel
  cell with a 6 × 6 fat bit in a `PCC.Dark` grid, and **QUIT** under it; the picker
  stays. On the table a 2-pixel `PCC.Hilite` frame sits just **outside** the viewed
  rectangle, so the pixels the viewer shows are never the frame's. ⭐ **The fat bits are
  read back off the card** (`VDATA`, post-incrementing), so they are the table, its art
  and its layer exactly as the eye sees them. ⭐ **A cell row is its runs and three
  copies**: cells of one colour are one span, painted over the grid between them; a
  `WM.Sprite` copy of a grid strip kept below the raster (rows 480–481) puts the grid
  back, keyed on index 0; and the copy engine repeats the two rows twice below. A table
  is mostly large areas of one colour, so a row is a handful of spans rather than 24. While it is up, every press goes to `MgAct`
  first:
  - **on the table**: the box moves, centred on the release and clamped so its frame
    stays on the table (record `EDL.MBox`, the new corner);
  - **in the viewer**: a Bresenham line of fat bits from the press to the release (a
    release outside the viewer ends it at the edge), into the layer in the picker's
    colour — ⭐ **or erased**, if the press was on a layer pixel already that colour, the
    brush's own toggle (`EDL.Plot`, the count and the colour, 0 for an erase). The rows
    it spans are the damage;
  - **QUIT** ends it (`EDL.MQuit`); **a tool** ends it and is taken as usual; **the
    picker** is the picker's; anything else on the panel is a miss.
  Ending it gives the box's rows to the damage and redraws the kit. ⚠ **The artifact
  colour is not copied**: a pixel is a palette index and its fat bit shows that index.
  Modes 23 and 24 stream the layer to `EditL` (VRAM row 496) after the session — the
  count and up to 682 triples — for the bench.
- ⚠ Not open any more, but worth keeping as a method note: the two tables that
  did not paint (2026-09-23) were **two different defects wearing one symptom**,
  and both were found by **modelling the 6809 routine in Python and diffing it
  against `pcspak.render` over all 29 shipped tables** rather than by running the
  machine. `DEMO2`'s reproduced in the model (`PCRow`'s per-record complement,
  §2); `DEMO4`'s did **not** — which is what proved it was not the algorithm and
  sent the search to the database, where object 10's span turned out to be stored
  with its ends swapped. See `history.md`.
- ⭐⭐ **A TABLE IS A FILE ON THE CARD** (2026-09-23), which is what `DISK.s`
  did and for the reason it did it: PCS never held two tables at once.
  `pcs <mode> <frames> <name>` takes a **bare name**, and `pcsfile.inc`'s
  `DOpen` tries `/SD0/DATA/` then `/DD/SYS/` — `tilescroll.asm`'s and
  `changefont.asm`'s, verbatim. `mkpcs.py` writes `software/pcs/bench/pcstbl/*.pbt`
  and `mkrom.sh` copies whatever is there onto the card; the four `DEMO*.PB` are
  there today (`PCS_FILES=n` writes more). ⛔ **The files are not in the
  repository** — same container, same shipped bytes, same rule (§5c).
  The loader refuses a payload longer than the object area, so a longer one is
  a version it does not know rather than a buffer it overruns; the free-hand
  layer follows the payload (§5).
- ⭐⭐ **THE DISK PANEL** (`pcsdisk.inc`, in `pcsfl`) is `DISK.s`'s LOAD, SAVE
  and QUIT over a typed name, with a **catalogue** the original did not have.
  It takes the kit's place like the magnifier — one byte, `edpnl`, says which
  panel has it, and `MgOn`/`MgAct` in `pcsmg` dispatch on it.
  - **The name** is one to eight letters and digits, folded to lower case;
    backspace takes one off. While the panel is up every key is the name's, so
    `q` does not end the editor. Each key is a record (`EDL.Key`).
  - **The catalogue** is every `*.pbt` in `/SD0/DATA` whose base is a legal
    name, sorted as NUL-padded bytes (`demo2` before `demo2l`), at most 48,
    fourteen rows a page; **MORE** turns the page and wraps. A row pressed
    puts its name in the field (`EDL.DPick`).
  - **LOAD** snapshots the object area (`PESnap`) and `wset`, then `PFLoad`s.
    Taken: the table is re-keyed, recoloured and repainted. Refused: the
    snapshot is rolled back and `wset` restored, so the table is the one that
    was there — except that `PFLoad` clears the layer before it reads a
    trailer, so a refused **trailer** (`PF.ELay`) leaves the table with no
    layer, and the model says so.
  - **SAVE** is `PFSave` (delete, create, header, payload, trailer), and the
    catalogue is read again after it whether it took or not.
  - **QUIT**, or any tool, ends it.
  Errors are shown by name on the panel's status line, and recorded
  (`EDL.DLoad`/`EDL.DSave`: `pferr`, and the object count or the catalogue's
  length). Modes 23 and 24 stream `logic` and `wset` to `EditW` (VRAM row 509)
  after the session, which is how `d0` sees what a LOAD brought with it.
  ⚠ And the module **still carries** up to `PCS_BUDGET` (8 KB, 7 tables) for the
  built-in modes the bench's mutation legs use. That is the last of the old
  arrangement, and it goes when `desk` gains a table picker.
- ⭐ **THE WORLD PANEL** (`pcsworld.inc`, in `pcsmg`) is `EDIT.s`'s WORLDSTART
  and DOSLIDE (`EDIT.s:2309–2470`): four vertical tracks over the kit's bin —
  GRAVITY and SPEED above, KICK and ELASTICITY below, the original's order —
  each with a tick beside its eight levels, a `PCC.Hilite` knob at the level
  `wset` holds, and QUIT under them. It is a panel like DISK's (`edpnl` =
  `PNL.Wld`).
  - **The level is DOSLIDE's rule at card scale**: 0 above the first level,
    then one level every 16 card rows from the track's top + 4, and 7 past the
    last — SLDXDY's thresholds were one every three Atari rows.
  - **A track takes the press** anywhere on its frame or 12 pixels either side,
    and **the knob follows the pointer while the button is down** (`WoLive`,
    called by `EdRls` each poll, as DOSLIDE's loop redrew it). The level is
    committed from the **release's y alone**, so a gesture is a function of
    its press and release and `checkpcs.py` models it from the script.
  - Each slide is a record (`EDL.WSet`: the slider, the level, the level
    before) and writes one byte of `wset`, which `RNWrld` turns into the
    physics when PLAY starts and SAVE writes to the file. **QUIT**
    (`EDL.WQuit`) or any tool ends the panel; anything else on it is a miss.
- ⭐ **`pcs` WITH NO ARGUMENTS IS THE EDITOR, FOR A PERSON**, and it is what
  `desk`'s Pinball icon and Applications item fork (`F$Fork` hands it a bare
  CR): mode 23 on `demo2.pbt` — or the built-in table if the card has none —
  with **no frame budget**, so it runs until `q`, and with the bench's VRAM
  streams off (`bare`, `PCEmit`). ⛔ The streams are off because a session with
  no end would write its gesture records past `EditR`'s eleven rows.
- ⚠ **Not written**: WIRE's tool (the wiring kit's UI). `RUN2.s`'s four-player game loop, the
  bonus tally and multiball are step 3c.
