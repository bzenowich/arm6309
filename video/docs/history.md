# Video — archived history

Superseded material removed from [`graphics.md`](graphics.md) and
[`features.md`](features.md) when the documentation was split into present design
and archived history on 2026-09-08. The present design is in those documents; this
one records what they used to say and why each claim changed. Section numbers refer
to `graphics.md` unless marked otherwise. "Vid-*" identifiers are findings of the
2026-09-04 review, [`docs/design-review.md`](../../docs/design-review.md).

---

## §5.2.1, §7.4, §13 — the three defects the first running machine found (2026-09-10)

On 2026-09-10 the video card was put in a slot behind a **cycle-accurate 6809E core
running the boot ROM's own instructions** for the first time
(`hardware/gal/verilog/machine_tb.sv`, `software/boot/boot.asm`). Twelve testbenches
and 543 model claims had passed against this card for two days. The machine did not
reach its second span.

**All three defects are seams between parts that are individually correct**, and all
three were invisible to every check that existed, for one reason each:

| | Why nothing saw it |
|---|---|
| **item 36** — the arbiter refused the span writer the chip the CPU's own stalled write was selecting, so the span could not finish, so `/WAIT` never released | `vspan_tb` drives `E` from a free-running counter. **Its CPU cannot be waited**, so `VRAMSEL` always went away on time and the loop could not close |
| **item 37** — `SPANBUSY` was set by a level over `E`-high, which `/WAIT` makes unbounded | The same. A six-dot `E`-high is bounded and the level is harmless; only a *stretched* cycle exposes it, and nothing could stretch one |
| **item 38** — any CPU access to `$FF60`–`$FF7F` took the register file away from the running span, and §7.4's colour path **is** the file's address | `regfile.check.ts` **asserted the defect**: it swept `SPANBUSY` and required the CPU to win in both states, "span running or not" |

### §5.2.1's grant rule — what it used to be

```
  GRANT_CPU[n]  = VREQ . (CPUCHIP == n)
  GRANT_SPAN[n] = SPNREQ . (SPNCHIP == n) . /GRANT_CPU[n]
```

**`VREQ` is now qualified on `R/W`.** A CPU VRAM *write* is posted (§3.1.1) — the byte
goes into a `'574` and the span writer retires it at `WPTR` — so it never needs a
framebuffer access of its own. Claiming one closed this loop:

```
  the write starts a span         -> SPANBUSY
  SPANBUSY + a CPU VRAM write     -> /WAIT, and U6 holds E HIGH
  E held high                     -> VRAMSEL stays asserted all cycle
  VRAMSEL asserted on this chip   -> GSPN is 0, the span never retires
  the span never retires          -> SPANBUSY never clears -> /WAIT never
                                     releases -> the machine stops
```

Cost: one literal on four cells, one product term on `GSPN` and on `SPNGRANT`.
`access.check.ts` sweeps `R/W` now — it was **held at 0**, which is CLAUDE.md's third
trap, and holding it is precisely why the check could not see this.

### §7.4's `WSTB` — the edge that was a level

`WSTBV = VRAMSEL & /RW & E` is correct for three of its four consumers and wrong for
`seqctl`'s `SPANBUSY`, which is set on `WSTB # SPANBUSY & !SPANEND`. Under `/WAIT` the
level re-set it on every dot of the span's own wait: `SPANEND` fired, `SPANBUSY`
cleared for one dot, the level set it again, and `WPTR` walked on for ever.

⚠ **An `E`-rise pulse was tried first and it is wrong twice over** — the CPU has not
driven its data yet, and it starts the span inside the CPU's own bus cycle, so the
first byte retires against an empty latch. `vspan_tb` reported every span retiring one
byte short. **The edge is `E`-fall**, which is what §3.1.1 always said: *"all four
`'574` clock on the same inverted E"*. `WPQ` (registered) and `WSTART` are the two
cells, and every other consumer keeps the level.

### §13's register file — who owns the address during a span

The CPU's claim is qualified on `!SPANBUSY`. The picture the machine drew had a
**three-pixel hole in every span** — three, because a retire is one per four dots and a
bus cycle is twelve — at the point in each span where the CPU's `VSTAT` poll landed.

⭐ **It gives product terms back.** The span's three gated terms collapse to one,
because "the CPU is not taking it" is implied by `SPANBUSY` itself: `RA1` goes from
four product terms to two, `RA0` from ten to eight.

