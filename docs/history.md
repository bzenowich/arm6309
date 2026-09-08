# The machine — archived history

Superseded material removed from [`machine.md`](machine.md) and
[`video-comparison.md`](video-comparison.md) when those documents were cleaned to
present-design-only (2026-09-08). Entries are organized by spec section; each records
the text or value chain that was removed and what replaced it. Dates are preserved as
the documents recorded them. [`coco3_c64.md`](coco3_c64.md) contributed nothing here —
its ⚠ marks are live confidence caveats, not revision history.

The review that produced most of the 2026-09-04 amendments is
[`design-review.md`](design-review.md), itself now an archived record.

---

# Part I — `machine.md`

## §intro — from pure collation to a document that decides (2026-09-04)

The document's original charter, and the amendment that broke it, read:

> **This document does not get to invent anything.** Where a card spec says "propose"
> rather than "take", it is recorded here as a proposal. Where two documents disagree,
> the disagreement is recorded rather than resolved.
>
> ⚠ **Amended 2026-09-04 by `docs/design-review.md`.** That rule held while this
> document was only a collation. The review found things no card document could have
> found from inside itself — chief among them that **the machine as specified could not
> execute its first instruction** — and a collation cannot fix those by citing somebody.
> So this revision *does* decide, in four places: the boot and vector story (§7), the
> `/IOPAGE` inhibit (§2), system RAM (§7.1), and the E rate (§1). Each is written as a
> decision, with its rationale and the alternative it beat, and each is marked.
> Everything else in this document still only reports.

Replaced by a present-tense charter naming the same four decisions. The opening also
said "the project now has three card specifications" (plan, graphics, audio); six card
specifications exist and the intro now lists all of them plus the CPU plan.

## §0 — value chains in the one-table summary

Kept current values only; the chains were:

| Row | Chain | Notes |
|---|---|---|
| CPU package | LQFP48 → **UFQFPN48** | "not the LQFP48 this table named until 2026-09-04 (§5 item 6)" — `design-review.md` §Cpu-C1: the pinout's pins are not bonded out on the LQFP48 |
| Address space | 1 MB → 2 MB → **32 MB (A0–A24)** | 1 MB was `graphics.md` §6.3's whole map; 2 MB was §5 item 1 option D (physical `A20`, 2026-09-08); 32 MB is `hardware/ram.md` §5.2's 16-bit map entries, same day |
| System RAM | 512 KB of SRAM → 2 MB of SRAM → **four 30-pin SIMM sockets, 4–16 MB of DRAM** | the SRAM stages are §7.1's history below |
| Video ICs | 41 → 31 → 28 → **27** | see §8 below for the per-step reasons |
| Storage ICs | 7 → **14** | the block buffer (§5 item 7) |
| Storage rate | 528 → **681 KiB/s** | |
| Storage period status | "The machine's one period exception" → **"the first of two"** | `net.md` §12 declared 10BASE-T-without-a-PHY the second period exception, 2026-09-07 |
| Net ICs | 16 → **12** | the same week's buffer work; the `DP8390`-shaped register-file argument became moot (§3 below) |
| Total silicon | 106 → 124 → **110**; motherboard 9 → 18 → **14** | "re-derived 2026-09-08 by adding the six card documents up, which nothing had done" — see §8 below |

The storage row also carried: "Its block buffer moved into `A20 = 1` on 2026-09-08 and
took the `TFM` hazard with it." The buffer's location and the hazard retirement are
present design (§5 item 7, item 1 D); only the move date is history.

## §1 — the oscillator was budgeted on the video card (fixed 2026-09-04)

> ⚠ **The oscillator is on the motherboard, and `graphics.md` §14 used to budget it on
> the video card.** Both cannot be true, and the motherboard is the right answer: if the
> can sat on the video card, pulling that card would kill E and stop the CPU — fatal for
> exactly the bring-up sequences that run *before* video exists (`sdcard.md` §12 step 0,
> and any serial-first DriveWire boot).

The rationale survives in §1 as a plain statement; the "used to budget it" conflict is
resolved — the motherboard owns the can.

## §1.1 — the ÷12 decision's review trail (2026-09-04)

The decision block opened:

> **Decided 2026-09-04. This was §5 item 4, and the answer is worse than that item
> expected.** The item asked only that a default be *stated* rather than inferred. The
> review priced the alternative and found that **three independent things break at ÷8**,
> in three different subsystems, none of which had checked it.

The serial row of the breakage table noted that `serial.md` §3.3 "had only ever checked
2.0979 MHz"; the CPU row's `t_cyc` finding was the one "nobody had checked".

The **naming** paragraph's origin story:

> Neither is called "stretch": `graphics.md` §3.3 and `machine.md` §1 used that one word
> for those two opposite things, which is how `serial.md` §3.3 came to offer `/WAIT` as
> an escape hatch from a mode `/WAIT` cannot escape.

The terminology rule (fast-E mode vs. wait state) stays in §1.1; the account of how the
confusion arose is archived here.

