# The sprite walker, from the programmer's side

**Written 2026-09-28.** How a program drives video3's sprite walker (`v3walk`): the
registers, the tables, the command, the timing and the traps. The hardware's own
description is `hardware/video3/docs/plan.md` §6.4, and the authoritative one is the
header of `hardware/video3/logic/v3walk.cpld.ts`. Where this document and those
disagree, they win. The worked example is `tilescroll`
(`../nitros9/level2/arm6309/cmds/tilescroll.asm`, `WInit`/`WArm`/`WRec`/`WFix`), and
`scrolling.md` §8 covers how that program uses the walker.

---

## 1. What it does

The walker is a sequencer in front of the copy engine. It loads the engine's nine
registers (`WPTR`, `CPTR`, `CWIDTH`, `CHEIGHT`, `CCTRL`) itself, out of tables held
on the card, and runs up to **three copies per sprite slot**:

| copy | from | to | keyed |
|---|---|---|---|
| **RESTORE** | the slot's save rectangle | last frame's position | no |
| **SAVE** | this frame's position | the slot's save rectangle | no |
| **DRAW** | the shape the record names | this frame's position | ⭐ **yes: index 0 is transparent** |

**One store to `SWCMD` runs a whole frame's actors.** The restores run for slots
*n*−1 down to 0, then the saves and draws for slots 0 up to *n*−1. Because the
order is LIFO, undoing last frame's draws in reverse leaves the background exactly
as it was, however the rectangles overlapped. **Higher slots draw on top**, so
slot *n*−1 is the front sprite.

The CPU writes no copy registers and does no address arithmetic. It writes a
3-byte record per sprite and one command a frame.

---

## 2. The registers

The card's registers are 32 bytes at **`$FF60`–`$FF7F`** (plan §10). The walker
uses two of them and shares a third:

| address | name (`armvid.d`) | direction | |
|---|---|---|---|
| `$FF7D` (+`$1D`) | `VR.WDAT` (`SWDAT`) | write | **the table port.** Each write stores one byte at the table pointer and advances it |
| `$FF7E` (+`$1E`) | `VR.WCMD` (`SWCMD`) | write | **SELECT** (b7 = 1) or **GO** (b7 = 0) |
| `$FF6D` (+`$0D`) | `VR.VSTAT` | read | b2 **`WALK`**: the walker is running. ⭐ The only card access that is not held during a walk |

### 2.1 `SWCMD` = SELECT (b7 = 1)

| b7 | b6..b3 | b2..b0 |
|---|---|---|
| 1 | first slot, 0–15 | table, 1–6, or ⭐ **7 = ARM** |

Tables 1–6 set the table pointer to (table, slot, byte 0). `WC.Sel` in `armvid.d` is b7.
⭐ **Table 7 (`WT.Arm`) is not a table: it arms the next GO** (§4.2). The slot field is
ignored.

### 2.2 `SWCMD` = GO (b7 = 0)

| bit | `armvid.d` | meaning |
|---|---|---|
| b3..b0 | — | **n − 1**: the walk covers slots 0..n−1, so n is 1–16 |
| b4 | `WC.NR` | **no restore pass.** Use it on the first walk, when nothing is on screen to put back |
| b5 | `WC.RO` | **restore only.** Puts every slot's background back and draws nothing, which removes the sprites |
| b6 | `WC.CB` | **the stream bank this frame's records are in**: 0 = table 1, 1 = table 2. The restore reads the **other** bank |

**Unarmed, the walk starts when the write ends. Armed, it starts at the next rise of
`VBLANK`** (§4.2). From then until `VSTAT` b2 clears, the walker owns the card's register
broadcast.

---

## 3. The tables

The tables live in the card's register-file SRAM. The CPU's 32 registers are page 0 of
that SRAM; the walker's tables are other pages of the same part. They **keep their
contents until overwritten**, so a table is written when it changes and not every
frame. Every row is three bytes:

