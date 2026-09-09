# Video — archived history

Superseded material removed from [`graphics.md`](graphics.md) and
[`features.md`](features.md) when the documentation was split into present design
and archived history on 2026-09-08. The present design is in those documents; this
one records what they used to say and why each claim changed. Section numbers refer
to `graphics.md` unless marked otherwise. "Vid-*" identifiers are findings of the
2026-09-04 review, [`docs/design-review.md`](../../docs/design-review.md).

---

## `features.md` §8.4 / `graphics.md` §7.4, §13 — sprite mode was a proposal with an open question (built 2026-09-09)

§8.4 was headed **"One change would make the span writer a real sprite engine"** and was
explicit that it was *"Proposal, not specification"*. Its cost estimate:

> - **What it costs:** the retire logic already computes `RETIRE = SPANBUSY · SPNGRANT`
>   and already routes the mask bit to the register file's `A0`. Suppressing `/WE` on a
>   `0` bit is **one product term on an existing output plus one `CTRL` code** — `WMODE`
>   has a free encoding at `11`, and `seqctl` is the roomiest GAL on the card at **7
>   macrocells of 10 and 8 of 14 input pins**.
> - ⚠ **What is unknown:** whether the mask bit is available at the sequencer at the right
>   moment. §7.4 is explicit that *"the mask bit never enters the sequencer"* — it goes
>   straight to the register file's address pin — so this proposal **needs it in a second
>   place**, and that is a real input-pin and timing question, not a formality. **Fit it
>   before believing this paragraph.**
>
> This is the highest-value cheap change this document found, and it is recorded as an
> open item rather than a decision.

**Fitting it settled both halves, and the estimate was right about the cheap one and
silent about the expensive one.**

| | estimated | actual |
|---|---|---|
| logic | "one product term on an existing output" | **one macrocell** — `WEN`, three terms, plus one more on `SPANEND`. `seqctl` 7 → 8 of 10 |
| the `CTRL` code | one | one — `WMODE 11`, §13 |
| ⚠ **the mask bit** | *unknown* | **an input pin on `vctrl`**, and `WEN` an output pin beside it |

⭐ **And the answer to "is it available at the sequencer" is no, so it became a pin — and
the part had exactly two left.** `vctrl` had been quoted at "64 of 64 I/O" in six
documents, and that was never the whole package: an `ATF1508AS` PLCC-84 also carries
**four dedicated input pins** that are not I/O, and two were free. The fit is now
**64/64 I/O *and* 4/4 dedicated, 122 of 128 cells**, still with JTAG reserved, still
"Design fits successfully".

**The estimate's "seqctl is the roomiest GAL on the card" was also true and beside the
point.** `seqctl` is a *superseded* GAL design kept as derivation (`gal/README.md`); the
card is two `ATF1508AS`, and headroom on the GAL says nothing about headroom on the die
it merged into. That is the second time this project has priced something against the
GAL partition after the CPLD build replaced it.

**What did not change**, and `check:seqctl` asserts it: **span-mask is unaffected**. A
`0` bit still writes `WBG` through the register file's address line, which is §7.4's
mechanism and costs no logic. Sprite mode reads the same bit a *second* time, for a
different purpose, and that is the entire difference.

**Two claims in §7.4 were rewritten with it.** *"The mask bit never enters the
sequencer"* became "does not enter the sequencer's **colour** path", and `RETIRE` stopped
being both the advance and the write strobe — they are two signals now, identical in
three modes of four.

---

## §0 / §14 — the IC count: ~33 → 36 → 41 → 31 → 28 → 27

The headline was wrong twice over before it was ever right. §0 claimed **"~33 ICs
(37 with the `'153` pixel mux)"** against a §14 table that summed to **36** with the
mux and 32 without — the parenthesis was inverted as well as the number, since §6.1
made the mux the default. And §14 was itself short of four things the bus interface
needs — the posted-write **address** latches (§3.1.1, +3 `'574`), the spare-access
**arbiter** (§5.2.1, +1 GAL), a tri-state driver for `VSTAT`'s live bits (§12.1,
+1 `'244`), and an analog buffer stage (§9.1, 0 ICs but 4 discretes) — while
carrying a master oscillator that belongs on the motherboard (−1; a card that
supplies E is a card whose removal stops the CPU). Net +4 packages and none of it a
change of design: **the same card, counted**. That made the honest GAL build
**41 ICs, 10 × GAL22V10**.

