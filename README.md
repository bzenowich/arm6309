# arm6309

A **6309 machine**, built one subsystem at a time.

It started as one question — can an STM32G431 pretend to be an HD6309E convincingly
enough to drop into a Tandy CoCo 3? — and the answer looked good enough that the project
grew a machine around the CPU: a 256-colour video card, a Paula-class sound card, and
(next) PS/2 and serial. Everything is period-plausible discrete logic except the CPU
itself, which is the one part 1989 could not have built this way.

**House rules, inherited from the CPU work and applied to every card since:**
period-appropriate silicon — **and programmable logic is in.** GALs, and CPLDs where a
GAL will not carry the design. A documented register map before a board, an honest IC
count, and a measurement in place of an estimate wherever one can be taken.

> **The rule used to read "no CPLDs, no FPGAs", and it was retired on 2026-09-08.** It
> was never a period rule — `video/docs/graphics.md` §10.1.2: Altera's first EPLD is
> 1984 and the first CPLD 1988, both older than parts this machine already uses. It was
> a style rule that bought one function per package and everything visible on a scope,
> and **three of six cards had already spent it**: video to compete with a GIME on even
> terms, audio because its interrupt block does not fit a `GAL22V10` either way, and net
> because a 74xx 10BASE-T MAC is 41 ICs across two slots and the machine has one left.
> A fourth — storage — had an `ATF1508AS` costed, worth **five packages**, and refused
> it on the rule alone (`storage/docs/sdcard.md` §8.1).
>
> **A rule three cards deep in exceptions, blocking a fifth-package saving on the
> fourth, was not describing the machine any more.** The
> test that actually decided each case is the one `io/README.md` derived independently:
> **does a part exist, is it available, and does it fit the I/O budget** — in that
> order, which is the ordering `net/docs/net.md` §13.6 paid to learn.
>
> ⚠ **One thing this does not decide: FPGAs.** No card has proposed one and none of the
> arguments above reaches them — a CPLD is a fitted, fuse-level-verifiable part with a
> vendor compiler this repository checks its own work against, and an FPGA is a
> different proposition. **Unproposed and undecided**, rather than banned.

> ⚠ **Every subsystem was reviewed on 2026-09-04, and the IC counts were not honest.**
> [`docs/design-review.md`](docs/design-review.md) re-derived each card's arithmetic
> against the datasheets and found 6 critical and 35 major defects — including that the
> machine **had no way to execute its first instruction**. The counts below are the
> corrected ones; they rose by about 45 % in aggregate. Every finding has been applied,
> and the claims each one overturned are preserved in the per-component `history.md`
> files, per the convention at the bottom of this file.

