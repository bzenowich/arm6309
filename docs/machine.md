# The Machine

## What Is Frozen, What Is Merely Proposed, and What Nobody Has Decided

**Question this answers:** the project has a CPU module plan
([`cpu/docs/plan.md`](../cpu/docs/plan.md)) and six card specifications
([`video/docs/graphics.md`](../video/docs/graphics.md),
[`audio/docs/audio.md`](../audio/docs/audio.md),
[`io/ps2/docs/ps2.md`](../io/ps2/docs/ps2.md),
[`io/serial/docs/serial.md`](../io/serial/docs/serial.md),
[`storage/docs/sdcard.md`](../storage/docs/sdcard.md),
[`net/docs/net.md`](../net/docs/net.md)), and each of them has, as **step 0 of its
own build order**, "freeze the machine spec". None of them can do that, because the
machine spec is the thing that spans them. This document is where that lives.

**Status: assembled, not frozen.** Most of §§1–4 is copied from a card document that
already committed to it, with the citation. §5 is the list of things that are genuinely
undecided, or that this document has had to decide itself.

> **This document mostly reports rather than invents.** Where a card spec says "propose"
> rather than "take", it is recorded here as a proposal. Where two documents disagree,
> the disagreement is recorded rather than resolved. But some things belong to the
> machine and to no card — chief among them that the machine as originally collated
> **could not execute its first instruction** — so this document does decide, in a
> handful of marked places: the boot and vector story (§7), the `/IOPAGE` inhibit (§2),
> system RAM (§7.1), and the E rate (§1). Each is written as a decision, with its
> rationale. Everything else only reports.

> Superseded material — struck values, amendment trails, and revision narratives — is
> archived in [history.md](history.md); this document describes only the present design.

---

## 0. The machine in one table

| | |
|---|---|
| **CPU** | HD6309E in native mode, synthesised on an **STM32G431CBU6** ([`cpu/`](../cpu/)) — UFQFPN48 (§5 item 6) |
| **Boot** | **a 1 MB boot ROM on the motherboard** — 2 ICs plus one `'541`, at physical 2.0–3.0 MB, holding the boot monitor **and a read-only ROM disk with the whole NitrOS-9 distribution in it** — §7.2. ⭐ It also serves `$FFC0`–`$FFFF`, so the vectors are where a 6809 expects them |
| **MMU** | **on the motherboard: 5 ICs, the SAM/GIME/DAT arrangement** — `graphics.md` §6.3.1. Register set is a free design, not GIME-compatible (§5 item 3) |
| **Address space** | 64 KB logical, MMU-mapped; **32 MB physical (A0–A24)** — 16-bit map entries, `hardware/ram.md` §5.2. ⚠ **`A21`–`A24` stay on the motherboard**; the backplane carries `A0`–`A20` |
| **System RAM** | **four 30-pin SIMM sockets, 4–16 MB of DRAM** — `hardware/ram.md` §6. **No SRAM anywhere on the motherboard**, and since §7.2 that costs nothing: boot is twenty stackless instructions in ROM — `ram.md` §6.4 |
| **System master clock** | one 25.175 MHz oscillator, **on the motherboard** — §1 |
| **E rate** | 25.175 / 12 = **2.0979 MHz**. This is the only rate the machine is specified at; ÷8 is experimental — §1 |
| **OS target** | NitrOS-9 Level 2 |
| **Video** | 640×200 × 256 colours, VGA out, **8×8 tile mode and a display list** — **27 ICs**, the programmable logic being **2 × `ATF1508AS` PLCC-84 + 1 × `GAL22V10`** ([`video/`](../video/), `graphics.md` §14.1) |
| **Audio** | 4-channel 8-bit PCM, Paula-exact, **with programmable per-channel panning** — **31 ICs**, one `ATF1508AS` PLCC-84 ([`audio/`](../audio/), `audio.md` §10.1). Output on a **3.5 mm stereo jack** on the card's own rear edge, and on the backplane pair |
| **I/O** | PS/2 keyboard + mouse, **11 ICs** ([`io/ps2/`](../io/ps2/)); RS-232 serial, **3 ICs** ([`io/serial/`](../io/serial/)). Both on `/IRQ`, both **specified** |
| **Storage** | SD card over SPI, **14 ICs**, **681 KiB/s** sustained — **specified** ([`storage/`](../storage/)). Its block buffer lives in `A20 = 1` (§5 item 7), which is what retired the `TFM` re-read hazard. ⚠ The first of the machine's two period exceptions |
| **Network** | 10BASE-T with no MAC or PHY chip, **12 ICs**, two of them `ATF1508AS` — **specified** ([`net/`](../net/)). The second period exception. ⚠ **56 % of the wire**, because a `TFM` at 2.0979 MHz is 681 KiB/s and 10BASE-T is 1221. Ported from `~/code/applenet` |
| **Total silicon** | **115 ICs** — **98 on cards**, **17** on the motherboard plus four SIMM sockets (`hardware/ram.md` §6.5). See §8 |

Note the two CPU targets, which are different machines and are easy to confuse:

| | **CoCo 3 drop-in** | **this machine** |
|---|---|---|
| Socket | a real CoCo 3's 40-pin CPU socket | a board you design |
| E | 0.895 / 1.79 MHz, from the GIME | 2.0979 MHz, from the ÷12 divider |
| `t_AD` deadline | **110 ns, fixed by the datasheet** | ~160 ns, self-specified (`graphics.md` §5.3) |
| Video / audio | GIME | the cards in this repo |
| MMU | GIME's, emulated | 5 ICs on the motherboard — `graphics.md` §6.3.1 |
| Boot | the CoCo's own ROM | **a 1 MB ROM on the motherboard** — §7.2 |

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

**The oscillator is on the motherboard, not the video card, deliberately**: if the can
sat on the video card, pulling that card would kill E and stop the CPU — fatal for
exactly the bring-up sequences that run *before* video exists (`sdcard.md` §12,
and any serial-first DriveWire link — [`drivewire.md`](drivewire.md)). The card
receives the master clock from the backplane, which §2 carries.

### 1.1 ÷12 is the machine's rate. ÷8 is experimental.

> **Decided 2026-09-04 — [`design-review.md`](design-review.md).** Three independent
> things break at ÷8, in three different subsystems:
>
> | Subsystem | At E = 3.1469 MHz | Source |
> |---|---|---|
> | **video** | VRAM read-back does not close | `graphics.md` §11 |
> | **serial** | 57 % over a 2 MHz R6551A's rating; only a genuine 4 MHz G65SC51 covers it | `serial.md` §3.3 |
> | **CPU** | 317.8 ns is **below the HD63C09E's 333 ns `t_cyc` minimum** — so the real part is out of spec, and the silicon A/B reference `plan.md` §6.2 depends on cannot even be captured at this rate | `plan.md` §3.3 |
> | storage | burst margin falls 2.25× → 1.5×, still passes | `sdcard.md` §5 |
> | audio | unaffected — the card runs from its own crystal | `audio.md` §4.1 |
>
> **The machine is specified at ÷12.** ÷8 remains implementable and the divider still
> supports it, but it is an experiment a builder opts into with the video read path and
> the ACIA understood, not a speed switch software may throw. Every cost estimate in
> `audio.md` and `modplayer.md` is quoted against 2.098 MHz and stands.