| T | `armvid.d` | a row, per slot (or per shape) | written |
|---|---|---|---|
| 1 | `WT.StrA` | **stream record, bank A**: `X[7:0]`, `Y[7:0]`, `SHAPE[4:0]<<3 \| X[9:8]<<1 \| Y[8]` — ⭐ **`SHAPE` 31 (`WS.Null`) is "no shape"** (§3.4) | every frame (alternate frames with T2) |
| 2 | `WT.StrB` | **stream record, bank B**: the same layout | every frame (alternate frames with T1) |
| 3 | `WT.Dim` | **DIM**: `W[7:0]`, `H[7:0]`, the `CCTRL` image = `W[9:8]<<3 \| H[8]<<5` | when a slot's size changes |
| 4 | `WT.Save` | **SAVE**: a pointer to the slot's save-behind rectangle | when the save area moves |
| 5 | `WT.Shp0` | **SHAPE 0–15**: a pointer to each shape's top-left pixel | when the art moves |
| 6 | `WT.Shp1` | **SHAPE 16–31**: the same | when the art moves |

Table 0 does not exist: page 0 is where the CPU's registers live, and 7 is the ARM
command rather than a table.

### 3.1 Coordinates are VRAM ring addresses, not screen positions

Every position and pointer is a place in the 512 KB of VRAM, seen as **1024 columns × 512
rows**, byte address = `row × 1024 + column`. The stream record's X is a column
(0–1023) and its Y a row (0–511). **They are not screen coordinates.** A program that
scrolls (`HSCROLL`/`VSCROLL`) adds its scroll origin itself, modulo 1024 and 512. The
pointers in tables 4–6 are the same address in the copy engine's `CPTR` byte order:

```
byte 0 = col[7:0]
byte 1 = row[5:0]<<2 | col[9:8]
byte 2 = row[8:6]
```

`tilescroll`'s `PtrOut` and `RecOut` build exactly these. ⭐ A stream record becomes a
pointer by lane wiring alone, with no adder on the card. That is why the record's third
byte packs the high bits the way it does.

A rectangle crosses the ring's edges freely: columns wrap at 1024 and rows at 512.

### 3.2 Width, height, shape count and where the art lives

- **Width and height belong to the SLOT, not the shape** (table 3). Each slot's W×H is
  the rectangle every one of its three copies moves. W is 1–1023 and H is 1–511; ⚠ a
  height of 512 is 0 in a 9-bit field, and the copy then does nothing. **Write W and H
  themselves, not W−1.** Byte 2 of the row is the `CCTRL` image. Its b0 (GO) is forced
  by the walker, and b1/b2 are reserved and must be 0.
- **There is no per-sprite "shape count".** There are 32 shapes shared by all slots
  (tables 5 and 6). Each frame's record names one of them in its top five bits.
  **Animation is writing a different shape number**, and the walker has no frame
  counter of its own. A slot can use any shape, but it copies its own W×H from that
  shape's top-left. Shapes a slot uses must therefore be drawn at least that big,
  padded with index 0.
- **The art lives anywhere in VRAM**, as an ordinary rectangle: rows are 1024 bytes
  apart, as they are on screen. Put it where the raster never shows it. `tilescroll`
  keeps its 32 shapes in the top-left of 32 × 32 cells in the off-screen tile bank
  (`scrolling.md` §6.2).
- **Each slot needs a save rectangle of its own**, at least W×H, also off screen
  (table 4). The walker copies the background there and back; nothing else may use it.

### 3.3 The table port auto-advances, and a TFM works

After a SELECT, each `SWDAT` write stores one byte and advances **byte 0 → 1 → 2 →
the next slot's byte 0**. So a table, or any run of consecutive slots, is one stream of
3 × *k* bytes. ⚠ **The slot wraps from 15 to 0 inside the same table**; it never
spills into the next table. That is why `tilescroll` SELECTs table 6 again before
shape 16.

So yes: the protocol is **a 3-byte record per sprite, written as a block**, and the
6309's `TFM r0+,r1` (source advancing, destination fixed) is the natural way to send a
prepared array:

```
        lda     #WC.Sel+WT.StrA         bank A, slot 0 (b6-3 = 0)
        sta     $FF7E
        ldx     #recs                   3*n bytes built during the frame
        ldy     #$FF7D                  SWDAT
        ldw     #3*NACT
        tfm     x+,y
```

