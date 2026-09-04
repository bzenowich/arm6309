# PS/2 Keyboard and Mouse for an arm6309 Machine
## Nine ICs, After the Minimal 64x4 Showed It Could Be Three

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
forces: a transmit path, a second port, and an address decoder. That comes to **nine**.

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
| **How much hardware does receiving PS/2 actually take?** | **Two packages per port** — a `'595` and a `'193` — plus a shared `'132`. Taken from the Minimal 64x4. | §4.1, §6 |
| **Would a quadrature mouse be cheaper, as on Burrell Smith's Apple II card?** | **One package cheaper and unaffordable.** Interrupt-per-notch scales with hand speed — up to 4,000/s, against PS/2's fixed 120. | §4.4(c) |
| **Would one 6522 VIA per port replace most of this?** | **Four packages instead of nine, and rejected on I/O space:** two VIAs decode 32 bytes against a 4-byte budget. | §4.5 |
| **How does the card get the CPU's attention?** | **`/IRQ`, as a third source.** `/IRQ` is already an open-drain line with two sources (VBL, raster compare); only `/FIRQ` is exclusive. | §3.1 |
| **What does that cost?** | **~0.9 % of the CPU while input is actually happening**, zero when it is not — with the mouse pinned at 40 samples/s. | §3.1, §5 |
| **Why is there no FIFO?** | Because with an interrupt there is nothing to buffer. The `'595`'s **storage register is one byte deep for free**, and that is the whole requirement. | §5 |
| **Why is the mouse set to 40 samples/s?** | You cannot display a pointer faster than the 70 Hz frame rate, so reporting faster only buys interrupt load. | §5 |
| **Does the card check parity?** | **No.** 30 cm of shielded cable at 16 kHz, and the only recovery costs a round trip worth more than the error. Slu4 checks nothing either. | §6.2 |
| **Does the card need to transmit?** | **Yes** — a mouse is silent until `F4`. **In software**, through two control bits and a `7407`. | §7 |
| **Where does it live in the `$FF` map?** | **`$FF50`–`$FF53`, four bytes** — a quarter of the region pencilled in for a disk controller, not half. | §3.2 |
| **Does it decode scan codes?** | **No.** Raw set-2 bytes; translation is the driver's job. | §11.1 |
| **Emulate the CoCo's PIA0 keyboard matrix so stock NitrOS-9 drivers work?** | **No** — it would cost more than the entire card. | §10 |
| **IC count** | **9.** Was 16 before reading the Minimal 64x4. | §9 |

**Net: 9 ICs** — one GAL22V10, two `'595`, two `'193`, and four glue packages — against
video's 33 and audio's 35.

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
- `ED` (LEDs), `F3` (sample rate — §5 needs it), `FF` (reset) and the mouse resynchronise
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
| Interrupt rate, mouse at **40 samples/s** (§5) | 120 /s while moving |
| Combined, worst realistic case | **~180 /s** |
| Cost at 100 cycles/interrupt (bare metal) | **0.9 %** of a 2.098 MHz CPU |
| Cost at 400 cycles/interrupt (NitrOS-9 dispatch ⚠) | **3.4 %** |
| Cost when nobody is touching anything | **zero** |

> **The 400-cycle figure is a guess and it is the weakest number in this document.**
> If NitrOS-9's dispatcher is worse than that, 3.4 % becomes 7 % and this decision
> should be revisited — §14 item 3, and §13 step 8 measures it. The fallback is §5's
> FIFO, which trades four packages for the interrupt load.

**The earlier revision of this document polled from the VBL tick instead**, to avoid
touching the interrupt structure at all. That was the wrong trade: it cost a 16-byte FIFO
per port — **four of sixteen packages** — to save an interrupt on a line that already had
two sources. Reading the Minimal 64x4 is what made that visible.

Polling remains a supported fallback and is how §13 step 7 brings the card up before the
video card exists — but with one byte of buffering it is only sound for the keyboard.

### 3.2 `$FF50`–`$FF53` — a quarter of the disk controller's window, not half

The geographic decode spans `$FF40`–`$FF7F` (`graphics.md` §17). Video has
`$FF60`–`$FF7F`; `audio.md` §9.1 proposes `$FF40`–`$FF4F`; `$FF50`–`$FF5F` is pencilled
in for a disk controller that does not exist.

**Propose `$FF50`–`$FF53` — four bytes** — leaving `$FF54`–`$FF5F`, twelve bytes, for the
disk controller. Four is enough because §8 has exactly four registers, and it has four
registers because §5 has no FIFO to index and §7 has no transmit engine to command. A
WD1773 is four registers plus a latch, so twelve bytes leaves the disk controller room it
would not otherwise have had.

