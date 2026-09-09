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

> Superseded material is archived in [history.md](history.md); this document
> describes only the present design.

**Constraints taken as given (yours):**
- RGB332 is the colour model you asked for; palette lookup is *nice, not required*.
- 80×25 text ⇒ **640×200 is preferred over 480×200**.
- Bitmap with smooth scrolling, and a blitter.
- **Programmable logic is two `ATF1508AS` in PLCC-84 plus one `GAL22V10`**
  (§10.1.6, §14.1). §10.1.2 shows CPLDs are period-honest here — the first EPLD
  (1984) and the first CPLD (1988) both predate parts this card already uses — and
  the root `README.md` retired the machine's no-CPLD rule on that argument. FPGAs
  are unproposed rather than banned.
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
| **Blitter + display-list engine** | **List engine built; blit datapath deferred.** The 6309's `TFM` plus the span writer cover most of the gap. The engine costs **no package**: it shares `WPTR` and took the macrocells §6.4.3's Variant B would have used. | §10, §10.1.6.2 |
| **Arbitration priority rule / preemption** | **Keep the rule, delete most of the mechanism.** Phase-locking makes CPU arbitration static **in time** — ⚠ but not in space: which chip the CPU hits is `address[1:0]`, so a small arbiter survives (inside `vctrl`, §5.2.1, §10.1.6.3). | §5, §5.2.1 |
| **MODE=0 bit-exact stock 1bpp path** | **Delete.** −4 ICs, −1 clock domain, −2 open items. Pure win. | §4 |
| **`$4000–$7FFF` broadcast window + RAM shadow write** | **Delete.** An artefact of MinOS compatibility. | §4 |
| **`BANK` register** | **Delete.** The machine has an MMU; that *is* the banking mechanism. | §6 |
| **VRAM write-only** | **Reverse — make it readable.** Now affordable, and worth a lot. | §11 |
| **Card-local asynchronous 20 MHz dot clock** | **Replace** with one system master clock; derive E and Q from it. | §5 |
| **480×200, 6×8 cells, 512 B stride** | **Replace** with 640×200, 8×8 cells, 1024 B stride. | §6 |
| **No interrupt source** | **Add VBL + raster-compare interrupts.** NitrOS-9 needs a tick; you want raster splits. | §12 |

**Net: 27 ICs (23 if the tri-state pixel bus closes at 39.7 ns and the
`'153` mux is not needed), against colormin's 39 (35)** — plus 3 buffer transistors and
3 R-2R SIP ladders, which are not ICs and are counted on their own line.

**The programmable logic is 2 × `ATF1508AS-15JC84` (PLCC-84) + 1 × `GAL22V10`** —
`vaddr`, `vctrl` (which carries the spare-access arbiter) and `rfa`, the
register-file address GAL.
Higher resolution, readable VRAM, raster interrupts, one clock domain; deleting the
stock-compatibility path still pays for most of the addition, and the honest bus
interface eats the rest.
Budget and the line-by-line arithmetic in §14; power in §14 as well:
**~0.5–0.85 A, 0.65 A nominal, specified for 1 A** (§14.2.5).

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
one fetch period, so it never waits.

> **"4-way" is the interleave, not the package count (§14.2).** The framebuffer is
> **two `AS6C8016` 512K×16** parts rather than four `AS6C1008` 128K×8, and two ×16
> accesses deliver the same four bytes in the same 158.9 ns slot. Every timing number
> in this section is unchanged, and so are the seventeen address bits (§19 item 3) —
> `A1` selects the part and `A0` drives `/LB` / `/UB` where both used to be chip
> select. **What does change is the spare-access budget** (four per slot becomes
> one, of up to four bytes) and that is the whole of §7.4's broadcast write.

> ⚠ **The margin has no escape hatch behind it.** The `AS6C8016` is a **55 ns part
> and Alliance list no faster grade**, so 86.9 ns of slack against a 72 ns access is
> the whole margin — there is no part-swap behind it, only a retreat to four
> `AS6C1008` 128K×8, whose −45 grade takes the access to 62 ns and the slack to
> 96.9 ns. That is why §14.2 is a packaging decision that can be reversed at layout
> and not one that closes a door.

Free accesses for the span writer and list engine, at 70 Hz — every access granted
on the **158.9 ns fetch-slot grid** (§5.2), at most two per slot
(2 × 72 = 144 ns ≤ 158.9 ns):

```
active display : 160 slots/line x 1 spare x 400 lines  =  64,000
hblank         : 6.36 us / 158.9 ns = 40.0 slots/line
                 40.0 x 2 spare x 400 lines            =  32,000
vblank         : 31.78 us / 158.9 ns = 200 slots/line
                 200 x 2 spare x 49 lines              =  19,600
                                                total  ~ 115,600/frame
```

During active display one of the slot's two accesses is the display fetch, so one is
spare; during hblank and vblank the display fetches nothing and both are spare.
≈ **8.1 M accesses/s**, each carrying up to four bytes across the two ×16 parts,
against a CPU that can issue ~420,000 writes/s. The card has **~15×** more spare
accesses than the CPU can consume — and each is up to four bytes wide (§14.2.3).
Bandwidth is not the constraint on this machine — **the CPU is** — which is the
single most important number for deciding what to build.

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
- **Programmable-logic policy.** The card's logic is 2 × `ATF1508AS` + 1 ×
  `GAL22V10` (§10.1.6), and §10.1.2 shows both families are period-honest for a
  1989–90 card.

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
| `/IOSEL` per slot | mainboard `'138` on the I/O page | colormin's windows are slot-sized and this machine's are function-sized, so `/IOSEL` is a **window strobe common to every slot**, not a geographic decode — [`machine.md`](../../docs/machine.md) §2 |
| `/WAIT` (clock gating) | **`/WAIT`: E held low for whole E periods** | §3.3 |
| `/INH` | not needed | the MMU decides what answers |

> **It is four capture registers, not colormin's one.** In colormin, VRAM is
> write-only through `WPTR` — the address always comes from the card's own counter,
> so a CPU write contributes nothing but a data byte. §6.3 makes this card's VRAM
> **flat-mapped**: a direct CPU write arrives carrying an arbitrary **19-bit
> physical address** that exists nowhere else on the card, and it has to be captured
> on the same edge as the data. One edge, four `'574`s. See §3.1.1.

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
divider holds E low for one or more further E periods. "Stretch" is reserved for
`docs/machine.md`'s ÷8 clock rate, which is a different thing entirely; the ÷8 rate
is **fast-E mode** (§5.1).

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

> ⚠ **The Q lead is a function of the divisor.** Q leads E by **90° of the E
> period**, and the E period is a different number of dots at each divisor:
>
> | Divisor | E period | 90° | Q lead |
> |---|---|---|---|
> | ÷12 | 12 dots, 476.7 ns | 3 dots | **3 dots, 119.2 ns** |
> | ÷8 | 8 dots, 317.8 ns | 2 dots | **2 dots, 79.4 ns** |
>
> A divider that emits a fixed 3-dot lead in both modes puts Q at 135° in fast-E
> mode — a 45° phase error, which a real HD63C09E in the socket samples against
> (`t_AVS`/`t_CSR` are referenced to Q, not to E). The divider's Q tap is therefore
> one more product term in the motherboard's divider GAL, and `docs/machine.md`
> says so.

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
- *Which* chip the CPU takes is dynamic, so which chips remain spare is a
  per-access computation, not a wire — §5.2.1.
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

Eight product terms of the form *(2-bit compare)·(request)* plus four inversions.
`SRCSEL[n]` **is** `GRANT_CPU[n]` — the same signal, not a second macrocell — so the
arbiter is **eight macrocells**, with six inputs. It lives inside `vctrl`
(§10.1.6.3); its standalone `GAL22V10` design is kept in
[`hardware/gal/access.jedec.ts`](../../hardware/gal/access.jedec.ts), because a
GAL22V10 fuse map is the form `access.check.ts` and the CUPL cross-check can
execute — the standalone design is the verification vehicle, not a leftover.

> ⚠ **§14.2's two-chip framebuffer makes this 2 grants instead of 8**, which is a
> §5.2 rewrite rather than a rebalance, and it is not done — §19 item 25. The
> equations here are the fitted four-chip form.

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

  > **Fetch-latch clocking is per-chip and mid-slot.** *Per-chip*, for three
  > reasons: §5.2.1 grants each chip's spare access independently, so the four
  > chips' bus turnarounds are not identical; §6.4's tile mode gives them different
  > fetch cadences, so a common slot-rate clock would have to be timed for the worst
  > chip in the worst mode; and — the strongest reason — **byte-granular horizontal
  > scroll requires it**: §8's note shows that with a common latch clock the display
  > cannot render a line at `HSCROLL[1:0] ≠ 0` at all. *Mid-slot*, because a clock
  > on the slot boundary has no settling margin and is the same edge that reloads
  > the address counters.

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

> ⚠ **59.94 Hz, not 60.0** —
> [`hardware/gal/sync.timing.ts`](../../hardware/gal/sync.timing.ts)'s arithmetic
> check: 25.175 MHz ÷ 800 ÷ 525 = 59.940 Hz, the standard VGA 640×480 rate. It
> matters in exactly one place — §12.1 makes vertical blank the NitrOS-9 system
> tick, so a tick divisor calibrated for one family runs 0.1 % wrong in the other,
> which is about **86 seconds a day**. The two families need different divisors.

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

**Cost in the sync logic: 10 product terms**, and three facts set the number. A
22V10's macrocells have unequal product-term allocations
(8, 10, 12, 14, 16, 16, 14, 12, 10, 8).

**Only `VMODE[0]` reaches the sync logic.** There are two vertical timings, not
four: `VMODE[1]` selects line-doubling, which is the scan-address generator's
business and not the raster's. So there is no window per `VMODE` value.

**XOR against a *variable* is not a doubling.** `A XOR B` doubles only when `A` and
`B` are both single literals. Here `A` is a window compare and `B` is `VMODE[0]`, so
the `/A·B` half is the **complement** of that compare — one product term per literal
in it. A nine-literal window compare becomes nine terms, not one.

**What makes it come out at 10 rather than far worse is where the counters start**,
which [`hardware/gal/sync.timing.ts`](../../hardware/gal/sync.timing.ts) fixes: both
counters are zeroed at the **leading edge of their own sync pulse** rather than at the
start of active video. Then `VSYNC_raw` is `v ≤ 1` — one product term, and *the same
term in both families*, because both timings open with a two-line pulse. A mid-raster
origin would have needed a mode-dependent window compare here, and it is the
complement of that compare that the polarity XOR then has to pay for.

10 terms sits on a 16-term macrocell with room, which is what this section required.
The same reasoning applies to `HSYNC` even though `HPOL` is strapped: it costs 6 of
the 10 terms on its macrocell, and carrying the input rather than strapping it in
silicon makes an out-of-spec monitor a re-burn instead of a cut trace. Fitted in the
standalone `hgen` and `vdec` designs — the sync logic's verification vehicles — and
carried inside `vctrl` (§10.1.6).

### 6.3 The 64 KB problem — and why the `BANK` register goes away

This is the one architectural question colormin never had to answer: the 64x4 has
a flat 64 KB space, so a windowed `BANK` register was the only option. **The 6309
machine has an MMU, because NitrOS-9 Level 2 requires one.** Once the MMU exists,
`BANK` is a second, worse banking mechanism sitting on top of it.

**The machine maps VRAM flat into the physical address space, behind the MMU.** The
MMU itself lives **on the motherboard** (§6.3.1), and it is not
GIME-register-compatible — both halves of the in-CPU alternative analysed below were
declined, for the single-SKU argument §6.3.1 records.

```
physical A19..A13  <-- MMU block map, 8 blocks x 8 KB, per task
physical A12..A0   <-- logical A12..A0, untranslated

A19 = 0  : 512 KB system RAM      } both qualified by /IOPAGE high
A19 = 1  : 512 KB VRAM            } (the video card's 1024 x 512 ring)

card VRAM select = A19 . /IOPAGE(high) . E . (no other card asserting)
```

The in-CPU version's case — kept because §6.3.1's decision was made against it, and
it is the analysis §6.3.1 prices:

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

1. **The external MMU is what lets one 48-pin SKU serve both targets (§6.3.1).**
   The in-CPU version needs a larger package: plan.md §3.2 closes LQFP48 at 35 of
   39 pins for the CoCo 3, and an in-CPU MMU adds A16–A19 plus an HSYNC input (§12)
   on top of that — it would force the homebrew module onto an LQFP64-class part
   (STM32G431RB / G474RE, same core, same 170 MHz). The *project* has a reason to
   want one SKU, and §6.3.1 is how it gets one.