## §2 — backplane table rows added or corrected in revision (2026-09-04, 2026-09-08)

- `/IOSEL` row read "geographic, per slot" until 2026-09-06 — **four documents said
  it** — then "the `$FF40`–`$FF7F` window strobe" until 2026-09-08's widening. See the
  `/IOSEL` entry below.
- `/HALT` "was missing from this list, which meant it had no owner and would have
  floated" — added 2026-09-04; it was already in the CPU module's pin budget
  (`graphics.md` §6.3.1).
- `HSYNC`, `VSYNC` were "added in this revision" (2026-09-04) — §12.2's raster-compare
  timer counts HSYNC and needed a frame origin.
- Audio `L`, `R` + 2 grounds were "added in this revision" — `graphics.md` §17
  instructed the backplane to carry them and the table omitted them.
- `A20` joined the address rows on 2026-09-08 (§5 item 1 D), on slot position A34,
  "the position that used to be the backplane's one spare".

## §2 — the physical-map carve: `A19` alone → `A20:A19` → `A24..A19` (2026-09-08)

The quadrant table was "re-carved 2026-09-08 by `hardware/ram.md` §5.2 so the
motherboard's three reserved SRAM footprints could be populated" — and then the same
day's §6.2 deleted the DIP SRAM entirely, so the footprints the re-carve was for never
shipped. The carve itself (a 32 MB map in 512 KB quadrants) stands. The table's
annotations "unchanged" (VRAM ring, card buffers) and "⚠ no RAM here any more" (the
bottom quadrant, which had been 512 KB of system SRAM) recorded the transition:
**`VRAM` keeps `A20:A19 = 01` and the card regions keep `A20 = 1`, so no card changes
address and the video card is untouched** — that invariant is why the re-carve cost
zero card changes.

## §2 — `/IOSEL`: "geographic, per slot" was never compatible with the base jumper (decided 2026-09-06)

The full account, condensed in the spec to the decision and the collision hazard:

> **Four documents said "geographic, per slot"**, and the phrase cannot mean here what
> it meant where it came from. In colormin it really is geographic.
> `~/code/colormin/docs/backplane.md` §3 gives each of four slots its own **64-byte**
> window — `$3F00`–`$3F3F` through `$3FC0`–`$3FFF` — decoded by slot position on a
> common pin. Four slots, four identical blocks, and which card sits in which slot *is*
> the address decode.
>
> This machine's windows are function-sized, not slot-sized, and no two are alike.
> Decode by position cannot produce them. It would have to nail each slot to a fixed
> window, which means every card has exactly one slot it will work in — and at that
> point the **base-address jumper** that `audio.md` §9.1 and `ps2.md` §3.2 each promise
> *in the very next sentence* selects nothing, because nothing is left for it to select.
>
> **The two sentences were never compatible.** "Geographic, per slot" and "so the base
> is a jumper" are alternatives, and three documents wrote both without noticing.
>
> **`serial.md` §6 is the card that got this right**, and it did so without remarking on
> it: its decode GAL takes `CS0`/`/CS1` "from geographic `/IOSEL` **and `A2`–`A5`**".
> That is the window-strobe model, written down, in the one document that also never
> claimed the geography.

Found while drawing the backplane — `hardware/README.md` finding 2.

## §2 — the window strobe's numbers moved with the widening (2026-09-08)

As decided on 2026-09-06 the strobe was the **`$FF40`–`$FF7F`** window: the `/IOPAGE`
term "further qualified by `A7,A6 = 01` — one more product term", with a card decoding
`A0`–`A5`. The annotation recording the change:

> ⚠ **Both halves of that paragraph moved on 2026-09-08, in opposite directions.** §5
> item 1 option A widened the window to **`$FF00`–`$FF7F`**, so the qualification is
> `A7 = 0` — **one product term *fewer*, not one more** — and **a card decodes
> `A0`–`A6`, seven bits**, because `A6` is no longer supplied by the strobe. A six-bit
> card answers at its base and 64 bytes below it. The mechanism is unchanged; the
> numbers are not.

## §2 — the `/IOSEL` equation was wrong from the day it was written until 2026-09-08

> ⚠ **And the equation that implements it was wrong from the day it was written until
> 2026-09-08.** `gal/clkdec.pld` read `/IOPAGE · A7 · /A6` — A7 = 1, A6 = 0, which is
> **`$FF80`–`$FFBF`**: the MMU's own two windows and the CPU module's vector RAM.
> `$FF40`–`$FF7F` is A7 = 0, A6 = 1. **Every card's `/IOSEL` fired on an MMU
> block-register write and never on the card window at all** — six cards driving
> `D0`–`D7` against the MMU, which is the `/IOPAGE` failure mode arriving from a third
> cause.
>
> **Five artefacts carried it and agreed with each other**: `clkdec.pld`, `clkdec.v`,
> `clkdec.jedec.ts`, `clkdec.model.ts` and `hardware/gal/README.md`. What let it survive
> is that `clkdec_tb.sv` **asserted the wrong sense under a message stating the right
> one** — `a7 == 1 && a6 == 0` printed as *"the I/O page with A7,A6 = 01"* — and the
> implementation was written from the assertion. Fifteen passing claims, and the prose
> beside them was correct the whole time.
>
> The lesson is the one `gal/jedec/cupl.check.ts` already draws about a second
> implementation, one step further out: **a check written from the same understanding as
> the design tests the understanding, not the design.** The replacement claim is the one
> that could not have been written wrong in the same direction — sweep A6 and require it
> to have *no effect* — and it is now in the testbench beside the range check.

