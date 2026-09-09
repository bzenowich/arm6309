# Hardware — archived history

Superseded passages from the `hardware/` documents — [`README.md`](README.md),
[`ram.md`](ram.md), [`gal/README.md`](gal/README.md) and
[`place/README.md`](place/README.md) — moved here when the specs were cut down to the
present design. Entries are organized by source file and section; the archived text is
kept verbatim or lightly trimmed, because the archive is the record.

---

## `ram.md` — the header, §0 and §1: "512 KB to 16 MB" (rewritten 2026-09-08)

The document was titled **"RAM Expansion — 512 KB to 16 MB, and the Three Ceilings That
Are Not the Same Height"** and opened:

> **Question this answers:** the machine has 512 KB of system RAM and a 2 MB physical
> map. What would it take to reach **16 MB**, and what is the cheapest path that does not
> throw away the 2 MB that already works?
>
> **The short answer.** The address path to 16 MB costs **one SRAM, one GAL output and
> three backplane pins** — it is nearly free, because the MMU was built with 128× more
> map storage than it uses.

§0's ceilings table had a **"Where it is now"** column reading *2 MB — 8-bit map entries*
and *512 KB in one DIP-32*, and §1 — headed **"Where the machine is today"** — listed an
8-bit map entry, one `CY7C128A`, `TASK` at one bit, and *"System RAM: **one `AS6C4008`,
512 KB**, at `A20 = 0, A19 = 0`"*, closing:

> **This is the GIME's architecture with the third-party 2 MB upgrade already applied.**
> ... This machine took bit 7 for `A20` on 2026-09-08 and is at exactly that ceiling:
> **8 bits, 2 MB, nothing left in the byte.**
>
> ⚠ **So the next megabyte is not free the way the last one was.** `A20` cost one
> backplane pin and no parts because the map SRAM was already byte-wide and the eighth
> bit was already stored. **There is no ninth bit.**

**Every line of that was true when written and none of it survived the same day.** §§5
and 6 of the same document decided the 32 MB map and the SIMM sockets, and §6.2 deleted
the DIP SRAM — so the "today" the header, §0 and §1 described was two sections earlier in
the file that superseded it. The **three backplane pins** in the short answer were struck
by §5.3 before the ink dried (`/IOPAGE` does the work instead, for zero pins), and this
archive's own entry below records that.

**Replaced by "The Memory System — 32 MB of Map, 16 MB of DRAM, 1 MB of ROM"**, with §1
retitled "Where the machine is" and describing the decided design.

---

## `ram.md` §6.4 — the boot path, and the scratch RAM that is not needed

§6.4 was headed **"⚠ The boot path, which is what the SRAM was quietly insuring"** and
offered two answers:

> | | |
> |---|---|
> | **Stackless DRAM init** | boot code brings up refresh and the map using registers only, no subroutine calls, until the first SIMM answers. The 6309 has the registers for it; it is careful assembly and a real constraint on the boot ROM |
> | ⭐ **The CPU module serves a scratch RAM** | it already serves an 8 KB shadow ROM and a 16-byte vector RAM from its own flash and SRAM. **An `STM32G431CB` has 32 KB of SRAM**; serving 2 KB of it as a logical window costs **zero ICs** and a firmware change, and it parallels §7.2 exactly |
>
> **The second is recommended and not specified.** It also gives the machine somewhere to
> run from if a SIMM is absent or dead, which the four-SRAM version got for free and this
> one does not.

§8 closed on *"the machine now has no SRAM at all, which is §6.4's boot problem and the
one thing this design gives up"*, §10 warned *"there is no step that yields a working
machine without DRAM any more"*, and §11 item 4 carried it open.

**The first answer is the one taken, and it turned out not to be careful assembly.**
`machine.md` §7.2's boot sequence is sixteen stores to `$FFA0`–`$FFAF`, a `CLR` of
`$FFB1` and an `LDS` — no `JSR`, so no stack — and **refresh needs no initialisation at
all**, because U10's refresh timer free-runs off `CLK25` from reset (which
`machine.md` §5 item 10's rule requires of it independently).

