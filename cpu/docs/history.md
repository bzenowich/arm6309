# CPU — archived history

Superseded material removed from [`plan.md`](plan.md) and [`../README.md`](../README.md),
organized by the spec section it came from. The spec files describe only the present
design; this file is the record of what they said before and why it changed. Nothing here
is current.

---

## §4.5 / §3.2 / Phase 6b / §10 items 7–8 — the shadow ROM and vector page, retired 2026-09-08

**The whole mechanism moved off this module** when `docs/machine.md` §7.2 put a 1 MB ROM
on the motherboard. The alternative `plan.md` §4.5 had itself recorded — *"an 8 KB EPROM
plus decode on the motherboard — 2 ICs, no CPU divergence"* — is the one the machine
took, at three packages and a megabyte, because `hardware/ram.md` §5.2's 32 MB re-carve
gave the physical map somewhere to put it.

### What §4.5 specified

> **Machine-wide decision D1.** Without this mechanism the homebrew machine cannot boot:
> no ROM chip exists anywhere in its physical map, and the reset vector at `$FFFE` lands
> inside the I/O page — which overrides MMU translation by design — so nothing decodes
> there. The resolution puts the boot ROM **in this module**, served from STM32 flash with
> no bus cycle at all, because that is the one place in the machine that already has
> non-volatile storage and an address decoder.
>
> #### 4.5.1 What the module serves
>
> | Logical range | Served from | When |
> |---|---|---|
> | `$E000`–`$FEFF` | STM32 flash, **shadow ROM** | from reset until the OS clears the disable bit |
> | `$FF00`–`$FFBF` | **nothing — decodes normally** | always: cards and the MMU answer here |
> | `$FFC0`–`$FFEF` | STM32 flash, shadow ROM | same as `$E000`–`$FEFF` |
> | `$FFF0`–`$FFFF` | 16-byte internal **vector RAM** | **always**, disable bit or not |
>
> Three rules, and the second is the one that is easy to get wrong:
>
> 1. **A shadowed read never becomes a bus cycle.** The emulator resolves the address
>    internally and supplies the byte from flash. Externally the cycle still happens — E,
>    Q and the address are the host's, and cycle accuracy is unaffected — but the module
>    ignores `D0..D7` and drives `BUS_OE`/`R/W` as it would for any read.
> 2. **`$FF00`–`$FFBF` is carved out and must keep decoding normally.** The boot code has
>    to talk to the MMU, the video card and storage while it is running. A shadow that
>    covered the whole of `$FF00`–`$FFFF` would work exactly until the first register
>    access.
> 3. **Vector service is unconditional.** `$FFF0`–`$FFFF` comes from the vector RAM
>    whether the shadow ROM is enabled or not, which is what lets the OS retarget the
>    vectors after it has switched the shadow off. The RAM is initialised from flash at
>    reset to point into the shadow ROM, so the reset vector is valid on the first fetch.
>
> #### 4.5.2 Control, and turning the whole thing off
>
> - **Disable bit** — one bit in the MMU control window. Setting it retires
>   `$E000`–`$FEFF` and `$FFC0`–`$FFEF`, freeing that logical space for RAM once NitrOS-9
>   is up. It is a one-way switch per reset by design: nothing re-enables the shadow
>   except a reset, so a wild store cannot bring the ROM back over live RAM.
> - **Vector RAM is writable through the MMU window**, 16 bytes, so the OS installs its
>   own vectors and the shadow ROM's are only the bootstrap set.
> - **Machine-mode gating.** On the **CoCo 3 and the Dragon 64 the entire mechanism is
>   off**. Mode is read once at reset from the **`PF1` strap** (pulled up = drop-in, tied
>   low on the homebrew motherboard), which keeps one firmware image serving all three
>   machines.
>
> > ⚠ **Consequence for the drop-in claim.** `video/docs/graphics.md` §16.8's "you can
> > drop a real HD63C09E into the homebrew machine" property **does not hold** with the
> > shadow ROM in the CPU: a real 6309 has no flash and the machine has no boot ROM
> > without it.
>
> #### 4.5.3 Cost
>
> | Item | Cost |
> |---|---|
> | Shadow ROM image | **~8 KB of the 128 KB** internal flash (6.3 %) |
> | Vector RAM | 16 bytes of SRAM, plus 16 bytes of flash for the reset image |
> | Per-cycle cost | one range test on the address the microcode is about to drive |
> | Pins | one, `PF1`, the last spare |
>
> The per-cycle cost is the term to watch — it lands in the microcode step measured in
> §3.3(d), not in the `t_AD` path, because the decision "does this read come from flash?"
> is made when the address is *formed*, one step before it is driven.

