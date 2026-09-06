# The Machine

## What Is Frozen, What Is Merely Proposed, and What Nobody Has Decided

**Question this answers:** the project now has three card specifications
([`cpu/docs/plan.md`](../cpu/docs/plan.md),
[`video/docs/graphics.md`](../video/docs/graphics.md),
[`audio/docs/audio.md`](../audio/docs/audio.md)) and each of them has, as **step 0 of its
own build order**, "freeze the machine spec". None of them can do that, because the
machine spec is the thing that spans them. This document is where that lives.

**Status: assembled, not frozen.** Everything in §§1–4 is copied from a card document
that already committed to it, with the citation. §5 is the list of things that are
genuinely undecided.

> **This document does not get to invent anything.** Where a card spec says "propose"
> rather than "take", it is recorded here as a proposal. Where two documents disagree,
> the disagreement is recorded rather than resolved.
>
> ⚠ **Amended 2026-09-04 by [`docs/design-review.md`](design-review.md).** That rule
> held while this document was only a collation. The review found things no card
> document could have found from inside itself — chief among them that **the machine
> as specified could not execute its first instruction** — and a collation cannot fix
> those by citing somebody. So this revision *does* decide, in four places: the boot
> and vector story (§7), the `/IOPAGE` inhibit (§2), system RAM (§7.1), and the E rate
> (§1). Each is written as a decision, with its rationale and the alternative it beat,
> and each is marked. Everything else in this document still only reports.

---

## 0. The machine in one table

| | |
|---|---|
| **CPU** | HD6309E in native mode, synthesised on an **STM32G431CBU6** ([`cpu/`](../cpu/)) — UFQFPN48, not the LQFP48 this table named until 2026-09-04 (§5 item 6) |
| **Boot** | **the CPU module serves an ~8 KB shadow ROM and the vector page from its own flash** — §7.2. No ROM chip on the motherboard |
| **MMU** | **on the motherboard: 5 ICs, the SAM/GIME/DAT arrangement** — `graphics.md` §6.3.1. Register set is a free design, not GIME-compatible (§5 item 3) |
| **Address space** | 64 KB logical, MMU-mapped; 1 MB physical (A0–A19) |
| **System RAM** | **512 KB SRAM on the motherboard**, `A19 = 0` — §7.1. Nobody owned this until 2026-09-04 |
| **System master clock** | one 25.175 MHz oscillator, **on the motherboard** — §1 |
| **E rate** | 25.175 / 12 = **2.0979 MHz**. This is the only rate the machine is specified at; ÷8 is experimental — §1 |
| **OS target** | NitrOS-9 Level 2 |
| **Video** | 640×200 × 256 colours, VGA out — **40 ICs**, 9 of them GALs ([`video/`](../video/), `graphics.md` §14) |
| **Audio** | 4-channel 8-bit PCM, Paula-exact — **36 ICs** ([`audio/`](../audio/), `audio.md` §10) |
| **I/O** | PS/2 keyboard + mouse, **11 ICs** ([`io/ps2/`](../io/ps2/)); RS-232 serial, **3 ICs** ([`io/serial/`](../io/serial/)). Both on `/IRQ`, both **specified** |
| **Storage** | SD card over SPI, **7 ICs**, 528 KiB/s sustained — **specified** ([`storage/`](../storage/)). ⚠ The machine's one period exception |
| **Total silicon** | **~106 ICs** — 97 on cards, **9** on the motherboard (~~13~~ — §7.1). See §8 |

Note the two CPU targets, which are different machines and are easy to confuse:

| | **CoCo 3 drop-in** | **this machine** |
|---|---|---|
| Socket | a real CoCo 3's 40-pin CPU socket | a board you design |
| E | 0.895 / 1.79 MHz, from the GIME | 2.0979 MHz, from the ÷12 divider |
| `t_AD` deadline | **110 ns, fixed by the datasheet** | ~160 ns, self-specified (`graphics.md` §5.3) |
| Video / audio | GIME | the cards in this repo |
| MMU | GIME's, emulated | 5 ICs on the motherboard — `graphics.md` §6.3.1 |
| Boot | the CoCo's own ROM | the CPU module's shadow ROM — §7.2 |

`cpu/docs/plan.md` is written against the first. `graphics.md` and `audio.md` are
written against the second. Both are live.

---

## 1. Clock tree

From `graphics.md` §5 — one oscillator, everything derived, so any card can phase-lock
to video:

```
25.175 MHz ──┬──► dot clock (video card)
             │
             └──► ÷12 ──► E at 2.0979 MHz   (Q = same divider, 3 dots early)
                  ÷8  ──► E at 3.1469 MHz   (fast-E mode — experimental, see below)
```

Both divisors are integral in **fetch slots** (4 dots), which is the property that
matters for the video card's arbitration. The divider is off-card, on the motherboard:
**1 GAL** (`graphics.md` §14).

> ⚠ **The oscillator is on the motherboard, and `graphics.md` §14 used to budget it on
> the video card.** Both cannot be true, and the motherboard is the right answer: if the
> can sat on the video card, pulling that card would kill E and stop the CPU — fatal for
> exactly the bring-up sequences that run *before* video exists (`sdcard.md` §12 step 0,
> and any serial-first DriveWire boot). The card receives the master clock from the
> backplane, which §2 already carries.