## §2.1 — the electrical section was new on 2026-09-04

> **New in this revision.** Every item here is a signal or a part that every card's
> document assumed existed and that no document owned. `design-review.md` §Sys-M4.

Individual rows recorded: bus voltage was "only ever inferable before now, from each
card's separate HCT-level argument"; the power-on reset "appeared in no card's budget",
and "`serial.md` §6 already takes `/RESET` as an input; `ps2.md` did not and now must
(`design-review.md` §IO-P3)"; the open-drain pull-ups existed in four cards'
declarations "and no document placed the resistors".

## §3 — the geographic window: `$FF40`–`$FF7F` → `$FF00`–`$FF7F` (2026-09-08)

The widening was §5 item 1 option A. `graphics.md` §17 had asked for exactly this three
times ("it is a decode term today and a board respin later"), and the closing line of
the section read:

> `graphics.md` §17 said *"widen the window now — it is a decode term today and a board
> respin later."* **It was right, it said so three times, and the second widening cost a
> decode term *back*** — `/IOSEL` went from two literals to one.

## §3 — the map-fullness heading, twice amended (2026-09-07, 2026-09-08)

The heading ran: ~~⚠ The map has four bytes left, and that is all.~~ ~~The map has
none.~~ The map has 64.

> **Twice amended, and the second one closes it.**
>
> - **2026-09-07 — `net/docs/net.md` §5.1 took the last four bytes.** 16 + 4 + 4 + 4 +
>   4 net + 32 = **64 of 64, nothing free.** The heading below had called those four
>   "one small card's worth, once", and net was that card. For one day the answer to
>   "where does the next card go?" was *nowhere* — not "nowhere if it is large",
>   nowhere at all.
> - **2026-09-08 — §5 item 1 option A widened the window to `$FF00`–`$FF7F`.** 64 + 64
>   = **128, of which 64 are free.**

The net window row itself carried "~~free~~ — **the machine's last unallocated I/O, and
this is what spent it**".

The four bytes net spent had come back from storage: the disk-controller reservation
was sized for a WD1773 — **four registers** plus a latch — and `sdcard.md` §6.1 needs
three, so four bytes returned. "That was the only movement this map ever made in the
expanding direction until the window itself moved." A sub-note: the table said "five
registers plus a latch" for the WD1773 until 2026-09-04; it is four (`ps2.md` §3.2 had
it right).

## §3 — what the shortage cost while it lasted (recorded 2026-09-07, moot 2026-09-08)

> ⚠ **What the shortage cost while it lasted is worth keeping visible, because the card
> that paid it is built to the shortage and not to the map.** `net.md` §13.6 specifies
> sixteen ICs and two CPLDs partly because a National `DP8390`'s register file wants 16
> bytes that did not exist. **That argument is now half-void and the card does not
> change**: the `DP8390` is long obsolete and what stock exists is priced as a
> collectable, so it loses on availability whatever the map says. The net card keeps the
> dual-`ATF1508AS` design. **`net.md` §13.6 is corrected rather than deleted** — it was
> a real argument on the day it was written, and the map is why it had to be made at
> all.

## §3 — `$FFA0`–`$FFAF` said "enable, task select, shadow-ROM disable and vector RAM" until 2026-09-06

> ⚠ **This table said `$FFA0`–`$FFAF` held "enable, task select, the shadow-ROM disable
> and the vector RAM" until 2026-09-06.** Writing the MMU's GAL equations
> (`hardware/gal/README.md`) showed that none of the four survives.

The three reasons (sixteen block registers need all sixteen bytes; MMU enable cannot
exist; the shadow-ROM disable cannot reach a motherboard latch) are present design and
stay in §3.

## §3 — the block-register width: bits 6–0 / `A19..A13` → bits 7–0 / `A20..A13` (2026-09-08)

The table said "Bits 6–0 are physical `A19..A13`" until §5 item 1 option D turned the
stored-but-unused bit 7 into physical `A20`. `hardware/gal/README.md` carries the
current 8-bit entry.

## §4 / §4.1 — the polling order's own history (2026-09-04, amended 2026-09-07)

The original decision specified **three** polled sources:
`1. video VSTAT → 2. PS/2 IOSTAT → 3. serial STATUS (last, always)`, then:

> ⚠ **Amended 2026-09-07 — a fifth source, and the order is now `video → net → PS/2 →
> serial`** (`net/docs/net.md` §6).

The decision block also recorded a corrected claim:

> this document's earlier claim that "NitrOS-9's CoCo 3 IRQ code already expects a
> GIME-compatible interrupt-source block" **was wrong on its own terms** — nothing in
> this machine decodes `$FF92`/`$FF93`, and §5 item 6 lists the interrupt block as a
> GIME divergence in the same breath.

And a remark on what the fifth source exposed: "nobody had to choose between
correctness-driven and frequency-driven ordering before" — the substance of which
(the two orders disagree, correctness wins) stays in §4.1.

## §5 item 1 — the item's own history (opened as "THE I/O WINDOW IS ALL BUT FULL")

> **The item's own history, because it took four documents and two years of project
> time to get here.** `graphics.md` §17 asked for the widening three times and called
> it "a decode term today and a board respin later". `serial.md` §7.1 reported the map
> exactly full. `sdcard.md` §6.1 handed four bytes back and §11.1 showed the shortage
> costing 27 % of a transfer rate. `net.md` §5.1 spent the four bytes and §13.6 showed
> it costing ten packages. **Every one of those was a card noticing from inside itself
> that the machine had a problem, and none of them could fix it.**

The item's closed heading read "The window is 128 bytes and **the physical map is
2 MB**" — true on the morning of 2026-09-08; `ram.md` §5.2 re-carved the map to 32 MB
the same day, and the cleaned item says so.

Option A's text said the widening "freed U6 pin 6, which is where §7.1's `A20` went" —
**wrong within its own item**: the very next table row says U6 pin 6 keeps its `LA6`
trace so `$FF80`–`$FF8F` stays a one-line change, and `mainboard.circuit.tsx` puts
`A20` on U6 **pin 9**. Fixed against the schematic.

The not-taken options B, E, F are condensed in the spec; their full recorded arguments:

> - **B — page the `$FF40` window.** Multiplies the space arbitrarily and costs a page
>   register plus page bits reaching every card. **Rejected on §4.1**: the shared-`/IRQ`
>   handler polls five cards' status registers, `net.md` §3.4 shows dispatch is already
>   the scarce resource, and a page write per poll makes the machine's worst
>   interrupt-latency case worse to solve its least urgent problem.
> - **E — index/data indirection per card.** Video's 32 bytes would become 4. Costs two
>   bus cycles per register access and is hostile to exactly the ISR polling §4.1
>   specifies. A card may choose it; the machine will not require it.
> - **F — declare the machine closed.** Six slots, six cards, an exact fit. Honest, and
>   unnecessary now.

## §5 item 2 — the original open item, whose premise was wrong

> **No interrupt line for an I/O card.** §4 gives `/IRQ` to video and `/FIRQ` to audio
> as sole owner. A PS/2 keyboard wants an interrupt; polling it from the VBL tick is a
> real option at 50–70 Hz and should be *chosen*, not defaulted into. `/NMI` is free and
> is almost certainly the wrong answer.

Resolution: "**Chosen, and the premise of this item was wrong**" — `/IRQ` was never
video's exclusively; it is the machine's shared line and PS/2 joined as a third source
(`ps2.md` §3.1). `/NMI` was "confirmed wrong, for a different reason than expected".

## §5 item 3 — the original open item, and a stale warning it accumulated

Original text:

> **The MMU register set is not written down.** `graphics.md` §6.3 said
> "GIME-register-compatible, `$FFA0`–`$FFAF`, 8 blocks, two task registers, 6-bit block
> numbers" and stopped there. `graphics.md` §18 step 0 lists it as an exit criterion.
> Nothing in `cpu/` implements it yet — Phase 1 is the timing spike and has no MMU.

Closed 2026-09-06. The closure note briefly carried this warning, superseded within two
days by §3 and §7.2 (the vector RAM moved to `$FF90`–`$FF9F` and the disable into the
CPU module, so nothing extra shares the 16 bytes):

> ⚠ **§7.2 adds two more things to the same 16 bytes**: the shadow-ROM disable bit and
> the 16-byte vector RAM's write port. `$FFA0`–`$FFAF` now carries the map entries, task
> select, MMU enable, shadow-ROM disable and vector-RAM access — **fit it before the GAL
> is fitted**, because it may not fit, and the free bytes at `$FF5C`–`$FF5F` are the
> only relief the machine has.

It also called itself "the most blocking of the CPU-side items", with three things
waiting: the motherboard's write-decode GAL, the NitrOS-9 patch, and the boot path.
The register set is hardware now; the NitrOS-9 patch remains an open cost (§5 item 6).

## §5 item 4 — the original open item

> **The E/Q divider ratio is assumed, not frozen.** Every cost estimate in `audio.md`
> and `modplayer.md` is quoted against 2.098 MHz, i.e. ÷12. `graphics.md` §11 shows VRAM
> read-back closing at ÷12 and *not* at ÷8, so ÷8 is not a free speed switch — it costs
> the read path. The default should be stated here rather than inferred from arithmetic.

