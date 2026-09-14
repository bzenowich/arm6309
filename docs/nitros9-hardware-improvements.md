# Hardware changes that would make NitrOS-9 run better — a running list, 2026-09-14

**This is a list, not a specification.** It collects card and machine changes found while
writing the NitrOS-9 video and audio drivers (`docs/nitros9-av-plan.md`). Each item says
what the driver does today, what it costs, and what change would remove the cost. None of
them is designed, fitted or checked. An item that is taken becomes a spec entry in its
card's document, and is deleted from here.

Costs are measured on the host emulator (`software/nitros9/run-vid.sh`, its `MASKLOG` and
`CALLTIME`) unless they say otherwise. Plan §10's items (the armed `GO`, a list-END event,
a tick without a video card, `SDATA` read-back, a register map for line compare) are not
repeated here.

## Video card

| # | What the driver does today | What it costs | The change |
|---|---|---|---|
| H1 | **The mouse pointer is drawn into VRAM.** The 16 × 16 pixels under it are read back through `VDATA` and kept, then the arrow is written in sprite mode. Every move puts them back and draws it again (`vidptr.asm`) | 256 reads, 256 writes and 32 sprite writes a move: **15.6 ms, measured** (`run-vid.sh`'s `mouse` run). Far too long for the mouse's `/IRQ` service, so the kernel's idle loop does it, and **a process that computes without sleeping freezes the pointer**. Every CoArm primitive must check whether it covers the pointer and take it off first (`PtrGuard`) | **A hardware cursor**: a 16 × 16 two-colour overlay with its own X/Y registers, merged at the pixel mux. A move is four register writes, and drawing never has to know where it is |
| H2 | **The text cursor on a bitmap window is XOR-inverted in software**: 64 pixels read and 64 written, to show it and again to hide it, around every write to the window (`ca_bmtx.asm` `CurXor`) | ~1.2 ms a character on a bitmap window, just for the cursor | **An XOR write mode**, or the hardware cursor of H1 used as a block. An XOR `WMODE` (pixel := pixel XOR `WFG`) would also serve H3 |
| H3 | **`LSet`'s AND, OR and XOR are read-modify-write**: the row is read back, combined in the CPU, and written again (`ca_draw.asm` `Span`) | one `VDATA` read and one write per pixel, instead of one write per 256 pixels | **Logic `WMODE`s**: span-solid with AND/OR/XOR of `WFG` into what is there. It needs the span writer to read before it writes, which is the blitter's datapath (`features.md` §5) |
| H4 | **A screen switch copies VRAM to DRAM and back at CPU speed.** The card has no second page, and no VRAM-to-VRAM or DMA path (`ca_scr.asm` `CardToStore`, `StoreToCard`) | 640 × 200 is 128 K each way; 640 × 480 is 307 K each way, several seconds. The display is off meanwhile | **More VRAM, with the scan start selectable**, so each screen keeps its own pixels and a switch is a base register. Or a DMA path between DRAM and VRAM |
| H5 | **A window that is not the whole screen scrolls by copying rows**: each row is read back and written 8 rows up (`BmScroll`). Only a full-screen window can use `VSCROLL` | ~1.8 ms a 640-pixel row. A text window 192 rows tall is ~350 ms a line | **A VRAM-to-VRAM rectangle copy** — the blitter `features.md` §5 already describes — even one limited to vertical moves |
| H6 | **A patterned fill is written a pixel at a time.** Span-mask gives 2-colour patterns, but CoWin's patterns are pixel data, so each row is built in the CPU and streamed direct (`Span`'s pattern path) | one write per pixel, where solid is one write per 256 | **A span-pattern mode**: an 8-byte repeating pattern loaded once, then span-solid-like writes that tile it |
| H7 | **Palette commits snow, so they wait for a blank, 16 entries at a time.** That keeps the VBL service under plan §3.4's 0.5 ms (`vidsvc.asm` `VcPalPer`) | a full 256-entry palette takes 16 frames (0.23 s) to arrive, and a screen switch waits for it with the display off | **A palette holding store latched in the blank**: the driver writes all 256 entries at any time, and the card commits them itself at VBLANK, without snow |
| H8 | **A `VMODE` family change must be written just after VBLANK falls** (plan V8: `vctrl.v`'s terminal-count decode is partial). The first VBL service waited for it with `/IRQ` masked, 1.2 ms; now CoArm polls for it from the main line (`VcVMode`) | a yield of a frame and a poll on every screen switch between the 449- and 525-line families. ⚠ The rule is inferred, and nothing checks it | **A `VMODE` register that takes effect at the next frame start**, whatever instant it is written |
| H9 | **Cell mode's map ring is 32 cell rows** (`graphics.md` §6.4.1). An 80 × 30 text screen has 2 spare ring rows, so more than 2 line feeds in a frame show a recycled row for that frame; 80 × 50 and 80 × 60 are not possible in cell mode | a visible glitch under fast output at 80 × 30; no fast-text screen taller than 30 rows | **A six-bit cell row**, which `graphics.md` §6.4.6 already prices at one bit of `MAPBASE` and 4 K more map |
| H10 | **Every register the system writes is shadowed**, because the register file reads back the last write but not safely under a span or a list (plan V1, V4) | none worth measuring; it is bookkeeping | Nothing needed. Noted because a readable `CTRL` and scroll pair would have saved a class of bugs |
| H14 | **A display list's `GO` is issued by polling `VBLANK` inside the VBL interrupt**, because `WAIT` *n* is line *n* only for a `GO` inside line 0 (`graphics.md` §10.3.2) and the interrupt arrives 12 lines into a 49-line blank (`vidsvc.asm` `VcGo`) | **1.66 ms masked** every frame a list is on, measured (`run-vid.sh`'s `rast` and `wave`): past the 16C550 FIFO's 1.4 ms at 115.2 kbaud. Plan §10's armed `GO` removes it | Plan §10's **armed `GO`**, or else **a readable scanline counter**: the service could then `GO` at once behind as many `WAIT`s as there are lines left in the blank, with no poll |
| H15 | **A moving figure on a tile screen is fifteen tiles the CPU composites**: each cell under the hero is the world's tile read back through `VDATA` with the sprite's bytes laid over it, written to a spare tile code, and the map cells swapped in the blank (`overworld.asm`, as `demo.asm` does it) | 64 reads and 64 writes a tile, so the hero is rebuilt a tile a frame and moves 4.4 times a second at 70 Hz; the swap is an `SS.Batch` of up to 30 map writes, **0.47–0.75 ms of a 1.56 ms blank**, measured, with the IRQ at 1.35 ms | **Hardware sprites**: H1's overlay, a few of them and larger, over cell mode as well as bitmap. The figure is a position and a frame, and the map never changes |
| H16 | **A column of map cells is a `WPTR` load per cell**: map rows are 128 bytes apart, and `WADV` steps a ring row, 1,024 (`libvid.asm` `VlPoke`) | a column of 26 is 26 × 3 register writes and 26 bytes; as 26 separate calls it cost one frame in five, and as two masked pokes it is ~0.35 ms each | **A `WADV` stride of 128 in cell mode** (the map's row), so a column is one `WPTR` load and a stream |

## PS/2 card

| # | What the driver does today | What it costs | The change |
|---|---|---|---|
| H11 | **`IRQEN` is one bit for both ports.** A byte waiting on the mouse port raises `/IRQ` as surely as a key. P1's first keyboard driver took only `KDR`; the mouse's power-on bytes held the line, IOMan's poll found no claimant, and the kernel returned from the IRQ with interrupts masked for 40 ms (`kbdarm.asm`) | a hang class: any port without a service can hold the shared `/IRQ` | **A separate `IRQEN` per port** (bit 7 of `IOCTRL` is spare), so a port nobody services stays quiet |
| H12 | **Transmit is done by software, with `/IRQ` masked for the whole frame** (`ps2.md` §7.1) | 1.9 ms masked per byte sent; Caps Lock's LED is not driven, because that would be a transmit from the keyboard's service | **A transmit shift register** clocked by the device, with a done flag |

## The machine

| # | What the driver does today | What it costs | The change |
|---|---|---|---|
| H13 | **CoArm runs in a task of its own**, because the 64 K system map had 15 K free after boot with it in the bootfile (`software/nitros9/docs/video-console.md`). Every window call is a task switch each way, through `D.Flip1` and `D.Flip0`, and CoArm must yield to ArmIO for anything that sleeps or allocates | two task switches per byte written to a window | **A larger system address space** — a 6309 in native mode does not give one, so this is an MMU question: a second system map for drivers, or a per-module map window the kernel manages |