### 1.1 ÷12 is the machine's rate. ÷8 is experimental.

> **Decided 2026-09-04. This was §5 item 4, and the answer is worse than that item
> expected.** The item asked only that a default be *stated* rather than inferred. The
> review priced the alternative and found that **three independent things break at ÷8**,
> in three different subsystems, none of which had checked it:
>
> | Subsystem | At E = 3.1469 MHz | Source |
> |---|---|---|
> | **video** | VRAM read-back does not close | `graphics.md` §11 |
> | **serial** | 57 % over a 2 MHz R6551A's rating; only a genuine 4 MHz G65SC51 covers it | `serial.md` §3.3, which had only ever checked 2.0979 MHz |
> | **CPU** | 317.8 ns is **below the HD63C09E's 333 ns `t_cyc` minimum** — so the real part is out of spec, and the silicon A/B reference `plan.md` §6.2 depends on cannot even be captured at this rate | `plan.md` §3.3 |
> | storage | burst margin falls 2.25× → 1.5×, still passes | `sdcard.md` §5 |
> | audio | unaffected — the card runs from its own crystal | `audio.md` §4.1 |
>
> **The machine is specified at ÷12.** ÷8 remains implementable and the divider still
> supports it, but it is an experiment a builder opts into with the video read path and
> the ACIA understood, not a speed switch software may throw. Every cost estimate in
> `audio.md` and `modplayer.md` is quoted against 2.098 MHz and stands.

**Naming.** ÷8 is **fast-E mode**. `/WAIT` is a **wait state** — it holds E. Neither is
called "stretch": `graphics.md` §3.3 and `machine.md` §1 used that one word for those two
opposite things, which is how `serial.md` §3.3 came to offer `/WAIT` as an escape hatch
from a mode `/WAIT` cannot escape.

The audio card does **not** hang off this tree. Its period reference is a second,
independent crystal — **28.37516 MHz ÷ 8 = 3.546895 MHz**, the Amiga PAL colour clock —
and `audio.md` §4.1 calls that non-negotiable, because every module in the corpus was
tuned by ear against exactly that number. Two oscillators in the machine, and the second
one is not a convenience.

---

## 2. Backplane

From `graphics.md` §17, which retargets colormin's slot model:

| Signal | Notes |
|---|---|
| `/IOSEL` | **the `$FF40`–`$FF7F` window strobe, common to every slot** — ~~geographic, per slot~~. Corrected in this revision; see below |
| `/IOPAGE` | **open-drain, motherboard-driven — asserted for the whole of any logical `$FF00`–`$FFFF` cycle.** New in this revision; see below |
| `/WAIT` | open-drain — here it means **hold E** (never "stretch") |
| `/IRQ` | open-drain |
| `/FIRQ` | open-drain — colormin's backplane reserved only `/IRQ`; NitrOS-9 uses both |
| `/NMI`, `/RESET` | `/RESET` is generated on the motherboard — §2.1 |
| `/HALT` | **added in this revision.** It is in the CPU module's pin budget (`graphics.md` §6.3.1) and was missing from this list, which meant it had no owner and would have floated |
| `E`, `Q`, `R/W` | not colormin's `16M`/`8M`/`/MRD`/`/MWR` |
| 25.175 MHz master | so any card can phase-lock to video |
| `HSYNC`, `VSYNC` | **added in this revision** — `graphics.md` §12.2's raster-compare timer counts HSYNC, and counting HSYNC gives a line number with no origin unless VSYNC (or an equivalent frame reset) comes with it |
| Audio `L`, `R` + 2 grounds | **added in this revision** — `graphics.md` §17 instructed the backplane to carry them and this table omitted them |
| `A0–A18`, `A19` | **physical**, not logical A0–A15 — the video card needs the translated address |
| `D0–D7` | |

`A19` is the system-RAM / VRAM selector: `A19 = 0` is 512 KB of system RAM (§7.1),
`A19 = 1` is the video card's 512 KB ring (`graphics.md` §6.3).

**Physical A13–A19 come from the motherboard's MMU, not from the CPU** (§5 item 6,
`graphics.md` §6.3.1). Two consequences for whoever draws the backplane:

- **Logical A13–A15 stay on the motherboard and do not appear on a slot.** They are the
  map SRAM's address inputs. Nothing on a card has any business seeing them.
- **The `$FF00`–`$FFFF` I/O-page decode is taken from those logical lines**, so that the
  I/O page overrides translation exactly as it does on a CoCo 3. A0–A12 are untranslated,
  making the term `(logical A15..A13 = 111) AND (A12..A8 = 11111)` — the same term that
  already gates `/IOSEL`, so it costs nothing, but it has to be drawn that way.

### ⚠ `/IOPAGE`, and why the backplane was one wire short of working

