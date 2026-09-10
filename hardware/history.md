# Hardware — archived history

Superseded passages from the `hardware/` documents — [`README.md`](README.md),
[`ram.md`](ram.md), [`gal/README.md`](gal/README.md) and
[`place/README.md`](place/README.md) — moved here when the specs were cut down to the
present design. Entries are organized by source file and section; the archived text is
kept verbatim or lightly trimmed, because the archive is the record.

---

## `lib/parts.ts` `HC4040` and `FLASH_512K` — the last two unverified pinouts, and finding 4 repeating (2026-09-10)

The two pinouts `lib/parts.ts` still carried "from familiarity" were read off datasheets
fetched from Octopart's CDN. **One was right and one was finding 4 all over again.**

### `FLASH_512K` — right on all 32 pins

The note said the numbering was "the JEDEC 32-pin byte-wide flash pinout written from
familiarity — which is EXACTLY the failure mode finding 4 records", and named two pins to
check. Both were already correct: pin 3 is `A15` (not `A14`, which is what the `AS6C4008`
above it in the file has there) and pin 31 is `/WE`. The 600-mil body is right too.
`SST39SF040.pdf` Figure 4. **The suspicion was well-placed and the work was sound.**

### `HC4040` — three pins rotated, on the same board, in the same way

The note said: *"The Q outputs are NOT in pin order on this part, which is exactly what
gets written from memory wrongly: check Q0–Q11 individually."* They were, and it was:

| pin | file said | `CD74HC4040.pdf` says |
|---|---|---|
| 12 | `Q10` | **`Q8`** |
| 13 | `Q8` | **`Q7`** |
| 15 | `Q7` | **`Q10`** |

A 3-cycle rotation of three outputs — **finding 4's map SRAM was three pins rotated too.**

⚠ **What makes it worth an entry rather than a diff is that nothing could have caught
it.** `mainboard.circuit.tsx` wires the refresh timebase as `Q8: "net.REFCLK"` — **by
name** — so the netlist is correct and `check:netlist` passes. The error lives in the pin
*number* behind the name and surfaces for the first time at layout. Finding 4's own
sentence, unchanged: *a name-level netlist check cannot see a number-level footprint
error.*

**And it would not have failed loudly.** `REFCLK` would have come off physical pin 13 —
`Q7`, not `Q8` — halving `ram.md` §6.3.1's interval from 10.16 µs to 5.08 µs. 512 rows in
2.6 ms against the DRAM's 8 ms, so refresh still holds; the machine would have worked, and
spent twice the refresh bandwidth for ever. `MR` active high was confirmed as stated.

### What changed so this cannot recur silently

`UNVERIFIED_PARTS` had been derived from `provenance` since 2026-09-06 and **nothing
imported it** — no check read it, and the comment beside it claimed it was empty while it
held three parts. `lib/netlist.check.ts` now pins its contents against a declared
`KNOWN_UNVERIFIED`, so adding a part without a datasheet fails the check and so does
confirming one without striking it off. **`SIMM30` is the one left**, and it closes
against a JEDEC standard rather than a vendor sheet.

⛔ **The gap this leaves is the cards.** `check:netlist` reads the motherboard's
`circuit.json` and nothing else, so **no card's pinout is checked by anything at all** —
which is how the I/O card's `TL16C550C` came to have `RD1` and `RD2` swapped
(`io/serial/docs/serial.md` §12.1, found the same day).

---

## `ram.md` §3.1 — "Isolation `'245`: 0 — both SRAMs sit on the same `D0`–`D7`" (2026-09-09)

§3.1's cost table for the second map SRAM carried this row:

> | Isolation `'245` | **0** — both SRAMs sit on the same `D0`–`D7`; the address picks which is written |

and the "Address path alone" line below it read **"9 ICs → 10 — §8 has the whole
motherboard at 17"**. §8's own table had a matching row, *"U3 high-byte write strobe: 0 —
pin 23 is free"*, and `mainboard.circuit.tsx` was drawn to the table: U1B's `DQ0`–`DQ3`
went to physical `A24`–`A21`, `DQ4`–`DQ7` were `noConnect`, and **no pin of the high map
SRAM touched `D0`–`D7` anywhere on the board.**

**Two common-I/O SRAMs cannot share one buffer.** A common-I/O SRAM drives its own `DQ`
pins for the whole of every translation, because on this board those pins *are* the
physical address. So the two parts are two separate nodes — `A20`–`A13` and `A24`–`A21`
— and twelve bits of map entry need twelve bits of buffer where a `'245` has eight.

