# `hardware/`

**Board layouts, in [tscircuit](https://tscircuit.com).** Paths in this document are
relative to `hardware/`; paths in source comments are repository-root-relative, per the
convention at the bottom of the root [`README.md`](../README.md).

[`docs/machine.md`](../docs/machine.md) §6 lists **"Draw the motherboard"** as an open
item owned by the machine, with no document behind it. This directory is the first pass
at that, and at the five cards that plug into it.

**Status: schematic-level, and nothing is placed or routed.** Three things had to happen
before layout is meaningful. **The third is done** — every package pinout is now read off a
datasheet (open item 1, closed 2026-09-06, and it was not a formality: see finding 4). The
first is **started**: [`gal/`](gal/) holds the MMU GAL's equations, and fitting them found
four more defects in the board below. The video output stage (`design-review.md` §Vid-M4)
has not moved.

> **The MMU register map was signed off on 2026-09-06 and the board now implements the
> equations.** `machine.md` §5 item 3 is closed with it. `npm run check:netlist` asserts
> all five changes the equations forced — the dead nets are gone, `U3` takes `Q`, `/IOSEL`
> is on `U6`, the `'245`'s direction is `R/W`, and the `'157`'s select is no longer the
> write strobe. See [`gal/README.md`](gal/README.md). What exists
today is the **bus interface of every board, generated from one table**, so the
motherboard and a card cannot disagree about what A17 is.

---

## The two decisions this took

`docs/machine.md` §5 item 5 — *"Backplane or single board?"* — left the connector, the
slot count and the CPU module's siting open, and a pinout cannot be written without them.

| | Decision | Why |
|---|---|---|
| **Connector** | **72-pin 0.1" card edge, 2 × 36** | 44 signals + 2 audio returns need more than colormin's 50 pins. A 100 mm Eurocard edge at 0.1" pitch holds 39 positions; 36 leaves 8.6 mm for the notch and mechanical margin, so **the card format sizes the connector**. |
| **CPU siting** | **A 40-pin DIP socket on the motherboard** | The module is the drop-in board [`cpu/`](../cpu/) already builds for the CoCo 3, plugged in — **one hardware SKU serving both machines literally**, not by recompilation. Its own `'541`/`'245` level buffers ride with it (`plan.md` §2.6), so the motherboard adds no buffering. |

**Slot count is six, and that is a guess** — five specified cards plus one free. Nothing
in the machine documents has ever said how many. Six slots is 12 A of finger capacity
against a 2–3 A machine, so the supply and not the connector is the limit.

---

## The slot

[`lib/slot.ts`](lib/slot.ts) is the single source of truth. The motherboard's sockets and
every card's gold fingers are generated from it, and [`lib/slot.check.ts`](lib/slot.check.ts)
re-derives the claims `machine.md` §2 and `graphics.md` §17 make about it.

```
                    row A                              row B
  1   GND                                1   GND
  2   +5V                                2   +5V
  3   /RESET                             3   /IOSEL        (geographic)
  4   /HALT                              4   /IOPAGE
  5   /WAIT                              5   R/W
  6   KEY  ── polarising notch ──        6   KEY
  7   GND                                7   GND
  8-11  A0  A1  A2  A3                   8-11  D0 D1 D2 D3
  12  GND                                12  GND
  13-16 A4  A5  A6  A7                   13-16 D4 D5 D6 D7
  17  GND                                17  GND
  18-21 A8  A9  A10 A11                  18  E        19 GND
  22  GND                                20  Q        21 GND
  23-26 A12 A13 A14 A15                  22  CLK25    23 GND
  27  GND                                24  HSYNC    25 GND
  28-31 A16 A17 A18 A19                  26  VSYNC    27 GND
  32  GND                                28-30 /IRQ /FIRQ /NMI
  33  +5V                                31  GND
  34  SPARE                              32  AUDIO_L  33 AGND
  35  +5V                                34  AUDIO_R  35 AGND
  36  GND                                36  +5V
```

**44 signals, 5 × +5 V, 18 GND, 2 dedicated analogue returns, 1 key, 1 spare.**

Four properties are load-bearing, and each is checked rather than asserted:

- **A ground on both sides of every clock and sync line.** `graphics.md` §17 asks for
  ground returns adjacent to them; `E`, `Q`, `CLK25`, `HSYNC` and `VSYNC` occupy B18–B27
  alternating with grounds, which is what costs that block its density.
- **The analogue pair has its own returns.** `AUDIO_L`/`AUDIO_R` sit at the opposite end
  of row B from the clock group, each beside an `AGND` — `graphics.md` §17's "two pins and
  two grounds". Paula's channels are hard-panned and summing them to mono makes a module
  *wrong*, not quieter, so the pair is not negotiable either.
- **5 × +5 V.** The video card is the worst case at ~1.1–1.7 A, design to 2 A
  (`graphics.md` §14). At a conservative ~1 A per gold finger that is 5 A against 2 A.
- **Logical A13–A15 appear nowhere.** They are the map SRAM's address inputs and stay on
  the motherboard (`machine.md` §2). `lib/netlist.check.ts` proves they reach no slot.

**The spare at A34** sits between two +5 V pins, which makes it the natural home for a
future rail. The backplane carries **5 V only** — the storage card makes its own 3.3 V
behind an LDO (`sdcard.md` §7) and the CPU module regulates for itself.

---

## What is here

| | | |
|---|---|---|
| [`lib/slot.ts`](lib/slot.ts) | the 72-pin pinout, as data | + [`slot.check.ts`](lib/slot.check.ts) |
| [`lib/SlotConnector.tsx`](lib/SlotConnector.tsx) | `SlotSocket` (motherboard) and `CardEdge` (card), both from that table | |
| [`lib/parts.ts`](lib/parts.ts) | package pinouts | every one datasheet-verified, each naming its source |
| [`lib/Card.tsx`](lib/Card.tsx) | the 100 × 160 Eurocard scaffold every card uses | |
| [`cards/windows.ts`](cards/windows.ts) | the `$FF` map as data | + [`cards.check.ts`](lib/cards.check.ts) |
| [`mainboard/`](mainboard/) | the motherboard | + [`netlist.check.ts`](lib/netlist.check.ts) |
| [`cards/`](cards/) | audio, video, PS/2, serial, storage — bus interface each | |
| [`gal/`](gal/) | **the programmable logic** — U3's equations, in CUPL, Verilog and as an exhaustive check | + [`gal/mmu.check.ts`](gal/mmu.check.ts), [`gal/mmu_tb.sv`](gal/mmu_tb.sv) |
| [`vendor/mc6809/`](vendor/mc6809/) | **third-party** — Greg Miller's cycle-accurate MC6809E core, BSD, byte-identical to upstream | |

```sh
npm install          # bun comes with it; the tsci CLI needs it
npm run build        # all six boards -> dist/
npm run check        # the slot pinout and the $FF map, as arithmetic
npm run check:netlist  # the motherboard's connectivity claims (needs a build first)
npm run check:sim      # gal/mmu.v under Verilator
```

`npm run dev` opens tscircuit's viewer.

> The `tsci` CLI runs on **bun**, which is why it is a dev dependency here rather than
> something to install globally. `package.json` also pins `circuit-json` to `0.0.485`
> through an `overrides` entry: `@tscircuit/cli@0.1.2021` declares a peer range of
> `^0.0.464`, but its bundled code imports `schematic_sheet_size`, which that version does
> not export. Without the override every command fails at import.

---

## What the layout found

Drawing a board is a different check on a specification than reading it, and this pass
turned up three things. The first changes a parts list.

### 1. ⚠ `machine.md` §7.1's system RAM is one part, not four — and needs no decode

**Applied 2026-09-06.** `machine.md` §7.1 now says one package and no decode, and §0, §6
and §8 carry the corrected counts. What follows is the finding as it was made.

> **512 KB of SRAM on the motherboard, selected by `A19 = 0` qualified with `/IOPAGE`.**
> Four × 512K×8 (AS6C4008-class, 55 ns) and a decode.

**512K × 8 is 512 KB.** Four of them is 2 MB — against a 512 KB requirement, in a 1 MB
physical map that allots system RAM exactly `A19 = 0`, i.e. **A0–A18, nineteen address
lines**. An AS6C4008 has A0–A18. It *is* the requirement, once.

And "a decode" goes with the other three. With one part there is nothing to decode
between: `/CE` is the `A19 = 0 · /IOPAGE` term, which the MMU's `GAL22V10` already forms
to generate `/IOSEL`. The motherboard is drawn that way here — [`mainboard/mainboard.circuit.tsx`](mainboard/mainboard.circuit.tsx)
fits **U8 alone** — and `lib/netlist.check.ts` asserts both halves: one package, A0–A18,
and no sight of A19.

**This moves §8's motherboard line from ~13 ICs to 9**: MMU 5, divider GAL, oscillator,
reset supervisor, system RAM. The machine total moves with it, from ~110 to ~106.

It is the same shape of error the 2026-09-04 review found repeatedly: **a table that
exists to do arithmetic is worth re-examining against the parts catalogue** (§8's own
closing lesson). Unlike audio's 57, though, it was not found by re-reading the document —
it was found by a board file that had to say how many packages to draw.

### 2. `/IOSEL` cannot be geographic in this machine, and four documents assume it is

**Applied 2026-09-06.** `machine.md` §2 now owns the correction, and `graphics.md` §17,
`audio.md` §9.1 and `ps2.md` §3.2 defer to it. What follows is the finding as it was made.

> ⚠ **One correction to the finding itself:** it first named `sdcard.md` §6.1 as a
> repeater of the claim. It is not — that section only proposes a window. The documents
> carrying "per slot" were `machine.md` §2, `graphics.md` §17 (twice), `audio.md` §9.1 and
> `ps2.md` §3.2.

`graphics.md` §17 adopts colormin's slot model, where `/IOSEL` is **geographic** — slot
*n* gets the *n*th 64-byte window, decoded by position. `audio.md` §9.1 and `ps2.md` §3.2
both repeat "decode is geographic from the backplane's per-slot `/IOSEL`", and each adds
**"so the base is a jumper"**.

Those two sentences cannot both be true here. colormin's windows are *slot*-sized — four
identical 64-byte blocks. This machine's are *function*-sized and all different: audio 16
bytes, video 32, PS/2 4, serial 4, storage 4. A decode that assigns windows by position
would force each card into one specific slot, at which point a base-address jumper decodes
nothing.

The reading that works is the one `machine.md` §2 already implies when it derives
`/IOPAGE`: **`/IOSEL` is the `$FF40`–`$FF7F` window strobe**, common to every slot — the
`/IOPAGE` term further qualified by `A7,A6 = 01` — and each card completes its own decode
from A0–A5 against its jumpered base. That is why A0–A5 are on the backplane at all, and
it is what the boards here implement. **It was not, however, what any document said** —
except `serial.md` §6, whose decode GAL takes `CS0`/`/CS1` "from geographic `/IOSEL` *and
`A2`–`A5`*". That is the window-strobe model written down, in the one card document that
never claimed the geography.

The cost of the fix is recorded with it in `machine.md` §2: the geography is genuinely
lost, so nothing now prevents two cards being jumpered to the same base, and nothing
detects it.

### 3. Card-edge fingers fail a copper-to-edge DRC, correctly

Every card reports `SMT pad violates copper-to-board-edge clearance (measured 0.000mm)`.
That is the fingers doing their job — a card edge connector's copper reaches the edge by
definition. The rule wants an exemption, not the layout.

---

### 4. The one pinout that was wrong was the one nobody would check twice

**Found 2026-09-06,** when the datasheets open item 1 asked for were fetched from Digi-Key
and Mouser and the pinouts were read off them rather than recalled.

Four of the five parts were right as drawn — `74HC574`, `74HC245`, `74HC157` and the
`AS6C4008` matched their datasheets pin for pin, the 512K × 8's awkward 25–31 block
included. **The map SRAM did not.** `lib/parts.ts` had pins 21–23 as A9 / A8 / `/WE`; the
part is `/WE` / A9 / A8. The three were rotated, and the package was drawn 600-mil when the
`CY7C128A`'s DIP is the 300-mil skinny one.

That numbering is the **6116 standard** that every 2K × 8 in a 24-pin DIP shares, which is
the uncomfortable part: it is not an obscure part-selection subtlety, it is the pinout most
likely to be written from memory and least likely to be re-read. Nothing downstream caught
it, and nothing could have — `mainboard.circuit.tsx` connects by pin *name*, and
`netlist.check.ts` proves the netlist, so both were correct against a footprint that would
have shipped a board with three pins swapped. **A name-level check cannot see a
number-level error.** The pin numbers become load-bearing exactly once, at layout, which
had not happened yet.

`lib/parts.ts` now carries a `source` on every part naming the file and page, and
`UNVERIFIED_PARTS` is **derived from `provenance`** instead of hand-maintained — the
hand-written list had already gone stale once, still naming `SRAM_512K` as four packages
after finding 1 made it one.


## Open items

1. ~~**⚠ Three of the five motherboard part pinouts are unverified.**~~ **Closed
   2026-09-06.** The datasheets were fetched from Digi-Key and Mouser and every pinout is
   read off one — see finding 4 above for what that caught, and
   [`reference/datasheets/README.md`](../reference/datasheets/README.md) for the files and
   what cites each. **One part on the wanted list has no datasheet and will not get one:**
   the serial card's `R6551A`/`G65SC51` is out of production at both distributors, so
   `serial.md` §3.4's speed-grade argument still rests on recalled figures. The `W65C51N`
   sheet is there for the DIP-28 pinout and for nothing else.

2. **The slot socket footprint is a DIP body.** Pad grid and pin numbering are right, the
   outline is not. It needs a measured footprint once a receptacle is sourced.
3. **Nothing is placed.** Every board's components sit at the origin, so the PCB DRC
   reports overlaps that mean nothing yet — **299 plated-hole clearance errors on the
   motherboard alone**, a count unchanged by the pinout fix, which is how that fix was
   checked for side effects. It becomes a real number the moment placement starts and not
   before. Placement waits on open item 2 and on the GAL fitting `graphics.md` §18 step 0
   requires.
4. ~~**⚠ The system RAM's control lines are not driven.**~~ **Closed 2026-09-06.**
   `RAM_CE`, `RAM_OE` and `RAM_WE` reached `U8` and nothing else, behind a comment
   claiming U3 formed the term — U3 forms no such term, and once
   [`gal/mmu.pld`](gal/mmu.pld) existed that stopped being arguable. U3 could not take
   them either: one free pin, and `/CE` alone needs two. They are on **U6** now
   ([`gal/clkdec.pld`](gal/clkdec.pld)), with `/OE` qualified by `R/W` rather than tied
   low — which removes ~90 ns of SRAM-versus-CPU contention on every write.
   `check:netlist` asserts all three run from U6 to U8.

5. **Six slots is unargued.** See above.
6. **Decoupling is not drawn.** One 0.1 µF per package plus bulk, everywhere; it is
   mechanical and belongs with placement.
7. **`machine.md` §5 item 1 is still the machine's blocking decision.** Four bytes of the
   `$FF` map remain (`npm run check` prints the figure). The `$FF40`–`$FF7F` decode is one
   GAL term in [`mainboard/mainboard.circuit.tsx`](mainboard/mainboard.circuit.tsx) today
   and a board respin after the backplane is etched.

---

## Conventions

- **`lib/slot.ts` is the only place a pin number and a signal name appear together.** A
  board that hardcodes one has a bug.
- **Every claim a check can make, a check makes.** `npm run check` is arithmetic out of
  the machine documents, not style.
- **Superseded and unverified material is marked, not deleted** — the root `README.md`
  convention, applied here to the map SRAM's wrong pinout and to §7.1's four SRAMs.
