# GIME vs VIC-II — Tandy CoCo 3 and Commodore 64 Video/System Chips

**Purpose:** a technical comparison of the two chips, written from the point of view of
someone building a cycle-accurate CPU replacement. The question that matters for
`arm6309` is not "which chip draws prettier pictures" but **"what does the video chip do
to the CPU's bus, and when?"** — and on that question the two machines differ
fundamentally.

**Date:** 2026-08-21
**Companion:** [`cpu/docs/plan.md`](../cpu/docs/plan.md) §2 (CoCo 3 host requirements), §3.3 (timing budget)

---

## 0. The one-paragraph answer

The **GIME** and the **VIC-II** occupy the same slot in their machines' block diagrams —
each is the master oscillator, the DRAM controller, the video generator, and the source of
the CPU's clock — but they solve the memory-bandwidth problem in opposite ways. The GIME
**runs the DRAM faster** and confines every video fetch to the half of each bus cycle the
CPU is not using. The VIC-II **runs the DRAM at CPU speed** and, when it needs more than
its half, **halts the CPU and takes the other half**. The consequence for a CPU
replacement is stark:

> **On a CoCo 3, the video chip never steals a cycle from the CPU. On a C64, it steals up
> to ~46 of 63 cycles on a bad line with eight sprites.**

Everything else — sprites, palettes, resolutions, scrolling — follows from the same split:
the VIC-II spent its transistor budget on a games machine that borrows CPU time; the GIME
spent its on a multitasking-OS machine that doesn't.

---

## 1. Sources and confidence

| Claim class | Source | Confidence |
|---|---|---|
| GIME registers, MMU, palette, video modes | *Color Computer 3 Service Manual* (Cat. 26-3334), pp. 10–20 — in this repo as [`coco3_ServiceManual.pdf`](../reference/manuals/coco3_ServiceManual.pdf) | **verified against the PDF** |
| GIME clocking, DRAM arbitration | Same, §5.2 (p. 33) and §5.3 (p. 35) | **verified against the PDF** |
| CoCo 3 DRAM part/organisation | Same, §5.2 and parts list (`M5M4464P-15`) | **verified against the PDF** |
| VIC-II cycle behaviour, registers, timing | Christian Bauer, *The MOS 6567/6569 video controller (VIC-II) and its application in the Commodore 64* (1996); *C64 Programmer's Reference Guide* | recalled, widely corroborated — **not** verified against a document in this repo |
| GIME 1986 vs 1987 mask revisions | Community documentation (*Unravelled* series, Cloud-9 notes) | **flagged — verify before relying on** |

Anything marked ⚠ below is an inference or a recalled figure that has not been checked
against a primary document.

---

## 2. Scope: what each chip actually is

The service manual calls the GIME the **ACVC** — *Advanced Color Video Chip* — part number
**TCC1014 / VC2645QC**, board reference **IC6**. Its register block is `$FF90–$FFDF`
(service manual §1.5, p. 10).

| Function | GIME (CoCo 3, 1986) | VIC-II (C64, 1982) |
|---|---|---|
| Master oscillator | ✅ 28.63636 MHz NTSC / 28.4750 MHz PAL | ✅ 14.31818 MHz NTSC / 17.734472 MHz PAL |
| CPU clock generation (E/Q, ϕ0) | ✅ E **and** Q, 0.89/1.78 MHz | ✅ ϕ0, ~1.02 MHz (NTSC) |
| DRAM RAS/CAS/WE + address mux | ✅ | ✅ |
| DRAM refresh | ✅ | ✅ (5 cycles/line) |
| Video generation | ✅ | ✅ |
| **Memory management (MMU)** | ✅ **16 × 6-bit task registers, 512 KB** | ❌ (C64 banking is PLA + 6510 port) |
| **System interrupt controller** | ✅ **6 sources → IRQ *or* FIRQ, per source** | ❌ (only its own 4 video sources; system IRQ/NMI come from the CIAs) |
| Device select decode (ROM/PIA/cart) | ✅ drives S0–S2 → 74LS138 | ❌ (PLA) |
| **Hardware sprites** | ❌ **none** | ✅ 8 |
| Collision detection | ❌ | ✅ sprite-sprite, sprite-background |
| Light pen latch | ❌ | ✅ |
| Character generator | **on-chip ROM** | **off-chip**, fetched over the video bus |
| Legacy compatibility mode | ✅ emulates SAM + MC6847 VDG | ❌ (VIC-I was never software-compatible) |
| Package | large DIP | 40-pin DIP |