**Naming.** ÷8 is **fast-E mode**. `/WAIT` is a **wait state** — it holds E. Neither is
called "stretch": those are two opposite things, and they share no word.

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
| `/IOSEL` | **the `$FF00`–`$FF7F` window strobe, common to every slot** — not a geographic per-slot select; see below |
| `/IOPAGE` | **open-drain, motherboard-driven — asserted for the whole of any logical `$FF00`–`$FFFF` cycle**, and for any access above the bottom 2 MB; see below |
| `/WAIT` | open-drain — here it means **hold E** (never "stretch"). Driven synchronously to `CLK25` — the rule in §5 item 8 |
| `/IRQ` | open-drain |
| `/FIRQ` | open-drain — colormin's backplane reserved only `/IRQ`; NitrOS-9 uses both |
| `/NMI`, `/RESET` | `/RESET` is generated on the motherboard — §2.1 |
| `/HALT` | tied high on the motherboard — §2.1. In the CPU module's pin budget (`graphics.md` §6.3.1) |
| `E`, `Q`, `R/W` | not colormin's `16M`/`8M`/`/MRD`/`/MWR` |
| 25.175 MHz master | so any card can phase-lock to video |
| `HSYNC`, `VSYNC` | `graphics.md` §12.2's raster-compare timer counts HSYNC, and counting HSYNC gives a line number with no origin unless VSYNC (or an equivalent frame reset) comes with it |
| Audio `L`, `R` + 2 grounds | carried per `graphics.md` §17 |
| `A0–A18`, `A19`, `A20` | **physical**, not logical A0–A15 — the video card needs the translated address. `A20` rides slot position A34, the position that was the backplane's one spare (§5 item 1 D) |
| `D0–D7` | |

**`A24..A19` selects a 512 KB quadrant of a 32 MB map** —
[`hardware/ram.md`](../hardware/ram.md) §5.2:

| `A24..A19` | Range | 512 KB |
|---|---|---|
| `000000` | 0.0–0.5 M | **reserved** — nothing answers here, and nothing needs to since §7.2 |
| `000001` | 0.5–1.0 M | the video card's ring (`graphics.md` §6.3) |
| `00001x` | 1.0–2.0 M | **card buffers — 16 regions of 64 KB** (§5 item 7) |
| `00010x` | **2.0–3.0 M** | ⭐ **the boot ROM — 1 MB, read-only** (§7.2) |
| `00011x` | 3.0–4.0 M | reserved |
| `001xxx`–`100xxx` | **4–20 M** | **four 4 MB SIMM windows — all of system RAM** (`ram.md` §6) |
| `101xxx`–`111xxx` | 20–32 M | reserved |

**`VRAM` sits at `A20:A19 = 01` and the card regions at `A20 = 1`.**
`gal/clkdec.pld`'s `ramsel` and `gal/vctrl.pld`'s `VRAMSEL` decode the bottom 2 MB; the
quadrants above it are decoded by a motherboard GAL (`ram.md` §6.2).

> ### ⭐ `/IOPAGE` is redefined, and every card author has to know
>
> **`A21`–`A24` never reach a slot.** A card decodes `A0`–`A20`, so an access at 2.5 MB
> would look to it exactly like one at 0.5 MB — and giving every card four more address
> pins is four the backplane has not got, on a video card whose `vaddr` is at 61 of
> 64 I/O with JTAG reserved — three free, against the four.
>
> **`/IOPAGE` solves it for nothing.** It is open-drain and this section already requires
> every physical decode on every card to qualify against it, so the motherboard simply
> **pulls it low for any access above the bottom 2 MB** and every card goes silent.
>
> **So `/IOPAGE` does not mean "the `$FF00`–`$FFFF` page". It means "cards must not
> respond to this cycle."** It always did the second thing; the I/O page was just the
> first reason it had to. **A card qualifies against it and asks no further questions.**

**Physical A13–A19 come from the motherboard's MMU, not from the CPU** (§5 item 6,
`graphics.md` §6.3.1). Two consequences for whoever draws the backplane:

- **Logical A13–A15 stay on the motherboard and do not appear on a slot.** They are the
  map SRAM's address inputs. Nothing on a card has any business seeing them.
- **The `$FF00`–`$FFFF` I/O-page decode is taken from those logical lines**, so that the
  I/O page overrides translation exactly as it does on a CoCo 3. A0–A12 are untranslated,
  making the term `(logical A15..A13 = 111) AND (A12..A8 = 11111)` — the same term that
  already gates `/IOSEL`, so it costs nothing, but it has to be drawn that way.

### ⚠ `/IOPAGE`, and why the backplane needs the inhibit

> **Decided 2026-09-04 — `design-review.md` §Sys-M1 and §Vid-C2.**
>
> Without the inhibit: during any `$FFxx` access the map SRAM keeps emitting a
> *translated* physical A13–A19 onto the backplane, and nothing gates it. System RAM and
> VRAM decode that physical address. So whatever the current task's block 7 happens to
> map to, **RAM or VRAM sees a perfectly valid memory cycle at the same moment as the
> addressed I/O card**:
>
> - on a **read** of `$FF40` or `$FF50`, two devices drive `D0–D7` — a real electrical
>   conflict, not a logical one;
> - on a **write** to any I/O register, a byte is *also* silently written into some
>   translated RAM or VRAM location.
>
> And this is not an exotic configuration. `graphics.md` §6.3 explicitly allows any of the
> eight MMU blocks to point at VRAM, so a graphics process with `$E000`–`$FFFF` mapped
> there puts a VRAM address on the backplane during **every** I/O access it makes.
>
> The term that identifies an I/O cycle already exists on the motherboard — it is what
> gates `/IOSEL`. So: **`/IOPAGE` is that term, brought to the backplane**, and
>
> - **every physical-memory decode must qualify against it.** System RAM's `/CS` and the
>   video card's VRAM select respond only when `/IOPAGE` is high.
> - **the map SRAM's outputs are gated by it too**, so physical A13–A19 are parked at a
>   defined value during I/O cycles instead of carrying a stale translation. This also
>   answers what those lines carry during a map-write cycle.
>
> No card could compute this inhibit for itself, because §2 keeps logical A13–A15 on the
> motherboard and off every slot. One wire, one sentence — **and a wrong board without
> it.**

### `/IOSEL` is a window strobe, not a geographic select

> **Decided 2026-09-06** ([`hardware/README.md`](../hardware/README.md) finding 2);
> the window itself is §5 item 1 A.
>
> In colormin, `/IOSEL` really is geographic: `~/code/colormin/docs/backplane.md` §3
> gives each of four slots its own identical **64-byte** window, decoded by slot
> position on a common pin — which card sits in which slot *is* the address decode.
> **This machine's windows are function-sized, not slot-sized, and no two are alike**:
> audio 16 bytes, video 32, PS/2 + serial 8, storage 4, net 4 (§3). Decode by position
> cannot produce them, and it would nail each card to exactly one slot — at which point
> the base-address jumper each card promises selects nothing.
>
> **The decision: `/IOSEL` is the `$FF00`–`$FF7F` window strobe, common to every slot.**
> It is the `/IOPAGE` term above, further qualified by `/A7` — one product term on a
> decode the motherboard already forms. **A card completes its own decode from `A0`–`A6`
> against its jumpered base**, which is what `A0`–`A6` are on the backplane *for*.
> Seven bits, not six: with `A6` outside the strobe, a six-bit card answers at its base
> **and 64 bytes below it** — two cards on `D0`–`D7`, silently.
> `hardware/lib/cards.check.ts` asserts the seven bits.
>
> ⚠ **What it costs, stated because it is a real loss.** A slot number means nothing to
> the address decode, so **nothing prevents two cards being jumpered to the same base,
> and nothing detects it.** In colormin that collision was impossible by construction.
> Here it is a build error that presents as two cards driving `D0`–`D7` at once — the
> same failure mode `/IOPAGE` was added to prevent, from a different cause. The
> alternative that keeps the geography — a per-slot base/size comparator on the
> motherboard — is recorded at §5 item 1 C, and is the shape the answer takes if the
> map is ever made software-configurable.
>
> **"Geographic" survives as the name of the `$FF00`–`$FF7F` range**, here and in five
> other documents, and that is harmless. It is a name, not a mechanism.

### 2.1 Electrical

Machine-level electrical facts that no single card owns (`design-review.md` §Sys-M4):

