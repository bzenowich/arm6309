# PS/2 — archived history

Everything here is superseded. [`ps2.md`](ps2.md) describes the present design; this file
records what earlier revisions of it said, what the 2026-09-04 design review
([`docs/design-review.md`](../../../docs/design-review.md) §5, findings IO-P1…P8) found,
and what replaced each claim. Entries are ordered by the spec section they came from.

## §0 / §9 IC count — the chain: 16 → 9 → 11

- **16** — the first revision, which assumed no interrupt line was available, polled from
  the VBL tick, and paid for the assumption with a 16-byte `CD40105B` FIFO per port
  (four of the sixteen packages).
- **9** — after reading the Minimal 64x4: the FIFO deleted (with `/IRQ` there is nothing
  to queue), the receiver rebuilt on Slu4's `'595` + `'193` topology.
- **11** — after the 2026-09-04 design review (IO-P1): a `74HC574` second-stage latch per
  port, because the `'595`'s storage register turned out not to be a byte of buffering
  (see the §5 entry below). Every "nine packages" comparison in the document was restated
  against 11; the FIFO fallback stays at 13 because the FIFO subsumes the latch.

Replaced by: `ps2.md` §9's flat count of 11, confirmed by `hardware/place/parts.ts`
(the merged I/O card is 14 = 11 + serial's 3).

## §3.1 Interrupts — the first revision polled from VBL instead

Archived text:

> **The earlier revision of this document polled from the VBL tick instead**, to avoid
> touching the interrupt structure at all. That was the wrong trade: it cost a 16-byte
> FIFO per port — **four of sixteen packages** — to save an interrupt on a line that
> already had two sources. Reading the Minimal 64x4 is what made that visible.

The same pattern is called out against Burrell Smith's story in §4.4(a) — "hardware is
what you build when you do not believe the CPU will be there in time"; the first revision
made the Apple II division's mistake, at the same four-package price, 45 years apart.
Replaced by: `/IRQ` as a shared open-drain source, with polling kept only as a bring-up
fallback (`ps2.md` §3.1).

## §3.1 Mouse rate in the budget — 40 /s, twice replaced (2026-09-04)

The interrupt budget was first computed at a different rate, then at 40 /s justified as
"just under the frame rate". Per the design review (IO-P5): 40 /s was chosen from a menu
that omitted 60, but 60 /s is a standard PS/2 rate and 70.09 Hz is the frame rate, so the
criterion's own answer was 60 all along. See the §5.2 entry. Replaced by: 60 /s in the
budget (240 interrupts/s combined, 1.1 %/4.6 %), with 40 /s kept as the documented
fallback.

## §3.1 The GIME-compatible interrupt block claim

The spec quoted `graphics.md` §12's interrupt-source block as one "NitrOS-9's CoCo 3 IRQ
code already talks to". `machine.md` §4.1 (decided 2026-09-04, Sys-M3) found that claim
"wrong on its own terms" — nothing in this machine decodes `$FF92`/`$FF93` — and replaced
it with an explicit polled dispatch order. Replaced by: a plain statement that `/IRQ` is
open-drain with multiple sources and `machine.md` §4.1 owns the order.

## §3.1 / §8 Chain position — "second" until the net card joined (2026-09-07)

The document placed this card **second** in the `/IRQ` polling chain — video `VSTAT`,
then `IOSTAT`, then serial `STATUS` last. `machine.md` §4.1 was amended 2026-09-07 when
the net card joined as a fifth source: net polls second because its status read is
side-effect-free and it is the most frequent source after VBL. Replaced by: the order
**video → net → PS/2 → serial**, with this card mid-chain; its reasoning (a
side-effect-free `IOSTAT` may sit anywhere; serial's destructive `STATUS` must be last)
is unchanged.

## §3.2 Address decode — three superseded framings

1. **"Geographic from the backplane's per-slot `/IOSEL`" (until 2026-09-06).** A
   per-slot decode fixes each card's window by position and leaves the base-address
   jumper in the same sentence nothing to select. Corrected: `/IOSEL` is the I/O window
   strobe, common to every slot, and the card matches address bits against a jumpered
   base. `machine.md` §2 owns the correction.
2. **`A0`–`A5` (until 2026-09-08).** The geographic window widened from `$FF40`–`$FF7F`
   to `$FF00`–`$FF7F` (`machine.md` §5 item 1, closed 2026-09-08) and `A6` left the
   strobe — a six-bit match answers at `$FF50` *and* `$FF10`. Replaced by: the card
   decodes `A0`–`A6`.
3. **"A quarter of the disk controller's window, not half."** The section title and body
   argued the four-byte claim against a `$FF50`–`$FF5F` disk-controller reservation — the
   previous revision had wanted half of it, and four bytes left "twelve bytes for the
   disk controller". The reservation no longer exists: storage took `$FF58`–`$FF5B`
   (returning the rest), net took `$FF5C`–`$FF5F` on 2026-09-07, and the window widened.
   Replaced by: the present map in `ps2.md` §3.2 / `hardware/cards/windows.ts`.

Also archived from §3.2 — resolved, not wrong here:

> ⚠ **Four, not five.** `machine.md` §3's parallel sentence says "five registers plus a
> latch"; the WD1773 has four (`COMMAND`/`STATUS`, `TRACK`, `SECTOR`, `DATA`) plus the
> drive-select/side/density latch that every CoCo-style controller board adds beside it.
> The figure in this section is the correct one; `machine.md` is the document to fix.

`machine.md` was fixed on 2026-09-04 and now says four registers plus a latch.

## §3.2 The board merge (2026-09-08)

The PS/2 and serial cards merged onto one board — `hardware/cards/io.circuit.tsx`, 14 ICs
on a 12 cm card, one eight-byte decode at `$FF50`–`$FF57` — because the two windows are
contiguous and the machine gets a slot back. Recorded here as a dated event; the fact
itself stays in the spec because it is the present design. Nothing about this card's
logic, its 11 packages or its interrupt behaviour changed with the merge.

## §5 Buffering — the central claim, overturned (2026-09-04, IO-P1)

**The claim below was this card's central engineering argument, and it is false:**

> **The `'595`'s storage register holds one byte while the next frame shifts in.** That
> buys one full frame time — **660 µs at the slowest clock rate** — to service the port.
> The only question is whether the CPU can be there inside 660 µs.
>
> - **With `/IRQ` (§3.1): trivially yes.** Interrupt latency on a 6309 is
>   instruction-time plus dispatch, three orders of magnitude inside the window.
>   **No FIFO. No packages.**

Two errors. The small one: 660 µs is 11 × 60 µs, the *fastest* PS/2 clock rate
(16.7 kHz); the slowest (10 kHz) gives 1.1 ms — the label was inverted. The large one:
`RCLK` is `Q0` of the `'193`, which toggles on every clock edge of every frame, so edge 1
of frame N+1 — its start bit — re-copies the shift register into storage and destroys
byte N. The real service deadline was never the frame time but the unspecified inter-byte
gap, which inside a 3-byte mouse packet can be a few hundred µs against a 191 µs dispatch
guess, with no parity or framing check to make the resulting torn byte detectable.

Found in the 2026-09-04 design review, `docs/design-review.md` §5 IO-P1. Replaced by:
`ps2.md` §5's present-tense analysis and §5.1's `74HC574` second-stage latch per port
(+2 ICs, 9 → 11), which makes the buffer genuinely one frame deep.

## §5.2 Mouse sample rate — 40 /s → 60 /s (2026-09-04, IO-P5)

Archived text:

> ⚠ **The previous revision specified 40 /s and justified it as "just under the frame
> rate".** It is not — 60 is, and 80 is the first rate above it. Corrected per the
> 2026-09-04 design review (IO-P5). The `F3` argument changes from `$28` to `$3C`
> (§11.2 step 3, §13 step 5).

Replaced by: 60 /s specified (`F3` then `$3C`), 40 /s kept as the cheap fallback if §13
step 8 measures a dispatch cost worse than 400 cycles.

## §5.3 The FIFO fallback's 13 — the earlier revision's number, re-derived

The 13-IC figure for the polled fallback is "exactly the number the earlier revision
quoted, arrived at for a different reason": the first revision's 13 was 9 + 4 FIFO
packages; the present 13 is 11 − 2 + 4, because the `CD40105B` subsumes §5.1's
second-stage latch. Replaced by: the plain arithmetic 11 − 2 + 4 = 13 in `ps2.md` §5.3.

## §6.1 The `'193` was never loaded (2026-09-04, IO-P2)

Archived text:

> ⚠ **The `'193` was never loaded in the previous revision.** It said the counter idles
> "preloaded" without saying with what or by what mechanism, §4.3's datapath drew no
> connection to `/PL` or the preset inputs, and §8.2 specified `KRST`/`MRST` as holding
> the counter "in reset" — but a 74HC193's `MR` forces **0000**, not the preload. A
> down-counter released at 0000 borrows on its very first clock edge, sets `DR` with
> garbage, and every following frame is misaligned by one. Corrected per the 2026-09-04
> design review (IO-P2).

Replaced by: preset strapped to 1010 = 10, `MR` tied low, `~TCD` fed back to `/PL`
through the GAL, and `KRST`/`MRST` asserting `/PL` — `ps2.md` §4.3 items 1–2, §6.1.
§13 step 2's breadboard falsifies the value 10 if it is wrong.

## §7 Transmit walkthrough — written in true-line polarity (2026-09-04, IO-P6)

Steps 3–5 of the software-transmit walkthrough previously read in true-line polarity —
"poll `KCLK` for a falling edge", "`KDAT` low" — which is correct about the wire and
wrong about the register: the `'HCT132` conditioning gates invert, all four are consumed,
and a driver written from the old text inverts every poll. Replaced by: the walkthrough
rewritten in register polarity, with §8.1 stating the polarity once, normatively.

## §7.1 The masked-transmit window — unrecorded before the review (IO-P4)

The previous revision's only concurrency rule was "a transmit must not happen inside an
interrupt handler". The converse — a task-level transmit with interrupts enabled is
corrupted *by* interrupt handlers, so the per-bit loop must run with `/IRQ` masked for
0.8–1.3 ms — and its interaction with `serial.md` §5.1 (a guaranteed serial overrun per
LED update at 19,200 baud) were recorded in neither document before the 2026-09-04
design review (IO-P4). Replaced by: `ps2.md` §7.1 in full, with the mitigation table and
§14 item 9 assigning the choice to the owner.

## §8.1 `IOSTAT` bits 2–5 — described backwards (2026-09-04, IO-P6)

The previous revision described bits 2–5 as "line state" and called idle-high "a crude
presence check" — both read backwards at the register, since the `'HCT132` gates invert
and a line at rest reads 0. It also overstated the presence check: the pull-ups read the
same with the connector empty. Replaced by: §8.1's normative inverted-polarity block and
the honest presence statement (only an `FF` returning `AA` proves a device).

## §8.2 `IOCTRL` — specified as a `'574` before the reset fix

The previous revision specified `IOCTRL` as a `74HC574` with `OE` tied active. The swap
to a `74HC273` (asynchronous `/MR` on backplane `/RESET`) was free — same package, same
pin count, same price — and §8.4 is why it is mandatory. Replaced by: the `'273`,
stated flatly in §8.2/§9.

## §8.4 Reset — `/RESET` reached no IC on the card (2026-09-04, IO-P3)

Archived text:

> The previous revision of this document had **`/RESET` as an input to no IC on the
> card**. The serial card gets this right (`serial.md` §6 wires backplane `/RESET`
> straight to the 6551's `/RES`); this one did not, and the consequences are not
> cosmetic.

The consequences (now stated conditionally in the spec): the card could power up holding
a port's `CLK` low (the PS/2 inhibit condition), with `IRQEN` stuck 1 and a `DR` latch
stuck set — an interrupt storm at boot on the line the system tick uses, before any
driver that could clear it is loaded. Replaced by: §8.4's two `/RESET` connections
(the `'273`'s `/MR`, and a GAL clear term on both `DR` latches).

## §9 GAL margin — "3 macrocells for decode" before the `/PL` terms moved in

The fitting arithmetic previously left 3 macrocells for the decode terms; §6.1's two
`/PL` feedback terms moved into the same package and the margin is now 1. The escape
(one `74HC74` for both `DR` latches, card = 12) is unchanged. Recorded as IO-P8's
follow-on; replaced by: §9's present arithmetic (9 of 10 macrocells spoken for).

## §10 PIA0 emulation — the cost comparison at 16 packages

When the card was 16 packages, the ~7-package PIA0-matrix emulator was a 44 % increase;
against 11 it is 64 %. Replaced by: the 64 % figure alone.

## §11.1 `Pause` — "seven bytes" (2026-09-04, IO-P7)

The make sequence was given as seven bytes. It is eight: `E1 14 77 E1 F0 14 F0 77`.
Replaced by: the eight-byte sequence, spelled out for whoever writes the state machine.

## §13 step 4 — "the card becomes 10 with a `'74`"

The exit criterion for the GAL-fitting step still said the fallback card was **10** — a
leftover from the 9-IC count (9 + 1). Fixed 2026-09-08 in this restructure to **12**
(11 + 1), matching §9. The step's term list also gained the two `/PL` terms §9 counts.

## io/README.md — the `$FF` map chain and the 9 → 11 warning block

The parent README carried the map's full strikethrough chain — "there is no free `$FF`
window" → "the map has four bytes left" → "the map is full" → "`$FF00`–`$FF7F`, 64 bytes
free" — and a warning block retelling the §5/IO-P1 story ("The PS/2 card was 9 ICs until
the 2026-09-04 design review… 9 → 11"). Both replaced by present-tense statements; the
9 → 11 story lives in this file's §5 entry.

## ps2/README.md — archived narrations

- "reading its schematic cut this card from 16 ICs to 9" — the count chain is this
  file's first entry.
- The bullet crediting the `'595` storage register with "one byte of buffering at zero
  cost", struck through and refuted in place — see the §5 entry.
- The block "The buffering was not free, and the card is 11, not 9", retelling IO-P1
  and its three free companion corrections (the `'193` loaded, the `'273` reset, the
  masked transmit) — see the §5, §6.1, §8.4 and §7.1 entries.
- "(The card asked for 40 /s until the design review pointed out that 60 is a standard
  rate and 40 was chosen from a menu that omitted it.)" — see the §5.2 entry.
- "which is the part the first three revisions left out" (of the masked transmit) — see
  the §7.1 entry.
