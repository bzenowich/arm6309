# Video for an arm6309 Machine
## What Carries Over From `colormin`, What Has To Change

**Question this answers:** the 256-colour card designed for the Minimal 64x4
([`~/code/colormin/docs/minimal256.md`](../../../colormin/docs/minimal256.md), plus
[`blitter.md`](../../../colormin/docs/blitter.md) and
[`backplane.md`](../../../colormin/docs/backplane.md)) is a good card for *that*
machine. How much of it is right for a **6309 machine built around `arm6309`**,
running **NitrOS-9 Level 2**, with **256 colours, 80×25 text, a scrolling
bitmap, and a blitter**?

**Short answer: the architecture transfers almost intact; the bus interface and
the geometry do not, and roughly a third of the card's complexity exists only to
protect MinOS and can be deleted outright.**

**Constraints taken as given (yours):**
- RGB332 is the colour model you asked for; palette lookup is *nice, not required*.
- 80×25 text ⇒ **640×200 is preferred over 480×200**.
- Bitmap with smooth scrolling, and a blitter.
- **No CPLDs or FPGAs on the graphics card.** GALs are in (colormin already uses 8).
- Period-appropriate silicon. VGA (1987), GAL22V10 (1986), 1 Mbit SRAM (~1989–90)
  and 25.175 MHz all place this card credibly at **1989–1990** — the same window
  the CoCo 3 and the IIgs were still current in.

---

## 0. Summary — the verdict in one table

| colormin feature | Verdict for an arm6309 machine | § |
|---|---|---|
| **Chunky 8bpp, 4-way SRAM interleave** | **Keep.** The bandwidth argument is unchanged and still wins. | §2.1 |
| **Posted-write capture on the write strobe** | **Keep**, retargeted to E-fall + `R/W` low. Direct analogue. | §3.1 |
| **Span writer (mask / solid, `WFG`/`WBG`)** | **Keep — and it matters more here.** The 6309 writes ~2.4× slower than the 64x4 CPU. | §7 |
| **Separate scroll counters, sync untouched** | **Keep verbatim.** Still the right way to scroll. | §8 |
| **SRAM register file + `/245` read-back** | **Keep.** Cheaper here — a 6809 bus read window is 2–3× wider. | §3.2 |
| **256 × 16 b palette LUT** | **Keep, with an RGB332 identity palette at boot.** §9 argues this satisfies your RGB332 constraint at no cost in software. | §9 |
| **Blitter + display-list engine** | **List engine yes; blit datapath defer.** The 6309's `TFM` plus the span writer cover most of the gap, and 18 GALs is where "no CPLD" starts to hurt. | §10 |
| **Arbitration priority rule / preemption** | **Keep the rule, delete the mechanism.** Phase-locking makes CPU arbitration static. | §5 |
| **MODE=0 bit-exact stock 1bpp path** | **Delete.** −4 ICs, −1 clock domain, −2 open items. Pure win. | §4 |
| **`$4000–$7FFF` broadcast window + RAM shadow write** | **Delete.** An artefact of MinOS compatibility. | §4 |
| **`BANK` register** | **Delete.** The machine has an MMU; that *is* the banking mechanism. | §6 |
| **VRAM write-only** | **Reverse — make it readable.** Now affordable, and worth a lot. | §11 |
| **Card-local asynchronous 20 MHz dot clock** | **Replace** with one system master clock; derive E and Q from it. | §5 |
| **480×200, 6×8 cells, 512 B stride** | **Replace** with 640×200, 8×8 cells, 1024 B stride. | §6 |
| **No interrupt source** | **Add VBL + raster-compare interrupts.** NitrOS-9 needs a tick; you want raster splits. | §12 |

**Net: ~33 ICs (37 with the `'153` pixel mux), against colormin's 35 (39).**
Higher resolution, readable VRAM, raster interrupts, one clock domain — and
fewer packages, because deleting the stock-compatibility path pays for all of it.
Budget in §14.

---

## 1. Why the two machines pull the design in different directions

| | Minimal 64x4 Redux | arm6309 machine |
|---|---|---|
| CPU | 4-phase microcoded TTL, 8 MHz bus clock | HD6309E (synthesised), E/Q bus |
| CPU write rate, sustained | ~16,000 writes/frame (≈1 M/s) | **~6,000 writes/frame (≈420 k/s)** |
| Address space | 64 KB flat, banked at `$8000` | 64 KB logical, **MMU-mapped**, ≥512 KB physical |
| Existing OS to protect | **MinOS, bit-exact 1bpp video** | **none** — NitrOS-9 is ported, not preserved |
| Bus read path | awkward (`/INH` race, 125 ns phase) | **native** — `t_ACC` 330 ns at 2 MHz |
| Bus stall mechanism | `/WAIT` clock gating, exercised but bolted on | E stretching — **free**, the emulator is edge-driven |
| Clock relationship | mainboard 16 MHz **fixed**, card asynchronous | **you choose one master crystal for the whole machine** |
| Block move | none | **`TFM`**, ~3 cycles/byte, in the instruction set |

Four of those rows change the card materially, and three of them change it in
your favour. The one that hurts is the write rate: **the 6309 is the slowest part
of this machine**, which is exactly the argument for keeping the span writer and
for eventually building the list engine.

---

## 2. What transfers unchanged, and why it is still right

### 2.1 Chunky 8bpp in 4-way interleave

The reasoning in minimal256.md §3.1 — that 2-way interleave is a *cliff*, not a
slope, because a 72 ns access does not fit twice into the per-chip video cadence
— survives the move to 640 pixels intact, with less margin:

| | colormin (480 px, 20 MHz) | arm6309 (640 px, 25.175 MHz) |
|---|---|---|
| Dot period | 50.0 ns | **39.72 ns** |
| 4-byte fetch slot | 200 ns | **158.9 ns** |
| Per-chip access (12 GAL + 55 SRAM + 5 setup) | 72 ns | 72 ns |
| Slack in the slot | 128 ns | **86.9 ns** |
| Spare accesses per chip per slot | 1 | **1** — still exactly one |

**The no-stall guarantee survives.** A direct CPU write still finds a slot within
one fetch period, so it never waits. If 55 ns proves marginal in layout, the
AS6C1008-45 grade takes the access to 62 ns and the slack to 96.9 ns.

Free accesses for the span writer and blitter, at 70 Hz:

```
active display : 160 slots/line x 1 spare x 4 chips x 400 lines  = 256,000
hblank         : 6.36 us / 72 ns x 4 chips x 400 lines           = 141,000
vblank         : 49 lines x 31.78 us / 72 ns x 4 chips           =  86,000
                                                          total  ~ 483,000/frame
```

≈ **34 M accesses/s**, against a CPU that can issue ~420,000 writes/s. The card
has ~80× more memory bandwidth than the CPU can consume. Bandwidth is not the
constraint on this machine — **the CPU is** — which is the single most important
number for deciding what to build.

### 2.2 The rest of the transferable core

- **Posted-write capture discipline** (latch address + data on the write strobe,
  retire in a free slot) — unchanged in shape, retargeted in §3.1.
- **Scroll by giving the address generators their own loadable counters** while
  sync generation stays put (minimal256.md §5) — this is the correct answer in
  any machine and transfers verbatim.
- **The SRAM register file** with `WFG`/`WBG` adjacent so the mask bit *is* an
  address line (minimal256.md §4.3) — a genuinely good trick, keep it.
- **Pipeline discipline**: index latch → LUT → output latch, break-before-make
  output enables, R-2R ladders over binary-weighted.
- **The arbitration *rule*** (video → CPU → list engine → span → blit, everything
  below tier 1 preemptible at an access boundary). Keep the rule even though §5
  removes most of the machinery that used to implement it.
- **GAL policy.** 8× GAL22V10 on the card is fine and period-honest.

---

## 3. The bus interface — the largest mechanical change

### 3.1 6809E strobes instead of `/MRD` / `/MWR`

colormin's card keys off `/MWR`'s trailing edge with address and data settled.
The 6809E/6309E bus gives you the same thing under different names:

| 64x4 bus | 6809E bus | Note |
|---|---|---|
| `/MWR` trailing edge | **E falling edge, `R/W` low** | Write data is valid before E rises and held `t_DHW` ≥ 30 ns past E-fall |
| `/MRD` asserted | **E high, `R/W` high** | Card must drive D0–D7 by `t_DSR` before E falls |
| `16M` / `8M` | **E and Q** | Q leads E by 90° |
| `/IOSEL` per slot | mainboard `'138` on the I/O page | Keep the geographic-slot idea — it is a good one |
| `/WAIT` (clock gating) | **stretch E** | §3.3 |
| `/INH` | not needed | the MMU decides what answers |

**One capture register, one edge, same discipline.** The posted-write path is a
rename, not a redesign.

**Reads are dramatically easier than on the 64x4.** backplane.md §4 gives the
card 60 ns to drive data after `/MRD`·`/IOSEL`; minimal256.md §11 item 10 flags
that as a real risk. The 6309E gives `t_ACC` = **330 ns at 2 MHz** (185 ns at
3 MHz) from address-valid to data-required. That is 5× the budget, and it is why
§11's readable VRAM becomes affordable.

### 3.2 Register read-back stops being a risk

minimal256.md §4.3 adds a `'245` so registers read back, and §11 item 10 lists
"can the card drive valid data within one 8 MHz bus phase" as an open item. On a
6809 bus at 2.098 MHz, the SRAM + `'245` path (~28 ns) against a 330 ns budget is
not a question worth benching. **Keep the register file and the `'245`; close the
open item.**

