# Serial — archived history

Everything here is superseded. [`serial.md`](serial.md) describes the present design;
this file records what earlier revisions of it said, what the 2026-09-04 design review
([`docs/design-review.md`](../../../docs/design-review.md) §6, findings IO-S1…S7) found,
the `$FF`-map narrative this card sat in the middle of, and what replaced each claim.
Entries are ordered by the spec section they came from.

## §0 / §6 / §7 / §9 / §12 / §13 — the 6551 became a `16C550` (2026-09-09)

**§4.5's tier 1 was taken.** The card is a `TL16C550C`, and what follows is the part it
replaced. §4, §5 and §5.4 stay live in the spec because they are the *argument* that
produced the change rather than a description of the card.

### §9 — "Total: 3", and the tier priced at "+1 IC"

The budget's first row was:

> | 1 | `G65SC51` (or `R6551A`) | the ACIA — **not `W65C51N`**, §3.3. **Speed grade is part of the specification, not a preference: 2 MHz minimum for ÷12, 4 MHz for fast-E — §3.4** |

and §9.1's tier table put **Tier 1 at 4 ICs** against a base of 3 — a figure §5.4
repeated.

⚠ **That was a counting error and it survived in two tables.** The base total read
*"Total: 3. Plus a 1.8432 MHz crystal…"*, with the crystal deliberately **not** a
package; the tier row listed *"`16C550`, `MAX232`, GAL22V10, **7.3728 MHz crystal**"* and
counted four. There is a crystal either way and only its frequency changes. **The
`16C550` replaces the 6551 one for one**, and the decision was easier than the document
made it look for as long as the error stood.

The sourcing note that went with the row, kept because it states a problem this card no
longer has:

> row 1 is the only part on this card that cannot be substituted with a jellybean, and it
> now has **two** attributes to match, not one — *not* a `W65C51N` (§3.3), **and** a speed
> grade adequate for the E rate the machine will actually run at (§3.4). A `G65SC51P-2`
> covers the specified ÷12 rate and **does not cover fast-E mode**; only a genuine 4 MHz
> grade does. Record which grade was bought, because the difference is invisible on the
> bench at ÷12 and shows up as occasional corrupted bytes at ÷8.

### §7.2 — the four registers

| Off | Name | R/W | Function |
|---|---|---|---|
| `+$0` | `DATA` | R/W | read: received byte, clears `RDRF`. write: transmit byte, clears `TDRE` |
| `+$1` | `STATUS` | R | below |
| `+$1` | `RESET` | W | programmed reset — the written value is ignored |
| `+$2` | `COMMAND` | R/W | parity mode, echo, transmitter interrupt control and `/RTS` state, receiver interrupt disable, `/DTR` state |
| `+$3` | `CONTROL` | R/W | baud rate select, receiver clock source, data-word length, stop bits |

**This is the map NitrOS-9's `sc6551` expects** (§10.1), which is why it is kept whole
rather than summarised: the driver question changed with the part.

### §7.3 — `STATUS`, and the argument that reached three other documents

| Bit | Meaning |
|---|---|
| 0 | parity error |
| 1 | framing error |
| 2 | **overrun** — a byte arrived before the last was read |
| 3 | `RDRF` — receive data register full |
| 4 | `TDRE` — transmit data register empty. ⚠ broken on the `W65C51N` |
| 5 | `/DCD` state |
| 6 | `/DSR` state |
| 7 | interrupt pending — **reading `STATUS` clears it** |

> Reading `STATUS` clears the interrupt, so the `/IRQ` handler's first action on this
> card is a `STATUS` read, and the error bits it carries must be consumed in that same
> read.
>
> **That single property fixes this card's position in the shared-`/IRQ` chain: last.**
> … **The consequence for §10.2's handler: no probe-and-defer.** A handler that reads
> `STATUS` to decide "not mine" and returns has already destroyed the error bits and
> dropped the interrupt.

⭐ **This is the most consequential thing the part change deleted.** `machine.md` §4.1
built the machine's polling order on it — *video → net → PS/2 → serial (last, always)* —
and recorded as a live cost that **the correctness ordering and the frequency ordering
disagreed, and the disagreement was paid on every dispatch.** A `16C550`'s `IIR` names the
interrupting source, or says there is none, **and destroys nothing**; the error bits moved
to `LSR`, read only when `IIR` has said to. `machine.md` §4.1 keeps the order for now and
says plainly that it is a preference rather than a rule.

### §6 — two rows that were properties this card had for free