§10.1.6 then replaced the GAL build on 2026-09-06 — *"two PLCC-84 parts, and this
is the build"* — **without the arithmetic being carried back**, so three counts were
live at once until 2026-09-08: §0/§14's 41, §10.1.6's uncounted 2-CPLD build, and
the power table's "one ATF1508AS" (wrong in a third way — the partition is two
parts). §14.1's reconciliation derived **31**, then §14.2's SRAM consolidation took
three packages (**28**... via the arbiter's day: see §10.1.6.3 below) and the final
build landed at **27** (2 CPLDs + `rfa` + 4 SRAMs + 20 × 74-series), 23 if the
tri-state pixel bus closes.

**The GAL-build table, as §14 carried it** (differences from the final build):
4 × `AS6C1008-55` framebuffer (→ 2 × `AS6C8016-55`), 2 × 32K×8 15 ns LUT
(→ 1 × `IS61C6416AL-12`), ten `GAL22V10-15` — sync `hgen`/`vgen`/`vdec` ×3, scan
×2, `WPTR` ×2, sequencer ×2, arbiter ×1 — (→ `vaddr` + `vctrl` + `rfa`), plus a
`74HC165` span-mask serialiser, a `74HC273` for `CTRL`, and 2 × `74HC161`
`SPANLEN` counters, all later absorbed into the CPLDs. The GAL count itself walked
8 → 9 (the arbiter became its own package, §5.2.1) → 10 (the sync section fitted at
three parts, not two — see §19 item 8 below).

---

## §0 / §14 — power: 450–650 mA → ~1.2–1.8 A → ~0.7–1.1 A → ~0.5–0.85 A

The original claim of **450–650 mA** was smaller than one line of its own
arithmetic: the same document priced a GAL22V10 at ~70–90 mA, and nine of them is
630–810 mA before a single SRAM is powered. The honest GAL-build total was
**~1.2–1.8 A** ("call it 1.6 A nominal and specify for 2 A") — which forced a
switching pre-regulator or a 5 V backplane rail (a 7805 dropping 7 V at 1.5 A is
10.5 W), and multiple parallel slot power pins. The CPLD consolidation took it to
**~0.7–1.1 A** ("0.9 A nominal, specify for 1.5 A", 2026-09-06 — at 0.9 A the 7805
is 6.3 W and arguable), and §14.2's SRAM consolidation to the final **~0.5–0.85 A,
0.65 A nominal, specify for 1 A** (4.6 W — the pre-regulator became unnecessary;
the multiple slot pins stayed). Area followed the same arc: the GAL build's
estimate was "~150 of 160 cm²" on a 24 cm Eurocard with the slack gone; the final
figure is 99.1 cm² on an 18 cm board, measured by `hardware/place`.

---

## §2.1 — the blanking rows were charged at the wrong cadence

The spare-access arithmetic divided the blanking intervals by the raw 72 ns access
time (`6.36 µs / 72 ns` = 88.3 accesses per chip per line, 483,000/frame,
≈34 M accesses/s) as if accesses were free-running. They are not: every access is
granted on the 158.9 ns fetch-slot grid (§5.2), and a chip takes at most two
accesses per slot. Charging the slot grid cost ~9 % on both blanking rows —
~462,000/frame, ≈32.4 M accesses/s, headroom **77×, not 80×**. The conclusion was
untouched, but the table is quoted downstream (`docs/video-comparison.md` §4), so
it was corrected rather than rounded away.

---

## §3.1.1 — one capture register became four

The posted-write path was described as *"one capture register, one edge, same
discipline — a rename, not a redesign"*. The "one register" figure was inherited
from colormin, where VRAM is write-only through `WPTR` — the address always came
from the card's own counter, so a CPU write contributed nothing but a data byte.
§6.3 makes this card's VRAM **flat-mapped**: a direct CPU write arrives carrying an
arbitrary 19-bit physical address that exists nowhere else on the card, and it has
to be captured on the same edge as the data. The edge count was unchanged; the
register count was not — 23 bits of address + control across three more `'574`s.

## §3.3 — "stretching E"

This document called the `/WAIT` mechanism "stretching E"; `docs/machine.md` uses
"stretch" for the ÷8 clock rate, a different thing entirely, so the word was
retired here in favour of "fast-E mode" for ÷8.

---

## §5.2.1 — "the other three chips, by a wire"

The arbitration was first written as static: the CPU's chip fixed in time and the
span writer taking "the other three chips… by a wire, not a state machine". Wrong —
*which* chip the CPU takes is `address[1:0]`, dynamic per access, so "the other
three" is a per-access computation. The first costing put it at 12 macrocells
("8 grants + 4 source selects") and budgeted a ninth GAL; the fit found
`SRCSEL[n] = GRANT_CPU[n]` — the same signal — so it was 8 macrocells with two
spare. The package itself went on a longer journey (§10.1.6.3 below).

## §5.2.2 — per-chip fetch-latch clocking, and the reason nobody had written down

The per-chip justification originally rested on the spare-access grant and tile
mode. The strongest reason was added 2026-09-06: **byte-granular horizontal scroll
requires it** — with a common latch clock the display cannot render a line at
`HSCROLL[1:0] ≠ 0` at all. The four latches load from a common address at a common
instant, so during fetch slot *g* every chip holds group *g*; with phase *p* the
mux emits `4g+p`, `4g+p+1`… and then wraps to chip 0, **which still holds `4g+0`**
— the line steps backwards `4−p` pixels in. `check:seqph` asserts the divergence
for every `p ≠ 0`. §5.2.2 and §8 had described one mechanism from opposite ends
without meeting; the phase-dependent `FCLK` equations (§19 item 23) are where they
met.

---

## §6.2.1 — 59.94 Hz, and the polarity-term arithmetic

"60.0 Hz" was corrected 2026-09-06 by `sync.timing.ts`'s own arithmetic check:
25.175 MHz ÷ 800 ÷ 525 = **59.940 Hz** — the standard VGA 640×480 rate, never 60.
It matters in one place: §12.1 makes vertical blank the NitrOS-9 system tick, so a
tick divisor calibrated for one family runs 0.1 % wrong in the other — about 86
seconds a day. The two families need different divisors.

The sync-polarity cost estimate was wrong twice in opposite directions. The
paragraph read *"two terms per mode over the four `VMODE` values = 4 product terms
… XOR doubles it to 8"*. Too high: only `VMODE[0]` reaches the sync logic — there
are two vertical timings, not four (`VMODE[1]` is line-doubling, the scan
generator's business). Too low: XOR against a *variable* is not a doubling — the
`/A·B` half is the complement of a nine-literal window compare, nine terms. Actual:
`VSYNC_raw` 1 term, polarity +9 → 10.

---

## §6.3 / §6.3.1 — the MMU's journey

The original recommendation was *"put the MMU inside `arm6309`,
GIME-register-compatible, and map VRAM flat into the physical address space"*. The
flat map stands; the location and register compatibility did not survive the
single-SKU argument — the MMU went to the motherboard so one 48-pin part serves
both the CoCo 3 drop-in and this machine. An interim alternative — *"use the
LQFP64 part (STM32G431RB/G474RE) for the homebrew CPU card"* — was superseded the
same way; its arithmetic (LQFP48 closes at 35 of 39 pins for the CoCo 3, and an
in-CPU MMU adds A16–A19 + HSYNC) remains why the in-CPU version would have needed
the larger package.

**The "three-IC" motherboard MMU could not be wired.** It was short two packages
for two reasons from one place: a common-I/O SRAM has one set of pins doing two
jobs (→ the `'245` isolation buffer and break-before-make discipline), and a
translate-mode address that is wrong during the very cycle that writes it (→ the
`'157` 4-bit address mux, which was not in the list). Hence **5 ICs**. §15's DAT
row records the irony: the 1980 `74LS189`-class part, with separate data-in/out
pins, was better shaped for the job than the 1990 commodity SRAM.

**The CPU package** was the CBT6/LQFP48 until `machine.md` §5 item 6: the LQFP48
bonds out only 38 GPIO and lacks `PC4`/`PC6`/`PC10`/`PC11` (`BA`, `BS`, debug
UART). The part is the **STM32G431CBU6, UFQFPN48** — same die, same firmware. The
HSYNC row in the pin table was also one pin when first written; §12.2 showed a
raster line *number* needs a frame origin as well as a line clock, so it is two.

Consequence 2 of the flat map was originally written as "physical A0–A18 plus a
chip select" and stopped there — an unsafe card; §6.3.2's `/IOPAGE` qualification
is the fix (found by the review).

---

## §6.4.1 — the address-mux source count, and the MAP stride

The tile address mux was priced at **two** sources per bit, then **three** (bitmap,
Variant A, Variant B), then the built version was **five** — the modes plus
`WRITESEL & WA[n]` and `MAPSEL` — exactly what an ATF15xx macrocell holds before
cascading, with nothing left. §10.3's engine wanted a **sixth** for its own
pointer, which is the real reason §10.1.6.2's first fit returned `INTERNAL ERROR`.
Both fixes were subtractions: the engine shares `WPTR`, and Variant B's `CHARSEL`
came out — **four sources, one spare**.

**The MAP fetch was not a concatenation.** An 80×25 map packed at 2,000 bytes needs
`MAPBASE + cellRow × 80 + cellCol`, and 80 is not a power of two — a
multiply-accumulate, exactly the adder the section's argument says does not exist.
Fix: a **128-byte row stride** — `MAPBASE` in `A18..A12`, cell row in `A11..A7`,
cell column in `A6..A0` — concatenation again, costing 1,200 bytes nobody was
using (3,200 B rather than 2,000). `check:tile` asserts both halves.

---

## §6.4.3 — Variant B, the 1bpp character generator (dropped 2026-09-08)

Kept in full because it is the design a rebuild would start from, the cost model
the decision was made against, and the record that the mode was priced rather than
dismissed. Its macrocells, product terms and four pins were spent on §10.3's list
engine (§10.1.6.2 has the fits).

**The design.** Per cell: fetch code, attribute, and one font row — 3 accesses per
8 dots against the bitmap's 8. The font byte goes to a serialiser; its output bit
plus the attribute chooses the colour through the LUT's unused 127/128, addressed
as `{page, attr[7:0], glyph_bit}` — 10 bits, well inside the 15 available:

```
graphics :  LUT[ 0 | 0000000 | pixel[7:0] ]        -> RGB565
text     :  LUT[ 1 | 000000  | attr[7:0] | bit ]   -> RGB565
```

The attribute byte rides the existing pixel bus into the existing index latch; the
glyph bit goes straight to a spare LUT address pin; the page select is one `CTRL`
bit. No comparator, no fg/bg mux, no second colour path. Against the GIME:
**256 freely-defined attributes** (vs 8 fg × 8 bg), any RGB565 pair (vs palette
entries 0–7), 240 accesses per line against the bitmap's 640 — roughly 400 accesses
per line, ~160,000 per frame, handed back to the span writer and blitter. Cost:
+1 IC (the serialiser) — or 0, since the span-mask `74HC165` is idle in character
mode and shareable, at an `'AHC` grade upgrade (that was §6.4.4, now moot).

| | Variant B | span writer, bitmap mode (§7.3) |
|---|---|---|
| Per cell | **2 writes** | 13 writes |
| Full 80×25 redraw | 9.5 ms — **105 Hz** | 62 ms — **16 Hz** |
| **Scroll one line** — what a terminal does | 0.38 ms | **2.5 ms** |

**Why it was dropped anyway.** The scroll row decides the *usefulness* question in
Variant B's favour on paper — but a 9600-baud BBS delivers about twelve 80-column
lines a second, so 12 × 2.5 ms is 3 % of the CPU in bitmap mode; at 115.2 kbaud it
is 36 % and still runs; and a full-screen ANSI art frame is 2–4 KB of escape codes
taking 2–4 s to arrive against 62 ms to draw. **The renderer is 30–60× faster than
the line feeding it.** And under NitrOS-9 the mode was never usable: it is global,
not per-window, so a text window and a graphics window cannot coexist — the whole
of NitrOS-9's windowing. What is lost that is not an update rate: the attribute
colour path (in bitmap mode per-cell colour is two of the thirteen writes — paid
for, not lost), and "text status bar over a bitmap playfield" survives via Variant
A's 8bpp tiles at 16 KB of font instead of 2 KB.

**The pendulum, for the record.** §7's opening was written as a settled rejection
of hardware text ("~8–12 ICs, cannot mix with graphics, needs its own memory");
§6.4 reopened it and §10.1.5 made Variant B the card's text engine on 2026-09-06
("text stops being the span writer's problem", 2 writes/cell); §10.1.6.2 dropped it
on 2026-09-08 for the list engine's fan-in. The span writer's 13 writes/cell is
the headline text figure again, and was the fallback figure for two days.

---

## §7.3 — the retire figure was wrong by 4×

The full-screen-clear row claimed **~5.1 ms to retire** until 2026-09-08. §7.4's
bound caught it: the figure assumed the span writer took all four chips' spare
accesses in a slot, but `WPTR` names one chip at a time and two accesses do not fit
the slack — one byte per 158.9 ns slot, so 128,000 bytes is **20.3 ms**. (Then
§14.2's two ×16 parts with four byte enables made it **5.1 ms again**, by a
mechanism that actually exists — the broadcast write.) The CPU-bound rows were
unaffected throughout.

## §7.4 — `/WAIT` stalled reads for nothing

`/WAIT` was `SPANBUSY · VRAMSEL · /IOPAGE · E`, stalling the CPU on **any** VRAM
access during a span — up to 40.7 µs. §3.1.1's backstop protects the depth-1
posted-**write** latch; a read proceeds a chip ahead of the span writer and has no
conflict. **`WAIT.oe` gained `& !RW`** on 2026-09-08 — one literal on an existing
output-enable term. §7.4's broadcast write was "proposal" until §14.2's two-chip
framebuffer dissolved its arbitration problem (one spare access, one grant, four
byte enables — nothing to count) and made it the default.

---

## §10.1 — the no-CPLD wall, and how the card went through it

`blitter.md` §6.2's trigger — *"eighteen GAL22V10s is the point where the honest
question becomes 'why not one CPLD'"* — was written per-card; the count that
reached eighteen was the machine's (ten here, two motherboard, five audio, plus
decode GALs — `hardware/gal/README.md` put it at roughly twenty). The GAL-build
escalation table read: Rev A **9→10** GALs / 40–41 ICs, + list engine ~12 / 45,
+ blit datapath ~21 / ~59 — 1.3–1.8 A of GAL alone at 70–90 mA each.

**§10.1.2's chronology paragraph is what eventually retired the machine's no-CPLD
rule** (root `README.md`, 2026-09-08): the MAX 5000 — the first architectural CPLD
— is 1988, a year before the card's own 1989–90 date; §15 already carried 74AHCT
(~1990) and the 1 Mbit SRAM (~1989–90) as newer. "No CPLDs" was a style rule, not
a period rule.

**The buried-register GAL analysis** (evaluated while the rule still stood): the
card was GAL-heavy because ~54 macrocells were counter bits on pins nobody read —
a 22V10 has no buried nodes. An ATF750C-class part with buried registers saves
**exactly one package** (the sync trio's 18 internal bits; two ATF750Cs hold it),
because the scan and `WPTR` pairs' 36 bits *are* the address buses — no part choice
changes that. Pure `'161`/`'163` counters instead: 10 → 8 GALs but 41 → 47 ICs.
One package in ten, for the house rule.

**The census** (`npm run census`, from the fitted designs): ~120 macrocells
including the 17-bit address mux the first pass missed — on GALs the two counter
pairs tri-state onto a shared address bus for free; inside one die two macrocells
cannot drive one pin, so the mux is 17 further macrocells, the one place merging
costs silicon. Half the pin count was the packaging talking to itself.

**§10.1.3 as first decided (2026-09-06): one `ATF1508AS-…AU100`, TQFP-100** —
119 macrocells / 71 I/O; PLCC-84 seven pins short even after shared-`/OE` and
`'139` tricks (collapsing `FCLK0..3` to a common clock would have found the pins
and cost byte-granular scroll — refused); PQFP-160 wasteful. ~$16 against ten
ATF22V10C at $2–3, deleting four more packages: 41 → 32 ICs. Costs: 0.5 mm-pitch
SMD (no socket), and `hardware/gal/jedec/` stops applying — its assembler and
fuse-map simulator are a GAL22V10 and nothing else; the fitter is Microchip's
`fit1508.exe`. The 3.3 V `ASV` variant was closed on cost: it needs a 3.3 V rail
the backplane does not carry, to save ~$10. **§10.1.4's "two ATF1504AS in
PLCC-84"** partition (63+57 of 64 macrocells, ~15 inter-part nets) was the
socketable alternative; its census's "128 of 128 macrocells" was withdrawn as an
artefact (absorbing the `'165` bought pins the TQFP did not need for macrocells
the card did — the real figure was 120 of 128, 78 of 80).

**§10.1.5 (2026-09-06): the variants set the package.** With Variants A and B in
v1 the design needed 89 I/O and 128 of 128 macrocells — `ATF1508AS` **PQFP-160**,
full, with the list engine having nowhere to go. That is what §10.1.6 answered by
splitting into two PLCC-84 parts.

**§10.1.6's evolution.** The 2026-09-07 refit: `vaddr` PLCC-84 101/128 cells,
62/64 I/O; `vctrl` PLCC-84 91/128, 50/64; `arb` on its own GAL22V10 10/10.
(An earlier lesson: count logic cells, not equations — the fitter cascades any
equation wider than five product terms, and every equation-counted estimate had
been low.) §10.1.6.1's pin repairs: `CTRL` was crossing the boundary twice
(8 outputs + 7 re-imported bits for a write-only byte that never leaves the part);
`HPOL = !VMODE0` freed a pin; `WRITESEL`/`LISTSEL` were `SPNGRANT`/`LGRANT` under
second names.

**§10.1.6.2: the list engine failed to fit** — `INTERNAL ERROR` on PLCC-84, and on
TQFP-100 (80 I/O, pins not the constraint) still failed at 90 % logic: **fan-in**
— an ATF1508AS logic block admits 40 of ~200 global signals, and a 19-bit pointer
feeding a six-source 17-bit mux does not fit a 40-signal window. Three ways
forward: a third CPLD; share `WPTR` (a semantics change); leave it out of v1.
Option 2 was measured: with its own pointer, unplaceable; sharing `WPTR` on
PLCC-84, ✗ by nodes (153/128); on TQFP-100 ✓; **sharing `WPTR` with Variant B
dropped, PLCC-84 ✓ at 64/64 I/O, 105/128 cells** — taken 2026-09-08. Dropping the
engine's own 19-bit pointer removed 19 registers, 19 mux inputs and the sixth
product term per address bit. The shared pointer is a specification rule the fit
does not settle — **the engine clobbers the CPU's write pointer** — recorded as
§10.3.1's `WPTR` reload rule; `LIST` at `+$0B`–`$0D` was deleted as a fiction
(three bytes back to the reserve). Deleting `LIST` also deleted a defect: the
`LLOAD` strobe `WSTB & !RA4 & RA3 & !RA2 & RA1` was described as "$0B–$0D under
one strobe", but five bits with `RA0` free is **two** addresses — `$0A` and `$0B`
— so a write to `WPTRC` would also have loaded the list pointer. It never fired;
the shared pointer removed strobe and bug together.

**Item 23's closure found three errors in the 2026-09-07 fit**, all in logic
already reported as fitted: the scroll holds loaded `HSCROLL[7:0]` where §8 wants
`HSCROLL[9:2]` (four bits off — every horizontal scroll would land at 4× the
column asked for); the intra-cell byte address came from a slot-counter bit
(units of sixteen pixels rather than four); and the map had no address source at
all (`MAPLD` latched a byte from an address nothing generated). Fitting proves a
design lands on a part, not that the design is right.

**§10.1.6.3: the arbiter's day (2026-09-08).** Machine-level decisions put `A6`
(window widened to `$FF00`–`$FF7F`), `/A20` (2 MB physical map) and `& E` (on
`WAIT.oe`) onto `vctrl` — 76 I/O against a PLCC-84's 64. Worse, the committed fit
had been run against a `P1508T100` (TQFP-100) while the `.pld` declared
`f1508ispplcc84` and `regfile.ts` said "62 of 64" — **the design and its fit
disagreed about the package and nothing checked it.** Morning: the arbiter went
back out to its own GAL22V10 (its ten macrocells are exactly a 22V10; `WRITESEL`
became a `vctrl` input), landing `vctrl` at 64/64 — zero spare, no JTAG. Then
`rfa` was built (`gal/regfile.jedec.ts`): moving `RA0`–`RA4` + `WSTB` off `vctrl`
freed **fourteen** pins, not the five estimated — removing the five outputs also
removed the nine inputs that existed only to feed them (`A0`–`A4`, `IOSEL`, `A5`,
`A6`); `rfa` re-derives `REGSEL = IOSEL & A6 & A5` locally, 6 of 10 macrocells,
checked against CUPL over all 8,192 inputs. Evening: with `rfa`'s −14 and Variant
B's −4, **the arbiter merged back into `vctrl`** at 62/64 and 97/128 — a part at
two-thirds capacity beside a GAL doing ten macrocells of work was a package nobody
was buying anything with. `rfa` cannot follow it (fitted and fails — it is what
bought the pins). Merging costs no verification: `arbDesign` stays in
`access.jedec.ts` as the executable check form, its `.jed` carrying a
**SUPERSEDED — DO NOT PROGRAM** banner. Cost: `vctrl`'s JTAG (2 spare pins against
4 needed) — both CPLDs programmed out of circuit; §14.2's 2-grant arbiter would
buy it back (~56 of 64) once §5.2 is rewritten, which is §19 item 25.

---

## §6.4.1 / §6.4.6 / §7 / §10.1.6.3 / §19 item 25 — the cell address took the wrong counter (corrected 2026-09-08)

`video.parts.ts` computed a **different map address from the one §6.4.1 and
`tile.model.ts` specify**, and had done since the tile fetch was written. `mapSrc`
read

```
bit >= 12 ? MB[bit-12] : bit >= 5 ? SA[bit-2] : V[bit+1]
```

which places the cell column at `A11..A5` and three bits of cell row at `A4..A2` —
a map with a **32-byte column stride and a 4-byte row stride**, 8 addressable rows
against the 25 an 80×25 needs, and the `HSCROLL` mux phase left in `A1..A0`. The
spec says `MAPBASE | cellRow<<7 | cellCol` throughout.

Two things let it stand. **Nothing asserted the design and the model agreed** —
`tile.check.ts` imported `addressMux()` only to *count* its product terms, and
counting a mux does not check what it computes. And the vertical source was the
**sync line counter `V`, not `vadr`'s row counter**, which is wrong independently
of where the bits land: `sync.timing.ts` puts both counters' origin at the leading
edge of their own sync pulse, so active video starts at line 37 in the 449-line
family and 35 in the 525-line one. `V2..V0` as the row inside the cell would have
rotated every cell by 5 rows in one mode and 3 in the other. `tileSrc` used exactly
that. The five bits the map's cell row needs, `V7..V3`, were declared as `vaddr`
input pins and **driven by nothing** — `vctrl` exported only `V0..V2`.

**What replaced it.** Both vertical fields are `vadr`'s row counter — `SA12..SA10`
for the row inside the cell, `SA17..SA13` for the cell row — which `VLOAD` loads
from `VSCROLL` at vblank and `ROWADV` steps once per *displayed* row, so it is
zero-based at the top of the window and scrolled. `mapSrc` is
`bit >= 12 ? MB[bit-12] : bit >= 7 ? SA[bit+6] : SA[bit+3]`. `MAPA1`/`MAPA0` =
`SA4`/`SA3` were added to name the chip the map byte lives on, the map fetch being
a spare access. `tile.check.ts` now evaluates the fitted mux against the model over
every cell, every pixel within it and all 256 codes, and asserts no cell-mode
address bit reads `V`; both halves of the old code fail it.

**Three claims moved with it.**

- **§6.4.6 limit 2 said fine scroll was free horizontally.** It is free in both
  axes — the vertical intra-cell offset is `SA12..SA10`, the same counter bits —
  and the cell ring is 32 rows, which is what makes §6.4.8's terminal scroll a
  single `VSCROLL` write. (`features.md` §10 had also still listed "fine
  horizontal scroll in tile mode" as *not* available, which §6.4.6 had already
  contradicted.)
- **§7 said the span writer was "the card's only text mode".** It is the only one
  that mixes with graphics or colours per cell; §6.4.8 is the one-colour-pair
  console at 1 write per cell, which is fewer than the dropped Variant B's 2.
- **⚠ "Neither CPLD has JTAG" (§10.1.6.3, §19 item 25) is no longer true.**
  `vctrl` exported `V0..V2` to `vaddr` for a field that should never have crossed;
  removing them returned three pins on each part. The fits went to **`vaddr` 61 of
  64 and `vctrl` 59 of 64 with `TMS`/`TDI`/`TDO`/`TCK` reserved**, both reporting
  "Design fits successfully" — so both parts are programmed **in circuit**. The
  superseded figures were `vaddr` 64 of 64 and `vctrl` 62 of 64, "two pins spare
  against the four JTAG needs", with §14.2's 2-grant arbiter named as the thing
  that would buy `vctrl`'s back. §14.2 would still free six output pins; it is no
  longer what in-circuit programming waits on. `vctrl`'s declared device moved
  `f1508plcc84` → `f1508ispplcc84` with it.

  ⚠ **The 59 stood for hours.** §6.4.9's fetch cadence and §8.1's window signals spent
  the three pins again the same day and `vctrl` is at **64 of 64 I/O and 121 of 128
  cells** — still fitting, JTAG still reserved, and with nothing spare. `vaddr` is
  unchanged at 61 of 64. The present figures are in `graphics.md` §10.1.6.3 and
  `cpld/vctrl.fit`; the chain 62 → 59 → 64 is in `hardware/history.md`.

**§6.4.5 / §10.1.5 / §19 item 15 said the tile fetch was closed by the CPLD build.**
§19 item 15 read *"closed by the CPLD build … what remains is bench verification with
everything else, not a fit question"*, §6.4.5 said the fit *"carries the whole of
§6.4's tiling"*, and §10.1.5 called Variant A *"v1 hardware, not an option"* without
qualification. **The fit was closed; the sequence never was.** `tileCadence` counts
`TC0..TC2` on `SLOTTICK` and splits at `TC2` — but a slot is four dots and a cell is
eight, so the period is four cells, and over it the design fetches 16 tile bytes where
32 are needed and latches one map byte where four are. Restated 2026-09-08 as item
15(c): the address path is checked (`check:tile`, both axes of scroll included) and
the fetch path is a placeholder needing a cell-aligned cadence, a fourth arbiter
requester for the map byte, and `MAPLEAD`.

---

## §8 / §19 item 15(d) — nothing drove the scan counters (built 2026-09-08)

§8 has always read as though scrolling worked: *"a separate 9-bit V-address counter
supplies row bits A18..A10, loaded from `VSCROLL` during vblank"*, *"`HSCROLL[9:2]`
preloads the H-address counter at the start of each line's fetch window"*. Both
counters were fitted and `scan.check.ts` exercised them over a 400-line frame at three
scroll positions. **Nothing produced their load or enable inputs.** `FETCH`, `HLOAD`,
`ROWADV` and `VLOAD` were declared as `hadr`/`vadr` inputs and listed in `census.ts`
under *"produced by the sequencer's unfitted decode half"* — a set that read as a
to-do list and was load-bearing. So the column counter never took `HSCROLL`, the row
counter never took `VSCROLL`, and **the row never advanced at all**, in bitmap mode as
much as in cell mode. A checked counter with no clock enable is still a counter that
does not count.

§6.4.9's cadence produced `FETCH` and `HLOAD` on its way past, because the map fetch
had to be placed against a fetch window. §8.1 is the rest, and two of its four
signals cost nothing:

- **`VLOAD` is `VBLANK`.** "Asserted through vertical blanking" is VBLANK's
  definition and `vdec` had been producing it all along — the signal was named twice
  and built once. Renamed at merge.
- **`CE` is `SLOTTICK`.** `hgen` declared its slot enable as an input while saying in
  the same breath that it *"is that signal and not a second divider"*, and `vctrl` was
  taking its own output back in on a pin. That pin paid for `ROWADV`.

Both are the same kind of identity as `WRITESEL` = `SPNGRANT`, and on a part at 64 of
64 I/O the difference between an identity and a signal is a pin.

**⚠ And a rule that was not written down anywhere: every counter *enable* carries
`SLOTTICK`, every *load* does not.** Both CPLDs are clocked on `DOTCLK`, so a window
level asserted for a whole slot steps a counter four times. `FETCH` and `MCADV` were
written as bare levels when §6.4.9 was built and would have walked 2,560 pixels across
a 640-pixel line; `ROWADV` was written the same way and would have scanned the picture
at quarter height. The first version of `cadence.check.ts` missed it by modelling the
map counter on rising *edges* instead of clock edges — a model kinder than the
silicon. Counting per dot is what makes the gate visible, and it is now what the check
does.

§6.2's line doubling ended up living entirely inside `ROWADV`, as `scan.jedec.ts`
always said it would: *"the sequencer withholds every second one"*. Which line to
withhold is one term in both families, because the first active line is odd in both
(37 and 35) — the same accident behind `vdec`'s "`v <= 1` in both families".

---

## §6.4.5 / §6.4.9 / §19 item 15(c) — the fetch cadence was never a sequence (built 2026-09-08)

`tileCadence` in `video.parts.ts` read:

```
  TC0..TC2 = counter on SLOTTICK
  MAPLD    = TILEMODE & SLOTTICK & !TC2 & !TC1 & !TC0
  MAPSEL   = CELL & !TC2
  TILESEL  = TILEMODE & TC2
```

**A slot is four dots and a cell is eight, so that period is four cells**, and the
split at `TC2` gave four slots to each side. Over those four cells it fetched **16
tile bytes where 32 are needed and latched one map byte where four are** — half a
line's pixels with no data, three cells in four with no code. It was a sketch of
"map byte, then the tile row", and it had never been run: no check evaluated it.

The docs had it as done. §19 item 15 read *"closed by the CPLD build … what remains
is bench verification with everything else, not a fit question"*; §6.4.5 said the fit
*"carries the whole of §6.4's tiling"*; §10.1.5 called Variant A *"v1 hardware, not
an option"* unqualified. **The fit was closed and the sequence never was** — the
distinction the archive should have carried and did not.

Replaced by §6.4.9, whose shape is forced by §6.4.2's own arithmetic: eight tile
bytes are two four-chip display fetches, so the ninth access is the map byte out of
§5.2.2's spare window, once per cell, with `H0` as the cell phase. Three things came
with it and each cost something:

- **A one-cell lead, and a counter to carry it.** Same-slot fetching leaves 4.4 ns
  twice over (mux 15 + SRAM 55 + setup 5 against a 79.4 ns half-slot), so `MFETCH`
  opens two slots before `TFETCH`. Addressing cell *N* while `SA9..SA3` names *N−1*
  needs `SA + 1`, which is the adder §6.4.1 forbids — so the map got its own seven-bit
  column counter `MC6..MC0`, loaded from the same `HSCROLL[9:3]` and started a cell
  earlier. `MAPA1/MAPA0` moved from `SA4/SA3` to `MC1/MC0` with it.
- **A fourth arbiter requester, refused in two places.** The span writer collides on
  the card's one internal address bus and stands down for whole map slots; the CPU
  collides per chip and loses only that chip. `arbDesign` is untouched — the gating
  is renames at merge — so it stays executable as a standalone `GAL22V10`.
- **`/WAIT` on reads, for the first time.** §7.4's backstop is write-only by a
  decision made the same day; a map hold has to stall reads too, since a read whose
  chip is pointed elsewhere returns the wrong byte. The two are separated by
  `WAITSRC`/`WAITRW` rather than by relaxing §7.4's rule, and the hold is one 158.9 ns
  slot against §7.4's 40.7 µs.

**A number moved with it.** §6.4.2 said cell mode costs the span writer *"roughly an
eighth"* of its free accesses. That is the per-chip figure (2.0 → 2.25 per cell) and
it is right; but the map takes the shared bus **one slot in two**, and slots are what
the span writer queues for, so its spare slots **halve**. Both numbers are now stated.

**And the fits moved twice in a day.** §6.4.1's correction returned three pins per
part (`vaddr` 64 → 61 of 64, `vctrl` 62 → 59) and §6.4.9's cadence spent them:
`vctrl` **64 of 64 I/O and 120 of 128 cells**, `vaddr` 61 of 64 and 109 of 128. Both
still fit with JTAG reserved. Neither has headroom left.

**What §19 item 15(c) left behind.** Building the cadence needed a fetch window to
place the map fetch against, and `census.ts` listed `FETCH` and `HLOAD` as *"produced
by the sequencer's unfitted decode half"* — nothing generated them, in either mode.
They are two range compares on `hgen`'s counter and are now produced. `ROWADV` and
`VLOAD`, the vertical half, are **not**: item 15(d), and until they exist the row
counter does not step in either mode.

---

**What did not change on the day of the address correction.** Logic-cell occupancy
— `vaddr` 102 of 128, `vctrl` 97 of 128 — and §19 item 15(c), the map fetch's missing
arbiter requester, which the `MAPA` pair made stated rather than latent. Both moved
again hours later when the cadence was built; see the entry above.

---

## §12.1 / §12.2 — "one macrocell" and "one pin"

The VBL interrupt was priced at one macrocell in the sync GALs; it is three — the
OE idiom ties the macrocell's data to a constant so the pending flag is its own
macrocell (`VBLPEND`), and the flag must be set by an edge or it re-arms under its
own handler (`VSDLY`). §12.2's raster timer was written as "feed HSYNC to a spare
pin"; a line *count* is not a line *number*, so VSYNC as a hardware frame origin
became the second pin — resetting in the VBL handler would jitter the origin by
the 48–191 µs dispatch latency, 1–6 lines.

## §13 — register-map remnants

`+$16` `BORDER` was deleted (§9.3: VGA has no overscan, porches must be black for
the back-porch clamp, and the `'153` mux has no spare input for a border index).
`LIST` `+$0B`–`$0D` deleted (above). "`TILEBASE` and `FONTBASE` have no offsets
and the sixteen-byte window is full" resolved twice over: the window is 32 bytes,
and `LIST`'s deletion freed three more. `VMODE` was three bits until the
2026-09-07 fit took the spare code for `CHAR`. `FONTBASE`'s registers went with
Variant B; the byte stays reserved at `+$18`.

---

## §17 — the backplane bullets, as first written

`/IOSEL` was "geographic, per slot" — copied from colormin, where slots have one
64-byte window each. This machine's windows are function-sized and all different,
which no position decode can produce; `audio.md` §9.1 and `ps2.md` §3.2 both
copied "per slot" from here and both then promised a base-address jumper, which a
position decode leaves nothing for (`serial.md` §6 had it right all along).
Corrected in `machine.md` §2. The window bullet then read "$FF40–$FF7F, not just
$FF60–$FF7F" with video and audio as the only owners and "$FF50–$FF5F left for a
disk controller"; three I/O cards filled `$FF50`–`$FF5B`, `$FF5C`–`$FF5F` was
briefly "the machine's only unallocated I/O" before the network card took it, and
the window widened to `$FF00`–`$FF7F` on 2026-09-08. The sound-card note carried
each of audio's IC counts in turn (36 at the split; see `audio/docs/history.md`).

---

## §19 — closed items, as they were argued

**Item 8 (GAL fit)** — the full record, kept for the derivations:

*Scan-address pair*: budgeted at 20 of 20, zero margin (19-bit loadable address +
inter-package carry). Fitted 2026-09-06 at **17 of 20, three spare** — §8 had
described the hardware correctly all along (9-bit row + 8-bit column, phase in the
`'153`s): `A1:A0` are not address bits, and the torus's stride-1024/ring-512
geometry means no inter-package carry exists. `check:scan` asserts both.

*Sync*: budgeted 24 wanted / 20 available; fitted at **27 of 30, three parts**
(`hgen` 10/10, `vgen` 10/10, `vdec` 7/10 at 14 of 14 pins). The three missing
macrocells were all consequences of things the document already said: `VTC` (the
line counter's mode-dependent modulus — a decode that cannot live where the
counter fills its own part), `VBLPEND` (the OE idiom leaves the pin stateless),
and `VSDLY` (the flag must be edge-set — a 6809 enters an interrupt in ~10 µs and
the blanking window is 63.5 µs). The cheapest-looking escape — slot counter to a
`'393` — failed on pins (22 inputs, 16 available), which is where "a counter has
to stay on the same package as the things that decode it" was learned. `vgen` was
the tightest fit in the machine: bit *i* of a ten-bit counter behind a six-literal
enable costs *i* + 7 product terms against the 22V10's palindrome, and only the
sorted pairing fits, with `V9` on 16 terms in a 16-term macrocell.

**Item 10** — the low-power GAL family question (nine ATF22V10C instead of nine
bipolar GALs ≈ half an amp) lapsed with the GALs themselves.

**Item 15 (tile fit)** — the open questions were: spare input pins for the map
byte (answered: three macrocells + two pins spare); tri-state and
linear-vs-concatenated addressing on the GALs; a second fetch cadence on the
sequencer pair. The GAL-era pricing was 89 I/O / 128 of 128 macrocells /
PQFP-160. All of it dissolved into the CPLD build, where the logic was written
(`video.parts.ts`) and fitted.

**Item 16** — §6.4.6 claimed sub-cell scroll "needs a 3-bit offset… new logic";
the three bits are `{SA2, mux phase}`, both already scrolled by §8's preloads.

**Item 17** — the `'AHC165` bench item, gone with Variant B; §14's "stays" note
for the `'165` lapsed too when the serialiser was absorbed into the CPLDs
(§10.1.6's absorption list and `hardware/place/parts.ts` are the record — the
27-IC build has no `'165`).

**Item 20** — the standalone arbiter GAL fit (see §5.2.1 and §10.1.6.3 above).

**Item 23** — closed with the FCLK equations (9 terms, 4 macrocells) and the
register-file decode (21 macrocells, 28 terms — per-register write strobes as
macrocells instead of nine strobe pins, the same trade as `CTRL`). Its closing
paragraph put `vctrl` on a TQFP-100 at 76/80 and 123/128; that lasted less than a
day — §10.1.6.3's `rfa` split returned both CPLDs to PLCC-84.

---

## `features.md` and `video/README.md`

`features.md`'s ⚠ markers tracked the same chains (text-mode pendulum, IC count,
list-engine build) and were cleaned against the entries above. `video/README.md`
carried "~33 ICs" → "41 with 10 GALs" → **30 ICs** — a count written between the
28-IC morning and the 27-IC evening of 2026-09-08 that nothing went back to fix —
now reconciled at **27** (verified against `hardware/place/parts.ts`).