The GIME is the more *integrated* chip; the VIC-II is the more *specialised* one. The GIME
absorbed two prior chips (the MC6883 SAM and the MC6847 VDG) plus an MMU and an interrupt
controller. The VIC-II absorbed nothing — the C64 still needs a PLA for banking and two
CIAs for timers and interrupts.

---

## 3. Clocking — a shared ancestry

Both chips derive everything from the NTSC colour subcarrier, and by coincidence of
history the CoCo 3's crystal is *exactly twice* the C64's.

| | CoCo 3 (NTSC) | C64 (NTSC) | C64 (PAL) |
|---|---|---|---|
| Crystal | 28.63636 MHz | 14.31818 MHz | 17.734472 MHz |
| Colour reference | ÷8 → 3.579545 MHz | ÷4 → 3.579545 MHz | 4.433618 MHz |
| CPU clock | ÷4 → **0.894886 MHz**<br>÷2 → **1.789773 MHz** | ÷14 → **1.022727 MHz** | **0.985248 MHz** |
| Dot clock | 14.31818 MHz (640-px modes) ⚠ | 8.181816 MHz | 7.881984 MHz |
| Cycles / scan line | ~57 @0.89, ~114 @1.78 | 65 | 63 |
| Lines / field | 262 (NTSC), 312 (PAL) | 263 | 312 |
| Field rate | ~59.9 Hz / 50 Hz | 59.83 Hz | 50.12 Hz |

Service manual §5.3 (p. 35), verbatim:

> "The Master Oscillator is divided by eight to give a 3.579545 MHz color reference signal
> to the Video Display Generator LOGIC and Composite Video Signal (NTSC version only). This
> reference signal is then divided by 4 (or 2) again to provide the 0.89 MHz (1.78 MHz) E
> and Q clock signals for the processor."

### 3.1 The runtime speed switch — no VIC-II equivalent

The GIME retains the SAM speed bits at `$FFD8`/`$FFD9` and will change the CPU clock
**between one bus cycle and the next, while software is running** (`POKE 65497,0`). The
C64 has no such facility — the VIC-II's ϕ0 is fixed for the life of the machine.

Critically, and unlike the CoCo 1/2 where the equivalent SAM poke destroyed the display,
**the CoCo 3 display survives the switch to 1.78 MHz**. This is a direct consequence of the
GIME's arbitration scheme (§4): the video fetch rate is set by the *scan line*, not by the
CPU clock, so doubling E halves the CPU's share of wall-clock time per line without
changing what video needs. What *does* break at 1.78 MHz is any cycle-counted software
delay loop — disk and serial routines in particular — which is why CoCo software toggles
the speed back down around I/O.

> For `arm6309`, this is the reason the bus loop must be **purely edge-driven** with no
> assumed E period (plan.md §2.1). The GIME gives no notice of the switch.

---

## 4. Memory arbitration — the central difference

### 4.1 Both chips interleave

Neither chip has dual-port memory. Both split each CPU bus cycle in half and take one half
for video. Service manual §5.3 (p. 35):

> "…access to the VDG LOGIC during the low time of E (Video portion). During each access,
> whether by the CPU or the Video, the ACVC must provide appropriately synchronized RAS*
> and CAS* signals… **Note that the DRAM access time must be twice as fast as that required
> by the CPU alone in order to be able to respond to VDG accesses.**"