⭐ **`tilescroll`'s `WRec` does exactly this every frame**: its records are built in a
RAM array (`recs`, during `Logic`'s aftermath, with the card untouched) and sent with
one `tfm x+,y` into `VR.WDAT` — 3 × 7 bytes, and `run-tilescroll.sh`'s byte-exact ring
gate and its tearing legs are what check them. Its setup tables (DIM, SAVE, SHAPE) are
still `sta` loops, because each byte is computed as it goes.

The SELECT's slot field is a start slot, not a limit. One slot's record can be
rewritten alone with `WC.Sel + slot<<3 + table` and three writes.

### 3.4 ⭐ Shape 31 is "no shape"

A record whose `SHAPE` is **31** (`WS.Null` in `armvid.d`) is **skipped by every copy
that reads it**: the walker notices it as it reformats the record and steps on as if the
copy had finished, without starting the engine. So a slot with a null record in this
frame's bank does no save and no draw, and one with a null record in the other bank does
no restore — which is right, since nothing was drawn. X and Y are ignored; `tilescroll`
writes zeros. A skipped restore costs **3 dots** and a skipped save-and-draw **12**,
against thousands for the copies. Shape 31's entry in table 6 is therefore never read,
and a program has 31 usable shapes. This is how to hide a sprite **without changing n**
(§4.3).

### 3.5 Writing the port

⚠ **Write the port with stores, never `clr`.** A 6809 `clr` to memory reads the
location first, and a card read is not free (it can start a prefetch, and during a
walk it waits). `WInit` notes the same thing.

---

## 4. A frame

```
setup, once:   DIM for each slot, SAVE for each slot, SHAPE 0-30
               first frame's records into bank A
               SELECT 7, GO (n-1) | CB=A | NR                  <- armed: waits for the blank
each frame:    ... game logic, CPU only: the walk starts at the blank meanwhile ...
               poll VSTAT b2 until clear (bounded)
               scroll registers for the NEXT frame (VSCROLL loads in the blank)
               the frame's card work: streaming, table fix-ups
               next frame's records into the OTHER bank (SELECT + TFM 3n bytes)
               SELECT 7, GO (n-1) | CB=that bank               <- armed again
at the end:    wait for the armed walk to finish, then
               GO  RO | (n-1) | CB=the bank last drawn
               poll VSTAT b2 until clear (bounded)
```

### 4.1 The buffer swap is a bit, and the program owns it

There is **no automatic swap**. The two stream banks are tables 1 and 2, and GO's
b6 (`WC.CB`) says which one holds this frame's positions. The restore reads the other
one, which is last frame's. The program flips its own bank variable after each GO and
writes the next records into the bank it just flipped to (`tilescroll`'s `wcb`, in
`WArm` and `WRec`).

⭐ Two banks are what let the restore know where last frame's sprites were without
the CPU copying anything. The new positions go into the other bank.

### 4.2 ⭐ The armed GO: the blank starts the walk

**Write SELECT 7, then GO.** The GO is latched and does not start; the walker waits for
`VBLANK` to rise and starts the walk **within one bus cycle of it** (measured 4 dots
after the edge in `v3card_tb`, and every one of `tilescroll`'s 1,201 walks starts on line
480 exactly). The CPU never has to be in the blank at all. It arms the walk when its card
work is done and goes back to its own, and the walk runs underneath its game logic.

An **unarmed** GO (no SELECT 7 before it) still starts at once, which is what a program
that has just taken the VBL interrupt, or a wipe at the end, wants.

⛔ **Between an armed GO and the blank, the CPU must not:**

- write `SWCMD` or `SWDAT` (the walker refuses them, and the emulator reports it);
- start a copy (`CCTRL` b0), a span, or touch `VDATA` — the walk takes the engine at the
  blank, and a copy still running then would have its registers loaded under it.

**Every other register is free**, and none of them waits, because the walk has not
started: the scroll registers (the next frame's scroll is written after the walk, since
`VSCROLL` loads only in the blank), `CTRL`, `WFG`/`WBG`, the palette. `tilescroll`'s `WArm`
does `V3Wait` and `V3Mode #WM.Direct` first, so the contract of §6 is met by the time the
blank comes.

The VBL interrupt lives on the walker CPLD too (`CTRL` b6 enables it, and a `VSTAT`
write acknowledges it); it is independent of the armed GO.

### 4.3 How many sprites: GO's low nibble, and it must not change casually

The count is n − 1 in GO b3..b0, **every walk**. There is no stored count.

⛔ **The restore uses THIS walk's n, DIM and SAVE for last frame's sprites.** So:

- **If n shrinks**, the slots dropped from the end are never restored, and their last
  draw stays on screen for good.
- **If n grows**, the new slot's restore copies a save rectangle that was never filled
  over whatever position its stale bank record names.
- **If a slot's DIM changes**, its restore puts back a rectangle of the new size over a
  save made at the old one.
- **If a SAVE pointer changes**, the restore reads the new place, which holds nothing
  of this slot's.

So change the cast only across a **wipe**: `GO RO` with the old n, then write the new
tables and GO with the new n **and** `NR`. ⭐ Or, much simpler, keep n fixed and give the
slots that should not show a **null record** (shape 31, §3.4). `tilescroll` walks every
slot every frame and writes a null for every actor not wholly on screen, so a hidden
actor costs 15 dots a frame and the walk is only as long as what is visible
(`scrolling.md` §8.2).

### 4.4 Turning it off

**There is no enable bit.** The walker does nothing until it is given a GO, and does
not repeat on its own. To remove the sprites, write one **`GO RO`** with the same n and
the bank last drawn as CB. Then stop writing GOs. `tilescroll`'s `WWipe` does this,
and bounds its poll of `VSTAT` b2.

---

## 5. Timing

The dot clock is 25.175 MHz (39.72 ns). A frame is 525 lines of 800 dots, 480 of them
displayed, so **the vertical blank is 45 lines = 36,000 dots ≈ 1.43 ms**.

### 5.1 What a walk costs

Each copy costs the walker's loads plus the engine:

```
dots per copy  ≈ 25 + H × (W × 6.216 + 17)
```

That is 25 dots of register loads and waits, 6.216 dots a byte (the engine's 4.05 MB/s:
one read access and one write access a byte), and 17 dots at each row end for the
column reload. These are measured in `v3card_tb` and reproduced in
`software/emu/machine.c`. `walkcast.py`'s `walk_cost()` computes it.

| per slot, per frame | copies |
|---|---|
| normal | 3 (restore, save, draw) |
| first walk (`NR`) | 2 |
| wipe (`RO`) | 1 |

| sprite | one walk (3 copies) |
|---|---|
| 8 × 8 | ≈ 1,680 dots ≈ 67 µs |
| 16 × 16 | ≈ 5,670 dots ≈ 225 µs |
| 24 × 16 | ≈ 8,050 dots ≈ 320 µs |
| 32 × 32 | ≈ 20,800 dots ≈ 0.83 ms |

`tilescroll`'s default cast (a 16×16 hero and six creatures from 8×8 to 24×16)
measures **480 → 504** of the 525 lines at the median and **517** at the worst — 0.76 ms
and 1.18 ms of the 1.43 ms blank — because the armed GO starts it on the blank's first
line and null records make an off-screen creature free.

### 5.2 Tearing

A displayed line is torn if the walk still owes a write to its VRAM row when the beam
starts drawing it. A walk that overruns the blank therefore tears **the top of the
picture, down to the line where it finishes**, and nothing below that. VRAM is never
wrong; only the frame being scanned shows a mixture. In `tilescroll`'s `s1` leg,
thirteen creatures overrun the blank in half the frames, by up to 29 lines, and every
torn line is in 0–13 (`scrolling.md` §8.4).

The line a copy lands on is where its destination row is on screen, which depends on
the scroll. So the budget is really **"the walk ends before the beam reaches the
topmost sprite"**. A frame whose sprites all sit low on the screen can afford a longer
walk than one with a sprite at line 0. To make an overrun cheaper, give low slot
numbers the sprites nearest the top. They are saved and drawn first, but restored
last, so the gain is partial.

### 5.3 ⛔ The CPU during a walk

**Any card access except a `VSTAT` read is held in `/WAIT` until the walk ends.** That
includes register writes, `VDATA`, the table port, the palette, a copy of the
program's own, a `VSTAT` *write* (the VBL acknowledge), and a second GO. Nothing is
lost, but the CPU stops for as long as the walk has left.

- **Do CPU-only work while the walk runs**: game logic, input, sound bookkeeping. Touch
  the card again only once `VSTAT` b2 has cleared, or accept the stall. ⚠ **`FCnt`
  (+`$1F`) is a card register and is held too** — read it after the walk. In
  `tilescroll` the order is movement and logic (CPU only, while the walk runs) →
  `ScBlank` (poll `VSTAT` b2, then the scroll registers and `FCnt`) → streaming jobs →
  `WFix` → `WRec` (the `TFM`) → `WArm`.
- **Interrupt handlers that touch the card stall too.** A VBL service that
  acknowledges through `VSTAT` waits out the rest of the walk, and interrupts behind it
  wait longer.
- A GO written during a walk is held until that walk ends and then starts the next
  one (or, armed, waits for the next blank). The hardware ignores `SWCMD`/`SWDAT` loads while `WALK` is high, which is why
  the `/WAIT` is what keeps them.

---

## 6. ⛔ The contract at GO

The walker loads the copy engine exactly as the CPU would, so it inherits the engine's
modes. **At the moment of GO:**

1. **`WMODE` is not 11 (`WM.Sprite`).** The key would then apply to the restores and
   saves too, leaving holes wherever a background pixel is index 0. The DRAW copy
   asserts its own key (`WKEY` into `v3lane`), so **the walk needs no mode**. Use
   `WM.Direct`.
2. **`WADV` b2 is clear.** With it set, every destination steps two bytes a byte.
3. **No copy or span is running.** A GO under a running copy would load registers
   beneath it.

For an **armed** GO, "the moment of GO" is the moment the walk starts at the blank, and
§4.2's pending rules keep it true until then. `tilescroll`'s `WArm` does `V3Wait` (engine
and span writer idle), then `V3Mode #WM.Direct`, then SELECT 7 and the GO. **The host
emulator enforces all of it**, checked when the walk actually starts. It prints `FAIL …
a walk with WMODE 11`, `… with WADV b2 set`, `… under a running copy`, or a card access
made while a GO is pending, and counts contract violations in its summary line.

---

## 7. What else a developer needs to know

- ⛔ **A walk overwrites `WPTR`, `CPTR`, `CWIDTH`, `CHEIGHT` and `CCTRL`.** They are the
  copy engine's own registers and the walker loads them. Afterwards they hold the
  last copy's values. **Reload `WPTR` before any `VDATA` access or span, and set every
  copy register before your own copy.** Nothing restores them. The read prefetch is
  invalidated too.
- **The restore puts back what was saved, even if the background has changed since.**
  If the program writes terrain under a sprite between its SAVE and next frame's
  RESTORE (streaming a new column, animating a tile), the restore undoes it.
  `tilescroll` makes that impossible by walking only actors wholly inside the view,
  while streaming writes only outside it. A program that edits the background under
  sprites must do it with the sprites wiped, or also edit the save rectangle.
- **Keep the tables true when the art or save area moves.** They hold absolute VRAM
  addresses. `tilescroll`'s tile bank rotates through the ring, so `WFix` rewrites
  table 4 whenever the save column moves, and tables 5
  and 6 whenever an art column moves. Such a move has to carry the save rectangles'
  contents with it, and it must happen **between** walks. It does naturally, because
  the copy that moves it waits for the walk.
- **The key is index 0**, fixed in hardware. Nothing drawn in a shape may be palette
  entry 0 unless it is meant to be transparent. `walkcast.py`'s `c332` lifts any
  colour that quantises to 0.
- **Slots and shapes are limits of the tables**: 16 slots and 32 shapes. There is no
  sprite hardware per slot; everything is copies into the frame, so a walked sprite
  shows in any display mode that shows that VRAM. It is unrelated to the card's 16×16
  mouse sprite (plan §7), which is a separate overlay.
- **Null slots are nearly free** (15 dots a frame), so walking a fixed n with nulls for
  the absent is cheaper and safer than changing n.
- **Tearing, in the emulator.** The host emulator applies a walk's copies a row at a
  time on the card's clock. With a walk running it writes `walk.txt` in the run
  directory, one line a frame: `frame … walks … start_line … end_line … torn … top
  … bottom … draw_top`. `run-tilescroll.sh`'s `walk()` shows how to summarise it.
- **Proof it works**: `v3card_tb`'s `walk` group (`make -C hardware/video3 sim`) runs
  three slots of three sizes over overlapping positions, then a wipe, then the same with
  null records behind an armed GO, and compares all 512 KB of VRAM against a model of
  every copy. `sh
  software/tilescroll/bench/run-tilescroll.sh` runs a whole program on it.
