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
genuinely undecided — and it is not short, because PS/2 and serial arrive into a bus
whose interrupt lines and I/O window are both already spoken for.

> **This document does not get to invent anything.** Where a card spec says "propose"
> rather than "take", it is recorded here as a proposal. Where two documents disagree,
> the disagreement is recorded rather than resolved.

---

## 0. The machine in one table

| | |
|---|---|
| **CPU** | HD6309E in native mode, synthesised on an STM32G431 ([`cpu/`](../cpu/)) |
| **MMU** | **on the motherboard: 3 ICs, the SAM/GIME/DAT arrangement** — `graphics.md` §6.3.1. Register set is a free design, not GIME-compatible (§5 item 6) |
| **Address space** | 64 KB logical, MMU-mapped; 1 MB physical (A0–A19) |
| **System master clock** | one 25.175 MHz oscillator, on the motherboard — `graphics.md` §5 |
| **E rate** | 25.175 / 12 = **2.0979 MHz**, software-selectable to ÷8 = 3.1469 MHz |
| **OS target** | NitrOS-9 Level 2 |
| **Video** | 640×200 × 256 colours, VGA out, ~33 ICs ([`video/`](../video/)) |
| **Audio** | 4-channel 8-bit PCM, Paula-exact, 35 ICs ([`audio/`](../audio/)) |
| **I/O** | PS/2 keyboard + mouse, 9 ICs ([`io/ps2/`](../io/ps2/)); RS-232 serial, 3 ICs ([`io/serial/`](../io/serial/)). Both on `/IRQ`, both **specified**. |
| **Storage** | SD card over SPI, 7 ICs, 537 KB/s — **specified** ([`storage/`](../storage/)). ⚠ The machine's one period exception. |

Note the two CPU targets, which are different machines and are easy to confuse:

| | **CoCo 3 drop-in** | **this machine** |
|---|---|---|
| Socket | a real CoCo 3's 40-pin CPU socket | a board you design |
| E | 0.895 / 1.79 MHz, from the GIME | 2.0979 / 3.1469 MHz, from the ÷12/÷8 divider |
| `t_AD` deadline | **110 ns, fixed by the datasheet** | ~160 ns, self-specified (`graphics.md` §5.3) |
| Video / audio | GIME | the cards in this repo |
| MMU | GIME's, emulated | 3 ICs on the motherboard — `graphics.md` §6.3.1 |

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
                  ÷8  ──► E at 3.1469 MHz   (stretch mode, software-selectable)