The VIC-II does the same thing with opposite polarity: the 6510 owns ϕ2-high, the VIC-II
owns ϕ2-low. So far, identical philosophies.

### 4.2 Where they diverge: what happens when half isn't enough

**The VIC-II needs two simultaneous streams and only has one bus.** In text and bitmap
modes it must fetch both:

- **g-accesses** — 40 bytes/line of pixel or character-generator data. These fit in ϕ2-low.
- **c-accesses** — 40 bytes of video matrix (screen codes) + 40 nibbles of colour RAM.
  These are needed only on every 8th line, but when they are needed they must happen *in
  the same cycles* as the g-accesses.

There is no second bus, so the VIC-II takes the CPU's half. It asserts `BA` low three
cycles in advance (giving the 6510's `RDY` input time to finish up to three write cycles),
then holds the bus for 40 cycles. That is a **bad line**: it occurs when
`RASTER & 7 == YSCROLL` inside the display window, and it leaves the CPU **23 of 63 cycles**
on PAL.

Sprites make it worse: each active sprite costs a pointer fetch plus two data bytes per
line, all stolen from the CPU.

| VIC-II per-line accesses (PAL, worst case) | Count |
|---|---|
| Graphics (g) | 40 |
| DRAM refresh | 5 |
| Video matrix + colour (c) — bad lines only | 40 |
| Sprite pointer + data — 8 sprites | 24 |
| **Total demand** | **109** |
| **ϕ2-low slots available** | **63** |
| **Shortfall taken from the CPU** | **~46** ⚠ |

**The GIME never has this problem, because it fetches only one stream and fetches it
faster.** Its peak video demand is **160 bytes per scan line, in every mode**:

| Highest-bandwidth GIME modes | Bytes / line |
|---|---|
| 640 px × 4 colours (2 bpp) | 640 × 2 / 8 = **160** |
| 320 px × 16 colours (4 bpp) | 320 × 4 / 8 = **160** |
| 80-column text + attribute bytes | 80 × 2 = **160** |
| *(640 px × 2 colours, for contrast)* | 80 |

That 160-byte ceiling is not a coincidence — it is the GIME's fetch bandwidth, and Tandy
defined the mode table around it. There is no second stream because **the character
generator is inside the GIME**, so text mode costs exactly the screen bytes and nothing
more.

Now the arithmetic. A scan line is 63.695 µs (the GIME's own slow timer tick, service
manual `$FF95`). 160 bytes in 63.695 µs is **398 ns/byte**; confined to the E-low half,
**~199 ns/byte**. The CoCo 3 ships `M5M4464P-15` DRAM — 64K × 4, **150 ns** — arranged as
64K × 8 with two banks (service manual §5.2, p. 33). ⚠ The manual does not spell out the
burst mechanism, but 199 ns/byte from 150 ns parts is comfortably inside fast-page-mode
territory, and it explains the manual's insistence that DRAM be "twice as fast as required
by the CPU alone."

> **Bottom line: the GIME's peak demand fits in its own half of the cycle. It has no
> mechanism to halt the CPU for video, and it never does.**

### 4.3 Consequence table

| | GIME | VIC-II |
|---|---|---|
| Steals CPU cycles for video | **Never** | Yes — bad lines |
| Steals CPU cycles for sprites | n/a (no sprites) | Yes — 2+/sprite/line |
| Steals CPU cycles for refresh | Never (refresh lives in E-low) | Never (refresh lives in ϕ2-low) |
| CPU-visible wait states | **None** | None *per se* — full halt instead |
| Cycles available to CPU per line | **constant** (~57 @0.89 MHz) | **23–63**, varies by line and sprite count |
| Signal used to halt the CPU | `/HALT` — **floppy DRQ only** | `BA` → `RDY` |
| Is instruction timing data-independent? | **Yes** | No — depends on raster position |

That last row is the one that matters most for a CPU replacement, and it is the reason a
CoCo 3 project is tractable in a way a C64 project would not be. See §10.

---

## 5. Address space and memory management

### 5.1 GIME: a real MMU

The GIME extends the 6809E's 16 address lines to 19 — **512 KB, `$00000–$7FFFF`** (service
manual p. 14). The mechanism:

- **16 task registers** at `$FFA0–$FFAF`, **6 bits each, write-only**, organised as two
  banks of 8.
- The CPU's 64 KB logical space is divided into **eight 8 KB pages**. `A15:A13` select which
  task register applies; that register's 6 bits become **`A18:A13`**.
- Bit `TR` (`$FF91` bit 0) selects which bank of 8 registers is live — so a task switch is
  **one register write**, not eight.
- Requires `COCO=0` and `M/P=1` in `$FF90`.

The two-bank design is the whole reason **NitrOS-9 Level 2** is practical on this machine:
process context switches don't have to rewrite the map.

### 5.2 VIC-II: a 16 KB window and nothing else

The VIC-II has **14 address lines — a 16 KB reach**. The bank is chosen by CIA #2 port A
bits 0–1 (inverted), so the VIC can see one of four 16 KB windows into the C64's 64 KB.
Inside that window:

- Video matrix location: `$D018` bits 7–4 (1 KB granularity)
- Character/bitmap base: `$D018` bits 3–1 (2 KB granularity)
- Sprite pointers: fixed at video matrix + `$03F8`
- **The character ROM is hard-shadowed** into VIC banks 0 and 2 at `$1000–$1FFF` and
  `$9000–$9FFF`, which is why those regions can't be used for graphics data.
- **Colour RAM is off the video bus entirely** — 1024 × 4 bits of static RAM at `$D800`,
  read through a separate 4-bit path.

| | GIME | VIC-II |
|---|---|---|
| Video address reach | **19 bits / 512 KB** | 14 bits / 16 KB |
| Video base granularity | **8 bytes** (`$FF9D`/`$FF9E` = Y18:Y3) | 1 KB (screen), 2 KB (chars) |
| Framebuffer can live anywhere in RAM | **Yes** | No — inside the current 16 KB bank |
| Holes in the video window | None | Char ROM shadow in banks 0 and 2 |
| CPU memory management | **8-page MMU, 2 tasks** | none (PLA + 6510 port `$01`) |

This is not a close contest. The GIME's memory architecture is a generation ahead — it was
designed to run a paged, multitasking OS, and it does.

---

## 6. Video modes and resolution

### 6.1 GIME (service manual pp. 17–18)

Mode selection is `HRES2:0` × `CRES1:0` in `$FF99`, with `BP` (`$FF98` bit 7) picking
alphanumeric vs bit-plane, and `LPF1:0` giving **192, 200, or 225 lines per field**.

| Pixels | Colours | Bytes/line |
|---|---|---|
| 640 | 4 | 160 |
| 640 | 2 | 80 |
| 512 | 4 | 128 |
| 512 | 2 | 64 |
| **320** | **16** | **160** |
| 320 | 4 | 80 |
| 256 | 16 | 128 |
| 256 | 4 | 64 |
| 256 | 2 | 32 |
| 160 | 16 | 80 |

Text: **32, 40, or 80 characters/line**, `LPR2:0` giving 8 or 9 scan lines per character row
(plus 1/2/3/12 for CoCo 1/2 legacy modes). Each character is a **pair** of bytes:

| Attribute byte (odd) | Meaning |
|---|---|
| bit 7 `BLINK` | 1/2-second blink |
| bit 6 `UNDLN` | underline |
| bits 5–3 `FGND2:0` | foreground → palette entry 0–7 |
| bits 2–0 `BGND2:0` | background → palette entry 0–7 |

**Crucially: no attribute clash.** In every GIME bitmap mode each pixel independently
indexes the palette. 320×192 in 16 colours means *any* 16 colours *anywhere*.