> ⛔ **And it was reviewed again on 2026-09-09, this time by simulation, and the
> features added in the intervening five days largely did not work.**
> [`docs/design-review2.md`](docs/design-review2.md) generates Verilog from the same
> term lists the CPLD fitter compiles and runs the video card, the audio card and the
> motherboard over whole frames, whole spans and the boot sequence: **122 claims
> verified, 16 failures across 10 defects**, plus eleven blocks that a port census
> found to be described in prose and present in no design file.
>
> ⭐ **Eleven of the twelve were repaired the same day**, and the twelfth is the audio
> sequencer, which is design work rather than a fix. The simulation is **140 claims and
> no failures**; `docs/design-review2.md` §10 is the disposition.
>
> **What the repairs cost:** the MMU's two map bytes get **two windows** instead of
> sharing an address bit with the task index, out of 32 bytes that decoded nowhere —
> U9 gives back a pin and U3's decode is the same size. The video card ends the day at
> **36 ICs on a 24 cm board**, and eight of those packages arrived on 2026-09-09: seven
> of them are features that were **specified and had no hardware behind them** —
> byte-granular horizontal scroll, the palette *write path*, and the display list's
> register port — and the eighth is a third `ATF1508AS`, which **reduced** the count by
> absorbing all three of the card's `GAL22V10`s (`graphics.md` §10.1.7, §14.1).
>
> ⛔ **AND THEN IT RAN ITS OWN SOFTWARE, on 2026-09-10, and three more things broke.**
> Everything above was checked by testbenches that drive the bus by hand. On
> 2026-09-10 a cycle-accurate **6809E core** went in the socket, the motherboard and
> the video card went in with it, and the machine executed
> [`software/boot/boot.asm`](software/boot/boot.asm) out of its own ROM
> (`hardware/gal/verilog/machine_tb.sv`). **It did not reach its second span.**
>
> Three defects, all of them seams between parts that are individually correct, and
> **all three invisible to every check that existed for the same reason: a testbench
> that drives `E` from a free-running counter has a CPU that cannot be waited.**
> `/WAIT` is the one backplane signal that changes what the CPU *does* rather than
> what it reads.
>
> | | |
> |---|---|
> | ⛔ **the machine deadlocked on its first span** | the arbiter refused the span writer the framebuffer chip the CPU's own stalled write was selecting — and that write was stalled *by* the span. One literal (`R/W`) on the CPU's grant: a posted VRAM write needs no access of its own |
> | ⛔ **the span re-armed itself for ever** | `SPANBUSY` was set by a **level** over `E`-high, and `/WAIT` makes `E`-high unbounded. One registered macrocell makes it an `E`-**fall** edge, which is what §3.1.1's `'574`s always did |
> | ⛔ **polling `VSTAT` put a three-pixel hole in every span** | §7.4's colour path *is* the register file's address, and any CPU access to the card took it from the running span. The CPU's claim is qualified on `!SPANBUSY` now, and it **gives product terms back** |
>
> ⭐ **All three are repaired, `vctrl` and `vsup` re-fit, and the machine draws a
> 640 × 200 picture whose every pixel is the index the software wrote** — 226
> Verilator claims, 543 model claims and 22 machine claims, **none failing**.
> `graphics.md` §19 items 36–38, and `video/docs/history.md` has the derivations.
>
> ⭐ **A fourth followed from the picture itself and is repaired too** (§19 item 35):
> it sat **five dots right of the active window**, so the last five columns of every
> row were never displayed and the first five repeated byte 0. §6.1's dot path is five
> dots deep and `BLANK` came off the H counter with no matching delay — and the H
> counter counts four-dot **slots**, so no change to its constants could ever buy
> five. `vctrl` exports the delayed copy and `BLANK` becomes buried: **five registered
> macrocells, zero pins**. `VSTAT`'s `HBLANK`/`VBLANK` are deliberately *not* delayed,
> because what those have to agree with is the sync.
>
> ⛔ **The audio card played a module the same day, and the volume converter was
> being fed the SAMPLE byte.** After the first volume change of a module, on every
> channel, while the state file held the right value throughout — so `audio_tb`'s
> *"VOL is one byte and goes straight through"* was true and useless: it is a claim
> about the state file, and **nothing had ever compared the converter's own pins
> against the file's contents.** ⭐ **Repaired by a DELETION**: the walk's per-frame
> refresh of the port registers had been redundant since `audio.md` §16 item 39(b)
> made the `PEND` write do the loading, and it was landing in the middle of a volume
> pass. U2's foldbacks go **72 → 65** and it still fits — two repairs that *added*
> logic were tried first and neither did (§16 item 41).
>
> ⛔ **And it still plays 12 dB too quietly.**
> `modplay_tb.sv` uploads a module's samples through the card's host port, delivers
> the register stream on the card's **own** tempo-timer interrupt, and records what the
> four `AD7528` pairs are given; it agrees with libopenmpt to **−0.01 cents** and
> **0.9977** spectral correlation, against **0.9989** for the C reference model as a
> control. `audio.md` §6.1's ×4 for Paula-mode `VOL` **is not built** and `ACTRL` b3
> reaches nothing, so the card implements raw mode only and the mode every MOD
> replayer uses is the broken one. ⛔ **It is 12.04 dB below every output level
> `audio.md` §7.1 specifies**: 0.98 mW into 32 Ω headphones where §7.1 calls 1–5 mW
> comfortable and claims 15.6 mW of headroom, **0.104 mW into the 300 Ω it says it
> drives**, a "line" output 5 dB *below* consumer line level, and a muted channel
> bleeding at −58 dB instead of −70. Where the ×4 belongs — two `74HC157`, one
> resistor and no raw mode, or the replayer — is a specification decision
> (`audio.md` §16 item 40, **open**).

> ⭐ **The display list has a descriptor format since 2026-09-09** — `MOVE`, `WAIT`,
> `$FF` to end (`graphics.md` §10.3.2) — and it reaches **`HSCROLL`, `HSCROLLH` and the
> whole palette port**, so per-scanline gradients and split palettes are hardware and
> not a raster interrupt. ⛔ **`CTRL` is the one it cannot reach, and the reason is
> which data bus `vctrl` taps rather than a pin count** (§10.3.4). ⭐ **Byte-granular
> horizontal scroll closed the same day** (§19 item 28, §8.2): two ranks of fetch latch
> in series with an output-enable select, +4 packages against the +12 the item
> estimated, and `vaddr_tb` emits a whole 640-pixel line at every `HSCROLL` from 0 to 7
> and gets **0 wrong of 640** at all eight.

---

## The subsystems

| | What | Status | Start here |
|---|---|---|---|
| [`cpu/`](cpu/) | HD6309E on an **STM32G431CBU6**, 40-pin drop-in. One UFQFPN48 SKU for the CoCo 3 and this machine, running **byte-identical firmware on both** — the MMU is on the motherboard and so, since 2026-09-08, is the boot ROM. | **Phase 1 — timing spike written, not yet measured on silicon** | [`cpu/README.md`](cpu/README.md), [`cpu/docs/plan.md`](cpu/docs/plan.md) |
| [`video/`](video/) | 640×200 × 256 colours, 80×25 text, byte-granular scroll, span writer, a display list that writes the palette per scanline. **36 ICs** on a 24 cm board — 3 `ATF1508AS` and no GALs, all three fitted with JTAG. | **Specified; simulated 2026-09-09 and repaired — 36 ICs, two open items** | [`video/README.md`](video/README.md), [`video/docs/graphics.md`](video/docs/graphics.md), [`video/docs/features.md`](video/docs/features.md) |
| [`audio/`](audio/) | 4-channel 8-bit PCM modelled on Paula, **with programmable panning**, 512 KB of samples in one package and a headphone-driven jack. ⭐ **35 ICs on an 18 cm card** — **two** `ATF1508AS`, both fitted. It reached 45 when the sequencer was built and came back the same day: programmable panning given up for classic MOD's fixed LRRL, and the counter, comparator and read-back latch absorbed into U1. Whether the analogue section fits the same card is open. Host reference model **builds and passes**. | ⭐ **Both CPLDs fitted, and the sequencer exactly fills its part; the card is simulated end to end — a sample byte reaches an `AD7528` and a buffer reloads from its shadow.** The analogue half is still unmeasured | [`audio/README.md`](audio/README.md), [`audio/docs/audio.md`](audio/docs/audio.md) |
| [`io/`](io/) | PS/2 keyboard and mouse — **11 ICs** of logic, because no period chip decodes PS/2. RS-232 serial — 3 ICs, because one does, and since 2026-09-09 it is a **`TL16C550C` at 115,200 baud with 16-byte FIFOs**. One 14-IC card. | **Both specified** | [`io/README.md`](io/README.md), [`io/ps2/docs/ps2.md`](io/ps2/docs/ps2.md), [`io/serial/docs/serial.md`](io/serial/docs/serial.md) |
| [`storage/`](storage/) | SD card interface — **14 ICs**, **681 KiB/s sustained**, an SPI burst started by the bus read strobe into a block buffer the host reads as memory. ⚠ The `TFM` hazard is retired, not mitigated. | **Specified** | [`storage/README.md`](storage/README.md), [`storage/docs/sdcard.md`](storage/docs/sdcard.md) |
| [`net/`](net/) | 10BASE-T with no MAC or PHY chip — **12 ICs**, two `ATF1508AS`, ported from `~/code/applenet`. ⚠ The host takes **56 % of the wire**; its sixteen-frame ring lives in the machine's new physical space. | **Specified** | [`net/README.md`](net/README.md), [`net/docs/net.md`](net/docs/net.md) |
| [`software/`](software/) | 6809/6309 code that runs *on* the machine. | Third-party monitor and FORTH, imported | [`software/README.md`](software/README.md) |
| [`hardware/`](hardware/) | Board layouts in **tscircuit** — the 72-pin backplane pinout as one table, the motherboard, the bus interface of all six cards, and the video card's analogue back end. Plus [`hardware/ram.md`](hardware/ram.md), the memory system: a 32 MB map, four SIMM sockets and a **1 MB boot ROM**. | **Schematic-level; boot, the map and all four SIMM windows simulate** | [`hardware/README.md`](hardware/README.md) |

Machine-level material that belongs to no single card — the system map, and the
comparisons against the two chips this machine stands in the tradition of — is in
[`docs/`](docs/):

- [`docs/machine.md`](docs/machine.md) — the machine spec: bus, `$FF` map, interrupt
  ownership, clock tree, and now boot, system RAM, power and the electrical rules.
  **The open item that both card specs name as step 0.**
- [`docs/drivewire.md`](docs/drivewire.md) — the host link: virtual disks over serial for
  zero ICs, what it costs on each serial tier, and the machine's only source of a
  wall-clock time.
- [`docs/design-review.md`](docs/design-review.md) — the 2026-09-04 review of every
  subsystem, and what it changed. Start here if a document says something this one
  contradicts.
- [`docs/design-review2.md`](docs/design-review2.md) — ⛔ **the 2026-09-09 review, by
  simulation.** What the term-list checks could not see, why they could not see it, and
  the tooling (`npm run check:video`) it leaves behind. Both reviews are frozen dated
  records.
- [`docs/coco3_c64.md`](docs/coco3_c64.md) — GIME vs VIC-II, from a CPU-replacement's
  point of view.
- [`docs/video-comparison.md`](docs/video-comparison.md) — the video card against both
  of them.

[`reference/`](reference/) holds datasheets, service manuals and ROMs. The large scans
are deliberately **not** in git — see [`reference/README.md`](reference/README.md) — and
neither, since 2026-09-04, is anything this project has no right to redistribute
([`reference/68k/README.md`](reference/68k/README.md)).

**This repository has no licence of its own.** That is an omission, not a choice; see
`docs/design-review.md` §Sys-M6.

---

## Building

Two configurations, building disjoint sets of targets. Both run from this directory.

### Host — no cross toolchain needed

Syntax-checks the firmware sources, builds the audio reference player, runs the tests.

```sh
cmake -B build-host -G Ninja
cmake --build build-host
ctest --test-dir build-host --output-on-failure
```

Produces `build-host/refplayer` and the two test binaries.

### Hardware — the design files, the fuse maps and the simulation

Needs `verilator`; `bun` comes from `hardware/`'s own `devDependencies`.

```sh
cd hardware
npm ci
npm run check         # every GAL design against its model, and against Atmel's CUPL
npm run check:sim     # the motherboard's two hand-written Verilog models
npm run check:video   # ⛔ the cards and the motherboard, generated and simulated
```

`check:video` reports **144 ok and no failures** as of 2026-09-09 — 140 after that
day's repairs, plus four for `graphics.md` §10.3.2's descriptor format. It reported 122
and 16 before the repairs, and [`docs/design-review2.md`](docs/design-review2.md) §10
says what each one turned into.

### Firmware — `cpu/` only

Needs `arm-none-eabi-gcc` (13.2.1 verified).

```sh
# Debian/Ubuntu
sudo apt install gcc-arm-none-eabi

