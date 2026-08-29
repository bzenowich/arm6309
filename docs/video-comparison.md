# Three Video Systems, Side by Side

## The `arm6309` Card vs. the GIME vs. the VIC-II

**Question this answers:** the card specified in [`graphics.md`](../video/docs/graphics.md) is an
adaptation of colormin's 256-colour design to a 6309 machine. How does it actually compare
to the two chips it stands in the tradition of — the **GIME** (Tandy CoCo 3, 1986) and the
**VIC-II** (Commodore 64, 1982)?

The card is a **1989–90-plausible discrete design**; the other two are single-chip ASICs
from 1986 and 1982. That gap is the whole story: three to seven years of silicon, and
36 packages instead of one.

---

## 0. Sources and confidence

| Claim class | Source | Confidence |
|---|---|---|
| `arm6309` card geometry, bandwidth, register map, chip count | [`graphics.md`](../video/docs/graphics.md) §§2, 6, 7, 9, 11, 12, 14 | **specified, not built** — timing closes on paper |
| CPU-side timings for the card | `graphics.md` §7.3 | ⚠ scales on an assumed **one write per 5 core cycles** — flagged there for verification |
| GIME registers, MMU, palette, modes, arbitration | *Color Computer 3 Service Manual* (Cat. 26-3334), pp. 10–20, §5.2–5.3 — [`coco3_ServiceManual.pdf`](../reference/manuals/coco3_ServiceManual.pdf) | **verified against the PDF** |
| VIC-II cycle behaviour, registers, timing | Bauer, *The MOS 6567/6569 video controller* (1996); *C64 Programmer's Reference Guide* | recalled, widely corroborated — **not** verified against a document in this repo |
| GIME horizontal scroll granularity | Service manual says byte; *Unravelled* says 2 bytes | ⚠ **unresolved — verify on hardware** |

Rows marked ⚠ are inferences or derived arithmetic, not primary-source figures.

---

## 1. Display

| | **arm6309 card** | GIME (CoCo 3, 1986) | VIC-II (C64, 1982) |
|---|---|---|---|
| Dot clock | **25.175 MHz — the VGA standard clock** | 14.31818 MHz (640-px modes) ⚠ | 8.181816 MHz NTSC / 7.881984 PAL |
| Line rate | **31.469 kHz** | 15.7 kHz | 15.73 kHz NTSC / 15.625 PAL |
| Frame rate | **70.09 Hz** | 59.92 Hz NTSC / 50 PAL | 59.83 Hz NTSC / 50.12 PAL |
| Output | **VGA only** — no TV, no composite | analogue RGB, composite, RF | composite + **separate luma/chroma (S-video)** |
| Best mode at 640 px | **640×200 × 256 colours** | 640×225 × 4 colours | — (no 640 mode) |
| Best mode at 320 px | n/a — 8bpp everywhere | 320×225 × 16 colours | 320×200, **2 colours per 8×8 cell** |
| Best multicolour mode | n/a | n/a | 160×200, 4 colours per 4×8 cell |
| Vertical resolutions | 200 / 240 / **400 / 480 progressive** | 192 / 200 / 225 | 200 |
| Frame bytes, peak | **128,000** (307,200 at 640×480) | 36,000 | ~10,000 (8 K bitmap + 1 K matrix + 1 K colour) |
| Legacy compatibility modes | none | **11 CoCo 1/2 VDG modes** | none |

The card is the only one of the three that produces a signal a modern display will lock
without a scaler, and the only one that cannot drive a period television.

---

## 2. Colour

| | **arm6309 card** | GIME | VIC-II |
|---|---|---|---|
| Simultaneous colours | **256** | 16 | 16, subject to the cell rule |
| Total palette | **65,536** (RGB565 LUT) | 64 (RGB222 per gun) | **16, fixed in silicon** |
| Programmable palette | **yes** | yes | **no** |
| Palette readable by the CPU | **yes** — `'245` read-back (§3.2) | **no** — write-only, shadow it in RAM | n/a — nothing to program |
| Attribute clash | **none** — chunky 8bpp | **none** — every pixel indexes the palette | **severe** — the defining C64 limitation |
| Independent border colour | yes (`BORDER`) | yes, from all 64 | yes, from the 16 |
| Mid-frame palette writes | yes | yes | not possible |
| Grey ramp | 24 exact greys, tint ≤ 4/255 | 2 exact greys (4-level blue grid) | fixed ladder, 9 usable greys ⚠ |

