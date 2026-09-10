# Paula (MOS 8364) — the part this card reproduces

> **What this file is.** A functional overview of the Amiga's audio/I-O custom chip,
> **added to the repository on 2026-09-10** as the reference behind
> [`audio.md`](audio.md) §1's nine requirements. It is a secondary source — a summary
> with links, not a primary document — and it is kept **verbatim**, with only this
> header added, so that what it says can be compared against what was cited from it.
>
> ⚠ **Trust precedence.** Where this file and the Amiga *Hardware Reference Manual*
> disagree, the manual wins; where this file and a measurement disagree, the
> measurement wins. §16 item 36's differential oracle is the measurement, and it has
> already overturned one claim this card carried about Paula (§4.2's "`PER` = 0 or 1:
> clamp, as Paula effectively does" — Paula does not clamp anywhere).
>
> ⚠ **Scope.** Only the **audio** half of this chip is in scope for the card. The
> floppy controller, the UART and the analogue-controller timing are Paula's and are
> not reproduced — [`audio.md`](audio.md) §11.4 says why, and the machine's serial and
> storage cards ([`serial.md`](../../io/serial/docs/serial.md),
> [`sdcard.md`](../../storage/docs/sdcard.md)) own those jobs instead. They are kept
> here because the DMA/interrupt structure they share with audio is the part of Paula
> this card's §9.4 host boundary is modelled on.
>
> ⚠ **What is deliberately NOT taken from this file: the DMA architecture.** Paula does
> not arbitrate the memory bus — Agnus allocates it a slot per channel per scanline —
> and this card has no Agnus and no bus mastering at all. Its sample RAM is
> **card-local** and 200× oversupplied ([`audio.md`](audio.md) §2, §5), so the whole
> "audio samples must live in chip RAM" constraint below has no analogue here. This is
> also why the oracle's "Paula discards the first word fetched after `DMACON`" result
> could not be settled from simulation: that fetch is an *Agnus* cycle (§16 item 36).

---

**Paula (MOS 8364) is the Amiga’s audio and I/O custom chip.** It provides four independent DMA-fed 8-bit PCM voices, a raw floppy-disk data controller, a serial UART, analog controller/potentiometer timing, and part of the interrupt/DMA-control interface; it does not generate display pixels—that is Denise’s job. [archive](https://archive.org/stream/AmigaSystemProgrammersGuide/Amiga_System_Programmers_Guide_djvu.txt)

For the original OCS Amiga, Paula’s DMA clients use **21-bit chip-memory addresses**, so they can reach a 2 MiB chip-RAM address space. In ECS systems, the high fields of selected DMA pointer registers expand from 3 to 5 bits, giving a **23-bit / 8 MiB address space** in register encoding—although common ECS machines normally have no more than 2 MiB installed chip RAM. Paula does not independently arbitrate the RAM bus: **Agnus allocates DMA slots and supplies the chip-memory path.** [amigadev.elowar](http://amigadev.elowar.com/read/ADCD_2.1/Hardware_Manual_guide/node0060.html)

## Paula’s place in Amiga

The important division of labor is:

| Hardware block | Primary responsibility |
|---|---|
| **Agnus** | Chip-RAM DMA arbitration, memory timing, Copper, Blitter, video/sprite fetch scheduling |
| **Denise** | Bitplane/sprite-to-pixel conversion, palette/priority/collision, RGB video output |
| **Paula** | Audio playback, floppy raw data codec/control, serial UART, analog controller timing, selected interrupt/DMA controls |
| **CIA-A / CIA-B** | Parallel I/O, timers, keyboard handshake, and floppy-drive select/motor/step/side control signals |

This is why an Amiga audio sample must reside in **chip RAM**, not Fast RAM: Paula requests the transfer, but Agnus schedules and performs the relevant shared-memory DMA cycle. The same logic applies to Paula’s floppy DMA buffer. [amigadev.elowar](http://amigadev.elowar.com/read/ADCD_2.1/Hardware_Manual_guide/node0060.html)

## Internal workings

This is a functional diagram, not a transistor-level netlist. The actual 8364 is an NMOS custom IC with shared custom-register decode, chip-bus handshaking, and analog/mixed-signal interfaces that are more intertwined than a clean block diagram suggests.

```text
                   68000 CPU and Copper
                           │
                           │ writes / reads custom registers
                           ▼
              Custom-chip register bus at $DFF000
                           │
                           ▼
 ┌────────────────────────────────────────────────────────────────┐
 │                           PAULA (8364)                          │
 │                                                                │
 │  ┌──────────────────── DMA / interrupt interface ───────────┐  │
 │  │  DMACON / INTENA / INTREQ / ADKCON                        │  │
 │  │  DMA request signals to Agnus                             │  │
 │  │  Audio-end, serial, disk, and port-related IRQ sources    │  │
 │  └───────────────┬──────────────────────┬───────────────────┘  │
 │                  │                      │                      │
 │                  │ chip-RAM DMA          │                      │
 │                  ▼                      ▼                      │
 │  ┌───────────────────────────┐  ┌───────────────────────────┐  │
 │  │ Four audio channels       │  │ Floppy raw-data controller │  │
 │  │ AUD0...AUD3               │  │                           │  │
 │  │                           │  │ DSKPTH/L, DSKLEN, DSKSYNC │  │
 │  │ start-location register   │  │ MFM/GCR timing/control    │  │
 │  │ internal current pointer  │  │ serial bit/word shifters  │  │
 │  │ word-length counter       │  │ disk DMA buffer            │  │
 │  │ 16-bit DMA buffer         │  │                           │  │
 │  │ byte selector             │  │ Read data / write data     │  │
 │  │ period down-counter       │  └──────────────┬────────────┘  │
 │  │ volume scaler             │                 │               │
 │  │ 8-bit signed DAC path     │              Disk drive          │
 │  └──────┬──────┬──────┬──────┘             RD / WD interface   │
 │         │      │      │                                          │
 │         │      │      │                                          │
 │         ▼      ▼      ▼                                          │
 │  CH0 + CH3 ───────► Left analog mix ───► AUDL                   │
 │  CH1 + CH2 ───────► Right analog mix ───► AUDR                  │
 │                                                                │
 │  ┌──────────────────────┐   ┌────────────────────────────────┐ │
 │  │ Serial UART          │   │ Analog controller interface    │ │
 │  │ SERDAT / SERDATR     │   │ POTGO / POTGOR                 │ │
 │  │ SERPER               │   │ POT0DAT / POT1DAT              │ │
 │  │ TXD / RXD            │   │ RC charge timing + counters    │ │
 │  └──────────┬───────────┘   └──────────────┬─────────────────┘ │
 └─────────────┼────────────────────────────────┼──────────────────┘
               ▼                                ▼
          RS-232-level                     Joystick/mouse/paddle
          interface logic                  / light-pen related pins

     Audio and disk DMA requests/acknowledgments are mediated by Agnus.
```

At a high level, Paula is not just “the sound chip.” It is the Amiga’s lower-speed peripheral and mixed-I/O custom chip, while Agnus carries the DMA/raster scheduling burden. The System Programmer’s Guide explicitly groups Paula’s main responsibilities as diskette I/O, serial I/O, sound output, and analog-input reading. [archive](https://archive.org/stream/AmigaSystemProgrammersGuide/Amiga_System_Programmers_Guide_djvu.txt)

## Audio architecture

Paula supports **four simultaneous, independent 8-bit signed PCM channels**, numbered 0–3. Each has its own sample start address, length, playback period, volume, DMA data buffer, and interrupt source. The fixed analog panning is:

| Channel | Output mix |
|---|---|
| Audio 0 | Left |
| Audio 1 | Right |
| Audio 2 | Right |
| Audio 3 | Left |

Thus, the standard Amiga configuration is four-voice PCM with stereo mixing—not four completely programmable pan positions. [archive](https://archive.org/stream/AmigaSystemProgrammersGuide/Amiga_System_Programmers_Guide_djvu.txt)

### One channel’s sample path

```text
AUDxLCH/LCL               AUDxLEN
   start location          length in 16-bit words
          │                       │
          └────► internal DMA address + word counter
                              │
                              ▼
                      DMA request to Agnus
                              │
                              ▼
                     16-bit AUDxDAT buffer
                              │
                 high byte, then low byte
                              ▼
                      8-bit signed PCM sample
                              │
                AUDxVOL: 0–64 linear amplitude
                              │
                              ▼
                      DAC / channel mixer
                              │
                      fixed left/right mix
```

Each `AUDxDAT` word stores **two sequential 8-bit two’s-complement samples**. As the period counter expires, Paula emits the next byte. When its word buffer needs refilling, it requests a memory transfer; when the programmed word count is exhausted and buffered data is consumed, it sets the corresponding audio interrupt request. Software may also write `AUDxDAT` directly with audio DMA disabled, allowing CPU-driven sample output. [ikod](https://www.ikod.se/wp-content/uploads/2020/08/Amiga_Hardware_Reference_Manual_3rd_Edition.pdf)

The nominal sample-rate relationship is approximately:

\[
f_s = \frac{f_{\text{color clock}}}{\texttt{AUDxPER}}
\]

where the color clock is about 3.546897 MHz on PAL and 3.579545 MHz on NTSC systems. The documented normal minimum usable period is 124 color clocks, corresponding to a maximum nominal sample rate of about **28.9 kHz**. Smaller periods may produce nonportable or undocumented behavior and should not be relied on. [lysator.liu](http://www.lysator.liu.se/amiga/hard/guide/AmigaHardware.guide)

### Audio registers

Every channel has the same six-register pattern, spaced by `$10` bytes:

| Register | Channel 0 address | Meaning |
|---|---:|---|
| `AUDxLCH` | `$DFF0A0` | High bits of the sample’s chip-RAM start location |
| `AUDxLCL` | `$DFF0A2` | Low 15 bits of sample start location; must be word-aligned |
| `AUDxLEN` | `$DFF0A4` | Sample length in 16-bit words |
| `AUDxPER` | `$DFF0A6` | Playback period / sample interval |
| `AUDxVOL` | `$DFF0A8` | Volume, 0–64 |
| `AUDxDAT` | `$DFF0AA` | 16-bit DMA buffer or direct CPU-fed sample-data register |

The address bases are `$0A0`, `$0B0`, `$0C0`, and `$0D0` for channels 0, 1, 2, and 3 respectively. The pointer register pair, though stored in the common custom register map, is marked as an Agnus-addressed DMA location pair; Paula maintains its own internal running playback address during transfer. [amigadev.elowar](http://amigadev.elowar.com/read/ADCD_2.1/Hardware_Manual_guide/node0060.html)

### Channel modulation mode

Paula can chain audio channels for a distinctive tracker-era effect:

- Channel 0 can modulate channel 1’s **period** and/or **volume**.
- Channel 1 can modulate channel 2.
- Channel 2 can modulate channel 3.
- Channel 3 has no downstream audio channel to modulate.

The control bits are in `ADKCON`:

| `ADKCON` bits | Effect |
|---|---|
| `USE0P1`, `USE1P2`, `USE2P3` | Route a prior channel’s sample values to the next channel’s period control |
| `USE0V1`, `USE1V2`, `USE2V3` | Route a prior channel’s sample values to the next channel’s volume control |

When a channel is used as a modulator, it is no longer available as an ordinary independently audible voice in the usual sense. Period and volume modulation can also be enabled together, in which case their data usage alternates. [lysator.liu](http://www.lysator.liu.se/amiga/hard/guide/AmigaHardware.guide)

## Paula-owned register groups

All custom chip registers appear in the CPU’s `$DFF000` register window. “Paula-owned” below means that Paula implements the functional block; some DMA pointer pairs are physically decoded/used jointly with Agnus because Agnus owns the shared-memory timing. [amigadev.elowar](http://amigadev.elowar.com/read/ADCD_2.1/Hardware_Manual_guide/node0060.html)

### Core control and interrupts

| Address | Register | Purpose |
|---:|---|---|
| `$DFF002` | `DMACONR` | Read DMA-control/status state |
| `$DFF096` | `DMACON` | Enable/disable master DMA and individual audio, disk, and other DMA channels |
| `$DFF010` | `ADKCONR` | Read audio/disk/UART auxiliary control state |
| `$DFF09E` | `ADKCON` | Audio modulation and disk/UART auxiliary control |
| `$DFF01C` | `INTENAR` | Read interrupt-enable state |
| `$DFF01E` | `INTREQR` | Read interrupt-request state |
| `$DFF09A` | `INTENA` | Enable/disable individual interrupt sources |
| `$DFF09C` | `INTREQ` | Set/clear interrupt-request bits |

`DMACON`, `INTENA`, and `INTREQ` use the familiar Amiga set/clear convention: bit 15 chooses whether the bits set to 1 in the written value are added or removed, so software can change selected enables/requests without a read-modify-write race. The audio channels’ DMA and interrupt enables are controlled through these common registers. [amigadev.elowar](http://amigadev.elowar.com/read/ADCD_2.1/Hardware_Manual_guide/node0060.html)

## Memory addressing

The accurate answer has two layers:

1. **Paula’s audio and disk clients use chip-memory DMA buffers**, and the DMA process is scheduled through Agnus.
2. **The address width depends on chipset generation**, not just Paula’s existence.

| Platform | Relevant pointer form | Reachable DMA address space | Practical note |
|---|---|---:|---|
| OCS Amiga | 3 high pointer bits + 15 low bits + word alignment | 21 bits = 2 MiB | Typical machines had 512 KiB or 1 MiB chip RAM |
| ECS Amiga | Expanded high fields: 5 bits + 15 low bits + word alignment | 23 bits = 8 MiB | Standard ECS machines typically topped out at 2 MiB chip RAM |
| AGA Amiga | Different later chipset implementation/integration | 24-bit chip-memory environment | Paula-compatible audio remains four 8-bit channels |

For OCS audio, `AUDxLCH` plus `AUDxLCL` form an 18-bit **word address**, with the least-significant byte address implicitly zero, giving 21 byte-address bits / 2 MiB. The disk pointer works under the same OCS chip-memory limit. The official register summary shows the OCS 3-bit high pointer field and notes the ECS expansion to 5 high bits. [amigadev.elowar](http://amigadev.elowar.com/read/ADCD_2.1/Hardware_Manual_guide/node0060.html)

## Practical implications

A classic four-channel MOD replay typically does the following:

1. Places each instrument sample in chip RAM.
2. Sets `AUDxLC` to its start address and `AUDxLEN` to its word length.
3. Writes `AUDxPER` for pitch and `AUDxVOL` for amplitude.
4. Enables the chosen audio DMA bits and the global DMA master bit in `DMACON`.
5. Uses each channel’s end interrupt to update its next sample/loop state, or relies on the automatic location/length reload behavior for repeating buffers.

The famous “four-channel Amiga sound” is therefore not a wavetable synth, FM block, or PSG. It is four autonomous sample players—small DMA engines feeding fixed 8-bit signed DAC paths, with tight timing and enough register-level control to make tracker music practical on a 7 MHz 68000. [ikod](https://www.ikod.se/wp-content/uploads/2020/08/Amiga_Hardware_Reference_Manual_3rd_Edition.pdf)