> **Decided 2026-09-04 — `design-review.md` §Sys-M1 and §Vid-C2, found independently
> from both ends.**
>
> The bug was this. During any `$FFxx` access the map SRAM keeps emitting a *translated*
> physical A13–A19 onto the backplane; nothing gates it. System RAM decodes `A19 = 0` and
> the video card decodes physical A0–A18 with `A19 = 1`. So whatever the current task's
> block 7 happens to map to, **RAM or VRAM sees a perfectly valid memory cycle at the same
> moment as the addressed I/O card**:
>
> - on a **read** of `$FF40` or `$FF50`, two devices drive `D0–D7` — a real electrical
>   conflict, not a logical one;
> - on a **write** to any I/O register, a byte is *also* silently written into some
>   translated RAM or VRAM location.
>
> And this is not an exotic configuration. `graphics.md` §6.3 explicitly allows any of the
> eight MMU blocks to point at VRAM, so a graphics process with `$E000`–`$FFFF` mapped
> there puts `A19 = 1` on the backplane during **every** I/O access it makes.
>
> The term that identifies an I/O cycle already exists on the motherboard — it is what
> gates `/IOSEL`. It simply never left the motherboard. So: **`/IOPAGE` is that term,
> brought to the backplane**, and
>
> - **every physical-memory decode must qualify against it.** System RAM's `/CS` and the
>   video card's VRAM select respond only when `/IOPAGE` is high.
> - **the map SRAM's outputs are gated by it too**, so physical A13–A19 are parked at a
>   defined value during I/O cycles instead of carrying a stale translation. This also
>   answers what those lines carry during a map-write cycle, which `graphics.md` §6.3.1
>   never said.
>
> The video card could not have computed this inhibit for itself, because §2 keeps logical
> A13–A15 on the motherboard and off every slot. One wire, one sentence — **and a wrong
> board without it.**

### ⚠ `/IOSEL` is a window strobe, not a geographic select

> **Decided 2026-09-06, and it corrects this table's own row.** Found while drawing the
> backplane — [`hardware/README.md`](../hardware/README.md) finding 2. **Four documents
> said "geographic, per slot"**, and the phrase cannot mean here what it meant where it
> came from.
>
> In colormin it really is geographic. `~/code/colormin/docs/backplane.md` §3 gives each
> of four slots its own **64-byte** window — `$3F00`–`$3F3F` through `$3FC0`–`$3FFF` —
> decoded by slot position on a common pin. Four slots, four identical blocks, and which
> card sits in which slot *is* the address decode.
>
> **This machine's windows are function-sized, not slot-sized, and no two are alike**:
> audio 16 bytes, video 32, PS/2 4, serial 4, storage 4 (§3). Decode by position cannot
> produce them. It would have to nail each slot to a fixed window, which means every card
> has exactly one slot it will work in — and at that point the **base-address jumper**
> that `audio.md` §9.1 and `ps2.md` §3.2 each promise *in the very next sentence* selects
> nothing, because nothing is left for it to select.
>
> **The two sentences were never compatible.** "Geographic, per slot" and "so the base is
> a jumper" are alternatives, and three documents wrote both without noticing.
>
> **The decision: `/IOSEL` is the `$FF40`–`$FF7F` window strobe, common to every slot.**
> It is the `/IOPAGE` term above, further qualified by `A7,A6 = 01` — one more product
> term on a decode the motherboard already forms. **A card completes its own decode from
> `A0`–`A5` against its jumpered base**, which is what `A0`–`A5` are on the backplane
> *for*.
>
> **`serial.md` §6 is the card that got this right**, and it did so without remarking on
> it: its decode GAL takes `CS0`/`/CS1` "from geographic `/IOSEL` **and `A2`–`A5`**".
> That is the window-strobe model, written down, in the one document that also never
> claimed the geography.
>
> **What it costs, stated because it is a real loss.** The geography went with it: a slot
> number no longer means anything to the address decode, so **nothing prevents two cards
> being jumpered to the same base, and nothing detects it.** In colormin that collision
> was impossible by construction. Here it is a build error that presents as two cards
> driving `D0`–`D7` at once — the same failure mode `/IOPAGE` was added to prevent, from
> a different cause.
>
> **The alternative, recorded because it is the one that keeps the geography.** Give the
> motherboard a per-slot base/size comparator — a window register per slot, written at
> boot. Collisions become impossible again, the map becomes software-configurable, and
> §5 item 1 dissolves outright. It costs several packages on a motherboard that is nine
> (§7.1), it needs a window in an `$FF` map with four bytes left, and nobody has specified
> it. **Not taken now — but it is the shape the answer takes if §5 item 1 is ever resolved
> by paging rather than by widening the decode.**
>
> **"Geographic" survives as the name of the `$FF40`–`$FF7F` range**, here and in five
> other documents, and that is harmless. It is a name now, not a mechanism.

### 2.1 Electrical

> **New in this revision.** Every item here is a signal or a part that every card's
> document assumed existed and that no document owned. `design-review.md` §Sys-M4.

