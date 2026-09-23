# `software/nitros9/` — NitrOS-9 Level 2 on this machine

NitrOS-9 Level 2 boots from the boot ROM to a shell on the serial console, running on the
host emulator. `docs/nitros9-av-plan.md` is the plan this belongs to. This README covers its
phase P0: the port skeleton that the video and audio drivers will be built on.

```sh
sh software/tools/fetch-nitros9-tools.sh       # LWTOOLS and ToolShed into .tools/ (once)
sh software/nitros9/run-emu.sh                 # build the ROM, boot it, type, check: 26 claims, ~30 s
sh software/nitros9/run-sd.sh                  # ... with an SD card in the socket: 17 claims, ~2 min
sh software/nitros9/run-sdboot.sh              # ⭐ BOOT THE OS OFF THE CARD: 45 claims, ~4 min
sh software/nitros9/mksddisk.sh out/demos.img  # ⭐ an SD image of the demo programs
BOOT=.../bootfile sh software/nitros9/mksddisk.sh out/boot.img   # ... a BOOTABLE one
```

```sh
SCENARIOS=nitros9 npm run check:machine        # the same ROM on the RTL machine: 19 claims, ~13 min (from hardware/)
SCENARIOS=reboot npm run check:machine         # ... and reboot through the boot ROM: 11 claims, ~14 min
SCENARIOS="disk nodisk" npm run check:machine  # ⭐ boot.asm 10a's boot dialog, both card-detect states: 52 claims, ~20 min
```

⛔ **The dialog pair needs a `V3=1` ROM and builds its own**, into
`/tmp/arm6309-dialog`. The toolbox it draws with is ROM page 64 and
`recipes/arm6309/arm6309.mak` only assembles it under `-DV3=1`; without the flag page
64 is 8 KB of zeros, `boot.asm` §10a finds no `"TB"` there and reports `$63`. The
`nitros9` and `reboot` runs above build the other flavour into `/tmp/arm6309-nitros9`,
and the recipe has one object directory — so alternating the two forces a clean rebuild,
which `mkrom.sh`'s `.flavour` stamp does on purpose.

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
| `level2/arm6309/modules/boot_sd.asm` | ⭐ the `Boot` module since 2026-09-21, and the recipe's default (`BOOTMOD`). `boot_common` reads `OS9Boot` **off the SD card** when block 0 carries `sdcard.md` §9.5's signature, and off the ROM disk when it does not — 881 bytes of the loader's 896 |
| `level2/arm6309/modules/boot_romdisk.asm` | the older `Boot` module, ROM disk only. `BOOTMOD=boot_romdisk` builds a ROM that cannot read a card at all, which is what "the card was used" is tested against |
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

## ⭐ There is no ROM disk: the card carries NitrOS-9 and the applications

The 488 K RBF image in ROM pages 3–63 was, until 2026-09-20, where every demo
program lived, and **it was full** — 6,656 bytes free, with `pinball` at 36 K
and a scene therefore having to ask the recipe for its command and give one
back (`CMDS_EXTRA` / `CMDS_DROP`). The machine has storage now
(`storage/docs/sdcard.md` §9.4), so:

⭐ **AND SINCE 2026-09-22 THE ROM KEEPS NOTHING AT ALL.** It carried a 61-page RBF
image — 499,712 bytes, 47.7 % of the flash — and now carries **no filesystem**: pages
3–63 are zeros. `machine.md` §7.2 has the map.

- **the ROM keeps** the boot monitor (the POST, §10a's dialog, the SD reader and the
  vectors), the loader and `krn`, and **the toolbox** the desktop and its apps draw
  with — that is all;
- **the card carries NitrOS-9**: `OS9Boot`, the whole command set, `MODULES`, `SYS`,
  `startup`, the applications **and their data**. ⚠ It answers to **both `/DD` and
  `/SD0`** — one descriptor source assembled twice — which is what lets `SysGo`,
  `init`, `armio.asm`'s `CoPath` and every program's `/DD` path keep working with no
  ROM disk under them;
- ⛔ **and with no bootable card the machine stops.** `boot.asm` blinks §10a's question
  mark for ever rather than handing off to a kernel with nothing to load. A blank card
  is written on a host, which is what a Macintosh needed too.

`recipes/arm6309/arm6309.mak`'s `$(DEMOS)` builds the programs into `.mods` (they are
part of `all`, so one that stops assembling is still noticed), `mkrom.sh` writes the
data set to `$OUT/data` **and a whole `system.img` beside the ROM**, and
**`mksyscard.sh`** is what decides what a system card carries — the command set and the
`/MODULES` list come out of `make print-syscard` / `print-modules`, so a card cannot
drift from the NitrOS-9 built beside it:

```sh
# ⭐ a BOOTABLE system card - NitrOS-9 itself plus the demos named
sh software/nitros9/mksyscard.sh /tmp/sd.img               # every demo the build made
sh software/nitros9/mksyscard.sh /tmp/sd.img mvania        # or the subset a bench wants
DATA=/tmp/out/data sh software/nitros9/mksyscard.sh /tmp/sd.img    # ... with its data

# ⛔ mksddisk.sh still builds a card with NO system on it, which since
# 2026-09-22 is a machine that does not start.  It is what run-sdboot.sh's
# `plain` control wants and nothing else.
sh software/nitros9/mksddisk.sh /tmp/data.img mvania
```

⭐ **AND THE LARGEST THING ON THE CARD IS NOT A PROGRAM.** `pinball`'s playfield is
`video3/bench/pcbtable.pic` — **327,680 bytes**, one palette index a pixel, 640 × 512,
**exactly 640 SD blocks** — and it goes into `DATA` beside the streams, with its
512-byte palette. ⛔ **It cannot be a module**: 327,680 bytes is five times the address
space a NitrOS-9 module may occupy, which is why that table was 61 interned 16 × 16
blocks composed into VRAM by 1,280 copies until 2026-09-21. `mkrom.sh` copies both files
into `$OUT/data` under `V3=1`, and the scene opens them **by bare name through `DOpen`**
(`/SD0/DATA/` first, `/DD/SYS/` after) so the desktop's Applications menu can fork it
from `/SD0/CMDS` and it still finds its table. ⚠ It reads in **11.1 s at 28.9 KiB/s** —
one `CMD17` a 512-byte block and a 6809 shifting every byte through SPI by hand — so the
scene shows a **loading screen** while it arrives, which is period-correct and is not
hidden (`video3/optimizations.md` §10.2).

⭐ **And the DESKTOP SHELL is one of them.** `desk` (`level2/arm6309/cmds/desk.asm`) is
the program `docs/boot-and-desktop.md` §3 asks for — an event loop on the PS/2 mouse, a
menu bar that pulls down and highlights, and a launcher that forks the other demos out of
`/SD0/CMDS`. It is an application and it lives on the card with them; `v3paint` goes with
it, because a menu item can fork a program and cannot fork the byte stream `v3show.py`
writes under that name. `video3/bench/run-v3desk.sh` runs both off a card and clicks at
them with a `PS2_SCRIPT`.

## ⭐ Booting off the card

Since 2026-09-21 `OS9Boot` comes off the SD card when there is a bootable one in the
socket. `storage/docs/sdcard.md` §9.5 is the design and `docs/boot-and-desktop.md` §2 is
the Macintosh story it belongs to; the short version:

| | |
|---|---|
| **What makes a card bootable** | `BOOT=<bootfile>` on `mksddisk.sh`. It runs `os9 gen` **first**, before any other file, so `OS9Boot` gets a contiguous run at a low LSN, and stamps the four bytes `"6309"` and a version at LSN 0 `+$F0`. Both are read back and checked before the script says `ok` |
| **Where it is** | `DD.BT` and `DD.BSZ` in `RBF`'s own volume header — LSN 0 `+$15` and `+$18`, the first half of SD block 0. No new structure, and `boot_common.asm` has read that pair since 2005 |
| **Who decides** | `boot.asm` §10b for the boot dialog's picture, `boot_sd.asm` for what is actually loaded. Neither trusts the other; both apply §9.5's rule |
| **Precedence** | ⛔ **the card, and nothing else, since 2026-09-22.** There is no ROM disk to fall back to: `BSNone` returns `E$NotRdy` and `boot.asm` blinks §10a's question mark for ever |
| ⭐ **How you can tell** | one character on the console between `krn`'s `tb` and `boot_common`'s `0`: `tb`**`s`**`0` is a card it read, `tb`**`n`** is no system disk |
| **Which benches boot off a card** | all of them now. `mkrom.sh` writes `system.img` beside the ROM and every bench passes it as `SDIMG`; a bench that wants its own card calls `mksyscard.sh` |

⛔ **`run-sdboot.sh` is the bench, and it asserts THREE CARD STATES.** Blessed,
**present and not bootable**, and empty — each booted from reset, and each `reboot`ed
back through `boot.asm`'s POST so that §10b's own verdict codes (`$64` bootable, `$65`
not) can be read off the progress port. ⭐ **Only the first reaches a shell**; the other
two take `D.Crash` with no `OS9Boot` to load, which is itself a claim. It also puts a
**different** `OS9Boot` on the blessed card — the recipe's bootfile with the FIRQ stub's
two modules appended — and asks `mdir` for them, so "it came off *this* card" does not
rest on a stale image in the build directory.

⚠ **The host emulator enters at `$8004`** by default, with `boot.asm`'s handoff already
applied, so the POST and the boot dialog do not run on a cold start there. `reboot`
re-enters at the reset vector, and ⭐ **`COLDBOOT=1`** starts at it — which is what
`software/nitros9/video/run-desk.sh` passes to put the POST and the dialog at the front
of the demo video. In Verilog, `machine_tb`'s `disk` scenario is a
cold start with the whole storage card and a blessed image in its socket.