### 3.3 `/WAIT` becomes free, because the emulator is edge-driven

plan.md §2.1 makes the emulator **purely edge-driven — no calibrated delays, no
assumed E period, every action keyed off an observed transition.** That was
written to survive the CoCo 3's runtime 0.895 ↔ 1.79 MHz switch. It has a second
consequence in a machine you design:

> **A stretched E cycle is transparent to `arm6309`.** The card can assert
> `/WAIT`, the motherboard's E/Q generator holds E low for another few dots, and
> the emulator simply observes a longer cycle. No emulator change, no new state.

So colormin's `SPANBUSY` + `/WAIT` backstop (§4.2.1) transfers directly and is
*less* exotic here than it was there — and it also becomes the fallback for VRAM
reads at the higher clock (§11). A real HD63C09E would tolerate the same
stretching, so this does not compromise the "drop a real 6309 in and it still
works" property.

---

## 4. What you delete, and what deleting it buys

About a third of colormin's complexity exists to guarantee that **MinOS keeps
seeing a bit-exact 400×240 1bpp screen**. You are building the machine and
porting the OS, so none of it is load-bearing.

| Deleted | Packages | Also deletes |
|---|---|---|
| Stock 1bpp VRAM (`AS6C62256`) | −1 | the whole second memory and its write path |
| Stock 1bpp shifter (`'166`) | −1 | |
| MODE=0 LUT-bus replication (`'244`) | −1 | the mode-gating argument in §6 there |
| Posted-commit synchroniser (`'74`) | −1 | **an entire clock-domain crossing** (§5) |
| Dual video timing (16 MHz / 20 MHz) | 0 | minimal256.md §11 items 1 and 2 |
| Dual stride in the scan GALs | 0 | product terms on the tightest-fitting pair |
| `$4000–$7FFF` broadcast + RAM shadow write | 0 | a whole compatibility hack in the memory map |
| `BANK` register and window decode | 0 | §6 — the MMU replaces it |

**−4 ICs, −1 clock domain, −2 open items, and the scan/sequencer GALs get their
product terms back** — which matters, because minimal256.md §11 items 4 and 11
both flag GAL fitting as the most likely place that design breaks.

This is the single largest structural difference between the two cards, and it is
entirely in your favour. It also removes the *reason* colormin needed a second
oscillator, which is what §5 exploits.

---

## 5. One clock for the whole machine — and static arbitration

### 5.1 The change

colormin runs the card's 8bpp mode from a **card-local 20 MHz oscillator,
asynchronous to the 16 MHz bus**, because it may not touch mainboard timing.
Posted-write commits therefore cross domains through a 2-stage `'74`
synchroniser, and the sequencer has to *search* for a free slot.

You have no such constraint. **Put one 25.175 MHz oscillator in the machine and
derive E and Q from it by division.**

```
25.175 MHz ──┬──► dot clock (video card)
             │
             └──► ÷12 ──► E at 2.0979 MHz   (Q = same divider, 3 dots early)
                  ÷8  ──► E at 3.1469 MHz   (stretch mode, software-selectable)
```

Both divisors are integral in **fetch slots** (4 dots), which is the property
that matters:

| E rate | Bus cycle | Fetch slots per bus cycle | Core cycles/bus cycle @170 MHz |
|---|---|---|---|
| dot ÷ 12 | 476.7 ns | **3** | **81** |
| dot ÷ 8 | 317.8 ns | **2** | **54** |

Against plan.md §3.3's measured numbers — post-read path ~13 core cycles, the
§4.1 microcode step 14 typical / 25 worst — **dot ÷ 12 is comfortable and
dot ÷ 8 is the same budget as the CoCo 3's 3 MHz stretch case** (56.7 cycles),
which plan.md already declares reachable with the §3.6 read latch. Make the
divisor a register bit and you have a CoCo-3-style runtime speed switch, which
the emulator already has to tolerate.

### 5.2 What phase-locking buys

Because E is *derived from* the dot clock, the CPU's bus cycle sits at a **fixed
phase relative to every video fetch**. That converts arbitration from a search
into an assignment:

- The CPU's access lands in a known slot, on the chip selected by
  `address[1:0]`. The sequencer **reserves** it rather than hunting for it.
- The other three chips' spare accesses in that slot go to the span writer or the
  blitter, by a wire, not a state machine.
- **The `'74` synchroniser disappears.** There is no domain to cross.
- minimal256.md §8's "commit: sync (2 stages) + slot arbitration ≥ 200 ns" row
  vanishes from the timing table.

The arbitration *priority rule* of blitter.md §2.3 still applies to the three
requesters that remain dynamic (list engine, span writer, blit datapath). Only
the CPU tier becomes static — and that is the tier whose failure mode was a CPU
stall.

**Caveat to verify:** E must be phase-stable at the divider output across the
÷12 ↔ ÷8 switch, or a speed change lands the CPU slot in the wrong phase for one
cycle. Gate the divisor change to vertical blank — the same discipline
minimal256.md §11 item 2 recommends for its clock switch, for the same reason,
but now on a signal you own.

### 5.3 `arm6309` stays clock-slaved — do not make it the clock master

It is tempting to have the STM32 generate E and Q from TIM1 (PA8/PA9 are
`TIM1_CH1`/`CH2` and could output as easily as capture). **Don't.** Deriving E
from the video master by division instead:

- keeps the bus loop's structure, the input-capture timestamping, and the §3.6
  read latch **exactly as designed and measured** — Phase 1's results stay valid;
- gives the phase-lock of §5.2, which a core-clock-derived E cannot (170 MHz and
  25.175 MHz have no clean integer relationship);
- keeps a **real HD63C09E a valid part for the socket**, which is the A/B
  reference the whole validation strategy rests on (plan.md §6.2).

The one thing that genuinely changes is that **`t_AD` stops being a datasheet
constant and becomes a number you specify.** In the CoCo 3 you must meet 110 ns
because the GIME says so. In your machine the address-valid deadline is whatever
your memory system needs — at 476.7 ns per cycle with a 72 ns SRAM access, 160 ns
is comfortable. That slack is what pays for §6.3's MMU — for the in-CPU version's
translation cycles, or, in the version the machine took, for §6.3.1's 15 ns of
external map propagation.

---

## 6. Geometry: 640×200, and where VRAM lives

### 6.1 640 wide is the right call, and it is nearly free

You asked for 640; here is what it actually costs and buys.

| | colormin 480×200 | **arm6309 640×200** |
|---|---|---|
| Dot clock | 20.0 MHz (card-local, non-standard) | **25.175 MHz — the VGA standard clock** |
| Line | 640 dots, 32.0 µs, 31.25 kHz | 800 dots, 31.78 µs, **31.469 kHz** |
| Frame | 400 lines doubled, ~78 Hz-class | **449 lines, 400 active, 70.09 Hz** |
| Character cell | 6×8 | **8×8** |
| Frame bytes | 96,000 | 128,000 |
| Row stride | 512 | **1024** |
| Ring | 512 × 512 = 256 KB scannable + 256 KB store | **1024 × 512 = 512 KB, all scannable** |
| Dot-path budget | 50 ns | **39.7 ns** |

**Three things make 640 the better fit, beyond legibility:**

1. **`640×200@70` is literally VGA mode 640×400** (25.175 MHz, 800 × 449) — the
   DOS text-mode timing. Every CRT, LCD and scaler locks it without argument.
   colormin's 31.25 kHz / 640-dot line is *close* to standard; this one **is**
   standard.
2. **8-pixel cells make the span-mask writer exactly one write per glyph row.**
   colormin's span-mask serialises a byte and stops at `SPANLEN`; with 6-px cells
   two bits per write are wasted. At 8×8 the mask byte *is* the glyph row. This is
   the existing hardware fitting the new geometry better than the old one.