| | |
|---|---|
| **Bus voltage** | **5 V TTL.** Only ever inferable before now, from each card's separate HCT-level argument. The CPU module is 3.3 V and fronts this bus through its own `'541`/`'245` buffers (`plan.md` §2.6/§3.2), which were specified for the CoCo 3 socket and apply here identically |
| **Power-on reset** | **on the motherboard**, and it appeared in no card's budget. A supervisor (DS1233-class) or an RC + Schmitt inverter, driving backplane `/RESET`. Every card takes `/RESET` as an input — `serial.md` §6 already does; `ps2.md` did not and now must (`design-review.md` §IO-P3) |
| **`/HALT`** | tied high on the motherboard through 4.7 kΩ, as the CoCo does (`plan.md` §2.6). Nothing in this machine drives it; saying so is the point |
| **Open-drain pull-ups** | `/IRQ`, `/FIRQ`, `/WAIT`, `/NMI`, `/IOPAGE` — **on the motherboard**, 3.3 kΩ. Four cards declare open-drain outputs and no document placed the resistors |
| **Data-bus loading** | `D0–D7` sees the CPU's `'245`, the video card's `'245`, audio's `'245`, two PS/2 `'595`s, the 6551, storage's `'595`, and system RAM — **eight or more loads before any expansion.** Within HC/HCT fan-out, but it is why the backplane wants short traces and it should be counted, not assumed |

---

## 3. The `$FF` I/O map

Geographic decode spans **`$FF40`–`$FF7F`** (`graphics.md` §17 — widened from
`$FF60`–`$FF7F` deliberately, because it is a decode term today and a board respin
later).

| Window | Size | Owner | Status |
|---|---|---|---|
| `$FF40`–`$FF4F` | 16 B | **audio** | *proposed* — `audio.md` §9.1 |
| `$FF50`–`$FF53` | 4 B | **PS/2 keyboard + mouse** | *proposed* — `io/ps2/docs/ps2.md` §3.2 |
| `$FF54`–`$FF57` | 4 B | **RS-232 serial** | *proposed* — `io/serial/docs/serial.md` §7.1 |
| `$FF58`–`$FF5B` | 4 B | **SD card storage** | *proposed* — `storage/docs/sdcard.md` §6.1 |
| `$FF5C`–`$FF5F` | 4 B | **free** | the machine's only unallocated I/O — half the disk reservation, **handed back** |
| `$FF60`–`$FF7F` | 32 B | **video** | *taken* — `graphics.md` §13 |
| `$FFA0`–`$FFAF` | 16 B | **MMU, and now boot control** | on the motherboard, decoded directly — `graphics.md` §6.3.1. **Not** GIME-compatible, and not in the geographic window. Enable, task select, the shadow-ROM disable and the vector RAM all live here — §7.2 |

### ⚠ The map has four bytes left, and that is all.

16 + 4 + 4 + 4 + 4 free + 32 = **64**. The disk-controller reservation was sized for a
WD1773 — **four registers** plus a latch — and `storage/docs/sdcard.md` §6.1 needs three,
so **four bytes came back**. That is the only movement this map has ever made in the
expanding direction, and it is one small card's worth, once.

> ⚠ This table said "five registers plus a latch" for the WD1773 until 2026-09-04.
> It is four (`ps2.md` §3.2 had it right). The arithmetic above does not change.

There is still no window for a second serial port, a third PS/2 port, a network interface,
or a floppy controller alongside the SD card.

`graphics.md` §17 said *"widen the window now — it is a decode term today and a board
respin later."* **That has stopped being prudent advice and become blocking.** See §5
item 1, which is now the highest-priority open item in the machine.

---

## 4. Interrupts

| Line | Owner | Source |
|---|---|---|
| `/IRQ` | **shared, open-drain** | video's VBL and raster compare — `graphics.md` §12. VBL is NitrOS-9's system tick. **PS/2 joins as a third source** — `io/ps2/docs/ps2.md` §3.1. **Serial as a fourth** — `serial.md` §6 |
| `/FIRQ` | **audio, and audio alone** | the on-card tempo timer — `audio.md` §8.1 |
| `/NMI` | unassigned | and should stay that way — a non-maskable I/O source would pre-empt the replayer tick |

`audio.md` §8.1 takes `/FIRQ` as the **sole** source specifically so that there is no
polling chain in the replayer's interrupt path, and `graphics.md` §17 agrees the
ownership should be recorded here rather than left to first-come. It now is.

**The two lines are not symmetric, and the difference is the whole answer for I/O.**
`/FIRQ` is exclusive by design. `/IRQ` was never exclusive — it has carried two sources
since `graphics.md` §12, its handler already polls, and a third and fourth source are
what the line is for.

### 4.1 The polling order is part of the specification

> **Decided 2026-09-04 — `design-review.md` §Sys-M3.** Four sources on `/IRQ` keep their
> status in four different cards' registers (`VSTAT $FF73`, `IOSTAT $FF52`, the 6551's
> `STATUS $FF55`, and raster compare inside the CPU module). There is no consolidated
> pending register anywhere, and this document's earlier claim that "NitrOS-9's CoCo 3
> IRQ code already expects a GIME-compatible interrupt-source block" **was wrong on its
> own terms** — nothing in this machine decodes `$FF92`/`$FF93`, and §5 item 6 lists the
> interrupt block as a GIME divergence in the same breath.
>
> That leaves the dispatcher polling, and **the order is not free**, because one of the
> four sources is destructive to read:
>
> **1. video `VSTAT`  →  2. PS/2 `IOSTAT`  →  3. serial `STATUS` (last, always).**
>
> Video first because VBL is the system tick and by far the most frequent source. Serial
> **last** because reading the 6551's `STATUS` **clears the interrupt and returns the
> error bits in the same read** (`serial.md` §7.3) — a dispatcher that probes serial
> early, decides it was not the source and moves on has already destroyed the overrun and
> framing bits that the serial handler needed. The serial handler must therefore consume
> its errors on that single read rather than probe-and-defer.
>
> The alternative — the CPU module serving a read-only consolidated pending register, for
> zero ICs, since it already owns raster compare — was considered and **not** taken: it
> adds a fifth NitrOS-9 divergence to a ledger nobody is yet keeping (§5 item 6), where
> the polling order costs nothing but a documented sentence.

**Nothing masks `/IRQ` or `/FIRQ` for long, with two exceptions that must be read
together**, because they are the machine's only interrupt-latency budget and they live in
different documents:

| Masked window | Duration | Consequence |
|---|---|---|
| `sdcard.md` §4.4 — a chunked TFM sector transfer | 49 µs per chunk | 0.25 % of the replayer's 20 ms tick; `/FIRQ` is delayed, not lost, because the source is level-held. VBL is latched in `VSTAT` and survives |
| `ps2.md` §7 — a host-to-device transmit (keyboard LEDs, mouse enable) | **~0.8–1.3 ms per frame** | ⚠ Longer than the 6551's 521 µs inter-byte deadline at 19,200 baud, so **an LED update during a download guarantees a serial overrun** — `design-review.md` §IO-P4 |

---

## 5. Open items — this document's own

These are not deferred details; each one blocks a board.

1. **⚠ THE I/O WINDOW IS ALL BUT FULL — and this is now the machine's blocking decision.**
   `$FF40`–`$FF7F` is 64 bytes. Audio takes 16, PS/2 4, serial 4, storage 4, video 32.
   **Four bytes remain**, returned by the storage card (§3), and they are the machine's
   entire margin.

   > **It now costs throughput, not just expandability.**
   > [`storage/docs/sdcard.md`](../storage/docs/sdcard.md) §11.1 shows that a 512-byte
   > memory-mapped block buffer would delete that card's `TFM` hazard outright and buy
   > 27 % more transfer rate — and it is rejected purely because neither the 64-byte `$FF`
   > window nor the 1 MB physical map (`graphics.md` §6.3 fixes both halves) has room for
   > it. **This is the strongest argument the machine has produced for widening the map.**

   The options are unchanged and only one of them is cheap **now**: widen the geographic
   decode below `$FF40`, page the window, or accept that the machine is closed to further
   cards. `graphics.md` §17 warned that this is "a decode term today and a board respin
   later" — **decide it before the backplane is laid out.**

   > **Two proposals are on the table, and together they are what filled it.**
   > [`io/serial/docs/serial.md`](../io/serial/docs/serial.md) §7.1 asks for
   > `$FF54`–`$FF57` — four bytes, because a 6551 ACIA decodes exactly four registers.
   > [`io/ps2/docs/ps2.md`](../io/ps2/docs/ps2.md) §3.2
   > asks for **`$FF50`–`$FF53`** — four bytes — leaving `$FF54`–`$FF5F`, twelve bytes,
   > for the disk controller. Four suffices because the card has four registers: two data
   > ports, one status, one control. **Still a proposal:** nobody has specified a disk
   > controller, so nobody can say whether twelve is enough for it — but a WD1773 is four
   > registers plus a latch, so it very likely is.

2. **No interrupt line for an I/O card.** §4 gives `/IRQ` to video and `/FIRQ` to audio
   as sole owner. A PS/2 keyboard wants an interrupt; polling it from the VBL tick is a
   real option at 50–70 Hz and should be *chosen*, not defaulted into. `/NMI` is free and
   is almost certainly the wrong answer.

   > **Chosen, and the premise of this item was wrong.**
   > [`io/ps2/docs/ps2.md`](../io/ps2/docs/ps2.md) §3.1 takes **`/IRQ`, as a third
   > source** — see §4: `/IRQ` is open-drain, already carries VBL and raster compare, and
   > its handler already polls. Only `/FIRQ` is exclusive.
   >
   > Cost: **~0.9 % of the CPU while input is actually happening**, zero otherwise.
   > ⚠ That figure assumes 100 cycles of NitrOS-9 interrupt
   > dispatch; at 400 it is 3.4 %. **Unmeasured — `ps2.md` §14 item 3.**
   >
   > `/NMI` is confirmed wrong, for a different reason than expected: being non-maskable,
   > a keypress would pre-empt the replayer tick that §4's `/FIRQ` ownership exists to
   > protect.
   >
   > **Serial follows the same call** — `serial.md` §6 puts the 6551's `/IRQ` on the same
   > line as the fourth source. Its §5 shows the cost is what bounds serial throughput: no
   > FIFO means one interrupt per byte, so 19,200 baud is 9 % of the CPU at 100 cycles of
   > dispatch and **37 % at 400** — and that is the *receive* direction alone; full duplex
   > doubles it (`design-review.md` §IO-S3). The practical ceiling is 4800–19,200 baud, and
   > **the same single measurement decides that and whether PS/2's FIFO comes back.**
   >
   > ⚠ **The order in which they are polled is now specified — §4.1.** It was not, and one
   > of the four sources destroys its own status on read.

3. **The MMU register set is not written down.** `graphics.md` §6.3 said
   "GIME-register-compatible, `$FFA0`–`$FFAF`, 8 blocks, two task registers, 6-bit block
   numbers" and stopped there. `graphics.md` §18 step 0 lists it as an exit criterion.
   Nothing in `cpu/` implements it yet — Phase 1 is the timing spike and has no MMU.

   > **Still open, and it grew.** The MMU is **hardware** — a write-decode GAL on the
   > motherboard (`graphics.md` §6.3.1) — so the register set is a fitting constraint, and
   > **GIME compatibility is not a requirement**, so this is a free design: the 6-bit block
   > number becomes 7 bits because the physical map is 1 MB, and enable and task select
   > move into the same contiguous window instead of sitting at the GIME's `$FF90`/`$FF91`.
   >
   > ⚠ **§7.2 adds two more things to the same 16 bytes**: the shadow-ROM disable bit and
   > the 16-byte vector RAM's write port. `$FFA0`–`$FFAF` now carries the map entries, task
   > select, MMU enable, shadow-ROM disable and vector-RAM access — **fit it before the GAL
   > is fitted**, because it may not fit, and the free bytes at `$FF5C`–`$FF5F` are the only
   > relief the machine has.
   >
   > **This is the most blocking of the CPU-side items**, because three things wait on it:
   > the motherboard's write-decode GAL, the NitrOS-9 patch, and now the boot path.

4. **The E/Q divider ratio is assumed, not frozen.** Every cost estimate in `audio.md`
   and `modplayer.md` is quoted against 2.098 MHz, i.e. ÷12. `graphics.md` §11 shows VRAM
   read-back closing at ÷12 and *not* at ÷8, so ÷8 is not a free speed switch — it costs
   the read path. The default should be stated here rather than inferred from arithmetic.

   > **Closed 2026-09-04 — §1.1.** ÷12 is the machine's rate. ÷8 breaks the video read
   > path, takes the 6551 57 % over its rating, and is *below the real HD63C09E's `t_cyc`
   > minimum* — the last of which nobody had checked, and which means the drop-in's own
   > silicon reference cannot be captured there. Three subsystems, none of which knew.

5. **Backplane or single board?** Every card document assumes slots and a `/IOSEL`, but
   nothing states how many slots, what the connector is, or whether the CPU module is a
   card or the motherboard.

   > **Still open — and it now has more to carry.** The motherboard's parts list is no
   > longer just the MMU and the divider: §7.1's 512 KB of system RAM, §2.1's reset
   > supervisor and pull-ups, and the master oscillator all live there. The connector
   > question has also acquired an answer it must satisfy — §8's supply is amps-scale, so
   > **how many power and ground pins per slot** is part of this decision, not a detail
   > after it.

6. **LQFP48 vs LQFP64 for the CPU module.** `graphics.md` §6.3 recommends the LQFP64 part
   for the homebrew card, because the MMU needs a second store for A16–A19.
   `cpu/docs/plan.md` §3.2 closes the pin budget on the LQFP48 — but for the *CoCo 3*
   drop-in, which has no MMU of its own to emulate at that width.

   > **Decided: the MMU moves off the CPU — `graphics.md` §6.3.1.** One STM32 SKU covers
   > both machines, the 48-pin part is cheaper and better stocked, and the timing is a wash
   > (the in-CPU version spends ~3–4 core cycles plus a second `STR` *inside* `t_AD`; the
   > external map spends 15 ns of SRAM propagation *after* it, on the motherboard, where
   > `graphics.md` §5.3's ~160 ns has room).
   >
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
   >
   > **What is given up, and it was priced rather than deferred.** `graphics.md` §6.3's
   > case for the in-CPU MMU is that faithful `$FFA0`–`$FFAF` emulation is "the
   > difference between porting the memory manager and configuring it". **The owner's
   > call is that patching NitrOS-9 Level 2's memory manager for this machine's own
   > register set is about an hour of work, not a port**, so the register set is now a
   > free design — see item 3, which is where the work actually lands.
   >
   > ⚠ **The hour is per-subsystem, and this machine has several.** It already diverges
   > from the GIME at the video registers (`graphics.md` §13), at the interrupt block,
   > at the MMU, and now at the boot ROM and vector page (§7.2). Nothing here claims the
   > sum is an hour. **Whoever is counting NitrOS-9 divergence should count it in one
   > place, and nobody is.**

---

## 6. What each card still owes the machine

Beyond §5, each subsystem's own document carries its open items; these are the ones with
a cross-card dependency.

| Owner | Item | Where |
|---|---|---|
| **machine** | **⚠ Write the MMU register set.** It is now hardware, and three things wait on it: the motherboard's write-decode GAL, the NitrOS-9 patch, and §7.2's boot control | §5 item 3, `graphics.md` §6.3.1 |
| **machine** | **Keep a NitrOS-9 divergence ledger** — video registers, interrupt block, MMU, boot ROM. Each is priced individually and nothing sums them | §5 item 6 |
| **machine** | **Draw the motherboard.** ⚠ **Begun** — [`hardware/`](../hardware/) has the backplane pinout, the motherboard and every card's bus interface, at schematic level. Nine ICs, 512 KB of RAM, a reset supervisor and the pull-ups. Placement waits on the GAL fitting | §2.1, §7.1, §5 item 5, [`hardware/README.md`](../hardware/README.md) |
| **machine** | **⚠ Fit `$FFA0`–`$FFAF`** — map entries, task, enable, shadow-ROM disable and vector RAM in 16 bytes | §5 item 3, §7.2 |
| cpu | Confirm the GIME accepts a 3.3 V `V_OH` from the level buffers | `cpu/README.md` TODO |
| cpu | First silicon measurement, against the recorded predictions | `cpu/docs/plan.md` §5 |
| cpu | **Provision the option bytes** (`nSWBOOT0 = 0`) — PB8 is A8 *and* BOOT0, so an unprovisioned part boots nondeterministically in the socket | `design-review.md` §Cpu-M2 |
| video | Bench the dot path and fit the sequencer GALs *before* layout | `graphics.md` §18 steps 1–2 |
| video | **Specify the video output stage** — the R-2R ladders cannot drive 75 Ω from `'574` outputs, and blanking has no mechanism | `design-review.md` §Vid-M4 |
| audio | Freeze §9's register map — it is the deliverable, ahead of any board | `audio.md` §15 step 0 |
| audio | The MCU bring-up card, which is what proves the register map | `audio.md` §12.5 |
| io | Measure the PS/2 protocol on a scope; add a reference document to `reference/` | `ps2.md` §13 step 1, §14 item 1 |
| io | **Measure NitrOS-9's interrupt dispatch cost** — it decides serial's ceiling, PS/2's FIFO, and §4.1's margins | `ps2.md` §14 item 3, §13 step 8 |
| io | Source an `R6551A` or `G65SC51` — the in-production `W65C51N` is defective for this use | `serial.md` §3.3, §13 item 5 |
| io | Confirm whether NitrOS-9's `sc6551` exists; it is the card's entire software cost | `serial.md` §13 item 2 |
| **cpu** | **⚠ Settle `TFM`'s interrupt/resume behaviour from silicon** — and note it is now a *choice*, not a discovery, because this machine's 6309 is the project's own firmware | `sdcard.md` §4, §13 item 1 |
| storage | A NitrOS-9 `RBF` driver — larger than the card. Evaluate matching CoCoSDC's map to inherit one | `sdcard.md` §13 item 4 |
| **project** | **Choose a licence.** The repository has none for its own work | `design-review.md` §Sys-M6 |

