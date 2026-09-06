# PS/2 Keyboard and Mouse for an arm6309 Machine
## Eleven ICs, After the Minimal 64x4 Showed It Could Be Three

**Question this answers:** the machine has a CPU ([`plan.md`](../../../cpu/docs/plan.md)),
a 256-colour video card ([`graphics.md`](../../../video/docs/graphics.md)) and a
Paula-class sound card ([`audio.md`](../../../audio/docs/audio.md)). It has no way for a
human to touch it. What does a PS/2 keyboard and mouse card look like, given that
[`machine.md`](../../../docs/machine.md) §5 says there is **no free `$FF` window** and
**no free interrupt line**?

**Short answer: a shift register and a counter per port, and put everything else in
software.** Slu4's Minimal 64x4 receives PS/2 in **three packages** — one `74HC595`, one
`74HC193`, one `74HCT132` — and §4.1 explains exactly how. Most of what a "proper" PS/2
controller contains is optional, and this card keeps only the parts that a **mouse**
forces: a transmit path, a second port, an address decoder — and, since the 2026-09-04
design review, **a second-stage latch per port**, because the buffering §5 thought it was
getting for free from the `'595` does not exist. That comes to **eleven**.

The half of the design people skip is **host-to-device transmit**, and it is not
optional — a mouse sends nothing at all until it is told `F4`. But it does not need
hardware either. It happens twice at boot and on caps-lock, at 60–100 µs per bit, so the
driver bit-bangs it through two control bits and the whole transmit engine disappears.

**Constraints taken as given (yours):**
- **PS/2 keyboard and mouse**, one port each.
- **Parts available before 1990.** No CPLDs, no FPGAs. GALs are in (video uses 8).
- Same house rules as the other cards: period-honest silicon, one card, a documented
  register map, and an honest IC count.

> **PS/2 is in period, but only just.** The interface is IBM's, introduced with the
> Personal System/2 in **April 1987** — two years before this machine's 1989–90 window,
> and contemporary with the VGA connector [`graphics.md`](../../../video/docs/graphics.md)
> §15 already justifies on the same grounds. §12 audits the rest of the BOM.

---

## 0. Summary — the verdict in one table

| Question | Answer | § |
|---|---|---|
| **How much hardware does receiving PS/2 actually take?** | **Three packages per port** — a `'595`, a `'193` and a `'574` — plus a shared `'132`. The first two are the Minimal 64x4's; the third is §5.1's correction. | §4.1, §5.1, §6 |
| **Would a quadrature mouse be cheaper, as on Burrell Smith's Apple II card?** | **Two packages cheaper and unaffordable.** Interrupt-per-notch scales with hand speed — up to 4,000/s, against PS/2's fixed 180. | §4.4(c) |
| **Would one 6522 VIA per port replace most of this?** | **Four packages instead of eleven, and rejected on I/O space:** two VIAs decode 32 bytes against a 4-byte budget. | §4.5 |
| **How does the card get the CPU's attention?** | **`/IRQ`, as a third source.** `/IRQ` is already an open-drain line with two sources (VBL, raster compare); only `/FIRQ` is exclusive. | §3.1 |
| **What does that cost?** | **~1.1 % of the CPU while input is actually happening**, zero when it is not — with the mouse at 60 samples/s. | §3.1, §5.2 |
| **Why is there no FIFO?** | Because with an interrupt there is nothing to *queue*. But the `'595`'s storage register is **not** a byte of buffering — it is overwritten by the next frame's start bit — so the card buys the frame time with a `'574` per port instead. | §5, §5.1 |
| **Why is the mouse set to 60 samples/s?** | You cannot display a pointer faster than the 70.09 Hz frame rate, and **60 /s is the largest standard PS/2 rate below it**. | §5.2 |
| **Does the card check parity?** | **No.** 30 cm of shielded cable at 16 kHz, and the only recovery costs a round trip worth more than the error. Slu4 checks nothing either. | §6.2 |
| **Does the card need to transmit?** | **Yes** — a mouse is silent until `F4`. **In software**, through two control bits and a `7407`. | §7 |
| **Where does it live in the `$FF` map?** | **`$FF50`–`$FF53`, four bytes** — a quarter of the region pencilled in for a disk controller, not half. | §3.2 |
| **Does it decode scan codes?** | **No.** Raw set-2 bytes; translation is the driver's job. | §11.1 |
| **Emulate the CoCo's PIA0 keyboard matrix so stock NitrOS-9 drivers work?** | **No** — it would cost more than the entire card. | §10 |
| **IC count** | **11.** Was 16 before reading the Minimal 64x4, and 9 before §5.1's second-stage latch. | §9 |

**Net: 11 ICs** — one GAL22V10, two `'595`, two `'193`, two `'574`, and four glue
packages — against the video card's count (`graphics.md` §14) and audio's
(`audio.md` §10).

---

## 1. Sources and confidence

| Claim class | Source | Confidence |
|---|---|---|
| The 3-IC receiver topology, the `Q0`→`RCLK` trick, the reversed bit order, the Schmitt-input requirement | **Minimal 64x4 Rev 1.4 Redux, sheet 3/9 "PS/2 Receiver"** — `~/code/colormin/minimal/`, KiCad source and `Schematics.pdf` | **read directly from the schematic**, including the designer's own annotations |
| Burrell Smith's two-chip Apple II mouse card; the interrupt-per-notch model; the video-sync flip-flop | Andy Hertzfeld, *Apple II Mouse Card*, folklore.org, June 1981 — `reference/articles/folklore-apple2-mouse-card.pdf` | **read directly**; a first-hand account, but a *narrative*, not a schematic |
| 6522 VIA shift-register modes and errata (§4.5) | recalled, 6502-community lore | ⚠ **no 6522 datasheet in `reference/` — §14 item 8** |
| Frame format: 11 bits, LSB-first, odd parity, start 0 / stop 1 | Adam Chapweske, *The PS/2 Mouse/Keyboard Protocol*; corroborated by Columbia CSEE W4840 notes and the ARM PrimeCell PS/2 (`DDI0096`) datasheet | widely corroborated — **not** verified against a primary document in this repo |
| Clock rate 10–16.7 kHz; 30–50 µs half-periods; ≥100 µs host inhibit; 15 ms request-to-first-clock; 2 ms frame completion | Same | ⚠ **recalled figures — measure before committing the GAL.** §13 step 1 is that measurement. |
| Keyboard ID `AB 83`, mouse ID `00`, BAT `AA`/`FC`, commands `FF`/`F4`/`F5`/`F3`/`ED` | Same | widely corroborated |
| Mouse stream: 3-byte packets, selectable 10–200 samples/s, default 100 | Same | widely corroborated |
| NitrOS-9 interrupt dispatch cost | ⚠ **guessed at 100–400 cycles.** §3.1's whole budget rests on it | **unverified — §14 item 3** |

**No PS/2 datasheet is in `reference/`** — §14 item 1, and the first thing to fix.

---

## 2. What the protocol actually demands

### 2.1 The frame

Eleven bits, in both directions, **LSB first**:

```
  start   b0 b1 b2 b3 b4 b5 b6 b7   parity   stop
    0     <------ data, LSB ----->    odd      1
```

Two lines, `CLK` and `DATA`, both **open-collector with pull-ups** — either end may pull
either line low, and that is the whole flow-control mechanism. **The device always
generates the clock**, in both directions. The host never clocks the bus; it only
inhibits it by holding `CLK` low.

That single fact sets the shape of §4: the card is clocked by an *external, asynchronous,
slow* clock that it does not control and cannot predict. Every state transition hangs off
a `CLK` edge, and there is no free-running timebase anywhere in the design.

### 2.2 Timing

⚠ Recalled figures — see §1.

| Parameter | Value | What it means here |
|---|---|---|
| Clock rate | 10–16.7 kHz | 60–100 µs per bit. **Enormous.** A 2.098 MHz bus cycle is 476 ns. |
| Clock low / high | 30–50 µs each | any Schmitt input and any HC-family register is 1000× faster than needed |
| Host inhibit to start a transmit | **≥100 µs**, `CLK` held low | §7 does this with a software delay loop |
| Clock idle-high before a device may transmit | ≥50 µs | the card must release cleanly, or a keypress is lost |
| Device begins clocking after a host request | within 15 ms | §7's software timeout |
| Frame completion | within 2 ms | §7's software timeout |
| **Signal rise/fall time** | **can exceed 400 ns** | **the one real electrical constraint — §4.2** |

**Nothing in this card is a timing problem**, which is the opposite of every other card in
the machine: `graphics.md` §2 fights a 39.7 ns dot path, `audio.md` §3.2 a 35 ns pipeline
stage, `plan.md` §3.3 a 110 ns `t_AD`. Here the tightest number is 30 µs. That slack is
what pays for §7 being software and §5 having no FIFO.

### 2.3 Host-to-device, and why it is not optional

This is the half that gets skipped — the Minimal 64x4's sheet is titled "PS/2 **Receiver**"
and has no transmit path at all — and skipping it costs you the mouse entirely:

- **A PS/2 mouse powers up with reporting disabled.** It sends its BAT result and its ID,
  and then **nothing, ever**, until the host sends `F4`. A receive-only port yields three
  bytes and then silence. This is why the Minimal 64x4 has a keyboard and no mouse.
- `ED` (LEDs), `F3` (sample rate — §5.2 needs it), `FF` (reset) and the mouse resynchronise
  of §11.3 all need transmit.

The sequence, which §7 implements in software:

1. Host pulls `CLK` low for **≥100 µs** — this inhibits the device.
2. Host pulls `DATA` low (the start bit) and **releases `CLK`**.
3. The device sees the request and **generates 11 clocks**.
4. Host presents each bit while `CLK` is low; the device samples on the rising edge.
5. After the stop bit the host releases `DATA`; the device pulls `DATA` low for one more
   clock — the **ACK bit**.

Note step 3: even for a host-to-device frame **the device supplies the clock**. The card
never becomes a clock source, which is why there is no baud generator and no timer IC
anywhere in §9.