**The scratch-RAM proposal is withdrawn**, and the reason is worth keeping: it was the
last thing that would have kept boot inside the CPU module, and `cpu/docs/plan.md` §4.5 —
the mechanism it paralleled — was retired the same day.

---

## `ram.md` §5.2 — the bottom quadrant was "the natural home for a boot scratch"

The 0.0–0.5 MB row of §5.2's map read **"reserved — the natural home for §6.5's boot
scratch"**, and `machine.md` §2's copy of the table said **"reserved — no RAM here;
§7.1's boot-scratch question lands here"**. There is no boot scratch (see above), so the
quadrant has no claimant at all; both tables now say so, and the boot ROM went into the
2.0–4.0 MB block that was already reserved.

---

## `README.md` finding 1 / open item 3 — the motherboard's system RAM

Finding 1 read **"`machine.md` §7.1's system RAM is one part, not four"** and described
the board as fitting **U8 alone**, an `AS6C4008` whose `/CE` is the `A19 = 0 · /IOPAGE`
term, with a parenthetical noting that `ram.md` §6.2 had since removed the DIP SRAM. That
parenthetical was doing too much work: the finding read as present design and the design
had no DIP SRAM in it.

**The finding is kept as a finding** — drawing the board is what showed the four-part
decode was imaginary — and rewritten to say plainly that the part is gone, that it went
to the audio card (`audio.md` §5), and that the board file has not caught up. Open item 3
now names both gaps: the board file draws 9 ICs where the design is 17, and nothing is
placed.

**The status paragraph also said "Three things gate layout"** and listed the video output
stage among them; `graphics.md` §9.1–§9.3 specified it and
`hardware/cards/video.circuit.tsx` draws it, so that clause is gone.

**And the slot's power bullet quoted the video card at "~1.1–1.7 A, design to 2 A"**,
which `graphics.md` §14.2 had already taken to **~0.5–0.85 A, 0.65 A nominal** when the
ten GALs became two CPLDs and the seven SRAMs became four. `lib/slot.check.ts` carried
the same stale figure in a comment and in `WORST_CARD_A`; both are corrected, and the
check still passes with 5 A of finger against it.

---

## README.md §The two decisions — card format: Eurocard → 250 × 100 → per-card lengths

The card-format cell carried its own chain: ⚠ *"**Was a 100 × 160 mm Eurocard.**
[`place/`](place/) drew the boards and the video card did not fit one: 134.4 cm² of
courtyard against 133.4 cm² of placeable area."* `place/README.md` recorded the
intermediate step: the overflow *"moved the card format to 250 × 100 and then to
per-card lengths."*

Replaced by: **100 mm high × 120, 180 or 240 mm long, per card** — `place.check.ts`
asserts each card takes the shortest length that works. The connector consequence is
still live in the spec: a 240 mm edge holds 98 positions at 0.1″ where the Eurocard held
39, so the 72-pin connector's original justification ("the card format sizes the
connector") no longer binds, and `machine.md` §5 item 5 is where a re-specification
would be decided.

## README.md §Slot count — five + 1 spare → six + none → five + 1 spare (2026-09-08)

> **Slot count is six, and that is a guess** — ~~five specified cards plus one free~~,
> ~~six specified cards and none free~~, and since PS/2 and serial merged on 2026-09-08,
> **five cards and one spare again**.

The specified-card count went five → six → five: a sixth card ate the spare slot, then
PS/2 and serial merged onto one I/O card on 2026-09-08 and gave it back. Replaced by:
six slots, five specified cards, one spare — still a guess, bounded by the supply and
not the connector.

## README.md §The slot — A34: "future rail" spare → physical `A20` (2026-09-08)