---

## 7. Memory, boot, and the vector page

> **New in this revision, and the whole of it answers `design-review.md` §Sys-C1 and
> §Sys-M2.** Both are things that belonged to the machine rather than to any card, which
> is why five internally careful card specifications went to press without them: the
> machine had **no main memory owner and no way to execute its first instruction.**

### 7.1 System RAM

**512 KB of SRAM on the motherboard, selected by `A19 = 0` qualified with `/IOPAGE`
(§2).** **One** × 512K×8 (AS6C4008-class, 55 ns), and **no decode**.

> ⚠ **This said "Four × 512K×8 … and a decode" until 2026-09-06, and both halves were
> wrong.** Found while drawing the motherboard, which is the first thing that had to
> fit the part rather than cite it — [`hardware/README.md`](../hardware/README.md)
> finding 1.
>
> **512K × 8 is 512 KB.** Four of them is 2 MB — against a 512 KB requirement, in a 1 MB
> physical map that gives system RAM exactly `A19 = 0`, i.e. **A0–A18, nineteen address
> lines**. An AS6C4008 has A0–A18. It *is* the requirement, once, and the part this
> section already named was the right one all along.
>
> **And the decode went with the other three.** With one package there is nothing to
> decode *between*: `/CE` is the `A19 = 0` AND `/IOPAGE` term, and the MMU's `GAL22V10`
> already forms that term to generate `/IOSEL` (`graphics.md` §6.3.1). The decode was a
> part the fourth SRAM created and the first one never needed.
>
> **The motherboard falls from ~13 ICs to 9** — MMU 5, divider GAL, oscillator, reset
> supervisor, system RAM — and the machine from ~110 to **~106**. §0 and §8 are
> corrected to match.
>
> It is the same shape of error the 2026-09-04 review kept finding, and §8's own closing
> lesson names it: **a table that exists to do arithmetic is worth re-examining against
> the parts catalogue.** This row was never checked against the part it names — and
> unlike audio's 57, it was not found by re-reading the document. It was found by a
> board file that had to say how many packages to draw.