> | `φ2` | backplane `E` — **and this is why §3.4's speed grade is a card-level
> constraint**: the part is clocked by whatever rate the machine is running at |
>
> | `/RES` | backplane `/RESET` — **the whole card comes up in a defined state from one
> pin**, which is the property `ps2.md` §8.4 had to add two changes to acquire |

The first is gone entirely: a `16C550` has no bus clock pin, which takes §3.4 *and*
`machine.md` §1.1's fast-E experiment off this card's plate. **The second is gone as a
freebie and survives as a requirement** — `MR` is active *high*, so it goes through the
GAL, and the property now depends on one macrocell being right rather than on a wire
being short.

> | `/IRQ` | backplane `/IRQ`, **open-drain — confirm this on the datasheet** |

⚠ **`INTR` is active-high and totem-pole.** It cannot wire-OR at all; the GAL inverts it
through an open-drain macrocell. The datasheet question this row raised was the right
question, and the answer turned out to be "no".

### §7.1 — the window was `$FF54`–`$FF57`

Four bytes immediately above PS/2's four, in a merged card decoding `$FF50`–`$FF57`.
**Eight registers do not fit where four did**, and those eight bytes were wedged between
audio at `$FF40` and storage at `$FF58` — so the card moved to a sixteen-byte window at
`$FF30` rather than displacing two other cards, and handed `$FF50`–`$FF57` back. The
machine's `$FF` margin went from 64 free to **56**.

### §12 step 0 and §13 items 6 and 9

Step 0 was *"Decide §5.4's tier, because Tier 1 changes which part step 1 sources"*;
items 6 and 9 were that decision and the speed grade hanging on it. All three are closed
by the part change. **Item 5 is not** — it changed from "which 6551, and is it in
production" to ⚠ **"is the `TL16C550C` still made in PDIP-40?"**, because TI's catalogue
lists PLCC-44 and TQFP-48. `net.md` §13.6's lesson holds either way.

---

## §3.3 — fast-E's reasons, three to two (2026-09-11)

The video card's VRAM read-back was built prefetched (`video/docs/graphics.md` §11) and stopped being a reason ÷8 is unsupported.

The text it replaced:

> > **experimental and not guaranteed**, and this is one of three independent reasons why
> > (`machine.md` §5; the others are the video card's VRAM read-back and the real
> > HD63C09E's 333 ns `t_cyc` minimum).
>

---

## §(intro) The README framing this document superseded

Archived text:

> **This supersedes [`../README.md`](../README.md)'s framing**, which said the first
> decision was "a period RS-232 port (~14 ICs) or a fast host link (~5)". That was a
> false choice, arrived at by looking only at the Minimal 64x4 and at colormin's
> `backplane.md` §5 — both of which build a UART out of discrete logic because their
> machines have no room for anything else. §4.1 and §4.2 explain why neither applies
> here.

The README was later rewritten around the 6551 verdict, and the false-choice framing is
gone from both files; the substantive rejections live in `serial.md` §4.1 and §4.2.

## §3.3 "/WAIT" naming — the retired word "stretch"

Archived text:

> ⚠ **This paragraph used to call `/WAIT` "stretch E".** It is a **wait state**, and the
> word "stretch" is retired on this card: `machine.md` used "stretch mode" for the
> ÷8 *faster* rate, so the two documents were using one word for opposite things. Per the
> project-wide naming decision: **`/WAIT` is a wait state; the ÷8 rate is "fast-E
> mode".**

Replaced by: the one-line naming note in §3.3.

## §3.4 The ÷8 rate — unchecked before the review (2026-09-04, IO-S1)

The previous revision worked the speed-grade numbers only at 2.0979 MHz and did not
mention ÷8 at all, in a document that otherwise re-derives everything. Replaced by:
§3.4's two-rate table (÷12 = 2.0979 MHz, ÷8 fast-E = 3.1469 MHz; 57 % over a 2 MHz part,
5 % over a 3 MHz one) and the "specified at ÷12 only" compatibility line.

## §3.2 / §13 item 2 The `sc6551` claim, graded up (2026-09-04, IO-S6)

The claim "NitrOS-9 ships a 6551 driver" was originally listed as unverified. Graded up
at the review: NitrOS-9's CoCo 3 tree does ship an `sc6551` SCF driver for the Deluxe
RS-232 Pak, so §3.2's "base-address change and nothing else" posture is likely real.
What remains open shifted from the driver's existence to whether §7.2's recalled
register layout matches the one it talks to — which merges §13 item 2 into item 1.

## §4.5 The `16C550` option — added 2026-09-08

