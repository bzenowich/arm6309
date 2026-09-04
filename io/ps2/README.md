# `io/ps2/` — PS/2 keyboard and mouse

Two PS/2 ports, **9 ICs**, no MCU, no FIFO, no transmit engine.

Paths below are relative to this directory.

| | |
|---|---|
| [`docs/ps2.md`](docs/ps2.md) | the card — protocol, the borrowed receiver, register map, IC budget |

## Where the design comes from

**§4.1 is the important section.** Slu4's Minimal 64x4 receives PS/2 in **three
packages** — one `74HC595`, one `74HC193`, one `74HCT132` — and reading its schematic cut
this card from 16 ICs to 9. Four ideas transfer intact:

- The `'595`'s **separate storage register** solves the 11-bit-frame-into-8-bit-register
  problem for free, and gives one byte of buffering at zero cost.
- **`Q0` of the bit counter drives `RCLK`**, so no decode of "the ninth clock" is needed.
- **The bit order is reversed in the wiring** — PS/2 is LSB-first, so `QA`→`BUS7`.
- **Schmitt inputs are mandatory, and `HCT` not `HC`**: PS/2 edges can exceed the 400 ns
  rise-time limit of a plain HC input, and a 3.3 V device does not clear `HC`'s `V_IH`.

What it does *not* do accounts for the difference: one port, receive-only (so no mouse —
a mouse is silent until it is told `F4`), and bus-attached by **microcode strobes and a
CPU branch flag** rather than an address decoder. Three of this card's six extra packages
are the tax for the 6309 being a fixed CPU.

**§4.4 is the second piece of prior art**, and it argues in two directions. Burrell
Smith's 1981 Apple II mouse card did the job in *two* chips — a 6522 VIA and a flip-flop —
because the mouse interrupted per notch of movement and software did the rest; the Apple
II division, not trusting interrupts, shipped "more than a dozen". That is the same
mistake this document's first revision made, at the same price. But the specific trick
**reverses** here: interrupt-per-notch scales with hand velocity and is unbounded — up to
4,000/s against PS/2's fixed 120 — so **PS/2's packetisation, which looks heavyweight next
to four quadrature wires, is exactly what makes it affordable on a machine with a
real-time replayer.** §4.5 evaluates and rejects the 6522 route it suggests, on I/O space.

## The two machine-level answers

- **`/IRQ`, as a third source.** `graphics.md` §12 already puts VBL and raster compare on
  it, open-drain; only `/FIRQ` is exclusive to audio. With an interrupt there is nothing
  to buffer, which is what deletes the FIFO. Cost is ~0.9 % of the CPU while input is
  happening, zero otherwise — **with the mouse pinned at 40 samples/s**, because you
  cannot display a pointer faster than the 70 Hz frame rate anyway.
- **`$FF50`–`$FF53`, four bytes**, leaving twelve for the disk controller.

**Transmit is software.** It happens twice at boot and on caps-lock, at ~1 ms per frame —
absurd to spend a shift register, a sequencer and a timer on. Two control bits drive the
lines low through a `7407`, two status bits read them back, and the driver walks the
protocol directly.

## Status

**Specified, nothing built.** No code and no `CMakeLists.txt`; the card is discrete logic
and the deliverable is the document.

`docs/ps2.md` §13 gives the build order. **Step 1 measures the protocol on a scope** —
§2.2's timings are recalled, not read from a document. **Step 2 breadboards the Minimal
64x4 receiver verbatim** before generalising it. **Step 8 can send the design back**: if
NitrOS-9's interrupt dispatch is worse than the guessed 400 cycles, the FIFO returns and
the card is 13.