2. **The video card now decodes physical A0–A18 plus a chip select**, not a 16 KB
   window. Any of the eight MMU blocks can be pointed at VRAM, so up to 64 KB of
   framebuffer is directly addressable at once — strictly better than a 16 KB
   window with a bank register, and it is what makes §11's readable VRAM useful.
3. **That chip select must be qualified against `/IOPAGE`.** ⚠ "Physical A0–A18
   plus a chip select", full stop, is an unsafe card. See §6.3.2.

`WPTR` stays. The auto-incrementing 19-bit pointer is the streaming path and the
span writer's address source; the MMU is the random-access path. Two paths on
purpose, exactly as colormin argues — just with the MMU doing the job `BANK` used
to do badly.

### 6.3.1 The MMU goes on the motherboard — 5 ICs, and one 48-pin SKU serves both machines

**Decided.** The in-CPU case above stands as *analysis* — an in-CPU MMU really is
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

> **Why five ICs and not three.** A three-IC version (SRAM + `'574` + GAL) cannot
> be wired, for two independent reasons that both come from the same place: a
> **common-I/O** SRAM has one set of pins doing two jobs, and a **translate-mode**
> address that is wrong during the very cycle that writes it.
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
>    map write must come from **A3..A0**. That is a 4-bit 2:1 mux, and it is a
>    package.
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
the part a three-IC list leaves unstated. Assume `E` high, `R/W` low, the decode
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

plan.md §3.2 carries the same arithmetic with the UART and LED counted as line items
rather than as spares; the two tables agree at 39 either way. The HSYNC row is two
pins, not one, because §12.2 shows a raster line *number* needs a frame origin as
well as a line clock. The in-CPU column has no spare at all, which sharpens rather
than changes the conclusion.

**Package, per `docs/machine.md` §5 item 6:** the part is the **STM32G431CBU6
(UFQFPN48)** — not the CBT6 (LQFP48), which bonds out only 38 GPIO and does not carry
`PC4`/`PC6`/`PC10`/`PC11`, where `BA`, `BS` and the debug UART live. Same die, same
48 pins, same firmware; the one-SKU argument is unaffected in every particular, so
read "LQFP48" as "48-pin part" throughout.

Nothing else in the machine asks the CPU module for a pin. Audio, PS/2, serial and
storage are all bus cards behind geographic `/IOSEL`, and their interrupts wire-OR onto
`/IRQ` and `/FIRQ`, which are in the count already ([`machine.md`](../../docs/machine.md)
§2, §4). §12.2's sync inputs are the only pins a card asks of the CPU module, and
they are in both columns.

**The timing argument reverses too, mildly.** The bullet above prices the in-CPU MMU at
~3–4 core cycles on the post-read path plus a second `STR` for A16–A19 — ~18–24 ns
inside `t_AD`. The external map spends 15 ns of SRAM propagation *after* `t_AD`, on the
motherboard, where §5.3's self-specified deadline has slack for it. So the external
version is a small win in absolute time and a real one on the CPU's most
deadline-critical instruction, not a cost at all.

**Two details that only exist in this version.** Both are carried in
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
  is an ordinary design task with a free hand — and it is the deliverable that
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
*something* onto physical A13–A19; ungated, it keeps emitting the current
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

The same override has a second consequence: with
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

  A18..A14   TILEBASE     (register)          TB4..TB0
  A13..A6    code[7:0]    <- the map byte just fetched   MAP7..MAP0
  A5..A3     row[2:0]     <- scan line within the cell   SA12..SA10
  A2..A0     col[2:0]     <- pixel within the row        SA2, and the mux phase

1bpp glyphs, 8 B each, 256 glyphs = 2 KB, aligned to 2 KB:

  A18..A11   FONTBASE
  A10..A3    code[7:0]
  A2..A0     row[2:0]
```

⚠ **The vertical fields are `vadr`'s row counter, not the sync line counter.**
Both count lines and only one of them is zero at the top of the display:
[`sync.timing.ts`](../../hardware/gal/sync.timing.ts) puts both counters' origin
at the leading edge of their own sync pulse, so active video begins at line 37 in
the 449-line family and line 35 in the 525-line one. `vadr` has neither problem —
`VLOAD` loads it from `VSCROLL` through vertical blanking and `ROWADV` steps it
once per *displayed* row (§8) — so `SA18..SA10` is zero-based at the top of the
window by construction, **and scrolled**. That is the whole reason `VSCROLL` works
in cell mode (§6.4.8).

The only new element in the datapath is **getting the map byte from the pixel bus
onto the VRAM address bus** — **zero packages**, absorbed into `vaddr` as registered
macrocells (§10.1.6). Each address bit is then a **four-source mux**: the bitmap
scan address, Variant A's tile concatenation, `WRITESEL & WA[n]` for the write
pointer (which the list engine shares — §10.3.1), and `MAPSEL` for the map fetch.
**Four sources, and one spare** against the five an ATF15xx macrocell holds before
cascading — and a fifth or sixth source per bit is exactly what §10.1.6.2's fits ran
out of, which is why the engine shares `WPTR` and Variant B is not built. Checked in
[`hardware/gal/tile.check.ts`](../../hardware/gal/tile.check.ts), which asserts the
no-adder property by showing OR equals ADD over all 524,288 field combinations in
each variant.

> **The map takes a 128-byte row stride so its fetch is a concatenation too.** An
> 80×25 map packed at 2,000 bytes would need `MAPBASE + cellRow × 80 + cellCol`, and
> **80 is not a power of two** — a multiply-accumulate, which is exactly the adder
> this section's argument says does not exist. With the 128-byte stride, `MAPBASE`
> sits in `A18..A12`, cell row in `A11..A7` (`SA17..SA13`), cell column in `A6..A0`
> (`SA9..SA3`) — concatenation again, and free. It costs **1,200 bytes** of the
> 512 KB nobody is using: 3,200 B rather than 2,000. `check:tile` asserts both
> halves, **and that the fitted mux computes the same address the model does** —
> it evaluates `addressMux()` over every cell and every pixel within it rather
> than only counting its product terms.
>
> ⚠ **The cell row is five bits, so cell mode addresses 32 rows.** That covers
> 80×25 and 80×30; **`VMODE` 10 and 11 need 50 and 60 rows and cell mode does not
> reach them.** Widening the field to six bits costs one bit of `MAPBASE`, takes
> the map region from 4 KB to 8 KB, and is otherwise the same concatenation —
> nobody has needed it.

**The map byte's `A1..A0` are not the pixel phase.** Every other fetch on the card
puts `col[1:0]` there, which is exactly what the `'153` mux is selecting on, so the
low two bits look after themselves. The map fetch is the exception: its `A1..A0`
are `cellCol[1:0]`, and a spare access has to *name* the chip it wants. So `vaddr`
emits **`MAPA1`/`MAPA0` = `SA4`/`SA3`** — the same identity as `SPNA[1:0]` =
`WPTR[1:0]` (§5.2.1). Four adjacent cells therefore sit on four different chips and
the map load spreads evenly. ⚠ **The name is fitted; the request is not** — the
arbiter gains it as a fourth requester (§6.4.9).

Both variants below need the map fetch **pipelined one cell ahead** of the tile
fetch — a serial dependency, and the same shape of pipelining the card already runs
for index → LUT → output.

#### 6.4.2 Variant A — 8bpp tilemap

Per cell: fetch the map byte, then the 8 tile bytes for this row. **The pixel path
downstream is unchanged** — the bytes flow through the `'153` mux, the index latch,
the LUT and the output latch exactly as bitmap bytes do.

| | Bitmap | **8bpp tilemap** |
|---|---|---|
| Screen memory | 128,000 B | **3,200 B** + 16 KB tile set — §6.4.1's stride note |
| CPU writes to change one cell | 64 | **1** |
| Display fetch per 8 dots | 8 accesses | 9 accesses |
| Per-chip load per cell (4.4 available) | 2.0 | **2.25** ⚠ |
| Colours | 256, per pixel | **256, per pixel — no attribute clash** |

It costs the same display bandwidth as the bitmap and buys **64:1 write
compression**, which is the right trade on a machine whose documented bottleneck is
the CPU and not bandwidth (§2.1). The nine accesses are eight tile bytes — two
ordinary four-chip display fetches — **plus one map byte from a spare access**; §6.4.9
is the sequence.

⚠ **Two different costs, and only one of them is an eighth.** Per-chip *load* rises
2.0 → 2.25 per cell, because the map byte lands on one chip in four, and that is the
figure §2.1's free-access budget scales by. But the map fetch takes the card's single
internal address bus for **one slot in two**, and slots are what the span writer
actually queues for — so **cell mode halves the span writer's spare slots**, and the
list engine's with them. `check:cadence` asserts both numbers off the fitted terms.

**A chunky 8bpp tilemap with no per-cell colour limit is not a mode any period
machine had** — the GIME's and VIC-II's tile/character modes are both 1bpp with
cell attributes. This one is strictly a superset.

**Cost: +1 IC, possibly 0.**

#### 6.4.3 Variant B — 1bpp character generator (dropped 2026-09-08; see history.md)

Not built. Its macrocells, product terms and four pins were spent on §10.3's list
engine — §10.1.6.2 has the fits. Text is §7's span writer in bitmap mode, and a
"text status bar over a bitmap playfield" survives via Variant A's 8bpp tiles. The
full design, its cost model, and the trade that decided the drop are archived in
[history.md](history.md).

#### 6.4.4 The span-mask serialiser is shareable (moot; see history.md)

Written for Variant B, which is not built (§6.4.3) — and the span-mask serialiser
is no longer a discrete `'165` in any case: it is absorbed into `vctrl` (§10.1.6).
The sharing argument and the `'AHC` grade requirement are archived in
[history.md](history.md).

#### 6.4.5 What it costs, and what it defers

The ICs are not the price. The price is programmable logic: the sequencer gains a
second fetch cadence with a serial dependency, and the scan-address logic must
switch between a linear scan address and the concatenated tile address, tri-stating
its low outputs during the tile fetch. Both are absorbed by the CPLD partition —
§10.1.6's `vaddr`/`vctrl` fit carries the whole of §6.4 — addressing and cadence
both — at **zero packages**. §6.4.9 is the sequence and §19 item 15(c) is closed. What
it did cost is headroom: `vctrl` went to **64 of 64 I/O and 121 of 128 cells**, and
`vaddr` to 109 of 128, so both still take JTAG and neither has room for the next
thing (§10.1.6.3).

Against that, **the blit datapath's 14 ICs become much easier to defer** (§10.3). A
tilemap redraws itself from the map every frame at zero CPU and zero blit cost, so
scrolling playfields, backgrounds and status bars stop being blitter work. What is
left for the blitter is *moving objects*, which is what §10.3 says it is for.

#### 6.4.6 Three limits, stated plainly

1. **The mode is global** — cells or pixels, not both in one region. But `CTRL` is a
   register, so a list-engine `MOVE` at a scanline boundary switches mid-frame: a
   status bar over a bitmap playfield, from the display list, with no CPU
   involvement (§10.3). The copper earns its keep again.
2. ⭐ **Cell mode scrolls in both axes, coarse and fine, from the same two
   registers as bitmap mode** — every cell-address field is a slice of a scan
   counter §8 already preloads, so `HSCROLL` and `VSCROLL` scroll a tilemap for
   nothing. `check:tile` walks every displayed pixel at whole-cell offsets,
   sub-cell offsets and across both ring wraps.

   | | Horizontal | Vertical |
   |---|---|---|
   | Cell | `SA9..SA3` — `HSCROLL[9:3]` | `SA17..SA13` — `VSCROLL[8:3]` |
   | Within the cell | `{SA2, mux phase}` = `HSCROLL[2:0]` | `SA12..SA10` = `VSCROLL[2:0]` |
   | **Ring** | **128 cells — 1024 px**, the bitmap's own torus | **⚠ 32 cell rows — 256 px** |
   | Margin off-screen at 80×25 | 48 cells | **7 rows** |

   ⚠ **The two rings are not the same size.** The map address has no `A18`, so the
   vertical ring is 32 cell rows against the bitmap's 512-row torus: a vertically
   scrolling playfield has **seven rows of runway** to write ahead into, not
   thirty-nine. Horizontally there is no such asymmetry — 48 cells of margin, the
   same 384 px §8 gives the bitmap. A sixth cell-row bit (§6.4.1) would take the
   ring to 64 rows for one bit of `MAPBASE` and 4 KB more map.

   `VSCROLL += 1` per frame is pixel-smooth in cell mode exactly as in bitmap mode,
   and `VSCROLL += 8` advances one whole cell row — the mechanism §6.4.8's terminal
   scroll uses. (§19 item 16 has the horizontal derivation and the one cadence
   guarantee it needs.)