```

Both divisors are integral in **fetch slots** (4 dots), which is the property that
matters for the video card's arbitration. The divider is off-card, on the motherboard:
**1 GAL**, or a `'163` + `'74` (`graphics.md` §14).

The audio card does **not** hang off this. Its period reference is a second,
independent crystal — **28.37516 MHz ÷ 8 = 3.546895 MHz**, the Amiga PAL colour clock —
and `audio.md` §4.1 calls that non-negotiable, because every module in the corpus was
tuned by ear against exactly that number. Two oscillators in the machine, and the second
one is not a convenience.

---

## 2. Backplane

From `graphics.md` §17, which retargets colormin's slot model:

| Signal | Notes |
|---|---|
| `/IOSEL` | geographic, per slot |
| `/WAIT` | open-drain — here it means **"stretch E"** |
| `/IRQ` | open-drain |
| `/FIRQ` | open-drain — colormin's backplane reserved only `/IRQ`; NitrOS-9 uses both |
| `/NMI`, `/RESET` | |
| `E`, `Q`, `R/W` | not colormin's `16M`/`8M`/`/MRD`/`/MWR` |
| 25.175 MHz master | so any card can phase-lock to video |
| `A0–A18`, `A19` | **physical**, not logical A0–A15 — the video card needs the translated address |
| `D0–D7` | |

`A19` is the system-RAM / VRAM selector: `A19 = 0` is 512 KB of system RAM, `A19 = 1`
is the video card's 512 KB ring (`graphics.md` §6.3).

**Physical A13–A19 come from the motherboard's MMU, not from the CPU** (§5 item 6,
`graphics.md` §6.3.1). Two consequences for whoever draws the backplane:

- **Logical A13–A15 stay on the motherboard and do not appear on a slot.** They are the
  map SRAM's address inputs. Nothing on a card has any business seeing them.
- **The `$FF00`–`$FFFF` I/O-page decode is taken from those logical lines**, so that the
  I/O page overrides translation exactly as it does on a CoCo 3. A0–A12 are untranslated,
  making the term `(logical A15..A13 = 111) AND (A12..A8 = 11111)` — the same term that
  already gates `/IOSEL`, so it costs nothing, but it has to be drawn that way.

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
| `$FFA0`–`$FFAF` | 16 B | **MMU** | on the motherboard, decoded directly — `graphics.md` §6.3.1. **Not** GIME-compatible, and not in the geographic window, so it does not touch the four free bytes. Enable and task select live here too, not at `$FF90`/`$FF91` |

### ⚠ The map has four bytes left, and that is all.

16 + 4 + 4 + 4 + 4 free + 32 = **64**. The disk-controller reservation was sized for a
WD1773 — five registers plus a latch — and `storage/docs/sdcard.md` §6.1 needs three, so
**four bytes came back**. That is the only movement this map has ever made in the
expanding direction, and it is one small card's worth, once.

There is still no window for a second serial port, a third PS/2 port, a network interface,
or a floppy controller alongside the SD card.

`graphics.md` §17 said *"widen the window now — it is a decode term today and a board
respin later."* **That has stopped being prudent advice and become blocking.** See §5
item 1, which is now the highest-priority open item in the machine.

---

## 4. Interrupts

| Line | Owner | Source |
|---|---|---|
| `/IRQ` | **shared, open-drain** | video's VBL and raster compare — `graphics.md` §12. VBL is NitrOS-9's system tick. **PS/2 joins as a third source** — `io/ps2/docs/ps2.md` §3.1. |
| `/FIRQ` | **audio, and audio alone** | the on-card tempo timer — `audio.md` §8.1 |
| `/NMI` | unassigned | and should stay that way — a non-maskable I/O source would pre-empt the replayer tick |

`audio.md` §8.1 takes `/FIRQ` as the **sole** source specifically so that there is no
polling chain in the replayer's interrupt path, and `graphics.md` §17 agrees the
ownership should be recorded here rather than left to first-come. It now is.

**The two lines are not symmetric, and the difference is the whole answer for I/O.**
`/FIRQ` is exclusive by design. `/IRQ` was never exclusive — it has carried two sources
since `graphics.md` §12, its handler already polls, and NitrOS-9's CoCo 3 IRQ code
already expects a GIME-compatible interrupt-source block. **A third source on `/IRQ` is
what the line is for**, and that is where PS/2 goes. See §5.

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
   > ports, one status, one control. It had asked for eight before the design lost its
   > FIFO and its transmit engine. **Still a proposal:** nobody has specified a disk
   > controller, so nobody can say whether twelve is enough for it — but a WD1773 is four
   > registers plus a latch, so it very likely is.

2. **No interrupt line for an I/O card.** §4 gives `/IRQ` to video and `/FIRQ` to audio
   as sole owner. A PS/2 keyboard wants an interrupt; polling it from the VBL tick is a
   real option at 50–70 Hz and should be *chosen*, not defaulted into. `/NMI` is free and
   is almost certainly the wrong answer.

   > **Chosen, and the premise of this item was wrong.**
   > [`io/ps2/docs/ps2.md`](../io/ps2/docs/ps2.md) §3.1 takes **`/IRQ`, as a third
   > source** — see §4: `/IRQ` is open-drain, already carries VBL and raster compare, and
   > its handler already polls. Only `/FIRQ` is exclusive. The first revision of that
   > document polled from the VBL tick instead, to avoid touching the interrupt structure
   > at all, and paid a 16-byte FIFO per port for it — **four of sixteen packages**. That
   > was the wrong trade.
   >
   > Cost: **~0.9 % of the CPU while input is actually happening**, zero otherwise, with
   > the mouse pinned at 40 samples/s because a pointer cannot be displayed faster than
   > the 70 Hz frame rate. ⚠ That figure assumes 100 cycles of NitrOS-9 interrupt
   > dispatch; at 400 it is 3.4 %. **Unmeasured — `ps2.md` §14 item 3.**
   >
   > `/NMI` is confirmed wrong, for a different reason than expected: being non-maskable,
   > a keypress would pre-empt the replayer tick that §4's `/FIRQ` ownership exists to
   > protect.
   >
   > **Serial follows the same call** — `serial.md` §6 puts the 6551's open-drain `/IRQ`
   > on the same line, making it the fourth source after VBL, raster compare and PS/2. Its
   > §5 shows the cost is what bounds serial throughput: no FIFO means one interrupt per
   > byte, so 19,200 baud is 9 % of the CPU at 100 cycles of dispatch and **37 % at 400**.
   > The practical ceiling is 4800–19,200 baud, and **the same single measurement decides
   > that and whether PS/2's FIFO comes back.**

3. **The MMU register set is not written down.** `graphics.md` §6.3 said
   "GIME-register-compatible, `$FFA0`–`$FFAF`, 8 blocks, two task registers, 6-bit block
   numbers" and stopped there. `graphics.md` §18 step 0 lists it as an exit criterion.
   Nothing in `cpu/` implements it yet — Phase 1 is the timing spike and has no MMU.

   > **Still open, but its character changed with item 6.** Two things moved. The MMU is
   > now **hardware** — a write-decode GAL on the motherboard (`graphics.md` §6.3.1) —
   > so the register set is a fitting constraint, not a firmware detail, and it is what
   > that GAL needs before it can be fitted. And **GIME compatibility is no longer a
   > requirement**, so this is a free design: the 6-bit block number becomes 7 bits
   > because the physical map is 1 MB, and enable and task select move into the same
   > contiguous window instead of sitting at the GIME's `$FF90`/`$FF91`.
   >
   > **This is now the most blocking of the CPU-side items**, because two boards wait on
   > it: the motherboard's GAL and whatever the NitrOS-9 patch of item 6 is written
   > against.

4. **The E/Q divider ratio is assumed, not frozen.** Every cost estimate in `audio.md`
   and `modplayer.md` is quoted against 2.098 MHz, i.e. ÷12. `graphics.md` §11 shows VRAM
   read-back closing at ÷12 and *not* at ÷8, so ÷8 is not a free speed switch — it costs
   the read path. The default should be stated here rather than inferred from arithmetic.

5. **Backplane or single board?** Every card document assumes slots and a `/IOSEL`, but
   nothing states how many slots, what the connector is, or whether the CPU module is a
   card or the motherboard.

6. **LQFP48 vs LQFP64 for the CPU module.** `graphics.md` §6.3 recommends the LQFP64 part
   for the homebrew card, because the MMU needs a second store for A16–A19.
   `cpu/docs/plan.md` §3.2 closes the pin budget on the LQFP48 — but for the *CoCo 3*
   drop-in, which has no MMU of its own to emulate at that width.

   > **Decided: LQFP48, with the MMU moved off the CPU — `graphics.md` §6.3.1.**
   > `graphics.md` §6.3's own closing paragraph always carried the alternative — a 15 ns
   > 2K×8 SRAM addressed by `{TASK, A15..A13}`, a `'574` for task and enable, and a write
   > decode, **3 ICs on the motherboard** — but recorded it as a thing you might want
   > rather than as the answer, and this document did not carry it at all. It is the
   > answer.
   >
   > **The deciding argument is one SKU, not one board.** An in-CPU MMU makes the CoCo 3
   > drop-in an LQFP48 and this machine an LQFP64: two parts, two pinouts, two board
   > files, two bring-up paths, one firmware. Moving the MMU out returns the four
   > A16–A19 pins and **one STM32G431CBT6 covers both machines**. The 48-pin part is also
   > cheaper and better stocked, which is what a board built in ones and twos actually
   > runs into.
   >
   > **The pin budget is not close.** Against `plan.md` §3.2's 39 usable pins, this
   > machine needs 34 with the external MMU and 38 with the in-CPU one — 5 spare against
   > 1. Nothing else in the machine asks the CPU for a pin: audio, PS/2, serial and
   > storage are all bus cards behind geographic `/IOSEL` with their interrupts
   > wire-ORed onto `/IRQ` and `/FIRQ` (§2, §4). The only pin the CPU module has gained
   > since `graphics.md` §6.3 was written is `graphics.md` §12.2's HSYNC input for the
   > raster-compare timer, and it is needed either way. The 5 spare pins are what buy
   > back `plan.md` §3.2's debug UART and status LED.
   >
   > **Timing is a wash, or slightly better.** The in-CPU version spends ~3–4 core cycles
   > plus a second `STR` *inside* `t_AD`; the external map spends 15 ns of SRAM
   > propagation *after* it, on the motherboard, where `graphics.md` §5.3's
   > self-specified ~160 ns has room.
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
   > and now at the MMU. Nothing here claims the sum is an hour — only that the MMU is
   > no longer a reason to pick a package. **Whoever is counting NitrOS-9 divergence
   > should count it in one place, and nobody is.**
   >
   > **Two wiring consequences**, both now recorded in §2 and §3: the I/O-page decode
   > comes off logical A13–A15, which stay on the motherboard and never reach a slot;
   > and MMU enable and task select move into the MMU's own window rather than needing
   > `$FF90`/`$FF91` decoded.