> ⚠ **~~The spare at A34~~ A34 is physical `A20`, since 2026-09-08.** It sits between
> two +5 V pins and this document called it "the natural home for a future rail".
> `machine.md` §5 item 1 option D spent it on the top address bit instead, doubling the
> physical map to 2 MB — and the reason it won is that it needs **nothing else**: the
> map SRAM is byte-wide, its eighth bit was already stored and read back through the
> isolation `'245`, and it drove nothing. One trace, no ICs, 1 MB.
>
> **`net/docs/net.md` §13.1 wanted two of these pins for a DMA request/grant pair and
> lost the same day.**

Replaced by: A34 is physical `A20`; there is no spare position, and `lib/slot.check.ts`
prices what a seventh signal would cost.

## README.md §What the layout found 1 — system RAM is one part, not four (applied 2026-09-06)

`machine.md` §7.1 said:

> **512 KB of SRAM on the motherboard, selected by `A19 = 0` qualified with `/IOPAGE`.**
> Four × 512K×8 (AS6C4008-class, 55 ns) and a decode.

The finding, as it was made: **512K × 8 is 512 KB.** Four of them is 2 MB — against a
512 KB requirement, in a 1 MB physical map that allots system RAM exactly `A19 = 0`,
i.e. **A0–A18, nineteen address lines**. An AS6C4008 has A0–A18. It *is* the
requirement, once. And "a decode" goes with the other three: with one part there is
nothing to decode between — `/CE` is the `A19 = 0 · /IOPAGE` term the MMU's `GAL22V10`
already forms.

**This moved §8's motherboard line from ~13 ICs to 9**: MMU 5, divider GAL, oscillator,
reset supervisor, system RAM. The machine total moved with it, from ~110 to ~106. It is
the same shape of error the 2026-09-04 review found repeatedly — **a table that exists
to do arithmetic is worth re-examining against the parts catalogue** (§8's own closing
lesson). Unlike audio's 57, though, it was not found by re-reading the document — it was
found by a board file that had to say how many packages to draw.

Applied 2026-09-06: `machine.md` §7.1 says one package and no decode, and §0, §6 and §8
carry the corrected counts. (`ram.md` §6.2 later removed the DIP SRAM from the decided
design entirely — see the ram.md §6.5 entry below.)

## README.md §What the layout found 2 — `/IOSEL` cannot be geographic (applied 2026-09-06)

The finding, as it was made. `graphics.md` §17 adopted colormin's slot model, where
`/IOSEL` is **geographic** — slot *n* gets the *n*th 64-byte window, decoded by
position. `audio.md` §9.1 and `ps2.md` §3.2 both repeated "decode is geographic from the
backplane's per-slot `/IOSEL`", and each added **"so the base is a jumper"**.

Those two sentences cannot both be true here. colormin's windows are *slot*-sized — four
identical 64-byte blocks. This machine's are *function*-sized and all different: audio
16 bytes, video 32, PS/2 4, serial 4, storage 4. A decode that assigns windows by
position would force each card into one specific slot, at which point a base-address
jumper decodes nothing.

The reading that works is the one `machine.md` §2 already implied when it derived
`/IOPAGE`: `/IOSEL` is the window strobe, common to every slot, and each card completes
its own decode against its jumpered base. **It was not, however, what any document
said** — except `serial.md` §6, whose decode GAL took `CS0`/`/CS1` "from geographic
`/IOSEL` *and `A2`–`A5`*": the window-strobe model written down, in the one card
document that never claimed the geography.

⚠ One correction to the finding itself: it first named `sdcard.md` §6.1 as a repeater of
the claim. It is not — that section only proposes a window. The documents carrying "per
slot" were `machine.md` §2, `graphics.md` §17 (twice), `audio.md` §9.1 and `ps2.md`
§3.2.

The window itself then changed twice more: the strobe was first written as
**`$FF40`–`$FF7F`** (`/IOPAGE · A7 · /A6` — and the term as originally written had its
polarity wrong: see the gal/README.md §U6 entry below), and on 2026-09-08 `machine.md`
§5 item 1 option A widened it to **`$FF00`–`$FF7F`** (`/IOPAGE · /A7`), moving the
card-side decode from `A0`–`A5` to `A0`–`A6`.