### 6.2 VIC-II

| Mode | Resolution | Colour rule |
|---|---|---|
| Standard text | 40×25 chars | 1 fg per char (colour RAM) + **1 global** bg |
| Multicolour text | 40×25 | 4 colours/char; 3 global + 1 per char |
| Extended background text | 40×25, **64 chars only** | 4 selectable global backgrounds |
| Hires bitmap | **320×200** | **2 colours per 8×8 cell** |
| Multicolour bitmap | **160×200** | **4 colours per 4×8 cell** |

The VIC-II's cell-based colour is the famous **attribute clash**, and it is the single
largest qualitative difference in image quality. The C64's answer was never more colours
per cell — it was *sprites*, which are exempt from the cell grid.

### 6.3 Head to head

| | GIME | VIC-II |
|---|---|---|
| Max horizontal resolution | **640** | 320 |
| Max vertical resolution | **225** | 200 |
| Max simultaneous colours (bitmap) | **16, freely placed** | 16, but ≤4 per 4×8 cell |
| Attribute clash | **none** | severe |
| Max text columns | **80, with fg+bg per char** | 40, fg only |
| Blink / underline attributes | **yes, in hardware** | no |
| Interlace / doubled vertical | no | no |
| Legacy compatibility modes | 11 CoCo 1/2 VDG modes | none |

---

## 7. Colour

**GIME:** 16 palette registers at `$FFB0–$FFBF`, **6 bits each**, so **16 on screen out of
64** — plus an independent border colour at `$FF9A` that is not one of the 16. The 6 bits
are interpreted differently per output (service manual p. 17):

| Output | Bit meaning |
|---|---|
| **Analogue RGB** | `R1 G1 B1 R0 G0 B0` — 2 bits per gun, 64 colours |
| **Composite** | `I1 I0 P3 P2 P1 P0` — 2-bit intensity + 4-bit phase (16 hues × 4 levels) |

The same register value therefore means **different colours on the RGB monitor and on
composite** — CM-8 users and TV users saw genuinely different pictures, and CoCo 3 software
routinely shipped two palette tables. (PAL machines ignore the composite table entirely.)

**VIC-II:** **16 colours, fixed in silicon, not programmable.** The chip generates luma and
chroma directly; there are no palette registers, only colour *selectors* (`$D020` border,
`$D021–$D024` backgrounds, `$D025`/`$D026` sprite multicolour, `$D027–$D02E` per sprite).
The exact hues differ between mask revisions, which is why C64 emulator palettes are a
matter of long-running argument.

| | GIME | VIC-II |
|---|---|---|
| Colours on screen | 16 | 16 |
| Total palette | **64** | 16 |
| Programmable palette | **yes** | **no** |
| Independent border colour | yes, from all 64 | yes, from the 16 |
| Analogue RGB output | **yes** | no |
| Separate luma/chroma (S-video) | composite only | **yes** — the reason C64 S-video is good |
| Palette-change raster effects | yes (write `$FFBx` mid-frame) | not possible |

The GIME wins on flexibility; the VIC-II wins on output quality into a TV, and its fixed
palette was chosen with real care.

---

## 8. Sprites, scrolling, and raster effects

This is where the VIC-II is not merely competitive but decisively better.

### 8.1 Sprites

**The GIME has none.** Every moving object on a CoCo 3 is drawn by the CPU.

The VIC-II has 8 hardware sprites: 24×21 hires (1 colour) or 12×21 multicolour (3 colours,
2 shared), independent X/Y 2× expansion, per-sprite priority against the foreground, and
**two hardware collision registers** (`$D01E` sprite-sprite, `$D01F` sprite-background)
that raise interrupts. Sprite multiplexing — reusing one sprite on several raster lines via
raster interrupts — routinely puts 16–24 objects on screen.

For an action game, this single feature is worth more than the GIME's entire resolution and
palette advantage.

### 8.2 Scrolling