⛔ **The consequence is `design-review2.md` M-1's own, surviving M-1's own repair.** M-1
was diagnosed as a decode fault — `LA3` doing two jobs — and repaired into §4.3's two
windows, and the high byte of every map register stayed **unwritable and unreadable**
because there was nothing to write it through. Everything above physical 2 MB was still
out of reach.

**Repaired at +1 IC (U18) and U3's last pin (`ISOOE_HI`).** ⚠ And it narrowed U6: see
the `clkdec.pld` entry below.

## `gal/README.md` / `ram.md` §11 item 5 — U3 pin 23 as a spare input (2026-09-09)

The pin budget chose the row *"6 outputs, 16 available inputs, 15 needed, one pin
spare"*, and `mmu.jedec.ts` left pin 23 undriven on purpose so the macrocell held it at
high-Z:

> **PIN 23 IS DELIBERATELY NOT DECLARED**, and that is two spare INPUTS rather than two
> driven lows… Undriven, the macrocell holds the pin at high-Z and it is a sixteenth
> input if the board ever wants one.

`ram.md` §11 item 5 closed on the same reasoning: *"U3 needs no second write strobe and
is untouched… pin 23 stays a spare **input**."* That is still true of a write **strobe**
and it was never true of an output **enable**. The part takes the budget's other row now
— **7 outputs, 15 available inputs, 15 needed, nothing left** — and **U3 is full.**

## `gal/clkdec.pld` — `BOOTOE` as the complement of the map-SRAM chip-enable UNION (2026-09-09)

Fixed the same morning as `design-review2.md` M-2 and M-3, and wrong by lunchtime:

```
mapsel = RUN & !IOPAGE                       /* translating                  */
       # IOPAGE & LA7 & !LA6 &  LA5 & !LA4   /* $FFA0-$FFAF, the low byte    */
       # IOPAGE & LA7 & !LA6 & !LA5 &  LA4 ; /* $FF90-$FF9F, the high byte   */
!BOOTOE = mapsel ;
```

described as *"the '244 drives physical `A20`–`A13` exactly when the map SRAMs do not"*,
at three product terms.

⚠ **It is a rule about a NET, written about a PART.** Physical `A20`–`A13` has exactly
two drivers: U1, and this buffer. U1B drives `A24`–`A21` and those never leave the board.
The union was correct only while **one** `'245` served both windows, because that buffer
then drove `A20`–`A13` during a high-byte write as well. The moment U4 shut for the high
window, the union left `A20`–`A13` with **no driver at all** for the sixteen high-byte
writes of every boot — M-2 again, in a narrower window. `mainboard_tb` reported it as
*"16 of 32"*.

It is `MAPCE_LO` alone now, at **two** product terms, and the rule is stated about the
net: ⭐ **the buffer drives a net exactly when that net's other driver does not.**

## `ram.md` §11 item 3 — "Layout A or B… the only genuinely open part of §3" (2026-09-09)

> 3. **⚠ Layout A or B** (§4) — a NitrOS-9 cost question, not a hardware one, and
>    the only genuinely open part of §3.

Superseded by §4.3's Layout C, and the item's own framing is the thing worth keeping:
calling it *"a cost question, not a hardware one"* is what let the board take Layout B's
index and Layout A's byte select, which is neither, and put everything above physical
2 MB out of reach. [`../docs/design-review2.md`](../docs/design-review2.md) §3.3.

---

## `ram.md` §6.3 — "refresh needs no counter", and the package that hid behind it (2026-09-09)