3. **A 1bpp glyph serialiser would land on the tightest path in the card** — §6.1
   gives the index → LUT → output chain 11.7 ns of margin at 39.7 ns. That risk went
   out with Variant B (§6.4.3); it binds any rebuild.

**Register space:** `TILEBASE` and the map base sit in `+$17`–`+$19`, reserved in
§13; `FONTBASE`'s byte stays reserved against a Variant B rebuild.

#### 6.4.7 Recommendation

**Variant A is the built variant** — every pixel independently coloured, 64:1 write
compression on exactly the workload the CPU is worst at, and no change to the pixel
path at all — and since 2026-09-08 **sequenced**: §6.4.9's cadence closed §19 item
15(c), and `check:cadence` runs a line against the fitted terms.
Variant B was priced and dropped (§6.4.3): it reintroduces per-cell colour limits —
the one thing this card does not have and both period chips do — and §10.1.6.2's
fits show its silicon is worth more as the display list.

#### 6.4.8 Text in cell mode — one write per cell, one colour pair

**Variant A is also a character generator, if you are willing to spend the tile
codes on glyphs instead of graphics.** Bake a font into the tile set — one 8×8
glyph per code, rendered once with §7's span writer — and a character cell becomes
**one CPU write of one map byte**. Nothing new is built for this: the mode, the
concatenation and the register are §6.4's, and the font is data.

That is *fewer* writes per cell than §6.4.3's dropped hardware character
generator, which needed a code and an attribute:

| | span writer, bitmap (§7.3) | Variant B (dropped, §6.4.3) | **cell mode, one colour pair** |
|---|---|---|---|
| Writes per cell | 13 | 2 | **1** |
| Full 80×25 redraw | 62 ms — 16 Hz | 9.5 ms — 105 Hz | **4.8 ms — 210 Hz** |
| **Scroll one line** | 2.5 ms | 0.38 ms | **0.19 ms** |
| At 9600 baud (~12 lines/s) | 3 % CPU | 0.5 % | **0.23 %** |
| At 115.2 kbaud (~144 lines/s) | 36 % CPU | 5 % | **2.7 %** |
| Screen memory | 128,000 B | 2 KB font + map | **16 KB tiles + a 4 KB map ring** (3,200 B displayed) |
| Glyph depth | 8bpp, any colours | 1bpp + attribute | **8bpp — antialiased glyphs are legal** |

At the §7.3 rate of one write per 5 cycles at 2.098 MHz, 2,000 cells is 4.8 ms and
a scrolled line is **80 map bytes plus one write to `VSCROLL`**. The scroll is the
row that matters and it is the row cell mode wins by the widest margin: **115.2
kbaud stops being a third of the CPU and becomes a rounding error.**

**Scrolling is `VSCROLL`, not a memmove.** §6.4.6 limit 2: the map's cell row is
`SA17..SA13`, so `VSCROLL += 8` advances one cell row within a 32-row ring. 25 of
those 32 rows are displayed, so the seven off-screen rows are where the incoming line
is written before it is scrolled into view — the same trick §8's 512-row torus plays
for the bitmap, in cells.

**Without it the mode would be *worse* than the span writer**: moving 1,920 map bytes
with `TFM` is 2.75 ms against bitmap text's 2.5 ms, and the 64:1 write compression
would evaporate on the one operation a terminal does constantly.

**The price is that 256 tiles are 256 (glyph, colour) pairs, not 256 glyphs.** The
map byte is the whole cell, so a code that is a glyph in one colour is a different
code in another. That buys the one write and it is the thing Variant B's attribute
byte bought instead:

- **One fg/bg pair:** 256 glyphs — the whole of CP437, the CoCo 3 hi-res font, or
  VT100 line drawing, in 16 KB. This is the case the mode is good at.
- **More than one:** `TILEBASE` is five bits, so the 512 KB holds **32 banks**, and
  switching them is one register write — or a list-engine `MOVE` at a scanline
  boundary (§10.3), which makes the colour *per region* free. It is never
  per-cell.
- **256-colour ANSI art stays in bitmap mode**, where per-cell colour is two of
  §7.3's thirteen writes and paid for.

**⚠ Three things bound it.**

1. **The mode is global** (§6.4.6 limit 1), so this does not rescue NitrOS-9
   windowing any more than Variant B did — a text window beside a graphics window
   is still the span writer's job.
2. **32 cell rows**, so 80×25 and 80×30 only (§6.4.1). `VMODE` 10 and 11 need a
   six-bit cell row.
3. **The span writer loses half its spare slots while cell mode is on** (§6.4.2),
   because the map fetch takes the card's one internal address bus one slot in
   two. Per-*chip* load only rises 2.0 → 2.25; slots are the figure that moves.

**Building the font costs 256 × 13 = 3,328 span-writer writes, about 7.9 ms, once**
at mode set — and again per colour bank. Against a 4.8 ms redraw that is one
screen's worth of work to make every later screen thirteen times cheaper.

#### 6.4.9 The fetch cadence — nine accesses, one bus, one cell of lead

**§6.4.2's arithmetic fixes the sequence, and there is only one that fits it.** Eight
tile bytes *are* two ordinary display fetches — four interleaved chips × two slots —
so in cell mode the tile address owns the display half of every slot exactly as the
bitmap's scan address does, and the **ninth access is the map byte, out of §5.2.2's
spare window, once per cell**:

```
  slot     2k            2k+1          2k+2          2k+3
  spare    map[N+1]      -             map[N+2]      -
  fetch    tile N.0-3    tile N.4-7    tile N+1.0-3  tile N+1.4-7
           \______ cell N ______/      \_____ cell N+1 _____/
```

A cell is two slots and **its phase is `H0`, the slot counter's own low bit** — cell
mode needs no counter of its own to know where it is.

**The map fetch leads by one cell, and that lead is a timing requirement.** §6.4.1
calls it "pipelined one cell ahead"; the number behind it is that a slot is 158.9 ns
split half-and-half by §5.2.2. Fetching the map byte in the spare half of the *same*
slot that then fetches the tile row puts address mux (~15 ns) + SRAM (55 ns, §14.2's
`AS6C8016-55`) + latch setup (~5 ns) = **75 ns inside a 79.4 ns half**, and then makes
the tile address repeat it. Two 4.4 ns margins on a card whose tightest documented
path has 11.7 (§6.1). One cell of lead makes both a full half-slot.

So `MFETCH` opens **two slots before** `TFETCH`, during the last cell of the back
porch, and the map keeps **its own cell-column counter `MC6..MC0`** — because leading
by one cell means addressing cell *N* while `SA9..SA3` names cell *N−1*, and `SA + 1`
is the adder §6.4.1 says does not exist. Seven macrocells on `vaddr`, loaded from the
same `HSCROLL[9:3]`, started one cell earlier. **"One ahead" costs a counter, not an
adder.**

##### The arbiter gains a fourth requester, and the two ranks collide differently

§2.2's priority is *video → CPU → list engine → span → blit*, and **the map byte is
video**: refuse it and the cell shows a stale code, every frame. So it outranks both
existing requesters — but not in the same place, because §5.2.1's `SRCSEL[n]` muxes
each *chip's* address source:

- **The span writer collides on the bus.** The display fetch, the span writer and the
  map fetch all drive the card's one internal address bus, so they are exclusive in
  *time*. `SPNREQ` is gated off for the whole of a map slot — one gate, upstream of
  the arbiter, which leaves `arbDesign` untouched and still executable as a standalone
  `GAL22V10` by `check:access` and `check:cupl`. This is what halves the span writer's
  slots (§6.4.2).
- **The CPU collides per chip**, because its address path is its own. `GMAP[n]` is the
  map's chip and the CPU's grant is withdrawn for that chip only.

##### And so the CPU has to be able to wait

A refused CPU access is a lost one. The map's collision therefore joins §7.4's span
backstop on `/WAIT`, and **it is a different kind of wait**: §7.4's is up to 40.7 µs
and only writes take it; this one is **a single 158.9 ns slot and it must apply to
reads too**, because a read whose chip is pointed elsewhere returns the wrong byte.

`arbDesign` is not edited for this either. Its `/WAIT` output enable already reads two
signals, and both are renamed at merge to ones the cadence forms:

```
  oe      = WAITSRC & VRAMSEL & /IOPAGE & E & /WAITRW
  WAITSRC = SPANBUSY # MAPHOLD
  WAITRW  = RW & /MAPHOLD
```

so a map hold waits on reads and writes alike while §7.4's backstop keeps its `!RW`
exactly as before. `check:cadence` asserts all four cases.

##### What it is checked against

[`cadence.check.ts`](../../hardware/gal/cadence.check.ts) evaluates the fitted terms
over **a whole 800-dot line** and asserts the sequence rather than the equations: 80
map accesses for 80 cells, in order; `MAPLD` one dot per cell on the spare/fetch
boundary; the lead measured in dots; §6.4.2's 9-per-8-dots and 2.25-per-chip; never
two sources on the address bus; and the four `/WAIT` cases. Removing the one-cell lead
fails six of them.

**`FETCH` and `HLOAD` are produced here too**, because the map fetch had to be placed
against a fetch window and `census.ts` listed both as *"produced by the sequencer's
unfitted decode half"* — nothing generated them, in either mode. They are two range
compares on `hgen`'s slot counter, which is on the same part. The vertical half —
`ROWADV`, and the load that turned out not to need building — is **§8.1**.

## 7. 80×25 text — software glyphs, and a correction to colormin's cost

**The span writer is the card's general text engine.** §6.4.3's Variant B — a
hardware character generator — was priced and dropped, so the figures below are
what text costs wherever it has to mix with graphics or carry per-cell colour. A
character generator cannot mix with graphics *per-pixel* (§6.4.6 limit 1), so even
built it would have been global and switchable rather than free; NitrOS-9's
windowing draws into bitmaps either way.

⭐ **The exception is a full-screen console in one colour pair**, which §6.4.8 does
in cell mode at one write per cell and a `VSCROLL` per scrolled line. It is the same
global-mode trade Variant B made, so it does not replace this section — it is the
faster path for the one case that does not need per-cell colour.

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
| Full-screen clear (128,000 px, span-solid) | ~500 | ~1.2 ms CPU, **~5.1 ms to retire** with §7.4's broadcast write (20.3 ms without it) |

> **The retire bound:** one byte at a time, the span writer retires **one byte per
> 158.9 ns slot** — `WPTR` names one chip at a time and two sequential accesses do
> not fit the slack — so 128,000 bytes is 20.3 ms; §7.4's broadcast write retires
> four per slot, 5.1 ms. The CPU-bound rows are unaffected either way — a line
> scroll is 1,040 writes of CPU against 0.81 ms of retire, and stays CPU-bound.

**A terminal never full-redraws** — it scrolls, and scrolling is 2.5 ms plus one
register write. That is the number that matters, and it is comfortable. The 62 ms
full redraw is a mode-change cost, paid once.

Compare the alternative the 64x4 does not have: a `TFM` of a pre-rendered 8×8×8bpp
glyph is 64 bytes at 3 cycles each = 192 cycles ≈ 92 µs per cell — **3× worse than
the span writer**, because the span writer moves 8 pixels per CPU write and `TFM`
moves one. Text belongs to the span writer; `TFM` earns its keep elsewhere (§10.2).

### 7.4 The span writer, respecified for 8 × 8 cells

The mechanism is inherited from minimal256, which was designed around **6-pixel
cells**. §6.1 says what changes:

> "colormin's span-mask serialises a byte and stops at `SPANLEN`; with 6-px cells two
> bits per write are wasted. At 8×8 the mask byte *is* the glyph row."

**The consequence is that span-mask mode does not consult `SPANLEN` at all.** Its
length is eight, always, because eight is the cell width: the byte the CPU writes is
exactly one glyph row and there is nothing to truncate. The length comes from a
three-bit counter — three bits *because* a cell is eight wide — and `SPANLEN`, an
eight-bit down-counter of its own, belongs to span-solid alone.

**That is what makes §7.3's "13 writes per character cell" true.** `WPTR` ×3 + `WFG` +
`WBG` is five of setup, then eight glyph rows. `SPANLEN` is not among them. Had mask
mode needed it, a cell would be **14** writes and every text figure in §7.3 would be
7 % worse. `npm run check:seqctl` asserts the 13.

#### Where the state lives