### What went with it

- **`PF1`** was *"§4.5 machine-mode strap — the last pin"* in §3.2's pin table, and the
  budget stood at **39 of 39, none spare** on both target columns. It is **38 of 39** now
  and the pin is unconnected.
- **Phase 6b** — *"Shadow boot ROM and vector page (3–5 days, homebrew target only)"* —
  is deleted, not renumbered.
- **§10 item 7**, *"`PF1` strap, or a build-time flag and two images?"*, is closed by not
  existing: the retirement gives both halves of what the question was trading between,
  because the image is identical on all three machines with no strap and no flag.
- **§10 item 8**, *"§4.5 or the EPROM alternative?"*, is decided in favour of the EPROM
  alternative.
- **§10's risk table** carried *"§4.5 shadow ROM competes for microcode budget — Low"*.
  There is no range test to budget for.
- **`README.md`'s "Serving the boot ROM (homebrew machine only)" section** described the
  same mechanism and ended: *"with this mechanism in the CPU, a real HD63C09E is not a
  drop-in for the homebrew machine"*. It is one again.

### Why it was right and then wasn't

**The reasoning was never wrong; one of its premises expired.** §4.5 opens on *"no ROM
chip exists anywhere in its physical map"*, and that was a true statement about a 1 MB
map in which `graphics.md` §6.3 had already spent every byte — 512 KB of system RAM at
`A19 = 0` and 512 KB of VRAM at `A19 = 1`. `machine.md` §5 item 1 option D doubled the
map on 2026-09-08 and `ram.md` §5.2 re-carved it to 32 MB hours later; **the sentence
stopped being true the same day it was still being cited.**

The second thing that changed is what the ROM is *for*. §4.5's job was to get the first
instruction executed, and 8 KB is enough for that. A megabyte holds the NitrOS-9
distribution as a read-only ROM disk, which makes the machine bootable with no SD card,
no serial cable and no host — a different capability, not a bigger version of the same
one.

The third is that **the vector RAM's headline benefit turned out to be a divergence.** A
writable vector page *"so the OS can retarget the vectors"* is not what a CoCo has; a
CoCo has ROM vectors pointing at a fixed RAM jump table, and NitrOS-9 is written against
that. Putting the vectors in ROM removed a divergence-ledger entry instead of shrinking
one.

---

## Header — revision trail (2026-08-19 → 2026-09-04)

The plan's date line recorded its own revisions:

> **Date:** 2026-08-19, revised 2026-08-27 (real 6309E timing; §3.6 latch; §3.7 MCU review),
> 2026-08-28 (core clock committed at 170 MHz; 200 MHz overclock rejected — §3.4(4)),
> 2026-09-04 (design review: package corrected to UFQFPN48 — §3.2; §3.6 glue redrawn;
> the homebrew machine's real E rates costed — §3.3(e); shadow boot ROM specified — §4.5)

Replaced by a single date; the individual revisions are the entries below.

## §0 / §1 — 5 MHz target withdrawn (2026-08-27)

Early revisions carried 5 MHz as a stretch target. Withdrawn when the timing sources
were verified:

> The 5 MHz target is **withdrawn**. No 6309E speed grade above HD63C09E exists, and the
> figure traced to an unsourced range rather than a datasheet (§3.3).

The §3.3 footnote recorded the provenance:

> The "5 MHz" figure that appeared in earlier revisions of this plan traces to an
> unsourced family-wide range in Wikipedia's 6309 infobox and is **not** supported by
> any datasheet.

Replaced by the plain statement that no speed grade above HD63C09E exists and 5 MHz is
not a target; 3 MHz (HD63C09E rated max) is the stretch target. The §8 risk row
"~~5 MHz stretch unreachable~~ — **Withdrawn**" was retired with it.

## §3.2 — package corrected: LQFP48 → UFQFPN48 (2026-09-04, review finding Cpu-C1)

The costliest correction in the document's history, caught before any board was drawn.
The marked block read:

> ⚠ **The package was wrong until 2026-09-04, and the pinout below did not exist on it.**
> Every revision of this document through 2026-08-28 committed to the **STM32G431CB*T*6,
> LQFP48**, and the budget line read "42, minus SWD and NRST = 39" for that package too.
> **It is 38 GPIO on LQFP48, not 42** (DS12589 Table 2: "38 in LQFP48, 42 in UFQFPN48";
> the LQFP48 pinout figure carries `PA0-15`, `PB0-15`, `PC13/14/15`, `PF0/1`, `PG10` and
> nothing else on port C). `PC4`, `PC6`, `PC10` and `PC11` are **not bonded out** on
> LQFP48 — and those four carry `BA`, `BS`, `UART_TX` and `UART_RX`.
>
> The real LQFP48 arithmetic: 38 − 2 (SWD) − 1 (NRST) = **35 usable**. The 33 mandatory
> CoCo 3 signals still fit, but the only spares are `PF0`/`PF1`, so on that package there
> is no `BA`, no `BS`, and no debug UART — and `gpio_init()` would have been configuring
> `GPIOC` registers for pins with no pads behind them, which fails silently. The error
> came from reading the family-wide pin list in `modm-devices` rather than the LQFP48
> bonding; "verified against modm-devices" was true and insufficient.
>
> **Fix (machine-wide decision D4): STM32G431CB*U*6, UFQFPN48.** Same die, same
> peripheral set, same 42 GPIO the tables assumed — so the pinout, `cpu/include/pinout.h`
> and the firmware are unchanged, and QFN soldering is the entire cost. The alternative,
> staying on LQFP48 and deleting `BA`/`BS`/UART from every table, was rejected: it costs
> the debug UART on a board that has never been brought up, for no saving.
>
> **The external-MMU decision survives unchanged, and is if anything reinforced.** The
> comparison below shows an in-CPU MMU needing all 39 pins on the 42-GPIO package; on the
> 35 usable pins of an LQFP48 it is not close to feasible. Nothing about
> `docs/machine.md` §5 item 6 depends on which 48-pin package is fitted.
>
> Caught in the 2026-09-04 design review (finding Cpu-C1), before any board was drawn.

§9 carried the matching parts-list note ("⚠ **Was `STM32G431CBT6` (LQFP48) until
2026-09-04.**"), the README a longer restatement, and `cpu/include/pinout.h` still
carries its own SUPERSEDED note in the header comment. §10 item 2's original answer
("**Answered — 48 pins, with 4 to spare. Answered again on 2026-09-04: it has to be the
UFQFPN48, not the LQFP48**") recorded the two-stage resolution.

Replaced by present-tense statements that the part is the **STM32G431CBU6, UFQFPN48**
(machine-wide decision D4) and that the two 48-pin packages are not interchangeable.

## §3.2 — pin budget: "38 of 39, one spare" became "39 of 39, none" (2026-09-04)

> ⚠ **This read "38 of 39, one spare" until 2026-09-04.** `PF1` was that spare, and §4.5's
> shadow ROM spends it on the machine-mode strap. The count is now exact on both targets —
> see the marked block under the three-machine table below.

Replaced by the plain totals: 39 of 39, with `PF1` carrying the §4.5 machine-mode strap.

## §3.2 — the three-machine table gained two rows (2026-09-04)

> ⚠ **This table gained two rows on 2026-09-04 and the budget went from comfortable to
> exactly full.** Both additions came from elsewhere:
>
> - **VSYNC.** `graphics.md` §12.2 counted only HSYNC, but counting HSYNC pulses yields a
>   line number *with no origin* — the raster-compare timer needs a frame reset too, and
>   resynchronising in the VBL handler jitters by interrupt-dispatch latency (1–6 lines).
>   The video card's fix pass made VSYNC a hardware input (`design-review.md` §Vid-m4).
> - **The `PF1` machine strap**, which §4.5's shadow ROM needs in order to keep the
>   "one firmware, three machines" property. It is the pin this document called spare.
>
> **Both target columns now stand at 39 of 39.** [...] **And the in-CPU MMU column no
> longer fits at all** — 41 pins against 39. It was already rejected on one-SKU grounds;
> it is now arithmetically impossible on this package, which retires the question rather
> than merely settling it.

Replaced by the same facts stated as present design (both columns exactly full; in-CPU
MMU 41 > 39).

## §3.3 — the address deadline was wrong twice (final form 2026-08-27)

> **Correction — this section has been wrong twice; this is the version backed by the
> right document.** Early revisions used the quarter cycle (E-fall to Q-rise) as the
> address deadline. That was wrong. The replacement used `reference/datasheets/MC6809E.pdf`,
> whose columns stop at the 2 MHz MC68B09E, and extrapolated `t_AD` to 3 MHz across speed
> grades as ≈0.21 × `t_cyc` ≈ 76 ns. **That was also wrong.** The authoritative source
> is now in the repo: `reference/datasheets/HD6309E_datasheet.pdf` p.3 gives AC
> characteristics for **HD63B09E and HD63C09E in adjacent columns**, and Hitachi holds
> `t_AD` at **110 ns for both grades**. The address deadline does *not* tighten at 3 MHz.

The extrapolation had the 3 MHz analysis wrong in both directions: it tightened the
address deadline that in fact stays at 110 ns, and it missed that `t_DSR` halves to
20 ns — the gate that actually breaks software sampling. "The picture at 3 MHz is the
opposite of what earlier revisions assumed", as the spec put it while the correction was
fresh. §10 item 3's original answer ("**Answered, twice**") recorded the same sequence.

Replaced by the HD6309E-datasheet-backed table and the statement that the datasheet is
the authoritative timing source.

## §3.3(d) — the whole E period was wrongly treated as emulator budget

> **Correction.** Earlier revisions said "at 1.79 MHz there are 95 core cycles per bus
> cycle, ~3–6× headroom", treating the whole period as available to the emulator. It is
> not.

Replaced by the timeline analysis: the CPU must be inside the sampling loop when E
falls, so only the pre-sampling portion is usable — 56 % spinning on the E pin, 75 %
spinning on the Q-fall capture flag.

## §3.3(d) — E-edge prediction, dismissed and then readmitted

> *Refinement now safe, not previously implemented:* an earlier revision dismissed
> predicting the E edge from `CCR2 + P/4 − margin` because the live 0.895 ↔ 1.79 MHz
> switch (§2.1) invalidates a prediction made from the last observed period. That
> dismissal was too quick.

The fix — predict with the fastest possible period, so a speed switch makes the
prediction early rather than late — stands in the spec as an unimplemented refinement.

## §3.3(e) — the homebrew machine's real E rates (added 2026-09-04)

The subsection opened "**Added 2026-09-04.**" It exists because the 2026-09-04 design
review costed the homebrew machine's actual rates (25.175 MHz ÷ 12 = 2.0979 MHz,
÷ 8 = 3.1469 MHz) against budgets that had only been run at the datasheet-grade 2.0 and
3.0 MHz — a ~5 % difference that cut fast-E's `TFM` margin from 9 to ~6 cycles and
revealed that no real 6309E is in spec at fast-E (317.8 ns < the C grade's 333 ns
`t_cyc` minimum), so no silicon A/B reference exists there. The content is present
design in §3.3(e).

## §3.4(4) / §5 — the 200 MHz overclock (rejected 2026-08-28)

§3.4 item 4 was headed "**~~Overclock the G4 to 200 MHz.~~ EVALUATED AND REJECTED
(2026-08-28)**", and §5's variant list carried "4. ~~(2) or (3) with the G4 overclocked
to 200 MHz.~~ **Dropped**". Before the rejection, overclocking to 180–200 MHz was a live
Phase 1 variant (the README listed it as "Variant 4 — overclock to 180–200 MHz"). The
full rejection analysis — the 344 MHz PLL VCO ceiling, the three simultaneous spec
violations, the thermal/V_DD/binning arguments — is retained in the spec as the
rationale for the committed 170 MHz core clock. The §8 risk row "~~Overclock to 200 MHz
fails silently and rarely~~ — **Closed — not taken**" was retired: the risk was retired
by declining the option.

## §3.5 — the `TT_a` inventory was incomplete (corrected 2026-09-04)

> **The recorded inventory was incomplete until 2026-09-04.** Earlier revisions listed
> `PA0..PA7`, `PB0..PB2` and `PB10`, omitting **`PB13`, `PB14` and `PC5`**, which Table
> 12 also gives as `TT_a`. On this pinout that means **six** of the sixteen address
> lines are 3.6 V pins (`A0`, `A1`, `A2`, `A10`, `A13`, `A14`), not four; `PC5` carries
> nothing here. The conclusion is unchanged and was never in doubt — buffers are
> mandatory either way — but §8's own instruction is "verify FT/FT_a in DS12589 before
> PCB", and a list that is wrong is not a verification. Corrected here and in
> `cpu/include/pinout.h`.

Replaced by the complete list, stated once.

## §3.5 — direct drive recommended, then ruled out; the '245 split into '574 + '541

An early revision recommended building v1 with the STM32 pins driving the bus directly,
treating 5 V tolerance as an open question:

> **Correction.** An earlier revision of this section recommended building v1
> direct-drive and treating 5 V tolerance as an open question. The datasheet answers it,
> and the answer is no.

DS12589 Table 12 lists `PA0`–`PA7` (the whole data bus) as `TT_a`, 3.6 V — destroyed by
the CoCo's 5 V TTL on every read — so buffers became architecturally mandatory. The
spec's `<details>` block records what direct drive would have bought on a 5 V-tolerant
part. A set of supporting bullets from the direct-drive era survived next to it until
this cleanup, describing benefits that do not exist in the buffered design:

> - Driving high, the STM32's ~10–25 Ω output easily dominates the 4.7 K pull-up; the
>   line sits near 3.3 V, comfortably above the 2.0 V `V_IH` of the LS parts downstream.
> - Driving low, it sinks ~1.1 mA per line from the pull-up. Trivial.
> - **`BUS_OE` disappears.** Tri-stating for `/HALT` becomes one write to `GPIOB->MODER`
>   — off the per-cycle critical path, and it frees a pin.
> - **Saves ~5 ns each way** of buffer propagation ≈ 1.7 core cycles per direction.
>   Against an 18.7-cycle deadline that is real money.
> - Fewer parts and less board area, which matters under the RF shield (§2.7).
> - Drive strength is a non-issue: the original 68B09E is HMOS with weak drive, and the
>   STM32 is stronger.

Separately, the data path was originally a single **74LVC245** transceiver; §3.6's latch
split it into a '574 (read) + '541 (write) pair. §10 item 3a's original answer form
("~~Are all bus pins 5 V-tolerant?~~ **Answered — no.**") is restated unstruck in the
spec.

## §3.6 — the glue was not buildable as drawn (corrected 2026-09-04, Cpu-M3)

The board-impact subsection read, in full:

> - `'574` `OE` ← `R/W` (drives `PA0..PA7` during reads)
> - `'541` `OE` ← `/R/W` (drives the bus during writes)
> - both still gated by `BUS_OE` for `/HALT` tri-stating (§2.2)
>
> Net **+1 package, ~+$0.30**, and one extra `OE` net derivable from the
> already-buffered `R/W`.

Four defects, found in the 2026-09-04 design review (Cpu-M3):

1. A `'574` is an **edge-triggered flip-flop that clocks on the RISING edge**; "clocked
   by E's falling edge" therefore needs `/E`, and **no inverter existed anywhere in the
   document or in §9**, where every part listed ('541, '574, '125) is non-inverting.
2. The two `OE` lines were **swapped**: `OE` on both parts is active LOW, so
   `'574 /OE ← R/W` disables the read latch during reads and `'541 /OE ← /R/W` disables
   the write buffer during writes — exactly inverted.
3. The `'574` has a **single** `/OE` covering all eight outputs, so "gated by `BUS_OE`
   as well" was not a wiring instruction but an OR gate that was not on the BOM. (The
   corrected design deliberately keeps the '574 out of the `BUS_OE` set instead.)
4. `/R/W` itself was a signal nobody generated.

Separately, the one `74LVC125` in §9 had **4 channels** against 7 control inputs plus
`R/W` out; through 2026-08-28 that §9 line read "74LVC125/AHCT125 (`R/W` + control)".
None of this changed the §3.6 conclusion — the latch was still right and still ~$0.30 —
but it was not buildable as drawn. The glue budget went from the ~5 packages the earlier
text implied to 7: +1 dual inverter, the '125 shrunk to a '1G125, +1 '541 for the
control inputs.

Replaced by the corrected drawing in §3.6 (now the schematic authority) and the
seven-package parts list in §9.

## §4.1 — the microstate mechanism, as originally specified (revised 2026-08-28)

The section originally specified two indirect calls per bus cycle and eagerly-computed
condition codes:

```c
typedef struct microstate {
    uint16_t (*addr)(cpu_t *);      /* address to drive this cycle       */
    uint8_t   rw;                   /* read or write                     */
    void    (*action)(cpu_t *);     /* register/ALU work for this cycle  */
    const struct microstate *next;  /* successor (may be patched)        */
} microstate_t;
```

`cpu/tools/microstate-probe/` measured it at **~80 core cycles per bus cycle — over
budget at every target rate, including 1.79 MHz.** The conceptual shape (one state per
bus cycle) survives; the mechanism was replaced by the three rules now in §4.1 (jump
table, lazy CC, AND-folded control lines). The 15–30 cycle estimate the budgets had been
carrying proved pessimistic for the tuned path (14 typical / 25 worst) and wildly
optimistic for the naive one.

## §4.5 — origin of the shadow boot ROM (2026-09-04, machine-wide decision D1)

The section was added as "**New requirement, 2026-09-04, machine-wide decision D1**",
after the design review found that the homebrew machine could not boot: no document
allocated a boot ROM, the reset vector at `$FFFE` lands inside the I/O page, and the
then-1 MB physical map had no room for a ROM (`docs/machine.md`, finding Sys-C1). The
mechanism is present design in §4.5; the physical map has since grown well past 1 MB
(`hardware/ram.md`), which changes nothing about D1.

## §5 — the pass gate was 18 before the bias analysis (2026-09-04, Cpu-M4)

The README (and by reference the plan) originally claimed the measurement was "slightly
conservative", on the grounds that the `DSB` before the timestamp errs in the safe
direction:

> The README used to claim that the `DSB` before the timestamp "errs in the safe
> direction". It does, by a couple of cycles — and three larger terms err the other way.

The 2026-09-04 review (Cpu-M4) found the three optimistic terms (TIM1 capture-path
resynchronisation ~2–3 cycles; store-retire vs pad-slew ~0.6; the absent bench buffers
~0.9 each way) and the gate was lowered from 18 to **14** (`SPIKE_TAD_CYCLES` in
`cpu/include/spike.h`). The bias analysis and the calibration path back to 18 are
present design in §5 and the README.

## §8 — closed risk rows

Rows retired from the risk table as their risks closed:

| Risk | Status | Resolution |
|---|---|---|
| Microcode step costs more than 15–30 cycles | **Largely closed** | Measured: 14 cy typical, 25 cy worst, against 34 available at 3 MHz (§3.3(d), `cpu/tools/microstate-probe/`). Residual coverage risk lives on in the lazy-CC and probe-coverage rows. |
| Overclock to 200 MHz fails silently and rarely | **Closed — not taken** | Core clock committed at 170 MHz (§3.4(4)); the risk was retired by declining the option, which bought no gate at any target rate. |
| Pin budget has zero slack | **Closed** | §2.6 confirmed six signals unconnected on the CoCo 3, leaving a debug UART, an LED and the strap. The budget was right and the part was wrong — "LQFP48 stands" did not survive; UFQFPN48 since 2026-09-04 (§3.2). |
| 5 MHz stretch unreachable | **Withdrawn** | No 6309E grade above HD63C09E exists; the figure was unsourced (§3.3). 3 MHz replaced it as the stretch target. |

## §10 — answered questions, original forms

The open-questions list kept answered items struck through with their resolution
narratives; the spec now states each answer plainly. Original narratives worth keeping:

- **Item 2 (LQFP48 or LQFP64?)** was answered twice: "48 pins, with 4 to spare", then
  again on 2026-09-04 — "it has to be the UFQFPN48, not the LQFP48. The 48-pin *die* was
  never in question; the *bonding* was."
- **Item 3 (`t_DSR`/`t_DHR`?)** was answered twice: first from
  `reference/datasheets/MC6809E.pdf` (40 ns / 10 ns, MC68B09E), then properly from the
  HD6309E datasheet — "this retired an extrapolation that had the 3 MHz analysis wrong
  in both directions."
- **Item 3d (does the microcode step fit?)** — "the §4.1 design *as originally
  specified* costs ~80 and misses at every rate, so this was a design constraint
  discovered just in time rather than a comfortable confirmation."

---

## README — archived material

### The quarter-cycle framing and its table (superseded 2026-08-27)

The README asked Phase 1's question as "can we drive the address inside a quarter
cycle?" and carried this table, followed by its own supersession notice:

> | E rate | Core cycles/bus cycle | Quarter cycle | Estimated need | Verdict |
> |---|---|---|---|---|
> | 0.895 MHz (CoCo 3 boot) | 190 | **47.5** | 9–14 | comfortable |
> | 1.79 MHz (CoCo 3 fast) | 95 | **23.7** | 9–14 | **target** |
> | 3.0 MHz (63C09E max) | 57 | 14.2 | 9–14 | marginal |
> | 5.0 MHz | 34 | 8.5 | 9–14 | below the floor |
>
> **The table above is superseded.** The deadline is not the quarter cycle. Per the
> MC6809E datasheet (`reference/datasheets/MC6809E.pdf` p.3, item 11), *Address Delay
> Time from E Low* `t_AD` is **110 ns max** for the MC68B09E — an **absolute** figure,
> not a fraction of the E period, so it is identical at 0.895 and 1.79 MHz.

A blanket notice ("⚠ **This README's timing numbers are superseded (2026-08-27)**...
Sections below that quote `t_DSR` = 40 ns, `t_DHR` = 10 ns or a `T_iter ≤ 6` gate are
correct **only for the 1.79 MHz target**") stood at the top of the README until this
cleanup. Replaced by the `t_AD`-window framing with both speed grades stated inline.

### The variant 3 timeout advice that pointed the wrong way (fixed 2026-09-04, Cpu-M1)

> ⚠ **This README used to say a timeout "points at wiring or a clock enable rather than
> a wrong bit position", and that advice would have sent you the wrong way.** The
> register constants *are* verified against RM0440 Rev 9, but that was never the only
> way to get a timeout: until 2026-09-04 `s_dma_addr` was declared `__ccmbss`, i.e.
> linked at `0x1000xxxx`, and **RM0440 §2.4 says CCM SRAM can be accessed by DMA only
> through its alias** (`0x2000 5800` on a category-2 part). Every transfer would have
> bus-errored, `dma_timeouts` would have equalled `n_cycles`, and the project's own
> documentation would have pointed the bench at the wiring. The variable is in ordinary
> SRAM now, and `dma_errors` exists so the two failures can never be confused again
> (`docs/design-review.md` Cpu-M1).

Replaced by the present-tense statement of the CCM/DMA alias constraint and the
`dma_timeouts`/`dma_errors` diagnosis table.

### The "slightly conservative" measurement claim (fixed 2026-09-04, Cpu-M4)

The README called the latency measurement "slightly conservative" on the strength of the
`DSB` before the timestamp, and the pass gate was 18. See the §5 entry above; the gate
is 14 and the README states the optimistic bias directly.

### Provisioning note

The BOOT0/PB8 hazard was found in the 2026-09-04 design review (`docs/design-review.md`
Cpu-M2); no document in the repository mentioned it before then.

### Phase 1 TODO list

The list carried "Variant 4 — overclock to 180–200 MHz" as a live item until 2026-08-28
(struck thereafter — see the §3.4(4) entry), and stale unchecked duplicates of the
already-built variants 2 and 3 ("predicted ~2.5 MHz" / "predicted ~3–3.5 MHz") until
this cleanup; `spike_poll_asm.S` and `spike_dma.c` exist and build, and the remaining
open work on them is the first silicon measurement, which has its own item.
