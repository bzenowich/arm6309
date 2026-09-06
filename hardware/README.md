# `hardware/`

**Board layouts, in [tscircuit](https://tscircuit.com).** Paths in this document are
relative to `hardware/`; paths in source comments are repository-root-relative, per the
convention at the bottom of the root [`README.md`](../README.md).

[`docs/machine.md`](../docs/machine.md) §6 lists **"Draw the motherboard"** as an open
item owned by the machine, with no document behind it. This directory is the first pass
at that, and at the five cards that plug into it.

**Status: schematic-level, and nothing is placed or routed.** Three things have to happen
before layout is meaningful, and none of them has: the GALs must be fitted
(`graphics.md` §18 step 0), the video output stage must be specified
(`design-review.md` §Vid-M4), and the package pinouts below need datasheets. What exists
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
| [`lib/parts.ts`](lib/parts.ts) | package pinouts | ⚠ mostly unverified — open item 1 |
| [`lib/Card.tsx`](lib/Card.tsx) | the 100 × 160 Eurocard scaffold every card uses | |
| [`cards/windows.ts`](cards/windows.ts) | the `$FF` map as data | + [`cards.check.ts`](lib/cards.check.ts) |
| [`mainboard/`](mainboard/) | the motherboard | + [`netlist.check.ts`](lib/netlist.check.ts) |
| [`cards/`](cards/) | audio, video, PS/2, serial, storage — bus interface each | |

```sh
npm install          # bun comes with it; the tsci CLI needs it
npm run build        # all six boards -> dist/
npm run check        # the slot pinout and the $FF map, as arithmetic
npm run check:netlist  # the motherboard's connectivity claims (needs a build first)
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

## Open items

1. **⚠ Three of the five motherboard part pinouts are unverified.** `lib/parts.ts` marks
   each one. Only the CPU socket is confirmed — `plan.md` §2.6 reads it off the *Color
   Computer 3 Service Manual* and §2.6.1 corroborates it against the Dragon 64 schematic.
   The rest were written from familiarity, and **no datasheet in
   [`reference/datasheets/`](../reference/datasheets/) covers any of them.** Wanted there:
   a 2K×8 15 ns SRAM, `AS6C4008`, `74HC245`, `74HC157`, `74HC273`, `74HC244`, `74HC595`,
   `74HC193`, `GAL22V10`, `R6551A`/`G65SC51`, `74LVC125`. This project puts a measurement
   in place of an estimate; these are estimates and are marked as such.
2. **The slot socket footprint is a DIP body.** Pad grid and pin numbering are right, the
   outline is not. It needs a measured footprint once a receptacle is sourced.
3. **Nothing is placed.** Every board's components sit at the origin, so the PCB DRC
   reports overlaps that mean nothing yet. Placement waits on open items 1 and 2, and on
   the GAL fitting `graphics.md` §18 step 0 requires.
4. **Six slots is unargued.** See above.
5. **Decoupling is not drawn.** One 0.1 µF per package plus bulk, everywhere; it is
   mechanical and belongs with placement.
6. **`machine.md` §5 item 1 is still the machine's blocking decision.** Four bytes of the
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
  convention, applied here to the pinouts and to §7.1's four SRAMs.