The card boots an **RGB332 identity palette** (§9), so RGB332 software is bit-identical to
a fixed-ladder card while the LUT stays available for fades, cycling and per-image
quantisation.

---

## 3. Memory

| | **arm6309 card** | GIME | VIC-II |
|---|---|---|---|
| Framebuffer lives in | **dedicated 512 KB SRAM**, separate from 512 KB system RAM | main DRAM, shared with the CPU | main DRAM, shared with the CPU |
| Video address reach | 19 bits / 512 KB, **all scannable** | 19 bits / 512 KB | **14 bits / 16 KB window** |
| CPU access to the framebuffer | MMU-mapped + `WPTR`/`VDATA` (§6.3, §11) | direct — it is just RAM | direct — it is just RAM |
| Framebuffer read-back | **yes** — colormin's write-only rule reversed (§11) | yes | yes |
| Video base granularity | **1 row vertically, 1 pixel horizontally** | 8 bytes (`$FF9D`/`$FF9E`) | 1 KB screen, 2 KB character base |
| Off-screen working space | **384 spare columns + 312 spare rows** in one 1024×512 torus | whatever RAM you spare | inside the same 16 KB window |
| Holes in the video window | none | none | **character ROM shadow** in banks 0 and 2 |
| Colour storage | in the pixel byte | in the pixel bits | **separate 1024×4 static colour RAM** off the video bus |
| CPU memory management | **MMU inside `arm6309`**, GIME-register-compatible | **8-page MMU, 2 task banks** | none — PLA + 6510 port `$01` |

---

## 4. Bandwidth, and who pays for it

| | **arm6309 card** | GIME | VIC-II |
|---|---|---|---|
| Peak video fetch | **640 B/line = 20.1 MB/s** | 160 B/line = 2.51 MB/s | 80 B/line on bad lines + sprite fetches |
| Spare memory bandwidth for drawing | **~34 M accesses/s** (§2.1) | none — drawing is CPU stores into DRAM | none |
| Ratio of card bandwidth to what the CPU can consume | **~80×** | ~1× | <1× |
| Steals CPU cycles for video | **never** — static slot assignment (§5) | **never** | **yes — bad lines** (~40 cycles) |
| Steals CPU cycles for sprites | n/a | n/a | **yes** — 2+ per sprite per line |
| Worst-case CPU cycles lost per line | **0** | **0** | **~46 of 63** ⚠ |
| Is instruction timing data-independent? | **yes** | **yes** | **no** — depends on raster position and sprite state |
| CPU clock | **2.098 MHz** (3.147 MHz option) | 0.894886 / 1.789773 MHz | 1.022727 MHz NTSC |

This is the row group that most shapes each machine's software. Two of the three never
touch the CPU; the VIC-II funds its sprites out of the 6510's cycle budget.

---

## 5. Drawing cost

Screen sizes differ by an order of magnitude, so read this as *cost per screen*, not as a
like-for-like rate.

| | **arm6309 card** | GIME | VIC-II |
|---|---|---|---|
| Pixels on screen, peak mode | 128,000 | 144,000 (640×225×2bpp) | 64,000 (320×200) |
| Bytes the CPU must write for a full clear | **~500** (span-solid) | 36,000 | ~9,000 |
| Time to clear the screen | **~1.2 ms CPU, 5.1 ms to retire** | ~55–120 ms ⚠ derived, technique-dependent | ~40 ms ⚠ derived |
| Pixels moved per CPU write | **8** (span writer), 1 (direct) | 4 at 2bpp, 2 at 4bpp | 8 at 1bpp |
| Bulk block move | **`TFM`, 3 cycles/byte ≈ 700 KB/s** | `TFM` on a 6309-upgraded machine; else ~10 cycles/byte | ~5–6 cycles/byte, 6502 loop |

The span writer is what makes the card's 128,000-pixel screen cheaper to clear than the
VIC-II's 64,000-pixel one, on a CPU running at twice the clock. Without it the card would
be the *slowest* of the three to fill.

---

## 6. Text