| | GIME | VIC-II |
|---|---|---|
| Horizontal fine scroll | `$FF9F` `X6:X0` — **byte granular at best** ⚠ | `$D016` bits 2–0 — **per pixel, 0–7** |
| Vertical fine scroll | `$FF9C` `VSC3:0` — within a character row | `$D011` bits 2–0 — **per pixel, 0–7** |
| Virtual (wider-than-screen) buffer | `$FF9F` bit 7 `HVEN` → **128-byte rows** | no |
| Coarse scroll | `$FF9D`/`$FF9E`, 8-byte steps | move video matrix, 1 KB steps |
| Hiding the scroll-in edge | no equivalent | `$D016` 38-col / `$D011` 24-row |

The GIME's `HVEN` virtual-screen mechanism is genuinely nice — set a 128-byte row pitch
regardless of the displayed width and pan a window across it, from the service manual
(p. 13):

> "HVEN enables a horizontal screen width of 128 bytes regardless of the HRES bits and CRES
> bits selected. This will allow a 'virtual' screen somewhat larger than the displayed
> screen."

But the horizontal offset moves the window in **byte** units, which is 2 pixels in
16-colour mode and 8 pixels in 2-colour mode — **never one pixel**. ⚠ Community
documentation (the *Unravelled* series) reports the increment is actually **2 bytes**,
making it coarser still; the service manual does not state the multiplier. Verify on
hardware before designing around it.

The VIC-II's `XSCROLL`/`YSCROLL` are true per-pixel, and combined with the 38-column /
24-row narrowing that hides the incoming edge, they give free pixel-smooth scrolling in
both axes. The CoCo 3 has to pre-shift bitmaps in software.

### 8.3 Raster interrupts — the decisive gap

| | GIME | VIC-II |
|---|---|---|
| Programmable raster compare | **no** | **yes** — `$D012` + `$D011` bit 7, any of 312 lines |
| Per-scan-line interrupt | `HBORD`, **every line, unconditional** | via raster compare |
| Per-frame interrupt | `VBORD` | via raster compare |
| Interrupt sources | 6: `TMR`, `HBORD`, `VBORD`, `EI2` serial, `EI1` keyboard, `EI0` cartridge | 4: raster, sprite-sprite, sprite-bg, light pen |
| Routing | **each source independently to IRQ *or* FIRQ** (`$FF92` / `$FF93`) | single IRQ line |
| Programmable timer | **12-bit, `$FF94`/`$FF95`**, auto-reload | none (CIA timers instead) |

To split the raster at line 100 on a **C64**, you write 100 to `$D012` and return. To do it
on a **CoCo 3**, you take a `VBORD` interrupt and then count 100 `HBORD` interrupts — one
interrupt every 63.695 µs, which at 0.89 MHz is **one interrupt per 57 CPU cycles**. Even
with `FIRQ` (which stacks only PC and CC — 10 cycles of entry, against the 6502's 7 cycles
plus manual register saves), that consumes a large fraction of the machine.

The practical CoCo 3 answer is the **GIME timer**: `TINS=0` in `$FF91` clocks it from
horizontal sync, so the 12-bit counter is a **scan-line counter** with a 261 ms range, and
one interrupt fires at the chosen line. That works, but it is a workaround for a missing
raster compare, and it costs a timer that NitrOS-9 also wants for its system tick.

Where the GIME does win: **independent IRQ/FIRQ routing per source**. On a C64 the raster
interrupt and the CIA timer interrupt share one IRQ line and must be demultiplexed in
software. On a CoCo 3 you can put the timer on FIRQ and vertical sync on IRQ and never poll
a status register.

### 8.4 The trick vocabulary

The VIC-II's cycle-exact, documented-to-the-cycle behaviour spawned an entire genre of
effects that have no CoCo 3 equivalent: **FLD** (suppress bad lines to push the display
down), **FLI** (force a bad line every line to get per-line colour, defeating attribute
clash at the cost of nearly all CPU time), **VSP**, **opening the side and top/bottom
borders**, **AGSP**, **DMA delay**. Every one of these depends on writing a specific
register in a specific cycle of a specific raster line.

