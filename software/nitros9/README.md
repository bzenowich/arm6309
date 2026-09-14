# `software/nitros9/` — NitrOS-9 Level 2 on this machine

NitrOS-9 Level 2 boots from the boot ROM to a shell on the serial console, running on the
host emulator. `docs/nitros9-av-plan.md` is the plan this belongs to. This README covers its
phase P0: the port skeleton that the video and audio drivers will be built on.

```sh
sh software/tools/fetch-nitros9-tools.sh       # LWTOOLS and ToolShed into .tools/ (once)
sh software/nitros9/run-emu.sh                 # build the ROM, boot it, type, check: 18 claims, ~20 s
```

```sh
SCENARIOS=nitros9 npm run check:machine        # the same ROM on the RTL machine: 12 claims, ~3 min (from hardware/)
```

`run-emu.sh` rebuilds `software/boot/boot.bin` and the NitrOS-9 ROM (`mkrom.sh`, which also
writes the `.hex` the RTL loads). It then boots on
`software/demo/emu/`, types `dir`, `mfree`, `date -t`, `sleep 2100` and `procs` at the
shell (including `firqtst`, twice), and checks the console output. **Its exit code is the answer.** The full console
is kept as `/tmp/arm6309-nitros9/console.txt`.

## Where the port lives

The port is written in the NitrOS-9 tree, the way every NitrOS-9 port is. It is on the
**`arm6309` branch of `../nitros9`** (`NITROS9DIR` overrides the path). This repository
holds what the port depends on: the boot ROM's vector page, the emulator, and this check.

| In `$NITROS9DIR` | What it is |
|---|---|
| `defs/arm6309.d` | the machine: the map, the I/O page, the tick, the ROM layout |
| `level2/arm6309/modules/rel_arm6309.asm` | ROM pages 1–2. The loader that `boot.asm` hands off to, followed by `OS9Kernel` |
| `level2/arm6309/modules/boot_romdisk.asm` | the `Boot` module. `boot_common` reads `OS9Boot` from the ROM disk |
| `level2/arm6309/modules/rbromdisk.asm`, `romdiskdesc.asm` | the read-only RBF driver, serving `/DD` and `/R0` |
| `level2/arm6309/modules/term_16550.asm` | `/Term` on the TL16C550C, using Wildbits' `sc16550` driver |
| `level2/modules/kernel/krn.asm` (`IFNE arm6309`) | ends at `$FF00`, so the vector stubs sit at `$FEEE`; forces slot 7 to `KrnBlk` |
| `level2/modules/kernel/krn.asm` (`ArmFIRQ`) | the `/FIRQ` stub, below |
| `level2/arm6309/modules/firqtstdrv.asm`, `firqtstdesc.asm`, `cmds/firqtst.asm` | the stub's test: the audio card's timer at 50 Hz, counted. In `/DD/MODULES` and `CMDS` |
| `level2/modules/clock.asm` (`picothing+arm6309`) | the video card's VBL as the tick, polled through `VSTAT` |
| `recipes/arm6309/l2` | `make` builds `arm6309_rom.bin`, 1 MB |

The edits to shared files are `IFNE`-guarded. **Every other port's modules assemble
byte-identical to `main`**, checked on 2026-09-14 for Pico-Thing, CoCo 3 and Wildbits:
`krn`, `clock`, `init`, `sysgo` and `sc16550`, each as a 6809 and a 6309 build.

## ⭐ On the RTL machine

`machine_tb +scenario=nitros9` runs the whole path on `mc6809e.v`, `mainboard.v` and
`video_card.v`, with `tl16c550.v` at `$FF38` as the console. It starts at the reset
vector, runs every stage of `boot.asm`, and then:

| Machine time | The console shows |
|---|---|
| 0.76 s | `RK`: `boot.asm` handed over at `$8004` and the loader entered `krn` |
| 1.03 s | the bootfile's module list, read from the ROM disk through the map's ROM pages |
| 1.40 s | the banner, `arm6309` |
| 2.22 s | the shell's prompt |
| 2.61 s | `dir`, typed at the UART, lists `OS9Boot CMDS MODULES SYS startup` |

It also asserts that the VBL tick was acknowledged (83 times by the second prompt) and
that the UART's INTR rose on the shared `/IRQ` (438 times). No cycle had two drivers on
`D0`–`D7` or on `A20`–`A13`. The emulator reaches the prompt at 1.55 s because it starts
at the handoff rather than at reset.

## How it boots

| ROM page | Holds | Runs at |
|---|---|---|
| 0 | `software/boot/boot.bin`: the monitor and the vector page | `$E000` |
| 1–2 | `"6309"`, `rel_arm6309`, then `OS9Kernel` (`Boot` padded to 1 K, then `krn`) | `$8000` |
| 3–127 | an RBF image of 4,000 sectors: `OS9Boot`, `CMDS`, `SYS`, `startup` | through the map |

1. **The monitor** finds `"6309"` and jumps to `$8004` (`software/boot/README.md`).
2. **The loader** does the following:
   - sets every map entry's high byte to `$02`, so NitrOS-9's 8-bit block numbers are the
     first 2 MB of SIMM socket 0;
   - copies `OS9Kernel` to `$E800`–`$FEFF` in block `$3F`;
   - puts `D.BtBug`, `D.Crash` and a trampoline at `$EB80`;
   - maps block `$3F` at slot 7 and enters `krn`.