| | **arm6309 card** | GIME | VIC-II |
|---|---|---|---|
| Character generator | **none — software glyphs via the span writer** (§7) | **on-chip ROM** | off-chip ROM, fetched over the video bus |
| Text geometry | **80×25** at 8×8 | 32 / 40 / **80** columns, 8 or 9 lines per row | 40×25 at 8×8 |
| Colour per cell | **any of 256 fg + any of 256 bg** | 8 fg + 8 bg (palette entries 0–7) | 1 fg of 16 + **one global** bg |
| Hardware attributes | none | **blink, underline** | none |
| Cost per cell | 13 writes ≈ 31 µs (§7.2) | **2 bytes, zero CPU beyond the write** | **1 byte + 1 colour nibble** |
| Scroll one line | **~2.5 ms** (render row, `VSCROLL += 8`) | one register write | ~10 ms ⚠ derived (move 1 K screen + 1 K colour) |
| Mixing text and graphics | **yes, per pixel — it is all one bitmap** | no — mode is global | no, except via raster splits |

The GIME's hardware character generator is its clearest structural win over the card. The
card buys part of it back with per-cell 256-colour freedom and free text/graphics mixing.

---

## 7. Scrolling

| | **arm6309 card** | GIME | VIC-II |
|---|---|---|---|
| Horizontal fine scroll | **per pixel** — `HSCROLL[9:2]` + output phase `[1:0]` (§8) | **byte granular at best** ⚠ (possibly 2 bytes) | **per pixel**, 0–7 (`$D016`) |
| Vertical fine scroll | **per pixel** — `VSCROLL += 1` | within a character row (`VSC3:0`) | **per pixel**, 0–7 (`$D011`) |
| Virtual (wider-than-screen) buffer | **1024×512 torus** | `HVEN` → fixed 128-byte rows | no |
| Coarse scroll | free — it is the same register | 8-byte steps | move video matrix, 1 KB steps |
| Hiding the scroll-in edge | off-screen columns are inside the torus | no equivalent | **38-column / 24-row narrowing** |
| Double buffering | **one write to `VSCROLL`** | change the video base | change `$D018` |

Two of the three scroll per pixel in both axes for free. The GIME is the odd one out, and
CoCo 3 software pre-shifts bitmaps in software to compensate.

---

## 8. Acceleration

| | **arm6309 card** | GIME | VIC-II |
|---|---|---|---|
| Hardware sprites | **none** | **none** | **8** — 24×21 hires or 12×21 multicolour |
| Sprite expansion / priority | n/a | n/a | 2× in X and Y, per-sprite priority vs foreground |
| Collision detection | n/a | n/a | **sprite-sprite and sprite-background, with interrupts** |
| Fill / span engine | **span writer** — mask and solid, 8 px per write | none | none |
| Display list / copper | **reserved, ≈5 ICs + 2 GALs** (§10.3) | none | none |
| Blit datapath | **deferred** — ~10 more GALs (§10.1) | none | none |
| Practical moving-object count | CPU-bound, no hardware help | CPU-bound, no hardware help | **16–24 via sprite multiplexing** |

For an action game, the VIC-II's sprites are worth more than every resolution and colour
advantage on this page. Neither of the other two has an answer to them.

---

## 9. Interrupts

| | **arm6309 card** | GIME | VIC-II |
|---|---|---|---|
| Vertical interrupt | **VBL**, one GAL macrocell (§12.1) | `VBORD` | via raster compare |
| Raster compare | **true line compare in the emulator** — any number of values, changeable per line (§12.2) | **none** — count `HBORD` every line, or repurpose the timer | **yes** — any of 312 lines (`$D012`) |
| Cost of a mid-frame split | one timer read at an instruction boundary | one interrupt per 57 CPU cycles, or the 12-bit timer | write one register and return |
| Interrupt sources | VBL + line compare (+ MCU timers) | **6** — `TMR`, `HBORD`, `VBORD`, and 3 external | 4 — raster, 2 collision, light pen |
| Per-source IRQ/FIRQ routing | inherited — `$FF92`/`$FF93`-compatible | **yes, per source** | no — single IRQ line |
| Programmable timer | in the MCU | **12-bit, auto-reload** (`$FF94`/`$FF95`) | none — the CIAs provide it |

The card's raster compare is the one place it is unambiguously better than the chip it
replaces, and it costs **one GPIO pin and a timer** (§12.2) — because the CPU is already a
microcontroller that knows the beam position.

---

## 10. Integration and cost