---

## 3. The two machine-level blockers, answered

[`machine.md`](../../../docs/machine.md) §5 items 1 and 2 are the two things an I/O card
runs into first, and [`../../README.md`](../../README.md) asks that both be *chosen*
rather than defaulted into. Here are the choices.

### 3.1 Take `/IRQ` — it is a shared line, and always was

`audio.md` §8.1 takes `/FIRQ` as the **sole** source, deliberately, so the replayer's
interrupt path has no polling chain in it. That exclusivity is specific to `/FIRQ`.
**`/IRQ` is the opposite**: `graphics.md` §12 already puts *two* sources on it — VBL and
raster compare — open-drain, with a GIME-compatible interrupt-source block that
"NitrOS-9's CoCo 3 IRQ code already talks to". A third source is what the line is for.

`/NMI` is free and is the wrong answer: being non-maskable, a keypress would pre-empt the
replayer tick that `/FIRQ`'s exclusivity exists to protect.

**So: `/IRQ`, open-drain, maskable by `IOCTRL.IRQEN`.**

| | |
|---|---|
| Interrupt rate, keyboard | ~60 /s while typing fast |
| Interrupt rate, mouse at **60 samples/s** (§5.2) | 180 /s while moving |
| Combined, worst realistic case | **~240 /s** |
| Cost at 100 cycles/interrupt (bare metal) | **1.1 %** of a 2.0979 MHz CPU |
| Cost at 400 cycles/interrupt (NitrOS-9 dispatch ⚠) | **4.6 %** |
| Cost when nobody is touching anything | **zero** |

Arithmetic: 240 × 400 = 96,000 cycles/s against 2,097,900 = 4.58 %. At the old 40 /s
mouse rate it was 180 × 400 = 72,000 = 3.4 %; §5.2 explains why the extra 1.2 points is
worth buying, and what to do if §13 step 8 says it is not.

> ⚠ **The 40 /s figure in the row above replaced an earlier one and has itself been
> replaced.** §5.2, per the 2026-09-04 design review (IO-P5): 40 /s was chosen as "just
> under the frame rate", but 60 /s is a standard PS/2 rate and 70.09 Hz is the frame rate,
> so the criterion's own answer was 60 all along.

> **The 400-cycle figure is a guess and it is the weakest number in this document.**
> If NitrOS-9's dispatcher is worse than that, 4.6 % becomes 9.2 % and this decision
> should be revisited — §14 item 3, and §13 step 8 measures it. The fallbacks are §5.2's
> 40 /s mouse rate (which costs nothing) and then §5.3's FIFO, which trades four packages
> for the interrupt load.

**The earlier revision of this document polled from the VBL tick instead**, to avoid
touching the interrupt structure at all. That was the wrong trade: it cost a 16-byte FIFO
per port — **four of sixteen packages** — to save an interrupt on a line that already had
two sources. Reading the Minimal 64x4 is what made that visible.

Polling remains a supported fallback and is how §13 step 7 brings the card up before the
video card exists — but with one byte of buffering it is only sound for the keyboard.

**The line is shared, so the order in which the handler polls it is a machine-level
decision, not this card's.** `machine.md` §4 records it, and it is: **video `VSTAT`
first** (VBL is NitrOS-9's system tick and by far the most frequent source), **then this
card's `IOSTAT`**, **then the serial card's `STATUS` last**. Serial is last because
reading the 6551's `STATUS` *clears* its interrupt and returns the error bits in the same
read (`serial.md` §7.3), so that card's handler cannot probe cheaply and defer — it must
consume what it finds. This card is deliberately in the middle: §8.1's `IOSTAT` read has
**no side effects at all**, so an early handler in the chain may read it as often as it
likes, and the byte is not consumed until `KDATA`/`MDATA` is read.

### 3.2 `$FF50`–`$FF53` — a quarter of the disk controller's window, not half

The geographic decode spans `$FF40`–`$FF7F` (`graphics.md` §17). Video has
`$FF60`–`$FF7F`; `audio.md` §9.1 proposes `$FF40`–`$FF4F`; `$FF50`–`$FF5F` is pencilled
in for a disk controller that does not exist.

**Propose `$FF50`–`$FF53` — four bytes** — leaving `$FF54`–`$FF5F`, twelve bytes, for the
disk controller. Four is enough because §8 has exactly four registers, and it has four
registers because §5 has no FIFO to index and §7 has no transmit engine to command. A
WD1773 is four registers plus a latch, so twelve bytes leaves the disk controller room it
would not otherwise have had.

> ⚠ **Four, not five.** `machine.md` §3's parallel sentence says "five registers plus a
> latch"; the WD1773 has four (`COMMAND`/`STATUS`, `TRACK`, `SECTOR`, `DATA`) plus the
> drive-select/side/density latch that every CoCo-style controller board adds beside it.
> The figure in this section is the correct one; `machine.md` is the document to fix.

Decode is from the backplane's `/IOSEL`, so the base is a jumper.

> ⚠ **This said "geographic from the backplane's per-slot `/IOSEL`" until 2026-09-06.**
> A per-slot decode fixes each card's window by position and leaves the jumper in the
> same sentence nothing to select. `/IOSEL` is the `$FF40`–`$FF7F` window strobe, common
> to every slot; this card decodes its four bytes from `A0`–`A5` against the jumpered
> base. [`machine.md`](../../../docs/machine.md) §2 owns the correction.

---

## 4. Architecture

### 4.1 What the Minimal 64x4 does, and why it is right

Slu4's Minimal 64x4 (Carsten Herting, CC BY-NC-SA 4.0) receives PS/2 in **three
packages**. The circuit is worth reading in full — `Schematics.pdf` sheet 3/9 — because
almost every choice in it is load-bearing:

```
  PS2_DAT ──────────────────────────────► SER      74HC595
  PS2_CLK ──►['132 Schmitt]──────────────► SRCLK   shift + storage
                    │                             QA..QH ──► BUS7..BUS0
                    ▼                                        (reversed)
                 74HC193  ──── Q0 ───────► RCLK
                 counts down
                    │
                  ~TCD ────►['132 NAND SR latch]──► PS2_DR
                                    ▲
                             ~KO ───┘ (also drives ~OE)
```

Four ideas, and all four transfer:

1. **The `'595`'s separate storage register solves the 11-into-8 problem.** A PS/2 frame
   is eleven bits and the register is eight, so the shift register alone never holds the
   byte you want. The `'595` shifts continuously and **transfers to storage at the right
   moment**, so start, parity and stop shift harmlessly through. This is the single
   cleverest part of the design and it is why the part is a `'595` and not a `'164`,
   `'165` or `'299`.

2. **`Q0` of the counter drives `RCLK`** — no decode of "the ninth clock" is needed. The
   counter's LSB toggles every clock, and Slu4's own note on the sheet explains the
   timing: *"RCLK is driven by Q0 which happens after CPD, thus RCLK always samples the
   current, not the previous register state; the last time a rising edge occurs is during
   bit 7."* One wire replaces a decode term.

   > ⚠ **And one wire is also what §5 gets wrong.** `Q0` toggles on *every* edge of
   > *every* frame, so `RCLK` keeps firing into the next frame and the storage register
   > is not a holding register between frames. Slu4's machine gets away with it because
   > its CPU tests a branch flag directly; this one cannot. §5, and §5.1 is the fix.

3. **The bit order is reversed in the wiring.** PS/2 is LSB-first, so shifting into a
   `'595` leaves the byte backwards; `QA`→`BUS7` … `QH`→`BUS0` fixes it for free.
   Slu4's note: *"The order of the bits is intentionally reversed."* Costs nothing,
   saves a software reverse on every byte.

4. **Data-ready is a NAND SR latch in the spare gates** of the same `'132` doing the
   input conditioning, set by the counter's borrow and cleared by the read strobe.

**What the Minimal 64x4 does not do**, and what therefore accounts for the difference
between its three packages and this card's eleven:

| | Minimal 64x4 | this card | cost |
|---|---|---|---|
| Ports | 1 (keyboard) | **2** (keyboard + mouse) | +2 ICs |
| Direction | receive only | **bidirectional** — a mouse needs `F4` | +1 IC (`7407`); the rest is software |
| Bus attachment | **microcode strobes** `/KO`, and `PS2_DR` wired to a **CPU branch flag** | memory-mapped, address-decoded | +3 ICs |
| Parity / framing | none | **none** — §6.2 | 0 |
| Buffering | 1 byte-ish (the `'595` storage, valid until the next start bit) | **1 byte, genuinely one frame deep** — a `'574` per port, §5.1 | +2 ICs |

**Three of the eight added packages exist only because the 6309 is a fixed CPU.** Slu4
could give his machine an instruction that reads the keyboard and a branch that tests
data-ready; `arm6309` cannot, because being bit-compatible with a real HD6309E is the
entire project. That is the honest accounting: this is not a worse design, it is the same
design paying a bus tax the Minimal 64x4 does not owe.

**And two of them exist because that same branch flag is what makes the Minimal 64x4's
buffering adequate.** Slu4's CPU can test data-ready in one instruction and read the byte
in the next, so the window between edge 9 and the next frame's edge 1 is never a problem
for it. A 6309 arriving through NitrOS-9's interrupt dispatcher is three orders of
magnitude slower to answer, which is why §5.1 spends the `'574`.

### 4.2 The one real electrical constraint

Slu4's annotation, and it is the kind of thing that is only obvious after it has bitten
someone:

> *"74HCxx input rise time (10–90 %) is required to be < 400 ns. Use 74HC132 (NAND with
> Schmitt trigger inputs) rather than 74HC00 here, since PS/2 signals can have rise and
> fall times > 400 ns. For PS/2 devices with only 3.3 V output use 74HCT132 for maximum
> robustness."*

Both halves matter. The lines are open-collector with 4.7 kΩ pull-ups driving metres of
cable capacitance, so edges are slow enough to violate a plain HC input's rise-time spec —
**Schmitt inputs are mandatory, not a nicety.** And **`HCT`, not `HC`**: a device with
3.3 V outputs clears `HCT`'s 2.0 V `V_IH` and does not reliably clear `HC`'s 3.5 V.