---

## 2026-09-09 — design-review2.md's corrections

### features.md §3.2 — the spare-access headline

**Was:** *"The card has ≈32.4 M spare accesses/s against a CPU that can issue ~420,000
writes/s — **77× more memory bandwidth than the CPU can consume** (`graphics.md`
§2.1)."*

**Why it moved:** `graphics.md` §14.2 replaced the four `AS6C1008` ×8 framebuffer parts
with two `AS6C8016` ×16 on 2026-09-08, which is one spare access per slot rather than
four. §14.2.3 states the new figures — **8.1 M/s and 15×** — and this sentence was not
updated with it. The accesses are up to four bytes wide, which the replacement says.

### features.md §3.1 — the `WMODE` table and two part numbers

**Was:** a three-row table ending at `WMODE 10`, with span-solid's length coming from
*"the `'161` pair's terminal count"* and the mask bit from *"the `74HC165`'s serial
output"*.

**Why it moved:** `features.md` §8.4 added `WMODE 11` (sprite) on 2026-09-09, and
`graphics.md` §10.1.6 had already booked both discrete parts into the CPLDs on
2026-09-08. ⚠ **The replacement carries a ⛔ note rather than simply renaming them**,
because `design-review2.md` §1.2 found that neither block was ever written: the
packages were deleted from §14.1's count and the logic does not exist.