Decode is geographic from the backplane's per-slot `/IOSEL`, so the base is a jumper.

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

3. **The bit order is reversed in the wiring.** PS/2 is LSB-first, so shifting into a
   `'595` leaves the byte backwards; `QA`→`BUS7` … `QH`→`BUS0` fixes it for free.
   Slu4's note: *"The order of the bits is intentionally reversed."* Costs nothing,
   saves a software reverse on every byte.

4. **Data-ready is a NAND SR latch in the spare gates** of the same `'132` doing the
   input conditioning, set by the counter's borrow and cleared by the read strobe.

**What the Minimal 64x4 does not do**, and what therefore accounts for the difference
between its three packages and this card's nine:

| | Minimal 64x4 | this card | cost |
|---|---|---|---|
| Ports | 1 (keyboard) | **2** (keyboard + mouse) | +2 ICs |
| Direction | receive only | **bidirectional** — a mouse needs `F4` | +1 IC (`7407`); the rest is software |
| Bus attachment | **microcode strobes** `/KO`, and `PS2_DR` wired to a **CPU branch flag** | memory-mapped, address-decoded | +3 ICs |
| Parity / framing | none | **none** — §6.2 | 0 |
| Buffering | 1 byte (the `'595` storage) | **1 byte** — §5 | 0 |