### ⭐ `/DD/SYS` was 1,140 of the ROM image's 1,952 sectors

The second half, done 2026-09-20. Everything `mkrom.sh` generated — the Haiku
desktop and Paint's streams, the BBS and its ANSI art, the overworld's world
and tiles, the 28 console faces, the `vt*`/`vg*` scripted sessions — was
copied into `/DD/SYS`. That is **291,840 bytes, 58% of the ROM disk**, and
none of it is needed to boot or to bring up a console: nothing in the bootfile
opens a path under `/DD/SYS`, and the only thing `armio.asm` opens by name is
`/DD/CMDS/CoArm`. What stays is **`errmsg`** — the shell reads it to print
`Error #216 - Path Name Not Found` at all, so a system without it cannot tell
you what went wrong.

⚠ **`/DD/SYS` IS ON THE CARD since 2026-09-22**, with the rest of the filesystem.
`mksyscard.sh` copies `errmsg`, `$OUT/sys` and `$OUT/romsys` into it, so the two
knobs below mean the same thing they always did — they just land somewhere else.

| | |
|---|---|
| `SYSROM=all` | ⚠ puts the whole data set in `/DD/SYS` as well as `/DD/DATA`, in one word. The sessions that type `copy /dd/sys/...` pass it: `run-vid.sh`, `video/run-video.sh`, `video/run-video3.sh`. `SYSROM="a b c"` names individual files |
| `$OUT/sys` | the caller's own streams, dropped there before calling `mkrom.sh` (`run-v3text.sh`, `run-v3copyn.sh` do this). ⛔ Every name `mkrom.sh` generates is **removed** from it first, so yesterday's `SYSROM=all` cannot leave the data there and make a bench pass on nothing |

**How a program finds its data.** The streams are opened by whoever types the
command (`copy /sd0/data/v3desk /w3`), so the path is already the caller's. The
four programs that opened a file *for themselves* — `overworld`, `rastbar`,
`wave`, `changefont` — now name it **without a directory** and share a `DOpen`
routine that tries, in order:

1. the path the caller gave, if it has a `/` in it (`changefont` only, which
   already had that rule);
2. **`/SD0/DATA/<name>`** — the card, the copy that can be updated;
3. **`/DD/SYS/<name>`** — the card's own `SYS`, which is where `SYSROM=` and
   `$OUT/sys` land (`mksyscard.sh`). ⚠ This was the *ROM* disk until 2026-09-22;
   `/DD` is the card now, so both paths name the same volume and the second is
   only a second directory to look in.

⚠ Both are **absolute** on purpose. A bare relative name would resolve against
the caller's data directory, and a demo must not stop working because somebody
typed `chd`.

⚠ **The image is a whole number of 512-byte SD blocks** and is sized to what it
is given — a directory costs a whole eight-sector allocation unit however few
entries it has, which a first cut got wrong by twenty sectors. ⛔ **And every
file is read back off the image and compared with the source**, because
`os9 copy` prints *"disk is filled to capacity"* **and exits 0**: without the
round trip a short image announces itself as a good one and the machine loads
a module with a bad CRC.

`video3/bench/run-v3sd.sh` is the check: both cards, the Haiku desktop and
Paint drawn from the card, `changefont` reading a face through `DOpen`, a demo
program loaded off `/SD0` — and a negative control with an empty socket in
which every one of them fails to find what it needs and says so.

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
  both ports by `ps2.md` §7 and §11.2 and echoes what they send — three bytes a device, or
  `ps2tst N` for N of them, up to 24. The emulator models the
  card's receive counter literally, so a transmit that skips §7 step 1 (holding `KRST`)
  receives garbage there, as it would on the card.
  ⭐ **What there IS, since 2026-09-20, is a way to script the input**: `PS2_SCRIPT=file`
  (`software/demo/emu/ps2script.h`, `ps2.md` §11.5) takes `move to 320 240`, `click left`
  and `type "..."` at machine times and encodes them properly, so a GUI can be tested
  before the drivers or the card exist. `software/demo/emu/test/run-ps2script.sh` drives
  `ps2tst 24` with one and checks the bytes that come back — 27 claims, ~2 min.
- **The emulator's audio card is `audio/refplayer/card.c`**, register level, stepped per
  colour clock. Its host port is never busy (`ASTAT` b6), so a driver's wait on that bit
  runs only on the RTL.
- **Five NUL bytes follow the echo of every command line.** The descriptor's end-of-line
  null count is 0, so where they come from is not found yet. They are cosmetic, and
  `run-emu.sh` strips them before it checks anything.
- **SWI3 vectors through `$FFFA`** in `mc6809e.v` (`cpu6809.h` lists it). NitrOS-9 uses
  SWI3 only for user-installed vectors, so nothing here takes it, but a program that
  installs one would crash on this core.