The bank's parts list was **+5 ICs**: four sockets, U9, U10 and three `'157`. Under it:

> ⭐ **Refresh needs no counter.** **CAS-before-RAS** makes the DRAM generate its own row
> address, so the refresh row counter a 1980s design would have carried — a `74HC4040`
> and its mux path — is **not on this list**. One request every ~15.6 µs, arbitrated by
> U10.

**Every word of that is true about the ROW counter and false about the INTERVAL timer**,
and the sentence covers both without distinguishing them. They are different things: one
supplies an address, the other says *when*. CAS-before-RAS deletes the first outright.
The second is 15.6 µs of `CLK25` = **393 counts, nine macrocells on a part that has
ten** — so it cannot live on U10, and nothing else on the board produces it.

It is a `74HC4040` after all, doing the other job. **The bank is +6 ICs and the
motherboard is 18**, and the naming irony is recorded because it is exactly how a package
goes missing: the part was *named* in the sentence that said it was not needed.

⚠ **The rejected alternative is worth keeping.** `HSYNC` is on the backplane and a line
is 31.78 µs, so two bursts a line would refresh 512 rows in 8.1 ms. It comes from the
video card — and a machine whose RAM forgets when you pull the video card is the failure
`machine.md` §1 puts the master oscillator on the motherboard to avoid. Same argument,
one subsystem along.

---

## `ram.md` §6.3 / `mainboard.circuit.tsx` — the SIMM address mux was wired a bit out (2026-09-09)

The board comment read:

> Row is physical A11-A1 and column A22-A12, which puts the SIMM's own A0 on the CPU's
> A1 - a 30-pin module is byte-wide and the low address bit is inside it.

⚠ **The last clause is backwards.** A 30-pin SIMM is ×8 — *byte*-wide — so its `A0` **is**
the CPU's `A0`. There is no low bit hidden inside it; that is true of a ×16 or ×32 module,
where the module's own address counts words. Wired as written, every DRAM access would
have landed on the wrong address and the bottom bit would have been unreachable.

Corrected to **row = physical `A10`–`A0`, column = `A21`–`A11`**, and
`lib/netlist.check.ts` asserts both halves so it cannot drift back.

**And the mux select stopped being a GAL output.** It was `MUX_ROW` from U10; it is `E` —
high for counts 6–11 of U6's divider, which is exactly the column window. One wire, and
it is the macrocell that let U10's nine-output design fit at all (§6.3.1).

⚠ **The mapping is for 4M × 8 modules and a 1M × 8 will not work in it** — a 10-bit
module ignores `MA10`, which drops physical `A10` out of the address entirely. §11 item 7
recommended 1 MB modules on availability grounds and was written without that in view; it
now carries three attributes to match instead of one.

---

## `gal/clkdec.pld` — the system RAM's control lines, and the three macrocells boot mode took (2026-09-09)

U6 carried a third job until 2026-09-09: `ramsel`, `RAM_CE`, `RAM_OE` and `RAM_WE`,
decoding one `AS6C4008` at physical `A20 = 0, A19 = 0`. `ram.md` §6.2 removed that part
from the design on 2026-09-08 and **this file kept driving it for a day** — three outputs
and two input pins on the machine's tightest GAL, all of them going to a package that was
no longer on the board.

The equations, kept because U9's ROM decode makes the same `/OE`-versus-`/CE` move for
the same reason:

```
ramsel = !IOPAGE & !A19 & !A20 ;
RAM_CE = ramsel ;
RAM_OE = ramsel & RW ;
RAM_WE = ramsel & !RW & E ;
```

> **`/OE` is qualified by `R/W`, and that is not decoration.** With `/OE` tied low the
> SRAM drives `D0`–`D7` from `/CE` time (~140 ns) until `/WE` asserts at E-rise (~238 ns)
> while the CPU is also driving write data from ~229 ns — about **90 ns of contention on
> every write.** The `AS6C4008`'s truth table permits the tied-low arrangement; this
> machine's bus timing does not.

⭐ **What replaced them is boot mode**, and it fitted exactly: `RUN` on pin 22 and the
boot buffer's output enable on pin 14, with **pin 23 left undeclared as a spare input —
the first spare pin this part has ever had.** Inputs `A19` (pin 7) and `A20` (pin 9) went
with the decode and became `LA5` and `LA4`; `LA0` took pin 11.

The `netlist.check.ts` assertions that went with them — *"`RAM_CE` runs from U6 to the
system RAM"* and the two beside it, which closed `README.md` open item 4 on 2026-09-06 —
are replaced by their inverses: **U6 no longer drives them and U8 is not on the board.**

⚠ **`clkdec.pld`'s pin 6 comment was wrong for a day in the other direction.** It read
*"`LA6` — KEPT WIRED, USED BY NOTHING"*, on the argument that keeping the trace made
`$FF80`–`$FF8F` a one-line change rather than a respin. Boot mode reads `LA6` twice, in
`vecsel` and in `ctlwr`. **That is the second time on this part that a trace kept for no
reason turned out to have one.**

---

## `ram.md` §11 items 5 and 6 — "U9 may not fit", and it fits at six of ten (2026-09-09)

Item 6 read:

> **⚠ Fit U9 and U10, and U9 is no longer comfortable.** The four SRAM chip selects went
> with the SRAM, but §6.7 put the boot ROM's two selects, `BOOT`, `VECSEL` and the
> `'541`/`'245` enable pair back — **ten outputs on a `GAL22V10`'s ten**, before counting
> inputs.

and `machine.md` §7.2 and `hardware/README.md` open item 8 both carried the warning.
**Fitting the part found the count wrong in both directions**, which is the whole reason
`gal/` exists:

| | counted | actual |
|---|---|---|
| SIMM window selects | 4 | **1** — the four windows are `A24..A22` = 001/010/011/100, and those codes are already distinct in `A23:A22` alone. U10 takes those two lines directly and picks its own RAS |
| map-SRAM chip enables | 0 | **2** — nobody had counted them. §3.1 said *"the address picks which is written"* and nothing said what forms that. It is `LA3` |
| `BOOT`, `VECSEL`, the enable pair | 3 | **0** — they went to U6, which already had the clock and the reset a registered mode bit needs |

**Six outputs, fourteen inputs, two spare macrocells, widest equation five terms of
sixteen.**

**Item 5 — *"Does U3 fit the second write strobe?"* — is closed by not needing one.** It
asked whether U3's free pin 23 could become the high map byte's `/WE`. U9's two chip
enables make U3's single `MAPWE` reach both parts with the chip enable deciding where the
byte lands, so **U3 is untouched by the entire memory system**: same fuse map, same 23
checks, same testbench, and pin 23 still a spare input.

⚠ **And the fit found a defect nobody had written down.** The `/IOPAGE` pull has to be
gated on `RUN`: during boot the high map SRAM is deselected and `A24`–`A21` float, so an
ungated above-2 MB compare asserts `/IOPAGE` at random — and `/IOSEL` is `/IOPAGE · /A7`,
so a random assertion makes every card decode a boot fetch and drive `D0`–`D7`. One
literal on four terms, between a machine that boots and one that does not.

---

## `machine.md` §7.2 / `ram.md` §6.7 — the boot address buffer was a `'541` (2026-09-09)