3. **8×8 fonts drop in.** CP437, the CoCo 3 hi-res font, VT100 line-drawing — all
   8 px wide. A 6-px box-drawing set has to be redrawn by hand
   (colormin's plan.md §4 budgets exactly that job).

**What it costs is dot-path margin, and only that.** §2.1 showed the framebuffer
side still closes. The dot path at 39.7 ns needs two decisions:

| Path | 50 ns (colormin) | 39.7 ns | Answer |
|---|---|---|---|
| Pixel-bus turnaround, 4 tri-state `'574` | ~20 ns, flagged as *the* tightest path | very likely does not close | **Budget the 4× `'153` mux (+4 ICs) as the default**, bench the tri-state version as the saving |
| Index `'574` → LUT SRAM → output `'574` | 8 + 20 + 5 = 33 ns, 17 ns margin | 8 + **15** + 5 = 28 ns, **11.7 ns margin** | Specify **15 ns** LUT SRAM, not 20 ns |

colormin already prices the `'153` fallback at +4 ICs and already treats the
tri-state turnaround as its top bench item; 640 wide simply moves it from
"probably fine" to "assume the fallback". Since §4 hands back 4 packages, this
nets out at zero.

### 6.2 Free modes that fall out of the same hardware

Because the H timing is fixed and the V counter is a GAL, several modes cost
product terms and nothing else:

| Mode | V total / active | Rate | Text | Frame bytes |
|---|---|---|---|---|
| **640×200**, line-doubled | 449 / 400 | 70.09 Hz | **80×25** | 128,000 |
| 640×240, line-doubled | 525 / 480 | 60.0 Hz | 80×30 | 153,600 |
| 640×400, progressive | 449 / 400 | 70.09 Hz | 80×50 | 256,000 |
| 640×480, progressive | 525 / 480 | 60.0 Hz | 80×60 | 307,200 |

**The progressive modes cost no extra bandwidth.** Line-doubling fetches every
row twice; 640×400 fetches 400 distinct rows once. Same 640 bytes per scanline
either way. The only cost is memory, and 512 KB covers even 640×480 single-buffered.

640×480×8bpp on a 6309 is not a mode any period machine had. It is available for
one bit in `CTRL` and a couple of terms in the V-sync GAL, so take it.

### 6.3 The 64 KB problem — and why the `BANK` register goes away

This is the one architectural question colormin never had to answer: the 64x4 has
a flat 64 KB space, so a windowed `BANK` register was the only option. **The 6309
machine has an MMU, because NitrOS-9 Level 2 requires one.** Once the MMU exists,
`BANK` is a second, worse banking mechanism sitting on top of it.

**Recommendation: put the MMU inside `arm6309`, GIME-register-compatible, and map
VRAM flat into the physical address space.** ⚠ **The first half of this was not taken —
see §6.3.1.** The flat physical map stands; the location and the register compatibility
did not survive the single-SKU argument.

```
physical A19..A13  <-- MMU block map, 8 blocks x 8 KB, per task
physical A12..A0   <-- logical A12..A0, untranslated

A19 = 0  : 512 KB system RAM
A19 = 1  : 512 KB VRAM  (the video card's 1024 x 512 ring)
```

Why in the CPU rather than as three chips on the motherboard:

- **Zero external parts.** The map is an 8- (or 16-) entry array and a shift-index-or
  in the emulator's address path — the same shape as the microcode dispatch.
- **NitrOS-9's Level 2 MMU code is GIME-specific.** Emulating `$FFA0–$FFAF`
  faithfully (8 blocks, two task registers, 6-bit block numbers) is the
  difference between porting the memory manager and configuring it.
- **The critical-path cost is affordable *here* and only here.** Translation adds
  ~3–4 core cycles to the post-read path and needs a second `STR` for A16–A19.
  Against the CoCo 3's fixed 110 ns `t_AD` that would be uncomfortable; against
  §5.3's self-specified ~160 ns it is not.

**Two consequences to plan for:**

1. ~~**Use the LQFP64 part for the homebrew CPU card.**~~ **Superseded by §6.3.1 —
   the machine took the external MMU and the LQFP48 stands for both targets.** The
   arithmetic that led here is still correct and is why the in-CPU version needs the
   larger package: plan.md §3.2 closes LQFP48 at 35 of 39 pins for the CoCo 3, and
   an in-CPU MMU adds A16–A19 plus an HSYNC input (§12) on top of that. The
   homebrew module is not a 40-pin DIP, so the package constraint does not apply to
   it — **STM32G431RB / G474RE, LQFP64, same core, same 170 MHz, same source** —
   but the *project* has a reason to want one SKU, and §6.3.1 is how it gets one.
2. **The video card now decodes physical A0–A18 plus a chip select**, not a 16 KB
   window. Any of the eight MMU blocks can be pointed at VRAM, so up to 64 KB of
   framebuffer is directly addressable at once — strictly better than a 16 KB
   window with a bank register, and it is what makes §11's readable VRAM useful.

`WPTR` stays. The auto-incrementing 19-bit pointer is the streaming path and the
span writer's address source; the MMU is the random-access path. Two paths on
purpose, exactly as colormin argues — just with the MMU doing the job `BANK` used
to do badly.

### 6.3.1 The MMU goes on the motherboard — 3 ICs, and one LQFP48 SKU serves both machines

**Decided.** The recommendation above stands as *analysis* — an in-CPU MMU really is
free in parts, and it really is the easier route to GIME register compatibility — but
the machine took the other option, for a reason that is about the project rather than
the address path, and it then decided it did not want the compatibility either. Recorded
in [`machine.md`](../../docs/machine.md) §5 item 6.

> **The deciding argument is one SKU, not one board.** `cpu/docs/plan.md` is written
> against a CoCo 3 drop-in that must be an LQFP48 in a 40-pin DIP footprint (§2.7).
> An in-CPU MMU pushes *this* machine's module to LQFP64. That is two different parts,
> two pinouts, two board files and two bring-up paths for what is otherwise the same
> firmware. Putting the MMU outside buys back the four A16–A19 pins and the LQFP48
> covers both targets. The 48-pin part is also the cheaper and the more available of
> the two — which matters for a board that gets built in ones and twos.

**The three ICs** (period-honest, and what a 1990 machine would really have done — the
SAM/GIME/DAT arrangement):

| Qty | Part | Role |
|---|---|---|
| 1 | 2K×8 SRAM, **15 ns** | the block map, addressed by `{TASK, A15..A13}`, outputting physical A13..A19 |
| 1 | `74HC574` | task select and MMU enable — two bits, at addresses this machine picks (see below), not the GIME's `$FF90`/`$FF91` |
| 1 | GAL (or `'138` + gate) | write decode: steer CPU writes into the map SRAM, and generate the I/O-page override |

Sixteen of the SRAM's 2048 locations are used. A 2K×8 is specified anyway because a
15 ns one is a stocked commodity part and a 16×8 is not.

**Pin budget, this machine, both ways.** From plan.md §3.2's 39 usable pins:

| | in-CPU MMU | external 3-IC MMU |
|---|---|---|
| `A0..A15` | 16 | 16 |
| `A16..A19` | **4** | 0 — the map SRAM emits A13..A19 |
| `D0..D7` | 8 | 8 |
| `R/W`, `E`, `Q` | 3 | 3 |
| `/RESET`, `/NMI`, `/IRQ`, `/FIRQ`, `/HALT` | 5 | 5 |
| `BUS_OE` | 1 | 1 |
| HSYNC in, for §12.2's raster compare | 1 | 1 |
| **Used, of 39** | **38** | **34** |
| Spare | 1 | **5** — debug UART, status LED, and one left |

plan.md §3.2 now carries the same arithmetic with the UART and LED counted as line items
rather than as spares; the two tables agree at 39 either way.

Nothing else in the machine asks the CPU module for a pin. Audio, PS/2, serial and
storage are all bus cards behind geographic `/IOSEL`, and their interrupts wire-OR onto
`/IRQ` and `/FIRQ`, which are in the count already ([`machine.md`](../../docs/machine.md)
§2, §4). The only pin the CPU has acquired since this section was first written is
§12.2's HSYNC input, and it is in both columns.

**The timing argument reverses too, mildly.** The bullet above prices the in-CPU MMU at
~3–4 core cycles on the post-read path plus a second `STR` for A16–A19 — ~18–24 ns
inside `t_AD`. The external map spends 15 ns of SRAM propagation *after* `t_AD`, on the
motherboard, where §5.3's self-specified deadline has slack for it. So the external
version is a small win in absolute time and a real one on the CPU's most deadline-critical
instruction, rather than the cost the "Alternative" framing implied.

**Two details that only exist in this version.** Both are now carried in
[`machine.md`](../../docs/machine.md) §2 and §3; they are stated here because they are
consequences of *this* choice, not of the backplane:

1. **The I/O-page decode must be taken from *logical* A13–A15.** `$FF00`–`$FFFF` has to
   override translation, exactly as it does on a CoCo 3. With the MMU outside, logical
   A13–A15 are on the motherboard — they are the map SRAM's address inputs — but they
   are deliberately **not** on the backplane, which carries physical A0–A18 + A19
   ([`machine.md`](../../docs/machine.md) §2). A0–A12 are untranslated, so the decode is
   `(logical A15..A13 = 111) AND (A12..A8 = 11111)`, and it is the same term that
   already generates `/IOSEL`. Free, but it has to be *drawn* that way.
2. **The enable and task-select bits need a home, and the `$FF` map does not allocate
   one.** A GIME keeps MMU enable in `$FF90` bit 6 and task select in `$FF91` bit 0,
   neither of which is inside the `$FF40`–`$FF7F` geographic window, and
   [`machine.md`](../../docs/machine.md) §3 lists only `$FFA0`–`$FFAF` against the MMU.
   In-CPU those are emulator state and cost nothing; outside they are the `'574`'s two
   bits and need a decode term. **See below — they do not have to be at the GIME's
   addresses**, and putting them in the MMU's own window costs one term instead of two.

**A third detail, common to both:** GIME block numbers are **6 bits**, which reaches
512 KB. This machine's physical map is 1 MB and the block map emits A13..A19 —
**7 bits**. Either implementation needs a seventh bit that a real GIME does not have.

#### GIME register compatibility is not a constraint on this machine

**Owner's call, and it changes what §6.3.1 costs.** Patching NitrOS-9 Level 2's memory
manager to talk to whatever register set this machine actually has is an hour of work,
not a port. So the argument in §6.3's bullets — that faithful `$FFA0`–`$FFAF` emulation
is the difference between porting the memory manager and configuring it — **is priced
and paid**, not deferred as a risk. It is the strongest argument for the in-CPU MMU and
it is the one being spent.

Three things follow, and they are simplifications rather than costs:

- **Detail 2 collapses.** Enable and task select go in the MMU's own window next to the
  block registers. One contiguous decode, no `$FF90`/`$FF91`, and none of it touches the
  machine's four remaining geographic bytes ([`machine.md`](../../docs/machine.md) §5
  item 1) — the MMU is on the motherboard and decodes directly.