The CoCo 3's repertoire is narrower — mid-frame palette writes, mid-frame mode and vertical
offset changes, palette rotation — but it exists, and it is *also* cycle-timed. plan.md
already flags this:

> "CoCo 3 software does cycle-timed GIME video tricks. This is not a machine where 'close
> enough' timing passes."

---

## 9. Register map, side by side

| GIME | | VIC-II | |
|---|---|---|---|
| `$FF90` | INIT0: COCO, M/P, IEN, FEN, MC3:0 | `$D000–$D010` | sprite X/Y |
| `$FF91` | INIT1: TINS, TR | `$D011` | RST8, ECM, BMM, DEN, RSEL, YSCROLL |
| `$FF92` | IRQ enable (6 sources) | `$D012` | raster compare |
| `$FF93` | FIRQ enable (6 sources) | `$D013`/`$D014` | light pen X/Y |
| `$FF94`/`$FF95` | 12-bit timer | `$D015` | sprite enable |
| `$FF98` | VMODE: BP, BPI, MOCH, H50, LPR2:0 | `$D016` | MCM, CSEL, XSCROLL |
| `$FF99` | VRES: LPF1:0, HRES2:0, CRES1:0 | `$D017` | sprite Y expand |
| `$FF9A` | border colour (6-bit) | `$D018` | video matrix + char base |
| `$FF9C` | vertical fine scroll | `$D019`/`$D01A` | IRQ status / enable |
| `$FF9D`/`$FF9E` | vertical offset Y18:Y3 | `$D01B` | sprite-background priority |
| `$FF9F` | HVEN + horizontal offset | `$D01C` | sprite multicolour |
| `$FFA0–$FFAF` | **MMU task registers (write-only)** | `$D01D` | sprite X expand |
| `$FFB0–$FFBF` | **palette (write-only)** | `$D01E`/`$D01F` | collision registers |
| `$FFC0–$FFDF` | SAM legacy: modes, offset, **speed** | `$D020–$D02E` | colour selectors |

Two GIME quirks worth internalising: the MMU and palette registers are **write-only** — you
cannot read back the current map or palette, so software must shadow them in RAM — and the
`$FFC0–$FFDF` SAM block is **set/clear paired** (write to the even address clears the bit,
odd sets it), a holdover from the MC6883.

---

## 10. What this means for `arm6309`

The comparison is not academic. Several `arm6309` design decisions are downstream of the
GIME's arbitration model, and would have to be different for a VIC-II machine.

1. **No video-driven bus arbitration to emulate.** The GIME has no `BA`/`RDY`-style
   request. The *only* thing that halts a CoCo 3 CPU is `/HALT` from the floppy `DRQ`
   (plan.md §2.2) — an event that is slow, byte-paced, and honoured at instruction
   boundaries. A comparable 6510 replacement would have to sample `RDY` inside the tight
   loop and implement the "continue for up to three write cycles, then stop on the next
   read" rule, in a window measured in tens of nanoseconds. **That constraint does not
   exist here, and its absence is a meaningful part of why the Phase 1 timing budget
   closes.**

2. **The `t_AD` = 110 ns deadline is the *only* hard deadline.** Because the GIME never
   stretches or steals a cycle, E and Q are metronomic between speed switches, and the
   post-read critical path is the whole problem (plan.md §3.3). There is no second,
   asynchronous deadline layered on top.

3. **E and Q are GIME outputs and change rate without notice.** Reinforces the edge-driven
   requirement — never a calibrated delay. §3.1 above.

4. **Cycle counts are directly comparable to real hardware.** Since neither chip inserts
   wait states into a CoCo 3 bus cycle, the emulator's cycle count *equals* the host's,
   always. This makes the planned logic-analyzer A/B against a real HD63C09E a clean
   equality test rather than a statistical one — a luxury a C64 project would not have,
   where the correct trace depends on raster position and sprite state.

