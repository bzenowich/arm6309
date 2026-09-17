# `software/nitros9/` — NitrOS-9 Level 2 on this machine

NitrOS-9 Level 2 boots from the boot ROM to a shell on the serial console, running on the
host emulator. `docs/nitros9-av-plan.md` is the plan this belongs to. This README covers its
phase P0: the port skeleton that the video and audio drivers will be built on.

```sh
sh software/tools/fetch-nitros9-tools.sh       # LWTOOLS and ToolShed into .tools/ (once)
sh software/nitros9/run-emu.sh                 # build the ROM, boot it, type, check: 23 claims, ~30 s
```

```sh
SCENARIOS=nitros9 npm run check:machine        # the same ROM on the RTL machine: 19 claims, ~13 min (from hardware/)
SCENARIOS=reboot npm run check:machine         # ... and reboot through the boot ROM: 11 claims, ~14 min
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
| `level2/modules/clock.asm` (`picothing+arm6309`) | the video card's VBL as the tick, polled through `VSTAT`; the video console's VBL service called from `VBLTick`, on the system stack; `DoPoll`'s carry set explicitly (below) |
| `level1/modules/kernel/fnproc.asm` (`IFNE arm6309`) | the idle loop calls the video console's idle work (`D.VBLSt`'s second vector) before it waits for an interrupt: the mouse pointer, which is too long for an IRQ |
| `level2/arm6309/modules/armio.asm` … `libvid.asm`, `defs/armvid.d`, `cmds/rastbar.asm`, `wave.asm`, `overworld.asm` | the video console and its test clients: `docs/video-console.md` |
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
| 1.41 s | the banner, `arm6309` |
| 3.06 s | the shell's prompt, the shell loaded from `/DD/CMDS` |
| 3.57 s | `dir`, typed at the UART, lists `OS9Boot CMDS MODULES SYS startup` |
| 4.10 s | `mfree` reports 8,104 KB free: RAM sized from `boot.asm`'s descriptor, on 16-bit blocks |
| 5.63 s | `firqtst q`: the audio card's timer on `/FIRQ`, 13 in 20 ticks and 30 in user state, registers intact |

`+scenario=reboot` boots, types `reboot`, and asserts that `boot.asm`'s POST ran again from its
reset vector (17 more progress codes, no `$E0`–`$EF`), that NitrOS-9 came back to a second
prompt at 4.9 s, and that `dir` works there.

It also asserts that the VBL tick was acknowledged (83 times by the second prompt) and
that the UART's INTR rose on the shared `/IRQ` (438 times). No cycle had two drivers on
`D0`–`D7` or on `A20`–`A13`. The emulator reaches the prompt at 1.55 s because it starts
at the handoff rather than at reset.

## How it boots

| ROM page | Holds | Runs at |
|---|---|---|
| 0 | `software/boot/boot.bin`: the monitor and the vector page | `$E000` |
| 1–2 | `"6309"`, `rel_arm6309`, then `OS9Kernel` (`Boot` padded to 1 K, then `krn`) | `$8000` |
| 3–63 | an RBF image of 1,952 sectors: `OS9Boot`, `CMDS`, `SYS`, `startup` | through the map |
| 64 | the **ROM toolbox**'s code (`tbox.asm`): Haiku's window chrome, anti-aliased text, icons, bevels, scroll bars and pictures, for CoArm's `ESC $6A` | in place, at `Co.WinA` in CoArm's map |
| 65–127 | its data (`tools/mktbox.py`): the directory, the Haiku palette, Noto Sans 12 px regular and bold, the icons, the paint document | through CoArm's `Co.WinB` |

1. **The monitor** finds `"6309"` and jumps to `$8004` (`software/boot/README.md`).
2. **The loader** does the following:
   - sets every map entry's high byte to `$02`, so NitrOS-9's 8-bit block numbers are the
     first 2 MB of SIMM socket 0;
   - copies `OS9Kernel` to `$E800`–`$FEFF` in block `$3F`;
   - puts `D.BtBug`, `D.Crash` and a trampoline at `$EB80`;
   - maps block `$3F` at slot 7 and enters `krn`.
3. **`krn`** sizes RAM to 2 MB, validates `Boot` and itself, and calls `F$Boot`.
4. **`Boot`** reads LSN 0 and the bootfile through map slot 1, pointed at the ROM page.
5. **`SysGo`** prints the banner and runs `startup`, then `Shell i=/term`. The shell is
   not in the bootfile: `SysGo` forks it from `/DD/CMDS`, and the 7 K it would take of the
   64 K system map is left for drivers attached after boot (`docs/video-console.md`).

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

## `reboot`

`F$Debug` with `A` = 255 (superuser only; the `reboot` command) is a cold start on a CoCo 3,
into Disk BASIC by way of GIME registers. Here it runs the power-on path again, without a
`/RESET`, which software cannot assert:

1. It turns off every interrupt source the boot ROM does not reprogram: the audio card's
   `ACTRL`, `AINTENA`, `ADMACON` and `AINTREQ` (polling `ASTAT` b6); the PS/2 card's
   `IOCTRL`; the UART's `IER`; and the video card's `CTRL`, after `SPANBUSY`.
2. It copies a stub to block 0, the one slot it does not move. The stub maps ROM page 0 at
   slot 7 and jumps through the reset vector.
3. `boot.asm` runs its whole POST with the map already live. Its first act rewrites all
   sixteen map entries, with block 7 on the page it is running from, and setting `RUN`
   again does nothing. It then hands page 1 the machine, and NitrOS-9 boots.

The emulator shows it too. Running `boot.asm` there needed the MMU's VRAM window, which
`machine.c` did not model: `boot.asm` writes its display lists through it.

## What differs from a CoCo 3, and what the kernel does about it

| | CoCo 3 | This machine | Handled by |
|---|---|---|---|
| **Map registers** | GIME `$FFA0`–`$FFAF`, two tasks | the same low bytes, plus a high byte at `$FF90`–`$FF9F` | the loader sets the high bytes once; the kernel never writes them |
| **Task register** | `$FF91` bit 0 | `$FFB0` bit 0 | `DAT.Task` |
| **Constant page** | `$FE00`–`$FEFF` is always block `$3F` | **none** | slot 7 of every map is `KrnBlk`, forced at each task switch, as on the Pico-Thing |
| **Vectors** | ROM points at `$FEEE`–`$FEFD` | **the same.** `boot.asm` was changed to match | the kernel is padded to end at `$FF00`; the assembly fails if the stubs would miss |
| **FIRQ** | unused, and it crashes | the audio card's timer and buffers | `ArmFIRQ`: its own stack in slot 7, the system map, `jsr [D.FIRQ]` |
| **Tick** | GIME VSYNC, 60 Hz | video card VBL, `VSTAT` b0, acknowledged by any write: **70.086 Hz or 59.940 Hz**, as `VMODE0` says | `clock.asm` waits out `SPANBUSY` before acknowledging (`graphics.md` §19 item 39). Each tick adds its own length, in 2^-20 s, to a 24-bit accumulator, so neither rate needs to be an integer and a `VMODE` change needs no call into the clock (`defs/arm6309.d`). `vmodetst` checks both families |
| **RAM** | up to 2 MB, blocks `$00`–`$FF`, sized by a probe | up to 16 MB, on a 16-bit map entry | **8 MB**, blocks `$000`–`$3FF`, from SIMM socket 0 up. A block number is 16 bits end to end: every kernel site that points a map slot at a block writes both bytes (`RAM.Hi` plus the high byte), and none of them touches the stack while a slot is moved. The block map is 1,024 bytes at `$E000` in the kernel's block. The size comes from `boot.asm`'s own SIMM descriptor, not a probe. ⚠ 1,024 blocks because `F$GBlkMp`'s callers pass a 1,024-byte buffer; the rest of a full bank needs another call. `memtst` checks every free block is distinct memory |

⛔ **`clock.asm`'s `DoPoll` returned carry set for every device IRQ.** It ends with `TSTB`,
which leaves carry alone, and carry there is `D.Poll`'s "no more devices" from the last call.
The kernel took every non-tick IRQ as unclaimed and returned to the interrupted code with
`/IRQ` masked, until something unmasked it: 3 ms under the shell, measured by the video
console's `run-vid.sh`. The arm6309 build sets carry explicitly. ⚠ Pico-Thing's build shares
the code and is left as `main` has it.

## ⚠ What P0 does not do yet

- **A 6809 build only.** The machine's CPU core is `mc6809e.v` and the emulator follows it.
  The recipe builds `CPU=6309` too (both kernels place their stubs at `$FEEE`), but nothing
  has run the 6309 build.
- **8 MB of RAM, not 16.** `F$GBlkMp` hands its caller a 1,024-byte buffer, so the block map
  stops at 1,024 blocks. RAM must start at socket 0: a machine whose socket 0 is empty (or
  holds an aliasing module) halts in the loader. `pmap` prints only a block's low byte.
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
