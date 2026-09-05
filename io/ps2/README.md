# `io/ps2/` — PS/2 keyboard and mouse

Two PS/2 ports, **11 ICs**, no MCU, no FIFO, no transmit engine.

Paths below are relative to this directory.

| | |
|---|---|
| [`docs/ps2.md`](docs/ps2.md) | the card — protocol, the borrowed receiver, register map, IC budget |

## Where the design comes from

**§4.1 is the important section.** Slu4's Minimal 64x4 receives PS/2 in **three
packages** — one `74HC595`, one `74HC193`, one `74HCT132` — and reading its schematic cut
this card from 16 ICs to 9. Four ideas transfer intact:

- The `'595`'s **separate storage register** solves the 11-bit-frame-into-8-bit-register
  problem for free. ⚠ ~~and gives one byte of buffering at zero cost~~ — **it does not**;
  see below.
- **`Q0` of the bit counter drives `RCLK`**, so no decode of "the ninth clock" is needed.
- **The bit order is reversed in the wiring** — PS/2 is LSB-first, so `QA`→`BUS7`.
- **Schmitt inputs are mandatory, and `HCT` not `HC`**: PS/2 edges can exceed the 400 ns
  rise-time limit of a plain HC input, and a 3.3 V device does not clear `HC`'s `V_IH`.

What it does *not* do accounts for the difference: one port, receive-only (so no mouse —
a mouse is silent until it is told `F4`), and bus-attached by **microcode strobes and a
CPU branch flag** rather than an address decoder. Three of this card's eight extra packages
are the tax for the 6309 being a fixed CPU, and two more are the tax for not having that
branch flag either.

> ### ⚠ The buffering was not free, and the card is 11, not 9
>
> **The 2026-09-04 design review (`../../docs/design-review.md` §5, IO-P1) overturned this
> card's central claim.** The second bullet above is why: `RCLK` is `Q0` of the bit
> counter, and `Q0` toggles on **every clock edge of every frame**, so the storage register
> is re-copied throughout the *next* frame — and edge 1 of frame N+1 is its **start bit**.
> Byte N survives from edge 9 of frame N to edge 1 of frame N+1, which means the service
> deadline was never the 660 µs of frame time the document claimed; it was the **inter-byte
> gap**, which the host does not control and which inside a 3-byte mouse packet can be a
> couple of hundred microseconds. One NitrOS-9 dispatch at the guessed 400 cycles is
> 191 µs. With no parity or framing check, the resulting torn byte is indistinguishable
> from a good one.
>
> **The fix is a `74HC574` per port**, clocked once at end-of-frame, which makes the buffer
> genuinely one frame deep: 660 µs at the fastest PS/2 clock rate, 1.1 ms at the slowest.
> **+2 ICs, 9 → 11.** Three further corrections came with it and cost nothing: the `'193`
> is now actually *loaded* (preset strapped to 10, `~TCD` looped back to `/PL`), `IOCTRL`
> becomes a `74HC273` cleared by backplane `/RESET` — the card previously had no power-on
> reset at all, and a `DR` latch stuck set at boot hangs the machine on the shared `/IRQ` —
> and §7's software transmit is documented as running with `/IRQ` **masked**, which is the
> longest interrupt-off window in the machine and costs the serial card data.
> `docs/ps2.md` §5, §6.1, §8.4, §7.1.

**§4.4 is the second piece of prior art**, and it argues in two directions. Burrell
Smith's 1981 Apple II mouse card did the job in *two* chips — a 6522 VIA and a flip-flop —
because the mouse interrupted per notch of movement and software did the rest; the Apple
II division, not trusting interrupts, shipped "more than a dozen". That is the same
mistake this document's first revision made, at the same price. But the specific trick
**reverses** here: interrupt-per-notch scales with hand velocity and is unbounded — up to
4,000/s against PS/2's fixed 180 — so **PS/2's packetisation, which looks heavyweight next
to four quadrature wires, is exactly what makes it affordable on a machine with a
real-time replayer.** §4.5 evaluates and rejects the 6522 route it suggests, on I/O space.

## The two machine-level answers

- **`/IRQ`, as a third source.** `graphics.md` §12 already puts VBL and raster compare on
  it, open-drain; only `/FIRQ` is exclusive to audio. With an interrupt there is nothing to
  *queue*, which is what deletes the FIFO. Cost is ~1.1 % of the CPU while input is
  happening, zero otherwise — **with the mouse at 60 samples/s**, which is the largest
  standard PS/2 rate below the 70.09 Hz frame rate, and you cannot display a pointer faster
  than that. (The card asked for 40 /s until the design review pointed out that 60 is a
  standard rate and 40 was chosen from a menu that omitted it.) **The line is shared and
  the polling order is fixed:** video `VSTAT`, then this card, then serial last —
  `docs/ps2.md` §3.1.
- **`$FF50`–`$FF53`, four bytes**, leaving twelve for the disk controller.

**Transmit is software.** It happens twice at boot and on caps-lock, at ~1 ms per frame —
absurd to spend a shift register, a sequencer and a timer on. Two control bits drive the
lines low through a `7407`, two status bits read them back, and the driver walks the
protocol directly.

**And it runs with `/IRQ` masked**, which is the part the first three revisions left out.
The host has to present each bit inside a 30–50 µs window and one NitrOS-9 dispatch is
48–191 µs, so a single mouse or serial byte landing mid-transmit blows several bit slots.
Masking for the frame costs 0.8–1.3 ms of interrupt-off time — against a 521 µs byte time
at 19,200 baud, a caps-lock LED update in the middle of a download **guarantees a serial
overrun**. `docs/ps2.md` §7.1 tabulates the options; the choice is the owner's.

## Status

**Specified, nothing built.** No code and no `CMakeLists.txt`; the card is discrete logic
and the deliverable is the document.

`docs/ps2.md` §13 gives the build order. **Step 1 measures the protocol on a scope** —
§2.2's timings are recalled, not read from a document, and it now has to measure one
specific number: **the inter-byte gap inside a 3-byte mouse packet**, which is what the
no-FIFO decision actually rests on. **Step 2 breadboards the Minimal 64x4 receiver
verbatim** before generalising it, and falsifies the `'193` preload value of 10 while it is
there. **Step 8 can send the design back**: if NitrOS-9's interrupt dispatch is worse than
the guessed 400 cycles, the mouse drops to 40 /s and then the FIFO returns and the card is
13 — 11 − 2 + 4, because the FIFO subsumes the second-stage latch. **Step 9 is new** and
needs the serial card on the backplane beside it.
