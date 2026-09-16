# Hardware changes that would make NitrOS-9 run better — a running list, 2026-09-14

**This is a list, not a specification.** It collects card and machine changes found while
writing the NitrOS-9 video and audio drivers (`docs/nitros9-av-plan.md`). Each item says
what the driver does today, what it costs, and what change would remove the cost. None of
them is designed, fitted or checked. An item that is taken becomes a spec entry in its
card's document, and is deleted from here.

Costs are measured on the host emulator (`software/nitros9/run-vid.sh`, its `MASKLOG` and
`CALLTIME`) unless they say otherwise. Plan §10's items (a list-END event, a tick without a
video card, `SDATA` read-back, a register map for line compare) are not repeated here.

## Taken, 2026-09-14

Four items were built, fitted and checked, at **no packages**, and left the list:

| Was | Now | What the driver lost | Measured after |
|---|---|---|---|
| H14, the armed `GO` | `graphics.md` §10.3.1 rule 3 | the `VBLANK` poll inside the VBL service | the longest IRQ with a list on **1.66 → 0.72 ms** (`rast`, `wave`); the VBL service's longest **468 → 183 µs** |
| H8, `VMODE` at frame start | `graphics.md` §6.2 (`vctrl`'s `M0`) | `VcVMode`'s yield and masked poll, and plan V8's unchecked rule | `vsync_tb` changes family at lines 500 and 300 |
| H7, a posted palette commit | `graphics.md` §13.1 response 3, `VSTAT` b1 `PBUSY` | `VcPalPer`'s 16 entries a blank; the palette is written from the main line, a line an entry | 0 snow dots outside `HLOAD` (`vpal_tb`). No holding `'574` was needed: the `PDATL`/`PDATH` `'573`s are the store |
| H11, an `IRQEN` per port | `ps2.md` §3.1, §8.2 (`IOCTRL` b6 `KIRQEN`, b7 `MIRQEN`) | a hang class | — |

The fits: `vctrl` 95 / 128 cells, 56 / 64 pins, pass 1; `vsup` 94 / 128 cells, **63 / 64
pins, on the fitter's second pass** (`graphics.md` §19 item 46). ⚠ `vsup` has one pin left.

Rank 5's software re-measurement was done in the same pass: `vidptr.asm` saves and restores
only the arrow's 106 pixels of row runs, and a move is **15.6 → 7.9 ms (7.3 ms outside
interrupts)**.

## What to build first, and what it costs — 2026-09-14, after P0–P3

The table below ranks the items by what P0–P3 measured against what each would cost the
card. **No cost here is a fit.** They are estimates against the fitted parts' headroom, and
headroom is not one number on this card (`graphics.md` §14): cells, I/O pins and switch-matrix
fan-in each run out separately.

| Part | Cells | I/O pins | Fan-in | What that means for a change |
|---|---|---|---|---|
| `vctrl` | 95 / 128 | 56 / 64 | — | the roomiest: sync, `CTRL`, the span control |
| `vsup` | 94 / 128 | 63 / 64 | — | **1 spare pin**, 2 cascades, placed on pass 2: pins are its limit |
| `vaddr` | 113 / 128 | 59 / 64 | **40 / 40 in every block** | one-literal changes have been refused here (`graphics.md` §10.3.3). Anything that touches the scan address or `WPTR` is a re-partition until a fit says otherwise |

The card is **33 ICs** today (`graphics.md` §14.1), the PS/2 card **11** (`ps2.md` §9).

### Tier 3 — large wins, large cost