- **The third detail stops being an extension.** Define the block registers as 7 bits
  and be done; there is no 6-bit register to stay bug-compatible with.
- **[`machine.md`](../../docs/machine.md) §5 item 3 changes character.** "The MMU
  register set is not written down" was blocked on how faithfully to copy the GIME. It
  is now an ordinary design task with a free hand — and it is the deliverable that
  gates the motherboard's write-decode GAL.

⚠ **What is not free** is the rest of NitrOS-9's CoCo 3 dependence. This machine already
diverges from the GIME at the video registers, the interrupt block, and now the MMU; the
hour is per-subsystem, and nothing here says the *sum* is an hour. It does say the MMU is
not the reason to choose a package.

**What it costs, then.** Three ICs and their board area, a write-decode GAL that is
harder to change than firmware, and a NitrOS-9 memory-manager patch the owner has
priced.

---

### 6.4 Tile and character modes — nearly free, because of three accidents

Neither colormin document has a tile mode, and §7 argues against a hardware
character generator on cost grounds. That argument was about a *bitmap-only* card.
Once the question is asked directly, three things already on this card — each built
for another reason — turn out to be most of a tile fetcher:

1. **The palette LUT is 32K×8 ×2 and uses 256 entries.** §14 buys 65,536 bytes to
   hold a 256 × 16-bit palette. **127/128 of the address space is dead**, with the
   high pins tied off.
2. **The geometry is all powers of two.** The no-adder property that §7.2 works to
   preserve is exactly what makes a tile address free.
3. **GAL22V10 outputs are individually tri-stateable**, and the scan address
   generators (§14) are already loadable counters in GALs.

#### 6.4.1 The tile address is concatenation, not arithmetic

A tile lookup is `base + code × size + row`. With an aligned tile set every term
lands on its own address bits, so **there is no adder** — the same property
minimal256.md §3 establishes for the scan path and §7.2 protects for `WADV`:

```
8bpp tiles, 8x8 (64 B each), 256 tiles = 16 KB, aligned to 16 KB:

  A18..A14   TILEBASE     (register)
  A13..A6    code[7:0]    <- the map byte just fetched
  A5..A3     row[2:0]     <- scan line within the cell
  A2..A0     col[2:0]     <- pixel within the row

1bpp glyphs, 8 B each, 256 glyphs = 2 KB, aligned to 2 KB:

  A18..A11   FONTBASE
  A10..A3    code[7:0]
  A2..A0     row[2:0]
```

The only new element in the datapath is **getting the map byte from the pixel bus
onto the VRAM address bus** — one 3-state `'574`, or **zero packages** if it can be
absorbed into the scan-address GAL as registered macrocells. Each address bit is
then a two-product-term mode mux, so product terms are not the constraint; **spare
GAL pins are**. Settle that at fit time (§19 item 15).

Both variants below need the map fetch **pipelined one cell ahead** of the tile
fetch — a serial dependency, and the same shape of pipelining the card already runs
for index → LUT → output.

#### 6.4.2 Variant A — 8bpp tilemap

Per cell: fetch the map byte, then the 8 tile bytes for this row. **The pixel path
downstream is unchanged** — the bytes flow through the `'153` mux, the index latch,
the LUT and the output latch exactly as bitmap bytes do.

| | Bitmap | **8bpp tilemap** |
|---|---|---|
| Screen memory | 128,000 B | **2,000 B** + 16 KB tile set |
| CPU writes to change one cell | 64 | **1** |
| Display fetch per 8 dots | 8 accesses | 9 accesses |
| Per-chip load per cell (4.4 available) | 2.0 | **2.25** ⚠ |
| Colours | 256, per pixel | **256, per pixel — no attribute clash** |

It costs the same display bandwidth as the bitmap and buys **64:1 write
compression**, which is the right trade on a machine whose documented bottleneck is
the CPU and not bandwidth (§2.1). It also costs the span writer and blitter a little
of their spare-slot budget: 2.25 accesses per chip per cell against 2.0, so the
free-access figure in §2.1 falls by roughly an eighth in this mode.

**A chunky 8bpp tilemap with no per-cell colour limit is not a mode any period
machine had** — the GIME's and VIC-II's tile/character modes are both 1bpp with
cell attributes. This one is strictly a superset.

**Cost: +1 IC, possibly 0.**

#### 6.4.3 Variant B — 1bpp character generator, and what the dead LUT space buys

Per cell: fetch code, attribute, and one font row — **3 accesses per 8 dots against
the bitmap's 8**. The font byte goes to a serialiser; its output bit plus the
attribute chooses the colour.

Here the unused 127/128 of the LUT pays for the whole colour path. Address it as
`{page, attr[7:0], glyph_bit}` — 10 bits, well inside the 15 available:

```
graphics :  LUT[ 0 | 0000000 | pixel[7:0] ]        -> RGB565
text     :  LUT[ 1 | 000000  | attr[7:0] | bit ]   -> RGB565
```

The attribute byte rides the existing pixel bus into the existing index latch; the
glyph bit goes straight to a spare LUT address pin. The page select is one `CTRL`
bit (b5 is reserved in §13). **No comparator, no fg/bg mux, no second colour path.**

What that yields, against the chip this card is replacing:

| | GIME text | **Variant B** |
|---|---|---|
| Attribute combinations | 8 fg × 8 bg | **256, freely defined** |
| Colour space per attribute | 64 | **65,536** |
| Foreground and background | palette entries 0–7 | **any RGB565 pair** |
| Blink / underline | in hardware | in the attribute table, or not at all |
| Bandwidth per line | 160 B | **240 accesses** (code + attr + font) |

240 accesses per line against the bitmap's 640 hands roughly **400 accesses per
line — ~160,000 per frame ⚠** back to the span writer and the blitter.

**Cost: +1 IC (the serialiser) — or 0, see below.**

#### 6.4.4 The span-mask serialiser is shareable

The card already carries a `74HC165` to serialise span masks (§14). **The span
writer is idle in character mode** — software writes code and attribute bytes
directly, and a span-mask write into a tilemap is meaningless — so the two uses are
mutually exclusive by mode and the part can be shared, with a mode input choosing
its load source and clock.

**One requirement:** glyph duty shifts at the 25.175 MHz dot rate, so the part must
be **`74AHC165`**, not `'HC`. That is a grade change on a part already in the BOM.

#### 6.4.5 What it costs, and what it defers

The ICs are not the price. The price is programmable logic, in the two places §19
item 8 already flags:

- The **sequencer pair** gains a second fetch cadence with a serial dependency.
- The **scan-address pair** must switch between a linear scan address and the
  concatenated tile address, and tri-state its low outputs during the tile fetch.

**Budget +1 to +2 GAL22V10** — 38–40 packages against Rev A's 36 — and fit both
pairs before committing. This is the item most likely to fail (§19 item 15).

Against that, two things get cheaper:

- **The blit datapath's 14 ICs become much easier to defer** (§10.3). A tilemap
  redraws itself from the map every frame at zero CPU and zero blit cost, so
  scrolling playfields, backgrounds and status bars stop being blitter work. What
  is left for the blitter is *moving objects*, which is what §10.3 says it is for.
- **Text stops being the span writer's problem.** §7.3's figures, recomputed at
  2 writes per cell (⚠ same 5-cycles-per-store assumption as §7.3, §19 item 1):

| Text operation | Span writer (§7.3) | Character mode |
|---|---|---|
| One cell | 13 writes, ~31 µs | **2 writes, ~4.8 µs** |
| Scroll one line | ~2.5 ms | **~0.4 ms** |
| Full 80×25 redraw, per-cell colour | ~62 ms | **~9.5 ms** |

#### 6.4.6 Three limits, stated plainly

1. **The mode is global** — cells or pixels, not both in one region. But `CTRL` is a
   register, so a list-engine `MOVE` at a scanline boundary switches mid-frame: a
   text status bar over a bitmap playfield, from the display list, with no CPU
   involvement (§10.3). The copper earns its keep again.
2. **Fine horizontal scroll must start the tile fetch mid-tile** — a 3-bit offset
   into the tile row, which is new logic in the address concatenation rather than
   the free `HSCROLL` of §8.
3. **Variant B lands on the tightest path in the card.** §6.1 gives the
   index → LUT → output chain 11.7 ns of margin at 39.7 ns; the serialiser's
   clock-to-Q goes into that chain. It belongs on the bench list beside the
   pixel-bus turnaround (§19 items 2, 3, 17).

**Register space:** `TILEBASE` / `FONTBASE` and the map base fit in `+$17`–`+$19`,
reserved in §13.

#### 6.4.7 Recommendation

**Build Variant A.** +1 IC and 1–2 GALs, every pixel independently coloured, 64:1
write compression on exactly the workload the CPU is worst at, and no change to the
pixel path at all. Variant B is a further +0–1 IC and is worth it for a genuinely
cheap 80×25 console — but note that it reintroduces per-cell colour limits, which is
the one thing this card currently does not have and both period chips do.

## 7. 80×25 text — software glyphs, and a correction to colormin's cost

There is no hardware text mode in either design, and there should not be one here
either: NitrOS-9's windowing draws into bitmaps, a hardware character generator
cannot mix with graphics per-pixel, and it would need its own memory and
serialiser (~8–12 ICs). The span writer is the text engine.