Applied 2026-09-06: `machine.md` §2 owns the correction; `graphics.md` §17, `audio.md`
§9.1 and `ps2.md` §3.2 defer to it.

## README.md §What the layout found 4 — the map SRAM pinout (found 2026-09-06)

Found when the datasheets open item 1 asked for were fetched from Digi-Key and Mouser
and the pinouts were read off them rather than recalled.

Four of the five parts were right as drawn — `74HC574`, `74HC245`, `74HC157` and the
`AS6C4008` matched their datasheets pin for pin, the 512K × 8's awkward 25–31 block
included. **The map SRAM did not.** `lib/parts.ts` had pins 21–23 as A9 / A8 / `/WE`;
the part is `/WE` / A9 / A8. The three were rotated, and the package was drawn 600-mil
when the `CY7C128A`'s DIP is the 300-mil skinny one.

That numbering is the **6116 standard** that every 2K × 8 in a 24-pin DIP shares, which
is the uncomfortable part: it is not an obscure part-selection subtlety, it is the
pinout most likely to be written from memory and least likely to be re-read. Nothing
downstream caught it, and nothing could have — `mainboard.circuit.tsx` connects by pin
*name*, and `netlist.check.ts` proves the netlist, so both were correct against a
footprint that would have shipped a board with three pins swapped. **A name-level check
cannot see a number-level error.** The pin numbers become load-bearing exactly once, at
layout, which had not happened yet.

The hand-written `UNVERIFIED_PARTS` list had also gone stale once, still naming
`SRAM_512K` as four packages after finding 1 made it one — which is why the list is
derived from `provenance` instead.

Replaced by: `lib/parts.ts` carries a datasheet `source` on every part, and
`UNVERIFIED_PARTS` is derived.

## README.md §Open items — closed items 1, 4, 7

- **Item 1** read *"⚠ Three of the five motherboard part pinouts are unverified"* —
  closed 2026-09-06 when every pinout was read off a fetched datasheet (finding 4 above
  is what that caught). The live remainder (the `R6551A`/`G65SC51` has no datasheet and
  will not get one) stays in the spec.
- **Item 3** carried a verification aside: the motherboard's 299 plated-hole clearance
  errors were *"a count unchanged by the pinout fix, which is how that fix was checked
  for side effects."* It also said the video card's **nine** GALs were unfitted — the
  card's logic has since consolidated into two ATF1508AS CPLDs plus the `rfa` GAL, all
  fitted.
- **Item 4** read *"⚠ The system RAM's control lines are not driven."* Closed
  2026-09-06: `RAM_CE`, `RAM_OE` and `RAM_WE` reached `U8` and nothing else, behind a
  comment claiming U3 formed the term — U3 forms no such term, and once
  [`gal/mmu.pld`](gal/mmu.pld) existed that stopped being arguable. U3 could not take
  them either: one free pin, and `/CE` alone needs two. They went to **U6**
  (`gal/clkdec.pld`).
- **Item 7** read *"`machine.md` §5 item 1 is still the machine's blocking decision"* —
  closed 2026-09-08 by options A and D. The finding had said the decode "is one GAL term
  today and a board respin after the backplane is etched", and it was right: the
  widening was one literal *removed* from `gal/clkdec.pld`, taken while the backplane
  was still a table.

## README.md §Conventions — the marked-not-deleted convention

The closing bullet read: *"**Superseded and unverified material is marked, not
deleted** — the root `README.md` convention, applied here to the map SRAM's wrong pinout
and to §7.1's four SRAMs."* Replaced 2026-09-08 by this archive: superseded material
moves to `history.md`; unverified material is still marked in place.

---

## ram.md §3, §7, §8 — the backplane cost: three pins → none