| Rank | Item | Measured cost it removes | Cost | Risk |
|---|---|---|---|---|
| **5** | **H1, a hardware cursor** | **7.9 ms a pointer move**, done only from the idle loop, so the pointer freezes under a busy process; `PtrGuard` on every drawing primitive. With it, a move is four register writes | **≈ +4–5 packages**: a fourth CPLD (position compare against the scan counters, and the shape's address), a small SRAM for two 16 × 16 planes, and a quad-OR pair to force white at the output register. Black can be the `'273`'s `/MR`, which blank-to-black already drives (§9.2). The scan position has to leave `vctrl`/`vaddr` on pins | ⛔ **`features.md` §8 rejected an overlay** because the pixel path has 11.7 ns of margin. Forcing the *output register* rather than muxing the LUT index keeps it out of the index → LUT path, but a gate before the register still spends part of that margin: it needs a timing argument before a fit |
| **6** | **H15, hardware sprites** (H1 generalised) | the overworld's hero: 15 tiles composited a tile a frame, 4.4 updates a second, and a 0.47–0.75 ms flip in a 1.56 ms blank | **≈ +8 or more**: a compare and a shape store per sprite, and a priority mux in the pixel path | the same timing objection, larger |
| **7** | **H4, more VRAM with a selectable scan start** | a screen switch copies 128 K–307 K each way at CPU speed, seconds with the display off | **≈ +2–3 packages** (another pair of `AS6C8016`s, and a page select) — and page bits in the scan address and `WPTR` land on **`vaddr`**, which has no fan-in left | a re-partition, most likely a fourth CPLD |
| **8** | **H9, a six-bit cell row** | no fast-text screen taller than 30 rows; at 80 × 30, more than two line feeds a frame show a recycled row | nominally 0 packages (`graphics.md` §6.4.6: one bit of `MAPBASE`, 4 K more map) — but on **`vaddr`** | as rank 7 |
| **9** | **H5, H2, H3, H6: the blit datapath** — vertical rectangle copy, XOR and logic `WMODE`s, a span pattern | a 192-row window scroll ~350 ms; the bitmap text cursor ~1.2 ms a character; `LSet` and patterned fills a write per pixel | **~14 ICs plus logic** (`features.md` §5), and `vsup`'s pins are the binding limit (`graphics.md` §14) | the largest piece of work on the card |

### Not recommended

| Item | Why not |
|---|---|
| **H16**, a 128-byte `WADV` stride | it lands on `vaddr`'s fan-in to save ~0.35 ms a map column, and `libvid`'s `VlPoke` already does a column in two masked calls |
| **H12**, a PS/2 transmit shift register | +2–4 packages, for a 1.9 ms mask that happens at Init, and for keyboard LEDs |
| **H13**, a larger system address space | a question for the MMU and the motherboard, not the video card. Taking the shell out of the bootfile bought P3 what it needed |
| **H10** | nothing to build |

### ⭐ Re-ranked 2026-09-16 — three corrections, and a new item

`docs/video-copyrect.md` asked what a blitter-first card would buy and measured
the store rate that every cost below is denominated in
(`software/demo/bench/vramrate.asm`). **Four things changed, and none of them is
a fit.**

| | Was | Is |
|---|---|---|
| ⭐ **VidCore's ~10 µs a byte** | a fixed cost the H-items are priced against | **measured: 20.86 E cycles a byte, and 16 of them are the loop.** Unrolling with direct-page stores is **2.2× for a copy, 2.7× for a fill, and ~2.5× again through a mapped VRAM window**, at no hardware, with the masking rule intact (it masks *less*) — so **every row below is worth less than it reads** until the streams are rewritten |
| ⭐ **H3**, logic `WMODE`s | "needs the span writer to read before it writes, which is the blitter's datapath" — priced with H5/H2/H6 at **~14 ICs** | ⛔ **that stopped being true on 2026-09-11.** `graphics.md` §11 built the read path: read at `WPTR` into the `vread` latch, ALU with `WFG`, write back. **3.15 MB/s, 4.5× `TFM`, ~3 packages** — ⚠ byte-wide only, so it gives up broadcast width |
| ⭐ **H4**, more VRAM | "≈ +2–3 packages (another pair of `AS6C8016`s, and a page select)" | ⛔ **the memory is already fitted.** `graphics.md` §14.2.2: each `AS6C8016` is 512K×16 with two address pins tied off, so the two parts hold **2 MB** and address 512 KB — "precisely the 2 MB upgrade path the moment the pointers widen to 21 bits". **0 packages of SRAM**; the cost is two more bits on the scan address and `WPTR`, both on `vaddr` |
| ⭐ **H1**, a hardware cursor | rank 5, the thing to buy first | **displaced by H20.** Copyrect makes a pointer move ~125 µs — inside the mouse's IRQ — *and* delivers H4, H5 and H15, without touching the pixel path that `features.md` §8 says has 11.7 ns of margin |

**The order that falls out**, and the first two need no silicon:

| | Item | Why here |
|---|---|---|
| **1** | **Rewrite VidCore's streams** (`video-copyrect.md` §6) | measured, free, and it changes what everything below is worth |
| **2** | **Spend an 8 KB map slot on the VRAM window** | `graphics.md` §11: every address in a mapped window is `VDATA`, so a 16-bit store carries two bytes. The fastest path on the card, and it exists |
| **3** | **H3**, logic `WMODE`s | ~3 packages, and it is what QuickDraw's `srcXor`/`srcOr` need (`video-copyrect.md` §5.4) |
| **4** | ⭐ **H20**, copyrect — **vertical-only first** | the missing third engine. ≈ +5–6 packages, ⚠ estimated |
| **5** | **H9**, the six-bit cell row, **and H18's attribute plane** | both land on `vaddr` and both are the console. ⭐ **H4, H9, H18 and H20 all want the same `vaddr` re-partition** — designing them as one fourth CPLD is the difference between one re-partition and four |
| ⛔ | **H1** (hardware cursor), **H19** (1/2/4bpp scan), flat-mapped VRAM | superseded, or priced and lost — `video-copyrect.md` §2.1, §4 |

### The software was measured again before buying rank 5

`features.md` §9 estimates a pointer move at **~0.92 ms**; the first driver took **15.6 ms**,
and the run-only driver takes **7.9 ms**. Most of the rest is the 6809 instruction set:
VidCore streams VRAM ~10 µs a byte in masked chunks, where the estimate assumed `TFM`, ~1.6 µs.
A 6309-native VidCore with `TFM` through `VDATA` would recover more. ⚠ Neither the host
emulator's core nor `machine_tb`'s `mc6809e` executes 6309 opcodes, so a `TFM` VidCore cannot
be checked on them as they stand. Even a ~2 ms move does not fit an IRQ service, so the
frozen pointer and `PtrGuard` remain the case for rank 5.

**What is left, in order:** the 6309 VidCore measurement; then rank 5 (≈ +5, ~38 ICs) if the
desktop's pointer matters — with `vsup` at one spare pin it needs its fourth CPLD anyway.
Ranks 6–9 are a card revision, not an amendment.

## Video card

| # | What the driver does today | What it costs | The change |
|---|---|---|---|
| H1 | **The mouse pointer is drawn into VRAM.** The pixels under the arrow's row runs are read back through `VDATA` and kept, then the arrow is composed over them. Every move puts them back and draws it again (`vidptr.asm`) | 106 pixels restored, 106 read back and 106 composed a move: **7.9 ms, 7.3 ms of it outside interrupts, measured** (`run-vid.sh`'s `mouse` run; 15.6 ms when the whole 16 × 16 box was saved). No write mode removes the save-behind itself. Far too long for the mouse's `/IRQ` service, so the kernel's idle loop does it, and **a process that computes without sleeping freezes the pointer**. Every CoArm primitive must check whether it covers the pointer and take it off first (`PtrGuard`) | **A hardware cursor**: a 16 × 16 two-colour overlay with its own X/Y registers, merged at the pixel mux. A move is four register writes, and drawing never has to know where it is |
| H2 | **The text cursor on a bitmap window is XOR-inverted in software**: 64 pixels read and 64 written, to show it and again to hide it, around every write to the window (`ca_bmtx.asm` `CurXor`) | ~1.2 ms a character on a bitmap window, just for the cursor | **An XOR write mode**, or the hardware cursor of H1 used as a block. An XOR `WMODE` (pixel := pixel XOR `WFG`) would also serve H3 |
| H3 | **`LSet`'s AND, OR and XOR are read-modify-write**: the row is read back, combined in the CPU, and written again (`ca_draw.asm` `Span`) | one `VDATA` read and one write per pixel, instead of one write per 256 pixels | **Logic `WMODE`s**: span-solid with AND/OR/XOR of `WFG` into what is there. It needs the span writer to read before it writes, which is the blitter's datapath (`features.md` §5) |
| H4 | **A screen switch copies VRAM to DRAM and back at CPU speed.** The card has no second page, and no VRAM-to-VRAM or DMA path (`ca_scr.asm` `CardToStore`, `StoreToCard`) | 640 × 200 is 128 K each way; 640 × 480 is 307 K each way, several seconds. The display is off meanwhile | **More VRAM, with the scan start selectable**, so each screen keeps its own pixels and a switch is a base register. Or a DMA path between DRAM and VRAM |
| H5 | **A window that is not the whole screen scrolls by copying rows**: each row is read back and written 8 rows up (`BmScroll`). Only a full-screen window can use `VSCROLL` | ~1.8 ms a 640-pixel row. A text window 192 rows tall is ~350 ms a line | **A VRAM-to-VRAM rectangle copy** — the blitter `features.md` §5 already describes — even one limited to vertical moves |
| H6 | **A patterned fill is written a pixel at a time.** Span-mask gives 2-colour patterns, but CoWin's patterns are pixel data, so each row is built in the CPU and streamed direct (`Span`'s pattern path) | one write per pixel, where solid is one write per 256 | **A span-pattern mode**: an 8-byte repeating pattern loaded once, then span-solid-like writes that tile it |
| H9 | **Cell mode's map ring is 32 cell rows** (`graphics.md` §6.4.1). An 80 × 30 text screen has 2 spare ring rows, so more than 2 line feeds in a frame show a recycled row for that frame; 80 × 50 and 80 × 60 are not possible in cell mode | a visible glitch under fast output at 80 × 30; no fast-text screen taller than 30 rows | **A six-bit cell row**, which `graphics.md` §6.4.6 already prices at one bit of `MAPBASE` and 4 K more map |
| H10 | **Every register the system writes is shadowed**, because the register file reads back the last write but not safely under a span or a list (plan V1, V4) | none worth measuring; it is bookkeeping | Nothing needed. Noted because a readable `CTRL` and scroll pair would have saved a class of bugs |
| H15 | **A moving figure on a tile screen is fifteen tiles the CPU composites**: each cell under the hero is the world's tile read back through `VDATA` with the sprite's bytes laid over it, written to a spare tile code, and the map cells swapped in the blank (`overworld.asm`, as `demo.asm` does it) | 64 reads and 64 writes a tile, so the hero is rebuilt a tile a frame and moves 4.4 times a second at 70 Hz; the swap is an `SS.Batch` of up to 30 map writes, **0.47–0.75 ms of a 1.56 ms blank**, measured, with the IRQ at 1.35 ms | **Hardware sprites**: H1's overlay, a few of them and larger, over cell mode as well as bitmap. The figure is a position and a frame, and the map never changes |
| H16 | **A column of map cells is a `WPTR` load per cell**: map rows are 128 bytes apart, and `WADV` steps a ring row, 1,024 (`libvid.asm` `VlPoke`) | a column of 26 is 26 × 3 register writes and 26 bytes; as 26 separate calls it cost one frame in five, and as two masked pokes it is ~0.35 ms each | **A `WADV` stride of 128 in cell mode** (the map's row), so a column is one `WPTR` load and a stream |
| H17 | **A display list cannot scroll vertically.** A `MOVE` reaches `HSCROLL` but not `VSCROLL` (its second write port was refused by the fitter, `graphics.md` §10.3.2), and the row counter loads from `VSCROLL` only in vertical blanking (`VLOAD`, §6.4.1). The armed `GO` does not change either | no mid-frame vertical split: a status line under a scrolling playfield is two screens' worth of redraw instead of a register | **A `VSCROLL` load at a line**, on `vaddr`, and a list `MOVE` to reach it — both on the part with no fan-in left |
| H18 | **A fast-text cell is a (glyph, colour) pair**, so `FColor`/`BColor` rebuild the whole 16 KB bank (~6 ms) and there is no per-character colour, underline or blink (`graphics.md` §6.4.8). ⛔ **And `$80`–`$FF` are spent on the inverted half of the font**, so CP437 — which is where every box and block character of ANSI art lives — does not fit a bank at all | ANSI art changes colour mid-line constantly, so **the fast console cannot render it**; it is bitmap text at 11–13 writes a cell, 63–74 ms a screen (`software/nitros9/docs/video-compat.md` §6.7) | ⭐ **An attribute plane, and `graphics.md` §6.4.10 now costs one** — two map bytes a cell, the attribute driving the **LUT's dead high address lines** (63.5 KB of its 64 are unused) rather than a 1bpp serialiser, which is what §6.4.6 limit 3 refuses. **2 writes a cell, 256 simultaneous (fg, bg) pairs from all 65,536**: 16-colour ANSI exactly, most 256-colour content in practice, and all 256 code points. ⚠ **≈ +1–2 packages and a `vaddr` re-partition**, unfitted; the load-bearing claim is that the attribute is constant across a cell so no stage joins the 11.7 ns dot path. ⭐ **The software half needs no silicon**: two halves of 128 glyphs in two colour pairs |
| H19 | **The scan path is 8bpp only**, so CoCo 3 screen types 1–4 must be rendered into 8bpp and no CoCo image is byte-compatible | 4–8× the memory for the same picture, and an asset converter for everything ported | **A 1/2/4bpp scan mode.** ⛔ **Not recommended**: it lands on the index → LUT path, which has 11.7 ns of margin (`graphics.md` §6.1). A build-time converter buys the compatibility more cheaply |
| ⭐ H20 | **There is no VRAM-to-VRAM path at all.** Every byte that moves inside VRAM goes out through `VDATA` into the CPU and back — which is H1, H4, H5 and H15, all of them | ~16.2 MB/s of spare access sits unused while a 192-row scroll takes ~350 ms and a `Select` takes seconds | **Copyrect.** ⭐ **The 1024-byte stride removes the adder** that usually makes it expensive — end-of-row is `WADV` 01, already built — so it is a second `WADV`-shaped pointer, two counters and a read-write sequence, not `features.md` §5's general blitter. ⚠ **≈ +5–6 packages, estimated**; `vaddr`'s fifth mux source is the risk (`docs/video-copyrect.md` §2, §3) |

## PS/2 card

| # | What the driver does today | What it costs | The change |
|---|---|---|---|
| H12 | **Transmit is done by software, with `/IRQ` masked for the whole frame** (`ps2.md` §7.1) | 1.9 ms masked per byte sent; Caps Lock's LED is not driven, because that would be a transmit from the keyboard's service | **A transmit shift register** clocked by the device, with a done flag |

## The machine

| # | What the driver does today | What it costs | The change |
|---|---|---|---|
| H13 | **CoArm runs in a task of its own**, because the 64 K system map had 15 K free after boot with it in the bootfile (`software/nitros9/docs/video-console.md`). Every window call is a task switch each way, through `D.Flip1` and `D.Flip0`, and CoArm must yield to ArmIO for anything that sleeps or allocates | two task switches per byte written to a window | **A larger system address space** — a 6309 in native mode does not give one, so this is an MMU question: a second system map for drivers, or a per-module map window the kernel manages |