### 7.1 The correction

minimal256.md §4.2 and §10 cost a character cell at **"10 writes — set `WFG`/`WBG`,
then eight span-mask writes of length 6, one per glyph row."**

**That figure holds only for one rendering order and one colour pattern.** After
a span, `WPTR` has advanced by the span length; the next glyph row is one *row
stride* further on. The two orderings available without new hardware both cost
more than 10, and they cost it in different places:

```
  claimed         :  2 colour + 8 mask                          = 10  writes/cell
  cell-major      :  2 colour + 8 x (2 WPTR reload + 1 mask)     = 26  writes/cell
  scanline-major  :  (3 WPTR)/80 + 8 x (2 colour + 1 mask)       = 24.3 writes/cell
```

Cell-major pays a `WPTR` reload per glyph row (the low and middle bytes change;
the high byte usually does not). Scanline-major — render glyph row 0 of all 80
cells, then row 1, and so on — amortises `WPTR` to nothing, because the cells'
row-0 bytes are contiguous, but then `WFG`/`WBG` must be re-set for **every glyph
row of every cell**.

**The claim is true only when adjacent cells share colours**, where scanline-major
collapses to ~8.3 writes/cell. That is the ordinary case for a monochrome console
and the *wrong* case for the design's stated target — 256-colour ANSI art, where
per-cell colour is the point. minimal256.md §4.2's own headline for this mode is
"every cell gets its own colours with no fallback case at all"; that case costs
2.4–2.6× what the table says.

On this machine the honest figure is 62 ms per screen becoming ~150 ms.

### 7.2 The fix, and it costs no packages

**Add a `WADV` pointer-advance mode and shadow `WPTR`'s column field into the
register file.**

- `WADV = 01` ("next row, same column"): when a span ends, reload `WPTR[9:0]`
  from the shadow and increment `WPTR[18:10]`. Stride 1024 is a power of two, so
  this is a reload and an increment — **not an adder** — preserving
  minimal256.md §3's no-adder-anywhere property.
- The shadow is free: a CPU write to `WPTR`'s low and middle bytes **also strobes
  the register file**, exactly the dual-strobe trick minimal256.md §4.3 already
  uses for `CTRL`. At span end the sequencer takes two deferrable file reads to
  restore the column. No latch, no mux.

```
  fixed   :  3 WPTR + 2 colour + 8 mask              = 13  writes/cell
```

Cost: **zero packages** — a register-file address, two sequencer terms, and a
mode input on the `WPTR` counter GALs. It does land on the GAL pair minimal256.md
§11 item 4 already flags for fitting, so fit it early.

A dedicated column-base latch would also work, but it is 9–10 bits — **2× `'574`,
not one** — and it cannot be shared with the blit datapath's own column-base
latches (blitter.md §6.2), because blitter.md §2.3 lets the span writer and the
blitter be in flight simultaneously and preemptible independently. The register-file
shadow is strictly cheaper.

### 7.3 What text then costs on a 2.1 MHz 6309

Assuming a tight store loop sustains roughly one write per 5 core-6309 cycles in
native mode (**verify against real cycle counts** — this is the number the whole
table scales on):

| Task | CPU writes | Time @ 2.098 MHz |
|---|---|---|
| One character cell | 13 | ~31 µs |
| **Scroll one line** (render new row, then `VSCROLL += 8`) | 1,040 | **~2.5 ms** |
| Full 80×25 redraw, per-cell colour | 26,000 | ~62 ms |
| Full-screen clear (128,000 px, span-solid) | ~500 | ~1.2 ms CPU, **~5.1 ms to retire** |

**A terminal never full-redraws** — it scrolls, and scrolling is 2.5 ms plus one
register write. That is the number that matters, and it is comfortable. The 62 ms
full redraw is a mode-change cost, paid once.

Compare the alternative the 64x4 does not have: a `TFM` of a pre-rendered 8×8×8bpp
glyph is 64 bytes at 3 cycles each = 192 cycles ≈ 92 µs per cell — **3× worse than
the span writer**, because the span writer moves 8 pixels per CPU write and `TFM`
moves one. Text belongs to the span writer; `TFM` earns its keep elsewhere (§10.2).

---

## 8. Scrolling — transfers verbatim, with wider registers

minimal256.md §5 is correct as written and needs only the geometry substituted:

- **Vertical:** a separate 9-bit V-address counter supplies row bits A18..A10,
  loaded from `VSCROLL` during vblank. A row is a pixel row, so `VSCROLL += 1` per
  frame is already pixel-smooth. Terminal scroll = render into rows
  `(VSCROLL + 200 .. +207) mod 512`, then `VSCROLL += 8`.
- **Horizontal:** `HSCROLL[9:2]` preloads the H-address counter at the start of
  each line's fetch window; `HSCROLL[1:0]` preloads the **output phase** — which
  of the four interleaved bytes emits first. Sub-pixel horizontal smoothness costs
  zero parts, because the phase counter already drives the 4:1 selection.
  (With the `'153` mux of §6.1 this is a mux-select preload rather than an
  output-enable preload — same two bits, same cost.)

**The torus is now 1024 × 512** with a 640 × 200 window on it. The 384 off-screen
columns are not waste: they are a horizontal margin wide enough for a 1024-pixel
playfield, and together with the 312 unused rows they hold sprite sheets, glyph
caches and display lists — the role colormin gives its separate 256 KB
off-screen store.

**One simplification falls out:** colormin splits its 512 KB at `address[18]` into
a scannable ring and a non-scannable store, which forces blitter.md §6.2 to carry
A18 as a latched bank bit outside the counter chain. Here the scan address is 19
bits and **all 512 KB is scannable**, so SRC and DST are plain 19-bit addresses in
one flat torus. The bank latch and its "does it wrap or spill" question disappear.

Double buffering: two 200-row buffers at rows 0–199 and 256–455, flipped by one
write to `VSCROLL`. 112 rows (114,688 B) plus the column margin left over.

---

## 9. Palette: you asked for RGB332, and you should still build the LUT

Your constraint is "RGB332; palette lookups nice but not required". colormin
**removed** RGB332 in favour of a 256 × 16 b LUT, and minimal256.md §6.1's
argument is worth restating because it is the strongest technical case in either
document:

| | RGB332 direct | RGB565 palette entry |
|---|---|---|
| Blue levels | **4, spaced 85** | 32, spaced 8.2 |
| Exactly neutral greys | **2 — black and white** | all 24, tint ≤ 4/255 |
| Worst cube error (blue) | **40/255 (15.7 %)** | 3.7/255 (1.5 %) |

The grey ramp is the fatal one: with a 4-level blue grid and an 8-level red/green
grid, the two coincide only at 0 and 255, so *no interior grey is actually grey*.
Any 256-colour ANSI art, any photo, and any anti-aliased text shows it.

**The resolution: keep the LUT, and boot it with an RGB332 identity palette.**

```
for i in 0..255:  PALETTE[i] = rgb565_of_rgb332(i)
```

Software that thinks in RGB332 — your converters, your `PSET`, your ANSI colour
table — is then **bit-identical to a fixed-ladder RGB332 card**, with zero
software awareness of the LUT. You have satisfied the constraint literally, and
you keep fades, palette cycling, per-scanline gradients, optimal per-image 256-of-65,536
quantisation, and blitter.md §8's "higher value per IC than the blit datapath".

**Cost, honestly stated:** +4 ICs net (2 LUT SRAM, 2 output `'574`, 1 `'593` index
counter, −1 because the `'244` mode-bypass is deleted anyway), 15 ns SRAM instead
of 20 ns, and it is the **tightest remaining path in the dot pipeline** at 39.7 ns
(28 ns used, 11.7 ns margin — §6.1). If the bench says that path does not close,
the retreat is clean and already specified: drive the ladders straight from the
pixel bus as RGB332 with 3/3/2 R-2R ladders, and software does not change at all,
because it was already writing RGB332 indices.

**That is the reason to build it this way round:** the LUT is an upgrade you can
abandon at bring-up without touching a line of software. Fixed ladders are an
upgrade you can never add without changing all of it.

**Sourcing flag carried over:** minimal256.md §6.1 notes the `74HC593` (loadable,
3-state counter) is the thin part of the BOM, and that the easier `'590`
substitutes only at the cost of single-entry palette patching. Confirm
availability before freezing the register map — that item transfers unchanged.

---

## 10. Blitter, list engine, and the instruction the 64x4 doesn't have

### 10.1 The GAL wall, stated plainly

blitter.md §6.2 already flags it: the card is 8 GALs, the full blitter adds 10,
and **"eighteen GAL22V10s is the point where the honest question becomes 'why not
one CPLD'."** You have answered that question — no CPLDs — so the consequence is
yours to accept rather than to route around:

| Build | GALs | Card ICs (with `'153` mux) |
|---|---|---|
| Rev A: framebuffer + span writer + palette + read-back | **8** | **36** |
| + list engine (the copper) | 10 | 41 |
| + blit datapath | **~20** | ~55 |

18–20 GAL22V10s is not just a fitting problem, it is a **power and area problem**:
at ~70–90 mA each that is 1.3–1.8 A of GAL alone, on a card that already carries
seven SRAMs. Two mitigations worth pricing at spec freeze:

- **Use a current-production low-power family** (Microchip ATF22V10C and its
  quarter-/zero-power variants) rather than classic bipolar GAL22V10s. Pin- and
  JEDEC-compatible. **Verify the actual `Icc` figures and the wake-up penalty on
  the zero-power grades before relying on it** — a continuously clocked counter
  may never power down, so the saving is largest on the decode/sequencer GALs.
- **Put the blitter on a piggyback**, as both colormin documents conclude for
  area reasons anyway.

### 10.2 What the 6309 gives you for free

The 64x4 has no block-move instruction. **The 6309 does — `TFM`, 6 + 3n cycles.**

| | Rate at 2.098 MHz | vs |
|---|---|---|
| `LDA ,X+` / `STA ,Y+` loop | ~10 cycles/byte | baseline |
| **`TFM R0+,R1+`** | **3 cycles/byte** ≈ 700 KB/s | **~3× the loop, zero hardware** |
| Blit datapath (blitter.md §2.2) | ~125,000 px/frame ≈ 8.7 M px/s | ~12× `TFM` |

`TFM` does not replace the blitter, but it changes the *order of operations*:
main-RAM work (scroll buffers, glyph caches, decompression, loading images from
the SSD) is already ~3× accelerated with no parts, and `arm6309` has to implement
`TFM` correctly for the CoCo 3 anyway (plan.md §4.3 calls it "the hard one —
interruptible mid-transfer, per-byte bus cycles"). It is on the critical path to
your primary goal regardless.

### 10.3 Recommendation

**Build the list engine (≈5 ICs, 2 GALs); defer the blit datapath.**

blitter.md §6.1 already reaches this conclusion for colormin, and every reason is
stronger here:

- The span writer covers text, fills, clears and scroll refills — and it covers
  them better at 8×8 cells (§6.1).
- `TFM` covers bulk main-RAM movement.
- The list engine is what delivers **per-scanline `HSCROLL`** — parallax, sine
  warps, split-scroll status bars — from one descriptor list and no CPU
  involvement. On a machine whose CPU is the bottleneck (§2.1), taking work off
  the CPU is worth more than raw fill rate.
- Its `MOVE` opcode is one SRAM write into the register file, and the palette it
  writes to already exists.

Reserve `+$0B..$0F` for `LIST`/`BCTRL`/`BSTAT` at spec freeze (blitter.md §9,
hook 2 — free), and reserve the board-to-board header (hook 6).

**One option you have excluded, recorded for completeness:** the machine's CPU is
already a microcontroller, so an MCU-based blitter would be no larger a departure
than `arm6309` itself, and would cost one part instead of fourteen. You have ruled
it out for the graphics card; noting it so the decision is deliberate rather than
inherited.

---

## 11. Reverse the write-only decision — make VRAM readable

colormin locks "VRAM is **write-only** from the CPU (no framebuffer read-back
path)". That is the right call *there*: the 64x4's read path is a 125 ns bus
phase with an `/INH`-versus-RAM-OE race that backplane.md §10 lists as the
tightest new path in the system.

**None of that applies here**, and the reasons to reverse it are strong:

| Enabled by read-back | Otherwise costs |
|---|---|
| Read-modify-write pixels (`PGET`, XOR cursors, rubber-banding) | impossible |
| Save-behind for sprites without a blitter | impossible |
| Screen capture / print / save | impossible |
| Software compositing while the blit datapath is deferred (§10.3) | impossible |
| NitrOS-9 window overlap and damage repair | a full shadow copy in system RAM |

That last row is the decisive one: **without read-back, a windowing OS must keep a
128 KB shadow of the screen in system RAM** — a quarter of your 512 KB, on a
machine where memory is the second-scarcest resource after CPU.

**What it costs:** one `'574` read latch (shared with the blit datapath later) and
decode terms. Timing:

```
decode 15 + slot alignment <=158.9 + access 72 + latch/drive 20  =  ~266 ns
budget at dot/12 (476.7 ns cycle, t_AD 160 ns, t_DSR 20 ns)      =  ~297 ns   OK
budget at dot/8  (317.8 ns cycle)                                =  ~138 ns   NO
```

So **VRAM reads close at 2.098 MHz and do not at 3.147 MHz.** Two clean answers,
both already in the design:

1. **`/WAIT` stretches E** (§3.3) — transparent to the emulator, transparent to a
   real 6309E, costs one extra E period on VRAM reads in fast mode only.
2. Or read through a `VDATA` port at `WPTR` with prefetch (the read for address
   *n* is issued when `WPTR` is set, so the CPU's read returns an already-latched
   byte). Streaming reads then run at full rate with no stall at either clock.

Provide both: flat readable VRAM for random access, `VDATA` for streaming.

---

## 12. The missing piece: interrupts

**Neither colormin document has an interrupt source.** backplane.md §2 reserves
`/IRQ` on the bus and nothing drives it. The 64x4 does not need one; **NitrOS-9
does** — it needs a periodic tick, and you want raster splits (plan.md's own
accuracy bar for the CoCo 3 is "the raster split, not the boot").

Two of them, and they belong in different places.

### 12.1 VBL interrupt — on the card

`VSTAT.VBL` plus an enable bit in `CTRL`, driving `/IRQ` open-drain. One macrocell
in the sync GAL pair, zero packages. This is the system tick: 70.09 Hz in the
primary mode, 60.0 Hz in the 640×240 mode — and note that a NitrOS-9 tick derived
from vertical blank is *inherently* tear-free for double-buffer flips.

### 12.2 Raster-compare interrupt — in the CPU, not on the card

This is the `arm6309`-specific one, and it is better than the hardware version.

**Feed the card's HSYNC to a spare STM32 pin and clock a timer from it.** The
emulator then knows the beam line with no card hardware at all, and:

- **Line compare is a register in the emulator**, not a `'521` and a latch. Any
  number of compare values, changeable per line, with no product terms.
- It can be made **register-compatible with the GIME's `$FF92`/`$FF93` interrupt
  block**, which is what NitrOS-9's CoCo 3 IRQ code already talks to.
- **Sample it at instruction boundaries**, where `/IRQ` is sampled anyway — never
  inside the bus loop. plan.md §4.1 rule 3 already folds control-line sampling
  into the per-cycle budget; a timer read at instruction boundaries is cheaper
  still, and a hardware ISR is **forbidden** here (it would blow `t_AD`).
- Cost: **one GPIO pin and a timer.** Both available on the LQFP48, once §6.3.1
  moves the MMU off the CPU and gives the four A16–A19 pins back.

That is a genuinely better raster-interrupt implementation than the GIME's, in a
machine that is otherwise less capable than a CoCo 3 — and it costs nothing.

### 12.3 What this unlocks

With VBL + line compare, the *software* copper works before the *hardware* list
engine exists: an IRQ per split line writing `HSCROLL` or a palette entry gets you
split screens, status bars and raster bars at ~2–3 splits per frame cheaply, and
tells you whether the list engine (§10.3) is worth its 5 ICs before you build it.

---

## 13. Proposed register map

32 bytes in the I/O page. A CoCo-compatible placement keeps NitrOS-9's existing
`$FF` decode assumptions intact: **`$FF60–$FF7F`** is spare on a real CoCo 3
(`$FF00–$FF3F` PIAs, `$FF40–$FF5F` cartridge/disk, `$FF90–$FFBF` GIME,
`$FFC0–$FFDF` SAM). Keep the offsets identical to minimal256.md §4.3 wherever the
register survives, so the emulator model, the image converter and the palette
tables are shared between both projects.

| Off | Name | Bits | Function | Δ vs colormin |
|---|---|---|---|---|
| `+$00` | `CTRL` | b2..0 `VMODE` | 000 640×200/70, 001 640×240/60, 010 640×400/70, 011 640×480/60 | **new** (was `BANK`) |
| | | b4..3 `WMODE` | 00 direct, 01 span-mask, 10 span-solid | moved |
| | | b5 | reserved | — |
| | | b6 | VBL IRQ enable | **new** |
| | | b7 | display enable | — |
| `+$01` | `VSCROLL` | b7..0 | top ring row, bits 7..0 | — |
| `+$02` | `VSCROLLH` | b0 | top ring row, bit 8 | — |
| `+$03` | `HSCROLL` | b7..0 | leftmost column, bits 7..0 | — |
| `+$04` | `HSCROLLH` | b1..0 | leftmost column, **bits 9..8** | widened (1024 stride) |
| `+$05` | `SPANLEN` | b7..0 | span length − 1 | — |
| `+$06` | `WFG` | b7..0 | span foreground index — **must stay at A0=0** | — |
| `+$07` | `WBG` | b7..0 | span background index — **must stay at A0=1** | — |
| `+$08`–`$0A` | `WPTR` | | write/read pointer, 19 bits, auto-increment | — |
| `+$0B`–`$0D` | `LIST` | | display-list pointer (reserved, §10.3) | — |
| `+$0E` | `BCTRL` | | list engine control (reserved) | — |
| `+$0F` | `BSTAT` | | list engine status (reserved, read) | — |
| `+$10` | `PIDX` | b7..0 | palette index, auto-increments after `PDATH` | — |
| `+$11` | `PDATL` | b7..0 | palette entry `GGGBBBBB` | — |
| `+$12` | `PDATH` | b7..0 | palette entry `RRRRRGGG`; write commits | — |
| `+$13` | `VSTAT` | b7 `SPANBUSY`, b6 `VBLANK`, b5 `HBLANK`, b0 IRQ pending | **read**; write clears IRQ | extended |
| `+$14` | `WADV` | b1..0 | pointer advance: 00 continue, **01 next row same column** (§7.2), 10 vertical (advance by stride) | **new** |
| `+$15` | `VDATA` | b7..0 | **read or write** VRAM byte at `WPTR`, post-increment | **new** (§11) |
| `+$16` | `BORDER` | b7..0 | border/overscan palette index | **new** |
| `+$17`–`$1F` | — | | reserved (`TILEBASE`/`FONTBASE` and map base, §6.4; `WPTR` column shadow, §7.2, is written implicitly) | |