§3's title read *"one SRAM and one GAL output (~~three pins~~ none, §5.3)"*, §3.1's
cost table struck out *"~~`A21`–`A24` to the backplane~~"*, and §7 opened: **"This
section wanted `A21`–`A23` on the slot and §5.3 deleted the requirement."** The first
draft of the address path spent three backplane pins on high address bits; §5.3's
open-drain `/IOPAGE` pull made every card go silent above 2 MB instead, for zero pins
and zero card changes. §8's table also carried the struck row *"~~`RAM2`–`RAM4`
populated~~ ~~+3~~"* (see the §6.5 entry).

§3.1 also said *"§8 has the whole memory system at 18"* — a leftover from before §6.2
removed the DIP SRAM; the assembled total is 14 (fixed in place, see §6.5 below).

## ram.md §5.2 — the card megabyte, halved and restored (2026-09-08)

> ⚠ **The card megabyte was halved to eight regions on 2026-09-08 and restored the same
> day.** The halving bought a 512 KB system-RAM quadrant for the second of four DIP
> SRAMs; §6 then dropped the DIP SRAM entirely for SIMM sockets, and **a cost paid for
> something that no longer exists is a cost to take back**. `net.md` and `sdcard.md`
> briefly said three jumper positions and say four again. Recorded because the churn is
> the interesting part: **the halving was right for one day and wrong the next, and the
> thing that changed was not the card space.**

Replaced by: the map at §5.2 — card buffers are 16 regions of 64 KB, unchanged, and §11
item 1 records that nothing is owed.

## ram.md §6.1 — the DRAM rejection, and when it expired (2026-09-08)

`machine.md` §7.1 rejected DRAM because *"DRAM needs a refresh owner and this machine
has none."* The archived phrasing: *"⭐ That changed on 2026-09-08… **The sentence was
true when it was written and is not any more.**"* — `machine.md` §5 item 8's `/WAIT`
hold gave the machine the mid-cycle stall a refresh needs.

## ram.md §6.5, §8 — the motherboard IC chain: ~13 → 9 → 18 (planned) → 14

The count's path: `machine.md` §8 first carried **~13 ICs** (four SRAMs and a decode);
finding 1 (README.md entry above) made the system RAM one part and no decode, **9 ICs**
(2026-09-06); this document's first plan populated three more DIP SRAM footprints
(`RAM2`–`RAM4`, +3) alongside the expansion for a planned **18**; §6.2 (2026-09-08)
dropped all four DIP SRAMs once the SIMM sockets existed — *"a 2 MB of SRAM against
4–16 MB of DRAM in four sockets"* — for the final **14 ICs + 4 SIMM sockets**. §6.5's
table struck the `RAM2`–`RAM4` row without showing the −1 for the system RAM itself; the
cleaned table carries the −1 row so the arithmetic sums to 14, which is the count
`place/svg.ts` draws.

## ram.md §7 — `vctrl` at 64 of 64, then 62 of 64

§5.3 and §7 said `vctrl` was at **64 of 64 I/O** (citing `graphics.md` §10.1.6.3) — the
figure from the arbiter-out-to-a-GAL arrangement (see the gal/README.md CPLD-refit entry
below). The arbiter merged back and the register-file address split out to `rfa`;
`gal/cpld/vctrl.fit` put the part at **62 of 64**.

Then **59 of 64**, and then **64 of 64**, both later the same day: `graphics.md` §6.4.1's cell address was taking
its vertical fields from the sync line counter, which meant `vctrl` exported `V0..V2`
to `vaddr` for a field that should never have crossed parts (`video/docs/history.md`
has the correction). Three pins came back on each part — and `graphics.md` §6.4.9's
fetch cadence spent them again hours later, landing the part at **64 of 64 I/O and
120 of 128 cells**. Both parts still fit with JTAG reserved. The spec carries 64 of
64. **The conclusion is unchanged through all three
figures** — there is no room for an `A21`–`A24` extension, and five spare pins are not
four address lines plus the JTAG the part now uses them for.

## ram.md §11 — closed open items 1 and 2