Closed 2026-09-04 by §1.1.

## §5 item 5 — the motherboard's parts list as first written

The item's status note said the motherboard carried "§7.1's 512 KB of system RAM" —
superseded by §7.1's DRAM decision; the cleaned item lists the SIMM sockets and DRAM
controller instead.

## §5 item 6 — LQFP48 vs LQFP64, and the package that was named wrong

Original question:

> **LQFP48 vs LQFP64 for the CPU module.** `graphics.md` §6.3 recommends the LQFP64
> part for the homebrew card, because the MMU needs a second store for A16–A19.
> `cpu/docs/plan.md` §3.2 closes the pin budget on the LQFP48 — but for the *CoCo 3*
> drop-in, which has no MMU of its own to emulate at that width.

The decision (MMU off the CPU) stands; the package correction in full:

> ⚠ **But the package named was wrong, and this is corrected 2026-09-04 —
> `design-review.md` §Cpu-C1.** The pinout puts `BA` on PC4, `BS` on PC6 and the debug
> UART on PC10/PC11. **None of those pins is bonded out on the LQFP48.** DS12589 Table 2
> gives 38 GPIO on LQFP48 against 42 on UFQFPN48; port C on the LQFP48 is PC13/14/15 and
> nothing else. The real LQFP48 budget is 38 − SWD − NRST = **35 usable**, which carries
> the 33 mandatory signals and leaves PF0/PF1 — no `BA`, no `BS`, no debug UART, and
> none of the "5 spare" this document claimed.
>
> **The fix is the package, not the design: `STM32G431CBU6`, UFQFPN48.** Same die, same
> firmware, and the existing pinout works verbatim. The external-MMU decision survives
> untouched — an in-CPU MMU needs ~38 pins and was infeasible on 35 either way.

## §5 item 7 — "nobody owns the megabyte", and a same-day halving

The item opened as "⚠ NEW — nobody owns the megabyte at `A20 = 1`", 2026-09-08, and
was decided the same day. The region count carried:

> ⚠ **Halved to 8 on 2026-09-08 and restored the same day** — the halving paid for a
> system-RAM quadrant that `ram.md` §6.2 then deleted along with all the DIP SRAM.

## §5 item 8 — `/WAIT` had a producer and no consumer (found and fixed 2026-09-08)

The discovery, as the item recorded it:

> `hardware/gal/vctrl.pld` line 419 drives it open-drain —
> `WAIT.oe = SPANBUSY & VRAMSEL & !IOPAGE`, the video card holding the CPU off VRAM
> while the span writer runs. **Nothing on the motherboard listens.** §1's E and Q come
> from U6's divider (`hardware/gal/clkdec.pld`) and that part has no `/WAIT` input;
> "it holds E" (§2) names an effect with no mechanism.
>
> So the video card's span writer, as drawn, **did not hold anything** — the CPU read
> VRAM through it and got whatever the span engine was mid-way through writing.

The fix (hold terms on all six registered macrocells, E from 7 to 8 of 16 product
terms, `vctrl`'s `WAIT.oe` gaining `& E`, the synchronous-to-`CLK25` rule, four new
testbench claims including "/RESET beats /WAIT") is present design and stays in the
item.

## §5 item 9 — every open-drain output drove its line the wrong way (found and fixed 2026-09-08)

The full account, condensed in the spec:

> Fixing item 8 meant compiling `/WAIT` for a real GAL for the first time, and
> `hardware/gal/jedec/cupl.check.ts` — the falsification check that runs Atmel's own
> compiler against our fuse map — **disagreed on exactly one signal.**
>
> The idiom is a cell with **no product terms**: it drives a constant and the condition
> rides entirely on the output enable, so the pin pulls to one rail or floats. Both
> emitters wrote the constant as `'b'0`. The pin is declared `PIN n = !WAIT`, so **CUPL
> inverts it and the pin drives HIGH whenever the enable is true.**
>
> On a shared open-drain line that is not "no wait". It is a card **fighting the
> motherboard's 3.3 kΩ pull-up and every other card on the wire.**
>
> **Three signals used the idiom and all three were wrong:**
>
> | | line | consequence |
> |---|---|---|
> | video `/WAIT` | shared, 5 cards | the defect of item 8, twice over |
> | **video `/IRQ`** | **shared with PS/2, serial and net** | **a card driving the machine's interrupt line high against four other open-drain drivers.** §4's whole ownership scheme assumes wire-OR |
> | audio `/FIRQ` | audio alone | fights the pull-up; sole owner, so no card-to-card contention |
>
> **Fixed** — `jedec/cupl.ts` and `jedec/galpld.ts` now emit `'b'1` for an active-low
> cell — and **verified the only way it could be**: Atmel's CUPL and our assembler now
> agree over all 512 input combinations of the arbiter. Every affected device was
> refitted.
>
> **This is the second time `cupl.check.ts` has earned its existence**, and the lesson
> is sharper than the first. Its own header records two errors that "178 passing checks
> could not find, because in both cases the assembler and the fuse-map simulator shared
> the mistake and agreed with each other perfectly". **This one was worse**: the
> mistake was in the *emitter*, so it was invisible to the assembler and the simulator
> **and** to every check written against either. Only a second compiler could see it —
> and only once a design using the idiom was compiled as a GAL rather than merged into
> a CPLD.