5. **The accuracy bar is the raster split, not the boot.** Mid-frame `$FFBx` palette writes
   and `$FF98`/`$FF99` mode changes are timed against `HBORD`/timer FIRQ. A one-cycle drift
   is a visible tear. "It boots" is necessary, not sufficient.

6. **The GIME timer at `TINS=0` is a free calibration reference.** It ticks once per scan
   line (63.695 µs) from a crystal, independent of the CPU clock. Reading it across a known
   instruction sequence gives an absolute timing check against real silicon — worth wiring
   into the Phase 1 test harness.

7. **Write-only registers matter for correctness testing.** `$FFA0–$FFAF` and `$FFB0–$FFBF`
   cannot be read back. Any test that assumes readback will silently pass on a naive
   emulator and fail on hardware.

8. **The GIME decodes `$FF00–$FFFF` itself** and drives `CTS*`/`SCS*`/`SLENB*`. The CPU
   module does not need an I/O map — it just drives the bus and lets the GIME decode. One
   less thing to get wrong.

---

## 11. Verdict

| Dimension | Winner |
|---|---|
| CPU bus friendliness | **GIME**, decisively — no cycle stealing, ever |
| Memory architecture | **GIME** — 512 KB MMU with two task banks vs a 16 KB window |
| Resolution and colour depth | **GIME** — 640×225, 16 free colours, no attribute clash |
| Text / productivity | **GIME** — 80 columns with per-character fg, bg, blink, underline |
| Palette flexibility | **GIME** — 16 of 64, programmable, mid-frame |
| Clock headroom | **GIME** — 2× runtime speed switch with the display intact |
| Sprites and collision | **VIC-II**, uncontested — the GIME has none |
| Smooth scrolling | **VIC-II** — per-pixel both axes vs byte-granular |
| Raster effects | **VIC-II** — programmable raster compare vs counting HBORDs |
| Video output quality to a TV | **VIC-II** — separate luma/chroma |
| Documentation depth | **VIC-II** — cycle-exact community documentation, unmatched |

The GIME is a **1986 systems chip**: an MMU, an interrupt controller, and a high-resolution
display generator that stays out of the CPU's way, built to run a paged multitasking OS.
The VIC-II is a **1982 games chip**: sprites, per-pixel scrolling, and a cycle-exact raster
hook, willing to take the CPU's bus cycles to get them.

Four years apart, aimed at different machines, and each is clearly better at what it was
built for. For the specific purpose of dropping a synthesised CPU into the socket, the
GIME's restraint is the gift that makes the project feasible.

---

## 12. Open items — verify before relying on

- ⚠ **GIME video burst mechanism.** §4.2 derives ~199 ns/byte within the E-low phase and
  infers fast-page-mode bursts from 150 ns DRAM. The service manual states only that DRAM
  "must be twice as fast as required by the CPU alone." Confirm with a logic analyzer on
  RAS*/CAS* during a 640×4-colour display.
- ⚠ **`$FF9F` horizontal offset multiplier.** Byte or 2-byte increments? The service manual
  gives bit names only. Measure it.
- ⚠ **GIME 1986 vs 1987 mask revisions.** Documented differences exist (timer reload
  behaviour and border/interrupt edge cases are the usual claims) but are not in the
  service manual. Identify which part is in the target machine before chasing any timing
  discrepancy.
- ⚠ **CoCo 3 dot clock for 640-pixel modes.** Stated as 14.31818 MHz by inference from the
  28.63636 MHz master ÷2; not stated in the excerpt read.
- ⚠ **VIC-II figures throughout** are recalled from Bauer (1996) and the PRG, not verified
  against a document in this repo. The per-line access totals in §4.2 in particular are an
  approximation of a mechanism whose exact cycle allocation is parity- and
  sprite-index-dependent.