3. **`krn`** sizes RAM to 2 MB, validates `Boot` and itself, and calls `F$Boot`.
4. **`Boot`** reads LSN 0 and the bootfile through map slot 1, pointed at the ROM page.
5. **`SysGo`** prints the banner and runs `startup`, then `Shell i=/term`.

The console shows every stage: `R` (loader), `K` (kernel), the module names, `t` `b` `0`,
a dot per bootfile sector, then the module directory and the banner.

## `/FIRQ`

Stock Level 2 crashes on any FIRQ. `FIRQVCT` forces task 0 and `DP` 0 on an entry that
stacked only `PC` and `CC`, so nothing could return. This machine's audio card is its only
`/FIRQ` source, so `krn.asm`'s `ArmFIRQ` gives a FIRQ a real entry:

1. It saves `S` and switches to a 192-byte FIRQ stack in the kernel's block. That block is
   slot 7 of every map, so the stack is valid before the map changes.
2. It saves `D`, `DP`, `X`, `Y` and `U`, selects the system map, and clears `D.TINIT`
   bit 0, as the IRQ path does.
3. It calls `jsr [D.FIRQ]` with `U` = `D.FIRQSt`, the owner's static storage.
4. It restores the interrupted map, then the registers and `S`, and returns with `RTI`.

With no owner installed, `D.FIRQ` still reaches `D.Crash`, as on every other port. The
service contract (masked, system map, acknowledge the level before `rts`) and the install
and remove sequence are in `defs/arm6309.d`.

**How it is checked.** Run `load /dd/modules/firqtst`, then `firqtst`. It starts the audio
card's tempo timer at 50 Hz and prints two counts:

| Line | What it shows |
|---|---|
| `FIRQs in 100 ticks: 70` | FIRQs taken in the system map while the kernel idles |
| `FIRQs in user state: 118, registers intact` | FIRQs taken inside a user busy loop that holds `A`, `B` and `DP` and steps `X`, `Y` and `U` to known values |

`run-emu.sh` runs it twice. The second run follows the driver's Term, which puts the
previous service back, so it also checks installing and removing a service. ⭐ **The
check can fail.** A stub built to corrupt `Y` before its `RTI` made the second line read
`CORRUPTED`.

## What differs from a CoCo 3, and what the kernel does about it

| | CoCo 3 | This machine | Handled by |
|---|---|---|---|
| **Map registers** | GIME `$FFA0`–`$FFAF`, two tasks | the same low bytes, plus a high byte at `$FF90`–`$FF9F` | the loader sets the high bytes once; the kernel never writes them |
| **Task register** | `$FF91` bit 0 | `$FFB0` bit 0 | `DAT.Task` |
| **Constant page** | `$FE00`–`$FEFF` is always block `$3F` | **none** | slot 7 of every map is `KrnBlk`, forced at each task switch, as on the Pico-Thing |
| **Vectors** | ROM points at `$FEEE`–`$FEFD` | **the same.** `boot.asm` was changed to match | the kernel is padded to end at `$FF00`; the assembly fails if the stubs would miss |
| **FIRQ** | unused, and it crashes | the audio card's timer and buffers | `ArmFIRQ`: its own stack in slot 7, the system map, `jsr [D.FIRQ]` |
| **Tick** | GIME VSYNC, 60 Hz | video card VBL, `VSTAT` b0, acknowledged by any write: **70.086 Hz or 59.940 Hz**, as `VMODE0` says | `clock.asm` waits out `SPANBUSY` before acknowledging (`graphics.md` §19 item 39). Each tick adds its own length, in 2^-20 s, to a 24-bit accumulator, so neither rate needs to be an integer and a `VMODE` change needs no call into the clock (`defs/arm6309.d`). `vmodetst` checks both families |
| **RAM** | up to 2 MB, blocks `$00`–`$FF` | up to 16 MB on the high byte | **2 MB for now**, the first socket's first 2 MB |

## ⚠ What P0 does not do yet

- **A 6809 build only.** The machine's CPU core is `mc6809e.v` and the emulator follows it.
  The recipe builds `CPU=6309` too (both kernels place their stubs at `$FEEE`), but nothing
  has run the 6309 build.
- **The FIRQ stub is checked on the emulator only.** `machine_tb`'s machine has no audio
  card (`AUDIO = 0`), so nothing raises `/FIRQ` on the RTL yet.
- **2 MB of RAM**, from one socket. Using more needs the memory manager to handle a block
  number wider than 8 bits (plan item X2, `hardware/ram.md` §9).
- **No input device but the UART.** The PS/2 drivers are phase P1. `ps2tst` initialises
  both ports by `ps2.md` §7 and §11.2 and echoes what they send. The emulator models the
  card's receive counter literally, so a transmit that skips §7 step 1 (holding `KRST`)
  receives garbage there, as it would on the card.
- **The emulator's audio card is `audio/refplayer/card.c`**, register level, stepped per
  colour clock. Its host port is never busy (`ASTAT` b6), so a driver's wait on that bit
  runs only on the RTL.
- **Five NUL bytes follow the echo of every command line.** The descriptor's end-of-line
  null count is 0, so where they come from is not found yet. They are cosmetic, and
  `run-emu.sh` strips them before it checks anything.
- **SWI3 vectors through `$FFFA`** in `mc6809e.v` (`cpu6809.h` lists it). NitrOS-9 uses
  SWI3 only for user-installed vectors, so nothing here takes it, but a program that
  installs one would crash on this core.
