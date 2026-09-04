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
| **MMU** | inside the CPU module, GIME-register-compatible — `graphics.md` §6.2 |
| **Address space** | 64 KB logical, MMU-mapped; 1 MB physical (A0–A19) |
| **System master clock** | one 25.175 MHz oscillator, on the motherboard — `graphics.md` §5 |
| **E rate** | 25.175 / 12 = **2.0979 MHz**, software-selectable to ÷8 = 3.1469 MHz |
| **OS target** | NitrOS-9 Level 2 |
| **Video** | 640×200 × 256 colours, VGA out, ~33 ICs ([`video/`](../video/)) |
| **Audio** | 4-channel 8-bit PCM, Paula-exact, 35 ICs ([`audio/`](../audio/)) |
| **I/O** | PS/2 keyboard + mouse, 9 ICs, on `/IRQ` — **specified** ([`io/ps2/`](../io/ps2/)). Serial not started. |

Note the two CPU targets, which are different machines and are easy to confuse:

| | **CoCo 3 drop-in** | **this machine** |
|---|---|---|
| Socket | a real CoCo 3's 40-pin CPU socket | a board you design |
| E | 0.895 / 1.79 MHz, from the GIME | 2.0979 / 3.1469 MHz, from the ÷12/÷8 divider |
| `t_AD` deadline | **110 ns, fixed by the datasheet** | ~160 ns, self-specified (`graphics.md` §5.3) |
| Video / audio | GIME | the cards in this repo |
| MMU | GIME's, emulated | the CPU module's own |

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
is the video card's 512 KB ring (`graphics.md` §6.2).

---

## 3. The `$FF` I/O map

Geographic decode spans **`$FF40`–`$FF7F`** (`graphics.md` §17 — widened from
`$FF60`–`$FF7F` deliberately, because it is a decode term today and a board respin
later).

| Window | Size | Owner | Status |
|---|---|---|---|
| `$FF40`–`$FF4F` | 16 B | **audio** | *proposed* — `audio.md` §9.1 |
| `$FF50`–`$FF53` | 4 B | **PS/2 keyboard + mouse** | *proposed* — `io/ps2/docs/ps2.md` §3.2 |
| `$FF54`–`$FF5F` | 12 B | disk controller | *reserved, unclaimed* — `graphics.md` §17, less the 4 bytes above |
| `$FF60`–`$FF7F` | 32 B | **video** | *taken* — `graphics.md` §13 |
| `$FFA0`–`$FFAF` | 16 B | **MMU**, GIME-compatible | in the CPU module — `graphics.md` §6.2 |

**PS/2 now has a proposed window; serial still has none.** See §5.

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

1. **No I/O window for PS/2 or serial.** §3's map has `$FF50`–`$FF5F` pencilled in for a
   disk controller and nothing else free inside the `$FF40`–`$FF7F` geographic decode.
   Either widen the decode again, subdivide `$FF50`–`$FF5F`, or put the I/O card
   somewhere else entirely. Decide before the backplane is laid out, not after.

   > **A proposal is on the table.** [`io/ps2/docs/ps2.md`](../io/ps2/docs/ps2.md) §3.2
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

3. **The MMU register set is not written down.** `graphics.md` §6.2 says
   "GIME-register-compatible, `$FFA0`–`$FFAF`, 8 blocks, two task registers, 6-bit block
   numbers" and stops there. `graphics.md` §18 step 0 lists it as an exit criterion.
   Nothing in `cpu/` implements it yet — Phase 1 is the timing spike and has no MMU.

4. **The E/Q divider ratio is assumed, not frozen.** Every cost estimate in `audio.md`
   and `modplayer.md` is quoted against 2.098 MHz, i.e. ÷12. `graphics.md` §11 shows VRAM
   read-back closing at ÷12 and *not* at ÷8, so ÷8 is not a free speed switch — it costs
   the read path. The default should be stated here rather than inferred from arithmetic.

5. **Backplane or single board?** Every card document assumes slots and a `/IOSEL`, but
   nothing states how many slots, what the connector is, or whether the CPU module is a
   card or the motherboard.

6. **LQFP48 vs LQFP64 for the CPU module.** `graphics.md` §6.2 recommends the LQFP64 part
   for the homebrew card, because the MMU needs a second store for A16–A19.
   `cpu/docs/plan.md` §3.2 closes the pin budget on the LQFP48 — but for the *CoCo 3*
   drop-in, which has no MMU of its own to emulate at that width.

---

## 6. What each card still owes the machine

Beyond §5, each subsystem's own document carries its open items; these are the ones with
a cross-card dependency.

| Owner | Item | Where |
|---|---|---|
| cpu | Confirm the GIME accepts a 3.3 V `V_OH` from the level buffers | `cpu/README.md` TODO |
| cpu | First silicon measurement, against the recorded predictions | `cpu/docs/plan.md` §5 |
| video | Bench the dot path and fit the sequencer GALs *before* layout | `graphics.md` §18 steps 1–2 |
| audio | Freeze §9's register map — it is the deliverable, ahead of any board | `audio.md` §15 step 0 |
| audio | The MCU bring-up card, which is what proves the register map | `audio.md` §12.5 |
| io | Measure the PS/2 protocol on a scope; add a reference document to `reference/` | `ps2.md` §13 step 1, §14 item 1 |
| io | **Measure NitrOS-9's interrupt dispatch cost** — it decides whether the FIFO comes back | `ps2.md` §14 item 3, §13 step 8 |
| io | Decide whether serial is a period RS-232 port (~14 ICs) or a fast host link (~5) | `io/serial/README.md` |