**Specify `74HCT132`.** This card uses one, shared between both ports, with all four gates
consumed by conditioning `CLK` and `DATA` on each.

### 4.3 The datapath, per port

```
        +5V
         │  4.7k                       preset A B C D = 1 0 1 0  (= 10)
  CLK ───┴──►['HCT132 Schmitt]──┬──────────────┬──► 74HC193 (MR = 0)
         ◄───[7407 open-coll.]  │              │      │        ▲
                                │              └──► SRCLK      │ /PL
                                │                     │        │
  DATA ──┬──►['HCT132 Schmitt]──┼──► SER   74HC595    Q0 ──► RCLK
         ◄───[7407 open-coll.]  │        shift+storage
                                │              │ QA..QH  (reversed)
                                ▼              ▼
                          ┌───────────┐    ┌──────────┐
        KRST/MRST ───────►│           │    │ 74HC574  │
           /RESET ───────►│  GAL22V10 │    │ 2nd stage│
      read strobe ───────►│           │    └──────────┘
                          │   /PL ────┼────► (to '193, with ~TCD)
             ~TCD ───────►│   DR ─────┼────► CLK of the '574
                          │   DR ─────┼────► /IRQ  (open drain)
                          └───────────┘    read strobe ──► /OE ──► D0–D7
```

Five things in that diagram are not in the Minimal 64x4's, and four of them are the
2026-09-04 design review's:

1. **The `'193`'s preset inputs are strapped to 1010 = 10**, and `~TCD` is fed back to
   `/PL` through the GAL so the counter reloads itself at the end of every frame. The
   Minimal 64x4 does this and this document's earlier revision did not draw it. §6.1
   derives the value, and §6.1's note explains why the load pulse is self-terminating and
   still wide enough. `MR` is **tied low permanently** — it forces 0000, not the preload,
   and a down-counter released at 0000 borrows on its very next edge.
2. **`KRST` asserts `/PL`, not `MR`**, for the same reason: "held in reset" for this
   counter means *held at the preload*, so that when the driver releases it the next
   `CLK` falling edge is counted as edge 1.
3. **A `74HC574` per port** captures the `'595`'s storage register once per frame and
   drives the bus — §5.1. The `'595`'s own `~OE` is now tied **permanently enabled**; it
   no longer touches the bus.
4. **`/RESET` is a GAL input**, clearing both `DR` latches — §8.4.
5. The `DR` latch, as well as raising `/IRQ`, is what **clocks the `'574`** — §5.1
   explains why the capture strobe is taken from the latch's clean output level rather
   than from the ~40 ns `~TCD` pulse that is simultaneously reloading the counter.

The `7407` open-collector drivers and the readable line states are the *entire* transmit
hardware. Everything else in §7 is software.

---

### 4.4 The other prior art: Burrell Smith's Apple II mouse card

Andy Hertzfeld's account (`reference/articles/folklore-apple2-mouse-card.pdf`, June 1981)
describes Burrell Smith building a mouse interface for the Apple II in **two chips** — a
6522 VIA and a dual flip-flop — where the Apple II division later shipped "more than a
dozen". Three ideas in it, and **they do not all point the same way**, which is what makes
it worth reading rather than just admiring.

#### (a) The two-chips-versus-a-dozen story, and why the dozen happened

> *"The mouse is hooked up to the 6522 so that it generates an interrupt each time the
> mouse moved a notch horizontally or vertically, with a one bit line to sense the mouse
> button. That was it — the rest was done in software."*

And the reason for the dozen:

> *"…they didn't think the Apple II could deal with interrupts properly (even though we
> had demonstrated that it could), so they added tons of hardware."*

**That is exactly the mistake the first revision of this document made.** It assumed no
interrupt was available (§3.1 — the assumption was wrong; `/IRQ` was never exclusive) and
paid for the assumption with a 16-byte FIFO per port: four packages of hardware bought by
distrusting an interrupt. Same error, same price, 45 years apart. It is recorded here
because the *pattern* is what recurs — **hardware is what you build when you do not
believe the CPU will be there in time**, and the first thing to check is always whether
that belief is true.

#### (b) The video-sync trick — inapplicable, but the shape of it is not

The part Hertzfeld calls the most brilliant: the Apple II had no vertical-blanking
interrupt, and rather than run a wire to the video signal, Burrell **wired the spare
flip-flop to the low bit of the data bus** to latch whatever byte the video circuitry was
displaying. Fill the frame buffer so that bit is 1 everywhere except the end of the last
scan line, poll the latch, and the transition *is* the start of VBL — a video sync derived
from something already on the bus, with no new connection.

Then the follow-on, which is the better idea:

> *"…if the loop time was relatively prime to the display frequency, it eventually had to
> slip into place. I wrote a 17 microsecond loop that fit the bill."*

The CPU could not sample fast enough to be sure of catching a one-byte-wide event, so the
sampling *phase* was made to walk until it landed.

**Neither trick is needed here — `graphics.md` §12 gives this machine a real VBL
interrupt.** But two places inherit the shape:

- **§13 step 7 is Burrell's exact situation:** bring the driver up on a monitor ROM with
  no video card and therefore no VBL. That step polls in a software loop, and if it ever
  needs to be periodic rather than continuous, the relatively-prime trick is the technique
  to reach for rather than a timer the bring-up rig does not have.
- **Presence and abort detection cost nothing because the information is already there.**
  §8.1 exposes `KCLK`/`MCLK`/`KDAT`/`MDAT` — line states the `'HCT132` is conditioning
  anyway, for §7's benefit. Idle-high means a device is plugged in; clock stuck low past
  2 ms means a frame died mid-way. **No presence-detect hardware, no watchdog IC** — the
  same move as latching the bus bit instead of running a wire to the video.

#### (c) The quadrature mouse — and here the lesson reverses

Burrell's mouse is not a serial device at all. It is two interrupt lines, two direction
bits and a button bit: **interrupt per notch of movement, position accumulated in
software.** In discrete logic on this card that is an edge-detect flip-flop per axis plus
a few bits of the `'244` that already exists — call it **one package instead of the three
(`'595` + `'193` + `'574`) the PS/2 mouse port costs.**

**Take the cheaper option and the machine falls over.** Interrupt-per-notch scales with
*hand velocity*, and it is unbounded:

| | Interrupts/s |
|---|---|
| Quadrature, 100 CPI, slow (2 in/s), both axes | 400 |
| Quadrature, 100 CPI, brisk (5 in/s) | 1,000 |
| Quadrature, 200 CPI, fast (10 in/s) | **4,000** |
| **PS/2 at 60 samples/s (§5.2)** | **180, whatever the hand does** |