---

## 6. What each card still owes the machine

Beyond §5, each subsystem's own document carries its open items; these are the ones with
a cross-card dependency.

| Owner | Item | Where |
|---|---|---|
| **machine** | **⚠ Write the MMU register set.** It is now hardware, and two things wait on it: the motherboard's write-decode GAL and the NitrOS-9 patch | §5 item 3, `graphics.md` §6.3.1 |
| **machine** | **Keep a NitrOS-9 divergence ledger** — video registers, interrupt block, MMU. Each is priced individually and nothing sums them | §5 item 6 |
| cpu | Confirm the GIME accepts a 3.3 V `V_OH` from the level buffers | `cpu/README.md` TODO |
| cpu | First silicon measurement, against the recorded predictions | `cpu/docs/plan.md` §5 |
| video | Bench the dot path and fit the sequencer GALs *before* layout | `graphics.md` §18 steps 1–2 |
| audio | Freeze §9's register map — it is the deliverable, ahead of any board | `audio.md` §15 step 0 |
| audio | The MCU bring-up card, which is what proves the register map | `audio.md` §12.5 |
| io | Measure the PS/2 protocol on a scope; add a reference document to `reference/` | `ps2.md` §13 step 1, §14 item 1 |
| io | **Measure NitrOS-9's interrupt dispatch cost** — it decides whether the FIFO comes back | `ps2.md` §14 item 3, §13 step 8 |
| io | Source an `R6551A` or `G65SC51` — the in-production `W65C51N` is defective for this use | `serial.md` §3.3, §13 item 5 |
| io | Confirm whether NitrOS-9's `sc6551` exists; it is the card's entire software cost | `serial.md` §13 item 2 |
| **cpu** | **⚠ Settle `TFM`'s interrupt/resume behaviour from silicon.** `plan.md` §7 already listed it; the storage card's correctness now depends on it too | `sdcard.md` §4, §13 item 1 |
| storage | A NitrOS-9 `RBF` driver — larger than the card. Evaluate matching CoCoSDC's map to inherit one | `sdcard.md` §13 item 4 |