- **Item 1** read *"~~`machine.md` §5 item 7 blocks step 1~~ — moot"*: the card regions
  were halved for system RAM and restored when the DIP SRAM went away (the §5.2 entry
  above). Nothing is owed and the two card documents are back where they started.
- **Item 2** read *"⭐ ~~Refresh against stretched cycles~~ — SETTLED"*: §6.6 closed it
  on 2026-09-08 — the video card's `/WAIT` is qualified on `VRAMSEL`, so the DRAM bus is
  idle for the whole 40.7 µs and refresh never contends.

---

## gal/README.md §intro — before there were equations

> Nothing in this repository had a GAL equation in it before 2026-09-06 —
> `grep -rn equation` returned three hits and all three were *exit criteria saying the
> equations must fit*. This directory is the start of the fitting…

Replaced by: the directory *is* the fitting; the observation dates it.

## gal/README.md §Deliverables — two live GALs → three (2026-09-08)

The deliverables section read **"Two GALs are live and get burned into silicon"** —
`mmu` and `clkdec`. On 2026-09-08 the register-file address decode split off `vctrl`
onto its own `GAL22V10`, **`rfa`** (`regfile.jedec.ts`, with a CUPL reference in
`jedec/reference/rfa.cupl.jed`), *"taken so `graphics.md` §7.4's broadcast write has
pins to signal through"* — three live GALs. The arbiter `arb` also left `vctrl` and
came back the same day (see the CPLD-refit entry below), so it stays on the superseded
list; its CUPL reference and check are kept anyway, because the design is still what the
CPLD is built from (`jedec/cupl.check.ts`).

## gal/README.md §The register map — proposed → signed off; the entry byte fills up

- The section was headed *"proposed"*, opening: *"That item has been open since the
  project began… It cannot stay open and have equations, so here is the map the
  equations implement."* Signed off 2026-09-06; `machine.md` §5 item 3 closed against
  it.
- The block-register row read *"Bits ~~6~~ **7**–0 = physical ~~`A19`~~ **`A20`**`..A13`"*,
  and the summary line *"Sixteen ~~7~~ 8-bit block registers"* — the entry was 7 bits
  (`A19..A13`, 1 MB) until 2026-09-08.
- The bit-7 note read: *"⚠ **Bit 7 said 'spare and stored' until 2026-09-08, and that
  sentence was the machine's cheapest unclaimed asset.** `machine.md` §5 item 1 option D
  made it **physical `A20`**… The map is now genuinely full at 8 of 8."*

Replaced by: bits 7–0 are physical `A20..A13`; the rationale (one backplane pin, no
parts) stays in the spec.

## gal/README.md §Pin budget — `/IOSEL`'s term chain

The bullet read: *"`/IOSEL` moves to U6. It is ~~`/IOPAGE · A7 · /A6`~~
**`/IOPAGE · /A7`**… (**Two corrections on 2026-09-08**: the term written here was the
wrong polarity, and the window then widened.)"* The two corrections are the next entry.

## gal/README.md §U6 — `/IOSEL` was the wrong 64 bytes, from the day it was written until 2026-09-08

It read **`/IOPAGE · A7 · /A6`**. `LA7` and `LA6` are true-sense on this part —
`mmu.pld` uses them the same way to decode `$FFA0`–`$FFBF` as `A7..A5 = 101` — so that
term is **`$FF80`–`$FFBF`: the MMU's own two windows and the CPU module's vector RAM.**
`$FF40`–`$FF7F` is `A7 = 0, A6 = 1`. The two literals were swapped.

**Every card's `/IOSEL` fired on an MMU block-register write and never on the card
window at all** — six cards onto `D0`–`D7` against U3, which is the failure mode
`/IOPAGE` was added to prevent, arriving from a third cause.

**Five artefacts carried it and agreed**: `clkdec.pld`, `clkdec.v`, `clkdec.jedec.ts`,
`clkdec.model.ts` and the README. It reached `clkdec.jed`, so it would have reached a
programmer.