| | |
|---|---|
| **Bus voltage** | **5 V TTL.** The CPU module is 3.3 V and fronts this bus through its own `'541`/`'245` buffers (`plan.md` §2.6/§3.2), which were specified for the CoCo 3 socket and apply here identically |
| **Power-on reset** | **on the motherboard.** A supervisor (DS1233-class) or an RC + Schmitt inverter, driving backplane `/RESET`. Every card takes `/RESET` as an input |
| **`/HALT`** | tied high on the motherboard through 4.7 kΩ, as the CoCo does (`plan.md` §2.6). Nothing in this machine drives it; saying so is the point |
| **Open-drain pull-ups** | `/IRQ`, `/FIRQ`, `/WAIT`, `/NMI`, `/IOPAGE` — **on the motherboard**, 3.3 kΩ. Four cards declare open-drain outputs; the resistors live here |
| **Data-bus loading** | `D0–D7` sees the CPU's `'245`, the video card's `'245`, audio's `'245`, two PS/2 `'595`s, the 6551, storage's `'595`, and system RAM — **eight or more loads before any expansion.** Within HC/HCT fan-out, but it is why the backplane wants short traces and it should be counted, not assumed |

---

## 3. The `$FF` I/O map

Geographic decode spans **`$FF00`–`$FF7F`** (§5 item 1 A): `/IOSEL` is
`/IOPAGE · /A7`, one literal.

> ⚠ **The cost is on the cards, and it is mandatory.** With `A6` out of the strobe, a card
> that matches only `A0`–`A5` answers **twice** — at its base and 64 bytes below it.
> **Every card decodes `A0`–`A6`.** `hardware/gal/vctrl.pld` is the one card decode that
> exists in this repository and it carries the seven bits;
> `hardware/lib/cards.check.ts` asserts them so the next card cannot inherit the
> old habit from a sibling document.

| Window | Size | Owner | Status |
|---|---|---|---|
| `$FF00`–`$FF3F` | **64 B** | **free** | the machine's entire margin |
| `$FF40`–`$FF4F` | 16 B | **audio** | *proposed* — `audio.md` §9.1 |
| `$FF50`–`$FF57` | **8 B** | **I/O — PS/2 keyboard, mouse and RS-232, one card** | *proposed* — `ps2.md` §3.2 + `serial.md` §7.1 |
| `$FF58`–`$FF5B` | 4 B | **SD card storage** | *proposed* — `storage/docs/sdcard.md` §6.1 |
| `$FF5C`–`$FF5F` | 4 B | **network** | *proposed* — [`net/docs/net.md`](../net/docs/net.md) §5.1 |
| `$FF60`–`$FF7F` | 32 B | **video** | *taken* — `graphics.md` §13 |
| `$FFA0`–`$FFAF` | 16 B | **MMU block registers** | 16 entries, index = `A3..A0` = `{TASK, block}`. Bits 7–0 are physical `A20..A13` — `hardware/gal/README.md` |
| `$FFB0`–`$FFBF` | 16 B | **MMU and boot control** | **two bytes, aliased 8× each on the address's parity**: `$FFB0` even is `TASK`, `$FFB1` odd is **`BOOT`** (§7.2). One literal — `A0` — and no more; decoding the sixteen bytes apart would cost four GAL inputs U3 has not got |
| `$FFC0`–`$FFFF` | 64 B | ⭐ **the boot ROM's vector page** | §7.2 — the ROM answers here unconditionally, so `$FFFE` is a reset vector and not an undriven bus. **The one region of the I/O page that is not I/O** |

> **`$FFA0`–`$FFAF` holds the sixteen block registers and nothing else**
> (`hardware/gal/README.md`):
>
> - **Sixteen block registers need all sixteen bytes**, so nothing else can share them.
>   **Nothing in this machine decodes `$FF80`–`$FF9F`**; `$FF90`–`$FF9F` was the CPU
>   module's vector RAM until §7.2 put the vectors in the boot ROM, and it is free.
> - **There is no MMU enable.** The map SRAM's outputs *are* physical `A13–A20` with no
>   bypass path, so "disabled" would mean floating the address bus — which is
>   *precisely* what §7.2's `BOOT` mode does, deliberately, with the `'541` driving in
>   the map's place. **`BOOT` is the bypass**, and it is one bit at `$FFB1` rather than
>   a mode inside the MMU.
> - **`BOOT` is a motherboard latch and can be**, because it gates motherboard logic and
>   nothing else. That is the difference from the shadow-ROM disable §7.2 retired, which
>   had to live inside the CPU module because all 40 pins of a 6809E socket are defined
>   and no wire could carry the bit out.
>
> What is left is `TASK` and `BOOT`, and it is why the control window holds two bits.

### The map has 64 bytes free

16 + 4 + 4 + 4 + 4 + 32 = **64** allocated, in a window of 128; the free 64 are
`$FF00`–`$FF3F`. `hardware/lib/cards.check.ts` prints the margin on every run, and it
prints how it was got.

**`$FF00`–`$FF3F` holds a second serial port, a third PS/2 port and a floppy
controller at once**, with room over. What it does not hold is a *buffer* — §5 item 1
option D is the half of that decision that answers `sdcard.md` §11.1 and `net.md` §7.6,
and it is a different address space entirely.

---

## 4. Interrupts

| Line | Owner | Source |
|---|---|---|
| `/IRQ` | **shared, open-drain** | video's VBL and raster compare — `graphics.md` §12. VBL is NitrOS-9's system tick. **PS/2 is a third source** — `io/ps2/docs/ps2.md` §3.1. **Serial a fourth** — `serial.md` §6. **Net a fifth** — `net/docs/net.md` §6, and it is the only source that can out-rate VBL |
| `/FIRQ` | **audio, and audio alone** | the on-card tempo timer — `audio.md` §8.1 |
| `/NMI` | unassigned | and should stay that way — a non-maskable I/O source would pre-empt the replayer tick |

`audio.md` §8.1 takes `/FIRQ` as the **sole** source specifically so that there is no
polling chain in the replayer's interrupt path, and `graphics.md` §17 agrees the
ownership should be recorded here rather than left to first-come.

**The two lines are not symmetric, and the difference is the whole answer for I/O.**
`/FIRQ` is exclusive by design. `/IRQ` was never exclusive — it has carried two sources
since `graphics.md` §12, its handler already polls, and further sources are what the
line is for.

### 4.1 The polling order is part of the specification

> **Decided 2026-09-04 — `design-review.md` §Sys-M3; the fifth source added 2026-09-07
> (`net.md` §6).** The sources on `/IRQ` keep their status in different cards'
> registers (`VSTAT $FF73`, `IOSTAT $FF52`, the 6551's `STATUS $FF55`, net's status,
> and raster compare inside the CPU module). There is no consolidated pending register
> anywhere. That leaves the dispatcher polling, and **the order is not free**, because
> one of the sources is destructive to read:
>
> **1. video `VSTAT`  →  2. net  →  3. PS/2 `IOSTAT`  →  4. serial `STATUS` (last,
> always).**
>
> Video first because VBL is the system tick and by far the most frequent source. Net
> second because its status read has no side effects at all and because under load it is
> the machine's most frequent source after VBL. Serial **last** because reading the
> 6551's `STATUS` **clears the interrupt and returns the error bits in the same read**
> (`serial.md` §7.3) — a dispatcher that probes serial early, decides it was not the
> source and moves on has already destroyed the overrun and framing bits that the serial
> handler needed. The serial handler must therefore consume its errors on that single
> read rather than probe-and-defer.
>
> ⚠ **This order is correctness-driven, not frequency-driven, and the two orders
> disagree.** `net.md` §3.4 puts the net card at up to ~6,100 interrupts/s and serial at
> 19,200 baud at 1,920, against VBL's 50–70 and PS/2's human rate — so the frequency
> ordering would be *serial, net, video, PS/2*, nearly the reverse. The specified order
> is still right, because the 6551's destructive `STATUS` read is a correctness matter
> and polling cost is not; but the cost of the disagreement is paid on every dispatch.
>
> The alternative — the CPU module serving a read-only consolidated pending register,
> for zero ICs, since it already owns raster compare — is **not** taken: it adds a
> NitrOS-9 divergence to a ledger nobody is yet keeping (§5 item 6), where the polling
> order costs nothing but a documented sentence.

**Nothing masks `/IRQ` or `/FIRQ` for long, with exceptions that must be read
together**, because they are the machine's only interrupt-latency budget and they live in
different documents:

| Masked window | Duration | Consequence |
|---|---|---|
| `sdcard.md` §4.4 — a chunked TFM sector transfer | 49 µs per chunk | 0.25 % of the replayer's 20 ms tick; `/FIRQ` is delayed, not lost, because the source is level-held. VBL is latched in `VSTAT` and survives |
| `graphics.md` §7.4 — a maximal span-solid, with the CPU touching VRAM | **up to 40.7 µs** | holds `E`, so it holds interrupt dispatch too. **Avoidable entirely** by polling `VSTAT` b7 first — §5 item 10 |
| `ps2.md` §7 — a host-to-device transmit (keyboard LEDs, mouse enable) | **~0.8–1.3 ms per frame** | ⚠ Longer than the 6551's 521 µs inter-byte deadline at 19,200 baud, so **an LED update during a download guarantees a serial overrun** — `design-review.md` §IO-P4. **And 1.06 maximum-size Ethernet frames of arrival**, which is why `net.md` §3.3 sizes the net card's RX ring at four banks rather than two |
| `net.md` §3.2 — a chunked masked `TFM` drain of a received frame | 49 µs per chunk | the same window `sdcard.md` opens, from the same instruction and the same cause. **Two cards depend on `TFM`'s resume behaviour** — §6 |

---

## 5. Open items — this document's own

Each of these blocked a board when it was opened. The closed ones record their
decisions here, because other documents cite them by item number.

1. **⚠ CLOSED 2026-09-08. The I/O window is 128 bytes, and physical `A20` gives cards
   a second megabyte** — since re-carved into the 32 MB map of §2 (`ram.md` §5.2).

   **Two decisions, and the reason this item stayed open so long is that they were
   discussed as one.** There are two shortages under the name "I/O space" and they have
   different answers:

   | | shortage | who feels it | answer |
   |---|---|---|---|
   | **registers** | 64 bytes for six cards' control and status | every card, a little | **A** — widen the window |
   | **buffers** | nowhere to put 512 B, or 8 KB, that the CPU can address | storage and net, a lot | **D** — a second megabyte |

   ### A — the geographic window is `$FF00`–`$FF7F`. Taken.

   `/IOSEL` is `/IOPAGE · /A7` — **one literal fewer than the 64-byte decode it
   replaces** (`gal/clkdec.pld`).

   | | |
   |---|---|
   | **Gained** | 64 bytes at `$FF00`–`$FF3F` — the machine's whole margin, and 16× what it had |
   | **Motherboard cost** | **negative.** One product-term literal removed from U6 |
   | **⚠ Card cost** | **every card must decode `A0`–`A6`, not `A0`–`A5`.** With `A6` out of the strobe, a card matching six bits answers at its base **and 64 bytes below it** — two cards on `D0`–`D7`, silently. `hardware/lib/cards.check.ts` asserts the seven bits; `gal/vctrl.pld` is the one card decode in this repository and it carries them |
   | **Given up** | `$FF00`–`$FF3F` is a CoCo 3's PIA0 and PIA1. Answering at the canonical PIA addresses is impossible — one more line for the divergence ledger item 6 says nobody keeps, and a cheap one: this machine has no PIAs, and PS/2 and serial replaced what they did |
   | **Not extended to `$FF80`–`$FF8F`** | 16 more bytes, but the decode becomes `/A7` **+** `(A7·/A6·/A5·/A4)` — two terms and two more inputs, for a window that is then discontiguous and needs every card to know it. **U6 pin 6 keeps its `LA6` trace precisely so this stays a one-line change**, and it is not taken today |

   ### D — physical `A20`. Taken, and it is nearly free.

   `graphics.md` §6.3 spends the entire original 1 MB physical map — 512 KB system RAM
   at `A19 = 0`, 512 KB VRAM at `A19 = 1` — which is why `sdcard.md` §11.1's 512-byte
   block buffer was refused by *both* maps and why `net.md` §7.6 once spent five
   74-series packages and a prefetch register reaching 8 KB through a four-byte port.

   **The eighth bit was already there.** The map SRAM is byte-wide, the isolation `'245`
   already carries all eight bits, and the block register's bit 7 was already written and
   read back. **It drove nothing.** It is now physical `A20`
   (`hardware/gal/README.md`).

   | | |
   |---|---|
   | **Cost** | **one backplane pin and zero ICs.** Slot position A34, which was the machine's one spare, is `A20`. `mainboard.circuit.tsx`'s map SRAM `DQ7` is `net.A20`; U6 takes it on pin 9 |
   | Decode cost | one literal each on `ramsel` (U6, on a part with spare inputs) and `VRAMSEL` (`gal/vctrl.pld`) |
   | **Gained** | `A20 = 1` — **1 MB for card buffers**, addressed as ordinary memory through the MMU's 8 KB blocks |
   | **⚠ And it retires a hazard** | `sdcard.md` §4's `TFM` re-read corrupts a block because the *port* read pops a byte. `sdcard.md` §4.2 already shows the mirror-image `TFM` against RAM is safe. **A memory-mapped card buffer is idempotent to re-read**, so the chunk-and-mask tax — 21 % on storage, 21 % on net — was a symptom of this shortage and not an independent CPU problem. It does not delete `cpu`'s obligation to settle the behaviour (§6), because a port is still a port; it deletes the two cards' need to care |
   | **⚠ Given up** | **the backplane has no spare pin now, and two things wanted it.** `hardware/README.md` earmarked A34 for a future rail; `net.md` §13.1 wanted **two** pins for a DMA request/grant pair, plus `BA`/`BS` brought out. `A20` beat both on arithmetic — one pin, no ICs, 1 MB — and **that competition is decided, not deferred.** A seventh signal position would now come out of the ground or power allocation, and `lib/slot.check.ts` is what prices that |

   ### What was not taken, and why

   - **B — page the `$FF40` window.** Multiplies the space arbitrarily; **rejected on
     §4.1** — a page write per poll makes the machine's worst interrupt-latency case
     worse to solve its least urgent problem.
   - **C — a per-slot base/size comparator on the motherboard.** The alternative that
     keeps the geography (§2): jumper collisions become impossible and the map
     software-set. **It creates no space**, costs several packages, and needs a window
     of its own. It composes with A and can be taken later on its own merits.
   - **E — index/data indirection per card.** Two bus cycles per register access,
     hostile to exactly the ISR polling §4.1 specifies. A card may choose it; the
     machine will not require it.
   - **F — declare the machine closed.** Six slots, six cards, an exact fit. Honest,
     and unnecessary.

2. **CLOSED — I/O interrupts ride `/IRQ`.**
   [`io/ps2/docs/ps2.md`](../io/ps2/docs/ps2.md) §3.1 takes **`/IRQ`, as a third
   source** — see §4: `/IRQ` is open-drain, already carries VBL and raster compare, and
   its handler already polls. Only `/FIRQ` is exclusive.

   > Cost: **~0.9 % of the CPU while input is actually happening**, zero otherwise.
   > ⚠ That figure assumes 100 cycles of NitrOS-9 interrupt
   > dispatch; at 400 it is 3.4 %. **Unmeasured — `ps2.md` §14 item 3.**
   >
   > `/NMI` is wrong for a keyboard: being non-maskable, a keypress would pre-empt the
   > replayer tick that §4's `/FIRQ` ownership exists to protect.
   >
   > **Serial follows the same call** — `serial.md` §6 puts the 6551's `/IRQ` on the same
   > line as the fourth source. Its §5 shows the cost is what bounds serial throughput: no
   > FIFO means one interrupt per byte, so 19,200 baud is 9 % of the CPU at 100 cycles of
   > dispatch and **37 % at 400** — and that is the *receive* direction alone; full duplex
   > doubles it (`design-review.md` §IO-S3). The practical ceiling is 4800–19,200 baud, and
   > **the same single measurement decides that and whether PS/2's FIFO comes back.**
   >
   > **The order in which the sources are polled is specified — §4.1** — because one of
   > them destroys its own status on read.