At 400 cycles of NitrOS-9 dispatch (§3.1's ⚠ figure), 4,000 interrupts/s is **76 % of the
CPU**, consumed by moving the mouse quickly. Even the brisk case is 19 %.

**PS/2's packetisation — the thing that makes it look heavyweight next to four quadrature
wires — is precisely what makes it affordable here.** The device does the accumulating and
reports at a rate *we* choose with `F3`. Burrell's machine had one job and a spare 6522;
this one has a replayer with a hard tick, and an input device whose cost is a function of
how fast someone moves their hand is the wrong shape for it.

> **One thing that does carry over intact:** `audio.md` §8.1 put the replayer on `/FIRQ`,
> which on a 6809 outranks `/IRQ`. So even a pathological interrupt storm on this card
> **cannot starve the replayer tick** — it would eat everything else instead. That
> protection was designed for a different reason and it happens to cover this case too,
> which is worth knowing before anyone is tempted by the four-wire mouse.

### 4.5 The alternative Burrell's card suggests: a 6522 per port

The deeper reading of §4.4(a) is not "use interrupts" but **"use a general-purpose
period part instead of building one out of glue."** Burrell's two chips are two chips
because a 6522 VIA already contains ports, timers, interrupt logic and a shift register.
That question deserves a straight answer here rather than being left implied.

A 6522 has a shift register with modes for **shift in and shift out under an external
clock on `CB1`** — which is, on the face of it, exactly a PS/2 port: `CB1` = `CLK`,
`CB2` = `DATA`, the port bits give §7's line drive and read-back, a timer gives the 100 µs
inhibit, and the interrupt logic gives `/IRQ`. Two VIAs, a `7407` and an `'HCT132` is
**four packages against this card's eleven**, and a 6522 is a 1977 part — comfortably inside
the period rules, which bar CPLDs and FPGAs, not LSI.

**Rejected, on three counts, and the first one is decisive:**

1. **I/O space.** A 6522 decodes sixteen registers of its own. Two of them is **32 bytes**
   against §3.2's four-byte budget — and against a `$FF40`–`$FF7F` geographic window of
   which video already owns half. There is not room, and there is no version of this that
   is close.
2. ⚠ **Eight bits against an eleven-bit frame.** The VIA's shift register interrupts every
   eight external clocks. A PS/2 frame is eleven, so the interrupt lands mid-frame and
   every byte needs software resynchronising across frame boundaries — the exact problem
   the `'595`'s storage register (§4.1) solves in a wire.
3. ⚠ **The 6522 shift register has a reputation for errata in external-clock mode.**
   Widely reported in the 6502 community; not verified against a datasheet here.

Points 2 and 3 are **recalled, not checked — §14 item 8.** Point 1 does not depend on
them, so the verdict stands regardless, but if this is ever revisited it should be
revisited against a real datasheet.

> **What this rejection is not.** It is not "LSI is against the rules" — it is not, and
> `audio.md` §12.5 keeps an MCU card as a bring-up vehicle. It is a budget argument about
> a scarce 64-byte I/O window, and if that window were ever widened (`machine.md` §5 item
> 1 contemplates exactly that) the 6522 route deserves a second look.

---


## 5. Buffering — one byte is enough, and two packages are what it costs

This is where the earlier revisions of this document were wrong, twice, and it is worth
showing the arithmetic that changed each time.

> ### ⚠ The `'595`'s storage register is **not** a byte of buffering. Superseded 2026-09-04.
>
> **The claim below was this card's central engineering argument, and it is false:**
>
> > **The `'595`'s storage register holds one byte while the next frame shifts in.** That
> > buys one full frame time — **660 µs at the slowest clock rate** — to service the port.
> > The only question is whether the CPU can be there inside 660 µs.
> >
> > - **With `/IRQ` (§3.1): trivially yes.** Interrupt latency on a 6309 is
> >   instruction-time plus dispatch, three orders of magnitude inside the window.
> >   **No FIFO. No packages.**
>
> **The small error first.** 660 µs is 11 × 60 µs, which is the *fastest* PS/2 clock rate
> (16.7 kHz). The *slowest* (10 kHz) gives 11 × 100 µs = **1.1 ms**. The label is
> inverted; 660 µs is the floor of the frame time, not its ceiling.
>
> **The large error.** `RCLK` is `Q0` of the `'193` (§4.1 idea 2), and `Q0` toggles on
> **every clock edge of every frame** — it has no notion of a frame boundary. For the
> capture to work at all `Q0` must rise on the odd edges, 1, 3, 5, 7, 9, so that its last
> rising edge lands during bit 7. **Edge 1 of frame N+1 is that frame's start bit**, and
> it copies the shift register into storage again: byte N shifted one place further, with
> the new frame's start bit in `d0`. So byte N is valid from edge 9 of frame N until
> **edge 1 of frame N+1**, and the service deadline is not the frame time at all. It is
> the **inter-byte gap** — a quantity the host does not control, that no PS/2 document
> specifies, and that inside a 3-byte mouse packet is device-dependent and can be a few
> hundred µs.
>
> Against that, one NitrOS-9 dispatch at this document's own 400-cycle guess is
> 400 / 2.0979 MHz = **191 µs** — before the shared-`/IRQ` chain of §3.1 has polled
> video's two sources, and before the handler body runs. And §6.2 checks neither parity
> nor framing, so a torn byte is **indistinguishable from a good one**: the failure mode
> is silent corruption of the mouse stream, not a detected error.
>
> Found in the 2026-09-04 design review, `docs/design-review.md` §5 IO-P1.

### 5.1 The second-stage latch — two packages, and the buffer becomes real

**A `74HC574` per port, between the `'595`'s outputs and the data bus, clocked once per
frame at end-of-frame.** The `'595` keeps doing exactly what Slu4's does — shift on every
`CLK` edge, re-copy to storage on every odd edge — and the `'574` samples that storage at
the single instant when it is known to hold `d0`–`d7`, then holds it against everything
the next frame does.

| | storage register alone | with the `'574` |
|---|---|---|
| Byte N first valid | edge 9 of frame N | end of frame N (edge 11) |
| Byte N destroyed at | **edge 1 of frame N+1** — its start bit | end of frame N+1 |
| Deadline the driver gets | the **inter-byte gap** — unspecified, device-dependent, a few hundred µs inside a mouse packet | **one whole frame: 660 µs at 16.7 kHz, 1.1 ms at 10 kHz** |
| In 191 µs dispatches (§3.1's worst guess) | one, if the gap is generous; possibly none | **3.5 to 5.8** |
| If the driver is late | silent garbage, undetectable (§6.2) | one dropped byte, and the mouse resynchronises (§11.3) |

That last row is the real change. The bad case stops being *undetectable corruption* and
becomes *a dropped byte*, which is a failure mode §11.3 already handles.

**Where the capture strobe comes from.** The obvious answer is `~TCD` itself, and it is
the wrong one, because §6.1's `/PL` feedback makes `~TCD` a **self-terminating pulse of
about 40 ns** — enough to load the `'193` and not a comfortable clock for a `'574`.
Instead the strobe is the **`DR` latch's own output**: `~TCD` sets the latch inside the
GAL, and the latch's clean 0→1 transition clocks the `'574`. Three consequences, all
wanted:

- The `'574`'s clock and `/IRQ` come from the same `DR` transition, and the `'574`'s
  outputs are valid ~20 ns after it. The 6309 cannot respond to `/IRQ` in less than one
  bus cycle (476 ns) and in practice takes several µs, so **there is no window in which
  the CPU is told a byte is ready and reads the previous one.** Setup on the `'574`'s `D`
  inputs is met by construction: the storage register has been stable since edge 9.
- The strobe is a clean level transition, not a 40 ns glitch, so no pulse-width argument
  is needed.
- **The overrun policy falls out and is the right one.** If `DR` is *already* set when the
  next frame ends, there is no rising edge, the `'574` is not re-clocked, and byte N is
  **kept** while byte N+1 is lost. The byte the driver has already been interrupted for
  is the byte it gets; a late driver loses the *new* byte rather than having the old one
  swapped underneath it mid-read.

**Cost: +2 ICs, and the card goes from 9 to 11** (§9). The `'595`'s own `~OE` is tied
permanently enabled and no longer drives the bus — the `'574`'s `/OE` does, from the same
read strobe that clears `DR`. Nothing else in the datapath moves.

**Polling at the 70.09 Hz VBL tick is still no** — 14.27 ms is 13 to 21 frame times, so
one byte of buffering never made polling work and the `'574` does not change that. That is
what forced the earlier design's 16-byte FIFO, and it is four packages of tail wagging one
dog.

### 5.2 The mouse sample rate — 60 /s, which is what the criterion always said

**Set the mouse to 60 samples/s** (`F3`, then `$3C`), not the 100 default.

The valid PS/2 sample rates are **10, 20, 40, 60, 80, 100 and 200 /s** — the device
rejects anything else. Each report is a 3-byte packet, so each costs three interrupts:

| Mouse rate | Bytes/s | Interrupts/s | Per 14.27 ms frame | Cost at 400 cyc ⚠ |
|---|---|---|---|---|
| 200 /s (max) | 600 | 600 | 8.6 | 11.4 % |
| 100 /s (default) | 300 | 300 | 4.3 | 5.7 % |
| 80 /s | 240 | 240 | 3.4 | 4.6 % |
| **60 /s (specified)** | **180** | **180** | **2.6** | **3.4 %** |
| 40 /s (previous revision) | 120 | 120 | 1.7 | 2.3 % |
| 20 /s | 60 | 60 | 0.9 | 1.1 % |
| 10 /s | 30 | 30 | 0.4 | 0.6 % |

**You cannot display a pointer faster than the frame rate**, so the criterion is: take the
largest standard rate that still sits below 70.09 Hz. That rate is **60**, and the
previous revision's 40 was a rate chosen from a menu that omitted it.

> ⚠ **The previous revision specified 40 /s and justified it as "just under the frame
> rate".** It is not — 60 is, and 80 is the first rate above it. Corrected per the
> 2026-09-04 design review (IO-P5). The `F3` argument changes from `$28` to `$3C`
> (§11.2 step 3, §13 step 5).

What it costs: mouse interrupts go from 120 /s to 180 /s, so §3.1's combined worst case
goes from ~180 /s to ~240 /s, and the CPU budget from 0.9 %/3.4 % to **1.1 %/4.6 %**.
What it buys: worst-case pointer latency falls from 25 ms (one 40 Hz report period) to
16.7 ms, which is under one 14.27 ms frame plus a compositing pass rather than nearly two
frames.

**If §13 step 8 measures a dispatch cost worse than 400 cycles, drop back to 40 /s before
touching anything else.** It is a one-byte change in the driver, it recovers 1.2 points of
CPU, and 25 ms of pointer latency is a defensible trade that this card can make at
runtime. That ordering matters: the sample rate is the cheap knob and §5.3's FIFO is the
expensive one.

### 5.3 The FIFO fallback, unchanged

> **If §13 step 8 finds the interrupt load unacceptable even at 40 /s:** two
> `CD40105B` per port — asynchronous 16 × 4 FIFO with data-ready and data-full flags,
> no pointer logic — restoring the polled design at **13 ICs**. The part is genuinely
> period (RCA, early 1980s) and genuinely hard to source now; the all-jellybean version
> of the same thing (SRAM + `'393` pointers + `'688` compare + `'157` mux + `'574`
> prefetch) lands at 16. Both numbers are the reason the interrupt is worth having.
>
> **13, not 15**, because the FIFO **subsumes** §5.1's second-stage latch: the
> `CD40105B`'s shift-in strobe is the same end-of-frame signal the `'574` uses, and it
> captures the storage register the same way — sixteen deep instead of one. So the
> fallback is 11 − 2 + 4 = 13, exactly the number the earlier revision quoted, arrived at
> for a different reason.

---

## 6. Receive path

### 6.1 What happens on a frame — and what the counter is loaded with

Idle is `CLK` high, `DATA` high, and **the `'193` holding 10**.

**Ten, and it must be an even number.** The counter counts down and borrows on the edge
that carries it from 0 to 15, so a counter loaded with *N* borrows on edge *N*+1. The
frame is eleven edges — edge 1 is the start bit, edges 2–9 are `d0`–`d7`, edge 10 is
parity, edge 11 is the stop bit — so `~TCD` lands on edge 11, at the end of the frame,
only if **N = 10**. And `Q0` (the LSB) must be 0 at the start of the frame so that it
*rises* on the odd edges 1, 3, 5, 7, 9 and its last rise lands during bit 7 (§4.1 idea 2);
10 is even, so it does.

| Preload | `Q0` rises on | Last `Q0` rise | Storage register ends up holding | `~TCD` on |
|---|---|---|---|---|
| **10 (specified)** | odd edges 1, 3, 5, 7, 9 | edge 9 = `d7` | **`d0`–`d7`** | **edge 11, the stop bit** |
| 11 | even edges 2, 4, 6, 8, 10 | edge 10 = parity | `d1`–`d7` + parity — the wrong eight bits | edge 12, which never comes |

So: **preset inputs `A B C D` strapped to `1 0 1 0`**, `MR` **tied low permanently**, and
`~TCD` fed back to `/PL` through the GAL so the counter reloads itself at every frame
boundary. Then:

1. The device pulls `DATA` low and starts clocking. Each falling edge of `CLK` shifts
   `DATA` into the `'595` and counts the `'193` down from 10.
2. `Q0` of the `'193` clocks the `'595`'s storage register. Its **last rising edge lands
   during bit 7**, so the storage register ends up holding `d0`–`d7` — start, parity and
   stop shift through the shift register and are discarded.
3. `~TCD` (borrow) asserts on edge 11 and does **three** things at once: it reloads the
   counter with 10 through `/PL`, it **sets the port's `DR` latch**, and the latch's
   rising edge **clocks the `'574`** (§5.1), capturing the storage register before
   anything can disturb it. `DR` drives `/IRQ` if `IOCTRL.IRQEN`.
4. The driver reads `KDATA`/`MDATA`. The read strobe enables the `'574`'s `/OE` onto the
   data bus **and clears `DR`** — one strobe, both jobs, exactly as Slu4's `/KO`.

> **The `/PL` feedback loop is self-terminating, and the arithmetic says it is wide
> enough.** `~TCD` low → GAL (10–25 ns) → `/PL` low → the `'193` loads 10 → the borrow
> condition is gone → `~TCD` high → GAL → `/PL` high. The pulse the `'193` sees is
> therefore about **2 × t_pd(GAL) + t_pd(load→BO)** ≈ 35–45 ns, against a 74HC193
> `/PL` minimum pulse width of roughly 20 ns at 5 V and 25 °C. Comfortable, and it is the
> loop the Minimal 64x4 already runs. It is also why §5.1 does **not** clock the `'574`
> from `~TCD`: a 40 ns strobe is fine for an asynchronous load and needlessly tight for a
> registered capture.

> ⚠ **The `'193` was never loaded in the previous revision.** It said the counter idles
> "preloaded" without saying with what or by what mechanism, §4.3's datapath drew no
> connection to `/PL` or the preset inputs, and §8.2 specified `KRST`/`MRST` as holding
> the counter "in reset" — but a 74HC193's `MR` forces **0000**, not the preload. A
> down-counter released at 0000 borrows on its very first clock edge, sets `DR` with
> garbage, and every following frame is misaligned by one. Corrected per the 2026-09-04
> design review (IO-P2); §13 step 2's breadboard is where the value 10 gets falsified if
> it is wrong.

**Frame phase is set once, by releasing `KRST` while the line is idle.** The counter has
no timebase and cannot see a frame boundary, so if it is ever released mid-frame its phase
is wrong *permanently* — 11 counts per frame against 11 edges per frame keeps a wrong
phase forever. The driver therefore releases `KRST` only after `IOSTAT` shows the port's
`CLK` idle (§8.1), which is the one condition under which the device is guaranteed not to
be part-way through a frame. §11.2 does this as a side effect of its first transmit; §8.4
makes it a requirement rather than an accident.

Sampling is on the **falling edge** of `CLK`, the middle of the device's data-valid
window — the device changes `DATA` on the rising edge. With 30–50 µs of setup either side
this is about as forgiving as a synchronous interface gets.

### 6.2 No parity check, and no framing check

Adopted from the Minimal 64x4, which checks neither, and the reasoning holds here:

- The link is **30 cm of shielded cable at 16 kHz** between two devices on the same
  supply. This is not a noisy channel.
- **The recovery costs more than the error.** PS/2's per-byte recovery is `FE` (resend),
  which requires a host-to-device frame — §7, ~1 ms of software bit-banging — by which
  time the device has moved on. For a keyboard, a dropped byte is a dropped keystroke; for
  a mouse, §11.3's packet-level resynchronise catches it at no hardware cost.
- Checking parity would need a toggle flip-flop and a compare, and framing would need
  start/stop decodes: **call it two more packages** on an eleven-package card, to detect
  something you cannot usefully act on.

**What replaces it is a software reset.** `IOCTRL.KRST`/`MRST` hold a port's `'193` at
its preload (`/PL` asserted — §6.1, *not* `MR`). A frame that stops half-way — a cable
pulled between bit 4 and bit 5 — leaves the counter mid-count and the port permanently
one, two or seven edges out of phase; the driver notices silence or nonsense and pulses
the reset, releasing it while `CLK` reads idle. That is a control bit, not a watchdog IC,
and it is the same bit §7 needs anyway. The `'595`'s `/SRCLR` is **tied high**: the shift
register's contents before a frame are irrelevant, because only the eight bits shifted in
before the last `Q0` rise survive into storage, so there is nothing to clear.

---

## 7. Transmit — in software, and it costs nothing

**The realisation that removes an entire engine:** transmit happens at initialisation
(twice), and on caps-lock. It is never in a hot path. At 60–100 µs per bit an eleven-bit
frame is **0.7–1.1 ms** of busy-wait — cheap for a driver doing one-time setup, and absurd
to spend a shift register, a sequencer and a timer on.

**What it is not is free**, and §7.1 is the part the earlier revision left out: that
busy-wait has to run with `/IRQ` masked, which makes it the longest interrupt-off window
in the machine and puts it in conflict with `serial.md` §5.1. Read §7.1 before writing the
driver.

The hardware is four bits of `IOCTRL` and four bits of `IOSTAT`:

| Direction | Bits |
|---|---|
| Drive low, through the `7407` | `KCLKD`, `KDATD`, `MCLKD`, `MDATD` |
| Read the line state, through the `'HCT132` | `KCLK`, `KDAT`, `MCLK`, `MDAT` |

**Both halves of that table are in the same polarity, and it is not the line's.** The
`'HCT132` conditioning gates **invert** (§4.2, §8.1), so `IOSTAT.KCLK` reads **1 when the
keyboard `CLK` line is low** and 0 when it is idle-high. The drive bits are true-sense —
`KCLKD` = 1 pulls the line low through the `7407` — so control and status agree with each
other: **1 means "low" in both directions**, and neither means "the line is at logic 1".
The walkthrough below is written in register polarity, which is the polarity a driver can
actually be written from.

The driver then walks §2.3 directly:

1. Set `KRST` — **hold the receive engine at its preload** (§6.1), so the transmit clocks
   do not shift garbage into the `'595` and leave the `'193` permanently out of phase.
   This is the reason that bit exists, and forgetting it is the bug this paragraph is here
   to prevent.
2. **Mask `/IRQ`** — §7.1, and it is not optional.
3. Set `KCLKD` (drives `CLK` low); delay **≥100 µs** in software; set `KDATD` (the start
   bit); clear `KCLKD` (releases `CLK`).
4. For each of eight data bits, then parity, then release: **poll `IOSTAT.KCLK` until it
   reads 1** — that is the line going *low*, the falling edge — then write `KDATD` = 1 for
   a data bit of 0 and `KDATD` = 0 for a data bit of 1. **`KDATD` is the complement of the
   bit being sent**: setting it pulls `DATA` low through the `7407`, and PS/2 `DATA` low is
   a logical 0. The parity bit and the stop bit follow the same rule.
5. Clear `KDATD` (releases `DATA`); poll for the device's ACK — `IOSTAT.KDAT` reading 1,
   i.e. the device pulling `DATA` low, on the next clock.
6. Clear `KRST` **while `IOSTAT.KCLK` still reads 0** — the line idle-high — because that
   is where the receive engine's frame phase is established (§6.1). Then unmask `/IRQ`.
   The device's response (`FA`, or `FE`) arrives through the **normal receive path** and
   appears in `KDATA` like any other byte.

Timeouts are software counters: 15 ms for the device to start clocking, 2 ms for the frame
to complete. No `'4040`, no monostable, no state machine.

> ⚠ **Steps 3–5 previously read in true-line polarity** — "poll `KCLK` for a falling
> edge", "`KDAT` low" — which is correct about the wire and wrong about the register, and
> a driver written from it inverts every poll. All four `'HCT132` gates are consumed by
> conditioning two ports' `CLK` and `DATA` (§4.2, §9), so **nothing on the card can
> re-invert them**: the inversion is load-bearing for the receive path, where the PS/2
> falling edge has to become the rising edge the `'595` and `'193` clock on. Corrected per
> the 2026-09-04 design review (IO-P6); §8.1 states the register polarity once,
> normatively.

### 7.1 Transmit runs with `/IRQ` masked, and that is expensive

> **The previous revision's only concurrency rule was "a transmit must not happen inside
> an interrupt handler".** That is the easy half. The half that matters is the converse:
> **a transmit at task level with interrupts enabled is corrupted *by* interrupt
> handlers.**

Step 4 must present each bit inside one device clock-low half-period — **30–50 µs** by
§2.2's own table. One NitrOS-9 dispatch is 48–191 µs (100–400 cycles at 2.0979 MHz). So a
**single** interrupt landing mid-transmit — one mouse byte, one serial byte, one VBL
tick — overruns one bit slot and usually two or three. The device sees a malformed frame,
answers `FE`, and the driver retries into exactly the same traffic.

And this is not a boot-only path. `ED` (LED update) fires on every caps-lock, num-lock and
scroll-lock keystroke, **during live typing, with the mouse streaming**, for the life of
the machine.

**So the per-bit loop of step 4 runs with `/IRQ` masked**, from step 2 to step 6:
**0.7–1.1 ms of frame, plus the ≥100 µs inhibit and the ACK, so 0.8–1.3 ms per frame.**
Masking `/FIRQ` is neither necessary nor allowed — `audio.md` §8.1's replayer tick
outranks `/IRQ` and must keep running; masking `/IRQ` alone leaves it untouched.

**What that costs the rest of the machine, which is the part worth confronting:**

| Victim | Deadline | Against a 0.8–1.3 ms mask |
|---|---|---|
| **Serial receive at 19,200 baud** | one byte time = 10 / 19,200 = **521 µs** (`serial.md` §5) | **1.5–2.5 byte times missed — an overrun is guaranteed** if the link is busy |
| Serial receive at 9600 | 1.04 ms | one byte, marginal |
| Serial receive at 2400 (period modem) | 4.17 ms | safe |
| **Mouse byte on the other port** | one frame, 660 µs–1.1 ms (§5.1) | **can be torn**, though §5.1 makes the loss a dropped byte rather than silent garbage |
| Keyboard byte | same | same |
| `/FIRQ` replayer tick | — | **unaffected**; `/FIRQ` is not masked |

A masked `ED` in the middle of a file download therefore **loses serial data**, and
`serial.md` §5's flow control does not save it: `/RTS` on a 6551 is a command-register bit
driven from the ISR, and the ISR is precisely what is not running (`serial.md` §5.1 point
4, where the same interaction is recorded from the other side).

**Alternatives, none free, and the choice is the owner's:**

| Option | Cost | Verdict |
|---|---|---|
| **Mask, and accept it** (specified) | one guaranteed serial overrun per LED update at 19,200 | the default, and honest: LED updates are rare and 19,200 is the top of `serial.md` §5's range |
| **Quiesce the mouse first** — `F5`, transmit, `F4` | two *more* masked frames, and the `F5` transmit has the same exposure it is trying to fix | halves the input traffic during the window it does not remove; worth it only if mouse tearing, not serial, is the observed problem |
| **Drop `/IRQ` masking, accept `FE` retries** | a retry budget (§11.2 already allows three) and unbounded latency under load | tempting and wrong: with the mouse streaming, *every* attempt sees traffic, so the retries correlate |
| **Defer the LED update to an idle window** — a flag consumed when both ports and the serial ring buffer are quiet | a few lines of driver, no hardware | **the cheapest real mitigation, and the one to try first** |

This §7.1 ↔ `serial.md` §5.1 interaction was recorded in neither document before the
2026-09-04 design review (IO-P4).

> **What this gives up.** A hardware transmitter would let the driver fire and forget.
> This one blocks the driver for ~1 ms *with `/IRQ` off*. Under NitrOS-9 that means a
> transmit must not happen inside an interrupt handler — it belongs in the driver's
> `SetStt`/init path, at task level. Say so in the driver, because the failure modes are a
> missed serial byte and a torn mouse packet.

---

## 8. Register map — four bytes at `$FF50`

| Off | Name | R/W | Function |
|---|---|---|---|
| `+$0` | `KDATA` | R | keyboard byte. **The read clears `KDR`** and drops `/IRQ` if the mouse is not also pending |
| `+$1` | `MDATA` | R | mouse byte, likewise |
| `+$2` | `IOSTAT` | R | §8.1 |
| `+$3` | `IOCTRL` | W | §8.2 |

Four registers, because §5 has no FIFO to index and §7 has no transmit engine to command.
There is no index/data window — contrast `audio.md` §9.2, which needs one because it has
16 bytes of state per channel; this card has one byte per port.

### 8.1 `IOSTAT` — read

| Bit | Name | Meaning |
|---|---|---|
| 0 | `KDR` | a keyboard byte is waiting in `KDATA` |
| 1 | `MDR` | a mouse byte is waiting in `MDATA` |
| 2 | `KCLK` | keyboard `CLK`: **1 = line low, 0 = line idle-high** — §7, and see the polarity note |
| 3 | `KDAT` | keyboard `DATA`: **1 = line low** — §7 |
| 4 | `MCLK` | mouse `CLK`: **1 = line low** |
| 5 | `MDAT` | mouse `DATA`: **1 = line low** |
| 6–7 | — | read 0 |

> ### ⚠ Bits 2–5 are **inverted line states**, and this is normative
>
> The four `'HCT132` gates that condition `CLK` and `DATA` (§4.2) are **NAND** gates used
> as Schmitt inverters, and that inversion is load-bearing for the receive path: PS/2
> clocks data on the *falling* edge of `CLK`, and the `'595` and `'193` need a *rising*
> edge. The same inverted signals are what the `'244` presents in `IOSTAT`, and **all four
> gates are consumed**, so there is nothing on the card that could re-invert them for the
> status port.
>
> **So a line at rest reads 0, not 1.** The previous revision of this table described bits
> 2–5 as "line state" and called idle-high "a crude presence check" — both of which read
> backwards at the register. Corrected per the 2026-09-04 design review (IO-P6).
>
> **Presence check, correctly stated:** a port with a device attached and idle reads
> `KCLK` = 0 and `KDAT` = 0. A port with **nothing plugged in** reads the same, because
> the 4.7 kΩ pull-ups hold both lines high with or without a device — which is the honest
> version of §14 item 6: these bits detect a device that is *talking* or *inhibited*, not
> one that is *present*. The only real presence test is a `FF` reset that returns `AA`.
>
> **The drive bits of §8.2 are in the same polarity by construction:** `KCLKD` = 1 pulls
> the line low, and reading it back gives `KCLK` = 1. Control and status agree; neither
> agrees with the wire.

**Reading `IOSTAT` has no side effects.** The interrupt handler reads it first to decide
which port to service, and clearing happens only on the `KDATA`/`MDATA` read. That matters
for the shared line: **this card sits second in the `/IRQ` polling chain** (§3.1, and
`machine.md` §4), between video's `VSTAT` and the serial card's `STATUS`, and a
side-effect-free status read is what lets it be polled by a handler that turns out not to
need it. The serial card cannot offer that, which is why it is polled last.

There are no error bits, because §6.2 detects no errors.

### 8.2 `IOCTRL` — write

| Bit | Name | Function | After `/RESET` |
|---|---|---|---|
| 0 | `KCLKD` | drive keyboard `CLK` low — §7 | 0 — released |
| 1 | `KDATD` | drive keyboard `DATA` low — §7 | 0 — released |
| 2 | `MCLKD` | drive mouse `CLK` low | 0 — released |
| 3 | `MDATD` | drive mouse `DATA` low | 0 — released |
| 4 | `KRST` | hold the keyboard `'193` **at its preload** (`/PL` asserted, *not* `MR`) — §6.1, §6.2, §7 step 1 | 0 — running, phase undefined |
| 5 | `MRST` | hold the mouse `'193` at its preload | 0 — running, phase undefined |
| 6 | `IRQEN` | enable `/IRQ` from either `DR` — §3.1 | **0 — masked** |
| 7 | — | reserved, write 0 | 0 |

`IOCTRL` is write-only and the driver must shadow it, which is the conventional cost of
not spending a register on read-back.

**`IOCTRL` is a `74HC273`, not a `'574`** — the same octal D register with an
asynchronous `/MR` in place of the output enable, wired to backplane `/RESET`. The `'574`
the previous revision specified had its `OE` tied active anyway, because `IOCTRL` never
drives the bus, so the swap is **free**: same package, same pin count, same price. §8.4 is
why it is not optional.

### 8.3 The interrupt handler

This card is **second** in the shared-`/IRQ` chain — after video's `VSTAT`, before the
serial card's `STATUS` (§3.1, `machine.md` §4, `serial.md` §7.3):

```
        lda   VSTAT           ; video first - VBL is the system tick
        ...
        lda   IOSTAT          ; then this card - no side effects, safe to probe
        bita  #%00000001      ; keyboard byte?
        beq   ChkMouse
        lda   KDATA           ; the read clears KDR
        ...
ChkSer  lda   SERSTAT         ; serial LAST - this read clears its IRQ and
        ...                   ; returns its error bits; they must be consumed here
```

Two loads and a test on the common path. Compare `audio.md` §13's replayer at 2.7 % of the
CPU: input costs less than the music, which is the right answer for something that happens
when a human moves.

**The order is not this card's to choose**, but this card is why it works: `IOSTAT` can be
read speculatively at no cost, so putting it in the middle costs the VBL path two extra
instructions and costs the serial path nothing.

### 8.4 Reset — what the card does at power-up

The previous revision of this document had **`/RESET` as an input to no IC on the card**.
The serial card gets this right (`serial.md` §6 wires backplane `/RESET` straight to the
6551's `/RES`); this one did not, and the consequences are not cosmetic.

**What was undefined at power-up, and what each undefined bit did:**

| Undefined | Consequence |
|---|---|
| `IOCTRL` bits 0–3 (the `'574`'s power-up state) | the card may come up **holding one or both ports' `CLK` low**, which is the PS/2 inhibit condition — the device never completes its power-on self-test, and the port looks dead in a way no software probe distinguishes from an unplugged connector |
| `IOCTRL` bit 6, `IRQEN` | may come up **1** |
| The GAL's two `DR` latches | may come up **set** |

The third and second together are the boot hang. NitrOS-9 enables `/IRQ` for the VBL
system tick **before** the PS/2 driver initialises `IOCTRL` — the tick is what the
scheduler runs on, so it has to come first — and a `DR` latch stuck set with `IRQEN` stuck
1 holds the shared open-drain `/IRQ` low with **no handler in the chain that can clear
it**: the read that clears `DR` lives in a driver that has not been loaded. That is an
interrupt storm at boot, on the line the system tick uses, and the machine does not get to
a prompt.

**So, two changes, at zero net IC cost:**

1. **`IOCTRL` becomes a `74HC273`** with `/MR` on backplane `/RESET`. All eight bits clear:
   both ports' lines released (devices run their BAT normally), `KRST`/`MRST` clear, and
   **`IRQEN` = 0**, which is the bit that matters.
2. **`/RESET` becomes a GAL input** that clears both `DR` latches. The GAL already forms
   them (§9), so this is one product term on each, not a package.

**What is still undefined after reset, deliberately:** the two `'193`s' *phase*. `/RESET`
leaves `KRST`/`MRST` clear and the counters free-running, so they self-align to some frame
boundary (the `/PL` feedback of §6.1 guarantees a period of 11, not a phase) and may
deliver garbage bytes into `KDATA`/`MDATA`. **That is harmless, because `IRQEN` = 0 and
nothing is listening**, and §11.2's initialisation establishes the phase properly by
asserting `KRST`, waiting for `IOSTAT` to show `CLK` idle, and releasing. Making reset
*also* assert `KRST` would need an inverting stage between the `'273` and `/PL`, or a
negative-logic redefinition of the bit; neither is worth a gate for a state the driver
must establish deliberately anyway.

Corrected per the 2026-09-04 design review (IO-P3).

---

## 9. Chip budget

**Shared (5):**

| # | Part | Function |
|---|---|---|
| 1 | GAL22V10 | decode from `/IOSEL`; four register strobes; the two `DR` latches (set by `~TCD`, cleared by the data read, **cleared by `/RESET`** — §8.4); the two `/PL` terms (`~TCD` or `KRST`/`MRST` — §6.1); `/IRQ` open-drain |
| 2 | **74HC273** | `IOCTRL` — the eight control bits of §8.2, **cleared by backplane `/RESET`** — §8.4 |
| 3 | 74HC244 | `IOSTAT` — six status bits onto the bus, 3-state; bits 2–5 are **inverted line states**, §8.1 |
| 4 | 7407 | open-collector drive, 4 lines of 6 — the whole transmit datapath |
| 5 | 74HCT132 | Schmitt conditioning, 4 gates for 2 ports × `CLK`/`DATA`, **all four consumed** — `HCT` for a reason, §4.2; the inversion is §8.1's polarity |

**Per port, ×2 (6):**

| # | Part | Function |
|---|---|---|
| 6, 7 | 74HC595 | shift + storage register; `~OE` **tied enabled**, `/SRCLR` tied high; drives the `'574`, not the bus |
| 8, 9 | 74HC193 | bit counter; preset strapped to **1010 = 10**, `MR` tied low, `/PL` from the GAL; `Q0` → `RCLK`, `~TCD` → `/PL` and `DR` — §6.1 |
| 10, 11 | **74HC574** | **second-stage latch — §5.1.** Clocked by the `DR` latch at end-of-frame; `QA`–`QH` of the `'595` wired to its `D7`–`D0`, **reversed**; `/OE` from the read strobe drives the data bus |

**Total: 11.** Plus four 4.7 kΩ pull-ups, **two polyfuses**, two mini-DIN-6 connectors,
and the +5 V provisioning below.

> ⚠ **The card was 9 until the 2026-09-04 design review.** The two `'574`s of §5.1 are the
> whole difference; the `'273`-for-`'574` swap of §8.4 is free. Every "nine packages"
> comparison elsewhere in this document has been restated against 11, and the FIFO
> fallback stays at 13 (§5.3).

**Connector power — the row a BOM forgets.** PS/2 devices are powered from the port:
**mini-DIN-6 pin 4 is +5 V, pin 3 is ground.** A keyboard draws **~50–100 mA** (more with
all three LEDs lit), a mouse ~30 mA. Both come off the backplane's +5 V rail, and each
port gets a **polyfuse — 500 mA hold, ~1 A trip** — in series with pin 4, because §14 item
6 already concedes that hot-plug happens and a mini-DIN is exactly the connector people
insert at an angle. A shorted pin 4 without one takes down the whole backplane rail; with
one it takes down a keyboard until it is unplugged. Add 100 nF of local decoupling per
connector while the pen is there.

Three things are *absent* that the earlier revision had, and each is worth naming: **no
`'245`** — the `'574`'s own 3-state output drives the bus, which is what Slu4 does with
the `'595`; **no FIFO** — §5.3; **no transmit engine and no timer** — §7.

> **The GAL is the fitting risk, and it got tighter.** A `GAL22V10` has 10 macrocells.
> Four strobes + two `DR` latches + `/IRQ` + **two `/PL` terms** (§6.1) = **9**, leaving
> **1** for the decode terms — where the earlier revision had 3. The `DR` latches remain
> the awkward part: set by an asynchronous external signal (`~TCD`), cleared synchronously
> by the read strobe and asynchronously by `/RESET`, which is not the shape a registered
> macrocell likes. **If it does not fit, `DR` moves back to a `74HC74` (one package for
> both ports, `/CLR` on `/RESET`) and the card is 12.** §13 step 4, and it is the same
> arithmetic `graphics.md` §18 step 2 insists on doing before layout.
>
> If the fit fails *and* the decode needs more room, the honest fallback is a second GAL
> rather than a squeeze; that is also 12.

---

## 10. The tempting alternative: emulate PIA0's keyboard matrix

Worth taking seriously, because it is the move this project makes elsewhere.

**The idea.** On a real CoCo the keyboard is a 7 × 8 matrix on PIA0: software writes a
column strobe to `$FF02` and reads rows back from `$FF00`; the mouse is a joystick read
through a 6-bit DAC and a comparator. If this card answered at `$FF00`–`$FF03` with a
synthesised matrix, **NitrOS-9's stock CoCo keyboard and joystick drivers would work
unmodified.**

That is the reasoning behind the **GIME-compatible MMU** (`graphics.md` §6.3 — "the
difference between porting the memory manager and configuring it") and the sound card's
**Paula-exact** period reference (`audio.md` §4.1 — every module transfers verbatim). The
pattern is real and has earned its place twice.

**Reject it, and the margin is wider than it was.** Three reasons, increasing in weight:

1. **It costs more than the entire card.** A scan-code → matrix-position table (a 256 × 8
   EPROM or boot-loaded SRAM), an 8 × 8 bit matrix file with set/clear on make/break, the
   `$FF00` decode, and for the mouse a 6-bit magnitude comparator pair plus the
   channel-select logic to fake the joystick's successive-approximation read — **about
   seven packages, against an eleven-package card.** At sixteen packages this was a 44 %
   increase; against eleven it is 64 %, and the thing it buys is *not writing software*.

2. **The compatibility argument is much weaker than it looks.** NitrOS-9 *cannot boot*
   without an MMU and its Level 2 MMU code is GIME-specific and deep in the kernel. A
   keyboard is a **device driver** — small, self-contained, replaceable, which is exactly
   what OS-9's driver model exists for. `graphics.md` §4 already *deleted* colormin's
   bit-exact stock 1bpp path and called it a pure win; this project knows when
   compatibility stops paying.

3. **A 7 × 8 matrix cannot express what a PS/2 keyboard sends.** No `E0` extended keys, so
   no separate cursor cluster, no right-hand modifiers. No rollover beyond the matrix
   geometry. No LED control, no typematic configuration. You would spend seven packages to
   *throw information away*.

The bring-up argument — "stock drivers give you a console before you write one" — is real,
and §13 step 7 answers it more cheaply.

---

## 11. Software

### 11.1 The card does not translate

Raw set-2 scan codes. There is no translation to set 1, because a PC does that in the 8042
and there is no 8042 here — introducing one would be an MCU on a card whose whole argument
is that the protocol is slow enough not to need one.

The driver sees, for `A`: `1C` on press, `F0 1C` on release. Extended keys carry an `E0`
prefix; `Pause` is an **eight**-byte make sequence — `E1 14 77 E1 F0 14 F0 77`, with no
break sequence at all — and is special-cased everywhere, including here.

> ⚠ **This said "seven bytes".** It is eight: `E1 14 77 E1 F0 14 F0 77`. The count matters
> to anyone writing the state machine that swallows it, which is the only reason the
> sequence is mentioned. Corrected per the 2026-09-04 design review (IO-P7).

### 11.2 Initialisation

Every step needs §7's software transmit, and every step blocks — so this runs at task
level, not in the interrupt handler.

| Step | Keyboard | Mouse |
|---|---|---|
| 0 | Set `KRST`; wait for `IOSTAT.KCLK` = 0 (line idle-high, §8.1); this is where the frame phase is established — §6.1, §8.4 | same, `MRST`/`MCLK` |
| 1 | `FF` reset → `FA`, then `AA` (BAT pass) | `FF` reset → `FA`, `AA`, then `00` (device ID) |
| 2 | `F2` read ID → `FA AB 83` | — |
| 3 | `ED` set LEDs, `F3` typematic rate | **`F3` then `$3C` — sample rate 60 /s, §5.2** |
| 4 | `F4` enable scanning | **`F4` enable reporting — without this the mouse is silent** |

Step 0 is new and it is not optional: after `/RESET` the counters are running with an
undefined *phase* (§8.4), and only a `KRST` pulse released during a confirmed idle window
fixes it. Every transmit in steps 1–4 re-establishes it as a side effect (§7 steps 1 and
6), which is why the previous revision got away without saying so.

⚠ **`$3C` was `$28` (40 /s) in the previous revision** — see §5.2 and the design review's
IO-P5. Both are valid `F3` arguments; only one of them is the largest standard rate below
the frame rate.
`FE` (resend) means the device rejected the frame; retry. Three retries and mark the port
dead rather than loop — a missing device produces silence, not `FE`.

### 11.3 Mouse packets, and resynchronisation

Standard 3-byte packet:

| Byte | Content |
|---|---|
| 1 | b0 left, b1 right, b2 middle, **b3 always 1**, b4 X sign, b5 Y sign, b6 X overflow, b7 Y overflow |
| 2 | X delta, 8 bits, sign-extended from byte 1 b4 |
| 3 | Y delta, likewise. **Y is positive upward** — screen coordinates run the other way |

**Byte 1's bit 3 is always 1, and with no parity checking (§6.2) it is the only integrity
handle the driver has.** Track the byte index; if a byte that should be byte 1 arrives
with b3 = 0, the stream has desynchronised — discard until a plausible packet aligns, or
more reliably send `F5`, drain, `F4`. Do the cheap test always and the command pair only
after it fails twice.

⚠ The 4-byte IntelliMouse packet with a Z axis is a **1996** extension, out of period, and
opt-in (a device only sends it after a magic sample-rate knock). Ignoring it is safe.

### 11.4 Where the driver lives

The interrupt handler is §8.3 — read `IOSTAT`, read a byte, push to a ring buffer in
system RAM, return. **The ring buffer moved from hardware to software**, which is the
whole §5 trade: sixteen bytes of 6309 RAM instead of four `CD40105B`. What §5.1 keeps in
hardware is not the queue — it is the one byte the driver has already been told about, and
two `'574`s is the price of that byte being the byte it was told about.

---

## 12. Period audit

| Part | First available | Verdict |
|---|---|---|
| PS/2 interface, 6-pin mini-DIN | **1987** (IBM PS/2) | in period, contemporary with the VGA connector `graphics.md` §15 justifies |
| GAL22V10 | 1986 | in period; the machine already uses 9 of them |
| 74HC595, 74HC193, 74HC244, 74HC574, 74HC273 | 1980s HC family | in period |
| 74HCT132 | 1980s HCT family | in period |
| 7407 | 1970s | in period, and the open-collector part everyone used |
| Polyfuse (PPTC) on each port's +5 V, §9 | Raychem PolySwitch, **1981** | in period, and the standard answer for a hot-pluggable powered connector |
| CD40105B *(fallback only, §5)* | early 1980s (RCA) | in period; **sourcing is the problem, not the date** |

**Nothing in this card is anachronistic**, and it is the only card in the machine of which
that is true without a footnote — video needs the 25.175 MHz VGA-clock argument and audio
needs the `AD7545A` → `LTC7545A` substitution.

---

## 13. Build order

| # | Step | Exit criterion |
|---|---|---|
| 0 | **Settle `machine.md` §5 items 1 and 2** — `$FF50`–`$FF53`, and `/IRQ` as a third source | `machine.md` records both as taken rather than proposed |
| 1 | **Measure the protocol.** Scope a real keyboard and mouse: clock rate, half-periods, **rise/fall times (§4.2)**, request-to-first-clock, and — **the number §5's whole no-FIFO argument turns on — the inter-byte gap *inside* a 3-byte mouse packet**, at 60 /s and at 200 /s, on every mouse to hand | §2.2's ⚠ table replaced with measured numbers; a PS/2 reference added to `reference/`; **the intra-packet gap recorded as a number, because if it is comfortably longer than a frame time then §5.1's `'574`s are insurance rather than a fix, and if it is 150 µs then they are the card** |
| 2 | **Breadboard the Minimal 64x4 receiver verbatim** — one `'595`, one `'193`, one `'HCT132`, one port, real keyboard — **with the preset strapped to 10 and `~TCD` looped to `/PL`** (§6.1) | raw set-2 codes read out correctly, **including the reversed bit order and the `Q0`→`RCLK` timing**; a preset of 11 demonstrably reads the wrong eight bits, which is what confirms the value rather than assuming it. Then add the `'574` and show that a byte survives the next frame's start bit. This step exists to confirm §4.1 and falsify §6.1 before generalising either. |
| 3 | **Software transmit** on the same breadboard, `7407` and two GPIO lines | `FF` returns `FA` then `AA`; `ED` visibly lights the keyboard LEDs |
| 4 | **Fit the GAL** — four strobes, two `DR` latches, `/IRQ` | fits one `GAL22V10`, or the card becomes 10 with a `'74` — §9 |
| 5 | **Mouse: `F3`/`$3C` then `F4`** (§5.2) | 3-byte packets at 60 /s, correct deltas, no desync over an hour |
| 6 | **Card rev A** on the STM32 bus exerciser (`graphics.md` §16.1) — no 6309 core needed | both ports read back; `IOSTAT` tracks **in the polarity §8.1 specifies**; `/IRQ` asserts and clears; **pulse `/RESET` with a device attached and confirm `IOCTRL` reads back as clear, both ports' lines released, and `/IRQ` high** — §8.4 |
| 7 | **Polled driver against a monitor ROM**, software loop, no VBL, keyboard only | keystrokes echo to the console — the step that does not depend on the video card |
| 8 | **NitrOS-9 driver on `/IRQ`** | **measure the dispatch cost (§14 item 3)**; typing and mousing under a running replayer with no lost keystrokes, no mouse desync, and no lost replayer ticks |
| 9 | **Transmit against live traffic** — `ED` LED updates while the mouse streams *and* the serial card runs a 19,200-baud download (§7.1) | the masked window is measured, not estimated; the serial overrun count is recorded; the mitigation chosen from §7.1's table. **This is the step that closes the `serial.md` §5 interaction, and it needs both cards on the backplane** |

**Step 1 gates everything** — and it now gates §5 specifically, because the intra-packet
inter-byte gap is the measurement the no-FIFO decision rests on. **Step 8 is the one that
can send the design back to §5.3's FIFO**, and **step 9 is the one that can send §7.1 back
to the owner.**

---

## 14. Open items

1. **No PS/2 reference document is in `reference/`.** Every timing figure in §2.2 is
   recalled. Add Chapweske's protocol document or an IBM PS/2 technical reference, and
   re-grade §1. **Blocks §13 step 4.**

2. **`$FF50`–`$FF53` takes a quarter of the disk controller's reservation** (§3.2). Better
   than the half the previous revision wanted, but still a claim on a region nobody has
   specified. Raise it in `machine.md` before the backplane is laid out.

3. **NitrOS-9's interrupt dispatch cost is a guess**, and §3.1's entire budget rests on
   it. At the specified 60 /s mouse rate, 100 cycles gives 1.1 %; 400 gives 4.6 %; 800
   would give 9.2 % and change the answer. **Measure it at §13 step 8** — this is the
   number that decides first whether §5.2 drops back to 40 /s, and then whether §5.3's
   FIFO comes back.

4. **The `DR` latch may not fit the GAL** (§9), and the margin is now one macrocell rather
   than three, because §6.1's two `/PL` terms moved into the same package. Asynchronous
   set, synchronous clear *and* an asynchronous `/RESET` clear is not a registered
   macrocell's natural shape. Costs one `74HC74` if not, and the card is 12.

   **In the same package:** the `'193` preload value (10) and the `/PL` feedback pulse
   width of §6.1 are *derived*, not measured — the arithmetic gives 35–45 ns against a
   ~20 ns minimum, on datasheet numbers nobody has read in this repo. §13 step 2 falsifies
   both on a breadboard rather than a board respin, so it is cheap to be wrong.

5. **`IOCTRL` is write-only** (§8.2) and must be shadowed by the driver. If §13 step 4
   finds GAL capacity spare, making it readable is worth more than it costs.

6. **Hot-plug is not designed for.** `KCLK`/`MCLK` (§8.1) is a **weaker** presence check
   than the previous revision claimed — the pull-ups read the same with the connector
   empty — so the only real probe is an `FF` that returns `AA`, which costs a §7.1 masked
   window. Decide whether the driver re-initialises on a transition or the card simply
   requires a reset. §9's per-port polyfuse is the *electrical* half of this item and is
   now specified; the software half is not.

7. **A third port** is no longer cheap in the way it was. With per-port `'595` + `'193` +
   `'574` it is **+3 ICs** plus `IOSTAT`/`IOCTRL` bits that are already nearly full, and
   the GAL has one macrocell of margin (§9). Decide before layout, not after.

8. **No 6522 datasheet is in `reference/`.** §4.5 rejects the VIA route primarily on I/O
   space, which needs no datasheet — but its points 2 and 3, the eight-versus-eleven-bit
   shift register and the external-clock errata, are recalled lore. If `machine.md` §5
   item 1 ever widens the I/O window, that rejection must be re-argued against a real
   datasheet before it is trusted.

9. **The `/IRQ`-masked transmit window (§7.1) is a machine-level trade this card cannot
   settle alone.** 0.8–1.3 ms with `/IRQ` off guarantees a serial overrun at 19,200 baud
   (`serial.md` §5) every time a caps-lock LED is updated during a download. Four options
   are tabulated in §7.1; **the owner picks one**, and §13 step 9 measures whichever is
   picked. Doing nothing is also an option — LED updates during downloads are rare — but
   it should be chosen rather than defaulted into, which is how it got missed.

10. **Slu4's work is CC BY-NC-SA 4.0.** §4.1 adopts *circuit ideas* — the storage-register
   trick, `Q0`→`RCLK`, the reversed bit order, the Schmitt-input requirement — which is
   not copying his files, but if this project is ever published the attribution in §4.1
   and §15 should stay, and the **non-commercial** clause is worth a second look before
   anyone sells a board.

---

## 15. Sources and cross-references

| | |
|---|---|
| **Minimal 64x4 Rev 1.4 Redux, sheet 3/9 "PS/2 Receiver"** | Carsten Herting (slu4), CC BY-NC-SA 4.0. The origin of §4.1, §4.2 and §6.1. Local copy: `~/code/colormin/minimal/Minimal-64x4-Home-Computer/` |
| **Andy Hertzfeld, *Apple II Mouse Card*, folklore.org, June 1981** | Burrell Smith's two-chip design. §4.4 takes the interrupt argument and the derive-it-from-the-bus habit, and rejects the interrupt-per-notch mouse on §4.4(c)'s arithmetic. `reference/articles/folklore-apple2-mouse-card.pdf` |
| [`machine.md`](../../../docs/machine.md) | §5 items 1 and 2 — the two blockers §3 answers |
| [`graphics.md`](../../../video/docs/graphics.md) | §12 the `/IRQ` sources this card joins; §16.1 the bus exerciser; §17 the backplane and the `$FF` map; §18 the build-order form |
| [`audio.md`](../../../audio/docs/audio.md) | §8.1 why `/FIRQ` is exclusive and `/IRQ` is not; §9 the register-map conventions; §10 the chip-budget form |
| [`plan.md`](../../../cpu/docs/plan.md) | §3.3 the bus timing this card's read path sits inside |
| [`serial.md`](../../serial/docs/serial.md) | §5 the flow-control mechanism §7.1's masked window defeats, and the other half of that interaction; §7.3 why serial is polled last on the shared `/IRQ`; §6 the `/RESET` wiring §8.4 should have copied |
| [`docs/design-review.md`](../../../docs/design-review.md) | §5, 2026-09-04. IO-P1 (§5), IO-P2 (§6.1), IO-P3 (§8.4), IO-P4 (§7.1), IO-P5 (§5.2), IO-P6 (§8.1), IO-P7 (§11.1), IO-P8 (§9) |
| Adam Chapweske, *The PS/2 Mouse/Keyboard Protocol* | the community reference for §2. **Not in `reference/` — §14 item 1.** |
| ARM PrimeCell PS/2 Keyboard/Mouse Interface, `DDI0096` | an independent description of the same frame format |