**`BANK` is gone** (§6.3). **`MODE` is gone** — there is no stock mode to select;
`VMODE` chooses among native modes only. Reset forces `CTRL = 0`: display
disabled, direct writes, no IRQ — so the machine comes up quiet and software
enables the display after loading a palette.

Register-file reset semantics carry over unchanged from minimal256.md §4.3: the
reset-critical bits live in the one `'273`, everything else is undefined until
written, and boot code writes the whole map once.

---

## 14. Chip budget

| Qty | Part | Role | vs colormin |
|---|---|---|---|
| 4 | AS6C1008-55 (128K×8) | framebuffer, 512 KB, 4-way interleave | = |
| 4 | 74AHCT574 | fetch read latches | = |
| **4** | **74AHCT153** | **4:1 pixel mux — assumed, not fallback (§6.1)** | +4 |
| 1 | 74AHCT574 | palette index latch | = |
| 2 | 32K×8 **15 ns** | palette LUT, 256 × 16 b | = (faster grade) |
| 2 | 74AHCT574 | post-LUT output latch | = |
| 1 | 74HC593 | `PIDX` counter (sourcing flag, §9) | = |
| 2 | GAL22V10-15 | H/V sync + blank/border decode + VBL IRQ | = (single timing now) |
| 2 | GAL22V10-15 | scan address generators, 19 b, loadable | = |
| 2 | GAL22V10-15 | `WPTR` / span pointer, 19 b | = |
| 2 | GAL22V10-15 | sequencer: decode, **static slot assignment**, span control, reg-file addressing, mux phasing | = |
| 1 | 74HC574 | posted-write data latch | = |
| 1 | 74HC165 | span mask serialiser | = |
| 1 | 32K×8 20 ns | register file | = |
| 1 | 74HC273 | `CTRL`, master reset | = |
| 1 | 74HC245 | register + VRAM read-back | = |
| **1** | **74HC574** | **VRAM read latch (§11)** | **+1** |
| 2 | 74HC161 | `SPANLEN` down-counter | = |
| 1 | 74HC244 | clock / load fan-out | = |
| 1 | 25.175 MHz oscillator | **system master** — also feeds the E/Q divider | = |
| — | 3 × R-2R SIP | 5/6/5 ladders | = |
| — | — | ~~stock 1bpp VRAM, `'166`, `'244` bypass, `'74` synchroniser~~ | **−4** |
| **36** | | **(32 if the tri-state pixel bus closes at 39.7 ns)** | **colormin: 39 (35)** |

Off-card, on the motherboard: **1 GAL** (or a `'163` + `'74`) dividing 25.175 MHz
by 12 or 8 to make E and Q with Q leading by 3 dots. That is the whole clock
system — plus **§6.3.1's 3 ICs for the MMU**, which is the other thing the
motherboard now carries.

**Power.** Seven SRAMs and eight GALs, GAL-dominated as before — estimate
450–650 mA, and it is still the first thing worth measuring at bring-up
(minimal256.md §11 item 7 transfers unchanged). §10.1's low-power GAL family
question applies here too, not only to the blitter.

**Area.** 36 ICs including 5 × DIP-32 and 3 × DIP-28 is the same envelope
colormin sizes at ~140 cm² on a 160 cm² Eurocard: 4 layers, disciplined
placement, and the blitter is a piggyback. Unchanged conclusion.

---

## 15. Period audit

| Element | Introduced | Verdict |
|---|---|---|
| VGA, 25.175 MHz, 640×400@70 | **1987** (IBM PS/2) | period-exact; the *standard* clock, not an approximation |
| HD63C09E | 1988 | the machine's premise |
| GAL22V10 | 1986 | period; PAL16L8 is 1978 |
| 74AHCT | ~1990 | **the newest family on the card.** 74F is the period-honest substitute on the dot path |
| AS6C1008 (128K×8 SRAM) | 1 Mbit SRAMs ~1989–90 | **the newest silicon on the card.** A 1988 build would be 16 × 32K×8 |
| 20 ns / 15 ns 32K×8 SRAM | ~1988 | period |
| R-2R SIP ladder DAC | forever | period |
| MMU as an SRAM block map | 1980 (SWTPc DAT), 1986 (GIME) | period |

**The card as a whole places at 1989–1990**, driven by the 1 Mbit SRAM and the
AHCT dot path. That is a coherent date: a 6309 machine with a VGA card, 512 KB,
and NitrOS-9 Level 2 is exactly what an ambitious CoCo owner was building in 1990.

If you want to pull it back to 1988, the honest changes are 8 × 62256 for 256 KB
(−1 mode, +4 ICs) and 74F on the dot path. Not recommended — the date gain is not
worth the parts.

**The one part that is not period at all is the CPU**, and that is the project.
Recording it so the card's rules and the machine's rules stay clearly separate.

---

## 16. What `arm6309` gives you that a real 6309 would not

These are the arguments for building this card *for this machine* rather than for
any other 6809 homebrew.

1. **A bus exerciser before any 6309 code exists.** The STM32 can be programmed
   to drive arbitrary address/data/`R/W` patterns at arbitrary rates over the real
   bus. You can bring up the video card — registers, palette load, span writer,
   scan-out — with a C program and no assembler, no monitor ROM, and no working
   CPU core. This removes the usual homebrew deadlock where the CPU and the video
   card have to work before either can be debugged.
2. **An arbitrarily slow clock for first light.** Divide the master by 4096 and
   single-step the bus. Every card bring-up problem that is normally a
   logic-analyser exercise becomes a printf.
3. **A built-in bus tracer.** plan.md §3.2 already reserves `USART3` on
   `PC10`/`PC11` for a debug console. Every bus cycle the card sees can be logged.
4. **The CPU clock is a software parameter.** §5.1's ÷12 / ÷8 choice is not
   limited by 6309E speed-grade availability, only by emulator throughput — which
   you can improve later without touching hardware.
5. ~~**The MMU costs nothing** (§6.3) and can be made GIME-register-compatible,
   which is worth real weeks of NitrOS-9 porting.~~ **Both halves spent — §6.3.1.**
   The MMU went outside to keep one LQFP48 SKU across both machines, so it costs
   3 ICs, and GIME register compatibility was priced at an hour of NitrOS-9 patching
   rather than weeks. This is the one item on this list the machine chose not to take.
6. **Raster interrupts cost one pin** (§12.2), and are more flexible than the
   hardware they replace.
7. **`TFM` exists** (§10.2).
8. **A real HD63C09E remains a valid part for the socket.** Keeping `arm6309`
   clock-slaved (§5.3) means you can drop real silicon in to bisect a bug —
   emulator or machine? — which is the same A/B lever the CoCo 3 project depends on.

---

## 17. Backplane and the sound card

Brief, because it is not the video question — but the backplane spec has to be
frozen before the video card is laid out, and the sound card is the other consumer.

> **The sound card now has its own document: [`audio.md`](../../audio/docs/audio.md)** — a
> 4-channel PCM card modelled on the Amiga's Paula, 35 ICs, whose acceptance test
> is playing existing OCS tracker modules unmodified, with the loader and
> replayer that do that in [`modplayer.md`](../../audio/docs/modplayer.md). **It supersedes this
> section's Ensoniq 5503 DOC assumption**; the bullets below are updated to what
> that design actually asks of the backplane.

- **Adopt backplane.md's slot model**, retargeted: geographic `/IOSEL` per slot,
  `/WAIT` open-drain (now meaning "stretch E"), `/IRQ` **and** `/FIRQ` open-drain
  (backplane.md reserves only `/IRQ`; NitrOS-9 uses both, and audio wants one of
  its own), `/NMI`, `/RESET`.
- **The geographic decode spans `$FF40`–`$FF7F`, not just `$FF60`–`$FF7F`.**
  Video takes `$FF60`–`$FF7F` (§13); [`audio.md`](../../audio/docs/audio.md) §9.1 proposes
  `$FF40`–`$FF4F`, leaving `$FF50`–`$FF5F` for a disk controller. Widen the window
  now — it is a decode term today and a board respin later.
- **`/FIRQ` belongs to audio, and to audio alone.** [`audio.md`](../../audio/docs/audio.md) §8.1
  takes it as the sole source, so there is no polling chain: video's VBL and
  raster compare stay on `/IRQ` (§12), and a replayer tick gets the cheap
  6809 interrupt it should have. Record the ownership in the backplane spec
  rather than leaving it to first-come.
- **Carry E, Q, `R/W` and the 25.175 MHz master** rather than `16M`/`8M`/`/MRD`/`/MWR`.
  Cards derive their own strobes; the master lets any card phase-lock to video.
- **Carry physical A0–A18 plus A19**, not just logical A0–A15 — the video card
  needs them (§6.3), and so will any future memory card. The sound card does not:
  its whole bus footprint is a 16-byte I/O window and `/FIRQ`.