### §19 item 35 — `BLANK` and the five dots nobody had charged for

Found by the same run, and only after the first three were repaired: with a picture on
the connector at last, every colour boundary in it was five dots right of where the
framebuffer said. §6.1's dot path is `'153` mux → pixel-index `'574` → 15 ns LUT →
post-LUT `'273`, and `BLANK` came straight off hgen's H counter with no matching delay.

⚠ **`sync.timing.ts` counts SLOTS, four dots each** (`H.backEnd` = 35,
`H.activeEnd` = 195), so every horizontal boundary is a multiple of four and moving
the constants can buy four dots and never five. The delay is the fix.

⭐ **And it costs no pin.** `BLANK`'s only consumer is the post-LUT `'273` pair's
asynchronous `/MR`, so `vctrl` exports the delayed copy and `BLANK` itself becomes
buried — five registered macrocells, zero pins.

`vsync_tb` used to assert `BLANK == HBLANK # VBLANK`, which is exactly the defect
written as a claim. It asserts the delay and its **depth** now, and that four and six
both fail.

### What the repairs cost the parts

| | before | after |
|---|---|---|
| `vctrl` logic cells | 98 of 128 | **104 of 128** |
| `vctrl` flip-flops | 45 | **51** |
| `vctrl` I/O | 64 of 64 | **61 of 64** |
| `vsup` I/O | 58 of 64 | **54 of 64** |
| `vctrl` cascades | 1 | **11** |

⚠ **The I/O drops are the fitter's placement and not headroom the design asked for**,
and the cascade count is a timing change even where the cell count is flat. Both parts
re-fit with *"Design fits successfully"*; `gal/cpld/vctrl.fit` and `vsup.fit` are the
authority.

---

## §9, §19 item 9 — the `74HC593` `PIDX` counter (closed 2026-09-09)

§9 carried minimal256.md §6.1's sourcing flag verbatim, and §19 item 9 carried it as an
open supplier question:

> **Sourcing flag carried over:** minimal256.md §6.1 notes the `74HC593` (loadable,
> 3-state counter) is the thin part of the BOM, and that the easier `'590`
> substitutes only at the cost of single-entry palette patching. Confirm
> availability before freezing the register map — that item transfers unchanged.

> 9. **`74HC593` availability** (§9). **carried**, and it is still in the BOM as
>    `PIDX` — one package, and §9's palette-index path is built around its loadable
>    count.

**The answer is that the part is discontinued**, with no widely available
pin-compatible replacement, so the item closes as a design decision rather than a
sourcing worry. `PIDX` is two `74AHCT163A` and one `74AHCT244`; §9 has the resolution
and §13.1 the reduced snow rule that follows from it.

⚠ **AND ONE VERSION WAS BUILT AND REVERTED, which is the interesting part.** `PIDX`
was first implemented as **eight macrocells inside `vsup`** — a loadable counter with a
product-term output enable driving the LUT's address bus directly. It fitted, at **66
of 128 cells and 61 of 64 I/O**, and it deleted the package outright. It was reverted
because those eight pins are the difference between a part with 3 spare I/O and one
with 8, and:

> on this card every block that could not be built was short of PINS and never of
> macrocells — `vlen` needed eight on the register file's read bus, `pxsel` needed two
> `vctrl` could not export, §9's palette write path needed seven.

Three packages were spent to buy eight pins back, deliberately, because **blitter room
is a pin question on this card and not a macrocell question**. `vsup` at 84 of 128
cells and 58 of 64 I/O is the cleanest evidence of that shape the project has.

---

## §14, §14.1 — the card at 28 ICs, and the two-CPLD build (superseded 2026-09-09)

§14 opened:

> **The card is 28 ICs: 2 CPLDs, 2 GALs, 4 SRAMs and 20 packages of 74-series** —
> against colormin's 39 (35). ⚠ **It was 27 until 2026-09-09**, and the extra package
> is §7.4's `SPANLEN` counter, which §14.1 had deleted as absorbed and which no design
> file contained.

and §14.1 derived 28 from the GAL build's 41. The build is **36 ICs on a 24 cm board**
now, and the whole of the growth is §8.2's second rank of fetch latches, §9's palette
write path and §10.3.3's descriptor buffer — features §8, §9 and §10.3 had specified
and that had no hardware. §14.1 has the line-by-line derivation.