§4.5 and §5.4 were added on 2026-09-08, after `machine.md` §5 item 1 widened the I/O
window: until then the map had four bytes free and an eight-address part was not an
option, so §4's survey (written against a four-byte budget) never asked whether a better
UART chip exists. The section itself stays in the spec because the decision (§13 item 6)
is still open; this entry records only the date and the trigger.

## §5 The throughput table — receive-only (2026-09-04, IO-S3)

Archived text:

> ⚠ **The previous revision's table counted receive interrupts only** and drew the
> ceiling from it. Corrected per the 2026-09-04 design review (IO-S3): 19,200 baud full
> duplex is 3,840 interrupts/s, which at the pessimistic dispatch figure is **73 % of
> the CPU** — the number the previous revision attached to the 38,400 "trap" row is what
> 19,200 actually costs a terminal.

The old text also called 9600 "comfortable" on the strength of the half-duplex figures.
Replaced by: §5's paired half-duplex/full-duplex tables and the ceiling restated toward
the low end.

## §5.1 "/RTS makes overruns throttling" — false for a 6551 (2026-09-04, IO-S2)

**The bullet below was wrong, and it was called the single most valuable thing to wire:**

> - **Hardware flow control.** The 6551 drives `/RTS` and reads `/CTS`. With `/RTS`
>   wired (§8) an overrun becomes *throttling* rather than lost data — the far end stops
>   and waits. This turns "too fast" from a correctness bug into a performance number,
>   and it is the single most valuable thing to wire on the connector.

That describes a 16550. On a 6551, `/RTS` is a bit in `COMMAND`, not a receiver-driven
output. Found at the 2026-09-04 design review (IO-S2). Replaced by: §5.1's account of
ISR-driven `/RTS` at a ring-buffer high-water mark, the `/RTS`/transmit-interrupt field
conflict, and the four designed-for consequences.

## §7.1 The `$FF` map — proposed, closed, reopened, widened

The map narrative this section carried, in order:

1. **This card's `$FF54`–`$FF57` closed the original map** — with it, the `$FF40`–`$FF7F`
   geographic decode was exactly 64 of 64, nothing free. The section title read
   "Placement — and the `$FF` map is now **full**", and the table's `$FF58`–`$FF5F` rows
   were a disk-controller reservation, then storage plus four returned bytes.
2. **`storage/docs/sdcard.md` §6.1 returned four bytes** (it needed only half the disk
   reservation), reopening `$FF5C`–`$FF5F`.
3. **`net/docs/net.md` §5.1 spent those on 2026-09-07** and the map was full again —
   which is what escalated `graphics.md` §17's "widen the window now" from advice to
   blocking, and made `machine.md` §5 item 1 the machine's highest-priority open item.
   The archived warning: after this card there was no room for a second serial port, a
   third PS/2 port, a network interface, or a SCSI controller, "and the disk
   controller's eight bytes are a guess made on its behalf by two cards that took theirs
   first".
4. **On 2026-09-08 `machine.md` §5 item 1 closed**: the geographic window widened to
   `$FF00`–`$FF7F`, 128 bytes with 64 free, and `/IOSEL` became *cheaper* in the
   process — `/IOPAGE · /A7`, one literal where the 64-byte decode was two. `A6` left
   the strobe, which is why every card's decode grew to `A0`–`A6`.

Replaced by: §7.1's present eight-row map (matching `hardware/cards/windows.ts`) and its
two standing consequences (the seven-bit decode; addresses no longer the scarce
currency). The board merge with PS/2 (2026-09-08, `hardware/cards/io.circuit.tsx`,
14 ICs, one eight-byte decode) arrived with the widening and stays in the spec as
present design.

## §6 The decode row — "geographic `/IOSEL`" and `A2`–`A5`