## §5 item 10 — opened as "a stretched cycle is a hazard", bounded the same day

The item opened as "⚠ NEW — a stretched cycle is a hazard for any card that schedules
against `E`" and was bounded on 2026-09-08 at 40.7 µs (one card's span writer). The
bound, what it settles, and the free-run-on-`CLK25` rule stay in the item.

## §6 — rows closed and archived (the table now lists only open items)

- **"Write the MMU register set"** and **"Fit `$FFA0`–`$FFAF` — map entries, task,
  enable, shadow-ROM disable and vector RAM in 16 bytes"** — both closed by §5 item 3
  and §3: the register set is hardware (`hardware/gal/README.md`, `mmu.pld`), and
  nothing beyond the sixteen block registers shares the window (vector RAM at
  `$FF90`–`$FF9F`, disable inside the module). The "fit it before the GAL is fitted"
  worry dissolved with the sharing.
- **"Divide the megabyte at `A20 = 1` — what is open is the arbitration"** — closed by
  §5 item 7: fixed-phase arbitration, no handshake.
- **"Refit `vctrl`"** — done 2026-09-08: `REGSEL` gained `A6`, `VRAMSEL` gained
  `/A20`, `WAIT.oe` gained `& E`, and the arbiter moved back out to its own `GAL22V10`
  so the part stayed a PLCC-84; then `RA0`–`RA4` and `WSTB` went out to a second GAL
  (`rfa`) and §6.4.3's Variant B came out for the display list, leaving it at 46 of
  64 — at which point the arbiter came back in and deleted its package. **Fit chain:
  64/64 I/O, 112/128 cells → 50/64, 91/128 → 46/64, 87/128 → final 62/64, 97/128**
  (`hardware/gal/video.cpld.ts`, `cpld/vctrl.fit`).
- **"`vctrl` has zero spare pins and therefore no JTAG"** — done 2026-09-08:
  `RA0`–`RA4` and `WSTB` moved to `rfa`, a second `GAL22V10`. The estimate said five
  pins; it was **fourteen**, because nine inputs existed only to feed those outputs.
  JTAG fitted with ten to spare — and was spent again the same day on the display list
  and the arbiter's return. (`vaddr`, not `vctrl`, is the CPLD without JTAG now — the
  live row.)
- **"Bound `SPANBUSY`"** — done 2026-09-08: **40.7 µs** worst case, **10.2 µs** once
  `graphics.md` §14.2's broadcast write lands; `/WAIT` also qualified on `R/W`, so
  reads never wait (`graphics.md` §7.4). Now §5 item 10.