Both documents specified a **`74HCT541`** driving physical `A19`–`A13`, and
`hardware/README.md` open item 8 quoted it. Two things changed when the board was drawn:

- **It is a `74HCT244`.** Both are octal three-state buffers and either does the job;
  the `'244`'s datasheet is in `reference/datasheets/` and the `'541`'s is not, so the
  `'244` is the one whose pin numbering is **read** rather than remembered. That is
  `hardware/README.md` open item 1 deciding a part choice, which is what it is for — and
  `hardware/history.md`'s finding 4 is what happens when it does not.
- ⚠ **It drives eight bits, not seven.** The ROM needs `A19`–`A13` above the untranslated
  `A12`–`A0`; `A20` is on the list because **it reaches the backplane**, and a floating
  `A20` during a boot fetch would let the video card's VRAM select (`A20 = 0, A19 = 1`)
  answer at random. Driving all eight to zero puts every card's memory decode out of
  range by construction.

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


---

## 2026-09-09 — design-review2.md's corrections

### §6.3 — the SIMM module size

**Was:** *"4 | 30-pin SIMM socket | ×8 or ×9, 1 MB or **4 MB** each — **4 to 16 MB**"*.

**Why it moved:** §6.3.1's own mux mapping paragraph, added the same day, says a
**1M×8 module will not work** in the row `A10`–`A0` / column `A21`–`A11` wiring — it
has ten row and ten column bits and ignores `MA10`, which drops physical `A10` out of
the address entirely — and that the correct 1 MB mapping is *"a rewire, not a jumper"*.
Only 4M×8 works as drawn, so the machine is **4, 8, 12 or 16 MB** and never 1, 2 or 3.
`machine.md` §0's "4–16 MB" was right by accident.

### §4 — Layout A and Layout B, and what not choosing cost

**Not superseded — extended.** §4 still closes with *"Neither is obviously right … the
decision belongs to whoever owns the NitrOS-9 port"*, and that remains the state of the
question. What is added is that **the board took both answers**: `u9.jedec.ts` decodes
Layout A's `LA3` byte-select while `mainboard.circuit.tsx` wires Layout B's `LA3` task
index onto the same `MAPA3` line, so no task can have both bytes of a block register
set. `../docs/design-review2.md` §3.3 (M-1) has the simulation and both repairs.


---

## 2026-09-09 — §4's layouts, superseded

**Was:** *"Neither is obviously right. Layout A is cleaner hardware and a bigger
divergence; Layout B is compatible and awkward. The decision belongs to whoever owns the
NitrOS-9 port."*

**Why it moved:** the board had taken different halves of the two — `u9.jedec.ts`
decoded Layout A's `LA3` byte-select while the `'157` carried Layout B's `LA3` task
index — so no task could have both bytes of a block register set and nothing above
physical 2 MB was reachable. §4.3 is a third layout that costs neither: two windows out
of the 32 bytes at `$FF80`–`$FF9F` that decoded nowhere, outside the geographic window,
with U3 the same size and U9 one pin smaller. §4.1 and §4.2 are kept for what each
costs, not for what the board does.