The `CS0`/`/CS1` row said "geographic `/IOSEL`" until 2026-09-06 (the mechanism — a
window strobe plus address-line match against a jumpered base — was right and became the
machine's; `machine.md` §2 cites this card as the one that never claimed the geography),
and matched `A2`–`A5` until 2026-09-08, when the widening removed `A6` from the strobe.
Replaced by: the present row, `/IOSEL` and `A2`–`A6`.

## §8 The straight-through-cable error (2026-09-04, IO-S4)

The connector section said the DE-9 male DTE wiring was "what a modem expects on the
other end of a straight-through cable — **and what a straight-through cable to a modern
USB-serial adapter expects**". The second half was wrong: a USB-serial adapter is also a
DTE, and two DTEs straight through hear nothing. Replaced by: §8's null-modem warning
(2↔3, 7↔8, 5 straight), with the crossover cable added to the bench kit in §9.

## §8 / §10.2 The unmaskable modem-status interrupt (2026-09-04, IO-S5)

Recorded at the review: a transition on `/DCD` or `/DSR` sets the 6551's
interrupt-pending bit with no `COMMAND` bit to mask it — free while they are strapped
low, live on every carrier drop once §8's second `MAX232` is fitted. The previous
revision's handler sketch checked `RDRF` and overrun only, and re-read `STATUS` for each
test — losing the error bits the first read consumed. Replaced by: §10.2's
read-once-and-save handler and its three rules.

## §12 step 0 — from "resolve the map" to "decide the tier"

Step 0 read "**Resolve `machine.md` §5 item 1 — the `$FF` map is full**"; that closed on
2026-09-08 (see the §7.1 entry) and the step was replaced by deciding §5.4's tier before
step 1 sources a part.

## §13 items — closed and renumber-shy leftovers

- Item 4 read "**The `$FF` map is full** — CLOSED 2026-09-08"; the surviving content is
  the seven-bit decode the GAL still owes, which is what the item now says.
- Item 10 read "**One port only** — §7.1 has no room for a second"; the widened window
  made a second port an ordinary option and the item now records that.
- Items 5 and 6 said Tier 1 "closes this item and item 6" / "closes items 5 and 7" —
  internally inconsistent item numbers. What Tier 1 actually closes is the sourcing trap
  (item 5) and the speed grade (item 9), which is what §9.1 and the README both say;
  fixed 2026-09-08 in this restructure to "items 5 and 9".
- Item 9 read "Closed outright by item 6's Tier 1" — but item 6 is an open decision, so
  the item now reads "moot if item 6 takes Tier 1".

## serial/README.md — archived narrations

- The block quoting the README's own earlier framing ("a period RS-232 port (~14 ICs)
  or a fast host link (~5)") — see the §(intro) entry.
- "This card closed the `$FF` map" — the closure/reopening/widening story, now this
  file's §7.1 entry; the README keeps only the present window and the `A0`–`A6` hazard.
- "`docs/serial.md` §8 used to say a straight-through cable to a modern USB-serial
  adapter was what the DE-9 expected" — see the §8 entry.


---

## 2026-09-09 — design-review2.md's corrections

### §0 — which design is the specified one

**Was:** *"⭐ The card as specified is 3 ICs and 19,200 baud. §4.5 and §5.4 argue it
should be 4 ICs and 115,200, on the strength of the widened address map. The 6551 design
is the specified one and the tiers are proposals with arithmetic — §13 items 6 and 7
hold the decision."*

**Why it moved:** §13 item 6 closed on 2026-09-09 and §9.1 took the `TL16C550C`, at
**3 ICs** rather than 4 — the "+1 IC" in that block was the counting error §9.1 records,
a baud crystal charged against a total that already had one. The same §0 table's own
rows already said the part had changed, so the block contradicted the table it sat under.

### §0 and `machine.md` §4.1 — the receive interrupt rate

**Was:** *"~1,030 interrupts/s receiving"* at 115,200 baud with a 14-byte FIFO trigger.

**Why it moved:** 115,200 baud 8N1 is 11,520 B/s, and 11,520 ÷ 14 is **823**. 1,030
implies 11.2 bytes per interrupt, which is not a trigger level the part offers. The
corrected figure strengthens §4.5's argument rather than weakening it.

### §2 — where the machine's system software comes from

**Was:** *"This machine boots NitrOS-9 from floppy."*

**Why it moved:** `machine.md` §7.2 decided the boot arrangement on 2026-09-08 — a 1 MB
ROM on the motherboard holding the boot monitor and a read-only ROM disk with the whole
NitrOS-9 distribution. **There is no floppy controller anywhere in this machine**, and
the sentence was inherited from the comparison with the Minimal 64x4 that surrounds it.

### §13 item 12 — `IRQB` open drain

**Was:** *"`IRQB` open drain is assumed, not read (§6, §12 step 1). The wire-OR onto a
line shared with three other cards depends on it. NMOS parts document it; the part
bought may not be one. One datasheet lookup, one diode if the answer is wrong."*

**Why it moved:** the item was a 6551 question and item 6 changed the part. §9.1 already
answers it for the `16C550` and the answer is **no** — `INTR` is active-high and
totem-pole, so the card's GAL inverts it through `machine.md` §5 item 9's open-drain
idiom. The item is closed with that answer rather than left as a lookup.