**Three of the six added packages exist only because the 6309 is a fixed CPU.** Slu4
could give his machine an instruction that reads the keyboard and a branch that tests
data-ready; `arm6309` cannot, because being bit-compatible with a real HD6309E is the
entire project. That is the honest accounting: this is not a worse design, it is the same
design paying a bus tax the Minimal 64x4 does not owe.

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
         │  4.7k
  CLK ───┴──►['HCT132 Schmitt]──┬──► 74HC193  ── Q0 ──► RCLK ─┐
         ◄───[7407 open-coll.]  │    counts down            │
                                └──► SRCLK              74HC595
  DATA ──┬──►['HCT132 Schmitt]───────► SER              shift+storage
         ◄───[7407 open-coll.]        ~TCD ──► DR latch    │  ~OE
                                              (in GAL)     │   ▲
                                                     QA..QH│   │ read strobe
                                                  reversed ▼   │
                                                        D0–D7 ─┘
```

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
a few bits of the `'244` that already exists — call it **one package instead of the two
(`'595` + `'193`) the PS/2 mouse port costs.**

**Take the cheaper option and the machine falls over.** Interrupt-per-notch scales with
*hand velocity*, and it is unbounded:

| | Interrupts/s |
|---|---|
| Quadrature, 100 CPI, slow (2 in/s), both axes | 400 |
| Quadrature, 100 CPI, brisk (5 in/s) | 1,000 |
| Quadrature, 200 CPI, fast (10 in/s) | **4,000** |
| **PS/2 at 40 samples/s (§5)** | **120, whatever the hand does** |

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
**four packages against this card's nine**, and a 6522 is a 1977 part — comfortably inside
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


## 5. Buffering — why one byte is enough

This is where the earlier revision of this document was wrong, and it is worth showing the
arithmetic that changed.

**The `'595`'s storage register holds one byte while the next frame shifts in.** That buys
one full frame time — **660 µs at the slowest clock rate** — to service the port. The only
question is whether the CPU can be there inside 660 µs.

- **With `/IRQ` (§3.1): trivially yes.** Interrupt latency on a 6309 is instruction-time
  plus dispatch, three orders of magnitude inside the window. **No FIFO. No packages.**
- **Polling at the 70.09 Hz VBL tick: no** — 14.27 ms is 21 frame times. That is what
  forced the earlier design's 16-byte FIFO, and it is four packages of tail wagging one
  dog.

**And pin the mouse at 40 samples/s** (`F3`), not the 100 default:

| Mouse rate | Bytes/s | Interrupts/s | Per 14.27 ms frame |
|---|---|---|---|
| 200 /s (max) | 600 | 600 | 8.6 |
| 100 /s (default) | 300 | 300 | 4.3 |
| **40 /s (specified)** | **120** | **120** | **1.7** |
| 20 /s | 60 | 60 | 0.9 |

**You cannot display a pointer faster than the frame rate.** At 70.09 Hz, a mouse
reporting at 100 or 200 /s is generating updates that get composited away before anything
draws them; all it buys is interrupt load. 40 /s sits just under the frame rate, so every
report is one the display can actually use, and it cuts §3.1's interrupt budget by 60 %.

> **The fallback, if §13 step 8 finds the interrupt load unacceptable:** two
> `CD40105B` per port — asynchronous 16 × 4 FIFO with data-ready and data-full flags,
> no pointer logic — restoring the polled design at **13 ICs**. The part is genuinely
> period (RCA, early 1980s) and genuinely hard to source now; the all-jellybean version
> of the same thing (SRAM + `'393` pointers + `'688` compare + `'157` mux + `'574`
> prefetch) lands at 16. Both numbers are the reason the interrupt is worth having.

---

## 6. Receive path

### 6.1 What happens on a frame

Idle is `CLK` high, `DATA` high, the `'193` preloaded.

1. The device pulls `DATA` low and starts clocking. Each falling edge of `CLK` shifts
   `DATA` into the `'595` and counts the `'193` down.
2. `Q0` of the `'193` clocks the `'595`'s storage register. Its **last rising edge lands
   during bit 7**, so the storage register ends up holding `d0`–`d7` — start, parity and
   stop shift through the shift register and are discarded.
3. `~TCD` (borrow) asserts at the end of the frame and **sets the port's `DR` latch**,
   which drives `/IRQ` if `IOCTRL.IRQEN`.
4. The driver reads `KDATA`/`MDATA`. The read strobe enables the `'595`'s `~OE` onto the
   data bus **and clears `DR`** — one strobe, both jobs, exactly as Slu4's `/KO`.

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
  start/stop decodes: **call it two more packages** on a nine-package card, to detect
  something you cannot usefully act on.

**What replaces it is a software reset.** `IOCTRL.KRST`/`MRST` hold a port's `'193` and
`'595` in reset. A frame that stops half-way — a cable pulled between bit 4 and bit 5 —
leaves the counter mid-count and the port dead; the driver notices silence and pulses the
reset. That is a control bit, not a watchdog IC, and it is the same bit §7 needs anyway.

---

## 7. Transmit — in software, and it costs nothing

**The realisation that removes an entire engine:** transmit happens at initialisation
(twice), and on caps-lock. It is never in a hot path. At 60–100 µs per bit an eleven-bit
frame is **0.7–1.1 ms** of busy-wait — trivial for a driver doing one-time setup, and
absurd to spend a shift register, a sequencer and a timer on.

The hardware is four bits of `IOCTRL` and four bits of `IOSTAT`:

| Direction | Bits |
|---|---|
| Drive low, through the `7407` | `KCLKD`, `KDATD`, `MCLKD`, `MDATD` |
| Read the line state, through the `'HCT132` | `KCLK`, `KDAT`, `MCLK`, `MDAT` |

The driver then walks §2.3 directly:

1. Set `KRST` — **hold the receive engine in reset**, so the transmit clocks do not shift
   garbage into the `'595` and desynchronise the `'193`. This is the reason that bit
   exists, and forgetting it is the bug this paragraph is here to prevent.
2. Set `KCLKD`; delay **≥100 µs** in software; set `KDATD`; clear `KCLKD`.
3. For each of eight data bits, then parity, then release: poll `KCLK` for a falling edge,
   set or clear `KDATD`.
4. Release `KDATD`; poll for the device's ACK — `KDAT` low on the next clock.
5. Clear `KRST`. The device's response (`FA`, or `FE`) arrives through the **normal
   receive path** and appears in `KDATA` like any other byte.

Timeouts are software counters: 15 ms for the device to start clocking, 2 ms for the frame
to complete. No `'4040`, no monostable, no state machine.

> **What this gives up.** A hardware transmitter would let the driver fire and forget.
> This one blocks the driver for ~1 ms. Under NitrOS-9 that means a transmit must not
> happen inside an interrupt handler — it belongs in the driver's `SetStt`/init path, at
> task level. Say so in the driver, because the failure mode is a missed replayer tick.

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
| 2 | `KCLK` | keyboard `CLK` line state — §7, and idle-high is a crude presence check |
| 3 | `KDAT` | keyboard `DATA` line state — §7 |
| 4 | `MCLK` | mouse `CLK` line state |
| 5 | `MDAT` | mouse `DATA` line state |
| 6–7 | — | read 0 |

**Reading `IOSTAT` has no side effects.** The interrupt handler reads it first to decide
which port to service, and clearing happens only on the `KDATA`/`MDATA` read.

There are no error bits, because §6.2 detects no errors. A driver that wants to know
whether anything is plugged in watches `KCLK`/`MCLK` for idle-high.

### 8.2 `IOCTRL` — write

| Bit | Name | Function |
|---|---|---|
| 0 | `KCLKD` | drive keyboard `CLK` low — §7 |
| 1 | `KDATD` | drive keyboard `DATA` low — §7 |
| 2 | `MCLKD` | drive mouse `CLK` low |
| 3 | `MDATD` | drive mouse `DATA` low |
| 4 | `KRST` | hold the keyboard receive engine in reset — §6.2, §7 step 1 |
| 5 | `MRST` | hold the mouse receive engine in reset |
| 6 | `IRQEN` | enable `/IRQ` from either `DR` — §3.1 |
| 7 | — | reserved, write 0 |

`IOCTRL` is write-only and the driver must shadow it, which is the conventional cost of
not spending a register on read-back.

### 8.3 The interrupt handler

```
        lda   IOSTAT
        bita  #%00000001      ; keyboard byte?
        beq   ChkMouse
        lda   KDATA           ; the read clears KDR
        ...
```

Two loads and a test on the common path. Compare `audio.md` §13's replayer at 2.7 % of the
CPU: input costs less than the music, which is the right answer for something that happens
when a human moves.

---

## 9. Chip budget

**Shared (5):**

| # | Part | Function |
|---|---|---|
| 1 | GAL22V10 | decode from `/IOSEL`; four register strobes; the two `DR` latches (set by `~TCD`, cleared by the data read); `/IRQ` open-drain |
| 2 | 74HC574 | `IOCTRL` — the eight control bits of §8.2 |
| 3 | 74HC244 | `IOSTAT` — six status bits onto the bus, 3-state |
| 4 | 7407 | open-collector drive, 4 lines of 6 — the whole transmit datapath |
| 5 | 74HCT132 | Schmitt conditioning, 4 gates for 2 ports × `CLK`/`DATA` — **`HCT` for a reason, §4.2** |

**Per port, ×2 (4):**

| # | Part | Function |
|---|---|---|
| 6, 7 | 74HC595 | shift + storage register; `QA`–`QH` wired to `BUS7`–`BUS0`, **reversed**; `~OE` from the read strobe drives the data bus directly |
| 8, 9 | 74HC193 | bit counter; `Q0` → `RCLK`, `~TCD` → `DR` |

**Total: 9.** Plus four 4.7 kΩ pull-ups and two mini-DIN-6 connectors.

Three things are *absent* that the earlier revision had, and each is worth naming: **no
`'245`** — the `'595`'s own 3-state output drives the bus, which is what Slu4 does; **no
FIFO** — §5; **no transmit engine and no timer** — §7.

> **The GAL is the fitting risk.** A `GAL22V10` has 10 macrocells. Four strobes + two
> `DR` latches + `/IRQ` = 7, leaving 3 for the decode terms — comfortable, but the `DR`
> latches are set by an asynchronous external signal (`~TCD`) and cleared synchronously,
> which is not the shape a registered macrocell likes. **If it does not fit, `DR` moves
> back to a `74HC74` and the card is 10.** §13 step 4, and it is the same arithmetic
> `graphics.md` §18 step 2 insists on doing before layout.

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
   seven packages, against a nine-package card.** At sixteen packages this was a 44 %
   increase; against nine it is 78 %, and the thing it buys is *not writing software*.

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
prefix; `Pause` is a seven-byte sequence and is special-cased everywhere, including here.

### 11.2 Initialisation

Every step needs §7's software transmit, and every step blocks — so this runs at task
level, not in the interrupt handler.

| Step | Keyboard | Mouse |
|---|---|---|
| 1 | `FF` reset → `FA`, then `AA` (BAT pass) | `FF` reset → `FA`, `AA`, then `00` (device ID) |
| 2 | `F2` read ID → `FA AB 83` | — |
| 3 | `ED` set LEDs, `F3` typematic rate | **`F3` then `28` — sample rate 40 /s, §5** |
| 4 | `F4` enable scanning | **`F4` enable reporting — without this the mouse is silent** |

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
whole §5 trade: sixteen bytes of 6309 RAM instead of four `CD40105B`.

---

## 12. Period audit

| Part | First available | Verdict |
|---|---|---|
| PS/2 interface, 6-pin mini-DIN | **1987** (IBM PS/2) | in period, contemporary with the VGA connector `graphics.md` §15 justifies |
| GAL22V10 | 1986 | in period; the machine already uses 9 of them |
| 74HC595, 74HC193, 74HC244, 74HC574 | 1980s HC family | in period |
| 74HCT132 | 1980s HCT family | in period |
| 7407 | 1970s | in period, and the open-collector part everyone used |
| CD40105B *(fallback only, §5)* | early 1980s (RCA) | in period; **sourcing is the problem, not the date** |

**Nothing in this card is anachronistic**, and it is the only card in the machine of which
that is true without a footnote — video needs the 25.175 MHz VGA-clock argument and audio
needs the `AD7545A` → `LTC7545A` substitution.

---

## 13. Build order

| # | Step | Exit criterion |
|---|---|---|
| 0 | **Settle `machine.md` §5 items 1 and 2** — `$FF50`–`$FF53`, and `/IRQ` as a third source | `machine.md` records both as taken rather than proposed |
| 1 | **Measure the protocol.** Scope a real keyboard and mouse: clock rate, half-periods, **rise/fall times (§4.2)**, inter-frame gap, request-to-first-clock | §2.2's ⚠ table replaced with measured numbers; a PS/2 reference added to `reference/` |
| 2 | **Breadboard the Minimal 64x4 receiver verbatim** — one `'595`, one `'193`, one `'HCT132`, one port, real keyboard | raw set-2 codes read out correctly, **including the reversed bit order and the `Q0`→`RCLK` timing**. This step exists to confirm §4.1 before generalising it. |
| 3 | **Software transmit** on the same breadboard, `7407` and two GPIO lines | `FF` returns `FA` then `AA`; `ED` visibly lights the keyboard LEDs |
| 4 | **Fit the GAL** — four strobes, two `DR` latches, `/IRQ` | fits one `GAL22V10`, or the card becomes 10 with a `'74` — §9 |
| 5 | **Mouse: `F3`/`28` then `F4`** | 3-byte packets at 40 /s, correct deltas, no desync over an hour |
| 6 | **Card rev A** on the STM32 bus exerciser (`graphics.md` §16.1) — no 6309 core needed | both ports read back; `IOSTAT` tracks; `/IRQ` asserts and clears |
| 7 | **Polled driver against a monitor ROM**, software loop, no VBL, keyboard only | keystrokes echo to the console — the step that does not depend on the video card |
| 8 | **NitrOS-9 driver on `/IRQ`** | **measure the dispatch cost (§14 item 3)**; typing and mousing under a running replayer with no lost keystrokes, no mouse desync, and no lost replayer ticks |

**Step 1 gates everything**, and **step 8 is the one that can send the design back to §5's
FIFO.**

---

## 14. Open items

1. **No PS/2 reference document is in `reference/`.** Every timing figure in §2.2 is
   recalled. Add Chapweske's protocol document or an IBM PS/2 technical reference, and
   re-grade §1. **Blocks §13 step 4.**

2. **`$FF50`–`$FF53` takes a quarter of the disk controller's reservation** (§3.2). Better
   than the half the previous revision wanted, but still a claim on a region nobody has
   specified. Raise it in `machine.md` before the backplane is laid out.

3. **NitrOS-9's interrupt dispatch cost is a guess**, and §3.1's entire budget rests on
   it. 100 cycles gives 0.9 %; 400 gives 3.4 %; 800 would give 6.9 % and change the
   answer. **Measure it at §13 step 8** — this is the number that decides whether §5's
   FIFO comes back.

4. **The `DR` latch may not fit the GAL** (§9) — asynchronous set, synchronous clear is
   not a registered macrocell's natural shape. Costs one `74HC74` if not.

5. **`IOCTRL` is write-only** (§8.2) and must be shadowed by the driver. If §13 step 4
   finds GAL capacity spare, making it readable is worth more than it costs.

6. **Hot-plug is not designed for.** `KCLK`/`MCLK` idle-high (§8.1) is a crude presence
   check and nothing more. Decide whether the driver re-initialises on a transition or the
   card simply requires a reset.

7. **A third port** is no longer cheap in the way it was. With per-port `'595` + `'193`
   it is +2 ICs plus `IOSTAT`/`IOCTRL` bits that are already nearly full. Decide before
   layout, not after.

8. **No 6522 datasheet is in `reference/`.** §4.5 rejects the VIA route primarily on I/O
   space, which needs no datasheet — but its points 2 and 3, the eight-versus-eleven-bit
   shift register and the external-clock errata, are recalled lore. If `machine.md` §5
   item 1 ever widens the I/O window, that rejection must be re-argued against a real
   datasheet before it is trusted.

9. **Slu4's work is CC BY-NC-SA 4.0.** §4.1 adopts *circuit ideas* — the storage-register
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
| Adam Chapweske, *The PS/2 Mouse/Keyboard Protocol* | the community reference for §2. **Not in `reference/` — §14 item 1.** |
| ARM PrimeCell PS/2 Keyboard/Mouse Interface, `DDI0096` | an independent description of the same frame format |