3. **CLOSED 2026-09-06 — the MMU register set is written down, and it is hardware.**
   [`hardware/gal/README.md`](../hardware/gal/README.md) carries the map and
   [`hardware/gal/mmu.pld`](../hardware/gal/mmu.pld) the equations that decode it; §3
   above holds the map. **`$FFA0`–`$FFAF` is 16 block registers, `$FFB0`–`$FFBF` is one
   control bit.**

   > It turned out to be barely a free design at all. The `'157` mux already on the board
   > puts `TASK` on `MAPA3` and `LA15..LA13` on `MAPA2..0` while translating, and `LA3..LA0`
   > on the same four lines during a write — so the write index **is** `{TASK, block}` with
   > no permutation, and `$FFA0+n` is task `n>>3`, block `n&7`. The board was drawn that way
   > before anyone wrote it down. There is no enable bit; it ceased to exist (§3).

4. **CLOSED 2026-09-04 — §1.1.** ÷12 is the machine's rate. ÷8 breaks the video read
   path, takes the 6551 57 % over its rating, and is *below the real HD63C09E's `t_cyc`
   minimum* — three subsystems, checked in one place for the first time by the review.

5. **CLOSED 2026-09-06 — backplane, and [`hardware/README.md`](../hardware/README.md)
   is the owning document.** Three decisions came with it and each is checked rather
   than asserted ([`hardware/lib/slot.check.ts`](../hardware/lib/slot.ts)):

   | | |
   |---|---|
   | **Connector** | **72-pin 0.1″ card edge, 2 × 36** — 45 signals, 5 × +5 V, 18 GND, 2 analogue returns, 1 key, **no spare** |
   | **Card format** | **100 mm high × 120, 180 or 240 mm long**, per card — `hardware/place/` draws each board 1 : 1 and `place.check.ts` asserts it takes the shortest length that works |
   | **CPU siting** | **a 40-pin DIP socket on the motherboard**, so the drop-in module `cpu/` already builds is literally the same hardware SKU |
   | **Slots** | **six** — five specified cards plus one spare. ⚠ **Unargued**; `hardware/README.md` open item 5 |

   > ⚠ **What is still open is a smaller question than this item was.** The connector's
   > own justification was derived from a 100 mm Eurocard edge holding 39 positions at
   > 0.1″, and **the card format is no longer a Eurocard** — a 240 mm edge holds 98. So
   > **72 pins is a decision that outlived its argument**: it works, nothing depends on
   > the number, and three things foreclosed by having exactly one spare pin
   > (`net.md` §13.1's DMA request/grant pair, a future rail, and the spare physical
   > `A20` spent) could come back if it were re-specified. **It is not.**
   >
   > §8's supply is amps-scale and the power/ground allocation was decided with the
   > connector: 5 × +5 V at ~1 A per gold finger against a 2–3 A machine, and a ground
   > on both sides of every clock and sync line.

