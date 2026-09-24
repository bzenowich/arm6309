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
> was never a period rule — `hardware/archive/video/docs/graphics.md` §10.1.2: Altera's first EPLD is
> 1984 and the first CPLD 1988, both older than parts this machine already uses. It was
> a style rule that bought one function per package and everything visible on a scope,
> and **three of six cards had already spent it**: video to compete with a GIME on even
> terms, audio because its interrupt block does not fit a `GAL22V10` either way, and net
> because a 74xx 10BASE-T MAC is 41 ICs across two slots and the machine has one left.
> A fourth — storage — had an `ATF1508AS` costed, worth **five packages**, and refused
> it on the rule alone (`hardware/storage/docs/sdcard.md` §8.1). ⭐ **That question closed itself
> on 2026-09-20**: the card shrank to 8 ICs and two GAL22V10s, so the CPLD would now buy
> nothing and would give up the fuse-level verification `hardware/tools/gal/jedec/` provides.
>
> **A rule three cards deep in exceptions, blocking a fifth-package saving on the
> fourth, was not describing the machine any more.** The
> test that actually decided each case is the one `hardware/io/README.md` derived independently:
> **does a part exist, is it available, and does it fit the I/O budget** — in that
> order, which is the ordering `hardware/net/docs/net.md` §13.6 paid to learn.
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
> (`hardware/tools/sim/machine_tb.sv`). **It did not reach its second span.**
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
> `graphics.md` §19 items 36–38, and `hardware/archive/video/docs/history.md` has the derivations.
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
> ⛔ **AND THE CENSUS THAT FOUND THOSE IS A CHECK NOW — `make -C hardware reach`.**
> `design-review2.md` closed the direction *"a fitted part reads what nothing
> produces"*; this is the other one, and it was open in twenty-five places. A
> signal that is **produced and read by nothing** is, for a register bit, a
> feature the host can write and the card cannot perform — and nothing else in
> this repository could see it, because every other check asks whether a part
> computes its own equations correctly and a bit nobody reads has no equation to
> get wrong.
>
> | | |
> |---|---|
> | ⭐ **0 promised and not built, as of 2026-09-11** | Video's §11 readable VRAM is built, through the VRAM window at `WPTR`, and `+$15` `VDATA` is reserved. Audio's `DAT` and `ATT` were retired (real Paula features that no ProTracker replayer writes), and its volume ×4 closed in the replayer. ⚠ The census still cannot see a feature with no register bit, which is how the ×4 hid |
> | ⭐ **6 invented features retired** | audio `ACTRL` b2 (NTSC — §4.1 takes **one** crystal), b3 (raw 256-level volume — `paula.md`'s `AUDxVOL` is 0–64 and the word "255" appears nowhere in it), b4 (8 channels — Paula has four), b5 and `PAN` (panning); video `CHAR` and `FONTBASE` (§6.4.3's Variant B). **Every one failed the same test, and §11's own title is the test:** *what does this card do that Paula cannot* |
> | ⭐ **8 macrocells of dead logic deleted** | six on U1, two on U2. **None was a broken feature** — the features work, which is how they were known to be redundant — and **two checks were their only consumers**, which is why they survived. A check is not a consumer |
> | ⚠ **12 whose consumer is a board part the model lacks** | §5.2.1's eight grants among them. `check:netlist` is what should close that and `graphics.md` §19 item 34 is why it cannot yet |
>
> ⚠ **The list is checked in both directions**: an entry that stops being unread
> fails too, so a feature that gets built has to be taken off it — which is what
> forced the deletions above to be recorded rather than merely made.
>
> **What the retirements bought, measured:** U1 **62 → 61 I/O**, and that pin is
> the one earmarked for §6.1's ×4 select (not needed since 2026-09-11); `vaddr` **63 → 59 I/O**, on the video part §19
> item 33 is blocked on. ⚠ **U2 gained nothing measurable** — two cells were deleted
> and the fitter still reported 128 of 128, because it packs the array.

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
> bleeding at −58 dB instead of −70. ⭐ **Closed 2026-09-11** (`audio.md` §16 item
> 40): the card already passed all eight bits of `VOL` to the converter, so the
> replayer writes `min(4 × volume, 255)` and no hardware changes. `modplay_tb` now
> asserts a full-volume module reaches converter code 255.

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

## Layout

Since 2026-09-23 the tree is **one directory per component**, hardware and software
alike, and every component is laid out the same way:

```
hardware/<card>/            mainboard, cpu, video3, audio, io (ps2, serial), storage, net
    README.md               what it is and where to start
    docs/                   its specification, and history.md beside it
    board/                  the tscircuit drawing (<card>.circuit.tsx)
    logic/                  its GAL/CPLD designs: *.jedec.ts / *.cpld.ts term lists, the
                            generated .pld, the fitter's cpld/*.fit and CUPL's cupl/*.cupl.jed
    sim/                    its Verilog: the generated parts, the hand-written board model,
                            and its testbench
    bench/, tools/          host-side exercisers and models, where it has them
    reference/              datasheets and other material it is checked against
hardware/tools/             what every card shares: lib/ (the slot, the checks), place/,
                            gal/ (the JEDEC assembler, CUPL cross-check, fitter wrappers),
                            sim/ (the Verilog generator, the runners, the whole-machine bench)
hardware/archive/           retired hardware - frozen, and still citable

software/<program>/         boot, nitros9, toolbox, desk, pcs, stardew, monster,
                            mvania, tilescroll, paint
    README.md               what it is, and where its 6809 source is
    bench/                  its generator (mk*.py), its model and checker, its run-*.sh
    docs/, reference/       as above
software/emu/               the host emulator every software bench runs on
software/tools/             shared host tools (the frame decoder, the assemblers' fetchers)
software/archive/           retired software - the video/ card's demo show, the tile-mode
                            overworld and zelda, three pinball attempts before pcs

docs/                       the machine as a whole: machine.md, the design reviews, history
reference/                  reference material more than one component uses
```

⚠ **The applications' 6809 source is not in this repository.** It is part of the
NitrOS-9 port, in `../nitros9` on its `arm6309` branch (`level2/arm6309/cmds/`,
`modules/`), because the NitrOS-9 recipe builds it there. Each `software/<program>/`
README names its files; this repository holds everything around them — the
generators that write their data tables, the models they are checked against, the
benches, the art and the docs.

## The subsystems

