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
> and the superseded claims are marked in place rather than deleted, per the convention
> at the bottom of this file.

---

## The subsystems

| | What | Status | Start here |
|---|---|---|---|
| [`cpu/`](cpu/) | HD6309E on an **STM32G431CBU6**, 40-pin drop-in. One UFQFPN48 SKU for the CoCo 3 and this machine — the MMU is on the motherboard, and the CPU also serves the boot ROM and vector page. | **Phase 1 — timing spike written, not yet measured on silicon** | [`cpu/README.md`](cpu/README.md), [`cpu/docs/plan.md`](cpu/docs/plan.md) |
| [`video/`](video/) | 640×200 × 256 colours, 80×25 text, smooth scroll, span writer. **30 ICs** — 2 `ATF1508AS`, 1 `GAL22V10`, both CPLDs fitted. | **Specified, not built** | [`video/README.md`](video/README.md), [`video/docs/graphics.md`](video/docs/graphics.md), [`video/docs/features.md`](video/docs/features.md) |
| [`audio/`](audio/) | 4-channel 8-bit PCM modelled on Paula. **29 ICs** — one `ATF1508AS` PLCC-84 holds all the logic; whether the analogue section fits the same card is open. Host reference model **builds and passes**. | **Specified; reference player validated against libopenmpt** | [`audio/README.md`](audio/README.md), [`audio/docs/audio.md`](audio/docs/audio.md) |
| [`io/`](io/) | PS/2 keyboard and mouse — **11 ICs** of logic, because no period chip decodes PS/2. RS-232 serial — 3 ICs, because one does. | **Both specified** | [`io/README.md`](io/README.md), [`io/ps2/docs/ps2.md`](io/ps2/docs/ps2.md), [`io/serial/docs/serial.md`](io/serial/docs/serial.md) |
| [`storage/`](storage/) | SD card interface — **13 ICs**, **681 KiB/s sustained**, an SPI burst started by the bus read strobe into a block buffer the host reads as memory. ⚠ The `TFM` hazard is retired, not mitigated. | **Specified** | [`storage/README.md`](storage/README.md), [`storage/docs/sdcard.md`](storage/docs/sdcard.md) |
| [`net/`](net/) | 10BASE-T with no MAC or PHY chip — **12 ICs**, two `ATF1508AS`, ported from `~/code/applenet`. ⚠ The host takes **56 % of the wire**; its sixteen-frame ring lives in the machine's new physical space. | **Specified** | [`net/README.md`](net/README.md), [`net/docs/net.md`](net/docs/net.md) |
| [`software/`](software/) | 6809/6309 code that runs *on* the machine. | Third-party monitor and FORTH, imported | [`software/README.md`](software/README.md) |
| [`hardware/`](hardware/) | Board layouts in **tscircuit** — the 72-pin backplane pinout as one table, the motherboard, and the bus interface of all ~~five~~ six cards. | **Schematic-level; nothing placed or routed** | [`hardware/README.md`](hardware/README.md) |

Machine-level material that belongs to no single card — the system map, and the
comparisons against the two chips this machine stands in the tradition of — is in
[`docs/`](docs/):

- [`docs/machine.md`](docs/machine.md) — the machine spec: bus, `$FF` map, interrupt
  ownership, clock tree, and now boot, system RAM, power and the electrical rules.
  **The open item that both card specs name as step 0.**
- [`docs/design-review.md`](docs/design-review.md) — the 2026-09-04 review of every
  subsystem, and what it changed. Start here if a document says something this one
  contradicts.
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
- **Superseded text is marked, not deleted.** Several documents carry `⚠` blocks where a
  later measurement overturned an earlier estimate; the wrong prediction is left visible
  on purpose.