6. **DECIDED — the MMU moves off the CPU, and the module is an `STM32G431CBU6`,
   UFQFPN48.**

   > **The MMU is external** (`graphics.md` §6.3.1): one STM32 SKU covers both machines,
   > the 48-pin part is cheaper and better stocked, and the timing is a wash (the in-CPU
   > version spends ~3–4 core cycles plus a second `STR` *inside* `t_AD`; the external
   > map spends 15 ns of SRAM propagation *after* it, on the motherboard, where
   > `graphics.md` §5.3's ~160 ns has room).
   >
   > **The package is the UFQFPN48**, not the LQFP48 (`design-review.md` §Cpu-C1): the
   > pinout puts `BA` on PC4, `BS` on PC6 and the debug UART on PC10/PC11, and none of
   > those pins is bonded out on the LQFP48 — DS12589 Table 2 gives it 38 GPIO against
   > the UFQFPN48's 42. Same die, same firmware, and the pinout works verbatim.
   >
   > **What is given up, and it was priced rather than deferred.** `graphics.md` §6.3's
   > case for the in-CPU MMU is that faithful `$FFA0`–`$FFAF` emulation is "the
   > difference between porting the memory manager and configuring it". **The owner's
   > call is that patching NitrOS-9 Level 2's memory manager for this machine's own
   > register set is about an hour of work, not a port**, so the register set is a free
   > design — item 3, which is where the work landed.
   >
   > ⚠ **The hour is per-subsystem, and this machine has several.** It diverges from the
   > GIME at the video registers (`graphics.md` §13), at the interrupt block, and at the
   > MMU. Nothing here claims the sum is an hour. **Whoever is counting NitrOS-9
   > divergence should count it in one place, and nobody is.**
   >
   > ⭐ **The list is one item shorter than it was.** It used to carry "the boot ROM and
   > vector page" as a fourth entry, because §7.2's shadow ROM lived inside the CPU
   > module and the vectors were writable RAM at `$FF90`–`$FF9F`. **The motherboard ROM
   > put both where a CoCo has them** — a ROM at `$FFC0`–`$FFFF` pointing at a fixed RAM
   > jump table — so that entry is not reduced, it is deleted.

7. **⚠ DECIDED 2026-09-08 — the megabyte at `A20 = 1` is sixteen regions of 64 KB, and
   the arbitration is a fixed phase rather than a handshake.**

   Item 1's option D created the space. Two cards asked for it within the day —
   `sdcard.md` §11.1's 512-byte block buffer and `net.md` §13.3's ring — so it is
   decided here rather than by whichever card got specified first.

   ### The allocation

   | | |
   |---|---|
   | **Region size** | **64 KB.** The MMU maps in 8 KB blocks, so 8 KB is the floor; 64 KB is chosen because **a region is then exactly one 6309 logical address space** — eight blocks, one `TASK`'s whole map |
   | **How many** | **16**, selected by physical `A19`–`A16` |
   | **How claimed** | a **4-position jumper** per card, compared against `A19`–`A16`. The same mechanism as the `$FF` window's base and with the same known flaw: nothing prevents two cards being jumpered alike and nothing detects it (§2) |
   | **Qualification** | **`/IOPAGE` high, always.** A card buffer is a physical-memory decode and §2's rule is not optional for it — a card answering during an `$FFxx` cycle is the bug `/IOPAGE` exists to prevent |
   | **Below `A16`** | the card's business. `net.md` splits its region `A15 = 0` RX / `A15 = 1` TX; `sdcard.md` uses 2 KB of one |

   ### The arbitration, and why it needs no handshake

   The card's own engine and the host both want the buffer SRAM, and **the host's access
   is a bus cycle the card cannot defer.** The obvious answer is `/WAIT`; it is not the
   one taken.

   **A bus cycle is 476.7 ns and `CLK25` is 39.7 ns, so there are twelve ticks in it.**
   The address is valid at E-fall + `t_AD` = 110 ns and data is wanted by ~437 ns, so the
   host's window is ticks 3–11 and an SRAM access is 2 ticks. **Give the host absolute
   priority in that window and the card's engine a fixed slot outside it**, and the two
   never meet:

   | | needs | gets |
   |---|---|---|
   | host access | 2 ticks, anywhere in its 8-tick window | absolute priority |
   | card engine | 2 ticks | **one fixed slot per bus cycle** = 1 byte / 476.7 ns = **2.1 MB/s** |

   2.1 MB/s covers both askers with margin — `net.md`'s framer needs 1.25 MB/s and
   `sdcard.md`'s SPI engine 1.57 MB/s — and it is **deterministic**, which a
   priority arbiter is not. At fast-E the slot rate rises to 3.1 MB/s, so the ÷8
   experiment does not break it either.

   **What each card pays** is one byte of slack: the engine's byte must survive up to one
   bus cycle of deferral. Both already have it — `net.md`'s deserializer output register
   and `sdcard.md`'s `'595` storage register are that byte, and both exist for other
   reasons.

   > **`/WAIT` is not used, and that is deliberate.** It would work, it would cost one
   > stretched cycle per collision, and it would put a card's internal scheduling on the
   > machine's critical timing path. The fixed slot costs nothing and can be verified by
   > reading the schedule. **See item 8 for why this matters more than it looks.**

   ### What a card gives up

   **The buffer is not a port and must not behave like one.** No side effects on read, no
   auto-increment, no read-triggered anything — that is the entire point (`sdcard.md` §4,
   `net.md` §3.2). A card wanting a side-effecting register keeps it in its four bytes of
   `$FF` space, where `TFM` will not land on it.

8. **⚠ FIXED 2026-09-08 — `/WAIT` holds E in U6, and it carries a machine-level rule.**

   [`hardware/gal/vctrl.pld`](../hardware/gal/vctrl.pld) drives `/WAIT` open-drain —
   the video card holding the CPU off VRAM while the span writer runs — and U6's divider
   ([`hardware/gal/clkdec.pld`](../hardware/gal/clkdec.pld)) consumes it: every
   registered macrocell carries a hold term (`Cn.d = next & /WAIT # Cn & WAIT`), +1
   product term each (E is at 8 of 16), input on a free pin, no macrocells spent — and
   U6 has none spare. `clkdec_tb.sv` carries the claims, including *"/RESET beats
   /WAIT"*; Atmel's own CUPL agrees with the fuse map; and `lib/netlist.check.ts`
   asserts that U6 takes the signal, which is what stops a consumerless `/WAIT`
   recurring.

   ⚠ **The machine-level rule: `/WAIT` is driven synchronously to `CLK25`.** `/WAIT`
   gates a counter clocked by `CLK25`; an asynchronous assertion is a metastability
   trap, and the synchroniser would need a macrocell U6 has not got. Every card that
   could drive `/WAIT` already has `CLK25` from the backplane, and the video card's
   `SPANBUSY` is in a `CLK25`-derived domain already, so the rule costs nothing — and
   it is written down here so no card assumes otherwise.

   **Item 7's card buffers do not need `/WAIT`** — their fixed-phase schedule never asks
   for one.

9. **FIXED 2026-09-08 — open-drain output polarity in the GAL toolchain.**

   A cell driving a shared open-drain line uses the no-product-term idiom: it drives a
   constant and the condition rides entirely on the output enable. For a pin declared
   `PIN n = !WAIT` the constant must be `'b'1` — CUPL inverts it — or the pin drives
   **high** whenever the enable is true, fighting the motherboard's 3.3 kΩ pull-up and
   every other card on the wire. Three signals use the idiom — video `/WAIT`, video
   `/IRQ`, audio `/FIRQ` — and all three once had it wrong; `jedec/cupl.ts` and
   `jedec/galpld.ts` now emit `'b'1` for an active-low cell, verified by
   `hardware/gal/jedec/cupl.check.ts` running Atmel's own compiler against our fuse map
   (agreement over all 512 input combinations of the arbiter). Every affected device
   was refitted. The full account, and the lesson about second implementations, is in
   [history.md](history.md).

10. **⚠ BOUNDED 2026-09-08 — a stretched cycle is at most 40.7 µs, and it is one card's
    span writer.**

    Item 8's fix means `E` can stop mid-cycle, and item 7's card buffers count `CLK25`
    ticks *within* a bus cycle. **`graphics.md` §7.4 bounds the stretch**, and the
    length is `WMODE` and nothing else, because the span writer retires one byte per
    158.9 ns fetch slot:

    | `WMODE` | Bytes | `/WAIT` held |
    |---|---|---|
    | direct | 1 | 159 ns |
    | span-mask | 8 | 1.27 µs |
    | **span-solid** | **up to 256** | **up to 40.7 µs** |

    **40.7 µs is longer than a scanline.** It is 85 bus cycles, 2.6 DRAM refresh
    intervals and 51 net framer byte-times. `/WAIT` is also qualified on `R/W`, so
    **reads never wait at all** (`graphics.md` §7.4).

    ### What it settles

    - ⭐ **DRAM refresh is safe** — `hardware/ram.md` §6.6's open question, closed.
      `/WAIT` here is qualified on `VRAMSEL`, so the CPU is stalled *on VRAM* and the
      DRAM bus is idle for the whole 40.7 µs while the refresh controller runs off
      `CLK25`. **They never contend**, and a maximal span is 2.6 refresh intervals of
      free DRAM time.
    - **Interrupt latency gains up to 40.7 µs**, because holding `E` holds dispatch.
      In §4's table; it is the smallest of the three entries there.
    - ⚠ **`net.md` §4.3 starves**, and that is a card-side fix — free-run the framer
      phase on `CLK25` and gate only the host window on `E`.

    ### ⭐ And the rule that generalises it

    > **A card's internal realtime scheduling free-runs on `CLK25`. Only host-facing
    > windows may be derived from `E`.**

    `E` can stop, and stopping it is a thing any card may do. A framer, a serialiser or
    a refresh counter that counts bus cycles has a correctness bug that appears only
    when some *other* card is busy — which is the worst kind. The net card is the one
    that has it today and the rule is written here so the next card does not.

    ### And the practical bound is zero

    `VSTAT` b7 **is** `SPANBUSY`, the read has no side effects, and it is in the I/O
    page — so it does not trigger `/WAIT`. **Software that polls it before touching VRAM
    never stalls the machine**, at a cost of one bus cycle against up to 85. `/WAIT`
    goes back to being the backstop `graphics.md` §3.3 calls it.

---

## 6. What each card still owes the machine

Beyond §5, each subsystem's own document carries its open items; these are the ones with
a cross-card dependency.

| Owner | Item | Where |
|---|---|---|
| **machine** | **Keep a NitrOS-9 divergence ledger** — video registers, interrupt block, MMU, the PIA addresses. Each is priced individually and nothing sums them. ⭐ **It got shorter on 2026-09-08**: §7.2's motherboard ROM put the boot code and the vectors where a CoCo has them, so two entries came off | §5 item 6 |
| **machine** | **Draw the motherboard.** ⚠ **Begun** — [`hardware/`](../hardware/) has the backplane pinout, the motherboard and every card's bus interface, at schematic level. ⚠ **The board file is behind the decisions**: it still draws the 9-IC state with a DIP system RAM, where `ram.md` §6 and §7.2 make it **17 ICs, four SIMM sockets and a 1 MB ROM**. Placement waits on the GAL fitting | §2.1, §7.1, §7.2, [`hardware/README.md`](../hardware/README.md) |
| **machine** | **⚠ RAM expansion — decided, not built.** `hardware/ram.md`: 16-bit map entries, a 32 MB map, four 30-pin SIMM sockets and **no SRAM**, for **five packages, zero backplane pins and zero card changes**. **The boot path it owed is closed** — §7.2's ROM. ⭐ Also: `TASK` widens from 1 bit to 8 **for nothing** — 256 contexts and a one-write process switch | `hardware/ram.md` §5, §6, §10 |
| cpu | Confirm the GIME accepts a 3.3 V `V_OH` from the level buffers | `cpu/README.md` TODO |
| cpu | First silicon measurement, against the recorded predictions | `cpu/docs/plan.md` §5 |
| cpu | **Provision the option bytes** (`nSWBOOT0 = 0`) — PB8 is A8 *and* BOOT0, so an unprovisioned part boots nondeterministically in the socket | `design-review.md` §Cpu-M2 |
| **cpu** | **⚠ Settle `TFM`'s interrupt/resume behaviour from silicon** — and note it is a *choice*, not a discovery, because this machine's 6309 is the project's own firmware. **Two cards wait on it**, and the second one cannot retry a lost frame | `sdcard.md` §4, §13 item 1; `net.md` §3.2 |
| video | Bench the dot path and fit the sequencer GALs *before* layout | `graphics.md` §18 steps 1–2 |
| ~~video~~ | **CLOSED — the video output stage is specified.** `graphics.md` §9.1 is a 1 kΩ/2 kΩ ladder, three NPN emitter followers on a shared `V_be` reference and a 75 Ω series source, with the arithmetic; §9.2 makes blanking a `74AHCT273` `/MR` for zero packages, and §9.3 deletes `BORDER` because VGA has no overscan. **Drawn** in `hardware/cards/video.circuit.tsx` | `graphics.md` §9.1–§9.3, was `design-review.md` §Vid-M4 |
| **video** | **⚠ The list engine clobbers `WPTR`, and that is software's rule to keep.** Sharing the write pointer is what made the display list fit; anything that starts a list reloads `+$08`–`$0A` afterwards, three writes. §10.3 owns the semantics | `graphics.md` §10.1.6.2, §13 |
| **video** | **⚠ Both video CPLDs are out of room.** §6.4.9's cadence and §8.1's window signals took `vctrl` to **64 of 64 I/O — 60 logic pins plus JTAG's four, which the `ATF1508AS` shares with ordinary I/O — and 121 of 128 cells** and `vaddr` to 109 of 128 — both still fit with JTAG reserved, and neither has room for the next thing. §14.2's two ×16 framebuffer parts would return six output pins by making the arbiter 2 grants instead of 8 | `cpld/vctrl.fit`, `graphics.md` §19 item 25 |
| **video** | **⚠ No hardware character generator, and text is two modes not one.** §6.4.3's Variant B is dropped. Text that mixes with graphics or colours per cell is the span writer in bitmap mode at **13 writes/cell** — a scrolled line is 2.5 ms, **3 % of the CPU at 9600 baud**, and a full 80×25 redraw is 62 ms against the 2–4 s a full ANSI screen takes to arrive over the modem. A **one-colour-pair console** is §6.4.8's cell mode instead, at **1 write/cell**, 0.19 ms per scrolled line and 4.8 ms per screen — bounded by 256 (glyph, colour) pairs, 32 cell rows, and a global mode. **Under NitrOS-9 neither is per-window**: §6.4.6's mode is global | `graphics.md` §6.4.3, §6.4.8 |
| **video** | **⚠ The framebuffer and palette go surface-mount.** `graphics.md` §14.2 consolidates seven SRAMs into four — 2 × `AS6C8016-55ZIN` and 1 × `IS61C6416AL-12TLI`, both TSOP-44 II, both stocked, ~$14–21 against ~$36–54 and 205–405 mA lighter. **These are the machine's first SMD parts**; everything else is DIP or a socketed PLCC. That is an assembly decision, not an electrical one | `graphics.md` §14.2 |
| audio | Freeze §9's register map — it is the deliverable, ahead of any board | `audio.md` §15 step 0 |
| audio | The MCU bring-up card, which is what proves the register map | `audio.md` §12.5 |
| **audio** | **DECIDED 2026-09-08 — the sample RAM does not move into `A20 = 1`.** `audio.md` §5.2: memory-mapping it needs a second source on a 19-bit address bus that §9.5 collapsed to one, which is **3 × `'157`** the card will not spend to delete a software mask. ⚠ **So audio is the last card carrying the doubled-write exposure**, and `sdcard.md` §11.6's `TFM` decision is what actually retires it | `audio.md` §5.2, §16 item 0 |
| io | Measure the PS/2 protocol on a scope; add a reference document to `reference/` | `ps2.md` §13 step 1, §14 item 1 |
| io | **Measure NitrOS-9's interrupt dispatch cost** — it decides serial's ceiling, PS/2's FIFO, and §4.1's margins | `ps2.md` §14 item 3, §13 step 8 |
| io | **⭐ Decide `serial.md` §5.4's tier.** A `16C550` is +1 IC for 115,200 baud instead of 19,200, is current-production, and takes its timing from its own crystal — closing the `W65C51N` trap and the fast-E speed grade outright. **It needs eight `$FF` addresses, which is what §5 item 1 made available** | `serial.md` §4.5, §13 items 5–7 |
| io | Confirm whether NitrOS-9's `sc6551` exists; it is the card's entire software cost | `serial.md` §13 item 2 |
| **io** | **⚠ Fit `net`'s U2 before laying out its board** — 118 of 128 macrocells and 56 of 60 pins, with a five-step cut order behind it | `net.md` §7.3, §16 item 1 |
| **io** | **Find out whether a NitrOS-9 network stack exists.** It is the net card's largest cost and nobody has looked — the same shape of unknown as `serial`'s `sc6551` | `net.md` §14.2, §16 item 12 |
| **storage** | **⚠ The SD *write* path is still on the port** — the block buffer (§5 item 7) took reads off it; writes still pay the port | `sdcard.md` §13 item 6, §5 item 1 D |
| **storage** | **Re-examine the `ATF1508AS` consolidation** — `sdcard.md` §8.1's single-CPLD design was refused on the no-CPLD house rule alone, and the rule is retired (root `README.md`): 8 ICs against 14 | `sdcard.md` §13 item 12 |
| storage | A NitrOS-9 `RBF` driver — larger than the card. Evaluate matching CoCoSDC's map to inherit one | `sdcard.md` §13 item 4 |
| **project** | **Choose a licence.** The repository has none for its own work | `design-review.md` §Sys-M6 |

---

## 7. Memory, boot, and the vector page

Main memory and the first instruction belong to the machine and to no card
(`design-review.md` §Sys-C1 and §Sys-M2), which is why the card specifications could
not supply them; both are decided here.

### 7.1 System RAM

**Four 30-pin SIMM sockets, 4–16 MB of DRAM**, at physical 4–20 MB —
[`hardware/ram.md`](../hardware/ram.md) §5.2, §6.

> ⭐ **Decided 2026-09-08.** The map entry is 16 bits wide, so system RAM does not have
> to fit inside a 2 MB map — and once SIMM sockets are on the board, DIP SRAM has no
> job left: the motherboard carries **no SRAM but the map's own two `CY7C128A`**. DRAM
> is admissible now because the machine finally has a refresh owner — §5 item 8 gave
> the divider a `/WAIT` hold, and §5 item 10 shows refresh and the video card's stall
> never contend.
>
> **What it once cost was the boot path**, and §7.2's ROM closed that the same day:
> with no writable memory until a SIMM answers, the machine's first instructions have
> to run without a stack, and **they do — there are about twenty of them and none is a
> `JSR`.** `ram.md` §6.4 has the sequence.

### 7.2 ⭐ Boot — a 1 MB ROM on the motherboard

> **DECIDED 2026-09-08, and it replaces the CPU-module shadow ROM.** The superseded
> design — an ~8 KB shadow ROM and a 16-byte vector RAM served from inside the CPU
> module without a bus cycle — is archived in [history.md](history.md), together with
> why it was right when the physical map had no room for a ROM and wrong once it did.

**The failure this fixes, restated because it has not changed.** The 6309 fetches its
reset vector from `$FFFE`–`$FFFF`. §2 makes `$FF00`–`$FFFF` override MMU translation,
exactly as a CoCo 3 does — but a CoCo 3's SAM/GIME *specifically maps `$FFF2`–`$FFFF`
onto ROM*, and this machine decodes only `$FF00`–`$FF7F` and `$FFA0`–`$FFBF` in that
page. Without this section, `$FFFE` selects **nothing** and the CPU fetches its reset
vector from an undriven bus.

**What is new is that there is now somewhere to put a ROM.** `ram.md` §5.2's 32 MB map
has 2.0–4.0 MB reserved and nothing wanting it.

#### The parts

| Qty | Part | Role |
|---|---|---|
| **2** | **`SST39SF040`** — 512K×8, 5 V, 70 ns, **PDIP-32**, current production, ~$2.50 | the 1 MB ROM. Physical `A19` selects between them — one literal on U9 |
| **1** | **`74HCT541`** | drives physical `A19`–`A13` in the map's place — the whole of the mechanism below |

⚠ **Two packages because no 5 V 1M×8 part comes in a DIP.** `AM29F080B` (1M×8) is
PLCC-44/TSOP-40 and `M27C801` is a UV EPROM needing an eraser; the `SST39SF040` is
flash, socketed, and burns in a $30 programmer. **If a single-package 5 V 1M×8 is
sourced this drops to one IC** — `hardware/README.md` open item 1's rule applies, and
availability is the first question about a part (`net.md` §13.6).

#### The mechanism — three modes of one decode

| | When | Physical `A19`–`A13` come from | The ROM answers |
|---|---|---|---|
| **`BOOT`** | from `/RESET` until software clears it | **the `'541`, driving zero** | **every cycle except `$FF00`–`$FFBF`** |
| **`VECSEL`** | any logical `$FFC0`–`$FFFF` access, always | **the `'541`, driving zero** | **yes** — ROM `$1FC0`–`$1FFF` |
| normal | everything else | the map SRAM through the isolation `'245` | only at physical 2.0–3.0 MB |

**In both forced modes the map's `'245` is off and the `'541` is on**, and they are
mutually exclusive by construction rather than by timing: `MAPOE` already deasserts for
the whole of any `$FFxx` cycle (`hardware/gal/README.md`), which is the *same* condition
`VECSEL` is a subset of. There is no break-before-make window to argue about.

⚠ **`A24`–`A20` float in both forced modes and nothing may read them.** The `'541`
drives seven lines, not twelve — the ROM needs only `A19`–`A13` above the untranslated
`A12`–`A0`, and `A24`–`A20` come from the *second* map SRAM, which is off with the
first. So **`BOOT` and `VECSEL` must gate the SIMM selects and the `/IOPAGE` pull
directly rather than by address compare**, and the ROM's own `/CE` likewise. They all
live on U9 (`ram.md` §6.7), which is what makes that a rule about one part and not a
rule every decode has to remember.

> **Why a `'541` and not pull-down resistors.** Ten kilohms against ~50 pF of address bus
> is a 0.5 µs settling time and a bus cycle is 476.7 ns. That is fine for `BOOT`, where
> the bus is parked for the whole mode and settles once — and **wrong for `VECSEL`,
> which is per-cycle.** One package removes the entire question, and it is the same
> package for both modes.

#### What boot actually does

```
  /RESET          BOOT := 1.  Every logical block reads ROM page 0.
  $FFFE           reset vector, from ROM $1FFE            (VECSEL, and BOOT too)
  ...             write the 16 map entries at $FFA0-$FFAF -- register writes
                  point one block at physical 2.0 M, which is the same ROM page
                  the code is executing out of
  $FFB1 <- 0      BOOT := 0.  The map takes over; execution does not move.
  ...             set S into DRAM, and the machine is ordinary
```

⭐ **No instruction in that sequence is a `JSR`, so §7.1's stacklessness costs nothing.**
Refresh needs no initialisation either — U10's refresh timer free-runs off `CLK25` from
reset, which §5 item 10's rule requires of it anyway. `ram.md` §6.4 carries the
arithmetic.

#### What the megabyte is for

| | |
|---|---|
| **ROM page 0 — 8 KB** | the boot monitor: the sequence above, a `16C550` DriveWire loader ([`drivewire.md`](drivewire.md) §6.1), and the `$FFC0`–`$FFFF` vector table |
| **the remaining ~1016 KB** | ⭐ **a read-only ROM disk**, mounted by an `RBF` descriptor. The whole NitrOS-9 Level 2 distribution is about **645 KB** of `.dsk` images, so it fits with a third to spare |

**That is why the ROM is 1 MB and not 8 KB.** A machine that boots to a NitrOS-9 shell
with no SD card, no serial cable and no host is a different machine to bring up than one
that needs two of those working first, and `sdcard.md` §12 step 0's circularity —
DriveWire needs a client, the client needs a ROM — disappears rather than being worked
around.

#### ⭐ What it buys back

| | |
|---|---|
| ⭐ **"Drop a real HD63C09E in the socket"** | `graphics.md` §16 item 8's standing sanity check **holds again**. The reset vector, the boot ROM and the interrupt vectors are all on the bus; nothing about boot is inside the CPU module any more |
| ⭐ **Two divergence-ledger entries go away** | §5 item 6's ledger loses the shadow ROM *and* the vector page. `$FFC0`–`$FFFF` in ROM pointing at a fixed RAM jump table **is what a CoCo does**, so NitrOS-9's vector handling stops needing a patch instead of needing a different one |
| **The CPU module gets simpler** | `plan.md` §4.5's per-address range test goes — it was one comparison on every *formed* address, in the microcode step §3.3(d) measures rather than on the `t_AD` path — and the `PF1` machine strap with it, so **the pinout has a spare pin and the drop-in and homebrew SKUs run byte-identical firmware** |
| **`ram.md` §6.4's scratch-RAM proposal is withdrawn** | it existed to give a stackless boot somewhere to put a stack, and there is no stack to put |

#### ⚠ What it costs

| | |
|---|---|
| **3 ICs on the motherboard** | 14 → **17**. The shadow ROM cost zero, and this is the whole of the price |
| ⚠ **The vectors are in ROM, so the OS cannot retarget them** | as on a CoCo: the ROM vectors point at a fixed RAM jump table and the OS writes *that*. It is a software convention the boot monitor has to publish, and `software/6809/README.md` is where it lands |
| ⚠ **A ROM disk is only as current as the last time it was burned** | which is `drivewire.md`'s entire job — §1 there |
| **`$FFC0`–`$FFFF` is no longer available for I/O** | it never was; nothing decoded it |

---

## 8. Power

Video estimates its own current and audio its own; PS/2, serial, storage, net, the
motherboard and system RAM owe measured figures at bring-up
(`design-review.md` §Sys-M5). This table is where they land.

| Rail | Consumer | ICs | Estimate |
|---|---|---|---|
| 5 V | **video card** | **27** — 2 CPLDs, 1 GAL, 4 SRAMs | **~0.5–0.85 A, 0.65 A nominal**, design to 1 A — `graphics.md` §14.2 |
| 5 V | **audio card** | **31** — `audio.md` §10.1 | **~330–440 mA** — `audio.md` §10 |
| 5 V | **PS/2**, plus ~50–100 mA per attached device from each mini-DIN pin 4 | 11 | not yet estimated; order 100 mA of logic + up to 200 mA of devices |
| 5 V | **net** | 12 (2 CPLDs) | **~410–510 mA**, of which ~250 mA is the two `ATF1508AS` with reduced-power mode set per-macrocell — `net/docs/net.md` §10. **The second largest single-card draw after video**, and the only figure on that card that cannot be derived from a datasheet with confidence |
| 5 V | **serial**; **storage** (plus SD write bursts behind its own LDO) | 3 + **14** | not yet estimated |
| 5 V | **motherboard**: MMU (5, +1 map SRAM), divider GAL, oscillator, reset supervisor, U9/U10 GALs and 3 × `'157`, **2 × `SST39SF040` boot ROM and the `'541`** — `hardware/ram.md` §6.5 | **17** + 4 SIMM sockets | not yet estimated. ⚠ **DRAM is the machine's first refreshed memory**; a populated SIMM bank is not a small load. The ROM adds ~30 mA per part while it is selected and ~10 µA when it is not, which is most of the time |
| 3.3 V | CPU module and its buffers; the SD card | 8 | not yet estimated |

**The machine is plausibly **1.8–2.9 A** at 5 V across **115 ICs**, plus a 3.3 V
rail.** The sum, from each card's own document:

| video | audio | PS/2 | serial | storage | net | **cards** | motherboard | **machine** |
|---|---|---|---|---|---|---|---|---|
| **27** | **31** | 11 | 3 | **14** | **12** | **98** | **17** | **115** |

The backplane-distribution question this used to leave open — **how many power and
ground pins per slot** — was answered with the connector (§5 item 5): **5 × +5 V and
18 grounds**, ~5 A of finger capacity against a 2–3 A machine. Each card still owes a
measured figure at its own bring-up.

> ⚠ **Whether the audio card's analogue section fits its board has to be measured.**
> `audio.md` §16 item 19 raised it, and the count has moved several times since — the
> analogue section is now **twelve converter halves and thirteen amplifier channels**
> after `audio.md` §11.1's panning, against the two converters and four channels the
> original one-board assertion was made about. `hardware/place/` puts the card on
> **18 cm** and that is a courtyard-area check, not a layout. **Measure it, with the
> analogue section physically separate.** (The assertion was originally made about a
> **Eurocard**, which the machine stopped using on 2026-09-08 — §5 item 5.)