| | What | Status | Start here |
|---|---|---|---|
| [`hardware/cpu/`](hardware/cpu/) | HD6309E on an **STM32G431CBU6**, 40-pin drop-in. One UFQFPN48 SKU for the CoCo 3 and this machine, running **byte-identical firmware on both** — the MMU is on the motherboard and so, since 2026-09-08, is the boot ROM. | **Phase 1 — timing spike written, not yet measured on silicon** | [`hardware/cpu/README.md`](hardware/cpu/README.md), [`hardware/cpu/docs/plan.md`](hardware/cpu/docs/plan.md) |
| [`hardware/video3/`](hardware/video3/) | ⭐ **The machine's video card since 2026-09-20.** 80×25 / 80×60 character mode with **per-cell colour**, 640×200/240/400/480 chunky 8bpp bitmap with a span writer and **full copyrect**, 8×8 tile mode and one 16×16 sprite. **45 ICs** on a 24 cm board — 4 `ATF1508AS` and a `GAL22V10`, all five fitted. ⛔ **No display list**, so nothing per-scanline. | ⭐ **Fitted, and simulated end to end**: `v3card_tb` runs whole frames pixel for pixel in every mode and `v3machine_tb` runs a 6809E against the card out of the boot ROM. ⚠ Nothing is timed, drawn or costed in current (`plan.md` §14) | [`hardware/video3/README.md`](hardware/video3/README.md), [`hardware/video3/docs/plan.md`](hardware/video3/docs/plan.md), [`hardware/video3/docs/partition.md`](hardware/video3/docs/partition.md) |
| [`hardware/archive/`](hardware/archive/) | ⭐ **Retired designs, kept whole and kept citable.** [`hardware/archive/video/`](hardware/archive/video/) is the machine's *previous* video card — 640×200 × 256 colours, a display list, 33 ICs, three fitted `ATF1508AS`, simulated and repaired — and it is where this machine's **backplane, slot model, arbitration rule and clock tree were designed**, so the rest of the repository still cites `graphics.md` for those. [`hardware/archive/video2/`](hardware/archive/video2/) is a microcoded ANSI card that was planned and never built. | **Archived 2026-09-20 — superseded, not wrong** | [`hardware/archive/README.md`](hardware/archive/README.md) |
| [`hardware/audio/`](hardware/audio/) | 4-channel 8-bit PCM modelled on Paula, **with programmable panning**, 512 KB of samples in one package and a headphone-driven jack. ⭐ **35 ICs on an 18 cm card** — **two** `ATF1508AS`, both fitted. It reached 45 when the sequencer was built and came back the same day: programmable panning given up for classic MOD's fixed LRRL, and the counter, comparator and read-back latch absorbed into U1. Whether the analogue section fits the same card is open. Host reference model **builds and passes**. | ⭐ **Both CPLDs fitted, and the sequencer exactly fills its part; the card is simulated end to end — a sample byte reaches an `AD7528` and a buffer reloads from its shadow.** The analogue half is still unmeasured | [`hardware/audio/README.md`](hardware/audio/README.md), [`hardware/audio/docs/audio.md`](hardware/audio/docs/audio.md) |
| [`hardware/io/`](hardware/io/) | PS/2 keyboard and mouse — **11 ICs** of logic, because no period chip decodes PS/2. RS-232 serial — 3 ICs, because one does, and since 2026-09-09 it is a **`TL16C550C` at 115,200 baud with 16-byte FIFOs**. One 14-IC card. | **Both specified** | [`hardware/io/README.md`](hardware/io/README.md), [`hardware/io/ps2/docs/ps2.md`](hardware/io/ps2/docs/ps2.md), [`hardware/io/serial/docs/serial.md`](hardware/io/serial/docs/serial.md) |
| [`hardware/storage/`](hardware/storage/) | SD card interface — **8 ICs**, **537 KiB/s sustained**, an SPI burst started by the bus read strobe. ⭐ **8 and not 14 since 2026-09-20**: the block buffer that once made this card 16 packages is gone, and §4.4's 32-byte chunk-and-mask carries the read path as it already carried the write path. ⚠ The `TFM` hazard is mitigated, not retired — and §11.6 gives the 21 % back if the CPU's resume is specified. | ⭐ **Both GAL22V10s built, fitted and checked against Atmel's CUPL — 24 claims. The rest specified** | [`hardware/storage/README.md`](hardware/storage/README.md), [`hardware/storage/docs/sdcard.md`](hardware/storage/docs/sdcard.md) |
| [`hardware/net/`](hardware/net/) | 10BASE-T with no MAC or PHY chip — **12 ICs**, two `ATF1508AS`, ported from `~/code/applenet`. ⚠ The host takes **56 % of the wire**; its sixteen-frame ring lives in the machine's new physical space. | **Specified** | [`hardware/net/README.md`](hardware/net/README.md), [`hardware/net/docs/net.md`](hardware/net/docs/net.md) |
| [`hardware/mainboard/`](hardware/mainboard/) | The motherboard: the MMU (a 32 MB map), four SIMM sockets, a **1 MB boot ROM**, the clock and the six-slot backplane. [`docs/ram.md`](hardware/mainboard/docs/ram.md) is the memory system | **Schematic-level; boot, the map and all four SIMM windows simulate** | [`hardware/mainboard/README.md`](hardware/mainboard/README.md) |
| [`software/`](software/) | ⭐ Everything that runs *on* the machine: the boot ROM and its drawing **toolbox**, NitrOS-9 Level 2 off the SD card, the **desktop** it boots to, and the applications — *Pinball Construction Set*, a Stardew-like farm, *Mayhem in Monsterland*, a metroidvania scene, a tile-streamed world of any size (`tilescroll`), and Paint with its BBS and ANSI-art viewers | ⭐ **Boots from reset to the desktop off the card**, in simulation and on the host emulator | [`software/README.md`](software/README.md) |
| [`hardware/tools/`](hardware/tools/) | What every card shares: the 72-pin backplane pinout as one table and the tscircuit library, the JEDEC assembler and Atmel cross-checks, the Verilog generator and the whole-machine testbench | | [`hardware/README.md`](hardware/README.md) |

Machine-level material that belongs to no single card — the system map, and the
comparisons against the two chips this machine stands in the tradition of — is in
[`docs/`](docs/):

- [`docs/machine.md`](docs/machine.md) — the machine spec: bus, `$FF` map, interrupt
  ownership, clock tree, and now boot, system RAM, power and the electrical rules.
  **The open item that both card specs name as step 0.**
- [`software/nitros9/docs/drivewire.md`](software/nitros9/docs/drivewire.md) — the host link: virtual disks over serial for
  zero ICs, what it costs on each serial tier, and the machine's only source of a
  wall-clock time.
- [`docs/design-review.md`](docs/design-review.md) — the 2026-09-04 review of every
  subsystem, and what it changed. Start here if a document says something this one
  contradicts.
- [`docs/design-review2.md`](docs/design-review2.md) — ⛔ **the 2026-09-09 review, by
  simulation.** What the term-list checks could not see, why they could not see it, and
  the tooling (`make -C hardware sim`) it leaves behind. Both reviews are frozen dated
  records.