**Also superseded: "the card is 27 ICs and one GAL"** (§10.1.6.3) and
**"2 × `ATF1508AS` PLCC-84 + 1 × `GAL22V10`"** (§0, §10.1). `rfa`, `vlen` and `pxsel`
are all inside `vsup` (§10.1.7): the card has **no `GAL22V10` at all**.

**And the board length went back.** §14.2 recorded *"`hardware/place` puts it on an
18 cm board instead of 24 — the same length as the audio card"*. Thirty-six packages do
not place on 18 cm; `npm run check:place` is the authority and it now asserts 24.

---

## §14 — the `vlen` `GAL22V10`, and why `SPANLEN` had to be in the register file (superseded 2026-09-09)

`vlen.jedec.ts` and §14 both argued that the span-solid length counter could not go
inside either CPLD:

> ⚠ **AND IT CANNOT GO INSIDE EITHER CPLD, for one reason: 7.4 loads it from the
> REGISTER FILE, not from the CPU bus.** It has to, and that is not an implementation
> detail — a span-solid is issued as "WPTR x3 + the posted write" with SPANLEN written
> once (7.3's full-screen clear is 500 spans and one SPANLEN), so the length has to
> persist somewhere across spans, and the register file is where 19 item 23(b) put it.
> Loading it means eight pins on the register file's read bus, and vctrl is at 64 of 64
> I/O while vaddr is at 61 of 64 with three. Eight pins is the whole story.

**The premise was persistence and the conclusion did not follow.** Eight macrocells
persist exactly as well as eight SRAM cells, so §10.1.7's `vsup` holds `SPANLEN`
itself, written from `+$05`; the file's byte still reads back and nothing reads it. The
read bus stops being the load path and the eight pins stop being the obstacle.

⚠ **It also removed a hazard rather than only a package.** `vlen` loaded at `WSTBV` —
a posted VRAM write — from whatever `rfa` had the file pointed at, which is why `rfa`
carried an idle state holding the address at `+$05` and why the load carried
`!SPANBUSY` ("without this literal the counter would reload from the colour byte on
every later edge of the same strobe"). A register that is never anything else needs
neither.

---

## §10.3.2 — what a list `MOVE` could reach, and the premise behind it (superseded 2026-09-09)

The reachability table had two ⭐ rows and four ⚠ ones, and the argument under it read:

> **The binding constraint is pins, and it chose the format.** The engine is on `vaddr`,
> so a `MOVE` can only write a register `vaddr` itself holds — every other target needs
> an input pin on a part that has none. §19 item 32 called this affordable because
> "`vctrl` has 24 spare macrocells"; ⛔ **that premise was wrong — the engine is not on
> `vctrl`**, and `vctrl`'s spare *cells* are unreachable behind its full *pin* budget.

> - **A list MOVE scrolls in units of four pixels**, because `HS0`/`HS1` — §8's mux
>   phase — are on `vctrl` and unreachable. ⭐ This costs nothing: §19 item 28 is that
>   the fetch latches cannot deliver two live groups, so **four pixels is what the card
>   displays at any scroll value**.

> - ⚠ **Per-scanline palette** — raster bars, gradient skies, more than 256 colours on
>   screen at once. **Not reachable.** `PIDX`/`PDATL`/`PDATH` are off-chip at the `'593`
>   and the LUT, and the engine has no pin to them. (`features.md` §4)

**Both limits are gone.** §8.2 made the card display byte-granular scroll, so "four
pixels is what the card displays" stopped being true; §9 built the palette write path
and §10.1.7 put it on the part that decodes the descriptor. A `MOVE` now reaches
`+$03`, `+$04`, `+$10`, `+$11` and `+$12`. The one that remains unreachable is `CTRL`,
and §10.3.4 replaces the pin-count explanation with the real one: `vctrl`'s data pins
tap the **backplane** bus, not the one a descriptor operand arrives on.

---

## §8, §19 item 23(a) — per-chip `FCLK` for byte-granular scroll (deleted 2026-09-09)

§8 carried this box, and `seqph.jedec.ts` carried the nine product terms behind it:

> **Byte-granular scroll is what forces per-chip fetch-latch clocking.** Chip *n* holds
> the byte at the column where `c mod 4 = n` … §5.2.2's *per-chip* clocking is the fix:
> chips `0..p−1` take the next group's byte on a late clock while `p..3` still hold
> this one. The four `FCLK` equations are a phase-dependent offset rather than four
> copies of one term — 9 product terms, no new package (§19 item 23, closed).

⛔ **It cannot work, and the arithmetic is one sentence: a latch clocked once per slot
always holds the most recent fetch, whichever edge you pick.** Two live fetch groups
need two ranks of latch. §8.2 is what replaces it — rank A and rank B in series with a
per-chip **output enable**, because `c < HSCROLL[1:0]` is constant for a whole line —
and the four `FCLK` equations collapsed to one signal, which is 5 product terms and 6
macrocells back on `vctrl`.

⚠ **And the old scheme was actively wrong once the ranks existed.** `vaddr_tb`'s pixel
check reported chip 3 alone wrong at `HSCROLL[1:0] = 0` — the one chip the p-dependent
phase still moved.

---

## `seqph.jedec.ts` — `SLOTTICK` at dot 3 (superseded 2026-09-09)

`SLOTTICK` was `PH1 & PH0`, the last dot of a slot, and `video.parts.ts` explained the
counter-enable rule in terms of it:

> SLOTTICK is one dot wide (dot 3), so the increment lands on the slot boundary. Every
> counter enable on this part carries it; a LOAD does not, because a load is
> idempotent.

⚠ **It moved to dot 0 by accident** — an unguarded whole-file replace during §8.2's
`FCLK` rewrite caught `terms: ["PH1 & PH0"]` here too — **and it is kept on the
merits.** Put back and measured, dot 3 gives **636 of 640 pixels wrong** at `HSCROLL 0`
and 159 of 160 tile addresses wrong. A counter advances on the edge that *ends* the dot
its enable is high in, so dot 0 puts the advance one dot **after** `FCLK`'s rising edge
and dot 3 puts it on the same edge, under the latch. The deleted per-chip `FCLK` scheme
hid that by clocking two of the four chips a dot later.

⛔ **AND IT MADE `vsync_tb` HANG RATHER THAN FAIL.** Its frame-start wait read
`SLOTTICK == 0 && PH == 0`, which named the first dot of a slot while the tick was at
dot 3 and became **unsatisfiable**. A `forever` with no bound is a hang and not a
failure: `run.sh`'s exit code cannot see it, the claim count cannot see it, and it
presents as "budget more time". Two agents spent half an hour of CPU apiece on it. The
condition is `PH == 0` alone.

---

## §10.3 — `BCTRLGO` set `LRUN` directly (superseded 2026-09-09)

`LRUN` read `BCTRLGO # LRUN & !LSTOP`, so the engine started on the **first** dot inside
E-high of the write to `+$0E`. Two defects hid behind that:

- ⛔ E is high for six dots at 2.1 MHz and a spare access is granted every four, so the
  engine took its first grant **while the CPU was still driving the card's internal data
  bus** — and §10.3.3's `'244` stands off for exactly that reason. Simulated: the list's
  first opcode was the CPU's own `$01`. §10.3.1's rule forbids every *other* collision on
  that bus; it cannot forbid the write that turns the engine on.
- ⛔ **A list could not be started twice.** `LD` holds the last byte fetched, so after a
  list terminates it holds the terminator — and `LSTOP` is a function of `LD` and `LRUN`
  alone, so the instant `LRUN` rose again `LSTOP` was already true. The level-wide
  `BCTRLGO` hid it by re-asserting `LRUN` for six dots until a grant happened to land
  inside the write and overwrite `LD`; **whether a second list ran depended on where the
  grant fell in E.**

`LGO` latches the GO, holds while the write is in flight, hands over on the dot `WSTB`
falls, and clears the descriptor state as it does.

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

## 2026-09-09 — §19's closed items, moved out of the spec

Until this date §19 carried its closed items in full, interleaved with the open
ones — sixteen of thirty-two, and the section read as a project history rather
than a work list. The spec now carries **only what is verifiably open** (§19.1–19.5)
plus a one-row-per-item table of what closed and where the argument lives (§19.6).

**The numbers are not reused.** Other documents cite `§19 item 8`, `§19 item 23`,
`§19 item 28` and so on by number, and those citations resolve here.

⚠ **Two of these closed and were later superseded**, and the superseding is the part
worth carrying forward:

- **Item 23(a)** ends "Byte-granular horizontal scroll is a design." **It is not.**
  §19 item 28 (2026-09-09) is the arithmetic that says one latch rank cannot hold two
  live fetch groups whatever the clock edges do, and item 23(a)'s phase qualification
  was only the first half of the mechanism. Item 28 is still open.
- **Item 32** was closed on the day it was raised, but its own costing was wrong: it
  said "`vctrl` has 24 spare macrocells now, which is the first time this has been
  affordable". ⛔ **The engine is on `vaddr`, not `vctrl`** — `vctrl`'s spare cells sit
  behind a full 64-of-64 pin budget and cannot be reached. §10.3.2's format is what
  fits the part the engine is actually on.

Each item below is its text as it stood in the spec on 2026-09-09.

### Item 4 — closed 2026-09-06 (location) and 2026-09-09 (register set)

4. **The MMU's location — closed, §6.3.1: on the motherboard, 5 ICs.** The deciding
   argument was one 48-pin SKU across the CoCo 3 drop-in
   and this machine, not the address path. What it leaves open is the register set
   itself (`machine.md` §5 item 3),
   which is now a free design with no GIME to copy, and which is what the write-decode
   GAL needs before it can be fitted — **including the break-before-make sequencing of
   §6.3.1's map-write table**, which is that GAL's hardest equation.

### Item 8 — closed 2026-09-06

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

### Item 12 — closed 2026-09-06

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

### Item 15 — closed 2026-09-08

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

### Item 16 — closed 2026-09-08

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

### Item 17 — closed 2026-09-08

17. **The Variant-B serialiser bench — closed 2026-09-08: Variant B is not built**
    (§6.4.3, §10.1.6.2). The serialiser on §6.1's 11.7 ns margin was its own risk
    and it went with it; the span-mask serialisation itself lives inside the CPLDs
    (§10.1.6, §14).

### Item 20 — closed 2026-09-06

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

### Item 23 — closed 2026-09-07

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
    122 of 128 cells, `vaddr` at 61 of 64 and 109 of 128 (§10.1.6.3, §14, the
    `hardware/gal/cpld/*.fit` files).

### Item 24 — closed 2026-09-09

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

### Item 25 — closed 2026-09-08

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

### Item 26 — closed 2026-09-09

26. **⭐ CLOSED 2026-09-09 — everything §10.1.6 books as absorbed now exists, and the
    card fits.** Eleven signals were inputs to fitted parts with no producer anywhere:
    the mask serialiser, the `SPANLEN` counter, `CTRL`'s and `VSTAT`'s write strobes,
    `HSCROLL[1:0]`, `WADV`, `SPNREQ`, `BCTRL`'s `GO`, the register file's read-back
    selects and the list engine's grant. All are designs now, and
    [`../../docs/design-review2.md`](../../docs/design-review2.md) §1.2 is the census
    that found them.

    **What it cost is one package and one encoding.** The `'161` pair could not be
    absorbed — §7.4 loads it from the register file's read bus, which is eight pins
    neither CPLD has — so it is `vlen`, a `GAL22V10`, and the card is **28 ICs**. The
    room for the rest came from encoding `vaddr`'s four mux-source selects as two bits
    (§14.1): `vctrl` fell from 122 to **104 of 128** cells and `vaddr` rose to **122**,
    both fitting a PLCC-84 with JTAG.

    ⚠ **`vaddr` is the tight part now** — six cells and three pins — and §14.2's two ×16
    framebuffer parts are still the relief that exists on paper (item 25).

### Item 27 — closed 2026-09-09

27. **CLOSED 2026-09-09 — `HPOL` is a constant**, as §6.2.1 and `sync.jedec.ts` always
    said. `VMODE 01` and `11` were emitted as +H/−V.

### Item 29 — closed 2026-09-09

29. **CLOSED 2026-09-09 — the map byte is a two-stage pipeline** (§6.4.9). One register
    provably cannot hold a code across the two slots that need it while a new one
    arrives in the middle; `MAPQ` is the second rank and `CELLTICK` the handover.

### Item 30 — closed 2026-09-09

30. **CLOSED 2026-09-09 — the posted-VRAM-write strobe exists** (§7.4). `WSTBV` on
    `vctrl`, one macrocell.

### Item 31 — closed 2026-09-09

31. **CLOSED 2026-09-09 — `WADV`'s column reload is built** (§7.2), as this section's
    own "two deferrable file reads": `rfa` points the register file at `+$08`/`+$09` for
    two dots and the counter loads through the path the CPU's write already uses. ⚠ Ten
    shadow registers on `vaddr` — the obvious alternative — is what the fitter refuses.

### Item 32 — closed 2026-09-09

32. **⚠ OPEN — the display list has no descriptor format.** The engine walks and
    terminates since 2026-09-09 (§10.3), and every fetched byte is a `MOVE` that names
    no register and carries no operand, with no scanline compare anywhere. `features.md`
    §4's per-scanline `HSCROLL`, palette and mode changes need an opcode, an operand and
    a raster compare, and none of the three is designed. **`vctrl` has 24 spare
    macrocells now**, which is the first time this has been affordable.

---

## 2026-09-09 — §10.3 / `features.md` §4: the display list got a format

### §10.3 — "what is still not designed is the descriptor format"

Replaced by §10.3.2. The callout read:

> ⚠ **What is still not designed is the descriptor format.** Every fetched byte is a
> `MOVE`, nothing names a register or supplies a value, and there is no scanline
> compare — so what runs is a byte-fetcher that stops at `$FF`, and §4's per-scanline
> `HSCROLL` needs an opcode, an operand and a raster compare that no design file
> contains. **§19 item 32**, and it is a design task rather than a wiring one.

**What the format cost, and what it could not buy.** Two macrocells of state (`LPH`,
the opcode/operand phase, and `LWAIT`) plus two decode cells, minus `LD5` and `LD6`
which nothing read — `vaddr` from 122 to 124 of 128. The scroll registers gained a
second write port at one product term per bit and no macrocell.

⛔ **`VSCROLL` was built with the same second port and the fitter returned
`INTERNAL ERROR` in pass 1** — nine more cells at a third term each, on the part that
is at 96 %. It is not in §10.3.2's reachable set for that reason and no other.

⛔ **And §19 item 32's own costing was wrong.** It said "`vctrl` has 24 spare
macrocells now, which is the first time this has been affordable". The engine is on
**`vaddr`**; `vctrl`'s spare cells sit behind a pin budget at 64 of 64 and cannot be
reached from it. The format that got built is the one that fits the part the engine is
actually on, which is why `MOVE` reaches two registers and not thirty-two.

### §10.3 — "what is not settled here is the interaction with `WADV`"

Replaced by the `!LRUN` gate on `WROWADV` (§19 item 24). The paragraph read:

> ⚠ **What is not settled here is the interaction with `WADV`.** §13's `+$14` changes
> what `WPTR` does on increment, and the engine's own walk is a plain +1. A driver that
> leaves `WADV` in vertical mode and then starts a list would have the engine step by
> the stride. **`BCTRL.GO` should force `WADV` to 00**, which is one product term on
> `vctrl` and is not built — it is filed as §19 item 24 rather than assumed.

The item's own fix was not the one taken: `BCTRL.GO` would have needed `BCTRLGO` as an
input pin on `vctrl`, which is at 64 of 64 I/O, and would have covered only the instant
the list starts. Gating `WROWADV` on `!LRUN` costs **one literal on each of two terms
that already existed** — no macrocell, no product term, no pin — holds for the whole
walk, and leaves the register intact so §10.3.1's reload rule stays one clause.

### `features.md` §4 — "what it buys", as first written

All three bullets were unqualified, and two of them are not reachable:

> - **Per-scanline `HSCROLL`** — parallax layers, sine warps, split-scroll status bars.
> - **Per-scanline palette** — raster bars, gradient skies, more than 256 colours on
>   screen at once.
> - **Mid-frame `CTRL` changes** — §6.4.6 spells out the good one: **a text status bar
>   over a bitmap playfield**, because the cell/pixel mode is a register and the list can
>   write it at a scanline boundary.

The palette is off-chip at the `'593` and the LUT; `CTRL` is `vctrl`'s macrocells and
`vctrl` has no input pin left. Both stay CPU work from a raster or VBL handler. The
comparison table's **"per-region mode mixing — the list engine switches it per
scanline"** and **"per cell colour ... or per scanline region from the display list"**
were the same claim in two more places and are corrected with it.

