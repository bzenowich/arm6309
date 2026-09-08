# Serial — archived history

Everything here is superseded. [`serial.md`](serial.md) describes the present design;
this file records what earlier revisions of it said, what the 2026-09-04 design review
([`docs/design-review.md`](../../../docs/design-review.md) §6, findings IO-S1…S7) found,
the `$FF`-map narrative this card sat in the middle of, and what replaced each claim.
Entries are ordered by the spec section they came from.

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
