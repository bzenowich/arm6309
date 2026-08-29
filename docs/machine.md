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
| **I/O** | PS/2 and serial — **not specified** ([`io/`](../io/)) |

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
| `$FF50`–`$FF5F` | 16 B | disk controller | *reserved, unclaimed* — `graphics.md` §17 |
| `$FF60`–`$FF7F` | 32 B | **video** | *taken* — `graphics.md` §13 |
| `$FFA0`–`$FFAF` | 16 B | **MMU**, GIME-compatible | in the CPU module — `graphics.md` §6.2 |

**There is no window for PS/2 or serial.** See §5.

---

## 4. Interrupts

| Line | Owner | Source |
|---|---|---|
| `/IRQ` | **video** | VBL, and raster compare — `graphics.md` §12. VBL is NitrOS-9's system tick. |
| `/FIRQ` | **audio, and audio alone** | the on-card tempo timer — `audio.md` §8.1 |
| `/NMI` | unassigned | |

`audio.md` §8.1 takes `/FIRQ` as the **sole** source specifically so that there is no
polling chain in the replayer's interrupt path, and `graphics.md` §17 agrees the
ownership should be recorded here rather than left to first-come. It now is.

The consequence is that **both maskable lines are claimed**, which is the first thing
an I/O card runs into. See §5.

---

## 5. Open items — this document's own

These are not deferred details; each one blocks a board.

1. **No I/O window for PS/2 or serial.** §3's map has `$FF50`–`$FF5F` pencilled in for a
   disk controller and nothing else free inside the `$FF40`–`$FF7F` geographic decode.
   Either widen the decode again, subdivide `$FF50`–`$FF5F`, or put the I/O card
   somewhere else entirely. Decide before the backplane is laid out, not after.

2. **No interrupt line for an I/O card.** §4 gives `/IRQ` to video and `/FIRQ` to audio
   as sole owner. A PS/2 keyboard wants an interrupt; polling it from the VBL tick is a
   real option at 50–70 Hz and should be *chosen*, not defaulted into. `/NMI` is free and
   is almost certainly the wrong answer.

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