This document asserted "`A19 = 0` is 512 KB of system RAM" in §0 and §2 from the
beginning and never said who provides it. It was in no chip budget — every card accounts
scrupulously for its own parts, and the motherboard was "3 ICs plus a divider GAL". SRAM
rather than DRAM because **DRAM needs a refresh owner and this machine has none**; at 55 ns
it also clears the CPU's ~160 ns `t_AD`-to-data budget without a wait state, which DRAM at
this vintage would not.

### 7.2 Boot — the CPU module serves the vectors and a shadow ROM

**The failure this fixes.** The 6309 fetches its reset vector from `$FFFE`–`$FFFF`. §2
makes `$FF00`–`$FFFF` override MMU translation, exactly as a CoCo 3 does — but a CoCo 3's
SAM/GIME *specifically maps `$FFF2`–`$FFFF` onto ROM*, and this machine decodes only
`$FF40`–`$FF7F` and `$FFA0`–`$FFAF` in that page. `$FFFE` selected **nothing**. The CPU
would have fetched its reset vector from an undriven bus. Worse, there was nowhere to put
a ROM even if one were added: `graphics.md` §6.3 spends the entire 1 MB physical map on
512 KB of RAM and 512 KB of VRAM. And the bring-up plan was circular —
`sdcard.md` §12 step 0 boots NitrOS-9 over DriveWire "before any of this exists", which
needs a 6809 boot client, which needs a ROM.

