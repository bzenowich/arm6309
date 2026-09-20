# From Reset to a Desktop

## A Macintosh 128K Boot, and What This Machine Already Has For It

**Question this answers:** the owner wants the machine to boot the way a Mac 128K does —
ROM finds the video card, clears the screen, puts up a dialog with an icon saying it is
looking for a disk, changes the icon when it finds a bootable one, loads the operating
system off the SD card, and comes up on a desktop with a working file manager and an
application menu. **What is already built, what is a mock-up, and what is missing?**

**Short answer: the drawing is real, the boot half is nearly there, and the desktop is a
recording.** `v3desk`, `v3paint` and `v3menu` are not programs — they are scripted streams
of CoArm escape sequences, played with `copy /sd0/data/v3desk /w3`, that paint a *picture*
of a desktop. Everything needed to make them real exists in pieces; what does not exist is
the shell that ties the pieces together and an event loop.

> **Status: specified, nothing built.** The deliverable is this document.

---

## 0. The sequence, against what exists

| Mac 128K does | this machine | state |
|---|---|---|
| ROM finds the video hardware | `boot.asm`'s `vprobe` — writes `$A5`/`$5A` to `+$13` and reads back; video3 returns it, the archived card cannot (b2/b3 hardwired zero), an empty slot floats | ⭐ **built 2026-09-20** |
| clears the screen | the POST already paints all of 640 × 200 with the span writer | ⭐ built |
| a dialog, with an icon: *looking for a disk* | the ROM toolbox draws Haiku windows, bevels, anti-aliased text and icons — and **it already has a `disk` icon** | ⚠ §1 |
| the icon changes when a disk is found | same drawing path, a second icon | ⚠ §1 |
| loads the OS from the disk | `rbsd` reads the card **under NitrOS-9**; the ROM has no SD reader of its own, and the OS still boots from the ROM disk | ⛔ §2 |
| a desktop | `v3desk` is a **recording** | ⛔ §3 |
| a file manager | `v3trk` fills a Tracker window's list **from a real directory** | ⚠ §3 |
| an application menu | `v3menu` is a recording of one | ⛔ §3 |

---

## 1. The boot dialog — the small one, and it is next

The ROM toolbox (`tbox.asm`, ROM page `TB.Pg` = 64) draws exactly what the dialog needs:
`Window` (the Haiku tab and frame), `Icon`, `TextC`, `Bevel`, `Rect`. Its icon set already
contains `disk`, and also `paint`, `game`, `files`, `trash`, `home` — which §3's app menu
will want.

**What is in the way is the calling convention, not the drawing.** `tbox`'s entry wants
`U` = a CoWin window descriptor and `Y` = `VG`, the video globals — CoArm's context. At
boot there is no CoArm and no `VG`.

⭐ **AND THE ANSWER IS THAT `tbox` NEEDS NO CHANGE AT ALL** — found 2026-09-20,
after first proposing a "bare entry" that would have taken explicit parameters.
`CoG` is `Co.Data` = **`$6000`**, and `Co.WinA`/`Co.WinB` are `$A000`/`$C000`
(`defs/armvid.d`): they are **logical addresses in CoArm's own map**, not a
structure the caller passes. At boot the ROM owns the whole map, so it can
simply **reproduce that layout** — SIMM pages at `$6000`–`$9FFF` for the `CoG`
scratch (`TB.Buf` lives inside it), ROM page `TB.Pg` at `$A000`, the toolbox's
data pages at `$C000` — and then call it exactly as `ca_tbox.asm` does:
`ldd #$FF00+TB.Pg`, map, `jsr >Co.WinA+3`, with `Y` pointing at a fabricated
`VG` whose only live field is `VG.Base`.

⚠ **The work is in populating `CoG`, not in entering the toolbox.** The row
layer (`ca_row.asm`) keeps real state there — `CG.TStr` (0 means the card),
`CG.TTop`, `CG.RY`/`RX`/`RN`, `CG.Off`, `CG.DBlk`, `CG.WinA`/`CG.WinB` — and
the drawing layer keeps the clip `CG.CX0`–`CG.CY1` and origin `CG.OX`/`CG.OY`
in inclusive screen pixels. A caller must set the minimum those paths read,
and be able to say why everything it left alone is provably unread rather
than unread by luck.

⚠ **And `boot.asm` must map the toolbox page itself.** It already maps ROM pages — the ROM
disk driver does it with `ROM.Hi`, and the POST maps ROM for its own reads — so this is a
map write and a `jsr`, not new machinery. It is the same mechanism
[`ca_tbox.asm`](../../nitros9/level2/arm6309/modules/ca_tbox.asm) uses (`ldd #$FF00+TB.Pg`,
`MapA`, `jsr >Co.WinA+3`), with the POST in CoArm's place.

**Cost: one ROM page mapped for the length of the dialog, and no RAM at all.**

---

## 2. Booting NitrOS-9 off the card

Today the OS comes out of the ROM disk (`boot_romdisk.asm`, `rbromdisk.asm`). The card is
mounted *afterwards*, by a driver the OS loaded. To boot **from** the card the ROM needs to
read it before there is an OS, which means a second, minimal SD reader:

- **In the boot ROM**: §9.0's initialisation and §9.1's `CMD17` read, no filesystem — enough
  to pull `OS9Boot` off a known place on the card. `rbsd`'s init is ~400 bytes of the 983 it
  takes altogether, and the boot copy needs neither the write path nor the 512-byte cache.
  ⚠ It also needs `sdcard.md` §9.0's 74-clock power-up rule and the `SDMOSI` write that
  precedes it, or the card never enters SPI mode.
- **A NitrOS-9 `boot_sd` module** beside `boot_romdisk`, so the loaded kernel's own `Boot`
  reads from the same place.
- **Where `OS9Boot` lives on the card.** Simplest is an RBF filesystem and a fixed path, which
  costs the ROM a directory walk. Cheaper and more period-correct: a **fixed block range**
  recorded in a small header in block 0, which is what a Mac's boot blocks are.

⭐ **And the icon change in §1 is the honest signal of this step**: *looking* while the init
sequence runs, *found* once `CMD58` says `CCS` and block 0 carries the signature, and a third
state — the Mac's blinking question mark — when it does not. ⚠ **The ROM disk stays as the
fallback**, which is what makes the question-mark state recoverable rather than terminal.

---

## 3. The desktop, which is the whole job

⛔ **What looks like a desktop today is `copy /sd0/data/v3desk /w3`** — a byte stream of
CoArm escapes that draws icons, a Deskbar and a Tracker window. It is a faithful picture and
it is not a program: nothing is clickable, and the window that drags does so because
`v3drag` was told to drag it.

**But the pieces are real, and there are more of them than the mock-up suggests:**

| piece | what it already does |
|---|---|
| `tbox` | Haiku windows, bevels, icons, anti-aliased Noto Sans, images — from ROM, drawn in place |
| CoArm | windows, screens, the `/W1`–`/W5` devices, `SS.Excl` |
| `v3trk` | **fills a Tracker window's list from a real directory** — the file manager's list view, already reading the filesystem |
| `v3drag` | moves a window with the **copy engine** |
| `v3grab`, `v3scrl` | drag a picture, scroll a canvas |
| PS/2 mouse | `io/ps2`, and `ps2tst` reads real packets |
| `rbsd` + `/SD0` | a filesystem with directories to manage |

**So what is missing is the shell**: an event loop that reads the mouse and keyboard, a
front-window notion, hit-testing against a menu bar and a close box, and a launcher that
forks a program. That is a real program — and the honest estimate is that it is larger than
any single thing built for this machine so far, larger than the pinball scene.

**Suggested order, smallest useful thing first:**

1. **An event loop and a menu bar** that can pull down and highlight, over a static desktop.
   Nothing launches yet. This is where the mouse meets `tbox`'s drawing.
2. **The launcher**: menu items fork `pinball`, `monster`, `v3paint` from `/SD0/CMDS`.
   ⭐ At this point the machine does what the owner asked for, minus the file manager.
3. **The file manager**: `v3trk`'s directory list in a real window, with open, and a second
   window. Rename/copy/delete after.
4. **Windows that move and close** — `v3drag` already moves one with the copy engine.

⚠ **`stardew` is one of the three games and it is not built** —
[`video3/docs/stardew.md`](../video3/docs/stardew.md) specifies it. The menu can carry it
before it exists, as a greyed item, which is also how a person would notice it was missing.

---

## 4. What this costs the ROM, and the division of labour

The owner's framing has been consistent: **the ROM is for toolbox routines, the card is for
apps.** After today's work that is nearly literally true — the ROM disk is 72 % free and
holds a rescue system, the demos and their data are on the card.

This document does not change that. What it adds to the ROM is small and all of it is
*machine*, not *application*:

| | |
|---|---|
| the boot dialog | §1 — a few hundred bytes of POST, calling `tbox`, which is already there |
| a minimal SD reader | §2 — ~400 bytes, and it is the only way the card can become the boot device |
| ⭐ `tbox`'s bare entry | §1 — and it is what would let **any** program call the toolbox, which is its own open question (see §5) |

Everything in §3 is an application and belongs on the card.

---

## 5. Open items

1. ⭐ **The toolbox as an address-space extension.** Asked 2026-09-20: can any 64 K process
   reach the ROM toolbox through the MMU? The MMU needs no change — a slot can point at any
   ROM page — but it costs a **map slot**, which is what defeated `libv3` (`E$MemFul`), and a
   user-state switch is unsafe against a task switch unless the mapping is permanent.
   `F$MapBlk` exists and would make it permanent, ⚠ but this machine's block numbers address
   RAM only (`block b = physical page $200 + b`, from 4 MB) and the ROM is at 2–3 MB.
   CoArm's `$FF00 + page` convention is the missing piece. **Not yet designed.**
2. **Where `OS9Boot` lives on the card** — filesystem path or fixed blocks (§2).
3. **Whether the ROM disk stays bootable** once the card is. It should, and the question-mark
   state is why.
4. **The mouse under an exclusive-screen program.** The demos take `SS.Excl` and the desktop
   must not; how the two coexist is unexamined.
5. **`stardew` is unbuilt** and the other two games do not yet launch from anything.