- [`docs/coco3_c64.md`](docs/coco3_c64.md) — GIME vs VIC-II, from a CPU-replacement's
  point of view.
- [`docs/video-comparison.md`](docs/video-comparison.md) — the video card against both
  of them.
- ⭐ [`software/toolbox/docs/proportional-font.md`](software/toolbox/docs/proportional-font.md) — a design study:
  antialiased proportional text, the Macintosh's strike and GEOS's mega-font, and
  what the copy engine can take off the CPU. ⛔ It corrects a 2026-09-21 claim in
  `boot-and-desktop.md` §5 item 8.
- ⭐ [`software/nitros9/docs/coarm-overlay.md`](software/nitros9/docs/coarm-overlay.md) — a design: CoArm's code
  window is **full to the byte**, and what an overlay would cost. ⛔ The crux is
  the build layout, not the mapping.
- ⭐ [`hardware/cpu/docs/6309.md`](hardware/cpu/docs/6309.md) — a plan: nothing in this machine has ever
  executed a 6309 instruction, what that costs, and how to simulate one before
  there is a Verilog core that is one.

[`reference/`](reference/) holds datasheets, service manuals and ROMs. The large scans
are deliberately **not** in git — see [`reference/README.md`](reference/README.md) — and
neither, since 2026-09-04, is anything this project has no right to redistribute
([`reference/68k/README.md`](reference/68k/README.md)).

**This repository has no licence of its own.** That is an omission, not a choice; see
`docs/design-review.md` §Sys-M6.

---

## Building

⭐ **`make`, everywhere.** Every component has a `Makefile` with the same targets —
`make help` lists them — and writes only to its own `build/`. From the root:

```sh
make check        # hardware's static checks (every GAL and CPLD design against its
                  #   model and Atmel's CUPL, the slot, the map, the documents' own
                  #   numbers) and software's fast ones - ~2 min
make sim          # the card testbenches under Verilator - ~4 min
make machine      # the whole machine off its boot ROM - ~25 min
make help         # the rest
```

and per component:

```sh
make -C hardware/audio help     # check, sim, oracle, modplay, bench, fit, host, test
make -C hardware/cpu firmware   # the STM32 timing spike -> hardware/cpu/build/arm/spike.elf
make -C software/pcs bench      # Pinball Construction Set's gate, ~8 min
```

**What it needs.** `verilator` (5.020 verified) for anything that simulates;
`bun` comes from `hardware/`'s own `devDependencies` (`npm ci` there, which the
Makefiles run for you); `cmake` and Ninja for the host builds;
`arm-none-eabi-gcc` (13.2.1 verified) for the firmware; `wine` and the WinCUPL
extraction for the CPLD fitter (`CLAUDE.md`). **Every software bench also needs
`../nitros9` on its `arm6309` branch**, and LWTOOLS and ToolShed:
`make -C software/tools all` builds them into `.tools/`.

The old `npm run check`, `check:video`, `check:machine`, … still work from
`hardware/`: they are aliases for these targets.

---

## Conventions

- **Paths in source comments and in cross-subsystem prose are repository-root-relative**
  — `hardware/cpu/src/gpio.c`, not `../src/gpio.c`. Inside a subsystem's own README, paths are
  relative to that subsystem and it says so at the top. Markdown *links* are always
  relative, because they have to resolve.
- **Every card's specification is one document**, and it owns its own open-items list and
  build order. Cross-document claims cite section numbers.
- **Superseded text is archived, not deleted — and not left in place.** Until
  2026-09-08 the rule was "marked, not deleted", and the specifications carried every
  overturned estimate inline; at ~500 markers they stopped being readable. Each
  component now splits in two: the **specification describes only the present
  design**, and a `history.md` beside it archives what was superseded, with dates and
  the reason each number moved (`hardware/archive/video/docs/history.md`, `hardware/audio/docs/history.md`,
  `hardware/cpu/docs/history.md`, `hardware/net/docs/history.md`, `hardware/storage/docs/history.md`,
  `hardware/io/ps2/docs/history.md`, `hardware/io/serial/docs/history.md`, `hardware/history.md`,
  `docs/history.md`). The wrong predictions are still visible on purpose — one
  directory over. A `⚠` in a spec now marks only a **live** hazard or unverified
  assumption, never a revision. Section numbers are never reused: a section whose
  content moved to history keeps its number as a one-line stub, so cross-document
  citations stay valid. `docs/design-review.md` is kept verbatim as a dated record.