**The decision.** The CPU module already synthesises every bus cycle in firmware, so it
can answer a fetch without running one:

| | |
|---|---|
| **Shadow ROM** | at reset, logical `$E000`–`$FFFF` is served from ~8 KB of the STM32's 128 KB flash **without a bus cycle** — except `$FF00`–`$FFBF`, which continues to decode normally to cards and the MMU, so I/O works during boot |
| **Vector page** | `$FFF0`–`$FFFF` is served from a 16-byte **vector RAM inside the CPU module**, writable through the `$FFA0`–`$FFAF` window, so the OS can retarget the vectors. Initialised from flash at reset to point into the shadow ROM. **Vector service is always on** — it is the one thing that must never depend on a configuration bit |
| **Disable** | a bit in the `$FFA0` window turns off the `$E000`–`$FEFF` shadow once the OS is up, returning that logical space to RAM. NitrOS-9 Level 2 wants it |
| **CoCo 3 drop-in** | the whole mechanism is **off**. That machine has its own ROM, and a drop-in that shadowed it would be a drop-in that broke it |

**Cost:** zero ICs, ~8 KB of a 128 KB flash, and one more line in the divergence ledger
(§5 item 6). **What it buys:** bring-up needs no ROM chip, no programmer, and no
carve-out drawn into a physical map that has no room for one.