### graphics.md §6.4.6 and features.md §1.4 — the cell row's width

**Was:** *"Cell | `SA17..SA13` — `VSCROLL[8:3]`"*.

**Why it moved:** `SA17..SA13` is five bits, so the field is `VSCROLL[7:3]`. The same
tables' *"⚠ 32 cell rows"* is the giveaway; `[8:3]` would be six bits and 64 rows.
Arithmetic, not a design change.

### graphics.md §14 — the motherboard's census

**Was:** *"the motherboard's own full census … is `hardware/ram.md` §6.5, at **17
ICs**"*.

**Why it moved:** `ram.md` §6.3.1 added the `74HC4040` refresh timebase on 2026-09-09 —
*"the refresh timebase is a package, and it was on nobody's list"* — taking the
motherboard to 18. `machine.md` §0 and `ram.md` both carry 18; this line did not.


---

## 2026-09-09 — the repairs

### §10.1.6 and §14.1 — the four absorptions

**Was:** *"`CTRL`'s `'273` (+8), the `'161` `SPANLEN` pair (+10) and the `'165` (+8) fit
easily"*, booked as **−4 packages** in the 27-IC count.

**Why it moved:** none of the three was written, and one of them cannot be. §7.4 loads
the length counter from the **register file's read bus** — it has to, because a
span-solid is issued with `SPANLEN` written once and the length persists across spans —
and that is eight pins neither CPLD has. `CTRL`'s `'273` and the `'165` are on `vctrl`;
the `'161` pair is `vlen`, one `GAL22V10`, and the card is **28 ICs**. §14.1's row is
−3 now, with `vlen` as its own line. `design-review2.md` §1.2 and §10.

