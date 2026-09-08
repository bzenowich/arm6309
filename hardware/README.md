# `hardware/`

**Board layouts, in [tscircuit](https://tscircuit.com).** Paths in this document are
relative to `hardware/`; paths in source comments are repository-root-relative, per the
convention at the bottom of the root [`README.md`](../README.md).

[`docs/machine.md`](../docs/machine.md) §6 lists **"Draw the motherboard"** as an open
item owned by the machine, with no document behind it. This directory is the first pass
at that, and at the five cards that plug into it.

> Superseded material is archived in [history.md](history.md); this document describes
> only the present design.

**Status: schematic-level, and nothing is placed or routed.** Three things gate layout.
Every package pinout is read off a datasheet — open item 1, and it was not a formality:
see history.md's finding 4. [`gal/`](gal/) holds the motherboard GALs' equations, fitted
as `.jed` files checked at the fuse level — fitting them found four defects in the board
below (history.md). The video output stage (`design-review.md` §Vid-M4) has not moved.

> **The MMU register map is signed off (2026-09-06) and the board implements the
> equations.** `machine.md` §5 item 3 is closed with it. `npm run check:netlist` asserts
> the five properties the equations force — no dead nets, `U3` takes `Q`, `/IOSEL`
> is on `U6`, the `'245`'s direction is `R/W`, and the `'157`'s select is not the
> write strobe. See [`gal/README.md`](gal/README.md). What exists
today is the **bus interface of every board, generated from one table**, so the
motherboard and a card cannot disagree about what A17 is.

---

## The two decisions this took

`docs/machine.md` §5 item 5 — *"Backplane or single board?"* — left the connector, the
slot count and the CPU module's siting open, and a pinout cannot be written without them.

| | Decision | Why |
|---|---|---|
| **Connector** | **72-pin 0.1" card edge, 2 × 36** | 45 signals + 2 audio returns need more than colormin's 50 pins. A 100 mm Eurocard edge at 0.1" pitch holds 39 positions; 36 leaves 8.6 mm for the notch and mechanical margin, so **the card format sizes the connector**. ⚠ **That premise expired on 2026-09-08** — see below. |
| **Card format** | **100 mm high × 120, 180 or 240 mm long** — Apple II proportions, per card | [`place/`](place/) drew the boards: the video card does not fit a 100 × 160 mm Eurocard (134.4 cm² of courtyard against 133.4 cm² of placeable area), and three of the five cards fit 12 cm — so the length is per-card and `place.check.ts` asserts each takes the shortest that works. |
| **CPU siting** | **A 40-pin DIP socket on the motherboard** | The module is the drop-in board [`cpu/`](../cpu/) already builds for the CoCo 3, plugged in — **one hardware SKU serving both machines literally**, not by recompilation. Its own `'541`/`'245` level buffers ride with it (`plan.md` §2.6), so the motherboard adds no buffering. |

**Slot count is six, and that is a guess** — five specified cards (PS/2 and serial share
one I/O card, merged 2026-09-08) plus one spare. Nothing in the machine documents has
ever said how many. Six slots is 12 A of finger capacity against a 2–3 A machine, so the
supply and not the connector is the limit.

> ⚠ **A 240 mm edge holds 98 positions at 0.1", not 39, so the connector's own
> justification no longer binds.** The 72-pin decision was derived from the Eurocard —
> *"the card format sizes the connector"* — and the format changed. Three things that
> were foreclosed by having exactly one spare pin come back into scope: the DMA
> request/grant pair `net/docs/net.md` §13.1 wanted, a future rail, and the spare that
> physical `A20` spent. **The connector is not re-specified**; this is a note that it
> could be, and `machine.md` §5 item 5 is where it would be decided.

---

## The slot

[`lib/slot.ts`](lib/slot.ts) is the single source of truth. The motherboard's sockets and
every card's gold fingers are generated from it, and [`lib/slot.check.ts`](lib/slot.check.ts)
re-derives the claims `machine.md` §2 and `graphics.md` §17 make about it.

```
                    row A                              row B
  1   GND                                1   GND
  2   +5V                                2   +5V
  3   /RESET                             3   /IOSEL   ($FF00-$FF7F)
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
  34  A20                                32  AUDIO_L  33 AGND
  35  +5V                                34  AUDIO_R  35 AGND
  36  GND                                36  +5V
```

**45 signals, 5 × +5 V, 18 GND, 2 dedicated analogue returns, 1 key, and no spare.**

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

> ⚠ **A34 is physical `A20`** — `machine.md` §5 item 1 option D (2026-09-08), doubling
> the physical map to 2 MB. The reason that use of the pin won is that it needs
> **nothing else**: the map SRAM is byte-wide, its eighth bit was already stored and read
> back through the isolation `'245`, and it drove nothing. One trace, no ICs, 1 MB.
>
> **There is no spare position.** `net/docs/net.md` §13.1's DMA request/grant pair lost
> to `A20` the same day; a seventh signal would come out of the ground or power
> allocation, and `lib/slot.check.ts` is what prices that.

The backplane carries **5 V only** — the storage card makes its own 3.3 V behind an LDO
(`sdcard.md` §7) and the CPU module regulates for itself.

---

## What is here

| | | |
|---|---|---|
| [`lib/slot.ts`](lib/slot.ts) | the 72-pin pinout, as data | + [`slot.check.ts`](lib/slot.check.ts) |
| [`lib/SlotConnector.tsx`](lib/SlotConnector.tsx) | `SlotSocket` (motherboard) and `CardEdge` (card), both from that table | |
| [`lib/parts.ts`](lib/parts.ts) | package pinouts | every one datasheet-verified, each naming its source |
| [`lib/Card.tsx`](lib/Card.tsx) | the card scaffold — 100 mm high, length per card | + [`place/`](place/) |
| [`cards/windows.ts`](cards/windows.ts) | the `$FF` map as data | + [`cards.check.ts`](lib/cards.check.ts) |
| [`mainboard/`](mainboard/) | the motherboard | + [`netlist.check.ts`](lib/netlist.check.ts) |
| [`cards/`](cards/) | audio, video, **io** (PS/2 + serial, merged 2026-09-08), storage, net — bus interface each | |
| [`ram.md`](ram.md) | **the memory system — decided 2026-09-08**: 16-bit map entries, a 32 MB physical map, four 30-pin SIMM sockets of DRAM and no SRAM at all. The address path costs one SRAM because the MMU was built with 128× the map storage it uses; the rest of the document is a staged brainstorm | |
| [`place/`](place/) | **the placement study** — every board drawn 1 : 1 from its parts list, and the check that found the video card did not fit a Eurocard | + [`place/place.check.ts`](place/place.check.ts) |
| [`gal/`](gal/) | **the programmable logic** — U3 and U6's equations in CUPL and Verilog, and [`gal/jedec/`](gal/jedec/), which assembles them into the fuse maps a programmer burns | + [`gal/mmu.check.ts`](gal/mmu.check.ts), [`gal/mmu_tb.sv`](gal/mmu_tb.sv), [`gal/jedec.check.ts`](gal/jedec.check.ts) |
| [`vendor/mc6809/`](vendor/mc6809/) | **third-party** — Greg Miller's cycle-accurate MC6809E core, BSD, byte-identical to upstream | |

```sh
npm install          # bun comes with it; the tsci CLI needs it
npm run build        # all six boards -> dist/
npm run check:place  # every card places on the length it declares
npm run render:boards # the drawings -> dist/boards.html
npm run check        # the slot pinout and the $FF map, as arithmetic
npm run check:netlist  # the motherboard's connectivity claims (needs a build first)
npm run check:sim      # gal/mmu.v and gal/clkdec.v under Verilator
npm run check:jedec    # assembles both GALs and checks the fuse maps
```

`npm run dev` opens tscircuit's viewer.

> The `tsci` CLI runs on **bun**, which is why it is a dev dependency here rather than
> something to install globally. `package.json` also pins `circuit-json` to `0.0.485`
> through an `overrides` entry: `@tscircuit/cli@0.1.2021` declares a peer range of
> `^0.0.464`, but its bundled code imports `schematic_sheet_size`, which that version does
> not export. Without the override every command fails at import.

---

## What the layout found

Drawing a board is a different check on a specification than reading it. Two of this
pass's findings are applied — their record is in [history.md](history.md) — and one is a
live DRC caveat.

### 1. `machine.md` §7.1's system RAM is one part, not four (applied 2026-09-06; see history.md)

**One `AS6C4008` is the whole 512 KB requirement, and with one part there is nothing to
decode**: `/CE` is the `A19 = 0 · /IOPAGE` term. [`mainboard/mainboard.circuit.tsx`](mainboard/mainboard.circuit.tsx)
fits **U8 alone**, and `lib/netlist.check.ts` asserts both halves: one package, A0–A18,
and no sight of A19. ([`ram.md`](ram.md) §6.2 has since removed the DIP SRAM from the
decided design entirely; the board file still draws today's 9-IC state.)

### 2. `/IOSEL` is the `$FF00`–`$FF7F` window strobe, not geographic (applied 2026-09-06; see history.md)

**`/IOSEL` is common to every slot** — the `/IOPAGE` term further qualified by
**`A7 = 0`** — and each card completes its own decode from **A0–A6** against its
jumpered base. That is why the low address lines are on the backplane at all, and it is
what the boards here implement. colormin's geographic per-slot model cannot work here:
this machine's windows are *function*-sized and all different, so a positional decode
would pin each card to one slot and make a base-address jumper meaningless.

The cost is recorded in `machine.md` §2: the geography is genuinely lost, so nothing
prevents two cards being jumpered to the same base, and nothing detects it.

### 3. Card-edge fingers fail a copper-to-edge DRC, correctly

Every card reports `SMT pad violates copper-to-board-edge clearance (measured 0.000mm)`.
That is the fingers doing their job — a card edge connector's copper reaches the edge by
definition. The rule wants an exemption, not the layout.

---

### 4. The one pinout that was wrong was the one nobody would check twice (found and fixed 2026-09-06; see history.md)

The map SRAM's pins 21–23 were rotated against the `CY7C128A` datasheet, and the package
was drawn 600-mil where the part is the 300-mil skinny DIP — a name-level netlist check
cannot see a number-level footprint error, so only reading the datasheet caught it. The
full account, and why the 6116-standard pinout is exactly the one that gets written from
memory, is in history.md.

`lib/parts.ts` carries a `source` on every part naming the datasheet file and page, and
`UNVERIFIED_PARTS` is **derived from `provenance`** rather than hand-maintained.


## Open items

1. **Closed 2026-09-06** — every motherboard pinout is read off a datasheet: see finding
   4 for what that caught, and
   [`reference/datasheets/README.md`](../reference/datasheets/README.md) for the files and
   what cites each. **One part on the wanted list has no datasheet and will not get one:**
   the I/O card's `R6551A`/`G65SC51` is out of production at both distributors, so
   `serial.md` §3.4's speed-grade argument rests on recalled figures. The `W65C51N`
   sheet is there for the DIP-28 pinout and for nothing else.

2. **The slot socket footprint is a DIP body.** Pad grid and pin numbering are right, the
   outline is not. It needs a measured footprint once a receptacle is sourced.
3. **Nothing is placed.** Every board's components sit at the origin, so the PCB DRC
   reports overlaps that mean nothing yet — **299 plated-hole clearance errors on the
   motherboard alone**. It becomes a real number the moment placement starts and not
   before. Placement waits on open item 2 and on the GAL fitting `graphics.md` §18 step 0
   requires — the motherboard's two parts are fitted ([`gal/jedec/`](gal/jedec/)), and so
   are the video card's two CPLDs and its `rfa` GAL ([`gal/cpld/`](gal/cpld/),
   `gal/rfa.jed`).
4. **Closed 2026-09-06** — the system RAM's control lines are driven: `RAM_CE`, `RAM_OE`
   and `RAM_WE` come from **U6** ([`gal/clkdec.pld`](gal/clkdec.pld)), with `/OE`
   qualified by `R/W` rather than tied low — which removes ~90 ns of SRAM-versus-CPU
   contention on every write. `check:netlist` asserts all three run from U6 to U8. (The
   defect this closed is archived in history.md.)

5. **Six slots is unargued.** See above.
6. **Decoupling is not drawn.** One 0.1 µF per package plus bulk, everywhere; it is
   mechanical and belongs with placement.
7. **CLOSED 2026-09-08** — `machine.md` §5 item 1 is decided: the window is
   `$FF00`–`$FF7F`, 64 bytes of it free (`npm run check` prints the figure), and the
   physical map is 2 MB — options A and D. The widening was one literal *removed* from
   [`gal/clkdec.pld`](gal/clkdec.pld), taken while the backplane is still a table.

---

## Conventions

- **`lib/slot.ts` is the only place a pin number and a signal name appear together.** A
  board that hardcodes one has a bug.
- **Every claim a check can make, a check makes.** `npm run check` is arithmetic out of
  the machine documents, not style.
- **Superseded material is archived, not lost** — it moves to [`history.md`](history.md),
  one archive for the whole `hardware/` area. Unverified material is still marked in
  place.