> **The alternative, recorded because it is genuinely close.** An 8 KB EPROM plus a decode
> on the motherboard — 2 ICs, no CPU divergence, and a `HD63C09E` could then be dropped
> into the socket and the machine would still boot. It needs an explicit ROM/vector
> carve-out cut out of the I/O page, and it puts the boot firmware on a part you have to
> program. It was not taken because the CPU-side answer costs nothing and this machine's
> CPU is firmware anyway — but if the "drop a real 6309 in" property is ever wanted back,
> **this is the switch that returns it.**
>
> ⚠ **And that property is what this decision spends.** `graphics.md` §16 item 8 offers
> "drop a real HD63C09E in" as a standing sanity check on the rest of the machine. Under
> the shadow-ROM answer it no longer holds: a real 6309 in the socket fetches `$FFFE` from
> a bus with nothing on it. Marked there too.

---

## 8. Power

> **New in this revision — `design-review.md` §Sys-M5.** Video estimated its own current
> and audio estimated its own; PS/2, serial, storage, the motherboard and §7.1's system
> RAM estimated nothing, and **nothing summed them.** "Measure at bring-up", per card, does
> not produce a power supply.

| Rail | Consumer | ICs | Estimate |
|---|---|---|---|
| 5 V | **video card** | 40 (9 GALs) | **~1.1–1.7 A**, design to 2 A — `graphics.md` §14. ⚠ It quoted 450–650 mA until 2026-09-04, which its own per-GAL figure (630–810 mA for the GALs alone) already exceeded |
| 5 V | **audio card** | 36 | **~300–400 mA** — `audio.md` §10 |
| 5 V | **PS/2**, plus ~50–100 mA per attached device from each mini-DIN pin 4 | 11 | not yet estimated; order 100 mA of logic + up to 200 mA of devices |
| 5 V | **serial**; **storage** (plus SD write bursts behind its own LDO) | 3 + 7 | not yet estimated |
| 5 V | **motherboard**: MMU (5), divider GAL, oscillator, reset supervisor, 512 KB SRAM (~~+ decode~~ — §7.1) | ~~13~~ **9** | not yet estimated |
| 3.3 V | CPU module and its buffers; the SD card | 8 | not yet estimated |

**The machine is plausibly 2–3 A at 5 V across ~106 ICs, plus a 3.3 V rail.**

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

This is a real supply and a real backplane-distribution question — **how many power and
ground pins per slot connector** — which §5 item 5 must answer as part of choosing the
connector. Each card owes a measured figure at its own bring-up; this table is where they
land.

> ⚠ **36 ICs is back inside the envelope this document originally assumed, and the fit
> still has to be measured.** `audio.md` §16 item 19 raised it as an open question at 57;
> three passes have taken it to 36, against the 35 the single-Eurocard assertion was
> first made at. The assertion is not restored by arriving at the same number — it was
> never measured, and the analogue section has grown from two converters and four
> amplifier channels to eight halves and ten. **Measure it, with the analogue section
> physically separate.** It remains a layout decision nobody has taken.