**Why 15 passing claims did not see it.** `clkdec_tb.sv` asserted
`p == 0 && a7 == 1 && a6 == 0` under the message *"/IOSEL is $FF40-$FF7F: the I/O page
with A7,A6 = 01"*. **The assertion and its own message disagree**, and the
implementation was written from the assertion. `mainboard.circuit.tsx`'s comment stated
the intent correctly too, directly above wiring that was fine.

> **This is `jedec/cupl.check.ts`'s lesson one step further out.** That file established
> that our assembler and our simulator share a device description and therefore agree
> whatever it says, so a second implementation is what breaks the tie. **The same is
> true of a check and the design it was written beside**: both came out of one
> understanding, so the check tested the understanding. Atmel's CUPL could not help here
> either — it compiles the equation it is given.

**And then the window widened**, `machine.md` §5 item 1 option A, in the same pass:
`$FF00`–`$FF7F`, 128 bytes — `/IOPAGE · /A7`, one literal, cheaper than the broken
two-literal version.

Replaced by: the one-literal decode and the sweep-`A6` testbench claim, which would have
failed loudly on the old equation.

## gal/README.md §U6 — `/WAIT` had a producer and no consumer (fixed 2026-09-08)

`vctrl` had driven `/WAIT` open-drain since the video card was captured
(`WAIT.oe = SPANBUSY & VRAMSEL & !IOPAGE`), and **U6 had no `/WAIT` input at all.**
`machine.md` §2's "it holds E" named an effect with no mechanism: the span writer held
nothing, and the CPU read VRAM out from under it. Fixed 2026-09-08 — `machine.md` §5
item 8 — with the hold terms the spec describes; `E` went from 7 terms of 16 to 8, and
`& E` was added at the source. (`access.jedec.ts` later added `!RW` as well — only
writes wait, 2026-09-08, so reads are never exposed to the 40.7 µs bound.)

## gal/README.md §The video CPLD refit — a package worth noticing, and a GAL that lived one day (2026-09-08)

`vctrl.pld` gained three literals on 2026-09-08: `A6` on `REGSEL`, `/A20` on `VRAMSEL`,
and `& E` on `WAIT.oe`. It fit at 78 of 80 I/O and 123 of 128 logic cells, on the
fitter's second placement pass — but:

⚠ **The committed fit targeted a `P1508T100` — a TQFP100 — where the `.pld` declared a
PLCC-84 and `regfile.ts` said "vctrl fits at 62 of 64".** The design and its fit had
disagreed about the package, and nothing checked it. **The card is a PLCC-84**, and the
two extra inputs are what forced the question:

| | I/O | logic cells |
|---|---|---|
| as committed, TQFP100 | 76 / 80 | 123 / 128 |
| + `A6`, `/A20`, `& E`, still TQFP100 | 78 / 80 | 123 / 128 |
| on a PLCC-84 | 76 needed, 64 available — does not fit | |
| arbiter moved out to a `GAL22V10` | 64 / 64 | 112 / 128 |

**The arbiter was the cheapest ten pins on the part to give back**: eight grants, `WAIT`
and `SPNGRANT` are exactly ten macrocells against a `GAL22V10`'s ten; its inputs are
backplane signals or already exported; and `access.jedec.ts` never stopped carrying it
as a standalone design with `access.check.ts` still checking it. At 64 of 64 the part
had zero spare — JTAG's four I/O did not fit, so `vctrl` was to be programmed out of
circuit, and *"if in-circuit programming is wanted back, `RA0`–`RA4` and `WSTB` onto a
second `GAL22V10` is the obvious six pins."*

That escape was then taken instead of the arbiter's: **the register-file address decode
split out as `rfa`** and **the arbiter merged back into `vctrl`** the same day
(`jedec/cupl.check.ts`: *"arb went out of vctrl and back in, both on 2026-09-08"*).

