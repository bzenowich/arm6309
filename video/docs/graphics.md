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
- ~~**No CPLDs or FPGAs on the graphics card.**~~ **Given up deliberately at §10.1.5**, after §10.1.2 showed it was a style rule and not a period one. The card is two `ATF1508AS` in PLCC-84 plus one `GAL22V10` (§10.1.6, §14.1). ⚠ **This card's exception became the machine's rule on 2026-09-08**: the root `README.md` retired the no-CPLD rule outright. FPGAs are unproposed rather than banned.
- Period-appropriate silicon. VGA (1987), GAL22V10 (1986), 1 Mbit SRAM (~1989–90)
  and 25.175 MHz all place this card credibly at **1989–1990** — the same window
  the CoCo 3 and the IIgs were still current in.

---

## 0. Summary — the verdict in one table

| colormin feature | Verdict for an arm6309 machine | § |
|---|---|---|
| **Chunky 8bpp, 4-way SRAM interleave** | **Keep.** The bandwidth argument is unchanged and still wins. | §2.1 |
| **Posted-write capture on the write strobe** | **Keep**, retargeted to E-fall + `R/W` low — but ⚠ **not a direct analogue**: colormin's VRAM is write-only through a pointer, this card's is flat-mapped, so the *address* has to be captured too. +3 `'574`. | §3.1, §3.1.1 |
| **Span writer (mask / solid, `WFG`/`WBG`)** | **Keep — and it matters more here.** The 6309 writes ~2.4× slower than the 64x4 CPU. | §7 |
| **Separate scroll counters, sync untouched** | **Keep verbatim.** Still the right way to scroll. | §8 |
| **SRAM register file + `/245` read-back** | **Keep.** Cheaper here — a 6809 bus read window is 2–3× wider. | §3.2 |
| **256 × 16 b palette LUT** | **Keep, with an RGB332 identity palette at boot.** §9 argues this satisfies your RGB332 constraint at no cost in software. ⚠ The analog stage behind it needs a real buffer, and blanking has to act after the LUT. | §9, §9.1, §9.2 |
| **Blitter + display-list engine** | **List engine yes; blit datapath defer.** The 6309's `TFM` plus the span writer cover most of the gap, and 18 GALs is where "no CPLD" starts to hurt — a wall the card now reaches one package sooner (§14). | §10 |
| **Arbitration priority rule / preemption** | **Keep the rule, delete most of the mechanism.** Phase-locking makes CPU arbitration static **in time** — ⚠ but not in space: which chip the CPU hits is `address[1:0]`, so a small arbiter survives. +1 GAL. | §5, §5.2.1 |
| **MODE=0 bit-exact stock 1bpp path** | **Delete.** −4 ICs, −1 clock domain, −2 open items. Pure win. | §4 |
| **`$4000–$7FFF` broadcast window + RAM shadow write** | **Delete.** An artefact of MinOS compatibility. | §4 |
| **`BANK` register** | **Delete.** The machine has an MMU; that *is* the banking mechanism. | §6 |
| **VRAM write-only** | **Reverse — make it readable.** Now affordable, and worth a lot. | §11 |
| **Card-local asynchronous 20 MHz dot clock** | **Replace** with one system master clock; derive E and Q from it. | §5 |
| **480×200, 6×8 cells, 512 B stride** | **Replace** with 640×200, 8×8 cells, 1024 B stride. | §6 |
| **No interrupt source** | **Add VBL + raster-compare interrupts.** NitrOS-9 needs a tick; you want raster splits. | §12 |

> ⚠ **Superseded — the headline was wrong twice over.** ~~**Net: ~33 ICs (37 with
> the `'153` pixel mux), against colormin's 35 (39).**~~ It disagreed with §14's own
> table, which summed to **36** with the mux and 32 without and made the mux the
> default (§6.1) — so the parenthesis was inverted as well as the number. And §14
> was itself short of four things the bus interface actually needs: the posted-write
> **address** latches (§3.1), the spare-access **arbiter** (§5.2), a tri-state driver
> for `VSTAT`'s live bits (§12.1), and an **analog buffer stage** (§9.1); while it
> carried a master oscillator that belongs on the motherboard, not on a card you can
> pull (§14). None of that is a change of design. It is the same card, counted.

**Net: ~~41 ICs (37…)~~ 28 ICs (24 if the tri-state pixel bus closes at 39.7 ns and the
`'153` mux is not needed), against colormin's 39 (35)** — plus 3 buffer transistors and
3 R-2R SIP ladders, which are not ICs and are counted on their own line.

**The programmable logic is 2 × `ATF1508AS-15JC84` (PLCC-84) + 1 × `GAL22V10`** —
`vaddr`, `vctrl` and the spare-access arbiter. ⚠ **41 and "10 GALs" were the GAL build,
which §10.1.6 replaced on 2026-09-06 without the arithmetic being carried back; three
different counts were live in this document until 2026-09-08. §14.1 reconciles them.**
Higher resolution, readable VRAM, raster interrupts, one clock domain; deleting the
stock-compatibility path still pays for most of the addition, and the honest bus
interface eats the rest.
Budget and the line-by-line arithmetic in §14; power in §14 as well, and it is
**~1.1–1.7 A**, not the 450–650 mA this document used to claim — which was less than
the GAL row of its own arithmetic.

---

## 1. Why the two machines pull the design in different directions

| | Minimal 64x4 Redux | arm6309 machine |
|---|---|---|
| CPU | 4-phase microcoded TTL, 8 MHz bus clock | HD6309E (synthesised), E/Q bus |
| CPU write rate, sustained | ~16,000 writes/frame (≈1 M/s) | **~6,000 writes/frame (≈420 k/s)** |
| Address space | 64 KB flat, banked at `$8000` | 64 KB logical, **MMU-mapped**, ≥512 KB physical |
| Existing OS to protect | **MinOS, bit-exact 1bpp video** | **none** — NitrOS-9 is ported, not preserved |
| Bus read path | awkward (`/INH` race, 125 ns phase) | **native** — `t_ACC` 330 ns at 2 MHz |
| Bus stall mechanism | `/WAIT` clock gating, exercised but bolted on | `/WAIT` **wait states** — **free**, the emulator is edge-driven |
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

> ⚠ **§14.2 spends that escape hatch.** The `AS6C8016` is a **55 ns part and Alliance
> list no faster grade**, so the −45 fallback above does not exist for it. 86.9 ns of
> slack against a 72 ns access is the margin, and there is no part-swap behind it —
> only a retreat to the four `AS6C1008`, which is why §14.2 is a packaging decision
> that can be reversed at layout and not one that closes a door.

> ⭐ **"4-way" is the interleave, not the package count — §14.2, 2026-09-08.** The
> framebuffer is **two `AS6C8016` 512K×16** parts rather than four `AS6C1008` 128K×8,
> and two ×16 accesses deliver the same four bytes in the same 158.9 ns slot. Every
> timing number in this section is unchanged, and so are the seventeen address bits
> (§19 item 3) — `A1` selects the part and `A0` drives `/LB` / `/UB` where both used to be
> chip select. **What does change is the spare-access budget** (four per slot becomes
> one, of up to four bytes) and that is the whole of §7.4's broadcast write.

Free accesses for the span writer and blitter, at 70 Hz:

> ⚠ **The blanking rows were charged at the wrong cadence.** The original
> arithmetic divided the blanking intervals by the raw 72 ns access time —
> ~~`6.36 us / 72 ns` = 88.3 accesses per chip per line, `483,000/frame`,
> `≈ 34 M accesses/s`~~ — as if accesses were free-running. They are not: every
> access is granted on the **158.9 ns fetch-slot grid** (§5.2), and a chip takes at
> most **two** accesses per slot (2 × 72 = 144 ns ≤ 158.9 ns). Charging the slot grid
> costs ~9 % on both blanking rows. The conclusion is untouched — the headroom is
> 77×, not 80× — but the table is quoted downstream (`docs/video-comparison.md` §4),
> so it is corrected rather than rounded away.

```
active display : 160 slots/line x 1 spare  x 4 chips x 400 lines  = 256,000
hblank         : 6.36 us / 158.9 ns = 40.0 slots/line
                 40.0 x 2 spare x 4 chips x 400 lines             = 128,000
vblank         : 31.78 us / 158.9 ns = 200 slots/line
                 200 x 2 spare x 4 chips x 49 lines               =  78,400
                                                           total  ~ 462,000/frame
```

During active display one of the slot's two per-chip accesses is the display fetch,
so one is spare; during hblank and vblank the display fetches nothing and both are
spare. ≈ **32.4 M accesses/s**, against a CPU that can issue ~420,000 writes/s. The
card has **~77×** more memory bandwidth than the CPU can consume. Bandwidth is not
the constraint on this machine — **the CPU is** — which is the single most important
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
| `/IOSEL` per slot | mainboard `'138` on the I/O page | ⚠ ~~Keep the geographic-slot idea — it is a good one~~ — **the idea does not survive the retarget.** colormin's windows are slot-sized and this machine's are function-sized, so `/IOSEL` becomes a window strobe common to every slot — [`machine.md`](../../docs/machine.md) §2 |
| `/WAIT` (clock gating) | **`/WAIT`: E held low for whole E periods** | §3.3 |
| `/INH` | not needed | the MMU decides what answers |

> ⚠ **Superseded — it is four capture registers, and the redesign is real.**
> ~~**One capture register, one edge, same discipline.** The posted-write path is a
> rename, not a redesign.~~ The "one register" figure was inherited from colormin,
> where **VRAM is write-only through `WPTR`** — the address always came from the
> card's own counter, so the CPU write contributed nothing but a data byte. §6.3 makes
> this card's VRAM **flat-mapped**: a direct CPU write arrives carrying an arbitrary
> **19-bit physical address** that exists nowhere else on the card, and it has to be
> captured on the same edge as the data. The edge count is unchanged; the register
> count is not. See §3.1.1.

### 3.1.1 The posted-write path needs its address, not just its data

The write is *posted*, not live: the CPU's cycle ends when E falls, and the write is
retired into a free VRAM slot some time afterwards. The two clocks that matter:

| Quantity | Value | Source |
|---|---|---|
| 6809E/6309E address hold after E-fall (`t_AH`) | ~20–30 ns | `reference/datasheets/HD6309E_datasheet.pdf` p.3 |
| 6809E/6309E write-data hold after E-fall (`t_DHW`) | ≥ 30 ns | same |
| Worst-case wait for a granted retire slot | **158.9 ns** (one full fetch slot) | §2.1, §5.2 |

`158.9 ns > 30 ns`, so **a live-retire scheme — driving the VRAM address and data
pins from the bus itself at retire time — does not work at any divisor.** By the time
the granted slot arrives, the CPU has moved on: at ÷12 the next bus cycle's address is
already going valid at `t_AD` = 160 ns, and at ÷8 the whole next cycle is 317.8 ns
long, so the address on the bus during the retire is the *next* instruction's fetch
address. There is no ordering of the arbitration that avoids this, because the write
cannot be retired inside its own bus cycle without stalling the CPU, which is the one
thing §5.2 exists to prevent.

So everything the retire needs is latched at E-fall:

```
  physical A18..A0        19 bits   <- must be captured
  VRAM select (qualified by /IOPAGE, §6.3)   1 bit
  R/W                                        1 bit
  WMODE[1:0] at capture time (§13)           2 bits
  ------------------------------------------------
                                            23 bits  ->  3 x '574
  D7..D0                                     8 bits  ->  1 x '574  (the one §14 had)
```

**Four `74HC574`, not one** — three of them new, and §14 carries them. All four clock
on the same inverted E; the "one edge" half of the original claim survives intact, and
it is the only half that does.

A depth-1 posted-write path is still the right shape: §2.1 gives one spare access per
chip per slot, so the retire always finds a slot within 158.9 ns, and the CPU cannot
issue a second write inside that window (the fastest 6309 store is 5 core cycles ≈
2.4 µs at ÷12 — §7.3). The `SPANBUSY`/`/WAIT` backstop of §3.3 covers the case where
the span writer holds the chip.

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

*Naming, machine-wide:* **`/WAIT` asserts a wait state** — the motherboard's E/Q
divider holds E low for one or more further E periods. This document previously called
that "stretching E"; `docs/machine.md` uses "stretch" for the ÷8 clock rate, which is
a different thing entirely, so the word is retired here. The ÷8 rate is **fast-E
mode** (§5.1).

plan.md §2.1 makes the emulator **purely edge-driven — no calibrated delays, no
assumed E period, every action keyed off an observed transition.** That was
written to survive the CoCo 3's runtime 0.895 ↔ 1.79 MHz switch. It has a second
consequence in a machine you design:

> **A `/WAIT`-extended E cycle is transparent to `arm6309`.** The card can assert
> `/WAIT`, the motherboard's E/Q generator holds E low for **an integral number of
> further E periods**, and the emulator simply observes a longer cycle. No emulator
> change, no new state.

**The granularity is not free, and §5.2 is why.** The static slot assignment works
because E is derived from the dot clock by an integer divisor, so the CPU's access
always lands in the same sub-slot phase. A wait state that extends E by an arbitrary
number of dots destroys that phase and the CPU's access lands somewhere the sequencer
has not reserved. **`/WAIT` must therefore extend E by an integral number of fetch
slots, and the divider should implement it as an integral number of whole E periods**
(3 slots at ÷12, 2 at ÷8), which is both stricter and simpler to build. Stated here
because it is a requirement on the *motherboard's* divider, not on this card, and
`docs/machine.md` is where it has to land.

So colormin's `SPANBUSY` + `/WAIT` backstop (§4.2.1) transfers directly and is
*less* exotic here than it was there — and it also becomes the fallback for VRAM
reads at the higher clock (§11). A real HD63C09E would tolerate the same
wait states, so this does not compromise the "drop a real 6309 in and it still
works" property. (⚠ That property is now qualified for a different reason — see §16
item 8.)

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
derive E and Q from it by division.** The oscillator lives **on the motherboard**,
next to the divider — not on this card. `docs/machine.md` §0/§1 has always said so;
§14 of this document used to list the same can inside the card's own budget, which
would have meant that **pulling the video card kills E and stops the CPU**. Every
bring-up ordering in §18 runs the bus before the video card exists (§16 item 1), so
the oscillator cannot be a passenger on the card it is used to debug. The card
receives the 25.175 MHz master from the backplane, which §17 already carries.

```
25.175 MHz  (motherboard)
   │
   ├──► backplane: master clock ──► dot clock (video card)
   │
   └──► ÷12 ──► E at 2.0979 MHz   (Q leads E by 90° = 3 dots)
        ÷8  ──► E at 3.1469 MHz   (fast-E mode — experimental, §11)
```

> ⚠ **"Q = same divider, 3 dots early" was stated unconditionally, and it is only
> true at ÷12.** Q leads E by **90° of the E period**, and the E period is a
> different number of dots at each divisor:
>
> | Divisor | E period | 90° | Q lead |
> |---|---|---|---|
> | ÷12 | 12 dots, 476.7 ns | 3 dots | **3 dots, 119.2 ns** |
> | ÷8 | 8 dots, 317.8 ns | 2 dots | **2 dots, 79.4 ns** |
>
> A divider that emits a fixed 3-dot lead in both modes puts Q at 135° in fast-E
> mode — a 45° phase error, which a real HD63C09E in the socket samples against
> (`t_AVS`/`t_CSR` are referenced to Q, not to E). The divider's Q tap is therefore
> **a function of the divisor**, one more product term in the motherboard's divider
> GAL, and `docs/machine.md` must say so. §14's off-card line is corrected to match.

Both divisors are integral in **fetch slots** (4 dots), which is the property
that matters:

| E rate | Bus cycle | Fetch slots per bus cycle | Core cycles/bus cycle @170 MHz |
|---|---|---|---|
| dot ÷ 12 | 476.7 ns | **3** | **81** |
| dot ÷ 8 | 317.8 ns | **2** | **54** |

Against plan.md §3.3's measured numbers — post-read path ~13 core cycles, the
§4.1 microcode step 14 typical / 25 worst — **dot ÷ 12 is comfortable and
dot ÷ 8 is the same budget as the CoCo 3's 3 MHz case** (56.7 cycles),
which plan.md already declares reachable with the §3.6 read latch. Make the
divisor a register bit and you have a CoCo-3-style runtime speed switch, which
the emulator already has to tolerate.

> ⚠ **÷12 is the specified rate; ÷8 is experimental.** `docs/machine.md` §5 records
> the machine-wide decision: **E = 2.0979 MHz is the default AND the only rate the
> machine is specified at.** Fast-E mode (÷8, 3.1469 MHz) is not guaranteed, because
> three independent things break at it and only one of them is on this card:
> flat VRAM read-back does not close (§11); a 2 MHz R6551A is 57 % over rating
> (`io/serial/docs/serial.md`); and 317.8 ns is below the real HD63C09E's **333 ns
> `t_cyc` minimum**, so the drop-in silicon A/B reference cannot be captured at that
> rate with a rated part. The divider still builds both — the hardware cost of
> keeping ÷8 available is one product term — but nothing in this document may assume
> it, and the ÷8 column below is retained as analysis, not as specification.

### 5.2 What phase-locking buys

Because E is *derived from* the dot clock, the CPU's bus cycle sits at a **fixed
phase relative to every video fetch**. That converts arbitration from a search
into an assignment:

- The CPU's access lands in a known slot, **in a known sub-slot phase** (see
  below), on the chip selected by `address[1:0]`. The sequencer **reserves** the
  phase rather than hunting for it.
- ~~The other three chips' spare accesses in that slot go to the span writer or the
  blitter, by a wire, not a state machine.~~ ⚠ **Wrong — see §5.2.1.** *Which* chip
  the CPU takes is dynamic, so "the other three" is a per-access computation.
- **The `'74` synchroniser disappears.** There is no domain to cross.
- minimal256.md §8's "commit: sync (2 stages) + slot arbitration ≥ 200 ns" row
  vanishes from the timing table.

#### 5.2.1 "The other three chips" is a compare, not a wire

Phase-locking fixes **when** the CPU's access happens. It says nothing about **which
of the four chips it lands on**, and it does not even say **whether it happens** —
the overwhelming majority of bus cycles are instruction fetches and system-RAM
accesses that never assert the card's VRAM select at all. Three facts, none of them
static:

1. The CPU's chip is `physical address[1:0]` — a new value on every bus cycle.
2. The span writer's current chip is *its* pointer's `[1:0]`, advancing every access.
3. The CPU's access may be absent, in which case all four chips are spare and the
   span writer should get the extra one rather than idling a slot.

So the span writer may use a chip only after a **live compare** of the CPU's low
address bits against its own. That is a small combinational arbiter, and it has to be
budgeted:

```
  VREQ     = VRAMSEL . /IOPAGE          (§6.3 — the CPU wants VRAM this cycle)
  CPUCHIP  = phys A[1:0]
  SPNCHIP  = WPTR[1:0]                  (span writer / list engine pointer)

  for chip n in 0..3:
      GRANT_CPU[n]  = VREQ . (CPUCHIP == n)
      GRANT_SPAN[n] = SPNREQ . (SPNCHIP == n) . /GRANT_CPU[n]
      SRCSEL[n]     = GRANT_CPU[n]      (mux the chip's address/data source)
```

Eight product terms of the form *(2-bit compare)·(request)* plus four inversions —
comfortably inside one GAL22V10's product-term budget, but it needs **eight outputs
plus the four `SRCSEL` lines = 12 macrocells**, and the sequencer pair (§14) is
already carrying static slot assignment, span control, register-file addressing and
mux phasing. **Budget one more `GAL22V10` for the spare-access arbiter** — the card
goes from 8 GALs to **9** — rather than pretending it fits in a pair that §19 item 8
already flags as the tightest fit on the board.

The arbitration *priority rule* is unchanged; what changes is the honest admission
that the CPU tier is static in **time** and dynamic in **space**, and only the first
half of that was ever a wire.

#### 5.2.2 Sub-slot ordering: the spare access goes **first**

This is a specification sentence, and §11's read budget does not close without it.

Within a 158.9 ns fetch slot a chip has room for exactly two 72 ns accesses
(2 × 72 = 144 ns ≤ 158.9 ns), and their order is a free choice for the sequencer.
**The choice is made here: the CPU/spare access occupies the FRONT half of the slot,
the display fetch the back half.**

| Ordering | CPU access window in the slot | §11 read completes at | Deadline | Verdict |
|---|---|---|---|---|
| **Spare first** (specified) | 0 → 72 ns | **409.8 ns** | 456.7 ns | **+46.9 ns** ✓ |
| Video first | 72 → 144 ns | 481.8 ns | 456.7 ns | **−25.1 ns** ✗ |

The full derivation is in §11. Two things follow:

- The "video → CPU → list engine → span → blit" priority of §2.2 is a **priority**
  rule, not a **temporal** one. Read plainly it implies video-first, which is the
  ordering that misses by 25 ns; the rule ranks who gets a contested access, not who
  goes first in an uncontested slot. Both wordings now appear so the distinction
  cannot be lost again.
- Spare-first is also what the **fetch-latch clocking** wants. Each chip's display
  fetch `74AHCT574` is clocked at the end of *that chip's own* fetch, and its output
  must then be stable for the whole of the next slot's four pixel times. With the
  spare access first and the fetch second the clock edge lands at **144 ns into the
  158.9 ns slot** — 14.9 ns of settling before the boundary, and comfortably clear of
  the spare access's own bus activity. Two properties follow and both are
  specification, not preference:

  > **Fetch-latch clocking is per-chip and mid-slot.** *Per-chip*, because §5.2.1
  > grants each chip's spare access independently, so the four chips' bus turnarounds
  > are not identical, and because §6.4's tile mode gives them different fetch
  > cadences; a common slot-rate clock would have to be timed for the worst chip in
  > the worst mode. **And, added 2026-09-06, because byte-granular horizontal scroll
  > requires it** — §8's note: with a common latch clock the display cannot render a
  > line at `HSCROLL[1:0] ≠ 0` at all. That is the strongest of the three reasons and
  > it was the one nobody had written down. *Mid-slot*, because a clock on the slot boundary has no settling
  > margin and is the same edge that reloads the address counters.

  Video-first inverts this: the fetch would complete at 72 ns and the latch would sit
  through the spare access's turnaround before its data is used, which is survivable —
  it is the read budget, not the latch, that decides the ordering. But the latch has
  no reason to prefer the other order, so nothing pulls against §11.