| | Where | Why |
|---|---|---|
| the mask byte | the `'165`-equivalent serialiser macrocells in `vctrl` (§10.1.6's absorption), loaded at `WSTB` | its serial output *is* a register-file address line |
| span-solid's length | the `SPANLEN` down-counter in `vctrl` (absorbed `'161` pair), loaded at `WSTB` | §14.1's absorption list |
| **span-mask's length** | **3 macrocells in `seqctl`** | **the cell width, fixed at 8** |
| `SPANBUSY` | 1 macrocell | `VSTAT` b7, and the `/WAIT` condition |
| the pointer | `wcol` / `wrow` | §19 item 12 |

**The mask bit never enters the sequencer.** The serialiser's serial output is wired
to the register file's address bit 0, which is why §13 requires `WFG` at `A0 = 0` and `WBG` at
`A0 = 1`. Choosing the source colour per pixel costs no macrocell and no product term
— it is an address line, and that placement rule *is* the mechanism.

#### One handshake, three terminations

```
  WSTB      a posted write has been latched (§3.1.1's '574s hold the address, the
            data, R/W and WMODE[1:0]) -> load the mask serialiser and the SPANLEN
            counter, zero the mask counter, set SPANBUSY
  SPNGRANT  the arbiter matched WPTR[1:0] against the CPU's chip and gave the span
            writer a spare access (§5.2.1)
  RETIRE    = SPANBUSY · SPNGRANT. One byte goes to VRAM. Drives WPTR's WINC, the
            serialiser's shift and SPANLEN's count — one signal, three loads,
            because those three advance together by construction
  SPANEND   the last byte retired -> apply WADV, clear SPANBUSY
```

| `WMODE` | Mode | Ends when |
|---|---|---|
| `00` | direct | the **first** byte retires — §3.1.1's posted write |
| `01` | span-mask | the **eighth** byte retires — the cell width |
| `10` | span-solid | the `SPANLEN` counter's terminal count — `SPANLEN` + 1 bytes |

Loading the `SPANLEN` counter in mask mode is harmless, and that is what lets `WSTB` drive
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

**Specified — §14.2's two-chip framebuffer is what makes it the default, and the
datapath for it is already wired.**

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

**The pins are not a problem.** `rfa` (`gal/regfile.jedec.ts`) freed fourteen of
them, and even with the arbiter merged back `vctrl` sits at **64 of 64** (§10.1.6.3).
There is room to signal, and §14.2's two-chip framebuffer means there is barely
anything to signal.

> ⚠ **The arbitration is the real work on four chips.** An all-or-nothing "grant all
> four" is one extra term and needs no feedback — but **during a `/WAIT` stall the CPU
> is holding one chip, so only three are free**, and the wide grant would never fire in
> exactly the case where the span writer is the bottleneck. Granting *whichever* chips
> are free works, and then the span writer has to learn how many it got: a count back
> from the arbiter into `WPTR`'s increment and `SPANLEN`'s countdown.

⭐ **§14.2 dissolves that, and it is why this is specification rather than proposal.** The framebuffer
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

#### How long `SPANBUSY` lasts — the bound `machine.md` §5 item 10 asked for

`/WAIT` is `SPANBUSY · VRAMSEL · /IOPAGE · E`
(`gal/access.jedec.ts`), so the video card holds the machine only while a span is in
flight **and** the CPU is touching VRAM. The length of that is `WMODE` and nothing else,
because the retire rate is fixed: §3.1.1 gives **one granted retire per fetch slot**, and
a fetch slot is 158.9 ns.

| `WMODE` | Bytes | `SPANBUSY` | |
|---|---|---|---|
| `00` direct | 1 | **159 ns** | one posted write |
| `01` span-mask | 8 | **1.27 µs** | a glyph row — the cell width, §7.4 |
| `10` span-solid | **up to 256** | **up to 40.7 µs** | `SPANLEN` is **eight bits** |

**40.7 µs is the number, and it is longer than a scanline.** Against the rest of the
machine: 85 bus cycles, 2.6 DRAM refresh intervals, 51 net framer byte-times, and just
under `sdcard.md` §4.4's 49 µs masked chunk.

> **Why the span writer is 6.29 MB/s and not 25.** Its pointer is one pointer. §2.1
> leaves one spare access per chip per slot and there are four chips, but `WPTR` names
> one of them at a time, and two sequential accesses do not fit the 86.9 ns of slack
> (2 × 72 ns). So the span writer retires **one byte per slot**, and every rate that
> depends on it follows from 158.9 ns.

**Three consequences, and only the third needs anything done:**

1. **DRAM refresh is unaffected** — `hardware/ram.md` §6.6's open question, closed. `/WAIT`
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

##### Only writes wait

`/WAIT`'s output enable carries `& !RW`, so the stall applies to writes alone.
§3.1.1 says what the backstop actually protects: **the depth-1 posted-write latch**,
which a second CPU *write* during a span would overwrite.

**A read does not touch that latch**, and §5.2.1's arbiter already gives the CPU its
chip ahead of the span writer, so a read has no conflict to wait for either — an
unqualified `/WAIT` would stall it for up to 40.7 µs for nothing. The
qualification is one literal on an output-enable term that already exists.

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

  > **Byte-granular scroll is what forces per-chip fetch-latch clocking**
  > ([`hardware/gal/seqph.jedec.ts`](../../hardware/gal/seqph.jedec.ts)). Chip *n*
  > holds the byte at the column where `c mod 4 = n`, so if all four fetch latches
  > were loaded from a common address bus at a common instant, then during fetch
  > slot *g* every chip would hold a byte of group *g*. With `HSCROLL[1:0] = p`,
  > the mux emits `4g+p`, `4g+p+1` … and then **wraps to chip 0, which still holds
  > `4g+0`** — the line steps backwards, `4−p` pixels in. §5.2.2's *per-chip*
  > clocking is the fix: chips `0..p−1` take the next group's byte on a late clock
  > while `p..3` still hold this one. The four `FCLK` equations are a
  > phase-dependent offset rather than four copies of one term — 9 product terms,
  > no new package (§19 item 23, closed). `check:seqph` computes both sequences
  > from the fitted fuses: it asserts the common-clock line diverges for every
  > `p ≠ 0` and the per-chip line is contiguous for every `p` — arithmetic, not
  > simulation.

### 8.1 What drives the counters

⭐ **Scrolling is a register write only if something steps the counter the register
loads.** Until 2026-09-08 nothing did: `FETCH`, `HLOAD`, `ROWADV` and `VLOAD` were
declared as `hadr`/`vadr` inputs and produced by nobody, so the column counter never
took `HSCROLL`, the row counter never took `VSCROLL`, and **the row never advanced at
all — in either mode.** That was the bitmap's gap as much as the tilemap's. All four
are fitted now, on `vctrl` beside the counters they time.

| | | |
|---|---|---|
| `HLOAD` | slots 0–33 | through the sync pulse and back porch, before `MFETCH` opens |
| `FETCH` | `TFETCH & SLOTTICK` | one edge per slot of the 160-slot window |
| **`VLOAD`** | **`VBLANK`** | not built — see below |
| `ROWADV` | `!VBLANK & HEND & SLOTTICK & (VMODE1 # !V0)` | one edge per displayed line, in slot 199 |

⚠ **Every counter *enable* carries `SLOTTICK`; a *load* does not.** Both parts are
clocked on `DOTCLK`, so a window level asserted for a whole slot advances a counter
four times — once per dot. `FETCH` without it walks 2,560 pixels across a 640-pixel
line; `ROWADV` without it scans the picture at quarter height. A load is idempotent
and needs no gate, which is why `HLOAD` and `VBLANK` are plain windows.
`check:cadence` counts the edges per dot, which is the only way that distinction is
visible.

**`VLOAD` is `VBLANK`.** §8 asks for a load "asserted through vertical blanking", and
that is what `vdec` has been producing all along — the signal was named twice and
built once. `vadr`'s input is renamed at merge, which keeps the standalone design and
its `GAL22V10` checks untouched and costs nothing on a part at 64 of 64 I/O. The same
identity as `WRITESEL` = `SPNGRANT` (§5.2.1) — and **`CE` = `SLOTTICK`** turned out to
be a third: `hgen` declared its slot enable as an input while saying in the same
breath that it *"is that signal and not a second divider"*, and `vctrl` was taking its
own output back in on a pin. That pin is what paid for `ROWADV`.

⭐ **§6.2's line doubling lives in `ROWADV` and nowhere else** — *"the sequencer
withholds every second one"*. `VMODE1 = 0` is the doubled pair (640×200, 640×240) and
`VMODE1 = 1` is one row per line (640×400, 640×480). Which line to withhold is **one
term in both families**: a doubled row must advance at the end of the second displayed
line, so the test is the parity of `V` minus the first active line — 37 in the
449-line family, 35 in the 525 — and **both are odd**, so "advance when `V` is even"
covers both. The same accident that gives `vdec` its "`v <= 1` in both families" sync
window (§6.2.1).

[`cadence.check.ts`](../../hardware/gal/cadence.check.ts) runs a **whole frame in each
of §12's four `VMODE` codes** at five scroll positions including the 512-row wrap, and
asserts which row each displayed line shows, that each mode visits exactly 200/240/400/480
rows, that a doubled mode shows each row on exactly two consecutive lines starting at
display line 0, and that `ROWADV` fires clear of both fetch windows so the row cannot
move under the addresses it is feeding.

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

> **Bare ladders facing the connector are not buildable.** "3 × R-2R SIP, 5/6/5
> ladders" alone is not an analog back end, and the arithmetic below is why the
> drive stage exists.

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

- **`/OE` on the post-LUT latch — rejected.** Three-stating the register **floats** the
  ladder's inputs. A floating R-2R ladder does not output 0 V; it outputs whatever
  leakage and stray coupling give it, which is undefined, drifts, and is not black.
- **Forcing palette index 0 during blanking — rejected.** Wrong for a reason specific to this
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

blitter.md §6.2 flags it: a GAL-only build of this card is **10** GAL22V10s before
any blitter, the full blitter adds ~10 more, and **"eighteen GAL22V10s is the point
where the honest question becomes 'why not one CPLD'."** 18–20 GAL22V10s is a power
and area problem as much as a fitting one — at ~70–90 mA each that is 1.3–1.8 A of
GAL alone. The card walked into that wall, and the answer is the build §10.1.6
describes: **2 × `ATF1508AS` PLCC-84 + 1 × `GAL22V10` + 4 SRAM + 20 packages of
74-series = 27 ICs** — §14.1 has the arithmetic. The GAL-build tables and the
step-by-step argument that produced the reversal are archived in
[history.md](history.md).

#### 10.1.1 Where the macrocells actually go, and what can be removed

The GAL build's macrocell census (archived in [history.md](history.md), with the
per-part fits) proved the thing that decided the architecture: **the card is
programmable-logic-heavy for exactly one reason — ~54 of its macrocells are counter
bits, and a GAL22V10 has no buried nodes.** Every register costs a macrocell *and* a
pin whether or not anything outside the package ever looks at it.

Buried-register GAL-class parts exist — Lattice **GAL6001/6002** (10 I/O macrocells
plus 8 buried registers, 24-pin, 1990) and Atmel **ATF750C** (10 output plus 10
buried macrocells in the 22V10's own footprint, still in production) — and they save
**exactly one package in ten**: buried registers help only where the register never
leaves the chip, and on this card that is the sync trio and nothing else. The scan
and `WPTR` pairs' 36 counter bits **are** the address buses — no part choice changes
that, because the output is the point. Pure `'161`/`'163` counters are worse still
(more packages, more area). The part that actually fixes it is one with buried nodes
*and* shared routing — §10.1.2.

#### 10.1.2 The CPLD question, answered with numbers

**The chronology does not block a CPLD.** §15's period audit places this card at
**1989–90**. Altera's EP300, the first reprogrammable PLD, is **1984** — two years
*before* the GAL22V10 the card already uses. The MAX 5000 family, the first part
that is architecturally a CPLD rather than a large PAL, is **1988**, a year before
the card's own date. A CPLD here is the *third*-newest part on the board: §15
already carries 74AHCT at ~1990 and flags the SRAMs as newer. **"No CPLDs" was
never a period rule on this card. It was a style rule** — one function per package,
everything visible on a scope — and that is a good reason, but not a period one.
(The root `README.md` retired the machine's no-CPLD rule citing exactly this
argument; the retirement narrative is in [history.md](history.md).)

**And the pin arithmetic decides it.** `npm run census`, computed from the fitted
GAL designs rather than counted by hand:

| | |
|---|---|
| ten GAL22V10s | 90 macrocells, **188 signal pins** |
| 21 inter-package nets | 43 pins |
| outputs nothing outside the group consumes | **54 pins** |
| | **97 of 188 pins — 52% — are an artefact of the packaging** |
| external I/O, everything that must reach a pin regardless | **84** |
| macrocells, with the address mux single-die integration forces | **~120** |

Half the pin count is the packaging talking to itself: a 22V10 has **no buried
nodes**, so every counter bit and every intermediate term is on a pin whether or not
anything wants it. The one place merging costs silicon rather than saving it is the
framebuffer address mux — on GALs the scan and `WPTR` pairs tri-state onto a shared
bus for free; inside one die two macrocells cannot drive one pin, so the 17 address
outputs are 17 further macrocells fed by both counter sets.

That is CPLD-shaped, and the fit is §10.1.6. The equations, the models and every
check in `hardware/gal/` are device-independent and transfer unchanged; what does
not transfer is `hardware/gal/jedec/`'s GAL22V10 assembler and fuse-map simulator —
an ATF1508AS is fitted by Microchip's own `fit1508.exe`. The verification
investment survives; the fitter does not. Power is measured in §14.1 from the
`ATF1508AS` datasheet, and it confirms the change: two CPLDs plus one GAL at
~270–330 mA against the ten GALs' 700–900 mA.

#### 10.1.3 Part selection — `ATF1508AS`, 5 V, `-15`

**The part is the `ATF1508AS`, two of them in PLCC-84, socketed** (§10.1.6; the
single-package TQFP-100 and PQFP-160 routes it displaced are archived in
[history.md](history.md)). The comparison this card invites is with the GIME and the
VIC-II, and both of those are single custom ASICs; holding this design to discrete
GALs while measuring it against them is not a like-for-like fight. The house rule is
restated as a style rule (§10.1.2) and set aside for the video card.

**The ordering code carries a trap.** The 5 V device is `ATF1508AS`; **`ATF1508ASV` is
the 3.3 V part** — two datasheets, "ATF1508AS(L) **5V** 128-Macrocell" and
"ATF1508ASV(L) **3.3V** 128-Macrocell". The cheap listings are mostly ASV: an
`ATF1508ASV-15AU100` is ~$6 where an `ATF1508AS-10AU100` is ~$16. On a 5 V card the
$6 part is the wrong one.

**The 3.3 V `ATF1508ASV` question is closed — on cost, not on tolerance.**
`reference/datasheets/ATF1508AS.pdf` confirms the family splits its rails:
`VCCINT` for the core, `VCCIO` per bank, with `VIH` specified as `VCCIO + 0.3 V`.
On the 5 V `AS` that means 5 V inputs, and the same structure makes it *likely* the
3.3 V `ASV` interfaces 5 V with `VCCIO` tied to 5 V — but that is the `ASV`'s
datasheet to state and this is not it, so the tolerance question stays formally
open. It does not need answering, because the ~$10 saving buys a rail the machine
does not have: `ASV` needs `VCCINT` at 3.3 V, §17's backplane carries 5 V, and the
card would gain a regulator, a rail and a decoupling story to save ten dollars once.
**Buy the `AS`.**

**Speed grade `-15`** — the slowest is the cheapest, and 15 ns is comfortable at
25.175 MHz. ⚠ Confirm a `-15` is stocked in 5 V PLCC-84 before committing; falling
back to `-10` costs money, not margin.

**What the datasheet changes about the design, beyond the price:**

- **Buried registers are confirmed** — *"Maximum Logic Utilization by Burying a
  Register within a COM Output"*. §10.1.2's census assumed it; it is a feature line.
- ⚠ **Five product terms per macrocell, expandable to 40 by cascade.** The 22V10's
  8–16 term macrocells are not the shape of this part. The widest equations fitted —
  `V9` at 16 terms, `SPNGRANT` at 16, `VBLANK` at 13 — all need cascade chains, which
  `fit1508.exe` builds automatically and which cost delay. Not a blocker at 25 MHz,
  and the GAL-era sorted-pairing placement rule (history.md, §19 item 8) simply
  disappears on this part.
- **Two bytes of User Signature**, against the GAL's eight. The `A6309Vn` strings in
  `hardware/gal/*.jedec.ts` do not fit; a two-byte revision code does.
- **Three global clocks, six global output enables, a global clear** — the 22V10's one
  clock and one shared asynchronous reset were a real constraint on the sync trio
  and are not one here.

**It is cheaper than what it replaces**, which was not the expected result: ~$16 per
part against ten `ATF22V10C` at $2–3 each, and the absorptions delete four more
packages on the way.

**Nothing above obliges the rest of the machine.** The motherboard's two GALs are
unaffected; the argument was always about this card's ten.

#### 10.1.4 Can it be squeezed into one PLCC-84? — no (see history.md)

One `ATF1508AS` PLCC-84 is **seven pins short** of the single-die design, and the
pins do not exist to save — the closest squeeze traded away byte-granular
horizontal scroll and was still three short. The full analysis, including the
two-`ATF1504AS` variant that does fit and the census-artefact correction it
surfaced, is archived in [history.md](history.md). The build takes **two
`ATF1508AS` PLCC-84s** instead (§10.1.6), and the display list then filled them.

#### 10.1.5 §6.4's tile mode is in v1, and it set the package

§6.4.2's Variant A is v1 hardware, not an option. **§2.1 is why this is not
optional**: that section's own conclusion is that the card has far more spare memory
bandwidth than the CPU can consume and that *"bandwidth is not the constraint on
this machine — **the CPU is**."* A 64:1 reduction in CPU writes per cell is the
single largest thing on this card that acts on the actual bottleneck.

Carrying §6.4's fetch machinery is what pushed the design past every
single-package fit and onto the two-PLCC-84 build — §10.1.6. (The census
arithmetic, and the role §6.4.3's Variant B played in it before it was dropped, are
archived in [history.md](history.md).)

**v1 hardware, and a sequence that runs.** The registers, the address mux and the
pins are fitted; `check:tile` asserts what they compute, including both axes of scroll
(§6.4.6 limit 2); and `check:cadence` runs the second fetch cadence over a whole line
(§6.4.9). ⚠ The package decision is unchanged but its **headroom is gone**: the
cadence took `vctrl` to 64 of 64 I/O and 121 of 128 cells.

**What §7 keeps.** The span writer is not deleted — it is the text engine, the fill
and clear engine, and §6.4.6's limit 1 means bitmap regions need it regardless.
`seqctl` and §7.4 stand unchanged; `check:seqctl` asserts the 13 writes per cell,
and since Variant B is not built (§6.4.3) that is the card's only text mode that
mixes with graphics or colours per cell — §6.4.8 is the one-colour-pair console.

#### 10.1.6 Two PLCC-84 parts — and this is the build

The `ATF1508AS` in **PLCC-84 has all 128 macrocells**; only
the I/O is cut, to 64 (+4 dedicated inputs, less JTAG's four — both parts reserve
them and still fit, §10.1.6.3). That one fact settles the question:

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
  with whatever they clock. The fit spends that freedom — `vaddr` is at 109 of 128
  logic cells and 61 of 64 I/O — so the choice is no longer free.
- **Two JTAG chains**, or one chained through both.

**The partition** — `hardware/gal/cpld/`, regenerated by
`hardware/gal/prjbureau/fit1508.sh`. It carries §6.4's tiling and §10.3's display
list — the whole of v1:

| | Package | Holds | Logic cells | I/O pins |
|---|---|---|---|---|
| **`vaddr`** | PLCC-84 | scan and `WPTR` counters (`WPTR` doubling as the list engine's pointer, §10.3.1), scroll and tile registers, the write-strobe decode, the four-source address mux, the list engine | **109 of 128** | **61 of 64** |
| **`vctrl`** | PLCC-84 | sync trio, sequencer, span control, `CTRL`, §6.4's fetch cadence, the register decode, **the spare-access arbiter** (§10.1.6.3) | **121 of 128** | **64 of 64** |
| **`rfa`** | **`GAL22V10`** | the register-file address — `RA0`–`RA4`, `WSTB`, the span-source walk (§10.1.6.3) | 6 of 10 | — |

The three-line table is the whole card's programmable logic. `DOTCLK` lands on a
global clock and `RESET` on the global clear, both CPLDs, with two of four dedicated
inputs used. 74,136 fuses each.

**Count logic cells, not equations.** The fitter cascades any equation wider than
five product terms across extra cells, and the address mux is four sources on
seventeen bits — macrocell estimates made by counting equations run low, every time.

#### 10.1.6.1 Two things the partition gets right

**`CTRL` never crosses the boundary.** §12 gives reads their own register, `VSTAT`,
so `CTRL` is write-only and belongs entirely inside `vctrl` — exporting its bits and
re-importing `HPOL`, `M0`, `IRQEN`, `WM0`, `WM1`, `TILEMODE` and `CHARMODE` would
cost fifteen pins to hold a byte that never leaves the part. That one placement is
larger than the whole of §6.4's fetch cadence, and it is what makes room for it.

Two bit-map consequences, both using space §12 had already reserved:

- **b2 is `CHAR`.** §12 spends three bits on `VMODE` and defines four codes, so b2
  was dead. With b5 it gives §6.4 both modes for nothing.
- **b5 is `CELL`** — cell fetch on.
- **`HPOL` is not a register bit.** §12's four codes are 70 Hz at `VMODE0 = 0` and
  60 Hz at `VMODE0 = 1`, and the 70 Hz pair is the positive-H pair, so
  `HPOL = !VMODE0`. A pin for a NOT gate is a pin wasted.

**Two selects are the same signal under two names.** `WRITESEL` is `SPNGRANT`, since
the write pointer owns the address bus exactly when the arbiter has given the span
writer a chip, and `LISTSEL` is `LGRANT` for the same reason. Both are identities,
not pins.

#### 10.1.6.2 The list engine shares `WPTR`, and fan-in is why

The engine has to be on the part with the address mux — its pointer *is* an address
source, so anywhere else is nineteen crossing nets — and an engine with its **own**
19-bit pointer fits no package at all. An ATF1508AS logic block is 16 macrocells
behind a switch matrix that admits 40 of roughly 200 global signals, and a
nineteen-bit pointer feeding a multi-source seventeen-bit mux does not fit through a
40-signal window however many macrocells sit behind it: the fitter aborts with
`INTERNAL ERROR` on the PLCC-84 and still fails on the TQFP-100's 80 I/O, so pins
were never the constraint — **fan-in is**.

**So the engine shares `WPTR`.** The span writer and the list engine never drive the
address in the same slot, so the engine fetches into `WPTR` instead of carrying its
own pointer — removing 19 registers, 19 mux inputs and the mux's extra product term
per address bit. With §6.4.3's Variant B also out, the build lands at:

| | I/O | Logic cells | Nodes+FB | |
|---|---|---|---|---|
| **`vaddr`, engine in, Variant B out** | **64 / 64** | **102 / 128** | 133 / 128 | ✓ **built** |
| `vctrl`, Variant B out, before the arbiter's return | 46 / 64 | 87 / 128 | 83 / 128 | ✓ — §10.1.6.3 has the final 64 of 64 |

`ARM6309_LIST` defaults to on in `gal/video.cpld.ts`, and §14's table gains nothing
— the engine costs no package. It cost two things that are not packages: **§6.4.3's
Variant B** (its macrocells, product terms and four pins), and the engine's own
pointer. The intermediate fits, and the alternatives that were measured and not
taken, are archived in [history.md](history.md).

> ⭐ **`vaddr` has JTAG** — 61 of 64 with `TMS`/`TDI`/`TDO`/`TCK` reserved, so the
> display list did not cost in-circuit programming after all. §6.4.1's corrected
> cell address is what paid for it (§10.1.6.3), not a rebalance against `vctrl`.

> ⚠ **The shared pointer is a specification rule, not only a fit: the engine
> CLOBBERS THE CPU'S WRITE POINTER**, so anything that starts a list must reload
> `WPTR` afterwards — three writes to §13's `+$08`–`$0A`. `LIST` at `+$0B`–`$0D`
> does not exist: a second address for the same nineteen registers is a fiction,
> and one that invites exactly the mistake the rule guards against. **§10.3.1 has
> the rule and the three bytes are back in the reserve.**

The write strobes are decoded on `vaddr` from a five-bit register address and one
strobe, in place of nine strobe pins (§19 item 23). §13's window is **32 bytes**,
`$FF60`–`$FF7F`, with `TILEBASE`/`FONTBASE`/map base reserved at `+$17`–`+$19`.

#### 10.1.6.3 The arbiter lives in `vctrl`, and `rfa` is the card's one GAL

Three machine-level inputs land on `vctrl` — `A6` on `REGSEL` (`machine.md` §5
item 1 A widened the geographic window to `$FF00`–`$FF7F`, so every card decodes
seven bits), `/A20` on `VRAMSEL` (§5 item 1 D made the physical map 2 MB), and
`& E` on `WAIT.oe` (§5 item 8) — and the pin budget that absorbs them, the arbiter
and all, is bought by one GAL:

**U-V9 `rfa`, the register-file address**
([`gal/regfile.jedec.ts`](../../hardware/gal/regfile.jedec.ts)). It carries
`RA0`–`RA4` and `WSTB`, and it **re-derives rather than imports**: `REGSEL` is
`IOSEL & A6 & A5` — three signals it already needs — so it is recomputed locally,
and `RDLEN`/`RDFG`/`RDBG` come from `!SPANBUSY & FP1:FP0`. The trade is six pins
out of `vctrl` and two back (`FP0`, `FP1`) — **fourteen pins net**, because
removing the five `RA` outputs also removed every input that existed only to feed
them (`A0`–`A4`, `IOSEL`, `A5`, `A6`). `rfa` is 6 macrocells of 10 (largest
equation 10 terms of 16, `RA2`), checked against CUPL over all 8,192 input
combinations by `gal/jedec/cupl.check.ts`. `hardware/gal/video.cpld.ts` and
`hardware/gal/regfile.ts` carry the argument, and §7.4's broadcast write has room
to signal through the freed pins.

**The spare-access arbiter is inside `vctrl`.** With `rfa`'s fourteen pins and
Variant B's four freed, `vctrl` holds the arbiter at **64 of 64 I/O and 121 of 128
cells**. A CPLD at two-thirds capacity sitting beside a `GAL22V10` doing ten
macrocells of work would be a package nobody is buying anything with — the
one-morning excursion in which the arbiter *was* a separate GAL is archived in
[history.md](history.md). **The card is 27 ICs and one GAL.**

**`WRITESEL` does not exist**, and that is the tell that this is the right shape:
§5.2.1 says `WRITESEL` **is** `SPNGRANT`, and the alias only ever existed to carry
the signal across a package boundary. With the arbiter on-part, `vaddr` reads
`SPNGRANT` directly and the identity is an identity.

> ⚠ **`rfa` cannot merge back in.** It was fitted and fails: `rfa` is what bought
> the fourteen pins that made room for the arbiter, so putting it back spends them
> and `vctrl` overflows. The two functions were never symmetric — `rfa` exports six
> outputs and takes nine inputs that exist only to feed them; the arbiter exports
> ten and takes signals the part already has.

> **Housing the arbiter on-part costs no verification.** `arbDesign` stays in
> `access.jedec.ts`; `access.check.ts` still executes its fuses against
> `access.model.ts` and `jedec/cupl.check.ts` still sweeps it against Atmel's
> compiler over all 1,024 inputs — a `GAL22V10` fuse map is the only form either
> check can execute, so the standalone design is the verification and not a
> leftover. Its `.jed` carries the **SUPERSEDED — DO NOT PROGRAM** banner, which is
> the guard that stops a superseded design being burnt.

⭐ **Both CPLDs have JTAG.** `TMS`/`TDI`/`TDO`/`TCK` are **four of the 64 I/O, not
extra pins** — the `ATF1508AS` shares them with ordinary I/O (PLCC-84 pins 14, 23, 62
and 71), which is exactly why JTAG has a cost at all. So the totals are logic pins
*plus* those four:

| | logic I/O | JTAG | total | dedicated inputs | cells |
|---|---|---|---|---|---|
| `vaddr` | 57 | +4 | **61 of 64** | 3 of 4 | 109 of 128 |
| `vctrl` | **60** | +4 | **64 of 64** | 2 of 4 | 121 of 128 |

Both report "Design fits successfully" with the four reserved
(`JTAG=on hardware/gal/prjbureau/fit1508.sh`), and no logic signal is placed on them.
**They are programmed in circuit**, unlike the audio card's `ATF1508AS`. ⚠ `vctrl` is
*exactly* full: 60 + 4 = 64, nothing spare.

⚠ **And that is the end of the headroom.** §6.4.9's cadence spent what §6.4.1's
correction returned: `vctrl` is at **64 of 64 I/O and 121 of 128 cells**, `vaddr` at
61 of 64 and 109 of 128. Both still fit, JTAG included, and **neither has room for
the next thing.** §14.2's two ×16 framebuffer parts are the relief that exists on
paper — 2 grants instead of 8, six output pins — and it is a §5.2 rewrite (§19 item
25).

The pins came from §6.4.1's correction, not from a rebalance: `vctrl` was exporting
`V0..V2` to `vaddr` as the row inside the cell, and that was the wrong counter —
the right one, `vadr`'s row counter, was already on `vaddr`. Three pins on each
part, against the four JTAG needs and the two `vctrl` had. §14.2's two ×16
framebuffer parts would free six more by making the arbiter 2 grants instead of 8
(§19 item 25); that is no longer what in-circuit programming waits on.

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

### 10.3 The list engine is built; the blit datapath is deferred

**The list engine lives in the CPLDs, at zero packages** — `ARM6309_LIST` defaults
to on in `gal/video.cpld.ts` and both parts fit a PLCC-84. It cost §6.4.3's
Variant B and the engine's own pointer instead (§10.1.6.2).

blitter.md §6.1 reaches the same engine-first conclusion for colormin, and every
reason is stronger here:

- The span writer covers text, fills, clears and scroll refills — and it covers
  them better at 8×8 cells (§6.1).
- `TFM` covers bulk main-RAM movement.
- The list engine is what delivers **per-scanline `HSCROLL`** — parallax, sine
  warps, split-scroll status bars — from one descriptor list and no CPU
  involvement. On a machine whose CPU is the bottleneck (§2.1), taking work off
  the CPU is worth more than raw fill rate.
- Its `MOVE` opcode is one SRAM write into the register file, and the palette it
  writes to already exists.

`BCTRL` and `BSTAT` sit at `+$0E`–`$0F`; there is no `LIST` register (§10.3.1).
The board-to-board blitter header stays reserved (blitter.md §9, hooks 2 and 6).

#### 10.3.1 The `WPTR` reload rule — what the shared pointer costs software

**The engine has no pointer of its own.** Sharing `WPTR` is what made it fit
(§10.1.6.2), and the price is a rule rather than a package: **`WPTR` and the list
pointer are the same nineteen registers.**

| | |
|---|---|
| `+$08`–`$0A` `WPTR` | the span writer's pointer — **and the list engine's.** A list is started by pointing this at the descriptor list |
| `+$0B`–`$0D` | reserved — there is **no `LIST` register**. A second address for the same nineteen registers would be a fiction, and one that invites exactly the mistake this section exists to prevent |
| `+$0E` `BCTRL` b0 `GO` | starts the walk. From here the engine owns `WPTR` |
| `+$0F` `BSTAT` b0 `LRUN` | **1 while the engine owns it**, 0 when the list ends |

**The rule, in one sentence: anything that starts a list must reload `WPTR` before its
next drawing operation.** Three writes to `+$08`–`$0A`, ~7.1 µs.

```
    ; start a display list - WPTR IS the list pointer
    lda   #list>>16
    sta   WPTR          ; +$08 - the pointer is 19 bits, so three byte stores
    ldx   #list
    stx   WPTR+1        ; +$09, +$0A
    lda   #1
    sta   BCTRL         ; GO. WPTR now belongs to the engine.
    ...
    ; before ANY span, fill or glyph, point it back:
    lda   #dest>>16
    sta   WPTR
    ldx   #dest
    stx   WPTR+1        ; three writes, ~7.1 us
```

##### Why this is safe rather than merely cheap

**The two never contend.** §5.2.1's arbiter grants one requester per chip per slot, and
the engine and the span writer are the same requester — they reach the framebuffer
through the same `SPNGRANT & WA[n]` mux source (`video.parts.ts`). There is no window in
which both hold the pointer, so the failure mode is not corruption; **it is drawing at
the wrong address**, which is deterministic and reproducible.

**And it is observable before it bites.** `BSTAT` b0 `LRUN` is 1 for exactly as long as
the engine owns `WPTR`, so a driver that cannot statically know whether a list is running
polls one bit. `VSTAT` b7 `SPANBUSY` (§13) answers the same question for the span writer,
and §7.4's `R/W` qualification means **reading either is free** — neither is in VRAM, so
neither triggers `/WAIT`.

##### The three rules a driver keeps

1. **Reload `WPTR` after `BCTRL.GO`**, before the next span, fill or glyph.
2. **Do not start a list while `SPANBUSY`**, or the engine's first `LADV` collides with a
   span still retiring. §7.4 bounds that wait at **40.7 µs** today and **10.2 µs** once
   §14.2's two-chip framebuffer lands — poll `VSTAT` b7.
3. **A per-frame list is started once in `VBLANK`**, not per drawing operation, so in
   practice rule 1 costs 7.1 µs per *frame* — **0.05 % of a 14.27 ms frame**, against the
   0 % it would cost with a separate pointer and the package that pointer did not fit in.

⚠ **What is not settled here is the interaction with `WADV`.** §13's `+$14` changes what
`WPTR` does on increment, and the engine's own walk is a plain +1. A driver that leaves
`WADV` in vertical mode and then starts a list would have the engine step by the stride.
**`BCTRL.GO` should force `WADV` to 00**, which is one product term on `vctrl` and is not
built — it is filed as §19 item 24 rather than assumed.

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

> ⚠ **The budget must be derived by phase, not as a sum** — a total-versus-total
> comparison cannot distinguish a path that closes from one that does not. Derived
> by phase below, the read closes at ÷12 with 46.9 ns to spare **only under
> §5.2.2's spare-first sub-slot ordering**; under the video-first ordering that
> §2.2's "video → CPU" priority reads as, it misses by 25.1 ns. The phase table
> also charges the **15 ns the map SRAM adds** to physical A13–A19 (§6.3.1): the
> address on the backplane is the translation of what the CPU emitted, not the
> thing itself.

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

`VSTAT.VBL` plus an enable bit in `CTRL`, driving `/IRQ` open-drain. **Three
macrocells, not one**: the OE idiom below ties the macrocell's data to a constant,
so the pending flag is a second macrocell, and it has to be set by an edge rather
than a level or it re-arms under its own handler, which is a third (§19 item 8's
fit is where the three were counted). This is the system tick: 70.09 Hz in the
primary mode, **59.94 Hz** (not 60.0 — §6.2) in the 640×240 mode — and note that a NitrOS-9 tick derived
from vertical blank is *inherently* tear-free for double-buffer flips.

**Two requirements that are easy to miss.**

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

**Counting HSYNC gives you a line *count*, not a line *number*** — one signal is
not enough: a counter of HSYNC pulses has no origin. Something must tell the CPU
where the frame starts, or line 37 is 37 lines after whenever the timer happened to
be started.

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
| `+$0B`–`$0D` | — | | reserved — there is **no `LIST` register**: the engine shares `WPTR`, so a list is started by loading `+$08`–`$0A` (§10.3.1) | — |
| `+$0E` | `BCTRL` | b0 `GO` | list engine control — writing b0 starts the walk from `WPTR` (§10.3.1) | **new** |
| `+$0F` | `BSTAT` | b0 `LRUN` | list engine status — 1 while the engine owns `WPTR`; the bit a driver polls (§10.3.1) | **new** |
| `+$10` | `PIDX` | b7..0 | palette index, auto-increments after `PDATH` | — |
| `+$11` | `PDATL` | b7..0 | palette entry `GGGBBBBB` | — |
| `+$12` | `PDATH` | b7..0 | palette entry `RRRRRGGG`; write commits | — |
| `+$13` | `VSTAT` | b7 `SPANBUSY`, b6 `VBLANK`, b5 `HBLANK`, b0 IRQ pending | **read** through the `'244` of §12.1, not the register file; write clears IRQ | extended |
| `+$14` | `WADV` | b1..0 | pointer advance: 00 continue, **01 next row same column** (§7.2), 10 vertical (advance by stride) | **new** |
| `+$15` | `VDATA` | b7..0 | **read or write** VRAM byte at `WPTR`, post-increment | **new** (§11) |
| `+$16` | — | | reserved — there is **no `BORDER` register** (§9.3): VGA timing has no overscan, the porches must be black for the back-porch clamp, and the `'153` pixel mux has no spare input for a border index | — |
| `+$17`–`$1F` | — | | reserved (`TILEBASE`/`FONTBASE` and map base at `+$17`–`$19`, §6.4; `WPTR` column shadow, §7.2, is written implicitly) | |

**There is no `BANK` register** (§6.3) and **no `MODE` register** — there is no
stock mode to select. `VMODE` is two bits; `CHAR` holds the third. Sync polarity is
**not** a register bit — it follows `VMODE0`, since §12's 70 Hz codes are exactly
the positive-H ones (§10.1.6.1). The window is **32 bytes**, so
`TILEBASE`/`FONTBASE`/map base sit at `+$17`–`+$19`; ⚠ **`FONTBASE` at `+$18` is
reserved rather than used** — §6.4.3's Variant B is not built.

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

**The card is 27 ICs: 2 CPLDs, 1 GAL, 4 SRAMs and 20 packages of 74-series** —
against colormin's 39 (35). (The GAL-build table this section used to carry — 41 ICs,
10 × `GAL22V10` — and the re-tallies that led here are archived in
[history.md](history.md).)

| Qty | Part | Role | vs colormin |
|---|---|---|---|
| **2** | **AS6C8016-55 (512K×16)** | framebuffer, **2 MB**, 4-way interleave as **2 parts × 2 bytes** — §14.2 | **−2** |
| 4 | 74AHCT574 | fetch read latches — clocked **per-chip, mid-slot** (§5.2.2) | = |
| **4** | **74AHCT153** | **4:1 pixel mux — assumed, not fallback (§6.1)** | +4 |
| 1 | 74AHCT574 | palette index latch | = |
| **1** | **IS61C6416AL-12 (64K×16)** | palette LUT, 256 × 16 b — **one ×16 part holds both bytes** (§14.2) | **−1** |
| **2** | **74AHCT273** | **post-LUT output register — `/MR` is blank-to-black (§9.2)** | = (was `'574`) |
| 1 | 74HC593 | `PIDX` counter (sourcing flag, §9) | = |
| 1 | `ATF1508AS-15JC84`, PLCC-84 | **`vaddr`** — scan address, `WPTR`/span pointer, tile/list address sources. **61 of 64 I/O, 109 of 128 cells** (`hardware/gal/cpld/vaddr.fit`) | |
| 1 | `ATF1508AS-15JC84`, PLCC-84 | **`vctrl`** — sync (§6.2.1's polarity, VBL IRQ), sequencer, span control, the spare-access arbiter (§10.1.6.3), `CTRL`, `SPANLEN`, span-mask handling. **64 of 64 I/O, 121 of 128 cells** (`hardware/gal/cpld/vctrl.fit`) | |
| 1 | GAL22V10-15 | **`rfa`** — the register-file address (§10.1.6.3), which is what bought `vctrl` its fourteen pins back | |
| 1 | 74HC574 | posted-write **data** latch | = |
| **3** | **74HC574** | **posted-write address + control latches — 19 address + VRAMSEL + R/W + `WMODE[1:0]` = 23 bits (§3.1.1)** | **+3** |
| 1 | 32K×8 20 ns | register file | = |
| 1 | 74HC245 | register + VRAM read-back | = |
| **1** | **74HC574** | **VRAM read latch (§11)** | **+1** |
| **1** | **74HC244** | **`VSTAT` live-bit driver (§12.1)** | **+1** |
| 1 | 74HC244 | clock / load fan-out, **plus HSYNC/VSYNC out to the backplane (§12.2)** | = |
| **27** | | **23 if the tri-state pixel bus closes and the four `'153` come out** | **colormin: 39 (35)** |
| — | 3 × NPN (β ≥ 300) + 1 × diode + 9 R | VGA drive stage, `V_be`-referenced (§9.1) | **new** |
| — | 3 × R-2R SIP, 1 kΩ/2 kΩ | 5/6/5 ladders (§9.1 sets the value) | = (value specified) |

The master oscillator is **not** on this list: it is on the motherboard (§5.1) — a
card that supplies E is a card whose removal stops the CPU, and §18 brings the bus up
before the card exists. `CTRL`'s `'273`, the `SPANLEN` `'161` pair and the `'165`
span-mask serialiser went into the CPLDs (§10.1.6); the `VSTAT` `'244` and the
posted-write address `'574`s did not, because pins, not macrocells, are what the
CPLDs are short of (§10.1.6.3).

### 14.1 The count, derived

**27, reconciled 2026-09-08** — from the GAL build's 41 (archived in
[history.md](history.md)):

| | Δ | |
|---|---|---|
| GAL build | **41** | |
| − the ten `GAL22V10` | **−10** | sync ×3, scan ×2, `WPTR` ×2, sequencer ×2, arbiter ×1 |
| + 2 × `ATF1508AS-15JC84`, PLCC-84 | **+2** | `vaddr` and `vctrl` — §10.1.6 |
| − §10.1.6's absorptions | **−4** | `CTRL`'s `'273`, the `SPANLEN` `'161` pair, the `'165` span-mask serialiser |
| + 1 × `GAL22V10`, `rfa` | **+1** | §10.1.6.3 — the register-file address, which bought fourteen pins and is why the arbiter could come back inside `vctrl` at no package cost |
| **− 3 SRAM** | **−3** | **§14.2** — two ×16 parts feed the dot clock where four ×8 did, and one holds the whole 16-bit palette |
| **= the build** | **27** | **23 if the tri-state pixel bus closes and the four `'153` come out** |

> **The `VSTAT` `'244` (§12.1) survives the CPLD**, which is not obvious — an
> `ATF1508AS` has per-macrocell three-state with a product-term enable, so §12.1's
> reason for rejecting the OE idiom evaporates. **Pins are why it stays**: driving
> `D0`–`D7` from `vctrl` needs eight it does not have (§10.1.6.3). The same argument
> keeps the three posted-write address `'574`s: 23 bits of latch is 23 pins, and
> `vaddr` has two spare.

**Power.** The programmable logic is **two `ATF1508AS` at ~100–120 mA each with
reduced-power mode on the slow macrocells, plus one `GAL22V10` at 70–90 mA** — call
it **270–330 mA** — and §14.2's SRAM consolidation took ~250 mA off the memories.
The card lands at **~0.5–0.85 A, 0.65 A nominal, specify for 1 A** (the full
arithmetic is in the power table below).

**Area.** Two PLCC-84 sockets are ~22 cm² and the `rfa` GAL ~2.6, against the ten
DIP-24 `GAL22V10`s' ~26 — a wash; the deleted packages are the real saving. The
card's 27 ICs of courtyard is **99.1 cm²**, measured by `hardware/place` rather than
estimated.
⚠ **If the tri-state pixel bus closes (§19 item 2) the four `'153` go too**, and the
card is **23 ICs**, which is where the slack comes back.

### 14.2 ⭐ The seven SRAMs become four, and the broadcast write falls out of it

**2026-09-08, after checking pricing and stock rather than guessing.** The GAL build
carried **seven** SRAMs — four framebuffer, two palette LUT, one register file — and
two of those counts were not capacity. They were **width**.

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
| ⭐ **The card gets shorter** | 137.7 cm² of courtyard becomes **99.1**, and `hardware/place` puts it on an **18 cm** board instead of 24 — the same length as the audio card. Three DIP-32/28 out, three TSOP-44 in; the arbiter GAL went too (§10.1.6.3) |
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
list went (the motherboard's own full census — DRAM control, buffers, SIMM sockets —
is `hardware/ram.md` §6.5, at **14 ICs**):

| Qty | Part | Role |
|---|---|---|
| 1 | 25.175 MHz oscillator | **system master** (§5.1) — feeds the E/Q divider *and* the backplane |
| 1 | GAL22V10 | ÷12 / ÷8 E and Q generation, with the **divisor-dependent Q tap** (§5.1) and the whole-E-period `/WAIT` (§3.3) |
| 5 | §6.3.1's MMU | SRAM, `'574`, GAL, `'245` isolation, `'157` address mux |

**Power:**

| Group | Count | Each | Total |
|---|---|---|---|
| **ATF1508AS** at 25.175 MHz, reduced-power on the slow macrocells | 2 | ~100–120 mA | **~200–240 mA** |
| GAL22V10-15 (`rfa`) | 1 | 70–90 mA | 70–90 mA |
| **AS6C8016-55** framebuffer | 2 | **30 mA typ** | **~60 mA** — §14.2 |
| **IS61C6416AL-12** LUT (dot rate) | 1 | **~35 mA typ** | **~35 mA** — §14.2 |
| 32K×8 20 ns register file (bus rate) | 1 | 10–30 mA | 10–30 mA |
| AHCT at 25.175 MHz (fetch latches, `'153`, index, post-LUT) | 11 | 9–22 mA | 100–240 mA |
| HC at bus rate (posted-write ×4, `'245`, read latch, `'244` ×2, `'593`) | 9 | 2–6 mA | 20–55 mA |
| Analog drive stage (§9.1) | 3 ch | 9.3 mA peak + bias | 30–45 mA |
| | | **Total** | **~0.5–0.85 A** |

**Call it 0.65 A nominal and specify for 1 A.** The CPLD figures are from
`reference/datasheets/ATF1508AS.pdf`:

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

**Two consequences.** At 0.65 A a linear 7805 dropping 7 V is **4.6 W**, which a
TO-220 on a small clip-on heatsink carries comfortably — the switching pre-regulator
is unnecessary. **The slot power pins do not move**: 0.65 A is still over a single
0.5 A-class pin, so §17's multiple parallel power and ground pins stand. Measuring
card current stays §19 item 10, but it is a *verification*, not a discovery.

**Area.** 27 ICs of courtyard is **99.1 cm²**, and the card fits an **18 cm**
Apple-II-length board rather than the 24 cm it needed at 31 — §14.2 took three
DIP-32/28 SRAMs off it and put back three TSOP-44 (`hardware/place`, measured rather
than estimated; colormin is ~140 cm² on a 160 cm² Eurocard). The blitter is still a
piggyback. If the tri-state pixel bus closes at 39.7 ns (§19 item 2) the four `'153`
come out and the card shortens again; that bench item is an *area* item as well as a
BOM item.

## 15. Period audit

| Element | Introduced | Verdict |
|---|---|---|
| VGA, 25.175 MHz, 640×400@70 | **1987** (IBM PS/2) | period-exact; the *standard* clock, not an approximation |
| HD63C09E | 1988 | the machine's premise |
| GAL22V10 | 1986 | period; PAL16L8 is 1978 |
| `ATF1508AS` CPLD ×2 (§10.1.6) | CPLDs as an architecture are **1988** (MAX 5000 — §10.1.2); the `ATF1508AS` itself is a later part in that class | admitted by the machine's programmable-logic rule (root `README.md`) — the period argument is the architecture's date, not the part number's |
| 74AHCT | ~1990 | **the newest 74-series family on the card.** 74F is the period-honest substitute on the dot path |
| **AS6C8016 (512K×16)** | **8 Mbit** SRAMs **~1995** | ⚠ **§14.2 gives up the 1989 plausibility**, and knowingly: an 8 Mbit ×16 part in TSOP is mid-90s silicon. The 1989 build is the four `AS6C1008`, and it still works — this is a packaging choice, not a capability one |
| 20 ns 32K×8 SRAM | ~1988 | period |
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

**The card as an architecture places at 1989–1990**, driven by the 1 Mbit-class SRAM
design and the AHCT dot path — a coherent date: a 6309 machine with a VGA card,
512 KB, and NitrOS-9 Level 2 is exactly what an ambitious CoCo owner was building in
1990. §14.2's ×16 packaging choice steps outside that date knowingly, per its row
above.

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
5. **The MMU went outside** — to the motherboard, to keep one 48-pin SKU across both
   machines — so it costs **5 ICs** (§6.3.1), and GIME register compatibility was
   priced at an hour of NitrOS-9 patching rather than weeks. This is the one item on
   this list the machine chose not to take as originally offered.
6. **Raster interrupts cost one pin** (§12.2), and are more flexible than the
   hardware they replace.
7. **`TFM` exists** (§10.2).
8. **A real HD63C09E is *not* currently a valid part for the socket** — a property
   the clock-slaved design (§5.3) was originally argued on, so it is worth being
   precise about what broke and what would restore it.

   `docs/machine.md` resolves the machine's boot problem (§6.3.3) by having the
   **CPU module serve the vector page and an 8 KB shadow ROM from its own STM32
   flash, without a bus cycle** (§7.2 there). A real HD63C09E dropped into that
   socket fetches `$FFFE`–`$FFFF` from the backplane, where nothing answers: the
   silicon A/B reference does not boot. It boots again **only if the recorded
   alternative is taken** — an 8 KB EPROM plus decode on the motherboard, with an
   explicit vector/ROM carve-out from the I/O page (2 ICs, no CPU divergence). That
   is a live option, recorded here so it stays priced.

   A second, smaller qualification, unrelated to boot: at **÷8** the 317.8 ns bus
   cycle is below the HD63C09E's **333 ns `t_cyc` minimum**, so the A/B reference
   cannot be captured in fast-E mode with a rated part even with a ROM present
   (§11). At the specified ÷12 rate, 476.7 ns, it is comfortable.

   What survives untouched is everything the property is *used* for at ÷12 with a
   motherboard ROM: clock-slaving (§5.3), the Q-lead specification (§5.1) and the
   `/WAIT` discipline (§3.3) are all written so that real silicon works. The
   obstacle is one decode, not the timing.

---

## 17. Backplane and the sound card

Brief, because it is not the video question — but the backplane spec has to be
frozen before the video card is laid out, and the sound card is the other consumer.

> **The sound card has its own document: [`audio.md`](../../audio/docs/audio.md)** — a
> 4-channel PCM card modelled on the Amiga's Paula, **29 ICs**, whose acceptance test
> is playing existing OCS tracker modules unmodified, with the loader and
> replayer that do that in [`modplayer.md`](../../audio/docs/modplayer.md). **It supersedes this
> section's original Ensoniq 5503 DOC assumption**; the bullets below are what
> that design actually asks of the backplane.

- **Adopt backplane.md's slot model**, retargeted: **`/IOSEL` as a window strobe
  common to every slot** — not colormin's geographic per-slot decode, because this
  machine's windows are function-sized and all different, which no position decode
  can produce ([`machine.md`](../../docs/machine.md) §2 is the owning document).
  `/WAIT` open-drain (a **wait state** — E held low for whole E periods, §3.3),
  `/IRQ` **and** `/FIRQ` open-drain (backplane.md reserves only `/IRQ`; NitrOS-9 uses
  both, and audio wants one of its own), `/NMI`, `/RESET`.
- **The `/IOSEL` window is `$FF00`–`$FF7F`** — widened 2026-09-08 once
  `$FF40`–`$FF5F` filled to the last four bytes. The card windows inside it:

  | Range | Size | Owner |
  |---|---|---|
  | `$FF40`–`$FF4F` | 16 B | audio — `audio/docs/audio.md` §9.1 |
  | `$FF50`–`$FF53` | 4 B | PS/2 keyboard + mouse — `io/ps2/docs/ps2.md` §3.2 |
  | `$FF54`–`$FF57` | 4 B | RS-232 serial — `io/serial/docs/serial.md` §7.1 |
  | `$FF58`–`$FF5B` | 4 B | SD card storage — `storage/docs/sdcard.md` §6.1 |
  | `$FF5C`–`$FF5F` | 4 B | network — `net/docs/net.md` §5.1 |
  | `$FF60`–`$FF7F` | 32 B | video — §13 |

  `docs/machine.md` §3 is the owning table; this one is a copy and defers to it.
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
  honest card current is ~0.5–0.85 A for video alone, and `docs/machine.md` has to sum
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
| `/IOSEL` | motherboard → **all** slots | **the `$FF00`–`$FF7F` window strobe, common to every slot**; the card decodes **`A0`–`A6`** against a jumpered base — [`machine.md`](../../docs/machine.md) §2, §5 item 1 A. `hardware/gal/vctrl.pld`'s `REGSEL` is `IOSEL & A6 & A5` |
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
| 2 | **Fit the card's logic** (minimal256.md §11 item 11) | **done** — sync, scan address, `WPTR`, sequencer and arbiter are all fitted, checked at the fuse level (`hardware/gal/`), and consolidated into the two CPLDs plus `rfa` (§10.1.6, §14) |
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
4. **The MMU's location — closed, §6.3.1: on the motherboard, 5 ICs.** The deciding
   argument was one 48-pin SKU across the CoCo 3 drop-in
   and this machine, not the address path. What it leaves open is the register set
   itself (`machine.md` §5 item 3),
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
8. **Logic fit — closed.** The sync section was fitted 2026-09-06
   ([`hardware/gal/sync.jedec.ts`](../../hardware/gal/sync.jedec.ts), fuse-level
   checked over whole frames in both families by `npm run check:sync`) and the
   scan-address pair the same day
   ([`hardware/gal/scan.jedec.ts`](../../hardware/gal/scan.jedec.ts), 17 of 20 with
   three spare, `npm run check:scan`); both now live inside the CPLDs of §10.1.6.
   (The GAL-partition fit tables and the escape analysis this item used to carry are
   archived in [history.md](history.md).) Three rules from that work stand:

   - **The scan generators emit a *chip* address of 17 bits, not a *byte* address of
     19.** `A1:A0` are the mux phase and never leave the `'153`s; and the 1024 × 512
     torus means the column and row counters are free binary rollovers of their own
     width with **no inter-package carry**. `check:scan` asserts both directly.
   - **A counter has to stay on the same package as the things that decode it** —
     pins, not macrocells, are the binding half of the constraint. (Moving the slot
     counter to a `'393` freed eight macrocells and needed 22 input pins on a part
     with 16.)
   - **Bit order is not pin order** for any wide counter on a 22V10: a loadable
     counter bit *i* costs *i* + 3 product terms and a plain enabled one *i* + 7 —
     a rising staircase against the package's palindrome of
     8, 10, 12, 14, 16, 16, 14, 12, 10, 8 — so the only assignment that fits pairs
     the two sorted sequences, interleaving the bits across the package. The fitter
     refuses the naive order rather than letting it through.
9. **`74HC593` availability** (§9). **carried.**
10. **Measure card current** with the four SRAMs, two CPLDs and one GAL against
    §14's **0.5–0.85 A** estimate. **carried, and no longer a discovery**:
    §14 and §14.2 do the arithmetic, so this is verification. ⚠ **§14.2's three
    TSOP-44 parts are the ones to measure first** — their 30 mA and 175 mW typicals
    are *typical*, and the whole 205–405 mA saving rests on them. The regulator
    topology and the slot's power-pin count depend on the answer (§17).
11. **Validate 640×400@70 and 640×480@60 on the actual monitors** — CRT, LCD and
    scaler. 70 Hz 400-line is a DOS text mode and should be universal; confirm it.
    **carried, retimed.**
12. **Span-wrap behaviour at the 1024-byte row boundary — decided 2026-09-06: wrap
    in row.** Not chosen by taste; the fit chose it, and the rest of
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
15. **Tile-mode fit — closed by the CPLD build.** §6.4.2's Variant A is v1 hardware
    (§10.1.5) and its logic exists: the map-byte latch, `TILEBASE`/`MAPBASE`
    registers and `MAPSEL` cadence are written in
    [`video.parts.ts`](../../hardware/gal/video.parts.ts), the
    aligned-tile "OR = ADD" address identity is asserted over all 524,288 field
    combinations by `tile.check.ts`, and both CPLDs fit with it in (§10.1.6, §14).
    What remains on the fit is bench verification with everything else.
    (The item's earlier fit questions and the Variant-B-era pricing are archived in
    [history.md](history.md).)

    **(c) The fetch cadence — closed 2026-09-08.** It was a placeholder: `TC0..TC2`
    counted on `SLOTTICK` and split at `TC2`, and since a slot is four dots and a
    cell is eight, that period was **four cells** — 16 tile bytes fetched where 32
    are needed, one map byte latched where four are. Half a line's pixels had no
    data and three cells in four had no code. It had never been run.

    §6.4.9 is the sequence that replaced it, and
    [`cadence.check.ts`](../../hardware/gal/cadence.check.ts) runs a whole line
    against the fitted terms. What it cost: seven macrocells for the map's own
    column counter (`vaddr`, §6.4.9's one-cell lead), a `SPNREQ` gate and four
    `GMAP`/`GCPU` pairs on `vctrl`, and two more signals on `/WAIT`. `arbDesign`
    itself is untouched and still executable as a standalone `GAL22V10`.

    **(d) The vertical window — closed 2026-09-08.** (c) produced `FETCH` and
    `HLOAD` because the map fetch needed a fetch window to sit against; `ROWADV`
    and `VLOAD` were the other half, and without them the row counter neither
    loaded `VSCROLL` nor stepped, **in either mode**. §8.1 is the answer and it
    cost two macrocells: `VLOAD` turned out to be `VBLANK` under a second name,
    and the pin `ROWADV` needed came from `CE` = `SLOTTICK`, a third identity of
    the same kind. §6.2's line doubling is one term inside `ROWADV`, and
    `check:cadence` runs a frame in each `VMODE`.

    ⚠ **What is left of the decode half is not the display's.** `LDA`, `LDB`,
    `LDC`, `WSTB` and `VSTATWR` are register-file strobes (`census.ts`) and have
    nothing to do with scanning; §18's bench brings them up with the CPU
    interface.
16. **The tile fetch's fine-scroll behaviour — implemented, and it is
    free.** A slot is four pixels and a cell is eight, so the three bits
    of intra-cell offset are `{SA2, mux phase}` — the column counter's own low bit
    and the two bits §8 already preloads. §8 loads that counter from `HSCROLL[9:2]`
    and the phase from `HSCROLL[1:0]`, so **both halves are already scrolled** and
    the concatenation needs no adder and no offset register.

    What it does need is a **cadence** guarantee, not an address one: the map byte
    for a cell must be held before that cell's first pixel is emitted, so when a line
    starts mid-cell the map fetch leads by one cell rather than one slot. That is
    `MAPSEL` in [`video.parts.ts`](../../hardware/gal/video.parts.ts).
17. **The Variant-B serialiser bench — closed 2026-09-08: Variant B is not built**
    (§6.4.3, §10.1.6.2). The serialiser on §6.1's 11.7 ns margin was its own risk
    and it went with it; the span-mask serialisation itself lives inside the CPLDs
    (§10.1.6, §14).
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
20. **§5.2.1's arbiter — closed 2026-09-06.** Fitted in
    [`hardware/gal/access.jedec.ts`](../../hardware/gal/access.jedec.ts) and checked
    over all 128 input combinations (now inside `vctrl` — §10.1.6.3):

    - **CPU and span on the same chip** — the span writer yields. ✓
    - **CPU absent entirely** — the span writer takes the chip rather than idling
      the slot. ✓
    - **Never both** — no chip is ever granted to two drivers in one slot, asserted
      separately from the model because it is the failure this part exists to
      prevent. ✓
    - The **`/WAIT` case** is not the arbiter's: a span *holding* the chip the CPU
      wants is `SPANBUSY · VRAMSEL · /IOPAGE` on the `/WAIT` pin (§3.3, §12.1's
      open-drain idiom), and the arbiter is purely combinational grant logic with no
      state to be busy with. It stays open as **item 21**, where it belongs.
21. **Decide `/WAIT`'s granularity with the motherboard** (§3.3): whole E periods is
    what this card's static phase needs, and it is the motherboard's divider that has
    to implement it. Confirm that a `/WAIT`-extended cycle re-enters the correct
    sub-slot phase — this is item 6 with the answer now specified rather than open.
23. **The phase-dependent `FCLK` equations, and the sequencer's other half —
    closed 2026-09-07.** Both halves are written, fitted and checked.

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

    **The pin cost was later paid by a GAL, not a bigger package.** The decode's
    I/O load briefly pushed `vctrl` toward a TQFP-100; splitting the register-file
    *address* onto its own `GAL22V10` (`rfa` — `hardware/gal/rfa.pld`) bought
    fourteen pins back, and both CPLDs are PLCC-84: `vctrl` at 64 of 64 I/O and
    121 of 128 cells, `vaddr` at 61 of 64 and 109 of 128 (§10.1.6.3, §14, the
    `hardware/gal/cpld/*.fit` files).

22. **Verify the sync-polarity table against the actual monitors** (§6.2.1), CRT, LCD
    and scaler, in *both* `VMODE` families. Polarity is how the monitor picks the
    vertical format; getting it right on paper and wrong at the connector produces a
    correctly-timed picture that is the wrong size, which is the failure mode most
    likely to be misdiagnosed as a timing bug. Folds into item 11.
24. **⚠ `WADV` and the list engine's walk.** §10.3.1's reload rule is written, and this
    is the one thing it could not settle. §13's `+$14` `WADV` changes what `WPTR` does on
    increment — 01 is next-row-same-column, 10 advances by the stride — and the engine's
    own walk is a plain +1 through the descriptor list. **A driver that leaves `WADV` in
    vertical mode and then starts a list gets an engine that steps by 1,024.**

    **The fix is one product term**: `BCTRL.GO` forces `WADV` to `00`. It is not built,
    and it is cheap enough that the only reason to file it rather than do it is that
    `vctrl` should be fitted once with it rather than twice. **`vctrl` has 2 spare
    pins and 31 spare macrocells**, so this is a macrocell question and not a pin one.

    The alternative — make it software's rule, a fourth line in §10.3.1 — is free and
    worse: it is a rule that fires only in the combination of two features neither of
    which is obviously related to the other, which is the shape of bug that survives
    into a released driver.
25. **JTAG — closed 2026-09-08, in the other direction.** Both parts are programmed
    **in circuit**: `vaddr` at 61 of 64 and `vctrl` at 64 of 64 with the four JTAG
    pins reserved, both fitting (§10.1.6.3). The item existed because the pair was at
    64 and 62 of 64; §6.4.1's corrected cell address returned three pins on each by
    stopping `vctrl` exporting a line counter that was the wrong one to begin with.

    §14.2's two ×16 framebuffer parts would still free six more output pins by making
    the arbiter 2 grants instead of 8, landing `vctrl` near 53 of 64 — worth having,
    no longer needed for this. **Confirm it when §5.2 is rewritten** rather than
    assuming it: the estimate that said `rfa` would free five pins freed fourteen,
    and estimates on this card have been wrong in both directions.

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