- **Audio: make it stereo, and the reason is now load-bearing rather than
  aesthetic.** backplane.md has one mono `AUDIO` summing node. Paula's channels
  are **hard-panned — 0 and 3 left, 1 and 2 right — and modules are mixed for it**
  ([`audio.md`](../../audio/docs/audio.md) §1, requirement 5). Summing them to mono does not make a
  mod quieter, it makes it *wrong*. Two pins and two grounds.
- **§5's one-master-clock rule has exactly one exception, and it is this card.**
  Video arbitration needs phase-locking; audio shares memory with nothing, so it
  carries its own **28.37516 MHz** can — the Amiga PAL master, from which the
  period reference every module is tuned against divides exactly.
  25.175 MHz has no integral relationship to it ([`audio.md`](../../audio/docs/audio.md) §4.1), and
  no amount of wanting one will produce it.
- **The sound card needs no `/WAIT`.** Its reads are prefetched on the index write
  ([`audio.md`](../../audio/docs/audio.md) §9.3, copying §11's `VDATA` trick), and its posted-write
  path retires at 3.55 M/s against a `TFM`-paced 700 k/s. It is the only card in
  the machine that never stalls the CPU.
- **Do not put sample data in the video card's VRAM.** It is tempting (512 KB is a
  lot of memory) and it would couple two subsystems that have no reason to be
  coupled, on the one bus resource that is already scheduled. This bullet survives
  the change of sound chip unchanged, and [`audio.md`](../../audio/docs/audio.md) §5 cites it.
- **The MCU sound card is not dead, it is demoted to a bring-up vehicle.** An
  STM32G431 carrying [`audio.md`](../../audio/docs/audio.md) §9's register map does the whole job in
  ~6–8 ICs, and building it *first* lets the loader, replayer and converter be
  written and the acceptance test run before a single GAL is fitted — the same A/B
  lever §16.1 gives for the video card. It is the reference the discrete card must
  match, not the product ([`audio.md`](../../audio/docs/audio.md) §12.5).

---

## 18. Build order

Phased so that each step is independently verifiable, and so the risky items are
measured before anything depends on them.

| # | Step | Exit criterion |
|---|---|---|
| 0 | **Freeze the machine spec** — bus signals, `$FF` map (video `$FF60`–`$FF7F`, audio `$FF40`–`$FF4F`), `/FIRQ` ownership, MMU register set, E/Q divider | one document; §19's items 1–4 answered |
| 1 | **Bench the dot path on a breadboard**: 4-way fetch → pixel mux → index latch → LUT → ladders at 25.175 MHz, driven by counters, no CPU | stable 640×400@70 colour bars on the target monitor; DNL measured across all 64 green codes |
| 2 | **Sync + scan address GALs**; fit the sequencer pair **first** (minimal256.md §11 item 11) | equations fit with the raster-compare and static-slot terms in place |
| 3 | **Card rev A**, driven by the STM32 bus exerciser (§16.1) — no 6309 core needed | registers read back; palette loads; framebuffer scans; `VSCROLL`/`HSCROLL` smooth in both axes |
| 4 | **Span writer + `SPANBUSY`/`/WAIT`** | full-screen clear in ~5 ms; 80×25 glyph render at 13 writes/cell; no lost writes under a hammering loop |
| 5 | **VRAM read-back** (§11) at ÷12, and the `/WAIT` path at ÷8 | read-modify-write pixel round-trips clean at both clocks |
| 6 | **`arm6309` core on the bus**: MMU, VBL IRQ, raster compare | a monitor ROM prints to the 80×25 screen |
| 7 | **NitrOS-9 Level 2 bring-up**, then the console/window driver | boots; `CoWin`-class driver drives the bitmap |
| 8 | **List engine** (5 ICs), if §12.3's software copper proves the value | per-scanline `HSCROLL` from a descriptor list |
| 9 | Blit datapath — **only if bitmap-heavy software actually shows up**, and only after §10.1's GAL count is priced | |

**Do steps 1 and 2 before laying out anything.** They contain both of the design's
real unknowns.

---

## 19. Open items

Numbered so they can be closed individually. Items marked **carried** transfer
unchanged from minimal256.md §11 and are not restated in full.

1. **Confirm the CPU write rate.** Every CPU-cost figure in §7.3 scales on
   "~5 core-6309 cycles per store, native mode". Verify against the real native
   cycle counts for `STA ,X+` / `STB ,X+` and the actual glyph loop, not an estimate.
2. **Bench the pixel-bus turnaround at 39.7 ns** before deciding tri-state vs the
   `'153` mux — the difference is 4 ICs and it is the one number that changes the
   BOM. **carried, retimed.**
3. **Bench the LUT stage at 39.7 ns** with 15 ns SRAM (§6.1). If it does not
   close, fall back to fixed RGB332 ladders — §9 makes that software-invisible,
   but confirm the identity-palette equivalence bit-for-bit first.
4. ~~**Decide the MMU's location**~~ **Closed — §6.3.1: 3 ICs on the motherboard.**
   The deciding argument was one LQFP48 SKU across the CoCo 3 drop-in and this
   machine, not the address path. What it leaves open is the register set itself
   (`machine.md` §5 item 3), which is now a free design with no GIME to copy, and
   which is what the write-decode GAL needs before it can be fitted.
5. **Confirm E/Q phase stability across the ÷12 ↔ ÷8 switch** (§5.2), and gate the
   change to vertical blank.
6. **Confirm the static slot assignment is actually static** — that the CPU's
   access phase is fixed for *both* divisors, and that a `/WAIT`-stretched cycle
   re-enters the correct phase afterwards. This is the load-bearing assumption
   behind deleting the `'74` synchroniser, and it is the most likely place §5 is
   wrong.
7. **Verify VRAM read timing on the bench** (§11), not just on paper — the
   266 ns estimate has ~30 ns of margin at ÷12 and none at ÷8.
8. **GAL fit**, now heavier in two places: the sequencer pair carries static slot
   assignment, raster compare and register-file addressing; the `WPTR` pair carries
   the `WADV` modes of §7.2. **carried, and heavier.** Fit both pairs before
   committing to 8 GALs — and see item 15 before committing to 8 at all.
9. **`74HC593` availability** (§9). **carried.**
10. **Measure card current** with seven SRAMs and eight GALs, and price the
    low-power GAL family (§10.1). **carried.**
11. **Validate 640×400@70 and 640×480@60 on the actual monitors** — CRT, LCD and
    scaler. 70 Hz 400-line is a DOS text mode and should be universal; confirm it.
    **carried, retimed.**
12. **Decide span-wrap behaviour at the 1024-byte row boundary** — wrap in row, or
    advance. §7.2's "next row, same column" mode makes advance the natural default;
    document whichever is chosen. **carried.**
13. **Emulator model** must charge spans their real ~40 ns/pixel, stall on a busy
    span, model `VSTAT`, the raster compare and the MMU — or software will be
    written against a machine that does not exist. **carried, extended.**
14. **NitrOS-9 driver scope.** How much of the CoCo 3 `GrfDrv`/`CoWin` stack can be
    retargeted to an 8bpp chunky bitmap with a span writer, versus rewritten? This
    is the largest unestimated piece of work in the whole project and it is
    software, not hardware.
15. **Tile-mode GAL fit — the gating item for §6.4.** Three questions, in order of
    risk: (a) are there **spare input pins** on the scan-address pair to take the
    map byte, or does it cost a `'574`; (b) can those GALs tri-state their low
    outputs during the tile fetch and switch between linear and concatenated
    addressing; (c) does the sequencer pair hold a second fetch cadence on top of
    what item 8 already lists. Product terms are not expected to be the constraint
    — pins and macrocell count are. **Fit this before freezing the BOM at 8 GALs.**
16. **Decide the tile fetch's fine-scroll behaviour** (§6.4.6). Sub-cell horizontal
    scroll needs a 3-bit offset applied to the tile-row address, which is new logic
    rather than the free `HSCROLL` of §8. Either implement it or document tile mode
    as cell-granular horizontally.
17. **Bench the serialiser in the LUT address path** if Variant B is built (§6.4.3).
    The glyph bit reaches a LUT address pin through a `74AHC165` clock-to-Q, inside
    the 11.7 ns margin item 3 is already measuring. `'HC` grade will not shift at
    25.175 MHz; confirm `'AHC` does, in circuit.

---

## 20. Sources

- `~/code/colormin/docs/minimal256.md` — the design this analyses (chunky
  framebuffer, interleave, span writer, scroll, palette LUT, register file).
- `~/code/colormin/docs/blitter.md` — list engine and blit datapath budgets,
  arbitration priority rule.
- `~/code/colormin/docs/backplane.md` — slot bus model, `/WAIT`/`/INH` semantics.
- `cpu/docs/plan.md` §2.1 (edge-driven requirement), §3.2 (pin budget), §3.3 (timing),
  §3.6 (read latch), §4.1/§4.3 (microcode step, `TFM`).
- `docs/coco3_c64.md` §5.1 (GIME MMU), §8.2–8.3 (scrolling, raster interrupts),
  §10 (what the GIME's restraint buys this project).
- `reference/datasheets/HD6309E_datasheet.pdf` p.3 — `t_ACC`, `t_DSR`, `t_DHW`, `t_AD`.
- VGA 640×400@70: 25.175 MHz, 800 × 449. VGA 640×480@60: 25.175 MHz, 800 × 525.
  **Both derived from the standard, not measured — confirm against the monitors
  in §19 item 11.**