Replaced by: `vctrl` fits a PLCC-84 at 62 of 64 I/O and 97 of 128 logic cells
(`cpld/vctrl.fit`), with the arbiter inside and `rfa` live beside it — still programmed
out of circuit.

## gal/README.md §Open-drain — every open-drain output in the machine drove its line the wrong way

Compiling `/WAIT` as a GAL for the first time made `jedec/cupl.check.ts` **disagree with
Atmel's compiler on exactly one signal.** Both emitters wrote `'b'0` for the no-terms
`.oe` idiom; the pin is declared `PIN n = !WAIT`, so CUPL inverts it and the pin drives
HIGH when enabled — on a shared line, a card fighting the motherboard's 3.3 kΩ pull-up
and every other driver on it.

**Three cells used the idiom and all three were wrong**: video's `/WAIT`
(`access.jedec.ts`), **video's `/IRQ`** (`sync.jedec.ts` — the line PS/2, serial and net
also pull), and audio's `/FIRQ` (`audio.jedec.ts`). Both emitters were changed to write
`'b'1` for an active-low cell, and every affected device was refitted.

> `cupl.check.ts`'s header records two earlier errors that "178 passing checks could not
> find, because the assembler and the fuse-map simulator shared the mistake". **This one
> was worse.** The mistake was in the **emitter**, upstream of both — so it was
> invisible to the assembler, the simulator, and every check written against either.
> Only a second compiler could see it, and only once a design using the idiom was built
> as a GAL instead of merged into a CPLD. **`machine.md` §5 item 9.**

Replaced by: the `'b'1` convention, stated in the spec.

## gal/README.md §Toolchain — stale progress counters

The toolchain table's first row said *"five parts assemble, fit and are checked at the
fuse level"*, and the closing paragraph *"Two GALs are written of roughly twenty in the
machine"* — both from before the video sync/scan/access/sequencer fits, the audio five,
and `rfa`. Every GAL design now assembles and is checked at the fuse level, and three
ship.

## gal/README.md §Open items — closed items 1 and 4

- **Item 1** read *"~~Nothing has been fitted~~"* — closed 2026-09-06 by `jedec/`, with
  a correction: the item had said *"product terms are all small (the widest is an
  8-input AND)"*, which counts literals inside a term, and the macrocell's limit is
  **terms** — `MAPOE` is nine of them (finding 5).
- **Item 4** read *"~~The scan-address pair will not fit either~~"* — closed at 17 of
  20 with three spare. Its tail then carried the next scare: *"the sequencer's other
  half… does not fit in the one part left. `graphics.md` §19 item 23 carries the
  budget: 20 macrocells wanted against 10 left… a budget rather than a fit because the
  span writer's state machine is inherited from minimal256 and has never been written
  down."* The span writer has since been stated and fitted (`seqctl.jedec.ts`,
  respecified for 8 × 8 cells per `graphics.md` §7.4), and the card's logic consolidated
  into the two CPLDs plus `rfa`.

## gal/README.md §place.ts — the claim that had to be weakened

> The placer used to refuse an over-wide equation with *"sorted pairing is optimal, so
> this does not fit on this part at all."* Sorted pairing is optimal over **assignments
> of a fixed set of equations**. It says nothing about whether the equations are as
> small as they could be, and `SPNGRANT` is the counter-example. The message now says
> which of the two it means.

Replaced by: the same distinction, stated as the message's present behaviour.

---

## place/README.md §intro — the unchecked area claim

> Nothing in this repository had ever been placed; `graphics.md` §14 carried an area
> claim (*"~150 of 160 cm²"*) that nobody had checked against a package outline.

Replaced by: the study itself — every board drawn 1 : 1, and the claim checked. The
check's verdict (the video card over budget on a Eurocard) stays in the spec.

## place/README.md §What it found — the 250 × 100 intermediate format

> That is what moved the card format to 250 × 100 and then to per-card lengths.

The single oversized format lived between the Eurocard and the per-card lengths; the
spec keeps only the endpoint (`../README.md`'s decisions table).