cmake -B build-arm -DCMAKE_TOOLCHAIN_FILE=cmake/arm-none-eabi.cmake -G Ninja
cmake --build build-arm
```

Produces `build-arm/spike.elf`, `.bin`, `.hex` and a link map.

Each subsystem owns its own `CMakeLists.txt`; the top-level file only decides which
subdirectories a given configuration visits. `video/` and `io/` are specification-only
and build nothing.

---

## Conventions

- **Paths in source comments and in cross-subsystem prose are repository-root-relative**
  — `cpu/src/gpio.c`, not `../src/gpio.c`. Inside a subsystem's own README, paths are
  relative to that subsystem and it says so at the top. Markdown *links* are always
  relative, because they have to resolve.
- **Every card's specification is one document**, and it owns its own open-items list and
  build order. Cross-document claims cite section numbers.
- **Superseded text is archived, not deleted — and not left in place.** Until
  2026-09-08 the rule was "marked, not deleted", and the specifications carried every
  overturned estimate inline; at ~500 markers they stopped being readable. Each
  component now splits in two: the **specification describes only the present
  design**, and a `history.md` beside it archives what was superseded, with dates and
  the reason each number moved (`video/docs/history.md`, `audio/docs/history.md`,
  `cpu/docs/history.md`, `net/docs/history.md`, `storage/docs/history.md`,
  `io/ps2/docs/history.md`, `io/serial/docs/history.md`, `hardware/history.md`,
  `docs/history.md`). The wrong predictions are still visible on purpose — one
  directory over. A `⚠` in a spec now marks only a **live** hazard or unverified
  assumption, never a revision. Section numbers are never reused: a section whose
  content moved to history keeps its number as a one-line stub, so cross-document
  citations stay valid. `docs/design-review.md` is kept verbatim as a dated record.