| | **arm6309 card** | GIME | VIC-II |
|---|---|---|---|
| Packages | **36 ICs** (32 if the tri-state pixel bus closes) | **1 custom ASIC** (TCC1014, large DIP) | **1 custom ASIC** (40-pin DIP) |
| Also provides | video only | **MMU, interrupt controller, timer, DRAM control, device-select decode, CPU clock** | master oscillator, ϕ0, DRAM control + refresh, light pen |
| What the system needs alongside it | MMU and raster compare **inside `arm6309`** | very little — it absorbed the SAM and the VDG | **PLA for banking, 2× CIA for timers and interrupts** |
| Programmable logic | 8 × GAL22V10 | none — mask ROM | none |
| Power | 450–650 mA ⚠ estimate, GAL-dominated | one chip | one chip, famously hot |
| Area | ~140 cm² on a 160 cm² Eurocard | a socket | a socket |
| Buildable from parts available today | **yes** | no | no |

That last row is the card's real justification. The other two columns describe chips nobody
can buy.

---

## 11. Verdict

| Dimension | Winner |
|---|---|
| Colour depth and resolution | **arm6309 card** — 256 of 65,536 at 640×200, against 16 of 64 and 16 fixed |
| Display-mode range | **arm6309 card** — up to 640×480 progressive, VGA-standard timing |
| Memory bandwidth | **arm6309 card** — ~80× what its CPU can consume |
| Drawing throughput | **arm6309 card** — the span writer, by an order of magnitude |
| Scrolling | **arm6309 card** and **VIC-II** — both per-pixel in both axes; GIME last |
| Raster interrupts | **arm6309 card** and **VIC-II** — true compare; the GIME has none |
| CPU bus friendliness | **arm6309 card** and **GIME** — neither ever steals a cycle |
| Moving objects | **VIC-II**, decisively — 8 sprites with collision, and nothing else has any |
| Text, as specified (Rev A) | **GIME** — hardware character generator, 80 columns, attributes, zero CPU |
| Text, with `graphics.md` §6.4 | **arm6309 card** — 80×25 at 2 writes/cell, and **256 attribute pairs from all 65,536 colours** against 8 fg × 8 bg |
| Tiled backgrounds | **arm6309 card** with §6.4 — an **8bpp tilemap with no attribute clash**, which neither period chip can express |
| Video output options | **GIME** — RGB, composite and RF; the card is VGA-only |
| Colour into a television | **VIC-II** — separate luma/chroma, a fixed palette chosen with care |
| Integration | **GIME** — five subsystems in one package |
| Parts count and power | **GIME** and **VIC-II** — one chip each, against 36 |
| Cycle-exact emulation of the *host* CPU | **GIME** — no video arbitration to model at all (`coco3_c64.md` §10) |
| Availability in 2026 | **arm6309 card** — the only one you can still build |

**Summary.** The card wins every axis that memory bandwidth and colour depth can buy,
because it is spending 36 packages and three to seven years of hindsight to do it. It loses
on exactly the things integration buys: TV output, one chip instead of a Eurocard — and it
has no answer at all to the VIC-II's sprites, which remain the single best-spent transistor
budget of the three.

**The text row is the one that moved.** It was the GIME's clearest structural win, and
`graphics.md` §6.4 closes it for **+1 IC and 1–2 GALs**: the tile address is bit
concatenation rather than arithmetic, and the colour path costs nothing because the palette
LUT is 32K×8 ×2 with 256 entries used — the attribute table lives in the dead 127/128 of
its address space. Two qualifications, both real:

- **It is a proposal, not the specified card.** §6.4 is one section old and its gating item
  — whether the scan-address and sequencer GAL pairs have the spare *pins* — is open
  (`graphics.md` §19 item 15). Until that fit closes, Rev A's row above is the true one.
- **The GIME still wins the thing it was built for.** Its character generator is in
  silicon at zero marginal cost; this one costs packages, GAL capacity, and a mode that
  cannot mix with per-pixel graphics except at a scanline boundary via the list engine.

What does *not* have a period equivalent is §6.4's Variant A: an 8bpp tilemap where every
pixel still indexes the full palette. Both period chips' tile modes are 1bpp with per-cell
attributes — the compromise that produces the VIC-II's attribute clash. Trading 64:1 write
compression for **no** loss of colour freedom is a trade neither 1982 nor 1986 could make,
and it is available here only because the framebuffer is chunky and the bandwidth is
already paid for.