### §10.1.6.1 — `HPOL`

**Was:** *"§12's four codes are 70 Hz at `VMODE0 = 0` and 60 Hz at `VMODE0 = 1`, and the
70 Hz pair is the positive-H pair, so `HPOL = !VMODE0`."*

**Why it moved:** the 70 Hz pair is the positive-**V** pair. §6.2.1's own table has
HSYNC negative in both families, which is also the VGA standard, and `sync.jedec.ts`
said so all along. `VMODE 01` and `VMODE 11` were emitted as +H/−V, which is not a
standard combination at 31.5 kHz.

### §10.1.6 — the partition's headroom

**Was:** *"`vctrl` is at 64 of 64 I/O and 122 of 128 cells, `vaddr` at 61 of 64 and 109
of 128. Both still fit, JTAG included, and neither has room for the next thing."*

**Why it moved:** it had room for eighteen more cells, and the way to find them was not
a rewrite. `vaddr`'s address mux has four sources and `vctrl` was exporting all four
selects; they are mutually exclusive, so `SRC1:SRC0` names them and `vaddr` decodes them
back for nothing. Two pins, and `vctrl` fell to **104 of 128**. `vaddr` rose to 122 with
the map pipeline and the reload walk, and is the tight part now.

### §19 item 23(b) — the register file's read-back walk

**Was:** a two-bit walk on `FP1:FP0` presenting `SPANLEN`, `WFG` and `WBG` in turn while
the span writer was idle — *"two deferrable file reads that fetch all three for the next
span"*.

**Why it moved:** nothing produced `FP0` or `FP1`, nothing received the three values, and
every term carried `!SPANBUSY` — so **during** a span the file address was `$00` and the
span writer would have retired `CTRL`'s byte into the framebuffer. §7.4's own sentence
replaces it: the file is addressed live and the mask bit is `RA0`. The walk survives for
the one job it was right for, §7.2's column reload, where it points the file at `+$08`
and `+$09` for two dots.