The arbitration *priority rule* of blitter.md §2.3 still applies to the three
requesters that remain dynamic (list engine, span writer, blit datapath). Only
the CPU tier becomes static — and that is the tier whose failure mode was a CPU
stall.

**Caveat to verify:** E must be phase-stable at the divider output across the
÷12 ↔ ÷8 switch, or a speed change lands the CPU slot in the wrong phase for one
cycle. Gate the divisor change to vertical blank — the same discipline
minimal256.md §11 item 2 recommends for its clock switch, for the same reason,
but now on a signal you own. The same argument applies to `/WAIT`, which is why §3.3
constrains it to whole E periods.

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
| 640×240, line-doubled | 525 / 480 | **59.94 Hz** | 80×30 | 153,600 |
| 640×400, progressive | 449 / 400 | 70.09 Hz | 80×50 | 256,000 |
| 640×480, progressive | 525 / 480 | **59.94 Hz** | 80×60 | 307,200 |

> ⚠ **59.94 Hz, not 60.0**, corrected 2026-09-06 by
> [`hardware/gal/sync.timing.ts`](../../hardware/gal/sync.timing.ts)'s own arithmetic
> check: 25.175 MHz ÷ 800 ÷ 525 = 59.940 Hz. This is the standard VGA 640×480 rate and
> it has never been 60. It matters in exactly one place — §12.1 makes vertical blank
> the NitrOS-9 system tick, so a tick divisor calibrated for one family runs 0.1 %
> wrong in the other, which is about **86 seconds a day**. The two families need
> different divisors; they were never interchangeable.

**The progressive modes cost no extra bandwidth.** Line-doubling fetches every
row twice; 640×400 fetches 400 distinct rows once. Same 640 bytes per scanline
either way. The only cost is memory, and 512 KB covers even 640×480 single-buffered.

640×480×8bpp on a 6309 is not a mode any period machine had. It is available for
one bit in `CTRL` and a couple of terms in the V-sync GAL, so take it.

#### 6.2.1 Sync polarity is part of the mode, and it must switch with it

**A VGA monitor identifies the vertical format by the polarity of the sync pulses,
not by counting lines.** This is the whole of the VGA/VESA mode-identification
mechanism at these two timings, and both of this card's `VMODE` families are on it:

| Mode | Dots × lines | HSYNC | VSYNC | What the monitor concludes |
|---|---|---|---|---|
| 640×400 @ 70 (`VMODE` 000, 010) | 800 × 449 | **negative** | **positive** | 400-line text format; picture sized to 400 active lines |
| 640×480 @ 60 (`VMODE` 001, 011) | 800 × 525 | **negative** | **negative** | 480-line graphics format |

The two timings share a dot clock, a line rate to within 0.06 %, and an HSYNC
polarity. **Polarity of VSYNC is the only thing that distinguishes them at the
connector.** Get it wrong and the monitor picks the other format's vertical size and
centring: a 449-line picture displayed against a 480-line template is short, high, and
letterboxed, and no amount of correct pixel timing fixes it, because the fault is in
the identification and not in the raster.

So VSYNC polarity is **a function of `VMODE`**, not a constant:

```
  VPOL   =  VMODE[0]                       ; 0 -> 449-line family, 1 -> 525-line
  VSYNC  =  VSYNC_raw  XOR  VPOL           ; raw = active-high pulse window
  HSYNC  =  HSYNC_raw  XOR  HPOL           ; HPOL tied to 1 (negative) in both
```

**Cost in the sync GALs — fitted 2026-09-06, and the estimate below was wrong twice
in opposite directions.** A 22V10's macrocells have unequal product-term allocations
(8, 10, 12, 14, 16, 16, 14, 12, 10, 8), and this paragraph used to read: *"the window
differs per mode: two terms per mode over the four `VMODE` values = 4 product terms …
`A XOR B` is `A·/B + /A·B`, so the polarity multiplexing doubles it to 8."*

| | Claimed | Actual |
|---|---|---|
| `VSYNC_raw` | 4 terms — one window per `VMODE` value | **1 term, shared by both families** |
| polarity multiplexing | ×2 → 8 | **+9 → 10** |

**Too high, because only `VMODE[0]` reaches the sync logic.** There are two vertical
timings, not four: `VMODE[1]` selects line-doubling, which is the scan-address
generator's business and not the raster's. So there was never a window per `VMODE`
value.

**Too low, because XOR against a *variable* is not a doubling.** `A XOR B` doubles
only when `A` and `B` are both single literals. Here `A` is a window compare and `B`
is `VMODE[0]`, so the `/A·B` half is the **complement** of that compare — one product
term per literal in it. A nine-literal window compare becomes nine terms, not one.

**What makes it come out at 10 rather than far worse is where the counters start**,
which nothing in this document had fixed and which
[`hardware/gal/sync.timing.ts`](../../hardware/gal/sync.timing.ts) now does: both
counters are zeroed at the **leading edge of their own sync pulse** rather than at the
start of active video. Then `VSYNC_raw` is `v ≤ 1` — one product term, and *the same
term in both families*, because both timings open with a two-line pulse. A mid-raster
origin would have needed a mode-dependent window compare here, and it is the
complement of that compare that the polarity XOR then has to pay for.

10 terms sits on a 16-term macrocell with room, which is what this section required.
The same reasoning applies to `HSYNC` even though `HPOL` is strapped: it costs 6 of
the 10 terms on its macrocell, and carrying the input rather than strapping it in
silicon makes an out-of-spec monitor a re-burn instead of a cut trace. Fitted in
`hgen` and `vdec`; §19 item 8 has the macrocell table.

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