- **"Decide whether the display list is worth §6.4.3's Variant B"** — **decided and
  built 2026-09-08: the list engine is in, Variant B is out.** It cost no package: the
  engine shares `WPTR` rather than carrying its own 19-bit pointer, and the 1bpp
  character generator's macrocells, product terms and four pins paid for the rest.
  `vaddr` 64/64 I/O and 102/128 cells, `vctrl` down to 46/64 and 87/128 (before the
  arbiter's return). ⭐ Per-scanline `HSCROLL`, palette and mode changes from a
  descriptor list, with no CPU (`graphics.md` §10.1.6.2). The live consequences —
  `WPTR` clobber, no JTAG on `vaddr`, no hardware text mode — remain as §6 rows.
- **"Re-price storage and io against a memory-mapped buffer"** — done 2026-09-08; both
  cards took it (`sdcard.md` §11.1, §4.5; `net.md` §13.3, §7.6). What is left is the
  SD write path, still a §6 row.
- **"Restate or retire the no-CPLD house rule"** — **retired 2026-09-08**, root
  `README.md`: programmable logic is in; FPGAs are unproposed rather than banned. The
  outstanding consequence (storage's `ATF1508AS` consolidation, 8 ICs against 14) is a
  §6 row.
- **"Source an `R6551A` or `G65SC51`"** — struck in favour of deciding
  `serial.md` §5.4's tier first (the `16C550` option); the tier decision is the live
  row.
- The **"Draw the motherboard"** row described it as "Nine ICs, 512 KB of RAM" —
  superseded by §7.1: 14 ICs, four SIMM sockets, no SRAM.

## §7 — the section was new on 2026-09-04

> **New in this revision, and the whole of it answers `design-review.md` §Sys-C1 and
> §Sys-M2.** Both are things that belonged to the machine rather than to any card,
> which is why five internally careful card specifications went to press without them:
> the machine had **no main memory owner and no way to execute its first instruction.**

## §7.1 — system RAM: unowned → 512 KB SRAM → SIMM DRAM (2026-09-04, 2026-09-08)

The 2026-09-04 text, kept then "because its arithmetic is still the argument for one
part rather than four *at 512 KB*":

> This document asserted "`A19 = 0` is 512 KB of system RAM" in §0 and §2 from the
> beginning and never said who provides it. It was in no chip budget — every card
> accounts scrupulously for its own parts, and the motherboard was "3 ICs plus a
> divider GAL". SRAM rather than DRAM because **DRAM needs a refresh owner and this
> machine has none**; at 55 ns it also clears the CPU's ~160 ns `t_AD`-to-data budget
> without a wait state, which DRAM at this vintage would not.

The 2026-09-08 transition:

> ⭐ **Decided 2026-09-08 and then simplified the same day.** Three SRAM footprints were
> reserved and could not be populated, because **four × 512 KB is 2 MB and that was the
> whole physical map** — so the map entry widened to 16 bits. Once there were SIMM
> sockets on the board the four DIP SRAMs had no job left, and they went: **14 ICs, not
> 18.** ⚠ **And this section's reason for rejecting DRAM expired** — *"DRAM needs a
> refresh owner and this machine has none"* was true until §5 item 8 gave the divider a
> `/WAIT` hold, and §5 item 10 then showed refresh and the video card's stall never
> contend.

## §7.2 — struck values in the boot story

- The failure statement cited the decoded page as "~~`$FF40`~~ `$FF00`–`$FF7F`" —
  tracking the §3 widening.
- The vector RAM's write window was "~~`$FFA0`–`$FFAF`~~ `$FF90`–`$FF9F`" — it moved
  on 2026-09-06 when the sixteen block registers claimed the whole `$FFA0` window.
- The disable bit "was a bit on the motherboard's `'574` until 2026-09-06, which could
  never have worked — every one of the socket's 40 pins is defined, so there is no wire
  to carry it and nowhere to add one."
- The original failure text also noted "`graphics.md` §6.3 spends the entire 1 MB
  physical map on 512 KB of RAM and 512 KB of VRAM" — the 1 MB map predates §5 item 1 D
  and `ram.md`.

## §8 — power and IC-count chains

**Video card row:** ICs 40 → 31 → 28 → **27**; estimate ~0.75–1.3 A (0.9 A nominal) →
**~0.5–0.85 A (0.65 A nominal)** — "the seven SRAMs became four and took ~250 mA with
them". Earlier still: "⚠ It quoted 450–650 mA until 2026-09-04 (less than its own GAL
row) and **~1.1–1.7 A until 2026-09-08**, when the ten GALs at 70–90 mA each were
finally replaced in the arithmetic as well as in the design."

**Audio row:** 36 → **29** (`audio.md` §10.1).

**Serial/storage row:** storage 7 → **14** (its block buffer, §5 item 7).

**Motherboard row:** 13 → 9 → **14** (`hardware/ram.md` §6.5).

**Machine totals:** "plausibly ~~2–3~~ **1.8–2.8 A** at 5 V across ~~~106~~ ~~108~~
~~113~~ ~~114~~ ~~111~~ **110 ICs**".

The re-derivation notes in full:

> ⚠ **Both halves re-derived 2026-09-08, and the card total had never been added up.**
> This row carried "97 on cards" while the card documents summed to 91, and neither
> number tracked the four counts that changed during the week. Video fell 41 → 30 when
> `graphics.md` §14.1 finally counted the two `ATF1508AS` that replaced its ten GALs
> (2026-09-06's decision, 2026-09-08's arithmetic), rose to **31** with `rfa`
> (§10.1.6.3), fell to **28** when §14.2 consolidated seven SRAMs into four, and to
> **27** when the arbiter merged back into `vctrl`; storage rose 7 → 14 and net fell
> 16 → 12 in the same week's buffer work; the motherboard rose 9 → 14 for the DRAM
> controller. **The current estimate fell** because ten GAL22V10 at 70–90 mA each were
> most of an amp and two CPLDs are not.

> ⚠ **Both halves of that sentence moved on 2026-09-04, and in the same direction.** The
> review estimated "~90 ICs and 1.5–2.5 A" from the counts the card documents then
> carried. Re-tallying those documents put video at 40 rather than ~33, audio at **57
> rather than 35**, and PS/2 at 11 rather than 9 — so the machine is about **45 % more
> silicon than any document claimed**, and the supply grew with it. Audio has since come
> back to **36 — below the 35 it originally claimed, and this time itemised**: the
> four-DAC analogue sum took 3 (`audio.md` §6.2), moving the host-visible counters and
> commit staging into the state file the card already owns took 9 (`audio.md` §9.5),
> and cascading two halves of a dual multiplying DAC so the volume multiply happens in
> the analogue domain took 9 more (`audio.md` §6.1). It is the only count that has moved
> down, and the two lessons generalise: **state living outside a card's own state memory
> is the cheapest thing to find**, and **a table that exists to do arithmetic is worth
> re-examining against the parts catalogue.**

The closing audio note recorded the trail "audio.md §16 item 19 raised it as an open
question at 57; four passes have taken it to 29 — the last of them replacing six
GAL22V10s and three HC packages with one `ATF1508AS` — against the 35 the
single-Eurocard assertion was first made at." The open question (measure the Eurocard
fit) stays in §8.

---

# Part II — `video-comparison.md`

## §intro — the 2026-09-04 re-basing note, and the counts since

The document opened with this note after the review:

> ⚠ **Figures re-based against `graphics.md`'s corrected §14.** This document mirrored
> the card specification faithfully, including its errors: the package count
> (~~36~~ → **40**), the GAL count (~~8~~ → **9**), the card power figure
> (~~450–650 mA~~ → **~1.1–1.7 A**), the spare-bandwidth total (~~34 M accesses/s~~ →
> **32.4 M**), the MMU's package count (~~3 ICs~~ → **5**), and two capability rows —
> "steals CPU cycles: never" and "mid-frame palette writes: yes" — that were true only
> with a qualification the card document had not yet written down. Corrected in place
> below, with the old figures struck rather than deleted.

The counts have moved again since: the card is **27 ICs** (`graphics.md` §14.1), the
nine GALs became **2 × `ATF1508AS` PLCC-84 + 1 × `GAL22V10`**, and the power estimate
fell to **~0.5–0.85 A, 0.65 A nominal** when the CPLDs replaced the GALs in the
arithmetic and §14.2 consolidated seven SRAMs into four (`machine.md` §8's chain,
above). The intro's "40 packages instead of one" framing tracked the 2026-09-04 count.

## §2 — the border register

"Independent border colour: ~~yes (`BORDER`)~~ **no — register deleted**" —
`graphics.md` §9.3: VGA timing has no overscan, and the `'153` pixel mux has no spare
input for a border index. A border is a fill in the off-screen torus instead. (The
current row states the "no" plainly.)

## §4 — spare bandwidth 34 M → 32.4 M accesses/s

"The blanking rows were charged at a raw 72 ns cadence instead of the 158.9 ns
fetch-slot grid" — corrected 2026-09-04; the CPU-consumption ratio moved ~80× → ~77×
with it.

## §9 — VSYNC joined the raster-compare recipe

The cost row read "HSYNC clocks the line counter, ~~and that is all~~ **and VSYNC
resets it**" — counting HSYNC alone gives a line *count* with no origin, and
resynchronising in the VBL handler jitters the frame origin by the `/IRQ` dispatch
latency, 1–6 lines. (The two-signal recipe is the current text.)

## §9 — "inherited `$FF92`/`$FF93`-compatible" interrupt routing

The interrupts table claimed per-source IRQ/FIRQ routing "inherited —
`$FF92`/`$FF93`-compatible". `machine.md` §4.1 (2026-09-04) found the premise wrong —
nothing in the machine decodes `$FF92`/`$FF93`, the interrupt block is a GIME
divergence, and the machine's answer is a specified polling order on shared `/IRQ`
with `/FIRQ` owned by audio alone. The row now says so.

## §10 — the package-count chain

The packages row reconciled three counts that were live at once: **~~41 (37)~~,
~~40 (36)~~, ~~36 (32)~~ → 30 (26)** — and `graphics.md` §14.1 has since taken the
card to **27 ICs (23 if the tri-state pixel bus closes)**. The GAL row's chain was
~~8~~ → 9 ("§5.2.1's arbiter is the ninth"), with "two of the four pairs at zero
macrocell margin" — all superseded by the CPLD consolidation: 2 × `ATF1508AS` +
1 × `GAL22V10`. Power: ~~450–650 mA~~ → ~1.1–1.7 A → **~0.5–0.85 A**. Area:
~~140~~ → ~150 cm² on a 160 cm² Eurocard. The MMU alongside: ~~3~~ → **5 ICs**.

## §8 / §11 — the display list and the text rows

§8's row read "Display list / copper: **reserved, ≈5 ICs + 2 GALs** (§10.3)" — the
list engine was **built** on 2026-09-08 at **no package cost** (`graphics.md`
§10.1.6.2; it shares `WPTR` and absorbed dropped Variant B's resources).

§11 carried two text verdicts: "Text, as specified (Rev A): GIME" and "Text, with
`graphics.md` §6.4: **arm6309 card** — 80×25 at 2 writes/cell, and 256 attribute pairs
from all 65,536 colours", with a qualification block noting §6.4 was "a proposal, not
the specified card" gated on GAL pin fit. §6.4.3's Variant B (the 2-writes/cell 1bpp
character mode) was **dropped 2026-09-08**; text is the span writer in bitmap mode at
**13 writes/cell**, and the GIME keeps the text row. Variant A's 8bpp tilemap — the
mode with no period equivalent — survives and keeps its row.