A19 = 0  : 512 KB system RAM      } both qualified by /IOPAGE high
A19 = 1  : 512 KB VRAM            } (the video card's 1024 x 512 ring)

card VRAM select = A19 . /IOPAGE(high) . E . (no other card asserting)
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
3. **That chip select must be qualified against `/IOPAGE`.** ⚠ This document
   originally wrote consequence 2 as "physical A0–A18 plus a chip select" and stopped
   there, which is an unsafe card. See §6.3.2.

`WPTR` stays. The auto-incrementing 19-bit pointer is the streaming path and the
span writer's address source; the MMU is the random-access path. Two paths on
purpose, exactly as colormin argues — just with the MMU doing the job `BANK` used
to do badly.

### 6.3.1 The MMU goes on the motherboard — 5 ICs, and one 48-pin SKU serves both machines

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

> ⚠ **Superseded — the three-IC list cannot be wired.** The list below stood as
> ~~"the three ICs"~~ for one revision and it is short by two packages, for two
> independent reasons that both come from the same place: a **common-I/O** SRAM has
> one set of pins doing two jobs, and a **translate-mode** address that is wrong
> during the very cycle that writes it.
>
> 1. **Data-bus conflict.** The map SRAM's data pins *are* its outputs, driving
>    physical A13–A19. To write an entry, CPU `D0–D7` must reach those same pins. If
>    they sit on the A13–A19 net, CPU data can never get to them; if they sit on
>    `D0–D7`, then physical A13–A19 **are** `D0–D7` at all times. There is no wiring
>    that satisfies both — the SRAM needs an **isolation buffer** between its common
>    I/O and one of the two nets, with break-before-make output-enable discipline.
> 2. **Missing address mux.** In translate mode the SRAM is addressed by
>    `{TASK, A15..A13}`. But when the CPU writes entry N at `$FFA0+N`, logical
>    A15..A13 = **111** — it is the I/O page, by construction — so the write would
>    land in entry 7 of the current task, whatever N was. The entry index during a
>    map write must come from **A3..A0**. That is a 4-bit 2:1 mux, and it was not in
>    the list.
>
> **The mux cannot be folded into the GAL.** The tempting escape is to make the GAL
> emit the four SRAM address lines itself. Count the inputs it would then need:
> a 12-bit `$FFAx` decode + 4 index bits (A3..A0) + `TASK` + `E` + `R/W` = **19**,
> against a GAL22V10 whose 22 input pins are only fully available when few macrocells
> are used as outputs — and this GAL must already produce the SRAM `/WE`, the buffer's
> two direction/enable controls, the mux select, the map `/OE`, the `'574` clock and
> the I/O-page term. At that output count the usable input pins do not reach 19. The
> mux is a package.
>
> **The period-honest precedent says the same thing.** §15 dates "MMU as an SRAM
> block map" to the **SWTPc DAT (1980)** — and the DAT used **74LS189-class register
> files**, which have *separate data-in and data-out pins*, precisely so that no
> isolation buffer is needed. A 2K×8 commodity SRAM with common I/O is the modern,
> cheap, wrong-shaped part, and the buffer is the price of using it.

**The five ICs** (period-honest, and what a 1990 machine would really have done — the
SAM/GIME/DAT arrangement, with the DAT's separate-port register file replaced by a
commodity SRAM and the buffer that substitution costs — §15). This is the count
`docs/machine.md` §5 item 6 carries:

| Qty | Part | Role |
|---|---|---|
| 1 | 2K×8 SRAM, **15 ns** | the block map, addressed by `{TASK, A15..A13}` in translate mode, outputting physical A13..A19 |
| 1 | `74HC574` | task select, MMU enable, and the §6.3.3 shadow-ROM disable — three bits, at addresses this machine picks (see below), not the GIME's `$FF90`/`$FF91` |
| 1 | `GAL22V10` | write decode, the `/IOPAGE` term, and the control sequencing of the two parts below |
| 1 | `74HC245` | **isolation** between the SRAM's common I/O and `D0–D7`, break-before-make |
| 1 | `74HC157` | **quad 2:1 mux** on the SRAM address: `{TASK, A15..A13}` in translate mode, `A3..A0` during a map write |

Sixteen of the SRAM's 2048 locations are used. A 2K×8 is specified anyway because a
15 ns one is a stocked commodity part and a 16×8 is not.

**The map-write cycle, drawn.** This is the sequence the GAL exists to run, and it is
the part the three-IC list left unstated. Assume `E` high, `R/W` low, the decode
`$FFAx` true:

| Phase | Mux select | `'245` direction / `/OE` | SRAM `/OE` | SRAM `/WE` | Physical A13–A19 |
|---|---|---|---|---|---|
| Idle (translate) | `{TASK,A15..A13}` | **disabled** | asserted | high | the translation — valid |
| Map write, setup | switches to `A3..A0` | disabled | **de-asserted first** | high | parked (see below) |
| Map write, drive | `A3..A0` | `B→A`, enabled onto SRAM I/O | de-asserted | high | parked |
| Map write, strobe | `A3..A0` | enabled | de-asserted | **asserted** | parked |
| Map write, release | `A3..A0` | `/WE` released, then **disabled** | still de-asserted | high | parked |
| Idle (translate) | back to `{TASK,...}` | disabled | re-asserted **last** | high | the new translation |

Two orderings are load-bearing and neither is optional:

- **Break before make.** The SRAM's `/OE` is de-asserted *before* the `'245` is
  enabled, and the `'245` is disabled *before* the SRAM's `/OE` is restored. Two
  drivers on the SRAM's I/O pins for even one propagation delay is a through-current
  event on every map write, and NitrOS-9 Level 2 writes the map on every task switch.
- **What physical A13–A19 carry during the write.** They carry the **parked** pattern,
  not a translation and not the CPU's data: a map write is a `$FFAx` cycle, so
  `/IOPAGE` is asserted for the whole of it (§6.3.2), and `/IOPAGE` is exactly what
  gates the map SRAM's `/OE` and every physical-memory decode in the machine. System
  RAM and this card's VRAM are both inhibited for the duration, so the backplane's
  A13–A19 being indeterminate during the write is harmless **because nothing is
  listening**. Without `/IOPAGE` this cycle would post a write into whatever block 7
  currently points at — which is the same failure §6.3.2 describes, arriving through
  the MMU's own front door.

**Pin budget, this machine, both ways.** From plan.md §3.2's 39 usable pins:

| | in-CPU MMU | external 5-IC MMU |
|---|---|---|
| `A0..A15` | 16 | 16 |
| `A16..A19` | **4** | 0 — the map SRAM emits A13..A19 |
| `D0..D7` | 8 | 8 |
| `R/W`, `E`, `Q` | 3 | 3 |
| `/RESET`, `/NMI`, `/IRQ`, `/FIRQ`, `/HALT` | 5 | 5 |
| `BUS_OE` | 1 | 1 |
| HSYNC **and VSYNC** in, for §12.2's raster compare | 2 | 2 |
| **Used, of 39** | **39** | **35** |
| Spare | **0** | **4** — debug UART, status LED, and two left |

plan.md §3.2 now carries the same arithmetic with the UART and LED counted as line items
rather than as spares; the two tables agree at 39 either way. ⚠ The HSYNC row was one
pin when this table was first written; §12.2 shows that a raster line *number* needs a
frame origin as well as a line clock, so it is two. The in-CPU column now has no spare
at all, which sharpens rather than changes the conclusion.

⚠ **Package, per `docs/machine.md` §5 item 6:** the part is the **STM32G431CBU6
(UFQFPN48)**, not the CBT6 (LQFP48) this section originally named. Same die, same 48
pins, same firmware — but the LQFP48 bonds out only 38 GPIO and does not carry
`PC4`/`PC6`/`PC10`/`PC11`, which is where `BA`, `BS` and the debug UART live. The
one-SKU argument below is unaffected in every particular; read "LQFP48" as
"48-pin part" throughout.

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

**What it costs, then.** **Five ICs** and their board area, a write-decode GAL that is
harder to change than firmware, and a NitrOS-9 memory-manager patch the owner has
priced. With the motherboard's E/Q divider GAL that is **six packages of motherboard
logic**, plus the 25.175 MHz master oscillator (§5.1) which now also lives there —
seven parts in total. The pin argument that decided the question is unaffected: five
ICs outside the CPU still buys back A16–A19 and still lets one LQFP48-class SKU serve
both machines, which was always the point.

### 6.3.2 `/IOPAGE` — why a flat VRAM map is unsafe without it

`$FF00`–`$FFFF` **overrides MMU translation by design** (§6.3.1 detail 1), exactly as
it does on a CoCo 3. But overriding translation does not stop the map SRAM emitting
*something* onto physical A13–A19; as originally drawn it keeps emitting the current
task's block-7 translation throughout the I/O cycle. §6.3 explicitly permits **any**
MMU block to point at VRAM. Therefore, for a task whose logical `$E000`–`$FFFF` is
mapped to VRAM, **every single I/O access in the machine also looks like a valid VRAM
access to this card**:

| CPU does | Card sees | Result |
|---|---|---|
| Read `$FF73` (`VSTAT`) | A19 = 1, a stale physical A18–A0, `R/W` high | The addressed card **and** VRAM both drive D0–D7. Electrical double-drive, every I/O read. |
| Write `$FF41` (audio) | A19 = 1, a stale physical A18–A0, `R/W` low | A posted VRAM write is captured and retired. Silent framebuffer corruption, every I/O write. |

The card cannot compute the inhibit for itself: the term is `logical A15..A13 = 111`
and logical A13–A15 are **deliberately not on the backplane** — they terminate at the
map SRAM's address inputs on the motherboard (§6.3.1, `docs/machine.md` §2).

**The fix is one backplane signal**, and it must exist before the backplane is etched:

> **`/IOPAGE`** — motherboard-generated, active-low, asserted for the whole of any
> logical `$FF00`–`$FFFF` bus cycle. It is the term the motherboard already forms to
> generate `/IOSEL`, so it costs a pin and a buffer, not logic.

Three consumers, all mandatory:

1. **This card's VRAM select** gains `. /IOPAGE(high)`. One product term in the
   sequencer pair's decode; it must also gate the **posted-write capture** (§3.1.1),
   not only the read path, or the write is captured and retired after the fact.
2. **System RAM's select** gains the same qualification (`docs/machine.md`).
3. **The map SRAM's own output enable** is gated by `/IOPAGE`, so physical A13–A19 are
   *parked* at a defined pattern during an I/O cycle rather than carrying a stale
   translation. That is what makes the map-write cycle of §6.3.1 safe as well.

### 6.3.3 Vector fetches, and what answers at `$FFF0`–`$FFFF`

The same override has a second consequence this document did not draw: with
`$FF00`–`$FFFF` bypassing translation, and the only I/O-page decodes being
`$FF40`–`$FF7F` (geographic) and the MMU's own window, **nothing on the backplane
answers a vector fetch at `$FFF0`–`$FFFF`.** The 6309 reads its reset vector from an
undriven bus. That is not a video problem, but it is a video *constraint*, because
the obvious repair (map a ROM into physical space) collides with §6.3's "`A19` = 0
RAM, `A19` = 1 VRAM" map, which reserves zero bytes for one.

**The machine's answer is CPU-module shadow ROM** (`docs/machine.md` §5 item 0):
`$FFF0`–`$FFFF` is served from 16 bytes of internal vector RAM in the STM32, always
on and writable through the MMU window; `$E000`–`$FEFF` is served from internal flash
at reset and switched off by a bit in the MMU window once the OS is up; and
`$FF00`–`$FFBF` continues to decode normally to cards and the MMU throughout, so this
card's registers work during boot. **Nothing on the video card changes** — the
physical map keeps both halves, no carve-out is needed, and `/IOPAGE` keeps the card
quiet during all of it. What it does cost is §16 item 8; see there.

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
then a ~~two~~ **three**-product-term mode mux — bitmap, Variant A and Variant B are
all in v1 (§10.1.5), so there are three sources per bit, not two. 17 bits × 3 = 51
terms across 17 macrocells, **3 each against the 5 an ATF15xx macrocell has before
cascading**. Product terms are still not the constraint. Checked in
[`hardware/gal/tile.check.ts`](../../hardware/gal/tile.check.ts), which asserts the
no-adder property by showing OR equals ADD over all 524,288 field combinations in
each variant.

> ⚠ **The MAP fetch is not a concatenation, and §6.4.2's "2,000 B" is why.** An 80×25
> map packed at 2,000 bytes needs `MAPBASE + cellRow × 80 + cellCol`, and **80 is not
> a power of two** — that is a multiply-accumulate, which is exactly the adder this
> section's argument says does not exist. The tile and font addresses are clean; the
> map address was never checked against the same rule.
>
> **Fix: a 128-byte row stride.** `MAPBASE` in `A18..A12`, cell row in `A11..A7`, cell
> column in `A6..A0` — concatenation again, and free. It costs **1,200 bytes** of the
> 512 KB nobody is using: 3,200 B rather than 2,000. `check:tile` asserts both halves.

Both variants below need the map fetch **pipelined one cell ahead** of the tile
fetch — a serial dependency, and the same shape of pipelining the card already runs
for index → LUT → output.

#### 6.4.2 Variant A — 8bpp tilemap

Per cell: fetch the map byte, then the 8 tile bytes for this row. **The pixel path
downstream is unchanged** — the bytes flow through the `'153` mux, the index latch,
the LUT and the output latch exactly as bitmap bytes do.

| | Bitmap | **8bpp tilemap** |
|---|---|---|
| Screen memory | 128,000 B | ~~2,000 B~~ **3,200 B** + 16 KB tile set — §6.4.1's stride note |
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

**Budget +1 to +2 GAL22V10** — **41–43 packages against Rev A's 40** (§14) — and fit
both pairs before committing. This is the item most likely to fail (§19 item 15).

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

> ⚠ **This section's opening is superseded by §6.4 and was not updated when §6.4 was
> written.** It reads as a settled rejection of hardware text; §6.4 reopens the
> question — *"that argument was about a bitmap-only card"* — and §6.4.5 concludes
> **"text stops being the span writer's problem"** at 2 CPU writes per cell against
> 13. §6.4.7 recommends building it. **As of 2026-09-06 the card's text engine is
> §6.4's Variant B character mode; this section is the fallback and the cost model
> for the span writer, both of which stay true and stay built.** §10.1.5 carries the
> decision.

~~There is no hardware text mode in either design, and there should not be one here
either~~: NitrOS-9's windowing draws into bitmaps, a hardware character generator
cannot mix with graphics per-pixel, and it would need its own memory and
serialiser (~8–12 ICs). **All three of those were true of a bitmap-only card and two
of them stopped being true once §6.4 asked the question directly** — the LUT's dead
127/128 is the colour path, and the scan-address generators are already loadable
counters. What survives is the first: a character generator cannot mix with graphics
*per-pixel*, which is §6.4.6's first limit and why the mode is global and switchable
rather than free. The span writer remains the text engine **in bitmap mode**, and the
figures below are what text costs when Variant B is not selected.

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
| Full-screen clear (128,000 px, span-solid) | ~500 | ~1.2 ms CPU, ⚠ **~20.3 ms to retire** (~~5.1~~) |

> ⚠ **The retire figure was wrong by 4× until 2026-09-08**, and §7.4's bound is what
> caught it: it assumed the span writer took all four chips' spare accesses in a slot,
> but `WPTR` names one chip at a time and two accesses do not fit the slack. **One byte
> per 158.9 ns slot**, so 128,000 bytes is 20.3 ms. The CPU-bound rows are unaffected —
> a line scroll is 1,040 writes of CPU against 0.81 ms of retire, and stays CPU-bound.

**A terminal never full-redraws** — it scrolls, and scrolling is 2.5 ms plus one
register write. That is the number that matters, and it is comfortable. The 62 ms
full redraw is a mode-change cost, paid once.

Compare the alternative the 64x4 does not have: a `TFM` of a pre-rendered 8×8×8bpp
glyph is 64 bytes at 3 cycles each = 192 cycles ≈ 92 µs per cell — **3× worse than
the span writer**, because the span writer moves 8 pixels per CPU write and `TFM`
moves one. Text belongs to the span writer; `TFM` earns its keep elsewhere (§10.2).

### 7.4 The span writer, respecified for 8 × 8 cells

§14 lists "span control" among the sequencer pair's duties and the mechanism itself
has never been written down here — it is inherited from minimal256, which was designed
around **6-pixel cells**. §6.1 says what changes and stops one step short of the
consequence:

> "colormin's span-mask serialises a byte and stops at `SPANLEN`; with 6-px cells two
> bits per write are wasted. At 8×8 the mask byte *is* the glyph row."

**The consequence is that span-mask mode does not consult `SPANLEN` at all.** Its
length is eight, always, because eight is the cell width: the byte the CPU writes is
exactly one glyph row and there is nothing to truncate. The length comes from a
three-bit counter — three bits *because* a cell is eight wide — and `SPANLEN` with its
`'161` pair belongs to span-solid alone.

**That is what makes §7.3's "13 writes per character cell" true.** `WPTR` ×3 + `WFG` +
`WBG` is five of setup, then eight glyph rows. `SPANLEN` is not among them. Had mask
mode needed it, a cell would be **14** writes and every text figure in §7.3 would be
7 % worse. `npm run check:seqctl` asserts the 13.

#### Where the state lives

| | Where | Why |
|---|---|---|
| the mask byte | `74HC165`, loaded at `WSTB` | its serial output *is* a register-file address line |
| span-solid's length | `74HC161` ×2, loaded at `WSTB` | §14's `SPANLEN` counter |
| **span-mask's length** | **3 macrocells in `seqctl`** | **the cell width, fixed at 8** |
| `SPANBUSY` | 1 macrocell | `VSTAT` b7, and the `/WAIT` condition |
| the pointer | `wcol` / `wrow` | §19 item 12 |

**The mask bit never enters the sequencer.** The `'165`'s serial output is wired to the
register file's address bit 0, which is why §13 requires `WFG` at `A0 = 0` and `WBG` at
`A0 = 1`. Choosing the source colour per pixel costs no macrocell and no product term
— it is an address line, and that placement rule *is* the mechanism.

#### One handshake, three terminations

```
  WSTB      a posted write has been latched (§3.1.1's '574s hold the address, the
            data, R/W and WMODE[1:0]) -> load the '165 and the '161s, zero the
            mask counter, set SPANBUSY
  SPNGRANT  the arbiter matched WPTR[1:0] against the CPU's chip and gave the span
            writer a spare access (§5.2.1)
  RETIRE    = SPANBUSY · SPNGRANT. One byte goes to VRAM. Drives WPTR's WINC, the
            '165's shift and the '161's count — one signal, three loads, because
            those three advance together by construction
  SPANEND   the last byte retired -> apply WADV, clear SPANBUSY
```

| `WMODE` | Mode | Ends when |
|---|---|---|
| `00` | direct | the **first** byte retires — §3.1.1's posted write |
| `01` | span-mask | the **eighth** byte retires — the cell width |
| `10` | span-solid | the `'161` pair's terminal count — `SPANLEN` + 1 bytes |

Loading the `'161` pair in mask mode is harmless, and that is what lets `WSTB` drive
both loads with no mode qualification: mask mode terminates on its own counter and
never looks at `TC`. `check:seqctl` asserts the eight-byte length **with `TC` held true
throughout**, so a leak from the solid path fails it.

#### Chaining, which is the whole text engine

`WADV = 01` ("next row, same column", §7.2) advances `WPTR`'s row at `SPANEND` and
reloads the column from the register-file shadow. Set it once and a glyph becomes
**eight mask writes and nothing else** — no pointer arithmetic between rows, no
`SPANLEN`, no mode changes. That is §7.3's 2.5 ms line scroll.

A span running off column 1023 wraps to column 0 of the same row (§19 item 12), which
is what the scanner does, so a glyph straddling the torus seam renders where the
display reads it.

#### ⭐ Broadcast writes — how to get the 4× back

**Proposal, 2026-09-08. The datapath for it is already wired.**

The retire rate is one byte per fetch slot because `WPTR` names one of the four
interleaved chips at a time. **In span-solid it does not have to.**

Two facts collide usefully:

1. **Every byte of a span-solid is the same byte** — `WFG` or `WBG`, one colour.
2. **Four consecutive framebuffer addresses `4n`…`4n+3` are the same *intra-chip*
   address `n` on four different chips**, because the chip select is `A[1:0]` and the
   intra-chip address is `A[18:2]`.

So a 4-byte group needs **one address, one data byte and four `/WE`** — a single 72 ns
access rather than four. It fits the 86.9 ns of slack easily, because the four accesses
are *simultaneous* rather than sequential, and sequential is what did not fit.

> ⭐ **And §14's parts list says the wiring is already there.** There is **one**
> `74HC574` posted-write data latch, four chips, and **no write-data mux or demux
> anywhere on the list** — so the latch already fans out to all four chips' data buses
> and the chip is chosen by `/WE`. Broadcast is not a new datapath; it is a different
> set of write enables on the one that exists.

| | one byte per slot | broadcast |
|---|---|---|
| Fill rate | 6.29 MB/s | **25.1 MB/s** |
| Full-screen clear | 20.3 ms | **5.1 ms** — against a 14.3 ms frame |
| Polygon crossover (`features.md` §6) | 75 px | **300 px** |
| A 200-pixel span | 31.8 µs, memory-bound | **11.9 µs, CPU-bound again — 16.8 Mpx/s** |
| **`SPANBUSY` worst case** | 40.7 µs | **10.2 µs** |

A 256-byte span is **4.0× aligned and 3.8× worst case** — three head bytes, then quads,
then three tail bytes. Software issuing a fill can align it.

**It lands exactly where the bottleneck is.** Span-mask gains nothing and needs nothing:
eight bytes retire in 1.27 µs against 2.38 µs per CPU write, so mask mode is already
CPU-bound. **Span-solid is the only retire-bound mode on the card.**

##### What it costs, and the one part that is real work

The logic is product terms rather than macrocells: a wide term on the arbiter's
`GSPNn`, a by-four increment on `WPTR`, a by-four countdown on `SPANLEN`.

**The pins are no longer the problem.** §10.1.6.3 priced the relief at one more
`GAL22V10` and **that GAL is built** — `gal/regfile.jedec.ts`, 2026-09-08 — which took
`vctrl` from 64 of 64 I/O to **50 of 64**. There is room to signal now, and §14.2's
two-chip framebuffer means there is barely anything to signal.

> ⚠ **The arbitration is the real work on four chips.** An all-or-nothing "grant all
> four" is one extra term and needs no feedback — but **during a `/WAIT` stall the CPU
> is holding one chip, so only three are free**, and the wide grant would never fire in
> exactly the case where the span writer is the bottleneck. Granting *whichever* chips
> are free works, and then the span writer has to learn how many it got: a count back
> from the arbiter into `WPTR`'s increment and `SPANLEN`'s countdown.

⭐ **§14.2 dissolves that, and it is why this stopped being a proposal.** The framebuffer
becomes **two ×16 parts instead of four ×8** — same four bytes per slot, same seventeen
address bits, half the packages — and then there is **one spare access per slot and one
grant to give**. Four byte enables on that access retire four bytes. Nothing to count,
no partial grant, no feedback path. The wide term *is* the design.

The cost is the other side of the same fact: spare bandwidth falls from four accesses
per slot to one, so the CPU and the span writer can no longer proceed in the same slot
on different chips and one of them waits **158.9 ns** — against 2.38 µs per CPU write.
§14.2.3 has the full comparison.

**Three things came out of this analysis and all three are taken**: the `R/W`
qualification below, `regfile.jedec.ts`, and §14.2's seven-SRAMs-to-four.

#### ⭐ How long `SPANBUSY` lasts — the bound `machine.md` §5 item 10 asked for

**Answered 2026-09-08.** `/WAIT` is `SPANBUSY · VRAMSEL · /IOPAGE · E`
(`gal/access.jedec.ts`), so the video card holds the machine only while a span is in
flight **and** the CPU is touching VRAM. The length of that is `WMODE` and nothing else,
because the retire rate is fixed: §3.1.1 gives **one granted retire per fetch slot**, and
a fetch slot is 158.9 ns.

| `WMODE` | Bytes | `SPANBUSY` | |
|---|---|---|---|
| `00` direct | 1 | **159 ns** | one posted write |
| `01` span-mask | 8 | **1.27 µs** | a glyph row — the cell width, §7.4 |
| `10` span-solid | **up to 256** | **up to 40.7 µs** | `SPANLEN` is a `'161` **pair**, so eight bits |

**40.7 µs is the number, and it is longer than a scanline.** Against the rest of the
machine: 85 bus cycles, 2.6 DRAM refresh intervals, 51 net framer byte-times, and just
under `sdcard.md` §4.4's 49 µs masked chunk.

> **Why the span writer is 6.29 MB/s and not 25.** Its pointer is one pointer. §2.1
> leaves one spare access per chip per slot and there are four chips, but `WPTR` names
> one of them at a time, and two sequential accesses do not fit the 86.9 ns of slack
> (2 × 72 ns). So the span writer retires **one byte per slot**, and every rate that
> depends on it follows from 158.9 ns.

**Three consequences, and only the third needs anything done:**

1. **DRAM refresh is unaffected** — `hardware/ram.md` §6.4's open question, closed. `/WAIT`
   here is qualified on `VRAMSEL`, so the CPU is stalled *on VRAM*; the DRAM bus is idle
   for the whole 40.7 µs and the refresh controller runs off `CLK25` regardless. **They
   never contend**, and a long span is 2.6 refresh intervals of free DRAM time.
2. **Interrupt latency gains up to 40.7 µs**, because holding `E` holds dispatch too.
   That belongs in `machine.md` §4's table beside PS/2's 1.3 ms and storage's 49 µs, and
   it is the smallest of the three.
3. ⚠ **A card that schedules against `E` starves.** `net.md` §4.3 does, and 40.7 µs is
   51 byte-times — a dropped frame every time a maximal span meets a received frame.
   **The fix is on that card and it is small** (`net.md` §16 item 5): free-run the framer
   phase on `CLK25` and gate only the host window on `E`. During a video stall the CPU is
   on VRAM, not on the net card, so its buffers are idle and its framers can have every
   slot.

##### ⭐ And only writes wait — taken 2026-09-08

`/WAIT` was `SPANBUSY · VRAMSEL · /IOPAGE · E`, which stalled the CPU on **any** VRAM
access. §3.1.1 says what the backstop actually protects: **the depth-1 posted-write
latch**, which a second CPU *write* during a span would overwrite.

**A read does not touch that latch**, and §5.2.1's arbiter already gives the CPU its
chip ahead of the span writer, so a read has no conflict to wait for either. It was
stalling for up to 40.7 µs anyway.

**`WAIT.oe` gains `& !RW`** — one literal on an output-enable term that already exists,
on a GAL that had the input pin free.

| | |
|---|---|
| Writes | still wait — **that is the throttle** that stops the CPU outrunning the span writer, and it is deliberate |
| **Reads** | **never wait** |

⭐ **What it buys is on the other side of the card.** `features.md` §8 and §9's sprite
save-behind, mouse cursor and read-modify-write pixels are **all VRAM reads**, and they
stop being exposed to the bound entirely.

**A read during a span sees a partially retired span.** That is the caller's own span
and `VSTAT` b7 says whether it has finished — a software rule, not a hazard.
`gal/access.check.ts` asserts the float on a read.

**And the practical bound is zero, not 40.7 µs.** `VSTAT` b7 **is** `SPANBUSY` (§13), the
read has no side effects, and it is in the I/O page — so it does not trigger `/WAIT`.
**Software that polls it before touching VRAM never stalls the machine at all**, and
`/WAIT` goes back to being the backstop §3.3 calls it rather than the normal path. One
bus cycle of poll against up to 85 of stall.

#### What it costs

`seqctl` is **7 macrocells of 10**, 3 free, 8 of 14 input pins — the most headroom of
any GAL on the card. Checked over all 16 states × 128 input combinations, plus a span
run end to end in each mode and the no-grant stall that holds `/WAIT`.

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

  > ⚠ **"Costs zero parts" is true of the mux *select* and is not yet true of what
  > the four latches hold** — 2026-09-06, from fitting the mux phasing
  > ([`hardware/gal/seqph.jedec.ts`](../../hardware/gal/seqph.jedec.ts)). Chip *n*
  > holds the byte at the column where `c mod 4 = n`, so if all four fetch latches
  > are loaded from a common address bus at a common instant, then during fetch slot
  > *g* every chip holds a byte of group *g*. With `HSCROLL[1:0] = p`, the mux emits
  > `4g+p`, `4g+p+1` … and then **wraps to chip 0, which still holds `4g+0`** — the
  > line steps backwards, `4−p` pixels in. `check:seqph` computes both sequences and
  > asserts they diverge for every `p ≠ 0`; it is arithmetic, not simulation.
  >
  > **The mechanism that fixes it is already on the card**: §5.2.2's *per-chip*
  > fetch-latch clocking, which lets chips `0..p−1` take the next group's byte while
  > `p..3` still hold this one. §5.2.2 justifies per-chip clocking by the spare-access
  > grant and by tile mode, and never mentions scroll; §8 promises the scroll and
  > never mentions the latches. **The two sections describe one mechanism from
  > opposite ends and do not meet.** No new package — the four `FCLK` macrocells
  > exist — but the equations are a phase-dependent offset rather than four copies of
  > one term, and that is §19 item 23.

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

**Cost, honestly stated:** +4 ICs net (2 LUT SRAM, 2 output registers — `74AHCT273`,
not `'574`, see §9.2 — 1 `'593` index counter, −1 because the `'244` mode-bypass is
deleted anyway), 15 ns SRAM instead of 20 ns, and it is the **tightest remaining path
in the dot pipeline** at 39.7 ns (28 ns used, 11.7 ns margin — §6.1). The analog stage
that turns the LUT's output into a VGA signal is §9.1, and it was missing from every
earlier version of this document. If the bench says that path does not close,
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

### 9.1 The drive stage — the ladders cannot face the connector on their own

> ⚠ **Neither this document nor colormin's ever specified what drives the VGA
> connector.** "3 × R-2R SIP, 5/6/5 ladders" (§14) is the entire analog back end as
> listed, and it is not buildable. The arithmetic below is why, and it is the
> arithmetic that was missing.

**What VGA asks for.** The RGB lines are **double-terminated 75 Ω**: a 75 Ω source
impedance at the card driving a 75 Ω termination inside the monitor, with peak white
**0.700 V** *at the load*. Sync is not on these lines — HSYNC and VSYNC are separate
TTL pins — so RGB has no sync tip and the whole 0 → 0.7 V range is picture.

```
  loaded peak white          0.700 V into 75 ohm
  open-circuit swing needed  1.400 V   (the divider halves it)
  current at peak white      1.400 V / 150 ohm = 9.33 mA per channel
  three channels, peak       28.0 mA;  ~14 mA average on typical picture
```

**Why a bare ladder cannot do it.** An R-2R ladder's Thevenin output impedance is `R`,
independent of code. To *be* the 75 Ω source, the ladder must be built with
`R = 75 Ω`, hence `2R = 150 Ω` in every leg:

```
  MSB leg current, 5 V logic:  5 V / 150 ohm = 33.3 mA
  74AHCT574 output rating:                    +/- 8 mA
                                              -> 4.2x over rating
```

That is not a margin question. The pin does not source 33 mA; it sags, and it sags by
a **code-dependent** amount because the ladder node it is fighting moves with the
code. On the 6-bit green channel one LSB is `0.700 / 63 = 11.1 mV` and an AHCT output
overdriven to 8 mA is already 0.3–0.5 V below rail — **tens of LSBs of error**, so
§18 step 1's "DNL measured across all 64 green codes" cannot even be attempted.

**The fix: a high-impedance ladder and an emitter follower per channel.** Raise `R`
until the logic drives it comfortably, then buffer, then set 75 Ω with a series
resistor:

| Element | Value | Arithmetic |
|---|---|---|
| Ladder `R` / `2R` | **1.00 kΩ / 2.00 kΩ**, 1 % | worst-case per-pin current `5 V / 2.00 kΩ` = **2.5 mA** ≤ 8 mA ✓ |
| Ladder node settling | ~287 Ω after the divider, ~15 pF stray | `τ` = 4.3 ns, `3τ` = 13 ns < the 39.7 ns dot ✓ |
| Base divider `R_shunt` | **402 Ω**, 1 % | `4.85 V × R/(1000+R) = 1.40 V` → `R = 406 Ω` |
| Buffer | **3 × NPN emitter follower**, β ≥ 300 (BC547C class) | `I_b = 9.33 mA / 300 = 31 µA` into 287 Ω = **8.9 mV = 0.8 LSB** green |
| Series source | **75 Ω**, 1 % | with the monitor's 75 Ω gives the 2:1 divider assumed above |
| Follower dissipation | `(5 − 1.4) V × 9.33 mA` = **33.6 mW** at peak white | TO-92 ✓ |

Two properties this buys that the bare ladder does not have, and they are the reason
it is worth three transistors:

- **Per-pin current is now bounded by the leg alone, not by the load**, so there is no
  code-dependent sag at all. DNL becomes a resistor-tolerance question: 1 % on the MSB
  leg is ±0.5 % of full scale = ±3.5 mV = **±0.32 LSB** on the 6-bit channel, so the
  converter is monotonic by construction. A matched SIP network does better still.
- **Bandwidth is set by the base node, not the connector.** A 2N3904/BC547 at 10 mA
  has `f_T` ≈ 300 MHz against the 25.175 MHz dot rate; the 13 ns ladder settling above
  is the binding number, and it fits inside the dot.

**Black level, and the one subtlety.** An NPN follower into a resistive-to-ground load
cuts off as its emitter approaches 0 V, so the bottom code or two are nonlinear.
Return the ladder's `2R` legs to a **+V_be reference** — one forward-biased diode of
the same family, thermally coupled to the three transistors, shared across all three
channels — so code 0 puts each base at `V_be` and each emitter at **0.000 V** with the
device just conducting. Residual mismatch between the shared diode and the three
`V_be`s is ±20–30 mV at the base, ~±2 LSB of green, and §9.2 removes even that: the
blanking level and the black level travel the **identical** path, so the monitor's
back-porch clamp subtracts the residual exactly. That is the argument for doing
blanking after the LUT rather than anywhere else.

**Parts.** 3 × NPN, 1 × diode, 3 × 75 Ω, 3 × 402 Ω, 3 × bias resistors, plus the three
R-2R SIPs already listed. **No ICs** — they go on §14's discrete line, and their ~40 mA
peak goes into §14's power total. The modern alternative, a monolithic triple video
buffer, is one package and is not period; recorded so the choice is deliberate.

### 9.2 Blank-to-black — a mechanism, not an assumption

**RGB must sit at 0 V for the whole of both porches and the sync interval.** This is
not cosmetic: a VGA monitor establishes its black reference by **clamping on the back
porch**. Whatever voltage is present there *becomes* black, so a card that leaves the
last active pixel's colour on the ladders during the back porch has told the monitor
that that colour is black, and the entire picture shifts against it, per line, with
the content.

Two mechanisms that look like they solve it and do not:

- ~~**`/OE` on the post-LUT latch.**~~ Three-stating the register **floats** the
  ladder's inputs. A floating R-2R ladder does not output 0 V; it outputs whatever
  leakage and stray coupling give it, which is undefined, drifts, and is not black.
- ~~**Force palette index 0 during blanking.**~~ Wrong for a reason specific to this
  card: **palette entry 0 is programmable**. §9's boot identity palette happens to put
  black there, but a fade-to-white, a per-image quantisation, or a palette-cycling
  effect can put any of 65,536 colours in entry 0, and the porches would be painted
  with it.

**Blanking must therefore act *after* the LUT**, on the last register before the
ladders — and it costs nothing:

> **Specify the two post-LUT output latches as `74AHCT273`, not `74AHCT574`.** Same
> 8-bit D register, same family, same speed grade; the `'273` has an asynchronous
> `/MR` that forces all eight outputs to **0**, where the `'574` has an `/OE` that
> forces them to nothing. `/MR` is driven by the registered `BLANK` term already
> produced by the sync GAL pair (§14). The post-LUT latch drives only the ladders and
> never a bus, so the `'574`'s output enable was unused anyway. **Zero packages,
> zero GAL macrocells** — `BLANK` exists already.

Timing: `BLANK` is a *registered* GAL output, so it changes on a dot-clock edge and
`/MR` therefore asserts on a dot boundary; `74AHCT273` `/MR`-to-output is ~7 ns
against the 39.7 ns dot, so the first blanked dot is fully black and the first active
dot after the back porch is fully coloured. Both ladders go to all-zeros together,
which through §9.1's `V_be`-referenced return is 0.000 V at the connector.

### 9.3 `BORDER` (+$16) is deleted, and here is why

The register at `+$16` was carried over as "border/overscan palette index". **VGA
timing has no overscan.** A 640×400@70 line is 800 dots: 640 active, then front porch,
sync, back porch. There is no region of the raster into which a border colour can
legally be painted, and painting one into the porches is precisely the back-porch
clamp corruption §9.2 exists to prevent — a *worse* artefact than having no border.

The honest alternative is a **reduced active window**: display, say, 608×384 of
picture inside the 640×400 active area and paint the 16-pixel margin. It costs more
than it looks:

| What it needs | Where it lands | Status |
|---|---|---|
| Two more window compares (H and V) with programmable edges | sync GAL pair | §19 item 8 — the pair is already at zero macrocell margin (§19 item 8's arithmetic) |
| A border index register and its decode | register file | free |
| **A path to inject the border index into the pixel stream** | the `'153` pixel mux | **there is none** — all four `'153` inputs are the four framebuffer chips |

The last row is the blocker. Injecting a fifth source means restructuring the 4 × `'153`
into an extra mux rank, inside the 39.7 ns dot path that §6.1 already identifies as
the tightest on the card, to buy a feature the framebuffer gives away for free.

**Decision: delete the register.** The torus is 1024 columns wide against a 640-pixel
window and 512 rows against 400 (§8), so a border is a **fill in off-screen memory**
positioned by `HSCROLL`/`VSCROLL` — one span-solid write per row, at zero hardware
cost and with all 256 colours, changeable per scanline from the list engine. `+$16`
is handed back to the reserved block in §13. The one thing genuinely lost is a border
that costs no VRAM, and this card has 384 spare columns; it is not short of VRAM.

---

## 10. Blitter, list engine, and the instruction the 64x4 doesn't have

### 10.1 The GAL wall, stated plainly

blitter.md §6.2 already flags it: the card is ~~8~~ **9** GALs (§14 — §5.2.1's
spare-access arbiter is the ninth), the full blitter adds 10,
and **"eighteen GAL22V10s is the point where the honest question becomes 'why not
one CPLD'."** ⚠ **That question was open when this section was written and the answer
was "no CPLDs".** §10.1.5 gave the rule up for this card and the root `README.md`
retired it for the machine on 2026-09-08. **Everything from here to §10.1.5 is the
argument that produced that reversal**, and it is kept for that reason — the wall is
real and the card walked into it:

| Build | GALs | Card ICs (with `'153` mux) |
|---|---|---|
| Rev A: framebuffer + span writer + palette + read-back | **9** | **40** |
| + list engine (the copper) | 11 | 45 |
| + blit datapath | **~21** | ~59 |

> ⚠ **This table is the GAL build and §10.1.6 replaced it.** The card is **2 ×
> `ATF1508AS` + 2 × `GAL22V10` + 4 SRAM + 20 packages = 28 ICs** — §14.1 has the arithmetic.
> The section below is kept because **it is the argument that produced that decision**:
> the wall it describes is real, the card hit it, and what follows is what happened
> next.

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

#### 10.1.1 Where the macrocells actually go, and what can be removed

Written after five of the ten were fitted (`hardware/gal/`, 2026-09-06), because the
answer to "how do we need fewer GALs" turns on which bits have to reach a pin.

| Block | GALs | Macrocells | Register bits | Must those bits reach pins? |
|---|---|---|---|---|
| sync — `hgen`/`vgen`/`vdec` | 3 | 27 of 30 | 18 | **No** — only 6 signals leave the group |
| scan address — `hadr`/`vadr` | 2 | 17 of 20 | 17 | **Yes** — they are the framebuffer address bus |
| `WPTR` / span pointer — `wcol`/`wrow` | 2 | 19 of 20 | 19 | **Yes** — they are the VRAM address path |
| sequencer — `seqph` + `seqctl` | 2 | 17 of 20 fitted, 13 more budgeted (§19 item 23) | 5 | the dot phase and the mask counter are internal |
| arbiter (§5.2.1) — `arb` | 1 | **8** of 10 | 0 | — |

**Nine of the ten are fitted**, and the tenth is the decode half of the sequencer
pair, whose two routes are in §19 item 23. Three parts are now full in **both**
dimensions — `vdec` at 14 of 14 pins, `wcol` at 10 of 10 macrocells *and* 11 of 11
pins, and `arb` once `/WAIT` and `SPNGRANT` moved onto it — so neither tile mode nor
the list engine can borrow capacity there. What is left is on `seqctl` (3 macrocells,
6 pins) and `hadr` (2 and 2).

**The card is GAL-heavy for exactly one reason: 54 of those macrocells are counter
bits, and a GAL22V10 has no buried nodes.** Every register costs a macrocell *and* a
pin whether or not anything outside the package ever looks at it. That is what made
the sync section three parts (§19 item 8) and it is what will decide the sequencer
pair.

So the obvious lever is a GAL-class part with buried registers, and there are two —
⚠ **evaluated while the no-CPLD rule still stood, and now of interest only for the
arbiter's `GAL22V10` (§10.1.6.3), which fits a plain 22V10 at 10 of 10:**

- Lattice **GAL6001/6002** — 10 I/O macrocells plus **8 buried registers**, 24-pin,
  1990. Unambiguously a GAL.
- Atmel **ATF750C** — 10 output plus **10 buried** macrocells in the 22V10's own
  24-pin footprint, still in production alongside the ATF22V10C.

**It saves exactly one package.** Buried registers help only where the register does
not need to leave the chip, and on this card that is the sync trio and nothing else:
its 18 counter bits are internal state and only `HSYNC`, `VSYNC`, `BLANK`, `VBLANK`,
`HBLANK` and `/IRQ` go anywhere. Two ATF750Cs hold all of it. The scan and `WPTR`
pairs' 36 bits **are** the address buses — no part choice changes that, because the
output is the point.

| Change | GAL count | What it costs |
|---|---|---|
| sync trio on two buried-register parts | 10 → **9** | the "GALs and nothing more programmable" rule, and a part nobody has second-sourced |
| scan / `WPTR` pairs on buried-register parts | 10 → **10** | nothing gained — the bits are the outputs |
| pure counters on `'161`/`'163` instead | 10 → 8, ICs 41 → **47** | worse on packages *and* area; better only on current |

**One package in ten, for the house rule.** That is worth stating precisely, because
"use a bigger GAL" reads like it ought to save more and on this particular card it
does not.

**What did come off, at no cost, by fitting rather than estimating:**

- **§19 item 15's tile-mode contingency package.** The scan pair is 17 of 20, not
  20 of 20 — three macrocells spare and two spare input pins.
- **The arbiter's four `SRCSEL` macrocells.** §14 budgets it as "8 grants + 4 source
  selects", which is 12 outputs on a part with 10 and should have been an overflow
  nobody had noticed. It is not one: §5.2.1's own equations say
  `SRCSEL[n] = GRANT_CPU[n]` — *the same signal*, not a second one. The arbiter is
  **8 macrocells with 2 spare** and six inputs. (If the `'153` and address-mux loads
  want a separate driver, a duplicate macrocell costs one product term and there is
  room for two of them.)

Against that, the sync trio's third part is the only genuine *increase*, and it is
measured rather than estimated. Net against the pre-fit projection of 9 + a tile-mode
contingency + an arbiter that did not fit: **10, and settled for five of them.**

#### 10.1.2 The CPLD question, answered with numbers

§10.1 sets the trigger at *"eighteen GAL22V10s is where the honest question becomes
'why not one CPLD'"*, and the card is at ten — so by its own rule the question is not
live. Two things say otherwise, and both are new.

**The chronology does not block it.** §15's period audit places this card at
**1989–90**. Altera's EP300, the first reprogrammable PLD, is **1984** — two years
*before* the GAL22V10 the card already uses. The MAX 5000 family, the first part that
is architecturally a CPLD rather than a large PAL, is **1988**, a year before the
card's own date. A MAX 5000 here would be the *third*-newest part on the board: §15
already carries 74AHCT at ~1990 and the 1 Mbit SRAM at ~1989–90 and flags both as
newer. **"No CPLDs" is not a period rule on this card. It is a style rule** — one
function per package, everything visible on a scope — and that is a good reason to
keep it, but it is not the reason the README gives.

> **This paragraph is what eventually retired the rule**, three cards later. The root
> `README.md`'s 2026-09-08 note cites it by section number: *"it was never a period
> rule — Altera's first EPLD is 1984 and the first CPLD 1988, both older than parts
> this machine already uses."*

**And the count that reaches eighteen is the machine's, not the card's.** Ten here,
two on the motherboard, five on audio's sequencer, plus decode GALs on serial, storage
and PS/2 — `hardware/gal/README.md` puts it at roughly twenty. The threshold was
written per-card and the number that crosses it is per-machine.

**What one die would actually absorb** — `npm run census`, computed from the fitted
designs rather than counted by hand:

| | |
|---|---|
| ten GAL22V10s | 90 macrocells, **188 signal pins** |
| 21 inter-package nets | 43 pins |
| outputs nothing outside the group consumes | **54 pins** |
| | **97 of 188 pins — 52% — are an artefact of the packaging** |
| external I/O, everything that must reach a pin regardless | **84** |
| macrocells: 90 fitted, ~13 of §19 item 23's unfitted decode, **+17 address mux** | **120** |

> ⚠ **The address mux was missed on the first pass and is corrected here.** On GALs
> the scan pair and the `WPTR` pair tri-state onto a shared framebuffer address bus and
> the mux costs nothing. Inside one die two macrocells cannot drive one pin, so the 17
> address outputs are 17 *further* macrocells fed by both counter sets — and the two
> sets stay, buried. It is the one place where merging the packages costs silicon
> rather than saving it.

Half the pin count is the packaging talking to itself. The 54 is the sharper half: a
22V10 has **no buried nodes**, so every counter bit and every intermediate term is on
a pin whether or not anything wants it — 36 address-counter bits, the arbiter's eight
grants, the mask counter, the dot phase.

**One `ATF1508AS` holds it, and only just**: 128 macrocells against 128 once the
affordable absorptions of §10.1.3 are applied, and 80 I/O against 75. The `ATF1504AS`
(64 macrocells) does not, alone.

| | GALs / CPLDs | Card ICs | Board area for the logic |
|---|---|---|---|
| ten `ATF22V10C`, DIP-24 | 10 | 41 (44 with §19 item 23's helpers) | ~26 cm² |
| one `ATF1508AS`, TQFP-100 | 1 | **32** | **~2.6 cm²** |
| one `ATF1508AS`, PLCC-84 | 1 | 32 | ~9 cm² |

§14 puts the card at ~150 of 160 cm² and calls the slack gone. This returns 17–23 cm²
of it, which is more than the four `'153`s of §19 item 2 were ever going to.

> ⚠ **The number that would decide it is the one not verified here.** §14's power
> table makes the ten GALs **700–900 mA of a ~1.2–1.8 A card**, easily its largest
> line, and Microchip's `Icc` figures for the ATF1508AS could not be retrieved. If one
> CPLD lands near 150 mA the card falls to ~0.7–1.1 A, and §14's conclusion that a
> linear 7805 "dissipates 10.5 W and needs a heatsink that does not fit the Eurocard
> envelope" stops being true — the switching pre-regulator and the multiple backplane
> power pins both come back into question. **Get the datasheet `Icc` before treating
> any of this as settled.**

**What would and would not survive the change.** The equations, the models and every
check in `hardware/gal/` are device-independent and transfer unchanged — a CPLD would
be verified against the same `sync.model.ts`, `scan.model.ts` and `seqctl.model.ts`.
What does not transfer is `hardware/gal/jedec/`: its assembler and fuse-map simulator
are a GAL22V10 and nothing else, and an ATF1508AS is fitted by Microchip's own
`fit1508.exe`. The verification investment survives; the fitter does not.

#### 10.1.3 Part selection — `ATF1508AS`, TQFP-100

**Decided 2026-09-06.** The comparison this card invites is with the GIME and the
VIC-II, and both of those are single custom ASICs; holding this design to discrete
GALs while measuring it against them is not a like-for-like fight. The house rule is
restated as a style rule (§10.1.2) and set aside for the video card.

**The ordering code carries a trap.** The 5 V device is `ATF1508AS`; **`ATF1508ASV` is
the 3.3 V part** — two datasheets, "ATF1508AS(L) **5V** 128-Macrocell" and
"ATF1508ASV(L) **3.3V** 128-Macrocell". The cheap listings are mostly ASV: an
`ATF1508ASV-15AU100` is ~$6 where an `ATF1508AS-10AU100` is ~$16. On a 5 V card the
$6 part is the wrong one.

**The package is decided by pins, again.** `npm run census`, with the absorption of
§10.1.2 applied:

| Package | Ordering | User I/O | Takes 119 macrocells / 71 I/O? |
|---|---|---|---|
| PLCC-84 | `…JC84` | **64** | ✗ — 7 short, and it is the socketable one |
| **TQFP-100** | **`…AU100`** | **80** | ✓ **9 spare** |
| PQFP-160 | `…QC160` | 96 | ✓ but 160 pins for 71 |

> ⚠ **Superseded by §10.1.5 and §10.1.6**: with §6.4's Variant A and B in v1 the
> design needs 89 I/O, and with §10.3's list engine it needs 163 macrocells — more
> than any one `ATF1508AS`. **The build is two `ATF1508AS-…JC84`, PLCC-84, socketed.**
> The rest of this section — voltage, speed grade, the ASV trap — is unchanged, and
> `JC84` is the cheap end of the range.

**So: `ATF1508AS-…AU100`, 5 V, TQFP-100, `-15` speed grade** — the same grade §14
already specifies for the GALs, and the slowest is the cheapest. ⚠ Confirm a `-15` is
stocked in 5 V TQFP-100 before committing; DigiKey's `-15AC100` is a Rochester
listing, and `-10AI100` is marked obsolete. Falling back to `-10` costs money, not
margin.

**It is cheaper than what it replaces**, which was not the expected result: ~$16
against ten `ATF22V10C` at $2–3 each, and it deletes four more packages on the way.

| | Card ICs | Logic area |
|---|---|---|
| ten GALs + `'244` + `'273` + `'165` | 41 | ~26 cm² |
| one `ATF1508AS` TQFP-100 | **29** | ~2.6 cm² |

**Two things this costs, and neither is money.** TQFP-100 is 0.5 mm pitch surface
mount: the PLCC-84 socket that would suit a hand-built Eurocard is exactly the package
that does not fit, so the card gains a fine-pitch part and loses the ability to pull
the logic and reseat it. And `hardware/gal/jedec/` stops applying — its assembler and
fuse-map simulator are a GAL22V10 and nothing else. The equations, the models and all
164 checks are device-independent and transfer unchanged; the fitter is
Microchip's `fit1508.exe` from here.

**The 3.3 V `ATF1508ASV` question, closed — on cost, not on tolerance.**
`reference/datasheets/ATF1508AS.pdf` is now in the tree and it confirms the family
splits its rails: `VCCINT` for the core, `VCCIO` per bank, with `VIH` specified as
`VCCIO + 0.3 V`. On the 5 V `AS` that means 5 V inputs, and the same structure makes
it *likely* the 3.3 V `ASV` interfaces 5 V with `VCCIO` tied to 5 V — but that is the
`ASV`'s datasheet to state and this is not it, so the tolerance question stays
formally open.

**It does not need answering, because the ~$10 saving buys a rail the machine does not
have.** `ASV` needs `VCCINT` at 3.3 V; §17's backplane carries 5 V, so the card would
gain a regulator, a rail and a decoupling story to save ten dollars once. **Buy the
`AS`.**

**What the datasheet changes about the design, beyond the price:**

- **Buried registers are confirmed** — *"Maximum Logic Utilization by Burying a
  Register within a COM Output"*. §10.1.2's census assumed it; it is a feature line.
- ⚠ **Five product terms per macrocell, expandable to 40 by cascade.** The 22V10's
  8–16 term macrocells are not the shape of this part. The widest equations fitted —
  `V9` at 16 terms, `SPNGRANT` at 16, `VBLANK` at 13 — all need cascade chains, which
  `fit1508.exe` builds automatically and which cost delay. Not a blocker at 25 MHz,
  but **the placement rule of §19 item 8 is a GAL rule and does not carry over**: on
  this part the sorted-pairing constraint simply disappears.
- **Two bytes of User Signature**, against the GAL's eight. The `A6309Vn` strings in
  `hardware/gal/*.jedec.ts` do not fit; a two-byte revision code does.
- **Three global clocks, six global output enables, a global clear** — the 22V10's one
  clock and one shared asynchronous reset were a real constraint on the sync trio
  (§19 item 8) and are not one here.

**Nothing above obliges the rest of the machine.** The motherboard's two GALs and the
audio card's five are unaffected; §10.1.2's argument was always about this card's ten.

#### 10.1.4 Can it be squeezed into PLCC-84? — no, and here is how close

PLCC-84 is the package a hand-built Eurocard wants: a socket exists, it can be pulled
and reseated, and it is the cheap end of the range. It was worth trying.

**The budget, from `npm run census`:** 128 macrocells and **75 I/O** after absorbing
everything that fits in 128. The packages, counting honestly:

| | Bidirectional I/O | + dedicated inputs | − JTAG | Usable | Verdict |
|---|---|---|---|---|---|
| PLCC-84 | 64 | 4 | not wired¹ | **68** | ✗ **7 short** |
| TQFP-100 | 80 | 4 | −4 | **80** | ✓ 5 spare |
| PQFP-160 | 96 | 4 | −4 | **96** | ✓ |

¹ The four dedicated inputs are input-only, which suits this design — it has ~50
outputs and ~25 inputs. And JTAG costs four I/O only when it is wired for in-system
programming: **a socketed part is programmed out of circuit and keeps them.** That is
the one structural advantage PLCC has here, and it is worth 4 pins.

**Seven pins short, and they do not exist.** What was tried:

| | |
|---|---|
| one shared `/OE` across the three posted-write address `'574`s | −1 |
| the four per-chip `/WE` from an external `'139`, fed by 2 select bits + a strobe | −1, +1 IC |
| **`FCLK0..3` collapsed to one common fetch-latch clock** | **−3, and it costs byte-granular horizontal scroll** (§8) |

−2 without giving anything up, so **73 against 68**. Taking the third gets to 70 — still
short, and §8's sub-pixel smoothness is not worth trading for a package.

**What does fit in PLCC-84 is two `ATF1504AS`**, socketed, if the `'165` serialiser
stays an external IC rather than being absorbed:

| | Macrocells | I/O |
|---|---|---|
| A — scan and `WPTR` counters, the address mux, the arbiter | 63 of 64 | ~50 of 68 |
| B — sync, sequencer, span control, decode | 57 of 64 | ~65 of 68 |

plus ~15 inter-part nets, costing a pin at each end. It works, it is two sockets
instead of one fine-pitch part, and it costs back some of what merging bought.

> ⚠ **"128 of 128 macrocells" was an artefact of this census and is withdrawn.** It
> absorbed everything that fitted in 128, which optimises for pins when pins are not
> the binding constraint: absorbing the `'165` buys three pins the TQFP-100 does not
> need and costs eight macrocells the card does. Taking only what the 80-pin target
> requires — and every absorption that costs no macrocells, because those are free —
> the real figure is **120 of 128 macrocells and 78 of 80 I/O.** Two pins and eight
> macrocells spare.

#### 10.1.5 §6.4's variants are in v1, and they set the package

**Decided 2026-09-06.** §6.4.5 is the deciding paragraph and it is easy to miss behind
§7's flat opening: *"**Text stops being the span writer's problem.**"*

| Text operation | Span writer (§7.3) | Character mode (§6.4.5) |
|---|---|---|
| One cell | 13 writes, ~31 µs | **2 writes, ~4.8 µs** |
| Scroll one line | ~2.5 ms | **~0.4 ms** |
| Full 80×25 redraw, per-cell colour | ~62 ms | **~9.5 ms** |

**§2.1 is why this is not optional.** That section's own conclusion is that the card
has ~77× more memory bandwidth than the CPU can consume and that *"bandwidth is not
the constraint on this machine — **the CPU is**"*. A 6.5× reduction in CPU writes per
cell is the single largest thing on this card that acts on the actual bottleneck, and
§6.4.3's comparison against the chip being replaced is not close: **256 freely defined
attributes against the GIME's 8 × 8, and any RGB565 pair against palette entries 0–7.**

**Two variants, and they stack.** A is the 8bpp tile fetcher — playfields, sprites,
every pixel independently coloured. B is the 1bpp character generator that makes text
cheap, and it needs A's fetch machinery. §6.4.7 recommends A and calls B *"worth it
for a genuinely cheap 80×25 console"*. `npm run census`:

| | I/O | Macrocells |
|---|---|---|
| base, bitmap card | 78 | 120 |
| **A** — map byte (+8 I/O), address mux (product terms), second fetch cadence (+5 mc) | 86 | 125 |
| **B** — serialiser load/shift (+2), LUT page select (+1), three-access cadence (+3 mc) | **89** | **128** |

**So the part is `ATF1508AS` in PQFP-160**, not TQFP-100 — which is 9 pins short. And
the macrocells land at **128 of 128**, which this time is real and not the census
artefact of §10.1.4:

> ⚠ **The part is full**, and §10.3's list engine has nowhere to go — see §10.1.6,
> which is the answer to that and changes the package.

**What §7 keeps.** The span writer is not deleted — it is the bitmap-mode text engine,
the fill and clear engine, and §6.4.6's limit 1 means bitmap regions still need it.
`seqctl` and §7.4 stand unchanged; `check:seqctl` still asserts the 13 writes per cell,
which is now the *fallback* figure rather than the headline one.

**Two costs to keep in view**, both §6.4's own:

- **Character mode reintroduces per-cell colour limits** — two colours per cell, from
  a 256-entry attribute table. §6.4.7 flags it as *"the one thing this card currently
  does not have and both period chips do"*. It is per-mode and switchable, not a
  property of the card.
- **The glyph serialiser lands on the tightest path on the board** (§6.4.6 limit 3):
  its clock-to-Q goes inside the 11.7 ns the index → LUT → output chain has at
  39.7 ns, and `'HC` will not shift at 25.175 MHz. `'AHC165`, and it is §19 item 17's
  bench measurement before layout.

#### 10.1.6 Two PLCC-84 parts — and this is the build

**Decided 2026-09-06.** The `ATF1508AS` in **PLCC-84 has all 128 macrocells**; only
the I/O is cut, to 64 (+4 dedicated inputs, and JTAG's four come back because a
socketed part is programmed out of circuit). That one fact settles the question:

| | Macrocells | Pins | Area |
|---|---|---|---|
| §6.4 A+B, plus §10.3's list engine | **163** | 91 external | |
| 1 × `ATF1508AS` PQFP-160 | 128 — **35 over** ✗ | 91 of 96 ✓ | ~7.8 cm² |
| **2 × `ATF1508AS` PLCC-84** | **256** ✓ | 119 of 136 ✓ | ~22 cm² |
| 2 × `ATF1504AS` PLCC-84 | 128 — 35 over ✗ | 119 of 136 ✓ | ~22 cm² |

The list engine costs **almost no pins and a lot of macrocells** — 19 for the `LIST`
pointer, ~10 for the descriptor latch and opcode decode, ~6 for sequencing — because
its interface is internal: it reads VRAM through the arbiter and address path that
already exist, and §10.3's `MOVE` is *"one SRAM write into the register file"*, also a
path that exists. Pins have bound every decision on this card so far. **This is the
first one macrocells decide.**

**The PQFP-160 is 35 macrocells short**, so taking it means the list engine becomes a
second package later anyway — at which point the board carries two parts regardless,
and the two it should carry are the socketed ones.

**93 spare macrocells changes what else is possible.** The absorptions §10.1.4 had to
refuse for costing macrocells all come back: `CTRL`'s `'273` (+8), the `'161` `SPANLEN`
pair (+10) and the `'165` (+8) fit easily, taking **189 of 256** and deleting four more
packages while saving 10 further pins.

> ⚠ **One thing the ATF1508AS costs that the ATF1504AS does not: verifiability.**
> [prjbureau](https://github.com/whitequark/prjbureau) documents the ATF15xx fuse maps,
> and its coverage is asymmetric. Its own status table rates the ATF1508AS fuse
> database **"Partial"** and its programming path **"Untested"** — and the checked-in
> `database.json` has no 1508 entry at all, only 1502 and 1504. The ATF1502 is the
> only device rated Complete on both. So the loop that caught
> the `WPTR` hold-gating defect — read the fuse map back, execute it against the model
> — **cannot be reproduced on an ATF1508AS.** Verification stops at the design.
>
> It is a smaller loss than it first looks: that loop existed because *we* were the
> fitter and had to check our own work. With `fit1508.exe` doing place and route the
> question is whether we described the design correctly, not whether the fuses are
> right. But it is a real difference and it is the one argument for 3 × `ATF1504AS`
> (192 macrocells, fully documented) over 2 × `ATF1508AS` — at ~33 cm², which is worse
> than the ten GALs it replaces. **Recorded, not acted on.**

**Three costs, and none of them is macrocells:**

- **Area.** ~22 cm² socketed against the PQFP-160's ~7.8, and against ten GALs' ~26.
  §14 has the card at ~150 of 160 cm², so the CPLD's area windfall largely evaporates
  — the win is ~4 cm² and four deleted packages, not ~18 cm².
- **Crossing delay.** A net between packages costs a `tPD` — 15 ns at the `-15` grade,
  against a 39.7 ns dot period. **The partition has to keep the dot-rate paths inside
  one part**: the phase counter, `SLOTTICK`, `FCLK0..3` and `MUXSEL` belong together
  with whatever they clock. The 2026-09-07 refit spends that freedom: `vaddr` is at 119
  of 128 logic cells and `vctrl` at 100, so the choice is no longer free.
- **Two JTAG chains**, or one chained through both.

**The partition, refitted 2026-09-07** — `hardware/gal/cpld/`, regenerated by
`hardware/gal/prjbureau/fit1508.sh`. This is the second fit. The first held only what
§7 and §5.2 describe; this one carries §6.4's tiling and character generation as well,
which is the whole of the v1 display list bar §19 item 23's decode.

| | Package | Holds | Logic cells | I/O pins |
|---|---|---|---|---|
| **`vaddr`** | PLCC-84 | scan and `WPTR` counters, scroll and tile registers, the write-strobe decode, the six-source address mux | **101 of 128** | 62 of 64 |
| **`vctrl`** | **PLCC-84** | sync trio, sequencer, span control, `CTRL`, §6.4's fetch cadence, §19 item 23's decode | **91 of 128** | **50 of 64** |
| **`arb`** | **`GAL22V10`** | **the spare-access arbiter — eight grants, `SPNGRANT`, `/WAIT`** | 10 of 10 | 9 of 12 in |

⚠ **`vctrl` outgrew the PLCC-84 when item 23 closed, and the fix was to take the
arbiter back out — §10.1.6.3.** The three-line table above is the whole card's
programmable logic.

`DOTCLK` lands on a global clock and `RESET` on the global clear, both parts, with two
of four dedicated inputs used. 74,136 fuses each.

**Count logic cells, not equations.** `vaddr` is 91 equations and **119 logic cells**:
the fitter cascades any equation wider than five product terms across extra cells, and
the address mux is five sources on seventeen bits. Every macrocell estimate in this
document before this fit was made by counting equations, and every one of them was low.

#### 10.1.6.1 Two things the fit paid for

**`CTRL` was crossing the boundary twice.** The merge exported `CTRL0..7` as eight pins
and took `HPOL`, `M0`, `IRQEN`, `WM0`, `WM1`, `TILEMODE` and `CHARMODE` back in as seven
more — fifteen pins to hold a byte that never leaves the part. §12 gives reads their own
register, `VSTAT`, so `CTRL` is write-only and belongs entirely inside `vctrl`. That one
correction is larger than the whole of §6.4's cadence, and it is what made room for it.

Two bit-map consequences, both using space §12 had already reserved:

- **b2 is now `CHAR`.** §12 spends three bits on `VMODE` and defines four codes, so b2
  was dead. With b5 it gives §6.4 both modes for nothing.
- **b5 is now `CELL`** — cell fetch on. It was marked reserved.
- **`HPOL` is not a register bit and never was.** §12's four codes are 70 Hz at
  `VMODE0 = 0` and 60 Hz at `VMODE0 = 1`, and the 70 Hz pair is the positive-H pair, so
  `HPOL = !VMODE0`. It had a pin, and a pin for a NOT gate is a pin wasted.

**Two selects were the same signal under two names.** `WRITESEL` arrived at both parts
as an input from nowhere; it is `SPNGRANT`, since the write pointer owns the address bus
exactly when the arbiter has given the span writer a chip. `LISTSEL` is `LGRANT` for the
same reason. Both are now identities, not pins.

#### 10.1.6.2 The list engine does not fit, and macrocells are not why

§10.3's engine was fitted, both packages, and it is the one thing here that failed:

| | Logic | Pins | Result |
|---|---|---|---|
| `vaddr` + list engine, PLCC-84 | 90% | 95% | fitter aborts — `INTERNAL ERROR` |
| `vaddr` + list engine, TQFP-100 | 90% | 63 of 80 | **does not fit** |

The TQFP-100 result is the informative one. It has 80 I/O against the PLCC-84's 64, so
pins stop being the constraint — and it still fails at 90% logic. **What runs out is
fan-in.** An ATF1508AS logic block is 16 macrocells behind a switch matrix that admits
40 of roughly 200 global signals, and a nineteen-bit pointer feeding a six-source
seventeen-bit mux does not fit through a 40-signal window however many macrocells sit
behind it.

The engine has to be on the part with the address mux — its pointer *is* an address
source, so anywhere else is nineteen crossing nets — which leaves three ways forward,
none of them free:

1. **A third ATF1508AS.** Honest, and it makes the card 3 CPLDs.
2. **Let the engine share `WPTR`.** The span writer and the list engine never drive the
   address in the same slot, so the engine could fetch into `WPTR` instead of carrying
   its own 19-bit pointer. That is 19 registers and most of the fan-in, but it changes
   §10.3's semantics — the engine would clobber the CPU's write pointer — and that is a
   specification decision, not a fitting one.
3. **Leave it out of v1**, which is what §12 already assumes: `LIST`, `BCTRL` and
   `BSTAT` are marked reserved.

**v1 as specified fits in two parts.** The engine is the line, and it falls just past it.

##### ⭐ Option 2 measured, 2026-09-08 — and it nearly works

The three ways forward above were reasoned, not fitted. Option 2 was, and it is much
better than "changes the semantics":

| | I/O | Logic cells | Nodes+FB | Result |
|---|---|---|---|---|
| `vaddr` as built, no engine | 62 / 64 | 104 / 128 | — | ✓ |
| **+ engine with its own `LIST` pointer** | | | | **`INTERNAL ERROR`** |
| **+ engine sharing `WPTR`**, PLCC-84 | **64 / 64** | 113 / 128 | **153 / 128** | ✗ — by nodes |
| + engine sharing `WPTR`, TQFP-100 | 65 / 80 | 113 / 128 | 153 / 128 | **✓** |
| ⭐ **+ engine sharing `WPTR`, Variant B dropped**, PLCC-84 | **64 / 64** | **105 / 128** | **135 / 128** | **✓** |

**Dropping the engine's own nineteen-bit pointer is the whole unlock.** It removes 19
registers, 19 mux inputs and the mux's *sixth* product term per address bit, and it
turns a design the fitter cannot even place into one that misses a PLCC-84 by nodes
rather than by fan-in.

⭐ **And then there is a version that fits the package we have.** Give up **§6.4.3's
Variant B** — the 1bpp character generator — and the shared-pointer engine lands at
**64 of 64 I/O and 105 of 128 cells**.

> **What that trade actually is.** Variant B is the *hardware* text mode: 3 accesses
> per 8 dots, 256 freely-defined attributes each choosing any RGB565 pair, and ~160,000
> accesses per frame handed back. Without it, **text still works** — §7's span writer is
> the text engine in bitmap mode, and §6.4.2's Variant A still gives 8bpp graphics
> tiles. What goes is the cheap 80-column text mode and its attribute colour path.
>
> ⚠ **Neither option leaves `vaddr` any JTAG**: both are 64 of 64. And this is a fit,
> not a design — the engine's semantics under a shared `WPTR` (it clobbers the CPU's
> write pointer, so software reloads after any list activity) are still §10.3's to
> settle. **What is settled is that the package is no longer the reason not to.**

> ✅ **Item 23 is closed and it took both of those repairs.** The write strobes are
> decoded on `vaddr` from a five-bit register address and one strobe, in place of nine
> strobe pins. And the window question was a mistake in this section rather than a real
> gap: §13's window is **32 bytes**, `$FF60`–`$FF7F`, and §6.4.6 had already reserved
> `+$17`–`+$19` for `TILEBASE`, `FONTBASE` and the map base. There was nothing to
> settle.
>
> ⚠ **Three errors in the 2026-09-07 fit, found while closing item 23**, all in logic
> this section had already reported as fitted: the scroll holds loaded `HSCROLL[7:0]`
> where §8 wants `HSCROLL[9:2]`, four bits off; the intra-cell byte address came from a
> slot-counter bit, which addresses in units of sixteen pixels rather than four; and
> the map had **no address source at all**, so `MAPLD` latched a byte from an address
> nothing generated. Fitting proves a design lands on a part. It does not prove the
> design is right, and this section read as though it did.

#### 10.1.6.3 ⚠ The arbiter came back out, and the card stays on PLCC-84

**2026-09-08.** Two machine-level decisions put two more inputs on `vctrl` — `A6` on
`REGSEL` (`machine.md` §5 item 1 A widened the geographic window to `$FF00`–`$FF7F`,
so `A6` left the strobe and every card decodes seven bits) and `/A20` on `VRAMSEL`
(§5 item 1 D made the physical map 2 MB). A third followed: `& E` on `WAIT.oe`, from
§5 item 8.

**76 I/O against a PLCC-84's 64.** The committed fit had been run against a
`P1508T100` — a TQFP-100 — while the `.pld` declared `f1508ispplcc84` and
`hardware/gal/regfile.ts` said *"vctrl fits at 62 of 64"*. **The design and its fit
had disagreed about the package and nothing checked it.**

**The arbiter is the cheapest ten pins on the part to give back.** Eight grants,
`SPNGRANT` and `/WAIT` are exactly ten macrocells against a `GAL22V10`'s ten; its
seven inputs are backplane signals or already-exported ones; and `access.jedec.ts`
never stopped carrying it as a standalone design with `access.check.ts` still checking
it. **It was a GAL before the two-CPLD rebalance and it is one again.** `WRITESEL`
**is** `SPNGRANT`, so it stops being a `vctrl` output and becomes a `vctrl` input.

| | I/O | Logic cells |
|---|---|---|
| as committed, TQFP-100 | 76 / 80 | 123 / 128 |
| + `A6`, `/A20`, `& E`, still TQFP-100 | 78 / 80 | 123 / 128 |
| **on a PLCC-84** | **76 needed, 64 available — does not fit** | |
| **arbiter out to a `GAL22V10`** | **64 / 64** ✓ | **112 / 128** |

⚠ **64 of 64 is zero spare, and JTAG costs four I/O — so `vctrl` has none.** It is
programmed out of circuit, which is what the audio card's `ATF1508AS` already does and
what this section's opening paragraph assumed.

##### ⭐ The six pins were taken — `rfa`, `gal/regfile.jedec.ts`, 2026-09-08

The paragraph above proposed `RA0`–`RA4` and `WSTB` onto a second `GAL22V10` "if
in-circuit programming is wanted back". §7.4's broadcast-write proposal wanted signalling
pins for a different reason, and one GAL answers both, so it was built: **U-V9 `rfa`**,
the register-file address.

**It re-derives rather than imports.** `REGSEL` is `IOSEL & A6 & A5` — three signals it
already needs — so it is recomputed locally instead of being carried across from `vctrl`,
and `RDLEN`/`RDFG`/`RDBG` come from `!SPANBUSY & FP1:FP0`. The trade is **six pins out and
two back** (`FP0`, `FP1`); `SPANBUSY` and `E` were already on the backplane side.

| | I/O | Logic cells |
|---|---|---|
| arbiter out, before this | 64 / 64 — **zero spare** | 112 / 128 |
| **`RA0`–`RA4` + `WSTB` out to `rfa`** | **50 / 64** — 14 spare | **91 / 128** |

⭐ **Fourteen pins, not the five the estimate promised.** Removing the five `RA` outputs
also removed every input that existed *only* to feed them — `A0`–`A4`, `IOSEL`, `A5`,
`A6` — nine inputs that went out with them. **JTAG's four fit with ten to spare**, and
§7.4 has room to signal a partial grant back to the span writer.

`rfa` is 6 macrocells of 10 (largest equation 10 terms of 16, `RA2`), checked against
CUPL over all 8,192 input combinations by `gal/jedec/cupl.check.ts`.
`hardware/gal/video.cpld.ts` and `hardware/gal/regfile.ts` carry the argument.


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
decode terms.

> ⚠ **The original budget was a sum, and a sum hides the ordering.** It read
> ~~`decode 15 + slot alignment <=158.9 + access 72 + latch/drive 20 = ~266 ns`
> against `~297 ns`, OK~~ — a total-versus-total comparison with an inequality inside
> it, which is exactly the shape that cannot distinguish a path that closes from one
> that does not. Re-derived **by phase** below, the read closes at ÷12 with 46.9 ns
> to spare **only under §5.2.2's spare-first sub-slot ordering**; under the video-first
> ordering that §2.2's "video → CPU" priority reads as, it misses by 25.1 ns. The
> sum also omitted the **15 ns the map SRAM adds** to physical A13–A19 (§6.3.1),
> because "decode 15" was charged from `t_AD` as if the address on the backplane were
> the address the CPU emitted. It is not; it is the translation of it.

**The budget, by phase.** Everything on this card is phase-locked to the dot clock
(§5.2), so the slot alignment is not a worst case to be bounded — it is a **constant
to be computed**. Take `t = 0` at the start of the bus cycle; E falls at 476.7 ns; the
fetch-slot boundaries inside the cycle are at 0, 158.9, 317.8 and 476.7 ns (÷12 is
integral in slots, §5.1).

| Phase | Duration | Ends at | Source |
|---|---|---|---|
| CPU address valid (`t_AD`, self-specified) | 160.0 ns | **160.0** | §5.3 |
| Map SRAM → physical A13–A19 | 15.0 ns | **175.0** | §6.3.1 |
| Card decode, incl. the `/IOPAGE` qualification | 15.0 ns | **190.0** | §6.3.2 |
| Align to the next fetch-slot boundary | 127.8 ns | **317.8** | slot grid |
| **Granted access — spare-first, front half of the slot** | 72.0 ns | **389.8** | §2.1, §5.2.2 |
| Read latch clock-to-Q + `'245` drive onto `D0–D7` | 20.0 ns | **409.8** | §14 |
| **Deadline: `t_DSR` = 20 ns before E-fall at 476.7 ns** | | **456.7** | HD6309E p.3 |
| | | **margin +46.9 ns** ✓ | |

And the same table with the display fetch taking the front half instead:

| Phase | Ends at |
|---|---|
| …decode complete, aligned | 317.8 |
| **display fetch** | 389.8 |
| **granted CPU access — back half of the slot** | 461.8 |
| latch + drive | **481.8** |
| Deadline | 456.7 |
| | **margin −25.1 ns** ✗ |

**So the read budget is an ordering decision, not a timing coincidence**, and
§5.2.2 makes the decision: spare access first, display fetch second. The fetch latch
wants the same ordering for its own reasons, so this costs nothing but a sentence —
which is precisely why the sentence has to exist.

**At ÷8 it does not close, and not by a little.** The cycle is 317.8 ns, the deadline
is 297.8 ns, and the slot boundaries inside the cycle are at 0 and 158.9 ns only. The
decode completes at the same absolute 190.0 ns, which is **past** the 158.9 ns
boundary, so the next available slot is 317.8 ns — the start of the *following* bus
cycle:

```
required for the 158.9 ns slot :  t_AD + 15 (map) + 15 (decode) <= 158.9
                               =>  t_AD <= 128.9 ns  =  21.9 core cycles @ 170 MHz
available                      :  plan.md 4.1's worst microcode step is 25 cycles
                               =>  no
```

> ⚠ **Compatibility line, per `docs/machine.md` §5: this card is specified at ÷12
> (E = 2.0979 MHz) and only at ÷12.** The ÷8 rate — **fast-E mode**, 3.1469 MHz — is
> **experimental and not guaranteed**, and flat VRAM read-back is one of the three
> independent things in the machine that break at it (the others are the 6551, which
> is 57 % over rating, and the real HD63C09E's 333 ns `t_cyc` minimum against a
> 317.8 ns cycle, which means the drop-in silicon A/B reference cannot even be
> captured there). Everything else on this card — writes, span writing, display
> fetch, palette, registers — closes at both divisors; it is read-back alone that
> does not.

Two answers to fast-E read-back, both already in the design and both **optional**,
because the rate they serve is not a specified rate:

1. **`/WAIT`** (§3.3) — the motherboard's divider holds E low for one further whole
   E period on VRAM reads in fast-E mode. Transparent to the emulator, transparent to
   a real 6309E, and the extra period restores the ÷12 arithmetic exactly. Note that
   this makes the *effective* fast-E VRAM read no faster than ÷12, which is most of
   the argument for not chasing ÷8 at all.
2. Or read through a `VDATA` port at `WPTR` with prefetch (the read for address
   *n* is issued when `WPTR` is set, so the CPU's read returns an already-latched
   byte). Streaming reads then run at full rate with no stall at either clock.

Provide both: flat readable VRAM for random access at ÷12, `VDATA` for streaming.

---

## 12. The missing piece: interrupts

**Neither colormin document has an interrupt source.** backplane.md §2 reserves
`/IRQ` on the bus and nothing drives it. The 64x4 does not need one; **NitrOS-9
does** — it needs a periodic tick, and you want raster splits (plan.md's own
accuracy bar for the CoCo 3 is "the raster split, not the boot").

Two of them, and they belong in different places.

### 12.1 VBL interrupt — on the card

`VSTAT.VBL` plus an enable bit in `CTRL`, driving `/IRQ` open-drain. ~~One macrocell
in the sync GAL pair~~ — **three, and §19 item 8 has the reason**: the OE idiom below
ties the macrocell's data to a constant, so the pending flag is a second macrocell,
and it has to be set by an edge rather than a level or it re-arms under its own
handler, which is a third. This is the system tick: 70.09 Hz in the
primary mode, **59.94 Hz** (not 60.0 — §6.2) in the 640×240 mode — and note that a NitrOS-9 tick derived
from vertical blank is *inherently* tear-free for double-buffer flips.

**Two things "zero packages" glossed over.**

*First, `VSTAT`'s live bits have no path to the data bus.* `VSTAT` (`+$13`, §13) is
the one register that is **not** a register-file location: `SPANBUSY`, `VBLANK` and
`HBLANK` are the instantaneous state of the sequencer and sync GALs, so the `'245`
that reads the register file back (§3.2) has nothing to read. Something has to drive
those bits onto `D0–D7` for the duration of a `$FF73` read, and nothing in §14 did.
Two ways:

| Option | Cost | Verdict |
|---|---|---|
| **`74HC244`** driven by the GAL macrocells, `/OE` = `VSTAT read` | **+1 IC** | **Specified.** Keeps the GAL outputs as plain totem-pole macrocells and puts the bus turnaround in a part designed for it. |
| Product-term output enables on the sync/sequencer macrocells themselves | 0 ICs | Rejected — see the note below, and those macrocells are the scarcest resource on the card (§19 item 8). |

*Second, the open-drain idiom costs a product term.* **A GAL22V10's outputs are
totem-pole**; there is no open-drain option. The standard trick is to tie the
macrocell's data to a constant 0 and put the *condition* on the output enable, so the
pin either drives low or floats — a genuine open-drain equivalent, and it is how
`/IRQ` (here) and `/WAIT` (§3.3) are produced. But a 22V10 macrocell has exactly
**one OE product term**, so this idiom spends it: the pin can no longer be
conditionally three-stated for any other reason, and the OE term must contain the
whole assertion condition (`VBL_pending · IRQ_enable` for `/IRQ`;
`SPANBUSY · VRAMSEL · /IOPAGE` for `/WAIT`). Both fit in one term as written. It is
stated here because it is invisible in a macrocell count and it is the reason the
`'244` above is a package rather than four more OE terms.

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
- Cost: **two GPIO pins and a timer** — see below. Both available, once §6.3.1
  moves the MMU off the CPU and gives the four A16–A19 pins back.

**Counting HSYNC gives you a line *count*, not a line *number*.** ⚠ This section was
written as "feed HSYNC to a spare pin", and one signal is not enough: a counter of
HSYNC pulses has no origin. Something must tell the CPU where the frame starts, or
line 37 is 37 lines after whenever the timer happened to be started.

| Approach | Cost | Error |
|---|---|---|
| Reset the HSYNC counter in the VBL handler | 0 pins | ⚠ **jitters by the whole IRQ dispatch latency** — a NitrOS-9 shared-`/IRQ` dispatch is 48–191 µs (`io/ps2/docs/ps2.md` §5), and a line is 31.78 µs, so the frame origin walks by **1–6 lines**, per frame, depending on what else interrupted. A raster split that moves is worse than no raster split. |
| **Feed VSYNC to a second GPIO and reset the counter in hardware** | **+1 pin** | **0 lines.** TIM's external-trigger/reset input does it with no ISR at all: HSYNC clocks the counter, VSYNC resets it, and the emulator reads an absolute line number at any instruction boundary. |

**Specify the second pin.** Both HSYNC and VSYNC must therefore be on the backplane
(§17 carries them from this revision), and the card must present them at TTL levels
to a slot pin as well as to the VGA connector — a `'244` channel, and §14's
clock/load fan-out `'244` has channels free. The pin budget in §6.3.1 counted one
HSYNC input against 5 spares on the external-MMU column; it is two now, and 4 spare.

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
| `+$00` | `CTRL` | b1..0 `VMODE` | 00 640×200/70, 01 640×240/60, 10 640×400/70, 11 640×480/60 | **new** (was `BANK`) |
| | | b2 `CHAR` | with `CELL`: 0 tile (8×8 colour), 1 character (1bpp glyph) | **new**, §10.1.6.1 |
| | | b4..3 `WMODE` | 00 direct, 01 span-mask, 10 span-solid | moved |
| | | b5 `CELL` | 1 = §6.4 cell fetch, 0 = linear | **new**, was reserved |
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
| `+$13` | `VSTAT` | b7 `SPANBUSY`, b6 `VBLANK`, b5 `HBLANK`, b0 IRQ pending | **read** through the `'244` of §12.1, not the register file; write clears IRQ | extended |
| `+$14` | `WADV` | b1..0 | pointer advance: 00 continue, **01 next row same column** (§7.2), 10 vertical (advance by stride) | **new** |
| `+$15` | `VDATA` | b7..0 | **read or write** VRAM byte at `WPTR`, post-increment | **new** (§11) |
| ~~`+$16`~~ | ~~`BORDER`~~ | | ⚠ **Deleted — §9.3.** VGA timing has no overscan, the porches must be black for the back-porch clamp, and the `'153` pixel mux has no spare input through which a border index could be injected. The byte is handed back to the reserved block. | ~~**new**~~ |
| `+$16`–`$1F` | — | | reserved — **10 bytes**, one of them handed back by §9.3 (`TILEBASE`/`FONTBASE` and map base, §6.4; `WPTR` column shadow, §7.2, is written implicitly) | |

**`BANK` is gone** (§6.3). **`MODE` is gone** — there is no stock mode to select;
`VMODE` was three bits with four codes defined; the 2026-09-07 CPLD fit took the spare
one for `CHAR`, so it is now two. Sync polarity is **not** a register bit — it follows
`VMODE0`, since §12's 70 Hz codes are exactly the positive-H ones (§10.1.6.1).

⚠ **`TILEBASE` and `FONTBASE` have no offsets and the sixteen-byte window is full.**
§6.4's fetch needs both, `vaddr` holds both, and `+$0B`–`+$0F` are reserved for the list
engine — which §10.1.6.2 now shows does not fit in v1. Reassigning two of those five is
the obvious move and it has not been made.

`VMODE` chooses among native modes only. Reset forces `CTRL = 0`: display
disabled, direct writes, no IRQ — so the machine comes up quiet and software
enables the display after loading a palette.

Register-file reset semantics carry over unchanged from minimal256.md §4.3: the
reset-critical bits live in the one `'273`, everything else is undefined until
written, and boot code writes the whole map once.

### 13.1 Palette writes and the LUT address bus — a software rule, stated

**`PIDX`/`PDATL`/`PDATH` writes during active display will snow, and the card has no
mechanism to prevent it.** The reason is structural, not a bug: the LUT's address bus
is **shared by tri-state turnaround** between two masters (§9, §14):

| Master | Drives LUT `A7..A0` | When |
|---|---|---|
| pixel-index `74AHCT574` | the pixel byte fetched from VRAM | every dot — one per 39.72 ns |
| `74HC593` `PIDX` counter | the CPU's palette index | whenever the CPU writes `PDATH` |

There is no third state and no arbitration: a `PDATH` commit must take the bus, and
it takes it from the pixel path, inside a 39.72 ns dot in which the chain
`index latch → 15 ns LUT → output register` already spends 28 ns (§6.1). The dot in
which the write lands emits whatever the LUT put out during the turnaround — one or
two wrong pixels, i.e. **snow**, exactly as a period card with a shared palette bus
produces.

Three responses, and the card takes the first:

1. **Specified rule: write the palette during blanking.** `VSTAT` already exposes
   `VBLANK` (b6) and `HBLANK` (b5) precisely so software can gate on them, and §2.1
   shows blanking is 40 slots per line plus 49 whole lines per frame — room for
   **all 256 entries** in one vertical blank at 2 writes per entry (512 writes ×
   ~2.4 µs = 1.2 ms against a 1.56 ms vertical blank at 70.09 Hz, so it fits, but
   only just; a fade should update half the palette per frame). The VBL handler
   (§12.1) is where a palette update belongs anyway, because that is the tear-free
   instant for the *picture* as well as for the LUT. **Zero packages.**
2. Accept the glitch. Legitimate for effects that are already per-scanline: a
   gradient written from the raster-compare handler during hblank is response 1 at a
   finer grain; one written mid-line is this.
3. Post the write into a holding register and retire it at the next hblank — a
   `'574` plus a busy bit and sequencer terms, on the pair §19 item 8 already calls
   the tightest fit on the card. **Not taken**: it buys a case response 1 covers for
   free.

`docs/video-comparison.md` §2's unqualified "mid-frame palette writes: yes" is
corrected to carry this rule. It is still a *yes* — the GIME snows in exactly the same
way and for exactly the same reason — but it is a yes with a rule attached.

---

## 14. Chip budget

> ⚠ **This table has been re-tallied, and it moved.** The previous version summed to
> **36** (32 without the `'153` mux) while §0's headline said "~33 (37 with the mux)"
> — two numbers that could not both be right and neither of which matched the table.
> Beyond the addition, the list was missing four things the card genuinely needs and
> carrying one thing that belongs elsewhere:
>
> | Change | Δ | Why |
> |---|---|---|
> | Posted-write **address + control** latches | **+3** `74HC574` | §3.1.1 — flat-mapped VRAM means the CPU supplies a 19-bit physical address that must be captured at E-fall |
> | Spare-access **arbiter** | **+1** `GAL22V10` | §5.2.1 — "the other three chips" is a live compare, not a wire |
> | `VSTAT` live-bit **driver** | **+1** `74HC244` | §12.1 — `SPANBUSY`/`VBLANK`/`HBLANK` are GAL state, not register-file contents, and had no path to `D0–D7` |
> | **Master oscillator** | **−1** | §5.1 — it is on the motherboard. A card that supplies E is a card whose removal stops the CPU, and §18 brings the bus up before the card exists |
> | Post-LUT registers `'574` → `'273` | 0 | §9.2 — blank-to-black needs an asynchronous clear, not an output enable |
> | VGA **drive stage** | 0 ICs, 4 discretes | §9.1 — the ladders cannot face a 75 Ω double-terminated line on their own |
> | `BORDER` deleted | 0 | §9.3 |
>
> Net **+4 packages**, and none of it is a change of design.

| Qty | Part | Role | vs colormin |
|---|---|---|---|
| ~~4~~ **2** | ~~AS6C1008-55 (128K×8)~~ **AS6C8016-55 (512K×16)** | framebuffer, ~~512 KB~~ **2 MB**, 4-way interleave as **2 parts × 2 bytes** — §14.2 | **−2** |
| 4 | 74AHCT574 | fetch read latches — clocked **per-chip, mid-slot** (§5.2.2) | = |
| **4** | **74AHCT153** | **4:1 pixel mux — assumed, not fallback (§6.1)** | +4 |
| 1 | 74AHCT574 | palette index latch | = |
| ~~2~~ **1** | ~~32K×8 **15 ns**~~ **IS61C6416AL-12 (64K×16)** | palette LUT, 256 × 16 b — **one ×16 part holds both bytes** (§14.2) | **−1** |
| **2** | **74AHCT273** | **post-LUT output register — `/MR` is blank-to-black (§9.2)** | = (was `'574`) |
| 1 | 74HC593 | `PIDX` counter (sourcing flag, §9) | = |
| **3** | GAL22V10-15 | **`hgen`/`vgen`/`vdec`** — H/V sync, blank, **mode-dependent sync polarity (§6.2.1)**, VBL IRQ. ⚠ **Fitted 2026-09-06 and it is three parts, not two** — §19 item 8 | **+1** |
| 2 | GAL22V10-15 | scan address generators, 19 b, loadable | = |
| 2 | GAL22V10-15 | `WPTR` / span pointer, 19 b | = |
| 2 | GAL22V10-15 | sequencer: decode (incl. the `/IOPAGE` term, §6.3.2), **static slot assignment**, span control, reg-file addressing, mux phasing | = |
| **1** | **GAL22V10-15** | **spare-access arbiter — 8 grants; `SRCSEL[n]` *is* `GRANT_CPU[n]` and is not a second macrocell, so 8 of 10 and not 12 (§5.2.1, §10.1.1)** | **+1** |
| 1 | 74HC574 | posted-write **data** latch | = |
| **3** | **74HC574** | **posted-write address + control latches — 19 address + VRAMSEL + R/W + `WMODE[1:0]` = 23 bits (§3.1.1)** | **+3** |
| 1 | 74HC165 | span mask serialiser (`74AHC165` if §6.4 Variant B is built) | = |
| 1 | 32K×8 20 ns | register file | = |
| 1 | 74HC273 | `CTRL`, master reset | = |
| 1 | 74HC245 | register + VRAM read-back | = |
| **1** | **74HC574** | **VRAM read latch (§11)** | **+1** |
| **1** | **74HC244** | **`VSTAT` live-bit driver (§12.1)** | **+1** |
| 2 | 74HC161 | `SPANLEN` down-counter | = |
| 1 | 74HC244 | clock / load fan-out, **plus HSYNC/VSYNC out to the backplane (§12.2)** | = |
| **41** | | ⚠ **the GAL build — superseded, see §14.1** | **colormin: 39 (35)** |
| — | 3 × NPN (β ≥ 300) + 1 × diode + 9 R | VGA drive stage, `V_be`-referenced (§9.1) | **new** |
| — | 3 × R-2R SIP, 1 kΩ/2 kΩ | 5/6/5 ladders (§9.1 sets the value) | = (value specified) |
| — | ~~1 × 25.175 MHz oscillator~~ | ⚠ **moved to the motherboard — §5.1** | **−1** |
| — | — | ~~stock 1bpp VRAM, `'166`, `'244` bypass, `'74` synchroniser~~ | **−4** |

**GAL count is ~~9~~ 10**, and that third step is measured rather than estimated: the
sync section was fitted on 2026-09-06 and needs three parts (§19 item 8). §10.1's
"the card is 8 GALs, the full blitter adds 10" table is re-based accordingly: Rev A
**10**, + list engine 12, + blit datapath ~22.

> **The scan-address pair was fitted the same day and needs no extra package** —
> 17 of 20 with three spare (§19 item 8), because it generates a *chip* address of 17
> bits and not a *byte* address of 19.

### 14.1 ⚠ The card is ~~31~~ 28 ICs, and three numbers in this document disagreed

**Reconciled 2026-09-08.** The table above is the **GAL build**, and §10.1.6 replaced it
on 2026-09-06 — *"Two PLCC-84 parts, and this is the build"* — without the arithmetic
being carried back here. The result was three counts live at once, all of them written
by this document:

| Where | Said | Status |
|---|---|---|
| §0 and the table above | **41 ICs, 10 GAL22V10** | the GAL build — **superseded** |
| §10.1.6 | 2 × `ATF1508AS`, no total given | the build, **uncounted** |
| §14's power table | *"`ATF1508AS`, one"* | **wrong in a third way** — the partition is two parts, not one |

**The count, derived from the table above:**

| | Δ | |
|---|---|---|
| GAL build | **41** | |
| − the ten `GAL22V10` | **−10** | sync ×3, scan ×2, `WPTR` ×2, sequencer ×2, arbiter ×1 |
| + 2 × `ATF1508AS-15JC84`, PLCC-84 | **+2** | `vaddr` and `vctrl` — §10.1.6 |
| − §10.1.6's absorptions | **−4** | `CTRL`'s `'273`, the `SPANLEN` `'161` pair, the `'165` span-mask serialiser |
| + 1 × `GAL22V10`, the arbiter | **+1** | §10.1.6.3 — it came back out on 2026-09-08 so `vctrl` stays a PLCC-84 |
| + 1 × `GAL22V10`, `rfa` | **+1** | §10.1.6.3 — the register-file address, out the same day, which bought JTAG back and §7.4 its signalling pins |
| **− 3 SRAM** | **−3** | **§14.2** — two ×16 parts feed the dot clock where four ×8 did, and one holds the whole 16-bit palette |
| **= the build** | **28** | **24 if the tri-state pixel bus closes and the four `'153` come out** |

**28 ICs: 2 CPLDs, 2 GALs, 4 SRAMs and 20 packages of 74-series.** Against
colormin's 39 (35), and against the 41 this document carried for two days after the
decision that replaced it.

> **The `VSTAT` `'244` (§12.1) survives the CPLD**, which is not obvious — an
> `ATF1508AS` has per-macrocell three-state with a product-term enable, so §12.1's
> reason for rejecting the OE idiom evaporates. **Pins are why it stays**: driving
> `D0`–`D7` from `vctrl` needs eight it does not have (§10.1.6.3). The same argument
> keeps the three posted-write address `'574`s: 23 bits of latch is 23 pins, and
> `vaddr` has two spare.

**Power does not move**, and that is worth stating because it is the number a supply
gets sized from. The programmable-logic row above assumed **one** `ATF1508AS` at
~190 mA; it is **two at ~100–120 mA each with reduced-power mode on the slow
macrocells, plus one `GAL22V10` at 70–90 mA** — call it **270–330 mA**, against the
ten GALs' 700–900 mA and against the single part's assumed 190. The card lands at
~~**~0.75–1.3 A, 0.9 A nominal, specify for 1.5 A**~~ — the same conclusion §14's power
paragraph already reaches, by different arithmetic.

⭐ **And then §14.2 took ~250 mA off it**, by consolidating seven SRAMs into four out of
a lower-power family. **~0.5–0.85 A, 0.65 A nominal, specify for 1 A.**

**Area moves less than §10.1.6 hoped.** Ten `GAL22V10` in DIP-24 are ~26 cm²; two
PLCC-84 sockets are ~22 and the arbiter GAL is ~2.6, so the win is **~1.4 cm²**, not
the ~4 that section predicts — because the arbiter came back out. The four deleted
packages are the real saving, and §14's *"~150 of 160 cm²"* becomes **102.5 cm²** once
§14.2's SRAM consolidation lands — measured by `hardware/place`, not estimated.
⚠ **If the tri-state pixel bus closes (§19 item 2) the four `'153` go too**, and the
card is **24 ICs**, which is where the slack comes back.

### 14.2 ⭐ The seven SRAMs become four, and the broadcast write falls out of it

**2026-09-08, after checking pricing and stock rather than guessing.** §14's table
carries **seven** SRAMs — four framebuffer, two palette LUT, one register file — and
two of those counts are not capacity. They are **width**.

| | Why that many | Capacity actually used |
|---|---|---|
| 4 × `AS6C1008` 128K×8 | **bandwidth.** A 55 ns part cannot feed a 39.7 ns dot clock; §2.1's 4-way interleave is the cliff that forces it | 128 KB of 512 KB at 640×200 |
| 2 × 32K×8 15 ns | **width.** The palette is 256 × **16** bits and both bytes are read every dot | **512 bytes of 64 KB** |
| 1 × 32K×8 20 ns | the register file | ~32 bytes of 32 KB |

**A ×16 part supplies both bytes in one access**, so two of them deliver the same four
bytes per 158.9 ns slot that four ×8 parts do — and one of them is a whole palette LUT.

#### 14.2.1 The parts exist, they are cheap, and they are stocked

The concern that made this worth checking first: **5 V wide async SRAM is mostly 1990s
cache silicon**, and the modern ×16 parts (`IS61WV`, `IS62WV`, `CY62`) are 3.3 V. Two
current parts answer it.

| | Part | Org | V | t<sub>AA</sub> | I<sub>CC</sub> | Package | Price | Stock |
|---|---|---|---|---|---|---|---|---|
| **framebuffer**, ×2 | `AS6C8016-55ZIN` | 512K×16 | **2.7–5.5** | 55 ns | **30 mA** typ, 6 µA standby | TSOP-44 II | ~$5.59 (1 k) – $8.83 (1) | **3,646 at DigiKey** |
| **palette LUT**, ×1 | `IS61C6416AL-12TLI` | 64K×16 | 4.5–5.5 | **12 ns** | **175 mW ≈ 35 mA** typ | TSOP-44 II | **$3.28** | **1,470 at Mouser** |

Both carry **`/LB` and `/UB` byte enables** alongside `/CE`, `/OE`, `/WE`, which is the
pin the whole scheme turns on.

⭐ **`AS6C8016` is Alliance's own part, the same vendor and the same `AS6C` low-power
family as the `AS6C1008` this table already specifies.** 2.7–5.5 V and 55 ns are the
numbers §2.1's 72 ns access budget was written against, unchanged.

> ⚠ **And the part being replaced is in worse shape than the replacement.** A 15 ns
> 5 V 32K×8 in DIP-28 is legacy: `AS7C256C-15PCN` is ~**$8.14** in ones at DigiKey and
> the `IS61C256AH-15N` / `CY7C199-15PC` alternatives are secondary-market. **Two of
> those at $8.14 become one at $3.28.** The consolidation is not only fewer packages —
> it moves the card's tightest timing path off the least available part on it.

| | today | consolidated |
|---|---|---|
| Framebuffer | 4 × `AS6C1008-55PCN`, ~$4.85–9.44 ea | **2 × `AS6C8016`**, ~$5.59–8.83 ea |
| Palette LUT | 2 × 32K×8 15 ns, ~$8.14 ea | **1 × `IS61C6416AL-12`**, $3.28 |
| Register file | 1 × 32K×8 20 ns | unchanged, and excluded from both totals |
| **SRAM packages** | **7** | **4** |
| **SRAM cost** | **~$36–54** | **~$14–21** |

> Prices and stock are single-distributor quotes taken **2026-09-08** and are the kind
> of number that moves. What is unlikely to move is the *shape*: a currently-stocked
> low-power ×16 part is cheaper than four ×8, and much cheaper than two legacy 15 ns
> DIP-28s. **Re-check before ordering, not before deciding.**

#### 14.2.2 The address generation does not change at all

This is the part that makes it cheap rather than a redesign. §19 item 3 fixes the point:
*"A 128K×8 has seventeen address pins and seventeen is what has to be generated."*

```
19-bit byte pointer (WPTR, or the scan address)

  A0        -> /LB, /UB       byte within the word     (was: part of the chip select)
  A1        -> chip select    which of the two parts   (was: part of the chip select)
  A18..A2   -> A16..A0        the SAME seventeen bits
```

**`A1:A0` are still not address bits** and the scan and `WPTR` generators still emit
seventeen. The `AS6C8016` has nineteen address pins and two get tied off, so each part
gives up **768 KB of its 1 MB** — precisely what §6.4.1 already tolerates on the LUT,
and precisely the **2 MB upgrade path** the moment the pointers widen to 21 bits.

#### 14.2.3 ⭐ What it does to §7.4

**§7.4's broadcast write stops being a proposal and becomes the default.** That section
ends on an unsolved arbitration: *"during a `/WAIT` stall the CPU is holding one chip,
so only three are free"*, and the span writer would have to count how many it got.

**With two parts there is one spare access per slot and one grant to give.** Four byte
enables on that access retire four bytes. Nothing to count, no partial grant, no
feedback path — the wide term is the whole design.

| | 4 × ×8 | **2 × ×16** |
|---|---|---|
| Display fetch | 4 accesses/slot | **1** |
| Spare accesses | 4/slot, ~32.4 M/s | 1/slot, ~8.1 M/s |
| Headroom over the CPU's ~420 K writes/s | 77× | **15×** |
| **Span-solid retire** | 6.29 MB/s | **25.1 MB/s** |
| Full-screen clear | 20.3 ms | **5.1 ms** |
| `SPANBUSY` worst case (§7.4) | 40.7 µs | **10.2 µs** |
| Arbiter | 8 grants, `GAL22V10` at 10 of 10 | **2 grants** |

⚠ **The bandwidth headroom really does fall 77× → 15×**, and that is the honest cost:
the CPU and the span writer can no longer proceed in the same slot on different chips,
so one of them waits **158.9 ns**. Against 2.38 µs per CPU write that is not a figure
anybody will measure. §3.1.1's posted-write backstop and §7.4's `R/W`-qualified `/WAIT`
already cover the case.

**The arbiter falling from 8 grants to 2 probably takes a package with it** — 2 grants
plus `SPNGRANT` and `/WAIT` is four macrocells, and §10.1.6.3's `vctrl` now has 14 spare
pins to host them. **That is not counted below**, because it needs a fit, not an
estimate.

#### 14.2.4 What it costs

| | |
|---|---|
| ⚠ **Surface mount** | TSOP-44 II. **The machine's first SMD** — the `ATF1508AS` are socketed PLCC-84 and everything else is DIP. This is an assembly decision, not an electrical one |
| ⚠ **§5.2 is rewritten** | the 8-grant arbiter, §5.2.2's per-chip fetch latch clocking, and the `SRCSEL = GRANT_CPU` identity all assume four chips |
| ⭐ **The card gets shorter** | 137.7 cm² of courtyard becomes **102.5**, and `hardware/place` puts it on an **18 cm** board instead of 24 — the same length as the audio card. Three DIP-32/28 out, three TSOP-44 in |
| Dead capacity | **1.5 MB of the framebuffer's 2 MB** (768 KB per part — two address pins tied off), and 63.5 KB of the LUT's 64 |
| The four `'153` and four `'574` | **unchanged** — still 32 bits latched and still a 4:1 mux at dot rate |

#### 14.2.5 ⭐ And it takes ~250 mA off the nominal

| Group | today | consolidated |
|---|---|---|
| Framebuffer | 4 × 40–70 mA = **160–280 mA** | 2 × 30 mA = **~60 mA** |
| Palette LUT | 2 × 70–110 mA = **140–220 mA** | 1 × ~35 mA = **~35 mA** |
| Register file | 10–30 mA | unchanged |
| **SRAM total** | **310–530 mA** | **~105–125 mA** |

**205–405 mA saved, ~250 at the nominal**, which takes the card from ~0.9 A to
**~0.65 A** and moves §14's regulator argument again: a 7805 dropping 7 V at 0.65 A is
**4.6 W**, and the switching pre-regulator stops being arguable and becomes
unnecessary.

> **Why this is a bigger saving than the package count suggests:** the `AS6C8016` is a
> *low-power* part at 30 mA typ where the `AS6C1008` is 40–70 mA, and the LUT swap
> trades two 15 ns cache-grade parts for one. **Half the saving is the family, not the
> consolidation.**

---

**Off-card, on the motherboard**, and this is where the parts that used to be on this
list went:

| Qty | Part | Role |
|---|---|---|
| 1 | 25.175 MHz oscillator | **system master** (§5.1) — feeds the E/Q divider *and* the backplane |
| 1 | GAL22V10 | ÷12 / ÷8 E and Q generation, with the **divisor-dependent Q tap** (§5.1) and the whole-E-period `/WAIT` (§3.3) |
| 5 | §6.3.1's MMU | SRAM, `'574`, GAL, `'245` isolation, `'157` address mux |
| **7** | | the whole of the machine's non-card logic |

**Power — restated, because the old figure was smaller than one line of its own
arithmetic.** This document claimed **450–650 mA** while simultaneously pricing a
GAL22V10 at "~70–90 mA each" (§10.1); nine of them is 630–810 mA before a single SRAM
is powered. The honest total:

| Group | Count | Each | Total |
|---|---|---|---|
| ~~GAL22V10-15~~ **ATF1508AS**, one, at 25.175 MHz | ~~10~~ **1** | ~~70–90 mA~~ | ~~700–900 mA~~ **~190 mA** |
| ~~AS6C1008-55~~ **AS6C8016-55** framebuffer | ~~4~~ **2** | ~~40–70 mA~~ **30 mA typ** | ~~160–280 mA~~ **~60 mA** — §14.2 |
| ~~32K×8 15 ns~~ **IS61C6416AL-12** LUT (dot rate) | ~~2~~ **1** | ~~70–110 mA~~ **~35 mA typ** | ~~140–220 mA~~ **~35 mA** — §14.2 |
| 32K×8 20 ns register file (bus rate) | 1 | 10–30 mA | 10–30 mA |
| AHCT at 25.175 MHz (fetch latches, `'153`, index, post-LUT) | 11 | 9–22 mA | 100–240 mA |
| HC at bus rate (posted-write ×4, `'165`, `'273`, `'245`, read latch, `'244` ×2, `'161` ×2) | 12 | 2–6 mA | 25–70 mA |
| Analog drive stage (§9.1) | 3 ch | 9.3 mA peak + bias | 30–45 mA |
| | | ~~**Total**~~ | ~~**~1.2–1.8 A**~~ |
| | | ~~**Total, §10.1.3**~~ | ~~**~0.7–1.1 A**~~ |
| | | **Total, §14.2** | **~0.5–0.85 A** |

~~Call it **1.6 A nominal** and specify for 2 A.~~ ~~Call it 0.9 A nominal and
specify for 1.5 A~~ — 2026-09-06, once the ten GALs became one `ATF1508AS`
(§10.1.3). ⭐ **Call it 0.65 A nominal and specify for 1 A** — 2026-09-08, once
§14.2's four SRAMs replaced seven. The measured figures are from `reference/datasheets/ATF1508AS.pdf`:

| | |
|---|---|
| `ICC1` standby, standard mode, commercial | **160 mA** typ |
| `ICC3` reduced-power mode | **65 mA** typ |
| supply current vs. frequency, p. 16, at 25.175 MHz | **~190 mA** standard, **~100 mA** reduced |

> ⚠ That graph's y-axis is labelled `ICC (µA)` and is plainly **mA** — the same page's
> standby row is 160 mA and the curve starts near 170. A datasheet typo, recorded
> because the figure is load-bearing here.

**Reduced power is a per-macrocell option**, and most of this design is slow: the line
counter advances at 31.5 kHz and the span writer at bus rate. Only the dot-phase and
slot counters, `FCLK` and `MUXSEL` need full speed. **~100–120 mA is the realistic
figure**, not 190.

**Two consequences, and only one of them moves.** §14's older text said a linear 7805
dropping 7 V at 1.5 A dissipates 10.5 W and needs a heatsink that does not fit the
Eurocard envelope. At **0.9 A that is 6.3 W** — still not comfortable bare, but a
7805 with a modest heatsink, or a lower input rail, is now arguable where it was not,
and the switching pre-regulator stops being forced. **The slot power pins do not
move**: 0.9 A still exceeds a single 0.5 A-class pin, so §17's multiple parallel power
and ground pins stand.

> ⭐ **At §14.2's 0.65 A the 7805 is 4.6 W**, which a TO-220 on a small clip-on
> heatsink carries comfortably. The switching pre-regulator stops being arguable and
> becomes unnecessary. **The slot pins still do not move** — 0.65 A is still over a
> 0.5 A pin, so §17 stands unchanged and for the same reason. Two consequences that the 450–650 mA figure hid:
a linear 7805 dropping 7 V at 1.5 A dissipates 10.5 W and needs a heatsink that does
not fit the Eurocard envelope, so the card wants a **switching pre-regulator or a 5 V
backplane rail**; and at 1.5 A a single 0.5 A-class slot power pin is not enough —
**the connector needs multiple parallel power and ground pins**, which is a backplane
decision (§17), not a card one. §10.1's low-power GAL family question is now worth
real money: nine ATF22V10C-class parts instead of nine bipolar GALs is most of half an
amp. Measuring card current stays §19 item 10, but it is now a *verification*, not a
discovery.

**Area.** ⚠ **The paragraph below is the GAL build's. The current figure is
`hardware/place`'s, measured rather than estimated: 28 ICs of courtyard is
**102.5 cm²**, and the card fits an **18 cm** Apple-II board rather than the 24 cm it
needed at 31 — §14.2 took three DIP-32/28 SRAMs off it and put back three TSOP-44.** ~~41 ICs including 4 × DIP-32 and 3 × DIP-28~~, against
colormin's ~140 cm² on a 160 cm² Eurocard. Four more packages plus a guarded analog corner by the VGA connector
puts this at **~150 of 160 cm²** — still a 4-layer Eurocard with disciplined placement
and the blitter still a piggyback, but the slack that made that conclusion comfortable
is gone. If the tri-state pixel bus closes at 39.7 ns (§19 item 2) the four `'153`
come back out and so does the slack; that bench item is now an *area* item as well as
a BOM item.

## 15. Period audit

| Element | Introduced | Verdict |
|---|---|---|
| VGA, 25.175 MHz, 640×400@70 | **1987** (IBM PS/2) | period-exact; the *standard* clock, not an approximation |
| HD63C09E | 1988 | the machine's premise |
| GAL22V10 | 1986 | period; PAL16L8 is 1978 |
| 74AHCT | ~1990 | **the newest family on the card.** 74F is the period-honest substitute on the dot path |
| ~~AS6C1008 (128K×8)~~ **AS6C8016 (512K×16)** | ~~1 Mbit~~ **8 Mbit** SRAMs ~~~1989–90~~ **~1995** | ⚠ **§14.2 gives up the 1989 plausibility**, and knowingly: an 8 Mbit ×16 part in TSOP is mid-90s silicon. The 1989 build is the four `AS6C1008`, and it still works — this is a packaging choice, not a capability one |
| 20 ns / 15 ns 32K×8 SRAM | ~1988 | period |
| R-2R SIP ladder DAC | forever | period |
| MMU as an SRAM block map | 1980 (SWTPc DAT), 1986 (GIME) | period — **but see below** |

**On the DAT row.** The SWTPc DAT is the correct precedent, and it is worth being
precise about *what* it used, because the precision is what §6.3.1 costs two extra
packages. The DAT is built from **74LS189-class 16×4 register files**, which have
**separate data-in and data-out pins**. That is why the period design needs no
isolation buffer: the CPU writes on one port while the address bus reads the other,
continuously, with no turnaround at all. Substituting a commodity 2K×8 SRAM with
**common I/O** — cheaper, faster, stocked, and the right modern choice — moves that
separation from inside the part to outside it, where it costs a `'245` and a
break-before-make discipline. The `'157` address mux is the second package and it is
not a period artefact at all: the DAT's index came from the address bus on both
paths. **The 1980 part was better shaped for the job than the 1990 one**, which is a
pleasing and slightly humbling result, and it is why the honest count is five.

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
   you can improve later without touching hardware. ⚠ **Qualified:** that is true of
   the *emulated* CPU and is exactly why ÷8 remains buildable, but it is also the
   half of item 8 that trades against the other half — a rate no rated HD63C09E can
   run at is a rate with no silicon reference. ÷12 is the specified rate (§5.1).
5. ~~**The MMU costs nothing** (§6.3) and can be made GIME-register-compatible,
   which is worth real weeks of NitrOS-9 porting.~~ **Both halves spent — §6.3.1.**
   The MMU went outside to keep one 48-pin SKU across both machines, so it costs
   **5 ICs** (~~3~~ — the three-IC list could not be wired; §6.3.1), and GIME register
   compatibility was priced at an hour of NitrOS-9 patching rather than weeks. This is
   the one item on this list the machine chose not to take.
6. **Raster interrupts cost one pin** (§12.2), and are more flexible than the
   hardware they replace.
7. **`TFM` exists** (§10.2).
8. ~~**A real HD63C09E remains a valid part for the socket.** Keeping `arm6309`
   clock-slaved (§5.3) means you can drop real silicon in to bisect a bug —
   emulator or machine? — which is the same A/B lever the CoCo 3 project depends on.~~

   > ⚠ **This property no longer holds as the machine is specified**, and it is worth
   > being blunt about it because it was one of the load-bearing arguments for the
   > whole clock-slaved design (§5.3).
   >
   > `docs/machine.md` §5 item 0 resolves the machine's boot problem (§6.3.3) by
   > having the **CPU module serve the vector page and an 8 KB shadow ROM from its own
   > STM32 flash, without a bus cycle**. A real HD63C09E dropped into that socket
   > fetches `$FFFE`–`$FFFF` from the backplane, where — as §6.3.3 sets out — nothing
   > answers. The silicon A/B reference does not boot.
   >
   > It holds again **only if the recorded alternative is taken**: an 8 KB EPROM plus
   > decode on the motherboard, with an explicit vector/ROM carve-out from the I/O
   > page (2 ICs, no CPU divergence). That is a live option and it is exactly the sort
   > of thing this list exists to price, so it is recorded rather than mourned.
   >
   > A second, smaller qualification, unrelated to boot: at **÷8** the 317.8 ns bus
   > cycle is below the HD63C09E's **333 ns `t_cyc` minimum**, so the A/B reference
   > cannot be captured in fast-E mode with a rated part even with a ROM present
   > (§11). At the specified ÷12 rate, 476.7 ns, it is comfortable.
   >
   > What survives untouched is everything the property was *used* for at ÷12 with a
   > motherboard ROM: clock-slaving (§5.3), the Q-lead specification (§5.1) and the
   > `/WAIT` discipline (§3.3) are all still written so that real silicon works. The
   > obstacle is one decode, not the timing.

---

## 17. Backplane and the sound card

Brief, because it is not the video question — but the backplane spec has to be
frozen before the video card is laid out, and the sound card is the other consumer.

> **The sound card now has its own document: [`audio.md`](../../audio/docs/audio.md)** — a
> 4-channel PCM card modelled on the Amiga's Paula, 36 ICs, whose acceptance test
> is playing existing OCS tracker modules unmodified, with the loader and
> replayer that do that in [`modplayer.md`](../../audio/docs/modplayer.md). **It supersedes this
> section's Ensoniq 5503 DOC assumption**; the bullets below are updated to what
> that design actually asks of the backplane.

- **Adopt backplane.md's slot model**, retargeted: ~~geographic `/IOSEL` per slot~~
  **`/IOSEL` as a window strobe common to every slot,**

  > ⚠ **The geography does not survive the retarget, and this bullet is where it was
  > lost.** colormin gives four slots one 64-byte window each and decodes them by
  > position; this machine's windows are function-sized and all different (16/32/4/4/4),
  > which no position decode can produce. `audio.md` §9.1 and `ps2.md` §3.2 both copied
  > "per slot" from here and both then promised a base-address jumper, which a position
  > decode leaves nothing for. Corrected in [`machine.md`](../../docs/machine.md) §2,
  > which is the owning document; `serial.md` §6 had it right all along.

  `/WAIT` open-drain (a **wait state** — E held low for whole E periods, §3.3),
  `/IRQ` **and** `/FIRQ` open-drain (backplane.md reserves only `/IRQ`; NitrOS-9 uses
  both, and audio wants one of its own), `/NMI`, `/RESET`.
- **The geographic decode spans `$FF40`–`$FF7F`, not just `$FF60`–`$FF7F`.**

  > ⚠ **Stale as written, and corrected below.** ~~Video takes `$FF60`–`$FF7F` (§13);
  > [`audio.md`](../../audio/docs/audio.md) §9.1 proposes `$FF40`–`$FF4F`, leaving
  > `$FF50`–`$FF5F` for a disk controller.~~ That sentence was true when this document
  > was the only card specification in the repository. **Three cards now live in
  > `$FF50`–`$FF5F`**, and the disk-controller reservation was handed back:
  >
  > | Range | Size | Owner |
  > |---|---|---|
  > | `$FF40`–`$FF4F` | 16 B | audio — `audio/docs/audio.md` §9.1 |
  > | `$FF50`–`$FF53` | 4 B | PS/2 keyboard + mouse — `io/ps2/docs/ps2.md` §3.2 |
  > | `$FF54`–`$FF57` | 4 B | RS-232 serial — `io/serial/docs/serial.md` §7.1 |
  > | `$FF58`–`$FF5B` | 4 B | SD card storage — `storage/docs/sdcard.md` §6.1 |
  > | `$FF5C`–`$FF5F` | 4 B | **free** — the machine's only unallocated I/O |
  > | `$FF60`–`$FF7F` | 32 B | video — §13 |
  >
  > `docs/machine.md` §3 is the owning table; this one is a copy and defers to it.
  > **The window is full to within four bytes**, which is a stronger argument for
  > widening it than the one originally given. Widen it now — it is a decode term
  > today and a board respin later.
- **`/FIRQ` belongs to audio, and to audio alone.** [`audio.md`](../../audio/docs/audio.md) §8.1
  takes it as the sole source, so there is no polling chain: video's VBL and
  raster compare stay on `/IRQ` (§12), and a replayer tick gets the cheap
  6809 interrupt it should have. Record the ownership in the backplane spec
  rather than leaving it to first-come.
- **Carry E, Q, `R/W` and the 25.175 MHz master** rather than `16M`/`8M`/`/MRD`/`/MWR`.
  Cards derive their own strobes; the master lets any card phase-lock to video. The
  master **originates on the motherboard** (§5.1), not on this card.
- **Carry physical A0–A18 plus A19**, not just logical A0–A15 — the video card
  needs them (§6.3), and so will any future memory card. The sound card does not:
  its whole bus footprint is a 16-byte I/O window and `/FIRQ`.
- **Carry `/IOPAGE`.** ⚠ **New, and mandatory — §6.3.2.** Motherboard-generated,
  active-low, asserted for the whole of any logical `$FF00`–`$FFFF` cycle. Every
  physical-memory decode in the machine — system RAM and this card's VRAM select —
  must qualify against it, and the map SRAM's own `/OE` is gated by it so physical
  A13–A19 are parked rather than stale during an I/O cycle. Without it, a task with
  any MMU block pointed at VRAM double-drives `D0–D7` on every I/O read and posts a
  spurious VRAM write on every I/O write. It costs a pin and a buffer, because it is
  the term the motherboard already forms to generate `/IOSEL` — but it costs a
  **respin** if the backplane is etched without it.
- **Carry `HSYNC` and `VSYNC`, TTL, from the video card to the CPU slot.** ⚠ **New —
  §12.2.** The raster-compare timer lives in the STM32 and clocks from HSYNC; without
  VSYNC as a hardware frame reset the line counter has **no origin**, and
  resynchronising it in the VBL handler jitters the frame origin by the whole
  `/IRQ` dispatch latency — 48–191 µs against a 31.78 µs line, i.e. **1–6 lines**,
  varying per frame with whatever else interrupted. Two pins, one `'244` channel
  each, on a `'244` the card already carries.
- **Power pins: size the connector for the load, not for the pin count.** §14's
  honest card current is ~1.1–1.7 A for video alone, and `docs/machine.md` has to sum
  the machine. A single power and a single ground pin per slot is not enough; specify
  **multiple parallel 5 V and ground pins** and put the ground returns adjacent to the
  clock and sync lines. This is a backplane decision that a per-card "measure at
  bring-up" cannot make.
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
**The signal list, consolidated** (`docs/machine.md` §2 is the owning table):

| Signal | Direction | Note |
|---|---|---|
| physical `A0`–`A18`, `A19` | motherboard → cards | translated; §6.3 |
| `D0`–`D7` | bidirectional | 5 V TTL |
| `E`, `Q`, `R/W` | motherboard → cards | Q leads E by 90°, which is 3 dots at ÷12 and **2 at ÷8** (§5.1) |
| 25.175 MHz master | motherboard → cards | lets any card phase-lock to video |
| `/IOSEL` | motherboard → **all** slots | ⚠ ~~geographic, per slot~~ — **the ~~`$FF40`~~ `$FF00`–`$FF7F` window strobe, common to every slot**; the card decodes ~~`A0`–`A5`~~ **`A0`–`A6`** against a jumpered base. Widened 2026-09-08 — [`machine.md`](../../docs/machine.md) §2, §5 item 1 A. `hardware/gal/vctrl.pld`'s `REGSEL` is `IOSEL & A6 & A5` and has been refitted |
| `A20` | motherboard → **all** slots | **new 2026-09-08** — physical `A20`, `machine.md` §5 item 1 D. **This card's `VRAMSEL` gained `/A20`**: the ring is `A20 = 0, A19 = 1`, the second quarter of a 2 MB map rather than the top half of a 1 MB one |
| **`/IOPAGE`** | motherboard → cards | **new** — §6.3.2, mandatory |
| `/WAIT` | cards → motherboard | open-drain; whole E periods only (§3.3) |
| `/IRQ`, `/FIRQ`, `/NMI` | cards → CPU | open-drain; `/FIRQ` is audio's alone |
| `/RESET`, `/HALT` | motherboard → cards | |
| **`HSYNC`, `VSYNC`** | video card → CPU slot | **new** — §12.2, TTL |
| audio L, audio R + 2 grounds | audio card → connector | stereo, and it is load-bearing |
| 5 V, ground | | **multiple parallel pins** — §14's power arithmetic |

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
| 0 | **Freeze the machine spec** — bus signals **including `/IOPAGE`, HSYNC and VSYNC** (§17), the full `$FF40`–`$FF7F` map (§17's table — six owners, not two), `/FIRQ` ownership, the MMU register set, the E/Q divider **and its divisor-dependent Q tap**, and the machine's boot arrangement (§6.3.3) | one document; §19's items 1–4 answered |
| 1 | **Bench the dot path on a breadboard**: 4-way fetch → pixel mux → index latch → LUT → ladders → **§9.1's buffer stage** at 25.175 MHz, driven by counters, no CPU | stable 640×400@70 colour bars on the target monitor, **locked in both `VMODE` families** (§6.2.1's sync polarity is what the monitor identifies them by); black measured at 0 V through the porches (§9.2); DNL measured across all 64 green codes at the **connector**, into a 75 Ω load |
| 2 | **Sync + scan address GALs**; fit the sequencer pair **first** (minimal256.md §11 item 11) | equations fit with the raster-compare and static-slot terms in place. ⚠ **Sync and scan address done 2026-09-06** — sync is three parts, not two; the scan pair is 17 of 20 and not 20 of 20. Both checked at the fuse level (`hardware/gal/`). Sequencer pair, `WPTR` pair and arbiter outstanding |
| 3 | **Card rev A**, driven by the STM32 bus exerciser (§16.1) — no 6309 core needed | registers read back; palette loads; framebuffer scans; `VSCROLL`/`HSCROLL` smooth in both axes |
| 4 | **Span writer + `SPANBUSY`/`/WAIT`** | full-screen clear in ~5 ms; 80×25 glyph render at 13 writes/cell; no lost writes under a hammering loop |
| 5 | **VRAM read-back** (§11) at ÷12 — the specified rate. Fast-E mode (÷8) is experimental and read-back does **not** close there without `/WAIT` | read-modify-write pixel round-trips clean at ÷12; the `/WAIT` path demonstrated at ÷8 or fast-E abandoned |
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
4. ~~**Decide the MMU's location**~~ **Closed — §6.3.1: on the motherboard,
   ~~3~~ 5 ICs.** The deciding argument was one 48-pin SKU across the CoCo 3 drop-in
   and this machine, not the address path, and it survives the corrected count
   unchanged. What it leaves open is the register set itself (`machine.md` §5 item 3),
   which is now a free design with no GIME to copy, and which is what the write-decode
   GAL needs before it can be fitted — **including the break-before-make sequencing of
   §6.3.1's map-write table**, which is that GAL's hardest equation.
5. **Confirm E/Q phase stability across the ÷12 ↔ ÷8 switch** (§5.2), and gate the
   change to vertical blank.
6. **Confirm the static slot assignment is actually static** — that the CPU's
   access phase is fixed for *both* divisors, and that a `/WAIT`-extended cycle
   re-enters the correct phase afterwards (§3.3 specifies whole E periods for exactly
   this reason; item 21 is the motherboard half of it). This is the load-bearing assumption
   behind deleting the `'74` synchroniser, and it is the most likely place §5 is
   wrong.
7. **Verify VRAM read timing on the bench** (§11), not just on paper — the
   266 ns estimate has ~30 ns of margin at ÷12 and none at ÷8.
8. **GAL fit — and it is worse than "heavier".** The card is now **9** GALs (§14),
   and two of the four original pairs are at or past their macrocell limit before any
   of §6.4 is asked for. A GAL22V10 has **10 macrocells**, so a pair has 20, and every
   output — registered or combinational — is one. The arithmetic, written out because
   this is the item most likely to fail:

   **Scan-address pair — ~~20 of 20, zero margin~~ CLOSED 2026-09-06: it is 17 of 20,
   and §8 said so all along.** Fitted in
   [`hardware/gal/scan.jedec.ts`](../../hardware/gal/scan.jedec.ts), checked against
   the torus by `npm run check:scan`.

   | Function | Was | Is |
   |---|---|---|
   | 19-bit loadable scan address, `A18..A0` | 19 | — |
   | 9-bit row counter, `A18..A10` | | 9 |
   | 8-bit column counter, `A9..A2` | | 8 |
   | inter-package carry / terminal count | 1 | **0** |
   | | **20 of 20** ✗ | **17 of 20, three spare** ✓ |

   Two things were counted that are not there, and **§8 of this document already
   describes the hardware correctly** — *"a separate **9-bit** V-address counter
   supplies row bits `A18..A10`"*, *"`HSCROLL[9:2]` preloads the H-address counter"*,
   *"`HSCROLL[1:0]` preloads the **output phase**"*.

   **`A1` and `A0` are not address bits.** The framebuffer is four `128K × 8` parts in
   4-way interleave (§2.1), so a chip's address *is* the scan address shifted down two
   and the bottom two bits are *which chip* — the mux phase, which never leaves the
   `'153`s. A `128K × 8` has **seventeen** address pins and seventeen is what has to be
   generated. `check:scan` asserts that identity directly.

   **There is no inter-package carry.** The torus is 1024 × 512 with a stride of
   exactly 1024 and a ring of exactly 512 rows (§8), so the column counter's rollover
   at `A9` *is* the wrap to column 0 of the same row and the row counter's at `A18`
   *is* the wrap to row 0 of the ring. Both are free binary rollovers of their own
   width and neither ever carries into the other. `check:scan` runs the column counter
   over 256 times and asserts the row does not move. The carry macrocell was the cost
   of a 19-bit flat counter that this design does not build.

   **So §19 item 15's premise is gone.** Its answer to "are there spare macrocells?"
   was "zero"; it is **three**, and both parts have spare input pins as well
   (`hadr` uses 11 of 13, `vadr` 12 of 12).

   **Sync — ~~24 wanted, 20 available~~ CLOSED 2026-09-06: it is 27, and it takes
   three parts.** Fitted in [`hardware/gal/sync.jedec.ts`](../../hardware/gal/sync.jedec.ts),
   checked at the fuse level over whole frames in both families by
   `npm run check:sync`. The count was three low:

   | Function | Macrocells | |
   |---|---|---|
   | V line counter, 0–524 | 10 | |
   | H counter at the fetch-slot rate, 0–199 | 8 | |
   | `HSYNC`, `VSYNC` (with §6.2.1's polarity XOR) | 2 | |
   | `BLANK` (drives the post-LUT `'273` `/MR`, §9.2) | 1 | |
   | `VBLANK`, `HBLANK` (to `VSTAT`, §12.1) | 2 | |
   | `/IRQ` for VBL (§12.1, OE-idiom) | 1 | |
   | **`VTC` — the line counter's mode-dependent modulus** | **1** | **not counted** |
   | **`VBLPEND` — the latched flag behind `/IRQ`** | **1** | **not counted** |
   | **`VSDLY` — one dot of delay, so the flag is an edge** | **1** | **not counted** |
   | **needed** | **27 of 30** | three GAL22V10s |

   The three that were missing are all consequences of things this document already
   says. `VTC` is a *decode of the line counter*, and the line counter fills its own
   part, so the modulus cannot live where the counter lives. `/IRQ`'s OE idiom
   (§12.1) ties the macrocell's **data** to a constant, which means the pin carries no
   state and the pending flag has to be a macrocell of its own. And `VBLPEND` has to
   be set by an **edge**, not by the level of the blanking window: a 6809 enters an
   interrupt in ~10 µs and the window is 63.5 µs, so a level re-arms the interrupt
   under its own handler. That is `VSDLY`.

   **The first escape does not work, and it was the cheapest-looking one.** Moving
   the 8-bit slot counter to a `'393` frees eight macrocells, but then one part has
   to decode *both* counters, and the pins are not there:

       h[7:0] + v[9:0] + VMODE0 + HPOL + IRQEN + VSTATWR   = 22 inputs
       a 22V10 carrying the six decode outputs             = 16 available

   Splitting the decodes to fix that costs two GALs *plus* the external counter,
   which is worse than the three GALs it was avoiding. **A counter has to stay on
   the same package as the things that decode it** — that is the rule this item was
   groping for when it said "macrocells and pins are" the constraint, and pins turn
   out to be the binding half.

   **So it is the third escape, and it is not a contingency: the card is ~~10 GALs and
   41 ICs~~ 2 `ATF1508AS` + 2 `GAL22V10` and 28 ICs (§14.1).** ⚠ **This item's
   macrocell table below is the GAL partition and §10.1.6's fit superseded it** — the
   sync trio is inside `vctrl` now, which is 91 of 128 cells and 50 of 64 pins. The
   item is kept because it is what proved the sync section needs three parts' worth of
   logic, which is why it did not fit two GALs:

   | Part | Holds | Macrocells | Pins |
   |---|---|---|---|
   | `hgen` | `H0..H7`, `HSYNC`, `HBLANK` | 10 of 10 | 3 of 11 inputs |
   | `vgen` | `V0..V9` | 10 of 10 | 8 of 11 inputs |
   | `vdec` | `VTC`, `VSYNC`, `VBLANK`, `BLANK`, `VSDLY`, `VBLPEND`, `/IRQ` | 7 of 10 | **14 of 14** |

   **`vgen` is the tightest fit in the machine.** A ten-bit counter behind a
   six-literal clock enable costs bit *i* exactly *i* + 7 product terms, so the bits
   need 7, 8, … 16 and a 22V10 offers 8, 10, 12, 14, 16, 16, 14, 12, 10, 8. Only the
   sorted pairing fits, which interleaves the bits across the package — even bits
   climb pins 14–18, odd bits descend 23–19 — and `V9` lands on **16 product terms in
   a 16-term macrocell**. Every other bit is at its limit or one below it. The
   six-literal enable is the slot counter's terminal count read back as five pins,
   and it is what keeps `hgen` at ten macrocells instead of eleven.

   **§6.2.1's arithmetic was wrong twice, in opposite directions, and the result
   still fits.** See that section.

   Product terms were never expected to be the constraint here and were not: the
   widest equation on the three parts is `V9` at 16, and the widest *decode* is
   `VBLANK` at 13 of 14.

   The sequencer pair, meanwhile, is why §5.2.1's arbiter became its own package
   rather than four more terms. **The sync section is fitted; the scan-address pair
   is not, and it is the one with 20 of 20 before tile mode asks for anything.** Fit
   it before committing the BOM, and see item 15 before committing to any GAL count.

   > **The scan pair was fitted the same day and came out the other way** — 17 of 20,
   > because the pair generates a chip address and not a byte address. The rule that
   > broke escape 1 still holds; it simply does not bind here, because nothing decodes
   > the scan address. It goes straight to the framebuffer's address pins.

   **A placement rule, now that three counters have been fitted.** A loadable counter
   bit *i* costs *i* + 3 product terms and a plain enabled one *i* + 7, so a wide
   counter's bits want a rising staircase while a 22V10 offers the palindrome
   8, 10, 12, 14, 16, 16, 14, 12, 10, 8. **Bit order is not pin order** for any counter
   past about six bits: the only assignment that fits pairs the two sorted sequences,
   which interleaves the bits across the package. `vgen`, `vadr` and the `WPTR` pair
   all land on it. The fitter refuses the naive order rather than letting it through —
   that is how `vadr`'s top bit was caught.
9. **`74HC593` availability** (§9). **carried.**
10. **Measure card current** with ~~seven SRAMs and nine GALs~~ **four SRAMs, two
    CPLDs and two GALs** against §14's ~~~1.1–1.7 A~~ **0.5–0.85 A** estimate, and
    price the low-power GAL family (§10.1) — nine ATF22V10C-class parts instead of
    nine bipolar GALs is most of half an amp. **carried, and no longer a discovery**:
    §14 and §14.2 do the arithmetic, so this is verification. ⚠ **And §14.2's three
    TSOP-44 parts are the ones to measure first** — their 30 mA and 175 mW typicals
    are *typical*, and the whole 205–405 mA saving rests on them. The regulator topology and the slot's power-pin count depend on the
    answer (§17).
11. **Validate 640×400@70 and 640×480@60 on the actual monitors** — CRT, LCD and
    scaler. 70 Hz 400-line is a DOS text mode and should be universal; confirm it.
    **carried, retimed.**
12. ~~**Decide span-wrap behaviour at the 1024-byte row boundary**~~ — **DECIDED
    2026-09-06: wrap in row.** Not chosen by taste; the fit chose it, and the rest of
    the card agrees.

    **The fit.** `WPTR` is nineteen bits with the same `{row, column}` structure as
    the scan address, because the stride is the same 1024. The column part
    ([`hardware/gal/access.jedec.ts`](../../hardware/gal/access.jedec.ts) `wcol`) is
    ten bits in **10 of 10 macrocells and 11 of 11 input pins** — full in both
    dimensions. Advancing into the next row needs a carry *out* of that part, and
    there is no eleventh macrocell to emit one from and no pin to carry it on.
    `check:access` asserts exactly that, so the constraint is recorded rather than
    remembered.

    **And wrapping is the right answer anyway, which is the part worth keeping.**
    `hadr`'s scan column counter wraps inside the row — `check:scan` runs it over the
    boundary 256 times and asserts the row does not move. If the writer advanced
    where the scanner wraps, the two would disagree about what follows column 1023 of
    a row, and every span that crossed the boundary would land somewhere the display
    would not read it from. **The torus is a torus in both directions or in neither.**

    §7.2's "next row, same column" is unaffected: it is `WADV = 01`, a row advance
    with the column reloaded from the register-file shadow, and it never relies on a
    carry.
13. **Emulator model** must charge spans their real ~40 ns/pixel, stall on a busy
    span, model `VSTAT`, the raster compare and the MMU — or software will be
    written against a machine that does not exist. **carried, extended.**
14. **NitrOS-9 driver scope.** How much of the CoCo 3 `GrfDrv`/`CoWin` stack can be
    retargeted to an 8bpp chunky bitmap with a span writer, versus rewritten? This
    is the largest unestimated piece of work in the whole project and it is
    software, not hardware.
15. **Tile-mode fit — ⚠ now a v1 item, not a §6.4 option.** §10.1.5 puts 80×25 text
    on Variant B's character mode (§6.4.5: 2 CPU writes per cell against 13), so this
    item is on the critical path rather than gating an enhancement. The macrocell and
    pin cost is priced — 89 I/O, 128 of 128 macrocells, `ATF1508AS` PQFP-160 — but
    **the logic itself has never been written**: the map-byte path, the
    linear-vs-concatenated address mux, and the three-access cadence (code, attribute,
    font row) are the three pieces, and none of them exists. **This is the largest
    unwritten block on the card.**

    Three questions, in order of risk: (a) are there **spare input pins** on the scan-address pair to take the
    map byte, or does it cost a `'574`; (b) can those GALs tri-state their low
    outputs during the tile fetch and switch between linear and concatenated
    addressing; (c) does the sequencer pair hold a second fetch cadence on top of
    what item 8 already lists. Product terms are not expected to be the constraint
    — pins and macrocell count are.

    > **(a) is answered and the premise of the pessimism is gone.** Item 8 said the
    > scan pair had **zero** macrocells spare; the fit says **three**, plus two spare
    > input pins on `hadr`. (b) and (c) are still open — tri-stating is free (every
    > macrocell has an output-enable term), but switching between linear and
    > concatenated addressing multiplies the terms on bits that are already at
    > *i* + 3, and the top bits have the least headroom. **Fit it before freezing the
    > BOM**, but it is no longer a near-certain extra package.
16. ~~**Decide the tile fetch's fine-scroll behaviour**~~ — **IMPLEMENTED, and it is
    free after all.** §6.4.6 says sub-cell scroll "needs a 3-bit offset applied to
    the tile-row address, which is new logic rather than the free `HSCROLL` of §8".
    It is not new logic. A slot is four pixels and a cell is eight, so the three bits
    of intra-cell offset are `{SA2, mux phase}` — the column counter's own low bit
    and the two bits §8 already preloads. §8 loads that counter from `HSCROLL[9:2]`
    and the phase from `HSCROLL[1:0]`, so **both halves are already scrolled** and
    the concatenation needs no adder and no offset register.

    What it does need is a **cadence** guarantee, not an address one: the map byte
    for a cell must be held before that cell's first pixel is emitted, so when a line
    starts mid-cell the map fetch leads by one cell rather than one slot. That is
    `MAPSEL` in [`video.parts.ts`](../../hardware/gal/video.parts.ts).
17. **Bench the serialiser in the LUT address path** if Variant B is built (§6.4.3).
    The glyph bit reaches a LUT address pin through a `74AHC165` clock-to-Q, inside
    the 11.7 ns margin item 3 is already measuring. `'HC` grade will not shift at
    25.175 MHz; confirm `'AHC` does, in circuit.
18. **Bench §9.1's drive stage into a real 75 Ω load** — DNL across all 64 green
    codes at the connector, black measured at 0.000 V, peak white at 0.700 V, and the
    `V_be` reference's drift over a 30-minute warm-up. This is the one part of the
    card that is analog, and it is the part with no prior art in either colormin
    document. Confirm also that the back-porch clamp on the *actual* monitors removes
    the residual black offset (§9.2), which is the argument the design rests on.
19. **Confirm §5.2.2's spare-first sub-slot ordering on the bench**, because §11's
    read budget is 46.9 ns of margin under it and −25.1 ns without it. Measure the
    CPU access's position within the fetch slot directly; do not infer it from a
    working read, because a marginal read works until it does not.
20. ~~**Fit §5.2.1's arbiter GAL**~~ **CLOSED 2026-09-06.** Fitted in
    [`hardware/gal/access.jedec.ts`](../../hardware/gal/access.jedec.ts) and checked
    over all 128 input combinations; two of the three cases are asserted by name.

    - **CPU and span on the same chip** — the span writer yields. ✓
    - **CPU absent entirely** — the span writer takes the chip rather than idling
      the slot. ✓
    - **Never both** — no chip is ever granted to two drivers in one slot, asserted
      separately from the model because it is the failure this part exists to
      prevent. ✓
    - The **`/WAIT` case** is not this part's: a span *holding* the chip the CPU
      wants is `SPANBUSY · VRAMSEL · /IOPAGE` on the `/WAIT` pin (§3.3, §12.1's
      open-drain idiom), and the arbiter is purely combinational grant logic with no
      state to be busy with. It stays open as **item 21**, where it belongs.

    **8 macrocells, not 12** — §14 budgeted "8 grants + 4 source selects" on a part
    with ten macrocells, which should have been an overflow nobody had noticed. It
    was never one: §5.2.1's own equations end `SRCSEL[n] = GRANT_CPU[n]`, the same
    signal. Two macrocells and seven input pins spare.
21. **Decide `/WAIT`'s granularity with the motherboard** (§3.3): whole E periods is
    what this card's static phase needs, and it is the motherboard's divider that has
    to implement it. Confirm that a `/WAIT`-extended cycle re-enters the correct
    sub-slot phase — this is item 6 with the answer now specified rather than open.
23. ~~**Write the phase-dependent `FCLK` equations, and the sequencer's other half.**~~
    **CLOSED 2026-09-07.** Both halves are written, fitted and checked.

    **(a) The four `FCLK` equations — 9 product terms, 4 macrocells, no new package.**
    §8 and §5.2.2 described one mechanism from opposite ends; they meet at the
    observation that the four latches can be clocked on either side of the moment
    the fetched data lands. The fetch owns the back half of the slot, so a clock
    rising at the PH 3→0 boundary takes this slot's group and one rising at PH 2→3
    keeps the previous one — and a chip clocked late therefore holds **exactly one
    group more** than a chip clocked early, which is all §8 needs. With
    `HSCROLL[1:0] = p`, chips `p..3` are emitted before the wrap and take the early
    clock; chips `0..p−1` are emitted after it and take the late one. `FCLK3`
    reduces to a single term, which is the arithmetic saying chip 3 is never after
    the wrap.

    `seqph.check.ts` now computes the emitted byte sequence for **every** `p` from
    the fitted fuses and asserts the line is contiguous — where before it could only
    assert Rev A's was not. Byte-granular horizontal scroll is a design.

    **(b) The register-file decode — 21 macrocells, 28 product terms.** Item 23's own
    budget was 13, and the extra 8 are deliberate: they are the per-register write
    strobes, which used to be **one pin each** into the address part. On a card made
    of GALs the item's `'138` was right; on a CPLD it is backwards, because
    macrocells are cheap and pins are the binding resource. Six address lines and one
    strobe replace nine strobe pins — the same trade §10.1.6.1 made for `CTRL`.

    Three things the item asked to be *stated*, now stated in
    [`hardware/gal/regfile.ts`](../../hardware/gal/regfile.ts):

    - **`REGSEL` is one address bit.** §13's window is `$FF60`–`$FF7F` and the
      motherboard's `/IOSEL` is `$FF40`–`$FF7F`, so the card's own decode is `A5`.
    - **`VRAMSEL` carries the `/IOPAGE` term** §6.3.2 requires. Without it the select
      matches every I/O access in the machine.
    - **The file address's internal side**, which the item called "the last thing on
      the card that has never been stated precisely". A span needs `SPANLEN`, `WFG`
      and `WBG` once each and none changes while it runs, so §7.4's "two deferrable
      file reads" become a two-bit walk at span end that fetches all three for the
      *next* span. Two macrocells and three decodes.

    **The cost is a package, and it is `vctrl`'s.** At 74 I/O the PLCC-84 refuses;
    the part is now an **`ATF1508AS` TQFP-100**, fitted at **76 of 80 pins and 123 of
    128 logic cells**. `vaddr` stays PLCC-84 at 62 of 64 and 101 of 128. §10.1.6
    carries the numbers.

22. **Verify the sync-polarity table against the actual monitors** (§6.2.1), CRT, LCD
    and scaler, in *both* `VMODE` families. Polarity is how the monitor picks the
    vertical format; getting it right on paper and wrong at the connector produces a
    correctly-timed picture that is the wrong size, which is the failure mode most
    likely to be misdiagnosed as a timing bug. Folds into item 11.

---

## 20. Sources

- `~/code/colormin/docs/minimal256.md` — the design this analyses (chunky
  framebuffer, interleave, span writer, scroll, palette LUT, register file).
- `~/code/colormin/docs/blitter.md` — list engine and blit datapath budgets,
  arbitration priority rule.
- `~/code/colormin/docs/backplane.md` — slot bus model, `/WAIT`/`/INH` semantics.

> ⚠ **Those three are home-directory paths into a sibling repository, and this
> document's load-bearing claims cite them** — "transfers unchanged from
> `minimal256.md` §11" and the arbitration priority rule are not checkable from a
> fresh clone of `arm6309`. A reader who is not the author cannot audit the
> derivation at all. **Snapshot the cited sections under `reference/`, or point at a
> public location** — `docs/design-review.md` §Sys-n1. Until then, treat every
> "unchanged from colormin" claim in this document as uncorroborated.
- `cpu/docs/plan.md` §2.1 (edge-driven requirement), §3.2 (pin budget), §3.3 (timing),
  §3.6 (read latch), §4.1/§4.3 (microcode step, `TFM`).
- `docs/coco3_c64.md` §5.1 (GIME MMU), §8.2–8.3 (scrolling, raster interrupts),
  §10 (what the GIME's restraint buys this project).
- `reference/datasheets/HD6309E_datasheet.pdf` p.3 — `t_ACC`, `t_DSR`, `t_DHW`, `t_AD`.
- VGA 640×400@70: 25.175 MHz, 800 × 449. VGA 640×480@60: 25.175 MHz, 800 × 525.
  **Both derived from the standard, not measured — confirm against the monitors
  in §19 item 11.**
